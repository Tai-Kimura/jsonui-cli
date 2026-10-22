/* ---------- the server room's migration plans played (ticket 2026-10-22-viz-infra-migration-plan) ----------
   Requester 10-22: 「インフラの機能でサーバー移管計画をビジュアライズする機能がほしい / 今のjsonと変更箇所のjsonを組み合わせることで
   それをマージした新インフラになる / 移管ボタンを押すと一個ずつノードが切り替わっていく / 削除のjsonも用意する必要がある / 新旧でid同じ
   ノードは差し替え / 違うidは追加のアニメーション / 新に変わる時にルートが切れる線はアニメーションで消える / 逆にルート追加は光の線で
   繋がっていくアニメーション」; 「コストの差の表示は欲しいね」.

   The room's read gives its plans (document_tools' infra.migration: "migrations", each with its steps, its problems
   in words and the new model). The board lists them; a plan with an error says why and cannot be played. 移管 lays
   out the old model and the new together (every node of either has its cell, so nothing moves while it plays), shows
   the old, and the player takes it one step at a time:
   - add: the node grows in its cell; remove: it shrinks away; replace: the old shape shrinks and the new one (its
     shape, its cloud's colour, up close its model) grows in its place — the room is drawn again at that moment, the
     camera where it was;
   - an edge that goes shrinks to its middle and is gone; an edge that comes is drawn from its start to its end with
     the flows' light at its head (59-sr-flows.js srFlowLight), after the node it needs is there;
   - a floor of a group the new model has alone comes with its first node; one the new model has not goes at the end.
   play / pause, one step on, back to the start, stop (the old room again), the speed — the flows' player's buttons.
   The month's cost, when the room has load definitions (infra.cost.diff: the engine's months of the old model, of the
   model after each step and of the new, each priced on its own): 旧 → 今の歩 → 新 on the player, with the step's
   difference; the コスト view lists 旧 · 新 · 差 by node and by cloud.
   While a plan is open the room's flows are not offered (they are the old model's). */
const SR_MIG = { stepMs: 1600, speed: 1.0, P: null };
const SR_MIG_KIND = { add: (node) => tl('sr.mig.kind.add', { node }), remove: (node) => tl('sr.mig.kind.remove', { node }),
  replace: (node) => tl('sr.mig.kind.replace', { node }), edges: () => tl('sr.mig.kind.edges') };
const SR_MIG_DONE = { add: (s) => tl('sr.mig.log.add', { node: s.node }), remove: (s) => tl('sr.mig.log.remove', { node: s.node }),
  replace: (s) => tl('sr.mig.log.replace', { node: s.node }), edges: (s) => tl('sr.mig.log.edges', { n: s.edgesAdded.length + s.edgesRemoved.length }) };
const SR_MIG_CHANGE = { added: tl('sr.mig.change.added'), replaced: tl('sr.mig.change.replaced'), removed: tl('sr.mig.change.removed') };

function srMigPlans() { return ((SR.migBase || SR.model || {}).migrations) || []; }
const srMigClamp = (x) => Math.max(0, Math.min(1, x));

/* The old model and the new laid out together: the old version of a node replaced until its step is past (or half
   done: ``half``), then the new; the new model's own nodes, groups and edges after the old ones. */
function srMigUnion(base, entry, k, half) {
  const at = srMigAt(entry), newNodes = new Map(entry.model.nodes.map((n) => [n.id, n]));
  const oldIds = new Set((base.nodes || []).map((n) => n.id));
  const isNew = (id) => at[id] && (k >= at[id] || half === at[id]);
  const nodes = (base.nodes || []).map((n) => (isNew(n.id) && newNodes.has(n.id) ? newNodes.get(n.id) : n));
  for (const n of entry.model.nodes) if (!oldIds.has(n.id)) nodes.push(n);
  const oldGroups = new Set((base.groups || []).map((g) => g.id));
  const groups = (base.groups || []).concat(entry.model.groups.filter((g) => !oldGroups.has(g.id)));
  const oldKeys = new Set((base.edges || []).map(srMigKey));
  const edges = (base.edges || []).concat(entry.model.edges.filter((e) => !oldKeys.has(srMigKey(e))));
  const envIds = new Set((base.environments || []).map((e) => e.id));
  const environments = (base.environments || []).concat((entry.model.environments || []).filter((e) => !envIds.has(e.id)));
  return { ...base, nodes, groups, edges, environments, flows: [] };
}
function srMigKey(e) { return e.id ? e.id : `${e.from}->${e.to}`; }
function srMigAt(entry) {
  if (!entry._at) { entry._at = {}; for (const s of entry.steps) if (s.node) entry._at[s.node] = s.index; }
  return entry._at;
}
function srMigEdgeSteps(entry) {
  if (!entry._edges) {
    entry._edges = { out: {}, in: {} };
    for (const s of entry.steps) { for (const k of s.edgesRemoved) entry._edges.out[k] = s.index; for (const k of s.edgesAdded) entry._edges.in[k] = s.index; }
  }
  return entry._edges;
}

