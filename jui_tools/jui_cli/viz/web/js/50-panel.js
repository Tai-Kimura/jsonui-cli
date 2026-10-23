
/* ---------- side panel ---------- */
const $ = (id) => document.getElementById(id);
const setHTML = (el, html) => { if (el._html !== html) { el.innerHTML = html; el._html = html; } };
const setText = (el, text) => { if (el && el.textContent !== text) el.textContent = text; };
/* The legend of heavy work's three looks (2.3.6), under the card's 重い作業 line. */
const HEAVY_LEGEND = tl('panel.heavy.legend');
const STATUS_CLASS = { idle: 'st-idle', write: 'st-write', written: 'st-idle', impl: 'st-impl', verify: 'st-verify', 'impl-done': 'st-idle', paused: 'st-paused', test: 'st-test', done: 'st-complete' };
/* A robot's badge: [its class, its words]. The kind (robotBadgeKind) is what the session's badge compares — never
   the words, which follow the language. */
const BADGES = {
  waiting: ['st-waiting', 'status.waiting'], asking: ['st-asking', 'status.asking'], done: ['st-done', 'status.done'],
  idle: ['st-idle', 'status.idle'], thinking: ['st-busy', 'status.thinking'], background: ['st-bg', 'status.background'],
  busy: ['st-busy', 'status.busy'],
};
function robotBadgeKind(id) {
  const s = robotState[id].state;
  // a question waits for the person too, but it is no permission: its own badge and filter (requester, 10-18)
  if (s === 'waiting') return robotState[id].asking ? 'asking' : 'waiting';
  return ['done', 'idle', 'thinking', 'background'].includes(s) ? s : 'busy';
}
const badgeOf = (kind) => [BADGES[kind][0], tl(BADGES[kind][1])];
const robotBadge = (id) => badgeOf(robotBadgeKind(id));
/* What the view is narrowed to: one project (or all), which sessions, how the session list is shown. */
const prefJSON = (key, fallback) => { try { return JSON.parse(readPref(key, JSON.stringify(fallback))); } catch (err) { return fallback; } };
const UI = {
  project: PROJECT[readPref('project', 'all')] ? readPref('project', 'all') : 'all',
  hiddenLists: new Set(),          // task lists left off the task board
  lanes: readPref('lanes', 'off') === 'on',
  sessFilter: readPref('sessFilter', 'all'),
  collapsed: new Set(prefJSON('collapsed', [])),
};
if (!['all', 'active', 'waiting', 'asking', 'background', 'idle'].includes(UI.sessFilter)) UI.sessFilter = 'all';
const inScope = (project) => UI.project === 'all' || UI.project === project;
// rbFollow (below): busy while it switches the view itself; handAt: the last switch by hand (setProject)
const FOLLOW = { busy: false, handAt: 0 };
const FOLLOW_HAND_MS = 3000;
const scopeLabel = () => (UI.project === 'all' ? tl('panel.scope.all') : PROJECT[UI.project].name);
function sessionBadge(s) {
  const kinds = new Set(s.robots.map(robotBadgeKind));
  // A session whose busy robots only think says 考え中, as its robot row does (they disagreed — 10-18 review).
  return badgeOf(['waiting', 'asking', 'busy', 'thinking', 'background'].find((k) => kinds.has(k)) || 'idle');
}
/* A robot on the whiteboards (10-19): its mark, and its session's name when it has one. */
const robotWho = (id) => `${pill(id, DEF[id].role)}${DEF[id].title ? `<span class="who-name">${esc(DEF[id].title)}</span>` : ''}`;
const roleVar = (s) => (s.by ? ` style="--c:${ROLES[DEF[s.by].role].color}"` : '');
/* Lists of buttons are rebuilt only when their membership changes, so keyboard focus survives the
   four-times-a-second refresh; the changing text and bars inside are updated in place. */
/* Everything a permission card shows that can change while it waits: its state, what the hooks allow (the async
   forward reports first with nothing allowed; --decide comes a moment later and allows the buttons), what was sent. */
const permSig = (p) => (p ? JSON.stringify([p.id, p.status, p.can, p.tooLongToShow, p.sentBy, p.sentRules, p.sentReason, p.input && p.input.command, p.task]) : '');
function keyed(el, sig, build) {
  if (el._sig === sig) return;
  const a = document.activeElement, fk = el.contains(a) ? a.dataset.fk : undefined;
  el.innerHTML = build(); el._sig = sig; el._html = null;
  if (fk !== undefined) { const again = el.querySelector(`[data-fk="${CSS.escape(fk)}"]`); if (again) again.focus({ preventScroll: true }); else el._lostFk = fk; }
}
const SEGS = `<span class="segs" aria-hidden="true">${'<i></i>'.repeat(7)}</span>`;
const SG_CLASS = { empty: 'sg-empty', writing: 'sg-writing', written: 'sg-written', impl: 'sg-impl', done: 'sg-done', test: 'sg-test', tested: 'sg-tested' };
function paintSegs(el, s) {
  const act = s.by ? activeSec(s) : -1;
  [...el.children].forEach((node, k) => {
    const g = secState(s, k), cls = SG_CLASS[g.kind] + (k === act ? ' sg-now' : ''), f = `${pct(g.f)}%`;
    if (node.className !== cls) node.className = cls;
    if (node._f !== f) { node.style.setProperty('--f', f); node._f = f; }
  });
}

/* panel open / close */
const mainEl = document.querySelector('.main');
let sideOpen = readPref('side', 'open') === 'open';
function applySide() {
  mainEl.classList.toggle('side-closed', !sideOpen);
  const b = $('btn-side');
  b.setAttribute('aria-expanded', String(sideOpen));
  b.textContent = sideOpen ? tl('panel.side.close') : tl('panel.side.open');
}
$('btn-side').addEventListener('click', () => { sideOpen = !sideOpen; writePref('side', sideOpen ? 'open' : 'closed'); applySide(); });
applySide();

let specFilter = readPref('specFilter', 'live');
if (!['live', 'partial', 'todo', 'done', 'all'].includes(specFilter)) specFilter = 'live';
const specFilterEl = $('spec-filter'), specListEl = $('spec-list');
specFilterEl.innerHTML = [...BUCKETS, ['all', tl('panel.scope.all')]].map(([b, label]) => `<button type="button" data-f="${esc(b)}" aria-pressed="${b === specFilter}">${esc(label)}<b></b></button>`).join('');
specFilterEl.addEventListener('click', (e) => {
  const b = e.target.closest('[data-f]');
  if (!b) return;
  specFilter = b.dataset.f; writePref('specFilter', specFilter);
  [...specFilterEl.children].forEach((x) => x.setAttribute('aria-pressed', String(x === b)));
  renderPanel(latestModel);
});
specListEl.addEventListener('click', (e) => { const b = e.target.closest('[data-idx]'); if (b) openWhiteboard(Number(b.dataset.idx), b); });
$('btn-specboard').addEventListener('click', (e) => openWhiteboard(-1, e.currentTarget));
$('btn-taskboard').addEventListener('click', (e) => openTaskBoard(e.currentTarget));

const COL_STATE = { doing: ['st-busy', tl('status.busy')], wait: ['st-waiting', tl('panel.col.wait')], todo: ['st-idle', tl('panel.col.todo')], done: ['st-done', tl('status.done')] };
const paintState = (node, [cls, label]) => { if (!node) return; const c = `state ${cls}`; if (node.className !== c) node.className = c; setText(node, label); };
const SESS_FILTERS = [['all', tl('panel.scope.all')], ['active', tl('panel.sf.active')], ['waiting', tl('status.waiting')], ['asking', tl('panel.sf.asking')], ['background', tl('status.background')], ['idle', tl('status.idle')]];
const sessFilterEl = $('sess-filter');
sessFilterEl.innerHTML = SESS_FILTERS.map(([k, label]) => `<button type="button" data-sf="${esc(k)}" aria-pressed="${k === UI.sessFilter}">${esc(label)}<b></b></button>`).join('');
sessFilterEl.addEventListener('click', (e) => {
  const b = e.target.closest('[data-sf]');
  if (!b) return;
  UI.sessFilter = b.dataset.sf; writePref('sessFilter', UI.sessFilter);
  [...sessFilterEl.children].forEach((x) => x.setAttribute('aria-pressed', String(x === b)));
  renderSessions();
});
const sessMatch = (s, f) => { const [c] = sessionBadge(s); return f === 'all' || (f === 'active' && c !== 'st-idle') || (f === 'waiting' && c === 'st-waiting') || (f === 'asking' && c === 'st-asking') || (f === 'background' && c === 'st-bg') || (f === 'idle' && c === 'st-idle'); };
$('sessions').addEventListener('click', (e) => {
  const b = e.target.closest('[data-fold]');
  if (!b) return;
  if (UI.collapsed.has(b.dataset.fold)) UI.collapsed.delete(b.dataset.fold); else UI.collapsed.add(b.dataset.fold);
  writePref('collapsed', JSON.stringify([...UI.collapsed]));
  renderSessions();
});
const SB_ORDER = { 'st-waiting': 0, 'st-asking': 1, 'st-busy': 2, 'st-bg': 3, 'st-idle': 4 };
function renderSessions() {
  const el = $('sessions'), scoped = SESSIONS.filter((s) => inScope(s.project));
  [...sessFilterEl.children].forEach((b) => setText(b.lastElementChild, String(scoped.filter((s) => sessMatch(s, b.dataset.sf)).length)));
  // Sessions that need you come first: waiting for permission, then working, then idle.
  const groups = ROOMS.filter((r) => inScope(r.id)).map((r) => [r, scoped.filter((s) => s.project === r.id && sessMatch(s, UI.sessFilter)).sort((a, b) => SB_ORDER[sessionBadge(a)[0]] - SB_ORDER[sessionBadge(b)[0]] || a.id.localeCompare(b.id))]);
  keyed(el, JSON.stringify([UI.project, UI.sessFilter, [...UI.collapsed], groups.map(([r, l]) => [r.id, l.map((x) => x.id)]), NAMES.rev]), () => groups.map(([r, list]) => {
    const folded = UI.collapsed.has(r.id), any = scoped.some((x) => x.project === r.id);
    const itemsHTML = list.map((x) => {
      const subsHTML = x.robots.filter((id) => id !== x.id).map((id) => `<li><button type="button" class="who-btn" data-robot-open="${esc(id)}" data-fk="ss-${esc(id)}">${pill(id, DEF[id].role)}<span>${esc(DEF[id].agent)}</span></button><span class="state" data-st="${esc(id)}"></span><p class="act" data-sact="${esc(id)}"></p></li>`).join('');
      return `<li class="session"><div class="srow"><button type="button" class="who-btn" data-robot-open="${esc(x.id)}" data-fk="ss-${esc(x.id)}">${pill(x.id, 'main')}<span class="sname">${esc(DEF[x.id].agent)}</span></button><span class="state" data-sst="${esc(x.id)}"></span></div><p class="act" data-sact="${esc(x.id)}"></p>${subsHTML ? `<ul class="subs">${subsHTML}</ul>` : ''}</li>`;
    }).join('');
    return `<section class="pgroup"><button type="button" class="pg-toggle" data-fold="${esc(r.id)}" data-fk="pg-${esc(r.id)}" aria-expanded="${!folded}"><span class="pg-caret" aria-hidden="true"></span><b>${esc(r.name)}</b><small data-pgsum="${esc(r.id)}"></small></button>${folded ? '' : itemsHTML ? `<ul class="sessions">${itemsHTML}</ul>` : `<p class="empty-note">${any ? esc(tl('panel.sess.nomatch')) : esc(tl('panel.sess.none'))}</p>`}</section>`;
  }).join(''));
  for (const [r] of groups) {
    const all = scoped.filter((x) => x.project === r.id), badges = all.map(sessionBadge);
    const w = badges.filter((b) => b[0] === 'st-waiting').length, ask = badges.filter((b) => b[0] === 'st-asking').length, busy = badges.filter((b) => b[0] === 'st-busy').length;
    setText(el.querySelector(`[data-pgsum="${CSS.escape(r.id)}"]`), `${tl('panel.pg.sessions', { n: all.length })}${w ? tl('panel.pg.waiting', { n: w }) : ''}${ask ? tl('panel.pg.asking', { n: ask }) : ''}${busy ? tl('panel.pg.busy', { n: busy }) : ''}`);
  }
  for (const x of scoped) {
    paintState(el.querySelector(`[data-sst="${CSS.escape(x.id)}"]`), sessionBadge(x));
    for (const id of x.robots) {
      if (id !== x.id) paintState(el.querySelector(`[data-st="${CSS.escape(id)}"]`), robotBadge(id));
      setText(el.querySelector(`[data-sact="${CSS.escape(id)}"]`), robotState[id].act);
    }
  }
}
function renderPanel(model) {
  renderSessions();

  const scopedSpecs = model.specs.filter((x) => inScope(x.project)), counts = bucketCounts(scopedSpecs);
  [...specFilterEl.children].forEach((b) => setText(b.lastElementChild, String(b.dataset.f === 'all' ? scopedSpecs.length : counts[b.dataset.f])));
  const roomOrder = Object.fromEntries(ROOMS.map((r, k) => [r.id, k]));
  const shown = model.specs.map((s, i) => [s, i]).filter(([s]) => inScope(s.project) && (specFilter === 'all' || s.bucket === specFilter)).sort((a, b) => roomOrder[a[0].project] - roomOrder[b[0].project] || specNewer(a, b));
  const multi = new Set(shown.map(([x]) => x.project)).size > 1;
  keyed(specListEl, JSON.stringify([UI.project, specFilter, scopedSpecs.length, shown.map(([x, i]) => `${i}:${x.bucket}:${x.by || ''}:${x.name}`)]), () => (shown.length
    ? shown.map(([x, i], k) => `${multi && (k === 0 || shown[k - 1][0].project !== x.project) ? `<li class="sl-group">${esc(PROJECT[x.project].name)}<b>${shown.filter(([y]) => y.project === x.project).length}</b></li>` : ''}<li><button type="button" class="spec-row b-${esc(x.bucket)}" data-idx="${i}" data-fk="sp-${i}"${roleVar(x)}><span class="nm">${coTag(x)}${esc(x.name)}</span><span class="stx"></span>${x.by ? pill(x.by, DEF[x.by].role) : ''}${SEGS}</button></li>`).join('')
    : `<li class="empty-note">${!scopedSpecs.length ? esc(tl('panel.spec.none.scope', { scope: scopeLabel() })) : specFilter === 'live' ? esc(tl('panel.spec.none.live')) : esc(tl('panel.spec.none.state'))}</li>`));
  specListEl.querySelectorAll('.spec-row').forEach((b) => { const s = model.specs[+b.dataset.idx]; paintStatus(b.querySelector('.stx'), specStatus(s)); paintSegs(b.querySelector('.segs'), s); });

  const T = model.tests, n = CASES.length;
  const pPct = (T.passed / n) * 100, rPct = T.runningIdx >= 0 ? 100 / n : 0;
  if (SOURCE.mode === 'live' && !T.rows.length && !T.command) setHTML($('tests'), `<p class="empty-note">${T.none ? esc(tl('tests.none')) : esc(T.statusText)}</p>`);
  else if (SOURCE.mode === 'live') setHTML($('tests'), liveTestsHTML(T));
  else if (!inScope('shop')) setHTML($('tests'), `<p class="empty-note">${esc(tl('panel.tests.none.scope', { scope: scopeLabel() }))}</p>`);
  else setHTML($('tests'), `<div class="test-head"><div>${pill('a2', 'test')} <code>${esc(T.file)}</code></div><code>${esc(T.device)} · ${esc(T.statusText)}</code>
<div class="prog" role="img" aria-label="${esc(tl('panel.tests.prog', { passed: T.passed, n }))}"><span class="p" style="width:${pPct}%"></span><span class="${T.retrying ? 'f' : 'r'}" style="width:${rPct}%"></span></div></div>
<ul class="cases">${T.rows.map((c, i) => {
    const icon = { pending: '○', running: '▶', passed: '✓', flaky: '⚠' }[c.status];
    const subHTML = c.status === 'running' ? `<span class="step">${c.attempt > 1 ? esc(tl('panel.case.retrying')) : ''}${esc(c.step)}</span>` : `<span class="br">${esc(tl('panel.case.branch', { branch: c.branch }))}${c.status === 'flaky' ? esc(tl('panel.case.flaky')) : ''}</span>`;
    return `<li class="c-${esc(c.status)}"><span class="ic">${esc(icon)}</span><span>${i + 1}. ${esc(c.name)}</span>${subHTML}</li>`;
  }).join('')}</ul>`);

  // Tasks: a task whose owner is waiting for permission comes first with the answer buttons; prompts that
  // belong to no task get their own row on top.
  const order = { doing: 0, wait: 1, todo: 2, done: 3 };
  const scopedTasks = model.tasks.filter((x) => inScope(PROJECT_OF[x.list]));
  const tasks = [...scopedTasks].sort((a, b) => (b.perm ? 1 : 0) - (a.perm ? 1 : 0) || order[a.col] - order[b.col] || a.list.localeCompare(b.list) || a.id - b.id);
  const scopedPend = model.pending.filter((p) => inScope(projectOfRobot(p.who)));
  const loose = scopedPend.filter((p) => !p.task);
  const projectTag = (list) => (UI.project === 'all' ? `<span class="ptag">${esc(PROJECT[PROJECT_OF[list]].name)}</span>` : '');
  setHTML($('task-sum'), KCOLS.map(([c, label]) => `<span class="state ${COL_STATE[c][0]}">${esc(label)} ${scopedTasks.filter((x) => x.col === c).length}</span>`).join('') + (scopedPend.length ? `<span class="state st-waiting">${esc(tl('panel.count.waiting', { n: scopedPend.length }))}</span>` : ''));
  keyed($('tasks'), JSON.stringify([UI.project, NAMES.rev, loose.map(permSig), tasks.map((x) => `${x.key}:${x.col}:${permSig(x.perm)}:${x.subject}:${x.owner || ''}`)]), () => [
    ...loose.map((p) => `<li class="task has-perm perm-only"><button type="button" class="task-open" data-open="perm:${esc(p.id)}" data-fk="to-${esc(p.id)}"><span class="tid">${esc(tl('panel.task.session', { id: SESSION_OF[p.who] }))}</span><span class="subject">${esc(tl('panel.task.perm.outside'))}</span></button><span class="state st-waiting">${esc(tl('status.waiting'))}</span><span class="meta">${pill(p.who, DEF[p.who].role)} ${esc(DEF[p.who].agent)}${projectTag(SESSION_OF[p.who])}</span>${permBox(p)}</li>`),
    ...tasks.map((x) => {
      const [c, l] = x.perm ? ['st-waiting', tl('status.waiting')] : x.col === 'wait' ? [x.waitingFor === 'question' ? 'st-asking' : 'st-waiting', waitLabel(x)] : COL_STATE[x.col];
      return `<li class="task t-${esc(x.status)}${x.perm ? ' has-perm' : ''}${x.fresh ? ' t-new' : ''}${isTurn(x) ? ' t-turn' : ''}${x.failed ? ' t-failed' : ''}"><button type="button" class="task-open" data-open="${esc(x.key)}" data-fk="to-${esc(x.key)}"><span class="tid">${esc(x.list)} ${esc(taskRef(x))}</span><span class="subject">${x.harness ? `<span class="h-tag">${esc(x.harness)}</span>` : ''}${esc(x.subject)}</span></button><span class="state ${esc(c)}">${esc(l)}</span><span class="meta">${x.owner ? `${pill(x.owner, DEF[x.owner].role)} ${esc(DEF[x.owner].agent)}` : esc(tl('panel.owner.none'))}${projectTag(x.list)}</span>${x.perm ? permBox(x.perm) : ''}</li>`;
    }),
  ].join('') || `<li class="empty-note">${esc(tl('panel.task.none.scope', { scope: scopeLabel() }))}</li>`);

  const chip = $('chip-perm');
  chip.hidden = model.pending.length === 0;
  setText(chip, tl('panel.count.waiting', { n: model.pending.length }));
  renderQuestions();
  renderDenials();
  paintSince($('denied'), model.t, tl('panel.since.elapsed'));
  waitChips();   // 53-waits.js
  const sIn = SESSIONS.filter((x) => inScope(x.project)).length, rIn = ROBOT_DEFS.filter((d) => inScope(projectOfRobot(d.id))).length;
  setText($('chip-robots'), UI.project === 'all' ? tl('panel.chip.robots', { n: ROBOT_DEFS.length }) : tl('panel.chip.robots.of', { n: rIn, all: ROBOT_DEFS.length }));
  setText($('chip-sessions'), UI.project === 'all' ? tl('panel.chip.sessions', { n: SESSIONS.length }) : tl('panel.chip.sessions.of', { n: sIn, all: SESSIONS.length }));
}

/* ---------- answering permission prompts from the view ---------- */
const PERM_NOTE = esc(tl('panel.perm.note'));
const RELAY_HOW = tlHTML('panel.relay.how');
const sentWords = (p) => `${p.sentBehavior === 'deny' ? `${tl('panel.sent.deny')}${p.sentReason ? tl('panel.sent.reason') : ''}` : p.sentRules ? tl('panel.sent.rules', { n: p.sentRules.length }) : tl('panel.sent.allow')}${p.sentBy ? tl('panel.sent.via', { via: tl(p.sentBy === 'hook' ? 'panel.sent.hook' : 'panel.sent.relay') }) : ''}`;
const permButtonsLive = (p, where) => (p.status === 'sent' ? `<p class="perm-sent">${tlHTML('panel.perm.sent', { what: sentWords(p) })}</p>`
  : p.tooLongToShow ? `<p class="perm-relay">${esc(tl('panel.perm.toolong'))}</p>`
  : !p.can.allowDeny ? `<p class="perm-relay">${esc(tl('panel.perm.norelay'))}<small>${RELAY_HOW}</small></p>`
    : `<button type="button" class="pa pa-allow" data-do="allow" data-perm="${esc(p.id)}" data-fk="${esc(where)}a-${esc(p.id)}">${esc(tl('panel.perm.allow'))}</button>${p.can.always && Array.isArray(p.suggestions) && p.suggestions.length ? `<button type="button" class="pa pa-always" data-do="always" data-perm="${esc(p.id)}" data-fk="${esc(where)}w-${esc(p.id)}">${esc(tl('panel.perm.always'))}</button>` : ''}<button type="button" class="pa pa-deny" data-do="deny" data-perm="${esc(p.id)}" data-fk="${esc(where)}d-${esc(p.id)}">${esc(tl('panel.perm.deny'))}</button>`);
const permButtons = (p, where) => (SOURCE.mode === 'live' ? permButtonsLive(p, where) : permButtonsDemo(p, where));
const permButtonsDemo = (p, where) => `<button type="button" class="pa pa-allow" data-do="allow" data-perm="${esc(p.id)}" data-fk="${esc(where)}a-${esc(p.id)}">${esc(tl('panel.perm.allow'))}</button><button type="button" class="pa pa-always" data-do="always" data-perm="${esc(p.id)}" data-fk="${esc(where)}w-${esc(p.id)}" title="${esc(tl('panel.perm.always.title', { rule: p.rule }))}">${esc(tl('panel.perm.always'))}</button><button type="button" class="pa pa-deny" data-do="deny" data-perm="${esc(p.id)}" data-fk="${esc(where)}d-${esc(p.id)}">${esc(tl('panel.perm.deny'))}</button>`;
/* What a live card asks about: card.exact verbatim — whitespace and line breaks as they are (pre-wrap), the whole
   command however long (the box scrolls) — never the summary or the clipped preview. A relay request the server
   could not pair with a hook has no exact: its preview is shown as what it is. The demo keeps its one-line code. */
const EXACT_LABEL = { command: '', file_path: tl('panel.exact.file'), notebook_path: tl('panel.exact.notebook'), url: 'URL', pattern: tl('panel.exact.pattern'), old_string: tl('panel.exact.old'), new_string: tl('panel.exact.new'), content: tl('panel.exact.content') };
function permSubjectLive(p) {
  const e = p.exact;
  if (!e) {
    return p.preview
      ? `<span class="perm-exact" tabindex="0"><span class="pe-k">${esc(tl('panel.exact.relayed'))}</span>${esc(p.preview)}</span>`
      : `<code>${esc(permSummary(p))}</code>`;
  }
  const partsHTML = Object.keys(EXACT_LABEL).filter((k) => typeof e[k] === 'string').map((k) => (EXACT_LABEL[k] ? `<span class="pe-k">${esc(EXACT_LABEL[k])}</span>` : '') + `<span class="pe-v">${esc(e[k])}</span>`);
  if (e.contentTruncated) partsHTML.push(`<span class="pe-note">${esc(tl('panel.exact.cut', { shown: [...(e.content || '')].length, all: Number(e.contentTruncated) }))}</span>`);
  return `<span class="perm-exact" tabindex="0">${partsHTML.join('')}</span>`;
}
const permSubject = (p) => (SOURCE.mode === 'live' ? permSubjectLive(p) : `<code>${esc(permSummary(p))}</code>`);
const permBox = (p) => `<div class="perm-box" data-perm-box="${esc(p.id)}"><p class="perm-q"><b>${esc(p.tool)}</b> ${permSubject(p)}</p><div class="perm-acts">${permButtons(p, 's')}</div></div>`;
function recentHTML(id) {
  const items = logItems.filter((e) => e.who === id).slice(0, 6);
  return items.length ? items.map((e) => `<li><time>${fmtClock(BASE_CLOCK + e.abs)}</time><span><b>${esc(e.kind)}</b> ${esc(e.what)}</span></li>`).join('') : `<li><span>${esc(tl('panel.recent.none'))}</span></li>`;
}
let toastTimer = 0;
function showToast(text) {
  const el = $('toast');
  el.textContent = text; el.classList.add('show');
  clearTimeout(toastTimer); toastTimer = setTimeout(() => el.classList.remove('show'), 3600);
}
function refreshNow() {
  const t = ((simT % LOOP) + LOOP) % LOOP;
  latestModel = computeModel(t, Math.floor(simT / LOOP));
  updateRobotStates(simT, t, latestModel.perms);
  renderPanel(latestModel); renderTicker(); renderTaskBoard(latestModel); renderRobot(latestModel); renderLog(true);
  if (has3D) redrawBoards(latestModel, performance.now() / 1000, true);
}
function decide(id, behavior, btn) {
  const p = latestModel.pending.find((q) => q.id === id);
  if (!p) return;
  const where = btn.closest('#tasks, #perm-strip, #kanban, #tb-detail, #rb');
  // the reason box of the very card pressed (the card is on the board, the robot's card and its 応答の履歴 tab at once)
  const card = btn.closest('.tbd-perm'), reasonEl = card ? card.querySelector('.tbd-reason input') : null;
  const reason = behavior === 'deny' && reasonEl ? reasonEl.value.trim() : '';
  if (SOURCE.mode === 'live' && behavior === 'always') { openAlwaysConfirm(p, btn); return; }   // confirm the rules first (plan 08 §5)
  SOURCE.decide(id, behavior, { perm: p, reason });
  refreshNow();
  // The answered buttons are gone; keep the keyboard where the person was.
  if (!document.activeElement || document.activeElement === document.body) {
    const next = where && (where.querySelector(`[data-open="${CSS.escape(p.task || `perm:${id}`)}"]`) || where.querySelector('#tbd-close, #rb-close, button'));
    (next || $(tb.open ? 'tb-close' : 'btn-taskboard')).focus({ preventScroll: true });
  }
}
document.addEventListener('click', (e) => {
  const t = e.target.closest('[data-do], [data-open], [data-robot-open], [data-spec-open], [data-log-robot], [data-close-detail], [data-reset-rules], [data-rb-close], [data-set-all]');
  if (!t) return;
  if (t.dataset.do) decide(t.dataset.perm, t.dataset.do, t);
  else if (t.dataset.open) openTaskBoard(t, t.dataset.open);
  else if (t.dataset.robotOpen) selectRobot(t.dataset.robotOpen, t);
  else if (t.dataset.specOpen !== undefined) openWhiteboard(Number(t.dataset.specOpen), t);
  else if (t.dataset.logRobot) openLogFor(t.dataset.logRobot, t);
  else if (t.hasAttribute('data-close-detail')) closeTaskDetail();
  else if (t.hasAttribute('data-reset-rules')) { alwaysRules.clear(); showToast(tl('panel.rules.reset.done')); refreshNow(); }
  else if (t.hasAttribute('data-rb-close')) closeRobot({ byHand: true });
  else if (t.hasAttribute('data-set-all')) setProject('all');
});
$('chip-perm').addEventListener('click', (e) => { tb.waitView = true; openTaskBoard(e.currentTarget); });

