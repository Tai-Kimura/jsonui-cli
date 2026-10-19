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
  // robots' name tags as drawn (10-19): the screen rect of each visible one, and placeRobotTags' cost
  tags: () => robots.filter((R) => R.tag.style.visibility !== 'hidden' && !R.tag.hidden && !tagsEl.hidden).map((R) => {
    const b = R.tag.getBoundingClientRect(); return { id: R.def.id, text: R.tag.textContent, x0: b.left, x1: b.right, y0: b.top, y1: b.bottom }; }),
  tagStats: (reset) => { const S0 = TAGS.stats, out = { n: S0.n, frames: S0.frames, meanMs: S0.frames ? S0.sumMs / S0.frames : 0, maxMs: S0.maxMs };
    if (reset) Object.assign(S0, { sumMs: 0, maxMs: 0, frames: 0 }); return out; },
  // the shredder (10-19): where it is and its box, the bits in flight, and each robot's errand
  shred: () => ({ shredder: PROPS.shredder ? { x: PROPS.shredder.x, z: PROPS.shredder.z, spot: PROPS.shredder.spot, box: PROPS.shredder.box } : null,
    bits: (PROPS.bits || []).length, boxes: PROPS.boxes,
    robots: robots.map((R) => ({ id: R.def.id, room: R.def.room, phase: R.shred ? R.shred.phase : null, held: !!(R.shred && R.shred.held),
      back: !!R.playBack, tilt: !!R.tiltUntil, x: +R.robot.root.position.x.toFixed(2), z: +R.robot.root.position.z.toFixed(2), seat: R.def.pos,
      path: R.path.length, act: R.act, tag: R.text.textContent })) }),
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
    note: e.querySelector('.stale') ? e.querySelector('.stale').textContent : '' })),
  // every header chip as laid out (10-19): its box and its text's box — a stale note must not swell the row
  chipBoxes: () => [...document.querySelectorAll('.chips > :not(.usage), .chips > .usage > *')].filter((e) => e.offsetParent !== null).map((e) => {
    const b = e.getBoundingClientRect(), r = document.createRange();
    r.selectNodeContents(e);
    const t = r.getBoundingClientRect();
    return { name: e.id || e.className, h: +b.height.toFixed(1), top: +b.top.toFixed(1), bottom: +b.bottom.toFixed(1),
             mid: +((b.top + b.bottom) / 2).toFixed(1), textMid: +((t.top + t.bottom) / 2).toFixed(1) };
  }),
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
  // the box (2.3.4): its desk, what it overlaps, the papers in it, each robot's trip and the trips' ends
  gitBox: () => ({ room: PROPS.room, desk: !!PROPS.gitDesk, fill: PROPS.gitFill, spot: PROPS.place ? PROPS.place.git : null,
    overlaps: gitDeskOverlaps(), ends: GITBOX.ends.slice(),
    trips: Object.fromEntries(robots.filter((R) => R.git).map((R) => [R.def.id, { id: R.git.trip.id, phase: R.git.phase, kind: R.git.trip.kind, sheets: R.robot.carrySheets,
      look: R.robot.state, at: R.robot.root.position.toArray().map((v) => +v.toFixed(2)) }])),
    said: Object.fromEntries(robots.map((R) => [R.def.id, R.text.textContent])),
    why: Object.fromEntries(robots.map((R) => { const st = robotState[R.def.id] || {}; return [R.def.id, { trip: st.git ? { id: st.git.id, pending: st.git.pending, at: st.git.at, kind: st.git.kind } : null,
      seen: R.gitSeen || null, git: R.git ? R.git.phase : null, path: R.path.length, pos: R.robot.root.position.toArray().map((v) => +v.toFixed(2)), desk: R.def.pos, play: !!(R.play || R.playBack || R.solo), standing: !!R.def.standing, room: R.def.room, propsRoom: PROPS.room, state: st.state }]; })) }),
  // a fresh trip on the page alone, as if the server had sent it (the trip-vs-break arm: a trip that comes during a break)
  gitPoke: (id, trip) => { const st = robotState[id]; if (st) st.git = { at: vizNow(), pending: false, kind: 'push', status: 'pushed', ...trip }; return !!st; },
  gitLog: () => logItems.filter((e) => e.kind === 'GitPush' || e.kind === 'GitPull').map((e) => `${e.kind} ${e.what}`),
  gitSet: (o) => { Object.assign(GITBOX, o || {}); return { ...GITBOX, ends: undefined }; },
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
  // the camera put at its pose for FOCUS now, as the follow (a lerp a frame) would end up: the arm's specimen search reads
  // the faint meshes of exact directions, not of wherever the follow had got to (frame-rate dependent: focus-cam flake, 10-19)
  focusSnap: () => {
    const R = rbState.id ? robots.find((x) => x.def.id === rbState.id) : null;
    if (!R || camTween || !zoom.zoomed) return false;
    const pose = focusPose(R, FOCUS.az, FOCUS.el, FOCUS.dist);
    camera.position.copy(pose.p); viewTarget.copy(pose.t); camera.lookAt(viewTarget);
    return true;
  },
  // how far the camera is from its pose for FOCUS now (0 once the follow has arrived)
  focusAt: () => { const R = rbState.id ? robots.find((x) => x.def.id === rbState.id) : null; return R ? camera.position.distanceTo(focusPose(R, FOCUS.az, FOCUS.el, FOCUS.dist).p) : null; },
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
// the prompt box's waits (55-history.js): an arm shortens 「届いていない」 instead of waiting a minute
window.__dbg.promptWait = PROMPT_WAIT;
