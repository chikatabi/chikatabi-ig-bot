# CHIKATABI Instagram 自動投稿

お得な旅の情報を毎日2回、自動でリサーチ → 記事化 → 画像化 → LINEで承認 → Instagram投稿。

```
毎朝6:00（GitHubのサーバーが自動で起動）
   ↓
① リサーチ    WEB・note・ニュースを巡回して候補を集める
② 重複チェック 過去に投稿したテーマは除外
③ 精査・執筆  Claudeが2本選んで、画像の文言とキャプションを書く
④ 画像生成    テンプレートに文字を流し込んでJPEGを作る
   ↓
LINEに2件の投稿案が届く（画像つき・ボタンつき）
   ↓
「投稿する」を押す
   ↓
⑤ Instagramへ投稿  ＋ 履歴に記録（次回の重複チェックに効く）
```

---

## セットアップ（全4ステップ）

はじめの1回だけ、CHIKA側で必要な作業です。
**パスワードやトークンを扱う場面があるので、この部分は必ずご自身で操作してください。**

### 1. GitHub にリポジトリを作る

1. https://github.com/new を開く
2. Repository name に `chikatabi-ig-bot` と入力
3. **Public を選ぶ**（後述の理由により必須）
4. 「Create repository」

作ったら、このフォルダの中身をアップロードします。ターミナルで：

```bash
cd ~/chikatabi-ig-bot && git init && git add -A && git commit -m "初期構築" && git branch -M main && git remote add origin https://github.com/【あなたのユーザー名】/chikatabi-ig-bot.git && git push -u origin main
```

> **なぜ Public なのか**
> Instagram は「インターネット上の公開URLに置かれた画像」しか受け付けません。
> バイナリを直接アップロードする方法が無いため、生成した画像を公開URLに置く必要があります。
> **パスワードやトークンはリポジトリには一切入りません**（後述の Secrets に暗号化して保管されます）。
> 公開されるのは画像と投稿案のテキストだけです。

### 2. Instagram側の準備

1. Instagram アプリで、アカウントを**プロアカウント（ビジネス or クリエイター）**に切り替える
2. https://developers.facebook.com/ で「アプリを作成」→ ユースケースは **「Instagram」** を選ぶ
3. 「Instagram API setup with Instagram login」の画面で、対象アカウントを追加する
4. 権限（スコープ）に `instagram_business_basic` と `instagram_business_content_publish` を入れる
5. 「Generate token」でトークンを発行し、**控えておく**（これが `IG_ACCESS_TOKEN`）

> 自分のアカウントに投稿するだけなら、アプリ審査は不要です（開発モード＋自分をテスターに登録した状態で動きます）。
> Facebookページとの連携も、この Instagram ログイン方式では不要です。

### 3. GitHub に鍵を登録する

リポジトリの **Settings → Secrets and variables → Actions → New repository secret** で、
以下を1つずつ登録します。ここに入れた値は暗号化され、画面上でも二度と見えません。

| 名前 | 中身 | どこで取るか |
|---|---|---|
| `ANTHROPIC_API_KEY` | Claude の APIキー | https://console.anthropic.com/settings/keys |
| `IG_ACCESS_TOKEN` | Instagram の長期トークン | 手順2で控えたもの |
| `IG_USER_ID` | Instagram のユーザーID | 空でOK（自動取得します） |
| `LINE_CHANNEL_ACCESS_TOKEN` | LINEのチャネルアクセストークン | 手順4で取得 |
| `LINE_TO_USER_ID` | CHIKA自身のLINEユーザーID | 手順4で取得 |
| `GH_PAT` | GitHubの個人アクセストークン | 下記 |

`GH_PAT` の作り方：https://github.com/settings/tokens?type=beta →
「Generate new token」→ Repository access でこのリポジトリを選び、
Permissions で **Contents: Read and write** と **Secrets: Read and write** を許可。

> `GH_PAT` は2つの用途に使います。①トークン延長時に新しいトークンを Secrets に書き戻す
> ②LINEのボタンから投稿ワークフローを起動する。

### 4. LINE承認ボタンの受け口を作る

LINEのボタンを押した信号を受け取る係が必要です。GitHub Actions は決まった時刻に動くことはできても、
**LINEからの通信を受け取ることができない**ためです。Apps Script を受け口にします。

> ⚠️ ここで使うのは**新しいLINEチャネル**です。既存の「CHIKATABI変態ポイント」チャネル
> （会員向けの残高照会bot）とは別に作ってください。混ぜると会員に投稿案が見えてしまいます。

> ⚠️ **Developers Console から直接チャネルは作れません**（2026-08時点）。公式アカウントを
> 先に作り、そこから Messaging API を有効化すると、チャネルが自動で作られる方式に変わりました。
> Console の「新規チャネル作成」を開いても、公式アカウント作成ページへ案内されるだけです。

1. https://developers.line.biz/ → 「LINE公式アカウントを作成する」→ 名前は「CHIKATABI運用bot」など。
   **未認証アカウント**でよい（審査待ちが発生しない）