/* ---- what is drawn now: a node's size (0 gone, 1 there), an edge's length (0..1, and how it goes) */
function srMigNodeScale(id) {
  const P = SR_MIG.P;
  if (!P) return 1;
  const i = srMigAt(P.entry)[id];
  if (!i) return 1;
  const kind = P.entry.steps[i - 1].kind, A = P.anim && P.anim.i === i ? P.anim : null;
  if (A) {
    const t = A.t;
    if (kind === 'add') return srMigClamp(t / 0.4);
    if (kind === 'remove') return 1 - srMigClamp((t - 0.4) / 0.6);
    return t < 0.5 ? 1 - srMigClamp(t / 0.5) : srMigClamp((t - 0.5) / 0.5);
  }
  if (kind === 'add') return P.k >= i ? 1 : 0;
  if (kind === 'remove') return P.k >= i ? 0 : 1;
  return 1;
}
function srMigHides(id) { return !!SR_MIG.P && srMigNodeScale(id) <= 0.001; }
function srMigEdge(e) {
  const P = SR_MIG.P;
  if (!P) return { v: 1, mode: 'grow' };
  const key = srMigKey(e), E = srMigEdgeSteps(P.entry), out = E.out[key], inn = E.in[key];
  if (out && inn) return { v: 1, mode: 'grow', lit: P.anim && P.anim.i === inn ? srMigClamp((P.anim.t - 0.45) / 0.55) : null };   // replaced: it stays
  if (out) {
    if (P.anim && P.anim.i === out) return { v: 1 - srMigClamp(P.anim.t / 0.5), mode: 'shrink' };
    return { v: P.k >= out ? 0 : 1, mode: 'shrink' };
  }
  if (inn) {
    if (P.anim && P.anim.i === inn) { const g = srMigClamp((P.anim.t - 0.45) / 0.55); return { v: g, mode: 'grow', lit: g > 0 && g < 1 ? g : null }; }
    return { v: P.k >= inn ? 1 : 0, mode: 'grow' };
  }
  return { v: 1, mode: 'grow' };
}
function srMigEdgeHidden(e) { return !!SR_MIG.P && srMigEdge(e).v <= 0.001; }

/* ---- the board's plans */
function srMigBoardHTML() {
  const plans = srMigPlans();
  if (!plans.length) return '';
  const P = SR_MIG.P;
  return `<h3>${esc(tl('sr.mig.board.title'))}</h3><ul class="sr-migs">${plans.map((m) => {
    const c = m.counts || {}, errs = (m.problems || []).filter((p) => p.severity === 'error');
    return `<li><button type="button" class="wb-btn" data-sr-mig="${esc(m.name)}"${m.ok ? '' : ' disabled'} aria-pressed="${P && P.entry.name === m.name ? 'true' : 'false'}">${esc(tl('sr.mig.play', { name: m.name }))}</button>
${m.ok ? `<small>${esc(tl('sr.mig.counts', { steps: m.steps.length, add: c.added || 0, replace: c.replaced || 0, remove: c.removed || 0 }))}</small>` : ''}
${(m.problems || []).length ? `<ul class="sr-problems" data-sr-mig-problems="${esc(m.name)}">${m.problems.slice(0, 20).map((p) => `<li title="${esc(p.message || '')}">${esc(p.short || p.message || '')}</li>`).join('')}</ul>` : ''}
${errs.length ? `<p class="sr-hint">${esc(tl('sr.mig.cannot'))}</p>` : ''}</li>`; }).join('')}</ul>`;
}

