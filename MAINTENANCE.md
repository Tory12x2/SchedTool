# SchedTool Maintenance Guide

この文書は、SchedToolの稼働確認、修正、VPS反映、サポートページ告知を、別の担当者やAIが安全に引き継ぐための運用手順です。

## 基本方針

- GitHubの`main`をソースコードの正とする
- 修正はローカルの作業コピーで行い、VPS上の稼働中コードを直接編集しない
- Botトークン、`.env`、SSH鍵、サーバーIP、DiscordユーザーIDをGitHub・サポートページ・公開ログに記載しない
- SQLite DBやDiscord上の投稿を削除・変更する作業は、対象と影響を確認してから行う
- 変更は「テスト -> コミット -> push -> VPS配備 -> 起動確認」の順で行う

## 現行の運用構成

| 項目 | 内容 |
| --- | --- |
| リポジトリ | `Tory12x2/SchedTool` の `main` ブランチ |
| 実行方式 | Docker Compose の `schedtool-bot` サービス |
| コンテナ名 | `personal-vps-schedtool-bot-1` |
| アプリ配置先 | `/opt/personal-vps/services/schedtool-bot` |
| Compose配置先 | `/opt/personal-vps` |
| DB | コンテナ内の `/data/schedule.db` |
| ログ | コンテナ内の `/data/logs/schedtool.log`（日次ローテーション、標準30日保持） |

VPSへの接続情報とBotトークンは、公開リポジトリではなく、管理者が管理する安全な場所にのみ保管します。

## 状況確認

### 1. コンテナとリソース

認可済みのVPS接続で、次を確認します。

```bash
cd /opt/personal-vps
docker inspect -f 'status={{.State.Status}} restarts={{.RestartCount}} started={{.State.StartedAt}} oom={{.State.OOMKilled}}' personal-vps-schedtool-bot-1
docker stats --no-stream personal-vps-schedtool-bot-1
df -h /
```

正常の目安:

- `status=running`
- `restarts=0`、または意図した配備直後だけ増加している
- `oom=false`
- CPU・メモリ・ディスクに継続的な増加がない

### 2. 定時処理と日次ヘルスログ

```bash
cd /opt/personal-vps
docker compose logs --since 36h schedtool-bot | grep 'health.daily'
docker compose logs --since 24h schedtool-bot | grep 'auto_loop.completed' | tail -12
```

`health.daily`では、参加サーバー数、キャッシュ済みメンバー数、イベント数、回答数、DBサイズを確認します。`auto_loop.completed`は毎時の定時処理で、通常は数msから数十msで完了します。

Dockerとアプリログの時刻はUTCの場合があります。ユーザー向けの報告ではJSTに換算して記載します。

### 3. エラーと利用状況

```bash
cd /opt/personal-vps
docker compose logs --since 36h schedtool-bot | grep -Ei 'error|exception|traceback|warning|rate limit|forbidden|notfound' | tail -100
docker compose logs --since 36h schedtool-bot | grep 'command.used' | tail -100
```

ログにはトークン、環境変数、メッセージ本文、DM本文を記録しない設計です。ただし、公開報告ではサーバーID・チャンネルID・ユーザーIDも不要なので出さないでください。

### よくある記録の判断

| 記録 | 判断と対応 |
| --- | --- |
| `WSServerHandshakeError: 503` | Discord Gatewayの一時障害。自動再接続・`RESUMED session`を確認し、復旧済みなら監視のみ |
| `429` / `rate limited` | Discord APIの制限。ライブラリが待機して復旧する。継続する場合は起動時の一括更新や同時投稿を見直す |
| `Unknown Message` / 404 | Discord上で日程メッセージが削除済み。Bot停止には直結しない。対象DB記録の整理は承認後に行う |
| `Forbidden` / 権限エラー | 対象チャンネルでBotの「チャンネルを見る」「メッセージを送信」「埋め込みリンク」を確認。必要なら管理者に案内する |
| 再起動やOOM | 直近ログとホスト状態を保存して原因調査。復旧前に安易な連続再起動をしない |

## 修正・更新のルール

### 実装前

