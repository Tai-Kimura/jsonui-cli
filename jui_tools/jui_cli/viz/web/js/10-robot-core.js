import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { RoundedBoxGeometry } from 'three/addons/geometries/RoundedBoxGeometry.js';

const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
const SPEED = reduceMotion ? 0.35 : 1;

const FONT_DISPLAY = '"Dela Gothic One", "Hiragino Sans", "Yu Gothic", sans-serif';
const FONT_BODY = '"BIZ UDPGothic", "Hiragino Sans", "Yu Gothic", sans-serif';
const FONT_MONO = '"JetBrains Mono", ui-monospace, Menlo, monospace';

const ROLES = {
  main: { name: 'メイン', color: '#0ea5e9', pill: '#0369a1' },   // sky blue (2.3.5, requester 10-19: 「スカイブルーにしようか」; it was orange, beside the subagents' orange coveralls)
  // `pill` (2.3.6, ticket 2026-10-20-jui-viz-main-pill-text-contrast): a role's pills (over the robot, in the panels, on the
  // boards) take it in place of `color`, white text on it. Main's is one step darker (#0369a1, white 5.93:1); its body stays #0ea5e9.
  // define / ground / navigation / test / other the same (requester 10-20: 「全部直す」): each the body's hue, darker, white ≥ 4.7:1.
  define: { name: 'define', color: '#7d5cff', pill: '#7552ff' },
  ground: { name: 'ground', color: '#b07a52', pill: '#996946' },
  implement: { name: 'implement', color: '#3b5bdb' },   // indigo (2.3.5): #2f80ed sat ΔE2000 14.6 from the main sky blue, side by side in the panel
  navigation: { name: 'navigation', color: '#10a693', pill: '#0c8172' },
  test: { name: 'test', color: '#3fae4a', pill: '#2f8338' },
  debug: { name: 'debug', color: '#f0b400' },
  other: { name: 'その他', color: '#8a9bb0', pill: '#60748e' },
};
/* Whatever is filled with a role's colour and has text on it (pills, the talk's marks, a phone's header and button) takes
   pillBg, with pillInk (20-core.js) for the text; the robot's own parts keep ROLES[role].color. */
const pillBg = (role) => ROLES[role].pill || ROLES[role].color;
const COL = {
  shell: '#e8ecf3', limb: '#394150', screen: '#0f1830', eye: '#a6fbff',
  band: '#fffdf7', bandInk: '#d62839', wood: '#c99f73', woodDark: '#9e7752',
  laptop: '#c9d0db', phone: '#1f2532',
};
/* A subagent's work clothes (2.3.5, requester 10-19: "サブエージェントは格好を作業着っぽい感じにできる？", "さいずも0.8くらいに
   して", "作業着の服装の感じはアメリカの囚人服っぽいオレンジがいいな"): a bright orange coverall (body, sleeves, legs) with a
   reflective stripe, a patch of its role's colour on the chest (a white rim and a navy edge, readable on the orange),
   a work cap; the whole robot SUB_SIZE of a main one. The orange is kept apart from ROLES.main (ΔE2000 ≥ 10; the e2e
   measures it). */
const WEAR = { overall: '#ff8c1a', stripe: '#e8edf3', brim: '#c25e00', rim: '#ffffff', edge: '#1f2a44' };
const SUB_SIZE = 0.8;
const LAMP = { idle: '#8fa3bf', busy: '#35d07f', think: '#8fe0b4', bg: '#4cc3d9', waiting: '#ffb020', done: '#35d07f', off: '#2a3a30' };
const STATES = {
  idle: { name: '待機', lamp: 'idle', face: 'normal' },
  thinking: { name: '考え中', lamp: 'think', face: 'normal' },
  background: { name: '裏で作業中', lamp: 'bg', face: 'normal' },   // waiting on background work: lit, watching its screen (10-18)
  typing: { name: '入力', lamp: 'busy', face: 'focus' },
  reading: { name: '読む', lamp: 'busy', face: 'normal' },
  command: { name: 'コマンド', lamp: 'busy', face: 'focus' },
  phone: { name: 'スマホ', lamp: 'busy', face: 'focus' },
  waiting: { name: '許可待ち', lamp: 'waiting', face: 'wide' },
  carry: { name: '運ぶ', lamp: 'busy', face: 'normal' },
  stroll: { name: '歩く', lamp: 'idle', face: 'normal' },   // to and from play (10-18): no papers; the lamp is the real state's
  done: { name: '完了', lamp: 'done', face: 'happy' },
};
const LAMP_TEXT = { idle: '青灰（待機）', busy: '緑（作業中）', think: '淡い緑のゆっくり点滅（考え中）', waiting: '黄（許可待ち）', done: '緑の点滅（完了）', bg: '水色（裏で作業中）' };

const HIPS_Y = 0.36;
const HEAD = { w: 1.1, h: 0.9, d: 0.92, r: 0.17 };
const CAP = { w: 0.92, h: 0.18, d: 0.82, y: HEAD.h + 0.06 };   // the work cap's crown, sitting on the head (head space)
const BAND = { y: 0.645, h: 0.17, t: 0.028 };
const LOOK = new THREE.Vector3(0, 1.25, 0.5);
const UP = new THREE.Vector3(0, 1, 0);

/* ---------- canvas helpers ---------- */
let maxAniso = 1;
function makeCanvas(w, h) { const c = document.createElement('canvas'); c.width = w; c.height = h; return c; }
function texFrom(canvas) { const t = new THREE.CanvasTexture(canvas); t.colorSpace = THREE.SRGBColorSpace; t.anisotropy = maxAniso; return t; }
function rr(ctx, x, y, w, h, r) {
  r = Math.min(r, w / 2, h / 2);
  ctx.beginPath();
  ctx.moveTo(x + r, y);
  ctx.arcTo(x + w, y, x + w, y + h, r);
  ctx.arcTo(x + w, y + h, x, y + h, r);
  ctx.arcTo(x, y + h, x, y, r);
  ctx.arcTo(x, y, x + w, y, r);
  ctx.closePath();
}

const gradientMap = (() => {
  const t = new THREE.DataTexture(new Uint8Array([105, 185, 255]), 3, 1, THREE.RedFormat);
  t.minFilter = THREE.NearestFilter; t.magFilter = THREE.NearestFilter; t.generateMipmaps = false; t.needsUpdate = true;
  return t;
})();
const toon = (color, extra = {}) => new THREE.MeshToonMaterial({ color, gradientMap, ...extra });

/* ---------- headband geometry: a smooth wall around the head, u runs left to right across the front ---------- */
function bandOutline(hw, hd, r, seg = 10) {
  const pts = [];
  const push = (x, z, nx, nz) => pts.push({ x, z, nx, nz });
  const cx = hw - r, cz = hd - r;
  const arc = (ox, oz, a0, a1) => {
    for (let i = 0; i <= seg; i++) { const a = a0 + (a1 - a0) * (i / seg); const c = Math.cos(a), s = Math.sin(a); push(ox + c * r, oz + s * r, c, s); }
  };
  push(0, -hd, 0, -1);
  push(-cx, -hd, 0, -1);
  arc(-cx, -cz, -Math.PI / 2, -Math.PI);
  push(-hw, cz, -1, 0);
  arc(-cx, cz, Math.PI, Math.PI / 2);
  push(cx, hd, 0, 1);
  arc(cx, cz, Math.PI / 2, 0);
  push(hw, -cz, 1, 0);
  arc(cx, -cz, 0, -Math.PI / 2);
  push(0, -hd, 0, -1);
  return pts;
}
function makeBandWall() {
  const hw = HEAD.w / 2 + BAND.t, hd = HEAD.d / 2 + BAND.t, r = HEAD.r + BAND.t, h = BAND.h / 2;
  const pts = bandOutline(hw, hd, r);
  const lens = [0];
  let total = 0;
  for (let i = 1; i < pts.length; i++) { total += Math.hypot(pts[i].x - pts[i - 1].x, pts[i].z - pts[i - 1].z); lens.push(total); }
  const pos = [], nor = [], uv = [], idx = [];
  pts.forEach((p, i) => {
    const u = lens[i] / total;
    pos.push(p.x, -h, p.z, p.x, h, p.z);
    nor.push(p.nx, 0, p.nz, p.nx, 0, p.nz);
    uv.push(u, 0, u, 1);
  });
  for (let i = 0; i < pts.length - 1; i++) { const b0 = i * 2, t0 = b0 + 1, b1 = b0 + 2, t1 = b0 + 3; idx.push(b0, b1, t1, b0, t1, t0); }
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
  g.setAttribute('normal', new THREE.Float32BufferAttribute(nor, 3));
  g.setAttribute('uv', new THREE.Float32BufferAttribute(uv, 2));
  g.setIndex(idx);
  g.userData.frontFraction = (2 * (hw - r)) / total;
  g.userData.perimeter = total;
  return g;
}
function roundedRect(PathType, hw, hd, r) {
  const p = new PathType();
  p.moveTo(-hw + r, -hd);
  p.lineTo(hw - r, -hd);
  p.absarc(hw - r, -hd + r, r, -Math.PI / 2, 0, false);
  p.lineTo(hw, hd - r);
  p.absarc(hw - r, hd - r, r, 0, Math.PI / 2, false);
  p.lineTo(-hw + r, hd);
  p.absarc(-hw + r, hd - r, r, Math.PI / 2, Math.PI, false);
  p.lineTo(-hw, -hd + r);
  p.absarc(-hw + r, -hd + r, r, Math.PI, Math.PI * 1.5, false);
  return p;
}
function makeBandCap() {
  const shape = roundedRect(THREE.Shape, HEAD.w / 2 + BAND.t, HEAD.d / 2 + BAND.t, HEAD.r + BAND.t);
  shape.holes.push(roundedRect(THREE.Path, HEAD.w / 2 - 0.01, HEAD.d / 2 - 0.01, HEAD.r - 0.01));
  const g = new THREE.ShapeGeometry(shape, 10);
  g.rotateX(-Math.PI / 2);
  g.translate(0, BAND.h / 2, 0);
  return g;
}

