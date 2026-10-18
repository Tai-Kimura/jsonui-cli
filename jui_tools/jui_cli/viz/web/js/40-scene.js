
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
      ctx.fillStyle = P.title; ctx.font = `700 20px ${FONT_BODY}`; fitText(ctx, `${t.list} ${taskRef(t)} ${t.subject}${t.perm ? '（許可待ち）' : ''}`, 58, ly, W - 90);
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
      if (isTurn(task)) { ctx.fillStyle = task.failed ? P.warn : P.head[col]; ctx.fillRect(nx, ny, 7, noteH); }   // a turn: a stripe down its left edge
      if (task.perm) { ctx.lineWidth = 6; ctx.strokeStyle = P.warn; ctx.strokeRect(nx - 2, ny - 2, nw + 4, noteH + 4); }
      ctx.fillStyle = P.pin; ctx.beginPath(); ctx.arc(nx + nw / 2, ny + 7, 5, 0, Math.PI * 2); ctx.fill();
      ctx.fillStyle = P.soft; ctx.font = `700 15px ${FONT_MONO}`; ctx.fillText(`${task.list} ${taskRef(task)}`, nx + (isTurn(task) ? 14 : 10), ny + 25);
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
// The walls' colour is the --wall token (app.css, light and dark); this is only what a page without the stylesheet gets.
const WALL_FALLBACK = '#ebe4d9';
function buildDemoOffice() {
  const wallMat = toon(readToken('--wall', WALL_FALLBACK));
  roomMats.push([wallMat, '--wall', WALL_FALLBACK]);
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
  controls.minDistance = 8; controls.maxDistance = SOURCE.mode === 'live' ? 80 : 44;   // live: a floor of 3×2 big rooms
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
    if (TOWER.on) return towerHit(ray);
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
    if (h.kind === 'floor') { if (SOURCE.mode === 'live') towerLeave(h.k, h.project); else towerLeave(0); }   // the demo has one office
    else if (h.kind === 'room') setProject(h.project);
    else if (h.kind === 'robot') openRobot(h.id, canvas);
    else if (h.kind === 'tasks') { fit(h.project); openTaskBoard(canvas, undefined, h.project); }
    else if (h.kind === 'spec') { fit(SPECS[h.i].project); openWhiteboard(h.i, canvas); }
    else { fit(h.project); openWhiteboard(-1, canvas, h.project); }
  });
  canvas.addEventListener('pointermove', (ev) => {
    if (ev.buttons || (zoom.zoomed && !rbState.id)) return;
    const h = hitAt(ev);
    canvas.style.cursor = h ? 'pointer' : '';
    canvas.title = h && (h.kind === 'floor' || h.kind === 'room') ? h.title : '';
  });

  sceneEl.addEventListener('pointerdown', () => { DIRECTOR.userAt = performance.now(); });
  sceneEl.addEventListener('wheel', () => { DIRECTOR.userAt = performance.now(); }, { passive: true });
  {
    // The wheel past the farthest distance shows the building; past the nearest in the building, the floor.
    // On the whole scene, not the canvas: a room's or a robot's tag can be under the pointer.
    sceneEl.addEventListener('wheel', (ev) => {
      const d = camera.position.distanceTo(controls.target);
      if (!TOWER.on && ev.deltaY > 0 && d >= controls.maxDistance - 0.5) towerEnter();
      else if (TOWER.on && ev.deltaY < 0 && d <= controls.minDistance + 0.5) towerLeave(LIVE.floor);
    }, { passive: true });
    const step = (d) => (SOURCE.mode === 'demo' ? towerLookAt(TOWER.look + d) : liveFloorStep(d));
    document.getElementById('floor-up').addEventListener('click', () => step(1));
    document.getElementById('floor-down').addEventListener('click', () => step(-1));
    document.getElementById('floor-building').addEventListener('click', () => (TOWER.on ? towerLeave(LIVE.floor) : towerEnter()));
    document.getElementById('weather-switch').addEventListener('click', () => { weatherSwitch(); });
    document.getElementById('room-back').addEventListener('click', () => setProject('all'));
  }
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
  const wallMat = toon(readToken('--wall', WALL_FALLBACK)), floorMat = toon(readToken(room.floor, '#e9eef6'));
  const mats = [[wallMat, '--wall', WALL_FALLBACK], [floorMat, room.floor, '#e9eef6']];
  roomMats.push(...mats);
  const floor = new THREE.Mesh(new RoundedBoxGeometry(w, 0.16, d, 2, 0.05), floorMat); floor.position.set(cx, -0.08, cz); g.add(floor);
  const frameMat = toon('#7a5a3c');
  // the back and left walls, with a door where a room is behind or to the left (requester, 10-18)
  const doors = room.doors || {}, da = doorAt(room), half = DOOR_W / 2;
  for (const wall of liveWalls().filter((q) => q.room === room.id)) {
    const ww = wall.x1 - wall.x0, wd = wall.z1 - wall.z0, hgt = wall.side === 'back' ? room.back : room.left;
    const m = new THREE.Mesh(new THREE.BoxGeometry(ww, hgt, wd), wallMat); m.position.set((wall.x0 + wall.x1) / 2, hgt / 2, (wall.z0 + wall.z1) / 2); g.add(m);
  }
  const doorway = (x, z, along) => {   // a lintel over the gap, a frame round it, a sill across the gap between the rooms
    const hgt = along === 'x' ? room.back : room.left, top = hgt - DOOR_H;
    const lin = new THREE.Mesh(along === 'x' ? new THREE.BoxGeometry(DOOR_W, top, WALL_T) : new THREE.BoxGeometry(WALL_T, top, DOOR_W), wallMat);
    lin.position.set(x, DOOR_H + top / 2, z); g.add(lin);
    for (const [bw, bh, bd, ox, oy, oz] of along === 'x'
      ? [[0.08, DOOR_H, WALL_T + 0.04, -half, DOOR_H / 2, 0], [0.08, DOOR_H, WALL_T + 0.04, half, DOOR_H / 2, 0], [DOOR_W + 0.08, 0.08, WALL_T + 0.04, 0, DOOR_H, 0]]
      : [[WALL_T + 0.04, DOOR_H, 0.08, 0, DOOR_H / 2, -half], [WALL_T + 0.04, DOOR_H, 0.08, 0, DOOR_H / 2, half], [WALL_T + 0.04, 0.08, DOOR_W + 0.08, 0, DOOR_H, 0]]) {
      const bar = new THREE.Mesh(new THREE.BoxGeometry(bw, bh, bd), frameMat); bar.position.set(x + ox, oy, z + oz); g.add(bar);
    }
    const gap = ROOM_GAP + WALL_T;
    const sill = new THREE.Mesh(along === 'x' ? new THREE.BoxGeometry(DOOR_W, 0.16, gap) : new THREE.BoxGeometry(gap, 0.16, DOOR_W), floorMat);
    sill.position.set(along === 'x' ? x : x - gap / 2 + WALL_T / 2, -0.08, along === 'x' ? z - gap / 2 + WALL_T / 2 : z); g.add(sill);
  };
  if (doors.back) doorway(da.backX, room.z0 - WALL_T / 2, 'x');
  if (doors.left) doorway(room.x0 - WALL_T / 2, da.leftZ, 'z');
  // the entrance from the corridor: a mat at the front, where robots come in and go out
  if (doors.front) { const mat = new THREE.Mesh(new THREE.BoxGeometry(DOOR_W, 0.02, 0.6), toon('#c9d0db')); mat.position.set(da.frontX, 0.01, room.z1 - 0.3); g.add(mat); }
  // project board on the back wall; a room with many specs gets the big spec board instead (plan 09 §7), kept
  // clear of the back door
  const pbW = room.big ? w - (doors.back ? 3.2 : 1.2) : Math.min(w - 2.2, 4.2);
  const pb = room.big ? { project: room.id, big: true, W: 2048, H: 1024, w: pbW, h: Math.min(room.back - 0.9, pbW * 1024 / 2048), specs: [], tiles: [], splitY: 1e9, sig: '' }
    : { project: room.id, W: 1024, H: 560, w: pbW, h: pbW * 560 / 1024, specs: [], tiles: [], splitY: 0, sig: '' };
  if (room.big) pb.W = Math.round(pb.H * pb.w / pb.h);
  pb.canvas = makeCanvas(pb.W, pb.H); pb.tex = texFrom(pb.canvas);
  pb.mesh = new THREE.Mesh(new THREE.PlaneGeometry(pb.w, pb.h), new THREE.MeshBasicMaterial({ map: pb.tex, toneMapped: false }));
  const pbX = room.big ? cx - (doors.back ? 1.0 : 0) : cx + 0.4, pbY = room.big ? Math.max(2.35, pb.h / 2 + 0.75) : 2.35;
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
  kb.mesh.rotation.y = Math.PI / 2; kb.mesh.position.set(room.x0 + 0.02, 2.1, doors.left ? Math.min(cz, da.leftZ - half - 0.25 - kw / 2) : cz); g.add(kb.mesh);
  scene.add(g);
  const tag = document.createElement('button');
  tag.type = 'button'; tag.className = 'tag room'; tag.dataset.setProject = room.id; tag.title = `${room.name} だけを表示する`; tag.textContent = room.name;
  tagsEl.append(tag);
  // over its own back wall's left end: at the front corner it sat on the back edge of the room in front (3×2 floors)
  const rt = { el: tag, id: room.id, p: new THREE.Vector3(room.x0 + 0.6, room.back + 0.35, room.z0 - 0.05) };
  roomTags.push(rt);
  return { geo: room.geo, group: g, floor, pb, kb, tb, rt, mats };
}
function liveDropRoom(id) {
  const R = LIVE3D.rooms[id];
  if (!R) return;
  if (PROPS.room === id) propsClear();   // the floor's own material goes back before the room is disposed
  scene.remove(R.group); focusRelease(R.group); disposeTree(R.group);   // focusRelease: 50-panel.js, the faint walls (10-18)
  R.rt.el.remove();
  roomTags.splice(roomTags.indexOf(R.rt), 1);
  for (const m of R.mats) roomMats.splice(roomMats.indexOf(m), 1);
  delete LIVE3D.rooms[id];
}
function liveAddRobot(d, i) {
  const robot = createRobot({ label: d.id, role: d.role, state: 'idle', seed: i * 1.7, furnished: true });
  robot.drawPhone = drawLivePhone;
  // a robot that comes in walks from the corridor through the doors (requester, 10-18)
  const route = d.enter ? liveRoute(null, d.room) : [];
  const start = route.length ? route[0] : d.pos || [0, 0];
  robot.root.position.set(start[0], 0, start[1]); robot.root.rotation.y = d.ry || 0;
  robot.root.userData.robotId = d.id;
  scene.add(robot.root);
  const tag = addTag('', `${pill(d.id, d.role)}<span></span>`);
  const R = { def: d, robot, tag, text: tag.lastElementChild, act: '', path: [], room: d.room, seatKey: '', exitAt: 0 };
  if (route.length) R.path = route.slice(1);
  d.enter = false;
  robots.push(R);
  return R;
}
function liveDropRobot(R) {
  scene.remove(R.robot.root); focusRelease(R.robot.root); disposeTree(R.robot.root);   // focusRelease: 50-panel.js (10-18)
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
    if (LIVE3D.floorMove) LIVE3D.floorMove = false;   // the floor change flies the camera itself
    else if (TOWER.on) { /* looking at the building: a regrouped floor does not move the camera */ }
    else if (!zoom.zoomed && (UI.project === 'all' || !PROJECT[UI.project] || !PROJECT[UI.project].shown)) focusProject('all', LIVE3D.rev <= 1);
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
  const root = R.robot.root, here = [root.position.x, root.position.z];
  const rm = PROJECT[d.room], rect = rm ? `${rm.x0},${rm.z0},${rm.x1},${rm.z1}` : '';
  const moved = R.seatKey && R.room === d.room && R.rect && R.rect !== rect;   // its room was laid out again (another slot, the one-room view)
  R.rect = rect;
  if (R.play || R.brk) {   // a break (10-19) keeps its path the same way: brkStop walks it to this seat
    // At play (2.3.1): the path is the game's. Taking it sent a player to its new desk, and there liveWalk read the
    // empty path as "at the spot" and it played from its desk (e2e, 1 run in 3). The game ends on its own reasons;
    // playStop then walks it to this seat (through the doors when the room changed).
    R.room = d.room; R.seatKey = key;
    return;
  }
  if (moved) { root.position.x = d.pos[0]; root.position.z = d.pos[1]; R.path = []; R.jumps = (R.jumps || 0) + 1; }
  else if (R.seatKey && R.room !== d.room) {
    // to another room: finish the step it is on, then through the doors (never a straight line through a wall)
    const next = R.path.length ? R.path[0] : here;
    R.path = [...(R.path.length ? [next] : []), ...liveRoute(roomAtPoint(next), d.room), d.pos];
  } else if (R.seatKey && R.path.length > 1) R.path[R.path.length - 1] = d.pos;   // still on its way: a new seat at the end
  else if (R.seatKey && roomAtPoint(here) !== d.room) { root.position.x = d.pos[0]; root.position.z = d.pos[1]; R.path = []; R.jumps = (R.jumps || 0) + 1; }   // its room moved under it (counted: the e2e wall check skips a jump)
  else if (R.seatKey) R.path = [d.pos];   // another seat in the same room
  else R.path.push(d.pos);                // first seat: after the doors when it just came in
  R.room = d.room; R.seatKey = key;
}
function liveWalk(R, dt, nowMs) {
  const root = R.robot.root, d = R.def;
  // Leaving is a state, not a layout change: start the "done, then out of the door" here.
  if (LIVE.leaving[d.id]) { if (!R.exitAt && !R.out) R.exitAt = nowMs + 2500; }
  else if (R.exitAt && !R.out) R.exitAt = 0;   // it came back before walking out
  if (R.exitAt && nowMs >= R.exitAt && !R.path.length && !R.out) {
    R.path = liveRoute(roomAtPoint([root.position.x, root.position.z]), null);   // out to the corridor
    R.out = true;
  }
  if (R.out && !R.path.length) { SOURCE.robotGone(d.id); return 'gone'; }
  const next = R.path[0];
  if (!next && R.play) {                                          // at the play spot: no desk, facing the partner
    if (R.robot.desk) R.robot.desk.visible = false;
    R.play.phase = 'playing';
    const q = R.play.partner.robot.root.position, ry = Math.atan2(q.x - root.position.x, q.z - root.position.z) + (R.play.turn || 0);
    root.rotation.y += (ry - root.rotation.y) * Math.min(1, dt * (R.play.turn !== undefined ? 12 : 6));   // highfive: turns to slap
    return 'playing';
  }
  if (!next && R.brk) return brkAt(R, dt);                        // at the smoking booth or the vending machine (10-19)
  if (!next && R.playBack) R.playBack = false;                    // back at its desk
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
/* Coffee and meals, now and then (requester, 10-18): once a second each robot that is idle or at work may start
   one (probability SNACK.p, a seeded generator so a test can repeat it), while at most SNACK.share of the robots
   (at least one) are at it. Never while waiting, thinking or done (startGesture refuses), none under reduced motion. */
const SNACK = { seed: 20261018, p: 1 / 90, share: 0.15, next: 0, rng: null };
function snackRandom(seed = SNACK.seed) {
  let a = seed >>> 0;
  return () => { a = (a + 0x6d2b79f5) >>> 0; let t = Math.imul(a ^ (a >>> 15), 1 | a); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
}
function snackTick(t) {
  if (reduceMotion || t < SNACK.next) return;
  SNACK.next = t + 1;
  if (!SNACK.rng) SNACK.rng = snackRandom();
  const here = robots.filter((R) => !LIVE.leaving[R.def.id]);
  const cap = Math.max(1, Math.floor(here.length * SNACK.share));
  let busy = here.filter((R) => R.robot.gesture && R.robot.gesture.kind !== 'drink').length;
  for (const R of here) {
    if (busy >= cap) break;
    if (R.robot.gesture || !GESTURE_OK.has(R.robot.state)) continue;
    if (SNACK.rng() < SNACK.p && startGesture(R.robot, SNACK.rng() < 0.5 ? 'coffee' : 'meal', t)) busy += 1;
  }
}
/* A call on the robot and on its name tag: a phone mark and the other robot's number, never the message. */
const CALL_TAG_TEXT = { dialing: '発信中', ringing: '呼び出し中', answered: '通話中' };
/* Alone at its desk (2.3.1): the name tag says so too — the robot is small in any view, so the zzz and the bento alone
   were hard to see (jsonuidocument-96, 10-18). The call mark wins; a call stops a nap anyway. */
const SOLO_TAG_TEXT = { nap: 'zzz 居眠り', bento: '弁当' };
function liveCallTag(R, call) {
  R.robot.call = call && CALL_ON_LINE.has(call.state) ? call : null;
  const c = R.robot.call;
  const text = c ? `☎ ${c.role === 'callee' && c.state !== 'answered' ? '着信' : CALL_TAG_TEXT[c.state]}${c.peer ? ` ${c.peer}` : ''}`
    : R.solo ? SOLO_TAG_TEXT[R.solo.kind] || '' : playText(R) || brkTagText(R);   // a game and a break never overlap
  if (text === (R.callText || '')) return;
  R.callText = text;
  if (!R.callEl) { R.callEl = document.createElement('span'); R.callEl.className = 'call-mark'; R.tag.insertBefore(R.callEl, R.text); }
  R.callEl.textContent = text;
  R.callEl.hidden = !text;
  R.callEl.classList.toggle('solo-mark', !c && !!text);
  R.tag.classList.toggle('on-call', !!c);
}
/* Play (requester, 10-18): "同じ部屋で待機が長いロボットが複数いたらロボット同士で遊ぶ", "動きはランダムでいい",
   "遊んだらまた元の場所に戻る", "指示が来たら遊ぶのやめて作業始めて". Looks only: the server, the panel and the tasks
   still say 待機. Main robots only (a subagent idle for long has usually left). Once a second a room with two robots
   idle for PLAY.idleMs or more may start a game (probability PLAY.p, a seeded generator): the two walk to the front
   aisle of their room, play one of PLAY_KINDS for a random while, and walk back to their desks. Any reason to stop —
   anything the server sets on the robot (an instruction keeps the state idle and changes only its act and updatedAt:
   jsonuidocument-96, 10-18), the robot no longer idle, its phone rings, it leaves, its seat moves — stops it at once: it
   walks back with its real lamp (through the doors when its desk is in another room now), and a partner left alone
   walks back too. A robot that played rests a while before the next game; at most PLAY.games at a time, one to a room,
   and none in a room with standing robots (a full room: they stand along the front wall, where the game would be).
   None under reduced motion. The e2e build can shorten the times (80-dbg.js). */
const PLAY_KINDS = ['ball', 'highfive', 'rps'];
/* 2.3.1 (requester, 10-18: "完了とか待機でもあんまり遊ばない"): idle for a minute, about 15 s to start once two are there,
   shorter rests, three games at a time. A robot that finished (完了) is idle again three seconds later and counts from
   then. Robots alone in their room nap or eat a bento at their desks (SOLO). Every end is kept with its reason in
   PLAY.ends (80-dbg.js shows them): the requester saw two walk up and go back without playing. */
const PLAY = { seed: 20261019, kinds: PLAY_KINDS, idleMs: 60_000, p: 1 / 15, games: 3, minSec: 15, maxSec: 35, restMinSec: 45, restMaxSec: 120,
  walkSec: 30, next: 0, rng: null, list: [], ends: [] };
const SOLO_KINDS = ['nap', 'bento'];
const SOLO = { p: 1 / 20, minSec: 20, maxSec: 60, kinds: SOLO_KINDS };
/* What a game looks like (2.3.3, requester 10-19: "ずっと二人で向き合ってるだけで何やってるかわからない"): the name tag,
   the robot's card and the building's window say which game it is (遊びに行く on the way), the ball is big enough to
   see from the usual view and goes from hand to hands, and at highfive the two walk toward each other and slap with a
   パチン mark. The poses are 10-robot-core.js's; both read the same phase helpers (ballPhase, highfivePhase). */
const PLAY_LOOK = { ballR: 0.3, gap: { ball: 1.3, highfive: 1.4 }, hfNear: 0.8 };   // gap: half the distance between the two spots
const PLAY_TAG_TEXT = { ball: 'キャッチボール中', highfive: 'ハイタッチ中', rps: 'じゃんけん中' };
function playText(R) {
  if (!R.play) return '';
  return R.robot.play ? PLAY_TAG_TEXT[R.robot.play.kind] || '' : '遊びに行く';
}
function playTagText(id) { const R = robots.find((x) => x.def.id === id); return R ? playText(R) : ''; }   // the card (50-panel.js)
function playRoomText(room) { const G = PLAY.list.find((x) => x.room === room); return !G ? '' : G.t0 ? PLAY_TAG_TEXT[G.kind] || '' : '遊びに行く'; }   // the building
const playV = [new THREE.Vector3(), new THREE.Vector3(), new THREE.Vector3()];
function playHand(r, side, out) { return (side === 'L' ? r.armL : r.armR).localToWorld(out.set(0, -0.38, 0)); }
function pachinCanvas() {
  const c = makeCanvas(280, 180), ctx = c.getContext('2d');
  ctx.beginPath();
  for (let i = 0; i < 24; i++) { const a = (i / 24) * Math.PI * 2, rad = i % 2 ? 52 : 88; ctx.lineTo(140 + Math.cos(a) * rad * 1.45, 90 + Math.sin(a) * rad); }
  ctx.closePath(); ctx.fillStyle = '#ffd23f'; ctx.fill(); ctx.lineWidth = 7; ctx.strokeStyle = '#1f2532'; ctx.lineJoin = 'round'; ctx.stroke();
  ctx.font = `700 52px ${FONT_DISPLAY}`; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
  ctx.lineWidth = 8; ctx.strokeStyle = '#ffffff'; ctx.strokeText('パチン!', 140, 92);
  ctx.fillStyle = '#d0352b'; ctx.fillText('パチン!', 140, 92);
  return c;
}
function playMove(G, left, nowSec) {
  if (left.length < 2) return;
  const u = Math.max(0, nowSec - G.t0);
  if (G.kind === 'ball') {
    if (!G.ball) { G.ball = new THREE.Mesh(new THREE.SphereGeometry(PLAY_LOOK.ballR, 16, 12), toon('#ff7a3d')); scene.add(G.ball); }
    const { n, thrower, w } = ballPhase(u), from = left[thrower].robot, to = left[1 - thrower].robot;
    const hand = playHand(from, 'R', playV[0]);
    if (w < BALL_T.release) { G.ball.position.copy(hand); return; }   // in the thrower's hand through the wind-up
    if (G.ballN !== n) { G.ballFrom = hand.clone(); G.ballN = n; }
    const at = playHand(to, 'L', playV[1]).add(playHand(to, 'R', playV[2])).multiplyScalar(0.5);   // between the catcher's hands
    const k = (w - BALL_T.release) / (1 - BALL_T.release);
    G.ball.position.lerpVectors(G.ballFrom, at, k); G.ball.position.y += Math.sin(Math.PI * k) * 0.8;
  } else if (G.kind === 'highfive') {
    const H = highfivePhase(u), [a, b] = left, sa = a.play.spot, sb = b.play.spot;
    const dx = sb[0] - sa[0], dz = sb[1] - sa[1], d = Math.hypot(dx, dz) || 1;
    const walk = Math.max(0, d / 2 - PLAY_LOOK.hfNear) * H.near;   // each walks this far toward the other
    left.forEach((R, i) => {
      const s = i ? -1 : 1, root = R.robot.root;
      root.position.x = R.play.spot[0] + (s * dx / d) * walk; root.position.z = R.play.spot[1] + (s * dz / d) * walk;
      R.play.turn = (i ? 1 : -1) * HIGHFIVE_T.turn * H.up;   // a little to the front: the inner hands meet between them
    });
    if (!G.mark) {
      G.mark = new THREE.Sprite(new THREE.SpriteMaterial({ map: texFrom(pachinCanvas()), transparent: true, depthTest: false }));
      G.mark.renderOrder = 6; G.mark.scale.set(1.5, 0.96, 1); G.mark.userData.playMark = true; scene.add(G.mark);
    }
    G.mark.visible = H.slap;
    if (H.slap) { G.mark.position.copy(playHand(a.robot, 'L', playV[0])).add(playHand(b.robot, 'R', playV[1])).multiplyScalar(0.5); G.mark.position.y += 0.6; }
  }
}
const playIdle = (R, st, now) => R.def.kind === 'main' && st.state === 'idle' && Number.isFinite(st.since) && st.since > 0
  && now - st.since >= PLAY.idleMs && !LIVE.leaving[R.def.id] && !R.robot.call && !R.path.length && !R.playBack && !R.play && !R.solo && !R.brk;
/* Why a robot stops (null: it does not): the reasons the requester's "walked up and went back" can be told by. Only a
   desk in another room stops it now; a desk that moves within the room (another session came or went and the room
   was laid out again — common with many sessions) no longer does: it walks back to the new desk afterwards. */
function playStopReason(R, st, room, since) {
  if (!robots.includes(R)) return 'gone';
  if (LIVE.leaving[R.def.id]) return 'leaving';
  if (R.robot.call) return 'call';
  if (st.state !== 'idle') return `state:${st.state}`;
  if (st.since !== since) return 'updated';
  if (R.def.room !== room) return 'room';
  return null;
}
function playLog(G, reason, nowSec) {
  PLAY.ends.push({ room: G.room, kind: G.kind, players: G.players.map((R) => R.def.id), reason, playedSec: G.t0 ? +(nowSec - G.t0).toFixed(1) : 0 });
  if (PLAY.ends.length > 30) PLAY.ends.shift();
}
function playStop(R) {
  if (!R.play) return;
  R.play = null; R.robot.play = null; R.playBack = true;
  if (R.robot.desk) R.robot.desk.visible = false;
  const p = R.robot.root.position, from = roomAtPoint([p.x, p.z]);
  R.path = from && from !== R.def.room ? [...liveRoute(from, R.def.room), R.def.pos] : [R.def.pos];   // never through a wall
}
function playEnd(G) {
  for (const R of G.players) playStop(R);
  if (G.ball) { scene.remove(G.ball); G.ball.geometry.dispose(); G.ball.material.dispose(); }
  if (G.mark) { scene.remove(G.mark); G.mark.material.map.dispose(); G.mark.material.dispose(); }
  PLAY.list.splice(PLAY.list.indexOf(G), 1);
}
/* The game's room laid out again (another room came or went, its robot count changed its size): the spot and the
   players move with it, as a jump (the e2e wall check skips jumps, as it does for livePlan's), and the game goes on.
   Without it the spot and the players stayed where the room had been — inside a wall of the new layout. */
// ball and highfive (2.3.3): farther apart, so the ball's flight shows and the two can walk toward each other (playMove)
const playSpotOf = (rm, side, kind) => [(rm.x0 + rm.x1) / 2 + (side ? 1 : -1) * (PLAY_LOOK.gap[kind] || 0.8), rm.z1 - 0.9];
function playFollowRoom(G) {
  const rm = PROJECT[G.room];
  if (!rm) return;
  const rect = `${rm.x0},${rm.z0},${rm.x1},${rm.z1}`;
  if (rect === G.rect) return;
  G.rect = rect;
  G.players.forEach((R, i) => {
    if (!R.play) return;
    const to = playSpotOf(rm, i, G.kind), dx = to[0] - R.play.spot[0], dz = to[1] - R.play.spot[1];
    const root = R.robot.root;
    root.position.x += dx; root.position.z += dz;
    R.path = R.path.map((p) => [p[0] + dx, p[1] + dz]);
    R.play.spot = to;
    R.jumps = (R.jumps || 0) + 1;
  });
}
function playTick(nowSec, now) {
  // stop at once: every frame
  for (const G of [...PLAY.list]) {
    playFollowRoom(G);
    let why = null;
    for (const R of G.players) {
      if (!R.play) continue;
      const reason = playStopReason(R, robotState[R.def.id] || { state: 'idle' }, G.room, R.play.since);
      if (reason) { playStop(R); why = why || `${R.def.id} ${reason}`; }
    }
    const left = G.players.filter((R) => R.play);
    const at = left.filter((R) => R.play.phase === 'playing');
    if (at.length === left.length && left.length >= 2 && !G.t0) {   // all there: the game's clock starts now
      G.t0 = nowSec; G.until = nowSec + G.len;
      left.forEach((R, i) => { R.robot.play = { kind: G.kind, t0: nowSec, side: i, seed: G.seed }; });
    }
    const end = left.length < 2 ? `alone (${why || 'partner stopped'})` : G.t0 && nowSec >= G.until ? 'done'
      : !G.t0 && nowSec >= G.walkUntil ? 'walk too long' : null;
    if (end) { playLog(G, end, nowSec); G.players = left; playEnd(G); continue; }
    if (G.t0) playMove(G, left, nowSec);
  }
  if (reduceMotion || nowSec < PLAY.next) return;
  PLAY.next = nowSec + 1;
  if (!PLAY.rng) PLAY.rng = snackRandom.call(null, PLAY.seed);
  if (PLAY.list.length >= PLAY.games) return;
  const byRoom = {};
  for (const R of robots) {
    const st = robotState[R.def.id];
    if (!st || !playIdle(R, st, now) || (R.restUntil || 0) > nowSec) continue;
    (byRoom[R.def.room] = byRoom[R.def.room] || []).push(R);
  }
  for (const [room, idle] of Object.entries(byRoom)) {
    if (PLAY.list.length >= PLAY.games || idle.length < 2 || PLAY.list.some((G) => G.room === room) || !PROJECT[room]) continue;
    if (robots.some((R) => R.def.room === room && R.def.standing)) continue;   // a full room: no aisle to play in
    if (PLAY.rng() >= PLAY.p) continue;
    const a = idle.splice(Math.floor(PLAY.rng() * idle.length), 1)[0], b = idle[Math.floor(PLAY.rng() * idle.length)];
    const rm = PROJECT[room];
    const kind = PLAY.kinds[Math.floor(PLAY.rng() * PLAY.kinds.length)];
    const len = PLAY.minSec + PLAY.rng() * (PLAY.maxSec - PLAY.minSec);
    PLAY.count = (PLAY.count || 0) + 1;
    const G = { room, kind, players: [a, b], t0: 0, len, until: 0, walkUntil: nowSec + PLAY.walkSec, ball: null, rect: `${rm.x0},${rm.z0},${rm.x1},${rm.z1}`, seed: PLAY.seed + PLAY.count };
    [a, b].forEach((R, i) => {
      const spot = playSpotOf(rm, i, kind);
      R.play = { phase: 'going', spot, partner: i ? a : b, since: robotState[R.def.id].since, len, kind };
      R.path = [spot];
      R.restUntil = nowSec + PLAY.walkSec + len + PLAY.restMinSec + PLAY.rng() * (PLAY.restMaxSec - PLAY.restMinSec);
    });
    PLAY.list.push(G);
  }
  soloTick(nowSec, now);
}
/* Alone (requester, 10-18: "一人の部屋のやつはzzzで居眠りしたり弁当食べたりさせてほしい"): a robot idle for long that has
   no one to play with in its room naps (its head nods, zzz) or eats a bento at its desk, for a while. It stops on the
   same reasons as a game. The state, its lamp and its label stay as they are; it never leaves its desk. */
function soloStop(R) { R.solo = null; R.robot.solo = null; }
function soloTick(nowSec, now) {
  for (const R of robots) {
    if (!R.solo) continue;
    const st = robotState[R.def.id] || { state: 'idle' };
    const reason = playStopReason(R, st, R.solo.room, R.solo.since) || (nowSec >= R.solo.until ? 'done' : null) || (R.path.length ? 'walking' : null);
    if (reason) { PLAY.ends.push({ room: R.solo.room, kind: R.solo.kind, players: [R.def.id], reason, playedSec: +(nowSec - R.solo.t0).toFixed(1) }); soloStop(R); }
  }
  if (reduceMotion || nowSec < (SOLO.next || 0)) return;
  SOLO.next = nowSec + 1;
  const byRoom = {};
  for (const R of robots) {
    const st = robotState[R.def.id];
    if (st && playIdle(R, st, now)) (byRoom[R.def.room] = byRoom[R.def.room] || []).push(R);
  }
  for (const [room, idle] of Object.entries(byRoom)) {
    // with two or more a game comes first; one left over (or alone) may nap or eat
    if (idle.length !== 1) continue;
    const R = idle[0];
    if ((R.restUntil || 0) > nowSec || PLAY.rng() >= SOLO.p) continue;
    const kind = SOLO.kinds[Math.floor(PLAY.rng() * SOLO.kinds.length)], len = SOLO.minSec + PLAY.rng() * (SOLO.maxSec - SOLO.minSec);
    R.solo = { kind, room, t0: nowSec, until: nowSec + len, since: robotState[R.def.id].since };
    R.robot.solo = { kind, t0: nowSec };
    R.restUntil = nowSec + len + PLAY.restMinSec + PLAY.rng() * (PLAY.restMaxSec - PLAY.restMinSec);
  }
}
function liveUpdateRobots(nowSec, dt) {
  if (SOURCE.layoutRev !== LIVE3D.rev) liveSync();
  liveLinks(latestModel, nowSec);
  const nowMs = performance.now();
  // Walking uses the real time between frames (up to 1 s), not the animation's capped step: a slow frame rate
  // must not slow the walk down.
  const walkDt = LIVE3D.lastWalk ? Math.min(1, (nowMs - LIVE3D.lastWalk) / 1000) : 0;
  LIVE3D.lastWalk = nowMs;
  snackTick(nowSec);
  const now = vizNow();
  playTick(nowSec, now);
  brkTick(nowSec, now);
  const calls = callsByLabel();
  for (const R of [...robots]) {
    const st = robotState[R.def.id] || { state: 'idle', act: '' };
    liveCallTag(R, calls[R.def.id] || null);
    setRobotTired(R.robot, R.def.kind === 'main' && isTired(sinceOf(R.def.id), now));
    R.robot.heavy = heavyOf(R.def.id);   // fast typing and sweat while it works (the robot decides when)
    const how = liveWalk(R, walkDt, nowMs);
    if (how === 'gone') continue;
    const playing = !!(R.play || R.playBack || R.brk);
    R.robot.lampState = playing ? st.state : null;   // to, at and back from play: the real state's lamp
    const vis = how === 'walking' ? (playing ? 'stroll' : 'carry') : how === 'playing' ? 'idle' : st.state;
    if (vis !== R.robot.state) setRobotState(R.robot, vis);
    if (st.act !== R.act) { R.act = st.act; R.text.textContent = st.act; }
    updateRobot(R.robot, nowSec, dt);
  }
  propsTick(nowSec, dt);
}
/* One room at a time (requester, 10-18): a project picked (its room's tag, its floor in 3D, the menu) lays out only
   that room, wider (layoutRooms, SOLO_GROW), with the way back at the top left. The other rooms' robots keep their
   desks for when the floor comes back. */
const liveSolo = () => (SOURCE.mode === 'live' ? soloRoomId() : null);
function liveSoloSync() {
  const solo = liveSolo();
  for (const [id, R] of Object.entries(LIVE3D.rooms)) { const on = !solo || id === solo; R.group.visible = on; R.rt.el.hidden = !!solo; }   // alone, its name is in the box
  for (const R of robots) {
    const p = R.robot.root.position, on = !solo || R.def.room === solo || roomAtPoint([p.x, p.z]) === solo;
    R.robot.root.visible = on; R.tag.hidden = !on;
  }
  const box = document.getElementById('room-solo');
  if (!box) return;
  box.hidden = !solo || !has3D || TOWER.on || zoom.zoomed;
  if (solo) setText(document.getElementById('room-solo-name'), PROJECT[solo].name);
}
/* ---------- the room up close: a water server, a robot vacuum and a wooden floor (requester, 10-18) ----------
   Only in the one-room view (room-solo) and only while that room has 10 robots or fewer; built when it is wanted and
   disposed as soon as it is not (back to the floor, the building, an 11th robot). The floor's own material is swapped
   for a toon material with a canvas plank texture (512 px, repeated; no image, no light, no shadow) and put back.
   2.3.3 (requester, 10-19): a glass smoking booth and a vending machine come with them, on the same rule (the one-room
   view, PROPS.max robots or fewer); robots on a break walk to them (BRK below). Where the three stand: propsPlace. */
const PROPS = { max: 10, room: null, geo: null, dark: null, group: null, server: null, vac: null, woodMat: null, woodTex: null, floorMat: null,
  boxes: [], boxesAt: 0, rng: null, seed: 20261020, speed: 0.45, radius: 0.64, serverScale: 1.9,   // the robots' scale (they stand about 1 m)
  place: null, booth: null, vend: null, fan: null, smoke: [] };
const PROPS_EMPTY = { room: null, geo: null, dark: null, group: null, server: null, vac: null, woodMat: null, woodTex: null, floorMat: null, boxes: [], boxesAt: 0,
  place: null, booth: null, vend: null, fan: null, smoke: [] };
function woodTexture(dark) {
  const N = 512, cv = makeCanvas(N, N), ctx = cv.getContext('2d'), W = { rng: snackRandom(PROPS.seed) };   // the same planks every time
  const base = dark ? [92, 72, 55] : [214, 184, 146], rows = 8, h = N / rows;
  for (let r = 0; r < rows; r++) {
    let x = -Math.floor(W.rng() * N);
    while (x < N) {
      const len = N * (0.45 + W.rng() * 0.5), k = (W.rng() - 0.5) * (dark ? 14 : 22);
      ctx.fillStyle = `rgb(${base.map((c) => Math.round(c + k)).join(',')})`;
      ctx.fillRect(x, r * h, len, h);
      ctx.globalAlpha = dark ? 0.10 : 0.12;   // a few faint grain lines along the plank
      ctx.strokeStyle = dark ? '#2b2018' : '#8a6a45'; ctx.lineWidth = 1;
      for (let g = 0; g < 4; g++) { const y = r * h + 6 + W.rng() * (h - 12); ctx.beginPath(); ctx.moveTo(x, y); ctx.bezierCurveTo(x + len / 3, y + (W.rng() - 0.5) * 6, x + len * 2 / 3, y + (W.rng() - 0.5) * 6, x + len, y); ctx.stroke(); }
      ctx.globalAlpha = 1;
      ctx.fillStyle = dark ? '#2a1f17' : '#9c7b55'; ctx.fillRect(x, r * h, 2, h);   // the joint at the plank's end
      x += len;
    }
    ctx.fillStyle = dark ? '#2a1f17' : '#a5845c'; ctx.fillRect(0, r * h, N, 2);       // the seam between rows
  }
  const t = texFrom(cv); t.wrapS = t.wrapT = THREE.RepeatWrapping;
  return t;
}
function propsWanted() {
  const solo = liveSolo();
  if (!solo || !has3D || TOWER.on || !LIVE3D.rooms[solo]) return null;
  return robots.filter((R) => R.def.room === solo).length <= PROPS.max ? solo : null;
}
function propsClear() {
  if (!PROPS.room) return;
  const R = LIVE3D.rooms[PROPS.room];
  if (R && PROPS.floorMat && R.floor.material === PROPS.woodMat) R.floor.material = PROPS.floorMat;
  if (PROPS.group) { scene.remove(PROPS.group); disposeTree(PROPS.group); }
  if (PROPS.woodMat) PROPS.woodMat.dispose();
  if (PROPS.woodTex) PROPS.woodTex.dispose();
  Object.assign(PROPS, PROPS_EMPTY, { boxes: [], smoke: [] });
}
function propsBuild(id) {
  const r = PROJECT[id], R = LIVE3D.rooms[id], g = new THREE.Group();
  PROPS.room = id; PROPS.geo = R.geo; PROPS.dark = isDark(); PROPS.group = g; PROPS.rng = snackRandom(PROPS.seed);
  // the floor: the same mesh, a wooden material while the room is up close
  PROPS.woodTex = woodTexture(PROPS.dark); PROPS.woodTex.repeat.set((r.x1 - r.x0) / 2.4, (r.z1 - r.z0) / 2.4);
  PROPS.woodMat = toon('#ffffff', { map: PROPS.woodTex }); PROPS.floorMat = R.floor.material; R.floor.material = PROPS.woodMat;
  // the water server: the back-right corner (propsPlace), in sight from the usual view
  const P = PROPS.place = propsPlace(r);
  const sv = new THREE.Group(), body = toon('#eef1f4'), dark = toon('#5b6573');
  const cab = new THREE.Mesh(new RoundedBoxGeometry(0.42, 0.95, 0.38, 2, 0.04), body); cab.position.y = 0.475; sv.add(cab);
  const panel = new THREE.Mesh(new THREE.BoxGeometry(0.3, 0.22, 0.02), dark); panel.position.set(0, 0.72, 0.2); sv.add(panel);
  for (const [x, c] of [[-0.07, '#4aa3ff'], [0.07, '#ff6b5b']]) { const tap = new THREE.Mesh(new THREE.BoxGeometry(0.05, 0.05, 0.06), toon(c)); tap.position.set(x, 0.66, 0.22); sv.add(tap); }
  const tray = new THREE.Mesh(new THREE.BoxGeometry(0.28, 0.03, 0.12), dark); tray.position.set(0, 0.5, 0.2); sv.add(tray);
  const tank = new THREE.Mesh(new THREE.CylinderGeometry(0.15, 0.15, 0.42, 20), toon('#8fd0f2', { transparent: true, opacity: 0.82 }));
  tank.position.y = 0.95 + 0.21; sv.add(tank);
  const cap = new THREE.Mesh(new THREE.CylinderGeometry(0.06, 0.06, 0.04, 12), toon('#2f7fd1')); cap.position.y = 1.39; sv.add(cap);
  sv.scale.setScalar(PROPS.serverScale);   // built at 1, shown bigger (requester, 10-18: the robots' size)
  sv.position.set(P.server.x, 0, P.server.z); sv.rotation.y = P.server.ry; g.add(sv); PROPS.server = sv;
  PROPS.booth = boothBuild(P.booth); g.add(PROPS.booth);
  PROPS.vend = vendBuild(P.vend); g.add(PROPS.vend);
  // the robot vacuum: a flat disc with a bumper and a light, on the floor clear of desks, robots and the front aisle
  const vac = new THREE.Group();
  const shell = new THREE.Mesh(new THREE.CylinderGeometry(PROPS.radius, PROPS.radius, 0.11, 32), toon('#3a3f47')); shell.position.y = 0.065; vac.add(shell);
  const top = new THREE.Mesh(new THREE.CylinderGeometry(PROPS.radius * 0.74, PROPS.radius * 0.74, 0.02, 28), toon('#5d6470')); top.position.y = 0.13; vac.add(top);
  const bumper = new THREE.Mesh(new THREE.CylinderGeometry(PROPS.radius * 1.02, PROPS.radius * 1.02, 0.04, 32, 1, true, -Math.PI / 2, Math.PI), toon('#9aa3ad')); bumper.position.y = 0.05; vac.add(bumper);
  const lamp = new THREE.Mesh(new THREE.SphereGeometry(0.04, 12, 8), toon('#52e08a')); lamp.position.set(0, 0.145, PROPS.radius * 0.5); vac.add(lamp);
  vac.userData.heading = PROPS.rng() * Math.PI * 2;
  g.add(vac); PROPS.vac = vac;
  propsBoxes(0, true);
  const start = propsSpot();
  vac.position.set(start[0], 0, start[1]);
  scene.add(g);
}
// Where the vacuum may go: the room's floor less the front aisle (doors, the play spot, the easel) and the corner of the
// water server; and never into a robot or its desk (their boxes, kept current while robots come and go).
function propsArea() {
  const r = PROJECT[PROPS.room];
  return { x0: r.x0 + 0.3, x1: r.x1 - 0.3, z0: r.z0 + 0.3, z1: r.z1 - SEAT.aisleF - 0.1 };
}
function propsBoxes(nowSec, force) {
  if (!force && nowSec - PROPS.boxesAt < 0.25) return;
  PROPS.boxesAt = nowSec;
  const box = new THREE.Box3();
  PROPS.boxes = robots.filter((R) => R.robot.root.visible && (R.def.room === PROPS.room || roomAtPoint([R.robot.root.position.x, R.robot.root.position.z]) === PROPS.room))
    .map((R) => { box.setFromObject(R.robot.root); return [box.min.x, box.max.x, box.min.z, box.max.z]; });
  const s = PROPS.server.position;
  const half = 0.42 * PROPS.serverScale;
  PROPS.boxes.push([s.x - half, s.x + half, s.z - half, s.z + half]);
  const P = PROPS.place;   // the booth and the machine with the spot in front of it (10-19)
  PROPS.boxes.push([P.booth.x0, P.booth.x1, P.booth.z0, P.booth.z1], [P.vend.x0, P.vend.x1, P.vend.z0, P.vend.spot[1] + 0.3]);
}
function propsClearAt(x, z) {
  const a = propsArea(), m = PROPS.radius + 0.06;
  if (x < a.x0 || x > a.x1 || z < a.z0 || z > a.z1) return false;
  return !PROPS.boxes.some(([x0, x1, z0, z1]) => x > x0 - m && x < x1 + m && z > z0 - m && z < z1 + m);
}
function propsSpot() {
  const a = propsArea();
  for (let i = 0; i < 200; i++) {
    const x = a.x0 + PROPS.rng() * (a.x1 - a.x0), z = a.z0 + PROPS.rng() * (a.z1 - a.z0);
    if (propsClearAt(x, z)) return [x, z];
  }
  return [a.x1, a.z1];
}
function propsTick(nowSec, dt) {
  const want = propsWanted();
  if (PROPS.room && (want !== PROPS.room || LIVE3D.rooms[PROPS.room].geo !== PROPS.geo || isDark() !== PROPS.dark)) propsClear();
  if (!want) return;
  if (!PROPS.room) propsBuild(want);
  propsBoxes(nowSec, false);
  if (reduceMotion) return;   // placed, not driven
  const v = PROPS.vac, p = v.position;
  if (!propsClearAt(p.x, p.z)) { const s = propsSpot(); p.set(s[0], 0, s[1]); return; }   // a robot sat down on it: start elsewhere
  const step = PROPS.speed * Math.min(dt, 0.1), h = v.userData.heading;
  const nx = p.x + Math.sin(h) * step, nz = p.z + Math.cos(h) * step;
  if (propsClearAt(nx, nz)) { p.x = nx; p.z = nz; v.rotation.y = h; }
  else v.userData.heading = h + Math.PI * (0.5 + PROPS.rng());   // a bump: turn away and try again next frame
}
/* ---------- breaks: a cigarette in the smoking booth, a drink from the vending machine (requester, 10-19) ----------
   「セッションが少ない時には部屋の隅っこに喫煙室作って待機中の時にたまにタバコ吸うようにして。これはbot１対でもやるし複数でもやる」,
   「部屋のbotが少ない時は自販機も設置して。たまにそこに行って飲み物を飲むパターンも追加で」, placement (10-19):
   「喫煙所は左上端、自販機はウォーターサーバーの横がいいかな」.
   Where (propsPlace; built with the room's other props, so only in the one-room view of a room with PROPS.max robots or
   fewer, and never on the floor or in the building):
   - the booth: the back-left corner (the top left of the usual view), BOOTH.w by BOOTH.d, its door in the front glass.
     The one-room view keeps that corner free of desks (SEAT_SOLO.left, 30-source-live.js).
   - the water server: the back-right corner, as before; the vending machine beside it on its left, facing the front.
     A room with a back door (near the right, doorAt) keeps the door's apron clear: the two stand BACK_DOOR_APRON in
     front of the back wall, still on the right. (The server's old place in such a room, the back-left corner, is the
     booth's now.) SEAT_SOLO.right keeps the machine's customer clear of the desks.
   Looks only, like play: the server, the panel's state and the lamp still say 待機. Once a second a main robot in that
   room, idle for PLAY.idleMs or more and not at play, a nap or a bento, may go (BRK.p per kind; a second smoker joins
   one already in the booth with BRK.joinP). At most BOOTH.seats in the booth and one at the machine; none in a room
   with standing robots (as play). Anything that stops a game stops a break at once (playStopReason: an instruction,
   a call, another state, leaving, another room), and so do the props going away or the room laid out again; it walks
   back with its real lamp (playBack), or jumps to its desk when the room was laid out again. None under reduced motion
   (as play). The e2e build can shorten the times (80-dbg.js). */
const BOOTH = { w: 2.6, d: 2.0, h: 2.3, door: 1.0, seats: 2 };
// taller than a robot, as a real one is than a person (requester, 10-19: 「自販機が小さい 人よりは背が高いのが普通でしょ」);
// the robots stand about 2.1 with the antenna (the e2e measures both)
const VEND = { w: 1.2, d: 0.9, h: 2.5 };
const BACK_DOOR_APRON = 1.3;
function propsPlace(r) {
  const backDoor = !!(r.doors && r.doors.back), zb = r.z0 + (backDoor ? BACK_DOOR_APRON : 0);
  const booth = { x0: r.x0, x1: r.x0 + BOOTH.w, z0: r.z0, z1: r.z0 + BOOTH.d };
  const bx = (booth.x0 + booth.x1) / 2;
  booth.ashtray = [bx, r.z0 + 0.6];
  booth.spots = [[booth.x0 + 0.6, r.z0 + 0.95, Math.PI / 2], [booth.x1 - 0.6, r.z0 + 0.95, -Math.PI / 2]];   // facing each other over the ashtray
  booth.way = [[bx, booth.z1 + 0.7], [bx, booth.z1 - 0.4]];   // in front of the door, then just inside it
  const server = { x: r.x1 - 0.42 * PROPS.serverScale, z: zb + 0.38 * PROPS.serverScale, ry: -Math.PI / 4, half: 0.55 };   // its footprint, turned
  const vx1 = server.x - server.half - 0.1;
  const vend = { x0: vx1 - VEND.w, x1: vx1, z0: zb + 0.05, z1: zb + 0.05 + VEND.d };
  vend.cx = (vend.x0 + vend.x1) / 2;
  vend.spot = [vend.cx, vend.z1 + 0.55, Math.PI];   // in front of it, facing it
  vend.way = [[vend.cx, vend.z1 + 1.3]];              // from the front: never round its corner
  return { booth, server, vend, backDoor };
}
function signTexture(text, bg, ink, w = 256, h = 96) {
  const cv = makeCanvas(w, h), ctx = cv.getContext('2d');
  ctx.fillStyle = bg; rr(ctx, 0, 0, w, h, 14); ctx.fill();
  ctx.fillStyle = ink; ctx.font = `${Math.round(h * 0.5)}px ${FONT_DISPLAY}`; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
  ctx.fillText(text, w / 2, h / 2 + 2);
  return texFrom(cv);
}
function boothBuild(B) {
  const g = new THREE.Group(), w = B.x1 - B.x0, d = B.z1 - B.z0, h = BOOTH.h, t = 0.06, fz = B.z1, rx = B.x1, dx = (B.x0 + B.x1) / 2, half = BOOTH.door / 2;
  const metal = toon('#4a515c');
  const glass = new THREE.MeshBasicMaterial({ color: 0xbfe6f5, transparent: true, opacity: 0.2, depthWrite: false, side: THREE.DoubleSide });
  const base = new THREE.Mesh(new THREE.BoxGeometry(w, 0.04, d), toon('#9aa1ab')); base.position.set(dx, 0.02, B.z0 + d / 2); g.add(base);
  const bar = (bw, bh, bd, x, y, z) => { const m = new THREE.Mesh(new THREE.BoxGeometry(bw, bh, bd), metal); m.position.set(x, y, z); g.add(m); };
  const pane = (pw, ph, x, y, z, ry) => { const m = new THREE.Mesh(new THREE.PlaneGeometry(pw, ph), glass); m.position.set(x, y, z); m.rotation.y = ry; g.add(m); };
  for (const [x, z] of [[B.x0 + t / 2, fz - t / 2], [rx - t / 2, fz - t / 2], [rx - t / 2, B.z0 + t / 2], [dx - half, fz - t / 2], [dx + half, fz - t / 2]]) bar(t, h, t, x, h / 2, z);
  bar(w, t, t, dx, h, fz - t / 2); bar(w, t, t, dx, h, B.z0 + t / 2); bar(t, t, d, rx - t / 2, h, B.z0 + d / 2); bar(t, t, d, B.x0 + t / 2, h, B.z0 + d / 2);
  bar(BOOTH.door, t, t, dx, 1.95, fz - t / 2);   // over the door
  const lw = dx - half - B.x0, rw = rx - dx - half;
  pane(lw, h, B.x0 + lw / 2, h / 2, fz - 0.03, 0); pane(rw, h, dx + half + rw / 2, h / 2, fz - 0.03, 0); pane(BOOTH.door, h - 1.95, dx, (h + 1.95) / 2, fz - 0.03, 0);
  pane(d, h, rx - 0.03, h / 2, B.z0 + d / 2, Math.PI / 2);
  const roof = new THREE.Mesh(new THREE.PlaneGeometry(w, d), glass); roof.rotation.x = -Math.PI / 2; roof.position.set(dx, h, B.z0 + d / 2); g.add(roof);   // glass: the view from above sees in
  const sign = new THREE.Mesh(new THREE.PlaneGeometry(0.95, 0.34), new THREE.MeshBasicMaterial({ map: signTexture('喫煙室', '#2b3340', '#ffffff'), toneMapped: false }));
  sign.position.set(dx, (h + 1.95) / 2, fz + 0.01); g.add(sign);
  // the ventilation fan on the back wall inside, turning (BRK's tick turns it)
  const fan = new THREE.Group(); fan.position.set(dx, 1.85, B.z0 + 0.06); g.add(fan);
  const ring = new THREE.Mesh(new THREE.CylinderGeometry(0.3, 0.3, 0.07, 24, 1, true), toon('#d7dce3', { side: THREE.DoubleSide })); ring.rotation.x = Math.PI / 2; fan.add(ring);
  const hub = new THREE.Mesh(new THREE.CylinderGeometry(0.05, 0.05, 0.08, 12), toon('#3a3f47')); hub.rotation.x = Math.PI / 2; fan.add(hub);
  const blades = new THREE.Group(); fan.add(blades);
  for (let k = 0; k < 3; k++) { const b = new THREE.Mesh(new THREE.BoxGeometry(0.24, 0.08, 0.012), toon('#7d8794')); b.position.set(Math.cos(k * 2.094) * 0.13, Math.sin(k * 2.094) * 0.13, 0); b.rotation.z = k * 2.094; blades.add(b); }
  PROPS.fan = blades;
  // the ashtray stand between the two spots
  const [ax, az] = B.ashtray;
  const foot = new THREE.Mesh(new THREE.CylinderGeometry(0.2, 0.22, 0.03, 20), metal); foot.position.set(ax, 0.055, az); g.add(foot);
  const pole = new THREE.Mesh(new THREE.CylinderGeometry(0.035, 0.035, 0.8, 10), metal); pole.position.set(ax, 0.45, az); g.add(pole);
  const bowl = new THREE.Mesh(new THREE.CylinderGeometry(0.18, 0.13, 0.08, 20), toon('#aab3bd')); bowl.position.set(ax, 0.88, az); g.add(bowl);
  const sand = new THREE.Mesh(new THREE.CylinderGeometry(0.16, 0.16, 0.01, 20), toon('#d8cfb8')); sand.position.set(ax, 0.92, az); g.add(sand);
  // the smoke: a fixed pool of soft sprites (BRK.puffs), nothing made while it runs; grey on the light wall, pale on the dark one
  const cv = makeCanvas(64, 64), ctx = cv.getContext('2d'), grd = ctx.createRadialGradient(32, 32, 2, 32, 32, 31);
  grd.addColorStop(0, 'rgba(255,255,255,1)'); grd.addColorStop(0.55, 'rgba(255,255,255,0.8)'); grd.addColorStop(1, 'rgba(255,255,255,0)');
  ctx.fillStyle = grd; ctx.fillRect(0, 0, 64, 64);
  const puffTex = texFrom(cv);
  PROPS.smoke = [];
  for (let k = 0; k < BRK.puffs; k++) {
    const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: puffTex, color: PROPS.dark ? 0xd9dee5 : 0x8f98a3, transparent: true, opacity: 0, depthWrite: false }));
    s.visible = false; s.renderOrder = 4; g.add(s);
    PROPS.smoke.push({ s, age: 0, life: 1, size: 0.1, alpha: 0, vx: 0, vy: 0, vz: 0 });
  }
  return g;
}
function vendTexture() {
  const W = 256, H = 576, cv = makeCanvas(W, H), ctx = cv.getContext('2d');
  ctx.fillStyle = '#f6f8fb'; ctx.fillRect(0, 0, W, H);
  ctx.fillStyle = '#d8343c'; ctx.fillRect(0, 0, W, 64);
  ctx.fillStyle = '#ffffff'; ctx.font = `34px ${FONT_DISPLAY}`; ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.fillText('のみもの', W / 2, 34);
  const colors = [['#1c2440', '#b6f03c'], ['#2f7fd1', '#ffffff'], ['#e8554e', '#fff3bf'], ['#2e9e5b', '#e1f1ef'], ['#7a4a2a', '#f3e6d4'], ['#f2b632', '#3b2410']];
  for (let row = 0; row < 3; row++) {
    const y = 84 + row * 128;
    ctx.fillStyle = '#e3eaf4'; ctx.fillRect(14, y, W - 28, 92);
    for (let k = 0; k < 4; k++) {
      const [body, band] = colors[(row * 4 + k) % colors.length], x = 24 + k * 56;
      rr(ctx, x, y + 10, 40, 74, 8); ctx.fillStyle = body; ctx.fill();
      ctx.fillStyle = band; ctx.fillRect(x, y + 36, 40, 16);
      ctx.fillStyle = '#41505f'; ctx.fillRect(x + 4, y + 98, 32, 12);   // the price
      ctx.fillStyle = '#ff5a4f'; ctx.beginPath(); ctx.arc(x + 20, y + 120, 5, 0, Math.PI * 2); ctx.fill();   // the button
    }
  }
  ctx.fillStyle = '#2b3340'; ctx.fillRect(W - 62, 470, 30, 44);   // the coin slot
  ctx.fillStyle = '#cfd6df'; ctx.fillRect(W - 54, 478, 14, 28);
  return texFrom(cv);
}
function vendBuild(V) {
  const g = new THREE.Group(), cz = (V.z0 + V.z1) / 2;
  const body = new THREE.Mesh(new RoundedBoxGeometry(VEND.w, VEND.h, VEND.d, 2, 0.04), toon('#d8343c')); body.position.set(V.cx, VEND.h / 2, cz); g.add(body);
  const ph = VEND.h - 0.55, pw = Math.min(VEND.w - 0.12, ph * 256 / 576);   // the texture's shape, a red frame round it
  const panel = new THREE.Mesh(new THREE.PlaneGeometry(pw, ph), new THREE.MeshBasicMaterial({ map: vendTexture(), toneMapped: false }));
  panel.position.set(V.cx, 0.42 + ph / 2, V.z1 + 0.006); g.add(panel);   // lit: no light needed
  const slot = new THREE.Mesh(new THREE.BoxGeometry(VEND.w - 0.3, 0.2, 0.04), toon('#1f242c')); slot.position.set(V.cx, 0.22, V.z1 + 0.01); g.add(slot);
  return g;
}
const BRK_TAG_TEXT = { smoke: 'タバコ休憩', vend: '飲み物を買いに' };
const BRK = { seed: 20261021, kinds: ['smoke', 'vend'], p: { smoke: 1 / 40, vend: 1 / 40 }, joinP: 1 / 6, smokeMinSec: 20, smokeMaxSec: 40,
  buySec: 2.4, drinkMinSec: 8, drinkMaxSec: 16, restMinSec: 60, restMaxSec: 180, walkSec: 30, puffs: 10, next: 0, last: 0, rng: null, ends: [] };
