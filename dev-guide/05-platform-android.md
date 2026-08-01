# 05. Android — KotlinJsonUI + kjui_tools

**KotlinJsonUI**（ランタイム、Gradle 4モジュール）+ **jsonui-cli/kjui_tools**（Ruby CLI `kjui`）。

> **XML (Android Views) モードは 2026-07-03 に正式凍結**。新機能は Compose のみ、
> XML は 3.0 削除候補、XML バグは won't-fix（ビルドを壊す場合を除く）。
> `lib/xml/` と `Kjui*` View ウィジェットには投資しない。

## 1. KotlinJsonUI モジュール構成

| モジュール | 役割 | 公開 |
|---|---|---|
| `:library` | コア。Compose composables + `core/`（DynamicModeManager, DynamicViewProvider=リフレクションブリッジ, ColorResolver, FontSpec）+ 凍結中の `views/Kjui*`（viewBinding/dataBinding はこのため残存） | `io.github.tai-kimura:kotlinjsonui` |
| `:library-dynamic` | 実行時 JSON→Compose インタープリタ。`DynamicView.kt`, `DataBindingContext`, `TypedAttrs.kt`, `components/Dynamic*Component.kt`（35個 = kjui emitter のランタイムミラー）, `hotloader/`。Compose-only | `io.github.tai-kimura:kotlinjsonui-dynamic` |
| `:sample-app` | dev/prod フレーバー付きサンプル。CI は `compileDevDebugKotlin` | — |
| `:conformance-host` | Compose **dynamic モード専用**の conformance 実行アプリ（UIAutomator、vendored driver） | — |

配線の要点:

- 生成される `<Screen>GeneratedView.kt` は `DynamicModeManager.isActive()` 分岐を持ち、
  active なら `SafeDynamicView(layoutName=…)`（:library → リフレクションで :library-dynamic へ）、
  でなければ静的 Compose ツリー。アプリは `implementation(core)` + `debugImplementation(dynamic)`。
- **`EmbedContainer` は :library 側**（全 GeneratedView が参照するため release でもコンパイル必須。
  `lifecycle-viewmodel-compose` が api 公開なのも同じ理由）。
- Dynamic v2 rewrite 計画（`Docs/dynamic-v2-rewrite-plan.md`）: Dynamic コンポーネントは
  kjui_tools の `modifier_builder.rb` / `resource_resolver.rb` / `*_component.rb` を
  source of truth として書き直し中。既知の未解決: `DynamicView.kt` の weight+gone ガード欠如、
  `VisibilityWrapper` に RowScope/ColumnScope オーバーロードがない（Box ラップで weight 消失）。

## 2. kjui_tools 構造と Compose パイプライン

```
kjui_tools/lib/
├── cli/                 init/setup/build/generate（view|partial|collection|binding|converter|adapter）
├── core/                config/validators/normalization/style_loader/…（attribute_definitions.json は symlink）
├── compose/
│   ├── compose_builder.rb        ★ 中央オーケストレータ（~1500行）— かつ自身が emit sink
│   ├── components/*.rb           28 emitters（+ extensions/ = カスタム部品プラグイン点）
│   ├── helpers/modifier_builder.rb   ★ 横断 modifier 工場（~1170行）。順序はここに符号化
│   ├── helpers/import_manager.rb     required_imports シンボル → import 行（import の唯一の sink）
│   ├── helpers/{resource_resolver,font_spec_helper,visibility_helper,responsive_helper,section_extractor}.rb
│   ├── generators/               view/cell/partial/converter/kotlin_component/dynamic_component/…
│   └── {style_loader,include_expander,data_model_updater,build_cache_manager}.rb
└── xml/                 凍結
```

リソース: `core/resources/string_manager.rb` が strings.json（SSoT）→
`res/values*/strings.xml` を update-or-add + **管理 prefix 内の stale prune**
（`<layout>_` prefix が strings.json に存在するキーのみ削除対象。
管理外の手書きキーは触らない — iOS の auto-generated セクションと同じ意味論。
2026-07-07 のバグ修正で prune 追加）。

ビルドフロー（`build.rb#build_compose` → ComposeBuilder）: キャッシュ判定（mtime + include/style
依存グラフ）→ リソース抽出 → `<Screen>Data.kt` 再生成 → validate（attribute/binding/
JsonUIShared::LayoutValidator）→ per-file: `$jui` 判定 → style merge → include 展開（ID prefix、
sjui 互換）→ scaffold（冪等）→ `generate_component` 再帰 emit →
`// >>> GENERATED_CODE_START/END` マーカー間に splice、ViewModel の `updateData(Map)` も
専用マーカー内を再生成、**import セクションは毎回全再構築**。

### emit sink の全リスト（「components/ だけ grep」は事故る）

kwargs や属性を通すときは **lib/compose/ 全体を grep** する。sink は:

1. `components/<x>_component.rb` — 大半のコンポーネント
2. **`compose_builder.rb` 内インライン** — `SafeAreaView`（`generate_safe_area_view*`、
   ConstraintLayout 切替含む）、`Spacer`、**responsive 全経路**
   （`generate_responsive_component` / `*_responsive_inline`）
