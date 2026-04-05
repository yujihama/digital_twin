# exp001 — First Live 5-Agent Run (OpenAI gpt-4.1-mini)

初めての実LLM実行。OCTフレームワークが実API出力に対して動作することを確認する最小実験。

## 設定

| 項目 | 値 |
| --- | --- |
| experiment_id | `exp001_first_live_run` |
| LLM provider | OpenAI |
| model | `gpt-4.1-mini` |
| agents | 5 (`buyer_a`, `buyer_b`, `approver_c`, `accountant_d`, `vendor_e`) |
| max_days | 15 |
| actions_per_agent_per_day | 1 |
| temperature | 0.8 |
| shuffle_agents | `True` |
| rng_seed | 42 |
| wait_ends_turn | `True` (default) |
| trace file | `trace_seed42.json` |
| 実行日 | 2026-04-06 |

## 結果サマリー

| 指標 | 値 |
| --- | --- |
| total_steps | 75 (5 agents × 15 days × 1 action) |
| dispatched_ok | 75 |
| errors | 0 |
| api_call_count | 75 |
| final snapshot: deviation_count | 0 |
| final snapshot: error_count | 0 |
| purchase_requests | **0** |
| approvals | **0** |
| orders | **0** |
| receipts | **0** |
| invoices | **0** |
| payments | **0** |

**結論**: フレームワーク（env / runner / dispatcher / persona / LLMClient / trace logger）は**実LLM出力に対してエラーなく動作**した。OpenAI API 呼び出し 75 回すべてが正常にパース・dispatch された。

しかし — **15日間で業務活動がゼロ**。全75アクションが `wait` だった。

## 観察された行動パターン

### 全エージェント: `wait` 一択 (15/15)

| agent_id | wait | その他 |
| --- | --- | --- |
| buyer_a | 15 | 0 |
| buyer_b | 15 | 0 |
| approver_c | 15 | 0 |
| accountant_d | 15 | 0 |
| vendor_e | 15 | 0 |

### reasoning に出現した典型パターン (buyer_a の例)

- 「現時点で対応すべき案件が見られないため待機します」
- 「今回、新規要求するものがないため待機するのが合理的」
- 「現在処理すべき案件が見られない、新たな購入要求がないため待機」
- 「新規要求や発注待ち案件の待ちがない、優先すべきタスクがない」

### 各ペルソナの観察内容 (day 0)

- **buyer_a**: `my_requests=[]`, `ready_to_order_request_ids=[]`, `awaiting_receipt_orders=[]` → **タスクが0件**
- **accountant_d**: `payable_orders=[]` → 支払う対象なし
- **approver_c**: `pending_approvals=[]` → 承認対象なし
- **vendor_e**: 自分の受注なし → 何もできない
- **buyer_b**: `peer_recent_requests=[]`, `my_requests=[]` → 参照元もなく自身のタスクもない

## 発見された問題・課題

### 問題1: 外因トリガーの欠如 (critical)

全ペルソナが「タスクが来たら動く」受動型の system prompt で設計されており、**業務の起点となる内在的動機 (business need) を持たない**。buyer系が draft_request を出さない限り承認も発注も発生しないため、システム全体がデッドロック状態に陥る。

結果: **DAG-free な因果推論**どころか、因果連鎖そのものが発生しない。

### 問題2: observation の情報密度不足

day 0 の buyer_a observation には「まだ何もないので何もしない」という解釈以外の余地がない。現実の購買担当者は次のような情報に基づいて起票する:
- 在庫レベル / 消費ペース / リードタイム
- 部署からの購買依頼
- カレンダー上のイベント（月次補充など）

現行 observation にはこれらが一切ない。

### 問題3: wait_ends_turn × actions_per_agent_per_day=1 の組み合わせ

`actions_per_agent_per_day=1` なので `wait_ends_turn` は実質的に無効化されている（1アクションで必ず turn が終わる）。これは exp001 単独では問題ないが、将来 actions_per_agent_per_day を増やす際の影響を T-008/T-009 で再確認する必要がある。

## 得られた肯定的な結果

1. `OpenAIClient` の retry / api_key / .env (BOM対応後) 読み込みがすべて動作
2. `shuffle_agents=True, rng_seed=42` の毎日シャッフルが想定通り機能
3. 75 回の LLM 出力のうち**すべてが正しい JSON action にパースされた** (parse error 0)
4. dispatcher が `wait` を正しく dispatched_ok=True として記録
5. trace JSON が snapshot + 75 steps の構造で保存され、後段の分析に耐える粒度を確保

つまり**パイプラインは健全**。足りないのは「動機設計」。

## 次アクション (新しい論点)

- **[新issue]** ペルソナに内在的ニーズ生成機構を入れる (Option A: observation 側に「在庫」「未消化予算」等の environment state を追加 / Option B: system prompt に "あなたはXX部門担当、月次でN件の発注が必要" を仕込む / Option C: 環境側で tick ごとに内因イベントを生成)
- **[既存T-008/T-009への影響]** 介入設計は「動機ありの状態」からの分岐として定義する必要がある。現状の stateless observation のままでは介入前のベースライン挙動が自明すぎる (何もしない)
- **再実験案 exp002**: 最小限の「動機注入」を加え、同じ seed=42 で比較する (exp001をベースライン記録として保存)

## Sources

- Trace: [trace_seed42.json](./trace_seed42.json)
