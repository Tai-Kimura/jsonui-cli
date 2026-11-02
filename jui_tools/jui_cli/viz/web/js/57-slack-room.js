/* ---------- the sorting factory: the Slack intake's own room (docs/plans/2026-11-02-viz-slack-intake-design.md §5–§7).
   Requester 11-02: 「Slack のセッション（タスク作りのロボット）は、ほかのロボットとは別の部屋にいる。部屋は仕分け工場の作り」;
   「この部屋には、プロジェクトとは別の経路で入る」; 「部屋にいるロボットは 1 体だけ。画面に出すのは 1. タスクの表示（仕分けの様子）
   2. そのロボットへ指示を出す UI 3. タスクボード」; 「ホワイトボードにメモ紙が貼ってある作り。1 タスクが 1 枚のメモ紙」.

   The header's Slack button (beside デバイス) opens it over the whole page, as the server room does (the floors' 3D is
   not drawn under it: srCovers). The server's slice slackRoom (slack_room.py) gives the folder, the robot (the session
   whose cwd is in the folder — the floors leave its room out: rebuildRooms), the sorted messages, the tasks and the two
   prompts. Left: the factory in 3D — a chute, a belt, the robot at the sorting table, one bin per project with a parcel
   per message in it (a message that comes while the room is open rides the belt into its bin) — what was sorted under
   it, and a box to tell the robot something (POST /api/prompt to its session). Right: the whiteboard, one lane per
   state (draft → ready → working → ended → done), one note per task. On a draft or ready note the prompt is edited in
   place, the session it goes to is chosen (the running ones; one that cannot take a prompt says why, and the command
   to start one with the channel is copied from the note), the robot is asked to change it; 開始 sends it (POST
   /api/slack-room/task: the server sends the prompt and marks it working), 完了 closes it. A note being edited is not
   redrawn under the hand: what is typed stays until it is saved or sent. ---------- */
const sfEl = $('sf');
const SF = { open: false, opener: null, view: null, full: false, lane: null, sel: null, edit: null, revise: null, drafts: {}, notes: new Map(), seen: null, parcels: [], status: '' };
const SF_LANES = ['talking', 'draft', 'ready', 'working', 'ended', 'done'];
const SF_LANE = { talking: tl('sf.lane.talking'), draft: tl('sf.lane.draft'), ready: tl('sf.lane.ready'), working: tl('sf.lane.working'), ended: tl('sf.lane.ended'), done: tl('sf.lane.done') };
const SF_SAID = { save: tl('sf.said.save'), ready: tl('sf.said.ready'), start: tl('sf.said.start'), done: tl('sf.said.done'), revise: tl('sf.said.revise'), draft: tl('sf.said.draft'), status: tl('sf.said.status') };
const SF_NOTE_HUE = { talking: 290, draft: 52, ready: 18, working: 205, ended: 140, done: 250 };
const SF_BELT = { from: -5.2, to: 0.4, z: 0, y: 0.78, speed: 2.4 };
const SF_BIN_MAX = 6;
function sfSlice() {
  const live = SOURCE.mode === 'live' && typeof LIVE !== 'undefined';
  const s = live && LIVE.slices.slackRoom && typeof LIVE.slices.slackRoom === 'object' ? LIVE.slices.slackRoom : null;
  return s && typeof s.dir === 'string' ? s : null;
}
function sfCovers() { return SF.open; }
const sfTasks = (s) => (Array.isArray(s.tasks) ? s.tasks.filter((t) => t && typeof t.id === 'string') : []);
const sfTargets = (s) => (Array.isArray(s.targets) ? s.targets.filter((t) => t && typeof t.sessionId === 'string') : []);
/* The tasks waiting on a person: a draft to look at, one ready to start, one whose work ended. */
const sfWaiting = (s) => sfTasks(s).filter((t) => t.status === 'draft' || t.status === 'ready' || t.status === 'ended').length;
const sfClock = (ms) => (Number(ms) > 0 ? new Date(Number(ms)).toTimeString().slice(0, 5) : '');

/* ---------- the header's button ---------- */
function renderSlackButton() {
  const s = sfSlice(), btn = $('btn-slack');
  btn.hidden = !s;
  if (!s) { if (SF.open) sfClose(false); return; }
  const n = sfWaiting(s);
  setText(btn, n ? tl('sf.button.count', { count: n }) : tl('sf.button'));
  const aria = tl('sf.button.aria', { n });
  if (btn.getAttribute('aria-label') !== aria) btn.setAttribute('aria-label', aria);
  if (SF.open) sfRender(s);
}

/* ---------- the room ---------- */
function sfOpen(opener) {
  const s = sfSlice();
  if (!s) return;
  SF.open = true; SF.opener = opener || null;
  SF.seen = null;   // the first render takes what is there as already sorted: only what comes later rides the belt
  showOverlay(sfEl);
  $('btn-slack').setAttribute('aria-expanded', 'true');
  sfBuild();
  sfRender(s);
  $('sf-back').focus({ preventScroll: true });
}
function sfClose(back = true) {
  if (!SF.open) return;
  SF.open = false;
  sfPromptsClose(false);
  sfChatClose(false);
  sfReviseClose(false);
  sfEditClose(false);
  if (SF.full) sfFull(false);
  sfDispose();
  hideOverlay(sfEl);
  $('btn-slack').setAttribute('aria-expanded', 'false');
  const to = SF.opener; SF.opener = null;
  if (back && to && document.contains(to)) to.focus({ preventScroll: true });
}
function sfRender(s) {
  setText($('sf-dir'), sfShortPath(s.dir) + (s.dirExists ? '' : tl('sf.dir.missing')));
  if ($('sf-dir').title !== String(s.dir)) $('sf-dir').title = String(s.dir);
  sfRenderRobot(s);
  sfRenderFlow(s);
  sfRenderBoard(s);
  sfSync(s);
}

/* ---------- the robot and the box to tell it something ---------- */
function sfRobotLabel(s) { return s.robot && typeof s.robot.label === 'string' ? s.robot.label : ''; }
function sfRobotHTML(s) {
  const r = s.robot;
  if (!r) {
    return `<p class="sf-none">${esc(tl('sf.robot.none'))}</p>${sfCopyHTML(String(s.robotLaunch || ''), tl('sf.robot.launch'))}`;
  }
  const st = robotState[r.label] || { state: 'idle', act: '' };
  const lamp = LAMP_TEXT[st.state] || st.state;
  // the session's name (claude -n, from robotLaunch) where it has one, its label beside it
  const name = typeof r.title === 'string' && r.title.trim() ? r.title.trim() : '';
  return `<p class="sf-who"><span class="sf-lamp" data-state="${esc(st.state)}"></span><b class="sf-robot-name">${esc(name || r.label)}</b>${name ? ` <span class="sf-act">${esc(r.label)}</span>` : ''} ${esc(lamp)} <span class="sf-act">${esc(st.act || '')}</span></p>`
    + (r.canPrompt ? '' : `<p class="sf-why">${esc(tl('sf.robot.cannot', { why: String(r.why || '') }))}</p>${sfCopyHTML(String(s.robotLaunch || ''), tl('sf.robot.launch'))}`);
}
function sfRenderRobot(s) {
  const r = s.robot, st = r ? robotState[r.label] || {} : {};
  keyed($('sf-robot'), JSON.stringify([r, st.state, st.act, s.robotLaunch]), () => sfRobotHTML(s));
  const can = !!(r && r.canPrompt);
  $('sf-say').disabled = !can;
  $('sf-send').disabled = !can;
}
async function sfSend() {
  const s = sfSlice(), area = $('sf-say'), text = area.value;
  if (!s || !s.robot || !text.trim()) return;
  $('sf-send').disabled = true;
  const got = await SOURCE.sendPrompt(s.robot.label, text, []);
  $('sf-send').disabled = false;
  if (got.ok) { area.value = ''; setText($('sf-said'), tl('sf.say.sent')); }
  else setText($('sf-said'), tl('sf.failed', { error: got.error || String(got.status) }));
}

