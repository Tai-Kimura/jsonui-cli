import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { RoundedBoxGeometry } from 'three/addons/geometries/RoundedBoxGeometry.js';

const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
const SPEED = reduceMotion ? 0.35 : 1;

const FONT_DISPLAY = '"Dela Gothic One", "Hiragino Sans", "Yu Gothic", sans-serif';
const FONT_BODY = '"BIZ UDPGothic", "Hiragino Sans", "Yu Gothic", sans-serif';
const FONT_MONO = '"JetBrains Mono", ui-monospace, Menlo, monospace';

const ROLES = {
  main: { name: 'メイン', color: '#ff7a3d' },
  define: { name: 'define', color: '#7d5cff' },
  ground: { name: 'ground', color: '#b07a52' },
  implement: { name: 'implement', color: '#2f80ed' },
  navigation: { name: 'navigation', color: '#10a693' },
  test: { name: 'test', color: '#3fae4a' },
  debug: { name: 'debug', color: '#f0b400' },
  other: { name: 'その他', color: '#8a9bb0' },
};
const COL = {
  shell: '#e8ecf3', limb: '#394150', screen: '#0f1830', eye: '#a6fbff',
  band: '#fffdf7', bandInk: '#d62839', wood: '#c99f73', woodDark: '#9e7752',
  laptop: '#c9d0db', phone: '#1f2532',
};
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
function drawFace(ctx, mode) {
  const W = ctx.canvas.width, H = ctx.canvas.height;
  ctx.clearRect(0, 0, W, H);
  rr(ctx, 3, 3, W - 6, H - 6, 34); ctx.fillStyle = COL.screen; ctx.fill();
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
  }
  ctx.lineWidth = 6; ctx.beginPath();
  if (mode === 'happy') ctx.arc(cx, 86, 14, Math.PI * 0.1, Math.PI * 0.9);
  else if (mode === 'wide') ctx.arc(cx, 98, 7, 0, Math.PI * 2);
  else if (mode === 'focus') { ctx.moveTo(cx - 9, 97); ctx.lineTo(cx + 9, 97); }
  else ctx.arc(cx, 86, 10, Math.PI * 0.2, Math.PI * 0.8);
  ctx.stroke();
  ctx.restore();
  if (mode === 'tired') {                                  // bags under the eyes
    ctx.strokeStyle = 'rgba(170, 120, 255, 0.85)'; ctx.lineWidth = 4;
    for (const side of [-1, 1]) { ctx.beginPath(); ctx.arc(cx + side * dx, ey + 26, 15, Math.PI * 0.15, Math.PI * 0.85); ctx.stroke(); }
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
  const accent = ROLES[r.role].color;
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
  ctx.fillStyle = 'rgba(255, 255, 255, 0.92)'; ctx.font = `700 11px ${FONT_MONO}`; ctx.fillText('9:41', sx + 12, sy + 17); ctx.fillRect(sx + sw - 32, sy + 8, 18, 9);
  ctx.fillStyle = '#ffffff'; ctx.font = `700 19px ${FONT_BODY}`; ctx.fillText('ログイン', sx + 14, sy + 50);
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
  ctx.fillStyle = '#ffffff'; ctx.font = `700 15px ${FONT_BODY}`; ctx.textAlign = 'center'; ctx.fillText('ログイン', sx + sw / 2, by + 26);
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
    confetti: ['#d62839', '#ffb020', '#35d07f', '#2f80ed', '#7d5cff', '#ff7a3d'].map((c) => new THREE.MeshBasicMaterial({ color: c, side: THREE.DoubleSide })),
  };
}

