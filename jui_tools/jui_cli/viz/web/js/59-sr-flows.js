/* ---------- the server room's flows played (ticket 2026-10-20-jui-viz-server-room-lines-dark-filter-spec, item 7) ----------
   Requester 10-20: 「エンドユーザーのノード押したら選択肢が出る。その選択肢押したら通る経路がアニメーションしてどういう処理の流れになるかが
   視覚的にわかるようにしたい」; 「DBに保存とか読み取りとかS3にアップロードとかもパッとわかるようにしたいね … 吹き出しでもトーストで出る感じで
   いける？ 速度も0.5,1.0,1.5,2.0,3.0,5.0,10.0 みたいに選べるようにして」; 「任意のオブジェクトに設定できてほしい」; 「途中で分岐作って
   そこで止まって選択できるのもあると便利じゃない？」.

   The model's flows (infra/flows.py checked them: every move leaves the node the flow is at). A node that starts a
   flow drawn now carries a small green cone; choosing the node lists its flows on the board, and a flow chosen plays:
   - a light runs along each move's edge and the node it reaches glows; a toast over that node says what happened
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

/* The board's list for the chosen node: the flows it starts (none: nothing is added). */
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
  if (layer) for (const o of [...layer.children]) if (!o.userData.flowStarts) { layer.remove(o); if (o.geometry) o.geometry.dispose(); }
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
  const V = SR.view, a = srFlowPos(V, step.from), b = srFlowPos(V, step.to);
  const dot = new THREE.Mesh(new THREE.SphereGeometry(0.28, 12, 8), new THREE.MeshBasicMaterial({ color: 0xffcf33 }));
  dot.position.copy(a);
  V.flowLayer.add(dot);
  P.lights.push(dot);
  return { kind: 'move', step, a, b, dot, done: 0 };
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
  const lines = new THREE.LineSegments(g, new THREE.LineBasicMaterial({ color: 0xffcf33, transparent: true, opacity: 0.45 }));
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
  for (const d of P.lights) SR.view.flowLayer.remove(d);
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
  const ring = new THREE.Mesh(new THREE.TorusGeometry(0.75, 0.08, 6, 24), new THREE.MeshBasicMaterial({ color: 0xffcf33, transparent: true, opacity: 0.9 }));
  ring.position.set(p.x, p.y - 0.6, p.z); ring.rotation.x = Math.PI / 2;
  ring.userData.left = SR_FLOW.nodeMs * 2;
  SR.view.flowLayer.add(ring);
  P.lights.push(ring);
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
    const k = A.done, y = Math.sin(Math.PI * k) * 0.8;
    A.dot.position.lerpVectors(A.a, A.b, k); A.dot.position.y += y;
    if (k < 1) return false;
    V.flowLayer.remove(A.dot); A.dot.geometry.dispose();
    P.lights = P.lights.filter((x) => x !== A.dot);
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
  if (P.state === 'branch' && SR_FLOW.auto && P.branch && P.branch.b.default && srNow() - P.branch.shownAt > 600 / SR_FLOW.speed) srFlowChoose(P.branch.b.default);
  for (const o of [...V.flowLayer.children]) if (o.userData.left !== undefined && (o.userData.left -= step) <= 0) { V.flowLayer.remove(o); P.lights = P.lights.filter((x) => x !== o); }
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
