# 09. Ablation実験計画 — LLMの価値の切り分け

> 本ドキュメントは、EOMにおけるLLMエージェントの必要性を検証するablation実験の設計を記述する。

## 1. 目的

exp003c/exp004で観察された波及効果（vendor_e間接活性化、accountant_d負荷増、buyer活性化等）が以下のどちらに起因するかを判別する。

1. **LLMの適応的判断**（優先順位付け、タイミング選択、キャパシティ配分等）
2. **ワークフロー構造の帰結**（キューイング動学、部分観測、逐次実行の構造的効果）

## 2. 設計原則

### role-wise × policy-family × regime

3つの軸で切る。

**軸1: 役割ごとの置換**

| 構成 | buyer_a | buyer_b | approver_c | accountant_d | vendor_e |
|------|---------|---------|------------|-------------|----------|
| 全LLM | LLM | LLM | LLM | LLM | LLM |
| 全RB | RB | RB | RB | RB | RB |
| buyer-only-RB | RB | RB | LLM | LLM | LLM |
| approver-only-RB | LLM | LLM | RB | LLM | LLM |
| vendor-only-RB | LLM | LLM | LLM | LLM | RB |
| accountant-only-RB | LLM | LLM | LLM | RB | LLM |

最低限必要なのは「全LLM」と「全RB」の比較。「どの役割でLLMが必要か」を特定するために役割別の置換を行う。

**軸2: Baseline Ladder（policy complexityの単調増加）**

第3回ヒアリングで `RB vs LLM` の二項対比から **Baseline Ladder** に再定義した（詳細は docs/08_research_pivot.md §6.1）。各段でQSDがどう変化するかを見ることで、「どの複雑度の階段を上がったときに新しい現象が出るか」を特定できる。

| level | family | 内容 | policy complexity |
|-------|--------|------|--------|
| L0 | random | 行動空間からuniform sampling | 最低 |
| L1 | RB-min | 固定優先順位ルールのみ（urgency高→古い順） | 低 |
| L2 | RB-score | urgency, age, backlog等の重み付きスコア最大化 | 中 |
| L3 | LLM | 現行（gpt-4.1-mini / gpt-5.4-mini） | 高 |

初回のablationはL1（RB-min）とL3（LLM）の比較で十分。同じパターンが出ればL0/L2は省略可能。違いが出た場合はL0とL2を追加して、ladderのどの段で現象が現れたかを特定する。

**実装上の要請: policy complexity の記録**

各実験のtraceメタデータに `policy_complexity` フィールド（"L0" / "L1" / "L2" / "L3"）を必ず記録する。後段の分析では、この値を横軸とした「QSD vs policy complexity」プロットを生成する。これによりladderに沿った可視化が可能になり、frontierの解釈に必要な情報源となる。

なお、L3（LLM）を構成するモデル名（gpt-4.1-mini, gpt-5.4-mini, claude-sonnet 等）はサブカテゴリとして別フィールドに記録する。

**軸3: regime（環境条件）**

| regime | 承認閾値 | 三者照合 | 需要強度 | キャパシティ |
|--------|---------|---------|---------|-----------|
| baseline | 200,000 | True | 1.5 | 2 |
| intervention_I1 | 5,000,000 | True | 1.5 | 2 |
| intervention_I2 | 200,000 | False | 1.5 | 2 |

初回はbaseline + intervention_I1のペアで実施。exp003c/exp004との直接比較が可能。

## 3. RB-minエージェントの仕様

### buyer_a / buyer_b（共通ロジック）

```python
def rb_min_buyer_decide(obs: dict) -> AgentAction:
    """最小限のルールベース購買担当。"""
    # 1. 受領可能な注文があれば受領（最古の注文を優先）
    if obs["awaiting_receipt_orders"]:
        order = obs["awaiting_receipt_orders"][0]
        return AgentAction(
            action_type="record_receipt",
            parameters={
                "order_id": order["order_id"],
                "delivered_amount": order["amount"],
            },
        )
    # 2. 発注可能な申請があれば発注（最古を優先）
    if obs["ready_to_order_request_ids"]:
        return AgentAction(
            action_type="place_order",
            parameters={"request_id": obs["ready_to_order_request_ids"][0]},
        )
    # 3. 未充足の需要があれば起票（urgency高→古い順）
    if obs["pending_demands"]:
        demands = sorted(
            obs["pending_demands"],
            key=lambda d: (
                {"high": 0, "normal": 1, "low": 2}[d["urgency"]],
                d["generated_day"],
            ),
        )
        d = demands[0]
        vendor = obs["available_vendors"][0] if obs["available_vendors"] else "vendor_e"
        return AgentAction(
            action_type="draft_request",
            parameters={
                "vendor": vendor,
                "item": d["item"],
                "amount": int(d["amount_hint"]),
                "demand_id": d["id"],
            },
        )
    # 4. 何もなければ待機
    return AgentAction(action_type="wait", parameters={})
```

### approver_c

