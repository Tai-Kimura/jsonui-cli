# 08. テスト基盤 — jsonui-test-runner / jsonui-test CLI / conformance / CI

## 1. リポジトリの正本関係（間違えやすい）

- **jsonui-test-runner** が正本: `schemas/`（JSON Schema）、`drivers/`、`examples/`。
  - `drivers/{ios,android,web}` は **3 種とも git submodule**（`Tai-Kimura/jsonui-test-runner-{ios,android,web}`
    のリリースタグを指す gitlink。2026-08-01 の P3 で ios の生ファイルコピーを撤去し 1.9.1 で
    submodule 化、URL は https に統一 — `git clone --recursive` 前提）。
    **ドライバ修正は各 standalone リポジトリでコミット・タグ → 親リポジトリで gitlink 更新**。
- **`jsonui-test` CLI の正本は `jsonui-cli/test_tools/`**（`document_tools` と同じモデルで移設済み）。
  self-contained（`validation/`〈launch.py/mock.py 含む〉+ `schema.py` を自前で同梱）で、`copy_shared_modules`
  には**渡さない**（旧 `shared/validation` 世代で mock/launch/setMocks 検証を握り潰さないため）。
  `document_tools`（`jsonui_doc_cli`）はバリデータ + スキーマ定数を **`jsonui_test_cli` から import** する
  （リポ内にテストバリデータは正確に 1 世代）。旧 `jsonui-test-runner/test_tools/` の CLI 本体は撤去済み。
  - **正本分担**: スキーマ（トップレベル 5 種）= jsonui-test-runner / バリデータ（`schema.py`・`validation/`）= jsonui-cli。
    両者はクロスリポでミラーするため drift-check を維持（§5 計画）。`mock.schema.json` はエディタ/doc 専用で実行時に読まれず、
    他のエディタスキーマと同じく jsonui-test-runner トップレベル `schemas/` に集約（CLI パッケージには同梱しない）。

## 2. テストファイル形式

スキーマ: `jsonui-test-runner/schemas/{screen-test,flow-test,actions}.schema.json`（draft-07）。

- **screen test**（`type:"screen"`）: `source.layout` 必須、`metadata`、`cases[].steps`。
  `platform`（ios/android/web/all、配列可、case 単位上書き可）、`initialState.viewModel`、
  `setup`/`teardown`、`embeddedIn`（`Parent#embedId` 形式で Embed 内実行）。
- **flow test**（`type:"flow"`）: steps は fileStep（`{"file":"screens/login","case(s)":...}` で
  screen test を参照）か inlineStep。`checkpoints[]`（afterStep + screenshot）。
- **actions の正本は `actions.schema.json` 一本**（2026-08-01 の P3 で正本化完了）:
  definitions の oneOf が全ステップを列挙（現在 **38 = アクション 28 + アサーション 10**）し、
  各定義の `x-doc {ja, platforms}` から README/CLAUDE の表を `npm run docs` で生成
  （手書き表は廃止、`npm run docs:check` が stale を検出）。CLI 側 `schema.py` の定数は
  vendored fixtures 経由の `test_schema_drift.py` がスキーマとの一致を CI で強制する。
- **source キーの正準は `document`**（screen / flow 共通。`spec` は deprecated alias —
  validator が警告付きで読み替え、併存はエラー。2026-08-01 の P11 で語彙統一）。
- 要素同定: JsonUI `id` → iOS `accessibilityIdentifier` / Android Compose `testTag` /
  Web `data-testid`・HTML id。
- Android ドライバは UIAutomator。

## 3. jsonui-test CLI

`jsonui-test validate|generate test|generate description|generate doc|generate html`。
検証実装: `test_tools/jsonui_test_cli/validation/`（validator → screen/flow/description、
`step.py` が action+assert 同居拒否・`@{varName}` プレースホルダ検証・file step の flow 限定を担当）。

## 4. conformance システム（jsonui-cli/conformance/）

**目的: 3 レンダラーが SSoT 全属性で同一挙動であることの機械証明**（WPT モデル）。

- **fixtures 717 組**（.layout.json + .test.json、28 コンポーネントセクション + common + __control）。
  すべて `jui conformance generate` の生成物（`_generated` センチネル付き、手書き禁止）。
  manifest 集計（2026-08-01 時点）: assertable 36 / visual 604 / interactive 37 / control 40 /
  skipped 159（全 skip に理由必須）/ promoted.callback 13。数値は `conformance/manifest.json` の
  `counts` が常に正。
- 分類は `jui_cli/conformance/rules.py`・`interactive_rules.py` のテーブルが持ち、
  `fixture_generator.py` は機械に徹する。**分類を変えたいときは rules を直す**。
- 実行ホスト: web = `conformance/hosts/web/`（Vite + Playwright、rjui 実 codegen）、
  iOS = `SwiftJsonUI/ConformanceHost`、Android = `KotlinJsonUI/conformance-host`
  （既定は **Dynamic モード**描画。vendored driver 使用）。
- **codegen ホストモード（plan 25）**: 同じモバイルホストが生成コードでも描画できる。
  `scripts/generate_codegen_host.rb`（各ホスト）が visual fixture を fx_NNNN 名で staging し
  **本物の `sjui build` / `kjui build`** を通して registry を生成 → iOS は
  `HOST_MODE=codegen scripts/run_conformance.sh`、Android は同スクリプトが
  instrumentation 引数 `conformanceHostMode` に転送。出力は `codegen/<p>.results.json` +
  `artifacts/<p>-codegen/`（dynamic の正本を汚さない）。
