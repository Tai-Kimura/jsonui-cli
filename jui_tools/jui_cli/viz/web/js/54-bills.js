/* ---------- the bill over a robot (2.3.6, ticket 2026-10-19-jui-viz-cost-bill-over-robot) ----------
   Each response's estimated cost (USD), over the robot that made it, with a banknote: the server prices it (prices.py:
   the four kinds of tokens × the model's row) and puts it in the "bills" slice once per message id; a subagent's go over
   its own robot. A bill rises a little and goes after BILL.showMs; responses that come while one shows are added to it
   (one amount per robot, never a pile). A model with no price shows ? and the tokens, never an amount. The bill takes
   its place above the name tag in placeRobotTags (40-scene.js), as part of the tag's box, so it never covers a tag.
   設定 › お札 turns it off (kept per browser, readPref); reduced motion: shown and gone, no rise. The 単価 sheet lists
   the table in use and changes the user's table (POST /api/prices); a model with no price is told in the top bar. */
const BILL = { showMs: 4200, rise: 12, gap: 3, on: readPref('bills', 'on') !== 'off', seen: new Map(), primed: false,
  notice: tl('bill.notice') };
const BILL_ICON_HTML = '<svg class="bill-ico" viewBox="0 0 22 14" aria-hidden="true"><rect x="0.75" y="0.75" width="20.5" height="12.5" rx="2" /><circle cx="11" cy="7" r="3" /><path d="M3.5 4v6M18.5 4v6" /></svg>';
function billMoney(usd) {
  if (usd < 0.01) return '< $0.01';
  return usd < 100 ? `≈ $${usd.toFixed(2)}` : `≈ $${Math.round(usd).toLocaleString('en-US')}`;
}
function billTokens(n) { return n < 1000 ? `${n}` : n < 1e6 ? `${(n / 1000).toFixed(1)}k` : `${(n / 1e6).toFixed(2)}M`; }
/* The text of a robot's bill from the responses it holds: their priced sum, "+ ?" when some had no price. */
function billText(items) {
  let usd = 0, priced = 0, tokens = 0;
  for (const it of items.values()) {
    tokens += it.tokens;
    if (typeof it.usd === 'number') { usd += it.usd; priced += 1; }
  }
  if (!priced) return { text: `? ${billTokens(tokens)} tok`, unknown: true };
  return { text: priced < items.size ? `${billMoney(usd)} + ?` : billMoney(usd), unknown: false };
}
function billEl(R) {
  if (R.bill) return R.bill;
  const el = document.createElement('div');
  el.className = 'bill';
  el.dataset.robot = R.def.id;   // a click on the bill selects the robot, as on its tag (40-scene.js, tagPress)
  el.hidden = true;
  el.innerHTML = `<span class="bill-in">${BILL_ICON_HTML}<b></b></span>`;
  tagsEl.append(el);
  R.bill = el;
  return el;
}
/* One response over robot `label` (the page's label): added to the bill showing, or a new one. */
function billShow(label, item) {
  if (!BILL.on || !has3D) return;
  const R = robots.find((x) => x.def.id === label);
  if (!R) return;
  const now = performance.now(), el = billEl(R);
  if (!R.billItems || now >= R.billUntil) R.billItems = new Map();
  R.billItems.set(item.id, { usd: item.usd, tokens: item.tokens, model: item.model, from: item.from });
  R.billUntil = now + BILL.showMs;
  const { text, unknown } = billText(R.billItems);
  el.querySelector('b').textContent = text;
  el.classList.toggle('unknown', unknown);
  const models = [...new Set([...R.billItems.values()].map((x) => x.model))].join(', ');
  const from = [...new Set([...R.billItems.values()].filter((x) => typeof x.usd === 'number').map((x) => (x.from === 'user' ? tl('bill.from.user') : tl('bill.from.default'))))].join(tl('bill.from.sep'));
  el.title = `${tl('bill.title.responses', { n: R.billItems.size })} · ${models}${from ? ` · ${tl('bill.title.prices', { from })}` : ''}${unknown ? ` · ${tl('bill.title.unpriced')}` : ''}\n${BILL.notice}`;
  el.classList.toggle('own-price', [...R.billItems.values()].some((x) => x.from === 'user' && typeof x.usd === 'number'));
  if (el.hidden) el.style.visibility = 'hidden';   // placeRobotTags shows it where it belongs, from the next frame
  el.hidden = false;
  el.dataset.n = String(R.billItems.size);
  const inner = el.firstElementChild;
  inner.classList.remove('rise');
  if (!reduceMotion) { void inner.offsetWidth; inner.classList.add('rise'); }   // start the rise again from the bottom
}
function billHide(R) {
  if (!R.bill || R.bill.hidden) return;
  R.bill.hidden = true;
  R.billItems = null;
  R.billSize = null;
}
/* Every frame (placeRobotTags): bills past their time go. */
function billsExpire() {
  const now = performance.now();
  for (const R of robots) if (R.bill && !R.bill.hidden && now >= R.billUntil) billHide(R);
}
/* Live: the slice's new bills. The bills already there when the page opens are old: seen, not shown. A bill whose
   amount changed (the same message written again with more tokens) replaces its own line in the robot's sum. */
