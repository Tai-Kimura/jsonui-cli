/* ---------- the server room's flows played (ticket 2026-10-20-jui-viz-server-room-lines-dark-filter-spec, item 7) ----------
   Requester 10-20: 「エンドユーザーのノード押したら選択肢が出る。その選択肢押したら通る経路がアニメーションしてどういう処理の流れになるかが
   視覚的にわかるようにしたい」; 「DBに保存とか読み取りとかS3にアップロードとかもパッとわかるようにしたいね … 吹き出しでもトーストで出る感じで
   いける？ 速度も0.5,1.0,1.5,2.0,3.0,5.0,10.0 みたいに選べるようにして」; 「任意のオブジェクトに設定できてほしい」; 「途中で分岐作って
   そこで止まって選択できるのもあると便利じゃない？」.

   The model's flows (infra/flows.py checked them: every move leaves the node the flow is at). A node that starts a
   flow drawn now carries a small green cone; choosing the node lists its flows on the board, and a flow chosen plays:
   - light runs through each move's edge, a bright head and a fading tail inside the cable (requester 10-22: 「ボールが跳ねる
     んじゃなくて同線に光が流れていくイメージで」), and the node it reaches glows; a row in the side bar says what happened
     (the action's mark and verb after the node's name: 「💾 d1 に保存」, the step's label on a second line), and the
     first one says what started it (the trigger's mark: 👤 ⏰ 📡 ⚡, with a schedule as written);
   - a branch stops the light: its choices are buttons over the node, the first edge of each glows faintly ahead, and
     with 自動 on a default is taken by itself (none: it waits). goto plays the other flow (jumping when it starts
     elsewhere), join goes on at that step; the choices taken are listed (「KV に結果が有る？ → 無い」);
   - lanes side by side run at once, and the flow goes on when all of them are done;
   - play / pause, one step on, one step back (to a branch: choose again), stop; the speed one of SR_FLOW_SPEEDS,
     changed while it plays (the light and the rests go by the same clock).
   A rebuild of the 3D (the environment, the clouds chosen, the theme) stops the flow playing: its light and side bar
   belonged to the 3D that went.
   The pace (ticket 2026-10-23-viz-sr-flow-replay-pace-and-focus; requester 10-23: 「遠いところの移動が目が追いつかない。
   距離/sで設定して / スピード調整が欲しい。0.5-3.0くらいで / 各喉についた時にそれぞれ少し留まって欲しい。 / 再生中は関係ない
   ノードは消して欲しい」):
   - the light goes SR_FLOW.unitsPerSec world units a second along its cable, so a long cable takes longer; the speed
     0.5–3.0 by 0.25, kept per room (srFlowPref) with which nodes are shown;
   - at each node it reaches it rests SR_FLOW.restMs (÷ the speed); a branch, once chosen, rests twice that with the
     chosen way's first cable lit;
   - the nodes shown (SR_FLOW_SHOWS): all, now (the moves' two ends, where the light is, a branch's first cables),
     seen (passed so far, and now) or flow (every node the flow names, its gotos' too). A node not shown loses its
     shape, icon, model, tag, cone and cables; the floors stay, faint, as a map (srFlowShowApply);
   - the camera follows a light about to leave the page (SR_FLOW.follow), at the same distance, never while the whole
     room is in view.
   The words (requester 10-24: 「3d/2dのオブジェクト上に文字が出るのみづらいからサイドに光に合わせて順番に履歴として出て
   それが下矢印で繋がっていく感じにしようか / 選択肢を選ぶのもそのサイドバーで選ぶ」): nothing is written over the room;
   each step is a row of the side bar left of it (#sr-route), joined to the one before by a down arrow, the newest the
   current one (its .sr-rt-step marked current), pressed to choose its node; a branch's ways are chosen under the last row.
   SR_ACTIONS and SR_TRIGGERS are the schema's x-label / x-icon (test_viz_bundle holds them to the schema). */
const SR_FLOW_SPEEDS = [0.5, 0.75, 1.0, 1.25, 1.5, 1.75, 2.0, 2.25, 2.5, 2.75, 3.0];
const SR_FLOW_SHOWS = { all: [tl('sr.flow.show.all'), tl('sr.flow.show.all.title')], now: [tl('sr.flow.show.now'), tl('sr.flow.show.now.title')],
  seen: [tl('sr.flow.show.seen'), tl('sr.flow.show.seen.title')], flow: [tl('sr.flow.show.flow'), tl('sr.flow.show.flow.title')] };
const SR_ACTIONS = { request: ['→', tl('sr.flow.action.request')], response: ['←', tl('sr.flow.action.response')], read: ['📖', tl('sr.flow.action.read')], write: ['💾', tl('sr.flow.action.write')], upload: ['⬆', tl('sr.flow.action.upload')], download: ['⬇', tl('sr.flow.action.download')], invoke: ['⚡', tl('sr.flow.action.invoke')], enqueue: ['📥', tl('sr.flow.action.enqueue')], dequeue: ['📤', tl('sr.flow.action.dequeue')], publish: ['📣', tl('sr.flow.action.publish')], subscribe: ['📡', tl('sr.flow.action.subscribe')], auth: ['🔑', tl('sr.flow.action.auth')], schedule: ['⏰', tl('sr.flow.action.schedule')] };
const SR_TRIGGERS = { user: ['👤', tl('sr.flow.trigger.user')], device: ['📡', tl('sr.flow.trigger.device')], schedule: ['⏰', tl('sr.flow.trigger.schedule')], event: ['⚡', tl('sr.flow.trigger.event')] };
const SR_FLOW_STATE = { play: tl('sr.flow.state.play'), pause: tl('sr.flow.state.pause'), branch: tl('sr.flow.state.branch'), done: tl('sr.flow.state.done') };
// follow: the light past `out` of the page's half (NDC) starts the camera after it, back inside `in` it stops; `ms` how
// quickly it catches up. frame: how much of the seen part of the room its shapes and tags fill when it is framed again
// beside the side bar (srFlowFrameRoom)
const SR_FLOW = { speed: 1.0, auto: false, unitsPerSec: 10, restMs: 400, branchRest: 2, nodeMs: 450, show: 'flow', floorFade: 0.6,
  follow: { out: 0.8, in: 0.45, ms: 280 }, frame: 0.8, player: null };

