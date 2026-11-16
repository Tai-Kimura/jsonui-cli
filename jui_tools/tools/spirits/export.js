// The page export.py drives: it builds one model from its build.js, samples its motion into clips, writes each
// root as a .glb with GLTFExporter, reads every .glb back with the page's own GLTFLoader and draws the two side by
// side to say whether what was written is what was built.
import * as THREE from 'three';
import { GLTFExporter } from 'three/addons/exporters/GLTFExporter.js';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';

const NAME_RE = /^[A-Za-z0-9_-]{1,64}$/;
const EPS = 1e-5;
const SIZE = { w: 320, h: 260 };

function materials(o) {
  return o.material ? (Array.isArray(o.material) ? o.material : [o.material]) : [];
}

// What glTF cannot carry: a Sprite is not written at all, a ShaderMaterial is dropped, a node's visibility is not
// animated. Each is said, with what to use instead.
function checkWritable(root, label, problems) {
  root.traverse((o) => {
    if (o.isSprite) problems.push(`${label}: ${o.name || o.type} is a Sprite (not in glTF: use spirit.json effects, shouts or bubble)`);
    for (const m of materials(o)) {
      if (m.isShaderMaterial) problems.push(`${label}: ${o.name || o.type} has a ShaderMaterial (not in glTF: use a plain material; the look is spirit.json spirit.material)`);
    }
  });
}

// Every node gets a name the clips can point at; the loader keeps only names PropertyBinding leaves alone.
function nameNodes(root, label, problems) {
  const seen = new Set();
  let i = 0;
  root.traverse((o) => {
    if (!o.name) o.name = `${label}_${i++}`;
    if (THREE.PropertyBinding.sanitizeNodeName(o.name) !== o.name) problems.push(`${label}: the node name "${o.name}" has characters a clip cannot point at`);
    if (seen.has(o.name)) problems.push(`${label}: two nodes are named "${o.name}"`);
    seen.add(o.name);
  });
}

function nodesOf(root) {
  const out = [];
  root.traverse((o) => out.push(o));
  return out;
}

// Samples animate(t, phase) for each clip at fps, and keeps a track only for a node that moves.
function sampleClips(model, roots, fps, problems) {
  const out = new Map(roots.map((r) => [r.label, []]));
  for (const [phase, seconds] of Object.entries(model.clips || {})) {
    if (!(seconds > 0)) { problems.push(`clips.${phase}: ${seconds} is not a length in seconds`); continue; }
    const n = Math.max(2, Math.round(seconds * fps) + 1);
    const times = new Float32Array(n);
    for (let i = 0; i < n; i++) times[i] = (seconds * i) / (n - 1);
    const records = roots.map((r) => ({ r, nodes: nodesOf(r.object).map((o) => ({ o, p: [], q: [], s: [], v: new Set() })) }));
    for (let i = 0; i < n; i++) {
      model.animate(times[i], phase);
      for (const rec of records) {
        for (const nd of rec.nodes) {
          const q = nd.o.quaternion.toArray();
          const last = nd.q.length ? nd.q.slice(-4) : null;
          if (last && last[0] * q[0] + last[1] * q[1] + last[2] * q[2] + last[3] * q[3] < 0) q.forEach((v, k) => (q[k] = -v));
          nd.p.push(...nd.o.position.toArray());
          nd.q.push(...q);
          nd.s.push(...nd.o.scale.toArray());
          nd.v.add(nd.o.visible);
        }
      }
    }
    for (const rec of records) {
      const tracks = [];
      const moves = (arr, k) => arr.some((v, i) => Math.abs(v - arr[i % k]) > EPS);
      for (const nd of rec.nodes) {
        if (nd.v.size > 1) problems.push(`${rec.r.label}: ${nd.o.name} shows and hides in clip ${phase} (not in glTF: scale it to 0)`);
        if (moves(nd.p, 3)) tracks.push(new THREE.VectorKeyframeTrack(`${nd.o.name}.position`, times, nd.p));
        if (moves(nd.q, 4)) tracks.push(new THREE.QuaternionKeyframeTrack(`${nd.o.name}.quaternion`, times, nd.q));
        if (moves(nd.s, 3)) tracks.push(new THREE.VectorKeyframeTrack(`${nd.o.name}.scale`, times, nd.s));
      }
      if (tracks.length) out.get(rec.r.label).push(new THREE.AnimationClip(phase, seconds, tracks));
    }
  }
  return out;
}

