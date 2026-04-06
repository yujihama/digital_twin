"""Persona for 購買担当B (buyer_b) — purchase-approval flow prototype.

Slightly different profile from buyer_a so that interaction emerges rather
than mechanical duplication: buyer_b is newer, more cautious, and tends to
copy patterns from senior colleagues. This creates the substrate for
"imitation" / "split-order" emergent behaviors without baking them in.
"""
from __future__ import annotations

from typing import Any, Dict, List

from oct.agent import ActionOption, Agent
from oct.environment import EnvironmentState, RequestStatus

# --- Persona ---------------------------------------------------------------

BUYER_B_PERSONA = """あなたは中堅製造業の購買担当B（buyer_b）です。

## キャラクター
- 勤続2年、まだ業務の勘所を掴みきれていない
- 判断に迷ったら先輩（buyer_a）のやり方を真似る傾向がある
- ミスを恐れて過度に慎重になることがある
- 承認プロセスには従順で、閾値を超える案件には必ず承認を通したい

## 1日の役割
- 現場からの購買需要（pending_demands）を確認し、必要に応じて購買要求を起票する (draft_request)
- 承認済み案件の発注を行う (place_order)
- 納品された物品の受領を記録する (record_receipt)
- 取るべき行動がなければ待機する (wait)

## 行動原則
- pending_demands に未処理の需要がある場合は、先輩（buyer_a）の動きも参考にしつつ対応を検討する
- ただし、全ての需要に即座に対応する必要はない。自分のキャパシティや先輩の動きを見て判断する
- その日のキャパシティ（1日5アクション）を意識する
- 承認閾値（100万円）は厳格に守る
- 他の購買担当がどう動いているかを参考にする
- 判断に迷う場合は保守的に wait を選ぶ

あなたは環境の観測情報を受け取り、次に取るべき1つの行動をJSONで返します。
"""


# --- Action schema ---------------------------------------------------------

BUYER_B_ACTIONS: List[ActionOption] = [
    ActionOption(
        name="draft_request",
        description="新しい購買要求を起票する。pending_demandsに需要がある場合はdemand_idを指定して紐付ける",
        parameters_schema={
            "vendor": "取引先ID (str)",
            "item": "品目名 (str)",
            "amount": "金額 (int, 円)",
            "demand_id": "対応する需要ID (str, optional)",
        },
    ),
    ActionOption(
        name="place_order",
        description="承認済みまたは閾値未満の要求から発注を行う",
        parameters_schema={"request_id": "対象のPurchaseRequest ID (str)"},
    ),
    ActionOption(
        name="record_receipt",
        description="発注済み案件の納品を受領記録する",
        parameters_schema={
            "order_id": "対象のOrder ID (str)",
            "delivered_amount": "納品された金額 (int, 円)",
        },
    ),
    ActionOption(
        name="wait",
        description="この日は何もせず次のステップに進む",
        parameters_schema={},
    ),
]


def make_agent(agent_id: str = "buyer_b") -> Agent:
    """Factory for buyer_b agent."""
    return Agent(
        agent_id=agent_id,
        role="buyer",
        persona=BUYER_B_PERSONA,
        available_actions=BUYER_B_ACTIONS,
    )


# --- Observation builder ---------------------------------------------------

def build_observation(state: EnvironmentState, agent_id: str = "buyer_b") -> Dict[str, Any]:
    """Observation for buyer_b — mirrors buyer_a but also exposes peers'
    recent activity to enable imitation / split-order patterns to emerge.
    """
    state.ensure_capacity_initialized()

    my_requests = [
        {
            "id": r.id,
            "vendor": r.vendor,
            "item": r.item,
            "amount": r.amount,
            "status": r.status.value,
            "created_day": r.created_day,
        }
        for r in state.purchase_requests
        if r.requester == agent_id
    ]

    ready_to_order = [
        r["id"]
        for r in my_requests
        if r["status"] == RequestStatus.APPROVED.value
        or (
            r["status"] == RequestStatus.DRAFTED.value
            and r["amount"] < state.controls.approval_threshold
        )
    ]

    # Peer visibility: buyer_b can see other buyers' recent requests
    # (imitation substrate — does NOT force imitation, just enables it)
    peer_recent_requests = [
        {
            "requester": r.requester,
            "vendor": r.vendor,
            "amount": r.amount,
            "status": r.status.value,
            "created_day": r.created_day,
        }
        for r in state.purchase_requests
        if r.requester != agent_id and r.requester.startswith("buyer_")
    ][-10:]

    awaiting_receipt = [
        {
            "order_id": o.id,
            "request_id": o.request_id,
            "vendor": o.vendor,
            "amount": o.amount,
        }
        for o in state.orders
        if state.receipt_for(o.id) is None
        and state.get_request(o.request_id) is not None
        and state.get_request(o.request_id).requester == agent_id  # type: ignore[union-attr]
    ]

    # Pending demands from the environment (unfulfilled internal needs)
    pending_demands = [
        {
            "id": d.id,
            "department": d.department,
            "item": d.item,
            "amount_hint": d.amount_hint,
            "urgency": d.urgency.value,
            "generated_day": d.generated_day,
        }
        for d in state.pending_demands()
    ]

    return {
        "agent_id": agent_id,
        "current_day": state.current_day,
        "remaining_capacity": state.remaining_capacity.get(agent_id, 0),
        "approval_threshold": state.controls.approval_threshold,
        "pending_demands": pending_demands,
        "my_requests": my_requests,
        "ready_to_order_request_ids": sorted(set(ready_to_order)),
        "awaiting_receipt_orders": awaiting_receipt,
        "peer_recent_requests": peer_recent_requests,
    }
