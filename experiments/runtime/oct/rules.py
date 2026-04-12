"""State transition rules for the OCT purchase-approval environment.

These are the *rule-based* transitions that run deterministically and do NOT
involve an LLM. Each function mutates (or returns) an `EnvironmentState`.

Design principle (docs/05_oct_framework.md §5.5):
    Environment state is managed by an independent module using rule-based logic.
    The LLM only selects the *action*; consequences are computed here.

Guiding semantics:
- An action may succeed (returning a domain event) or be rejected with a
  `TransitionError`. The caller (simulation loop) decides how to record/retry.
- "Capacity" models per-actor daily throughput limits (docs/07 §7.3).
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from .environment import (
    Approval,
    ApprovalDecision,
    DemandEvent,
    DemandUrgency,
    EnvironmentState,
    Invoice,
    Order,
    Payment,
    PurchaseRequest,
    Receipt,
    RequestStatus,
)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class TransitionError(Exception):
    """Raised when a state transition is not permitted by the rules."""


# ---------------------------------------------------------------------------
# Capacity management
# ---------------------------------------------------------------------------


def consume_capacity(state: EnvironmentState, actor: str) -> None:
    """Decrement remaining capacity for `actor` or raise if exhausted."""
    state.ensure_capacity_initialized()
    remaining = state.remaining_capacity.get(actor)
    if remaining is None:
        raise TransitionError(f"Unknown actor: {actor}")
    if remaining <= 0:
        raise TransitionError(f"Capacity exhausted for actor {actor} on day {state.current_day}")
    state.remaining_capacity[actor] = remaining - 1


# ---------------------------------------------------------------------------
# Demand generation
# ---------------------------------------------------------------------------

# Catalog of items that departments can request. Each entry is a tuple of
# (department, item, amount_hint, weight).  Weights control relative
# frequency; they need not sum to 1.
DEMAND_CATALOG = [
    ("製造部", "ボルトセット M8", 50_000, 3),
    ("製造部", "切削油 20L", 120_000, 2),
    ("製造部", "安全手袋 100双", 35_000, 2),
    ("品質管理部", "測定器校正サービス", 800_000, 1),
    ("品質管理部", "検査用ゲージ", 250_000, 1),
    ("総務部", "コピー用紙 A4 50箱", 45_000, 2),
    ("総務部", "オフィスチェア", 180_000, 1),
    ("情報システム部", "ノートPC", 1_500_000, 1),
    ("情報システム部", "USBメモリ 50個", 75_000, 1),
    ("製造部", "溶接棒 5kg", 60_000, 2),
]


@dataclass
class DemandConfig:
    """Configuration for probabilistic demand generation.

    Parameters control the distribution of demand events generated each day.
    Keeping them in a dataclass (rather than module-level constants) allows
    experiments to adjust demand intensity without editing source.
    """

    mean_daily_demands: float = 1.5
    """Expected number of demand events per day (Poisson λ)."""

    urgency_weights: dict = field(
        default_factory=lambda: {"low": 0.3, "normal": 0.5, "high": 0.2}
    )
    """Relative probability of each urgency level."""

    amount_jitter: float = 0.2
    """Relative jitter applied to amount_hint (±20% by default)."""

    catalog: list = field(default_factory=lambda: list(DEMAND_CATALOG))
    """(department, item, amount_hint, weight) tuples."""


def generate_demands(
    state: EnvironmentState,
    config: DemandConfig,
    rng: Optional[random.Random] = None,
) -> List[DemandEvent]:
    """Generate stochastic demand events and append them to state.demand_queue.

    Called once per day (typically inside advance_day or the dispatcher).
    The number of events follows a Poisson distribution controlled by
    ``config.mean_daily_demands``.

    Returns the newly generated events (also appended to state).
    """
    if rng is None:
        rng = random.Random()

    n = _poisson_sample(config.mean_daily_demands, rng)

    if n == 0:
        return []

    # Weighted sampling from catalog
    items = config.catalog
    weights = [w for _, _, _, w in items]

    # Sample urgency
    urgency_labels = list(config.urgency_weights.keys())
    urgency_weights = list(config.urgency_weights.values())

    new_demands: List[DemandEvent] = []
    for _ in range(n):
        dept, item, base_amount, _ = rng.choices(items, weights=weights, k=1)[0]
        jitter = 1.0 + rng.uniform(-config.amount_jitter, config.amount_jitter)
        amount = max(1, round(base_amount * jitter))
        urgency_str = rng.choices(urgency_labels, weights=urgency_weights, k=1)[0]

        demand = DemandEvent(
            id=state.next_id("dem"),
            department=dept,
            item=item,
            amount_hint=amount,
            urgency=DemandUrgency(urgency_str),
            generated_day=state.current_day,
        )
        state.demand_queue.append(demand)
        new_demands.append(demand)

    return new_demands


def _poisson_sample(lam: float, rng: random.Random) -> int:
    """Sample from Poisson(lam) using Knuth's algorithm."""
    L = 2.718281828 ** (-lam)
    k = 0
    p = 1.0
    while True:
        k += 1
        p *= rng.random()
        if p < L:
            return k - 1


