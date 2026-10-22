/* ---------- the server room's flows played (ticket 2026-10-20-jui-viz-server-room-lines-dark-filter-spec, item 7) ----------
   Requester 10-20: 「エンドユーザーのノード押したら選択肢が出る。その選択肢押したら通る経路がアニメーションしてどういう処理の流れになるかが
   視覚的にわかるようにしたい」; 「DBに保存とか読み取りとかS3にアップロードとかもパッとわかるようにしたいね … 吹き出しでもトーストで出る感じで
   いける？ 速度も0.5,1.0,1.5,2.0,3.0,5.0,10.0 みたいに選べるようにして」; 「任意のオブジェクトに設定できてほしい」; 「途中で分岐作って
   そこで止まって選択できるのもあると便利じゃない？」.

   The model's flows (infra/flows.py checked them: every move leaves the node the flow is at). A node that starts a
   flow drawn now carries a small green cone; choosing the node lists its flows on the board, and a flow chosen plays:
   - light runs through each move's edge, a bright head and a fading tail inside the cable (requester 10-22: 「ボールが跳ねる
     んじゃなくて同線に光が流れていくイメージで」), and the node it reaches glows; a toast over that node says what happened
     (the action's mark and verb after the node's name: 「💾 d1 に保存」, the step's label on a second line), and the
     first one says what started it (the trigger's mark: 👤 ⏰ 📡 ⚡, with a schedule as written);
   - a branch stops the light: its choices are buttons over the node, the first edge of each glows faintly ahead, and
     with 自動 on a default is taken by itself (none: it waits). goto plays the other flow (jumping when it starts
     elsewhere), join goes on at that step; the choices taken are listed (「KV に結果が有る？ → 無い」);
   - lanes side by side run at once, and the flow goes on when all of them are done;
   - play / pause, one step on, one step back (to a branch: choose again), stop; the speed one of SR_FLOW_SPEEDS,
     changed while it plays (the light and the toasts go by the same clock).
   A rebuild of the 3D (the environment, the clouds chosen, the theme) stops the flow playing: its light and toasts
   belonged to the 3D that went.
   SR_ACTIONS and SR_TRIGGERS are the schema's x-label / x-icon (test_viz_bundle holds them to the schema). */
