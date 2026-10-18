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
  slices: {}, model: null, modelAt: 0, labelOfReal: {}, seenSeq: 0, specRows: {}, sheetAsked: {}, sheetFailed: {},
  seats: {}, seatOf: {}, leaving: {}, shown: [], floors: [], floor: 0, rank: {}, connectedOnce: false, serverError: '',
};
const ROOM_MAX = 6;
/* A floor is three rooms across, two deep (requester, 10-18: the rooms looked cramped at 6×5 in rows of three). */
const FLOOR_COLS = 3, ROOM_GAP = 0.6;
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
  /* perm.decide (plan 04 §5, P6): `always` is true (every suggestion) or the indexes the person kept, and goes
     with allow only; a reason goes with deny only. The answer shows when the perms slice says "sent". */
  decide(id, behavior, { perm: p, reason = '', always = null }) {
    const msg = { permId: (p && p.realId) || id, behavior: behavior === 'deny' ? 'deny' : 'allow' };
    if (msg.behavior === 'allow' && always) msg.always = always;
    if (msg.behavior === 'deny' && reason) msg.reason = reason;
    netRequest('perm.decide', msg).then((ack) => showToast(ack.ok
      ? `${p.who} の ${p.tool} を${msg.behavior === 'deny' ? `拒否${reason ? '（理由つき）' : ''}` : msg.always ? '許可し、ルールを追加' : '許可'}した（Claude Code へ送った）`
      : `送れなかった（${ack.error || '不明'}）`));
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

/* The model has the demo's shape (computeModel(t, loop) there): tests, specs, tasks, perms, pending. Live it is
   built from the slices, again when a slice changed and at most every half second otherwise (a task's "new"
   mark and the waiting clocks move with time). It reads the wall clock itself: 40-scene.js asks for it before
   70-main.js has declared its clock. */
function computeModel() {
  const now = Date.now();
  if (LIVE.model && now - LIVE.modelAt < 500) { LIVE.model.t = secOfDay(now); return LIVE.model; }
  LIVE.modelAt = now;
  const t = secOfDay(now);
  const tests = liveTests();
  const perms = PERMS_LIVE.map((p) => ({ ...p, since: t - p.at }));
  const tasks = liveTasks(now);
  for (const x of tasks) x.perm = perms.find((p) => p.task === x.key && (p.status === 'pending' || p.status === 'sent')) || null;
  LIVE.model = { t, loop: 0, tests, specs: SPECS, tasks, perms, pending: perms.filter((p) => p.status === 'pending' || p.status === 'sent') };
  return LIVE.model;
}

/* ---------- specs (plan 04 Spec → the demo's spec rows) ---------- */
const SPEC_KEYS = ['metadata', 'structure', 'stateManagement', 'dataFlow', 'userActions', 'transitions', 'branchContracts'];
const labelOf = (realId) => (realId ? LIVE.labelOfReal[realId] || null : null);
function liveSpecRow(x) {
  const secs = Object.fromEntries((Array.isArray(x.sections) ? x.sections : []).map((q) => [q.key, q]));
  const written = SPEC_KEYS.map((k) => { const q = secs[k]; return !q ? 0 : q.state === 'writing' ? (q.items ? 0.6 : 0.3) : q.state === 'written' ? 1 : 0; });
  const totals = SPEC_KEYS.map((k) => Math.max(0, Number((secs[k] || {}).items) || 0));
  const impl = x.impl || { total: 0, done: 0 }, tests = x.tests || { total: 0, passed: 0, failed: 0, running: false };
  const share = impl.total > 0 ? Math.min(1, impl.done / impl.total) : 0;
  let left = Math.round(sumImpl(totals) * share);
  const implN = totals.map((n, k) => { if (k < 1 || k > 5) return 0; const v = Math.min(n, left); left -= v; return v; });
  implN[6] = Math.min(totals[6] || tests.total, tests.passed);
  if (!totals[6] && tests.total) totals[6] = tests.total;
  const implPhase = impl.done > 0 || tests.total > 0;
  const writingIdx = SPEC_KEYS.findIndex((k) => (secs[k] || {}).state === 'writing');
  const by = labelOf(x.by);
  const pctImpl = impl.total ? pct(share) : 0;
  const status = tests.running ? { kind: 'test', text: `テスト中 ${tests.passed}/${tests.total}` }
    : writingIdx >= 0 ? { kind: 'write', text: `書き込み中 ${pct(written.reduce((a, b) => a + b, 0) / 7)}%` }
      : x.bucket === 'done' ? { kind: 'done', text: '実装・テスト完了' }
        : x.bucket === 'todo' ? { kind: 'idle', text: '未着手' }
          : impl.total && impl.done >= impl.total ? { kind: 'impl-done', text: tests.total ? `実装完了・テスト ${tests.passed}/${tests.total}` : '実装完了・テスト待ち' }
            : impl.done > 0 ? { kind: by ? 'impl' : 'paused', text: `実装 ${pctImpl}%` }
              : written.every((w) => w >= 1) ? { kind: 'written', text: '記述完了・実装待ち' } : { kind: 'paused', text: `記述 ${pct(written.reduce((a, b) => a + b, 0) / 7)}%` };
  const note = `実装 ${impl.done}/${impl.total}${tests.total ? ` · テスト ${tests.passed}/${tests.total}${tests.failed ? `（失敗 ${tests.failed}）` : ''}` : ' · テストの定義なし'}`;
  const prev = LIVE.specRows[x.id];
  const row = {
    id: x.id, screen: String(x.name || ''), name: String(x.name || ''), project: x.projectId, file: String(x.file || ''),
    doc: prev && prev.docAt === x.updatedAt ? prev.doc : (prev ? prev.doc : null), docAt: prev ? prev.docAt : null, updatedAt: x.updatedAt,
    totals, related: prev && prev.doc ? (prev.doc.related || []) : [], written, implN, implPhase, writingIdx,
    implIdx: by && writingIdx < 0 && x.bucket === 'live' && !tests.running ? Math.max(1, implN.findIndex((n, k) => k >= 1 && k <= 5 && n < totals[k])) : -1,
    testIdx: tests.running ? 6 : -1, by, relatedNow: -1, status, note, bucket: ['live', 'partial', 'todo', 'done'].includes(x.bucket) ? x.bucket : 'partial',
  };
  if (row.implIdx === 0) row.implIdx = -1;
  LIVE.specRows[x.id] = row;
  return row;
}
function rebuildSpecs() {
  const list = Array.isArray(LIVE.slices.specs) ? LIVE.slices.specs : [];
  const rows = list.filter((x) => x && x.id && PROJECT[x.projectId]).map(liveSpecRow);
  rows.sort((a, b) => (PROJECT[a.project].order - PROJECT[b.project].order) || a.file.localeCompare(b.file));
  SPECS.splice(0, SPECS.length, ...rows);
  for (const k of Object.keys(SPEC_INDEX)) delete SPEC_INDEX[k];
  SPECS.forEach((x, i) => { SPEC_INDEX[x.id] = i; });
  for (const k of Object.keys(SCREEN_JA)) delete SCREEN_JA[k];
  for (const x of SPECS) if (x.doc && x.doc.metadata) SCREEN_JA[x.doc.metadata.name] = x.doc.metadata.displayName || x.name;
}
/* The sheet (plan 09 §6): asked for when a spec opens on the whiteboard, again when the spec changes. */
function liveWantSheet(row) {
  if (!row || SOURCE.mode !== 'live') return;
  const asked = LIVE.sheetAsked[row.id];
  if (row.doc && row.docAt === row.updatedAt) return;
  if (asked && asked.at === row.updatedAt && Date.now() - asked.t < 15000) return;
  LIVE.sheetAsked[row.id] = { at: row.updatedAt, t: Date.now() };
  netRequest('spec.sheet', { specId: row.id }).then((ack) => { if (!ack.ok) LIVE.sheetFailed[row.id] = ack.error || '不明'; });
}
function liveSheet(msg) {
  const row = LIVE.specRows[msg.specId];
  if (!row || !msg.cards || typeof msg.cards !== 'object') return;
  const d = msg.cards;
  const arr = (v) => (Array.isArray(v) ? v : []);
  const meta = d.metadata && typeof d.metadata === 'object' ? d.metadata : {};
  row.doc = {
    metadata: { name: String(meta.name || ''), displayName: String(meta.displayName || row.name), description: String(meta.description || ''), platforms: arr(meta.platforms).map(String), layoutFile: String(meta.layoutFile || ''), createdAt: String(meta.createdAt || '') },
    components: arr(d.components), layoutChildren: arr(d.layoutChildren), uiVariables: arr(d.uiVariables), eventHandlers: arr(d.eventHandlers),
    vmMethods: arr(d.vmMethods), vmVars: arr(d.vmVars), repositories: arr(d.repositories), apis: arr(d.apis),
    userActions: arr(d.userActions), transitions: arr(d.transitions), branches: arr(d.branches), related: arr(d.related),
  };
  row.related = row.doc.related; row.docAt = LIVE.sheetAsked[row.id] ? LIVE.sheetAsked[row.id].at : row.updatedAt;
  delete LIVE.sheetFailed[row.id];
  if (row.doc.metadata.name) SCREEN_JA[row.doc.metadata.name] = row.doc.metadata.displayName || row.name;
}

/* ---------- tasks (plan 04 Task → the demo's task rows; plan 09 §5) ---------- */
function rebuildTasks() {
  const list = Array.isArray(LIVE.slices.tasks) ? LIVE.slices.tasks : [];
  const rows = [];
  for (const x of list) {
    if (!x || !x.key || !x.sessionId) continue;
    const listLabel = LIVE.labelOfReal[x.sessionId];
    if (!listLabel) continue;
    const blockedBy = Array.isArray(x.blockedBy) ? x.blockedBy.map(String) : [];
    rows.push({
      list: listLabel, id: String(x.id), realKey: x.key, subject: String(x.subject || ''), description: String(x.description || ''),
      activeForm: x.activeForm ? String(x.activeForm) : '', owner: labelOf(x.owner) || null, spec: x.specId && SPEC_INDEX[x.specId] !== undefined ? x.specId : null,
      status: x.status, blockedByAll: blockedBy, blocksAll: Array.isArray(x.blocks) ? x.blocks.map(String) : [],
      created: x.createdAt ? secOfDay(x.createdAt) : -1, createdMs: x.createdAt || 0,
      start: x.startedAt ? secOfDay(x.startedAt) : null, end: x.completedAt ? secOfDay(x.completedAt) : null,
    });
  }
  TASKS.splice(0, TASKS.length, ...rows);
  for (const k of Object.keys(TASK_BY_KEY)) delete TASK_BY_KEY[k];
  for (const x of TASKS) TASK_BY_KEY[`${x.list}#${x.id}`] = x;
  for (const x of TASKS) {
    // The demo keeps one blocker per task: the first one not done yet (else the first).
    const open = x.blockedByAll.find((b) => (TASK_BY_KEY[`${x.list}#${b}`] || {}).status !== 'completed');
    x.blockedBy = open || x.blockedByAll[0] || null;
    if (x.blockedBy && !TASK_BY_KEY[`${x.list}#${x.blockedBy}`]) x.blockedBy = null;
  }
}
function liveTasks(now) {
  const t = secOfDay(now);
  return TASKS.map((x) => {
    const dep = x.blockedBy ? TASK_BY_KEY[`${x.list}#${x.blockedBy}`] : null;
    const status = x.status === 'completed' ? 'completed' : x.status === 'in_progress' ? 'in_progress' : 'pending';
    const blocked = status === 'pending' && x.blockedByAll.some((b) => (TASK_BY_KEY[`${x.list}#${b}`] || {}).status !== 'completed');
    const col = status === 'completed' ? 'done' : status === 'in_progress' ? 'doing' : blocked ? 'wait' : 'todo';
    void t;
    return { ...x, key: `${x.list}#${x.id}`, status, blocked, dep, col, fresh: x.createdMs > 0 && now - x.createdMs < 1500 };
  });
}

/* ---------- test runs (plan 04 TestRun → the demo's one test panel: the run that matters now) ---------- */
const CASE_STATUS = { running: 'running', passed: 'passed', failed: 'failed', skipped: 'skipped', pending: 'pending' };
/* A room's board, a big spec board past ROOM_BIG specs, and a test easel while it has runs. */
const ROOM_BIG = 9;
function roomFlags() {
  const counts = {};
  for (const x of SPECS) counts[x.project] = (counts[x.project] || 0) + 1;
  const runs = Array.isArray(LIVE.slices.tests) ? LIVE.slices.tests : [];
  for (const r of ROOMS) { r.big = (counts[r.id] || 0) > ROOM_BIG; r.tests = runs.some((x) => x && x.projectId === r.id); }
}
function liveTests() {
  const t = liveTestsFor(null);
  if (t !== EMPTY_TESTS) CASES.splice(0, CASES.length, ...t.rows); else CASES.length = 0;
  return t;
}
/* The run that matters for a project (or for what the view shows): the one running, else the latest. */
function liveTestsFor(projectId) {
  const runs = (Array.isArray(LIVE.slices.tests) ? LIVE.slices.tests : []).filter((r) => r && r.id);
  const mine = projectId ? runs.filter((r) => r.projectId === projectId) : runs.filter((r) => !LIVE.uiReady || inScope(r.projectId));   // UI exists once 70-main.js ran
  const pickFrom = projectId || LIVE.uiReady ? mine : runs;   // narrowed to a project: only its runs
  if (!pickFrom.length) return EMPTY_TESTS;
  const run = pickFrom.find((r) => r.status === 'running') || [...pickFrom].sort((a, b) => (b.startedAt || 0) - (a.startedAt || 0))[0];
  const cases = Array.isArray(run.cases) ? run.cases : [];
  const rows = cases.map((c) => ({ name: String(c.name || ''), branch: '', status: CASE_STATUS[c.status] || 'pending', attempt: 1, step: c.status === 'running' ? 'このケースを実行中' : '' }));
  const passed = rows.filter((r) => r.status === 'passed').length;
  const failed = rows.filter((r) => r.status === 'failed').length;
  const runningIdx = rows.findIndex((r) => r.status === 'running');
  const dev = (Array.isArray(LIVE.slices.devices) ? LIVE.slices.devices : []).find((d) => d && d.id === run.deviceId);
  const statusText = run.status === 'running' ? `実行中${rows.length ? ` ${passed}/${rows.length} 通過` : ''}`
    : run.summary ? `${run.status === 'passed' ? '通過' : '失敗'} · ${run.summary}` : run.status === 'passed' ? '通過' : '失敗';
  return {
    rows, passed, failed, runningIdx, retrying: false, active: run.status === 'running', statusText,
    file: String(run.file || run.command || ''), device: dev ? String(dev.name) : ({ ios: 'iOS', android: 'Android', web: 'Web' }[run.platform] || ''),
    who: labelOf(run.agentId), project: run.projectId, runStatus: run.status, command: String(run.command || ''),
  };
}

/* ---------- permission prompts (plan 04 Permission, plan 08 §4 → the demo's perm rows) ---------- */
const PERMS_LIVE = [];
const PERM_STATUS = { pending: 'pending', sent: 'sent', allow: 'allow', deny: 'deny', answered_in_terminal: 'terminal', expired: 'expired' };
/* The fields the decision is about, exactly as the server got them (card.exact: command, file_path, old_string,
   new_string … uncut up to 20,000 characters, whitespace kept; Write's content as its first 2,000). The card shows
   these and nothing else: a summary or the 2,000-character preview once hid the tail of a long command
   ("…; rm -rf ~/tail-hidden") and folded runs of spaces (dd's review, 10-18). */
const EXACT_KEYS = ['command', 'file_path', 'notebook_path', 'url', 'pattern', 'old_string', 'new_string', 'content'];
function exactOf(x) {
  const e = x.exact && typeof x.exact === 'object' ? x.exact : null;
  if (!e) return null;
  const out = {};
  for (const k of EXACT_KEYS) if (typeof e[k] === 'string') out[k] = e[k];
  if (Number.isFinite(e.contentTruncated)) out.contentTruncated = e.contentTruncated;
  return Object.keys(out).length ? out : null;
}
/* One line naming what is asked, for the log and the history (never the place a decision is made). */
function permWhat(x, exact) {
  if (exact) for (const k of EXACT_KEYS) if (exact[k]) return exact[k];
  return String(x.summary || '');
}
function rebuildPerms() {
  const list = Array.isArray(LIVE.slices.perms) ? LIVE.slices.perms : [];
  const rows = [];
  for (const x of list) {
    if (!x || !x.id) continue;
    const who = labelOf(x.agentId) || labelOf(x.sessionId);
    if (!who || !DEF[who]) continue;
    // A prompt belongs to the task its robot owns and is doing; otherwise it stands alone (no guessing).
    const doing = TASKS.find((q) => q.owner === who && q.status === 'in_progress');
    const can = x.can && typeof x.can === 'object' ? x.can : {};
    const exact = exactOf(x);
    rows.push({
      id: String(x.id), realId: String(x.id), who, task: doing ? `${doing.list}#${doing.id}` : null, tool: String(x.toolName || ''),
      input: { command: permWhat(x, exact) }, exact, tooLongToShow: !!x.tooLongToShow,
      preview: String(x.preview || ''), suggestions: x.suggestions, rule: '',
      at: secOfDay(x.createdAt || Date.now()), end: x.decidedAt ? secOfDay(x.decidedAt) : null,
      status: PERM_STATUS[x.status] || 'pending', decidedBy: x.decidedBy || null, sentBehavior: x.sentBehavior || null,
      sentBy: x.sentBy || null, sentRules: Array.isArray(x.sentRules) ? x.sentRules : null, sentReason: x.sentReason ? String(x.sentReason) : '',
      terminalBehavior: x.terminalBehavior || null, relayOnly: !!x.relayOnly,
      decided: x.decidedAt ? { at: secOfDay(x.decidedAt), behavior: x.status === 'deny' || x.terminalBehavior === 'deny' ? 'deny' : 'allow' } : null,
      can: { allowDeny: !!can.allowDeny, always: !!can.always, reason: !!can.reason },
      raw: { id: x.id, toolName: x.toolName, summary: x.summary, exact: x.exact, tooLongToShow: !!x.tooLongToShow, preview: x.preview, suggestions: x.suggestions, status: x.status, relayOnly: !!x.relayOnly },
    });
  }
  PERMS_LIVE.splice(0, PERMS_LIVE.length, ...rows);
  for (const k of Object.keys(PERM_BY_ID)) delete PERM_BY_ID[k];
  for (const p of PERMS_LIVE) PERM_BY_ID[p.id] = p;
}

/* ---------- rooms: size by robot count, left to right by order, a new row past 24 (plan 07 §4) ---------- */
// Floor and walls only: the boards, desks and robots keep their scale, so a bigger room is more space around them.
function roomSize(n) { return n <= 8 ? [10, 8] : n <= 12 ? [12, 9] : [14, 10]; }
function seatGrid(room) {
  const xs = [], zs = [];
  for (let x = room.x0 + 1.15; x <= room.x1 - 0.85 + 1e-6; x += 1.75) xs.push(x);
  for (let z = room.z0 + 1.35; z <= room.z1 - 1.05 + 1e-6; z += 1.85) zs.push(z);
  const seats = [];
  for (const z of zs) for (const x of xs) seats.push([x, z]);
  return seats;
}
const doorOf = (room) => ({ inside: [room.x1 - 0.7, room.z1 - 0.5], outside: [room.x1 - 0.7, room.z1 + 1.6] });

/* ---------- floors: six rooms to a floor, the rooms where something happens on 1F (requester's ruling, 10-18) ----------
   A machine with 28 sessions in 11 projects showed the first six rooms by order and kept them: a project that started
   working later (the last by order) never reached the 3D view. Now every room is on a floor; 1F takes the rooms where
   a robot waits for permission, then the rooms where one works, and only the 1F rooms are drawn in detail.
   - rank: 0 a robot waits for permission, 1 a robot works, 2 robots that are idle, 3 nobody.
   - 1F: the active rooms (rank 0 or 1) by rank, a room already on 1F first within a rank, then order; at most
     ROOM_MAX. Seats left over keep the rooms that were on 1F (a room that stopped working stays until an active one
     needs its seat), then the rest by rank and order. Rooms that stay keep their slot, so they do not move around.
   - 2F, 3F …: the other rooms by rank and order, ROOM_MAX to a floor. More than ROOM_MAX active rooms spill to 2F.
   - The floor being looked at is a number: a regrouping never moves the view to another floor (only fewer floors
     can bring it down). */
function roomRanks() {
  const waiting = new Set(PERMS_LIVE.filter((p) => p.status === 'pending' && DEF[p.who]).map((p) => DEF[p.who].room));
  const rank = {};
  for (const r of ROOMS) rank[r.id] = 3;
  for (const d of ROBOT_DEFS) {
    if (LIVE.leaving[d.id] || !(d.room in rank)) continue;
    const st = (robotState[d.id] || {}).state;
    const k = st === 'waiting' ? 0 : st && st !== 'idle' && st !== 'done' ? 1 : 2;
    rank[d.room] = Math.min(rank[d.room], k);
  }
  for (const id of waiting) if (id in rank) rank[id] = 0;
  return rank;
}
function assignFloors(rooms, rank, prevFirst, max = ROOM_MAX) {
  const rk = (r) => (r.id in rank ? rank[r.id] : 3);
  const ids = new Set(rooms.map((r) => r.id));
  const was = new Set(prevFirst.filter((id) => ids.has(id)));
  const active = rooms.filter((r) => rk(r) < 2).sort((a, b) => rk(a) - rk(b) || (was.has(b.id) - was.has(a.id)) || a.order - b.order);
  const want = active.slice(0, max).map((r) => r.id);
  for (const id of prevFirst) if (want.length < max && was.has(id) && !want.includes(id)) want.push(id);
  const rest = rooms.filter((r) => !want.includes(r.id)).sort((a, b) => rk(a) - rk(b) || a.order - b.order);
  while (want.length < max && rest.length) want.push(rest.shift().id);
  // Rooms that stay on 1F keep their slot; the newcomers take the freed slots in their rank order.
  const stay = prevFirst.filter((id) => want.includes(id));
  const comers = want.filter((id) => !stay.includes(id));
  const first = prevFirst.filter((id) => ids.has(id)).map((id) => (stay.includes(id) ? id : comers.shift() || null)).filter(Boolean);
  first.push(...comers);
  const floors = [first.slice(0, max)];
  for (let k = 0; k < rest.length; k += max) floors.push(rest.slice(k, k + max).map((r) => r.id));
  return floors.filter((f, k) => k === 0 || f.length);
}
function layoutRooms() {
  const counts = {};
  for (const d of ROBOT_DEFS) counts[d.room] = (counts[d.room] || 0) + 1;
  LIVE.rank = roomRanks();
  LIVE.floors = assignFloors(ROOMS, LIVE.rank, LIVE.floors[0] || []);
  LIVE.floor = Math.min(LIVE.floor, LIVE.floors.length - 1);
  LIVE.shown = LIVE.floors[LIVE.floor] || [];
  const byOrder = LIVE.shown.map((id) => PROJECT[id]);   // the floor's slot order
  for (const r of ROOMS) if (!LIVE.shown.includes(r.id)) { r.shown = false; r.x0 = r.x1 = r.z0 = r.z1 = undefined; }
  // Every room on the floor gets the floor's largest size, in a fixed grid of FLOOR_COLS by two.
  let w = 0, d = 0;
  for (const r of byOrder) {
    r.shown = true;
    r.peak = Math.max(r.peak || 0, counts[r.id] || 0);   // a room does not shrink while the page is open
    const [rw, rd] = roomSize(r.peak);
    w = Math.max(w, rw); d = Math.max(d, rd);
  }
  const cols = Math.min(FLOOR_COLS, byOrder.length), rows = Math.ceil(byOrder.length / FLOOR_COLS);
  const ox = -(cols * w + (cols - 1) * ROOM_GAP) / 2, oz = -(rows * d + (rows - 1) * ROOM_GAP) / 2;
  const placed = byOrder.map((r, i) => [r, (i % FLOOR_COLS) * (w + ROOM_GAP), Math.floor(i / FLOOR_COLS) * (d + ROOM_GAP), w, d]);
  placed.forEach(([r, px, pz, w, d], k) => {
    r.x0 = +(px + ox).toFixed(3); r.x1 = +(r.x0 + w).toFixed(3); r.z0 = +(pz + oz).toFixed(3); r.z1 = +(r.z0 + d).toFixed(3);
    r.floor = FLOORS[r.order % FLOORS.length]; r.back = 3.9; r.left = 3.9;
    r.geo = `${r.x0},${r.x1},${r.z0},${r.z1},${r.big ? 'big' : ''},${r.tests ? 'tests' : ''}`;
    void k;
  });
}

/* Eight hours into its session a main robot gets tired (requester, 10-18). The start is the session's own
   (sessions[].since, from its transcript); a session without one is never tired — startedAt is when the server
   first saw it, not when it began. */
const TIRED_MS = 8 * 3600 * 1000;
const isTired = (since, now) => Number.isFinite(since) && since > 0 && now - since >= TIRED_MS;
const sinceOf = (label) => { const s = SESSIONS.find((x) => x.id === SESSION_OF[label]); return s ? s.since : null; };

/* Another floor, from the floor buttons, the building view or a project picked in the menu. */
function liveFloorOf(id) { return LIVE.floors.findIndex((f) => f.includes(id)); }
function liveGoToFloor(k) {
  if (!(k >= 0 && k < LIVE.floors.length) || k === LIVE.floor) return false;
  LIVE.floor = k;
  layoutRooms();
  placeRobots();
  SOURCE.layoutRev += 1;
  LIVE.model = null;
  return true;
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
    r.mock = p.mock && typeof p.mock === 'object' ? { running: !!p.mock.running, port: Number(p.mock.port) || 0, other: !!p.mock.other } : null;
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
    next.push({ id: label, project: s.projectId, robots, room: PROJECT[s.projectId].name, status: s.status, title: s.title || '',
      since: Number.isFinite(s.since) && s.since > 0 ? s.since : null });   // the transcript's first record; none: not guessed
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
  rebuildSpecs();
  roomFlags();
  rebuildSessions();
  rebuildTasks();
  rebuildPerms();
  layoutRooms();   // after the permissions: a room's rank comes from this round's requests
  placeRobots();
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
  sheet(msg) { liveSheet(msg); },
  notice(level, text) { if (text) showToast(text); void level; },
};
