"""Rule-based minimal (RB-min) agents for ablation experiments.

These agents share the :class:`oct.agent.Agent` interface but ignore the
LLM client entirely and instead derive their next action from the
observation dict via a small set of deterministic rules.

Design goals (see ``docs/09_ablation_plan.md`` §3 and §6):

* Minimize cleverness. The point is *not* to mimic an LLM, but to provide
  the simplest possible workflow-following baseline. Anything that requires
  ranking, scoring, or memory belongs in a higher level (RB-score, RB-memory).
* Preserve the action space. RB-min uses exactly the same action types as
  the LLM agents — no new actions, no truncated actions.
* Drop-in compatibility. ``PurchaseDispatcher`` and ``runner.run_simulation``
  must keep working unchanged. The only requirement is that ``decide()``
  returns an :class:`oct.agent.AgentAction`.

Conventions for "oldest first":

* For lists where the environment already produces a stable ordering
  (``ready_to_order_request_ids``, ``pending_approvals``, ``payable_orders``)
  RB-min picks index 0.
* For ``pending_demands`` we sort by ``(urgency_rank, generated_day)`` so
  high-urgency / older demands are picked first.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from oct.agent import ActionOption, Agent, AgentAction, LLMClient


_URGENCY_RANK: Dict[str, int] = {"high": 0, "normal": 1, "low": 2}


# ---------------------------------------------------------------------------
# Base class
# ---------------------------------------------------------------------------


class RBMinAgent(Agent):
    """Base class for rule-based minimal agents.

    Subclasses override :meth:`_choose_action` to encode their role's rules.
    The :meth:`decide` override deliberately ignores ``llm`` and
    ``temperature`` so that any caller (including the existing runner) can
    invoke the agent without an LLM client at all — the parameters are
    accepted only to keep the call signature compatible with
    :class:`oct.agent.Agent`.
    """

    def decide(  # type: ignore[override]
        self,
        llm: Optional[LLMClient] = None,
        observation: Optional[Dict[str, Any]] = None,
        temperature: float = 0.0,
    ) -> AgentAction:
        if observation is None:
            raise ValueError("RBMinAgent.decide requires an observation dict")
        return self._choose_action(observation)

    # Subclasses implement this.
    def _choose_action(self, observation: Dict[str, Any]) -> AgentAction:  # pragma: no cover - abstract
        raise NotImplementedError


def _wait(reason: str) -> AgentAction:
    return AgentAction(
        action_type="wait",
        parameters={},
        reasoning=f"RB-min: {reason}",
    )


# ---------------------------------------------------------------------------
# Buyer (buyer_a / buyer_b share the same logic)
# ---------------------------------------------------------------------------


class RBMinBuyerAgent(RBMinAgent):
    """Minimal rule-based buyer.

    Priority order:
      1. Record receipt for the oldest awaiting-receipt order.
      2. Place order for the oldest approved (ready-to-order) request.
      3. Draft a request for the highest-priority pending demand.
      4. Otherwise wait.
    """

    def _choose_action(self, observation: Dict[str, Any]) -> AgentAction:
        awaiting = observation.get("awaiting_receipt_orders") or []
        if awaiting:
            order = awaiting[0]
            return AgentAction(
                action_type="record_receipt",
                parameters={
                    "order_id": order["order_id"],
                    "delivered_amount": order["amount"],
                },
                reasoning="RB-min: receive oldest awaiting order",
            )

        ready = observation.get("ready_to_order_request_ids") or []
        if ready:
            return AgentAction(
                action_type="place_order",
                parameters={"request_id": ready[0]},
                reasoning="RB-min: place oldest approved request",
            )

        pending = observation.get("pending_demands") or []
        if pending:
            ranked = sorted(
                pending,
                key=lambda d: (
                    _URGENCY_RANK.get(d.get("urgency", "normal"), 1),
                    d.get("generated_day", 0),
                ),
            )
            demand = ranked[0]
            vendors = observation.get("available_vendors") or ["vendor_e"]
            vendor = vendors[0] if vendors else "vendor_e"
            amount_hint = demand.get("amount_hint", 0)
            try:
                amount = int(amount_hint)
            except (TypeError, ValueError):
                amount = 0
            return AgentAction(
                action_type="draft_request",
                parameters={
                    "vendor": vendor,
                    "item": demand.get("item", "unknown"),
                    "amount": amount,
                    "demand_id": demand.get("id"),
                },
                reasoning="RB-min: draft for highest-priority demand",
            )

        return _wait("nothing to do")


# ---------------------------------------------------------------------------
# Approver
# ---------------------------------------------------------------------------


class RBMinApproverAgent(RBMinAgent):
    """Minimal rule-based approver.

    Approves the oldest pending approval unconditionally. Never rejects.
    The point is to remove approver-side judgement entirely; any deviation
    observed in the simulation must therefore come from elsewhere.
    """

    def _choose_action(self, observation: Dict[str, Any]) -> AgentAction:
        pending = observation.get("pending_approvals") or []
        if pending:
            req = pending[0]
            return AgentAction(
                action_type="approve_request",
                parameters={
                    "request_id": req["id"],
                    "decision": "approved",
                    "note": "auto-approved by RB-min",
                },
                reasoning="RB-min: approve oldest pending request",
            )
        return _wait("no pending approvals")


# ---------------------------------------------------------------------------
# Accountant
# ---------------------------------------------------------------------------


class RBMinAccountantAgent(RBMinAgent):
    """Minimal rule-based accountant.

    Pays the oldest payable order at the order amount. Does not inspect
    three-way-match status — that is the dispatcher / rules' responsibility.
    """

    def _choose_action(self, observation: Dict[str, Any]) -> AgentAction:
        payable = observation.get("payable_orders") or []
        if payable:
            order = payable[0]
            amount = order.get("order_amount", order.get("amount", 0))
            return AgentAction(
                action_type="pay_order",
                parameters={
                    "order_id": order["order_id"],
                    "amount": amount,
                },
                reasoning="RB-min: pay oldest payable order",
            )
        return _wait("no payable orders")


# ---------------------------------------------------------------------------
# Vendor
# ---------------------------------------------------------------------------


class RBMinVendorAgent(RBMinAgent):
    """Minimal rule-based vendor.

    Priority order:
      1. Issue an invoice for the oldest delivered-but-not-invoiced order.
      2. Deliver the oldest undelivered order at the full ordered amount.
      3. Otherwise wait.

    Important: this vendor never "negotiates", "delays", or "splits". The
    LLM-vendor's freedom is exactly what we are *not* giving the RB-min
    baseline; if any deviation patterns survive in the RB-only run they
    cannot have come from vendor-side judgement.
    """

    @staticmethod
    def _is_delivered(order: Dict[str, Any]) -> bool:
        if order.get("delivered") is True:
            return True
        if order.get("delivered_amount") is not None:
            return True
        return False

    @staticmethod
    def _is_invoiced(order: Dict[str, Any]) -> bool:
        if order.get("invoiced") is True:
            return True
        if order.get("invoice_amount") is not None:
            return True
        return False

    def _choose_action(self, observation: Dict[str, Any]) -> AgentAction:
        my_orders: List[Dict[str, Any]] = observation.get("my_orders") or []

        # 1. delivered but not invoiced -> register_invoice
        # Some observation builders provide a pre-filtered list; respect it.
        delivered_not_invoiced = observation.get("delivered_not_invoiced")
        if delivered_not_invoiced:
            order = delivered_not_invoiced[0]
            return AgentAction(
                action_type="register_invoice",
                parameters={
                    "order_id": order["order_id"],
                    "amount": order.get("amount", order.get("order_amount", 0)),
                },
                reasoning="RB-min: invoice oldest delivered order",
            )
        for order in my_orders:
            if self._is_delivered(order) and not self._is_invoiced(order):
                return AgentAction(
                    action_type="register_invoice",
                    parameters={
                        "order_id": order["order_id"],
                        "amount": order.get("amount", order.get("order_amount", 0)),
                    },
                    reasoning="RB-min: invoice oldest delivered order",
                )

        # 2. undelivered -> deliver
        for order in my_orders:
            if not self._is_delivered(order):
                return AgentAction(
                    action_type="deliver",
                    parameters={
                        "order_id": order["order_id"],
                        "delivered_amount": order.get("amount", order.get("order_amount", 0)),
                    },
                    reasoning="RB-min: deliver oldest undelivered order",
                )

        return _wait("no orders to handle")


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def _empty_actions() -> List[ActionOption]:
    """RB-min agents do not consult `available_actions`; keep it empty."""
    return []


_RB_MIN_PERSONA = (
    "(rule-based-minimum policy; this persona is never sent to an LLM)"
)


def build_rb_min_agents() -> Dict[str, RBMinAgent]:
    """Construct the standard 5-agent RB-min cast for purchase ablation.

    The returned dict is keyed by ``agent_id`` so that callers can drop it
    straight into ``runner.run_simulation``.
    """
    return {
        "buyer_a": RBMinBuyerAgent(
            agent_id="buyer_a",
            role="buyer",
            persona=_RB_MIN_PERSONA,
            available_actions=_empty_actions(),
        ),
        "buyer_b": RBMinBuyerAgent(
            agent_id="buyer_b",
            role="buyer",
            persona=_RB_MIN_PERSONA,
            available_actions=_empty_actions(),
        ),
        "approver_c": RBMinApproverAgent(
            agent_id="approver_c",
            role="approver",
            persona=_RB_MIN_PERSONA,
            available_actions=_empty_actions(),
        ),
        "accountant_d": RBMinAccountantAgent(
            agent_id="accountant_d",
            role="accountant",
            persona=_RB_MIN_PERSONA,
            available_actions=_empty_actions(),
        ),
        "vendor_e": RBMinVendorAgent(
            agent_id="vendor_e",
            role="vendor",
            persona=_RB_MIN_PERSONA,
            available_actions=_empty_actions(),
        ),
    }
