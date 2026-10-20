/* ---------- browser-test hook (appended only when the server runs with JUI_VIZ_E2E=1) ---------- */
// The e2e scripts press the 3D boards through these, as the prototype's agent-test.html did.
// Demo: setSim(seconds) jumps the script. Live: setSim(factor) sets the replay speed instead (25-net.js).
window.__dbg = {
  // the server room (ticket 2026-10-20-jui-viz-server-room): the door's press, the keypad, the bubble, the view
  sr: () => {
    const k = srKeypad(SR.project, 0), V = SR.view;
    let door = null;
    const at = srDoorNow();
    if (at) { const v = new THREE.Vector3(); at.D.root.getWorldPosition(v); v.y = 1.1; v.project(camera); const r = canvas.getBoundingClientRect(); door = [Math.round(r.left + (v.x + 1) / 2 * r.width), Math.round(r.top + (1 - v.y) / 2 * r.height)]; }
    return { phase: SR.phase, project: SR.project, seq: SR.seq, keypad: k.state, stars: k.stars, built: !!at, door, place: at ? at.place : null,
      bubble: srBubbleEl.hidden ? null : { kind: srBubbleEl.dataset.kind, text: srBubbleEl.querySelector('.sr-short').textContent, full: srBubbleEl.querySelector('.sr-full').textContent },
      open: !srEl.hidden, lod: V ? V.lod : null, labels: V ? V.shownLabels || 0 : 0, cellPx: V ? +srCellPx(V).toFixed(2) : null, stats: SR.stats, shown: SR.shown || null,
      frames: V ? V.frames.slice(-90) : [], icons: V ? V.iconCount || 0 : 0, env: V ? V.env : null, log: SR.log.slice(0, 20).map((l) => l.text),
      board: srEl.hidden ? '' : $('sr-board').textContent, layers: V ? { near: V.near.visible, far: V.far.visible } : null,
      bubbleRect: srBubbleEl.hidden ? null : (({ left, top, right, bottom }) => [left, top, right, bottom].map(Math.round))(srBubbleEl.getBoundingClientRect()),
      gpu: V ? { geometries: V.renderer.info.memory.geometries, textures: V.renderer.info.memory.textures, calls: V.renderer.info.render.calls, triangles: V.renderer.info.render.triangles } : null };
  },
  srGroups: () => (SR.view ? SR.view.L.floors.filter((G) => G.g.id).map((G) => ({ id: G.g.id, nodes: srCountNodes(G), closed: !!G.closed })) : []),
  srSelectGroup: (id) => { SR.selected = null; SR.selectedGroup = id; srRenderBoard(); return !!document.querySelector('#sr-board [data-sr-act="toggle"]'); },
  srEdges: () => (SR.view ? SR.view.L.edges.map((e) => `${e.from}>${e.to}`) : []),
  mainFrames: () => renderer.info.render.frame,
  // the server room's arms (dd's verification, 10-20): what is drawn and how, without changing anything
  srTiming: () => ({ took: SR.took ?? null, waitMs: SR.waitMs ?? null, fastMs: SR.fastMs, okMs: SR.okMs }),
  srIconKeys: () => (SR.view ? { ...(SR.view.iconKeys || {}) } : {}),
  srNodeEnvs: () => (SR.view ? SR.view.L.nodes.map((n) => [n.id, Array.isArray(n.environments) ? n.environments : []]) : []),
  srAlive: () => !!SR.view,
  srProviders: () => (SR.view ? { only: [...SR.only], drawn: SR.view.L.nodes.map((n) => [n.id, n.providerResolved || n.provider || '']), groups: SR.view.L.floors.length, emptyFloors: SR.view.L.floors.filter((G) => srCountNodes(G) === 0).map((G) => G.g.id || '(none)'), cross: SR.view.L.edges.filter((e) => e.crossProvider).map((e) => [e.from, e.to]) } : null),
  srTheme: () => { const V = SR.view; if (!V) return null; const lab = document.querySelector('#sr-labels .sr-label:not([hidden])'), cs = lab ? getComputedStyle(lab) : null;
    return { dark: V.dark, bg: `#${V.scene.background.getHexString()}`, floors: [...new Set(V.floorColors)], label: cs ? [cs.color, cs.backgroundColor] : null }; },
  srLines: () => { const V = SR.view; return V ? { mode: SR.lines, plainOpacity: V.plainLines.material.opacity, crossOpacity: V.crossLines.material.opacity,
    plainVisible: V.plainLines.visible, crossVisible: V.crossLines.visible, focus: V.focusCount || 0, selected: SR.selected } : null; },
  srSelect: (id) => { srSelect(id); return SR.view ? SR.view.focusCount || 0 : null; },
  srEdgesOf: (id) => (SR.view ? SR.view.L.edges.filter((e) => e.from === id || e.to === id).length : null),
  srLabelRects: () => [...document.querySelectorAll('#sr-labels .sr-label:not([hidden])')].map((s) => { const r = s.getBoundingClientRect(); return [r.left, r.top, r.right, r.bottom].map(Math.round); }),
  // a robot of the room up close moved onto the line from the camera to the door, at a robot's height: it then stands in
  // front of the door from this view (D2: the door must still take the press, as the bell and the rack do)
  srRobotBeforeDoor: () => {
    const at = srDoorNow();
    if (!at) return null;
    // live: a robot of that room; the demo: a seated one (the walker is placed by the script each frame)
    const R = robots.find((x) => x.robot && x.robot.root && x.robot.root.visible && (SOURCE.mode === 'live' ? x.def.room === at.room : !x.def.walk));
    if (!R) return null;
    const door = new THREE.Vector3(); at.D.root.getWorldPosition(door); door.y = 1.1;
    const cam = camera.position, t = (cam.y - 1.0) / (cam.y - door.y), p = cam.clone().lerp(door, Math.min(0.97, Math.max(0, t)));
    R.robot.root.position.set(p.x, 0, p.z);
    R.robot.root.updateMatrixWorld(true);
    // what a ray from the camera through the door's point meets first: the robot, if it stands in front
    const ray = new THREE.Raycaster(cam.clone(), door.clone().sub(cam).normalize());
    ray.camera = camera;   // a sprite (a robot's sign) is hit only with the camera given
    const first = ray.intersectObjects([...robots.map((x) => x.robot.root), at.D.root, at.D.pad].filter(Boolean), true)[0];
    return { id: R.def.id, first: first ? (robotOf(first.object) !== undefined ? `robot:${robotOf(first.object)}` : first.object.userData.serverDoor ? 'door' : 'other') : null };
  },
  srFramesReset: () => { if (SR.view) SR.view.frames = []; return !!SR.view; },
  srZoom: (factor) => { const V = SR.view; if (!V) return null; const d = V.camera.position.clone().sub(V.controls.target).multiplyScalar(factor); V.camera.position.copy(V.controls.target).add(d); V.controls.update(); return +srCellPx(V).toFixed(2); },
  srEnter: (project) => srEnter(project, null),
  srCross: () => { const V = SR.view; return V ? { drawn: V.crossLines.geometry.attributes.position.count / 2, dashed: !!V.crossLines.material.isLineDashedMaterial, plain: V.plainLines.geometry.attributes.position.count / 2 } : null; },
  // the browser notifications (2.3.6): what this tab has looked at, its switches, the board and the card open now
  notifySeen: () => [...NOTIFY.seen],
  notifyBased: () => NOTIFY.based.perm && NOTIFY.based.ask,
  notifyPings: () => NOTIFY.pings,
  notifyAudio: () => (NOTIFY.audio ? NOTIFY.audio.state : null),
  notifyLastChime: () => NOTIFY.lastChime || null,
  notifyPanel: () => { notifyOpenPanel(null); return !notifyEl.hidden; },   // opened without a press (a press would wake the sound)
  notifyOn: () => ({ ...NOTIFY.on }),
  notifyVolume: () => NOTIFY.volume,
  notifySayStop: () => { clearInterval(NOTIFY.sayTimer); return true; },   // a hidden tab's throttled timers, at their worst
  notifyPeers: () => [...NOTIFY.peers.values()].map((p) => p.running),
  // a test's way to make this tab take events later than the others (which tab takes one first is not fixed)
  notifyDelay: (ms) => { const orig = notifyEvent; notifyEvent = (...a) => setTimeout(() => orig(...a), ms); return true; },
  notifyPresenceSay: () => notifyPresenceSay(),
  notifySet: (o) => { Object.assign(NOTIFY.on, o || {}); notifySavePrefs(); notifyPresenceSay(); return { ...NOTIFY.on }; },
  board: () => ({ open: !!tb.open, detail: tb.detail || null, waitView: !!tb.waitView, robot: rbState.id || null }),
  questions: () => QUESTIONS.map((q) => ({ id: q.id, status: q.status, hookWaiting: !!q.hookWaiting, waitEndReason: q.waitEndReason || null })),
  questionRelease: (id) => SOURCE.releaseQuestion(id),
  // the bill over a robot (54-bills.js): the message ids the page has taken from the bills slice (shown or not)
  billSeen: () => [...BILL.seen.keys()],
  camera, sbTile, sbPoint, SB, KB, THREE, robots,
  // Mermaid (2.3.5): draw a text into a box of its own and say what came out — whether it was read yet, the config it
  // runs with, the svg's nodes, and anything that could run (a script, an on* attribute, a javascript: link)
  mermaid: async (text) => {
    const before = !!window.mermaid;
    let box = document.getElementById('e2e-mermaid');
    if (!box) { box = document.createElement('div'); box.id = 'e2e-mermaid'; document.body.appendChild(box); }
    let svg = null, error = null;
    try { svg = await renderMermaid(box, text); } catch (err) { error = String(err && err.message || err); }
    const all = [...box.querySelectorAll('*')];
    return { loadedBefore: before, error, svg: !!svg, nodes: box.querySelectorAll('g.node').length, text: box.textContent,
      scripts: box.querySelectorAll('script').length, onAttrs: all.filter((e) => [...e.attributes].some((a) => /^on/i.test(a.name))).length,
      jsLinks: all.filter((e) => /^\s*javascript:/i.test(e.getAttribute('href') || e.getAttribute('xlink:href') || '')).length,
      foreignObjects: box.querySelectorAll('foreignObject').length, imgs: box.querySelectorAll('img, image').length,
      securityLevel: window.mermaid ? window.mermaid.mermaidAPI.getConfig().securityLevel : null, htmlLabels: window.mermaid ? window.mermaid.mermaidAPI.getConfig().htmlLabels : null, theme: box.dataset.theme || null,
      src: [...document.scripts].map((x) => x.getAttribute('src')).filter((x) => x && x.includes('mermaid')) };
  },
  // the data server (2.3.5): its rack (built, its box, where it is on the screen) and its sheet (open, tab, what shows)
  dataServer: () => {
    const S = PROPS.dataServer, b = new THREE.Box3(), r = canvas.getBoundingClientRect();
    let box = null, screen = null;
    if (S) {
      S.group.updateMatrixWorld(true); b.setFromObject(S.group);
      box = [b.min.x, b.max.x, b.min.z, b.max.z].map((v) => +v.toFixed(3));
      const c = b.getCenter(new THREE.Vector3()).project(camera);
      screen = [r.left + (c.x + 1) / 2 * r.width, r.top + (1 - c.y) / 2 * r.height];
    }
    return { room: PROPS.room, docs: PROPS.room && PROJECT[PROPS.room] ? PROJECT[PROPS.room].dataDocs : null, built: !!S, box, screen, spot: PROPS.place ? PROPS.place.dataServer.rect : null, wanted: PROPS.room ? dataServerWanted(PROPS.room) : null,
      open: ds.open, tab: ds.tab, loading: ds.loading, error: ds.error, api: ds.doc ? ds.doc.api.length : null, db: ds.doc ? ds.doc.db.length : null };
  },
  mermaidSafeText: (t) => mermaidSafeText(t),   // the text as it is handed to Mermaid (2.3.5)
  mermaidSafeSvg: (svg) => mermaidSafeSvg(svg),  // the drawn SVG as it goes into the page
  // the `secure` lock alone: the text drawn WITHOUT mermaidSafeText (this test hook only; the page never does)
  mermaidRenderUnsanitized: async (text) => {
    let box = document.getElementById('e2e-mermaid-raw');
    if (!box) { box = document.createElement('div'); box.id = 'e2e-mermaid-raw'; document.body.appendChild(box); }
    let svg = null, error = null;
    try { svg = await mermaidDraw(box, text, false); } catch (err) { error = String(err && err.message || err); }
    return { svg: !!svg, error, foreignObjects: box.querySelectorAll('foreignObject').length, imgs: box.querySelectorAll('img, image').length,
      htmlLabels: window.mermaid ? window.mermaid.mermaidAPI.getConfig().htmlLabels : null };
  },
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
  // tags left on each other (2.3.6, the click on a tag): false turns off keeping them apart, so the e2e can put one
  // robot's tag over another's and check the nearer takes the click; true (or nothing) puts the passes back
  tagsApart: (on) => { if (TAGS.passesAsBuilt === undefined) TAGS.passesAsBuilt = TAGS.maxPasses; TAGS.maxPasses = on === false ? 0 : TAGS.passesAsBuilt; return TAGS.maxPasses; },
  // a bill over robot `label` now (54-bills.js), without a response: the click-on-a-bill arm
  billShow: (label, usd) => { billShow(label, { id: `e2e-${label}-${performance.now()}`, usd, tokens: 1200, model: 'e2e-model', from: 'default' }); return !!(robots.find((x) => x.def.id === label) || {}).bill; },
  // placeRobotTags' own CPU time, k placements in a row in this call (2.3.5): the cost arm reads this, not the frames a
  // loaded machine happened to draw (1–2 in 3 s at load 90–130). The frame stats are left as they were.
  tagBench: (k) => { const keep = { ...TAGS.stats }; let sum = 0, max = 0;
    for (let i = 0; i < k; i++) { const t = performance.now(); placeRobotTags(); const ms = performance.now() - t; sum += ms; max = Math.max(max, ms); }
    Object.assign(TAGS.stats, keep); return { n: robots.length, runs: k, meanMs: sum / k, maxMs: max }; },
  tagStats: (reset) => { const S0 = TAGS.stats, out = { n: S0.n, frames: S0.frames, meanMs: S0.frames ? S0.sumMs / S0.frames : 0, maxMs: S0.maxMs };
    if (reset) Object.assign(S0, { sumMs: 0, maxMs: 0, frames: 0 }); return out; },
  // the shredder (10-19): where it is and its box, the bits in flight, and each robot's errand
  shred: () => ({ shredder: PROPS.shredder ? { x: PROPS.shredder.x, z: PROPS.shredder.z, spot: PROPS.shredder.spot, box: PROPS.shredder.box } : null,
    bits: (PROPS.bits || []).length, boxes: PROPS.boxes,
    robots: robots.map((R) => ({ id: R.def.id, room: R.def.room, phase: R.shred ? R.shred.phase : null, held: !!(R.shred && R.shred.held),
      back: !!R.playBack, tilt: !!R.tiltUntil, x: +R.robot.root.position.x.toFixed(2), z: +R.robot.root.position.z.toFixed(2), seat: R.def.pos,
      path: R.path.length, act: R.act, tag: R.text.textContent })) }),
  // the room up close (10-18): what is placed, where the vacuum is, the boxes it keeps clear of, and three's counts
  // the call bell (2.3.5): its place, whether it is built, and where its dome is on the page (for a real click)
  bell: () => {
    if (!PROPS.bell) return { built: false, place: PROPS.place ? PROPS.place.callButton : null };
    const v = new THREE.Vector3(PROPS.bell.position.x, BELL.h - 0.02, PROPS.bell.position.z).project(camera), r = canvas.getBoundingClientRect();
    return { built: true, place: PROPS.place.callButton, room: PROPS.room, open: !document.getElementById('call').hidden,
      screen: [Math.round(r.left + ((v.x + 1) / 2) * r.width), Math.round(r.top + ((1 - v.y) / 2) * r.height)], inView: v.z > -1 && v.z < 1 };
  },
  // what lies under a page point in the live office, nearest first (one entry per thing): the e2e shows a robot stands in
  // front of the bell or the rack before it presses there (ticket 2026-10-20-jui-viz-callbell-bell-hidden-behind-a-desk)
  under: ([x, y]) => {
    if (SOURCE.mode !== 'live' || TOWER.on) return null;
    const r = canvas.getBoundingClientRect(), ray = new THREE.Raycaster();
    ray.setFromCamera(new THREE.Vector2(((x - r.left) / r.width) * 2 - 1, -((y - r.top) / r.height) * 2 + 1), camera);
    const seen = [];
    for (const h of ray.intersectObjects(liveTargets(), true)) {
      const rid = robotOf(h.object), k = rid !== undefined ? `robot:${rid}` : isFixture(h.object) ? (h.object.userData.dataServer ? 'rack' : h.object.userData.serverDoor ? 'door' : 'bell') : 'board';
      if (!seen.includes(k)) seen.push(k);
    }
    return seen;
  },
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
    return { ends: BRK.ends.slice(), place: P ? JSON.parse(JSON.stringify(P)) : null, meshBoxes: { booth: xz(PROPS.booth), vend: xz(PROPS.vend), server: xz(PROPS.server), bell: xz(PROPS.bell), ...(PROPS.dataServer ? { dataServer: xz(PROPS.dataServer.group) } : {}) }, heights: { vend: top(PROPS.vend), robots: robots.filter((R) => R.robot.root.visible).map((R) => [R.def.id, top(R.robot.root), !!(R.robot.desk && R.robot.desk.visible)]) },
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
    heavy: heavyCauses(R.robot).length > 0, sweat: !!(R.robot.sweat && R.robot.sweat.visible), act: R.text ? R.text.textContent : '', actShown: R.text ? getComputedStyle(R.text).display !== 'none' : false })),
  // heavy work's three looks (2.3.6): force a robot's causes or tiredness (null gives them back), and read each look
  // from the robot itself: its causes, the look now, the screen's colour (a pixel of the face canvas, below the
  // mouth, clear of the eyes and the lines), the face drawn, the whistle, the sweat, the arm and the antenna
  force: (id, o) => { const R = robots.find((x) => x.def.id === id); if (!R) return false; R.robot.force = o ? { ...(R.robot.force || {}), ...o } : null; return true; },
  looks: (ids) => robots.filter((R) => !ids || ids.includes(R.def.id)).map((R) => {
    const r = R.robot, probe = makeCanvas(1, 1).getContext('2d', { willReadFrequently: true });
    probe.drawImage(r.faceCanvas, 60, 112, 1, 1, 0, 0, 1, 1);
    const px = probe.getImageData(0, 0, 1, 1).data;
    return { id: R.def.id, role: r.role, state: r.state, tired: !!r.tired, looks: heavyCauses(r), look: r.look,
      tint: r.tint ? r.tint.map((v, i) => (i < 3 ? Math.round(v) : +v.toFixed(3))) : null, face: String(r.faceMode).split('|')[0],
      screen: [px[0], px[1], px[2]], whistle: !!(r.whistle && r.whistle.visible), pipi: !!(r.pipi && r.pipi.visible), sweat: !!(r.sweat && r.sweat.visible),
      armRz: +r.armR.rotation.z.toFixed(3), antenna: +r.antenna.rotation.x.toFixed(3), period: LOOK_PERIOD, reduced: reduceMotion,
      eased: !r.tint || (r.look ? LOOK_TINT[r.look] : [r.tint[0], r.tint[1], r.tint[2], 0]).every((v, i) => Math.abs(v - r.tint[i]) < (i < 3 ? 3 : 0.01)) };
  }),
  // a close look at one robot's face, from in front of it (for the pictures of the looks)
  faceCam: (id, dist = 3.6) => {
    const R = robots.find((x) => x.def.id === id); if (!R) return false;
    const head = R.robot.head.localToWorld(new THREE.Vector3(0, 0.3, 0)), ry = R.robot.root.rotation.y;
    const eye = head.clone().add(new THREE.Vector3(Math.sin(ry) * dist, 1.4, Math.cos(ry) * dist));   // within maxPolarAngle
    controls.minDistance = Math.min(controls.minDistance, dist);   // the orbit's floor (8) would push it back out
    flyTo(eye, head, controls.target, 0, () => { controls.target.copy(head); controls.update(); });
    return true;
  },
  towerLines: (text) => { const f = towerNameFit(makeCanvas(8, 8).getContext('2d'), text, towerBays()[0].w - 8); return [f.size, ...f.lines]; },
  openRobot: (id) => openRobot(id, document.getElementById('scene-canvas')),
  // a session's main robot and a robot's project, as the page has them (tools/viz_e2e/project_switch.py)
  labelOfSession: (sid) => (typeof SESSION_UUID === 'undefined' ? null : Object.keys(SESSION_UUID).find((l) => SESSION_UUID[l] === sid) || null),
  robotProject: (id) => projectOfRobot(id) || null,
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
  liveSeenSeq: () => LIVE.seenSeq,   // the last event the page took in (a hook that rings nothing leaves no other trace)
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
  // what holds the 3D view (ticket 2026-10-20-jui-viz-data-server-from-robot-card-freezes-3d): the camera's zoom and
  // tween, whether the orbit takes input, the card, every screen open over the 3D, the tags layer
  view: () => ({ zoomed: zoom.zoomed, controls: controls.enabled, tween: !!camTween, card: rbState.id,
    open: { rb: !rbEl.hidden, wb: wb.open, tb: tb.open, ds: ds.open, pr: pr.open, log: logState.open },
    tagsHidden: tagsEl.hidden, held: typeof VIEW_HOLD === 'undefined' ? null : [...VIEW_HOLD] }),
  // the rack pressed (40-scene.js's pick, kind 'data', makes this same call) — for when the camera, framing a robot's
  // card, leaves the rack off the screen
  pressRack: () => { if (!PROPS.dataServer || !PROPS.room) return false; openDataDocs(PROPS.room, canvas); return true; },
  // a robot's spot on the screen (a real click there opens its card)
  robotXY: (id) => {
    const R = robots.find((x) => x.def.id === id);
    if (!R) return null;
    const v = R.robot.root.position.clone().add(new THREE.Vector3(0, 1.0, 0)).project(camera), r = canvas.getBoundingClientRect();
    return [r.left + ((v.x + 1) / 2) * r.width, r.top + ((1 - v.y) / 2) * r.height];
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
// Settled, for the e2e's waits (tools/viz_e2e/waits.py, 2.3.5): what animates per frame — a pose blending into the
// next (0.4 s of capped frame time), a robot walking, a tag easing up — read only when it has arrived, never sampled
// on the wall clock. ids: robot labels (all robots when omitted). A robot is settled when its pose has finished
// blending, it has no path left and is not leaving, and its tag stands where it was going.
window.__dbg.settleInfo = (ids) => robots.filter((R) => !ids || ids.includes(R.def.id)).map((R) => ({
  id: R.def.id, state: R.robot.state, blend: +R.robot.blend.toFixed(3), path: (R.path || []).length, leaving: !!(typeof LIVE !== 'undefined' && LIVE.leaving[R.def.id]),
  tag: R.tagTarget === undefined || R.tag.style.visibility === 'hidden' ? null : +(R.tagDy - R.tagTarget).toFixed(2),
  out: !!R.out, exitIn: R.exitAt ? Math.round(R.exitAt - performance.now()) : null,
  // ms from the page learning it left (LIVE.leaving's since) to its walk out (exitAt): 2500 when counted from the event
  exitAfter: R.exitAt && typeof LIVE !== 'undefined' && LIVE.leaving[R.def.id] && LIVE.leaving[R.def.id].since
    ? Math.round(R.exitAt - (performance.now() - (Date.now() - LIVE.leaving[R.def.id].since))) : null,
  leftAgo: typeof LIVE !== 'undefined' && LIVE.leaving[R.def.id] && LIVE.leaving[R.def.id].since ? Date.now() - LIVE.leaving[R.def.id].since : null }));
window.__dbg.settle = (ids) => window.__dbg.settleInfo(ids).every((x) => x.blend >= 1 && !x.path && !x.leaving && (x.tag === null || x.tag === 0));
// A gap between frames, as a hidden tab makes (rAF stops; minutes later it resumes): the next frame walks with `sec`
// more of real time (liveUpdateRobots' walkDt), and nothing else is touched.
window.__dbg.walkGap = (sec) => { LIVE3D.lastWalk -= sec * 1000; return true; };
// The walking speed now (m/s): liveWalk's WALK_SPEED, faster in a fast replay (the e2e's lower bound on a walk's time)
window.__dbg.walkSpeed = () => WALK_SPEED * (SOURCE.replaySpeed > 1 ? Math.min(4, SOURCE.replaySpeed) : 1);
// One call at the end of each frame's update of the robots (a recorder of what the frame did; null: none)
window.__dbg.afterFrame = (fn) => { LIVE3D.afterFrame = fn || null; return true; };
// Send robot `id` on foot from its room to the middle of room `to`, through the doors (liveRoute, as every walk goes):
// with walkGap, the whole route in one frame, around the doors' corners (rooms.py: the wall watcher follows the path)
window.__dbg.walkRoute = (id, to) => {
  const R = robots.find((x) => x.def.id === id), r = PROJECT[to];
  if (!R || !r) return null;
  const end = [(r.x0 + r.x1) / 2, (r.z0 + r.z1) / 2], p = R.robot.root.position;
  R.path = [...liveRoute(R.def.room, to), end];
  return { from: [p.x, p.z], to: end, points: R.path.length };
};
// how far the camera following a robot is from where it is going (0 once it has arrived)
window.__dbg.camFollowGap = () => (rbState.id && zoom.zoomed ? camera.position.distanceTo(robotPose(rbState.id).p) : null);
/* The wide history's camera (ticket 2026-10-20-jui-viz-wide-history-camera-jitters): a recorder of the camera and of where it is
   going (robotPose), every frame, to a list the arm reads; the fixed box it fits (FOCUS_BOX) and the robot's shown meshes in its
   own space (the widest corners over the frames recorded), to check that the box holds the pose. */
window.__dbg.camRecord = (id) => {
  const rec = window.__camRec = { frames: [], states: new Set(), env: null, rootY: [Infinity, -Infinity] };
  const inv = new THREE.Matrix4(), box = new THREE.Box3(), v = new THREE.Vector3();
  LIVE3D.afterFrame = () => {
    const R = robots.find((x) => x.def.id === id), root = R.robot.root, pose = robotPose(id);
    rec.frames.push([...camera.position.toArray(), ...viewTarget.toArray(), ...pose.p.toArray(), ...pose.t.toArray()]);
    rec.rootY[0] = Math.min(rec.rootY[0], root.position.y); rec.rootY[1] = Math.max(rec.rootY[1], root.position.y);
    rec.states.add(`${R.robot.state}|${!!R.robot.tired}|${!!(R.robot.sweat && R.robot.sweat.visible)}|${R.robot.look || ''}`);
    root.updateMatrixWorld(true);
    inv.copy(root.matrixWorld).invert();
    const e = rec.env || (rec.env = { x: [Infinity, -Infinity], y: [Infinity, -Infinity], z: [Infinity, -Infinity] });
    root.traverse((o) => {
      if (!o.isMesh || !shownChain(o)) return;
      box.setFromObject(o);
      for (let i = 0; i < 8; i++) {
        v.set(i & 1 ? box.max.x : box.min.x, i & 2 ? box.max.y : box.min.y, i & 4 ? box.max.z : box.min.z).applyMatrix4(inv);
        for (const k of ['x', 'y', 'z']) { e[k][0] = Math.min(e[k][0], v[k]); e[k][1] = Math.max(e[k][1], v[k]); }
      }
    });
  };
  return true;
};
window.__dbg.camRecorded = () => { const r = window.__camRec; return r ? { frames: r.frames, states: [...r.states], env: r.env, rootY: r.rootY } : null; };
// the fixed box's width as focusExtent gives it for the focused robot, at the camera's turn and distance now (before a back-off),
// with what the arm needs to work it out on its own: the robot's size and turn, the camera's direction and right
window.__dbg.focusFit = () => {
  const R = rbState.id ? robots.find((x) => x.def.id === rbState.id) : null;
  if (!R) return null;
  const dir = focusDir(FOCUS.az, FOCUS.el), right = new THREE.Vector3().crossVectors(dir.clone().negate(), new THREE.Vector3(0, 1, 0)).normalize();
  const e = focusExtent(R, right, dir, FOCUS.dist);
  return { id: R.def.id, size: R.robot.size || 1, l: e.l, r: e.r, dist: FOCUS.dist, dir: dir.toArray(), right: right.toArray(), quat: R.robot.root.quaternion.toArray() };
};
window.__dbg.focusBox = () => JSON.parse(JSON.stringify(FOCUS_BOX));
// background work (2.3.5): the headset, the notes and the laptop of each robot; and a pose's keystroke, sampled
window.__dbg.bgLook = () => robots.map((R) => {
  const r = R.robot, notes = r.notes ? r.notes.children : [], lap = r.props.background;
  return { id: R.def.id, state: r.state, kind: R.def.kind, headset: !!(r.headset && r.headset.visible && r.headset.parent),
    noteSprites: notes.length, notes: r.notes && r.notes.visible ? notes.map((n) => [+n.position.x.toFixed(3), +n.position.y.toFixed(3), +n.material.opacity.toFixed(2)]) : [],
    laptop: !!(lap && lap.group.visible), armL: +r.armL.rotation.x.toFixed(4), play: !!R.play, brk: !!R.brk, solo: !!R.solo,
    call: r.call ? `${r.call.role}:${r.call.state}` : null, onLine: !!(r.call && CALL_ON_LINE.has(r.call.state) && !(r.call.role === 'callee' && (r.call.state === 'ringing' || r.call.state === 'dialing'))),
    handset: !!r.handset };
});
// the notes' places at two pose times (still under reduced motion, rising otherwise): read without sampling frames
window.__dbg.notesAt = (id, times) => { const R = robots.find((x) => x.def.id === id); return times.map((t) => [0, 1, 2].map((k) => { const n = notePose(R.robot, k, t); return [+n.x.toFixed(3), +n.y.toFixed(3)]; })); };
// a robot that went to a game, a nap, a bento or a break, from now on, every frame (the arm reads it when it is done)
window.__dbg.watchOuting = (ids) => { const seen = Object.fromEntries(ids.map((i) => [i, false])); window.__outing = seen;
  const tick = () => { for (const R of robots) if (R.def.id in seen && (R.play || R.brk || R.solo)) seen[R.def.id] = true; if (window.__outing === seen) requestAnimationFrame(tick); };
  requestAnimationFrame(tick); return true; };
window.__dbg.poseStats = (state) => {   // the left arm over 20 s of pose time: its swing and how many strokes a second
  let lo = Infinity, hi = -Infinity, strokes = 0, prev = null;
  for (let i = 0; i <= 4000; i++) {
    const s = i * 0.005, a = poseFor(state, s).aLx;
    lo = Math.min(lo, a); hi = Math.max(hi, a);
    const up = prev !== null && a > prev; if (up && prev !== null && !window.__dbgRising) strokes += 1; window.__dbgRising = up; prev = a;
  }
  window.__dbgRising = false;
  return { swing: +(hi - lo).toFixed(4), strokesPerSec: +(strokes / 20).toFixed(2) };
};
// a subagent's work clothes and size (2.3.5): what each robot wears, its height as drawn, where its tag hangs
window.__dbg.wear = () => robots.map((R) => {
  const r = R.robot, T = THREE, box = new T.Box3(), b = new T.Box3();
  r.hips.updateWorldMatrix(true, true);
  r.hips.traverse((o) => {
    if (!o.isMesh) return;
    for (let x = o; x && x !== r.hips; x = x.parent) if (!x.visible) return;
    o.geometry.computeBoundingBox(); b.copy(o.geometry.boundingBox).applyMatrix4(o.matrixWorld); box.union(b);
  });
  const hex = (m) => (m && m.color ? '#' + m.color.getHexString() : null);
  const w = r.wear || {}, hand = r.armL.children.find((c) => c.geometry === S.geo.hand), deskTop = r.desk ? r.desk.children[0] : null;
  return { id: R.def.id, kind: R.def.kind || 'main', role: R.def.role, size: +r.root.scale.x.toFixed(3), cap: !!w.cap, patch: w.fill ? hex(w.fill.material) : null,
    patchEdge: w.patch ? hex(w.patch.children[0].material) : null, body: hex(r.torso.children[0].material), roleColor: ROLES[R.def.role].color,
    height: +(box.max.y - box.min.y).toFixed(3), top: +box.max.y.toFixed(3), bottom: +box.min.y.toFixed(3), rootY: +r.root.position.y.toFixed(3),
    tagY: +(r.root.position.y + TAG_UP.y * (r.size || 1)).toFixed(3),
    handY: hand ? +hand.getWorldPosition(new T.Vector3()).y.toFixed(3) : null, deskY: deskTop ? +deskTop.getWorldPosition(new T.Vector3()).y.toFixed(3) : null,
    torso: r.torso.children[0].getWorldPosition(new T.Vector3()).toArray().map((v) => +v.toFixed(3)) };
});
// the headset over the work cap, in the head's own space: the band's top against the crown's, the cups against its sides
window.__dbg.wearFit = (id) => {
  const R = robots.find((x) => x.def.id === id), r = R && R.robot;
  if (!r || !r.wear || !r.wear.crown) return null;
  if (!r.headset) bgGear(r);
  const bb = (mesh) => { mesh.updateMatrix(); mesh.geometry.computeBoundingBox(); return mesh.geometry.boundingBox.clone().applyMatrix4(mesh.matrix); };
  const crown = bb(r.wear.crown), parts = r.headset.children.map(bb);
  const arc = parts[0], cups = parts.slice(1, 5);
  return { crownTop: +crown.max.y.toFixed(3), arcTop: +arc.max.y.toFixed(3), crownHalfW: +crown.max.x.toFixed(3),
    cupInnerX: +Math.min(...cups.map((c) => Math.min(Math.abs(c.min.x), Math.abs(c.max.x)))).toFixed(3),
    overlapCrownCups: cups.some((c) => c.intersectsBox(crown)) };
};
window.__dbg.setVisState = (id, state) => { robotState[id] = { ...(robotState[id] || {}), state }; };
window.__dbg.wearColors = () => ({ main: ROLES.main.color, overall: WEAR.overall, edge: WEAR.edge, rim: WEAR.rim, roles: Object.fromEntries(Object.entries(ROLES).map(([k, v]) => [k, v.color])) });
// トーク (2.3.6, 58-talk.js): its state, the requests it sent and refused, and in the demo the stand-in server's hands
window.__dbg.talk = () => ({ on: TALK.on, owner: TALK.owner, agent: TALK.agent, opened: TALK.opened, conv: TALK.conv, atEnd: TALK.atEnd, newer: TALK.newer,
  list: TALK.list ? TALK.list.map((c) => ({ id: c.id, name: c.peer.name, unread: c.unread, alive: c.peer.alive, agentId: c.peer.agentId })) : null,
  msgs: TALK.conv && TALK.msgs.get(TALK.conv) ? TALK.msgs.get(TALK.conv).items.length : 0, more: TALK.conv && TALK.msgs.get(TALK.conv) ? TALK.msgs.get(TALK.conv).more : null,
  badges: { ...TALK.badges }, sent: TALK.sent.map((f) => ({ ...f })), refused: TALK.refused.length });
window.__dbg.talkFrame = (type, fields) => talkFrame(type, fields);
window.__dbg.talkDemo = SOURCE.talkDemo || null;
window.__dbg.talkAgentId = (label) => SOURCE.talkAgentId(label);
window.__dbg.talkPage = (n) => { TALK.page = n; };   // a smaller page, so paging shows on a short talk
// every role's pill as drawn (2.3.6, ticket 2026-10-20-jui-viz-main-pill-text-contrast): pill() in the page with its CSS
// (the computed background and text), and drawRolePill on a canvas (a pixel of the background, and the text's colour:
// the commonest opaque colour other than the background, a large glyph so its inside is solid)
window.__dbg.rolePills = () => {
  const box = document.createElement('div');
  box.style.cssText = 'position:absolute;left:-9999px;top:0';
  box.innerHTML = Object.keys(ROLES).map((r) => pill(r, r)).join('');
  document.body.append(box);
  const html = Object.fromEntries([...box.children].map((p) => [p.textContent, { bg: getComputedStyle(p).backgroundColor, fg: getComputedStyle(p).color }]));
  box.remove();
  const W = 240, H = 120, cv = makeCanvas(W, H), ctx = cv.getContext('2d', { willReadFrequently: true });
  const hx = (d, i) => '#' + [d[i], d[i + 1], d[i + 2]].map((v) => v.toString(16).padStart(2, '0')).join('');
  const canvas = Object.fromEntries(Object.keys(ROLES).map((r) => {
    ctx.clearRect(0, 0, W, H);
    drawRolePill(ctx, r, 'M', 0, 0, W, H, 96, 100);
    const d = ctx.getImageData(0, 0, W, H).data, bg = hx(d, ((H >> 1) * W + 30) * 4), n = {};
    for (let i = 0; i < d.length; i += 4) if (d[i + 3] === 255) { const c = hx(d, i); if (c !== bg) n[c] = (n[c] || 0) + 1; }
    const fg = Object.entries(n).sort((a, b) => b[1] - a[1])[0];
    return [r, { bg, fg: fg ? fg[0] : null }];
  }));
  return { html, canvas, body: Object.fromEntries(Object.entries(ROLES).map(([k, v]) => [k, v.color])) };
};
// reading the web (10-20): the dictionary on the desk of each robot, read from the robot itself: shown (it and every
// parent visible, in the scene), the held book, each page's turn (radians, 0 on the right block, π on the left one)
// and whether it is drawn; dictAt: the pages' turns at pose times (still under reduced motion, turning otherwise)
window.__dbg.webLook = () => robots.map((R) => {
  const r = R.robot, d = r.dict, book = r.props.reading;
  let shown = !!d; for (let x = d ? d.book : null; x; x = x.parent) { if (!x.visible) shown = false; if (!x.parent && x !== scene) shown = false; }
  return { id: R.def.id, kind: R.def.kind, state: r.state, readKind: r.readKind || null, dict: shown, book: !!(book && book.group.visible),
    pages: d ? d.pages.map((h) => +(-h.rotation.z).toFixed(3)) : [], pagesShown: d ? d.pages.filter((h) => h.visible).length : 0,
    armRz: +r.armR.rotation.z.toFixed(4), look: r.look || null, headset: !!(r.headset && r.headset.visible), reduced: reduceMotion,
    play: !!R.play, brk: !!R.brk, solo: !!R.solo, walking: R.path.length > 0 };
});
window.__dbg.dictAt = (times) => times.map((s) => [...Array(DICT_PAGES).keys()].map((k) => +(Math.PI * dictFlip(s, k)).toFixed(3)));
// a mark on the dispose of each geometry and material of a robot's dictionary that is its own (the arm sees whether
// taking the robot down disposes them); returns how many were marked
window.__dbg.markDict = (id) => {
  const R = robots.find((x) => x.def.id === id), d = R && R.robot.dict;
  if (!d) return 0;
  window.__disposed = window.__disposed || {};
  liveShared();
  const seen = new Set();
  d.book.traverse((o) => {
    const own = [o.geometry, ...[].concat(o.material || [])].filter((x) => x && !seen.has(x) && !LIVE3D.sharedGeo.has(x) && !LIVE3D.sharedMat.has(x));
    for (const x of own) { seen.add(x); const key = `dict:${x.uuid}`, f = x.dispose.bind(x); window.__disposed[key] = 0; x.dispose = () => { window.__disposed[key] += 1; f(); }; }
  });
  return seen.size;
};
// calling a subagent (10-20): the whistle of each robot read from the robot itself, and the script's time (demo)
window.__dbg.launchLook = () => ({ t: latestModel ? +latestModel.t.toFixed(3) : null, now: vizNow(), robots: robots.map((R) => {
  const r = R.robot;
  return { id: R.def.id, state: r.state, launch: !!r.launch, whistle: !!(r.whistle && r.whistle.visible), pipi: !!(r.pipi && r.pipi.visible),
    pipiLong: !!(r.pipiLong && r.pipiLong.visible), look: r.look || null, face: String(r.faceMode).split('|')[0], sweat: !!(r.sweat && r.sweat.visible),
    armRz: +r.armR.rotation.z.toFixed(3), reduced: reduceMotion, until: (robotState[R.def.id] || {}).whistle ? robotState[R.def.id].whistle.until : null };
}) });
window.__dbg.launchBeats = () => (typeof DEMO_BEATS !== 'undefined' && DEMO_BEATS.launch ? { beats: DEMO_BEATS.launch, sec: DEMO_BEATS.launchSec } : null);
// the other surfaces with text on a role's colour (2.3.7, ticket 2026-10-20-jui-viz-talk-pill-contrast-and-version-comments):
// the talk's marks (each peer's pill in the list and the header, with the role of its robot), and the phones' headers,
// drawn per role by each drawer this page has (drawPhoneUI; drawCartUI in the demo; drawLivePhone in the live view) on
// a stand-in robot: a pixel of the header clear of the text, and the commonest opaque colour other than it (the clock
// and the battery are drawn in the text's colour)
window.__dbg.talkMarks = () => [...document.querySelectorAll('#rb .talk-mark .pill')].map((p) => ({ label: p.textContent,
  role: DEF[p.textContent] ? DEF[p.textContent].role : null, where: p.closest('.talk-row') ? 'row' : 'head',
  bg: getComputedStyle(p).backgroundColor, fg: getComputedStyle(p).color }));
window.__dbg.phoneHeads = () => {
  const hx = (d, i) => '#' + [d[i], d[i + 1], d[i + 2]].map((v) => v.toString(16).padStart(2, '0')).join('');
  const drawers = { phoneUI: drawPhoneUI };
  if (SOURCE.mode === 'demo') drawers.cart = drawCartUI; else drawers.live = drawLivePhone;
  const out = {};
  for (const [name, draw] of Object.entries(drawers)) {
    out[name] = {};
    for (const role of Object.keys(ROLES)) {
      const r = { role, label: '__probe', phoneCanvas: makeCanvas(240, 400), phoneTex: {}, phoneScreenTex: {} };
      try { draw(r, 0); } catch (e) { out[name][role] = { error: String(e) }; continue; }
      const d = r.phoneCanvas.getContext('2d', { willReadFrequently: true }).getImageData(24, 24, 192, 44).data, bg = hx(d, (40 * 192 + 186) * 4), n = {};
      for (let i = 0; i < d.length; i += 4) if (d[i + 3] === 255) { const c = hx(d, i); if (c !== bg) n[c] = (n[c] || 0) + 1; }
      const fg = Object.entries(n).sort((a, b) => b[1] - a[1])[0];
      out[name][role] = { bg, fg: fg ? fg[0] : null };
    }
  }
  return out;
};
