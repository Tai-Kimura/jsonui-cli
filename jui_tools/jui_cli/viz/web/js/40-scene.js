
/* ---------- 3D office ---------- */
let has3D = true;
let renderer = null;
try {
  renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
} catch (err) {
  has3D = false;
  sceneEl.insertAdjacentHTML('beforeend', '<p class="nogl">この環境では WebGL を使えないため 3D 表示を出せません。右のパネルとイベント欄はそのまま動きます。</p>');
}
let latestModel = computeModel(START_AT);
let scene, camera, controls;
const robots = [];
const roomMats = [];
const roomTags = [];
const links = {};
let sbCanvas, sbTex, tbCanvas, tbTex, kbCanvas, kbTex, standMat, standOffTex, boardMesh, kbMesh, trayGroup, selRing, trayPending = [], trayDone = [], trayTag;

/* The shop-app spec board: one tile per screen spec of that project, seven section bars per tile. */
const SHOP_IDX = SPECS.map((s, i) => [s, i]).filter(([s]) => s.project === 'shop').map(([, i]) => i);
const SHOP_POS = Object.fromEntries(SHOP_IDX.map((i, pos) => [i, pos]));
const SB = { cx: -4.0, cy: 2.55, z: -4.98, w: 6.8, h: 2.3, W: 2048, H: 693, pad: 22, gap: 14, top: 76, cols: 6, segGap: 6 };
SB.rows = Math.ceil(SHOP_IDX.length / SB.cols);
SB.tw = (SB.W - SB.pad * 2 - SB.gap * (SB.cols - 1)) / SB.cols;
SB.th = (SB.H - SB.top - SB.pad - SB.gap * (SB.rows - 1)) / SB.rows;
SB.segW = (SB.tw - 36 - SB.segGap * 6) / 7;
const sbTile = (i) => ({ x: SB.pad + (i % SB.cols) * (SB.tw + SB.gap), y: SB.top + Math.floor(i / SB.cols) * (SB.th + SB.gap) });
/* Tile layouts: the big tiles of the shop-app board and the smaller ones on the other rooms' boards. */
const SBG = { pad: 18, name: 30, nameY: 46, status: 19, statusY: 80, segH: 20, segBottom: 18, segGap: 6, pillW: 66, pillH: 36, pillFont: 24 };
const PBG = { pad: 14, name: 24, nameY: 36, status: 16, statusY: 62, segH: 16, segBottom: 13, segGap: 5, pillW: 54, pillH: 28, pillFont: 19 };
const segW = (w, g) => (w - g.pad * 2 - g.segGap * 6) / 7;
function tileFocus(x, y, w, h, g, k) {
  const sw = segW(w, g);
  return k >= 0 ? [x + g.pad + k * (sw + g.segGap) + sw / 2, y + h - g.segBottom - g.segH / 2] : [x + w / 2, y + g.nameY - 10];
}
function sbFocus(pos, k) { const p = sbTile(pos); return tileFocus(p.x, p.y, SB.tw, SB.th, SBG, k); }
/* The other project rooms: a wall board in jsonui-cli/, an easel in JsonUIDocument/. */
const PBOARDS = [
  { project: 'cli', W: 1024, H: 560, w: 3.4, h: 1.86, wall: { cx: 6.6, cy: 2.35, z: -4.98 } },
  { project: 'doc', W: 1024, H: 720, w: 2.15, h: 1.51, easel: { x: 4.35, z: 1.2, ry: 0.42, bottom: 0.95 } },
].map((pb) => ({ ...pb, specs: SPECS.map((s, i) => [s, i]).filter(([s]) => s.project === pb.project).map(([, i]) => i), tiles: [], splitY: 0 }));
const PBOARD = Object.fromEntries(PBOARDS.map((pb) => [pb.project, pb]));
const pbPoint = (pb, px, py) => pb.mesh.localToWorld(new THREE.Vector3((px / pb.W - 0.5) * pb.w, (0.5 - py / pb.H) * pb.h, 0.03));
const TB = { x: -9.57, cy: 2.05, cz: 1.5, w: 2.6, h: 2.08, W: 1024, H: 820 };
const tbRowTop = (i) => 186 + i * 78;
const TB_DEMO = TB;
/* The task board: a cork board beside the spec board, one column per task state. */
const KB = { cx: 1.12, cy: 2.55, z: -4.98, w: 2.8, h: 2.3, W: 1024, H: 842 };

function sbPoint(px, py) { return new THREE.Vector3(SB.cx + (px / SB.W - 0.5) * SB.w, SB.cy + (0.5 - py / SB.H) * SB.h, SB.z + 0.03); }
function tbPoint(px, py) { return new THREE.Vector3(TB.x + 0.03, TB.cy + (0.5 - py / TB.H) * TB.h, TB.cz - (px / TB.W - 0.5) * TB.w); }

/* Status chip colours on the boards, for the light and the dark theme. */
const ST_STYLE = {
  light: { idle: ['#e3eaf4', '#4b5c76'], write: ['#ebe5fd', '#5a3fd0'], written: ['#e3eaf4', '#33445e'], impl: ['#dde8fb', '#2a62c9'], verify: ['#fff0d1', '#8a5800'], 'impl-done': ['#e1f1ef', '#22706a'], paused: ['#f3ede2', '#7a5a14'], test: ['#dcf3e5', '#1d8f4e'], done: ['#dcf3e5', '#1d8f4e'] },
  dark: { idle: ['#1b2c45', '#9fb1cb'], write: ['#2a2154', '#c5b8ff'], written: ['#1b2c45', '#c9d6e8'], impl: ['#15305a', '#9cc4ff'], verify: ['#3a2b0c', '#ffc65c'], 'impl-done': ['#123733', '#6fd6c8'], paused: ['#33291a', '#e8c98a'], test: ['#123a2a', '#5ad893'], done: ['#123a2a', '#5ad893'] },
};
const BOARD = {
  light: { bg: '#16304f', grid: 'rgba(160, 200, 255, 0.07)', title: '#ffffff', sub: '#9fc3ff', tile: '#f7f9fc', done: '#eaf6ef', todo: 'rgba(255, 255, 255, 0.06)', todoLine: 'rgba(190, 210, 240, 0.5)', todoInk: '#a9bdd6', ink: '#13233a', base: '#a9b8cc', empty: '#b4c0d0', violet: '#6b4ce6', violetBg: '#e2d9fd', blue: '#2f74e0', green: '#22a35a' },
  dark: { bg: '#0b1828', grid: 'rgba(160, 200, 255, 0.045)', title: '#e4ecf8', sub: '#86b8ff', tile: '#17273e', done: '#132d22', todo: 'rgba(255, 255, 255, 0.03)', todoLine: 'rgba(120, 150, 190, 0.45)', todoInk: '#6c809c', ink: '#e4ecf8', base: '#40536f', empty: '#4a5d79', violet: '#b3a1ff', violetBg: '#2e2560', blue: '#6aa5ff', green: '#5ad893' },
};
const KB_PAL = {
  light: { cork: '#c99a62', speck: 'rgba(90, 55, 20, 0.16)', title: '#3b2410', sub: '#5c3d1e', col: 'rgba(255, 248, 236, 0.32)', ink: '#1f2a37', soft: '#55606f', pin: '#d62839', warn: '#e08a00', warnInk: '#2a1a00', note: { todo: '#fff3bf', wait: '#ffd8b5', doing: '#d5e5ff', done: '#d6f0df' }, head: { todo: '#8a6d1f', wait: '#b4561b', doing: '#2a62c9', done: '#1d8f4e' } },
  dark: { cork: '#47331f', speck: 'rgba(0, 0, 0, 0.22)', title: '#f3e6d4', sub: '#d8c3a6', col: 'rgba(0, 0, 0, 0.2)', ink: '#eef2f8', soft: '#b9c6d8', pin: '#ff6b78', warn: '#ffb020', warnInk: '#2a1a00', note: { todo: '#4a4222', wait: '#4e3322', doing: '#1f375c', done: '#1b3f2e' }, head: { todo: '#e6c766', wait: '#ffab73', doing: '#86b8ff', done: '#5ad893' } },
};

function fitText(ctx, text, x, y, maxW) {
  let s = String(text);
  if (ctx.measureText(s).width <= maxW) { ctx.fillText(s, x, y); return; }
  while (s.length > 1 && ctx.measureText(`${s}…`).width > maxW) s = s.slice(0, -1);
  ctx.fillText(`${s}…`, x, y);
}
function wrapText(ctx, text, x, y, maxW, lineH, maxLines) {
  const chars = [...String(text)];
  let line = '', n = 0;
  for (let i = 0; i < chars.length; i++) {
    if (line && ctx.measureText(line + chars[i]).width > maxW) {
      if (n === maxLines - 1) { fitText(ctx, line + chars.slice(i).join(''), x, y + n * lineH, maxW); return; }
      ctx.fillText(line, x, y + n * lineH); n++; line = chars[i];
    } else line += chars[i];
  }
  if (line) ctx.fillText(line, x, y + n * lineH);
}

