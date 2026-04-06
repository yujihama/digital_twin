"""exp005: I2介入実験 — 三者照合無効化（S-005の反証テスト）.

研究上の目的:
  S-005（全条件でdeviation_count=0）が「LLMの行動バイアス（コンプライアンス
  従順傾向）」なのか「三者照合という統制が品質を維持している因果効果」なのかを
  判別する。

実験設計:
  exp005a（ベースライン）: three_way_match_required=True, approval_threshold=200k
  exp005b（介入）: three_way_match_required=False, approval_threshold=200k
    → 三者照合のみを無効化し、その他は同一条件

LLMモデル: gpt-4.1-mini（既存実験との連続性を維持。gpt-5.4-miniへの切替えは
  モデル可用性確認後に実施）

Usage (from experiments/runtime/ with venv activated):
    python scripts/run_exp005.py            # 両方実行
    python scripts/run_exp005.py --baseline # exp005aのみ
    python scripts/run_exp005.py --intervention # exp005bのみ

Outputs:
    - experiments/exp005_three_way_match/exp005a_baseline/trace.json
    - experiments/exp005_three_way_match/exp005b_intervention/trace.json
    - experiments/exp005_three_way_match/exp005a_baseline/summary.json
    - experiments/exp005_three_way_match/exp005b_intervention/summary.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List

RUNTIME_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RUNTIME_DIR))


def _load_dotenv() -> None:
    """Minimal .env loader (no external dep): KEY=VALUE lines, # comments."""
    env_path = RUNTIME_DIR / ".env"
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv()

from oct.dispatchers.purchase import PurchaseDispatcher  # noqa: E402
from oct.environment import EnvironmentState  # noqa: E402
from oct.llm import OpenAIClient  # noqa: E402
from oct.personas.accountant_d import make_agent as make_accountant_d  # noqa: E402
from oct.personas.approver_c import make_agent as make_approver_c  # noqa: E402
from oct.personas.buyer_a import make_agent as make_buyer_a  # noqa: E402
from oct.personas.buyer_b import make_agent as make_buyer_b  # noqa: E402
from oct.personas.vendor_e import make_agent as make_vendor_e  # noqa: E402
from oct.rules import DemandConfig  # noqa: E402
from oct.runner import SimulationTrace, run_simulation  # noqa: E402

# ---- Shared experiment parameters (identical to exp003c) ----
MODEL = "gpt-4.1-mini"
MAX_DAYS = 20
TEMPERATURE = 0.8
RNG_SEED = 42
ACTIONS_PER_AGENT_PER_DAY = 2
DEMAND_RNG_SEED = 42
MEAN_DAILY_DEMANDS = 1.5
APPROVAL_THRESHOLD = 200_000  # exp003c相当

OUTPUT_ROOT = Path(__file__).resolve().parents[2] / "exp005_three_way_match"


@dataclass
class ExperimentConfig:
    experiment_id: str
    three_way_match_required: bool
    model: str = MODEL
    max_days: int = MAX_DAYS
    temperature: float = TEMPERATURE
    rng_seed: int = RNG_SEED
    actions_per_agent_per_day: int = ACTIONS_PER_AGENT_PER_DAY
    demand_rng_seed: int = DEMAND_RNG_SEED
    mean_daily_demands: float = MEAN_DAILY_DEMANDS
    approval_threshold: float = APPROVAL_THRESHOLD