/* ---------- the robot ---------- */
function faceToward(obj, target) {
  const m = new THREE.Matrix4().lookAt(target, obj.position, UP);
  obj.quaternion.setFromRotationMatrix(m);
}
function createRobot({ label = 'a0', role = 'main', state = 'idle', seed = 0, furnished = false }) {
  const g = S.geo, m = S.mat;
  const r = { label, role, state, prev: state, blend: 1, seed, props: {}, faceMode: '', nextBlink: 1 + (seed % 2), blinkEnd: 0, termAt: 0, phoneAt: 0,
    tired: false, needDrink: false, drinks: 0, gesture: null, hand: null, heavy: false, sweat: null };
  r.furnished = furnished;
  r.accent = toon(ROLES[role].color);
  r.lampMat = new THREE.MeshBasicMaterial({ color: LAMP.idle });
  r.logoCanvas = makeCanvas(96, 64);
  r.logoTex = texFrom(r.logoCanvas);
  r.logoMat = new THREE.MeshBasicMaterial({ map: r.logoTex, transparent: true });
  r.root = new THREE.Group();

  r.hips = new THREE.Group(); r.hips.position.y = HIPS_Y; r.root.add(r.hips);
  const pelvis = new THREE.Mesh(g.pelvis, m.limb); pelvis.position.y = 0.03; r.hips.add(pelvis);
  const leg = (x) => {
    const pivot = new THREE.Group(); pivot.position.set(x, 0, 0); r.hips.add(pivot);
    const shin = new THREE.Mesh(g.leg, m.limb); shin.position.y = -0.15; pivot.add(shin);
    const foot = new THREE.Mesh(g.foot, r.accent); foot.position.set(0, -0.31, 0.04); pivot.add(foot);
    return pivot;
  };
  r.legL = leg(0.17); r.legR = leg(-0.17);

  r.torso = new THREE.Group(); r.hips.add(r.torso);
  const body = new THREE.Mesh(g.torso, m.shell); body.position.y = 0.32; r.torso.add(body);
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
    const upper = new THREE.Mesh(g.arm, m.limb); upper.position.y = -0.18; pivot.add(upper);
    const hand = new THREE.Mesh(g.hand, m.shell); hand.position.y = -0.38; pivot.add(hand);
    return pivot;
  };
  r.armL = arm(0.42); r.armR = arm(-0.42);
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
  if (reduceMotion || !GESTURE_OK.has(r.state) || r.play || (r.call && CALL_ON_LINE.has(r.call.state))) return false;
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
   long). r.play is { kind: 'ball' | 'highfive' | 'rps', t0, side: 0 | 1 } while at the spot; the state stays idle.
   ball: a throw from the right hand, the two in turn (the ball itself is the scene's); highfive: both hands up,
   meeting now and then; rps (じゃんけん): three pumps, then a hand over the head. */
const RPS_HANDS = ['グー', 'チョキ', 'パー'];
function playPose(r, p, t) {
  const P = r.play, u = t - P.t0;
  if (P.kind === 'ball') {
    const turn = ((u / 1.6) + P.side * 0.5) % 1;           // the two throw half a period apart
    const throwing = turn < 0.25;
    p.aRx = throwing ? -2.4 + turn * 6 : -0.9; p.aRz = -0.25; p.aLx = -0.7; p.aLz = 0.3; p.headX = -0.18;
  } else if (P.kind === 'highfive') {
    const meet = Math.max(0, Math.sin(u * 2.6));
    p.aRz = -2.4 - meet * 0.3; p.aRx = -0.2 - meet * 0.4; p.aLz = 0.4; p.rootY = meet * 0.08; p.headX = -0.12;
  } else {
    const round = u % 3, pump = round < 1.8 ? Math.abs(Math.sin(round * Math.PI * 1.67)) : 0;
    p.aRx = -1.2 - pump * 0.5; p.aRz = -0.3; p.aLx = -0.4; p.headX = 0.05;
  }
}
function playBubble(r, P, t) {
  const show = !!P && P.kind === 'rps' && (t - P.t0) % 3 >= 1.8;
  if (show && !r.rps) {
    r.rpsCanvas = makeCanvas(200, 120);
    r.rps = new THREE.Sprite(new THREE.SpriteMaterial({ map: texFrom(r.rpsCanvas), transparent: true }));
    r.rps.position.set(0, 2.25, 0.1); r.rps.scale.set(0.6, 0.36, 1); r.root.add(r.rps); r.rpsShown = '';
  }
  if (!r.rps) return;
  r.rps.visible = show;
  if (!show) return;
  const hand = RPS_HANDS[(Math.floor((t - P.t0) / 3) * 7 + P.side * 5 + (r.seed | 0)) % 3];
  if (hand === r.rpsShown) return;
  r.rpsShown = hand;
  const ctx = r.rpsCanvas.getContext('2d');
  ctx.clearRect(0, 0, 200, 120);
  ctx.fillStyle = '#ffffff'; ctx.strokeStyle = '#1f2532'; ctx.lineWidth = 5;
  rr(ctx, 6, 6, 188, 108, 26); ctx.fill(); ctx.stroke();
  ctx.fillStyle = '#1f2532'; ctx.font = `700 46px ${FONT_BODY}`; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
  ctx.fillText(hand, 100, 62);
  r.rps.material.map.needsUpdate = true;
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
  carry() {
    const g = S.geo, m = S.mat, group = new THREE.Group();
    const stack = new THREE.Group(); stack.position.set(0, 0.64, 0.4); group.add(stack);
    for (let i = 0; i < 4; i++) { const sheet = new THREE.Mesh(g.sheet, m.sheets[i]); sheet.position.y = i * 0.034; sheet.rotation.y = (i % 2 ? 1 : -1) * 0.05 * i; stack.add(sheet); }
    return { group, update(s) { stack.position.y = 0.64 + Math.abs(Math.cos(s * 7)) * 0.03; } };
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
    case 'background': {   // at its desk, watching the screen while the work runs in the background
      const look = reduceMotion ? 0 : Math.sin(s * 0.35);
      p.torsoX = 0.04; p.headX = 0.22 + look * 0.02; p.headY = look * 0.06; p.hipsY = reduceMotion ? 0 : Math.sin(s * 1.4) * 0.006;
      p.aLx = -0.85; p.aLz = -0.28; p.aRx = -0.85; p.aRz = 0.28;   // hands resting on the desk
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
  const heavy = r.heavy && HEAVY_OK.has(r.state);
  const a = poseFor(r.prev, s), b = heavy ? poseFor('typing', s * 2.4) : poseFor(r.state, s);   // heavy: fast typing
  sweatUpdate(r, s, heavy);
  const p = {};
  for (const k in b) p[k] = a[k] + (b[k] - a[k]) * e;
  if (r.tired) { p.headX += 0.2; p.torsoX += 0.08; p.hipsY -= 0.012; p.aLz *= 0.5; p.aRz *= 0.5; }   // head and shoulders down
  if (r.gesture && (!GESTURE_OK.has(r.state) || t >= r.gesture.t1)) endGesture(r);
  const onCall = callUpdate(r, t);
  if (!onCall && !r.gesture && r.needDrink && GESTURE_OK.has(r.state) && startGesture(r, 'drink', t)) r.needDrink = false;
  if (onCall) callPose(p, t);
  else if (r.play) playPose(r, p, t);
  else if (r.gesture) gesturePose(r, p, t);
  playBubble(r, onCall ? null : r.play, t);
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
  if (mode === 'normal' || mode === 'focus' || mode === 'tired') {
    if (s > r.nextBlink) { r.blinkEnd = s + 0.12; r.nextBlink = s + 2.4 + Math.random() * 3.2; }
    if (s < r.blinkEnd) mode = 'blink';
  }
  if (mode !== r.faceMode) { drawFace(r.faceCtx, mode); r.faceTex.needsUpdate = true; r.faceMode = mode; }

  for (const key in r.props) {
    const pr = r.props[key];
    const k = key === r.state ? e : (key === r.prev && r.prev !== r.state ? 1 - e : 0);
    pr.group.visible = k > 0.02;
    if (!pr.group.visible) continue;
    for (const child of pr.group.children) {
      const base = child.userData.base || (child.userData.base = child.scale.clone());
      child.scale.copy(base).multiplyScalar(Math.max(0.001, k));
    }
    if (pr.update) pr.update(s);
  }
}
function setRobotState(r, state) {
  if (state === r.state) return;
  ensureProps(r, state);
  r.prev = r.state; r.state = state; r.blend = 0;
}

