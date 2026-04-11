# T-021b ablation 結果ノート

このディレクトリは T-021b（Baseline Ladder × regime ablation）の実行結果を保管する。スクリプトは `experiments/runtime/scripts/run_ablation.py`、計画は `docs/09_ablation_plan.md`、研究上の位置付けは `docs/08_research_pivot.md §6` を参照。

実行コマンド (本ノートに記載した結果を再現する場合):

```
cd experiments/runtime
python scripts/run_ablation.py --level L1 --all-regimes --seeds 42 43 44 --days 8
```

## 1. 実行サマリ（L1 = RB-min）

3 シード × 3 regime = 9 セルを実行。各セルの単発所要時間は 1 ms 程度。トータル数秒。

| cell                  | n_seeds | mean_payments | mean_deviation | mean_errors | mean_dispatched_ok |
|-----------------------|---------|---------------|----------------|-------------|--------------------|
| L1_baseline           | 3       | 5.33          | 0              | 0           | 61.0               |
| L1_intervention_I1    | 3       | 6.67          | 0              | 0           | 61.0               |
| L1_intervention_I2    | 3       | 5.33          | 0              | 0           | 61.0               |

regime のパラメータは `run_ablation.py` の `REGIMES` を参照。簡略すると以下の通り。

| regime          | approval_threshold | three_way_match | mean_daily_demands |
|-----------------|--------------------|------------------|--------------------|
| baseline        | 200,000            | True             | 1.5                |
| intervention_I1 | 5,000,000          | True             | 1.5                |
| intervention_I2 | 200,000            | False            | 1.5                |

## 2. 観察事項

### 2.1 RB-min は I1 介入でのみスループット差が出る

I1（承認閾値を 200k → 5M に引き上げ）では平均支払件数が baseline の 5.33 → 6.67 に増加した。これは buyer が approver の処理を待たず直接 `place_order` に進めるため、approver_c のキャパシティがボトルネックでなくなることに対応する。`per_agent_actions` を見ると I1 の approver_c は `approve_request` を 0 回しか実行していない（baseline では 3 回）。

I2（三者照合無効化）では `mean_payments` が baseline と同じ 5.33 のままだった。RB-min の vendor_e は常に発注額そのままで `deliver` と `register_invoice` を行うため、三者照合があっても無くても結果が変わらない。これは仕様通りで、I2 介入による差は LLM 由来（または RB-score 由来）の opportunistic behavior が必要である、という第3回フィードバック §6.6 の triangulation 仮説を補強する一次証拠となる。

### 2.2 deviation_count = 0 は L1 の特性として記録すべき

3 regime × 3 seed すべてで `deviation_count = 0` だった。これは「RB-min は ladder の最下層であり deviation を起こす自由度を持たない」という設計通りの結果。第3回フィードバック §6.7 の批判 #3「RB と LLM で同じ波及が出るなら LLM は不要」への一次的な応答材料になる: **L1 では波及が起きないため、L3（LLM）で波及が観測されれば、それは ladder の上の段階に固有の現象である**ことが示せる。

ただしこれだけでは不十分で、L3 を未だ走らせていないため反証可能性が弱い。次の実験ステップ（§4）で L3 sweep を実行し、`mean_deviation_count` の差を確認する必要がある。

### 2.3 dispatched_ok = 61 はキャパシチェイン上の上限値

5 agents × 8 days × 2 actions/day = 80 が理論上限だが、`wait_ends_turn=True` と `actions_per_agent_per_day=2` の組合せで agent あたり 1 日 1 wait 出ると次の turn が消費されない。実測 61 はその前提下で妥当。L3 でもこの上限近くで頭打ちになると予想される（LLM は wait をより頻繁に選ぶ可能性があるため）。

### 2.4 errors = 0 は RB-min が action schema を絶対に守ることを示す

`decide_or_dispatch_errors = 0` がすべてのセルで成立した。これは RB-min が `Agent.decide` を経由した parser failure を起こさず、dispatcher に入っても schema 不一致を起こさないことを意味する。L3 の比較では、LLM 側の parser/dispatch 失敗率を「行為選択の信頼性」の指標として使える。

## 3. ファイル構成

各セルのトレースとサマリは以下の階層に保存される。

```
experiments/ablation_t021/
├── ablation_summary.json          # aggregate(combined) summary
├── L1_baseline/
│   ├── seed42/{trace.json, summary.json}
│   ├── seed43/{trace.json, summary.json}
│   └── seed44/{trace.json, summary.json}
├── L1_intervention_I1/
│   ├── seed42/...
│   ├── seed43/...
│   └── seed44/...
├── L1_intervention_I2/
│   ├── seed42/...
│   ├── seed43/...
│   └── seed44/...
└── results.md                      # このファイル
```

`ablation_summary.json` の `cells` キーに集約値、`raw_summaries` に全 9 セルの詳細が入っている。

## 4. 次のステップ

### 4.1 L3 (LLM) の実行 — このPRの範囲外

L3（LLM）sweep は `OPENAI_API_KEY` を環境変数に設定して以下を実行する:

```
python scripts/run_ablation.py --level L3 --all-regimes --seeds 42 43 44 --days 8
```

実行コストは exp003c の実績から 1 セルあたり ~30〜90s 程度、9 セルで合計 5〜15 分程度を見込む（モデルにより変動）。`OCT_LLM_MODEL` 環境変数で `gpt-4.1-mini` 以外も指定可能。

L3 を走らせた後で再度 `run_ablation.py --all-levels --all-regimes` を実行すれば、ablation_summary.json に L1 と L3 の両方が並ぶ。

### 4.2 比較分析

L3 結果が揃った時点で以下の比較を行う:

1. `L1_baseline` vs `L3_baseline` の `mean_deviation_count` 差 → ladder の段差が deviation を生むかどうかの一次判定
2. `L3_intervention_I1 - L3_baseline` vs `L1_intervention_I1 - L1_baseline` → 介入応答が ladder 段で異なるかどうか
3. `L3_intervention_I2 - L3_baseline` → LLM vendor が三者照合無効化を「悪用」するかどうか（vendor_e の `register_invoice` 金額が `order.amount` から逸脱するか）

これらが §2.1〜§2.2 の triangulation 仮説の検証に対応する。

### 4.3 L0 と L2 の追加

* **L0 (random)**: 現在は `_RandomLLM`（常に wait）でスタブされている。本物の random は agent ごとの action schema が必要なので、T-027 の trace metadata 整備と合わせて実装する。
* **L2 (RB-score)**: 重み付きスコア最大化。L1 と L3 の差が大きい場合のみ追加実装する（第3回フィードバック §6.1 の優先順位通り）。

## 5. construct validity 上の留意点

ここで観測した結果はすべて `experiments/runtime` 内の合成シミュレータ上のものであり、実在 ERP データとの照合はまだ行っていない。`docs/08 §6.6` の 4 対処のうち、本 PR は **(2) Triangulation across baselines** の最初の半分（L1 baseline 確立）のみを完了している。残り 3 対処（real-process anchoring / practitioner check / ODD-TRACE）は別タスクで取り組む。
