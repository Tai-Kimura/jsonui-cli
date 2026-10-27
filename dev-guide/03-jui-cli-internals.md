# 03. jui_tools — Python 統合 CLI「jui」の内部構造

エントリ: `jui_tools/bin/jui`（pip install なしでも動くよう sys.path を自己注入）→
`jui_cli/cli.py`（argparse、`command_map` で dispatch）。パッケージ: `jui-tools`（版数はリポ直下
`VERSION` = 現 1.1.0 を実行時参照 — タグ運用と lockstep 検査は 09章）、
deps は watchdog / aiohttp、extra `conformance` で Pillow。
エイリアス: `init`=`i`, `generate`=`g`, `build`=`b`。

## 1. コマンド → 実装対応表

| コマンド | モジュール | 備考 |
|---|---|---|
| `jui init` | `commands/init_cmd.py` | `_sync_one_tool` を再利用してツールコピーも播種 |
| `jui generate project\|screen\|converter\|api\|attr-bindings` | `commands/generate_cmd.py` | |
| `jui build` | `commands/build_cmd.py` | 下記 §2 |
| `jui verify` | `commands/verify_cmd.py` | 下記 §3 |
| `jui migrate-layouts` | `commands/migrate_cmd.py` | |
| `jui lint-generated` | `commands/lint_generated_cmd.py` | inode で dedupe（case-insensitive FS 対策） |
| `jui ls api-specs\|api-models` | `commands/ls_cmd.py` | MCP 用 `--json`。swagger halt 条件を build 前に検出 |
| `jui sync_tool` | `commands/sync_tool_cmd.py` | 下記 §5 |
| `jui hotload listen\|status\|stop` | `commands/hotload_cmd.py` → `hotloader/` | WebSocket wire protocol v2。サーバーは jui に集約済み（sjui watch はレガシー） |
| `jui viz serve\|status\|stop\|open\|doctor\|hooks\|relay\|export-demo` | `commands/viz_cmd.py` → `viz/` | 下記 §6.6。jui.config.json 不要（どこからでも起動）。127.0.0.1 だけ |
| `jui conformance generate\|report\|gate\|compat-doc\|baseline` | `commands/conformance_cmd.py` → `conformance/` | 08章。`gate` は CI と同一判定をローカル実行（ratchet 台帳 = `conformance/gate_ratchet.json`） |

ほとんどのハンドラは `ConfigManager()`（`jui.config.json` を上方探索）をまず作る。
MCP の `mcp__jui-tools__jui_*` ツール群はこれらの薄いラッパ（07章）。

## 2. `jui build` の実行順序（`build_cmd.py::cmd_build`)

1. **配布**: `_distribute_layouts`（L1 正規化はデフォルト ON。配布時に `_generated` マーカー注入、
   orphan コピーの削除も行う）→ `_distribute_styles` → `_distribute_resources` →
   `_distribute_images`（SVG → imageset/VectorDrawable/svg、`core/image_converter.py`、
   rsvg-convert or cairosvg 必須）→ `_distribute_hotload_config`（iOS/Android バンドルに
   `hotloader.json`、Android は `network_security_config.xml` の cleartext IP をマーカーブロックで管理）
2. **API モデル同期** `_sync_api_models`: swagger → DTO + Domain（`core/api_model_sync.py` の
   collect_docs / plan_for / apply_plan）。halt 不変条件（多ファイル `$ref`、直接自己参照など）で
   ビルド停止。※ oneOf + discriminator は対応済み（halt ではない）— agents 文書と同期済みであること
3. **ViewModel Protocol 同期** `_sync_viewmodel_protocols`: spec の `dataFlow.viewModel` +
   Impl の `// @jui:protocol` マーカーから Protocol/Base を再生成（`core/protocol_sync.py`,
   `method_extractor.py`）。Impl の継承リスト / Kotlin `override` を **atomic に in-place patch**
   （`core/impl_updater.py`）。spec↔Impl drift は **ハードエラー**
4. **各プラットフォームビルド**: `core/tool_resolver.py` の `resolve_tool`（プロジェクトローカル →
   PATH）+ `build_tool_env`（RBENV_VERSION 注入等）で `sjui build` / `kjui build` / `rjui build` を実行

