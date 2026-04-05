"""Unit tests for the state-transition rules."""

from __future__ import annotations

import pytest

from oct.environment import (
    ApprovalDecision,
    EnvironmentState,
    RequestStatus,
)
from oct.rules import (
    TransitionError,
    advance_day,
    approve_request,
    awaiting_payment,
    consume_capacity,
    draft_request,
    pay_order,
    pending_for_approval,
    place_order,
    ready_to_order,
    record_receipt,
    register_invoice,
    three_way_match,
)


# ---------------------------------------------------------------------------
# Capacity
# ---------------------------------------------------------------------------


def test_consume_capacity_decrements_then_raises() -> None:
    state = EnvironmentState(daily_capacity={"buyer_a": 2})
    consume_capacity(state, "buyer_a")
    consume_capacity(state, "buyer_a")
    assert state.remaining_capacity["buyer_a"] == 0
    with pytest.raises(TransitionError):
        consume_capacity(state, "buyer_a")


def test_consume_capacity_unknown_actor() -> None:
    state = EnvironmentState(daily_capacity={"buyer_a": 1})
    with pytest.raises(TransitionError):
        consume_capacity(state, "unknown")


def test_advance_day_resets_capacity() -> None:
    state = EnvironmentState(daily_capacity={"buyer_a": 3})
    consume_capacity(state, "buyer_a")
    assert state.remaining_capacity["buyer_a"] == 2
    advance_day(state)
    assert state.current_day == 1
    assert state.remaining_capacity["buyer_a"] == 3


# ---------------------------------------------------------------------------
# End-to-end happy path (under-threshold, no approver needed)
# ---------------------------------------------------------------------------


def _make_state() -> EnvironmentState:
    return EnvironmentState(
        daily_capacity={
            "buyer_a": 5,
            "approver_c": 5,
            "accountant_d": 5,
        }
    )


def test_end_to_end_under_threshold_happy_path() -> None:
    state = _make_state()
    state.controls.approval_threshold = 1_000_000.0

    req = draft_request(state, "buyer_a", "Acme", "paper", amount=50_000.0)
    assert req.status == RequestStatus.DRAFTED
    assert req in ready_to_order(state)  # under threshold auto-eligible
    assert req not in pending_for_approval(state)

    order = place_order(state, "buyer_a", req.id)
    assert req.status == RequestStatus.ORDERED
    assert order.vendor == "Acme"

    record_receipt(state, "buyer_a", order.id, delivered_amount=50_000.0)
    assert state.get_request(req.id).status == RequestStatus.RECEIVED

    register_invoice(state, order.id, amount=50_000.0)
    assert three_way_match(state, order.id) is True

    payment = pay_order(state, "accountant_d", order.id)
    assert payment.three_way_matched is True
    assert state.get_request(req.id).status == RequestStatus.PAID
    assert state.total_amount() == 50_000.0
    assert state.deviation_count == 0


# ---------------------------------------------------------------------------
# Approval required path (above threshold)
# ---------------------------------------------------------------------------


def test_above_threshold_requires_approval() -> None:
    state = _make_state()
    state.controls.approval_threshold = 1_000_000.0

    req = draft_request(state, "buyer_a", "Acme", "server", amount=2_000_000.0)
    assert req in pending_for_approval(state)
    assert req not in ready_to_order(state)

    # Cannot order without approval
    with pytest.raises(TransitionError):
        place_order(state, "buyer_a", req.id)

    approval = approve_request(
        state, "approver_c", req.id, ApprovalDecision.APPROVED, note="ok"
    )
    assert approval.decision == ApprovalDecision.APPROVED
    assert state.get_request(req.id).status == RequestStatus.APPROVED

    place_order(state, "buyer_a", req.id)
    assert state.get_request(req.id).status == RequestStatus.ORDERED


