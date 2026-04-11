"""Tests for the RB-min (rule-based minimum) ablation agents.

These tests cover:
  - Unit-level: each RBMin* agent picks the expected action for the
    relevant observation shapes (queue empty, queue non-empty, priority).
  - Integration: a 5-day end-to-end simulation with all five RB-min
    agents successfully drives a request from draft 竊・payment without
    invoking any LLM client.
"""

from __future__ import annotations

from typing import Any, Dict

import pytest

from oct.agent import AgentAction
from oct.agents.rb_min import (
    RBMinAccountantAgent,
    RBMinApproverAgent,
    RBMinBuyerAgent,
    RBMinVendorAgent,
    build_rb_min_agents,
)
from oct.dispatchers.purchase import PurchaseDispatcher
from oct.environment import EnvironmentState, RequestStatus
from oct.rules import DemandConfig
from oct.runner import run_simulation


# ---------------------------------------------------------------------------
# Helper: an LLM client that should never be called.
# ---------------------------------------------------------------------------


class _ForbiddenLLM:
    """LLM stub that fails the test if called.

    RB-min must not invoke any LLM, ever. Passing this client into
    ``run_simulation`` is the strongest possible enforcement.
    """

    def complete(self, system: str, user: str, temperature: float = 0.0) -> str:
        raise AssertionError("RB-min agent must not call the LLM client")


# ---------------------------------------------------------------------------
# Buyer
# ---------------------------------------------------------------------------


def _make_buyer() -> RBMinBuyerAgent:
    return RBMinBuyerAgent(
        agent_id="buyer_a",
        role="buyer",
        persona="rb-min-test",
        available_actions=[],
    )


def test_buyer_records_receipt_when_awaiting() -> None:
    obs: Dict[str, Any] = {
        "awaiting_receipt_orders": [
            {"order_id": "ord_00001", "amount": 1500, "request_id": "req_00001", "vendor": "vendor_e"},
            {"order_id": "ord_00002", "amount": 2200, "request_id": "req_00002", "vendor": "vendor_e"},
        ],
        "ready_to_order_request_ids": ["req_99999"],
        "pending_demands": [{"id": "dem_1", "urgency": "high", "generated_day": 0, "amount_hint": 1000, "item": "x"}],
        "available_vendors": ["vendor_e"],
    }
    action = _make_buyer().decide(None, obs)
    assert action.action_type == "record_receipt"
    assert action.parameters["order_id"] == "ord_00001"
    assert action.parameters["delivered_amount"] == 1500


def test_buyer_places_order_when_no_receipts_pending() -> None:
    obs: Dict[str, Any] = {
        "awaiting_receipt_orders": [],
        "ready_to_order_request_ids": ["req_00010", "req_00020"],
        "pending_demands": [{"id": "dem_1", "urgency": "high", "generated_day": 0, "amount_hint": 1000, "item": "x"}],
        "available_vendors": ["vendor_e"],
    }
    action = _make_buyer().decide(None, obs)
    assert action.action_type == "place_order"
    assert action.parameters["request_id"] == "req_00010"


def test_buyer_drafts_request_picking_high_urgency_then_oldest() -> None:
    obs: Dict[str, Any] = {
        "awaiting_receipt_orders": [],
        "ready_to_order_request_ids": [],
        "pending_demands": [
            {"id": "dem_low", "urgency": "low", "generated_day": 0, "amount_hint": 100, "item": "stationery"},
            {"id": "dem_high_old", "urgency": "high", "generated_day": 1, "amount_hint": 5_000_000, "item": "laptop"},
            {"id": "dem_high_new", "urgency": "high", "generated_day": 3, "amount_hint": 9_000_000, "item": "server"},
        ],
        "available_vendors": ["vendor_e"],
    }
    action = _make_buyer().decide(None, obs)
    assert action.action_type == "draft_request"
    assert action.parameters["demand_id"] == "dem_high_old"
    assert action.parameters["vendor"] == "vendor_e"
    assert action.parameters["item"] == "laptop"
    assert action.parameters["amount"] == 5_000_000


def test_buyer_waits_when_idle() -> None:
    obs: Dict[str, Any] = {
        "awaiting_receipt_orders": [],
        "ready_to_order_request_ids": [],
        "pending_demands": [],
        "available_vendors": ["vendor_e"],
    }
    action = _make_buyer().decide(None, obs)
    assert action.action_type == "wait"


