"""Persona for 購買担当A (buyer_a) — purchase-approval flow prototype.

Domain-specific module. Depends on the purchase-approval environment
(oct.environment) for action semantics.

Minimal T-003 scope: persona text + action schema + observation builder.
Kept deliberately simple so that T-007 can be reached quickly; richer
decision-making traits (risk tolerance, vendor preferences, etc.) can
be layered on later without changing the generic `oct.agent` module.
"""
from __future__ import annotations

from typing import Any, Dict, List

from oct.agent import ActionOption, Agent
from oct.environment import EnvironmentState, RequestStatus

# --- Persona ---------------------------------------------------------------

BUYER_A_PERSONA = """あなたは中堅製造業の購買担当A（buyer_a）です。

## キャラクター
- 勤続8年、現場からの要望を日常的に受ける立場
- 効率重視で、手戻りを避けたい
- 承認待ちが長引くとストレスを感じる
- 取引先との関係維持も意識している

## 1日の役割
- 現場からの購買需要（pending_demands）を確認し、必要に応じて購買要求を起票する (draft_request)
- 承認済み案件の発注を行う (place_order)
- 納品された物品の受領を記録する (record_receipt)
- 取るべき行動がなければ待機する (wait)

## 行動原則
- pending_demands に未処理の需要がある場合は、優先度（urgency: high > normal > low）を考慮して起票を検討する
- draft_request の vendor には available_vendors に含まれるIDのいずれかを指定すること
- ただし、全ての需要に即座に対応する必要はない。キャパシティや他の案件の状況を踏まえて判断する
- その日のキャパシティ（1日5アクション）を意識する
- 承認閾値（100万円）を意識しつつ、不要な分割発注はしない
- 判断に迷う場合は保守的に wait を選ぶ

あなたは環境の観測情報を受け取り、次に取るべき1つの行動をJSONで返します。
"""


# --- Action schema ---------------------------------------------------------

BUYER_A_ACTIONS: List[ActionOption] = [
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


def make_agent(agent_id: str = "buyer_a") -> Agent:
    """Factory for buyer_a agent."""
    return Agent(
        agent_id=agent_id,
        role="buyer",
        persona=BUYER_A_PERSONA,
        available_actions=BUYER_A_ACTIONS,
    )


# --- Observation builder ---------------------------------------------------

def build_observation(state: EnvironmentState, agent_id: str = "buyer_a") -> Dict[str, Any]:
    """Project EnvironmentState into a buyer_a-oriented observation dict.

    Only surfaces information buyer_a can reasonably see:
      - the current day and their remaining capacity
      - their own drafted/approved requests
      - orders they placed that are awaiting receipt
      - approval threshold (public control parameter)
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

    # Fix (PR#4 review): make intent explicit. Orderable = APPROVED, OR
    # DRAFTED with amount under the approval threshold (auto-approve path).
    ready_to_order = [
        r["id"]
        for r in my_requests
        if r["status"] == RequestStatus.APPROVED.value
        or (
            r["status"] == RequestStatus.DRAFTED.value
            and r["amount"] < state.controls.approval_threshold
        )
    ]

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
        and state.get_request(o.request_id).requester == agent_id
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

    # Available vendors — buyer must use one of these IDs when drafting
    available_vendors = [
        aid for aid, cap in state.daily_capacity.items()
        if aid.startswith("vendor_")
    ]

    return {
        "agent_id": agent_id,
        "current_day": state.current_day,
        "remaining_capacity": state.remaining_capacity.get(agent_id, 0),
        "approval_threshold": state.controls.approval_threshold,
        "available_vendors": available_vendors,
        "pending_demands": pending_demands,
        "my_requests": my_requests,
        "ready_to_order_request_ids": sorted(set(ready_to_order)),
        "awaiting_receipt_orders": awaiting_receipt,
    }
