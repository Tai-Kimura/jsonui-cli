/* ---------- a worktree's spec beside the spec it started from (2.3.23, ticket 2026-10-24-viz-worktree-spec-diff-against-base:
   the requester asked for a button that shows, full screen, the base on the left and the changes on the right) ----------
   One button in the whiteboard's head, #wb-diff, shown only for a worktree's spec or a worktree's list:
   - on a worktree's spec: the full-screen #sd, the base (where the branch left the room's checkout) on the left, the
     worktree's file on the right, row beside row, each row same / added / removed / changed (spec_diff.py pairs them);
   - on a worktree's list (the overview with the worktree's app chosen): marks each card +n −n ~n, and shows the specs
     the worktree deleted as faint cards, which open the same view (the left all removed). Pressed again, they go.
   git runs on the server only when one of these is pressed; a base it could not read is said, with why. */
const SD = { open: false, opener: null, seq: 0, only: false, got: null, title: '', branch: '', lists: {} };
const sdEl = $('sd'), sdBody = $('sd-body');
const sdIsWorktree = (s) => !!(s && s.checkout && s.checkout.worktree);
const sdListKey = (project, app) => `${project}|${app}`;
/* The worktree's app the overview shows, and its project, or null: the button belongs to a worktree's list only. */
function sdOverviewApp(model) {
  if (wb.app === 'all' || wb.app.indexOf('@') < 0) return null;
  const s = model.specs.find((x) => (x.app || '') === wb.app && inScope(x.project) && sdIsWorktree(x));
  return s ? { project: s.project, app: wb.app, branch: s.checkout.branch, worktree: s.checkout.worktree } : null;
}
/* The sessions working in a worktree now (ticket 2026-10-29-viz-spec-board-worktree-session-name; requester: 「これ差分ボタンの
   右に作成者のセッション名出せる？」): who made it is recorded nowhere, but a worktree is on the board only while a session not
   ended works there (ingest.py _worktrees_tick: its cwd, or a checkout its tools named within 30 minutes, session.touched) —
   those, by name, beside the button. */
