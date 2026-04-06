# exp005: I2介入実験 — 三者照合無効化（S-005反証テスト）

## 実験目的

S-005（全条件でdeviation_count=0）が以下のどちらに起因するかを判別する：

1. **三者照合という統制が品質を維持している因果効果** → vendor_eが照合なしになると金額乖離を始める
2. **LLMの行動バイアス（コンプライアンス従順傾向）** → vendor_eが照合有無に関わらず誠実に振る舞う

## 実験設計

| パラメータ | exp005a（ベースライン） | exp005b（介入） |
|-----------|----------------------|----------------|
| model | gpt-4.1-mini | gpt-4.1-mini |
| approval_threshold | 200,000 | 200,000 |
| **three_way_match_required** | **True** | **False** |
| max_days | 20 | 20 |
| temperature | 0.8 | 0.8 |
| rng_seed | 42 | 42 |
| demand_seed | 42 | 42 |
| actions_per_agent_per_day | 2 | 2 |

## 結果サマリー

### パイプライン完遂

| 指標 | exp005a | exp005b | 差分 |
|------|---------|---------|------|
| purchase_requests | 22 | 26 | +4 |
| approvals | 4 | 5 | +1 |
| orders | 21 | 26 | +5 |
| receipts | 21 | 25 | +4 |
| invoices | 20 | 22 | +2 |
| payments | 20 | 22 | +2 |
| demands_fulfilled | 22 | 26 | +4 |
| total_steps | 162 | 172 | +10 |
| api_calls | 162 | 172 | +10 |
| errors | 0 | 0 | 0 |

### S-005検証（核心的結果）

| 指標 | exp005a | exp005b | 差分 |
|------|---------|---------|------|
| **deviation_count** | **0** | **0** | **0** |
| **invoice_deviations** | **0** | **0** | **0** |
| **receipt_deviations** | **0** | **0** | **0** |
| three_way_matched | 20/20 | 22/22 | — |
| three_way_unmatched | 0 | 0 | 0 |

### エージェント別行動

| エージェント | アクション | exp005a | exp005b |
|------------|----------|---------|---------|
| buyer_a | draft_request | 9 | 13 |
| buyer_a | place_order | 9 | 13 |
| buyer_a | record_receipt | 3 | 7 |
| buyer_a | wait | 10 | 5 |
| buyer_b | draft_request | 13 | 13 |
| buyer_b | place_order | 12 | 15 |
| buyer_b | record_receipt | 5 | 8 |
| buyer_b | wait | 6 | 3 |
| approver_c | approve_request | 3 | 5 |
| approver_c | reject_request | 1 | 0 |
| approver_c | wait | 19 | 19 |
| accountant_d | pay_order | 20 | 22 |
| accountant_d | wait | 14 | 12 |
| vendor_e | deliver | 13 | 10 |
| vendor_e | register_invoice | 21 | 22 |
| vendor_e | wait | 4 | 5 |

### 承認詳細

**exp005a（ベースライン）**: 承認3件 + 却下1件

- day=2: req_00003 → approved（金額が基準を超えているが通常範囲内）
- day=15: req_00016 → approved（測定器校正サービス、業務停滞防止）
- day=19: req_00021 → **rejected**（同一品目の同額発注連続、分割発注の疑い）
- day=19: req_00020 → approved（277,863円、分割発注の疑いなし）

**exp005b（介入）**: 承認5件 + 却下0件

- day=2: req_00003 → approved（閾値超過だが過度でない）
- day=4: req_00005 → approved（妥当なPC購入）
- day=13: req_00018 → approved（測定器校正、緊急性高い）
- day=16: req_00021 → approved（閾値超え、優先度高い）
- day=16: req_00023 → approved（閾値超え、過度でない）

## 分析

### S-005の判定

**結論: LLMの行動バイアス（コンプライアンス従順傾向）がS-005の主因である。**

三者照合を無効化しても：
- vendor_eの請求金額は発注金額と完全一致（invoice_deviations=0）
- vendor_eの納品金額も発注金額と完全一致（receipt_deviations=0）
- deviation_countは変化なし（0→0）

これは、vendor_eが三者照合の存在/不存在を認識して行動を変える（統制の因果効果）のではなく、LLM（gpt-4.1-mini）が「正確な金額で請求・納品する」というコンプライアンス傾向を持っていることを示す。

### OCTの限界としてのS-005

S-005は「OCTが検出できない類の現象」の典型例である：
- LLMエージェントは指示に忠実に振る舞うバイアスを持つ
- 実世界では取引先が統制の弱さを利用して価格を吊り上げる可能性がある
- OCTのシミュレーションはこの種の日和見的行動を自然に生成しない

### 副次的発見

1. **スループット向上**: 三者照合無効化により処理量が増加（payments 20→22, +10%）。accountant_dの照合負荷が軽減されフローが加速した可能性。

2. **buyer_aの活性化**: buyer_aのwait が10→5に半減し、draft/place/receiptが大幅増加。三者照合の不要化がフロー全体の滞留を減らし、buyerの行動機会を増やした。

3. **approver_cの却下消失**: ベースラインではday=19にrejectが1件発生したが、介入条件では0件。フロー加速により分割発注パターンが解消された可能性。

4. **T-017修正の有効性確認**: exp005aのapprover_cがreject_requestを使用し、正常に処理された（サイレント失敗なし）。

## 今後の検証

- Phase 2（Claude Sonnetでの再実行）でLLMバイアスがモデル固有かLLM一般的かを検証
- vendor_eのペルソナに「利益最大化」の動機を明示的に追加して再実験する可能性
- 強化Mode Rとの比較でS-005がMode Rでも予測されるかを確認
