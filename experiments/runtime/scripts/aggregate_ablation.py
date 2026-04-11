"""Aggregate per-cell ablation summaries into a single ablation_summary.json.

Motivation
----------
`scripts/run_ablation.py` emits an `ablation_summary.json` for the set of
cells it runs in a *single* invocation. When the L1 and L3 sweeps are run
in separate invocations (the current workflow, because the L3 sweep takes
~30 minutes per regime and we do not want to re-run L1 each time), the
second invocation overwrites the aggregate file with its own cells only.

This helper walks ``experiments/ablation_t021/`` and rebuilds the aggregate
from the per-cell ``summary.json`` files, so results from separate sweeps
can be merged deterministically. It also computes additional per-cell
statistics (``stdev_payments``, ``payments_by_seed``, ``stdev_total_steps``)
that the inline aggregator in ``run_ablation.py`` does not emit today; see
``results.md`` §1 for how those are used.

Usage
-----
::

    cd experiments/runtime
    python scripts/aggregate_ablation.py

    # write to an alternate location
    python scripts/aggregate_ablation.py --out ../ablation_t021_snapshot
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path
from typing import Any, Dict, List

RUNTIME_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROOT = RUNTIME_ROOT.parent / "ablation_t021"

# Folders under the ablation root that should be ignored (historical/preliminary
# data kept for reference). Anything starting with one of these prefixes is
# skipped during scanning.
EXCLUDED_PREFIXES = ("preliminary_",)


def _mean(values: List[float]) -> float:
    if not values:
        return 0.0
    return round(sum(values) / len(values), 3)


def _stdev(values: List[float]) -> float:
    """Population-friendly stdev: returns 0.0 when fewer than 2 samples."""
    if len(values) < 2:
        return 0.0
    return round(statistics.stdev(values), 3)


def _is_excluded(relative: Path) -> bool:
    parts = relative.parts
    if not parts:
        return False
    return any(parts[0].startswith(prefix) for prefix in EXCLUDED_PREFIXES)


def load_summaries(root: Path) -> List[Dict[str, Any]]:
    """Return every per-cell ``summary.json`` beneath ``root``.

    Skips ``preliminary_*`` folders (reserved for historical snapshots) and
    the ablation-level ``ablation_summary.json`` (not a per-cell file).
    """
    summaries: List[Dict[str, Any]] = []
    for summary_path in sorted(root.rglob("summary.json")):
        relative = summary_path.relative_to(root)
        if _is_excluded(relative):
            continue
        try:
            data = json.loads(summary_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            print(
                f"[aggregate_ablation] WARN: failed to parse {summary_path}: {exc}",
                file=sys.stderr,
            )
            continue
        # Per-cell summaries always carry level/regime/seed. Anything that
        # doesn't is not one of ours.
        if not all(key in data for key in ("level", "regime", "seed")):
            continue
        summaries.append(data)
    return summaries


def aggregate(summaries: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Group summaries by ``{level}_{regime}`` and compute cell statistics."""
    by_cell: Dict[str, List[Dict[str, Any]]] = {}
    for s in summaries:
        key = f"{s['level']}_{s['regime']}"
        by_cell.setdefault(key, []).append(s)

    cells: Dict[str, Any] = {}
    for key, group in sorted(by_cell.items()):
        group_sorted = sorted(group, key=lambda s: s["seed"])
        deviations = [s.get("deviation_count", 0) for s in group_sorted]
        errors = [s.get("error_count", 0) for s in group_sorted]
        payments = [s.get("counts", {}).get("payments", 0) for s in group_sorted]
        dispatched = [s.get("dispatched_ok", 0) for s in group_sorted]
        total_steps = [s.get("total_steps", 0) for s in group_sorted]
        decide_errors = [s.get("decide_or_dispatch_errors", 0) for s in group_sorted]

        first = group_sorted[0]
        cells[key] = {
            "level": first["level"],
            "regime": first["regime"],
            "n_seeds": len(group_sorted),
            "max_days": first.get("max_days"),
            "mean_deviation_count": _mean(deviations),
            "mean_error_count": _mean(errors),
            "mean_payments": _mean(payments),
            "stdev_payments": _stdev(payments),
            "payments_by_seed": {
                str(s["seed"]): s.get("counts", {}).get("payments", 0)
                for s in group_sorted
            },
            "mean_dispatched_ok": _mean(dispatched),
            "mean_total_steps": _mean(total_steps),
            "stdev_total_steps": _stdev(total_steps),
            "mean_decide_or_dispatch_errors": _mean(decide_errors),
            "seeds": [s["seed"] for s in group_sorted],
        }
    return cells


def build_doc(
    summaries: List[Dict[str, Any]],
    aggregated: Dict[str, Any],
    note: str,
) -> Dict[str, Any]:
    """Assemble the top-level ``ablation_summary.json`` payload."""
    levels = sorted({s["level"] for s in summaries})
    regimes = sorted({s["regime"] for s in summaries})
    seeds = sorted({s["seed"] for s in summaries})
    max_days_values = sorted({s.get("max_days") for s in summaries if s.get("max_days") is not None})
    models = sorted({s.get("model") for s in summaries if s.get("model")})

    return {
        "config": {
            "levels": levels,
            "regimes": regimes,
            "seeds": seeds,
            "days": max_days_values[-1] if max_days_values else None,
            "model": models[-1] if models else None,
            "note": note,
        },
        "cells": aggregated,
        "raw_summaries": sorted(
            summaries,
            key=lambda s: (s["level"], s["regime"], s["seed"]),
        ),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Aggregate per-cell ablation summaries into ablation_summary.json",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=DEFAULT_ROOT,
        help="Directory containing per-cell {level}_{regime}/seed{N}/summary.json files",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output path (default: <root>/ablation_summary.json)",
    )
    parser.add_argument(
        "--note",
        default=(
            "Rebuilt by scripts/aggregate_ablation.py by scanning per-cell "
            "summary.json files. preliminary_8day/ is excluded; see results.md §0."
        ),
        help="Free-form note stored in config.note",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root: Path = args.root
    if not root.exists():
        print(f"[aggregate_ablation] ERROR: {root} does not exist", file=sys.stderr)
        return 2

    summaries = load_summaries(root)
    if not summaries:
        print(
            f"[aggregate_ablation] ERROR: no per-cell summary.json files found under {root}",
            file=sys.stderr,
        )
        return 2

    aggregated = aggregate(summaries)
    doc = build_doc(summaries, aggregated, args.note)

    out_path: Path = args.out or (root / "ablation_summary.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(doc, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(
        f"[aggregate_ablation] wrote {out_path} "
        f"({len(summaries)} summaries, {len(aggregated)} cells)",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