**ビルド中の converter 自動生成は削除済み**（`build_cmd.py:74-80`、非対話 MCP/CI を塞いだ問題への対処。
バグレポート 2026-04-23 参照）。`jui g converter` を明示実行する。

## 3. `jui verify` (`verify_cmd.py`)

- spec からメモリ内で Layout を再生成（`LayoutGenerator`）し、実ファイル
  （`_resolve_actual_layout`、layoutFile/名前マップのフォールバックあり）と
  `core/view_diff_checker.py` で diff。
- 追加レポート: data セクション孤児（Layout `data[]` にあるが spec `uiVariables` にない —
  **generate/verify ともハードエラー**）、未登録カスタム型（`.jsonui-type-map.json` 提案）、
  API モデル drift（DTO をメモリ再生成してディスクとバイト比較 — build と独立）。
- `normalizeLayouts` ON のときは両辺に同じ normalizer を適用（02章 §2 の偽 drift 防止）。
- `--fail-on-diff` が CI 用。

## 4. `jui generate` 系

- **project**: spec 収集 → `document_tools` の SpecValidator で検証
  （`config_mgr.ensure_document_tools_importable()` — import 失敗は警告を出す。過去に silent 破損バグ）→
  `ParentSpecMerger`（first-write-wins）→ `extract_screen_spec` → `RepositoryAggregator` →
  Layout JSON を共有 layouts_directory へ + セルレイアウト（`cell_layout_generator.py`）→
  各プラットフォームの VM 宣言（自動更新・diff 警告、`--force`）+ VM Impl（**上書きしない**）+
  Repository/UseCase 集約ファイル。`.jui_cache.json` 保存。
- **screen**: `<snake_name>.spec.json` テンプレート出力。
- **converter**: `--all` / `--from <spec>` / 直接名。`sjui/kjui/rjui g converter` へシェルアウト。
  `--skip-existing` → 環境変数 `JUI_SKIP_EXISTING=1` で Ruby 側の上書きプロンプトを回避。
  `--force` → 各ツールへ `--force`（1.8.113 から。それまで sjui / kjui は invalid option で拒否していた）。
  `--from` / `--all` は spec の `props.items[].description` と `exposedEvents[].description` を
  `--attribute-descriptions '<JSON>'` で渡し、`attribute_definitions/<Name>.json` の description に残す
  （JSON は `\u` エスケープの ASCII — LANG 未設定だと生の UTF-8 引数は Ruby に binary で届く。
  rjui が生成物に記録するコマンドラインにはこの JSON を入れない。sjui / kjui の記録にも無い）。
  直接名の形は spec を持たないので `"<key> attribute"` のまま。
- **attr-bindings**: 02章 §3。
- **api**: swagger → DTO/Domain（`--dry-run --json` が MCP の preview_api_model_sync の実体）。

## 5. `jui sync_tool` (`sync_tool_cmd.py`)

配布モデルの要。ホームインストール（`$JSONUI_CLI_PATH` > `~/.jsonui-cli`）から
プロジェクトローカルの `<platform_root>/<tool>_tools/` へミラーする
（`PLATFORM_TO_TOOL`: ios→sjui_tools, android→kjui_tools, web→rjui_tools）。

- **`extensions/` 以下は絶対に触らない**（`_is_extensions_path` がコピーも `--prune` もガード）。
  プロジェクト独自コンバータ（`rjui g converter` 等の出力）保護のため。
- `.ruby-version` をプラットフォームルートへ伝播（rbenv は CWD から上方探索するため、
  これがないと standalone `rjui build` が落ちる）。ただし書くのは**ルートに pin が無く、
  かつそのパッチ版（例 3.2.2）が rbenv に入っているときだけ**。既存の pin は書き換えない
  （3.2 以上は黙って保持、3.2 未満は名指しで警告のみ）。未インストールの pin を書くと
  rbenv がツール起動前に止まり、ツール側の Ruby floor ERROR の案内が届かなくなるため
  （`tool_resolver` の RBENV_VERSION 方針と同じ）。
- `SHARED_CORE_PAYLOADS`（font_weight_mapping.json）を `<tool>/shared/core/` に配布
  （漏れると sjui が font weight を全部 .regular に丸める）。
- `--prune`（extensions/ 以外の孤児削除）、`--dry-run` あり。

## 6. hotloader (`jui_cli/hotloader/`)