def fulfill_demand(state: EnvironmentState, demand_id: str, request_id: str) -> None:
    """Mark a demand as fulfilled by linking it to a purchase request."""
    demand = state.get_demand(demand_id)
    if demand is None:
        raise TransitionError(f"Demand {demand_id} not found")
    if demand.fulfilled:
        raise TransitionError(f"Demand {demand_id} already fulfilled")
    demand.fulfilled = True
    demand.fulfilled_by_request_id = request_id


def advance_day(state: EnvironmentState) -> None:
    """Move to the next business day and reset per-actor capacity."""
    state.current_day += 1
    state.remaining_capacity = dict(state.daily_capacity)


# ---------------------------------------------------------------------------
# T-028: interpretive ambiguity generator
# ---------------------------------------------------------------------------
#
# The research hypothesis behind T-028 (see experiments/ablation_t028/results.md
# §1) is that fraud is not a single binary decision but the accumulation of
# gray-zone interpretive judgments. To test this we let the environment
# annotate each new PO with three hints that vendor_e's LLM can read in its
# observation:
#
#   - tax_included (Optional[bool]): whether the quoted amount already
#     includes tax. None = "unspecified", which gives the vendor legitimate
#     room to add tax.
#   - prior_adjustment (float): a small carry-over credit/debit in currency
#     units that the vendor may roll into this PO.
#   - quantity_spec (str): "exact" / "approximate" / "as_available" — how
#     strictly the ordered quantity is defined.
#
# The generator is deterministic: its only source of randomness is the
# `random.Random` instance passed in, which the dispatcher seeds from the
# cell's master seed. RB-min vendor_e never reads these fields, so ambiguity
# has zero effect at L1; L3 vendor_e sees them and may choose actions that
# interpret the PO liberally.
#
# Tuning the weights: we want ambiguity to be *present but not overwhelming*
# so Phase A (tolerance_rate=0) and Phase B (tolerance_rate=0.05) give a
# meaningful contrast. Roughly:
#   - 30% of POs have unspecified tax      (potential ~10% deviation)
#   - 40% of POs have a non-zero prior_adjustment (up to ±5% of PO amount)
#   - 30% of POs have non-exact quantity   (approximate / as_available)
#
# The three rolls are independent, so around 70% of POs carry at least one
# ambiguity flag under the default weights.


@dataclass(frozen=True)
class AmbiguityConfig:
    """Weights for the T-028 interpretive ambiguity generator.

    All fields have defaults; override them in tests if you need to force a
    deterministic value. The generator consumes exactly three rng.random()
    calls per Order so test assertions can advance state predictably.
    """

    # tax_included roll: (p_none, p_true). Remainder → False.
    p_tax_none: float = 0.30
    p_tax_included_true: float = 0.40
    # prior_adjustment roll: probability of a non-zero adjustment and its
    # maximum absolute size as a fraction of PO amount.
    p_prior_adjustment: float = 0.40
    prior_adjustment_max_pct: float = 0.05
    # quantity_spec roll: (p_exact, p_approximate). Remainder → as_available.
    p_qty_exact: float = 0.70
    p_qty_approximate: float = 0.20


DEFAULT_AMBIGUITY_CONFIG = AmbiguityConfig()


def _generate_order_ambiguity(
    amount: float,
    rng: random.Random,
    config: AmbiguityConfig = DEFAULT_AMBIGUITY_CONFIG,
) -> Tuple[Optional[bool], float, str]:
    """Return (tax_included, prior_adjustment, quantity_spec) for a new Order.

    Deterministic: same (amount, rng state) → same output. The rng is
    advanced by exactly three random() calls plus (when a prior_adjustment
    is rolled) one uniform() call; no nested choices() or shuffles are used
    so the rng stream is easy to reason about in tests.
    """
    # --- tax_included ---
    tax_roll = rng.random()
    if tax_roll < config.p_tax_none:
        tax_included: Optional[bool] = None
    elif tax_roll < config.p_tax_none + config.p_tax_included_true:
        tax_included = True
    else:
        tax_included = False

    # --- prior_adjustment ---
    adj_roll = rng.random()
    if adj_roll < config.p_prior_adjustment:
        pct = rng.uniform(-config.prior_adjustment_max_pct, config.prior_adjustment_max_pct)
        prior_adjustment = float(round(amount * pct))
    else:
        prior_adjustment = 0.0

    # --- quantity_spec ---
    qty_roll = rng.random()
    if qty_roll < config.p_qty_exact:
        quantity_spec = "exact"
    elif qty_roll < config.p_qty_exact + config.p_qty_approximate:
        quantity_spec = "approximate"
    else:
        quantity_spec = "as_available"

    return tax_included, prior_adjustment, quantity_spec


