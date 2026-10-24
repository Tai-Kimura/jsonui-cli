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

const EMPTY_TESTS = { rows: [], passed: 0, runningIdx: -1, retrying: false, active: false, statusText: tl('tests.status.none'), none: true, file: '', device: '' };
const LIVE = {
  slices: {}, model: null, modelAt: 0, labelOfReal: {}, seenSeq: 0, specRows: {}, sheetAsked: {}, sheetFailed: {},
  seatOf: {}, leaving: {}, shown: [], floors: [], floor: 0, rank: {}, connectedOnce: false, serverError: '',
};
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
      ? tl('live.perm.sent.head', { who: p.who, tool: p.tool })
        + (msg.behavior === 'deny' ? tl('live.perm.deny') + (reason ? tl('live.perm.reason') : '') : msg.always ? tl('live.perm.always') : tl('live.perm.allow'))
        + tl('live.perm.sent.tail')
      : tl('live.send.failed', { error: ack.error || tl('live.unknown') })));
  },
  setReplaySpeed(v) { this.replaySpeed = Number(v) || 1; },
  /* A prompt typed in the 応答の履歴 tab, for this robot's session (POST /api/prompt; server.prompt_checks says what it
     must carry: the page's own Host and Origin, which the browser sets, the token, JSON). Resolves { ok, status, error }. */
  async sendPrompt(label, text, attachments) {
    try {
      const body = { sessionId: SESSION_UUID[label] || '', text };
      if (attachments && attachments.length) body.attachments = attachments;
      const res = await fetch('/api/prompt', {
        method: 'POST', cache: 'no-store', credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json', 'X-Jui-Viz-Token': NET.token },
        body: JSON.stringify(body),
      });
      return res.ok ? { ok: true, status: res.status } : { ok: false, status: res.status, error: (await res.text()).trim() };
    } catch (err) { return { ok: false, status: 0, error: tl('live.offline') }; }
  },
  /* One file attached to the next prompt for this robot's session (POST /api/attach: the checks of /api/prompt, the bytes
     as application/octet-stream; the server keeps it under its own name). Resolves { ok, id, name, media, size } or
     { ok: false, status, error }. */
  async attachFile(label, file) {
    try {
      const res = await fetch('/api/attach', {
        method: 'POST', cache: 'no-store', credentials: 'same-origin',
        headers: { 'Content-Type': 'application/octet-stream', 'X-Jui-Viz-Token': NET.token,
          'X-Jui-Viz-Session': SESSION_UUID[label] || '', 'X-Jui-Viz-Name': encodeURIComponent(file.name || ''),
          'X-Jui-Viz-Media': file.type || '' },
        body: file,
      });
      if (!res.ok) return { ok: false, status: res.status, error: (await res.text()).trim() };
      return { ok: true, ...(await res.json()) };
    } catch (err) { return { ok: false, status: 0, error: tl('live.offline') }; }
  },
  /* × on an attachment not sent yet (POST /api/attach-remove). Nothing to wait for. */
  attachRemove(label, id) {
    fetch('/api/attach-remove', {
      method: 'POST', cache: 'no-store', credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'X-Jui-Viz-Token': NET.token },
      body: JSON.stringify({ sessionId: SESSION_UUID[label] || '', id }),
    }).catch(() => {});
  },
  /* 停止 in the 応答の履歴 tab (55-history.js): POST /api/stop with the checks of /api/prompt; cancel takes the request back
     while it still waits. Resolves { ok, status, error }. */
  async stopSession(label, cancel) {
    try {
      const body = { sessionId: SESSION_UUID[label] || '' };
      if (cancel) body.cancel = true;
      const res = await fetch('/api/stop', {
        method: 'POST', cache: 'no-store', credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json', 'X-Jui-Viz-Token': NET.token },
        body: JSON.stringify(body),
      });
      return res.ok ? { ok: true, status: res.status } : { ok: false, status: res.status, error: (await res.text()).trim() };
    } catch (err) { return { ok: false, status: 0, error: tl('live.offline') }; }
  },
  /* 退勤 (50-panel.js): POST /api/session/end with the same page-only checks as /api/prompt; the server checks the session,
     the robot (a main one) and the process again, sends SIGTERM once and answers when it has gone. Resolves { ok, status, error }. */
  async clockOut(label) {
    try {
      const res = await fetch('/api/session/end', {
        method: 'POST', cache: 'no-store', credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json', 'X-Jui-Viz-Token': NET.token },
        body: JSON.stringify({ sessionId: SESSION_UUID[label] || '', agentId: (DEF[label] && DEF[label].realId) || '' }),
      });
      return res.ok ? { ok: true, status: res.status } : { ok: false, status: res.status, error: (await res.text()).trim() };
    } catch (err) { return { ok: false, status: 0, error: tl('live.offline') }; }
  },
  /* The 単価 sheet (2.3.6, 54-bills.js): set / remove / reset a model's line in the user's price table (POST /api/prices,
     the checks of /api/prompt). Resolves { ok } or { ok: false, error }. */
  async pricesOp(op, model, row) {
    try {
      const res = await fetch('/api/prices', {
        method: 'POST', cache: 'no-store', credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json', 'X-Jui-Viz-Token': NET.token },
        body: JSON.stringify(row ? { op, model, row } : { op, model }),
      });
      const text = await res.text();
      let body = null;
      try { body = JSON.parse(text); } catch (err) { body = null; }
      return res.ok && body && body.ok ? { ok: true } : { ok: false, error: (body && body.error) || `${res.status} ${text.trim()}` };
    } catch (err) { return { ok: false, error: tl('live.offline') }; }
  },
  /* The call bell (2.3.5, 50-panel.js): the line to paste, made by the server (callcmd.py) from the project's own folder,
     under the checks of /api/prompt. Nothing is run. Resolves { ok, command, flag } or { ok: false, why }. */
  async callCommand(project, name, role) {
    try {
      const res = await fetch('/api/call-command', {
        method: 'POST', cache: 'no-store', credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json', 'X-Jui-Viz-Token': NET.token },
        body: JSON.stringify({ projectId: project, name, role }),
      });
      const text = await res.text();
      let body = null;
      try { body = JSON.parse(text); } catch (err) { body = null; }
      if (res.ok && body && body.ok) return { ok: true, command: body.command, flag: body.flag };
      return { ok: false, why: (body && body.why) || tl('live.make.failed', { status: res.status, text: text.trim() }) };
    } catch (err) { return { ok: false, why: tl('live.offline') }; }
  },
  /* 2.3.6: question notifications are on (or not) on this page — POST /api/notify-presence, the checks of /api/prompt */
  async notifyPresence(ask) {
    try {
      await fetch('/api/notify-presence', { method: 'POST', cache: 'no-store', credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json', 'X-Jui-Viz-Token': NET.token }, body: JSON.stringify({ ask: !!ask }) });
    } catch (err) { /* the next word comes in 4 s */ }
  },
  /* 2.3.6: how long a question waits for the page — POST /api/ask-wait, saved in the server's config.json */
  async setAskWait(sec) {
    try {
      const res = await fetch('/api/ask-wait', { method: 'POST', cache: 'no-store', credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json', 'X-Jui-Viz-Token': NET.token }, body: JSON.stringify({ sec }) });
      const text = await res.text();
      let body = null;
      try { body = JSON.parse(text); } catch (err) { body = null; }
      return res.ok && body && body.ok ? { ok: true } : { ok: false, why: (body && body.why) || `${res.status} ${text.trim()}` };
    } catch (err) { return { ok: false, why: tl('live.offline') }; }
  },
  /* The server room (56-server-room.js): the room's model, read when its door is pressed (POST /api/infra-docs, the
     room's id and the press's seq; the boundary's §5.2 reply, ok or {ok: false, reason, message, short}). */
  async infraDocs(project, seq) {
    try {
      const res = await fetch('/api/infra-docs', { method: 'POST', cache: 'no-store', credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json', 'X-Jui-Viz-Token': NET.token }, body: JSON.stringify({ projectId: project, seq }) });
      let body = null;
      try { body = await res.json(); } catch (err) { body = null; }
      if (body && typeof body === 'object' && typeof body.ok === 'boolean') return body;
      return { ok: false, seq, reason: 'unreadable', message: `HTTP ${res.status}`, short: tl('live.read.failed', { status: res.status }) };
    } catch (err) { return { ok: false, seq, reason: 'unreadable', message: tl('live.offline'), short: tl('live.offline') }; }
  },
  /* The cost simulator (56-server-cost.js): POST /api/infra-cost with the room and {seq, scenario, date, by, account (null: the server's default)}; the
     server's shapes, or {ok: false, reason, message}. */
  async infraCost(project, ask) {
    try {
      const res = await fetch('/api/infra-cost', { method: 'POST', cache: 'no-store', credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json', 'X-Jui-Viz-Token': NET.token }, body: JSON.stringify({ projectId: project, ...ask }) });
      let body = null;
      try { body = await res.json(); } catch (err) { body = null; }
      if (body && typeof body === 'object' && typeof body.ok === 'boolean') return body;
      return { ok: false, reason: 'unreadable', message: `HTTP ${res.status}` };
    } catch (err) { return { ok: false, reason: 'unreadable', message: tl('live.offline') }; }
  },
  /* One icon the room's settings name (POST /api/infra-icon): a Blob, or null (the neutral shape stays). */
  async infraIcon(project, key) {
    try {
      const res = await fetch('/api/infra-icon', { method: 'POST', cache: 'no-store', credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json', 'X-Jui-Viz-Token': NET.token }, body: JSON.stringify({ projectId: project, key }) });
      return res.ok ? await res.blob() : null;
    } catch (err) { return null; }
  },
  /* The 応答の履歴 tab (55-history.js): one robot's last turns, read by the server when asked. */
  // opts (2.3.12): { before } the items before that byte (「もっと前を読む」), { stop } from that byte to the end
  specDiff(body) { return netRequest('spec.diff', body); },   // a worktree's spec beside its base (50-spec-diff.js, 2.3.23)
  specDiffList(body) { return netRequest('spec.diffList', body); },   // a worktree's whole list against its base
  history(label, opts) { return netRequest('history.get', { agentId: (DEF[label] && DEF[label].realId) || label, ...(opts || {}) }); },
  /* One picture of that history (2.3.4): the robot and the picture's place, under the same checks as a prompt
     (server.prompt_checks). The bytes come back as a Blob; nothing is kept but what the page holds. */
  async historyImage(label, ref) {
    try {
      const res = await fetch('/api/history-image', {
        method: 'POST', cache: 'no-store', credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json', 'X-Jui-Viz-Token': NET.token },
        body: JSON.stringify({ agentId: (DEF[label] && DEF[label].realId) || label, off: ref.off, n: ref.n }),
      });
      if (!res.ok) return { ok: false, status: res.status, error: (await res.text()).trim() };
      return { ok: true, blob: await res.blob() };
    } catch (err) { return { ok: false, status: 0, error: tl('live.offline') }; }
  },
  /* The skill spirits the page may show (POST /api/spirits, under the prompt's checks): the models the checks pass. */
  async spirits() {
    try {
      const res = await fetch('/api/spirits', { method: 'POST', cache: 'no-store', credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json', 'X-Jui-Viz-Token': NET.token }, body: '{}' });
      if (!res.ok) return { ok: false, status: res.status, error: (await res.text()).trim() };
      return { ok: true, models: (await res.json()).models || [] };
    } catch (err) { return { ok: false, status: 0, error: tl('live.offline') }; }
  },
  /* One .glb of a listed spirit (POST /api/spirit-file: its id and file name, never a path), as an ArrayBuffer. */
  async spiritFile(id, file) {
    try {
      const res = await fetch('/api/spirit-file', { method: 'POST', cache: 'no-store', credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json', 'X-Jui-Viz-Token': NET.token }, body: JSON.stringify({ id, file }) });
      if (!res.ok) return { ok: false, status: res.status, error: (await res.text()).trim() };
      return { ok: true, buffer: await res.arrayBuffer() };
    } catch (err) { return { ok: false, status: 0, error: tl('live.offline') }; }
  },
  /* One attached image of a prompt from this page (POST /api/attach-image: the session and the id from the prompt's
     line, under the prompt's checks). The bytes come back as a Blob; { gone: true } when the kept file is gone. */
  async attachImage(ref) {
    try {
      const res = await fetch('/api/attach-image', {
        method: 'POST', cache: 'no-store', credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json', 'X-Jui-Viz-Token': NET.token },
        body: JSON.stringify({ sessionId: ref.sessionId, id: ref.id, ext: ref.ext }),
      });
      if (!res.ok) return { ok: false, status: res.status, error: (await res.text()).trim() };
      if ((res.headers.get('Content-Type') || '').startsWith('application/json')) return { ok: false, gone: !!(await res.json()).gone, status: 200 };
      return { ok: true, blob: await res.blob() };
    } catch (err) { return { ok: false, status: 0, error: tl('live.offline') }; }
  },
  /* One picture the robot's session sent with SendUserFile (POST /api/history-file: the robot, the call's record and
     the file's place in it — never a path; under the prompt's checks). A Blob — the copy taken when it was sent, else its
     file —, or { gone: true, why } when neither is there (why: the copy could not be taken; viz/sent_copies.py). */
  async historyFile(label, ref) {
    try {
      const res = await fetch('/api/history-file', {
        method: 'POST', cache: 'no-store', credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json', 'X-Jui-Viz-Token': NET.token },
        body: JSON.stringify({ agentId: (DEF[label] && DEF[label].realId) || label, off: ref.off, n: ref.n }),
      });
      if (!res.ok) return { ok: false, status: res.status, error: (await res.text()).trim() };
      if ((res.headers.get('Content-Type') || '').startsWith('application/json')) { const j = await res.json(); return { ok: false, gone: !!j.gone, why: typeof j.why === 'string' ? j.why : '', status: 200 }; }
      return { ok: true, blob: await res.blob() };
    } catch (err) { return { ok: false, status: 0, error: tl('live.offline') }; }
  },
  /* A file of the history shown in Finder (POST /api/reveal-file, 2.3.12): { sent: { off, n } } or { tool: { off, id } }
     of the robot's transcript, or { attach: { sessionId, id, ext } } — never a path; under the prompt's checks. { ok }, { gone: true }
     when the file is no longer there, or { ok: false, status, error }. */
  async revealFile(label, ref) {
    try {
      const agentId = (DEF[label] && DEF[label].realId) || label;
      const body = ref.attach ? { attach: { sessionId: ref.attach.sessionId, id: ref.attach.id, ext: ref.attach.ext } }
        : ref.tool ? { tool: { agentId, off: ref.tool.off, id: ref.tool.id } } : { sent: { agentId, off: ref.sent.off, n: ref.sent.n } };
      const res = await fetch('/api/reveal-file', {
        method: 'POST', cache: 'no-store', credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json', 'X-Jui-Viz-Token': NET.token }, body: JSON.stringify(body),
      });
      if (!res.ok) return { ok: false, status: res.status, error: (await res.text()).trim() };
      const got = await res.json();
      return got.gone ? { ok: false, gone: true, status: 200 } : { ok: !!got.ok, status: 200, error: got.ok ? '' : tl('live.finder.failed') };
    } catch (err) { return { ok: false, status: 0, error: tl('live.offline') }; }
  },
  /* The data server's documents (2.3.5): the room's API and DB specifications, read by the server now (POST
     /api/data-docs under the prompt's checks; the room's id only, never a path). Resolves { ok, doc } or { ok, error }. */
  async dataDocs(projectId) {
    try {
      const res = await fetch('/api/data-docs', {
        method: 'POST', cache: 'no-store', credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json', 'X-Jui-Viz-Token': NET.token },
        body: JSON.stringify({ projectId }),
      });
      if (!res.ok) return { ok: false, status: res.status, error: (await res.text()).trim() };
      const doc = await res.json();
      const arr = (v) => (Array.isArray(v) ? v : []);
      return { ok: true, doc: { api: arr(doc.api), db: arr(doc.db), skipped: Number(doc.skipped) || 0 } };
    } catch (err) { return { ok: false, status: 0, error: tl('live.offline') }; }
  },
  /* The near weather's switch (10-18): { on, lat, lon } with the position already rounded (40-scene.js). */
  setWeather(body) { return netRequest('weather.set', body); },
  /* question.answer (10-18): picks are question text -> { labels, other }; the card says "sent" when the slice does. */
  /* question.hold while someone answers (the hook waits a little longer); question.release: answer in the terminal */
  holdQuestion(id) { netRequest('question.hold', { questionId: id }); },
  releaseQuestion(id) {
    netRequest('question.release', { questionId: id }).then((ack) => showToast(ack.ok ? tl('live.q.released') : tl('live.q.release.failed', { error: ack.error || tl('live.unknown') })));
  },
  answerQuestion(id, picks) {
    netRequest('question.answer', { questionId: id, answers: picks }).then((ack) => showToast(ack.ok
      ? tl('live.q.sent') : tl('live.send.failed', { error: ack.error || tl('live.unknown') })));
  },
  /* A card of a call stopped by auto mode (51-denials.js): 'approve' (the server sends the card's own words to its
     session) or 'dismiss'. The checks of /api/prompt. Resolves { ok } or { ok: false, status, error }. */
  async denial(id, what) {
    try {
      const res = await fetch('/api/denial', {
        method: 'POST', cache: 'no-store', credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json', 'X-Jui-Viz-Token': NET.token },
        body: JSON.stringify({ id, do: what }),
      });
      return res.ok ? { ok: true } : { ok: false, status: res.status, error: (await res.text()).trim() };
    } catch (err) { return { ok: false, status: 0, error: tl('live.offline') }; }
  },
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
  // what a done spec has passed (the server's tests.needed: its cases, and as many as its branches — requester 10-23
  // 「分岐も全部で完了」): the 分岐 tab, the panel's and the list's words all count against it, as the bucket does
  const needed = Number.isFinite(tests.needed) ? tests.needed : tests.total;
  const share = impl.total > 0 ? Math.min(1, impl.done / impl.total) : 0;
  // Only what the server measured (jsonui_project.impl): the structure is the Layout's tree, so it is implemented
  // exactly when the Layout exists (or, when the spec lists components, as many as the Layout has). States, data,
  // actions and transitions are not measured one by one, so they get no ✓ / ○ (unmeasured); 分岐 comes from tests.
  const measure = { related: impl.related || { total: 0, done: 0 }, layout: impl.layout === undefined ? null : impl.layout, components: impl.components || null };
  const implN = totals.map(() => 0);
  implN[1] = measure.components ? Math.min(totals[1], measure.components.done) : measure.layout ? totals[1] : 0;
  implN[6] = Math.min(needed, tests.passed);
  const unmeasured = [false, false, true, true, true, true, false];
  if (!totals[6] && tests.total) totals[6] = tests.total;
  const implPhase = impl.done > 0 || tests.total > 0;
  const writingIdx = SPEC_KEYS.findIndex((k) => (secs[k] || {}).state === 'writing');
  const by = labelOf(x.by);
  const pctImpl = impl.total ? pct(share) : 0;
  const status = tests.running ? { kind: 'test', text: tl('live.spec.testing', { passed: tests.passed, total: needed }) }
    : writingIdx >= 0 ? { kind: 'write', text: tl('live.spec.writing', { pct: pct(written.reduce((a, b) => a + b, 0) / 7) }) }
      : x.bucket === 'done' ? { kind: 'done', text: tl('live.spec.done') }
        : x.bucket === 'todo' ? { kind: 'idle', text: tl('live.spec.todo') }
          : impl.total && impl.done >= impl.total ? { kind: 'impl-done', text: tests.total ? tl('live.spec.impl.tests', { passed: tests.passed, total: needed }) : tl('live.spec.impl.waiting') }
            : impl.done > 0 ? { kind: by ? 'impl' : 'paused', text: tl('live.spec.impl', { pct: pctImpl }) }
              : written.every((w) => w >= 1) ? { kind: 'written', text: tl('live.spec.written') } : { kind: 'paused', text: tl('live.spec.writing.paused', { pct: pct(written.reduce((a, b) => a + b, 0) / 7) }) };
  // maybeStale: the spec or its layout changed after the newest result (mtime, which a git checkout also moves).
  const note = tl('live.note.impl', { done: impl.done, total: impl.total })
    + (tests.total ? tl('live.note.tests', { passed: tests.passed, total: tests.total }) + (tests.failed ? tl('live.note.failed', { n: tests.failed }) : '')
      + (tests.maybeStale ? tl('live.note.stale') : '') : tl('live.note.notests'));
  const prev = LIVE.specRows[x.id];
  const row = {
    testsNeeded: needed,
    id: x.id, screen: String(x.name || ''), name: String(x.name || ''), project: x.projectId, file: String(x.file || ''),
    app: String(x.app || ''), specDir: String(x.specDir || ''),   // the app inside the room that holds the spec
    // the checkout it is read from, when the room shows a worktree of its app: {branch, worktree?} (a worktree's own row has worktree)
    checkout: x.checkout && typeof x.checkout.branch === 'string'
      ? { branch: x.checkout.branch, worktree: typeof x.checkout.worktree === 'string' ? x.checkout.worktree : '' } : null,
    advancedAt: Number.isFinite(x.advancedAt) ? x.advancedAt : 0,   // when it last moved on: the lists' order (specNewer)
    advancedBy: typeof x.advancedBy === 'string' ? x.advancedBy : '',   // what moved it: spec / layout / test (specWhen)
    doc: prev && prev.docAt === x.updatedAt ? prev.doc : (prev ? prev.doc : null), docAt: prev ? prev.docAt : null, updatedAt: x.updatedAt,
    totals, related: prev && prev.doc ? (prev.doc.related || []) : [], written, implN, implPhase, writingIdx, measure, unmeasured,
    implIdx: by && writingIdx < 0 && x.bucket === 'live' && !tests.running && implN[1] < totals[1] ? 1 : -1,
    testIdx: tests.running ? 6 : -1, by, relatedNow: -1, status, note, bucket: ['live', 'partial', 'todo', 'done'].includes(x.bucket) ? x.bucket : 'partial',
  };
  if (row.implIdx === 0) row.implIdx = -1;
  LIVE.specRows[x.id] = row;
  return row;
}
function rebuildSpecs() {
  const list = Array.isArray(LIVE.slices.specs) ? LIVE.slices.specs : [];
  const rows = list.filter((x) => x && x.id && PROJECT[x.projectId]).map(liveSpecRow);
  rows.sort((a, b) => (PROJECT[a.project].order - PROJECT[b.project].order) || a.file.localeCompare(b.file) || a.id.localeCompare(b.id));
  // the spec open on the whiteboard is kept by its id: a row that comes or goes (a worktree shown or gone) moves the
  // others' places, and a gone spec leaves the overview (ticket 2026-10-23-jui-viz-spec-board-shows-worktree-in-progress)
  const openId = typeof wb !== 'undefined' && wb.idx >= 0 && SPECS[wb.idx] ? SPECS[wb.idx].id : null;
  SPECS.splice(0, SPECS.length, ...rows);
  for (const k of Object.keys(SPEC_INDEX)) delete SPEC_INDEX[k];
  SPECS.forEach((x, i) => { SPEC_INDEX[x.id] = i; });
  if (openId !== null) wb.idx = openId in SPEC_INDEX ? SPEC_INDEX[openId] : -1;
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
  netRequest('spec.sheet', { specId: row.id }).then((ack) => { if (!ack.ok) LIVE.sheetFailed[row.id] = ack.error || tl('live.unknown'); });
}
/* A prose field as the server sent it: {markdown} (from a texts file, drawn as Markdown by the sheet) kept, else text. */
function sheetProse(v) { return v && typeof v === 'object' && typeof v.markdown === 'string' ? { markdown: v.markdown } : String(v ?? ''); }
function liveSheet(msg) {
  const row = LIVE.specRows[msg.specId];
  if (!row || !msg.cards || typeof msg.cards !== 'object') return;
  const d = msg.cards;
  const arr = (v) => (Array.isArray(v) ? v : []);
  const meta = d.metadata && typeof d.metadata === 'object' ? d.metadata : {};
  row.doc = {
    metadata: { name: String(meta.name || ''), displayName: String(meta.displayName || row.name), description: sheetProse(meta.description), platforms: arr(meta.platforms).map(String), layoutFile: String(meta.layoutFile || ''), createdAt: String(meta.createdAt || '') },
    components: arr(d.components), layoutChildren: arr(d.layoutChildren), uiVariables: arr(d.uiVariables), eventHandlers: arr(d.eventHandlers),
    vmMethods: arr(d.vmMethods), vmVars: arr(d.vmVars), repositories: arr(d.repositories), apis: arr(d.apis),
    userActions: arr(d.userActions), transitions: arr(d.transitions), branches: arr(d.branches), related: arr(d.related),
    flowMermaid: typeof d.flowMermaid === 'string' ? d.flowMermaid : '',   // the spec page's data flow diagram (2.3.5)
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
      source: String(x.source || 'task'), turn: Number(x.turn) || 0, harness: typeof x.harness === 'string' ? x.harness : '', waiting: !!x.waiting, waitingFor: x.waitingFor === 'question' ? 'question' : '', background: !!x.background, failed: !!x.failed,
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
    // a turn waits while its session waits for a permission
    const col = status === 'completed' ? 'done' : status === 'in_progress' ? (x.waiting ? 'wait' : 'doing') : blocked ? 'wait' : 'todo';
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
  return liveRunView(pickFrom.find((r) => r.status === 'running') || [...pickFrom].sort((a, b) => (b.startedAt || 0) - (a.startedAt || 0))[0]);
}
/* What decided a finished run's head (ingest robots.test_verdict, 2.3.10): shown as the status's tooltip. */
const VERDICT_FROM_JA = {
  runner: tl('live.verdict.runner'),
  xcode: tl('live.verdict.xcode'),
  summary: tl('live.verdict.summary'),
  exit: tl('live.verdict.exit'),
};
/* One run as the panels show it (the test pane, and a robot's card). */
function liveRunView(run) {
  const cases = Array.isArray(run.cases) ? run.cases : [];
  const rows = cases.map((c) => ({ name: String(c.name || ''), branch: '', status: CASE_STATUS[c.status] || 'pending', attempt: 1, step: c.status === 'running' ? tl('live.run.case') : '' }));
  const passed = rows.filter((r) => r.status === 'passed').length;
  const failed = rows.filter((r) => r.status === 'failed').length;
  const runningIdx = rows.findIndex((r) => r.status === 'running');
  const dev = (Array.isArray(LIVE.slices.devices) ? LIVE.slices.devices : []).find((d) => d && d.id === run.deviceId);
  const statusText = run.status === 'running' ? tl('live.run.running') + (rows.length ? tl('live.run.passed', { passed, all: rows.length }) : '')
    : run.summary ? `${run.status === 'passed' ? tl('live.run.pass') : tl('live.run.fail')} · ${run.summary}` : run.status === 'passed' ? tl('live.run.pass') : tl('live.run.fail');
  return {
    rows, passed, failed, runningIdx, retrying: false, active: run.status === 'running', statusText,
    file: String(run.file || run.command || ''), device: dev ? String(dev.name) : ({ ios: 'iOS', android: 'Android', web: 'Web' }[run.platform] || ''),
    who: labelOf(run.agentId), project: run.projectId, runStatus: run.status, command: String(run.command || ''),
    id: String(run.id), startedAt: Number(run.startedAt) || 0, savedAt: Number(run.savedAt) || 0,
    verdictWhy: run.status === 'running' ? '' : VERDICT_FROM_JA[run.verdictFrom] || '',
  };
}
/* A robot's own runs for its card (requester, 10-18: "ロボットのパネルにもテストの経過表示できない？"): only runs
   that robot started — the one running first, then the latest — at most ROBOT_RUNS_MAX. */
const ROBOT_RUNS_MAX = 3;
function robotRuns(label) {
  const runs = (Array.isArray(LIVE.slices.tests) ? LIVE.slices.tests : []).filter((r) => r && r.id && labelOf(r.agentId) === label);
  runs.sort((a, b) => (b.status === 'running') - (a.status === 'running') || (b.startedAt || 0) - (a.startedAt || 0));
  return runs.slice(0, ROBOT_RUNS_MAX).map(liveRunView);
}

/* ---------- permission prompts (plan 04 Permission, plan 08 §4 → the demo's perm rows) ---------- */
const PERMS_LIVE = [];
const PERM_STATUS = { pending: 'pending', sent: 'sent', allow: 'allow', deny: 'deny', answered_in_terminal: 'terminal', expired: 'expired' };
/* The fields the decision is about, exactly as the server got them (card.exact: command, file_path, old_string,
   new_string … uncut up to 20,000 characters, whitespace kept; Write's content as its first 2,000). The card shows
   these and nothing else: a summary or the 2,000-character preview once hid the tail of a long command
   ("…; rm -rf ~/tail-hidden") and folded runs of spaces (the independent review, 10-18). */
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
  notifyWaiting('perm', PERMS_LIVE);   // 2.3.6
}

/* ---------- rooms: size by robot count, left to right by order, a new row past 24 (plan 07 §4) ---------- */
// Floor and walls only: the boards, desks and robots keep their scale, so a bigger room is more space around them.
// The desks stand where a seeded draw puts them (requester, 10-18), which needs more floor than a grid did.
function roomSize(n) { return n <= 6 ? [11, 8.5] : n <= 10 ? [13, 9.5] : [15, 10.5]; }

/* ---------- doors (requester, 10-18): robots walk through doors, never through a wall ----------
   A room has walls at its back and on its left (the front and the right are cut away so the view can see in).
   - left door: in the left wall, between the cork board and the test easel, to the room on its left;
   - back door: in the back wall, near the right, to the room behind it;
   - entrance: at the front, near the right, when no room is in front of it (the corridor runs along the front).
   A door is DOOR_W wide; robots pass through its middle. */
const DOOR_W = 1.2, DOOR_H = 2.3, WALL_T = 0.16;
const doorAt = (r) => ({ leftZ: r.z1 - 2.4, backX: r.x1 - 1.4, frontX: r.x1 - 1.4 });
const roomById = (id) => (id && PROJECT[id] && PROJECT[id].shown ? PROJECT[id] : null);
/* The wall pieces of the shown rooms as rectangles on the floor (x0, x1, z0, z1), door gaps cut out. */
function liveWalls() {
  const out = [];
  for (const r of ROOMS) {
    if (!r.shown) continue;
    const d = doorAt(r), half = DOOR_W / 2;
    const back = [r.x0 - WALL_T, r.x1], left = [r.z0, r.z1];
    const cut = (span, gap) => (gap === null ? [span] : [[span[0], gap - half], [gap + half, span[1]]]);
    for (const [a, b] of cut(back, r.doors && r.doors.back ? d.backX : null)) out.push({ room: r.id, side: 'back', x0: a, x1: b, z0: r.z0 - WALL_T, z1: r.z0 });
    for (const [a, b] of cut(left, r.doors && r.doors.left ? d.leftZ : null)) out.push({ room: r.id, side: 'left', x0: r.x0 - WALL_T, x1: r.x0, z0: a, z1: b });
  }
  return out;
}
const corridorZ = () => Math.max(...ROOMS.filter((r) => r.shown).map((r) => r.z1), 0) + 1.2;
/* The rooms a robot can walk to from a room in one step, with the points it walks through (inside the first room
   → inside the next, through the door's middle). 'OUT' is the corridor. */
function doorHops(id) {
  const hops = [];
  if (id === 'OUT') {
    const c = corridorZ();
    for (const r of ROOMS) if (r.shown && r.doors && r.doors.front) { const x = doorAt(r).frontX; hops.push([r.id, [[x, c], [x, r.z1 + 0.9], [x, r.z1 - 0.7]]]); }
    return hops;
  }
  const r = roomById(id);
  if (!r || !r.doors) return hops;
  const d = doorAt(r);
  const L = roomById(r.doors.left), B = roomById(r.doors.back);
  if (L) hops.push([L.id, [[r.x0 + 0.7, d.leftZ], [L.x1 - 0.7, d.leftZ]]]);
  if (B) hops.push([B.id, [[d.backX, r.z0 + 0.7], [d.backX, B.z1 - 0.7]]]);
  for (const o of ROOMS) {
    if (!o.shown || !o.doors) continue;
    const od = doorAt(o);
    if (o.doors.left === r.id) hops.push([o.id, [[r.x1 - 0.7, od.leftZ], [o.x0 + 0.7, od.leftZ]]]);
    if (o.doors.back === r.id) hops.push([o.id, [[od.backX, r.z1 - 0.7], [od.backX, o.z0 + 0.7]]]);
  }
  if (r.doors.front) { const c = corridorZ(); hops.push(['OUT', [[d.frontX, r.z1 - 0.7], [d.frontX, r.z1 + 0.9], [d.frontX, c]]]); }
  return hops;
}
/* The points from one room to another (null: the corridor), the fewest doors first. */
function liveRoute(fromId, toId) {
  const from = roomById(fromId) ? fromId : 'OUT', to = roomById(toId) ? toId : 'OUT';
  if (from === to) return [];
  const prev = { [from]: null }, queue = [from];
  while (queue.length) {
    const id = queue.shift();
    if (id === to) break;
    for (const [next, pts] of doorHops(id)) if (!(next in prev)) { prev[next] = [id, pts]; queue.push(next); }
  }
  if (!(to in prev)) return [];
  const legs = [];
  for (let id = to; prev[id]; id = prev[id][0]) legs.unshift(prev[id][1]);
  return legs.flat();
}
/* The room a point is in (null: the corridor or a gap). */
const roomAtPoint = (p) => (ROOMS.find((r) => r.shown && p[0] > r.x0 && p[0] < r.x1 && p[1] > r.z0 && p[1] < r.z1) || {}).id || null;

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
  const slot = {};
  placed.forEach(([r, px, pz, w, d], k) => {
    r.x0 = +(px + ox).toFixed(3); r.x1 = +(r.x0 + w).toFixed(3); r.z0 = +(pz + oz).toFixed(3); r.z1 = +(r.z0 + d).toFixed(3);
    r.floor = FLOORS[r.order % FLOORS.length]; r.back = 3.9; r.left = 3.9;
    r.col = k % FLOOR_COLS; r.row = Math.floor(k / FLOOR_COLS);
    slot[`${r.row},${r.col}`] = r.id;
  });
  const solo = soloRoomId();
  for (const [r] of placed) {
    r.baseW = w; r.baseD = d;
    r.doors = { left: slot[`${r.row},${r.col - 1}`] || null, back: slot[`${r.row - 1},${r.col}`] || null, front: !slot[`${r.row + 1},${r.col}`] };
    if (solo && r.id !== solo) { r.shown = false; r.x0 = r.x1 = r.z0 = r.z1 = undefined; continue; }
    if (solo) {
      // the room picked, alone and SOLO_GROW times as wide and deep: more floor, the same desks spread over it
      // (requester, 10-18: "広くしてあげてほしい — ただの拡大だと窮屈に見える"); in from the corridor at its front
      const sw = +(w * SOLO_GROW).toFixed(3), sd = +(d * SOLO_GROW).toFixed(3);
      r.x0 = -sw / 2; r.x1 = sw / 2; r.z0 = -sd / 2; r.z1 = sd / 2;
      r.doors.front = true;
    }
    r.geo = `${r.x0},${r.x1},${r.z0},${r.z1},${r.big ? 'big' : ''},${r.tests ? 'tests' : ''},${r.doors.left ? 'L' : ''}${r.doors.back ? 'B' : ''}${r.doors.front ? 'F' : ''}${solo ? ',solo' : ''}`;
  }
}

/* One room at a time (requester, 10-18): the project picked in the view, when its room is on the floor shown. */
const SOLO_GROW = 1.6;
function soloRoomId() {
  const id = typeof UI !== 'undefined' ? UI.project : 'all';
  return id !== 'all' && LIVE.shown.includes(id) ? id : null;
}
function liveRelayout() {
  layoutRooms();
  placeRobots();
  SOURCE.layoutRev += 1;
  LIVE.model = null;
}

/* Eight hours into its session a main robot gets tired (requester, 10-18). The start is the session's own
   (sessions[].since, from its transcript); a session without one is never tired — startedAt is when the server
   first saw it, not when it began. */
/* Phone calls (SendMessage, 10-18): the server's calls slice, per robot label. A robot in two calls shows the newest
   (the slice is sorted by start). The peer is the other robot's label, or null when it is not a robot here. */
function callsByLabel() {
  const list = Array.isArray(LIVE.slices.calls) ? LIVE.slices.calls : [];
  const out = {};
  for (const c of list) {
    if (!c || typeof c.state !== 'string') continue;
    const from = c.from ? LIVE.labelOfReal[c.from] : null, to = c.toSession ? LIVE.labelOfReal[c.toSession] : null;
    if (from) out[from] = { role: 'caller', state: c.state, peer: to };
    if (to) out[to] = { role: 'callee', state: c.state, peer: from };
  }
  return out;
}
// the causes of heavy work (tokens / tool / subagents), [] when none: the robot shows one look per cause (2.3.6)
const heavyOf = (label) => { const s = SESSIONS.find((x) => x.id === SESSION_OF[label]); return s && Array.isArray(s.heavy) ? s.heavy : []; };
/* What the robot card says under 今やっていること: hours of a tired session, the reasons of heavy work. */
function robotCondition(label) {
  const s = SESSIONS.find((x) => x.id === SESSION_OF[label]);
  if (!s) return { tired: false, hours: null, heavy: null };
  const main = DEF[label] && DEF[label].kind === 'main';
  const hours = s.since ? (vizNow() - s.since) / 3600000 : null;
  return { tired: main && isTired(s.since, vizNow()), hours, heavy: s.heavy && s.heavy.length ? { reasons: s.heavy, ...(s.heavyInfo || {}) } : null };
}
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

/* ---------- seats: a robot keeps its desk; desks stand where a seeded draw puts them (requester, 10-18) ----------
   - The draw is seeded by the robot's server id (its session's or its agent's) and the room: the same robot in the
     same room draws the same spots, so a reload puts the desks back where they were.
   - A desk takes the first drawn spot that keeps clear of the other desks and of the aisles
     (the front, where the doors are, and the right, where the back door and the entrance are) — SEAT.gaps[0]
     between desks while there is room, the last of SEAT.gaps when the room fills up. A subagent takes,
     of the spots that are clear, the one nearest its parent's desk.
   - Taken desks never move while the page is open: a desk is kept in room coordinates (from the back-left corner),
     so a room that grows or moves to another slot keeps its desks; robots that come and go do not move the others.
   - The page also remembers each desk in this browser (DESK_MEM): after a reload a robot takes its remembered desk
     when it is still clear, so robots that have left since (and drew earlier) do not shift the others.
   - No clear spot: the robot stands along the front. */
/* The one-room view's desks keep clear of the room's own corners (requester, 10-19: the smoking booth top left, the
   vending machine beside the water server): SEAT_SOLO.left more on the left, SEAT_SOLO.right more on the right. */
const SEAT_SOLO = { left: 2.1, right: 0.8 };
const SEAT = { tries: 600, field: [16, 12], gaps: [1.1, 0.3], foot: { l: 0.6, r: 0.6, b: 0.45, f: 0.95 }, left: 0.9, back: 1.1, aisleR: 2.4, aisleF: 1.7 };
function hash32(str) {
  let h = 0x811c9dc5;
  for (let i = 0; i < str.length; i++) { h ^= str.charCodeAt(i); h = Math.imul(h, 0x01000193) >>> 0; }
  return h >>> 0;
}
function seededRandom(seed) {
  let a = seed >>> 0;
  return () => { a = (a + 0x6d2b79f5) >>> 0; let t = Math.imul(a ^ (a >>> 15), 1 | a); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; };
}
/* Where a desk may stand in a room, in room coordinates: the robot's spot, with its desk in front of it. */
// Desks are drawn in the room's floor-view size (baseW × baseD); the wider room of the one-room view spreads them
// over its own area (seatPos), so a desk is the same desk in both views.
function seatArea(w, d) {
  const F = SEAT.foot;
  return { x0: SEAT.left + F.l, x1: w - SEAT.aisleR - F.r, z0: SEAT.back + F.b, z1: d - SEAT.aisleF - F.f };
}
const seatsClear = (a, b, gap = SEAT.gaps[SEAT.gaps.length - 1]) => Math.abs(a[0] - b[0]) >= SEAT.foot.l + SEAT.foot.r + gap || Math.abs(a[1] - b[1]) >= SEAT.foot.b + SEAT.foot.f + gap;
function freeSeat(label) { delete LIVE.seatOf[label]; }
const DESK_MEM = { map: null, max: 400 };
function deskMemory() {
  if (!DESK_MEM.map) { try { DESK_MEM.map = new Map(Object.entries(JSON.parse(readPref('desks', '{}')) || {})); } catch (err) { DESK_MEM.map = new Map(); } }
  return DESK_MEM.map;
}
function rememberDesk(key, p) {
  const m = deskMemory();
  m.delete(key); m.set(key, p);   // newest last; the oldest go past DESK_MEM.max
  while (m.size > DESK_MEM.max) m.delete(m.keys().next().value);
  writePref('desks', JSON.stringify(Object.fromEntries(m)));
}
function drawSeat(def, room, nearLocal) {
  const area = seatArea(room.baseW, room.baseD);
  const taken = Object.entries(LIVE.seatOf).filter(([id, s]) => id !== def.id && s.room === room.id && !s.standing).map(([, s]) => [s.dx, s.dz]);
  for (const gap of SEAT.gaps) {   // roomy while the room has space, closer when it fills up
    const rnd = seededRandom(hash32(`${def.realId || def.id}|${room.id}`));
    let best = null, bestD = Infinity;
    for (let i = 0; i < SEAT.tries; i++) {
      // spots over a fixed field, not over the room: the same spot whatever the room's size (rooms grow with robots)
      const p = [+(rnd() * SEAT.field[0]).toFixed(2), +(rnd() * SEAT.field[1]).toFixed(2)];
      if (p[0] < area.x0 || p[0] > area.x1 || p[1] < area.z0 || p[1] > area.z1 || !taken.every((q) => seatsClear(p, q, gap))) continue;
      if (!nearLocal) return p;
      const dd = Math.hypot(p[0] - nearLocal[0], p[1] - nearLocal[1]);
      if (dd < bestD) { best = p; bestD = dd; }
    }
    if (best) return best;
  }
  return null;
}
function takeSeat(def, room) {
  const parent = def.kind === 'sub' && LIVE.seatOf[def.mainLabel];
  const near = parent && parent.room === room.id && !parent.standing ? [parent.dx, parent.dz] : null;
  const key = `${room.id}|${def.realId || def.id}`, area = seatArea(room.baseW, room.baseD);
  const taken = Object.entries(LIVE.seatOf).filter(([id, s]) => id !== def.id && s.room === room.id && !s.standing).map(([, s]) => [s.dx, s.dz]);
  const mem = deskMemory().get(key);
  const kept = Array.isArray(mem) && mem[0] >= area.x0 && mem[0] <= area.x1 && mem[1] >= area.z0 && mem[1] <= area.z1 && taken.every((q) => seatsClear(mem, q)) ? mem : null;
  const p = kept || drawSeat(def, room, near);
  if (p) { LIVE.seatOf[def.id] = { room: room.id, dx: p[0], dz: p[1], standing: false }; if (!kept) rememberDesk(key, p); return; }
  const used = new Set(Object.values(LIVE.seatOf).filter((s) => s.room === room.id && s.standing).map((s) => s.k));
  let k = 0; while (used.has(k)) k += 1;
  LIVE.seatOf[def.id] = { room: room.id, standing: true, k };
}
function seatPos(room, s) {
  if (!s.standing) {
    const a = seatArea(room.baseW, room.baseD), b = seatArea(room.x1 - room.x0, room.z1 - room.z0);
    // the one-room view keeps the back-left corner for the smoking booth and a little more of the right aisle for the
    // vending machine's customer (SEAT_SOLO, 40-scene.js propsPlace): the desks spread over the rest
    if (room.id === soloRoomId()) { b.x0 += SEAT_SOLO.left; b.x1 -= SEAT_SOLO.right; }
    const map = (v, a0, a1, b0, b1) => (a1 > a0 ? b0 + ((v - a0) * (b1 - b0)) / (a1 - a0) : v);
    return { pos: [+(room.x0 + map(s.dx, a.x0, a.x1, b.x0, b.x1)).toFixed(3), +(room.z0 + map(s.dz, a.z0, a.z1, b.z0, b.z1)).toFixed(3)], ry: 0, standing: false };
  }
  const along = room.x0 + 0.9 + s.k * 0.95;   // standing along the front, then down the right
  return along < room.x1 - SEAT.aisleR ? { pos: [along, room.z1 - 0.45], ry: Math.PI, standing: true }
    : { pos: [room.x1 - 0.45, room.z1 - 2.2 - (s.k - Math.floor((room.x1 - room.x0 - SEAT.aisleR - 0.9) / 0.95)) * 0.95], ry: -Math.PI / 2, standing: true };
}
function placeRobots() {
  // A robot in another room than its desk gets a new one there. Robots draw in the order they came into their
  // room (then the server's order), the same order live and after a reload.
  const order = ROBOT_DEFS.map((d, i) => [d, i]).sort((a, b) => (a[0].inRoomAt || 0) - (b[0].inRoomAt || 0) || a[1] - b[1]).map(([d]) => d);
  for (const def of order) {
    if (LIVE.leaving[def.id]) continue;
    const room = PROJECT[def.room];
    const s = LIVE.seatOf[def.id];
    if (!room) { freeSeat(def.id); def.pos = null; continue; }
    if (!room.shown) { def.pos = null; continue; }   // on another floor or out of the one-room view: it keeps its desk
    if (s && s.room !== room.id) freeSeat(def.id);
    if (!LIVE.seatOf[def.id]) takeSeat(def, room);
    const p = seatPos(room, LIVE.seatOf[def.id]);
    def.pos = p.pos; def.ry = p.ry; def.standing = p.standing;
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
    // its API / DB specifications, counted by the server (2.3.5): the data server's rack stands there when either is above 0
    r.dataDocs = p.dataDocs && typeof p.dataDocs === 'object' ? { api: Number(p.dataDocs.api) || 0, db: Number(p.dataDocs.db) || 0 } : { api: 0, db: 0 };
    // the server room's door: how many model files the room has (infra_docs.counts); the model is read on the door only
    r.infraDocs = p.infraDocs && typeof p.infraDocs === 'object' ? { files: Number(p.infraDocs.files) || 0, dir: String(p.infraDocs.dir || '') } : { files: 0, dir: '' };
    return r;
  });
  ROOMS.splice(0, ROOMS.length, ...next);
  for (const k of Object.keys(PROJECT)) delete PROJECT[k];
  for (const r of ROOMS) PROJECT[r.id] = r;
}
function sessionHead(a, sess) { return tl('live.session.head', { id: String((sess && sess.id) || a.sessionId || '').slice(0, 4) }); }
function displayName(a, sess) {
  if (a.kind === 'main') return sessionName(sess && sess.title) || sessionHead(a, sess);
  return a.agentType ? String(a.agentType) : tl('live.subagent');
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
    const named = a.kind === 'sub' ? '' : sessionName(sess && sess.title);
    if (def.agent !== displayName(a, sess) || (def.title || '') !== named) NAMES.rev += 1;
    Object.assign(def, {
      title: named, head: a.kind === 'sub' ? '' : sessionHead(a, sess),   // the session's name (none: '') and its id's head
      realId: String(a.id || label), sessionId: String(a.sessionId || ''), kind: a.kind === 'sub' ? 'sub' : 'main',
      role: ROLE_OF(a), agent: displayName(a, sess), furnished: true, mainLabel,
      room: sess && sess.projectId ? sess.projectId : (def.room || ''),
      // when it came into its room: desks are drawn in this order, so a reload draws them the same way
      inRoomAt: Math.max(Number(a.startedAt) || 0, Number(sess && sess.roomSince) || 0),
    });
    LIVE.labelOfReal[def.realId] = label;
    if (def.kind === 'main' && sess) LIVE.labelOfReal[sess.id] = label;
    SESSION_OF[label] = mainLabel;
    if (def.kind === 'sub') AGENT_ID[label] = def.realId;
    if (gone && !isNew) { if (!LIVE.leaving[label]) LIVE.leaving[label] = { since: now }; }
    else if (!gone && isNew) { ROBOT_DEFS.push(def); def.enter = !initial; }   // robots already there sit down at once
    else if (!gone) delete LIVE.leaving[label];
    // since: when the server last set this robot (its idle began then, for play: 10-18)
    const st = { state: STATES[a.state] ? a.state : 'idle', act: String(a.act || ''), asking: a.state === 'waiting' && a.waitingOn === 'question', since: Number(a.updatedAt) || 0,
      promptAt: Number(a.promptAt) || 0, whistle: a.whistle && Number(a.whistle.until) > 0 ? { at: Number(a.whistle.at) || 0, until: Number(a.whistle.until) } : null,   // a subagent called (10-20)
      readKind: a.state === 'reading' && a.readKind === 'web' ? 'web' : null,   // the dictionary (10-20)
      // a skill in use (the spirit, 45-spirits.js): its name and when it began (the key of one skill's spirit)
      skill: a.skill && typeof a.skill.name === 'string' && Number(a.skill.since) > 0 ? { name: a.skill.name, since: Number(a.skill.since), forked: a.skill.forked === true } : null,
      git: a.git && typeof a.git === 'object' && a.git.id ? a.git : null };   // the box (2.3.4): its last push / pull
    // a deletion it ran (10-19): the page walks it to the shredder once per new at
    if (a.shred && typeof a.shred === 'object' && Number(a.shred.at) > 0) {
      st.shred = { at: Number(a.shred.at), ok: a.shred.ok === true, label: String(a.shred.label || ''), count: Math.max(1, Number(a.shred.count) || 1), folder: a.shred.folder === true };
    }
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
      relay: s.relay === true, prompt: s.prompt === true,   // prompt: its channel takes a prompt from the page (jui-viz 1.2.0+)
      launch: typeof s.launch === 'string' ? s.launch : null,   // whether the CLI hands that text over (sources/launch.py)
      // 停止 (jui-viz 1.3.0): asked and waiting for its next tool boundary, when it last stopped so, whether its --stop hook was heard
      stopAt: Number.isFinite(s.stopAt) && s.stopAt > 0 ? s.stopAt : 0, stoppedAt: Number.isFinite(s.stoppedAt) && s.stoppedAt > 0 ? s.stoppedAt : 0,
      stopHook: s.stopHook === true,
      client: ['terminal', 'vscode', 'desktop', 'other'].includes(s.client) ? s.client : 'unknown',   // 退勤: terminal only
      since: Number.isFinite(s.since) && s.since > 0 ? s.since : null,
      inputWaitAt: Number.isFinite(s.inputWaitAt) && s.inputWaitAt > 0 ? s.inputWaitAt : 0,   // 入力待ち since (53-waits.js)
      heavy: Array.isArray(s.heavy) ? s.heavy.filter((x) => typeof x === 'string') : [],   // tokens / tool / subagents
      heavyInfo: s.heavyInfo && typeof s.heavyInfo === 'object' ? { tokensPerMin: Number(s.heavyInfo.tokensPerMin) || 0, toolSec: Number(s.heavyInfo.toolSec) || 0, subagents: Number(s.heavyInfo.subagents) || 0 } : null });   // the transcript's first record; none: not guessed
  }
  SESSIONS.splice(0, SESSIONS.length, ...next);
}
function layoutSignature() {
  return JSON.stringify([ROOMS.map((r) => [r.id, r.geo || '', r.shown]), ROBOT_DEFS.map((d) => [d.id, d.role, d.room, (d.pos || []).join()])]);
}
/* ---------- questions (AskUserQuestion, 10-18): the server's cards with the asking robot's label ---------- */
const QUESTIONS = [];
function rebuildQuestions() {
  const list = Array.isArray(LIVE.slices.questions) ? LIVE.slices.questions : [];
  const rows = [];
  for (const x of list) {
    const who = x && (labelOf(x.agentId) || labelOf(x.sessionId));
    if (!who || !DEF[who] || !Array.isArray(x.questions)) continue;
    rows.push({ ...x, who, at: secOfDay(x.createdAt || Date.now()) });
  }
  QUESTIONS.splice(0, QUESTIONS.length, ...rows);
  notifyWaiting('ask', QUESTIONS);   // 2.3.6
}
/* Slices one pane reads for itself and the scene never does (the デバイス pane, 53-devices.js, reads LIVE.slices.machine
   every second): a push that carries only these is stored and nothing is rebuilt. The machine's load changes every
   5 s, and a full rebuild that often reset the robots' timed looks — the whistle, the sweat — and held a break's
   waiting trip (the e2e suites hist-wide and gitbox, red with the デバイス pane in 2.3.11's gate). */
const PAGE_ONLY_SLICES = new Set(['machine', 'cloudPrices']);
function liveApply(changed, replace) {
  if (replace) LIVE.slices = {};
  for (const [k, v] of Object.entries(changed || {})) LIVE.slices[k] = v;
  const keys = Object.keys(changed || {});
  if (!replace && keys.length && keys.every((k) => PAGE_ONLY_SLICES.has(k))) return;
  if (changed && changed.settings) notifySettingsShow(changed.settings);   // 2.3.6: the question window, as the server has it
  const before = layoutSignature();
  rebuildRooms();
  rebuildRobots(replace);
  rebuildSpecs();
  roomFlags();
  rebuildSessions();
  rebuildTasks();
  rebuildPerms();
  rebuildQuestions();
  rebuildDenials();
  layoutRooms();   // after the permissions: a room's rank comes from this round's requests
  placeRobots();
  renderUsage(vizNow());
  const server = LIVE.slices.server || {};
  const errs = Object.entries(server.sources || {}).filter(([, s]) => s && (s.error || s.state === 'error')).map(([k, s]) => `${k}: ${s.error || tl('live.error')}`);
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
function liveEvents(items, older, replay = false) {
  const add = [];
  for (const raw of items) {
    if (!older && Number(raw.seq) <= LIVE.seenSeq) continue;
    const item = liveEvent(raw);
    if (item) add.push(item);
    if (!older && item && (raw.kind === 'Stop' || raw.kind === 'StopFailure')) notifyStop(raw, item, replay);   // 2.3.6: the replay is seen, never rung
    if (!older && item && raw.kind === 'Notification' && raw.ntype === 'idle_prompt') notifyIdle(raw, item, replay);   // 2.3.7: 入力待ち
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
  state(state) { SOURCE.connected = state === 'connected'; if (state === 'connected') LIVE.connectedOnce = true; liveChrome(); talkConn(state); },
  snapshot(slices) {
    LIVE.replayNext = true;   // the server sends the recent events right after the snapshot (server.ws): seen, not rung
    liveApply(slices, true);
    netRequest('events.more', { beforeSeq: 2 ** 31, limit: 200 });
    if (typeof refreshNow === 'function') refreshNow();
  },
  slices(changed) { liveApply(changed, false); },
  events(items, older) { const replay = !older && LIVE.replayNext; if (!older) LIVE.replayNext = false; liveEvents(items, older, replay); },
  sheet(msg) { liveSheet(msg); },
  notice(level, text) { if (text) showToast(text); void level; },
  notifyPing() { NOTIFY.pings += 1; notifyPresenceSay(); },
  talk(msg) { talkReceive(msg); },   // talk.list / talk.messages / talk.update / talk.badges (58-talk.js)
};
/* トーク (2.3.6): a robot's agentId on the wire is the server's id (a main robot: its session id; a subagent: its id). */
Object.assign(SOURCE, {
  talkAgentId: (label) => (DEF[label] && DEF[label].realId) || null,
  talkLabel: (agentId) => (agentId ? LIVE.labelOfReal[agentId] || null : null),
  /* One request, already checked against the contract (58-talk.js talkFrame). talk.open and talk.get wait for their
     answer (talk.list / talk.messages, or a failed ack); talk.seen and talk.close are sent and not waited for. */
  talkSend(frame) {
    if (frame.type !== 'talk.open' && frame.type !== 'talk.get') return Promise.resolve({ ok: netSend(frame) });
    return new Promise((resolve) => {
      if (!netSend(frame)) { resolve({ ok: false, error: 'offline' }); return; }
      const timer = setTimeout(() => { NET.waits.delete(frame.reqId); resolve({ ok: false, error: 'timeout' }); }, 15000);
      NET.waits.set(frame.reqId, (ack) => { clearTimeout(timer); resolve(ack); });
    });
  },
});

/* ---------- the plan's usage limits (requester, 10-18) ----------
   From the statusLine (statusline.py → POST /usage → the usage slice): the 5-hour and the weekly window, their
   used share and when they reset. Only a terminal claude runs a statusLine (the VS Code extension and the desktop app do not), so
   the value may be old: past USAGE_STALE_MS it says how old. The number and its % share one colour, from green at
   0 to red just below 100 (the hue, not steps); at 100 — Claude Code caps the share there — the number gives way
   to 上限到達 in the inactive colour, and the time to the reset stays. */
const USAGE_STALE_MS = 15 * 60 * 1000;
const USAGE_LABEL = { fiveHour: tl('live.usage.five'), sevenDay: tl('live.usage.week') };
function usageHue(pct) { return Math.round(120 * (1 - Math.max(0, Math.min(100, pct)) / 100)); }
// The hue carries the share; the lightness is whatever keeps the text at 4.6:1 or more against the chip (12 px bold
// needs WCAG AA 4.5): darker in light (yellow especially), lighter in dark (red especially). Reviewed 10-18.
const USAGE_CONTRAST = 4.6;
function usageRgb(h, s, l) {
  const k = (n) => (n + h / 30) % 12, a = s * Math.min(l, 1 - l);
  const f = (n) => l - a * Math.max(-1, Math.min(k(n) - 3, 9 - k(n), 1));
  return [f(0), f(8), f(4)].map((v) => Math.round(v * 255));
}
function usageLum(rgb) {
  const [r, g, b] = rgb.map((v) => { const c = v / 255; return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4; });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}
function usageContrast(a, b) { const x = usageLum(a), y = usageLum(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); }
function usageColor(pct, dark = isDark()) {
  const fallback = dark ? '#182c47' : '#e3eaf4';   // app.css --chip; the live token when asked for the theme on screen
  const hex = ((dark === isDark() ? readToken('--chip', fallback) : fallback).match(/^#?([0-9a-f]{6})$/i) || [0, fallback.slice(1)])[1];
  const bg = [0, 2, 4].map((i) => parseInt(hex.slice(i, i + 2), 16));
  const h = usageHue(pct), sat = dark ? 0.7 : 0.62;
  let l = dark ? 0.64 : 0.34, rgb = usageRgb(h, sat, l);
  while (usageContrast(rgb, bg) < USAGE_CONTRAST && l > 0.02 && l < 0.98) { l += dark ? 0.01 : -0.01; rgb = usageRgb(h, sat, l); }
  return `rgb(${rgb.join(', ')})`;
}
function usageLeft(ms) {
  const m = Math.ceil(ms / 60000), d = Math.floor(m / 1440), h = Math.floor((m % 1440) / 60);
  return d > 0 ? tl('live.usage.left.days', { d, h }) : tl('live.usage.left.time', { h: Math.floor(m / 60), m: String(m % 60).padStart(2, '0') });
}
function usageAgo(ms) {
  const m = Math.floor(ms / 60000);
  return m < 60 ? tl('live.usage.ago.min', { n: m }) : m < 1440 ? tl('live.usage.ago.hour', { n: Math.floor(m / 60) }) : tl('live.usage.ago.day', { n: Math.floor(m / 1440) });   // 「◯分前の値」 until 10-19 (the requester: shorter)
}
function renderUsage(now) {
  const el = document.getElementById('usage');
  if (!el) return;
  const u = LIVE.slices.usage, windows = u && typeof u === 'object' && u.windows && typeof u.windows === 'object' ? u.windows : null;
  el.hidden = SOURCE.mode !== 'live';
  const stale = windows && Number(u.receivedAt) > 0 && now - u.receivedAt > USAGE_STALE_MS ? usageAgo(now - u.receivedAt) : '';
  const rows = [];
  for (const key of ['fiveHour', 'sevenDay']) {
    const w = windows && windows[key];
    if (!w || !Number.isFinite(Number(w.pct))) continue;
    const pct = Number(w.pct), over = Number(w.resetsAt) <= now;   // past its reset the share is not this window's any more
    rows.push({ key, pct, over, limit: !over && pct >= 100, left: over ? '' : usageLeft(Number(w.resetsAt) - now) });
  }
  const sig = JSON.stringify([rows, stale, isDark()]);
  if (el.dataset.sig === sig) return;
  el.dataset.sig = sig;
  const span = (cls, text, color) => { const s = document.createElement(cls === 'num' || cls === 'pc' ? 'b' : 'span'); s.className = cls; s.textContent = text; if (color) s.style.color = color; return s; };
  const out = rows.map((r) => {
    const box = span('uw', `${USAGE_LABEL[r.key]} `);
    box.dataset.window = r.key;
    if (r.over) box.append(span('limit', tl('live.usage.reset')));
    else if (r.limit) box.append(span('limit', tl('live.usage.limit')));
    // floored: 99.5 is not 100, and 100 only ever means the limit
    else box.append(span('num', String(Math.floor(r.pct)), usageColor(r.pct)), span('pc', '%', usageColor(r.pct)));
    if (!r.over) box.append(tl('live.usage.left', { left: r.left }));
    if (stale) { box.append(span('stale', ` · ${stale}`));   // not .note: that is the board's sticky-note card (10-19)
      box.title = tl('live.usage.stale', { ago: stale }); }
    return box;
  });
  if (!out.length) {
    const none = span('uw none', tl('live.usage.none'));
    none.title = tl('live.usage.none.title');
    out.push(none);
  }
  el.replaceChildren(...out);
}
