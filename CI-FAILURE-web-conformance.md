# web-conformance が落ちた理由（PR #2、run 36369077809、head d5fdd3ad）

> 一時メモです。直したら、このファイルと隣の `CI-FAILURE-web-conformance.baseline.patch` を消してから merge してください。

## 結論

- 落ちたのは `web-conformance` job の門の step（`jui conformance gate --platform web --env ci`）だけです。スイート自体は pass 931 / fail 0 / error 0 / skipped 201 でした。
- 門を赤にしたのは、基準値との見た目の差 2 件です（dhash-64、しきい値 8）。

  | screenshot | 距離 |
  |---|---|
  | `common_effectStyle__chrome.png` | 27 |
  | `common_effectStyle__thick.png` | 17 |

- 原因は、d5fdd3ad で焼いた基準値の出どころです。
  - re-host した effectStyle の 9 件を、CI の成果物からではなく、手元で再現した job の描画から焼いています。commit 本文にも「The CI artifacts could not be downloaded, so these came from a local replica」とあります。
  - `conformance/baselines/README.md` は、`ci/` を「CI run の成果物から焼く。ローカルの描画からは焼かない」と定めています。
- コードの退行ではありません。CI の描画は毎回同じで、ずれているのは焼いた値のほうです（下の「測ったこと」）。

## 測ったこと

計器は、この枝の `jui_cli.conformance.baseline` の `dhash_file` / `ink_file` です（門と作り直しの道具が使う関数）。検体は、run 36369077809 の成果物 `web-conformance`（849 枚）です。

1. **計器の確認。** この成果物で門を回すと、CI と同じ 2 件（27 / 17）が出て rc 1 になりました。
2. **d5fdd3ad が触った 16 件を、CI の描画と比べました。**
   - ハッシュは 13 件が一致しました。違うのは次の 3 件です。
     - chrome: 27
     - thick: 17
     - regular: 1。しきい値の内側なので門は通しますが、`--fail-on-moved` で作り直すと MOVED に出ます。
   - ink が違うのは次の 3 件です。
     - extralight: 39998 → 40000
     - light: 39998 → 40000
     - thin: 39519 → 39680
     - この 3 件はハッシュの popcount が 140 で空白に近い絵ではないため、門は ink を判定に使いません。それでも、再現環境の値です。
   - 新しく足した 7 件（safeAreaInsetPositions の 6 件と control の 1 件）は、ハッシュも ink も一致しました。
3. **d5fdd3ad が触っていない 833 件は、ハッシュも ink も CI と完全に一致しました。** CI は、自分が以前に焼いた基準値をそのまま再現しています。
4. **CI の描画は安定しています。** この枝の 4 回の run で、chrome・thick・regular のハッシュは 4 回とも同じでした。

   | run | head |
   |---|---|
   | 36367790196 | bcfd09c0 |
   | 36368137534 | 83b58ece |
   | 36368399060 | 5a8e3997 |
   | 36369077809 | d5fdd3ad |

## thick と chrome だけがずれた理由（ここは測っていません）

- rjui の `EFFECT_STYLE_BLUR_PX` では、thick が 16px、chrome が 20px です。9 種類の中で、ぼかしが大きい上位 2 つです。
  - ほかの 7 種類は 12px 以下です。12px の regular は距離 1 でした。
- 手元の再現環境の Chromium が、大きなぼかしを CI のランナーと違うふうに描いた、と読むと観測に合います。ただし、再現環境の描画そのものは見ていないので、推測です。
- 再現環境が CI と同じ描画をしない証拠は、d5fdd3ad の本文にもう 1 つあります。SelectBox の `hint` と `placeholder`（`__static`）が、CI の基準値から距離 6 ずれた、と書かれています。

## 直し方（検証済み）

この環境からは CI の成果物を取れないとのことなので、run 36369077809 の成果物から焼いた結果をパッチにして、隣の `CI-FAILURE-web-conformance.baseline.patch` に置きました。

1. `git apply CI-FAILURE-web-conformance.baseline.patch` で当てます。
2. 当てた後の `conformance/baselines/ci/web.hashes.json` の md5 が `d50b4c86affd1275e59e45e3dd98d02c` になることを確かめます。
3. このファイルとパッチを消して commit します。

### パッチの作り方

README の手順どおり、同じ版の run 1 回分から丸ごと焼き、`rendered_by` が全件について正しくなるようにしました。

1. 成果物を取りました: `gh run download 36369077809 -R Tai-Kimura/jsonui-cli -n web-conformance`
2. まず `jui conformance baseline update --platform web --env ci --fail-on-moved --artifacts <dl>/artifacts/web` を実行しました。
   - 道具はファイルを書かずに拒否し、MOVED 3（chrome 27 / regular 1 / thick 17）を出しました。
   - 3 件とも、d5fdd3ad が意図して動かした effectStyle です。
3. 同じコマンドから `--fail-on-moved` を外し、`--rendered-by jsonui-cli=d5fdd3adb36b0b9b96974c6374ddc31e51debb5d` を足して、丸ごと焼きました。
4. 差分を HEAD（d5fdd3ad）と比べました。
   - hashes: changed 3 / added 0 / removed 0
   - ink: changed 3 / added 0 / removed 0
   - ほかは `rendered_by` だけです（d46b54cb → d5fdd3ad）。
5. 焼いた元の run で確かめました。
   - `jui conformance gate --platform web --env ci` は OK でした（0 fail / 0 error / visual + ratchets OK）。
   - もう一度 `--fail-on-moved` で焼くと、new 0 / same 849 / moved 0 でした。

### 注意

- このパッチは d5fdd3ad の描画です。web の描画を変える commit をこの後に積んだら、その commit の CI run から焼き直してください。
- このメモを書き足すとき: python-suite の `jui_tools/tests/test_every_bake_recipe_forces_the_review.py` は、追跡している全ファイルでこのコマンドの文字列を数えます。書くなら `--platform` と `--fail-on-moved` を同じ行に入れてください。