1. 再現条件、影響範囲、期待する挙動を短く整理する。
2. 既存の実装・テスト・ログを確認し、既存の設定や日程データを壊さない方法を選ぶ。
3. DBスキーマ変更、削除、既存投稿の更新、大量通知は、実行前に管理者の承認を得る。
4. 日程の回答、参加者、通知先設定はサーバー単位で独立している前提を保つ。

### 実装と検証

1. 修正はローカルのGit作業コピーで行う。手編集には`apply_patch`を使う。
2. バグ修正には、可能な範囲で再発防止のテストを追加する。
3. 最低限、構文確認・対象ユニットテスト・`git diff --check`を実行する。
4. Discordライブラリがローカルにない場合は、Dockerコンテナ内でテストする。
5. ユーザーに見えるコマンド、設定、通知文を変えた場合は、READMEとサポートページの該当箇所も同じ変更内で更新する。
6. 既存データの削除や修復は、対象イベントと影響を明示してから実施する。

### GitHub更新

1. `git status`で無関係な変更が混ざっていないか確認する。
2. コミット作成者は、リポジトリ所有者が指定したGitHubアカウント設定を使う。
3. 内容が分かる英語の命令形コミットメッセージを付ける。
4. テスト成功後に`main`へpushする。失敗した修正や未検証の変更をpushしない。
5. 強制push、履歴改変、秘密情報のコミットは行わない。

### VPS配備

配備前に、対象ファイルと既存のVPS設定差分を確認します。DBと`.env`は上書きしません。

```bash
cd /opt/personal-vps
docker compose --profile schedtool up -d --build schedtool-bot
docker compose exec -T schedtool-bot python -m unittest tests.test_member_changes.ChannelAccessTests tests.test_member_changes.ResultUpdateQueueTests
docker inspect -f 'status={{.State.Status}} restarts={{.RestartCount}} started={{.State.StartedAt}}' personal-vps-schedtool-bot-1
docker compose logs --tail 50 schedtool-bot
```

配備によるBot再起動は短時間発生します。再起動後は、Discord Gatewayへの接続、テスト成功、定時処理の継続を必ず確認します。問題があれば、直前の正常コミットに戻す方法を検討し、DBを巻き戻す前には必ず承認を得ます。

## 報告のルール

### 状況報告

事実と時刻を分け、次の順で簡潔に報告します。

1. 結論: 正常稼働か、障害中か
2. 稼働情報: 連続稼働時間、再起動数、CPU、メモリ、ディスク
3. 利用規模: サーバー数、イベント数、回答数、DBサイズ
4. 定時処理: 処理時間と失敗有無
5. 例外: 発生時刻、原因、復旧状況、ユーザー影響
6. 対応要否: すぐ必要な対応と、整理候補を分ける

外部サービスの一時障害、古い削除済みメッセージ、現在も継続する障害を混同しないことが大切です。

### サポートページ用の更新案内

ユーザーが知りたいのは「何が変わったか」「自分の操作が必要か」です。内部のクラス名、サーバーパス、例外名、テスト件数は書きません。

書き方:

- 先頭は`SchedToolをアップデートしました。`
- 変更点を3〜6個の箇条書きで記載する
- 修正は「何ができるようになったか」で表現する
- 操作が必要な場合だけ、対象者とコマンドをコードブロックで示す
- 影響がない場合は「既存の日程調整や回答データには影響ありません」と明記する
- 未確認の効果や将来予定を、完了した機能のように書かない

テンプレート:

    SchedToolをアップデートしました。

    主な変更点:

    - [ユーザーが分かる変更内容]
    - [改善・不具合修正]
    - [設定や通知に関する変更]

    必要な操作がある場合:

    管理者は以下を実行してください。

    /command_name option:value

    既存の日程調整や回答データには影響ありません。

コマンド名、表示文言、権限条件は、実装済みの内容と必ず照合してから掲載します。

## 変更後チェックリスト

- [ ] 対象の修正・テスト・ドキュメントを確認した
- [ ] 秘密情報、個人ID、DB、`.env`をコミットしていない
- [ ] `git diff --check`と対象テストが成功した
- [ ] GitHubの`main`へpushした
- [ ] VPSで再ビルド・再起動・コンテナ内テストを実施した
- [ ] Discord Gatewayへの接続と起動ログを確認した
- [ ] ユーザー向け告知が実装と一致している
- [ ] 結果報告に秘密情報や不要なIDを含めていない