/* Speed and the nodes shown, per room: {project: {speed, show}} in the page's own storage. */
function srFlowPref() {
  try { const all = JSON.parse(readPref('srFlow', '{}')) || {}; return all[SR.project] || {}; } catch (err) { return {}; }
}
function srFlowPrefSet(key, value) {
  let all = {};
  try { all = JSON.parse(readPref('srFlow', '{}')) || {}; } catch (err) { all = {}; }
  all[SR.project] = { ...(all[SR.project] || {}), [key]: value };
  writePref('srFlow', JSON.stringify(all));
}

function srFlowsOf(V) {
  const flows = (SR.model && SR.model.flows) || [];
  return flows.filter((f) => srVisible(f, V.env) && V.L.pos.has(f.start));
}
function srFlowNodeName(id) {
  const n = SR.model && (SR.model.nodes || []).find((x) => x.id === id);
  return n ? n.label || n.id : id;
}
function srFlowPos(V, id) {
  const p = V.L.pos.get(id);
  return p ? new THREE.Vector3(p.x, p.y + 0.9, p.z) : null;
}

/* After each build: the cones over the nodes that start a flow drawn now, and the layers the player draws on. */
function srFlowBuild(V) {
  const pref = srFlowPref();
  SR_FLOW.speed = SR_FLOW_SPEEDS.includes(pref.speed) ? pref.speed : 1.0;
  SR_FLOW.show = SR_FLOW_SHOWS[pref.show] ? pref.show : 'flow';
  V.flowStarts = [...new Set(srFlowsOf(V).map((f) => f.start))];
  V.flowLayer = new THREE.Group();
  V.near.add(V.flowLayer);
  if (V.flowStarts.length) {
    const mesh = new THREE.InstancedMesh(new THREE.ConeGeometry(0.22, 0.4, 10), new THREE.MeshBasicMaterial({ color: 0x2fb36d }), V.flowStarts.length);
    const m4 = new THREE.Matrix4(), q = new THREE.Quaternion().setFromEuler(new THREE.Euler(Math.PI, 0, 0));
    V.flowStarts.forEach((id, i) => { const p = V.L.pos.get(id); m4.compose(new THREE.Vector3(p.x + 0.55, p.y + 2.0, p.z), q, new THREE.Vector3(1, 1, 1)); mesh.setMatrixAt(i, m4); });
    mesh.userData.flowStarts = V.flowStarts.slice();
    V.flowLayer.add(mesh);
  }
}

/* The board's list for the chosen node: the flows it starts (none: nothing is added), right under the node's own rows. */
function srFlowBoardHTML(nodeId) {
  const V = SR.view;
  if (!V || !nodeId) return '';
  const mine = srFlowsOf(V).filter((f) => f.start === nodeId);
  if (!mine.length) return '';
  return `<h3>${esc(tl('sr.flow.board.title'))}</h3><ul class="sr-flows">${mine.map((f) => { const t = SR_TRIGGERS[f.trigger] || SR_TRIGGERS.user;
    return `<li><button type="button" class="wb-btn" data-sr-flow="${esc(f.id)}">${esc(t[0])} ${esc(f.label || f.id)}</button>${f.schedule ? ` <small>${esc(f.schedule)}</small>` : ''}</li>`; }).join('')}</ul>`;
}

