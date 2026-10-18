/* ---------- controls and main loop ---------- */
// Demo: the script's clock, with play / speed. Live: the wall clock (the local time of day in seconds), no
// controls; the state comes from the server (25-net.js).
let simT = START_AT, prevSim = -0.001, playing = true, speed = 1, lastMs = performance.now(), lastPanel = -1e9, lastBoard = -1e9;
$('btn-play').addEventListener('click', (e) => { playing = !playing; e.currentTarget.textContent = playing ? '一時停止' : '再生'; e.currentTarget.setAttribute('aria-pressed', String(!playing)); });
$('btn-speed').addEventListener('click', (e) => { speed = speed === 1 ? 3 : 1; e.currentTarget.textContent = `速度 ×${speed}`; });

/* ?fps=1: frames per second in the corner, from the requestAnimationFrame intervals (plan 10 §7). */
const fpsMeter = new URLSearchParams(location.search).get('fps') === '1' ? { el: document.createElement('p'), n: 0, from: performance.now() } : null;
if (fpsMeter) { fpsMeter.el.className = 'fps-meter'; fpsMeter.el.setAttribute('aria-hidden', 'true'); document.body.append(fpsMeter.el); }

function frame(ms) {
  const dt = Math.min(0.05, Math.max(0, (ms - lastMs) / 1000));
  lastMs = ms;
  if (SOURCE.mode === 'demo') {
    if (playing) simT += dt * speed;
    const t = ((simT % LOOP) + LOOP) % LOOP;
    emitEvents(prevSim, simT); prevSim = simT;
    latestModel = computeModel(t, Math.floor(simT / LOOP));
    updateRobotStates(simT, t, latestModel.perms);
  } else {
    simT = secOfDay(Date.now());
    latestModel = computeModel();
  }
  if (has3D) {
    if (ms - lastBoard > 200 && !(SOURCE.mode === 'live' && TOWER.on)) { redrawBoards(latestModel, ms / 1000); lastBoard = ms; }   // the building hides the boards
    update3D(latestModel, ms / 1000, dt);
  }
  if (ms - lastPanel > 250) {
    renderPanel(latestModel);
    renderTicker();
    renderWhiteboard(latestModel, false);
    renderTaskBoard(latestModel);
    renderRobot(latestModel);
    renderLog(false);
    $('chip-clock').textContent = fmtClock(BASE_CLOCK + simT);
    if (SOURCE.mode === 'live') liveChrome();
    lastPanel = ms;
  }
  if (fpsMeter) {
    fpsMeter.n += 1;
    if (ms - fpsMeter.from >= 1000) { fpsMeter.el.textContent = `${Math.round((fpsMeter.n * 1000) / (ms - fpsMeter.from))} fps`; fpsMeter.n = 0; fpsMeter.from = ms; }
  }
  requestAnimationFrame(frame);
}

/* ---------- live only: the connection chip, no-session and source-error notes (plan 07 §5) ---------- */
function liveChrome() {
  if (SOURCE.mode !== 'live') return;
  const chip = document.querySelector('.chip.demo');
  if (chip) {
    const ok = NET.state === 'connected';
    setText(chip, ok ? '接続中' : NET.state === 'connecting' && !LIVE.connectedOnce ? '接続しています…' : '再接続中…');
    chip.dataset.conn = ok ? 'ok' : 'wait';
  }
  const empty = $('live-empty');
  if (empty) empty.hidden = !SOURCE.connected || SESSIONS.length > 0;
  const nav = $('floor-nav');
  if (nav) {
    const n = LIVE.floors.length, k = LIVE.floor;
    // The floors steer the 3D office: hidden while a board, the log or a zoomed view covers it (they sat on the
    // spec board's header and its checkbox — 10-18 live check).
    const covered = wb.open || tb.open || logState.open || zoom.zoomed || !!rbState.id;
    nav.hidden = !has3D || n < 2 || covered;
    if (nav.hidden) $('tower-legend').hidden = true;
    if (!nav.hidden) {
      setText($('floor-label'), TOWER.on ? `全 ${n} 階` : `${k + 1}F / ${n}F`);
      const waits = LIVE.floors.map((f) => f.some((id) => LIVE.rank[id] === 0));
      const up = $('floor-up'), down = $('floor-down'), bld = $('floor-building');
      up.disabled = !TOWER.on && k >= n - 1; down.disabled = !TOWER.on && k <= 0;
      const above = waits.some((w, j) => w && j > k), below = waits.some((w, j) => w && j < k);
      up.toggleAttribute('data-alert', above && !TOWER.on); down.toggleAttribute('data-alert', below && !TOWER.on);
      bld.toggleAttribute('data-alert', (above || below) && !TOWER.on);
      up.setAttribute('aria-label', above ? '上の階へ（上の階に許可待ち）' : '上の階へ');
      down.setAttribute('aria-label', below ? '下の階へ（下の階に許可待ち）' : '下の階へ');
      bld.setAttribute('aria-pressed', TOWER.on ? 'true' : 'false');
      $('tower-legend').hidden = !TOWER.on;
    }
  }
  const err = $('live-error');
  if (err) { err.hidden = !LIVE.serverError; setText(err, LIVE.serverError ? `取得元の故障: ${LIVE.serverError}` : ''); }
}
if (SOURCE.mode === 'live') {
  document.body.dataset.mode = 'live';
  const hookChip = document.querySelector('.chips .chip[title="フックの受け口"]');
  if (hookChip) hookChip.textContent = location.host;
  for (const id of ['btn-play', 'btn-speed']) $(id).hidden = true;   // demo only
  liveChrome();
}

if (SOURCE.mode === 'demo') updateRobotStates(simT, START_AT, latestModel.perms);
paintScopeButtons();
renderPanel(latestModel);
if (UI.project !== 'all' && SOURCE.mode === 'demo') focusProject(UI.project, true);
const redrawAll = () => { fontRedraws.forEach((fn) => fn()); if (has3D) redrawBoards(latestModel, 0, true); };
Promise.all([
  document.fonts.load(`40px ${FONT_DISPLAY}`, 'a0!仕様書ログインテスト実行タスクボード'),
  document.fonts.load(`700 40px ${FONT_MONO}`, '{ }$✓▶○⚠#'),
  document.fonts.load(`700 16px ${FONT_BODY}`, 'ログインカート購入する未着手待ち作業中完了'),
]).then(redrawAll, redrawAll);
requestAnimationFrame(frame);
if (SOURCE.mode === 'live') { LIVE.uiReady = true; netConnect(); }