function drawSpecBoard(model, now) {
  const dark = isDark(), P = BOARD[dark ? 'dark' : 'light'], ST = ST_STYLE[dark ? 'dark' : 'light'];
  const ctx = sbCanvas.getContext('2d');
  ctx.fillStyle = P.bg; ctx.fillRect(0, 0, SB.W, SB.H);
  ctx.fillStyle = P.grid;
  for (let x = 0; x < SB.W; x += 32) ctx.fillRect(x, 0, 1, SB.H);
  for (let y = 0; y < SB.H; y += 32) ctx.fillRect(0, y, SB.W, 1);
  ctx.textAlign = 'left'; ctx.textBaseline = 'alphabetic';
  ctx.fillStyle = P.title; ctx.font = `36px ${FONT_DISPLAY}`; ctx.fillText('spec ボード', SB.pad + 4, 52);
  const shop = SHOP_IDX.map((i) => model.specs[i]), c = bucketCounts(shop);
  ctx.fillStyle = P.sub; ctx.font = `700 24px ${FONT_BODY}`;
  ctx.fillText(`shop-app/ · 全 ${shop.length} 画面 · 作業中 ${c.live} · 途中 ${c.partial} · 未着手 ${c.todo} · 完了 ${c.done}`, SB.pad + 250, 50);
  ctx.font = `700 20px ${FONT_BODY}`;
  let lx = SB.W - SB.pad;
  for (const [label, color] of [['テスト済み', P.green], ['実装済み', P.blue], ['記入済み', P.base], ['書き込み中', P.violet]]) {
    const tw = ctx.measureText(label).width;
    ctx.fillStyle = P.sub; ctx.fillText(label, lx - tw, 49);
    lx -= tw + 26; rr(ctx, lx, 33, 18, 18, 4); ctx.fillStyle = color; ctx.fill(); lx -= 28;
  }
  SHOP_IDX.forEach((i, pos) => { const t = sbTile(pos); drawSpecTile(ctx, P, ST, model.specs[i], t.x, t.y, SB.tw, SB.th, now, SBG); });
  sbTex.needsUpdate = true;
}
function drawSpecTile(ctx, P, ST, s, x, y, w, h, now, g) {
  const todo = s.bucket === 'todo', role = s.by ? DEF[s.by].role : null, sw = segW(w, g);
  rr(ctx, x, y, w, h, 14);
  ctx.fillStyle = todo ? P.todo : s.bucket === 'done' ? P.done : P.tile; ctx.fill();
  if (todo) { ctx.setLineDash([10, 8]); ctx.lineWidth = 2.5; ctx.strokeStyle = P.todoLine; ctx.stroke(); ctx.setLineDash([]); }
  if (role) { rr(ctx, x + 3, y + 3, w - 6, h - 6, 12); ctx.lineWidth = 6; ctx.strokeStyle = ROLES[role].color; ctx.stroke(); }
  ctx.textAlign = 'left'; ctx.textBaseline = 'alphabetic';
  ctx.fillStyle = todo ? P.todoInk : P.ink; ctx.font = `${g.name}px ${FONT_DISPLAY}`;
  fitText(ctx, s.name, x + g.pad, y + g.nameY, w - g.pad * 2 - (role ? g.pillW + 8 : 0));
  if (role) {
    const px = x + w - g.pad - g.pillW, py = y + g.nameY - g.pillH + 6;
    rr(ctx, px, py, g.pillW, g.pillH, g.pillH / 2); ctx.fillStyle = ROLES[role].color; ctx.fill();
    ctx.fillStyle = ROLE_INK[role] || '#ffffff'; ctx.font = `700 ${g.pillFont}px ${FONT_MONO}`; ctx.textAlign = 'center'; ctx.fillText(s.by, px + g.pillW / 2, py + g.pillH * 0.72); ctx.textAlign = 'left';
  }
  ctx.font = `700 ${g.status}px ${FONT_BODY}`; ctx.fillStyle = todo ? P.todoInk : ST[s.status.kind][1];
  fitText(ctx, s.status.text, x + g.pad, y + g.statusY, w - g.pad * 2);
  const act = role ? activeSec(s) : -1, sy = y + h - g.segBottom - g.segH;
  for (let k = 0; k < 7; k++) {
    const st = secState(s, k), sx = x + g.pad + k * (sw + g.segGap);
    rr(ctx, sx, sy, sw, g.segH, 5);
    if (st.kind === 'empty') { ctx.setLineDash([5, 4]); ctx.lineWidth = 2; ctx.strokeStyle = todo ? P.todoLine : P.empty; ctx.stroke(); ctx.setLineDash([]); }
    else {
      ctx.fillStyle = st.kind === 'writing' ? P.violetBg : P.base; ctx.fill();
      const fill = { writing: P.violet, impl: P.blue, done: P.blue, test: P.green, tested: P.green }[st.kind];
      if (fill && st.f > 0) { ctx.save(); ctx.clip(); ctx.fillStyle = fill; ctx.fillRect(sx, sy, sw * st.f, g.segH); ctx.restore(); }
    }
    if (k === act) {
      rr(ctx, sx - 4, sy - 4, sw + 8, g.segH + 8, 8); ctx.lineWidth = 3.5; ctx.strokeStyle = ROLES[role].color; ctx.stroke();
      if (st.kind === 'writing' && Math.floor(now * 2.5) % 2 === 0) { ctx.fillStyle = P.violet; ctx.fillRect(sx + sw * st.f + 1, sy - 6, 3, g.segH + 12); }
    }
  }
}
/* A project room's own board: its specs (when it has screens) above, its task counts below. */
function drawProjectBoard(pb, model, now) {
  const dark = isDark(), P = BOARD[dark ? 'dark' : 'light'], ST = ST_STYLE[dark ? 'dark' : 'light'], K = KB_PAL[dark ? 'dark' : 'light'];
  const ctx = pb.canvas.getContext('2d'), { W, H } = pb, proj = PROJECT[pb.project];
  ctx.fillStyle = P.bg; ctx.fillRect(0, 0, W, H);
  ctx.fillStyle = P.grid;
  for (let x = 0; x < W; x += 32) ctx.fillRect(x, 0, 1, H);
  for (let y = 0; y < H; y += 32) ctx.fillRect(0, y, W, 1);
  ctx.textAlign = 'left'; ctx.textBaseline = 'alphabetic';
  ctx.fillStyle = P.title; ctx.font = `38px ${FONT_DISPLAY}`; fitText(ctx, proj.name, 28, 58, W - 260);
  ctx.fillStyle = P.sub; ctx.font = `600 19px ${FONT_MONO}`; ctx.fillText(proj.path, 30, 88);
  const pend = model.pending.filter((p) => projectOfRobot(p.who) === pb.project).length;
  if (pend) {
    const label = `許可待ち ${pend}`;
    ctx.font = `700 24px ${FONT_BODY}`;
    const w = ctx.measureText(label).width + 36;
    rr(ctx, W - 24 - w, 28, w, 42, 21); ctx.fillStyle = K.warn; ctx.fill();
    ctx.fillStyle = K.warnInk; ctx.fillText(label, W - 24 - w + 18, 57);
  }
  let y = 104;
  pb.tiles = [];
  if (pb.specs.length) {
    const specs = pb.specs.map((i) => model.specs[i]), c = bucketCounts(specs);
    ctx.fillStyle = P.sub; ctx.font = `700 20px ${FONT_BODY}`;
    ctx.fillText(`spec ${specs.length} 画面 · 作業中 ${c.live} · 途中 ${c.partial} · 未着手 ${c.todo} · 完了 ${c.done}`, 30, y + 20);
    const cols = 3, gap = 12, tw = (W - 56 - gap * (cols - 1)) / cols, th = 104;
    pb.specs.forEach((i, k) => {
      const x = 28 + (k % cols) * (tw + gap), ty = y + 34 + Math.floor(k / cols) * (th + gap);
      drawSpecTile(ctx, P, ST, model.specs[i], x, ty, tw, th, now, PBG);
      pb.tiles.push({ i, x, y: ty, w: tw, h: th });
    });
    y += 34 + Math.ceil(pb.specs.length / cols) * (th + gap);
  }
  pb.splitY = y;
  const tasks = model.tasks.filter((x) => PROJECT_OF[x.list] === pb.project);
  ctx.fillStyle = P.title; ctx.font = `700 23px ${FONT_BODY}`; ctx.fillText(`タスク ${tasks.length} 件`, 30, y + 34);
  const bw = (W - 56 - 3 * 12) / 4, by = y + 48, bh = 78;
  KCOLS.forEach(([col, label], c) => {
    const x = 28 + c * (bw + 12), n = tasks.filter((t) => t.col === col).length;
    rr(ctx, x, by, bw, bh, 10); ctx.fillStyle = K.note[col]; ctx.fill();
    ctx.fillStyle = K.ink; ctx.font = `700 20px ${FONT_BODY}`; ctx.fillText(label, x + 14, by + 32);
    ctx.fillStyle = K.head[col]; ctx.font = `700 34px ${FONT_MONO}`; ctx.textAlign = 'right'; ctx.fillText(String(n), x + bw - 14, by + 62); ctx.textAlign = 'left';
  });
  if (!pb.specs.length) {
    const open = tasks.filter((t) => t.col !== 'done').sort((a, b) => ['doing', 'wait', 'todo'].indexOf(a.col) - ['doing', 'wait', 'todo'].indexOf(b.col));
    open.slice(0, 3).forEach((t, k) => {
      const ly = by + bh + 26 + k * 40;
      ctx.fillStyle = K.head[t.col]; ctx.beginPath(); ctx.arc(40, ly - 7, 7, 0, Math.PI * 2); ctx.fill();
      ctx.fillStyle = P.title; ctx.font = `700 20px ${FONT_BODY}`; fitText(ctx, `${t.list} #${t.id} ${t.subject}${t.perm ? '（許可待ち）' : ''}`, 58, ly, W - 90);
    });
    const note = SOURCE.mode === 'demo' ? '画面の spec はない（CLI ツール）' : proj.jsonui ? 'spec はまだ無い' : 'JsonUI のプロジェクトではない（spec なし）';
    ctx.fillStyle = P.sub; ctx.font = `600 18px ${FONT_BODY}`; ctx.fillText(note, 30, H - 22);
  }
  pb.tex.needsUpdate = true;
}

