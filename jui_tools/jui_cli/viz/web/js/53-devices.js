/* ---------- the デバイス button: this machine's load and the devices up (ticket 2026-10-20-jui-viz-device-panel-machine-
   load-and-emulators). Requester: 「ヘッダのメニューにデバイスボタン用意してそれ押すとサイドのボードの位置くらいに全部出る 負荷に
   応じてボタンの色合いが変わる」「デバイスの担当セッションわかる時はクリックでそのロボット選択状態にして欲しい 部屋の移動」.
   Live only (the demo has no machine). The button's colour is the server's level (sources/machine.py: the worse of the
   load over the cores and the free memory); the pane takes the side panel's place. Who uses a device is the server's
   estimate (ingest.devices_slice), and the row says how it was told; a row whose robot is known goes to its room and
   picks it, the robot pressed winning over the room's last picked one (LAST_ROBOT). Nothing here starts or stops a
   device. ---------- */
const devPane = $('dev-pane');
const DEV = { opener: null };
const DEV_LEVEL = { ok: tl('dev.level.ok'), busy: tl('dev.level.busy'), high: tl('dev.level.high') };
const DEV_STATE = { booted: tl('dev.state.booted'), device: tl('dev.state.device'), offline: tl('dev.state.offline'), unauthorized: tl('dev.state.unauthorized'), recovery: tl('dev.state.recovery'), sideload: tl('dev.state.sideload'), bootloader: tl('dev.state.bootloader') };
const DEV_KINDS = [['ios', tl('dev.kind.ios')], ['emulator', tl('dev.kind.emulator')], ['phone', tl('dev.kind.phone')]];
const devKind = (d) => (d.platform === 'ios' ? 'ios' : /^emulator-\d+$/.test(d.id) ? 'emulator' : 'phone');
const devClock = (at) => new Date(at).toTimeString().slice(0, 5);
function devData() {
  const live = SOURCE.mode === 'live' && typeof LIVE !== 'undefined';
  const m = live && LIVE.slices.machine && typeof LIVE.slices.machine === 'object' ? LIVE.slices.machine : null;
  const devices = live && Array.isArray(LIVE.slices.devices) ? LIVE.slices.devices.filter((d) => d && typeof d.id === 'string') : [];
  return { live, m, devices };
}
/* The robot a device's row goes to: still in a room (not gone, not walking out), else none. */
function devRobot(d) {
  const label = d.usedBy ? labelOf(d.usedBy.agentId) : null;
  if (!label || !DEF[label] || !ROBOT_DEFS.some((x) => x.id === label) || LIVE.leaving[label]) return null;
  return label;
}
function devWhoHTML(d, label) {
  const u = d.usedBy;
  if (!u) return `<span class="dev-who">${esc(tl('dev.who.unknown'))}</span>`;
  const how = u.how === 'test' ? tl('dev.how.test')
    : u.how === 'process' ? tl('dev.how.process')
      : tl('dev.how.command', { at: devClock(u.at || 0) });
  const others = (u.others || []).map(labelOf).filter(Boolean);
  const whoHTML = label ? `${pill(label, DEF[label].role)} ${esc(DEF[label].agent)}` : esc(tl('dev.who.gone'));
  return `<span class="dev-who">${esc(tl('dev.who.label'))} ${whoHTML}<span class="dev-guess">${esc(how)}</span>${others.length ? `<span class="dev-guess">${esc(tl('dev.who.others', { names: others.join(tl('dev.who.sep')) }))}</span>` : ''}</span>`;
}
function devRowHTML(d) {
  const label = devRobot(d);
  const innerRowHTML = `<span class="dev-name">${esc(String(d.name || d.id))}</span><span class="dev-note">${esc(DEV_STATE[d.state] || String(d.state || ''))} · ${esc(d.id)}</span>${devWhoHTML(d, label)}`;
  return label
    ? `<li><button type="button" class="dev-row" data-dev-robot="${esc(label)}" data-dev-id="${esc(d.id)}" data-fk="dev-${esc(d.id)}" title="${esc(tl('dev.row.go', { name: label }))}">${innerRowHTML}</button></li>`
    : `<li><div class="dev-row" data-dev-id="${esc(d.id)}">${innerRowHTML}</div></li>`;
}
/* The machine's load as a person reads it (the requester, 10-23: what the "load" at the top stood for was hard to
   tell): the CPU's busyness as a per cent of its cores (the 1-minute load / the cores) with a bar marked at 100 %, what
   100 % means, the three load averages in small type with the way they go, the free memory the same way, and the
   colour rule in words. The bars' colours are the box's own thresholds (sources/machine.py: LOAD_BUSY / LOAD_HIGH,
   MEM_BUSY / MEM_HIGH). */
