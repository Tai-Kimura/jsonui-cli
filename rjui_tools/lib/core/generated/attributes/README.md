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

Placement note: the 06 plan default is
`{s,k,r}jui_tools/lib/core/generated/attributes/`; rjui is the pilot and
uses exactly that layout so sjui/kjui can mirror it later.
