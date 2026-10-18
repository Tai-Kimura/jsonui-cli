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
  atEnd: true, top: 0, newer: false, marker: null, compose: null, sent: null };

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
function histFolded(cls, title, body, open) {
  const d = hNode('details', cls);
  if (open) d.open = true;
  const s = hNode('summary');
  for (const part of title) s.appendChild(part);
  d.appendChild(s);
  for (const b of body) if (b) d.appendChild(b);
  return d;
}
function histItem(item) {
  const at = hNode('time', 'h-at', HIST_TIME(item.at));
  if (item.kind === 'user') {
    const n = hNode('div', 'h-item h-user');
    const head = hNode('p', 'h-who', '依頼者'); head.appendChild(at); n.appendChild(head);
    n.appendChild(hNode('p', 'h-plain', item.text));
    const cut = histCutNote(item); if (cut) n.appendChild(cut);
    return n;
  }
  if (item.kind === 'assistant') {
    const n = hNode('div', 'h-item h-asst');
    n.appendChild(histMarkdown(item.text));
    const cut = histCutNote(item); if (cut) n.appendChild(cut);
    return n;
  }
  if (item.kind === 'peer') {
    return histFolded('h-item h-peer', [hNode('b', '', `${item.from} から`), hNode('span', 'h-head', String(item.text).split('\n').find((l) => l.trim()) || ''), at],
      [hNode('p', 'h-plain', item.text), histCutNote(item)], false);
  }
  if (item.kind === 'harness') {
    return histFolded('h-item h-harness', [hNode('b', '', item.label), hNode('span', 'h-head', 'ハーネスが入れた文'), at],
      [hNode('p', 'h-plain', item.text), histCutNote(item)], false);
  }
  if (item.kind === 'tool') {
    const first = String(item.in || '').split('\n')[0];
    const title = [hNode('b', 'h-tname', item.name), hNode('span', 'h-head', item.description || first)];
    if (item.error) title.push(hNode('span', 'h-err', 'エラー'));
    if (item.out === undefined) title.push(hNode('span', 'h-run', '結果待ち'));
    const io = hNode('div', 'h-io');
    io.appendChild(hNode('span', 'h-io-k', 'IN'));
    io.appendChild(hNode('pre', 'h-code', `${item.in || ''}${item.inCut ? '\n…' : ''}`));
    if (item.out !== undefined) {
      io.appendChild(hNode('span', 'h-io-k', 'OUT'));
      io.appendChild(hNode('pre', `h-code${item.error ? ' h-code-err' : ''}`, `${item.out}${item.outCut ? '\n…' : ''}`));
    }
    return histFolded('h-item h-tool', title, [io], false);
  }
  if (item.kind === 'thought') return hNode('p', 'h-item h-mark', '考えた');
  if (item.kind === 'image') return hNode('p', 'h-item h-mark', '画像 1 枚');
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
  if (id !== HIST.id) { HIST.id = id; HIST.data = null; HIST.node = null; HIST.sig = ''; HIST.error = ''; HIST.atEnd = true; HIST.newer = false; histStop(); }
  const tabs = rbEl.querySelectorAll('[data-rb-tab]');
  tabs.forEach((b) => b.setAttribute('aria-selected', String(b.dataset.rbTab === HIST.tab)));
  const body = rbEl.querySelector('.rb-body:not([data-rb-hist])'), pane = histPane();
  if (body) body.hidden = HIST.tab !== 'now';
  if (pane) pane.hidden = HIST.tab !== 'history';
  composePlace(pane, id);
  if (!id || HIST.tab !== 'history') { histStop(); return; }
  histShow();
  if (!HIST.timer) { histFetch(); HIST.timer = setInterval(() => { if (document.visibilityState === 'visible') histFetch(); }, HIST_POLL_MS); }
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
  return { why: '', name };
}
function composeBuild() {
  const box = hNode('div', 'h-compose');
  box.dataset.hCompose = '';
  const why = hNode('p', 'h-compose-why'); why.dataset.hWhy = '';
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
  box.append(why, area, row, confirm);
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
  return { box: b, why: q('h-why'), area: q('h-text'), state: q('h-state'), send: q('h-send'), confirm: q('h-confirm'), to: q('h-to'), preview: q('h-preview'), go: q('h-go') };
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
  rbEl._lostFk = undefined;
  const again = lost !== undefined && !box.hidden ? box.querySelector('[data-fk="' + CSS.escape(lost) + '"]') : null;
  if (again) again.focus({ preventScroll: true });
  composePaint();
}
function composePaint() {
  if (!HIST.compose) return;
  const E = composeEls(), id = HIST.compose._for, t = composeTarget(id);
  const asking = !E.confirm.hidden;
  E.why.textContent = t.why;
  E.why.hidden = !t.why;
  E.area.disabled = !!t.why;
  E.area.readOnly = asking;
  const text = E.area.value, bytes = text.trim() ? composeBytes(id, text) : 0;
  E.send.disabled = !!t.why || !text.trim() || bytes > PROMPT_MAX_BYTES || asking;
  const sent = HIST.sent && HIST.sent.id === id ? HIST.sent : null;
  E.state.textContent = bytes > PROMPT_MAX_BYTES ? `長すぎる（${bytes.toLocaleString('ja-JP')} / ${PROMPT_MAX_BYTES.toLocaleString('ja-JP')} バイト）`
    : sent && sent.error ? `送れなかった（${sent.error}）`
    : sent ? `送信済み ${HIST_TIME(sent.at)}（履歴に出るまで待っている）` : '';
  E.state.classList.toggle('h-compose-err', bytes > PROMPT_MAX_BYTES || !!(sent && sent.error));
  if (asking && t.why) composeClose(false);   // the session lost its relay while the confirmation was open
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
/* The prompt sent shows in the history (as words of the requester, or folded as text the harness put in): 送信済み ends. */
function composeArrived(items) {
  const sent = HIST.sent;
  if (!sent || sent.error || sent.id !== HIST.id || !Array.isArray(items)) return;
  const want = composeNorm(sent.text).slice(0, 120);
  const fresh = (x) => !(Number(x.at) < sent.at - 60000);   // an older item with the same words is not this one
  if (items.some((x) => ['user', 'harness', 'peer'].includes(x.kind) && fresh(x) && composeNorm(x.text).includes(want))) { HIST.sent = null; composePaint(); }
}