`server.py`（aiohttp WebSocket）+ `watcher.py`（watchdog）+ `layout_resolver.py` ほか
正規化サブモジュール群（normalizer の出自）。クライアントは
`{type:hello, platform:ios}` を送り、サーバーが `layout_changed` / `style_changed` を push。
hotloader は事実上 **L2 を配信**している。iOS 側受信は `SwiftJsonUI/Classes/HotLoader/`、
Android は library-dynamic の `hotloader/`。ドキュメント: `docs/hotload/README.md`。

## 6.5 jsonui-doc check（document_tools、2026-07-07 追加）

`docs/api`・`docs/db` と実装の契約照合。実装は `document_tools/jsonui_doc_cli/`
の `project_config.py`（checks/databases 宣言 + コマンドパス検証）、
`check/`（runner / report 契約 schemaVersion=1 / openapi_normalize+diff /
db_schema/）。ユーザー向け仕様は `docs/jui_tools_README.md` の check 節、
設計判断は `docs/plans/2026-07-07-doc-contract-check-review.md` + `-05-impl-plan.md`。

- 不変条件: `generate html` 単体はコード実行ゼロ・レポート無しで出力不変 /
  ベースインストール依存ゼロ（SQLAlchemy は optional extras）/ 実行対象は
  config 宣言のみ。exit 0/1/2 は check コマンド限定の新規約。
- FastAPI ノイズ（anyOf-null / allOf ラッパ / 自動422 / response_model 未宣言 /
  param nullable）は `openapi_normalize.py` + diff 側 skipped 集約で吸収済み。
  新しい偽陽性クラスを見つけたら emitter でなく正規化層に足す。

## 6.6 jui viz（`jui_cli/viz/`、2026-10-18 追加）

手元の Claude Code のセッションとサブエージェントを、three.js の部屋とロボットでブラウザに出す。
計画書と判断の記録はリポジトリの外（引き継ぎパッケージの `plan/` と `PROGRESS.md`）。ここは保守に要る形だけ。

- **構成**: `serve`（aiohttp、127.0.0.1:7788）が、フック（`forward.py` → `POST /hook`）、`claude agents --json`
  （`sources/agents_cli.py`、3 秒）、`~/.claude/sessions/<digits>.json`（`sources/session_files.py`、watchdog）、
  JsonUI のプロジェクトのファイル（`sources/jsonui_project.py`）、端末（`sources/devices.py`）、
  テストの進捗（`sources/test_progress.py`）を `ingest.World` に集め、スライス（`state.py`）として
  200ms ごとに WebSocket で配る。画面は `web/`（試作第 4 版を持ち込み、`bundle.py` が `web/js/` を連結）。
- **時刻は引数**: `World` のどの入口も時刻を引数で受け、`tick(at)` でタイマー（退場 5 秒、done→idle 3 秒、
  ended の 60 秒）を進める。`--replay` は記録の時刻で仮想の時計を回す（500ms ごと、最後のあと 70 秒）。
  これで「記録して再生すると同じ最終状態」が成り立つ。
- **守り**（`security.py`）: Host（421）、`/ws` の Origin（403）、起動ごとのトークン（`server.json` 0600 と
  ページの meta）。守る相手は「利用者のブラウザの別のサイトのページ」。同じ利用者の別プロセスは守らない
  （`GET /` がトークン入りの HTML を返す。mock serve と同じ）。ヘッダーは `on_response_prepare` で全応答に。
- **停止**: `stop` は viz.pid と server.json の pid が一致し、その port の `/health`（生のソケット。urllib は
  HTTP_PROXY に従う）が同じ pid を返すときだけ SIGTERM。viz.pid は 2 以上の整数だけ、中身つきの一時ファイルを
  `os.link` して作る（O_EXCL で空のまま作ると、同時に起動した 2 つ目が空を「壊れている」として消した）。
- **配り方**: 主は Claude Code のプラグイン（`plugins/jui-viz/`、マーケットプレイスはルートの
  `.claude-plugin/marketplace.json` の `jsonui`）。フック・チャンネル（MCP サーバー）・SessionStart で
  `CLAUDE_ENV_FILE` に `JSONUI_TEST_PROGRESS_DIR` を書くスクリプトを持つ。`scripts/forward.py` と
  `scripts/channel.py` は `jui_cli/viz/` の写しで、`tests/test_viz_plugin.py` がバイト一致を見る
  （片方だけ直すと赤）。中身を変えたら `plugin.json` の `version` を上げる（上げないと利用者の版が動かない）。
  プラグインが有効な環境では `jui viz hooks install` は二重の転送を避けて止まる。