function billsFromSlice() {
  const list = Array.isArray(LIVE.slices.bills) ? LIVE.slices.bills : [];
  if (list === BILL.list) return;   // a slice is replaced whole when it changes
  BILL.list = list;
  for (const b of list) {
    if (!b || typeof b.id !== 'string') continue;
    const key = `${b.agentId}|${b.id}`, sig = `${b.usd}|${b.tokens}`;
    if (BILL.seen.get(key) === sig) continue;
    BILL.seen.set(key, sig);
    if (!BILL.primed) continue;
    const label = labelOf(b.agentId);
    if (label) billShow(label, { id: key, usd: typeof b.usd === 'number' ? b.usd : null, tokens: Number(b.tokens) || 0, model: String(b.model || ''), from: b.priceFrom === 'user' ? 'user' : 'default' });
  }
  BILL.primed = true;
  if (BILL.seen.size > 600) for (const k of [...BILL.seen.keys()].slice(0, 300)) BILL.seen.delete(k);
}
/* Demo: now and then a working robot's response costs a little (made up: the demo has no transcripts). */
const BILL_DEMO = { next: 0, n: 0, seed: 7 };
function billsDemo(ms) {
  if (SOURCE.mode !== 'demo' || ms < BILL_DEMO.next) return;
  BILL_DEMO.seed = (BILL_DEMO.seed * 16807) % 2147483647;
  const r = (BILL_DEMO.seed % 1000) / 1000;
  BILL_DEMO.next = ms + 2500 + r * 3500;
  const busy = robots.filter((R) => R.robot.root.visible && !['idle', 'sleep'].includes(R.robot.state));
  if (!busy.length) return;
  const R = busy[Math.floor(r * busy.length) % busy.length];
  BILL_DEMO.n += 1;
  billShow(R.def.id, { id: `demo-${BILL_DEMO.n}`, usd: r < 0.12 ? null : 0.004 + r * r * 0.11, tokens: Math.round(20000 + r * 60000), model: r < 0.12 ? 'claude-unknown' : 'claude-opus-5-5' });
}

/* 設定 › お札: on by default; off hides what shows. */
function billPaint() {
  const b = document.getElementById('bill-switch');
  if (b) b.setAttribute('aria-checked', BILL.on ? 'true' : 'false');
  const n = document.getElementById('bill-note');
  if (n) setText(n, BILL.on ? tl('bill.switch.on') : tl('bill.switch.off'));
}
{ const b = document.getElementById('bill-switch');
  if (b) b.addEventListener('click', () => {
    BILL.on = !BILL.on;
    writePref('bills', BILL.on ? 'on' : 'off');
    if (!BILL.on) for (const R of robots) billHide(R);
    billPaint();
  });
  billPaint(); }

