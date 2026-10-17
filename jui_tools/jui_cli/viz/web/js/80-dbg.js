/* ---------- browser-test hook (appended only when the server runs with JUI_VIZ_E2E=1) ---------- */
// The e2e scripts press the 3D boards through these, as the prototype's agent-test.html did.
// Demo: setSim(seconds) jumps the script. Live: setSim(factor) sets the replay speed instead (25-net.js).
window.__dbg = {
  camera, sbTile, sbPoint, SB, KB, THREE, robots,
  robotState: () => robotState,   // the model behind the robots (live: what the last slice said)
  setSim: SOURCE.mode === 'demo' ? (v) => { simT = v; prevSim = v - 0.001; } : (v) => SOURCE.setReplaySpeed(v),
};