/* ---------- what was sorted ---------- */
function sfFlowHTML(s) {
  const a = s.arrivals || {}, recent = Array.isArray(a.recent) ? a.recent : [];
  const by = a.byProject && typeof a.byProject === 'object' ? Object.entries(a.byProject) : [];
  const note = s.note === 'no-robot' ? tl('sf.flow.note.robot') : s.note === 'no-channel' ? tl('sf.flow.note.channel')
    : s.note === 'busy' ? tl('sf.flow.note.busy') : '';
  const binsHTML = by.map(([p, n]) => `<li><span class="sf-bin-dot" style="background:${esc(sfProjectColor(p))}"></span>${esc(p)} <b>${esc(String(n))}</b></li>`).join('');
  const rowsHTML = recent.map((r) => `<li class="sf-msg" data-sf-msg="${esc(String(r.path || ''))}"><span class="sf-to" style="border-color:${esc(sfProjectColor(String(r.projectId || '')))}">${esc(String(r.projectId || ''))}</span>`
    + `<span class="sf-from">${esc(String(r.channel || ''))} · ${esc(String(r.user || ''))}</span><span class="sf-head">${esc(r.broken ? tl('sf.flow.broken') : String(r.head || ''))}</span></li>`).join('');
  return `<p class="sf-counts">${esc(tl('sf.flow.counts', { total: Number(a.total) || 0, pending: Number(a.pending) || 0, unsorted: Number(a.unsorted) || 0 }))}</p>`
    + (note ? `<p class="sf-why">${esc(note)}</p>` : '')
    + (Number(s.toldAt) > 0 ? `<p class="dev-note">${esc(tl('sf.flow.told', { at: sfClock(s.toldAt), n: Number(s.told) || 0 }))}</p>` : '')
    + (by.length ? `<ul class="sf-bins">${binsHTML}</ul>` : '')
    + (recent.length ? `<ol class="sf-msgs">${rowsHTML}</ol>` : `<p class="sf-none">${esc(tl('sf.flow.none'))}</p>`);
}
function sfRenderFlow(s) {
  keyed($('sf-flow-body'), JSON.stringify([s.arrivals, s.note, s.toldAt, s.told]), () => sfFlowHTML(s));
  sfRenderIntake();
}
/* Stage 1's own state (the slice slack, slack/intake.py): the last and the next fetch, one running, why it cannot run;
   今すぐ取る asks it for a fetch now (POST /api/slack/fetch). */
function sfIntake() { return typeof LIVE !== 'undefined' && LIVE.slices.slack && typeof LIVE.slices.slack === 'object' ? LIVE.slices.slack : null; }
function sfRenderIntake() {
  const k = sfIntake(), btn = $('sf-fetch');
  btn.hidden = !k;
  sfRenderFetchErrors(k);
  if (!k) { setText($('sf-intake'), ''); return; }
  btn.disabled = !k.configured || !!k.running;
  const failed = Array.isArray(k.failed) ? k.failed.length : 0;
  const parts = !k.configured ? [k.error ? tl('sf.intake.error', { error: String(k.error) }) : tl('sf.intake.none')]
    : [k.running ? tl('sf.intake.running') : tl('sf.intake.last', { at: k.lastRun && k.lastRun.at ? sfClock(k.lastRun.at) : tl('sf.intake.never') }),
      k.nextRun ? tl('sf.intake.next', { at: sfClock(k.nextRun) }) : tl('sf.intake.manual')]
      .concat(failed ? [tl('sf.intake.failed', { n: failed })] : []);
  setText($('sf-intake'), parts.join(tl('sf.intake.sep')));
}
/* The last fetch's errors (lastRun.errors: "<workspace>/<channel>: <method>: <Slack's error>"), the count and the
   first one's words, with a hint where the fix is known; and the connector's warning (modeNote) while mode is
   connector. The server writes paths from ~ and keeps no key in them (slack/intake.py); a key-shaped word is masked
   here again. */
const SF_KEY_SHAPE = /\b(?:xox[a-z]-|sk-ant-)[A-Za-z0-9_-]+/g;
function sfFetchHint(text) {
  const scope = /\/([CDG])[A-Z0-9]+: [^:]*: missing_scope\b/.exec(text);
  if (scope) return tl(scope[1] === 'D' ? 'sf.intake.hint.im' : scope[1] === 'G' ? 'sf.intake.hint.groups' : 'sf.intake.hint.channels');
  if (/: (?:not_in_channel|channel_not_found)\b/.test(text)) return tl('sf.intake.hint.invite');
  if (/: (?:invalid_auth|not_authed|token_revoked|account_inactive|no token)\b/.test(text)) return tl('sf.intake.hint.token');
  return '';
}
function sfRenderFetchErrors(k) {
  const el = $('sf-intake-err'), note = $('sf-mode-note');
  const errs = k && k.configured && !k.running && k.lastRun && Array.isArray(k.lastRun.errors) ? k.lastRun.errors.filter((e) => typeof e === 'string') : [];
  const text = errs.length ? String(errs[0]).replace(SF_KEY_SHAPE, '…') : '';
  const hint = text ? sfFetchHint(text) : '';
  setText(el, text ? tl('sf.intake.errors', { n: errs.length, error: text }) + (hint ? tl('sf.intake.sep') + hint : '') : '');
  el.hidden = !text;
  const connector = !!(k && k.configured && k.mode === 'connector');
  setText(note, connector ? tl('sf.intake.modeNote', { note: tl('srv.slack.modeNote') }) : '');
  note.hidden = !connector;
}
/* The left column's two tabs (the requester, 11-02): one at a time, the column's height its own; the last one kept. */
const SF_TAB_KEY = 'jui-viz.sf.tab';
function sfTab(k, focus = false) {
  const tab = k === 'flow' ? 'flow' : 'talk';
  for (const b of document.querySelectorAll('#sf .sf-tab')) {
    const on = b.dataset.sfTab === tab;
    b.setAttribute('aria-selected', String(on));
    b.tabIndex = on ? 0 : -1;
    $(b.getAttribute('aria-controls')).hidden = !on;
    if (on && focus) b.focus();
  }
  try { localStorage.setItem(SF_TAB_KEY, tab); } catch (err) { /* storage refused: the tab is not kept */ }
}
function sfTabSaved() { try { return localStorage.getItem(SF_TAB_KEY) === 'flow' ? 'flow' : 'talk'; } catch (err) { return 'talk'; } }
async function sfFetch() {
  $('sf-fetch').disabled = true;
  const got = await sfPost('/api/slack/fetch', {});
  if (!got.ok) setText($('sf-intake'), tl('sf.failed', { error: got.error || String(got.status) }));
}

/* ---------- the whiteboard ---------- */
function sfCopyHTML(line, label) {
  return `<div class="sf-copy"><span class="sf-copy-label">${esc(label)}</span><code>${esc(line)}</code><button type="button" class="wb-btn" data-sf-copy="${esc(line)}">${esc(tl('sf.copy'))}</button></div>`;
}
function sfTargetHTML(t, s) {
  const d = SF.drafts[t.id] || {};
  const chosen = d.sessionId !== undefined ? d.sessionId : (t.target && t.target.sessionId) || '';
  const named = t.target && t.target.sessionName ? String(t.target.sessionName) : '';
  const targets = sfTargets(s);
  const optionsHTML = targets.map((x) => `<option value="${esc(x.sessionId)}"${x.sessionId === chosen ? ' selected' : ''}${x.canPrompt ? '' : ' disabled'}>`
    + `${esc(tl('sf.target.option', { name: x.title || x.label, project: x.project || x.label }))}${esc(x.canPrompt ? '' : tl('sf.target.cannot'))}</option>`).join('');
  // the command to start a fitting session: when none can take a prompt, or the robot found none (its launchCommand, or a
  // session it named that is not running), until one is chosen
  const usable = targets.some((x) => x.canPrompt), own = typeof t.launchCommand === 'string' && t.launchCommand;
  const line = own ? t.launchCommand : String(s.launch || '');
  return `<label class="sf-field"><span class="sf-label">${esc(tl('sf.note.target'))}</span><select data-sf-target>`
    + `<option value=""${chosen ? '' : ' selected'}>${esc(named ? tl('sf.target.named', { name: named }) : tl('sf.target.choose'))}</option>${optionsHTML}</select></label>`
    + (chosen || (usable && !named && !own) ? '' : sfCopyHTML(line, own ? tl('sf.target.launch') : tl('sf.target.launch.dir')));
}
/* The messages a task was made from, oldest first: who, where, the head (the server's sourceHeads). Folded on a note
   that has a prompt; open on a talking one (the exchange so far is what it shows). */
