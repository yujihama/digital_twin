# T-021b / T-021c ablation 結果ノート

このディレクトリは T-021b（Baseline Ladder × regime ablation runner 実装）および
T-021c（20日版 L1 / L3 sweep）の実行結果を保管する。スクリプトは
`experiments/runtime/scripts/run_ablation.py`、計画は `docs/09_ablation_plan.md`、
研究上の位置付けは `docs/08_research_pivot.md §6` を参照。

## 0. 本ノートの対象データ

| フォルダ | max_days | 対象 levels | 対象 regimes | seeds | 主要用途 |
|---|---|---|---|---|---|
| `L1_*/` `L3_*/` (このディレクトリ直下) | **20** | L1, L3 | baseline, I1, I2 | 42, 43, 44 | **§1〜§4 の一次データ** |
| `preliminary_8day/` | 8 | L1 | baseline, I1, I2 | 42, 43, 44 | 予備実験（PR #23）。長さ依存性の参考用 |

T-021c で 20日版に揃え直した経緯は PR #24 のレビューコメントを参照。`docs/09_ablation_plan.md` の
`max_days=20` 指定と `exp003c/exp004` の設定に整合させるため、8日版は `preliminary_8day/`
に退避した。


## 1. 実行サマリ（20日版 L1 + L3）

3 シード × 3 regime × 2 levels = 18 セルを実行。L1 の所要時間は 1 セルあたり数ミリ秒、
L3 は 165〜235 秒（gpt-4.1-mini）。

### 再現コマンド

```bash
cd experiments/runtime
.venv\Scripts\activate                    # Windows (see README.md)
# L1 sweep (no API key required)
python scripts/run_ablation.py --level L1 --all-regimes --seeds 42 43 44 --days 20
# L3 sweep (requires .env / OPENAI_API_KEY; loaded via python-dotenv)
python scripts/run_ablation.py --level L3 --all-regimes --seeds 42 43 44 --days 20
```

L1 と L3 を別々に走らせたため、最終的な `ablation_summary.json` は `merge_ablation.py`
相当の集約スクリプトで L1 と L3 を結合している（スクリプトはコミットしていない）。
集約後の値は下表の通り。

### 20日 L1 × regime

| cell                | n | mean_payments | stdev | deviation | errors | mean_total_steps |
|---------------------|---|---------------|-------|-----------|--------|------------------|
| L1_baseline         | 3 | 21.67         | 3.22  | 0         | 0      | 166.7            |
| L1_intervention_I1  | 3 | 22.33         | 3.79  | 0         | 0      | 164.3            |
| L1_intervention_I2  | 3 | 21.67         | 3.22  | 0         | 0      | 166.7            |

### 20日 L3 × regime（gpt-4.1-mini, temperature=0.8）

| cell                | n | mean_payments | stdev | deviation | errors | mean_total_steps |
|---------------------|---|---------------|-------|-----------|--------|------------------|
| L3_baseline         | 3 | 18.67         | 2.31  | 0         | 0      | 162.0            |
| L3_intervention_I1  | 3 | 21.00         | 3.00  | 0         | 0      | 162.3            |
| L3_intervention_I2  | 3 | 18.00         | 2.65  | 0         | 0      | 159.3            |

regime パラメータは `run_ablation.py::REGIMES` を参照。

| regime          | approval_threshold | three_way_match | mean_daily_demands |
|-----------------|--------------------|-----------------|--------------------|
| baseline        | 200,000            | True            | 1.5                |
| intervention_I1 | 5,000,000          | True            | 1.5                |
| intervention_I2 | 200,000            | False           | 1.5                |


## 2. 観察事項（20日版）

### 2.1 L3 は baseline で L1 よりスループットが低い（18.67 vs 21.67）

20日 baseline の `mean_payments` は L1 > L3（21.67 > 18.67, 差 +3.00, stdev 0 を
前提にすれば有意）。RB-min は `wait` を返す条件が非常に限定的で毎ターン何らかの
アクションを選択するのに対し、LLM 側は状況判断で `wait` を選ぶ頻度が高く、
`mean_total_steps` も L1 166.7 vs L3 162.0 と低い。ladder 上段ほど「判断のコスト」
が上がるという docs/08 §6.1 の想定と整合する。

### 2.2 L3 の方が I1 介入への応答が大きい

`I1 - baseline` の `mean_payments` 差分:

- L1: +0.67（21.67 → 22.33, ±3.2 の stdev に埋もれる）
- L3: +2.33（18.67 → 21.00, 同上の条件下で +12%）

承認閾値を 200k → 5M に上げたとき、RB-min ではキャパ差がほぼ出ないのに対し、
LLM では buyer が approver 経由のステップを省略し、より積極的に `place_order` に
進む挙動が定性的に観測される（cell ごとの `per_agent_actions` 内訳で確認可能）。
docs/08 §6.6 の **triangulation** 仮説「L3 だけが介入応答を示せば、その応答は
ladder 上段に固有である」の一次証拠。ただし seed 数 3 では統計的主張は保留する。

### 2.3 I2 介入は両 ladder とも deviation を生まなかった

`three_way_match_required=False` に切り替えても L1/L3 いずれでも `deviation_count=0`、
`mean_payments` はむしろ若干減少（L3: 18.67 → 18.00, L1: 変化なし）。
これは「三者照合を外しても、エージェントが vendor 側で虚偽金額 invoice を
生成する自由度を持たない限り、deviation は観測されない」ことを示している。

- RB-min vendor_e は `order.order_amount` を忠実に `register_invoice` する
  実装であり、三者照合の on/off に関わらず同じ金額を投入する
- LLM vendor_e も現状の system prompt では金額逸脱を積極的には行わない

