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
| `three-0.160.0/addons/loaders/GLTFLoader.js` | `package/examples/jsm/loaders/GLTFLoader.js` | `d073b438e6a07e1359741dd5d6c76c953420cc0d4fd84eb1bdde94315540e6a3` |
| `three-0.160.0/addons/utils/BufferGeometryUtils.js` | `package/examples/jsm/utils/BufferGeometryUtils.js` | `9be041e96308775d00e2695cc607645b9a9b64fd7c0e759dd8f7c00a8d92becb` |
| `three-0.160.0/addons/utils/SkeletonUtils.js` | `package/examples/jsm/utils/SkeletonUtils.js` | `83748c5072a5ce96e9d68d8efda908a1f1a06c0b5fd2618edc3e54a361a8fd5b` |
| `three-0.160.0/LICENSE` | `package/LICENSE` | `852e0e8699169bf9f6fdc6bda3e682d078dcbc738b5d33e74df594721bff271d` |

The import map in `index.html` points `three` and `three/addons/` here. The addons import only `three`, except
GLTFLoader, which also imports `../utils/BufferGeometryUtils.js` (vendored beside it). GLTFLoader and SkeletonUtils
(fetched 2026-10-21 from the same tarball, its sha256 checked again) read the skill spirits' .glb models
(viz/spirits.py); the page hands GLTFLoader the bytes (`parse`), never a URL.

## Mermaid 11.17.2 (MIT)

Source: the npm tarball `https://registry.npmjs.org/mermaid/-/mermaid-11.17.2.tgz` (published 2026-08-25; fetched
2026-10-19; sha256 `6ad2f42c3fc26bbf9e45cbb6d11898972573ea52b33a5f4ff51952899f950ffd`; sha1
`e3caf3717582c0e44e5d04cff043e025caec7cba` and the sha512 integrity match the registry's `dist` record). 11.x, not the
newer 12.x: the diagrams document_tools draws are written for 10 / 11.

| File here | From the tarball | sha256 |
|---|---|---|
| `mermaid-11.17.2/mermaid.min.js` | `package/dist/mermaid.min.js` | `581ed7d74bd9048d0e3a91363927d72ef22942d7722546b27f7cc29e35390eb8` |
| `mermaid-11.17.2/LICENSE` | `package/LICENSE` | `ec9fb67dcb25eccc416ed56e1aab819222c805a2a4bfe4cb19e7556bf2ffde80` |

One file (3,572,661 bytes; it sets `globalThis.mermaid`), read by `loadMermaid()` (js/20-core.js) the first time a
diagram is drawn — never when the page opens. `jui viz export-demo` leaves it out (export_demo.NOT_EXPORTED): the
demo's sheets are written by hand and draw no diagram. It
calls no `eval` / `new Function` (the CSP has no 'unsafe-eval'); its `fetch` calls are for icon packs, which the view
never registers, and the CSP's `connect-src 'self'` would stop them anyway. The view always initializes it with
`securityLevel: 'strict'` (labels sanitized; no click handlers, no scripts in a diagram) and `htmlLabels: false` (a
label is SVG text: with HTML labels, strict still keeps an `<img src>` and the page fetched it).

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
