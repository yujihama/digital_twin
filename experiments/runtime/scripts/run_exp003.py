"""exp003: 全購買フロー完遂テスト（vendor_id修正検証）.

exp002ではbuyer→approver→order→receiptまで到達したが、vendor_eは未行動
だった（原因: buyerがLLM生成のvendor IDを使用し、vendor_eとマッチしなかった）。
PR#11で buyer observation に available_vendors フィールドを追加して修正。

exp003の検証目標:
  - buyer が available_vendors から vendor_e を選択すること
  - vendor_e が deliver / register_invoice を実行すること
  - accountant_d が pay_order を実行すること
  - 全フロー (draft→approve→order→deliver→invoice→pay) が少なくとも1件完遂

exp002との差分:
  - EXPERIMENT_ID = "exp003_full_pipeline"
  - MAX_DAYS = 20 (15→20: フロー完遂に必要な日数を確保)
  - ACTIONS_PER_AGENT_PER_DAY = 2 (1→2: vendor_eがdeliver+invoiceを1日で可能に)
  - その他のパラメータ（model, temperature, rng_seed, demand設定）は同一

Usage (from experiments/runtime/ with venv activated):
    python scripts/run_exp003.py

Outputs:
    - experiments/exp003_full_pipeline/trace_seed42.json
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

# ---- Experiment configuration ----
EXPERIMENT_ID = "exp003_full_pipeline"
MODEL = "gpt-4.1-mini"
MAX_DAYS = 20
TEMPERATURE = 0.8
RNG_SEED = 42
ACTIONS_PER_AGENT_PER_DAY = 2  # exp002は1 → vendor_eがdeliver+invoiceを1日で可能に
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
        f"actions_per_day={ACTIONS_PER_AGENT_PER_DAY}, "
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

    # Pipeline completion check
    snap = trace.final_snapshot or {}
    counts = snap.get("counts", {})
    print("\n--- PIPELINE COMPLETION ---", file=sys.stderr)
    print(f"purchase_requests   : {counts.get('purchase_requests', 0)}", file=sys.stderr)
    print(f"approvals           : {counts.get('approvals', 0)}", file=sys.stderr)
    print(f"orders              : {counts.get('orders', 0)}", file=sys.stderr)
    print(f"receipts            : {counts.get('receipts', 0)}", file=sys.stderr)
    print(f"invoices            : {counts.get('invoices', 0)}", file=sys.stderr)
    print(f"payments            : {counts.get('payments', 0)}", file=sys.stderr)
    print(f"demands_fulfilled   : {counts.get('demands_fulfilled', 0)}", file=sys.stderr)

    full_pipeline = counts.get("payments", 0) > 0
    print(
        f"\nFull pipeline (draft→pay) achieved: {'YES' if full_pipeline else 'NO'}",
        file=sys.stderr,
    )

    # Sample of errors (if any)
    errs = trace.errors()
    if errs:
        print(f"\n--- SAMPLE ERRORS (up to 10) ---", file=sys.stderr)
        for s in errs[:10]:
            print(f"[day {s.day}] {s.agent_id}: {s.error}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
