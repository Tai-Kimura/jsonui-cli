/* ---------- the server room (ticket 2026-10-20-jui-viz-server-room, part B) ----------
   Requester 10-20: 「各リポジトリの部屋にサーバールームの扉を置く そこクリックで全体をサーバールームの3Dページに遷移させる。（3Dモデル以外の
   表示は全て消せるもの（ボード、ログだけにする） そこにはインフラの構成のモデルが表示され、ビジュアルで構成がわかる」; 「かなり大きい構成でも
   使えるようにズームの引き出来るようにしてね あと複数プロバイダを跨げるようにもして欲しい」; 「読み込みに時間かかりそうならサーバールーム
   クリックしたタイミングで処理走らせてアニメーションは壁についてるパネルにパスワード打ち込んでるように」; 「吹き出しでサーバー構成を読み込んで
   いますを出す」; 「サーバールームのjsonにエラーがあって読めない場合はパスワード入力失敗のアニメーションとエラーの吹き出し出して」.

   The door (40-scene.js) → srEnter: the model is read then and never before (SOURCE.infraDocs: the room's id and this
   press's seq; the boundary's §5.2 reply). While it reads the keypad fills with * (none moving under reduced motion)
   and a bubble says サーバー構成を読み込んでいます (reduced motion too). Read: 解錠 in green, the door swings, the server
   room opens — at once when it took under SR.fastMs. Not read ({ok: false}: broken JSON, the schema, a secret-shaped
   value, too big, no files…): the keypad turns red, the * go, it shakes, the bubble gives the boundary's short line
   (the file and what is wrong — never a value) and, on hover, the whole text; the room stays. Esc while it reads drops
   the press: a reply that comes later, for that seq, changes nothing.

   The server room: the whole page under one view (the 3D, a board and a log — each shown or hidden), back by its
   button or Esc. The model as the boundary gives it (groups with their parents, nodes in a group, edges between
   nodes), one environment at a time (an item with no environments is in all of them), the folded ones (fold: IAM,
   policies, alarms) out until asked for, the external ones on a strip in front of the room.
   - layout: every group a floor holding its child groups and its nodes, packed in rows (sizes bottom-up, places top-
     down), so 2,000 nodes still fit one view; a node is a cell.
   - shapes: one InstancedMesh per shape (category → shape, srShape), the colour the provider's; one InstancedMesh for
     all the floors; the cables two LineSegments (within a provider: solid; across providers: dashed magenta, higher).
   - far (a node smaller than SR.lod.far px on the page): the top groups are boxes, the cables bundled between them
     (one line per pair, its count in the board), the labels the boxes' only; near again past SR.lod.near px.
   - labels: a pool of SR.labels.max on the page, given each tenth of a second to the nearest things in view.
   - icons: where the room's settings give one (service → provider → category), its image on a plane above the node,
     read from the room by the server (SOURCE.infraIcon); otherwise the neutral shape.
   Measured for the ticket: the first draw, the frame time far and near, the memory (SR.stats). */
const SR = {
  phase: 'idle', project: null, seq: 0, t0: 0, until: 0, why: '', full: '', opener: null, model: null, view: null, log: [],
  fastMs: 300, starMs: 140, okMs: 700, failMs: 9000,
  lod: { far: 9, near: 13 }, labels: { max: 110, nodes: 80 }, stats: null,
  closed: new Set(), selected: null, selectedGroup: null, zoomStep: 1.4,
};
const srEl = $('sr'), srBubbleEl = $('sr-bubble');
function srNow() { return performance.now(); }
function srCovers() { return SR.phase === 'open'; }   // 40-scene.js: the room's 3D is not drawn under the server room
function srLog(text) {
  SR.log.unshift({ at: Date.now(), text });
  SR.log.length = Math.min(SR.log.length, 200);
  if (!$('sr-log').hidden) srRenderLog();
}