/* ---------- scope: which project (or all) every panel and board shows, and which sessions ---------- */
function paintScopeButtons() {
  document.querySelectorAll('[data-scope-btn]').forEach((b) => setHTML(b, `<span class="sb-k">${esc(tl('panel.sb.project'))}</span><b>${esc(scopeLabel())}</b><span class="sb-caret" aria-hidden="true"></span>`));
  const scoped = SESSIONS.filter((s) => inScope(s.project));
  const shown = scoped.filter((s) => !UI.hiddenLists.has(s.id));
  setHTML($('tb-sess'), `<span class="sb-k">${esc(tl('panel.sb.session'))}</span><b>${shown.length === scoped.length ? esc(tl('panel.sb.all', { n: scoped.length })) : shown.length === 1 ? esc(shown[0].id) : `${shown.length} / ${scoped.length}`}</b><span class="sb-caret" aria-hidden="true"></span>`);
  const robotsIn = ROBOT_DEFS.filter((d) => inScope(projectOfRobot(d.id)));
  const shownR = robotsIn.filter((d) => !logState.hiddenRobots.has(d.id));
  setHTML($('log-who'), `<span class="sb-k">${esc(tl('panel.sb.robot'))}</span><b>${shownR.length === robotsIn.length ? esc(tl('panel.sb.all', { n: robotsIn.length })) : shownR.length === 1 ? esc(shownR[0].id) : `${shownR.length} / ${robotsIn.length}`}</b><span class="sb-caret" aria-hidden="true"></span>`);
  $('tb-lanes').checked = UI.lanes;
  document.body.dataset.scope = UI.project;
}
function roomPose(id) {
  if (SOURCE.mode === 'live') return liveRoomPose(id);
  if (id === 'all') return { p: new THREE.Vector3(6.8, 15.9, 22.1), t: new THREE.Vector3(0.3, 0.4, -0.4) };
  const r = PROJECT[id], c = new THREE.Vector3((r.x0 + r.x1) / 2, 0.4, (r.z0 + r.z1) / 2);
  const size = Math.max(r.x1 - r.x0, (r.z1 - r.z0) * 1.3);
  return { p: c.clone().add(new THREE.Vector3(6.5, 15.5, 22.5).normalize().multiplyScalar(size * 1.9 + 3)), t: c };
}
function focusProject(id, instant) {
  if (!has3D) return;
  const pose = roomPose(id);
  if (zoom.zoomed) { zoom.returnPose = pose; return; }
  controls.enabled = false;
  flyTo(pose.p, pose.t, controls.target, instant || reduceMotion ? 0 : 0.8, () => { controls.target.copy(pose.t); controls.enabled = true; controls.update(); });
}
/* The robot last picked in each project (ticket 2026-10-20-jui-viz-project-switch-keeps-last-robot-per-project;
   requester: 「ロボット選択状態でプロジェクト切り替えた先のロボットに切り替えて欲しい。各プロジェクトで最後に選択してたロボット
   覚えといて、それがいたらそれを選択、いなかったら未選択で部屋表示」): project id -> robot, or null when its card was closed
   by hand. Kept in the page only (a label may name another robot after the server restarts). */
const LAST_ROBOT = new Map();
/* The robot to pick on switching to a project with a robot picked: the one last picked there if it is still in the
   room (not gone, not walking out), else none. すべて: none. */
function robotToPick(id) {
  const want = id === 'all' ? null : LAST_ROBOT.get(id);
  if (!want || !DEF[want] || !ROBOT_DEFS.some((d) => d.id === want) || projectOfRobot(want) !== id) return null;
  return SOURCE.mode === 'live' && LIVE.leaving[want] ? null : want;
}
function setProject(id, { camera: moveCamera = true } = {}) {
  if (!(id === 'all' || PROJECT[id]) || UI.project === id) return;
  if (!FOLLOW.busy) FOLLOW.handAt = Date.now();   // a switch by hand (rbFollow does not follow right after one)
  // only a picked robot carries over: with none picked, the room is shown and nothing opens
  const pick = rbState.id ? robotToPick(id) : undefined;
  // The card closes and the next opens with the 3D held (ticket 2026-10-21-jui-viz-3d-zoom-lost-after-project-switch):
  // closing alone used to start the flight back, which then ran to its end under the card opened next.
  const held = !!rbState.id;
  if (held) holdView('switch');
  if (rbState.id) closeRobot();
  UI.project = id; writePref('project', id);
  if (wb.open && wb.idx >= 0 && !inScope(SPECS[wb.idx].project)) wb.idx = -1;
  if (tb.detail && !tb.detail.startsWith('perm:') && !inScope(PROJECT_OF[tb.detail.split('#')[0]])) tb.detail = null;
  if (SOURCE.mode === 'live' && has3D) liveShowFloorOf(id);   // a room on another floor: go there first
  if (SOURCE.mode === 'live') liveRelayout();                // one room at a time: the room picked, wider (or the floor again)
  if (has3D && zoom.zoomed) zoom.returnPose = roomPose(id);   // what closes later goes back to this room, not the last one's
  if (pick) openRobot(pick, document.getElementById('scene-canvas'));   // the camera goes to it, not to the room
  else if (moveCamera) focusProject(id);
  if (held) releaseView('switch');   // no card now: back to this room; a card open: it holds the view
  paintScopeButtons();
  refreshNow();
  if (wb.open) { wbCode.scrollTop = 0; renderWhiteboard(latestModel, true); }
  // A zoomed board view moves to the board of the project now shown.
  if (has3D && zoom.zoomed && !camTween && (wb.open || tb.open)) { const pose = wb.open ? specPose(wb.idx) : taskPose(); camera.position.copy(pose.p); viewTarget.copy(pose.t); }
  showToast(id === 'all' ? tl('panel.scope.all.shown') : tl('panel.scope.one.shown', { name: PROJECT[id].name }));
}

/* ---------- questions (AskUserQuestion, requester 10-18): single and multiple choice, a free answer per question ----------
   A card shows every question, header, option, description and preview as text (escaped). It can be answered only
   while a hook waits for it (forward.py --ask) and only when everything fits on it; every question needs an answer
   before it can be sent. Options are named by their index, never by their label, in the markup. */
const Q_SHOW_MS = 30_000;   // an answered card stays a moment, saying who answered and what
const qState = (q) => (q.status === 'sent' ? tl('panel.q.sent')
  : q.status === 'answered' ? tl('panel.q.answered') : q.status === 'answered_in_terminal' ? tl('panel.q.terminal')
    : q.status === 'expired' ? tl('panel.expired') : '');
/* Why a pending card cannot be answered here. It goes at the top, above choices drawn as not pickable: at the
   bottom, under radios that looked live, the requester clicked them and nothing happened (10-18). */
const qWhy = (q) => (q.tooLongToShow ? tl('panel.q.why.toolong')
  : q.released ? tl('panel.q.why.released') : q.waitEnded ? qWhyEnded(q)
    : tl('panel.q.why.norelay'));
/* Why the wait ended (2.3.6, ticket 2026-10-19-jui-viz-question-window-too-short): the server keeps the reason and
   the time on the card (questions.hook_gave_up), so a reload says the same. */
const qClock = (ms) => (ms ? new Date(ms).toTimeString().slice(0, 8) : '');
function qWhyEnded(q) {
  const at = q.waitEndedAt ? tl('panel.q.at', { time: qClock(q.waitEndedAt) }) : '';
  if (q.waitEndReason === 'hidden') return tl('panel.q.end.hidden', { at });
  if (q.waitEndReason === 'session') return tl('panel.q.end.session', { at });
  return tl('panel.q.end.time', { at });
}
/* The countdown on a waiting card: "until answered" (2.3.6) has none. */
const Q_NEVER_MS = 2 ** 53 - 1;
function qLeftText(q, now) {
  if (!q || !q.waitUntil) return '';
  if (q.waitUntil >= Q_NEVER_MS) return tl('panel.q.left.never');
  const left = Math.max(0, Math.ceil((q.waitUntil - now) / 1000));
  return left >= 90 ? tl('panel.q.left.min', { m: Math.floor(left / 60), s: left % 60 }) : tl('panel.q.left.sec', { s: left });
}
/* × on a card in the history's cards box (where 'h') nobody waits on any more: it takes the card off that box only
   (histOff, 55-history.js; ticket 2026-10-21-jui-viz-hist-answered-card-dismiss-and-expand). */
function histOffHTML(where, kind, id, done) {
  if (where !== 'h' || !done) return '';
  return `<button type="button" class="h-card-x" data-h-off="${esc(`${kind}:${id}`)}" data-fk="hx-${esc(kind)}-${esc(id)}" aria-label="${esc(tl('panel.hist.off.aria'))}" title="${esc(tl('panel.hist.off.title'))}">×</button>`;
}
function questionHTML(q, where = '') {   // where: '' in the panel, 'b' on the board (the same card twice in one page)
  const open = q.status === 'pending' && q.hookWaiting && !q.tooLongToShow;
  const closed = q.status === 'pending' && !open;
  const got = q.sentAnswers || q.gotAnswers || null;
  const itemsHTML = q.questions.map((x, i) => {
    const type = x.multiSelect ? 'checkbox' : 'radio', name = `qa-${where}${q.id}-${i}`;   // radios: one group per card
    const optsHTML = x.options.map((o, k) => `<label class="qopt"><input type="${esc(type)}" name="${esc(name)}" data-qi="${i}" data-qk="${k}"${open ? '' : ' disabled'}><span class="qlabel">${esc(o.label)}</span>${o.description ? `<span class="qdesc">${esc(o.description)}</span>` : ''}${o.preview ? `<pre class="qprev">${esc(o.preview)}</pre>` : ''}</label>`).join('');
    const otherHTML = `<label class="qopt qother"><input type="${esc(type)}" name="${esc(name)}" data-qi="${i}" data-qk="other"${open ? '' : ' disabled'}><span class="qlabel">${esc(tl('panel.q.other'))}</span><input type="text" class="qother-text" data-qi="${i}" aria-label="${esc(tl('panel.q.other.aria', { question: x.question }))}" maxlength="2000"${open ? '' : ' disabled'}></label>`;
    const answeredHTML = got && got[x.question] !== undefined ? `<p class="qgot">${esc(tl('panel.q.got'))}<b>${esc(got[x.question])}</b></p>` : '';
    // answered or over: the question and its answer only
    const choicesHTML = q.status === 'pending' ? `${optsHTML}${otherHTML}` : '';
    return `<fieldset class="qq"><legend>${x.header ? `<span class="qhead">${esc(x.header)}</span>` : ''}<span class="qtext">${esc(x.question)}</span>${x.multiSelect ? `<span class="qmulti">${esc(tl('panel.q.multi'))}</span>` : ''}</legend>${choicesHTML}${answeredHTML}</fieldset>`;
  }).join('');
  // While the hook waits the terminal shows no question (measured 10-18): the time left, and the way to the terminal.
  const footHTML = open ? `<div class="qfoot"><button type="button" class="pa pa-allow" data-qsend="${esc(q.id)}" data-fk="${esc(where)}qs-${esc(q.id)}" disabled>${esc(tl('panel.q.send'))}</button><button type="button" class="pa pa-deny" data-qrelease="${esc(q.id)}" data-fk="${esc(where)}qr-${esc(q.id)}">${esc(tl('panel.q.release'))}</button></div><p class="qnote">${esc(tl('panel.q.note.a'))}<span data-quntil="${esc(q.id)}"></span>${esc(tl('panel.q.note.b'))}</p>`
    : closed ? '' : `<p class="qnote qdone">${esc(qState(q))}</p>`;
  const whyHTML = closed ? `<p class="qnote qwhy" role="note">${esc(tl('panel.q.why', { why: qWhy(q) }))}</p>` : '';
  return `<article class="qcard${open ? ' q-open' : ''}${closed ? ' q-closed' : ''}" data-qcard="${esc(q.id)}"><header class="qwho">${pill(q.who, DEF[q.who].role)}<span>${esc(DEF[q.who].agent)}</span><span class="pc-wait" data-since="${q.at}"></span>${histOffHTML(where, 'q', q.id, q.status !== 'pending')}</header>${whyHTML}${itemsHTML}${footHTML}</article>`;
}
/* The question cards the panel shows and the board shows (2.3.5): one list from QUESTIONS, oldest first. */
function questionsShown(now = Date.now()) {
  return QUESTIONS.filter((q) => inScope(projectOfRobot(q.who)) && (q.status === 'pending' || q.status === 'sent' || now - (q.doneAt || 0) < Q_SHOW_MS))
    .sort((a, b) => (a.at || 0) - (b.at || 0));
}
/* The questions waiting for an answer, every project; the chip counts them all. In scope and elsewhere: the board shows
   the first and says how many of the second (as its permission strip does), so the chip = cards in scope + elsewhere. */
const questionsWaiting = () => QUESTIONS.filter((q) => q.status === 'pending');
const questionsElsewhere = () => questionsWaiting().filter((q) => !inScope(projectOfRobot(q.who))).length;
const questionsSig = (shown) => JSON.stringify([NAMES.rev, ...shown.map((q) => [q.id, q.status, q.hookWaiting, q.tooLongToShow, q.waitEnded, q.waitEndReason, q.waitEndedAt, q.released, q.sentAnswers, q.gotAnswers])]);
function renderQuestions() {
  const now = Date.now();
  const shown = questionsShown(now);
  const waiting = questionsWaiting().length;
  const chip = $('chip-ask');
  chip.hidden = waiting === 0;
  setText(chip, tl('panel.chip.ask', { n: waiting }));
  $('questions-sec').hidden = shown.length === 0;
  keyed($('questions'), questionsSig(shown), () => shown.map((q) => questionHTML(q)).join(''));
  for (const el of document.querySelectorAll('#questions [data-quntil], #q-strip [data-quntil], [data-h-cards] [data-quntil]')) {   // the countdown, in place (inputs keep their state)
    const q = QUESTIONS.find((x) => x.id === el.dataset.quntil);
    setText(el, qLeftText(q, now));
  }
}
const qHeld = {};   // question id -> when the page last asked the hook to wait longer
function holdQuestion(id) {
  const t = Date.now();
  if (t - (qHeld[id] || 0) < 3000) return;
  qHeld[id] = t;
  SOURCE.holdQuestion(id);
}
/* What the card's inputs say: question text -> { labels, other }, and whether every question has an answer. */
function questionPicks(card, q) {
  const picks = {};
  let complete = true;
  q.questions.forEach((x, i) => {
    const boxes = [...card.querySelectorAll(`input[data-qi="${i}"][data-qk]`)].filter((b) => b.checked);
    const labels = boxes.filter((b) => b.dataset.qk !== 'other').map((b) => x.options[Number(b.dataset.qk)].label);
    const otherOn = boxes.some((b) => b.dataset.qk === 'other');
    const other = otherOn ? card.querySelector(`.qother-text[data-qi="${i}"]`).value.trim() : '';
    if (otherOn && !other) complete = false;
    if (!labels.length && !other) complete = false;
    picks[x.question] = { labels, other };
  });
  return { picks, complete };
}
function onQuestionInput(e) {
  const card = e.target.closest('[data-qcard]');
  const q = card && QUESTIONS.find((x) => x.id === card.dataset.qcard);
  if (!q) return;
  // typing a free answer picks その他
  if (e.target.classList.contains('qother-text') && e.target.value) { const box = e.target.parentElement.querySelector('input[data-qk="other"]'); if (box) box.checked = true; }
  const send = card.querySelector('[data-qsend]');
  if (send) send.disabled = !questionPicks(card, q).complete;
  if (send) holdQuestion(q.id);   // someone is answering: the hook waits a little longer
}
function onQuestionClick(e) {
  const r = e.target.closest('[data-qrelease]');
  if (r) { r.disabled = true; SOURCE.releaseQuestion(r.dataset.qrelease); return; }
  const b = e.target.closest('[data-qsend]');
  if (!b) return;
  const card = b.closest('[data-qcard]'), q = QUESTIONS.find((x) => x.id === b.dataset.qsend);
  if (!q) return;
  const { picks, complete } = questionPicks(card, q);
  if (!complete) return;
  b.disabled = true;
  SOURCE.answerQuestion(q.id, picks);
}
// The same handlers for the panel's cards and the board's: the same state (QUESTIONS), the same sending (SOURCE).
for (const id of ['questions', 'q-strip']) { $(id).addEventListener('input', onQuestionInput); $(id).addEventListener('click', onQuestionClick); }
/* 2.3.5 (requester 10-19: "このヘッダーの許可のチップクリックでボード表示してほしい"): the 質問 chip opens the board that
   already lists what waits for a permission (the task board, its strip on top) with the questions waiting over it,
   panel open or not; the 許可待ち chip opens the same board. The chips are hidden while nothing waits (no no-op chip). */
$('chip-ask').addEventListener('click', (e) => { tb.waitView = true; openTaskBoard(e.currentTarget); });

/* ---------- popovers: project switcher, session picker, robot picker ---------- */
const popEl = $('pop');
const pop = { anchor: null, kind: null, q: '' };
function openPop(anchor, kind) {
  if (pop.anchor === anchor && !popEl.hidden) { closePop(); return; }
  if (pop.anchor) pop.anchor.setAttribute('aria-expanded', 'false');
  pop.anchor = anchor; pop.kind = kind; pop.q = '';
  const titles = { project: tl('panel.pop.project'), lists: tl('panel.pop.lists'), robots: tl('panel.pop.robots') };
  popEl.setAttribute('aria-label', titles[kind]);
  popEl.innerHTML = `<p class="pop-title">${esc(titles[kind])}<small data-pop-count></small></p>${kind === 'project' && ROOMS.length <= 6 ? '' : `<input type="search" class="pop-search" placeholder="${kind === 'project' ? esc(tl('panel.pop.find.name')) : esc(tl('panel.pop.find.id'))}" aria-label="${esc(tl('panel.pop.search.aria', { title: titles[kind] }))}">`}${kind === 'project' ? '' : `<div class="pop-quick" role="group" aria-label="${esc(tl('panel.pop.quick'))}"><button type="button" data-quick="all">${esc(tl('panel.scope.all'))}</button><button type="button" data-quick="active">${esc(tl('panel.pop.quick.active'))}</button><button type="button" data-quick="waiting">${esc(tl('panel.pop.quick.waiting'))}</button><button type="button" data-quick="none">${esc(tl('panel.pop.quick.none'))}</button></div>`}<div class="pop-body"></div>`;
  renderPopBody();
  popEl.hidden = false;
  anchor.setAttribute('aria-expanded', 'true');
  placePop();
  const first = popEl.querySelector('.pop-search') || popEl.querySelector('[role="option"][aria-selected="true"]') || popEl.querySelector('input, button');
  if (first) first.focus({ preventScroll: true });
}
function closePop(back = true) {
  if (popEl.hidden) return;
  popEl.hidden = true;
  const a = pop.anchor;
  pop.anchor = null; pop.kind = null;
  if (a) { a.setAttribute('aria-expanded', 'false'); if (back && document.contains(a)) a.focus({ preventScroll: true }); }
}
function placePop() {
  const r = pop.anchor.getBoundingClientRect(), vw = window.innerWidth, vh = window.innerHeight, w = Math.min(380, vw - 16);
  popEl.style.width = `${w}px`;
  popEl.style.left = `${Math.max(8, Math.min(r.left, vw - w - 8))}px`;
  const below = vh - r.bottom - 14, above = r.top - 14;
  if (below >= 280 || below >= above) { popEl.style.top = `${r.bottom + 6}px`; popEl.style.bottom = 'auto'; popEl.style.maxHeight = `${below}px`; }
  else { popEl.style.top = 'auto'; popEl.style.bottom = `${vh - r.top + 6}px`; popEl.style.maxHeight = `${above}px`; }
}
document.addEventListener('pointerdown', (e) => { if (!popEl.hidden && !popEl.contains(e.target) && !(pop.anchor && pop.anchor.contains(e.target))) closePop(false); }, true);
window.addEventListener('resize', () => { if (!popEl.hidden) placePop(); });
function projectStats(model, id) {
  const sess = SESSIONS.filter((s) => id === 'all' || s.project === id);
  const robotIds = sess.flatMap((s) => s.robots);
  return {
    sessions: sess.length,
    busy: robotIds.filter((r) => robotBadge(r)[0] === 'st-busy').length,
    pend: model.pending.filter((p) => id === 'all' || projectOfRobot(p.who) === id).length,
    live: model.specs.filter((s) => (id === 'all' || s.project === id) && s.bucket === 'live').length,
  };
}
const matchQ = (text) => !pop.q || text.toLowerCase().includes(pop.q);
function renderPopBody() {
  const body = popEl.querySelector('.pop-body');
  if (!body) return;
  const keepFocus = popEl.contains(document.activeElement) && document.activeElement.closest('.pop-body') ? document.activeElement.dataset.fk : null;
  if (pop.kind === 'project') {
    const ids = ['all', ...ROOMS.map((r) => r.id)].filter((id) => id === 'all' || matchQ(`${PROJECT[id].name} ${PROJECT[id].path}`));
    body.innerHTML = `<ul class="pop-list" role="listbox" aria-label="${esc(tl('panel.sb.project'))}">${ids.map((id) => {
      const st = projectStats(latestModel, id), sel = UI.project === id;
      return `<li role="option" tabindex="${sel ? 0 : -1}" aria-selected="${sel ? 'true' : 'false'}" data-pick-project="${esc(id)}" data-fk="pp-${esc(id)}"><span class="po-main"><b>${id === 'all' ? esc(tl('panel.pop.all.projects')) : esc(PROJECT[id].name)}</b><small>${id === 'all' ? esc(tl('panel.pop.n.projects', { n: ROOMS.length })) : esc(PROJECT[id].path)} · ${esc(tl('panel.pg.sessions', { n: st.sessions }))}</small></span><span class="po-badges">${st.pend ? `<span class="state st-waiting">${esc(tl('panel.count.waiting', { n: st.pend }))}</span>` : ''}${st.busy ? `<span class="state st-busy">${esc(tl('panel.pop.busy', { n: st.busy }))}</span>` : ''}${st.live ? `<span class="state st-write">${esc(tl('panel.pop.live', { n: st.live }))}</span>` : ''}</span></li>`;
    }).join('')}</ul>`;
  } else {
    const isLog = pop.kind === 'robots';
    const hidden = isLog ? logState.hiddenRobots : UI.hiddenLists;
    const sess = SESSIONS.filter((s) => inScope(s.project));
    const groups = ROOMS.filter((r) => inScope(r.id)).map((r) => [r, sess.filter((s) => s.project === r.id && matchQ(`${s.id} ${s.room} ${s.robots.map((id) => `${id} ${DEF[id].agent}`).join(' ')} ${sessionBadge(s)[1]}`))]).filter(([, l]) => l.length);
    const rowHTML = (s) => {
      const [c, l] = sessionBadge(s), n = latestModel.tasks.filter((x) => x.list === s.id).length;
      if (!isLog) return `<label class="pg-item"><input type="checkbox" data-pick-list="${esc(s.id)}" data-fk="pl-${esc(s.id)}"${hidden.has(s.id) ? '' : ' checked'}>${pill(s.id, 'main')}<span class="pg-name">${esc(DEF[s.id].agent)}<small>${esc(tl('panel.pop.tasks', { n }))}</small></span><span class="state ${esc(c)}">${esc(l)}</span></label>`;
      const on = s.robots.filter((id) => !hidden.has(id)).length;
      const subsHTML = s.robots.filter((id) => id !== s.id).map((id) => `<label class="pg-item pg-sub"><input type="checkbox" data-pick-robot="${esc(id)}" data-fk="pr-${esc(id)}"${hidden.has(id) ? '' : ' checked'}>${pill(id, DEF[id].role)}<span class="pg-name">${esc(DEF[id].agent)}</span><span class="state ${esc(robotBadge(id)[0])}">${esc(robotBadge(id)[1])}</span></label>`).join('');
      return `<label class="pg-item"><input type="checkbox" data-pick-session="${esc(s.id)}" data-fk="ps-${esc(s.id)}"${on === s.robots.length ? ' checked' : ''}${on > 0 && on < s.robots.length ? ' data-mixed' : ''}>${pill(s.id, 'main')}<span class="pg-name">${esc(DEF[s.id].agent)}<small>${esc(tl('panel.chip.robots', { n: s.robots.length }))}</small></span><span class="state ${esc(c)}">${esc(l)}</span></label>${subsHTML}`;
    };
    body.innerHTML = `<div class="pop-groups">${groups.map(([r, list]) => `<p class="pg-label">${esc(r.name)}</p>${list.map(rowHTML).join('')}`).join('') || `<p class="pop-none">${esc(tl('panel.pop.none'))}</p>`}</div>`;
    body.querySelectorAll('[data-mixed]').forEach((x) => { x.indeterminate = true; });
    const total = isLog ? ROBOT_DEFS.filter((d) => inScope(projectOfRobot(d.id))).length : sess.length;
    const shown = isLog ? ROBOT_DEFS.filter((d) => inScope(projectOfRobot(d.id)) && !hidden.has(d.id)).length : sess.filter((s) => !hidden.has(s.id)).length;
    setText(popEl.querySelector('[data-pop-count]'), tl('panel.pop.count', { shown, total }));
  }
  if (keepFocus) { const again = body.querySelector(`[data-fk="${CSS.escape(keepFocus)}"]`); if (again) again.focus({ preventScroll: true }); }
}
function afterPick() {
  paintScopeButtons();
  renderPopBody();
  if (pop.kind === 'robots') renderLog(true); else renderTaskBoard(latestModel);
}
popEl.addEventListener('input', (e) => { if (e.target.matches('.pop-search')) { pop.q = e.target.value.trim().toLowerCase(); renderPopBody(); } });
popEl.addEventListener('change', (e) => {
  const t = e.target;
  if (t.dataset.pickList) { if (t.checked) UI.hiddenLists.delete(t.dataset.pickList); else UI.hiddenLists.add(t.dataset.pickList); }
  else if (t.dataset.pickRobot) { if (t.checked) logState.hiddenRobots.delete(t.dataset.pickRobot); else logState.hiddenRobots.add(t.dataset.pickRobot); }
  else if (t.dataset.pickSession) { for (const id of SESSIONS.find((s) => s.id === t.dataset.pickSession).robots) { if (t.checked) logState.hiddenRobots.delete(id); else logState.hiddenRobots.add(id); } }
  else return;
  afterPick();
});
popEl.addEventListener('click', (e) => {
  const opt = e.target.closest('[data-pick-project]');
  if (opt) { setProject(opt.dataset.pickProject); closePop(); return; }
  const q = e.target.closest('[data-quick]');
  if (!q) return;
  const isLog = pop.kind === 'robots', hidden = isLog ? logState.hiddenRobots : UI.hiddenLists;
  for (const s of SESSIONS.filter((x) => inScope(x.project))) {
    const [c] = sessionBadge(s);
    const keep = q.dataset.quick === 'all' || (q.dataset.quick === 'active' && c !== 'st-idle') || (q.dataset.quick === 'waiting' && c === 'st-waiting');
    for (const id of isLog ? s.robots : [s.id]) { if (keep) hidden.delete(id); else hidden.add(id); }
  }
  afterPick();
});
popEl.addEventListener('keydown', (e) => {
  const opt = e.target.closest('[role="option"]');
  if (!opt) { if (e.key === 'ArrowDown' && e.target.matches('.pop-search')) { const f = popEl.querySelector('[role="option"], .pop-body input'); if (f) { e.preventDefault(); f.focus(); } } return; }
  const opts = [...popEl.querySelectorAll('[role="option"]')], i = opts.indexOf(opt);
  const go = (j) => { e.preventDefault(); opts.forEach((o) => { o.tabIndex = -1; }); opts[j].tabIndex = 0; opts[j].focus(); };
  if (e.key === 'ArrowDown') go(Math.min(opts.length - 1, i + 1));
  else if (e.key === 'ArrowUp') go(Math.max(0, i - 1));
  else if (e.key === 'Home') go(0);
  else if (e.key === 'End') go(opts.length - 1);
  else if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); opt.click(); }
});
document.addEventListener('click', (e) => {
  const sb = e.target.closest('[data-scope-btn]');
  if (sb) { openPop(sb, 'project'); return; }
  const pk = e.target.closest('[data-picker]');
  if (pk) { openPop(pk, pk.dataset.picker); return; }
  const sp = e.target.closest('[data-set-project]');
  if (sp) setProject(UI.project === sp.dataset.setProject ? 'all' : sp.dataset.setProject);
});