const brkTagText = (R) => (R.brk ? BRK_TAG_TEXT[R.brk.kind] || '' : '');
function brkPanelText(id) { const R = robots.find((x) => x.def.id === id); return R ? brkTagText(R) : ''; }   // the robot card (50-panel.js)
const brkCap = (kind) => (kind === 'smoke' ? BOOTH.seats : 1);
const rectOf = (rm) => `${rm.x0},${rm.z0},${rm.x1},${rm.z1}`;
function brkStart(R, kind, slot, nowSec) {
  const P = PROPS.place, st = robotState[R.def.id];
  const len = kind === 'smoke' ? BRK.smokeMinSec + BRK.rng() * (BRK.smokeMaxSec - BRK.smokeMinSec)
    : BRK.buySec + BRK.drinkMinSec + BRK.rng() * (BRK.drinkMaxSec - BRK.drinkMinSec);
  const spot = kind === 'smoke' ? P.booth.spots[slot] : P.vend.spot, way = kind === 'smoke' ? P.booth.way : P.vend.way;
  R.brk = { kind, slot, room: R.def.room, rect: rectOf(PROJECT[R.def.room]), since: st.since, phase: 'going', spot, way, len, t0: 0, until: 0, walkUntil: nowSec + BRK.walkSec };
  if (R.robot.gesture) endGesture(R.robot);
  R.path = [...way.map((q) => [q[0], q[1]]), [spot[0], spot[1]]];
  R.restUntil = nowSec + BRK.walkSec + len + BRK.restMinSec + BRK.rng() * (BRK.restMaxSec - BRK.restMinSec);
}
function brkStop(R, reason, nowSec) {
  const B = R.brk;
  BRK.ends.push({ room: B.room, kind: B.kind, who: R.def.id, reason, atSec: B.t0 ? +(nowSec - B.t0).toFixed(1) : 0 });
  if (BRK.ends.length > 30) BRK.ends.shift();
  // the way points it has passed, back out the same way (out of the booth's door, round the front of the machine)
  const reached = Math.min(B.way.length, B.way.length + 1 - R.path.length);
  R.brk = null; R.robot.brk = null;
  if (!robots.includes(R) || !R.def.pos) return;
  const root = R.robot.root;
  if (reason === 'relaid') {   // its room was laid out again (back to the floor, a bigger room): a jump to its desk, as livePlan's
    root.position.x = R.def.pos[0]; root.position.z = R.def.pos[1]; R.path = []; R.jumps = (R.jumps || 0) + 1;
    return;
  }
  const out = B.way.slice(0, Math.max(0, reached)).reverse().map((q) => [q[0], q[1]]);
  const from = roomAtPoint([root.position.x, root.position.z]);
  R.playBack = true;   // walking back: the real state's lamp, no papers (as from play)
  if (R.robot.desk) R.robot.desk.visible = false;
  R.path = from && from !== R.def.room ? [...out, ...liveRoute(from, R.def.room), R.def.pos] : [...out, R.def.pos];   // never through a wall
}
function brkAt(R, dt) {
  const B = R.brk, root = R.robot.root;
  if (R.robot.desk) R.robot.desk.visible = false;
  if (B.phase === 'going') B.phase = 'at';
  // bought: it turns round to the room with the can (its back hid the can and the machine's panel from the usual view)
  const ry = B.kind === 'vend' && R.robot.brkHandKind === 'vend' ? 0 : B.spot[2];
  const turn = ((ry - root.rotation.y) % (Math.PI * 2) + Math.PI * 3) % (Math.PI * 2) - Math.PI;   // the short way round
  root.rotation.y += turn * Math.min(1, dt * 6);
  return 'playing';
}
function brkTick(nowSec, now) {
  if (!BRK.rng) BRK.rng = snackRandom(BRK.seed);
  // stop at once: every frame
  for (const R of robots) {
    const B = R.brk;
    if (!B) continue;
    const st = robotState[R.def.id] || { state: 'idle' }, rm = PROJECT[B.room];
    const reason = playStopReason(R, st, B.room, B.since) || (!rm || !rm.shown || rectOf(rm) !== B.rect ? 'relaid' : null) || (PROPS.room !== B.room ? 'props' : null)
      || (B.phase === 'going' && nowSec >= B.walkUntil ? 'walk too long' : null) || (B.t0 && nowSec >= B.until ? 'done' : null);
    if (reason) { brkStop(R, reason, nowSec); continue; }
    if (B.phase === 'at' && !B.t0) { B.t0 = nowSec; B.until = nowSec + B.len; R.robot.brk = { kind: B.kind, t0: nowSec, buySec: BRK.buySec }; }
  }
  brkSmoke(nowSec);
  if (reduceMotion || nowSec < BRK.next) return;
  BRK.next = nowSec + 1;
  const room = PROPS.room;
  if (!room || !PROPS.place || robots.some((R) => R.def.room === room && R.def.standing)) return;
  const here = robots.filter((R) => R.def.room === room);
  for (const R of here) {
    const st = robotState[R.def.id];
    if (!st || !playIdle(R, st, now) || (R.restUntil || 0) > nowSec) continue;
    for (const kind of BRK.kinds) {
      const on = here.filter((x) => x.brk && x.brk.kind === kind);
      if (on.length >= brkCap(kind)) continue;
      if (BRK.rng() >= (kind === 'smoke' && on.length ? BRK.joinP : BRK.p[kind])) continue;
      const used = new Set(on.map((x) => x.brk.slot));
      brkStart(R, kind, kind === 'smoke' ? [0, 1].find((k) => !used.has(k)) : 0, nowSec);
      break;
    }
  }
}
/* The smoke: from the cigarette's tip now and then, and out of the mouth after each puff (brkPuff); each sprite rises,
   grows and fades. Never more than BRK.puffs at once (a free sprite or none). */