/* ---------- static drawings ---------- */
function drawKeys(c) {
  const ctx = c.getContext('2d');
  ctx.fillStyle = '#4a5363'; ctx.fillRect(0, 0, c.width, c.height);
  const cols = 12, rows = 4, pad = 6;
  const kw = (c.width - pad * (cols + 1)) / cols, kh = (c.height - pad * (rows + 1)) / rows;
  ctx.fillStyle = '#e8ecf2';
  for (let r = 0; r < rows; r++) for (let k = 0; k < cols; k++) { rr(ctx, pad + k * (kw + pad), pad + r * (kh + pad), kw, kh, 3); ctx.fill(); }
  return c;
}
function drawCode(c) {
  const ctx = c.getContext('2d');
  ctx.fillStyle = '#14203a'; ctx.fillRect(0, 0, c.width, c.height);
  const colors = ['#7ef9ff', '#ffd166', '#ff8fab', '#9ad57a', '#c3cbe0'];
  let seed = 7;
  const rnd = () => (seed = (seed * 9301 + 49297) % 233280) / 233280;
  for (let y = 14; y < c.height - 8; y += 13) {
    let x = 12 + Math.floor(rnd() * 3) * 14;
    const n = 1 + Math.floor(rnd() * 3);
    for (let i = 0; i < n; i++) { const w = 18 + rnd() * 60; ctx.fillStyle = colors[Math.floor(rnd() * colors.length)]; ctx.fillRect(x, y, w, 6); x += w + 8; }
  }
  return c;
}
function drawShadow(c) {
  const ctx = c.getContext('2d');
  const g = ctx.createRadialGradient(64, 64, 4, 64, 64, 62);
  g.addColorStop(0, 'rgba(15, 25, 45, 0.34)');
  g.addColorStop(0.6, 'rgba(15, 25, 45, 0.16)');
  g.addColorStop(1, 'rgba(15, 25, 45, 0)');
  ctx.fillStyle = g; ctx.fillRect(0, 0, 128, 128);
  return c;
}
function drawGear(c) {
  const ctx = c.getContext('2d');
  ctx.translate(64, 64);
  ctx.fillStyle = '#9fb1c9';
  for (let i = 0; i < 9; i++) { ctx.save(); ctx.rotate((i / 9) * Math.PI * 2); rr(ctx, -9, -58, 18, 22, 4); ctx.fill(); ctx.restore(); }
  ctx.beginPath(); ctx.arc(0, 0, 42, 0, Math.PI * 2); ctx.fill();
  ctx.globalCompositeOperation = 'destination-out';
  ctx.beginPath(); ctx.arc(0, 0, 16, 0, Math.PI * 2); ctx.fill();
  ctx.globalCompositeOperation = 'source-over';
  return c;
}
function drawChest(c) {
  const ctx = c.getContext('2d');
  ctx.clearRect(0, 0, c.width, c.height);
  rr(ctx, 4, 4, c.width - 8, c.height - 8, 20); ctx.fillStyle = '#e3e8f0'; ctx.fill();
  ctx.lineWidth = 4; ctx.strokeStyle = '#c3ccd9'; ctx.stroke();
  ctx.fillStyle = '#394150'; ctx.font = `700 50px ${FONT_MONO}`; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
  ctx.fillText('{ }', c.width / 2, c.height / 2 + 2);
}
function drawAlert(c) {
  const ctx = c.getContext('2d');
  ctx.clearRect(0, 0, c.width, c.height);
  ctx.fillStyle = '#ffffff'; ctx.strokeStyle = '#1d2330'; ctx.lineWidth = 6; ctx.lineJoin = 'round';
  ctx.beginPath(); ctx.moveTo(52, 128); ctx.lineTo(30, 170); ctx.lineTo(88, 136); ctx.closePath(); ctx.fill(); ctx.stroke();
  ctx.beginPath(); ctx.arc(80, 74, 66, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
  ctx.beginPath(); ctx.moveTo(56, 124); ctx.lineTo(37, 161); ctx.lineTo(83, 133); ctx.closePath(); ctx.fill();
  ctx.fillStyle = '#f0a000'; ctx.font = `96px ${FONT_DISPLAY}`; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
  ctx.fillText('!', 80, 80);
}
function drawCover(c) {
  const ctx = c.getContext('2d');
  ctx.fillStyle = '#23406b'; ctx.fillRect(0, 0, c.width, c.height);
  ctx.strokeStyle = 'rgba(255, 255, 255, 0.35)'; ctx.lineWidth = 3; ctx.strokeRect(10, 10, c.width - 20, c.height - 20);
  ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
  ctx.fillStyle = '#ffd166'; ctx.font = `700 34px ${FONT_MONO}`; ctx.fillText('{ }', c.width / 2, 58);
  ctx.fillStyle = '#ffffff'; ctx.font = `30px ${FONT_DISPLAY}`; ctx.fillText('仕様書', c.width / 2, 112);
  ctx.fillStyle = 'rgba(255, 255, 255, 0.8)'; ctx.font = `700 18px ${FONT_MONO}`; ctx.fillText('Login', c.width / 2, 150);
}

/* ---------- per-robot drawings ---------- */
function drawFace(ctx, mode, tint = null) {
  const W = ctx.canvas.width, H = ctx.canvas.height;
  ctx.clearRect(0, 0, W, H);
  rr(ctx, 3, 3, W - 6, H - 6, 34); ctx.fillStyle = COL.screen; ctx.fill();
  if (tint && tint[3] > 0) { ctx.fillStyle = `rgba(${tint[0]}, ${tint[1]}, ${tint[2]}, ${tint[3]})`; ctx.fill(); }   // heavy work: red or blue
  const sheen = ctx.createLinearGradient(0, 0, 0, H);
  sheen.addColorStop(0, 'rgba(120, 230, 255, 0.14)'); sheen.addColorStop(0.55, 'rgba(120, 230, 255, 0)');
  ctx.fillStyle = sheen; ctx.fill();
  const cx = W / 2, ey = 56, dx = 54;
  ctx.save();
  ctx.shadowColor = 'rgba(94, 242, 255, 0.9)'; ctx.shadowBlur = 16;
  ctx.fillStyle = COL.eye; ctx.strokeStyle = COL.eye; ctx.lineCap = 'round'; ctx.lineJoin = 'round';
  for (const side of [-1, 1]) {
    const x = cx + side * dx;
    if (mode === 'normal') { rr(ctx, x - 15, ey - 24, 30, 48, 15); ctx.fill(); }
    else if (mode === 'blink') { rr(ctx, x - 18, ey - 3, 36, 7, 3.5); ctx.fill(); }
    else if (mode === 'focus') { rr(ctx, x - 19, ey - 8, 38, 17, 8); ctx.fill(); }
    else if (mode === 'happy') { ctx.lineWidth = 10; ctx.beginPath(); ctx.arc(x, ey + 12, 17, Math.PI * 1.15, Math.PI * 1.85); ctx.stroke(); }
    else if (mode === 'wide') { ctx.beginPath(); ctx.arc(x, ey, 22, 0, Math.PI * 2); ctx.fill(); }
    else if (mode === 'tired') { rr(ctx, x - 16, ey - 2, 32, 22, 9); ctx.fill(); ctx.fillStyle = COL.screen; ctx.fillRect(x - 18, ey - 6, 36, 9); ctx.fillStyle = COL.eye; }
    else if (mode === 'fired') {                          // fired up: narrowed eyes under brows slanted to the middle
      rr(ctx, x - 19, ey - 4, 38, 17, 8); ctx.fill();
      ctx.lineWidth = 8; ctx.beginPath(); ctx.moveTo(x - side * 22, ey - 24); ctx.lineTo(x + side * 20, ey - 12); ctx.stroke();
    } else if (mode === 'drained') {                      // drained: small eyes sunk low, looking down
      ctx.beginPath(); ctx.arc(x, ey + 12, 8, 0, Math.PI * 2); ctx.fill();
    } else if (mode === 'whistle') {                      // blowing the whistle: eyes squeezed shut with the effort
      ctx.lineWidth = 9; ctx.beginPath();                 // > <
      ctx.moveTo(x + side * 17, ey - 12); ctx.lineTo(x - side * 5, ey); ctx.lineTo(x + side * 17, ey + 12); ctx.stroke();
    }
  }
  ctx.lineWidth = 6; ctx.beginPath();
  if (mode === 'whistle') { /* the whistle covers the mouth */ }
  else if (mode === 'fired') { ctx.moveTo(cx - 14, 96); ctx.lineTo(cx + 14, 96); }   // a set jaw
  else if (mode === 'drained') { ctx.moveTo(cx - 16, 98); ctx.quadraticCurveTo(cx - 8, 90, cx, 98); ctx.quadraticCurveTo(cx + 8, 106, cx + 16, 98); }   // a wobbly mouth
  else if (mode === 'happy') ctx.arc(cx, 86, 14, Math.PI * 0.1, Math.PI * 0.9);
  else if (mode === 'wide') ctx.arc(cx, 98, 7, 0, Math.PI * 2);
  else if (mode === 'focus') { ctx.moveTo(cx - 9, 97); ctx.lineTo(cx + 9, 97); }
  else ctx.arc(cx, 86, 10, Math.PI * 0.2, Math.PI * 0.8);
  ctx.stroke();
  ctx.restore();
  if (mode === 'tired') {                                  // bags under the eyes
    ctx.strokeStyle = 'rgba(170, 120, 255, 0.85)'; ctx.lineWidth = 4;
    for (const side of [-1, 1]) { ctx.beginPath(); ctx.arc(cx + side * dx, ey + 26, 15, Math.PI * 0.15, Math.PI * 0.85); ctx.stroke(); }
  }
  if (mode === 'drained') {                              // gloom lines down the top of the screen (青ざめ), not the bags of 8 hours
    ctx.strokeStyle = 'rgba(150, 200, 255, 0.85)'; ctx.lineWidth = 4;
    for (let i = 0; i < 7; i++) { const x = cx - 78 + i * 26; ctx.beginPath(); ctx.moveTo(x, 12); ctx.lineTo(x, 12 + (i % 2 ? 22 : 30)); ctx.stroke(); }
  }
  if (mode === 'wide') { ctx.fillStyle = COL.screen; for (const side of [-1, 1]) { ctx.beginPath(); ctx.arc(cx + side * dx + 7, ey - 8, 6, 0, Math.PI * 2); ctx.fill(); } }
  ctx.fillStyle = 'rgba(255, 120, 160, 0.42)';
  for (const side of [-1, 1]) { ctx.beginPath(); ctx.ellipse(cx + side * 96, 88, 15, 8, 0, 0, Math.PI * 2); ctx.fill(); }
}
function drawBand(r) {
  const c = r.bandCanvas, ctx = c.getContext('2d'), W = c.width, H = c.height;
  ctx.clearRect(0, 0, W, H);
  ctx.fillStyle = COL.band; ctx.fillRect(0, 0, W, H);
  ctx.fillStyle = 'rgba(40, 50, 70, 0.05)';
  for (let y = 5; y < H - 4; y += 7) ctx.fillRect(0, y, W, 1.5);
  const shade = ctx.createLinearGradient(0, H * 0.6, 0, H);
  shade.addColorStop(0, 'rgba(40, 50, 70, 0)'); shade.addColorStop(1, 'rgba(40, 50, 70, 0.12)');
  ctx.fillStyle = shade; ctx.fillRect(0, 0, W, H);
  ctx.fillStyle = 'rgba(40, 50, 70, 0.14)'; ctx.fillRect(0, 3, W, 2); ctx.fillRect(0, H - 5, W, 2);
  const text = (r.label || '').trim() || '··';
  const maxW = W * S.geo.bandWall.userData.frontFraction * 0.88;
  let size = H * 0.8;
  const setFont = () => { ctx.font = `${size.toFixed(1)}px ${FONT_DISPLAY}`; if ('letterSpacing' in ctx) ctx.letterSpacing = `${Math.round(size * 0.05)}px`; };
  setFont();
  const w = ctx.measureText(text).width;
  if (w > maxW) { size *= maxW / w; setFont(); }
  ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
  ctx.fillStyle = COL.bandInk; ctx.strokeStyle = COL.bandInk; ctx.lineJoin = 'round'; ctx.lineWidth = Math.max(1.5, size * 0.05);
  const y = H / 2 + size * 0.04;
  ctx.strokeText(text, W / 2, y); ctx.fillText(text, W / 2, y);
  r.bandTex.needsUpdate = true;
}
function drawLogo(r) {
  const ctx = r.logoCanvas.getContext('2d');
  ctx.clearRect(0, 0, 96, 64);
  ctx.fillStyle = ROLES[r.role].color; ctx.font = `700 40px ${FONT_MONO}`; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
  ctx.fillText('{ }', 48, 34);
  r.logoTex.needsUpdate = true;
}
function drawPhoneUI(r, t) {
  const c = r.phoneCanvas, ctx = c.getContext('2d'), W = c.width;
  const accent = pillBg(r.role), ink = pillInk(r.role);   // the header and the button carry text
  ctx.clearRect(0, 0, c.width, c.height);
  ctx.fillStyle = '#ffffff'; ctx.strokeStyle = '#1d2330'; ctx.lineWidth = 5; ctx.lineJoin = 'round';
  ctx.beginPath(); ctx.moveTo(44, 360); ctx.lineTo(16, 396); ctx.lineTo(84, 362); ctx.closePath(); ctx.fill(); ctx.stroke();
  rr(ctx, 6, 6, W - 12, 360, 28); ctx.fill(); ctx.stroke();
  ctx.beginPath(); ctx.moveTo(48, 355); ctx.lineTo(25, 387); ctx.lineTo(79, 358); ctx.closePath(); ctx.fill();
  const sx = 24, sy = 24, sw = 192, sh = 320;
  ctx.save();
  rr(ctx, sx, sy, sw, sh, 18); ctx.clip();
  ctx.fillStyle = '#f1f4f9'; ctx.fillRect(sx, sy, sw, sh);
  ctx.fillStyle = accent; ctx.fillRect(sx, sy, sw, 64);
  ctx.textAlign = 'left'; ctx.textBaseline = 'alphabetic';
  ctx.fillStyle = ink; ctx.font = `700 11px ${FONT_MONO}`; ctx.fillText('9:41', sx + 12, sy + 17); ctx.fillRect(sx + sw - 32, sy + 8, 18, 9);
  ctx.fillStyle = ink; ctx.font = `700 19px ${FONT_BODY}`; ctx.fillText('ログイン', sx + 14, sy + 50);
  for (let i = 0; i < 2; i++) {
    const y = sy + 84 + i * 52;
    ctx.fillStyle = '#7a879b'; ctx.fillRect(sx + 14, y, 56 + i * 20, 7);
    rr(ctx, sx + 14, y + 12, sw - 28, 30, 8); ctx.fillStyle = '#ffffff'; ctx.fill(); ctx.strokeStyle = '#cfd8e6'; ctx.lineWidth = 2; ctx.stroke();
    ctx.fillStyle = '#394150';
    if (i === 0) { ctx.font = `500 12px ${FONT_MONO}`; ctx.fillText('test@example.com', sx + 22, y + 32); }
    else for (let k = 0; k < 6; k++) { ctx.beginPath(); ctx.arc(sx + 26 + k * 12, y + 27, 3.5, 0, Math.PI * 2); ctx.fill(); }
  }
  const by = sy + 200;
  rr(ctx, sx + 14, by, sw - 28, 40, 10); ctx.fillStyle = accent; ctx.fill();
  ctx.fillStyle = ink; ctx.font = `700 15px ${FONT_BODY}`; ctx.textAlign = 'center'; ctx.fillText('ログイン', sx + sw / 2, by + 26);
  const ph = (t * 0.7) % 1;
  ctx.beginPath(); ctx.arc(sx + sw / 2 + 24, by + 20, 6 + ph * 30, 0, Math.PI * 2);
  ctx.strokeStyle = `rgba(255, 255, 255, ${(0.9 * (1 - ph)).toFixed(2)})`; ctx.lineWidth = 4; ctx.stroke();
  for (let i = 0; i < 2; i++) { rr(ctx, sx + 14, by + 58 + i * 26, sw - 28, 18, 5); ctx.fillStyle = '#dde4ef'; ctx.fill(); }
  ctx.restore();
  ctx.fillStyle = '#4b5c76'; ctx.font = `700 11px ${FONT_MONO}`; ctx.textAlign = 'center'; ctx.textBaseline = 'alphabetic';
  ctx.fillText(`iOS Simulator · ${r.label}`, W / 2, 359);
  r.phoneTex.needsUpdate = true; r.phoneScreenTex.needsUpdate = true;
}
function drawTerminal(r, t) {
  const c = r.termCanvas, ctx = c.getContext('2d'), W = c.width, H = c.height;
  ctx.clearRect(0, 0, W, H);
  rr(ctx, 6, 6, W - 12, H - 12, 18); ctx.fillStyle = 'rgba(9, 32, 58, 0.86)'; ctx.fill();
  ctx.lineWidth = 3; ctx.strokeStyle = 'rgba(126, 249, 255, 0.9)'; ctx.stroke();
  ['#ff6b6b', '#ffd166', '#06d6a0'].forEach((col, i) => { ctx.fillStyle = col; ctx.beginPath(); ctx.arc(28 + i * 20, 28, 6, 0, Math.PI * 2); ctx.fill(); });
  ctx.textAlign = 'left'; ctx.textBaseline = 'alphabetic';
  ctx.font = `700 21px ${FONT_MONO}`; ctx.fillStyle = '#c9fbff';
  const cmd = '$ jui build';
  ctx.fillText(cmd, 24, 78);
  if (Math.floor(t * 2) % 2 === 0) ctx.fillRect(24 + ctx.measureText(`${cmd} `).width, 61, 11, 21);
  const prog = (t * 0.2) % 1;
  const doneCount = Math.min(3, Math.floor(prog * 4));
  ctx.font = `500 18px ${FONT_MONO}`;
  ['Login.json', 'Home.json', 'Settings.json'].forEach((f, i) => {
    ctx.fillStyle = i < doneCount ? '#86ffb4' : 'rgba(201, 251, 255, 0.5)';
    ctx.fillText(`${i < doneCount ? '✓' : '·'} ${f}`, 24, 114 + i * 28);
  });
  const bx = 24, by = H - 46, bw = W - 48, bh = 14;
  rr(ctx, bx, by, bw, bh, 7); ctx.fillStyle = 'rgba(126, 249, 255, 0.2)'; ctx.fill();
  rr(ctx, bx, by, Math.max(bh, bw * prog), bh, 7); ctx.fillStyle = '#7ef9ff'; ctx.fill();
  r.termTex.needsUpdate = true;
}

/* ---------- shared assets ---------- */
const S = {};
const fontRedraws = [];
function initShared() {
  S.geo = {
    head: new RoundedBoxGeometry(HEAD.w, HEAD.h, HEAD.d, 5, HEAD.r),
    torso: new RoundedBoxGeometry(0.74, 0.56, 0.54, 5, 0.16),
    pelvis: new RoundedBoxGeometry(0.46, 0.12, 0.36, 3, 0.05),
    arm: new THREE.CapsuleGeometry(0.075, 0.2, 6, 14),
    hand: new THREE.SphereGeometry(0.095, 24, 16),
    shoulder: new THREE.SphereGeometry(0.095, 24, 16),
    leg: new THREE.CapsuleGeometry(0.08, 0.12, 6, 14),
    foot: new RoundedBoxGeometry(0.2, 0.1, 0.3, 3, 0.045),
    neck: new THREE.CylinderGeometry(0.1, 0.11, 0.1, 20),
    ear: new THREE.CylinderGeometry(0.15, 0.15, 0.08, 32),
    earCap: new THREE.CylinderGeometry(0.085, 0.085, 0.1, 24),
    rod: new THREE.CylinderGeometry(0.014, 0.014, 0.2, 8),
    ball: new THREE.SphereGeometry(0.05, 18, 12),
    face: new THREE.PlaneGeometry(0.76, 0.38),
    chest: new THREE.PlaneGeometry(0.32, 0.2),
    lamp: new THREE.SphereGeometry(0.036, 16, 12),
    bandWall: makeBandWall(),
    bandCap: makeBandCap(),
    knot: new RoundedBoxGeometry(0.13, 0.12, 0.07, 2, 0.03),
    tail: new THREE.PlaneGeometry(0.085, 0.34).translate(0, -0.17, 0),
    stage: new THREE.CylinderGeometry(0.98, 1.02, 0.06, 64),
    ring: new THREE.RingGeometry(0.9, 0.925, 72),
    shadow: new THREE.PlaneGeometry(1.25, 1.25),
    deskTop: new RoundedBoxGeometry(1.0, 0.05, 0.55, 2, 0.015),
    deskLeg: new THREE.CylinderGeometry(0.025, 0.025, 0.5, 10),
    laptopBase: new RoundedBoxGeometry(0.62, 0.025, 0.36, 2, 0.008),
    keys: new THREE.PlaneGeometry(0.52, 0.2),
    laptopLid: new RoundedBoxGeometry(0.62, 0.4, 0.022, 2, 0.008),
    lidLogo: new THREE.PlaneGeometry(0.17, 0.11),
    lidScreen: new THREE.PlaneGeometry(0.56, 0.35),
    bookPanel: new THREE.BoxGeometry(0.21, 0.29, 0.016),
    bookPages: new THREE.BoxGeometry(0.195, 0.27, 0.018),
    bookCover: new THREE.PlaneGeometry(0.2, 0.28),
    phoneBody: new RoundedBoxGeometry(0.2, 0.36, 0.03, 2, 0.028),
    phoneScreen: new THREE.PlaneGeometry(0.18, 0.3),
    phoneCam: new RoundedBoxGeometry(0.06, 0.06, 0.012, 2, 0.01),
    phoneLogo: new THREE.PlaneGeometry(0.09, 0.06),
    term: new THREE.PlaneGeometry(0.74, 0.5),
    projector: new THREE.CylinderGeometry(0.1, 0.12, 0.05, 24),
    beam: new THREE.CylinderGeometry(0.3, 0.05, 0.68, 24, 1, true),
    sheet: new RoundedBoxGeometry(0.34, 0.03, 0.24, 1, 0.006),
    confetti: new THREE.PlaneGeometry(0.035, 0.06),
    stripe: new THREE.BoxGeometry(0.77, 0.045, 0.57),
    patch: new THREE.PlaneGeometry(0.13, 0.1),
    patchRim: new THREE.PlaneGeometry(0.16, 0.13),
    patchEdge: new THREE.PlaneGeometry(0.185, 0.155),
    capCrown: new RoundedBoxGeometry(CAP.w, CAP.h, CAP.d, 4, 0.09),
    capBrim: new RoundedBoxGeometry(0.74, 0.035, 0.32, 2, 0.015),
  };
  S.tex = {
    chest: texFrom(makeCanvas(160, 100)),
    keys: texFrom(drawKeys(makeCanvas(256, 100))),
    code: texFrom(drawCode(makeCanvas(256, 160))),
    shadow: texFrom(drawShadow(makeCanvas(128, 128))),
    alert: texFrom(makeCanvas(160, 176)),
    gear: texFrom(drawGear(makeCanvas(128, 128))),
    cover: texFrom(makeCanvas(140, 196)),
  };
  const redrawFontTextures = () => {
    drawChest(S.tex.chest.image); S.tex.chest.needsUpdate = true;
    drawAlert(S.tex.alert.image); S.tex.alert.needsUpdate = true;
    drawCover(S.tex.cover.image); S.tex.cover.needsUpdate = true;
  };
  redrawFontTextures();
  fontRedraws.push(redrawFontTextures);
  S.mat = {
    shell: toon(COL.shell),
    limb: toon(COL.limb),
    band: toon(COL.band),
    tail: toon(COL.band, { side: THREE.DoubleSide }),
    chest: toon('#ffffff', { map: S.tex.chest, transparent: true, alphaTest: 0.5 }),
    wood: toon(COL.wood),
    woodDark: toon(COL.woodDark),
    laptop: toon(COL.laptop),
    phone: toon(COL.phone),
    keys: toon('#ffffff', { map: S.tex.keys }),
    code: new THREE.MeshBasicMaterial({ map: S.tex.code }),
    shadow: new THREE.MeshBasicMaterial({ map: S.tex.shadow, transparent: true, depthWrite: false }),
    pages: toon('#fbf8ef'),
    bookShell: toon('#23406b'),
    cover: toon('#ffffff', { map: S.tex.cover }),
    alert: new THREE.SpriteMaterial({ map: S.tex.alert, transparent: true }),
    gear: new THREE.SpriteMaterial({ map: S.tex.gear, transparent: true }),
    projector: toon('#3a4252'),
    beam: new THREE.MeshBasicMaterial({ color: '#7ef9ff', transparent: true, opacity: 0.12, side: THREE.DoubleSide, depthWrite: false, blending: THREE.AdditiveBlending }),
    sheets: ['#ffffff', '#f4efe3', '#e8f0fb', '#fff6dc'].map((c) => toon(c)),
    overall: toon(WEAR.overall),
    stripe: toon(WEAR.stripe),
    brim: toon(WEAR.brim),
    rim: new THREE.MeshBasicMaterial({ color: WEAR.rim }),
    edge: new THREE.MeshBasicMaterial({ color: WEAR.edge }),
    confetti: ['#d62839', '#ffb020', '#35d07f', '#2f80ed', '#7d5cff', '#ff7a3d'].map((c) => new THREE.MeshBasicMaterial({ color: c, side: THREE.DoubleSide })),
  };
}

/* ---------- the robot ---------- */
function faceToward(obj, target) {
  const m = new THREE.Matrix4().lookAt(target, obj.position, UP);
  obj.quaternion.setFromRotationMatrix(m);
}
function createRobot({ label = 'a0', role = 'main', state = 'idle', seed = 0, furnished = false, sub = false }) {
  const g = S.geo, m = S.mat;
  const coat = sub ? m.overall : null;   // a subagent: the coverall over body, sleeves and legs
  const r = { label, role, state, prev: state, blend: 1, seed, props: {}, faceMode: '', nextBlink: 1 + (seed % 2), blinkEnd: 0, termAt: 0, phoneAt: 0,
    tired: false, needDrink: false, drinks: 0, gesture: null, hand: null, heavy: false, sweat: null,
    look: null, tint: null, whistle: null, pipi: null };
  r.furnished = furnished;
  r.sub = sub; r.size = sub ? SUB_SIZE : 1;
  r.accent = toon(ROLES[role].color);
  r.lampMat = new THREE.MeshBasicMaterial({ color: LAMP.idle });
  r.logoCanvas = makeCanvas(96, 64);
  r.logoTex = texFrom(r.logoCanvas);
  r.logoMat = new THREE.MeshBasicMaterial({ map: r.logoTex, transparent: true });
  r.root = new THREE.Group();

  r.hips = new THREE.Group(); r.hips.position.y = HIPS_Y; r.root.add(r.hips);
  const pelvis = new THREE.Mesh(g.pelvis, coat || m.limb); pelvis.position.y = 0.03; r.hips.add(pelvis);
  const leg = (x) => {
    const pivot = new THREE.Group(); pivot.position.set(x, 0, 0); r.hips.add(pivot);
    const shin = new THREE.Mesh(g.leg, coat || m.limb); shin.position.y = -0.15; pivot.add(shin);
    const foot = new THREE.Mesh(g.foot, r.accent); foot.position.set(0, -0.31, 0.04); pivot.add(foot);
    return pivot;
  };
  r.legL = leg(0.17); r.legR = leg(-0.17);

  r.torso = new THREE.Group(); r.hips.add(r.torso);
  const body = new THREE.Mesh(g.torso, coat || m.shell); body.position.y = 0.32; r.torso.add(body);
  if (sub) {
    const stripe = new THREE.Mesh(g.stripe, m.stripe); stripe.position.y = 0.14; r.torso.add(stripe);
    const patch = new THREE.Group(); patch.position.set(-0.24, 0.45, 0.2725); patch.userData.wear = 'patch'; r.torso.add(patch);
    const edge = new THREE.Mesh(g.patchEdge, m.edge); patch.add(edge);
    const rim = new THREE.Mesh(g.patchRim, m.rim); rim.position.z = 0.001; patch.add(rim);
    const fill = new THREE.Mesh(g.patch, r.accent); fill.position.z = 0.002; patch.add(fill);
    r.wear = { body, stripe, patch, fill };
  }
  const chest = new THREE.Mesh(g.chest, m.chest); chest.position.set(0, 0.3, 0.2715); r.torso.add(chest);
  const lamp = new THREE.Mesh(g.lamp, r.lampMat); lamp.position.set(0.2, 0.5, 0.235); r.torso.add(lamp);
  const neck = new THREE.Mesh(g.neck, m.limb); neck.position.y = 0.63; r.torso.add(neck);

  r.head = new THREE.Group(); r.head.position.y = 0.66; r.torso.add(r.head);
  const skull = new THREE.Mesh(g.head, m.shell); skull.position.y = HEAD.h / 2; r.head.add(skull);
  r.faceCanvas = makeCanvas(256, 128);
  r.faceCtx = r.faceCanvas.getContext('2d');
  r.faceTex = texFrom(r.faceCanvas);
  const face = new THREE.Mesh(g.face, new THREE.MeshBasicMaterial({ map: r.faceTex, transparent: true, alphaTest: 0.4 }));
  face.position.set(0, 0.35, HEAD.d / 2 + 0.003); r.head.add(face);
  for (const side of [1, -1]) {
    const ear = new THREE.Mesh(g.ear, r.accent); ear.rotation.z = Math.PI / 2; ear.position.set(side * (HEAD.w / 2 + 0.035), 0.4, 0); r.head.add(ear);
    const cap = new THREE.Mesh(g.earCap, m.limb); cap.rotation.z = Math.PI / 2; cap.position.set(side * (HEAD.w / 2 + 0.06), 0.4, 0); r.head.add(cap);
  }
  r.antenna = new THREE.Group(); r.antenna.position.set(0, HEAD.h, -0.12); r.head.add(r.antenna);   // droops when tired
  const rod = new THREE.Mesh(g.rod, m.limb); rod.position.set(0, 0.09, 0); r.antenna.add(rod);
  const ball = new THREE.Mesh(g.ball, r.accent); ball.position.set(0, 0.2, 0); r.antenna.add(ball);

  r.bandCanvas = makeCanvas(2048, Math.round((2048 * BAND.h) / g.bandWall.userData.perimeter));
  r.bandTex = texFrom(r.bandCanvas);
  const band = new THREE.Group(); band.position.y = BAND.y; r.head.add(band);
  band.add(new THREE.Mesh(g.bandWall, toon('#ffffff', { map: r.bandTex })));
  band.add(new THREE.Mesh(g.bandCap, m.band));
  const knotZ = -(HEAD.d / 2 + BAND.t + 0.025);
  const knot = new THREE.Mesh(g.knot, m.band); knot.position.set(0, 0, knotZ); band.add(knot);
  r.tails = [0.3, -0.3].map((spread) => {
    const tail = new THREE.Mesh(g.tail, m.tail);
    tail.position.set(0, -0.02, knotZ - 0.01);
    tail.userData.spread = spread;
    band.add(tail);
    return tail;
  });

  const arm = (x) => {
    const pivot = new THREE.Group(); pivot.position.set(x, 0.49, 0.05); r.torso.add(pivot);
    pivot.add(new THREE.Mesh(g.shoulder, r.accent));
    const upper = new THREE.Mesh(g.arm, coat || m.limb); upper.position.y = -0.18; pivot.add(upper);
    const hand = new THREE.Mesh(g.hand, m.shell); hand.position.y = -0.38; pivot.add(hand);
    return pivot;
  };
  r.armL = arm(0.42); r.armR = arm(-0.42);
  if (sub) {   // the work cap: its brim to the front, over the band; the antenna stays out through the top
    const cap = new THREE.Group(); cap.userData.wear = 'cap'; r.head.add(cap);
    const crown = new THREE.Mesh(g.capCrown, m.overall); crown.position.y = CAP.y; cap.add(crown);
    const brim = new THREE.Mesh(g.capBrim, m.brim); brim.position.set(0, HEAD.h - 0.01, HEAD.d / 2 + 0.13); brim.rotation.x = 0.1; cap.add(brim);
    r.wear.cap = cap; r.wear.crown = crown;
  }
  r.root.scale.setScalar(r.size);
  if (furnished) {
    const desk = new THREE.Group(); desk.position.set(0, 0.275, 0.6); r.root.add(desk);
    const top = new THREE.Mesh(g.deskTop, m.wood); top.position.y = 0.25; desk.add(top);
    for (const [x, z] of [[-0.44, -0.22], [0.44, -0.22], [-0.44, 0.22], [0.44, 0.22]]) { const leg = new THREE.Mesh(g.deskLeg, m.woodDark); leg.position.set(x, -0.025, z); desk.add(leg); }
    r.desk = desk;   // the live view hides it while the robot walks to another seat
  }

  drawBand(r);
  drawLogo(r);
  r.fontRedraw = () => { drawBand(r); drawLogo(r); };   // kept so the live view can drop it when the robot leaves
  fontRedraws.push(r.fontRedraw);
  ensureProps(r, state);
  return r;
}

/* ---------- gestures: an energy drink once after 8 hours, coffee or a meal now and then (10-18) ----------
   A gesture moves the arms and shows a thing in the hand; the state, its lamp and its label stay as they are.
   Only while idle or at work (typing, reading, a command) — never while waiting for permission, thinking or done:
   a gesture there ends at once. None under reduced motion. */
const GESTURE_OK = new Set(['idle', 'typing', 'reading', 'command']);
const GESTURE_LEN = { drink: 3.6, coffee: 5, meal: 5, cheer: 1.6 };   // cheer: a small fist pump when a permission is granted (demo)
function handThing(kind) {
  const g = new THREE.Group();
  if (kind === 'drink') {                                   // a tall can, bright
    // dark with a lime band: no role colour (the hand is the role's colour) and not the white of the robot
    const can = new THREE.Mesh(new THREE.CylinderGeometry(0.07, 0.07, 0.26, 12), toon('#1c2440'));
    const band = new THREE.Mesh(new THREE.CylinderGeometry(0.072, 0.072, 0.08, 12), toon('#b6f03c')); band.position.y = 0.03;
    g.add(can, band);
  } else if (kind === 'coffee') {                           // a mug with a handle
    // a white mug with a navy band, coffee on top and steam: the hand (the role's colour) and the mug stay apart
    const mug = new THREE.Mesh(new THREE.CylinderGeometry(0.08, 0.07, 0.15, 12), toon('#ffffff'));
    const stripe = new THREE.Mesh(new THREE.CylinderGeometry(0.082, 0.078, 0.04, 12), toon('#24407a')); stripe.position.y = -0.01;
    const coffee = new THREE.Mesh(new THREE.CylinderGeometry(0.07, 0.07, 0.01, 12), toon('#6b4226')); coffee.position.y = 0.07;
    const handle = new THREE.Mesh(new THREE.TorusGeometry(0.045, 0.014, 6, 10), toon('#ffffff')); handle.position.x = 0.1;
    g.add(mug, stripe, coffee, handle);
    const steamMat = new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.55, depthWrite: false });
    for (let i = 0; i < 3; i++) { const puff = new THREE.Mesh(new THREE.SphereGeometry(0.03 + i * 0.008, 6, 4), steamMat); puff.position.set((i - 1) * 0.025, 0.12 + i * 0.06, 0); puff.userData.steam = i; g.add(puff); }
  } else {                                                  // a rice bowl and chopsticks
    const bowl = new THREE.Mesh(new THREE.SphereGeometry(0.12, 12, 8, 0, Math.PI * 2, Math.PI / 2, Math.PI / 2), toon('#e8554e'));
    bowl.rotation.x = Math.PI;
    const rice = new THREE.Mesh(new THREE.CircleGeometry(0.11, 12), toon('#fffaf0')); rice.rotation.x = -Math.PI / 2; rice.position.y = 0.0;
    g.add(bowl, rice);
  }
  g.position.set(0, -0.44, 0.2); g.scale.setScalar(1.4);   // in front of the hand: the face is 0.46 in front of the neck
  return g;
}
function startGesture(r, kind, t) {
  if (reduceMotion || !GESTURE_OK.has(r.state) || r.play || r.solo || r.brk || (r.call && CALL_ON_LINE.has(r.call.state))) return false;
  endGesture(r);
  if (kind !== 'cheer') { r.hand = handThing(kind); (kind === 'meal' ? r.armL : r.armR).add(r.hand); }
  r.gesture = { kind, t0: t, t1: t + GESTURE_LEN[kind] };
  if (kind === 'drink') r.drinks += 1;
  return true;
}
function endGesture(r) {
  if (r.hand) { r.hand.parent.remove(r.hand); r.hand.traverse((o) => { if (o.geometry) o.geometry.dispose(); if (o.material) o.material.dispose(); }); }
  r.hand = null; r.gesture = null;
}
/* Tired after 8 hours of its session (the page decides; the robot only shows it): the first time, a drink. */
/* Heavy work (requester, 10-18: many output tokens, a long tool call, three subagents — the server decides): while
   the robot works it types fast and sweats. The lamp and the label stay 作業中; never while waiting, thinking or done;
   under reduced motion the drops stay where they are. */