function drawTaskBoard(full, project = 'shop', board = null) {
  const tasks = full.tasks.filter((x) => PROJECT_OF[x.list] === project);
  const model = { tasks, pending: full.pending.filter((p) => projectOfRobot(p.who) === project) };
  const B = board || KB, cv = board ? board.canvas : kbCanvas, tx = board ? board.tex : kbTex;
  const P = KB_PAL[isDark() ? 'dark' : 'light'], ctx = cv.getContext('2d');
  ctx.fillStyle = P.cork; ctx.fillRect(0, 0, B.W, B.H);
  ctx.fillStyle = P.speck;
  for (let i = 0; i < 520; i++) ctx.fillRect((i * 97.31) % B.W, (i * 61.7 + (i % 7) * 13) % B.H, 3, 2);
  ctx.textAlign = 'left'; ctx.textBaseline = 'alphabetic';
  ctx.fillStyle = P.title; ctx.font = `40px ${FONT_DISPLAY}`; ctx.fillText('タスクボード', 26, 58);
  ctx.fillStyle = P.sub; ctx.font = `700 21px ${FONT_BODY}`;
  ctx.fillText(`${PROJECT[project].name} · ${model.tasks.length} 件 · ${new Set(model.tasks.map((x) => x.list)).size} セッションの一覧`, 30, 92);
  if (model.pending.length) {
    const label = `許可待ち ${model.pending.length}`;
    ctx.font = `700 24px ${FONT_BODY}`;
    const w = ctx.measureText(label).width + 36;
    rr(ctx, B.W - 24 - w, 30, w, 42, 21); ctx.fillStyle = P.warn; ctx.fill();
    ctx.fillStyle = P.warnInk; ctx.fillText(label, B.W - 24 - w + 18, 59);
  }
  const colW = (B.W - 24 * 2 - 12 * 3) / 4, top = 112, noteH = 76, gap = 8, maxN = Math.floor((B.H - top - 92) / (noteH + gap));
  KCOLS.forEach(([col, label], c) => {
    const x = 24 + c * (colW + 12), items = model.tasks.filter((t) => t.col === col);
    rr(ctx, x, top, colW, B.H - top - 18, 10); ctx.fillStyle = P.col; ctx.fill();
    ctx.save(); ctx.clip(); ctx.fillStyle = P.head[col]; ctx.fillRect(x, top, colW, 7); ctx.restore();
    ctx.fillStyle = P.title; ctx.font = `700 24px ${FONT_BODY}`; ctx.fillText(label, x + 12, top + 40);
    ctx.fillStyle = P.head[col]; ctx.font = `700 26px ${FONT_MONO}`; ctx.textAlign = 'right'; ctx.fillText(String(items.length), x + colW - 12, top + 41); ctx.textAlign = 'left';
    items.slice(0, maxN).forEach((task, j) => {
      const nx = x + 8, nw = colW - 16, ny = top + 58 + j * (noteH + gap);
      ctx.save();
      ctx.translate(nx + nw / 2, ny + noteH / 2); ctx.rotate((((task.id * 37 + c * 11) % 5) - 2) * 0.007); ctx.translate(-(nx + nw / 2), -(ny + noteH / 2));
      ctx.fillStyle = 'rgba(0, 0, 0, 0.16)'; ctx.fillRect(nx + 2, ny + 3, nw, noteH);
      ctx.fillStyle = P.note[col]; ctx.fillRect(nx, ny, nw, noteH);
      if (task.perm) { ctx.lineWidth = 6; ctx.strokeStyle = P.warn; ctx.strokeRect(nx - 2, ny - 2, nw + 4, noteH + 4); }
      ctx.fillStyle = P.pin; ctx.beginPath(); ctx.arc(nx + nw / 2, ny + 7, 5, 0, Math.PI * 2); ctx.fill();
      ctx.fillStyle = P.soft; ctx.font = `700 15px ${FONT_MONO}`; ctx.fillText(`${task.list} #${task.id}`, nx + 10, ny + 25);
      if (task.perm) {
        rr(ctx, nx + nw - 76, ny + 9, 66, 24, 12); ctx.fillStyle = P.warn; ctx.fill();
        ctx.fillStyle = P.warnInk; ctx.font = `700 14px ${FONT_BODY}`; ctx.textAlign = 'center'; ctx.fillText('許可待ち', nx + nw - 43, ny + 26); ctx.textAlign = 'left';
      } else if (task.owner) {
        const role = DEF[task.owner].role;
        rr(ctx, nx + nw - 50, ny + 11, 40, 20, 10); ctx.fillStyle = ROLES[role].color; ctx.fill();
        ctx.fillStyle = ROLE_INK[role] || '#ffffff'; ctx.font = `700 13px ${FONT_MONO}`; ctx.textAlign = 'center'; ctx.fillText(task.owner, nx + nw - 30, ny + 26); ctx.textAlign = 'left';
      }
      ctx.fillStyle = P.ink; ctx.font = `700 16px ${FONT_BODY}`;
      wrapText(ctx, task.subject, nx + 10, ny + 49, nw - 20, 20, 2);
      ctx.restore();
    });
    if (items.length > maxN) { ctx.fillStyle = P.title; ctx.font = `700 17px ${FONT_BODY}`; ctx.fillText(`ほか ${items.length - maxN} 件`, x + 12, B.H - 34); }
  });
  tx.needsUpdate = true;
}

function drawTestBoard(model, board = null, run = null) {
  const T = run || model.tests, TB = board || TB_DEMO, ctx = (board ? board.canvas : tbCanvas).getContext('2d');
  const nCases = Math.max(1, T.rows.length), maxRows = Math.floor((TB.H - 186) / 78);
  ctx.fillStyle = '#102640'; ctx.fillRect(0, 0, TB.W, TB.H);
  ctx.textAlign = 'left'; ctx.textBaseline = 'alphabetic';
  ctx.fillStyle = '#ffffff'; ctx.font = `40px ${FONT_DISPLAY}`; ctx.fillText('テスト実行', 36, 62);
  ctx.fillStyle = '#9fc3ff'; ctx.font = `600 21px ${FONT_MONO}`; ctx.fillText(`${T.file} · ${T.device}`, 36, 98);
  ctx.fillStyle = '#d6e4f7'; ctx.font = `700 23px ${FONT_BODY}`; ctx.fillText(T.statusText, 36, 134);
  const bx = 36, bw = TB.W - 72, by = 150;
  rr(ctx, bx, by, bw, 14, 7); ctx.fillStyle = '#23405f'; ctx.fill();
  const pw = (bw * T.passed) / nCases;
  if (pw > 0) { rr(ctx, bx, by, Math.max(14, pw), 14, 7); ctx.fillStyle = '#4fd48a'; ctx.fill(); }
  if (T.runningIdx >= 0) { ctx.fillStyle = T.retrying ? '#ffc14d' : '#7ab4ff'; ctx.fillRect(bx + pw, by, bw / nCases, 14); }
  // a long run: the window of rows around the one running
  const first = T.rows.length > maxRows ? Math.max(0, Math.min(T.rows.length - maxRows, (T.runningIdx >= 0 ? T.runningIdx : T.rows.length) - Math.floor(maxRows / 2))) : 0;
  T.rows.slice(first, first + maxRows).forEach((c, j) => {
    const i = first + j;
    const y = tbRowTop(j);
    if (c.status === 'running') { rr(ctx, 20, y, TB.W - 40, 72, 12); ctx.fillStyle = T.retrying ? '#4a3a12' : '#1f4f8a'; ctx.fill(); }
    const icon = { pending: '○', running: '▶', passed: '✓', flaky: '⚠', failed: '✗', skipped: '–' }[c.status];
    ctx.fillStyle = { pending: '#6f87a6', running: '#ffffff', passed: '#4fd48a', flaky: '#ffc14d', failed: '#ff7a85', skipped: '#8aa0bd' }[c.status];
    ctx.font = `700 28px ${FONT_MONO}`; ctx.fillText(icon, 36, y + 36);
    ctx.fillStyle = c.status === 'pending' ? '#8aa0bd' : '#ffffff'; ctx.font = `700 25px ${FONT_BODY}`; ctx.fillText(`${i + 1}. ${c.name}`, 80, y + 34);
    ctx.font = `500 18px ${FONT_MONO}`;
    if (c.status === 'running') { ctx.fillStyle = '#7ef9ff'; ctx.fillText(`${c.attempt > 1 ? '再実行 2 回目 · ' : ''}${c.step}`, 80, y + 62); }
    else if (c.branch) { ctx.fillStyle = '#8fa6c4'; ctx.fillText(`分岐: ${c.branch}${c.status === 'flaky' ? ' · 再実行で通過' : ''}`, 80, y + 62); }
  });
  if (!T.rows.length && T.command) { ctx.fillStyle = '#8fa6c4'; ctx.font = `500 20px ${FONT_MONO}`; wrapText(ctx, T.command, 36, 220, TB.W - 72, 28, 6); }
  (board ? board.tex : tbTex).needsUpdate = true;
}