const DEV_CPU = { busy: 70, high: 100, max: 200 }, DEV_MEM = { busy: 25, high: 10 };
const DEV_TREND = { up: tl('dev.load.trend.up'), down: tl('dev.load.trend.down'), flat: tl('dev.load.trend.flat') };
const devCpuTone = (pct) => (pct >= DEV_CPU.high ? 'high' : pct >= DEV_CPU.busy ? 'busy' : 'ok');
const devMemTone = (free) => (free < DEV_MEM.high ? 'high' : free < DEV_MEM.busy ? 'busy' : 'ok');
// the 1-minute load against the 15-minute one: a tenth either way is a change
const devTrend = (load) => (load[0] > load[2] * 1.1 ? 'up' : load[0] < load[2] * 0.9 ? 'down' : 'flat');
function devBarHTML(kind, fill, tone, mark) {
  const width = `${Math.max(0, Math.min(100, fill))}%`;
  return `<span class="dev-bar" data-bar="${esc(kind)}" data-tone="${esc(tone)}" aria-hidden="true"><span class="dev-bar-fill" style="width:${esc(width)}"></span>`
    + (mark != null ? `<span class="dev-bar-mark" style="left:${esc(String(mark) + '%')}"></span>` : '') + '</span>';
}
function devLoadHTML(m) {
  if (!m) return `<div class="dev-load"><p>${esc(tl('dev.load.none'))}</p></div>`;
  const load = Array.isArray(m.load) && m.load.length >= 3 ? m.load : null;
  const pct = load && m.cpus ? Math.round((load[0] / m.cpus) * 100) : null;
  const gib = m.memTotal ? `${Math.round(m.memTotal / 2 ** 30)} GiB` : '';
  const free = m.memFreePct != null ? Math.round(m.memFreePct) : null;
  return `<div class="dev-load" data-load="${esc(m.level || '')}" data-dev-load>`
    + `<p class="dev-stat" data-dev-cpu="${esc(pct != null ? String(pct) : '')}"><span>${esc(tl('dev.cpu.head', { pct: pct != null ? String(pct) : tl('dev.unknown') }))}</span>`
    + `<span class="dev-level">${esc(DEV_LEVEL[m.level] || tl('dev.level.unknown'))}</span></p>`
    + (pct != null ? devBarHTML('cpu', (pct / DEV_CPU.max) * 100, devCpuTone(pct), (DEV_CPU.high / DEV_CPU.max) * 100) : '')
    + (m.cpus ? `<p class="dev-what" data-dev-what>${esc(tl('dev.cpu.what', { cpus: String(m.cpus) }))}</p>` : '')
    + (load ? `<p class="dev-note" data-dev-recent>${esc(tl('dev.load.recent', { a: load[0].toFixed(1), b: load[1].toFixed(1), c: load[2].toFixed(1), trend: DEV_TREND[devTrend(load)] }))}</p>` : '')
    + `<p class="dev-stat" data-dev-mem="${esc(free != null ? String(free) : '')}"><span>${esc(tl('dev.mem.head', { pct: free != null ? String(free) : tl('dev.unknown') }))}${gib ? esc(tl('dev.mem.of', { total: gib })) : ''}</span></p>`
    + (free != null ? devBarHTML('mem', free, devMemTone(free)) : '')
    + `<p class="dev-note" data-dev-rule>${esc(tl('dev.load.rule', { cb: String(DEV_CPU.busy), ch: String(DEV_CPU.high), mb: String(DEV_MEM.busy), mh: String(DEV_MEM.high) }))}</p>`
    + `<p class="dev-note">${esc(tl('dev.load.at', { at: new Date(m.at || 0).toTimeString().slice(0, 8) }))}</p></div>`;
}
function renderDevices() {
  const { live, m, devices } = devData();
  const btn = $('btn-devices');
  btn.hidden = !live;
  if (!live) return;
  const lvl = m && DEV_LEVEL[m.level] ? m.level : '';
  if (btn.dataset.load !== lvl) btn.dataset.load = lvl;
  setText(btn, devices.length ? tl('dev.button.count', { count: devices.length }) : tl('dev.button'));
  const aria = tl('dev.button.aria', { level: DEV_LEVEL[lvl] || tl('dev.unknown'), n: devices.length });
  if (btn.getAttribute('aria-label') !== aria) btn.setAttribute('aria-label', aria);
  if (devPane.hidden) return;
  const rows = devices.map((d) => [d, devRobot(d)]);
  keyed($('dev-body'), JSON.stringify([m, NAMES.rev, rows.map(([d, label]) => [d, label])]), () => {
    const groupsHTML = DEV_KINDS.map(([kind, title]) => {
      const mine = devices.filter((d) => devKind(d) === kind);
      return `<section class="dev-group" data-dev-kind="${esc(kind)}"><h3>${esc(tl('dev.group.title', { kind: title, n: mine.length }))}</h3>${mine.length ? `<ul class="dev-list">${mine.map((d) => devRowHTML(d)).join('')}</ul>` : ''}</section>`;
    }).join('');
    return `${devLoadHTML(m)}${groupsHTML}<p class="dev-note">${esc(tl('dev.pane.note'))}</p>`;
  });
}
/* Under the header, however tall it wraps (a fixed top hid the header's own buttons, this one among them). */
function devPlace() { devPane.style.top = `${Math.round(document.querySelector('.topbar').getBoundingClientRect().bottom)}px`; }
function devOpen(opener) {
  DEV.opener = opener || null;
  devPlace();
  devPane.hidden = false;
  $('btn-devices').setAttribute('aria-expanded', 'true');
  renderDevices();
  $('dev-close').focus({ preventScroll: true });
}
function devClose(back = true) {
  if (devPane.hidden) return;
  devPane.hidden = true;
  $('btn-devices').setAttribute('aria-expanded', 'false');
  const to = DEV.opener; DEV.opener = null;
  if (back && to && document.contains(to)) to.focus({ preventScroll: true });
}
/* A row with its robot: the robot picked as any pick is (selectRobot, 50-panel.js) — outside the view, its room is
   remembered first and switched to, so the switch's own pick is this robot, not the one last picked there. */
function devGoRobot(label, opener) {
  devClose(false);
  selectRobot(label, opener);
}
$('btn-devices').addEventListener('click', (e) => (devPane.hidden ? devOpen(e.currentTarget) : devClose()));
$('dev-close').addEventListener('click', () => devClose());
window.addEventListener('resize', () => { if (!devPane.hidden) devPlace(); });
devPane.addEventListener('keydown', (e) => { if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); devClose(); } });
devPane.addEventListener('click', (e) => {
  const row = e.target.closest('[data-dev-robot]');
  if (row) devGoRobot(row.dataset.devRobot, $('btn-devices'));
});
setInterval(renderDevices, 1000);   // the slices come every 5 s (load) and 10 s (devices); the button follows them
renderDevices();