/* ---- the player */
function srFlowPlay(id) {
  const V = SR.view, flow = V && srFlowsOf(V).find((f) => f.id === id);
  if (!flow) return false;
  srFlowStop();
  // departs / reached / chose: where and when (the e2e reads the pace and the rests from them)
  const P = SR_FLOW.player = { flow, frames: [{ steps: flow.steps, i: 0 }], pos: flow.start, state: 'play', anim: null, history: [],
    chosen: [], lights: [], branch: null, arrivals: [], reached: [], departs: [], chose: [], log: [], dirty: true,
    all: srFlowNodesOf(flow), seen: new Set([flow.start]) };
  const t = SR_TRIGGERS[flow.trigger] || SR_TRIGGERS.user;
  $('sr-route-list').replaceChildren();
  $('sr-route-title').textContent = `${t[0]} ${flow.label || flow.id}`;
  // the side bar takes its column from the room: a room seen whole stays whole, its shapes and tags in what is left of
  // the room above the player's bar (srFit frames the 3D by its height alone, and a node's middle in view can be a tag
  // cut by the page's edge: the requester's stills at 900 wide)
  const whole = srFlowWhole(V);
  $('sr-route').hidden = false;
  srResize(V);
  srFlowRenderBar();
  if (whole && srFlowRoomOut(V).length) srFlowFrameRoom(V);
  srFlowToast(P, flow.start, `${t[0]} ${flow.label || flow.id}`, flow.schedule || t[1]);
  srFlowGlow(P, flow.start);
  srFlowRenderBar();
  srFlowShowApply(V);
  return true;
}
/* Every node a flow names: its start, each step's, every branch's and lane's, and the flows a choice goes to. */
function srFlowNodesOf(flow, out = new Set(), done = new Set()) {
  if (!flow || done.has(flow.id)) return out;
  done.add(flow.id);
  out.add(flow.start);
  const walk = (steps) => {
    for (const s of steps || []) {
      for (const k of ['from', 'to', 'at', 'node']) if (s[k]) out.add(s[k]);
      if (s.branch) for (const c of s.branch.choices) { walk(c.steps); if (c.goto) srFlowNodesOf(srFlowsOf(SR.view).find((f) => f.id === c.goto), out, done); }
      if (s.parallel) for (const lane of s.parallel) walk(lane);
    }
  };
  walk(flow.steps);
  return out;
}
function srFlowStop() {
  const P = SR_FLOW.player;
  if (!P) return;
  $('sr-route-list').replaceChildren();
  $('sr-route').hidden = true;
  const layer = SR.view && SR.view.flowLayer;
  if (layer) for (const o of [...layer.children]) if (!o.userData.flowStarts) { layer.remove(o); if (o.userData.flowLight) srFlowLightDispose(o); else if (o.geometry) o.geometry.dispose(); }
  SR_FLOW.player = null;
  $('sr-choices').hidden = true;
  srFlowRenderBar();
  if (SR.view && SR.view.flowLayer) srFlowShowApply(SR.view);   // every node drawn again
}
function srFlowSnapshot(P) {
  return { flow: P.flow, frames: P.frames.map((f) => ({ steps: f.steps, i: f.i })), pos: P.pos, chosen: P.chosen.slice(), seen: new Set(P.seen), rows: P.log.length };
}
/* Take the next step (or wait at a branch). One step at a time: the frame loop calls it when the last one is done. */
function srFlowNext(P) {
  if (P.branch) return;
  for (;;) {
    const top = P.frames[P.frames.length - 1];
    if (!top) { P.state = 'done'; srFlowToast(P, P.pos, tl('sr.flow.end'), ''); srFlowRenderBar(); return; }
    if (top.i >= top.steps.length) { P.frames.pop(); continue; }
    P.history.push(srFlowSnapshot(P));
    const step = top.steps[top.i];
    top.i += 1;
    if (step.branch) { srFlowAtBranch(P, step.branch); return; }
    if (step.parallel) {
      const lanes = step.parallel.map((lane) => ({ steps: srFlowLane(lane), k: 0, anim: null }));
      P.anim = { kind: 'lanes', lanes };
      for (const L of lanes) srFlowLaneNext(P, L);
      return;
    }
    if (step.from && step.to) { P.anim = srFlowMove(P, step); return; }
    if (step.at || step.node) { srFlowSay(P, step, step.at || step.node); P.anim = { kind: 'wait', left: SR_FLOW.nodeMs, at: step.at || step.node }; return; }
  }
}
/* A lane plays its moves and node steps (a branch inside a lane takes its default, else its first choice). */
function srFlowLane(steps) {
  const out = [];
  for (const s of steps) {
    if (s.branch) { const c = s.branch.choices.find((x) => x.id === s.branch.default) || s.branch.choices[0]; out.push(...srFlowLane(c.steps || [])); }
    else if (s.parallel) for (const l of s.parallel) out.push(...srFlowLane(l));
    else out.push(s);
  }
  return out;
}
function srFlowLaneNext(P, L) {
  const s = L.steps[L.k];
  L.k += 1;
  if (!s) { L.anim = null; L.done = true; return; }
  if (s.from && s.to) L.anim = srFlowMove(P, s);
  else { srFlowSay(P, s, s.at || s.node); L.anim = { kind: 'wait', left: SR_FLOW.nodeMs, at: s.at || s.node }; }
}
/* A move takes its cable's length at SR_FLOW.unitsPerSec (at 1.0), then rests at the node it reached (rest: ms left). */
function srFlowMove(P, step) {
  const V = SR.view, light = srFlowLight(V, step.from, step.to);
  V.flowLayer.add(light);
  P.lights.push(light);
  P.seen.add(step.from);
  P.departs.push([step.from, step.to, srNow()]);
  return { kind: 'move', step, light, done: 0, ms: light.userData.total / SR_FLOW.unitsPerSec * 1000, rest: null };
}

/* ---- the light in the cable: no object travels. The move's edge gets a tube as long as its cable, at the cable's
   height (srBuild: 1.7, across clouds 2.6), in two layers — a thin core and a wide soft glow — and SR_FLOW_LIGHT_SHADER
   lights the part of it behind the head: full at the head (toward white), fading over the tail. The head goes from the
   cable's start to its end on the move's clock; once there the tail drains into the node (SR_FLOW_LIGHT.drainMs), the
   light no longer counted as moving. In dark the glow adds to what is behind it; on the light ground it is laid over. */
const SR_FLOW_LIGHT = { core: 0.07, glow: 0.24, tail: 3.2, drainMs: 380 };
const SR_FLOW_LIGHT_SHADER = {
  vertex: `varying float vAlong; varying float vFacing;
    void main() { vAlong = position.y + 0.5; vec4 mv = modelViewMatrix * vec4(position, 1.0);
      vFacing = abs(dot(normalize(normalMatrix * normal), normalize(-mv.xyz))); gl_Position = projectionMatrix * mv; }`,
  fragment: `uniform vec3 uColor; uniform float uHead, uTail, uOpacity, uSoft, uWhite; varying float vAlong; varying float vFacing;
    void main() { float d = uHead - vAlong;
      float a = d >= 0.0 ? pow(max(0.0, 1.0 - d / uTail), 1.7) : max(0.0, 1.0 + d / 0.015);
      a *= mix(1.0, pow(vFacing, 2.0), uSoft);
      if (a <= 0.004) discard;
      gl_FragColor = vec4(mix(uColor, vec3(1.0), uWhite * pow(a, 3.0)), a * uOpacity); }`,
};
function srFlowCrossing(V, from, to) {
  const e = V.L.edges.find((x) => (x.from === from && x.to === to) || (x.from === to && x.to === from));
  return !!(e && e.crossProvider);
}
/* The light runs in its cable, along the same path (56-server-room.js srCablePathOf), in the move's direction: a tube a
   segment, each lit for the part of the head and tail that falls on it. */
