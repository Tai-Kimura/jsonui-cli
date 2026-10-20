/* ---------- the cost simulator (plan 2026-10-20-jui-viz-backend-load-and-cost-simulator, L-C) ----------
   Requester 10-20: 「バックエンドの負荷とコストシミュレータをサーバーの3dと切り替えで表示出来るようにしたい … 1ヶ月のコストグラフ …
   1日のうちで横棒グラフでどのノードのコストがどう変わっていくかをシミュレーション」; 「棒の中とかに何がどのくらいコストを生んでるか
   表示して欲しい 例えばリクエスト100/sec」; 「捌ききれなくなった時に赤字になって捌けた数/リクエスト数みたいな表示」.

   The page computes nothing: SOURCE.infraCost asks the server (POST /api/infra-cost), which runs document_tools' load,
   engine and view and gives the shapes drawn here. 3D / コスト on the server room's header switches the stage: the 3D
   pauses (no frame drawn) while the cost is shown. The month: the days stacked by provider or by node, a red mark on a
   day with an hour over capacity, a flag on one at the autoscale's top, the sum, and the counts of what is not priced
   (never hidden). A day: the top nodes' bars hour by hour (play, stop, the hour's slider), each bar its meters with the
   quantity's rate and the charge; over capacity in red as 捌けた / 来た. A meter pressed shows the price it used. */
const SRC = { mode: '3d', seq: 0, scenario: null, by: 'provider', month: null, day: null, date: null, hour: 0, timer: 0,
  playMs: 700, picked: null, error: '' };
const srcEl = $('sr-cost');
const SRC_PER = { second: 'sec', minute: 'min', hour: 'h', day: 'day', month: 'mo' };
const SRC_COLORS = ['#4e79a7', '#f28e2b', '#59a14f', '#e15759', '#76b7b2', '#edc948', '#b07aa1', '#ff9da7', '#9c755f', '#bab0ac'];

function srcUsd(v) {
  if (v === null || v === undefined) return '単価なし';
  const digits = Math.abs(v) < 1 && v !== 0 ? 4 : 2;
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', minimumFractionDigits: 2, maximumFractionDigits: digits }).format(v);
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
  if (mode === '3d') {
    srcStop();
    if (SR.view && !SR.view.raf && SR.view.loop) SR.view.loop();
    return;
  }
  if (!SRC.month) srcLoad();
}
function srCostReset() {   // the server room closed (56-server-room.js srClose): back to 3D, nothing kept
  srcStop();
  Object.assign(SRC, { mode: '3d', scenario: null, month: null, day: null, date: null, hour: 0, picked: null, error: '' });
  SR.paused = false;
  $('sr-mode-3d').setAttribute('aria-pressed', 'true');
  $('sr-mode-cost').setAttribute('aria-pressed', 'false');
  $('sr-scn-ctl').hidden = true;
  srcEl.hidden = true;
  setHTML(srcEl, '');
}

