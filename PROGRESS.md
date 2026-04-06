# OCT研究 作業管理表

> **運用ルール**: タスクに進捗があるたびに本ファイルを更新し、feature ブランチでコミット → PR 作成 → main にマージする。
> 詳細は [CONTRIBUTING.md](CONTRIBUTING.md) を参照。

最終更新: 2026-04-06 (T-008 Mode R完了 / T-016複数seed検証完了 / Layer 1-2完了 / Emergence Ratio 62.5%確定)

---

## 現在のフェーズ

**Phase 0: 概念設計 → Phase 1: 小規模プロトタイプ着手**

上位RQ: LLMマルチエージェントシミュレーションにより組織環境をツインとして構築し、ツインへの介入を通じて、事前のDAG定義なしに、知識想起では検出できない因果関係を発見できるか？

---

## マイルストーン

| # | マイルストーン | 目標時期 | 状態 |
|---|----------------|---------|------|
| M0 | 研究コンセプト・ドキュメント一式 | 2026-04 | ✅ 完了 |
| M1 | 購買承認フロー Environment State 実装 | 2026-04 | 🟢 進行中 |
| M2 | 購買担当A単体でのシミュレーション動作確認 | 2026-05 | ✅ 完了 |
| M3 | 3-5エージェント構成での baseline 実験 (Phase 1) | 2026-05 | ✅ 完了 |
| M4 | Mode R 回答収集 (Phase 2) | 2026-06 | ✅ 完了 |
| M5 | 介入 I1 シミュレーション実行 (Phase 3) | 2026-06 | ✅ 完了 |
| M6 | 三層検証プロトコル実施 (Phase 4) | 2026-07 | 🟢 進行中（Layer 1-2完了、Layer 3未着手） |
| M7 | 国内学会発表用の初稿作成 | 2026-08 | ⬜ 未着手 |

状態: ✅ 完了 / 🟢 進行中 / 🟡 次に着手 / ⬜ 未着手 / 🔴 ブロック中

---

## タスクボード

### 🟢 In Progress

- [ ] **T-017** reject_request ハンドラ追加またはaction schema明確化（PR#16レビュー指摘。seed=44でapprover_cの8件rejectがサイレント失敗）

### 🟡 Next Up

- [ ] **T-012** Layer 3: 相互作用遮断モードの実装（approver_cの経路依存性の深掘り）
- [ ] **T-015** buyer_a awaiting_receipt フィルター非対称性の修正判断

### ⬜ Backlog

- [ ] **T-005** Observation Logger の実装（JSONL 形式での全状態遷移記録）
  - T-013 の baseline 実験までに必要。現在は trace を in-memory で保持するのみ。
- [ ] **T-013** baseline 実験ランナー（N=10回、50ステップ、複数エージェント）
### ✅ Done

