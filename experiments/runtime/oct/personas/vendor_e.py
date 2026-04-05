"""Persona for 取引先E (vendor_e) — external actor, counterparty.

vendor_e sits **outside** the organization. Its presence is essential for
OCT to observe emergent behaviors that come from the org↔outside boundary
(docs/05_oct_framework.md §5.5, PR#2 review).

Deliberately given a flexible action set and a persona that **leaves room
for strategic behavior** without baking any single strategy into the
prompt — the research question is whether such behavior emerges.

Available strategic moves (enabled by the action schema, not forced):
  - Deliver the exact ordered amount vs. deliver slightly different
    (creates three-way-match friction)
  - Invoice matching the order vs. invoice with a small markup
  - Pricing adjustments over time (observable pattern)
"""
from __future__ import annotations

from typing import Any, Dict, List

from oct.agent import ActionOption, Agent
from oct.environment import EnvironmentState

# --- Persona ---------------------------------------------------------------

VENDOR_E_PERSONA = """あなたは取引先E（vendor_e）の営業担当です。組織の**外部**の立場です。

## キャラクター
- 中小の専門部品サプライヤ
- 長期的な取引関係を重視するが、自社の利益も守りたい
- 発注元の承認プロセスや締め付けの度合いを観察している
- 取引量が増えれば価格を据え置き、減れば値上げも検討する

## 1日の役割
- 受注済み案件に対して納品を行う (deliver)
- 納品済み案件に対して請求書を発行する (register_invoice)
- 特に動きがなければ待機する (wait)

## 行動原則
- その日のキャパシティ（1日6アクション）を意識する
- 基本は発注金額と同額で納品・請求する（誠実な取引）
- ただし長期関係や市況を踏まえ、金額や納期を調整する余地はある
- 判断材料がなければ wait を選ぶ

あなたは環境の観測情報を受け取り、次に取るべき1つの行動をJSONで返します。
"""


# --- Action schema ---------------------------------------------------------
#
# NOTE: vendor_e uses `deliver` (vendor-side naming) which the dispatcher
# maps to the same `record_receipt` transition buyer_a uses. This reflects
# the domain reality that a receipt event happens when the vendor delivers.

VENDOR_E_ACTIONS: List[ActionOption] = [
    ActionOption(
        name="deliver",
        description="受注済みOrderに対して物品を納品する（金額は発注額と一致が基本）",
        parameters_schema={
            "order_id": "対象のOrder ID (str)",
            "delivered_amount": "実際の納品金額 (int, 円)",
        },
    ),
    ActionOption(
        name="register_invoice",
        description="納品済みOrderに対して請求書を発行する",
        parameters_schema={
            "order_id": "対象のOrder ID (str)",
            "amount": "請求金額 (int, 円)",
        },
    ),
    ActionOption(
        name="wait",
        description="この日は何もせず次のステップに進む",
        parameters_schema={},
    ),
]


def make_agent(agent_id: str = "vendor_e") -> Agent:
    """Factory for vendor_e agent."""
    return Agent(
        agent_id=agent_id,
        role="vendor",
        persona=VENDOR_E_PERSONA,
        available_actions=VENDOR_E_ACTIONS,
    )


# --- Observation builder ---------------------------------------------------

def build_observation(state: EnvironmentState, agent_id: str = "vendor_e") -> Dict[str, Any]:
    """Observation for vendor_e — scoped to *their own* orders and
    payment history (what a real external counterparty would know).

    Intentionally does NOT expose internal approval details, pending
    requests from other buyers, or three-way-match state; vendor_e only
    sees the interface: orders placed with them, deliveries they made,
    invoices they issued, and payments received.
    """
    state.ensure_capacity_initialized()

    my_orders: List[Dict[str, Any]] = []
    paid_ids = {p.order_id for p in state.payments}
    for order in state.orders:
        if order.vendor != agent_id:
            continue
        receipt = state.receipt_for(order.id)
        invoice = state.invoice_for(order.id)
        my_orders.append(
            {
                "order_id": order.id,
                "amount": order.amount,
                "placed_day": order.placed_day,
                "delivered": receipt is not None,
                "delivered_amount": receipt.delivered_amount if receipt else None,
                "invoiced": invoice is not None,
                "invoice_amount": invoice.amount if invoice else None,
                "paid": order.id in paid_ids,
            }
        )

    recent_payments = [
        {
            "order_id": p.order_id,
            "amount": p.amount,
            "paid_day": p.paid_day,
            "three_way_matched": p.three_way_matched,
        }
        for p in state.payments[-10:]
        if state.get_order(p.order_id) is not None
        and state.get_order(p.order_id).vendor == agent_id  # type: ignore[union-attr]
    ]

    return {
        "agent_id": agent_id,
        "current_day": state.current_day,
        "remaining_capacity": state.remaining_capacity.get(agent_id, 0),
        "my_orders": my_orders,
        "recent_payments_received": recent_payments,
    }
