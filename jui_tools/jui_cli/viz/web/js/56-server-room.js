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
     all the floors; the cables two sets of strips (within a provider: solid; across providers: dashed magenta, a little
     higher), from one node's side to the other's, low, rising only over what stands between (srCablePathOf), each at least SR_CABLE px
     wide on the page however far the camera is (srCables).
   - far (a node smaller than SR.lod.far px on the page): the top groups are boxes, the cables bundled between them
     (one line per pair, its count in the board), the labels the boxes' only; near again past SR.lod.near px.
   - labels: a pool of SR.labels.max on the page, given each tenth of a second to the nearest things in view.
   - icons: where the room's settings give one (service → provider → category), its image on a plane above the node,
     read from the room by the server (SOURCE.infraIcon); otherwise the neutral shape.
   - up close (ticket 2026-10-20-jui-viz-server-room-lines-dark-filter-spec §5, requester: 「ある程度拡大して表示されてる
     ノードが少なくなった時はどれが何のインスタンスかわかる程度に違いが欲しい」): near, with SR.detail.enter nodes or fewer
     in view, a second set of shapes by service (a function a slim pillar, a container a crate, a key-value store a
     tapered drum, a notification a pyramid...: srDetailShape) and tags of name · service · its main spec; back to
     the simple ones past SR.detail.leave (between the two it stays as it was). There, each node in view stands as a model of what
     it does (56-sr-models.js); the shapes by service under it still take the press.
   - migration plans (ticket 2026-10-22-viz-infra-migration-plan): the board lists them; 移管 plays one (59-sr-migration.js).
   - a node's spec (§4): the board's 選んだもの lists it, the keys the IaC tables know with a name in words.
   - つながっている物を全部見せる (ticket 2026-10-22-viz-sr-cables-too-thin-and-no-show-neighbours): beside これに寄る; the
     chosen node and every node an edge joins it to (in and out; one step, or every step on) drawn as they are, the rest
     faint, their cables strong, the camera moved until all of them are in view; pressed again or Esc, as it was (srReach).
   Measured for the ticket: the first draw, the frame time far and near, the memory (SR.stats). */
const SR = {
  phase: 'idle', project: null, seq: 0, t0: 0, until: 0, why: '', full: '', opener: null, model: null, view: null, log: [],
  fastMs: 300, starMs: 140, okMs: 700, failMs: 9000,
  lod: { far: 9, near: 13 },
  // 2D pulled back (the requester 10-23, 「引きでは跨ぐ線だけ」): below `hide` px a cell, the cables within one provider are
  // hidden and only the crossing ones drawn; above `show` all again (a gap between, so it never flickers)
  flatPlain: { hide: 18, show: 22 }, labels: { max: 110, nodes: 80 }, stats: null, detail: { enter: 30, leave: 40 },
  closed: new Set(), selected: null, selectedGroup: null, boardSel: null, zoomStep: 1.4,
  // fewer lines (2.3.9, requester 10-20: 「線減らす工夫欲しいね」): all cables faint, the pressed and the pointed node's
  // drawn strong on a layer of their own; a switch for all (faint) / crossing ones only / the chosen node's only
  lines: 'all', hover: null, plainOpacity: 0.18, crossOpacity: 0.55,
  only: new Set(),   // the clouds chosen on the board's legend (2.3.9, item 3; empty: all)
  // a box drawn to move in on (2.3.11 item 6): Option + drag, or 範囲で寄る then one drag; fit is how much of the page it fills
  box: { armed: false, drag: null }, boxFit: 0.92,
  // つながっている物を全部見せる: {id, hops, ids, edges, cam} while shown; how many steps it follows (1, or 'all'); how faint the rest
  reach: null, reachHops: 1, reachFade: 0.82, reachLineOpacity: 0.05, reachFit: 0.7,   // reachFit: what it holds fills this much of the page, its tags inside
  // 2D (requester 10-23: 「3D見にくいので2Dモードも実装してほしい / 機能は3Dと一緒」): the same room from straight above, an
  // orthographic camera and flat shapes; flat is the room open now's, remembered per project (srViewPref)
  flat: false,
};
/* The 2D camera's frame: half its height in world units at zoom 1 (srResize gives it the page's aspect), and how high it
   sits (well above anything drawn, so the cables' near plane never cuts them). */
