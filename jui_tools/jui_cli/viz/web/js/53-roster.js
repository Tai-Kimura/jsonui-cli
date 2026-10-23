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
     opened from the list. The header's waiting chips and the notifications are not the list's: they stay;
   - put in order (requester 10-23: 「ロボットの一覧に並べ替え機能追加できる？左右キーで移動するのもその順番に」): the person's
     own order (dragged, or Alt+↑↓ on a row; remembered per room as the checks are, pref roster-order:<room>, a new
     session at the end), by name, by state (waiting first) or most recently active (pref roster-sort:<room>). A row
     moved while another order shows starts the person's own from the one shown. The card's ‹ › and ← → go in the
     list's order and skip the robots it hides (rosterCycle, robotCycle in a room's view). */
const ROSTER = { off: new Map(), order: new Map(), sig: '', max: 200, placedAt: 0, placeMs: 250, shownFor: null, drag: null };
const ROSTER_SORTS = ['own', 'name', 'state', 'recent'];
// the boards drawn over the 3D (each shown by showOverlay): the whiteboard (a spec, and ボードで全部見る), the task board,
// the server room, the data server, the bills
const ROSTER_BOARDS = ['wb', 'tb', 'sr', 'ds', 'pr'];
// and every dialog that takes the whole page (aria-modal: the full-screen log, the call, the server room) — the gate,
// 10-23: the list stayed up over the log (the floor buttons go under it)
const rosterUnderBoard = () => ROSTER_BOARDS.some((id) => { const el = document.getElementById(id); return !!el && el._showing === true; })
  || !!document.querySelector('[role="dialog"][aria-modal="true"]:not([hidden])');
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
const rosterSort = (room) => { const s = readPref(`roster-sort:${room}`, 'own'); return ROSTER_SORTS.includes(s) ? s : 'own'; };
/* The person's own order of the room's sessions (keys), first to last; the sessions not in it come after, by number. */
function rosterOrder(room) {
  if (!ROSTER.order.has(room)) {
    let got = [];
    try { got = JSON.parse(readPref(`roster-order:${room}`, '[]')); } catch (err) { got = []; }
    ROSTER.order.set(room, Array.isArray(got) ? got.filter((k) => typeof k === 'string') : []);
  }
  return ROSTER.order.get(room);
}
const rosterById = (a, b) => a.id.localeCompare(b.id, undefined, { numeric: true });
// waiting on the person (its own wait or a subagent's), then at work, then free, then done
const rosterRank = (r) => (r.wait || r.lamp === 'waiting' || r.lamp === 'asking' ? 0 : r.lamp === 'idle' ? 2 : r.lamp === 'done' ? 3 : 1);
function rosterArrange(rows, how, own) {
  const at = new Map(own.map((k, i) => [k, i])), pos = (r) => (at.has(r.key) ? at.get(r.key) : Infinity);
  const by = {
    own: (a, b) => pos(a) - pos(b),
    name: (a, b) => String(a.name).localeCompare(String(b.name), 'ja', { numeric: true }),
    state: (a, b) => rosterRank(a) - rosterRank(b),
    recent: (a, b) => (b.since || 0) - (a.since || 0),
  }[how] || (() => 0);
  return [...rows].sort((a, b) => by(a, b) || rosterById(a, b));
}
/* A row moved to place `to` among the others (a drop, Alt+↑↓): the order shown becomes the person's own. The sessions
   not in the room now keep their places after it, to come back to. */
function rosterMove(room, key, to) {
  const keys = rosterRows(room).map((r) => r.key).filter((k) => k !== key);
  keys.splice(Math.max(0, Math.min(to, keys.length)), 0, key);
  const order = [...keys, ...rosterOrder(room).filter((k) => !keys.includes(k))].slice(0, ROSTER.max);
  ROSTER.order.set(room, order);
  writePref(`roster-order:${room}`, JSON.stringify(order));
  writePref(`roster-sort:${room}`, 'own');
  ROSTER.sig = '';
}
/* The robots ‹ › and ← → go through in a room's view: the list's rows in its order, the ones it hides skipped, a
   main session's subagents after it. */