const HEAVY_OK = new Set(['typing', 'reading', 'command']);
function sweatDrops(r) {
  const g = new THREE.Group(), mat = new THREE.MeshBasicMaterial({ color: 0x7fd3ff, transparent: true, opacity: 0.9 });
  const geo = new THREE.SphereGeometry(0.05, 8, 6);
  for (let k = 0; k < 4; k++) { const d = new THREE.Mesh(geo, mat); d.scale.set(1, 1.5, 1); d.userData.k = k; g.add(d); }
  r.head.add(g);
  return g;
}
function sweatUpdate(r, s, on) {
  if (on && !r.sweat) r.sweat = sweatDrops(r);
  if (!r.sweat) return;
  r.sweat.visible = on;
  if (!on) return;
  for (const d of r.sweat.children) {
    const k = d.userData.k, side = k % 2 ? 1 : -1;
    const ph = reduceMotion ? 0.35 + k * 0.1 : (s * 1.7 + k / 4) % 1;
    d.position.set(side * (0.62 + ph * 0.45), 0.85 + Math.sin(ph * Math.PI) * 0.35 - ph * 0.2, 0.15);
    d.scale.setScalar(Math.max(0.2, 1 - ph * 0.8)); d.scale.y *= 1.5;
  }
}
/* Heavy work in three looks, one per cause (requester, 10-19; 2.3.6). r.heavy is the server's list of causes
   (ingest.py _heavy: 'tokens', 'tool', 'subagents'); the causes are decided there, only the look is decided here:
     tokens    -> 'fired':   the screen glows red, brows slanted down to the middle, a set jaw; fast typing
     tool      -> 'drained': the screen goes blue, small eyes sunk low, a wobbly mouth, gloom lines down its top;
                             slower typing. Not the 8-hour tiredness: that keeps the dark screen, half-shut eyes with
                             purple bags, a drooping antenna and the energy drink.
     subagents -> 'whistle': a whistle at the mouth, eyes squeezed > <, 「ピッ！」 over the head, one arm waving the
                             team on (main robots only: a subagent has no team)
   Sweat drops stay with all three (heavy work). Two or more causes take turns every LOOK_PERIOD seconds, the colour
   easing over LOOK_EASE seconds. Reduced motion: colour and face only, no waving and no turns: the first of
   LOOK_ORDER that holds (blue > whistle > red), the colour set at once. */
