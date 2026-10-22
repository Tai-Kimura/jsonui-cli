/* ---------- the server room's nodes up close, as models that say what they do ----------
   Requester 10-22: 「これ拡大した時だけもっと複雑なオブジェクトにできない？どんな機能のノードかわかりやすいように / 引きになったら
   負荷が大きいので今の表示で」 (ticket 2026-10-22-viz-server-room-palette-and-light-flow §3).
   Only up close: when the room shows its shapes by service (srPlaceLabels' detail, SR.detail.enter nodes in view or
   fewer, back past SR.detail.leave), each node in view gets a model of its kind (SR_MODEL_KIND), built then and only
   for those, at most SR_MODEL.max at a time (the ones out of view go first). Far away, and whenever the room shows its
   simple shapes, there is none: the instanced shapes alone are drawn, as before. The shapes by service stay what a
   press picks (their drawing is switched off while the models stand on them); the colour is the node's cloud's, the
   tags, the ring on arrival and the flow's light are where they were. */
const SR_MODEL = { max: 64 };
/* category (and a service where one category holds two looks) → the model */
function srModelKind(n) {
  const c = String(n.category || ''), s = String(n.service || '');
  if (c.startsWith('database.')) return 'db';
  if (c === 'cache') return 'cache';
  if (c === 'storage.object') return 'bucket';
  if (c === 'storage.block' || c === 'storage.file') return 'drive';
  if (c === 'queue' && /^(sns|eventgrid|notification|pubsub)/.test(s)) return 'broadcast';
  if (c === 'queue') return 'queue';
  if (c === 'stream') return 'stream';
  if (c === 'load_balancer') return 'splitter';
  if (c === 'edge.cdn') return 'globe';
  if (c === 'edge.dns') return 'signpost';
  if (c === 'edge.waf') return 'shield';
  if (c.startsWith('gateway.')) return 'arch';
  if (c === 'compute.function') return 'bolt';
  if (c === 'compute.vm') return 'server';
  if (c === 'compute.container' || c === 'compute.paas') return 'container';
  if (c === 'compute.k8s') return 'wheel';
  if (c === 'client') return 'browser';
  if (c === 'auth') return 'padlock';
  if (c === 'secrets') return 'key';
  if (c === 'scheduler') return 'clock';
  if (c === 'mail') return 'envelope';
  if (c.startsWith('monitoring')) return 'gauge';
  if (c === 'external.saas') return 'cloud';
  return 'plinth';
}

/* Each model is parts (made once, when first wanted): [geometry, x, y, z, tone, rotation] — tone 0 the cloud's colour, 1 a deeper one, 2 a lighter one;
   y from the node's middle (the instanced shape's), the whole about as big as the simple shape. */