const brkV = new THREE.Vector3();
function brkSmoke(nowSec) {
  const dt = Math.max(0, Math.min(0.1, nowSec - (BRK.last || nowSec)));
  BRK.last = nowSec;
  if (PROPS.fan && !reduceMotion) PROPS.fan.rotation.z += dt * 7;
  const pool = PROPS.smoke;
  if (!pool.length) return;
  for (const q of pool) {
    if (!q.s.visible) continue;
    q.age += dt;
    if (q.age >= q.life) { q.s.visible = false; continue; }
    const k = q.age / q.life;
    q.s.position.x += q.vx * dt; q.s.position.y += q.vy * dt; q.s.position.z += q.vz * dt;
    q.s.scale.setScalar(q.size * (1 + k * 1.2));
    q.s.material.opacity = q.alpha * (1 - k);
  }
  if (reduceMotion) return;
  for (const R of robots) {
    const B = R.robot.brk, hand = R.robot.brkHand;
    if (!B || B.kind !== 'smoke' || !hand || R.robot.call) continue;
    const c = (nowSec - B.t0) % BRK_PUFF_SEC, exhale = c >= 2.3 && c < 3.3;
    if (nowSec - (R.puffAt || 0) < (exhale ? 0.22 : 0.6)) continue;
    const q = pool.find((x) => !x.s.visible);
    if (!q) continue;
    R.puffAt = nowSec;
    const ry = R.robot.root.rotation.y, fw = exhale ? 0.25 : 0.03;
    if (exhale) { R.robot.head.getWorldPosition(brkV); brkV.x += Math.sin(ry) * 0.7; brkV.z += Math.cos(ry) * 0.7; brkV.y += 0.3; }   // in front of the face (HEAD.d)
    else hand.userData.tip.getWorldPosition(brkV);
    Object.assign(q, { age: 0, life: exhale ? 2.8 : 2.2, size: exhale ? 0.8 : 0.4, alpha: exhale ? 0.95 : 0.8,
      vx: Math.sin(ry) * fw + (BRK.rng() - 0.5) * 0.08, vy: 0.35, vz: Math.cos(ry) * fw + (BRK.rng() - 0.5) * 0.08 });
    q.s.position.copy(brkV); q.s.scale.setScalar(q.size); q.s.material.opacity = q.alpha; q.s.visible = true;
  }
}
/* A board press in the live office: the project board opens that project's spec board (overview), its lower
   part and the cork board the task board, a robot its card. */
