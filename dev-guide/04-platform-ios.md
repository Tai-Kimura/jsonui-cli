# 04. iOS — SwiftJsonUI + sjui_tools

2つのリポジトリで1プラットフォーム:
**SwiftJsonUI**（ランタイム、アプリが依存）と **jsonui-cli/sjui_tools**（Ruby CLI `sjui`、codegen）。
sjui_tools は他ツール改修時の**リファレンス実装**（rjui の CLAUDE.md が「必ず sjui を先に見ろ」と明記）。

## 1. SwiftJsonUI ライブラリ構造

```
Sources/SwiftJsonUI/Classes/
├── UIKit/            レガシー実行時解釈パス
│   ├── UI/SJUIViewCreator.swift   createView() が再帰インタープリタ（type の巨大 switch）
│   ├── UI/UIView/SJUI*.swift      SJUIButton / SJUILabel / SJUICollectionView 等
│   ├── Binding.swift              ViewHolder ベースのバインディング
│   └── SJUIViewController.swift
├── SwiftUI/
│   ├── Components/                codegen が参照する共有プリミティブ（StateAwareButtonView 等）
│   ├── （ルート直下）              NetworkImage, SelectBoxView, CollectionStackView,
│   │                              KeyboardAvoidance/, Embed/EmbedContainer, Configuration/ 等
│   └── Dynamic/                   ★ DEBUG 限定の実行時解釈（SwiftUI 版）
│       ├── DynamicView.swift              エントリ（jsonName / component）
│       ├── DynamicComponentBuilder.swift  type.lowercased() の switch → 各 Converter
│       ├── Converters/*.swift             29 converters（codegen .rb とペア）
│       ├── Containers/
│       ├── TypedAttributes.swift ほかヘルパ
│       └── Generated/Attributes/*.swift   ★ @generated。手編集禁止（attr-codegen 出力）
└── HotLoader/        WebSocket wire protocol v2 クライアント（#if DEBUG）
```

- Dynamic モードは **DEBUG 限定**（`#if DEBUG`）。本番は生成済み compiled views。
- Package.swift: **iOS 17 / swift-tools 5.10**。配布は SPM のみ
  （podspec は 2026-08-01 の P7 で削除 — CocoaPods 撤退。09章）。

## 2. sjui_tools 構造

```
sjui_tools/
├── bin/sjui → lib/cli/main.rb    コマンド: init/setup/generate/destroy/build/convert/watch/validate/version
├── lib/core/                      config/finder/validators/normalization/type_converter/
│                                  pbxproj_manager/xcode_project_manager/…
│                                  attribute_definitions.json は shared/core への symlink
├── lib/swiftui/                   ★ SwiftUI codegen
│   ├── json_to_swiftui_converter.rb   オーケストレータ（read→style merge→validate→include展開→emit）
│   ├── converter_factory.rb           type→Converter クラス対応（extensions を先に見る）
│   ├── views/*_converter.rb           コンポーネント別 emitter（base_view_converter.rb が基底）
│   ├── views/extensions/              カスタムコンバータ・attribute_definitions 上書き点
│   ├── binding/handlers/*.rb          @{...} → SwiftUI modifier 変換
│   └── generators/                    view/partial/collection/converter/adapter scaffolds
└── lib/uikit/                     UIKit codegen（binding handlers + xcode_project 操作）
```

- `base_view_converter.rb` の **ModifierBag** が modifier 順序を強制:
  center/edge alignment → padding → frame constraints → frame size → insets → background →
  accessibilityIdentifier。**Swift 側 Dynamic converter はこの順序を手で鏡写しにしている**
  （各 .rb のヘッダコメントに対応する Swift ファイル名と順序が書いてある）。
- L0/L1: `Normalization.canonicalized?` → `layout_normalized` → canonical-only。
  L0 では `attr_with_alias(canonical, *aliases)` で許容。

## 3. どこを直すか — 「Button に属性を1つ追加」の全経路

