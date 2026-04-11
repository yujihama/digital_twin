# OCT Runtime

購買承認フローの Environment State と状態遷移ルールを実装する Python パッケージ。
エージェント（LLM／RB-min）実装とアブレーション実験ドライバも同梱する。

## セットアップ

### 仮想環境の作成

Windows (PowerShell):

```powershell
cd experiments/runtime
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
```

macOS / Linux:

```bash
cd experiments/runtime
python3.11 -m venv .venv
source .venv/bin/activate
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
固定したいバージョンを確認し、`requirements.txt` と `pyproject.toml` の該当行を
手動で更新すること（直接依存のみをピン留めする方針のため `pip freeze > requirements.txt`
は使わない）。

```powershell
# PowerShell
pip show pydantic anthropic openai python-dotenv pytest | Select-String '^(Name|Version):'
```

```bash
# bash
pip show pydantic anthropic openai python-dotenv pytest | grep -E '^(Name|Version):'
```

### API キー設定 (.env)

LLM エージェント（L3）を使うスクリプト（`run_multi_seed.py` / `run_ablation.py`）は、
`experiments/runtime/.env` から `OPENAI_API_KEY` を読み込む。`.env` は `.gitignore`
対象でリポジトリにはコミットされない。`.env.example` をコピーして使うこと。

```powershell
# PowerShell
Copy-Item .env.example .env
notepad .env
```

```bash
# bash
cp .env.example .env
$EDITOR .env
```

`.env` が無い場合、L3 cell はスキップされる（L0/L1/L2 は API キー不要なので実行される）。

## テスト実行

Windows (PowerShell):

```powershell
cd experiments/runtime
.venv\Scripts\Activate.ps1
pytest
```

macOS / Linux:

```bash
cd experiments/runtime
source .venv/bin/activate
pytest
```

全 115 テストがグリーンであることを確認する。pytest が `anthropic` / `openai`
の import で失敗する場合は、仮想環境が正しくアクティブ化されていないか、
`pip install -r requirements.txt` が実行されていない可能性が高い。

## スクリプト実行

Windows (PowerShell) の場合は `.venv\Scripts\Activate.ps1`、macOS / Linux は
`source .venv/bin/activate` で仮想環境を有効化してから実行する。

```bash
cd experiments/runtime

# Multi-seed baseline (L3 のみ、既存)
python scripts/run_multi_seed.py

# Baseline Ladder アブレーション (L0/L1/L3 × regimes × seeds)
python scripts/run_ablation.py --level L1 --all-regimes --seeds 42 43 44

# L1/L3 を別々に走らせた後、per-cell summary.json を再集約する
python scripts/aggregate_ablation.py
```

`run_ablation.py --days` のデフォルトは `docs/09_ablation_plan.md` 準拠で
**20 日**（PR #24 で `5 → 20` に変更）。過去の予備実験（PR #23, 8 日版）と
比較する場合は `--days 8` を明示的に指定する。

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
| `scripts/aggregate_ablation.py` | per-cell `summary.json` から `ablation_summary.json` を再集約するヘルパ（PR #25） |
| `tests/` | pytest ベースのユニットテスト |

## 設計原則

`docs/05_oct_framework.md` §5.5 より:

> LLMは環境状態を「想像」しない。環境状態は独立モジュールがルールベースで管理する。
> LLMの役割は「行動の選択」であり「結果の予測」ではない。

この原則に従い、本パッケージは完全に決定論的。エージェント（LLM／RB-min）層は
別レイヤで実装する。
