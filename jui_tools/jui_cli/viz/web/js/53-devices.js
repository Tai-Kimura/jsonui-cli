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
const DEV_LEVEL = { ok: '余裕あり', busy: '混んでいる', high: '高負荷' };
const DEV_STATE = { booted: '起動中', device: '接続中', offline: 'オフライン', unauthorized: '未許可', recovery: 'リカバリー', sideload: 'サイドロード', bootloader: 'ブートローダー' };
const DEV_KINDS = [['ios', 'iOS シミュレーター'], ['emulator', 'Android エミュレーター'], ['phone', 'Android 実機']];
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
  if (!u) return '<span class="dev-who">使っている人: 不明（記録から分からない）</span>';
  const how = u.how === 'test' ? 'テスト実行中（コマンドがこの機器を指定）'
    : u.how === 'process' ? '推定（そのセッションの下のプロセスがこの機器を指定）'
      : `推定（最後にこの機器を指定したコマンド ${devClock(u.at || 0)}）`;
  const others = (u.others || []).map(labelOf).filter(Boolean);
  const whoHTML = label ? `${pill(label, DEF[label].role)} ${esc(DEF[label].agent)}` : 'ロボットはもういない';
  return `<span class="dev-who">使っている人: ${whoHTML}<span class="dev-guess">${esc(how)}</span>${others.length ? `<span class="dev-guess">ほかに ${esc(others.join('・'))}</span>` : ''}</span>`;
}
function devRowHTML(d) {
  const label = devRobot(d);
  const innerRowHTML = `<span class="dev-name">${esc(String(d.name || d.id))}</span><span class="dev-note">${esc(DEV_STATE[d.state] || String(d.state || ''))} · ${esc(d.id)}</span>${devWhoHTML(d, label)}`;
  return label
    ? `<li><button type="button" class="dev-row" data-dev-robot="${esc(label)}" data-dev-id="${esc(d.id)}" data-fk="dev-${esc(d.id)}" title="${esc(label)} の部屋へ移って選ぶ">${innerRowHTML}</button></li>`
    : `<li><div class="dev-row" data-dev-id="${esc(d.id)}">${innerRowHTML}</div></li>`;
}
function devLoadHTML(m) {
  if (!m) return '<div class="dev-load"><p>負荷はまだ届いていない</p></div>';
  const load = Array.isArray(m.load) ? m.load : null, ratio = load && m.cpus ? (load[0] / m.cpus).toFixed(2) : null;
  const gib = m.memTotal ? `${Math.round(m.memTotal / 2 ** 30)} GiB` : '';
  return `<div class="dev-load" data-load="${esc(m.level || '')}" data-dev-load><p class="dev-level">${esc(DEV_LEVEL[m.level] || '不明')}</p>`
    + `<p>load（1 / 5 / 15 分）${load ? esc(load.map((x) => x.toFixed(2)).join(' / ')) : '不明'}${m.cpus ? `（コア ${esc(String(m.cpus))}、混み具合 ${esc(String(ratio))}）` : ''}</p>`
    + `<p>メモリの空き ${m.memFreePct != null ? `${esc(String(m.memFreePct))} %` : '不明'}${gib ? `（合計 ${esc(gib)}）` : ''}</p>`
    + `<p class="dev-note">${esc(new Date(m.at || 0).toTimeString().slice(0, 8))} に測った · 色は 混み具合（load ÷ コア）0.7 / 1.0 と メモリの空き 25 % / 10 % の悪い方</p></div>`;
}
function renderDevices() {
  const { live, m, devices } = devData();
  const btn = $('btn-devices');
  btn.hidden = !live;
  if (!live) return;
  const lvl = m && DEV_LEVEL[m.level] ? m.level : '';
  if (btn.dataset.load !== lvl) btn.dataset.load = lvl;
  setText(btn, devices.length ? `デバイス ${devices.length}` : 'デバイス');
  const aria = `デバイス（負荷: ${DEV_LEVEL[lvl] || '不明'}、起動中の機器 ${devices.length} 台）`;
  if (btn.getAttribute('aria-label') !== aria) btn.setAttribute('aria-label', aria);
  if (devPane.hidden) return;
  const rows = devices.map((d) => [d, devRobot(d)]);
  keyed($('dev-body'), JSON.stringify([m, NAMES.rev, rows.map(([d, label]) => [d, label])]), () => {
    const groupsHTML = DEV_KINDS.map(([kind, title]) => {
      const mine = devices.filter((d) => devKind(d) === kind);
      return `<section class="dev-group" data-dev-kind="${esc(kind)}"><h3>${esc(title)} ${mine.length} 台</h3>${mine.length ? `<ul class="dev-list">${mine.map((d) => devRowHTML(d)).join('')}</ul>` : ''}</section>`;
    }).join('');
    return `${devLoadHTML(m)}${groupsHTML}<p class="dev-note">使っている人は記録からの推定です（テストのコマンド、機器を指定したプロセスとそのセッション、最後に機器を指定したコマンドの順）。名前のある行を押すと、そのロボットの部屋へ移って選びます。ここから機器は止めません</p>`;
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
/* A row with its robot: that robot's room, the robot picked. The room remembers it first, so the switch's own pick
   (robotToPick) is this robot, not the one last picked there. */
function devGoRobot(label, opener) {
  const proj = projectOfRobot(label);
  devClose(false);
  if (proj) LAST_ROBOT.set(proj, label);
  if (proj && PROJECT[proj] && UI.project !== proj) setProject(proj, { camera: false });
  if (rbState.id !== label) openRobot(label, opener);
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
