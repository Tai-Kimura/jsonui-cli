
/* ---------- side panel ---------- */
const $ = (id) => document.getElementById(id);
const setHTML = (el, html) => { if (el._html !== html) { el.innerHTML = html; el._html = html; } };
const setText = (el, text) => { if (el && el.textContent !== text) el.textContent = text; };
const STATUS_CLASS = { idle: 'st-idle', write: 'st-write', written: 'st-idle', impl: 'st-impl', verify: 'st-verify', 'impl-done': 'st-idle', paused: 'st-paused', test: 'st-test', done: 'st-complete' };
function robotBadge(id) {
  const s = robotState[id].state;
  // a question waits for the person too, but it is no permission: its own badge and filter (requester, 10-18)
  if (s === 'waiting') return robotState[id].asking ? ['st-asking', '質問に回答待ち'] : ['st-waiting', '許可待ち'];
  if (s === 'done') return ['st-done', '完了'];
  if (s === 'idle') return ['st-idle', '待機'];
  if (s === 'thinking') return ['st-busy', '考え中'];
  if (s === 'background') return ['st-bg', '裏で作業中'];
  return ['st-busy', '作業中'];
}
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
const scopeLabel = () => (UI.project === 'all' ? 'すべて' : PROJECT[UI.project].name);
function sessionBadge(s) {
  const b = s.robots.map(robotBadge);
  // A session whose busy robots only think says 考え中, as its robot row does (they disagreed — 10-18 review).
  return b.some((x) => x[0] === 'st-waiting') ? ['st-waiting', '許可待ち'] : b.some((x) => x[0] === 'st-asking') ? ['st-asking', '質問に回答待ち'] : b.some((x) => x[1] === '作業中') ? ['st-busy', '作業中']
    : b.some((x) => x[1] === '考え中') ? ['st-busy', '考え中'] : b.some((x) => x[0] === 'st-bg') ? ['st-bg', '裏で作業中'] : ['st-idle', '待機'];
}
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
  if (fk !== undefined) { const again = el.querySelector(`[data-fk="${CSS.escape(fk)}"]`); if (again) again.focus({ preventScroll: true }); }
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
  b.textContent = sideOpen ? 'パネルを閉じる' : 'パネルを開く';
}
$('btn-side').addEventListener('click', () => { sideOpen = !sideOpen; writePref('side', sideOpen ? 'open' : 'closed'); applySide(); });
applySide();

let specFilter = readPref('specFilter', 'live');
if (!['live', 'partial', 'todo', 'done', 'all'].includes(specFilter)) specFilter = 'live';
const specFilterEl = $('spec-filter'), specListEl = $('spec-list');
specFilterEl.innerHTML = [...BUCKETS, ['all', 'すべて']].map(([b, label]) => `<button type="button" data-f="${esc(b)}" aria-pressed="${b === specFilter}">${esc(label)}<b></b></button>`).join('');
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

