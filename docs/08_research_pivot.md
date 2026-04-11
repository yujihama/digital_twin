# 08. 研究方向性の転換 — 協議の経緯と結論

> 本ドキュメントは、exp005（三者照合無効化）の結果を起点とする研究方向性の再検討プロセスを、結論だけでなく協議の過程も含めて記録する。

## 1. 転換の起点: exp005 の結果と S-005 問題

### 何が起きたか

exp005（三者照合無効化の介入実験）で、vendor_e は三者照合の有無に関わらず deviation_count=0 を維持した。invoice_deviations=0, receipt_deviations=0。

当初これは「LLMのコンプライアンス従順バイアス」と解釈され、OCTの限界として位置づけられた。

### 最初の対応案（後に撤回）

- vendor_e のペルソナに利益最大化の動機を追加する
- 環境変数として「仕入れコスト指数」を追加し、誠実な取引のコストを可視化する

### Yuji の問題提起

> 「仕入れコスト指数を変数として入れるのは、従来の因果推論で固定的な変数定義をしていたのと同じ方向ではないか」

この指摘により、対応案は撤回された。`cost_pressure` → vendor行動変化という因果パスを研究者が事前に仮定し、検証用の変数を設計していることが問題。これはDAGのノード追加と構造的に同一であり、OCTが回避しようとしていたアプローチに戻っている。

### さらなる深掘り要求

> 「もっと深い思考ができるはず。多様な分野の情報を収集してアイデアを発散させまくってください」

この要求に応じ、製薬（ハイスループットスクリーニング）、気象（アンサンブル予報）、金融（ストレステスト）、進化生物学（フィットネスランドスケープ）、複雑適応系（CAS）からの知見を収集した。

## 2. 他分野からの知見と統合的な着想

### 収集された知見

| 分野 | パターン | OCTへの示唆 |
|------|---------|-----------|
| 製薬 | 数万化合物の並行スクリーニング。「効くはず」と仮説を立てず、効いたものから学ぶ | 環境条件の網羅探索。仮説なしの帰納的発見 |
| 気象 | 初期条件を微摂動させた50-100のアンサンブル。散らばり自体が情報 | パラレルワールドの分岐。結果の分散が感度情報 |
| 金融（FRB） | ストレステスト：複数シナリオの並行評価。リバースストレステスト：結果から逆算してシナリオを探索 | 目標結果からの逆引き探索。最小条件集合の発見 |
| 進化生物学 | 事前定義された制約なしに創発的な動態を捕捉。フィットネスランドスケープの探索 | 行動パターンの地図構築。相転移の発見 |
| 複雑適応系 | 状態空間の探索。疎結合→探索的適応、密結合→安定化選択 | 組織のフェーズスペース探索 |

### 統合的な着想: パラレルワールド

> Yuji: 「製薬における基礎研究のように多様な分岐を全て並行してシミュレートして観察も面白そう。パラレルワールドを発生させると、より高度なABテストをしているイメージ」

これに応じ、環境条件の空間を網羅的に探索する「パラレルワールド」アプローチを検討した。

```
提案されたグリッド:
  approval_threshold × three_way_match × mean_daily_demands × actions_per_day
  = 4 × 2 × 3 × 3 = 72パターンの並行シミュレーション
```

### Yuji の再度の問題提起

> 「環境条件の軸すらもあらかじめ決めるのは恣意的である」

グリッドの軸を定義した時点で、それは「設計された実験」であり、OCTが回避しようとしたDAG的思考と同じ構造。

この指摘により、「きれいな方向性を整理する必要はなく、カオスになってもいい」という方針で外部ヒアリングを実施することになった。

## 3. 外部ヒアリング — 第1回

### ヒアリングドキュメントの構成

以下の5つの根本的な問いを提示した:

1. シミュレーション vs 質問の境界はどこか
2. 環境の「リアリティ」をどう高めるか（変数定義の矛盾）
3. パラレルワールド的アプローチの可能性
4. OCTの成果物は何であるべきか
5. 「一見明らか」な結果の価値

5つの着想（A〜E）も未整理のまま提示:
- A: 環境をテキストとして進化させる
- B: 実データ駆動の環境構築
- C: リバースストレステスト
- D: 正常の地図の構築
- E: 研究自体をOCTの対象にする

### フィードバック（第1回）の核心

> 「勝ち筋は『DAGを超える新しい因果推論』そのものより、『部分観測・逐次相互作用・外在化された状態をもつ実行系で、単発の質問では見落とすメカニズムを露出させる』ことです」

具体的な指摘:

**1. DAGは消えていない**
> 「DAGを消したのではなく、環境ルール・状態表現・プロンプトの中に因果仮定を移しただけではないかと見なされる」

