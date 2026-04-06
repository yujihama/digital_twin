"""T-016: Multi-seed experiment runner for Layer 2 path-dependency test.

Runs both exp003c (threshold=200k) and exp004 (threshold=5M) with multiple
seeds to verify reproducibility and compute Emergence Ratio variance.

Usage (from experiments/runtime/ with venv activated):
    python scripts/run_multi_seed.py --seeds 43 44 45
    python scripts/run_multi_seed.py --seeds 43 --threshold 200000
    python scripts/run_multi_seed.py --seeds 43 44 45 --threshold 200000 5000000

Outputs per (threshold, seed) pair:
    - experiments/multi_seed_t016/t{threshold}_seed{seed}/trace.json
    - experiments/multi_seed_t016/t{threshold}_seed{seed}/summary.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

RUNTIME_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RUNTIME_DIR))


def _load_dotenv() -> None:
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
from oct.runner import run_simulation  # noqa: E402

# ---- Fixed parameters (identical across all experiments) ----
MODEL = "gpt-4.1-mini"
MAX_DAYS = 20
TEMPERATURE = 0.8
ACTIONS_PER_AGENT_PER_DAY = 2
MEAN_DAILY_DEMANDS = 1.5

OUTPUT_BASE = Path(__file__).resolve().parents[2] / "multi_seed_t016"


def run_single(threshold: int, rng_seed: int, demand_seed: int) -> dict:
    """Run one experiment and return summary dict."""
    tag = f"t{threshold}_seed{rng_seed}"
    out_dir = OUTPUT_BASE / tag
    out_dir.mkdir(parents=True, exist_ok=True)
    trace_path = out_dir / "trace.json"

    print(f"\n{'='*60}", file=sys.stderr)
    print(f"  {tag}: threshold={threshold:,}, rng_seed={rng_seed}, "
          f"demand_seed={demand_seed}", file=sys.stderr)
    print(f"{'='*60}", file=sys.stderr)

    state = EnvironmentState(current_day=0)
    state.controls.approval_threshold = threshold

    demand_config = DemandConfig(mean_daily_demands=MEAN_DAILY_DEMANDS)
    dispatcher = PurchaseDispatcher(
        state,
        demand_config=demand_config,
        demand_rng_seed=demand_seed,
    )
    agents = [
        make_buyer_a(),
        make_buyer_b(),
        make_approver_c(),
        make_accountant_d(),
        make_vendor_e(),
    ]
    llm = OpenAIClient(model=MODEL)

    t0 = time.time()
    trace = run_simulation(
        env=dispatcher,
        agents=agents,
        llm=llm,
        max_days=MAX_DAYS,
        temperature=TEMPERATURE,
        shuffle_agents=True,
        rng_seed=rng_seed,
        actions_per_agent_per_day=ACTIONS_PER_AGENT_PER_DAY,
    )
    elapsed = time.time() - t0

    # Save trace
    trace_path.write_text(
        json.dumps(trace.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    # Build summary
    snap = trace.final_snapshot or {}
    counts = snap.get("counts", {})

    # Per-agent action breakdown
    per_agent: dict = {}
    for step in trace.steps:
        action_type = step.action.action_type if step.action else "(none)"
        agent = step.agent_id
        per_agent.setdefault(agent, {}).setdefault(action_type, 0)
        per_agent[agent][action_type] += 1

    # Per-agent wait counts
    agent_waits = {}
    for agent, acts in per_agent.items():
        agent_waits[agent] = acts.get("wait", 0)

    # Error details
    errors = []
    for e in trace.errors():
        errors.append({
            "day": e.day,
            "agent_id": e.agent_id,
            "error": str(e.error)[:200],
        })

    # Approval details
    approvals = []
    for s in trace.steps:
        if s.action and s.action.action_type == "approve_request":
            approvals.append({
                "day": s.day,
                "agent_id": s.agent_id,
                "request_id": s.action.parameters.get("request_id"),
                "decision": s.action.parameters.get("decision"),
            })

    # Three-way match from snapshot
    three_way = snap.get("three_way_match", {})

    summary = {
        "tag": tag,
        "threshold": threshold,
        "rng_seed": rng_seed,
        "demand_seed": demand_seed,
        "model": MODEL,
        "temperature": TEMPERATURE,
        "max_days": MAX_DAYS,
        "elapsed_seconds": round(elapsed, 1),
        "api_calls": llm.call_count,
        "total_steps": len(trace.steps),
        "counts": counts,
        "approvals": approvals,
        "errors": errors,
        "per_agent": per_agent,
        "agent_waits": agent_waits,
        "three_way_match": three_way,
        "deviation_count": snap.get("deviation_count", 0),
    }

    # Save summary
    summary_path = out_dir / "summary.json"
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    # Print summary to stderr
    print(f"\n--- {tag} SUMMARY ---", file=sys.stderr)
    print(f"  elapsed       : {elapsed:.1f}s", file=sys.stderr)
    print(f"  api_calls     : {llm.call_count}", file=sys.stderr)
    print(f"  requests      : {counts.get('purchase_requests', 0)}", file=sys.stderr)
    print(f"  approvals     : {counts.get('approvals', 0)}", file=sys.stderr)
    print(f"  orders        : {counts.get('orders', 0)}", file=sys.stderr)
    print(f"  payments      : {counts.get('payments', 0)}", file=sys.stderr)
    print(f"  errors        : {len(errors)}", file=sys.stderr)
    print(f"  deviation_cnt : {snap.get('deviation_count', 0)}", file=sys.stderr)
    print(f"  three_way     : {three_way}", file=sys.stderr)

    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="T-016 multi-seed runner")
    parser.add_argument("--seeds", nargs="+", type=int, default=[43, 44, 45])
    parser.add_argument("--thresholds", nargs="+", type=int,
                        default=[200_000, 5_000_000])
    parser.add_argument("--demand-seed", type=int, default=42,
                        help="Fixed demand seed (same across all runs)")
    args = parser.parse_args()

    if not os.environ.get("OPENAI_API_KEY"):
        print("ERROR: OPENAI_API_KEY is not set", file=sys.stderr)
        return 1

    OUTPUT_BASE.mkdir(parents=True, exist_ok=True)

    all_summaries = []
    total = len(args.thresholds) * len(args.seeds)
    i = 0

    for threshold in args.thresholds:
        for seed in args.seeds:
            i += 1
            print(f"\n[{i}/{total}] Running threshold={threshold:,}, seed={seed}",
                  file=sys.stderr)
            summary = run_single(threshold, seed, args.demand_seed)
            all_summaries.append(summary)

    # Save combined results
    combined_path = OUTPUT_BASE / "all_summaries.json"
    combined_path.write_text(
        json.dumps(all_summaries, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    print(f"\n{'='*60}", file=sys.stderr)
    print(f"All {total} experiments complete. Combined: {combined_path}", file=sys.stderr)
    print(f"{'='*60}", file=sys.stderr)

    # Quick comparison table
    print("\n--- COMPARISON TABLE ---", file=sys.stderr)
    print(f"{'Tag':<25s} {'Req':>4s} {'Appr':>5s} {'Pay':>4s} {'Err':>4s} "
          f"{'Dev':>4s} {'Time':>6s}", file=sys.stderr)
    print("-" * 60, file=sys.stderr)
    for s in all_summaries:
        c = s["counts"]
        print(f"{s['tag']:<25s} {c.get('purchase_requests',0):>4d} "
              f"{c.get('approvals',0):>5d} {c.get('payments',0):>4d} "
              f"{len(s['errors']):>4d} {s['deviation_count']:>4d} "
              f"{s['elapsed_seconds']:>6.1f}s", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
