/* ---------- 応答の履歴: the robot card's second tab (requester, 10-18) ----------
   "ロボットに合わせた時に会話履歴みたいな感じで" / "応答の履歴タブをこのメニューに作って、それ選択したらメニュー全体が
   会話の履歴見れるようになる感じがいいな". The server reads the last turns of that robot's transcript only when this tab
   asks (sources/history.py), and again every HIST_POLL_MS while it stays open.

   Everything here is built with DOM nodes: a transcript holds any text at all (files read, pages fetched, HTML), so
   every character of it goes in through textContent, never through innerHTML, and this part has no HTML template.
   The answers are Markdown, drawn by a small subset: headings, lists, quotes, rules, tables, fenced and inline code
   (never converted inside), bold, italics, links — an href only when the URL, its character references decoded,
   is http: or https: — and images as a mark (nothing is fetched). */
const HIST_POLL_MS = 3000;
/* atEnd / top: where the reader is in the pane, kept here because the pane itself is not kept — renderRobot rebuilds the
   whole card (keyed) whenever its key changes, and the new pane starts at scrollTop 0 (measured 10-19: every new turn of
   a working session sent the reader to the top). newer: answers came while the reader was above (the 新しい応答 marker). */
const HIST = { tab: 'now', id: null, data: null, error: '', timer: 0, busy: false, node: null, sig: '',
  atEnd: true, top: 0, newer: false, marker: null, compose: null, sent: null, wide: false, imgs: new Map(), box: null };

function hNode(tag, cls, text) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text !== undefined && text !== null) n.textContent = String(text);
  return n;
}

/* A link's target as the browser would read it: character references decoded, then whitespace and controls out. */
function histDecodeRefs(s) {
  return String(s).replace(/&(#x[0-9a-f]+|#[0-9]+|[a-z]+);?/gi, (m, ref) => {
    const r = ref.toLowerCase();
    if (r[0] === '#') {
      const code = r[1] === 'x' ? parseInt(r.slice(2), 16) : parseInt(r.slice(1), 10);
      return Number.isFinite(code) && code >= 0 && code <= 0x10ffff ? String.fromCodePoint(code) : '';
    }
    return { amp: '&', lt: '<', gt: '>', quot: '"', apos: "'", colon: ':', tab: '\t', newline: '\n' }[r] ?? m;
  });
}
function histSafeHref(raw) {
  const url = histDecodeRefs(raw).replace(/[\u0000- \u007f-\u009f]/g, '');
  return /^https?:/i.test(url) ? url : null;
}

/* Inline Markdown into parent: code spans first (their text is left as it is), then images, links, bold, italics. */
const HIST_INLINE = /(\x60+)([\s\S]+?)\1|!\[([^\]\n]*)\]\(([^)\s]*)\)|\[([^\]\n]+)\]\(([^)\s]+)\)|\*\*([^*\n](?:[\s\S]*?[^*\n])?)\*\*|\*([^*\s\n](?:[^*\n]*?[^*\s\n])?)\*/g;
function histInline(parent, text) {
  let last = 0;
  const re = new RegExp(HIST_INLINE.source, 'g');   // its own: the calls below for a link's text or bold recurse
  const src = String(text);
  for (let m = re.exec(src); m; m = re.exec(src)) {
    if (m.index > last) parent.appendChild(document.createTextNode(src.slice(last, m.index)));
    if (m[1]) parent.appendChild(hNode('code', '', m[2]));
    else if (m[4] !== undefined && m[0][0] === '!') parent.appendChild(hNode('span', 'h-img', `画像: ${m[3] || '（説明なし）'}`));
    else if (m[5] !== undefined) {
      const href = histSafeHref(m[6]);
      if (href) {
        const a = hNode('a');
        a.setAttribute('href', href);
        a.setAttribute('target', '_blank');
        a.setAttribute('rel', 'noopener noreferrer');
        histInline(a, m[5]);
        parent.appendChild(a);
      } else parent.appendChild(document.createTextNode(m[0]));   // not http(s): the text as written
    } else if (m[7] !== undefined) { const b = hNode('strong'); histInline(b, m[7]); parent.appendChild(b); }
    else if (m[8] !== undefined) { const i = hNode('em'); histInline(i, m[8]); parent.appendChild(i); }
    last = re.lastIndex;
  }
  if (last < src.length) parent.appendChild(document.createTextNode(src.slice(last)));
}