- **フック**（`hooks_installer.py`、プラグインを使わない環境の代わり）: `~/.claude/settings.json` に 18 イベントの async の転送と、
  PermissionRequest の同期の `forward.py --decide`（P6）と、UserPromptSubmit・PreToolUse・PostToolUse の同期の `forward.py --stop`（2.3.20）を足す。自分のものの見分けは「python で、
  引数が `jui_cli/viz/forward.py` で終わる」だけ。読めない JSON には書かない、バックアップ 10 個、
  stat を読む前と後に取る、書く直前に変わっていたら読み直す。`env` に `JSONUI_TEST_PROGRESS_DIR`。
- **許可**（`permissions.py`、`channel.py`）: 段階 A（PermissionRequest でカード）、B（MCP チャンネル
  `jui-viz` の中継）、C（同期のフック。今後も許可＝その要求の `permission_suggestions` だけ、理由つきの拒否）。
  照合は推測でつながない（候補が 1 枚でも、コマンドやパスが中継の preview に含まれること）。
  チャンネルは JSON-RPC 以外を stdout に書かない。`notifications/claude/channel`（セッションの文脈への書き込み）は、
  サーバーの poll がそのチャンネルに渡したプロンプトだけを、打たれたとおりに送る（1.2.0、依頼者の裁定 10-19）。
- **ページからのプロンプト**（`server.py` の `POST /api/prompt` と `prompt_checks`、`ingest.send_prompt`、`55-history.js`）:
  応答の履歴タブの入力欄から、そのロボットのセッションへ。受けるのは POST・Host がちょうど `127.0.0.1:<port>`・Origin が
  ちょうど `http://127.0.0.1:<port>`・トークン・`application/json`・本文 8 KB まで、の全部を満たすものだけ。宛先は
  session id で、中継（relay）があり、そのチャンネルの hello が `accepts: ["prompt"]`（jui-viz 1.2.0 以上）のものだけ。
  イベントログには時刻・宛先・先頭 40 文字だけ（本文はチャンネルの待ち行列にだけあり、渡したら消える）。
  待ち受けは 127.0.0.1 固定で、変える口（オプション・設定）は無い。古いプラグインのセッションはページと doctor がそう言う。
  **届くのは、起動のときに channel を名指ししたセッションだけ**（2.3.4。CLI は名指しの無い channel の文を黙って捨てる。
  MCP のログに `not in --channels list for this session`）。名指しは `--dangerously-load-development-channels plugin:jui-viz@jsonui`
  （`jui viz relay install` で入れたなら `server:jui-viz`。起動のたびに確認が出る）。または managed settings
  （macOS: `/Library/Application Support/ClaudeCode/managed-settings.json`）に
  `{"channelsEnabled": true, "allowedChannelPlugins": [{"plugin": "jui-viz", "marketplace": "jsonui"}]}` を載せれば、
  `claude --channels plugin:jui-viz@jsonui` で警告なしに使える（allowedChannelPlugins は既定の承認リストを置き換える。10-19 に依頼者の前で確認）。
  組織のアカウントは `channelsEnabled` が要る。managed settings の中身は viz からは見ない（--channels の起動は届く扱い）。
  VS Code 拡張とデスクトップアプリは起動の引数を足せないので届かない。見分けは `sources/launch.py`: セッションファイルの pid の
  argv（macOS は sysctl KERN_PROCARGS2、Linux は /proc の cmdline）と entrypoint、channel.py の hello の `via`（plugin / mcp、1.2.1）。
  公開するのは分類（`sessions[].launch`）だけで、argv は出さない。届かないセッションはサーバーが 409 で断り、ページは理由と起動の仕方を出す。
  ページは「送信中」→ 受け手の transcript（応答の履歴）に送った文が出たら「届いた」、出ないまま 60 秒・セッションが 30 秒静かなら「届いていない」。
  自分の POST の成功は「送った」までしか言わない。受け手の transcript での記録は、本物で測った形（10-19）: `user` の記録で `isMeta`、
  `origin: {"kind": "channel", "server": "plugin:jui-viz:jui-viz"}`、中身は `<channel source="plugin:jui-viz:jui-viz" sender="jui_viz_page">` で包んだ文。
  `sources/history.py` はこれを `channel` の項目（包みを外した文）にし、ページはこの項目の文が送った文で始まるときだけ「届いた」にする。
  同期のフックは、表示中のページ（presence、12 秒）が無ければ即座に空で返る。
