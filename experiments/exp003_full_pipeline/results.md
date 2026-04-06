# exp003: 全購買フロー完遂テスト — 結果

## 実験目的

exp002 で発覚した vendor_id 問題（buyer が LLM 生成の vendor ID を使用し vendor_e とマッチしなかった）を PR#11 で修正。buyer の observation に `available_vendors` フィールドを追加し、LLM が正しい vendor_e を選択するかを検証する。

**検証目標**: 全購買フロー（draft→approve→order→deliver→invoice→pay）の少なくとも1件完遂。

## パラメータ

| パラメータ | exp002 | exp003 | 変更理由 |
|---|---|---|---|
| model | gpt-4.1-mini | gpt-4.1-mini | 同一 |
| max_days | 15 | **20** | フロー完遂に必要な日数確保 |
| temperature | 0.8 | 0.8 | 同一 |
| rng_seed | 42 | 42 | 同一 |
| actions_per_agent_per_day | 1 | **2** | vendor_e が deliver+invoice を1日で可能に |
| demand_rng_seed | 42 | 42 | 同一 |
| mean_daily_demands | 1.5 | 1.5 | 同一 |

## 結果サマリー

| 指標 | exp002 | exp003 |
|---|---|---|
| total_steps | 75 | **154** |
| api_call_count | 75 | **154** |
| errors | 0 | 0 |
| purchase_requests | 10 | **18** |
| approvals | 0 | **1** |
| orders | 9 | **18** |
| receipts | 9 | **18** |
| invoices | 0 | **18** |
| payments | 0 | **18** |
| demands_fulfilled | 10 | **18** |
| deviation_count | 0 | 0 |
| 三者照合一致 | N/A | **18/18 (100%)** |

## vendor_id 修正の検証結果

**全18件の draft_request で vendor=vendor_e が使用された。** available_vendors フィールドの追加が有効に機能し、LLM は環境から提供された正しい取引先IDを使用した。

exp002 では LLM が `VND-001` 等の架空IDを生成していたが、exp003 では全件 `vendor_e` を選択。

## パイプライン完遂分析

18件全てが draft→order→receipt→invoice→pay の全フローを完遂した。

### エージェント別行動

| agent | draft | place_order | record_receipt | deliver | register_invoice | approve | pay_order | wait |
|---|---|---|---|---|---|---|---|---|
| buyer_a | 8 | 8 | 6 | — | — | — | — | 11 |
| buyer_b | 10 | 10 | 4 | — | — | — | — | 8 |
| approver_c | — | — | — | — | — | 1 | — | 20 |
| accountant_d | — | — | — | — | — | — | 18 | 15 |
| vendor_e | — | — | — | 8 | 18 | — | — | 9 |

### 重要な観察

1. **buyer_b > buyer_a の積極性**: buyer_b は draft=10, wait=8 に対し buyer_a は draft=8, wait=11。exp002 と同様の傾向が再現された。

2. **vendor_e の行動パターン**: deliver=8 に対し register_invoice=18。receipt は buyer 側の record_receipt (10件) と vendor_e の deliver (8件) の合計18件。vendor_e は納品だけでなく請求書発行も積極的に行った。

3. **承認は1件のみ**: req_00005（ノートPC、1,618,884円）のみ承認閾値（100万円）を超えた。その他17件は閾値以下で自動承認扱い。approver_c は承認対象を正しく識別した。

4. **三者照合 100% 一致**: deviation_count=0。vendor_e は全件で発注金額と同額の納品・請求を行い、誠実な取引パターンを選択した。

5. **buyer_a の receipt 非対称性**: buyer_a が record_receipt=6、buyer_b が record_receipt=4。exp002 で指摘した buyer_a の `awaiting_receipt` フィルター非対称性（全注文が見える）の影響が引き続き存在する可能性がある。

## 日別アクティビティ

Day 0 から即座に buyer_b が draft→order を実行し、vendor_e が同日に deliver→invoice まで完了。Day 1 には accountant_d が最初の pay_order を実行。以降20日間で継続的にフローが回転した。

## exp001→exp002→exp003 の進歩

| 実験 | 主な変更 | 結果 |
|---|---|---|
| exp001 | ベースライン（需要なし） | 全員 wait×15日 |
| exp002 | DemandConfig 追加 | buyer 活性化、draft→order→receipt まで到達 |
| exp003 | available_vendors 追加 + actions/day=2 | **全フロー完遂、18件が draft→pay** |

## 次のステップ

- [ ] buyer_a awaiting_receipt フィルター非対称性の修正判断
- [ ] 介入実験（承認閾値 100万→500万への変更で行動がどう変わるか）
- [ ] 複数 seed での再現性検証
