# スマホ・通信 速報ボード

ケータイWatch / ITmedia Mobile のRSSを自動取得し、分割フラップ表示風のボードで
一覧・カテゴリ分類・お客様共有用テキスト生成ができるプロトタイプです。

## 構成

```
telecom-news-board.html      表示用ページ(GitHub Pagesで公開する)
data/news.json               GitHub Actionsが自動生成するニュースデータ
scripts/fetch_news.py        RSS取得・カテゴリ分類スクリプト
scripts/requirements.txt     Python依存パッケージ
.github/workflows/fetch-news.yml   3時間おきに自動実行するワークフロー
```

## セットアップ手順

1. **GitHubで新規リポジトリを作成**し、このフォルダ一式(`telecom-news-board.html` /
   `data/` / `scripts/` / `.github/`)をそのままpushしてください。
   フォルダ構成(相対パス)を変えないことが重要です。ページは同じ階層の
   `data/news.json` を読みに行きます。

2. **GitHub Pagesを有効化**
   - リポジトリの Settings → Pages
   - Source を「Deploy from a branch」、Branch を `main` / `/(root)` に設定
   - 数分後、`https://<ユーザー名>.github.io/<リポジトリ名>/telecom-news-board.html`
     でアクセスできるようになります。

3. **Actionsの権限を確認**
   - Settings → Actions → General → Workflow permissions を
     「Read and write permissions」にしておいてください
     (news.jsonの自動コミットに必要です)。

4. **手動で1回動かして確認**
   - Actions タブ → 「Fetch telecom news」→ 「Run workflow」で手動実行できます。
   - 成功すると `data/news.json` が更新され、コミットが1件増えます。
   - 以降は `cron: "0 */3 * * *"` の設定により3時間おきに自動更新されます。

## 今後の拡張候補

- キャリア公式サイト(ドコモ/au/ソフトバンク/楽天モバイル等)のお知らせページを
  追加取得(RSS非対応のためスクレイピング処理が別途必要)
- カテゴリ・キャリア判定ルールの精度改善(`scripts/fetch_news.py` の
  `CATEGORY_RULES` / `CARRIER_RULES` を編集するだけで調整可能)
- 障害・不具合カテゴリのみLINE通知するなど、通知系との連携
