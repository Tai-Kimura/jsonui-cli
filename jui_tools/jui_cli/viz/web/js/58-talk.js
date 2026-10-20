/* ---------- トーク: a robot's SendMessage conversations, as a chat (2.3.6, requester 10-20) ----------
   「チャットアイコンをロボットのメニューに置いて、それ選んだらラインのトークっぽい画面でトークの一覧が表示される。トーク選ぶと詳細で
   トークが見れる。新しいメッセージ受信したら一覧では通知が出て詳細ではメッセージが表示される。」 and (00:54) 「トークの詳細でヘッダーに
   相手のbot名表示しってタップでそのbotに切り替えられるようにして。名前は一行で入らないなら省略で」.
   The rulings (TALK_CONTRACT.md): read only — no box, no button and no request that sends; no browser notification (the
   badge and the order of the list are the news); a talk whose peer ended goes when the server removes it.

   The wire is talk_contract.json (version 2): the page asks talk.open / talk.get / talk.seen / talk.close and hears
   talk.list / talk.messages / talk.update / talk.badges. Every request is built by talkFrame, which checks it against the
   contract's rules first and refuses (null, nothing sent) what would not conform; tests/test_viz_talk_ui_frames.py runs
   the block below under node and validates what it builds with talk_contract.validate, and pins these rules to the JSON.
   Text from a transcript goes in through textContent (histMarkdown: escaped Markdown), never innerHTML. */
/* talk-frames:begin */
const TALK_RULES = {
  agentId: '^[A-Za-z0-9_.:@-]+$', agentIdMax: 128,
  convId: '^t-[0-9a-f]{16}$',
  messageId: '^(m|u|r)-[A-Za-z0-9_.:@-]+$', messageIdMin: 3, messageIdMax: 200,
  pageMax: 100,
};
const TALK_FIELDS = {   // the keys each request may carry (required first), as the contract's requests
  'talk.open': { need: ['type', 'reqId', 'agentId'], may: [] },
  'talk.close': { need: ['type'], may: ['reqId'] },
  'talk.get': { need: ['type', 'reqId', 'agentId', 'convId'], may: ['before', 'limit'] },
  'talk.seen': { need: ['type', 'reqId', 'agentId', 'convId', 'upTo'], may: [] },
};
const talkIsInt = (v) => typeof v === 'number' && Number.isInteger(v);
const talkOkAgent = (v) => typeof v === 'string' && v.length >= 1 && v.length <= TALK_RULES.agentIdMax && new RegExp(TALK_RULES.agentId).test(v);
const talkOkConv = (v) => typeof v === 'string' && new RegExp(TALK_RULES.convId).test(v);
const talkOkMessage = (v) => typeof v === 'string' && v.length >= TALK_RULES.messageIdMin && v.length <= TALK_RULES.messageIdMax && new RegExp(TALK_RULES.messageId).test(v);
/* Every way a request breaks the contract (empty: it conforms). */
function talkCheck(f) {
  const spec = f && typeof f === 'object' ? TALK_FIELDS[f.type] : null;
  if (!spec) return ['not a talk request'];
  const out = [];
  for (const k of spec.need) if (!(k in f)) out.push(`missing ${k}`);
  for (const k of Object.keys(f)) if (!spec.need.includes(k) && !spec.may.includes(k)) out.push(`unexpected ${k}`);
  if ('reqId' in f && !(talkIsInt(f.reqId) || typeof f.reqId === 'string')) out.push('reqId');
  if ('agentId' in f && !talkOkAgent(f.agentId)) out.push('agentId');
  if ('convId' in f && !talkOkConv(f.convId)) out.push('convId');
  if ('before' in f && !talkOkMessage(f.before)) out.push('before');
  if ('limit' in f && !(talkIsInt(f.limit) && f.limit >= 1 && f.limit <= TALK_RULES.pageMax)) out.push('limit');
  if ('upTo' in f && !(talkIsInt(f.upTo) && f.upTo >= 0)) out.push('upTo');
  return out;
}
/* A request of `type` from `fields` (undefined fields left out), or null when it would not conform. */
function talkFrame(type, fields) {
  const f = { type };
  for (const [k, v] of Object.entries(fields || {})) if (v !== undefined) f[k] = v;
  return talkCheck(f).length ? null : f;
}
/* talk-frames:end */

