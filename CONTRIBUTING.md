# Contributing / 運用ルール

本リポジトリ（OCT 研究）の変更は、**feature ブランチ → Pull Request → main** の流れで反映する。

## 1. ブランチ戦略

| ブランチ種別 | 命名規則 | 用途 |
|-------------|----------|------|
| `main` | `main` | 常に公開可能な状態を保つ。直接 commit 禁止 |
| feature | `feat/<短い説明>` | ドキュメント追加・実装・実験 |
| experiment | `exp/<実験ID>` | 実験結果の記録（`experiments/expNNN_*` 単位） |
| fix | `fix/<短い説明>` | 既存ドキュメント・コードの修正 |
| chore | `chore/<短い説明>` | 設定・運用ファイル等の整備 |

例:
- `feat/environment-state-schema`
- `exp/exp001-baseline`
- `fix/typo-in-oct-framework`
- `chore/progress-tracking-setup`

## 2. コミットメッセージ

Conventional Commits 風に、プレフィックスを付ける。

| プレフィックス | 用途 |
|---------------|------|
| `docs:` | ドキュメント追加・修正 |
| `feat:` | 機能・スクリプト追加 |
| `fix:` | 不具合修正 |
| `exp:` | 実験ログ・結果の追加 |
| `chore:` | 運用・設定関連 |
| `refactor:` | リファクタリング |

例:
```
docs: add Mode R vs Mode S comparison table
feat: implement EnvironmentState dataclass
exp: exp001 baseline results (N=10, T=50)
chore: add PROGRESS.md for work tracking
```

## 3. Pull Request 運用

**進捗があった時点で速やかに PR を作成する。** 蓄積せずタイムリーに反映することが原則。

### PR 作成のトリガー

- ドキュメントの追加・更新（1ファイル以上の実質的変更）
- スクリプト・実装の追加
- 実験結果（成果物含む）の記録
- 作業管理表（PROGRESS.md）の進捗反映

### PR テンプレート

```
## 概要
<1-3行で変更内容を要約>

## 関連タスク
- PROGRESS.md の T-XXX

## 変更点
- <箇条書き>

## 成果物 / 確認方法
- <該当ファイルへのリンクや、確認手順>

## TODO / フォローアップ
- <残課題があれば>
```

### マージ方針

- **Squash merge** を基本とする（履歴を簡潔に保つため）
- レビュアー不在の場合でも self-review してからマージ
- マージ後は feature ブランチを削除

## 4. 作業管理表（PROGRESS.md）の更新

PR をマージするたびに **PROGRESS.md の「直近の更新履歴」と該当タスクのステータス** を更新する。これにより、リポジトリの状態と進捗表が常に同期する。

- タスク着手時: 該当タスクを `Next Up` → `In Progress` に移動
- PR マージ時: `In Progress` → `Done` に移動、更新履歴に1行追加
- 新しい課題発見時: `Backlog` に追加

## 5. ディレクトリ構成

```
digital_twin/
├── README.md                 # プロジェクト概要
├── PROGRESS.md               # 作業管理表（本体）
├── CONTRIBUTING.md           # 本ファイル
├── docs/                     # 研究ドキュメント（01-07）
└── experiments/              # 実験記録
    ├── README.md
    └── expNNN_<name>/
        ├── config.json
        ├── logs/
        ├── results.md
        └── analysis.md
```

## 6. Cowork セッションでの作業フロー

Claude Cowork で研究作業を進める際は以下の流れを推奨する:

1. PROGRESS.md を確認し、着手するタスクを選定
2. feature ブランチを作成（`git checkout -b feat/<...>`）
3. 作業を実施（ドキュメント・実装・実験）
4. 変更内容を commit
5. PROGRESS.md を更新（ステータス・履歴）
6. push して PR を作成
7. マージ後、main を pull して次のタスクへ