/* ---- opening, the steps, closing */
function srMigStart(name) {
  const base = SR.migBase || SR.model, entry = srMigPlans().find((m) => m.name === name);
  if (!entry || !entry.ok || SR.phase !== 'open') return false;
  if (SR_MIG.P) srMigStop(true);
  srFlowStop();
  SR.migBase = base;
  SR_MIG.P = { entry, k: 0, anim: null, state: 'pause', half: null, cost: null, costSeq: 0, lights: new Map(), log: [] };
  srMigRebuild(true);
  srLog(tl('sr.mig.log.start', { name, n: entry.steps.length }));
  srMigCost();
  return true;
}
function srMigStop(quiet) {
  const P = SR_MIG.P;
  if (!P) return false;
  SR_MIG.P = null;
  SR.model = SR.migBase; SR.migBase = null;
  if (!quiet) { srMigRebuild(); srLog(tl('sr.mig.log.stop', { name: P.entry.name })); }
  srMigRenderBar();
  return true;
}
/* The room drawn again for the plan's state, the camera kept (srFit only when it opens). */
function srMigRebuild(first) {
  const V = SR.view, P = SR_MIG.P;
  if (P) SR.model = srMigUnion(SR.migBase, P.entry, P.k, P.half);
  if (!V) return;
  const pos = V.camera.position.clone(), target = V.controls.target.clone();
  srBuild();
  if (!first) { const W = SR.view; W.camera.position.copy(pos); W.controls.target.copy(target); W.controls.update(); }
}
function srMigReset() {
  const P = SR_MIG.P;
  if (!P) return;
  srMigLightsClear(SR.view);
  Object.assign(P, { k: 0, anim: null, state: 'pause', half: null });
  srMigRebuild();
}
function srMigStepOn() {
  const P = SR_MIG.P;
  if (!P || P.anim || P.k >= P.entry.steps.length) return false;
  const s = P.entry.steps[P.k];
  P.anim = { i: s.index, t: 0 };
  P.log.push(s.node || 'edges');
  return true;
}
function srMigCost() {
  const P = SR_MIG.P;
  if (!P || typeof SOURCE.infraCost !== 'function') return;
  const seq = ++P.costSeq;
  SOURCE.infraCost(SR.project, { seq, migration: P.entry.name }).then((got) => {
    if (SR_MIG.P !== P || seq !== P.costSeq) return;
    P.cost = got && got.ok ? got : { ok: false, message: (got && (got.message || got.reason)) || '' };
    srMigRenderBar();
    if (typeof srcRender === 'function' && typeof SRC !== 'undefined' && SRC.mode === 'cost') srcRender();
  });
}

/* ---- after each build: the index of what the plan changes, and its state drawn */
function srMigAfterBuild(V) {
  const P = SR_MIG.P;
  srMigRenderBar();
  if (!P) return;
  V.migLayer = new THREE.Group();
  V.near.add(V.migLayer);
  P.lights = new Map();
  const at = srMigAt(P.entry), E = srMigEdgeSteps(P.entry);
  V.migNodes = new Map();
  srMigIndexNodes(V, at);
  V.migEdges = [];
  const segs = { plain: 0, cross: 0 };
  for (const e of V.L.edges) {   // the same order srBuild laid them in: a segment each
    const set = e.crossProvider ? 'cross' : 'plain', j = segs[set]++;
    const key = srMigKey(e);
    if (E.out[key] || E.in[key]) {
      const a = V.L.pos.get(e.from), b = V.L.pos.get(e.to), y = e.crossProvider ? 2.6 : 1.7;
      V.migEdges.push({ e, key, line: set === 'cross' ? V.crossLines : V.plainLines, j, a: [a.x, y, a.z], b: [b.x, y, b.z], v: -1 });
    }
  }
  V.migFloors = V.L.floors.map((G, i) => ({ G, i }));
  srMigApply(V, true);
}
function srMigIndexNodes(V, at) {
  V.migNodes.clear();
  const meshes = [...V.nodeMeshes.simple, ...V.nodeMeshes.detail];
  V.near.traverse((o) => { if (o.isInstancedMesh && o.userData.icon && o.userData.nodes) meshes.push(o); });
  const m4 = new THREE.Matrix4();
  for (const mesh of meshes) mesh.userData.nodes.forEach((id, i) => {
    if (!at[id]) return;
    mesh.getMatrixAt(i, m4);
    const pos = new THREE.Vector3(), q = new THREE.Quaternion(), sc = new THREE.Vector3();
    m4.decompose(pos, q, sc);
    (V.migNodes.get(id) || V.migNodes.set(id, []).get(id)).push({ mesh, i, pos, q, sc, s: -1 });
  });
  V.migIcons = V.iconCount || 0;
}
/* The plan's state on the 3D: sizes of the nodes it changes (their shapes, icons, models up close), the edges'
   lengths, the floors, the lights on the edges coming in. Only what changed is written. */
