# Attribute coverage ledger (`coverage.json`)

`jui conformance coverage` answers one question the screenshot suite cannot:

> for every declared attribute, does the platform's converter actually read it?

## Why a second check exists

Conformance compares each platform's screenshot against **that same platform's
previous screenshot**. Cross-platform pixel comparison is out of scope by
design, so a fixture whose attribute is silently dropped renders nothing,
matches its own blank baseline, and passes.

`Button.image` did exactly that. The fixture existed, all three platforms
reported ✅, and the attribute was emitted by nobody but UIKit. `View.flexWrap`
was the same story on web. Every gate was green.

This check reads the converter sources instead of the rendered output, so it
catches a dropped attribute the moment it is declared — no simulator, no
emulator, no browser.

## The ledger is a ratchet, not a TODO list

`coverage.json` records every gap that is currently accepted, with a reason.
The check fails in **both** directions:

- a gap with no entry — something was declared and nobody wired it up
- an entry whose gap is closed, or whose attribute no longer exists — the
  ledger would otherwise rot into a list of things that used to be broken

So the accepted state stays explicit and reviewable. Nothing here is a promise
to implement; it is a record of what is knowingly not implemented.

## Closing a gap

Three legitimate outcomes, in preference order:

1. **Implement it** in the platform's converter, then delete the entry.
2. **Narrow `platform` / `mode`** in `shared/core/attribute_definitions.json` if
   the attribute cannot mean anything on that platform. It stops being a gap —
   this is better than a ledger entry, because it fixes the declaration.
3. **Record it** with `jui conformance coverage --update` and set an accurate
   `reason`. Regeneration preserves reasons and notes already recorded.

### `reason` values

| reason | meaning |
|---|---|
| `platform-na` | cannot mean anything here — prefer narrowing `platform`/`mode` instead |
| `unimplemented` | should work here, nobody built it. Real debt. |
| `runtime-only` | the runtime / dynamic component applies it; codegen has nothing to emit |
| `dynamic-key` | read through a computed key, invisible to the scanner (a false gap) |
| `legacy` | kept for compatibility, intentionally not wired up (aliases land here) |

## Scope and known blind spots

**In scope**: every attribute in `attribute_definitions.json` that a Ruby
converter is expected to read, for each platform it is declared for.
Callbacks and binding-only attributes count — they are hard to *fixture*, but a
converter certainly reads them.

**Out of scope**, and deliberately so:

- **`mode: uikit` (85 attributes).** UIKit applies attributes in the
  SwiftJsonUI Swift runtime straight off the layout JSON — `SJUIButton` reads
  `attr["image"]` itself. There is no Ruby converter to scan, so every one of
  them would report as a gap. UIKit coverage is a blind spot of this check, not
  a clean result.

  **The blind spot is wider than the tag**, and this is the part that misleads:
  an attribute with *no* mode declared is still measured against the Ruby
  codegen alone, so a feature the UIKit runtime fully implements reads here as
  an iOS gap. 32 of the recorded gaps are that shape — 28 in
  `SJUI*` / `SJUIViewCreator`, 4 in the KotlinJsonUI dynamic components — and
  each carries a `note` naming the surface. So read a gap as **"the codegen
  does not emit this"**, never as "the platform cannot do this": the two differ
  by a working reference implementation.
- **`mode: dynamic-only`**, deprecated attributes, and definition metadata
  (`type`, `id`, `child`, `$jui`, …), classified by the same taxonomy the
  fixture generator uses (`conformance/rules.py`).

**Detection is a source scan**, so it is deliberately biased: a read form the
scanner does not know reads as a gap. False gaps are recoverable (record them
with `reason: dynamic-key`); a missed gap is not. Known read forms are the
bracket lookup, `attr_with_alias` / `attr_lookup`, and `dig` / `fetch` /
`key?`.

## The other half: does the attribute *do* anything? (`control_diff.json`)

The source scan proves a converter **reads** the attribute. It cannot prove the
emitted code has any effect — a converter that reads `maxZoom` and emits
`// maxZoom: … - Consider using MagnificationGesture` counts as covered here.

`jui conformance effect` closes that from the output side. For every visual
fixture the generator also emits a **control**: the same layout with the
attribute under test removed. If the fixture renders identically to its
control, nothing the attribute asked for happened.

Two things make this trustworthy where the baseline check is blind:

- **No baseline is involved.** Both screenshots come from the same run on the
  same device, so simulator drift, OS upgrades and font changes cancel out. The
  iOS runner moving 18.6 → 26.2 invalidated every baseline hash; it would not
  have touched a single fixture-vs-control verdict.
- **No cross-platform comparison is involved.** That stays out of scope. The
  question is only "did *this* platform react to the attribute".

One control serves every fixture sharing its shape (`host` + anchor), so ~30
controls cover all 600 visual fixtures rather than doubling the suite.

`control_diff.json` is the ratchet, same shape as `coverage.json`: it lists the
fixtures asserted to differ from their control. A listed fixture that stops
differing fails the build. A fixture that renders identically and is **not**
listed is reported but does not fail — an attribute whose fixture value happens
to equal the platform default (`enabled: true`, a colour matching the theme)
cannot differ, and failing on that is how a check ends up switched off.

So implementing an attribute has three steps, not one: make the converter emit
it, delete its `coverage.json` entry, and record its fixture in
`control_diff.json`.

## Commands

```sh
jui conformance coverage                     # check (CI gate)
jui conformance coverage --platform web      # one platform
jui conformance coverage --update            # rewrite the ledger, keeping reasons

jui conformance effect --platform web            # check (CI gate, needs artifacts)
jui conformance effect --platform web --update    # record what currently differs
```

`coverage` runs in the `ssot-guards` job of `ci.yml`, next to the other drift
guards on `attribute_definitions.json`. `effect` runs in the report job of
`conformance-mobile.yml`, where all three platforms' artifacts are available.