function drawCartUI(r, t) {
  const c = r.phoneCanvas, ctx = c.getContext('2d'), W = c.width;
  const accent = ROLES[r.role].color;
  const T = latestModel.tests, idx = T.runningIdx, step = idx >= 0 ? T.rows[idx].step : '';
  ctx.clearRect(0, 0, c.width, c.height);
  ctx.fillStyle = '#ffffff'; ctx.strokeStyle = '#1d2330'; ctx.lineWidth = 5; ctx.lineJoin = 'round';
  ctx.beginPath(); ctx.moveTo(44, 360); ctx.lineTo(16, 396); ctx.lineTo(84, 362); ctx.closePath(); ctx.fill(); ctx.stroke();
  rr(ctx, 6, 6, W - 12, 360, 28); ctx.fill(); ctx.stroke();
  ctx.beginPath(); ctx.moveTo(48, 355); ctx.lineTo(25, 387); ctx.lineTo(79, 358); ctx.closePath(); ctx.fill();
  const sx = 24, sy = 24, sw = 192, sh = 320;
  ctx.save();
  rr(ctx, sx, sy, sw, sh, 18); ctx.clip();
  ctx.fillStyle = '#f1f4f9'; ctx.fillRect(sx, sy, sw, sh);
  ctx.fillStyle = accent; ctx.fillRect(sx, sy, sw, 58);
  ctx.textAlign = 'left'; ctx.textBaseline = 'alphabetic';
  ctx.fillStyle = '#ffffff'; ctx.font = `700 11px ${FONT_MONO}`; ctx.fillText('9:41', sx + 12, sy + 16);
  ctx.font = `700 18px ${FONT_BODY}`; ctx.fillText(idx === 6 && step.includes('screen') ? 'ログイン' : 'カート', sx + 14, sy + 46);
  const empty = idx === 2;
  const items = empty ? 0 : idx === 1 && step.includes('count') ? 2 : 3;
  if (empty) {
    ctx.fillStyle = '#7a879b'; ctx.font = `700 14px ${FONT_BODY}`; ctx.textAlign = 'center'; ctx.fillText('カートは空です', sx + sw / 2, sy + 130); ctx.textAlign = 'left';
  }
  for (let i = 0; i < items; i++) {
    const y = sy + 70 + i * 50;
    rr(ctx, sx + 10, y, sw - 20, 42, 8); ctx.fillStyle = '#ffffff'; ctx.fill();
    ctx.fillStyle = ['#ffd6a5', '#cde7ff', '#d8f5c9'][i]; rr(ctx, sx + 16, y + 6, 30, 30, 6); ctx.fill();
    ctx.fillStyle = '#394150'; ctx.fillRect(sx + 54, y + 10, 70 - i * 10, 7);
    ctx.fillStyle = '#7a879b'; ctx.fillRect(sx + 54, y + 24, 40, 6);
    ctx.fillStyle = '#394150'; ctx.font = `700 12px ${FONT_MONO}`; ctx.fillText(`×${i === 0 && idx === 1 && !step.includes('count') ? 0 : 1}`, sx + sw - 42, y + 27);
    if (idx === 5 && i === 1) { ctx.fillStyle = '#c62f3c'; ctx.font = `700 10px ${FONT_BODY}`; ctx.fillText('在庫切れ', sx + 54, y + 38); }
  }
  const cy = sy + 226;
  rr(ctx, sx + 10, cy, sw - 20, 26, 6); ctx.fillStyle = '#ffffff'; ctx.fill(); ctx.strokeStyle = '#cfd8e6'; ctx.lineWidth = 2; ctx.stroke();
  ctx.fillStyle = '#394150'; ctx.font = `500 11px ${FONT_MONO}`; ctx.fillText(idx === 3 ? 'WELCOME10' : idx === 4 ? 'OLD2025' : 'クーポン', sx + 18, cy + 17);
  if (idx === 4 && T.retrying) { ctx.fillStyle = '#c62f3c'; ctx.font = `700 10px ${FONT_BODY}`; ctx.fillText('期限切れのクーポンです', sx + 14, cy + 40); }
  const disabled = empty || idx === 5;
  const byBtn = sy + 274;
  rr(ctx, sx + 10, byBtn, sw - 20, 34, 10); ctx.fillStyle = disabled ? '#b9c3d1' : accent; ctx.fill();
  ctx.fillStyle = '#ffffff'; ctx.font = `700 14px ${FONT_BODY}`; ctx.textAlign = 'center'; ctx.fillText('購入する', sx + sw / 2, byBtn + 23);
  if (idx >= 0) {
    let tx = sx + sw / 2, ty = byBtn + 17;
    if (step.includes('coupon')) { tx = sx + 60; ty = cy + 13; } else if (step.includes('qty')) { tx = sx + sw - 34; ty = sy + 92; } else if (step.includes('cart_list') || step.includes('count')) { tx = sx + 90; ty = sy + 120; }
    const ph = (t * 0.9) % 1;
    ctx.beginPath(); ctx.arc(tx, ty, 6 + ph * 22, 0, Math.PI * 2); ctx.strokeStyle = `rgba(214, 40, 57, ${(0.9 * (1 - ph)).toFixed(2)})`; ctx.lineWidth = 4; ctx.stroke();
  }
  ctx.restore();
  ctx.fillStyle = '#4b5c76'; ctx.font = `700 11px ${FONT_MONO}`; ctx.textAlign = 'center'; ctx.textBaseline = 'alphabetic';
  ctx.fillText(idx >= 0 ? `case ${idx + 1}/8 · iPhone 16` : 'iPhone 16 シミュレータ', W / 2, 359);
  r.phoneTex.needsUpdate = true; r.phoneScreenTex.needsUpdate = true;
}

/* Board textures are uploaded again only when what they show has changed (or the theme flipped). */
const boardSig = { spec: '', test: '', task: '' };
function redrawBoards(model, now, force) {
  if (SOURCE.mode === 'live') { liveRedrawBoards(model, now, force); return; }
  const theme = isDark() ? 'd' : 'l';
  const blink = model.specs.some((s) => s.writingIdx >= 0 && s.by) ? Math.floor(now * 2.5) % 2 : 0;
  const spec = theme + blink + model.specs.map((s) => [s.bucket, s.status.text, s.by, s.written.map((w) => Math.round(w * 50)).join(), s.implN.join(), activeSec(s)].join('|')).join(';');
  const test = model.tests.statusText + model.tests.rows.map((r) => r.status + (r.step || '')).join();
  const task = theme + model.pending.map((p) => p.id).join() + model.tasks.map((x) => x.key + x.col + (x.perm ? '!' : '')).join();
  if (force || spec !== boardSig.spec) { drawSpecBoard(model, now); boardSig.spec = spec; }
  if (force || test !== boardSig.test) { drawTestBoard(model); boardSig.test = test; }
  if (force || task !== boardSig.task) { drawTaskBoard(model); boardSig.task = task; }
  for (const pb of PBOARDS) {
    const sig = theme + blink + pb.specs.map((i) => { const s = model.specs[i]; return [s.status.text, s.by, s.written.map((w) => Math.round(w * 50)).join(), s.implN.join(), activeSec(s)].join('|'); }).join(';')
      + model.tasks.filter((x) => PROJECT_OF[x.list] === pb.project).map((x) => x.key + x.col + (x.perm ? '!' : '')).join() + model.pending.map((p) => p.id).join();
    if (force || sig !== pb.sig) { drawProjectBoard(pb, model, now); pb.sig = sig; }
  }
}

function makeLink(color) {
  const N = 48, pos = new Float32Array(N * 3);
  const geo = new THREE.BufferGeometry(); geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
  const line = new THREE.Line(geo, new THREE.LineBasicMaterial({ color, transparent: true, opacity: 0.9, depthTest: false }));
  line.renderOrder = 5; line.frustumCulled = false; scene.add(line);
  const dotMat = new THREE.MeshBasicMaterial({ color, depthTest: false });
  const dots = [0, 1, 2].map(() => { const d = new THREE.Mesh(S.geo.lamp, dotMat); d.scale.setScalar(1.8); d.renderOrder = 6; scene.add(d); return d; });
  const curve = new THREE.QuadraticBezierCurve3(new THREE.Vector3(), new THREE.Vector3(), new THREE.Vector3());
  const tmp = new THREE.Vector3();
  return {
    set(a, b, on, time) {
      line.visible = on; dots.forEach((d) => { d.visible = on; });
      if (!on) return;
      curve.v0.copy(a); curve.v2.copy(b); curve.v1.copy(a).add(b).multiplyScalar(0.5); curve.v1.y += 1.1;
      for (let i = 0; i < N; i++) { curve.getPoint(i / (N - 1), tmp); pos[i * 3] = tmp.x; pos[i * 3 + 1] = tmp.y; pos[i * 3 + 2] = tmp.z; }
      geo.attributes.position.needsUpdate = true;
      dots.forEach((d, i) => curve.getPoint((time * 0.45 + i / 3) % 1, d.position));
    },
  };
}
const linkFor = (id) => links[id] || (links[id] = makeLink(ROLES[DEF[id].role].color));

function addTag(cls, html) { const el = document.createElement('div'); el.className = `tag ${cls}`; el.innerHTML = html; tagsEl.append(el); return el; }

function addFrame(cx, cy, z, w, h, mat) {
  for (const [bw, bh, x, y] of [[w + 0.16, 0.08, 0, h / 2 + 0.04], [w + 0.16, 0.08, 0, -h / 2 - 0.04], [0.08, h, -w / 2 - 0.04, 0], [0.08, h, w / 2 + 0.04, 0]]) {
    const bar = new THREE.Mesh(new THREE.BoxGeometry(bw, bh, 0.05), mat); bar.position.set(cx + x, cy + y, z + 0.01); scene.add(bar);
  }
}

/* The demo office: three fixed rooms with their boards, the test stand, the document tray and the robots of
   the script (the prototype as it was). The live view builds its rooms from the slices instead (liveSync). */
