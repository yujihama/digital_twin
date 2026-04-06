"""exp002: 需要生成ありの5エージェント実行（exp001との比較実験）.

exp001では全エージェントが15日間waitのみだった。本実験ではDemandConfigを
有効化し、環境が確率的に需要イベントを生成することで因果連鎖の起点が発生
するかを検証する。

exp001との差分:
  - PurchaseDispatcher に DemandConfig(mean_daily_demands=1.5) を設定
  - demand_rng_seed=42 で需要生成も再現可能
  - その他のパラメータ（model, max_days, temperature, rng_seed）は同一

Usage (from experiments/runtime/ with venv activated):
    python scripts/run_exp002.py

Outputs:
    - experiments/exp002_demand_driven/trace_seed42.json
    - stderr に実行サマリー
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

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
from oct.runner import run_simulation  # noqa: E402

# ---- Experiment configuration (同一seed, exp001と比較可能) ----
EXPERIMENT_ID = "exp002_demand_driven"
MODEL = "gpt-4.1-mini"
MAX_DAYS = 15
TEMPERATURE = 0.8
RNG_SEED = 42
ACTIONS_PER_AGENT_PER_DAY = 1
DEMAND_RNG_SEED = 42
MEAN_DAILY_DEMANDS = 1.5

OUTPUT_DIR = Path(__file__).resolve().parents[2] / EXPERIMENT_ID
OUTPUT_TRACE = OUTPUT_DIR / f"trace_seed{RNG_SEED}.json"


def main() -> int:
    if not os.environ.get("OPENAI_API_KEY"):
        print("ERROR: OPENAI_API_KEY is not set", file=sys.stderr)
        return 1

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    state = EnvironmentState(current_day=0)
    demand_config = DemandConfig(mean_daily_demands=MEAN_DAILY_DEMANDS)
    dispatcher = PurchaseDispatcher(
        state,
        demand_config=demand_config,
        demand_rng_seed=DEMAND_RNG_SEED,
    )
    agents = [
        make_buyer_a(),
        make_buyer_b(),
        make_approver_c(),
        make_accountant_d(),
        make_vendor_e(),
    ]
    llm = OpenAIClient(model=MODEL)

    print(
        f"Starting {EXPERIMENT_ID}: model={MODEL}, agents={len(agents)}, "
        f"days={MAX_DAYS}, temp={TEMPERATURE}, seed={RNG_SEED}, "
        f"demand_seed={DEMAND_RNG_SEED}, mean_demands={MEAN_DAILY_DEMANDS}",
        file=sys.stderr,
    )

    trace = run_simulation(
        env=dispatcher,
        agents=agents,
        llm=llm,
        max_days=MAX_DAYS,
        temperature=TEMPERATURE,
        shuffle_agents=True,
        rng_seed=RNG_SEED,
        actions_per_agent_per_day=ACTIONS_PER_AGENT_PER_DAY,
    )

    # Save full JSON trace
    OUTPUT_TRACE.write_text(
        json.dumps(trace.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # Short human summary on stderr
    print("\n--- SUMMARY ---", file=sys.stderr)
    print(f"trace_saved         : {OUTPUT_TRACE}", file=sys.stderr)
    print(f"total_steps         : {len(trace.steps)}", file=sys.stderr)
    print(f"dispatched_ok       : {len(trace.dispatched_actions())}", file=sys.stderr)
    print(f"errors              : {len(trace.errors())}", file=sys.stderr)
    print(f"api_call_count      : {llm.call_count}", file=sys.stderr)
    print(f"final_snapshot      : {trace.final_snapshot}", file=sys.stderr)

    # Per-agent action type breakdown
    per_agent: dict = {}
    for step in trace.steps:
        action_type = step.action.action_type if step.action else "(none)"
        per_agent.setdefault(step.agent_id, {}).setdefault(action_type, 0)
        per_agent[step.agent_id][action_type] += 1
    print("\n--- PER-AGENT ACTIONS ---", file=sys.stderr)
    for aid, counts in per_agent.items():
        print(f"{aid:14s}: {counts}", file=sys.stderr)

    # Sample of errors (if any)
    errs = trace.errors()
    if errs:
        print("\n--- SAMPLE ERRORS (up to 5) ---", file=sys.stderr)
        for s in errs[:5]:
            print(f"[day {s.day}] {s.agent_id}: {s.error}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
