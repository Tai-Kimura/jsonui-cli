# 10. メンテナンス・プレイブック集

実作業の手順書。各手順の背景は該当章を参照。

---

## プレイブック1: 既存コンポーネントに属性を追加する（全プラットフォーム）

最頻出の作業。**順序が重要**（SSoT → 生成 → emitter → Dynamic → 検証）。

1. **SSoT 定義**: `shared/core/attribute_definitions.json` の対象コンポーネント（横断なら `common`）に
   追加。`type` / `enum` / `aliases` / `description` / `binding_direction` / `platform` タグ /
   `mode` を正しく。エージェント向け説明が要るなら `component_metadata.json` も。
2. **型付き属性再生成**: `jui g attr-bindings --lang all`
   - ruby → `rjui_tools/lib/core/generated/attributes/` へ vendored 反映（コミット。CI が diff 照合）
   - swift → `SwiftJsonUI/scripts/sync_generated_attributes.sh` → コミット
   - kotlin → KotlinJsonUI へ取込み
3. **emitter 実装（プラットフォームごと、sjui を先に見る）**:
   - iOS: `sjui_tools/lib/swiftui/views/<x>_converter.rb`（+ binding handler）
   - Android: **emit sink を特定してから**（05章 §2 — components/ だけとは限らない。
     modifier 系は modifier_builder.rb、SafeAreaView/Spacer/responsive は compose_builder.rb 内。
     `grep -r <属性名> kjui_tools/lib/compose/` で全 sink 確認）+ import_manager 登録
   - Web: `tailwind_mapper.rb` の map_* + base_converter or 該当 converter
4. **Dynamic ミラー（iOS/Android 必須）**:
   - iOS: `SwiftJsonUI/.../Dynamic/Converters/<X>Converter.swift`（typedAttributes で読む。
     modifier 順序を .rb と一致させる）
   - Android: `KotlinJsonUI/library-dynamic/.../Dynamic<X>Component.kt`
5. **conformance**: `jui conformance generate`（分類調整は rules.py / interactive_rules.py）→
   web はローカルで `hosts/web` 実行、mobile は専用 AVD / シミュレータで実測 → visual なら
   baseline 更新。
6. **テスト**: 各ツールの RSpec / unittest / Gradle test / xcodebuild test。golden 更新。
7. **下流更新**: MCP data/ スナップショット + push + 再起動、jsonui-helper sync:specs、
   `SwiftUI_Unimplemented_Attributes_Checklist.md` 消し込み。

チェック: `jui build` 冪等 / ゼロ警告（kjui は CI ゲート）/ conformance ゲート green。

---

## プレイブック2: 新コンポーネントタイプを追加する

プレイブック1 に加えて:

- SSoT に新セクション + `component_metadata.json` にエントリ
- `conformance/rules.py` に BASE_ATTRS / BASE_CHILDREN / host エントリ
- タイプ別 dispatch への登録:
  - iOS codegen: `converter_factory.rb` / Dynamic: `DynamicComponentBuilder.swift` の switch
  - Android codegen: ComposeBuilder の dispatch / Dynamic: DynamicRenderer 側 registry
  - Web: **`react_generator.rb` の CONVERTERS と `base_converter.rb#get_converter_class` の両方**
- タイプシノニム（`Text→Label` 等）を足すなら `alias_table.py` の `_TYPE_SYNONYMS` と
  Ruby 側 `map_type_to_definition` を両方
- ランタイム部品が要るなら: iOS Components/、Android :library、Web templates/ +
  ensure_builtin_components

プロジェクト固有部品ならコア変更不要 — 各ツールの `g converter`（extensions/ 機構）で完結。

---

## プレイブック3: テストアクション/アサーション追加

08章 §6 参照。schema.json → schema.py → 3ドライバ（それぞれ別リポジトリでコミット +
submodule ポインタ）→ docs → conformance ホストの vendored driver 再同期。

---

## プレイブック4: spec / codegen の機能追加（dataFlow・swagger 系）

