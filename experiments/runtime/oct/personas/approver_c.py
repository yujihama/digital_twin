"""Persona for 承認者C (approver_c) — approves/rejects drafted requests.

Central gatekeeper of the approval flow. Their persona balances the
tension between "don't block the business" and "enforce the threshold",
which in the intervention scenario (threshold 100万→500万) is exactly
the pressure point the research is probing.
"""
from __future__ import annotations

from typing import Any, Dict, List

from oct.agent import ActionOption, Agent
from oct.environment import EnvironmentState, RequestStatus
from oct.rules import _requires_approval  # noqa: WPS450 (intentional: domain helper)

# --- Persona ---------------------------------------------------------------

APPROVER_C_PERSONA = """あなたは中堅製造業の購買承認者C（approver_c）です。

## キャラクター
- 勤続15年、購買部門のマネージャー
- コンプライアンス重視だが、業務の停滞も避けたい
- 閾値を超える案件の承認/却下を判断する最終責任者
- 現場からの突き上げと経理からの締め付けの板挟み

## 1日の役割
- 承認待ちの購買要求を承認または却下する (approve_request)
- 判断材料が足りない案件は見送って次の日に回す (wait)

## 行動原則
- その日のキャパシティ（1日10アクション）の範囲で処理する
- 閾値（100万円）以上の案件を優先的にさばく
- 金額が過度に大きい / 分割発注が疑われる案件は却下も検討
- 判断根拠を note に残す

あなたは環境の観測情報を受け取り、次に取るべき1つの行動をJSONで返します。
"""


# --- Action schema ---------------------------------------------------------

APPROVER_C_ACTIONS: List[ActionOption] = [
    ActionOption(
        name="approve_request",
        description="承認待ちのPurchaseRequestを承認または却下する",
        parameters_schema={
            "request_id": "対象のPurchaseRequest ID (str)",
            "decision": "'approved' または 'rejected' (str)",
            "note": "判断根拠の短いメモ (str, 任意)",
        },
    ),
    ActionOption(
        name="reject_request",
        description="承認待ちのPurchaseRequestを却下する（approve_requestでdecision='rejected'と同等）",
        parameters_schema={
            "request_id": "対象のPurchaseRequest ID (str)",
            "note": "却下理由の短いメモ (str, 任意)",
        },
    ),
    ActionOption(
        name="wait",
        description="この日は判断を保留し次のステップに進む",
        parameters_schema={},
    ),
]


def make_agent(agent_id: str = "approver_c") -> Agent:
    """Factory for approver_c agent."""
    return Agent(
        agent_id=agent_id,
        role="approver",
        persona=APPROVER_C_PERSONA,
        available_actions=APPROVER_C_ACTIONS,
    )


# --- Observation builder ---------------------------------------------------

def build_observation(state: EnvironmentState, agent_id: str = "approver_c") -> Dict[str, Any]:
    """Observation for approver_c — surfaces drafted requests awaiting
    approval plus recent approval history for pattern recognition."""
    state.ensure_capacity_initialized()

    pending = [
        {
            "id": r.id,
            "requester": r.requester,
            "vendor": r.vendor,
            "item": r.item,
            "amount": r.amount,
            "created_day": r.created_day,
        }
        for r in state.purchase_requests
        if r.status == RequestStatus.DRAFTED and _requires_approval(state, r.amount)
    ]

    recent_approvals = [
        {
            "request_id": a.request_id,
            "decision": a.decision.value,
            "day": a.day,
        }
        for a in state.approvals[-10:]
    ]

    return {
        "agent_id": agent_id,
        "current_day": state.current_day,
        "remaining_capacity": state.remaining_capacity.get(agent_id, 0),
        "approval_threshold": state.controls.approval_threshold,
        "pending_approvals": pending,
        "recent_approvals": recent_approvals,
    }
