"""LLM client implementations that satisfy `oct.agent.LLMClient` Protocol.

Keeps all vendor-specific SDK usage in one module so that swapping providers
(Anthropic, OpenAI, local models) only requires adding a sibling class.

T-006 scope: Anthropic Messages API wrapper with:
  - model / temperature / max_tokens configuration
  - exponential-backoff retry on transient errors
  - deterministic call counting for observability
"""
from __future__ import annotations

import os
import random
import time
from dataclasses import dataclass, field
from typing import Callable, List, Optional


DEFAULT_MODEL = "claude-sonnet-4-6"
DEFAULT_MAX_TOKENS = 1024


class LLMError(RuntimeError):
    """Raised when the LLM call fails after all retry attempts."""


@dataclass
class RetryConfig:
    max_attempts: int = 3
    initial_backoff_sec: float = 1.0
    backoff_multiplier: float = 2.0
    jitter: float = 0.25  # +/- fraction of the backoff delay


@dataclass
class AnthropicClient:
    """Thin wrapper around `anthropic.Anthropic().messages.create`.

    Satisfies `oct.agent.LLMClient`: exposes `.complete(system, user, temperature)`.

    Construction:
        client = AnthropicClient(api_key=..., model="claude-sonnet-4-6")
    If `api_key` is None, the Anthropic SDK picks up `ANTHROPIC_API_KEY` from env.

    A `sleep_fn` hook is exposed so tests can run without real sleeps.
    """

    api_key: Optional[str] = None
    model: str = DEFAULT_MODEL
    max_tokens: int = DEFAULT_MAX_TOKENS
    retry: RetryConfig = field(default_factory=RetryConfig)
    sleep_fn: Callable[[float], None] = time.sleep
    _client: object = field(default=None, init=False, repr=False)
    call_count: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        # Lazy import so the module can be imported even if anthropic isn't installed
        # (e.g. in CI running unit tests with FakeLLM only).
        try:
            import anthropic  # type: ignore
        except ImportError as exc:  # pragma: no cover
            raise ImportError(
                "The `anthropic` package is required for AnthropicClient. "
                "Install it with `pip install anthropic`."
            ) from exc
        api_key = self.api_key or os.environ.get("ANTHROPIC_API_KEY")
        self._client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()

    def complete(self, system: str, user: str, temperature: float = 0.8) -> str:
        """Invoke the Messages API with retry. Returns the assistant text."""
        self.call_count += 1
        last_exc: Optional[BaseException] = None
        delay = self.retry.initial_backoff_sec
        for attempt in range(1, self.retry.max_attempts + 1):
            try:
                response = self._client.messages.create(  # type: ignore[attr-defined]
                    model=self.model,
                    max_tokens=self.max_tokens,
                    temperature=temperature,
                    system=system,
                    messages=[{"role": "user", "content": user}],
                )
                return _extract_text(response)
            except Exception as exc:  # broad: SDK raises many subclasses
                last_exc = exc
                if not _is_retryable(exc) or attempt >= self.retry.max_attempts:
                    break
                jitter_range = delay * self.retry.jitter
                actual_delay = delay + random.uniform(-jitter_range, jitter_range)
                self.sleep_fn(max(0.0, actual_delay))
                delay *= self.retry.backoff_multiplier
        raise LLMError(
            f"Anthropic API call failed after {self.retry.max_attempts} attempt(s): {last_exc!r}"
        ) from last_exc


def _extract_text(response: object) -> str:
    """Concatenate text blocks from an Anthropic Messages response."""
    content = getattr(response, "content", None)
    if content is None:
        raise LLMError(f"Response has no content: {response!r}")
    parts: List[str] = []
    for block in content:
        block_type = getattr(block, "type", None)
        if block_type == "text":
            parts.append(getattr(block, "text", ""))
    if not parts:
        raise LLMError(f"Response has no text blocks: {response!r}")
    return "".join(parts)


def _is_retryable(exc: BaseException) -> bool:
    """Decide whether an exception from the SDK is worth retrying.

    Retries on rate-limit (429), 5xx, connection/timeout errors. Does not
    retry on 4xx client errors (bad key, bad request).
    """
    name = exc.__class__.__name__
    retryable_names = {
        "RateLimitError",
        "APIConnectionError",
        "APITimeoutError",
        "InternalServerError",
        "APIError",  # some SDK versions use this for 5xx
    }
    if name in retryable_names:
        return True
    # Check status_code if present (some SDK exceptions expose it)
    status = getattr(exc, "status_code", None)
    if isinstance(status, int) and (status == 429 or 500 <= status < 600):
        return True
    return False
