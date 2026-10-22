/* ---------- the cost simulator (plan 2026-10-20-jui-viz-backend-load-and-cost-simulator, L-C) ----------
   Requester 10-20: 「バックエンドの負荷とコストシミュレータをサーバーの3dと切り替えで表示出来るようにしたい … 1ヶ月のコストグラフ …
   1日のうちで横棒グラフでどのノードのコストがどう変わっていくかをシミュレーション」; 「棒の中とかに何がどのくらいコストを生んでるか
   表示して欲しい 例えばリクエスト100/sec」; 「捌ききれなくなった時に赤字になって捌けた数/リクエスト数みたいな表示」.

   The page computes nothing: SOURCE.infraCost asks the server (POST /api/infra-cost), which runs document_tools' load,
   engine and view and gives the shapes drawn here. 3D / コスト on the server room's header switches the stage: the 3D
   pauses (no frame drawn) while the cost is shown. The month: the days stacked by provider or by node, a red mark on a
   day with an hour over capacity, a flag on one at the autoscale's top, the sum, and the counts of what is not priced
   (never hidden). A day: the top nodes' bars hour by hour (play, stop, the hour's slider), each bar its meters with the
   quantity's rate and the charge; over capacity in red as 捌けた / 来た. A meter pressed shows the price it used.
   The account (the server's account.available: two environments or more, each with a load definition): この環境だけ /
   アカウントの合計 — the environments priced with one total (a free amount taken once), the month stacked by
   environment; a day is the chosen scenario's within that pricing. アカウントの合計 is the default (the requester 10-21:
   「合計で」): SRC.account stays null (the server's default) until one is pressed. */
const SRC = { mode: '3d', seq: 0, scenario: null, by: 'provider', account: null, month: null, day: null, date: null, hour: 0, timer: 0,
  playMs: 700, picked: null, error: '', open: new Set() };   // open: the rows whose meters are shown whole (広げる)
const srcEl = $('sr-cost');
const SRC_PER = { second: 'sec', minute: 'min', hour: 'h', day: 'day', month: 'mo' };
const SRC_COLORS = ['#4e79a7', '#f28e2b', '#59a14f', '#e15759', '#76b7b2', '#edc948', '#b07aa1', '#ff9da7', '#9c755f', '#bab0ac'];

function srcUsd(v) {
  return v === null || v === undefined ? tl('cost.noprice') : usdText(v);
}
function srcNum(v) {
  return new Intl.NumberFormat('en-US', { maximumFractionDigits: v !== 0 && Math.abs(v) < 10 ? 2 : 0 }).format(v);
}
function srcRate(rate) { return rate ? `${srcNum(rate.value)}/${SRC_PER[rate.per] || rate.per}` : ''; }
function srcKeyColor(key, i) {
  if (SRC.month && SRC.month.by === 'provider' && key !== '__others__') return srProviderColor(key);
  return key === '__others__' ? '#9aa0a6' : SRC_COLORS[i % SRC_COLORS.length];
}

/* ---- switching ---- */
function srcSetMode(mode) {
  SRC.mode = mode;
  $('sr-mode-3d').setAttribute('aria-pressed', String(mode === '3d'));
  $('sr-mode-cost').setAttribute('aria-pressed', String(mode === 'cost'));
  $('sr-scn-ctl').hidden = mode !== 'cost';
  srcEl.hidden = mode !== 'cost';
  SR.paused = mode === 'cost';
  $('sr-boxzoom').disabled = mode === 'cost';   // the box is the 3D's (56-server-room.js); the cost page takes its own presses
  if (mode === 'cost') { srBoxEnd(); srBoxArm(false); srFlowStop(); }   // a flow playing (59-sr-flows.js) is the 3D's too
  if (mode === '3d') {
    srcStop();
    if (SR.view && !SR.view.raf && SR.view.loop) SR.view.loop();
    return;
  }
  if (!SRC.month) srcLoad();
}
function srCostReset() {   // the server room closed (56-server-room.js srClose): back to 3D, nothing kept
  srcStop();
  Object.assign(SRC, { mode: '3d', scenario: null, account: null, month: null, day: null, date: null, hour: 0, picked: null, error: '', open: new Set() });
  SR.paused = false;
  $('sr-boxzoom').disabled = false;
  $('sr-mode-3d').setAttribute('aria-pressed', 'true');
  $('sr-mode-cost').setAttribute('aria-pressed', 'false');
  $('sr-scn-ctl').hidden = true;
  srcEl.hidden = true;
  setHTML(srcEl, '');
}

