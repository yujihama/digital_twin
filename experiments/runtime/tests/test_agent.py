"""Tests for generic Agent abstraction + buyer_a persona.

Uses a FakeLLM so tests run without API calls (no network, deterministic).
"""
from __future__ import annotations

from typing import List

import pytest

from oct.agent import (
    ActionOption,
    Agent,
    AgentAction,
    parse_action_json,
)
from oct.environment import EnvironmentState, PurchaseRequest, RequestStatus
from oct.personas.buyer_a import (
    BUYER_A_ACTIONS,
    BUYER_A_PERSONA,
    build_observation,
    make_agent,
)


class FakeLLM:
    """Deterministic LLM that returns canned responses in order."""

    def __init__(self, responses: List[str]) -> None:
        self._responses = list(responses)
        self.calls: List[dict] = []

    def complete(self, system: str, user: str, temperature: float = 0.8) -> str:
        self.calls.append({"system": system, "user": user, "temperature": temperature})
        if not self._responses:
            raise RuntimeError("FakeLLM exhausted")
        return self._responses.pop(0)


# --- parse_action_json -----------------------------------------------------

def test_parse_action_plain_json():
    raw = '{"action_type": "wait", "parameters": {}, "reasoning": "nothing to do"}'
    action = parse_action_json(raw)
    assert action.action_type == "wait"
    assert action.parameters == {}
    assert action.reasoning == "nothing to do"


def test_parse_action_with_fenced_code():
    raw = '```json\n{"action_type": "draft_request", "parameters": {"vendor": "V1", "item": "bolt", "amount": 50000}}\n```'
    action = parse_action_json(raw)
    assert action.action_type == "draft_request"
    assert action.parameters["amount"] == 50000


def test_parse_action_with_chatter():
    raw = 'Sure, here is my decision: {"action_type": "wait", "parameters": {}}'
    action = parse_action_json(raw)
    assert action.action_type == "wait"


def test_parse_action_empty_raises():
    with pytest.raises(ValueError):
        parse_action_json("")


def test_parse_action_no_json_raises():
    with pytest.raises(ValueError):
        parse_action_json("I cannot decide right now.")


def test_parse_action_missing_action_type_raises():
    with pytest.raises(ValueError):
        parse_action_json('{"parameters": {}}')


# --- Agent generic behavior ------------------------------------------------

def test_agent_build_user_prompt_includes_observation_and_actions():
    agent = Agent(
        agent_id="tester",
        role="test",
        persona="test persona",
        available_actions=[
            ActionOption(name="noop", description="no operation", parameters_schema={}),
        ],
    )
    prompt = agent.build_user_prompt({"hello": "world"})
    assert "hello" in prompt
    assert "world" in prompt
    assert "noop" in prompt
    assert "no operation" in prompt
    assert "JSON" in prompt


def test_agent_decide_uses_fake_llm_and_returns_action():
    agent = Agent(
        agent_id="tester",
        role="test",
        persona="sys",
        available_actions=[ActionOption(name="wait", description="wait")],
    )
    fake = FakeLLM(['{"action_type": "wait", "parameters": {}}'])
    action = agent.decide(fake, observation={"x": 1}, temperature=0.5)
    assert isinstance(action, AgentAction)
    assert action.action_type == "wait"
    assert len(fake.calls) == 1
    assert fake.calls[0]["system"] == "sys"
    assert fake.calls[0]["temperature"] == 0.5


# --- buyer_a persona factory -----------------------------------------------

def test_make_agent_defaults():
    agent = make_agent()
    assert agent.agent_id == "buyer_a"
    assert agent.role == "buyer"
    assert agent.persona == BUYER_A_PERSONA
    assert agent.available_actions == BUYER_A_ACTIONS
    names = {a.name for a in agent.available_actions}
    assert names == {"draft_request", "place_order", "record_receipt", "wait"}


def test_buyer_a_decides_draft_request_with_fake_llm():
    agent = make_agent()
    fake = FakeLLM(
        [
            '{"action_type": "draft_request", "parameters": {"vendor": "V-ACME", "item": "ボルトM8", "amount": 80000}, "reasoning": "現場から急ぎ要望"}'
        ]
    )
    action = agent.decide(fake, observation={"current_day": 0, "remaining_capacity": 5})
    assert action.action_type == "draft_request"
    assert action.parameters["vendor"] == "V-ACME"
    assert action.parameters["amount"] == 80000
    assert "現場" in (action.reasoning or "")


# --- buyer_a observation builder ------------------------------------------

def test_build_observation_on_empty_state():
    state = EnvironmentState(current_day=0)
    obs = build_observation(state, agent_id="buyer_a")
    assert obs["agent_id"] == "buyer_a"
    assert obs["current_day"] == 0
    assert obs["remaining_capacity"] == 5  # default daily_capacity for buyer_a
    assert obs["approval_threshold"] == 1_000_000
    assert obs["my_requests"] == []
    assert obs["ready_to_order_request_ids"] == []
    assert obs["awaiting_receipt_orders"] == []


def test_build_observation_includes_only_own_requests():
    state = EnvironmentState(current_day=1)
    state.ensure_capacity_initialized()
    state.purchase_requests.append(
        PurchaseRequest(
            id="req-1",
            requester="buyer_a",
            vendor="V1",
            item="bolt",
            amount=50_000,
            created_day=0,
            status=RequestStatus.DRAFTED,
        )
    )
    state.purchase_requests.append(
        PurchaseRequest(
            id="req-2",
            requester="buyer_b",  # someone else's
            vendor="V2",
            item="nut",
            amount=70_000,
            created_day=0,
            status=RequestStatus.DRAFTED,
        )
    )
    obs = build_observation(state, agent_id="buyer_a")
    assert len(obs["my_requests"]) == 1
    assert obs["my_requests"][0]["id"] == "req-1"
    # under-threshold drafted request is orderable
    assert "req-1" in obs["ready_to_order_request_ids"]


def test_build_observation_ready_to_order_logic():
    """Regression test (PR#4 review fix): ready_to_order judgment.

    Verifies three cases after the boolean precedence fix:
      - DRAFTED under threshold        -> orderable
      - DRAFTED over threshold         -> NOT orderable (needs approval)
      - APPROVED regardless of amount  -> orderable
    """
    state = EnvironmentState(current_day=0)
    state.ensure_capacity_initialized()
    state.purchase_requests.extend(
        [
            PurchaseRequest(
                id="r-under", requester="buyer_a", vendor="V", item="x",
                amount=500_000, created_day=0, status=RequestStatus.DRAFTED,
            ),
            PurchaseRequest(
                id="r-over", requester="buyer_a", vendor="V", item="x",
                amount=2_000_000, created_day=0, status=RequestStatus.DRAFTED,
            ),
            PurchaseRequest(
                id="r-approved-big", requester="buyer_a", vendor="V", item="x",
                amount=5_000_000, created_day=0, status=RequestStatus.APPROVED,
            ),
        ]
    )
    obs = build_observation(state, agent_id="buyer_a")
    ready = set(obs["ready_to_order_request_ids"])
    assert "r-under" in ready
    assert "r-over" not in ready
    assert "r-approved-big" in ready
