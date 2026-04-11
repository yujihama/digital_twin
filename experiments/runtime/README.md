# OCT Runtime

購買承認フローの Environment State と状態遷移ルールを実装する Python パッケージ。
エージェント（LLM／RB-min）実装とアブレーション実験ドライバも同梱する。

## セットアップ

### 仮想環境の作成

```bash
cd experiments/runtime
py -3.11 -m venv .venv            # Windows (または `python3.11 -m venv .venv`)
.venv\Scripts\activate            # Windows
# source .venv/bin/activate       # macOS / Linux
```

### 依存パッケージのインストール

再現性のため、`requirements.txt` と `pyproject.toml` にはすべて完全固定バージョン
（`==`）を記載している。

```bash
pip install --upgrade pip
pip install -r requirements.txt        # 実行時依存のみ
# または
pip install -e .[dev]                  # editable install + pytest などの dev 依存
```

バージョンを意図的に上げる場合は、個別に `pip install -U <package>` したうえで、
`pip freeze | Select-String pydantic,anthropic,openai,python-dotenv,pytest`
（PowerShell）または `pip freeze | grep -E 'pydantic|anthropic|openai|python-dotenv|pytest'`
（bash）で固定版を取得し、両ファイルを手動で更新すること。

### API キー設定 (.env)

LLM エージェント（L3）を使うスクリプト（`run_multi_seed.py` / `run_ablation.py`）は、
`experiments/runtime/.env` から `OPENAI_API_KEY` を読み込む。`.env` は `.gitignore`
対象でリポジトリにはコミットされない。

```
OPENAI_API_KEY=sk-...
# 任意: ANTHROPIC_API_KEY=sk-ant-...
```

`.env` が無い場合、L3 cell はスキップされる（L0/L1/L2 は API キー不要なので実行される）。

## テスト実行

```bash
cd experiments/runtime
.venv\Scripts\activate
pytest
```

全 115 テストがグリーンであることを確認する。pytest が `anthropic` / `openai`
の import で失敗する場合は、仮想環境が正しくアクティブ化されていないか、
`pip install -r requirements.txt` が実行されていない可能性が高い。

## スクリプト実行

```bash
cd experiments/runtime
.venv\Scripts\activate

# Multi-seed baseline (L3 のみ、既存)
python scripts/run_multi_seed.py

# Baseline Ladder アブレーション (L0/L1/L2/L3 × regimes × seeds)
python scripts/run_ablation.py --levels L1 --regimes baseline,intervention_I1,intervention_I2 --seeds 42,43,44 --days 20
```

`--days` のデフォルトは `docs/09_ablation_plan.md` 準拠で **20 日**。過去の予備実験
（PR #23, 8 日版）と比較する場合は `--days 8` を明示的に指定する。

## パッケージ構成

| モジュール | 役割 |
|-----------|------|
| `oct/environment.py` | EnvironmentState と各ドメインエンティティ（PurchaseRequest, Approval, Order, Receipt, Invoice, Payment, ControlParameters）。**LLM 呼び出しは含まない** |
| `oct/rules.py` | 状態遷移ルール（draft/approve/order/receipt/invoice/pay, capacity, advance_day, three-way match）。決定論的で、LLM を呼ばない |
| `oct/agent.py` | Agent 抽象クラスと LLM 呼び出しラッパ |
| `oct/agents/rb_min.py` | L1（Rule-Based minimum）エージェント実装。LLM を呼ばず決定論的に行動選択 |
| `oct/runner.py` | シミュレーションループ（PurchaseDispatcher / EnvironmentAdapter） |
| `scripts/run_multi_seed.py` | L3 multi-seed baseline（既存） |
| `scripts/run_ablation.py` | Baseline Ladder × regime × seed アブレーションドライバ |
| `tests/` | pytest ベースのユニットテスト |

## 設計原則

`docs/05_oct_framework.md` §5.5 より:

> LLMは環境状態を「想像」しない。環境状態は独立モジュールがルールベースで管理する。
> LLMの役割は「行動の選択」であり「結果の予測」ではない。

この原則に従い、本パッケージは完全に決定論的。エージェント（LLM／RB-min）層は
別レイヤで実装する。