/* ---- asking the server ---- */
async function srcAsk(extra) {
  const seq = ++SRC.seq;
  const got = typeof SOURCE.infraCost === 'function' ? await SOURCE.infraCost(SR.project, { seq, scenario: SRC.scenario, account: SRC.account, ...extra })
    : { ok: false, reason: 'unreadable', message: tl('cost.unavailable') };
  return seq === SRC.seq && SRC.mode === 'cost' ? got : null;   // an older answer, or the view left: dropped
}
async function srcLoad() {
  SRC.error = '';
  srcRender(tl('cost.loading'));
  const got = await srcAsk({ by: SRC.by });
  if (!got) return;
  if (!got.ok) { SRC.error = got.short || got.message || got.reason || tl('cost.failed'); SRC.month = null; srcRender(); return; }
  SRC.scenario = got.scenario;
  SRC.month = { ...got.month, scenarios: got.scenarios, problems: got.problems, prices: got.prices, account: got.account };
  setHTML($('sr-scn'), got.scenarios.map((s) => `<option value="${esc(s.id)}"${s.id === got.scenario ? ' selected' : ''}>${esc(tl('cost.scn.option', { label: s.label, month: s.month }))}</option>`).join(''));
  const label = got.scenarios.find((s) => s.id === got.scenario).label;
  srLog(tl(got.account.on ? 'cost.account.log' : 'cost.log.done', { label, usd: srcUsd(got.month.usd) }));
  if (SRC.date) await srcOpenDay(SRC.date); else srcRender();
}
async function srcOpenDay(date) {
  const got = await srcAsk({ date });
  if (!got) return;
  if (!got.ok) { SRC.error = got.short || got.message || tl('cost.failed'); srcRender(); return; }
  Object.assign(SRC, { date, day: got.day, hour: Math.min(SRC.hour, got.day.hours.length - 1), picked: null });
  srcRender();
}
function srcBackToMonth() { srcStop(); Object.assign(SRC, { date: null, day: null, picked: null }); srcRender(); }

/* ---- playing the day ---- */
function srcPlay() {
  if (reduceMotion || !SRC.day) return;   // reduced motion: the slider only
  srcStop();
  if (SRC.hour >= SRC.day.hours.length - 1) SRC.hour = 0;
  SRC.timer = setInterval(() => {
    if (!SRC.day || SRC.hour >= SRC.day.hours.length - 1) { srcStop(); srcRender(); return; }
    SRC.hour += 1;
    srcRender();
  }, SRC.playMs);
  srcRender();
}
function srcStop() { if (SRC.timer) { clearInterval(SRC.timer); SRC.timer = 0; } }