- **停止**（2.3.20、jui-viz 1.3.0。`server.py` の `POST /api/stop` と `POST /hook/stop`、`ingest.request_stop` / `hook_stop`、`55-history.js` の stopPaint）:
  応答の履歴タブの「送信」の隣。押すとサーバーがそのセッションに停止の要求（`sessions[].stopAt`）を立て、次の道具の区切りで
  同期の `forward.py --stop`（PreToolUse・PostToolUse、timeout 3、接続 0.3 s・返事 0.7 s で諦めて何も出さない）が
  `{"continue": false, "stopReason": …}` を返す。中継もチャンネルも要らない。受け口の確かめは `/api/prompt` と同じ。
  測った形（10-22、Claude Code 2.1.307、隔離）: PreToolUse で返すと、その呼び出しは走ってから止まる（`terminal_reason: hook_stopped`）。
  PostToolUse で返すと、モデルへの次の呼び出しは無いが、同じ応答に入っていた次の呼び出しは走った。どちらも Stop のフックは来ず、
  次の入力は普通に受ける。なので、主のロボットの最初の区切りで要求を渡し（`stopAt` → `stopTurn`、Stopped を 1 回）、
  そのターンの後の区切りにも同じ返事をする。ターンは、その呼び出しの PostToolUse ごとにサーバーが終える。サブエージェントには
  同じ返事をして要求は残す。止めたターンは、次のプロンプトの同期の `--stop`（UserPromptSubmit）で消す。プロンプトの async の
  転送は新しいターンの最初の道具より後に着くことがあるので、そちらには頼らない。Stop・セッションの終わりでも、まだ渡していない要求は消える。`--stop` が一度も聞こえていないセッション（古いプラグイン）も頼めるが、ページは止まらないかもしれないと言う。
- **退勤**（`server.py` の `POST /api/session/end`、`clockout.py`、`ingest.clock_out`、`50-panel.js` の CLOCK）:
  ロボットのカードの「退勤…」から、確認（ロボット・セッションの title・フォルダ・クライアント、既定のフォーカスはやめる）の後に、
  そのセッションの claude へ SIGTERM を 1 回。使えるのはターミナルで起動したセッション（登録簿の `entrypoint` が `cli`）だけで、
  VS Code（タブがエラーで残る）とデスクトップアプリ（画面が変わらない）はページでも無効、サーバーでも断る（依頼者の目の前の測定と裁定、10-19）。
  リクエストの検査は `prompt_checks` をそのまま使う（上限は 1 KB）。そのあと、このサーバーのセッション一覧にあって終わっていないこと、
  メインのロボットであること（サブエージェントは断る）。pid は `~/.claude/sessions/<pid>.json` から引き、sessionId・pid・
  `kind: interactive`・`entrypoint: cli`・viz 自身でない・ps のコマンド行の argv[0] が claude・開始時刻が `procStart` と同じ
  （再利用された pid は別の時刻に始まっている）を確かめ、合図の直前にもう一度全部を確かめる。SIGKILL は送らない
  （6 秒で終わらなければ「終わらなかった」と返すだけ）。試みは全部 `<viz_home>/clock-out.log`（0600、1 行 1 JSON）と stderr、
  知っているセッションならイベントログにも残る。終わったら session-recovery の台帳（`~/.claude/session-recovery/active.json`、
  別レーンの道具）の該当エントリに `ended_reason: "clocked-out"` を付ける。ロックは common.sh の `lock_acquire` と同じ
  （`.lock` の mkdir、0.1 秒おきに 50 回、30 秒より古いロックは捨てる、`active.json.tmp.<pid>` からの rename）。ファイルが無ければ何もしない。
- **テストの進捗**: driver 3 種が `schemas/progress.schema.json`（jsonui-test-runner、写しは
  `test_tools/tests/schema_fixtures/`）の 1 行を出す。Web はフォルダの .jsonl、Android は logcat、
  iOS は unified logging。jui_tools に JSON Schema のライブラリが無いので検証は手書きで、
  テストがスキーマのファイルと機械で突き合わせる。