/* ---- the door's press ---- */
async function srEnter(project, opener) {
  if (!project || ['loading', 'ok', 'open'].includes(SR.phase)) return;
  const seq = ++SR.seq;
  Object.assign(SR, { phase: 'loading', project, t0: srNow(), why: '', full: '', opener: opener || null });
  srBubble('サーバー構成を読み込んでいます', 'info');
  srLog(`${(PROJECT[project] && PROJECT[project].name) || project}: 構成を読み込み始めた`);
  const got = typeof SOURCE.infraDocs === 'function' ? await SOURCE.infraDocs(project, seq)
    : { ok: false, seq, reason: 'unreadable', message: 'このページでは読めない', short: 'このページでは読めない' };
  if (seq !== SR.seq || SR.phase !== 'loading') return;   // Esc, or a newer press: this reply changes nothing
  if (!got || got.ok !== true) { srFail(got || {}); return; }
  const took = srNow() - SR.t0;
  SR.model = got; SR.phase = 'ok';
  SR.until = srNow() + (took < SR.fastMs ? 120 : SR.okMs);
  srBubble(null);
  srLog(`読み込んだ: ${got.files.length} ファイル、node ${got.nodes.length}・edge ${got.edges.length}（${got.readMs} ms）${got.problems && got.problems.length ? `、問題 ${got.problems.length} 件` : ''}`);
  setTimeout(() => { if (seq === SR.seq && SR.phase === 'ok') srShow(got); }, Math.max(0, SR.until - srNow()));
}
function srFail(got) {
  const short = String(got.short || got.message || '読めなかった');
  const lines = [String(got.message || '')];
  for (const p of (got.problems || []).slice(0, 30)) lines.push(`${p.file || ''}${p.line ? `:${p.line}` : ''} ${p.short || p.message || ''}`.trim());
  Object.assign(SR, { phase: 'failed', why: short, full: lines.filter(Boolean).join('\n'), until: srNow() + SR.failMs });
  srBubble(short, 'error', SR.full);
  srLog(`読めなかった: ${short}`);
}
function srCancel() {
  if (SR.phase !== 'loading') return false;
  SR.seq += 1; SR.phase = 'idle';
  srBubble(null);
  srLog('読み込みをやめた（Esc）');
  return true;
}
/* What the keypad shows now (40-scene.js serverDoorTick). */
function srKeypad(project, nowSec) {
  void nowSec;
  if (project !== SR.project) return { state: 'idle', stars: 0, open: 0 };
  const t = srNow();
  if (SR.phase === 'failed' && t > SR.until) { SR.phase = 'idle'; srBubble(null); }
  if (SR.phase === 'loading') return { state: 'loading', stars: reduceMotion ? 4 : 1 + (Math.floor((t - SR.t0) / SR.starMs) % 8), open: 0 };
  if (SR.phase === 'ok') return { state: 'ok', stars: 8, open: 1 };
  if (SR.phase === 'failed') return { state: 'failed', stars: 0, open: 0, shake: t - (SR.until - SR.failMs) < 500 };
  return { state: 'idle', stars: 0, open: 0 };
}
/* The bubble over the keypad: shown while it reads and when it failed (the short line; the whole text on hover). */
function srBubble(text, kind = 'info', full = '') {
  if (!text) { srBubbleEl.hidden = true; srBubbleEl.dataset.kind = ''; return; }
  setText(srBubbleEl.querySelector('.sr-short'), text);
  setText(srBubbleEl.querySelector('.sr-full'), full || '');
  srBubbleEl.dataset.kind = kind;
  srBubbleEl.hidden = false;
  srBubblePlace();
}
function srBubblePlace() {
  if (srBubbleEl.hidden) return;
  const at = typeof serverDoorScreen === 'function' ? serverDoorScreen() : null;
  if (at) {   // kept on the page: centred over the keypad, its top and sides 16 px in at least
    const w = srBubbleEl.offsetWidth, h = srBubbleEl.offsetHeight, half = w / 2 + 16;
    const x = Math.min(Math.max(at[0], half), Math.max(half, window.innerWidth - half)), y = Math.max(at[1], h + 10 + 16);
    srBubbleEl.style.left = `${Math.round(x)}px`; srBubbleEl.style.top = `${Math.round(y)}px`; srBubbleEl.classList.remove('sr-bubble-free');
  }
  else srBubbleEl.classList.add('sr-bubble-free');   // the keypad out of sight: the bubble at the top of the page
  requestAnimationFrame(srBubblePlace);
}

/* ---- the server room's view ---- */
const SR_CELL = 1.8, SR_PAD = 0.6, SR_HEAD = 1.0;
const SR_SHAPES = {
  rack: () => new THREE.BoxGeometry(0.9, 1.5, 0.7), drum: () => new THREE.CylinderGeometry(0.5, 0.5, 1.1, 12),
  bucket: () => new THREE.CylinderGeometry(0.55, 0.4, 0.9, 12), belt: () => new THREE.BoxGeometry(1.3, 0.35, 0.6),
  globe: () => new THREE.SphereGeometry(0.55, 12, 8), gate: () => new THREE.ConeGeometry(0.6, 1.0, 4),
  puck: () => new THREE.CylinderGeometry(0.55, 0.55, 0.45, 12), small: () => new THREE.BoxGeometry(0.6, 0.6, 0.6),
  kiosk: () => new THREE.OctahedronGeometry(0.55),
};
function srShape(category) {
  const c = String(category || '');
  if (c.startsWith('compute.')) return 'rack';
  if (c.startsWith('database.')) return 'drum';
  if (c.startsWith('storage.')) return 'bucket';
  if (c === 'queue' || c === 'stream') return 'belt';
  if (c.startsWith('edge.')) return 'globe';
  if (c === 'load_balancer') return 'gate';
  if (c === 'cache') return 'puck';
  if (c === 'external.saas' || c === 'client') return 'kiosk';
  return 'small';
}
const SR_PALETTE = ['#f29a38', '#4f8ef7', '#3fb26b', '#e2574c', '#a26bd6', '#26a5b8', '#d4a72c', '#7d8a99', '#e06fa8', '#5c6bc0'];
function srProviderColor(p) {
  if (!p) return '#9aa4b2';
  let h = 0;
  for (const ch of String(p)) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return SR_PALETTE[h % SR_PALETTE.length];
}
const srVisible = (x, env) => !env || !Array.isArray(x.environments) || !x.environments.length || x.environments.includes(env);
function srEnvs(model) { return (model.environments || []).map((e) => (typeof e === 'string' ? { id: e, label: e } : { id: e.id, label: e.label || e.id })); }

