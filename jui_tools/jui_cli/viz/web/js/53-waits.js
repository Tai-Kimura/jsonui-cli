/* ---------- a robot waiting on the person, told apart in 3D (ticket 2026-10-20-jui-viz-3d-waiting-kinds-question-permission-input) ----------
   Requester: 「今こっちの返答や許可待ちになってるbotが3dの見た目でもわかるようにしてほしい。質問、許可、入力待ちでそれぞれUI用意して」
   and 「ボットの頭に追加の吹き出し用意して、そこからボード遷移もできるといい」; answers: an input's wait may go to play (the
   bubble goes with it), an auto mode denial is a permission's bubble, the colour is ours, the bubble opens the panel's card.
   One robot shows one wait, permission > question > input (the panel's order):
     * perm  — a permission prompt (state waiting, not a question) or a stopped call's card (51-denials.js): "!", amber
     * ask   — a question (state waiting on AskUserQuestion): "?" and how many choices, violet; the lamp violet too
     * input — the session's turn ended and nobody answered (Notification idle_prompt: the server's inputWaitAt, until it
               moves again), on its main robot, until it is opened on this page since: "…"
   The pose (10-robot-core.js) follows r.waitKind: perm the raised hand, ask a hand to the chin, input leaning back. The
   bubble is a button over the tag (placeRobotTags keeps it on the tag's box), in front of everything 3D; a press opens
   the wait's card in the panel — the question card, the permission (or the stopped call's) card — or the session's
   talk. A press on the robot or its tag does what it did. Text 4.5:1 on each bubble, light and dark (fixed colours). */
const WAIT = { picked: null, mark: { perm: '!', ask: '?', input: '…' }, name: { perm: tl('status.waiting'), ask: tl('status.asking'), input: tl('status.input') } };
function waitKindOf(id) {
  const st = robotState[id];
  if (!st || !DEF[id]) return null;
  const denied = typeof DENIALS !== 'undefined' && DENIALS.some((d) => d.who === id && d.status === 'pending');
  if ((st.state === 'waiting' && !st.asking) || denied) return 'perm';
  if (st.state === 'waiting' && st.asking) return 'ask';
  if (DEF[id].kind === 'main' && SOURCE.mode === 'live') {
    const sess = SESSIONS.find((x) => x.id === SESSION_OF[id]);
    const since = sess ? Number(sess.inputWaitAt) || 0 : 0;
    if (since && !((NOTIFY.opened.get(id) || 0) >= since)) return 'input';   // seen on this page since: no bubble
  }
  return null;
}
/* The question waiting for this robot (the one its bubble opens), or null. */
const waitQuestion = (id) => (typeof QUESTIONS !== 'undefined' ? QUESTIONS.find((q) => q.who === id && q.status === 'pending') : null) || null;
function waitText(id, kind) {
  if (kind !== 'ask') return WAIT.mark[kind];
  const q = waitQuestion(id), n = q && q.questions[0] && Array.isArray(q.questions[0].options) ? q.questions[0].options.length : 0;
  return n ? `? ${n}` : '?';
}
/* Each frame (liveUpdateRobots / the demo's loop): the robot's wait and its bubble. */
function waitSync(R) {
  const kind = waitKindOf(R.def.id);
  R.robot.waitKind = kind;
  if (!kind) { if (R.waitEl) R.waitEl.hidden = true; return; }
  if (!R.waitEl) {
    const b = document.createElement('button');
    b.type = 'button'; b.className = 'wait-bubble'; b.dataset.waitRobot = R.def.id;
    tagsEl.append(b);
    R.waitEl = b;
  }
  const text = waitText(R.def.id, kind);
  if (R.waitEl.dataset.waitKind !== kind) { R.waitEl.dataset.waitKind = kind; R.waitEl.title = tl('wait.open', { name: WAIT.name[kind] }); }
  if (R.waitEl.textContent !== text) R.waitEl.textContent = text;
  R.waitEl.hidden = false;
}
function waitDrop(R) { if (R.waitEl) { R.waitEl.remove(); R.waitEl = null; } }
/* Before a wait is shown on the board or the panel (requester 10-24: 「質問系でボードに移動する時はその質問をしてる
   プロジェクト選択状態にして」 and 「複数プロジェクト待ちの時は全てのプロジェクト選択状態にして」, ticket
   2026-10-24-viz-wait-to-board-keeps-the-wrong-project): the project the waits are in — one project: it; two or more:
   すべて — so what was pressed for is on screen, not a board of another project saying it is elsewhere. Every way from a
   wait to the board or the panel goes through here: the header's chips, the block's sum and its pane's ボードで見る,
   a notification, a robot's bubble. */