- **テストの結果（保存分）**: `sources/test_results.py`。driver は resultsPath が無いとき、run ごとに
  `<base>/<platform>/<app>/<UTC>-<run>.json` を書く（base = `JSONUI_TEST_RESULTS_DIR` か
  `~/.local/state/jsonui-test/results`。XDG_STATE_HOME には従わない＝シミュレータから見えない）。
  Android は端末の `/data/local/tmp/jsonui-test-results/<package>/` を、起動時に 1 回と run_end のときだけ
  `adb pull`（timeout 20 秒）。spec への結び付けは推測しない: ① サーバーが見た run id → ② Android の
  `test.artifacts.android.appId` → ③ そのテストファイルを持つ app が 1 つだけ、のどれにも当たらなければ付けない
  （iOS に ② は無い）。進捗と保存分は (file, test, case) ごとに新しいほうを採る。spec / layout の mtime が新しければ
  「結果は古い可能性」（checkout でも mtime は動くので断定しない）。`jui viz doctor` が読む場所を印字する。
- **テストファイルと spec**: テストの根と照合は jsonui-test の `test_tools/jsonui_test_cli/test_dirs.py` を
  パスで読んで使う（規則の写しを作らない。無ければテストを数えない）。根は `test.testDir`（既定 `tests`、
  config のフォルダ相対、app の外も可）で、再帰で読む。driver の `file` は面ごとに綴りが違う（iOS はファイル名だけ、
  Android は `tests/<name>`、Web は起動フォルダからの相対）ので、後ろからのパスの要素が最も長く一致する
  ただ 1 つのテストファイルに解決し、同点なら付けない。driver は 1 テストファイルに 1 run を出すので、
  1 つのテストのコマンドに run を全部結ぶ（`progressRuns`。`progressRun` は最初の 1 本のまま）。
- **上限（ヘッダ）**: 取れる口は、Claude Code が statusLine のコマンドに渡す JSON の `rate_limits` だけ
  （five_hour / seven_day、used_percentage は 0〜100 で 100 頭打ち、resets_at は epoch 秒）。`viz/statusline.py` が
  POST /usage に送り（forward.py と同じ生ソケット・短い timeout・失敗は黙る）、`viz/usage.py` が検証して
  viz_home/usage.json に残す（再起動しても最後の値）。`jui viz statusline install` が settings.json に書き、既存の
  statusLine は `--wrap <base64>` で包む（出力はそのまま、uninstall で元の値に戻す）。⚠️ statusLine を走らせるのは
  ターミナルの claude だけで、VS Code 拡張（2.1.301 で確認）とデスクトップアプリ（10-19 に確認）は走らせないので、ヘッダは 15 分を超えると「◯分前」（10-19 まで「◯分前の値」）。
- **シュレッダー（削除）**: Claude Code に削除の道具は無く、削除は Bash。`robots.deletions` がテストの見分けと同じく
  単純コマンドごとに「実行ファイル＋サブコマンド」で読む（rm・rmdir・unlink・trash・git rm・git worktree remove・
  find -delete / -exec rm。sudo・command・`\rm`・`git -C` も。git rm の -n / --dry-run / --cached と、文字列の中の rm は
  数えない）。対象は書かれた形のまま（glob は展開前、-r のフォルダは 1 件）。PostToolUse でエージェントに `shred`
  （成否・名前・件数・フォルダか・時刻）を付け、拡大した部屋（小物の条件）ではロボットが書類を持って奥の壁の
  シュレッダーへ行く。削除は休憩・遊び・居眠りを終わらせ（同じフレームで始まったものも）、git の箱への往復は待つ。
  新しい指示（`promptAt`）・道具・電話で即やめる。終わったターン（done）は続ける。
  見えないもの: スクリプトの中の削除、利用者自身の削除（doctor に出す）。
