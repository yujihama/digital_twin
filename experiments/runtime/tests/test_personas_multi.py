"""Tests for the additional personas (buyer_b / approver_c / accountant_d /
vendor_e) and their integration via PurchaseDispatcher.

Focus areas:
  - each persona module's build_observation works
  - dispatcher routes approve_request / deliver correctly
  - multi-agent end-to-end happy path produces a fully-paid order
"""
from __future__ import annotations

import json
from typing import List

from oct.agent import Agent
from oct.dispatchers.purchase import PurchaseDispatcher
from oct.environment import ApprovalDecision, EnvironmentState, RequestStatus
from oct.personas.accountant_d import (
    build_observation as obs_accountant_d,
    make_agent as make_accountant_d,
)
from oct.personas.approver_c import (
    build_observation as obs_approver_c,
    make_agent as make_approver_c,
)
from oct.personas.buyer_a import make_agent as make_buyer_a
from oct.personas.buyer_b import (
    build_observation as obs_buyer_b,
    make_agent as make_buyer_b,
)
from oct.personas.vendor_e import (
    build_observation as obs_vendor_e,
    make_agent as make_vendor_e,
)
from oct.rules import draft_request, place_order
from oct.runner import run_simulation


class ScriptedLLM:
    """Emits pre-canned JSON responses in order."""

    def __init__(self, responses: List[str]) -> None:
        self._responses = list(responses)
        self.calls = 0

    def complete(self, system: str, user: str, temperature: float = 0.8) -> str:
        if self.calls >= len(self._responses):
            return '{"action_type": "wait", "parameters": {}}'
        resp = self._responses[self.calls]
        self.calls += 1
        return resp


# --- make_agent factories --------------------------------------------------


def test_make_agent_for_each_persona():
    a = make_buyer_a()
    b = make_buyer_b()
    c = make_approver_c()
    d = make_accountant_d()
    e = make_vendor_e()
    for agent, aid, role in [
        (a, "buyer_a", "buyer"),
        (b, "buyer_b", "buyer"),
        (c, "approver_c", "approver"),
        (d, "accountant_d", "accountant"),
        (e, "vendor_e", "vendor"),
    ]:
        assert isinstance(agent, Agent)
        assert agent.agent_id == aid
        assert agent.role == role
        assert len(agent.available_actions) >= 2


# --- observation builders --------------------------------------------------


def test_buyer_b_observation_exposes_peer_activity():
    state = EnvironmentState(current_day=0)
    draft_request(state, requester="buyer_a", vendor="V1", item="bolt", amount=50000)
    draft_request(state, requester="buyer_b", vendor="V2", item="nut", amount=30000)
    obs = obs_buyer_b(state, "buyer_b")
    assert obs["agent_id"] == "buyer_b"
    assert len(obs["my_requests"]) == 1
    assert obs["my_requests"][0]["item"] == "nut"
    assert len(obs["peer_recent_requests"]) == 1
    assert obs["peer_recent_requests"][0]["requester"] == "buyer_a"


def test_approver_c_observation_surfaces_pending_over_threshold():
    state = EnvironmentState(current_day=0)
    # Under threshold — should NOT appear
    draft_request(state, requester="buyer_a", vendor="V1", item="bolt", amount=50000)
    # Over threshold — should appear
    draft_request(
        state, requester="buyer_a", vendor="V1", item="machine", amount=2_000_000
    )
    obs = obs_approver_c(state, "approver_c")
    assert obs["agent_id"] == "approver_c"
    assert len(obs["pending_approvals"]) == 1
    assert obs["pending_approvals"][0]["amount"] == 2_000_000
    assert obs["approval_threshold"] == 1_000_000


def test_accountant_d_observation_shows_payable_orders():
    state = EnvironmentState(current_day=0)
    req = draft_request(
        state, requester="buyer_a", vendor="vendor_e", item="bolt", amount=50000
    )
    order = place_order(state, buyer="buyer_a", request_id=req.id)
    # Without invoice: should NOT appear in payable
    obs = obs_accountant_d(state, "accountant_d")
    assert obs["payable_orders"] == []
    # Add receipt + invoice
    from oct.rules import record_receipt, register_invoice
    record_receipt(state, buyer="buyer_a", order_id=order.id, delivered_amount=50000)
    register_invoice(state, order_id=order.id, amount=50000)
    obs = obs_accountant_d(state, "accountant_d")
    assert len(obs["payable_orders"]) == 1
    assert obs["payable_orders"][0]["three_way_matched"] is True