def run_experiment(config: ExperimentConfig) -> Dict[str, Any]:
    """Run a single experiment and return summary dict."""
    output_dir = OUTPUT_ROOT / config.experiment_id
    output_dir.mkdir(parents=True, exist_ok=True)

    state = EnvironmentState(current_day=0)
    state.controls.approval_threshold = config.approval_threshold
    state.controls.three_way_match_required = config.three_way_match_required

    demand_config = DemandConfig(mean_daily_demands=config.mean_daily_demands)
    dispatcher = PurchaseDispatcher(
        state,
        demand_config=demand_config,
        demand_rng_seed=config.demand_rng_seed,
    )
    agents = [
        make_buyer_a(),
        make_buyer_b(),
        make_approver_c(),
        make_accountant_d(),
        make_vendor_e(),
    ]
    llm = OpenAIClient(model=config.model)

    print(
        f"\n{'='*60}\n"
        f"Starting {config.experiment_id}\n"
        f"  model={config.model}, agents={len(agents)}, days={config.max_days}\n"
        f"  temp={config.temperature}, seed={config.rng_seed}\n"
        f"  approval_threshold={config.approval_threshold:,.0f}\n"
        f"  three_way_match_required={config.three_way_match_required}\n"
        f"{'='*60}",
        file=sys.stderr,
    )

    trace = run_simulation(
        env=dispatcher,
        agents=agents,
        llm=llm,
        max_days=config.max_days,
        temperature=config.temperature,
        shuffle_agents=True,
        rng_seed=config.rng_seed,
        actions_per_agent_per_day=config.actions_per_agent_per_day,
    )

    # Save trace
    trace_path = output_dir / "trace.json"
    trace_path.write_text(
        json.dumps(trace.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # Build summary
    summary = _build_summary(config, trace, state, llm.call_count)

    # Save summary
    summary_path = output_dir / "summary.json"
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # Print summary to stderr
    _print_summary(config, trace, state, llm.call_count)

    return summary


def _build_summary(
    config: ExperimentConfig,
    trace: SimulationTrace,
    state: EnvironmentState,
    api_calls: int,
) -> Dict[str, Any]:
    """Build structured summary dict for analysis."""
    snap = trace.final_snapshot or {}
    counts = snap.get("counts", {})

    # Per-agent action breakdown
    per_agent: Dict[str, Dict[str, int]] = {}
    for step in trace.steps:
        action_type = step.action.action_type if step.action else "(none)"
        per_agent.setdefault(step.agent_id, {}).setdefault(action_type, 0)
        per_agent[step.agent_id][action_type] += 1

    # Approval details
    approvals = []
    for s in trace.steps:
        if s.action and s.action.action_type in ("approve_request", "reject_request"):
            approvals.append({
                "day": s.day,
                "agent_id": s.agent_id,
                "action_type": s.action.action_type,
                "request_id": s.action.parameters.get("request_id"),
                "decision": s.action.parameters.get("decision", "rejected"),
                "note": s.action.parameters.get("note", ""),
            })

    # Three-way match analysis
    three_way_matched_count = sum(1 for p in state.payments if p.three_way_matched)
    three_way_unmatched_count = len(state.payments) - three_way_matched_count

    # Invoice-order amount comparison (vendor behavior analysis)
    invoice_deviations = []
    for inv in state.invoices:
        order = state.get_order(inv.order_id)
        if order:
            diff = inv.amount - order.amount
            if diff != 0:
                invoice_deviations.append({
                    "invoice_id": inv.id,
                    "order_id": inv.order_id,
                    "order_amount": order.amount,
                    "invoice_amount": inv.amount,
                    "deviation": diff,
                })

    # Receipt-order amount comparison
    receipt_deviations = []
    for rcp in state.receipts:
        order = state.get_order(rcp.order_id)
        if order:
            diff = rcp.delivered_amount - order.amount
            if diff != 0:
                receipt_deviations.append({
                    "receipt_id": rcp.id,
                    "order_id": rcp.order_id,
                    "order_amount": order.amount,
                    "delivered_amount": rcp.delivered_amount,
                    "deviation": diff,
                })

    return {
        "experiment_id": config.experiment_id,
        "config": {
            "model": config.model,
            "max_days": config.max_days,
            "temperature": config.temperature,
            "rng_seed": config.rng_seed,
            "approval_threshold": config.approval_threshold,
            "three_way_match_required": config.three_way_match_required,
            "actions_per_agent_per_day": config.actions_per_agent_per_day,
            "demand_rng_seed": config.demand_rng_seed,
            "mean_daily_demands": config.mean_daily_demands,
        },
        "results": {
            "total_steps": len(trace.steps),
            "dispatched_ok": len(trace.dispatched_actions()),
            "errors": len(trace.errors()),
            "api_calls": api_calls,
            "deviation_count": state.deviation_count,
            "error_count": state.error_count,
        },
        "pipeline_counts": counts,
        "per_agent_actions": per_agent,
        "approval_details": approvals,
        "three_way_match": {
            "matched": three_way_matched_count,
            "unmatched": three_way_unmatched_count,
            "total_payments": len(state.payments),
        },
        "vendor_behavior": {
            "invoice_deviations": invoice_deviations,
            "receipt_deviations": receipt_deviations,
            "invoice_deviation_count": len(invoice_deviations),
            "receipt_deviation_count": len(receipt_deviations),
        },
    }


def _print_summary(
    config: ExperimentConfig,
    trace: SimulationTrace,
    state: EnvironmentState,
    api_calls: int,
) -> None:
    """Print human-readable summary to stderr."""
    snap = trace.final_snapshot or {}
    counts = snap.get("counts", {})

    print(f"\n--- SUMMARY ({config.experiment_id}) ---", file=sys.stderr)
    print(f"total_steps             : {len(trace.steps)}", file=sys.stderr)
    print(f"dispatched_ok           : {len(trace.dispatched_actions())}", file=sys.stderr)
    print(f"errors                  : {len(trace.errors())}", file=sys.stderr)
    print(f"api_calls               : {api_calls}", file=sys.stderr)
    print(f"deviation_count         : {state.deviation_count}", file=sys.stderr)
    print(f"three_way_match_required: {config.three_way_match_required}", file=sys.stderr)

    print(f"\n--- PIPELINE COUNTS ---", file=sys.stderr)
    for key in ["purchase_requests", "approvals", "orders", "receipts", "invoices", "payments"]:
        print(f"  {key:20s}: {counts.get(key, 0)}", file=sys.stderr)

    # Three-way match analysis
    matched = sum(1 for p in state.payments if p.three_way_matched)
    total = len(state.payments)
    print(f"\n--- THREE-WAY MATCH ---", file=sys.stderr)
    print(f"  matched/total         : {matched}/{total}", file=sys.stderr)

    # Invoice deviations (vendor behavior)
    deviations = 0
    for inv in state.invoices:
        order = state.get_order(inv.order_id)
        if order and inv.amount != order.amount:
            deviations += 1
    print(f"\n--- VENDOR BEHAVIOR (S-005) ---", file=sys.stderr)
    print(f"  invoice_deviations    : {deviations}", file=sys.stderr)
    print(f"  deviation_count       : {state.deviation_count}", file=sys.stderr)

    # Per-agent action breakdown
    per_agent: Dict[str, Dict[str, int]] = {}
    for step in trace.steps:
        action_type = step.action.action_type if step.action else "(none)"
        per_agent.setdefault(step.agent_id, {}).setdefault(action_type, 0)
        per_agent[step.agent_id][action_type] += 1
    print(f"\n--- PER-AGENT ACTIONS ---", file=sys.stderr)
    for aid, act_counts in sorted(per_agent.items()):
        print(f"  {aid:14s}: {act_counts}", file=sys.stderr)

    # Errors sample
    errs = trace.errors()
    if errs:
        print(f"\n--- ERRORS (up to 10) ---", file=sys.stderr)
        for s in errs[:10]:
            print(f"  day={s.day} {s.agent_id}: {s.error}", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(description="exp005: I2 three-way match intervention")
    parser.add_argument("--baseline", action="store_true", help="Run exp005a only")
    parser.add_argument("--intervention", action="store_true", help="Run exp005b only")
    args = parser.parse_args()

    if not os.environ.get("OPENAI_API_KEY"):
        print("ERROR: OPENAI_API_KEY is not set", file=sys.stderr)
        return 1

    run_baseline = args.baseline or (not args.baseline and not args.intervention)
    run_intervention = args.intervention or (not args.baseline and not args.intervention)

    summaries = []

    if run_baseline:
        config_a = ExperimentConfig(
            experiment_id="exp005a_baseline",
            three_way_match_required=True,
        )
        summaries.append(run_experiment(config_a))

    if run_intervention:
        config_b = ExperimentConfig(
            experiment_id="exp005b_intervention",
            three_way_match_required=False,
        )
        summaries.append(run_experiment(config_b))

    # If both were run, save combined summary
    if len(summaries) == 2:
        combined_path = OUTPUT_ROOT / "comparison.json"
        a, b = summaries
        comparison = {
            "experiment": "exp005_three_way_match",
            "research_question": "S-005: Is deviation_count=0 due to LLM compliance bias or three-way match control?",
            "baseline": a,
            "intervention": b,
            "diff": {
                "deviation_count": b["results"]["deviation_count"] - a["results"]["deviation_count"],
                "invoice_deviations": b["vendor_behavior"]["invoice_deviation_count"] - a["vendor_behavior"]["invoice_deviation_count"],
                "receipt_deviations": b["vendor_behavior"]["receipt_deviation_count"] - a["vendor_behavior"]["receipt_deviation_count"],
                "three_way_unmatched_diff": b["three_way_match"]["unmatched"] - a["three_way_match"]["unmatched"],
                "payments_diff": b["pipeline_counts"].get("payments", 0) - a["pipeline_counts"].get("payments", 0),
            },
        }
        combined_path.write_text(
            json.dumps(comparison, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        print(f"\n{'='*60}", file=sys.stderr)
        print("COMPARISON: exp005a (baseline) vs exp005b (intervention)", file=sys.stderr)
        print(f"{'='*60}", file=sys.stderr)
        for key, val in comparison["diff"].items():
            direction = "+" if val > 0 else ("" if val == 0 else "")
            print(f"  {key:30s}: {direction}{val}", file=sys.stderr)

        # Verdict on S-005
        inv_dev = comparison["diff"]["invoice_deviations"]
        dev_cnt = comparison["diff"]["deviation_count"]
        if inv_dev > 0 or dev_cnt > 0:
            print("\n  VERDICT: Three-way match removal CAUSED behavioral change", file=sys.stderr)
            print("  → Supports: Control has causal effect on vendor behavior (OCT value)", file=sys.stderr)
        else:
            print("\n  VERDICT: Three-way match removal had NO effect on vendor behavior", file=sys.stderr)
            print("  → Supports: LLM compliance bias (OCT limitation for S-005)", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