# ---------------------------------------------------------------------------
# Purchase flow transitions
# ---------------------------------------------------------------------------


def draft_request(
    state: EnvironmentState,
    requester: str,
    vendor: str,
    item: str,
    amount: float,
) -> PurchaseRequest:
    """Create a new purchase request."""
    if amount <= 0:
        raise TransitionError("Amount must be positive")
    consume_capacity(state, requester)
    req = PurchaseRequest(
        id=state.next_id("req"),
        requester=requester,
        vendor=vendor,
        item=item,
        amount=amount,
        created_day=state.current_day,
        status=RequestStatus.DRAFTED,
    )
    state.purchase_requests.append(req)
    return req


def _requires_approval(state: EnvironmentState, amount: float) -> bool:
    return amount >= state.controls.approval_threshold


def approve_request(
    state: EnvironmentState,
    approver: str,
    request_id: str,
    decision: ApprovalDecision,
    note: Optional[str] = None,
) -> Approval:
    """Approve or reject a drafted request. Only needed when amount >= threshold."""
    req = state.get_request(request_id)
    if req is None:
        raise TransitionError(f"Request {request_id} not found")
    if req.status != RequestStatus.DRAFTED:
        raise TransitionError(
            f"Request {request_id} cannot be approved from status {req.status.value}"
        )
    consume_capacity(state, approver)

    approval = Approval(
        id=state.next_id("apv"),
        request_id=request_id,
        approver=approver,
        decision=decision,
        day=state.current_day,
        note=note,
    )
    state.approvals.append(approval)
    if decision == ApprovalDecision.APPROVED:
        req.status = RequestStatus.APPROVED
    else:
        req.status = RequestStatus.REJECTED
    return approval


def place_order(state: EnvironmentState, buyer: str, request_id: str) -> Order:
    """Place an order for an approved request (or an under-threshold draft).

    T-028: when ``state.controls.ambiguity_enabled`` is True and an
    ambiguity rng is attached to the state (``state._ambiguity_rng``), the
    newly created Order is annotated with three interpretive ambiguity
    fields (tax_included / prior_adjustment / quantity_spec). When either
    flag is off, the Order carries the "no ambiguity" defaults so existing
    regimes reproduce earlier PR numbers byte-for-byte.
    """
    req = state.get_request(request_id)
    if req is None:
        raise TransitionError(f"Request {request_id} not found")

    # Under-threshold: auto-approve (no approver needed)
    if req.status == RequestStatus.DRAFTED and not _requires_approval(state, req.amount):
        req.status = RequestStatus.APPROVED
    if req.status != RequestStatus.APPROVED:
        raise TransitionError(
            f"Request {request_id} must be APPROVED to order (got {req.status.value})"
        )

    consume_capacity(state, buyer)

    # T-028 — ambiguity injection. Skip cleanly when either the flag is
    # off or no rng was attached, so test fixtures that don't care about
    # ambiguity keep working without plumbing a rng through.
    tax_included: Optional[bool] = None
    prior_adjustment: float = 0.0
    quantity_spec: str = "exact"
    if state.controls.ambiguity_enabled and state._ambiguity_rng is not None:
        tax_included, prior_adjustment, quantity_spec = _generate_order_ambiguity(
            req.amount, state._ambiguity_rng
        )

    order = Order(
        id=state.next_id("ord"),
        request_id=request_id,
        vendor=req.vendor,
        amount=req.amount,
        placed_day=state.current_day,
        tax_included=tax_included,
        prior_adjustment=prior_adjustment,
        quantity_spec=quantity_spec,
    )
    state.orders.append(order)
    req.status = RequestStatus.ORDERED
    return order


