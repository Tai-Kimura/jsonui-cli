/* ---------- tool calls stopped by auto mode (ticket 2026-10-20-jui-viz-auto-mode-denial-approve-from-page) ----------
   Requester: 「このケースの時に許可できる仕組み実装できない？」. The server's cards (denials.py: the PermissionDenied hook
   and the transcript's denial, one card per call) are shown next to the questions: in the panel, on the board's strip,
   and counted by the 止められた chip. 「実行してよいと伝える…」 opens a confirmation that shows the exact words the server
   will send (the card's prompt); only its 送る sends, and the page names the card, never the words (POST /api/denial).
   That prompt is all: no rule, no setting, no answer to a hook — whether the next try passes is Claude Code's call.
   The orchestrator's ruling (10-20 15:30): what this claims is that the person's judgement reaches the receiver unmistaken, not
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
/* The same rule as a permission (the author's notification rules, kind perm): one ring per card; what waited before the page
   loaded is not rung. */
function denialsNotify() {
  const waiting = DENIALS.filter((d) => d.status === 'pending');
  if (!DEN.based) { DEN.based = true; for (const d of waiting) NOTIFY.seen.add(`${notifyServer()}:denied:${d.id}`); return; }
  for (const d of waiting) {
    notifyEvent('perm', `${notifyServer()}:denied:${d.id}`, { id: `denied:${d.id}`, who: d.who },
      tl('deny.notify', { name: notifyName(d.who), tool: String(d.tool || '').slice(0, 40) }));
  }
}
const denialsShown = (now = Date.now()) => DENIALS.filter((d) => inScope(projectOfRobot(d.who)) && (d.status === 'pending' || now - (d.doneAt || 0) < DEN_SHOW_MS));
const denialsWaiting = () => DENIALS.filter((d) => d.status === 'pending');
/* Whether a prompt can reach the card's session (the box under the history says the same: composeTarget). */
function denialTarget(d) {
  const main = SESSION_OF[d.who];
  return main && DEF[main] ? composeTarget(main) : { why: tl('deny.why.unseen') };
}
const DEN_DONE = { sent: tl('deny.done.sent'), dismissed: tl('deny.done.dismissed'), ended: tl('deny.done.ended') };
const DEN_MAY = tl('deny.may');
function denialHTML(d, where = '') {
  const t = d.status === 'pending' ? denialTarget(d) : { why: '' };
  const asking = DEN.asking === `${d.id}|${where}`;
  const whatHTML = `<p class="dwhat"><b>${esc(d.tool)}</b>${d.input ? ` <code>${esc(d.input)}</code>` : ''}</p>${d.reason ? `<p class="dwhy">${esc(tl('deny.reason', { reason: d.reason }))}</p>` : ''}`;
  let footHTML;
  if (d.status === 'sent') {
    footHTML = `<p class="qnote qdone">${esc(DEN_DONE.sent)}</p>` + (d.reply
      ? `<p class="dreply" data-dreply="${esc(d.id)}"><b>${esc(tl('deny.reply'))}</b> ${esc(d.reply)}</p>`
      : `<p class="qnote" data-dreply-wait="${esc(d.id)}">${esc(tl('deny.reply.wait', { may: DEN_MAY }))}</p>`);
  } else if (d.status !== 'pending') footHTML = `<p class="qnote qdone">${esc(DEN_DONE[d.status] || d.status)}</p>`;
  else if (t.why) footHTML = `<p class="qnote qwhy" role="note">${esc(tl('deny.why.terminal', { why: t.why }))}</p><div class="qfoot"><button type="button" class="pa pa-deny" data-ddismiss="${esc(d.id)}" data-fk="${esc(where)}dd-${esc(d.id)}">${esc(tl('deny.dismiss'))}</button></div>`;
  else if (asking) {
    footHTML = `<div class="dconfirm" role="group" aria-label="${esc(tl('deny.confirm.aria'))}"><p class="dconfirm-to">${esc(tl('deny.confirm.to', { name: t.name || '' }))}</p><blockquote class="dprompt" data-dprompt="${esc(d.id)}">${esc(d.prompt)}</blockquote><p class="qnote" data-dmay>${esc(DEN_MAY)}</p>`
      + `<div class="qfoot"><button type="button" class="pa pa-allow" data-dgo="${esc(d.id)}" data-fk="${esc(where)}dg-${esc(d.id)}">${esc(tl('deny.confirm.go'))}</button><button type="button" class="pa pa-deny" data-dback="${esc(d.id)}" data-fk="${esc(where)}db-${esc(d.id)}">${esc(tl('deny.confirm.back'))}</button></div></div>`;
  } else {
    footHTML = `<div class="qfoot"><button type="button" class="pa pa-allow" data-dask="${esc(d.id)}" data-fk="${esc(where)}da-${esc(d.id)}">${esc(tl('deny.ask'))}</button><button type="button" class="pa pa-deny" data-ddismiss="${esc(d.id)}" data-fk="${esc(where)}dd-${esc(d.id)}">${esc(tl('deny.dismiss'))}</button></div>`
      + `<p class="qnote">${esc(tl('deny.ask.note', { may: DEN_MAY }))}</p>`;
  }
  return `<article class="qcard dcard${d.status === 'pending' ? ' q-open' : ''}" data-dcard="${esc(d.id)}"><header class="qwho">${pill(d.who, DEF[d.who].role)}<span>${esc(DEF[d.who].agent)}</span><span class="dtag">${esc(tl('deny.tag'))}</span><span class="pc-wait" data-since="${d.at}"></span>${histOffHTML(where, 'd', d.id, d.status !== 'pending')}</header>${whatHTML}${footHTML}</article>`;
}
const denialsSig = (shown) => JSON.stringify([NAMES.rev, DEN.asking, ...shown.map((d) => [d.id, d.status, d.reason, d.input, d.reply, denialTarget(d).why])]);
function renderDenials() {
  const shown = denialsShown(), waiting = denialsWaiting().length;
  const chip = $('chip-denied');
  chip.hidden = waiting === 0;
  setText(chip, tl('deny.chip', { n: waiting }));
  $('denied-sec').hidden = shown.length === 0;
  keyed($('denied'), denialsSig(shown), () => shown.map((d) => denialHTML(d)).join(''));
}
function renderDenialStrip() {
  const el = $('denied-strip'), shown = denialsShown(), elsewhere = denialsWaiting().filter((d) => !inScope(projectOfRobot(d.who))).length;
  el.hidden = !shown.length && !elsewhere;
  keyed(el, `${elsewhere}|${denialsSig(shown)}`, () => {
    const otherHTML = elsewhere ? `<p class="ps-rules">${esc(tl('deny.elsewhere', { n: elsewhere }))} <button type="button" class="link-btn" data-set-all data-fk="ds-all">${esc(tl('deny.show.all'))}</button></p>` : '';
    const foldHTML = shown.map((d) => foldLine(`d:${d.id}`, d, d.tool, d.input || '', d.status === 'pending' ? '' : DEN_DONE[d.status] || d.status)).join('');
    return `<h3 class="ps-title">${esc(tl('deny.strip.title'))}${countB(shown.filter((d) => d.status === 'pending').length)}<small>${esc(tl('deny.strip.order'))}</small></h3>${foldHTML ? `<ul class="ps-fold">${foldHTML}</ul>` : ''}${otherHTML}${shown.map((d) => denialHTML(d, 'b')).join('')}`;
  });
  tb.waiting.d = shown.filter((d) => d.status === 'pending').length;
  el.classList.toggle('ps-hot', tb.waiting.d > 0);
}
function onDenialClick(e) {
  const where = e.currentTarget.dataset.dwhere !== undefined ? e.currentTarget.dataset.dwhere : e.currentTarget.id === 'denied-strip' ? 'b' : '';   // h: the 応答の履歴 tab
  const ask = e.target.closest('[data-dask]'), go = e.target.closest('[data-dgo]'), back = e.target.closest('[data-dback]'), dismiss = e.target.closest('[data-ddismiss]');
  const repaint = () => { renderDenials(); if (typeof tb !== 'undefined' && tb.open) renderDenialStrip(); if (typeof histCardsPaint === 'function') histCardsPaint(); if (typeof cardWaitPanePaint === 'function') cardWaitPanePaint(); };
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
      showToast(got.ok ? tl('deny.sent') : tl('deny.send.failed') + (got.error || `HTTP ${got.status}`) + tl('deny.paren.end'));
      repaint();
    });
    return;
  }
  if (dismiss) {
    dismiss.disabled = true;
    SOURCE.denial(dismiss.dataset.ddismiss, 'dismiss').then((got) => { if (!got.ok) showToast(tl('deny.close.failed') + (got.error || `HTTP ${got.status}`) + tl('deny.paren.end')); repaint(); });
  }
}
for (const id of ['denied', 'denied-strip']) $(id).addEventListener('click', onDenialClick);
$('chip-denied').addEventListener('click', (e) => openWaitBoard(e.currentTarget, WAITS_OF.denied()));   // 53-waits.js