def test_vendor_e_observation_scoped_to_own_orders():
    state = EnvironmentState(current_day=0)
    # Order to vendor_e
    req1 = draft_request(
        state, requester="buyer_a", vendor="vendor_e", item="bolt", amount=50000
    )
    place_order(state, buyer="buyer_a", request_id=req1.id)
    # Order to a different vendor — vendor_e should NOT see it
    req2 = draft_request(
        state, requester="buyer_a", vendor="OTHER_VENDOR", item="nut", amount=30000
    )
    place_order(state, buyer="buyer_a", request_id=req2.id)
    obs = obs_vendor_e(state, "vendor_e")
    assert obs["agent_id"] == "vendor_e"
    assert len(obs["my_orders"]) == 1
    assert obs["my_orders"][0]["amount"] == 50000
    assert obs["my_orders"][0]["delivered"] is False


# --- dispatcher: new handlers ----------------------------------------------


def test_dispatcher_routes_approve_request():
    state = EnvironmentState(current_day=0)
    env = PurchaseDispatcher(state)
    # over-threshold drafted request
    draft_request(
        state, requester="buyer_a", vendor="V1", item="machine", amount=2_000_000
    )
    from oct.agent import AgentAction

    action = AgentAction(
        action_type="approve_request",
        parameters={"request_id": "req_00001", "decision": "approved", "note": "OK"},
    )
    result = env.dispatch("approver_c", action)
    assert result["ok"] is True
    assert result["details"]["decision"] == "approved"
    assert state.purchase_requests[0].status == RequestStatus.APPROVED


def test_dispatcher_rejects_invalid_decision():
    state = EnvironmentState(current_day=0)
    env = PurchaseDispatcher(state)
    draft_request(
        state, requester="buyer_a", vendor="V1", item="machine", amount=2_000_000
    )
    from oct.agent import AgentAction

    action = AgentAction(
        action_type="approve_request",
        parameters={"request_id": "req_00001", "decision": "maybe"},
    )
    result = env.dispatch("approver_c", action)
    assert result["ok"] is False
    assert "invalid decision" in result["error"]


def test_dispatcher_routes_deliver_for_vendor_e():
    state = EnvironmentState(current_day=0)
    env = PurchaseDispatcher(state)
    req = draft_request(
        state, requester="buyer_a", vendor="vendor_e", item="bolt", amount=50000
    )
    place_order(state, buyer="buyer_a", request_id=req.id)
    from oct.agent import AgentAction

    action = AgentAction(
        action_type="deliver",
        parameters={"order_id": "ord_00001", "delivered_amount": 50000},
    )
    result = env.dispatch("vendor_e", action)
    assert result["ok"] is True
    assert state.receipts[0].delivered_amount == 50000


# --- runner: shuffling & wait_ends_turn ------------------------------------


def test_shuffle_agents_is_deterministic_with_seed():
    """Same seed → same per-day ordering; different seeds → different order."""
    state = EnvironmentState(current_day=0)
    env = PurchaseDispatcher(state)
    agents = [make_buyer_a(), make_buyer_b(), make_approver_c()]
    llm1 = ScriptedLLM(['{"action_type": "wait", "parameters": {}}'] * 30)
    llm2 = ScriptedLLM(['{"action_type": "wait", "parameters": {}}'] * 30)

    trace1 = run_simulation(
        env=PurchaseDispatcher(EnvironmentState(current_day=0)),
        agents=agents, llm=llm1, max_days=3, rng_seed=42,
    )
    trace2 = run_simulation(
        env=PurchaseDispatcher(EnvironmentState(current_day=0)),
        agents=agents, llm=llm2, max_days=3, rng_seed=42,
    )
    order1 = [s.agent_id for s in trace1.steps]
    order2 = [s.agent_id for s in trace2.steps]
    assert order1 == order2

    llm3 = ScriptedLLM(['{"action_type": "wait", "parameters": {}}'] * 30)
    trace3 = run_simulation(
        env=PurchaseDispatcher(EnvironmentState(current_day=0)),
        agents=agents, llm=llm3, max_days=3, rng_seed=999,
    )
    order3 = [s.agent_id for s in trace3.steps]
    # Over 3 days × 3 agents, a different seed is extremely likely to yield
    # at least one different ordering
    assert order1 != order3


def test_shuffle_disabled_preserves_input_order():
    state = EnvironmentState(current_day=0)
    env = PurchaseDispatcher(state)
    agents = [make_buyer_a(), make_buyer_b(), make_approver_c()]
    llm = ScriptedLLM(['{"action_type": "wait", "parameters": {}}'] * 30)
    trace = run_simulation(
        env=env, agents=agents, llm=llm, max_days=2, shuffle_agents=False,
    )
    # With wait_ends_turn=True (default) and actions_per_agent_per_day=1,
    # each agent gets exactly 1 step per day
    day0 = [s.agent_id for s in trace.steps if s.day == 0]
    assert day0 == ["buyer_a", "buyer_b", "approver_c"]