function sfSourcesHTML(t, s) {
  const paths = Array.isArray(t.sources) ? t.sources.filter((p) => typeof p === 'string') : [];
  const atEdit = new Set(Array.isArray(t.sourcesAtEdit) ? t.sourcesAtEdit : []);
  const late = t.promptEditedByUser === true ? paths.filter((p) => !atEdit.has(p)).length : 0;
  const threads = Array.isArray(t.threads) ? t.threads.length : 0;
  return (late ? `<p class="sf-mark sf-mark-late">${esc(tl('sf.note.late', { n: late }))}</p>` : '')
    + `<button type="button" class="sf-src-open" data-sf-chat${paths.length ? '' : ' disabled'}>${esc(tl('sf.note.sources', { n: paths.length }))}${threads > 1 ? esc(tl('sf.note.threads', { n: threads })) : ''}</button>`;
}
/* The other notes this one is tied to: a later message about it made a new task (relatedTaskId), or it is that task. */
function sfRelatedHTML(t, s) {
  const all = sfTasks(s), title = (id) => { const x = all.find((y) => y.id === id); return x ? String(x.title || x.id) : String(id); };
  const later = all.filter((x) => x.relatedTaskId === t.id);
  const laterHTML = later.map((x) => `<p class="sf-mark sf-mark-more">${esc(tl('sf.note.more', { id: x.id, title: String(x.title || x.id) }))}</p>`).join('');
  return (typeof t.relatedTaskId === 'string' && t.relatedTaskId ? `<p class="sf-mark">${esc(tl('sf.note.follows', { id: t.relatedTaskId, title: title(t.relatedTaskId) }))}</p>` : '') + laterHTML;
}
/* A note (requester 11-02, the refine): its id and its state on top; the title (3 lines, the whole on hover); its project
   and the ties; its messages (they open beside the board); the prompt and the session under their labels; one row of
   actions, 開始 at its right. Spaced 4 / 8 / 12. The state is chosen from the select (sent nothing: 開始 alone sends). */
function sfNoteHTML(t, s) {
  const edit = t.status === 'talking' || t.status === 'draft' || t.status === 'ready';
  const d = SF.drafts[t.id] || {};
  const prompt = d.prompt !== undefined ? d.prompt : typeof t.prompt === 'string' ? t.prompt : '';
  const title = String(t.title || t.id);
  const who = t.target && t.target.sessionName ? String(t.target.sessionName) : '';
  const times = [['sf.note.created', t.createdAt], ['sf.note.started', t.startedAt], ['sf.note.ended', t.endedAt], ['sf.note.done', t.doneAt]]
    .filter(([, at]) => Number(at) > 0);
  const timesHTML = times.map(([k, at]) => `<span>${esc(tl(k, { at: sfClock(at) }))}</span>`).join('');
  const idHTML = `<button type="button" class="sf-id" data-sf-copy="${esc(t.id)}" data-sf-label="${esc(t.id)}" title="${esc(tl('sf.note.id.title'))}" aria-label="${esc(tl('sf.note.id.aria', { id: t.id }))}">${esc(t.id)}</button>`;
  if (t.broken) return `${idHTML}<p class="sf-why">${esc(tl('sf.note.broken', { id: t.id }))}</p>`;
  const optionsHTML = SF_LANES.map((k) => `<option value="${esc(k)}"${k === t.status ? ' selected' : ''}>${esc(SF_LANE[k])}</option>`).join('');
  const stateHTML = `<select class="sf-state" data-sf-status aria-label="${esc(tl('sf.note.state', { id: t.id }))}">${optionsHTML}</select>`;
  const left = Number(t.purgeAt) > 0 ? Math.max(0, Math.ceil((Number(t.purgeAt) - Date.now()) / 60000)) : -1;
  const purgeHTML = left >= 0 ? `<p class="sf-mark sf-mark-purge" data-sf-purge="${esc(String(t.purgeAt))}">${esc(tl('sf.note.purge', { n: left }))}</p>` : '';
  // the prompt's first lines only, no scroll inside the note: a press opens it whole in the popup (edited there while it can be)
  const empty = !prompt.trim();
  const promptHTML = `<div class="sf-field"><span class="sf-label">${esc(tl('sf.note.prompt'))}</span>`
    + `<button type="button" class="sf-prompt-view${empty ? ' is-empty' : ''}" data-sf-prompt-open aria-haspopup="dialog" aria-label="${esc(tl(edit ? 'sf.note.prompt.edit' : 'sf.note.prompt.read', { id: t.id }))}">`
    + `<span class="sf-prompt-text">${esc(empty ? (t.status === 'talking' ? tl('sf.note.talking') : tl('sf.note.prompt.empty')) : prompt)}</span></button></div>`;
  const actsHTML = edit
    ? `<button type="button" class="wb-btn sf-revise-open" data-sf-revise-open aria-haspopup="dialog">${esc(tl('sf.op.revise'))}</button>`
      + `<div class="sf-acts sf-note-acts"><button type="button" class="wb-btn" data-sf-op="save">${esc(tl('sf.op.save'))}</button>`
      + `<span class="grow"></span>${t.status === 'ready' ? `<button type="button" class="wb-btn sf-go" data-sf-op="start">${esc(tl('sf.op.start'))}</button>` : ''}</div>`
    : '';
  return `<div class="sf-note-top">${idHTML}</div>`
    + `<p class="sf-note-title" title="${esc(title)}">${esc(title)}</p>`
    + (sfStale(t) ? `<button type="button" class="wb-btn sf-reload" data-sf-reload>${esc(tl('sf.note.stale'))}</button>` : '')
    + `<label class="sf-field sf-state-row"><span class="sf-label">${esc(tl('sf.note.state.label'))}</span>${stateHTML}</label>`
    + (t.projectId ? `<p class="sf-note-meta"><span class="sf-to" style="border-color:${esc(sfProjectColor(String(t.projectId)))}">${esc(String(t.projectId))}</span></p>` : '')
    + `${purgeHTML}${sfRelatedHTML(t, s)}${sfSourcesHTML(t, s)}${promptHTML}`
    + (t.promptEditedByUser === true && edit ? `<p class="sf-mark">${esc(tl('sf.note.edited'))}</p>` : '')
    + (edit && t.status !== 'talking' ? sfTargetHTML(t, s) : who ? `<p class="sf-target-ro">${esc(tl('sf.note.sent', { name: who }))}</p>` : '')
    + `${actsHTML}<p class="sf-note-times">${timesHTML}</p><p class="sf-note-said" role="status"></p>`;
}
/* The selector of a pressed thing on a note, to find it again after the note is drawn again. */
function sfFocusKey(el) {
  const attr = ['data-sf-op', 'data-sf-revise-open', 'data-sf-prompt-open', 'data-sf-chat', 'data-sf-reload', 'data-sf-copy'].find((a) => el.hasAttribute(a));
  if (!attr) return el.classList.contains('sf-id') ? '.sf-id' : '';
  const v = el.getAttribute(attr);
  return v ? '[' + attr + '="' + CSS.escape(v) + '"]' : '[' + attr + ']';   // a selector, not HTML
}
/* What was typed on a note and not saved, while its file changed under it: the prompt or the target. */
function sfStale(t) {
  const d = SF.drafts[t.id]; if (!d) return false;
  const prompt = typeof t.prompt === 'string' ? t.prompt : '', sid = (t.target && t.target.sessionId) || '';
  return (d.prompt !== undefined && d.promptBase !== undefined && d.promptBase !== prompt)
    || (d.sessionId !== undefined && d.sessionBase !== undefined && d.sessionBase !== sid);
}
/* A draft of a note: what is typed, and the file's value it was typed over (sfStale). */
function sfDraft(id) {
  let d = SF.drafts[id];
  if (!d) {
    const t = sfTaskOf(id);
    d = SF.drafts[id] = { promptBase: t && typeof t.prompt === 'string' ? t.prompt : '', sessionBase: (t && t.target && t.target.sessionId) || '' };
  }
  return d;
}
/* One lane per state, drawn once; a note is drawn again when its task changed. */
function sfRenderBoard(s) {
  const wb = $('sf-wb');
  if (!wb.firstChild) {
    const lanesHTML = SF_LANES.map((k) => `<section class="sf-lane" data-sf-lane="${esc(k)}"><h4><button type="button" class="sf-lane-btn" data-sf-lane-open="${esc(k)}" title="${esc(tl('sf.lane.open', { lane: SF_LANE[k] }))}">${esc(SF_LANE[k])} <span class="sf-lane-n"></span></button></h4><div class="sf-lane-notes"></div></section>`).join('');
    wb.innerHTML = lanesHTML;
  }
  const tasks = sfTasks(s), ids = new Set(tasks.map((t) => t.id));
  for (const [id, n] of SF.notes) if (!ids.has(id)) { n.el.remove(); SF.notes.delete(id); delete SF.drafts[id]; }
  const targetsSig = JSON.stringify([sfTargets(s), s.launch]);
  const ties = (t) => JSON.stringify([(Array.isArray(t.sources) ? t.sources : []).map((p) => (s.sourceHeads || {})[p] || null),
    tasks.filter((x) => x.relatedTaskId === t.id || x.id === t.relatedTaskId).map((x) => [x.id, x.title])]);
  tasks.forEach((t, k) => {
    const lane = SF_LANES.includes(t.status) ? t.status : 'draft';
    let n = SF.notes.get(t.id);
    if (!n) {
      const el = document.createElement('article');
      el.className = 'sf-note';
      el.dataset.sfTask = t.id;
      el.style.setProperty('--tilt', `${((k * 37) % 7) - 3}deg`);
      n = { el, sig: '' };
      SF.notes.set(t.id, n);
    }
    n.el.dataset.status = lane;
    n.el.style.setProperty('--note-h', String(SF_NOTE_HUE[lane]));
    const box = wb.querySelector(`[data-sf-lane="${CSS.escape(lane)}"] .sf-lane-notes`);
    if (n.el.parentElement !== box) box.appendChild(n.el);
    const sig = JSON.stringify([t, ties(t), lane === 'draft' || lane === 'ready' ? targetsSig : '', sfStale(t)]);
    // a note follows its file (the robot's rewrite after 直しを頼む, 2.4.0): drawn again unless a select or a field in it
    // has the focus; a button's focus moves to the same button. What was typed and not saved stays (SF.drafts), and a
    // note whose file changed under it says so (sfStale), its 読み直す dropping what was typed.
    const hand = n.el.contains(document.activeElement) ? document.activeElement : null;
    if (sig !== n.sig && !(hand && hand.matches('select, input, textarea'))) {
      const said = (n.el.querySelector('.sf-note-said') || {}).textContent || '';
      const open = [...n.el.querySelectorAll('details')].map((x) => x.className + (x.open ? ':open' : ''));
      const again = hand ? sfFocusKey(hand) : '';
      n.el.innerHTML = sfNoteHTML(t, s);
      if (said) setText(n.el.querySelector('.sf-note-said'), said);
      for (const x of n.el.querySelectorAll('details')) if (open.includes(`${x.className}:open`)) x.open = true;
      if (again) { const to = n.el.querySelector(again) || n.el.querySelector('[data-sf-prompt-open]'); if (to) to.focus({ preventScroll: true }); }
      else if (hand === n.el) n.el.focus({ preventScroll: true });
      n.sig = sig;
    }
  });
  for (const k of SF_LANES) {
    const lane = wb.querySelector(`[data-sf-lane="${CSS.escape(k)}"]`);
    setText(lane.querySelector('.sf-lane-n'), String(lane.querySelectorAll('.sf-note').length));
  }
  setText($('sf-board-empty'), tasks.length ? '' : tl('sf.board.empty'));
  sfApplyView();
}
async function sfPost(route, body) {
  if (typeof NET === 'undefined') return { ok: false, status: 0, error: tl('live.offline') };
  try {
    const res = await fetch(route, {
      method: 'POST', cache: 'no-store', credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'X-Jui-Viz-Token': NET.token },
      body: JSON.stringify(body),
    });
    return res.ok ? { ok: true, status: res.status } : { ok: false, status: res.status, error: (await res.text()).trim() };
  } catch (err) { return { ok: false, status: 0, error: tl('live.offline') }; }
}
async function sfNoteOp(note, op) {
  const id = note.dataset.sfTask, body = { id, op };
  const pick = note.querySelector('[data-sf-target]');
  if ((op === 'save' || op === 'start') && note.querySelector('[data-sf-prompt-open]') && sfEditable(id)) body.prompt = sfPromptOf(id);
  if ((op === 'save' || op === 'start') && pick) {
    const s = sfSlice(), t = s && sfTasks(s).find((x) => x.id === id);
    body.target = pick.value ? { sessionId: pick.value } : { sessionName: (t && t.target && t.target.sessionName) || '', sessionId: null };
  }
  for (const b of note.querySelectorAll('button')) b.disabled = true;
  const got = await sfPost('/api/slack-room/task', body);
  for (const b of note.querySelectorAll('button')) b.disabled = false;
  const said = note.querySelector('.sf-note-said');
  if (got.ok) {
    delete SF.drafts[id];
    setText(said, SF_SAID[op] || '');
    if (document.activeElement && note.contains(document.activeElement)) document.activeElement.blur();
    const s = sfSlice(); if (s) sfRenderBoard(s);
  } else setText(said, tl('sf.failed', { error: got.error || String(got.status) }));
}