const HEAVY_LOOK = { tokens: 'fired', tool: 'drained', subagents: 'whistle' };
const LOOK_ORDER = ['drained', 'whistle', 'fired'];
const LOOK_PERIOD = 4, LOOK_EASE = 0.6;
const LOOK_TINT = { fired: [255, 64, 64, 0.42], drained: [64, 140, 255, 0.42], whistle: [0, 0, 0, 0] };
function heavyCauses(r) {
  const h = r.heavy === true ? ['tokens'] : Array.isArray(r.heavy) ? r.heavy : [];
  return LOOK_ORDER.filter((look) => h.some((c) => HEAVY_LOOK[c] === look) && (look !== 'whistle' || r.role === 'main'));
}
function heavyLook(r, t) {
  // background work: only the whistle (3+ subagents) shows, over the headset (requester 10-20: 「笛を優先」); red and blue not
  if (r.state === 'background') return heavyCauses(r).includes('whistle') ? 'whistle' : null;
  if (!HEAVY_OK.has(r.state)) return null;
  const looks = heavyCauses(r);
  if (!looks.length) return null;
  if (reduceMotion || looks.length === 1) return looks[0];
  return looks[Math.floor(t / LOOK_PERIOD) % looks.length];
}
function whistleProp() {
  const g = new THREE.Group(), metal = toon('#ffc928');
  const body = new THREE.Mesh(new THREE.CylinderGeometry(0.045, 0.045, 0.1, 12), metal); body.rotation.z = Math.PI / 2;
  const tube = new THREE.Mesh(new THREE.BoxGeometry(0.05, 0.03, 0.09), metal); tube.position.set(-0.05, 0.01, 0.04);
  const ring = new THREE.Mesh(new THREE.TorusGeometry(0.025, 0.009, 6, 10), toon('#1f2532')); ring.position.set(0.06, 0.02, 0);
  g.add(body, tube, ring);
  g.rotation.y = Math.PI / 2;
  g.position.set(0.02, 0.27, HEAD.d / 2 + 0.06);           // at the mouth, in front of the screen
  g.scale.setScalar(1.6);
  g.userData.whistle = true;
  return g;
}
function pipiBubble(text = 'ピッ！') {                        // 「ピッ」 over the head while the whistle blows
  const canvas = makeCanvas(192, 112), ctx = canvas.getContext('2d');
  ctx.fillStyle = '#ffffff'; ctx.strokeStyle = '#1f2532'; ctx.lineWidth = 6;
  rr(ctx, 6, 6, 180, 78, 30); ctx.fill(); ctx.stroke();
  ctx.beginPath(); ctx.moveTo(132, 82); ctx.lineTo(148, 106); ctx.lineTo(108, 82); ctx.closePath(); ctx.fill(); ctx.stroke();   // the tail toward the head
  ctx.fillStyle = '#ffffff'; ctx.fillRect(104, 76, 30, 8);
  ctx.fillStyle = '#e8590c'; ctx.font = `46px ${FONT_DISPLAY}`; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
  ctx.font = `${text.length > 3 ? 40 : 46}px ${FONT_DISPLAY}`;
  ctx.fillText(text, 96, 46);
  const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: texFrom(canvas), transparent: true }));
  s.position.set(-1.0, 2.1, 0.3); s.scale.set(0.72, 0.42, 1); s.userData.pipi = true;   // beside the head, by the waving (right, -x) arm
  return s;
}
/* Calling a subagent (requester 10-20: "サブエージェント呼ぶのは笛鳴らそうか"; ticket 2026-10-20-jui-viz-agent-launch-whistle):
   r.launch is true for a fixed length from the moment an Agent call starts (the server's agent.whistle, robots.py
   LAUNCH_WHISTLE_MS; the page turns it off when vizNow passes its end, and never while the robot is away from its
   desk). The same whistle and the same waving arm as heavy work's 'whistle', the face squeezed > <, and its own
   bubble 「ピーッ！」 (a long blow) where heavy work says 「ピッ！」. Told apart: the launch is short (2.5 s), comes with
   the call (the robot carries its papers, then waits, or works on), with no sweat and with 「ピーッ！」; heavy work's
   directing of 3 or more subagents lasts as long as they run, with sweat and 「ピッ！」. Both at once: 「ピーッ！」 for
   the launch's 2.5 s, then 「ピッ！」 and the sweat go on. Reduced motion: the whistle at the mouth only, no waving. */
function lookUpdate(r, t, dt) {
  const look = heavyLook(r, t);
  r.look = look;
  const want = look ? LOOK_TINT[look] : [0, 0, 0, 0];
  const cur = r.tint || (r.tint = [0, 0, 0, 0]);
  if (!cur[3]) { cur[0] = want[0]; cur[1] = want[1]; cur[2] = want[2]; }   // from nothing: the hue at once, the alpha eases
  const k = reduceMotion ? 1 : Math.min(1, dt / LOOK_EASE * 3);
  for (let i = 0; i < 4; i++) cur[i] += (want[i] - cur[i]) * k;
  const blow = look === 'whistle' || !!r.launch;
  if (blow && !r.whistle) { r.whistle = whistleProp(); r.head.add(r.whistle); }
  if (r.whistle) r.whistle.visible = blow;
  if (look === 'whistle' && !r.launch && !r.pipi) { r.pipi = pipiBubble(); r.root.add(r.pipi); }
  if (r.launch && !r.pipiLong) { r.pipiLong = pipiBubble('ピーッ！'); r.pipiLong.userData.launch = true; r.root.add(r.pipiLong); }
  for (const [bubble, on] of [[r.pipi, look === 'whistle' && !r.launch], [r.pipiLong, !!r.launch]]) {
    if (!bubble) continue;
    bubble.visible = on;
    if (on && !reduceMotion) bubble.position.y = 2.1 + Math.abs(Math.sin(t * 7)) * 0.08;   // in time with the arm
  }
  return look;
}
/* The browser tests' hook (80-dbg.js, force) sets a robot's causes or its tiredness; the page never does. */
const forced = (r, key, value) => (r.force && key in r.force ? r.force[key] : value);
/* Background work and heavy work: the heavy looks (lookUpdate, sweat) hold in HEAVY_OK's states (typing, reading, a
   command); a robot working in the background is in its own state, 'background', where the headset, the notes and the
   loose typing win over the red and the blue face (2.3.5 integration, 10-20). The whistle wins over the headset
   (requester 10-20: 「サブエージェント7対いるけど笛のアクションにならないね」, then 「笛を優先」): with 3 or more
   subagents a main robot in the background whistles, waves and sweats, its headset and notes off; when the cause goes,
   the headset is back. The launch whistle (2.5 s, 「ピーッ！」) shows over the headset as before, with no change. */