/* ---------- event ticker ---------- */
const tickerItems = [];
const fmtClock = (sec) => { const s = Math.floor(sec) % 86400; return [Math.floor(s / 3600), Math.floor(s / 60) % 60, s % 60].map((v) => String(v).padStart(2, '0')).join(':'); };
function emitEvents(prev, now) {
  for (let k = Math.floor(prev / LOOP); k <= Math.floor(now / LOOP); k++) {
    for (const [et, who, kind, what, perm] of EVENTS) {
      const abs = k * LOOP + et;
      if (abs > prev && abs <= now) {
        if (perm && ruleCovers(PERM_BY_ID[perm], abs)) continue;   // an "always allow" rule answered it: no prompt at all
        const item = { abs, who, kind, what, perm, seq: ++logSeq };
        tickerItems.unshift(item);
        logItems.unshift(item);
      }
    }
  }
  tickerItems.length = Math.min(tickerItems.length, 40);
  logItems.length = Math.min(logItems.length, 600);
}
function renderTicker() {
  setHTML($('ticker'), tickerItems.filter((e) => inScope(projectOfRobot(e.who))).slice(0, 5).map((e) => `<li><time>${fmtClock(BASE_CLOCK + e.abs)}</time>${pill(e.who, DEF[e.who].role)}<span class="kind">${esc(e.kind)}</span><span class="what">${esc(e.what)}</span></li>`).join(''));
}

/* ---------- zooming into a board: camera flight, then the board as a page ---------- */
const zoom = { zoomed: false, returnPose: null, opener: null, waitFor: null };   // waitFor: a robot whose card is open, not yet in the scene
let camTween = null;
const viewTarget = new THREE.Vector3();
function flyTo(pos, target, fromTarget, dur, done) {
  camTween = { p0: camera.position.clone(), t0: fromTarget.clone(), p1: pos.clone(), t1: target.clone(), start: performance.now(), dur, done };
}
function stepTween(ms) {
  if (!camTween) return;
  const k = camTween.dur <= 0 ? 1 : Math.min(1, (ms - camTween.start) / (camTween.dur * 1000));
  const e = k < 0.5 ? 4 * k * k * k : 1 - Math.pow(-2 * k + 2, 3) / 2;
  camera.position.lerpVectors(camTween.p0, camTween.p1, e);
  viewTarget.lerpVectors(camTween.t0, camTween.t1, e);
  if (k >= 1) { const done = camTween.done; camTween = null; if (done) done(); }
}
// The show class lands a frame later; a hide in between cancels it (an Escape in that frame used to reopen the card).
function showOverlay(el) { el.hidden = false; el._showing = true; requestAnimationFrame(() => { if (el._showing) el.classList.add('show'); }); }
function hideOverlay(el) { el._showing = false; el.classList.remove('show'); setTimeout(() => { if (!el.classList.contains('show')) el.hidden = true; }, reduceMotion ? 0 : 240); }
function zoomTo(pose, opener, arrive) {
  if (opener) zoom.opener = opener;
  if (!has3D) { arrive(); return; }
  if (!zoom.zoomed) {
    zoom.returnPose = { p: camera.position.clone(), t: controls.target.clone() };
    zoom.zoomed = true; controls.enabled = false;
    flyTo(pose.p, pose.t, controls.target, reduceMotion ? 0 : 0.9, arrive);
  } else flyTo(pose.p, pose.t, viewTarget, reduceMotion ? 0 : 0.5, arrive);
}
/* What holds the 3D view (ticket 2026-10-20-jui-viz-data-server-from-robot-card-freezes-3d): every screen that takes
   it — the robot's card, the spec board, the task board, the data server's sheet, the 単価 sheet — holds it while it is
   open. A screen holds as it opens, before it closes the one it replaces, and lets go as it closes; the camera flies
   back and the orbit takes input again only when the last one lets go (and only if it was zoomed: a sheet opened from
   the 3D did not move the camera). The card used to close "keeping the zoom" for whatever came next, and a sheet that
   does not zoom never gave it back: the 3D froze (zoomed, the orbit off) after card → rack → back. */
const VIEW_HOLD = new Set();
function holdView(name) { VIEW_HOLD.add(name); }
function releaseView(name) {
  if (!VIEW_HOLD.delete(name) || VIEW_HOLD.size) return;
  zoomBack();
}
function zoomBack() {
  if (has3D && zoom.returnPose && zoom.zoomed) {    // not zoomed: nothing to fly back from (a pose kept from before)
    const back = zoom.returnPose;
    flyTo(back.p, back.t, viewTarget, reduceMotion ? 0 : 0.8, () => { controls.target.copy(back.t); zoom.zoomed = false; controls.enabled = true; controls.update(); });
  }
  if (zoom.opener && document.contains(zoom.opener)) zoom.opener.focus({ preventScroll: true });
}
const boardProject = (pref) => pref || (UI.project !== 'all' ? UI.project : SOURCE.mode === 'demo' ? 'shop' : ((ROOMS.find((r) => r.shown) || ROOMS[0] || {}).id));
function meshPose(mesh, w, h, px, py, dist) {
  const c = mesh.localToWorld(new THREE.Vector3(px === undefined ? 0 : (px - 0.5) * w, py === undefined ? 0 : (0.5 - py) * h, 0));
  const n = new THREE.Vector3(0, 0, 1).applyQuaternion(mesh.getWorldQuaternion(new THREE.Quaternion()));
  return { p: c.clone().add(n.multiplyScalar(dist)), t: c };
}
function specPose(i, pref) {
  if (SOURCE.mode === 'live') return liveBoardPose(i >= 0 ? SPECS[i].project : boardProject(pref), 'spec', i);
  if (i >= 0 && SPECS[i].project === 'shop') { const p = sbTile(SHOP_POS[i]), c = sbPoint(p.x + SB.tw / 2, p.y + SB.th / 2); return { p: c.clone().add(new THREE.Vector3(0, 0, 2.2)), t: c }; }
  const proj = i >= 0 ? SPECS[i].project : boardProject(pref);
  if (proj === 'shop') { const c = new THREE.Vector3(SB.cx, SB.cy, SB.z); return { p: c.clone().add(new THREE.Vector3(0, 0, 4.6)), t: c }; }
  const pb = PBOARD[proj], t = i >= 0 && pb.tiles.find((q) => q.i === i);
  return t ? meshPose(pb.mesh, pb.w, pb.h, (t.x + t.w / 2) / pb.W, (t.y + t.h / 2) / pb.H, 1.6) : meshPose(pb.mesh, pb.w, pb.h, undefined, undefined, pb.w * 1.15 + 0.6);
}
function taskPose(pref) {
  if (SOURCE.mode === 'live') return liveBoardPose(boardProject(pref), 'tasks');
  const proj = boardProject(pref);
  if (proj === 'shop') { const c = new THREE.Vector3(KB.cx, KB.cy, KB.z); return { p: c.clone().add(new THREE.Vector3(0, 0, 3.4)), t: c }; }
  const pb = PBOARD[proj];
  return meshPose(pb.mesh, pb.w, pb.h, undefined, undefined, pb.w * 1.15 + 0.6);
}

/* ---------- spec board up close: every spec (overview) or one spec as a readable sheet ---------- */
const wbEl = $('wb'), wbCode = $('wb-code'), wbNav = $('wb-nav'), wbBody = $('wb-body'), wbSideList = $('wb-side-list');
const wb = { open: false, idx: -1, lastActive: null, q: '', app: 'all', flowFit: false };
/* The data flow diagram (2.3.5): at the sheet's text size (Mermaid's 16 px × FLOW_SCALE = 12 px), with a scroll bar
   when it is wider than the section — fitted, a long flow's text came out at 8 px — or fitted on request. */
const FLOW_SCALE = 0.75;
function flowZoomApply(svg) {
  if (!svg || !svg.viewBox || !svg.viewBox.baseVal) return;
  const vb = svg.viewBox.baseVal;
  svg.style.maxWidth = wb.flowFit ? `${Math.round(vb.width)}px` : 'none';
  svg.style.width = wb.flowFit ? '100%' : `${Math.round(vb.width * FLOW_SCALE)}px`;
  svg.style.height = 'auto';
}
wbCode.addEventListener('click', (e) => {
  const b = e.target.closest('[data-flow-zoom]');
  if (!b) return;
  wb.flowFit = !wb.flowFit;
  b.setAttribute('aria-pressed', String(wb.flowFit)); b.textContent = wb.flowFit ? tl('panel.flow.actual') : tl('panel.flow.fit');
  flowZoomApply(b.closest('.flow-mmd-wrap').querySelector('svg'));
});
/* The apps of the rooms in scope (a repo with client/, admin/, … each declaring its own specs): [app, count, specDir],
   in the order the specs come. The board offers them only when there is more than one; 全体 adds them up. */
function wbApps(model) {
  const apps = new Map();
  for (const s of model.specs) if (inScope(s.project)) { const a = apps.get(s.app || '') || [s.app || '', 0, s.specDir || '']; a[1] += 1; apps.set(s.app || '', a); }
  const list = [...apps.values()];
  if (wb.app !== 'all' && !apps.has(wb.app)) wb.app = 'all';
  return list;
}
const inApp = (s) => wb.app === 'all' || (s.app || '') === wb.app;
// a worktree's app is "<app>@<branch>" (the server's key): its app's name and its branch
const appLabel = (app) => {
  const at = app.indexOf('@');
  return at < 0 ? (app || tl('panel.app.root')) : `${app.slice(0, at) || tl('panel.app.root')} ⎇ ${app.slice(at + 1)}`;
};
/* The checkout a spec is read from, when the room shows a worktree of its app beside it: the branch, and on a
   worktree's row its folder in the title. Both rows of a spec in the two checkouts are shown, each with its own tag. */
const coTag = (s) => (s.checkout ? `<span class="co-tag${s.checkout.worktree ? ' co-wt' : ''}" title="${esc(s.checkout.worktree ? tl('panel.co.worktree', { path: s.checkout.worktree }) : tl('panel.co.room'))}">⎇ ${esc(s.checkout.branch)}</span>` : '');
let wbSideOpen = readPref('wbSide', 'open') === 'open';
const narrowWb = () => sceneEl.clientWidth < 800;
function applyWbSide() {
  wbBody.classList.toggle('side-closed', !wbSideOpen);
  const b = $('wb-side-btn');
  b.setAttribute('aria-expanded', String(wbSideOpen));
  b.textContent = wbSideOpen ? tl('panel.ws.close') : tl('panel.ws.open');
}
$('wb-side-btn').addEventListener('click', () => {
  wbSideOpen = !wbSideOpen;
  if (!narrowWb()) writePref('wbSide', wbSideOpen ? 'open' : 'closed');
  applyWbSide();
  if (wbSideOpen) $('wb-search').focus({ preventScroll: true });
});
$('wb-search').addEventListener('input', (e) => { wb.q = e.target.value.trim().toLowerCase(); renderWbSide(latestModel); });
wbSideList.addEventListener('click', (e) => {
  const a = e.target.closest('[data-app]');
  if (a) { wb.app = a.dataset.app; renderWhiteboard(latestModel, true); return; }
  const b = e.target.closest('[data-idx]');
  if (!b) return;
  openWhiteboard(Number(b.dataset.idx));
  if (narrowWb()) { wbSideOpen = false; applyWbSide(); wbCode.focus({ preventScroll: true }); }
});
wbCode.addEventListener('click', (e) => { const b = e.target.closest('.ov-card'); if (b) { openWhiteboard(Number(b.dataset.idx)); wbCode.focus({ preventScroll: true }); } });
wbNav.addEventListener('click', (e) => {
  const b = e.target.closest('button[data-sec]');
  if (!b) return;
  $('wb-follow').checked = false;
  const el = document.getElementById(`wb-sec-${b.dataset.sec}`);
  if (el) wbCode.scrollTop += el.getBoundingClientRect().top - wbCode.getBoundingClientRect().top - 8;
});
// Scrolling by hand stops the automatic follow until the box is ticked again.
['wheel', 'touchmove'].forEach((type) => wbCode.addEventListener(type, () => { if (wb.idx >= 0) $('wb-follow').checked = false; }, { passive: true }));

function openWhiteboard(i, opener, board) {
  holdView('wb');
  if (tb.open) closeTaskBoard();
  if (rbState.id) closeRobot();
  if (i >= 0 && !inScope(SPECS[i].project)) setProject(SPECS[i].project, { camera: false });
  if (i >= 0 && !inApp(SPECS[i])) wb.app = 'all';
  wb.idx = i; wb.lastActive = null; wb.board = board || null;
  wbSideList._shownFor = undefined;   // opened (again): its row is brought into view (wbSideShowOpen)
  if (wb.open) {
    if (opener) zoom.opener = opener;
    $('wb-follow').checked = true;
    wbCode.scrollTop = 0;
    renderWhiteboard(latestModel, true);
    if (has3D && !camTween) { const pose = specPose(i, wb.board); camera.position.copy(pose.p); viewTarget.copy(pose.t); }
    return;
  }
  wb.open = true;
  wbSideOpen = narrowWb() ? false : readPref('wbSide', 'open') === 'open';
  applyWbSide();
  zoomTo(specPose(i, wb.board), opener, () => {
    if (!wb.open) return;
    showOverlay(wbEl);
    $('wb-follow').checked = true;
    renderWhiteboard(latestModel, true);
    $('wb-close').focus({ preventScroll: true });
  });
}
function closeWhiteboard() {
  if (!wb.open) { releaseView('wb'); return; }
  wb.open = false;
  hideOverlay(wbEl);
  releaseView('wb');
}
$('wb-close').addEventListener('click', closeWhiteboard);

function renderWhiteboard(model, force) {
  if (!wb.open) return;
  renderWbSide(model);
  if (wb.idx < 0) renderOverview(model); else renderSheet(model, force);
}
function renderWbSide(model) {
  const q = wb.q, apps = wbApps(model);
  const match = (s) => inScope(s.project) && inApp(s) && (!q || `${s.name} ${s.screen} ${s.file} ${PROJECT[s.project].name}`.toLowerCase().includes(q));
  const groups = BUCKETS.map(([b, label]) => [label, model.specs.map((s, i) => [s, i]).filter(([s]) => s.bucket === b && match(s)).sort(specNewer)]).filter(([, items]) => items.length);
  const n = model.specs.filter((s) => inScope(s.project) && inApp(s)).length;
  keyed(wbSideList, JSON.stringify([UI.project, q, wb.idx, wb.app, apps, groups.map(([label, items]) => [label, items.map(([s, i]) => `${i}:${s.by || ''}:${s.name}`)])]), () => {
    const total = apps.reduce((k, [, c]) => k + c, 0);
    const appsHTML = apps.length > 1 ? `<div class="seg-filter ws-apps" role="group" aria-label="${esc(tl('panel.app.filter'))}">${[['all', total], ...apps].map(([a, c]) => `<button type="button" data-app="${esc(a)}" aria-pressed="${wb.app === a}">${esc(a === 'all' ? tl('panel.app.all') : appLabel(a))}<b>${esc(String(c))}</b></button>`).join('')}</div>` : '';
    const allHTML = appsHTML + `<button type="button" class="ws-item ws-all" data-idx="-1" data-fk="ws--1" aria-current="${wb.idx === -1}"><span class="dot" aria-hidden="true"></span><span class="nm">${esc(tl('panel.ws.all'))}</span><span></span><small>${esc(scopeLabel())} · ${esc(tl('panel.ws.progress', { n }))}</small></button>`;
    const bodyHTML = groups.map(([label, items]) => `<p class="ws-group"><span>${esc(label)}</span><b>${items.length}</b></p>${items.map(([s, i]) => `<button type="button" class="ws-item b-${esc(s.bucket)}" data-idx="${i}" data-fk="ws-${i}" aria-current="${wb.idx === i}"${roleVar(s)}><span class="dot" aria-hidden="true"></span><span class="nm">${coTag(s)}${esc(s.name)}</span>${s.by ? pill(s.by, DEF[s.by].role) : '<span></span>'}<small></small></button>`).join('')}`).join('');
    return allHTML + (bodyHTML || `<p class="ws-none">${esc(tl('panel.ws.none'))}</p>`);
  });
  wbSideList.querySelectorAll('.ws-item:not(.ws-all)').forEach((b) => { const x = model.specs[+b.dataset.idx]; paintStatus(b.lastElementChild, specStatus(x, UI.project === 'all' ? `${PROJECT[x.project].name} · ` : '')); });
  wbSideShowOpen();
}
/* The open spec's row in view (ticket 2026-10-23-viz-whiteboard-list-not-scrolled-to-opened-spec): every way of opening
   one — the panel, a board card, this list, a robot, the URL, the follow — ends in wb.idx and this list's redraw, so it
   is done here, once per spec opened. Only the list scrolls (never the page); a list not shown waits until it is. */
function wbSideShowOpen() {
  if (wbSideList._shownFor === wb.idx) return;
  const row = wbSideList.querySelector('.ws-item[aria-current="true"]');
  if (!row || !row.offsetParent) return;
  const box = wbSideList.getBoundingClientRect(), r = row.getBoundingClientRect();
  if (r.top < box.top) wbSideList.scrollTop -= box.top - r.top + 8;
  else if (r.bottom > box.bottom) wbSideList.scrollTop += r.bottom - box.bottom + 8;
  wbSideList._shownFor = wb.idx;
}

/* Colours of the spec sheet (2.3.5, requester 10-19: "遷移のところの遷移先が白の太字見にくい 色少しつけてみやすくしてほしい。
   あと状態変数の型も型ごとに色分けできない？"). One source for three things: a transition's tag (its kind, from the spec's
   type / method and the destination's words; the kind is written in the tag too, so the colour is never the only cue),
   a state variable's type text, and their legend in the 「?」 dialog (SPEC_HELP_HTML). The colours themselves are CSS
   variables (app.css, light and dark), each at least 4.5:1 against where it is drawn. */
const TRANSITION_KINDS = [   // [key, the tag's words, what it is told by, the legend's words] — the first that matches wins
  ['none', tl('panel.tk.none'), /遷移なし|画面内|no transition|\bnone\b|alert|confirmationdialog|ダイアログ|toast|トースト/i, tl('panel.tk.none')],
  ['external', tl('panel.tk.external'), /外部|ブラウザ|browser|https?:|\burl\b|tel:|mailto:|地図アプリ|マップアプリ|\bmaps? app|google ?maps|apple ?maps|safari|openurl|linking/i, tl('panel.tk.external.full')],   // a screen named …MAP… is not an app
  ['back', 'pop / dismiss', /\bpop|dismiss|戻る|\bback\b|閉じる/i, tl('panel.tk.back.full')],
  ['replace', 'replace / root', /replace|\broot|navigatetoscreen|置き換|入れ替/i, tl('panel.tk.replace.full')],
  ['modal', 'sheet / modal', /sheet|modal|present|fullscreen|cover|シート|モーダル/i, tl('panel.tk.modal.full')],
  ['push', 'push', /push|navigat|router|遷移/i, tl('panel.tk.push.full')],
];
// No kind written (requester's ruling 10-19): a destination that names a screen (or a path) is 「画面へ」 in a colour
// of its own — never shown as push, the page does not guess what the spec does not say. Grey only when the destination
// names nothing either: empty, blank, or a placeholder (TRANSITION_PLACEHOLDER: 未定・未設定・不明・TBD・TBA・TODO・N/A・
// null・undefined, or only ? / - / — / ー / … / ・ / . characters).
const TRANSITION_SCREEN = ['screen', tl('panel.tk.screen'), null, tl('panel.tk.screen.full')];
const TRANSITION_OTHER = ['other', tl('panel.tk.other'), null, tl('panel.tk.other')];
const TRANSITION_PLACEHOLDER = /^(?:未定|未設定|不明|tbd|tba|todo|n\/a|null|undefined|[?？\-—―ー…・.]+)$/i;
// The type / method decides when it is written and names a kind; only then the destination's words (a word in the
// destination — 「sheet 表示」, 「MAP」, 「…Sheet」 — must not beat what the spec says the transition is).
const kindOf = (text) => (text ? TRANSITION_KINDS.find((k) => k[2].test(text)) : null);
function transitionKind(type, dest) {
  const d = String(dest || '').trim();
  return kindOf(String(type || '').trim()) || kindOf(d) || (d && !TRANSITION_PLACEHOLDER.test(d) ? TRANSITION_SCREEN : TRANSITION_OTHER);
}
const transitionTag = (dest, type) => {
  const [key, label] = transitionKind(type, dest);
  return `<span class="scr tk tk-${esc(key)}" data-tk="${esc(key)}" title="${esc(dest)}"><span class="tk-k">${esc(label)}</span><span class="tk-d">${esc(SCREEN_JA[dest] || dest)}</span></span>`;
};
const TYPE_KINDS = [   // [key, label, sample, test] — Optional first: String? is an Optional
  ['optional', tl('panel.ty.optional'), 'String?', (t) => /\?\s*$/.test(t)],
  ['array', tl('panel.ty.array'), '[Item]', (t) => /^\s*[[{]|^\s*(array|dictionary|set|list|map)\b/i.test(t)],
  ['string', 'String', 'String', (t) => /^\s*string\s*$/i.test(t)],
  ['bool', 'Bool', 'Bool', (t) => /^\s*(bool|boolean)\s*$/i.test(t)],
  ['number', tl('panel.ty.number'), 'Int', (t) => /^\s*(u?int\d*|double|float|cgfloat|number|decimal|long)\s*$/i.test(t)],
  ['color', 'Color', 'Color', (t) => /^\s*(color|uicolor|cgcolor)\s*$/i.test(t)],
];
const TYPE_OTHER = ['custom', tl('panel.ty.custom'), 'Visibility'];
const typeKind = (t) => TYPE_KINDS.find((k) => k[3](String(t || ''))) || TYPE_OTHER;
const typeCell = (t) => { const k = esc(typeKind(t)[0]); return `<td class="mono ty ty-${k}" data-ty="${k}">${esc(t)}</td>`; };
const COLOR_LEGEND_HTML = `<p>${esc(tl('panel.help.kinds'))}</p>
<p class="seg-legend sh-legend sh-kinds">${[...TRANSITION_KINDS, TRANSITION_SCREEN, TRANSITION_OTHER].map(([key, label, , full]) => { const more = full.startsWith(label) ? full.slice(label.length) : '';
  return `<span class="scr tk tk-${esc(key)}${more ? '' : ' tk-solo'}" data-tk="${esc(key)}"><span class="tk-k">${esc(label)}</span>${esc(more)}</span>`; }).join('')}</p>
<p>${esc(tl('panel.help.types'))}</p>
<p class="seg-legend sh-legend sh-types">${[...TYPE_KINDS, TYPE_OTHER].map(([key, label, sample]) => `<span><code class="mono ty ty-${esc(key)}" data-ty="${esc(key)}">${esc(sample)}</code> ${esc(label)}</span>`).join('')}</p>`;
const SWATCHES = `<span><i class="sw sw-writing"></i>${esc(tl('panel.sw.writing'))}</span><span><i class="sw sw-written"></i>${esc(tl('panel.sw.written'))}</span><span><i class="sw sw-impl"></i>${esc(tl('panel.sw.impl'))}</span><span><i class="sw sw-tested"></i>${esc(tl('panel.sw.tested'))}</span><span><i class="sw sw-empty"></i>${esc(tl('panel.sw.empty'))}</span>`;
/* The explanation of 「spec の進み具合」 (2.3.4, requester 10-19: "specの進み具合の説明をボードから消してその代わりに？
   ボタンおいて押したらモーダルで説明出して", for the panel and the overview alike: "同じで"). It used to sit under the
   panel's heading and over the overview's cards; now both places have a 「?」 next to the heading and both open this
   one dialog, built from this one source (the two can no longer say different things). */
const SPEC_HELP_HTML = `<p>${esc(tl('panel.help.watch'))}</p>
<p>${esc(tl('panel.help.bar'))}</p>
<p class="seg-legend sh-legend">${SWATCHES}</p>
<p>${esc(tl('panel.help.open'))}</p>
${COLOR_LEGEND_HTML}`;
let specHelp = null;
function openSpecHelp(opener) {
  closeSpecHelp(false);
  const el = document.createElement('div');
  el.className = 'spec-help'; el.id = 'spec-help';
  el.innerHTML = `<div class="sh-box" role="dialog" aria-modal="true" aria-labelledby="sh-title" tabindex="-1"><div class="sh-head"><h3 id="sh-title">${esc(tl('panel.help.title'))}</h3><button type="button" class="mini-btn" data-sh-close>${esc(tl('panel.close'))}</button></div><div class="sh-body">${SPEC_HELP_HTML}</div></div>`;
  document.body.append(el);
  const onKey = (e) => {
    if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); closeSpecHelp(true); return; }
    if (e.key !== 'Tab') return;
    const box = el.querySelector('.sh-box'), list = [...box.querySelectorAll('button, [href], input, [tabindex]:not([tabindex="-1"])')];
    const first = list[0], last = list[list.length - 1];
    if (!box.contains(document.activeElement)) { e.preventDefault(); first.focus(); }
    else if (e.shiftKey && (document.activeElement === first || document.activeElement === box)) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  };
  document.addEventListener('keydown', onKey, true);   // first, so Esc closes this and not the board under it
  el.addEventListener('click', (e) => { if (e.target === el || e.target.closest('[data-sh-close]')) closeSpecHelp(true); });
  specHelp = { el, opener, onKey };
  el.querySelector('[data-sh-close]').focus();
}
function closeSpecHelp(back) {
  if (!specHelp) return;
  const { el, opener, onKey } = specHelp;
  specHelp = null; el.remove(); document.removeEventListener('keydown', onKey, true);
  if (back && opener && document.contains(opener)) opener.focus({ preventScroll: true });
}
document.addEventListener('click', (e) => { const b = e.target.closest('[data-spec-help]'); if (b) openSpecHelp(b); });
// the overview shows the 「?」 instead of its legend; an open spec keeps its own legend (what the marks on the sheet mean)
function wbHelpMode(overview) { $('spec-help-board').hidden = !overview; $('wb-legend').hidden = overview; }
const SHEET_LEGEND_LIVE = `<span class="lg-writing">${esc(tl('panel.lg.writing'))}</span><span class="lg-empty">${esc(tl('panel.lg.empty'))}</span><span><b class="m-done">✓</b>${esc(tl('panel.lg.live.done'))}</span><span><b class="m-todo">○</b>${esc(tl('panel.lg.live.todo'))}</span><span><b class="m-test">▶</b>${esc(tl('panel.lg.testing'))}</span><span>${esc(tl('panel.lg.live.unmeasured'))}</span>`;
const SHEET_LEGEND = `<span class="lg-writing">${esc(tl('panel.lg.writing'))}</span><span class="lg-empty">${esc(tl('panel.lg.empty'))}</span><span><b class="m-done">✓</b>${esc(tl('panel.lg.done'))}</span><span><b class="m-doing">●</b>${esc(tl('panel.lg.doing'))}</span><span><b class="m-todo">○</b>${esc(tl('panel.lg.todo'))}</span><span><b class="m-test">▶</b>${esc(tl('panel.lg.testing'))}</span><span><b class="m-flaky">⚠</b>${esc(tl('panel.lg.flaky'))}</span><span>${esc(tl('panel.lg.demo'))}</span>`;
function setHead(title, file, stCls, stText, whoHTML) {
  setText($('wb-title'), title);
  setText($('wb-file'), file);
  const st = $('wb-status'), cls = `state ${stCls}`;
  if (st.className !== cls) st.className = cls;
  paintStatus(st, typeof stText === 'object' ? stText : { text: stText, title: '' });   // a spec's: with its time (specStatus)
  setHTML($('wb-who'), whoHTML);
}
function specSummary(s) {
  if (s.bucket === 'todo') return tl('panel.sum.nofile');
  const w = s.written.reduce((a, b) => a + b, 0) / 7;
  if (s.measure) {
    const m = s.measure, layout = m.layout === null ? 'layout —' : m.layout ? tl('panel.sum.layout.yes') : tl('panel.sum.layout.no');
    return [tl('panel.sum.written', { w: pct(w) }), layout, tl('panel.sum.related', { done: m.related.done, total: m.related.total }), tl('panel.sum.tests', { n: s.implN[6], all: s.totals[6] })].join(' · ');
  }
  return [tl('panel.sum.written', { w: pct(w) }), tl('panel.sum.impl') + (s.implPhase ? `${sumImpl(s.implN)}/${sumImpl(s.totals)}` : '—'), tl('panel.sum.test') + (s.implPhase ? `${s.implN[6]}/${s.totals[6]}` : '—')].join(' · ');
}
function renderOverview(model) {
  const apps = wbApps(model), inS = model.specs.filter((s) => inScope(s.project) && inApp(s)), c = bucketCounts(inS);
  const dirs = [...new Set(inS.map((s) => s.specDir).filter(Boolean))];
  const where = dirs.length > 1 ? tl('panel.ov.dirs', { n: dirs.length }) : `${dirs[0] || 'docs/screens/json'}/`;
  const title = `${tl('panel.ov.title')}${UI.project === 'all' ? '' : ` · ${PROJECT[UI.project].name}`}${wb.app !== 'all' && apps.length > 1 ? ` · ${appLabel(wb.app)}` : ''}`;
  setHead(title, tl('panel.ov.file', { where, n: inS.length }), 'st-busy', tl('panel.ov.counts', { live: c.live, partial: c.partial, todo: c.todo, done: c.done }), '');
  wbNav.hidden = true; $('wb-follow-label').hidden = true;
  wbHelpMode(true);
  const sig = JSON.stringify(['ov', UI.project, wb.app, model.specs.map((s) => `${s.bucket}:${s.by || ''}:${s.advancedAt || 0}`)]);
  if (wbCode._sig !== sig) {
    wbCode.innerHTML = !inS.length ? `<p class="sc-ph ov-none">${esc(tl('panel.ov.none', { scope: scopeLabel() }))}</p>` : BUCKETS.map(([b, label]) => {
      const items = model.specs.map((s, i) => [s, i]).filter(([s]) => s.bucket === b && inScope(s.project) && inApp(s)).sort(specNewer);
      if (!items.length) return '';
      return `<section class="ov-group" aria-label="${esc(label)}"><h3>${esc(label)}<small>${items.length}</small></h3><div class="ov-grid">${items.map(([s, i]) => `<button type="button" class="ov-card b-${esc(s.bucket)}" data-idx="${i}"${roleVar(s)}><span class="ov-top"><strong>${coTag(s)}${esc(s.name)}</strong><span class="state"></span></span><code class="ov-file">${UI.project === 'all' ? `${esc(PROJECT[s.project].name)} · ` : ''}${esc(s.file)}</code><span class="ov-who"></span><span class="ov-secs">${SEGS}<span class="ov-labels" aria-hidden="true">${SECTIONS.map((x) => `<span>${esc(x)}</span>`).join('')}</span></span><span class="ov-sum"></span></button>`).join('')}</div></section>`;
    }).join('');
    wbCode._sig = sig; wbCode._html = null;
  }
  wbCode.querySelectorAll('.ov-card').forEach((card) => {
    const s = model.specs[+card.dataset.idx], st = card.querySelector('.state'), cls = `state ${STATUS_CLASS[s.status.kind]}`;
    if (st.className !== cls) st.className = cls;
    paintStatus(st, specStatus(s));
    setHTML(card.querySelector('.ov-who'), s.by ? `${robotWho(s.by)}<span>${esc(robotState[s.by].act)}</span>` : `<span>${esc(s.note)}</span>`);
    paintSegs(card.querySelector('.segs'), s);
    setText(card.querySelector('.ov-sum'), specSummary(s));
  });
}

