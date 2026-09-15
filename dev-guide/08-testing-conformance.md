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
  baseline 更新: `jui conformance baseline update --platform <p> [--env <e>] --fail-on-moved`。
  **`--fail-on-moved` は既定 off で、付けないと既存の絵が変わっても exit 0 で焼ける**
  （吸収された regression は regression でなくなる）。赤で止まったら `MOVED` 行を
  1 本ずつ読み、意図した変化だと判断してから旗を外して焼き直す。`unstable` 行は
  別集合で件数に入らない。
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
| publication-hygiene | 公開物に消費側の名前・パス・型が漏れていないか | 5m |
| python-suite | jui_tools unittest + protocol-sync 冪等性 e2e | 15m |
| stub-identifier-tables | 生成スタブの識別子表が SSoT と一致 | 20m |
| ruby-suites | rspec matrix（sjui は macos-15）Ruby 3.3 | 20m |
| ruby-generation-parity | kjui が Ruby 2.6 と 3.3 で同じバイト列を出す | 25m |
| **ssot-guards** | ①`jui conformance generate` → git diff ゼロ ②attr-bindings 決定論 ③rjui vendored テーブル diff | 10m |
| web-conformance | Node 24 + Playwright → web.results.json、gate `--env ci`（**視覚判定あり** — `baselines/ci/web` と比較。fixture 変更時は本レーンのアーティファクトから ci/web を焼き直して同 PR に載せる） | 30m |
| xcode-27-preview | 次期 Xcode での先行ビルド。**証拠であって前提ではない**（赤でも出荷は止めない） | 30m |

### conformance-mobile.yml（週次: 日曜 18:00 UTC = 月曜 03:00 JST + dispatch）

- ios: macos-15 + **Xcode 26.3 固定**、SwiftJsonUI + test-runner checkout、iPhone 16 Pro sim、90m
  （Xcode ビルド ~30m 込み）
- android: ubuntu + KVM、API 34 / pixel_tablet 固定、270m。**予算は「悪いランナー」基準**
  （良ランナー ~7 分、悪いと 6 倍）: boot ~2 分 + gradle ~5 分 + 20 分×最大 5 attempt の resumable 実行
  （step 95 + retry 130 + setup ~15 ≈ 245 → job 270。attempt 数は fixture 数から導出する — 算数は
  workflow のコメントに在る）。
  `progress.jsonl` で resume、timeout でチョップされた fixture は 1 回だけ再実行してから error 扱い。
  attempt-1 のみ retry 許容
- **ios-codegen / android-codegen**: 同じ fixture を生成コードで描画する 2 レーン
  （sjui/kjui 実 codegen → registry → HOST_MODE=codegen。予算は dynamic レーンと同算数）
- report: 5 job 後、ゲート = 欠落 0 / mismatch 0 / stale 0 / fail 0 / error 0 /
  visual regression 0 / ratchet 天井内 / **parity（codegen ⇔ dynamic ci ベースライン、
  codegen_parity.json 台帳照合）**。1 コマンド:

  ```
  jui conformance gate --platform ios --platform android --platform web --env ci \
      --parity --cross-effect --inert-complete --value-discrimination \
      --rendered-by swiftjsonui.src=… --rendered-by ios.toolchain=… （計 6 本）
  ```

  🔴 **`--env ci` は `--inert-complete` / `--cross-effect` / attribute-effect を「注記」に
  格下げする。** activeness と inert verdict は **local-env で主張される量**だから
  （gate.py の env スコープ）。つまり **CI がいくら緑でも、この 3 つは一度も撃たれていない**。
  2026-09-15 実測: CI 6/6 緑の同じ run で、inert 台帳は stale 33 件・未計上 12 件。
  これらを実際に判定できるのは **3 面をローカルでレンダしてから `--env local` で撃つとき**だけで、
  手元の results は放っておくと数週間古くなる（当日の実測: android が 12 日前、web が 38 日前、
  どちらも manifestHash が旧）。**glass のように manifest が動いた変更の後は、
  local 面の再レンダまでが 1 セット**。