def test_rejection_blocks_order() -> None:
    state = _make_state()
    state.controls.approval_threshold = 100.0
    req = draft_request(state, "buyer_a", "Acme", "laptop", amount=500.0)
    approve_request(state, "approver_c", req.id, ApprovalDecision.REJECTED)
    assert state.get_request(req.id).status == RequestStatus.REJECTED
    with pytest.raises(TransitionError):
        place_order(state, "buyer_a", req.id)


# ---------------------------------------------------------------------------
# Three-way match & deviations
# ---------------------------------------------------------------------------


def test_three_way_mismatch_puts_on_hold_when_required() -> None:
    state = _make_state()
    state.controls.approval_threshold = 10_000_000.0  # no approval needed
    state.controls.three_way_match_required = True

    req = draft_request(state, "buyer_a", "Acme", "paper", amount=100.0)
    order = place_order(state, "buyer_a", req.id)
    record_receipt(state, "buyer_a", order.id, delivered_amount=100.0)
    # Invoice amount mismatches order
    register_invoice(state, order.id, amount=120.0)

    assert three_way_match(state, order.id) is False
    with pytest.raises(TransitionError):
        pay_order(state, "accountant_d", order.id)
    assert state.get_request(req.id).status == RequestStatus.ON_HOLD
    assert state.deviation_count == 1


def test_three_way_mismatch_paid_when_not_required() -> None:
    state = _make_state()
    state.controls.approval_threshold = 10_000_000.0
    state.controls.three_way_match_required = False

    req = draft_request(state, "buyer_a", "Acme", "paper", amount=100.0)
    order = place_order(state, "buyer_a", req.id)
    record_receipt(state, "buyer_a", order.id, delivered_amount=90.0)
    register_invoice(state, order.id, amount=120.0)

    payment = pay_order(state, "accountant_d", order.id)
    assert payment.three_way_matched is False
    assert state.deviation_count == 1  # logged as deviation even though paid
    assert state.get_request(req.id).status == RequestStatus.PAID


def test_tolerance_allows_small_mismatch() -> None:
    state = _make_state()
    state.controls.approval_threshold = 10_000_000.0
    state.controls.three_way_match_tolerance = 5.0

    req = draft_request(state, "buyer_a", "Acme", "paper", amount=100.0)
    order = place_order(state, "buyer_a", req.id)
    record_receipt(state, "buyer_a", order.id, delivered_amount=98.0)
    register_invoice(state, order.id, amount=103.0)

    assert three_way_match(state, order.id) is True
    payment = pay_order(state, "accountant_d", order.id)
    assert payment.three_way_matched is True
    assert state.deviation_count == 0


# ---------------------------------------------------------------------------
# Query helpers
# ---------------------------------------------------------------------------


def test_awaiting_payment_excludes_uninvoiced_and_paid() -> None:
    state = _make_state()
    state.controls.approval_threshold = 10_000_000.0

    req1 = draft_request(state, "buyer_a", "Acme", "a", amount=10.0)
    order1 = place_order(state, "buyer_a", req1.id)
    record_receipt(state, "buyer_a", order1.id, 10.0)
    register_invoice(state, order1.id, 10.0)
    assert order1 in awaiting_payment(state)

    pay_order(state, "accountant_d", order1.id)
    assert order1 not in awaiting_payment(state)

    # Another order without invoice yet
    req2 = draft_request(state, "buyer_a", "Acme", "b", amount=20.0)
    order2 = place_order(state, "buyer_a", req2.id)
    assert order2 not in awaiting_payment(state)


def test_duplicate_receipt_or_invoice_rejected() -> None:
    state = _make_state()
    state.controls.approval_threshold = 10_000_000.0
    req = draft_request(state, "buyer_a", "Acme", "a", amount=10.0)
    order = place_order(state, "buyer_a", req.id)
    record_receipt(state, "buyer_a", order.id, 10.0)
    with pytest.raises(TransitionError):
        record_receipt(state, "buyer_a", order.id, 10.0)
    register_invoice(state, order.id, 10.0)
    with pytest.raises(TransitionError):
        register_invoice(state, order.id, 10.0)