const WAITS_OF = {
  perm: () => ((latestModel && latestModel.pending) || []).filter((p) => p.status === 'pending'),
  ask: () => questionsWaiting(),
  denied: () => denialsWaiting(),
};
const waitsAll = () => [...WAITS_OF.perm(), ...WAITS_OF.ask(), ...WAITS_OF.denied()];
function scopeToWaits(whos) {
  const ps = [...new Set(whos.map((w) => projectOfRobot(w)).filter(Boolean))];
  if (!ps.length) return;
  const want = ps.length === 1 ? ps[0] : 'all';
  if (UI.project !== want) setProject(want, { camera: false });
}
/* The board's waiting strip, for these waits (their project chosen first). */
function openWaitBoard(opener, waits) {
  scopeToWaits(waits.map((x) => x.who));
  tb.waitView = true;
  openTaskBoard(opener);
}
/* A press on a bubble: the panel's card of that wait, scrolled to and focused (the side panel opened first), or the
   session's talk. WAIT.picked says what was picked (the e2e reads it). */
function waitOpen(id, kind) {
  if (kind === 'input') {
    selectRobot(id, document.getElementById('scene-canvas'));
    const until = Date.now() + 4000;
    const talk = () => { if (rbState.id !== id) return; if (rbEl.hidden) { if (Date.now() < until) requestAnimationFrame(talk); return; } talkShow(true); WAIT.picked = { kind, id }; };
    requestAnimationFrame(talk);
    return;
  }
  if (kind !== 'input') scopeToWaits([id]);   // its project: the panel shows the project chosen
  if (!sideOpen) { sideOpen = true; applySide(); }
  let el = null, card = null;
  if (kind === 'ask') {
    const q = waitQuestion(id);
    card = q ? q.id : null;
    el = q ? $('questions').querySelector(`[data-qcard="${CSS.escape(q.id)}"]`) : null;
  } else {
    const d = typeof DENIALS !== 'undefined' ? DENIALS.find((x) => x.who === id && x.status === 'pending') : null;
    const p = SOURCE.mode === 'live' ? PERMS_LIVE.find((x) => x.who === id && x.status === 'pending') : null;
    // the panel's task list: the permission's box (50-panel.js permBox), with or without its buttons (no relay: none)
    if (p) { card = `perm:${p.id}`; const b = $('tasks').querySelector(`[data-perm-box="${CSS.escape(p.id)}"]`); el = b ? b.closest('li') : null; }
    else if (d) { card = `denied:${d.id}`; el = $('denied').querySelector(`[data-dcard="${CSS.escape(d.id)}"]`); }
  }
  WAIT.picked = { kind, id, card, found: !!el };
  if (!el) return;
  el.scrollIntoView({ block: 'center' });
  el.classList.add('wait-picked');
  setTimeout(() => el.classList.remove('wait-picked'), 2400);
  // its first control, or the card itself when it has none (answered in the terminal: no relay)
  const first = el.querySelector('input:not([disabled]), button:not([disabled])');
  if (first) first.focus({ preventScroll: true });
  else { el.tabIndex = -1; el.focus({ preventScroll: true }); }
}
tagsEl.addEventListener('click', (e) => {
  const b = e.target.closest('[data-wait-robot]');
  if (b) waitOpen(b.dataset.waitRobot, b.dataset.waitKind);
});
/* The header's chips say how many wait of each kind with the bubbles' marks (the 入力待ち chip is new). */
function waitChips() {
  let input = 0;
  for (const d of ROBOT_DEFS) if (waitKindOf(d.id) === 'input') input += 1;
  const chip = $('chip-input');
  chip.hidden = input === 0;
  setText(chip, tl('wait.chip.input', { n: input }));
}
$('chip-input').addEventListener('click', () => {
  const d = ROBOT_DEFS.find((x) => waitKindOf(x.id) === 'input');
  if (d) waitOpen(d.id, 'input');
});

