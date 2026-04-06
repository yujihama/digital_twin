# exp003: 全購買フロー完遂テスト — 結果

> **集計方法**: 本ドキュメントの全数値は `scripts/analyze_trace.py` の出力に基づく。
> 手動集計は行わない。再検証時は `python scripts/analyze_trace.py ../exp003_full_pipeline/trace_seed42.json` を実行すること。

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
| total_steps | 75 | **158** |
| errors | 0 | 0 |
| purchase_requests | 10 | **19** |
| approvals | 0 | **1** |
| orders | 9 | **19** |
| receipts | 9 | **18** |
| invoices | 0 | **18** |
| payments | 0 | **18** |
| demands_fulfilled | 10 | **19** |
| deviation_count | 0 | 0 |
| 三者照合一致 | N/A | **18/18 (100%)** |

**19件中18件が全フロー完遂。** 1件（最終日付近の order）は receipt/invoice/pay に未到達のままシミュレーション終了。

## vendor_id 修正の検証結果

**全19件の draft_request で vendor=vendor_e が使用された。** available_vendors フィールドの追加が有効に機能し、LLM は環境から提供された正しい取引先IDを使用した。

exp002 では LLM が `VND-001` 等の架空IDを生成していたが、exp003 では全件 `vendor_e` を選択。

## エージェント別行動

| agent | draft_request | approve_request | place_order | record_receipt | deliver | register_invoice | pay_order | wait |
|---|---|---|---|---|---|---|---|---|
| buyer_a | 9 | — | 9 | 8 | — | — | — | 9 |
| buyer_b | 10 | — | 10 | 3 | — | — | — | 9 |
| approver_c | — | 1 | — | — | — | — | — | 20 |
| accountant_d | — | — | — | — | — | — | 18 | 16 |
| vendor_e | — | — | — | — | 7 | 18 | — | 11 |

### 重要な観察

1. **buyer_b > buyer_a の積極性（draft）**: buyer_b は draft=10 に対し buyer_a は draft=9。ただし buyer_a は wait=9、buyer_b も wait=9 で均衡している。exp002 の buyer_b 優位傾向は概ね再現。

2. **buyer_a の record_receipt 優位**: buyer_a が record_receipt=8、buyer_b が record_receipt=3。exp002 で指摘した buyer_a の `awaiting_receipt` フィルター非対称性（全注文が見える）の影響が引き続き存在する。

3. **vendor_e の行動パターン**: deliver=7 に対し register_invoice=18。receipt は buyer 側の record_receipt (11件) と vendor_e の deliver (7件) の合計18件。vendor_e は納品よりも請求書発行を多く実行した。

4. **承認は1件のみ**: req_00005 のみ承認閾値（100万円）を超えた。approver_c は承認対象を正しく識別し、「閾値超過案件で優先処理。金額は妥当範囲内で分割発注の疑いなし」と判断根拠を記録。介入実験のベースラインとしては承認対象が少なすぎるため、閾値引き下げが必要。

5. **三者照合 100% 一致**: deviation_count=0。vendor_e は全件で発注金額と同額の納品・請求を行い、誠実な取引パターンを選択した。

6. **1件未完遂**: 19件の order のうち1件が receipt/invoice/pay に到達せずシミュレーション終了。日数（20日）の制約による。

## exp001→exp002→exp003 の進歩

| 実験 | 主な変更 | 結果 |
|---|---|---|
| exp001 | ベースライン（需要なし） | 全員 wait×15日 |
| exp002 | DemandConfig 追加 | buyer 活性化、draft→order→receipt まで到達 |
| exp003 | available_vendors 追加 + actions/day=2 | **19件中18件が draft→pay 完遂** |

## 次のステップ

- [ ] 承認閾値を50万円程度に引き下げて exp003 を再実行（承認フローの十分なベースライン確保）
- [ ] buyer_a awaiting_receipt フィルター非対称性の修正判断
- [ ] 介入実験（承認閾値 100万→500万への変更で行動がどう変わるか）
- [ ] 複数 seed での再現性検証