const histCells = (line) => line.trim().replace(/^\|/, '').replace(/\|$/, '').split('|').map((c) => c.trim());
/* Block Markdown into a new element. */
function histMarkdown(text) {
  const root = hNode('div', 'h-md');
  const lines = String(text).replace(/\r\n?/g, '\n').split('\n');
  let i = 0, para = null, list = null;
  const flush = () => { para = null; list = null; };
  while (i < lines.length) {
    const line = lines[i];
    const fence = line.match(/^\s*(\x60{3,}|~{3,})\s*([\w+-]*)\s*$/);
    if (fence) {                                       // a code block: kept as it is, up to its closing fence
      flush();
      const body = [];
      i += 1;
      while (i < lines.length && !lines[i].trim().startsWith(fence[1])) { body.push(lines[i]); i += 1; }
      i += 1;
      const pre = hNode('pre', 'h-code');
      pre.appendChild(hNode('code', '', body.join('\n')));
      root.appendChild(pre);
      continue;
    }
    if (!line.trim()) { flush(); i += 1; continue; }
    const h = line.match(/^\s{0,3}(#{1,6})\s+(.*)$/);
    if (h) { flush(); const n = hNode(`h${Math.min(6, h[1].length + 3)}`, 'h-h'); histInline(n, h[2].replace(/\s+#+\s*$/, '')); root.appendChild(n); i += 1; continue; }
    if (/^\s{0,3}([-*_])(\s*\1){2,}\s*$/.test(line)) { flush(); root.appendChild(hNode('hr')); i += 1; continue; }
    if (line.includes('|') && i + 1 < lines.length && /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/.test(lines[i + 1])) {
      flush();
      const table = hNode('table', 'h-table'), head = hNode('tr');
      for (const c of histCells(line)) { const th = hNode('th'); histInline(th, c); head.appendChild(th); }
      const thead = hNode('thead'); thead.appendChild(head); table.appendChild(thead);
      const tbody = hNode('tbody');
      i += 2;
      while (i < lines.length && lines[i].includes('|') && lines[i].trim()) {
        const tr = hNode('tr');
        for (const c of histCells(lines[i])) { const td = hNode('td'); histInline(td, c); tr.appendChild(td); }
        tbody.appendChild(tr);
        i += 1;
      }
      table.appendChild(tbody);
      const wrap = hNode('div', 'h-tablewrap'); wrap.appendChild(table); root.appendChild(wrap);
      continue;
    }
    const q = line.match(/^\s{0,3}>\s?(.*)$/);
    if (q) {
      flush();
      const body = [q[1]];
      i += 1;
      while (i < lines.length && /^\s{0,3}>/.test(lines[i])) { body.push(lines[i].replace(/^\s{0,3}>\s?/, '')); i += 1; }
      const bq = hNode('blockquote', 'h-quote');
      bq.appendChild(histMarkdown(body.join('\n')));
      root.appendChild(bq);
      continue;
    }
    const li = line.match(/^(\s*)([-*+]|\d{1,9}[.)])\s+(.*)$/);
    if (li) {
      const ordered = /\d/.test(li[2]);
      if (!list || list.ordered !== ordered) {
        para = null;
        list = { ordered, el: hNode(ordered ? 'ol' : 'ul', 'h-list') };
        root.appendChild(list.el);
      }
      const item = hNode('li');
      if (li[1].length >= 2) item.className = 'h-sub';
      histInline(item, li[3]);
      list.el.appendChild(item);
      i += 1;
      continue;
    }
    list = null;
    if (!para) { para = hNode('p'); root.appendChild(para); } else para.appendChild(hNode('br'));
    histInline(para, line);
    i += 1;
  }
  return root;
}

/* ---------- the items ---------- */
const HIST_TIME = (at) => (Number.isFinite(at) ? new Date(at).toLocaleTimeString('ja-JP', { hour: '2-digit', minute: '2-digit' }) : '');
function histCutNote(item) { return item.cut ? hNode('p', 'h-cut', '（長いので途中まで）') : null; }
/* A fold (a message from another session, the harness's text, a tool's IN / OUT): the summary opens and closes it,
   and once open a click anywhere in its body closes it too (requester, 10-20: 「開くと閉じづらい」), then the row's
   head is scrolled back into view if it went above. A click does not close it when it selects text (a drag, a
   double-click: the selection is not empty, the pointer moved, or a second click came within HIST_DBL_MS), or when
   it lands on something with its own action (HIST_FOLD_KEEP: a link, a button, a field, a picture, the whole-text
   tag, a table that scrolls sideways, and the scroll bar of a long code line).
   Keyboard: Enter / Space on the summary, as before — focus stays on the summary after it opens, so the body gets no
   key and no extra tab stop of its own. */
const HIST_FOLD_KEEP = 'a[href], button, input, textarea, select, label, img, video, [contenteditable], .h-thumb, .fulltext';
const HIST_DRAG_PX = 4, HIST_DBL_MS = 280;
const histScrollsX = (el) => el.scrollWidth > el.clientWidth + 1 && /auto|scroll/.test(getComputedStyle(el).overflowX);
function histFoldKeeps(target, d, y) {
  if (!(target instanceof Element) || target.closest('summary') || target.closest(HIST_FOLD_KEEP)) return true;
  const table = target.closest('.h-tablewrap');
  if (table && histScrollsX(table)) return true;
  for (let el = target; el && el !== d; el = el.parentElement) {   // on the scroll bar under a sideways-scrolling box
    if (histScrollsX(el) && y > el.getBoundingClientRect().top + el.clientTop + el.clientHeight) return true;
  }
  const sel = window.getSelection ? window.getSelection() : null;
  return !!(sel && !sel.isCollapsed && String(sel).trim() && d.contains(sel.anchorNode));
}
function histFolded(cls, title, body, open) {
  const d = hNode('details', cls);
  if (open) d.open = true;
  const s = hNode('summary');
  for (const part of title) s.appendChild(part);
  d.appendChild(s);
  for (const b of body) if (b) d.appendChild(b);
  let down = null, pending = 0;
  d.addEventListener('pointerdown', (e) => { down = { x: e.clientX, y: e.clientY }; });
  d.addEventListener('click', (e) => {
    const moved = down && Math.hypot(e.clientX - down.x, e.clientY - down.y) > HIST_DRAG_PX;
    down = null;
    clearTimeout(pending);
    if (!d.open || moved || e.detail > 1 || histFoldKeeps(e.target, d, e.clientY)) return;
    // a double-click selects a word: wait out its second click before closing (and look at the selection again then)
    const target = e.target, y = e.clientY;
    pending = setTimeout(() => {
      if (!d.open || histFoldKeeps(target, d, y)) return;
      d.open = false;
      const pane = d.closest('[data-rb-hist]'), top = s.getBoundingClientRect().top;
      if (pane && top < pane.getBoundingClientRect().top) s.scrollIntoView({ block: 'nearest' });
    }, HIST_DBL_MS);
  });
  return d;
}
/* The other end of a SendMessage, or the sender of a received message (2.3.6, requester 10-20: 「閉じた状態でも誰宛か
   わかるようにして、その宛先クリックでそのロボットの表示に切り替え」). The server links it to a session here
   (World._history_peers: an agents-list name, `name [ref]`, a uds socket or the pid in it); a session with a robot on
   this page is a button that switches the card to that robot (the same way as ← →: the camera follows, the tab
   stays). Anything else is plain text, not focusable, with a title that says it is not here. */
function histPeerName(text, session) {
  const label = session && typeof labelOf === 'function' ? labelOf(session) : null;
  if (label && robots.some((R) => R.def.id === label)) {
    const b = hNode('button', 'h-peerlink', text);
    b.type = 'button'; b.dataset.hGo = label;
    b.title = `${label} のロボットに切り替える`;
    return b;
  }
  const s = hNode('span', 'h-peername', text);
  s.title = 'この viz にいないセッション';
  return s;
}
function histItem(item) {
  const at = hNode('time', 'h-at', HIST_TIME(item.at));
  if (item.kind === 'user') {
    const n = hNode('div', 'h-item h-user');
    const head = hNode('p', 'h-who', '依頼者'); head.appendChild(at); n.appendChild(head);
    n.appendChild(hNode('p', 'h-plain', item.text));
    const cut = histCutNote(item); if (cut) n.appendChild(cut);
    for (const path of Array.isArray(item.gone) ? item.gone : []) n.appendChild(hNode('p', 'h-gone', `元の画像ファイルは消えている: ${path}`));
    return n;
  }
  if (item.kind === 'assistant') {
    const n = hNode('div', 'h-item h-asst');
    n.appendChild(histMarkdown(item.text));
    const cut = histCutNote(item); if (cut) n.appendChild(cut);
    return n;
  }
  if (item.kind === 'channel') {   // a prompt that came through a channel (from this page, for jui-viz)
    const n = hNode('div', 'h-item h-user h-channel');
    const head = hNode('p', 'h-who', /(^|:)jui-viz$/.test(String(item.server || '')) ? 'ページから（jui-viz の channel）' : `channel ${item.server || ''}`);
    head.appendChild(at); n.appendChild(head);
    n.appendChild(hNode('p', 'h-plain', item.text));
    const cut = histCutNote(item); if (cut) n.appendChild(cut);
    return n;
  }
  if (item.kind === 'peer') {
    const who = hNode('b', 'h-from'); who.append(histPeerName(item.from, item.fromSession), ' から');
    return histFolded('h-item h-peer', [who, hNode('span', 'h-head', String(item.text).split('\n').find((l) => l.trim()) || ''), at],
      [hNode('p', 'h-plain', item.text), histCutNote(item)], false);
  }
  if (item.kind === 'harness') {
    return histFolded('h-item h-harness', [hNode('b', '', item.label), hNode('span', 'h-head', 'ハーネスが入れた文'), at],
      [hNode('p', 'h-plain', item.text), histCutNote(item)], false);
  }
  if (item.kind === 'tool') {
    const first = String(item.in || '').split('\n')[0];
    const title = [hNode('b', 'h-tname', item.name), hNode('span', 'h-head', item.description || first)];
    if (item.name === 'SendMessage' && typeof item.to === 'string') {   // who it went to and what about, folded too
      const to = hNode('span', 'h-to'); to.append('→ ', histPeerName(item.to, item.toSession));
      title.splice(1, 1, to, hNode('span', 'h-head', item.summary || first));
    }
    if (item.error) title.push(hNode('span', 'h-err', 'エラー'));
    if (item.out === undefined) title.push(hNode('span', 'h-run', '結果待ち'));
    // The time the tool was called (its tool_use record's), at the right end after the marks (2.3.7, requester 10-20:
    // 「このBashとかのタイトルの右端にその時の時刻表示できる？」); the description narrows first (.h-head), never the time.
    title.push(at);
    const io = hNode('div', 'h-io');
    io.appendChild(hNode('span', 'h-io-k', 'IN'));
    io.appendChild(hNode('pre', 'h-code', `${item.in || ''}${item.inCut ? '\n…' : ''}`));
    if (item.out !== undefined) {
      io.appendChild(hNode('span', 'h-io-k', 'OUT'));
      io.appendChild(hNode('pre', `h-code${item.error ? ' h-code-err' : ''}`, `${item.out}${item.outCut ? '\n…' : ''}`));
      if (Array.isArray(item.imgs) && item.imgs.length) { const row = hNode('div', 'h-imgs'); for (const ref of item.imgs) row.appendChild(histThumb(ref)); io.appendChild(row); }
    }
    return histFolded('h-item h-tool', title, [io], false);
  }
  if (item.kind === 'thought') return hNode('p', 'h-item h-mark', '考えた');
  if (item.kind === 'image') {
    if (!item.img) return hNode('p', 'h-item h-mark', '画像 1 枚（表示できない形式）');
    const row = hNode('div', 'h-item h-imgs');
    row.appendChild(histThumb(item.img));
    return row;
  }
  return null;
}
function histBuild(data) {
  const box = hNode('div', 'h-list-box');
  const items = Array.isArray(data.items) ? data.items : [];
  if (data.more) box.appendChild(hNode('p', 'h-note', `直近 ${items.filter((x) => x.kind !== 'thought' && x.kind !== 'image').length} 件（それより前は表示しない）`));
  let prev = null;
  const seen = new Map();
  for (const item of items) {
    if (item.kind === 'thought' && prev === 'thought') continue;   // one mark for a run of thinking
    if (item.kind === 'image' && item.img && prev === 'image' && box.lastChild && box.lastChild.classList.contains('h-imgs')) {
      box.lastChild.appendChild(histThumb(item.img));               // pictures side by side
      continue;
    }
    const n = histItem(item);
    if (n) {
      // Which item this is, so the place read above survives a rebuild of the list (the oldest items leave the window).
      const base = `${item.kind}|${item.at}|${String(item.text ?? item.in ?? item.name ?? '').slice(0, 200)}`;
      seen.set(base, (seen.get(base) || 0) + 1);
      n._hk = `${base}|${seen.get(base)}`;
      box.appendChild(n);
    }
    prev = item.kind;
  }
  if (!items.length) box.appendChild(hNode('p', 'h-note', 'まだ応答がない'));
  return box;
}

/* ---------- the tab ---------- */
function histPane() { return rbEl.querySelector('[data-rb-hist]'); }
const HIST_END_PX = 24;
function histMarker() {
  if (!HIST.marker) {
    const b = hNode('button', 'h-newer', '新しい応答 ↓');
    b.type = 'button';
    b.dataset.hNewer = '';
    b.dataset.fk = 'rb-hist-newer';
    b.addEventListener('click', () => { const pane = histPane(); if (pane) histToEnd(pane); });
    HIST.marker = b;
  }
  HIST.marker.hidden = !HIST.newer;
  return HIST.marker;
}
function histToEnd(pane) {
  HIST.atEnd = true; HIST.newer = false;
  pane.scrollTop = pane.scrollHeight;
  HIST.top = pane.scrollTop;
  histMarker();
}
/* The reader's place, on every scroll of the pane (a user's or ours). */
function histRemember(pane) {
  if (pane.hidden || !pane.contains(HIST.node)) return;
  HIST.top = pane.scrollTop;
  HIST.atEnd = pane.scrollHeight - pane.scrollTop - pane.clientHeight < HIST_END_PX;
  if (HIST.atEnd && HIST.newer) { HIST.newer = false; histMarker(); }
}
/* The place kept in HIST, put back on a pane that was just given the list (a rebuilt card, the tab opened). */
function histRestore(pane) {
  if (HIST.atEnd) histToEnd(pane);
  else pane.scrollTop = HIST.top;
}
function histShow() {
  const pane = histPane();
  if (!pane) return;
  if (!pane._histBound) { pane._histBound = true; pane.addEventListener('scroll', () => histRemember(pane), { passive: true }); }
  if (HIST.error && !HIST.data) { pane.replaceChildren(hNode('p', 'h-note', HIST.error)); return; }
  if (!HIST.node) { pane.replaceChildren(hNode('p', 'h-note', '読み込み中…')); return; }
  if (pane.firstChild !== HIST.node) { pane.replaceChildren(HIST.node, histMarker()); histRestore(pane); }
}
/* The first item at the top of the pane and how far below the top it starts. */
function histAnchor(pane) {
  if (!HIST.node || !pane.contains(HIST.node)) return null;
  const top = pane.getBoundingClientRect().top;
  for (const n of HIST.node.children) {
    if (n._hk && n.getBoundingClientRect().bottom > top + 1) return { key: n._hk, y: n.getBoundingClientRect().top - top };
  }
  return null;
}
async function histFetch() {
  const id = HIST.id;
  if (!id || HIST.busy || HIST.tab !== 'history') return;
  HIST.busy = true;
  const got = await SOURCE.history(id);
  HIST.busy = false;
  if (HIST.id !== id || HIST.tab !== 'history') return;
  if (!got.ok) { HIST.error = got.error === 'demo' ? 'デモでは応答の履歴を表示しない' : '応答の履歴を読めない（このロボットの記録が見つからない）'; histShow(); return; }
  HIST.error = '';
  const sig = JSON.stringify(got.data.items);
  if (sig === HIST.sig && HIST.node) return;           // nothing new: the open folds and the scroll stay
  const pane = histPane();
  const shown = pane && !pane.hidden && HIST.node && pane.contains(HIST.node);
  const anchor = shown && !HIST.atEnd ? histAnchor(pane) : null;
  const had = !!HIST.data;
  HIST.sig = sig; HIST.data = got.data; HIST.node = histBuild(got.data);
  composeArrived(got.data.items);
  if (had && !HIST.atEnd) HIST.newer = true;          // the reader is above: leave the place, show the marker
  histShow();                                          // at the end: histRestore sends the pane to the newest
  if (anchor && pane && pane.contains(HIST.node)) {   // the same item at the same place, though the oldest left
    const top = pane.getBoundingClientRect().top;
    const same = [...HIST.node.children].find((n) => n._hk === anchor.key);
    if (same) pane.scrollTop += same.getBoundingClientRect().top - top - anchor.y;
    HIST.top = pane.scrollTop;
  }
}
function histStop() { clearInterval(HIST.timer); HIST.timer = 0; }
/* After every renderRobot: which tab shows, and the polling that keeps an open history fresh. */
function histSync() {
  const id = rbEl.hidden ? null : rbState.id;
  if (id !== HIST.id) { HIST.id = id; HIST.data = null; HIST.node = null; HIST.sig = ''; HIST.error = ''; HIST.atEnd = true; HIST.newer = false; histStop(); histImgsDrop(); }
  const tabs = rbEl.querySelectorAll('[data-rb-tab]');
  tabs.forEach((b) => b.setAttribute('aria-selected', String(b.dataset.rbTab === HIST.tab)));
  const body = rbEl.querySelector('.rb-body:not([data-rb-hist])'), pane = histPane();
  if (body) body.hidden = HIST.tab !== 'now';
  if (pane) pane.hidden = HIST.tab !== 'history';
  composePlace(pane, id);
  histWideSync(id);
  if (!id || HIST.tab !== 'history') { histStop(); return; }
  histShow();
  if (!HIST.timer) { histFetch(); HIST.timer = setInterval(() => { if (document.visibilityState === 'visible') { histFetch(); composePaint(); } }, HIST_POLL_MS); }
}
rbEl.addEventListener('click', (e) => {
  const b = e.target.closest('[data-rb-tab]');
  if (!b) return;
  const opening = b.dataset.rbTab === 'history' && HIST.tab !== 'history';
  HIST.tab = b.dataset.rbTab === 'history' ? 'history' : 'now';
  if (opening) {   // the tab opened: the newest shows (the bottom), the old place is not kept
    HIST.atEnd = true; HIST.newer = false;
    const pane = histPane();
    if (pane && HIST.node && pane.contains(HIST.node)) pane.replaceChildren();   // histShow puts it back and restores
  }
  histSync();
});

/* ---------- a prompt to the session of this robot (requester, 10-19) ----------
   "プロンプトをロボットの会話の履歴から打てないと不便だから打てるようにしよう" — and "別端末からは送れなくていいよ": the server takes it
   only from this page at http://127.0.0.1:<port> (server.prompt_checks). Here: the box under the history; Enter is a new
   line, the 送信 button or Ctrl/⌘+Enter opens a confirmation naming the robot and the session, and only its 送る sends.
   After that 「送信済み」 until the prompt shows in the history. The box is built once and moved into each rebuilt card,
   so what is typed survives a rebuild. A session without the relay, or with a jui-viz plugin older than 1.2.0 (its
   channel cannot deliver), gets the box disabled and the reason. */
const PROMPT_MAX_BYTES = 8192;   // server.PROMPT_MAX_BODY: the JSON body, not only the text
const composeBytes = (label, text) => new TextEncoder().encode(JSON.stringify({ sessionId: SESSION_UUID[label] || '', text })).length;
const RELAY_HOW_TEXT = RELAY_HOW.replace(/<[^>]+>/g, '');   // the same how-to as on a permission card, as plain text
const composeNorm = (t) => String(t || '').split(/\s+/).join(' ').trim();
/* Whether the CLI hands the channel's text to the session (sources/launch.py, 2.3.4): it does only for a session started
   naming the channel. The server's sessions slice says which case (launch); the words here are the same as the server's. */
const PROMPT_START = 'claude --dangerously-load-development-channels plugin:jui-viz@jsonui';
const PROMPT_START_CHANNELS = 'claude --channels plugin:jui-viz@jsonui';
const LAUNCH_WHY = {
  dev: [true, ''],
  channels: [true, '--channels で起動したセッション。managed settings の allowedChannelPlugins に jui-viz が載っていなければ届かない'],
  'no-flag': [false, '起動に channel の指定が無いので届かない'],
  other: [false, '起動の channel の指定に jui-viz が無いので届かない'],
  form: [false, '起動の指定の形が、この channel のつながり方と合わない（プラグインなら plugin:jui-viz@jsonui、jui viz relay install なら server:jui-viz）'],
  'server-channels': [false, 'server: の指定は --channels では効かない'],
  vscode: [false, 'VS Code 拡張のセッションは起動の指定を足せないので届かない'],
  desktop: [false, 'デスクトップアプリのセッションは起動の指定を足せないので届かない'],
  unreadable: [false, 'このセッションのプロセスの起動の引数を読めないので、届くか確かめられない'],
};
/* 送信中 until the receiver's own transcript shows the prompt (届いた); 届いていない when it has not, NOT_ARRIVED_MS after
   sending and with the session quiet (not busy) for QUIET_MS — a busy session takes it at the end of its turn. */
const PROMPT_WAIT = { notArrivedMs: 60000, quietMs: 30000 };
function composeTarget(id) {
  if (!id || !DEF[id]) return { why: '' };
  const sess = SESSIONS.find((x) => x.id === SESSION_OF[id]);
  const name = sess ? `${sess.id} のメインセッション（${DEF[sess.id].agent} · ${sess.room}）` : '';
  if (SOURCE.mode !== 'live') return { why: 'デモでは送れない' };
  if (DEF[id].kind === 'sub') return { why: `サブエージェントには送れない。${SESSION_OF[id]} のメインセッションのカードから送る` };
  if (location.hostname !== '127.0.0.1') return { why: `このページは http://127.0.0.1:${location.port}/ で開いたときだけ送れる（jui viz open）` };
  if (!sess || sess.status === 'ended') return { why: 'このセッションは終わっている' };
  if (!sess.relay) return { why: 'このセッションは中継（jui-viz の channel）につながっていないので送れない。' + RELAY_HOW_TEXT };
  if (!sess.prompt) return { why: 'このセッションの jui-viz プラグインが古いので送れない（1.2.0 から送れる）。/plugin で jui-viz を更新して、セッションを起動し直す' };
  const L = LAUNCH_WHY[sess.launch] || LAUNCH_WHY.unreadable;
  if (!L[0]) {
    return { why: `${L[1]}。届くのは、ターミナルで ${PROMPT_START}（起動のたびに確認が出る）か、managed settings の allowedChannelPlugins に jui-viz を載せて ${PROMPT_START_CHANNELS}（警告なし）と起動したセッションだけ。組織のアカウントは channelsEnabled も要る` };
  }
  return { why: '', name, note: L[1] };
}
/* The note above the box for a session that can take a prompt (LAUNCH_WHY's note: --channels) has a × (requester 10-20:
   "この注意書きの部分邪魔だから消せるようにしといて xボタンで消せて、消したら他でも表示されない"). Pressed: gone on every card and,
   kept in this browser (readPref / writePref, both try/catch), after a reload; 設定 › 「カードの説明をまた出す」 brings it
   back. A blocked storage still hides it for this page view. Only the note: the reason a box is disabled always shows. */
const CARD_NOTE_PREF = 'cardNote';
let cardNoteOff = readPref(CARD_NOTE_PREF, 'on') === 'off';
function cardNoteSet(off) {
  cardNoteOff = !!off;
  writePref(CARD_NOTE_PREF, cardNoteOff ? 'off' : 'on');
  composePaint();
  cardNotePaint();
}
function cardNotePaint() {
  const b = document.getElementById('card-note-back'), n = document.getElementById('card-note-state');
  if (b) b.disabled = !cardNoteOff;
  if (n) setText(n, cardNoteOff ? '消してある — ロボットのカードのプロンプト欄の上の説明（--channels のセッション）を出していません' : '出している');
}
{ const b = document.getElementById('card-note-back');
  if (b) b.addEventListener('click', () => cardNoteSet(false));
  cardNotePaint(); }
function composeBuild() {
  const box = hNode('div', 'h-compose');
  box.dataset.hCompose = '';
  const head = hNode('div', 'h-compose-head'); head.dataset.hHead = '';
  const why = hNode('p', 'h-compose-why'); why.dataset.hWhy = '';
  const noteX = hNode('button', 'h-note-x', '×'); noteX.type = 'button'; noteX.dataset.hNoteX = '';
  noteX.setAttribute('aria-label', 'この説明を消す（ほかのカードでも出さない。設定 › カードの説明をまた出す で戻る）'); noteX.title = 'この説明を消す';
  noteX.addEventListener('click', () => cardNoteSet(true));
  head.append(why, noteX);
  const area = hNode('textarea', 'h-compose-text');
  area.rows = 3;
  area.dataset.hText = '';
  area.dataset.fk = 'rb-prompt';
  area.setAttribute('aria-label', 'このセッションへのプロンプト');
  area.placeholder = 'このセッションへのプロンプト（Enter は改行。送信は ボタン か Ctrl/⌘+Enter）';
  const row = hNode('div', 'h-compose-row');
  const state = hNode('span', 'h-compose-state'); state.dataset.hState = ''; state.setAttribute('aria-live', 'polite');
  const send = hNode('button', 'wb-btn h-compose-send', '送信…'); send.type = 'button'; send.dataset.hSend = ''; send.dataset.fk = 'rb-prompt-send';
  row.append(state, send);
  const confirm = hNode('div', 'h-confirm'); confirm.dataset.hConfirm = ''; confirm.hidden = true;
  confirm.setAttribute('role', 'group'); confirm.setAttribute('aria-label', '送信の確認');
  const to = hNode('p', 'h-confirm-to'); to.dataset.hTo = '';
  const preview = hNode('p', 'h-confirm-text'); preview.dataset.hPreview = '';
  const acts = hNode('div', 'h-confirm-acts');
  const go = hNode('button', 'wb-btn h-confirm-go', 'このセッションへ送る'); go.type = 'button'; go.dataset.hGo = '';
  const back = hNode('button', 'wb-btn', 'やめる'); back.type = 'button'; back.dataset.hBack = '';
  acts.append(go, back);
  confirm.append(to, preview, acts);
  box.append(head, area, row, confirm);
  area.addEventListener('input', () => composePaint());
  area.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey) && !e.isComposing) { e.preventDefault(); composeAsk(); }
  });
  send.addEventListener('click', () => composeAsk());
  back.addEventListener('click', () => composeClose(true));
  go.addEventListener('click', () => { if (Date.now() - (box._askedAt || 0) > 350) composeSend(); });   // not the same key press that opened it
  return box;
}
function composeEls() {
  const b = HIST.compose;
  const q = (k) => b.querySelector(`[data-${k}]`);
  return { box: b, head: q('h-head'), why: q('h-why'), noteX: q('h-note-x'), area: q('h-text'), state: q('h-state'), send: q('h-send'), confirm: q('h-confirm'), to: q('h-to'), preview: q('h-preview'), go: q('h-go') };
}
/* After every histSync: the box under the history pane of the card shown, and its state. */
function composePlace(pane, id) {
  if (!HIST.compose) HIST.compose = composeBuild();
  const { box } = composeEls();
  if (HIST.compose._for !== id) {   // another robot: nothing typed for the last one goes to this one
    HIST.compose._for = id;
    composeEls().area.value = '';
    composeClose(false);
  }
  if (pane && box.previousElementSibling !== pane) pane.after(box);
  box.hidden = !pane || HIST.tab !== 'history';
  // The card was rebuilt (50-panel.js, keyed) while the box had the focus, and the box is put back only now: refocus.
  const lost = rbEl._lostFk;
  const again = lost !== undefined && !box.hidden ? box.querySelector('[data-fk="' + CSS.escape(lost) + '"]') : null;
  if (again) { rbEl._lostFk = undefined; again.focus({ preventScroll: true }); }   // not found here: the talk pane may hold it (58-talk.js)
  composePaint();
}
function composePaint() {
  if (!HIST.compose) return;
  const E = composeEls(), id = HIST.compose._for, t = composeTarget(id);
  const asking = !E.confirm.hidden;
  const note = !t.why && t.note && !cardNoteOff ? t.note : '';   // the reason (t.why) is never dismissed
  E.why.textContent = t.why || note;
  E.why.hidden = !(t.why || note);
  E.why.classList.toggle('h-compose-note', !!note);
  E.noteX.hidden = !note;
  E.head.hidden = E.why.hidden;
  E.area.disabled = !!t.why;
  E.area.readOnly = asking;
  const text = E.area.value, bytes = text.trim() ? composeBytes(id, text) : 0;
  E.send.disabled = !!t.why || !text.trim() || bytes > PROMPT_MAX_BYTES || asking;
  const sent = HIST.sent && HIST.sent.id === id ? HIST.sent : null;
  const phase = sent && !sent.error ? composePhase(sent) : '';
  E.state.textContent = bytes > PROMPT_MAX_BYTES ? `長すぎる（${bytes.toLocaleString('ja-JP')} / ${PROMPT_MAX_BYTES.toLocaleString('ja-JP')} バイト）`
    : sent && sent.error ? `送れなかった（${sent.error}）`
    : phase === 'arrived' ? `届いた ${HIST_TIME(sent.arrivedAt)}（受け手の記録に出た）`
    : phase === 'missing' ? `届いていない（${HIST_TIME(sent.at)} に送ったが、受け手の記録に出ない。候補: 起動の指定が無い・組織の channelsEnabled が無い・セッションが閉じた）`
    : sent ? `送信中 ${HIST_TIME(sent.at)}（受け手の記録に出るのを待っている。まだ届いたとは言えない）` : '';
  E.state.dataset.hPhase = bytes > PROMPT_MAX_BYTES ? 'long' : sent && sent.error ? 'error' : phase;
  E.state.classList.toggle('h-compose-err', bytes > PROMPT_MAX_BYTES || !!(sent && sent.error) || phase === 'missing');
  if (asking && t.why) composeClose(false);   // the session lost its relay while the confirmation was open
}
/* sending / arrived / missing for a prompt sent (and taken by the server). */
function composePhase(sent) {
  if (sent.arrivedAt) return 'arrived';
  const now = Date.now(), sess = SESSIONS.find((x) => x.id === SESSION_OF[sent.id]);
  if (sess && sess.status === 'busy') sent.quietSince = 0;
  else if (!sent.quietSince) sent.quietSince = now;
  return now - sent.at > PROMPT_WAIT.notArrivedMs && sent.quietSince && now - sent.quietSince > PROMPT_WAIT.quietMs ? 'missing' : 'sending';
}
function composeAsk() {
  const E = composeEls(), id = HIST.compose._for, t = composeTarget(id), text = E.area.value;
  if (t.why || !text.trim() || composeBytes(id, text) > PROMPT_MAX_BYTES || !E.confirm.hidden) return;
  E.to.textContent = `送り先: ${t.name}`;
  E.preview.textContent = text.length > 400 ? `${text.slice(0, 400)}…` : text;
  E.confirm.hidden = false;
  E.box._askedAt = Date.now();
  composePaint();
  E.go.focus({ preventScroll: true });
}
function composeClose(focusBack) {
  const E = composeEls();
  E.confirm.hidden = true;
  composePaint();
  if (focusBack) E.area.focus({ preventScroll: true });
}
async function composeSend() {
  const E = composeEls(), id = HIST.compose._for, text = E.area.value;
  if (composeTarget(id).why || !text.trim()) return;
  E.go.disabled = true;
  const got = await SOURCE.sendPrompt(id, text);
  E.go.disabled = false;
  composeClose(!got.ok);
  if (got.ok) { HIST.sent = { id, text, at: Date.now() }; E.area.value = ''; }
  else HIST.sent = { id, text, at: Date.now(), error: got.error || `HTTP ${got.status}` };
  composePaint();
}
/* The prompt sent shows in the receiver's transcript as a channel item of jui-viz (sources/history.py: the CLI's own
   record, origin.kind "channel", measured 10-19 on a real receiver started with --channels plugin:jui-viz@jsonui),
   its text the text sent: 届いた. Our own POST proves only that it was sent; the same words typed by hand do not count. */