- interactive fixtures は `INTERACTIVE_HOST_CONTRACT.md` の汎用 state provider 1 個で賄う
  （per-fixture ホストコード禁止。データ既定値は各プラットフォームの production パスで注入）。
- 結果: `results/<platform>.results.json`（`RESULTS_SCHEMA.md` 準拠、manifestHash で stale 検出、
  全 fixture 分のエントリ必須）。visual は **`baselines/<env>/<platform>.hashes.json`**
  （dhash-64、Pillow。**ベースラインはレンダ環境ごと**: `local/` = 開発機、`ci/` = CI ランナー。
  閾値はマニフェスト格納 — 共有既定 8、ci/android のみ 12〈taskbar recents の
  インスタンス間二値、`baselines/README.md` の較正記録参照〉）。PNG はコミットしない。
- レポート: `jui conformance report` → `REPORT.md`（クロスプラットフォーム mismatch 表が主ゲート）。
  baseline 更新: `jui conformance baseline update --platform <p> [--env <e>] [--threshold N]`。
  **ci ベースラインは CI アーティファクトから焼く**（ローカルレンダ厳禁 — manifest が env を
  記録し、別 env での比較は loader が拒否する）。
- **parity（dynamic ≡ codegen）**: `jui conformance parity --platform <ios|android> [--env e]`
  が codegen ホストのスクリーンショットを**同一プラットフォームの dynamic ベースライン**と
  比較する（第 2 の正解は作らない）。乖離は `conformance/codegen_parity.json` に
  理由付きで記録（coverage.json と同じ運用: 未記録の乖離は fail、実測が消えた entry は
  stale で fail、`--update` で記録/剪定）。web は対象外（web ホストは元々 codegen 描画）。

## 5. CI（jsonui-cli/.github/workflows/）

### ci.yml（push to main + 全 PR）

| job | 内容 | timeout |
|---|---|---|
| python-suite | jui_tools unittest + protocol-sync 冪等性 e2e | 15m |
| ruby-suites | rspec matrix（sjui は macos-15）Ruby 3.3 | 20m |
| **ssot-guards** | ①`jui conformance generate` → git diff ゼロ ②attr-bindings 決定論 ③rjui vendored テーブル diff | 10m |
| web-conformance | Node 24 + Playwright → web.results.json、gate `--env ci`（**視覚判定あり** — `baselines/ci/web` と比較。fixture 変更時は本レーンのアーティファクトから ci/web を焼き直して同 PR に載せる） | 30m |

### conformance-mobile.yml（週次: 日曜 18:00 UTC = 月曜 03:00 JST + dispatch）

- ios: macos-15 + **Xcode 16.4 固定**、SwiftJsonUI + test-runner checkout、iPhone 16 Pro sim、90m
  （Xcode ビルド ~30m 込み）
- android: ubuntu + KVM、API 34 / pixel_tablet 固定、150m。**予算は「悪いランナー」基準**
  （良ランナー ~7 分、悪いと 6 倍）: boot ~2m + gradle ~5m + 20 分×最大 3 attempt の resumable 実行。
  `progress.jsonl` で resume、timeout でチョップされた fixture は 1 回だけ再実行してから error 扱い。
  attempt-1 のみ retry 許容
- **ios-codegen / android-codegen**: 同じ fixture を生成コードで描画する 2 レーン
  （sjui/kjui 実 codegen → registry → HOST_MODE=codegen。予算は dynamic レーンと同算数）
- report: 5 job 後、ゲート = 欠落 0 / mismatch 0 / stale 0 / fail 0 / error 0 /
  visual regression 0 / ratchet 天井内 / **parity（codegen ⇔ dynamic ci ベースライン、
  codegen_parity.json 台帳照合）**。すべて `jui conformance gate --env ci --parity` 1 コマンド

**CI 予算の鉄則**（過去の実測から）: cancelled はまず timeout 到達を疑う。fixture を増やしたら
再採寸する（ローカル実測 × 5-7 倍が CI 目安）。attempt < step < job の算数を workflow コメントに書く。

## 6. よくある作業

**fixture を増やす/変える**: 手書きしない。SSoT か rules.py を変更 → `jui conformance generate` →
diff が意図どおりか確認 → 各ホストで実行 → visual なら baseline 更新（local は手元、
**ci は次の conformance-mobile dispatch のアーティファクトから焼き直し**）→ report ゲート確認。
codegen ホストは staging を作り直すだけ（`generate_codegen_host.rb` 再実行）。

**テストアクションを追加する**（全レイヤー横断、単一コマンドなし）:
1. `schemas/actions.schema.json`（definitions + oneOf + **`x-doc {ja, platforms}` 必須** —
   欠落は表生成がエラーで止まる）
2. `test_tools/jsonui_test_cli/schema.py`（SUPPORTED_ACTIONS 等）+ 必要なら `validation/step.py`
   + `schema_fixtures/` 再 vendor（`VENDOR.md` 手順、drift テストが両者の一致を強制）
3. **3 ドライバ全部**の ActionExecutor/AssertionExecutor + モデル
   （3 種とも submodule — 各 standalone リポジトリでコミット・タグ → 親で gitlink 更新）
4. `npm run docs` で README/CLAUDE の表を再生成、CLI テスト + ドライバテスト
5. conformance ホストの vendored driver 再同期（kjui はローカルパッチ保持に注意 — 05章）
