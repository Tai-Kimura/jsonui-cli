# 01. アーキテクチャ全体像

## 1. リポジトリ地図

| リポジトリ | 役割 | 主要言語 | 公開物 |
|---|---|---|---|
| **jsonui-cli**（本リポジトリ） | 全 CLI ツール + SSoT + conformance のモノレポ | Ruby / Python | `~/.jsonui-cli` へインストール（bootstrap.sh） |
| **SwiftJsonUI** | iOS ランタイムライブラリ（UIKit + SwiftUI、Dynamic モード内蔵） | Swift | CocoaPods + SPM（tag = VERSION） |
| **KotlinJsonUI** | Android ランタイム（`:library` + `:library-dynamic`、Compose） | Kotlin | Maven Central + JitPack（両モジュール同一バージョン） |
| **ReactJsonUI** | Web。**ランタイムパッケージなし**（完全静的生成）。example アプリ + ドキュメントのみ | — | npm 公開なし |
| **jsonui-mcp-server** | Claude Code 用 MCP サーバー `jui-tools`（42ツール） | TypeScript | `~/.jsonui-mcp-server` + `~/.claude.json` 登録 |
| **jsonui-test-runner** | テスト JSON スキーマ（トップレベル `schemas/`）+ 3プラットフォームドライバの正本。`jsonui-test` CLI は jsonui-cli へ移設済み | TS/Swift/Kotlin/Python | ドライバ 3 種とも各リポジトリを指す submodule（2026-08-01 に ios も 1.9.1 で submodule 化、URL は https） |
| **jsonui-helper** | VSCode 拡張（補完・診断・スニペット）。CLI/MCP とは独立に SSoT を vendor | TypeScript | .vsix |
| **JsonUI-Agents-for-claude** | コンシューマプロジェクト用 Claude エージェント/ルール一式 | Markdown | 各プロジェクトの `.claude/` に配置 |

### jsonui-cli モノレポの内訳

```
jsonui-cli/
├── shared/core/          ★ 属性 SSoT（attribute_definitions.json ほか）→ 02章
├── jui_tools/            Python 統合 CLI「jui」（クロスプラットフォーム生成・配布・検証）→ 03章
├── sjui_tools/           Ruby「sjui」 iOS codegen → 04章
├── kjui_tools/           Ruby「kjui」 Android codegen → 05章
├── rjui_tools/           Ruby「rjui」 Web codegen → 06章
├── test_tools/           **`jsonui-test` CLI の正本**（self-contained・`pip install -e` で配布）→ 08章
├── document_tools/       Python「jsonui-doc」（spec 検証・HTML/Mermaid 生成）
├── conformance/          fixtures 717件 + web ホスト + baselines + レポート → 08章
├── installer/ install.sh 配布 → 09章
├── dev-guide/            ★ 本ガイド（追跡・公開。2026-08-01 に docs/ から移動）
└── docs/                 ローカル専用（gitignore）: plans / bugs / jui_tools_README ほか
```

## 2. 2つの SSoT レイヤーを混同しない

このエコシステムには「SSoT」が **2階層** ある:

1. **ライブラリ開発者向け SSoT（本ガイドの主題）**
   `shared/core/attribute_definitions.json` = 「JsonUI 言語仕様」の正本。
   属性名・型・enum・エイリアス・deprecation・プラットフォームタグを一元管理し、
   バリデータ（Ruby 3ツール）、型付き属性コード（Swift/Kotlin/Ruby）、conformance fixtures、
   MCP のコンポーネント検索がすべてここから派生する。

2. **コンシューマプロジェクト向け SSoT**
   spec（`*.spec.json`）= 意図と契約の正本、Layout JSON（共有 layouts/）= UI 構造の正本。
   `jui build` が各プラットフォームへ「コピー」を配布する。プラットフォーム側 Layouts/ は成果物であり編集禁止。

## 3. 全体データフロー（ライブラリ視点）