function sdWorkers(worktree) {
  if (!worktree) return [];
  const w = String(worktree).replace(/\/+$/, '');
  return SESSIONS.filter((x) => x.status !== 'ended' && (x.cwd === w || x.cwd.startsWith(w + '/') || x.touched.includes(w)));
}
function sdWhoRender(worktree) {
  const el = $('wb-wt-who');
  const who = SOURCE.mode === 'live' ? sdWorkers(worktree) : [];
  const shown = who.slice(0, SD_WHO_MAX);
  const html = shown.map((x) => `<span class="sd-who-one">${pill(x.id, DEF[x.id] ? DEF[x.id].role : 'main')}<span class="sd-who-nm">${esc(x.title || tl('panel.rb.main', { id: x.id }))}</span></span>`).join('')
    + (who.length > shown.length ? `<span class="sd-who-more">${esc(tl('sd.who.more', { n: who.length - shown.length }))}</span>` : '');
  el.hidden = !who.length;
  el.title = who.length ? tl('sd.who.title') : '';
  setHTML(el, html);
}
const SD_WHO_MAX = 2;
/* The head's button: shown and named as the open sheet or the overview needs (renderSheet / renderOverview). */
function sdHeadButton(model, s) {
  const b = $('wb-diff');
  const live = SOURCE.mode === 'live';
  if (s) {
    b.hidden = !(live && sdIsWorktree(s));
    setText(b, tl('sd.button'));
    b.dataset.sdFor = 'spec';
    sdWhoRender(b.hidden ? null : s.checkout.worktree);
    return;
  }
  const ov = live ? sdOverviewApp(model) : null;
  b.hidden = !ov;
  sdWhoRender(ov ? ov.worktree : null);
  if (!ov) return;
  const st = SD.lists[sdListKey(ov.project, ov.app)];
  setText(b, !st || st.state === 'off' ? tl('sd.button') : st.state === 'loading' ? tl('sd.button.loading') : tl('sd.button.hide'));
  b.dataset.sdFor = 'list';
}
$('wb-diff').addEventListener('click', (e) => {
  const model = latestModel;
  if (e.currentTarget.dataset.sdFor === 'spec') {
    const s = model.specs[wb.idx];
    if (s) sdOpen({ specId: s.id }, s.name, s.checkout.branch, e.currentTarget);
    return;
  }
  const ov = sdOverviewApp(model);
  if (!ov) return;
  const key = sdListKey(ov.project, ov.app), st = SD.lists[key];
  if (st && st.state !== 'off') { SD.lists[key] = { state: 'off' }; renderWhiteboard(model, true); return; }
  SD.lists[key] = { state: 'loading' };
  renderWhiteboard(model, true);
  SOURCE.specDiffList({ project: ov.project, app: ov.app }).then((ack) => {
    if (SD.lists[key] && SD.lists[key].state === 'off') return;
    const d = ack.ok && ack.data ? ack.data.diff : null;
    SD.lists[key] = d && d.ok ? { state: 'ok', marks: d.marks || {}, deleted: Array.isArray(d.deleted) ? d.deleted : [], base: String(d.base || ''), branch: ov.branch }
      : { state: 'err', reason: d ? d.reason : (ack.error || 'offline'), detail: d ? String(d.detail || '') : '' };
    renderWhiteboard(latestModel, true);
  });
});
/* The overview's part (renderOverview): the list's state in its signature, a card's mark, and the deleted cards. */
function sdListState(model) {
  const ov = SOURCE.mode === 'live' ? sdOverviewApp(model) : null;
  return ov ? SD.lists[sdListKey(ov.project, ov.app)] || null : null;
}
function sdListSig(model) {
  const st = sdListState(model);
  return st ? [st.state, st.base || '', JSON.stringify(st.marks || {}), (st.deleted || []).length, st.reason || ''] : null;
}
function sdCountsHTML(m) {
  return `${m.add ? `<b class="sd-c-add">+${esc(m.add)}</b>` : ''}${m.del ? `<b class="sd-c-del">−${esc(m.del)}</b>` : ''}${m.chg ? `<b class="sd-c-chg">~${esc(m.chg)}</b>` : ''}`;
}
function sdCardMarkHTML(model, s) {
  const st = sdListState(model);
  if (!st || st.state !== 'ok') return '';
  const m = st.marks[s.id];
  if (!m) return '';
  if (m.isNew) return `<span class="sd-mark sd-m-new">${esc(tl('sd.mark.new'))}</span>`;
  if (!m.add && !m.del && !m.chg) return `<span class="sd-mark sd-m-same">${esc(tl('sd.mark.same'))}</span>`;
  return `<span class="sd-mark" aria-label="${esc(tl('sd.counts.aria', { add: m.add, del: m.del, chg: m.chg }))}">${sdCountsHTML(m)}</span>`;
}
function sdListHTML(model) {
  const st = sdListState(model);
  if (!st) return '';
  if (st.state === 'loading') return `<p class="sd-band">${esc(tl('sd.list.loading'))}</p>`;
  if (st.state === 'err') return `<p class="sd-band sd-band-err" role="status">${esc(tl('sd.unavailable', { why: sdReason(st.reason) }))}${st.detail ? ` <code>${esc(st.detail)}</code>` : ''}</p>`;
  if (st.state !== 'ok') return '';
  const headHTML = `<p class="sd-band">${esc(tl('sd.list.base', { sha: st.base.slice(0, 8), branch: st.branch }))}</p>`;
  if (!st.deleted.length) return headHTML;
  return `${headHTML}<section class="ov-group sd-gone-group" aria-label="${esc(tl('sd.list.deleted'))}"><h3>${esc(tl('sd.list.deleted'))}<small>${esc(st.deleted.length)}</small></h3><div class="ov-grid">${st.deleted.map((d, i) => `<button type="button" class="ov-card sd-gone" data-sd-gone="${i}"><span class="ov-top"><strong>${esc(d.name)}</strong><span class="sd-mark sd-m-gone">${esc(tl('sd.mark.deleted'))}</span></span><code class="ov-file">${esc(d.file)}</code></button>`).join('')}</div></section>`;
}
wbCode.addEventListener('click', (e) => {
  const g = e.target.closest('[data-sd-gone]');
  if (!g) return;
  const ov = sdOverviewApp(latestModel), st = sdListState(latestModel);
  const d = st && st.deleted ? st.deleted[Number(g.dataset.sdGone)] : null;
  if (ov && d) sdOpen({ project: ov.project, app: ov.app, deleted: d.file }, d.name, ov.branch, g);
});
const SD_REASONS = {
  'no-parent-head': 'sd.reason.no-parent-head', 'no-merge-base': 'sd.reason.no-merge-base', 'git-missing': 'sd.reason.git-missing',
  timeout: 'sd.reason.timeout', 'git-failed': 'sd.reason.git-failed', 'base-unreadable': 'sd.reason.base-unreadable',
  'worktree-unreadable': 'sd.reason.worktree-unreadable', 'not-a-worktree': 'sd.reason.not-a-worktree', 'unknown-spec': 'sd.reason.unknown-spec',
  'no-such-base-file': 'sd.reason.no-such-base-file', offline: 'sd.reason.offline',
};
const sdReason = (r) => tl(Object.prototype.hasOwnProperty.call(SD_REASONS, r) ? SD_REASONS[r] : 'sd.reason.other');

