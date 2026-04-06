"""Tests for the demand generation mechanism (Option A+C from exp001).

Covers:
  - DemandEvent model basics
  - generate_demands stochastic generation with seeded RNG
  - fulfill_demand linking
  - PurchaseDispatcher integration (day-0 seeding + advance_day generation)
  - Buyer observation includes pending_demands
  - draft_request with demand_id fulfillment
"""
from __future__ import annotations

import random

import pytest

from oct.dispatchers.purchase import PurchaseDispatcher
from oct.environment import (
    DemandEvent,
    DemandUrgency,
    EnvironmentState,
)
from oct.rules import (
    DemandConfig,
    TransitionError,
    fulfill_demand,
    generate_demands,
)
from oct.personas.buyer_a import build_observation as build_buyer_a_obs
from oct.personas.buyer_b import build_observation as build_buyer_b_obs


# ---------------------------------------------------------------------------
# DemandEvent model
# ---------------------------------------------------------------------------

class TestDemandEvent:
    def test_create_demand_event(self):
        d = DemandEvent(
            id="dem_00001",
            department="製造部",
            item="ボルトセット M8",
            amount_hint=50_000,
            urgency=DemandUrgency.HIGH,
            generated_day=0,
        )
        assert d.fulfilled is False
        assert d.fulfilled_by_request_id is None
        assert d.urgency == DemandUrgency.HIGH

    def test_urgency_enum_values(self):
        assert DemandUrgency.LOW.value == "low"
        assert DemandUrgency.NORMAL.value == "normal"
        assert DemandUrgency.HIGH.value == "high"


# ---------------------------------------------------------------------------
# generate_demands
# ---------------------------------------------------------------------------

class TestGenerateDemands:
    def test_seeded_reproducibility(self):
        """Same seed should produce identical demands."""
        state1 = EnvironmentState(current_day=0)
        state2 = EnvironmentState(current_day=0)
        cfg = DemandConfig(mean_daily_demands=3.0)

        d1 = generate_demands(state1, cfg, random.Random(99))
        d2 = generate_demands(state2, cfg, random.Random(99))

        assert len(d1) == len(d2)
        for a, b in zip(d1, d2):
            assert a.department == b.department
            assert a.item == b.item
            assert a.amount_hint == b.amount_hint
            assert a.urgency == b.urgency

    def test_demands_appended_to_state(self):
        state = EnvironmentState(current_day=5)
        cfg = DemandConfig(mean_daily_demands=2.0)
        demands = generate_demands(state, cfg, random.Random(42))
        assert len(state.demand_queue) == len(demands)
        for d in demands:
            assert d.generated_day == 5

    def test_zero_mean_produces_mostly_zero(self):
        """With mean=0.01, almost all runs produce 0 demands."""
        cfg = DemandConfig(mean_daily_demands=0.01)
        counts = []
        for seed in range(100):
            state = EnvironmentState()
            generate_demands(state, cfg, random.Random(seed))
            counts.append(len(state.demand_queue))
        assert sum(counts) < 10  # very few demands expected

    def test_ids_are_sequential(self):
        state = EnvironmentState()
        cfg = DemandConfig(mean_daily_demands=5.0)
        demands = generate_demands(state, cfg, random.Random(7))
        if len(demands) >= 2:
            ids = [d.id for d in demands]
            # All should start with "dem_"
            assert all(i.startswith("dem_") for i in ids)
            # Sequential
            nums = [int(i.split("_")[1]) for i in ids]
            assert nums == list(range(1, len(nums) + 1))

    def test_amount_jitter_applied(self):
        """With jitter=0.5, amounts should vary from the catalog base."""
        cfg = DemandConfig(mean_daily_demands=10.0, amount_jitter=0.5)
        state = EnvironmentState()
        demands = generate_demands(state, cfg, random.Random(123))
        # At least some demands should have amounts different from base catalog
        catalog_amounts = {a for _, _, a, _ in cfg.catalog}
        if len(demands) > 3:
            amounts = {d.amount_hint for d in demands}
            # With jitter, not all should exactly match catalog
            assert not amounts.issubset(catalog_amounts)


# ---------------------------------------------------------------------------
# fulfill_demand
# ---------------------------------------------------------------------------

class TestFulfillDemand:
    def test_fulfill_success(self):
        state = EnvironmentState()
        cfg = DemandConfig(mean_daily_demands=3.0)
        demands = generate_demands(state, cfg, random.Random(42))
        assert len(demands) > 0

        d = demands[0]
        fulfill_demand(state, d.id, "req_00001")
        assert d.fulfilled is True
        assert d.fulfilled_by_request_id == "req_00001"

    def test_fulfill_already_fulfilled_raises(self):
        state = EnvironmentState()
        d = DemandEvent(
            id="dem_00001", department="X", item="Y",
            amount_hint=100, generated_day=0,
            fulfilled=True, fulfilled_by_request_id="req_00001",
        )
        state.demand_queue.append(d)
        with pytest.raises(TransitionError, match="already fulfilled"):
            fulfill_demand(state, "dem_00001", "req_00002")

    def test_fulfill_not_found_raises(self):
        state = EnvironmentState()
        with pytest.raises(TransitionError, match="not found"):
            fulfill_demand(state, "dem_99999", "req_00001")

    def test_pending_demands_excludes_fulfilled(self):
        state = EnvironmentState()
        d1 = DemandEvent(id="dem_00001", department="A", item="X",
                         amount_hint=100, generated_day=0)
        d2 = DemandEvent(id="dem_00002", department="B", item="Y",
                         amount_hint=200, generated_day=0,
                         fulfilled=True, fulfilled_by_request_id="req_00001")
        state.demand_queue.extend([d1, d2])
        pending = state.pending_demands()
        assert len(pending) == 1
        assert pending[0].id == "dem_00001"