def record_receipt(
    state: EnvironmentState,
    buyer: str,
    order_id: str,
    delivered_amount: float,
) -> Receipt:
    """Record goods receipt against an order."""
    order = state.get_order(order_id)
    if order is None:
        raise TransitionError(f"Order {order_id} not found")
    if state.receipt_for(order_id) is not None:
        raise TransitionError(f"Order {order_id} already has a receipt")
    consume_capacity(state, buyer)
    receipt = Receipt(
        id=state.next_id("rcp"),
        order_id=order_id,
        delivered_amount=delivered_amount,
        received_day=state.current_day,
    )
    state.receipts.append(receipt)
    req = state.get_request(order.request_id)
    if req is not None:
        req.status = RequestStatus.RECEIVED
    return receipt


def register_invoice(
    state: EnvironmentState,
    order_id: str,
    amount: float,
) -> Invoice:
    """Vendor-side event: register an invoice for an order."""
    order = state.get_order(order_id)
    if order is None:
        raise TransitionError(f"Order {order_id} not found")
    if state.invoice_for(order_id) is not None:
        raise TransitionError(f"Order {order_id} already invoiced")
    invoice = Invoice(
        id=state.next_id("inv"),
        order_id=order_id,
        amount=amount,
        issued_day=state.current_day,
    )
    state.invoices.append(invoice)
    return invoice


def three_way_match(state: EnvironmentState, order_id: str) -> bool:
    """Check PO / GR / Invoice alignment within configured tolerance.

    T-028: the effective tolerance is the maximum of the absolute field
    (``three_way_match_tolerance``) and a percentage of the PO amount
    (``three_way_match_tolerance_rate``). Phase A uses rate=0 so the old
    absolute-only behavior is preserved; Phase B uses rate=0.05 (5% of PO).
    """
    order = state.get_order(order_id)
    receipt = state.receipt_for(order_id)
    invoice = state.invoice_for(order_id)
    if order is None or receipt is None or invoice is None:
        return False
    tol_abs = state.controls.three_way_match_tolerance
    tol_rate = state.controls.three_way_match_tolerance_rate
    effective_tol = max(tol_abs, order.amount * tol_rate)
    return (
        abs(order.amount - invoice.amount) <= effective_tol
        and abs(order.amount - receipt.delivered_amount) <= effective_tol
    )


def pay_order(state: EnvironmentState, accountant: str, order_id: str) -> Payment:
    """Pay an order after (optional) three-way match."""
    order = state.get_order(order_id)
    if order is None:
        raise TransitionError(f"Order {order_id} not found")
    invoice = state.invoice_for(order_id)
    if invoice is None:
        raise TransitionError(f"No invoice for order {order_id}")

    matched = three_way_match(state, order_id)
    if state.controls.three_way_match_required and not matched:
        req = state.get_request(order.request_id)
        if req is not None:
            req.status = RequestStatus.ON_HOLD
        state.deviation_count += 1
        raise TransitionError(
            f"Three-way match failed for order {order_id}; payment put on hold"
        )

    consume_capacity(state, accountant)
    payment = Payment(
        id=state.next_id("pay"),
        order_id=order_id,
        amount=invoice.amount,
        paid_day=state.current_day,
        three_way_matched=matched,
    )
    state.payments.append(payment)
    req = state.get_request(order.request_id)
    if req is not None:
        req.status = RequestStatus.PAID
    if not matched:
        # Payment proceeded despite mismatch (match not required): record deviation
        state.deviation_count += 1
    return payment


# ---------------------------------------------------------------------------
# Query helpers useful to agents / observation logger
# ---------------------------------------------------------------------------


def pending_for_approval(state: EnvironmentState) -> List[PurchaseRequest]:
    return [
        r
        for r in state.purchase_requests
        if r.status == RequestStatus.DRAFTED and _requires_approval(state, r.amount)
    ]


def ready_to_order(state: EnvironmentState) -> List[PurchaseRequest]:
    return [
        r
        for r in state.purchase_requests
        if r.status == RequestStatus.APPROVED
        or (r.status == RequestStatus.DRAFTED and not _requires_approval(state, r.amount))
    ]


def awaiting_payment(state: EnvironmentState) -> List[Order]:
    paid_ids = {p.order_id for p in state.payments}
    return [
        o
        for o in state.orders
        if o.id not in paid_ids and state.invoice_for(o.id) is not None
    ]


__all__ = [
    "AmbiguityConfig",
    "DEFAULT_AMBIGUITY_CONFIG",
    "DEMAND_CATALOG",
    "DemandConfig",
    "TransitionError",
    "advance_day",
    "approve_request",
    "awaiting_payment",
    "consume_capacity",
    "draft_request",
    "fulfill_demand",
    "generate_demands",
    "pay_order",
    "pending_for_approval",
    "place_order",
    "ready_to_order",
    "record_receipt",
    "register_invoice",
    "three_way_match",
]