/* ---------- the whole board at once (requester 11-02: the whole board seen at once): the board takes the room, and
   shrinks until every lane and note is in view; Esc or the button again goes back. ---------- */
/* The board's views (the requester, 11-02): the room's (beside the 3D); the whole board (ボード全体: the six lanes over the
   room, nothing shrunk, sized to read); one lane (its heading pressed, or a note: its notes side by side), a note
   selected in it (← → the next lane's, ↑ ↓ the lane's next note; Esc a step back). */
function sfView(full, lane = null, sel = null) {
  SF.full = !!full;
  SF.lane = SF.full && lane ? lane : null;
  SF.sel = SF.lane && sel ? sel : null;
  sfEl.dataset.board = !SF.full ? '' : SF.lane ? 'lane' : 'full';
  setText($('sf-full'), SF.full ? tl('sf.full.back') : tl('sf.full'));
  sfApplyView();
  const note = SF.sel && SF.notes.get(SF.sel);
  if (note) { note.el.focus({ preventScroll: true }); note.el.scrollIntoView({ block: 'nearest', inline: 'nearest' }); }
}
function sfFull(on) { sfView(on); }
function sfApplyView() {
  const wb = $('sf-wb');
  const picked = SF.sel && SF.notes.get(SF.sel);
  if (SF.sel && !picked) SF.sel = null;                                   // the note went (purged)
  if (picked && picked.el.dataset.status !== SF.lane) SF.lane = picked.el.dataset.status;   // its state changed: the lane follows
  for (const lane of wb.querySelectorAll('.sf-lane')) {
    lane.hidden = !!SF.lane && lane.dataset.sfLane !== SF.lane;
  }
  for (const [id, n] of SF.notes) {
    const on = id === SF.sel;
    n.el.classList.toggle('is-selected', on);
    n.el.tabIndex = -1;   // focused from the keys, not a Tab stop
    if (on) n.el.setAttribute('aria-current', 'true'); else n.el.removeAttribute('aria-current');
  }
}
/* A lane's notes, top to bottom. */
function sfNotesOf(k) { return [...$('sf-wb').querySelectorAll('[data-sf-lane="' + CSS.escape(k) + '"] .sf-note')]; }   // a selector, not HTML
/* ← → ↑ ↓ while a note is selected. */
function sfStep(key) {
  if (key === 'ArrowLeft' || key === 'ArrowRight') {
    const dir = key === 'ArrowRight' ? 1 : -1;
    for (let i = SF_LANES.indexOf(SF.lane) + dir; i >= 0 && i < SF_LANES.length; i += dir) {
      const first = sfNotesOf(SF_LANES[i])[0];
      if (first) { sfView(true, SF_LANES[i], first.dataset.sfTask); return; }   // an empty lane is passed over
    }
    return;
  }
  const list = sfNotesOf(SF.lane), k = list.findIndex((n) => n.dataset.sfTask === SF.sel);
  const next = list[Math.max(0, Math.min(list.length - 1, k + (key === 'ArrowDown' ? 1 : -1)))];
  if (next) sfView(true, SF.lane, next.dataset.sfTask);
}

