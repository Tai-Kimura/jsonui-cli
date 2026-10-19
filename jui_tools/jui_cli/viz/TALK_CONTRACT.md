# トーク（talk view）の WebSocket の約束

正（source of truth）は `talk_contract.json` の 1 つだけ。この文はその意味の説明で、形が食い違ったら JSON が正しい。
検査は `talk_contract.py` の `validate(frame)`（tests/test_viz_talk_contract.py が見本を通す）。
形を変えるときは JSON の `version` を上げ、サーバー（talk.py）とページ（web/js）を同じ commit の列で直す。

## 決まっていること（依頼者の確定、10-20「質問3つは全部それでいいよ」）
1. サブエージェントとの SendMessage も入れる（親 → 子の `to: <agentId>`、子 → 親の `to: "main"`）。Agent の起動の prompt と最後の返事は入れない（SendMessage ではない）。
2. トークの画面から送らない。見るだけ。送る口（入力欄・送信ボタン・POST）は作らない。
3. ブラウザの通知は出さない。新着は一覧の未読のバッジと行の並び替えだけ。
4. 相手（または自分）のセッションが死んだら、1 時間（`graceSecDefault` = 3600、config の `talkGraceSec`）待ってからそのトークを消す。待つ間に同じセッションが戻れば消さない。消した後に戻ったら transcript から作り直す。
5. 詳細のヘッダーに相手の名前（と札）。押すと相手のロボットに切り替わる（`peer.agentId` が null でないときだけ押せる）。1 行に入らなければ末尾を「…」で省略し、全文はホバーの浮き札（57-fulltext.js）で見せる。

## 言葉
- **owner**: 一覧を開いたロボット（`agentId`）。一覧も詳細も owner から見た形で届く。`dir: "out"` は owner が送った通（右の吹き出し）、`"in"` は相手から（左）。
- **トーク（conversation）**: 2 者の組。`id` は `t-` + 16 桁の 16 進で、組の 2 者の鍵から決まる（どちらの owner から見ても同じ id）。安定。
- **参加者の鍵（peer.key）**: そのロボットの agentId（主＝セッション id、子＝サブエージェントの id）。この機械にいない相手（名前が解けない・クラウド・別の機械）は `x:` + 送った宛先の名前。
- **peer.kind**: `session`（どこかのセッションの主ロボット）、`subagent`（子）、`external`（この機械で見えない。`agentId` は null）。

## 安定した id
- `conversation.id`（`t-…`）、`message.id`、`peer.key`、`owner`/`agentId`。
- `message.id` の作り方（この順で最初に取れたもの）:
  - `m-<msg_id>`: CLI の msg_id（送り手の tool_result の `toolUseResult.msg_id` ＝ 受け手の `origin.msg_id`）。
  - `u-<tool_use id>`: msg_id の無い送り（届かなかった通、子との通）。
  - `r-<受け手の sid>:<記録の uuid>`: 受け手側でしか見えない通（送り手がこの機械にいない）。
- 同じ通は 1 回だけ届く。後で状態が変わったら同じ `id` の `message` op が来る（上書き）。

## 1 通（message）
| 欄 | 意味 |
|---|---|
| `at` | 送った時刻（送り手の tool_use の timestamp、ms）。送り手が見えない通は受け手の最初の記録の時刻 |
| `deliveredAt` | 届いた（受け手の enqueue の時刻。見えなければ、送りの結果が成功（msg_id あり）の時刻か、読んだ記録の時刻）。無ければ null |
| `readAt` | 受け手が読んだ（受け手の isMeta / queued_command の記録）。LINE の「既読」はこれ。`dir: "out"` の通に出す |
| `state` | `sent`（送った、結果待ち）・`delivered`・`read`・`undelivered`（「No agent named … is reachable」や失敗。印を付けて見せる。他の着信には付けない） |
| `text` / `cut` | 本文（受け手の `origin.body`、無ければ送り手の `input.message`）。`textMax` 字で切り、切ったら `cut: true`。Markdown は履歴と同じく escape して描く。長い本文は折りたたみ、本文のクリックでも開閉 |
| `summary` | 送り手の `input.summary`（無ければ null） |
| `seen` | どちら側の記録から見えたか: `both` / `sender` / `receiver` |
| `via` | 相手の種類: `session`（セッション間）、`subagent`（親から子へ）、`parent`（子から親 = `to: "main"`）、`external` |
| `merged` | 受け手が 2 通を 1 記録に束ねた（`origin.members`）通 |
| `msgId` | CLI の msg_id（無ければ null）。表示しない。照合と検証のため |