/* Places every group and node (sizes bottom-up, places top-down); the external nodes on a strip in front. */
function srLayout(model, env, showFold, closed = new Set()) {
  const groups = new Map();
  for (const g of model.groups || []) if (srVisible(g, env)) groups.set(g.id, { g, kids: [], nodes: [], level: 0 });
  const roots = [];
  for (const G of groups.values()) { const p = G.g.parent && groups.get(G.g.parent); (p ? p.kids : roots).push(G); }
  const loose = { g: { id: '', kind: 'logical', label: 'グループなし' }, kids: [], nodes: [], level: 0 }, ext = [];
  const nodes = (model.nodes || []).filter((n) => srVisible(n, env) && (showFold || !n.fold));
  for (const n of nodes) {
    if (n.external || n.category === 'external.saas') { ext.push(n); continue; }
    const G = n.group && groups.get(n.group);
    (G ? G.nodes : loose.nodes).push(n);
  }
  if (loose.nodes.length) roots.push(loose);
  const pack = (items) => {
    const area = items.reduce((a, it) => a + it.w * it.d, 0), wide = Math.max(SR_CELL, ...items.map((it) => it.w));
    const rowW = Math.max(wide, Math.sqrt(area) * 1.25);
    items.sort((a, b) => b.d - a.d || b.w - a.w);
    let x = 0, z = 0, rowD = 0, W = 0;
    for (const it of items) {
      if (x > 0 && x + it.w > rowW) { z += rowD + SR_PAD * 0.5; x = 0; rowD = 0; }
      it.x = x; it.z = z; x += it.w + SR_PAD * 0.5; rowD = Math.max(rowD, it.d); W = Math.max(W, x);
    }
    return [Math.max(W - SR_PAD * 0.5, SR_CELL), z + rowD];
  };
  const size = (G, level) => {
    G.level = level;
    if (G.g.id && closed.has(G.g.id)) {   // closed: one box the size of two cells, its insides not laid out
      G.closed = true; G.items = []; G.w = SR_CELL * 2 + 2 * SR_PAD; G.d = SR_CELL + SR_PAD + SR_HEAD;
      return;
    }
    const items = [...G.kids.map((k) => { size(k, level + 1); return { w: k.w, d: k.d, k }; }), ...G.nodes.map((n) => ({ w: SR_CELL, d: SR_CELL, n }))];
    const [W, D] = items.length ? pack(items) : [SR_CELL, SR_CELL * 0.5];
    G.items = items; G.w = W + 2 * SR_PAD; G.d = D + SR_PAD + SR_HEAD;
  };
  for (const G of roots) size(G, 0);
  const top = roots.map((G) => ({ w: G.w, d: G.d, k: G }));
  const [TW, TD] = top.length ? pack(top) : [0, 0];
  const pos = new Map(), floors = [], tops = [];
  const place = (G, x, z) => {
    G.x = x; G.z = z;
    floors.push(G);
    if (G.closed) {   // every node inside stands in at the box's middle: the cables end there
      const inside = (H) => { for (const n of H.nodes) pos.set(n.id, { x: x + G.w / 2, z: z + G.d / 2, y: 0.06 * (G.level + 1), n, root: null, hiddenIn: G }); H.kids.forEach(inside); };
      inside(G);
      return;
    }
    for (const it of G.items) {
      const ix = x + SR_PAD + it.x, iz = z + SR_HEAD + it.z;
      if (it.k) place(it.k, ix, iz);
      else pos.set(it.n.id, { x: ix + SR_CELL / 2, z: iz + SR_CELL / 2, y: 0.06 * (G.level + 1), n: it.n, root: null });
    }
  };
  for (const it of top) { place(it.k, it.x, it.z); tops.push(it.k); }
  const rootOf = (G) => G;   // filled below: every node's top group
  void rootOf;
  for (const R of tops) {
    const walk = (G) => { for (const n of G.nodes) { const p = pos.get(n.id); if (p) p.root = R; } for (const k of G.kids) walk(k); };
    walk(R);
  }
  ext.forEach((n, i) => pos.set(n.id, { x: i * SR_CELL * 1.3 + SR_CELL / 2, z: TD + 5, y: 0, n, root: null, external: true }));
  const width = Math.max(TW, ext.length * SR_CELL * 1.3), depth = TD + (ext.length ? 7 : 0);
  // an edge in this environment as the merge gave it (e.environments; none: all), both its ends laid out
  const edges = (model.edges || []).filter((e) => srVisible(e, env) && pos.has(e.from) && pos.has(e.to)
    && !(pos.get(e.from).hiddenIn && pos.get(e.from).hiddenIn === pos.get(e.to).hiddenIn));   // within one closed group: not drawn
  const shown = [...pos.values()].filter((p) => !p.hiddenIn);
  return { floors, tops, pos, ext, edges, nodes: shown.map((p) => p.n), hidden: pos.size - shown.length, closed: floors.filter((G) => G.closed), width, depth };
}