/* ---------- a task's messages as a chat (requester 11-02: like the robot's history, beside the board; who, when and
   the text in bubbles, thread by thread, each with its Slack link; Esc and x close it). Read when opened (POST
   /api/slack-room/messages), the whole text; a message added while it is open shows at its next opening. ---------- */
const sfTs = (ts) => { const n = Number(ts); return n > 0 ? new Date(n * 1000) : null; };
function sfChatRowHTML(m, k, rows) {
  const at = sfTs(m.ts), newThread = k === 0 || rows[k - 1].threadTs !== m.threadTs, reply = m.threadTs && m.threadTs !== m.ts;
  const when = at ? `${at.toLocaleDateString()} ${at.toTimeString().slice(0, 5)}` : '';
  return (newThread && k > 0 ? `<li class="sf-chat-sep" aria-hidden="true"></li>` : '')
    + `<li class="sf-bubble${reply ? ' sf-reply' : ''}"><p class="sf-bubble-head"><b>${esc(m.user || '?')}</b> <span>${esc(m.channel)}</span> <time>${esc(when)}</time></p>`
    + `<p class="sf-bubble-text">${esc(m.text)}</p>`
    + (m.permalink ? `<a class="sf-bubble-link" href="${esc(m.permalink)}" target="_blank" rel="noopener noreferrer">${esc(tl('sf.chat.open'))}</a>` : '') + '</li>';
}
async function sfChatOpen(id, opener) {
  SF.chatOpener = opener || null;
  const panel = $('sf-chat');
  setText($('sf-chat-title'), id);
  $('sf-chat-list').innerHTML = '';
  panel.hidden = false;
  $('sf-chat-close').focus({ preventScroll: true });
  const got = typeof NET === 'undefined' ? null : await fetch('/api/slack-room/messages', {
    method: 'POST', cache: 'no-store', credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json', 'X-Jui-Viz-Token': NET.token }, body: JSON.stringify({ id }),
  }).then((r) => (r.ok ? r.json() : null)).catch(() => null);
  if (panel.hidden) return;
  if (!got) { $('sf-chat-list').innerHTML = `<li class="sf-why">${esc(tl('sf.chat.failed'))}</li>`; return; }
  setText($('sf-chat-title'), `${got.id} ${got.title}`);
  const rows = Array.isArray(got.messages) ? got.messages : [];
  const rowsHTML = rows.map((m, k) => sfChatRowHTML(m, k, rows)).join('')
    + (Array.isArray(got.missing) && got.missing.length ? `<li class="sf-why">${esc(tl('sf.chat.missing', { n: got.missing.length }))}</li>` : '');
  $('sf-chat-list').innerHTML = rowsHTML;
}
function sfChatClose(back = true) {
  if ($('sf-chat').hidden) return false;
  $('sf-chat').hidden = true;
  const to = SF.chatOpener; SF.chatOpener = null;
  if (back && to && document.contains(to)) to.focus({ preventScroll: true });
  return true;
}
/* The folder in the header: as ~ when it is under the home; a long one cut in the middle, the whole on hover. */
function sfShortPath(p, max = 52) {
  const t = String(p || '');
  return t.length <= max ? t : `${t.slice(0, Math.floor(max * 0.4))}…${t.slice(t.length - Math.ceil(max * 0.6) + 1)}`;
}

/* ---------- asking the robot to change a note (requester 11-02: a popup with a wide box, which note at its head, the
   focus in the box; Cmd/Ctrl+Enter sends, Esc and x close; sent: closed, and the note says so) ---------- */
function sfReviseOpen(note, opener) {
  const s = sfSlice(), t = s && sfTasks(s).find((x) => x.id === note.dataset.sfTask);
  SF.revise = { id: note.dataset.sfTask, opener };
  setText($('sf-revise-h'), tl('sf.revise.head', { id: SF.revise.id, title: String((t && t.title) || '') }));
  setText($('sf-revise-said'), '');
  $('sf-revise').hidden = false;
  $('sf-revise-text').focus({ preventScroll: true });
}
function sfReviseClose(back = true) {
  if ($('sf-revise').hidden) return false;
  $('sf-revise').hidden = true;
  const to = SF.revise && SF.revise.opener; SF.revise = null;
  if (back && to && document.contains(to)) to.focus({ preventScroll: true });
  return true;
}
async function sfReviseSend() {
  const text = $('sf-revise-text').value;
  if (!SF.revise || !text.trim()) return;
  const id = SF.revise.id;
  $('sf-revise-send').disabled = true;
  const got = await sfPost('/api/slack-room/task', { id, op: 'revise', text });
  $('sf-revise-send').disabled = false;
  if (!got.ok) { setText($('sf-revise-said'), tl('sf.failed', { error: got.error || String(got.status) })); return; }
  $('sf-revise-text').value = '';
  sfReviseClose();
  const note = $('sf-wb').querySelector(`[data-sf-task="${CSS.escape(id)}"] .sf-note-said`);
  if (note) setText(note, SF_SAID.revise);
}

/* ---------- a task's prompt, large (the note shows its first lines only) ---------- */
function sfTaskOf(id) { const s = sfSlice(); return (s && sfTasks(s).find((x) => x.id === id)) || null; }
function sfEditable(id) { const t = sfTaskOf(id); return !!t && (t.status === 'talking' || t.status === 'draft' || t.status === 'ready'); }
/* What the task's prompt is now on this page: what was typed in the popup, else the file's. */
function sfPromptOf(id) {
  const d = SF.drafts[id] || {}, t = sfTaskOf(id);
  return d.prompt !== undefined ? d.prompt : t && typeof t.prompt === 'string' ? t.prompt : '';
}
function sfEditOpen(note, opener) {
  const id = note.dataset.sfTask, t = sfTaskOf(id), edit = sfEditable(id);
  SF.edit = { id, opener };
  setText($('sf-edit-h'), tl('sf.edit.head', { id, title: String((t && t.title) || '') }));
  setText($('sf-edit-label'), tl(edit ? 'sf.edit.label' : 'sf.edit.label.read'));
  const area = $('sf-edit-text');
  area.value = sfPromptOf(id);
  area.readOnly = !edit;
  area.placeholder = t && t.status === 'talking' ? tl('sf.note.talking') : '';
  setText($('sf-edit-save'), tl('sf.op.save'));
  $('sf-edit-save').hidden = !edit;
  setText($('sf-edit-said'), '');
  $('sf-edit').hidden = false;
  area.focus({ preventScroll: true });
  area.setSelectionRange(0, 0);
  area.scrollTop = 0;
}
function sfEditClose(back = true) {
  if ($('sf-edit').hidden) return false;
  $('sf-edit').hidden = true;
  const ed = SF.edit; SF.edit = null;
  // the note's first lines follow what was typed (kept until 保存 or 開始 sends it)
  const s = sfSlice(), t = ed && sfTaskOf(ed.id), n = ed && SF.notes.get(ed.id);
  if (s && t && n) { n.el.innerHTML = sfNoteHTML(t, s); n.sig = ''; }
  const to = ed && n ? n.el.querySelector('[data-sf-prompt-open]') : ed && ed.opener;
  if (back && to && document.contains(to)) to.focus({ preventScroll: true });
  if (s) sfRenderBoard(s);
  return true;
}
async function sfEditSave() {
  const ed = SF.edit; if (!ed || !sfEditable(ed.id)) return;
  const note = SF.notes.get(ed.id), pick = note && note.el.querySelector('[data-sf-target]'), t = sfTaskOf(ed.id);
  const body = { id: ed.id, op: 'save', prompt: $('sf-edit-text').value };
  if (pick) body.target = pick.value ? { sessionId: pick.value } : { sessionName: (t && t.target && t.target.sessionName) || '', sessionId: null };
  $('sf-edit-save').disabled = true;
  const got = await sfPost('/api/slack-room/task', body);
  $('sf-edit-save').disabled = false;
  if (!got.ok) { setText($('sf-edit-said'), tl('sf.failed', { error: got.error || String(got.status) })); return; }
  if (SF.drafts[ed.id]) { delete SF.drafts[ed.id].prompt; delete SF.drafts[ed.id].promptBase; if (SF.drafts[ed.id].sessionId === undefined) delete SF.drafts[ed.id]; }
  sfEditClose();
  const said = note && note.el.querySelector('.sf-note-said');
  if (said) setText(said, SF_SAID.save);
}