function rosterCycle(room) {
  const subs = new Map();
  for (const R of robots) {
    if (R.def.room !== room) continue;
    const main = rosterMainDef(R.def);
    if (main !== R.def) { if (!subs.has(main.id)) subs.set(main.id, []); subs.get(main.id).push(R.def); }
  }
  return rosterRows(room).filter((r) => r.on).flatMap((r) => [r.id, ...(subs.get(r.id) || []).sort(rosterById).map((d) => d.id)]);
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
    const row = rows.get(key) || { key, id: main.id, role: main.role, name: main.title || main.agent || main.id, state: 'idle', lamp: 'idle', wait: null, on: !off.has(key), since: 0 };
    row.since = Math.max(row.since, (robotState[R.def.id] && robotState[R.def.id].since) || 0);
    if (R.def === main) {
      const st = robotState[main.id] || { state: 'idle' };
      row.state = st.state;
      row.lamp = (STATES[st.state] || STATES.idle).lamp;
      if (row.lamp === 'waiting' && st.asking) row.lamp = 'asking';
    }
    row.wait = row.wait || (typeof waitKindOf === 'function' ? waitKindOf(R.def.id) : null);
    rows.set(key, row);
  }
  return rosterArrange([...rows.values()], rosterSort(room), rosterOrder(room));
}
/* The row of the robot selected now (its card open, the ring under it in the 3D; requester 10-23: 「今選択されてるロボットが
   チェックの方でもハイライトされるようにしてほしい」): a subagent's is its main session's row, as the list has it. */
function rosterCurrentKey() {
  const def = rbState.id && DEF[rbState.id];
  return def ? rosterKeyOf(rosterMainDef(def)) : null;
}
function rosterRowHTML(r, current) {
  const label = r.on ? tl('roster.hide', { name: r.name }) : tl('roster.show', { name: r.name });
  return `<li class="roster-row${r.on ? '' : ' roster-off'}${!r.on && r.wait ? ' roster-alert' : ''}" draggable="true" data-roster-key="${esc(r.key)}" data-robot="${esc(r.id)}" data-wait="${esc(r.wait || '')}"${r.key === current ? ' aria-current="true"' : ''}>`
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
  if (ROSTER.drag) return;   // a row being dragged: written again when it is dropped
  const sort = document.getElementById('roster-sort'), how = rosterSort(solo);
  if (sort && sort.value !== how) sort.value = how;
  const rows = rosterRows(solo), waiting = rows.filter((r) => !r.on && r.wait).length, current = rosterCurrentKey();
  const sig = `${solo}|${current}|${rows.map((r) => [r.key, r.id, r.name, r.lamp, r.wait, r.on].join(',')).join(';')}`;
  if (sig === ROSTER.sig) { rosterShowCurrent(current); return; }
  ROSTER.sig = sig;
  // the focus kept on its row's check or name: a row moved with Alt+↑↓ is moved again with the next press
  const list = document.getElementById('roster-list'), fo = document.activeElement, fRow = fo && list.contains(fo) ? fo.closest('.roster-row') : null;
  const had = fRow && { key: fRow.dataset.rosterKey, part: fo.classList.contains('roster-check') ? '.roster-check' : '.roster-name' };
  setHTML(list, rows.map((r) => rosterRowHTML(r, current)).join(''));
  if (had) {
    const again = [...list.querySelectorAll('.roster-row')].find((x) => x.dataset.rosterKey === had.key);
    const el = again && again.querySelector(had.part);
    if (el) { el.focus({ preventScroll: true }); el.scrollIntoView({ block: 'nearest' }); }
  }
  setText(document.getElementById('roster-count'), tl('roster.count', { shown: rows.filter((r) => r.on).length, n: rows.length }));
  const alert = document.getElementById('roster-alert');
  alert.hidden = !waiting;
  setText(alert, waiting ? tl('roster.waiting', { n: waiting }) : '');
  rosterShowCurrent(current);
}
/* The selected robot's row in view, once per robot selected (as the spec board's list, wbSideShowOpen): only the list
   scrolls, and a row scrolled away by hand afterwards stays where the person put it. A folded list waits. */
function rosterShowCurrent(current) {
  if (ROSTER.shownFor === current) return;
  const list = document.getElementById('roster-list');
  const row = current && list ? list.querySelector('.roster-row[aria-current="true"]') : null;
  if (current && (!row || !row.offsetParent)) return;
  if (row) {
    const box = list.getBoundingClientRect(), r = row.getBoundingClientRect();
    if (r.top < box.top) list.scrollTop -= box.top - r.top + 4;
    else if (r.bottom > box.bottom) list.scrollTop += r.bottom - box.bottom + 4;
  }
  ROSTER.shownFor = current;
}
/* The fixed parts over the 3D that share its column (the gate, 10-23: the list's fold button lay on the floor buttons,
   a room's view on a building of three floors): the room's name box, the floor buttons, the source's error line, the
   building's legend and weather, the empty room's note. Any of them shown in the list's column and in the 3D's upper
   half keeps the list below it; the list is as tall as what is left. On a narrow page the list sits at the foot, so
   only its height gives way. */
