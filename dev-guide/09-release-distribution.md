# 09. リリースと配布

## 1. 配布モデルの全体像

```
GitHub (Tai-Kimura/jsonui-cli)
  └─ installer/bootstrap.sh (curl | bash)
       → ~/.jsonui-cli/            ← MCP・プラットフォームツールが探す既定地
           ├── symlink → 実コピー化（attribute_definitions.json を各ツール lib/core/ へコピー）
           ├── pip install -e（jui / jsonui-doc / jsonui-test、無条件再インストール）
           │    ※ test_tools は self-contained（validation/＋schema.py 同梱）。copy_shared_modules
           │      には渡さない。document_tools は validator/schema 定数を jsonui_test_cli から import
           └── (任意) jsonui-mcp-server installer 委譲 → ~/.jsonui-mcp-server + ~/.claude.json 登録
  └─ jui sync_tool
       → 各コンシューマプロジェクトの <platform_root>/<tool>_tools/ ミラー
         （extensions/ 保護、.ruby-version 伝播、SHARED_CORE_PAYLOADS 配布）
```

### 開発版の伝播ルート（ローカル運用）

dev checkout（`~/resource/jsonui-cli`）→ `~/.jsonui-cli/` → 各コンシューマプロジェクトへ
`jui sync_tool`。**コミット/push してよいのはツール系リポジトリのみ**。コンシューマプロジェクトへは
push せず、rsync/sync_tool による同期のみ。
公開リポジトリのコミットに**コンシューマ固有の名前・パス・型名を絶対に入れない**
（docs/ が gitignore なのはこのため）。

## 2. リポジトリ別リリース手順

### jsonui-cli
- **タグ運用（2026-08-01 開始、初版 v1.1.0）**: リポ直下 `VERSION` が版数の単一正本。
  main が配布元である点は不変（bootstrap は `git reset --hard origin/main`）で、
  タグは「consumer に配った生成コードの再現座標」。
  - 派生関係: `jui --version` / `setup.py` は実行時に root `VERSION` を読む。
    `{s,k}jui_tools/lib/cli/version.rb` の定数と `rjui_tools/VERSION` は
    consumer コピー単体動作のためのリテラル複製で、
    `jui_tools/tests/test_version_lockstep.py` が root との一致を強制
    （バンプは root + Ruby 側 3 箇所を同時更新。漏れると python-suite が落ちる）。
  - **`sjui_tools/VERSION` には絶対に CLI 版数を書かない** — そこは
    SwiftJsonUI **ライブラリ**版数のスロット（`library_setup.rb` が読む）。
  - リリース手順: テスト green → commit → push → `git tag vX.Y.Z` →
    `git push origin vX.Y.Z` →（shared/core を触っていれば）MCP snapshot 更新。
- **ソース SHA の刻印（ツールチェーン座標）**:
  - `installer/bootstrap.sh` が clone/update 直後・`.git` 削除前に `SOURCE_SHA` を
    書く（インストール先は git リポではないため）。
  - **dev rsync 経路は手動刻印**: `~/.jsonui-cli/` へ rsync した後に
    `git -C <dev-checkout> rev-parse HEAD > ~/.jsonui-cli/SOURCE_SHA`
    （`VERSION` は rsync がミラーするので version 側は自動）。
  - `jui sync_tool` は source の version+SHA を consumer の
    `.jsonui-cli/sync-meta.json` にプラットフォーム別で刻印する。
    consumer からのバグ報告にはこのファイルの引用を求める。
- push 前チェック: `python -m unittest`（jui_tools）、`bundle exec rspec`（3 Ruby ツール）、
  ssot-guards 相当（attr-bindings 決定論 + conformance generate diff ゼロ + rjui vendored diff）。