const TALK_END_PX = 24;        // this close to the bottom counts as at the end (as the history's)
const TALK = {
  on: false,                   // the talk pane shows on the card (instead of its tabs)
  owner: null, agent: null,    // the card's robot (label) and its agentId
  opened: null,                // the agentId this socket has talk.open'd
  list: null, more: false, listError: '', listAt: 0,
  conv: null,                  // the talk shown in detail (convId), or null: the list
  want: null,                  // a talk to show once the card has switched to the peer (the header's press)
  msgs: new Map(),             // convId -> { items, more, busy, error, loaded }
  seenSent: new Map(),         // `${agent}|${convId}` -> upTo sent
  seenWant: new Map(),         // `${agent}|${convId}` -> the newest at seen on screen, not sent yet
  badges: {},                  // agentId -> unread (talk.badges; robots at 0 are not in it)
  sent: [], refused: [],       // the requests sent and refused, for the tests (the last 200)
  page: 30,                    // messages a talk.get asks for (≤ pageMax)
  seq: 0, node: null, nodes: new Map(), atEnd: true, top: 0, newer: false, note: '',
};
const talkNow = () => Date.now();
function talkTime(at, short) {
  if (!Number.isFinite(at)) return '';
  const d = new Date(at), n = new Date(talkNow());
  const hm = fmtTime(d, { hour: '2-digit', minute: '2-digit' });
  if (d.toDateString() === n.toDateString()) return hm;
  return short ? `${d.getMonth() + 1}/${d.getDate()}` : `${d.getMonth() + 1}/${d.getDate()} ${hm}`;
}