const COL_STATE = { doing: ['st-busy', '作業中'], wait: ['st-waiting', '待ち'], todo: ['st-idle', '未着手'], done: ['st-done', '完了'] };
const paintState = (node, [cls, label]) => { if (!node) return; const c = `state ${cls}`; if (node.className !== c) node.className = c; setText(node, label); };
const SESS_FILTERS = [['all', 'すべて'], ['active', '動いている'], ['waiting', '許可待ち'], ['asking', '質問待ち'], ['background', '裏で作業中'], ['idle', '待機']];
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
  keyed(el, JSON.stringify([UI.project, UI.sessFilter, [...UI.collapsed], groups.map(([r, l]) => [r.id, l.map((x) => x.id)])]), () => groups.map(([r, list]) => {
    const folded = UI.collapsed.has(r.id), any = scoped.some((x) => x.project === r.id);
    const itemsHTML = list.map((x) => {
      const subsHTML = x.robots.filter((id) => id !== x.id).map((id) => `<li><button type="button" class="who-btn" data-robot-open="${esc(id)}" data-fk="ss-${esc(id)}">${pill(id, DEF[id].role)}<span>${esc(DEF[id].agent)}</span></button><span class="state" data-st="${esc(id)}"></span><p class="act" data-sact="${esc(id)}"></p></li>`).join('');
      return `<li class="session"><div class="srow"><button type="button" class="who-btn" data-robot-open="${esc(x.id)}" data-fk="ss-${esc(x.id)}">${pill(x.id, 'main')}<span class="sname">${esc(DEF[x.id].agent)}</span></button><span class="state" data-sst="${esc(x.id)}"></span></div><p class="act" data-sact="${esc(x.id)}"></p>${subsHTML ? `<ul class="subs">${subsHTML}</ul>` : ''}</li>`;
    }).join('');
    return `<section class="pgroup"><button type="button" class="pg-toggle" data-fold="${esc(r.id)}" data-fk="pg-${esc(r.id)}" aria-expanded="${!folded}"><span class="pg-caret" aria-hidden="true"></span><b>${esc(r.name)}</b><small data-pgsum="${esc(r.id)}"></small></button>${folded ? '' : itemsHTML ? `<ul class="sessions">${itemsHTML}</ul>` : `<p class="empty-note">${any ? '条件に合うセッションはない' : 'セッションはない'}</p>`}</section>`;
  }).join(''));
  for (const [r] of groups) {
    const all = scoped.filter((x) => x.project === r.id), badges = all.map(sessionBadge);
    const w = badges.filter((b) => b[0] === 'st-waiting').length, ask = badges.filter((b) => b[0] === 'st-asking').length, busy = badges.filter((b) => b[0] === 'st-busy').length;
    setText(el.querySelector(`[data-pgsum="${CSS.escape(r.id)}"]`), `${all.length} セッション${w ? ` · 許可待ち ${w}` : ''}${ask ? ` · 質問待ち ${ask}` : ''}${busy ? ` · 作業中 ${busy}` : ''}`);
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
  const shown = model.specs.map((s, i) => [s, i]).filter(([s]) => inScope(s.project) && (specFilter === 'all' || s.bucket === specFilter)).sort((a, b) => roomOrder[a[0].project] - roomOrder[b[0].project] || a[1] - b[1]);
  const multi = new Set(shown.map(([x]) => x.project)).size > 1;
  keyed(specListEl, JSON.stringify([UI.project, specFilter, scopedSpecs.length, shown.map(([x, i]) => `${i}:${x.bucket}:${x.by || ''}:${x.name}`)]), () => (shown.length
    ? shown.map(([x, i], k) => `${multi && (k === 0 || shown[k - 1][0].project !== x.project) ? `<li class="sl-group">${esc(PROJECT[x.project].name)}<b>${shown.filter(([y]) => y.project === x.project).length}</b></li>` : ''}<li><button type="button" class="spec-row b-${esc(x.bucket)}" data-idx="${i}" data-fk="sp-${i}"${roleVar(x)}><span class="nm">${esc(x.name)}</span><span class="stx"></span>${x.by ? pill(x.by, DEF[x.by].role) : ''}${SEGS}</button></li>`).join('')
    : `<li class="empty-note">${!scopedSpecs.length ? `${esc(scopeLabel())} には画面の spec がない` : specFilter === 'live' ? '今は誰も spec を触っていない' : 'この状態の spec はない'}</li>`));
  specListEl.querySelectorAll('.spec-row').forEach((b) => { const s = model.specs[+b.dataset.idx]; setText(b.querySelector('.stx'), s.status.text); paintSegs(b.querySelector('.segs'), s); });

  const T = model.tests, n = CASES.length;
  const pPct = (T.passed / n) * 100, rPct = T.runningIdx >= 0 ? 100 / n : 0;
  if (SOURCE.mode === 'live' && !T.rows.length && !T.command) setHTML($('tests'), `<p class="empty-note">${T.statusText === 'まだ無い' ? 'テストの実行はまだ無い' : esc(T.statusText)}</p>`);
  else if (SOURCE.mode === 'live') setHTML($('tests'), liveTestsHTML(T));
  else if (!inScope('shop')) setHTML($('tests'), `<p class="empty-note">${esc(scopeLabel())} で動いているテストはない</p>`);
  else setHTML($('tests'), `<div class="test-head"><div>${pill('a2', 'test')} <code>${esc(T.file)}</code></div><code>${esc(T.device)} · ${esc(T.statusText)}</code>
<div class="prog" role="img" aria-label="通過 ${T.passed} 件 / 全 ${n} 件"><span class="p" style="width:${pPct}%"></span><span class="${T.retrying ? 'f' : 'r'}" style="width:${rPct}%"></span></div></div>
<ul class="cases">${T.rows.map((c, i) => {
    const icon = { pending: '○', running: '▶', passed: '✓', flaky: '⚠' }[c.status];
    const subHTML = c.status === 'running' ? `<span class="step">${c.attempt > 1 ? '1 回目は失敗 · 再実行中 · ' : ''}${esc(c.step)}</span>` : `<span class="br">分岐: ${esc(c.branch)}${c.status === 'flaky' ? ' · 1 回目は失敗、再実行で通過' : ''}</span>`;
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
  setHTML($('task-sum'), KCOLS.map(([c, label]) => `<span class="state ${COL_STATE[c][0]}">${esc(label)} ${scopedTasks.filter((x) => x.col === c).length}</span>`).join('') + (scopedPend.length ? `<span class="state st-waiting">許可待ち ${scopedPend.length}</span>` : ''));
  keyed($('tasks'), JSON.stringify([UI.project, loose.map(permSig), tasks.map((x) => `${x.key}:${x.col}:${permSig(x.perm)}:${x.subject}:${x.owner || ''}`)]), () => [
    ...loose.map((p) => `<li class="task has-perm perm-only"><button type="button" class="task-open" data-open="perm:${esc(p.id)}" data-fk="to-${esc(p.id)}"><span class="tid">${esc(SESSION_OF[p.who])} セッション</span><span class="subject">タスクの外で許可を求めている</span></button><span class="state st-waiting">許可待ち</span><span class="meta">${pill(p.who, DEF[p.who].role)} ${esc(DEF[p.who].agent)}${projectTag(SESSION_OF[p.who])}</span>${permBox(p)}</li>`),
    ...tasks.map((x) => {
      const [c, l] = x.perm ? ['st-waiting', '許可待ち'] : x.col === 'wait' ? [x.waitingFor === 'question' ? 'st-asking' : 'st-waiting', waitLabel(x)] : COL_STATE[x.col];
      return `<li class="task t-${esc(x.status)}${x.perm ? ' has-perm' : ''}${x.fresh ? ' t-new' : ''}${isTurn(x) ? ' t-turn' : ''}${x.failed ? ' t-failed' : ''}"><button type="button" class="task-open" data-open="${esc(x.key)}" data-fk="to-${esc(x.key)}"><span class="tid">${esc(x.list)} ${esc(taskRef(x))}</span><span class="subject">${x.harness ? `<span class="h-tag">${esc(x.harness)}</span>` : ''}${esc(x.subject)}</span></button><span class="state ${esc(c)}">${esc(l)}</span><span class="meta">${x.owner ? `${pill(x.owner, DEF[x.owner].role)} ${esc(DEF[x.owner].agent)}` : '担当なし'}${projectTag(x.list)}</span>${x.perm ? permBox(x.perm) : ''}</li>`;
    }),
  ].join('') || `<li class="empty-note">${esc(scopeLabel())} にタスクはない</li>`);

  const chip = $('chip-perm');
  chip.hidden = model.pending.length === 0;
  setText(chip, `許可待ち ${model.pending.length}`);
  renderQuestions();
  const sIn = SESSIONS.filter((x) => inScope(x.project)).length, rIn = ROBOT_DEFS.filter((d) => inScope(projectOfRobot(d.id))).length;
  setText($('chip-robots'), UI.project === 'all' ? `ロボット ${ROBOT_DEFS.length}` : `ロボット ${rIn} / ${ROBOT_DEFS.length}`);
  setText($('chip-sessions'), UI.project === 'all' ? `セッション ${SESSIONS.length}` : `セッション ${sIn} / ${SESSIONS.length}`);
}

/* ---------- answering permission prompts from the view ---------- */
const PERM_NOTE = 'ターミナルでも答えられ、先に答えた方が使われる';
const RELAY_HOW = '有効にするには <code>jui viz relay install</code> を 1 回、セッションを <code>claude --dangerously-load-development-channels server:jui-viz</code> で起動';
const sentWhat = (p) => `${p.sentBehavior === 'deny' ? `拒否${p.sentReason ? '・理由つき' : ''}` : p.sentRules ? `許可・ルール ${p.sentRules.length} 件を追加` : '許可'}${p.sentBy ? `・${p.sentBy === 'hook' ? 'フック' : '中継'}経由` : ''}`;
const permButtonsLive = (p, where) => (p.status === 'sent' ? `<p class="perm-sent">送信済み（${sentWhat(p)}）· Claude Code の確定を待っている</p>`
  : p.tooLongToShow ? '<p class="perm-relay">長すぎて全部を表示できないので、ターミナルで答えてください</p>'
  : !p.can.allowDeny ? `<p class="perm-relay">ターミナルで答えてください（このセッションは中継が無効）<small>${RELAY_HOW}</small></p>`
    : `<button type="button" class="pa pa-allow" data-do="allow" data-perm="${esc(p.id)}" data-fk="${esc(where)}a-${esc(p.id)}">許可</button>${p.can.always && Array.isArray(p.suggestions) && p.suggestions.length ? `<button type="button" class="pa pa-always" data-do="always" data-perm="${esc(p.id)}" data-fk="${esc(where)}w-${esc(p.id)}">今後も許可</button>` : ''}<button type="button" class="pa pa-deny" data-do="deny" data-perm="${esc(p.id)}" data-fk="${esc(where)}d-${esc(p.id)}">拒否</button>`);
const permButtons = (p, where) => (SOURCE.mode === 'live' ? permButtonsLive(p, where) : permButtonsDemo(p, where));
const permButtonsDemo = (p, where) => `<button type="button" class="pa pa-allow" data-do="allow" data-perm="${esc(p.id)}" data-fk="${esc(where)}a-${esc(p.id)}">許可</button><button type="button" class="pa pa-always" data-do="always" data-perm="${esc(p.id)}" data-fk="${esc(where)}w-${esc(p.id)}" title="${esc(p.rule)} を今後は聞かずに許可する">今後も許可</button><button type="button" class="pa pa-deny" data-do="deny" data-perm="${esc(p.id)}" data-fk="${esc(where)}d-${esc(p.id)}">拒否</button>`;
/* What a live card asks about: card.exact verbatim — whitespace and line breaks as they are (pre-wrap), the whole
   command however long (the box scrolls) — never the summary or the clipped preview. A relay request the server
   could not pair with a hook has no exact: its preview is shown as what it is. The demo keeps its one-line code. */
const EXACT_LABEL = { command: '', file_path: 'ファイル', notebook_path: 'ノートブック', url: 'URL', pattern: 'パターン', old_string: '置き換え前', new_string: '置き換え後', content: '書き込む中身' };
function permSubjectLive(p) {
  const e = p.exact;
  if (!e) {
    return p.preview
      ? `<span class="perm-exact" tabindex="0"><span class="pe-k">Claude Code が中継で送った内容（全体とは限らない）</span>${esc(p.preview)}</span>`
      : `<code>${esc(permSummary(p))}</code>`;
  }
  const partsHTML = Object.keys(EXACT_LABEL).filter((k) => typeof e[k] === 'string').map((k) => (EXACT_LABEL[k] ? `<span class="pe-k">${EXACT_LABEL[k]}</span>` : '') + `<span class="pe-v">${esc(e[k])}</span>`);
  if (e.contentTruncated) partsHTML.push(`<span class="pe-note">中身は先頭 ${[...(e.content || '')].length} 字だけ表示（全体 ${Number(e.contentTruncated)} 字）</span>`);
  return `<span class="perm-exact" tabindex="0">${partsHTML.join('')}</span>`;
}
const permSubject = (p) => (SOURCE.mode === 'live' ? permSubjectLive(p) : `<code>${esc(permSummary(p))}</code>`);
const permBox = (p) => `<div class="perm-box"><p class="perm-q"><b>${esc(p.tool)}</b> ${permSubject(p)}</p><div class="perm-acts">${permButtons(p, 's')}</div></div>`;
function recentHTML(id) {
  const items = logItems.filter((e) => e.who === id).slice(0, 6);
  return items.length ? items.map((e) => `<li><time>${fmtClock(BASE_CLOCK + e.abs)}</time><span><b>${esc(e.kind)}</b> ${esc(e.what)}</span></li>`).join('') : '<li><span>まだ記録がない</span></li>';
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
  const reasonEl = $('tbd-reason') || $('rb-reason');
  const reason = behavior === 'deny' && reasonEl && where && where.contains(reasonEl) ? reasonEl.value.trim() : '';
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
  else if (t.dataset.robotOpen) openRobot(t.dataset.robotOpen, t);
  else if (t.dataset.specOpen !== undefined) openWhiteboard(Number(t.dataset.specOpen), t);
  else if (t.dataset.logRobot) openLogFor(t.dataset.logRobot, t);
  else if (t.hasAttribute('data-close-detail')) closeTaskDetail();
  else if (t.hasAttribute('data-reset-rules')) { alwaysRules.clear(); showToast('このデモで足した常時許可を取り消した'); refreshNow(); }
  else if (t.hasAttribute('data-rb-close')) closeRobot();
  else if (t.hasAttribute('data-set-all')) setProject('all');
});
$('chip-perm').addEventListener('click', (e) => openTaskBoard(e.currentTarget));

/* ---------- scope: which project (or all) every panel and board shows, and which sessions ---------- */
function paintScopeButtons() {
  document.querySelectorAll('[data-scope-btn]').forEach((b) => setHTML(b, `<span class="sb-k">プロジェクト</span><b>${esc(scopeLabel())}</b><span class="sb-caret" aria-hidden="true"></span>`));
  const scoped = SESSIONS.filter((s) => inScope(s.project));
  const shown = scoped.filter((s) => !UI.hiddenLists.has(s.id));
  setHTML($('tb-sess'), `<span class="sb-k">セッション</span><b>${shown.length === scoped.length ? `すべて（${scoped.length}）` : shown.length === 1 ? esc(shown[0].id) : `${shown.length} / ${scoped.length}`}</b><span class="sb-caret" aria-hidden="true"></span>`);
  const robotsIn = ROBOT_DEFS.filter((d) => inScope(projectOfRobot(d.id)));
  const shownR = robotsIn.filter((d) => !logState.hiddenRobots.has(d.id));
  setHTML($('log-who'), `<span class="sb-k">ロボット</span><b>${shownR.length === robotsIn.length ? `すべて（${robotsIn.length}）` : shownR.length === 1 ? esc(shownR[0].id) : `${shownR.length} / ${robotsIn.length}`}</b><span class="sb-caret" aria-hidden="true"></span>`);
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
function setProject(id, { camera: moveCamera = true } = {}) {
  if (!(id === 'all' || PROJECT[id]) || UI.project === id) return;
  UI.project = id; writePref('project', id);
  if (wb.open && wb.idx >= 0 && !inScope(SPECS[wb.idx].project)) wb.idx = -1;
  if (tb.detail && !tb.detail.startsWith('perm:') && !inScope(PROJECT_OF[tb.detail.split('#')[0]])) tb.detail = null;
  if (SOURCE.mode === 'live' && has3D) liveShowFloorOf(id);   // a room on another floor: go there first
  if (SOURCE.mode === 'live') liveRelayout();                // one room at a time: the room picked, wider (or the floor again)
  if (moveCamera) focusProject(id);
  paintScopeButtons();
  refreshNow();
  if (wb.open) { wbCode.scrollTop = 0; renderWhiteboard(latestModel, true); }
  // A zoomed board view moves to the board of the project now shown.
  if (has3D && zoom.zoomed && !camTween && (wb.open || tb.open)) { const pose = wb.open ? specPose(wb.idx) : taskPose(); camera.position.copy(pose.p); viewTarget.copy(pose.t); }
  showToast(id === 'all' ? 'すべてのプロジェクトを表示' : `${PROJECT[id].name} だけを表示`);
}

/* ---------- questions (AskUserQuestion, requester 10-18): single and multiple choice, a free answer per question ----------
   A card shows every question, header, option, description and preview as text (escaped). It can be answered only
   while a hook waits for it (forward.py --ask) and only when everything fits on it; every question needs an answer
   before it can be sent. Options are named by their index, never by their label, in the markup. */
const Q_SHOW_MS = 30_000;   // an answered card stays a moment, saying who answered and what
const qState = (q) => (q.status === 'sent' ? '送信済み · Claude Code の確定を待っている'
  : q.status === 'answered' ? 'ブラウザの答えが届いた' : q.status === 'answered_in_terminal' ? 'ターミナルで答えた'
    : q.status === 'expired' ? '答えないまま終わった' : '');
/* Why a pending card cannot be answered here. It goes at the top, above choices drawn as not pickable: at the
   bottom, under radios that looked live, the requester clicked them and nothing happened (10-18). */
const qWhy = (q) => (q.tooLongToShow ? '質問の全部をここに表示できないため、ここでは答えられません'
  : q.released ? 'ターミナルに返しました' : q.waitEnded ? 'ブラウザで答えられる時間が過ぎました（だれも操作しないまま待ちが終わった）'
    : 'このセッションは答えの中継を待っていません');
function questionHTML(q) {
  const open = q.status === 'pending' && q.hookWaiting && !q.tooLongToShow;
  const closed = q.status === 'pending' && !open;
  const got = q.sentAnswers || q.gotAnswers || null;
  const itemsHTML = q.questions.map((x, i) => {
    const type = x.multiSelect ? 'checkbox' : 'radio', name = `qa-${q.id}-${i}`;
    const optsHTML = x.options.map((o, k) => `<label class="qopt"><input type="${esc(type)}" name="${esc(name)}" data-qi="${i}" data-qk="${k}"${open ? '' : ' disabled'}><span class="qlabel">${esc(o.label)}</span>${o.description ? `<span class="qdesc">${esc(o.description)}</span>` : ''}${o.preview ? `<pre class="qprev">${esc(o.preview)}</pre>` : ''}</label>`).join('');
    const otherHTML = `<label class="qopt qother"><input type="${esc(type)}" name="${esc(name)}" data-qi="${i}" data-qk="other"${open ? '' : ' disabled'}><span class="qlabel">その他（自由記述）</span><input type="text" class="qother-text" data-qi="${i}" aria-label="${esc(x.question)} への自由記述" maxlength="2000"${open ? '' : ' disabled'}></label>`;
    const answeredHTML = got && got[x.question] !== undefined ? `<p class="qgot">答え: <b>${esc(got[x.question])}</b></p>` : '';
    // answered or over: the question and its answer only
    const choicesHTML = q.status === 'pending' ? `${optsHTML}${otherHTML}` : '';
    return `<fieldset class="qq"><legend>${x.header ? `<span class="qhead">${esc(x.header)}</span>` : ''}<span class="qtext">${esc(x.question)}</span>${x.multiSelect ? '<span class="qmulti">複数選べる</span>' : ''}</legend>${choicesHTML}${answeredHTML}</fieldset>`;
  }).join('');
  // While the hook waits the terminal shows no question (measured 10-18): the time left, and the way to the terminal.
  const footHTML = open ? `<div class="qfoot"><button type="button" class="pa pa-allow" data-qsend="${esc(q.id)}" data-fk="qs-${esc(q.id)}" disabled>答えを送る</button><button type="button" class="pa pa-deny" data-qrelease="${esc(q.id)}" data-fk="qr-${esc(q.id)}">ターミナルで答える</button></div><p class="qnote">待っている間はターミナルに質問が出ない · <span data-quntil="${esc(q.id)}"></span>（操作すると延びる）</p>`
    : closed ? '' : `<p class="qnote qdone">${esc(qState(q))}</p>`;
  const whyHTML = closed ? `<p class="qnote qwhy" role="note">${esc(qWhy(q))}。ターミナルで答えてください（ここでは選べません）</p>` : '';
  return `<article class="qcard${open ? ' q-open' : ''}${closed ? ' q-closed' : ''}" data-qcard="${esc(q.id)}"><header class="qwho">${pill(q.who, DEF[q.who].role)}<span>${esc(DEF[q.who].agent)}</span><span class="pc-wait" data-since="${q.at}"></span></header>${whyHTML}${itemsHTML}${footHTML}</article>`;
}
function renderQuestions() {
  const now = Date.now();
  const shown = QUESTIONS.filter((q) => inScope(projectOfRobot(q.who)) && (q.status === 'pending' || q.status === 'sent' || now - (q.doneAt || 0) < Q_SHOW_MS));
  const waiting = QUESTIONS.filter((q) => q.status === 'pending').length;
  const chip = $('chip-ask');
  chip.hidden = waiting === 0;
  setText(chip, `質問 ${waiting}`);
  $('questions-sec').hidden = shown.length === 0;
  keyed($('questions'), JSON.stringify(shown.map((q) => [q.id, q.status, q.hookWaiting, q.tooLongToShow, q.waitEnded, q.released, q.sentAnswers, q.gotAnswers])), () => shown.map((q) => questionHTML(q)).join(''));
  for (const el of $('questions').querySelectorAll('[data-quntil]')) {   // the countdown, in place (inputs keep their state)
    const q = QUESTIONS.find((x) => x.id === el.dataset.quntil);
    setText(el, q && q.waitUntil ? `あと ${Math.max(0, Math.ceil((q.waitUntil - now) / 1000))} 秒でターミナルに戻す` : '');
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
$('questions').addEventListener('input', (e) => {
  const card = e.target.closest('[data-qcard]');
  const q = card && QUESTIONS.find((x) => x.id === card.dataset.qcard);
  if (!q) return;
  // typing a free answer picks その他
  if (e.target.classList.contains('qother-text') && e.target.value) { const box = e.target.parentElement.querySelector('input[data-qk="other"]'); if (box) box.checked = true; }
  const send = card.querySelector('[data-qsend]');
  if (send) send.disabled = !questionPicks(card, q).complete;
  if (send) holdQuestion(q.id);   // someone is answering: the hook waits a little longer
});
$('questions').addEventListener('click', (e) => {
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
});
$('chip-ask').addEventListener('click', () => { const sec = $('questions-sec'); sec.scrollIntoView({ block: 'start' }); const first = sec.querySelector('input:not([disabled])'); if (first) first.focus({ preventScroll: true }); });

/* ---------- popovers: project switcher, session picker, robot picker ---------- */
const popEl = $('pop');
const pop = { anchor: null, kind: null, q: '' };
function openPop(anchor, kind) {
  if (pop.anchor === anchor && !popEl.hidden) { closePop(); return; }
  if (pop.anchor) pop.anchor.setAttribute('aria-expanded', 'false');
  pop.anchor = anchor; pop.kind = kind; pop.q = '';
  const titles = { project: 'プロジェクトで絞り込む', lists: 'セッションで絞り込む', robots: 'ロボットで絞り込む' };
  popEl.setAttribute('aria-label', titles[kind]);
  popEl.innerHTML = `<p class="pop-title">${titles[kind]}<small data-pop-count></small></p>${kind === 'project' && ROOMS.length <= 6 ? '' : `<input type="search" class="pop-search" placeholder="${kind === 'project' ? '名前で探す' : 'ID・フォルダ・役割で探す'}" aria-label="${titles[kind]}（検索）">`}${kind === 'project' ? '' : `<div class="pop-quick" role="group" aria-label="まとめて選ぶ"><button type="button" data-quick="all">すべて</button><button type="button" data-quick="active">動いているだけ</button><button type="button" data-quick="waiting">許可待ちだけ</button><button type="button" data-quick="none">全部外す</button></div>`}<div class="pop-body"></div>`;
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
    body.innerHTML = `<ul class="pop-list" role="listbox" aria-label="プロジェクト">${ids.map((id) => {
      const st = projectStats(latestModel, id), sel = UI.project === id;
      return `<li role="option" tabindex="${sel ? 0 : -1}" aria-selected="${sel ? 'true' : 'false'}" data-pick-project="${esc(id)}" data-fk="pp-${esc(id)}"><span class="po-main"><b>${id === 'all' ? 'すべてのプロジェクト' : esc(PROJECT[id].name)}</b><small>${id === 'all' ? `${ROOMS.length} プロジェクト` : esc(PROJECT[id].path)} · ${st.sessions} セッション</small></span><span class="po-badges">${st.pend ? `<span class="state st-waiting">許可待ち ${st.pend}</span>` : ''}${st.busy ? `<span class="state st-busy">作業中 ${st.busy} 体</span>` : ''}${st.live ? `<span class="state st-write">作業中の spec ${st.live}</span>` : ''}</span></li>`;
    }).join('')}</ul>`;
  } else {
    const isLog = pop.kind === 'robots';
    const hidden = isLog ? logState.hiddenRobots : UI.hiddenLists;
    const sess = SESSIONS.filter((s) => inScope(s.project));
    const groups = ROOMS.filter((r) => inScope(r.id)).map((r) => [r, sess.filter((s) => s.project === r.id && matchQ(`${s.id} ${s.room} ${s.robots.map((id) => `${id} ${DEF[id].agent}`).join(' ')} ${sessionBadge(s)[1]}`))]).filter(([, l]) => l.length);
    const rowHTML = (s) => {
      const [c, l] = sessionBadge(s), n = latestModel.tasks.filter((x) => x.list === s.id).length;
      if (!isLog) return `<label class="pg-item"><input type="checkbox" data-pick-list="${esc(s.id)}" data-fk="pl-${esc(s.id)}"${hidden.has(s.id) ? '' : ' checked'}>${pill(s.id, 'main')}<span class="pg-name">${esc(DEF[s.id].agent)}<small>${n} タスク</small></span><span class="state ${esc(c)}">${esc(l)}</span></label>`;
      const on = s.robots.filter((id) => !hidden.has(id)).length;
      const subsHTML = s.robots.filter((id) => id !== s.id).map((id) => `<label class="pg-item pg-sub"><input type="checkbox" data-pick-robot="${esc(id)}" data-fk="pr-${esc(id)}"${hidden.has(id) ? '' : ' checked'}>${pill(id, DEF[id].role)}<span class="pg-name">${esc(DEF[id].agent)}</span><span class="state ${esc(robotBadge(id)[0])}">${esc(robotBadge(id)[1])}</span></label>`).join('');
      return `<label class="pg-item"><input type="checkbox" data-pick-session="${esc(s.id)}" data-fk="ps-${esc(s.id)}"${on === s.robots.length ? ' checked' : ''}${on > 0 && on < s.robots.length ? ' data-mixed' : ''}>${pill(s.id, 'main')}<span class="pg-name">${esc(DEF[s.id].agent)}<small>ロボット ${s.robots.length}</small></span><span class="state ${esc(c)}">${esc(l)}</span></label>${subsHTML}`;
    };
    body.innerHTML = `<div class="pop-groups">${groups.map(([r, list]) => `<p class="pg-label">${esc(r.name)}</p>${list.map(rowHTML).join('')}`).join('') || '<p class="pop-none">該当するセッションがない</p>'}</div>`;
    body.querySelectorAll('[data-mixed]').forEach((x) => { x.indeterminate = true; });
    const total = isLog ? ROBOT_DEFS.filter((d) => inScope(projectOfRobot(d.id))).length : sess.length;
    const shown = isLog ? ROBOT_DEFS.filter((d) => inScope(projectOfRobot(d.id)) && !hidden.has(d.id)).length : sess.filter((s) => !hidden.has(s.id)).length;
    setText(popEl.querySelector('[data-pop-count]'), `${shown} / ${total} を表示`);
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
const zoom = { zoomed: false, returnPose: null, opener: null };
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
function zoomBack() {
  if (has3D && zoom.returnPose) {
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
const wb = { open: false, idx: -1, lastActive: null, q: '', app: 'all' };
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
const appLabel = (app) => app || '直下';
let wbSideOpen = readPref('wbSide', 'open') === 'open';
const narrowWb = () => sceneEl.clientWidth < 800;
function applyWbSide() {
  wbBody.classList.toggle('side-closed', !wbSideOpen);
  const b = $('wb-side-btn');
  b.setAttribute('aria-expanded', String(wbSideOpen));
  b.textContent = wbSideOpen ? '一覧を閉じる' : 'spec 一覧';
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
  if (tb.open) { tb.open = false; tb.detail = null; hideOverlay(tbEl); }
  if (rbState.id) closeRobot(true);
  if (i >= 0 && !inScope(SPECS[i].project)) setProject(SPECS[i].project, { camera: false });
  if (i >= 0 && !inApp(SPECS[i])) wb.app = 'all';
  wb.idx = i; wb.lastActive = null; wb.board = board || null;
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
  if (!wb.open) return;
  wb.open = false;
  hideOverlay(wbEl);
  zoomBack();
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
  const groups = BUCKETS.map(([b, label]) => [label, model.specs.map((s, i) => [s, i]).filter(([s]) => s.bucket === b && match(s))]).filter(([, items]) => items.length);
  const n = model.specs.filter((s) => inScope(s.project) && inApp(s)).length;
  keyed(wbSideList, JSON.stringify([UI.project, q, wb.idx, wb.app, apps, groups.map(([label, items]) => [label, items.map(([s, i]) => `${i}:${s.by || ''}:${s.name}`)])]), () => {
    const total = apps.reduce((k, [, c]) => k + c, 0);
    const appsHTML = apps.length > 1 ? `<div class="seg-filter ws-apps" role="group" aria-label="アプリで絞り込む">${[['all', total], ...apps].map(([a, c]) => `<button type="button" data-app="${esc(a)}" aria-pressed="${wb.app === a}">${esc(a === 'all' ? '全体' : appLabel(a))}<b>${esc(String(c))}</b></button>`).join('')}</div>` : '';
    const allHTML = appsHTML + `<button type="button" class="ws-item ws-all" data-idx="-1" data-fk="ws--1" aria-current="${wb.idx === -1}"><span class="dot" aria-hidden="true"></span><span class="nm">全体を見る</span><span></span><small>${esc(scopeLabel())} · ${n} 画面の進み具合</small></button>`;
    const bodyHTML = groups.map(([label, items]) => `<p class="ws-group"><span>${esc(label)}</span><b>${items.length}</b></p>${items.map(([s, i]) => `<button type="button" class="ws-item b-${esc(s.bucket)}" data-idx="${i}" data-fk="ws-${i}" aria-current="${wb.idx === i}"${roleVar(s)}><span class="dot" aria-hidden="true"></span><span class="nm">${esc(s.name)}</span>${s.by ? pill(s.by, DEF[s.by].role) : '<span></span>'}<small></small></button>`).join('')}`).join('');
    return allHTML + (bodyHTML || '<p class="ws-none">該当する画面がない</p>');
  });
  wbSideList.querySelectorAll('.ws-item:not(.ws-all)').forEach((b) => { const x = model.specs[+b.dataset.idx]; setText(b.lastElementChild, UI.project === 'all' ? `${PROJECT[x.project].name} · ${x.status.text}` : x.status.text); });
}

const SWATCHES = '<span><i class="sw sw-writing"></i>書き込み中</span><span><i class="sw sw-written"></i>記入済み</span><span><i class="sw sw-impl"></i>実装済み</span><span><i class="sw sw-tested"></i>テスト済み</span><span><i class="sw sw-empty"></i>未記入</span>';
const OV_LEGEND = `${SWATCHES}<span>バーは左から 概要・構造・状態・データ・操作・遷移・分岐</span><span>カードを押すとその spec を開く</span>`;
const SHEET_LEGEND_LIVE = '<span class="lg-writing">✎ 紫の枠 = 書き込み中</span><span class="lg-empty">点線 = 未記入</span><span><b class="m-done">✓</b> 構造: layout に在る ／ 分岐: テスト通過</span><span><b class="m-todo">○</b> 構造: layout が無い ／ 分岐: 未テスト</span><span><b class="m-test">▶</b> テスト中</span><span>状態・データ・操作・遷移は項目ごとの実装を測れないので印なし（関連ファイルの節に、在るファイルの数）</span>';
const SHEET_LEGEND = '<span class="lg-writing">✎ 紫の枠 = 書き込み中</span><span class="lg-empty">点線 = 未記入</span><span><b class="m-done">✓</b> 実装済み・テスト済み</span><span><b class="m-doing">●</b> 実装中</span><span><b class="m-todo">○</b> 未実装・未テスト</span><span><b class="m-test">▶</b> テスト中</span><span><b class="m-flaky">⚠</b> 再実行で通過</span><span>中身はデモの例</span>';
function setHead(title, file, stCls, stText, whoHTML) {
  setText($('wb-title'), title);
  setText($('wb-file'), file);
  const st = $('wb-status'), cls = `state ${stCls}`;
  if (st.className !== cls) st.className = cls;
  setText(st, stText);
  setHTML($('wb-who'), whoHTML);
}
function specSummary(s) {
  if (s.bucket === 'todo') return 'spec ファイルなし';
  const w = s.written.reduce((a, b) => a + b, 0) / 7;
  if (s.measure) {
    const m = s.measure, layout = m.layout === null ? 'layout —' : m.layout ? 'layout あり' : 'layout なし';
    return `記述 ${pct(w)}% · ${layout} · 関連ファイル ${m.related.done}/${m.related.total} · テスト ${s.implN[6]}/${s.totals[6]}`;
  }
  return `記述 ${pct(w)}% · 実装 ${s.implPhase ? `${sumImpl(s.implN)}/${sumImpl(s.totals)}` : '—'} · テスト ${s.implPhase ? `${s.implN[6]}/${s.totals[6]}` : '—'}`;
}
function renderOverview(model) {
  const apps = wbApps(model), inS = model.specs.filter((s) => inScope(s.project) && inApp(s)), c = bucketCounts(inS);
  const dirs = [...new Set(inS.map((s) => s.specDir).filter(Boolean))];
  const where = dirs.length > 1 ? `${dirs.length} か所の spec フォルダ` : `${dirs[0] || 'docs/screens/json'}/`;
  const title = `spec ボード${UI.project === 'all' ? '' : ` · ${PROJECT[UI.project].name}`}${wb.app !== 'all' && apps.length > 1 ? ` · ${appLabel(wb.app)}` : ''}`;
  setHead(title, `${where}（${inS.length} 画面）`, 'st-busy', `作業中 ${c.live} · 途中 ${c.partial} · 未着手 ${c.todo} · 完了 ${c.done}`, '');
  wbNav.hidden = true; $('wb-follow-label').hidden = true;
  setHTML($('wb-legend'), OV_LEGEND);
  const sig = JSON.stringify(['ov', UI.project, wb.app, model.specs.map((s) => `${s.bucket}:${s.by || ''}`)]);
  if (wbCode._sig !== sig) {
    wbCode.innerHTML = !inS.length ? `<p class="sc-ph ov-none">${esc(scopeLabel())} には画面の spec がない（CLI ツールなど）。上の「プロジェクト」で別のプロジェクトを選べる</p>` : BUCKETS.map(([b, label]) => {
      const items = model.specs.map((s, i) => [s, i]).filter(([s]) => s.bucket === b && inScope(s.project) && inApp(s));
      if (!items.length) return '';
      return `<section class="ov-group" aria-label="${esc(label)}"><h3>${esc(label)}<small>${items.length}</small></h3><div class="ov-grid">${items.map(([s, i]) => `<button type="button" class="ov-card b-${esc(s.bucket)}" data-idx="${i}"${roleVar(s)}><span class="ov-top"><strong>${esc(s.name)}</strong><span class="state"></span></span><code class="ov-file">${UI.project === 'all' ? `${esc(PROJECT[s.project].name)} · ` : ''}${esc(s.file)}</code><span class="ov-who"></span><span class="ov-secs">${SEGS}<span class="ov-labels" aria-hidden="true">${SECTIONS.map((x) => `<span>${esc(x)}</span>`).join('')}</span></span><span class="ov-sum"></span></button>`).join('')}</div></section>`;
    }).join('');
    wbCode._sig = sig; wbCode._html = null;
  }
  wbCode.querySelectorAll('.ov-card').forEach((card) => {
    const s = model.specs[+card.dataset.idx], st = card.querySelector('.state'), cls = `state ${STATUS_CLASS[s.status.kind]}`;
    if (st.className !== cls) st.className = cls;
    setText(st, s.status.text);
    setHTML(card.querySelector('.ov-who'), s.by ? `${pill(s.by, DEF[s.by].role)}<span>${esc(robotState[s.by].act)}</span>` : `<span>${esc(s.note)}</span>`);
    paintSegs(card.querySelector('.segs'), s);
    setText(card.querySelector('.ov-sum'), specSummary(s));
  });
}

const TYPE_JA = { View: 'コンテナ', SafeAreaView: '画面枠', ScrollView: 'スクロール', Label: 'テキスト', TextField: '入力欄', TextView: '複数行入力', Button: 'ボタン', Image: '画像', NetworkImage: '画像', Collection: '一覧', Indicator: '読み込み', Segment: '切り替え', SelectBox: '選択', CheckBox: 'チェック', Switch: 'スイッチ', TabView: 'タブ' };
const PLATFORM_JA = { ios: 'iOS', android: 'Android', web: 'Web' };
const CHIP = { empty: 'c-empty', writing: 'c-writing', written: '', impl: 'c-impl', done: 'c-done', test: 'c-test', tested: 'c-done' };
// A section with nothing implemented or tested yet stays plain; colour marks progress.
const chipCls = (g) => ((g.kind === 'impl' || g.kind === 'test') && g.f === 0 ? '' : CHIP[g.kind]);
/* [section, card title, key in the spec file, full width] */
const SHEET = [[0, '概要', 'metadata', true], [1, '構造（部品と並び）', 'structure', true], [2, '状態', 'stateManagement', false], [3, 'データの流れ', 'dataFlow', false], [4, '操作', 'userActions', false], [5, '遷移', 'transitions', false], [6, '分岐（テストで確かめる条件）', 'branchContracts', true], [7, '関連ファイル', 'relatedFiles', true]];
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
function wfElement([type, id, desc], state) {
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
  return `<div class="wf s-${esc(state)}"><span class="wf-id">${esc(id)}</span>${shapeHTML}</div>`;
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
      setHead(s.name, s.file, STATUS_CLASS[s.status.kind], s.status.text, s.by ? pill(s.by, DEF[s.by].role) : '');
      wbNav.hidden = false; $('wb-follow-label').hidden = false;
      setHTML($('wb-legend'), SHEET_LEGEND_LIVE);
      renderNav(s);
      const failed = LIVE.sheetFailed[s.id];
      setHTML(wbCode, `<p class="sc-ph">${failed ? `この spec を読めなかった（${esc(failed)}）` : 'spec を読み込んでいます…'}</p>`);
      wbCode._sig = null;
      return;
    }
  }
  if (SOURCE.mode === 'live') setHead(s.name, s.file, STATUS_CLASS[s.status.kind], s.status.text, s.by ? pill(s.by, DEF[s.by].role) : '');
  else setHead(`${s.name}（${s.screen}）`, `docs/screens/json/${s.file}`, STATUS_CLASS[s.status.kind], s.status.text, s.by ? pill(s.by, DEF[s.by].role) : '');
  wbNav.hidden = false; $('wb-follow-label').hidden = false;
  setHTML($('wb-legend'), SOURCE.mode === 'live' ? SHEET_LEGEND_LIVE : SHEET_LEGEND);
  renderNav(s);
  if (wbCode._sig) { wbCode._sig = null; wbCode._html = null; }

  let activeKey = null;
  const actAttr = (cls, key) => ((cls === 'is-doing' || cls === 'is-testing') && activeKey === null ? (activeKey = key, ' data-act') : '');
  const li = (m, key, innerHTML) => `<li class="rw ${esc(m[2])}"${actAttr(m[2], key)}><span class="mk ${esc(m[1])}">${esc(m[0])}</span><span>${innerHTML}</span></li>`;
  const tr = (m, key, cellsHTML) => `<tr class="${esc(m[2])}"${actAttr(m[2], key)}><td class="mk ${esc(m[1])}">${esc(m[0])}</td>${cellsHTML}</tr>`;
  // The first n items of a section; while it is being written the newest one is highlighted instead of marked.
  const pick = (k, arr, n, fresh) => arr.slice(0, n).map((x, i) => [x, i, fresh ? ['', '', i === n - 1 ? 'is-new' : ''] : markOf(s, model, k, i)]);
  const bodies = [
    (w) => {
      const m = d.metadata;
      const rows = [['画面名', `${esc(m.displayName)}（<span class="mono">${esc(m.name)}</span>）`], ['説明', esc(m.description)], ['対応', m.platforms.map((p) => `<span class="bdg">${PLATFORM_JA[p] || esc(p)}</span>`).join(' ')], ['レイアウト', m.layoutFile ? `<code>docs/screens/layouts/${esc(m.layoutFile)}.json</code>` : ''], ['作成日', esc(m.createdAt)]].filter(([, v]) => v !== '');
      return `<dl class="kv">${rows.slice(0, reveal(rows.length, w)).map(([a, bHTML]) => `<dt>${esc(a)}</dt><dd>${bHTML}</dd>`).join('')}</dl>`;
    },
    (w, writing) => {
      const COMP_MAX = 60, compAll = reveal(d.components.length, w);
      const items = pick(1, d.components, Math.min(COMP_MAX, compAll), writing);
      const moreHTML = compAll > COMP_MAX ? `<p class="sc-note">ほか ${compAll - COMP_MAX} 個の部品（Layout が大きいので先頭の ${COMP_MAX} 個だけ）</p>` : '';
      const rowsHTML = items.map(([[type, id, desc], i, m]) => li(m, `c${i}`, `<span class="tp">${esc(TYPE_JA[type] || type)}</span> <span class="id">${esc(id)}</span> <span class="desc">${esc(desc)}</span>`)).join('');
      const byId = new Map(items.map((x) => [x[0][1], x]));
      const wfHTML = d.layoutChildren.filter((id) => byId.has(id)).map((id) => {
        const [c, , m] = byId.get(id);
        const state = writing ? (m[2] === 'is-new' ? 'writing' : 'defined') : !s.implPhase ? 'defined' : m[1] === 'm-done' ? 'done' : m[1] === 'm-doing' ? 'doing' : 'todo';
        return wfElement(c, state);
      }).join('');
      return `<div class="st-grid"><div class="wf-phone" role="img" aria-label="${esc((d.components[0] || [])[1] || '')} の中に並ぶ部品の配置図">${wfHTML}</div><ul class="rows">${rowsHTML}</ul></div>${moreHTML}`;
    },
    (w, writing) => {
      const rowsHTML = pick(2, d.uiVariables, reveal(d.uiVariables.length, w), writing).map(([[name, type, init], i, m]) => tr(m, `v${i}`, `<td class="mono">${esc(name)}</td><td class="mono">${esc(type)}</td><td class="mono">${esc(init)}</td>`)).join('');
      const evHTML = !writing || w >= 0.6 ? `<p class="sub-h">イベント</p><ul class="rows">${d.eventHandlers.map(([name, desc]) => `<li class="rw"><span class="mk"></span><span><span class="id">${esc(name)}</span> <span class="desc">${esc(desc)}</span></span></li>`).join('')}</ul>` : '';
      return `<table class="vt"><thead><tr><th><span class="sr">状態</span></th><th>変数</th><th>型</th><th>初期値</th></tr></thead><tbody>${rowsHTML}</tbody></table>${evHTML}`;
    },
    (w, writing) => {
      const M = d.vmMethods.length, shown = writing ? reveal(M + 2 + d.apis.length, w) : M + 2 + d.apis.length;
      const methodsHTML = pick(3, d.vmMethods, Math.min(shown, M), writing && shown <= M).map(([name, i, m]) => li(m, `m${i}`, `<span class="id">${esc(name)}</span>`)).join('');
      const varsHTML = shown > M ? `<p class="fb-vars">持つ値: ${d.vmVars.map((v) => `<code>${esc(v)}</code>`).join(' ')}</p>` : '';
      const reposHTML = shown > M + 1 ? `<div class="farrow" aria-hidden="true">↓</div><div class="fbox"><p class="fb-h">Repository</p><p>${d.repositories.map((r) => `<span class="bdg">${esc(r)}</span>`).join(' ')}</p></div>` : '';
      const apiN = Math.max(0, shown - M - 2);
      let apisHTML = '';
      if (shown > M + 1 && !d.apis.length) apisHTML = '<div class="farrow" aria-hidden="true">↓</div><div class="fbox"><p class="fb-h">API</p><p class="sc-ph">通信しない</p></div>';
      else if (apiN > 0) apisHTML = `<div class="farrow" aria-hidden="true">↓</div><div class="fbox"><p class="fb-h">API</p><ul class="rows">${d.apis.slice(0, apiN).map(([op, method, path]) => `<li class="api"><span class="http http-${esc(method)}">${esc(method)}</span><code>${esc(path)}</code><span class="desc">${esc(op)}</span></li>`).join('')}</ul></div>`;
      return `<div class="flow"><div class="fbox"><p class="fb-h">ViewModel</p><ul class="rows">${methodsHTML}</ul>${varsHTML}</div>${reposHTML}${apisHTML}</div>`;
    },
    (w, writing) => `<ul class="rows">${pick(4, d.userActions, reveal(d.userActions.length, w), writing).map(([[a, p], i, m]) => li(m, `a${i}`, `${esc(a)}<span class="to">→</span><code>${esc(p)}</code>`)).join('')}</ul>`,
    (w, writing) => `<ul class="rows">${pick(5, d.transitions, reveal(d.transitions.length, w), writing).map(([[trig, dest], i, m]) => li(m, `t${i}`, `${esc(trig)}<span class="to">→</span><span class="scr" title="${esc(dest)}">${esc(SCREEN_JA[dest] || dest)}</span>`)).join('')}</ul>`,
    (w, writing) => {
      const rowsHTML = pick(6, d.branches, reveal(d.branches.length, w), writing).map(([[method, when, then], i, m]) => tr(m, `b${i}`, `<td class="mono">${esc(method)}</td><td>${esc(when)}</td><td>${esc(then)}</td>`)).join('');
      const sheetNoteHTML = s.id === 'cart' && model.t >= 18 ? `<p class="sc-note">tests/screens/cart.test.json の 8 ケースと 1 対 1（${T.passed}/8 通過）</p>` : '';
      return `<table class="vt"><thead><tr><th><span class="sr">状態</span></th><th>メソッド</th><th>条件</th><th>結果</th></tr></thead><tbody>${rowsHTML}</tbody></table>${sheetNoteHTML}`;
    },
    () => `<ul class="files">${s.related.map(([type, path, exists], i) => {
      const now = i === s.relatedNow && s.by;
      return `<li class="${now ? 'now' : ''}"><span class="bdg">${esc(type)}</span><code>${esc(path)}</code>${exists === false ? '<span class="desc">まだ無い</span>' : ''}${now ? `<span class="editing">${pill(s.by, DEF[s.by].role)} ${s.status.kind === 'test' ? '実行中' : '編集中'}</span>` : ''}</li>`;
    }).join('')}</ul>`,
  ];
  const sheetHTML = SHEET.map(([k, title, key, wide]) => {
    // 関連ファイル: live, written when the spec lists any (the demo ties it to 分岐, as its script does).
    const w = k === 7 ? (s.measure ? (s.measure.related.total ? 1 : 0) : (s.written[6] >= 1 ? 1 : 0)) : s.written[k];
    const rel = s.measure && s.measure.related;
    const g = k !== 7 ? secState(s, k) : !w ? { kind: 'empty', text: '未記入' }
      : rel && rel.total ? { kind: rel.done >= rel.total ? 'done' : 'impl', f: rel.done / rel.total, text: `在る ${rel.done}/${rel.total}` } : { kind: 'written', text: '記入済み' };
    const writing = w > 0 && w < 1, live = !!s.by && k === activeSec(s);
    const cls = ['sc', wide && 'wide', w <= 0 && 'sc-empty', live && (k === s.writingIdx ? 'sc-writing' : k === s.testIdx ? 'sc-testing' : 'sc-active')].filter(Boolean).join(' ');
    const headHTML = `<header><h3>${esc(title)}</h3><code>${esc(key)}</code>${live ? pill(s.by, DEF[s.by].role) : ''}<span class="sc-chip ${chipCls(g)}">${esc(g.text)}</span></header>`;
    if (w <= 0) return `<section class="${esc(cls)}" id="wb-sec-${k}">${headHTML}<p class="sc-ph">まだ書かれていません</p></section>`;
    const act = live && k === s.writingIdx && activeKey === null ? (activeKey = `w${k}`, ' data-act') : '';
    const tailHTML = !writing ? '' : s.by ? `<p class="sc-typing">✎ ${esc(s.by)} が書き込み中<span class="caret" aria-hidden="true"></span></p>` : '<p class="sc-ph">ここで書きかけのまま止まっている</p>';
    return `<section class="${esc(cls)}" id="wb-sec-${k}"${esc(act)}>${headHTML}${bodies[k](w, writing)}${tailHTML}</section>`;
  }).join('');
  setHTML(wbCode, sheetHTML);

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
const tbEl = $('tb'), kanbanEl = $('kanban'), stripEl = $('perm-strip'), detailEl = $('tb-detail');
const tb = { open: false, detail: null, board: null };
$('tb-lanes').addEventListener('change', (e) => { UI.lanes = e.target.checked; writePref('lanes', UI.lanes ? 'on' : 'off'); renderTaskBoard(latestModel); });
function openTaskBoard(opener, detail, board) {
  if (detail !== undefined) tb.detail = detail;
  if (board !== undefined) tb.board = board;
  if (detail && !detail.startsWith('perm:') && !inScope(PROJECT_OF[detail.split('#')[0]])) setProject(PROJECT_OF[detail.split('#')[0]], { camera: false });
  if (detail && detail.startsWith('perm:') && !inScope(projectOfRobot(PERM_BY_ID[detail.slice(5)].who))) setProject(projectOfRobot(PERM_BY_ID[detail.slice(5)].who), { camera: false });
  if (wb.open) { wb.open = false; hideOverlay(wbEl); }
  if (rbState.id) closeRobot(true);
  if (tb.open) { renderTaskBoard(latestModel); if (detail) $('tbd-close').focus({ preventScroll: true }); return; }
  tb.open = true;
  zoomTo(taskPose(tb.board), opener, () => {
    if (!tb.open) return;
    showOverlay(tbEl);
    renderTaskBoard(latestModel);
    $(tb.detail ? 'tbd-close' : 'tb-close').focus({ preventScroll: true });
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
  if (!tb.open) return;
  tb.open = false; tb.detail = null;
  hideOverlay(tbEl);
  zoomBack();
}
$('tb-close').addEventListener('click', closeTaskBoard);
const COL_HINT = { todo: '担当が決まれば始められる', wait: '先に終わるタスクがある', doing: 'ロボットが今やっている', done: '' };
const mmss = (sec) => `${Math.floor(sec / 60)}:${String(Math.floor(sec % 60)).padStart(2, '0')}`;
const paintSince = (root, t, word) => root.querySelectorAll('[data-since]').forEach((el) => setText(el, `${word} ${mmss(Math.max(0, t - Number(el.dataset.since)))}`));
function renderTaskBoard(model) {
  if (!tb.open) return;
  const visible = (list) => inScope(PROJECT_OF[list]) && !UI.hiddenLists.has(list);
  const tasks = model.tasks.filter((x) => visible(x.list));
  // Permission prompts stay on top for the whole project even when some sessions are filtered out; prompts in
  // other projects are counted so they are never missed.
  const pend = model.pending.filter((p) => inScope(projectOfRobot(p.who)));
  const elsewhere = model.pending.length - pend.length;
  setText($('tb-count'), `${tasks.length} 件`);
  setText($('tb-title'), UI.project === 'all' ? 'タスクボード' : `タスクボード · ${PROJECT[UI.project].name}`);
  stripEl.hidden = !pend.length && !alwaysRules.size && !elsewhere;
  keyed(stripEl, JSON.stringify([pend.map(permSig), [...alwaysRules.keys()], elsewhere]), () => {
    const cardsHTML = pend.map((p) => {
      const x = p.task && TASK_BY_KEY[p.task];
      return `<li class="pcard"><div class="pc-who">${pill(p.who, DEF[p.who].role)}<span>${esc(DEF[p.who].agent)}</span><span class="pc-wait" data-since="${p.at}"></span></div><p class="pc-what"><b>${esc(p.tool)}</b> ${permSubject(p)}</p><button type="button" class="pc-task" data-open="${x ? esc(p.task) : `perm:${esc(p.id)}`}" data-fk="pt-${esc(p.id)}">${x ? `${esc(x.list)} ${esc(taskRef(x))} ${esc(x.subject)}` : `${esc(SESSION_OF[p.who])} セッション · タスクなし`} › 詳細</button><div class="perm-acts">${permButtons(p, 'p')}</div></li>`;
    }).join('');
    const rulesHTML = alwaysRules.size ? `<p class="ps-rules">このデモで足した常時許可: ${[...alwaysRules.keys()].map((r) => `<code>${esc(r)}</code>`).join(' ')} <button type="button" class="link-btn" data-reset-rules data-fk="rules">取り消す</button></p>` : '';
    const otherHTML = elsewhere ? `<p class="ps-rules">ほかのプロジェクトでも ${elsewhere} 件が許可を待っている <button type="button" class="link-btn" data-set-all data-fk="ps-all">すべてのプロジェクトを表示</button></p>` : '';
    return `<h3 class="ps-title">許可を求めています<b>${pend.length}</b><small>${PERM_NOTE}</small></h3>${cardsHTML ? `<ul class="ps-list">${cardsHTML}</ul>` : '<p class="ps-none">このプロジェクトでは今は誰も許可を求めていない</p>'}${otherHTML}${rulesHTML}`;
  });
  paintSince(stripEl, model.t, '待ち');
  const loopStart = simT - model.t;
  const lists = SESSIONS.filter((x) => visible(x.id)).map((x) => x.id);
  const noteHTML = (x, col) => {
      const ownerHTML = x.owner ? `${pill(x.owner, DEF[x.owner].role)}<span>${esc(DEF[x.owner].agent)}</span>` : '<span>担当なし</span>';
      const extraHTML = col === 'doing' ? `<span class="n-doing">▶ ${esc(isTurn(x) ? (x.background ? 'バックグラウンドで作業中' : '指示を処理中') : x.activeForm || x.subject)}<span data-since="${x.start}"></span></span>`
        : col === 'wait' ? (x.dep ? `<span class="n-wait">#${esc(x.dep.id)}「${esc(x.dep.subject)}」の完了待ち</span>` : `<span class="n-wait">${isTurn(x) ? (x.waitingFor === 'question' ? '質問に回答待ち' : '許可の返事待ち') : '待ち'}</span>`)
          : col === 'done' ? `<span class="n-time">${fmtClock(BASE_CLOCK + loopStart + x.end)} に${x.failed ? '失敗で終了' : '完了'}</span>` : '';
      const permHTML = x.perm ? `<div class="n-permbox"><p class="n-permq"><b>許可待ち</b> ${esc(x.perm.tool)} ${permSubject(x.perm)}</p><div class="perm-acts">${permButtons(x.perm, 'k')}</div></div>` : '';
      return `<li class="note${x.perm ? ' n-perm' : ''}${x.fresh ? ' n-new' : ''}${isTurn(x) ? ' n-turn' : ''}"><button type="button" class="note-open" data-open="${esc(x.key)}" data-fk="nb-${esc(x.key)}"><span class="n-top"><span>${esc(taskRef(x))}</span><span>${UI.lanes ? '' : `${esc(x.list)} の一覧${UI.project === 'all' ? ` · ${esc(PROJECT[PROJECT_OF[x.list]].name)}` : ''}`}</span></span><span class="n-subj">${esc(x.subject)}</span>${extraHTML}<span class="n-owner">${ownerHTML}</span></button>${permHTML}</li>`;
  };
  const sortCol = (col) => (a, b) => (b.perm ? 1 : 0) - (a.perm ? 1 : 0) || (col === 'done' ? b.end - a.end : 0) || a.list.localeCompare(b.list) || a.id - b.id;
  kanbanEl.classList.toggle('lanes', UI.lanes);
  keyed(kanbanEl, JSON.stringify([UI.lanes, lists, KCOLS.map(([col]) => tasks.filter((x) => x.col === col).map((x) => `${x.key}:${permSig(x.perm)}:${x.fresh ? 1 : 0}:${x.subject}:${x.owner || ''}`))]), () => {
    if (!lists.length) return `<p class="k-none">表示するセッションがない。上の「セッション」で選ぶ</p>`;
    if (!UI.lanes) return KCOLS.map(([col, label]) => {
      const items = tasks.filter((x) => x.col === col).sort(sortCol(col));
      return `<section class="kcol k-${esc(col)}" aria-label="${esc(label)} ${items.length} 件"><h3 class="ktab"><span>${esc(label)}${COL_HINT[col] ? `<small>${COL_HINT[col]}</small>` : ''}</span><b>${items.length}</b></h3><ol class="knotes">${items.map((x) => noteHTML(x, col)).join('') || '<li class="k-empty">なし</li>'}</ol></section>`;
    }).join('');
    // One lane per session: its four state columns side by side, sessions that need you first.
    const headHTML = `<div class="lane-cols" aria-hidden="true"><span></span>${KCOLS.map(([col, label]) => `<span class="k-${esc(col)}">${esc(label)}<b>${tasks.filter((x) => x.col === col).length}</b></span>`).join('')}</div>`;
    const ordered = SESSIONS.filter((x) => lists.includes(x.id)).sort((a, b) => SB_ORDER[sessionBadge(a)[0]] - SB_ORDER[sessionBadge(b)[0]] || a.id.localeCompare(b.id));
    return headHTML + ordered.map((x) => {
      const mine = tasks.filter((t) => t.list === x.id), [c, l] = sessionBadge(x);
      return `<section class="lane" aria-label="${esc(x.id)} のタスク ${mine.length} 件"><header class="lane-head"><button type="button" class="who-btn" data-robot-open="${esc(x.id)}" data-fk="lh-${esc(x.id)}">${pill(x.id, 'main')}<span>${esc(PROJECT[x.project].name)}</span></button><span class="state ${esc(c)}">${esc(l)}</span><small>${mine.length} 件</small></header>${KCOLS.map(([col, label]) => { const items = mine.filter((t) => t.col === col).sort(sortCol(col)); return `<div class="lane-cell k-${esc(col)}" aria-label="${esc(label)} ${items.length} 件"><span class="lane-label">${esc(label)} ${items.length}</span><ol class="knotes">${items.map((t) => noteHTML(t, col)).join('')}</ol></div>`; }).join('')}</section>`;
    }).join('');
  });
  paintSince(kanbanEl, model.t, '経過');
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
    const [cls, label] = x ? (x.perm ? ['st-waiting', '作業中・許可待ち'] : x.col === 'wait' ? ['st-waiting', '待ち'] : COL_STATE[x.col]) : ['st-idle', 'まだ作られていない'];
    const blocks = base ? TASKS.filter((q) => q.list === base.list && q.blockedBy === base.id) : [];
    const specIdx = base && base.spec ? SPEC_INDEX[base.spec] : -1;
    const spec = specIdx >= 0 ? model.specs[specIdx] : null;
    const histHTML = here.filter((q) => q.status !== 'pending' && q.status !== 'sent').map((q) => {
      const howHTML = SOURCE.mode === 'live' ? livePermHow(q) : q.status === 'terminal' ? 'ターミナルで許可された' : q.status === 'rule' ? `ルール ${esc(q.rule)} で自動許可` : q.status === 'deny' ? 'ビューで拒否した' : q.status === 'always' ? `ビューで許可し、${esc(q.rule)} を追加` : 'ビューで許可した';
      const at = q.decided ? fmtClock(BASE_CLOCK + q.decided.at) : clock(q.status === 'rule' ? q.at : q.end);
      return `<li><time>${esc(at)}</time><span>${howHTML} · ${esc(q.tool)} <code>${esc(permSummary(q))}</code></span></li>`;
    }).join('');
    const sample = pending || here[here.length - 1] || known;
    const times = base ? [base.created >= 0 ? `作成 ${clock(base.created)}` : '', base.start !== null && base.start <= model.t ? `開始 ${clock(base.start)}` : '', base.end !== null && base.end <= model.t ? `完了 ${clock(base.end)}` : ''].filter(Boolean).join(' · ') : '';
    return `<div class="tbd-top"><p class="tbd-id">${base ? `${esc(base.list)} ${esc(taskRef(base))} · ${esc(base.list)} の一覧` : `${esc(SESSION_OF[who])} セッション · タスクなし`}</p><button type="button" class="wb-btn" id="tbd-close" data-close-detail data-fk="tbd-close">閉じる</button></div>
<h3 id="tbd-title">${base ? esc(base.subject) : `${esc(known.tool)} の実行許可`}</h3>
${base ? `<p class="tbd-state"><span class="state ${esc(cls)}">${esc(label)}</span></p>` : ''}
${pending ? permDetail(pending, 'tbd') : ''}
<dl class="tbd-kv">
<dt>担当</dt><dd>${who ? `<button type="button" class="link-btn" data-robot-open="${esc(who)}" data-fk="tbd-who">${pill(who, DEF[who].role)} ${esc(DEF[who].agent)}</button>` : '担当なし'}</dd>
${who ? `<dt>今の作業</dt><dd data-live-act="${esc(who)}"></dd>` : ''}
${base ? `<dt>依存</dt><dd>${base.blockedBy ? `<button type="button" class="link-btn" data-open="${esc(base.list)}#${esc(base.blockedBy)}" data-fk="tbd-dep">#${esc(base.blockedBy)}「${esc(TASK_BY_KEY[`${base.list}#${base.blockedBy}`].subject)}」</button>${x && x.blocked ? ' の完了待ち' : ''}` : 'なし'}</dd>` : ''}
${base ? `<dt>後続</dt><dd>${blocks.length ? blocks.map((q) => `<button type="button" class="link-btn" data-open="${esc(q.list)}#${esc(q.id)}" data-fk="tbd-b${esc(q.id)}">#${esc(q.id)}「${esc(q.subject)}」</button>`).join(' ') : 'なし'}</dd>` : ''}
${times ? `<dt>時刻</dt><dd>${esc(times)}</dd>` : ''}
${spec ? `<dt>spec</dt><dd><button type="button" class="link-btn" data-spec-open="${specIdx}" data-fk="tbd-spec">${esc(spec.name)}（${esc(spec.screen)}）を開く</button><span class="state ${STATUS_CLASS[spec.status.kind]}">${esc(spec.status.text)}</span></dd>` : ''}
</dl>
${histHTML ? `<h4>許可の履歴</h4><ul class="tbd-list">${histHTML}</ul>` : ''}
${who ? `<h4>${esc(who)} の最近の動き</h4><ul class="tbd-list" data-recent="${esc(who)}"></ul>` : ''}
${sample ? rawDetails(sample) : ''}`;
  });
  paintSince(detailEl, model.t, '待ち');
  detailEl.querySelectorAll('[data-live-act]').forEach((el) => setText(el, robotState[el.dataset.liveAct].act));
  detailEl.querySelectorAll('[data-recent]').forEach((el) => setHTML(el, recentHTML(el.dataset.recent)));
}
const permDetail = (p, where) => (SOURCE.mode === 'live' ? permDetailLive(p, where) : permDetailDemo(p, where));
const permDetailLive = (p, where) => `<div class="tbd-perm"><h4>許可を求めています</h4><p>${pill(p.who, DEF[p.who].role)} ${esc(DEF[p.who].agent)} が <b>${esc(p.tool)}</b> を使いたい<span class="tbd-wait" data-since="${p.at}"></span></p><div class="tbd-cmd">${permSubjectLive(p)}</div>${p.can.reason ? `<label class="tbd-reason">拒否するときの理由（任意。Claude に伝わる）<input type="text" id="${esc(where)}-reason" autocomplete="off"></label>` : ''}<div class="perm-acts">${permButtons(p, where)}</div><p class="tbd-note">${PERM_NOTE}${p.relayOnly ? '。フックと照合できなかった中継の要求（内容は中継の文から）' : ''}</p></div>`;
const permDetailDemo = (p, where) => `<div class="tbd-perm"><h4>許可を求めています</h4><p>${pill(p.who, DEF[p.who].role)} ${esc(DEF[p.who].agent)} が <b>${esc(p.tool)}</b> を使いたい<span class="tbd-wait" data-since="${p.at}"></span></p><pre class="tbd-cmd">${esc(permSummary(p))}</pre><label class="tbd-reason">拒否するときの理由（任意。Claude に伝わる）<input type="text" id="${esc(where)}-reason" placeholder="例: 先に jui build を通して" autocomplete="off"></label><div class="perm-acts">${permButtons(p, where)}</div><p class="tbd-note">${PERM_NOTE}。「今後も許可」は <code>${esc(p.rule)}</code> を設定に足す。これと拒否の理由は PermissionRequest フック経由のときだけ返せる（channel の許可中継は許可・拒否のみ）</p></div>`;
/* The relay's request id: five lowercase letters without "l". */
const relayId = (p) => [...`${p.id}${p.who}xyz`].slice(0, 5).map((ch, k) => 'abcdefghijkmnopqrstuvwxyz'[(ch.charCodeAt(0) * 7 + k * 11) % 25]).join('');
const livePermHow = (q) => (q.status === 'terminal' ? (q.terminalBehavior === 'deny' ? 'ターミナルで拒否された' : 'ターミナルで許可された')
  : q.status === 'allow' ? (q.decidedBy === 'terminal' ? 'ターミナルで許可された' : q.sentRules ? `ビューで許可し、ルール ${q.sentRules.length} 件を追加` : 'ビューで許可した')
    : q.status === 'deny' ? (q.decidedBy === 'terminal' ? 'ターミナルで拒否された' : q.sentReason ? `ビューで拒否した（理由: ${esc(q.sentReason)}）` : 'ビューで拒否した')
    : q.status === 'expired' ? '答えないまま終わった' : esc(q.status));
const rawDetails = (p) => {
  if (SOURCE.mode === 'live') return `<details class="tbd-raw"><summary>受け取った内容</summary><pre>${esc(p.preview || permSummary(p))}</pre>${p.suggestions ? `<p>Claude Code が示した選択肢</p><pre>${esc(JSON.stringify(p.suggestions, null, 2))}</pre>` : ''}</details>`;
  const id = relayId(p);
  const relayIn = { method: 'notifications/claude/channel/permission_request', params: { request_id: id, tool_name: p.tool, description: p.tool + ' ' + permSummary(p), input_preview: JSON.stringify(p.input) } };
  const relayOut = { method: 'notifications/claude/channel/permission', params: { request_id: id, behavior: 'allow' } };
  return `<details class="tbd-raw"><summary>Claude Code とのやりとり（例）</summary><p>channel の許可中継で受け取る（ターミナルのダイアログも開いたまま）</p><pre>${esc(JSON.stringify(relayIn, null, 2))}</pre><p>返す（「許可」または「拒否」）</p><pre>${esc(JSON.stringify(relayOut, null, 2))}</pre><p>PermissionRequest フックで受け取る場合</p><pre>${esc(JSON.stringify(permRequestPayload(p), null, 2))}</pre><p>返す（「今後も許可」）</p><pre>${esc(JSON.stringify(permResponse(p, 'always'), null, 2))}</pre></details>`;
};

/* ---------- a robot up close: what it is doing, its tasks and its prompts ---------- */
const rbEl = $('rb');
const rbState = { id: null };
const CAM_DIR = new THREE.Vector3(0.25, 0.42, 0.87).normalize();
function robotPose(id) {
  const R = robots.find((x) => x.def.id === id);
  const dist = 8, wide = sceneEl.clientWidth > 900;
  const right = new THREE.Vector3().crossVectors(CAM_DIR.clone().negate(), new THREE.Vector3(0, 1, 0)).normalize();
  const viewH = 2 * dist * Math.tan(THREE.MathUtils.degToRad(camera.fov / 2)), viewW = viewH * camera.aspect;
  const t = R.robot.root.position.clone().add(new THREE.Vector3(0, 1.15, 0));
  // Wide: the card covers the right of the scene, so the robot sits left of centre. Narrow: the card is a
  // bottom sheet, so the robot sits high.
  if (wide) t.add(right.multiplyScalar((Math.min(420, sceneEl.clientWidth - 28) / 2 / sceneEl.clientWidth) * viewW));
  else t.y -= viewH * 0.2;
  return { p: t.clone().add(CAM_DIR.clone().multiplyScalar(dist)), t };
}
function openRobot(id, opener) {
  if (wb.open) { wb.open = false; hideOverlay(wbEl); }
  if (tb.open) { tb.open = false; tb.detail = null; hideOverlay(tbEl); }
  const showing = !!rbState.id;
  rbState.id = id;
  if (showing) { renderRobot(latestModel); $('rb-close').focus({ preventScroll: true }); return; }
  // no 3D, or the robot is not in the scene (another floor, another room of the one-room view): the card alone
  if (!has3D || !robots.some((x) => x.def.id === id)) {
    if (!zoom.zoomed) zoom.returnPose = null;   // nothing to fly back from when the card closes
    showOverlay(rbEl); renderRobot(latestModel); $('rb-close').focus({ preventScroll: true }); return; }
  zoomTo(robotPose(id), opener, () => {
    if (rbState.id !== id) return;
    showOverlay(rbEl);
    renderRobot(latestModel);
    $('rb-close').focus({ preventScroll: true });
  });
}
function closeRobot(keepZoom) {
  if (!rbState.id) return;
  rbState.id = null;
  hideOverlay(rbEl);
  histSync();
  if (!keepZoom) zoomBack();
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
  keyed(rbEl, JSON.stringify([id, permSig(pending), specIdx, owned.map((x) => `${x.key}:${x.col}:${x.perm ? 1 : 0}:${x.subject}`)]), () => {
    const room = (SESSIONS.find((s) => s.id === sess) || { room: (PROJECT[projectOfRobot(id)] || {}).name || '' }).room;
    const tasksHTML = owned.length ? `<ul class="rb-tasks">${owned.map((x) => {
      const [c, l] = x.perm ? ['st-waiting', '許可待ち'] : x.col === 'wait' ? [x.waitingFor === 'question' ? 'st-asking' : 'st-waiting', waitLabel(x)] : COL_STATE[x.col];
      return `<li><button type="button" class="task-open" data-open="${esc(x.key)}" data-fk="rt-${esc(x.key)}"><span class="state ${esc(c)}">${esc(l)}</span><span class="tid">${esc(x.list)} ${esc(taskRef(x))}</span><span class="subject">${x.harness ? `<span class="h-tag">${esc(x.harness)}</span>` : ''}${esc(x.subject)}</span>${!isMain || !x.owner ? '' : `<span class="rb-owner">${pill(x.owner, DEF[x.owner].role)}</span>`}</button></li>`;
    }).join('')}</ul>` : `<p class="rb-none">${isMain ? 'このセッションのタスク一覧は空' : '担当しているタスクはない'}</p>`;
    return `<div class="rb-head" style="--c:${ROLES[d.role].color}"><span class="rb-badge" aria-hidden="true">${esc(id)}</span><div><h2 class="rb-name" id="rb-title">${esc(isMain ? `${id} のメインセッション` : d.agent)}</h2><p class="rb-sub">${esc(isMain ? `${d.agent} · ${room}` : `${ROLE_JA[d.role]} · ${sess} セッションのサブエージェント · ${room}`)}</p></div><button type="button" class="wb-btn" id="rb-close" data-rb-close data-fk="rb-close">← 3D に戻る</button></div>
<div class="rb-tabs" role="tablist" aria-label="表示"><button type="button" role="tab" data-rb-tab="now" data-fk="rb-tab-now" aria-selected="true">今の様子</button><button type="button" role="tab" data-rb-tab="history" data-fk="rb-tab-history" aria-selected="false">応答の履歴</button></div>
<div class="rb-body rb-hist" data-rb-hist hidden aria-label="応答の履歴"></div>
<div class="rb-body">
<section class="rb-sec" aria-labelledby="rb-h-now"><h3 id="rb-h-now">今やっていること</h3><div class="rb-now"><p class="rb-state"><span class="rb-lamp" data-rb-lamp></span><b data-rb-state></b><span class="rb-since">ランプ: <span data-rb-lampname></span></span></p><p class="rb-act" data-rb-act></p><p class="rb-cond" data-rb-cond></p>${spec ? `<p class="rb-spec"><button type="button" class="link-btn" data-spec-open="${specIdx}" data-fk="rb-spec">${esc(spec.name)}（${esc(spec.screen)}）の spec</button> <span data-rb-specnow></span></p><span class="rb-segs" style="--c:${ROLES[d.role].color}">${SEGS}</span>` : ''}${(SOURCE.mode === 'demo' && id === 'a2') ? '<p class="rb-test" data-rb-test></p><div class="prog" data-rb-prog role="img"><span class="p"></span><span class="r"></span></div>' : ''}</div></section>
${pending ? `<section class="rb-sec" aria-label="許可">${permDetail(pending, 'rb')}</section>` : ''}
${SOURCE.mode === 'live' ? '<section class="rb-sec" aria-labelledby="rb-h-tests"><h3 id="rb-h-tests">テスト実行</h3><div data-rb-tests></div></section>' : ''}
<section class="rb-sec" aria-labelledby="rb-h-tasks"><h3 id="rb-h-tasks">${isMain ? 'このセッションのタスク' : '担当しているタスク'}<small>${owned.length} 件</small></h3>${tasksHTML}</section>
${subs.length ? `<section class="rb-sec" aria-labelledby="rb-h-subs"><h3 id="rb-h-subs">サブエージェント</h3><ul class="rb-subs">${subs.map((r) => `<li><button type="button" class="who-btn" data-robot-open="${esc(r)}" data-fk="rs-${esc(r)}">${pill(r, DEF[r].role)}<span>${esc(DEF[r].agent)}</span></button><span class="state" data-rb-sub="${esc(r)}"></span><p class="act" data-rb-subact="${esc(r)}"></p></li>`).join('')}</ul></section>` : ''}
<section class="rb-sec" aria-labelledby="rb-h-log"><h3 id="rb-h-log">最近の動き</h3><ul class="tbd-list" data-recent="${esc(id)}"></ul><button type="button" class="link-btn" data-log-robot="${esc(id)}" data-fk="rb-log">ログで ${esc(id)} だけを見る</button></section>
</div>`;
  });
  const S = STATES[st.state] || STATES.idle;
  setText(rbEl.querySelector('[data-rb-state]'), st.asking ? '質問に回答待ち' : S.name);
  setText(rbEl.querySelector('[data-rb-lampname]'), st.asking ? '黄（質問に回答待ち）' : LAMP_TEXT[S.lamp] || '');
  const lamp = rbEl.querySelector('[data-rb-lamp]'); if (lamp) lamp.style.background = LAMP[S.lamp];
  setText(rbEl.querySelector('[data-rb-act]'), st.act);
  // Tiredness and heavy work in words too (the 3D showed them, the card did not — 10-18 review)
  const cond = robotCondition(id), parts = [];
  if (cond.tired) parts.push(`稼働 ${Math.floor(cond.hours)} 時間（疲れ気味）`);
  if (cond.heavy) {
    const H = cond.heavy, why = [];
    if (H.reasons.includes('tokens')) why.push(`出力 ${Math.round(H.tokensPerMin || 0).toLocaleString('ja-JP')} トークン/分`);
    if (H.reasons.includes('tool')) why.push(`ツールが ${Math.round(H.toolSec || 0)} 秒走っている`);
    if (H.reasons.includes('subagents')) why.push(`サブエージェント ${H.subagents || 0} 体`);
    parts.push(`重い作業: ${why.join(' · ')}`);
  }
  const condEl = rbEl.querySelector('[data-rb-cond]');
  if (condEl) { setText(condEl, parts.join(' / ')); condEl.hidden = !parts.length; }
  if (spec) {
    const k = activeSec(spec);
    setText(rbEl.querySelector('[data-rb-specnow]'), `${spec.status.text}${k >= 0 ? ` · ${SECTIONS[k]}` : ''}`);
    paintSegs(rbEl.querySelector('.rb-segs .segs'), spec);
  }
  if ((SOURCE.mode === 'demo' && id === 'a2')) {
    const T = model.tests, n = CASES.length;
    setText(rbEl.querySelector('[data-rb-test]'), `${T.file} · ${T.statusText}`);
    const bar = rbEl.querySelector('[data-rb-prog]');
    bar.setAttribute('aria-label', `通過 ${T.passed} 件 / 全 ${n} 件`);
    bar.children[0].style.width = `${(T.passed / n) * 100}%`; bar.children[1].style.width = `${T.runningIdx >= 0 ? 100 / n : 0}%`;
  }
  rbEl.querySelectorAll('[data-rb-sub]').forEach((el) => paintState(el, robotBadge(el.dataset.rbSub)));
  rbEl.querySelectorAll('[data-rb-subact]').forEach((el) => setText(el, robotState[el.dataset.rbSubact].act));
  paintSince(rbEl, model.t, '待ち');
  rbEl.querySelectorAll('[data-recent]').forEach((el) => setHTML(el, recentHTML(el.dataset.recent)));
  const testsEl = rbEl.querySelector('[data-rb-tests]');
  if (testsEl) setHTML(testsEl, robotTestsHTML(robotRuns(id)));   // rewritten on every refresh while a run moves
  histSync();   // 55-history.js: the tab shown, and the history kept fresh while it is
}

/* ---------- live: the test run in the side panel (plan 09 §4) ---------- */
const CASE_ICON = { pending: '○', running: '▶', passed: '✓', flaky: '⚠', failed: '✗', skipped: '–' };
/* A robot's runs on its card: platform, state, counts, the bar, and the failed cases by name (FAILED_SHOWN at most). */
const FAILED_SHOWN = 5;
function robotTestsHTML(runs) {
  if (!runs.length) return '<p class="rb-none">このロボットが走らせたテストはまだ無い</p>';
  return `<ul class="rb-runs">${runs.map((T) => robotRunHTML(T)).join('')}</ul>`;
}
function robotRunHTML(T) {
  const n = T.rows.length, pPct = n ? (T.passed / n) * 100 : T.runStatus === 'passed' ? 100 : 0, rPct = n && T.runningIdx >= 0 ? 100 / n : 0;
  const fPct = n ? (T.failed / n) * 100 : T.runStatus === 'failed' ? 100 : 0;
  const failedRows = T.rows.filter((c) => c.status === 'failed');
  const namesHTML = failedRows.slice(0, FAILED_SHOWN).map((c) => `<li>${esc(c.name)}</li>`).join('');
  const moreHTML = failedRows.length > FAILED_SHOWN ? `<li class="rb-fail-more">ほか ${Math.max(0, failedRows.length - FAILED_SHOWN)} 件</li>` : '';
  return `<li class="rb-run r-${esc(T.runStatus)}" data-rb-run="${esc(T.id)}"><p class="rb-run-head"><b>${esc(T.device || 'テスト')}</b> <span>${esc(T.statusText)}</span>${T.savedAt ? '<small class="rb-saved">保存された結果</small>' : ''}</p><code class="rb-run-file">${esc(T.file)}</code>
<div class="prog" role="img" aria-label="通過 ${T.passed} 件 / 失敗 ${T.failed} 件 / 全 ${n} 件"><span class="p" style="width:${pPct}%"></span><span class="r" style="width:${rPct}%"></span><span class="x" style="width:${fPct}%"></span></div>${namesHTML ? `<ul class="rb-fails" aria-label="失敗したケース">${namesHTML}${moreHTML}</ul>` : ''}</li>`;
}
function liveTestsHTML(T) {
  const n = T.rows.length, pPct = n ? (T.passed / n) * 100 : T.runStatus === 'passed' ? 100 : 0, rPct = n && T.runningIdx >= 0 ? 100 / n : 0;
  const fPct = n ? (T.failed / n) * 100 : T.runStatus === 'failed' ? 100 : 0;
  const whoPillHTML = T.who && DEF[T.who] ? pill(T.who, DEF[T.who].role) : '';
  return `<div class="test-head"><div>${whoPillHTML} <code>${esc(T.file)}</code></div><code>${esc(T.device)}${T.device ? ' · ' : ''}${esc(T.statusText)}</code>
<div class="prog" role="img" aria-label="通過 ${T.passed} 件 / 全 ${n} 件"><span class="p" style="width:${pPct}%"></span><span class="r" style="width:${rPct}%"></span><span class="x" style="width:${fPct}%"></span></div></div>
<ul class="cases">${T.rows.map((c, i) => `<li class="c-${esc(c.status)}"><span class="ic">${CASE_ICON[c.status] || '○'}</span><span>${i + 1}. ${esc(c.name)}</span>${c.status === 'running' ? `<span class="step">${esc(c.step)}</span>` : ''}</li>`).join('')}</ul>`;
}

/* ---------- live: "from now on" asks first (plan 08 §5) ----------
   Only the request's own suggestions can be added. The dialog lists each one — the rules and where they are
   saved — with a box each; the answer goes out only from its confirm button. */
const DEST_JA = {
  localSettings: 'このプロジェクトの .claude/settings.local.json（自分だけ）',
  projectSettings: 'このプロジェクトの .claude/settings.json（共有）',
  userSettings: '~/.claude/settings.json（すべてのプロジェクト）',
  session: 'このセッションの間だけ',
};
function suggestionHTML(sg) {
  if (!sg || typeof sg !== 'object') return `<code>${esc(JSON.stringify(sg))}</code>`;
  const whereHTML = sg.destination ? `<small>保存先: ${esc(DEST_JA[sg.destination] || sg.destination)}</small>` : '';
  if (sg.type === 'addRules' && Array.isArray(sg.rules)) {
    const rulesHTML = sg.rules.map((r) => `<code>${esc(r && r.toolName ? `${r.toolName}${r.ruleContent ? `(${r.ruleContent})` : ''}` : JSON.stringify(r))}</code>`).join(' ');
    return `<span>${sg.behavior === 'deny' ? '拒否するルール' : '許可するルール'} ${rulesHTML}</span>${whereHTML}`;
  }
  if (sg.type === 'setMode') return `<span>モードを <code>${esc(sg.mode)}</code> にする</span>${whereHTML}`;
  if (sg.type === 'addDirectories' && Array.isArray(sg.directories)) return `<span>作業フォルダを足す ${sg.directories.map((d) => `<code>${esc(d)}</code>`).join(' ')}</span>${whereHTML}`;
  return `<code>${esc(JSON.stringify(sg))}</code>${whereHTML}`;
}
let alwaysDlg = null;
function openAlwaysConfirm(p, opener) {
  const list = Array.isArray(p.suggestions) ? p.suggestions : [];
  if (!list.length) { showToast('この要求には今後も許可できるルールが無い'); return; }
  closeAlwaysConfirm(false);
  const el = document.createElement('div');
  el.className = 'perm-confirm'; el.setAttribute('role', 'dialog'); el.setAttribute('aria-modal', 'true'); el.setAttribute('aria-labelledby', 'pcf-title');
  el.innerHTML = `<div class="pcf-box"><h3 id="pcf-title">今後も許可する内容を確かめる</h3><p>${pill(p.who, DEF[p.who].role)} の <b>${esc(p.tool)}</b> ${permSubject(p)} を許可し、次を設定に足す。外したものは足さない。</p>
<ul class="pcf-list">${list.map((sg, i) => `<li><label><input type="checkbox" data-pcf="${i}" checked>${suggestionHTML(sg)}</label></li>`).join('')}</ul>
<div class="pcf-acts"><button type="button" class="pa pa-always" data-pcf-ok>この内容で今後も許可</button><button type="button" class="pa" data-pcf-cancel>やめる</button></div></div>`;
  document.body.append(el);
  alwaysDlg = { el, p, opener };
  el.addEventListener('click', (e) => {
    if (e.target === el || e.target.closest('[data-pcf-cancel]')) { closeAlwaysConfirm(true); return; }
    if (!e.target.closest('[data-pcf-ok]')) return;
    const keep = [...el.querySelectorAll('[data-pcf]')].filter((c) => c.checked).map((c) => Number(c.dataset.pcf));
    if (!keep.length) { showToast('足すルールを 1 つ以上選んでください'); return; }
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
