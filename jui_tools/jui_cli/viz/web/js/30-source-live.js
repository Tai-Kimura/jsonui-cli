/* =====================================================================
   Live source: the names the rest of the view reads (the same names the demo script defines), built from the
   server's slices (plan 07 §2–§4, plan 04 §1–§3).
   - Arrays and tables are made once and refilled in place (other parts hold references to them).
   - A robot's id in the view is its Agent.label (unique, plan 04 §1); DEF[label].realId is the server's id.
   - SOURCE.layoutRev grows whenever the rooms or the robots in 3D change; 40-scene.js follows it.
   - Time: the view's clock is the local time of day in seconds (BASE_CLOCK 0), so fmtClock(abs) reads as the
     wall clock and LOOP is never reached.
   ===================================================================== */
const LOOP = 1e9;
const START_AT = 0;
const BASE_CLOCK = 0;
const secOfDay = (ms) => { const d = new Date(ms); return d.getHours() * 3600 + d.getMinutes() * 60 + d.getSeconds() + d.getMilliseconds() / 1000; };

const ROOMS = [];                 // the projects (all of them; the 3D shows at most ROOM_MAX)
const PROJECT = {};
const SESSIONS = [];
const ROBOT_DEFS = [];            // robots on screen (a leaving robot stays until it has walked out)
const DEF = {};                   // every robot seen this page load: logs and tickers keep naming the ones gone
const SESSION_OF = {};
const PROJECT_OF = {};
const projectOfRobot = (id) => PROJECT_OF[SESSION_OF[id]];
const SESSION_UUID = {};
const AGENT_ID = {};
const CWD = {};
const doc = () => null;
const SPECS = [];                 // P4
const SPEC_INDEX = {};
const SCREEN_JA = {};
const CASES = [];                 // P4
const TASKS = [];                 // P4
const TASK_BY_KEY = {};
const EVENTS = [];                // the demo's script; live events arrive as messages instead
const PERM_BY_ID = {};            // P5
const permDecisions = new Map();
const alwaysRules = new Map();    // P5/P6: the rules added from the view (always empty until then)
const permRequestPayload = (p) => (p && p.raw) || {};
const permResponse = (p, behavior, reason) => ({ behavior, reason: reason || undefined });
const robotState = {};
function updateRobotStates() { /* the server decides the states (plan 04 §3) */ }

const EMPTY_TESTS = { rows: [], passed: 0, runningIdx: -1, retrying: false, active: false, statusText: 'まだ無い', file: '', device: '' };
const LIVE = {
  slices: {}, model: null, labelOfReal: {}, seenSeq: 0,
  seats: {}, seatOf: {}, leaving: {}, shown: [], connectedOnce: false, serverError: '',
};
const ROOM_MAX = 6;
const ROW_WIDTH = 24;
const FLOORS = ['--floor-a', '--floor-b', '--floor-c'];
const ROLE_OF = (a) => {
  if (a.kind === 'main') return 'main';
  const r = a.role;
  return ROLES[r] ? r : 'other';
};

/* ---------- the source's face to the rest of the view ---------- */
const SOURCE = {
  mode: 'live', layoutRev: 0, connected: false, replaySpeed: 1,
  /* perm.decide to the server; the answer shows when the perms slice changes (P5). */
  decide(id, behavior, { perm: p, reason = '' }) {
    const always = behavior === 'always';
    netRequest('perm.decide', { permId: (p && p.realId) || id, behavior: always ? 'allow' : behavior, always, reason: reason || undefined })
      .then((ack) => showToast(ack.ok ? `${p.who} の ${p.tool} への答えを Claude Code へ送った` : `送れなかった（${ack.error || '不明'}）`));
  },
  setReplaySpeed(v) { this.replaySpeed = Number(v) || 1; },
  /* 40-scene.js calls this when a leaving robot has walked out of the door. */
  robotGone(label) {
    if (rbState.id === label) closeRobot();   // its card closes when it has walked out
    const i = ROBOT_DEFS.findIndex((d) => d.id === label);
    if (i >= 0) ROBOT_DEFS.splice(i, 1);
    delete LIVE.leaving[label];
    freeSeat(label);
    rebuildSessions();
    SOURCE.layoutRev += 1;
  },
};

/* The model has the demo's shape (computeModel(t, loop) there); live it is rebuilt only when a slice changed.
   It reads the wall clock itself: 40-scene.js asks for it before 70-main.js has declared its clock. */
function computeModel() {
  if (!LIVE.model) LIVE.model = { t: 0, loop: 0, tests: EMPTY_TESTS, specs: SPECS, tasks: [], perms: [], pending: [] };
  LIVE.model.t = secOfDay(Date.now());
  return LIVE.model;
}

