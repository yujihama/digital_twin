"""Tests for generic simulation runner and purchase dispatcher.

All tests run without real API calls — a ScriptedLLM returns canned JSON
responses to drive the loop deterministically.
"""
from __future__ import annotations

from typing import List

import pytest

from oct.dispatchers.purchase import PurchaseDispatcher
from oct.environment import EnvironmentState, RequestStatus
from oct.personas.buyer_a import make_agent
from oct.runner import StepRecord, run_simulation


class ScriptedLLM:
    """Returns canned responses in order. Raises on exhaustion."""

    def __init__(self, responses: List[str]) -> None:
        self._responses = list(responses)
        self.calls = 0

    def complete(self, system: str, user: str, temperature: float = 0.8) -> str:
        self.calls += 1
        if not self._responses:
            raise RuntimeError("ScriptedLLM exhausted")
        return self._responses.pop(0)


# --- PurchaseDispatcher ----------------------------------------------------

def test_dispatcher_snapshot_on_empty_state():
    state = EnvironmentState(current_day=0)
    env = PurchaseDispatcher(state)
    snap = env.snapshot()
    assert snap["current_day"] == 0
    assert snap["counts"]["purchase_requests"] == 0


def test_dispatcher_observe_buyer_a():
    env = PurchaseDispatcher(EnvironmentState(current_day=2))
    obs = env.observe("buyer_a")
    assert obs["agent_id"] == "buyer_a"
    assert obs["remaining_capacity"] == 5


def test_dispatcher_observe_unknown_agent_raises():
    env = PurchaseDispatcher(EnvironmentState(current_day=0))
    with pytest.raises(KeyError):
        env.observe("buyer_x_not_registered")


def test_dispatcher_dispatch_draft_request_ok():
    env = PurchaseDispatcher(EnvironmentState(current_day=0))
    agent = make_agent()
    action = agent.available_actions  # just to reference the schema exists
    assert action  # sanity
    # Build AgentAction via model validation
    from oct.agent import AgentAction
    result = env.dispatch(
        "buyer_a",
        AgentAction(
            action_type="draft_request",
            parameters={"vendor": "V1", "item": "bolt", "amount": 50000},
        ),
    )
    assert result["ok"] is True
    assert "request_id" in result["details"]
    assert env.state.purchase_requests[0].amount == 50000


def test_dispatcher_dispatch_unknown_action_type():
    from oct.agent import AgentAction
    env = PurchaseDispatcher(EnvironmentState(current_day=0))
    result = env.dispatch("buyer_a", AgentAction(action_type="nonexistent"))
    assert result["ok"] is False
    assert "unknown action_type" in result["error"]


def test_dispatcher_dispatch_bad_parameters():
    from oct.agent import AgentAction
    env = PurchaseDispatcher(EnvironmentState(current_day=0))
    result = env.dispatch(
        "buyer_a",
        AgentAction(action_type="draft_request", parameters={"vendor": "V1"}),  # missing item/amount
    )
    assert result["ok"] is False
    assert "bad_parameters" in result["error"]


def test_dispatcher_dispatch_transition_error_surfaces():
    """Draft-then-place should fail if capacity is exhausted."""
    from oct.agent import AgentAction
    state = EnvironmentState(current_day=0)
    env = PurchaseDispatcher(state)
    # Exhaust buyer_a capacity
    state.remaining_capacity["buyer_a"] = 0
    result = env.dispatch(
        "buyer_a",
        AgentAction(
            action_type="draft_request",
            parameters={"vendor": "V1", "item": "x", "amount": 10000},
        ),
    )
    assert result["ok"] is False
    assert "transition_error" in result["error"]


def test_dispatcher_wait_is_noop():
    from oct.agent import AgentAction
    state = EnvironmentState(current_day=0)
    env = PurchaseDispatcher(state)
    cap_before = state.remaining_capacity["buyer_a"]
    result = env.dispatch("buyer_a", AgentAction(action_type="wait"))
    assert result["ok"] is True
    # wait does not consume capacity
    assert state.remaining_capacity["buyer_a"] == cap_before


