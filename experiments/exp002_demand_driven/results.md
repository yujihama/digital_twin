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

## 結果サマリー（トレースから再集計）

| 指標 | exp002 | exp001 | 変化 |
| --- | --- | --- | --- |
| total_steps | 75 | 75 | - |
| dispatched_ok | 75 | 75 | - |
| errors | 0 | 0 | - |
| api_call_count | 75 | 75 | - |
| **purchase_requests** | **10** | 0 | **+10** |
| approvals | 0 | 0 | - |
| **orders** | **9** | 0 | **+9** |
| **receipts** | **9** | 0 | **+9** |
| invoices | 0 | 0 | - |
| payments | 0 | 0 | - |
| demands_total | 31 | - | 新規 |
| demands_pending | 21 | - | 新規 |
| demands_fulfilled | 10 | - | 新規 |

**結論**: 需要生成メカニズムにより、buyer 系エージェントのデッドロックは**完全に解消**された。
10件の購買要求が起票され、9件の発注、9件の受領まで進行。因果連鎖の起点が正常に機能している。

## 観察された行動パターン

### エージェント別アクション内訳（トレースから集計）

| agent_id | draft_request | place_order | record_receipt | wait | 合計 |
| --- | --- | --- | --- | --- | --- |
| buyer_a | 4 | 3 | 6 | 2 | 15 |
| buyer_b | 6 | 6 | 3 | 0 | 15 |
| approver_c | 0 | 0 | 0 | 15 | 15 |
| accountant_d | 0 | 0 | 0 | 15 | 15 |
| vendor_e | 0 | 0 | 0 | 15 | 15 |

### buyer_b の行動パターン（15/15日アクティブ、wait=0）

**ペルソナの予測に反し、buyer_b（勤続2年の新人）が最も積極的だった。** draft_request=6件はbuyer_a（4件）を上回る。

- day 0: draft_request（切削油 20L, 106,714円, dem_00001）
- day 1: place_order（req_00001）
- day 2: record_receipt（ord_00001, 106,714円）
- day 3: draft_request（安全手袋 100双, 28,417円, dem_00002）
- day 6: draft_request（USBメモリ 50個, 78,556円, dem_00008）
- day 8: draft_request（コピー用紙 A4 50箱, 39,080円, dem_00012）
- day 10: draft_request（ボルトセット M8, 47,589円, dem_00013）
- day 12: draft_request（安全手袋 100双, 31,070円, dem_00019）

**注目**: buyer_b は全15日間 wait を選ばなかった。ペルソナに「慎重」「waitを選びやすい」と設定しているにもかかわらず、需要があると即座に対応する傾向を示した。これはpending_demandsの存在が行動の「理由」を与え、慎重さよりも「対応すべきタスクがある」というシグナルが優先された可能性がある。

### buyer_a の行動パターン（13/15日アクティブ、wait=2）

buyer_a は draft_request=4件だが record_receipt=6件と受領処理が多い。

- day 1: draft_request（検査用ゲージ, 202,654円, dem_00003）
- day 2: place_order（req_00002）
- day 3: record_receipt（ord_00002, 202,654円）
- day 4: draft_request（ボルトセット M8, 57,000円, dem_00006）
- day 8: record_receipt（ord_00005, 78,556円 — **buyer_b の注文**）
- day 9: record_receipt（ord_00006, 39,080円 — **buyer_b の注文**）
- day 12: record_receipt（ord_00007, 47,589円 — **buyer_b の注文**）

**重要な発見: buyer_a は buyer_b が発注した注文（ord_00005, ord_00006, ord_00007）の受領処理を実行している。** これは buyer_a の `build_observation` の `awaiting_receipt_orders` フィルターが `requester` で絞り込んでいないことが原因（buyer_b は自分の注文のみ表示する設計）。buyer_a には全注文の未受領分が見え、buyer_b には自分の注文のみが見える非対称性がある。

この非対称性は PR#4 時点からの設計であり、「先輩が後輩の受領を代行する」という解釈も可能だが、意図的な設計かバグかは判断が必要。buyer_a の record_receipt=6 のうち 3件は他人の注文であるため、「buyer_a がより多くの receipt を処理した」のは積極性ではなく observation の非対称性に起因する。

### approver_c / accountant_d / vendor_e — 全日 wait

3エージェントが15日間waitのまま。原因は明確:

- **approver_c**: 全10件の購買要求が承認閾値（100万円）未満のためauto-approve → 承認対象なし
- **vendor_e**: 注文は存在するが、buyer が指定した vendor_id（vendor_01, vendor_001 等）は vendor_e ではない → 自身に関連する注文が見えない
- **accountant_d**: invoice が 0 件 → 支払い対象なし（vendor_e が動かないためinvoice未発行）

