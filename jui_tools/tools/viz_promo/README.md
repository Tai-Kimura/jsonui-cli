# viz_promo — the promo video's real-app frames

Captures the chapters of the JsonUI promo video (plan `docs/plans/2026-10-21-promo-video-plan.md`, ticket
`docs/bugs/2026-10-21-viz-promo-replay-and-capture-tool.md`) as numbered PNG frames for the Remotion project
`jsonui-promo` (`public/captures/<lang>/<chapter>/00000.png …`, read by its `CaptureSlot`).

```
python tools/viz_promo/run.py --lang ja --chapters hook,2,3,4 --jui-root PATH [--out DIR] [--promo PATH]
```

Run it with the Python the viz e2e uses (Playwright, Chromium and the server's dependencies). It waits for the viz
e2e's machine lock, so it never runs beside a browser-test run.

## What is real and what is a sample

- The app is real: `jui viz serve` of `--jui-root` in a throwaway HOME on a free port, the page it serves, the 3D it
  draws. The hooks go through the real `forward.py`; a question's `forward.py --ask` really waits until the driver
  presses the answer on the page.
- The data is a sample (`timeline.py`): fictional rooms (`demo-shop`, a copy of the jsonui-demo-shop workdir;
  `demo-admin`, `demo-docs`), 15 sessions, their names, prompts, commands, the question, the talk and the test cases
  — every word from `WORDS[lang]`.
- The relay is connected as the plugin connects it: each session's process is a stand-in (it only sleeps) whose argv carries `--dangerously-load-development-channels plugin:jui-viz@jsonui`, and the script does what the plugin's `channel.py` does for it — `POST /channel/hello` (session id, that process as ppid, `accepts: ["prompt"]`, `via: "plugin"`), a long poll on `/channel/poll`, and a permission prompt as `POST /channel/request` — so the page shows every session relay-connected; nothing in the viz is changed.
- The device pane lists nothing: stand-ins for `xcrun` and `adb` that report no device are first on the server's
  PATH (the machine's simulators are not part of the sample).
- **The cursor is an overlay.** The plan (§2.6) shows the mouse. Headless Chromium draws none, so the driver adds one
  small arrow element (`#promo-cursor`) at the position of the mouse it drives. It is the only thing in the frames
  the app did not draw.
- 1a / 1b (`term.py`): the editor shows real files of a demo-shop copy, and the cart screen's spec document, made at
  capture time by `jsonui-doc generate spec … --format html` into a temporary folder that is deleted once read; it is
  shown rendered (the HTML has no @generated header to show as source). The terminal types the real gates (build,
  verify, lint-strings, web branch-tests --check, validate, doc check) and shows what they printed in that copy, with
  colour codes taken out and the copy's absolute path written relative to it. The prompt is `demo-shop $`.
  `gates.json` beside the frames keeps each command and its output.
  1b starts with one drift made in the copy before the window opens (`term.DRIFT`: the cart layout binds `totalPrice`,
  which its spec does not declare, and `verify.external` is `"gate"`), so the first `jui verify --fail-on-diff` reports
  the finding and fails; `git restore` takes the layout back and the second verify passes.
- **5-json is a window segment.** Chapter 5 opens on the load definition (`docs/infra/load/weekend-campaign.json` of
  the copy; for `--lang en` the copy's file is `tools/make_load.py --lang en`'s output) in the editor window, 74–77 s,
  captured to `captures/<lang>/5-json/` (90 frames, frame 0 = 74 s). The promo frames it as a window, then shows
  `captures/<lang>/5/` from its frame 90 on: chapter 5's own capture still covers 74–88 s, and its cost page starts
  after 77 s. Capturing 5 captures 5-json too.

- **1b-board is the page beside 1b's terminal.** The promo shows chapter 1b split: the terminal (`captures/<lang>/1b/`)
  on the left half and the viz page (`captures/<lang>/1b-board/`) on the right half, both taken at `SPLIT_VIEWPORT`
  (1125x1012, shown at 900x810). The board is the real whiteboard of demo-shop's cart spec: before frame 0 the file is
  left with its metadata only (`spec_reset`) and the sheet is opened from the spec list; then each `spec_write` is a
  real Write of the real file with one more section, as demo-shop has it, with the hooks a Write sends around it. The
  server reads the file (the hook's path and its watcher) and the open sheet fills in. Capturing 1b captures
  1b-board too.

## Frames and the clock

Frame 0 is the chapter's start; there are (end − start) × 30 frames, the bounds read from `jsonui-promo/src/timeline.json`
(`run.py` stops when they moved from the ones the script was written for). The page's clock is Playwright's
(`page.clock.install`): the page animates only when the driver runs it, 1/30 s per frame. Hooks and the server run
in real time; after an event the driver waits for the page to take it in before the next frame. The sky shows
`--sky-time` (default 14:00) through `__dbg.setClock`.

## Measuring the floor

`run.py --measure-fps --lang ja --jui-root PATH --out DIR` starts the floor with all 30 robots on the page's own clock
(no fake clock), records every frame's time through `__dbg.afterFrame` (the hook `frame_gaps.py` uses) for 10 s on the
whole floor and 10 s up close on demo-shop, and prints p50 / p90 / max of the intervals in ms
(`DIR/fps-<lang>.json`). Headless Chromium under the e2e's software GL, 1920x1080.

A chapter whose feature the tree lacks (the flow player for 4, the cost view for 5, the language switch for
`--lang en`) is reported and skipped. Each chapter writes `manifest.json` (events and the frame each fired on,
warnings, console lines); the run writes `<out>/<lang>/run.json`.
