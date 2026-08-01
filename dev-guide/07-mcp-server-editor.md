# 07. jsonui-mcp-server と jsonui-helper（エディタ層）

## 1. jsonui-mcp-server（MCP 名 `jui-tools`）

`jui-tools-mcp-server`（現 v2.4.0）、TypeScript ESM、`@modelcontextprotocol/sdk` + zod、stdio transport。
エントリ `src/index.ts`。**登録ツールは 42**（spec 7 + context 7 + jui 8 + doc 9 + api 3 + test 8）。
ツール数はドキュメントに書いた瞬間から古びる — 常に index.ts（実登録）が正。

### ツール群と実装方式

| グループ | ツール | 実装 |
|---|---|---|
| A. Spec lookup (7) | lookup_component / lookup_attribute / search_components / get_modifier_order / get_binding_rules / get_platform_mapping / get_data_source | **SpecLoader のメモリ内データを直接返す**（CLI もディスクも触らない）。modifier順序・binding規則・platform対応表は `src/data/derived.ts` に**手書き**で符号化（SSoT 由来ではない — 仕様変更時は derived.ts も更新） |
| B. Project context (7) | get_project_config / list_screen_specs / list_component_specs / list_layouts / read_spec_file / read_layout_file / get_screen_identity | fs 直接読み。`validatePathInProject()` が path traversal / symlink 脱出をガード |
| C. jui wrappers (8) | jui_init / generate_project / generate_screen / generate_converter / build / verify / migrate_layouts / sync_tool | `execFile("jui", ...)`（シェルなし、60s 既定 / **build は 300s**、PYTHONIOENCODING=utf-8） |
| D. doc wrappers (9) | doc_init_* / doc_validate_* / doc_generate_* / doc_rules_* | `execFile("jsonui-doc", ...)` |
| E. API discovery (3) | list_api_specs / list_api_models / preview_api_model_sync | `jui ls ... --json` / `jui g api --dry-run --json`（書き込みなし） |
| F. Test tools (8) | test_validate / test_report / test_generate_screen / test_generate_flow / test_generate_description / test_mock_generate / test_artifacts_pull / test_artifacts_status | `jsonui-test` CLI のラッパ（test_tools 移設で CLI 化 → MCP ツール化。2026-07 の test_tools 移行計画） |

C/D/E は bare コマンド名で呼ぶため **PATH に jui / jsonui-doc が必要**
（jsonui-cli bootstrap がインストールするもの）。プロジェクトは引数 → `JUI_PROJECT_DIR` env の順で解決。

### データ解決の4層フォールバック（SpecLoader.resolveFile）

`attribute_definitions.json` / `component_metadata.json` それぞれを:

1. `$JSONUI_CLI_PATH/shared/core/`
2. `./.jsonui-cli/shared/core/`（cwd）
3. `~/.jsonui-cli/shared/core/`
4. バンドル `data/`（最終フォールバック）

の順で解決。**ロードは起動時に1回だけ**で、以後プロセス寿命の間メモリキャッシュ。
→ **SSoT を更新しても MCP 再起動（= Claude Code 再起動）までツールに反映されない**。
`get_data_source` が layer/mtime/鮮度（fresh≤30d / aging≤90d / stale>90d)を返すので、
エージェントが古いデータで動いていないか確認できる（ただし boot 時点の情報）。

### data/ スナップショットの更新義務

`data/` は `scripts/fetch-definitions.js`（npm postinstall / `npm run fetch-definitions`）が
**jsonui-cli のリリースタグをピン参照**（`JSONUI_CLI_TAG` 定数、現 v1.1.0。2026-08-01 の P13 で
main 追従からタグピンに変更）して取得・更新する（JSON 検証あり、ネットワーク失敗は exit 0 で
旧スナップショット維持、IPv4 強制。取得対象 FILES には conformance の coverage.json も含む）。

**運用ルール: jsonui-cli の `shared/core/*.json` を変更して push したら、jsonui-cli のタグを
発行 → jsonui-mcp-server の `JSONUI_CLI_TAG` をバンプ → `npm run fetch-definitions` →
ピン更新と data/ diff を同一コミットで push**（別リポジトリなので自動では追従しない。09章）。
CI は `npm ci --ignore-scripts` で postinstall を止め、**コミット済み data/ を検証**する設計 —
スナップショット放置はテストで気づけない。

### インストール / 登録 / テスト

- `install.sh`: `~/.jsonui-mcp-server` に clone/update（`git reset --hard origin/main`）→
  `npm install`（postinstall fetch）→ `npm run build`（tsc → dist/）→ `~/.claude.json` の
  `mcpServers["jui-tools"]` に登録（旧 `jsonui-spec` エントリは削除）。
- テスト: `npm test`（vitest、`pool: "forks"` — process.chdir を使う cwd フォールバックテストのため。
  `tests/setup.ts` が HOME を temp に差し替えて実インストールの漏洩を防ぐ hermetic 設計）。

## 2. jsonui-helper（VSCode 拡張）

v0.1.x、`jui.config.json` を含むワークスペースで活性化。**CLI/MCP を一切呼ばない**独立実装:

- 5つの言語プロバイダ（Layout/Spec 補完、hover、⌘クリック定義ジャンプ、document link）+
  デバウンス診断（未知属性、enum 違反、未解決 include/view/style 参照、id 重複、
  hidden+visibility 矛盾、iOS 専用型に `platforms:["ios"]` なし等）+ スニペット 17 コマンド。
- データは `vendor/` に **git コミットされた vendored スナップショット**:
  attribute_definitions.json、spec スキーマ 2 種（Python `document_tools` から export）、
  builtin_type_map.json、responsive_size_classes.json、VERSION（jsonui-cli short SHA）。
- 更新は `npm run sync:specs`（`scripts/sync-specs.sh`、`$JSONUI_CLI` 既定 `~/resource/jsonui-cli`）。

### つまり SSoT の消費者は 3 系統

| 消費者 | 更新方法 | 反映タイミング |
|---|---|---|
| CLI ツール群 | symlink / sync_tool | 即時〜sync 時 |
| MCP サーバー | fetch-definitions + 再起動 | **再起動時** |
| VSCode 拡張 | sync:specs + 拡張リロード | 手動 sync 時 |

属性を追加して「エディタ補完に出ない」「MCP lookup に出ない」は、ほぼこの更新漏れが原因。
