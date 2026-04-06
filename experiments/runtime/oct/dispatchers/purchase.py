"""Purchase-approval EnvironmentAdapter — domain-specific glue for the runner.

Wraps `EnvironmentState` + `oct.rules` transition functions + buyer_a
observation builder so the generic `oct.runner.run_simulation` can operate
on the purchase-approval environment without knowing any domain details.
"""
from __future__ import annotations

import random
from typing import Any, Dict, List, Optional

from oct.agent import AgentAction
from oct.environment import ApprovalDecision, DemandEvent, EnvironmentState
from oct.personas.accountant_d import build_observation as build_accountant_d_observation
from oct.personas.approver_c import build_observation as build_approver_c_observation
from oct.personas.buyer_a import build_observation as build_buyer_a_observation
from oct.personas.buyer_b import build_observation as build_buyer_b_observation
from oct.personas.vendor_e import build_observation as build_vendor_e_observation
from oct.rules import (
    DemandConfig,
    TransitionError,
    advance_day,
    approve_request,
    draft_request,
    fulfill_demand,
    generate_demands,
    pay_order,
    place_order,
    record_receipt,
    register_invoice,
)


# Observation builder registry: agent_id -> callable(state, agent_id) -> dict
_OBSERVATION_BUILDERS = {
    "buyer_a": build_buyer_a_observation,
    "buyer_b": build_buyer_b_observation,
    "approver_c": build_approver_c_observation,
    "accountant_d": build_accountant_d_observation,
    "vendor_e": build_vendor_e_observation,
}


class PurchaseDispatcher:
    """Implements `oct.runner.EnvironmentAdapter` for the purchase flow.

    Action routing table (action_type -> rules.py function):
      - draft_request   -> rules.draft_request
      - place_order     -> rules.place_order
      - record_receipt  -> rules.record_receipt
      - register_invoice -> rules.register_invoice
      - pay_order       -> rules.pay_order
      - wait            -> no-op

    Demand generation:
      When ``demand_config`` is provided, ``advance_day()`` generates
      stochastic demand events each day. This is the Option A+C mechanism
      identified in exp001: the environment provides internal needs as state,
      and the LLM decides how to act on them.
    """

    def __init__(
        self,
        state: EnvironmentState,
        demand_config: Optional[DemandConfig] = None,
        demand_rng_seed: Optional[int] = None,
        isolated_mode: bool = False,
    ) -> None:
        self.state = state
        self.state.ensure_capacity_initialized()
        self.demand_config = demand_config
        self.isolated_mode = isolated_mode
        self._demand_rng = random.Random(demand_rng_seed) if demand_config else None
        # Seed day-0 demands so buyers have something to act on immediately
        if self.demand_config is not None and self._demand_rng is not None:
            generate_demands(self.state, self.demand_config, self._demand_rng)

    # ---- EnvironmentAdapter Protocol ---------------------------------------

    def observe(self, agent_id: str) -> Dict[str, Any]:
        builder = _OBSERVATION_BUILDERS.get(agent_id)
        if builder is None:
            raise KeyError(f"No observation builder registered for agent_id={agent_id!r}")
        obs = builder(self.state, agent_id)
        if self.isolated_mode:
            obs = self._apply_isolation(agent_id, obs)
        return obs

    def _apply_isolation(self, agent_id: str, obs: Dict[str, Any]) -> Dict[str, Any]:
        """Remove cross-agent information for isolated mode.

        This implements the Layer 3 interaction-blocking test from docs/06.
        Each agent loses visibility into other agents' behavior patterns,
        while retaining access to the shared state needed for basic workflow
        progression (e.g., approver_c still sees pending_approvals so the
        flow doesn't deadlock, but loses feedback from recent_approvals).
        """
        obs = dict(obs)  # shallow copy to avoid mutating original
        if agent_id == "buyer_b":
            # Remove peer (buyer_a) recent request patterns -- blocks imitation
            obs["peer_recent_requests"] = []
        if agent_id == "approver_c":
            # Remove own approval history feedback -- blocks pattern learning
            obs["recent_approvals"] = []
        if agent_id == "vendor_e":
            # Remove payment receipt history -- blocks payment timing learning
            obs["recent_payments_received"] = []
        if agent_id == "accountant_d":
            # Fix deviation count to 0 -- blocks cumulative deviation awareness
            obs["deviation_count"] = 0
        return obs

    def dispatch(self, agent_id: str, action: AgentAction) -> Dict[str, Any]:
        handler = _ACTION_HANDLERS.get(action.action_type)
        if handler is None:
            return {
                "ok": False,
                "details": {},
                "error": f"unknown action_type: {action.action_type!r}",
            }
        try:
            details = handler(self.state, agent_id, action.parameters)
        except TransitionError as exc:
            return {"ok": False, "details": {}, "error": f"transition_error: {exc}"}
        except (TypeError, KeyError, ValueError) as exc:
            return {"ok": False, "details": {}, "error": f"bad_parameters: {exc}"}
        return {"ok": True, "details": details, "error": None}

    def remaining_capacity(self, agent_id: str) -> int:
        return self.state.remaining_capacity.get(agent_id, 0)

    def advance_day(self) -> None:
        advance_day(self.state)
        # Generate new demand events for the new day (if configured)
        if self.demand_config is not None and self._demand_rng is not None:
            generate_demands(self.state, self.demand_config, self._demand_rng)

    def snapshot(self) -> Dict[str, Any]:
        pending = [d for d in self.state.demand_queue if not d.fulfilled]
        fulfilled = [d for d in self.state.demand_queue if d.fulfilled]
        return {
            "current_day": self.state.current_day,
            "deviation_count": self.state.deviation_count,
            "error_count": self.state.error_count,
            "counts": {
                "purchase_requests": len(self.state.purchase_requests),
                "approvals": len(self.state.approvals),
                "orders": len(self.state.orders),
                "receipts": len(self.state.receipts),
                "invoices": len(self.state.invoices),
                "payments": len(self.state.payments),
                "demands_total": len(self.state.demand_queue),
                "demands_pending": len(pending),
                "demands_fulfilled": len(fulfilled),
            },
        }