1. **SSoT**: `shared/core/attribute_definitions.json` の `Button` に追加（symlink で sjui validator に即反映）
2. **型付き struct 再生成**: `jui g attr-bindings --lang swift` →
   `SwiftJsonUI/scripts/sync_generated_attributes.sh`（要 `JSONUI_CLI_PATH`）で
   `Dynamic/Generated/Attributes/ButtonAttributes.swift` を更新し**コミット**
   （ライブラリは cli checkout なしでビルドできる必要がある）
3. **codegen 側**: `sjui_tools/lib/swiftui/views/button_converter.rb`
   （binding 駆動なら `binding/handlers/button_binding_handler.rb` も）
4. **Dynamic 側（#3 と厳密ミラー）**: `Classes/SwiftUI/Dynamic/Converters/ButtonConverter.swift`。
   `component.typedAttributes(ButtonAttributes.self)` で読む。`rawData[` は
   `scripts/check_converter_raw_reads.sh` に弾かれる
5. **プリミティブ**（描画挙動が新規なら）: `Components/StateAwareButtonView.swift`
6. **UIKit**（必要な場合のみ）: `SJUIViewCreator.swift` + `SJUIButton.swift` +
   `sjui_tools/lib/uikit/handlers/button_binding_handler.rb`
7. `SwiftUI_Unimplemented_Attributes_Checklist.md` から消し込み
8. conformance fixture 再生成 + iOS 実行（08章）

## 4. ビルド・テスト

- **`swift build` は macOS で失敗する**（56ファイルが `import UIKit` をガードなしで持つ）。
  必ず xcodebuild + iOS Simulator。シミュレータ名は **xcodebuild の eligible リスト**に合わせる
  （simctl のリストとは一致しないことがある）。
- カバレッジ: `scripts/test-coverage.sh`（SCHEME=SwiftJsonUI、destination は iPhone シリーズ）。
  現状 ~3.4%、目標 80%（README_COVERAGE.md）。
- **test_app/**: リポジトリ内の swiftui-mode サンプル（`sjui.config.json`, hotloader 127.0.0.1:8081）。
  コンバータ変更の検証ループ: test app 側の `sjui_tools/` で修正 → `./sjui_tools/bin/sjui build` →
  本体へ適用。
- **ConformanceHost/**: Dynamic モードで conformance fixtures を回す XCUITest ホスト。
  Xcode プロジェクトは `scripts/generate_project.rb` で**生成**（gitignore）。
  `sync_fixtures.sh`（要 CONFORMANCE_DIR / JSONUI_TEST_RUNNER_PATH）→ generate_project →
  `run_conformance.sh`（既定 SIMULATOR_NAME="iPhone 16 Pro"、ステータスバー時計を 9:41 固定で
  dHash ノイズ除去、40 fixtures/launch のバッチ、Darwin 通知で advance）→ `collect_results.sh`。

## 5. バージョン・リリース

- 版数は `VERSION` 一本（現 10.12.0。podspec は P7 で削除済み — SPM-only）。
- 手順: commit → push → `git tag -f <version>` → `git push origin <version> --force`
  （タグは動かして上書きする流儀）。SPM、tag = version。
- sjui_tools は独立バージョン（`lib/cli/version.rb`）。

## 6. 罠（iOS 固有）

- **`Dynamic/Generated/Attributes/` と `*View.swift`（GeneratedView）と Data モデルは手編集禁止**。
- codegen .rb と Dynamic .swift の**乖離は conformance が検出**する — 片方だけの修正は必ず落ちる。
- エイリアス例: `EditText`/`Input`→`TextField`, `Toggle`→`Switch`, `Check`→`CheckBox`,
  `alpha`→`opacity`。emitter に分岐を書かず SSoT の aliases + normalizer に任せる。
- Collection: SwiftUI モードで `items` binding があり `sections` がないと警告。
  `include` に `id` がないと data プロパティ名衝突の警告。
- hotload サーバーは jui に移管済み（`jui hotload listen`）。`sjui watch` はレガシー。
- 属性ドキュメントの正は SwiftJsonUI / KotlinJsonUI の GitHub wiki（メンテナはローカルに
  wiki クローンを持つ運用）。推測で属性名を書かない。
