/* ---------- the room's robot list (ticket 2026-10-23-viz-room-robot-list-show-hide) ----------
   Requester 10-23: 「botが多くなると全体が見づらいので部屋の中の時は3dの右側にbotの名前とチェックを表示してチェックしてないbotは消して
   欲しい。」 Inside one room (liveSolo), a list at the 3D's right: per session a check, its number and name and a lamp of
   its state. A robot unchecked leaves the 3D with all it carries (liveSoloSync hides its root, its desk with it, and
   its tag; the tag's bill, wait and skill badges and the spirit's bubbles follow; a game, a nap or a break it is in
   ends and none starts: rosterHides in playIdle / playStopReason). Its desk stays empty rather than the room being
   packed again: the others' desks are remembered (rememberDesk) and would all move.
   - per session: the subagents follow their main session's check, and a main's row lights when one of them waits;
   - remembered per room in this browser (pref roster:<room>, the sessions hidden; a new one is shown);
   - 全部 / 作業中だけ (any state but idle and done: waiting is work the person is owed) / なし;
   - a hidden robot waiting on the person (waitKindOf: a permission, a question, input) is not lost: its row is marked
     with what it waits for, and the list's head counts them;
   - not over a board (requester 10-23 01:23: 「ボード出してる時はbotの切り替えの表示も消していいよ」): while one of
     ROSTER_BOARDS is drawn over the 3D the list goes, and comes back with the 3D. The robot's card is not a board: it is
     opened from the list. The header's waiting chips and the notifications are not the list's: they stay. */