function towerHit(ray) {
  ray.layers.set(TOWER.LAYER);
  const h = ray.intersectObjects(TOWER.floors.map((F) => F.box), false)[0];
  ray.layers.set(0);
  if (!h) return null;
  // The window pressed names its room (towerHover reads the same bay): the room, not the one open before (10-18).
  const F = TOWER.floors[h.object.userData.floor];
  const bay = F && h.uv ? F.bays.find((b) => h.uv.x >= b.x0 && h.uv.x <= b.x1) : null;
  return { kind: 'floor', k: h.object.userData.floor, project: bay && bay.id && PROJECT[bay.id] ? bay.id : null, title: towerHover(h) };
}
function liveHit(ray) {
  const solo = liveSolo(), rooms = Object.entries(LIVE3D.rooms).filter(([id]) => !solo || id === solo).map(([, R]) => R);
  const targets = [...rooms.flatMap((R) => [R.pb.mesh, R.kb.mesh, ...(R.tb ? [R.tb.mesh] : [])]), ...robots.filter((R) => R.robot.root.visible).map((R) => R.robot.root)];
  const hit = ray.intersectObjects(targets, true)[0];
  if (!hit) {
    // a room's floor picks the room (the floor view only)
    const f = solo ? null : ray.intersectObjects(rooms.map((R) => R.floor), false)[0];
    const id = f && Object.keys(LIVE3D.rooms).find((k) => LIVE3D.rooms[k].floor === f.object);
    return id ? { kind: 'room', project: id, title: `${PROJECT[id].name} を選ぶ` } : null;
  }
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
      if (!s.by || !robots.some((R) => R.def.id === s.by && R.robot.root.visible)) return;
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
/* One room fills most of the view (about 80 % of the narrower side, from the camera's field of view and aspect);
   everything is framed with a margin. */
function liveRoomPose(id) {
  const b = liveBounds(id === 'all' ? null : [id]) || { c: new THREE.Vector3(0, 0.4, 0), size: 12 };
  const half = THREE.MathUtils.degToRad(camera.fov) / 2, tanH = Math.tan(half) * Math.min(1, camera.aspect || 1);
  const fit = (size, share) => (size / 2) / (tanH * share);
  const dist = id === 'all' ? Math.max(22, fit(b.size, 0.92)) : Math.max(9, fit(b.size, (camera.aspect || 1) < 1 ? 0.7 : 0.86));   // one room: most of the view (less on a tall screen, where its corners reach out)
  return { p: b.c.clone().add(new THREE.Vector3(6.5, 15.5, 22.5).normalize().multiplyScalar(dist)), t: b.c };
}
/* The near weather's switch (10-18), in the building view of a live page. Off by default. Turning it on is the only
   place that asks the browser for the position — the permission dialog shows inside this click, never on opening the
   page — and the position is rounded to two decimals (about 1 km) before it leaves the page; the server rounds again
   and asks Open-Meteo itself (the page never talks to anyone but this server). Turning it off removes the position. */
const WEATHER_JA = { clear: '晴れ', cloudy: '曇り', fog: '霧', rain: '雨', snow: '雪', thunder: '雷雨' };
const WEATHER_UI = { busy: false, note: '' };
const roundCoord = (v) => Math.round(v * 100) / 100;
/* Two places show the same switch (10-18): the building view's corner, and the side panel's 設定 — the latter for every
   live page, so the weather can be turned on and its state read with fewer than seven rooms (no building view). */
function weatherPaint(towerHidden) {
  const box = document.getElementById('tower-weather'), sec = document.getElementById('sec-settings');
  if (!box) return;
  box.hidden = towerHidden;
  if (sec) sec.hidden = SOURCE.mode !== 'live';
  if (SOURCE.mode !== 'live') return;   // the demo has no server to ask, and no LIVE.slices
  const w = LIVE.slices.weather || { on: false };
  const at = typeof w.at === 'number' ? new Date(w.at).toTimeString().slice(0, 5) : '';
  const text = WEATHER_UI.note || (!w.on ? 'オフ — 外への通信はしません'
    : w.kind ? `${WEATHER_JA[w.kind] || w.kind}${typeof w.tempC === 'number' ? ` ${Math.round(w.tempC)}℃` : ''}（最後に取れた時刻 ${at}${w.stale ? '・古い値' : ''}）${w.error ? ` — 失敗: ${w.error}` : ''}`
      : w.error ? `取れていません — 失敗: ${w.error}` : '取得中…');
  for (const [b, n, hidden] of [['weather-switch', 'weather-note', towerHidden], ['weather-switch-panel', 'weather-note-panel', !sec || sec.hidden]]) {
    if (hidden) continue;
    const btn = document.getElementById(b), note = document.getElementById(n);
    btn.setAttribute('aria-checked', w.on ? 'true' : 'false');
    btn.setAttribute('aria-busy', WEATHER_UI.busy ? 'true' : 'false');
    setText(note, text);
    note.toggleAttribute('data-error', !!(WEATHER_UI.note || w.error));
  }
}
async function weatherSwitch() {
  if (WEATHER_UI.busy) return;
  const on = !(LIVE.slices.weather && LIVE.slices.weather.on);
  WEATHER_UI.busy = true; WEATHER_UI.note = on ? '位置の許可を待っています…' : '';
  floorNavSync();
  try {
    if (!on) {
      const ack = await SOURCE.setWeather({ on: false });
      WEATHER_UI.note = ack.ok ? '' : `オフにできませんでした — ${ack.error || ''}`;
      return;
    }
    if (!navigator.geolocation) { WEATHER_UI.note = 'このブラウザでは位置を取れないため、オフのままです'; return; }
    const pos = await new Promise((resolve, reject) => navigator.geolocation.getCurrentPosition(resolve, reject,
      { enableHighAccuracy: false, timeout: 20000, maximumAge: 600000 }));
    const lat = roundCoord(pos.coords.latitude), lon = roundCoord(pos.coords.longitude);   // about 1 km, before it leaves the page
    const ack = await SOURCE.setWeather({ on: true, lat, lon });
    WEATHER_UI.note = ack.ok ? '' : `オンにできませんでした — ${ack.error || ''}`;
  } catch (err) {
    const why = err && err.code === 1 ? '位置の利用が許可されませんでした' : err && err.code === 3 ? '位置を取るのに時間がかかりすぎました' : '位置を取れませんでした';
    WEATHER_UI.note = `${why}。オフのままです`;
  } finally {
    WEATHER_UI.busy = false;
    floorNavSync();
  }
}
// The panel's switch works without 3D too (no WebGL: no building, but the setting and its state are still here).
{ const btn = document.getElementById('weather-switch-panel'); if (btn) btn.addEventListener('click', () => { weatherSwitch(); }); }
/* The floor buttons (both views). Hidden while a board, the log, a zoom or a robot card covers the 3D (10-18). The
   demo has one office: its buttons show in the building only, and look at the floors there. */
function floorNavSync() {
  const nav = document.getElementById('floor-nav'), legend = document.getElementById('tower-legend');
  if (!nav) return;
  const n = LIVE.floors.length, k = SOURCE.mode === 'demo' || TOWER.on ? TOWER.look : LIVE.floor;
  const covered = wb.open || tb.open || logState.open || zoom.zoomed || !!rbState.id;
  nav.hidden = !has3D || n < 2 || covered || (SOURCE.mode === 'demo' && !TOWER.on);
  legend.hidden = nav.hidden || !TOWER.on;
  weatherPaint(!has3D || covered || !TOWER.on || SOURCE.mode !== 'live');
  if (nav.hidden) return;
  setText(document.getElementById('floor-label'), TOWER.on && SOURCE.mode === 'live' ? `全 ${n} 階` : `${k + 1}F / ${n}F`);
  const waits = LIVE.floors.map((f) => f.some((id) => LIVE.rank[id] === 0));
  const up = document.getElementById('floor-up'), down = document.getElementById('floor-down'), bld = document.getElementById('floor-building');
  const free = TOWER.on && SOURCE.mode === 'live';
  up.disabled = !free && k >= n - 1; down.disabled = !free && k <= 0;
  const above = waits.some((w, j) => w && j > k), below = waits.some((w, j) => w && j < k);
  up.toggleAttribute('data-alert', above && !free); down.toggleAttribute('data-alert', below && !free);
  bld.toggleAttribute('data-alert', (above || below) && !TOWER.on);
  up.setAttribute('aria-label', above ? '上の階へ（上の階に許可待ち）' : '上の階へ');
  down.setAttribute('aria-label', below ? '下の階へ（下の階に許可待ち）' : '下の階へ');
  bld.setAttribute('aria-pressed', TOWER.on ? 'true' : 'false');
}
/* The demo's director: once a loop, the camera beats (out to the building, up to 2F, back, down; the building at
   night), scripted coffee and meals, and a small fist pump when a permission is granted. The camera beats skip
   while someone uses the 3D view (a touch in the last 8 s) or a board / card covers it. */
const DIRECTOR = { userAt: -1e9, prevT: null, perm: {} };
function demoDirector(model, nowSec) {
  const t = model.t, prev = DIRECTOR.prevT;
  DIRECTOR.prevT = t;
  demoBuilding(t);
  if (prev === null) return;
  // a beat between the last frame and this one; across the loop's end only when time wrapped (not a jump back)
  const wrapped = prev - t > LOOP / 2;
  const crossed = (beat) => (prev <= t ? prev < beat && beat <= t : wrapped && (prev < beat || beat <= t));
  const robot = (id) => { const R = robots.find((x) => x.def.id === id); return R && R.robot; };
  const B = DEMO_BEATS, quiet = performance.now() - DIRECTOR.userAt > 8000 && !wb.open && !tb.open && !logState.open && !zoom.zoomed && !rbState.id;
  if (quiet && has3D && playing) {
    if (crossed(B.towerOut) || crossed(B.nightOut)) towerEnter();
    if (crossed(B.look2F)) towerLookAt(1);
    if (crossed(B.look1F)) towerLookAt(0);
    if (crossed(B.towerIn) || crossed(B.nightIn)) towerLeave(0);
  }
  for (const [at, id, kind] of B.snacks) if (crossed(at) && robot(id)) startGesture(robot(id), kind, nowSec);
  for (const p of model.perms) {                     // granted (in the view, by a rule or in the terminal): a fist pump
    const was = DIRECTOR.perm[p.id];
    if (was === 'pending' && p.status !== 'pending' && p.status !== 'deny' && robot(p.who)) {
      setRobotState(robot(p.who), robotState[p.who].state);   // the 3D robot still shows last frame's 許可待ち
      startGesture(robot(p.who), 'cheer', nowSec);
    }
    DIRECTOR.perm[p.id] = p.status;
  }
}
/* ---------- the building: every floor of six rooms, stacked (requester's ruling, 10-18) ----------
   Looking at a floor, the 3D is that floor's rooms in full, as before; the other floors are not drawn. Zoomed out
   (the ビル全体 button, or the wheel past the farthest distance) the building replaces them: one plain box per floor
   on its own layer, with the floor number, a window per room (lit: a robot works; yellow: one waits for permission),
   the counts and the room names on its front. Pressing a floor goes down to it. Changing floors moves the camera
   up or down into the new floor. */
/* The sky behind the building follows the local time of the machine viewing it (requester, 10-18): dawn, day, dusk,
   night. The panels, the floor buttons and the legend carry their own background, so they read at any hour. */
const SKY = { dawn: ['#8fa9d6', '#f6c49f'], day: ['#8fc4f2', '#e3f1ff'], dusk: ['#3f4486', '#f0935f'], night: ['#050c1c', '#17264a'] };
function skyPhase(date) {
  const h = date.getHours() + date.getMinutes() / 60;
  return h >= 5 && h < 7 ? 'dawn' : h >= 7 && h < 16.5 ? 'day' : h >= 16.5 && h < 19 ? 'dusk' : 'night';
}
/* The outside of the building: the season and, when turned on, the weather near this machine (requester, 10-18).
   The season comes from the viewer's date (northern hemisphere): spring cherry blossom with a few petals in the air,
   summer deep green with cicadas on the trunks (no sound), autumn red and orange leaves with a few falling, winter
   bare branches and a thin snow on the plaza and the roof. Only the trees, the plaza and the roof change; the rooms
   and the robots do not. The weather (the server's weather slice: off by default, and then nothing is asked of
   anyone) greys the sky, rains, snows, flashes or fogs over the season. Falling things are capped at OUTSIDE.max and
   stand still under reduced motion. */
const OUTSIDE = { max: 160, force: null, weatherForce: null };
function seasonOf(date) {
  const m = date.getMonth() + 1;
  return m >= 3 && m <= 5 ? 'spring' : m >= 6 && m <= 8 ? 'summer' : m >= 9 && m <= 11 ? 'autumn' : 'winter';
}
const season = () => OUTSIDE.force || seasonOf(new Date(vizNow()));
/* The weather to draw: { kind, isDay } or null (off, not read yet, too old, or the demo). */
function weatherNow() {
  if (OUTSIDE.weatherForce) return OUTSIDE.weatherForce;
  const w = SOURCE.mode === 'live' ? LIVE.slices.weather : null;
  return w && w.on && typeof w.kind === 'string' ? { kind: w.kind, isDay: w.isDay !== false } : null;
}
// How far each weather pulls the sky toward its grey (light rain under a dark cloud, a pale fog).
const SKY_GREY = { cloudy: ['#8d99a8', 0.55], rain: ['#6f7b8a', 0.7], thunder: ['#4c5563', 0.8], fog: ['#c3cad3', 0.7], snow: ['#c9d1dc', 0.55] };
function skyColors(phase, w) {
  const base = SKY[phase];
  const g = w && SKY_GREY[w.kind];
  if (!g) return base;
  const mix = (hex) => '#' + new THREE.Color(hex).lerp(new THREE.Color(g[0]), phase === 'night' ? g[1] * 0.4 : g[1]).getHexString();
  return [mix(base[0]), mix(base[1])];
}
function skySync() {
  if (!TOWER.on && TOWER.flash) { TOWER.flash = false; sceneEl.style.filter = ''; }   // left the building mid-flash
  const w = weatherNow();
  let phase = TOWER.on || SOURCE.mode === 'demo' ? skyPhase(new Date(vizNow())) : '';   // the demo's office has its clock's sky too
  if (phase && w) phase = !w.isDay ? 'night' : phase === 'night' ? 'day' : phase;   // the place's own day and night
  const key = phase ? `${phase}:${w ? w.kind : ''}` : '';
  const fog = TOWER.on && w && w.kind === 'fog';
  if (!!scene.fog !== !!fog) scene.fog = fog ? new THREE.Fog(new THREE.Color(SKY_GREY.fog[0]), 18, 70) : null;
  if ((sceneEl.dataset.sky || '') === key) return;
  sceneEl.dataset.sky = key;
  const c = phase ? skyColors(phase, w) : null;
  sceneEl.style.background = c ? `linear-gradient(180deg, ${c[0]}, ${c[1]})` : '';
}
const outsideKey = () => { const w = weatherNow(); return `${season()}:${w ? w.kind : ''}`; };
const TOWER = { on: false, look: 0, sign: null, group: null, floors: [], sig: '', theme: null, W: 16, D: 9, H: 3, SLAB: 0.28, LOBBY: 1.1, LAYER: 1, pulse: 1,
  lights: null, actors: null, bayColor: [] };
const towerBase = (k) => TOWER.LOBBY + k * (TOWER.H + TOWER.SLAB);          // the slab under floor k
const towerY = (k) => towerBase(k) + TOWER.SLAB + TOWER.H / 2;              // the middle of floor k
// The page's colours (the side panel's state badges: 作業中 = --ok, 許可待ち = --warn, 待機 = --chip), per theme.
function towerPalette() {
  const dark = isDark(), t = (name, light, darkV) => readToken(name, dark ? darkV : light);
  return {
    dark, ink: t('--ink', '#13233a', '#e4ecf8'), soft: t('--ink-soft', '#4b5c76', '#9fb1cb'), panel: t('--panel', '#fbfcfe', '#111f34'),
    line: t('--line', '#cfd9e7', '#24395a'), chip: t('--chip', '#e3eaf4', '#182c47'), ok: t('--ok', '#1d8f4e', '#5ad893'),
    okBg: t('--ok-bg', '#dcf3e5', '#123a2a'), warn: t('--warn', '#9a6200', '#ffc65c'), warnBg: t('--warn-bg', '#fff0d1', '#3a2b0c'),
    frame: dark ? '#4a5f80' : '#5d6f88', concrete: dark ? '#2a3546' : '#dfe5ee', glass: dark ? '#1b3150' : '#9fbbd9',
    // the light in a window: on (warm), off (a dark room), none (no room at all)
    on: '#ffd585', off: dark ? '#152238' : '#33445e', none: '#05070b',
  };
}
function towerFloorText(k) {
  const ids = LIVE.floors[k] || [];
  let working = 0, waiting = 0, idle = 0;
  for (const d of ROBOT_DEFS) {
    if (!ids.includes(roomOfDef(d)) || LIVE.leaving[d.id]) continue;
    const st = (robotState[d.id] || {}).state;
    if (st === 'waiting') waiting += 1; else if (st && st !== 'idle' && st !== 'done') working += 1; else idle += 1;
  }
  waiting = Math.max(waiting, PERMS_LIVE.filter((p) => p.status === 'pending' && DEF[p.who] && ids.includes(DEF[p.who].room)).length);
  return { ids, working, waiting, idle };
}
const TOWER_STATE = ['waiting', 'working', 'idle', 'idle'];   // rank 0..3 → what a window shows
// A working room where nobody does more than think shows "thinking" (lit, its own badge and pose).
const roomThinks = (id) => { const st = ROBOT_DEFS.filter((d) => roomOfDef(d) === id && !LIVE.leaving[d.id]).map((d) => (robotState[d.id] || {}).state);
  return st.includes('thinking') && !st.some((x) => x && !['idle', 'done', 'thinking', 'waiting'].includes(x)); };
const towerState = (id) => { if (!id) return 'empty'; const t = TOWER_STATE[LIVE.rank[id]] || 'idle'; return t === 'working' && roomThinks(id) ? 'thinking' : t; };
const towerName = (id) => String(TOWER_NAMES[id] || (PROJECT[id] && PROJECT[id].name) || id || '').replace(/\/+$/, '');
const roomOfDef = (d) => d.room || projectOfRobot(d.id);   // the live defs carry a room; the demo's come from their session
/* A name in up to two lines that fit maxW, broken after '-', '_' or a space when it can be (not "tea-finder-ag / ent");
   a part longer than a line breaks where it must; a name longer than two lines ends with '…'. */
function towerLines(ctx, text, maxW) {
  const parts = text.match(/[^-_\s]*[-_\s]|[^-_\s]+$/g) || [text];
  const lines = [''];
  for (const part of parts) {
    const cur = lines[lines.length - 1];
    if (ctx.measureText(cur + part).width <= maxW) { lines[lines.length - 1] = cur + part; continue; }
    if (cur) lines.push('');
    for (const ch of [...part]) {                         // a part wider than a line: by character
      const now = lines[lines.length - 1];
      if (ctx.measureText(now + ch).width > maxW && now) lines.push(ch); else lines[lines.length - 1] = now + ch;
    }
  }
  if (lines.length <= 2) return lines.filter(Boolean);
  let last = lines[1];
  lines.cut = true;
  while (last && ctx.measureText(last + '…').width > maxW) last = last.slice(0, -1);
  const out = [lines[0], last + '…'];
  out.cut = true;
  return out;
}
/* The largest of 30 / 26 / 22 px at which the name fits two lines uncut (only the smallest may cut it). */
function towerNameFit(ctx, text, maxW) {
  for (const size of [30, 26, 22]) {
    ctx.font = `700 ${size}px ${FONT_BODY}`;
    const lines = towerLines(ctx, text, maxW);
    if (!lines.cut || size === 22) return { size, lines };
  }
  return null;
}
/* A floor's front, 2048 × 384: the floor number | six bays (a badge band, the window — cut out, the light and the
   robots behind it show through — and the name band) | the counts. Nothing shares a band, so nothing overlaps. */
const FACADE = { W: 2048, H: 384, NUM: 210, STATS: 330, WIN_TOP: 22, BADGE: 52, WIN_BOTTOM: 246, NAME_TOP: 262 };
function towerBays() {
  const bw = (FACADE.W - FACADE.NUM - FACADE.STATS) / ROOM_MAX;
  return Array.from({ length: ROOM_MAX }, (_, i) => ({ x: FACADE.NUM + i * bw + 10, w: bw - 20 }));
}
function towerFacade(F, k, P) {
  const { ids, working, waiting, idle } = towerFloorText(k);
  const ctx = F.canvas.getContext('2d'), { W, H, NUM, STATS, WIN_TOP, BADGE, WIN_BOTTOM, NAME_TOP } = FACADE;
  ctx.textBaseline = 'alphabetic';
  ctx.clearRect(0, 0, W, H);
  ctx.fillStyle = P.panel; ctx.fillRect(0, 0, W, H);
  ctx.fillStyle = P.ink; ctx.beginPath(); ctx.roundRect(28, 120, NUM - 56, 140, 24); ctx.fill();
  ctx.fillStyle = P.panel; ctx.font = `78px ${FONT_DISPLAY}`; ctx.textAlign = 'center'; ctx.fillText(`${k + 1}F`, NUM / 2, 220);
  F.bays = [];
  towerBays().forEach(({ x, w }, i) => {
    const id = ids[i], state = towerState(id), gy = WIN_TOP + BADGE;
    // the badge band: the state in words and a symbol (not only a colour)
    ctx.fillStyle = P.frame; ctx.fillRect(x, WIN_TOP, w, BADGE);
    const badge = { working: ['▶ 作業中', P.ok, P.okBg], thinking: ['… 考え中', P.ok, P.okBg], waiting: ['! 許可待ち', P.warn, P.warnBg], idle: ['● 待機（消灯）', P.soft, P.chip], empty: ['空き', P.soft, P.panel] }[state];
    ctx.font = `700 26px ${FONT_BODY}`;
    const bwid = ctx.measureText(badge[0]).width + 26;
    ctx.fillStyle = badge[2]; ctx.beginPath(); ctx.roundRect(x + 10, WIN_TOP + 8, bwid, 36, 18); ctx.fill();
    if (state === 'empty') { ctx.setLineDash([8, 6]); ctx.strokeStyle = P.soft; ctx.lineWidth = 2; ctx.stroke(); ctx.setLineDash([]); }
    ctx.fillStyle = badge[1]; ctx.textAlign = 'left'; ctx.fillText(badge[0], x + 23, WIN_TOP + 35);
    // the window: cut out of the front
    ctx.clearRect(x, gy, w, WIN_BOTTOM - gy);
    ctx.strokeStyle = P.frame; ctx.lineWidth = 6; ctx.strokeRect(x, WIN_TOP, w, WIN_BOTTOM - WIN_TOP);
    ctx.lineWidth = 4; ctx.beginPath(); ctx.moveTo(x + w / 2, gy); ctx.lineTo(x + w / 2, gy + 30); ctx.stroke();
    if (state === 'empty') {                         // no room: a dashed frame across the dark glass
      ctx.setLineDash([14, 10]); ctx.strokeStyle = P.soft; ctx.lineWidth = 4; ctx.strokeRect(x + 10, gy + 10, w - 20, WIN_BOTTOM - gy - 20); ctx.setLineDash([]);
    }
    if (state === 'waiting') { ctx.strokeStyle = P.warn; ctx.lineWidth = 12; ctx.globalAlpha = 0.5 + 0.5 * TOWER.pulse; ctx.strokeRect(x + 6, WIN_TOP + 6, w - 12, WIN_BOTTOM - WIN_TOP - 12); ctx.globalAlpha = 1; }
    const play = id && SOURCE.mode === 'live' ? playRoomText(id) : '';   // a game in the room (2.3.3): its name at the window's foot
    if (play) {
      let size = 32; ctx.font = `700 ${size}px ${FONT_BODY}`;
      while (ctx.measureText(play).width > w - 40 && size > 14) { size -= 2; ctx.font = `700 ${size}px ${FONT_BODY}`; }
      const pw = ctx.measureText(play).width + 28;
      ctx.fillStyle = P.panel; ctx.beginPath(); ctx.roundRect(x + (w - pw) / 2, WIN_BOTTOM - 58, pw, size + 22, 12); ctx.fill();
      ctx.strokeStyle = P.ink; ctx.lineWidth = 3; ctx.stroke();
      ctx.fillStyle = P.ink; ctx.textAlign = 'center'; ctx.fillText(play, x + w / 2, WIN_BOTTOM - 58 + size + 8);
    }
    // the name band
    ctx.fillStyle = id ? P.ink : P.soft; ctx.textAlign = 'center';
    const fit = id ? towerNameFit(ctx, towerName(id), w - 8) : (ctx.font = `700 30px ${FONT_BODY}`, { size: 30, lines: ['—'] });
    fit.lines.forEach((ln, j) => ctx.fillText(ln, x + w / 2, NAME_TOP + 30 + j * (fit.size + 10)));
    F.bays.push({ x0: x / W, x1: (x + w) / W, gy0: gy / H, gy1: WIN_BOTTOM / H, id, state, play });
  });
  const sx = W - STATS + 18;
  ctx.fillStyle = P.chip; ctx.beginPath(); ctx.roundRect(sx - 8, 22, STATS - 36, H - 44, 20); ctx.fill();
  const row = (y, icon, label, n, fg, bg) => {
    ctx.fillStyle = bg; ctx.beginPath(); ctx.arc(sx + 34, y - 12, 24, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = fg; ctx.font = `700 30px ${FONT_BODY}`; ctx.textAlign = 'center'; ctx.fillText(icon, sx + 34, y - 1);
    ctx.textAlign = 'left'; ctx.fillStyle = P.ink; ctx.fillText(label, sx + 70, y);
    ctx.font = `700 40px ${FONT_MONO}`; ctx.textAlign = 'right'; ctx.fillText(String(n), W - 48, y + 2);
  };
  row(110, '▶', '作業中', working, P.ok, P.okBg);
  row(206, '!', '許可待ち', waiting, P.warn, P.warnBg);
  row(302, '●', '待機', idle, P.soft, P.panel);
  F.tex.needsUpdate = true;
}
/* The office robots seen through the windows: one sprite per pose (a desk, a walk in two steps, pointing at a
   board, a raised hand, a shadow in a dark room). How many and where is a picture of an office, not a count. */
function towerSprite(pose, P) {
  const c = makeCanvas(160, 200), ctx = c.getContext('2d');
  const ink = pose === 'shadow' ? (P.dark ? 'rgba(140, 160, 192, 0.55)' : 'rgba(170, 186, 210, 0.6)') : '#2b2f3a';
  const band = pose === 'shadow' ? ink : '#d62839';
  const head = (x, y) => { ctx.fillStyle = ink; ctx.beginPath(); ctx.roundRect(x - 26, y - 22, 52, 44, 12); ctx.fill(); ctx.fillRect(x - 2, y - 38, 4, 16); ctx.beginPath(); ctx.arc(x, y - 40, 6, 0, Math.PI * 2); ctx.fill(); ctx.fillStyle = band; ctx.fillRect(x - 26, y - 10, 52, 7); };
  const limb = (x1, y1, x2, y2, wdt = 12) => { ctx.strokeStyle = ink; ctx.lineWidth = wdt; ctx.lineCap = 'round'; ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke(); };
  const torso = (x, y, h = 56) => { ctx.fillStyle = ink; ctx.beginPath(); ctx.roundRect(x - 22, y, 44, h, 10); ctx.fill(); };
  if (pose === 'type' || pose === 'shadow') {          // at a desk, side on, hands on the keyboard
    head(62, 74); torso(62, 98, 50); limb(70, 112, 112, 124);
    ctx.fillStyle = ink; ctx.fillRect(40, 146, 46, 10); limb(48, 156, 48, 196, 10); limb(76, 156, 76, 196, 10);
    ctx.fillStyle = pose === 'shadow' ? ink : '#6b4f33'; ctx.fillRect(96, 126, 64, 10); ctx.fillRect(146, 136, 8, 64);
    if (pose === 'type') { ctx.fillStyle = '#9ad1ff'; ctx.fillRect(118, 96, 30, 26); }
  } else if (pose === 'walkA' || pose === 'walkB') {
    const s = pose === 'walkA' ? 1 : -1;
    head(80, 52); torso(80, 76);
    limb(72, 90, 72 - 16 * s, 126); limb(88, 90, 88 + 16 * s, 126);
    limb(72, 132, 72 - 18 * s, 194); limb(88, 132, 88 + 18 * s, 194);
  } else if (pose === 'point') {                       // at a board, one arm out
    ctx.fillStyle = '#f4f6fa'; ctx.fillRect(100, 40, 58, 70); ctx.strokeStyle = '#6b4f33'; ctx.lineWidth = 4; ctx.strokeRect(100, 40, 58, 70);
    ctx.fillStyle = '#7aa2d6'; ctx.fillRect(108, 52, 40, 6); ctx.fillRect(108, 66, 30, 6); ctx.fillRect(108, 80, 36, 6);
    head(56, 60); torso(56, 84); limb(66, 98, 104, 70); limb(48, 98, 44, 136);
    limb(48, 140, 46, 194); limb(64, 140, 66, 194);
  } else if (pose === 'think') {                       // standing, a hand to the chin, a … above
    head(70, 70); torso(70, 94); limb(80, 108, 82, 76); limb(60, 108, 70, 128);
    limb(62, 150, 60, 194); limb(78, 150, 80, 194);
    ctx.fillStyle = '#ffffff'; ctx.beginPath(); ctx.ellipse(120, 26, 30, 18, 0, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = '#2f6fd8'; for (let i = 0; i < 3; i++) { ctx.beginPath(); ctx.arc(106 + i * 14, 26, 4.5, 0, Math.PI * 2); ctx.fill(); }
  } else {                                             // a raised hand, looking up
    head(80, 60); torso(80, 84); limb(92, 96, 112, 30); limb(68, 96, 60, 136);
    limb(72, 140, 70, 194); limb(88, 140, 90, 194);
    ctx.fillStyle = '#ffc65c'; ctx.beginPath(); ctx.arc(126, 22, 16, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = '#2b1d00'; ctx.font = `700 24px ${FONT_BODY}`; ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.fillText('!', 126, 23);
  }
  return texFrom(c);
}
const TOWER_POSES = ['type', 'walkA', 'walkB', 'point', 'raise', 'think', 'shadow'];
function towerBuild() {
  const n = LIVE.floors.length, dark = isDark();
  const outside = outsideKey();
  if (TOWER.group && TOWER.floors.length === n && TOWER.theme === dark && TOWER.outside === outside) return;
  if (TOWER.group) { scene.remove(TOWER.group); disposeTree(TOWER.group); }
  const P = towerPalette(), L = TOWER.LAYER, { W, D, H, SLAB, LOBBY } = TOWER;
  TOWER.group = new THREE.Group(); TOWER.floors = []; TOWER.sig = ''; TOWER.theme = dark; TOWER.bayColor = []; TOWER.outside = outside;
  const put = (mesh) => { mesh.layers.set(L); TOWER.group.add(mesh); return mesh; };
  for (const o of scene.children) if (o.isLight) o.layers.enable(L);
  const top = towerBase(n), front = D / 2;
  const body = put(new THREE.Mesh(new THREE.BoxGeometry(W - 0.1, top - LOBBY, D - 0.1), toon(P.glass)));
  body.position.set(0, LOBBY + (top - LOBBY) / 2, 0);
  const m = new THREE.Matrix4();
  const slabs = put(new THREE.InstancedMesh(new THREE.BoxGeometry(W + 0.5, SLAB, D + 0.5), toon(P.concrete), n + 1));
  for (let k = 0; k <= n; k++) { m.makeTranslation(0, towerBase(k) + SLAB / 2, 0); slabs.setMatrixAt(k, m); }
  // the lights behind every window: one instanced quad each, coloured per window (on / off / no room)
  const glow = makeCanvas(4, 64), gctx = glow.getContext('2d'), gg = gctx.createLinearGradient(0, 0, 0, 64);
  gg.addColorStop(0, '#ffffff'); gg.addColorStop(1, '#b8bcc4'); gctx.fillStyle = gg; gctx.fillRect(0, 0, 4, 64);
  TOWER.lights = put(new THREE.InstancedMesh(new THREE.PlaneGeometry(1, 1), new THREE.MeshBasicMaterial({ map: texFrom(glow), toneMapped: false }), n * ROOM_MAX));
  TOWER.lights.renderOrder = 1;
  const bays = towerBays(), off = new THREE.Color(P.off);
  for (let k = 0; k < n; k++) bays.forEach((b, i) => {
    const x0 = (b.x / FACADE.W - 0.5) * W, x1 = ((b.x + b.w) / FACADE.W - 0.5) * W;
    const yTop = towerY(k) + H / 2 - ((FACADE.WIN_TOP + FACADE.BADGE) / FACADE.H) * H, yBot = towerY(k) + H / 2 - (FACADE.WIN_BOTTOM / FACADE.H) * H;
    m.compose(new THREE.Vector3((x0 + x1) / 2, (yTop + yBot) / 2, front + 0.004), new THREE.Quaternion(), new THREE.Vector3(x1 - x0, yTop - yBot, 1));
    TOWER.lights.setMatrixAt(k * ROOM_MAX + i, m);
    TOWER.lights.setColorAt(k * ROOM_MAX + i, off);
    TOWER.bayColor.push({ x0, x1, yBot, yTop, c: off.clone() });
  });
  // the robots in the windows: one instanced mesh per pose
  TOWER.actors = {};
  for (const pose of TOWER_POSES) {
    const mesh = put(new THREE.InstancedMesh(new THREE.PlaneGeometry(0.5, 0.62), new THREE.MeshBasicMaterial({ map: towerSprite(pose, P), transparent: true, depthWrite: false, toneMapped: false, side: THREE.DoubleSide /* flipped to face left */ }), n * ROOM_MAX * 3));
    mesh.renderOrder = 2; mesh.count = 0; mesh.frustumCulled = false;
    TOWER.actors[pose] = mesh;
  }
  // every floor's front over them: frames, badges, names, counts; the windows cut out
  for (let k = 0; k < n; k++) {
    const canvas = makeCanvas(FACADE.W, FACADE.H), tex = texFrom(canvas);
    const face = put(new THREE.Mesh(new THREE.PlaneGeometry(W, H), new THREE.MeshBasicMaterial({ map: tex, transparent: true, toneMapped: false })));
    face.position.set(0, towerY(k), front + 0.012); face.userData.floor = k; face.renderOrder = 3;
    TOWER.floors.push({ box: face, canvas, tex, bays: [] });
  }
  // the lobby with its entrance, the roof (parapet, plant, the JsonUI sign), the plaza with a shadow and trees
  const lobby = put(new THREE.Mesh(new THREE.BoxGeometry(W - 0.6, LOBBY, D - 0.6), toon(P.concrete)));
  lobby.position.set(0, LOBBY / 2, 0);
  const doorC = makeCanvas(1024, 160), dctx = doorC.getContext('2d');
  dctx.fillStyle = P.concrete; dctx.fillRect(0, 0, 1024, 160);
  dctx.fillStyle = P.on; dctx.fillRect(352, 20, 320, 140); dctx.strokeStyle = P.frame; dctx.lineWidth = 8; dctx.strokeRect(352, 20, 320, 140);
  dctx.beginPath(); dctx.moveTo(512, 20); dctx.lineTo(512, 160); dctx.stroke();
  const door = put(new THREE.Mesh(new THREE.PlaneGeometry(W - 0.6, LOBBY), new THREE.MeshBasicMaterial({ map: texFrom(doorC), toneMapped: false })));
  door.position.set(0, LOBBY / 2, (D - 0.6) / 2 + 0.01);
  const canopy = put(new THREE.Mesh(new THREE.BoxGeometry(4.2, 0.12, 1.4), toon(P.frame)));
  canopy.position.set(0, LOBBY + 0.02, front + 0.55);
  const parapet = put(new THREE.Mesh(new THREE.BoxGeometry(W + 0.5, 0.5, D + 0.5), toon(P.concrete)));
  parapet.position.set(0, top + SLAB + 0.25, 0);
  const plant = put(new THREE.Mesh(new THREE.BoxGeometry(3.2, 0.9, 2.4), toon(P.frame)));
  plant.position.set(-W / 2 + 2.6, top + SLAB + 0.95, -D / 2 + 2);
  const signC = makeCanvas(1024, 256), sctx = signC.getContext('2d');
  sctx.fillStyle = P.ink; sctx.beginPath(); sctx.roundRect(8, 8, 1008, 240, 40); sctx.fill();
  sctx.fillStyle = P.panel; sctx.font = `150px ${FONT_DISPLAY}`; sctx.textAlign = 'center'; sctx.textBaseline = 'middle'; sctx.fillText('JsonUI', 512, 136);
  const sign = put(new THREE.Mesh(new THREE.PlaneGeometry(5.2, 1.3), new THREE.MeshBasicMaterial({ map: texFrom(signC), toneMapped: false, side: THREE.DoubleSide })));
  sign.position.set(1.6, top + SLAB + 1.4, front - 0.4);
  TOWER.sign = sign.material;
  // the outside: the season, with the weather over it (OUTSIDE above)
  const sea = season(), w = weatherNow(), snowy = sea === 'winter' || (w && w.kind === 'snow'), wet = w && (w.kind === 'rain' || w.kind === 'thunder');
  const ground = snowy ? (dark ? '#c3ccd8' : '#f1f5fa') : wet ? (dark ? '#151d2a' : '#b4bfcd') : (dark ? '#1c2636' : '#cfd8e4');
  const plaza = put(new THREE.Mesh(new THREE.BoxGeometry(W + 9, 0.2, D + 9), toon(ground)));
  plaza.position.set(0, -0.1, 0); plaza.userData.outside = 'plaza';
  const shadow = put(new THREE.Mesh(new THREE.PlaneGeometry(W + 3, D + 3), new THREE.MeshBasicMaterial({ color: 0x000000, transparent: true, opacity: dark ? 0.35 : 0.14, depthWrite: false })));
  shadow.rotation.x = -Math.PI / 2; shadow.position.set(0.8, 0.01, 0.6);
  if (snowy) {                                        // a thin snow on the roof, inside the parapet
    const roofSnow = put(new THREE.Mesh(new THREE.BoxGeometry(W + 0.4, 0.06, D + 0.4), toon(dark ? '#d6dde8' : '#ffffff')));
    roofSnow.position.set(0, top + SLAB + 0.53, 0); roofSnow.userData.outside = 'roofSnow';
  }
  const spots = [[-W / 2 - 2.2, front + 2.2], [W / 2 + 2.2, front + 2.2], [-W / 2 - 2.6, -D / 2 + 0.5], [W / 2 + 2.6, -D / 2 + 0.5], [-5.2, front + 3.4], [5.2, front + 3.4]];
  const trunks = put(new THREE.InstancedMesh(new THREE.CylinderGeometry(0.12, 0.16, 0.9, 6), toon('#7a5a3c'), spots.length));
  spots.forEach(([x, z], i) => { m.makeTranslation(x, 0.45, z); trunks.setMatrixAt(i, m); });
  const CROWN = { spring: ['#f6bfd0', '#b98597'], summer: ['#2f8a4e', '#2a6643'], autumn: ['#de7a2e', '#a95a2a'] };
  if (sea === 'winter') {                             // bare: three branches each, a little snow on top
    const branches = put(new THREE.InstancedMesh(new THREE.CylinderGeometry(0.035, 0.06, 1.0, 5), toon('#6b4e33'), spots.length * 3));
    branches.userData.outside = 'branches';
    const q = new THREE.Quaternion(), e = new THREE.Euler(), one = new THREE.Vector3(1, 1, 1);
    spots.forEach(([x, z], i) => [-0.5, 0, 0.55].forEach((tilt, j) => {
      e.set(0, j * 2.1 + i, tilt); q.setFromEuler(e); m.compose(new THREE.Vector3(x + tilt * 0.4, 1.3, z), q, one); branches.setMatrixAt(i * 3 + j, m);
    }));
  } else {
    const crowns = put(new THREE.InstancedMesh(new THREE.ConeGeometry(0.85, 1.9, 8), toon('#ffffff'), spots.length));
    crowns.userData.outside = 'crowns';
    const autumn2 = new THREE.Color(dark ? '#8c3424' : '#c8452f');
    spots.forEach(([x, z], i) => {
      m.makeTranslation(x, 1.7, z); crowns.setMatrixAt(i, m);
      crowns.setColorAt(i, sea === 'autumn' && i % 2 ? autumn2 : new THREE.Color(CROWN[sea][dark ? 1 : 0]));
    });
    if (sea === 'summer') {                           // a cicada on each trunk, facing out
      const cicadas = put(new THREE.InstancedMesh(new THREE.BoxGeometry(0.1, 0.15, 0.06), toon('#3d2f1c'), spots.length));
      cicadas.userData.outside = 'cicadas';
      spots.forEach(([x, z], i) => { m.makeTranslation(x, 0.62 + (i % 3) * 0.08, z + 0.16); cicadas.setMatrixAt(i, m); });
    }
  }
  // falling things: the weather's (rain, snow) over the season's (petals, leaves); none in a summer or winter calm
  const fall = wet ? 'rain' : w && w.kind === 'snow' ? 'snow' : sea === 'spring' ? 'petal' : sea === 'autumn' ? 'leaf' : null;
  TOWER.fall = null;
  if (fall) {
    const N = Math.min(OUTSIDE.max, { rain: 160, snow: 120, petal: 50, leaf: 40 }[fall]);
    const geo = fall === 'rain' ? new THREE.PlaneGeometry(0.025, 0.42) : new THREE.PlaneGeometry(0.13, 0.1);
    const color = { rain: dark ? '#7f93ad' : '#7d8fa6', snow: '#ffffff', petal: '#ffc2d3', leaf: '#d96a2a' }[fall];
    const mesh = put(new THREE.InstancedMesh(geo, new THREE.MeshBasicMaterial({ color, side: THREE.DoubleSide, transparent: true, opacity: fall === 'rain' ? 0.7 : 0.95, depthWrite: false }), N));
    mesh.userData.outside = fall;
    const rnd = snackRandom(20261020), span = [W / 2 + 6, top + 4, D / 2 + 6];
    const pos = new Float32Array(N * 3);
    for (let i = 0; i < N; i++) { pos[i * 3] = (rnd() * 2 - 1) * span[0]; pos[i * 3 + 1] = rnd() * span[1]; pos[i * 3 + 2] = (rnd() * 2 - 1) * span[2]; }
    TOWER.fall = { kind: fall, mesh, pos, span, speed: { rain: 9, snow: 0.9, petal: 0.7, leaf: 1.1 }[fall], n: N };
    fallPlace(0);
  }
  scene.add(TOWER.group);
}
/* The falling things, placed for time t (still under reduced motion: where they were made). */
function fallPlace(dt, t = 0) {
  const F = TOWER.fall;
  if (!F) return;
  const { m, q, p, s } = towerTmp, e = new THREE.Euler();
  for (let i = 0; i < F.n; i++) {
    const k = i * 3;
    if (dt > 0) {
      F.pos[k + 1] -= F.speed * dt * (0.8 + (i % 5) * 0.1);
      if (F.kind !== 'rain') F.pos[k] += Math.sin(t * 0.9 + i) * 0.4 * dt;
      if (F.pos[k + 1] < 0) F.pos[k + 1] += F.span[1];
    }
    e.set(F.kind === 'rain' ? 0 : t * 1.3 + i, F.kind === 'rain' ? 0 : i, F.kind === 'rain' ? 0.15 : t + i * 0.7);
    q.setFromEuler(e); p.set(F.pos[k], F.pos[k + 1], F.pos[k + 2]); s.set(1, 1, 1);
    m.compose(p, q, s); F.mesh.setMatrixAt(i, m);
  }
  F.mesh.instanceMatrix.needsUpdate = true;
}
function towerSync(now = performance.now()) {
  towerBuild();
  const waits = LIVE.floors.some((f) => f.some((id) => LIVE.rank[id] === 0));
  const pulse = waits && !reduceMotion ? Math.round((0.5 + 0.5 * Math.sin(now / 160)) * 4) / 4 : 1;   // a waiting window's frame
  const sig = JSON.stringify([LIVE.floors, LIVE.rank, TOWER.floors.map((F, k) => towerFloorText(k)).map((t) => [t.working, t.waiting, t.idle]),
    SOURCE.mode === 'live' ? PLAY.list.map((G) => [G.room, G.kind, !!G.t0]) : []]);   // a game's name on its window (2.3.3)
  if (sig === TOWER.sig && pulse === TOWER.pulse) return;
  const P = towerPalette(), all = sig !== TOWER.sig;
  TOWER.sig = sig; TOWER.pulse = pulse;
  // A pulse alone redraws only the floors with a waiting window (a whole front is a 2048 × 384 upload).
  TOWER.floors.forEach((F, k) => { if (all || (LIVE.floors[k] || []).some((id) => LIVE.rank[id] === 0)) towerFacade(F, k, P); });
}
/* Every frame in the building: the lights fade toward on / off / none (instant under reduced motion), and the
   robots move — at their desks, walking across, pointing at a board where the room works; a raised hand where it
   waits for permission; a still shadow in a room whose lights are off; nobody where there is no room. */
const towerTmp = { m: new THREE.Matrix4(), q: new THREE.Quaternion(), p: new THREE.Vector3(), s: new THREE.Vector3(1, 1, 1), c: new THREE.Color() };
function towerAnimate(t, dt) {
  if (!TOWER.lights || !TOWER.actors) return;
  const P = towerPalette(), want = { working: P.on, thinking: P.on, waiting: P.on, idle: P.off, empty: P.none };
  const k = reduceMotion ? 1 : Math.min(1, dt * 4);
  const counts = Object.fromEntries(TOWER_POSES.map((p) => [p, 0]));
  const { m, q, p, s, c } = towerTmp;
  const place = (pose, x, y, flip = 1, tilt = 0) => {
    const mesh = TOWER.actors[pose];
    q.setFromAxisAngle(new THREE.Vector3(0, 0, 1), tilt); p.set(x, y + 0.31, (TOWER.D / 2) + 0.008); s.set(flip, 1, 1);
    m.compose(p, q, s); mesh.setMatrixAt(counts[pose]++, m);
  };
  const still = reduceMotion;
  TOWER.floors.forEach((F, fk) => F.bays.forEach((bay, i) => {
    const B = TOWER.bayColor[fk * ROOM_MAX + i];
    if (!B) return;
    B.c.lerp(c.set(want[bay.state]), k);
    TOWER.lights.setColorAt(fk * ROOM_MAX + i, B.c);
    const w = B.x1 - B.x0, x = (f) => B.x0 + w * f, seed = fk * 7 + i * 3;
    if (bay.state === 'working') {
      place('type', x(0.22), B.yBot + (still ? 0 : Math.abs(Math.sin(t * 9 + seed)) * 0.015));
      const ph = still ? 0.25 : ((t / 6 + seed * 0.13) % 1);
      const fwd = ph < 0.5, f = fwd ? ph * 2 : 2 - ph * 2;
      place(still || Math.floor(t * 4 + seed) % 2 ? 'walkA' : 'walkB', x(0.38 + f * 0.36), B.yBot, fwd ? 1 : -1);
      place('point', x(0.86), B.yBot, -1, still ? 0 : Math.sin(t * 1.4 + seed) * 0.04);
    } else if (bay.state === 'thinking') {          // hands to chins, a … over one of them
      place('think', x(0.35), B.yBot, 1, still ? 0 : Math.sin(t * 0.9 + seed) * 0.05); place('type', x(0.72), B.yBot, -1);
    } else if (bay.state === 'waiting') {
      place('raise', x(0.55), B.yBot + (still ? 0 : Math.abs(Math.sin(t * 3 + seed)) * 0.05));
      place('type', x(0.2), B.yBot);
    } else if (bay.state === 'idle') {
      place('shadow', x(0.3), B.yBot); place('shadow', x(0.72), B.yBot, -1);
    }
  }));
  TOWER.lights.instanceColor.needsUpdate = true;
  if (TOWER.sign) {                                  // the roof's sign lights up at night, a slow glow (steady under reduced motion)
    const night = skyPhase(new Date(vizNow())) === 'night', glow = reduceMotion ? 1 : 0.6 + 0.4 * Math.abs(Math.sin(t * 1.4));
    TOWER.sign.color.set(night ? c.set('#ffffff').lerp(new THREE.Color('#ffd76a'), glow) : c.set('#ffffff'));
  }
  for (const pose of TOWER_POSES) { const mesh = TOWER.actors[pose]; mesh.count = counts[pose]; mesh.instanceMatrix.needsUpdate = true; }
  if (!reduceMotion) fallPlace(Math.min(dt, 0.1), t);   // petals, leaves, rain or snow (still under reduced motion)
  const w = weatherNow();                               // thunder: a short white flash now and then (none under reduced motion)
  const flash = w && w.kind === 'thunder' && !reduceMotion && (t % 7.3) < 0.12;
  if (flash !== !!TOWER.flash) { TOWER.flash = flash; sceneEl.style.filter = flash ? 'brightness(1.8)' : ''; }
}
/* The room under the pointer in the building: its full name and state, as the canvas's title. */
const TOWER_STATE_JA = { working: '作業中', thinking: '考え中', waiting: '許可待ち', idle: '待機（消灯）', empty: '空き' };
function towerHover(hit) {
  const F = hit && TOWER.floors[hit.object.userData.floor];
  const bay = F && hit.uv ? F.bays.find((b) => hit.uv.x >= b.x0 && hit.uv.x <= b.x1) : null;
  return bay ? `${hit.object.userData.floor + 1}F · ${bay.id ? towerName(bay.id) : '（空き）'} · ${TOWER_STATE_JA[bay.state]}` : '';
}
function towerPose() {
  const h = towerBase(LIVE.floors.length) + 3, c = new THREE.Vector3(0, h / 2, 0);
  const dist = Math.max(24, h * 1.5 + 15);
  return { p: c.clone().add(new THREE.Vector3(6.5, 6, 22.5).normalize().multiplyScalar(dist)), t: c };
}
function towerSetView(on) {
  TOWER.on = on;
  camera.layers.set(on ? TOWER.LAYER : 0);
  controls.minDistance = on ? 14 : 8; controls.maxDistance = on ? 150 : 80;
  // The building is looked at from its middle, so it can turn almost to face-on (just above the horizon);
  // a floor keeps the office's limit, which never shows the underside of the floor.
  controls.maxPolarAngle = on ? 1.52 : 1.25;
}
function towerEnter() {
  if (TOWER.on || LIVE.floors.length < 2 || zoom.zoomed) return;
  TOWER.look = LIVE.floor;
  towerSync();
  towerSetView(true);
  const pose = towerPose();
  controls.enabled = false;
  flyTo(pose.p, pose.t, controls.target, reduceMotion ? 0 : 0.8, () => { controls.target.copy(pose.t); controls.enabled = true; controls.update(); });
}
/* Down from the building into floor k (the camera starts at that floor's height in the building).
   ``project``: the room of the window pressed (that room alone), or null for an empty window (the whole floor);
   left out (the building button, the wheel), the view stays on what was picked before. */
function towerLeave(k, project) {
  if (!TOWER.on) return;
  towerSetView(false);
  if (liveGoToFloor(k)) LIVE3D.floorMove = true;
  const picked = project === undefined ? undefined : project && PROJECT[project] ? project : 'all';
  if (picked !== undefined && UI.project !== picked) { setProject(picked); return; }   // setProject flies there
  const pose = SOURCE.mode === 'live' ? liveRoomPose(UI.project !== 'all' && PROJECT[UI.project] && PROJECT[UI.project].shown ? UI.project : 'all') : roomPose(UI.project);
  controls.enabled = false;
  flyTo(pose.p, pose.t, controls.target, reduceMotion ? 0 : 0.8, () => { controls.target.copy(pose.t); controls.enabled = true; controls.update(); });
}
/* In the building, look at floor k's front (the demo's floor change; the floor buttons in the demo's building). */
function towerLookAt(k) {
  if (!TOWER.on) return;
  TOWER.look = Math.max(0, Math.min(LIVE.floors.length - 1, k));
  const y = towerY(TOWER.look), t = new THREE.Vector3(0, y, TOWER.D / 2), p = t.clone().add(new THREE.Vector3(5, 3, 30));
  controls.enabled = false;
  flyTo(p, t, controls.target, reduceMotion ? 0 : 0.9, () => { controls.target.copy(t); controls.enabled = true; controls.update(); });
}
/* One floor up (+1) or down (-1): the camera comes in from above or below. */
function liveFloorStep(dir) {
  const k = LIVE.floor + dir;
  if (TOWER.on) { towerLeave(Math.max(0, Math.min(LIVE.floors.length - 1, k))); return; }
  if (zoom.zoomed || !liveGoToFloor(k)) return;
  LIVE3D.floorMove = true;
  const id = UI.project !== 'all' && PROJECT[UI.project] && PROJECT[UI.project].shown ? UI.project : 'all';
  const pose = liveRoomPose(id), lift = new THREE.Vector3(0, -dir * 14, 0);
  camera.position.copy(pose.p).add(lift); controls.target.copy(pose.t).add(lift);
  controls.enabled = false;
  flyTo(pose.p, pose.t, controls.target, reduceMotion ? 0 : 0.7, () => { controls.target.copy(pose.t); controls.enabled = true; controls.update(); });
}
/* A project picked in the menu: its floor first (out of the building if need be); focusProject then flies to it. */
function liveShowFloorOf(id) {
  if (id === 'all' || !PROJECT[id]) return;
  if (TOWER.on) towerSetView(false);
  const k = liveFloorOf(id);
  if (k >= 0 && liveGoToFloor(k)) LIVE3D.floorMove = true;
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
/* Robots' name tags kept apart on screen (10-19): two robots close by (at play, in the smoking booth, at desks side
   by side) put their tags on each other and the one behind could not be read. Each frame, nearest first, a tag that
   would cross one already placed moves up just above it; the move eases (no flicker when the order swaps). Sizes
   are read again only when the text changes or every TAGS.measureMs, all reads before all writes (one layout). A
   robot showing じゃんけん lifts its tag clear of the hand. Cost per frame: TAGS.stats (the e2e reads it). */
const TAGS = { gap: 3, ease: 0.35, measureMs: 500, maxPasses: 12, rpsLift: 0.55, stats: { n: 0, sumMs: 0, maxMs: 0, frames: 0 } };
const tagNdc = new THREE.Vector3();
function placeRobotTags() {
  const t0 = performance.now(), W = canvas.clientWidth, H = canvas.clientHeight, list = [];
  for (const R of robots) {
    tagNdc.copy(R.robot.root.position).add(TAG_UP);
    if (R.robot.rps && R.robot.rps.visible) tagNdc.y += TAGS.rpsLift;
    tagNdc.project(camera);
    const hidden = tagNdc.z > 1 || tagNdc.z < -1 || !R.robot.root.visible || R.tag.hidden;
    const text = R.tag.textContent;
    if (!hidden && (!R.tagSize || R.tagSize.text !== text || t0 - R.tagSize.at > TAGS.measureMs)) R.tagSize = { text, at: t0, w: R.tag.offsetWidth, h: R.tag.offsetHeight };
    list.push({ R, hidden, x: ((tagNdc.x + 1) / 2) * W, y: ((1 - tagNdc.y) / 2) * H, z: tagNdc.z });
  }
  const placed = [];
  for (const it of list.filter((q) => !q.hidden).sort((a, b) => a.z - b.z)) {   // nearest first: it keeps its spot
    const { w, h } = it.R.tagSize, x0 = it.x - w / 2, x1 = it.x + w / 2;
    let bottom = it.y;
    for (let pass = 0; pass < TAGS.maxPasses; pass++) {
      const hit = placed.find((p) => x0 < p.x1 && p.x0 < x1 && bottom - h < p.y1 && p.y0 < bottom);
      if (!hit) break;
      bottom = hit.y0 - TAGS.gap;   // just above the one it crossed
    }
    placed.push({ x0, x1, y0: bottom - h, y1: bottom });
    it.target = it.y - bottom;
  }
  for (const it of list) {   // the writes
    const el = it.R.tag;
    if (it.hidden) { el.style.visibility = 'hidden'; it.R.tagDy = 0; continue; }
    el.style.visibility = 'visible';
    const dy = it.R.tagDy === undefined ? it.target : it.R.tagDy + (it.target - it.R.tagDy) * TAGS.ease;
    it.R.tagDy = Math.abs(dy - it.target) < 0.5 ? it.target : dy;
    el.style.transform = `translate(${it.x.toFixed(1)}px, ${(it.y - it.R.tagDy).toFixed(1)}px) translate(-50%, -100%)`;
  }
  const ms = performance.now() - t0, S0 = TAGS.stats;
  S0.n = list.length; S0.frames++; S0.sumMs += ms; S0.maxMs = Math.max(S0.maxMs, ms);
}
const HEAD_UP = new THREE.Vector3(0, 2.2, 0);
const TAG_UP = new THREE.Vector3(0, 2.62, 0);
function robotPoint(id, up) { const R = robots.find((x) => x.def.id === id); return R.robot.root.position.clone().add(up); }

function update3D(model, nowSec, dt) {
  if (SOURCE.mode === 'live') { liveUpdateRobots(nowSec, dt); liveSoloSync(); }
  else {
    demoDirector(model, nowSec);
    for (const R of robots) {
      const st = robotState[R.def.id];
      setRobotTired(R.robot, demoTired(R.def.id));
      R.robot.heavy = demoHeavy(R.def.id, model.t);
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
  if (TOWER.on) { towerSync(); towerAnimate(nowSec, dt); }
  skySync();
  tagsEl.hidden = zoom.zoomed || TOWER.on;
  placeRobotTags();
  for (const rt of roomTags) { placeTag(rt.el, rt.p); rt.el.classList.toggle('on', UI.project === rt.id); }
  if (trayTag) placeTag(trayTag.el, trayTag.p);   // the demo's document tray
}