/* ---------- the 単価 sheet: the table in use, and the user's own (live only) ---------- */
const prEl = $('pr'), prBody = $('pr-body');
const pr = { open: false, edit: null, msg: '', busy: false, opener: null, sig: '' };
const PR_KINDS = [['input', tl('pr.kind.input')], ['cache_write_5m', tl('pr.kind.cache_write_5m')], ['cache_write_1h', tl('pr.kind.cache_write_1h')], ['cache_read', tl('pr.kind.cache_read')], ['output', tl('pr.kind.output')]];
const PR_ORIGIN = { default: tl('pr.origin.default'), user: tl('pr.origin.user'), changed: tl('pr.origin.changed'), removed: tl('pr.origin.removed') };
function pricesSlice() { const p = LIVE.slices && LIVE.slices.prices; return p && !Array.isArray(p) && typeof p === 'object' ? p : null; }
function openPrices(opener, model) {
  if (SOURCE.mode !== 'live') return;
  holdView('pr');   // 50-panel.js VIEW_HOLD: held before the card it replaces lets go
  if (wb.open) closeWhiteboard();
  if (tb.open) closeTaskBoard();
  if (rbState.id) closeRobot();
  if (ds.open) closeDataDocs();
  const p = pricesSlice(), row = p && (p.rows || []).find((r) => r.model === model);
  Object.assign(pr, { open: true, msg: '', opener: opener || null, sig: '',
    edit: model ? { model, values: row && row.origin !== 'removed' ? Object.fromEntries(PR_KINDS.map(([k]) => [k, row[k]])) : {}, isNew: !row } : null });
  showOverlay(prEl);
  liveSoloSync();
  renderPrices(true);
  const first = model ? prBody.querySelector('[data-pr-in="input"]') : $('pr-close');
  if (first) first.focus({ preventScroll: true });
}
function closePrices() {
  if (!pr.open) { releaseView('pr'); return; }
  pr.open = false; pr.edit = null;
  hideOverlay(prEl);
  releaseView('pr');
  liveSoloSync();
  if (pr.opener && pr.opener.focus) pr.opener.focus({ preventScroll: true });
}
function renderPrices(force) {
  if (!pr.open) return;
  const p = pricesSlice();
  const sig = JSON.stringify([p, pr.edit, pr.msg, pr.busy]);
  if (!force && sig === pr.sig) return;
  // a form being typed into is not drawn again under the cursor: only the list and the notes change
  if (!force && prBody.contains(document.activeElement) && document.activeElement.matches('input')) return;
  pr.sig = sig;
  if (!p) { prBody.innerHTML = `<p class="ds-none">${esc(tl('pr.none'))}</p>`; return; }
  const num = (v) => (typeof v === 'number' ? String(v) : '—');
  const unpricedHTML = (p.unpriced || []).map((m) => `<li><code>${esc(m)}</code> <button type="button" class="mini-btn" data-pr-add="${esc(m)}">${esc(tl('pr.add'))}</button></li>`).join('');
  const errorsHTML = (p.errors || []).map((e) => `<li>${esc(e)}</li>`).join('');
  const rowsHTML = (p.rows || []).map((r) => {
    const removed = r.origin === 'removed', mine = r.origin !== 'default';
    const extra = [r.long ? tl('pr.extra.long', { over: fmtNum(r.long.over) }) : '', r.fast ? tl('pr.extra.fast') : '', r.us ? `us ×${r.us}` : ''].filter(Boolean).join(' · ');
    return `<tr data-pr-row="${esc(r.model)}"${removed ? ' class="removed"' : ''}><th scope="row"><code>${esc(r.model)}</code>${extra ? `<span class="pr-extra">${esc(extra)}</span>` : ''}</th>`
      + PR_KINDS.map(([k]) => `<td>${removed ? '' : esc(num(r[k]))}</td>`).join('')
      + `<td><span class="pr-origin" data-origin="${esc(r.origin)}">${esc(PR_ORIGIN[r.origin] || r.origin)}</span></td><td class="pr-acts">`
      + (removed ? '' : `<button type="button" class="mini-btn" data-pr-edit="${esc(r.model)}">${esc(tl('pr.edit'))}</button><button type="button" class="mini-btn" data-pr-op="remove" data-pr-model="${esc(r.model)}">${esc(tl('pr.remove'))}</button>`)
      + (mine && r.origin !== 'user' ? `<button type="button" class="mini-btn" data-pr-op="reset" data-pr-model="${esc(r.model)}">${esc(tl('pr.reset'))}</button>` : '')
      + '</td></tr>';
  }).join('');
  const e = pr.edit;
  const formHTML = e ? `<form class="pr-form" id="pr-form"><h3>${esc(e.isNew ? tl('pr.add') : tl('pr.change'))}</h3>
      <label class="pr-model">${esc(tl('pr.model.label'))}<input data-pr-in="model" value="${esc(e.model || '')}" ${e.isNew ? '' : 'readonly'} required maxlength="100" autocomplete="off" spellcheck="false"></label>
      <div class="pr-nums">${PR_KINDS.map(([k, ja]) => `<label>${esc(ja)}<input data-pr-in="${esc(k)}" type="number" min="0" max="100000" step="any" required value="${esc(e.values[k] === undefined ? '' : String(e.values[k]))}"></label>`).join('')}</div>
      <p class="set-hint">${esc(tl('pr.hint'))}</p>
      <div class="pr-btns"><button type="submit" class="mini-btn pr-save"${pr.busy ? ' disabled' : ''}>${esc(tl('pr.save'))}</button><button type="button" class="mini-btn" data-pr-cancel>${esc(tl('pr.cancel'))}</button></div></form>`
    : `<p><button type="button" class="mini-btn" data-pr-add="">${esc(tl('pr.add'))}</button></p>`;
  const aboutHTML = `<p class="pr-about">${esc(BILL.notice)} ${tlHTML('pr.about', { source: p.source || '', checked: p.checked || '', path: p.userPath || '' })}</p>`;
  const msgHTML = pr.msg ? `<p class="pr-msg" role="status">${esc(pr.msg)}</p>` : '';
  const headHTML = PR_KINDS.map(([, ja]) => `<th>${esc(ja)}</th>`).join('');
  prBody.innerHTML = `${aboutHTML}${msgHTML}`
    + (unpricedHTML ? `<section class="pr-unpriced"><h3>${esc(tl('pr.unpriced'))}</h3><ul>${unpricedHTML}</ul></section>` : '')
    + (errorsHTML ? `<section class="pr-errors"><h3>${esc(tl('pr.errors'))}</h3><ul>${errorsHTML}</ul></section>` : '')
    + `${formHTML}<table class="ds-table pr-table"><thead><tr><th>${esc(tl('pr.col.model'))}</th>${headHTML}<th>${esc(tl('pr.col.origin'))}</th><th></th></tr></thead><tbody>${rowsHTML}</tbody></table>`;
}
async function pricesSend(op, model, row) {
  pr.busy = true; renderPrices(true);
  const got = typeof SOURCE.pricesOp === 'function' ? await SOURCE.pricesOp(op, model, row) : { ok: false, error: tl('pr.live.only') };
  pr.busy = false;
  pr.msg = got.ok ? tl({ set: 'pr.done.set', remove: 'pr.done.remove', reset: 'pr.done.reset' }[op], { model }) : tl('pr.failed', { error: got.error || tl('pr.unknown') });
  if (got.ok && op === 'set') pr.edit = null;
  renderPrices(true);
}
$('pr-close').addEventListener('click', closePrices);
prBody.addEventListener('click', (ev) => {
  const t = ev.target;
  const add = t.closest('[data-pr-add]'), edit = t.closest('[data-pr-edit]'), op = t.closest('[data-pr-op]');
  if (add) { pr.edit = { model: add.dataset.prAdd, values: {}, isNew: true }; pr.msg = ''; renderPrices(true); const f = prBody.querySelector(add.dataset.prAdd ? '[data-pr-in="input"]' : '[data-pr-in="model"]'); if (f) f.focus(); return; }
  if (edit) {
    const row = ((pricesSlice() || {}).rows || []).find((r) => r.model === edit.dataset.prEdit);
    pr.edit = { model: edit.dataset.prEdit, values: row ? Object.fromEntries(PR_KINDS.map(([k]) => [k, row[k]])) : {}, isNew: false };
    pr.msg = ''; renderPrices(true);
    const f = prBody.querySelector('[data-pr-in="input"]'); if (f) f.focus();
    return;
  }
  if (op) { pricesSend(op.dataset.prOp, op.dataset.prModel, null); return; }
  if (t.closest('[data-pr-cancel]')) { pr.edit = null; renderPrices(true); }
});
prBody.addEventListener('submit', (ev) => {
  ev.preventDefault();
  const val = (k) => (prBody.querySelector(`[data-pr-in="${k}"]`) || {}).value;
  const model = String(val('model') || '').trim();
  const row = Object.fromEntries(PR_KINDS.map(([k]) => [k, Number(val(k))]));
  pricesSend('set', model, row);
});
/* The top bar: models seen with no price — the amount is not shown for them; the chip opens the sheet to add one. */
function pricesNotice() {
  const chip = $('chip-price');
  if (!chip) return;
  const p = SOURCE.mode === 'live' ? pricesSlice() : null, list = (p && p.unpriced) || [];
  chip.hidden = !list.length;
  setText(chip, tl('pr.chip', { n: list.length }));
  chip.title = tl('pr.chip.title', { models: list.join(', ') });
}
$('chip-price').addEventListener('click', (e) => { const p = pricesSlice(); openPrices(e.currentTarget, p && p.unpriced && p.unpriced[0]); });
{ const b = document.getElementById('prices-open'); if (b) b.addEventListener('click', (e) => openPrices(e.currentTarget)); }
/* Each frame from the main loop: the live bills (when the slice changed), the demo's. */
function billsFrame(ms) {
  if (SOURCE.mode === 'live') billsFromSlice();
  else billsDemo(ms);
}
/* With the panels (4 a second): the chip, and the sheet when the table changed. */
function pricesPanel() {
  pricesNotice();
  renderPrices(false);
}