/* ---------- rooms: size by robot count, left to right by order, a new row past 24 (plan 07 §4) ---------- */
function roomSize(n) { return n <= 4 ? [6, 5] : n <= 8 ? [8, 6] : [10, 8]; }
function seatGrid(room) {
  const xs = [], zs = [];
  for (let x = room.x0 + 1.15; x <= room.x1 - 0.85 + 1e-6; x += 1.75) xs.push(x);
  for (let z = room.z0 + 1.35; z <= room.z1 - 1.05 + 1e-6; z += 1.85) zs.push(z);
  const seats = [];
  for (const z of zs) for (const x of xs) seats.push([x, z]);
  return seats;
}
const doorOf = (room) => ({ inside: [room.x1 - 0.7, room.z1 - 0.5], outside: [room.x1 - 0.7, room.z1 + 1.6] });

function layoutRooms() {
  const counts = {};
  for (const d of ROBOT_DEFS) counts[d.room] = (counts[d.room] || 0) + 1;
  // The rooms in 3D: the ones with robots first (by order), at most ROOM_MAX; a room the person picked stays.
  const byOrder = [...ROOMS].sort((a, b) => a.order - b.order);
  const keep = LIVE.shown.filter((id) => PROJECT[id]);
  for (const r of byOrder) if (keep.length < ROOM_MAX && !keep.includes(r.id) && counts[r.id]) keep.push(r.id);
  for (const r of byOrder) if (keep.length < ROOM_MAX && !keep.includes(r.id)) keep.push(r.id);
  LIVE.shown = keep.slice(0, ROOM_MAX);
  let x = 0, z = 0, rowDepth = 0, maxX = 0;
  const placed = [];
  for (const r of byOrder) {
    r.shown = LIVE.shown.includes(r.id);
    if (!r.shown) { r.x0 = r.x1 = r.z0 = r.z1 = undefined; continue; }
    const [w, d] = roomSize(Math.max(r.peak || 0, counts[r.id] || 0));
    r.peak = Math.max(r.peak || 0, counts[r.id] || 0);   // a room does not shrink while the page is open
    if (x > 0 && x + w > ROW_WIDTH) { x = 0; z += rowDepth + 0.6; rowDepth = 0; }
    placed.push([r, x, z, w, d]);
    x += w + 0.5; rowDepth = Math.max(rowDepth, d); maxX = Math.max(maxX, x - 0.5);
  }
  const depth = z + rowDepth, ox = -maxX / 2, oz = -depth / 2;
  placed.forEach(([r, px, pz, w, d], k) => {
    r.x0 = +(px + ox).toFixed(3); r.x1 = +(r.x0 + w).toFixed(3); r.z0 = +(pz + oz).toFixed(3); r.z1 = +(r.z0 + d).toFixed(3);
    r.floor = FLOORS[r.order % FLOORS.length]; r.back = 3.9; r.left = 3.9;
    r.geo = `${r.x0},${r.x1},${r.z0},${r.z1}`;
    void k;
  });
}

/* ---------- seats: a robot keeps its seat; a subagent sits near its parent; no seat → stand by the wall ---------- */
function freeSeat(label) {
  const s = LIVE.seatOf[label];
  if (!s) return;
  const m = LIVE.seats[s.room];
  if (m && m.get(s.idx) === label) m.delete(s.idx);
  delete LIVE.seatOf[label];
}
function seatPos(room, idx) {
  const grid = seatGrid(room);
  if (idx < grid.length) return { pos: grid[idx], ry: 0, standing: false };
  const k = idx - grid.length;   // standing along the front, then the right wall
  const along = room.x0 + 0.9 + k * 0.95;
  return along < room.x1 - 0.6 ? { pos: [along, room.z1 - 0.45], ry: Math.PI, standing: true }
    : { pos: [room.x1 - 0.45, room.z1 - 0.9 - (k - Math.floor((room.x1 - room.x0 - 1.5) / 0.95)) * 0.95], ry: -Math.PI / 2, standing: true };
}
function takeSeat(def, near) {
  const room = PROJECT[def.room];
  if (!room || !room.shown) return null;
  const m = LIVE.seats[room.id] || (LIVE.seats[room.id] = new Map());
  const grid = seatGrid(room);
  let best = -1, bestD = Infinity;
  for (let i = 0; i < grid.length; i++) {
    if (m.has(i)) continue;
    const d = near ? Math.hypot(grid[i][0] - near[0], grid[i][1] - near[1]) : i;
    if (d < bestD) { best = i; bestD = d; }
  }
  if (best < 0) { best = grid.length; while (m.has(best)) best += 1; }
  m.set(best, def.id);
  LIVE.seatOf[def.id] = { room: room.id, idx: best };
  return best;
}
function placeRobots() {
  // Seats follow rooms that moved (a room grew) by index; a robot in another room than its seat moves seats.
  for (const def of ROBOT_DEFS) {
    if (LIVE.leaving[def.id]) continue;
    const room = PROJECT[def.room];
    const s = LIVE.seatOf[def.id];
    if (!room || !room.shown) { freeSeat(def.id); def.pos = null; continue; }
    if (s && s.room !== room.id) freeSeat(def.id);
    if (!LIVE.seatOf[def.id]) {
      const parent = def.kind === 'sub' && LIVE.seatOf[def.mainLabel] && DEF[def.mainLabel] && DEF[def.mainLabel].pos;
      takeSeat(def, parent || null);
    }
    const p = seatPos(room, LIVE.seatOf[def.id].idx);
    def.pos = p.pos; def.ry = p.ry; def.standing = p.standing; def.door = doorOf(room);
  }
}