def test_wait_ends_turn_when_multiple_actions_allowed():
    """With actions_per_agent_per_day=3, a wait on turn 1 should stop the
    inner loop so the agent doesn't spin through wait×3 in one day."""
    state = EnvironmentState(current_day=0)
    env = PurchaseDispatcher(state)
    llm = ScriptedLLM(['{"action_type": "wait", "parameters": {}}'] * 10)
    trace = run_simulation(
        env=env,
        agents=[make_buyer_a()],
        llm=llm,
        max_days=2,
        actions_per_agent_per_day=3,
        wait_ends_turn=True,
        shuffle_agents=False,
    )
    # 2 days × 1 agent × 1 step each (wait ends turn) = 2 steps total
    assert len(trace.steps) == 2


def test_wait_ends_turn_disabled_allows_multiple_waits():
    state = EnvironmentState(current_day=0)
    env = PurchaseDispatcher(state)
    llm = ScriptedLLM(['{"action_type": "wait", "parameters": {}}'] * 10)
    trace = run_simulation(
        env=env,
        agents=[make_buyer_a()],
        llm=llm,
        max_days=1,
        actions_per_agent_per_day=3,
        wait_ends_turn=False,
        shuffle_agents=False,
    )
    # wait doesn't consume capacity and doesn't end turn → 3 waits in day 0
    assert len(trace.steps) == 3


# --- end-to-end: all 5 agents cooperating to pay an order ------------------


def test_full_flow_all_five_agents_end_to_end():
    """Happy path: buyer_a drafts → approver_c approves → buyer_a orders
    → vendor_e delivers → vendor_e invoices → accountant_d pays."""
    responses = [
        # Day 0
        '{"action_type": "draft_request", "parameters": {"vendor": "vendor_e", "item": "machine", "amount": 2000000}}',
        '{"action_type": "approve_request", "parameters": {"request_id": "req_00001", "decision": "approved", "note": "ok"}}',
        '{"action_type": "place_order", "parameters": {"request_id": "req_00001"}}',
        '{"action_type": "deliver", "parameters": {"order_id": "ord_00001", "delivered_amount": 2000000}}',
        '{"action_type": "register_invoice", "parameters": {"order_id": "ord_00001", "amount": 2000000}}',
        '{"action_type": "pay_order", "parameters": {"order_id": "ord_00001"}}',
    ]
    # Agents ordered to match the response script exactly
    agents = [
        make_buyer_a(),
        make_approver_c(),
        make_buyer_a(),  # second turn (different instance same id) — use one agent w/ more actions
    ]
    # Simpler: use one of each and actions_per_agent_per_day=2 so buyer_a
    # can draft then order on day 0. But ordering won't cooperate. Use a
    # scripted LLM with explicit day-by-day responses instead.

    # Day 0: buyer_a drafts (turn1) + approver_c approves (turn1)
    # Day 1: buyer_a orders, vendor_e delivers, vendor_e invoices
    # Day 2: accountant_d pays
    responses = [
        # Day 0 (no-shuffle order: buyer_a, buyer_b, approver_c, accountant_d, vendor_e)
        '{"action_type": "draft_request", "parameters": {"vendor": "vendor_e", "item": "machine", "amount": 2000000}}',  # buyer_a
        '{"action_type": "wait", "parameters": {}}',  # buyer_b
        '{"action_type": "approve_request", "parameters": {"request_id": "req_00001", "decision": "approved"}}',  # approver_c
        '{"action_type": "wait", "parameters": {}}',  # accountant_d
        '{"action_type": "wait", "parameters": {}}',  # vendor_e
        # Day 1
        '{"action_type": "place_order", "parameters": {"request_id": "req_00001"}}',  # buyer_a
        '{"action_type": "wait", "parameters": {}}',  # buyer_b
        '{"action_type": "wait", "parameters": {}}',  # approver_c
        '{"action_type": "wait", "parameters": {}}',  # accountant_d
        '{"action_type": "deliver", "parameters": {"order_id": "ord_00001", "delivered_amount": 2000000}}',  # vendor_e
        # Day 2
        '{"action_type": "wait", "parameters": {}}',  # buyer_a
        '{"action_type": "wait", "parameters": {}}',  # buyer_b
        '{"action_type": "wait", "parameters": {}}',  # approver_c
        '{"action_type": "wait", "parameters": {}}',  # accountant_d
        '{"action_type": "register_invoice", "parameters": {"order_id": "ord_00001", "amount": 2000000}}',  # vendor_e
        # Day 3
        '{"action_type": "wait", "parameters": {}}',  # buyer_a
        '{"action_type": "wait", "parameters": {}}',  # buyer_b
        '{"action_type": "wait", "parameters": {}}',  # approver_c
        '{"action_type": "pay_order", "parameters": {"order_id": "ord_00001"}}',  # accountant_d
        '{"action_type": "wait", "parameters": {}}',  # vendor_e
    ]
    state = EnvironmentState(current_day=0)
    env = PurchaseDispatcher(state)
    agents = [
        make_buyer_a(),
        make_buyer_b(),
        make_approver_c(),
        make_accountant_d(),
        make_vendor_e(),
    ]
    llm = ScriptedLLM(responses)
    trace = run_simulation(
        env=env,
        agents=agents,
        llm=llm,
        max_days=4,
        shuffle_agents=False,  # need deterministic order to match scripted responses
    )

    # Verify end state: order is paid
    assert len(state.purchase_requests) == 1
    assert state.purchase_requests[0].status == RequestStatus.PAID
    assert len(state.approvals) == 1
    assert state.approvals[0].decision


