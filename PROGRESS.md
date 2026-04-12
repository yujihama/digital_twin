# EOM研究 作業管理表

> **運用ルール**: タスクに進捗があるたびに本ファイルを更新し、feature ブランチでコミット → PR 作成 → main にマージする。
> 詳細は [CONTRIBUTING.md](CONTRIBUTING.md) を参照。

> **命名変更（2026-04-07）**: Organizational Causal Twin (OCT) → Executable Organizational Model (EOM)。経緯は docs/08_research_pivot.md を参照。

最終更新: 2026-04-11 (T-028 interpretive ambiguity × three-way match tolerance — Phase A で drift 3 件を観測、Phase B で全て吸収)

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
| **M7** | **ablation: Baseline Ladder (L0/L1/L2/L3)** | **2026-04** | **🟢 進行中（L1/L3 20日 sweep 完了、L0/L2 と frontier 探索が次段階）** |
| M8 | vendor incentive設計 + reverse stress testing (frontier) | 2026-05 | 🟢 進行中（T-023 で narrative framing チャネル、T-028 で interpretive ambiguity チャネルの 2 本が独立に deviation_count>0 を誘発。Phase A tolerance=0 で 3 件／15 L3 セル、Phase B tolerance=0.05 で全吸収。seed 幅・tolerance sweep・branch attribution が次段階） |
| M9 | 論文初稿作成 | 2026-08 | ⬜ 未着手 |

状態: ✅ 完了 / 🟢 進行中 / 🟡 次に着手 / ⬜ 未着手 / 🔴 ブロック中

---

## タスクボード

### 🟢 In Progress

- [ ] **T-021** Baseline Ladder ablation。L1 / L3 の 20日 sweep（baseline / I1 / I2 / combined_I1_I2 / high_pressure × seed 42-44）完了（T-022）。narrative framing での L3 再実行（T-023）、interpretive ambiguity × tolerance の 2 phase sweep（T-028）も完了。L0 / L2 の実装と frontier の regime 拡張が残り。

### 🟡 Next Up

- [ ] **T-021d** frontier 探索のための regime 拡張（T-022 で combined_I1_I2 / high_pressure を追加済。次は temperature sweep と narrative framing）。results.md §4.1 参照。
- [ ] **T-024** Temperature sweep（T ∈ {0.5, 0.8, 1.0, 1.3} × high_pressure × seed 5〜10）で opportunistic action 境界を探索（T-022 §6.2）
- [ ] **T-028a** Phase-A anomaly の seed 幅確認（`L3_intervention_I2` / `L3_combined_I1_I2` × ambiguity × seed 42-51）。per-cell drift rate の点推定と seed=43 outlier 検定（T-028 §6）
- [ ] **T-028b** Tolerance sweep（tolerance_rate ∈ {0, 0.005, 0.01, 0.02, 0.03, 0.05} × `L3_intervention_I2` × seed 42-44）で吸収閾値を特定（T-028 §6）
- [ ] **T-028c** Ambiguity branch attribution（tax / prior_adjustment / quantity_spec を 1 つずつ ON、他は default）× `intervention_I2` / `combined_I1_I2` × seed 42-44（T-028 §6）
- [ ] **T-028d** narrative × ambiguity 合成（`L3_high_pressure --narrative --ambiguity` × Phase A × seed 42-44）で 2 チャネルの加法／干渉を検証（T-028 §6）
- [ ] **T-029** Mode R強化版（段階的推論、自己整合付きbaseline）
- [ ] **T-026** frontier可視化（probability field × QSD field、heatmap → contour → PRIM box）
- [ ] **T-027** policy_complexity フィールドのtraceメタデータへの追加

### ⬜ Backlog

- [ ] **T-019** Claude Sonnet / gpt-5.4-mini での再実行（ablation結果に依存）
- [ ] **T-020** LLM間比較分析 + QSD算出
- [ ] **T-025** Trace signature分析（付録レベル）
- [ ] **T-005** Observation Logger の実装（JSONL 形式）
- [ ] **T-013** baseline 実験ランナー（N=10回）

### ✅ Done

