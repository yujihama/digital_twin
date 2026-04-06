"""T-012: Layer 3 interaction-blocking test.

Runs 4 experiments (baseline/intervention x full/isolated) to determine
whether emergent events arise from inter-agent interaction or from
individual agent behavior.

Usage (from experiments/runtime/ with venv activated):
    python scripts/run_layer3.py

Outputs:
    - experiments/layer3_t012/{tag}/trace.json
    - experiments/layer3_t012/{tag}/summary.json
    - experiments/layer3_t012/all_summaries.json
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

from oct.dispatchers.purchase import PurchaseDispatcher
from oct.environment import EnvironmentState
from oct.llm import OpenAIClient
from oct.personas.accountant_d import make_agent as make_accountant_d
from oct.personas.approver_c import make_agent as make_approver_c
from oct.personas.buyer_a import make_agent as make_buyer_a
from oct.personas.buyer_b import make_agent as make_buyer_b
from oct.personas.vendor_e import make_agent as make_vendor_e
from oct.rules import DemandConfig
from oct.runner import run_simulation

# Fixed parameters
MODEL = "gpt-4.1-mini"
MAX_DAYS = 20
TEMPERATURE = 0.8
RNG_SEED = 42
ACTIONS_PER_AGENT_PER_DAY = 2
DEMAND_RNG_SEED = 42
MEAN_DAILY_DEMANDS = 1.5

OUTPUT_BASE = Path(__file__).resolve().parents[2] / "layer3_t012"


EXPERIMENTS = [
    {"threshold": 200_000,   "isolated": False, "tag": "baseline_full"},
    {"threshold": 200_000,   "isolated": True,  "tag": "baseline_isolated"},
    {"threshold": 5_000_000, "isolated": False, "tag": "intervention_full"},
    {"threshold": 5_000_000, "isolated": True,  "tag": "intervention_isolated"},
]


def run_single(threshold: int, isolated: bool, tag: str) -> dict:
    out_dir = OUTPUT_BASE / tag
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*60}", file=sys.stderr)
    print(f"  {tag}: threshold={threshold:,}, isolated={isolated}, "
          f"seed={RNG_SEED}", file=sys.stderr)
    print(f"{'='*60}", file=sys.stderr)

    state = EnvironmentState(current_day=0)
    state.controls.approval_threshold = threshold

    demand_config = DemandConfig(mean_daily_demands=MEAN_DAILY_DEMANDS)
    dispatcher = PurchaseDispatcher(
        state,
        demand_config=demand_config,
        demand_rng_seed=DEMAND_RNG_SEED,
        isolated_mode=isolated,
    )
    agents = [
        make_buyer_a(), make_buyer_b(), make_approver_c(),
        make_accountant_d(), make_vendor_e(),
    ]
    llm = OpenAIClient(model=MODEL)

    t0 = time.time()
    trace = run_simulation(
        env=dispatcher, agents=agents, llm=llm,
        max_days=MAX_DAYS, temperature=TEMPERATURE,
        shuffle_agents=True, rng_seed=RNG_SEED,
        actions_per_agent_per_day=ACTIONS_PER_AGENT_PER_DAY,
    )
    elapsed = time.time() - t0

    # Save trace
    trace_path = out_dir / "trace.json"
    trace_path.write_text(
        json.dumps(trace.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    # Build summary
    snap = trace.final_snapshot or {}
    counts = snap.get("counts", {})
    per_agent = {}
    for step in trace.steps:
        action_type = step.action.action_type if step.action else "(none)"
        per_agent.setdefault(step.agent_id, {}).setdefault(action_type, 0)
        per_agent[step.agent_id][action_type] += 1

    agent_waits = {a: acts.get("wait", 0) for a, acts in per_agent.items()}
    errors = [{"day": e.day, "agent_id": e.agent_id, "error": str(e.error)[:200]}
              for e in trace.errors()]

    summary = {
        "tag": tag, "threshold": threshold, "isolated": isolated,
        "rng_seed": RNG_SEED, "demand_seed": DEMAND_RNG_SEED,
        "model": MODEL, "temperature": TEMPERATURE, "max_days": MAX_DAYS,
        "elapsed_seconds": round(elapsed, 1),
        "api_calls": llm.call_count,
        "total_steps": len(trace.steps),
        "counts": counts, "errors": errors,
        "per_agent": per_agent, "agent_waits": agent_waits,
        "deviation_count": snap.get("deviation_count", 0),
    }

    (out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n--- {tag} SUMMARY ---", file=sys.stderr)
    print(f"  elapsed   : {elapsed:.1f}s", file=sys.stderr)
    print(f"  requests  : {counts.get('purchase_requests', 0)}", file=sys.stderr)
    print(f"  approvals : {counts.get('approvals', 0)}", file=sys.stderr)
    print(f"  payments  : {counts.get('payments', 0)}", file=sys.stderr)
    print(f"  errors    : {len(errors)}", file=sys.stderr)
    print(f"  deviation : {snap.get('deviation_count', 0)}", file=sys.stderr)

    return summary


def main() -> int:
    if not os.environ.get("OPENAI_API_KEY"):
        print("ERROR: OPENAI_API_KEY is not set", file=sys.stderr)
        return 1

    OUTPUT_BASE.mkdir(parents=True, exist_ok=True)
    all_summaries = []

    for i, exp in enumerate(EXPERIMENTS, 1):
        print(f"\n[{i}/{len(EXPERIMENTS)}] {exp['tag']}", file=sys.stderr)
        s = run_single(exp["threshold"], exp["isolated"], exp["tag"])
        all_summaries.append(s)

    # Save combined
    combined = OUTPUT_BASE / "all_summaries.json"
    combined.write_text(
        json.dumps(all_summaries, ensure_ascii=False, indent=2),
        encoding="utf-8")

    print(f"\n{'='*60}", file=sys.stderr)
    print(f"All {len(EXPERIMENTS)} experiments complete.", file=sys.stderr)
    print(f"{'='*60}", file=sys.stderr)

    # Comparison table
    print("\n--- COMPARISON TABLE ---", file=sys.stderr)
    hdr = f"{'Tag':<30s} {'Req':>4s} {'Appr':>5s} {'Pay':>4s} {'Err':>4s} {'Dev':>4s} {'Time':>6s}"
    print(hdr, file=sys.stderr)
    print("-" * len(hdr), file=sys.stderr)
    for s in all_summaries:
        c = s["counts"]
        print(f"{s['tag']:<30s} {c.get('purchase_requests',0):>4d} "
              f"{c.get('approvals',0):>5d} {c.get('payments',0):>4d} "
              f"{len(s['errors']):>4d} {s['deviation_count']:>4d} "
              f"{s['elapsed_seconds']:>6.1f}s", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
