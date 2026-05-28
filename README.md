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

## Railwayで運用する

RailwayではGitHubリポジトリを接続してデプロイします。

1. Railwayで `New Project` を作成
2. `Deploy from GitHub repo` でこのリポジトリを選択
3. Serviceの `Variables` に次を追加

```text
DISCORD_TOKEN=Discord Bot Token
```

4. SQLiteを永続化するため、ServiceにVolumeを追加
5. VolumeのMount Pathを `/app/data` に設定

このBotはRailwayの `RAILWAY_VOLUME_MOUNT_PATH` があれば、その中に `schedule.db` を保存します。
ローカル実行時は従来どおりプロジェクト直下の `schedule.db` を使います。

起動コマンドは `railway.json` で次のように設定しています。

```text
python main.py
```

## ファイルの役割

- `main.py`: Botを起動するだけのファイルです。基本的には触りません。
- `config.py`: サーバーID、通知先チャンネル、環境変数、ボタン表示名などを調整します。
- `commands.py`: `/schedule`、`/list`、`/result` などのコマンド名や動作を調整します。
- `views.py`: 日付ごとの `◎ / △ / ×` ボタンUIを調整します。
- `embeds.py`: 結果表示の文章や見た目を調整します。
- `database.py`: SQLiteへの保存、取得、削除処理をまとめています。
- `main2.py`: UI試作用の元ファイルです。参考として残しています。

## よく調整する場所

- コマンド名を変える: `commands.py`
- 通知チャンネルを変える: `config.py` の `RESULT_CHANNEL_ID`
- サーバーを変える: `config.py` の `GUILD_ID`
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

## 締切

日程調整を作成すると、開始日の24時間前が締切として自動保存されます。

例:

```text
/schedule start:2026-06-10
```

この場合、締切は `2026-06-09 00:00` です。
締切を過ぎると、Botが自動で募集を終了し、回答ボタンを無効化します。
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
通知先は `config.py` の `RESULT_CHANNEL_ID` です。

通知タイミングを変えたい場合は、管理者が次を実行します。

```text
/reminder_setting days_before:1 hour:21 comment:忘れずに準備お願いします
```

- `days_before`: 何日前に通知するかです。
- `hour`: 何時に通知するかです。0〜23で指定します。
- `comment`: 通知に添える一言コメントです。不要なら省略できます。
- 同じイベントの同じ日程は、二重通知されないように記録されます。