```
shared/core/attribute_definitions.json（属性 SSoT）
  ├─(symlink)→ {s,k,r}jui_tools/lib/core/attribute_definitions.json … Ruby validator が直接読む
  ├─(jui g attr-bindings)→ build/attr_codegen/{swift,kotlin,ruby}/
  │     ├─ swift → SwiftJsonUI/.../Dynamic/Generated/Attributes/（rsync スクリプトで取込み・コミット）
  │     ├─ kotlin → KotlinJsonUI/library-dynamic/.../TypedAttrs 系
  │     └─ ruby  → rjui_tools/lib/core/generated/attributes/（vendored、CI が鮮度を diff で強制）
  ├─(jui conformance generate)→ conformance/fixtures/**（717件、決定論的、CI が diff ゼロを強制）
  ├─(4層フォールバック)→ jsonui-mcp-server（起動時ロード・メモリキャッシュ）
  └─(scripts/sync-specs.sh)→ jsonui-helper/vendor/（手動 vendor）
```

```
レンダリング実装は各プラットフォーム 2 系統（+レガシー）:
  iOS:     sjui codegen（*.rb → *View.swift）⇄ Dynamic モード（Swift converters、DEBUG限定）
  Android: kjui codegen（*.rb → GeneratedView.kt）⇄ library-dynamic（Dynamic*Component.kt）
           ※ XML(Android Views) パスは 2026-07-03 凍結、3.0 で削除候補
  Web:     rjui codegen（*.rb → JSX/TSX + Tailwind）のみ（Dynamic なし、ランタイムなし）
```

**codegen コンバータと Dynamic コンバータはミラー関係**であり、両方直すのが原則。
その一致を機械検証するのが conformance（08章）。

## 4. 設計原則（`.claude/jsonui-rules/design-philosophy.md` +
`docs/plans/2026-07-02-renderer-ssot-00-overview.md` より）

- **正準が正、エイリアスは normalizer**。emitter にエイリアス分岐を書かない。
  L1 正規化済み（`$jui` マーカー付き）レイアウトでは各ツールは canonical-only パスを取る。
- **CI が到達しない資産は追加しない**（追加するなら凍結宣言する）。
  決定論チェック（attr-bindings 2回実行一致、conformance generate diff ゼロ）が CI ゲート。
- **ツール先・フォーマット後**: 新機能はまずツール（jui/コード生成）に実装し、レイアウトフォーマット拡張は後。
- **抽象化しない境界線**: レンダラー本体（意味論の適用コード）は自動生成しない。生成するのは
  fixture・正規化・型付き属性抽出まで（Renderer SSoT 3本柱: conformance / normalizer / attr-codegen）。
- **DTO / Domain 分離**: swagger 由来の DTO（`@generated`、毎ビルド再生成）と、ユーザー所有の Domain
  ラッパ（初回のみ生成、以後スキップ）は物理的に別ファイル。スキーマ変更は Domain プロキシの
  コンパイルエラーとして局所化される。

## 5. 全体不変条件（どの修正でも守る）

1. `jui build` の**冪等性**: 2回実行して diff ゼロ。normalizer も `normalize(normalize(x)) == normalize(x)`。
2. 生成物には必ず `@generated` / `_generated` マーカー。手編集検出は `jui lint-generated`。
3. 既存プロジェクトを壊さない: 出力が変わる変更は opt-in から始め、実コンシューマの worktree で
   「生成物バイト一致」を確認してからデフォルト化する（renderer-ssot-10-final-verification.md 方式）。
4. コンシューマ「昔は動いてた」報告は、**リグレッション前の emit を diff** し、プロジェクト側の
   git 履歴（カスタム Swift/JSON）も確認してからライブラリを直す。正準セマンティクスが
   コンシューマの期待に優先する。
5. conformance の before/after が一致することがリファクタのマージゲート。

## 6. コンシューマ側ワークフローとの接点

コンシューマプロジェクトでは JsonUI-Agents-for-claude の `.claude/` 一式
（jsonui-conductor ほか 9 エージェント + jsonui-rules 5ファイル）が MCP 経由で
`jui build` / `jui verify` / spec 読み書きを回す。ライブラリ側の変更は:

- `jui sync_tool` でプロジェクトローカルの `<platform>/<tool>_tools/` コピーに伝播（extensions/ は保護）
- MCP は**再起動するまで**新属性を認識しない（07章）
- エージェント/ルール md に書かれた挙動（例: swagger halt 条件、oneOf+discriminator 対応）は
  jui 実装変更時に追従更新が必要（過去コミット参照: `docs(agents+skill)` 系）