const TYPE_JA = { View: tl('panel.type.container'), SafeAreaView: tl('panel.type.safearea'), ScrollView: tl('panel.type.scroll'), Label: tl('panel.type.label'), TextField: tl('panel.type.textfield'), TextView: tl('panel.type.textview'), Button: tl('panel.type.button'), Image: tl('panel.type.image'), NetworkImage: tl('panel.type.image'), Collection: tl('panel.type.collection'), Indicator: tl('panel.type.indicator'), Segment: tl('panel.type.segment'), SelectBox: tl('panel.type.select'), CheckBox: tl('panel.type.checkbox'), Switch: tl('panel.type.switch'), TabView: tl('panel.type.tabs') };
const PLATFORM_JA = { ios: 'iOS', android: 'Android', web: 'Web' };
const CHIP = { empty: 'c-empty', writing: 'c-writing', written: '', impl: 'c-impl', done: 'c-done', test: 'c-test', tested: 'c-done' };
// A section with nothing implemented or tested yet stays plain; colour marks progress.
const chipCls = (g) => ((g.kind === 'impl' || g.kind === 'test') && g.f === 0 ? '' : CHIP[g.kind]);
/* [section, card title, key in the spec file, full width] */
const SHEET = [[0, tl('panel.sec.overview'), 'metadata', true], [1, tl('panel.sec.structure'), 'structure', true], [2, tl('panel.sec.state'), 'stateManagement', false], [3, tl('panel.sec.data'), 'dataFlow', false], [4, tl('panel.sec.actions'), 'userActions', false], [5, tl('panel.sec.transitions'), 'transitions', false], [6, tl('panel.sec.branches'), 'branchContracts', true], [7, tl('panel.sec.related'), 'relatedFiles', true]];
const reveal = (n, w) => (w >= 1 ? n : w <= 0 ? 0 : Math.min(n, Math.max(1, Math.ceil(n * w))));
function markOf(s, model, k, i) {
  if (s.id === 'cart' && k === 6 && model.t >= 18) {
    const st = (model.tests.rows[i] || {}).status;
    if (st === 'passed') return ['✓', 'm-done', ''];
    if (st === 'flaky') return ['⚠', 'm-flaky', ''];
    if (st === 'running') return ['▶', 'm-test', 'is-testing'];
    return ['○', 'm-todo', ''];
  }
  if (!s.implPhase || (s.unmeasured && s.unmeasured[k])) return ['', '', ''];
  const n = s.implN[k];
  if (i < n) return ['✓', 'm-done', ''];
  if (i === n && s.implIdx === k) return ['●', 'm-doing', 'is-doing'];
  return ['○', 'm-todo', ''];
}
function wfElement([type, id, desc], state, idx) {
  let shapeHTML;
  if (type === 'Button') shapeHTML = `<b class="wf-btn">${esc(desc)}</b>`;
  else if (type === 'TextField' || type === 'TextView') shapeHTML = `<span class="wf-input">${esc(desc)}</span>`;
  else if (type === 'SelectBox') shapeHTML = `<span class="wf-input">${esc(desc)} ▾</span>`;
  else if (type === 'Collection') shapeHTML = '<span class="wf-tiles"><i></i><i></i><i></i></span>';
  else if (type === 'Indicator') shapeHTML = '<span class="wf-spin"></span>';
  else if (type === 'Segment') shapeHTML = '<span class="wf-seg"><i></i><i></i><i></i></span>';
  else if (type === 'Image' || type === 'NetworkImage') shapeHTML = '<span class="wf-img"></span>';
  else if (type === 'Switch' || type === 'CheckBox') shapeHTML = `<span class="wf-check"><span class="bar short"></span><i class="${type === 'CheckBox' ? 'cb' : ''}"></i></span>`;
  else shapeHTML = `<span class="bar${type === 'Label' ? ' short' : ''}"></span>`;
  return `<div ${idx === undefined ? '' : `data-wf="${esc(idx)}" `}class="wf s-${esc(state)}"><span class="wf-id">${esc(id)}</span>${shapeHTML}</div>`;
}
/* The structure as a tree (ticket 2026-10-20-jui-viz-spec-structure-shows-no-nesting). The server sends each
   component as [type, id, desc, depth], depth-first (sheet.py); a row's parent is the nearest row above it one level
   up. TREE_STEP: the list's indent per level. WF_PAD: a box's inner padding in the phone frame by its depth — the cap
   that keeps a deep tree readable in the 196 px frame: 6 px at depths 0–2, 2 px at 3–5, none from 6 (a 1 px border
   only), so a box at depth 4 is still about 110 px wide and one at depth 15 about 80 px. */
const TREE_STEP = 14;
const WF_PAD = (depth) => (depth < 3 ? 6 : depth < 6 ? 2 : 0);
const hasDepths = (rows) => rows.some((c) => Array.isArray(c) && Number.isInteger(c[3]));
// The depths as drawn: the first row at 0, a row never more than one level below the row above it (a bad depth from
// the wire cannot make a row without a parent).
function treeDepths(rows) {
  let prev = -1;
  return rows.map((c) => { const raw = Number.isInteger(c[3]) && c[3] > 0 ? c[3] : 0; prev = Math.min(raw, prev + 1); return prev; });
}
// The list's tree lines for each row: one cell per level above it — 'v' (an ancestor's later sibling below: a line
// down), 'e' (none) — and its own 't' (a later sibling: ├) or 'l' (the last: └). Depth 0: none.
function treeGuides(depths) {
  const later = depths.map((d, i) => { for (let j = i + 1; j < depths.length; j++) { if (depths[j] < d) return false; if (depths[j] === d) return true; } return false; });
  const open = [];
  return depths.map((d, i) => {
    open.length = d;
    const cells = [];
    for (let k = 1; k < d; k++) cells.push(open[k] ? 'v' : 'e');
    if (d > 0) cells.push(later[i] ? 't' : 'l');
    open[d] = later[i];
    return cells;
  });
}
// The phone frame: a box per row, a child's box inside its parent's.
function wfTree(nodes) {
  let i = 0;
  const levelHTML = (depth) => {
    let outHTML = '';
    while (i < nodes.length && nodes[i].depth === depth) {
      const n = nodes[i++];
      const kidsHTML = i < nodes.length && nodes[i].depth > depth ? levelHTML(depth + 1) : '';
      if (!kidsHTML) { outHTML += wfElement(n.c, n.state, n.idx); continue; }
      const [type, id] = n.c, pad = WF_PAD(depth);
      outHTML += `<div data-wf="${esc(n.idx)}" class="wf wf-box${depth >= 6 ? ' wf-deep' : ''} s-${esc(n.state)}" style="padding:${esc(pad + 2)}px ${esc(pad)}px ${esc(pad)}px"><span class="wf-id">${esc(id || type)}</span>${kidsHTML}</div>`;
    }
    return outHTML;
  };
  return levelHTML(0);
}
/* 分岐's condition and result as formatted JSON (ticket 2026-10-20-jui-viz-spec-branch-json-formatted; requester 10-20:
   「json formatterでフォーマットした感じに」). The server sends a when / then the spec wrote as an object or an array as
   it is (sheet._json_or_text); its cell is an empty placeholder in the sheet's HTML, filled after it is set with
   JSON.stringify(v, null, 2) built from text nodes and spans — keys, strings, numbers and true / false / null each
   coloured — with createElement and textContent only: no value of the spec ever goes through HTML. The block scrolls
   sideways inside itself; over BJ_FOLD lines it is folded, 「全部を見る」 opens it (kept open across redraws). Anything
   else stays the one line of text it was. */
const BJ_FOLD = 12;
const bjCell = (v, i, j, prose = esc) => (isProse(v) ? `<td>${prose(v)}</td>` : v !== null && typeof v === 'object' ? `<td class="bj-cell" data-bj="${esc(i)}:${esc(j)}"></td>` : `<td>${esc(v)}</td>`);
/* Prose from a texts file ({markdown}, ticket 2026-10-23-viz-spec-sheet-shows-md-reference-raw): every prose field of
   the sheet — the description, a part's, an event's, a step's, a transition's condition, a branch's note, an API's
   notes — is drawn the one way, by the history's histMarkdown (text nodes only, so a < stays a character; only
   http(s) links, opened in a new tab). The sheet's HTML holds a placeholder per field (its text's hash in it, so a
   changed text is a changed sheet), filled after it is set. */
const isProse = (v) => !!v && typeof v === 'object' && typeof v.markdown === 'string';
function proseHash(t) { let h = 5381; for (let k = 0; k < t.length; k += 1) h = ((h * 33) ^ t.charCodeAt(k)) >>> 0; return h.toString(36); }
function fillProse(root, texts) {
  for (const el of root.querySelectorAll('[data-md]')) {
    if (el.firstChild) continue;   // filled before, the sheet's HTML unchanged
    const t = texts[+el.dataset.md];
    if (typeof t === 'string') el.append(histMarkdown(t));
  }
}
const BJ_OPEN = new Set();
function jsonBlock(v, key) {
  const text = JSON.stringify(v, null, 2), lines = text.split('\n').length;
  const box = document.createElement('div'), pre = document.createElement('pre');
  box.className = 'bj'; pre.className = 'bj-pre';
  const put = (t, cls) => {
    if (!t) return;
    if (!cls) { pre.append(document.createTextNode(t)); return; }
    const sp = document.createElement('span'); sp.className = cls; sp.textContent = t; pre.append(sp);
  };
  const re = /("(?:[^"\\]|\\.)*")(\s*:)?|(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)|\b(true|false|null)\b/g;
  let at = 0, m;
  while ((m = re.exec(text))) {
    put(text.slice(at, m.index));
    if (m[1]) { put(m[1], m[2] ? 'bj-key' : 'bj-str'); put(m[2]); } else if (m[3]) put(m[3], 'bj-num'); else put(m[4], 'bj-lit');
    at = re.lastIndex;
  }
  put(text.slice(at));
  box.append(pre);
  if (lines > BJ_FOLD) {
    const btn = document.createElement('button');
    btn.type = 'button'; btn.className = 'bj-more';
    const show = (open) => { box.classList.toggle('bj-open', open); btn.setAttribute('aria-expanded', String(open)); btn.textContent = open ? tl('panel.bj.fold') : tl('panel.bj.more', { n: lines }); };
    btn.addEventListener('click', () => { const open = !box.classList.contains('bj-open'); if (open) BJ_OPEN.add(key); else BJ_OPEN.delete(key); show(open); });
    box.classList.add('bj-fold'); show(BJ_OPEN.has(key));
    box.append(btn);
  }
  return box;
}
function fillBranchJSON(root, branches, specId) {
  for (const td of root.querySelectorAll('td[data-bj]')) {
    if (td.firstChild) continue;   // filled before, the sheet's HTML unchanged
    const [i, j] = td.dataset.bj.split(':').map(Number), row = branches[i];
    if (row && row[j] !== null && typeof row[j] === 'object') td.append(jsonBlock(row[j], `${specId}:${i}:${j}`));
  }
}
function renderNav(s) {
  if (wbNav._idx !== wb.idx) { wbNav.innerHTML = SECTIONS.map((label, k) => `<button type="button" data-sec="${k}"><span>${esc(label)}</span><small></small></button>`).join(''); wbNav._idx = wb.idx; }
  [...wbNav.children].forEach((b, k) => { const g = secState(s, k); const cls = chipCls(g); if (b.className !== cls) b.className = cls; setText(b.lastElementChild, g.text); });
}
function renderSheet(model, force) {
  const s = model.specs[wb.idx], d = s.doc, T = model.tests;
  if (SOURCE.mode === 'live') {
    liveWantSheet(s);
    if (!d) {
      setHead(s.name, s.file, STATUS_CLASS[s.status.kind], specStatus(s), s.by ? robotWho(s.by) : '');
      wbNav.hidden = false; $('wb-follow-label').hidden = false;
      setHTML($('wb-legend'), SHEET_LEGEND_LIVE); wbHelpMode(false);
      renderNav(s);
      const failed = LIVE.sheetFailed[s.id];
      setHTML(wbCode, `<p class="sc-ph">${failed ? esc(tl('panel.sheet.failed', { error: failed })) : esc(tl('panel.sheet.loading'))}</p>`);
      wbCode._sig = null;
      return;
    }
  }
  if (SOURCE.mode === 'live') setHead(s.name, s.checkout ? `⎇ ${s.checkout.branch} · ${s.file}` : s.file, STATUS_CLASS[s.status.kind], specStatus(s), s.by ? robotWho(s.by) : '');
  else setHead(tl('panel.sheet.head', { name: s.name, screen: s.screen }), `docs/screens/json/${s.file}`, STATUS_CLASS[s.status.kind], specStatus(s), s.by ? pill(s.by, DEF[s.by].role) : '');
  wbNav.hidden = false; $('wb-follow-label').hidden = false;
  setHTML($('wb-legend'), SOURCE.mode === 'live' ? SHEET_LEGEND_LIVE : SHEET_LEGEND); wbHelpMode(false);
  renderNav(s);
  if (wbCode._sig) { wbCode._sig = null; wbCode._html = null; }

  let activeKey = null;
  const actAttr = (cls, key) => ((cls === 'is-doing' || cls === 'is-testing') && activeKey === null ? (activeKey = key, ' data-act') : '');
  const li = (m, key, innerHTML, depth) => `<li ${depth === undefined ? '' : `data-depth="${esc(depth)}" `}class="rw ${depth === undefined ? '' : 'rw-tree '}${esc(m[2])}"${actAttr(m[2], key)}><span class="mk ${esc(m[1])}">${esc(m[0])}</span><span>${innerHTML}</span></li>`;
  // イベント and 操作: one table (tickets 2026-10-20-jui-viz-spec-events-as-table), the look of the variables above it.
  // Its columns are the spec's own fields, nothing read out of the text; an event's name in one unbroken line.
  const nameTable = (heads, bodyHTML) => `<table class="vt nt"><thead><tr><th><span class="sr">${esc(tl('panel.th.state'))}</span></th>${heads.map((h) => `<th>${esc(h)}</th>`).join('')}</tr></thead><tbody>${bodyHTML}</tbody></table>`;
  const nameCells = (cells, named) => cells.map((c, j) => `<td class="${j === 0 && named ? 'mono nt-name' : 'nt-desc'}">${j === 0 && named ? esc(c) : prose(c)}</td>`).join('');
  const tr = (m, key, cellsHTML) => `<tr class="${esc(m[2])}"${actAttr(m[2], key)}><td class="mk ${esc(m[1])}">${esc(m[0])}</td>${cellsHTML}</tr>`;
  // The first n items of a section; while it is being written the newest one is highlighted instead of marked.
  const pick = (k, arr, n, fresh) => arr.slice(0, n).map((x, i) => [x, i, fresh ? ['', '', i === n - 1 ? 'is-new' : ''] : markOf(s, model, k, i)]);
  const mdTexts = [];
  const prose = (v) => {
    if (!isProse(v)) return esc(v);
    const k = mdTexts.push(v.markdown) - 1;
    return `<span class="sc-md" data-md="${k}" data-mdh="${esc(proseHash(v.markdown))}"></span>`;
  };
  const bodies = [
    (w) => {
      const m = d.metadata;
      const rows = [[tl('panel.meta.name'), `${esc(m.displayName)}${esc(tl('panel.meta.open'))}<span class="mono">${esc(m.name)}</span>${esc(tl('panel.meta.close'))}`], [tl('panel.meta.description'), prose(m.description)], [tl('panel.meta.platforms'), m.platforms.map((p) => `<span class="bdg">${PLATFORM_JA[p] || esc(p)}</span>`).join(' ')], [tl('panel.meta.layout'), m.layoutFile ? `<code>docs/screens/layouts/${esc(m.layoutFile)}.json</code>` : ''], [tl('panel.meta.created'), esc(m.createdAt)]].filter(([, v]) => v !== '');
      return `<dl class="kv">${rows.slice(0, reveal(rows.length, w)).map(([a, bHTML]) => `<dt>${esc(a)}</dt><dd>${bHTML}</dd>`).join('')}</dl>`;
    },
    (w, writing) => {
      const COMP_MAX = 60, compAll = reveal(d.components.length, w);
      const items = pick(1, d.components, Math.min(COMP_MAX, compAll), writing);
      const moreHTML = compAll > COMP_MAX ? `<p class="sc-note">${esc(tl('panel.comp.more', { n: compAll - COMP_MAX, max: COMP_MAX }))}</p>` : '';
      const wfState = (m) => (writing ? (m[2] === 'is-new' ? 'writing' : 'defined') : !s.implPhase ? 'defined' : m[1] === 'm-done' ? 'done' : m[1] === 'm-doing' ? 'doing' : 'todo');
      const rowText = (type, id, desc) => `<span class="tp">${esc(TYPE_JA[type] || type)}</span> <span class="id">${esc(id)}</span> <span class="desc">${prose(desc)}</span>`;
      let rowsHTML, wfHTML;
      if (hasDepths(d.components)) {
        // a tree: the list indented by depth with its lines, the phone frame's boxes nested
        const depths = treeDepths(items.map((x) => x[0])), guides = treeGuides(depths);
        rowsHTML = items.map(([[type, id, desc], i, m]) => {
          const gHTML = guides[i].length ? `<span class="tg" aria-hidden="true">${guides[i].map((k) => `<i class="g-${esc(k)}"></i>`).join('')}</span>` : '';
          return li(m, `c${i}`, `${gHTML}<span class="tr-in" style="padding-left:${esc(depths[i] * TREE_STEP)}px">${rowText(type, id, desc)}</span>`, depths[i]);
        }).join('');
        wfHTML = wfTree(items.map(([c, i, m]) => ({ c, idx: i, depth: depths[i], state: wfState(m) })));
      } else {
        // no depths (the demo's screens): one level, the wireframe in layoutChildren's order
        rowsHTML = items.map(([[type, id, desc], i, m]) => li(m, `c${i}`, rowText(type, id, desc))).join('');
        const byId = new Map(items.map((x) => [x[0][1], x]));
        wfHTML = d.layoutChildren.filter((id) => byId.has(id)).map((id) => { const [c, , m] = byId.get(id); return wfElement(c, wfState(m)); }).join('');
      }
      return `<div class="st-grid"><div class="wf-phone" role="img" aria-label="${esc(tl('panel.wf.aria', { id: (d.components[0] || [])[1] || '' }))}">${wfHTML}</div><ul class="rows">${rowsHTML}</ul></div>${moreHTML}`;
    },
    (w, writing) => {
      const rowsHTML = pick(2, d.uiVariables, reveal(d.uiVariables.length, w), writing).map(([[name, type, init], i, m]) => tr(m, `v${i}`, `<td class="mono">${esc(name)}</td>${typeCell(type)}<td class="mono">${esc(init)}</td>`)).join('');
      const evHTML = !writing || w >= 0.6 ? `<p class="sub-h">${esc(tl('panel.ev.title'))}</p>${nameTable([tl('panel.ev.title'), tl('panel.meta.description')], d.eventHandlers.map(([name, desc], i) => tr(['', '', ''], `e${i}`, nameCells([name, desc], true))).join(''))}` : '';
      return `<table class="vt"><thead><tr><th><span class="sr">${esc(tl('panel.th.state'))}</span></th><th>${esc(tl('panel.th.var'))}</th><th>${esc(tl('panel.th.type'))}</th><th>${esc(tl('panel.th.initial'))}</th></tr></thead><tbody>${rowsHTML}</tbody></table>${evHTML}`;
    },
    (w, writing) => {
      const M = d.vmMethods.length, shown = writing ? reveal(M + 2 + d.apis.length, w) : M + 2 + d.apis.length;
      const methodsHTML = pick(3, d.vmMethods, Math.min(shown, M), writing && shown <= M).map(([name, i, m]) => li(m, `m${i}`, `<span class="id">${esc(name)}</span>`)).join('');
      const varsHTML = shown > M ? `<p class="fb-vars">${esc(tl('panel.fb.vars'))}${d.vmVars.map((v) => `<code>${esc(v)}</code>`).join(' ')}</p>` : '';
      const reposHTML = shown > M + 1 ? `<div class="farrow" aria-hidden="true">↓</div><div class="fbox"><p class="fb-h">Repository</p><p>${d.repositories.map((r) => `<span class="bdg">${esc(r)}</span>`).join(' ')}</p></div>` : '';
      const apiN = Math.max(0, shown - M - 2);
      let apisHTML = '';
      if (shown > M + 1 && !d.apis.length) apisHTML = `<div class="farrow" aria-hidden="true">↓</div><div class="fbox"><p class="fb-h">API</p><p class="sc-ph">${esc(tl('panel.fb.noapi'))}</p></div>`;
      else if (apiN > 0) apisHTML = `<div class="farrow" aria-hidden="true">↓</div><div class="fbox"><p class="fb-h">API</p><ul class="rows">${d.apis.slice(0, apiN).map(([op, method, path]) => `<li class="api"><span class="http http-${esc(method)}">${esc(method)}</span><code>${esc(path)}</code><span class="desc">${prose(op)}</span></li>`).join('')}</ul></div>`;
      const boxesHTML = `<div class="flow"><div class="fbox"><p class="fb-h">ViewModel</p><ul class="rows">${methodsHTML}</ul>${varsHTML}</div>${reposHTML}${apisHTML}</div>`;
      // 2.3.5: the diagram the spec page draws (Mermaid), the boxes under it with what it does not say; while the
      // section is being written, the boxes alone (they grow as it is written)
      if (!d.flowMermaid || writing) return boxesHTML;
      return `<div class="flow-mmd-wrap"><div class="flow-mmd-bar"><button type="button" class="wb-btn" data-flow-zoom data-fk="flow-zoom" aria-pressed="${wb.flowFit ? 'true' : 'false'}">${wb.flowFit ? esc(tl('panel.flow.actual')) : esc(tl('panel.flow.fit'))}</button></div><div class="flow-mmd" data-flow-mmd role="img" aria-label="${esc(tl('panel.flow.aria'))}"></div></div><p class="sub-h">${esc(tl('panel.flow.details'))}</p>${boxesHTML}`;
    },
    (w, writing) => {
      // 操作 (userAction: action, processing, destination): the destination column only when the spec writes one
      const dest = d.userActions.some((x) => x[2]);
      return nameTable(dest ? [tl('panel.th.action'), tl('panel.th.result'), tl('panel.th.dest')] : [tl('panel.th.action'), tl('panel.th.result')], pick(4, d.userActions, reveal(d.userActions.length, w), writing)
        .map(([[a, p, to], i, m]) => tr(m, `a${i}`, nameCells(dest ? [a, p, to || ''] : [a, p], false))).join(''));
    },
    (w, writing) => `<ul class="rows">${pick(5, d.transitions, reveal(d.transitions.length, w), writing).map(([[trig, dest, how], i, m]) => li(m, `t${i}`, `${prose(trig)}<span class="to">→</span>${transitionTag(dest, how)}`)).join('')}</ul>`,
    (w, writing) => {
      const rowsHTML = pick(6, d.branches, reveal(d.branches.length, w), writing).map(([[method, when, then], i, m]) => tr(m, `b${i}`, `<td class="mono">${esc(method)}</td>${bjCell(when, i, 1, prose)}${bjCell(then, i, 2, prose)}`)).join('');
      const sheetNoteHTML = s.id === 'cart' && model.t >= 18 ? `<p class="sc-note">${esc(tl('panel.bt.note', { passed: T.passed }))}</p>` : '';
      return `<table class="vt bt"><thead><tr><th><span class="sr">${esc(tl('panel.th.state'))}</span></th><th>${esc(tl('panel.th.method'))}</th><th>${esc(tl('panel.th.condition'))}</th><th>${esc(tl('panel.th.result'))}</th></tr></thead><tbody>${rowsHTML}</tbody></table>${sheetNoteHTML}`;
    },
    () => `<ul class="files">${s.related.map(([type, path, exists], i) => {
      const now = i === s.relatedNow && s.by;
      return `<li class="${now ? 'now' : ''}"><span class="bdg">${esc(type)}</span><code>${esc(path)}</code>${exists === false ? `<span class="desc">${esc(tl('panel.rel.missing'))}</span>` : ''}${now ? `<span class="editing">${pill(s.by, DEF[s.by].role)} ${esc(tl(s.status.kind === 'test' ? 'panel.rel.running' : 'panel.rel.editing'))}</span>` : ''}</li>`;
    }).join('')}</ul>`,
  ];
  const sheetHTML = SHEET.map(([k, title, key, wideAlways]) => {
    const wide = wideAlways || (k === 3 && !!d.flowMermaid);   // the data flow diagram takes the whole row (2.3.5)
    // 関連ファイル: live, written when the spec lists any (the demo ties it to 分岐, as its script does).
    const w = k === 7 ? (s.measure ? (s.measure.related.total ? 1 : 0) : (s.written[6] >= 1 ? 1 : 0)) : s.written[k];
    const rel = s.measure && s.measure.related;
    const g = k !== 7 ? secState(s, k) : !w ? { kind: 'empty', text: tl('panel.sw.empty') }
      : rel && rel.total ? { kind: rel.done >= rel.total ? 'done' : 'impl', f: rel.done / rel.total, text: tl('panel.rel.found', { done: rel.done, total: rel.total }) } : { kind: 'written', text: tl('panel.sw.written') };
    const writing = w > 0 && w < 1, live = !!s.by && k === activeSec(s);
    const cls = ['sc', wide && 'wide', w <= 0 && 'sc-empty', live && (k === s.writingIdx ? 'sc-writing' : k === s.testIdx ? 'sc-testing' : 'sc-active')].filter(Boolean).join(' ');
    const headHTML = `<header><h3>${esc(title)}</h3><code>${esc(key)}</code>${live ? pill(s.by, DEF[s.by].role) : ''}<span class="sc-chip ${chipCls(g)}">${esc(g.text)}</span></header>`;
    if (w <= 0) return `<section class="${esc(cls)}" id="wb-sec-${k}">${headHTML}<p class="sc-ph">${esc(tl('panel.sec.unwritten'))}</p></section>`;
    const act = live && k === s.writingIdx && activeKey === null ? (activeKey = `w${k}`, ' data-act') : '';
    const tailHTML = !writing ? '' : s.by ? `<p class="sc-typing">${esc(tl('panel.sec.typing', { who: s.by }))}<span class="caret" aria-hidden="true"></span></p>` : `<p class="sc-ph">${esc(tl('panel.sec.stopped'))}</p>`;
    return `<section class="${esc(cls)}" id="wb-sec-${k}"${esc(act)}>${headHTML}${bodies[k](w, writing)}${tailHTML}</section>`;
  }).join('');
  setHTML(wbCode, sheetHTML);
  fillBranchJSON(wbCode, d.branches, s.id);
  fillProse(wbCode, mdTexts);
  const mmd = wbCode.querySelector('[data-flow-mmd]');
  if (mmd) drawMermaid(mmd, d.flowMermaid).then((svg) => flowZoomApply(svg));

  // Follow: keep the card being written, or the row being implemented or tested, in view.
  if ($('wb-follow').checked && activeKey) {
    const el = wbCode.querySelector('[data-act]');
    if (el) {
      const r = el.getBoundingClientRect(), c = wbCode.getBoundingClientRect();
      if (el.tagName === 'SECTION') { const over = r.bottom - (c.top + c.height * 0.85); if (force || activeKey !== wb.lastActive || over > 0) wbCode.scrollTop += over; }
      else if (force || activeKey !== wb.lastActive) wbCode.scrollTop += r.top + r.height / 2 - (c.top + c.height / 2);
    }
  }
  wb.lastActive = activeKey;
}