/* ---------- requests ---------- */
function talkSend(type, fields) {
  const reqId = type === 'talk.close' ? undefined : `tk${++TALK.seq}`;
  const frame = talkFrame(type, { reqId, ...fields });
  if (!frame) { TALK.refused.push({ type, fields }); TALK.refused.splice(0, TALK.refused.length - 200); return Promise.resolve({ ok: false, error: 'refused' }); }
  TALK.sent.push(frame); TALK.sent.splice(0, TALK.sent.length - 200);
  return SOURCE.talkSend(frame);
}
/* The socket follows the card: the robot on the card is the one open (its list and its updates), none when it closes. */
function talkFollow(agent) {
  if (agent === TALK.opened) return;
  if (!agent) { if (TALK.opened) talkSend('talk.close', {}); TALK.opened = null; return; }
  TALK.opened = agent;
  TALK.list = null; TALK.listError = ''; TALK.more = false; TALK.msgs.clear(); TALK.nodes.clear();
  talkSend('talk.open', { agentId: agent }).then((got) => {
    if (TALK.opened !== agent || got.ok) return;
    TALK.listError = got.error === 'offline' ? tl('talk.offline') : tl('talk.list.error', { error: got.error || tl('talk.unknown') });
    talkRender();
  });
}
/* The socket closed or came back (live): the server forgot what was open, so it is opened again. */
function talkConn(state) {
  if (state === 'connected') { const a = TALK.opened; TALK.opened = null; if (a) { talkFollow(a); if (TALK.conv) talkLoad(TALK.conv, false); } }
  else if (TALK.opened && !TALK.list) { TALK.listError = tl('talk.offline'); talkRender(); }
}
async function talkLoad(convId, older) {
  const agent = TALK.agent;
  if (!agent || !convId) return;
  const box = TALK.msgs.get(convId) || { items: [], more: false, busy: false, error: '', loaded: false };
  TALK.msgs.set(convId, box);
  if (box.busy || (older && (!box.more || !box.items.length))) return;
  box.busy = true; box.error = '';
  talkRender();
  const got = await talkSend('talk.get', { agentId: agent, convId, before: older ? box.items[0].id : undefined, limit: TALK.page });
  box.busy = false;
  if (TALK.agent !== agent || TALK.msgs.get(convId) !== box) return;
  if (!got.ok || !got.data || !Array.isArray(got.data.items)) {
    box.error = got.error === 'offline' ? tl('talk.offline') : tl('talk.messages.error', { error: got.error || tl('talk.unknown') });
  } else {
    const pane = talkPane(), keep = older && pane ? pane.scrollHeight - pane.scrollTop : null;
    talkMerge(box, got.data.items);
    if (older || !box.loaded) box.more = !!got.data.more;
    box.loaded = true;
    talkRender();
    if (keep !== null && pane) { pane.scrollTop = pane.scrollHeight - keep; TALK.top = pane.scrollTop; }
    return;
  }
  talkRender();
}
const talkOkMsg = (m) => m && typeof m === 'object' && talkOkMessage(m.id) && Number.isFinite(m.at) && (m.dir === 'in' || m.dir === 'out') && typeof m.text === 'string';
function talkMerge(box, items) {
  const byId = new Map(box.items.map((m) => [m.id, m]));
  for (const m of items) if (talkOkMsg(m)) byId.set(m.id, m);
  box.items = [...byId.values()].sort((a, b) => a.at - b.at || (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
}

/* ---------- what the server sends ---------- */
const talkOkConvRow = (c) => c && typeof c === 'object' && talkOkConv(c.id) && c.peer && typeof c.peer === 'object' && Number.isFinite(c.lastAt);
function talkSortList() { if (TALK.list) TALK.list.sort((a, b) => b.lastAt - a.lastAt || (a.id < b.id ? -1 : 1)); }
function talkReceive(f) {
  if (!f || typeof f !== 'object') return;
  if (f.type === 'talk.badges') {
    const counts = {};
    for (const [k, v] of Object.entries(f.counts && typeof f.counts === 'object' ? f.counts : {})) if (talkOkAgent(k) && talkIsInt(v) && v > 0) counts[k] = v;
    TALK.badges = counts;
    talkPaintButton();
    return;
  }
  if (f.agentId !== TALK.opened) return;   // another robot's (the socket moved on)
  if (f.type === 'talk.list') {
    TALK.list = (Array.isArray(f.items) ? f.items : []).filter(talkOkConvRow);
    TALK.more = !!f.more; TALK.listError = '';
    talkSortList();
    talkRender();
    return;
  }
  if (f.type !== 'talk.update' || !Array.isArray(f.ops)) return;
  let newHere = false;
  for (const op of f.ops) {
    if (!op || typeof op !== 'object') continue;
    if (op.op === 'conv' && talkOkConvRow(op.conv)) {
      if (!TALK.list) continue;
      const k = TALK.list.findIndex((c) => c.id === op.conv.id);
      if (k >= 0) TALK.list[k] = op.conv; else TALK.list.push(op.conv);
    } else if (op.op === 'message' && talkOkConv(op.convId) && talkOkMsg(op.message)) {
      const box = TALK.msgs.get(op.convId);
      if (box && box.loaded) {
        const had = box.items.some((m) => m.id === op.message.id);
        talkMerge(box, [op.message]);
        if (!had && op.convId === TALK.conv) newHere = true;
      }
    } else if (op.op === 'remove' && talkOkConv(op.convId)) {
      if (TALK.list) TALK.list = TALK.list.filter((c) => c.id !== op.convId);
      TALK.msgs.delete(op.convId);
      if (TALK.conv === op.convId) {
        TALK.conv = null;
        TALK.note = op.reason === 'owner-ended' ? tl('talk.gone.owner') : tl('talk.gone.peer');
      }
    }
  }
  talkSortList();
  if (newHere && !TALK.atEnd) TALK.newer = true;
  talkRender();
}

/* ---------- the pane ---------- */
function talkPane() { return TALK.node ? TALK.node.querySelector('[data-tk-body]') : null; }
function talkBuildNode() {
  const root = hNode('section', 'tk');
  root.dataset.talk = '';
  root.setAttribute('aria-label', tl('talk.title'));
  const head = hNode('div', 'talk-head'); head.dataset.tkHead = '';
  const body = hNode('div', 'talk-body'); body.dataset.tkBody = ''; body.tabIndex = 0;
  const newer = hNode('button', 'h-newer talk-newer', tl('talk.newer')); newer.type = 'button'; newer.dataset.tkNewer = ''; newer.hidden = true;
  const foot = hNode('p', 'talk-foot', tl('talk.foot'));
  root.append(head, body, newer, foot);
  body.addEventListener('scroll', () => talkRemember(body), { passive: true });
  root.addEventListener('click', talkClick);
  return root;
}
function talkRemember(pane) {
  if (!TALK.conv) return;
  TALK.top = pane.scrollTop;
  TALK.atEnd = pane.scrollHeight - pane.scrollTop - pane.clientHeight < TALK_END_PX;
  if (TALK.atEnd && TALK.newer) { TALK.newer = false; talkPaintNewer(); }
  const box = TALK.msgs.get(TALK.conv);
  if (box && box.more && !box.busy && pane.scrollTop < 40) talkLoad(TALK.conv, true);   // read up: the page before
}
function talkToEnd() {
  const pane = talkPane();
  if (!pane) return;
  TALK.atEnd = true; TALK.newer = false;
  pane.scrollTop = pane.scrollHeight;
  TALK.top = pane.scrollTop;
  talkPaintNewer();
}
function talkPaintNewer() { const b = TALK.node && TALK.node.querySelector('[data-tk-newer]'); if (b) b.hidden = !(TALK.newer && TALK.conv); }

function talkPeerMark(peer) {
  const label = SOURCE.talkLabel(peer.agentId);
  const span = hNode('span', 'talk-mark');
  span.setAttribute('aria-hidden', 'true');
  if (label && DEF[label]) {   // the robot's mark, as pill() draws it (built as nodes here)
    const role = DEF[label].role, mark = hNode('span', 'pill', label);
    mark.style.setProperty('--c', pillBg(role)); mark.style.setProperty('--t', pillInk(role));
    span.appendChild(mark);
  }
  else span.appendChild(hNode('span', `talk-kind talk-kind-${peer.kind}`, peer.kind === 'external' ? tl('talk.mark.external') : peer.kind === 'subagent' ? tl('talk.mark.subagent') : tl('talk.mark.other')));
  return span;
}
const TALK_KIND = { session: tl('talk.kind.session'), subagent: tl('talk.kind.subagent'), external: tl('talk.kind.external') };
function talkGoneText(peer) {
  if (peer.alive) return '';
  return Number.isFinite(peer.removeAt) ? tl('talk.ended.until', { at: talkTime(peer.removeAt) }) : tl('talk.ended');
}
function talkHead() {
  const head = TALK.node.querySelector('[data-tk-head]');
  const conv = TALK.conv && TALK.list ? TALK.list.find((c) => c.id === TALK.conv) : null;
  const sig = JSON.stringify([TALK.owner, TALK.conv, conv && conv.peer, NAMES.rev]);
  if (head._sig === sig) return;
  head._sig = sig;
  const fk = head.contains(document.activeElement) ? document.activeElement.dataset.fk : undefined;
  const kids = [];
  if (!TALK.conv) {
    const back = hNode('button', 'wb-btn talk-back', tl('talk.back.card')); back.type = 'button'; back.dataset.tkClose = ''; back.dataset.fk = 'talk-close';
    const title = hNode('h3', 'talk-title', tl('talk.title'));
    kids.push(back, title);
  } else {
    const back = hNode('button', 'wb-btn talk-back', tl('talk.back.list')); back.type = 'button'; back.dataset.tkBack = ''; back.dataset.fk = 'talk-back';
    back.setAttribute('aria-label', tl('talk.back.list.aria'));
    kids.push(back);
    if (conv) {
      const p = conv.peer;
      // The peer's name, one line (cut with … : the whole name on hover and focus, 57-fulltext.js). Pressed: that robot.
      const who = p.agentId ? hNode('button', 'talk-peer') : hNode('span', 'talk-peer talk-peer-off');
      if (p.agentId) { who.type = 'button'; who.dataset.tkPeer = p.agentId; who.dataset.fk = 'talk-peer'; who.setAttribute('aria-label', tl('talk.peer.switch', { name: p.name || tl('talk.peer.someone') })); }
      else who.title = tl('talk.peer.unseen');
      who.append(talkPeerMark(p), hNode('span', 'talk-peer-name', p.name || tl('talk.noname')));
      const sub = hNode('p', 'talk-peer-sub', [TALK_KIND[p.kind] || '', talkGoneText(p)].filter(Boolean).join(' · '));
      const box = hNode('div', 'talk-peer-box'); box.append(who, sub);
      kids.push(box);
    }
  }
  head.replaceChildren(...kids);
  if (fk !== undefined) { const again = head.querySelector(`[data-fk="${CSS.escape(fk)}"]`); if (again) again.focus({ preventScroll: true }); }
}
function talkRow(c) {
  const b = hNode('button', 'talk-row');
  b.type = 'button'; b.dataset.tkConv = c.id; b.dataset.fk = `talk-${c.id}`;
  if (!c.peer.alive) b.classList.add('talk-row-gone');
  const top = hNode('span', 'talk-row-top');
  top.append(hNode('span', 'talk-row-name', c.peer.name || tl('talk.noname')), hNode('time', 'talk-row-at', talkTime(c.lastAt, true)));
  const bottom = hNode('span', 'talk-row-bottom');
  bottom.append(hNode('span', 'talk-row-pre', `${c.lastDir === 'out' ? tl('talk.row.mine') : ''}${c.preview}`));
  if (c.unread > 0) { const u = hNode('span', 'talk-unread', c.unread > 99 ? '99+' : String(c.unread)); u.dataset.tkUnread = String(c.unread); bottom.append(u); }
  const text = hNode('span', 'talk-row-text'); text.append(top, bottom);
  const gone = talkGoneText(c.peer);
  if (gone) text.append(hNode('span', 'talk-row-gone-note', gone));
  b.append(talkPeerMark(c.peer), text);
  b.setAttribute('aria-label', tl('talk.row.aria', { name: c.peer.name, at: talkTime(c.lastAt), unread: c.unread ? tl('talk.row.unread', { n: c.unread }) : '', preview: c.preview }));
  return b;
}
const TALK_STATE = { read: tl('talk.state.read'), delivered: tl('talk.state.delivered'), sent: tl('talk.state.sent'), undelivered: tl('talk.state.undelivered') };
function talkMsgSig(m) { return JSON.stringify([m.id, m.state, m.readAt, m.deliveredAt, m.text, m.cut, m.merged, m.dir]); }
function talkMsgNode(m) {
  const n = hNode('div', `talk-msg talk-${m.dir === 'out' ? 'out' : 'in'}`);
  n.dataset.tkMsg = m.id;
  n._at = m.at; n._dir = m.dir;
  const bubble = hNode('div', 'talk-bubble');
  if (m.state === 'undelivered') bubble.classList.add('talk-undelivered');
  const text = hNode('div', 'talk-text talk-folded');
  text.dataset.tkText = '';
  text.appendChild(histMarkdown(m.text));
  const more = hNode('button', 'talk-more', tl('talk.more')); more.type = 'button'; more.dataset.tkMore = ''; more.hidden = true;
  bubble.append(text, more);
  if (m.cut) bubble.appendChild(hNode('p', 'talk-note', tl('talk.cut')));
  if (m.merged) bubble.appendChild(hNode('p', 'talk-note', tl('talk.merged')));
  const meta = hNode('p', 'talk-meta');
  meta.appendChild(hNode('time', 'talk-at', talkTime(m.at)));
  if (m.dir === 'out') {
    const st = hNode('span', `talk-state talk-state-${m.state}`, m.state === 'read' && Number.isFinite(m.readAt) ? tl('talk.state.read.at', { at: talkTime(m.readAt) }) : TALK_STATE[m.state] || '');
    st.dataset.tkState = m.state;
    if (m.state === 'undelivered') st.title = tl('talk.state.undelivered.why');
    meta.appendChild(st);
  }
  if (m.via === 'subagent' || m.via === 'parent') meta.appendChild(hNode('span', 'talk-via', m.via === 'subagent' ? tl('talk.via.subagent') : tl('talk.via.parent')));
  n.append(bubble, meta);
  return n;
}
/* A long text is folded to three lines (as the history's messages from other sessions); 全文を表示 or a press on the text
   opens it, and a press on the opened text folds it again — not while text is selected, not on a link or a control. */
function talkMeasure() {
  const pane = talkPane();
  if (!pane || !pane.offsetParent) return;
  for (const t of pane.querySelectorAll('[data-tk-text]')) {
    if (t._measured) continue;
    if (!t.clientHeight) continue;
    t._measured = true;
    const long = t.scrollHeight > t.clientHeight + 1;
    t._long = long;
    t.classList.toggle('talk-folded', long);
    t.classList.toggle('talk-foldable', long);
    const more = t.parentNode.querySelector('[data-tk-more]');
    if (more) more.hidden = !long;
  }
}
function talkFold(text, open) {
  const more = text.parentNode.querySelector('[data-tk-more]');
  text.classList.toggle('talk-folded', !open);
  if (more) { more.textContent = open ? tl('talk.fold') : tl('talk.more'); more.setAttribute('aria-expanded', String(open)); }
  if (!open) {   // folded: its start stays in view
    const pane = talkPane(), msg = text.closest('.talk-msg');
    if (pane && msg && msg.getBoundingClientRect().top < pane.getBoundingClientRect().top) msg.scrollIntoView({ block: 'nearest' });
  }
}
function talkClick(e) {
  const t = e.target;
  if (t.closest('[data-tk-close]')) { talkShow(false); return; }
  if (t.closest('[data-tk-back]')) { TALK.conv = null; TALK.note = ''; talkRender(); const r = TALK.node.querySelector('[data-tk-conv]'); (r || TALK.node.querySelector('[data-tk-close]')).focus({ preventScroll: true }); return; }
  const row = t.closest('[data-tk-conv]');
  if (row) { talkOpenConv(row.dataset.tkConv); return; }
  const peer = t.closest('[data-tk-peer]');
  if (peer) { talkSwitch(peer.dataset.tkPeer); return; }
  if (t.closest('[data-tk-newer]')) { talkToEnd(); return; }
  if (t.closest('[data-tk-older]')) { talkLoad(TALK.conv, true); return; }
  const more = t.closest('[data-tk-more]');
  if (more) { const text = more.parentNode.querySelector('[data-tk-text]'); talkFold(text, text.classList.contains('talk-folded')); return; }
  const text = t.closest('[data-tk-text]');
  if (text && text._long) {
    if (t.closest('a, button, input, textarea, select, pre, .h-tablewrap')) return;   // its own action, or a box that scrolls
    const sel = window.getSelection && window.getSelection();
    if (sel && !sel.isCollapsed && text.contains(sel.anchorNode)) return;           // selecting text, not pressing
    talkFold(text, text.classList.contains('talk-folded'));
  }
}
function talkOpenConv(convId) {
  TALK.conv = convId; TALK.note = ''; TALK.atEnd = true; TALK.newer = false; TALK.nodes.clear();
  const box = TALK.msgs.get(convId);
  talkRender();
  if (!box || !box.loaded) talkLoad(convId, false);
  const back = TALK.node.querySelector('[data-tk-back]'); if (back) back.focus({ preventScroll: true });
}
/* The header's name pressed: the card switches to that robot, its talk open on this same conversation (a talk's id is
   the same seen from either side). A peer not on this page says so and stays. */
function talkSwitch(agentId) {
  const label = SOURCE.talkLabel(agentId);
  if (!label || !DEF[label]) { showToast(tl('talk.robot.absent')); return; }
  if (label === TALK.owner) return;
  TALK.want = TALK.conv;
  openRobot(label);
}
function talkBody() {
  const pane = talkPane();
  if (!TALK.conv) {
    const sig = JSON.stringify(['list', TALK.list, TALK.listError, TALK.note, TALK.more]);
    if (pane._sig === sig) return;
    pane._sig = sig;
    const fk = pane.contains(document.activeElement) ? document.activeElement.dataset.fk : undefined;
    const kids = [];
    if (TALK.note) kids.push(hNode('p', 'talk-empty talk-gone-note', TALK.note));
    if (TALK.listError) kids.push(hNode('p', 'talk-empty talk-error', TALK.listError));
    else if (!TALK.list) kids.push(hNode('p', 'talk-empty', tl('talk.loading')));
    else if (!TALK.list.length) kids.push(hNode('p', 'talk-empty', tl('talk.list.empty')));
    else {
      const ul = hNode('ul', 'talk-list');
      for (const c of TALK.list) { const li = hNode('li'); li.appendChild(talkRow(c)); ul.appendChild(li); }
      kids.push(ul);
      if (TALK.more) kids.push(hNode('p', 'talk-empty', tl('talk.list.newest', { n: TALK.list.length })));
    }
    pane.replaceChildren(...kids);
    pane.scrollTop = 0;
    if (fk !== undefined) { const again = pane.querySelector(`[data-fk="${CSS.escape(fk)}"]`); if (again) again.focus({ preventScroll: true }); }
    return;
  }
  const box = TALK.msgs.get(TALK.conv) || { items: [], loaded: false, busy: true };
  const sig = JSON.stringify(['conv', TALK.conv, box.items.map(talkMsgSig), box.more, box.busy, box.error, box.loaded]);
  if (pane._sig === sig) return;
  pane._sig = sig;
  const keepTop = !TALK.atEnd && pane.firstChild ? talkAnchor(pane) : null;
  const kids = [];
  if (box.more) {
    const older = hNode('button', 'talk-older', box.busy ? tl('talk.loading') : tl('talk.older')); older.type = 'button'; older.dataset.tkOlder = '';
    kids.push(older);
  }
  if (box.error) kids.push(hNode('p', 'talk-empty talk-error', box.error));
  if (!box.loaded && !box.error) kids.push(hNode('p', 'talk-empty', tl('talk.loading')));
  else if (box.loaded && !box.items.length) kids.push(hNode('p', 'talk-empty', tl('talk.messages.empty')));
  let day = '';
  const keep = new Map();
  for (const m of box.items) {
    const d = new Date(m.at).toDateString();
    if (d !== day) { day = d; const dt = new Date(m.at); kids.push(hNode('p', 'talk-day', dt.toLocaleDateString(LOCALE, { month: 'long', day: 'numeric' }))); }
    const ms = talkMsgSig(m), old = TALK.nodes.get(m.id);
    const node = old && old.sig === ms ? old.node : talkMsgNode(m);
    keep.set(m.id, { sig: ms, node });
    kids.push(node);
  }
  TALK.nodes = keep;
  pane.replaceChildren(...kids);
  talkObserve(pane);
  requestAnimationFrame(() => {
    talkMeasure();
    if (TALK.atEnd) talkToEnd();
    else if (keepTop) talkRestoreAnchor(pane, keepTop);
  });
  talkPaintNewer();
}
function talkAnchor(pane) {
  const top = pane.getBoundingClientRect().top;
  for (const n of pane.querySelectorAll('[data-tk-msg]')) if (n.getBoundingClientRect().bottom > top + 1) return { id: n.dataset.tkMsg, y: n.getBoundingClientRect().top - top };
  return null;
}
function talkRestoreAnchor(pane, a) {
  const n = [...pane.querySelectorAll('[data-tk-msg]')].find((x) => x.dataset.tkMsg === a.id);
  if (n) pane.scrollTop += n.getBoundingClientRect().top - pane.getBoundingClientRect().top - a.y;
  TALK.top = pane.scrollTop;
}

/* ---------- seen: what came in and was on screen, told to the server (talk.seen) ----------
   A message from the peer counts as seen when at least half of it has been in the pane while the talk shows and the
   tab is visible. The newest such time goes out as upTo, once per new value; the server recounts the unread and answers
   with a conv op and, when a total changed, talk.badges. */
const talkSeenIO = typeof IntersectionObserver === 'function' ? new IntersectionObserver((entries) => {
  for (const e of entries) {
    if (!e.isIntersecting || !TALK.conv || !TALK.agent) continue;
    const n = e.target;
    if (n._dir !== 'in') continue;
    const k = `${TALK.agent}|${TALK.conv}`;
    if (!(n._at <= (TALK.seenWant.get(k) || -1))) TALK.seenWant.set(k, n._at);
  }
  talkSeenFlush();
}, { threshold: 0.5 }) : null;
let talkSeenRoot = null;
function talkObserve(pane) {
  if (!talkSeenIO) return;
  if (talkSeenRoot !== pane) talkSeenRoot = pane;
  talkSeenIO.disconnect();
  for (const n of pane.querySelectorAll('.talk-msg.talk-in')) talkSeenIO.observe(n);
}
function talkSeenFlush() {
  if (document.visibilityState !== 'visible' || !TALK.on || !TALK.conv || !TALK.agent) return;
  const k = `${TALK.agent}|${TALK.conv}`, want = TALK.seenWant.get(k);
  if (!Number.isFinite(want) || want <= (TALK.seenSent.get(k) || -1)) return;
  TALK.seenSent.set(k, want);
  talkSend('talk.seen', { agentId: TALK.agent, convId: TALK.conv, upTo: Math.max(0, Math.round(want)) });
}
document.addEventListener('visibilitychange', talkSeenFlush);

/* ---------- the card ---------- */
function talkRender() {
  if (!TALK.node) return;
  talkHead();
  talkBody();
  talkPaintButton();
}
/* The chat button's unread badge: talk.badges, the server's totals per robot. */
function talkPaintButton() {
  const b = rbEl.querySelector('[data-rb-talk]');
  if (!b) return;
  const n = (TALK.agent && TALK.badges[TALK.agent]) || 0;
  const badge = b.querySelector('[data-rb-talk-n]');
  const text = n > 99 ? '99+' : String(n);
  if (badge) { badge.hidden = !n; if (badge.textContent !== text) badge.textContent = text; }
  const label = n ? tl('talk.title.unread', { n }) : tl('talk.title');
  if (b.getAttribute('aria-label') !== label) b.setAttribute('aria-label', label);
  if (b.getAttribute('aria-pressed') !== String(TALK.on)) b.setAttribute('aria-pressed', String(TALK.on));
}
function talkShow(on) {
  TALK.on = !!on && !!rbState.id;
  if (!TALK.on) { TALK.conv = null; TALK.note = ''; }
  talkSync();
  const again = rbEl.querySelector(TALK.on ? '[data-tk-close]' : '[data-rb-talk]');
  if (again) again.focus({ preventScroll: true });
}
/* After every renderRobot (and when the card closes): the socket follows the card's robot, and the pane takes the
   card's place below its head while it is on. */
function talkSync() {
  const robot = rbEl.hidden ? null : rbState.id;
  const agent = robot ? SOURCE.talkAgentId(robot) : null;
  if (robot !== TALK.owner) {
    TALK.owner = robot; TALK.agent = agent;
    TALK.conv = robot && TALK.want ? TALK.want : null;
    TALK.want = null; TALK.note = ''; TALK.atEnd = true; TALK.newer = false; TALK.nodes.clear();
    if (!robot) TALK.on = false;
    if (TALK.node) { const p = talkPane(); if (p) p._sig = ''; TALK.node.querySelector('[data-tk-head]')._sig = ''; }
  }
  TALK.agent = agent;
  talkFollow(agent);
  if (TALK.on && TALK.conv && TALK.agent && !(TALK.msgs.get(TALK.conv) || {}).loaded && !(TALK.msgs.get(TALK.conv) || {}).busy && !(TALK.msgs.get(TALK.conv) || {}).error) talkLoad(TALK.conv, false);
  rbEl.classList.toggle('rb-talking', TALK.on);
  if (TALK.on) {
    if (!TALK.node) TALK.node = talkBuildNode();
    if (TALK.node.parentNode !== rbEl) {
      const head = rbEl.querySelector('.rb-head');
      if (head) head.after(TALK.node); else rbEl.appendChild(TALK.node);
      const pane = talkPane();
      requestAnimationFrame(() => { talkMeasure(); if (TALK.atEnd) talkToEnd(); else pane.scrollTop = TALK.top; });
    }
    if (HIST.compose) HIST.compose.hidden = true;
    talkRender();
  } else if (TALK.node && TALK.node.parentNode) TALK.node.remove();
  // The card was rebuilt (50-panel.js keyed) with the focus in the talk pane, put back only now: the focus goes back too.
  const lost = rbEl._lostFk;
  rbEl._lostFk = undefined;
  const again = lost !== undefined && TALK.on && TALK.node ? TALK.node.querySelector(`[data-fk="${CSS.escape(lost)}"]`) : null;
  if (again) again.focus({ preventScroll: true });
  talkPaintButton();
}
rbEl.addEventListener('click', (e) => { if (e.target.closest('[data-rb-talk]') && rbState.id) talkShow(!TALK.on); });
