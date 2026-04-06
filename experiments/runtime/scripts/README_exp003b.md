# exp003b: 承認フローベースライン確保

## 目的

exp003では承認閾値100万円のため、承認対象が1件（ノートPC 1,618,884円）のみだった。
介入実験（T-009: 閾値100万→500万）のベースラインとしては不十分。

**exp003b** では承認閾値を **50万円** に引き下げ、複数件の承認/却下判断を発生させる。

## exp003との差分

| パラメータ | exp003 | exp003b | 変更理由 |
|---|---|---|---|
| approval_threshold | 1,000,000 | **500,000** | 承認対象件数の増加 |
| model | gpt-4.1-mini | gpt-4.1-mini | 同一 |
| max_days | 20 | 20 | 同一 |
| temperature | 0.8 | 0.8 | 同一 |
| rng_seed | 42 | 42 | 同一 |
| actions_per_agent_per_day | 2 | 2 | 同一 |
| demand_rng_seed | 42 | 42 | 同一 |
| mean_daily_demands | 1.5 | 1.5 | 同一 |

## 期待される効果

DEMAND_CATALOGの品目のうち、閾値50万円以上の以下が承認対象に含まれる：

- 品質管理部・測定器校正サービス: ~800,000円
- 切削油 20L: ~120,000円 → 閾値以下のため対象外
- 情報システム部・ノートPC: ~1,500,000円
- 品質管理部・検査用ゲージ: ~250,000円 → 閾値以下のため対象外

※ amount_jitter=±20% があるため、実際の金額はカタログ値から変動する

主に **測定器校正サービス（~80万円）** と **ノートPC（~150万円）** が承認対象となり、
approver_c の承認行動パターンのベースラインが確立される。

## 実行手順

```bash
# experiments/runtime/ ディレクトリで実行
cd experiments/runtime

# venv有効化（初回のみ作成）
python -m venv .venv
.venv\Scripts\activate  # Windows
# source .venv/bin/activate  # Linux/macOS

# 依存インストール（初回のみ）
pip install -r requirements.txt

# 実行
python scripts/run_exp003b.py

# トレース分析
python scripts/analyze_trace.py ../exp003b_approval_baseline/trace_seed42.json
```

## 出力

- `experiments/exp003b_approval_baseline/trace_seed42.json` — 完全トレース
- `experiments/exp003b_approval_baseline/trace_seed42.analysis.json` — 分析結果（analyze_trace.py実行後）
- stderr — 実行サマリー

## 次のステップ: T-009（介入実験）

exp003b でベースラインが確立できたら：

```
exp003b（閾値50万）= 統制が厳格なベースライン
  ↓ 介入: 閾値を500万に引き上げ
exp004（閾値500万）= 統制が緩和された状態
  → 差分が「統制緩和の因果効果」
```