/* ---------- slices → the view's names ---------- */
const home = (s) => String(s || '');
function rebuildRooms() {
  const list = Array.isArray(LIVE.slices.projects) ? LIVE.slices.projects : [];
  const old = Object.fromEntries(ROOMS.map((r) => [r.id, r]));
  const next = list.filter((p) => p && typeof p.id === 'string').map((p, k) => {
    const r = old[p.id] || { id: p.id };
    r.name = String(p.name || p.id); r.path = home(p.displayRoot); r.jsonui = !!p.jsonui;
    r.order = Number.isFinite(p.order) ? p.order : k;
    return r;
  });
  ROOMS.splice(0, ROOMS.length, ...next);
  for (const k of Object.keys(PROJECT)) delete PROJECT[k];
  for (const r of ROOMS) PROJECT[r.id] = r;
}
function displayName(a, sess) {
  if (a.kind === 'main') return `セッション ${String((sess && sess.id) || a.sessionId || '').slice(0, 4)}…`;
  return a.agentType ? String(a.agentType) : 'サブエージェント';
}
function rebuildRobots(initial) {
  const sessions = Array.isArray(LIVE.slices.sessions) ? LIVE.slices.sessions : [];
  const agents = Array.isArray(LIVE.slices.agents) ? LIVE.slices.agents : [];
  const sessById = Object.fromEntries(sessions.filter((s) => s && s.id).map((s) => [s.id, s]));
  const seen = new Set();
  const now = Date.now();
  for (const a of agents) {
    if (!a || typeof a.label !== 'string' || !a.label) continue;
    const sess = sessById[a.sessionId];
    const label = a.label;
    const mainLabel = sess && sess.label ? sess.label : label;
    const gone = !!a.leftAt || (sess && sess.status === 'ended');
    let def = DEF[label];
    const isNew = !def || !ROBOT_DEFS.includes(def);
    if (!def) def = DEF[label] = { id: label };
    Object.assign(def, {
      realId: String(a.id || label), sessionId: String(a.sessionId || ''), kind: a.kind === 'sub' ? 'sub' : 'main',
      role: ROLE_OF(a), agent: displayName(a, sess), furnished: true, mainLabel,
      room: sess && sess.projectId ? sess.projectId : (def.room || ''),
    });
    LIVE.labelOfReal[def.realId] = label;
    if (def.kind === 'main' && sess) LIVE.labelOfReal[sess.id] = label;
    SESSION_OF[label] = mainLabel;
    if (def.kind === 'sub') AGENT_ID[label] = def.realId;
    if (gone && !isNew) { if (!LIVE.leaving[label]) LIVE.leaving[label] = { since: now }; }
    else if (!gone && isNew) { ROBOT_DEFS.push(def); def.enter = !initial; }   // robots already there sit down at once
    else if (!gone) delete LIVE.leaving[label];
    const st = { state: STATES[a.state] ? a.state : 'idle', act: String(a.act || '') };
    if (LIVE.leaving[label]) st.state = 'done';
    robotState[label] = st;
    seen.add(label);
  }
  // Agents no longer in the slice leave the same way.
  for (const def of ROBOT_DEFS) {
    if (!seen.has(def.id) && !LIVE.leaving[def.id]) LIVE.leaving[def.id] = { since: now };
    if (LIVE.leaving[def.id] && robotState[def.id]) robotState[def.id] = { ...robotState[def.id], state: 'done' };
  }
  for (const s of sessions) {
    if (!s || !s.id) continue;
    const label = s.label || LIVE.labelOfReal[s.id];
    if (!label) continue;
    SESSION_UUID[label] = s.id; CWD[label] = home(s.cwd); PROJECT_OF[label] = s.projectId;
  }
}
function rebuildSessions() {
  const sessions = Array.isArray(LIVE.slices.sessions) ? LIVE.slices.sessions : [];
  const next = [];
  for (const s of sessions) {
    if (!s || !s.id || !PROJECT[s.projectId]) continue;
    const label = s.label || LIVE.labelOfReal[s.id];
    const robots = ROBOT_DEFS.filter((d) => d.mainLabel === label || d.id === label)
      .sort((a, b) => (a.kind === 'main' ? -1 : 0) - (b.kind === 'main' ? -1 : 0) || a.id.localeCompare(b.id)).map((d) => d.id);
    if (!robots.length || robots[0] !== label) continue;   // a session is shown through its main robot
    next.push({ id: label, project: s.projectId, robots, room: PROJECT[s.projectId].name, status: s.status, title: s.title || '' });
  }
  SESSIONS.splice(0, SESSIONS.length, ...next);
}
function layoutSignature() {
  return JSON.stringify([ROOMS.map((r) => [r.id, r.geo || '', r.shown]), ROBOT_DEFS.map((d) => [d.id, d.role, d.room, (d.pos || []).join()])]);
}
function liveApply(changed, replace) {
  if (replace) LIVE.slices = {};
  for (const [k, v] of Object.entries(changed || {})) LIVE.slices[k] = v;
  const before = layoutSignature();
  rebuildRooms();
  rebuildRobots(replace);
  layoutRooms();
  placeRobots();
  rebuildSessions();
  const server = LIVE.slices.server || {};
  const errs = Object.entries(server.sources || {}).filter(([, s]) => s && (s.error || s.state === 'error')).map(([k, s]) => `${k}: ${s.error || 'エラー'}`);
  LIVE.serverError = errs.join(' / ');
  if (layoutSignature() !== before) SOURCE.layoutRev += 1;
  LIVE.model = null;
  // The project the view was narrowed to is gone (its last session ended, or the server restarted empty).
  if (UI.project !== 'all' && !PROJECT[UI.project]) { UI.project = 'all'; paintScopeButtons(); }
}

