/* ---------- the whole text of a line cut to one (2.3.6, requester 10-19: "これテストのパスが見えないからホバーで全部表示されるようにしてほしい") ----------
   One component for every one-line ellipsis of the robot card and the side panel (the family: FULLTEXT_LINES; the table is
   in the ticket 2026-10-19-jui-viz-test-run-path-on-hover). A line that is cut (scrollWidth > clientWidth) shows a floating
   tag with its whole text, wrapped, when the pointer is over it or the keyboard focus reaches it; the tag's text can be
   selected and copied; it stays inside the card's (or the panel's) box and goes when the pointer or the focus leaves, or
   on Esc. A line that is not cut never gets it. Not the native title: slow, and the OS cuts a long one.
   Focus: a cut line that is plain text becomes focusable (tabindex 0) only while it is cut; a line inside a button or a
   summary (already focusable) shows through that control's focus. The control or the line points at the tag
   (aria-describedby) while the tag shows. */
const FULLTEXT_HOSTS = ['#rb', '#side'];
const FULLTEXT_LINES = [
  '.rb-run-file',                 // card · テスト実行: the test file / command (the request)
  '.rb-subs .act',                // card · サブエージェント: what each is doing
  '.h-head',                      // card · 応答の履歴: a folded item's head (in its summary)
  '.h-tool summary > b',          // card · 応答の履歴: a tool's name (in its summary)
  '#sessions .act',               // panel · セッション: a robot's act, the row's second line
  '#sessions .subs .who-btn > span:last-child',   // panel · セッション: a subagent's name (in its button)
  '.spec-row .nm',                // panel · spec の進み具合: the spec's name (in its button)
  '.pg-toggle small',             // panel · セッション: a project group's summary (in its button)
].join(', ');
const FULLTEXT = { el: null, anchor: null, owner: null, host: null, via: null };
const fulltextCut = (el) => !!el && el.isConnected && el.scrollWidth > el.clientWidth + 1;
const fulltextControl = (el) => el.closest('button, summary, a[href]');   // already focusable: the line shows through it
function fulltextHost(el) { return FULLTEXT_HOSTS.map((s) => document.querySelector(s)).find((h) => h && h.contains(el)) || null; }
function fulltextEl() {
  if (FULLTEXT.el) return FULLTEXT.el;
  const el = document.createElement('div');
  el.id = 'fulltext'; el.className = 'fulltext'; el.setAttribute('role', 'tooltip'); el.hidden = true;
  el.addEventListener('pointerleave', (e) => { if (!(FULLTEXT.anchor && FULLTEXT.anchor.contains(e.relatedTarget))) fulltextHide(); });
  document.body.append(el);
  FULLTEXT.el = el;
  return el;
}
function fulltextShow(line, via) {
  const host = fulltextHost(line);
  if (!host || !fulltextCut(line)) return;
  const el = fulltextEl();
  if (FULLTEXT.anchor !== line) fulltextHide();
  el.textContent = line.textContent;
  el.hidden = false;
  const owner = fulltextControl(line) || line;
  owner.setAttribute('aria-describedby', 'fulltext');
  Object.assign(FULLTEXT, { anchor: line, owner, host, via });
  fulltextPlace();
}
/* Below the line (above when there is no room), inside the host's box; wrapped to the host's width. */
function fulltextPlace() {
  const { el, anchor, host } = FULLTEXT;
  if (!el || el.hidden || !anchor) return;
  const hb = host.getBoundingClientRect(), lb = anchor.getBoundingClientRect(), pad = 8;
  const top = Math.max(hb.top, 0), bottom = Math.min(hb.bottom, window.innerHeight);
  el.style.maxWidth = `${Math.max(120, hb.width - pad * 2)}px`;
  el.style.maxHeight = `${Math.max(60, (bottom - top) - pad * 2)}px`;
  el.style.left = '0px'; el.style.top = '0px';
  const r = el.getBoundingClientRect();
  const x = Math.min(Math.max(lb.left, hb.left + pad), hb.right - pad - r.width);
  let y = lb.bottom + 4;
  if (y + r.height > bottom - pad) y = Math.max(top + pad, lb.top - 4 - r.height);
  el.style.left = `${Math.round(x)}px`; el.style.top = `${Math.round(y)}px`;
}
function fulltextHide() {
  if (FULLTEXT.owner) FULLTEXT.owner.removeAttribute('aria-describedby');
  if (FULLTEXT.el) FULLTEXT.el.hidden = true;
  Object.assign(FULLTEXT, { anchor: null, owner: null, host: null, via: null });
}
/* Plain cut lines take the focus while they are cut, and only then (re-checked when the card or the panel changes). */
function fulltextSync() {
  for (const host of FULLTEXT_HOSTS.map((s) => document.querySelector(s)).filter(Boolean)) {
    for (const line of host.querySelectorAll(FULLTEXT_LINES)) {
      if (fulltextControl(line)) continue;
      const cut = fulltextCut(line);
      if (cut && line.getAttribute('tabindex') !== '0') line.setAttribute('tabindex', '0');
      else if (!cut && line.hasAttribute('tabindex')) line.removeAttribute('tabindex');
    }
  }
  if (FULLTEXT.anchor && !FULLTEXT.anchor.isConnected) fulltextHide();   // the card was rebuilt under it
  else fulltextPlace();
}
const fulltextLineAt = (t) => (t && t.closest ? t.closest(FULLTEXT_LINES) : null);
document.addEventListener('pointerover', (e) => {
  const line = fulltextLineAt(e.target);
  if (line && fulltextHost(line) && fulltextCut(line)) fulltextShow(line, 'pointer');
});
document.addEventListener('pointerout', (e) => {
  if (FULLTEXT.via !== 'pointer' || !FULLTEXT.anchor) return;
  const to = e.relatedTarget;
  if (FULLTEXT.anchor.contains(e.target) && !(to && (FULLTEXT.anchor.contains(to) || FULLTEXT.el.contains(to)))) fulltextHide();
});
document.addEventListener('focusin', (e) => {
  const t = e.target;
  const line = t.matches && t.matches(FULLTEXT_LINES) ? t : [...(t.querySelectorAll ? t.querySelectorAll(FULLTEXT_LINES) : [])].find(fulltextCut);
  if (line && fulltextHost(line) && fulltextCut(line)) fulltextShow(line, 'focus');
  else if (FULLTEXT.via === 'focus') fulltextHide();
});
document.addEventListener('focusout', (e) => {
  if (FULLTEXT.via === 'focus' && FULLTEXT.owner && FULLTEXT.owner.contains(e.target) && !(e.relatedTarget && FULLTEXT.owner.contains(e.relatedTarget))) fulltextHide();
});
document.addEventListener('keydown', (e) => {   // first (capture): Esc closes the tag, not the card under it
  if (e.key !== 'Escape' || !FULLTEXT.el || FULLTEXT.el.hidden) return;
  e.preventDefault(); e.stopPropagation();
  fulltextHide();
}, true);
{
  let due = false;
  const later = () => { if (due) return; due = true; requestAnimationFrame(() => { due = false; fulltextSync(); }); };
  const mo = new MutationObserver(later), ro = new ResizeObserver(later);
  for (const host of FULLTEXT_HOSTS.map((s) => document.querySelector(s)).filter(Boolean)) {
    mo.observe(host, { childList: true, subtree: true, characterData: true, attributes: true, attributeFilter: ['hidden', 'class'] });
    ro.observe(host);
  }
  document.addEventListener('scroll', () => { if (FULLTEXT.anchor) fulltextPlace(); }, true);
  window.addEventListener('resize', later);
}
