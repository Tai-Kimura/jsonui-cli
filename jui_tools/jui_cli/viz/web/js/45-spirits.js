/* ---------- the skill spirit (ticket 2026-10-21-jui-viz-skill-spirit) ----------
   While a robot's session uses a skill (the server's agents slice: skill {name, since}), a spirit stands behind it: a
   model the person put in <viz home>/spirits/ or a bundled original (POST /api/spirits lists the ones the checks
   pass), chosen at random at each skill's start — the models naming the skill first, weighted. A model's spirit.glb
   stands at the robot's back, its robot-*.glb and prop-*.glb are put on the robot's anchors, and what it hides
   (band, antenna, headset) is put back when the skill ends. Its bubble's words are the model's (spirit.json, the
   page's language, then ja, then the first), and its tail points at who says them: the spirit, or the robot. At most
   SPIRIT.maxShown spirits stand at once; a robot past them still wears the parts. With reduced motion the spirit
   stands still. The badge "スキル使用中: <名>" shows by the tag with or without a model. */
const SPIRIT = { maxShown: 4, fadeMs: 700, listMs: 60_000, bubbleSec: 4, back: [0, 0, -0.9] };
const SPIRITS = { list: null, listedAt: 0, asking: null, models: new Map() };
/* The anchors spirit.json names (spirits.ANCHORS), as points of the robot's parts (10-robot-core.js createRobot). */
const SPIRIT_ANCHORS = {
  head: (r) => [r.head, [0, 0, 0]],
  forehead: (r) => [r.head, [0, 0.62, HEAD.d / 2]],
  band: (r) => [r.head, [0, BAND.y, 0]],
  headset: (r) => [r.head, [0, 0.42, 0]],
  face: (r) => [r.head, [0, 0.35, HEAD.d / 2 + 0.01]],
  handL: (r) => [r.armL, [0, -0.44, 0.2]],
  handR: (r) => [r.armR, [0, -0.44, 0.2]],
  back: (r) => [r.root, SPIRIT.back],
  root: (r) => [r.root, [0, 0, 0]],
};
/* Where a part goes when spirit.json does not say: robot-*.glb on the head, prop-*.glb in the right hand. */
const spiritDefaultAt = (file) => (file.startsWith('prop-') ? 'handR' : 'head');
/* A model's words in the page's language (05-i18n.js), else ja, else the first written; a string is itself. */
function spiritWords(v) {
  if (typeof v === 'string' || Array.isArray(v)) return v;
  if (!v || typeof v !== 'object') return '';
  const lang = (typeof I18N !== 'undefined' && I18N.language) || 'en';
  return v[lang] !== undefined ? v[lang] : v.ja !== undefined ? v.ja : Object.values(v)[0] || '';
}
/* The list, asked at most every SPIRIT.listMs (a model put in the folder shows from the next skill after). */
function spiritList() {
  if (typeof SOURCE.spirits !== 'function') return null;
  if (!SPIRITS.asking && (!SPIRITS.list || vizNow() - SPIRITS.listedAt > SPIRIT.listMs)) {
    SPIRITS.asking = SOURCE.spirits().then((got) => {
      if (got.ok) { SPIRITS.list = got.models; SPIRITS.listedAt = vizNow(); }
      SPIRITS.asking = null;
    });
  }
  return SPIRITS.list;
}
/* The model for a skill: the ones naming it, else the ones naming none; weighted (weight 0 is never chosen). */
function spiritPick(list, skill, rnd = Math.random) {
  const named = list.filter((m) => Array.isArray(m.skills) && m.skills.includes(skill));
  const pool = (named.length ? named : list.filter((m) => !(m.skills || []).length)).filter((m) => Number(m.weight) > 0);
  const total = pool.reduce((s, m) => s + Number(m.weight), 0);
  let x = rnd() * total;
  for (const m of pool) { x -= Number(m.weight); if (x < 0) return m; }
  return pool[pool.length - 1] || null;
}
/* A model's .glb files, read once (GLTFLoader.parse on the bytes: no URL is given to the loader). */
function spiritLoad(model) {
  if (!SPIRITS.models.has(model.id)) {
    const loader = new GLTFLoader();
    // An embedded texture is a blob: URL. GLTFLoader reads it with ImageBitmapLoader's fetch where it can, and the
    // page's CSP has no blob: in connect-src (measured: the picture never loaded). An <img> may read it (img-src
    // blob:), so the parser is given a TextureLoader before it loads anything; the policy stays as it is.
    loader.register((parser) => { parser.textureLoader = new THREE.TextureLoader(parser.options.manager); return { name: 'jui-viz-img-textures' }; });
    const one = (file) => SOURCE.spiritFile(model.id, file).then((got) => {
      if (!got.ok) throw new Error(`${file}: ${got.status} ${got.error || ''}`);
      return new Promise((ok, no) => loader.parse(got.buffer, '', ok, no));
    }).then((gltf) => [file, gltf]);
    SPIRITS.models.set(model.id, Promise.all(Object.keys(model.files).map(one)).then((pairs) => Object.fromEntries(pairs)));
  }
  return SPIRITS.models.get(model.id);
}
/* Put a part on an anchor; its offset, rotation (degrees) and scale as spirit.json writes them. */
function spiritPut(r, object, at, part = {}) {
  const [parent, p] = (SPIRIT_ANCHORS[at] || SPIRIT_ANCHORS.head)(r);
  const holder = new THREE.Group();
  holder.position.set(p[0], p[1], p[2]);
  const o = part.offset || [0, 0, 0], rot = part.rotate || [0, 0, 0];
  object.position.add(new THREE.Vector3(o[0], o[1], o[2]));
  object.rotation.set(...rot.map((d) => THREE.MathUtils.degToRad(d)));
  if (part.scale) object.scale.multiplyScalar(part.scale);
  holder.add(object);
  parent.add(holder);
  return holder;
}
/* The spirit's materials: its own, transparent, at spirit.json's opacity and tinted; their opacity then follows the
   fade (spiritFade) from userData.base. */
