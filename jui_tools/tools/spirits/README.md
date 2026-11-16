# tools/spirits — writing skill-spirit models

A skill spirit (ticket 2026-10-21-jui-viz-skill-spirit) is a folder of .glb files and a spirit.json that viz reads
from `<viz home>/spirits/<name>/` (or config.json's `spiritsDir`). This tool writes those .glb files from a model
built with three.js, so a model can be made as code and kept reproducible:

    python tools/spirits/export.py tools/spirits/models/gear-giant --out jui_cli/viz/web/spirits/gear-giant --preview /tmp/prev

- `build.js` (the contract is in export.py's docstring) returns the spirit, the robot's parts and props, the clip
  lengths and `animate(t, clip)`. Each clip is sampled at 30 fps into position / rotation / scale tracks; a bend is
  made with bones (a SkinnedMesh), which glTF carries.
- What glTF has no place for is refused with its reason: a Sprite (use spirit.json `effects`, `shouts` or `bubble`),
  a ShaderMaterial (the see-through look is spirit.json `spirit.material`, drawn by viz), a node that shows and
  hides (scale it to 0).
- Every written .glb is read back with the page's GLTFLoader and drawn beside what was built at a quarter, half and
  three quarters of each clip; `--preview` keeps the pictures. The folder is then checked as viz reads it
  (`python -m jui_cli.viz.spirits <folder>`).

Needs Playwright and its Chromium (as tools/viz_e2e).

## What is here

- `models/ink-scholar`, `models/gear-giant`: the two bundled models (original works). Their written folders are
  `jui_cli/viz/web/spirits/<name>/`; write them again after changing a build.js or spirit.json (the tests compare
  the copied spirit.json and check the written folder).
- `vendor/`: three 0.160.0's GLTFExporter, for this tool only (VENDOR.md).

Only original works go in this repository. A model made after someone else's work is kept in the person's own
spirits folder, not here and not in the tests.