/* ---- asking the server ---- */
async function srcAsk(extra) {
  const seq = ++SRC.seq;
  const got = typeof SOURCE.infraCost === 'function' ? await SOURCE.infraCost(SR.project, { seq, scenario: SRC.scenario, ...extra })
    : { ok: false, reason: 'unreadable', message: 'このページでは計算できない' };
  return seq === SRC.seq && SRC.mode === 'cost' ? got : null;   // an older answer, or the view left: dropped
}
async function srcLoad() {
  SRC.error = '';
  srcRender('読み込んでいます…');
  const got = await srcAsk({ by: SRC.by });
  if (!got) return;
  if (!got.ok) { SRC.error = got.message || got.reason || '読めなかった'; SRC.month = null; srcRender(); return; }
  SRC.scenario = got.scenario;
  SRC.month = { ...got.month, scenarios: got.scenarios, problems: got.problems, prices: got.prices };
  setHTML($('sr-scn'), got.scenarios.map((s) => `<option value="${esc(s.id)}"${s.id === got.scenario ? ' selected' : ''}>${esc(s.label)}（${esc(s.month)}）</option>`).join(''));
  srLog(`コスト: ${got.scenarios.find((s) => s.id === got.scenario).label} を計算した（${srcUsd(got.month.usd)}）`);
  if (SRC.date) await srcOpenDay(SRC.date); else srcRender();
}
async function srcOpenDay(date) {
  const got = await srcAsk({ date });
  if (!got) return;
  if (!got.ok) { SRC.error = got.message || '読めなかった'; srcRender(); return; }
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
    ['noPrice', '単価なし', M.noPrice.length, M.noPrice.map((x) => `${x.node} · ${x.meter}（${x.sku}・${x.unit}）`)],
    ['noRule', '規則なし', M.noRule.length, M.noRule],
    ['loadUndefined', '負荷未定義', M.loadUndefined.length, M.loadUndefined],
    ['overflow', '容量を超えた node', Object.keys(M.overflowHours).length, Object.entries(M.overflowHours).map(([n, h]) => `${n}: ${h} 時間`)],
    ['problems', '負荷定義の警告', M.problems.count, M.problems.first.map((p) => `${p.file} ${p.path}: ${p.message}`)],
  ];
  return `<div class="src-sum"><strong class="src-total" data-src-total>${esc(srcUsd(M.usd))}</strong><span class="src-note">1 か月の概算（USD・オンデマンド。予約・割引・税は入っていない）</span>
<label class="sr-ctl">積み上げ <select id="src-by"><option value="provider"${M.by === 'provider' ? ' selected' : ''}>provider ごと</option><option value="node"${M.by === 'node' ? ' selected' : ''}>node ごと</option></select></label></div>
<div class="src-chips">${chips.map(([k, label, n, items]) => `<details class="src-chip" data-src-chip="${k}"${n ? ' data-some="1"' : ''}><summary>${esc(label)} <b>${n}</b></summary>${items.length ? `<ul>${items.slice(0, 50).map((x) => `<li>${esc(x)}</li>`).join('')}</ul>` : '<p>なし</p>'}</details>`).join('')}</div>`;
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
    const marksHTML = (d.overflowHours ? `<circle class="src-over" cx="${Number(x + bw / 2 - 1)}" cy="${Number(y(d.usd) - 8)}" r="4"><title>${Number(d.overflowHours)} 時間、容量を超えた</title></circle>` : '')
      + (d.atMaxHours ? `<text class="src-flag" x="${Number(x + bw / 2 - 1)}" y="${Number(y(d.usd) - (d.overflowHours ? 14 : 4))}" text-anchor="middle">⚑<title>${Number(d.atMaxHours)} 時間、自動スケールの上限</title></text>` : '');
    return `<g class="src-day" data-src-date="${esc(d.date)}" tabindex="0" role="button" aria-label="${esc(d.date)} ${esc(srcUsd(d.usd))}">${segsHTML}<rect class="src-hit" x="${Number(x)}" y="${Number(padT)}" width="${Math.max(1, bw - 2)}" height="${Number(h - padT - padB)}"/>${marksHTML}<text class="src-dlabel" x="${Number(x + bw / 2 - 1)}" y="${Number(h - 10)}" text-anchor="middle">${esc(String(Number(d.date.slice(8))))}</text></g>`;
  }).join('');
  const legendHTML = M.keys.map((k, ki) => `<span class="src-key"><i style="background:${esc(srcKeyColor(k.key, ki))}"></i>${esc(k.label)}</span>`).join('');
  return `<svg class="src-month" width="${Number(w)}" height="${Number(h)}" viewBox="0 0 ${Number(w)} ${Number(h)}" role="img" aria-label="${esc(M.month)} の日ごとのコスト">${ticksHTML}${barsHTML}</svg><div class="src-legend">${legendHTML}</div><p class="src-hint">棒を押すと、その日の 1 日を再生します。</p>`;
}