function srMigApply(V, all) {
  const P = SR_MIG.P;
  if (!P || !V.migNodes) return;
  if ((V.iconCount || 0) !== V.migIcons) srMigIndexNodes(V, srMigAt(P.entry));   // the icons come after the build
  const m4 = new THREE.Matrix4(), sc = new THREE.Vector3(), touched = new Set();
  for (const [id, list] of V.migNodes) {
    const s = srMigNodeScale(id);
    for (const it of list) {
      if (!all && Math.abs(it.s - s) < 1e-4) continue;
      it.s = s;
      it.mesh.setMatrixAt(it.i, m4.compose(it.pos, it.q, sc.copy(it.sc).multiplyScalar(Math.max(s, 1e-4))));
      touched.add(it.mesh);
    }
  }
  for (const mesh of touched) { mesh.instanceMatrix.needsUpdate = true; mesh.boundingSphere = null; }
  if (V.models) for (const g of V.models.values()) {
    if (!srMigAt(P.entry)[g.userData.node]) continue;
    const s = srMigNodeScale(g.userData.node);
    g.scale.setScalar((g.userData.base || 1) * Math.max(s, 1e-4)); g.visible = s > 0.001;
  }
  const lines = new Set();
  for (const M of V.migEdges) {
    const st = srMigEdge(M.e);
    if (!all && Math.abs(M.v - st.v) < 1e-4 && M.mode === st.mode) { srMigLight(V, M, st); continue; }
    M.v = st.v; M.mode = st.mode;
    const arr = M.line.geometry.attributes.position.array, o = M.j * 6, a = M.a, b = M.b;
    for (let c = 0; c < 3; c++) {
      if (st.mode === 'shrink') { const mid = (a[c] + b[c]) / 2; arr[o + c] = mid + (a[c] - mid) * st.v; arr[o + 3 + c] = mid + (b[c] - mid) * st.v; }
      else { arr[o + c] = a[c]; arr[o + 3 + c] = a[c] + (b[c] - a[c]) * st.v; }
    }
    lines.add(M.line);
    srMigLight(V, M, st);
  }
  for (const l of lines) { l.geometry.attributes.position.needsUpdate = true; l.geometry.computeBoundingSphere(); if (l.material.isLineDashedMaterial) l.computeLineDistances(); }
  srMigFloors(V);
}
/* An edge coming in: the flows' light at its head while it is drawn. */
function srMigLight(V, M, st) {
  const P = SR_MIG.P;
  let light = P.lights.get(M.key);
  if (st.lit === null || st.lit === undefined) {
    if (light) { V.migLayer.remove(light); srFlowLightDispose(light); P.lights.delete(M.key); }
    return;
  }
  if (!light) { light = srFlowLight(V, M.e.from, M.e.to); V.migLayer.add(light); P.lights.set(M.key, light); }
  srFlowLightAt(light, st.lit);
  srFlowLightKeepSize(V, light);
}
function srMigLightsClear(V) {
  const P = SR_MIG.P;
  if (!P || !V || !V.migLayer) return;
  for (const l of P.lights.values()) { V.migLayer.remove(l); srFlowLightDispose(l); }
  P.lights.clear();
}
/* A floor is drawn while something on it is (a group of the new model alone comes with its first node), and one the
   new model has not goes with the last step. */
