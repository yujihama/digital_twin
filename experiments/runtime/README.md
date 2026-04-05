# OCT Runtime

購買承認フローの Environment State と状態遷移ルールを実装する Python パッケージ。

## セットアップ

```bash
cd experiments/runtime
py -3 -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS/Linux
pip install -r requirements.txt
```

## テスト実行

```bash
cd experiments/runtime
.venv\Scripts\activate
pytest
```

## パッケージ構成

| モジュール | 役割 |
|-----------|------|
| `oct/environment.py` | EnvironmentState と各ドメインエンティティ（PurchaseRequest, Approval, Order, Receipt, Invoice, Payment, ControlParameters）。**LLM 呼び出しは含まない** |
| `oct/rules.py` | 状態遷移ルール（draft/approve/order/receipt/invoice/pay, capacity, advance_day, three-way match）。決定論的で、LLM を呼ばない |
| `tests/` | pytest ベースのユニットテスト |

## 設計原則

`docs/05_oct_framework.md` §5.5 より:

> LLMは環境状態を「想像」しない。環境状態は独立モジュールがルールベースで管理する。
> LLMの役割は「行動の選択」であり「結果の予測」ではない。

この原則に従い、本パッケージは完全に決定論的。エージェント（LLM）層は別レイヤで実装する。

## 次のステップ

- `oct/agent.py`: エージェント基底クラスと購買担当 A のペルソナ
- `oct/logger.py`: Observation Logger（JSONL 形式の状態遷移ログ）
- `oct/runner.py`: シミュレーションループ