/* ---- a day ---- */
function srcRunning(hr) {
  if (hr.range) return `稼働 ${srcNum(hr.running)} 台（自動、${hr.range[0]}〜${hr.range[1]}）`;
  if (hr.sku && hr.running) return `${hr.sku} × ${srcNum(hr.running)}`;
  return hr.running ? `稼働 ${srcNum(hr.running)} 台` : '';
}
function srcSegText(sg) { return `${sg.label}${sg.rate ? ` ${srcRate(sg.rate)}` : ''} · ${srcUsd(sg.usd)}`; }
function srcRow(n, k, max, barPx) {
  const hr = n.hours[k];
  if (n.note) return `<div class="src-row src-noted" data-src-node="${esc(n.node)}"><div class="src-name">${esc(n.label)}</div><div class="src-bar"><span class="src-notetext">${esc(n.note === 'no rule' ? '規則なし' : '負荷未定義')}</span></div></div>`;
  const over = hr.load && hr.load.overflow > 0;
  const marksHTML = (hr.atMax ? '<span class="src-flag" title="自動スケールの上限">⚑</span>' : '') + (hr.stepChanged ? '<span class="src-step" title="型が変わった">◆</span>' : '');
  const outside = [];
  const segsHTML = hr.segments.map((sg, i) => {
    const pct = max > 0 && sg.usd ? (sg.usd / max) * 100 : 0, text = srcSegText(sg);
    const fits = pct / 100 * barPx >= text.length * 7 + 12;
    if (!fits) outside.push(text);
    return `<span class="src-seg" tabindex="0" role="button" data-src-seg="${i}" style="width:${Number(pct.toFixed(3))}%;background:${esc(SRC_COLORS[i % SRC_COLORS.length])}" title="${esc(text)}" aria-label="${esc(text)}">${fits ? esc(text) : ''}</span>`;
  }).join('');
  const noPrice = hr.segments.filter((sg) => sg.usd === null).map((sg) => `${sg.label}${sg.rate ? ` ${srcRate(sg.rate)}` : ''} · 単価なし`);
  const loadHTML = over ? `<span class="src-red" data-src-over>${esc(hr.load.label)} ${esc(srcNum(hr.load.served))} / ${esc(srcNum(hr.load.demand))} /${esc(SRC_PER[hr.load.per] || hr.load.per)}（捌けた / 来た）</span>` : '';
  return `<div class="src-row${over ? ' src-overrow' : ''}" data-src-node="${esc(n.node)}"><div class="src-name">${esc(n.label)}<small>${esc(srcRunning(hr))}</small>${marksHTML}</div><div class="src-bar">${segsHTML}<span class="src-out">${esc([...outside, ...noPrice].join('　'))}</span></div><div class="src-usd">${esc(srcUsd(hr.usd))}${loadHTML ? `<br>${loadHTML}` : ''}</div></div>`;
}
function srcDayHtml(D) {
  const k = SRC.hour, hourUsd = D.nodes.reduce((a, n) => a + (n.note ? 0 : n.hours[k].usd), 0) + (D.others.usd[k] || 0);
  const max = Math.max(...D.nodes.flatMap((n) => (n.note ? [] : n.hours.map((h) => h.usd))), 0.0001);
  const barPx = Math.max(160, srcEl.clientWidth - 420);
  const rowsHTML = D.nodes.map((n) => srcRow(n, k, max, barPx)).join('')
    + (D.others.count ? `<div class="src-row src-noted"><div class="src-name">その他（${Number(D.others.count)}）</div><div class="src-bar"></div><div class="src-usd">${esc(srcUsd(D.others.usd[k]))}</div></div>` : '');
  const pickHTML = SRC.picked ? srcPicked(D) : '';
  return `<div class="src-dayhead"><button type="button" class="wb-btn" data-src-act="month">← 1 か月</button><strong>${esc(D.date)}</strong>
<button type="button" class="wb-btn" data-src-act="${SRC.timer ? 'stop' : 'play'}"${reduceMotion ? ' disabled title="動きを減らす設定のため、再生しません"' : ''}>${SRC.timer ? '止める' : '再生'}</button>
<label class="sr-ctl">時刻 <input type="range" id="src-hour" min="0" max="${Number(D.hours.length - 1)}" value="${k}" step="1"></label><span class="src-clock" data-src-clock>${esc(String(D.hours[k]).padStart(2, '0'))}:00</span>
<span class="src-hoursum">この時間 ${esc(srcUsd(hourUsd))}・この日 ${esc(srcUsd(D.usd))}</span></div>
<div class="src-rows">${rowsHTML}</div>${pickHTML ? `<div class="src-price" data-src-price>${pickHTML}</div>` : '<p class="src-hint">区間を押すと、使った単価の出どころが出ます。</p>'}`;
}
function srcPicked(D) {
  const n = D.nodes.find((x) => x.node === SRC.picked.node);
  const sg = n && !n.note ? n.hours[SRC.hour].segments[SRC.picked.seg] : null;
  if (!sg) return '';
  const p = sg.price;
  return `<h4>${esc(n.label)} · ${esc(sg.label)}</h4><dl><dt>量</dt><dd>${esc(srcNum(sg.amount))} ${esc(sg.unit)}${sg.rate ? `（${esc(srcRate(sg.rate))} ${esc(sg.rate.unit)}）` : ''}</dd><dt>金額</dt><dd>${esc(srcUsd(sg.usd))}</dd>`
    + (p ? `<dt>単価</dt><dd>${esc(p.sku)} · ${esc(p.unit)}${p.per_units > 1 ? ` · ${esc(srcNum(p.per_units))} あたり` : ''} · ${esc(p.region)}</dd><dt>出どころ</dt><dd>${esc({ user: '利用者のファイル', cache: '取得した単価', bundled: '同梱の表' }[p.layer] || p.layer)} · ${esc(p.file)} の ${esc(String(p.index))} 行目</dd><dt>source</dt><dd>${esc(p.source)}</dd><dt>effective</dt><dd>${esc(p.effective)}</dd>`
      : '<dt>単価</dt><dd>単価なし（この sku の単価が、どの層にもない）</dd>') + '</dl>';
}

function srcRender(status) {
  if (SRC.mode !== 'cost') return;
  if (status) { setHTML(srcEl, `<p class="src-status">${esc(status)}</p>`); return; }
  if (SRC.error) { setHTML(srcEl, `<p class="src-status src-red">コストを出せません: ${esc(SRC.error)}</p>`); return; }
  if (!SRC.month) return;
  if (SRC.day) setHTML(srcEl, srcDayHtml(SRC.day));
  else setHTML(srcEl, `${srcSummary(SRC.month)}${srcMonthSvg(SRC.month)}`);
}

/* ---- wiring ---- */
$('sr-mode-3d').addEventListener('click', () => srcSetMode('3d'));
$('sr-mode-cost').addEventListener('click', () => srcSetMode('cost'));
$('sr-scn').addEventListener('change', () => { SRC.scenario = $('sr-scn').value; Object.assign(SRC, { month: null, day: null }); srcLoad(); });
srcEl.addEventListener('click', (e) => {
  const act = e.target.closest('[data-src-act]');
  if (act) {
    if (act.dataset.srcAct === 'month') srcBackToMonth();
    else if (act.dataset.srcAct === 'play') srcPlay();
    else { srcStop(); srcRender(); }
    return;
  }
  const day = e.target.closest('[data-src-date]');
  if (day) { SRC.hour = 0; srcOpenDay(day.dataset.srcDate); return; }
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