/* ---------- the waits beside an open card (requester 10-23: 「質問や許可まちがカード開いてると見えないので、開いてるときは
   カードの左側の上の方に許可が来たのがわかるようにしてほしい」) ----------
   While a robot's card is open, the header's chips and the other robots' bubbles are behind it. Beside the card, out of
   it at its top-left corner, a small block says what the other sessions wait on — permissions, questions, stopped calls
   — how many, and whose (each robot's mark). The open card's own session is left out: its wait is in the card. A
   robot's button opens its wait's card (waitOpen, as its bubble does); the sum opens the task board's waiting strip (as
   the chips do). Where the card is the page's width (a phone's sheet, or the card widened to the whole stage) the block
   has no room beside it: the count goes in the card's head row as a badge that opens the same board. Something new moves
   once (not under reduced motion). */
const CARD_WAITS = { seen: new Set(), sig: '', open: null };   // open: the robot whose waits the pane shows
const RBW_SUM = { perm: 'rbw.sum.perm', ask: 'rbw.sum.ask', denied: 'rbw.sum.denied' };
const RBW_KIND = { perm: 'rbw.kind.perm', ask: 'rbw.kind.ask', denied: 'rbw.kind.denied' };
const rbwSum = (counts) => ['perm', 'ask', 'denied'].filter((k) => counts[k]).map((k) => tl(RBW_SUM[k], { n: counts[k] })).join(' · ');
const rbwKinds = (ks) => ks.map((x) => tl(RBW_KIND[x])).join(tl('rbw.sep'));
const CARD_WAIT_MAX = 6;   // robots listed; the rest said as ほか N
function cardWaitItems() {
  const own = rbState.id, out = [];
  for (const p of (latestModel && latestModel.pending) || []) if (p.who !== own && p.status === 'pending') out.push({ kind: 'perm', who: p.who, key: `p:${p.id}`, it: p });
  for (const d of denialsWaiting()) if (d.who !== own) out.push({ kind: 'denied', who: d.who, key: `d:${d.id}`, it: d });
  for (const q of questionsWaiting()) if (q.who !== own) out.push({ kind: 'ask', who: q.who, key: `q:${q.id}`, it: q });
  return out.filter((x) => DEF[x.who]);
}
/* Beside the card (its left edge, its top), or in its head (no room). */
const cardWaitInHead = () => window.matchMedia('(max-width: 900px)').matches || rbEl.classList.contains('rb-wide-full');
function cardWaits() {
  const box = $('rb-waits'), open = !!rbState.id && !rbEl.hidden && rbEl.classList.contains('show');   // the card on screen
  const items = open ? cardWaitItems() : [];
  const head = open && cardWaitInHead();
  const counts = { perm: 0, ask: 0, denied: 0 };
  for (const x of items) counts[x.kind] += 1;
  const fresh = items.filter((x) => !CARD_WAITS.seen.has(x.key));
  for (const x of items) CARD_WAITS.seen.add(x.key);
  // the block beside the card
  box.hidden = !items.length || head;
  if (!box.hidden) {
    const robots = [...new Set(items.map((x) => x.who))];
    const kindsOf = (id) => ['perm', 'denied', 'ask'].filter((k) => items.some((x) => x.who === id && x.kind === k));
    const sig = JSON.stringify([NAMES.rev, items.map((x) => x.key)]);
    if (sig !== CARD_WAITS.sig) {
      CARD_WAITS.sig = sig;
      const sum = rbwSum(counts);
      const newWho = new Set(fresh.map((x) => x.who));
      setHTML(box, `<p class="rbw-title">${esc(tl('rbw.title'))}</p><button type="button" class="rbw-sum" data-rbw-board data-fk="rbw-board">${esc(sum)}</button>`
        + `<ul class="rbw-list">${robots.slice(0, CARD_WAIT_MAX).map((id) => {
          const ks = kindsOf(id), k = ks[0] === 'ask' ? 'ask' : 'perm';
          return `<li><button type="button" class="rbw-robot${newWho.has(id) ? ' rbw-new' : ''}" data-rbw-robot="${esc(id)}" data-rbw-kind="${esc(k)}" data-fk="rbw-${esc(id)}" aria-controls="rb-wait-pane" aria-expanded="false" title="${esc(tl('rbw.open', { name: DEF[id].title || DEF[id].agent || id, what: rbwKinds(ks) }))}">${pill(id, DEF[id].role)}${DEF[id].title ? `<span class="rbw-name">${esc(DEF[id].title)}</span>` : ''}<span>${esc(rbwKinds(ks))}</span></button></li>`;
        }).join('')}${robots.length > CARD_WAIT_MAX ? `<li class="rbw-more">${esc(tl('rbw.more', { n: robots.length - CARD_WAIT_MAX }))}</li>` : ''}</ul>`);
      if (fresh.length) { box.classList.remove('rbw-arrive'); void box.offsetWidth; box.classList.add('rbw-arrive'); }
    }
    const parent = rbEl.offsetParent || rbEl.parentElement;
    box.style.top = `${rbEl.offsetTop}px`;
    box.style.right = `${parent.clientWidth - rbEl.offsetLeft + 10}px`;
  } else CARD_WAITS.sig = '';
  // the badge in the card's head row
  const slot = rbEl.querySelector('[data-rbw-slot]');
  if (slot) {
    const n = items.length, want = head && n ? tl('rbw.badge', { n }) : '';
    if (slot.dataset.n !== String(head ? n : 0)) {
      slot.dataset.n = String(head ? n : 0);
      setHTML(slot, want ? `<button type="button" class="rbw-badge${fresh.length ? ' rbw-new' : ''}" data-rbw-pane data-fk="rbw-badge" aria-controls="rb-wait-pane" aria-expanded="false" title="${esc(rbwSum(counts))}">${esc(want)}</button>` : '');
    }
  }
  cardWaitPanePaint();
}
/* ---------- answering a wait where it is listed (requester 10-24: 「ここでも該当の質問クリックで質問が開いてそこで回答
   できるようにして」, ticket 2026-10-24-viz-card-waits-answer-in-place) ----------
   A robot's row opens its waits in a pane under the block — the panel's own cards: a question's choices, free answer and
   send (questionHTML), a permission's tool, what it asks and allow / deny (permBox), a stopped call's (denialHTML) —
   answered through the same calls (SOURCE.answerQuestion, decide, SOURCE.denial). The open card stays and the camera
   does not move. Everything is drawn from the one state, so a wait answered anywhere (here, the panel, the board) goes
   from every place at once; the pane follows, and closes when its robot waits on nothing more. The row again, its ×
   or Esc closes it. Where the card is the page's width the head's badge opens it, listing the robots first. */
