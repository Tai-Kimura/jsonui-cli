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
  - ~~`sjui_tools/VERSION` には絶対に CLI 版数を書かない~~ **（2026-09-03 訂正: そのファイルは
    存在しない）**。SwiftJsonUI のライブラリ版数は **消費側プロジェクトの `.sjui-version`**（無ければ
    installer が置く VERSION）を `library_setup.rb#get_current_version` が読む。**jsonui-cli の追跡ファイルは
    SwiftJsonUI / KotlinJsonUI の版を 1 箇所も pin していない**（現行版数で `git grep` して 0）⇒
    ライブラリ列車はツール側の commit を要しない。要るのは両ライブラリ repo の
    `JSONUI_CLI_MANIFEST_REF`（attr 表の再ベンダーと同じ commit）と、消費側の SPM / Gradle の pin（lib 取り込みレーン）。
  - **バンプ対象にもう 1 箇所**: `document_tools/pyproject.toml` の
    `jsonui-test-cli @ git+…@vX.Y.Z#subdirectory=test_tools`。同一リポの兄弟を
    直 git URL で入れているため、**rev を書かないとタグ指定でインストールしても
    兄弟だけ既定ブランチ**に解決される（= 消費側 CI のツール固定が宣言側で崩れる）。
    同じ `test_version_lockstep.py` が root との一致を強制する。
  - **タグ門**: `dev-guide/release/check-tag.sh <repo> <prev-tag> <tag> <branch> <version> <words,comma> <remote>`
    を **`git tag -a` の後・`git push` の前**に撃つ（5 検査がタグ object を要求するので
    「緑をもらってから打つ」は実行不能）。
  - **2 本目のタグ門**: `python3 dev-guide/release/check-tag-from-prev.py <repo> <prev-tag> <tag> [tested-sha]`
    を同じ窓（`git tag -a` の後・`git push --atomic` の前）で撃ち、**終了コードで読む**
    （後ろにパイプを付けない。`| tail` は tail の終了コードを返す）。期待値は前タグの木と
    first-parent 履歴・`git rev-list`・タグ名からだけ導く。⚠️ **独立なのはファイルの場所ではなく
    期待値の出所**なので、重複に見えても統合しない。以前の 2 本目（triage の verify_tag.sh）は
    repo に入ったことがなく、v1.8.94 を最後に消えた（v1.8.95〜v1.8.118 は check-tag.sh 1 本で打った。v1.8.119 は push 前にこの門でも 17/17）。
  - リリース手順: テスト green → commit → `git tag vX.Y.Z` →
    **`git push --atomic origin main vX.Y.Z`**（main とタグを 1 回で押す）→
    （shared/core を触っていれば）MCP snapshot 更新。
  - **main とタグを別々に push しない**。ピン導入後、release commit は
    「まだ存在しないタグ」を宣言している状態なので、その隙間に main HEAD から
    `pip install` した人は**インストールごと失敗する**（兄弟の checkout が落ち、
    `Failed to build 'jsonui-test-cli'`。実測 2026-08-20）。
    release commit の CI 自体は `--no-deps` なので取りに行かず影響を受けない。
  - **タグを打ったら、配布が終わるまで main に何も push しない**。
    `bootstrap.sh` は `origin/main` を取るので、タグの後に 1 コミットでも足すと
    `~/.jsonui-cli/SOURCE_SHA` と consumer の `sync-meta.json` が
    **タグから外れた SHA**になる（v1.6.13 で実際に踏み、consumer に指摘された）。
    内容が同一でも、4 点照合（VERSION / タグ / 報告書 / 現物）をする受け手が
    引っかかる。**リリースに付随する編集は release commit に入れてからタグを打つ**。
    後から気づいた分は、配布を終えてから次の commit に回す。
  - 🔑 **版番号を持つ文字列は 3 種類あり、バンプするのは 1 種類だけ**（2026-09-15、
    v1.8.81 の準備で消費側レーンが第三の種類を指摘して判明）。手で列挙せず
    **述語で導出する**（当夜、手で数えて 5 と答え、実際は 9 だった）:
    ```
    刻印   lockstep が強制する。バンプ対象。v1.8.80 時点で 9 行 / 8 ファイル
           述語: ^X.Y.Z$（root と rjui_tools の VERSION）/ VERSION = 'X.Y.Z'（Ruby 2 本）/
                 _FALLBACK_VERSION = "X.Y.Z"（Python 2 本）/ ^version = "X.Y.Z"（pyproject 2 本）/
                 jsonui-cli.git@vX.Y.Z#subdirectory=（兄弟 pin 1 本）
    機能行 書き換えると取得される木や挙動が変わる。バンプとは無関係
    散文   版番号を本文に運ぶが挙動を決めない。**バンプしない**。
           件数は書かない——刻印を上げると母集団が変わるので、書いた瞬間に古くなる
           （v1.8.81 の作業中に「17 行 / 12 ファイル」が実測 16 行 / 10 ファイルと
           食い違った）。数えるなら `git grep -c -F <旧版>` を撃ち、
           **刻印を上げた後に残る全件が散文であること**を目視する
           例: 生成表 description の "As of 1.8.80 the Compose emitter carries that floor"、
               installer/bootstrap.sh の配布本数の履歴行、kjui のコメント
    ```
    ⚠️ **散文を一括置換すると文が嘘になる**（「1.8.80 から床を持つ」は 1.8.81 でも真）。
    ⚠️ **判別子を 2 値（刻印 / 機能行）で持つと第三の種類が両方に見えない。** 消費側で
    生成表の集約ハッシュを腕にしている面があり、散文が動くと「機能行が動いた」と
    誤って鳴る。

    🔻 **ただし読み順は 3 段。「散文に閉じているか」で止めると判定できない。**
    散文と機能行は**同じファイルの同じ diff に同居する**（実測 v1.8.79→v1.8.80 の
    rjui 生成表 5 本: コメント 21 行 / コード 9 行。コードの中身は `glass` の
    `{ name: 'glass', kind: :raw }` 追加と `input` enum への 4 値追加）:
    ```
    集約が動いた → ① diff を読む
                 → ② 変化は散文（description / "As of X.Y.Z" 行）に閉じているか
                      閉じている   ⇒ 機能行 0。取り込んでよい
                      閉じていない ⇒ ③ 動いた機能行に、その面の layouts が到達するか
                                      到達 0   ⇒ 生成物は動かない
                                                 ⚠️ この 0 は「変わらなかった」ではなく
                                                    「入る入力を持っていない」
                                      到達あり ⇒ 生成物 diff を読んでから判断
    ```
    ③の判定式の例（web 面）: `grep -rhoE '"input"\s*:\s*"[^"]*"' <layouts> | sort | uniq -c`
    と `"glass"` の有無。v1.8.80 は全消費面が③の「到達 0」で通った。
    📌 この 3 段は消費側レーンの実測で確定した（当方は②で止めた版を一度書いている）。

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