/* ---- the full-screen view ---- */
function sdOpen(req, name, branch, opener) {
  Object.assign(SD, { open: true, opener: opener || null, got: null, title: name, branch });
  const seq = ++SD.seq;
  sdEl.hidden = false;
  document.body.classList.add('sd-on');
  sdRender();
  $('sd-close').focus({ preventScroll: true });
  SOURCE.specDiff(req).then((ack) => {
    if (seq !== SD.seq || !SD.open) return;
    SD.got = ack.ok && ack.data ? ack.data.diff : { ok: false, reason: ack.error === 'offline' ? 'offline' : 'git-failed', detail: ack.error || '' };
    sdRender();
  });
}
function sdClose() {
  if (!SD.open) return;
  SD.open = false; SD.seq += 1;
  sdEl.hidden = true;
  document.body.classList.remove('sd-on');
  if (SD.opener && SD.opener.isConnected) SD.opener.focus({ preventScroll: true });
}
$('sd-close').addEventListener('click', sdClose);
sdEl.addEventListener('keydown', (e) => { if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); sdClose(); } });
$('sd-only').addEventListener('change', (e) => { SD.only = e.target.checked; sdRender(); });

const SD_SECTIONS = {
  metadata: 'panel.sec.overview', components: 'panel.sec.structure', uiVariables: 'sd.sec.vars', eventHandlers: 'sd.sec.events',
  vmMethods: 'sd.sec.methods', vmVars: 'sd.sec.vmvars', repositories: 'sd.sec.repos', apis: 'sd.sec.apis',
  userActions: 'panel.sec.actions', transitions: 'panel.sec.transitions', branches: 'panel.sec.branches', flowMermaid: 'sd.sec.flow',
};
const SD_STATES = { same: 'sd.state.same', add: 'sd.state.add', del: 'sd.state.del', chg: 'sd.state.chg' };
const SD_SIGNS = { same: '', add: '+', del: '−', chg: '~' };
const sdText = (v) => (v === null || v === undefined ? '' : typeof v === 'string' ? v : typeof v === 'object' && typeof v.markdown === 'string' ? v.markdown : JSON.stringify(v));
/* One row's cells as the sheet names them: [text, column] pieces (-1: a separator); a changed column is marked on both sides. */
function sdPieces(key, r) {
  if (!Array.isArray(r)) return [[sdText(r), 0]];
  const t = (i) => sdText(r[i]);
  switch (key) {
    case 'metadata': return [[`${t(0)}: `, -1], [Array.isArray(r[1]) ? r[1].join(', ') : t(1), 1]];
    case 'components': return [['  '.repeat(Number(r[3]) || 0), 3], [t(0), 0], [' ', -1], [t(1), 1], ...(r[2] && r[2] !== r[0] ? [[' — ', -1], [t(2), 2]] : [])];
    case 'uiVariables': return [[t(0), 0], [': ', -1], [t(1), 1], ...(t(2) ? [[' = ', -1], [t(2), 2]] : [])];
    case 'eventHandlers': return [[t(0), 0], [' — ', -1], [t(1), 1]];
    case 'apis': return [[t(1), 1], [' ', -1], [t(2), 2], [' — ', -1], [t(0), 0]];
    case 'userActions': return [[t(0), 0], [' → ', -1], [t(1), 1], [' → ', -1], [t(2), 2]];
    case 'transitions': return [[t(0), 0], [' → ', -1], [t(1), 1], [' (', -1], [t(2), 2], [')', -1]];
    case 'branches': return [[t(0), 0], [': ', -1], [t(1), 1], [' ⇒ ', -1], [t(2), 2]];
    default: return r.map((c, i) => [sdText(c), i]);
  }
}
function sdCellHTML(key, row, side) {
  const r = row[side];
  if (r === null || r === undefined) return `<div class="sd-cell sd-none" aria-hidden="true"></div>`;
  const cols = row.s === 'chg' ? new Set(row.cols || []) : null;
  const partsHTML = sdPieces(key, r).map(([t, c]) => (cols && c >= 0 && cols.has(c) ? `<mark class="sd-x">${esc(t)}</mark>` : esc(t))).join('');
  return `<div class="sd-cell${key === 'flowMermaid' ? ' sd-pre' : ''}"><span class="sd-sign" aria-hidden="true">${esc(SD_SIGNS[row.s] || '')}</span><span class="sd-t">${partsHTML}</span></div>`;
}
function sdSectionHTML(sec) {
  const rows = (sec.rows || []).filter((r) => !SD.only || r.s !== 'same');
  if (!rows.length) return '';
  const n = sec.counts || {};
  const tagHTML = n.add || n.del || n.chg ? `<small>${sdCountsHTML(n)}</small>` : '';
  return `<section class="sd-sec"><h3>${esc(tl(SD_SECTIONS[sec.key] || 'sd.sec.other'))}${tagHTML}</h3><div class="sd-rows">${rows.map((r) => `<div class="sd-row sd-${esc(r.s)}" role="group" aria-label="${esc(tl(SD_STATES[r.s] || 'sd.state.same'))}">${sdCellHTML(sec.key, r, 'l')}${sdCellHTML(sec.key, r, 'r')}</div>`).join('')}</div></section>`;
}
function sdRender() {
  if (!SD.open) return;
  const d = SD.got;
  setText($('sd-title'), tl('sd.title', { name: SD.title }));
  const counts = $('sd-counts');
  if (!d || !d.ok) {
    setText($('sd-sides'), '');
    setHTML(counts, '');
    setHTML(sdBody, !d ? `<p class="sd-band">${esc(tl('sd.loading'))}</p>`
      : `<p class="sd-band sd-band-err" role="status">${esc(tl('sd.unavailable', { why: sdReason(d.reason) }))}${d.detail ? ` <code>${esc(d.detail)}</code>` : ''}</p>`);
    return;
  }
  const c = d.counts || { add: 0, del: 0, chg: 0 };
  setText($('sd-sides'), tl('sd.sides', { sha: String(d.base || '').slice(0, 8), branch: SD.branch, file: d.file || '' }));
  setHTML(counts, `<b class="sd-c-add">+${esc(c.add)}</b><b class="sd-c-del">−${esc(c.del)}</b><b class="sd-c-chg">~${esc(c.chg)}</b>`);
  counts.setAttribute('aria-label', tl('sd.counts.aria', { add: c.add, del: c.del, chg: c.chg }));
  const headsHTML = `<div class="sd-cols-head"><div>${esc(tl('sd.left'))}${d.isNew ? `<span class="sd-note">${esc(tl('sd.left.new'))}</span>` : ''}</div><div>${esc(tl('sd.right'))}${d.isDeleted ? `<span class="sd-note">${esc(tl('sd.right.deleted'))}</span>` : ''}</div></div>`;
  const bandHTML = !c.add && !c.del && !c.chg ? `<p class="sd-band sd-band-same" role="status">${esc(tl('sd.none'))}</p>` : '';
  const secsHTML = (d.sections || []).map(sdSectionHTML).join('');
  setHTML(sdBody, `${bandHTML}${headsHTML}${secsHTML || `<p class="sd-band">${esc(tl('sd.only.none'))}</p>`}`);
}