# --- T-017: reject_request handler -----------------------------------------


def test_dispatcher_routes_reject_request():
    """reject_request action_type should be handled as approve_request with
    decision=rejected, fixing the silent-failure bug (T-017)."""
    state = EnvironmentState(current_day=0)
    env = PurchaseDispatcher(state)
    # Create an over-threshold drafted request
    draft_request(
        state, requester="buyer_a", vendor="V1", item="machine", amount=2_000_000
    )
    from oct.agent import AgentAction

    action = AgentAction(
        action_type="reject_request",
        parameters={"request_id": "req_00001", "note": "too expensive"},
    )
    result = env.dispatch("approver_c", action)
    assert result["ok"] is True
    assert result["details"]["decision"] == "rejected"
    assert state.purchase_requests[0].status == RequestStatus.REJECTED


def test_reject_request_in_simulation_flow():
    """End-to-end: approver_c emits reject_request during simulation and
    the request is properly rejected (not silently dropped)."""
    responses = [
        # Day 0
        '{"action_type": "draft_request", "parameters": {"vendor": "vendor_e", "item": "machine", "amount": 2000000}}',  # buyer_a
        '{"action_type": "wait", "parameters": {}}',  # buyer_b
        '{"action_type": "reject_request", "parameters": {"request_id": "req_00001", "note": "budget exceeded"}}',  # approver_c
        '{"action_type": "wait", "parameters": {}}',  # accountant_d
        '{"action_type": "wait", "parameters": {}}',  # vendor_e
    ]
    state = EnvironmentState(current_day=0)
    env = PurchaseDispatcher(state)
    agents = [
        make_buyer_a(),
        make_buyer_b(),
        make_approver_c(),
        make_accountant_d(),
        make_vendor_e(),
    ]
    llm = ScriptedLLM(responses)
    trace = run_simulation(
        env=env, agents=agents, llm=llm, max_days=1, shuffle_agents=False,
    )
    assert state.purchase_requests[0].status == RequestStatus.REJECTED
    assert state.approvals[0].decision == ApprovalDecision.REJECTED
    assert len(trace.errors()) == 0


def test_approver_c_has_reject_request_action():
    """approver_c action schema should include reject_request (T-017)."""
    agent = make_approver_c()
    action_names = [a.name for a in agent.available_actions]
    assert "reject_request" in action_names
    assert "approve_request" in action_names


# --- T-015: buyer_a awaiting_receipt symmetry fix ---------------------------


def test_buyer_a_awaiting_receipt_filters_own_orders_only():
    """buyer_a should only see awaiting_receipt for orders originating from
    their own purchase requests, not orders from buyer_b (T-015)."""
    from oct.personas.buyer_a import build_observation as obs_buyer_a

    state = EnvironmentState(current_day=0)
    # buyer_a creates and orders a request
    req_a = draft_request(
        state, requester="buyer_a", vendor="vendor_e", item="bolt", amount=50000
    )
    order_a = place_order(state, buyer="buyer_a", request_id=req_a.id)
    # buyer_b creates and orders a request
    req_b = draft_request(
        state, requester="buyer_b", vendor="vendor_e", item="nut", amount=30000
    )
    order_b = place_order(state, buyer="buyer_b", request_id=req_b.id)

    obs_a = obs_buyer_a(state, "buyer_a")
    # buyer_a should only see their own order
    assert len(obs_a["awaiting_receipt_orders"]) == 1
    assert obs_a["awaiting_receipt_orders"][0]["order_id"] == order_a.id

    # buyer_b observation should also only see their own order (existing behavior)
    obs_b = obs_buyer_b(state, "buyer_b")
    assert len(obs_b["awaiting_receipt_orders"]) == 1
    assert obs_b["awaiting_receipt_orders"][0]["order_id"] == order_b.id 