**2. 命名が強すぎる**
> 「"causal"も"twin"も少し強い言葉。実データとの較正が薄い間は『organizational sandboxでは？』と言われる」

**3. LLMの価値が未分離**
> 「観察された波及効果がLLMエージェント固有の価値なのか、単なるワークフロー/キューの動学なのか、まだ切れていない」

**4. 着想の優先順位**
> 「C（リバースストレステスト）が一番尖っている」。C → B → D → A → E の順。

**5. 問い4（変数定義の矛盾）への回答**
> 「完全には解けない。哲学を『変数ゼロ』から『最小限のprimitiveだけ定義し、高次の関係は創発に委ねる』へ移す」

**6. vendor問題の4つの可能性**
単なるLLMバイアスではなく、incentiveの欠如、統制弱化の非観測、学習の不在も原因候補。

**7. Emergence Ratioの脆弱性**
> 「面白い記述統計だが、主指標としては脆い。イベント粒度、Mode Rの聞き方、モデル、seed数で大きく動く」

**8. 別案: プロセスマイニング閉ループ**
> 「ERP/event logから現実のtraceを取り、OCTのtraceとconformanceを比較する。このループはかなり強い」

**9. 推奨する次のステップ**
1. Mode R を強化した baseline を作る
2. LLM が本当に必要かを ablation する
3. vendor に学習と incentive を入れる
4. reverse stress testing を一つの具体的リスクで回す

## 4. フォローアップの質問と第2回フィードバック

第1回フィードバックを受け、以下の追加質問を設計した:

- A: ablationで差が出なかった場合の研究的位置づけ
- B: vendor incentiveの抽象度（レベル1-4のどれが適切か）
- C: リバースストレステストの探索自動化（LLM-guided searchの整合性）
- D: プロセスマイニング閉ループを最初の論文に入れるか
- E: 命名候補の評価
- F: 「境界の発見」を中心クレームにできるか

### フィードバック（第2回）の核心

**1. 論文の中心軸が確定**
> 「1本目の論文の中心を『reverse stress testing で、組織直観が壊れる境界を発見する』に置く。LLMは中心仮説ではなく、置換可能な policy module として扱う」

**2. ablation の精密な設計**
> 「role-wise × policy-family × regime で切る」

policy family の段階:
- RB-min: 優先順位ルールだけ
- RB-score: urgency, age, backlog などのスコア最大化
- RB-memory: 過去数回の結果を要約して使う
- LLM: 現行

解釈:
- ルールベースでも同じ波及 → 構造由来。LLM固有の価値ではない
- 符号は同じだが強さだけ違う → LLMは増幅器/減衰器
- LLMでしか質的に違う現象が出ない → LLMの本当の価値
- どれでも大差ない → 研究の中心はLLMではなく実行可能な組織シミュレータ

> 「差が出なかった場合でも価値はある。『一見LLMの社会的推論に見える現象の多くは、実はworkflow structureだけで説明できる』と示すのは、それ自体が学術的に意味がある」

**3. vendor incentive はレベル2+4**
> 「action を treatment に応じて増やさず、state / payoff / memory を変える」

行動空間（quote_standard, quote_with_fee, delay, partial_ship, split_invoice, dispute, comply）は全条件で固定。変えるのは利益率、キャッシュ圧力、支払遅延、需要逼迫、検知リスク、過去の成功/失敗記憶。

> 「悪い設計: 条件が悪化したときだけ不正アクションを生やす。良い設計: アクションは常にある。条件悪化でその選好が変わるかを見る」

**4. リバースストレステストの設計**
Mode R を「候補提案器」、Mode S を「審判」として分離。LLM-assisted experimental design。

目的関数は3つ: event発生 × baseline近接性 × seed間頑健性。

**5. 命名の確定**
- システム名: Executable Organizational Model (EOM)
- 方法名: Organizational Reverse Stress Testing
- 評価名: Query-Simulation Divergence (QSD)

**6. Intuition-Failure Frontier**
> 「『境界の発見』を中心クレームにできるか → できる。むしろ有望」

成立条件: 境界があること × 境界が頑健であること × 境界が実務的に意味を持つこと。

**7. 論文の構造**

```
主張: 直接質問では見落とされる波及が、部分観測・逐次実行・状態更新を持つ
      executable model では系統的に露出する。
      その露出は、特に control-capacity boundary 付近で大きくなる。

実験:
  1. Query vs Simulation の divergence を示す
  2. role-wise policy ablation で structural effect と LLM-mediated effect を切り分ける
  3. reverse stress testing で risk frontier を探す
  4. 境界の前後で trace signature がどう変わるかを示す

成果物:
  - risk-condition catalog
  - intuition-failure frontier
  - trace signatures
  - structural vs policy-mediated effect の切り分け
```