これは docs/08 §6.7 の reviewer attack #3「RB と LLM が同じ波及しか生まないなら
LLM は不要」への部分的な応答でもあり、同時に **opportunistic behavior を誘導する
には追加の介入（例: vendor の incentive 設計変更、temperature 引き上げ、役割
プロンプトの改変）が必要である** ことを示唆する（次ステップ §4 で議論）。

### 2.4 deviation_count = 0 は両 ladder で共通

20日 sweep のすべて 18 セルで `deviation_count = 0`。第3回 external review §6.7 が
提起した「ladder 段差がそのまま deviation 波及を生むか」という論点について、
**baseline regime / I1 / I2 のどれでも単独では deviation を発生させないこと** が
確認できた。つまり intuition-failure frontier（docs/08 §6.2）を観測するには、
より厳しい regime（例: 複数の制御を同時に緩める、ノイジーな demand、ambiguous な
vendor プロンプト）を必要とする。T-022 以降の探索範囲設計に反映する。

### 2.5 seed44 は両 ladder で低スループット（確認済みの外れ値）

PR #23 の 8日実験で指摘されていた seed44 の低ステップ数傾向は、20日 sweep でも
再現した。

| regime          | L1 seed42 | L1 seed43 | L1 seed44 | L3 seed42 | L3 seed43 | L3 seed44 |
|-----------------|-----------|-----------|-----------|-----------|-----------|-----------|
| baseline        | 24        | 23        | 18        | 20        | 20        | 16        |
| intervention_I1 | 25        | 24        | 18        | 24        | 21        | 18        |
| intervention_I2 | 24        | 23        | 18        | 17        | 21        | 16        |

seed44 は demand RNG 固有の「1日あたり demand 数が多くかつ初日から pipeline が
詰まる」パターンを引くと仮説している。バグではないが、平均値の解釈時は stdev と
併せて記載する。より大きい seed pool（例: 10 seed）を使う次回の sweep 設計では
seed44 の扱いを再評価する。


## 3. ファイル構成

```
experiments/ablation_t021/
├── ablation_summary.json           # 20日版 L1 + L3 集約サマリ
├── L1_baseline/                    # 20日版 L1
│   ├── seed42/{trace.json, summary.json}
│   ├── seed43/{trace.json, summary.json}
│   └── seed44/{trace.json, summary.json}
├── L1_intervention_I1/             # (同上)
├── L1_intervention_I2/
├── L3_baseline/                    # 20日版 L3
├── L3_intervention_I1/
├── L3_intervention_I2/
├── preliminary_8day/               # PR #23 の 8日版（参考データ）
│   ├── L1_baseline/...
│   ├── L1_intervention_I1/...
│   ├── L1_intervention_I2/...
│   └── ablation_summary.json
└── results.md                      # このファイル
```

各セルの `summary.json` には `max_days`、`policy_complexity`、`seed`、
`counts`、`per_agent_actions`、`errors` が記録される。

## 4. 次のステップ

### 4.1 Frontier 探索のための regime 拡張

§2.3 で述べた通り、今回の baseline / I1 / I2 のどれも単独では deviation を
発生させなかった。intuition-failure frontier を観測するには regime の軸を
増やす必要がある。候補:

1. **多要素同時介入**: I1 ∧ I2（閾値 5M かつ 三者照合無効化）を組み合わせた
   regime を追加し、単独介入では出なかった波及が出るかを確認する。
2. **Ambiguous vendor prompt**: vendor_e の system prompt を「納品遅延時に
   invoice 金額を帳尻合わせに上乗せしてよい」と解釈余地のある文言に変え、
   LLM 側の opportunistic behavior を誘発できるかを試す（L1 との差を観測）。
3. **Higher temperature / more seeds**: 現行の temperature=0.8 / n=3 seed は
   stdev ≒ 3 のノイズに対して弱い。temperature=1.0 かつ n=10 seed 程度で
   再実行すると、§2.2 の +2.33 差分の信頼性が判定できる。

### 4.2 L0 と L2 の追加

- **L0 (random)**: 現在 `_RandomLLM` が常に `wait` を返すスタブ。真の random は
  agent ごとの action schema が必要なため、T-027 の trace metadata 整備と
  合わせて実装する。
- **L2 (RB-score)**: 重み付きスコア最大化。L1 ↔ L3 の差が十分大きくないと
  ladder 上の「連続性」を測る指標にならないため、§4.1 の frontier 探索で
  L1 と L3 の差が観測されたあとに実装優先度を判断する。

### 4.3 Real-process anchoring と practitioner check

docs/08 §6.6 の 4 mitigations のうち、本 PR で進捗したのは **(2) Triangulation**
の L1↔L3 一次比較のみ。残り3つ:

- **(1) Real process anchoring**: exp001/exp002 の PO→GR→Invoice→Payment の実
  SAP トレースを 1 本取得し、シミュレータの state transition と side-by-side で
  可視化する（T-030 で計画）。
- **(3) Practitioner check**: 現場担当者に deviation 定義の妥当性を確認する
  インタビュープロトコルを docs/10 として起案する（T-031）。
- **(4) ODD / TRACE 準拠**: モデル記述を ODD+D プロトコルに揃えた README セクション
  を `experiments/runtime/ODD.md` として分離する（T-032）。

## 5. construct validity 上の留意点

ここで観測した値はすべて `experiments/runtime` 合成シミュレータ上のものであり、
実在 ERP データとの突合はまだ行っていない。また、LLM 側のランダム性は
`temperature=0.8` に固定しているが、seed による multi-sample stability は
n=3 では不十分である。20日 sweep の stdev（L3 baseline で 2.31 / 20日）は
このノイズ水準で、§2 の差分解釈はすべて「定性的な方向性」の域を出ない。
より強い統計的主張には n ≥ 10 seed または temperature 固定化が必要。