function buildDemoOffice() {
  const wallMat = toon(readToken('--wall', '#f7f9fc'));
  roomMats.push([wallMat, '--wall', '#f7f9fc']);
  for (const room of ROOMS) {
    const w = room.x1 - room.x0, d = room.z1 - room.z0, cx = (room.x0 + room.x1) / 2, cz = (room.z0 + room.z1) / 2;
    const floorMat = toon(readToken(room.floor, '#e9eef6'));
    roomMats.push([floorMat, room.floor, '#e9eef6']);
    const floor = new THREE.Mesh(new RoundedBoxGeometry(w, 0.16, d, 2, 0.05), floorMat); floor.position.set(cx, -0.08, cz); scene.add(floor);
    const back = new THREE.Mesh(new THREE.BoxGeometry(w + 0.16, room.back, 0.16), wallMat); back.position.set(cx - 0.08, room.back / 2, room.z0 - 0.08); scene.add(back);
    const left = new THREE.Mesh(new THREE.BoxGeometry(0.16, room.left, d), wallMat); left.position.set(room.x0 - 0.08, room.left / 2, cz); scene.add(left);
    const tag = document.createElement('button');
    tag.type = 'button'; tag.className = 'tag room'; tag.dataset.setProject = room.id; tag.title = `${room.name} だけを表示する`; tag.textContent = room.name;
    tagsEl.append(tag);
    roomTags.push({ el: tag, id: room.id, p: new THREE.Vector3(room.x0 + 0.2, 0.02, room.z1 - 0.1) });
  }

  const frameMat = toon('#7a5a3c');
  sbCanvas = makeCanvas(SB.W, SB.H); sbTex = texFrom(sbCanvas);
  boardMesh = new THREE.Mesh(new THREE.PlaneGeometry(SB.w, SB.h), new THREE.MeshBasicMaterial({ map: sbTex, toneMapped: false }));
  boardMesh.position.set(SB.cx, SB.cy, SB.z); scene.add(boardMesh);
  addFrame(SB.cx, SB.cy, SB.z, SB.w, SB.h, frameMat);
  kbCanvas = makeCanvas(KB.W, KB.H); kbTex = texFrom(kbCanvas);
  kbMesh = new THREE.Mesh(new THREE.PlaneGeometry(KB.w, KB.h), new THREE.MeshBasicMaterial({ map: kbTex, toneMapped: false }));
  kbMesh.position.set(KB.cx, KB.cy, KB.z); scene.add(kbMesh);
  addFrame(KB.cx, KB.cy, KB.z, KB.w, KB.h, frameMat);
  for (const pb of PBOARDS) {
    pb.canvas = makeCanvas(pb.W, pb.H); pb.tex = texFrom(pb.canvas);
    pb.mesh = new THREE.Mesh(new THREE.PlaneGeometry(pb.w, pb.h), new THREE.MeshBasicMaterial({ map: pb.tex, toneMapped: false }));
    if (pb.wall) {
      pb.mesh.position.set(pb.wall.cx, pb.wall.cy, pb.wall.z); scene.add(pb.mesh);
      addFrame(pb.wall.cx, pb.wall.cy, pb.wall.z, pb.w, pb.h, frameMat);
    } else {
      const e = pb.easel, g = new THREE.Group();
      g.position.set(e.x, 0, e.z); g.rotation.y = e.ry; scene.add(g);
      pb.mesh.position.set(0, e.bottom + pb.h / 2, 0.06); g.add(pb.mesh);
      const back = new THREE.Mesh(new THREE.BoxGeometry(pb.w + 0.12, pb.h + 0.12, 0.06), frameMat); back.position.set(0, e.bottom + pb.h / 2, 0.02); g.add(back);
      for (const sx of [-1, 1]) {
        const leg = new THREE.Mesh(new THREE.CylinderGeometry(0.035, 0.035, e.bottom + pb.h + 0.2, 8), frameMat);
        leg.position.set(sx * (pb.w / 2 - 0.15), (e.bottom + pb.h + 0.2) / 2, -0.06); leg.rotation.x = 0.06; g.add(leg);
      }
      const ledge = new THREE.Mesh(new THREE.BoxGeometry(pb.w + 0.2, 0.05, 0.16), frameMat); ledge.position.set(0, e.bottom - 0.04, 0.1); g.add(ledge);
    }
  }
  tbCanvas = makeCanvas(TB.W, TB.H); tbTex = texFrom(tbCanvas);
  const tboard = new THREE.Mesh(new THREE.PlaneGeometry(TB.w, TB.h), new THREE.MeshBasicMaterial({ map: tbTex, toneMapped: false }));
  tboard.rotation.y = Math.PI / 2; tboard.position.set(TB.x, TB.cy, TB.cz); scene.add(tboard);

  const stand = new THREE.Group(); stand.position.set(-8.7, 0, -0.5); stand.rotation.y = 0.85; scene.add(stand);
  const legMat = toon('#394150');
  for (let i = 0; i < 3; i++) {
    const leg = new THREE.Mesh(new THREE.CylinderGeometry(0.025, 0.025, 1.0, 8), legMat);
    const a = (i / 3) * Math.PI * 2;
    leg.position.set(Math.sin(a) * 0.18, 0.45, Math.cos(a) * 0.18); leg.rotation.set(Math.cos(a) * 0.35, 0, -Math.sin(a) * 0.35); stand.add(leg);
  }
  const pole = new THREE.Mesh(new THREE.CylinderGeometry(0.03, 0.03, 0.6, 8), legMat); pole.position.y = 1.15; stand.add(pole);
  const big = new THREE.Mesh(new RoundedBoxGeometry(0.94, 1.58, 0.08, 3, 0.08), toon(COL.phone)); big.position.y = 2.15; stand.add(big);
  const offCanvas = makeCanvas(192, 320), octx = offCanvas.getContext('2d');
  octx.fillStyle = '#0d1828'; octx.fillRect(0, 0, 192, 320);
  octx.fillStyle = '#6f87a6'; octx.font = `700 16px ${FONT_BODY}`; octx.textAlign = 'center'; octx.fillText('シミュレータ', 96, 150); octx.fillText('待機中', 96, 176);
  standOffTex = texFrom(offCanvas);
  standMat = new THREE.MeshBasicMaterial({ map: standOffTex, toneMapped: false });
  const screen = new THREE.Mesh(new THREE.PlaneGeometry(0.82, 1.37), standMat); screen.position.set(0, 2.15, 0.042); stand.add(screen);

  trayGroup = new THREE.Group(); trayGroup.position.set(1.4, 0, 2.75); scene.add(trayGroup);
  const tabMat = toon(COL.wood);
  const top = new THREE.Mesh(new RoundedBoxGeometry(2.0, 0.08, 1.0, 2, 0.02), tabMat); top.position.y = 0.74; trayGroup.add(top);
  for (const [x, z] of [[-0.9, -0.42], [0.9, -0.42], [-0.9, 0.42], [0.9, 0.42]]) { const leg = new THREE.Mesh(new THREE.CylinderGeometry(0.03, 0.03, 0.72, 8), toon(COL.woodDark)); leg.position.set(x, 0.36, z); trayGroup.add(leg); }
  const box = new THREE.Mesh(new RoundedBoxGeometry(0.62, 0.07, 0.44, 2, 0.02), toon('#c9d0db')); box.position.set(0.5, 0.815, 0); trayGroup.add(box);
  for (let i = 0; i < 12; i++) {
    const p = new THREE.Mesh(S.geo.sheet, S.mat.sheets[i % 4]); p.position.set(-0.45, 0.8 + i * 0.034, 0); p.rotation.y = ((i * 37) % 9 - 4) * 0.02; trayGroup.add(p); trayPending.push(p);
    const q = new THREE.Mesh(S.geo.sheet, S.mat.sheets[(i + 1) % 4]); q.position.set(0.5, 0.86 + i * 0.022, 0); q.rotation.y = ((i * 53) % 7 - 3) * 0.02; q.scale.set(0.95, 0.7, 0.95); trayGroup.add(q); trayDone.push(q);
  }
  trayTag = { el: addTag('tray', ''), p: new THREE.Vector3(1.4, 1.45, 2.75) };

  for (const [i, d] of ROBOT_DEFS.entries()) {
    const robot = createRobot({ label: d.id, role: d.role, state: 'idle', seed: i * 1.7, furnished: !!d.furnished });
    if (d.pos) { robot.root.position.set(d.pos[0], 0, d.pos[1]); robot.root.rotation.y = d.ry; }
    if (d.id === 'a2') { robot.drawPhone = drawCartUI; ensureProps(robot, 'phone'); }
    robot.root.userData.robotId = d.id;
    scene.add(robot.root);
    const tag = addTag('', `${pill(d.id, d.role)}<span></span>`);
    robots.push({ def: d, robot, tag, text: tag.lastElementChild, act: '' });
  }
}

function build3D() {
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.setClearColor(0x000000, 0);
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  maxAniso = renderer.capabilities.getMaxAnisotropy();
  initShared();

  scene = new THREE.Scene();
  camera = new THREE.PerspectiveCamera(32, 1, 0.5, 200);
  camera.position.set(6.8, 15.9, 22.1);
  controls = new OrbitControls(camera, canvas);
  controls.target.set(0.3, 0.4, -0.4);
  controls.enableDamping = true; controls.dampingFactor = 0.08;
  controls.minDistance = 8; controls.maxDistance = 44;
  controls.minPolarAngle = 0.3; controls.maxPolarAngle = 1.25;
  controls.screenSpacePanning = false;
  controls.update();
  scene.add(new THREE.HemisphereLight(0xffffff, 0x9fb0c8, 1.6));
  const sun = new THREE.DirectionalLight(0xffffff, 2.0); sun.position.set(6, 14, 9); scene.add(sun);

  // Live: the rooms come with the first snapshot; the first frame after it builds them (liveSync).
  if (SOURCE.mode === 'demo') buildDemoOffice(); else LIVE3D.rev = -1;

  selRing = new THREE.Mesh(new THREE.RingGeometry(0.78, 0.96, 48), new THREE.MeshBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.9, depthWrite: false }));
  selRing.rotation.x = -Math.PI / 2; selRing.visible = false; scene.add(selRing);

  // A click (not a drag) zooms in: a robot opens its card, a spec tile opens that spec, the rest of the spec
  // board opens the overview, and the cork board or the document tray opens the task board.
  const ray = new THREE.Raycaster(), ndc = new THREE.Vector2();
  let downAt = null;
  const hitAt = (ev) => {
    const r = canvas.getBoundingClientRect();
    ndc.set(((ev.clientX - r.left) / r.width) * 2 - 1, -((ev.clientY - r.top) / r.height) * 2 + 1);
    ray.setFromCamera(ndc, camera);
    if (SOURCE.mode === 'live') return liveHit(ray);
    const hit = ray.intersectObjects([boardMesh, kbMesh, trayGroup, ...PBOARDS.map((pb) => pb.mesh), ...robots.map((R) => R.robot.root)], true)[0];
    if (!hit) return null;
    let o = hit.object;
    while (o && o.userData.robotId === undefined && o.parent) o = o.parent;
    if (o && o.userData.robotId !== undefined) return { kind: 'robot', id: o.userData.robotId };
    const pb = PBOARDS.find((b) => b.mesh === hit.object);
    if (pb) {
      const px = hit.uv.x * pb.W, py = (1 - hit.uv.y) * pb.H;
      if (py >= pb.splitY) return { kind: 'tasks', project: pb.project };
      const t = pb.tiles.find((q) => px >= q.x && px <= q.x + q.w && py >= q.y && py <= q.y + q.h);
      return t ? { kind: 'spec', i: t.i } : { kind: 'board', project: pb.project };
    }
    if (hit.object !== boardMesh) return { kind: 'tasks', project: 'shop' };
    const px = hit.uv.x * SB.W, py = (1 - hit.uv.y) * SB.H;
    for (let pos = 0; pos < SHOP_IDX.length; pos++) { const p = sbTile(pos); if (px >= p.x && px <= p.x + SB.tw && py >= p.y && py <= p.y + SB.th) return { kind: 'spec', i: SHOP_IDX[pos] }; }
    return { kind: 'board', project: 'shop' };
  };
  canvas.addEventListener('pointerdown', (ev) => { downAt = [ev.clientX, ev.clientY]; });
  canvas.addEventListener('pointerup', (ev) => {
    if (!downAt || (zoom.zoomed && !rbState.id)) return;
    const moved = Math.hypot(ev.clientX - downAt[0], ev.clientY - downAt[1]);
    downAt = null;
    if (moved > 6) return;
    const h = hitAt(ev);
    if (!h) return;
    // A board belongs to one project room, so opening it narrows the view to that project (unless it already shows everything).
    const fit = (proj) => { if (proj && UI.project !== 'all' && UI.project !== proj) setProject(proj, { camera: false }); };
    if (h.kind === 'robot') openRobot(h.id, canvas);
    else if (h.kind === 'tasks') { fit(h.project); openTaskBoard(canvas, undefined, h.project); }
    else if (h.kind === 'spec') { fit(SPECS[h.i].project); openWhiteboard(h.i, canvas); }
    else { fit(h.project); openWhiteboard(-1, canvas, h.project); }
  });
  canvas.addEventListener('pointermove', (ev) => {
    if (ev.buttons || (zoom.zoomed && !rbState.id)) return;
    canvas.style.cursor = hitAt(ev) ? 'pointer' : '';
  });

  const applyTheme = () => { for (const [mat, token, fallback] of roomMats) mat.color.set(readToken(token, fallback)); };
  window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', applyTheme);
  new MutationObserver(applyTheme).observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
}
/* =====================================================================
   The live office (plan 07 §4): one room per project from the slices, built and removed as SOURCE.layoutRev
   moves. Each room: floor, back and left walls, its project board on the back wall and its task cork board on
   the left wall. Robots get seats from 30-source-live.js and walk there: in through the room's door, out
   through it when they leave, and door to door when their session moves to another project.
   ===================================================================== */