/* ---------- the two prompts (slack.json's router.prompt and taskPrompt) ---------- */
function sfProjectRowHTML(id, text) {
  return `<li class="sf-proj"><input type="text" data-sf-proj-id value="${esc(id)}" aria-label="${esc(tl('sf.prompts.project.id'))}">`
    + `<textarea data-sf-proj-text rows="2" aria-label="${esc(tl('sf.prompts.project.text'))}">${esc(text)}</textarea>`
    + `<button type="button" class="wb-btn" data-sf-proj-del aria-label="${esc(tl('sf.prompts.project.del'))}">×</button></li>`;
}
function sfPromptsOpen() {
  const s = sfSlice(); if (!s) return;
  const p = s.prompts || {};
  $('sf-p-instructions').value = String(p.instructions || '');
  $('sf-p-chitchat').value = String(p.chitchat || '');
  $('sf-p-task').value = String(p.taskPrompt || '');
  const rows = Object.entries(p.projects && typeof p.projects === 'object' ? p.projects : {});
  const rowsHTML = rows.map(([id, text]) => sfProjectRowHTML(id, String(text))).join('');
  $('sf-p-projects').innerHTML = rowsHTML;
  setText($('sf-p-said'), tl('sf.prompts.where', { path: String((s.config && s.config.path) || '') }));
  $('sf-prompts').hidden = false;
  $('sf-prompts-btn').setAttribute('aria-expanded', 'true');
  $('sf-p-instructions').focus({ preventScroll: true });
}
function sfPromptsClose(back = true) {
  if ($('sf-prompts').hidden) return;
  $('sf-prompts').hidden = true;
  $('sf-prompts-btn').setAttribute('aria-expanded', 'false');
  if (back) $('sf-prompts-btn').focus({ preventScroll: true });
}
async function sfPromptsSave() {
  const projects = {};
  for (const li of $('sf-p-projects').querySelectorAll('.sf-proj')) {
    const id = li.querySelector('[data-sf-proj-id]').value.trim();
    if (id) projects[id] = li.querySelector('[data-sf-proj-text]').value;
  }
  const got = await sfPost('/api/slack-room/prompts', { instructions: $('sf-p-instructions').value, chitchat: $('sf-p-chitchat').value,
    taskPrompt: $('sf-p-task').value, projects });
  setText($('sf-p-said'), got.ok ? tl('sf.prompts.saved') : tl('sf.failed', { error: got.error || String(got.status) }));
}

/* ---------- the factory in 3D ---------- */
function sfProjectColor(id) {
  let h = 0;
  for (const ch of String(id)) h = (h * 31 + ch.charCodeAt(0)) % 360;
  return `hsl(${h}, 62%, ${isDark() ? 58 : 46}%)`;
}
function sfBuild() {
  sfDispose();
  const cv = $('sf-canvas');
  const renderer = SF.renderer || (SF.renderer = new THREE.WebGLRenderer({ canvas: cv, antialias: true }));
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  const dark = isDark();
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(dark ? '#0f1b2d' : '#dfe6ef');
  scene.add(new THREE.HemisphereLight(0xffffff, 0x445566, 1.5));
  const sun = new THREE.DirectionalLight(0xffffff, 1.1); sun.position.set(6, 14, 9); scene.add(sun);
  const camera = new THREE.PerspectiveCamera(42, 1, 0.1, 200);
  camera.position.set(1.2, 8.2, 12.5);
  const controls = new OrbitControls(camera, cv);
  Object.assign(controls, { enableDamping: !reduceMotion, dampingFactor: 0.12, minDistance: 6, maxDistance: 40, maxPolarAngle: Math.PI * 0.47 });
  controls.target.set(1.4, 0.4, 0.2);
  const mat = (c) => new THREE.MeshToonMaterial({ color: c, gradientMap });
  const floor = new THREE.Mesh(new THREE.BoxGeometry(18, 0.2, 11), mat(dark ? '#1c2a40' : '#c9cfd6')); floor.position.set(1, -0.1, 0); scene.add(floor);
  const wall = new THREE.Mesh(new THREE.BoxGeometry(18, 4, 0.2), mat(dark ? '#22344f' : '#e8e2d6')); wall.position.set(1, 2, -4.6); scene.add(wall);
  // the hazard stripe along the floor in front of the belt
  const stripe = new THREE.Mesh(new THREE.BoxGeometry(SF_BELT.to - SF_BELT.from + 1, 0.02, 0.18), mat('#f2b705')); stripe.position.set((SF_BELT.from + SF_BELT.to) / 2, 0.01, 1.05); scene.add(stripe);
  // the chute the messages drop from, the belt with its legs and rollers, the sorting table
  const chute = new THREE.Mesh(new THREE.BoxGeometry(1.4, 1.2, 1.4), mat(dark ? '#5d6b80' : '#8796aa')); chute.position.set(SF_BELT.from - 0.4, 2.3, 0); scene.add(chute);
  const hopper = new THREE.Mesh(new THREE.CylinderGeometry(0.75, 0.35, 0.8, 4, 1, true), mat(dark ? '#4a576b' : '#9aa7b8')); hopper.position.set(SF_BELT.from - 0.4, 1.35, 0); hopper.rotation.y = Math.PI / 4; scene.add(hopper);
  const beltLen = SF_BELT.to - SF_BELT.from;
  const belt = new THREE.Mesh(new THREE.BoxGeometry(beltLen, 0.16, 1.3), mat('#2b2f36')); belt.position.set((SF_BELT.from + SF_BELT.to) / 2, SF_BELT.y - 0.08, SF_BELT.z); scene.add(belt);
  for (const side of [-0.7, 0.7]) {
    const rail = new THREE.Mesh(new THREE.BoxGeometry(beltLen, 0.22, 0.08), mat('#f2b705')); rail.position.set(belt.position.x, SF_BELT.y, side); scene.add(rail);
  }
  const rollers = [];
  for (let x = SF_BELT.from + 0.3; x < SF_BELT.to; x += 0.7) {
    const leg = new THREE.Mesh(new THREE.BoxGeometry(0.12, SF_BELT.y - 0.1, 0.12), mat('#59606b'));
    leg.position.set(x, (SF_BELT.y - 0.1) / 2, 0.55); scene.add(leg);
    const leg2 = leg.clone(); leg2.position.z = -0.55; scene.add(leg2);
    const roller = new THREE.Mesh(new THREE.CylinderGeometry(0.07, 0.07, 1.3, 10), mat('#8b939e')); roller.rotation.x = Math.PI / 2; roller.position.set(x, SF_BELT.y - 0.2, 0); scene.add(roller); rollers.push(roller);
  }
  const table = new THREE.Mesh(new THREE.BoxGeometry(1.8, 0.82, 1.6), mat(dark ? '#6b5a48' : '#b38b62')); table.position.set(1.4, 0.41, 0); scene.add(table);
  const view = { renderer, scene, camera, controls, rollers, bins: new Map(), mat, robot: null, robotLabel: '', raf: 0, last: performance.now(), t0: performance.now() };
  view.ro = new ResizeObserver(() => sfResize(view)); view.ro.observe(cv.parentElement);
  SF.view = view;
  SF.parcels = [];
  sfResize(view);
  const loop = (now) => { view.raf = requestAnimationFrame(loop); sfFrame(view, now); };
  view.raf = requestAnimationFrame(loop);
}
/* The camera back far enough for the whole line (chute to the last bin, SF_SPAN wide) in the canvas's shape, along the
   same slant; a resize sets it again. */