const SR_FLOW_SPEEDS = [0.5, 1.0, 1.5, 2.0, 3.0, 5.0, 10.0];
const SR_ACTIONS = { request: ['→', tl('sr.flow.action.request')], response: ['←', tl('sr.flow.action.response')], read: ['📖', tl('sr.flow.action.read')], write: ['💾', tl('sr.flow.action.write')], upload: ['⬆', tl('sr.flow.action.upload')], download: ['⬇', tl('sr.flow.action.download')], invoke: ['⚡', tl('sr.flow.action.invoke')], enqueue: ['📥', tl('sr.flow.action.enqueue')], dequeue: ['📤', tl('sr.flow.action.dequeue')], publish: ['📣', tl('sr.flow.action.publish')], subscribe: ['📡', tl('sr.flow.action.subscribe')], auth: ['🔑', tl('sr.flow.action.auth')], schedule: ['⏰', tl('sr.flow.action.schedule')] };
const SR_TRIGGERS = { user: ['👤', tl('sr.flow.trigger.user')], device: ['📡', tl('sr.flow.trigger.device')], schedule: ['⏰', tl('sr.flow.trigger.schedule')], event: ['⚡', tl('sr.flow.trigger.event')] };
const SR_FLOW_STATE = { play: tl('sr.flow.state.play'), pause: tl('sr.flow.state.pause'), branch: tl('sr.flow.state.branch'), done: tl('sr.flow.state.done') };
const SR_FLOW = { speed: 1.0, auto: false, moveMs: 900, nodeMs: 450, toastMs: 2600, player: null };

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
  const P = SR_FLOW.player = { flow, frames: [{ steps: flow.steps, i: 0 }], pos: flow.start, state: 'play', anim: null, history: [],
    chosen: [], toasts: [], lights: [], branch: null, arrivals: [], reached: [], log: [], dirty: true };
  const t = SR_TRIGGERS[flow.trigger] || SR_TRIGGERS.user;
  srFlowToast(P, flow.start, `${t[0]} ${flow.label || flow.id}`, flow.schedule || t[1]);
  srFlowGlow(P, flow.start);
  srFlowRenderBar();
  return true;
}
function srFlowStop() {
  const P = SR_FLOW.player;
  if (!P) return;
  for (const x of P.toasts) x.el.remove();
  const layer = SR.view && SR.view.flowLayer;
  if (layer) for (const o of [...layer.children]) if (!o.userData.flowStarts) { layer.remove(o); if (o.userData.flowLight) srFlowLightDispose(o); else if (o.geometry) o.geometry.dispose(); }
  SR_FLOW.player = null;
  $('sr-choices').hidden = true;
  srFlowRenderBar();
}
function srFlowSnapshot(P) {
  return { flow: P.flow, frames: P.frames.map((f) => ({ steps: f.steps, i: f.i })), pos: P.pos, chosen: P.chosen.slice() };
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
    if (step.at || step.node) { srFlowSay(P, step, step.at || step.node); P.anim = { kind: 'wait', left: SR_FLOW.nodeMs }; return; }
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
  else { srFlowSay(P, s, s.at || s.node); L.anim = { kind: 'wait', left: SR_FLOW.nodeMs }; }
}
function srFlowMove(P, step) {
  const V = SR.view, light = srFlowLight(V, step.from, step.to);
  V.flowLayer.add(light);
  P.lights.push(light);
  return { kind: 'move', step, light, done: 0 };
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
function srFlowCableY(V, from, to) {
  const e = V.L.edges.find((x) => (x.from === from && x.to === to) || (x.from === to && x.to === from));
  return e && e.crossProvider ? 2.6 : 1.7;
}
function srFlowLight(V, from, to) {
  const pa = V.L.pos.get(from), pb = V.L.pos.get(to), y = srFlowCableY(V, from, to);
  const a = new THREE.Vector3(pa.x, y, pa.z), b = new THREE.Vector3(pb.x, y, pb.z), len = Math.max(a.distanceTo(b), 1e-3);
  const PAL = SR_PAL[V.dark ? 'dark' : 'light'], tail = Math.min(0.85, SR_FLOW_LIGHT.tail / len);
  const layer = (color, opacity, soft, white) => new THREE.ShaderMaterial({ vertexShader: SR_FLOW_LIGHT_SHADER.vertex, fragmentShader: SR_FLOW_LIGHT_SHADER.fragment,
    uniforms: { uColor: { value: new THREE.Color(color) }, uHead: { value: 0 }, uTail: { value: tail }, uOpacity: { value: opacity }, uSoft: { value: soft }, uWhite: { value: white } },
    transparent: true, depthWrite: false, blending: V.dark ? THREE.AdditiveBlending : THREE.NormalBlending });
  const tube = new THREE.CylinderGeometry(1, 1, 1, 12, 1, true);
  const glow = new THREE.Mesh(tube, layer(PAL.light, V.dark ? 0.75 : 0.85, 1, 0));
  const core = new THREE.Mesh(tube, layer(PAL.lightCore, 1, 0, V.dark ? 0.85 : 0.35));
  const light = new THREE.Group();
  light.add(glow, core);
  light.position.copy(a).add(b).multiplyScalar(0.5);
  light.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), b.clone().sub(a).normalize());
  glow.scale.set(SR_FLOW_LIGHT.glow, len, SR_FLOW_LIGHT.glow); core.scale.set(SR_FLOW_LIGHT.core, len, SR_FLOW_LIGHT.core);
  light.renderOrder = glow.renderOrder = core.renderOrder = 3;
  light.userData = { flowLight: true, moving: true, a, b, head: a.clone(), glow, core, tail };
  return light;
}
/* The head at k (0: the cable's start, 1: its end, past 1: the tail draining). */
function srFlowLightAt(o, k) {
  for (const m of [o.userData.glow, o.userData.core]) m.material.uniforms.uHead.value = k;
  o.userData.head.lerpVectors(o.userData.a, o.userData.b, Math.min(k, 1));
}
/* Pulled back, the glow is drawn at least SR_FLOW_MIN_PX in radius at its head (the core a third of that). */
function srFlowLightKeepSize(V, o) {
  const px = srFlowPxPerUnit(V, o.userData.head), g = Math.max(SR_FLOW_LIGHT.glow, SR_FLOW_MIN_PX / px), c = Math.max(SR_FLOW_LIGHT.core, SR_FLOW_MIN_PX / 3 / px);
  o.userData.glow.scale.x = o.userData.glow.scale.z = g;
  o.userData.core.scale.x = o.userData.core.scale.z = c;
}
function srFlowLightDispose(o) {
  o.userData.glow.geometry.dispose();
  for (const m of [o.userData.glow, o.userData.core]) m.material.dispose();
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
  srFlowHints(P, b);
  const box = $('sr-choices');
  setHTML(box, `<p class="sr-choice-q">${esc(b.label)}</p>${b.choices.map((c) => `<button type="button" class="wb-btn" data-sr-choice="${esc(c.id)}"${c.id === b.default ? ' data-default' : ''}>${esc(c.label)}${c.id === b.default ? ` <small>${esc(tl('sr.flow.choice.default'))}</small>` : ''}</button>`).join('')}`);
  box.hidden = false;
  srFlowRenderBar();
}
/* Each choice's first edge, faint, while the branch waits. */
function srFlowHints(P, b) {
  const V = SR.view, arr = [];
  for (const c of b.choices) {
    const first = (c.steps || []).find((s) => s.from && s.to);
    if (!first) continue;
    const a = srFlowPos(V, first.from), z = srFlowPos(V, first.to);
    if (a && z) arr.push(a.x, a.y, a.z, z.x, z.y, z.z);
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.Float32BufferAttribute(arr, 3));
  const lines = new THREE.LineSegments(g, new THREE.LineBasicMaterial({ color: SR_PAL[V.dark ? 'dark' : 'light'].light, transparent: true, opacity: 0.45 }));
  lines.userData.hints = arr.length / 6;
  V.flowLayer.add(lines);
  P.hints = lines;
}
function srFlowChoose(id) {
  const P = SR_FLOW.player;
  if (!P || !P.branch) return false;
  const b = P.branch.b, c = b.choices.find((x) => x.id === id);
  if (!c) return false;
  P.chosen.push(`${b.label} → ${c.label}`);
  P.branch = null;
  $('sr-choices').hidden = true;
  if (P.hints) { SR.view.flowLayer.remove(P.hints); P.hints.geometry.dispose(); P.hints = null; }
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
  P.flow = s.flow; P.frames = s.frames; P.pos = s.pos; P.chosen = s.chosen;
  P.branch = null; $('sr-choices').hidden = true;
  if (P.hints) { SR.view.flowLayer.remove(P.hints); P.hints = null; }
  for (const d of P.lights) { SR.view.flowLayer.remove(d); if (d.userData.flowLight) srFlowLightDispose(d); }
  P.lights = []; P.anim = null; P.state = 'pause';
  srFlowRenderBar();
  return true;
}
function srFlowToast(P, at, head, sub) {
  const el = document.createElement('div');
  el.className = 'sr-toast';
  el.innerHTML = `<b>${esc(head)}</b>${sub ? `<span>${esc(sub)}</span>` : ''}`;
  $('sr-toasts').append(el);
  P.toasts.push({ el, at, left: SR_FLOW.toastMs });
  P.log.push(head);
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
  const d = V.camera.position.distanceTo(at);
  return V.renderer.domElement.clientHeight / (2 * Math.max(d, 1e-3) * Math.tan(V.camera.fov * Math.PI / 360));
}
function srFlowKeepSize(V, o) {
  if (!o.userData.r) return;
  o.scale.setScalar(Math.max(1, o.userData.minPx / (o.userData.r * srFlowPxPerUnit(V, o.position))));
}

