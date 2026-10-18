/* ---------- browser-test hook (appended only when the server runs with JUI_VIZ_E2E=1) ---------- */
// The e2e scripts press the 3D boards through these, as the prototype's agent-test.html did.
// Demo: setSim(seconds) jumps the script. Live: setSim(factor) sets the replay speed instead (25-net.js).
window.__dbg = {
  camera, sbTile, sbPoint, SB, KB, THREE, robots,
  robotState: () => robotState,   // the model behind the robots (live: what the last slice said)
  // play (10-18): the arms shorten the times; the real defaults stay in 40-scene.js
  play: (opts) => { if (opts) { Object.assign(PLAY, opts, { next: 0 }); if ('restMaxSec' in opts) robots.forEach((R) => { R.restUntil = 0; }); if (opts.endAll) [...PLAY.list].forEach(playEnd); } return { list: PLAY.list.map((G) => ({ room: G.room, kind: G.kind, players: G.players.map((R) => R.def.id), started: !!G.t0,
    ball: G.ball ? [+G.ball.position.x.toFixed(2), +G.ball.position.y.toFixed(2)] : null })),
    robots: robots.map((R) => ({ id: R.def.id, play: R.play ? R.play.phase : null, back: !!R.playBack, vis: R.robot.state, lamp: R.robot.lampState || R.robot.state, pose: R.robot.play ? R.robot.play.kind : null, rps: !!(R.robot.rps && R.robot.rps.visible),
      x: +R.robot.root.position.x.toFixed(2), z: +R.robot.root.position.z.toFixed(2), seat: R.def.pos, room: R.def.room, path: R.path.length })) }; },
  calls: () => robots.map((R) => ({ id: R.def.id, call: R.robot.call ? { role: R.robot.call.role, state: R.robot.call.state, peer: R.robot.call.peer } : null,
    handset: !!R.robot.handset, ring: !!(R.robot.ring && R.robot.ring.visible), tag: R.callText || '', state: R.robot.state })),   // phone calls (10-18)
  model: () => latestModel,       // what the panels and boards draw from
  live3d: () => (SOURCE.mode === 'live' ? LIVE3D : null),   // the live rooms' boards
  links: () => links,             // the robot → board lines
  room: (id) => { const r = PROJECT[id]; return r ? { x0: r.x0, x1: r.x1, z0: r.z0, z1: r.z1, shown: !!r.shown, doors: r.doors || null } : null; },
  walls: () => (SOURCE.mode === 'live' ? liveWalls() : null),   // the wall pieces, door gaps cut out (the e2e checks no robot is in one)
  seats: () => (SOURCE.mode === 'live' ? JSON.parse(JSON.stringify(LIVE.seatOf)) : null),
  solo: () => (SOURCE.mode === 'live' ? liveSolo() : null),
  // the usage chips as drawn (10-18): per window its text, the number's and the %'s colours, 上限到達, the note
  usage: () => [...document.querySelectorAll('#usage .uw')].map((e) => ({ window: e.dataset.window || null, text: e.textContent,
    num: e.querySelector('.num') ? getComputedStyle(e.querySelector('.num')).color : null,
    pc: e.querySelector('.pc') ? getComputedStyle(e.querySelector('.pc')).color : null,
    limit: !!e.querySelector('.limit'), limitColor: e.querySelector('.limit') ? getComputedStyle(e.querySelector('.limit')).color : null,
    note: e.querySelector('.note') ? e.querySelector('.note').textContent : '' })),
  usageHue: SOURCE.mode === 'live' ? usageHue : null,
  usageColor: SOURCE.mode === 'live' ? usageColor : null,   // (pct, dark) → the colour the header would use
  inkSoft: () => { const e = document.createElement('span'); e.style.color = 'var(--ink-soft)'; document.body.append(e); const c = getComputedStyle(e).color; e.remove(); return c; },
  floors: () => ({ floors: LIVE.floors, floor: LIVE.floor, rank: LIVE.rank, tower: TOWER.on, look: TOWER.look }),
  beats: () => (SOURCE.mode === 'demo' ? DEMO_BEATS : null),
  director: () => ({ userAt: DIRECTOR.userAt }),
  condition: (id) => robotCondition(id),
  assignFloors: SOURCE.mode === 'live' ? assignFloors : null,
  goFloor: SOURCE.mode === 'live' ? liveFloorStep : null,
  tower: (on) => (on ? towerEnter() : towerLeave(LIVE.floor)),
  // What a press at (x, y) on the canvas hits in the building — the same ray and towerHit the pointer uses.
  towerAt: (x, y) => {
    if (!TOWER.on) return null;
    const r = document.getElementById('scene-canvas').getBoundingClientRect(), ray = new THREE.Raycaster();
    ray.setFromCamera(new THREE.Vector2(((x - r.left) / r.width) * 2 - 1, -((y - r.top) / r.height) * 2 + 1), camera);
    const h = towerHit(ray);
    return h ? { k: h.k, project: h.project } : null;
  },
  project: () => UI.project,
  towerDistance: () => { const want = towerPose(); return { at: +camera.position.distanceTo(want.t).toFixed(1), want: +want.p.distanceTo(want.t).toFixed(1) }; },
  towerActors: () => (TOWER.actors ? Object.fromEntries(Object.entries(TOWER.actors).map(([k, m]) => [k, m.count])) : null),
  towerLook: (k) => { const y = towerY(k), t = new THREE.Vector3(0, y, TOWER.D / 2); flyTo(t.clone().add(new THREE.Vector3(2, 1.5, 30)), t, controls.target, 0, () => { controls.target.copy(t); controls.update(); }); },
  setClock: (ms) => { VIZ_CLOCK.at = ms; },
  sky: () => ({ phase: sceneEl.dataset.sky || '', background: sceneEl.style.background }),
  snack: SOURCE.mode === 'live' ? (o) => { Object.assign(SNACK, o || {}); SNACK.rng = null; SNACK.next = 0; } : null,
  gestures: () => robots.map((R) => ({ id: R.def.id, state: R.robot.state, gesture: R.robot.gesture ? R.robot.gesture.kind : null, tired: !!R.robot.tired, drinks: R.robot.drinks || 0,
    heavy: !!R.robot.heavy, sweat: !!(R.robot.sweat && R.robot.sweat.visible), act: R.text ? R.text.textContent : '', actShown: R.text ? getComputedStyle(R.text).display !== 'none' : false })),
  towerLines: (text) => { const f = towerNameFit(makeCanvas(8, 8).getContext('2d'), text, towerBays()[0].w - 8); return [f.size, ...f.lines]; },
  openRobot: (id) => openRobot(id, document.getElementById('scene-canvas')),
  renderInfo: () => (renderer ? { calls: renderer.info.render.calls, triangles: renderer.info.render.triangles, geometries: renderer.info.memory.geometries, textures: renderer.info.memory.textures } : null),
  setSim: SOURCE.mode === 'demo' ? (v) => { simT = v; prevSim = v - 0.001; } : (v) => SOURCE.setReplaySpeed(v),
};