# ---- Action handlers -------------------------------------------------------

def _handle_draft_request(
    state: EnvironmentState, agent_id: str, params: Dict[str, Any]
) -> Dict[str, Any]:
    req = draft_request(
        state,
        requester=agent_id,
        vendor=str(params["vendor"]),
        item=str(params["item"]),
        amount=int(params["amount"]),
    )
    # If a demand_id was specified, mark the demand as fulfilled
    demand_id = params.get("demand_id")
    if demand_id:
        try:
            fulfill_demand(state, str(demand_id), req.id)
        except TransitionError:
            pass  # Non-fatal: demand link is optional
    return {"request_id": req.id, "status": req.status.value}


def _handle_place_order(
    state: EnvironmentState, agent_id: str, params: Dict[str, Any]
) -> Dict[str, Any]:
    order = place_order(state, buyer=agent_id, request_id=str(params["request_id"]))
    return {"order_id": order.id, "amount": order.amount}


def _handle_record_receipt(
    state: EnvironmentState, agent_id: str, params: Dict[str, Any]
) -> Dict[str, Any]:
    receipt = record_receipt(
        state,
        buyer=agent_id,
        order_id=str(params["order_id"]),
        delivered_amount=int(params["delivered_amount"]),
    )
    return {"receipt_id": receipt.id, "delivered_amount": receipt.delivered_amount}


def _handle_register_invoice(
    state: EnvironmentState, agent_id: str, params: Dict[str, Any]
) -> Dict[str, Any]:
    invoice = register_invoice(
        state,
        order_id=str(params["order_id"]),
        amount=int(params["amount"]),
    )
    return {"invoice_id": invoice.id, "amount": invoice.amount}


def _handle_pay_order(
    state: EnvironmentState, agent_id: str, params: Dict[str, Any]
) -> Dict[str, Any]:
    payment = pay_order(state, accountant=agent_id, order_id=str(params["order_id"]))
    return {
        "payment_id": payment.id,
        "amount": payment.amount,
        "three_way_matched": payment.three_way_matched,
    }


def _handle_approve_request(
    state: EnvironmentState, agent_id: str, params: Dict[str, Any]
) -> Dict[str, Any]:
    decision_raw = str(params["decision"]).lower()
    try:
        decision = ApprovalDecision(decision_raw)
    except ValueError as exc:
        raise ValueError(
            f"invalid decision {decision_raw!r}; expected 'approved' or 'rejected'"
        ) from exc
    approval = approve_request(
        state,
        approver=agent_id,
        request_id=str(params["request_id"]),
        decision=decision,
        note=params.get("note"),
    )
    return {
        "approval_id": approval.id,
        "decision": approval.decision.value,
        "request_id": approval.request_id,
    }


def _handle_deliver(
    state: EnvironmentState, agent_id: str, params: Dict[str, Any]
) -> Dict[str, Any]:
    """vendor_e-side alias for record_receipt."""
    receipt = record_receipt(
        state,
        buyer=agent_id,
        order_id=str(params["order_id"]),
        delivered_amount=int(params["delivered_amount"]),
    )
    return {"receipt_id": receipt.id, "delivered_amount": receipt.delivered_amount}


def _handle_reject_request(
    state: EnvironmentState, agent_id: str, params: Dict[str, Any]
) -> Dict[str, Any]:
    """Alias: approver_c may emit reject_request instead of approve_request
    with decision=rejected. Internally delegates to _handle_approve_request
    with decision forced to 'rejected'.
    """
    params = dict(params)  # shallow copy to avoid mutating caller's dict
    params["decision"] = "rejected"
    return _handle_approve_request(state, agent_id, params)


def _handle_wait(
    state: EnvironmentState, agent_id: str, params: Dict[str, Any]
) -> Dict[str, Any]:
    # wait consumes no capacity -- intentional no-op
    return {"action": "wait"}


_ACTION_HANDLERS = {
    "draft_request": _handle_draft_request,
    "approve_request": _handle_approve_request,
    "reject_request": _handle_reject_request,
    "place_order": _handle_place_order,
    "record_receipt": _handle_record_receipt,
    "deliver": _handle_deliver,
    "register_invoice": _handle_register_invoice,
    "pay_order": _handle_pay_order,
    "wait": _handle_wait,
}