## 5. 確定した方針

### 研究の再定義

| 項目 | 旧 | 新 |
|------|-----|-----|
| 中心主張 | OCTでDAG-freeな因果推論ができる | EOMで組織直観が壊れる境界（intuition-failure frontier）を発見する |
| システム名 | Organizational Causal Twin (OCT) | Executable Organizational Model (EOM) |
| LLMの位置づけ | 環境シミュレータの核 | 置換可能なpolicy module |
| 主要指標 | Emergence Ratio | Query-Simulation Divergence (QSD) |
| 成果物 | 因果効果推定値 | risk-condition catalog, intuition-failure frontier, trace signatures |
| 分野 | 因果推論 | LLM-based ABM / computational social science / audit analytics |

### 実験の優先順位（確定）

1. **ablation（ルールベース比較）** — LLMの価値の切り分け。最優先
2. **vendor incentive設計（Level 2+4）** — 行動空間の拡張
3. **reverse stress testing** — frontier発見。論文の核
4. **Mode R強化版** — divergence指標の堅牢化
5. **trace signature** — 付録レベルの実証

### 過去の実験の位置づけ

| 実験 | 旧位置づけ | 新位置づけ |
|------|----------|----------|
| exp001-003 | フレームワークの検証 | パイプラインの構築と calibration（有効） |
| exp004（介入） | 因果効果推定の実証 | QSD の初期観測（有効だが主張を弱める） |
| Layer 1（創発性テスト） | Emergence Ratio算出 | QSD の定義と初期測定（指標名を変更） |
| Layer 2（経路依存性） | 再現性検証 | 頑健性の予備確認（有効） |
| Layer 3（相互作用遮断） | 相互作用の因果寄与 | structural vs interaction の切り分け（有効） |
| exp005（三者照合） | S-005の反証テスト | LLMバイアスの診断（有効。vendor incentive設計の動機） |

### 残る研究上の問い

1. ルールベースエージェントでも同じ波及パターンが出るか（ablation）
2. vendor に incentive を入れた場合、日和見的行動が自然に出現するか
3. reverse stress testing で、deviation_count > 0 になる最小条件集合は何か
4. intuition-failure frontier は seed/model をまたいで頑健か
5. 強化 Mode R でも QSD > 0 が維持されるか

## 6. 外部ヒアリング — 第3回（設計の検証）

第2回フィードバックを踏まえてablation実験計画を起案した後、計画自体の妥当性を再度問うために第3回のヒアリングを実施した。論点は「ablationの軸の取り方」「frontierの形式的定義」「最小条件集合の形式化」「論文の構造と投稿先」「construct validityの弱さへの対処」「想定される批判」の6つ。

### 6.1 ablation設計の修正 — Baseline Ladder

第2回の提案では `RB-min / RB-score / RB-memory / LLM` を「policy familyの段階」と呼んでいたが、これは「LLMがどの能力で寄与するか」を測る軸として整理されていなかった。第3回フィードバックではこれを **Baseline Ladder（policy complexityの単調増加）** として再定義することが提案された。

```
L0 (random)         : ランダム選択（行動空間からuniform sampling）
L1 (RB-min)         : 固定優先順位ルールのみ
L2 (RB-score)       : 重み付きスコア最大化（urgency, age, backlog 等）
L3 (LLM)            : 自然言語推論を伴う適応的判断
```

ladderの各段でQSDがどう変化するかを観察することで、「どの複雑度の階段を上がったときに新しい現象が出るか」を特定できる。これは単発の `RB vs LLM` 比較よりも情報量が大きい。

各実験のtraceには **policy complexity** をメタデータとして記録する（後段の分析でladderに沿った可視化を可能にするため）。

### 6.2 frontierの形式的定義 — probability field と frontier band

第2回までは「intuition-failure frontier」を直感的な概念として扱っていたが、第3回では明示的な数学的定義が要求された。フィードバックの整理:

* 環境条件 \(x \in \mathcal{X}\) を入力として、event発生の **probability field** \(p_E(x)\) と、Mode R と Mode S の **divergence field** \(d_{QSD}(x)\) の二つを別々に推定する。
* **frontier** は \(p_E(x)\) の等高線ではなく、「\(p_E(x)\) が低く、かつ \(d_{QSD}(x)\) が高い領域」 — つまり「実務者の直感では起きないと思われがちだが、実際には起きるかもしれない領域」 — として定義される。
* 可視化は、heatmap → contour → PRIM box の順で粒度を上げる（PRIM = Patient Rule Induction Method。frontierを矩形領域として近似する）。
* frontier band は、seed/model間の不確実性を含めた帯として表現する（点や線ではない）。

