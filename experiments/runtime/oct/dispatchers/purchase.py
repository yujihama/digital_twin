"""Purchase-approval EnvironmentAdapter — domain-specific glue for the runner.

Wraps `EnvironmentState` + `oct.rules` transition functions + buyer_a
observation builder so the generic `oct.runner.run_simulation` can operate
on the purchase-approval environment without knowing any domain details.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from oct.agent import AgentAction
from oct.environment import ApprovalDecision, EnvironmentState
from oct.personas.accountant_d import build_observation as build_accountant_d_observation
from oct.personas.approver_c import build_observation as build_approver_c_observation
from oct.personas.buyer_a import build_observation as build_buyer_a_observation
from oct.personas.buyer_b import build_observation as build_buyer_b_observation
from oct.personas.vendor_e import build_observation as build_vendor_e_observation
from oct.rules import (
    TransitionError,
    advance_day,
    approve_request,
    draft_request,
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
    """

    def __init__(self, state: EnvironmentState) -> None:
        self.state = state
        self.state.ensure_capacity_initialized()

    # ---- EnvironmentAdapter Protocol ---------------------------------------

    def observe(self, agent_id: str) -> Dict[str, Any]:
        builder = _OBSERVATION_BUILDERS.get(agent_id)
        if builder is None:
            raise KeyError(f"No observation builder registered for agent_id={agent_id!r}")
        return builder(self.state, agent_id)

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

    def snapshot(self) -> Dict[str, Any]:
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
    """vendor_e-side alias for record_receipt.

    A delivery event from the vendor's perspective is the same physical
    event as a receipt from the buyer's perspective. We reuse the
    `record_receipt` transition but attribute capacity consumption to
    the vendor.
    """
    receipt = record_receipt(
        state,
        buyer=agent_id,  # charge capacity to the actor taking the action
        order_id=str(params["order_id"]),
        delivered_amount=int(params["delivered_amount"]),
    )
    return {"receipt_id": receipt.id, "delivered_amount": receipt.delivered_amount}


def _handle_wait(
    state: EnvironmentState, agent_id: str, params: Dict[str, Any]
) -> Dict[str, Any]:
    # wait consumes no capacity — intentional no-op
    return {"action": "wait"}


_ACTION_HANDLERS = {
    "draft_request": _handle_draft_request,
    "approve_request": _handle_approve_request,
    "place_order": _handle_place_order,
    "record_receipt": _handle_record_receipt,
    "deliver": _handle_deliver,
    "register_invoice": _handle_register_invoice,
    "pay_order": _handle_pay_order,
    "wait": _handle_wait,
}
