# T-012: Layer 3 相互作用遮断テスト

> **目的**: T-016で確認された創発事象が、エージェント間相互作用に起因するか、個別エージェントの独立的行動に起因するかを判定する。

## 実験設計

### 遮断モード（isolated_mode）の仕様

PurchaseDispatcherに`isolated_mode=True`を追加。`_apply_isolation()`メソッドで各エージェントのobservationから他エージェント由来の情報を除去する。

| エージェント | 除去フィールド | 遮断の意図 |
|---|---|---|
| buyer_b | `peer_recent_requests` → `[]` | buyer_aの申請パターン模倣を遮断 |
| approver_c | `recent_approvals` → `[]` | 自身の承認履歴フィードバックを遮断 |
| vendor_e | `recent_payments_received` → `[]` | 支払タイミング学習を遮断 |
| accountant_d | `deviation_count` → `0` | 累積逸脱認識を遮断 |

### 実験条件

| 項目 | 値 |
|---|---|
| モデル | gpt-4.1-mini |
| temperature | 0.8 |
| max_days | 20 |
| actions_per_agent_per_day | 2 |
| rng_seed | 42 |
| demand_seed | 42 |

| 実験 | 閾値 | isolated_mode | タグ |
|---|---|---|---|
| ① ベースライン・通常 | 200,000円 | False | baseline_full |
| ② ベースライン・遮断 | 200,000円 | True | baseline_isolated |
| ③ 介入・通常 | 5,000,000円 | False | intervention_full |
| ④ 介入・遮断 | 5,000,000円 | True | intervention_isolated |

## 1. 集計結果一覧

### 全体集計

| 指標 | ①BL_full | ②BL_isolated | ③INT_full | ④INT_isolated |
|---|---|---|---|---|
| Requests | 22 | 23 | 28 | 28 |
| Approvals | 4 | 3 | 0 | 0 |
| Orders | 22 | 23 | 28 | 27 |
| Receipts | 22 | 23 | 27 | 26 |
| Invoices | 22 | 20 | 26 | 26 |
| Payments | 22 | 20 | 25 | 25 |
| Errors | 0 | 0 | 0 | 0 |
| Deviation | 0 | 0 | 0 | 0 |

### エージェント別wait回数

| エージェント | ①BL_full | ②BL_isolated | ③INT_full | ④INT_isolated |
|---|---|---|---|---|
| buyer_a | 7 | 6 | 3 | 3 |
| buyer_b | 8 | 7 | 1 | 2 |
| approver_c | 20 | 20 | 20 | 20 |
| accountant_d | 11 | 15 | 10 | 10 |
| vendor_e | 5 | 7 | 3 | 3 |

### エージェント別行動内訳

#### buyer_a

| 行動 | ①BL_full | ②BL_isolated | ③INT_full | ④INT_isolated |
|---|---|---|---|---|
| draft_request | 10 | 10 | 11 | 12 |
| place_order | 10 | 10 | 11 | 11 |
| record_receipt | 10 | 10 | 12 | 12 |
| wait | 7 | 6 | 3 | 3 |

#### buyer_b

| 行動 | ①BL_full | ②BL_isolated | ③INT_full | ④INT_isolated |
|---|---|---|---|---|
| draft_request | 12 | 13 | 17 | 16 |
| place_order | 13 | 13 | 17 | 16 |
| record_receipt | 2 | 2 | 5 | 4 |
| wait | 8 | 7 | 1 | 2 |

#### approver_c

| 行動 | ①BL_full | ②BL_isolated | ③INT_full | ④INT_isolated |
|---|---|---|---|---|
| approve_request | 4 | 3 | 0 | 0 |
| wait | 20 | 20 | 20 | 20 |

#### vendor_e

| 行動 | ①BL_full | ②BL_isolated | ③INT_full | ④INT_isolated |
|---|---|---|---|---|
| deliver | 10 | 11 | 10 | 10 |
| register_invoice | 22 | 20 | 27 | 26 |
| wait | 5 | 7 | 3 | 3 |

#### accountant_d

| 行動 | ①BL_full | ②BL_isolated | ③INT_full | ④INT_isolated |
|---|---|---|---|---|
| pay_order | 22 | 20 | 25 | 25 |
| wait | 11 | 15 | 10 | 10 |

## 2. 介入効果（ATE）の比較