/* ---------- events → the ticker and the log (plan 04 §2) ---------- */
const LIVE_CAT = { tool: 'tool', spec: 'spec', test: 'test', task: 'task', perm: 'session', session: 'session' };
function liveEvent(e) {
  if (!e || typeof e !== 'object' || !(Number(e.seq) > 0)) return null;
  const who = LIVE.labelOfReal[e.agentId] || LIVE.labelOfReal[e.sessionId];
  if (!who || !DEF[who]) return null;
  const tool = typeof e.tool === 'string' ? e.tool : '';
  let kind = String(e.kind || ''), what = String(e.text || '');
  if (e.cat === 'tool' && tool) {
    kind = tool.startsWith('mcp__') ? 'MCP' : tool;
    if (what.startsWith(`${tool} `)) what = what.slice(tool.length + 1);
  }
  return { abs: secOfDay(Number(e.at) || Date.now()), who, kind, what, cat: LIVE_CAT[e.cat] || 'session', detail: e.detail, srvSeq: Number(e.seq), seq: ++logSeq };
}
function liveEvents(items, older) {
  const add = [];
  for (const raw of items) {
    if (!older && Number(raw.seq) <= LIVE.seenSeq) continue;
    const item = liveEvent(raw);
    if (item) add.push(item);
    if (!older) LIVE.seenSeq = Math.max(LIVE.seenSeq, Number(raw.seq) || 0);
  }
  add.sort((a, b) => a.srvSeq - b.srvSeq);
  if (older) {
    const have = new Set(logItems.map((x) => x.srvSeq));
    const fresh = add.filter((x) => !have.has(x.srvSeq)).reverse();
    logItems.push(...fresh);
    if (!tickerItems.length) tickerItems.push(...fresh.slice(0, 40));
    if (fresh.length) LIVE.seenSeq = Math.max(LIVE.seenSeq, ...fresh.map((x) => x.srvSeq));
  } else {
    for (const item of add) { tickerItems.unshift(item); logItems.unshift(item); }
  }
  tickerItems.length = Math.min(tickerItems.length, 40);
  logItems.length = Math.min(logItems.length, 2000);
}

NET.handlers = {
  state(state) { SOURCE.connected = state === 'connected'; if (state === 'connected') LIVE.connectedOnce = true; liveChrome(); },
  snapshot(slices) {
    liveApply(slices, true);
    netRequest('events.more', { beforeSeq: 2 ** 31, limit: 200 });
    if (typeof refreshNow === 'function') refreshNow();
  },
  slices(changed) { liveApply(changed, false); },
  events(items, older) { liveEvents(items, older); },
  notice(level, text) { if (text) showToast(text); void level; },
};