- **データサーバー（2.3.5）**: JsonUI の部屋の `docs/api`・`docs/db`（部屋の根と各アプリの config の根。`docs/db/<名前>/`
  は別の DB）にある仕様を、`viz/data_docs.py` が document_tools の部品（`is_swagger_file`・`has_api_paths`・ER 図の
  `_build_mermaid_erd`。`core/document_tools_import.load_document_tools_module` で読む）で見つけて数え、件数を部屋の行の
  `dataDocs` に載せる。拡大した部屋に 1 件以上あればラックを置き、押すと `POST /api/data-docs`（`prompt_checks`、部屋の
  ID だけ、パスは受け取らない、部屋の外へ出る symlink と `..` は読まない、件数と大きさに上限）で、その時に読む。
  スナップショットにも export にも入らない。ER 図とデータの流れの図は、同梱の Mermaid（`web/vendor/VENDOR.md`、
  securityLevel strict・htmlLabels なし、初めて描くときだけ読む）。データの流れの図の文字列は、spec ページと同じ規則
  （`sheet.dataflow_mermaid` → html_generator）。
- **Codex のセッション**（`sources/codex_app_server.py`、`ingest.apply_codex` / `codex_approval` / `codex_resolved`、2026-10-26 試作）:
  Codex の app-server daemon（`codex app-server daemon start`。ソケットは `$CODEX_HOME/app-server-control/app-server-control.sock`、
  Unix ソケット上の WebSocket で JSON-RPC）に 1 本つなぐ。ターミナルの `codex` は daemon があれば自分でそこに載る
  （macOS・Linux、Codex 0.164.0 で確認）。`thread/loaded/list` を 3 秒ごとに見て、新しいスレッドは `thread/resume`（`excludeTurns`）で購読する。
  届いた通知は `Translator` が Claude Code のフックの形（SessionStart・UserPromptSubmit・PreToolUse / PostToolUse の Bash・Edit・Write・
  mcp__…・Stop・SubagentStart / Stop・SessionEnd）に置き換え、`apply_hook` にそのまま渡す（テストの見分け・シュレッダー・ファイルの印が
  そのまま効く）。親スレッド（`parentThreadId`）のある子はサブエージェント。セッションとロボットに `cli: "codex"`（Claude Code のには無い）。
  ラベルは id の末尾から（UUIDv7 の先頭は作成時刻で、どれも `01a17…` になる）。
  ターミナル終了の検知は `sources/codex_clients.py`。その home の `logs_2.sqlite` を開いているプロセスを
  `lsof` と `ps` で照合し、daemon や `codex exec` を除いた TUI がいなくなったと確認できたら、idle の CLI ロボットを退勤させる。
  別の TUI が同じ home に残る場合は、どのスレッドの持ち主かは推定しない。取得失敗は不明として在席を保つ。
  daemon の loaded/list に残っていても復帰させず、そのスレッドの新しい turn/userMessage が来た時だけ復帰させる。
  許可: `item/commandExecution/requestApproval`・`item/fileChange/requestApproval` は TUI のダイアログと viz の両方に届く（先に答えた方が勝ち、
  もう一方に `serverRequest/resolved`）。カードは PermissionRequest と同じ（`hook_decide` の future）。答えは `accept`／`decline`、今後も許可は
  `acceptWithExecpolicyAmendment`（`proposedExecpolicyAmendment`）か `acceptForSession`（ファイル）。`item/permissions/requestApproval` には答えない。
  停止は `turn/interrupt`（その場で止まる。`--stop` フックは無い）。ページからの送信は `POST /api/prompt` から、待機中は `turn/start`、
  作業中は `turn/steer`（`expectedTurnId` 付き）。daemon の受付を待って成功を返し、モデル・承認方針・sandbox は上書きしない。
  ほかに書き込むのは許可の答えと、呼び出しダイアログの Codex タブで起動した
  スレッドの名前（`thread/name/set`、最初のプロンプトの「セッション名: …」から、名前の無いスレッドに 1 回）だけ。daemon が無いのは故障ではない
  （帯は出さない。`jui viz doctor` の `codex daemon` 行が起動の仕方を言う）。daemon を使わずに起動した Codex と VS Code 拡張のセッションは
  見えない（依頼者の判断 10-26）。応答の履歴は `sources/codex_history.py` が、`thread/resume` の `path` をその daemon の
  home の `sessions/` 内に限定して読む。`response_item` の user / assistant と tool call / output を既存の履歴の行に変換し、
  重複する `event_msg` と instructions・reasoning の本文は表示しない。既存の件数・バイト上限と「もっと前を読む」を共用。
  履歴は要求時だけ読み、slice・snapshot・export に入れない。ローカルモデルの home とサブエージェントの履歴も同じ。
  履歴タブの許可カードは初期状態で1行。pending→sent でも折り畳みを維持し、クリックして開いた選択はその待機が終わるまで保つ。
  まだ無いもの: コスト（`thread/tokenUsage/updated`）、トークの Codex 間（`CollabAgentToolCall`）。
  ページ: `20-core.js` の `cliOf` / `pillCli`。pill・3D の札・セッション一覧の札・カードの番号（`data-cli-name`）・トークの印が
  `--cli-claude` / `--cli-codex` で縁取られる。呼び出しダイアログは Claude Code / Codex のタブ（`callcmd.codex_command`、`POST /api/call-command` の `cli`）。
