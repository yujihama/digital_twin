"""Unit tests for the EnvironmentState schema."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from oct.environment import (
    ControlParameters,
    EnvironmentState,
    PurchaseRequest,
    RequestStatus,
)


def test_environment_state_defaults() -> None:
    state = EnvironmentState()
    assert state.current_day == 0
    assert state.purchase_requests == []
    assert state.payments == []
    assert state.deviation_count == 0
    assert state.error_count == 0
    assert state.controls.approval_threshold == 1_000_000.0
    assert state.controls.three_way_match_required is True
    # daily_capacity seeded with defaults for the 5 roles (incl. external vendor_e)
    assert set(state.daily_capacity) == {
        "buyer_a",
        "buyer_b",
        "approver_c",
        "accountant_d",
        "vendor_e",
    }


def test_ensure_capacity_initialized_is_idempotent() -> None:
    state = EnvironmentState()
    state.ensure_capacity_initialized()
    snapshot = dict(state.remaining_capacity)
    # Second call must not reset already-consumed capacity
    state.remaining_capacity["buyer_a"] = 1
    state.ensure_capacity_initialized()
    assert state.remaining_capacity["buyer_a"] == 1
    assert snapshot["buyer_a"] == state.daily_capacity["buyer_a"]


def test_next_id_is_monotonic_per_prefix() -> None:
    state = EnvironmentState()
    ids = [state.next_id("req") for _ in range(3)]
    assert ids == ["req_00001", "req_00002", "req_00003"]
    # Different prefix starts fresh
    assert state.next_id("ord") == "ord_00001"
    assert state.next_id("req") == "req_00004"


def test_purchase_request_requires_positive_amount() -> None:
    with pytest.raises(ValidationError):
        PurchaseRequest(
            id="req_1",
            requester="buyer_a",
            vendor="V",
            item="paper",
            amount=0.0,
            created_day=0,
        )


def test_control_parameters_validation() -> None:
    with pytest.raises(ValidationError):
        ControlParameters(approval_threshold=-1.0)


def test_lookup_helpers_return_none_when_missing() -> None:
    state = EnvironmentState()
    assert state.get_request("missing") is None
    assert state.get_order("missing") is None
    assert state.approval_for("missing") is None
    assert state.receipt_for("missing") is None
    assert state.invoice_for("missing") is None


def test_total_amount_sums_payments() -> None:
    state = EnvironmentState()
    # total of 0 when empty
    assert state.total_amount() == 0.0


def test_request_status_enum_values() -> None:
    # Guard against accidental rename of enum values used by agents/logger
    assert RequestStatus.DRAFTED.value == "drafted"
    assert RequestStatus.APPROVED.value == "approved"
    assert RequestStatus.PAID.value == "paid"
    assert RequestStatus.ON_HOLD.value == "on_hold"