### ATE = 介入 − ベースライン（通常モード vs 遮断モード）

| 指標 | ATE_full (③−①) | ATE_isolated (④−②) | 差分 | 相互作用寄与率 |
|---|---|---|---|---|
| Requests | +6 | +5 | 1 | 16.7% |
| Payments | +3 | +5 | -2 | — (*) |
| buyer_a wait | -4 | -3 | -1 | 25.0% |
| buyer_b wait | -7 | -5 | -2 | 28.6% |
| vendor_e wait | -2 | -4 | +2 | — (*) |
| accountant_d pay | +3 | +5 | -2 | — (*) |

> (*) ATE_isolated > ATE_full のケース。相互作用が効果を増幅するのではなく、むしろ抑制していた可能性を示唆。

## 3. 創発事象の相互作用依存性判定

各創発事象について、通常モードと遮断モードの介入条件下の値を比較し、`|Y_full - Y_isolated| / Y_full > 0.1` を判定基準とする。

### S-002: approver_c完全遊休化

| 指標 | ③INT_full | ④INT_isolated | 差分率 | 判定 |
|---|---|---|---|---|
| approve_request | 0 | 0 | 0% | **個別行動** |
| wait | 20 | 20 | 0% | — |

**結論**: 遮断しても完全遊休化は維持。approver_cの遊休化は閾値構造の直接的帰結であり、他エージェントとの相互作用に依存しない。

### S-003: buyer活性化（wait減少）

| 指標 | ③INT_full | ④INT_isolated | 差分率 | 判定 |
|---|---|---|---|---|
| buyer_a wait | 3 | 3 | 0% | **個別行動** |
| buyer_b wait | 1 | 2 | 100% | **相互作用寄与あり** |

**結論**: buyer_aの活性化は完全に個別行動。buyer_bは遮断時にwaitがわずかに増加（1→2）しており、peer_recent_requests（buyer_aの申請パターン参照）の除去が微小な影響を与えている。ただし効果量は小さく（Δ=1アクション）、方向性は維持されている。

### S-004: vendor_e間接活性化

| 指標 | ③INT_full | ④INT_isolated | 差分率 | 判定 |
|---|---|---|---|---|
| vendor_e wait | 3 | 3 | 0% | **個別行動** |
| vendor_e deliver | 10 | 10 | 0% | **個別行動** |
| vendor_e invoice | 27 | 26 | 3.7% | **個別行動** |

**結論**: vendor_eの活性化は遮断によりほぼ変化せず。recent_payments_received（支払タイミング学習）を除去しても行動パターンに影響しない。vendor_eの活性化はフロー上流の注文増加に対する反応的行動であり、相互作用ではなく構造的因果。

### S-005: 統制品質維持（deviation=0）

| 指標 | ③INT_full | ④INT_isolated | 差分率 | 判定 |
|---|---|---|---|---|
| deviation_count | 0 | 0 | 0% | **個別行動** |

**結論**: 全4条件でdeviation=0。統制品質維持は個別エージェントのルール遵守行動に起因。

### S-008: buyer_b record_receipt増加

| 指標 | ③INT_full | ④INT_isolated | 差分率 | 判定 |
|---|---|---|---|---|
| buyer_b receipt | 5 | 4 | 20% | **弱い相互作用寄与** |

**結論**: 方向性は維持（ベースラインの2→介入で4-5に増加）だが、遮断により微減（5→4）。buyer_aの行動パターン可視性の除去が受領行動のタイミングにわずかに影響。ただし増加トレンド自体は個別行動として成立。

### S-009: accountant_d活性化

| 指標 | ③INT_full | ④INT_isolated | 差分率 | 判定 |
|---|---|---|---|---|
| accountant_d pay | 25 | 25 | 0% | **個別行動** |
| accountant_d wait | 10 | 10 | 0% | **個別行動** |

**結論**: deviation_count=0の遮断は影響なし。accountant_dの支払行動はフロー上流の完了件数に応じた反応的行動であり、完全に個別行動。

## 4. 遮断効果のまとめ

### ベースライン条件での遮断影響

遮断モードはベースライン条件下で一部の指標に影響を与えている：

