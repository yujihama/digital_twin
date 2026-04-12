"""Trace analysis utility — canonical source for experiment results.

Reads a trace JSON file and outputs a structured analysis suitable for
copying into results.md. This script eliminates manual counting errors
by deriving all numbers directly from the trace data.

Usage:
    python scripts/analyze_trace.py <trace_file.json>

Example:
    python scripts/analyze_trace.py ../exp003_full_pipeline/trace_seed42.json

T-028 extension
---------------
The report now includes a "PO vs Actual Amount Deltas" section that lists,
for every order in the trace, (PO amount, delivered amount, invoiced amount)
plus the relative deltas. This surfaces the T-028 ambiguity effect: when
interpretive ambiguity is ON and vendor_e is an LLM, non-zero deltas appear
even though vendor_e's action schema is unchanged from T-022. RB-min
(L1) always produces zero deltas because it ignores the ambiguity fields.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional


def load_trace(path: Path) -> Dict[str, Any]:
    """Load and return the trace JSON."""
    return json.loads(path.read_text(encoding="utf-8"))


def _extract_action_params(step: Dict[str, Any]) -> Dict[str, Any]:
    action = step.get("action") or {}
    return action.get("parameters", {}) or {}


def _extract_details(step: Dict[str, Any]) -> Dict[str, Any]:
    dr = step.get("dispatch_result", {}) or {}
    return dr.get("details", {}) or {}


def analyze_amount_deltas(steps: List[Dict[str, Any]]) -> Dict[str, Any]:
    """T-028 — reconstruct (PO, GR, Invoice) amounts per order from the trace.

    Walks the action log and groups events by ``order_id``. For each order
    we record the PO amount (from place_order or deliver_partial/invoice
    details), the delivered amount (from deliver / deliver_partial /
    record_receipt), and the invoice amount (from register_invoice /
    invoice_with_markup). Deltas are computed relative to the PO amount.

    Only orders for which we see a place_order event are included so the
    baseline is unambiguous. Orders that never got delivered or invoiced
    still appear in the per-order list with ``gr_amount=None`` /
    ``inv_amount=None``.

    Returns a dict with:
      - ``per_order``: list of dicts, one per order_id, with fields
        ``order_id``, ``po_amount``, ``gr_amount``, ``gr_delta``,
        ``gr_delta_pct``, ``inv_amount``, ``inv_delta``, ``inv_delta_pct``.
      - ``summary``: aggregate counts & percentiles.
    """
    po_amounts: Dict[str, float] = {}
    gr_amounts: Dict[str, float] = {}
    inv_amounts: Dict[str, float] = {}

    for step in steps:
        action = step.get("action") or {}
        action_type = action.get("action_type")
        params = _extract_action_params(step)
        details = _extract_details(step)
        dr = step.get("dispatch_result", {}) or {}
        if not dr.get("ok"):
            continue

        # PO amount is primarily established by place_order. The strategic
        # vendor actions (deliver_partial / invoice_with_markup) also expose
        # po_amount in their details so we capture it there as a safety net
        # in case the trace got spliced or truncated upstream.
        if action_type == "place_order":
            order_id = details.get("order_id") or params.get("request_id")
            amt = details.get("amount")
            if order_id is not None and amt is not None:
                po_amounts.setdefault(str(order_id), float(amt))
        elif action_type in ("deliver_partial", "invoice_with_markup"):
            order_id = params.get("order_id") or details.get("order_id")
            po = details.get("po_amount")
            if order_id is not None and po is not None:
                po_amounts.setdefault(str(order_id), float(po))

        # Goods receipt
        if action_type in ("deliver", "record_receipt", "deliver_partial"):
            order_id = params.get("order_id") or details.get("order_id")
            delivered = details.get("delivered_amount")
            if delivered is None:
                delivered = params.get("delivered_amount")
            if order_id is not None and delivered is not None:
                gr_amounts[str(order_id)] = float(delivered)

        # Invoice
        if action_type in ("register_invoice", "invoice_with_markup"):
            order_id = params.get("order_id") or details.get("order_id")
            amt = details.get("amount")
            if amt is None:
                amt = params.get("amount")
            if order_id is not None and amt is not None:
                inv_amounts[str(order_id)] = float(amt)

    per_order: List[Dict[str, Any]] = []
    for order_id in sorted(po_amounts.keys()):
        po = po_amounts[order_id]
        gr = gr_amounts.get(order_id)
        inv = inv_amounts.get(order_id)
        entry: Dict[str, Any] = {
            "order_id": order_id,
            "po_amount": po,
            "gr_amount": gr,
            "gr_delta": (gr - po) if gr is not None else None,
            "gr_delta_pct": ((gr - po) / po * 100.0) if (gr is not None and po) else None,
            "inv_amount": inv,
            "inv_delta": (inv - po) if inv is not None else None,
            "inv_delta_pct": ((inv - po) / po * 100.0) if (inv is not None and po) else None,
        }
        per_order.append(entry)

    # Aggregate stats. We report how many orders have a non-zero delta and
    # the worst-case percentage so reviewers can see the tail of the
    # distribution at a glance.
    def _nonzero(vals: List[Optional[float]]) -> int:
        return sum(1 for v in vals if v is not None and v != 0.0)

    def _max_abs_pct(vals: List[Optional[float]]) -> Optional[float]:
        nums = [abs(v) for v in vals if v is not None]
        return round(max(nums), 3) if nums else None

    def _mean_abs_pct(vals: List[Optional[float]]) -> Optional[float]:
        nums = [abs(v) for v in vals if v is not None]
        return round(sum(nums) / len(nums), 3) if nums else None

    gr_deltas = [e["gr_delta"] for e in per_order]
    inv_deltas = [e["inv_delta"] for e in per_order]
    gr_delta_pcts = [e["gr_delta_pct"] for e in per_order]
    inv_delta_pcts = [e["inv_delta_pct"] for e in per_order]

    summary = {
        "n_orders": len(per_order),
        "n_with_gr": sum(1 for e in per_order if e["gr_amount"] is not None),
        "n_with_invoice": sum(1 for e in per_order if e["inv_amount"] is not None),
        "n_gr_delta_nonzero": _nonzero(gr_deltas),
        "n_inv_delta_nonzero": _nonzero(inv_deltas),
        "max_abs_gr_delta_pct": _max_abs_pct(gr_delta_pcts),
        "max_abs_inv_delta_pct": _max_abs_pct(inv_delta_pcts),
        "mean_abs_gr_delta_pct": _mean_abs_pct(gr_delta_pcts),
        "mean_abs_inv_delta_pct": _mean_abs_pct(inv_delta_pcts),
    }
    return {"per_order": per_order, "summary": summary}


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

    # --- T-028 amount deltas ---
    amount_deltas = analyze_amount_deltas(steps)

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
        "amount_deltas": amount_deltas,
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

    # T-028 amount delta section
    ad = result.get("amount_deltas", {})
    summary = ad.get("summary", {}) if ad else {}
    if summary:
        lines.append("## T-028 PO vs Actual Amount Deltas")
        lines.append(f"  n_orders              : {summary.get('n_orders', 0)}")
        lines.append(f"  n_with_gr             : {summary.get('n_with_gr', 0)}")
        lines.append(f"  n_with_invoice        : {summary.get('n_with_invoice', 0)}")
        lines.append(f"  n_gr_delta_nonzero    : {summary.get('n_gr_delta_nonzero', 0)}")
        lines.append(f"  n_inv_delta_nonzero   : {summary.get('n_inv_delta_nonzero', 0)}")
        lines.append(f"  max_abs_gr_delta_pct  : {summary.get('max_abs_gr_delta_pct')}")
        lines.append(f"  max_abs_inv_delta_pct : {summary.get('max_abs_inv_delta_pct')}")
        lines.append(f"  mean_abs_gr_delta_pct : {summary.get('mean_abs_gr_delta_pct')}")
        lines.append(f"  mean_abs_inv_delta_pct: {summary.get('mean_abs_inv_delta_pct')}")
        lines.append("")

        # Show up to 10 orders with non-zero deltas so reviewers can spot
        # patterns (e.g. always-5%-markup) without scrolling through the
        # full list.
        flagged = [
            o for o in ad.get("per_order", [])
            if (o.get("gr_delta") not in (None, 0.0))
            or (o.get("inv_delta") not in (None, 0.0))
        ]
        if flagged:
            lines.append("  Non-zero deltas (up to 10):")
            header = "  order_id       po          gr          gr_Δ%      inv         inv_Δ%"
            lines.append(header)
            for o in flagged[:10]:
                gr_pct = o.get("gr_delta_pct")
                inv_pct = o.get("inv_delta_pct")
                lines.append(
                    f"  {o['order_id']:<14}"
                    f" {o['po_amount']:<11.0f}"
                    f" {('-' if o['gr_amount'] is None else f'{o[chr(103)+chr(114)+chr(95)+chr(97)+chr(109)+chr(111)+chr(117)+chr(110)+chr(116)]:.0f}'):<11}"
                    f" {('-' if gr_pct is None else f'{gr_pct:+.2f}%'):<10}"
                    f" {('-' if o['inv_amount'] is None else f'{o[chr(105)+chr(110)+chr(118)+chr(95)+chr(97)+chr(109)+chr(111)+chr(117)+chr(110)+chr(116)]:.0f}'):<11}"
                    f" {('-' if inv_pct is None else f'{inv_pct:+.2f}%')}"
                )
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
    if summary:
        lines.append(f"| n_gr_delta_nonzero | {summary.get('n_gr_delta_nonzero', 0)} |")
        lines.append(f"| n_inv_delta_nonzero | {summary.get('n_inv_delta_nonzero', 0)} |")
        lines.append(f"| max_abs_inv_delta_pct | {summary.get('max_abs_inv_delta_pct')} |")
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
