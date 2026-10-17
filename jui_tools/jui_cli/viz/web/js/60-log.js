
/* ---------- full-screen event log ---------- */
let logSeq = 0;
const logItems = [];
const CAT_LABEL = { tool: 'ツール', spec: 'spec', test: 'テスト', task: 'タスク', session: '許可・停止' };
const kindCat = (k) => (/^(Read|Edit|Write|Bash|MCP)$/.test(k) ? 'tool' : k === 'spec 更新' ? 'spec' : /^(case|retry)/.test(k) ? 'test' : /^Task/.test(k) ? 'task' : 'session');
/* Live events carry their category (plan 04 §2); the demo's are read from the kind. */
const catOf = (e) => e.cat || kindCat(e.kind);
function payloadFor(e) {
  if (SOURCE.mode === 'live') return e.detail === undefined ? { kind: e.kind, text: e.what } : e.detail;
  const cat = kindCat(e.kind), sess = SESSION_OF[e.who];
  if (e.kind === 'PermissionRequest' && e.perm) return permRequestPayload(PERM_BY_ID[e.perm]);
  if (e.decision) return { source: 'エージェントビュー → Claude Code（PermissionRequest フックへの応答）', ...permResponse(PERM_BY_ID[e.perm], e.decision, e.reason) };
  if (cat === 'spec') { const [file, section] = e.what.split(' › '); return { source: 'ファイル監視（可視化サーバー）', event: 'change', path: `docs/screens/json/${file}`, section }; }
  if (cat === 'test') return { source: 'jsonui-test-runner（追加予定の進捗出力）', file: 'tests/screens/cart.test.json', case: e.what, status: e.kind === 'retry' ? 'retrying' : e.kind.includes('✗') ? 'failed' : 'passed' };
  const p = { hook_event_name: cat === 'tool' ? 'PreToolUse' : e.kind, session_id: SESSION_UUID[sess], cwd: CWD[sess] };
  if (AGENT_ID[e.who]) { p.agent_id = AGENT_ID[e.who]; p.agent_type = DEF[e.who].agent; }
  if (['Read', 'Edit', 'Write'].includes(e.kind)) { p.tool_name = e.kind; p.tool_input = { file_path: `${CWD[sess]}/${e.what}` }; }
  else if (e.kind === 'Bash') { p.tool_name = 'Bash'; p.tool_input = { command: e.what }; }
  else if (e.kind === 'MCP') { const [server, tool, ...rest] = e.what.split(' '); p.tool_name = `mcp__${server}__${tool}`; p.tool_input = { target: rest.join(' ') }; }
  else if (e.kind === 'PermissionRequest') { p.tool_name = 'Bash'; p.tool_input = { command: e.what.replace(/^Bash /, '') }; }
  else if (e.kind === 'PostToolUse') { p.tool_name = ['a5', 'f2'].includes(e.who) ? 'mcp__jui-tools__jui_verify' : 'Bash'; p.tool_response = { summary: e.what }; }
  else if (e.kind.startsWith('Task')) { const m = e.what.match(/^#(\d+) (.*)$/); p.task_id = m ? m[1] : ''; p.task_subject = m ? m[2] : e.what; }
  else if (e.kind === 'Stop' || e.kind === 'SubagentStop') p.last_assistant_message = e.what;
  return p;
}
const logState = { open: false, cats: new Set(Object.keys(CAT_LABEL)), hiddenRobots: new Set(), q: '', expanded: new Set(), shownTop: null, opener: null };
const logOverlay = $('log-overlay'), logRows = $('log-rows'), logBody = $('log-body');
$('log-cats').innerHTML = Object.entries(CAT_LABEL).map(([k, v]) => `<button type="button" class="fbtn" data-cat="${k}" aria-pressed="true">${v}</button>`).join('');
function toggleIn(set, key, btn) { if (set.has(key)) set.delete(key); else set.add(key); btn.setAttribute('aria-pressed', String(set.has(key))); }
$('log-cats').addEventListener('click', (e) => { const b = e.target.closest('[data-cat]'); if (b) { toggleIn(logState.cats, b.dataset.cat, b); renderLog(true); } });
$('log-search').addEventListener('input', (e) => { logState.q = e.target.value.trim().toLowerCase(); renderLog(true); });
$('log-follow').addEventListener('change', () => renderLog(true));
$('log-more').addEventListener('click', () => { renderLog(true); logBody.scrollTop = 0; });
logRows.addEventListener('click', (e) => {
  const tr = e.target.closest('tr.ev');
  if (!tr) return;
  const key = tr.dataset.key;
  if (logState.expanded.has(key)) logState.expanded.delete(key); else logState.expanded.add(key);
  renderLog(true);
});
logRows.addEventListener('keydown', (e) => { if ((e.key === 'Enter' || e.key === ' ') && e.target.matches('tr.ev')) { e.preventDefault(); e.target.click(); } });
function openLog(opener) { logState.open = true; logState.opener = opener; logOverlay.hidden = false; renderLog(true); $('log-close').focus(); }
function openLogFor(id, opener) {
  if (!inScope(projectOfRobot(id))) setProject(projectOfRobot(id), { camera: false });
  logState.hiddenRobots = new Set(ROBOT_DEFS.map((d) => d.id).filter((r) => r !== id));
  paintScopeButtons();
  openLog(opener);
}
function closeLog() { logState.open = false; logOverlay.hidden = true; if (logState.opener) logState.opener.focus(); }
$('btn-log').addEventListener('click', (e) => openLog(e.currentTarget));
$('log-close').addEventListener('click', closeLog);
function renderLog(force) {
  if (!logState.open) return;
  const follow = $('log-follow').checked;
  const list = logItems.filter((e) => logState.cats.has(catOf(e)) && inScope(projectOfRobot(e.who)) && !logState.hiddenRobots.has(e.who) && (!logState.q || `${e.who} ${e.kind} ${e.what}`.toLowerCase().includes(logState.q)));
  $('log-count').textContent = `${list.length} 件（全 ${logItems.length} 件）`;
  setText($('log-title'), UI.project === 'all' ? 'イベントログ' : `イベントログ · ${PROJECT[UI.project].name}`);
  const more = $('log-more');
  if (!follow && !force && logState.shownTop !== null) {
    const newer = list.filter((e) => e.seq > logState.shownTop).length;
    more.hidden = newer === 0;
    more.textContent = `新着 ${newer} 件を表示`;
    return;
  }
  more.hidden = true;
  logState.shownTop = list.length ? list[0].seq : 0;
  const rows = list.slice(0, 400).map((e) => {
    const cat = catOf(e), d = DEF[e.who], open = logState.expanded.has(String(e.seq));
    const row = `<tr class="ev" tabindex="0" data-key="${e.seq}" aria-expanded="${open}"><td class="time">${fmtClock(BASE_CLOCK + e.abs)}</td><td class="who">${pill(e.who, d.role)} ${esc(d.agent)}</td><td><span class="cat cat-${cat}">${esc(e.kind)}</span></td><td class="what">${esc(e.what)}</td></tr>`;
    const note = SOURCE.mode === 'live' ? 'サーバーが受けた入力（長いものは切り詰め）' : e.decision ? 'ビューで押した答えを Claude Code へ返す内容の例' : cat === 'spec' || cat === 'test' ? '可視化サーバーが作るイベントの例' : 'フック入力の例（項目名は実際と同じ。値はデモ）';
    return open ? `${row}<tr class="payload"><td colspan="4"><p>${note}</p><pre>${esc(JSON.stringify(payloadFor(e), null, 2))}</pre></td></tr>` : row;
  }).join('');
  setHTML(logRows, rows || '<tr><td colspan="4" class="log-empty">条件に合うイベントがありません</td></tr>');
  if (follow) logBody.scrollTop = 0;
}
document.addEventListener('keydown', (e) => {
  if (e.key !== 'Escape') return;
  if (!popEl.hidden) { e.preventDefault(); closePop(); return; }
  if (logState.open) { e.preventDefault(); closeLog(); }
  else if (rbState.id) { e.preventDefault(); closeRobot(); }
  else if (wb.open) {
    e.preventDefault();
    if (narrowWb() && wbSideOpen) { wbSideOpen = false; applyWbSide(); } else closeWhiteboard();
  } else if (tb.open) { e.preventDefault(); if (tb.detail) closeTaskDetail(); else closeTaskBoard(); }
});

