"""Minimum viable T-007 demo: buyer_a × 5 days × AnthropicClient.

Run from `experiments/runtime/` with the venv activated:
    python scripts/demo_buyer_a.py

Requires:
    - ANTHROPIC_API_KEY in environment
    - `anthropic` package installed (see requirements.txt)

Writes a JSON trace to stdout and a short human summary at the end.
The goal is to verify that the environment actually advances state when
driven by a real LLM, so we deliberately keep the scope tiny:
    - 1 agent (buyer_a)
    - 5 days, 1 action per day
    - temperature = 0.8
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Ensure `oct` package is importable when running as a script
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from oct.dispatchers.purchase import PurchaseDispatcher  # noqa: E402
from oct.environment import EnvironmentState  # noqa: E402
from oct.llm import AnthropicClient  # noqa: E402
from oct.personas.buyer_a import make_agent  # noqa: E402
from oct.runner import run_simulation  # noqa: E402


def main() -> int:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("ERROR: ANTHROPIC_API_KEY is not set", file=sys.stderr)
        return 1

    state = EnvironmentState(current_day=0)
    dispatcher = PurchaseDispatcher(state)
    agent = make_agent("buyer_a")
    llm = AnthropicClient()

    trace = run_simulation(
        env=dispatcher,
        agents=[agent],
        llm=llm,
        max_days=5,
        temperature=0.8,
        actions_per_agent_per_day=1,
    )

    # Full trace as JSON for machine consumption
    print(json.dumps(trace.to_dict(), ensure_ascii=False, indent=2))

    # Short human summary
    print("\n--- SUMMARY ---", file=sys.stderr)
    print(f"total_steps       : {len(trace.steps)}", file=sys.stderr)
    print(f"dispatched_ok     : {len(trace.dispatched_actions())}", file=sys.stderr)
    print(f"errors            : {len(trace.errors())}", file=sys.stderr)
    print(f"final_snapshot    : {trace.final_snapshot}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
