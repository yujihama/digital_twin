# exp002 — 需要生成ありの5エージェント実行（exp001との比較）

exp001で発見された「全員wait」問題への対策として需要生成メカニズム（Option A+C）を
導入した上での再実行。同一seed・同一パラメータで比較可能。

## 設定

| 項目 | 値 | exp001との差分 |
| --- | --- | --- |
| experiment_id | `exp002_demand_driven` | 変更 |
| LLM provider | OpenAI | 同一 |
| model | `gpt-4.1-mini` | 同一 |
| agents | 5 (`buyer_a`, `buyer_b`, `approver_c`, `accountant_d`, `vendor_e`) | 同一 |
| max_days | 15 | 同一 |
| actions_per_agent_per_day | 1 | 同一 |
| temperature | 0.8 | 同一 |
| shuffle_agents | `True` | 同一 |
| rng_seed | 42 | 同一 |
| **demand_config** | **DemandConfig(mean_daily_demands=1.5)** | **新規** |
| **demand_rng_seed** | **42** | **新規** |
| 実行日 | 2026-04-06 | - |

## 結果サマリー

| 指標 | exp002 | exp001 | 変化 |
| --- | --- | --- | --- |
| total_steps | 75 | 75 | - |
| dispatched_ok | 75 | 75 | - |
| errors | 0 | 0 | - |
| api_call_count | 75 | 75 | - |
| **purchase_requests** | **8** | 0 | **+8** |
| approvals | 0 | 0 | - |
| **orders** | **8** | 0 | **+8** |
| **receipts** | **7** | 0 | **+7** |
| invoices | 0 | 0 | - |
| payments | 0 | 0 | - |
| demands_total | 31 | - | 新規 |
| demands_pending | 23 | - | 新規 |
| demands_fulfilled | 8 | - | 新規 |

**結論**: 需要生成メカニズムにより、buyer 系エージェントのデッドロックは**完全に解消**された。
8件の購買要求が起票され、8件の発注、7件の受領まで進行。因果連鎖の起点が正常に機能している。

## 観察された行動パターン

### エージェント別アクション内訳

| agent_id | draft_request | place_order | record_receipt | wait | 合計 |
| --- | --- | --- | --- | --- | --- |
| buyer_a | 5 | 5 | 4 | 1 | 15 |
| buyer_b | 3 | 3 | 3 | 6 | 15 |
| approver_c | 0 | 0 | 0 | 15 | 15 |
| accountant_d | 0 | 0 | 0 | 15 | 15 |
| vendor_e | 0 | 0 | 0 | 15 | 15 |

### buyer_a の行動パターン（14/15日アクティブ）

buyer_a はペルソナ通り「効率重視」で動いた。needs を受けて即座に draft → place_order → record_receipt のサイクルを回す傾向:

- day 1: draft_request（検査用ゲージ, 202,654円, dem_00003に対応）
- day 2: place_order（req_00002）
- day 3: record_receipt（ord_00002, 202,654円）
- day 4: draft_request（ボルトセット M8, 57,000円, dem_00006に対応）
- day 10: draft_request（切削油 20L, 124,060円, dem_00018に対応）
- day 14: draft_request（測定器校正サービス, 945,221円, dem_00024に対応 — 閾値100万未満ギリギリ）

**注目**: buyer_a は demand_id を正しく紐付けている（LLMがobservation内のdemand情報を理解している）。

### buyer_b の行動パターン（9/15日アクティブ）

buyer_b はペルソナ通り「慎重」で、buyer_a ほど積極的ではない:

- draft_request 3件 / place_order 3件 / record_receipt 3件 / wait 6日
- buyer_a の約60%のアクティビティ（ペルソナの勤続2年 vs 8年を反映）

### approver_c / accountant_d / vendor_e — 全日 wait

3エージェントが15日間waitのまま。原因は明確:

- **approver_c**: 全8件の購買要求が承認閾値（100万円）未満のためauto-approve → 承認対象なし
- **vendor_e**: 注文は存在するが、vendor_e の observation は自身の受注のみをスコープとし、buyer が指定した vendor_id（vendor_01, vendor_02 等）は vendor_e ではない → 自身に関連する注文が見えない
- **accountant_d**: invoice が 0 件 → 支払い対象なし（vendor_e が動かないためinvoice未発行）

## 発見された問題・課題

### 問題1: vendor_id の不一致（重要）

buyer_a/buyer_b が指定する vendor_id（vendor_01, vendor_02 等）は LLM が自由に生成した値であり、シミュレーション内の `vendor_e` agent_id と一致しない。結果として:
- vendor_e は「自分宛の注文がない」と判断して wait
- deliver / register_invoice が発生しない
- 支払いプロセスに到達できない

**対策案**: buyer の observation に「利用可能な取引先 = vendor_e」を明示するか、環境の demand_event に vendor 情報を含める。

### 問題2: 承認フローの未テスト

全購買要求が100万円未満でauto-approveされたため、approver_c のフローが一切テストされていない。

**対策案**: DemandConfig のカタログに100万円以上の品目を増やす、あるいは approval_threshold を引き下げて介入実験の一環として設計する。

### 問題3: 需要消化率（8/31 = 25.8%）

31件の需要のうち8件しか消化されていない。actions_per_agent_per_day=1 という制約下で buyer 2名が15日で処理できる最大は30アクション（うち draft は最大15件）なので、消化率25.8%は妥当な範囲だが、urgency=high の需要が放置されているかは要確認。

## exp001 → exp002 比較まとめ

| 指標 | exp001 | exp002 | 判定 |
| --- | --- | --- | --- |
| buyer行動 | 全wait | draft/order/receiptが活発 | ✅ 改善 |
| 因果連鎖 | 未発生 | draft→order→receipt まで到達 | ✅ 改善 |
| 全フロー完遂 | N/A | order→deliver→invoice→pay 未到達 | ⚠️ 次課題 |
| エージェント間相互作用 | なし | buyer_a/buyer_b が同一需要プールを共有 | ✅ 基盤あり |
| 創発パターン | なし | buyer_a がより積極的（ペルソナ反映） | ✅ 観察 |

## 得られた肯定的な結果

1. **需要生成メカニズム（Option A+C）が機能**: 環境が状態を提供し、LLMが判断するという原則が保たれたまま、デッドロックが解消された
2. **demand_id 紐付けが正常動作**: LLMが observation 内の demand 情報を理解し、draft_request 時に demand_id を正しく指定
3. **ペルソナ差の反映**: buyer_a（勤続8年、効率重視）と buyer_b（勤続2年、慎重）の行動量に差が出現
4. **パイプライン前半は健全**: draft_request → place_order → record_receipt のサイクルが自然に回る
5. **0 errors**: フレームワーク全体が需要生成を含めてもエラーなく動作

## 次アクション

1. **vendor_id 問題の解決**: buyer observation に利用可能取引先リストを追加するか、demand_event に vendor_id を含める
2. **exp003**: vendor_id 修正後、全フロー（draft→approve→order→deliver→invoice→pay）の完遂を目指す
3. **承認フローテスト**: 高額品目の追加 or 閾値引き下げで approver_c の動作を確認
4. **T-008/T-009 への接続**: 全フロー完遂後、介入実験（承認閾値 100万→500万）の設計に進む

## Sources

- Trace: [trace_seed42.json](./trace_seed42.json)
- 比較元: [exp001 results](../exp001_first_live_run/results.md)
