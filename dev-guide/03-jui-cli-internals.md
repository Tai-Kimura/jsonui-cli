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
- **attr-bindings**: 02章 §3。
- **api**: swagger → DTO/Domain（`--dry-run --json` が MCP の preview_api_model_sync の実体）。

## 5. `jui sync_tool` (`sync_tool_cmd.py`)

配布モデルの要。ホームインストール（`$JSONUI_CLI_PATH` > `~/.jsonui-cli`）から
プロジェクトローカルの `<platform_root>/<tool>_tools/` へミラーする
（`PLATFORM_TO_TOOL`: ios→sjui_tools, android→kjui_tools, web→rjui_tools）。

- **`extensions/` 以下は絶対に触らない**（`_is_extensions_path` がコピーも `--prune` もガード）。
  プロジェクト独自コンバータ（`rjui g converter` 等の出力）保護のため。
- `.ruby-version` をプラットフォームルートへ伝播（rbenv は CWD から上方探索するため、
  これがないと standalone `rjui build` が落ちる）。
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