const SF_SPAN = { w: 15.5, h: 7.5 }, SF_LOOK = new THREE.Vector3(0, 8.2, 12.3).normalize();
function sfResize(V) {
  const box = $('sf-canvas').parentElement, w = Math.max(1, box.clientWidth), h = Math.max(1, box.clientHeight);
  V.renderer.setSize(w, h, false); V.camera.aspect = w / h; V.camera.updateProjectionMatrix();
  const t = Math.tan((V.camera.fov * Math.PI) / 360), dist = Math.max(SF_SPAN.h / (2 * t), SF_SPAN.w / (2 * t * V.camera.aspect));
  V.camera.position.copy(V.controls.target).addScaledVector(SF_LOOK, Math.min(dist, V.controls.maxDistance));
}
function sfDispose() {
  const V = SF.view;
  if (!V) return;
  cancelAnimationFrame(V.raf);
  V.ro.disconnect();
  V.controls.dispose();
  if (V.robot) sfRobotDrop(V);
  V.scene.traverse((o) => { if (o.geometry && !o.userData.shared) o.geometry.dispose(); if (o.material && !o.userData.shared) for (const m of [].concat(o.material)) m.dispose(); });
  V.renderer.renderLists.dispose();
  $('sf-labels').innerHTML = '';
  SF.view = null;
  SF.parcels = [];
}
/* A bin per project, in the order they came (at most SF_BIN_MAX; more share the last as その他). */
function sfBinFor(V, project) {
  const ids = [...V.bins.keys()];
  if (!V.bins.has(project) && ids.length >= SF_BIN_MAX) return V.bins.get(ids[ids.length - 1]);
  if (V.bins.has(project)) return V.bins.get(project);
  const k = ids.length, x = 3.3 + (k % 3) * 2.2, z = -1.4 + Math.floor(k / 3) * 3.0;
  const color = new THREE.Color(sfProjectColor(project));
  const g = new THREE.Group(); g.position.set(x, 0, z);
  const body = new THREE.Mesh(new THREE.BoxGeometry(1.4, 1.0, 1.4), V.mat(color)); body.position.y = 0.5; g.add(body);
  const lip = new THREE.Mesh(new THREE.BoxGeometry(1.5, 0.08, 1.5), V.mat(color.clone().multiplyScalar(0.7))); lip.position.y = 1.02; g.add(lip);
  V.scene.add(g);
  const tag = document.createElement('div'); tag.className = 'sf-tag'; $('sf-labels').appendChild(tag);
  const bin = { project, group: g, tag, n: 0, stack: [] };
  V.bins.set(project, bin);
  return bin;
}
function sfParcel(V, color) {
  const g = new THREE.Group();
  const box = new THREE.Mesh(new THREE.BoxGeometry(0.5, 0.36, 0.42), V.mat('#c89a5e')); g.add(box);
  const tape = new THREE.Mesh(new THREE.BoxGeometry(0.52, 0.06, 0.44), V.mat(color)); tape.position.y = 0.05; g.add(tape);
  V.scene.add(g);
  return g;
}
/* The bins' contents follow the counts; a message not seen before rides the belt (the first render only fills the bins). */
function sfSync(s) {
  const V = SF.view;
  if (!V) return;
  const a = s.arrivals || {}, by = a.byProject && typeof a.byProject === 'object' ? a.byProject : {};
  for (const [p, n] of Object.entries(by)) {
    const bin = sfBinFor(V, p);
    bin.n = Number(n) || 0;
    const want = Math.min(5, bin.n - SF.parcels.filter((x) => x.bin === bin).length);
    while (bin.stack.length > Math.max(0, want)) V.scene.remove(bin.stack.pop());
    while (bin.stack.length < want) {
      const k = bin.stack.length, parcel = sfParcel(V, new THREE.Color(sfProjectColor(p)));
      parcel.position.set(bin.group.position.x + ((k % 2) - 0.5) * 0.5, 0.3 + Math.floor(k / 2) * 0.38, bin.group.position.z + ((k % 3) - 1) * 0.2);
      parcel.rotation.y = k * 0.7;
      bin.stack.push(parcel);
    }
    setText(bin.tag, tl('sf.bin', { project: bin.project, n: bin.n }));
  }
  const recent = Array.isArray(a.recent) ? a.recent : [];
  const paths = recent.map((r) => String(r.path || ''));
  if (SF.seen === null) { SF.seen = new Set(paths); return; }
  for (const r of recent.slice().reverse()) {
    const path = String(r.path || '');
    if (!path || SF.seen.has(path)) continue;
    SF.seen.add(path);
    if (reduceMotion || SF.parcels.length > 12) continue;
    const bin = sfBinFor(V, String(r.projectId || ''));
    const g = sfParcel(V, new THREE.Color(sfProjectColor(String(r.projectId || ''))));
    g.position.set(SF_BELT.from - 0.4, 2.0, 0);
    SF.parcels.push({ g, bin, phase: 'drop', t: 0, delay: SF.parcels.length * 0.9 });
  }
}
function sfFrame(V, now) {
  const dt = Math.min(0.1, (now - V.last) / 1000); V.last = now;
  const t = (now - V.t0) / 1000;
  V.controls.update();
  for (const r of V.rollers) r.rotation.y += dt * (reduceMotion ? 0 : 6);
  const s = sfSlice();
  sfRobotTick(V, s, t, dt);
  for (const p of SF.parcels.slice()) {
    if (p.delay > 0) { p.delay -= dt; continue; }
    p.t += dt;
    if (p.phase === 'drop') {
      p.g.position.y = Math.max(SF_BELT.y + 0.18, 2.0 - p.t * p.t * 5);
      if (p.g.position.y <= SF_BELT.y + 0.18) { p.phase = 'belt'; p.t = 0; }
    } else if (p.phase === 'belt') {
      p.g.position.x += dt * SF_BELT.speed;
      if (p.g.position.x >= SF_BELT.to + 0.6) { p.phase = 'sort'; p.t = 0; p.from = p.g.position.clone(); }
    } else if (p.phase === 'sort') {
      const u = Math.min(1, p.t / 0.9), to = p.bin.group.position;
      p.g.position.set(p.from.x + (to.x - p.from.x) * u, p.from.y + Math.sin(u * Math.PI) * 1.6 + (1.1 - p.from.y) * u, p.from.z + (to.z - p.from.z) * u);
      p.g.rotation.y += dt * 4;
      if (u >= 1) { V.scene.remove(p.g); SF.parcels.splice(SF.parcels.indexOf(p), 1); if (s) sfSync(s); }
    }
  }
  sfPlaceTags(V);
  V.renderer.render(V.scene, V.camera);
}
/* The one robot: the factory session's own state (robotState, from the agents slice), standing at the table. */
function sfRobotTick(V, s, t, dt) {
  const label = s ? sfRobotLabel(s) : '';
  if (label !== V.robotLabel) {
    if (V.robot) sfRobotDrop(V);
    V.robotLabel = label;
    if (label) {
      const def = DEF[label];
      V.robot = createRobot({ label, role: (def && def.role) || 'main', state: 'idle', seed: 2.1, furnished: false });
      V.robot.root.position.set(1.4, 0, -1.25);
      V.robot.root.rotation.y = 0;
      V.robot.root.traverse((o) => { o.userData.shared = true; });
      V.scene.add(V.robot.root);
    }
  }
  if (!V.robot) return;
  const st = robotState[label] || { state: 'idle' };
  const busy = SF.parcels.some((p) => p.phase === 'sort');
  const want = busy && st.state === 'idle' ? 'command' : st.state;
  if (want !== V.robot.state) setRobotState(V.robot, want);
  updateRobot(V.robot, t, dt);
}
function sfRobotDrop(V) {
  V.scene.remove(V.robot.root);
  const k = fontRedraws.indexOf(V.robot.fontRedraw);
  if (k >= 0) fontRedraws.splice(k, 1);
  V.robot = null;
}
function sfPlaceTags(V) {
  const box = $('sf-canvas').getBoundingClientRect(), v = new THREE.Vector3(), placed = [];
  for (const bin of V.bins.values()) {
    v.set(bin.group.position.x, 1.5, bin.group.position.z).project(V.camera);
    const on = v.z < 1 && Math.abs(v.x) < 1.1 && Math.abs(v.y) < 1.1;
    bin.tag.hidden = !on;
    if (!on) continue;
    // over its bin; lifted above any tag already placed that it would cover (neighbours never hide each other's names)
    const w = bin.tag.offsetWidth, h = bin.tag.offsetHeight, x = Math.round((v.x + 1) / 2 * box.width) - w / 2;
    let y = Math.round((1 - v.y) / 2 * box.height) - h;
    for (let moved = true; moved;) {
      moved = false;
      for (const p of placed) if (x < p.x + p.w + 2 && p.x < x + w + 2 && y < p.y + p.h + 2 && p.y < y + h + 2) { y = p.y - h - 2; moved = true; }
    }
    placed.push({ x, y, w, h });
    bin.tag.style.transform = `translate(${Math.round(x)}px, ${Math.round(y)}px)`;
  }
}