function srMigFloors(V) {
  const P = SR_MIG.P, mesh = V.floorMesh;
  if (!mesh) return;
  const oldG = new Set((SR.migBase.groups || []).map((g) => g.id)), newG = new Set(P.entry.model.groups.map((g) => g.id));
  const end = P.k >= P.entry.steps.length && !P.anim;
  const shown = (G) => G.nodes.some((n) => !srMigHides(n.id)) || G.kids.some(shown);
  const m4 = new THREE.Matrix4(), pos = new THREE.Vector3(), q = new THREE.Quaternion(), sc = new THREE.Vector3();
  V.migFloorBase = V.migFloorBase || V.L.floors.map((G, i) => { mesh.getMatrixAt(i, m4); const p = new THREE.Vector3(), r = new THREE.Quaternion(), s = new THREE.Vector3(); m4.decompose(p, r, s); return [p, r, s]; });
  let changed = false;
  V.migFloorShown = [];
  V.L.floors.forEach((G, i) => {
    const id = G.g.id, inOld = !id || oldG.has(id), inNew = !id || newG.has(id);
    const on = inOld && !inNew ? !end || shown(G) : !inOld ? shown(G) || end : true;
    if (on) V.migFloorShown.push(id);
    const [p, r, s] = V.migFloorBase[i];
    mesh.getMatrixAt(i, m4); m4.decompose(pos, q, sc);
    const want = on ? 1 : 0;
    if (Math.abs(sc.x - s.x * Math.max(want, 1e-4)) > 1e-6) { mesh.setMatrixAt(i, m4.compose(p, r, s.clone().multiplyScalar(Math.max(want, 1e-4)))); changed = true; }
  });
  if (changed) { mesh.instanceMatrix.needsUpdate = true; mesh.boundingSphere = null; }
}

/* ---- each frame: the step playing, the next one when it is done */
function srMigTick(V, dt) {
  const P = SR_MIG.P;
  if (!P || !V.migNodes || P.rebuilding) return;
  if (!P.anim && P.state === 'play') { if (!srMigStepOn()) { P.state = 'done'; srMigRenderBar(); } }
  if (P.anim) {
    const kind = P.entry.steps[P.anim.i - 1].kind, before = P.anim.t;
    P.anim.t = reduceMotion ? 1 : Math.min(1, P.anim.t + dt * SR_MIG.speed / SR_MIG.stepMs);
    if (kind === 'replace' && before < 0.5 && P.anim.t >= 0.5) {   // the new shape: the room drawn again, then it grows
      P.half = P.anim.i; P.rebuilding = true;
      setTimeout(() => { if (SR_MIG.P === P) { P.rebuilding = false; srMigRebuild(); } }, 0);
      return;
    }
    if (P.anim.t >= 1) {
      P.k = P.anim.i; P.anim = null; P.half = null;
      const s = P.entry.steps[P.k - 1];
      srLog(SR_MIG_DONE[s.kind](s));
      if (P.k >= P.entry.steps.length) P.state = 'done';
      else if (P.state === 'step') P.state = 'pause';
      srMigApply(V, false);
      srMigLightsClear(V);
      srMigRenderBar();
      return;
    }
  }
  srMigApply(V, false);
}
/* ---- the player's bar: the plan, play / pause, one step, back to the start, stop, the speed, the cost */
function srMigRenderBar() {
  const bar = $('sr-mplayer'), P = SR_MIG.P;
  if (!bar) return;
  if (!P) { bar.hidden = true; setHTML(bar, ''); return; }
  bar.hidden = false;
  const n = P.entry.steps.length, playing = P.state === 'play', cur = P.anim ? P.entry.steps[P.anim.i - 1] : P.k ? P.entry.steps[P.k - 1] : null;
  const what = cur ? SR_MIG_KIND[cur.kind](cur.node || '') : tl('sr.mig.old');
  const C = P.cost;
  let costHTML = '';
  if (C && C.ok) {
    const nowUsd = P.k ? C.steps[P.k - 1].usd : C.old.usd, stepDiff = cur ? C.steps[cur.index - 1].diff : null;   // the step shown
    costHTML = `<span class="sr-mp-cost" data-sr-mp-cost>${esc(tl('sr.mig.cost', { old: srcUsd(C.old.usd), now: srcUsd(nowUsd), new: srcUsd(C.new.usd) }))}${stepDiff !== null ? ` <b data-sr-mp-diff>${esc(tl('sr.mig.cost.step', { diff: srMigSigned(stepDiff) }))}</b>` : ''}</span>`;
  } else if (C && !C.ok) costHTML = `<span class="sr-fp-state">${esc(tl('sr.mig.cost.none'))}</span>`;
  setHTML(bar, `<b class="sr-fp-title">${esc(tl('sr.mig.title', { name: P.entry.name }))}</b>
<button type="button" class="wb-btn" data-sr-mp="toggle" aria-label="${esc(playing ? tl('sr.flow.pause') : tl('sr.mig.go'))}">${playing ? '⏸' : '▶'}</button>
<button type="button" class="wb-btn" data-sr-mp="step" aria-label="${esc(tl('sr.flow.step'))}"${P.k >= n ? ' disabled' : ''}>⏭</button>
<button type="button" class="wb-btn" data-sr-mp="reset" aria-label="${esc(tl('sr.mig.reset'))}"${P.k || P.anim ? '' : ' disabled'}>⏮</button>
<button type="button" class="wb-btn" data-sr-mp="stop" aria-label="${esc(tl('sr.mig.stop'))}">■</button>
<label>${esc(tl('sr.flow.speed'))} <select data-sr-mp="speed">${SR_FLOW_SPEEDS.map((s) => `<option value="${esc(String(s))}"${s === SR_MIG.speed ? ' selected' : ''}>${esc(s.toFixed(1))}×</option>`).join('')}</select></label>
<span class="sr-fp-state" data-sr-mp-step>${esc(tl('sr.mig.at', { k: P.anim ? P.anim.i : P.k, n }))} · ${esc(what)}</span>
${costHTML}`);
}
function srMigSigned(v) { return `${v >= 0 ? '+' : '−'}${srcUsd(Math.abs(v))}`; }
$('sr-mplayer').addEventListener('click', (e) => {
  const b = e.target.closest('[data-sr-mp]'), P = SR_MIG.P;
  if (!b || !P || b.tagName === 'SELECT') return;
  const what = b.dataset.srMp;
  if (what === 'toggle') {
    if (P.state === 'play') P.state = 'pause';
    else { if (P.k >= P.entry.steps.length && !P.anim) srMigReset(); SR_MIG.P.state = 'play'; }
  } else if (what === 'step') { if (!P.anim && srMigStepOn()) P.state = 'step'; }
  else if (what === 'reset') srMigReset();
  else if (what === 'stop') { srMigStop(); return; }
  srMigRenderBar();
});
$('sr-mplayer').addEventListener('change', (e) => { if (e.target.dataset.srMp === 'speed') SR_MIG.speed = Number(e.target.value); });