function srFlowLight(V, from, to) {
  const pts = srCablePathOf(V, from, to, srFlowCrossing(V, from, to)).map((q) => new THREE.Vector3(...q));
  const lens = pts.slice(1).map((q, i) => q.distanceTo(pts[i])), total = Math.max(lens.reduce((x, y) => x + y, 0), 1e-3);
  const PAL = SR_PAL[V.dark ? 'dark' : 'light'], tail = Math.min(0.85, SR_FLOW_LIGHT.tail / total);
  const layer = (color, opacity, soft, white) => new THREE.ShaderMaterial({ vertexShader: SR_FLOW_LIGHT_SHADER.vertex, fragmentShader: SR_FLOW_LIGHT_SHADER.fragment,
    uniforms: { uColor: { value: new THREE.Color(color) }, uHead: { value: 0 }, uTail: { value: tail }, uOpacity: { value: opacity }, uSoft: { value: soft }, uWhite: { value: white } },
    transparent: true, depthWrite: false, blending: V.dark ? THREE.AdditiveBlending : THREE.NormalBlending });
  const tube = new THREE.CylinderGeometry(1, 1, 1, 12, 1, true), light = new THREE.Group(), parts = [];
  let at = 0;
  for (let i = 0; i < lens.length; i++) {
    const a = pts[i], b = pts[i + 1], len = Math.max(lens[i], 1e-4);
    const glow = new THREE.Mesh(tube, layer(PAL.light, V.dark ? 0.75 : 0.85, 1, 0)), core = new THREE.Mesh(tube, layer(PAL.lightCore, 1, 0, V.dark ? 0.85 : 0.35));
    const seg = new THREE.Group();
    seg.add(glow, core);
    seg.position.copy(a).add(b).multiplyScalar(0.5);
    seg.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), b.clone().sub(a).normalize());
    glow.scale.set(SR_FLOW_LIGHT.glow, len, SR_FLOW_LIGHT.glow); core.scale.set(SR_FLOW_LIGHT.core, len, SR_FLOW_LIGHT.core);
    seg.renderOrder = glow.renderOrder = core.renderOrder = 3;
    light.add(seg);
    parts.push({ glow, core, from: at / total, span: len / total });
    at += len;
  }
  light.renderOrder = 3;
  // glow / core: the first part's (read by the e2e hooks as before); parts: every part, its place on the path
  light.userData = { flowLight: true, moving: true, from, to, a: pts[0], b: pts[pts.length - 1], pts, total, head: pts[0].clone(), glow: parts[0].glow, core: parts[0].core, parts, tail };
  return light;
}
/* The head at k (0: the cable's start, 1: its end, past 1: the tail draining): each part sees it in its own length. */
function srFlowLightAt(o, k) {
  const U = o.userData;
  U.k = k;   // where the head is on the whole path (the e2e reads it)
  for (const P of U.parts) for (const m of [P.glow, P.core]) {
    m.material.uniforms.uHead.value = (k - P.from) / P.span;
    m.material.uniforms.uTail.value = U.tail / P.span;
  }
  const want = Math.min(k, 1) * U.total;
  let at = 0;
  for (let i = 0; i + 1 < U.pts.length; i++) {
    const l = U.pts[i + 1].distanceTo(U.pts[i]);
    if (at + l >= want || i + 2 === U.pts.length) { U.head.lerpVectors(U.pts[i], U.pts[i + 1], l ? Math.min(1, (want - at) / l) : 1); break; }
    at += l;
  }
}
/* Pulled back, the glow is drawn at least SR_FLOW_MIN_PX in radius at its head (the core a third of that). */
function srFlowLightKeepSize(V, o) {
  const px = srFlowPxPerUnit(V, o.userData.head), g = Math.max(SR_FLOW_LIGHT.glow, SR_FLOW_MIN_PX / px), c = Math.max(SR_FLOW_LIGHT.core, SR_FLOW_MIN_PX / 3 / px);
  for (const P of o.userData.parts) { P.glow.scale.x = P.glow.scale.z = g; P.core.scale.x = P.core.scale.z = c; }
}
function srFlowLightDispose(o) {
  o.userData.glow.geometry.dispose();
  for (const P of o.userData.parts) for (const m of [P.glow, P.core]) m.material.dispose();
}
function srFlowSay(P, step, at) {
  const act = SR_ACTIONS[step.action];
  const head = act ? tl('sr.flow.say', { mark: act[0], node: srFlowNodeName(at), verb: act[1] }) : `• ${srFlowNodeName(at)}`;
  srFlowToast(P, at, head, step.label || '');
  srFlowGlow(P, at);
}
function srFlowAtBranch(P, b) {
  P.branch = { b, at: P.pos, shownAt: srNow() };
  P.state = 'branch';
  P.stepOnce = false;        // a step taken to here ends here: the choice made plays on
  srFlowHints(P, b.choices);
  srFlowChoices();
  srFlowRenderBar();
}
/* The branch's question and its ways, in the side bar under the last row (Auto on: the default says it is taken by itself). */
function srFlowChoices() {
  const P = SR_FLOW.player, box = $('sr-choices');
  if (!P || !P.branch) { box.hidden = true; return; }
  const b = P.branch.b, mark = tl(SR_FLOW.auto ? 'sr.flow.choice.auto' : 'sr.flow.choice.default');
  setHTML(box, `<span class="sr-rt-arrow" aria-hidden="true">↓</span><p class="sr-choice-q">${esc(b.label)}</p>${b.choices.map((c) => `<button type="button" class="wb-btn" data-sr-choice="${esc(c.id)}"${c.id === b.default ? ' data-default' : ''}>${esc(c.label)}${c.id === b.default ? ` <small>${esc(mark)}</small>` : ''}</button>`).join('')}`);
  box.hidden = false;
  srFlowRouteScroll(box);
}
/* Each choice's first edge, faint, while the branch waits (and the chosen one's alone while it rests there). */
function srFlowHints(P, choices) {
  const V = SR.view, arr = [];
  for (const c of choices) {
    const first = (c.steps || []).find((s) => s.from && s.to);
    if (!first) continue;
    const path = srCablePathOf(V, first.from, first.to, srFlowCrossing(V, first.from, first.to));   // as its cable runs
    if (path) arr.push(path);
  }
  // a strip as wide as the cables (56-server-room.js srCables), in the light's colour: a 1 px line was lost beside them
  const lines = srCables(arr, { color: SR_PAL[V.dark ? 'dark' : 'light'].light, opacity: 0.45, px: SR_CABLE.focus, world: SR_CABLE.world, max: SR_CABLE.max });
  lines.userData.hints = arr.length;
  V.flowLayer.add(lines);
  P.hints = lines;
}
function srFlowChoose(id) {
  const P = SR_FLOW.player;
  if (!P || !P.branch) return false;
  const b = P.branch.b, c = b.choices.find((x) => x.id === id);
  if (!c) return false;
  P.chosen.push(`${b.label} → ${c.label}`);
  P.chose.push([P.branch.at, c.id, srNow()]);
  // it rests at the branch twice as long as at a node, the way chosen lit, before it goes on
  const at = P.branch.at;
  srFlowToast(P, at, `${b.label} → ${c.label}`, '');
  P.branch = null;
  $('sr-choices').hidden = true;
  srFlowHintsOff(P);
  srFlowHints(P, [c]);
  P.anim = { kind: 'wait', left: SR_FLOW.restMs * SR_FLOW.branchRest, at, way: c, then: () => srFlowHintsOff(P) };
  if (c.goto) {
    const next = srFlowsOf(SR.view).find((f) => f.id === c.goto);
    if (next) {
      P.flow = next; P.frames = [{ steps: next.steps, i: 0 }];
      const t = SR_TRIGGERS[next.trigger] || SR_TRIGGERS.user;
      P.pos = next.start;
      srFlowToast(P, next.start, `${t[0]} ${next.label || next.id}`, next.schedule || t[1]);
    }
  } else if (c.join) {
    const j = P.flow.steps.findIndex((s) => s.id === c.join);
    P.frames = [{ steps: P.flow.steps, i: j }];
  } else if (c.steps) P.frames.push({ steps: c.steps, i: 0 });
  if (P.state !== 'pause') P.state = 'play';
  srFlowRenderBar();
  return true;
}
function srFlowBack() {
  const P = SR_FLOW.player;
  if (!P || !P.history.length) return false;
  const s = P.history.pop();
  P.flow = s.flow; P.frames = s.frames; P.pos = s.pos; P.chosen = s.chosen; P.seen = s.seen;
  P.branch = null; $('sr-choices').hidden = true;
  P.log.length = s.rows;   // the side bar back to the rows it had then
  const list = $('sr-route-list');
  while (list.children.length > s.rows) list.lastElementChild.remove();
  if (list.lastElementChild) { for (const x of list.querySelectorAll('.sr-rt-step[aria-current]')) x.removeAttribute('aria-current'); list.lastElementChild.querySelector('.sr-rt-step').setAttribute('aria-current', 'true'); }
  srFlowHintsOff(P);
  for (const d of P.lights) { SR.view.flowLayer.remove(d); if (d.userData.flowLight) srFlowLightDispose(d); }
  P.lights = []; P.anim = null; P.state = 'pause';
  srFlowRenderBar();
  return true;
}
function srFlowHintsOff(P) {
  if (!P.hints) return;
  SR.view.flowLayer.remove(P.hints); P.hints.geometry.dispose(); P.hints.material.dispose(); P.hints = null;
}
/* A step said in the side bar (requester 10-24: 「3d/2dのオブジェクト上に文字が出るのみづらいからサイドに光に合わせて順番に
   履歴として出てそれが下矢印で繋がっていく感じに」): a row at the end, a down arrow from the one before, it the current one;
   pressed, its node is chosen. Nothing is written over the room. */
