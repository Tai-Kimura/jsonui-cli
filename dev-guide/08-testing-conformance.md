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
| ruby-suites | rspec matrix（sjui は macos-15）Ruby 3.2（下限。3.3 にしか無い API はここで落ちる）。release/run-suites.sh も 3.2.2 で走らせる。kjui は Kotlin コンパイラ（JDK 17 + 固定 jar）で compile arm を実行 | 40m |
| ruby-generation-parity | kjui が Ruby 3.2（下限）と 3.3 で同じバイト列を出す（jsonui-cli 1.9.0 まで 2.6 と 3.3 だった） | 25m |
| **ssot-guards** | ①`jui conformance generate` → git diff ゼロ ②attr-bindings 決定論 ③rjui vendored テーブル diff | 10m |
| web-conformance | Node 24 + Playwright → web.results.json、gate `--env ci`（**視覚判定あり** — `baselines/ci/web` と比較。fixture 変更時は本レーンのアーティファクトから ci/web を焼き直して同 PR に載せる） | 30m |
| xcode-27-preview | 次期 Xcode での先行ビルド。**証拠であって前提ではない**（赤でも出荷は止めない） | 30m |

### conformance-mobile.yml（週次: 日曜 18:00 UTC = 月曜 03:00 JST + dispatch）

- ios: macos-15 + **Xcode 26.3 固定**、SwiftJsonUI + test-runner checkout、iPhone 16 Pro sim、150m（2026-10-07 に 90m から上げた。ios-codegen も同じ 150m。実測 ios 61 / 76 / 73 / 79 分・ios-codegen 71 / 81 / 89 分、1.9.18 で ios-codegen が 90m の予算で cancelled — 票 ci-ios-conformance-jobs-outgrow-their-90-minute-budget）
  （Xcode ビルド ~30m 込み）
- android: ubuntu + KVM、API 34 / pixel_tablet 固定、270m。**予算は「悪いランナー」基準**
  （良ランナー ~7 分、悪いと 6 倍）: boot ~2 分 + gradle ~5 分 + 20 分×最大 5 attempt の resumable 実行
  （step 95 + retry 130 + setup ~15 ≈ 245 → job 270。attempt 数は fixture 数から導出する — 算数は
  workflow のコメントに在る）。
  `progress.jsonl` で resume、timeout でチョップされた fixture は 1 回だけ再実行してから error 扱い。
  attempt-1 のみ retry 許容
- **ios-codegen / android-codegen**: 同じ fixture を生成コードで描画する 2 レーン
  （sjui/kjui 実 codegen → registry → HOST_MODE=codegen。予算は dynamic レーンと同算数）
- ios / ios-codegen が赤のとき: `Name the failed tests` step が run の xcodebuild.log から失敗した
  `Test Case` と `file:line: error:` を印字し（`.github/scripts/name_failed_xctests.py`、注釈にも出る）、
  xcodebuild.log と xcresult を artifact `failure-log-ios` / `failure-log-ios-codegen` に上げる（14 日）。
  run_conformance.sh は `tail -40` しか印字しないので、jsonui-cli 1.9.9 より前は失敗名がログに残らなかった
- **tap-repro**（dispatch で `tap_repro=true` のときだけ。ほかの 7 job はすべて止まる）: iOS Dynamic で 2 つの interactive
  fixture（Switch/onValueChange__callback_fire と common/clipToBounds__hit_overflow_true）を別 id の複製で交互に
  `tap_repro_repeats` 回ずつ回し、取りこぼしを数えて分類する（`.github/scripts/tap_repro.py`、SwiftJsonUI 8815b51 の
  post-tap 行: 2 回目の tap で通れば touch 未達、通らなければ handler 不応答）。予算 90 分（固定 ~18.5 分 + 300 本 ~32.5 分）
- ios / ios-codegen は緑でも赤でも `Record every XCTest result` が全テストの結果行（passed / failed / skipped）を
  クラスごとに 1 行で数えて印字し（`.github/scripts/record_xctests.py`、`Executed N tests` と突き合わせる）、
  行そのものを artifact `xctests-ios` / `xctests-ios-codegen` に上げる（7 日）。staging は suite step の env で
  `/tmp/jsonui-conformance-ios[-codegen].ci` に固定（run_conformance.sh 自前の staging は緑の run で消えるため）
