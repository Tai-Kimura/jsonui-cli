/* ---------- the skill spirit (ticket 2026-10-21-jui-viz-skill-spirit) ----------
   While a robot's session uses a skill (the server's agents slice: skill {name, since}), a spirit stands behind it: a
   model the person put in <viz home>/spirits/ or a bundled original (POST /api/spirits lists the ones the checks
   pass), chosen at random at each skill's start — the models naming the skill first, weighted. A model's spirit.glb
   stands at the robot's back, its robot-*.glb and prop-*.glb are put on the robot's anchors, and what it hides
   (band, antenna, headset) is put back when the skill ends. Its bubble's words are the model's (spirit.json, the
   page's language, then ja, then the first), and its tail points at who says them: the spirit, or the robot. At most
   SPIRIT.maxShown spirits stand at once; a robot past them still wears the parts. With reduced motion the spirit
   stands still. The badge "スキル使用中: <名>" shows by the tag with or without a model. */
// minPx: a robot drawn shorter than this on screen (a floor seen from far) shows no spirit or effects, only its parts
// fullFx: the spirits nearest the camera that also draw their outline, afterimages and glow (measured 10-22 in the e2e's
// software GL: four spirits made the frames 57 % longer, about 54 draws a spirit, each mesh drawn twice — the figure
// and its outline — and each afterimage a whole figure again); the rest keep the figure, the aura and the sparks
// hide: null; the e2e's frame-cost samples set it (80-dbg.js spiritHide) to 'figure', 'all' or 'dom' to see what each costs
const SPIRIT = { maxShown: 4, fadeMs: 700, listMs: 60_000, bubbleSec: 4, back: [0, 0, -0.9], minPx: 48, gap: 4, fullFx: 2, hide: null };
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
  object.traverse((o) => {
    if (!o.isMesh) return;
    for (const m of [].concat(o.material)) {
      if (m.uniforms && m.uniforms.uFade) m.uniforms.uFade.value = k;   // the ghost's shader
      else if (m.userData.base !== undefined) m.opacity = m.userData.base * k;
    }
  });
}
/* What the robot wears for the skill comes off: the parts are taken down and disposed (the model's geometry is the
   loaded copy's, shared, and kept), the hidden parts shown again. */
