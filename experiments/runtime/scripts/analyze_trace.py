"""Trace analysis utility — canonical source for experiment results.

Reads a trace JSON file and outputs a structured analysis suitable for
copying into results.md. This script eliminates manual counting errors
by deriving all numbers directly from the trace data.

Usage:
    python scripts/analyze_trace.py <trace_file.json>

Example:
    python scripts/analyze_trace.py ../exp003_full_pipeline/trace_seed42.json
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List


def load_trace(path: Path) -> Dict[str, Any]:
    """Load and return the trace JSON."""
    return json.loads(path.read_text(encoding="utf-8"))


def analyze(trace: Dict[str, Any]) -> Dict[str, Any]:
    """Analyze trace and return structured results dict."""
    steps: List[Dict[str, Any]] = trace["steps"]
    final_snapshot = trace.get("final_snapshot", {})
    counts = final_snapshot.get("counts", {})

    # --- Per-agent action breakdown ---
    per_agent: Dict[str, Counter] = {}
    for s in steps:
        aid = s["agent_id"]
        atype = s["action"]["action_type"] if s.get("action") else "(none)"
        per_agent.setdefault(aid, Counter())[atype] += 1

    # --- Total steps (from trace, not snapshot) ---
    total_steps = len(steps)

    # --- Count actions by type across all agents ---
    action_counts: Counter = Counter()
    for s in steps:
        if s.get("action"):
            action_counts[s["action"]["action_type"]] += 1

    # --- Dispatch results analysis ---
    ok_count = 0
    error_count = 0
    errors: List[Dict[str, Any]] = []
    for s in steps:
        dr = s.get("dispatch_result", {})
        if dr.get("ok"):
            ok_count += 1
        elif dr.get("error"):
            error_count += 1
            errors.append({
                "day": s["day"],
                "agent_id": s["agent_id"],
                "action": s["action"]["action_type"] if s.get("action") else None,
                "error": dr["error"],
            })

    # --- Vendor ID analysis ---
    vendor_ids_used: Counter = Counter()
    for s in steps:
        if s.get("action") and s["action"]["action_type"] == "draft_request":
            vendor = s["action"]["parameters"].get("vendor", "N/A")
            vendor_ids_used[vendor] += 1

    # --- Three-way match analysis ---
    payments = []
    for s in steps:
        if s.get("action") and s["action"]["action_type"] == "pay_order":
            dr = s.get("dispatch_result", {})
            details = dr.get("details", {})
            payments.append({
                "day": s["day"],
                "agent": s["agent_id"],
                "matched": details.get("three_way_matched", None),
            })
    matched = sum(1 for p in payments if p["matched"])
    unmatched = sum(1 for p in payments if not p["matched"])

    # --- Approval analysis ---
    approvals = []
    for s in steps:
        if s.get("action") and s["action"]["action_type"] == "approve_request":
            params = s["action"]["parameters"]
            approvals.append({
                "day": s["day"],
                "agent": s["agent_id"],
                "request_id": params.get("request_id"),
                "decision": params.get("decision"),
                "note": params.get("note", ""),
            })

    # --- Pipeline completion (from snapshot counts) ---
    pipeline = {
        "purchase_requests": counts.get("purchase_requests", 0),
        "approvals": counts.get("approvals", 0),
        "orders": counts.get("orders", 0),
        "receipts": counts.get("receipts", 0),
        "invoices": counts.get("invoices", 0),
        "payments": counts.get("payments", 0),
        "demands_total": counts.get("demands_total", 0),
        "demands_pending": counts.get("demands_pending", 0),
        "demands_fulfilled": counts.get("demands_fulfilled", 0),
    }

    return {
        "total_steps": total_steps,
        "dispatched_ok": ok_count,
        "errors": error_count,
        "error_details": errors,
        "per_agent": {aid: dict(c) for aid, c in per_agent.items()},
        "action_counts": dict(action_counts),
        "vendor_ids_used": dict(vendor_ids_used),
        "three_way_match": {"matched": matched, "unmatched": unmatched},
        "approvals": approvals,
        "pipeline": pipeline,
        "final_snapshot": final_snapshot,
    }


def format_report(result: Dict[str, Any], trace_path: str) -> str:
    """Format analysis results as a human-readable report."""
    lines: List[str] = []
    lines.append(f"=== Trace Analysis: {trace_path} ===")
    lines.append("")

    # Summary
    lines.append("## Summary")
    lines.append(f"  total_steps       : {result['total_steps']}")
    lines.append(f"  dispatched_ok     : {result['dispatched_ok']}")
    lines.append(f"  errors            : {result['errors']}")
    lines.append("")

    # Pipeline counts (from final_snapshot)
    lines.append("## Pipeline Counts (final_snapshot)")
    p = result["pipeline"]
    for key in ["purchase_requests", "approvals", "orders", "receipts",
                "invoices", "payments", "demands_total", "demands_pending",
                "demands_fulfilled"]:
        lines.append(f"  {key:24s}: {p[key]}")
    lines.append("")

    # Per-agent breakdown
    agent_order = ["buyer_a", "buyer_b", "approver_c", "accountant_d", "vendor_e"]
    lines.append("## Per-Agent Actions")
    for aid in agent_order:
        counts = result["per_agent"].get(aid, {})
        if counts:
            lines.append(f"  {aid:14s}: {counts}")
    lines.append("")

    # Vendor IDs
    lines.append("## Vendor IDs Used in draft_request")
    for vid, count in sorted(result["vendor_ids_used"].items()):
        lines.append(f"  {vid}: {count}")
    lines.append("")

    # Three-way match
    twm = result["three_way_match"]
    lines.append("## Three-Way Match")
    lines.append(f"  matched  : {twm['matched']}")
    lines.append(f"  unmatched: {twm['unmatched']}")
    lines.append("")

    # Approvals
    lines.append("## Approvals")
    if result["approvals"]:
        for a in result["approvals"]:
            lines.append(f"  day={a['day']} {a['agent']}: {a['request_id']} -> {a['decision']} ({a['note']})")
    else:
        lines.append("  (none)")
    lines.append("")

    # Errors
    if result["error_details"]:
        lines.append(f"## Errors ({result['errors']} total, showing up to 10)")
        for e in result["error_details"][:10]:
            lines.append(f"  day={e['day']} {e['agent_id']}: {e['error']}")
    else:
        lines.append("## Errors: none")
    lines.append("")

    # Markdown table for results.md
    lines.append("## results.md Table (copy-paste ready)")
    lines.append("")
    lines.append("| 指標 | 値 |")
    lines.append("|---|---|")
    lines.append(f"| total_steps | {result['total_steps']} |")
    lines.append(f"| errors | {result['errors']} |")
    for key in ["purchase_requests", "approvals", "orders", "receipts",
                "invoices", "payments", "demands_fulfilled"]:
        lines.append(f"| {key} | {p[key]} |")
    lines.append("")

    lines.append("| agent | " + " | ".join([
        "draft", "approve", "place_order", "record_receipt",
        "deliver", "register_invoice", "pay_order", "wait"
    ]) + " |")
    lines.append("|---|" + "---|" * 8)
    action_keys = [
        "draft_request", "approve_request", "place_order", "record_receipt",
        "deliver", "register_invoice", "pay_order", "wait"
    ]
    for aid in agent_order:
        counts = result["per_agent"].get(aid, {})
        vals = [str(counts.get(k, "—")) for k in action_keys]
        lines.append(f"| {aid} | " + " | ".join(vals) + " |")

    return "\n".join(lines)


def main() -> int:
    # Ensure UTF-8 output on Windows
    if sys.stdout.encoding != "utf-8":
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    if sys.stderr.encoding != "utf-8":
        sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]

    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <trace_file.json>", file=sys.stderr)
        return 1

    trace_path = Path(sys.argv[1])
    if not trace_path.exists():
        print(f"ERROR: File not found: {trace_path}", file=sys.stderr)
        return 1

    trace = load_trace(trace_path)
    result = analyze(trace)
    report = format_report(result, str(trace_path))
    print(report)

    # Also output as JSON for programmatic use
    json_path = trace_path.with_suffix(".analysis.json")
    json_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\nJSON analysis saved to: {json_path}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