/* Background work (requester, 10-19: "バックグラウンドで作業の場合はヘッドセットつけて、音符出してる状態で机の上でパソコンを
   ゆるめにいじってほしい"): a headset on the head (cups in the 裏で作業中 colour, LAMP.bg, as on the tag, the card and the
   legend), NOTE_MAX notes rising over it (still under reduced motion), and the laptop typed on loosely (poseFor
   'background'). Built once a robot first works in the background, one set a robot; shown only in that state. */
const NOTE_MAX = 3;
function noteCanvas(double) {
  const c = makeCanvas(96, 112), ctx = c.getContext('2d');
  const head = (x, y) => { ctx.beginPath(); ctx.ellipse(x, y, 15, 11, -0.45, 0, Math.PI * 2); ctx.fill(); ctx.stroke(); };
  ctx.lineJoin = 'round'; ctx.lineCap = 'round';
  for (const [pass, w, colour] of [[0, 14, '#1f2a44'], [1, 0, LAMP.bg]]) {
    ctx.strokeStyle = pass ? colour : '#1f2a44'; ctx.fillStyle = pass ? colour : '#1f2a44'; ctx.lineWidth = pass ? 6 : w;
    if (double) {
      ctx.beginPath(); ctx.moveTo(38, 84); ctx.lineTo(38, 24); ctx.lineTo(80, 14); ctx.lineTo(80, 74); ctx.stroke();
      ctx.lineWidth = pass ? 10 : 18; ctx.beginPath(); ctx.moveTo(38, 26); ctx.lineTo(80, 16); ctx.stroke();
      ctx.lineWidth = pass ? 2 : w; head(26, 86); head(68, 76);
    } else {
      ctx.beginPath(); ctx.moveTo(56, 86); ctx.lineTo(56, 16); ctx.quadraticCurveTo(66, 40, 84, 46); ctx.stroke();
      ctx.lineWidth = pass ? 2 : w; head(44, 88);
    }
  }
  return c;
}
function bgGear(r) {
  if (!S.tex.notes) S.tex.notes = [texFrom(noteCanvas(false)), texFrom(noteCanvas(true))];
  const band = toon('#273449'), cup = toon(LAMP.bg), pad = toon('#1b2333');
  const headset = new THREE.Group(); headset.userData.headset = true;
  const R = HEAD.w / 2 + 0.15;
  const arc = new THREE.Mesh(new THREE.TorusGeometry(R, 0.04, 10, 40, Math.PI), band);
  const top = r.sub ? CAP.y + CAP.h / 2 + 0.07 : HEAD.h + 0.07;   // over the work cap's crown when it has one
  arc.position.set(0, 0.42, -0.02); arc.scale.y = (top - 0.42) / R; headset.add(arc);
  for (const side of [1, -1]) {
    const shell = new THREE.Mesh(new THREE.CylinderGeometry(0.2, 0.2, 0.13, 28), cup); shell.rotation.z = Math.PI / 2; shell.position.set(side * R, 0.42, -0.02); headset.add(shell);
    const cushion = new THREE.Mesh(new THREE.CylinderGeometry(0.16, 0.16, 0.05, 24), pad); cushion.rotation.z = Math.PI / 2; cushion.position.set(side * (R - 0.08), 0.42, -0.02); headset.add(cushion);
  }
  // the microphone on its boom, from the right cup to in front of the mouth
  const boom = new THREE.Mesh(new THREE.CylinderGeometry(0.02, 0.02, 0.5, 8), band);
  boom.position.set(R - 0.12, 0.26, 0.24); boom.rotation.set(Math.PI / 2 - 0.35, 0, 0.55); headset.add(boom);
  const mic = new THREE.Mesh(new THREE.SphereGeometry(0.05, 14, 10), pad); mic.position.set(R - 0.27, 0.15, 0.47); headset.add(mic);
  r.head.add(headset);
  const notes = new THREE.Group(); notes.userData.notes = true;
  for (let k = 0; k < NOTE_MAX; k++) {
    const sp = new THREE.Sprite(new THREE.SpriteMaterial({ map: S.tex.notes[k % 2], transparent: true, depthWrite: false }));
    sp.scale.set(0.3, 0.35, 1); sp.userData.k = k; notes.add(sp);
  }
  r.root.add(notes);
  r.headset = headset; r.notes = notes;
}
function bgUpdate(r, t, on) {
  if (on && !r.headset) bgGear(r);
  if (!r.headset) return;
  r.headset.visible = on; r.notes.visible = on;
  if (!on) return;
  for (const sp of r.notes.children) {
    const n = notePose(r, sp.userData.k, t);
    sp.position.set(n.x, n.y, 0.1);
    sp.material.opacity = n.opacity;
  }
}
/* Where note k stands at time t (the e2e reads it at two times: still under reduced motion, rising otherwise). */
function notePose(r, k, t) {
  const ph = reduceMotion ? 0.3 + k * 0.22 : (t * 0.42 + k / NOTE_MAX + r.seed * 0.13) % 1;
  return { x: (k % 2 ? -1 : 1) * (0.42 + ph * 0.18) + Math.sin(ph * 6.3 + k) * 0.06, y: 1.95 + ph * 0.75,
    opacity: reduceMotion ? 1 : Math.min(1, Math.sin(ph * Math.PI) * 1.6) };
}
/* Reading the web (requester 10-20: "WebFetchの時は机で辞書をペラペラめくるアニメーションにして欲しい"; WebSearch too): the
   state stays 'reading' (lamp, tag and card as they were) and r.readKind is 'web' (ingest.py agent.readKind, from
   robots.WEB_READING_TOOLS). In place of the book held up, a thick dictionary lies open on the desk and the right hand
   flips its pages: DICT_PAGES pages one after another (DICT_GAP apart, each over in DICT_FLIP), then a rest, every
   DICT_PERIOD of pose time. A page is drawn only while it turns; the two blocks of pages stay. Only in 'reading', so
   never away from the desk (walking, a break, a game, the box: other states). Reduced motion: the dictionary open,
   no page turning, the hand still. Built once a robot first reads the web, under its root with geometries and
   materials of its own: taking the robot down (disposeTree) disposes them, as the other props. */
const DICT_PAGES = 3, DICT_PERIOD = 2.6, DICT_FLIP = 0.55, DICT_GAP = 0.22;
const DICT = { w: 0.27, d: 0.36, block: 0.1, board: 0.014, x: 0, y: 0.55, z: 0.5 };   // y: the desk's top (0.275 + 0.25 + 0.025)
/* How far page k has turned at pose time s, 0 (on the right block) to 1 (laid on the left one). */
function dictFlip(s, k) {
  if (reduceMotion) return 0;
  const u = Math.min(1, Math.max(0, ((((s % DICT_PERIOD) + DICT_PERIOD) % DICT_PERIOD) - k * DICT_GAP) / DICT_FLIP));
  return u * u * (3 - 2 * u);
}
/* The right hand over the pages: 0 at rest, 1 in the middle of a turn. */
function dictHand(s) {
  let f = 0;
  for (let k = 0; k < DICT_PAGES; k++) f = Math.max(f, Math.sin(Math.PI * dictFlip(s, k)));
  return f;
}
function dictBuild(r) {
  const group = new THREE.Group(); group.userData.dictionary = true;
  group.position.set(DICT.x, DICT.y, DICT.z);
  const coverMat = toon('#7a2432'), pageMat = toon('#f7f1df'), edgeMat = toon('#d9cba3'), tabMat = toon('#c9a227');
  const top = DICT.board + DICT.block;
  for (const side of [-1, 1]) {   // -1: the robot's right (-x), the pages not read yet; 1: its left
    const board = new THREE.Mesh(new THREE.BoxGeometry(DICT.w + 0.02, DICT.board, DICT.d + 0.025), coverMat);
    board.position.set(side * (DICT.w / 2 + 0.008), DICT.board / 2, 0); group.add(board);
    const block = new THREE.Mesh(new THREE.BoxGeometry(DICT.w, DICT.block, DICT.d), [edgeMat, edgeMat, pageMat, edgeMat, edgeMat, edgeMat]);
    block.position.set(side * (DICT.w / 2 + 0.004), DICT.board + DICT.block / 2, 0); block.rotation.z = side * 0.04; group.add(block);
  }
  const spine = new THREE.Mesh(new THREE.CylinderGeometry(0.03, 0.03, DICT.d + 0.025, 16, 1, false, -Math.PI / 2, Math.PI), coverMat);
  spine.rotation.x = Math.PI / 2; spine.position.set(0, 0.03, 0); group.add(spine);   // the round back, under the middle
  for (let k = 0; k < 3; k++) {   // thumb-index tabs on the outer edge of the pages still to read: a dictionary
    const tab = new THREE.Mesh(new THREE.BoxGeometry(0.012, 0.03, 0.05), tabMat);
    tab.position.set(-(DICT.w + 0.01), DICT.board + 0.022 + k * 0.028, -0.11 + k * 0.11); group.add(tab);
  }
  const leafGeo = new THREE.BoxGeometry(DICT.w - 0.01, 0.003, DICT.d - 0.01).translate(-(DICT.w - 0.01) / 2, 0, 0);
  const pages = [];
  for (let k = 0; k < DICT_PAGES; k++) {   // each page turns about the spine, from the right block over to the left
    const hinge = new THREE.Group(); hinge.position.set(0, top + 0.002 + k * 0.001, 0); group.add(hinge);
    const leaf = new THREE.Mesh(leafGeo, pageMat); hinge.add(leaf);
    pages.push(hinge);
  }
  const holder = new THREE.Group(); holder.add(group);
  if (!r.furnished) {   // a robot without a desk of its own (the demo) gets one, as the laptop does
    const g = S.geo, m = S.mat, desk = new THREE.Group(); desk.position.set(0, 0.275, 0.6); holder.add(desk);
    const deskTop = new THREE.Mesh(g.deskTop, m.wood); deskTop.position.y = 0.25; desk.add(deskTop);
    for (const [x, z] of [[-0.44, -0.22], [0.44, -0.22], [-0.44, 0.22], [0.44, 0.22]]) { const leg = new THREE.Mesh(g.deskLeg, m.woodDark); leg.position.set(x, -0.025, z); desk.add(leg); }
  }
  r.root.add(holder);
  return { group: holder, book: group, pages };
}
function dictUpdate(r, s, k) {
  const on = k > 0.02;
  if (on && !r.dict) r.dict = dictBuild(r);
  if (!r.dict) return;
  r.dict.group.visible = on;
  if (!on) return;
  r.dict.book.scale.setScalar(Math.max(0.001, k));
  r.dict.pages.forEach((hinge, i) => {
    const f = dictFlip(s, i);
    hinge.rotation.z = -Math.PI * f;   // 0: lying on the right block; π: on the left one
    hinge.visible = f > 0.001 && f < 0.999;
  });
}
function setRobotTired(r, on) {
  if (on && !r.tired) r.needDrink = true;
  if (!on) r.needDrink = false;
  r.tired = on;
}
/* Phone calls (requester, 10-18: SendMessage between two sessions — the server's calls slice decides). r.call is
   { role: 'caller' | 'callee', state } or null; like sweat, the state, its lamp and its label stay as they are.
   The caller holds a handset to its ear while it rings and on the line; the callee's phone rings over its head until
   it picks up (it reads the message), then it holds the handset too. A call puts a gesture away. Under reduced
   motion nothing shakes. */
