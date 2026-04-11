# EOM研究 作業管理表

> **運用ルール**: タスクに進捗があるたびに本ファイルを更新し、feature ブランチでコミット → PR 作成 → main にマージする。
> 詳細は [CONTRIBUTING.md](CONTRIBUTING.md) を参照。

> **命名変更（2026-04-07）**: Organizational Causal Twin (OCT) → Executable Organizational Model (EOM)。経緯は docs/08_research_pivot.md を参照。

最終更新: 2026-04-07 (研究方向性転換 / EOMへ改称 / ablation実験計画策定)

---

## 現在のフェーズ

**Phase 1完了 → Phase 2: ablation + reverse stress testing**

上位RQ（改訂版）: 部分観測・逐次実行・状態更新を持つ executable organizational model は、直接質問（Mode R）では見落とされる組織的波及を系統的に露出させるか？ その露出は、特に control-capacity boundary 付近で大きくなるか？

> 旧RQ: LLMマルチエージェントシミュレーションにより組織環境をツインとして構築し、ツインへの介入を通じて、事前のDAG定義なしに、知識想起では検出できない因果関係を発見できるか？

---

## マイルストーン

| # | マイルストーン | 目標時期 | 状態 |
|---|----------------|---------|------|
| M0 | 研究コンセプト・ドキュメント一式 | 2026-04 | ✅ 完了 |
| M1 | 購買承認フロー Environment State 実装 | 2026-04 | ✅ 完了 |
| M2 | 購買担当A単体でのシミュレーション動作確認 | 2026-05 | ✅ 完了 |
| M3 | 3-5エージェント構成での baseline 実験 (Phase 1) | 2026-05 | ✅ 完了 |
| M4 | Mode R 回答収集 (Phase 2) | 2026-06 | ✅ 完了 |
| M5 | 介入 I1 シミュレーション実行 (Phase 3) | 2026-06 | ✅ 完了 |
| M6 | 三層検証プロトコル実施 (Phase 4) | 2026-07 | ✅ 完了（Layer 1-3全完了） |
| **M7** | **ablation: RB-min vs LLMの切り分け** | **2026-04** | **🟢 進行中** |
| M8 | vendor incentive設計 + reverse stress testing | 2026-05 | ⬜ 未着手 |
| M9 | 論文初稿作成 | 2026-08 | ⬜ 未着手 |

状態: ✅ 完了 / 🟢 進行中 / 🟡 次に着手 / ⬜ 未着手 / 🔴 ブロック中

---

## タスクボード

### 🟢 In Progress

- [ ] **T-021** RB-minエージェント実装（`oct/agents/rb_min.py`）+ ablation実験実行（全RB vs 全LLM × baseline/intervention）

### 🟡 Next Up

- [ ] **T-022** vendor incentive設計（Level 2+4: 行動空間固定、state/payoff/memoryを変更）
- [ ] **T-023** reverse stress testing実装（目標: deviation_count > 0 の最小条件集合探索）
- [ ] **T-024** Mode R強化版（段階的推論、自己整合付きbaseline）

### ⬜ Backlog

- [ ] **T-019** Claude Sonnet / gpt-5.4-mini での再実行（ablation結果に依存）
- [ ] **T-020** LLM間比較分析 + QSD算出
- [ ] **T-025** Trace signature分析（付録レベル）
- [ ] **T-005** Observation Logger の実装（JSONL 形式）
- [ ] **T-013** baseline 実験ランナー（N=10回）

### ✅ Done

