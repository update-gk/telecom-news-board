# 通信業界レーダー

各通信キャリア/専門メディアの最新情報を自動取得し、分割フラップ表示風のボードで
一覧・カテゴリ分類・共有用テキスト生成ができるプロトタイプです。

## 情報源

| 情報源 | 取得方法 |
| --- | --- |
| ケータイWatch / ITmedia Mobile | RSS |
| NTTドコモ / au(KDDI) | RSS |
| ソフトバンク | 公開JSON API（`sbkk_press_top`） |
| 楽天モバイル / Y!mobile / UQ mobile | 公開ページのスクレイピング |

公式RSSが確認できないキャリアは公開ページ/APIから取得しているため、
サイト構造の変更で一時的に取得できなくなることがあります
（その場合は `data/news.json` の `errors` 欄に記録されます）。

## 構成

```
telecom-news-board.html      表示用ページ(GitHub Pagesで公開する)
index.html                   telecom-news-board.html へのリダイレクト
manifest.json                PWAマニフェスト(ホーム画面追加用)
sw.js                        Service Worker(オフライン表示・アプリ化)
icons/                       PWAアイコン(scripts/make_icons.js で生成)
data/news.json               GitHub Actionsが自動生成するニュースデータ
scripts/fetch_news.py        RSS取得・スクレイピング・カテゴリ分類スクリプト
scripts/make_icons.js        アイコン生成スクリプト(Nodeのみ・依存なし)
scripts/requirements.txt     Python依存パッケージ(feedparser / requests / beautifulsoup4)
.github/workflows/fetch-news.yml   3時間おきに自動実行するワークフロー
```

## スマホアプリとして使う(PWA)

GitHub Pagesで公開したページはPWA対応済みです。ブラウザでページを開き、

- **iPhone (Safari)**: 共有ボタン → 「ホーム画面に追加」
- **Android (Chrome)**: 右上メニュー → 「アプリをインストール」／「ホーム画面に追加」

でホーム画面にアイコンが追加され、アドレスバーのない全画面アプリとして起動します。
一度開けばオフラインでも直近のデータを表示できます。

アイコンを作り直す場合: `node scripts/make_icons.js`

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

- スクレイピング対象の追加・セレクタ調整(`scripts/fetch_news.py` の
  `SCRAPER_SOURCES` と各 `scrape_*` 関数)
- カテゴリ・キャリア判定ルールの精度改善(`scripts/fetch_news.py` の
  `CATEGORY_RULES` / `CARRIER_RULES` を編集するだけで調整可能)
- 障害・不具合カテゴリのみLINE通知するなど、通知系との連携