const paneEl = $('rb-wait-pane');
const paneItemSig = (x) => (x.kind === 'ask' ? [x.key, x.it.status, x.it.hookWaiting, x.it.tooLongToShow, x.it.released, x.it.waitEnded]
  : x.kind === 'perm' ? [x.key, x.it.status, x.it.tooLongToShow, x.it.can]
    : [x.key, x.it.status, x.it.reason, x.it.input, x.it.reply, denialTarget(x.it).why]);
const paneItemHTML = (x) => (x.kind === 'ask' ? questionHTML(x.it, 'w')
  : x.kind === 'perm' ? `<article class="qcard pcard rbwp-perm" data-rbwp-perm="${esc(x.it.id)}"><header class="qwho">${pill(x.who, DEF[x.who].role)}<span>${esc(DEF[x.who].agent)}</span><span class="dtag">${esc(tl('rbw.kind.perm'))}</span></header>${permBox(x.it, 'w')}</article>`
    : denialHTML(x.it, 'w'));
function paneRobotsHTML(robots, who, items) {
  return `<ul class="rbw-list rbwp-robots">${robots.map((id) => `<li><button type="button" class="rbw-robot" data-rbwp-robot="${esc(id)}" data-fk="rbwp-${esc(id)}" aria-controls="rb-wait-pane" aria-expanded="${id === who}">${pill(id, DEF[id].role)}${DEF[id].title ? `<span class="rbw-name">${esc(DEF[id].title)}</span>` : ''}<span>${esc(rbwKinds(['perm', 'denied', 'ask'].filter((k) => items.some((x) => x.who === id && x.kind === k))))}</span></button></li>`).join('')}</ul>`;
}
function paneHTML(name, head, robots, who, items, mine) {
  return `<div class="rbwp-head"><p class="rbwp-title">${esc(tl('rbw.pane.title', { name }))}</p>${head ? `<button type="button" class="link-btn" data-rbw-board data-fk="rbwp-board">${esc(tl('rbw.pane.board'))}</button>` : ''}<button type="button" class="rbwp-x" data-rbwp-close data-fk="rbwp-x" aria-label="${esc(tl('rbw.pane.close'))}" title="${esc(tl('rbw.pane.close'))}">×</button></div>`
    + `${head ? paneRobotsHTML(robots, who, items) : ''}<div class="rbwp-items">${mine.map(paneItemHTML).join('')}</div>`;
}
function cardWaitPanePaint() {
  const head = !!rbState.id && cardWaitInHead();
  const items = (head || !$('rb-waits').hidden) && rbState.id ? cardWaitItems() : [];
  const robots = [...new Set(items.map((x) => x.who))];
  // its robot answered everything: closed (in the head's list, the next robot's waits instead)
  if (CARD_WAITS.open !== null && !robots.includes(CARD_WAITS.open)) CARD_WAITS.open = head && robots.length ? robots[0] : null;
  const open = CARD_WAITS.open !== null && items.length > 0;
  for (const b of document.querySelectorAll('[data-rbw-robot], [data-rbw-pane]')) {
    const on = open && (b.dataset.rbwPane !== undefined || b.dataset.rbwRobot === CARD_WAITS.open);
    if (b.getAttribute('aria-expanded') !== String(on)) b.setAttribute('aria-expanded', String(on));
  }
  if (!open) { if (!paneEl.hidden) { paneEl.hidden = true; paneEl._sig = null; } CARD_WAITS.open = null; return; }
  const who = CARD_WAITS.open, mine = items.filter((x) => x.who === who);
  const name = DEF[who].title || DEF[who].agent || who;
  paneEl.setAttribute('aria-label', tl('rbw.pane.aria', { name }));
  // where the block has no room (the card as wide as the page): the robots first, as the block lists them
  keyed(paneEl, JSON.stringify([NAMES.rev, DEN.asking, head, head ? robots : 0, who, mine.map(paneItemSig)]), () => paneHTML(name, head, head ? robots : [], who, items, mine));
  for (const card of paneEl.querySelectorAll('[data-qcard]')) questionSendState(card);
  paneEl.hidden = false;
  // under the block, its right edge on the block's (left of the card); in the head's case under the card's head row
  const parent = rbEl.offsetParent || rbEl.parentElement;
  if (head) {
    // the card is fixed here (a phone's sheet, or widened over the stage): the pane too, right under the badge, over
    // the card's body (there is no room beside it), the badge and the head row left in sight
    const at = (rbEl.querySelector('[data-rbw-pane]') || rbEl.querySelector('.rb-head') || rbEl).getBoundingClientRect(), card = rbEl.getBoundingClientRect();
    paneEl.classList.add('rbwp-in-head');
    paneEl.style.top = `${Math.round(at.bottom + 6)}px`;
    paneEl.style.right = `${Math.round(innerWidth - card.right + 6)}px`;
    paneEl.style.width = `${Math.max(200, Math.round(card.width - 12))}px`;
    paneEl.style.maxHeight = `${Math.max(160, Math.round(innerHeight - at.bottom - 18))}px`;
    return;
  } else {
    const box = $('rb-waits');
    paneEl.classList.remove('rbwp-in-head');
    const right = parent.clientWidth - rbEl.offsetLeft + 10;
    paneEl.style.top = `${box.offsetTop + box.offsetHeight + 8}px`;
    paneEl.style.right = `${right}px`;
    paneEl.style.width = `${Math.max(220, Math.min(360, parent.clientWidth - right - 12))}px`;
  }
  paneEl.style.maxHeight = `${Math.max(160, parent.clientHeight - paneEl.offsetTop - 12)}px`;
}
/* Open (or switch to, or close) the pane for a robot; the focus to its first control, or back to what opened it. */
function cardWaitPaneToggle(who, from) {
  CARD_WAITS.open = CARD_WAITS.open === who ? null : who;
  CARD_WAITS.from = from || null;
  cardWaitPanePaint();
  if (CARD_WAITS.open) {
    const first = paneEl.querySelector('.rbwp-items input:not([disabled]), .rbwp-items button:not([disabled])');
    (first || paneEl.querySelector('[data-rbwp-close]')).focus({ preventScroll: true });
  } else if (from && from.isConnected) from.focus({ preventScroll: true });
}
function cardWaitPaneClose() {
  if (CARD_WAITS.open === null) return false;
  const from = CARD_WAITS.from;
  CARD_WAITS.open = null;
  cardWaitPanePaint();
  if (from && from.isConnected) from.focus({ preventScroll: true });
  return true;
}
function cardWaitClick(e) {
  const r = e.target.closest('[data-rbw-robot]');
  if (r) { cardWaitPaneToggle(r.dataset.rbwRobot, r); return; }
  const p = e.target.closest('[data-rbw-pane]');
  if (p) {
    const first = cardWaitItems()[0];
    if (CARD_WAITS.open !== null) cardWaitPaneClose(); else if (first) cardWaitPaneToggle(first.who, p);
    return;
  }
  const b = e.target.closest('[data-rbw-board]');
  if (b) openWaitBoard(b, cardWaitItems());
}
$('rb-waits').addEventListener('click', cardWaitClick);
rbEl.addEventListener('click', (e) => { if (e.target.closest('[data-rbw-board], [data-rbw-pane]')) cardWaitClick(e); });
paneEl.addEventListener('click', (e) => {
  if (e.target.closest('[data-rbwp-close]')) { cardWaitPaneClose(); return; }
  const r = e.target.closest('[data-rbwp-robot]');
  if (r) { CARD_WAITS.open = r.dataset.rbwpRobot; cardWaitPanePaint(); return; }
  if (e.target.closest('[data-rbw-board]')) { cardWaitPaneClose(); cardWaitClick(e); }
});
// the panel's question and stopped-call handlers, on the pane's cards too (the same state, the same sending)
paneEl.addEventListener('input', onQuestionInput);
paneEl.addEventListener('click', onQuestionClick);
paneEl.addEventListener('click', onDenialClick);
// Esc closes the pane first (the card stays), from inside it or from the row that opened it
window.addEventListener('keydown', (e) => {
  if (e.key !== 'Escape' || paneEl.hidden) return;
  const a = document.activeElement;
  if (!(paneEl.contains(a) || $('rb-waits').contains(a) || (a && a.closest && a.closest('[data-rbw-slot]')) || a === document.body)) return;
  e.preventDefault(); e.stopPropagation();
  cardWaitPaneClose();
}, true);
window.addEventListener('resize', () => { if (rbState.id) cardWaits(); });