function srShow(model) {
  SR.phase = 'open';
  SR.model = model;
  showOverlay(srEl);
  setText($('sr-room'), (PROJECT[SR.project] && PROJECT[SR.project].name) || '');
  const envs = srEnvs(model);
  $('sr-env').innerHTML = envs.length ? envs.map((e) => `<option value="${esc(e.id)}">${esc(e.label)}</option>`).join('') : '<option value="">（環境の指定なし）</option>';
  $('sr-env').disabled = envs.length < 2;
  $('sr-fold').checked = false;
  SR.closed = new Set(); SR.selected = null; SR.selectedGroup = null;
  srBuild();
  $('sr-back').focus({ preventScroll: true });
}
function srClose() {
  if (SR.phase !== 'open') return;
  SR.phase = 'idle';
  srDispose();
  hideOverlay(srEl);
  SR.seq += 1;
  srLog('部屋に戻った');
  if (SR.opener && SR.opener.focus) SR.opener.focus({ preventScroll: true });
}
function srDispose() {
  const V = SR.view;
  if (!V) return;
  cancelAnimationFrame(V.raf);
  V.ro.disconnect();
  V.controls.dispose();
  V.scene.traverse((o) => { if (o.geometry) o.geometry.dispose(); if (o.material) { for (const m of [].concat(o.material)) { if (m.map) m.map.dispose(); m.dispose(); } } });
  V.renderer.dispose();
  for (const url of V.iconUrls) URL.revokeObjectURL(url);
  $('sr-labels').innerHTML = '';
  SR.view = null;
}
function srBuild() {
  const t0 = srNow();
  srDispose();
  const model = SR.model, env = $('sr-env').value || '', fold = $('sr-fold').checked;
  const L = srLayout(model, env, fold, SR.closed);
  const cv = $('sr-canvas'), box = cv.parentElement;
  const renderer = new THREE.WebGLRenderer({ canvas: cv, antialias: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(isDark() ? '#141a22' : '#eef2f7');
  scene.add(new THREE.HemisphereLight(0xffffff, 0x445566, 1.6));
  const sun = new THREE.DirectionalLight(0xffffff, 1.2); sun.position.set(30, 60, 40); scene.add(sun);
  const camera = new THREE.PerspectiveCamera(45, 1, 0.1, 5000);
  const controls = new OrbitControls(camera, cv);
  Object.assign(controls, { enableDamping: !reduceMotion, dampingFactor: 0.12, screenSpacePanning: true, minDistance: 3, maxDistance: 4000, maxPolarAngle: Math.PI * 0.48 });
  const V = { renderer, scene, camera, controls, L, near: new THREE.Group(), far: new THREE.Group(), lod: 'near', pick: [], iconUrls: [], raf: 0,
    frames: [], labelAt: 0, labels: [], ro: null, env, fold };
  V.far.visible = false;   // srLod only switches on a change: a view that opens near never showed the far boxes' level
  scene.add(V.near, V.far);
  // floors: one instanced box for all of them
  const floorMesh = new THREE.InstancedMesh(new THREE.BoxGeometry(1, 1, 1), new THREE.MeshLambertMaterial({ color: 0xffffff }), Math.max(1, L.floors.length));
  const m4 = new THREE.Matrix4(), col = new THREE.Color(), q = new THREE.Quaternion(), sc = new THREE.Vector3(), at = new THREE.Vector3();
  L.floors.forEach((G, i) => {
    const h = 0.05, y = 0.06 * G.level + h / 2;
    m4.compose(at.set(G.x + G.w / 2, y, G.z + G.d / 2), q, sc.set(G.w, h, G.d));
    floorMesh.setMatrixAt(i, m4);
    const g = G.g, base = g.kind === 'logical' ? '#c9b8e8' : g.visibility === 'public' ? '#dfe7f2' : g.visibility === 'private' ? '#9fb0c4' : g.provider ? srProviderColor(g.provider) : '#cfd6df';
    col.set(base); if (g.provider && g.kind !== 'logical') col.lerp(new THREE.Color(isDark() ? '#1d2430' : '#ffffff'), 0.55 - Math.min(G.level, 4) * 0.08);
    floorMesh.setColorAt(i, col);
  });
  floorMesh.count = L.floors.length;
  floorMesh.userData.groups = L.floors.map((G) => G.g.id);
  V.near.add(floorMesh); V.pick.push(floorMesh);
  if (L.closed.length) {   // the closed groups: a box each, as tall as what it holds
    const cm = new THREE.InstancedMesh(new THREE.BoxGeometry(1, 1, 1), new THREE.MeshLambertMaterial({ color: 0xffffff }), L.closed.length);
    L.closed.forEach((G, i) => {
      const h = 0.6 + Math.log2(1 + srCountNodes(G)) * 0.35;
      m4.compose(at.set(G.x + G.w / 2, 0.06 * G.level + h / 2, G.z + SR_HEAD + (G.d - SR_HEAD) / 2), q, sc.set(G.w - SR_PAD, h, G.d - SR_HEAD - SR_PAD * 0.5));
      cm.setMatrixAt(i, m4);
      cm.setColorAt(i, col.set(G.g.kind === 'logical' ? '#b49be0' : srProviderColor(G.g.providerResolved || G.g.provider)));
    });
    cm.userData.groups = L.closed.map((G) => G.g.id);
    V.near.add(cm); V.pick.push(cm);
  }
  // nodes: one instanced mesh per shape
  const byShape = {};
  for (const p of L.pos.values()) if (!p.hiddenIn) (byShape[srShape(p.n.category)] = byShape[srShape(p.n.category)] || []).push(p);
  for (const [shape, list] of Object.entries(byShape)) {
    const mesh = new THREE.InstancedMesh(SR_SHAPES[shape](), new THREE.MeshLambertMaterial({ color: 0xffffff }), list.length);
    list.forEach((p, i) => {
      const s = p.n.count > 1 ? 1 + Math.min(Math.log2(p.n.count), 4) * 0.12 : 1;
      m4.compose(at.set(p.x, p.y + 0.75, p.z), q, sc.set(s, s, s));
      mesh.setMatrixAt(i, m4);
      mesh.setColorAt(i, col.set(srProviderColor(p.n.providerResolved || p.n.provider)));
    });
    mesh.userData.nodes = list.map((p) => p.n.id);
    V.near.add(mesh); V.pick.push(mesh);
  }
  // cables: within a provider solid, across providers dashed magenta and higher (requester: 跨いでいることが見て分かる)
  const plain = [], cross = [];
  for (const e of L.edges) {
    const a = L.pos.get(e.from), b = L.pos.get(e.to), crossing = !!e.crossProvider, y = crossing ? 2.6 : 1.7;
    (crossing ? cross : plain).push(a.x, y, a.z, b.x, y, b.z);
  }
  const lines = (arr, mat) => { const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.Float32BufferAttribute(arr, 3)); const l = new THREE.LineSegments(g, mat); if (mat.isLineDashedMaterial) l.computeLineDistances(); return l; };
  V.plainLines = lines(plain, new THREE.LineBasicMaterial({ color: isDark() ? 0x7f8ea3 : 0x5c6b7f, transparent: true, opacity: 0.7 }));
  V.crossLines = lines(cross, new THREE.LineDashedMaterial({ color: 0xd63fb0, dashSize: 0.5, gapSize: 0.3 }));
  V.near.add(V.plainLines, V.crossLines);
  // far: the top groups as boxes, the cables bundled between them
  const tops = L.tops, topIndex = new Map(tops.map((G, i) => [G, i]));
  const boxMesh = new THREE.InstancedMesh(new THREE.BoxGeometry(1, 1, 1), new THREE.MeshLambertMaterial({ color: 0xffffff }), Math.max(1, tops.length));
  tops.forEach((G, i) => {
    const n = srCountNodes(G), h = 0.8 + Math.log2(1 + n) * 0.6;
    G.boxH = h; G.nodeCount = n;
    m4.compose(at.set(G.x + G.w / 2, h / 2, G.z + G.d / 2), q, sc.set(G.w * 0.92, h, G.d * 0.92));
    boxMesh.setMatrixAt(i, m4);
    boxMesh.setColorAt(i, col.set(G.g.kind === 'logical' ? '#b49be0' : srProviderColor(G.g.provider)));
  });
  boxMesh.count = tops.length;
  V.far.add(boxMesh);
  const bundles = new Map();
  for (const e of L.edges) {
    const ra = L.pos.get(e.from).root, rb = L.pos.get(e.to).root;
    if (!ra || !rb || ra === rb) continue;
    const ia = topIndex.get(ra), ib = topIndex.get(rb), key = ia < ib ? `${ia}:${ib}` : `${ib}:${ia}`;
    const B = bundles.get(key) || { a: ra, b: rb, n: 0, cross: 0 };
    B.n += 1; if (e.crossProvider) B.cross += 1;
    bundles.set(key, B);
  }
  const bp = [], bc = [];
  for (const B of bundles.values()) {
    const ya = B.a.boxH + 0.3, yb = B.b.boxH + 0.3;
    (B.cross ? bc : bp).push(B.a.x + B.a.w / 2, ya, B.a.z + B.a.d / 2, B.b.x + B.b.w / 2, yb, B.b.z + B.b.d / 2);
  }
  V.bundles = [...bundles.values()];
  V.far.add(lines(bp, new THREE.LineBasicMaterial({ color: 0x5c6b7f })), lines(bc, new THREE.LineDashedMaterial({ color: 0xd63fb0, dashSize: 1.2, gapSize: 0.7 })));
  // the external strip's sign
  if (L.ext.length) {
    const strip = new THREE.Mesh(new THREE.BoxGeometry(L.ext.length * SR_CELL * 1.3, 0.04, SR_CELL * 1.6), new THREE.MeshLambertMaterial({ color: isDark() ? 0x3a3248 : 0xe9e2f5 }));
    strip.position.set(L.ext.length * SR_CELL * 1.3 / 2, 0.02, L.pos.get(L.ext[0].id).z);
    V.near.add(strip);
  }
  srIcons(V);
  // the labels: a fixed pool, given out each tenth of a second
  const holder = $('sr-labels');
  holder.innerHTML = '';
  for (let i = 0; i < SR.labels.max; i++) { const s = document.createElement('span'); s.className = 'sr-label'; s.hidden = true; holder.append(s); V.labels.push(s); }
  V.ro = new ResizeObserver(() => srResize(V)); V.ro.observe(box);
  srResize(V);
  SR.view = V;
  srFit(true);
  srCounts(L);
  cv.onpointerdown = (e) => { V.downAt = [e.clientX, e.clientY]; };
  cv.onpointerup = (e) => { if (V.downAt && Math.hypot(e.clientX - V.downAt[0], e.clientY - V.downAt[1]) < 5) srPick(e); V.downAt = null; };
  const loop = () => {
    V.raf = requestAnimationFrame(loop);
    const t = srNow();
    if (V.last) { V.frames.push(t - V.last); if (V.frames.length > 240) V.frames.shift(); }
    V.last = t;
    controls.update();
    srLod(V);
    if (t - V.labelAt > 100) { V.labelAt = t; srPlaceLabels(V); }
    renderer.render(scene, camera);
  };
  loop();
  SR.stats = { firstMs: Math.round(srNow() - t0), nodes: L.nodes.length, edges: L.edges.length, floors: L.floors.length };
  srLog(`描いた: node ${L.nodes.length}・edge ${L.edges.length}・床 ${L.floors.length}（${SR.stats.firstMs} ms）${env ? `、環境 ${env}` : ''}`);
}
function srCountNodes(G) { return G.nodes.length + G.kids.reduce((a, k) => a + srCountNodes(k), 0); }
function srResize(V) {
  const box = $('sr-canvas').parentElement, w = Math.max(1, box.clientWidth), h = Math.max(1, box.clientHeight);
  V.renderer.setSize(w, h, false); V.camera.aspect = w / h; V.camera.updateProjectionMatrix();
}
function srFit(instant) {
  const V = SR.view;
  if (!V) return;
  const L = V.L, cx = L.width / 2, cz = L.depth / 2, r = Math.max(6, Math.hypot(L.width, L.depth) / 2);
  const dist = r / Math.sin((V.camera.fov * Math.PI / 180) / 2) * 0.95;
  V.controls.target.set(cx, 0, cz);
  V.camera.position.set(cx, dist * 0.78, cz + dist * 0.62);
  V.camera.near = Math.max(0.1, dist / 500); V.camera.far = dist * 6; V.camera.updateProjectionMatrix();
  V.controls.update();
  void instant;
}
/* How big a node cell is on the page now (px): far below SR.lod.far, near again above SR.lod.near. */
function srCellPx(V) {
  const dist = V.camera.position.distanceTo(V.controls.target), h = V.renderer.domElement.clientHeight || 1;
  return SR_CELL / (2 * dist * Math.tan((V.camera.fov * Math.PI / 180) / 2)) * h;
}
function srLod(V) {
  const px = srCellPx(V);
  const want = V.lod === 'near' ? (px < SR.lod.far ? 'far' : 'near') : (px > SR.lod.near ? 'near' : 'far');
  if (want === V.lod) return;
  V.lod = want; V.near.visible = want === 'near'; V.far.visible = want === 'far';
  V.labelAt = 0;
}
function srPlaceLabels(V) {
  const cam = V.camera, w = V.renderer.domElement.clientWidth, h = V.renderer.domElement.clientHeight, v = new THREE.Vector3(), out = [];
  const consider = (x, y, z, text, kind, weight) => {
    v.set(x, y, z).project(cam);
    if (v.z < -1 || v.z > 1 || v.x < -1.05 || v.x > 1.05 || v.y < -1.05 || v.y > 1.05) return;
    out.push({ sx: (v.x + 1) / 2 * w, sy: (1 - v.y) / 2 * h, text, kind, d: cam.position.distanceToSquared(new THREE.Vector3(x, y, z)) * weight });
  };
  if (V.lod === 'far') {
    for (const G of V.L.tops) consider(G.x + G.w / 2, G.boxH + 0.8, G.z + G.d / 2, `${G.g.label || G.g.id} · ${G.nodeCount}`, 'group', 1);
  } else {
    for (const G of V.L.floors) if (G.g.id) consider(G.x + 0.6, 0.2 + G.level * 0.06, G.z + 0.5, G.g.label || G.g.id, 'group', 0.6);
    for (const p of V.L.pos.values()) if (!p.hiddenIn) consider(p.x, p.y + 1.9, p.z, `${p.n.label || p.n.id}${p.n.count > 1 ? ` ×${p.n.count}` : ''}`, p.external ? 'external' : 'node', 1);
  }
  out.sort((a, b) => a.d - b.d);
  const groups = out.filter((o) => o.kind === 'group').slice(0, SR.labels.max - SR.labels.nodes);
  const rest = out.filter((o) => o.kind !== 'group').slice(0, SR.labels.nodes);
  const placed = [], clear = (o) => {   // a label that would cover one already given out is left out (its width from its text)
    const wd = 12 + [...o.text].reduce((a, ch) => a + (ch.charCodeAt(0) > 0x2e7f ? 12 : 7), 0), b = [o.sx - wd / 2, o.sy - 20, o.sx + wd / 2, o.sy];
    if (placed.some((q) => b[0] < q[2] && b[2] > q[0] && b[1] < q[3] && b[3] > q[1])) return false;
    placed.push(b); return true;
  };
  const shown = [...groups, ...rest].filter(clear).slice(0, SR.labels.max);
  V.labels.forEach((s, i) => {
    const o = shown[i];
    if (!o) { s.hidden = true; return; }
    s.hidden = false; s.dataset.kind = o.kind;
    if (s.textContent !== o.text) s.textContent = o.text;
    s.style.transform = `translate(${Math.round(o.sx)}px, ${Math.round(o.sy)}px) translate(-50%, -100%)`;
  });
  V.shownLabels = shown.length;
}
/* The room's icons: per node the strongest key the settings give (service → provider → category), an image plane above it. */
async function srIcons(V) {
  const icons = new Set(SR.model.icons ? Object.keys(SR.model.icons) : []);
  if (!icons.size || typeof SOURCE.infraIcon !== 'function') return;
  const byKey = {};
  for (const p of V.L.pos.values()) {
    if (p.hiddenIn) continue;
    const n = p.n, prov = n.providerResolved || n.provider;
    const key = [n.service && prov ? `service:${prov}/${n.service}` : null, prov ? `provider:${prov}` : null, `category:${n.category}`].find((k) => k && icons.has(k));
    if (key) (byKey[key] = byKey[key] || []).push(p);
  }
  for (const [key, list] of Object.entries(byKey)) {
    const blob = await SOURCE.infraIcon(SR.project, key);
    if (!blob || SR.view !== V) continue;
    const url = URL.createObjectURL(blob);
    V.iconUrls.push(url);
    const tex = await new THREE.TextureLoader().loadAsync(url).catch(() => null);
    if (!tex || SR.view !== V) continue;
    const mesh = new THREE.InstancedMesh(new THREE.PlaneGeometry(0.9, 0.9), new THREE.MeshBasicMaterial({ map: tex, transparent: true, toneMapped: false }), list.length);
    const m4 = new THREE.Matrix4(), q = new THREE.Quaternion().setFromEuler(new THREE.Euler(-0.5, 0, 0));
    list.forEach((p, i) => { m4.compose(new THREE.Vector3(p.x, p.y + 2.1, p.z), q, new THREE.Vector3(1, 1, 1)); mesh.setMatrixAt(i, m4); });
    mesh.userData.icon = key;
    V.near.add(mesh);
    V.iconCount = (V.iconCount || 0) + list.length;
  }
}
function srPick(e) {
  const V = SR.view;
  if (!V || V.lod !== 'near') return;
  const r = V.renderer.domElement.getBoundingClientRect(), ray = new THREE.Raycaster();
  ray.setFromCamera(new THREE.Vector2(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1), V.camera);
  const hit = ray.intersectObjects(V.pick, false)[0];
  const ud = hit && hit.instanceId !== undefined ? hit.object.userData : {};
  SR.selected = ud.nodes ? ud.nodes[hit.instanceId] : null;
  SR.selectedGroup = ud.groups ? ud.groups[hit.instanceId] || null : null;
  srRenderBoard();
}
/* Moves in on a node or a group (its floor's middle, near enough to see what it holds). */
function srFocus(x, z, r) {
  const V = SR.view;
  if (!V) return;
  const dir = V.camera.position.clone().sub(V.controls.target).normalize(), dist = Math.max(6, r * 2.2);
  V.controls.target.set(x, 0, z);
  V.camera.position.copy(V.controls.target).addScaledVector(dir, dist);
  V.controls.update();
}
function srFocusSelected() {
  const V = SR.view;
  if (!V) return;
  const p = SR.selected && V.L.pos.get(SR.selected), G = SR.selectedGroup && V.L.floors.find((F) => F.g.id === SR.selectedGroup);
  if (p) srFocus(p.x, p.z, SR_CELL * 2);
  else if (G) srFocus(G.x + G.w / 2, G.z + G.d / 2, Math.hypot(G.w, G.d) / 2);
}
function srToggleGroup(id) {
  if (!id || !SR.view) return;
  const open = SR.closed.has(id);
  if (open) SR.closed.delete(id); else SR.closed.add(id);
  const G = SR.view.L.floors.find((F) => F.g.id === id);
  srLog(`${(G && (G.g.label || G.g.id)) || id} を${open ? '開いた' : '閉じた'}`);
  srBuild();
}
function srZoomBy(factor) {
  const V = SR.view;
  if (!V) return;
  const d = V.camera.position.clone().sub(V.controls.target).multiplyScalar(factor);
  if (d.length() < V.controls.minDistance || d.length() > V.controls.maxDistance) return;
  V.camera.position.copy(V.controls.target).add(d);
  V.controls.update();
}

/* ---- the board and the log ---- */
function srCounts(L) {
  SR.shown = { nodes: L.nodes.length, edges: L.edges.length, cross: L.edges.filter((e) => e.crossProvider).length, groups: L.floors.length,
    folded: (SR.model.nodes || []).filter((n) => n.fold).length, external: L.ext.length, closed: L.closed.length, inClosed: L.hidden };
  srRenderBoard();
}
function srRenderBoard() {
  const M = SR.model, S = SR.shown || {};
  if (!M) return;
  const provs = [...new Set((M.nodes || []).map((n) => n.providerResolved || n.provider).filter(Boolean))];
  const sel = SR.selected ? (M.nodes || []).find((n) => n.id === SR.selected) : null;
  const grp = !sel && SR.selectedGroup ? (M.groups || []).find((g) => g.id === SR.selectedGroup) : null;
  const inGroup = grp && SR.view ? SR.view.L.floors.find((F) => F.g.id === grp.id) : null;
  const edgesOf = sel ? (M.edges || []).filter((e) => e.from === sel.id || e.to === sel.id).slice(0, 20) : [];
  const probs = (M.problems || []).slice(0, 50);
  setHTML($('sr-board'), `<h3>構成</h3>
<p class="sr-meta">${esc(M.dir || '')} · ${esc(String((M.files || []).length))} ファイル</p>
<dl class="sr-counts"><dt>node</dt><dd data-sr-count="nodes">${esc(String(S.nodes ?? 0))}</dd><dt>edge</dt><dd data-sr-count="edges">${esc(String(S.edges ?? 0))}</dd><dt>provider を跨ぐ edge</dt><dd data-sr-count="cross">${esc(String(S.cross ?? 0))}</dd><dt>畳んだもの</dt><dd>${esc(String(S.folded ?? 0))}${$('sr-fold').checked ? '（出している）' : ''}</dd><dt>外部</dt><dd>${esc(String(S.external ?? 0))}</dd></dl>
<h3>凡例</h3><ul class="sr-legend">${provs.map((p) => `<li><span class="sr-chip" style="background:${esc(srProviderColor(p))}"></span>${esc(p)}</li>`).join('')}
<li><span class="sr-line"></span>同じ provider の中のつながり</li><li><span class="sr-line sr-line-cross"></span>provider を跨ぐつながり（破線・マゼンタ）</li></ul>
${sel ? `<h3>選んだもの</h3><dl class="sr-sel"><dt>id</dt><dd>${esc(sel.id)}</dd><dt>名前</dt><dd>${esc(sel.label || '')}</dd><dt>種類</dt><dd>${esc(sel.category)}</dd><dt>provider</dt><dd>${esc(sel.providerResolved || sel.provider || '')}${sel.service ? ` · ${esc(sel.service)}` : ''}</dd>${sel.count > 1 ? `<dt>台数</dt><dd>${esc(String(sel.count))}</dd>` : ''}</dl>
<p class="sr-acts"><button type="button" class="wb-btn" data-sr-act="focus">これに寄る</button></p>
<ul class="sr-edges">${edgesOf.map((e) => `<li>${esc(e.from)} → ${esc(e.to)}${e.protocol ? ` <small>${esc(e.protocol)}</small>` : ''}${e.crossProvider ? ' <b>跨ぐ</b>' : ''}</li>`).join('')}</ul>`
    : grp ? `<h3>選んだ group</h3><dl class="sr-sel"><dt>id</dt><dd>${esc(grp.id)}</dd><dt>名前</dt><dd>${esc(grp.label || '')}</dd><dt>種類</dt><dd>${esc(grp.kind || '')}</dd><dt>provider</dt><dd>${esc(grp.providerResolved || grp.provider || '')}</dd><dt>中の node</dt><dd>${esc(String(inGroup ? srCountNodes(inGroup) : 0))}</dd></dl>
<p class="sr-acts"><button type="button" class="wb-btn" data-sr-act="focus">これに寄る</button> <button type="button" class="wb-btn" data-sr-act="toggle" data-sr-group="${esc(grp.id)}">${SR.closed.has(grp.id) ? '開く' : '閉じる（箱 1 つに）'}</button></p>`
    : '<p class="sr-hint">形や床を押すと、ここに詳しく出ます（床なら、その group を閉じる・開く）</p>'}
${probs.length ? `<h3>問題 ${probs.length} 件</h3><ul class="sr-problems">${probs.map((p) => `<li title="${esc(p.message || '')}">${esc(p.short || p.message || '')}</li>`).join('')}</ul>` : ''}`);
}
function srRenderLog() {
  setHTML($('sr-log'), `<ol>${SR.log.map((l) => `<li><time>${esc(new Date(l.at).toTimeString().slice(0, 8))}</time> ${esc(l.text)}</li>`).join('')}</ol>`);
}
$('sr-back').addEventListener('click', srClose);
$('sr-fit').addEventListener('click', () => srFit(false));
$('sr-zin').addEventListener('click', () => srZoomBy(1 / SR.zoomStep));
$('sr-zout').addEventListener('click', () => srZoomBy(SR.zoomStep));
$('sr-board').addEventListener('click', (e) => {
  const b = e.target.closest('[data-sr-act]');
  if (!b) return;
  if (b.dataset.srAct === 'focus') srFocusSelected();
  else if (b.dataset.srAct === 'toggle') srToggleGroup(b.dataset.srGroup);
});
$('sr-env').addEventListener('change', () => { srLog(`環境を ${$('sr-env').value || '（なし）'} にした`); srBuild(); });
$('sr-fold').addEventListener('change', () => { srLog($('sr-fold').checked ? '細かいものを出した' : '細かいものを畳んだ'); srBuild(); });
for (const [btn, el] of [['sr-board-btn', 'sr-board'], ['sr-log-btn', 'sr-log']]) {
  $(btn).addEventListener('click', () => {
    const show = $(el).hidden;
    $(el).hidden = !show; $(btn).setAttribute('aria-pressed', String(show));
    if (el === 'sr-log' && show) srRenderLog();
    if (SR.view) srResize(SR.view);
  });
}
document.addEventListener('keydown', (e) => {
  if (e.key !== 'Escape') return;
  if (SR.phase === 'loading') { e.preventDefault(); e.stopPropagation(); srCancel(); return; }
  if (SR.phase === 'open') { e.preventDefault(); e.stopPropagation(); srClose(); }
}, true);