function srFlowToast(P, at, head, sub) {
  const list = $('sr-route-list'), li = document.createElement('li');
  const part = (tag, cls, text) => { const el = document.createElement(tag); if (cls) el.className = cls; if (text) el.textContent = text; return el; };
  if (list.children.length) { const arrow = part('span', 'sr-rt-arrow', '↓'); arrow.setAttribute('aria-hidden', 'true'); li.append(arrow); }
  const step = part('button', 'sr-rt-step');
  step.type = 'button';
  if (at) step.dataset.srRt = at;
  step.append(part('b', '', head));
  if (sub) step.append(part('span', '', sub));
  li.append(step);
  for (const x of list.querySelectorAll('.sr-rt-step[aria-current]')) x.removeAttribute('aria-current');
  li.className = 'sr-rt'; li.querySelector('.sr-rt-step').setAttribute('aria-current', 'true');
  list.append(li);
  srFlowRouteScroll(li);
  P.log.push(head);
}
/* The side bar turned so el (the current row, or the branch's ways) is in view. */
function srFlowRouteScroll(el) {
  const box = $('sr-route'), top = el.offsetTop, bottom = top + el.offsetHeight;
  if (bottom > box.scrollTop + box.clientHeight) box.scrollTop = bottom - box.clientHeight + 8;
  else if (top < box.scrollTop) box.scrollTop = top - 8;
}
function srFlowGlow(P, at) {
  const p = srFlowPos(SR.view, at);
  if (!p) return;
  const ring = new THREE.Mesh(new THREE.TorusGeometry(0.75, 0.08, 6, 24), new THREE.MeshBasicMaterial({ color: SR_PAL[SR.view.dark ? 'dark' : 'light'].light, transparent: true, opacity: 0.9 }));
  ring.position.set(p.x, p.y - 0.6, p.z); ring.rotation.x = Math.PI / 2;
  ring.userData.left = SR_FLOW.nodeMs * 2;
  ring.userData.r = 0.75; ring.userData.minPx = SR_FLOW_MIN_PX * 2;
  SR.view.flowLayer.add(ring);
  P.lights.push(ring);
}

/* Pulled back over a large room a light is a few pixels: it is drawn at least SR_FLOW_MIN_PX in radius (the ring under a
   node twice that), and at its own size once the camera is near enough for that. */