3. `helpers/modifier_builder.rb` — padding/margin/size/weight/shadow/background/border/
   visibility/alpha/clickable/relative-positioning/testTag/lifecycle 等の横断属性
4. `helpers/resource_resolver.rb`（色・文字列）、`font_spec_helper.rb`（フォント）、
   `visibility_helper.rb`（visibility/gone 静的スキップ）
5. import が要るなら `import_manager.rb#get_imports_map` + emit 側 `required_imports&.add(:sym)`
   — 登録漏れは生成コードのコンパイルエラー

## 3. どこを直すか — 「コンポーネント X に属性追加」

1. SSoT `shared/core/attribute_definitions.json`（`platform`/`mode` タグ必須。漏れると
   kjui validator が Unknown attribute 警告）
2. kjui_tools の該当 emit sink（上記リストから特定）+ import 登録
3. bindable なら `data_model_updater.rb` / `compose_builder.rb` の `get_kotlin_cast` /
   `generate_update_data_function`
4. **KotlinJsonUI 側 Dynamic ミラー（必須）**: `library-dynamic/.../components/Dynamic<X>Component.kt`
   （+ `TypedAttrs.kt` 等）。落とすと静的では出るが dynamic/hot-reload で消え、conformance で落ちる
5. :library 本体は通常触らない（新しいランタイム composable が要るときだけ）
6. カスタムコンポーネントは `kjui g converter` が 5 sink（extensions の .rb / mappings /
   attribute_definitions / Kotlin 部品 / Dynamic 部品+registry）へ書く

## 4. ビルド・テスト・conformance・公開

- コンパイル（CI 同等）:
  `./gradlew :library:compileReleaseKotlin :library-dynamic:compileReleaseKotlin :sample-app:compileDevDebugKotlin --warning-mode all`
- ユニット: `./gradlew :library:testReleaseUnitTest :library-dynamic:testReleaseUnitTest`。
  **CI はゼロ警告ゲート**（`^w:` 再出現で fail）— 生成コード側も警告フリー前提
  （`@Suppress("UNCHECKED_CAST")` 等は意図的）。
- conformance（ローカル）: 検証専用 AVD（**日常用 Pixel_Tablet にテストを入れない**。
  専用 AVD port 5560 / 10G、macOS は timeout shim 必要）で
  `CONFORMANCE_DIR=... ./conformance-host/scripts/run_conformance.sh --fresh` → `collect_results.sh`。
  結果は `/sdcard/Android/data/com.kotlinjsonui.conformance/files/conformance/`
  （`progress.jsonl` によるクラッシュ/タイムアウト resume 付き）。ローカル 717 fixtures ≒ 4分、
  CI は 25-30分（×5-7倍で採寸する — 08章）。
- 公開: バージョンは **root `gradle.properties` の `version=` 一本**（現 2.17.2）。両モジュールが
  これを読むため **library と library-dynamic は構造的に同一バージョン公開**。
  Maven Central（vanniktech maven-publish、CENTRAL_PORTAL、automaticRelease）が正、
  jitpack.yml は best-effort。**publish 前にテストを回すこと**（過去の運用事故由来のルール）。
  - `library-dynamic` は **空 javadoc jar**（AGP/Dokka が Java17 sealed class を解析できない回避策）。
  - `library/build.gradle.kts` のコメントアウトされた旧 publishing{} は無視（正は mavenPublishing{}）。

## 5. 罠（Android 固有）

- **responsive はインライン emit が正**: ファイルスコープ helper へ抽出すると
  `data`/`viewModel`/scope が漏れ `Modifier.weight` が壊れる（過去バグ多数、
  compose_builder.rb に長文コメントあり）。`LocalWindowInfo`/`LocalDensity` を使う
  （`LocalConfiguration.screenWidthDp` は deprecated）。
- responsive な Embed/Collection は下端の `wrap_with_visibility` に到達する前に return する
  経路があるため**自己ラップ必須**。`Embed` はコンテナ skip-list から除外
  （EmbedComponent.generate は Hash でなく String を返す）。
- **JVM 64KB メソッド制限**: `SectionExtractor` が大きいコンテナ子を `SectionN` helper へ
  リフト（`RESPONSIVE_HELPERS` マーカー間）。
- import は毎ビルド全再構築 + blessed-names で刈られる。必要な import が消えるのは
  名前が blessed に入っていないから。
- `attribute_check.md` が正準/非正準の履歴表（`margin`→個別 margin、`color`→`fontColor`、
  `children`→`child`、`onValueChange`→`onTextChange`、`source|name`→`src`）。
- conformance driver は vendored + ローカルパッチ 1 件（`// KJUI-CONFORMANCE PATCH`、
  assertText retry）。`sync_driver.sh` で再同期時にパッチ消失に注意。
- `KotlinJsonUI/CLAUDE.md` は 2026-08-01（P9）に刷新済み。乖離を見つけたら README の乖離表の教訓どおり同時修正する。
