# attr_codegen — typed attribute extraction generator

Generates Swift / Kotlin / Ruby typed parsers from the attribute SSoT
(`shared/core/attribute_definitions.json`). Converters consume typed
objects instead of raw JSON, which structurally eliminates key-name
typos, alias-fallback omissions, and ad-hoc type coercion bugs
(Renderer SSoT plan, pillar C).

```
jui generate attr-bindings [--lang swift|kotlin|ruby|all] [--out DIR] [--definitions PATH]
```

Default output: `build/attr_codegen/<lang>/` inside this repo (the
default directory is wiped and rewritten on each run). Writing into an
external repo (SwiftJsonUI / KotlinJsonUI) requires an explicit `--out`
— the platform-adoption phases sync from `build/` instead of coupling
repos through cross-writes.

## What is generated

| File | Content |
|---|---|
| `AttrCodegenSupport.{swift,kt}` / `attr_support.rb` | `AttrValue<T>` (value \| binding), warning hook, coercion helpers, `DimensionValue` |
| `CommonAttributes.*` | the ~143 shared attributes, emitted **once** |
| `<Component>Attributes.*` | per-component diff; embeds/merges common |
| `skipped_attributes.json` | attributes excluded from codegen, with reasons |

Guarantees:

- **Deterministic** — components/attributes sorted, no timestamps;
  regenerating always produces byte-identical output (diff-checkable).
- **Alias resolution is baked in** — `opacity` also reads `alpha`, etc.
  L1-normalized input makes it a no-op; raw JSON still works.
- **Never crashes** — unknown enum values / dimension keywords parse as
  `nil`/`null` and are reported through the warning hook
  (`AttrCodegenWarnings.handler` / `AttrWarnings.handler` /
  `JsonUI::Generated::AttrWarnings.handler=`).
- **Skips with reasons** — `callback`-typed attributes (function-valued)
  and metadata (`generatedBy`) are listed in `skipped_attributes.json`.
- Every file carries the `@generated` marker.

## Generated API shape

Swift (parses the `[String: Any]` shape used by the dynamic converters):

```swift
let attrs = LabelAttributes(json: component.rawData)
attrs.common.width          // AttrValue<DimensionValue>?
switch attrs.text {         // AttrValue<String>?
case .value(let s):   render(s)
case .binding(let e): bind(e)   // e = expression inside @{...}
case nil:             break
}
attrs.textAlign?.value      // LabelAttributes.TextAlign? (generated enum)
```

Kotlin (parses a plain `Map<String, Any?>` — **zero dependencies**;
`org.json.JSONObject.toMap()` or a small kotlinx `JsonObject` adapter
both feed it; this keeps `library-dynamic` free to change JSON libraries
without regenerating):

```kotlin
val attrs = LabelAttributes.parse(jsonMap)
attrs.common.width                       // AttrValue<DimensionValue>?
attrs.text?.valueOrNull()                // String?
attrs.text?.bindingExpressionOrNull()    // String?
```

Ruby (rjui_tools converter style — canonical-key Hash, replaces
hand-written `json['text'] || json['label']` fallbacks):

```ruby
attrs = JsonUI::Generated::LabelAttributes.extract(json)
attrs['opacity']       # AttrValue (binding-capable attrs are wrapped)
attrs['borderStyle']   # validated enum string, or absent when unknown
```

## Walkthrough: add one attribute → all 3 languages

1. Add to `shared/core/attribute_definitions.json` (e.g. under `Label`):

   ```json
   "letterSpacingMode": {
     "type": ["string", "binding"],
     "enum": ["normal", "tight"],
     "description": "Letter spacing preset"
   }
   ```

2. Regenerate: `jui generate attr-bindings --lang all`

3. Result — no hand-written parsing anywhere:
   - `swift/LabelAttributes.swift`: `public let letterSpacingMode: AttrValue<LetterSpacingMode>?` + generated enum + unknown-value warning
   - `kotlin/LabelAttributes.kt`: `val letterSpacingMode: AttrValue<LetterSpacingMode>? = null` + `enum class LetterSpacingMode`
   - `ruby/label_attributes.rb`: `{ name: 'letterSpacingMode', kind: :enum, bindable: true, values: [...] }` row

This walkthrough runs automatically in
`jui_tools/tests/test_attr_codegen_emitters.py::WalkthroughTests`
(against a temp copy of the definitions — the SSoT file itself is never
mutated by tests).

## Smoke checks

```sh
jui generate attr-bindings --lang all
swiftc -typecheck build/attr_codegen/swift/*.swift        # or -parse
kotlinc -d /tmp/out build/attr_codegen/kotlin/*.kt        # Kotlin 2.x
for f in build/attr_codegen/ruby/*.rb; do ruby -c "$f"; done
```

If `kotlinc` is not on PATH, Android Studio's bundled compiler works:

```sh
JAVA_HOME="/Applications/Android Studio.app/Contents/jbr/Contents/Home" \
  "/Applications/Android Studio.app/Contents/plugins/Kotlin/kotlinc/bin/kotlinc" \
  -d /tmp/out build/attr_codegen/kotlin/*.kt
```

Full build verification against the consuming libraries happens in the
platform-adoption phases (07/08/09) — this generator only guarantees
emit-level correctness.

## Classification reference (model.py)

| definitions `type` | kind | generated as |
|---|---|---|
| `"string"` / `"color"` | STRING / COLOR | `String` |
| `"string"` + `enum` | ENUM | language enum, unknown → nil + warning |
| `"number"` | NUMBER | `Double` (numeric `enum` lists stay plain numbers) |
| `"boolean"` | BOOLEAN | `Bool` / `Boolean` |
| `"object"` / `"array"` | OBJECT / ARRAY | `[String: Any]` / `Map<String, Any?>` … |
| `"any"` | ANY | `Any` (pass-through) |
| `["number", {"enum": [...]}, "binding"]` | DIMENSION | `DimensionValue` (number \| keyword) |
| `[..., "binding"]` | (bindable) | wrapped in `AttrValue<T>` |
| `"binding"` only | BINDING | binding-expression `String` |
| other unions (`["string","object"]` …) | RAW | `Any`, accepted kinds in doc comment |
| `"callback"` | — | skipped (see `skipped_attributes.json`) |
| `generatedBy` | — | skipped (metadata) |

Legacy enum spellings that collapse to one identifier (`"flow"` /
`"Flow"`) merge into a single case; the parser accepts every spelling
and the canonical (first-listed) one becomes the raw value.