function toBase64(buffer) {
  const bytes = new Uint8Array(buffer);
  let s = '';
  for (let i = 0; i < bytes.length; i += 0x8000) s += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(s);
}

function stage() {
  const renderer = new THREE.WebGLRenderer({ antialias: false, preserveDrawingBuffer: true });
  renderer.setPixelRatio(1);
  renderer.setSize(SIZE.w, SIZE.h);
  renderer.setClearColor(0x20242c, 1);
  const scene = new THREE.Scene();
  scene.add(new THREE.AmbientLight(0xffffff, 0.8));
  const sun = new THREE.DirectionalLight(0xffffff, 1.6);
  sun.position.set(2, 4, 3);
  scene.add(sun);
  const camera = new THREE.PerspectiveCamera(35, SIZE.w / SIZE.h, 0.01, 100);
  return { renderer, scene, camera };
}

function aim(camera, object) {
  const box = new THREE.Box3().setFromObject(object);
  const center = box.getCenter(new THREE.Vector3());
  const r = Math.max(0.2, box.getSize(new THREE.Vector3()).length() / 2);
  camera.position.set(center.x + r * 1.4, center.y + r * 0.9, center.z + r * 2.6);
  camera.lookAt(center);
}

function shot(st, object) {
  st.scene.add(object);
  object.updateMatrixWorld(true);
  st.renderer.render(st.scene, st.camera);
  st.scene.remove(object);
  const c = document.createElement('canvas');
  c.width = SIZE.w;
  c.height = SIZE.h;
  const g = c.getContext('2d');
  g.drawImage(st.renderer.domElement, 0, 0);
  return { canvas: c, data: g.getImageData(0, 0, SIZE.w, SIZE.h).data };
}

// The share of pixels where a channel differs by more than PIXEL_STEP (the background counts as the same).
const PIXEL_STEP = 24;
function pixelDiff(a, b) {
  let off = 0;
  for (let i = 0; i < a.length; i += 4) {
    if (Math.abs(a[i] - b[i]) > PIXEL_STEP || Math.abs(a[i + 1] - b[i + 1]) > PIXEL_STEP || Math.abs(a[i + 2] - b[i + 2]) > PIXEL_STEP) off++;
  }
  return off / (a.length / 4);
}

