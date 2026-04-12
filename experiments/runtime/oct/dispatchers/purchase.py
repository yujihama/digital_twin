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
#
# NOTE (T-023): vendor_e is intentionally *not* in this registry because it
# takes an additional ``narrative_mode`` kwarg. Dispatching to it happens
# directly in :meth:`PurchaseDispatcher.observe` so non-vendor builders
# don't need a pass-through kwarg they would ignore.
_OBSERVATION_BUILDERS = {
    "buyer_a": build_buyer_a_observation,
    "buyer_b": build_buyer_b_observation,
    "approver_c": build_approver_c_observation,
    "accountant_d": build_accountant_d_observation,
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
        narrative_mode: bool = False,
        ambiguity_enabled: bool = False,
        ambiguity_rng_seed: Optional[int] = None,
        ambiguity_branch: str = "all",
    ) -> None:
        self.state = state
        self.state.ensure_capacity_initialized()
        self.demand_config = demand_config
        self.isolated_mode = isolated_mode
        # T-023 — when True, vendor_e's observation block includes a
        # natural-language rendering of its business_context. Other agents
        # are unaffected (the flag is only read in the vendor_e branch of
        # observe()).
        self.narrative_mode = narrative_mode
        self._demand_rng = random.Random(demand_rng_seed) if demand_config else None

        # T-028 — interpretive ambiguity injection. When enabled we seed a
        # dedicated rng (derived from the cell's master seed when not given
        # explicitly) and attach it to the state via PrivateAttr so
        # rules.place_order() can reach it without threading extra kwargs
        # through every action handler. Using a separate rng (not the
        # demand rng) means toggling ambiguity does NOT perturb the demand
        # stream, so Phase A / Phase B stays comparable to the T-021b
        # baseline run for the same seed.
        self.ambiguity_enabled = ambiguity_enabled
        self.state.controls.ambiguity_enabled = ambiguity_enabled
        # T-028c — branch attribution. Validation lives in
        # rules._generate_order_ambiguity (raised on the first PO) so we
        # don't need to import the constant here. The default "all" keeps
        # backward compatibility with PR #27 / T-028 Phase A.
        self.ambiguity_branch = ambiguity_branch
        self.state.controls.ambiguity_branch = ambiguity_branch
        if ambiguity_enabled:
            if ambiguity_rng_seed is None:
                # Derive from demand_rng_seed deterministically. The XOR
                # salt (0xA28B) is arbitrary but fixed, and the fallback
                # keeps reproducibility when no demand_rng_seed was given.
                base = demand_rng_seed if demand_rng_seed is not None else 0
                ambiguity_rng_seed = base ^ 0xA28B
            self.state._ambiguity_rng = random.Random(ambiguity_rng_seed)
        else:
            self.state._ambiguity_rng = None

        # Seed day-0 demands so buyers have something to act on immediately
        if self.demand_config is not None and self._demand_rng is not None:
            generate_demands(self.state, self.demand_config, self._demand_rng)

    # ---- EnvironmentAdapter Protocol ---------------------------------------

    def observe(self, agent_id: str) -> Dict[str, Any]:
        if agent_id == "vendor_e":
            # vendor_e takes an extra kwarg (T-023). Keep it out of the
            # generic builder registry so non-vendor builders don't need
            # a pass-through they would ignore.
            obs = build_vendor_e_observation(
                self.state, agent_id, narrative_mode=self.narrative_mode
            )
        else:
            builder = _OBSERVATION_BUILDERS.get(agent_id)
            if builder is None:
                raise KeyError(
                    f"No observation builder registered for agent_id={agent_id!r}"
                )
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


# T-022 — strategic vendor actions. These are deliberately distinct from
# `deliver` / `register_invoice` (which accept an arbitrary amount anyway) so
# that the vendor's *intent* is legible in the trace. They also fix the
# deviation direction so the ablation measures a clean treatment effect:
#
#   deliver_partial       — delivers strictly *less* than PO (GR < PO)
#   invoice_with_markup   — invoices strictly *more* than PO (Inv > PO)
#   delay_delivery        — defers delivery to a later day (trace-legible wait)
#
# Both `fraction` and `markup_ratio` are optional; defaults are chosen so that
# three-way-match fails with the default `three_way_match_tolerance = 0`.


def _handle_deliver_partial(
    state: EnvironmentState, agent_id: str, params: Dict[str, Any]
) -> Dict[str, Any]:
    """Deliver goods at a fraction of the ordered amount.

    The caller may specify ``fraction`` in [0, 1]; defaults to 0.8 (i.e. a
    20% shortfall which always breaks three-way match under tolerance 0).
    """
    order_id = str(params["order_id"])
    order = state.get_order(order_id)
    if order is None:
        raise TransitionError(f"Order {order_id} not found")
    try:
        fraction = float(params.get("fraction", 0.8))
    except (TypeError, ValueError):
        fraction = 0.8
    fraction = max(0.0, min(1.0, fraction))
    delivered = int(round(order.amount * fraction))
    receipt = record_receipt(
        state,
        buyer=agent_id,
        order_id=order_id,
        delivered_amount=delivered,
    )
    return {
        "receipt_id": receipt.id,
        "delivered_amount": receipt.delivered_amount,
        "fraction": fraction,
        "po_amount": order.amount,
    }


def _handle_invoice_with_markup(
    state: EnvironmentState, agent_id: str, params: Dict[str, Any]
) -> Dict[str, Any]:
    """Issue an invoice at (1 + markup_ratio) x PO.

    ``markup_ratio`` defaults to 0.10 (a 10% markup, which breaks three-way
    match under tolerance 0). Negative values are clamped to 0 because the
    semantic of this action is "strictly higher than PO".
    """
    order_id = str(params["order_id"])
    order = state.get_order(order_id)
    if order is None:
        raise TransitionError(f"Order {order_id} not found")
    try:
        markup_ratio = float(params.get("markup_ratio", 0.10))
    except (TypeError, ValueError):
        markup_ratio = 0.10
    markup_ratio = max(0.0, markup_ratio)
    amount = int(round(order.amount * (1.0 + markup_ratio)))
    invoice = register_invoice(
        state,
        order_id=order_id,
        amount=amount,
    )
    return {
        "invoice_id": invoice.id,
        "amount": invoice.amount,
        "markup_ratio": markup_ratio,
        "po_amount": order.amount,
    }


def _handle_delay_delivery(
    state: EnvironmentState, agent_id: str, params: Dict[str, Any]
) -> Dict[str, Any]:
    """No-op action that is legible in the trace as a deferral.

    Does not consume capacity (same as ``wait``) so that the vendor can still
    choose other actions on the same day. The point is to give the vendor a
    *named* way to decline delivery today without the choice being erased as
    a plain ``wait``.
    """
    order_id = str(params.get("order_id", ""))
    return {"action": "delay_delivery", "order_id": order_id}


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
    "deliver_partial": _handle_deliver_partial,
    "register_invoice": _handle_register_invoice,
    "invoice_with_markup": _handle_invoice_with_markup,
    "delay_delivery": _handle_delay_delivery,
    "pay_order": _handle_pay_order,
    "wait": _handle_wait,
}