# ---------------------------------------------------------------------------
# Approver
# ---------------------------------------------------------------------------


def _make_approver() -> RBMinApproverAgent:
    return RBMinApproverAgent(
        agent_id="approver_c",
        role="approver",
        persona="rb-min-test",
        available_actions=[],
    )


def test_approver_approves_oldest_pending_using_id_field() -> None:
    obs: Dict[str, Any] = {
        "pending_approvals": [
            {"id": "req_00001", "requester": "buyer_a", "amount": 1_200_000, "vendor": "vendor_e", "item": "x", "created_day": 0},
            {"id": "req_00002", "requester": "buyer_b", "amount": 800_000, "vendor": "vendor_e", "item": "y", "created_day": 1},
        ],
    }
    action = _make_approver().decide(None, obs)
    assert action.action_type == "approve_request"
    assert action.parameters["request_id"] == "req_00001"
    assert action.parameters["decision"] == "approved"


def test_approver_waits_when_no_pending() -> None:
    obs: Dict[str, Any] = {"pending_approvals": []}
    action = _make_approver().decide(None, obs)
    assert action.action_type == "wait"


# ---------------------------------------------------------------------------
# Accountant
# ---------------------------------------------------------------------------


def _make_accountant() -> RBMinAccountantAgent:
    return RBMinAccountantAgent(
        agent_id="accountant_d",
        role="accountant",
        persona="rb-min-test",
        available_actions=[],
    )


def test_accountant_pays_oldest_payable_with_order_amount() -> None:
    obs: Dict[str, Any] = {
        "payable_orders": [
            {
                "order_id": "ord_00001",
                "vendor": "vendor_e",
                "order_amount": 1_500_000,
                "invoice_amount": 1_500_000,
                "delivered_amount": 1_500_000,
                "has_receipt": True,
                "three_way_matched": True,
            },
            {
                "order_id": "ord_00002",
                "vendor": "vendor_e",
                "order_amount": 2_500_000,
                "invoice_amount": 2_500_000,
                "delivered_amount": 2_500_000,
                "has_receipt": True,
                "three_way_matched": True,
            },
        ],
    }
    action = _make_accountant().decide(None, obs)
    assert action.action_type == "pay_order"
    assert action.parameters["order_id"] == "ord_00001"
    assert action.parameters["amount"] == 1_500_000


def test_accountant_waits_when_no_payables() -> None:
    obs: Dict[str, Any] = {"payable_orders": []}
    action = _make_accountant().decide(None, obs)
    assert action.action_type == "wait"


# ---------------------------------------------------------------------------
# Vendor
# ---------------------------------------------------------------------------


def _make_vendor() -> RBMinVendorAgent:
    return RBMinVendorAgent(
        agent_id="vendor_e",
        role="vendor",
        persona="rb-min-test",
        available_actions=[],
    )


def test_vendor_invoices_delivered_but_not_invoiced() -> None:
    obs: Dict[str, Any] = {
        "my_orders": [
            {"order_id": "ord_00001", "amount": 1_000_000, "delivered": True, "delivered_amount": 1_000_000, "invoiced": False, "invoice_amount": None, "paid": False, "placed_day": 0},
            {"order_id": "ord_00002", "amount": 2_000_000, "delivered": False, "delivered_amount": None, "invoiced": False, "invoice_amount": None, "paid": False, "placed_day": 1},
        ],
    }
    action = _make_vendor().decide(None, obs)
    assert action.action_type == "register_invoice"
    assert action.parameters["order_id"] == "ord_00001"
    assert action.parameters["amount"] == 1_000_000


def test_vendor_delivers_oldest_undelivered_when_nothing_to_invoice() -> None:
    obs: Dict[str, Any] = {
        "my_orders": [
            {"order_id": "ord_00001", "amount": 500_000, "delivered": False, "delivered_amount": None, "invoiced": False, "invoice_amount": None, "paid": False, "placed_day": 0},
            {"order_id": "ord_00002", "amount": 700_000, "delivered": False, "delivered_amount": None, "invoiced": False, "invoice_amount": None, "paid": False, "placed_day": 1},
        ],
    }
    action = _make_vendor().decide(None, obs)
    assert action.action_type == "deliver"
    assert action.parameters["order_id"] == "ord_00001"
    assert action.parameters["delivered_amount"] == 500_000