```python
def rb_min_approver_decide(obs: dict) -> AgentAction:
    """最小限のルールベース承認者。閾値超えは全て承認。"""
    if obs["pending_approvals"]:
        req = obs["pending_approvals"][0]
        return AgentAction(
            action_type="approve_request",
            parameters={
                "request_id": req["request_id"],
                "decision": "approved",
                "note": "auto-approved by RB-min",
            },
        )
    return AgentAction(action_type="wait", parameters={})
```

### accountant_d

```python
def rb_min_accountant_decide(obs: dict) -> AgentAction:
    """最小限のルールベース経理。支払可能な注文があれば支払。"""
    if obs["payable_orders"]:
        order = obs["payable_orders"][0]
        return AgentAction(
            action_type="pay_order",
            parameters={
                "order_id": order["order_id"],
                "amount": order["amount"],
            },
        )
    return AgentAction(action_type="wait", parameters={})
```

### vendor_e

```python
def rb_min_vendor_decide(obs: dict) -> AgentAction:
    """最小限のルールベース取引先。注文があれば納品→請求。"""
    # 1. 請求可能な注文（納品済み・未請求）があれば請求
    if obs.get("delivered_not_invoiced"):
        order = obs["delivered_not_invoiced"][0]
        return AgentAction(
            action_type="register_invoice",
            parameters={
                "order_id": order["order_id"],
                "amount": order["amount"],
            },
        )
    # 2. 未納品の注文があれば納品
    if obs.get("my_orders"):
        undelivered = [o for o in obs["my_orders"] if not o.get("delivered")]
        if undelivered:
            order = undelivered[0]
            return AgentAction(
                action_type="deliver",
                parameters={
                    "order_id": order["order_id"],
                    "delivered_amount": order["amount"],
                },
            )
    # 3. 何もなければ待機
    return AgentAction(action_type="wait", parameters={})
```

## 4. 実験手順

### Step 1: RB-minエージェントの実装

`oct/agents/rb_min.py` として実装。各エージェントの`decide`メソッドを上記ロジックで置換する。

LLMClientの呼び出しをスキップし、observationから直接AgentActionを返す。PurchaseDispatcherとrunnerは変更不要（Agentインターフェースが同一のため）。

### Step 2: 実験実行

```
実行する実験（最低限）:
  exp_ablation_rb_baseline:   全RB-min × baseline（閾値20万）
  exp_ablation_rb_intervention: 全RB-min × intervention（閾値500万）

比較対象:
  exp003c: 全LLM × baseline（閾値20万）
  exp004:  全LLM × intervention（閾値500万）

パラメータ: seed=42, demand_seed=42, 20日, actions_per_day=2
```

### Step 3: 比較分析

analyze_trace.py の出力を使い、以下を比較する。

**3a. 介入効果の符号と質**

| 指標 | LLM ATE (exp004-exp003c) | RB ATE (rb_int-rb_base) | 一致？ |
|------|-------------------------|------------------------|-------|
| Requests | | | |
| Payments | | | |
| buyer_a wait | | | |
| buyer_b wait | | | |
| vendor_e wait | | | |
| accountant_d pay | | | |

符号が一致すれば「構造由来」。不一致なら「LLM-mediated」。

**3b. 波及効果の再現**

| 創発事象 | LLMで観察 | RBで観察 | 判定 |
|---------|----------|---------|------|
| S-004 vendor_e間接活性化 | ✅ | ? | |
| S-009 accountant_d活性化 | ✅ | ? | |
| buyer活性化 | ✅ | ? | |
| 重複請求エラー | 1/4 seed | ? | |

**3c. trace variantの比較**

行動系列のパターンが質的に同じか。同じなら構造由来。

## 5. 結果の解釈フレームワーク

| RBの結果 | 解釈 | 研究の方向性 |
|---------|------|------------|
| LLMと同じ波及パターン | 構造由来。LLM不要 | 「実行可能な組織シミュレータ」として位置づけ |
| 符号は同じだが強さが違う | LLMは増幅器/減衰器 | LLMの「calibration価値」を主張 |
| LLMでしか出ない質的な違い | LLMの適応的判断が創発に寄与 | LLMの「発見的価値」を主張 |
| RBのほうが波及が大きい | LLMが波及を抑制している | LLMの「安定化効果」という新しい知見 |

**いずれの結果でもreverse stress testingには進める。** ablationの結果は「LLMをどう位置づけるか」を決めるだけであり、EOMフレームワークの価値自体は不変。

## 6. 今後の拡張（初回ablation後）

初回ablation（全RB vs 全LLM）で「構造由来」と判明した場合:
- 役割別ablation（buyer-only-RB等）は省略可能
- 研究の中心を「executable model + reverse stress testing」に完全移行

初回ablationで「LLMでしか出ない現象がある」場合:
- 役割別ablationで「どの役割でLLMが必要か」を特定
- RB-score, RB-memoryの段階的テストで「LLMのどの能力が寄与しているか」を分離