/* ---- the month ---- */
function srcSummary(M) {
  const chips = [
    ['noPrice', tl('cost.noprice'), M.noPrice.length, M.noPrice.map((x) => tl('cost.noprice.item', { node: x.node, meter: x.meter, sku: x.sku, unit: x.unit }))],
    ['noRule', tl('cost.norule'), M.noRule.length, M.noRule],
    ['loadUndefined', tl('cost.noload'), M.loadUndefined.length, M.loadUndefined],
    ['overflow', tl('cost.overflow'), Object.keys(M.overflowHours).length, Object.entries(M.overflowHours).map(([n, h]) => tl('cost.overflow.item', { node: n, n: h }))],
    ['problems', tl('cost.problems'), M.problems.count, M.problems.first.map((p) => p.short || `${p.file} ${p.path}: ${p.message}`)],
    ['warnings', tl('cost.warnings'), M.warningCount, M.warnings.map(srcWarnText)],
  ];
  // the free amount is taken once per scenario (one environment): environments on one account each counted take it twice
  const free = M.warnings.find((w) => w.code === 'cost.free_per_scenario');
  const freeHTML = free ? `<p class="src-free" data-src-free role="note">${esc(tl('cost.free'))}${free.rows && free.rows.length ? esc(tl('cost.free.rows', { n: Number(free.rows.length) })) : ''}</p>` : '';
  const acctHTML = M.account && M.account.available ? `<span class="sr-ctl sr-mode" role="group" aria-label="${esc(tl('cost.account.group'))}"><button type="button" class="wb-btn" data-src-act="acct-on" aria-pressed="${esc(String(!!M.account.on))}">${esc(tl('cost.account.all'))}</button><button type="button" class="wb-btn" data-src-act="acct-off" aria-pressed="${esc(String(!M.account.on))}">${esc(tl('cost.account.one'))}</button></span>` : '';
  const byHTML = M.by === 'environment' ? '' : `<label class="sr-ctl">${esc(tl('cost.by'))} <select id="src-by"><option value="provider"${M.by === 'provider' ? ' selected' : ''}>${esc(tl('cost.by.provider'))}</option><option value="node"${M.by === 'node' ? ' selected' : ''}>${esc(tl('cost.by.node'))}</option></select></label>`;
  return `<div class="src-sum"><strong class="src-total" data-src-total>${esc(srcUsd(M.usd))}</strong><span class="src-note">${esc(tl('cost.month.note'))}</span>
${acctHTML}${byHTML}</div>${M.account && M.account.on ? srcAccountHTML(M) : ''}
<div class="src-chips">${chips.map(([k, label, n, items]) => `<details class="src-chip" data-src-chip="${k}"${n ? ' data-some="1"' : ''}><summary>${esc(label)} <b>${n}</b></summary>${items.length ? `<ul>${items.slice(0, 50).map((x) => `<li>${esc(x)}</li>`).join('')}</ul>` : `<p>${esc(tl('cost.chip.none'))}</p>`}</details>`).join('')}</div>${freeHTML}`;
}
/* The account's environments: each one's scenario and month, the ones left out, and how the free amounts were taken. */
function srcAccountHTML(M) {
  const partsHTML = M.scenarios.map((s) => `<li>${esc(M.keys.find((k) => k.key === s.environment)?.label || s.environment)}: ${esc(s.label)} ${esc(srcUsd(s.usd))}</li>`).join('');
  const missing = M.account.missing || [];
  return `<div class="src-acct" data-src-acct><p class="src-note">${esc(tl('cost.account.note'))}</p><ul>${partsHTML}</ul>${missing.length ? `<p class="src-note">${esc(tl('cost.account.missing', { month: M.month, envs: new Intl.ListFormat(LOCALE).format(missing) }))}</p>` : ''}</div>`;
}
/* An engine warning in one line: its message, and the rows it names (a row is an id or a {id}). */
function srcWarnText(w) {
  const rows = Array.isArray(w.rows) ? w.rows.map((r) => (r && typeof r === 'object' ? String(r.id || r.sku || JSON.stringify(r)) : String(r))) : [];
  return `${w.environment ? `${w.environment} · ` : ''}${w.node ? `${w.node} · ` : ''}${w.short || w.message}${rows.length ? tl('cost.warn.rows', { rows: rows.slice(0, 8).join(tl('cost.warn.sep')), more: rows.length > 8 ? tl('cost.warn.more', { n: rows.length - 8 }) : '' }) : ''}`;
}
function srcMonthSvg(M) {
  const w = Math.max(320, srcEl.clientWidth - 32), h = 260, padL = 56, padB = 28, padT = 18;
  const max = Math.max(...M.days.map((d) => d.usd), 0.0001), bw = (w - padL - 8) / M.days.length;
  const y = (v) => padT + (h - padT - padB) * (1 - v / max);
  const ticksHTML = [0, 0.5, 1].map((f) => `<g class="src-tick"><line x1="${Number(padL)}" x2="${Number(w - 4)}" y1="${Number(y(max * f))}" y2="${Number(y(max * f))}"/><text x="${Number(padL - 6)}" y="${Number(y(max * f) + 4)}" text-anchor="end">${esc(srcUsd(max * f))}</text></g>`).join('');
  const barsHTML = M.days.map((d, i) => {
    let acc = 0;
    const x = padL + i * bw + 1;
    const segsHTML = M.keys.map((k, ki) => {
      const v = d.stack[k.key] || 0;
      if (!v) return '';
      const y0 = y(acc + v), hh = y(acc) - y0;
      acc += v;
      return `<rect x="${Number(x)}" y="${Number(y0)}" width="${Math.max(1, bw - 2)}" height="${Math.max(0, hh)}" fill="${esc(srcKeyColor(k.key, ki))}"><title>${esc(k.label)} ${esc(srcUsd(v))}</title></rect>`;
    }).join('');
    const marksHTML = (d.overflowHours ? `<circle class="src-over" cx="${Number(x + bw / 2 - 1)}" cy="${Number(y(d.usd) - 8)}" r="4"><title>${esc(tl('cost.day.overflow', { n: Number(d.overflowHours) }))}</title></circle>` : '')
      + (d.atMaxHours ? `<text class="src-flag" x="${Number(x + bw / 2 - 1)}" y="${Number(y(d.usd) - (d.overflowHours ? 14 : 4))}" text-anchor="middle">⚑<title>${esc(tl('cost.day.atmax', { n: Number(d.atMaxHours) }))}</title></text>` : '');
    return `<g class="src-day" data-src-date="${esc(d.date)}" tabindex="0" role="button" aria-label="${esc(d.date)} ${esc(srcUsd(d.usd))}">${segsHTML}<rect class="src-hit" x="${Number(x)}" y="${Number(padT)}" width="${Math.max(1, bw - 2)}" height="${Number(h - padT - padB)}"/>${marksHTML}<text class="src-dlabel" x="${Number(x + bw / 2 - 1)}" y="${Number(h - 10)}" text-anchor="middle">${esc(String(Number(d.date.slice(8))))}</text></g>`;
  }).join('');
  const legendHTML = M.keys.map((k, ki) => `<span class="src-key"><i style="background:${esc(srcKeyColor(k.key, ki))}"></i>${esc(k.label)}</span>`).join('');
  return `<svg class="src-month" width="${Number(w)}" height="${Number(h)}" viewBox="0 0 ${Number(w)} ${Number(h)}" role="img" aria-label="${esc(tl('cost.month.aria', { month: M.month }))}">${ticksHTML}${barsHTML}</svg><div class="src-legend">${legendHTML}</div><p class="src-hint">${esc(tl('cost.month.hint'))}</p>`;
}