const SR_FLOW_MIN_PX = 7;
function srFlowPxPerUnit(V, at) {
  if (V.flat) return V.renderer.domElement.clientHeight / srSpan(V);   // 2D: one scale over the whole page
  const d = V.camera.position.distanceTo(at);
  return V.renderer.domElement.clientHeight / (2 * Math.max(d, 1e-3) * Math.tan(V.camera.fov * Math.PI / 360));
}
function srFlowKeepSize(V, o) {
  if (!o.userData.r) return;
  o.scale.setScalar(Math.max(1, o.userData.minPx / (o.userData.r * srFlowPxPerUnit(V, o.position))));
}

/* ---- the nodes shown while it plays (null: all of them) */
function srFlowNow(P) {
  const now = new Set([P.pos]);
  const add = (A) => {
    if (!A) return;
    if (A.kind === 'move') { now.add(A.step.from); now.add(A.step.to); } else if (A.at) now.add(A.at);
  };
  if (P.anim && P.anim.kind === 'lanes') for (const L of P.anim.lanes) add(L.anim); else add(P.anim);
  const ways = P.branch ? P.branch.b.choices : P.anim && P.anim.way ? [P.anim.way] : [];   // a branch's first cables, or the way chosen
  for (const c of ways) { const first = (c.steps || []).find((s) => s.from && s.to); if (first) { now.add(first.from); now.add(first.to); } }
  return now;
}
function srFlowShown(P) {
  if (!P || SR_FLOW.show === 'all') return null;
  const now = srFlowNow(P);
  if (SR_FLOW.show === 'now') return now;
  return new Set([...(SR_FLOW.show === 'seen' ? P.seen : P.all), ...now]);
}
function srFlowHides(id) { const V = SR.view; return !!(V && V.flowHidden && V.flowHidden.has(id)); }
function srFlowEdgeHidden(e) { return srFlowHides(e.from) || srFlowHides(e.to); }
/* Writes the nodes shown on the 3D when they change (and when the icons come, after the build): a node not shown is
   drawn at no size (its shapes, icon, cone), its model hidden, its tag left out (56-server-room.js srPlaceLabels), and
   its cables not drawn; the floors go faint toward the ground while any node is hidden, so they stay as a map. */
function srFlowShowApply(V, force = false) {
  const shown = srFlowShown(SR_FLOW.player);
  const key = `${shown ? [...shown].sort().join('|') : '*'}#${V.iconCount || 0}`;
  if (!force && key === V.flowShowKey) return;
  V.flowShowKey = key;
  const hidden = new Set();
  if (shown) for (const id of V.L.pos.keys()) if (!shown.has(id)) hidden.add(id);
  const was = V.flowHidden ? V.flowHidden.size : 0;
  V.flowHidden = hidden;
  if (!hidden.size && !was && !force) return;
  const m4 = new THREE.Matrix4(), pos = new THREE.Vector3(), q = new THREE.Quaternion(), sc = new THREE.Vector3();
  V.near.traverse((mesh) => {
    const ids = mesh.isInstancedMesh && (mesh.userData.nodes || mesh.userData.flowStarts);
    if (!ids) return;
    if (!mesh.userData.flowBase) { if (!hidden.size) return; mesh.userData.flowBase = mesh.instanceMatrix.array.slice(); }
    const base = mesh.userData.flowBase;
    ids.forEach((id, i) => {
      m4.fromArray(base, i * 16);
      if (hidden.has(id)) { m4.decompose(pos, q, sc); m4.compose(pos, q, sc.multiplyScalar(1e-4)); }
      mesh.setMatrixAt(i, m4);
    });
    mesh.instanceMatrix.needsUpdate = true; mesh.boundingSphere = null;
    if (!hidden.size) mesh.userData.flowBase = null;
  });
  if (V.models) for (const [id, g] of V.models) g.visible = !hidden.has(id);
  const segs = { plain: 0, cross: 0 };
  for (const e of V.L.edges) {   // the same order srBuild laid them in: a cable each
    const set = e.crossProvider ? 'cross' : 'plain', j = segs[set]++;
    srCableShow(set === 'cross' ? V.crossLines : V.plainLines, j, 0, hidden.has(e.from) || hidden.has(e.to) ? 0 : 1);
  }
  srCableDone(V.plainLines); srCableDone(V.crossLines);
  const fm = V.floorMesh;
  if (fm && fm.instanceColor) {
    const bg = new THREE.Color(V.scene.background), c = new THREE.Color();
    V.floorColors.forEach((hex, i) => { c.set(hex); if (hidden.size) c.lerp(bg, SR_FLOW.floorFade); fm.setColorAt(i, c); });
    fm.instanceColor.needsUpdate = true;
  }
  srFocusLines(V);
  V.labelAt = 0;   // the tags placed again on the next frame
}

/* What the room draws on the page (px, in the canvas): each node's shape (a box round its cell, as tall as a model) and
   its tag (srTagOf, srTagWidth: 20 px over its point). */