const CALL_ON_LINE = new Set(['dialing', 'ringing', 'answered']);
function handset() {
  const g = new THREE.Group();
  const body = new THREE.Mesh(new THREE.CapsuleGeometry(0.05, 0.26, 4, 8), toon('#1f2532'));
  for (const y of [-0.16, 0.16]) { const cup = new THREE.Mesh(new THREE.SphereGeometry(0.075, 10, 8), toon('#1f2532')); cup.position.y = y; g.add(cup); }
  g.add(body);
  g.position.set(0, -0.46, 0.14); g.rotation.x = 0.3;
  return g;
}
function ringBubble() {
  const canvas = makeCanvas(160, 160), ctx = canvas.getContext('2d');
  ctx.fillStyle = '#ffffff'; ctx.strokeStyle = '#1f2532'; ctx.lineWidth = 6;
  ctx.beginPath(); ctx.arc(80, 80, 52, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
  ctx.fillStyle = '#2f9e5b';   // a handset, tilted
  ctx.save(); ctx.translate(80, 84); ctx.rotate(-0.6);
  rr(ctx, -30, -9, 60, 18, 9); ctx.fill();
  rr(ctx, -34, -9, 18, 28, 7); ctx.fill(); rr(ctx, 16, -9, 18, 28, 7); ctx.fill();
  ctx.restore();
  ctx.strokeStyle = '#2f9e5b'; ctx.lineWidth = 6; ctx.lineCap = 'round';
  for (const rad of [64, 76]) { ctx.beginPath(); ctx.arc(80, 80, rad, -1.2, -0.4); ctx.stroke(); ctx.beginPath(); ctx.arc(80, 80, rad, Math.PI + 0.4, Math.PI + 1.2); ctx.stroke(); }
  const mat = new THREE.SpriteMaterial({ map: texFrom(canvas), transparent: true });
  const s = new THREE.Sprite(mat); s.position.set(0, 2.3, 0.1); s.scale.set(0.5, 0.5, 1);
  return s;
}
function callUpdate(r, t) {
  const c = r.call;
  const ringing = !!c && c.role === 'callee' && (c.state === 'ringing' || c.state === 'dialing');
  const onLine = !!c && CALL_ON_LINE.has(c.state) && !ringing;
  if (ringing && !r.ring) { r.ring = ringBubble(); r.root.add(r.ring); }
  if (r.ring) {
    r.ring.visible = ringing;
    if (ringing && !reduceMotion) { r.ring.material.rotation = Math.sin(t * 38) * 0.22; r.ring.position.y = 2.3 + Math.abs(Math.sin(t * 9)) * 0.06; }
  }
  if (onLine && !r.handset) { if (r.gesture) endGesture(r); r.handset = handset(); r.armR.add(r.handset); }
  if (!onLine && r.handset) { r.handset.parent.remove(r.handset); r.handset.traverse((o) => { if (o.geometry) o.geometry.dispose(); if (o.material) o.material.dispose(); }); r.handset = null; }
  return onLine;
}
function callPose(p, t) {   // the right hand at the ear, the head toward it
  p.aRx = -2.25; p.aRz = -1.2; p.headZ = 0.16; p.headX = -0.04;
  if (!reduceMotion) p.headY = Math.sin(t * 1.3) * 0.12;
}
/* Play (requester, 10-18: robots idle for long in one room play together; the scene decides who, where and how
   long). r.play is { kind: 'ball' | 'highfive' | 'rps', t0, side: 0 | 1, seed } while at the spot; the state stays idle.
   2.3.3 (requester, 10-19: "ずっと二人で向き合ってるだけで何やってるかわからない"): every game moves big enough to read
   from the usual view. ball: the thrower winds up over its shoulder and swings through, the catcher holds both hands
   out (the ball itself is the scene's); highfive: the two walk toward each other, turn a little to the front and slap
   the inner hands (the walk and the パチン mark are the scene's); rps (じゃんけん): three pumps, then the hand drawn in a
   bubble that stays up until the next pump, the winner raises both arms, the loser hangs its head, あいこ plays again
   at once. The timing helpers are shared with the scene (40-scene.js), so the arms, the ball and the walk agree. */
const RPS_HANDS = ['グー', 'チョキ', 'パー'];
const playEase = (v) => { const k = Math.max(0, Math.min(1, v)); return k * k * (3 - 2 * k); };
const playMix = (a, b, k) => a + (b - a) * k;
// ball: one throw per half; the thrower winds up until windup, the ball leaves the hand at release
const BALL_T = { half: 1.5, windup: 0.3, release: 0.42 };
function ballPhase(u) { const n = Math.floor(u / BALL_T.half); return { n, thrower: n % 2, w: u / BALL_T.half - n }; }
// highfive: walk in until inEnd, the hands up and the slap at touch, walk back from outStart until back
const HIGHFIVE_T = { period: 2.8, inEnd: 0.34, touch: 0.46, outStart: 0.6, back: 0.92, turn: 1.15 };
function highfivePhase(u) {
  const T = HIGHFIVE_T, w = (u / T.period) % 1;
  const near = w < T.inEnd ? playEase(w / T.inEnd) : w < T.outStart ? 1 : w < T.back ? 1 - playEase((w - T.outStart) / (T.back - T.outStart)) : 0;
  const up = w < T.touch ? playEase((w - (T.inEnd - 0.1)) / (T.touch - T.inEnd + 0.06)) : 1 - playEase((w - T.touch - 0.06) / (T.outStart - T.touch));
  const walking = (w < T.inEnd) || (w >= T.outStart && w < T.back);
  return { w, near, up, walking, slap: Math.abs(w - T.touch) < 0.09 };
}
// rps: the pumps until shake; a decided round lasts len, a tie (あいこ) only tie: it plays again at once
const RPS_T = { shake: 1.5, result: 2.1, len: 4.4, tie: 3.2 };
function rpsHand(seed, k, side) {
  let h = Math.imul((seed | 0) ^ 0x9e3779b9, 0x85ebca6b) ^ Math.imul(k + 1, 0xc2b2ae35) ^ Math.imul(side + 7, 0x27d4eb2f);
  h = Math.imul(h ^ (h >>> 15), 0x2c1b3c6d); h ^= h >>> 13;
  return (h >>> 0) % 3;
}
// a beats b when (b - a + 3) % 3 === 1 (グー > チョキ > パー > グー)
function rpsRound(seed, u) {
  let start = 0;
  for (let k = 0; k < 500; k++) {
    const hands = [rpsHand(seed, k, 0), rpsHand(seed, k, 1)], tie = hands[0] === hands[1];
    const len = tie ? RPS_T.tie : RPS_T.len;
    if (u < start + len) {
      const res = tie ? ['tie', 'tie'] : (hands[1] - hands[0] + 3) % 3 === 1 ? ['win', 'lose'] : ['lose', 'win'];
      return { k, w: u - start, len, hands, res };
    }
    start += len;
  }
  return { k: 0, w: 0, len: RPS_T.len, hands: [0, 0], res: ['tie', 'tie'] };
}
function playPose(r, p, t) {
  const P = r.play, u = Math.max(0, t - P.t0);
  if (P.kind === 'ball') {
    const { thrower, w } = ballPhase(u);
    if (P.side === thrower) {
      p.aLx = -1.1; p.aLz = 0.25; p.headX = -0.12;
      if (w < BALL_T.windup) {                               // wind up: the arm up and back over the shoulder, the body turned away
        const k = playEase(w / BALL_T.windup);
        p.aRx = playMix(-0.6, 0.75, k); p.aRz = playMix(-0.3, -2.35, k); p.torsoY = -0.4 * k; p.torsoX = -0.12 * k;
      } else if (w < BALL_T.release) {                       // the throw: a big swing forward and down, the body leaning in
        const k = playEase((w - BALL_T.windup) / (BALL_T.release - BALL_T.windup));
        p.aRx = playMix(0.75, -2.0, k); p.aRz = playMix(-2.35, -0.5, k); p.torsoY = playMix(-0.4, 0.3, k); p.torsoX = playMix(-0.12, 0.2, k);
      } else {                                               // follow through, then rest while the ball flies
        const k = playEase((w - BALL_T.release) / 0.35);
        p.aRx = playMix(-2.0, -0.5, k); p.aRz = playMix(-0.5, -0.2, k); p.torsoY = playMix(0.3, 0, k); p.torsoX = playMix(0.2, 0, k);
      }
    } else {                                                 // the catcher: both hands out in front, together
      const k = playEase((w - 0.08) / 0.25);
      p.aRx = -1.45 * k; p.aLx = -1.45 * k; p.aRz = playMix(-0.12, 0.38, k); p.aLz = playMix(0.12, -0.38, k);
      p.headX = -0.1; p.torsoX = w > 0.94 ? -0.08 : 0.04 * k;
    }
  } else if (P.kind === 'highfive') {
    const H = highfivePhase(u), inner = P.side === 0 ? 'L' : 'R', sgn = P.side === 0 ? 1 : -1;   // the hand toward the partner
    if (H.walking) { const sw = Math.sin(u * 11) * 0.55; p.lLx = sw; p.lRx = -sw; p.aLx = -sw * 0.5; p.aRx = sw * 0.5; }
    p[`a${inner}z`] = sgn * playMix(0.12, 2.0, H.up); p[`a${inner}x`] = playMix(p[`a${inner}x`] || 0, 0, H.up);
    p.rootY = H.slap ? 0.08 * (1 - Math.abs(H.w - HIGHFIVE_T.touch) / 0.09) : 0; p.headX = -0.12 * H.up;
  } else {
    const R = rpsRound(P.seed | 0, u), w = R.w;
    if (w < RPS_T.shake) {                                   // じゃん・けん・ぽん: three big pumps
      const pump = Math.abs(Math.sin((w / RPS_T.shake) * Math.PI * 3));
      p.aRx = -0.6 - pump * 1.5; p.aRz = -0.3; p.aLx = -0.4; p.aLz = 0.3; p.headX = 0.05; p.torsoX = pump * 0.06;
    } else if (w < RPS_T.result) {                           // the hand out in front
      p.aRx = -1.45; p.aRz = -0.15; p.aLx = -0.3; p.headX = 0.08;
    } else if (R.res[P.side] === 'win') {                    // both arms up, a hop
      const hop = Math.abs(Math.sin((w - RPS_T.result) * 6));
      p.aRx = 0; p.aRz = -2.35; p.aLx = 0; p.aLz = 2.35; p.rootY = hop * 0.12; p.headX = -0.2;
    } else if (R.res[P.side] === 'lose') {                   // head down, arms hanging
      p.aRx = 0.15; p.aRz = -0.05; p.aLx = 0.15; p.aLz = 0.05; p.headX = 0.4; p.torsoX = 0.14; p.hipsY = -0.02;
    } else {                                                 // あいこ: the hand still out, the head tilted
      p.aRx = -1.3; p.aRz = -0.15; p.headZ = 0.22; p.headX = -0.05;
    }
  }
}
// the hand as a picture (a fist, two fingers, an open hand) and its name; the result under it once it is known
function rpsDraw(ctx, W, H, hand, res) {
  ctx.clearRect(0, 0, W, H);
  ctx.fillStyle = '#ffffff'; ctx.strokeStyle = '#1f2532'; ctx.lineWidth = 7;
  rr(ctx, 6, 6, W - 12, H - 12, 34); ctx.fill(); ctx.stroke();
  const cx = 82, cy = 104, skin = '#ffcf9e';
  ctx.fillStyle = skin; ctx.strokeStyle = '#5a3a1e'; ctx.lineWidth = 5; ctx.lineCap = 'round'; ctx.lineJoin = 'round';
  const finger = (ang, len) => {
    ctx.save(); ctx.translate(cx, cy); ctx.rotate(ang);
    rr(ctx, -10, -len - 18, 20, len + 10, 10); ctx.fill(); ctx.stroke(); ctx.restore();
  };
  if (hand === 1) { finger(-0.32, 58); finger(0.18, 62); }
  if (hand === 2) { finger(-0.95, 34); finger(-0.42, 54); finger(-0.08, 60); finger(0.26, 56); finger(0.6, 46); }
  rr(ctx, cx - 36, cy - 32, 72, 70, 24); ctx.fill(); ctx.stroke();
  if (hand === 0) for (let i = 0; i < 3; i++) { ctx.beginPath(); ctx.moveTo(cx - 34, cy - 12 + i * 16); ctx.lineTo(cx + 6, cy - 12 + i * 16); ctx.stroke(); }
  ctx.fillStyle = '#1f2532'; ctx.font = `700 50px ${FONT_BODY}`; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
  ctx.fillText(RPS_HANDS[hand], 200, res ? 74 : 104);
  if (res) {
    const [text, color] = { win: ['かち！', '#d0352b'], lose: ['まけ…', '#5b6577'], tie: ['あいこ', '#d88a00'] }[res];
    ctx.fillStyle = color; ctx.font = `700 46px ${FONT_DISPLAY}`; ctx.fillText(text, 200, 150);
  }
}
function playBubble(r, P, t) {
  const R = P && P.kind === 'rps' ? rpsRound(P.seed | 0, Math.max(0, t - P.t0)) : null;
  const show = !!R && R.w >= RPS_T.shake;                    // from the reveal until the next pump
  r.rpsState = R ? { k: R.k, hand: show ? RPS_HANDS[R.hands[P.side]] : null, res: show && R.w >= RPS_T.result ? R.res[P.side] : null, shaking: !show } : null;
  if (show && !r.rps) {
    r.rpsCanvas = makeCanvas(300, 210);
    r.rps = new THREE.Sprite(new THREE.SpriteMaterial({ map: texFrom(r.rpsCanvas), transparent: true, depthTest: false }));
    r.rps.renderOrder = 5; r.rps.position.set(0, 2.3, 0.1); r.rps.scale.set(0.86, 0.6, 1); r.root.add(r.rps); r.rpsShown = '';
  }
  if (!r.rps) return;
  r.rps.visible = show;
  if (!show) return;
  const key = `${R.hands[P.side]}:${r.rpsState.res || ''}`;
  if (key === r.rpsShown) return;
  r.rpsShown = key;
  rpsDraw(r.rpsCanvas.getContext('2d'), 300, 210, R.hands[P.side], r.rpsState.res);
  r.rps.material.map.needsUpdate = true;
}
/* Alone in its room (requester, 10-18): r.solo is { kind: 'nap' | 'bento', t0 } while the scene says so. nap: the head
   sinks and nods, the arms rest, a zzz drifts up; bento: a box on the desk, chopsticks to the mouth. */
function soloPose(r, p, t) {
  const u = t - r.solo.t0;
  if (r.solo.kind === 'nap') {
    const nod = reduceMotion ? 0 : Math.sin(u * 1.1);
    p.headX = 0.42 + nod * 0.06; p.headZ = 0.12; p.torsoX = 0.1; p.hipsY = -0.01;
    p.aLx = -0.9; p.aLz = -0.3; p.aRx = -0.9; p.aRz = 0.3;
  } else {
    const bite = 0.5 + 0.5 * Math.sin(u * 4.2);
    p.aLx = -1.1; p.aLz = -0.35; p.aRx = -1.35 - bite * 0.45; p.aRz = 0.3; p.headX = 0.22 - bite * 0.06;
  }
}
/* White letters with a dark rim: readable on the light floor and on the dark one (jsonuidocument-96, 10-18: the blue zzz
   all but vanished on the dark floor and walls). */
function zzzCanvas() {
  const c = makeCanvas(200, 150), ctx = c.getContext('2d');
  ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.lineJoin = 'round';
  [[50, 112, 38], [104, 74, 50], [156, 34, 62]].forEach(([x, y, size]) => {
    ctx.font = `700 ${size}px ${FONT_DISPLAY}`;
    ctx.lineWidth = 9; ctx.strokeStyle = '#1f2a44'; ctx.strokeText('z', x, y);
    ctx.fillStyle = '#ffffff'; ctx.fillText('z', x, y);
  });
  return c;
}
function bentoBox() {
  const g = new THREE.Group();
  // big enough to read from the usual view (96, 10-18: a few pixels even up close): a red box, rice, a side dish, a lid
  const box = new THREE.Mesh(new THREE.BoxGeometry(0.62, 0.12, 0.44), toon('#c0392b'));
  const rice = new THREE.Mesh(new THREE.BoxGeometry(0.28, 0.03, 0.38), toon('#fffaf0')); rice.position.set(-0.14, 0.07, 0);
  const plum = new THREE.Mesh(new THREE.SphereGeometry(0.04, 10, 8), toon('#d63a5a')); plum.position.set(-0.14, 0.1, 0);
  const side = new THREE.Mesh(new THREE.BoxGeometry(0.26, 0.04, 0.38), toon('#e6a23c')); side.position.set(0.15, 0.07, 0);
  const lid = new THREE.Mesh(new THREE.BoxGeometry(0.62, 0.03, 0.44), toon('#2b2f36')); lid.position.set(0.5, 0.0, 0.05); lid.rotation.z = 0.35;
  g.add(box, rice, plum, side, lid);
  g.position.set(0, 0.62, 0.48);
  return g;
}
function soloProps(r, S, t) {
  const nap = !!S && S.kind === 'nap', bento = !!S && S.kind === 'bento';
  if (nap && !r.zzz) { r.zzz = new THREE.Sprite(new THREE.SpriteMaterial({ map: texFrom(zzzCanvas()), transparent: true, depthTest: false })); r.zzz.renderOrder = 5; r.zzz.scale.set(1.1, 0.82, 1); r.root.add(r.zzz); }
  if (r.zzz) {
    r.zzz.visible = nap;
    if (nap) { const k = reduceMotion ? 0.4 : ((t - S.t0) * 0.4) % 1; r.zzz.position.set(0.55, 2.0 + k * 0.5, 0.1); r.zzz.material.opacity = 1 - k * 0.5; }
  }
  if (bento && !r.bento) { r.bento = bentoBox(); r.root.add(r.bento); }
  if (r.bento) r.bento.visible = bento;
}
/* A break (requester, 10-19: a cigarette in the smoking booth, a drink from the vending machine). r.brk is
   { kind: 'smoke' | 'vend', t0, buySec } while the robot is at the booth or the machine; the scene walks it there and back.
   smoke: the hand with the cigarette goes to the mouth every BRK_PUFF_SEC, then down (the scene lets the smoke out);
   vend: a button pressed, a bend to the slot, then a can sipped now and then. */
const BRK_PUFF_SEC = 5;
function brkPuff(u) {   // 0: the hand down, 1: at the mouth (a smooth lift, a hold, a smooth drop)
  const c = u % BRK_PUFF_SEC, e = (x) => x * x * (3 - 2 * x);
  return c < 0.5 ? e(c / 0.5) : c < 1.8 ? 1 : c < 2.3 ? 1 - e((c - 1.8) / 0.5) : 0;
}
function brkPose(r, p, t) {
  const B = r.brk, u = t - B.t0;
  if (B.kind === 'smoke') {
    const k = reduceMotion ? 0 : brkPuff(u);
    p.aRx = -0.55 - k * 1.0; p.aRz = 0.15 + k * 0.35; p.aLx = -0.15; p.aLz = 0.12; p.headX = 0.02 - k * 0.08;
  } else if (u < B.buySec * 0.5) {                          // a finger on a button
    p.aRx = -1.45; p.aRz = 0.08; p.torsoX = 0.05; p.headX = 0.05;
  } else if (u < B.buySec) {                                // a bend to the slot below
    p.aRx = -0.9; p.aRz = 0.1; p.torsoX = 0.35; p.headX = 0.25;
  } else {                                                  // the can to the mouth, head back, now and then
    const c = (u - B.buySec) % 4, sip = c < 1.6 ? Math.sin((c / 1.6) * Math.PI) : 0;
    p.aRx = -1.0 - sip * 0.8; p.aRz = 0.3 + sip * 0.15; p.headX = -sip * 0.3;
  }
}
function cigarette() {
  const g = new THREE.Group();
  const stick = new THREE.Mesh(new THREE.CylinderGeometry(0.02, 0.02, 0.16, 8), toon('#f4f1ea'));
  const filter = new THREE.Mesh(new THREE.CylinderGeometry(0.021, 0.021, 0.05, 8), toon('#d9913a')); filter.position.y = -0.08;
  const tip = new THREE.Mesh(new THREE.SphereGeometry(0.026, 8, 6), new THREE.MeshBasicMaterial({ color: 0xff6a2a })); tip.position.y = 0.085;
  g.add(stick, filter, tip); g.userData.tip = tip;
  g.rotation.x = Math.PI / 2; g.position.set(0, -0.43, 0.1); g.scale.setScalar(1.5);
  return g;
}
function brkProps(r, B, t) {
  const want = !B ? null : B.kind === 'smoke' ? 'smoke' : t - B.t0 >= B.buySec ? 'vend' : null;   // the can once it is taken out
  if (want === (r.brkHandKind || null)) return;
  if (r.brkHand) { r.brkHand.parent.remove(r.brkHand); r.brkHand.traverse((o) => { if (o.geometry) o.geometry.dispose(); if (o.material) o.material.dispose(); }); }
  r.brkHand = want === 'smoke' ? cigarette() : want === 'vend' ? handThing('drink') : null;
  r.brkHandKind = want;
  if (r.brkHand) r.armR.add(r.brkHand);
}
function gesturePose(r, p, t) {
  const G = r.gesture, k = Math.min(1, (t - G.t0) / 0.35, (G.t1 - t) / 0.35);   // ease in and out
  const sip = 0.5 + 0.5 * Math.sin((t - G.t0) * (G.kind === 'meal' ? 5 : 2.6));
  const mix = (key, v) => { p[key] += (v - p[key]) * k; };
  if (r.hand) for (const o of r.hand.children) if (o.userData.steam !== undefined) o.position.y = 0.12 + ((t * 0.6 + o.userData.steam / 3) % 1) * 0.2;
  if (G.kind === 'cheer') { const pump = Math.abs(Math.sin((t - G.t0) * 9)); mix('aRx', -0.3); mix('aRz', -2.5 + pump * 0.35); mix('headX', -0.15); return; }
  // Arms forward (not up: a raised hand ends inside the head), the thing lifted toward the face and back.
  if (G.kind === 'meal') {                                  // the bowl in the left hand, chopsticks to the mouth
    mix('aLx', -1.35); mix('aLz', -0.4); mix('aRx', -1.45 - sip * 0.35); mix('aRz', 0.3); mix('headX', 0.18);
  } else {                                                  // a can or a mug to the mouth, head back for the drink
    mix('aRx', -1.5 - sip * 0.3); mix('aRz', 0.45); mix('headX', G.kind === 'drink' ? -0.3 : -0.08 - sip * 0.08);
  }
}

/* ---------- props, built the first time a robot needs them ---------- */
const BUILDERS = {
  typing(r) {
    const g = S.geo, m = S.mat, group = new THREE.Group();
    if (!r.furnished) {
      const desk = new THREE.Group(); desk.position.set(0, 0.275, 0.6); group.add(desk);
      const top = new THREE.Mesh(g.deskTop, m.wood); top.position.y = 0.25; desk.add(top);
      for (const [x, z] of [[-0.44, -0.22], [0.44, -0.22], [-0.44, 0.22], [0.44, 0.22]]) { const leg = new THREE.Mesh(g.deskLeg, m.woodDark); leg.position.set(x, -0.025, z); desk.add(leg); }
    }
    const laptop = new THREE.Group(); laptop.position.set(0, 0.55, 0.52); group.add(laptop);
    const base = new THREE.Mesh(g.laptopBase, m.laptop); base.position.y = 0.0125; laptop.add(base);
    const keys = new THREE.Mesh(g.keys, m.keys); keys.rotation.x = -Math.PI / 2; keys.position.set(0, 0.0262, -0.03); laptop.add(keys);
    const lid = new THREE.Group(); lid.position.set(0, 0.025, 0.18); lid.rotation.x = 0.28; laptop.add(lid);
    const shell = new THREE.Mesh(g.laptopLid, m.laptop); shell.position.y = 0.2; lid.add(shell);
    const logo = new THREE.Mesh(g.lidLogo, r.logoMat); logo.position.set(0, 0.2, 0.0115); lid.add(logo);
    const screen = new THREE.Mesh(g.lidScreen, m.code); screen.position.set(0, 0.2, -0.0115); screen.rotation.y = Math.PI; lid.add(screen);
    return { group };
  },
  background(r) { return BUILDERS.typing(r); },   // the same laptop (and desk where the room has none) as typing
  reading(r) {
    const g = S.geo, m = S.mat, group = new THREE.Group();
    const book = new THREE.Group(); book.position.set(0, 0.93, 0.47); book.rotation.x = -0.35; book.scale.setScalar(1.2); group.add(book);
    for (const side of [-1, 1]) {
      const hinge = new THREE.Group(); hinge.rotation.y = side * 0.42; book.add(hinge);
      const panel = new THREE.Mesh(g.bookPanel, m.bookShell); panel.position.set(side * 0.105, 0, 0); hinge.add(panel);
      const pages = new THREE.Mesh(g.bookPages, m.pages); pages.position.set(side * 0.1, 0, -0.016); hinge.add(pages);
      if (side === 1) { const cover = new THREE.Mesh(g.bookCover, m.cover); cover.position.set(0.105, 0, 0.0085); hinge.add(cover); }
    }
    return { group, update(s) { book.position.y = 0.93 + Math.sin(s * 0.8) * 0.008; } };
  },
  command(r) {
    const g = S.geo, m = S.mat, group = new THREE.Group();
    r.termCanvas = makeCanvas(384, 256);
    r.termTex = texFrom(r.termCanvas);
    const holo = new THREE.Group(); holo.position.set(-0.88, 0.92, 0.3); holo.rotation.y = 0.75; holo.scale.setScalar(0.84); group.add(holo);
    holo.add(new THREE.Mesh(g.term, new THREE.MeshBasicMaterial({ map: r.termTex, transparent: true, side: THREE.DoubleSide, depthWrite: false })));
    const projector = new THREE.Group(); projector.position.set(-0.88, 0.025, 0.3); group.add(projector);
    projector.add(new THREE.Mesh(g.projector, m.projector));
    const beam = new THREE.Mesh(g.beam, m.beam); beam.position.y = 0.34; projector.add(beam);
    r.gearMat = m.gear.clone();
    const gear = new THREE.Sprite(r.gearMat); gear.position.set(-0.32, 2.02, 0.05); gear.scale.set(0.3, 0.3, 1); group.add(gear);
    drawTerminal(r, 0);
    return {
      group,
      update(s) {
        holo.position.y = 0.92 + Math.sin(s * 1.6) * 0.02;
        r.gearMat.rotation = -s * 1.8;
        if (s > r.termAt) { drawTerminal(r, s); r.termAt = s + 0.12; }
      },
    };
  },
  phone(r) {
    const g = S.geo, m = S.mat, group = new THREE.Group();
    r.phoneCanvas = makeCanvas(240, 400);
    r.phoneTex = texFrom(r.phoneCanvas);
    r.phoneScreenTex = r.phoneTex.clone();
    r.phoneScreenTex.repeat.set(0.8, 0.8);
    r.phoneScreenTex.offset.set(0.1, 0.14);
    const phone = new THREE.Group(); phone.position.set(0, 0.84, 0.47); faceToward(phone, LOOK); group.add(phone);
    phone.add(new THREE.Mesh(g.phoneBody, m.phone));
    const screen = new THREE.Mesh(g.phoneScreen, new THREE.MeshBasicMaterial({ map: r.phoneScreenTex })); screen.position.z = 0.0155; phone.add(screen);
    const cam = new THREE.Mesh(g.phoneCam, m.limb); cam.position.set(0.05, 0.12, -0.019); phone.add(cam);
    const logo = new THREE.Mesh(g.phoneLogo, r.logoMat); logo.position.set(0, -0.03, -0.0155); logo.rotation.y = Math.PI; phone.add(logo);
    const bubble = new THREE.Sprite(new THREE.SpriteMaterial({ map: r.phoneTex, transparent: true }));
    bubble.position.set(0.95, 1.72, 0.15); bubble.scale.set(0.42, 0.7, 1); group.add(bubble);
    (r.drawPhone || drawPhoneUI)(r, 0);
    return {
      group,
      update(s) {
        bubble.position.y = 1.72 + Math.sin(s * 2) * 0.025;
        if (s > r.phoneAt) { (r.drawPhone || drawPhoneUI)(r, s); r.phoneAt = s + 0.1; }
      },
    };
  },
  thinking(r) {
    const group = new THREE.Group();
    const canvas = makeCanvas(160, 112), tex = texFrom(canvas);
    const draw = (lit) => {
      const ctx = canvas.getContext('2d');
      ctx.clearRect(0, 0, 160, 112);
      ctx.fillStyle = '#ffffff'; ctx.strokeStyle = '#8a9bb0'; ctx.lineWidth = 4;
      ctx.beginPath(); ctx.ellipse(86, 46, 66, 38, 0, 0, Math.PI * 2); ctx.fill(); ctx.stroke();
      for (const [x, y, rr] of [[30, 92, 9], [14, 106, 5]]) { ctx.beginPath(); ctx.arc(x, y, rr, 0, Math.PI * 2); ctx.fill(); ctx.stroke(); }
      for (let i = 0; i < 3; i++) { ctx.fillStyle = lit < 0 || i <= lit ? '#2f6fd8' : '#c8d3e3'; ctx.beginPath(); ctx.arc(58 + i * 28, 47, 9, 0, Math.PI * 2); ctx.fill(); }
      tex.needsUpdate = true;
    };
    draw(reduceMotion ? -1 : 0);
    const bubble = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, transparent: true }));
    bubble.position.set(0.62, 1.95, 0.1); bubble.scale.set(0.62, 0.43, 1); group.add(bubble);
    let shown = 0;
    return {
      group,
      update(s) {
        if (reduceMotion) return;
        bubble.position.y = 1.95 + Math.sin(s * 1.3) * 0.02;
        const lit = Math.floor(s * 2.2) % 3;
        if (lit !== shown) { shown = lit; draw(lit); }
      },
    };
  },
  waiting() {
    const group = new THREE.Group();
    const bubble = new THREE.Sprite(S.mat.alert); bubble.position.set(0.6, 1.95, 0.1); bubble.scale.set(0.42, 0.462, 1); group.add(bubble);
    return { group, update(s) { bubble.position.y = 1.95 + Math.sin(s * 4) * 0.035; } };
  },
  carry(r) {
    // up to CARRY_MAX sheets; r.carrySheets (the box, 2.3.4: the amount of a push or a pull) shows that many, 4 otherwise
    const g = S.geo, m = S.mat, group = new THREE.Group();
    const stack = new THREE.Group(); stack.position.set(0, 0.64, 0.4); group.add(stack);
    const sheets = [];
    for (let i = 0; i < CARRY_MAX; i++) { const sheet = new THREE.Mesh(g.sheet, m.sheets[i % 4]); sheet.position.y = i * 0.034; sheet.rotation.y = (i % 2 ? 1 : -1) * 0.05 * (i % 5); stack.add(sheet); sheets.push(sheet); }
    return { group, update(s) {
      const n = Math.max(1, Math.min(CARRY_MAX, r && Number.isFinite(r.carrySheets) ? r.carrySheets : 4));
      sheets.forEach((sh, i) => { sh.visible = i < n; });
      stack.position.y = 0.64 + Math.abs(Math.cos(s * 7)) * 0.03;
    } };
  },
  done() {
    const group = new THREE.Group();
    const pieces = [];
    for (let i = 0; i < 26; i++) {
      const piece = new THREE.Mesh(S.geo.confetti, S.mat.confetti[i % S.mat.confetti.length]);
      Object.assign(piece.userData, { x: (Math.random() - 0.5) * 1.8, z: (Math.random() - 0.5) * 1.2, speed: 0.25 + Math.random() * 0.25, phase: Math.random(), spin: 2 + Math.random() * 4 });
      group.add(piece); pieces.push(piece);
    }
    return {
      group,
      update(s) {
        for (const p of pieces) {
          const d = p.userData, k = (s * d.speed + d.phase) % 1;
          p.position.set(d.x + Math.sin(s * 2 + d.phase * 6) * 0.08, 2.35 - k * 2.2, d.z);
          p.rotation.set(s * d.spin, s * d.spin * 0.7, 0);
        }
      },
    };
  },
};
const CARRY_MAX = 12;
function ensureProps(r, state) {
  if (r.props[state] || !BUILDERS[state]) return;
  const pr = BUILDERS[state](r);
  pr.group.visible = false;
  r.root.add(pr.group);
  r.props[state] = pr;
}