/* ---- a day ---- */
function srcRunning(hr) {
  if (hr.range) return tl('cost.running.auto', { n: srcNum(hr.running), from: hr.range[0], to: hr.range[1] });
  if (hr.sku && hr.running) return `${hr.sku} × ${srcNum(hr.running)}`;
  return hr.running ? tl('cost.running', { n: srcNum(hr.running) }) : '';
}
function srcSegText(sg) { return `${sg.label}${sg.rate ? ` ${srcRate(sg.rate)}` : ''} · ${srcUsd(sg.usd)}`; }
/* A row: the bar across the whole column (each meter's length its share), the meters' words under it, two lines folded
   with 広げる for the rest (the requester 10-23: 「長い文章だと棒グラフの中に入り切らずに...になってる / 全文見るために広げるのボタンが
   欲しい」「文字とグラフは縦並びにして」). */
function srcRow(n, k, max, i) {
  const hr = n.hours[k];
  if (n.note) return `<div class="src-row src-noted" data-src-node="${esc(n.node)}"><div class="src-name">${esc(n.label)}</div><div class="src-mid"><span class="src-notetext">${esc(n.note === 'no rule' ? tl('cost.norule') : tl('cost.noload'))}</span></div></div>`;
  const over = hr.load && hr.load.overflow > 0;
  const marksHTML = (hr.atMax ? `<span class="src-flag" title="${esc(tl('cost.atmax'))}">⚑</span>` : '') + (hr.stepChanged ? `<span class="src-step" title="${esc(tl('cost.step'))}">◆</span>` : '');
  const color = (j) => SRC_COLORS[j % SRC_COLORS.length];
  const segsHTML = hr.segments.map((sg, j) => {
    const pct = max > 0 && sg.usd ? (sg.usd / max) * 100 : 0, text = srcSegText(sg);
    return `<span class="src-seg" tabindex="0" role="button" data-src-seg="${Number(j)}" style="width:${Number(pct.toFixed(3))}%;background:${esc(color(j))}" title="${esc(text)}" aria-label="${esc(text)}"></span>`;
  }).join('');
  const partsHTML = hr.segments.map((sg, j) => `<span class="src-part"><i style="background:${esc(color(j))}"></i>${esc(srcSegText(sg))}</span>`).join(' ');
  const open = SRC.open.has(n.node);
  const loadHTML = over ? `<span class="src-red" data-src-over>${esc(hr.load.label)} ${esc(srcNum(hr.load.served))} / ${esc(srcNum(hr.load.demand))} /${esc(SRC_PER[hr.load.per] || hr.load.per)}${esc(tl('cost.load.served'))}</span>` : '';
  return `<div class="src-row${over ? ' src-overrow' : ''}" data-src-node="${esc(n.node)}"><div class="src-name">${esc(n.label)}<small>${esc(srcRunning(hr))}</small>${marksHTML}</div><div class="src-mid"><div class="src-bar">${segsHTML}</div>`
    + `<div class="src-words" data-src-more="${esc(n.node)}"><div class="src-parts${open ? ' open' : ''}" id="src-parts-${Number(i)}" data-src-parts>${partsHTML}</div>`
    + `<button type="button" class="src-more" data-src-more="${esc(n.node)}" aria-controls="src-parts-${Number(i)}" aria-expanded="${esc(String(open))}"${open ? '' : ' hidden'}>${esc(tl(open ? 'cost.less' : 'cost.more'))}</button></div></div>`
    + `<div class="src-usd">${esc(srcUsd(hr.usd))}${loadHTML ? `<br>${loadHTML}` : ''}</div></div>`;
}
/* 広げる only where the folded words are cut (measured after they are drawn); an open row keeps its たたむ. */
function srcMoreFit() {
  for (const b of srcEl.querySelectorAll('button[data-src-more]')) {
    const parts = b.parentElement.querySelector('[data-src-parts]');
    b.hidden = !(SRC.open.has(b.dataset.srcMore) || parts.scrollHeight > parts.clientHeight + 1);
    b.parentElement.classList.toggle('src-cut', !b.hidden);   // the words themselves press too (the button is their edge)
  }
  const all = srcEl.querySelector("[data-src-act='more-all']");
  if (all) all.hidden = !srcEl.querySelector('button[data-src-more]:not([hidden])');
}
function srcDayHtml(D) {
  const k = SRC.hour, hourUsd = D.nodes.reduce((a, n) => a + (n.note ? 0 : n.hours[k].usd), 0) + (D.others.usd[k] || 0);
  const max = Math.max(...D.nodes.flatMap((n) => (n.note ? [] : n.hours.map((h) => h.usd))), 0.0001);
  const rowsHTML = D.nodes.map((n, i) => srcRow(n, k, max, i)).join('')
    + (D.others.count ? `<div class="src-row src-noted"><div class="src-name">${esc(tl('cost.others', { n: Number(D.others.count) }))}</div><div class="src-mid"></div><div class="src-usd">${esc(srcUsd(D.others.usd[k]))}</div></div>` : '');
  const priced = D.nodes.filter((n) => !n.note), allOpen = priced.length > 0 && priced.every((n) => SRC.open.has(n.node));
  const pickHTML = SRC.picked ? srcPicked(D) : '';
  const acctHTML = SRC.month && SRC.month.account && SRC.month.account.on ? `<span class="src-note" data-src-dayacct>${esc(tl('cost.account.day', { scenario: (SRC.month.scenarios.find((s) => s.scenario === SRC.scenario) || {}).label || SRC.scenario }))}</span>` : '';
  return `<div class="src-dayhead"><button type="button" class="wb-btn" data-src-act="month">${esc(tl('cost.back.month'))}</button><strong>${esc(D.date)}</strong>${acctHTML}
<button type="button" class="wb-btn" data-src-act="${SRC.timer ? 'stop' : 'play'}"${reduceMotion ? ` disabled title="${esc(tl('cost.play.reduced'))}"` : ''}>${esc(SRC.timer ? tl('cost.stop') : tl('cost.play'))}</button>
<label class="sr-ctl">${esc(tl('cost.hour'))} <input type="range" id="src-hour" min="0" max="${Number(D.hours.length - 1)}" value="${k}" step="1"></label><span class="src-clock" data-src-clock>${esc(String(D.hours[k]).padStart(2, '0'))}:00</span>
<span class="src-hoursum">${esc(tl('cost.hoursum', { hour: srcUsd(hourUsd), day: srcUsd(D.usd) }))}</span>
<button type="button" class="wb-btn" data-src-act="more-all" aria-expanded="${esc(String(allOpen))}" hidden>${esc(tl(allOpen ? 'cost.less.all' : 'cost.more.all'))}</button></div>
<div class="src-rows">${rowsHTML}</div>${pickHTML ? `<div class="src-price" data-src-price>${pickHTML}</div>` : `<p class="src-hint">${esc(tl('cost.day.hint'))}</p>`}`;
}
function srcPicked(D) {
  const n = D.nodes.find((x) => x.node === SRC.picked.node);
  const sg = n && !n.note ? n.hours[SRC.hour].segments[SRC.picked.seg] : null;
  if (!sg) return '';
  const p = sg.price;
  return `<h4>${esc(n.label)} · ${esc(sg.label)}</h4><dl><dt>${esc(tl('cost.pick.amount'))}</dt><dd>${esc(srcNum(sg.amount))} ${esc(sg.unit)}${sg.rate ? esc(tl('cost.pick.rate', { rate: srcRate(sg.rate), unit: sg.rate.unit })) : ''}</dd><dt>${esc(tl('cost.pick.usd'))}</dt><dd>${esc(srcUsd(sg.usd))}</dd>`
    + (p ? `<dt>${esc(tl('cost.pick.price'))}</dt><dd>${esc(p.sku)} · ${esc(p.unit)}${p.per_units > 1 ? ` · ${esc(tl('cost.pick.per', { n: srcNum(p.per_units) }))}` : ''} · ${esc(p.region)}</dd><dt>${esc(tl('cost.pick.from'))}</dt><dd>${esc({ user: tl('cost.layer.user'), cache: tl('cost.layer.cache'), bundled: tl('cost.layer.bundled') }[p.layer] || p.layer)} · ${esc(tl('cost.pick.line', { file: p.file, line: String(p.index) }))}</dd><dt>source</dt><dd>${esc(p.source)}</dd><dt>effective</dt><dd>${esc(p.effective)}</dd>`
      : `<dt>${esc(tl('cost.pick.price'))}</dt><dd>${esc(tl('cost.pick.noprice'))}</dd>`) + '</dl>';
}

