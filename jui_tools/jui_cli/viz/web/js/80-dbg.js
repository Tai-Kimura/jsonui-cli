/* ---------- browser-test hook (appended only when the server runs with JUI_VIZ_E2E=1) ---------- */
// The e2e scripts press the 3D boards through these, as the prototype's agent-test.html did.
// Demo: setSim(seconds) jumps the script. Live: setSim(factor) sets the replay speed instead (25-net.js).
window.__dbg = {
  camera, sbTile, sbPoint, SB, KB, THREE, robots,
  robotState: () => robotState,   // the model behind the robots (live: what the last slice said)
  // the outside (10-18): the arms force a season ('spring' …) or a weather ({ kind, isDay }); null gives it back
  outside: (opts) => {
    if (opts && 'season' in opts) OUTSIDE.force = opts.season;
    if (opts && 'weather' in opts) OUTSIDE.weatherForce = opts.weather;
    const g = TOWER.group;
    const find = (name) => (g ? g.children.find((o) => o.userData.outside === name) : null);
    const crowns = find('crowns'), c = new THREE.Color();
    return { season: season(), weather: weatherNow(), built: TOWER.outside || null, sky: sceneEl.dataset.sky || '',
      fall: TOWER.fall ? { kind: TOWER.fall.kind, n: TOWER.fall.n } : null, fog: !!scene.fog,
      crown: crowns && crowns.instanceColor ? '#' + (crowns.getColorAt(0, c), c.getHexString()) : null,
      branches: !!find('branches'), cicadas: find('cicadas') ? find('cicadas').count : 0, roofSnow: !!find('roofSnow'),
      ground: find('plaza') ? '#' + find('plaza').material.color.getHexString() : null,
      fallY: TOWER.fall ? Array.from({ length: Math.min(5, TOWER.fall.n) }, (_, i) => +TOWER.fall.pos[i * 3 + 1].toFixed(3)) : [] };
  },
  // play (10-18): the arms shorten the times; the real defaults stay in 40-scene.js
  play: (opts) => { if (opts) { if (opts.solo) Object.assign(SOLO, opts.solo, { next: 0 }); Object.assign(PLAY, opts, { next: 0 }); if ('restMaxSec' in opts) robots.forEach((R) => { R.restUntil = 0; }); if (opts.endAll) [...PLAY.list].forEach(playEnd); } return { ends: PLAY.ends.slice(), list: PLAY.list.map((G) => ({ room: G.room, kind: G.kind, players: G.players.map((R) => R.def.id), started: !!G.t0,
    ball: G.ball ? [+G.ball.position.x.toFixed(2), +G.ball.position.y.toFixed(2)] : null })),
    robots: robots.map((R) => ({ id: R.def.id, play: R.play ? R.play.phase : null, back: !!R.playBack, vis: R.robot.state, lamp: R.robot.lampState || R.robot.state, pose: R.robot.play ? R.robot.play.kind : null, rps: !!(R.robot.rps && R.robot.rps.visible),
      solo: R.solo ? R.solo.kind : null, zzz: !!(R.robot.zzz && R.robot.zzz.visible), bento: !!(R.robot.bento && R.robot.bento.visible), desk: !!(R.robot.desk && R.robot.desk.visible), seatKey: R.seatKey, tag: R.callText || '',
      x: +R.robot.root.position.x.toFixed(2), z: +R.robot.root.position.z.toFixed(2), seat: R.def.pos, room: R.def.room, path: R.path.length })) }; },
  rps: { round: rpsRound, T: RPS_T },   // じゃんけん's rounds (2.3.3): the arm finds a tie and reads the round after it
  towerPlay: () => TOWER.floors.map((F) => F.bays.map((b) => b.play || '')),   // a game's name on its window (2.3.3)
  calls: () => robots.map((R) => ({ id: R.def.id, call: R.robot.call ? { role: R.robot.call.role, state: R.robot.call.state, peer: R.robot.call.peer } : null,
    handset: !!R.robot.handset, ring: !!(R.robot.ring && R.robot.ring.visible), tag: R.callText || '', state: R.robot.state })),   // phone calls (10-18)
  model: () => latestModel,       // what the panels and boards draw from
  live3d: () => (SOURCE.mode === 'live' ? LIVE3D : null),   // the live rooms' boards
  links: () => links,             // the robot → board lines
  room: (id) => { const r = PROJECT[id]; return r ? { x0: r.x0, x1: r.x1, z0: r.z0, z1: r.z1, shown: !!r.shown, doors: r.doors || null } : null; },
  walls: () => (SOURCE.mode === 'live' ? liveWalls() : null),   // the wall pieces, door gaps cut out (the e2e checks no robot is in one)
  seats: () => (SOURCE.mode === 'live' ? JSON.parse(JSON.stringify(LIVE.seatOf)) : null),
  solo: () => (SOURCE.mode === 'live' ? liveSolo() : null),
  // the room up close (10-18): what is placed, where the vacuum is, the boxes it keeps clear of, and three's counts
  props: () => {
    const R = PROPS.room ? LIVE3D.rooms[PROPS.room] : null, v = PROPS.vac, sv = PROPS.server;
    return { room: PROPS.room, server: sv ? [+sv.position.x.toFixed(2), +sv.position.z.toFixed(2)] : null,
      vac: v ? [+v.position.x.toFixed(3), +v.position.z.toFixed(3)] : null, radius: PROPS.radius, boxes: PROPS.boxes,
      area: PROPS.room ? propsArea() : null, wood: !!(R && R.floor.material === PROPS.woodMat && PROPS.woodMat && PROPS.woodMat.map),
      floorMap: Object.values(LIVE3D.rooms).some((x) => !!x.floor.material.map), sceneChildren: scene.children.length - robots.length,   // less the robots, which come and go
      memory: { ...renderer.info.memory } };
  },
  // breaks (10-19): the arms shorten the times (the real defaults stay in 40-scene.js); where the props stand, for a room
  // as it is or for any rectangle and doors (the arms try every size the layout makes); who is on a break
  brk: (opts) => {
    if (opts) { Object.assign(BRK, opts, { next: 0 }); if (opts.p) BRK.p = { ...opts.p }; if ('restMaxSec' in opts) robots.forEach((R) => { R.restUntil = 0; }); if (opts.endAll) robots.forEach((R) => { if (R.brk) brkStop(R, 'e2e', performance.now() / 1000); }); }
    const P = PROPS.place;
    const top = (o) => { if (!o) return null; const b = new THREE.Box3(); o.updateMatrixWorld(true); o.traverseVisible((m) => { if (m.isMesh) b.expandByObject(m, true); }); return [+b.min.y.toFixed(3), +b.max.y.toFixed(3)]; };
    const xz = (o) => { if (!o) return null; const b = new THREE.Box3(); o.updateMatrixWorld(true); o.traverseVisible((m) => { if (m.isMesh) b.expandByObject(m, true); }); return [b.min.x, b.max.x, b.min.z, b.max.z].map((v) => +v.toFixed(3)); };
    return { ends: BRK.ends.slice(), place: P ? JSON.parse(JSON.stringify(P)) : null, meshBoxes: { booth: xz(PROPS.booth), vend: xz(PROPS.vend), server: xz(PROPS.server) }, heights: { vend: top(PROPS.vend), robots: robots.filter((R) => R.robot.root.visible).map((R) => [R.def.id, top(R.robot.root), !!(R.robot.desk && R.robot.desk.visible)]) },
      deskBoxes: robots.filter((R) => R.def.room === PROPS.room && !R.brk && !R.playBack && !R.path.length && R.robot.root.visible).map((R) => [R.def.id, xz(R.robot.root)]), built: { booth: !!PROPS.booth, vend: !!PROPS.vend, fan: PROPS.fan ? +PROPS.fan.rotation.z.toFixed(2) : null },
      smoke: PROPS.smoke.filter((q) => q.s.visible).length, puffs: PROPS.smoke.filter((q) => q.s.visible).map((q) => [...q.s.position.toArray().map((v) => +v.toFixed(2)), +q.s.scale.x.toFixed(2), +q.s.material.opacity.toFixed(2)]), smokeMax: PROPS.smoke.length,
      robots: robots.map((R) => ({ id: R.def.id, kind: R.brk ? R.brk.kind : null, phase: R.brk ? R.brk.phase : null, at: !!R.robot.brk, back: !!R.playBack,
        hand: R.robot.brkHandKind || null, tag: R.callText || '', vis: R.robot.state, lamp: R.robot.lampState || R.robot.state, desk: !!(R.robot.desk && R.robot.desk.visible),
        play: !!R.play, solo: R.solo ? R.solo.kind : null, x: +R.robot.root.position.x.toFixed(3), z: +R.robot.root.position.z.toFixed(3), seat: R.def.pos, room: R.def.room, path: R.path.length })) };
  },
  propsPlace: (r) => propsPlace(r),
  seatGeom: () => ({ SEAT: JSON.parse(JSON.stringify(SEAT)), SEAT_SOLO: { ...SEAT_SOLO }, SOLO_GROW, DOOR_W, roomSize: [1, 7, 11].map(roomSize), doorAt: doorAt({ x0: 0, x1: 0, z0: 0, z1: 0 }) }),
  // the usage chips as drawn (10-18): per window its text, the number's and the %'s colours, 上限到達, the note
  usage: () => [...document.querySelectorAll('#usage .uw')].map((e) => ({ window: e.dataset.window || null, text: e.textContent, title: e.title,
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
  sky: () => ({ phase: (sceneEl.dataset.sky || '').split(':')[0], background: sceneEl.style.background }),
  snack: SOURCE.mode === 'live' ? (o) => { Object.assign(SNACK, o || {}); SNACK.rng = null; SNACK.next = 0; } : null,
  gestures: () => robots.map((R) => ({ id: R.def.id, state: R.robot.state, gesture: R.robot.gesture ? R.robot.gesture.kind : null, tired: !!R.robot.tired, drinks: R.robot.drinks || 0,
    heavy: !!R.robot.heavy, sweat: !!(R.robot.sweat && R.robot.sweat.visible), act: R.text ? R.text.textContent : '', actShown: R.text ? getComputedStyle(R.text).display !== 'none' : false })),
  towerLines: (text) => { const f = towerNameFit(makeCanvas(8, 8).getContext('2d'), text, towerBays()[0].w - 8); return [f.size, ...f.lines]; },
  openRobot: (id) => openRobot(id, document.getElementById('scene-canvas')),
  // the camera on a robot (10-18): its orbit, how its view was chosen, and what stands in the way now
  focus: () => {
    const R = rbState.id ? robots.find((x) => x.def.id === rbState.id) : null;
    const now = R ? [...focusBlockers(R, camera.position)] : [];
    return { id: FOCUS.id, az: +FOCUS.az.toFixed(4), el: +FOCUS.el.toFixed(4), dist: +FOCUS.dist.toFixed(3), chosen: FOCUS.chosen,
      cam: camera.position.toArray().map((v) => +v.toFixed(3)), zoomed: zoom.zoomed, tween: !!camTween,
      blockersNow: now.length, blockersFaded: now.filter((o) => FOCUS.faded.has(o)).length, faded: FOCUS.faded.size,
      fadedOpacity: [...FOCUS.faded.keys()].map((o) => [].concat(o.material)[0].opacity) };
  },
  // the arm turns the camera back to the usual direction, as a drag would (to see the faint walls)
  focusSet: (o) => { if ('az' in o) FOCUS.az = o.az; if ('el' in o) FOCUS.el = o.el; if ('dist' in o) FOCUS.dist = o.dist; return { az: FOCUS.az, el: FOCUS.el }; },
  focusBase: () => ({ ...FOCUS_BASE }),
  // the faint meshes: whether still in the scene, their room, whether their own material is a shared one; and a mark
  // on each own material's dispose (the arm sees whether taking a room down disposes it)
  fadedInfo: () => (liveShared(), [...FOCUS.faded.entries()]).map(([o, mat]) => {
    let inScene = false; for (let x = o; x; x = x.parent) if (x === scene) inScene = true;
    const room = Object.keys(LIVE3D.rooms).find((id) => { let hit = false; LIVE3D.rooms[id].group.traverse((c) => { if (c === o) hit = true; }); return hit; }) || null;
    // exclusive: no other mesh in the scene uses its own material — the only case taking the room down could leak it
    const own = [].concat(mat); let others = 0;
    scene.traverse((c) => { if (c !== o && c.material && [].concat(c.material).some((m) => own.includes(m))) others += 1; });
    return { uuid: o.uuid, inScene, room, shared: own.some((m) => LIVE3D.sharedMat.has(m)), exclusive: others === 0 };
  }),
  markOwnMaterials: () => {
    window.__disposed = window.__disposed || {};
    return [...FOCUS.faded.entries()].map(([o, mat]) => {
      for (const m of [].concat(mat)) { const d = m.dispose.bind(m); m.dispose = () => { window.__disposed[o.uuid] = (window.__disposed[o.uuid] || 0) + 1; d(); }; }
      return o.uuid;
    });
  },
  disposedMarks: () => ({ ...(window.__disposed || {}) }),
  inScene: (uuid) => !!scene.getObjectByProperty('uuid', uuid),
  projectPath: (id) => (PROJECT[id] ? PROJECT[id].path : null),
  // what a robot's view would cross from the usual direction (the arm looks for a robot the usual view cannot see)
  usualBlockers: (id) => { const R = robots.find((x) => x.def.id === id); return R ? focusBlockers(R, focusPose(R, FOCUS_BASE.az, FOCUS_BASE.el, 8).p).size : -1; },
  renderInfo: () => (renderer ? { calls: renderer.info.render.calls, triangles: renderer.info.render.triangles, geometries: renderer.info.memory.geometries, textures: renderer.info.memory.textures } : null),
  setSim: SOURCE.mode === 'demo' ? (v) => { simT = v; prevSim = v - 0.001; } : (v) => SOURCE.setReplaySpeed(v),
};