let srModelPartsMade = null;
function srModelParts() {
  if (srModelPartsMade) return srModelPartsMade;
  const T = THREE;
  const cyl = (r, h, n = 20, r2 = r) => new T.CylinderGeometry(r, r2, h, n);
  const box = (w, h, d) => new T.BoxGeometry(w, h, d);
  const bolt = () => {
    const s = new T.Shape([[0.1, 0.75], [-0.32, 0.02], [-0.02, 0.02], [-0.14, -0.75], [0.32, 0.08], [0.02, 0.08]].map(([x, y]) => new T.Vector2(x, y)));
    const g = new T.ExtrudeGeometry(s, { depth: 0.3, bevelEnabled: true, bevelSize: 0.03, bevelThickness: 0.03, bevelSegments: 1 });
    g.translate(0, 0, -0.15); g.rotateY(-0.7); return g;   // turned toward the room's usual view, so it is not seen edge on
  };
  const parts = {
    db: [[cyl(0.55, 0.28), 0, -0.45, 0, 0], [cyl(0.56, 0.05), 0, -0.29, 0, 1], [cyl(0.55, 0.28), 0, -0.12, 0, 0], [cyl(0.56, 0.05), 0, 0.04, 0, 1],
      [cyl(0.55, 0.28), 0, 0.21, 0, 0], [cyl(0.5, 0.04), 0, 0.37, 0, 2]],
    cache: [[box(1.0, 0.18, 0.8), 0, -0.2, 0, 1], [box(0.62, 0.14, 0.5), 0, -0.04, 0, 0],
      ...[-0.36, -0.12, 0.12, 0.36].flatMap((x) => [[box(0.08, 0.06, 0.16), x, -0.2, 0.48, 2], [box(0.08, 0.06, 0.16), x, -0.2, -0.48, 2]]),
      [bolt(), 0, 0.42, 0, 2, [0, 0, 0, 0.42]]],
    bucket: [[new T.CylinderGeometry(0.58, 0.4, 0.95, 24, 1, true), 0, -0.05, 0, 0], [cyl(0.4, 0.04, 24), 0, -0.5, 0, 1],
      [new T.TorusGeometry(0.58, 0.05, 8, 28), 0, 0.42, 0, 1, [Math.PI / 2, 0, 0]], [new T.TorusGeometry(0.42, 0.03, 6, 20, Math.PI), 0, 0.42, 0, 2]],
    drive: [[box(1.0, 0.36, 0.75), 0, -0.25, 0, 0], [box(0.6, 0.05, 0.02), 0, -0.25, 0.38, 1], [cyl(0.05, 0.02, 10), 0.36, -0.25, 0.38, 2, [Math.PI / 2, 0, 0]],
      [box(1.0, 0.36, 0.75), 0, 0.16, 0, 0], [box(0.6, 0.05, 0.02), 0, 0.16, 0.38, 1]],
    queue: [[box(1.5, 0.08, 0.5), 0, -0.45, 0, 1], ...[-0.5, -0.17, 0.16, 0.49].map((x, i) => [box(0.26, 0.42 - i * 0.04, 0.4), x, -0.2 - i * 0.02, 0, i ? 0 : 2]),
      [new T.ConeGeometry(0.14, 0.26, 4), 0.82, -0.2, 0, 2, [0, 0, -Math.PI / 2]]],
    broadcast: [[cyl(0.18, 0.7, 12), 0, -0.2, 0, 1], [new T.ConeGeometry(0.42, 0.5, 20, 1, true), 0, 0.3, 0, 0],
      [new T.TorusGeometry(0.6, 0.04, 6, 24, Math.PI * 0.6), 0, 0.3, 0, 2, [0, 0, Math.PI * 0.2]], [new T.TorusGeometry(0.8, 0.04, 6, 24, Math.PI * 0.6), 0, 0.3, 0, 2, [0, 0, Math.PI * 0.2]]],
    stream: [[box(1.7, 0.06, 0.45), 0, -0.45, 0, 1], ...[-0.7, -0.42, -0.14, 0.14, 0.42, 0.7].map((x, i) => [box(0.1, 0.5, 0.36), x, -0.17, 0, i % 2 ? 2 : 0])],
    splitter: [[cyl(0.32, 0.5, 16), 0, -0.4, 0, 1], [new T.SphereGeometry(0.3, 16, 12), 0, 0, 0, 0],
      ...[-0.6, 0, 0.6].flatMap((x) => [[cyl(0.06, 0.62, 8), x / 2, 0.3, 0, 0, [0, 0, -x * 0.9]], [new T.SphereGeometry(0.15, 12, 8), x, 0.55, 0, 2]])],
    globe: [[new T.SphereGeometry(0.5, 24, 16), 0, 0, 0, 0], [new T.TorusGeometry(0.53, 0.025, 6, 32), 0, 0, 0, 2, [Math.PI / 2, 0, 0]],
      [new T.TorusGeometry(0.53, 0.025, 6, 32), 0, 0, 0, 2], [new T.TorusGeometry(0.53, 0.025, 6, 32), 0, 0, 0, 2, [0, Math.PI / 2, 0]],
      [new T.TorusGeometry(0.72, 0.04, 6, 32), 0, -0.15, 0, 1, [Math.PI / 2 + 0.25, 0, 0]]],
    signpost: [[cyl(0.06, 1.3, 10), 0, -0.1, 0, 1], [box(0.7, 0.22, 0.06), 0.28, 0.35, 0, 0], [new T.ConeGeometry(0.15, 0.16, 3), 0.7, 0.35, 0, 0, [0, 0, -Math.PI / 2]],
      [box(0.6, 0.2, 0.06), -0.24, 0.05, 0, 2], [new T.ConeGeometry(0.14, 0.15, 3), -0.6, 0.05, 0, 2, [0, 0, Math.PI / 2]], [cyl(0.25, 0.06, 16), 0, -0.73, 0, 1]],
    shield: [[new T.CylinderGeometry(0.55, 0.55, 0.16, 24, 1, false, -Math.PI / 2, Math.PI), 0, 0.15, 0, 0, [Math.PI / 2, 0, 0]],
      [new T.ConeGeometry(0.55, 0.7, 4, 1, false, Math.PI / 4), 0, -0.3, 0, 0, [Math.PI, 0, 0]], [box(0.1, 0.6, 0.2), 0, 0, 0, 2], [box(0.4, 0.1, 0.2), 0, 0.1, 0, 2]],
    arch: [[box(0.26, 1.0, 0.4), -0.45, -0.25, 0, 0], [box(0.26, 1.0, 0.4), 0.45, -0.25, 0, 0], [box(1.25, 0.24, 0.5), 0, 0.37, 0, 1],
      [new T.TorusGeometry(0.32, 0.05, 6, 20, Math.PI), 0, 0.0, 0, 2]],
    bolt: [[bolt(), 0, 0, 0, 0], [cyl(0.4, 0.06, 20), 0, -0.75, 0, 1]],
    server: [[box(0.95, 1.4, 0.75), 0, 0, 0, 1], ...[-0.45, -0.15, 0.15, 0.45].flatMap((y) => [[box(0.82, 0.2, 0.04), 0, y, 0.38, 0], [box(0.06, 0.06, 0.03), 0.3, y, 0.41, 2]])],
    container: [[box(1.3, 0.72, 0.72), 0, -0.1, 0, 0], ...[-0.48, -0.24, 0, 0.24, 0.48].map((x) => [box(0.05, 0.74, 0.76), x, -0.1, 0, 1]),
      [box(1.34, 0.06, 0.76), 0, 0.28, 0, 1]],
    wheel: [[new T.TorusGeometry(0.45, 0.07, 8, 28), 0, 0, 0, 0], [cyl(0.14, 0.12, 14), 0, 0, 0, 1, [Math.PI / 2, 0, 0]],
      ...[0, 1, 2, 3, 4, 5, 6].map((k) => [box(0.05, 0.62, 0.05), 0, 0, 0, 2, [0, 0, k * Math.PI / 7 * 2]])],
    browser: [[box(1.2, 0.85, 0.06), 0, 0.15, 0, 2], [box(1.2, 0.14, 0.08), 0, 0.52, 0, 1], ...[-0.5, -0.4, -0.3].map((x) => [cyl(0.03, 0.02, 8), x, 0.52, 0.05, 0, [Math.PI / 2, 0, 0]]),
      [box(0.9, 0.08, 0.07), -0.05, 0.25, 0.01, 0], [box(0.6, 0.08, 0.07), -0.2, 0.1, 0.01, 0], [cyl(0.05, 0.4, 8), 0, -0.45, 0, 1], [box(0.5, 0.05, 0.3), 0, -0.65, 0, 1]],
    padlock: [[box(0.8, 0.65, 0.4), 0, -0.25, 0, 0], [new T.TorusGeometry(0.27, 0.07, 8, 20, Math.PI), 0, 0.08, 0, 1], [cyl(0.07, 0.2, 10), 0, -0.2, 0.21, 2, [Math.PI / 2, 0, 0]]],
    key: [[new T.TorusGeometry(0.24, 0.08, 8, 20), -0.45, 0, 0, 0], [box(0.75, 0.12, 0.12), 0.1, 0, 0, 0], [box(0.08, 0.2, 0.1), 0.3, -0.13, 0, 1], [box(0.08, 0.14, 0.1), 0.42, -0.1, 0, 1]],
    clock: [[cyl(0.52, 0.16, 28), 0, 0.05, 0, 0, [Math.PI / 2, 0, 0]], [cyl(0.44, 0.02, 28), 0, 0.05, 0.09, 2, [Math.PI / 2, 0, 0]],
      [box(0.05, 0.32, 0.03), 0, 0.18, 0.11, 1], [box(0.24, 0.05, 0.03), 0.1, 0.05, 0.11, 1], [box(0.5, 0.1, 0.3), 0, -0.55, 0, 1]],
    envelope: [[box(1.1, 0.7, 0.12), 0, 0, 0, 2], [box(0.78, 0.06, 0.14), -0.2, 0.12, 0, 1, [0, 0, -0.56]], [box(0.78, 0.06, 0.14), 0.2, 0.12, 0, 1, [0, 0, 0.56]]],
    gauge: [[new T.TorusGeometry(0.45, 0.09, 8, 28, Math.PI), 0, -0.05, 0, 0], [box(0.06, 0.45, 0.06), 0.1, 0.12, 0.05, 2, [0, 0, -0.5]], [cyl(0.08, 0.1, 12), 0, -0.05, 0.05, 1, [Math.PI / 2, 0, 0]],
      [box(1.05, 0.08, 0.3), 0, -0.1, 0, 1]],
    cloud: [[new T.SphereGeometry(0.34, 16, 12), -0.3, -0.05, 0, 0], [new T.SphereGeometry(0.44, 16, 12), 0.05, 0.1, 0, 0], [new T.SphereGeometry(0.3, 16, 12), 0.38, -0.08, 0, 0],
      [box(1.1, 0.12, 0.5), 0, -0.3, 0, 1]],
    plinth: [[box(0.8, 0.8, 0.8), 0, 0.05, 0, 0], [box(1.0, 0.16, 1.0), 0, -0.45, 0, 1]],
  };
  srModelPartsMade = parts;
  return parts;
}