function srFlowRoomRects(V) {
  const w = V.renderer.domElement.clientWidth, h = V.renderer.domElement.clientHeight, v = new THREE.Vector3(), out = [];
  const px = (x, y, z) => { v.set(x, y, z).project(V.camera); return [(v.x + 1) / 2 * w, (1 - v.y) / 2 * h, v.z]; };
  for (const p of V.L.pos.values()) {
    if (p.hiddenIn) continue;
    const pts = [];
    for (const dx of [-0.9, 0.9]) for (const dz of [-0.9, 0.9]) for (const dy of [0, 1.6]) pts.push(px(p.x + dx, p.y + dy, p.z + dz));
    out.push({ id: p.n.id, kind: 'shape', box: [Math.min(...pts.map((q) => q[0])), Math.min(...pts.map((q) => q[1])), Math.max(...pts.map((q) => q[0])), Math.max(...pts.map((q) => q[1]))],
      behind: pts.some((q) => q[2] > 1) });
    const t = srTagOf(V, p), a = px(...t.at), wd = srTagWidth(t.text);
    out.push({ id: p.n.id, kind: 'tag', box: [a[0] - wd / 2, a[1] - 20, a[0] + wd / 2, a[1]], behind: a[2] > 1 });
  }
  return out;
}
/* The shapes and tags not inside the seen part of the canvas ([id, kind]). */
function srFlowRoomOut(V) {
  const S = srFlowSeen(V);
  return srFlowRoomRects(V).filter((r) => r.behind || r.box[0] < S[0] || r.box[1] < S[1] || r.box[2] > S[2] || r.box[3] > S[3]).map((r) => [r.id, r.kind]);
}
/* The part of the canvas the room can be seen in (px): all of it but what the player's bar covers. */
function srFlowSeen(V) {
  const c = V.renderer.domElement.getBoundingClientRect(), bar = $('sr-player'), b = !bar.hidden && bar.getBoundingClientRect();
  return [0, 0, c.width, b && b.top > c.top ? Math.min(c.height, b.top - c.top) : c.height];
}
/* The camera moved (its distance in 3D, its span in 2D, the same way it looks) until every shape and tag is inside the
   seen part of the canvas with SR_FLOW.frame of it to spare round the edges; at the room's middle. */
function srFlowFrameRoom(V) {
  const L = V.L, cx = L.width / 2, cz = L.depth / 2, S = srFlowSeen(V), m = (1 - SR_FLOW.frame) / 2;
  const inner = [S[0] + (S[2] - S[0]) * m, S[1] + (S[3] - S[1]) * m, S[2] - (S[2] - S[0]) * m, S[3] - (S[3] - S[1]) * m];
  const dir = V.camera.position.clone().sub(V.controls.target).normalize();
  if (!(dir.lengthSq() > 0)) dir.set(0, 0.78, 0.62).normalize();
  const tan = 2 * Math.tan(SR_FLAT.fov * Math.PI / 360);
  const place = (d) => {
    if (V.flat) { srSetSpan(V, cx, cz, d * tan); return; }
    V.controls.target.set(cx, 0, cz); V.camera.position.copy(V.controls.target).addScaledVector(dir, d); V.camera.updateMatrixWorld();
  };
  const fits = (d) => { place(d); return srFlowRoomRects(V).every((r) => !r.behind && r.box[0] >= inner[0] && r.box[1] >= inner[1] && r.box[2] <= inner[2] && r.box[3] <= inner[3]); };
  let lo = V.controls.minDistance, hi = Math.max(srViewDist(V), lo);
  while (!fits(hi) && hi < V.controls.maxDistance) hi = Math.min(V.controls.maxDistance, hi * 2);
  for (let i = 0; i < 32 && hi - lo > 0.01; i++) { const mid = (lo + hi) / 2; if (fits(mid)) hi = mid; else lo = mid; }
  place(hi);
  if (!V.flat) { V.camera.far = Math.max(V.camera.far, hi * 6); V.camera.updateProjectionMatrix(); }
  V.controls.update();
}
/* The camera after a light about to leave the page: moved over the floor (the same distance, the same angle) until the
   light is well inside again. Not while the whole room is in view: there the light never leaves it. */
function srFlowWhole(V) {
  const v = new THREE.Vector3();
  for (const p of V.L.pos.values()) {
    if (p.hiddenIn) continue;
    v.set(p.x, p.y, p.z).project(V.camera);
    if (v.z > 1 || Math.abs(v.x) > 1.02 || Math.abs(v.y) > 1.02) return false;
  }
  return true;
}
function srFlowFollow(V, P, dt) {
  const moving = P.state === 'play' ? P.lights.filter((o) => o.userData.flowLight && o.userData.moving) : [];
  if (!moving.length) { V.flowFollowing = false; return; }
  const head = moving[moving.length - 1].userData.head, v = head.clone().project(V.camera), off = v.z > 1 ? Infinity : Math.max(Math.abs(v.x), Math.abs(v.y));
  if (!V.flowFollowing) {
    if (off <= SR_FLOW.follow.out) return;
    V.flowWhole = srFlowWhole(V);
    if (V.flowWhole) return;
    V.flowFollowing = true;
  } else if (off < SR_FLOW.follow.in) { V.flowFollowing = false; return; }
  const k = 1 - Math.exp(-dt / SR_FLOW.follow.ms), d = new THREE.Vector3(head.x - V.controls.target.x, 0, head.z - V.controls.target.z).multiplyScalar(k);
  V.controls.target.add(d); V.camera.position.add(d); V.camera.updateMatrixWorld();
  P.follows = (P.follows || 0) + 1;   // frames the camera went after the light (the e2e)
}