function composeArrived(items) {
  const sent = HIST.sent;
  if (!sent || sent.error || sent.arrivedAt || sent.id !== HIST.id || !Array.isArray(items)) return;
  const want = composeNorm(sent.text).slice(0, 120);
  const fresh = (x) => !(Number(x.at) < sent.at - 60000);   // an older item with the same words is not this one
  const ours = (x) => x.kind === 'channel' && /(^|:)jui-viz$/.test(String(x.server || ''));
  if (items.some((x) => ours(x) && fresh(x) && composeNorm(x.text).startsWith(want))) { sent.arrivedAt = Date.now(); composePaint(); }
}

/* ---------- pictures (2.3.4, requester 10-19: "画像ファイルが履歴にある場合はサムネイル表示とクリックで拡大表示") ----------
   An image item names a picture by its place (sources/history.py); the bytes are asked for one picture at a time
   (SOURCE.historyImage, POST /api/history-image under the prompt's checks) when its thumbnail comes into view, and
   kept as a blob URL only while this robot's tab is open. The browser scales the thumbnail. A press opens it large
   in a dialog: ← → for the others in this history, Esc / the backdrop / 閉じる close it and give the focus back. */
const histImgKey = (ref) => `${HIST.id}|${ref.off}|${ref.n}`;
function histImgsDrop() {
  for (const v of HIST.imgs.values()) v.then((g) => { if (g.url) URL.revokeObjectURL(g.url); });
  HIST.imgs.clear();
}
function histImgGet(ref) {
  const key = histImgKey(ref);
  if (!HIST.imgs.has(key)) {
    const id = HIST.id;
    HIST.imgs.set(key, SOURCE.historyImage(id, ref).then((got) => (got.ok ? { url: URL.createObjectURL(got.blob) }
      : { error: got.status === 413 ? '大きすぎて表示しない' : got.status === 415 ? '表示できない形式' : `画像を読めない（${got.status || got.error}）` })));
  }
  return HIST.imgs.get(key);
}
const histSeen = typeof IntersectionObserver === 'function' ? new IntersectionObserver((entries) => {
  for (const e of entries) if (e.isIntersecting) { histSeen.unobserve(e.target); histThumbLoad(e.target); }
}, { rootMargin: '200px' }) : null;
function histThumbLoad(btn) {
  if (btn._loading) return;
  btn._loading = true;
  histImgGet(btn._ref).then((g) => {
    const img = btn.querySelector('img');
    if (g.url) {
      img.addEventListener('load', () => { const pane = histPane(); if (HIST.atEnd && pane && pane.contains(btn)) histToEnd(pane); }, { once: true });
      img.src = g.url; btn.classList.remove('h-thumb-wait');
    }
    else { btn.classList.add('h-thumb-bad'); btn.querySelector('.h-thumb-note').textContent = g.error; }
  });
}
function histThumb(ref) {
  const b = hNode('button', 'h-thumb h-thumb-wait');
  b.type = 'button';
  b._ref = ref;
  b.dataset.hImg = `${ref.off}:${ref.n}`;
  b.setAttribute('aria-label', '画像を大きく表示');
  const img = hNode('img');
  img.alt = '履歴の画像';
  img.decoding = 'async';
  b.append(img, hNode('span', 'h-thumb-note', ''));
  b.addEventListener('click', () => histLightOpen(b));
  if (histSeen) histSeen.observe(b); else histThumbLoad(b);
  return b;
}
const LIGHT = { el: null, list: [], k: 0, opener: null, onKey: null };
function histLightShow() {
  const ref = LIGHT.list[LIGHT.k], img = LIGHT.el.querySelector('img'), note = LIGHT.el.querySelector('.h-light-note');
  LIGHT.el.querySelector('.h-light-count').textContent = `${LIGHT.k + 1} / ${LIGHT.list.length}`;
  LIGHT.el.querySelectorAll('[data-h-light-step]').forEach((b) => { b.disabled = LIGHT.list.length < 2; });
  img.removeAttribute('src'); note.textContent = '読み込み中…';
  const want = LIGHT.k;
  histImgGet(ref).then((g) => {
    if (!LIGHT.el || LIGHT.k !== want) return;
    if (g.url) { img.src = g.url; note.textContent = ''; } else note.textContent = g.error;
  });
}
function histLightOpen(btn) {
  histLightClose(false);
  const all = HIST.node ? [...HIST.node.querySelectorAll('.h-thumb')] : [btn];
  LIGHT.list = all.map((b) => b._ref);
  LIGHT.k = Math.max(0, all.indexOf(btn));
  LIGHT.opener = btn.dataset.hImg;
  const el = hNode('div', 'h-light');
  const box = hNode('div', 'h-light-box');
  box.setAttribute('role', 'dialog'); box.setAttribute('aria-modal', 'true'); box.setAttribute('aria-labelledby', 'h-light-title'); box.tabIndex = -1;
  const head = hNode('div', 'h-light-head');
  const title = hNode('h3', '', '履歴の画像'); title.id = 'h-light-title';
  const prev = hNode('button', 'wb-btn', '‹ 前'); prev.type = 'button'; prev.dataset.hLightStep = '-1'; prev.setAttribute('aria-label', '前の画像（←）');
  const next = hNode('button', 'wb-btn', '次 ›'); next.type = 'button'; next.dataset.hLightStep = '1'; next.setAttribute('aria-label', '次の画像（→）');
  const close = hNode('button', 'wb-btn', '閉じる'); close.type = 'button'; close.dataset.hLightClose = '';
  head.append(title, hNode('span', 'h-light-count', ''), prev, next, close);
  const img = hNode('img'); img.alt = '履歴の画像（拡大）';
  box.append(head, img, hNode('p', 'h-light-note', ''));
  el.appendChild(box);
  document.body.appendChild(el);
  LIGHT.el = el;
  const step = (d) => { LIGHT.k = (LIGHT.k + d + LIGHT.list.length) % LIGHT.list.length; histLightShow(); };
  el.addEventListener('click', (e) => {
    if (e.target === el || e.target.closest('[data-h-light-close]')) { histLightClose(true); return; }
    const s = e.target.closest('[data-h-light-step]');
    if (s) step(Number(s.dataset.hLightStep));
  });
  LIGHT.onKey = (e) => {   // first (capture): these keys belong to the dialog, not to the card or the board under it
    if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); histLightClose(true); return; }
    if ((e.key === 'ArrowLeft' || e.key === 'ArrowRight') && !e.altKey && !e.ctrlKey && !e.metaKey) { e.preventDefault(); e.stopPropagation(); if (LIGHT.list.length > 1) step(e.key === 'ArrowRight' ? 1 : -1); return; }
    if (e.key !== 'Tab') return;
    const list = [...box.querySelectorAll('button:not(:disabled)')], first = list[0], last = list[list.length - 1];
    if (!box.contains(document.activeElement)) { e.preventDefault(); first.focus(); }
    else if (e.shiftKey && (document.activeElement === first || document.activeElement === box)) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  };
  document.addEventListener('keydown', LIGHT.onKey, true);
  histLightShow();
  close.focus();
}
function histLightClose(back) {
  if (!LIGHT.el) return;
  LIGHT.el.remove(); LIGHT.el = null;
  document.removeEventListener('keydown', LIGHT.onKey, true);
  if (!back) return;
  // the thumbnail that opened it (the list may have been rebuilt meanwhile: the same picture's new button)
  const again = HIST.node && [...HIST.node.querySelectorAll('.h-thumb')].find((b) => b.dataset.hImg === LIGHT.opener);
  if (again) again.focus({ preventScroll: true });
}