const ROSTER_AROUND = ['room-solo', 'floor-nav', 'live-error', 'tower-legend', 'tower-weather', 'live-empty'];
function rosterPlace(box) {
  const scene = document.getElementById('scene');
  if (!scene) return;
  const S = scene.getBoundingClientRect(), r = box.getBoundingClientRect();
  let clear = S.top + 12;   // the page y the list's top stays under
  for (const id of ROSTER_AROUND) {
    const el = document.getElementById(id);
    if (!el || el.hidden) continue;
    const o = el.getBoundingClientRect();
    if (o.width && o.height && o.left < r.right && r.left < o.right && o.top < S.top + S.height / 2) clear = Math.max(clear, o.bottom + 6);
  }
  if (!rosterNarrow()) box.style.setProperty('--roster-top', `${Math.round(clear - S.top)}px`);
  box.style.setProperty('--roster-max', `${Math.max(48, Math.round(S.bottom - 12 - clear))}px`);
}
const rosterNarrow = () => !!(window.matchMedia && window.matchMedia('(max-width: 900px)').matches);   // app.css: the list at the foot
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
    box.addEventListener('change', (e) => {
      const solo = liveSolo();
      if (e.target.id !== 'roster-sort' || !solo || !ROSTER_SORTS.includes(e.target.value)) return;
      writePref(`roster-sort:${solo}`, e.target.value);
      ROSTER.sig = '';
    });
    box.addEventListener('keydown', (e) => {
      if ((e.key !== 'ArrowUp' && e.key !== 'ArrowDown') || !e.altKey || e.ctrlKey || e.metaKey || e.shiftKey) return;
      const row = e.target.closest('.roster-row'), solo = liveSolo();
      if (!row || !solo) return;
      e.preventDefault();
      const i = rosterRows(solo).findIndex((r) => r.key === row.dataset.rosterKey);
      if (i >= 0) rosterMove(solo, row.dataset.rosterKey, i + (e.key === 'ArrowDown' ? 1 : -1));
    });
    // dragged: a line above or below the row it would go to
    const dropAt = (e) => {
      const row = e.target.closest && e.target.closest('.roster-row');
      if (!row) return null;
      const r = row.getBoundingClientRect();
      return { row, after: e.clientY > r.top + r.height / 2 };
    };
    const unmark = () => box.querySelectorAll('.roster-drop-before, .roster-drop-after, .roster-dragging').forEach((x) => x.classList.remove('roster-drop-before', 'roster-drop-after', 'roster-dragging'));
    box.addEventListener('dragstart', (e) => {
      const row = e.target.closest && e.target.closest('.roster-row');
      if (!row) return;
      ROSTER.drag = row.dataset.rosterKey;
      row.classList.add('roster-dragging');
      e.dataTransfer.effectAllowed = 'move';
      e.dataTransfer.setData('text/plain', ROSTER.drag);
    });
    box.addEventListener('dragover', (e) => {
      const at = ROSTER.drag && dropAt(e);
      if (!at) return;
      e.preventDefault();
      e.dataTransfer.dropEffect = 'move';
      box.querySelectorAll('.roster-drop-before, .roster-drop-after').forEach((x) => x.classList.remove('roster-drop-before', 'roster-drop-after'));
      if (at.row.dataset.rosterKey !== ROSTER.drag) at.row.classList.add(at.after ? 'roster-drop-after' : 'roster-drop-before');
    });
    box.addEventListener('drop', (e) => {
      const at = ROSTER.drag && dropAt(e), solo = liveSolo(), key = ROSTER.drag;
      if (!at || !solo) return;
      e.preventDefault();
      const others = rosterRows(solo).map((r) => r.key).filter((k) => k !== key), j = others.indexOf(at.row.dataset.rosterKey);
      ROSTER.drag = null;
      unmark();
      if (j >= 0) rosterMove(solo, key, j + (at.after ? 1 : 0));
    });
    box.addEventListener('dragend', () => { ROSTER.drag = null; unmark(); ROSTER.sig = ''; });
  }
}