### attr-codegen テーブルの再 vendor（SwiftJsonUI / KotlinJsonUI — B3 ガード付き）

swift / kotlin テーブルは手動 rsync だが、規律ではなく**ゲート**で守られている:
`jui generate attr-bindings --lang all` が `build/attr_codegen/manifest.json`
（ファイル毎 sha256 + attribute_definitions.json の source sha256。build/ 配下で
唯一のコミット対象）を発行し、ssot-guards が陳腐化で fail、両ライブラリ CI の
`vendored-attr-guard` ジョブがピン参照(`JSONUI_CLI_MANIFEST_REF`)の manifest と
vendored 実体を双方向照合する（hash 不一致・欠落・余剰いずれも fail。
`skipped_attributes.json` は emit メタデータで vendor 対象外）。

再 vendor の正式手順（順序厳守）:

1. `jui generate attr-bindings --lang all` — テーブルと manifest を同時再生成
2. jsonui-cli コミット: attr テーブル差分の原因(SSoT 変更等) + **manifest を同一コミット**に → push
3. rsync: `build/attr_codegen/swift/*.swift` → SwiftJsonUI
   `Sources/SwiftJsonUI/Classes/SwiftUI/Dynamic/Generated/Attributes/`、
   `build/attr_codegen/kotlin/*.kt` → KotlinJsonUI
   `library-dynamic/src/main/kotlin/com/kotlinjsonui/dynamic/generated/`
4. **両ライブラリをビルド**（テーブルからフィールドが消える変更は本体コードの追随が要る —
   sjui は xcodebuild + iOS Simulator、kjui は `:library-dynamic:compileReleaseKotlin`）
5. 各ライブラリのコミットで **再 vendor と `JSONUI_CLI_MANIFEST_REF` バンプを同一コミット**に
   （2. の push 済み SHA、次回リリース以降はタグを推奨 — manifest は `2299153` 以降にのみ存在）
6. CI 3 本 green を確認（jsonui-cli ssot-guards / 両ライブラリ vendored-attr-guard）

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