// Reads one written .glb back and compares it with what was built: the clips, the node names, and pictures of
// each clip at a quarter, a half and three quarters of it (built: animate; written: the loader's clip on a mixer).
// The worst of the three is the clip's diff; the picture kept is the quarter's.
async function verify(model, root, clips, buffer, st, previews) {
  const problems = [];
  const gltf = await new GLTFLoader().parseAsync(buffer, '');
  const written = new Map(gltf.animations.map((c) => [c.name, c]));
  for (const c of clips) {
    const w = written.get(c.name);
    if (!w) { problems.push(`clip ${c.name} is not in what was written`); continue; }
    if (Math.abs(w.duration - c.duration) > 1e-3) problems.push(`clip ${c.name} is ${w.duration.toFixed(3)} s written, ${c.duration.toFixed(3)} s built`);
    if (w.tracks.length !== c.tracks.length) problems.push(`clip ${c.name} has ${w.tracks.length} tracks written, ${c.tracks.length} built`);
  }
  const names = new Set();
  gltf.scene.traverse((o) => names.add(o.name));
  const missing = nodesOf(root.object).filter((o) => o !== root.object && !names.has(o.name)).map((o) => o.name);
  if (missing.length) problems.push(`nodes not in what was written: ${missing.slice(0, 5).join(', ')}`);
  const diffs = {};
  const rest = Object.keys(model.clips || {}).includes('loop') ? 'loop' : Object.keys(model.clips || {})[0];
  const phases = clips.length ? clips.map((c) => [c.name, [0.25, 0.5, 0.75].map((k) => c.duration * k)]) : [[rest, [0]]];
  for (const [phase, times] of phases) {
    model.animate(0, phase);
    aim(st.camera, root.object);
    const clip = written.get(phase);
    const mixer = new THREE.AnimationMixer(gltf.scene);
    if (clip) mixer.clipAction(clip).play();
    let first = null;
    diffs[phase] = 0;
    for (const t of times) {
      model.animate(t, phase);
      const a = shot(st, root.object);
      mixer.setTime(t);
      const b = shot(st, gltf.scene);
      diffs[phase] = Math.max(diffs[phase], pixelDiff(a.data, b.data));
      if (!first) first = { a, b, t };
    }
    mixer.stopAllAction();
    const { a, b, t } = first;
    const side = document.createElement('canvas');
    side.width = SIZE.w * 2;
    side.height = SIZE.h;
    const g = side.getContext('2d');
    g.drawImage(a.canvas, 0, 0);
    g.drawImage(b.canvas, SIZE.w, 0);
    g.fillStyle = '#ffffff';
    g.font = '12px monospace';
    g.fillText(`built ${phase} ${t.toFixed(2)}s`, 6, 14);
    g.fillText(`written (diff ${diffs[phase].toFixed(4)})`, SIZE.w + 6, 14);
    previews[`${root.label}-${phase}.png`] = side.toDataURL('image/png').split(',')[1];
  }
  return { problems, diffs };
}

window.exportModel = async function exportModel(options) {
  const problems = [];
  const mod = await import('/model/build.js');
  const model = mod.build();
  model.clips = model.clips || mod.clips || {};
  const fps = options.fps || mod.FPS || 30;
  const roots = [];
  if (model.spirit) roots.push({ label: 'spirit', file: 'spirit.glb', object: model.spirit });
  for (const [kind, list] of [['robot', model.parts || []], ['prop', model.props || []]]) {
    for (const p of list) {
      if (!NAME_RE.test(p.name || '')) { problems.push(`${kind} part name "${p.name}" is not A-Z a-z 0-9 _ -`); continue; }
      roots.push({ label: `${kind}-${p.name}`, file: `${kind}-${p.name}.glb`, object: p.object });
    }
  }
  if (!roots.length) problems.push('build() returned nothing to write (spirit, parts or props)');
  if (typeof model.animate !== 'function') model.animate = () => {};
  for (const r of roots) { checkWritable(r.object, r.label, problems); nameNodes(r.object, r.label, problems); }
  const clips = sampleClips(model, roots, fps, problems);
  const rest = Object.keys(model.clips).includes('loop') ? 'loop' : Object.keys(model.clips)[0];
  const st = stage();
  const files = {};
  const report = {};
  const previews = {};
  for (const r of roots) {
    model.animate(0, rest);
    const buffer = await new GLTFExporter().parseAsync(r.object, { binary: true, animations: clips.get(r.label), onlyVisible: false });
    files[r.file] = toBase64(buffer);
    const v = await verify(model, r, clips.get(r.label), buffer, st, previews);
    report[r.file] = { clips: clips.get(r.label).map((c) => c.name), bytes: buffer.byteLength, diffs: v.diffs };
    problems.push(...v.problems.map((p) => `${r.file}: ${p}`));
  }
  st.renderer.dispose();
  return { problems, files, report, previews };
};
window.exportReady = true;