**CI 予算の鉄則**（過去の実測から）: cancelled はまず timeout 到達を疑う。fixture を増やしたら
再採寸する（ローカル実測 × 5-7 倍が CI 目安）。attempt < step < job の算数を workflow コメントに書く。

## 6. よくある作業

🔻 **門の「こう直せ」に従う前に、その指示が前提を壊さないか測る**（2026-09-15、実害あり）。

`inert_audit.json` の一部の行は、**自分が在ることで fixture を対照比較から外す**。
`control_diff.off_face_exclusions` が **reason 散文の sentinel**
（`"Family: off-face-equals-control."`）を grep して除外集合を作るからで、
`adjudicatedFamily` ではない——台帳の `_comment` が
「Consumers key off those, never off a sentinel inside the prose」と書いているのは
**実装と逆**なので信じないこと。

除外された fixture は測定に現れないので、素朴な ratchet は永遠に stale と言う:

```
32 行が在る  → 「32 stale。--update で剪定せよ」
32 行を消す  → 「34 未計上。--update で記録せよ」
```

**どちらの指示に従ってももう一方が出る。** 剪定側は破壊的で、`update_ledger` が
測定から台帳を作り直すため調停 32 件と除外集合ごと消える。当日、指示どおり実行して
壊した。`self_excluding()` の免除と持ち越しで閉じ、
`test_the_inert_ratchet_is_not_a_catch22.py` が変異で赤くなることを確認済み。

📌 **この種の穴は CI に出ない。** inert / cross-effect / attribute-effect は
local-env で主張され、CI の `--env ci` では注記に落ちる。**CI が緑である期間と、
これらが正しい期間は別物**。manifest を動かしたら local を撃つこと。

**manifest が動く変更のあと、local 面を測り直す**（2026-09-15 に手順として確定）:

`results/*.results.json` は**判定だけ**を持ち、画素は `artifacts/<platform>/` 側にある。
env 依存は画素のほうだけなので、`--env local` の判定を成り立たせるには **3 面とも
その manifest でレンダし直す**必要がある。当日の実測では android が 12 日前 /
web が 38 日前で、どちらも `manifestHash` が旧だった。

```
web      cd conformance/hosts/web && ./generate.sh && npm run conformance   # ~3 分
android  conf_ci AVD を起動 → CONFORMANCE_DIR=<repo>/conformance \
         ANDROID_SERIAL=emulator-5554 JAVA_HOME=/opt/homebrew/opt/openjdk@17 \
         KotlinJsonUI/conformance-host/scripts/run_conformance.sh --fresh
         → collect_results.sh                                               # ~8 分
ios      SIMULATOR_UDID=<iOS 26 の iPhone 16 Pro> \
         SwiftJsonUI/ConformanceHost/scripts/run_conformance.sh             # 全面で ~45 分
         CONFORMANCE_FILTER=<部分一致> で 1 コンポーネントだけなら ~60 秒
```

🔻 **ベースラインを scratch の木から焼いたら、その画素を `conformance/artifacts/<p>/`
にも置く。** `conformance/artifacts/` は gitignore なので、置き忘れても `git status`
に出ない。2026-09-15 に iOS でこれが起き、local ios lane が**自分のベースラインに対して
590 regression** を出す状態が誰にも見えないまま残った。どの木が正本かは
「ベースラインを再現するか」で同定できる（3 候補を当てて 865/865・844/865・0/852）。

⚠️ **artifacts/ は run をまたいで消えない。** 消えた fixture の絵が残り、全面焼成が
それをベースラインに取り込む（2026-09-15: 08-07 の control 1 枚）。捕まえるのは
`missing_artifact` ratchet なので、天井は 0 のままにしておくこと。

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