/* ---------- the wide history (2.3.4, requester 10-19: "チャットが狭いから見づらい 左にロボット一人分くらいの余裕を残して残りを
   チャットの表示にしてほしい"; "チャット広げた時はカメラの位置移動もしてね 選んでるボットが左の余白の部分に来るように") ----------
   広げる on the card's head (both tabs since 2.3.7, requester 10-20: "今の様子タブでも広げられるようにして、応答の履歴と共有で単純に
   タブ切り替えても広さが保持されればいい" — one state, HIST.wide with its kept histWidePref, for 今の様子 and 応答の履歴): the card covers everything right of histWideMargin(), the side
   panel too, and the camera flies (focusPose, 50-panel.js) so the robot stands in the middle of that margin; ← → keep
   it there for the next robot. 元の幅に戻す / Esc: the card's width and the view before. 900 px or narrower: the whole
   screen. The choice is kept in localStorage (readPref / writePref: a blocked storage only forgets it). */
const HIST_WIDE_PREF = 'hist-wide';
let histWidePref = readPref(HIST_WIDE_PREF, 'off') === 'on';   // read once: a blocked storage still keeps it for this page
function histWideMargin() {
  if (!HIST.wide) return 0;
  const w = window.innerWidth;
  return w <= 900 ? 0 : Math.round(Math.min(440, Math.max(320, w * 0.28)));
}
function histWideFly() {
  if (!has3D || !zoom.zoomed || !rbState.id || !robots.some((x) => x.def.id === rbState.id)) return;
  const pose = robotPose(rbState.id);
  flyTo(pose.p, pose.t, viewTarget, reduceMotion ? 0 : 0.6, null);
}
function histSetWide(on, remember = true) {
  on = !!on && !!rbState.id;
  if (remember) { histWidePref = on; writePref(HIST_WIDE_PREF, on ? 'on' : 'off'); }
  if (HIST.wide === on) { histWidePaint(); return; }
  HIST.wide = on;
  histWidePaint();
  histWideFly();
  const pane = histPane();
  if (pane && HIST.tab === 'history' && HIST.atEnd) histToEnd(pane);   // the newest stays in view across the change of width
}
function histWidePaint() {
  const m = histWideMargin();
  rbEl.classList.toggle('rb-wide', HIST.wide);
  rbEl.classList.toggle('rb-wide-full', HIST.wide && !m);
  rbEl.style.setProperty('--wide-left', `${m}px`);
  const b = rbEl.querySelector('[data-rb-wide]');
  if (b) {
    b.hidden = false;
    b.setAttribute('aria-pressed', String(HIST.wide));
    b.textContent = HIST.wide ? '元の幅に戻す' : '広げる';
    b.title = HIST.wide ? '元の幅に戻す（Esc）' : 'カードを画面いっぱいに広げる（今の様子・応答の履歴で同じ）';
  }
}
/* After every histSync: the card decides whether it is wide (the kept choice, the same for both tabs). */
function histWideSync(id) {
  const want = !!id && histWidePref;
  if (want !== HIST.wide) histSetWide(want, false);
  else histWidePaint();
}
rbEl.addEventListener('click', (e) => { if (e.target.closest('[data-rb-wide]')) histSetWide(!HIST.wide); });
window.addEventListener('resize', () => { if (HIST.wide) { histWidePaint(); histWideFly(); } });


/* A linked name: switch the card to that robot. Inside a summary: the fold does not toggle. */
document.addEventListener('click', (e) => {
  const b = e.target instanceof Element ? e.target.closest('[data-rb-hist] [data-h-go]') : null;
  if (!b) return;
  e.preventDefault();
  e.stopPropagation();
  goRobot(b.dataset.hGo);
});