const LIVE3D = { rev: -1, rooms: {}, sharedGeo: null, sharedMat: null, roomsSig: '', userMoved: false };
const WALK_SPEED = 1.7;
function liveShared() {
  if (LIVE3D.sharedGeo) return;
  const flat = (o) => Object.values(o).flatMap((v) => (Array.isArray(v) ? v : [v]));
  LIVE3D.sharedGeo = new Set(flat(S.geo));
  LIVE3D.sharedMat = new Set(flat(S.mat));
}
function disposeTree(root) {
  liveShared();
  root.traverse((o) => {
    if (o.geometry && !LIVE3D.sharedGeo.has(o.geometry)) o.geometry.dispose();
    const mats = Array.isArray(o.material) ? o.material : o.material ? [o.material] : [];
    for (const m of mats) {
      if (LIVE3D.sharedMat.has(m)) continue;
      if (m.map && !Object.values(S.tex || {}).includes(m.map)) m.map.dispose();
      m.dispose();
    }
  });
}
function liveBuildRoom(room) {
  const g = new THREE.Group();
  const w = room.x1 - room.x0, d = room.z1 - room.z0, cx = (room.x0 + room.x1) / 2, cz = (room.z0 + room.z1) / 2;
  const wallMat = toon(readToken('--wall', '#f7f9fc')), floorMat = toon(readToken(room.floor, '#e9eef6'));
  const mats = [[wallMat, '--wall', '#f7f9fc'], [floorMat, room.floor, '#e9eef6']];
  roomMats.push(...mats);
  const floor = new THREE.Mesh(new RoundedBoxGeometry(w, 0.16, d, 2, 0.05), floorMat); floor.position.set(cx, -0.08, cz); g.add(floor);
  const back = new THREE.Mesh(new THREE.BoxGeometry(w + 0.16, room.back, 0.16), wallMat); back.position.set(cx - 0.08, room.back / 2, room.z0 - 0.08); g.add(back);
  const left = new THREE.Mesh(new THREE.BoxGeometry(0.16, room.left, d), wallMat); left.position.set(room.x0 - 0.08, room.left / 2, cz); g.add(left);
  // the doorway: a mat at the front right, where robots come in and go out
  const mat = new THREE.Mesh(new THREE.BoxGeometry(1.0, 0.02, 0.6), toon('#c9d0db')); mat.position.set(room.x1 - 0.7, 0.01, room.z1 - 0.3); g.add(mat);
  const frameMat = toon('#7a5a3c');
  // project board on the back wall; a room with many specs gets the big spec board instead (plan 09 §7)
  const pbW = room.big ? w - 1.2 : Math.min(w - 2.2, 4.2);
  const pb = room.big ? { project: room.id, big: true, W: 2048, H: 1024, w: pbW, h: Math.min(room.back - 0.9, pbW * 1024 / 2048), specs: [], tiles: [], splitY: 1e9, sig: '' }
    : { project: room.id, W: 1024, H: 560, w: pbW, h: pbW * 560 / 1024, specs: [], tiles: [], splitY: 0, sig: '' };
  if (room.big) pb.W = Math.round(pb.H * pb.w / pb.h);
  pb.canvas = makeCanvas(pb.W, pb.H); pb.tex = texFrom(pb.canvas);
  pb.mesh = new THREE.Mesh(new THREE.PlaneGeometry(pb.w, pb.h), new THREE.MeshBasicMaterial({ map: pb.tex, toneMapped: false }));
  const pbX = room.big ? cx : cx + 0.4, pbY = room.big ? Math.max(2.35, pb.h / 2 + 0.75) : 2.35;
  pb.mesh.position.set(pbX, pbY, room.z0 + 0.02); g.add(pb.mesh);
  for (const [bw, bh, x, y] of [[pb.w + 0.16, 0.08, 0, pb.h / 2 + 0.04], [pb.w + 0.16, 0.08, 0, -pb.h / 2 - 0.04], [0.08, pb.h, -pb.w / 2 - 0.04, 0], [0.08, pb.h, pb.w / 2 + 0.04, 0]]) {
    const bar = new THREE.Mesh(new THREE.BoxGeometry(bw, bh, 0.05), frameMat); bar.position.set(pbX + x, pbY + y, room.z0 + 0.03); g.add(bar);
  }
  // the test board, on an easel at the front left, only while the project has test runs
  let tb = null;
  if (room.tests) {
    tb = { project: room.id, W: 1024, H: 820, w: 1.7, h: 1.7 * 820 / 1024, sig: '' };
    tb.canvas = makeCanvas(tb.W, tb.H); tb.tex = texFrom(tb.canvas);
    const eg = new THREE.Group(); eg.position.set(room.x0 + 1.15, 0, room.z1 - 0.9); eg.rotation.y = 0.55; g.add(eg);
    tb.mesh = new THREE.Mesh(new THREE.PlaneGeometry(tb.w, tb.h), new THREE.MeshBasicMaterial({ map: tb.tex, toneMapped: false }));
    tb.mesh.position.set(0, 0.95 + tb.h / 2, 0.06); eg.add(tb.mesh);
    const back = new THREE.Mesh(new THREE.BoxGeometry(tb.w + 0.12, tb.h + 0.12, 0.06), frameMat); back.position.set(0, 0.95 + tb.h / 2, 0.02); eg.add(back);
    for (const sx of [-1, 1]) {
      const leg = new THREE.Mesh(new THREE.CylinderGeometry(0.035, 0.035, 1.15 + tb.h, 8), frameMat);
      leg.position.set(sx * (tb.w / 2 - 0.15), (1.15 + tb.h) / 2, -0.06); leg.rotation.x = 0.06; eg.add(leg);
    }
  }
  // task cork board on the left wall
  const kw = Math.min(d - 1.4, 2.6), kb = { project: room.id, W: 1024, H: 842, w: kw, h: kw * 842 / 1024, sig: '' };
  kb.canvas = makeCanvas(kb.W, kb.H); kb.tex = texFrom(kb.canvas);
  kb.mesh = new THREE.Mesh(new THREE.PlaneGeometry(kb.w, kb.h), new THREE.MeshBasicMaterial({ map: kb.tex, toneMapped: false }));
  kb.mesh.rotation.y = Math.PI / 2; kb.mesh.position.set(room.x0 + 0.02, 2.1, cz); g.add(kb.mesh);
  scene.add(g);
  const tag = document.createElement('button');
  tag.type = 'button'; tag.className = 'tag room'; tag.dataset.setProject = room.id; tag.title = `${room.name} だけを表示する`; tag.textContent = room.name;
  tagsEl.append(tag);
  const rt = { el: tag, id: room.id, p: new THREE.Vector3(room.x0 + 0.2, 0.02, room.z1 - 0.1) };
  roomTags.push(rt);
  return { geo: room.geo, group: g, pb, kb, tb, rt, mats };
}
function liveDropRoom(id) {
  const R = LIVE3D.rooms[id];
  if (!R) return;
  scene.remove(R.group); disposeTree(R.group);
  R.rt.el.remove();
  roomTags.splice(roomTags.indexOf(R.rt), 1);
  for (const m of R.mats) roomMats.splice(roomMats.indexOf(m), 1);
  delete LIVE3D.rooms[id];
}
function liveAddRobot(d, i) {
  const robot = createRobot({ label: d.id, role: d.role, state: 'idle', seed: i * 1.7, furnished: true });
  robot.drawPhone = drawLivePhone;
  const start = d.enter && d.door ? d.door.outside : d.pos || [0, 0];
  robot.root.position.set(start[0], 0, start[1]); robot.root.rotation.y = d.ry || 0;
  robot.root.userData.robotId = d.id;
  scene.add(robot.root);
  const tag = addTag('', `${pill(d.id, d.role)}<span></span>`);
  const R = { def: d, robot, tag, text: tag.lastElementChild, act: '', path: [], room: d.room, seatKey: '', exitAt: 0 };
  if (d.enter && d.door) R.path = [d.door.inside];
  d.enter = false;
  robots.push(R);
  return R;
}
function liveDropRobot(R) {
  scene.remove(R.robot.root); disposeTree(R.robot.root);
  const k = fontRedraws.indexOf(R.robot.fontRedraw); if (k >= 0) fontRedraws.splice(k, 1);
  R.tag.remove();
  if (links[R.def.id]) links[R.def.id].set(null, null, false, 0);
  robots.splice(robots.indexOf(R), 1);
}
/* Rooms and robots follow the source; seats are targets the robots walk to. */
function liveSync() {
  LIVE3D.rev = SOURCE.layoutRev;
  const shown = ROOMS.filter((r) => r.shown);
  for (const id of Object.keys(LIVE3D.rooms)) {
    const r = PROJECT[id];
    if (!r || !r.shown || r.geo !== LIVE3D.rooms[id].geo) liveDropRoom(id);
  }
  for (const r of shown) if (!LIVE3D.rooms[r.id]) LIVE3D.rooms[r.id] = liveBuildRoom(r);
  const want = new Set(ROBOT_DEFS.filter((d) => d.pos || LIVE.leaving[d.id]).map((d) => d.id));
  for (const R of [...robots]) if (!want.has(R.def.id)) liveDropRobot(R);
  const have = new Set(robots.map((R) => R.def.id));
  ROBOT_DEFS.forEach((d, i) => { if (want.has(d.id) && !have.has(d.id)) liveAddRobot(d, i); });
  for (const R of robots) livePlan(R);
  const sig = shown.map((r) => r.geo).join(';');
  if (sig !== LIVE3D.roomsSig) {
    LIVE3D.roomsSig = sig;
    if (!zoom.zoomed && (UI.project === 'all' || !PROJECT[UI.project] || !PROJECT[UI.project].shown)) focusProject('all', LIVE3D.rev <= 1);
    else if (!zoom.zoomed) focusProject(UI.project, false);
  }
  redrawBoards(latestModel, performance.now() / 1000, true);
  const empty = $('live-empty');
  if (empty) empty.hidden = !!SESSIONS.length || !SOURCE.connected;
}
/* Where a robot walks next: its seat (through the doors when it changed rooms), or out of the door. */
function livePlan(R) {
  const d = R.def, leaving = LIVE.leaving[d.id];
  if (leaving) return;   // liveWalk walks it out
  if (!d.pos) return;
  const key = `${d.room}:${d.pos.join()}`;
  if (key === R.seatKey) return;
  const fromRoom = PROJECT[R.room];
  if (R.seatKey && R.room !== d.room && fromRoom && fromRoom.shown && d.door) {
    const out = doorOf(fromRoom);
    R.path = [out.inside, out.outside, d.door.outside, d.door.inside, d.pos];
  } else if (R.seatKey) R.path = [d.pos];   // another seat in the same room
  else R.path.push(d.pos);                    // first seat: after the doorway when it just came in
  R.room = d.room; R.seatKey = key;
}
function liveWalk(R, dt, nowMs) {
  const root = R.robot.root, d = R.def;
  // Leaving is a state, not a layout change: start the "done, then out of the door" here.
  if (LIVE.leaving[d.id]) { if (!R.exitAt && !R.out) R.exitAt = nowMs + 2500; }
  else if (R.exitAt && !R.out) R.exitAt = 0;   // it came back before walking out
  if (R.exitAt && nowMs >= R.exitAt && !R.path.length && !R.out) {
    const room = PROJECT[d.room];
    const door = room && room.shown ? doorOf(room) : null;
    R.path = door ? [door.inside, door.outside] : [];
    R.out = true;
  }
  if (R.out && !R.path.length) { SOURCE.robotGone(d.id); return 'gone'; }
  const next = R.path[0];
  if (!next) {
    if (R.robot.desk) R.robot.desk.visible = !d.standing;
    if (Math.abs(root.rotation.y - (d.ry || 0)) > 1e-3) root.rotation.y += ((d.ry || 0) - root.rotation.y) * Math.min(1, dt * 6);
    return 'still';
  }
  const dx = next[0] - root.position.x, dz = next[1] - root.position.z, dist = Math.hypot(dx, dz);
  const step = WALK_SPEED * (SOURCE.replaySpeed > 1 ? Math.min(4, SOURCE.replaySpeed) : 1) * dt;
  if (R.robot.desk) R.robot.desk.visible = false;
  if (dist <= step || dist < 1e-3) { root.position.x = next[0]; root.position.z = next[1]; R.path.shift(); }
  else { root.position.x += (dx / dist) * step; root.position.z += (dz / dist) * step; root.rotation.y = Math.atan2(dx, dz); }
  return 'walking';
}
function liveUpdateRobots(nowSec, dt) {
  if (SOURCE.layoutRev !== LIVE3D.rev) liveSync();
  liveLinks(latestModel, nowSec);
  const nowMs = performance.now();
  // Walking uses the real time between frames (up to 1 s), not the animation's capped step: a slow frame rate
  // must not slow the walk down.
  const walkDt = LIVE3D.lastWalk ? Math.min(1, (nowMs - LIVE3D.lastWalk) / 1000) : 0;
  LIVE3D.lastWalk = nowMs;
  for (const R of [...robots]) {
    const st = robotState[R.def.id] || { state: 'idle', act: '' };
    const how = liveWalk(R, walkDt, nowMs);
    if (how === 'gone') continue;
    const vis = how === 'walking' ? 'carry' : st.state;
    if (vis !== R.robot.state) setRobotState(R.robot, vis);
    if (st.act !== R.act) { R.act = st.act; R.text.textContent = st.act; }
    updateRobot(R.robot, nowSec, dt);
  }
}
/* A board press in the live office: the project board opens that project's spec board (overview), its lower
   part and the cork board the task board, a robot its card. */