/* ---------- task board up close: one column per task state, permission prompts on top ---------- */
const tbEl = $('tb'), kanbanEl = $('kanban'), stripEl = $('perm-strip'), detailEl = $('tb-detail'), qStripEl = $('q-strip');
const tb = { open: false, detail: null, board: null, waitView: false, wide: false, waiting: { q: 0, d: 0, p: 0 } };   // waitView: opened from a 質問 / 許可待ち chip
const kbBodyEl = tbEl.querySelector('.kb-body'), wideBtn = $('tb-wide');
$('tb-lanes').addEventListener('change', (e) => { UI.lanes = e.target.checked; writePref('lanes', UI.lanes ? 'on' : 'off'); renderTaskBoard(latestModel); });
function openTaskBoard(opener, detail, board) {
  if (detail !== undefined) tb.detail = detail;
  if (board !== undefined) tb.board = board;
  if (detail && !detail.startsWith('perm:') && !inScope(PROJECT_OF[detail.split('#')[0]])) setProject(PROJECT_OF[detail.split('#')[0]], { camera: false });
  if (detail && detail.startsWith('perm:') && !inScope(projectOfRobot(PERM_BY_ID[detail.slice(5)].who))) setProject(projectOfRobot(PERM_BY_ID[detail.slice(5)].who), { camera: false });
  holdView('tb');
  if (wb.open) closeWhiteboard();
  if (rbState.id) closeRobot();
  if (tb.open) { renderTaskBoard(latestModel); if (detail) $('tbd-close').focus({ preventScroll: true }); return; }
  tb.open = true;
  zoomTo(taskPose(tb.board), opener, () => {
    if (!tb.open) return;
    showOverlay(tbEl);
    renderTaskBoard(latestModel);
    const firstQ = tb.waitView && !tb.detail ? kbBodyEl.querySelector('#q-strip .ps-line, #denied-strip .ps-line, #perm-strip .ps-line') : null;   // from a chip: the first card's line
    (firstQ || $(tb.detail ? 'tbd-close' : 'tb-close')).focus({ preventScroll: true });
  });
}
function closeTaskDetail() {
  const key = tb.detail;
  tb.detail = null;
  renderTaskBoard(latestModel);
  const back = key && (kanbanEl.querySelector(`[data-open="${CSS.escape(key)}"]`) || stripEl.querySelector(`[data-open="${CSS.escape(key)}"]`));
  (back || $('tb-close')).focus({ preventScroll: true });
}
function closeTaskBoard() {
  if (!tb.open) { releaseView('tb'); return; }
  tb.open = false; tb.detail = null; tb.waitView = false; tb.wide = false;   // the strips are folded again next time
  qStripEl.replaceChildren(); qStripEl._sig = null; qStripEl.hidden = true;   // no second copy of the cards while closed
  const dStrip = $('denied-strip'); dStrip.replaceChildren(); dStrip._sig = null; dStrip.hidden = true;
  hideOverlay(tbEl);
  releaseView('tb');
}
$('tb-close').addEventListener('click', closeTaskBoard);
/* The strips on top, folded or wide (ticket 2026-10-22-viz-taskboard-top-strips-hide-the-columns). Requester: 「上の許可の
   表示を小さくして、広げるを押すと許可の部分だけ表示で下が消える仕様にして欲しい」. Folded (the default each time the board
   opens): each strip is its count and one line per card (who, what, how long); the four columns below stay in sight.
   Wide: the strips' whole cards and no columns. A card's line opens the strips wide at that card. The handle that opens
   and folds them hangs under the strips (the requester on the first look: 「上の幅を広げる、たたむはわかりづらい上の方の添付
   画像の部分を広げるってわかるUIにしてほしい」): ▼ / ▲ and what is waiting in them, in words. */
const foldLine = (go, x, tool, text, note = '') => `<li><button type="button" class="ps-line" data-ps-go="${esc(go)}" data-fk="fl-${esc(go)}">${pill(x.who, DEF[x.who].role)}<span class="ps-who">${esc(DEF[x.who].agent)}</span><span class="ps-what">${tool ? `<b>${esc(tool)}</b> <code>${esc(text)}</code>` : esc(text)}</span>${note ? `<span class="ps-note">${esc(note)}</span>` : ''}<span class="pc-wait" data-since="${x.at}"></span></button></li>`;
const countB = (n) => `<b${n ? '' : ' class="ps-zero"'}>${n}</b>`;
function paintTbWide() {
  const any = !qStripEl.hidden || !$('denied-strip').hidden || !stripEl.hidden;
  if (!any) tb.wide = false;
  wideBtn.hidden = !any;
  kbBodyEl.classList.toggle('tb-wide', tb.wide);
  kbBodyEl.classList.toggle('tb-fold', !tb.wide);
  wideBtn.setAttribute('aria-expanded', String(tb.wide));
  const W = tb.waiting, what = [W.q && tl('panel.tb.wide.q', { n: W.q }), W.d && tl('panel.tb.wide.d', { n: W.d }), W.p && tl('panel.tb.wide.p', { n: W.p })].filter(Boolean).join(tl('panel.tb.wide.sep'));
  setText(wideBtn, tb.wide ? tl('panel.tb.fold') : tl('panel.tb.wide', { what: what || tl('panel.tb.wide.none') }));
}
const FOLD_CARD = { q: (id) => `#q-strip [data-qcard="${CSS.escape(id)}"]`, d: (id) => `#denied-strip [data-dcard="${CSS.escape(id)}"]`, p: (id) => `#perm-strip [data-fk="pt-${CSS.escape(id)}"]` };
function setTbWide(on, go) {
  tb.wide = on;
  renderTaskBoard(latestModel);
  const [kind, ...rest] = go ? go.split(':') : [];
  const at = kind && FOLD_CARD[kind] ? kbBodyEl.querySelector(FOLD_CARD[kind](rest.join(':'))) : null;
  const card = at && (at.closest('.qcard, .pcard') || at);
  if (card) { card.scrollIntoView({ block: 'nearest' }); (card.querySelector('input:not([disabled]), button:not([disabled])') || wideBtn).focus({ preventScroll: true }); }
  else wideBtn.focus({ preventScroll: true });
}
wideBtn.addEventListener('click', () => setTbWide(!tb.wide));
kbBodyEl.addEventListener('click', (e) => { const go = e.target.closest('[data-ps-go]'); if (go) setTbWide(true, go.dataset.psGo); });
const COL_HINT = { todo: tl('panel.hint.todo'), wait: tl('panel.hint.wait'), doing: tl('panel.hint.doing'), done: '' };
const mmss = (sec) => `${Math.floor(sec / 60)}:${String(Math.floor(sec % 60)).padStart(2, '0')}`;
const paintSince = (root, t, word) => root.querySelectorAll('[data-since]').forEach((el) => setText(el, `${word} ${mmss(Math.max(0, t - Number(el.dataset.since)))}`));
/* The board's question strip (2.3.5): the panel's cards in scope, and how many wait elsewhere (the chip counts both). */
function renderQuestionStrip() {
  const qs = questionsShown(), elsewhere = questionsElsewhere();
  qStripEl.hidden = !qs.length && !elsewhere && !tb.waitView;
  keyed(qStripEl, `${tb.waitView}|${elsewhere}|${questionsSig(qs)}`, () => {
    const otherHTML = elsewhere ? `<p class="ps-rules" data-q-elsewhere="${elsewhere}">${esc(tl('panel.q.elsewhere', { n: elsewhere }))} <button type="button" class="link-btn" data-set-all data-fk="qs-all">${esc(tl('panel.scope.all.shown'))}</button></p>` : '';
    const foldHTML = qs.map((q) => foldLine(`q:${q.id}`, q, '', q.questions.map((x) => x.header || x.question).join(' / '), q.status === 'pending' ? '' : qState(q))).join('');
    return `<h3 class="ps-title">${esc(tl('panel.q.title'))}${countB(qs.filter((q) => q.status === 'pending').length)}<small>${esc(tl('panel.q.oldest'))}</small></h3>${foldHTML ? `<ul class="ps-fold">${foldHTML}</ul>` : ''}${qs.some((q) => q.status === 'pending') ? '' : `<p class="ps-none">${esc(tl('panel.q.none'))}</p>`}${otherHTML}${qs.map((q) => questionHTML(q, 'b')).join('')}`;
  });
  tb.waiting.q = qs.filter((q) => q.status === 'pending').length;
  qStripEl.classList.toggle('ps-hot', tb.waiting.q > 0);
}
function renderTaskBoard(model) {
  if (!tb.open) return;
  const visible = (list) => inScope(PROJECT_OF[list]) && !UI.hiddenLists.has(list);
  const tasks = model.tasks.filter((x) => visible(x.list));
  // Permission prompts stay on top for the whole project even when some sessions are filtered out; prompts in
  // other projects are counted so they are never missed.
  const pend = model.pending.filter((p) => inScope(projectOfRobot(p.who)));
  const elsewhere = model.pending.length - pend.length;
  setText($('tb-count'), tl('panel.tb.count', { n: tasks.length }));
  setText($('tb-title'), UI.project === 'all' ? tl('panel.tb.title') : tl('panel.tb.title.project', { name: PROJECT[UI.project].name }));
  // the questions waiting, the same cards as the panel's from the same list (questionsShown), on top
  renderQuestionStrip();
  paintSince(qStripEl, model.t, tl('panel.since.wait'));
  renderDenialStrip();
  paintSince($('denied-strip'), model.t, tl('panel.since.elapsed'));
  stripEl.hidden = !pend.length && !alwaysRules.size && !elsewhere && !tb.waitView;
  keyed(stripEl, JSON.stringify([NAMES.rev, pend.map(permSig), [...alwaysRules.keys()], elsewhere]), () => {
    const cardsHTML = pend.map((p) => {
      const x = p.task && TASK_BY_KEY[p.task];
      return `<li class="pcard"><div class="pc-who">${pill(p.who, DEF[p.who].role)}<span>${esc(DEF[p.who].agent)}</span><span class="pc-wait" data-since="${p.at}"></span></div><p class="pc-what"><b>${esc(p.tool)}</b> ${permSubject(p)}</p><button type="button" class="pc-task" data-open="${x ? esc(p.task) : `perm:${esc(p.id)}`}" data-fk="pt-${esc(p.id)}">${x ? `${esc(x.list)} ${esc(taskRef(x))} ${esc(x.subject)}` : esc(tl('panel.task.session.none', { id: SESSION_OF[p.who] }))} ${esc(tl('panel.pc.details'))}</button><div class="perm-acts">${permButtons(p, 'p')}</div></li>`;
    }).join('');
    const rulesHTML = alwaysRules.size ? `<p class="ps-rules">${esc(tl('panel.rules.added'))}${[...alwaysRules.keys()].map((r) => `<code>${esc(r)}</code>`).join(' ')} <button type="button" class="link-btn" data-reset-rules data-fk="rules">${esc(tl('panel.rules.reset'))}</button></p>` : '';
    const otherHTML = elsewhere ? `<p class="ps-rules">${esc(tl('panel.perm.elsewhere', { n: elsewhere }))} <button type="button" class="link-btn" data-set-all data-fk="ps-all">${esc(tl('panel.scope.all.shown'))}</button></p>` : '';
    const foldHTML = pend.map((p) => foldLine(`p:${p.id}`, p, p.tool, p.input ? permSummary(p) : '')).join('');
    return `<h3 class="ps-title">${esc(tl('panel.perm.asking'))}${countB(pend.length)}<small>${PERM_NOTE}</small></h3>${foldHTML ? `<ul class="ps-fold">${foldHTML}</ul>` : ''}${cardsHTML ? `<ul class="ps-list">${cardsHTML}</ul>` : `<p class="ps-none">${esc(tl('panel.perm.none'))}</p>`}${otherHTML}${rulesHTML}`;
  });
  tb.waiting.p = pend.length;
  stripEl.classList.toggle('ps-hot', pend.length > 0);
  paintSince(stripEl, model.t, tl('panel.since.wait'));
  paintTbWide();
  const loopStart = simT - model.t;
  const lists = SESSIONS.filter((x) => visible(x.id)).map((x) => x.id);
  const noteHTML = (x, col) => {
      const ownerHTML = x.owner ? `${pill(x.owner, DEF[x.owner].role)}<span>${esc(DEF[x.owner].agent)}</span>` : `<span>${esc(tl('panel.owner.none'))}</span>`;
      const extraHTML = col === 'doing' ? `<span class="n-doing">▶ ${esc(isTurn(x) ? tl(x.background ? 'panel.note.bg' : 'panel.note.turn') : x.activeForm || x.subject)}<span data-since="${x.start}"></span></span>`
        : col === 'wait' ? (x.dep ? `<span class="n-wait">${esc(tl('panel.note.dep', { id: x.dep.id, subject: x.dep.subject }))}</span>` : `<span class="n-wait">${esc(isTurn(x) ? (x.waitingFor === 'question' ? tl('status.asking') : tl('panel.note.perm')) : tl('panel.col.wait'))}</span>`)
          : col === 'done' ? `<span class="n-time">${esc(tl('panel.note.at', { time: fmtClock(BASE_CLOCK + loopStart + x.end), what: tl(x.failed ? 'panel.note.failed' : 'panel.note.done') }))}</span>` : '';
      const permHTML = x.perm ? `<div class="n-permbox"><p class="n-permq"><b>${esc(tl('status.waiting'))}</b> ${esc(x.perm.tool)} ${permSubject(x.perm)}</p><div class="perm-acts">${permButtons(x.perm, 'k')}</div></div>` : '';
      return `<li class="note${x.perm ? ' n-perm' : ''}${x.fresh ? ' n-new' : ''}${isTurn(x) ? ' n-turn' : ''}"><button type="button" class="note-open" data-open="${esc(x.key)}" data-fk="nb-${esc(x.key)}"><span class="n-top"><span>${esc(taskRef(x))}</span><span>${UI.lanes ? '' : `${esc(tl('panel.note.list', { list: x.list }))}${UI.project === 'all' ? ` · ${esc(PROJECT[PROJECT_OF[x.list]].name)}` : ''}`}</span></span><span class="n-subj">${esc(x.subject)}</span>${extraHTML}<span class="n-owner">${ownerHTML}</span></button>${permHTML}</li>`;
  };
  const sortCol = (col) => (a, b) => (b.perm ? 1 : 0) - (a.perm ? 1 : 0) || (col === 'done' ? b.end - a.end : 0) || a.list.localeCompare(b.list) || a.id - b.id;
  kanbanEl.classList.toggle('lanes', UI.lanes);
  keyed(kanbanEl, JSON.stringify([UI.lanes, NAMES.rev, lists, KCOLS.map(([col]) => tasks.filter((x) => x.col === col).map((x) => `${x.key}:${permSig(x.perm)}:${x.fresh ? 1 : 0}:${x.subject}:${x.owner || ''}`))]), () => {
    if (!lists.length) return `<p class="k-none">${esc(tl('panel.k.none'))}</p>`;
    if (!UI.lanes) return KCOLS.map(([col, label]) => {
      const items = tasks.filter((x) => x.col === col).sort(sortCol(col));
      return `<section class="kcol k-${esc(col)}" aria-label="${esc(tl('panel.k.col.aria', { label, n: items.length }))}"><h3 class="ktab"><span>${esc(label)}${COL_HINT[col] ? `<small>${esc(COL_HINT[col])}</small>` : ''}</span><b>${items.length}</b></h3><ol class="knotes">${items.map((x) => noteHTML(x, col)).join('') || `<li class="k-empty">${esc(tl('panel.none'))}</li>`}</ol></section>`;
    }).join('');
    // One lane per session: its four state columns side by side, sessions that need you first.
    const headHTML = `<div class="lane-cols" aria-hidden="true"><span></span>${KCOLS.map(([col, label]) => `<span class="k-${esc(col)}">${esc(label)}<b>${tasks.filter((x) => x.col === col).length}</b></span>`).join('')}</div>`;
    const ordered = SESSIONS.filter((x) => lists.includes(x.id)).sort((a, b) => SB_ORDER[sessionBadge(a)[0]] - SB_ORDER[sessionBadge(b)[0]] || a.id.localeCompare(b.id));
    return headHTML + ordered.map((x) => {
      const mine = tasks.filter((t) => t.list === x.id), [c, l] = sessionBadge(x);
      return `<section class="lane" aria-label="${esc(tl('panel.lane.aria', { id: x.id, n: mine.length }))}"><header class="lane-head"><button type="button" class="who-btn" data-robot-open="${esc(x.id)}" data-fk="lh-${esc(x.id)}">${pill(x.id, 'main')}<span>${esc(PROJECT[x.project].name)}</span></button><span class="state ${esc(c)}">${esc(l)}</span><small>${esc(tl('panel.tb.count', { n: mine.length }))}</small></header>${KCOLS.map(([col, label]) => { const items = mine.filter((t) => t.col === col).sort(sortCol(col)); return `<div class="lane-cell k-${esc(col)}" aria-label="${esc(tl('panel.k.col.aria', { label, n: items.length }))}"><span class="lane-label">${esc(label)} ${items.length}</span><ol class="knotes">${items.map((t) => noteHTML(t, col)).join('')}</ol></div>`; }).join('')}</section>`;
    }).join('');
  });
  paintSince(kanbanEl, model.t, tl('panel.since.elapsed'));
  renderTaskDetail(model);
}

