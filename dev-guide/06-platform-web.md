# 06. Web — ReactJsonUI + rjui_tools

## 1. 前提: ランタイムは存在しない

ReactJsonUI は**完全静的コード生成**方式。npm パッケージも React ランタイムライブラリもない。
コンシューマの依存は `next` / `react` / `tailwindcss` だけで、必要なランタイム片
（EmbedContainer, NetworkImage, StringManager, ColorManager, hooks）は
**rjui build がプロジェクト内に emit する**。

- `ReactJsonUI` リポジトリの実体は `example/`（Next.js 16 / React 19 / Tailwind v4 デモ）+
  ドキュメントのみ。ジェネレータの正体は **`jsonui-cli/rjui_tools`**（CLAUDE.md にも明記済み。
  `rjui_tools/VERSION` はリポ直下 `VERSION` のロックステップ複製 = 現 1.1.0 — 09章）。
- `example/` は生成出力のリファレンスを兼ねる。特に
  `example/lib/react/converters/extensions/`（プロジェクトローカル Ruby コンバータ拡張の実例）。
- Dynamic モードも Web には存在しない（3プラットフォームで唯一 codegen 一本）。

## 2. rjui_tools 構造

```
rjui_tools/lib/
├── cli/commands/        init/build/watch/hotload/generate
├── core/                validators/normalization/responsive_resolver/…
│                        attribute_definitions.json(4427行, symlink 相当) +
│                        generated/attributes/*.rb ★ vendored 型付きテーブル（CI が鮮度強制）
└── react/
    ├── react_generator.rb        CONVERTERS レジストリ + ファイル組み立て（"use client" 判定、
    │                             hooks/StringManager/lucide/Configuration import、useState 抽出）
    ├── converters/*.rb           25 converters + base_converter.rb（属性→Tailwind 中央エンジン）
    │   └── extensions/           組み込みカスタム部品（CodeBlock 等）
    ├── tailwind_mapper.rb        純関数群 map_width/map_padding/map_color/map_gravity/…
    ├── responsive_helper.rb      size class → md:/lg: プレフィクス + landscape useMediaQuery
    ├── data_model_generator.rb / viewmodel_generator.rb / hook_generator.rb
    ├── style_loader.rb / helpers/（string_manager, lucide_icon, font_spec）
    ├── generators/converter_generator.rb  カスタムコンバータ scaffold（rjui g converter）
    └── templates/                ホストへ emit するランタイム片: Configuration.ts,
                                  EmbedContainer.tsx, network_image.tsx, use_color_mode.ts, use_media_query.ts
```

ビルドフロー（`build_command.rb`）: StringManager 更新（strings.json + Strings/{lang}.json →
useSyncExternalStore ベース）→ Data モデル → cellIdGenerator（FNV-1a）→ ColorManager
（hex 抽出→テーマキー化）→ 各 Layout: parse → style merge → validate（L0 alias-tolerant /
L1 canonical、`$jui`）→ ReactGenerator → `.tsx/.jsx` → ViewModel/hooks 生成 →
組み込み部品 ensure → 孤児 prune。

### スタイリングの方針

- 静的属性 → Tailwind クラス（`bg-[#007AFF]` 等の arbitrary value 含む、
  margin は `mt-2 mr-0 mb-6 ml-0` に展開）
- 動的バインディングと CSS グラデーション → inline `style={{}}`
- `fontFamily` 指定時はフォント一式が `Configuration.Font.resolve(...)`（inline style）に
  ルーティングされ、Tailwind の weight/size クラスは**意図的に落とす**（詳細度で inline が勝つ）

### バインディング

- `@{prop}` → `{data.prop}`（`viewModel.data.x` / `data.x` / `x` すべて `data.x` に正規化）
- `onClick`（camelCase）= `@{fn}` バインディング必須 / `onclick`（小文字）= セレクタ文字列。
  誤用は **JSX に ERROR コメントを emit** する仕様
- `{action:link, url}` オブジェクト → `window.open`
- binding 内のビジネスロジックは BindingValidator が警告（VM へ寄せる）

## 3. どこを直すか

**属性追加**: SSoT → `jui g attr-bindings --lang ruby` で vendored テーブル再 emit（コミット必須、
CI `ssot-guards` が diff 照合）→ `tailwind_mapper.rb` に `map_*` を追加 →
横断属性なら `base_converter.rb#build_class_name`、固有なら該当 converter → RSpec
（`rjui_tools/spec/react/`）。**必ず sjui_tools の同属性実装を先に見る**（リファレンス実装）。

**組み込みコンポーネント追加**:
1. `converters/<name>_converter.rb`（BaseConverter 継承）
2. **登録は 2 箇所**: `react_generator.rb` の `CONVERTERS` と
   `base_converter.rb#get_converter_class` — 重複レジストリで両方必須
3. ランタイム片が要るなら `templates/` + `build_command.rb#ensure_builtin_components`
   （+ `init_command.rb#create_builtin_components`、import は `extract_extension_components`）

**プロジェクトローカルカスタム部品**（コア変更なし）: `rjui g converter <Name> --attributes k:type,...`
→ プロジェクトの `lib/react/converters/extensions/` に converter + mappings +
attribute_definitions/<Name>.json + `src/components/extensions/<Name>.tsx` skeleton。

## 4. ビルド・テスト

- RSpec: `cd rjui_tools && bundle exec rspec`（CI: Ruby 3.3）
- Web conformance: `conformance/hosts/web/`（Vite+React）`./generate.sh`（fixture → rjui 実 codegen →
  fixtureRegistry）→ `npm run conformance`（Playwright headless、vendored executors、
  port 4177 / 6 workers）→ `results/web.results.json`。**per-push CI で常時実行**（0 fail / 0 error ゲート）。
  Node ≥ 23 必須（scripts/run.ts がネイティブ TS type stripping 依存、CI は Node 24）。

## 5. 罠（Web 固有）

- **SSR/hydration**: StringManager は `getServerSnapshot` でデフォルト言語を返し、
  persisted locale は hydration 後に swap。VM の constructor/onAppear では
  `getDefaultString` を使う（`getString` は hydration mismatch を起こす）。
  生成コードが `const $s = useStringManager()` を使い `StringManager.currentLanguage.` を
  `$s.` に書き換えるのは setLanguage 反応性のため。
- **matchParent height は軸依存**（`base_converter.rb:78-93`）: ZStack 子 → `h-full`、
  flex-row 親 → `self-stretch`、縦/不明 → `flex-1 min-w-0 min-h-0`。誤ると兄弟幅の乗っ取り/overflow。
- カスタム部品が Tailwind emission を抑止できる（reclaim できる）decoration key は
  `minWidth/maxWidth/minHeight/maxHeight` のみ（`DECORATION_KEYS_OVERRIDABLE`）。
- StringManager の名前空間はディレクトリ修飾 snake_case（`learn/installation.json` →
  `learn_installation`）。
- ViewModelBase はフラット配置前提（ネストは旧 Python ジェネレータの孤児として prune される）。
- `JUI_SKIP_EXISTING=1`（jui build が設定）で converter 生成が非対話化。