function liveHit(ray) {
  const targets = [...Object.values(LIVE3D.rooms).flatMap((R) => [R.pb.mesh, R.kb.mesh, ...(R.tb ? [R.tb.mesh] : [])]), ...robots.map((R) => R.robot.root)];
  const hit = ray.intersectObjects(targets, true)[0];
  if (!hit) return null;
  let o = hit.object;
  while (o && o.userData.robotId === undefined && o.parent) o = o.parent;
  if (o && o.userData.robotId !== undefined) return { kind: 'robot', id: o.userData.robotId };
  for (const [id, R] of Object.entries(LIVE3D.rooms)) {
    if (hit.object === R.kb.mesh) return { kind: 'tasks', project: id };
    if (R.tb && hit.object === R.tb.mesh) return { kind: 'board', project: id };
    if (hit.object === R.pb.mesh) {
      const px = hit.uv.x * R.pb.W, py = (1 - hit.uv.y) * R.pb.H;
      if (py >= R.pb.splitY) return { kind: 'tasks', project: id };
      const t = R.pb.tiles.find((q) => px >= q.x && px <= q.x + q.w && py >= q.y && py <= q.y + q.h);
      return t ? { kind: 'spec', i: t.i } : { kind: 'board', project: id };
    }
  }
  return null;
}
function liveRedrawBoards(model, now, force) {
  if (SOURCE.layoutRev !== LIVE3D.rev) { liveSync(); return; }   // rooms first (liveSync redraws them)
  const theme = isDark() ? 'd' : 'l';
  for (const [id, R] of Object.entries(LIVE3D.rooms)) {
    if (!PROJECT[id]) continue;
    // the room's label: its name, and its mock server when one runs (P7 §A3)
    const mk = PROJECT[id].mock, label = `${PROJECT[id].name}${mk && mk.running ? ` · モック :${mk.port}` : mk && mk.other ? ` · :${mk.port} は別のモック` : ''}`;
    if (R.rt.el.textContent !== label) { R.rt.el.textContent = label; R.rt.el.classList.toggle('mock-on', !!(mk && mk.running)); }
    const tasks = model.tasks.filter((x) => PROJECT_OF[x.list] === id);
    const pend = model.pending.filter((p) => projectOfRobot(p.who) === id).map((p) => p.id).join();
    const robotsIn = ROBOT_DEFS.filter((d) => d.room === id).length;
    R.pb.specs = model.specs.map((s, i) => [s, i]).filter(([s]) => s.project === id).map(([, i]) => i);
    const blink = R.pb.specs.some((i) => model.specs[i].writingIdx >= 0 && model.specs[i].by) ? Math.floor(now * 2.5) % 2 : 0;
    const specSig = R.pb.specs.map((i) => { const x = model.specs[i]; return [x.bucket, x.status.text, x.by, x.written.map((v) => Math.round(v * 50)).join(), x.implN.join(), activeSec(x)].join('|'); }).join(';');
    const sig = theme + blink + robotsIn + SESSIONS.filter((s) => s.project === id).length + pend + tasks.map((x) => x.key + x.col).join() + specSig;
    if (force || sig !== R.pb.sig) { if (R.pb.big) drawBigSpecBoard(R.pb, model, now); else drawProjectBoard(R.pb, model, now); R.pb.sig = sig; }
    const taskSig = theme + pend + tasks.map((x) => x.key + x.col + (x.perm ? '!' : '')).join();
    if (force || taskSig !== R.kb.sig) { drawTaskBoard(model, id, R.kb); R.kb.sig = taskSig; }
    if (R.tb) {
      const run = liveTestsFor(id);
      const testSig = theme + JSON.stringify([run.statusText, run.rows.map((r) => r.status), run.command]);
      if (force || testSig !== R.tb.sig) { drawTestBoard(model, R.tb, run); R.tb.sig = testSig; }
    }
  }
}
/* Where the camera goes for a room or for everything: the same direction as the prototype's view, far enough
   for what is shown. */
function liveBounds(ids) {
  const rs = ROOMS.filter((r) => r.shown && (!ids || ids.includes(r.id)));
  if (!rs.length) return null;
  const x0 = Math.min(...rs.map((r) => r.x0)), x1 = Math.max(...rs.map((r) => r.x1));
  const z0 = Math.min(...rs.map((r) => r.z0)), z1 = Math.max(...rs.map((r) => r.z1));
  return { c: new THREE.Vector3((x0 + x1) / 2, 0.4, (z0 + z1) / 2), size: Math.max(x1 - x0, (z1 - z0) * 1.3) };
}
/* The big spec board for a room with many specs (plan 09 §7): the prototype's drawSpecBoard, tile size from the
   count. Each tile is the prototype's drawSpecTile, scaled. */
