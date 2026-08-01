# JsonUI エコシステム メンテナーガイド（正規ドキュメント）

このディレクトリは **JsonUI エコシステム全体をライブラリ開発者として修正するための正規ドキュメント**。
2026-07-07 時点の全リポジトリ実地調査（コード・CI・スクリプト読解）に基づく。

対象読者はコンシューマアプリの開発者ではなく、**jsonui-cli / SwiftJsonUI / KotlinJsonUI / ReactJsonUI /
jsonui-mcp-server / jsonui-test-runner を修正する人**。コンシューマ向けの使い方は
`docs/jui_tools_README.md`（日本語・正）を参照。

> **2026-08-01 から本ガイドは追跡・公開対象**（`dev-guide/`、W3-3 で `docs/dev-guide/` から移動）。
> `jsonui-cli/docs/` は従来どおり .gitignore（コンシューマ名を含むバグ報告・計画メモの置き場）。
> 本文中の `docs/...` 参照はメンテナのローカル checkout にのみ存在する文書を指す。
> 公開領域なので、コンシューマ固有の名前・パス・ローカル絶対パスを書かないこと
> （pre-commit の leak-guard と CI の publication-hygiene が検査する）。

## ファイル構成（読む順）

| # | ファイル | 内容 |
|---|---|---|
| 1 | [01-architecture-overview.md](01-architecture-overview.md) | リポジトリ地図・全体データフロー・設計原則・不変条件 |
| 2 | [02-ssot-shared-core.md](02-ssot-shared-core.md) | shared/core の中身、SSoT 消費マトリクス、正規化 L0/L1/L2、attr-codegen |
| 3 | [03-jui-cli-internals.md](03-jui-cli-internals.md) | Python `jui` CLI の内部構造（build / verify / generate / sync_tool / hotload） |
| 4 | [04-platform-ios.md](04-platform-ios.md) | SwiftJsonUI + sjui_tools（改修ポイント・ビルド・罠） |
| 5 | [05-platform-android.md](05-platform-android.md) | KotlinJsonUI + kjui_tools（同上、XML凍結の実態含む） |
| 6 | [06-platform-web.md](06-platform-web.md) | ReactJsonUI + rjui_tools（ランタイムレス静的生成の実態） |
| 7 | [07-mcp-server-editor.md](07-mcp-server-editor.md) | jsonui-mcp-server（42ツール）+ jsonui-helper VSCode 拡張 |
| 8 | [08-testing-conformance.md](08-testing-conformance.md) | jsonui-test-runner・jsonui-test CLI・コンフォーマンス717fixtures・CI |
| 9 | [09-release-distribution.md](09-release-distribution.md) | 配布モデル（~/.jsonui-cli）、各リポジトリの公開手順、伝播フロー |
| 10 | [10-maintenance-playbooks.md](10-maintenance-playbooks.md) | **実作業レシピ集**: 属性追加・コンポーネント追加・テストアクション追加・バグトリアージ |

## 最短で使うには

- **属性を1つ追加したい** → まず [10-maintenance-playbooks.md](10-maintenance-playbooks.md) のプレイブック1。
  背景理解が必要になったら 02（SSoT）と該当プラットフォーム章（04/05/06）へ。
- **「昔は動いてた」系のバグ報告が来た** → 10 のプレイブック5（トリアージ）と各章の「罠」節。
- **CI が落ちた** → 08 の CI 節（決定論ゲート・conformance 予算の考え方）。
- **リリースしたい** → 09。

## この文書群の前提となる鉄則（全章共通）

1. **正準（canonical）が正**。エイリアスは normalizer / validator の仕事であり、emitter に散らさない。
2. **`@generated` ファイルは手編集しない**。SSoT（attribute_definitions.json / spec）を直して再生成する。
3. **生成は決定論的**であること（タイムスタンプ・未ソート反復禁止）。CI が「再生成して diff ゼロ」でゲートしている。
4. **codegen コンバータと Dynamic モードコンバータは常にペアで直す**（iOS/Android とも）。片方だけ直すと conformance が落ちる。
5. **コンシューマプロジェクト固有の名前・パスを公開リポジトリのコミットに入れない**（docs/ が gitignore されている理由）。

## 関連する既存正規文書（重複させない）

- `docs/jui_tools_README.md`（ローカル専用） — `jui` のユーザー向け仕様（spec の書き方、ViewModel Protocol 同期、型マップ等）。**本ガイドはこれを再掲しない**。
- `docs/plans/2026-07-02-renderer-ssot-*.md` — Renderer SSoT 化マスタープラン（本ガイド 02 章の背景）。
- `docs/bugs/README.md` + `docs/bugs/reports/` — バグ受付箱と過去の修正レポート。
- `conformance/RESULTS_SCHEMA.md` / `conformance/INTERACTIVE_HOST_CONTRACT.md` — コンフォーマンスの契約書。
- `jui_tools/jui_cli/generators/attr_codegen/README.md` — 型付き属性生成の契約書。

## 過去に発見・修正したドキュメント乖離（2026-07-07 修正済み）

初回調査時に以下の乖離を発見し、**各リポジトリのドキュメントを修正済み**（2026-08-01 の
ecosystem-hardening で各リポジトリともコミット・push 済み。KotlinJsonUI / SwiftJsonUI の
CLAUDE.md はさらに P9 で全面刷新）。同種の乖離が再発しやすい箇所として記録を残す:

| 場所 | 乖離していた内容（→ 修正済み） |
|---|---|
| `KotlinJsonUI/CLAUDE.md` | Project Structure が kjui_tools を Kotlin 製・リポジトリ内と記載 → 実際は Ruby 製・jsonui-cli モノレポ内。`:sample:` → `:sample-app:`、API 21+ → 24+、古い Progress チェックリスト削除も実施 |
| `ReactJsonUI/CLAUDE.md` | 構成図に `ReactJsonUI/rjui_tools/` → 実際は jsonui-cli/rjui_tools。sjui_tools 参照パスも旧 `SwiftJsonUI/tools/` から修正 |
| `jsonui-test-runner/README.md` `CLAUDE.md` | Android ドライバ Espresso → **UIAutomator** |
| `jsonui-mcp-server/docs/design.md` / `README.md` | ツール数 30/29/28 → **33**（Group E: API 3ツール + get_data_source / jui_sync_tool の記載漏れを追記） |
| `SwiftJsonUI/README.md` | "iOS8/Swift4+" → iOS 13(CocoaPods)/iOS 17(SPM)、Swift 5.8+ |

教訓: **リポジトリ構成を変えたら（特にツールのモノレポ移設）、旧リポジトリの CLAUDE.md /
README の構成図を同時に更新する**。エージェントはこれらを信じて動くため、乖離は実害になる。
