# Vendored files

The view loads nothing from outside: three.js and the monospace font ship here and are served by `jui viz serve`
from the package (`importlib.resources`). Fetched once by hand on 2026-10-18; to update, fetch the same way and
replace the sha256 lines.

## three.js 0.160.0 (MIT)

Source: the npm tarball `https://registry.npmjs.org/three/-/three-0.160.0.tgz`
(sha256 `1ee2f935c4f555814b388e87b5ef78a44856bd2e9d0feb88643a6e193fb42856`; sha1 `cd1e4dbd01aee0719280a9086d75545db52b7a8f`
and the sha512 integrity match the registry's `dist` record).

| File here | From the tarball | sha256 |
|---|---|---|
| `three-0.160.0/three.module.min.js` | `package/build/three.module.min.js` | `3e690ac7d180b0aadf0891bea39eec643e29e2d3e75c99b18689518665f69ba6` |
| `three-0.160.0/addons/controls/OrbitControls.js` | `package/examples/jsm/controls/OrbitControls.js` | `5a44a9e86a2a0fb11933eed69bc2cd33c76a496854c1aed6ed776efa87d7b064` |
| `three-0.160.0/addons/geometries/RoundedBoxGeometry.js` | `package/examples/jsm/geometries/RoundedBoxGeometry.js` | `d20aeaf7077c459a8d952d215738d7b44fba028440bb862d84b622a34f0c80bb` |
| `three-0.160.0/LICENSE` | `package/LICENSE` | `852e0e8699169bf9f6fdc6bda3e682d078dcbc738b5d33e74df594721bff271d` |

The import map in `index.html` points `three` and `three/addons/` here. The two addons import only `three`.

## JetBrains Mono 2.304 (SIL OFL 1.1)

Source: the official release `https://github.com/JetBrains/JetBrainsMono/releases/download/v2.304/JetBrainsMono-2.304.zip`
(sha256 `6f6376c6ed2960ea8a963cd7387ec9d76e3f629125bc33d1fdcd7eb7012f7bbf`).

| File here | From the zip | sha256 |
|---|---|---|
| `../fonts/JetBrainsMono-Medium.woff2` | `fonts/webfonts/JetBrainsMono-Medium.woff2` | `086c48dfbea9ddaff1320f7e09399b8e2924e88ce67453721255db3bdbb5a353` |
| `../fonts/JetBrainsMono-Bold.woff2` | `fonts/webfonts/JetBrainsMono-Bold.woff2` | `c503cc5ec5f8b2c7666b7ecda1adf44bd45f2e6579b2eba0fc292150416588a2` |
| `../fonts/OFL.txt` | `OFL.txt` | `30f0c136e3c88e422d0791acd97238870f9054a9729bc34cf2ff0d4ed8cac4ad` |

Japanese text uses the OS fonts (`"BIZ UDPGothic", "Hiragino Sans", "Yu Gothic", sans-serif`); BIZ UDPGothic and
Dela Gothic One are used when installed.