const ROSTER = { off: new Map(), sig: '', max: 200, placedAt: 0, placeMs: 250 };
// the boards drawn over the 3D (each shown by showOverlay): the whiteboard (a spec, and ボードで全部見る), the task board,
// the server room, the data server, the bills
const ROSTER_BOARDS = ['wb', 'tb', 'sr', 'ds', 'pr'];
const rosterUnderBoard = () => ROSTER_BOARDS.some((id) => { const el = document.getElementById(id); return !!el && el._showing === true; });
const rosterMainDef = (def) => (def.kind === 'sub' && DEF[def.mainLabel] ? DEF[def.mainLabel] : def);
const rosterKeyOf = (def) => def.sessionId || def.realId || def.id;
function rosterOff(room) {
  if (!ROSTER.off.has(room)) {
    let got = [];
    try { got = JSON.parse(readPref(`roster:${room}`, '[]')); } catch (err) { got = []; }
    ROSTER.off.set(room, new Set(Array.isArray(got) ? got.filter((k) => typeof k === 'string') : []));
  }
  return ROSTER.off.get(room);
}
function rosterSave(room) {
  const off = [...rosterOff(room)].slice(-ROSTER.max);   // the newest kept: a long-lived room does not grow it for ever
  writePref(`roster:${room}`, JSON.stringify(off));
}
/* Hidden by the list now: in a room's own view, its session unchecked there. */
function rosterHides(R) {
  const solo = liveSolo();
  return !!solo && R.def.room === solo && rosterOff(solo).has(rosterKeyOf(rosterMainDef(R.def)));
}
const ROSTER_QUIET = new Set(['idle', 'done']);
/* The rows: the room's main sessions (a subagent rides on its main's row), each with its lamp and what it waits on. */
function rosterRows(room) {
  const off = rosterOff(room), rows = new Map();
  for (const R of robots) {
    if (R.def.room !== room) continue;
    const main = rosterMainDef(R.def), key = rosterKeyOf(main);
    const row = rows.get(key) || { key, id: main.id, role: main.role, name: main.title || main.agent || main.id, state: 'idle', lamp: 'idle', wait: null, on: !off.has(key) };
    if (R.def === main) {
      const st = robotState[main.id] || { state: 'idle' };
      row.state = st.state;
      row.lamp = (STATES[st.state] || STATES.idle).lamp;
      if (row.lamp === 'waiting' && st.asking) row.lamp = 'asking';
    }
    row.wait = row.wait || (typeof waitKindOf === 'function' ? waitKindOf(R.def.id) : null);
    rows.set(key, row);
  }
  return [...rows.values()].sort((a, b) => a.id.localeCompare(b.id, undefined, { numeric: true }));
}
function rosterRowHTML(r) {
  const label = r.on ? tl('roster.hide', { name: r.name }) : tl('roster.show', { name: r.name });
  return `<li class="roster-row${r.on ? '' : ' roster-off'}${!r.on && r.wait ? ' roster-alert' : ''}" data-roster-key="${esc(r.key)}" data-robot="${esc(r.id)}" data-wait="${esc(r.wait || '')}">`
    + `<input type="checkbox" class="roster-check" data-roster-check="${esc(r.key)}"${r.on ? ' checked' : ''} aria-label="${esc(label)}">`
    + `<button type="button" class="roster-name" data-roster-open="${esc(r.id)}"${r.on ? '' : ' disabled'}>${pill(r.id, r.role)}<span class="roster-nm">${esc(r.name)}</span></button>`
    + `<span class="roster-lamp" style="--lamp:${esc(LAMP[r.lamp] || LAMP.idle)}" title="${esc(LAMP_TEXT[r.lamp] || '')}" aria-label="${esc(LAMP_TEXT[r.lamp] || '')}"></span>`
    + (r.wait ? `<span class="roster-wait">${esc(WAIT.name[r.wait] || '')}</span>` : '')
    + '</li>';
}
/* Called each frame from liveSoloSync: the list shown in a room's view, written again only when a row changed. */
function rosterSync(solo) {
  const box = document.getElementById('roster');
  if (!box) return;
  // kept while a robot is zoomed on: a card is opened from the list, and the next row is pressed from there
  const show = !!solo && has3D && !TOWER.on && !ds.open && !pr.open && !rosterUnderBoard();
  box.hidden = !show;
  if (!show) { ROSTER.sig = ''; return; }
  const now = performance.now();
  if (now - ROSTER.placedAt > ROSTER.placeMs) { ROSTER.placedAt = now; rosterPlace(box); }
  const rows = rosterRows(solo), waiting = rows.filter((r) => !r.on && r.wait).length;
  const sig = `${solo}|${rows.map((r) => [r.key, r.id, r.name, r.lamp, r.wait, r.on].join(',')).join(';')}`;
  if (sig === ROSTER.sig) return;
  ROSTER.sig = sig;
  const list = document.getElementById('roster-list'), had = document.activeElement && document.activeElement.dataset ? document.activeElement.dataset.rosterCheck : null;
  setHTML(list, rows.map(rosterRowHTML).join(''));
  if (had) { const again = [...list.querySelectorAll('[data-roster-check]')].find((x) => x.dataset.rosterCheck === had); if (again) again.focus({ preventScroll: true }); }
  setText(document.getElementById('roster-count'), tl('roster.count', { shown: rows.filter((r) => r.on).length, n: rows.length }));
  const alert = document.getElementById('roster-alert');
  alert.hidden = !waiting;
  setText(alert, waiting ? tl('roster.waiting', { n: waiting }) : '');
}
/* Under the source's error line when it shows (it holds the 3D's top right too); the narrow page's list sits at the foot. */
function rosterPlace(box) {
  const err = document.getElementById('live-error'), scene = document.getElementById('scene');
  const top = err && !err.hidden && scene ? Math.round(err.getBoundingClientRect().bottom - scene.getBoundingClientRect().top) + 6 : 12;
  box.style.setProperty('--roster-top', `${Math.max(12, top)}px`);
}
function rosterSet(room, key, on) {
  const off = rosterOff(room);
  if (on) off.delete(key); else off.add(key);
  rosterSave(room);
  ROSTER.sig = '';
}
/* 全部 / 作業中だけ / なし: every row of the room at once. */
function rosterBulk(room, how) {
  for (const r of rosterRows(room)) rosterSet(room, r.key, how === 'all' || (how === 'busy' && !ROSTER_QUIET.has(r.state)));
}
function rosterFold(folded) {
  const box = document.getElementById('roster');
  box.classList.toggle('roster-folded', folded);
  document.getElementById('roster-fold').setAttribute('aria-expanded', String(!folded));
  writePref('rosterFold', folded ? '1' : '0');
}
{
  const box = document.getElementById('roster');
  if (box) {
    // a narrow page opens it folded (the list would cover the room) until the person opens it
    rosterFold(readPref('rosterFold', window.matchMedia && window.matchMedia('(max-width: 600px)').matches ? '1' : '0') === '1');
    box.addEventListener('change', (e) => {
      const c = e.target.closest('[data-roster-check]'), solo = liveSolo();
      if (c && solo) rosterSet(solo, c.dataset.rosterCheck, c.checked);
    });
    box.addEventListener('click', (e) => {
      const solo = liveSolo();
      const b = e.target.closest('[data-roster-bulk]');
      if (b && solo) { rosterBulk(solo, b.dataset.rosterBulk); return; }
      const o = e.target.closest('[data-roster-open]');
      if (o && !o.disabled) { selectRobot(o.dataset.rosterOpen, o); return; }
      if (e.target.closest('#roster-fold')) rosterFold(!box.classList.contains('roster-folded'));
    });
  }
}