## 発見された問題・課題

### 問題1: vendor_id の不一致（重要）

buyer_a/buyer_b が指定する vendor_id（vendor_01, vendor_001 等）は LLM が自由に生成した値であり、シミュレーション内の `vendor_e` agent_id と一致しない。結果として:
- vendor_e は「自分宛の注文がない」と判断して wait
- deliver / register_invoice が発生しない
- 支払いプロセスに到達できない

**対策案**: buyer の observation に「利用可能な取引先 = vendor_e」を明示する。プロトタイプ段階では vendor_e 1社で十分。将来的には複数 vendor 追加や demand_event への suggested_vendor 追加で拡張可能。

### 問題2: 承認フローの未テスト

全購買要求が100万円未満でauto-approveされたため、approver_c のフローが一切テストされていない。

**対策案**: DemandConfig のカタログに100万円以上の品目を増やす、あるいは approval_threshold を引き下げて介入実験の一環として設計する。

### 問題3: buyer_a の awaiting_receipt フィルター非対称性

buyer_a は全注文の未受領分が見え、buyer_b は自分の注文のみが見える。この非対称性は創発パターンの解釈に影響する:
- buyer_a の record_receipt=6 のうち 3件は buyer_b の注文
- 「buyer_a がより積極的に受領処理をした」のではなく「他人の注文が見えていたから」

意図的な設計（先輩権限）かバグかの判断が必要。

### 問題4: ペルソナ特性と実行動の乖離

buyer_b（慎重・新人）が buyer_a（効率重視・ベテラン）より積極的（draft=6 vs 4、wait=0 vs 2）。考えられる原因:
- pending_demands の存在が「行動すべき理由」として機能し、ペルソナの慎重さを上書きした
- gpt-4.1-mini がペルソナの微妙なニュアンスを十分に反映できていない可能性
- temperature=0.8 の設定下でのペルソナ差の現れ方を T-013 で検証する必要がある

### 問題5: 需要消化率（10/31 = 32.3%）

31件の需要のうち10件消化。actions_per_agent_per_day=1 の制約下で buyer 2名 × 15日 = 最大30アクション。draft→order→receipt の3ステップで1需要消化とすると理論最大は10件。つまり buyer の処理能力は上限近くまで活用されている。

## exp001 → exp002 比較まとめ

| 指標 | exp001 | exp002 | 判定 |
| --- | --- | --- | --- |
| buyer行動 | 全wait | draft/order/receiptが活発 | ✅ 改善 |
| 因果連鎖 | 未発生 | draft→order→receipt まで到達 | ✅ 改善 |
| 全フロー完遂 | N/A | order→deliver→invoice→pay 未到達 | ⚠️ 次課題 |
| エージェント間相互作用 | なし | buyer_a が buyer_b の注文を受領（非対称性起因） | ⚠️ 要判断 |
| ペルソナ差 | なし | buyer_b > buyer_a（予測に反する） | ⚠️ 要検証 |

## 得られた肯定的な結果

1. **需要生成メカニズム（Option A+C）が機能**: 環境が状態を提供し、LLMが判断するという原則が保たれたまま、デッドロックが解消された
2. **demand_id 紐付けが正常動作**: LLMが observation 内の demand 情報を理解し、draft_request 時に demand_id を正しく指定（10件 fulfilled）
3. **パイプライン前半は健全**: draft_request → place_order → record_receipt のサイクルが自然に回る
4. **0 errors**: フレームワーク全体が需要生成を含めてもエラーなく動作
5. **需要処理の効率**: 理論上限に近い消化率（10/31、3ステップ×10件=30アクション≒buyer能力上限）

## 次アクション

1. **vendor_id 問題の解決**: buyer observation に利用可能取引先リスト（vendor_e）を追加
2. **exp003**: vendor_id 修正後、全フロー（draft→approve→order→deliver→invoice→pay）の完遂を目指す
3. **buyer_a awaiting_receipt フィルター**: 非対称性を意図的設計として残すかバグとして修正するか判断
4. **ペルソナ差の検証**: T-013 で temperature / model 差による行動パターンの変動を確認
5. **T-008/T-009 への接続**: 全フロー完遂後、介入実験（承認閾値 100万→500万）の設計に進む

## Sources

- Trace: [trace_seed42.json](./trace_seed42.json)
- 比較元: [exp001 results](../exp001_first_live_run/results.md)