## 1 トーク（conversation、一覧の 1 行）
`peer`（相手の札・名前・生死）、`lastAt`（最後の通の `at`）、`preview`（最後の通の 1 行目、`previewMax` 字）、`lastDir`、`unread`、`count`。
- 並びは `lastAt` の新しい順（ページが並べる）。
- `unread`: 相手からの通（`dir: "in"`）のうち、owner の画面でまだ見ていない数。「見た」は `talk.seen` の `upTo`（ms）以下の `at`。トークを初めて索引した時点より前の通は既読として数えない（viz を初めて起動したときに過去の全部がバッジにならない）。
- `peer.alive: false` のとき `goneAt`（死んだと見えた時刻）と `removeAt`（= goneAt + 猶予）。ページは「相手は終了しました」を出してよい。`removeAt` を過ぎたらサーバーが `remove` op を送る。

## やりとり
ページ → サーバー（認証済みの WebSocket。応答や失敗は既存の `{"type":"ack","reqId","ok":false,"error"}`）:
- `talk.open {reqId, agentId}`: そのロボットの一覧を見始める。1 つの socket で 1 ロボットだけ（後の open が前を置き換える）。返事は `talk.list`。以後そのロボットの増分（`talk.update`）がこの socket に届く。
- `talk.close {reqId?}`: 見るのをやめる（増分が止まる）。
- `talk.get {reqId, agentId, convId, before?, limit?}`: 詳細の通を新しい方から `limit`（既定・上限 `pageMax`）通、古い順に並べて返す（`talk.messages`）。`before` は `message.id`（それより古い通）。`more: true` ならさらに古い通がある。
- `talk.seen {reqId, agentId, convId, upTo}`: 詳細を開いている間に見た通の最後の `at`。サーバーは未読を数え直し、`conv` op を送る。

サーバー → ページ（`talk.badges` 以外は、その socket が求めたか `talk.open` したロボットの分だけ）:
- `talk.list {reqId?, agentId, items, more}`: 一覧（`listMax` 行まで、新しい順。超えたら `more: true`）。
- `talk.messages {reqId, agentId, convId, items, more}`。
- `talk.badges {counts}`: チャットのアイコンのバッジ。`counts` は ロボットの agentId → 未読の合計（そのロボットの全トークの `unread` の和）。**0 のロボットは入れない**（空の `{}` は「どこにも未読なし」）。毎回全体を送る（差分ではない。小さいので）。送る時: socket の認証の直後（snapshot の後）に 1 回、以後は合計が変わったとき（新着・`talk.seen`・トークの削除）に、`talk.open` していない socket も含む全部の socket へ。本文・要約・名前・path は入らない（数だけ）。
  - `talk.seen` を受けたら、サーバーはそのトークの `unread` を数え直して `conv` op（open している socket へ）と、合計が変わったなら `talk.badges`（全 socket へ）を送る。
- `talk.update {agentId, ops}`: 増分だけ（全部を送り直さない）。`ops` は `opsMax` 個まで、超える分は次の frame。
  - `{op: "message", convId, message}`: 新しい通、または状態が変わった通（届いた・読んだ）。`id` で上書き。
  - `{op: "conv", conv}`: 一覧の 1 行の新しい形（新着で `lastAt`・`unread` が変わった、相手が死んだ・戻った）。
  - `{op: "remove", convId, reason}`: 猶予を過ぎて消した（`peer-ended` 相手が死んだ / `owner-ended` 自分が死んだ）。

## 大きさ（`limits`）
`textMax` 20,000 字（調べた最大は 13,683 バイト）、`summaryMax` 200、`nameMax` 200、`previewMax` 120、`listMax` 200 行、`pageMax` 100 通、`opsMax` 100、1 トークに残す通 `keptPerConversation` 5,000（古い方から索引を外す。transcript は元のまま）。

## 出さないもの
- ファイルの場所（transcript・DB の path）は一切送らない。ページが読み出しに使える path は無い。
- トークの本文は slice・snapshot・イベントの記録・書き出し（export）に入れない。`talk.*` の返事と増分だけ。
- サーバーのログに本文を書かない。
