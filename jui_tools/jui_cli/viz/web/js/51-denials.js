/* ---------- tool calls stopped by auto mode (ticket 2026-10-20-jui-viz-auto-mode-denial-approve-from-page) ----------
   Requester: 「このケースの時に許可できる仕組み実装できない？」. The server's cards (denials.py: the PermissionDenied hook
   and the transcript's denial, one card per call) are shown next to the questions: in the panel, on the board's strip,
   and counted by the 止められた chip. 「実行してよいと伝える…」 opens a confirmation that shows the exact words the server
   will send (the card's prompt); only its 送る sends, and the page names the card, never the words (POST /api/denial).
   That prompt is all: no rule, no setting, no answer to a hook — whether the next try passes is Claude Code's call.
   cd's ruling (10-20 15:30): what this claims is that the person's judgement reaches the receiver unmistaken, not
   that the receiver goes on — it may rightly ask for a confirmation in the terminal. Once sent, the card says 伝えた
   and shows the receiver's next response under it.
   A session whose channel cannot take a prompt gets the reason instead of the button. 「そのまま」 closes the card. */
const DENIALS = [];
const DEN = { asking: null, askedAt: 0, based: false };
const DEN_SHOW_MS = 60000;
function rebuildDenials() {
  const list = typeof LIVE !== 'undefined' && Array.isArray(LIVE.slices.denials) ? LIVE.slices.denials : [];
  const rows = [];
  for (const x of list) {
    const who = x && (labelOf(x.agentId) || labelOf(x.sessionId));
    if (!who || !DEF[who] || typeof x.id !== 'string') continue;
    rows.push({ ...x, who, atMs: x.at, at: secOfDay(x.at || Date.now()) });   // at: the second of the day, as a question's
  }
  DENIALS.splice(0, DENIALS.length, ...rows);
  if (DEN.asking && !DENIALS.some((d) => d.id === DEN.asking.split('|')[0] && d.status === 'pending')) DEN.asking = null;
  denialsNotify();
}
/* The same rule as a permission (c2's notification rules, kind perm): one ring per card; what waited before the page
   loaded is not rung. */
