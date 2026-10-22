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
   - up close (ticket 2026-10-20-jui-viz-server-room-lines-dark-filter-spec §5, requester: 「ある程度拡大して表示されてる
     ノードが少なくなった時はどれが何のインスタンスかわかる程度に違いが欲しい」): near, with SR.detail.enter nodes or fewer
     in view, a second set of shapes by service (a function a slim pillar, a container a crate, a key-value store a
     tapered drum, a notification a pyramid...: srDetailShape) and tags of name · service · its main spec; back to
     the simple ones past SR.detail.leave (between the two it stays as it was). There, each node in view stands as a model of what
     it does (56-sr-models.js); the shapes by service under it still take the press.
   - a node's spec (§4): the board's 選んだもの lists it, the keys the IaC tables know with a name in words.
   Measured for the ticket: the first draw, the frame time far and near, the memory (SR.stats). */
const SR = {
  phase: 'idle', project: null, seq: 0, t0: 0, until: 0, why: '', full: '', opener: null, model: null, view: null, log: [],
  fastMs: 300, starMs: 140, okMs: 700, failMs: 9000,
  lod: { far: 9, near: 13 }, labels: { max: 110, nodes: 80 }, stats: null, detail: { enter: 30, leave: 40 },
  closed: new Set(), selected: null, selectedGroup: null, boardSel: null, zoomStep: 1.4,
  // fewer lines (2.3.9, requester 10-20: 「線減らす工夫欲しいね」): all cables faint, the pressed and the pointed node's
  // drawn strong on a layer of their own; a switch for all (faint) / crossing ones only / the chosen node's only
  lines: 'all', hover: null, plainOpacity: 0.18, crossOpacity: 0.55,
  only: new Set(),   // the clouds chosen on the board's legend (2.3.9, item 3; empty: all)
  // a box drawn to move in on (2.3.11 item 6): Option + drag, or 範囲で寄る then one drag; fit is how much of the page it fills
  box: { armed: false, drag: null }, boxFit: 0.92,
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
const srShapeIn = (set, n) => (set === 'detail' ? srDetailShape(n) : srShape(n.category));
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
  SR.model = model;
  showOverlay(srEl);
  setText($('sr-room'), (PROJECT[SR.project] && PROJECT[SR.project].name) || '');
  const envs = srEnvs(model);
  $('sr-env').innerHTML = envs.length ? envs.map((e) => `<option value="${esc(e.id)}">${esc(e.label)}</option>`).join('') : `<option value="">${esc(tl('sr.env.none'))}</option>`;
  $('sr-env').disabled = envs.length < 2;
  $('sr-fold').checked = false;
  SR.closed = new Set(); SR.selected = null; SR.selectedGroup = null; SR.hover = null; SR.only = new Set();
  $('sr-lines').value = SR.lines;
  srBuild();
  $('sr-back').focus({ preventScroll: true });
}
function srClose() {
  if (SR.phase !== 'open') return;
  SR.phase = 'idle';
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
  const L = srLayout(model, env, fold, SR.closed, SR.only);
  // a chosen or pointed node not drawn now (another environment, a cloud not chosen, folded) is let go (the independent verification)
  for (const k of ['selected', 'hover']) if (SR[k] && !(L.pos.has(SR[k]) && !L.pos.get(SR[k]).hiddenIn)) SR[k] = null;
  const cv = $('sr-canvas'), box = cv.parentElement;
  const renderer = new THREE.WebGLRenderer({ canvas: cv, antialias: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  const scene = new THREE.Scene();
  const dark = isDark(), PAL = dark ? SR_PAL.dark : SR_PAL.light;
  scene.background = new THREE.Color(PAL.bg);
  scene.add(new THREE.HemisphereLight(0xffffff, 0x445566, 1.6));
  const sun = new THREE.DirectionalLight(0xffffff, 1.2); sun.position.set(30, 60, 40); scene.add(sun);
  const camera = new THREE.PerspectiveCamera(45, 1, 0.1, 5000);
  const controls = new OrbitControls(camera, cv);
  Object.assign(controls, { enableDamping: !reduceMotion, dampingFactor: 0.12, screenSpacePanning: true, minDistance: 3, maxDistance: 4000, maxPolarAngle: Math.PI * 0.48 });
  const V = { renderer, scene, camera, controls, L, near: new THREE.Group(), far: new THREE.Group(), lod: 'near', pick: [], iconUrls: [], raf: 0,
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
  V.near.add(floorMesh); V.pick.push(floorMesh);
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
  for (const set of ['simple', 'detail']) {
    const byShape = {};
    for (const p of L.pos.values()) if (!p.hiddenIn) (byShape[srShapeIn(set, p.n)] = byShape[srShapeIn(set, p.n)] || []).push(p);
    for (const [shape, list] of Object.entries(byShape)) {
      const mesh = new THREE.InstancedMesh(SR_SHAPES[shape](), new THREE.MeshLambertMaterial({ color: 0xffffff }), list.length);
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
    const a = L.pos.get(e.from), b = L.pos.get(e.to), crossing = !!e.crossProvider, y = crossing ? 2.6 : 1.7;
    (crossing ? cross : plain).push(a.x, y, a.z, b.x, y, b.z);
  }
  const lines = (arr, mat) => { const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.Float32BufferAttribute(arr, 3)); const l = new THREE.LineSegments(g, mat); if (mat.isLineDashedMaterial) l.computeLineDistances(); return l; };
  V.plainLines = lines(plain, new THREE.LineBasicMaterial({ color: PAL.plain, transparent: true, opacity: SR.plainOpacity }));
  V.crossLines = lines(cross, new THREE.LineDashedMaterial({ color: PAL.cross, dashSize: 0.5, gapSize: 0.3, transparent: true, opacity: SR.crossOpacity }));
  // the strong layer: the pressed and the pointed node's cables (srFocusLines fills it)
  V.focusLines = new THREE.LineSegments(new THREE.BufferGeometry(), new THREE.LineBasicMaterial({ color: PAL.focus }));
  V.focusCross = new THREE.LineSegments(new THREE.BufferGeometry(), new THREE.LineBasicMaterial({ color: PAL.cross }));
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
    const ya = B.a.boxH + 0.3, yb = B.b.boxH + 0.3;
    (B.cross ? bc : bp).push(B.a.x + B.a.w / 2, ya, B.a.z + B.a.d / 2, B.b.x + B.b.w / 2, yb, B.b.z + B.b.d / 2);
  }
  V.bundles = [...bundles.values()];
  // the far view's bundles: as faint as the near cables, and the lines switch holds there too (the independent verification of item 1)
  V.farPlain = lines(bp, new THREE.LineBasicMaterial({ color: PAL.plain, transparent: true, opacity: SR.plainOpacity }));
  V.farCross = lines(bc, new THREE.LineDashedMaterial({ color: PAL.cross, dashSize: 1.2, gapSize: 0.7, transparent: true, opacity: SR.crossOpacity }));
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
  srFlowBuild(V);          // 59-sr-flows.js: the cones over the nodes that start a flow
  const loop = () => {   // the cost view over the stage pauses it (SR.paused, 56-server-cost.js): no frame drawn meanwhile
    if (SR.paused) { V.raf = 0; return; }
    V.raf = requestAnimationFrame(loop);
    const t = srNow();
    const dt = V.last ? Math.min(t - V.last, 100) : 16;
    if (V.last) { V.frames.push(t - V.last); if (V.frames.length > 240) V.frames.shift(); }
    V.last = t;
    controls.update();
    srLod(V);
    srFlowTick(V, dt);
    if (t - V.labelAt > 100) { V.labelAt = t; srPlaceLabels(V); }
    renderer.render(scene, camera);
  };
  V.loop = loop;
  loop();
  SR.stats = { firstMs: Math.round(srNow() - t0), nodes: L.nodes.length, edges: L.edges.length, floors: L.floors.length };
  srLog(tl('sr.log.drawn', { nodes: L.nodes.length, edges: L.edges.length, floors: L.floors.length, ms: SR.stats.firstMs })
    + (env ? tl('sr.log.drawn.env', { env }) : ''));
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
  const consider = (x, y, z, text, kind, weight, n = null) => {
    v.set(x, y, z).project(cam);
    if (v.z < -1 || v.z > 1 || v.x < -1.05 || v.x > 1.05 || v.y < -1.05 || v.y > 1.05) return;
    out.push({ sx: (v.x + 1) / 2 * w, sy: (1 - v.y) / 2 * h, text, kind, n, d: cam.position.distanceToSquared(new THREE.Vector3(x, y, z)) * weight });
  };
  if (V.lod === 'far') {
    for (const G of V.L.tops) consider(G.x + G.w / 2, G.boxH + 0.8, G.z + G.d / 2, `${G.g.label || G.g.id} · ${G.nodeCount}`, 'group', 1);
  } else {
    for (const G of V.L.floors) if (G.g.id) consider(G.x + 0.6, 0.2 + G.level * 0.06, G.z + 0.5, G.g.label || G.g.id, 'group', 0.6);
    for (const p of V.L.pos.values()) if (!p.hiddenIn) consider(p.x, p.y + 1.9, p.z, `${p.n.label || p.n.id}${p.n.count > 1 ? ` ×${p.n.count}` : ''}`, p.external ? 'external' : 'node', 1, p.n);
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
/* The simple shapes or the ones by service (§5): shown, and the ones a press picks. */
function srSetDetail(V, on) {
  V.detail = on;
  V.nodeSets.simple.visible = !on; V.nodeSets.detail.visible = on;
  const drop = new Set(V.nodeMeshes[on ? 'simple' : 'detail']);
  V.pick = V.pick.filter((m) => !drop.has(m)).concat(V.nodeMeshes[on ? 'detail' : 'simple']);
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
    const m4 = new THREE.Matrix4(), q = new THREE.Quaternion().setFromEuler(new THREE.Euler(-0.5, 0, 0));
    list.forEach((p, i) => { m4.compose(new THREE.Vector3(p.x, p.y + 2.1, p.z), q, new THREE.Vector3(1, 1, 1)); mesh.setMatrixAt(i, m4); });
    mesh.userData.icon = key;
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
  SR.selected = node; SR.selectedGroup = node ? null : group;
  if (SR.view) srFocusLines(SR.view);
  srRenderBoard();
}
/* The strong layer: every cable of the pressed node and of the pointed one (both ends drawn). */
function srFocusLines(V) {
  const ids = new Set([SR.selected, SR.hover].filter(Boolean)), plain = [], cross = [];
  if (ids.size) {
    for (const e of V.L.edges) {
      if (!ids.has(e.from) && !ids.has(e.to)) continue;
      const a = V.L.pos.get(e.from), b = V.L.pos.get(e.to), y = e.crossProvider ? 2.62 : 1.72;
      (e.crossProvider ? cross : plain).push(a.x, y, a.z, b.x, y, b.z);
    }
  }
  for (const [layer, arr] of [[V.focusLines, plain], [V.focusCross, cross]]) {
    layer.geometry.dispose();
    layer.geometry = new THREE.BufferGeometry();
    layer.geometry.setAttribute('position', new THREE.Float32BufferAttribute(arr, 3));
  }
  V.focusCount = (plain.length + cross.length) / 6;
}
/* The lines switch: all (faint) / crossing ones only / the chosen node's only. */
function srLinesMode(V) {
  V.plainLines.visible = V.farPlain.visible = SR.lines === 'all';
  V.crossLines.visible = V.farCross.visible = SR.lines !== 'focus';
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
  srLog(tl('sr.log.toggle', { name: (G && (G.g.label || G.g.id)) || id, done: open ? tl('sr.log.opened') : tl('sr.log.closed') }));
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
  const dir = V.camera.position.clone().sub(V.controls.target).normalize(), now = V.camera.position.distanceTo(V.controls.target);
  const { minDistance: lo0, maxDistance: hi0 } = V.controls;
  const place = (d) => { V.camera.position.copy(V.controls.target).addScaledVector(dir, d); V.camera.updateMatrixWorld(); };
  if (held.length) {
    const c = held.reduce((a, [, v]) => a.add(v), new THREE.Vector3()).divideScalar(held.length);
    V.controls.target.set(c.x, 0, c.z);
    const k = SR.boxFit;
    const fits = (d) => {
      place(d);
      return held.every(([, v]) => { const q = v.clone().project(V.camera); return q.z > -1 && q.z < 1 && Math.abs(q.x) <= k && Math.abs(q.y) <= k; });
    };
    let lo = lo0, hi = Math.max(now, lo0);
    while (!fits(hi) && hi < hi0) hi = Math.min(hi0, hi * 2);
    if (fits(lo)) hi = lo;
    else for (let i = 0; i < 32 && hi - lo > 0.01; i++) { const m = (lo + hi) / 2; if (fits(m)) hi = m; else lo = m; }
    place(hi);
  } else {   // nothing in it: its middle on the floor, as much nearer as the box is smaller than the page
    const ray = new THREE.Raycaster(), at = new THREE.Vector3();
    ray.setFromCamera(new THREE.Vector2(((l + r) / 2 / w) * 2 - 1, -((t + b) / 2 / h) * 2 + 1), V.camera);
    if (ray.ray.intersectPlane(new THREE.Plane(new THREE.Vector3(0, 1, 0), 0), at)) V.controls.target.copy(at);
    place(Math.min(hi0, Math.max(lo0, now * Math.max((r - l) / w, (b - t) / h))));
  }
  V.camera.near = Math.max(0.1, Math.min(V.camera.near, V.camera.position.distanceTo(V.controls.target) / 500));
  V.camera.updateProjectionMatrix();
  V.controls.update();
  V.lastBox = { held: held.map(([id]) => id), lod: V.lod };
  srLog(tl('sr.box.log', { kind: V.lastBox.lod === 'far' ? 'group' : 'node', n: held.length }));
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
  setHTML($('sr-board'), `<h3>${esc(tl('sr.board.title'))}</h3>
<p class="sr-meta">${esc(M.dir || '')} · ${esc(tl('sr.board.files', { n: (M.files || []).length }))}</p>
<dl class="sr-counts"><dt>node</dt><dd data-sr-count="nodes">${esc(String(S.nodes ?? 0))}</dd><dt>edge</dt><dd data-sr-count="edges">${esc(String(S.edges ?? 0))}</dd><dt>${esc(tl('sr.board.cross'))}</dt><dd data-sr-count="cross">${esc(String(S.cross ?? 0))}</dd><dt>${esc(tl('sr.board.folded'))}</dt><dd>${esc(String(S.folded ?? 0))}${$('sr-fold').checked ? esc(tl('sr.board.folded.shown')) : ''}</dd><dt>${esc(tl('sr.board.external'))}</dt><dd>${esc(String(S.external ?? 0))}</dd></dl>
<h3>${esc(tl('sr.board.legend'))}</h3><p class="sr-hint">${esc(tl('sr.board.legend.hint'))}${SR.only.size ? ` ${esc(tl('sr.only', { clouds: [...SR.only].join(', ') }))}` : ''}</p>
<ul class="sr-legend">${provs.map((p) => `<li><button type="button" class="sr-prov" data-sr-prov="${esc(p)}" aria-pressed="${SR.only.has(p) ? 'true' : 'false'}"><span class="sr-chip" style="background:${esc(srProviderColor(p))}"></span>${esc(p)}</button></li>`).join('')}
<li><button type="button" class="sr-prov" data-sr-prov="" aria-pressed="${SR.only.size ? 'false' : 'true'}">${esc(tl('sr.board.all'))}</button></li>
<li><span class="sr-line"></span>${esc(tl('sr.board.line.same'))}</li><li><span class="sr-line sr-line-cross"></span>${esc(tl('sr.board.line.cross'))}</li></ul>
${sel ? `<h3 data-sr-sel-head>${esc(tl('sr.sel.title'))}</h3><dl class="sr-sel"><dt>id</dt><dd>${esc(sel.id)}</dd><dt>${esc(tl('sr.sel.name'))}</dt><dd>${esc(sel.label || '')}</dd><dt>${esc(tl('sr.sel.kind'))}</dt><dd>${esc(sel.category)}</dd><dt>provider</dt><dd>${esc(sel.providerResolved || sel.provider || '')}${sel.service ? ` · ${esc(sel.service)}` : ''}</dd>${sel.count > 1 ? `<dt>${esc(tl('sr.sel.count'))}</dt><dd>${esc(String(sel.count))}</dd>` : ''}${sel.engine ? `<dt>${esc(tl('sr.sel.engine'))}</dt><dd>${esc(sel.engine)}</dd>` : ''}</dl>${srFlowBoardHTML(sel.id)}
${Array.isArray(sel.spec) && sel.spec.length ? `<h3>${esc(tl('sr.sel.spec'))}</h3><table class="sr-spec" data-sr-spec><tbody>${sel.spec.map((x) => `<tr><th scope="row">${SR_SPEC_NAME[x.key] ? `${esc(SR_SPEC_NAME[x.key])} <small>${esc(x.key)}</small>` : esc(x.key)}</th><td>${esc(x.value)}</td></tr>`).join('')}</tbody></table>` : ''}
<p class="sr-acts"><button type="button" class="wb-btn" data-sr-act="focus">${esc(tl('sr.act.focus'))}</button></p>
<ul class="sr-edges">${edgesOf.map((e) => `<li>${esc(e.from)} → ${esc(e.to)}${e.protocol ? ` <small>${esc(e.protocol)}</small>` : ''}${e.crossProvider ? ` <b>${esc(tl('sr.edge.cross'))}</b>` : ''}</li>`).join('')}</ul>`
    : grp ? `<h3>${esc(tl('sr.grp.title'))}</h3><dl class="sr-sel"><dt>id</dt><dd>${esc(grp.id)}</dd><dt>${esc(tl('sr.sel.name'))}</dt><dd>${esc(grp.label || '')}</dd><dt>${esc(tl('sr.sel.kind'))}</dt><dd>${esc(grp.kind || '')}</dd><dt>provider</dt><dd>${esc(grp.providerResolved || grp.provider || '')}</dd><dt>${esc(tl('sr.grp.nodes'))}</dt><dd>${esc(String(inGroup ? srCountNodes(inGroup) : 0))}</dd></dl>
<p class="sr-acts"><button type="button" class="wb-btn" data-sr-act="focus">${esc(tl('sr.act.focus'))}</button> <button type="button" class="wb-btn" data-sr-act="toggle" data-sr-group="${esc(grp.id)}">${esc(SR.closed.has(grp.id) ? tl('sr.grp.open') : tl('sr.grp.close'))}</button></p>`
    : `<p class="sr-hint">${esc(tl('sr.board.hint'))}</p>`}
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
  const pos = V.camera.position.clone(), target = V.controls.target.clone();
  srBuild();
  const W = SR.view;
  W.camera.position.copy(pos); W.controls.target.copy(target); W.controls.update();
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
  const fl = e.target.closest('[data-sr-flow]');
  if (fl) { srFlowPlay(fl.dataset.srFlow); return; }   // 59-sr-flows.js
  const b = e.target.closest('[data-sr-act]');
  if (!b) return;
  if (b.dataset.srAct === 'focus') srFocusSelected();
  else if (b.dataset.srAct === 'toggle') srToggleGroup(b.dataset.srGroup);
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
  if (SR.phase === 'loading') { e.preventDefault(); e.stopPropagation(); srCancel(); return; }
  if (SR.phase === 'open') { e.preventDefault(); e.stopPropagation(); srClose(); }
}, true);