function spiritGhost(object, spec) {
  const tint = spec.tint ? new THREE.Color(spec.tint) : null;
  object.traverse((o) => {
    if (!o.isMesh) return;
    o.material = [].concat(o.material).map((m) => {
      const c = m.clone();
      c.transparent = true; c.depthWrite = false;
      if (tint && c.color) c.color.multiply(tint);
      c.userData.base = (spec.opacity ?? 0.55) * (m.opacity ?? 1);
      c.opacity = 0;
      return c;
    });
    if (o.material.length === 1) o.material = o.material[0];
    o.renderOrder = 2;
  });
}
function spiritFade(object, k) {
  object.traverse((o) => { if (o.isMesh) for (const m of [].concat(o.material)) m.opacity = m.userData.base * k; });
}
/* What the robot wears for the skill comes off: the parts are taken down and disposed (the model's geometry is the
   loaded copy's, shared, and kept), the hidden parts shown again. */
function spiritDrop(R) {
  const S = R.spirit;
  if (!S) return;
  for (const h of S.holders) { h.parent && h.parent.remove(h); h.traverse((o) => { if (o.isMesh) for (const m of [].concat(o.material)) if (m.userData.base !== undefined) m.dispose(); }); }
  for (const [part, was] of S.hidden) part.visible = was;
  if (S.bubbleEl) S.bubbleEl.remove();
  R.spirit = null;
}
/* Whether this robot may raise a spirit now: SPIRIT.maxShown at most (the parts are worn either way). */
function spiritRoom() { return robots.filter((x) => x.spirit && x.spirit.figure).length < SPIRIT.maxShown; }
/* One frame of one robot (40-scene.js liveUpdateRobots). */
function spiritTick(R, st, nowSec, dt) {
  const skill = SOURCE.mode === 'live' && has3D && st.skill ? st.skill : null;
  const key = skill ? `${skill.name}@${skill.since}` : null;
  spiritBadge(R, skill);
  const S = R.spirit;
  if (S && S.key !== key) {   // the skill ended (or another began): leave, then come off
    if (S.phase !== 'leave') { S.phase = 'leave'; S.phaseAt = vizNow(); spiritClip(S, 'leave'); }
    if (vizNow() - S.phaseAt >= SPIRIT.fadeMs || !S.figure) spiritDrop(R);
  }
  if (!R.spirit && key) {
    const list = spiritList();
    if (!list) return;
    const model = list.length ? spiritPick(list, skill.name) : null;
    R.spirit = { key, model, phase: 'loading', phaseAt: vizNow(), holders: [], hidden: [], figure: null, mixer: null };
    if (model) spiritWear(R, R.spirit);
    return;
  }
  const T = R.spirit;
  if (!T || T.phase === 'loading') return;
  if (T.mixer && !reduceMotion) T.mixer.update(dt);
  const k = T.phase === 'appear' ? Math.min(1, (vizNow() - T.phaseAt) / SPIRIT.fadeMs)
    : T.phase === 'leave' ? Math.max(0, 1 - (vizNow() - T.phaseAt) / SPIRIT.fadeMs) : 1;
  if (T.phase === 'appear' && k >= 1) { T.phase = 'shown'; spiritClip(T, 'loop'); }
  if (T.figure) { spiritFade(T.figure, reduceMotion ? 1 : k); T.figure.visible = !TOWER.on; }
  spiritBubble(R, T);
}
async function spiritWear(R, S) {
  let gltfs;
  try { gltfs = await spiritLoad(S.model); } catch (err) { S.phase = 'shown'; S.error = String(err); return; }
  if (R.spirit !== S || !robots.includes(R)) return;   // the skill ended, or the robot left, while it loaded
  const spec = S.model.spec || {}, r = R.robot;
  const sp = spec.spirit || {};
  const figureFile = sp.file || 'spirit.glb';
  if (gltfs[figureFile] && spiritRoom()) {
    const figure = SkeletonUtils.clone(gltfs[figureFile].scene);
    if (sp.scale) figure.scale.multiplyScalar(sp.scale);
    spiritGhost(figure, sp);
    S.holders.push(spiritPut(r, figure, sp.at || 'back'));
    S.figure = figure;
    S.clips = gltfs[figureFile].animations || [];
    S.names = sp.clips || {};
    S.mixer = new THREE.AnimationMixer(figure);
  }
  for (const part of spec.parts || []) {
    if (!gltfs[part.file] || part.file === figureFile) continue;
    S.holders.push(spiritPut(r, SkeletonUtils.clone(gltfs[part.file].scene), part.at || spiritDefaultAt(part.file), part));
  }
  for (const file of Object.keys(gltfs)) {   // a part spirit.json does not place goes on its default anchor
    if (file === figureFile || (spec.parts || []).some((p) => p.file === file)) continue;
    S.holders.push(spiritPut(r, SkeletonUtils.clone(gltfs[file].scene), spiritDefaultAt(file)));
  }
  for (const name of (spec.robot && spec.robot.hide) || []) {
    const part = name === 'band' ? r.band : name === 'antenna' ? r.antenna : name === 'headset' ? r.headset : null;
    if (part) { S.hidden.push([part, part.visible]); part.visible = false; }
  }
  const tag = (spec.robot && spec.robot.tag) || 'auto';
  const onHead = (spec.parts || []).some((p) => ['head', 'forehead', 'band'].includes(p.at || spiritDefaultAt(p.file)))
    || Object.keys(gltfs).some((f) => f.startsWith('robot-'));
  S.tagCheek = tag === 'cheek' || (tag === 'auto' && onHead);
  S.bubble = spec.bubble || null;
  S.phase = 'appear'; S.phaseAt = vizNow();
  spiritClip(S, 'appear');
}
/* Play the model's clip for a phase (spirit.json's spirit.clips names it; a clip it does not have plays nothing). */
function spiritClip(S, slot) {
  if (!S.mixer || reduceMotion) return;
  const clip = (S.clips || []).find((c) => c.name === (S.names[slot] || slot));
  if (!clip) return;
  S.mixer.stopAllAction();
  const action = S.mixer.clipAction(clip);
  if (slot === 'loop') action.setLoop(THREE.LoopRepeat, Infinity);
  else { action.setLoop(THREE.LoopOnce, 1); action.clampWhenFinished = true; }
  action.reset().play();
}
/* The badge by the tag: the skill in use, with or without a model (the tag's column, 40-scene.js placeRobotTags). */
function spiritBadge(R, skill) {
  if (!skill) { if (R.skillEl) R.skillEl.hidden = true; return; }
  if (!R.skillEl) {
    R.skillEl = document.createElement('div');
    R.skillEl.className = 'skill-badge';
    R.skillEl.dataset.skillBadge = R.def.id;
    tagsEl.appendChild(R.skillEl);
  }
  const text = tl('spirit.badge', { name: skill.name });
  if (R.skillEl.textContent !== text) R.skillEl.textContent = text;
  R.skillEl.hidden = false;
}
/* The model's bubble, for bubble.showSec after the spirit appears: its words and their ruby (<ruby>/<rt>, the words
   as text only), its tail at who says them — the spirit's head (its "bubbleAnchor" node, else the top of the figure)
   or the robot's (then it rides in the tag's column, over the badge). */