### 6.3 最小条件集合（MCS）の形式化

reverse stress testingで「deviation_count > 0 になる最小条件集合」を探索する際の「最小」を、以下の3つの基準で形式化する。

```
τ-sufficient   : 条件集合 C が deviation を確率 τ 以上で誘発する
subset-minimal : C のいかなる真部分集合でも τ-sufficient にならない
```

その上で、複数のsubset-minimalな解候補から1つを選ぶ基準を以下のいずれかから選ぶ:

| 基準        | 意味                                          | 用途                  |
|-------------|-----------------------------------------------|-----------------------|
| sparsest MCS | 条件数が最も少ない                             | 説明可能性            |
| nearest MCS  | baseline からの距離が最も小さい                | 「すぐ起きる」リスク  |
| robust MCS   | seed/model 間で再現する確率が最も高い          | 監査・規制応用        |

論文ではいずれか1つを主要指標とし、残りは付録で報告する。

### 6.4 論文の構造（option C）

第2回で提案された構造に対し、第3回では以下の3案が比較された:

* **option A**: ablationを中心に据える。「LLMは workflow structure と区別できる新しい現象を生むか？」を主問とする。
* **option B**: reverse stress testing を中心に据える。「組織直感が壊れる境界はどこか？」を主問とする。
* **option C**: 両者を貫く統一フレームとして EOM を提示し、QSD と frontier を中心指標とする。ablation は frontier の解釈を支える補助実験として配置する。

→ **option C を採用**。理由は、ablation だけでは「LLMの価値の有無」しか議論できず、frontier だけでは「なぜ LLM を使うのか」が説明できないため。両者は補完関係にある。

### 6.5 投稿先候補

```
JASSS / CMOT          : computational social science / agent-based simulation
MABS @ AAMAS          : multi-agent based simulation の主要ワークショップ
HICSS                 : org sciences track + IS audit/risk track
ICAIL                 : audit analytics 寄りに振る場合
arXiv (preprint)      : 上記と並行して常時公開
```

第1論文は MABS @ AAMAS または JASSS を主軸にし、auditing 系の文脈は section 7 (discussion) で触れる程度に留める。

### 6.6 construct validity の弱さと4つの対処

第3回フィードバックで最も鋭く指摘された弱点が **construct validity** — 「シミュレータの中で観察される deviation が、現実の組織で起きる deviation と本当に対応しているか」 — であった。完全には解けないが、以下の4つで弱さを補強する。

1. **Anchoring to a real process**: 実在するERP/event logの一部を入力として使い、initial state と demand pattern を実データに較正する。最低限 day-0 の在庫・demand 強度・ベンダー数だけでも実データに合わせる。
2. **Triangulation across baselines**: 同じ frontier が L0/L1/L2/L3 のうち少なくとも 2 段で再現されることを要求する。L3 のみで現れる frontier は「LLM artifact」として別カテゴリに分類する。
3. **Practitioner sanity check**: 抽出された frontier の上位 5 件を、実務者（監査人・購買マネージャ）にレビューしてもらう（informal な structured walkthrough）。
4. **ODD / TRACE protocol準拠**: ABM/シミュレーションの再現性に関する標準（ODD = Overview, Design concepts, Details / TRACE = TRAnsparent and Comprehensive model Evaludation）に沿った supplementary material を添付する。

### 6.7 想定される批判（査読対策）

第3回フィードバックで列挙された、想定される7つの査読批判と、それぞれへの一次的な応答方針:

| # | 批判                                                            | 応答方針                                                                     |
|---|-----------------------------------------------------------------|------------------------------------------------------------------------------|
| 1 | DAG は環境ルール・state 表現の中に隠れているだけ                | DAG の概念ではなく **observability assumption** に置き換えていることを明示  |
| 2 | LLM の確率性で全てが説明できる                                  | seed 間の variance を frontier 抽出時に明示的に分離する（robust MCS）        |
| 3 | RB と LLM で同じ波及が出るならLLMは不要                          | frontier の **形** の違いを示す。同じ deviation でも条件分布は異なりうる    |
| 4 | "intuition-failure" は post-hoc に作られた評価軸                | Mode R を **事前** に取得し、Mode S と比較することで post-hoc を回避        |
| 5 | "trace signature" は naming だけの concept で内容がない         | trace variant の clustering と stability test を付録で実施                  |
| 6 | 実データとの calibration が無いから現実の組織にはマッピングできない | construct validity 4 対処 (6.6) を予め添付。limitations にも明記           |
| 7 | benchmark task が無いから他研究と比較できない                    | sandbox + fixture を公開し、再現可能な ablation suite を提供                |

これら7点は論文の **threats to validity** セクションで先回りして言及する。

---
