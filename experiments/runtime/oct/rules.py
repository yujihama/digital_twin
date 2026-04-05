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
from typing import List, Optional

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

    # Sample count from Poisson (manual: sum of exponential inter-arrivals)
    n = 0
    limit = rng.expovariate(1.0)
    total = 0.0
    while total < config.mean_daily_demands:
        total += limit
        limit = rng.expovariate(1.0)
        n += 1
    # n is now Poisson-distributed with mean ≈ config.mean_daily_demands
    # (using the standard exponential-sum algorithm)
    # Actually, let's use a cleaner approach:
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
    """Place an order for an approved request (or an under-threshold draft)."""
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
    order = Order(
        id=state.next_id("ord"),
        request_id=request_id,
        vendor=req.vendor,
        amount=req.amount,
        placed_day=state.current_day,
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
    """Check PO / GR / Invoice alignment within configured tolerance."""
    order = state.get_order(order_id)
    receipt = state.receipt_for(order_id)
    invoice = state.invoice_for(order_id)
    if order is None or receipt is None or invoice is None:
        return False
    tol = state.controls.three_way_match_tolerance
    return (
        abs(order.amount - invoice.amount) <= tol
        and abs(order.amount - receipt.delivered_amount) <= tol
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