function spiritBubble(R, S) {
  const b = S.bubble;
  const showing = b && S.phase === 'shown' && vizNow() - (S.shownAt || (S.shownAt = vizNow())) < (b.showSec || SPIRIT.bubbleSec) * 1000;
  if (!showing) { if (S.bubbleEl) S.bubbleEl.hidden = true; return; }
  if (!S.bubbleEl) {
    const el = document.createElement('div');
    el.className = `spirit-bubble font-${b.font === 'mincho' ? 'mincho' : 'gothic'} tail-${b.tail === 'right' ? 'right' : 'left'}`;
    el.dataset.spiritBubble = R.def.id;
    el.dataset.target = b.target === 'robot' ? 'robot' : 'spirit';
    const words = spiritWords(b.text), ruby = spiritWords(b.ruby);
    const lines = Array.isArray(words) ? words : [words];
    lines.forEach((line, i) => {
      const row = document.createElement('div');
      if (i === 0 && ruby && !Array.isArray(ruby)) {
        const rb = document.createElement('ruby'); rb.append(String(line));
        const rt = document.createElement('rt'); rt.textContent = String(ruby); rb.appendChild(rt);
        row.appendChild(rb);
      } else row.textContent = String(line);
      el.appendChild(row);
    });
    tagsEl.appendChild(el);
    S.bubbleEl = el;
  }
  S.bubbleEl.hidden = false;
  if (S.bubbleEl.dataset.target === 'spirit') placeTag(S.bubbleEl, spiritHead(R, S));
}
/* The point a bubble aimed at the spirit points at: its "bubbleAnchor" node, else the top middle of the figure. */
function spiritHead(R, S) {
  const out = new THREE.Vector3();
  const anchor = S.figure && S.figure.getObjectByName('bubbleAnchor');
  if (anchor) return anchor.getWorldPosition(out);
  if (!S.figure) return R.robot.root.position.clone().addScaledVector(TAG_UP, R.robot.size || 1);
  const box = new THREE.Box3().setFromObject(S.figure);
  return out.set((box.min.x + box.max.x) / 2, box.max.y, (box.min.z + box.max.z) / 2);
}
/* The tag's point when the robot wears something on its head (spirit.json robot.tag auto / cheek): its cheek. */
const SPIRIT_CHEEK = new THREE.Vector3(0.45, 0.25, HEAD.d / 2);
function spiritTagPoint(R, out) {
  if (!R.spirit || !R.spirit.tagCheek || R.spirit.phase === 'loading') return false;
  out.copy(SPIRIT_CHEEK);
  R.robot.head.localToWorld(out);
  return true;
}