1. 仕様は先に `docs/jui_tools_README.md` に書けるか確認（書けない仕様は作らない — spec-first）
2. 実装: `jui_cli/core/`（spec 抽出・protocol_sync・api_model_sync）+ generators/
3. **冪等性テスト必須**: 2回 build で diff ゼロ、atomic write、`@generated` マーカー
4. validator（document_tools の SpecValidator）とエラーメッセージ更新
5. **swagger/DTO 系は必ず**: DTO=`@generated` 毎回再生成 / Domain=初回のみ、の所有権を壊さない。
   halt 不変条件を変えたら `jui ls api-specs` の事前検出と agents 文書も更新
6. JsonUI-Agents-for-claude のエージェント/ルール md、MCP ツール（必要なら zod スキーマ）、
   jsonui-helper のスキーマ export を追従

---

## プレイブック5: バグレポート処理（定常運用）

受付箱: `docs/bugs/`（README 以外のファイルが未処理レポート）。セッション開始時や
「レポート上がってる」の一言で `ls docs/bugs/` を最初に確認する運用。

1. **分類**: ツールバグ / ライブラリバグ / コンシューマ側の誤用・spec 逸脱 / 仕様どおり
2. **「昔は動いてた」系は baseline 検証を先に**:
   - リグレッション前バージョンのツールで emit して現行と diff
   - コンシューマ側 git 履歴（カスタム Swift/JSON の変更）も疑う
   - **正準セマンティクスがコンシューマの期待に優先**（ライブラリを安易に曲げない）
3. spec-first でトレース（症状 → Layout → spec → generator の順に絞る。
   3 ゲート = verify / build / validate_spec を診断に使う）
4. 修正計画 → 実装 → プレイブック1 の検証セット
5. **統合レポートを `docs/bugs/reports/YYYY-MM-DD-<slug>.md` に書き、処理済みソースファイルは削除**

---

## プレイブック6: normalizer / 配布まわりを触る

- L1 の意味論を変える変更は全消費者（sjui/kjui/rjui の canonical-only パス、
  SwiftJsonUI `JsonUINormalization.swift`、KotlinJsonUI `Normalization.kt`、
  jsonui-helper の whitelist）に波及する。`$jui` marker の schemaVersion を上げる判断を先に。
- `normalize(normalize(x)) == normalize(x)` を壊さない。
- 共有 layouts_directory は書き換えない（L0 のまま）。配布コピーだけが L1。
- 出力が変わるなら 09章 §3 のゲート（実コンシューマ worktree バイト一致）を必ず通す。

---

## 横断的な落とし穴 早見表

| 症状 | 原因の定番 |
|---|---|
| 直したのに挙動が変わらない | pip editable が別 checkout を指している / プロジェクトローカルツールコピーが古い（sync_tool 忘れ）/ MCP 再起動忘れ |
| MCP/補完に新属性が出ない | jsonui-cli タグ未発行 or `JSONUI_CLI_TAG` 未バンプ（data/ 未更新）or サーバー再起動忘れ / helper の sync:specs 忘れ |
| kjui で属性が一部レイアウトだけ効かない | emit sink 漏れ（responsive インライン / SafeAreaView / modifier_builder のどれか） |
| 生成 Kotlin がコンパイルエラー | import_manager 登録漏れ / blessed-names に入っていない import が刈られた |
| conformance が iOS/Android だけ落ちる | Dynamic コンバータのミラー修正漏れ |
| CI ssot-guards が落ちる | attr-bindings / conformance generate の再生成コミット忘れ、または emitter に非決定論を入れた |
| CI mobile conformance が cancelled | まず timeout 到達を疑う（fixture 増加後の再採寸漏れ） |
| sjui で font weight が全部 regular | font_weight_mapping.json の配布漏れ（sync_tool の SHARED_CORE_PAYLOADS） |
| verify で大量の偽 drift | normalizer が片側にしか掛かっていない / AliasTable 空ガードの状況 |
| swift build が通らない | 仕様（iOS-only）。xcodebuild + simulator を使う |
| jsonui-doc check api が偽 mismatch を量産 | 実装側 OpenAPI の新ノイズクラス — `check/openapi_normalize.py` に正規化を足す（diff 側に分岐を足さない） |
| check の stale 表示が常時点灯 | input_hashes は project root 相対。root はレポート位置（docs/&lt;kind&gt;）の2階層上から導出される — `-d` の渡し方ではなくレポートの置き場所が正 |