def test_dispatcher_advance_day_resets_capacity():
    state = EnvironmentState(current_day=0)
    env = PurchaseDispatcher(state)
    state.remaining_capacity["buyer_a"] = 2
    env.advance_day()
    assert state.current_day == 1
    assert state.remaining_capacity["buyer_a"] == 5


# --- run_simulation end-to-end --------------------------------------------

def test_run_simulation_happy_path_5_days():
    """buyer_a drafts a request, orders it, records receipt, then waits."""
    responses = [
        '{"action_type": "draft_request", "parameters": {"vendor": "V1", "item": "bolt", "amount": 50000}, "reasoning": "need bolts"}',
        '{"action_type": "place_order", "parameters": {"request_id": "req_00001"}, "reasoning": "auto approved"}',
        '{"action_type": "record_receipt", "parameters": {"order_id": "ord_00001", "delivered_amount": 50000}, "reasoning": "arrived"}',
        '{"action_type": "wait", "parameters": {}}',
        '{"action_type": "wait", "parameters": {}}',
    ]
    state = EnvironmentState(current_day=0)
    env = PurchaseDispatcher(state)
    agent = make_agent()
    llm = ScriptedLLM(responses)

    trace = run_simulation(env=env, agents=[agent], llm=llm, max_days=5, temperature=0.8)

    assert len(trace.steps) == 5
    assert len(trace.dispatched_actions()) == 5
    assert len(trace.errors()) == 0
    assert state.current_day == 5
    assert len(state.purchase_requests) == 1
    assert state.purchase_requests[0].status == RequestStatus.RECEIVED
    assert len(state.orders) == 1
    assert len(state.receipts) == 1
    assert llm.calls == 5
    # Snapshot recorded
    assert trace.final_snapshot is not None
    assert trace.final_snapshot["current_day"] == 5


def test_run_simulation_records_errors_and_continues():
    """Unknown action_type should be logged but not abort the run."""
    responses = [
        '{"action_type": "nonsense_action", "parameters": {}}',
        '{"action_type": "wait", "parameters": {}}',
    ]
    state = EnvironmentState(current_day=0)
    env = PurchaseDispatcher(state)
    agent = make_agent()
    llm = ScriptedLLM(responses)

    trace = run_simulation(env=env, agents=[agent], llm=llm, max_days=2)
    assert len(trace.steps) == 2
    # First step: action parsed fine, but dispatch returned ok=False
    step0: StepRecord = trace.steps[0]
    assert step0.action is not None
    assert step0.error is None  # decide succeeded
    assert step0.dispatch_result["ok"] is False
    # Second step: wait is ok
    assert trace.steps[1].dispatch_result["ok"] is True


def test_run_simulation_handles_invalid_llm_json():
    """Non-JSON LLM output should be captured as decide_failed."""
    responses = ["I'm sorry, I cannot comply.", '{"action_type": "wait"}']
    state = EnvironmentState(current_day=0)
    env = PurchaseDispatcher(state)
    agent = make_agent()
    llm = ScriptedLLM(responses)

    trace = run_simulation(env=env, agents=[agent], llm=llm, max_days=2)
    assert trace.steps[0].error is not None
    assert "decide_failed" in trace.steps[0].error
    assert trace.steps[0].action is None
    assert trace.steps[1].error is None


def test_run_simulation_skips_agent_without_capacity():
    """If remaining_capacity is 0 at day start, agent is not asked."""
    state = EnvironmentState(current_day=0)
    env = PurchaseDispatcher(state)
    state.remaining_capacity["buyer_a"] = 0
    agent = make_agent()
    llm = ScriptedLLM([])  # will raise if called

    trace = run_simulation(env=env, agents=[agent], llm=llm, max_days=1)
    assert trace.steps == []
    assert llm.calls == 0
    # But day still advances
    assert state.current_day == 1
