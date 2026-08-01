# 02. SSoT — shared/core と正規化・型付き属性

## 1. shared/core/ の中身

| ファイル | 役割 | 消費者 |
|---|---|---|
| `attribute_definitions.json`（約120KB / ~4,500行 / top-level 31キー: `_comment` + `common`(~148属性) + 29コンポーネント） | **属性 SSoT**。各属性: `type`（文字列 or 配列、inline `{"enum":[...]}` や `"binding"` を含み得る）、`enum`、`aliases`（宣言キーが正準）、`deprecated`/`deprecation_note`、`required`、`default`、`binding_direction`、`platform`（swift/kotlin/react）、`mode` | Ruby 3ツールの validator（symlink）、attr-codegen、conformance 生成、MCP、jsonui-helper |
| `component_metadata.json`（~22KB / 30キー） | コンポーネントの説明・エイリアス・プラットフォーム可用性（swift_generated/swift_dynamic/kotlin_generated/kotlin_dynamic/react）・エージェント向け rules | MCP `lookup_component` 等。codegen は読まない |
| `font_weight_mapping.json` | weight 名 → swift/kotlin/css enum 対応表 | 各ツールの font_spec_helper（3箇所探索: ツール内コピー → repo ルート → `~/.jsonui-cli`） |
| `layout_validator.rb` / `responsive_resolver.rb`（`module JsonUIShared`） | Layout 整合性チェック / responsive 解決の共通 Ruby 実装 | s/k/rjui に**コピー**（symlink ではない）され同一警告・同一解決を保証 |
| `../schema.py`, `../validation/*.py` | テスト JSON 検証の Python 共通実装 | install 時に test_tools / document_tools へコピー |

### 消費形態マトリクス（ここを間違えると「直したのに反映されない」）

| 消費者 | 形態 | 更新の反映条件 |
|---|---|---|
| sjui/kjui/rjui validator | dev checkout では **symlink**（`<tool>/lib/core/attribute_definitions.json`） | 即時。ただし**インストール済みツリー（~/.jsonui-cli）は bootstrap が実コピーに置換**するため再インストール/再同期が必要 |
| rjui typed tables | **vendored**（`rjui_tools/lib/core/generated/attributes/*.rb`） | `jui g attr-bindings --lang ruby` で再 emit して**コミット**。CI `ssot-guards` が fresh emit と diff 照合 |
| SwiftJsonUI typed structs | rsync 取込み（`scripts/sync_generated_attributes.sh`）→ **SwiftJsonUI リポジトリにコミット** | 手動実行。ライブラリ単体でビルド可能にするため必ずコミットする |
| KotlinJsonUI dynamic | attr-codegen kotlin 出力を library-dynamic に取込み | プラットフォーム適用フェーズ（plans 07/08）の手順に従う |
| jsonui-mcp-server | 4層フォールバック + **起動時1回ロードのメモリキャッシュ** | `data/` スナップショット更新 + **サーバー再起動**（07章） |
| jsonui-helper | `vendor/` に手動 vendor（`npm run sync:specs`、VERSION に cli の short SHA を記録） | 手動 sync + 拡張リロード |
| プロジェクトローカルツールコピー | `jui sync_tool` が `SHARED_CORE_PAYLOADS`（font_weight_mapping.json）を `<tool>/shared/core/` に配布 | sync_tool 実行。**配布漏れだと sjui は全 weight を .regular に黙って丸める既知バグ** |

## 2. 正規化レベル L0 / L1 / L2（全ツール共通用語）

実装: `jui_tools/jui_cli/core/normalizer/`（`alias_table.py` / `canonicalizer.py` /
`style_merger.py` / `include_expander.py` / `platform_filter.py`、公開 API は `normalize()`）。
元は hotloader（`jui_cli/hotloader/`）の実装を core へ昇格したもの。

| レベル | 内容 | 消費者 |
|---|---|---|
| L0 (raw) | 作者が書いたまま | 共有 layouts_directory は**常に L0 のまま**（書き換えない） |
| L1 (canonical) | エイリアス→正準名書き換え + deprecated 警告 + `"$jui": {"normalized":"L1","schemaVersion":1}` マーカー。style/include は解決**しない**（include はコンポーネント再利用構造として codegen に必要） | 配布された各プラットフォーム Layouts/（codegen が読む） |
| L2 (resolved) | L1 + style merge + include 展開 + platform filter | dynamic モードランタイム / hotloader |

重要な実装知識:

- **`normalizeLayouts` はデフォルト TRUE**（SSoT phase 14 以降、`build_cmd.py:165-178`）。
  レガシーとバイト一致させたい場合は `jui.config.json` の `"build":{"normalizeLayouts":false}`。
- `AliasTable.is_empty()` ガード: 定義ファイルが見つからないのに `$jui` マーカーだけ付けると
  canonical-only 消費者を壊すため、その場合は **L0 のまま配布**する（`build_cmd.py:205-218`）。
- `jui verify` は両辺（spec 由来の期待と実 Layout）に同じ normalizer を適用する。
  片側だけだとエイリアス書き換えが偽 drift として出る。
- 各 Ruby ツールは `Core::Normalization.canonicalized?` で L1 を検出し、
  **canonical-only 属性ルックアップ**に切り替える（L0 なら alias-tolerant）。残存エイリアスは
  unknown-attribute 警告になる（仕様どおり）。
- `alias_table.py` の `_TYPE_SYNONYMS`（`Text→Label`, `HStack→View` 等）は Ruby 側の
  `map_type_to_definition` テーブルと**手動で同期**が必要。

## 3. 型付き属性コード生成（attr-codegen、SSoT 柱C）

実装: `jui_tools/jui_cli/generators/attr_codegen/`（`model.py` + `{swift,kotlin,ruby}_emitter.py`）。
契約書: 同ディレクトリの `README.md`。コマンド: `jui generate attr-bindings --lang swift|kotlin|ruby|all`。

- `load_model()` が定義をロードし `AttrKind`（STRING/COLOR/NUMBER/BOOLEAN/OBJECT/ARRAY/ANY/RAW/
  ENUM/DIMENSION/BINDING）に分類。`callback` 型と `$` 接頭辞などメタ属性は
  `skipped_attributes.json` へスキップ記録（黙って落とさない）。
- 出力: `AttrCodegenSupport.*` + `CommonAttributes.*` +
  `<Component>Attributes.*`（コンポーネント差分）。共通属性は 1 回だけ emit。エイリアス解決と lenient enum は生成コードに焼き込み。
- **決定論が CI ゲート**: ソート済み・タイムスタンプなし。2回 emit してバイト一致すること。
  golden files: `jui_tools/tests/golden/attr_codegen/`。
- enum の case 名は `dedupe_case_names` が大文字小文字衝突（`Left`/`left` 等）に `_2` を付ける
  （macOS APFS の case-insensitive 対策。fixture 生成の `_unique_stem` も同様）。

### 消費側の読み方（Swift の例）

Dynamic converters は `component.typedAttributes(ButtonAttributes.self)` で読む。
生の辞書読み（`rawData[`）は `SwiftJsonUI/scripts/check_converter_raw_reads.sh` が禁止しており、
`component.rawAttribute("key")` はレガシー許可リスト（`parent_orientation`, `action`, `colors`,
`gradient` 等）のみ。**宣言済み属性は必ず typed で読む**。

## 4. SSoT を変更したときの派生物更新チェックリスト

`shared/core/attribute_definitions.json` を触ったら以下が芋づるで動く/要更新（詳細手順は 10 章）:

1. Ruby validator: symlink なので dev checkout は即反映（何もしない）
2. `jui g attr-bindings --lang all` → ruby は vendored テーブル再コミット、swift は
   SwiftJsonUI へ rsync + コミット、kotlin は KotlinJsonUI へ取込み
3. `jui conformance generate` → fixtures/manifest 再生成（diff は生成差分のみのはず）
4. 分類が要る属性は `jui_cli/conformance/rules.py` / `interactive_rules.py`（機械部分の
   `fixture_generator.py` は触らない）
5. `component_metadata.json`（エージェント向け説明が要るなら）
6. **jsonui-mcp-server の `data/` スナップショット更新 + push、ライブサーバー再起動**
7. jsonui-helper の `npm run sync:specs`（急ぎでなければ次回まとめてでよい）
8. `jui_tools/tests/golden/` の更新、`python -m unittest discover -s tests`

## 5. Renderer SSoT 化の現在地

マスタープラン: `docs/plans/2026-07-02-renderer-ssot-00-overview.md`（3本柱:
A=conformance / B=normalizer / C=attr-codegen）。フェーズ 14（enablement）まで進み、
normalizer はデフォルト有効、conformance は CI 常設（web は per-push、mobile は週次）。
新しい修正はこの枠組みを前提にする — 例えば「エイリアス追加」は emitter の分岐追加ではなく
`aliases` 配列 + normalizer の仕事、が正解になっている。