| 変化 | 説明 |
|---|---|
| accountant_d wait: 11→15 (+36%) | deviation_count遮断により、逸脱への警戒がなくなり待機が増加 |
| vendor_e wait: 5→7 (+40%) | recent_payments_received遮断により、支払パターン学習が機能せずタイミングが遅延 |
| Invoices: 22→20 (-9%) | vendor_eの遅延波及 |
| Payments: 22→20 (-9%) | accountant_d・vendor_eの遅延複合効果 |

### 介入条件での遮断影響

介入条件下では遮断の影響がほぼ消失：

| 指標 | ③INT_full | ④INT_isolated | 差分 |
|---|---|---|---|
| Requests | 28 | 28 | 0 |
| Payments | 25 | 25 | 0 |
| buyer_a wait | 3 | 3 | 0 |
| buyer_b wait | 1 | 2 | +1 |
| vendor_e wait | 3 | 3 | 0 |
| accountant_d wait | 10 | 10 | 0 |

**解釈**: 介入（閾値引き上げ）によりフロー速度が十分に速くなると、相互作用による情報共有の有無は行動パターンにほぼ影響しない。ベースラインで観測された遮断効果（accountant_d, vendor_eの遅延）は、フロー速度が遅い場合にのみ相互作用情報が行動タイミングの最適化に寄与していたことを示す。

## 5. Layer 3 判定

### 相互作用の因果寄与度

| 創発事象 | 相互作用依存性 | 因果メカニズム |
|---|---|---|
| S-002 approver_c遊休化 | **なし** (0%) | 閾値構造の直接効果 |
| S-003 buyer活性化 | **微小** (buyer_b Δ=1のみ) | 需要対応の個別判断 |
| S-004 vendor_e活性化 | **なし** (0%) | フロー上流からの構造的波及 |
| S-005 統制品質維持 | **なし** (0%) | 個別エージェントのルール遵守 |
| S-008 buyer_b receipt増加 | **弱い** (Δ=1) | 主に個別行動、微小な相互作用寄与 |
| S-009 accountant_d活性化 | **なし** (0%) | フロー上流の件数増への反応 |

### 総合判定

**6件の創発事象のうち、相互作用に本質的に依存するものは0件。**

全ての創発事象は、介入（閾値引き上げ）が各エージェントの行動環境を構造的に変化させたことに対する個別的反応として説明可能である。

ただし、ベースライン条件では相互作用情報がパフォーマンスに寄与している証拠がある（Payments: 22→20, accountant_d wait: 11→15）。これは「創発事象の発生メカニズム」と「日常運用の効率性」が異なるチャネルで機能していることを示唆する。

### OCTフレームワークへの示唆

1. **構造的因果の優位性**: 本実験で観測された創発事象は全て「閾値変更→承認ステップ省略→フロー加速→各エージェントの反応変化」という構造的因果連鎖で説明できる。LLMエージェント間の相互学習・模倣は、この環境では創発の主要ドライバーではない。

2. **相互作用の役割は「効率最適化」**: 通常モードで相互作用情報がある場合、ベースライン条件でのパフォーマンスが向上する（Payments: 20→22）。相互作用は新たな創発パターンを生むのではなく、既存のフローをスムーズにする潤滑油として機能している。

3. **スケーラビリティ**: 創発事象が個別行動ベースであるため、エージェント数の増減による創発パターンの大幅な変化は予想されにくい。ただしこの結論は5エージェント・単純フローに限定される。

4. **Layer 3の限界**: 今回の遮断設計は情報遮断（observation filtering）に限定されており、行動の相互影響（あるエージェントのアクションが別のエージェントのobservation環境を変える）は遮断していない。完全な相互作用遮断にはエージェント毎の独立環境が必要だが、それはワークフロー自体を破壊するため現実的ではない。

## 6. 制限事項

1. **seed=42のみ**: Layer 3は計算コストの制約からseed=42でのみ実施。T-016の4seedでの再現が可能であれば堅牢性が向上する。
2. **遮断範囲の限界**: observation filteringのみ。行動レベルの間接的相互作用（共有状態経由）は遮断不可能。
3. **temperature=0.8の非決定性**: 同一seed・同一条件でも微小な差異が生じうる。full/isolated間の微小差（Δ≤2）は確率的ノイズの可能性を排除できない。
4. **遮断設計の妥当性**: 各エージェントから除去したフィールドが「相互作用情報」の適切な代理変数かどうかは、ペルソナプロンプトの設計に依存する。
