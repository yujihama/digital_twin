"""Unit tests for T-028 interpretive ambiguity.

Covers the four integration points listed in the spec:

1. Deterministic generator — same seed produces same fields byte-for-byte
2. place_order injects ambiguity when enabled, leaves defaults when disabled
3. three_way_match honors the new tolerance_rate field (max of abs & rate)
4. vendor_e observation surfaces ambiguity fields on ``my_orders`` entries
5. RB-min vendor_e behavior is unchanged by ambiguity (it ignores the fields
   and always passes ``order.amount`` through)

See environment.py::Order, rules.py::_generate_order_ambiguity, and
dispatchers/purchase.py::PurchaseDispatcher for the implementation.
"""

from __future__ import annotations

import random

from oct.agent import AgentAction
from oct.agents.rb_min import RBMinVendorAgent
from oct.dispatchers.purchase import PurchaseDispatcher
from oct.environment import EnvironmentState
from oct.personas.vendor_e import build_observation as build_vendor_e_observation
from oct.rules import (
    DEFAULT_AMBIGUITY_CONFIG,
    VALID_AMBIGUITY_BRANCHES,
    DemandConfig,
    _generate_order_ambiguity,
    draft_request,
    place_order,
    record_receipt,
    register_invoice,
    three_way_match,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_state() -> EnvironmentState:
    # T-028 tests loop many draft_request + place_order pairs on day 0, so
    # use generous per-actor capacities to avoid TransitionError on capacity
    # exhaustion. The rules being tested are orthogonal to capacity.
    return EnvironmentState(
        daily_capacity={
            "buyer_a": 200,
            "approver_c": 200,
            "accountant_d": 200,
            "vendor_e": 200,
        }
    )


# ---------------------------------------------------------------------------
# 1. Deterministic generator
# ---------------------------------------------------------------------------


def test_generator_is_deterministic_given_seed() -> None:
    """Same rng seed → same (tax_included, prior_adjustment, quantity_spec)."""
    rng_a = random.Random(42)
    rng_b = random.Random(42)
    a1 = _generate_order_ambiguity(100_000.0, rng_a)
    b1 = _generate_order_ambiguity(100_000.0, rng_b)
    assert a1 == b1

    # Advancing the rng produces a different (but still deterministic) value
    a2 = _generate_order_ambiguity(100_000.0, rng_a)
    b2 = _generate_order_ambiguity(100_000.0, rng_b)
    assert a2 == b2


def test_generator_returns_expected_types() -> None:
    """All three fields match their declared Order types."""
    rng = random.Random(123)
    for _ in range(20):
        tax, adj, qty = _generate_order_ambiguity(250_000.0, rng)
        assert tax is None or isinstance(tax, bool)
        assert isinstance(adj, float)
        assert qty in ("exact", "approximate", "as_available")


def test_generator_prior_adjustment_within_bound() -> None:
    """prior_adjustment never exceeds prior_adjustment_max_pct of PO amount."""
    rng = random.Random(7)
    amount = 500_000.0
    bound = amount * DEFAULT_AMBIGUITY_CONFIG.prior_adjustment_max_pct
    for _ in range(200):
        _, adj, _ = _generate_order_ambiguity(amount, rng)
        assert abs(adj) <= bound + 1.0  # +1 for rounding slack


# ---------------------------------------------------------------------------
# 2. place_order integration
# ---------------------------------------------------------------------------


def test_place_order_injects_ambiguity_when_enabled() -> None:
    """With ambiguity_enabled, orders carry non-default fields (statistically)."""
    state = EnvironmentState(
        daily_capacity={"buyer_a": 200, "approver_c": 200, "accountant_d": 200, "vendor_e": 200}
    )
    state.controls.approval_threshold = 10_000_000.0
    state.controls.ambiguity_enabled = True
    state._ambiguity_rng = random.Random(42)

    for i in range(30):
        req = draft_request(state, "buyer_a", "vendor_e", f"item_{i}", amount=100_000.0)
        place_order(state, "buyer_a", req.id)

    # At least a few orders should have non-default values. With default
    # weights, P(all exact, 0 adjustment, known-tax) ≈ 0.7*0.6*0.7 ≈ 0.29
    # per order, so 30 orders with *zero* ambiguity is astronomically unlikely.
    has_non_exact_qty = any(o.quantity_spec != "exact" for o in state.orders)
    has_nonzero_adjustment = any(o.prior_adjustment != 0.0 for o in state.orders)
    has_unspecified_tax = any(o.tax_included is None for o in state.orders)
    assert has_non_exact_qty, "Expected at least one non-exact quantity_spec"
    assert has_nonzero_adjustment, "Expected at least one non-zero prior_adjustment"
    assert has_unspecified_tax, "Expected at least one tax_included=None"


def test_place_order_keeps_defaults_when_disabled() -> None:
    """Without ambiguity_enabled, every order has the backward-compat defaults."""
    state = _make_state()
    state.controls.approval_threshold = 10_000_000.0
    # ambiguity_enabled defaults to False and no rng is attached

    for i in range(5):
        req = draft_request(state, "buyer_a", "vendor_e", f"item_{i}", amount=100_000.0)
        place_order(state, "buyer_a", req.id)

    for order in state.orders:
        assert order.tax_included is None
        assert order.prior_adjustment == 0.0
        assert order.quantity_spec == "exact"


def test_place_order_reproducibility_across_runs() -> None:
    """Two dispatchers with same seed produce identical ambiguity on every PO."""
    orders_a = _run_place_order_sequence(seed=99)
    orders_b = _run_place_order_sequence(seed=99)
    assert len(orders_a) == len(orders_b)
    for a, b in zip(orders_a, orders_b):
        assert (a.tax_included, a.prior_adjustment, a.quantity_spec) == (
            b.tax_included,
            b.prior_adjustment,
            b.quantity_spec,
        )


def _run_place_order_sequence(seed: int) -> list:
    from oct.rules import advance_day
    state = EnvironmentState(
        daily_capacity={"buyer_a": 200, "approver_c": 200, "accountant_d": 200, "vendor_e": 200}
    )
    state.controls.approval_threshold = 10_000_000.0
    PurchaseDispatcher(
        state,
        demand_config=DemandConfig(mean_daily_demands=1.0),
        demand_rng_seed=seed,
        ambiguity_enabled=True,
    )
    for i in range(10):
        req = draft_request(state, "buyer_a", "vendor_e", f"item_{i}", amount=150_000.0)
        place_order(state, "buyer_a", req.id)
    return list(state.orders)


# ---------------------------------------------------------------------------
# 3. three_way_match with tolerance_rate
# ---------------------------------------------------------------------------


def test_three_way_match_tolerance_rate_allows_percentage_mismatch() -> None:
    """5% tolerance rate allows up to 5% deviation on a 200k PO."""
    state = _make_state()
    state.controls.approval_threshold = 10_000_000.0
    state.controls.three_way_match_tolerance_rate = 0.05

    req = draft_request(state, "buyer_a", "vendor_e", "x", amount=200_000.0)
    order = place_order(state, "buyer_a", req.id)
    # 5% of 200k = 10k; 207k invoice is within tolerance, 215k is not
    record_receipt(state, "buyer_a", order.id, delivered_amount=200_000.0)
    register_invoice(state, order.id, amount=207_000.0)
    assert three_way_match(state, order.id) is True


def test_three_way_match_tolerance_rate_rejects_over_percentage() -> None:
    state = _make_state()
    state.controls.approval_threshold = 10_000_000.0
    state.controls.three_way_match_tolerance_rate = 0.05

    req = draft_request(state, "buyer_a", "vendor_e", "x", amount=200_000.0)
    order = place_order(state, "buyer_a", req.id)
    record_receipt(state, "buyer_a", order.id, delivered_amount=200_000.0)
    # 215k is 7.5% over — exceeds 5% rate and exceeds abs=0
    register_invoice(state, order.id, amount=215_000.0)
    assert three_way_match(state, order.id) is False


def test_three_way_match_uses_max_of_abs_and_rate() -> None:
    """effective_tol = max(abs, order.amount * rate)."""
    state = _make_state()
    state.controls.approval_threshold = 10_000_000.0
    # abs=8000 vs rate=0.05 * 100_000 = 5000 → abs wins
    state.controls.three_way_match_tolerance = 8_000.0
    state.controls.three_way_match_tolerance_rate = 0.05

    req = draft_request(state, "buyer_a", "vendor_e", "x", amount=100_000.0)
    order = place_order(state, "buyer_a", req.id)
    record_receipt(state, "buyer_a", order.id, delivered_amount=100_000.0)
    register_invoice(state, order.id, amount=107_000.0)  # 7k over, under 8k abs
    assert three_way_match(state, order.id) is True


def test_three_way_match_defaults_reproduce_prior_behavior() -> None:
    """tolerance_rate=0 & abs=0 → strict equality (PR #24 / PR #26 behavior)."""
    state = _make_state()
    state.controls.approval_threshold = 10_000_000.0

    req = draft_request(state, "buyer_a", "vendor_e", "x", amount=100_000.0)
    order = place_order(state, "buyer_a", req.id)
    record_receipt(state, "buyer_a", order.id, delivered_amount=100_000.0)
    register_invoice(state, order.id, amount=100_001.0)  # 1yen over
    assert three_way_match(state, order.id) is False


# ---------------------------------------------------------------------------
# 4. vendor_e observation surfaces ambiguity
# ---------------------------------------------------------------------------


def test_vendor_e_observation_includes_ambiguity_fields() -> None:
    state = _make_state()
    state.controls.approval_threshold = 10_000_000.0
    state.controls.ambiguity_enabled = True
    state._ambiguity_rng = random.Random(5)

    req = draft_request(state, "buyer_a", "vendor_e", "sensor", amount=300_000.0)
    order = place_order(state, "buyer_a", req.id)

    obs = build_vendor_e_observation(state, "vendor_e")
    assert len(obs["my_orders"]) == 1
    entry = obs["my_orders"][0]
    assert entry["order_id"] == order.id
    assert "tax_included" in entry
    assert "prior_adjustment" in entry
    assert "quantity_spec" in entry
    # Values should match the order itself
    assert entry["tax_included"] == order.tax_included
    assert entry["prior_adjustment"] == order.prior_adjustment
    assert entry["quantity_spec"] == order.quantity_spec


def test_vendor_e_observation_defaults_without_ambiguity() -> None:
    """ambiguity disabled → observation still has the fields, set to defaults."""
    state = _make_state()
    state.controls.approval_threshold = 10_000_000.0

    req = draft_request(state, "buyer_a", "vendor_e", "sensor", amount=300_000.0)
    place_order(state, "buyer_a", req.id)

    obs = build_vendor_e_observation(state, "vendor_e")
    entry = obs["my_orders"][0]
    assert entry["tax_included"] is None
    assert entry["prior_adjustment"] == 0.0
    assert entry["quantity_spec"] == "exact"


# ---------------------------------------------------------------------------
# 5. RB-min vendor_e unchanged by ambiguity
# ---------------------------------------------------------------------------


def test_rb_min_vendor_ignores_ambiguity() -> None:
    """RBMinVendorAgent always delivers at exactly order.amount regardless
    of any ambiguity fields in the observation. This is the T-028 invariant:
    the rule-based vendor is the control condition for the experiment — if
    RB-min reacted to ambiguity we could not distinguish the LLM effect.
    """
    state = _make_state()
    state.controls.approval_threshold = 10_000_000.0
    state.controls.ambiguity_enabled = True
    state._ambiguity_rng = random.Random(999)

    req = draft_request(state, "buyer_a", "vendor_e", "sensor", amount=300_000.0)
    order = place_order(state, "buyer_a", req.id)
    # Force an ambiguous order for the test regardless of rng roll
    order.tax_included = None
    order.prior_adjustment = 12_345.0
    order.quantity_spec = "approximate"

    agent = RBMinVendorAgent(
        agent_id="vendor_e",
        role="vendor",
        persona="rb-min",
        available_actions=[],
    )
    obs = build_vendor_e_observation(state, "vendor_e")
    action = agent._choose_action(obs)
    assert action is not None
    assert action.action_type == "deliver"
    # Crucial: delivered_amount equals order.amount, NOT order.amount +
    # prior_adjustment or any interpretation of tax/quantity ambiguity.
    assert action.parameters["delivered_amount"] == order.amount
    assert action.parameters["order_id"] == order.id


# ---------------------------------------------------------------------------
# 6. T-028c — branch attribution (--ambiguity-branch)
# ---------------------------------------------------------------------------
#
# The branch flag must satisfy three properties so the T-028c attribution
# experiment is interpretable:
#
#   (a) Single-branch modes mask the inactive channels back to the
#       "no ambiguity" defaults (None / 0.0 / "exact"). The active
#       channel still carries its rolled value.
#   (b) The rng stream is byte-identical across branches: the same seed
#       advances the rng by the same number of calls regardless of which
#       branch is selected. This means a "tax_only" run reuses exactly
#       the same tax_roll the "all" run would have seen for the same PO
#       — so any difference in deviation_count is attributable to channel
#       masking, not to a divergent rng stream.
#   (c) branch="all" is byte-equivalent to omitting the flag entirely
#       (PR #27 / T-028 Phase A reproducibility).


def test_ambiguity_branch_all_matches_default() -> None:
    """branch='all' must produce identical output to the default for the
    same rng state — this is the backward-compat guarantee for PR #27."""
    rng_default = random.Random(2026)
    rng_all = random.Random(2026)
    for _ in range(50):
        d = _generate_order_ambiguity(150_000.0, rng_default)
        a = _generate_order_ambiguity(150_000.0, rng_all, branch="all")
        assert d == a


def test_ambiguity_branch_tax_only_keeps_others_default() -> None:
    """tax_only: prior_adjustment is always 0.0 and quantity_spec is always
    'exact', regardless of how the rng would have rolled them. tax_included
    matches what the 'all' branch would have produced for the same rng
    state (because the rolls happen in the same order).
    """
    rng_branch = random.Random(7)
    rng_all = random.Random(7)
    for _ in range(40):
        tax_b, prior_b, qty_b = _generate_order_ambiguity(
            200_000.0, rng_branch, branch="tax_only"
        )
        tax_a, prior_a, qty_a = _generate_order_ambiguity(
            200_000.0, rng_all, branch="all"
        )
        # masked channels
        assert prior_b == 0.0
        assert qty_b == "exact"
        # active channel matches the 'all' baseline (rng stream identical)
        assert tax_b == tax_a


def test_ambiguity_branch_prior_only_keeps_others_default() -> None:
    """prior_only: tax_included is always None and quantity_spec is always
    'exact'. prior_adjustment matches the 'all' baseline for the same rng.
    """
    rng_branch = random.Random(11)
    rng_all = random.Random(11)
    for _ in range(40):
        tax_b, prior_b, qty_b = _generate_order_ambiguity(
            200_000.0, rng_branch, branch="prior_only"
        )
        tax_a, prior_a, qty_a = _generate_order_ambiguity(
            200_000.0, rng_all, branch="all"
        )
        assert tax_b is None
        assert qty_b == "exact"
        assert prior_b == prior_a


def test_ambiguity_branch_quantity_only_keeps_others_default() -> None:
    """quantity_only: tax_included is always None and prior_adjustment is
    always 0.0. quantity_spec matches the 'all' baseline for the same rng.
    """
    rng_branch = random.Random(13)
    rng_all = random.Random(13)
    for _ in range(40):
        tax_b, prior_b, qty_b = _generate_order_ambiguity(
            200_000.0, rng_branch, branch="quantity_only"
        )
        tax_a, prior_a, qty_a = _generate_order_ambiguity(
            200_000.0, rng_all, branch="all"
        )
        assert tax_b is None
        assert prior_b == 0.0
        assert qty_b == qty_a


def test_ambiguity_branch_rng_stream_byte_identical_across_branches() -> None:
    """Property (b): the rng is advanced by the *same* number of calls for
    any branch value. We probe this by reading rng.random() AFTER the
    generator and asserting all four branches leave it in the same state.
    """
    next_values = []
    for branch in VALID_AMBIGUITY_BRANCHES:
        rng = random.Random(31337)
        for _ in range(10):
            _generate_order_ambiguity(120_000.0, rng, branch=branch)
        next_values.append(rng.random())
    assert len(set(next_values)) == 1, (
        f"rng stream diverged across branches: {dict(zip(VALID_AMBIGUITY_BRANCHES, next_values))}"
    )


def test_ambiguity_branch_invalid_value_raises() -> None:
    """Typos in --ambiguity-branch must fail loud at the first roll."""
    rng = random.Random(0)
    try:
        _generate_order_ambiguity(100_000.0, rng, branch="not_a_real_branch")
    except ValueError as exc:
        assert "not_a_real_branch" in str(exc)
    else:  # pragma: no cover - assertion failure path
        raise AssertionError("expected ValueError for unknown branch")


def test_dispatcher_records_branch_on_state_controls() -> None:
    """PurchaseDispatcher must propagate ambiguity_branch onto state.controls
    so place_order picks it up via state.controls.ambiguity_branch.
    """
    state = _make_state()
    state.controls.approval_threshold = 10_000_000.0
    PurchaseDispatcher(
        state,
        demand_config=DemandConfig(mean_daily_demands=1.0),
        demand_rng_seed=99,
        ambiguity_enabled=True,
        ambiguity_branch="prior_only",
    )
    assert state.controls.ambiguity_branch == "prior_only"


def test_place_order_branch_tax_only_masks_other_channels() -> None:
    """End-to-end: with branch=tax_only every Order has prior_adjustment=0
    and quantity_spec='exact', but tax_included is allowed to vary.
    """
    state = _make_state()
    state.controls.approval_threshold = 10_000_000.0
    PurchaseDispatcher(
        state,
        demand_config=DemandConfig(mean_daily_demands=1.0),
        demand_rng_seed=42,
        ambiguity_enabled=True,
        ambiguity_branch="tax_only",
    )
    for i in range(30):
        req = draft_request(state, "buyer_a", "vendor_e", f"item_{i}", amount=180_000.0)
        place_order(state, "buyer_a", req.id)

    for o in state.orders:
        assert o.prior_adjustment == 0.0, (
            f"prior_adjustment leaked through tax_only: {o.prior_adjustment}"
        )
        assert o.quantity_spec == "exact", (
            f"quantity_spec leaked through tax_only: {o.quantity_spec}"
        )
    # And we still want at least one non-default tax value (otherwise the
    # branch would be indistinguishable from "no ambiguity" and the test
    # could pass for the wrong reason).
    assert any(o.tax_included is True or o.tax_included is False for o in state.orders), (
        "expected at least one rolled True/False tax_included under tax_only"
    )


def test_place_order_branch_prior_only_masks_other_channels() -> None:
    state = _make_state()
    state.controls.approval_threshold = 10_000_000.0
    PurchaseDispatcher(
        state,
        demand_config=DemandConfig(mean_daily_demands=1.0),
        demand_rng_seed=42,
        ambiguity_enabled=True,
        ambiguity_branch="prior_only",
    )
    for i in range(30):
        req = draft_request(state, "buyer_a", "vendor_e", f"item_{i}", amount=180_000.0)
        place_order(state, "buyer_a", req.id)

    for o in state.orders:
        assert o.tax_included is None
        assert o.quantity_spec == "exact"
    assert any(o.prior_adjustment != 0.0 for o in state.orders), (
        "expected at least one non-zero prior_adjustment under prior_only"
    )


def test_place_order_branch_quantity_only_masks_other_channels() -> None:
    state = _make_state()
    state.controls.approval_threshold = 10_000_000.0
    PurchaseDispatcher(
        state,
        demand_config=DemandConfig(mean_daily_demands=1.0),
        demand_rng_seed=42,
        ambiguity_enabled=True,
        ambiguity_branch="quantity_only",
    )
    for i in range(30):
        req = draft_request(state, "buyer_a", "vendor_e", f"item_{i}", amount=180_000.0)
        place_order(state, "buyer_a", req.id)

    for o in state.orders:
        assert o.tax_included is None
        assert o.prior_adjustment == 0.0
    assert any(o.quantity_spec != "exact" for o in state.orders), (
        "expected at least one non-exact quantity_spec under quantity_only"
    )


def test_rb_min_register_invoice_unchanged_under_ambiguity() -> None:
    """After delivery, RB-min invoices at exactly order.amount as well."""
    state = _make_state()
    state.controls.approval_threshold = 10_000_000.0
    state.controls.ambiguity_enabled = True
    state._ambiguity_rng = random.Random(12)

    req = draft_request(state, "buyer_a", "vendor_e", "sensor", amount=250_000.0)
    order = place_order(state, "buyer_a", req.id)
    order.tax_included = False
    order.prior_adjustment = -5000.0
    order.quantity_spec = "as_available"
    record_receipt(state, "buyer_a", order.id, delivered_amount=order.amount)

    agent = RBMinVendorAgent(
        agent_id="vendor_e",
        role="vendor",
        persona="rb-min",
        available_actions=[],
    )
    obs = build_vendor_e_observation(state, "vendor_e")
    action = agent._choose_action(obs)
    assert action is not None
    assert action.action_type == "register_invoice"
    assert action.parameters["amount"] == order.amount
    assert action.parameters["order_id"] == order.id
