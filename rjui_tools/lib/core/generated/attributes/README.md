# Generated typed attribute extraction (Ruby)

Everything in this directory except this README is **@generated** from
`shared/core/attribute_definitions.json` by the attr-codegen emitter.
Do not edit by hand.

Regenerate (from the jsonui-cli repo root):

```sh
jui generate attr-bindings --lang ruby --out rjui_tools/lib/core/generated/attributes
```

Consumers: `rjui_tools/lib/core/typed_attributes.rb` (the converter-facing
bridge) and, through it, `BaseConverter#attributes` in
`rjui_tools/lib/react/converters/`.

Public API surface (documented contract — see the generator README,
`jui_tools/jui_cli/generators/attr_codegen/README.md`, for full details):

- `Module.extract(hash, canonical_only: false)` — canonical-key Hash;
  `canonical_only: true` disables alias fallback for L1-normalized input.
- `Module.rows` / `Module.declared?(key)` / `Module.alias_map` — the
  declared-attribute metadata contract (common rows merged first,
  component rows override; alias spellings that are also declared rows
  are never redirected).
- Binding-capable and binding-only values come back as
  `JsonUI::Generated::AttrValue` (`value` XOR `binding_expression`;
  `#raw` recovers the original layout representation, including `@{}`
  wrappers and action-object Hashes).
- Enum matching is lenient: case-insensitive, unknown values warn via
  `JsonUI::Generated::AttrWarnings` and pass through raw.

Placement note: the 06 plan default is
`{s,k,r}jui_tools/lib/core/generated/attributes/`; rjui is the pilot and
uses exactly that layout so sjui/kjui can mirror it later.
