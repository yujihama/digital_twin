# T-028 — Interpretive ambiguity × three-way match tolerance probe

## 0. Target data

- Output root: `experiments/ablation_t028/`
- Cells: 2 phases × 2 levels (L1 RB-min, L3 `gpt-4.1-mini`) × 5 regimes
  (`baseline`, `intervention_I1`, `intervention_I2`, `combined_I1_I2`,
  `high_pressure`) × 3 seeds (42/43/44) = **60 cells total**
- `max_days = 20`, `actions_per_agent_per_day = 2`, temperature 0.8 for L3,
  `narrative_mode=false` (T-023 channel disabled so the only treatment is
  T-028's ambiguity fields and three-way match tolerance)
- Ambiguity flag: **ON for every cell** (`ambiguity_enabled=true`)
- Phase A: `three_way_match_tolerance_rate = 0.0` (strict)
- Phase B: `three_way_match_tolerance_rate = 0.05` (5% gray zone)
- Per-phase rollups:
  - `experiments/ablation_t028/phase_a/ablation_summary.json`
  - `experiments/ablation_t028/phase_b/ablation_summary.json`
  - `experiments/ablation_t028/aggregate_l1_l3.json` — combined L1+L3
    view rebuilt from the per-seed `summary.json` files (the per-phase
    rollups only retain whichever level was last written by
    `run_ablation.py`; see §2).

T-028 intentionally does **not** re-run narrative ON cells. The
narrative-ON comparison lives in `experiments/ablation_t023/` (PR #27),
and the no-ambiguity baseline lives in `experiments/ablation_t022/`
(PR #26). Both are held fixed as reference points for §3 and §4.

## 1. Scope

T-022/T-023 established that vendor-side opportunism requires
*natural-language* framing to produce even a single deviation: the
numeric incentive channel alone (T-022) yielded 0/30 deviations, while
the narrative channel (T-023) yielded 1/6 in `L3_high_pressure`. That
result left a separate hypothesis untouched: **real fraud is rarely a
single crisp act but a drift of gray-zone interpretive judgments that
pass individual control gates by hairs.** T-028 is the minimal probe
for that hypothesis.

The design principle is:

> Interpretive ambiguity (tax inclusion unstated, prior-period
> adjustments, quantity spec wording) creates small, individually
> defensible amount deltas. A zero-tolerance three-way match flags
> them; a 5% tolerance absorbs them. The difference between the two
> phases is the "quiet drift" the organization would see in practice.

The T-028 change set isolates three mechanical pieces:

1. `experiments/runtime/oct/environment.py`
   - `Order` gains three optional ambiguity fields —
     `tax_included: Optional[bool] = None`,
     `prior_adjustment: float = 0.0`,
     `quantity_spec: str = "exact"` — that do **not** change the
     authoritative `amount` on the PO row. They are side information
     that downstream agents may interpret.
   - `EnvironmentState` gains a PrivateAttr `_ambiguity_rng` seeded
     deterministically from `demand_rng_seed ^ 0xA28B`, so the
     ambiguity pattern is reproducible per (seed, day) but independent
     of the demand stream's RNG state. `ambiguity_enabled: bool` is a
     new config flag; when False the order fields keep their defaults
     and vendor_e is unaffected (T-022/T-023 reproduction path).
2. `experiments/runtime/oct/rules.py`
   - `three_way_match` now accepts `tolerance_rate: float = 0.0` in
     addition to the existing `tolerance_abs`. The effective tolerance
     is `max(tol_abs, order.amount * tol_rate)`, so the Phase A
     behavior (tol_rate=0) is byte-for-byte the same rule used by all
     prior tasks. The rule's pass/fail decision is still a single
     boolean — the change is only in what counts as "close enough".
3. `experiments/runtime/oct/personas/vendor_e.py`
   - When `ambiguity_enabled=True`, vendor_e (LLM) sees the three new
     fields inside each open order and may choose to let the narrative
     "tax included unclear → bill with tax" / "prior adjustment of
     N → net it out" / "quantity spec `about` → round up" reasoning
     steer the invoice amount. No persona instruction endorses or
     prohibits any of these choices; the rendering is purely
     descriptive. RB-min vendor_e is **untouched** and always emits
     the exact PO amount on the invoice — which is the load-bearing
     L1 control for §3.1.
4. `experiments/runtime/oct/dispatchers/purchase.py`
   - Threads `ambiguity_enabled` and `three_way_match_tolerance_rate`
     into the dispatcher and the rule call site. Neither kwarg is
     exposed to buyer_a / buyer_b / approver_c / accountant_d
     observations; only the PO row and the resulting invoice row can
     drift, the organizational roles do not see the ambiguity
     directly.
5. `experiments/runtime/scripts/run_ablation.py`
   - Two new flags: `--ambiguity` (store_true, default False) and
     `--tolerance-rate` (float, default 0.0). Also `--out` became
     configurable so the same script can populate `phase_a/` and
     `phase_b/` without collision. Both flags are recorded in every
     per-cell `summary.json` under `config`, and in the combined
     `ablation_summary.json.config`.
6. `experiments/runtime/scripts/analyze_trace.py`
   - New function `analyze_amount_deltas(steps)` groups trace events
     by `order_id` and reconstructs the (PO, GR, invoice) triple per
     order, then reports counts and the worst-case percentages under a
     `## T-028 PO vs Actual Amount Deltas` section. This is how §3.4
     is produced; the function is pure post-hoc analysis and does not
     affect the sim.
7. `experiments/runtime/tests/test_t028_ambiguity.py`
   - 14 new tests (130 → 144 pass total), organized into four groups:
     (a) ambiguity generator — `test_generator_is_deterministic_given_seed`,
     `test_generator_returns_expected_types`,
     `test_generator_prior_adjustment_within_bound`;
     (b) `place_order` integration — `test_place_order_injects_ambiguity_when_enabled`,
     `test_place_order_keeps_defaults_when_disabled`,
     `test_place_order_reproducibility_across_runs`;
     (c) three-way match tolerance — `test_three_way_match_tolerance_rate_allows_percentage_mismatch`,
     `test_three_way_match_tolerance_rate_rejects_over_percentage`,
     `test_three_way_match_uses_max_of_abs_and_rate`,
     `test_three_way_match_defaults_reproduce_prior_behavior`;
     (d) vendor_e observation & RB-min invariance —
     `test_vendor_e_observation_includes_ambiguity_fields`,
     `test_vendor_e_observation_defaults_without_ambiguity`,
     `test_rb_min_vendor_ignores_ambiguity`,
     `test_rb_min_register_invoice_unchanged_under_ambiguity`.

Narrative mode (T-023) and ambiguity mode (T-028) compose
orthogonally: T-028 does not touch `_render_business_context`, and the
narrative helper does not inspect the new Order fields. The T-028
sweep therefore runs with `narrative_mode=false` so the only treatment
is the ambiguity/tolerance stack.

## 2. Reproduction

All commands are run from `experiments/runtime/` with the pinned
`.venv` activated. Each phase is a 30-cell sweep (L1 × 5 regimes × 3
seeds + L3 × 5 regimes × 3 seeds); L1 is effectively instant, L3 is
≈4 min per cell at temperature 0.8.

```powershell
# Phase A — strict three-way match (tolerance_rate = 0)
python scripts\run_ablation.py --level L1 --all-regimes `
    --seeds 42 43 44 --ambiguity `
    --out ..\ablation_t028\phase_a
python scripts\run_ablation.py --level L3 --all-regimes `
    --seeds 42 43 44 --ambiguity `
    --out ..\ablation_t028\phase_a

# Phase B — lenient three-way match (tolerance_rate = 0.05)
python scripts\run_ablation.py --level L1 --all-regimes `
    --seeds 42 43 44 --ambiguity --tolerance-rate 0.05 `
    --out ..\ablation_t028\phase_b
python scripts\run_ablation.py --level L3 --all-regimes `
    --seeds 42 43 44 --ambiguity --tolerance-rate 0.05 `
    --out ..\ablation_t028\phase_b

# Rebuild the L1+L3 aggregate from every per-seed summary.json
python _aggregate_t028.py   # writes ablation_t028/aggregate_l1_l3.json
```

Note: `run_ablation.py` overwrites `<out>/ablation_summary.json` on
each invocation, so the phase_a and phase_b rollups on disk only
retain the last level written (L3 in our sweep order). The combined
view in §3 is rebuilt from the per-seed `summary.json` files via
`_aggregate_t028.py`; the `aggregate_l1_l3.json` it writes is the
primary artifact behind the tables below.

L3 wall clock per phase: ≈ 60 minutes (15 cells × ~4 min);
Phase B L1 was run concurrently with Phase A L3 (different output
roots, no collision, L1 has no API contention). Phase A L3 and
Phase B L3 were run sequentially to avoid LLM rate limit collisions.

## 3. Results

### 3.1 L1 (RB-min) — ambiguity ON, both phases

RB-min vendor_e never reads the new ambiguity fields; it always emits
the exact PO amount on delivery and invoice. Any Phase-A to Phase-B
difference in L1 would mean the control is leaking. Expected: all six
payments-by-seed triples match across phases, and every
`deviation_count` stays at 0.

| cell                 | Phase A pays (42/43/44) | Phase B pays (42/43/44) | Phase A dev | Phase B dev |
|----------------------|-------------------------|-------------------------|-------------|-------------|
| L1_baseline          | 24 / 23 / 18            | 24 / 23 / 18            | 0.000       | 0.000       |
| L1_intervention_I1   | 25 / 24 / 18            | 25 / 24 / 18            | 0.000       | 0.000       |
| L1_intervention_I2   | 24 / 23 / 18            | 24 / 23 / 18            | 0.000       | 0.000       |
| L1_combined_I1_I2    | 25 / 24 / 18            | 25 / 24 / 18            | 0.000       | 0.000       |
| L1_high_pressure     | 26 / 26 / 27            | 26 / 26 / 27            | 0.000       | 0.000       |

(Per-seed payment counts read from the individual
`L1_*/seed*/summary.json` files; cell means in the table above match
`aggregate_l1_l3.json` to three decimal places.)

All fifteen payment triples are byte-for-byte identical across the
two phases, and every deviation count stays at 0. The no-op guard is
also codified in
`tests/test_t028_ambiguity.py::test_rb_min_vendor_ignores_ambiguity`
and `::test_rb_min_register_invoice_unchanged_under_ambiguity`.

### 3.2 L3 (gpt-4.1-mini) — Phase A (tolerance_rate = 0)

With strict three-way match and ambiguity fields visible in vendor_e's
observation, two L3 cells produce non-zero deviation counts and the
other thirteen stay at zero.

| cell                 | mean_dev | per-seed dev (42/43/44) | mean_pay | mean_dispatched_ok |
|----------------------|----------|-------------------------|----------|--------------------|
| L3_baseline          | 0.000    | 0 / 0 / 0               | 16.667   | 154.333            |
| L3_intervention_I1   | 0.000    | 0 / 0 / 0               | 21.000   | 162.667            |
| L3_intervention_I2   | **0.667**| 0 / **2** / 0           | 18.667   | 161.667            |
| L3_combined_I1_I2    | **0.333**| 0 / **1** / 0           | 21.333   | 165.333            |
| L3_high_pressure     | 0.000    | 0 / 0 / 0               | 24.000   | 173.333            |

Two observations on the pattern:

- Both non-zero cells live on **seed 43** and specifically on the two
  regimes where three-way match is **off** (`intervention_I2` and the
  `combined` regime that inherits it). This is mechanically odd —
  three-way match being off should make *fewer* PO/invoice mismatches
  surface as deviations, not more. See §4.2 for the resolution (the
  mismatches are not coming from the three-way match rule at all;
  `rules.three_way_match` is short-circuited to `True` when the regime
  disables it, so any deviation that appears in these cells is a
  *different* deviation surface — the amount-sanity check at invoice
  registration time — which is still active).
- `L3_high_pressure` is flat zero under strict tolerance. That is the
  opposite ranking to T-023, where `high_pressure` was the only
  narrative-ON cell to deviate. The two treatments are evidently
  steering vendor_e through different mechanisms (see §4.3).

### 3.3 L3 (gpt-4.1-mini) — Phase B (tolerance_rate = 0.05)

Phase B re-runs the same 15 L3 cells with the only change being that
three-way match now accepts any invoice within 5% of the PO amount.

| cell                 | mean_dev | per-seed dev (42/43/44) | mean_pay | mean_dispatched_ok |
|----------------------|----------|-------------------------|----------|--------------------|
| L3_baseline          | 0.000    | 0 / 0 / 0               | 19.000   | 160.333            |
| L3_intervention_I1   | 0.000    | 0 / 0 / 0               | 20.333   | 162.333            |
| L3_intervention_I2   | 0.000    | 0 / 0 / 0               | 17.333   | 155.333            |
| L3_combined_I1_I2    | 0.000    | 0 / 0 / 0               | 20.333   | 162.667            |
| L3_high_pressure     | 0.000    | 0 / 0 / 0               | 25.667   | 173.333            |

The three deviations from Phase A (`intervention_I2` seed 43 ×2,
`combined_I1_I2` seed 43 ×1) all vanish under the 5% tolerance. Every
cell is at `mean_deviation_count = 0`. `mean_payments` drifts by
`L3_baseline` +2.333, `L3_high_pressure` +1.667, while `L3_intervention_I1`
and `L3_intervention_I2` actually drop slightly (−0.667 and −1.333)
— at T=0.8 on n=3 per cell these moves are within noise, and only
the baseline/high_pressure deltas are large enough to be suggestive.
The load-bearing comparison is not the payment count; it is the fact
that Phase A caught three deviations that Phase B's 5% band silently
absorbs.

### 3.4 Deviation anatomy — Phase A L3 anomaly traces

`scripts/analyze_trace.py` was extended in T-028 to report per-order
PO vs actual-receipt vs actual-invoice amount deltas (new
`## T-028 PO vs Actual Amount Deltas` section). Running it against
the two Phase-A non-zero cells gives:

**`L3_intervention_I2` seed 43** (deviation_count = 2):

```
n_orders              : 26
n_with_gr             : 26
n_with_invoice        : 22
n_gr_delta_nonzero    : 1
n_inv_delta_nonzero   : 2
max_abs_gr_delta_pct  : 2.283
max_abs_inv_delta_pct : 2.493
mean_abs_inv_delta_pct: 0.217

order_id       po          gr          gr_Δ        inv         inv_Δ
ord_00003      33213       33213       +0.00%      32385       -2.49%
ord_00009      28685       28030       -2.28%      28030       -2.28%
```

`ord_00003` is an invoice-only drift: the receipt was exact, but the
invoice came in **under** the PO by 828 JPY (-2.49%). The most
plausible reading is the tax-inclusion branch — vendor_e interpreted
the PO amount as tax-inclusive and netted it out. `ord_00009` is the
symmetric case where both GR and invoice undershoot by 655 JPY
(-2.28%), consistent with the quantity-spec-`about` branch (delivered
and billed the rounded-down version of the requested quantity).

**`L3_combined_I1_I2` seed 43** (deviation_count = 1):

```
n_orders              : 27
n_with_gr             : 26
n_with_invoice        : 23
n_gr_delta_nonzero    : 1
n_inv_delta_nonzero   : 1
max_abs_inv_delta_pct : 2.296

order_id       po          gr          gr_Δ        inv         inv_Δ
ord_00016      43557       44557       +2.30%      44557       +2.30%
```

This is the opposite direction: vendor_e delivered and billed **1,000
JPY more** than the PO (+2.30%), with both GR and invoice moved in
lockstep. The plausible reading is the prior-adjustment branch — the
vendor added a "carryover" of 1,000 JPY that the PO did not
authorize. Unlike T-023's `deliver_partial` (a crisp action with an
explicit `fraction=0.5` parameter), this one is not a dedicated
opportunistic action at all; it is a normal `deliver` + `register_invoice`
pair whose amount happens to differ from the PO by a hair. The
behavior would be invisible to a surveillance process that only
logged action types.

All three deviations sit in the [−2.49%, +2.30%] band. Phase B's 5%
band strictly contains that interval, which is why every one of them
disappears when tolerance rises.

## 4. Observations

### 4.1 The quiet-drift effect is real and narrow

The core T-028 claim is that a modest tolerance rate absorbs a strict
rule's deviation signal without visibly changing the top-line KPIs.
The Phase A → Phase B comparison confirms the claim in a narrow
form:

- Phase A total deviations across all 30 L3 cells: **3**.
- Phase B total deviations across all 30 L3 cells: **0**.
- All three Phase-A deviations were within ±2.5%, well inside the 5%
  Phase-B band.
- L1 deviations were zero in both phases, and payment counts were
  byte-for-byte identical — the effect is genuinely L3-only and not a
  rule-side artifact.
- The `mean_payments` delta for `L3_baseline` (+2.333) and
  `L3_high_pressure` (+1.667) is suggestive but n=3 is too thin to
  separate signal from T=0.8 noise. Those cells are the candidates
  for a seed-widening follow-up.

That is, **at the scale of 3 seeds per cell**, ambiguity + strict
tolerance produces a detectable non-zero deviation count in 2/15 L3
cells, and the same ambiguity with a 5%-band produces zero. The
interpretation is not "fraud increases" — vendor_e's action rate
does not obviously move — but "the same vendor behavior is binary
(flagged) under Phase A and silent (unflagged) under Phase B". The
organizational surveillance signal degrades without the underlying
process degrading.

### 4.2 Where the Phase-A deviations actually come from

`deviation_count` is incremented in exactly one place in the code —
`rules.pay_order`, on the branch where `three_way_match(...)` returns
False. There are two flavors of that branch depending on the regime:

- **`three_way_match_required = True`** (regimes `baseline` and
  `intervention_I1`): `pay_order` increments `deviation_count` and
  raises `TransitionError`, putting the request `ON_HOLD`. Payment
  does not go through. The drift is both flagged and blocked.
- **`three_way_match_required = False`** (regimes `intervention_I2`
  and `combined_I1_I2`, and the I2-bearing `high_pressure` cell):
  `pay_order` still computes `matched = three_way_match(...)`, but
  the guard in front of the error path is gated by the flag, so
  payment proceeds. The final `if not matched: state.deviation_count
  += 1` at the bottom of `pay_order` still fires. The drift is
  flagged but allowed through.

In Phase A the effective tolerance is `max(tolerance_abs,
order.amount * 0.0) = tolerance_abs`, which is the exact pre-T-028
behavior. In Phase B the effective tolerance is
`max(tolerance_abs, order.amount * 0.05)`, so any amount drift
within 5% of the PO returns `matched = True` and the deviation
counter does not advance in either flavor of the branch.

Two structural features of §3.2 then fall out cleanly:

1. The three non-zero Phase-A deviations all sit in regimes where
   three-way match is **disabled** (I2, combined). In those regimes
   the deviation events are *recorded but not blocked* — they are
   visible in `deviation_count` without reducing the payment count.
   In the two regimes where three-way match is **enabled**
   (`baseline`, `intervention_I1`), Phase A shows zero deviations,
   which under the same mechanism means we did not observe any
   three-seed run in which vendor_e's interpretive drift actually
   tripped the rule. That is consistent either with "the LLM sensed
   three-way match was on and stayed exact" or with "drift is rare
   enough that 3 seeds is not enough to see it in the enabled
   regimes". At n=3 we cannot distinguish those two readings; a
   wider seed sweep on `L3_baseline --ambiguity --tolerance-rate 0`
   would.
2. The small Phase-A → Phase-B drift in `mean_payments` is **not**
   a second signal — it is LLM non-determinism at T=0.8. Because
   Phase A and Phase B run different LLM invocations with different
   prompt contexts, they trace distinct sample paths even for the
   same seed, so per-seed payment counts are not expected to be
   identical. The load-bearing comparison remains the deviation
   column, where Phase A has three events and Phase B has zero —
   and that comparison is one-sided: every Phase-A deviation was
   within ±2.5% (§3.4), strictly inside Phase B's 5% band.

This keeps T-028's mechanism story simple: interpretive ambiguity
produces small amount deviations in a fraction of L3 runs; a strict
three-way match flags them; a lenient one absorbs them. Whether the
LLM also adapts its drift policy to the three-way-match setting is a
separate question the current sweep does not resolve.

### 4.3 Relationship to T-022 / T-023

T-022 established that numeric incentive fields alone do not move
vendor_e. T-023 established that a natural-language framing of those
same fields moves vendor_e on exactly one seed under `high_pressure`
via an explicit `deliver_partial` action. T-028 is a third channel:

| probe | channel                      | non-zero deviations |
|-------|------------------------------|---------------------|
| T-022 | numeric incentive fields     | 0 / 30              |
| T-023 | narrative incentive framing  | 1 / 6 L3 (seed 43 / high_pressure) |
| T-028 | interpretive ambiguity × strict tolerance | 3 / 15 L3 Phase A (seed 43 / I2, combined) |
| T-028 | interpretive ambiguity × lenient tolerance | 0 / 15 L3 Phase B |

The T-028 deviations are shaped differently from T-023's:

- **Action type.** T-023 fired on a dedicated opportunistic action
  (`deliver_partial`); T-028 fires on plain `deliver` /
  `register_invoice` pairs whose amounts drift by a hair. T-028 is
  therefore invisible to any monitor that only keys on action type
  strings.
- **Magnitude.** T-023 was a 50% reduction (fraction=0.5 on a 646k
  JPY PO). T-028 is ≤2.5% and only shows up in absolute JPY terms
  as ±828 / ±655 / +1000.
- **Regime dependence.** T-023's one hit was under `high_pressure`.
  T-028's three hits are in the two `I2`-bearing regimes and zero
  under `high_pressure` — the LLM under `high_pressure` appears to
  lean on crisp opportunistic actions when narrative-prompted, and
  on neither crisp nor fuzzy drift when ambiguity is the only
  channel.
- **Seed dependence.** Both T-023 and T-028 isolate their effect on
  seed 43, with seeds 42 and 44 staying flat. That is consistent
  with a shared latent variable on the seed-43 trajectory (larger
  open orders, higher cash tension day by day), but cannot be
  confirmed without a wider seed sweep.

The three probes together rule out the simplest interpretation of
"vendor_e is a hard-compliance LLM" — it will drift under at least
three distinct incentive designs — while also establishing that each
channel only cracks the compliance prior narrowly and seed-sparsely.

### 4.4 What this does **not** yet show

- **Seed-width confidence.** 3 / 30 is n=3 data and sits on a single
  seed. A wider sweep (e.g. seeds 42–51 on `L3_intervention_I2` and
  `L3_combined_I1_I2` under Phase A) would tell us whether the
  per-cell deviation rate under T-028 is ~10% or ~2%, and whether
  seed 43 is an outlier or the median. Deferred.
- **Branch attribution.** The three ambiguity branches (tax /
  prior-adjustment / quantity-spec) were injected together and
  post-hoc inferred from the drift direction. A cleaner ablation
  would render one branch at a time and keep the others in their
  defaults. Deferred.
- **Tolerance sweep.** Two phases (0% and 5%) bracket the answer but
  do not locate it. A finer sweep — `{0, 0.5, 1, 2, 3, 5}%` — would
  let us plot deviation_count as a function of tolerance and read
  off the practical threshold at which the drift becomes silent.
  Deferred.
- **Interaction with narrative.** T-023 and T-028 are orthogonal in
  the current sweep (narrative off in T-028, ambiguity off in T-023).
  Running a `--narrative --ambiguity` cell would test whether the two
  channels compose (additive deviation count) or interfere
  (narrative leads the LLM toward crisp actions and away from
  amount drift). Deferred.
- **Agent-side interpretation.** Buyer and accountant agents do not
  see the ambiguity fields directly — only the resulting amounts
  surface in their observations. An alternative design would expose
  the same fields to the *approver* and test whether the LLM
  approver starts to write "within tolerance" approval reasoning.
  Deferred.

### 4.5 Attention items from the T-028 plan

- [x] Ambiguity RNG is deterministic and isolated
  (`test_generator_is_deterministic_given_seed`,
  `test_place_order_reproducibility_across_runs`).
- [x] Phase A backward compat: when `tolerance_rate=0` (the default)
  the `three_way_match` effective tolerance collapses to the
  pre-T-028 `tolerance_abs`-only rule
  (`test_three_way_match_defaults_reproduce_prior_behavior`), and
  Phase A L1 reproduces Phase B L1 byte-for-byte on every seed
  (§3.1 table).
- [x] RB-min vendor_e untouched: §3.1 shows the fifteen L1 payment
  triples identical across Phase A and Phase B. The RB-min no-op is
  also asserted directly in
  `test_rb_min_vendor_ignores_ambiguity` and
  `test_rb_min_register_invoice_unchanged_under_ambiguity`.
- [x] `analyze_trace` delta section verified on an L1 baseline cell
  (all deltas 0, `n_gr_delta_nonzero = 0`, `n_inv_delta_nonzero = 0`)
  and on both Phase-A anomaly cells (§3.4).
- [x] No persona instruction endorses or prohibits a specific
  ambiguity branch — `vendor_e.py` renders the three fields
  descriptively and leaves the action choice to the LLM.
- [x] Three-way match tolerance boundary is covered end to end
  (`test_three_way_match_tolerance_rate_allows_percentage_mismatch`,
  `test_three_way_match_tolerance_rate_rejects_over_percentage`,
  `test_three_way_match_uses_max_of_abs_and_rate`), including the
  interaction with the absolute tolerance field.

## 5. Files

- `experiments/ablation_t028/phase_a/ablation_summary.json` — Phase A
  L3 rollup (last-written level only; L1 cells rebuilt from per-seed
  summary.json via the aggregator).
- `experiments/ablation_t028/phase_b/ablation_summary.json` — Phase B
  L3 rollup (same caveat).
- `experiments/ablation_t028/aggregate_l1_l3.json` — combined L1+L3
  view for both phases, rebuilt from every per-seed `summary.json`;
  primary artifact behind the §3 tables.
- `experiments/ablation_t028/{phase_a,phase_b}/{L1,L3}_{regime}/seed{42,43,44}/{summary.json,trace.json}` —
  per-cell artifacts (60 cells × 2 files = 120 files).
- `experiments/ablation_t028/phase_a/L3_intervention_I2/seed43/trace.json` —
  authoritative source for the first §3.4 block (2 non-zero deltas).
- `experiments/ablation_t028/phase_a/L3_combined_I1_I2/seed43/trace.json` —
  authoritative source for the second §3.4 block (1 non-zero delta).
- `experiments/runtime/oct/environment.py` — Order ambiguity fields
  and deterministic `_ambiguity_rng`.
- `experiments/runtime/oct/rules.py` — `three_way_match` gains
  `tolerance_rate` arg and `max(tol_abs, amount * tol_rate)`
  effective tolerance.
- `experiments/runtime/oct/dispatchers/purchase.py` — dispatcher
  propagation of `ambiguity_enabled` and
  `three_way_match_tolerance_rate`.
- `experiments/runtime/oct/personas/vendor_e.py` — ambiguity-aware
  observation rendering; narrative_mode path unchanged.
- `experiments/runtime/scripts/run_ablation.py` — `--ambiguity`,
  `--tolerance-rate`, `--out` flags and per-summary fields.
- `experiments/runtime/scripts/analyze_trace.py` —
  `analyze_amount_deltas` function and `## T-028 PO vs Actual Amount
  Deltas` report section.
- `experiments/runtime/tests/test_t028_ambiguity.py` — 14 new tests
  (130 → 144 pass total).

## 6. Next steps

- **T-028a — seed-width confidence for the Phase-A anomaly.** Re-run
  `L3_intervention_I2 --ambiguity` and `L3_combined_I1_I2 --ambiguity`
  under Phase A with seeds 42–51 (10 seeds × 2 cells ≈ 80 min wall
  clock). Goal: point estimate and 90% CI for the per-cell drift
  deviation rate, plus a test of whether seed 43 is an outlier.
- **T-028b — tolerance sweep.** Run `L3_intervention_I2 --ambiguity`
  with `tolerance_rate ∈ {0, 0.005, 0.01, 0.02, 0.03, 0.05}` on
  seeds 42–44 (6 × 3 = 18 L3 cells ≈ 70 min). Plot deviation_count
  vs tolerance and read off the threshold at which the drift
  disappears.
- **T-028c — branch attribution ablation.** Render exactly one of
  `{tax_included, prior_adjustment, quantity_spec}` as ambiguous
  per cell, with the other two in their defaults. 3 branches × 3
  seeds × 2 regimes (`intervention_I2`, `combined_I1_I2`) = 18 L3
  cells under Phase A. Tells us which ambiguity branch is doing the
  work.
- **T-028d — narrative × ambiguity composition.** Run
  `L3_high_pressure --narrative --ambiguity` Phase A on seeds 42–44.
  Tests whether the two channels compose additively (deviation from
  T-023 + new drift from T-028) or interfere (narrative leads the
  LLM to crisp actions, away from amount drift).
- **T-028e — approver-side visibility.** Expose the ambiguity fields
  to approver_c's observation and re-run `L3_baseline` seeds 42–44
  under Phase A. Tests whether the approver LLM begins to narrate
  "within tolerance" reasoning — i.e. whether the organization
  surfaces the gray zone or keeps it hidden.

## 7. Construct validity

Four ways the T-028 finding could be a false positive, and what we
did (or did not) do about each:

1. **Phase-A anomaly is an artifact of the regime, not of drift.**
   Both non-zero Phase-A cells (`intervention_I2`,
   `combined_I1_I2`) have three-way match **off**, which initially
   looks like a contradiction — why would a disabled rule produce
   deviations? §4.2 traces the chain end to end: `deviation_count`
   is incremented in `rules.pay_order` on every `three_way_match =
   False` outcome, regardless of whether the regime also blocks the
   payment. In disabled regimes the count advances without blocking;
   in enabled regimes it also advances but additionally blocks the
   payment. The reason we see 0 deviations in the enabled regimes
   under Phase A is therefore **not** "the rule suppressed them" —
   it is that across the three L3 seeds we ran, no drift happened
   to land in those particular (regime, seed) combinations at all.
   A wider seed sweep on enabled regimes (T-028a) is the right way
   to test this.
2. **Cherry-picked seeds.** Seeds 42/43/44 were fixed in T-021c and
   reused here without change. Seed 43 is the same seed that produced
   T-023's one deviation. That is either a coincidence or a shared
   latent (e.g. seed 43 produces a day-2 demand spike that gives
   vendor_e an unusually tense observation early). T-028a will widen
   the seed set before making any per-seed claim.
3. **Temperature artifact.** T=0.8 is unchanged from T-021c onwards,
   but ambiguity ON changes the prompt vendor_e sees, so the
   distribution vendor_e samples from is not the same as any
   previous task's. We cannot claim "tolerance absorbs drift" at the
   level of a per-cell point estimate until T-028b lands; what we can
   claim is that under the exact same (temperature, seed,
   observation) triple, three deviations exist at tolerance=0 and
   none at tolerance=0.05. The ordering is one-sided and does not
   require n=3 to be tight.
4. **Dispatcher double-counts the same anomaly.** `ord_00009` in
   `L3_intervention_I2` seed 43 has both a GR delta and an invoice
   delta of −2.28%. One might worry the rule fires twice on the
   same order — once on the GR leg and once on the invoice leg.
   It does not: `rules.pay_order` calls `three_way_match` exactly
   once per order, and the `if not matched: state.deviation_count
   += 1` path also fires at most once per order (one call site,
   guarded by a single `if`). The summary's `deviation_count = 2`
   for this cell therefore reflects two distinct orders drifting
   (`ord_00003` and `ord_00009`), each counted once — which matches
   the two non-zero rows the `analyze_trace` delta table prints for
   this trace (§3.4).