- **ローカルのモデル**（`local_models.py`、`codex_homes.py`、`jui viz codex-local`、2026-10-27）: 呼び出しダイアログの Codex タブで、
  LM Studio（127.0.0.1:1234）と Ollama（127.0.0.1:11434）の `GET /v1/models` から選べる（ダイアログを開いたときだけ `POST /api/local-models`）。
  `codex --oss` は使わない: ローカルの提供元を起動時に指定した codex（`--oss`、`-c model_provider=…`、プロファイル）は daemon に載らず、viz から見えない
  （Codex 0.164.0 で確認）。既定の提供元がそれになっている CODEX_HOME なら載り、`-m <model>` だけならそのまま載る。そこで提供元ごとに
  `~/.codex-local/<provider>/`（config.toml に `model_provider` と、`~/.codex/config.toml` の `[features]`・`[mcp_servers.*]` の写し。
  無いときだけ作り、あるものは書き換えない）を作り、その daemon で起動する。serve は `~/.codex` に加えて各 home の daemon にもつなぐ
  （source 名 `codex:<provider>`、5 秒ごとに新しい home を探す）。ソケットのパスが長いと Codex は `/tmp/codex-daemon-<uid>/<hash>` へのリンクに
  するので、つなぐ先はリンクの先。セッションは `modelProvider`（lmstudio / ollama）を持ち、カードにモデル名と「ローカル」の札を出す。
- **テスト**: `tests/test_viz_*.py`（pytest。サーバーは `aiohttp.test_utils` を `asyncio.run` の中で、
  CLI は一時の HOME とサブプロセスで）。ブラウザの e2e は pytest の外の `tools/viz_e2e/run.py`（Playwright）。

## 7. 罠（jui_tools 固有）

- **pip editable ポインタ乗っ取り**: 別 checkout からの `pip install -e` が console script を
  握っていると古いコードが動く。bootstrap は無条件再インストールでこれを潰す（bootstrap.sh:264-319）。
  「直したのに挙動が変わらない」時は `pip show jui-tools` で Location を確認。
- **共有 layouts は L0 のまま**: 正規化・`_generated` マーカーは配布コピーだけ。
  `lint-generated` も配布側のみ検査（Resources/Styles はスキップ）。
- **eventHandlers は Data に載らない**: callback プロパティは `uiVariables` /
  `dataFlow.viewModel.vars` に宣言する（spec 所有原則）。
- Web は Protocol 整合性検査をスキップ（構造が固有、member は `<Name>Data` 経由）。
  Swift の external-label drift チェックは iOS のみ。
- テスト実行: `cd jui_tools && python -m unittest discover -s tests`。
  決定論チェック 2 種（attr-bindings 2回一致 / conformance generate diff ゼロ）もローカルで回せる。
- **jui viz のテストで本物の `~/.jsonui-cli` / `~/.claude` に触らない**: `viz/paths.py` は呼ぶたびに `Path.home()`
  から作るので、テストは HOME を一時フォルダに向ける。ポートは 7788 を避ける（手元で動いている serve とぶつかる）。
- **jui_tools の中で `pip wheel .` すると `jui_tools/build/` ができる**: ルートの `.gitignore` は `/build/*` だけを
  無視していたので、`git add jui_tools` がこれを拾った（2026-10-18、push 前に枝を作り直した）。今は
  `/jui_tools/build/` も無視している。


Codex 0.164.0 の daemon は TUI 由来でも `source=vscode` を返す場合がある。退勤判定は source=cli に加え、その home の sessions 配下の rollout 先頭 session_meta（最大1MiB、thread id一致）の `originator=codex-tui` も確認する。IDE由来・確認不能のセッションをターミナル終了だけで退勤させない。