/* The detail drawer: one task (or one prompt that belongs to no task) with its permission prompt, links and history. */
function renderTaskDetail(model) {
  const key = tb.detail;
  detailEl.hidden = !key;
  if (!key) { detailEl._sig = null; return; }
  const permOnly = key.startsWith('perm:');
  const x = permOnly ? null : model.tasks.find((q) => q.key === key) || null;
  const base = permOnly ? null : TASK_BY_KEY[key];
  const here = model.perms.filter((q) => (permOnly ? q.id === key.slice(5) : q.task === key));
  const pending = here.find((q) => q.status === 'pending') || null;
  const known = permOnly ? PERM_BY_ID[key.slice(5)] : null;
  const who = base ? base.owner : known ? known.who : null;
  const sig = JSON.stringify([key, x && x.col, x && x.status, x && x.subject, here.map(permSig)]);
  keyed(detailEl, sig, () => {
    const loopStart = simT - model.t;
    const clock = (v) => fmtClock(BASE_CLOCK + loopStart + v);
    const [cls, label] = x ? (x.perm ? ['st-waiting', tl('panel.td.perm')] : x.col === 'wait' ? ['st-waiting', tl('panel.col.wait')] : COL_STATE[x.col]) : ['st-idle', tl('panel.td.notyet')];
    const blocks = base ? TASKS.filter((q) => q.list === base.list && q.blockedBy === base.id) : [];
    const specIdx = base && base.spec ? SPEC_INDEX[base.spec] : -1;
    const spec = specIdx >= 0 ? model.specs[specIdx] : null;
    const histHTML = here.filter((q) => q.status !== 'pending' && q.status !== 'sent').map((q) => {
      const howHTML = SOURCE.mode === 'live' ? livePermHow(q) : q.status === 'terminal' ? esc(tl('panel.how.term.allow')) : q.status === 'rule' ? esc(tl('panel.how.rule', { rule: q.rule })) : q.status === 'deny' ? esc(tl('panel.how.view.deny')) : q.status === 'always' ? esc(tl('panel.how.view.always', { rule: q.rule })) : esc(tl('panel.how.view.allow'));
      const at = q.decided ? fmtClock(BASE_CLOCK + q.decided.at) : clock(q.status === 'rule' ? q.at : q.end);
      return `<li><time>${esc(at)}</time><span>${howHTML} · ${esc(q.tool)} <code>${esc(permSummary(q))}</code></span></li>`;
    }).join('');
    const sample = pending || here[here.length - 1] || known;
    const times = base ? [base.created >= 0 ? tl('panel.td.created', { time: clock(base.created) }) : '', base.start !== null && base.start <= model.t ? tl('panel.td.started', { time: clock(base.start) }) : '', base.end !== null && base.end <= model.t ? tl('panel.td.ended', { time: clock(base.end) }) : ''].filter(Boolean).join(' · ') : '';
    return `<div class="tbd-top"><p class="tbd-id">${base ? `${esc(base.list)} ${esc(taskRef(base))} · ${esc(tl('panel.note.list', { list: base.list }))}` : esc(tl('panel.task.session.none', { id: SESSION_OF[who] }))}</p><button type="button" class="wb-btn" id="tbd-close" data-close-detail data-fk="tbd-close">${esc(tl('panel.close'))}</button></div>
<h3 id="tbd-title">${base ? esc(base.subject) : esc(tl('panel.td.perm.title', { tool: known.tool }))}</h3>
${base ? `<p class="tbd-state"><span class="state ${esc(cls)}">${esc(label)}</span></p>` : ''}
${pending ? permDetail(pending, 'tbd') : ''}
<dl class="tbd-kv">
<dt>${esc(tl('panel.td.owner'))}</dt><dd>${who ? `<button type="button" class="link-btn" data-robot-open="${esc(who)}" data-fk="tbd-who">${pill(who, DEF[who].role)} ${esc(DEF[who].agent)}</button>` : esc(tl('panel.owner.none'))}</dd>
${who ? `<dt>${esc(tl('panel.td.now'))}</dt><dd data-live-act="${esc(who)}"></dd>` : ''}
${base ? `<dt>${esc(tl('panel.td.dep'))}</dt><dd>${base.blockedBy ? `<button type="button" class="link-btn" data-open="${esc(base.list)}#${esc(base.blockedBy)}" data-fk="tbd-dep">${esc(tl('panel.td.ref', { id: base.blockedBy, subject: TASK_BY_KEY[`${base.list}#${base.blockedBy}`].subject }))}</button>${x && x.blocked ? esc(tl('panel.td.dep.wait')) : ''}` : esc(tl('panel.none'))}</dd>` : ''}
${base ? `<dt>${esc(tl('panel.td.next'))}</dt><dd>${blocks.length ? blocks.map((q) => `<button type="button" class="link-btn" data-open="${esc(q.list)}#${esc(q.id)}" data-fk="tbd-b${esc(q.id)}">${esc(tl('panel.td.ref', { id: q.id, subject: q.subject }))}</button>`).join(' ') : esc(tl('panel.none'))}</dd>` : ''}
${times ? `<dt>${esc(tl('panel.td.times'))}</dt><dd>${esc(times)}</dd>` : ''}
${spec ? `<dt>spec</dt><dd><button type="button" class="link-btn" data-spec-open="${specIdx}" data-fk="tbd-spec">${esc(tl('panel.td.spec.open', { name: spec.name, screen: spec.screen }))}</button><span class="state ${STATUS_CLASS[spec.status.kind]}" title="${esc(specStatus(spec).title)}">${esc(specStatus(spec).text)}</span></dd>` : ''}
</dl>
${histHTML ? `<h4>${esc(tl('panel.td.perm.hist'))}</h4><ul class="tbd-list">${histHTML}</ul>` : ''}
${who ? `<h4>${esc(tl('panel.td.recent', { who }))}</h4><ul class="tbd-list" data-recent="${esc(who)}"></ul>` : ''}
${sample ? rawDetails(sample) : ''}`;
  });
  paintSince(detailEl, model.t, tl('panel.since.wait'));
  detailEl.querySelectorAll('[data-live-act]').forEach((el) => setText(el, robotState[el.dataset.liveAct].act));
  detailEl.querySelectorAll('[data-recent]').forEach((el) => setHTML(el, recentHTML(el.dataset.recent)));
}
const permDetail = (p, where) => (SOURCE.mode === 'live' ? permDetailLive(p, where) : permDetailDemo(p, where));
const permDetailLive = (p, where) => `<div class="tbd-perm"><h4>${esc(tl('panel.perm.asking'))}</h4><p>${pill(p.who, DEF[p.who].role)} ${esc(DEF[p.who].agent)} ${esc(tl('panel.perm.wants.pre'))}<b>${esc(p.tool)}</b>${esc(tl('panel.perm.wants.post'))}<span class="tbd-wait" data-since="${p.at}"></span></p><div class="tbd-cmd">${permSubjectLive(p)}</div>${p.can.reason ? `<label class="tbd-reason">${esc(tl('panel.perm.reason'))}<input type="text" id="${esc(where)}-reason" autocomplete="off"></label>` : ''}<div class="perm-acts">${permButtons(p, where)}</div><p class="tbd-note">${PERM_NOTE}${p.relayOnly ? esc(tl('panel.perm.relayonly')) : ''}</p></div>`;
const permDetailDemo = (p, where) => `<div class="tbd-perm"><h4>${esc(tl('panel.perm.asking'))}</h4><p>${pill(p.who, DEF[p.who].role)} ${esc(DEF[p.who].agent)} ${esc(tl('panel.perm.wants.pre'))}<b>${esc(p.tool)}</b>${esc(tl('panel.perm.wants.post'))}<span class="tbd-wait" data-since="${p.at}"></span></p><pre class="tbd-cmd">${esc(permSummary(p))}</pre><label class="tbd-reason">${esc(tl('panel.perm.reason'))}<input type="text" id="${esc(where)}-reason" placeholder="${esc(tl('panel.perm.reason.example'))}" autocomplete="off"></label><div class="perm-acts">${permButtons(p, where)}</div><p class="tbd-note">${PERM_NOTE}${tlHTML('panel.perm.demo.note', { rule: p.rule })}</p></div>`;
/* The relay's request id: five lowercase letters without "l". */
const relayId = (p) => [...`${p.id}${p.who}xyz`].slice(0, 5).map((ch, k) => 'abcdefghijkmnopqrstuvwxyz'[(ch.charCodeAt(0) * 7 + k * 11) % 25]).join('');
const livePermHow = (q) => (q.status === 'terminal' ? (q.terminalBehavior === 'deny' ? esc(tl('panel.how.term.deny')) : esc(tl('panel.how.term.allow')))
  : q.status === 'allow' ? (q.decidedBy === 'terminal' ? esc(tl('panel.how.term.allow')) : q.sentRules ? esc(tl('panel.how.view.rules', { n: q.sentRules.length })) : esc(tl('panel.how.view.allow')))
    : q.status === 'deny' ? (q.decidedBy === 'terminal' ? esc(tl('panel.how.term.deny')) : q.sentReason ? esc(tl('panel.how.view.deny.why', { reason: q.sentReason })) : esc(tl('panel.how.view.deny')))
    : q.status === 'expired' ? esc(tl('panel.expired')) : esc(q.status));
const rawDetails = (p) => {
  if (SOURCE.mode === 'live') return `<details class="tbd-raw"><summary>${esc(tl('panel.raw.got'))}</summary><pre>${esc(p.preview || permSummary(p))}</pre>${p.suggestions ? `<p>${esc(tl('panel.raw.suggestions'))}</p><pre>${esc(JSON.stringify(p.suggestions, null, 2))}</pre>` : ''}</details>`;
  const id = relayId(p);
  const relayIn = { method: 'notifications/claude/channel/permission_request', params: { request_id: id, tool_name: p.tool, description: p.tool + ' ' + permSummary(p), input_preview: JSON.stringify(p.input) } };
  const relayOut = { method: 'notifications/claude/channel/permission', params: { request_id: id, behavior: 'allow' } };
  return `<details class="tbd-raw"><summary>${esc(tl('panel.raw.title'))}</summary><p>${esc(tl('panel.raw.relay.in'))}</p><pre>${esc(JSON.stringify(relayIn, null, 2))}</pre><p>${esc(tl('panel.raw.relay.out'))}</p><pre>${esc(JSON.stringify(relayOut, null, 2))}</pre><p>${esc(tl('panel.raw.hook.in'))}</p><pre>${esc(JSON.stringify(permRequestPayload(p), null, 2))}</pre><p>${esc(tl('panel.raw.hook.out'))}</p><pre>${esc(JSON.stringify(permResponse(p, 'always'), null, 2))}</pre></details>`;
};

/* ---------- a robot up close: what it is doing, its tasks and its prompts ---------- */
const rbEl = $('rb');
// seen: the robot whose room rbFollow last saw, and that room; moved: the card's mark when it does not follow (rbFollow)
const rbState = { id: null, seen: null, moved: null };
/* The chat icon of トーク (58-talk.js): a speech bubble, drawn with the text's colour. */
const TALK_ICON = '<svg class="rb-talk-icon" viewBox="0 0 20 20" width="16" height="16" aria-hidden="true" focusable="false"><path d="M3 4.5A2.5 2.5 0 0 1 5.5 2h9A2.5 2.5 0 0 1 17 4.5v6a2.5 2.5 0 0 1-2.5 2.5H9l-4 3.5V13h0A2 2 0 0 1 3 11z" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/><circle cx="7" cy="7.6" r="1" fill="currentColor"/><circle cx="10" cy="7.6" r="1" fill="currentColor"/><circle cx="13" cy="7.6" r="1" fill="currentColor"/></svg>';
const CAM_DIR = new THREE.Vector3(0.25, 0.42, 0.87).normalize();
/* ---------- the camera on a robot (requester, 10-18: "ズーム中も回転とか拡大縮小とかできるようにしたい",
   "ロボットの場所によってはこんな感じになって見えない") ----------
   While the card is open the camera orbits the robot: azimuth, elevation and distance (FOCUS), changed by a drag, the
   wheel or a pinch. Its first direction is chosen when a robot is focused (opened, ← →, another robot clicked): of 12
   azimuths × 2 elevations, the one whose lines from the robot (chest, head, knees) to the camera cross the fewest
   walls, boards and furniture, nearest the usual direction on a tie. What still stands between them is drawn faint
   until the camera leaves (focusFadeSync, with the card's refresh). */
const FOCUS = { id: null, az: 0, el: 0, dist: 8, chosen: null, faded: new Map(), drag: null, pinch: null, touches: new Map() };
const FOCUS_DIST = [4, 18], FOCUS_EL = [0.12, 1.3], FOCUS_FADE = 0.22;
const FOCUS_BASE = { az: Math.atan2(CAM_DIR.x, CAM_DIR.z), el: Math.asin(CAM_DIR.y) };
const FOCUS_SAMPLES = [0.55, 1.15, 1.65];   // heights on the robot the camera must see
const focusRay = new THREE.Raycaster();
const focusDir = (az, el) => new THREE.Vector3(Math.sin(az) * Math.cos(el), Math.sin(el), Math.cos(az) * Math.cos(el));
function focusPose(R, az, el, dist, fitted = false) {
  const dir = focusDir(az, el), wide = sceneEl.clientWidth > 900;
  const right = new THREE.Vector3().crossVectors(dir.clone().negate(), new THREE.Vector3(0, 1, 0)).normalize();
  const viewH = 2 * dist * Math.tan(THREE.MathUtils.degToRad(camera.fov / 2)), viewW = viewH * camera.aspect;
  // a subagent is 0.8 (2.3.5). The floor under the robot, not its root's height: a hop or a jump (play) moves the root up and
  // down, and the camera does not go with the robot's motion (ticket 2026-10-20-jui-viz-wide-history-camera-jitters).
  const rp = R.robot.root.position, t = new THREE.Vector3(rp.x, 1.15 * (R.robot.size || 1), rp.z);
  // Wide: the card covers the right of the scene, so the robot sits left of centre. Narrow: the card is a
  // bottom sheet, so the robot sits high.
  // The wide 応答の履歴 (2.3.4, 55-history.js): the card leaves only histWideMargin() on the left, and the robot sits in its middle:
  // the middle of a fixed box around its seat (FOCUS_BOX: the desk and a little room around it) in the middle of the margin,
  // and the camera backs off if that box would not fit. Fixed, so the camera stays still whatever the robot does (10-20).
  const margin = typeof histWideMargin === 'function' ? histWideMargin() : 0;
  if (wide && margin) {
    const ext = focusExtent(R, right, dir, dist), mid = (ext.l + ext.r) / 2, width = ext.r - ext.l;
    const fit = (margin / sceneEl.clientWidth) * viewW * FOCUS_FIT;
    if (width > fit && !fitted) return focusPose(R, az, el, dist * (width / fit), true);   // farther, so the fixed box fits the margin
    t.add(right.clone().multiplyScalar(((sceneEl.clientWidth - margin) / 2 / sceneEl.clientWidth) * viewW + mid));
  }
  else if (wide) t.add(right.multiplyScalar((Math.min(420, sceneEl.clientWidth - 28) / 2 / sceneEl.clientWidth) * viewW));
  else t.y -= viewH * 0.2;
  return { p: t.clone().add(dir.multiplyScalar(dist)), t };
}
/* The width the wide history keeps in its margin: a fixed box in the robot's own space (its seat: the root's turn and its
   size go with it), the desk and a little room around it — not the robot as posed (requester 10-20: 「あんまり難しいことしなく
   ていいよ 机プラス少しの余裕くらいの固定値にしたら？」). 2.3.5 measured every shown mesh each frame and kept the widest per
   posture, turn and distance: the sweat drops coming and going, and a key with the distance in it that a backed-off camera
   changed every other frame, moved the camera with the robot's motion (ticket 2026-10-20-jui-viz-wide-history-camera-jitters).
   The box holds the widest pose there is: FOCUS_SPARE past each side of the desk (DESK_W wide, 10-robot-core.js) takes the
   tired slump, the headset's cups, the waving arm and the sweat drops: measured 10-20 in the robot's own space over 5 s each,
   the widest x ±1.09 (the sweat drops, the whistle's arm), y -0.02..2.19, z -0.77..1.00 (tired with sweat). Along the camera's right, in
   units of the plane it looks at, a corner nearer the camera counted wider (perspective). */
const FOCUS_FIT = 0.9;
const DESK_W = 1.0, FOCUS_SPARE = 0.65;
const FOCUS_BOX = { x: [-(DESK_W / 2 + FOCUS_SPARE), DESK_W / 2 + FOCUS_SPARE], y: [-0.05, 2.45], z: [-0.8, 1.05] };
const focusCorner = new THREE.Vector3(), focusQuat = new THREE.Quaternion(), focusScale = new THREE.Vector3(), FOCUS_LOOK = new THREE.Vector3(0, 1.15, 0);
function focusExtent(R, right, dir, dist) {
  const root = R.robot.root, B = FOCUS_BOX;
  root.updateWorldMatrix(true, false);
  root.matrixWorld.decompose(focusCorner, focusQuat, focusScale);
  let l = 0, r = 0;
  for (let i = 0; i < 8; i++) {
    focusCorner.set(B.x[i & 1 ? 1 : 0], B.y[i & 2 ? 1 : 0], B.z[i & 4 ? 1 : 0]).multiply(focusScale).applyQuaternion(focusQuat);
    const side = focusCorner.dot(right), depth = dist - focusCorner.sub(FOCUS_LOOK).dot(dir);
    const d = depth > 0.1 ? side * (dist / depth) : side;
    if (d < l) l = d;
    if (d > r) r = d;
  }
  return { l, r };
}
const shownChain = (o) => { for (let x = o; x; x = x.parent) if (!x.visible) return false; return true; };
const ofRobot = (o) => { for (let x = o; x; x = x.parent) if (x.userData && x.userData.robotId !== undefined) return true; return false; };
/* The meshes (walls, boards, furniture — not robots, not the selection ring) between the robot's sample points and p. */
function focusBlockers(R, p) {
  const out = new Set();
  for (const y of FOCUS_SAMPLES) {
    const from = R.robot.root.position.clone().add(new THREE.Vector3(0, y * (R.robot.size || 1), 0)), dir = p.clone().sub(from), len = dir.length();
    focusRay.set(from, dir.normalize());
    focusRay.far = len;
    focusRay.camera = camera;   // a sprite (a tag, a label) cannot be raycast without it: three.js throws
    for (const h of focusRay.intersectObject(scene, true)) {
      const o = h.object;
      if (o.isMesh && o !== selRing && !ofRobot(o) && shownChain(o)) out.add(o);
    }
  }
  return out;
}
function focusChoose(id) {
  const R = robots.find((x) => x.def.id === id);
  FOCUS.id = id; FOCUS.dist = 8; FOCUS.az = FOCUS_BASE.az; FOCUS.el = FOCUS_BASE.el; FOCUS.chosen = null;
  if (!R) return;
  let best = null;
  for (const el of [FOCUS_BASE.el, FOCUS_BASE.el + 0.3]) {
    for (const k of [0, 1, -1, 2, -2, 3, -3, 4, -4, 5, -5, 6]) {
      const az = FOCUS_BASE.az + (k * Math.PI) / 6, n = focusBlockers(R, focusPose(R, az, el, FOCUS.dist).p).size;
      if (!best || n < best.n) best = { az, el, n, k };
      if (n === 0) break;
    }
    if (best.n === 0) break;
  }
  FOCUS.az = best.az; FOCUS.el = best.el;
  FOCUS.chosen = { step: best.k, raised: best.el !== FOCUS_BASE.el, blockers: best.n,
    usual: focusBlockers(R, focusPose(R, FOCUS_BASE.az, FOCUS_BASE.el, FOCUS.dist).p).size };
}
function robotPose(id) {
  if (FOCUS.id !== id) focusChoose(id);
  const R = robots.find((x) => x.def.id === id);
  return focusPose(R, FOCUS.az, FOCUS.el, FOCUS.dist);
}
/* Faint what stands between the camera and the focused robot now; give the rest its own material back. */
function focusFadeSync() {
  const R = has3D && rbState.id && zoom.zoomed && !rbEl.hidden ? robots.find((x) => x.def.id === rbState.id) : null;
  const now = R ? focusBlockers(R, camera.position) : new Set();
  for (const [o, mat] of FOCUS.faded) {
    if (now.has(o)) continue;
    const faint = o.material;
    o.material = mat;
    for (const m of [].concat(faint)) m.dispose();
    FOCUS.faded.delete(o);
  }
  for (const o of now) {
    if (FOCUS.faded.has(o)) continue;
    FOCUS.faded.set(o, o.material);
    o.material = [].concat(o.material).map((m) => { const c = m.clone(); c.transparent = true; c.opacity = FOCUS_FADE; c.depthWrite = false; return c; });
    if (!Array.isArray(FOCUS.faded.get(o))) o.material = o.material[0];
  }
}
/* A room or a robot about to be taken down (40-scene.js liveDropRoom / liveDropRobot): what of it is faint gets its
   own material back first, so disposeTree works as if nothing had been faint — the room's own materials disposed,
   the shared ones left — and the faint copies go with it. Left faint, disposeTree disposed the copies and never the
   own materials (a library lane's review, 10-18). */
function focusRelease(root) {
  for (const [o, mat] of FOCUS.faded) {
    let inside = false;
    for (let x = o; x; x = x.parent) if (x === root) { inside = true; break; }
    if (!inside) continue;
    const faint = o.material;
    o.material = mat;
    for (const m of [].concat(faint)) m.dispose();
    FOCUS.faded.delete(o);
  }
}
const focusing = () => has3D && !!rbState.id && zoom.zoomed && !camTween;
{
  // drag: around the robot; wheel and pinch: nearer or farther. Only while a robot's card has the camera.
  canvas.addEventListener('pointerdown', (e) => {
    if (!focusing()) return;
    FOCUS.touches.set(e.pointerId, [e.clientX, e.clientY]);
    if (FOCUS.touches.size === 2) { const [a, b] = [...FOCUS.touches.values()]; FOCUS.pinch = { d: Math.hypot(a[0] - b[0], a[1] - b[1]), dist: FOCUS.dist }; FOCUS.drag = null; }
    else FOCUS.drag = { x: e.clientX, y: e.clientY, az: FOCUS.az, el: FOCUS.el };
  });
  canvas.addEventListener('pointermove', (e) => {
    if (!focusing() || !FOCUS.touches.has(e.pointerId)) return;
    FOCUS.touches.set(e.pointerId, [e.clientX, e.clientY]);
    if (FOCUS.pinch && FOCUS.touches.size === 2) {
      const [a, b] = [...FOCUS.touches.values()], d = Math.hypot(a[0] - b[0], a[1] - b[1]);
      FOCUS.dist = Math.min(FOCUS_DIST[1], Math.max(FOCUS_DIST[0], FOCUS.pinch.dist * (FOCUS.pinch.d / Math.max(1, d))));
    } else if (FOCUS.drag) {
      FOCUS.az = FOCUS.drag.az - (e.clientX - FOCUS.drag.x) * 0.008;
      FOCUS.el = Math.min(FOCUS_EL[1], Math.max(FOCUS_EL[0], FOCUS.drag.el + (e.clientY - FOCUS.drag.y) * 0.006));
    }
  });
  const up = (e) => { FOCUS.touches.delete(e.pointerId); if (FOCUS.touches.size < 2) FOCUS.pinch = null; if (!FOCUS.touches.size) FOCUS.drag = null; };
  canvas.addEventListener('pointerup', up);
  canvas.addEventListener('pointercancel', up);
  canvas.addEventListener('wheel', (e) => {
    if (!focusing()) return;
    e.preventDefault();
    FOCUS.dist = Math.min(FOCUS_DIST[1], Math.max(FOCUS_DIST[0], FOCUS.dist * Math.exp(e.deltaY * 0.0015)));
  }, { passive: false });
}
function openRobot(id, opener) {
  if (projectOfRobot(id)) LAST_ROBOT.set(projectOfRobot(id), id);   // whichever way it was opened (list, tag, card, notification)
  rbState.seen = { id, room: projectOfRobot(id) || null, name: (PROJECT[projectOfRobot(id)] || {}).name || '' }; rbState.moved = null;
  NOTIFY.opened.set(id, Date.now());   // the session looked at since its turn's end: no 入力待ち reminder (notifyIdle)
  holdView('rb');
  if (wb.open) closeWhiteboard();
  if (tb.open) closeTaskBoard();
  const showing = !!rbState.id;
  rbState.id = id;
  zoom.waitFor = null;
  if (showing) {   // another robot on the open card: the camera goes to it too (as ← → do)
    renderRobot(latestModel); $('rb-close').focus({ preventScroll: true });
    zoomToRobot(id);
    return;
  }
  // no 3D, or the robot is not in the scene yet (another floor, another room of the one-room view): the card alone, and
  // the camera goes to the robot when the scene puts it there (rbZoomWhenBuilt)
  if (!has3D || !robots.some((x) => x.def.id === id)) {
    if (!zoom.zoomed) zoom.returnPose = null;   // nothing to fly back from when the card closes
    if (has3D) zoom.waitFor = id;
    showOverlay(rbEl); renderRobot(latestModel); $('rb-close').focus({ preventScroll: true }); return; }
  zoomTo(robotPose(id), opener, () => {
    if (rbState.id !== id) return;
    showOverlay(rbEl);
    renderRobot(latestModel);
    $('rb-close').focus({ preventScroll: true });
  });
}
/* The camera to the robot whose card is open: now when it is in the scene, else when the scene puts it there. */
function zoomToRobot(id) {
  if (!has3D) return;
  if (robots.some((x) => x.def.id === id)) { zoom.waitFor = null; zoomTo(robotPose(id), null, () => {}); }
  else zoom.waitFor = id;
}
/* Called by the scene after it has put its robots (40-scene.js liveSync): a card opened before its robot was there gets
   the camera now — the switch back to a project in the one-room view puts that room's robots a frame later. */
function rbZoomWhenBuilt() {
  const id = zoom.waitFor;
  if (!id) return;
  if (rbState.id !== id) { zoom.waitFor = null; return; }
  if (!robots.some((x) => x.def.id === id)) return;
  const from = !zoom.zoomed;
  zoomToRobot(id);
  // Not zoomed, the camera was still on (or flying from) the room before: closing goes back to the room shown now.
  if (from) zoom.returnPose = roomPose(viewRoom());
}
/* The room the camera shows with no card open: the project picked, or the floor (as liveSync chooses). */
function viewRoom() {
  return UI.project === 'all' || !PROJECT[UI.project] || (SOURCE.mode === 'live' && !PROJECT[UI.project].shown) ? 'all' : UI.project;
}
/* The rooms in view: the project picked, or the rooms of the floor shown. */
function roomsInView() {
  const live = SOURCE.mode === 'live';
  return ROOMS.filter((r) => inScope(r.id) && (!live || UI.project !== 'all' || !LIVE.shown.length || LIVE.shown.includes(r.id))).map((r) => r.id);
}
/* Picking a robot, from anywhere outside its card (ticket 2026-10-21-jui-viz-3d-zoom-lost-after-project-switch; with
   2026-10-21-jui-viz-talk-panel-tabs-and-robot-list): the lists, the 3D, the notifications, a talk. Every way ends as a
   press on the robot in the 3D does — its room shown, its card open, the camera on it. A robot outside the view (another
   project's room, another floor) is remembered in its room and its project switched to: with a card open, the switch
   opens it with the view held (setProject); with none, it opens after the switch and the camera goes to it when the
   scene has put it there (rbZoomWhenBuilt). openRobot is the part inside: only this and setProject call it. */
function selectRobot(id, opener) {
  if (!DEF[id]) return;
  const p = projectOfRobot(id);
  const away = !!p && !!PROJECT[p] && !roomsInView().includes(p);
  if (away) {
    LAST_ROBOT.set(p, id);
    if (rbState.id) setProject(p);
    else setProject(p, { camera: false });
    if (rbState.id === id) return;
  }
  const from = !zoom.zoomed;
  openRobot(id, opener);
  // From no card, the camera was still on the room before (or wherever it was turned): closing goes back to the room
  // switched to. A robot not in the scene yet sets it when it gets the camera (rbZoomWhenBuilt).
  if (away && from && has3D && zoom.zoomed) zoom.returnPose = roomPose(viewRoom());
}
/* The open card's robot moved to another room (ticket 2026-10-21-jui-viz-camera-does-not-follow-robot-walking-rooms;
   the ruling of 10-21): a room in view, it walks there and the camera follows it each frame (40-scene.js). A room out of
   the view (the one-room view, another floor) put it out of the 3D and the camera stayed where it was: now the view
   follows it as selectRobot does, and a toast says so. Not right after a switch by hand (FOLLOW_HAND_MS): the card
   says where it went, with a button to go there. Its room closed: the card stays open and says so. Only while its card
   is open; called after each liveSync, never inside it (setProject lays the rooms out again). */
function rbFollow() {
  const id = rbState.id;
  if (SOURCE.mode !== 'live' || !id) return;
  const room = projectOfRobot(id) || null, seen = rbState.seen;
  if (!seen || seen.id !== id) { rbState.seen = { id, room, name: room && PROJECT[room] ? PROJECT[room].name : '' }; rbState.moved = null; return; }   // ← →: another robot
  if (!room || !PROJECT[room]) {   // its room closed: its project gone (the same id, or none)
    if (rbState.moved && rbState.moved.closed !== undefined) return;
    const was = seen.name || '';
    seen.room = room;
    rbState.moved = { closed: was };
    renderRobot(latestModel);
    showToast(tl('panel.rb.follow.closed.toast', { id, was: was ? tl('panel.rb.follow.was', { name: was }) : '' }));
    return;
  }
  if (seen.room === room) return;
  seen.room = room; seen.name = PROJECT[room].name;
  rbState.moved = null;
  if (roomsInView().includes(room)) { renderRobot(latestModel); return; }
  if (Date.now() - FOLLOW.handAt < FOLLOW_HAND_MS) { rbState.moved = { room }; renderRobot(latestModel); return; }
  rbFollowTo(id, room);
}
function rbFollowTo(id, room) {
  FOLLOW.busy = true;
  try { selectRobot(id); } finally { FOLLOW.busy = false; }
  showToast(tl('panel.rb.follow.moved.toast', { id, room: PROJECT[room].name }));
}
rbEl.addEventListener('click', (e) => {
  if (!e.target.closest('[data-rb-moved-go]') || !rbState.id || !rbState.moved || !rbState.moved.room) return;
  selectRobot(rbState.id);   // pressed by hand: a switch by hand, as the project menu
});
function closeRobot({ byHand = false } = {}) {
  zoom.waitFor = null;
  if (!rbState.id) { releaseView('rb'); return; }
  if (byHand && projectOfRobot(rbState.id)) LAST_ROBOT.set(projectOfRobot(rbState.id), null);   // closed by hand: none is remembered
  rbState.id = null; rbState.seen = null; rbState.moved = null;
  hideOverlay(rbEl);
  histSync();
  talkSync();
  FOCUS.id = null;      // the next robot opened chooses its view afresh
  focusFadeSync();      // everything faint gets its own material back
  releaseView('rb');    // the camera goes back only when no other screen holds the view (VIEW_HOLD)
}
/* ← → on the robot card (requester, 10-18: "この画面の時に左右キーとかでロボットを切り替えれるようにできる？"): the
   robots in view — the project picked, or the rooms of the floor shown — room by room in the rooms' order, then by
   label; robots leaving are skipped; the ends wrap. The card keeps its tab (55-history.js holds it), and the camera
   flies with the existing zoomTo (the camera itself is 40-scene.js's). */
function robotCycle() {
  const live = SOURCE.mode === 'live';
  const rooms = roomsInView();
  return ROBOT_DEFS.filter((d) => rooms.includes(projectOfRobot(d.id)) && !(live && LIVE.leaving[d.id]))
    .sort((a, b) => rooms.indexOf(projectOfRobot(a.id)) - rooms.indexOf(projectOfRobot(b.id)) || a.id.localeCompare(b.id, 'ja', { numeric: true }))
    .map((d) => d.id);
}
function stepRobot(dir) {
  const list = robotCycle();
  if (!rbState.id || list.length < 2) return;
  const i = list.indexOf(rbState.id);
  goRobot(list[i < 0 ? 0 : (i + dir + list.length) % list.length]);
}
/* The card on another robot, as ← → do it (the camera flies, the tab stays): also a linked name in the history. */
function goRobot(next) {
  if (!rbState.id || !next || next === rbState.id) return;
  rbState.id = next;
  renderRobot(latestModel);
  zoomToRobot(next);
}
rbEl.addEventListener('click', (e) => { const b = e.target.closest('[data-rb-step]'); if (b) stepRobot(Number(b.dataset.rbStep)); });
/* 2.3.4 (requester 10-19: "タブ選択してる時左右キーがタブの移動になるのやめてほしい 左右はロボットの移動でタブの移動はtabキーに
   できる？"): ← → switch robots wherever the focus is on the card, the tabs included (2.3.1 moved between the tabs there),
   except where text is typed (an input, a textarea, a select, an editable element) and while an IME composes. The tabs
   move with Tab instead (below). */
document.addEventListener('keydown', (e) => {
  if ((e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') || e.altKey || e.ctrlKey || e.metaKey || e.shiftKey) return;
  if (e.isComposing || e.keyCode === 229) return;                                                   // an IME is composing
  if (!rbState.id || rbEl.hidden || !popEl.hidden || logState.open || alwaysDlg || clockDlg) return;
  const t = e.target;
  if (t && (t.isContentEditable || (t.closest && t.closest('input, textarea, select')))) return;   // typing keeps its keys
  e.preventDefault();
  stepRobot(e.key === 'ArrowRight' ? 1 : -1);
});
/* 2.3.5 (requester 10-19: "部屋の状態で左右キー押したら左右の部屋に移動したい それと階全体表示で上下押したら上下の階に移動したい"):
   with no card open, in the room close-up ← → go to the room before / after on this floor, and on the whole floor ↑ ↓ go
   one floor up / down (the same as ▲ ▼). The card's own ← → (above) are untouched: this handler does nothing while a
   card is open. Nothing either where text is typed, while an IME composes, with a modifier, while a dialog, a board,
   the log or the building covers the floor, and in the demo (one office). Only a key that acts is taken
   (preventDefault); the room's ↑ ↓ and the floor's ← → stay the page's (they do nothing here). */
/* The rooms of the floor shown, in the order ← → walk them. The requester's rulings (10-19): the floor's own layout
   (the scene's row and column of each room, layoutRooms), read like text — the back row left to right, then the front
   row left to right; empty slots are skipped. Swap this one function to change the order. The walk wraps (ruling 2:
   after the last room the first, before the first the last) and never leaves the floor (floors are ↑ ↓). */
function arrowRoomOrder() {
  const ids = (LIVE.floors[LIVE.floor] || []).filter((id) => PROJECT[id]);
  return ids.sort((a, b) => (PROJECT[a].row - PROJECT[b].row) || (PROJECT[a].col - PROJECT[b].col));
}
function roomStep(dir) {
  const list = arrowRoomOrder(), i = list.indexOf(UI.project);
  if (i < 0 || list.length < 2) return false;
  const next = list[(i + dir + list.length) % list.length];   // wraps, on this floor
  setProject(next);                  // the room's tag, ← フロア全体に戻る, the project menu and the camera follow
  return true;
}
const arrowsCovered = () => !!(rbState.id || !rbEl.hidden || !popEl.hidden || logState.open || wb.open || tb.open || alwaysDlg || clockDlg
  || specHelp || LIGHT.el || document.querySelector('[aria-modal="true"]:not([hidden])'));
document.addEventListener('keydown', (e) => {
  if (!['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(e.key) || e.altKey || e.ctrlKey || e.metaKey || e.shiftKey) return;
  if (e.isComposing || e.keyCode === 229 || e.defaultPrevented) return;
  const t = e.target;
  if (t && (t.isContentEditable || (t.closest && t.closest('input, textarea, select')))) return;
  if (SOURCE.mode !== 'live' || !has3D || TOWER.on || zoom.zoomed || arrowsCovered()) return;
  const room = UI.project !== 'all' && PROJECT[UI.project] && PROJECT[UI.project].shown;
  if (room && (e.key === 'ArrowLeft' || e.key === 'ArrowRight')) {
    e.preventDefault();
    roomStep(e.key === 'ArrowRight' ? 1 : -1);
  } else if (UI.project === 'all' && (e.key === 'ArrowUp' || e.key === 'ArrowDown')) {
    e.preventDefault();
    if (LIVE.floors.length > 1) liveFloorStep(e.key === 'ArrowUp' ? 1 : -1);
  }
});
/* Tab on the card's tabs: 今の様子 → Tab selects 応答の履歴 and focuses it; 応答の履歴 → Tab goes on into the card (the
   browser's own order); Shift+Tab is the reverse (応答の履歴 → 今の様子 → what is before the tabs). Never a dead end. */
rbEl.addEventListener('keydown', (e) => {
  if (e.key !== 'Tab' || e.altKey || e.ctrlKey || e.metaKey) return;
  const tab = e.target && e.target.closest && e.target.closest('[role="tablist"] [role="tab"]');
  if (!tab) return;
  const tabs = [...tab.closest('[role="tablist"]').querySelectorAll('[role="tab"]')], k = tabs.indexOf(tab);
  const next = tabs[k + (e.shiftKey ? -1 : 1)];
  if (!next) return;                                  // the last tab forward, the first back: the browser's order
  e.preventDefault();
  next.click();
  const want = next.dataset.fk;   // the card's tabs, or the talk list's (58-talk.js)
  const again = [...rbEl.querySelectorAll('[role="tab"]')].find((b) => b.dataset.fk === want);   // the card may have been rebuilt
  if (again) again.focus();
});
/* The card's mark when its robot moved and the view did not follow (rbFollow). */
function rbMovedHTML() {
  const m = rbState.moved;
  if (!m) return '';
  if (m.room === undefined) return `<p class="rb-moved" data-rb-moved>${esc(tl('panel.rb.follow.closed', { was: m.closed ? tl('panel.rb.follow.was', { name: m.closed }) : '' }))}</p>`;
  const name = PROJECT[m.room] ? PROJECT[m.room].name : m.room;
  return `<p class="rb-moved" data-rb-moved>${esc(tl('panel.rb.follow.moved', { room: name }))} <button type="button" class="link-btn" data-rb-moved-go data-fk="rb-moved-go">${esc(tl('panel.rb.follow.go'))}</button></p>`;
}
function renderRobot(model) {
  const id = rbState.id;
  if (!id || rbEl.hidden) return;
  const d = DEF[id], sess = SESSION_OF[id], isMain = sess === id, st = robotState[id];
  const specIdx = model.specs.findIndex((s) => s.by === id), spec = specIdx >= 0 ? model.specs[specIdx] : null;
  const pending = model.pending.find((p) => p.who === id) || null;
  const order = { doing: 0, wait: 1, todo: 2, done: 3 };
  const owned = model.tasks.filter((x) => (isMain ? x.list === id : x.owner === id)).sort((a, b) => order[a.col] - order[b.col] || a.id - b.id);
  const subs = isMain ? (SESSIONS.find((s) => s.id === id) || { robots: [] }).robots.filter((r) => r !== id) : [];
  keyed(rbEl, JSON.stringify([id, NAMES.rev, projectOfRobot(id) || '', rbState.moved, permSig(pending), specIdx, owned.map((x) => `${x.key}:${x.col}:${x.perm ? 1 : 0}:${x.subject}`)]), () => {
    const room = (SESSIONS.find((s) => s.id === sess) || { room: (PROJECT[projectOfRobot(id)] || {}).name || '' }).room;
    const tasksHTML = owned.length ? `<ul class="rb-tasks">${owned.map((x) => {
      const [c, l] = x.perm ? ['st-waiting', tl('status.waiting')] : x.col === 'wait' ? [x.waitingFor === 'question' ? 'st-asking' : 'st-waiting', waitLabel(x)] : COL_STATE[x.col];
      return `<li><button type="button" class="task-open" data-open="${esc(x.key)}" data-fk="rt-${esc(x.key)}"><span class="state ${esc(c)}">${esc(l)}</span><span class="tid">${esc(x.list)} ${esc(taskRef(x))}</span><span class="subject">${x.harness ? `<span class="h-tag">${esc(x.harness)}</span>` : ''}${esc(x.subject)}</span>${!isMain || !x.owner ? '' : `<span class="rb-owner">${pill(x.owner, DEF[x.owner].role)}</span>`}</button></li>`;
    }).join('')}</ul>` : `<p class="rb-none">${esc(tl(isMain ? 'panel.rb.tasks.empty' : 'panel.rb.owned.none'))}</p>`;
    return `<div class="rb-head" style="--c:${ROLES[d.role].color}"><span class="rb-badge" aria-hidden="true">${esc(id)}</span><div><h2 class="rb-name" id="rb-title">${esc(isMain ? d.title || tl('panel.rb.main', { id }) : d.agent)}</h2><p class="rb-sub">${esc(isMain ? `${d.title ? tl('panel.rb.main.head', { id, head: d.head }) : d.agent} · ${room}` : tl('panel.rb.sub', { role: ROLE_JA[d.role], sess, room }))}</p></div><div class="rb-side"><div class="rb-menu"><button type="button" class="wb-btn rb-talk" data-rb-talk data-fk="rb-talk" aria-pressed="false" aria-label="${esc(tl('talk.title'))}" title="${esc(tl('panel.rb.talk.title'))}">${TALK_ICON}<span>${esc(tl('talk.title'))}</span><span class="rb-talk-n" data-rb-talk-n hidden></span></button><button type="button" class="wb-btn rb-clock" data-rb-clock data-fk="rb-clock" aria-haspopup="dialog" aria-describedby="rb-clock-why">${esc(tl('panel.clk.button'))}</button></div><div class="rb-nav"><button type="button" class="rb-step" data-rb-step="-1" data-fk="rb-prev" aria-label="${esc(tl('panel.rb.prev'))}" title="${esc(tl('panel.rb.prev'))}">‹</button><button type="button" class="rb-step" data-rb-step="1" data-fk="rb-next" aria-label="${esc(tl('panel.rb.next'))}" title="${esc(tl('panel.rb.next'))}">›</button><button type="button" class="wb-btn" id="rb-close" data-rb-close data-fk="rb-close">${esc(tl('panel.rb.back'))}</button></div></div><p class="rb-clock-why" id="rb-clock-why" data-rb-clock-why hidden></p>${rbMovedHTML()}</div>
<div class="rb-tabs"><button type="button" class="wb-btn rb-wide-btn" data-rb-wide data-fk="rb-wide" aria-pressed="false" aria-controls="rb" hidden>${esc(tl('hist.wide.on'))}</button><div class="rb-tablist" role="tablist" aria-label="${esc(tl('panel.rb.tabs'))}"><button type="button" role="tab" data-rb-tab="now" data-fk="rb-tab-now" aria-selected="true">${esc(tl('panel.rb.tab.now'))}</button><button type="button" role="tab" data-rb-tab="history" data-fk="rb-tab-history" aria-selected="false">${esc(tl('panel.rb.tab.history'))}</button></div></div>
<div class="rb-body rb-hist" data-rb-hist hidden aria-label="${esc(tl('panel.rb.tab.history'))}" tabindex="0"></div>
<div class="rb-body" tabindex="0" aria-label="${esc(tl('panel.rb.tab.now'))}">
<section class="rb-sec" aria-labelledby="rb-h-now"><h3 id="rb-h-now">${esc(tl('panel.rb.now'))}</h3><div class="rb-now"><p class="rb-state"><span class="rb-lamp" data-rb-lamp></span><b data-rb-state></b><span class="rb-since">${esc(tl('panel.rb.lamp'))}<span data-rb-lampname></span></span></p><p class="rb-act" data-rb-act></p><p class="rb-git" data-rb-git hidden title="${esc(tl('panel.rb.git.title'))}"></p><p class="rb-cond" data-rb-cond></p><p class="rb-looks" data-rb-looks hidden></p>${spec ? `<p class="rb-spec"><button type="button" class="link-btn" data-spec-open="${specIdx}" data-fk="rb-spec">${esc(tl('panel.rb.spec', { name: spec.name, screen: spec.screen }))}</button> <span data-rb-specnow></span></p><span class="rb-segs" style="--c:${ROLES[d.role].color}">${SEGS}</span>` : ''}${(SOURCE.mode === 'demo' && id === 'a2') ? '<p class="rb-test" data-rb-test></p><div class="prog" data-rb-prog role="img"><span class="p"></span><span class="r"></span></div>' : ''}</div></section>
${pending ? `<section class="rb-sec" aria-label="${esc(tl('panel.rb.perm'))}">${permDetail(pending, 'rb')}</section>` : ''}
${SOURCE.mode === 'live' ? `<section class="rb-sec" aria-labelledby="rb-h-tests"><h3 id="rb-h-tests">${esc(tl('panel.rb.tests'))}</h3><div data-rb-tests></div></section>` : ''}
<section class="rb-sec" aria-labelledby="rb-h-tasks"><h3 id="rb-h-tasks">${esc(tl(isMain ? 'panel.rb.tasks' : 'panel.rb.owned'))}<small>${esc(tl('panel.tb.count', { n: owned.length }))}</small></h3>${tasksHTML}</section>
${subs.length ? `<section class="rb-sec" aria-labelledby="rb-h-subs"><h3 id="rb-h-subs">${esc(tl('panel.rb.subs'))}</h3><ul class="rb-subs">${subs.map((r) => `<li><button type="button" class="who-btn" data-robot-open="${esc(r)}" data-fk="rs-${esc(r)}">${pill(r, DEF[r].role)}<span>${esc(DEF[r].agent)}</span></button><span class="state" data-rb-sub="${esc(r)}"></span><p class="act" data-rb-subact="${esc(r)}"></p></li>`).join('')}</ul></section>` : ''}
<section class="rb-sec" aria-labelledby="rb-h-log"><h3 id="rb-h-log">${esc(tl('panel.rb.recent'))}</h3><ul class="tbd-list" data-recent="${esc(id)}"></ul><button type="button" class="link-btn" data-log-robot="${esc(id)}" data-fk="rb-log">${esc(tl('panel.rb.log', { id }))}</button></section>
</div>`;
  });
  const S = STATES[st.state] || STATES.idle;
  const play = SOURCE.mode === 'live' && has3D ? playTagText(id) : '';   // a game (2.3.3): the same words as the name tag
  setText(rbEl.querySelector('[data-rb-state]'), st.asking ? tl('status.asking') : play ? `${S.name} · ${play}` : S.name);
  setText(rbEl.querySelector('[data-rb-lampname]'), st.asking ? LAMP_TEXT.asking : LAMP_TEXT[S.lamp] || '');
  const lamp = rbEl.querySelector('[data-rb-lamp]'); if (lamp) lamp.style.background = st.asking ? LAMP.asking : LAMP[S.lamp];   // its swatch as its name
  setText(rbEl.querySelector('[data-rb-act]'), st.act);
  // the box (2.3.4): its last push / pull, from the server's agent.git
  const gitEl = rbEl.querySelector('[data-rb-git]');
  if (gitEl) { const g = st.git; gitEl.hidden = !g; if (g) setText(gitEl, tl('panel.rb.git', { label: g.label || '', time: new Date(g.at || 0).toTimeString().slice(0, 5) })); }
  // Tiredness and heavy work in words too (the 3D showed them, the card did not — 10-18 review)
  const cond = robotCondition(id), parts = [];
  if (cond.tired) parts.push(tl('panel.rb.tired', { n: Math.floor(cond.hours) }));
  if (cond.heavy) {
    const H = cond.heavy, why = [];
    if (H.reasons.includes('tokens')) why.push(tl('panel.heavy.tokens', { n: fmtNum(Math.round(H.tokensPerMin || 0)) }));
    if (H.reasons.includes('tool')) why.push(tl('panel.heavy.tool', { n: Math.round(H.toolSec || 0) }));
    if (H.reasons.includes('subagents')) why.push(tl('panel.heavy.subagents', { n: H.subagents || 0 }));
    parts.push(tl('panel.heavy', { why: why.join(' · ') }));
  }
  const brk = SOURCE.mode === 'live' ? brkPanelText(id) : '';   // on a break (10-19): the name tag's words
  if (brk) parts.push(brk);
  const condEl = rbEl.querySelector('[data-rb-cond]');
  if (condEl) { setText(condEl, parts.join(' / ')); condEl.hidden = !parts.length; }
  // what the three looks of heavy work mean (2.3.6), only while the robot works hard
  const looksEl = rbEl.querySelector('[data-rb-looks]');
  const RB = robots.find((x) => x.def.id === id), causes = RB ? heavyCauses(RB.robot) : [];   // what the robot shows
  if (looksEl) { looksEl.hidden = !causes.length; if (causes.length) setText(looksEl, HEAVY_LEGEND); }
  if (spec) {
    const k = activeSec(spec);
    const st = specStatus(spec);
    paintStatus(rbEl.querySelector('[data-rb-specnow]'), { text: `${st.text}${k >= 0 ? ` · ${SECTIONS[k]}` : ''}`, title: st.title });
    paintSegs(rbEl.querySelector('.rb-segs .segs'), spec);
  }
  if ((SOURCE.mode === 'demo' && id === 'a2')) {
    const T = model.tests, n = CASES.length;
    setText(rbEl.querySelector('[data-rb-test]'), `${T.file} · ${T.statusText}`);
    const bar = rbEl.querySelector('[data-rb-prog]');
    bar.setAttribute('aria-label', tl('panel.tests.prog', { passed: T.passed, n }));
    bar.children[0].style.width = `${(T.passed / n) * 100}%`; bar.children[1].style.width = `${T.runningIdx >= 0 ? 100 / n : 0}%`;
  }
  clockPaint(id);
  rbEl.querySelectorAll('[data-rb-sub]').forEach((el) => paintState(el, robotBadge(el.dataset.rbSub)));
  rbEl.querySelectorAll('[data-rb-subact]').forEach((el) => setText(el, robotState[el.dataset.rbSubact].act));
  paintSince(rbEl, model.t, tl('panel.since.wait'));
  rbEl.querySelectorAll('[data-recent]').forEach((el) => setHTML(el, recentHTML(el.dataset.recent)));
  const testsEl = rbEl.querySelector('[data-rb-tests]');
  if (testsEl) setHTML(testsEl, robotTestsHTML(robotRuns(id)));   // rewritten on every refresh while a run moves
  histSync();   // 55-history.js: the tab shown, and the history kept fresh while it is
  talkSync();   // 58-talk.js: the talk socket follows this robot, and its pane shows while トーク is on
  focusFadeSync();   // what stands between the camera and this robot, faint
}

/* ---------- 退勤: end this robot's session from its card (requester, 10-19) ----------
   「3Dに戻るの上あたりに退勤ボタン置いて、それ押したら確認ダイアログの後にセッション消す」. Measured with the requester (11:10–11:15):
   SIGTERM ends claude in about 1.5 s everywhere, but only a terminal is left in a good state (back at its shell); the
   VS Code tab stays with an error and the desktop app shows no change. So the button works for terminal sessions only and
   is disabled elsewhere with the reason (the server refuses those too: clockout.py). The dialog names the robot, the
   session (its title), the folder and the client; its default focus is やめる. After 退勤させる the server sends SIGTERM once,
   sees the process go and marks the session ended — the robot then walks out of the door like any session that ended. */
const CLOCK_WHY = {
  vscode: tl('panel.clk.why.vscode'),
  desktop: tl('panel.clk.why.desktop'),
  other: tl('panel.clk.why.other'),
  unknown: tl('panel.clk.why.unknown'),
};
const CLIENT_JA = { terminal: tl('panel.client.terminal'), vscode: tl('panel.client.vscode'), desktop: tl('panel.client.desktop'), other: tl('panel.client.other'), unknown: tl('panel.client.unknown') };
const CLOCK = { busy: null, last: null };
let clockDlg = null;
function clockTarget(id) {
  if (SOURCE.mode !== 'live') return { why: tl('panel.clk.why.demo') };
  if (!id || !DEF[id]) return { why: '' };
  if (DEF[id].kind === 'sub') return { why: tl('panel.clk.why.sub', { id: SESSION_OF[id] }) };
  const sess = SESSIONS.find((x) => x.id === SESSION_OF[id]);
  if (!sess || sess.status === 'ended' || LIVE.leaving[id]) return { why: tl('panel.clk.why.ended') };
  const client = sess.client || 'unknown';
  if (client !== 'terminal') return { why: CLOCK_WHY[client] || CLOCK_WHY.unknown, client };
  if (location.hostname !== '127.0.0.1') return { why: tl('panel.clk.why.host', { port: location.port }), client };
  return { why: '', sess, client };
}
function clockPaint(id) {
  const btn = rbEl.querySelector('[data-rb-clock]'), why = rbEl.querySelector('[data-rb-clock-why]');
  if (!btn || !why) return;
  const t = clockTarget(id), busy = CLOCK.busy === id, last = CLOCK.last && CLOCK.last.id === id ? CLOCK.last : null;
  btn.disabled = !!t.why || busy;
  setText(btn, busy ? tl('panel.clk.busy') : tl('panel.clk.button'));
  const text = t.why || (last ? tl('panel.clk.failed', { error: last.error }) : '');
  setText(why, text);
  why.hidden = !text;
  why.classList.toggle('rb-clock-err', !t.why && !!last);
}
function openClockConfirm(id) {
  const t = clockTarget(id);
  if (t.why || clockDlg) return;
  const opener = rbEl.querySelector('[data-rb-clock]');
  const el = document.createElement('div');
  el.className = 'perm-confirm clock-confirm'; el.setAttribute('role', 'alertdialog'); el.setAttribute('aria-modal', 'true');
  el.setAttribute('aria-labelledby', 'clk-title'); el.setAttribute('aria-describedby', 'clk-note');
  const title = t.sess.title || tl('talk.noname');
  el.innerHTML = `<div class="pcf-box"><h3 id="clk-title">${esc(tl('panel.clk.title', { id }))}</h3>
<dl class="clk-facts"><dt>${esc(tl('panel.sb.robot'))}</dt><dd data-clk-robot>${pill(id, DEF[id].role)} ${esc(tl('panel.rb.main', { id }))}</dd><dt>${esc(tl('panel.sb.session'))}</dt><dd data-clk-title>${esc(title)}</dd><dt>${esc(tl('panel.clk.folder'))}</dt><dd data-clk-cwd><code>${esc(CWD[id] || '?')}</code></dd><dt>${esc(tl('panel.clk.client'))}</dt><dd data-clk-client>${esc(CLIENT_JA[t.client] || t.client)}</dd></dl>
<p id="clk-note">${esc(tl('panel.clk.note'))}</p>
<div class="pcf-acts"><button type="button" class="pa clk-go" data-clk-go>${esc(tl('panel.clk.go'))}</button><button type="button" class="pa clk-cancel" data-clk-cancel>${esc(tl('panel.cancel'))}</button></div></div>`;
  document.body.append(el);
  clockDlg = { el, id, opener, at: Date.now() };
  el.addEventListener('click', (e) => {
    if (e.target === el || e.target.closest('[data-clk-cancel]')) { closeClockConfirm(true); return; }
    if (e.target.closest('[data-clk-go]') && Date.now() - clockDlg.at > 350) clockGo(id);   // not the press that opened it
  });
  el.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); closeClockConfirm(true); return; }
    if (e.key === 'Tab') {   // the focus stays in the dialog
      const f = [...el.querySelectorAll('button')];
      const i = f.indexOf(document.activeElement);
      e.preventDefault();
      f[(i + (e.shiftKey ? -1 : 1) + f.length) % f.length].focus();
    }
  });
  el.querySelector('[data-clk-cancel]').focus();
}
function closeClockConfirm(back) {
  if (!clockDlg) return;
  const { el, opener } = clockDlg;
  clockDlg = null; el.remove();
  const again = back ? rbEl.querySelector('[data-rb-clock]') || opener : null;
  if (again && document.contains(again) && !again.disabled) again.focus({ preventScroll: true });
}
async function clockGo(id) {
  closeClockConfirm(false);
  if (clockTarget(id).why || CLOCK.busy) return;
  CLOCK.busy = id; CLOCK.last = null;
  if (rbState.id === id) clockPaint(id);
  const got = await SOURCE.clockOut(id);
  CLOCK.busy = null;
  if (got.ok) showToast(tl('panel.clk.done', { id }));
  else { CLOCK.last = { id, error: got.error || `HTTP ${got.status}` }; showToast(tl('panel.clk.failed.id', { id, error: CLOCK.last.error })); }
  if (rbState.id === id) clockPaint(id);
}
rbEl.addEventListener('click', (e) => { if (e.target.closest('[data-rb-clock]') && rbState.id) openClockConfirm(rbState.id); });

/* ---------- live: the test run in the side panel (plan 09 §4) ---------- */
const CASE_ICON = { pending: '○', running: '▶', passed: '✓', flaky: '⚠', failed: '✗', skipped: '–' };
/* A robot's runs on its card: platform, state, counts, the bar, and the failed cases by name (FAILED_SHOWN at most). */
const FAILED_SHOWN = 5;
function robotTestsHTML(runs) {
  if (!runs.length) return `<p class="rb-none">${esc(tl('panel.run.none'))}</p>`;
  return `<ul class="rb-runs">${runs.map((T) => robotRunHTML(T)).join('')}</ul>`;
}
function robotRunHTML(T) {
  const n = T.rows.length, pPct = n ? (T.passed / n) * 100 : T.runStatus === 'passed' ? 100 : 0, rPct = n && T.runningIdx >= 0 ? 100 / n : 0;
  const fPct = n ? (T.failed / n) * 100 : T.runStatus === 'failed' ? 100 : 0;
  const failedRows = T.rows.filter((c) => c.status === 'failed');
  const namesHTML = failedRows.slice(0, FAILED_SHOWN).map((c) => `<li>${esc(c.name)}</li>`).join('');
  const moreHTML = failedRows.length > FAILED_SHOWN ? `<li class="rb-fail-more">${esc(tl('panel.run.more', { n: Math.max(0, failedRows.length - FAILED_SHOWN) }))}</li>` : '';
  return `<li class="rb-run r-${esc(T.runStatus)}" data-rb-run="${esc(T.id)}"><p class="rb-run-head"><b>${esc(T.device || tl('panel.run.test'))}</b> <span${T.verdictWhy ? ` title="${esc(T.verdictWhy)}" data-verdict-why` : ''}>${esc(T.statusText)}</span>${T.savedAt ? `<small class="rb-saved">${esc(tl('panel.run.saved'))}</small>` : ''}</p><code class="rb-run-file">${esc(T.file)}</code>
<div class="prog" role="img" aria-label="${esc(tl('panel.run.prog', { passed: Number(T.passed), failed: Number(T.failed), n: Number(n) }))}"><span class="p" style="width:${Number(pPct)}%"></span><span class="r" style="width:${Number(rPct)}%"></span><span class="x" style="width:${Number(fPct)}%"></span></div>${namesHTML ? `<ul class="rb-fails" aria-label="${esc(tl('panel.run.failed'))}">${namesHTML}${moreHTML}</ul>` : ''}</li>`;
}
function liveTestsHTML(T) {
  const n = T.rows.length, pPct = n ? (T.passed / n) * 100 : T.runStatus === 'passed' ? 100 : 0, rPct = n && T.runningIdx >= 0 ? 100 / n : 0;
  const fPct = n ? (T.failed / n) * 100 : T.runStatus === 'failed' ? 100 : 0;
  const whoPillHTML = T.who && DEF[T.who] ? pill(T.who, DEF[T.who].role) : '';
  return `<div class="test-head"><div>${whoPillHTML} <code>${esc(T.file)}</code></div><code${T.verdictWhy ? ` title="${esc(T.verdictWhy)}" data-verdict-why` : ''}>${esc(T.device)}${T.device ? ' · ' : ''}${esc(T.statusText)}</code>
<div class="prog" role="img" aria-label="${esc(tl('panel.tests.prog', { passed: Number(T.passed), n: Number(n) }))}"><span class="p" style="width:${Number(pPct)}%"></span><span class="r" style="width:${Number(rPct)}%"></span><span class="x" style="width:${Number(fPct)}%"></span></div></div>
<ul class="cases">${T.rows.map((c, i) => `<li class="c-${esc(c.status)}"><span class="ic">${CASE_ICON[c.status] || '○'}</span><span>${i + 1}. ${esc(c.name)}</span>${c.status === 'running' ? `<span class="step">${esc(c.step)}</span>` : ''}</li>`).join('')}</ul>`;
}

/* ---------- live: "from now on" asks first (plan 08 §5) ----------
   Only the request's own suggestions can be added. The dialog lists each one — the rules and where they are
   saved — with a box each; the answer goes out only from its confirm button. */
const DEST_JA = {
  localSettings: tl('panel.dest.local'),
  projectSettings: tl('panel.dest.project'),
  userSettings: tl('panel.dest.user'),
  session: tl('panel.dest.session'),
};
function suggestionHTML(sg) {
  if (!sg || typeof sg !== 'object') return `<code>${esc(JSON.stringify(sg))}</code>`;
  const whereHTML = sg.destination ? `<small>${esc(tl('panel.sg.where', { where: DEST_JA[sg.destination] || sg.destination }))}</small>` : '';
  if (sg.type === 'addRules' && Array.isArray(sg.rules)) {
    const rulesHTML = sg.rules.map((r) => `<code>${esc(r && r.toolName ? `${r.toolName}${r.ruleContent ? `(${r.ruleContent})` : ''}` : JSON.stringify(r))}</code>`).join(' ');
    return `<span>${esc(tl(sg.behavior === 'deny' ? 'panel.sg.deny' : 'panel.sg.allow'))} ${rulesHTML}</span>${whereHTML}`;
  }
  if (sg.type === 'setMode') return `<span>${tlHTML('panel.sg.mode', { mode: sg.mode })}</span>${whereHTML}`;
  if (sg.type === 'addDirectories' && Array.isArray(sg.directories)) return `<span>${esc(tl('panel.sg.dirs'))}${sg.directories.map((d) => `<code>${esc(d)}</code>`).join(' ')}</span>${whereHTML}`;
  return `<code>${esc(JSON.stringify(sg))}</code>${whereHTML}`;
}
let alwaysDlg = null;
function openAlwaysConfirm(p, opener) {
  const list = Array.isArray(p.suggestions) ? p.suggestions : [];
  if (!list.length) { showToast(tl('panel.pcf.norules')); return; }
  closeAlwaysConfirm(false);
  const el = document.createElement('div');
  el.className = 'perm-confirm'; el.setAttribute('role', 'dialog'); el.setAttribute('aria-modal', 'true'); el.setAttribute('aria-labelledby', 'pcf-title');
  el.innerHTML = `<div class="pcf-box"><h3 id="pcf-title">${esc(tl('panel.pcf.title'))}</h3><p>${pill(p.who, DEF[p.who].role)} ${esc(tl('panel.pcf.pre'))}<b>${esc(p.tool)}</b> ${permSubject(p)}${esc(tl('panel.pcf.post'))}</p>
<ul class="pcf-list">${list.map((sg, i) => `<li><label><input type="checkbox" data-pcf="${i}" checked>${suggestionHTML(sg)}</label></li>`).join('')}</ul>
<div class="pcf-acts"><button type="button" class="pa pa-always" data-pcf-ok>${esc(tl('panel.pcf.ok'))}</button><button type="button" class="pa" data-pcf-cancel>${esc(tl('panel.cancel'))}</button></div></div>`;
  document.body.append(el);
  alwaysDlg = { el, p, opener };
  el.addEventListener('click', (e) => {
    if (e.target === el || e.target.closest('[data-pcf-cancel]')) { closeAlwaysConfirm(true); return; }
    if (!e.target.closest('[data-pcf-ok]')) return;
    const keep = [...el.querySelectorAll('[data-pcf]')].filter((c) => c.checked).map((c) => Number(c.dataset.pcf));
    if (!keep.length) { showToast(tl('panel.pcf.pick')); return; }
    const perm = alwaysDlg.p;
    closeAlwaysConfirm(true);
    SOURCE.decide(perm.id, 'allow', { perm, always: keep.length === list.length ? true : keep });
    refreshNow();
  });
  el.addEventListener('change', () => { el.querySelector('[data-pcf-ok]').disabled = ![...el.querySelectorAll('[data-pcf]')].some((c) => c.checked); });
  el.addEventListener('keydown', (e) => { if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); closeAlwaysConfirm(true); } });
  el.querySelector('[data-pcf-ok]').focus();
}
function closeAlwaysConfirm(back) {
  if (!alwaysDlg) return;
  const { el, opener } = alwaysDlg;
  alwaysDlg = null; el.remove();
  if (back && opener && document.contains(opener)) opener.focus({ preventScroll: true });
}

/* ---------- the call bell's dialog (2.3.5, ticket 2026-10-19-jui-viz-call-a-robot-button) ----------
   The bell in the room up close (40-scene.js) or the header's 呼び出し opens it for that project: a name (required, one
   line), a role text (optional), the command the server makes from them (SOURCE.callCommand -> /api/call-command,
   callcmd.py) and a copy button. Each edit asks again; only the latest answer is shown (CALL.seq), and the copy button
   is off whenever the shown line is not the one for what is typed now. Copy: the clipboard API (127.0.0.1 is a secure
   context); when that fails, the line is selected for a manual copy. viz runs nothing. */
const CALL = { project: null, opener: null, seq: 0, command: '', timer: 0 };
const callEl = $('call');
function openCall(project, opener) {
  if (!project || !PROJECT[project]) return;
  CALL.project = project; CALL.opener = opener || document.activeElement; CALL.command = '';
  const p = PROJECT[project];
  setText($('call-lead'), tl('panel.call.lead', { name: p.name, path: p.path || '' }));
  $('call-cmd').value = ''; setText($('call-why'), tl('panel.call.name')); $('call-copy').disabled = true;
  callEl.hidden = false;
  $('call-name').focus();
  callAsk();
}
function closeCall() {
  if (callEl.hidden) return;
  callEl.hidden = true; CALL.seq++; clearTimeout(CALL.timer);
  const back = CALL.opener;
  CALL.project = null; CALL.opener = null;
  if (back && document.contains(back) && back.focus) back.focus({ preventScroll: true });
}
function callAsk() {
  clearTimeout(CALL.timer);
  const seq = ++CALL.seq, project = CALL.project, name = $('call-name').value, role = $('call-role').value;
  CALL.command = ''; $('call-copy').disabled = true;
  if (!name.trim()) { $('call-cmd').value = ''; setText($('call-why'), tl('panel.call.name')); return; }
  CALL.timer = setTimeout(async () => {
    const got = await SOURCE.callCommand(project, name, role);
    if (seq !== CALL.seq || callEl.hidden) return;   // typed again (or closed) meanwhile: a newer answer comes
    if (!got.ok) { $('call-cmd').value = ''; setText($('call-why'), got.why || tl('panel.call.failed')); return; }
    CALL.command = got.command; $('call-cmd').value = got.command; $('call-copy').disabled = false;
    setText($('call-why'), got.flag === '--channels' ? tl('panel.call.ready')
      : tl('panel.call.ready.dev'));
  }, 150);
}
async function callCopy() {
  const line = CALL.command;
  if (!line) return;
  try {
    await navigator.clipboard.writeText(line);
    showToast(tl('panel.call.copied.toast'));
    setText($('call-why'), tl('panel.call.copied'));
  } catch (err) {
    const t = $('call-cmd'); t.focus(); t.select();
    showToast(tl('panel.call.nocopy.toast'));
    setText($('call-why'), tl('panel.call.nocopy'));
  }
}
$('call-name').addEventListener('input', callAsk);
$('call-role').addEventListener('input', callAsk);
$('call-copy').addEventListener('click', callCopy);
$('call-close').addEventListener('click', closeCall);
$('room-call').addEventListener('click', (e) => openCall(liveSolo(), e.currentTarget));
$('room-sr').addEventListener('click', (e) => {   // as a press on the room's server room door (40-scene.js); not with no docs/infra
  if (e.currentTarget.getAttribute('aria-disabled') === 'true') return;
  srEnter(liveSolo(), e.currentTarget);
});
callEl.addEventListener('click', (e) => { if (e.target === callEl) closeCall(); });
callEl.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); closeCall(); return; }
  if (e.key === 'Tab') {   // the focus stays in the dialog
    const f = [...callEl.querySelectorAll('input, textarea, button')].filter((x) => !x.disabled);
    const i = f.indexOf(document.activeElement);
    e.preventDefault();
    f[(i + (e.shiftKey ? -1 : 1) + f.length) % f.length].focus();
  }
});

/* ---------- browser notifications and the question window's setting (2.3.6) ----------
   Requester 10-19: 「完了通知がwebプッシュで届くようにしてほしい。許可や質問も同様」, then 「開いている間でいい」: the
   Notification API only, while a viz page is open — no service worker, no push service; nothing leaves the machine.
   - done: a main robot's turn ends (its Stop); subagents never. perm: a new permission waits. ask: a new question waits.
   - one ring per event in all the tabs: the rung keys (server start + kind + id) are kept in localStorage and read
     and written under one Web Lock; a tab without storage decides alone. The notification's tag is the key too.
   - nothing from before the page was loaded or connected: the waiting permissions and questions of the first snapshot
     are taken as seen; neither the recent events the server sends after each snapshot nor the history asked for are
     rung; and an event older than 2 minutes is not either.
   - quiet: the page in front and focused, and that very thing on screen (the robot's card; that permission or that
     question on the board).
   - a click: the page comes forward and opens the robot's card, or the board on that permission, or the questions.
   - the switches per kind are kept in this browser (localStorage, try/catch); the browser's permission is asked only
     from the button in the settings, never on load.
   - while question notifications can be shown (permission granted, the kind on) the page says so to the server every
     4 s and whenever the server asks (notify.ping): then a question waits for an answer though the page is hidden
     (the orchestrator's ruling 10-19; it lapses notifyPresenceSec after the last word, a closed tab included). */
const NOTIFY_PREFS = 'jui-viz-notify', NOTIFY_RUNG = 'jui-viz-notify-rung', NOTIFY_KINDS = ['done', 'perm', 'ask', 'idle', 'chime'];
// the chime's loudness (requester 10-20: 「音が少し小さいね」): the tones' peak gain, 中 by default (0.08 before)
const NOTIFY_VOLUMES = { low: 0.1, mid: 0.2, high: 0.35 };
const NOTIFY = { on: { done: true, perm: true, ask: true, idle: true, chime: true }, lastStop: new Map(), opened: new Map(), volume: 'mid', audio: null, seen: new Set(), based: { perm: false, ask: false }, said: false, settings: null, pings: 0,
  tab: `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`, peers: new Map(), yieldMs: 1500 };
function notifyLoadPrefs() {
  try {
    const v = JSON.parse(localStorage.getItem(NOTIFY_PREFS) || 'null');
    if (v && typeof v === 'object') for (const k of NOTIFY_KINDS) if (typeof v[k] === 'boolean') NOTIFY.on[k] = v[k];
    if (v && Object.hasOwn(NOTIFY_VOLUMES, v.volume)) NOTIFY.volume = v.volume;
  } catch (err) { /* no storage: the defaults */ }
}
notifyLoadPrefs();
// a switch turned in another tab holds here too (a kind turned off there must not ring from this one)
window.addEventListener('storage', (e) => { if (e.key === NOTIFY_PREFS) { notifyLoadPrefs(); notifySettingsShow(); notifyPresenceSay(); } });
function notifySavePrefs() { try { localStorage.setItem(NOTIFY_PREFS, JSON.stringify({ ...NOTIFY.on, volume: NOTIFY.volume })); } catch (err) { /* kept for this page only */ } }
const notifyCan = () => typeof Notification !== 'undefined';
const notifyGranted = () => notifyCan() && Notification.permission === 'granted';
const notifyName = (who) => String((DEF[who] && (DEF[who].title || DEF[who].agent)) || who).slice(0, 40);
function notifyViewing(kind, ref) {
  if (document.visibilityState !== 'visible' || !document.hasFocus()) return false;
  if (kind === 'done' || kind === 'idle') return rbState.id === ref.who;
  if (kind === 'perm') return tb.open && (tb.detail === `perm:${ref.id}` || (!!ref.task && tb.detail === ref.task) || (tb.waitView && !tb.detail));
  return tb.open && !!(qStripEl && qStripEl.querySelector(`[data-qcard="${CSS.escape(ref.id)}"]`));
}
function notifyOpen(kind, ref) {
  try { window.focus(); } catch (err) { /* the OS may keep it behind */ }
  if (kind === 'done' || kind === 'idle') { NOTIFY.opened.set(ref.who, Date.now()); if (DEF[ref.who]) selectRobot(ref.who, document.getElementById('scene-canvas')); }
  else if (kind === 'perm') openTaskBoard(null, ref.task || `perm:${ref.id}`);
  else { tb.waitView = true; openTaskBoard(null); }
}
/* The one place a notification is made. */
function notifyOut(key, body, onClick, title = 'jui viz') {
  const n = new Notification(title, { body, tag: key });
  n.onclick = () => { n.close(); onClick(); };
  return n;
}
/* The chime (2.3.6, ticket 2026-10-20-jui-viz-notify-chime; requester: 「鳴らす 鳴らすかどうかは設定で変えれる」): the
   page makes it with Web Audio (no sound file), quietly, when it shows a notification — the tab that showed it only,
   never when quiet. One switch for all three kinds (on by default, kept with them); done falls, a permission or a
   question rises. A browser starts an AudioContext only after the person has pressed something on the page: it is
   woken by the permission button and by the first press anywhere; until then the notification shows without sound
   and the settings say a press is needed. */
function notifyAudioMake() {
  try {
    const AC = window.AudioContext || window.webkitAudioContext;
    if (AC && !NOTIFY.audio) { NOTIFY.audio = new AC(); NOTIFY.audio.onstatechange = () => { notifySettingsShow(); notifyAudioSay(); }; }
  } catch (err) { /* no sound: the notification still shows */ }
  return NOTIFY.audio;
}
function notifyAudioWake() {
  const ac = notifyAudioMake();
  if (ac && ac.state !== 'running') ac.resume().catch(() => {}).finally(() => notifySettingsShow());
}
const notifyAudioReady = () => !!(NOTIFY.audio && NOTIFY.audio.state === 'running');
const notifyAudioState = () => (NOTIFY.audio ? NOTIFY.audio.state : 'none');
/* The real check (10-20): the banner showed and no chime was heard, though the same tones from a new AudioContext in
   the console were. A browser lets a context run only after a press on the page since it was loaded, and a context
   can go back to suspended; so right before each chime the page asks it to resume (at most RESUME_MS) and sounds only
   if it then runs. Each try is kept (NOTIFY.lastChime: the state before and after, the clock, played or not) and shown
   in the settings and the console, to tell the two apart the next time. */
const NOTIFY_RESUME_MS = 600;
async function notifyChime(kind) {
  if (!NOTIFY.on.chime) return;
  const rec = { at: Date.now(), kind, before: notifyAudioState(), after: null, t: null, played: false };
  try {
    const ac = notifyAudioMake();
    if (ac && ac.state !== 'running') await Promise.race([ac.resume().catch(() => {}), new Promise((done) => setTimeout(done, NOTIFY_RESUME_MS))]);
    rec.after = notifyAudioState();
    rec.t = ac ? +Number(ac.currentTime || 0).toFixed(2) : null;
    if (ac && ac.state === 'running') { rec.peak = notifyTones(ac, kind); rec.played = true; }
  } catch (err) { rec.error = String((err && err.message) || err); }
  rec.noTab = !rec.played && !notifyPeerCanSound();   // no tab of this browser could make it (the settings say so)
  NOTIFY.lastChime = rec;
  try { console.info('jui viz: chime', JSON.stringify(rec)); } catch (err) { /* the console is for the eye only */ }
  notifySettingsShow();
}
function notifyTones(ac, kind) {
  const peak = NOTIFY_VOLUMES[NOTIFY.volume] || NOTIFY_VOLUMES.mid;
  try {
    const t = ac.currentTime, notes = kind === 'done' ? [880, 660] : [660, 988];
    notes.forEach((hz, i) => {
      const o = ac.createOscillator(), g = ac.createGain(), at = t + i * 0.16;
      o.type = 'sine'; o.frequency.setValueAtTime(hz, at);
      g.gain.setValueAtTime(0.0001, at); g.gain.exponentialRampToValueAtTime(peak, at + 0.02); g.gain.exponentialRampToValueAtTime(0.0001, at + 0.3);
      o.connect(g); g.connect(ac.destination); o.start(at); o.stop(at + 0.32);
    });
  } catch (err) { /* no sound: the notification has shown */ }
  return peak;
}
/* Which tab rings (the real check 2, 10-20): two old tabs of an earlier check, their sound never started, took the
   one-time key first and showed the notification silently, while the tab in front could sound. Each tab says on a
   BroadcastChannel whether its sound runs (when it changes, every NOTIFY_SAY_MS, when a new tab asks, and good-bye
   when it goes); a tab that cannot sound leaves an event to a tab whose last word was that it can, and takes it
   itself only if, NOTIFY.yieldMs later, nobody has (the notification is never lost, and still shows once). A last
   word does not age: a hidden tab's timers can run once a minute (the browser's throttling), so its every-2-s word
   comes late though its sound runs; one gone without a good-bye costs NOTIFY.yieldMs and a silent notification.
   When no tab can sound, the notification shows without it and the settings say so. */
const NOTIFY_SAY_MS = 2000;
const notifyBus = typeof BroadcastChannel === 'function' ? new BroadcastChannel('jui-viz-notify-audio') : null;
function notifyAudioSay(bye = false, hello = false) {
  if (!notifyBus) return;
  try { notifyBus.postMessage({ tab: NOTIFY.tab, running: !bye && notifyAudioReady(), bye, hello }); } catch (err) { /* a closed channel */ }
}
if (notifyBus) {
  notifyBus.onmessage = (e) => {
    const m = e.data || {};
    if (typeof m.tab !== 'string' || m.tab === NOTIFY.tab) return;
    if (m.bye) NOTIFY.peers.delete(m.tab); else NOTIFY.peers.set(m.tab, { running: !!m.running, at: Date.now() });
    if (m.hello) notifyAudioSay();   // a new tab: it hears this one now, not a throttled timer later
    notifySettingsShow();
  };
  NOTIFY.sayTimer = setInterval(() => notifyAudioSay(), NOTIFY_SAY_MS);
  window.addEventListener('pagehide', () => notifyAudioSay(true));
  notifyAudioSay(false, true);
}
const notifyPeerCanSound = () => [...NOTIFY.peers.values()].some((p) => p.running);
// every press until the sound runs (not the first only: a context can go back to suspended)
for (const ev of ['pointerdown', 'keydown']) document.addEventListener(ev, () => { if (!notifyAudioReady()) notifyAudioWake(); }, { capture: true });
/* true: this tab rings it (the first to take the key); false: another tab (or this one) already did. */
function notifyRungTake(key) {
  let rung;
  try { rung = JSON.parse(localStorage.getItem(NOTIFY_RUNG) || '[]'); if (!Array.isArray(rung)) rung = []; } catch (err) { return true; }
  if (rung.includes(key)) return false;
  rung.push(key);
  try { localStorage.setItem(NOTIFY_RUNG, JSON.stringify(rung.slice(-300))); } catch (err) { /* the next tab may ring it too */ }
  return true;
}
function notifyEvent(kind, key, ref, body, title) {
  if (NOTIFY.seen.has(key)) return;
  NOTIFY.seen.add(key);
  if (!NOTIFY.on[kind] || !notifyGranted()) return;
  // quiet (this very thing on screen, in front): the key is taken without a ring, so a tab that comes to it later does
  // not ring it either (tabs take an event in no fixed order: one that came first may already have rung it)
  const quiet = notifyViewing(kind, ref);
  const ring = () => { if (notifyRungTake(key) && !quiet) { notifyOut(key, body, () => notifyOpen(kind, ref), title); notifyChime(kind); } };   // the sound: the same one tab
  const locked = (fn) => (navigator.locks && navigator.locks.request ? navigator.locks.request('jui-viz-notify', fn).catch(() => {}) : fn());
  locked(() => {
    // this tab cannot sound and another says it can: that one rings it; this one only if nobody has, a moment later
    if (!quiet && NOTIFY.on.chime && !notifyAudioReady() && notifyPeerCanSound()) { setTimeout(() => locked(ring), NOTIFY.yieldMs); return; }
    ring();
  });
}
/* From the live source: a turn's end, the permissions and the questions as they are now. */
const notifyServer = () => (typeof LIVE !== 'undefined' && LIVE.slices.server && LIVE.slices.server.startedAt) || 0;
function notifyStop(raw, item, replay = false) {
  if (replay) { NOTIFY.seen.add(`${notifyServer()}:done:${raw.seq}`); return; }   // sent again after a snapshot: seen, not rung
  if (!item || !DEF[item.who] || DEF[item.who].kind !== 'main' || !(Date.now() - (Number(raw.at) || 0) < 120_000)) return;
  NOTIFY.lastStop.set(item.who, Date.now());
  notifyEvent('done', `${notifyServer()}:done:${raw.seq}`, { who: item.who }, tl('panel.nt.done', { name: notifyName(item.who) }) + (raw.kind === 'StopFailure' ? tl('panel.nt.failed') : ''));
}
const NOTIFY_ASK_GRACE_MS = 1500;
NOTIFY.askFirst = new Map();
/* 入力待ち (2.3.7, ticket 2026-10-20-jui-viz-notify-waiting-for-input; requester: 「入力待ち…検知出来るなら許可とかと同じ
   ように通知鳴らして欲しい」). Claude Code sends Notification idle_prompt 60 s after a turn's end that nobody answered
   (measured by the requester 10-20 10:36: Stop 10:36:45, idle_prompt 10:37:45, "Claude is waiting for your input").
   The orchestrator's ruling: a reminder — not rung when, since that turn's end, its 完了 notification was clicked or the session was
   opened on the page (NOTIFY.opened, by openRobot and by a click on the notification); otherwise once, with the chime,
   by the same one-tab, yield and quiet rules; its own switch. A replay after a snapshot is seen, never rung. */
function notifyIdle(raw, item, replay = false) {
  const key = `${notifyServer()}:idle:${raw.seq}`;
  if (replay) { NOTIFY.seen.add(key); return; }
  if (!item || !DEF[item.who] || DEF[item.who].kind !== 'main' || !(Date.now() - (Number(raw.at) || 0) < 120_000)) return;
  const stop = NOTIFY.lastStop.get(item.who) || 0, opened = NOTIFY.opened.get(item.who) || 0;
  if (stop && opened >= stop) { NOTIFY.seen.add(key); return; }   // looked at since the turn's end: no reminder
  const name = notifyName(item.who);
  notifyEvent('idle', key, { who: item.who }, tl('panel.nt.idle', { name }), tl('panel.nt.idle.title', { name }));
}
function notifyWaiting(kind, rows) {
  const waiting = rows.filter((x) => x.status === 'pending');
  if (!NOTIFY.based[kind]) {   // the first look after loading: what already waits was there before this page
    NOTIFY.based[kind] = true;
    for (const x of waiting) NOTIFY.seen.add(`${notifyServer()}:${kind}:${x.id}`);
    return;
  }
  for (const x of waiting) {
    const key = `${notifyServer()}:${kind}:${x.id}`;
    // a question comes with two hooks in no fixed order (the async forward and --ask, ingest.py): before --ask the card
    // does not wait in viz yet, so the text would send the person to the terminal while viz waits — give --ask
    // NOTIFY_ASK_GRACE_MS from this tab's first sight (ticket 2026-10-20-jui-viz-notify-ask-says-terminal-while-viz-waits)
    if (kind === 'ask' && !x.hookWaiting && !NOTIFY.seen.has(key)) {
      const first = NOTIFY.askFirst.get(key) || Date.now();
      NOTIFY.askFirst.set(key, first);
      const left = first + NOTIFY_ASK_GRACE_MS - Date.now();
      if (left > 0) { setTimeout(() => notifyWaiting('ask', typeof QUESTIONS !== 'undefined' ? QUESTIONS : rows), left + 20); continue; }
    }
    NOTIFY.askFirst.delete(key);
    const name = notifyName(x.who);
    const body = kind === 'perm' ? tl('panel.nt.perm', { name, tool: String(x.tool || '').slice(0, 40) })
      : tl('panel.nt.ask', { name, how: x.hookWaiting ? notifyAskLeft() : tl('panel.nt.terminal') });
    notifyEvent(kind, key, { id: x.id, who: x.who, task: x.task || null }, body);
  }
}
function notifyAskLeft() {
  const s = NOTIFY.settings;
  if (!s) return tl('panel.nt.left.none');
  return s.askWaitSec > 0 ? tl('panel.nt.left', { wait: s.askWaitText }) : tl('panel.nt.left.never');
}
/* The page tells the server its question notifications are on (or no longer). */
const notifyPresenceWanted = () => SOURCE.mode === 'live' && notifyGranted() && NOTIFY.on.ask;
function notifyPresenceSay() {
  const want = notifyPresenceWanted();
  if (!want && !NOTIFY.said) return;
  NOTIFY.said = want;
  if (SOURCE.notifyPresence) SOURCE.notifyPresence(want);
}
setInterval(notifyPresenceSay, 4000);
document.addEventListener('visibilitychange', notifyPresenceSay);

/* The settings: a button in the header, a chip saying how long a question waits, a small panel. */
const notifyEl = $('notify-pop');
function notifySettingsShow(settings) {
  if (settings && typeof settings === 'object') NOTIFY.settings = settings;
  const s = NOTIFY.settings, live = SOURCE.mode === 'live';
  $('btn-notify').hidden = !live;
  const chip = $('chip-askwait');
  chip.hidden = !live || !s;
  if (s) setText(chip, s.askWaitSec > 0 ? tl('panel.ask.chip', { wait: s.askWaitText }) : tl('panel.ask.chip.never'));
  if (notifyEl.hidden) return;
  const state = !notifyCan() ? tl('panel.nt.cannot')
    : Notification.permission === 'granted' ? tl('panel.nt.granted')
      : Notification.permission === 'denied' ? tl('panel.nt.denied')
        : tl('panel.nt.default');
  setText($('notify-perm-state'), state);
  $('notify-ask-perm').hidden = !notifyCan() || Notification.permission !== 'default';
  for (const el of notifyEl.querySelectorAll('[data-notify-kind]')) el.checked = !!NOTIFY.on[el.dataset.notifyKind];
  const st = notifyAudioState(), lc = NOTIFY.lastChime;
  $('notify-volume').value = NOTIFY.volume;
  $('notify-volume').disabled = !NOTIFY.on.chime;
  setText($('notify-chime-note'), !NOTIFY.on.chime ? '' : tl('panel.chime.state', { state: tl(st === 'running' ? 'panel.chime.running' : st === 'none' ? 'panel.chime.none' : 'panel.chime.stopped'), code: st })
    + (st !== 'running' && notifyPeerCanSound() ? tl('panel.chime.peer') : '')
    + (lc ? tl('panel.chime.last', { time: new Date(lc.at).toTimeString().slice(0, 8), before: lc.before, after: lc.after, t: lc.t, played: tl(lc.played ? 'panel.chime.played' : 'panel.chime.unplayed') }) : '')
    + (lc && lc.noTab ? tl('panel.chime.notab') : ''));
  const sel = $('ask-wait');
  if (s) {
    // "until answered" is bounded by the hook's timeout (ticket 2026-10-20): the server says how long
    const most = Number(s.askUntilAnsweredSec) > 0 ? Number(s.askUntilAnsweredSec) : 0;
    const mostText = most >= 3600 ? tl('panel.ask.hours', { n: Math.round(most / 3600) }) : most >= 60 ? tl('panel.ask.min', { n: Math.round(most / 60) }) : '';
    const label = (sec) => (sec <= 0 ? (mostText ? tl('panel.ask.until.most', { most: mostText }) : tl('panel.ask.until')) : sec < 60 ? tl('panel.ask.sec', { n: sec }) : tl('panel.ask.min', { n: sec / 60 }));
    const choices = s.askWaitChoices.includes(s.askWaitSec) ? s.askWaitChoices : [...s.askWaitChoices, s.askWaitSec];
    const sig = JSON.stringify(choices);
    if (sel.dataset.sig !== sig) { sel.dataset.sig = sig; sel.innerHTML = choices.map((c) => `<option value="${esc(String(c))}">${esc(label(c))}</option>`).join(''); }
    sel.value = String(s.askWaitSec);
  }
}
function notifyOpenPanel(opener) {
  NOTIFY.opener = opener || null;
  notifyEl.hidden = false;
  $('btn-notify').setAttribute('aria-expanded', 'true');
  notifySettingsShow();
  (notifyEl.querySelector('#notify-ask-perm:not([hidden])') || notifyEl.querySelector('[data-notify-kind]')).focus({ preventScroll: true });
}
function notifyClosePanel() {
  if (notifyEl.hidden) return;
  notifyEl.hidden = true;
  $('btn-notify').setAttribute('aria-expanded', 'false');
  const back = NOTIFY.opener; NOTIFY.opener = null;
  if (back && document.contains(back)) back.focus({ preventScroll: true });
}
$('btn-notify').addEventListener('click', (e) => (notifyEl.hidden ? notifyOpenPanel(e.currentTarget) : notifyClosePanel()));
$('chip-askwait').addEventListener('click', (e) => notifyOpenPanel(e.currentTarget));
$('notify-close').addEventListener('click', notifyClosePanel);
$('notify-ask-perm').addEventListener('click', async () => {
  if (!notifyCan()) return;
  notifyAudioWake();   // the press that asks also lets the page make a sound (the chime)
  try { await Notification.requestPermission(); } catch (err) { /* refused or not asked */ }
  notifySettingsShow();
  notifyPresenceSay();
});
notifyEl.addEventListener('change', async (e) => {
  const k = e.target.closest('[data-notify-kind]');
  if (k) { NOTIFY.on[k.dataset.notifyKind] = k.checked; notifySavePrefs(); notifyPresenceSay(); notifySettingsShow(); return; }
  if (e.target.id === 'notify-volume') { if (Object.hasOwn(NOTIFY_VOLUMES, e.target.value)) NOTIFY.volume = e.target.value; notifySavePrefs(); return; }
  if (e.target.id === 'ask-wait') {
    const got = SOURCE.setAskWait ? await SOURCE.setAskWait(Number(e.target.value)) : { ok: false, why: tl('panel.ask.demo') };
    setText($('ask-wait-note'), got.ok ? tl('panel.ask.saved') : tl('panel.ask.failed', { why: got.why || '?' }));
  }
});
notifyEl.addEventListener('keydown', (e) => { if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); notifyClosePanel(); } });
document.addEventListener('pointerdown', (e) => {
  if (!notifyEl.hidden && !notifyEl.contains(e.target) && !$('btn-notify').contains(e.target) && !$('chip-askwait').contains(e.target)) notifyClosePanel();
}, true);
notifySettingsShow();