2. https://manager.line.biz/ で作ったアカウントを開く →
   **設定 → Messaging API → 「Messaging APIを利用する」**。
   途中で開発者情報（名前・メール）とプロバイダーを聞かれるので、プロバイダーは `CHIKATABI` を選ぶ。
   ここでチャネルが作られ、Developers Console に現れる
3. Developers Console → そのチャネル → **Messaging API設定**タブ →
   「チャネルアクセストークン（長期）」を発行 → `LINE_CHANNEL_ACCESS_TOKEN`
4. 同じタブで、**応答メッセージをオフ**、**Webhookをオン**にする（URLは手順7の後で貼る）。
   ついでに**QRコードで自分を友だち追加**しておく（手順9で userId を拾うのに必要）
5. https://script.google.com/ で新規プロジェクトを作り、`apps_script/Code.gs` の中身を貼り付ける
6. 左の歯車（プロジェクトの設定）→ スクリプト プロパティ で以下を登録：
   - `LINE_CHANNEL_ACCESS_TOKEN`（手順3で発行したもの）
   - `GH_PAT`（「3. Secretsを登録する」で作ったもの）
   - `GH_REPO`（例 `chikatabi/chikatabi-ig-bot`）
   - `ALLOWED_USER_ID`（手順9で判明するので、後で入れる）
7. 「デプロイ」→「新しいデプロイ」→ 種類を **ウェブアプリ**、
   実行ユーザー **自分**、アクセスできるユーザー **全員** → デプロイ
8. 出てきた `/exec` のURLを、LINE Developers の **Webhook URL** に貼る
9. 自分のアカウントを友だち追加して何かメッセージを送り、Apps Script の実行ログに出る
   `userId` を控える → `ALLOWED_USER_ID` と `LINE_TO_USER_ID` の両方に設定

> **既知の紛らわしい挙動**：LINEの「検証」ボタンは **302エラー**になりますが、これは正常です。
> Apps Script の仕様（内部リダイレクト）で、実際のメッセージ配信は問題なく動きます。
> ポイントbotを作ったときと同じ現象です。深追いしないでください。

> **コードを直したときの注意**：Apps Script はエディタで保存しただけでは反映されません。
> 「デプロイ」→「デプロイを管理」→ 鉛筆アイコン → バージョンを「新バージョン」→ デプロイ
> まで行って初めて反映されます。URLは変わりません。

---

## 動作確認

セットアップが終わったら、時刻を待たずに手動で回せます。

GitHubのリポジトリ → **Actions** タブ → 「朝のリサーチと投稿案の作成」→ **Run workflow**

数分でLINEに投稿案が2件届けば成功です。片方を承認すると、Instagramに投稿されます。

---

## 日々の運用

やることは **1日2回、LINEのボタンを押すだけ**です。

- 投稿案に `⚠️ 数字・期限を含みます` が出ていたら、元記事リンクを開いて数字を確認してから承認
- 内容が違うと思ったら「やめる」。その日はその1本が飛ぶだけで、翌日は通常どおり動く

### 調整したくなったら

`config.yaml` を編集します（コードは触らなくて大丈夫です）。

| 変えたいこと | 場所 |
|---|---|
| 1日の投稿数 | `posts_per_day` |
| 画像の配色 | `image.themes` |
| 承認を挟むかどうか | `approval`（`line` / `auto`） |
| 数字入りネタを自動で弾く | `numeric_policy` を `block` に |
| 巡回先の追加・削除 | `sources.yaml` |
| 文章のトーン・選定基準 | `src/compose.py` の `SYSTEM` |

投稿時刻を変えるときは `config.yaml` と `.github/workflows/research.yml` の `cron` の**両方**を直してください。
cron は UTC です（JSTから9時間引く）。

---

## 気をつけること

**トークン延長を止めない。** `refresh-token.yml` が毎月1日に動いて、Instagramのトークンを
延長し続けています。これが止まると、**60日後に何のエラーも出ないまま投稿が止まります**。
Actionsタブでこのワークフローが緑になっているか、たまに見てください。

**数字は自動生成させていない。** キャプションの数字は元記事に書かれているものだけを使う設計です
（`src/compose.py` の SYSTEM に明記）。それでもLLMは間違えることがあるので、
`⚠️` が付いた投稿は元記事で確認してから承認してください。

**投稿上限。** Instagram は24時間で100投稿までです。1日2投稿なので問題ありません。

---

## ファイルの役割

| ファイル | 何をするか |
|---|---|
| `config.yaml` | 設定。ここだけ触れば大体のことは変えられる |
| `sources.yaml` | 巡回先のリスト |
| `src/research.py` | RSS・ニュースを集める。ノイズを除去して点数付け |
| `src/compose.py` | Claudeが2本選んで文言を書く |
| `src/render.py` | テンプレート組版で画像を作る |
| `src/publish.py` | Instagram APIへ投稿 |
| `src/notify.py` | LINEへ承認依頼を送る |
| `src/refresh_token.py` | トークンを延長して Secrets に書き戻す |
| `data/posted.tsv` | 投稿履歴。重複チェックはこれを見る |
| `data/queue/` | 承認待ちの投稿案 |
| `drafts/` | 生成した文面の控え |
| `apps_script/Code.gs` | LINEのボタン → GitHub の中継役 |