/* ---------- poses ---------- */
function poseFor(state, s) {
  const p = { rootY: 0, hipsY: 0, torsoX: 0, torsoY: 0, headX: 0, headY: 0, headZ: 0, aLx: 0, aLz: 0.12, aRx: 0, aRz: -0.12, lLx: 0, lRx: 0 };
  switch (state) {
    case 'idle': {
      const b = Math.sin(s * 2.1);
      p.hipsY = b * 0.012;
      p.headY = Math.sin(s * 0.55) * 0.38; p.headX = Math.sin(s * 0.8) * 0.05 - 0.02; p.headZ = Math.sin(s * 0.65) * 0.05;
      p.aLx = b * 0.06; p.aRx = -b * 0.06;
      break;
    }
    case 'thinking': {
      const sway = reduceMotion ? 0 : Math.sin(s * 0.9);
      p.headZ = 0.24 + sway * 0.08; p.headX = -0.14; p.headY = 0.18 + sway * 0.06;
      p.aRx = -2.05; p.aRz = -0.95;           // a hand to the chin
      p.aLx = -1.0; p.aLz = -0.55;            // the other arm folded
      p.torsoY = sway * 0.04; p.hipsY = reduceMotion ? 0 : Math.sin(s * 1.8) * 0.006;
      break;
    }
    case 'background': {   // at its desk with the headset on, typing now and then while the work runs in the background
      const nod = reduceMotion ? 0 : Math.sin(s * 2.2);   // nodding along to the music
      p.torsoX = 0.04; p.headX = 0.2 + nod * 0.035; p.headY = Math.sin(s * 0.35) * 0.06; p.headZ = nod * 0.03;
      p.hipsY = reduceMotion ? 0 : Math.sin(s * 1.4) * 0.006;
      // the keys, loosely: slower (6 against 15) and smaller (0.05 against 0.13) than 'typing'
      p.aLx = -1.0 + Math.max(0, Math.sin(s * 6)) * 0.05; p.aLz = -0.3;
      p.aRx = -1.0 + Math.max(0, Math.sin(s * 6 + 2.6)) * 0.05; p.aRz = 0.3;
      break;
    }
    case 'typing':
      p.torsoX = 0.06; p.headX = 0.2 + Math.sin(s * 1.2) * 0.03; p.headY = Math.sin(s * 0.45) * 0.08;
      p.aLx = -1.05 + Math.max(0, Math.sin(s * 15)) * 0.13; p.aLz = -0.32;
      p.aRx = -1.05 + Math.max(0, Math.sin(s * 15 + 1.9)) * 0.13; p.aRz = 0.32;
      break;
    case 'reading':
      p.headX = 0.3 + Math.sin(s * 0.7) * 0.03; p.headY = Math.sin(s * 0.3) * 0.12;
      p.aLx = -1.25; p.aLz = -0.55; p.aRx = -1.25; p.aRz = 0.55;
      break;
    case 'readingWeb': {   // over the dictionary on the desk: the left hand holds its pages, the right one turns them
      const f = dictHand(s);
      p.torsoX = 0.06; p.headX = 0.42 + Math.sin(s * 0.7) * 0.02; p.headY = -0.1 + f * 0.16;
      p.aLx = -0.95; p.aLz = -0.3;
      p.aRx = -0.95 - f * 0.25; p.aRz = 0.2 + f * 0.45;
      break;
    }
    case 'command': {
      const tap = Math.max(0, Math.sin(s * 5));
      p.headY = -0.55; p.headX = -0.02; p.torsoY = -0.15;
      p.aRx = -1.5 + tap * 0.12; p.aRz = -0.7; p.aLx = 0.05; p.aLz = 0.18;
      break;
    }
    case 'phone':
      p.headX = 0.34 + Math.sin(s * 0.9) * 0.02; p.headZ = Math.sin(s * 0.7) * 0.05;
      p.aLx = -1.35 + Math.max(0, Math.sin(s * 8)) * 0.07; p.aLz = -0.72;
      p.aRx = -1.35 + Math.max(0, Math.sin(s * 8 + 2.2)) * 0.07; p.aRz = 0.72;
      break;
    case 'waiting':
      p.aRz = -2.7 + Math.sin(s * 7) * 0.2; p.aRx = -0.1; p.aLz = 0.2;
      p.headX = -0.12; p.headZ = Math.sin(s * 1.6) * 0.06; p.hipsY = Math.abs(Math.sin(s * 3.5)) * 0.02;
      break;
    case 'stroll': {
      const w = s * 7;
      p.lLx = Math.sin(w) * 0.5; p.lRx = -Math.sin(w) * 0.5; p.hipsY = Math.abs(Math.cos(w)) * 0.03;
      p.aLx = -Math.sin(w) * 0.4; p.aRx = Math.sin(w) * 0.4; p.headX = -0.02;
      break;
    }
    case 'carry': {
      const w = s * 7;
      p.lLx = Math.sin(w) * 0.5; p.lRx = -Math.sin(w) * 0.5; p.hipsY = Math.abs(Math.cos(w)) * 0.03; p.torsoY = Math.sin(w) * 0.05;
      p.aLx = -0.95; p.aLz = -0.5; p.aRx = -0.95; p.aRz = 0.5; p.headX = 0.04;
      break;
    }
    case 'done': {
      const j = Math.max(0, Math.sin(s * 4.2));
      p.rootY = j * 0.15;
      p.aLz = 2.55 + Math.sin(s * 8.4) * 0.12; p.aRz = -2.55 - Math.sin(s * 8.4) * 0.12;
      p.lLx = -j * 0.25; p.lRx = -j * 0.25; p.headX = -0.15;
      break;
    }
    default: break;
  }
  return p;
}
function updateRobot(r, t, dt) {
  const s = t * SPEED * (r.tired ? 0.7 : 1) + r.seed;    // tired: a little slower
  r.blend = Math.min(1, r.blend + dt / 0.4);
  const e = r.blend * r.blend * (3 - 2 * r.blend);
  const look = lookUpdate(r, t, dt), heavy = !!look;
  // heavy: fast typing (drained: slower than fired)
  const posed = (state) => (state === 'reading' && r.readKind === 'web' ? 'readingWeb' : state);   // the dictionary (10-20)
  const a = poseFor(posed(r.prev), s), b = heavy ? poseFor('typing', s * (look === 'drained' ? 1.5 : 2.4)) : poseFor(posed(r.state), s);
  sweatUpdate(r, s, heavy);
  const p = {};
  for (const k in b) p[k] = a[k] + (b[k] - a[k]) * e;
  if (look === 'drained') { p.headX += 0.12; }             // head a little down over the long wait
  if ((look === 'whistle' || r.launch) && !reduceMotion) { // one arm up waving the team on, the other pointing
    // the right arm up beside the head (as the done cheer, so the head does not hide it), waving; the left pointing
    p.aRx = Math.sin(t * 7) * 0.25; p.aRz = -2.85 + Math.sin(t * 7) * 0.3; p.aLx = -1.35; p.aLz = 0.15; p.headY = Math.sin(t * 3.5) * 0.15;
  }
  if (r.tired) { p.headX += 0.2; p.torsoX += 0.08; p.hipsY -= 0.012; p.aLz *= 0.5; p.aRz *= 0.5; }   // head and shoulders down
  if (r.gesture && (!GESTURE_OK.has(r.state) || t >= r.gesture.t1)) endGesture(r);
  const onCall = callUpdate(r, t);
  if (!onCall && !r.gesture && r.needDrink && GESTURE_OK.has(r.state) && startGesture(r, 'drink', t)) r.needDrink = false;
  if (onCall) callPose(p, t);
  else if (r.play) playPose(r, p, t);
  else if (r.solo) soloPose(r, p, t);
  else if (r.brk) brkPose(r, p, t);
  else if (r.gesture) gesturePose(r, p, t);
  soloProps(r, onCall ? null : r.solo, t);
  brkProps(r, onCall ? null : r.brk, t);
  playBubble(r, onCall ? null : r.play, t);
  bgUpdate(r, t, r.state === 'background' && look !== 'whistle' && !onCall && !r.play && !r.solo && !r.brk);   // the whistle takes the headset off
  r.antenna.rotation.x += ((r.tired ? 1.0 : 0) - r.antenna.rotation.x) * Math.min(1, dt * 3);
  r.root.position.y = p.rootY;
  r.hips.position.y = HIPS_Y + p.hipsY;
  r.torso.rotation.set(p.torsoX, p.torsoY, 0);
  r.head.rotation.set(p.headX, p.headY, p.headZ);
  r.armL.rotation.set(p.aLx, 0, p.aLz);
  r.armR.rotation.set(p.aRx, 0, p.aRz);
  r.legL.rotation.x = p.lLx;
  r.legR.rotation.x = p.lRx;
  r.tails.forEach((tail, i) => tail.rotation.set(0.5 + Math.sin(s * 6.5 + i * 1.3) * 0.12, 0, tail.userData.spread));

  const lampKey = STATES[r.lampState && STATES[r.lampState] ? r.lampState : r.state].lamp;   // play: the real state's lamp
  const lampOn = lampKey === 'think' ? (reduceMotion || Math.sin(s * 1.6) > -0.4)   // thinking: a slow blink
    : lampKey !== 'done' || Math.floor(s * 3) % 2 === 0;
  r.lampMat.color.set(lampOn ? LAMP[lampKey] : LAMP.off);

  let mode = STATES[r.blend < 0.5 ? r.prev : r.state].face;
  if (r.tired && mode === 'normal') mode = 'tired';
  if (look) mode = look;                                     // heavy work's face over the state's and the tired one
  if (r.launch) mode = 'whistle';                            // calling a subagent: the whistle's face for its moment
  if (mode === 'normal' || mode === 'focus' || mode === 'tired' || mode === 'fired') {
    if (s > r.nextBlink) { r.blinkEnd = s + 0.12; r.nextBlink = s + 2.4 + Math.random() * 3.2; }
    if (s < r.blinkEnd) mode = 'blink';
  }
  const tint = r.tint && r.tint[3] > 0.01 ? r.tint.map((v, i) => (i < 3 ? Math.round(v / 8) * 8 : Math.round(v * 40) / 40)) : null;
  const faceKey = `${mode}|${tint ? tint.join(',') : ''}`;   // the colour in steps: redrawn a few times while it eases
  if (faceKey !== r.faceMode) { drawFace(r.faceCtx, mode, tint); r.faceTex.needsUpdate = true; r.faceMode = faceKey; }

  let dictK = 0;
  for (const key in r.props) {
    const pr = r.props[key];
    let k = key === r.state ? e : (key === r.prev && r.prev !== r.state ? 1 - e : 0);
    if (key === 'reading' && r.readKind === 'web') { dictK = k; k = 0; }   // the dictionary on the desk, not the book
    pr.group.visible = k > 0.02;
    if (!pr.group.visible) continue;
    for (const child of pr.group.children) {
      const base = child.userData.base || (child.userData.base = child.scale.clone());
      child.scale.copy(base).multiplyScalar(Math.max(0.001, k));
    }
    if (pr.update) pr.update(s);
  }
  dictUpdate(r, s, dictK);
}
function setRobotState(r, state) {
  if (state === r.state) return;
  ensureProps(r, state);
  r.prev = r.state; r.state = state; r.blend = 0;
}

