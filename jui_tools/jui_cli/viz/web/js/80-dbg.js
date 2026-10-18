/* ---------- browser-test hook (appended only when the server runs with JUI_VIZ_E2E=1) ---------- */
// The e2e scripts press the 3D boards through these, as the prototype's agent-test.html did.
// Demo: setSim(seconds) jumps the script. Live: setSim(factor) sets the replay speed instead (25-net.js).
window.__dbg = {
  camera, sbTile, sbPoint, SB, KB, THREE, robots,
  robotState: () => robotState,   // the model behind the robots (live: what the last slice said)
  model: () => latestModel,       // what the panels and boards draw from
  live3d: () => (SOURCE.mode === 'live' ? LIVE3D : null),   // the live rooms' boards
  links: () => links,             // the robot → board lines
  room: (id) => { const r = PROJECT[id]; return r ? { x0: r.x0, x1: r.x1, z0: r.z0, z1: r.z1, shown: !!r.shown } : null; },
  floors: () => (SOURCE.mode === 'live' ? { floors: LIVE.floors, floor: LIVE.floor, rank: LIVE.rank, tower: TOWER.on } : null),
  assignFloors: SOURCE.mode === 'live' ? assignFloors : null,
  goFloor: SOURCE.mode === 'live' ? liveFloorStep : null,
  tower: SOURCE.mode === 'live' ? (on) => (on ? towerEnter() : towerLeave(LIVE.floor)) : null,
  renderInfo: () => (renderer ? { calls: renderer.info.render.calls, triangles: renderer.info.render.triangles, geometries: renderer.info.memory.geometries, textures: renderer.info.memory.textures } : null),
  setSim: SOURCE.mode === 'demo' ? (v) => { simT = v; prevSim = v - 0.001; } : (v) => SOURCE.setReplaySpeed(v),
};
