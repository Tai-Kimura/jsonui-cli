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
- The device pane lists nothing: stand-ins for `xcrun` and `adb` that report no device are first on the server's
  PATH (the machine's simulators are not part of the sample).
- **The cursor is an overlay.** The plan (§2.6) shows the mouse. Headless Chromium draws none, so the driver adds one
  small arrow element (`#promo-cursor`) at the position of the mouse it drives. It is the only thing in the frames
  the app did not draw.
- 1a / 1b (`term.py`): the editor shows real files of a demo-shop copy; the terminal types the real gates and shows
  what they printed in that copy, with colour codes taken out and the copy's absolute path written relative to it.
  The prompt is `demo-shop $`. `gates.json` beside the frames keeps each command and its output.

## Frames and the clock

Frame 0 is the chapter's start; there are (end − start) × 30 frames, the bounds read from `jsonui-promo/src/timeline.json`
(`run.py` stops when they moved from the ones the script was written for). The page's clock is Playwright's
(`page.clock.install`): the page animates only when the driver runs it, 1/30 s per frame. Hooks and the server run
in real time; after an event the driver waits for the page to take it in before the next frame. The sky shows
`--sky-time` (default 14:00) through `__dbg.setClock`.

A chapter whose feature the tree lacks (the flow player for 4, the cost view for 5, the language switch for
`--lang en`) is reported and skipped. Each chapter writes `manifest.json` (events and the frame each fired on,
warnings, console lines); the run writes `<out>/<lang>/run.json`.