function denialsNotify() {
  const waiting = DENIALS.filter((d) => d.status === 'pending');
  if (!DEN.based) { DEN.based = true; for (const d of waiting) NOTIFY.seen.add(`${notifyServer()}:denied:${d.id}`); return; }
  for (const d of waiting) {
    notifyEvent('perm', `${notifyServer()}:denied:${d.id}`, { id: `denied:${d.id}`, who: d.who },
      `${notifyName(d.who)} の操作が自動モードで止められました: ${String(d.tool || '').slice(0, 40)}`);
  }
}
const denialsShown = (now = Date.now()) => DENIALS.filter((d) => inScope(projectOfRobot(d.who)) && (d.status === 'pending' || now - (d.doneAt || 0) < DEN_SHOW_MS));
const denialsWaiting = () => DENIALS.filter((d) => d.status === 'pending');
/* Whether a prompt can reach the card's session (the box under the history says the same: composeTarget). */
function denialTarget(d) {
  const main = SESSION_OF[d.who];
  return main && DEF[main] ? composeTarget(main) : { why: 'このセッションは見えていない' };
}
const DEN_DONE = { sent: '伝えた', dismissed: 'そのままにした', ended: 'セッションが終わった' };
const DEN_MAY = '受け手は続けることも、端末での確認を求めることもある（求められたら端末で答える）';
function denialHTML(d, where = '') {
  const t = d.status === 'pending' ? denialTarget(d) : { why: '' };
  const asking = DEN.asking === `${d.id}|${where}`;
  const whatHTML = `<p class="dwhat"><b>${esc(d.tool)}</b>${d.input ? ` <code>${esc(d.input)}</code>` : ''}</p>${d.reason ? `<p class="dwhy">理由 ${esc(d.reason)}</p>` : ''}`;
  let footHTML;
  if (d.status === 'sent') {
    footHTML = `<p class="qnote qdone">${esc(DEN_DONE.sent)}</p>` + (d.reply
      ? `<p class="dreply" data-dreply="${esc(d.id)}"><b>受け手の次の応答</b> ${esc(d.reply)}</p>`
      : `<p class="qnote" data-dreply-wait="${esc(d.id)}">受け手の応答を待っている。${esc(DEN_MAY)}</p>`);
  } else if (d.status !== 'pending') footHTML = `<p class="qnote qdone">${esc(DEN_DONE[d.status] || d.status)}</p>`;
  else if (t.why) footHTML = `<p class="qnote qwhy" role="note">${esc(t.why)}。端末で許可を伝えてください</p><div class="qfoot"><button type="button" class="pa pa-deny" data-ddismiss="${esc(d.id)}" data-fk="${esc(where)}dd-${esc(d.id)}">そのまま</button></div>`;
  else if (asking) {
    footHTML = `<div class="dconfirm" role="group" aria-label="送信の確認"><p class="dconfirm-to">このセッションへ次の文を伝える（${esc(t.name || '')}）</p><blockquote class="dprompt" data-dprompt="${esc(d.id)}">${esc(d.prompt)}</blockquote><p class="qnote" data-dmay>${esc(DEN_MAY)}</p>`
      + `<div class="qfoot"><button type="button" class="pa pa-allow" data-dgo="${esc(d.id)}" data-fk="${esc(where)}dg-${esc(d.id)}">送る</button><button type="button" class="pa pa-deny" data-dback="${esc(d.id)}" data-fk="${esc(where)}db-${esc(d.id)}">やめる</button></div></div>`;
  } else {
    footHTML = `<div class="qfoot"><button type="button" class="pa pa-allow" data-dask="${esc(d.id)}" data-fk="${esc(where)}da-${esc(d.id)}">実行してよいと伝える…</button><button type="button" class="pa pa-deny" data-ddismiss="${esc(d.id)}" data-fk="${esc(where)}dd-${esc(d.id)}">そのまま</button></div>`
      + `<p class="qnote">押すと、確認の後に、止められた操作と理由と「実行してよいと判断した」をこのセッションへ伝える。${esc(DEN_MAY)}。許可の規則や設定は変えない</p>`;
  }
  return `<article class="qcard dcard${d.status === 'pending' ? ' q-open' : ''}" data-dcard="${esc(d.id)}"><header class="qwho">${pill(d.who, DEF[d.who].role)}<span>${esc(DEF[d.who].agent)}</span><span class="dtag">自動モードが止めた</span><span class="pc-wait" data-since="${d.at}"></span></header>${whatHTML}${footHTML}</article>`;
}
const denialsSig = (shown) => JSON.stringify([NAMES.rev, DEN.asking, ...shown.map((d) => [d.id, d.status, d.reason, d.input, d.reply, denialTarget(d).why])]);
function renderDenials() {
  const shown = denialsShown(), waiting = denialsWaiting().length;
  const chip = $('chip-denied');
  chip.hidden = waiting === 0;
  setText(chip, `止められた ${waiting}`);
  $('denied-sec').hidden = shown.length === 0;
  keyed($('denied'), denialsSig(shown), () => shown.map((d) => denialHTML(d)).join(''));
}
function renderDenialStrip() {
  const el = $('denied-strip'), shown = denialsShown(), elsewhere = denialsWaiting().filter((d) => !inScope(projectOfRobot(d.who))).length;
  el.hidden = !shown.length && !elsewhere;
  keyed(el, `${elsewhere}|${denialsSig(shown)}`, () => {
    const otherHTML = elsewhere ? `<p class="ps-rules">ほかのプロジェクトでも ${elsewhere} 件 <button type="button" class="link-btn" data-set-all data-fk="ds-all">すべてのプロジェクトを表示</button></p>` : '';
    return `<h3 class="ps-title">自動モードが止めた操作<b>${shown.filter((d) => d.status === 'pending').length}</b><small>古い順</small></h3>${otherHTML}${shown.map((d) => denialHTML(d, 'b')).join('')}`;
  });
}
function onDenialClick(e) {
  const where = e.currentTarget.id === 'denied-strip' ? 'b' : '';
  const ask = e.target.closest('[data-dask]'), go = e.target.closest('[data-dgo]'), back = e.target.closest('[data-dback]'), dismiss = e.target.closest('[data-ddismiss]');
  const repaint = () => { renderDenials(); if (typeof tb !== 'undefined' && tb.open) renderDenialStrip(); };
  if (ask) {
    DEN.asking = `${ask.dataset.dask}|${where}`; DEN.askedAt = Date.now(); repaint();
    const btn = e.currentTarget.querySelector(`[data-dgo="${CSS.escape(ask.dataset.dask)}"]`);
    if (btn) btn.focus({ preventScroll: true });
    return;
  }
  if (back) { DEN.asking = null; repaint(); return; }
  if (go) {
    if (Date.now() - DEN.askedAt < 350 || DEN.asking !== `${go.dataset.dgo}|${where}`) return;   // not the press that opened it
    go.disabled = true;
    SOURCE.denial(go.dataset.dgo, 'approve').then((got) => {
      DEN.asking = null;
      showToast(got.ok ? 'このセッションへ伝えた（受け手の次の応答が札の下に出る）' : `送れなかった（${got.error || `HTTP ${got.status}`}）`);
      repaint();
    });
    return;
  }
  if (dismiss) {
    dismiss.disabled = true;
    SOURCE.denial(dismiss.dataset.ddismiss, 'dismiss').then((got) => { if (!got.ok) showToast(`閉じられなかった（${got.error || `HTTP ${got.status}`}）`); repaint(); });
  }
}
for (const id of ['denied', 'denied-strip']) $(id).addEventListener('click', onDenialClick);
$('chip-denied').addEventListener('click', (e) => { tb.waitView = true; openTaskBoard(e.currentTarget); });