- **shared/core/*.json を変更した push には必ず後続タスク**:
  ① jsonui-cli のタグを発行（`git tag vX.Y.Z` + push）— **P13 以降、MCP の
     fetch-definitions はタグピン参照**（`scripts/fetch-definitions.js` の
     `JSONUI_CLI_TAG`）。タグを進めるまで snapshot は意図的に固定される
  ② jsonui-mcp-server の `JSONUI_CLI_TAG` を新タグへ更新 →
     `npm run fetch-definitions` → data/ diff とピン更新を**同一コミット**で push（07章）
  ③ 使用中のライブ MCP は再起動しないと新属性が出ない
  ④（時間があれば）jsonui-helper `npm run sync:specs`

### SwiftJsonUI
- version は `VERSION` のみ（`SwiftJsonUI.podspec` は P7 で削除 — SPM-only）。
- commit → push → `git tag -f <version>` → `git push origin <version> --force`（tag 移動流儀）。
- 配布は SPM（tag 参照）のみ。
- attr-codegen の Swift 出力（Dynamic/Generated/Attributes/）は**コミットに含める**
  （cli checkout なしでビルド可能に保つ）。
- リリース前にテスト: xcodebuild + iOS Simulator（swift build 不可 — 04章）。

### KotlinJsonUI
- バージョンは root `gradle.properties` の `version=` **一本**。
  → `:library` と `:library-dynamic` は**構造的に同一バージョン**で publish される。
- **publish 前にテスト必須**: `:library:testReleaseUnitTest :library-dynamic:testReleaseUnitTest`
  + ゼロ警告コンパイル。
- 正: Maven Central（vanniktech maven-publish / CENTRAL_PORTAL / automaticRelease / PGP in-memory）。
  jitpack.yml は best-effort の publishToMavenLocal。
- 罠: library-dynamic の空 javadoc jar は仕様（Dokka × Java17 sealed class 回避）。
  旧 publishing{} ブロック（コメントアウト）は復活させない。

### ReactJsonUI / rjui_tools
- npm 公開物なし。rjui_tools の VERSION 更新 + jsonui-cli main への push が実質のリリース。

### jsonui-mcp-server
- `install.sh` 再実行が更新手段（reset --hard → npm install → build → 登録）。
- リリース前: `npm test`（hermetic vitest）+ `npm run build`。
- data/ スナップショットのコミットを忘れない（CI は committed data/ を検証する設計）。
- スナップショットの取得元は **jsonui-cli のタグピン**（`scripts/fetch-definitions.js`
  の `JSONUI_CLI_TAG`、P13）。バンプはピン更新 + data/ diff を同一コミットで。

### jsonui-test-runner（+ ドライバ 3 リポジトリ）
- **`jsonui-test` CLI は jsonui-cli へ移設済み**。test-runner が正本として持つのは
  トップレベル `schemas/`（5 種 + `mock.schema.json`）・`drivers/`・`examples/` のみ。
- ドライバは各自リポジトリ（-web / -android / -ios）でコミットし、親リポジトリで
  submodule ポインタ更新。conformance ホストの vendored driver 再同期も追随
  （kjui のローカルパッチ保持に注意）。

### スキーマ ↔ validator の正本分担（クロスリポ・重要）

| 資産 | 正本 | ミラー相手 | 保証 |
|---|---|---|---|
| テストスキーマ（screen-test / actions / flow-test / results / description） | **jsonui-test-runner** `schemas/` | — | JSON Schema（実行時は誰も読まない） |
| `mock.schema.json`（エディタ/doc 専用） | **jsonui-test-runner** `schemas/`（D5 で他エディタスキーマと集約） | actions.schema.json の `setMocks`/`mocksScenarioMap` | 実行時無依存 |
| validator 定数（`schema.py` SUPPORTED_ACTIONS/ASSERTIONS/VALID_*） | **jsonui-cli** `test_tools/jsonui_test_cli/schema.py` | actions/screen-test/flow-test/description schema | `test_schema_drift.py`（vendored fixtures と一致を CI で強制） |
| results 契約（`report.py` VALID_RESULT_*） | **jsonui-cli** `test_tools/jsonui_test_cli/report.py` | `results.schema.json` **＋ 3 ドライバの `ResultsWriter`**（test-runner） | `test_schema_drift.py` が report.py ⇄ results.schema.json を CI で照合（2/3 点）。ドライバ側の逸脱は report 実行時の VALID_RESULT_* 検証で捕捉（3 点目のランタイムガード） |

- **drift-check の運用**: 正準スキーマは `test_tools/tests/schema_fixtures/` に **test 専用 fixture として vendor**（パッケージ非同梱＝実行時無依存を維持）。
  test-runner 側でスキーマを変えたら `schema_fixtures/VENDOR.md` の手順で再 vendor し、`test_schema_drift.py` を通す（通らなければ実 drift）。

### jsonui-helper
- `npm run sync:specs` → vendor/VERSION（cli SHA）更新 → `vsce package`（.vsix）。

## 3. 「出力が変わる」変更のリリースゲート

codegen / normalizer / SSoT に触れて生成物が変わり得る変更は、公開前に:

1. conformance suite before/after 一致（または意図した差分だけであることを REPORT で確認）。
   合否判定は CI と同一コマンドがローカルで実行可能:
   `jui conformance gate --platform ios --platform android --platform web`
   （ratchet 台帳は `conformance/gate_ratchet.json`。ceiling の引き下げは奨励、
   引き上げは同ファイルへの正当化コメント必須）
2. `jui build` 冪等性（2回実行 diff ゼロ）
3. **実コンシューマプロジェクトの worktree 上で新ツールを適用してビルドし、
   生成物が旧ツールとバイト一致**（意図した差分のみ）— ライブ checkout と `~/.jsonui-cli/` には触れない
   （renderer-ssot-10-final-verification.md のプロトコル）
4. デフォルト挙動を変える場合は opt-in flag から始める

## 4. 破壊的変更の連絡先（追従が必要な下流）

| 変更 | 追従が必要なもの |
|---|---|
| jui コマンド/挙動変更 | JsonUI-Agents-for-claude のエージェント md・jsonui-rules、MCP ツール定義（zod スキーマ）、jui_tools_README.md |
| spec スキーマ変更 | document_tools スキーマ → jsonui-helper vendor（sync:specs で export される） |
| テストアクション追加 | 08章 §6 の 5 レイヤー |
| wire protocol（hotload）変更 | SwiftJsonUI HotLoader / KotlinJsonUI hotloader / rjui hotload コマンドの 3 クライアント |