- [x] **T-028** interpretive ambiguity × three-way match tolerance probe。`Order` に 3 つの解釈曖昧性フィールド（`tax_included` / `prior_adjustment` / `quantity_spec`）を追加し、`EnvironmentState._ambiguity_rng`（`demand_rng_seed ^ 0xA28B` で seed）で決定的に生成。`three_way_match` に `tolerance_rate` を導入し、実効トレランスを `max(tolerance_abs, amount * tolerance_rate)` に拡張（`tolerance_rate=0` は従来挙動）。`run_ablation.py` に `--ambiguity` / `--tolerance-rate` / `--out` フラグ、`analyze_trace.py` に `analyze_amount_deltas` / `## T-028 PO vs Actual Amount Deltas` セクションを追加。**Phase A（tolerance_rate=0）と Phase B（tolerance_rate=0.05）の 2 phase sweep**（narrative OFF × ambiguity ON × L1/L3 × 5 regime × seed 42-44 × 20日 = 60 セル）を実行。Phase A で 3 件の deviation を観測（`L3_intervention_I2` seed=43 ×2、`L3_combined_I1_I2` seed=43 ×1、いずれも ±2.5% 以内の drift）、Phase B では 5% band に全て吸収されて 0 件。L1 15 セルは両 phase で byte-for-byte 一致、RB-min 不変性を確認。14 件のユニットテスト追加（130→144）。narrative framing（T-023）と直交する第 2 の deviation 誘発チャネルを確立し、「quiet drift」現象を定量化（2026-04-11）
- [x] **T-023** narrative-level vendor framing × deviation frontier probe。`_render_business_context` ヘルパーで `ControlParameters` の 4 incentive フィールドを決定的な日本語の経営状況ナラティブに変換し、`vendor_e.build_observation(narrative_mode=True)` でLLM に渡す（RB-min vendor_e / 他エージェント観測は不変）。`run_ablation.py` に `--narrative` フラグを追加。narrative ON × L1/L3 × {combined_I1_I2, high_pressure} × seed 42-44 × 20日 = 12 セル sweep を実行。**L3_high_pressure で `mean_deviation_count = 0.333`、seed=43 day=2 に 1 件の `deliver_partial`（ord_00002, fraction=0.5, PO=646,130 JPY）**。T-021→T-023 の全系列で初めての非ゼロ deviation で、LLM の reasoning はnarrative のキャッシュプレッシャー分岐を明示的に引用。L1 全 6 セルは T-022 と byte-for-byte 一致、backward-compat を確認。5 件のユニットテスト追加（125→130）。T-022 §6.1 仮説の弱形肯定（2026-04-11）
- [x] **T-022** vendor incentive 観測拡張。`ControlParameters` に `vendor_profit_margin` / `vendor_cash_pressure` / `vendor_payment_delay_days` / `vendor_detection_risk` の 4 フィールドを追加し、`vendor_e.build_observation` に `business_context` として渡す。`deliver_partial` / `invoice_with_markup` / `delay_delivery` の 3 action を全条件固定で追加（RB-min vendor_e は不変）。2 新 regime（`combined_I1_I2` / `high_pressure`）を含む 5 regime × L1/L3 × 3 seed × 20日で計 30 セル sweep。**全セル deviation_count=0、LLM vendor_e は新規 3 action を 0 回選択**。Observation level の incentive 情報だけでは LLM の opportunism を誘発できない negative result。10 新規ユニットテスト追加（115→125）（2026-04-11）
- [x] **T-021c** 20日 sweep で L1 / L3 × 3 regime × 3 seed を実行、venv/.env 整備（`requirements.txt` / `pyproject.toml` / `README.md` / `run_ablation.py` に dotenv 読み込み追加、DEFAULT_MAX_DAYS=20）、8日版 L1 は `preliminary_8day/` に退避、`results.md` を 20日データに更新。L3_baseline 18.67 vs L1_baseline 21.67、L3 の I1 応答 +2.33 vs L1 +0.67、全 18 セルで deviation_count=0（2026-04-11）
- [x] **T-021b (impl + L1 exec)** ablation runner `scripts/run_ablation.py` 実装 + L1 sweep 9 セル実行 + `experiments/ablation_t021/results.md` 作成。test_llm.py の8件失敗（anthropic未インストール）も解消（2026-04-11）
- [x] **T-021a** RB-minエージェント実装（`oct/agents/rb_min.py`）+ 14件のユニット/統合テスト（2026-04-11）
- [x] **第3回外部ヒアリング反映** Baseline Ladder導入、frontier形式定義、MCS定義、construct validity 4対処、想定査読批判7件をdocs/08 §6に追記（2026-04-11）
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
| 2026-04-11 | **T-023 narrative-level vendor framing**。T-022 の 4 つの vendor incentive フィールドを決定的な日本語ナラティブに変換する `_render_business_context` を追加。`run_ablation.py --narrative` フラグ経由で `vendor_e` 観測に `business_context.narrative` として渡る（他エージェント観測と RB-min 挙動は不変）。narrative ON × L1/L3 × {combined_I1_I2, high_pressure} × seed 42-44 × 20日 = 12 セル sweep。**L3_high_pressure で `mean_deviation_count = 0.333`**（seed=43 day=2, `deliver_partial(ord_00002, fraction=0.5)`）。T-021→T-023 全系列で初めての非ゼロ deviation で、LLM reasoning はnarrative のキャッシュプレッシャー分岐を明示的に引用。L1 全 6 セルは T-022 と byte-for-byte 一致。5 件のユニットテスト追加（125→130） | #27 |
| 2026-04-11 | **T-022 vendor incentive observation ablation**。`ControlParameters` に 4 つの vendor incentive フィールド（profit_margin / cash_pressure / payment_delay_days / detection_risk）を追加。`vendor_e` persona に `deliver_partial` / `invoice_with_markup` / `delay_delivery` の 3 action を全条件固定で追加（RB-min は不変）。`combined_I1_I2` と `high_pressure` の 2 regime を追加し、L1/L3 × 5 regime × 3 seed × 20日 = 30 セル sweep 実行。**30 セルすべてで `deviation_count=0`**、LLM vendor_e は赤字マージン × 資金枯渇 × 検知リスク 10% という極端な条件下でも新規 3 action を 1 回も選ばなかった。Observation level の incentive 情報だけでは LLM の opportunism を誘発できないことを示す negative result。10 件のユニットテスト追加（115→125） | #26 |
| 2026-04-11 | **T-021c 20日 sweep + venv/.env 整備**。L1/L3 × 3 regime × 3 seed を `--days 20` で再実行。L3_baseline=18.67, L3_I1=21.00, L3_I2=18.00, L1_baseline=21.67, L1_I1=22.33, L1_I2=21.67。全 18 セルで deviation=0。`requirements.txt` / `pyproject.toml` をバージョン固定し、`python-dotenv` を追加。`run_ablation.py` は `experiments/runtime/.env` を dotenv で読み込み、DEFAULT_MAX_DAYS=20 に変更。8日版 L1 は `preliminary_8day/` に退避 | #24 |
| 2026-04-11 | **T-021b ablation runner**。`scripts/run_ablation.py` 実装。L1 (RB-min) sweep 完了 (3 regime × 3 seed, 8日版): mean_payments は baseline=5.33, I1=6.67, I2=5.33。全セル deviation_count=0、errors=0。L3 sweep は API key 環境下で別途実行。test_llm.py の anthropic 未インストール問題も解消 | #23 |
| 2026-04-11 | **第3回外部ヒアリング反映**。Baseline Ladder (L0/L1/L2/L3) 導入、frontierをprobability field × QSD fieldとして形式化、MCS（τ-sufficient/subset-minimal）定義、construct validity 4対処、想定査読批判7件。RB-minエージェント実装 + 14件のテスト | #22 |
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