- [x] **T-000** 研究コンセプト・7ドキュメントの整備（2026-04-05）
- [x] **T-001** Environment State スキーマの Python 実装（`experiments/runtime/oct/environment.py`）（2026-04-05）
- [x] **T-002** 状態遷移ルールの実装（承認・三者照合・日次キャパシティ）（2026-04-05）
- [x] **T-003** 購買担当Aペルソナ＆行動選択プロンプト雛形（汎用Agent抽象 + buyer_a persona）（2026-04-05）
- [x] **T-006** Anthropic API 呼び出しラッパー（AnthropicClient + 指数バックオフ・リトライ）（2026-04-05）
- [x] **T-007** 最小シミュレーションループ（runner + PurchaseDispatcher + buyer_a × 5ステップ、56テスト passing）（2026-04-05）
- [x] **T-004** 全エージェント実装（buyer_b / approver_c / accountant_d / vendor_e）＋runner エージェント順ランダム化（shuffle_agents / rng_seed）＋ wait_ends_turn（69テスト passing）（2026-04-05）
- [x] **T-014** OpenAIClient 実装（`oct/llm.py`、LLMClient Protocol 準拠、.env 読み込み、76テスト passing）（2026-04-06）
- [x] **exp001** 初回実LLM実行（OpenAI gpt-4.1-mini × 5 agents × 15 days × seed=42、75 API calls / 0 errors、全エージェント wait のみという重要な発見）（2026-04-06）
- [x] **需要生成メカニズム** DemandEvent / DemandConfig / generate_demands / fulfill_demand を実装。Option A+C（環境が確率的需要を生成 → buyer observation に pending_demands として提示）。95テスト passing（2026-04-06）
- [x] **exp002** 需要生成あり実LLM再実行。buyer デッドロック解消を確認（purchase_requests=10, orders=9, receipts=9）。vendor_id 不一致・承認フロー未到達を次課題として特定（2026-04-06）
- [x] **exp003** 全購買フロー完遂テスト。vendor_id 修正（available_vendors）の有効性を確認。19件中18件が draft→pay 完遂、三者照合 18/18 一致。158 steps / 0 errors（2026-04-06）
- [x] **exp003b** 承認閾値50万円ベースライン。24件中23件完遂、承認2件（ノートPC・測定器校正）、三者照合 23/23 一致。DEMAND_CATALOGの構成上50万超は2品目のみと判明（2026-04-06）
- [x] **exp003c** 承認閾値20万円ベースライン（T-009統制群）。23件中20件完遂、承認3件（検査用ゲージ・測定器校正・検査用ゲージ）、三者照合 20/20 一致（2026-04-06）
- [x] **T-009 / exp004** 介入実験（閾値500万円）。28件中24件完遂、承認0件、三者照合 24/24 一致。スループット+21.7%、vendor_e wait 8→1（間接活性化）、重複請求エラー1件（フロー加速の副作用）（2026-04-06）
- [x] **T-008** Mode R 質問プロンプト設計 + 回答構造化 → Layer 1 創発性テスト完了。gpt-4.1-miniに対し18件のMode R予測を収集。exp004観測との突合でEmergence Ratio = 66.7%（修正前）を算出（2026-04-06）
- [x] **T-010 / T-011** Layer 1 Emergence Ratio算出 + Layer 2 経路依存性テスト。T-008結果のEmergence Ratio算出をT-016と統合して実施（2026-04-06）
- [x] **T-016** 複数seed検証（seed=42-45 × 閾値200k/5M = 8実験）。7/8の創発事象が4seedで再現。S-006（重複請求エラー）は1/4で非再現→確率的ノイズに再分類。修正Emergence Ratio = 62.5%。集計CVは6%未満で堅牢。seed=44のapprover_c reject 8件（サイレント失敗）が経路依存性の重要な証拠（2026-04-06）

---

## 直近の更新履歴

| 日付 | 更新内容 | コミット / PR |
|------|---------|--------------|
| 2026-04-06 | T-016複数seed検証完了。seed=42-45×2閾値=8実験。修正Emergence Ratio=62.5%。reject_requestサイレント失敗を特定。PROGRESS.md更新 | #16→#17 |
| 2026-04-06 | T-008 Mode R完了。18件のLLM知識予測を収集、Layer 1テストでEmergence Ratio=66.7%を算出 | #15 |
| 2026-04-06 | T-009介入実験完了。exp003b（閾値50万）→exp003c（閾値20万）→exp004（閾値500万）。スループット+21.7%、vendor_e間接活性化、三者照合100%維持を確認。PROGRESS.md更新 | #14→#15 |
| 2026-04-06 | exp003 results.md 再集計（analyze_trace.py 導入）。PROGRESS.md 削除セクション復帰 | #13 |
| 2026-04-06 | exp003 全フロー完遂テスト実行。19件中18件が draft→pay 完遂、三者照合 100% 一致。158 steps / 0 errors | #12 |
| 2026-04-06 | exp002 results.md をトレースから再集計して修正（10 req / 9 ord / 9 rcp）。vendor_id 問題修正（available_vendors 追加）。buyer_a receipt 非対称性を記録。97テスト passing | #11 |
| 2026-04-06 | exp002 需要生成あり実行。buyer デッドロック解消（10 requests / 9 orders / 9 receipts）。generate_demands デッドコード修正。vendor_id 不一致・承認フロー未到達を次課題として特定 | #10 |
| 2026-04-06 | 需要生成メカニズム実装（DemandEvent / DemandConfig / generate_demands / fulfill_demand）。Option A+C: 環境が確率的需要を生成し buyer observation に pending_demands として提示。95テスト passing | #9 |
| 2026-04-06 | exp001 初回実LLM実行（gpt-4.1-mini × 5 agents × 15 days × seed=42）。75/75 API calls 成功・parse error 0。全エージェントが wait のみで業務活動ゼロという発見 → 内在的動機設計の必要性が明らかに | #8 |
| 2026-04-06 | T-014 OpenAIClient 実装（gpt-4.1-mini、retry、.env 読み込み、76テスト passing） | #8 |
| 2026-04-05 | T-004 全エージェント実装（buyer_b/approver_c/accountant_d/vendor_e）+ runnerランダム化（69テスト passing） | #7 |
| 2026-04-05 | T-007 最小シミュレーションループ実装（汎用runner + PurchaseDispatcher + demo, 56テスト passing） | #6 |
| 2026-04-05 | T-006 AnthropicClient 実装 + PR#4レビュー反映バグ修正（43テスト passing） | #5 |
| 2026-04-05 | T-003 汎用Agent抽象 + buyer_a persona を実装（31テスト passing） | #4 |
| 2026-04-05 | PR#2 レビュー反映：vendor_e追加・タスク順序変更・スコープ分離原則を追記 | #3 |
| 2026-04-05 | Environment State と状態遷移ルールを Pydantic + pytest で実装（19テスト passing） | #2 |
| 2026-04-05 | 作業管理体制（PROGRESS.md / CONTRIBUTING.md）を整備 | #1 |
| 2026-04-05 | 初期ドキュメント一式を整備、リモートに反映 | 7ae8d5f |

