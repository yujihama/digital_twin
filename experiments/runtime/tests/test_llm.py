"""Tests for AnthropicClient.

All tests run without real API calls by injecting a fake `messages.create`.
The AnthropicClient constructor requires `anthropic` to be importable, but
never calls it — we replace `_client` after construction.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

import pytest

from oct.llm import (
    AnthropicClient,
    LLMError,
    OpenAIClient,
    RetryConfig,
    _extract_openai_text,
    _extract_text,
    _is_retryable,
)


# --- fake anthropic response objects ---------------------------------------

@dataclass
class FakeTextBlock:
    type: str
    text: str


@dataclass
class FakeResponse:
    content: List[FakeTextBlock]


class FakeMessages:
    def __init__(self, outcomes):
        """outcomes: list of either a FakeResponse or an Exception."""
        self._outcomes = list(outcomes)
        self.calls: List[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


class FakeAnthropicSDK:
    def __init__(self, messages: FakeMessages) -> None:
        self.messages = messages


# --- helpers ---------------------------------------------------------------

def make_client(outcomes, **kwargs) -> AnthropicClient:
    """Build a client whose underlying SDK is a fake with canned outcomes."""
    client = AnthropicClient(api_key="test-key", sleep_fn=lambda _s: None, **kwargs)
    client._client = FakeAnthropicSDK(FakeMessages(outcomes))
    return client


def ok_response(text: str) -> FakeResponse:
    return FakeResponse(content=[FakeTextBlock(type="text", text=text)])


# --- _extract_text ---------------------------------------------------------

def test_extract_text_concatenates_blocks():
    resp = FakeResponse(
        content=[
            FakeTextBlock(type="text", text="Hello "),
            FakeTextBlock(type="text", text="world"),
        ]
    )
    assert _extract_text(resp) == "Hello world"


def test_extract_text_skips_non_text_blocks():
    resp = FakeResponse(
        content=[
            FakeTextBlock(type="tool_use", text="ignored"),
            FakeTextBlock(type="text", text="kept"),
        ]
    )
    assert _extract_text(resp) == "kept"


def test_extract_text_no_text_raises():
    resp = FakeResponse(content=[FakeTextBlock(type="tool_use", text="x")])
    with pytest.raises(LLMError):
        _extract_text(resp)


# --- _is_retryable ---------------------------------------------------------

def test_is_retryable_by_class_name():
    class RateLimitError(Exception):
        pass

    assert _is_retryable(RateLimitError("slow down")) is True


def test_is_retryable_by_status_code():
    exc = RuntimeError("boom")
    exc.status_code = 503  # type: ignore[attr-defined]
    assert _is_retryable(exc) is True


def test_not_retryable_on_4xx():
    exc = RuntimeError("bad request")
    exc.status_code = 400  # type: ignore[attr-defined]
    assert _is_retryable(exc) is False


def test_not_retryable_on_unknown_exception():
    assert _is_retryable(ValueError("x")) is False


# --- AnthropicClient.complete ---------------------------------------------

def test_complete_happy_path():
    client = make_client([ok_response("the answer is 42")])
    out = client.complete(system="sys", user="usr", temperature=0.5)
    assert out == "the answer is 42"
    assert client.call_count == 1
    call = client._client.messages.calls[0]
    assert call["system"] == "sys"
    assert call["messages"] == [{"role": "user", "content": "usr"}]
    assert call["temperature"] == 0.5


def test_complete_retries_then_succeeds():
    class APIConnectionError(Exception):
        pass

    client = make_client(
        [APIConnectionError("network blip"), ok_response("ok")],
        retry=RetryConfig(max_attempts=3, initial_backoff_sec=0.0, jitter=0.0),
    )
    out = client.complete(system="s", user="u")
    assert out == "ok"
    assert len(client._client.messages.calls) == 2


def test_complete_gives_up_after_max_attempts():
    class APIConnectionError(Exception):
        pass

    client = make_client(
        [APIConnectionError("fail")] * 5,
        retry=RetryConfig(max_attempts=3, initial_backoff_sec=0.0, jitter=0.0),
    )
    with pytest.raises(LLMError) as exc_info:
        client.complete(system="s", user="u")
    assert "3 attempt(s)" in str(exc_info.value)
    assert len(client._client.messages.calls) == 3


def test_complete_does_not_retry_on_client_error():
    class BadRequestError(Exception):
        def __init__(self):
            super().__init__("bad request")
            self.status_code = 400

    client = make_client(
        [BadRequestError(), ok_response("never reached")],
        retry=RetryConfig(max_attempts=3, initial_backoff_sec=0.0, jitter=0.0),
    )
    with pytest.raises(LLMError):
        client.complete(system="s", user="u")
    # Only one call made — 400 is not retried
    assert len(client._client.messages.calls) == 1


# ---------------------------------------------------------------------------
# OpenAIClient tests
# ---------------------------------------------------------------------------


@dataclass
class FakeOpenAIMessage:
    content: str


@dataclass
class FakeOpenAIChoice:
    message: FakeOpenAIMessage


@dataclass
class FakeOpenAIResponse:
    choices: List[FakeOpenAIChoice]


class FakeChatCompletions:
    def __init__(self, outcomes) -> None:
        self._outcomes = list(outcomes)
        self.calls: List[dict] = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


class FakeOpenAIChat:
    def __init__(self, completions: FakeChatCompletions) -> None:
        self.completions = completions


class FakeOpenAISDK:
    def __init__(self, chat: FakeOpenAIChat) -> None:
        self.chat = chat


def make_openai_client(outcomes, **kwargs) -> OpenAIClient:
    client = OpenAIClient(api_key="test-key", sleep_fn=lambda _s: None, **kwargs)
    client._client = FakeOpenAISDK(FakeOpenAIChat(FakeChatCompletions(outcomes)))
    return client


def ok_openai_response(text: str) -> FakeOpenAIResponse:
    return FakeOpenAIResponse(choices=[FakeOpenAIChoice(message=FakeOpenAIMessage(content=text))])


# --- _extract_openai_text --------------------------------------------------


def test_extract_openai_text_happy():
    assert _extract_openai_text(ok_openai_response("hello")) == "hello"


def test_extract_openai_text_no_choices_raises():
    resp = FakeOpenAIResponse(choices=[])
    with pytest.raises(LLMError):
        _extract_openai_text(resp)


def test_extract_openai_text_empty_content_raises():
    resp = FakeOpenAIResponse(
        choices=[FakeOpenAIChoice(message=FakeOpenAIMessage(content=""))]
    )
    with pytest.raises(LLMError):
        _extract_openai_text(resp)


# --- OpenAIClient.complete -------------------------------------------------


def test_openai_complete_happy_path():
    client = make_openai_client([ok_openai_response("42")], model="gpt-4.1-mini")
    out = client.complete(system="sys", user="usr", temperature=0.3)
    assert out == "42"
    assert client.call_count == 1
    call = client._client.chat.completions.calls[0]
    assert call["model"] == "gpt-4.1-mini"
    assert call["temperature"] == 0.3
    assert call["messages"][0] == {"role": "system", "content": "sys"}
    assert call["messages"][1] == {"role": "user", "content": "usr"}


def test_openai_complete_retries_then_succeeds():
    class APIConnectionError(Exception):
        pass

    client = make_openai_client(
        [APIConnectionError("blip"), ok_openai_response("ok")],
        retry=RetryConfig(max_attempts=3, initial_backoff_sec=0.0, jitter=0.0),
    )
    out = client.complete(system="s", user="u")
    assert out == "ok"
    assert len(client._client.chat.completions.calls) == 2


def test_openai_complete_gives_up_after_max_attempts():
    class APIConnectionError(Exception):
        pass

    client = make_openai_client(
        [APIConnectionError("fail")] * 5,
        retry=RetryConfig(max_attempts=3, initial_backoff_sec=0.0, jitter=0.0),
    )
    with pytest.raises(LLMError) as exc_info:
        client.complete(system="s", user="u")
    assert "3 attempt(s)" in str(exc_info.value)
    assert len(client._client.chat.completions.calls) == 3


def test_openai_complete_does_not_retry_on_client_error():
    class BadRequestError(Exception):
        def __init__(self):
            super().__init__("bad request")
            self.status_code = 400

    client = make_openai_client(
        [BadRequestError(), ok_openai_response("never")],
        retry=RetryConfig(max_attempts=3, initial_backoff_sec=0.0, jitter=0.0),
    )
    with pytest.raises(LLMError):
        client.complete(system="s", user="u")
    assert len(client._client.chat.completions.calls) == 1