/* The theme changed while the room is open: built again in its colours (the parcels on their way start over). */
function sfRetheme() { if (SF.open) { sfBuild(); const s = sfSlice(); SF.seen = null; if (s) sfSync(s); } }
if (window.matchMedia) window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', sfRetheme);
new MutationObserver(sfRetheme).observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });

/* ---------- wiring ---------- */
$('btn-slack').addEventListener('click', (e) => (SF.open ? sfClose() : sfOpen(e.currentTarget)));
$('sf-back').addEventListener('click', () => sfClose());
$('sf-full').addEventListener('click', () => sfFull(!SF.full));
$('sf-chat-close').addEventListener('click', () => sfChatClose());
$('sf-edit-close').addEventListener('click', () => sfEditClose());
$('sf-edit-save').addEventListener('click', sfEditSave);
$('sf-edit-text').addEventListener('input', (e) => {
  if (!SF.edit || e.target.readOnly) return;
  sfDraft(SF.edit.id).prompt = e.target.value;
});
$('sf-edit-text').addEventListener('keydown', (e) => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) { e.preventDefault(); sfEditSave(); } });
$('sf-revise-close').addEventListener('click', () => sfReviseClose());
$('sf-revise-send').addEventListener('click', sfReviseSend);
$('sf-revise-text').addEventListener('keydown', (e) => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) { e.preventDefault(); sfReviseSend(); } });
$('sf-send').addEventListener('click', sfSend);
$('sf-fetch').addEventListener('click', sfFetch);
document.querySelector('#sf .sf-tabs').addEventListener('click', (e) => { const b = e.target.closest('[data-sf-tab]'); if (b) sfTab(b.dataset.sfTab); });
document.querySelector('#sf .sf-tabs').addEventListener('keydown', (e) => {
  if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight' && e.key !== 'Home' && e.key !== 'End') return;
  e.preventDefault(); e.stopPropagation();
  const now = document.querySelector('#sf .sf-tab[aria-selected="true"]').dataset.sfTab;
  sfTab(e.key === 'Home' ? 'talk' : e.key === 'End' ? 'flow' : now === 'talk' ? 'flow' : 'talk', true);
});
sfTab(sfTabSaved());
$('sf-say').addEventListener('keydown', (e) => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) { e.preventDefault(); sfSend(); } });
$('sf-prompts-btn').addEventListener('click', () => ($('sf-prompts').hidden ? sfPromptsOpen() : sfPromptsClose()));
$('sf-p-close').addEventListener('click', () => sfPromptsClose());
$('sf-p-save').addEventListener('click', sfPromptsSave);
$('sf-p-add').addEventListener('click', () => { $('sf-p-projects').insertAdjacentHTML('beforeend', sfProjectRowHTML('', '')); $('sf-p-projects').lastElementChild.querySelector('input').focus(); });
$('sf-p-projects').addEventListener('click', (e) => { const del = e.target.closest('[data-sf-proj-del]'); if (del) del.closest('.sf-proj').remove(); });
sfEl.addEventListener('keydown', (e) => {
  if (['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(e.key)) {
    // a field, a select, the tabs and the popups keep their arrows; the floors' arrows never run under the room (aria-modal)
    const t = e.target;
    if (!SF.sel || e.altKey || e.ctrlKey || e.metaKey || e.shiftKey || e.isComposing) return;
    if (t && (t.isContentEditable || (t.closest && t.closest('input, textarea, select, [role="tablist"], .sf-modal, .sf-dialog, .sf-chat')))) return;
    e.preventDefault(); e.stopPropagation();
    sfStep(e.key);
    return;
  }
  if (e.key !== 'Escape') return;
  e.preventDefault(); e.stopPropagation();
  if (!$('sf-prompts').hidden) sfPromptsClose(); else if (sfEditClose() || sfReviseClose() || sfChatClose()) return;
  else if (SF.sel) sfView(true, SF.lane); else if (SF.lane) sfView(true); else if (SF.full) sfFull(false); else sfClose();
});
sfEl.addEventListener('click', async (e) => {
  const copy = e.target.closest('[data-sf-copy]');
  if (copy) {
    try { await navigator.clipboard.writeText(copy.dataset.sfCopy); setText(copy, tl('sf.copied')); } catch (err) { setText(copy, tl('sf.copy.failed')); }
    setTimeout(() => setText(copy, copy.dataset.sfLabel || tl('sf.copy')), 1600);
    return;
  }
  const chat = e.target.closest('[data-sf-chat]');
  if (chat) { sfChatOpen(chat.closest('.sf-note').dataset.sfTask, chat); return; }
  const rev = e.target.closest('[data-sf-revise-open]');
  if (rev) { sfReviseOpen(rev.closest('.sf-note'), rev); return; }
  const laneBtn = e.target.closest('[data-sf-lane-open]');
  if (laneBtn) { const k = laneBtn.dataset.sfLaneOpen; if (SF.lane === k) sfView(true); else sfView(true, k); return; }
  const reload = e.target.closest('[data-sf-reload]');
  if (reload) {
    const n = reload.closest('.sf-note'); delete SF.drafts[n.dataset.sfTask];
    const s = sfSlice(); if (s) sfRenderBoard(s);
    const to = n.querySelector('[data-sf-prompt-open]'); if (to) to.focus({ preventScroll: true });
    return;
  }
  const big = e.target.closest('[data-sf-prompt-open]');
  if (big) { sfEditOpen(big.closest('.sf-note'), big); return; }
  if (e.target === $('sf-revise')) { sfReviseClose(); return; }   // a press outside the box
  if (e.target === $('sf-edit')) { sfEditClose(); return; }
  const op = e.target.closest('[data-sf-op]');
  if (op) { sfNoteOp(op.closest('.sf-note'), op.dataset.sfOp); return; }
  // a press on a note's own surface (not one of its controls): its lane over the room, the note selected
  const card = e.target.closest('.sf-note');
  if (card && !e.target.closest('button, select, input, textarea, a, label, summary, code')) sfView(true, card.dataset.status, card.dataset.sfTask);
});
/* What is typed on a note is kept (a push redraws only a note no hand is on). */
$('sf-wb').addEventListener('input', (e) => {
  const note = e.target.closest('.sf-note'); if (!note) return;
  if (e.target.matches('[data-sf-target]')) sfDraft(note.dataset.sfTask).sessionId = e.target.value;
});
$('sf-wb').addEventListener('change', async (e) => {
  if (e.target.matches('[data-sf-status]')) {
    const note = e.target.closest('.sf-note');
    const got = await sfPost('/api/slack-room/task', { id: note.dataset.sfTask, op: 'status', status: e.target.value });
    if (document.activeElement === e.target) e.target.blur();   // the note may be drawn in its new lane now
    if (!got.ok) setText(note.querySelector('.sf-note-said'), tl('sf.failed', { error: got.error || String(got.status) }));
    const s = sfSlice(); if (s) sfRenderBoard(s);
    return;
  }
  const note = e.target.closest('.sf-note'); if (!note || !e.target.matches('[data-sf-target]')) return;
  sfDraft(note.dataset.sfTask).sessionId = e.target.value;
});
$('sf-wb').addEventListener('focusout', () => setTimeout(() => { const s = sfSlice(); if (SF.open && s) sfRenderBoard(s); }, 0));
setInterval(renderSlackButton, 1000);
setInterval(() => { for (const m of document.querySelectorAll('#sf-wb [data-sf-purge]')) setText(m, tl('sf.note.purge', { n: Math.max(0, Math.ceil((Number(m.dataset.sfPurge) - Date.now()) / 60000)) })); }, 15000);
renderSlackButton();