function spiritDrop(R) {
  const S = R.spirit;
  if (!S) return;
  for (const h of S.holders) {
    if (h.parent) h.parent.remove(h);
    h.traverse((o) => { if (o.isMesh || o.isSprite || o.isLine) for (const m of [].concat(o.material)) if (m.userData.base !== undefined || m.userData.ghost || o.isSprite || o.isLine) m.dispose(); });
  }
  for (const [part, was] of S.hidden) part.visible = was;
  const r = R.robot;
  if (r.spiritEyes || r.spiritPose) { r.spiritEyes = null; r.spiritPose = null; r.faceMode = null; }   // its own face again
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
  if (SPIRIT.hide === 'dom' && R.skillEl) R.skillEl.hidden = true;
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
  const near = !TOWER.on && spiritNear(R);   // the building, or a floor seen from far: the spirit and its effects rest
  T.near = near;
  const hide = SPIRIT.hide;   // the e2e's frame-cost samples only: 'figure' the figures out, 'all' the effects too, 'dom' the DOM too
  if (T.figure) { spiritFade(T.figure, reduceMotion ? 1 : k); T.figure.visible = near && !hide; }
  if (T.ghost) T.ghost.uniforms.uY0.value = R.robot.root.position.y;   // the downward fade from the robot's floor
  if (T.fx) { T.fx.group.visible = near && !hide; if (near) spiritFxTick(R, T, dt, reduceMotion ? 1 : k); }
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
    if (sp.material && sp.material.kind === 'ghost') S.ghost = spiritGhostShader(figure, sp);
    else spiritGhost(figure, sp);
    spiritOutline(figure, sp);
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
  const robotSpec = spec.robot || {};
  r.spiritEyes = robotSpec.eyes ? { shape: robotSpec.eyes.shape || 'normal', color: robotSpec.eyes.color || null } : null;
  r.spiritPose = robotSpec.pose && robotSpec.pose !== 'none' ? robotSpec.pose : null;
  spiritFxStart(R, S, gltfs);
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
  S.bubbleEl.hidden = !S.near || SPIRIT.hide === 'dom';   // placed with the others after the tags (spiritPlaceBubbles)
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

/* ---------- the spirit's look (spirit.json spirit.material / outline) ----------
   glTF cannot carry a shader, so the page holds the "ghost" look (the prototype's): a rim of light over a shade,
   fading downward from yFade over yFadeLen, at spirit.json's opacity and the fade's k. A skinned mesh is skinned here
   too. "plain" (or no material) keeps the model's own colours, transparent and tinted (spiritGhost). */
const SPIRIT_GHOST_VS = `#include <common>
#include <skinning_pars_vertex>
varying vec3 vN; varying vec3 vV; varying float vY;
void main() {
  #include <skinbase_vertex>
  #include <beginnormal_vertex>
  #include <skinnormal_vertex>
  #include <begin_vertex>
  #include <skinning_vertex>
  vec4 mv = modelViewMatrix * vec4(transformed, 1.0);
  vN = normalize(normalMatrix * objectNormal); vV = normalize(-mv.xyz);
  vY = (modelMatrix * vec4(transformed, 1.0)).y;
  gl_Position = projectionMatrix * mv;
}`;
const SPIRIT_GHOST_FS = `uniform vec3 uRim; uniform vec3 uShade; uniform vec3 uBase;
uniform float uRimK; uniform float uPow; uniform float uYFade; uniform float uYFadeLen; uniform float uY0;
uniform float uOpacity; uniform float uFade;
varying vec3 vN; varying vec3 vV; varying float vY;
void main() {
  float rim = clamp(pow(1.0 - abs(dot(normalize(vN), normalize(vV))), uPow) * uRimK, 0.0, 1.0);
  vec3 col = mix(mix(uShade, uBase, 0.6), uRim, rim);
  float down = uYFade == 0.0 ? 1.0 : clamp((vY - uY0) / uYFadeLen, 0.0, 1.0);
  float a = uOpacity * uFade * clamp(0.35 + rim, 0.0, 1.0) * mix(1.0 - abs(uYFade) * 0.25, 1.0, down);
  gl_FragColor = vec4(col, a);
}`;
function spiritGhostShader(object, spec) {
  const m = spec.material || {};
  const base = new THREE.Color(m.base || spec.tint || '#ffffff');
  const mat = new THREE.ShaderMaterial({
    vertexShader: SPIRIT_GHOST_VS, fragmentShader: SPIRIT_GHOST_FS, transparent: true, depthWrite: false,
    uniforms: { uRim: { value: new THREE.Color(m.rim || '#ffffff') }, uShade: { value: new THREE.Color(m.shade || '#202830') },
      uBase: { value: base }, uRimK: { value: m.rimK ?? 1.2 }, uPow: { value: m.pow ?? 2 }, uYFade: { value: m.yFade ?? 0 },
      uYFadeLen: { value: m.yFadeLen ?? 1 }, uY0: { value: 0 }, uOpacity: { value: spec.opacity ?? 0.55 }, uFade: { value: 0 } },
  });
  mat.userData.ghost = true;
  object.traverse((o) => { if (o.isMesh) { o.material = mat; o.renderOrder = 2; } });
  return mat;
}
/* The meshes an outline or a glow goes round: each mesh but the shells, and none under a node named fx_… (a flat card,
   a flame: a shell drawn from behind shows there as dark or tinted slivers, not as a rim). */
function spiritShellable(object) {
  const out = [];
  const walk = (o, skip) => {
    skip = skip || /^fx_/.test(o.name || '');
    if (o.isMesh && !skip && !o.userData.spiritOutline && !o.userData.spiritGlow) out.push(o);
    for (const c of o.children) walk(c, skip);
  };
  walk(object, false);
  return out;
}
/* A shell of the mesh: its geometry again (and, skinned, its skeleton) as its child at no offset, so whatever moves the
   mesh (its own node in a clip, the bones) moves the shell with it. */
function spiritShell(mesh, material, flag, renderOrder) {
  const shell = mesh.clone(false);
  shell.position.set(0, 0, 0); shell.quaternion.identity(); shell.scale.set(1, 1, 1);
  shell.material = material; shell.renderOrder = renderOrder; shell.userData = { [flag]: true };
  mesh.add(shell);
  return shell;
}
/* The outline: each mesh again, pushed out along its normals by width and drawn from behind, in the outline's colour. */
function spiritOutline(object, spec) {
  const o = spec.outline;
  if (!o || !o.width) return;
  const mat = new THREE.MeshBasicMaterial({ color: o.color || '#000000', side: THREE.BackSide, transparent: true, depthWrite: false });
  mat.onBeforeCompile = (sh) => {   // the width as a uniform: pushed out before skinning, so a skinned mesh's shell bends with it
    sh.uniforms.uWidth = { value: Number(o.width) };
    sh.vertexShader = 'uniform float uWidth;\n' + sh.vertexShader.replace('#include <begin_vertex>', '#include <begin_vertex>\n  transformed += normal * uWidth;');
  };
  mat.userData.base = 1; mat.userData.outline = true;
  for (const mesh of spiritShellable(object)) spiritShell(mesh, mat, 'spiritOutline', 1);
}

/* effects.glow: a shell on each of the figure's meshes the outline goes round (spiritShell: the mixer that moves the
   figure moves it too). It grows along the normals before skinning, as the outline does: scale 1.03 is a rim of 3% of
   half the figure's longest side, whatever the mesh's own scale. */
const spiritGlowBox = new THREE.Box3(), spiritGlowV = new THREE.Vector3(), spiritGlowW = new THREE.Vector3();
function spiritGlow(figure, g) {
  figure.updateMatrixWorld(true);
  const figureScale = figure.getWorldScale(spiritGlowW).x || 1;
  const size = spiritGlowBox.setFromObject(figure).getSize(spiritGlowV);
  const half = Math.max(size.x, size.y, size.z) / 2 / figureScale;
  const shells = [];
  for (const mesh of spiritShellable(figure)) {
    const own = (mesh.getWorldScale(spiritGlowW).x || figureScale) / figureScale;   // the mesh's scale in the figure's
    const m = new THREE.MeshBasicMaterial({ color: g.color || '#ffffff', transparent: true, opacity: 0, depthWrite: false, side: THREE.BackSide });
    m.userData.base = g.opacity ?? 0.25;
    m.onBeforeCompile = (sh) => {
      sh.uniforms.uWidth = { value: ((g.scale || 1.06) - 1) * half / own };
      sh.vertexShader = 'uniform float uWidth;\n' + sh.vertexShader.replace('#include <begin_vertex>', '#include <begin_vertex>\n  transformed += normal * uWidth;');
    };
    shells.push(spiritShell(mesh, m, 'spiritGlow', 0));
  }
  return shells;
}

/* ---------- what spirit.json's robot says: its eyes and its pose ---------- */
/* At the desk only (the robot's own pose elsewhere): book — the left hand holds the model's book up, the right types;
   arms-crossed — no typing; type — the usual typing; none — as the state poses it. */
const SPIRIT_DESK = new Set(['typing', 'command', 'reading', 'thinking', 'idle', 'done']);
function spiritPose(r, p, t) {
  if (!SPIRIT_DESK.has(r.state) || r.spiritPose === 'none') return;
  const tap = (ph) => (reduceMotion ? 0 : Math.max(0, Math.sin(t * 15 + ph)) * 0.13);
  if (r.spiritPose === 'book') { p.aLx = -1.55; p.aLz = -0.55; p.aRx = -1.05 + tap(1.9); p.aRz = 0.32; p.headX = 0.12; }
  else if (r.spiritPose === 'arms-crossed') { p.aLx = -1.35; p.aLz = -1.05; p.aRx = -1.35; p.aRz = 1.05; p.headX = -0.05; }
  else if (r.spiritPose === 'type') { p.aLx = -1.05 + tap(0); p.aLz = -0.32; p.aRx = -1.05 + tap(1.9); p.aRz = 0.32; }
}

/* ---------- the effects the page draws (spirit.json effects, shouts) ----------
   Each in a group of its own on the robot's root (it moves and scales with the robot), every sprite and mesh made once
   at the start (the sparks' pool as many as rate × sparkLife shows, at most sparkMax). With reduced motion: the aura
   and the glow stand still, and no sparks, lightning, afterimages or shouts. */
const SPIRIT_FX = { sparkLife: 1.6, sparkMax: 64, shoutLife: 1.1, tongues: 24, cores: 8, boltSegs: 7, boltSec: 0.15 };
let spiritDot = null;
function spiritDotTex() {
  if (spiritDot) return spiritDot;
  const c = document.createElement('canvas'); c.width = c.height = 32;
  const g = c.getContext('2d'), grad = g.createRadialGradient(16, 16, 0, 16, 16, 16);
  grad.addColorStop(0, 'rgba(255,255,255,1)'); grad.addColorStop(1, 'rgba(255,255,255,0)');
  g.fillStyle = grad; g.fillRect(0, 0, 32, 32);
  spiritDot = new THREE.CanvasTexture(c);
  return spiritDot;
}
/* The aura's flame (white, coloured by its material): a tongue, bright at its foot and gone at its tip, and the
   envelope round the robot with flame points along its top (both in the page's canvas, made once). */
let spiritFlame = null;
function spiritFlameTex() {
  if (spiritFlame) return spiritFlame;
  const tongue = makeCanvas(128, 256), x = tongue.getContext('2d');
  const g = x.createLinearGradient(0, 256, 0, 0);
  g.addColorStop(0, 'rgba(255,255,255,0.95)'); g.addColorStop(0.45, 'rgba(255,255,255,0.75)'); g.addColorStop(0.85, 'rgba(255,255,255,0.3)'); g.addColorStop(1, 'rgba(255,255,255,0)');
  x.fillStyle = g; x.beginPath(); x.moveTo(64, 0);
  x.bezierCurveTo(96, 70, 124, 150, 112, 200); x.bezierCurveTo(100, 250, 28, 250, 16, 200); x.bezierCurveTo(4, 150, 32, 70, 64, 0); x.fill();
  const env = makeCanvas(256, 320), y = env.getContext('2d');
  const r = y.createRadialGradient(128, 210, 20, 128, 190, 150);
  r.addColorStop(0, 'rgba(255,255,255,0.5)'); r.addColorStop(0.55, 'rgba(255,255,255,0.45)'); r.addColorStop(1, 'rgba(255,255,255,0)');
  y.fillStyle = r; y.beginPath(); y.moveTo(30, 310);
  const tips = [[24, 150], [52, 70], [78, 110], [100, 30], [128, 80], [156, 26], [178, 108], [204, 66], [232, 148]];
  y.quadraticCurveTo(0, 220, tips[0][0], tips[0][1]);
  for (let i = 1; i < tips.length; i++) { const [px, py] = tips[i - 1], [qx, qy] = tips[i]; y.quadraticCurveTo((px + qx) / 2, Math.max(py, qy) + 40, qx, qy); }
  y.quadraticCurveTo(256, 220, 226, 310); y.closePath(); y.fill();
  spiritFlame = { tongue: texFrom(tongue), envelope: texFrom(env) };
  return spiritFlame;
}
const spiritUnitCyl = new THREE.CylinderGeometry(1, 1, 1, 6, 1).translate(0, 0.5, 0).rotateX(Math.PI / 2);   // from 0 to +z, one long
const spiritBoltA = new THREE.Vector3(), spiritBoltB = new THREE.Vector3(), spiritBoltD = new THREE.Vector3(), spiritZ = new THREE.Vector3(0, 0, 1);
function spiritLimb(mesh, a, b, r) {   // a cylinder from a to b (its parent's own space, not the world's), r thick
  const d = spiritBoltD.subVectors(b, a), len = d.length();
  mesh.position.copy(a); mesh.quaternion.setFromUnitVectors(spiritZ, len > 1e-6 ? d.divideScalar(len) : spiritZ);
  mesh.scale.set(r, r, Math.max(1e-4, len));
}
function spiritShoutTex(text, style = {}) {
  const c = document.createElement('canvas'); c.width = 256; c.height = 96;
  const g = c.getContext('2d');
  g.setTransform(1, 0, Math.tan(THREE.MathUtils.degToRad(style.skew || 0)), 1, 0, 0);
  g.font = '900 56px system-ui, sans-serif'; g.textAlign = 'center'; g.textBaseline = 'middle';
  g.lineWidth = 8; g.strokeStyle = style.stroke || '#1a1a1a'; g.strokeText(text, 128, 50);
  g.fillStyle = style.fill || '#ffffff'; g.fillText(text, 128, 50);
  return new THREE.CanvasTexture(c);
}
/* effects.aura. style "flame" (the default): an envelope behind the robot with flame points along its top, tongues that
   rise round it, stretch and die at three rates, and a few brighter ones at its foot. "column": the open cylinder of
   before. size widens it, height lifts it, flicker speeds it (0: still), opacity is the whole. */
function spiritAura(group, a) {
  const h = a.height || 1.6, size = a.size || 1, color = new THREE.Color(a.color || '#ffd23a'), base = a.opacity ?? 0.35;
  if (a.style === 'column') {
    const mat = new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0, depthWrite: false, side: THREE.DoubleSide });
    mat.userData.base = base;
    const cone = new THREE.Mesh(new THREE.CylinderGeometry(0.55 * size, 0.85 * size, h, 20, 1, true), mat);
    cone.position.y = h / 2; group.add(cone);
    return { style: 'column', mesh: cone, base, flicker: a.flicker ?? 1, width: 1.7 * size, h };
  }
  const T = spiritFlameTex();
  const sprite = (map, tint, z, cx, cy) => {
    const sp = new THREE.Sprite(new THREE.SpriteMaterial({ map, color: tint, transparent: true, opacity: 0, depthWrite: false }));
    sp.center.set(cx, cy); sp.position.z = z; group.add(sp); return sp;
  };
  const envelope = sprite(T.envelope, color, -0.45, 0.5, 0);
  envelope.position.y = 0.1;
  const tongues = [], white = color.clone().lerp(new THREE.Color('#ffffff'), 0.55);
  let seed = 7;
  const rnd = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);
  for (let i = 0; i < SPIRIT_FX.tongues + SPIRIT_FX.cores; i++) {
    const core = i >= SPIRIT_FX.tongues, ang = Math.PI * (0.03 + 0.94 * rnd());
    const sp = sprite(T.tongue, core ? white : color, 0, 0.5, 0.15);
    tongues.push({ sp, core, x: Math.cos(ang) * (core ? 0.35 : 0.66 + 0.2 * rnd()) * size, z: -0.2 - Math.sin(ang) * 0.35,
      rate: (core ? 2 : [4, 5, 6][i % 3]) / 3, off: rnd(), w: (core ? 0.3 : 0.42 + 0.28 * rnd()) * size, hh: (core ? 0.6 : 0.9 + 0.5 * rnd()) * h / 1.6, k: i });
  }
  return { style: 'flame', envelope, tongues, base, flicker: a.flicker ?? 1, width: 1.8 * size, size, h };
}
function spiritAuraTick(A, t, k) {
  const still = reduceMotion || !A.flicker, s = still ? 0 : t * A.flicker, TAU = Math.PI * 2;
  if (A.style === 'column') {
    A.mesh.material.opacity = A.base * k * (still ? 1 : 0.85 + Math.sin(s * 7) * 0.15);
    if (!still) A.mesh.scale.set(1 + Math.sin(s * 5) * 0.04, 1 + Math.sin(s * 3.3) * 0.06, 1 + Math.sin(s * 4.1) * 0.04);
    return;
  }
  A.envelope.material.opacity = Math.min(1, A.base * 1.6 * k * (still ? 0.9 : 0.85 + 0.1 * Math.sin(TAU * 1.5 * s)));
  A.envelope.scale.set(2.6 * A.size * (1 + (still ? 0 : 0.03 * Math.sin(TAU * s))), A.h * 1.6 * (1 + (still ? 0 : 0.05 * Math.sin(TAU * 1.5 * s))), 1);
  for (const F of A.tongues) {
    const p = still ? (F.off * 0.8 + 0.1) : (s * F.rate + F.off) % 1, flick = still ? 1 : 1 + 0.15 * Math.sin(TAU * 2 * s + F.k);
    F.sp.position.set(F.x * (1 - 0.3 * p) + (still ? 0 : 0.05 * Math.sin(TAU * 0.75 * s + F.k)), 0.25 + p * A.h * (F.core ? 0.35 : 0.65), F.z);
    F.sp.scale.set(F.w * (1 - 0.4 * p) * flick, F.hh * (0.7 + 0.5 * Math.sin(Math.PI * p)) * flick, 1);
    F.sp.material.opacity = Math.min(1, A.base * k * Math.sin(Math.PI * Math.min(1, p * 1.2)) * (F.core ? 2.2 : 2.6));
  }
}
function spiritFxStart(R, S, gltfs) {
  const spec = S.model.spec || {}, fx = spec.effects || {}, r = R.robot;
  const group = new THREE.Group(); r.root.add(group); S.holders.push(group);
  const F = S.fx = { group, sparks: [], shouts: [], clones: [], next: 0, nextShout: 0, nextBolt: 0, t: 0 };
  if (fx.aura) F.aura = spiritAura(group, fx.aura);
  if (fx.glow && S.figure) F.glow = spiritGlow(S.figure, fx.glow);
  if (fx.sparks) {
    const mat = new THREE.SpriteMaterial({ map: spiritDotTex(), color: fx.sparks.color || '#ffffff', transparent: true, depthWrite: false });
    const pool = Math.min(SPIRIT_FX.sparkMax, Math.ceil((fx.sparks.rate || 0) * SPIRIT_FX.sparkLife));   // all rate shows, no more
    F.sparkSize = fx.sparks.size || 0.12; F.sparkSpread = F.aura ? F.aura.width : 1.2;
    for (let i = 0; i < pool; i++) { const sp = new THREE.Sprite(mat.clone()); sp.visible = false; sp.scale.setScalar(F.sparkSize); group.add(sp); F.sparks.push({ sp, age: 99 }); }
  }
  if (fx.lightning) {   // each bolt a ribbon: a thin bright core in a wider glow, segment by segment
    const L = fx.lightning;
    const core = new THREE.MeshBasicMaterial({ color: '#f4fbff', transparent: true, opacity: 0, depthWrite: false });
    const glow = new THREE.MeshBasicMaterial({ color: L.color || '#bfefff', transparent: true, opacity: 0, depthWrite: false });
    core.userData.base = glow.userData.base = 1;   // spiritDrop disposes them
    F.bolts = Array.from({ length: L.count || 1 }, () => Array.from({ length: SPIRIT_FX.boltSegs }, () => {
      const c = new THREE.Mesh(spiritUnitCyl, core), g = new THREE.Mesh(spiritUnitCyl, glow);
      c.renderOrder = 5; g.renderOrder = 4; group.add(c, g); return [c, g];
    }));
    F.bolt = { core, glow, length: L.length || 2.2 };
  }
  if (fx.afterimage && S.figure && S.clips && S.clips.length && !reduceMotion) {
    const n = fx.afterimage.count || 2, spread = fx.afterimage.spreadDeg ?? 12;
    for (let i = 1; i <= n; i++) {
      const c = SkeletonUtils.clone(S.figure);
      const shells = []; c.traverse((o) => { if (o.isMesh && (o.userData.spiritGlow || (o.material.userData && o.material.userData.outline))) shells.push(o); });
      for (const o of shells) o.parent.remove(o);   // a faint copy draws no outline and no glow
      c.traverse((o) => { if (o.isMesh) o.material = [].concat(o.material).map((m) => { const x = m.clone(); if (x.uniforms) x.uniforms = THREE.UniformsUtils.clone(m.uniforms); return x; })[0]; });
      c.rotation.y = THREE.MathUtils.degToRad(spread * (i % 2 ? i : -i) / 2);
      S.figure.parent.add(c);
      const mixer = new THREE.AnimationMixer(c);
      F.clones.push({ c, mixer, lag: i * 0.06, k: 0.5 / i });
    }
  }
  if (spec.shouts && !reduceMotion) {
    const texts = spiritWords(spec.shouts.texts) || [];
    F.shoutTex = (Array.isArray(texts) ? texts : [texts]).map((t) => spiritShoutTex(String(t), spec.shouts.style));
    F.shoutEvery = spec.shouts.everySec || 0.6;
    for (let i = 0; i < 6 && F.shoutTex.length; i++) {
      const sp = new THREE.Sprite(new THREE.SpriteMaterial({ transparent: true, depthWrite: false })); sp.visible = false; sp.scale.set(0.9, 0.34, 1); group.add(sp);
      F.shouts.push({ sp, age: 99 });
    }
  }
}
function spiritFxTick(R, S, dt, k) {
  const F = S.fx;
  if (!F) return;
  F.t += dt;
  const fx = (S.model.spec || {}).effects || {};
  if (F.aura) spiritAuraTick(F.aura, F.t, k);
  for (const o of F.glow || []) o.material.opacity = o.material.userData.base * k;
  if (reduceMotion) return;
  if (F.sparks.length && fx.sparks.rate) {
    F.next -= dt;
    while (F.next <= 0) {
      F.next += 1 / fx.sparks.rate;
      const s = F.sparks.find((x) => x.age >= SPIRIT_FX.sparkLife);
      if (!s) break;
      s.age = 0; s.sp.position.set((Math.random() - 0.5) * F.sparkSpread, 0.2 + Math.random() * 0.6, -0.4 + (Math.random() - 0.5) * 0.8);
    }
    for (const s of F.sparks) {
      s.age += dt;
      const live = s.age < SPIRIT_FX.sparkLife;
      s.sp.visible = live && k > 0.05;
      if (live) { s.sp.position.y += dt * (fx.sparks.rise || 0.8); s.sp.material.opacity = k * (1 - s.age / SPIRIT_FX.sparkLife);
        s.sp.scale.setScalar(F.sparkSize * (0.7 + 0.3 * Math.sin(s.age * 9 + s.sp.id))); }
    }
  }
  if (F.bolt) {
    F.nextBolt -= dt;
    if (F.nextBolt <= 0) {   // new bolts: each from high on a side of the robot, zigzagging down its length
      F.nextBolt = fx.lightning.everySec || 2.5;
      const step = F.bolt.length / SPIRIT_FX.boltSegs, a = spiritBoltA, b = spiritBoltB;
      F.bolts.forEach((segs, i) => {
        const side = i % 2 ? -1 : 1;
        a.set(side * (0.35 + 0.35 * Math.random()), 0.6 + F.bolt.length, -0.3 + (Math.random() - 0.5) * 0.4);
        for (const [c, g] of segs) {
          b.set(a.x + (Math.random() - 0.5) * 0.5 * step * 2, a.y - step, a.z + (Math.random() - 0.5) * 0.1);
          spiritLimb(c, a, b, 0.014); spiritLimb(g, a, b, 0.045); a.copy(b);
        }
      });
      F.boltAt = F.t;
    }
    const on = F.boltAt !== undefined && F.t - F.boltAt < SPIRIT_FX.boltSec ? k : 0;
    F.bolt.core.opacity = on; F.bolt.glow.opacity = on * 0.45;
  }
  for (const cl of F.clones) {   // the afterimages: the loop a little behind, fainter
    if (!cl.action && S.mixer) {
      const clip = (S.clips || []).find((c) => c.name === (S.names.loop || 'loop'));
      if (clip) { cl.action = cl.mixer.clipAction(clip); cl.action.setLoop(THREE.LoopRepeat, Infinity).play(); cl.mixer.setTime(Math.max(0, (S.mixer.time || 0) - cl.lag)); }
    }
    cl.mixer.update(dt);
    spiritFade(cl.c, k * cl.k);
  }
  if (F.shouts.length) {
    F.nextShout -= dt;
    if (F.nextShout <= 0 && k > 0.5) {
      F.nextShout = F.shoutEvery;
      const s = F.shouts.find((x) => x.age >= SPIRIT_FX.shoutLife);
      if (s) { s.age = 0; s.sp.material.map = F.shoutTex[Math.floor(Math.random() * F.shoutTex.length)]; s.sp.material.needsUpdate = true;
        s.sp.position.set((Math.random() - 0.5) * 1.6, 2.2 + Math.random() * 0.5, -0.6); }
    }
    for (const s of F.shouts) {
      s.age += dt;
      const live = s.age < SPIRIT_FX.shoutLife;
      s.sp.visible = live;
      if (live) { s.sp.position.y += dt * 0.6; s.sp.material.opacity = k * (1 - s.age / SPIRIT_FX.shoutLife); }
    }
  }
}