/* A material per colour (deeper / lighter tones of the node's), kept for the view. */
function srModelMaterial(V, hex, tone) {
  const key = `${hex}:${tone}`;
  V.modelMats = V.modelMats || {};
  if (!V.modelMats[key]) {
    const c = new THREE.Color(hex);
    if (tone === 1) c.lerp(new THREE.Color(V.dark ? '#0b1018' : '#1d2433'), 0.32);
    if (tone === 2) c.lerp(new THREE.Color('#ffffff'), V.dark ? 0.45 : 0.5);
    V.modelMats[key] = new THREE.MeshLambertMaterial({ color: c, side: THREE.DoubleSide });
  }
  return V.modelMats[key];
}
function srModelBuild(V, p) {
  const kind = srModelKind(p.n), hex = srProviderColor(p.n.providerResolved || p.n.provider, 'node', 0, V.dark), g = new THREE.Group();
  for (const [geo, x, y, z, tone, rot] of srModelParts()[kind]) {
    const m = new THREE.Mesh(geo, srModelMaterial(V, hex, tone));
    m.position.set(x, y, z);
    if (rot) m.rotation.set(rot[0], rot[1], rot[2]);
    g.add(m);
  }
  const s = p.n.count > 1 ? 1 + Math.min(Math.log2(p.n.count), 4) * 0.12 : 1;
  g.position.set(p.x, p.y + 0.75, p.z); g.scale.setScalar(s);
  g.userData = { node: p.n.id, kind };
  return g;
}

/* Called with the room's look decided (srSetDetail) and each tenth of a second up close with the nodes in view: the models
   for those, built as they come into view; none when the simple shapes are shown. */
function srModelsSync(V, ids) {
  if (!V.models) { V.models = new Map(); V.modelLayer = new THREE.Group(); V.near.add(V.modelLayer); }
  const on = V.detail && V.lod === 'near';
  for (const m of V.nodeMeshes.detail) m.material.visible = !on;    // the shapes by service still take the press
  if (!on) {
    for (const g of V.models.values()) V.modelLayer.remove(g);
    V.models.clear();
    return;
  }
  const want = new Set(ids);
  for (const id of want) {
    if (V.models.has(id)) continue;
    if (V.models.size >= SR_MODEL.max) {
      const out = [...V.models.keys()].find((k) => !want.has(k));
      if (!out) break;
      V.modelLayer.remove(V.models.get(out)); V.models.delete(out);
    }
    const p = V.L.pos.get(id);
    if (!p || p.hiddenIn) continue;
    const g = srModelBuild(V, p);
    V.modelLayer.add(g); V.models.set(id, g);
  }
}