/* ---- the cost view's columns: old, new and the difference, by node and by cloud (56-server-cost.js srcRender puts
   them under the month) */
function srMigCostHTML() {
  const P = SR_MIG.P, C = P && P.cost;
  if (!C || !C.ok) return '';
  const rowsHTML = (list, key) => list.filter((r) => r.old || r.new || (r.change && r.change !== 'same')).slice(0, 15).map((r) => `<tr data-sr-mig-row="${esc(r[key])}"><th scope="row">${esc(r[key] || '—')}${SR_MIG_CHANGE[r.change] ? ` <small>${esc(SR_MIG_CHANGE[r.change])}</small>` : ''}</th><td>${esc(srcUsd(r.old))}</td><td>${esc(srcUsd(r.new))}</td><td class="${r.diff > 0 ? 'src-up' : r.diff < 0 ? 'src-down' : ''}">${esc(srMigSigned(r.diff))}</td></tr>`).join('');
  const headHTML = `<thead><tr><th></th><th scope="col">${esc(tl('sr.mig.col.old'))}</th><th scope="col">${esc(tl('sr.mig.col.new'))}</th><th scope="col">${esc(tl('sr.mig.col.diff'))}</th></tr></thead>`;
  return `<section class="src-mig" data-src-mig><h3>${esc(tl('sr.mig.cost.title', { name: P.entry.name }))}</h3>
<p>${esc(tl('sr.mig.cost', { old: srcUsd(C.old.usd), now: srcUsd(P.k ? C.steps[P.k - 1].usd : C.old.usd), new: srcUsd(C.new.usd) }))} <b>${esc(srMigSigned(C.diff.usd))}</b></p>
<table class="src-mig-t" data-src-mig-nodes>${headHTML}<tbody>${rowsHTML(C.byNode, 'node')}</tbody></table>
<table class="src-mig-t" data-src-mig-clouds>${headHTML}<tbody>${rowsHTML(C.byProvider, 'provider')}</tbody></table></section>`;
}