function drawBigSpecBoard(pb, model, now) {
  const dark = isDark(), P = BOARD[dark ? 'dark' : 'light'], ST = ST_STYLE[dark ? 'dark' : 'light'];
  const ctx = pb.canvas.getContext('2d'), { W, H } = pb, proj = PROJECT[pb.project];
  ctx.fillStyle = P.bg; ctx.fillRect(0, 0, W, H);
  ctx.fillStyle = P.grid;
  for (let x = 0; x < W; x += 32) ctx.fillRect(x, 0, 1, H);
  for (let y = 0; y < H; y += 32) ctx.fillRect(0, y, W, 1);
  ctx.textAlign = 'left'; ctx.textBaseline = 'alphabetic';
  const specs = pb.specs.map((i) => model.specs[i]), c = bucketCounts(specs);
  ctx.fillStyle = P.title; ctx.font = `36px ${FONT_DISPLAY}`; ctx.fillText('spec ボード', 26, 52);
  ctx.fillStyle = P.sub; ctx.font = `700 24px ${FONT_BODY}`;
  fitText(ctx, `${proj.name} · 全 ${specs.length} 画面 · 作業中 ${c.live} · 途中 ${c.partial} · 未着手 ${c.todo} · 完了 ${c.done}`, 276, 50, W - 300);
  const pad = 22, top = 76, n = Math.max(1, specs.length), aspect = 2.6;
  // columns so that the tiles keep roughly the prototype's shape
  let cols = Math.max(1, Math.round(Math.sqrt((n * (W - pad * 2)) / ((H - top - pad) * aspect))));
  while (Math.ceil(n / cols) * ((W - pad * 2) / cols / aspect) > H - top - pad && cols < n) cols += 1;
  const rows = Math.ceil(n / cols), gap = Math.max(4, Math.round(14 * Math.min(1, 8 / cols)));
  const tw = (W - pad * 2 - gap * (cols - 1)) / cols, th = Math.min(tw / aspect * 1.25, (H - top - pad - gap * (rows - 1)) / rows);
  const k = Math.min(1, th / 104), g = Object.fromEntries(Object.entries(PBG).map(([key, v]) => [key, v * k]));
  pb.tiles = [];
  pb.specs.forEach((i, pos) => {
    const x = pad + (pos % cols) * (tw + gap), y = top + Math.floor(pos / cols) * (th + gap);
    drawSpecTile(ctx, P, ST, model.specs[i], x, y, tw, th, now, g);
    pb.tiles.push({ i, x, y, w: tw, h: th, g });
  });
  pb.tex.needsUpdate = true;
}
/* A line from a robot to the part of the board it works on (the prototype's links), live. */
function liveLinks(model, nowSec) {
  const used = new Set();
  if (!zoom.zoomed) {
    model.specs.forEach((s, i) => {
      if (!s.by || !robots.some((R) => R.def.id === s.by)) return;
      const R = LIVE3D.rooms[s.project];
      const t = R && R.pb.tiles.find((q) => q.i === i);
      if (!t) return;
      const [px, py] = tileFocus(t.x, t.y, t.w, t.h, t.g || PBG, activeSec(s));
      linkFor(s.by).set(robotPoint(s.by, HEAD_UP), pbPoint(R.pb, px, py), true, nowSec);
      used.add(s.by);
    });
  }
  for (const [id, L] of Object.entries(links)) if (!used.has(id)) L.set(null, null, false, nowSec);
}
function liveRoomPose(id) {
  if (id !== 'all' && PROJECT[id] && !PROJECT[id].shown) liveShowRoom(id);
  const b = liveBounds(id === 'all' ? null : [id]) || { c: new THREE.Vector3(0, 0.4, 0), size: 12 };
  const dist = id === 'all' ? Math.max(22, b.size * 1.55 + 6) : b.size * 1.9 + 3;
  return { p: b.c.clone().add(new THREE.Vector3(6.5, 15.5, 22.5).normalize().multiplyScalar(dist)), t: b.c };
}
function liveBoardPose(project, which, i) {
  const R = LIVE3D.rooms[project] || Object.values(LIVE3D.rooms)[0];
  if (!R) return { p: camera.position.clone(), t: controls.target.clone() };
  const b = which === 'tasks' ? R.kb : R.pb;
  const t = which !== 'tasks' && i >= 0 ? b.tiles.find((q) => q.i === i) : null;
  if (t) return meshPose(b.mesh, b.w, b.h, (t.x + t.w / 2) / b.W, (t.y + t.h / 2) / b.H, Math.max(1.2, (t.w / b.W) * b.w * 2.2));
  return meshPose(b.mesh, b.w, b.h, undefined, undefined, b.w * 1.15 + 0.6);
}
/* The live phone screen: the command a robot runs on a device (the device itself comes in P7). */
function drawLivePhone(r, t) {
  const c = r.phoneCanvas, ctx = c.getContext('2d'), W = c.width;
  const act = (robotState[r.label] && robotState[r.label].act) || '';
  const run = (Array.isArray(LIVE.slices.tests) ? LIVE.slices.tests : []).find((x) => x && x.status === 'running' && labelOf(x.agentId) === r.label);
  const cases = run && Array.isArray(run.cases) ? run.cases : [];
  const done = cases.filter((c) => c.status === 'passed').length, now = cases.find((c) => c.status === 'running');
  ctx.clearRect(0, 0, c.width, c.height);
  ctx.fillStyle = '#ffffff'; ctx.strokeStyle = '#1d2330'; ctx.lineWidth = 5; ctx.lineJoin = 'round';
  rr(ctx, 6, 6, W - 12, 360, 28); ctx.fill(); ctx.stroke();
  ctx.save(); rr(ctx, 24, 24, 192, 320, 18); ctx.clip();
  ctx.fillStyle = '#0d1828'; ctx.fillRect(24, 24, 192, 320);
  ctx.fillStyle = ROLES[r.role].color; ctx.fillRect(24, 24, 192, 46);
  ctx.textAlign = 'left'; ctx.textBaseline = 'alphabetic';
  ctx.fillStyle = '#ffffff'; ctx.font = `700 15px ${FONT_BODY}`; ctx.fillText('テスト実行', 36, 54);
  ctx.fillStyle = '#9fc3ff'; ctx.font = `600 12px ${FONT_MONO}`;
  wrapText(ctx, act || '待機中', 36, 96, 168, 18, cases.length ? 6 : 12);
  if (cases.length) {
    ctx.fillStyle = '#4fd48a'; ctx.font = `700 14px ${FONT_BODY}`; ctx.fillText(`${done}/${cases.length} 通過`, 36, 222);
    if (now) { ctx.fillStyle = '#ffffff'; ctx.font = `500 12px ${FONT_BODY}`; wrapText(ctx, `▶ ${now.name}`, 36, 244, 168, 16, 3); }
  }
  const ph = (t * 0.9) % 1;
  ctx.beginPath(); ctx.arc(120, 300, 6 + ph * 18, 0, Math.PI * 2); ctx.strokeStyle = `rgba(122, 180, 255, ${(0.9 * (1 - ph)).toFixed(2)})`; ctx.lineWidth = 3; ctx.stroke();
  ctx.restore();
  r.phoneTex.needsUpdate = true; r.phoneScreenTex.needsUpdate = true;
}

if (has3D) build3D();

const tmpV = new THREE.Vector3();
function placeTag(el, p) {
  tmpV.copy(p).project(camera);
  if (tmpV.z > 1 || tmpV.z < -1) { el.style.visibility = 'hidden'; return; }
  el.style.visibility = 'visible';
  const x = ((tmpV.x + 1) / 2) * canvas.clientWidth, y = ((1 - tmpV.y) / 2) * canvas.clientHeight;
  el.style.transform = `translate(${x.toFixed(1)}px, ${y.toFixed(1)}px) translate(-50%, -100%)`;
}
const HEAD_UP = new THREE.Vector3(0, 2.2, 0);
const TAG_UP = new THREE.Vector3(0, 2.62, 0);
function robotPoint(id, up) { const R = robots.find((x) => x.def.id === id); return R.robot.root.position.clone().add(up); }

function update3D(model, nowSec, dt) {
  if (SOURCE.mode === 'live') liveUpdateRobots(nowSec, dt);
  else {
    for (const R of robots) {
      const st = robotState[R.def.id];
      if (st.walk) { R.robot.root.position.x = st.walk.x; R.robot.root.position.z = st.walk.z; R.robot.root.rotation.y = st.walk.ry; }
      if (st.state !== R.robot.state) setRobotState(R.robot, st.state);
      if (st.act !== R.act) { R.act = st.act; R.text.textContent = st.act; }
      updateRobot(R.robot, nowSec, dt);
    }
    // A line from each busy robot to the part of the board it is working on (a2 points at the test board).
    const used = new Set();
    model.specs.forEach((s, i) => {
      if (!s.by || s.by === 'a2' || zoom.zoomed) return;
      let to;
      if (s.project === 'shop') { const [px, py] = sbFocus(SHOP_POS[i], activeSec(s)); to = sbPoint(px, py); }
      else {
        const pb = PBOARD[s.project], t = pb && pb.tiles.find((q) => q.i === i);
        if (!t) return;
        const [px, py] = tileFocus(t.x, t.y, t.w, t.h, PBG, activeSec(s)); to = pbPoint(pb, px, py);
      }
      linkFor(s.by).set(robotPoint(s.by, HEAD_UP), to, true, nowSec);
      used.add(s.by);
    });
    if (model.tests.runningIdx >= 0 && !zoom.zoomed) { linkFor('a2').set(robotPoint('a2', HEAD_UP), tbPoint(TB.W - 70, tbRowTop(model.tests.runningIdx) + 36), true, nowSec); used.add('a2'); }
    for (const [id, L] of Object.entries(links)) if (!used.has(id)) L.set(null, null, false, nowSec);

    const shopTasks = model.tasks.filter((x) => PROJECT_OF[x.list] === 'shop');
    const open = shopTasks.filter((x) => x.status !== 'completed').length;
    const closed = shopTasks.filter((x) => x.status === 'completed').length;
    trayPending.forEach((p, i) => { p.visible = i < open; });
    trayDone.forEach((p, i) => { p.visible = i < closed; });
    trayTag.el.textContent = `書類 未完了 ${open} ／ 完了 ${closed}`;

    const a2 = robots.find((x) => x.def.id === 'a2').robot;
    standMat.map = robotState.a2.state === 'phone' ? a2.phoneScreenTex : standOffTex;
  }

  const w = sceneEl.clientWidth, h = sceneEl.clientHeight, pr = renderer.getPixelRatio();
  if (canvas.width !== Math.floor(w * pr) || canvas.height !== Math.floor(h * pr)) {
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    camera.fov = Math.min(62, 32 * Math.max(1, Math.pow(1.4 / camera.aspect, 0.85)));
    camera.updateProjectionMatrix();
  }
  const sel = rbState.id && robots.find((x) => x.def.id === rbState.id);
  selRing.visible = !!sel;
  if (sel) {
    selRing.position.set(sel.robot.root.position.x, 0.03, sel.robot.root.position.z);
    selRing.material.color.set(ROLES[sel.def.role].color);
    selRing.scale.setScalar(1 + 0.06 * Math.sin(nowSec * 3));
    // keep the robot framed, also while it walks or after switching to another robot
    if (!camTween && zoom.zoomed) { const pose = robotPose(rbState.id); camera.position.lerp(pose.p, 0.08); viewTarget.lerp(pose.t, 0.08); }
  }
  stepTween(performance.now());
  if (camTween || zoom.zoomed) camera.lookAt(viewTarget); else controls.update();
  renderer.render(scene, camera);
  tagsEl.hidden = zoom.zoomed;
  for (const R of robots) placeTag(R.tag, tmpV.copy(R.robot.root.position).add(TAG_UP).clone());
  for (const rt of roomTags) { placeTag(rt.el, rt.p); rt.el.classList.toggle('on', UI.project === rt.id); }
  if (trayTag) placeTag(trayTag.el, trayTag.p);   // the demo's document tray
}