/* ---- each frame: the light along its edge, the toasts' places and lives, the next step when one is done */
function srFlowTick(V, dt) {
  const P = SR_FLOW.player;
  if (!P) return;
  const step = dt * SR_FLOW.speed;      // the speed is read every frame: changed while it plays, it applies at once
  const run = P.state === 'play';
  const advance = (A) => {
    if (!A) return true;
    if (A.kind === 'wait') { A.left -= step; return A.left <= 0; }
    A.done = Math.min(1, A.done + step / SR_FLOW.moveMs);
    srFlowLightAt(A.light, A.done);
    if (A.done < 1) return false;
    A.light.userData.moving = false;               // its tail drains into the node, on the same clock
    A.light.userData.left = SR_FLOW_LIGHT.drainMs;
    P.pos = A.step.to;
    P.arrivals.push(srNow());
    P.reached.push([A.step.to, srNow()]);       // where and when (the e2e reads that lanes arrive together)
    srFlowSay(P, A.step, A.step.to);
    return true;
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
  for (const o of [...V.flowLayer.children]) if (o.userData.left !== undefined && (o.userData.left -= step) <= 0) {
    V.flowLayer.remove(o); P.lights = P.lights.filter((x) => x !== o);
    if (o.userData.flowLight) srFlowLightDispose(o);
  }
  // the toasts over their nodes, stacked when several are on one
  const w = V.renderer.domElement.clientWidth, h = V.renderer.domElement.clientHeight, per = {};
  P.toasts = P.toasts.filter((x) => { x.left -= step; if (x.left > 0) return true; x.el.remove(); return false; });
  for (const x of P.toasts.slice().reverse()) {
    const p = srFlowPos(V, x.at);
    if (!p) continue;
    const v = p.clone(); v.y += 1.6; v.project(V.camera);
    const n = per[x.at] = (per[x.at] || 0) + 1;
    x.el.style.transform = `translate(${Math.round((v.x + 1) / 2 * w)}px, ${Math.round((1 - v.y) / 2 * h - (n - 1) * 44)}px) translate(-50%, -100%)`;
  }
  if (P.branch) {
    const p = srFlowPos(V, P.branch.at);
    if (p) { const v = p.clone(); v.y -= 1.0; v.project(V.camera); $('sr-choices').style.transform = `translate(${Math.round((v.x + 1) / 2 * w)}px, ${Math.round((1 - v.y) / 2 * h)}px) translate(-50%, 0)`; }
  }
}

/* The player's bar over the 3D: the flow, play / pause, one step, back, stop, the speed, 自動, the choices taken. */
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
<label>${esc(tl('sr.flow.speed'))} <select data-sr-fp="speed">${SR_FLOW_SPEEDS.map((s) => `<option value="${esc(String(s))}"${s === SR_FLOW.speed ? ' selected' : ''}>${esc(s.toFixed(1))}×</option>`).join('')}</select></label>
<label><input type="checkbox" data-sr-fp="auto"${SR_FLOW.auto ? ' checked' : ''}> ${esc(tl('sr.flow.auto'))}</label>
<span class="sr-fp-state">${esc(SR_FLOW_STATE[P.state] || '')}</span>
${P.chosen.length ? `<ol class="sr-fp-chosen">${P.chosen.map((c) => `<li>${esc(c)}</li>`).join('')}</ol>` : ''}`);
}
$('sr-player').addEventListener('click', (e) => {
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
  if (t.dataset.srFp === 'speed') SR_FLOW.speed = Number(t.value);
  else if (t.dataset.srFp === 'auto') SR_FLOW.auto = t.checked;
});
$('sr-choices').addEventListener('click', (e) => {
  const b = e.target.closest('[data-sr-choice]');
  if (b) srFlowChoose(b.dataset.srChoice);
});