- [x] **T-018 / exp005** I2介入実験（三者照合無効化）。S-005はLLMバイアスと判定。vendor_eは三者照合有無に関わらずdeviation_count=0（2026-04-06）
- [x] **T-017** reject_requestハンドラ追加（2026-04-06）
- [x] **T-015** buyer_a awaiting_receipt非対称性修正（2026-04-06）
- [x] **T-012** Layer 3 相互作用遮断テスト。創発事象の相互作用依存性=0件（2026-04-06）
- [x] **T-016** 複数seed検証。修正Emergence Ratio = 62.5%（2026-04-06）
- [x] **T-008** Mode R 質問プロンプト設計 + Layer 1テスト（2026-04-06）
- [x] **T-010 / T-011** Layer 1-2検証（2026-04-06）
- [x] **T-009 / exp004** 介入実験（閾値500万円）。スループット+21.7%（2026-04-06）
- [x] **exp003c** 承認閾値20万円ベースライン（2026-04-06）
- [x] **exp003b** 承認閾値50万円ベースライン（2026-04-06）
- [x] **exp003** 全購買フロー完遂テスト（2026-04-06）
- [x] **exp002** 需要生成あり実行（2026-04-06）
- [x] **exp001** 初回実LLM実行（2026-04-06）
- [x] **需要生成メカニズム** DemandEvent / DemandConfig / generate_demands（2026-04-06）
- [x] **T-014** OpenAIClient実装（2026-04-06）
- [x] **T-004** 全エージェント実装（2026-04-05）
- [x] **T-007** 最小シミュレーションループ（2026-04-05）
- [x] **T-006** AnthropicClient実装（2026-04-05）
- [x] **T-003** 汎用Agent抽象 + buyer_aペルソナ（2026-04-05）
- [x] **T-002** 状態遷移ルール実装（2026-04-05）
- [x] **T-001** Environment State実装（2026-04-05）
- [x] **T-000** 研究コンセプト・ドキュメント整備（2026-04-05）

---

## 直近の更新履歴

| 日付 | 更新内容 | コミット / PR |
|------|---------|----|
| 2026-04-07 | **研究方向性転換**。外部ヒアリング2回を経て、OCT→EOMに改称。中心主張を「DAG-free因果推論」から「intuition-failure frontierの発見」に変更。ablation実験計画策定。詳細はdocs/08_research_pivot.md | #21 |
| 2026-04-06 | T-018 exp005完了。S-005はLLMバイアスと判定 | #20 |
| 2026-04-06 | T-017/T-015バグ修正 + 実験計画拡張 | #19 |
| 2026-04-06 | T-012 Layer 3完了。創発事象の相互作用依存性=0件 | #18 |
| 2026-04-06 | T-016複数seed検証完了。修正Emergence Ratio=62.5% | #16→#17 |
| 2026-04-06 | T-008 Mode R完了。Layer 1テストでEmergence Ratio=66.7% | #15 |
| 2026-04-06 | T-009介入実験完了。スループット+21.7% | #14→#15 |
| 2026-04-06 | exp003 results.md再集計 + analyze_trace.py導入 | #13 |
| 2026-04-06 | exp003 全フロー完遂 | #12 |
| 2026-04-06 | exp002 results.md修正 + vendor_id問題修正 | #11 |
| 2026-04-06 | exp002 需要生成あり実行 | #10 |
| 2026-04-06 | 需要生成メカニズム実装 | #9 |
| 2026-04-06 | exp001 + OpenAIClient実装 | #8 |
| 2026-04-05 | T-004〜T-007, PR#1〜#7 | #1→#7 |

---

## 論文の構造（確定版、docs/08_research_pivot.md より）

```
主張: 直接質問では見落とされる波及が、部分観測・逐次実行・状態更新を持つ
      executable model では系統的に露出する。
      その露出は、特に control-capacity boundary 付近で大きくなる。

実験:
  1. Query vs Simulation divergence（QSD）
  2. Role-wise policy ablation（structural vs LLM-mediated effect）
  3. Reverse stress testing（risk frontier探索）
  4. Trace signatureの変化（付録レベル）

成果物:
  - risk-condition catalog
  - intuition-failure frontier
  - trace signatures
  - structural vs policy-mediated effect の切り分け
```

---

## オープンな論点・意思決定待ち

- **[最優先] ablationの結果次第で研究の軸が分岐**: ルールベースでも同じ波及 → 実行可能シミュレータの価値。LLM固有の現象あり → LLMのpolicy価値。どちらでもreverse stress testingには進める。
- **Emergence Ratio → QSDへの名称変更**: ドキュメント全体でEmergence RatioをQuery-Simulation Divergence (QSD) に更新。S-005除外後の修正値 = 4/7 = 57.1%。
- **gpt-5.4-miniへの切替え**: ablation後のPhase 2で実施。過去実験の再実行要否はablation結果に依存。
- **vendor incentive設計**: ablation完了後に着手。行動空間は固定（quote_standard, quote_with_fee, delay, partial_ship, split_invoice, dispute, comply）。state/payoff/memoryのみ変更。
- **プロセスマイニング閉ループ**: 最初の論文では付録レベル。trace-signature実証のみ。
- **命名**: システム名=EOM、方法名=Organizational Reverse Stress Testing、評価名=QSD。