def test_vendor_waits_when_no_orders_or_all_done() -> None:
    obs_empty: Dict[str, Any] = {"my_orders": []}
    assert _make_vendor().decide(None, obs_empty).action_type == "wait"

    obs_all_done: Dict[str, Any] = {
        "my_orders": [
            {"order_id": "ord_00001", "amount": 100, "delivered": True, "delivered_amount": 100, "invoiced": True, "invoice_amount": 100, "paid": True, "placed_day": 0},
        ],
    }
    assert _make_vendor().decide(None, obs_all_done).action_type == "wait"


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def test_build_rb_min_agents_returns_full_cast() -> None:
    agents = build_rb_min_agents()
    assert set(agents) == {"buyer_a", "buyer_b", "approver_c", "accountant_d", "vendor_e"}
    assert isinstance(agents["buyer_a"], RBMinBuyerAgent)
    assert isinstance(agents["buyer_b"], RBMinBuyerAgent)
    assert isinstance(agents["approver_c"], RBMinApproverAgent)
    assert isinstance(agents["accountant_d"], RBMinAccountantAgent)
    assert isinstance(agents["vendor_e"], RBMinVendorAgent)


# ---------------------------------------------------------------------------
# Integration: 5-day full simulation, no LLM
# ---------------------------------------------------------------------------


def test_rb_min_five_agent_simulation_runs_without_llm() -> None:
    """End-to-end smoke test.

    Runs a small (5-day, low-demand) simulation with only RB-min agents
    and an LLM client that raises if invoked. The test asserts:
      * the simulation completes without errors
      * the dispatcher records at least one action of each lifecycle stage
      * a non-zero number of payments is made
    """
    state = EnvironmentState(current_day=0)
    state.controls.approval_threshold = 200_000.0
    demand_config = DemandConfig(mean_daily_demands=2.0)
    dispatcher = PurchaseDispatcher(
        state,
        demand_config=demand_config,
        demand_rng_seed=42,
    )
    agents_dict = build_rb_min_agents()
    agents = [
        agents_dict["buyer_a"],
        agents_dict["buyer_b"],
        agents_dict["approver_c"],
        agents_dict["accountant_d"],
        agents_dict["vendor_e"],
    ]

    trace = run_simulation(
        env=dispatcher,
        agents=agents,
        llm=_ForbiddenLLM(),
        max_days=5,
        temperature=0.0,
        shuffle_agents=False,
        rng_seed=0,
        actions_per_agent_per_day=2,
    )

    assert trace.errors() == [], f"unexpected errors: {trace.errors()}"
    assert len(trace.dispatched_actions()) > 0

    # Some progress was made along the lifecycle
    assert len(state.purchase_requests) > 0, "buyers should draft at least one request"
    assert len(state.approvals) > 0, "approver should approve at least one request"
    assert len(state.orders) > 0, "buyer should place at least one order"
    assert len(state.receipts) > 0, "vendor should deliver at least one order"
    assert len(state.invoices) > 0, "vendor should invoice at least one delivered order"
    assert len(state.payments) > 0, "accountant should pay at least one matched order"


def test_rb_min_simulation_completes_with_demand_seed_variation() -> None:
    """Different demand seeds should still complete cleanly (no crashes)."""
    for seed in (0, 7, 99):
        state = EnvironmentState(current_day=0)
        state.controls.approval_threshold = 200_000.0
        dispatcher = PurchaseDispatcher(
            state,
            demand_config=DemandConfig(mean_daily_demands=1.5),
            demand_rng_seed=seed,
        )
        agents_dict = build_rb_min_agents()
        agents = list(agents_dict.values())
        trace = run_simulation(
            env=dispatcher,
            agents=agents,
            llm=_ForbiddenLLM(),
            max_days=4,
            temperature=0.0,
            shuffle_agents=True,
            rng_seed=seed,
            actions_per_agent_per_day=2,
        )
        assert trace.errors() == [], f"errors at seed={seed}: {trace.errors()}"