/* ---- each frame: the light along its edge, the next step when one is done */
function srFlowTick(V, dt) {
  const P = SR_FLOW.player;
  if (!P) return;
  const step = dt * SR_FLOW.speed;      // the speed is read every frame: changed while it plays, it applies at once
  const run = P.state === 'play';
  const advance = (A) => {
    if (!A) return true;
    if (A.kind === 'wait') { A.left -= step; if (A.left <= 0 && A.then) { A.then(); A.then = null; } return A.left <= 0; }
    if (A.rest !== null) { A.rest -= step; return A.rest <= 0; }   // resting at the node it reached
    A.done = Math.min(1, A.done + step / A.ms);
    srFlowLightAt(A.light, A.done);
    if (A.done < 1) return false;
    A.light.userData.moving = false;               // its tail drains into the node, on the same clock
    A.light.userData.left = SR_FLOW_LIGHT.drainMs;
    P.pos = A.step.to;
    P.seen.add(A.step.to);
    P.arrivals.push(srNow());
    P.reached.push([A.step.to, srNow()]);       // where and when (the e2e reads each move's time and each rest)
    srFlowSay(P, A.step, A.step.to);
    A.rest = SR_FLOW.restMs;
    return false;
  };
  if (run || P.stepOnce) {
    if (P.anim && P.anim.kind === 'lanes') {
      for (const L of P.anim.lanes) while (!L.done && advance(L.anim)) srFlowLaneNext(P, L);
      if (P.anim.lanes.every((L) => L.done)) { P.anim = null; if (P.stepOnce) { P.stepOnce = false; } else srFlowNext(P); }
    } else if (P.anim) {
      if (advance(P.anim)) { P.anim = null; if (P.stepOnce) P.stepOnce = false; else srFlowNext(P); }
    } else if (P.state === 'play') srFlowNext(P);
  }
  for (const o of P.lights) {
    if (!o.userData.flowLight) { srFlowKeepSize(V, o); continue; }
    if (!o.userData.moving) srFlowLightAt(o, 1 + (1 - Math.max(0, o.userData.left) / SR_FLOW_LIGHT.drainMs) * o.userData.tail);
    srFlowLightKeepSize(V, o);
  }
  if (P.state === 'branch' && SR_FLOW.auto && P.branch && P.branch.b.default && srNow() - P.branch.shownAt > 600 / SR_FLOW.speed) srFlowChoose(P.branch.b.default);
  srFlowShowApply(V);
  srFlowFollow(V, P, dt);
  for (const o of [...V.flowLayer.children]) if (o.userData.left !== undefined && (o.userData.left -= step) <= 0) {
    V.flowLayer.remove(o); P.lights = P.lights.filter((x) => x !== o);
    if (o.userData.flowLight) srFlowLightDispose(o);
  }
}

/* The player's bar over the 3D: the flow, play / pause, one step, back, stop, the speed, 自動, the nodes shown, the
   choices taken. */
function srFlowRenderBar() {
  const bar = $('sr-player'), P = SR_FLOW.player;
  if (!P) { bar.hidden = true; return; }
  bar.hidden = false;
  const playing = P.state === 'play';
  setHTML(bar, `<b class="sr-fp-title">${esc((SR_TRIGGERS[P.flow.trigger] || SR_TRIGGERS.user)[0])} ${esc(P.flow.label || P.flow.id)}</b>
<button type="button" class="wb-btn" data-sr-fp="toggle" aria-label="${esc(playing ? tl('sr.flow.pause') : tl('sr.flow.play'))}">${playing ? '⏸' : '▶'}</button>
<button type="button" class="wb-btn" data-sr-fp="step" aria-label="${esc(tl('sr.flow.step'))}">⏭</button>
<button type="button" class="wb-btn" data-sr-fp="back" aria-label="${esc(tl('sr.flow.back'))}"${P.history.length ? '' : ' disabled'}>⏮</button>
<button type="button" class="wb-btn" data-sr-fp="stop" aria-label="${esc(tl('sr.flow.stop'))}">■</button>
<label>${esc(tl('sr.flow.speed'))} <select data-sr-fp="speed">${SR_FLOW_SPEEDS.map((s) => `<option value="${esc(String(s))}"${s === SR_FLOW.speed ? ' selected' : ''}>${esc(s.toFixed(s * 2 % 1 ? 2 : 1))}×</option>`).join('')}</select></label>
<label><input type="checkbox" data-sr-fp="auto"${SR_FLOW.auto ? ' checked' : ''}> ${esc(tl('sr.flow.auto'))}</label>
<span class="sr-fp-show" role="group" aria-label="${esc(tl('sr.flow.show'))}">${Object.entries(SR_FLOW_SHOWS).map(([k, w]) => `<button type="button" class="wb-btn" data-sr-fp-show="${esc(k)}" title="${esc(w[1])}" aria-pressed="${k === SR_FLOW.show}">${esc(w[0])}</button>`).join('')}</span>
<span class="sr-fp-state">${esc(SR_FLOW_STATE[P.state] || '')}</span>
${P.chosen.length ? `<ol class="sr-fp-chosen">${P.chosen.map((c) => `<li>${esc(c)}</li>`).join('')}</ol>` : ''}`);
}
$('sr-player').addEventListener('click', (e) => {
  const show = e.target.closest('[data-sr-fp-show]');
  if (show) { srFlowShowSet(show.dataset.srFpShow); return; }
  const b = e.target.closest('[data-sr-fp]'), P = SR_FLOW.player;
  if (!b || !P || b.tagName === 'SELECT' || b.type === 'checkbox') return;
  const what = b.dataset.srFp;
  if (what === 'toggle') { P.state = P.state === 'play' ? 'pause' : (P.branch ? 'branch' : P.state === 'done' ? 'done' : 'play'); if (P.state === 'done') srFlowPlay(P.flow.id); }
  else if (what === 'step') { if (!P.anim && !P.branch) { P.stepOnce = true; srFlowNext(P); } }
  else if (what === 'back') srFlowBack();
  else if (what === 'stop') srFlowStop();
  srFlowRenderBar();
});
$('sr-player').addEventListener('change', (e) => {
  const t = e.target;
  if (t.dataset.srFp === 'speed') { SR_FLOW.speed = Number(t.value); srFlowPrefSet('speed', SR_FLOW.speed); }
  else if (t.dataset.srFp === 'auto') { SR_FLOW.auto = t.checked; srFlowChoices(); }
});
function srFlowShowSet(how) {
  if (!SR_FLOW_SHOWS[how]) return;
  SR_FLOW.show = how;
  srFlowPrefSet('show', how);
  if (SR.view && SR.view.flowLayer) srFlowShowApply(SR.view);
  srFlowRenderBar();
}
$('sr-choices').addEventListener('click', (e) => {
  const b = e.target.closest('[data-sr-choice]');
  if (b) srFlowChoose(b.dataset.srChoice);
});
$('sr-route-list').addEventListener('click', (e) => {
  const b = e.target.closest('[data-sr-rt]');
  if (b) srSelect(b.dataset.srRt);
});
