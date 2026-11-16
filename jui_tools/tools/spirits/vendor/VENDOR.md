# Vendored for the export tool only

Not part of the package and never served by `jui viz`: export.py's page uses them to write .glb files. From the
same npm tarball as the view's three (`https://registry.npmjs.org/three/-/three-0.160.0.tgz`, sha256
`1ee2f935c4f555814b388e87b5ef78a44856bd2e9d0feb88643a6e193fb42856`), fetched 2026-10-21. MIT, as
`jui_cli/viz/web/vendor/three-0.160.0/LICENSE`.

| File here | From the tarball | sha256 |
|---|---|---|
| `exporters/GLTFExporter.js` | `package/examples/jsm/exporters/GLTFExporter.js` | `f8a6eb87719e68c925fdf445014b5ead49cf779ae14e69c6cc1cb1dd4eae514d` |
| `utils/TextureUtils.js` | `package/examples/jsm/utils/TextureUtils.js` | `1b84a7fde8745dd614f62b6ca8108b592144278c07891a0cbe8cdf8e15796efa` |

GLTFExporter imports `../utils/TextureUtils.js`; both import only `three`.