- **[最優先] Baseline Ladderの結果次第で研究の軸が分岐**: L1（RB-min）でL3（LLM）と同じ波及 → 実行可能シミュレータの価値。L3で固有の現象あり → LLMのpolicy価値。どちらでもreverse stress testing / frontier発見には進める。
- **論文の構造**: option C（EOMを統一フレームとして提示し、QSDとfrontierを中心指標、ablationは補助実験）を採用。
- **投稿先**: 第1論文はMABS@AAMAS / JASSS / CMOTを主軸、HICSS / ICAILは候補。
- **construct validity対処**: 4本柱（実プロセスへのanchoring、ladder triangulation、practitioner sanity check、ODD/TRACE準拠）をsupplementaryに同梱。
- **Emergence Ratio → QSDへの名称変更**: ドキュメント全体でEmergence RatioをQuery-Simulation Divergence (QSD) に更新。S-005除外後の修正値 = 4/7 = 57.1%。
- **gpt-5.4-miniへの切替え**: ablation後のPhase 2で実施。過去実験の再実行要否はablation結果に依存。
- **vendor incentive設計**: ablation完了後に着手。行動空間は固定（quote_standard, quote_with_fee, delay, partial_ship, split_invoice, dispute, comply）。state/payoff/memoryのみ変更。
- **プロセスマイニング閉ループ**: 最初の論文では付録レベル。trace-signature実証のみ。
- **命名**: システム名=EOM、方法名=Organizational Reverse Stress Testing、評価名=QSD。
                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       