- android-library-tests（125m。初回の実測は step 17.5 分 / 262 case。2026-10-04 時点の直近 5 本は 17.8〜26.3 分 /
  394 case で、host の probe を足して (26.3 + 8) × 3 ≈ 103 → step 110）: KotlinJsonUI の
  `library` / `library-dynamic` / `conformance-host` の androidTest（connectedDebugAndroidTest）を **API 35** / pixel_tablet で走らせる。
  host の ConformanceSuiteTest は除外する（android の job が run_conformance.sh で走らせる）。host の probe 13 クラスは
  2026-10-04 までどの CI でも走っておらず、そのうち TapRoleProbeTest は KotlinJsonUI 14c075b 以来赤のままだった
  （conformance の 34 ではない。API 34 の CI emulator では IME が出ず、前面 window の読み上げも空になることがあり、
  焦点を要する腕が emulator を測ってしまう。matrix run 36197930038 で 34 は赤、35 は緑、画面キーボードの設定は無関係）。判定は結果 XML から（`.github/scripts/kjui_device_tests.py`）:
  失敗 / error / 結果の無いモジュール / **@Test を持つのに結果に 1 件も無いクラス** / **device test を持つのに、この job が走らせず
  `UNREACHED_MODULES` に理由つきで名前も無いモジュール**が赤。skip は名前で印字。sample-app は理由つきで名指しされている
  2026-09-26 まで、この 2 モジュールの androidTest はどの CI でも走っていなかった。
  Gradle は `kjui_device_tests.py watch` の下で走る: 最初に失敗した case の時点で端末の状態（screenshot /
  `dumpsys input_method` / `dumpsys window` / 上の activity / logcat）を `device-evidence/first-failure` に、
  モジュールの進捗の数が 600 秒（`KJUI_IDLE_SECONDS`。緑の 5 run で最長 120 秒）動かなければ状態を
  `device-evidence/stopped` に残して Gradle を止める（exit 124）。2 run が `Tests 0/203` のまま 99 分、step の予算まで
  止まり、Gradle の後の証拠集めが一度も走らなかった（ticket ci-android-library-tests-emulator-dies-in-the-keyboard-
  tests-and-the-run-hangs）。emulator console の失敗行は合図ではない（緑の run でもモジュールごとに出る）。
  テストの前に `hide_error_dialogs=1`（ANR / crash でダイアログを出さず app を閉じる。API 35 の tablet AVD で、
  設定なしはダイアログが focus を取り、設定ありは出ないことを両側で測った）。watch は 15 秒ごと（`KJUI_FOCUS_SECONDS`）に
  window の focus を読み、system の「isn't responding」ダイアログなら状態を `device-evidence/anr-N` に残して、その app を
  force-stop（テスト対象の package は閉じずに記録だけ）、時刻と回数を `device-evidence/anr-dialogs.txt` に書く。
  run 37618369032: Pixel Launcher の ANR ダイアログが focus を 14 分持ち、IME が一度も出なかった。
  テストの前に IME が出せるかも確かめる（`kjui_device_tests.py ime`）: 自分から IME を求める画面（Settings の検索、
  無ければ global search）を開いて `mInputShown=true` を待ち、`KJUI_IME_BUDGET_SECONDS`（120。緑の run は最初の要求から
  最長 35 秒で出た）の間やり直す。一度も出なければ状態を `device-evidence/ime-never-shown` に残し、テストを走らせずに
  「the IME never showed before the tests」で落とす（環境の赤。run 37650134866 はこれを library のキーボードの 10 件として出していた）。
  画面がその image に無ければ WARNING（IME は確かめていない）を出してテストへ進む
- dispatch の入力: `swiftjsonui_ref`（iOS 2 job）/ `image_probes` / `kotlinjsonui_ref`（Android 3 job）/
  `android_probes`（テストが `getArguments().getString("x") == "1"` と比べる旗をすべて立てる。旗の一覧は
  テストから導出）。2 つの probe は **jsonui-cli 1.9.8 から既定で true**（下ろすときだけ `=false`）。
  **SwiftJsonUI / KotlinJsonUI のタグの前に release 枝で撃つ**。schedule は入力無し＝既定ブランチ、probe なし。
  `android_library_only=true` は android-library-tests だけを走らせる（ほかの job と report は止まる）。
  KotlinJsonUI の device test だけを繰り返すとき用（conformance の job は 1 本も走らない）
  ⚠️ 同じ枝へ続けて撃つと消える: workflow の concurrency は枝（ref）ごとで、GitHub は同じ group に実行中 1 本＋待機 1 本しか
  持たず、3 本目が来ると待機中の run を cancel する（`cancel-in-progress: false` が守るのは実行中だけ）。2026-10-07 に
  同じ枝へ 3 本ずつ撃ち、2 本目が job 0 本のまま cancelled（37618377022 / 37618381831）。まとめて撃つなら 1 本ずつ別の枝から
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

  📐 **`--frame-parity`**（2026-10-05、frame_parity.py）は、宣言された id が**どこに描かれたか**を
  面どうしで比べる。上の 3 つと違い **env に依らず赤**になる（frame は layout の幾何で、
  renderer の画素ではないため）。入力は各ドライバが screenshot の隣に書く `.frames.json`
  （`conformance/frames.schema.json`、RESULTS_SCHEMA.md の `frames` 節）。許容差は
  `frame_parity.TOLERANCE` の 1 か所だけ。比べられなかったものは理由ごとに 1 行ずつ件数を印字し、
  1 件も比べられなかった run は赤になる。3 面（web / android / ios）とも frames を書き、
  `EXPECTED_FRAME_HOSTS` に宣言済み。CI（conformance-mobile.yml）では jsonui-cli 1.9.17 から
  **既定で走る**（input `frame_parity` の既定 true。式は `!= false` なので、input を持たない
  schedule でも走る。`= true` だと schedule は空文字で off のままになる）。外すのは dispatch で
  `-f frame_parity=false`。旗なしの gate は `note: frame parity: NOT judged (--frame-parity not given)`
  を印字する（旗なしが無言だと「比べて一致」と「比べていない」が同じ出力になるため）。
  on の run は `note: frame parity (…): N fixture(s) compared, …` を印字する。

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
