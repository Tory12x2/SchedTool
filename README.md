# Schedule Tool

Discord用の日程調整Botです。

## 起動

```bash
export DISCORD_TOKEN="ここにBotトークン"
./venv/bin/python main.py
```

または、先に仮想環境を有効化してから起動します。

```bash
source venv/bin/activate
python main.py
```

`ModuleNotFoundError: No module named 'discord'` が出る場合は、通常のPythonではなく
このプロジェクト内の `venv` を使って起動してください。

## ファイルの役割

- `main.py`: Botを起動するだけのファイルです。基本的には触りません。
- `config.py`: 環境変数、既存データ移行用サーバーID、ボタン表示名などを調整します。
- `commands.py`: `/schedule`、`/list`、`/result` などのコマンド名や動作を調整します。
- `views.py`: 日付ごとの `◎ / △ / ×` ボタンUIを調整します。
- `embeds.py`: 結果表示の文章や見た目を調整します。
- `database.py`: SQLiteへの保存、取得、削除処理をまとめています。
- `main2.py`: UI試作用の元ファイルです。参考として残しています。

## よく調整する場所

- コマンド名を変える: `commands.py`
- 通知チャンネルを変える: Discordで `/notification_channel_setting`
- サーバー別の設定: 各Discordサーバー内で設定コマンドを実行
- ボタンの文字を変える: `config.py` の `STATUS_LABELS`
- 調整できる最大日数を変える: `config.py` の `MAX_DAYS`
- 結果表示の文言を変える: `embeds.py`
- 保存ファイル名を変える: `config.py` の `DATABASE_PATH`

## 日程調整の表示

先に `/schedule_setting` でイベント名と1回の日程調整日数を設定します。

```text
/schedule_setting event_name:定例会 days:10
```

その後、`/schedule` では開始日だけを指定します。

```text
/schedule start:2026-06-10
```

イベントIDは `定例会_20260610` のように自動で作られます。
`/schedule_setting` の日数は最大10日分まで受け付けます。
回答UIはDiscordの制限に合わせて5日ずつに分かれ、公開メッセージには
`06/10(水)〜06/14(日)` のような日程範囲ボタンが表示されます。

公開メッセージには `月間日程表` ボタンも表示されます。
このボタンを押すと、押した人だけに全員の入力内容が日付ごとに表示されます。
月間日程表では、メンバーごとに固定アイコンを自動で割り当て、スマホで見やすいように
`06/10(水)｜◎🍎🍊｜△🍋｜×-` の形式で表示します。

自分のアイコンを指定したい場合は、次を実行します。

```text
/my_icon icon:🍎
```

他のメンバーが使っているアイコンは指定できません。

Botを再起動した場合も、作成済みの日程調整ボタンは起動時に再登録されます。

## 締切

日程調整を作成すると、日付範囲ごとに締切が自動保存されます。
締切は、各日程の2日前24時です。

例:

```text
/schedule start:2026-06-10
```

この場合、1つ目の日付範囲の締切は `2026-06-09 00:00` です。
開始日が当日の範囲は例外として、当日 `23:59` まで回答できます。
締切を過ぎると、Botが自動で対象の日付範囲ボタンを無効化します。
手動で終了したい場合は、管理者が次を実行します。

```text
/close event_id:定例会_20260610
```

## 日程調整の自動作成

自動作成を開始するには、日程調整を出したいチャンネルで実行します。

```text
/auto_schedule_start first_start:2026-06-10 lead_days:5
```

- `first_start`: 最初に調整する期間の開始日です。
- `lead_days`: 開始日の何日前に日程調整を出すかです。省略時は5日前です。
- 自動作成は `/schedule_setting` のイベント名と日数を使います。
- 次回以降は、設定した日数ごとに自動で次の期間へ進みます。

自動作成を止めるには、次を実行します。

```text
/auto_schedule_stop
```

## 参加可能日の通知

参加可能日の通知は、デフォルトで1日前の21時に通知されます。
参加予定者ロールを設定すると、そのロールのメンバーだけを対象に管理します。
未設定の場合は、Bot以外のサーバーメンバー全員を対象にします。

```text
/participant_role_setting role:@参加予定者
```

通知されるのは、対象者全員が予定を入力済みで、かつ `×` が1人もいない場合だけです。
`△` は参加確率50%として扱い、保留人数に応じた決行確率を通知に表示します。
通知先を変えたい場合は、管理者が通知先にしたいチャンネルを指定して実行します。

```text
/notification_channel_setting channel:#通知先チャンネル
```

通知で参加可能者にメンションするかどうかも設定できます。

```text
/notification_mention_setting enabled:true
/notification_mention_setting enabled:false
```

通知タイミングを変えたい場合は、管理者が次を実行します。

```text
/reminder_setting days_before:1 hour:21 comment:忘れずに準備お願いします
```

- `days_before`: 何日前に通知するかです。
- `hour`: 何時に通知するかです。0〜23で指定します。
- `comment`: 通知に添える一言コメントです。不要なら省略できます。

通知の見た目を確認したい場合は、管理者がイベントIDと日付を指定してテスト送信できます。

```text
/available_day_reminder_test event_id:定例会_20260610 date:2026-06-10
```
- 同じイベントの同じ日程は、二重通知されないように記録されます。