---

## 設計原則：スコープ分離（PR#2レビュー反映）

購買承認フローは OCT プロトタイプの **controlled setting（下限を示す環境）** として位置づける。将来 "購買 + 経費精算 + 在庫管理" のように環境を拡張できるよう、モジュールは以下のレイヤに分離して実装する。

| レイヤ | 役割 | 汎用性 | 該当モジュール |
|-------|------|--------|---------------|
| Domain | 業務ルール・状態・遷移 | **購買承認フロー固有**（OK） | `oct/environment.py`, `oct/rules.py` |
| Agent | LLMエージェントの思考・行動選択 | **汎用**（環境非依存） | `oct/agent.py` |
| Runner | シミュレーションループ・ステップ進行 | **汎用**（環境非依存） | `oct/runner.py` |
| Logger | 観測イベントのJSONL記録 | **汎用**（環境非依存） | `oct/logger.py`（予定） |

**目指す姿**: 将来新しい業務ドメインを追加する際に、`oct/environment.py` / `oct/rules.py` の差し替えのみで agent / runner / logger は変更不要となること。

---

## 進め方の方針（PR#2レビュー反映）

**最速で「環境が動く」ことを確認する**ことを優先する。完璧なプロンプト設計やログ設計は、動くものを見てから調整する。

推奨順序: `T-003（最小プロンプト）→ T-006（APIラッパー）→ T-007（1体5ステップ動作確認）→ T-004（全エージェント追加）→ T-005（ログ整備）`

---

## オープンな論点・意思決定待ち

- **[解決済み] 内在的動機の設計**: Option A+C を採用し実装・検証済み（exp002 で buyer デッドロック解消を確認）。
- **[解決済み] vendor_id 不一致**: available_vendors フィールド追加で解決（exp003 で全件 vendor_e を選択）。
- **[解決済み] 承認フロー不足**: exp003bで閾値50万（承認2件）、exp003cで閾値20万（承認3件）に引き下げてベースライン確立。T-009（exp004: 閾値500万）との比較で介入効果を観測済み。
- **[T-016 由来] reject_requestサイレント失敗**: PurchaseDispatcherに`reject_request`ハンドラが存在せず、seed=44のapprover_cによる8件の却下判断が全て無視されている。ATEの正確な推定に影響する可能性あり。論文化前に対処必要（T-017）。
- **[exp002 由来] buyer_a awaiting_receipt 非対称性**: buyer_a は全注文を見るが buyer_b は自分の注文のみ。意図的設計か修正対象か要判断。
- **[解決済み] 介入設計への影響**: T-008/T-009/T-016で介入実験とLayer 1-2検証を完了。
- **LLMモデル選定**: gpt-4.1-mini でスタート済み。Anthropic（Sonnet / Opus）との比較検証は T-013 以降で実施予定。
- **エージェント人数**: 5体で運用開始（exp001〜exp003）
- **temperature**: 0.8 を exp001〜exp003 で採用。0.7 / 1.0 との比較は T-013 のロバストネス確認で実施。
- **失敗ケースの扱い**: LLMが無効なJSONを返したときのフォールバック設計