function srcRender(status) {
  if (SRC.mode !== 'cost') return;
  if (status) { setHTML(srcEl, `<p class="src-status">${esc(status)}</p>`); return; }
  if (SRC.error) { setHTML(srcEl, `<p class="src-status src-red">${esc(tl('cost.error', { why: SRC.error }))}</p>`); return; }
  if (!SRC.month) return;
  if (SRC.day) { setHTML(srcEl, srcDayHtml(SRC.day)); srcMoreFit(); }
  else setHTML(srcEl, `${srcSummary(SRC.month)}${srcMonthSvg(SRC.month)}`);
}

/* ---- wiring ---- */
$('sr-mode-3d').addEventListener('click', () => srcSetMode('3d'));
$('sr-mode-cost').addEventListener('click', () => srcSetMode('cost'));
new ResizeObserver(() => { if (SRC.mode === 'cost' && SRC.day) srcMoreFit(); }).observe(srcEl);   // a narrower page cuts more words
$('sr-scn').addEventListener('change', () => { SRC.scenario = $('sr-scn').value; Object.assign(SRC, { month: null, day: null }); srcLoad(); });
srcEl.addEventListener('click', (e) => {
  const act = e.target.closest('[data-src-act]');
  if (act) {
    if (act.dataset.srcAct === 'month') srcBackToMonth();
    else if (act.dataset.srcAct === 'acct-on' || act.dataset.srcAct === 'acct-off') {
      const on = act.dataset.srcAct === 'acct-on';
      if (on !== !!(SRC.month && SRC.month.account.on)) { SRC.account = on; Object.assign(SRC, { month: null, day: null, date: null }); srcLoad(); }
    }
    else if (act.dataset.srcAct === 'play') srcPlay();
    else if (act.dataset.srcAct === 'more-all') {
      const ids = SRC.day.nodes.filter((n) => !n.note).map((n) => n.node);
      SRC.open = ids.every((id) => SRC.open.has(id)) ? new Set() : new Set(ids);
      srcRender();
    }
    else { srcStop(); srcRender(); }
    return;
  }
  const day = e.target.closest('[data-src-date]');
  if (day) { SRC.hour = 0; srcOpenDay(day.dataset.srcDate); return; }
  const more = e.target.closest('[data-src-more]');
  if (more && !more.querySelector(':scope > button[data-src-more][hidden]')) {   // words that are not cut have nothing to show
    const id = more.dataset.srcMore;
    if (!SRC.open.delete(id)) SRC.open.add(id);
    srcRender();
    srcEl.querySelector(`button[data-src-more="${CSS.escape(id)}"]`)?.focus();   // the key that pressed it stays on it
    return;
  }
  const seg = e.target.closest('[data-src-seg]');
  if (seg) { SRC.picked = { node: seg.closest('[data-src-node]').dataset.srcNode, seg: Number(seg.dataset.srcSeg) }; srcRender(); }
});
srcEl.addEventListener('keydown', (e) => {
  if ((e.key === 'Enter' || e.key === ' ') && e.target.closest('[data-src-date], [data-src-seg]')) { e.preventDefault(); e.target.click(); }
});
srcEl.addEventListener('input', (e) => {
  if (e.target.id === 'src-hour') { srcStop(); SRC.hour = Number(e.target.value); srcRender(); }
});
srcEl.addEventListener('change', (e) => {
  if (e.target.id === 'src-by') { SRC.by = e.target.value; Object.assign(SRC, { month: null }); srcLoad(); }
});