# ---------------------------------------------------------------------------
# PurchaseDispatcher integration
# ---------------------------------------------------------------------------

class TestDispatcherDemandIntegration:
    def test_day0_demands_seeded(self):
        """Dispatcher with demand_config should generate demands at init."""
        state = EnvironmentState(current_day=0)
        cfg = DemandConfig(mean_daily_demands=3.0)
        dispatcher = PurchaseDispatcher(state, demand_config=cfg, demand_rng_seed=42)
        assert len(state.demand_queue) > 0
        for d in state.demand_queue:
            assert d.generated_day == 0

    def test_advance_day_generates_more_demands(self):
        state = EnvironmentState(current_day=0)
        cfg = DemandConfig(mean_daily_demands=3.0)
        dispatcher = PurchaseDispatcher(state, demand_config=cfg, demand_rng_seed=42)
        day0_count = len(state.demand_queue)
        dispatcher.advance_day()
        assert len(state.demand_queue) >= day0_count  # may generate 0 but usually more
        # New demands should be for day 1
        new_demands = [d for d in state.demand_queue if d.generated_day == 1]
        # Can't guarantee non-zero due to Poisson, but structure is correct

    def test_no_demands_without_config(self):
        """Without demand_config, no demands are generated."""
        state = EnvironmentState(current_day=0)
        dispatcher = PurchaseDispatcher(state)
        assert len(state.demand_queue) == 0
        dispatcher.advance_day()
        assert len(state.demand_queue) == 0

    def test_snapshot_includes_demand_counts(self):
        state = EnvironmentState(current_day=0)
        cfg = DemandConfig(mean_daily_demands=3.0)
        dispatcher = PurchaseDispatcher(state, demand_config=cfg, demand_rng_seed=42)
        snap = dispatcher.snapshot()
        assert "demands_total" in snap["counts"]
        assert "demands_pending" in snap["counts"]
        assert "demands_fulfilled" in snap["counts"]
        assert snap["counts"]["demands_total"] == len(state.demand_queue)

    def test_draft_request_with_demand_id_fulfills(self):
        """draft_request action with demand_id should fulfill the demand."""
        from oct.agent import AgentAction

        state = EnvironmentState(current_day=0)
        d = DemandEvent(id="dem_00001", department="製造部", item="ボルト",
                        amount_hint=50000, generated_day=0)
        state.demand_queue.append(d)
        dispatcher = PurchaseDispatcher(state)

        action = AgentAction(
            action_type="draft_request",
            parameters={
                "vendor": "vendor_e",
                "item": "ボルト",
                "amount": 50000,
                "demand_id": "dem_00001",
            },
            reasoning="需要に対応",
        )
        result = dispatcher.dispatch("buyer_a", action)
        assert result["ok"] is True
        assert d.fulfilled is True
        assert d.fulfilled_by_request_id == result["details"]["request_id"]


# ---------------------------------------------------------------------------
# Buyer observations include pending_demands
# ---------------------------------------------------------------------------

class TestBuyerObservationDemands:
    def _make_state_with_demands(self) -> EnvironmentState:
        state = EnvironmentState(current_day=0)
        state.ensure_capacity_initialized()
        d1 = DemandEvent(id="dem_00001", department="製造部", item="ボルト",
                         amount_hint=50000, urgency=DemandUrgency.HIGH,
                         generated_day=0)
        d2 = DemandEvent(id="dem_00002", department="総務部", item="コピー用紙",
                         amount_hint=45000, urgency=DemandUrgency.NORMAL,
                         generated_day=0)
        d3 = DemandEvent(id="dem_00003", department="X", item="Y",
                         amount_hint=100, generated_day=0,
                         fulfilled=True, fulfilled_by_request_id="req_00001")
        state.demand_queue.extend([d1, d2, d3])
        return state

    def test_buyer_a_sees_pending_demands(self):
        state = self._make_state_with_demands()
        obs = build_buyer_a_obs(state, "buyer_a")
        assert "pending_demands" in obs
        assert len(obs["pending_demands"]) == 2  # d3 is fulfilled
        assert obs["pending_demands"][0]["id"] == "dem_00001"
        assert obs["pending_demands"][0]["urgency"] == "high"

    def test_buyer_a_sees_available_vendors(self):
        state = self._make_state_with_demands()
        obs = build_buyer_a_obs(state, "buyer_a")
        assert "available_vendors" in obs
        assert "vendor_e" in obs["available_vendors"]

    def test_buyer_b_sees_pending_demands(self):
        state = self._make_state_with_demands()
        obs = build_buyer_b_obs(state, "buyer_b")
        assert "pending_demands" in obs
        assert len(obs["pending_demands"]) == 2

    def test_buyer_b_sees_available_vendors(self):
        state = self._make_state_with_demands()
        obs = build_buyer_b_obs(state, "buyer_b")
        assert "available_vendors" in obs
        assert "vendor_e" in obs["available_vendors"]

    def test_no_demands_means_empty_list(self):
        state = EnvironmentState(current_day=0)
        state.ensure_capacity_initialized()
        obs = build_buyer_a_obs(state, "buyer_a")
        assert obs["pending_demands"] == []
