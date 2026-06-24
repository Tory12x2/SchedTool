# Schedule Tool

Discord用の日程調整Botです。

[使い方はこちら](https://tory12x2.github.io/SchedTool/)

イベントごとに日程候補を作成し、メンバーが `◎ / △ / ×` ボタンで回答できます。
回答結果の集計、月間日程表、締切、自動作成、開催日通知に対応しています。

## セットアップ

### 1. Discord Botを作成する

Discord Developer PortalでBotを作成し、Bot Tokenを取得します。

Bot設定では、次を有効にしてください。

- `SERVER MEMBERS INTENT`
- `MESSAGE CONTENT INTENT` は不要です

Botをサーバーへ招待するときは、少なくとも次のスコープと権限を付けます。

- Scope: `bot`
- Scope: `applications.commands`
- Permission: メッセージ送信
- Permission: メッセージ履歴を読む
- Permission: 埋め込みリンク

### 2. リポジトリをcloneする

```bash
git clone https://github.com/Tory12x2/SchedTool.git
cd SchedTool
```

### 3. Python環境を作る

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 4. 環境変数を設定する

```bash
cp .env.example .env
```

`.env` を開いて、少なくとも `DISCORD_TOKEN` を設定します。

```text
DISCORD_TOKEN=your_discord_bot_token_here
```

必要に応じて、初期通知先チャンネルも設定できます。

```text
RESULT_CHANNEL_ID=123456789012345678
```

未設定の場合は、Bot起動後にDiscordで `/notification_channel_setting` を実行してください。

### 5. 起動する

```bash
python main.py
```

起動に成功すると、Botが参加しているDiscordサーバーにスラッシュコマンドを同期します。

## 管理者向けの初期設定

Discordサーバー内に、日程調整用チャンネルと通知用チャンネルを分けて作っておくと運用しやすくなります。
日程調整用チャンネルでは `/schedule` や `/auto_schedule_start` を実行し、通知用チャンネルは `/notification_channel_setting` で設定します。

必要に応じて、日程調整の対象メンバー用ロールも作成し、`/participant_role_setting` で設定してください。

## よく使う流れ

### 日程調整を作成する

先にイベント名と日数を設定します。

```text
/schedule_setting event_name:定例会 days:10
```

その後、開始日を指定して日程調整を作成します。

```text
/schedule start:2026-06-10
```

イベントIDは `定例会_20260610` のように自動で作られます。
回答UIはDiscordの制限に合わせて5日ずつに分かれ、公開メッセージには
`06/10(水)〜06/14(日)` のような日程範囲ボタンが表示されます。

### 回答する

日程範囲ボタンを押すと、押した人だけに回答画面が表示されます。
各日付に対して `◎ / △ / ×` を選びます。

公開メッセージには `月間日程表` ボタンも表示されます。
このボタンを押すと、押した人だけに全員の入力内容が日付ごとに表示されます。

自分のアイコンを指定したい場合は、次を実行します。

```text
/my_icon icon:🍎
```

他のメンバーが使っているアイコンは指定できません。

## 締切

日程調整を作成すると、日付範囲ごとに締切が自動保存されます。
締切は、各日程の2日前24時です。

開始日が当日の範囲は例外として、当日 `23:59` まで回答できます。
締切を過ぎると、Botが自動で対象の日付範囲ボタンを無効化します。

手動で終了したい場合は、管理者が次を実行します。

```text
/close event_id:定例会_20260610
```

## 日程調整の自動作成

自動作成を開始するには、日程調整を出したいチャンネルで実行します。
指定したイベント名の最新の日程調整を基準にして、次回分から自動作成します。

そのため、初回だけは `/schedule_setting` と `/schedule` で手動作成しておきます。

```text
/auto_schedule_start event_name:定例会 lead_days:5
```

- `event_name`: 自動作成するイベント名です
- `lead_days`: 開始日の何日前に日程調整を出すかです。省略時は5日前です
- 1回の日数は、指定したイベント名で作成済みの最新の日程調整から引き継ぎます
- 次回開始日は、最新の日程調整の最終日の翌日になります
- 次回以降は、同じ日数ごとに自動で次の期間へ進みます

自動作成を止めるには、次を実行します。

```text
/auto_schedule_stop event_name:定例会
```

## 開催日通知

開催日通知は、デフォルトで1日前の21時に通知されます。
参加予定者ロールを設定すると、そのロールのメンバーだけを対象に管理します。
未設定の場合は、Bot以外のサーバーメンバー全員を対象にします。

```text
/participant_role_setting role:@参加予定者
```

通知されるのは、対象者全員が予定を入力済みで、かつ `×` が1人もいない場合だけです。
`△` は参加確率50%として扱い、保留人数に応じた開催確率を通知に表示します。

通知先を変えたい場合は、管理者が通知先にしたいチャンネルを指定して実行します。

```text
/notification_channel_setting channel:#通知先チャンネル
```

通知で参加可能者と保留者にメンションするかどうかも設定できます。

```text
/notification_mention_setting enabled:true
/notification_mention_setting enabled:false
```

通知タイミングを変えたい場合は、管理者が次を実行します。

```text
/reminder_setting days_before:1 hour:21 comment:忘れずに準備お願いします
```

通知の見た目を確認したい場合は、管理者がイベントIDと日付を指定してテスト送信できます。

```text
/available_day_reminder_test event_id:定例会_20260610 date:2026-06-10
```

通知文は次の形式です。

```text
開催日のお知らせ
イベント: 定例会_20260610
日程: 06/10(水)
参加可能: @参加可能な人たち
保留: @保留の人たち
開催確率: 25%…保留の方は確定次第コメントください
```

## 主なコマンド

- `/schedule_setting`: イベント名と日数を設定します
- `/schedule`: 日程調整を作成します
- `/list`: イベント一覧を実行者だけに表示します
- `/result`: イベント結果を表示します
- `/announce`: 結果を通知チャンネルへ投稿します
- `/close`: イベントを締め切ります
- `/delete`: イベントを削除します
- `/admin_status`: Bot設定と未回答者を確認します
- `/my_icon`: 月間日程表で使う自分のアイコンを設定します

## 設定

`.env` で設定できます。

```text
DISCORD_TOKEN=your_discord_bot_token_here
RESULT_CHANNEL_ID=
GUILD_ID=
DATABASE_PATH=schedule.db
```

- `DISCORD_TOKEN`: 必須。Discord Bot Tokenです
- `RESULT_CHANNEL_ID`: 任意。初期通知先チャンネルIDです
- `GUILD_ID`: 任意。古いローカルデータの移行用です。通常は空で構いません
- `DATABASE_PATH`: 任意。SQLite DBの保存先です

## ファイルの役割

- `main.py`: Botを起動します
- `config.py`: 環境変数、ボタン表示名、最大日数などを設定します
- `commands.py`: スラッシュコマンドを定義します
- `views.py`: 日付ごとの `◎ / △ / ×` ボタンUIを定義します
- `embeds.py`: 結果表示の文章や見た目を定義します
- `database.py`: SQLiteへの保存、取得、削除処理をまとめています
- `schedule_service.py`: 日程調整の作成処理です
- `close_service.py`: 締切処理です
- `auto_scheduler.py`: 自動作成、締切、開催日通知の定期処理です