/* Whether the robot is drawn tall enough to wear a spirit: its height on screen, feet to the tag's point. */
const spiritA = new THREE.Vector3(), spiritB = new THREE.Vector3();
function spiritNear(R) {
  spiritA.copy(R.robot.root.position).project(camera);
  spiritB.copy(R.robot.root.position).addScaledVector(TAG_UP, R.robot.size || 1).project(camera);
  if (spiritA.z > 1 || spiritB.z > 1) return false;
  return Math.abs(spiritA.y - spiritB.y) / 2 * canvas.clientHeight >= SPIRIT.minPx;
}
/* The bubbles aimed at spirits, after the tags (40-scene.js placeRobotTags leaves its columns in TAGS.placed): the
   nearest first, each just above anything placed it would cross — a tag's column or another bubble. */
function spiritPlaceBubbles() {
  const W = canvas.clientWidth, H = canvas.clientHeight, list = [];
  for (const R of robots) {
    const el = R.spirit && R.spirit.bubbleEl;
    if (!el || el.hidden || el.dataset.target !== 'spirit') continue;
    const p = spiritHead(R, R.spirit).project(camera);
    if (p.z > 1 || p.z < -1) { el.style.visibility = 'hidden'; continue; }
    if (!el._size || el._size.text !== el.textContent) el._size = { text: el.textContent, w: el.offsetWidth, h: el.offsetHeight };
    list.push({ el, x: ((p.x + 1) / 2) * W, y: ((1 - p.y) / 2) * H, z: p.z });
  }
  const placed = [...(TAGS.placed || [])];
  for (const it of list.sort((a, b) => a.z - b.z)) {
    const { w, h } = it.el._size, x0 = it.x - w / 2, x1 = it.x + w / 2;
    let bottom = it.y;
    for (let pass = 0; pass < TAGS.maxPasses; pass++) {
      const hit = placed.find((q) => x0 < q.x1 && q.x0 < x1 && bottom - h < q.y1 && q.y0 < bottom);
      if (!hit) break;
      bottom = hit.y0 - SPIRIT.gap;
    }
    placed.push({ x0, x1, y0: bottom - h, y1: bottom });
    it.el.style.visibility = 'visible';
    it.el.style.transform = `translate(${it.x.toFixed(1)}px, ${bottom.toFixed(1)}px) translate(-50%, -100%)`;
  }
}

/* Which spirits draw everything: the SPIRIT.fullFx nearest the camera keep their outline, afterimages and glow, the
   others leave them off (once a frame, after the tags: 40-scene.js). */
const spiritCam = new THREE.Vector3();
function spiritLod() {
  const standing = robots.filter((R) => R.spirit && R.spirit.fx && R.spirit.figure);
  standing.sort((a, b) => camera.position.distanceToSquared(a.robot.root.getWorldPosition(spiritCam))
    - camera.position.distanceToSquared(b.robot.root.getWorldPosition(spiritCam)));
  standing.forEach((R, i) => {
    const full = i < SPIRIT.fullFx, F = R.spirit.fx;
    for (const cl of F.clones) cl.c.visible = full;
    for (const o of F.glow || []) o.visible = full;
    if (R.spirit.full !== full) R.spirit.figure.traverse((o) => { if (o.userData.spiritOutline) o.visible = full; });   // the outline too
    R.spirit.full = full;
  });
}
