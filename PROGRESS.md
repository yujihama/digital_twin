# OCT研究 作業管理表

> **運用ルール**: タスクに進捗があるたびに本ファイルを更新し、feature ブランチでコミット → PR 作成 → main にマージする。
> 詳細は [CONTRIBUTING.md](CONTRIBUTING.md) を参照。

最終更新: 2026-04-06 (exp002 results.md 修正 / vendor_id 問題修正 / 97テスト passing)

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
| M3 | 3-5エージェント構成での baseline 実験 (Phase 1) | 2026-05 | 🟢 進行中 |
| M4 | Mode R 回答収集 (Phase 2) | 2026-06 | ⬜ 未着手 |
| M5 | 介入 I1 シミュレーション実行 (Phase 3) | 2026-06 | ⬜ 未着手 |
| M6 | 三層検証プロトコル実施 (Phase 4) | 2026-07 | ⬜ 未着手 |
| M7 | 国内学会発表用の初稿作成 | 2026-08 | ⬜ 未着手 |

状態: ✅ 完了 / 🟢 進行中 / 🟡 次に着手 / ⬜ 未着手 / 🔴 ブロック中

---

## タスクボード

### 🟢 In Progress

_（次のPRで着手）_

### 🟡 Next Up

- [ ] **T-008** Mode R 質問プロンプト設計 + 回答構造化
- [ ] **T-009** 介入 I1（承認閾値 100万→500万）実装

### ⬜ Backlog

- [ ] **T-005** Observation Logger の実装（JSONL 形式での全状態遷移記録）
  - T-013 の baseline 実験までに必要。現在は trace を in-memory で保持するのみ。
- [ ] **T-010** Layer 1: Emergence Ratio 算出スクリプト
- [ ] **T-011** Layer 2: 経路依存性テスト（CV算出）
- [ ] **T-012** Layer 3: 相互作用遮断モードの実装
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
- [x] **exp002** 需要生成あり実LLM再実行。buyer デッドロック解消を確認（purchase_requests=8, orders=8, receipts=7）。vendor_id 不一致・承認フロー未到達を次課題として特定（2026-04-06）

---

## 直近の更新履歴

| 日付 | 更新内容 | コミット / PR |
|------|---------|--------------|
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
| Agent | LLMエージェントの思考・行動選択 | **汎用**（環境非依存） | `oct/agent.py`（予定） |
| Runner | シミュレーションループ・ステップ進行 | **汎用**（環境非依存） | `oct/runner.py`（予定） |
| Logger | 観測イベントのJSONL記録 | **汎用**（環境非依存） | `oct/logger.py`（予定） |

**目指す姿**: 将来新しい業務ドメインを追加する際に、`oct/environment.py` / `oct/rules.py` の差し替えのみで agent / runner / logger は変更不要となること。

---

## 進め方の方針（PR#2レビュー反映）

**最速で「環境が動く」ことを確認する**ことを優先する。完璧なプロンプト設計やログ設計は、動くものを見てから調整する。

推奨順序: `T-003（最小プロンプト）→ T-006（APIラッパー）→ T-007（1体5ステップ動作確認）→ T-004（全エージェント追加）→ T-005（ログ整備）`

---

## オープンな論点・意思決定待ち

- **[exp001 由来・解決済み] 内在的動機の設計**: Option A+C を採用し実装・検証済み（exp002 で buyer デッドロック解消を確認）。
- **[exp002 由来・解決済み] vendor_id 不一致**: buyer observation に `available_vendors` フィールドを追加、persona に「available_vendors のIDを使うこと」を明記。exp003 で検証予定。
- **[exp002 由来] 承認フロー未テスト**: 全購買要求が100万円未満でauto-approve → approver_c 未動作。高額品目追加 or 閾値引き下げで対応。
- **[exp001/exp002 由来] 介入設計への影響**: 全フロー（draft→order→deliver→invoice→pay）完遂後に T-008/T-009 に進む。
- **LLMモデル選定**: gpt-4.1-mini でスタート済み。Anthropic（Sonnet / Opus）との比較検証は T-013 以降で実施予定。
- **エージェント人数**: 5体で運用開始（exp001）
- **temperature**: 0.8 を exp001 で採用。0.7 / 1.0 との比較は T-013 のロバストネス確認で実施。
- **失敗ケースの扱い**: LLMが無効なJSONを返したときのフォールバック設計