const SR_FLAT = { half: 50, height: 400, fov: 45 };
/* 2D or 3D, per project: {project: '2d' | '3d'} in the page's own storage. */
function srViewPref(project) {
  try { const all = JSON.parse(readPref('srView', '{}')) || {}; return (all[project] || all['*']) === '2d'; } catch (err) { return false; }   // '*': every project not chosen yet (the e2e's 2D runs)
}
function srViewPrefSet(project, flat) {
  let all = {};
  try { all = JSON.parse(readPref('srView', '{}')) || {}; } catch (err) { all = {}; }
  all[project] = flat ? '2d' : '3d';
  writePref('srView', JSON.stringify(all));
}
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
  clearTimeout(SR.failTimer);
  Object.assign(SR, { phase: 'loading', project, t0: srNow(), why: '', full: '', opener: opener || null });
  srBubble(tl('sr.loading'), 'info');
  srLog(tl('sr.log.loading', { room: (PROJECT[project] && PROJECT[project].name) || project }));
  const got = typeof SOURCE.infraDocs === 'function' ? await SOURCE.infraDocs(project, seq)
    : { ok: false, seq, reason: 'unreadable', message: tl('sr.unreadable'), short: tl('sr.unreadable') };
  if (seq !== SR.seq || SR.phase !== 'loading') return;   // Esc, or a newer press: this reply changes nothing
  if (!got || got.ok !== true) { srFail(got || {}); return; }
  const took = srNow() - SR.t0;
  SR.model = got; SR.phase = 'ok';
  SR.until = srNow() + (took < SR.fastMs ? 120 : SR.okMs);
  SR.took = Math.round(took); SR.waitMs = Math.round(SR.until - srNow());   // read under SR.fastMs: a flash, not the whole 解錠
  srBubble(null);
  srLog(tl('sr.log.read', { files: got.files.length, nodes: got.nodes.length, edges: got.edges.length, ms: got.readMs })
    + (got.problems && got.problems.length ? tl('sr.log.read.problems', { n: got.problems.length }) : ''));
  setTimeout(() => { if (seq === SR.seq && SR.phase === 'ok') srShow(got); }, Math.max(0, SR.until - srNow()));
}
function srFail(got) {
  const short = String(got.short || got.message || tl('sr.failed'));
  const lines = [String(got.message || '')];
  for (const p of (got.problems || []).slice(0, 30)) lines.push(`${p.file || ''}${p.line ? `:${p.line}` : ''} ${p.short || p.message || ''}`.trim());
  Object.assign(SR, { phase: 'failed', why: short, full: lines.filter(Boolean).join('\n'), until: srNow() + SR.failMs });
  srBubble(short, 'error', SR.full);
  // gone after SR.failMs by its own timer, wherever the view is (the independent verification D1, 10-20: it was cleared from the
  // keypad's tick, which runs only for the door in sight, and stayed on the floor view after a failure)
  clearTimeout(SR.failTimer);
  const seq = SR.seq;
  SR.failTimer = setTimeout(() => { if (SR.phase === 'failed' && SR.seq === seq) srIdle(); }, SR.failMs);
  srLog(tl('sr.log.failed', { why: short }));
}
function srIdle() {
  clearTimeout(SR.failTimer);
  SR.phase = 'idle';
  srBubble(null);
}
function srCancel() {
  if (SR.phase !== 'loading') return false;
  SR.seq += 1; SR.phase = 'idle';
  srBubble(null);
  srLog(tl('sr.log.cancel'));
  return true;
}
/* What the keypad shows now (40-scene.js serverDoorTick, and the e2e hook): it only reads, it changes nothing. */
function srKeypad(project, nowSec) {
  void nowSec;
  if (project !== SR.project) return { state: 'idle', stars: 0, open: 0 };
  const t = srNow();
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
  // a failure is about one room's door: away from that room (the floor, another room) it goes at once (D1)
  const near = typeof srDoorNow === 'function' ? srDoorNow() : null;
  if (SR.phase === 'failed' && (!near || near.room !== SR.project)) { srIdle(); return; }
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
  // up close only (srDetailShape)
  pillar: () => new THREE.CylinderGeometry(0.3, 0.3, 1.5, 6), crate: () => new THREE.BoxGeometry(1.3, 0.8, 0.8),
  ring: () => new THREE.TorusGeometry(0.42, 0.16, 8, 20), taper: () => new THREE.CylinderGeometry(0.35, 0.6, 1.1, 8),
  pyramid: () => new THREE.TetrahedronGeometry(0.65), longBelt: () => new THREE.BoxGeometry(1.7, 0.22, 0.45),
  shield: () => new THREE.DodecahedronGeometry(0.5), key: () => new THREE.IcosahedronGeometry(0.5),
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
/* Up close: a shape by what the node is, so two of one category tell apart (an EC2 and a Lambda, an SQS and an SNS). */
function srDetailShape(n) {
  const c = String(n.category || ''), s = String(n.service || '');
  if (c === 'compute.function') return 'pillar';
  if (c === 'compute.container') return 'crate';
  if (c === 'compute.k8s') return 'ring';
  if (c === 'database.kv' || c === 'database.document') return 'taper';
  if (c === 'queue' && /^(sns|eventgrid|notification)/.test(s)) return 'pyramid';
  if (c === 'stream') return 'longBelt';
  if (c === 'edge.waf') return 'shield';
  if (c === 'auth' || c === 'secrets') return 'key';
  return srShape(c);
}
const srShapeIn = (set, n) => (SR.flat ? `flat:${srModelKind(n)}` : set === 'detail' ? srDetailShape(n) : srShape(n.category));
/* 2D's shapes (the 3D models' kinds, 56-sr-models.js srModelKind; the orchestrator 10-23: each kind told apart, the
   requester's 「どんな機能のノードかわかりやすいように」): a flat tile each — an outline of its own and its short name on it,
   drawn once on a canvas, white where the cloud's colour shows and dark for the name. [outline, name, half width, half
   depth, round]. */
const SR_FLAT_KIND = {
  db: ['circle', 'DB', 0.62, 0.62, true], cache: ['circle', 'MEM', 0.55, 0.55, true], bucket: ['bucket', 'OBJ', 0.6, 0.6, false],
  drive: ['square', 'DISK', 0.6, 0.6, false], broadcast: ['triangle', 'PUB', 0.66, 0.6, false], queue: ['pill', 'QUEUE', 0.8, 0.42, false],
  stream: ['pill', 'STREAM', 0.8, 0.42, false], splitter: ['diamond', 'LB', 0.66, 0.66, false], globe: ['ring', 'CDN', 0.66, 0.66, true],
  signpost: ['sign', 'DNS', 0.7, 0.5, false], shield: ['shield', 'WAF', 0.6, 0.66, false], arch: ['arch', 'API', 0.66, 0.6, false],
  bolt: ['square', 'λ', 0.58, 0.58, false], server: ['square', 'VM', 0.62, 0.62, false], container: ['hex', 'CTR', 0.66, 0.6, false],
  wheel: ['oct', 'K8s', 0.64, 0.64, true], browser: ['window', 'UI', 0.7, 0.55, false], padlock: ['lock', 'AUTH', 0.58, 0.64, false],
  key: ['round', 'KEY', 0.58, 0.58, false], clock: ['clock', 'CRON', 0.6, 0.6, true], envelope: ['envelope', 'MAIL', 0.7, 0.5, false],
  gauge: ['gauge', 'MON', 0.64, 0.56, false], cloud: ['cloud', 'SaaS', 0.74, 0.54, false], plinth: ['round', '', 0.45, 0.45, false],
};
const SR_FLAT_TEX = new Map();
// the tiles drawn this much of their size in SR_FLAT_KIND, so a lane stays clear between two rows or columns of a full
// room (a cell is SR_CELL; the widest tile then leaves 0.5 between) for the cables to run in (srCablePathFlat)
const SR_FLAT_TILE = 0.82;
function srFlatTexture(kind) {
  if (SR_FLAT_TEX.has(kind)) return SR_FLAT_TEX.get(kind);
  const [outline, name, hx, hz] = SR_FLAT_KIND[kind] || SR_FLAT_KIND.plinth, S = 128, cv = document.createElement('canvas');
  cv.width = cv.height = S;
  const g = cv.getContext('2d'), w = hx / 0.8 * (S / 2 - 4), h = hz / 0.8 * (S / 2 - 4), c = S / 2;
  g.beginPath();
  const poly = (pts) => { pts.forEach(([x, y], i) => (i ? g.lineTo(c + x * w, c + y * h) : g.moveTo(c + x * w, c + y * h))); g.closePath(); };
  const rect = (r) => g.roundRect(c - w, c - h, 2 * w, 2 * h, r);
  ({ circle: () => g.ellipse(c, c, w, h, 0, 0, Math.PI * 2), ring: () => g.ellipse(c, c, w, h, 0, 0, Math.PI * 2), clock: () => g.ellipse(c, c, w, h, 0, 0, Math.PI * 2),
    square: () => rect(6), round: () => rect(Math.min(w, h) * 0.45), window: () => rect(5), envelope: () => rect(4), lock: () => rect(10),
    pill: () => rect(h), hex: () => poly([[-1, 0], [-0.5, -1], [0.5, -1], [1, 0], [0.5, 1], [-0.5, 1]]),
    oct: () => poly([[-0.42, -1], [0.42, -1], [1, -0.42], [1, 0.42], [0.42, 1], [-0.42, 1], [-1, 0.42], [-1, -0.42]]),
    diamond: () => poly([[0, -1], [1, 0], [0, 1], [-1, 0]]), triangle: () => poly([[0, -1], [1, 1], [-1, 1]]),
    bucket: () => poly([[-1, -1], [1, -1], [0.72, 1], [-0.72, 1]]), sign: () => poly([[-1, -1], [0.6, -1], [1, 0], [0.6, 1], [-1, 1]]),
    shield: () => { g.moveTo(c - w, c - h); g.lineTo(c + w, c - h); g.lineTo(c + w, c); g.quadraticCurveTo(c + w, c + h * 0.7, c, c + h); g.quadraticCurveTo(c - w, c + h * 0.7, c - w, c); g.closePath(); },
    arch: () => { g.moveTo(c - w, c + h); g.lineTo(c - w, c - h * 0.1); g.arc(c, c - h * 0.1, w, Math.PI, 0); g.lineTo(c + w, c + h); g.closePath(); },
    gauge: () => { g.moveTo(c - w, c + h * 0.6); g.arc(c, c + h * 0.6, w, Math.PI, 0); g.lineTo(c + w, c + h); g.lineTo(c - w, c + h); g.closePath(); },
    cloud: () => {} }[outline] || (() => rect(6)))();
  if (outline === 'cloud') {   // puffs: the edge's grey a little larger under the white
    const puffs = (k) => { g.beginPath(); for (const [x, y, r] of [[-0.5, 0.25, 0.48], [0.05, -0.2, 0.62], [0.55, 0.2, 0.45]]) { g.moveTo(c + x * w + r * h * k, c + y * h); g.arc(c + x * w, c + y * h, r * h * k, 0, Math.PI * 2); }
      g.roundRect(c - w * 0.95 * k, c + h * 0.1, w * 1.9 * k, h * 0.75 * k, h * 0.3); };
    g.fillStyle = '#7a7a7a'; puffs(1.07); g.fill();
    g.fillStyle = '#ffffff'; puffs(1); g.fill();
  } else {
    g.fillStyle = '#ffffff'; g.fill();
    g.lineWidth = 5; g.strokeStyle = '#7a7a7a'; g.stroke();
  }
  g.strokeStyle = '#3a3a3a'; g.lineWidth = 4;   // a mark of the outline's own where it helps tell apart
  if (outline === 'ring') { g.beginPath(); g.ellipse(c, c, w * 0.78, h * 0.78, 0, 0, Math.PI * 2); g.stroke(); }
  if (outline === 'window') { g.beginPath(); g.moveTo(c - w, c - h * 0.55); g.lineTo(c + w, c - h * 0.55); g.stroke(); }
  if (outline === 'envelope') { g.beginPath(); g.moveTo(c - w, c - h); g.lineTo(c, c - h * 0.15); g.lineTo(c + w, c - h); g.stroke(); }
  if (outline === 'clock') { g.beginPath(); g.moveTo(c, c - h * 0.8); g.lineTo(c, c - h * 0.45); g.stroke(); }
  if (name) {
    g.fillStyle = '#2a2a2a';
    let px = 44;
    const room = 2 * w * (outline === 'diamond' || outline === 'triangle' ? 0.62 : 0.84);
    do { g.font = `700 ${px}px system-ui, -apple-system, 'Segoe UI', sans-serif`; px -= 2; } while (g.measureText(name).width > room && px > 14);
    g.textAlign = 'center'; g.textBaseline = 'middle';
    g.fillText(name, c, c + (outline === 'triangle' ? h * 0.3 : outline === 'window' ? h * 0.2 : outline === 'gauge' ? h * 0.35 : outline === 'envelope' ? h * 0.3 : 0));
  }
  const tex = new THREE.CanvasTexture(cv);
  tex.colorSpace = THREE.SRGBColorSpace; tex.anisotropy = 4;
  SR_FLAT_TEX.set(kind, tex);
  return tex;
}
/* A flat tile, lying on the floor's plane (the page's up the layout's -z). */
let srFlatGeoMade = null;
function srFlatGeo() {
  if (!srFlatGeoMade) { srFlatGeoMade = new THREE.PlaneGeometry(1.6 * SR_FLAT_TILE, 1.6 * SR_FLAT_TILE); srFlatGeoMade.rotateX(-Math.PI / 2); }
  return srFlatGeoMade;
}
/* The instanced mesh of a shape: the 3D's lit solids, or 2D's flat tiles (their colour the cloud's, unlit). */
function srShapeMesh(shape, count) {
  if (shape.startsWith('flat:')) {
    const mesh = new THREE.InstancedMesh(srFlatGeo(), new THREE.MeshBasicMaterial({ map: srFlatTexture(shape.slice(5)), alphaTest: 0.5, toneMapped: false }), count);
    mesh.userData.flatGeo = true;   // shared: never disposed with the mesh
    return mesh;
  }
  return new THREE.InstancedMesh(SR_SHAPES[shape](), new THREE.MeshLambertMaterial({ color: 0xffffff }), count);
}
// the services' names as people say them (the tag up close); an unknown one shows as it is written
const SR_SERVICE_NAME = { ec2: 'EC2', 'ec2.asg': 'EC2 Auto Scaling', ecs: 'ECS', 'ecs.fargate': 'ECS Fargate', eks: 'EKS', lambda: 'Lambda',
  stepfunctions: 'Step Functions', apprunner: 'App Runner', beanstalk: 'Elastic Beanstalk', elb: 'ELB', 'elb.alb': 'ALB', 'elb.nlb': 'NLB',
  cloudfront: 'CloudFront', route53: 'Route 53', waf: 'WAF', apigateway: 'API Gateway', rds: 'RDS', 'rds.mysql': 'RDS MySQL',
  'rds.postgres': 'RDS PostgreSQL', aurora: 'Aurora', dynamodb: 'DynamoDB', docdb: 'DocumentDB', elasticache: 'ElastiCache',
  opensearch: 'OpenSearch', s3: 'S3', efs: 'EFS', ebs: 'EBS', sqs: 'SQS', sns: 'SNS', eventbridge: 'EventBridge', kinesis: 'Kinesis',
  msk: 'MSK', ses: 'SES', cognito: 'Cognito', secretsmanager: 'Secrets Manager', kms: 'KMS', ssm: 'SSM', gce: 'Compute Engine',
  'gce.mig': 'Compute Engine MIG', run: 'Cloud Run', 'run.job': 'Cloud Run Job', functions: 'Cloud Functions', gke: 'GKE',
  appengine: 'App Engine', cloudsql: 'Cloud SQL', spanner: 'Spanner', firestore: 'Firestore', bigtable: 'Bigtable',
  bigquery: 'BigQuery', memorystore: 'Memorystore', gcs: 'Cloud Storage', pubsub: 'Pub/Sub', cloudtasks: 'Cloud Tasks',
  scheduler: 'Cloud Scheduler', workers: 'Workers', kv: 'Workers KV', d1: 'D1', r2: 'R2', queues: 'Queues', nextjs: 'Next.js',
  'elasticache.redis': 'ElastiCache Redis', 'cloudsql.postgres': 'Cloud SQL PostgreSQL', 'memorystore.redis': 'Memorystore Redis',
  containerapps: 'Container Apps', servicebus: 'Service Bus', cosmosdb: 'Cosmos DB', blob: 'Blob Storage', sql: 'Azure SQL',
  'cache.redis': 'Azure Cache for Redis' };
// a spec's keys the IaC tables give (document_tools iac_tables.TF_SPEC / CFN_SPEC), in words; any other key as written
const SR_SPEC_NAME = { instance_type: tl('sr.spec.instance'), instance_class: tl('sr.spec.instance'), node_type: tl('sr.spec.node_type'),
  machine_type: tl('sr.spec.machine_type'), tier: tl('sr.spec.tier'), version: tl('sr.spec.version'), storage_gb: tl('sr.spec.storage_gb'), storage_type: tl('sr.spec.storage_type'),
  memory_mb: tl('sr.spec.memory_mb'), memory: tl('sr.spec.memory'), cpu: 'CPU', timeout_s: tl('sr.spec.timeout_s'), runtime: tl('sr.spec.runtime'),
  multi_az: tl('sr.spec.multi_az'), nodes: tl('sr.spec.nodes'), tasks: tl('sr.spec.tasks') };
// the one value a tag up close shows: what the instance is, else its size
const SR_SPEC_MAIN = ['instance_type', 'instance_class', 'node_type', 'machine_type', 'tier', 'memory_mb', 'memory', 'cpu'];
const SR_SPEC_KIND = SR_SPEC_MAIN.slice(0, 5);
function srDetailText(n) {
  const name = SR_SERVICE_NAME[n.service] || n.service || '';
  const eng = n.engine && !name.toLowerCase().includes(String(n.engine).split(/\s/)[0].toLowerCase()) ? ` ${n.engine}` : '';
  const spec = Array.isArray(n.spec) ? n.spec : [];
  const main = SR_SPEC_MAIN.map((k) => spec.find((x) => x.key === k)).find(Boolean);
  // what the instance is speaks for itself (db.r6g.large); a size says which one it is (memory 2048)
  const shown = !main ? '' : SR_SPEC_KIND.includes(main.key) ? main.value : `${main.key} ${main.value}`;
  return [n.label || n.id, `${name}${eng}`.trim(), shown].filter(Boolean).join(' · ') + (n.count > 1 ? ` ×${n.count}` : '');
}
/* The 3D's colours (requester 10-22: 「サーバーのノードたち色合いがセンスないからもっとオシャレに」; ticket
   2026-10-22-viz-server-room-palette-and-light-flow). One designed set: a cloud is a hue, and the role sets how much of it
   shows — a floor holds a whisper of its cloud's hue, a node the hue itself, the focus and the flow's light the strongest.
   The hues sit at one lightness and chroma (OKLCH), so they read as a family; the ground and the frames are a cool slate,
   and the warm gold is kept for light (the flow, its glow) — the accent. Dark (2.3.9, item 2: 「ダークでも背景が白なの嫌だね」):
   the ground near-black, every floor at least 3:1 against it.
   SR_HUES: the clouds most rooms name, each its own hue; any other takes one of SR_HUE_RING by its name. */
const SR_HUES = { aws: 68, gcp: 255, azure: 222, cloudflare: 30, vercel: [270, 0.25], auth0: 300, supabase: 155, firebase: 48, fastly: 350,
  netlify: 190, heroku: 290, digitalocean: 235, oracle: 25, alibaba: 40, render: 165, fly: 300, github: [265, 0.3] };
const SR_HUE_RING = [255, 190, 300, 155, 32, 340, 222, 120];
const SR_ROLE = {   // [lightness, chroma] of a cloud's hue by role, light and dark
  light: { floor: [0.925, 0.06], floorStep: -0.02, node: [0.74, 0.175], box: [0.82, 0.12] },
  dark: { floor: [0.55, 0.095], floorStep: 0.018, node: [0.8, 0.165], box: [0.66, 0.125] },
};
const srOk = (L, C, h) => srOklch(L, C, h);
const SR_PAL = {
  light: { bg: srOk(0.972, 0.006, 250), logical: srOk(0.935, 0.03, 285), public: srOk(0.955, 0.02, 245), private: srOk(0.885, 0.035, 245),
    neutral: srOk(0.92, 0.01, 250), logicalBox: srOk(0.8, 0.045, 280), strip: srOk(0.93, 0.02, 280), plain: srOk(0.56, 0.035, 255),
    focus: srOk(0.52, 0.2, 262), cross: srOk(0.6, 0.19, 350), light: srOk(0.66, 0.2, 48), lightCore: srOk(0.86, 0.12, 80), nodeless: srOk(0.72, 0.02, 250) },
  dark: { bg: srOk(0.17, 0.016, 258), logical: srOk(0.53, 0.045, 285), public: srOk(0.55, 0.025, 245), private: srOk(0.52, 0.035, 245),
    neutral: srOk(0.53, 0.015, 250), logicalBox: srOk(0.6, 0.05, 280), strip: srOk(0.36, 0.03, 280), plain: srOk(0.66, 0.035, 255),
    focus: srOk(0.8, 0.13, 255), cross: srOk(0.7, 0.17, 350), light: srOk(0.83, 0.15, 78), lightCore: srOk(0.97, 0.05, 90), nodeless: srOk(0.72, 0.02, 250) },
};
/* OKLCH (L 0..1, C, h in degrees) to '#rrggbb' (out of gamut: clipped). */
function srOklch(L, C, h) {
  const a = C * Math.cos(h * Math.PI / 180), b = C * Math.sin(h * Math.PI / 180);
  const l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3, m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3, s = (L - 0.0894841775 * a - 1.291485548 * b) ** 3;
  const lin = [4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s, -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s, -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s];
  return '#' + lin.map((v) => { v = Math.min(1, Math.max(0, v)); const g = v <= 0.0031308 ? 12.92 * v : 1.055 * v ** (1 / 2.4) - 0.055; return Math.round(g * 255).toString(16).padStart(2, '0'); }).join('');
}
function srHue(p) {
  const k = String(p).toLowerCase(), known = SR_HUES[k];
  if (known !== undefined) return Array.isArray(known) ? known : [known, 1];
  let h = 0;
  for (const ch of k) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return [SR_HUE_RING[h % SR_HUE_RING.length], 1];
}
/* A cloud's colour for a role (node: the shapes, the legend's chip and the cost's bars; box: a closed group and the far
   view; floor: its floor, `level` deep) in the theme shown. */
function srProviderColor(p, role = 'node', level = 0, dark = isDark()) {
  const R = SR_ROLE[dark ? 'dark' : 'light'];
  if (!p) return dark ? SR_PAL.dark.nodeless : SR_PAL.light.nodeless;
  const [h, k] = srHue(p), [L, C] = R[role];
  return srOklch(L + (role === 'floor' ? R.floorStep * Math.min(level, 4) : 0), C * k, h);
}
const srVisible = (x, env) => !env || !Array.isArray(x.environments) || !x.environments.length || x.environments.includes(env);
function srEnvs(model) { return (model.environments || []).map((e) => (typeof e === 'string' ? { id: e, label: e } : { id: e.id, label: e.label || e.id })); }

/* The cables (ticket 2026-10-22-viz-sr-cables-too-thin-and-no-show-neighbours; requester: 「ノード同士を繋ぐ線が細すぎて
   みづらい」). A WebGL line is one pixel whatever is asked, so a cable is a strip: four corners per segment,
   pushed apart on the page by SR_CABLE_SHADER — at least `px` wide (pulled back) and, up close, as wide as
   `world` units up to `max` px, like the flows' light (59-sr-flows.js srFlowLightKeepSize) whose core is a little wider, so a light
   still reads as running inside its cable. A segment with an end behind the camera is cut at the near plane; one of
   length 0 (a migration step's edge before it grows) draws nothing. A cable is a path of segments (srCablePathOf);
   srCableShow / srCableShown / srCableGet / srCableDone draw part of one and read it (59-sr-migration.js): the order is
   the one srBuild laid them in. A cable running past the camera is held to `max` px, else it would fill the page. */
// The widths (requester 10-23, 2.3.20 in use: 「未選択の時の線はもっと全然細くていい」「選択時も少しだけ細くして」): the
// cables not chosen thin — px on the page at least, `faintWorld` units up close up to `faintMax` px; the strong layer (the
// chosen, the pointed, the reach) `focus` px, `world` units up close up to `max` px, inside the flows' light (its core
// at least 7/3 px in radius: 59-sr-flows.js).
const SR_CABLE = { plain: 0.9, cross: 1.1, bundle: 1, faintWorld: 0.025, faintMax: 1.8, focus: 3, world: 0.06, max: 5 };
/* Where a cable runs (requester 10-23: 「線がノードのオブジェクトの上にあるからわかりづらい、ちゃんとノード同士を繋ぐように
   してほしい」; then 「ノードの外にあることというよりノードの際外側と接地してることだね、今上に浮いてるから高さが合ってない
   他のオブジェクト避ける時だけ上に角度変えて」): from the side of one node to the side of the other, low — each end on the
   outer edge of the node as it is drawn now (its simple shape, or up close its model: srNodeFoot), at a height within the
   node, SR_ROUTE.side above its foot. Straight and flat between the two, unless something stands on the way (another node,
   a closed group's box): then the cable rises just before it (SR_ROUTE.ramp), passes SR_ROUTE.clear over its top, and
   comes down after it; obstacles near each other share one rise. A cable is a polyline: every set of cables, the strong
   layer, the flows' light and their branch hints, the migration's edges read the same path (srCablePathOf). The far
   view's bundles run the same way between the top groups' boxes (srBundlePath). */
// join: two rises nearer than this (units, ramp to ramp) are one — a cable through a crowded room rises once at the
// height of the tallest thing under it, rather than up and down over each (and a segment for each: 133,000 segments
// in the 2,000-node room, a frame up close 87 ms, against 5,000 and 18 before the paths)
const SR_ROUTE = { side: 0.3, ramp: 0.55, clear: 0.25, margin: 0.06, cross: 0.06, join: Infinity };
// a shape's or a model's extent around its middle (x, z half widths; y from its middle) and whether it is round
const SR_FOOT = new Map();
function srFootOfObject(key, make) {
  if (!SR_FOOT.has(key)) {
    const o = make(), box = new THREE.Box3().setFromObject(o);
    const round = o.isMesh && !(o.geometry && o.geometry.type === 'BoxGeometry');
    SR_FOOT.set(key, { hx: Math.max(Math.abs(box.min.x), box.max.x), hz: Math.max(Math.abs(box.min.z), box.max.z), y0: box.min.y, y1: box.max.y, round });
    o.traverse((x) => { if (x.geometry) x.geometry.dispose(); });
  }
  return SR_FOOT.get(key);
}
function srShapeFoot(shape) {
  if (shape.startsWith('flat:')) { const k = SR_FLAT_KIND[shape.slice(5)] || SR_FLAT_KIND.plinth; return { hx: k[2] * SR_FLAT_TILE, hz: k[3] * SR_FLAT_TILE, y0: -0.01, y1: 0.01, round: k[4] }; }
  return srFootOfObject(`shape:${shape}`, () => new THREE.Mesh(SR_SHAPES[shape]()));
}
function srModelFoot(kind) {
  return srFootOfObject(`model:${kind}`, () => {
    const g = new THREE.Group();
    for (const [geo, x, y, z, , rot] of srModelParts()[kind]) { const m = new THREE.Mesh(geo.clone()); m.position.set(x, y, z); if (rot) m.rotation.set(rot[0], rot[1], rot[2]); g.add(m); }
    g.updateMatrixWorld(true);
    return g;
  });
}
/* A node as drawn now, on the floor's plane: its middle, its half widths, its foot and top (world y), whether round. A node
   in a closed group is that group's box. */
function srNodeFoot(V, p) {
  if (p.hiddenIn) {
    const G = p.hiddenIn, h = 0.6 + Math.log2(1 + srCountNodes(G)) * 0.35, y = 0.06 * G.level;
    return { x: G.x + G.w / 2, z: G.z + SR_HEAD + (G.d - SR_HEAD) / 2, hx: (G.w - SR_PAD) / 2, hz: (G.d - SR_HEAD - SR_PAD * 0.5) / 2, y0: y, y1: y + h, round: false };
  }
  const sc = p.n.count > 1 ? 1 + Math.min(Math.log2(p.n.count), 4) * 0.12 : 1;
  const f = V.flat ? srShapeFoot(srShapeIn('simple', p.n))
    : V.detail && typeof srModelKind === 'function' ? srModelFoot(srModelKind(p.n)) : srShapeFoot(srShape(p.n.category));
  const mid = p.y + 0.75;
  return { x: p.x, z: p.z, hx: f.hx * sc, hz: f.hz * sc, y0: mid + f.y0 * sc, y1: mid + f.y1 * sc, round: f.round };
}
/* Where a ray from a foot's middle, along the unit (dx, dz), leaves its outline. */
function srFootExit(f, dx, dz) {
  if (f.round) return 1 / Math.hypot(dx / Math.max(f.hx, 1e-6), dz / Math.max(f.hz, 1e-6));
  return Math.min(Math.abs(dx) > 1e-9 ? f.hx / Math.abs(dx) : Infinity, Math.abs(dz) > 1e-9 ? f.hz / Math.abs(dz) : Infinity);
}
/* Where the segment s(t) = A + t (B - A), t in 0..1, crosses a foot grown by m (null: it does not), as [t in, t out]. */
function srFootSpan(f, A, B, m) {
  const dx = B[0] - A[0], dz = B[1] - A[1];
  if (f.round) {   // an ellipse: scaled to the unit circle
    const ax = (A[0] - f.x) / (f.hx + m), az = (A[1] - f.z) / (f.hz + m), bx = dx / (f.hx + m), bz = dz / (f.hz + m);
    const qa = bx * bx + bz * bz, qb = 2 * (ax * bx + az * bz), qc = ax * ax + az * az - 1, disc = qb * qb - 4 * qa * qc;
    if (qa < 1e-12 || disc <= 0) return null;
    const r = Math.sqrt(disc), t0 = (-qb - r) / (2 * qa), t1 = (-qb + r) / (2 * qa);
    return t1 < 0 || t0 > 1 ? null : [Math.max(0, t0), Math.min(1, t1)];
  }
  let t0 = 0, t1 = 1;   // a box: the slabs
  for (const [o, d, c, h] of [[A[0], dx, f.x, f.hx + m], [A[1], dz, f.z, f.hz + m]]) {
    if (Math.abs(d) < 1e-12) { if (Math.abs(o - c) > h) return null; continue; }
    let u0 = (c - h - o) / d, u1 = (c + h - o) / d;
    if (u0 > u1) [u0, u1] = [u1, u0];
    t0 = Math.max(t0, u0); t1 = Math.min(t1, u1);
    if (t0 > t1) return null;
  }
  return [t0, t1];
}
/* The feet of the nodes drawn, on a grid of SR_CELL, for the spans a cable may cross. */
function srFootGrid(V) {
  if (V.footGrid && V.footGrid.detail === V.detail) return V.footGrid;
  const cells = new Map(), feet = new Map(), boxes = new Set();
  for (const [id, p] of V.L.pos) {
    const f = srNodeFoot(V, p);
    feet.set(id, f);
    if (p.hiddenIn) { if (boxes.has(p.hiddenIn)) continue; boxes.add(p.hiddenIn); }
    f.id = id;
    for (let gx = Math.floor((f.x - f.hx) / SR_CELL); gx <= Math.floor((f.x + f.hx) / SR_CELL); gx++)
      for (let gz = Math.floor((f.z - f.hz) / SR_CELL); gz <= Math.floor((f.z + f.hz) / SR_CELL); gz++) {
        const k = `${gx},${gz}`; (cells.get(k) || cells.set(k, []).get(k)).push(f);
      }
  }
  V.footGrid = { cells, feet, detail: V.detail };
  return V.footGrid;
}
/* The path of a cable, from one node's side to the other's (see SR_ROUTE): points [x, y, z], at least two. */
function srCablePathOf(V, from, to, crossing) {
  if (V.flat) return srCablePathFlat(V, from, to, crossing);
  const grid = srFootGrid(V), fa = grid.feet.get(from), fb = grid.feet.get(to);
  if (!fa || !fb) return null;
  const lift = crossing ? SR_ROUTE.cross : 0;
  let dx = fb.x - fa.x, dz = fb.z - fa.z;
  const d = Math.hypot(dx, dz);
  const ya = Math.min(fa.y0 + SR_ROUTE.side, (fa.y0 + fa.y1) / 2) + lift, yb = Math.min(fb.y0 + SR_ROUTE.side, (fb.y0 + fb.y1) / 2) + lift;
  if (d < 1e-6 || (fa === fb)) return [[fa.x, ya, fa.z], [fa.x, ya, fa.z]];   // one place (a closed group to itself): nothing drawn
  dx /= d; dz /= d;
  const ea = srFootExit(fa, dx, dz), eb = srFootExit(fb, -dx, -dz);
  if (ea + eb >= d) return [[fa.x, ya, fa.z], [fa.x, ya, fa.z]];   // touching: no cable between them
  const A = [fa.x + dx * ea, fa.z + dz * ea], B = [fb.x - dx * eb, fb.z - dz * eb], len = d - ea - eb;
  // what stands on the way: the feet in the grid cells along it (its own two out)
  const seen = new Set([fa, fb]), spans = [];
  for (let k = 0, n = Math.ceil(len / (SR_CELL / 2)) + 1; k <= n; k++) {
    const x = A[0] + (B[0] - A[0]) * k / n, z = A[1] + (B[1] - A[1]) * k / n;
    for (let gx = Math.floor(x / SR_CELL) - 1; gx <= Math.floor(x / SR_CELL) + 1; gx++)
      for (let gz = Math.floor(z / SR_CELL) - 1; gz <= Math.floor(z / SR_CELL) + 1; gz++)
        for (const f of grid.cells.get(`${gx},${gz}`) || []) {
          if (seen.has(f)) continue;
          seen.add(f);
          const sp = srFootSpan(f, A, B, SR_ROUTE.margin);
          if (sp) spans.push([sp[0], sp[1], f.y1 + SR_ROUTE.clear]);
        }
  }
  const base = (t) => ya + (yb - ya) * t, at = (t, y) => [A[0] + (B[0] - A[0]) * t, y, A[1] + (B[1] - A[1]) * t];
  const pts = [at(0, ya)];
  if (spans.length) {   // rises, each over the obstacles it covers; two whose ramps would meet are one
    const r = SR_ROUTE.ramp / len, join = SR_ROUTE.join / len;
    spans.sort((p, q) => p[0] - q[0]);
    const humps = [];
    for (const sp of spans) {
      const h = humps[humps.length - 1];
      if (h && sp[0] - r <= h[1] + r + join) { h[1] = Math.max(h[1], sp[1]); h[2] = Math.max(h[2], sp[2]); } else humps.push([...sp]);
    }
    for (const [t0, t1, top] of humps) {
      const up = Math.max(0, t0 - r), down = Math.min(1, t1 + r), y = Math.max(top, base(t0), base(t1));
      if (up > 0) pts.push(at(up, base(up)));
      pts.push(at(t0, y), at(t1, y));
      if (down < 1) pts.push(at(down, base(down)));
    }
  }
  pts.push(at(1, yb));
  return pts;
}
const srCablePath = (V, e) => srCablePathOf(V, e.from, e.to, !!e.crossProvider);
/* 2D's cables (the plan's: 「重なる時は角を曲げて避ける」): from one tile's edge to the other's as the 3D's (srNodeFoot,
   srFootExit), flat under the tiles; straight when nothing is on the way, else around it with square corners: the
   shortest of an L either way, a run along the lane between two rows or columns next to either end (the cells' edges,
   SR_CELL / 2 from a node's middle), or a Z, that crosses no other tile. None clear (a full room, far apart): straight,
   under the tiles — drawn beneath them, never over one. */
const SR_FLAT_ROUTE = { y: 0.45, cross: 0.03, margin: 0.12, lanes: 6 };
function srFlatClear(V, grid, P, Q, skip) {
  const len = Math.hypot(Q[0] - P[0], Q[1] - P[1]);
  if (len < 1e-6) return true;
  const seen = new Set(skip);
  for (let k = 0, n = Math.ceil(len / (SR_CELL / 2)) + 1; k <= n; k++) {
    const x = P[0] + (Q[0] - P[0]) * k / n, z = P[1] + (Q[1] - P[1]) * k / n;
    for (let gx = Math.floor(x / SR_CELL) - 1; gx <= Math.floor(x / SR_CELL) + 1; gx++)
      for (let gz = Math.floor(z / SR_CELL) - 1; gz <= Math.floor(z / SR_CELL) + 1; gz++)
        for (const f of grid.cells.get(`${gx},${gz}`) || []) {
          if (seen.has(f)) continue;
          seen.add(f);
          if (srFootSpan(f, P, Q, SR_FLAT_ROUTE.margin)) return false;
        }
  }
  return true;
}
function srCablePathFlat(V, from, to, crossing) {
  const grid = srFootGrid(V), fa = grid.feet.get(from), fb = grid.feet.get(to);
  if (!fa || !fb) return null;
  const y = SR_FLAT_ROUTE.y + (crossing ? SR_FLAT_ROUTE.cross : 0), skip = [fa, fb];
  const none = [[fa.x, y, fa.z], [fa.x, y, fa.z]];
  let dx = fb.x - fa.x, dz = fb.z - fa.z;
  const d = Math.hypot(dx, dz);
  if (d < 1e-6 || fa === fb) return none;
  dx /= d; dz /= d;
  const ea = srFootExit(fa, dx, dz), eb = srFootExit(fb, -dx, -dz);
  if (ea + eb >= d) return none;
  const A = [fa.x + dx * ea, fa.z + dz * ea], B = [fb.x - dx * eb, fb.z - dz * eb];
  if (srFlatClear(V, grid, A, B, skip)) return [[A[0], y, A[1]], [B[0], y, B[1]]];
  // the corners' routes: each leg along x or z, leaving and entering the tiles at their edges
  const out = (f, ux, uz) => { const e = srFootExit(f, ux, uz); return [f.x + ux * e, f.z + uz * e]; };
  const sx = Math.sign(fb.x - fa.x), sz = Math.sign(fb.z - fa.z), tries = [];
  if (sx && sz) {
    tries.push([out(fa, sx, 0), [fb.x, fa.z], out(fb, 0, -sz)]);     // along x, then z
    tries.push([out(fa, 0, sz), [fa.x, fb.z], out(fb, -sx, 0)]);     // along z, then x
  }
  const h = SR_CELL / 2;
  for (const s1 of [1, -1]) {
    // along the lane next to one end, then straight into the other (3 legs)
    tries.push([out(fa, 0, s1), [fa.x, fa.z + s1 * h], [fb.x, fa.z + s1 * h], out(fb, 0, Math.sign(fa.z + s1 * h - fb.z) || -s1)]);
    tries.push([out(fa, 0, Math.sign(fb.z + s1 * h - fa.z) || s1), [fa.x, fb.z + s1 * h], [fb.x, fb.z + s1 * h], out(fb, 0, s1)]);
    tries.push([out(fa, s1, 0), [fa.x + s1 * h, fa.z], [fa.x + s1 * h, fb.z], out(fb, Math.sign(fa.x + s1 * h - fb.x) || -s1, 0)]);
    tries.push([out(fa, Math.sign(fb.x + s1 * h - fa.x) || s1, 0), [fb.x + s1 * h, fa.z], [fb.x + s1 * h, fb.z], out(fb, s1, 0)]);
    for (const s2 of [1, -1]) {   // the lane by one end, the cross lane by the other (4 legs)
      tries.push([out(fa, 0, s1), [fa.x, fa.z + s1 * h], [fb.x + s2 * h, fa.z + s1 * h], [fb.x + s2 * h, fb.z], out(fb, s2, 0)]);
      tries.push([out(fa, s1, 0), [fa.x + s1 * h, fa.z], [fa.x + s1 * h, fb.z + s2 * h], [fb.x, fb.z + s2 * h], out(fb, 0, s2)]);
    }
  }
  for (let k = 0; k <= SR_FLAT_ROUTE.lanes; k++) for (const sgn of k ? [1, -1] : [1]) {
    const off = sgn * k * SR_CELL / 2;
    if (sx) { const xm = (fa.x + fb.x) / 2 + off; tries.push([out(fa, Math.sign(xm - fa.x) || sx, 0), [xm, fa.z], [xm, fb.z], out(fb, Math.sign(xm - fb.x) || -sx, 0)]); }
    if (sz) { const zm = (fa.z + fb.z) / 2 + off; tries.push([out(fa, 0, Math.sign(zm - fa.z) || sz), [fa.x, zm], [fb.x, zm], out(fb, 0, Math.sign(zm - fb.z) || -sz)]); }
  }
  const length = (pts) => pts.slice(1).reduce((a, q, i) => a + Math.hypot(q[0] - pts[i][0], q[1] - pts[i][1]), 0);
  // the shortest first: the first clear one is the one (fewer checks on a full room)
  const best = tries.map((pts) => [length(pts), pts]).sort((a, b) => a[0] - b[0])
    .find(([, pts]) => pts.slice(1).every((q, i) => srFlatClear(V, grid, pts[i], q, skip)));
  return (best ? best[1] : [A, B]).map((q) => [q[0], y, q[1]]);
}
/* A bundle between two top groups' boxes, from the side of one to the side of the other, rising over the boxes between. */
function srBundlePath(V, A, B, crossing) {
  const foot = (G) => ({ x: G.x + G.w / 2, z: G.z + G.d / 2, hx: G.w * 0.46, hz: G.d * 0.46, y0: 0, y1: G.boxH, round: false });
  if (V.flat) {   // 2D, pulled back: side to side, straight (the boxes are flat, nothing to go round at this size)
    const fa = foot(A), fb = foot(B), y = SR_FLAT_ROUTE.y + (crossing ? SR_FLAT_ROUTE.cross : 0) + 0.6;
    let dx = fb.x - fa.x, dz = fb.z - fa.z;
    const d = Math.hypot(dx, dz);
    if (d < 1e-6) return [[fa.x, y, fa.z], [fa.x, y, fa.z]];
    dx /= d; dz /= d;
    const ea = srFootExit(fa, dx, dz), eb = srFootExit(fb, -dx, -dz);
    if (ea + eb >= d) return [[fa.x, y, fa.z], [fa.x, y, fa.z]];
    return [[fa.x + dx * ea, y, fa.z + dz * ea], [fb.x - dx * eb, y, fb.z - dz * eb]];
  }
  const fa = foot(A), fb = foot(B), lift = crossing ? SR_ROUTE.cross : 0;
  let dx = fb.x - fa.x, dz = fb.z - fa.z;
  const d = Math.hypot(dx, dz);
  const ya = Math.min(SR_ROUTE.side * 2, A.boxH / 2) + lift, yb = Math.min(SR_ROUTE.side * 2, B.boxH / 2) + lift;
  if (d < 1e-6) return [[fa.x, ya, fa.z], [fa.x, ya, fa.z]];
  dx /= d; dz /= d;
  const ea = srFootExit(fa, dx, dz), eb = srFootExit(fb, -dx, -dz);
  if (ea + eb >= d) return [[fa.x, ya, fa.z], [fa.x, ya, fa.z]];
  const P = [fa.x + dx * ea, fa.z + dz * ea], Q = [fb.x - dx * eb, fb.z - dz * eb], len = d - ea - eb, r = SR_ROUTE.ramp * 2 / len;
  const spans = V.L.tops.filter((G) => G !== A && G !== B).map((G) => { const sp = srFootSpan(foot(G), P, Q, SR_ROUTE.margin); return sp ? [sp[0], sp[1], G.boxH + SR_ROUTE.clear] : null; }).filter(Boolean).sort((p, q) => p[0] - q[0]);
  const base = (t) => ya + (yb - ya) * t, at = (t, y) => [P[0] + (Q[0] - P[0]) * t, y, P[1] + (Q[1] - P[1]) * t], pts = [at(0, ya)];
  for (const [t0, t1, top] of spans) {
    const up = Math.max(0, t0 - r), down = Math.min(1, t1 + r), y = Math.max(top, base(t0), base(t1));
    if (up > 0) pts.push(at(up, base(up)));
    pts.push(at(t0, y), at(t1, y));
    if (down < 1) pts.push(at(down, base(down)));
  }
  pts.push(at(1, yb));
  return pts;
}
const SR_CABLE_SHADER = {
  vertex: `attribute vec3 cableStart; attribute vec3 cableEnd; uniform vec2 uRes; uniform float uPx, uWorld, uMax; varying float vDist;
    void main() {
      vec4 a = modelViewMatrix * vec4(cableStart, 1.0), b = modelViewMatrix * vec4(cableEnd, 1.0);
      float len = distance(cableStart, cableEnd);
      float near = -projectionMatrix[3][2] / (projectionMatrix[2][2] - 1.0);   // the near plane's z (the camera looks down -z)
      if (a.z > near && b.z > near) { gl_Position = vec4(2.0, 2.0, 2.0, 1.0); vDist = 0.0; return; }
      if (a.z > near) a = mix(b, a, (b.z - near) / (b.z - a.z) * 0.999);
      if (b.z > near) b = mix(a, b, (a.z - near) / (a.z - b.z) * 0.999);
      vec4 ca = projectionMatrix * a, cb = projectionMatrix * b;
      vec2 sa = ca.xy / ca.w * uRes, sb = cb.xy / cb.w * uRes, d = sb - sa;
      float dl = length(d);
      vec2 dir = dl > 1e-5 ? d / dl : vec2(1.0, 0.0), nrm = vec2(-dir.y, dir.x);
      vec4 c = position.y < 0.5 ? ca : cb;
      float w = len > 1e-6 ? clamp(uWorld * projectionMatrix[1][1] * uRes.y / c.w, uPx, max(uPx, uMax)) : 0.0;
      c.xy += nrm * position.x * w / uRes * c.w;
      vDist = position.y * len;
      gl_Position = c;
    }`,
  fragment: `uniform vec3 uColor; uniform float uOpacity, uDash, uGap; varying float vDist;
    void main() {
      if (uDash > 0.0 && mod(vDist, uDash + uGap) > uDash) discard;
      gl_FragColor = vec4(uColor, uOpacity);
      #include <colorspace_fragment>
    }`,   // the colour as the old lines drew it: uColor is linear (THREE.Color), the page sRGB
};
/* A set of cables from [ax, ay, az, bx, by, bz, ...]: `px` the least width on the page, `dash`/`gap` world units (0: solid). */
function srCables(paths, { color, opacity = 1, px = SR_CABLE.plain, dash = 0, gap = 0, world = SR_CABLE.faintWorld, max = SR_CABLE.faintMax }) {
  const g = new THREE.BufferGeometry();
  srCableFill(g, paths);
  const m = new THREE.ShaderMaterial({ vertexShader: SR_CABLE_SHADER.vertex, fragmentShader: SR_CABLE_SHADER.fragment, transparent: opacity < 1, depthWrite: opacity >= 1, side: THREE.DoubleSide,   // the corners' winding is the page's, whichever way the cable runs
    uniforms: { uColor: { value: new THREE.Color(color) }, uOpacity: { value: opacity }, uRes: { value: new THREE.Vector2(1, 1) }, uPx: { value: px },
      uWorld: { value: world }, uMax: { value: max }, uDash: { value: dash }, uGap: { value: gap } } });
  m.opacity = opacity;   // read as a LineBasicMaterial's was (the board, the e2e); the shader reads uOpacity
  const mesh = new THREE.Mesh(g, m);
  mesh.frustumCulled = false;   // the strips are placed by the shader: the box three would cull by is the corners'
  mesh.userData.cables = true; mesh.userData.dashed = dash > 0;
  mesh.onBeforeRender = (renderer) => renderer.getSize(m.uniforms.uRes.value).multiplyScalar(0.5);   // half the page: NDC 1 is this many px
  return mesh;
}
/* Four corners a segment, each carrying both its ends; a cable (one path, srCablePathOf) is its segments one after
   the other, kept as geometry.userData.paths[j] = {i0, pts, lens, len}. Not instanced: measured in the e2e's software GL,
   up close in the 2,000-node room, 5,000 instanced strips made a frame's p90 56 ms (17 with the old lines); written
   out, 20. */
function srCableFill(g, paths) {
  const list = [], segs = [];
  for (const pts of paths) {
    const i0 = segs.length, lens = [];
    for (let k = 0; k + 1 < pts.length; k++) { segs.push([pts[k], pts[k + 1]]); lens.push(Math.hypot(pts[k + 1][0] - pts[k][0], pts[k + 1][1] - pts[k][1], pts[k + 1][2] - pts[k][2])); }
    list.push({ i0, pts, lens, len: lens.reduce((x, y) => x + y, 0) });
  }
  const n = segs.length, corner = new Float32Array(n * 12), st = new Float32Array(n * 12), en = new Float32Array(n * 12), idx = new Uint32Array(n * 6);
  for (let i = 0; i < n; i++) {
    corner.set([-0.5, 0, 0, 0.5, 0, 0, -0.5, 1, 0, 0.5, 1, 0], i * 12);
    for (let k = 0; k < 4; k++) for (let c = 0; c < 3; c++) { st[i * 12 + k * 3 + c] = segs[i][0][c]; en[i * 12 + k * 3 + c] = segs[i][1][c]; }
    idx.set([0, 1, 2, 2, 1, 3].map((x) => i * 4 + x), i * 6);
  }
  g.setAttribute('position', new THREE.BufferAttribute(corner, 3));
  g.setAttribute('cableStart', new THREE.BufferAttribute(st, 3));
  g.setAttribute('cableEnd', new THREE.BufferAttribute(en, 3));
  g.setIndex(new THREE.BufferAttribute(idx, 1));
  g.userData.paths = list;
  g.userData.cables = paths.length;
}
/* A set's cables all made again (the strong layer: the pressed, the pointed, the reach; every set when the look changes). */
function srCablesRefill(mesh, paths) {
  mesh.geometry.dispose();
  mesh.geometry = new THREE.BufferGeometry();
  srCableFill(mesh.geometry, paths);
}
const srCableCount = (mesh) => mesh.geometry.userData.cables;
const srCablePts = (mesh, j) => mesh.geometry.userData.paths[j].pts;
/* Cable j drawn from f0 to f1 of its length (0..1), the rest of it not (a migration's edge going to its middle, or
   coming out of its start); its segments written, srCableDone hands them over. */
function srCableShow(mesh, j, f0, f1) {
  const P = mesh.geometry.userData.paths[j], st = mesh.geometry.getAttribute('cableStart').array, en = mesh.geometry.getAttribute('cableEnd').array;
  const lo = f0 * P.len, hi = f1 * P.len;
  let at = 0;
  for (let k = 0; k < P.lens.length; k++) {
    const a = P.pts[k], b = P.pts[k + 1], l = P.lens[k], u0 = Math.min(1, Math.max(0, (lo - at) / (l || 1))), u1 = Math.min(1, Math.max(0, (hi - at) / (l || 1)));
    const s0 = a.map((x, c) => x + (b[c] - x) * u0), s1 = u1 > u0 ? a.map((x, c) => x + (b[c] - x) * u1) : s0;
    const i = P.i0 + k;
    for (let q = 0; q < 4; q++) for (let c = 0; c < 3; c++) { st[i * 12 + q * 3 + c] = s0[c]; en[i * 12 + q * 3 + c] = s1[c]; }
    at += l;
  }
}
/* How much of cable j is drawn now (0..1), and its two ends as drawn. */
function srCableShown(mesh, j) {
  const P = mesh.geometry.userData.paths[j], st = mesh.geometry.getAttribute('cableStart').array, en = mesh.geometry.getAttribute('cableEnd').array;
  let drawn = 0;
  for (let k = 0; k < P.lens.length; k++) { const i = P.i0 + k; drawn += Math.hypot(en[i * 12] - st[i * 12], en[i * 12 + 1] - st[i * 12 + 1], en[i * 12 + 2] - st[i * 12 + 2]); }
  return P.len ? drawn / P.len : 0;
}
/* Cable j's two ends (its path's first and last points). */
function srCableGet(mesh, j) { const pts = srCablePts(mesh, j); return [pts[0], pts[pts.length - 1]]; }
function srCableDone(mesh) { for (const k of ['cableStart', 'cableEnd']) mesh.geometry.getAttribute(k).needsUpdate = true; }

/* Places every group and node (sizes bottom-up, places top-down); the external nodes on a strip in front. */
function srLayout(model, env, showFold, closed = new Set(), only = new Set()) {
  const groups = new Map();
  for (const g of model.groups || []) if (srVisible(g, env)) groups.set(g.id, { g, kids: [], nodes: [], level: 0 });
  const roots = [];
  for (const G of groups.values()) { const p = G.g.parent && groups.get(G.g.parent); (p ? p.kids : roots).push(G); }
  const loose = { g: { id: '', kind: 'logical', label: tl('sr.group.none') }, kids: [], nodes: [], level: 0 }, ext = [];
  // clouds chosen on the board (2.3.9, item 3): only their nodes; one with no provider is out while any is chosen
  const nodes = (model.nodes || []).filter((n) => srVisible(n, env) && (showFold || !n.fold) && (!only.size || only.has(n.providerResolved || n.provider)));
  for (const n of nodes) {
    if (n.external || n.category === 'external.saas') { ext.push(n); continue; }
    const G = n.group && groups.get(n.group);
    (G ? G.nodes : loose.nodes).push(n);
  }
  if (loose.nodes.length) roots.push(loose);
  if (only.size) {   // a group with nothing left inside is not drawn while clouds are chosen
    const keep = (G) => { G.kids = G.kids.filter(keep); return G.nodes.length > 0 || G.kids.length > 0; };
    roots.splice(0, roots.length, ...roots.filter(keep));
  }
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
  SR.model = model; SR.migBase = null;
  showOverlay(srEl);
  setText($('sr-room'), (PROJECT[SR.project] && PROJECT[SR.project].name) || '');
  const envs = srEnvs(model);
  $('sr-env').innerHTML = envs.length ? envs.map((e) => `<option value="${esc(e.id)}">${esc(e.label)}</option>`).join('') : `<option value="">${esc(tl('sr.env.none'))}</option>`;
  $('sr-env').disabled = envs.length < 2;
  $('sr-fold').checked = false;
  SR.closed = new Set(); SR.selected = null; SR.selectedGroup = null; SR.hover = null; SR.only = new Set();
  $('sr-lines').value = SR.lines;
  SR.flat = srViewPref(SR.project);   // the look this project was last seen in (56-server-cost.js srSetFlat)
  srModeButtons();
  srBuild();
  $('sr-back').focus({ preventScroll: true });
}
function srClose() {
  if (SR.phase !== 'open') return;
  SR.phase = 'idle';
  SR.reach = null;
  srMigStop(true);   // a plan open: the room's own model again (59-sr-migration.js)
  srBoxEnd();
  srBoxArm(false);
  if (typeof srCostReset === 'function') srCostReset();
  srDispose();
  hideOverlay(srEl);
  SR.seq += 1;
  srLog(tl('sr.log.back'));
  if (SR.opener && SR.opener.focus) SR.opener.focus({ preventScroll: true });
}
function srDispose() {
  const V = SR.view;
  if (!V) return;
  srFlowStop();          // 59-sr-flows.js: a flow playing belongs to this 3D
  cancelAnimationFrame(V.raf);
  V.ro.disconnect();
  V.controls.dispose();
  V.scene.traverse((o) => {
    if (o.userData.flatGeo) { o.material.dispose(); return; }   // 2D's tile and its canvases are the page's, kept for the next build
    if (o.geometry) o.geometry.dispose(); if (o.material) { for (const m of [].concat(o.material)) { if (m.map) m.map.dispose(); m.dispose(); } }
  });
  V.renderer.renderLists.dispose();   // the renderer stays: a new one on the same canvas drew its first frame washed out
  for (const url of V.iconUrls) URL.revokeObjectURL(url);
  if (V.reachMats) for (const m of V.reachMats.values()) m.dispose();   // a faint copy not on a model now is in no scene
  $('sr-labels').innerHTML = '';
  SR.view = null;
}
/* keep: {pos, target} — the camera the view had (the theme, a migration step): set before the first frame is drawn,
   so the fit view is never seen in between. */
function srBuild(keep) {
  const t0 = srNow();
  SR.builds = (SR.builds || 0) + 1;   // the e2e: a migration step builds nothing
  srDispose();
  const model = SR.model, env = $('sr-env').value || '', fold = $('sr-fold').checked;
  const L = srLayout(model, env, fold, SR.closed, SR.only);
  // a chosen or pointed node not drawn now (another environment, a cloud not chosen, folded) is let go (the independent verification)
  for (const k of ['selected', 'hover']) if (SR[k] && !(L.pos.has(SR[k]) && !L.pos.get(SR[k]).hiddenIn)) SR[k] = null;
  const cv = $('sr-canvas'), box = cv.parentElement;
  // one renderer for the page's server room, kept across builds (the video, 10-22: each build made a new one on the same
  // canvas, and its first frame showed the floors white and the models pale — once a migration step, once a theme)
  const renderer = SR.renderer || (SR.renderer = new THREE.WebGLRenderer({ canvas: cv, antialias: true }));
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  const scene = new THREE.Scene();
  const dark = isDark(), PAL = dark ? SR_PAL.dark : SR_PAL.light;
  scene.background = new THREE.Color(PAL.bg);
  scene.add(new THREE.HemisphereLight(0xffffff, 0x445566, 1.6));
  const sun = new THREE.DirectionalLight(0xffffff, 1.2); sun.position.set(30, 60, 40); scene.add(sun);
  const flat = SR.flat;
  // 2D: straight down (OrbitControls' polar angle 0 against the usual up), so the page's top is the layout's -z as the 3D
  // looks from the south; no turning: a drag moves, the wheel zooms
  const camera = flat ? new THREE.OrthographicCamera(-SR_FLAT.half, SR_FLAT.half, SR_FLAT.half, -SR_FLAT.half, 1, SR_FLAT.height * 2)
    : new THREE.PerspectiveCamera(45, 1, 0.1, 5000);
  const controls = new OrbitControls(camera, cv);
  Object.assign(controls, { enableDamping: !reduceMotion, dampingFactor: 0.12, screenSpacePanning: true, minDistance: 3, maxDistance: 4000, maxPolarAngle: Math.PI * 0.48 });
  if (flat) {
    Object.assign(controls, { enableRotate: false, minZoom: SR_FLAT.half * 2 / 4000, maxZoom: SR_FLAT.half * 2 / 3, minPolarAngle: 0, maxPolarAngle: 0 });
    controls.mouseButtons = { LEFT: THREE.MOUSE.PAN, MIDDLE: THREE.MOUSE.DOLLY, RIGHT: THREE.MOUSE.PAN };
    controls.touches = { ONE: THREE.TOUCH.PAN, TWO: THREE.TOUCH.DOLLY_PAN };
  }
  const V = { flat, renderer, scene, camera, controls, L, near: new THREE.Group(), far: new THREE.Group(), lod: 'near', pick: [], iconUrls: [], raf: 0,
    frames: [], labelAt: 0, labels: [], ro: null, env, fold, dark, floorColors: [] };
  V.far.visible = false;   // srLod only switches on a change: a view that opens near never showed the far boxes' level
  scene.add(V.near, V.far);
  // floors: one instanced box for all of them
  const floorMesh = new THREE.InstancedMesh(new THREE.BoxGeometry(1, 1, 1), new THREE.MeshLambertMaterial({ color: 0xffffff }), Math.max(1, L.floors.length));
  const m4 = new THREE.Matrix4(), col = new THREE.Color(), q = new THREE.Quaternion(), sc = new THREE.Vector3(), at = new THREE.Vector3();
  L.floors.forEach((G, i) => {
    const h = 0.05, y = 0.06 * G.level + h / 2;
    m4.compose(at.set(G.x + G.w / 2, y, G.z + G.d / 2), q, sc.set(G.w, h, G.d));
    floorMesh.setMatrixAt(i, m4);
    const g = G.g, base = g.kind === 'logical' ? PAL.logical : g.visibility === 'public' ? PAL.public : g.visibility === 'private' ? PAL.private
      : g.provider ? srProviderColor(g.provider, 'floor', G.level, dark) : PAL.neutral;
    col.set(base);
    floorMesh.setColorAt(i, col);
    V.floorColors.push(`#${col.getHexString()}`);
  });
  floorMesh.count = L.floors.length;
  floorMesh.userData.groups = L.floors.map((G) => G.g.id);
  V.near.add(floorMesh); V.pick.push(floorMesh); V.floorMesh = floorMesh;
  if (L.closed.length) {   // the closed groups: a box each, as tall as what it holds
    const cm = new THREE.InstancedMesh(new THREE.BoxGeometry(1, 1, 1), new THREE.MeshLambertMaterial({ color: 0xffffff }), L.closed.length);
    L.closed.forEach((G, i) => {
      const h = 0.6 + Math.log2(1 + srCountNodes(G)) * 0.35;
      m4.compose(at.set(G.x + G.w / 2, 0.06 * G.level + h / 2, G.z + SR_HEAD + (G.d - SR_HEAD) / 2), q, sc.set(G.w - SR_PAD, h, G.d - SR_HEAD - SR_PAD * 0.5));
      cm.setMatrixAt(i, m4);
      cm.setColorAt(i, col.set(G.g.kind === 'logical' ? PAL.logicalBox : srProviderColor(G.g.providerResolved || G.g.provider, 'box', 0, dark)));
    });
    cm.userData.groups = L.closed.map((G) => G.g.id);
    V.near.add(cm); V.pick.push(cm);
  }
  // nodes: one instanced mesh per shape, twice — the simple shapes, and up close the shapes by service (srSetDetail
  // shows one set and gives it to the picking)
  V.nodeSets = { simple: new THREE.Group(), detail: new THREE.Group() };
  V.nodeMeshes = { simple: [], detail: [] };
  V.nodeSets.detail.visible = false;
  V.detail = false;
  for (const set of flat ? ['simple'] : ['simple', 'detail']) {   // 2D: one set, the flat tiles
    const byShape = {};
    for (const p of L.pos.values()) if (!p.hiddenIn) (byShape[srShapeIn(set, p.n)] = byShape[srShapeIn(set, p.n)] || []).push(p);
    for (const [shape, list] of Object.entries(byShape)) {
      const mesh = srShapeMesh(shape, list.length);
      list.forEach((p, i) => {
        const s = p.n.count > 1 ? 1 + Math.min(Math.log2(p.n.count), 4) * 0.12 : 1;
        m4.compose(at.set(p.x, p.y + 0.75, p.z), q, sc.set(s, s, s));
        mesh.setMatrixAt(i, m4);
        mesh.setColorAt(i, col.set(srProviderColor(p.n.providerResolved || p.n.provider, 'node', 0, dark)));
      });
      mesh.userData.nodes = list.map((p) => p.n.id);
      mesh.userData.shape = shape;
      V.nodeSets[set].add(mesh); V.nodeMeshes[set].push(mesh);
    }
  }
  V.near.add(V.nodeSets.simple, V.nodeSets.detail);
  V.pick.push(...V.nodeMeshes.simple);
  // cables: within a provider solid, across providers dashed magenta and higher (requester: 跨いでいることが見て分かる)
  const plain = [], cross = [];
  for (const e of L.edges) {
    (e.crossProvider ? cross : plain).push(srCablePath(V, e));
  }
  V.plainLines = srCables(plain, { color: PAL.plain, opacity: SR.plainOpacity, px: SR_CABLE.plain });
  V.crossLines = srCables(cross, { color: PAL.cross, opacity: SR.crossOpacity, px: SR_CABLE.cross, dash: 0.5, gap: 0.3 });
  // the strong layer: the pressed, the pointed node's and the reach's cables (srFocusLines fills it)
  V.focusLines = srCables([], { color: PAL.focus, px: SR_CABLE.focus, world: SR_CABLE.world, max: SR_CABLE.max });
  V.focusCross = srCables([], { color: PAL.cross, px: SR_CABLE.focus, world: SR_CABLE.world, max: SR_CABLE.max });
  V.focusLines.renderOrder = V.focusCross.renderOrder = 2;
  V.near.add(V.plainLines, V.crossLines, V.focusLines, V.focusCross);
  // far: the top groups as boxes, the cables bundled between them
  const tops = L.tops, topIndex = new Map(tops.map((G, i) => [G, i]));
  const boxMesh = new THREE.InstancedMesh(new THREE.BoxGeometry(1, 1, 1), new THREE.MeshLambertMaterial({ color: 0xffffff }), Math.max(1, tops.length));
  tops.forEach((G, i) => {
    const n = srCountNodes(G), h = 0.8 + Math.log2(1 + n) * 0.6;
    G.boxH = h; G.nodeCount = n;
    m4.compose(at.set(G.x + G.w / 2, h / 2, G.z + G.d / 2), q, sc.set(G.w * 0.92, h, G.d * 0.92));
    boxMesh.setMatrixAt(i, m4);
    boxMesh.setColorAt(i, col.set(G.g.kind === 'logical' ? PAL.logicalBox : srProviderColor(G.g.provider, 'box', 0, dark)));
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
    (B.cross ? bc : bp).push(srBundlePath(V, B.a, B.b, !!B.cross));
  }
  V.bundles = [...bundles.values()];
  // the far view's bundles: as faint as the near cables, and the lines switch holds there too (the independent verification of item 1)
  V.farPlain = srCables(bp, { color: PAL.plain, opacity: SR.plainOpacity, px: SR_CABLE.bundle });
  V.farCross = srCables(bc, { color: PAL.cross, opacity: SR.crossOpacity, px: SR_CABLE.bundle, dash: 1.2, gap: 0.7 });
  V.far.add(V.farPlain, V.farCross);
  // the external strip's sign
  if (L.ext.length) {
    const strip = new THREE.Mesh(new THREE.BoxGeometry(L.ext.length * SR_CELL * 1.3, 0.04, SR_CELL * 1.6), new THREE.MeshLambertMaterial({ color: PAL.strip }));
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
  srLinesMode(V);
  srFocusLines(V);
  srFit(true);
  if (keep && !!keep.flat === flat) { camera.position.copy(keep.pos); controls.target.copy(keep.target); if (flat) { camera.zoom = keep.zoom; camera.updateProjectionMatrix(); } controls.update(); }
  srCounts(L);
  cv.onpointerdown = (e) => { V.downAt = [e.clientX, e.clientY]; };
  cv.onpointermove = (e) => {   // the pointed node's cables, strong (at most every 60 ms)
    if (e.buttons || srNow() - (V.hoverAt || 0) < 60) return;
    V.hoverAt = srNow();
    const id = srNodeAt(V, e);
    if (id !== SR.hover) { SR.hover = id; srFocusLines(V); }
  };
  cv.onpointerleave = () => { if (SR.hover) { SR.hover = null; srFocusLines(V); } };
  cv.onpointerup = (e) => { if (V.downAt && Math.hypot(e.clientX - V.downAt[0], e.clientY - V.downAt[1]) < 5) srPick(e); V.downAt = null; };
  srReachAfterBuild(V);
  srFlowBuild(V);          // 59-sr-flows.js: the cones over the nodes that start a flow
  srMigAfterBuild(V);      // 59-sr-migration.js: a plan open, its state drawn
  const loop = () => {   // the cost view over the stage pauses it (SR.paused, 56-server-cost.js): no frame drawn meanwhile
    if (SR.paused) { V.raf = 0; return; }
    V.raf = requestAnimationFrame(loop);
    const t = srNow();
    const dt = V.last ? Math.min(t - V.last, 100) : 16;
    if (V.last) { V.frames.push(t - V.last); if (V.frames.length > 240) V.frames.shift(); }
    V.last = t;
    controls.update();
    if (SR.camTrail) SR.camTrail.push(camera.position.toArray().concat(controls.target.toArray()));   // the e2e: each frame's camera
    srLod(V);
    srFlowTick(V, dt);
    srMigTick(V, dt);
    if (t - V.labelAt > 100) { V.labelAt = t; srPlaceLabels(V); }
    renderer.render(scene, camera);
    if (SR.pixTrail) SR.pixTrail.push(srPixMean(renderer));   // the e2e: each frame's colour, read as it was drawn
  };
  V.loop = loop;
  loop();
  SR.stats = { firstMs: Math.round(srNow() - t0), nodes: L.nodes.length, edges: L.edges.length, floors: L.floors.length };
  srLog(tl('sr.log.drawn', { nodes: L.nodes.length, edges: L.edges.length, floors: L.floors.length, ms: SR.stats.firstMs })
    + (env ? tl('sr.log.drawn.env', { env }) : ''));
}
/* The mean colour of a 12 x 8 grid of the frame just drawn (read before the browser clears it): the e2e holds that a
   redraw never shows a frame in other colours. */
function srPixMean(renderer) {
  const gl = renderer.getContext(), w = gl.drawingBufferWidth, h = gl.drawingBufferHeight, px = new Uint8Array(4), sum = [0, 0, 0];
  for (let i = 0; i < 12; i++) for (let j = 0; j < 8; j++) {
    gl.readPixels(Math.floor((i + 0.5) * w / 12), Math.floor((j + 0.5) * h / 8), 1, 1, gl.RGBA, gl.UNSIGNED_BYTE, px);
    sum[0] += px[0]; sum[1] += px[1]; sum[2] += px[2];
  }
  return sum.map((s) => Math.round(s / 96 * 10) / 10);
}
function srCountNodes(G) { return G.nodes.length + G.kids.reduce((a, k) => a + srCountNodes(k), 0); }
function srResize(V) {
  const box = $('sr-canvas').parentElement, w = Math.max(1, box.clientWidth), h = Math.max(1, box.clientHeight);
  V.renderer.setSize(w, h, false);
  if (V.flat) { const a = w / h; Object.assign(V.camera, { left: -SR_FLAT.half * a, right: SR_FLAT.half * a, top: SR_FLAT.half, bottom: -SR_FLAT.half }); }
  else V.camera.aspect = w / h;
  V.camera.updateProjectionMatrix();
}
/* How much of the floor the page's height shows now (world units): the 3D's at its target's distance, the 2D's its frame
   over its zoom. Both cameras are moved by it (srSetSpan), so fit, zoom, focus, the box and the reach are one code. */
function srSpan(V) {
  if (V.flat) return (V.camera.top - V.camera.bottom) / V.camera.zoom;
  return 2 * V.camera.position.distanceTo(V.controls.target) * Math.tan((V.camera.fov * Math.PI / 180) / 2);
}
/* The span as the 3D's distance to its target (the 2D says the distance a 45° camera would need for its span). */
function srViewDist(V) { return V.flat ? srSpan(V) / (2 * Math.tan(SR_FLAT.fov * Math.PI / 360)) : V.camera.position.distanceTo(V.controls.target); }
/* Looks at (x, z) with `span` world units in the page's height: the 3D along its direction now, the 2D from straight above. */
function srSetSpan(V, x, z, span) {
  V.controls.target.set(x, 0, z);
  if (V.flat) {
    V.camera.position.set(x, SR_FLAT.height, z);
    V.camera.zoom = Math.min(V.controls.maxZoom, Math.max(V.controls.minZoom, (V.camera.top - V.camera.bottom) / span));
    V.camera.updateProjectionMatrix();
  } else {
    const dir = V.camera.position.clone().sub(V.controls.target).normalize();
    if (!(dir.lengthSq() > 0)) dir.set(0, 0.78, 0.62).normalize();
    V.camera.position.copy(V.controls.target).addScaledVector(dir, span / (2 * Math.tan((V.camera.fov * Math.PI / 180) / 2)));
  }
  V.camera.updateMatrixWorld();
}
/* Where the camera is, to put it back after a build (the same view only: a switch between 2D and 3D fits again). */
function srCamKeep(V) { return { pos: V.camera.position.clone(), target: V.controls.target.clone(), zoom: V.camera.zoom, flat: V.flat }; }
function srFit(instant) {
  const V = SR.view;
  if (!V) return;
  const L = V.L, cx = L.width / 2, cz = L.depth / 2, r = Math.max(6, Math.hypot(L.width, L.depth) / 2);
  if (V.flat) {   // the whole layout in the page, whichever way it is longer
    const a = (V.camera.right - V.camera.left) / (V.camera.top - V.camera.bottom);
    srSetSpan(V, cx, cz, Math.max(12, L.depth, L.width / a) * 1.08);
  } else {
    const dist = r / Math.sin((V.camera.fov * Math.PI / 180) / 2) * 0.95;
    V.controls.target.set(cx, 0, cz);
    V.camera.position.set(cx, dist * 0.78, cz + dist * 0.62);
    V.camera.near = Math.max(0.1, dist / 500); V.camera.far = dist * 6; V.camera.updateProjectionMatrix();
  }
  V.controls.update();
  void instant;
}
/* How big a node cell is on the page now (px): far below SR.lod.far, near again above SR.lod.near. */
function srCellPx(V) {
  return SR_CELL / srSpan(V) * (V.renderer.domElement.clientHeight || 1);
}
function srLod(V) {
  const px = srCellPx(V);
  if (V.flat) {
    const sparse = V.sparse ? px < SR.flatPlain.show : px < SR.flatPlain.hide;
    if (sparse !== !!V.sparse) { V.sparse = sparse; srLinesMode(V); }
  }
  const want = V.lod === 'near' ? (px < SR.lod.far ? 'far' : 'near') : (px > SR.lod.near ? 'near' : 'far');
  if (want === V.lod) return;
  V.lod = want; V.near.visible = want === 'near'; V.far.visible = want === 'far';
  V.labelAt = 0;
}
/* A tag's width on the page (px) from its text, as the tags are given out (and as 59-sr-flows.js frames the room). */
function srTagWidth(text) { return 12 + [...text].reduce((a, ch) => a + (ch.charCodeAt(0) > 0x2e7f ? 12 : 7), 0); }
/* A node's tag as srPlaceLabels writes it, and the point it stands on. */
function srTagOf(V, p) { return { text: `${p.n.label || p.n.id}${p.n.count > 1 ? ` ×${p.n.count}` : ''}`, at: [p.x, p.y + 1.9, V.flat ? p.z - 0.85 : p.z] }; }
function srPlaceLabels(V) {
  const cam = V.camera, w = V.renderer.domElement.clientWidth, h = V.renderer.domElement.clientHeight, v = new THREE.Vector3(), out = [];
  const consider = (x, y, z, text, kind, weight, n = null) => {
    v.set(x, y, z).project(cam);
    if (v.z < -1 || v.z > 1 || v.x < -1.05 || v.x > 1.05 || v.y < -1.05 || v.y > 1.05) return;
    out.push({ sx: (v.x + 1) / 2 * w, sy: (1 - v.y) / 2 * h, text, kind, n, d: cam.position.distanceToSquared(new THREE.Vector3(x, y, z)) * weight });
  };
  if (V.lod === 'far') {
    for (const G of V.L.tops) consider(G.x + G.w / 2, G.boxH + 0.8, G.z + G.d / 2, `${G.g.label || G.g.id} · ${G.nodeCount}`, 'group', 1);
  } else {
    for (const G of V.L.floors) if (G.g.id && !(V.migFloorShown && !V.migFloorShown.includes(G.g.id))) { consider(G.x + 0.15, 0.2 + G.level * 0.06, G.z + 0.5, G.g.label || G.g.id, 'group', 0.6); out[out.length - 1] && out[out.length - 1].kind === 'group' && (out[out.length - 1].left = true); }
    for (const p of V.L.pos.values()) if (!p.hiddenIn && !srMigHides(p.n.id) && !srFlowHides(p.n.id) && !(SR.reach && !SR.reach.ids.has(p.n.id))) { const t = srTagOf(V, p); consider(...t.at, t.text, p.external ? 'external' : 'node', 1, p.n); }
  }
  // up close (§5): how many nodes are in view decides the look, with room between going in and coming back
  const inView = out.filter((o) => o.n).length;
  V.inView = inView;
  const detail = V.lod === 'near' && inView > 0 && (V.detail ? inView <= SR.detail.leave : inView <= SR.detail.enter);
  if (detail !== V.detail) srSetDetail(V, detail);
  V.inViewIds = out.filter((o) => o.n).map((o) => o.n.id);
  srModelsSync(V, V.inViewIds);   // up close, the models of the nodes in view (56-sr-models.js)
  if (V.detail) for (const o of out) if (o.n) o.text = srDetailText(o.n);
  out.sort((a, b) => a.d - b.d);
  const groups = out.filter((o) => o.kind === 'group').slice(0, SR.labels.max - SR.labels.nodes);
  const rest = out.filter((o) => o.kind !== 'group').slice(0, SR.labels.nodes);
  const placed = [], clear = (o) => {   // a label that would cover one already given out is left out (its width from its text)
    const wd = srTagWidth(o.text), x0 = o.left ? o.sx : o.sx - wd / 2, b = [x0, o.sy - 20, x0 + wd, o.sy];
    if (placed.some((q) => b[0] < q[2] && b[2] > q[0] && b[1] < q[3] && b[3] > q[1])) return false;
    placed.push(b); return true;
  };
  const shown = [...groups, ...rest].filter(clear).slice(0, SR.labels.max);
  V.labels.forEach((s, i) => {
    const o = shown[i];
    if (!o) { s.hidden = true; return; }
    s.hidden = false; s.dataset.kind = o.kind; s.dataset.node = o.n ? o.n.id : '';
    if (s.textContent !== o.text) s.textContent = o.text;
    s.style.transform = `translate(${Math.round(o.sx)}px, ${Math.round(o.sy)}px) translate(${o.left ? '0' : '-50%'}, -100%)`;   // a group's tag from its floor's corner, inside it
  });
  V.shownLabels = shown.length;
}
/* The simple shapes or the ones by service (§5): shown, and the ones a press picks. */
function srSetDetail(V, on) {
  V.detail = on;
  if (V.flat) return;   // 2D: one set of flat tiles, its feet the same up close; only the tags say more (srPlaceLabels)
  V.nodeSets.simple.visible = !on; V.nodeSets.detail.visible = on;
  const drop = new Set(V.nodeMeshes[on ? 'simple' : 'detail']);
  V.pick = V.pick.filter((m) => !drop.has(m)).concat(V.nodeMeshes[on ? 'detail' : 'simple']);
  srCablesReroute(V);   // the cables end on the nodes as drawn now: the models' sides up close, the shapes' otherwise
}
/* Every cable laid again on the nodes as drawn now (srNodeFoot), the same edges in the same order: a migration's state
   is written on them again (59-sr-migration.js). */
function srCablesReroute(V) {
  const t0 = srNow();
  const plain = [], cross = [];
  for (const e of V.L.edges) (e.crossProvider ? cross : plain).push(srCablePath(V, e));
  srCablesRefill(V.plainLines, plain);
  srCablesRefill(V.crossLines, cross);
  srFocusLines(V);
  if (V.migEdges && typeof srMigApply === 'function') srMigApply(V, true);
  if (V.flowHidden && V.flowHidden.size) srFlowShowApply(V, true);   // a flow playing: its hidden nodes' cables again (59-sr-flows.js)
  V.reroutes = (V.reroutes || 0) + 1; V.rerouteMs = Math.round(srNow() - t0);   // how often and how long (the e2e reads it)
}
/* The room's icons: per node the strongest key the settings give (service → provider → category), an image plane above it. */
async function srIcons(V) {
  V.iconKeys = {};
  const icons = new Set(SR.model.icons ? Object.keys(SR.model.icons) : []);
  if (!icons.size || typeof SOURCE.infraIcon !== 'function') return;
  const byKey = {};
  for (const p of V.L.pos.values()) {
    if (p.hiddenIn) continue;
    const n = p.n, prov = n.providerResolved || n.provider;
    const key = [n.service && prov ? `service:${prov}/${n.service}` : null, prov ? `provider:${prov}` : null, `category:${n.category}`].find((k) => k && icons.has(k));
    if (key) { (byKey[key] = byKey[key] || []).push(p); V.iconKeys[n.id] = key; }
  }
  for (const [key, list] of Object.entries(byKey)) {
    const blob = await SOURCE.infraIcon(SR.project, key);
    if (!blob || SR.view !== V) continue;
    const url = URL.createObjectURL(blob);
    V.iconUrls.push(url);
    const tex = await new THREE.TextureLoader().loadAsync(url).catch(() => null);
    if (!tex || SR.view !== V) continue;
    const mesh = new THREE.InstancedMesh(new THREE.PlaneGeometry(0.9, 0.9), new THREE.MeshBasicMaterial({ map: tex, transparent: true, toneMapped: false }), list.length);
    // 2D: lying flat on the tile's corner (its name stays readable); 3D: tilted to the usual slant, over the shape
    const m4 = new THREE.Matrix4(), q = new THREE.Quaternion().setFromEuler(new THREE.Euler(V.flat ? -Math.PI / 2 : -0.5, 0, 0));
    list.forEach((p, i) => { m4.compose(V.flat ? new THREE.Vector3(p.x + 0.5, p.y + 0.8, p.z - 0.5) : new THREE.Vector3(p.x, p.y + 2.1, p.z), q, new THREE.Vector3(V.flat ? 0.55 : 1, 1, V.flat ? 0.55 : 1)); mesh.setMatrixAt(i, m4); });
    mesh.userData.icon = key; mesh.userData.nodes = list.map((p) => p.n.id);
    V.near.add(mesh);
    V.iconCount = (V.iconCount || 0) + list.length;
  }
}
function srHitAt(V, e) {
  const r = V.renderer.domElement.getBoundingClientRect(), ray = new THREE.Raycaster();
  ray.setFromCamera(new THREE.Vector2(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1), V.camera);
  const hit = ray.intersectObjects(V.pick, false)[0];
  return hit && hit.instanceId !== undefined ? { ud: hit.object.userData, i: hit.instanceId } : null;
}
function srNodeAt(V, e) {
  if (V.lod !== 'near') return null;
  const h = srHitAt(V, e);
  return h && h.ud.nodes ? h.ud.nodes[h.i] : null;
}
function srPick(e) {
  const V = SR.view;
  if (!V || V.lod !== 'near') return;
  const h = srHitAt(V, e);
  srSelect(h && h.ud.nodes ? h.ud.nodes[h.i] : null, h && h.ud.groups ? h.ud.groups[h.i] || null : null);
}
function srSelect(node, group = null) {
  if (SR.reach && node !== SR.reach.id) srReachEnd(false);   // another node chosen: the faint rest goes, the camera stays
  SR.selected = node; SR.selectedGroup = node ? null : group;
  if (SR.view) srFocusLines(SR.view);
  srRenderBoard();
}
/* The strong layer: every cable of the pressed node and of the pointed one (both ends drawn). */
function srFocusLines(V) {
  const ids = new Set([SR.selected, SR.hover].filter(Boolean)), plain = [], cross = [], reach = SR.reach ? SR.reach.edges : null;
  if (ids.size || reach) {
    for (const e of V.L.edges) {
      if ((!ids.has(e.from) && !ids.has(e.to) && !(reach && reach.has(e))) || srMigEdgeHidden(e) || srFlowEdgeHidden(e)) continue;
      (e.crossProvider ? cross : plain).push(srCablePath(V, e).map((q) => [q[0], q[1] + 0.02, q[2]]));   // a hair over its faint twin
    }
  }
  srCablesRefill(V.focusLines, plain);
  srCablesRefill(V.focusCross, cross);
  V.focusCount = plain.length + cross.length;   // a path a cable
}
/* The lines switch: all (faint) / crossing ones only / the chosen node's only. */
function srLinesMode(V) {
  V.plainLines.visible = V.farPlain.visible = SR.lines === 'all' && !V.sparse;   // 2D pulled back: the crossing ones only (srLod)
  V.crossLines.visible = V.farCross.visible = SR.lines !== 'focus';
}
/* Moves in on a node or a group (its floor's middle, near enough to see what it holds). */
function srFocus(x, z, r) {
  const V = SR.view;
  if (!V) return;
  srSetSpan(V, x, z, 2 * Math.max(6, r * 2.2) * Math.tan(SR_FLAT.fov * Math.PI / 360));
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
  srLog(tl('sr.log.toggle', { name: (G && (G.g.label || G.g.id)) || id, done: open ? tl('sr.log.opened') : tl('sr.log.closed') }));
  srBuild();
}
function srZoomBy(factor) {
  const V = SR.view;
  if (!V) return;
  if (V.flat) {
    const z = V.camera.zoom / factor;
    if (z < V.controls.minZoom || z > V.controls.maxZoom) return;
    V.camera.zoom = z; V.camera.updateProjectionMatrix();
    V.controls.update();
    return;
  }
  const d = V.camera.position.clone().sub(V.controls.target).multiplyScalar(factor);
  if (d.length() < V.controls.minDistance || d.length() > V.controls.maxDistance) return;
  V.camera.position.copy(V.controls.target).add(d);
  V.controls.update();
}
/* The box (2.3.11 item 6). Requester 10-20: 「ドラッグで範囲指定できてそこが画面全体になるようにズームするとかできる？」.
   Option (Alt) + a left drag draws it, or 範囲で寄る then one drag (a finger too). Not Shift: OrbitControls pans on
   Shift / Ctrl / ⌘ + a left drag. The stage takes the press in the capture phase, so the controls never start turning;
   a second finger, Esc or a drag under 5 px draws nothing. Let go, the camera keeps its direction and moves in until
   what the box held fills SR.boxFit of the page; 全体を見る goes back. */
function srBoxArm(on) {
  SR.box.armed = on;
  $('sr-boxzoom').setAttribute('aria-pressed', String(on));
  $('sr-canvas').parentElement.dataset.box = on ? 'armed' : '';
}
function srBoxEnd() {
  SR.box.drag = null;
  $('sr-box').hidden = true;
}
function srBoxDraw() {
  const D = SR.box.drag, el = $('sr-box');
  el.hidden = false;
  el.style.transform = `translate(${Math.min(D.x0, D.x1)}px, ${Math.min(D.y0, D.y1)}px)`;
  el.style.width = `${Math.abs(D.x1 - D.x0)}px`; el.style.height = `${Math.abs(D.y1 - D.y0)}px`;
}
/* The camera, its direction kept, on the middle of these points and as near as lets all of them fill k of the page. */
function srFrameOn(V, pts, k = SR.boxFit) {
  const c = pts.reduce((a, v) => a.add(v), new THREE.Vector3()).divideScalar(pts.length);
  if (V.flat) {   // a distance as the 3D's (srViewDist), the same search
    const tan = 2 * Math.tan(SR_FLAT.fov * Math.PI / 360), now = srViewDist(V);
    const place = (d) => srSetSpan(V, c.x, c.z, d * tan);
    const fits = (d) => { place(d); return pts.every((v) => { const q = v.clone().project(V.camera); return Math.abs(q.x) <= k && Math.abs(q.y) <= k; }); };
    let lo = V.controls.minDistance, hi = Math.max(now, lo);
    while (!fits(hi) && hi < V.controls.maxDistance) hi = Math.min(V.controls.maxDistance, hi * 2);
    if (fits(lo)) hi = lo;
    else for (let i = 0; i < 32 && hi - lo > 0.01; i++) { const m = (lo + hi) / 2; if (fits(m)) hi = m; else lo = m; }
    place(hi);
    return;
  }
  const dir = V.camera.position.clone().sub(V.controls.target).normalize(), now = V.camera.position.distanceTo(V.controls.target);
  const { minDistance: lo0, maxDistance: hi0 } = V.controls;
  const place = (d) => { V.camera.position.copy(V.controls.target).addScaledVector(dir, d); V.camera.updateMatrixWorld(); };
  V.controls.target.set(c.x, 0, c.z);
  const fits = (d) => {
    place(d);
    return pts.every((v) => { const q = v.clone().project(V.camera); return q.z > -1 && q.z < 1 && Math.abs(q.x) <= k && Math.abs(q.y) <= k; });
  };
  let lo = lo0, hi = Math.max(now, lo0);
  while (!fits(hi) && hi < hi0) hi = Math.min(hi0, hi * 2);
  if (fits(lo)) hi = lo;
  else for (let i = 0; i < 32 && hi - lo > 0.01; i++) { const m = (lo + hi) / 2; if (fits(m)) hi = m; else lo = m; }
  place(hi);
}
/* What the box can hold: near the nodes drawn, far the top groups' boxes ([id, point]). */
function srBoxPoints(V) {
  if (V.lod === 'far') return V.L.tops.map((G) => [G.g.id, new THREE.Vector3(G.x + G.w / 2, G.boxH / 2, G.z + G.d / 2)]);
  return [...V.L.pos.values()].filter((p) => !p.hiddenIn).map((p) => [p.n.id, new THREE.Vector3(p.x, p.y + 0.75, p.z)]);
}
/* A point on the page now (px within the canvas), or null behind the camera. */
function srScreenAt(V, v, w, h) {
  const q = v.clone().project(V.camera);
  return q.z < -1 || q.z > 1 ? null : [(q.x + 1) / 2 * w, (1 - q.y) / 2 * h];
}
function srZoomToBox(x0, y0, x1, y1) {
  const V = SR.view;
  if (!V) return;
  const cv = V.renderer.domElement, w = cv.clientWidth || 1, h = cv.clientHeight || 1;
  const l = Math.min(x0, x1), r = Math.max(x0, x1), t = Math.min(y0, y1), b = Math.max(y0, y1);
  V.camera.updateMatrixWorld();
  const held = srBoxPoints(V).filter(([, v]) => { const s = srScreenAt(V, v, w, h); return s && s[0] >= l && s[0] <= r && s[1] >= t && s[1] <= b; });
  const dir = V.camera.position.clone().sub(V.controls.target).normalize(), now = srViewDist(V);
  const { minDistance: lo0, maxDistance: hi0 } = V.controls;
  const place = (d) => { if (V.flat) { srSetSpan(V, V.controls.target.x, V.controls.target.z, d * 2 * Math.tan(SR_FLAT.fov * Math.PI / 360)); return; } V.camera.position.copy(V.controls.target).addScaledVector(dir, d); V.camera.updateMatrixWorld(); };
  if (held.length) srFrameOn(V, held.map(([, v]) => v));
  else {   // nothing in it: its middle on the floor, as much nearer as the box is smaller than the page
    const ray = new THREE.Raycaster(), at = new THREE.Vector3();
    ray.setFromCamera(new THREE.Vector2(((l + r) / 2 / w) * 2 - 1, -((t + b) / 2 / h) * 2 + 1), V.camera);
    if (ray.ray.intersectPlane(new THREE.Plane(new THREE.Vector3(0, 1, 0), 0), at)) V.controls.target.copy(at);
    place(Math.min(hi0, Math.max(lo0, now * Math.max((r - l) / w, (b - t) / h))));
  }
  if (!V.flat) V.camera.near = Math.max(0.1, Math.min(V.camera.near, V.camera.position.distanceTo(V.controls.target) / 500));
  V.camera.updateProjectionMatrix();
  V.controls.update();
  V.lastBox = { held: held.map(([id]) => id), lod: V.lod };
  srLog(tl('sr.box.log', { kind: V.lastBox.lod === 'far' ? 'group' : 'node', n: held.length }));
}

/* ---- つながっている物を全部見せる (requester 10-22: 「繋がってるものを全て表示のメニューが欲しい。選択したノードによるのと
   同じ感じで。」) ---- */
/* The nodes an edge joins to `id` (either way), `hops` steps on (1, or 'all': until nothing new), and the edges walked. */
function srReachOf(L, id, hops) {
  const adj = new Map();
  for (const e of L.edges) for (const [x, y] of [[e.from, e.to], [e.to, e.from]]) (adj.get(x) || adj.set(x, []).get(x)).push([y, e]);
  const ids = new Set([id]), edges = new Set();
  let front = [id];
  for (let d = 0; front.length && (hops === 'all' || d < hops); d++) {
    const next = [];
    for (const x of front) for (const [y, e] of adj.get(x) || []) { edges.add(e); if (!ids.has(y)) { ids.add(y); next.push(y); } }
    front = next;
  }
  return { ids, edges };
}
function srReachPoints(V) {
  return [...SR.reach.ids].map((id) => V.L.pos.get(id)).filter(Boolean).map((p) => new THREE.Vector3(p.x, p.y + 0.75, p.z));
}
/* Shown: what it holds, the camera on all of it. Pressed again: as it was, the camera too. */
function srReachToggle() {
  const V = SR.view;
  if (SR.reach) { srReachEnd(true); return; }
  if (!V || !SR.selected || !V.L.pos.has(SR.selected)) return;
  SR.reach = { id: SR.selected, hops: SR.reachHops, ...srReachOf(V.L, SR.selected, SR.reachHops),
    cam: { pos: V.camera.position.clone(), target: V.controls.target.clone(), zoom: V.camera.zoom } };
  srReachDraw(V);
  srFrameOn(V, srReachPoints(V), SR.reachFit);
  V.controls.update();
  srLog(tl('sr.log.reach', { node: SR.selected, n: SR.reach.ids.size - 1, hops: tl(SR.reach.hops === 'all' ? 'sr.reach.hops.all' : 'sr.reach.hops.one') }));
  srRenderBoard();
}
function srReachEnd(back) {
  const R = SR.reach, V = SR.view;
  if (!R) return;
  SR.reach = null;
  if (V) {
    srReachDraw(V);
    if (back) { V.camera.position.copy(R.cam.pos); V.controls.target.copy(R.cam.target); if (V.flat) { V.camera.zoom = R.cam.zoom; V.camera.updateProjectionMatrix(); } V.controls.update(); }
  }
  srLog(tl('sr.log.reach.end'));
  srRenderBoard();
}
/* The steps changed while shown: walked again, the camera on what it holds now (going back, still to where it was). */
function srReachHops(hops) {
  SR.reachHops = hops;
  const V = SR.view, R = SR.reach;
  if (!R || !V) return;
  Object.assign(R, { hops }, srReachOf(V.L, R.id, hops));
  srReachDraw(V);
  srFrameOn(V, srReachPoints(V), SR.reachFit);
  V.controls.update();
  srLog(tl('sr.log.reach', { node: R.id, n: R.ids.size - 1, hops: tl(hops === 'all' ? 'sr.reach.hops.all' : 'sr.reach.hops.one') }));
  srRenderBoard();
}
/* A new build (the theme, an environment, a cloud chosen): still shown when its node is still drawn, walked in the new
   layout; the camera stays where the build put it. */
function srReachAfterBuild(V) {
  const R = SR.reach;
  if (!R) return;
  if (!V.L.pos.has(R.id) || V.L.pos.get(R.id).hiddenIn) { SR.reach = null; return; }
  Object.assign(R, srReachOf(V.L, R.id, R.hops));
  srReachDraw(V);
}
/* The rest faint (the shapes, the models up close, the cables), or all as drawn again. A shape's own colour is kept the
   first time and put back from there, so what any other part of the room set (a migration's new versions) is not lost. */
function srReachDraw(V) {
  const R = SR.reach, bg = new THREE.Color(V.scene.background), c = new THREE.Color();
  for (const mesh of [...V.nodeMeshes.simple, ...V.nodeMeshes.detail]) {
    if (!mesh.instanceColor) continue;
    if (!mesh.userData.baseColors) mesh.userData.baseColors = mesh.instanceColor.array.slice();
    const base = mesh.userData.baseColors;
    mesh.userData.nodes.forEach((id, i) => {
      c.fromArray(base, i * 3);
      if (R && !R.ids.has(id)) c.lerp(bg, SR.reachFade);
      mesh.setColorAt(i, c);
    });
    mesh.instanceColor.needsUpdate = true;
    if (!R) mesh.userData.baseColors = null;
  }
  if (V.models) for (const g of V.models.values()) srReachTint(g);
  const faint = !!R;
  for (const [m, o] of [[V.plainLines, SR.plainOpacity], [V.crossLines, SR.crossOpacity], [V.farPlain, SR.plainOpacity], [V.farCross, SR.crossOpacity]]) {
    m.material.opacity = m.material.uniforms.uOpacity.value = faint ? Math.min(o, SR.reachLineOpacity) : o;
  }
  srFocusLines(V);
  srPlaceLabels(V);   // the faint ones' tags go now, not at the next tenth of a second
}
/* A model up close: faint while out of what is shown. The models share a material per colour (56-sr-models.js
   srModelMaterial), so a faint one gets a faint copy of it, made once a view, never a change to the shared one. */
function srReachTint(g) {
  const V = SR.view, out = !!SR.reach && !SR.reach.ids.has(g.userData.node);
  if (!V) return;
  V.reachMats = V.reachMats || new Map();
  g.traverse((o) => {
    if (!o.isMesh) return;
    const base = o.userData.reachBase || (o.userData.reachBase = o.material);
    if (out && !V.reachMats.has(base)) {
      const f = base.clone();
      f.transparent = true; f.opacity = base.opacity * (1 - SR.reachFade); f.depthWrite = false;
      V.reachMats.set(base, f);
    }
    o.material = out ? V.reachMats.get(base) : base;
  });
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
  const laid = SR.selected && SR.view && SR.view.L.pos.get(SR.selected);   // a migration step may have put a new version there
  const sel = SR.selected ? (laid && laid.n) || (M.nodes || []).find((n) => n.id === SR.selected) : null;
  const grp = !sel && SR.selectedGroup ? (M.groups || []).find((g) => g.id === SR.selectedGroup) : null;
  const inGroup = grp && SR.view ? SR.view.L.floors.find((F) => F.g.id === grp.id) : null;
  const edgesOf = sel ? (M.edges || []).filter((e) => e.from === sel.id || e.to === sel.id).slice(0, 20) : [];
  const probs = (M.problems || []).slice(0, 50);
  setHTML($('sr-board'), `<h3>${esc(tl('sr.board.title'))}</h3>
<p class="sr-meta">${esc(M.dir || '')} · ${esc(tl('sr.board.files', { n: (M.files || []).length }))}</p>
<dl class="sr-counts"><dt>node</dt><dd data-sr-count="nodes">${esc(String(S.nodes ?? 0))}</dd><dt>edge</dt><dd data-sr-count="edges">${esc(String(S.edges ?? 0))}</dd><dt>${esc(tl('sr.board.cross'))}</dt><dd data-sr-count="cross">${esc(String(S.cross ?? 0))}</dd><dt>${esc(tl('sr.board.folded'))}</dt><dd>${esc(String(S.folded ?? 0))}${$('sr-fold').checked ? esc(tl('sr.board.folded.shown')) : ''}</dd><dt>${esc(tl('sr.board.external'))}</dt><dd>${esc(String(S.external ?? 0))}</dd></dl>
<h3>${esc(tl('sr.board.legend'))}</h3><p class="sr-hint">${esc(tl('sr.board.legend.hint'))}${SR.only.size ? ` ${esc(tl('sr.only', { clouds: [...SR.only].join(', ') }))}` : ''}</p>
<ul class="sr-legend">${provs.map((p) => `<li><button type="button" class="sr-prov" data-sr-prov="${esc(p)}" aria-pressed="${SR.only.has(p) ? 'true' : 'false'}"><span class="sr-chip" style="background:${esc(srProviderColor(p))}"></span>${esc(p)}</button></li>`).join('')}
<li><button type="button" class="sr-prov" data-sr-prov="" aria-pressed="${SR.only.size ? 'false' : 'true'}">${esc(tl('sr.board.all'))}</button></li>
<li><span class="sr-line"></span>${esc(tl('sr.board.line.same'))}</li><li><span class="sr-line sr-line-cross"></span>${esc(tl('sr.board.line.cross'))}</li></ul>
${sel ? `<h3 data-sr-sel-head>${esc(tl('sr.sel.title'))}</h3><dl class="sr-sel"><dt>id</dt><dd>${esc(sel.id)}</dd><dt>${esc(tl('sr.sel.name'))}</dt><dd>${esc(sel.label || '')}</dd><dt>${esc(tl('sr.sel.kind'))}</dt><dd>${esc(sel.category)}</dd><dt>provider</dt><dd>${esc(sel.providerResolved || sel.provider || '')}${sel.service ? ` · ${esc(sel.service)}` : ''}</dd>${sel.count > 1 ? `<dt>${esc(tl('sr.sel.count'))}</dt><dd>${esc(String(sel.count))}</dd>` : ''}${sel.engine ? `<dt>${esc(tl('sr.sel.engine'))}</dt><dd>${esc(sel.engine)}</dd>` : ''}</dl>${srFlowBoardHTML(sel.id)}
${Array.isArray(sel.spec) && sel.spec.length ? `<h3>${esc(tl('sr.sel.spec'))}</h3><table class="sr-spec" data-sr-spec><tbody>${sel.spec.map((x) => `<tr><th scope="row">${SR_SPEC_NAME[x.key] ? `${esc(SR_SPEC_NAME[x.key])} <small>${esc(x.key)}</small>` : esc(x.key)}</th><td>${esc(x.value)}</td></tr>`).join('')}</tbody></table>` : ''}
<p class="sr-acts"><button type="button" class="wb-btn" data-sr-act="focus">${esc(tl('sr.act.focus'))}</button> <button type="button" class="wb-btn sr-reach" data-sr-act="reach" aria-pressed="${SR.reach ? 'true' : 'false'}">${esc(tl('sr.act.reach'))}</button> <select class="sr-reach-hops" data-sr-reach-hops aria-label="${esc(tl('sr.reach.hops'))}"><option value="1"${SR.reachHops === 1 ? ' selected' : ''}>${esc(tl('sr.reach.hops.one'))}</option><option value="all"${SR.reachHops === 'all' ? ' selected' : ''}>${esc(tl('sr.reach.hops.all'))}</option></select></p>
${SR.reach ? `<p class="sr-hint" data-sr-reach-said>${esc(tl('sr.reach.shown', { n: SR.reach.ids.size - 1 }))}</p>` : ''}
<ul class="sr-edges">${edgesOf.map((e) => `<li>${esc(e.from)} → ${esc(e.to)}${e.protocol ? ` <small>${esc(e.protocol)}</small>` : ''}${e.crossProvider ? ` <b>${esc(tl('sr.edge.cross'))}</b>` : ''}</li>`).join('')}</ul>`
    : grp ? `<h3>${esc(tl('sr.grp.title'))}</h3><dl class="sr-sel"><dt>id</dt><dd>${esc(grp.id)}</dd><dt>${esc(tl('sr.sel.name'))}</dt><dd>${esc(grp.label || '')}</dd><dt>${esc(tl('sr.sel.kind'))}</dt><dd>${esc(grp.kind || '')}</dd><dt>provider</dt><dd>${esc(grp.providerResolved || grp.provider || '')}</dd><dt>${esc(tl('sr.grp.nodes'))}</dt><dd>${esc(String(inGroup ? srCountNodes(inGroup) : 0))}</dd></dl>
<p class="sr-acts"><button type="button" class="wb-btn" data-sr-act="focus">${esc(tl('sr.act.focus'))}</button> <button type="button" class="wb-btn" data-sr-act="toggle" data-sr-group="${esc(grp.id)}">${esc(SR.closed.has(grp.id) ? tl('sr.grp.open') : tl('sr.grp.close'))}</button></p>`
    : `<p class="sr-hint">${esc(tl('sr.board.hint'))}</p>`}
${srMigBoardHTML()}
${probs.length ? `<h3>${esc(tl('sr.board.problems', { n: probs.length }))}</h3><ul class="sr-problems">${probs.map((p) => `<li title="${esc(p.message || '')}">${esc(p.short || p.message || '')}</li>`).join('')}</ul>` : ''}`);
  // a node newly chosen: the board turns to its rows (and the flows it starts, under them), not left where it was scrolled
  const head = $('sr-board').querySelector('[data-sr-sel-head]');
  if (head && SR.boardSel !== SR.selected) { const B = $('sr-board'); B.scrollTop += head.getBoundingClientRect().top - B.getBoundingClientRect().top - 6; }
  SR.boardSel = SR.selected;
}
function srRenderLog() {
  setHTML($('sr-log'), `<ol>${SR.log.map((l) => `<li><time>${esc(new Date(l.at).toTimeString().slice(0, 8))}</time> ${esc(l.text)}</li>`).join('')}</ol>`);
}
/* The theme changing while the server room is open (the OS's light and dark, or the page's own switch; the independent verification
   D3): the 3D is made again in the new colours, the camera where it was. */
function srRetheme() {
  const V = SR.view;
  if (SR.phase !== 'open' || !V || V.dark === isDark()) return;
  srBuild(srCamKeep(V));
  const W = SR.view;
  srLog(tl('sr.log.theme', { theme: W.dark ? tl('sr.theme.dark') : tl('sr.theme.light') }));
}
if (window.matchMedia) window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', srRetheme);
new MutationObserver(srRetheme).observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
$('sr-back').addEventListener('click', srClose);
$('sr-fit').addEventListener('click', () => srFit(false));
$('sr-boxzoom').addEventListener('click', () => { srBoxEnd(); srBoxArm(!SR.box.armed); });
{
  const stage = $('sr-canvas').parentElement;
  const local = (e) => { const r = stage.getBoundingClientRect(); return [e.clientX - r.left, e.clientY - r.top]; };
  stage.addEventListener('pointerdown', (e) => {   // capture: before OrbitControls on the canvas
    if (SR.phase !== 'open' || !SR.view || SR.paused) return;   // コスト is drawn on the stage: its presses are its own
    if (SR.box.drag) { e.stopPropagation(); e.preventDefault(); srBoxEnd(); return; }   // a second finger: no box
    if (e.button !== 0 || !(e.altKey || SR.box.armed)) return;
    e.stopPropagation(); e.preventDefault();
    const [x, y] = local(e);
    SR.box.drag = { id: e.pointerId, x0: x, y0: y, x1: x, y1: y };
    try { stage.setPointerCapture(e.pointerId); } catch { /* a pointer already gone */ }
  }, true);
  stage.addEventListener('pointermove', (e) => {
    const D = SR.box.drag;
    if (!D || e.pointerId !== D.id) return;
    e.stopPropagation();
    [D.x1, D.y1] = local(e);
    srBoxDraw();
  }, true);
  const up = (e) => {
    const D = SR.box.drag;
    if (!D || e.pointerId !== D.id) return;
    e.stopPropagation();
    srBoxEnd();
    srBoxArm(false);
    if (e.type === 'pointerup' && Math.abs(D.x1 - D.x0) >= 5 && Math.abs(D.y1 - D.y0) >= 5) srZoomToBox(D.x0, D.y0, D.x1, D.y1);
  };
  stage.addEventListener('pointerup', up, true);
  stage.addEventListener('pointercancel', up, true);
}
$('sr-zin').addEventListener('click', () => srZoomBy(1 / SR.zoomStep));
$('sr-lines').addEventListener('change', () => {
  SR.lines = $('sr-lines').value;
  srLog(tl('sr.log.lines', { lines: $('sr-lines').selectedOptions[0].textContent }));
  if (SR.view) srLinesMode(SR.view);
});
$('sr-zout').addEventListener('click', () => srZoomBy(SR.zoomStep));
$('sr-board').addEventListener('click', (e) => {
  const pv = e.target.closest('[data-sr-prov]');
  if (pv) {   // a cloud on the legend: toggled; 全部 clears the choice
    const p = pv.dataset.srProv;
    if (!p) SR.only = new Set(); else if (SR.only.has(p)) SR.only.delete(p); else SR.only.add(p);
    srLog(SR.only.size ? tl('sr.only', { clouds: [...SR.only].join(', ') }) : tl('sr.only.all'));
    srBuild();
    return;
  }
  const mg = e.target.closest('[data-sr-mig]');
  if (mg) { srMigStart(mg.dataset.srMig); return; }   // 59-sr-migration.js
  const fl = e.target.closest('[data-sr-flow]');
  if (fl) { srFlowPlay(fl.dataset.srFlow); return; }   // 59-sr-flows.js
  const b = e.target.closest('[data-sr-act]');
  if (!b) return;
  if (b.dataset.srAct === 'focus') srFocusSelected();
  else if (b.dataset.srAct === 'reach') srReachToggle();
  else if (b.dataset.srAct === 'toggle') srToggleGroup(b.dataset.srGroup);
});
$('sr-board').addEventListener('change', (e) => {
  const h = e.target.closest('[data-sr-reach-hops]');
  if (h) srReachHops(h.value === 'all' ? 'all' : 1);
});
$('sr-env').addEventListener('change', () => { srLog(tl('sr.log.env', { env: $('sr-env').value || tl('sr.env.unset') })); srBuild(); });
$('sr-fold').addEventListener('change', () => { srLog($('sr-fold').checked ? tl('sr.log.fold.shown') : tl('sr.log.fold.folded')); srBuild(); });
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
  if (SR.phase === 'open' && (SR.box.drag || SR.box.armed)) { e.preventDefault(); e.stopPropagation(); srBoxEnd(); srBoxArm(false); return; }   // the box only, the room stays
  if (SR.phase === 'open' && SR.reach) { e.preventDefault(); e.stopPropagation(); srReachEnd(true); return; }   // what was shown only, the room stays
  if (SR.phase === 'loading') { e.preventDefault(); e.stopPropagation(); srCancel(); return; }
  if (SR.phase === 'open') { e.preventDefault(); e.stopPropagation(); srClose(); }
}, true);
