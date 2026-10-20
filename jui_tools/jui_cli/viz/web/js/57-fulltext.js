/* ---------- the whole text of a line cut to one (2.3.6, requester 10-19: "これテストのパスが見えないからホバーで全部表示されるようにしてほしい") ----------
   One component for every one-line ellipsis of the robot card and the side panel (the family: FULLTEXT_LINES; the table is
   in the ticket 2026-10-19-jui-viz-test-run-path-on-hover). A line that is cut (scrollWidth > clientWidth) shows a floating
   tag with its whole text, wrapped, when the pointer is over it or the keyboard focus reaches it; the tag's text can be
   selected and copied; it sits at the left of the 3D (fulltextPlace, 10-20) and goes when the pointer or the focus
   leaves (the pointer: after the time to cross to the tag), or on Esc. A line that is not cut never gets it. Not the native title: slow, and the OS cuts a long one.
   Focus: a cut line that is plain text becomes focusable (tabindex 0) only while it is cut; a line inside a button or a
   summary (already focusable) shows through that control's focus. The control or the line points at the tag
   (aria-describedby) while the tag shows. */
const FULLTEXT_HOSTS = ['#rb', '#side', '#ticker-strip'];
/* The log strip (2.3.6) sits at the bottom of the screen, below the scene: its tag sits on the scene's bottom (fulltextPlace).
   Closed (2.3.4's log-strip), its lines are not drawn: never cut, never focusable. */
const FULLTEXT_LINES = [
  '.rb-run-file',                 // card · テスト実行: the test file / command (the request)
  '.rb-subs .act',                // card · サブエージェント: what each is doing
  '.h-head',                      // card · 応答の履歴: a folded item's head (in its summary)
  '.h-tool summary > b',          // card · 応答の履歴: a tool's name (in its summary)
  '#sessions .act',               // panel · セッション: a robot's act, the row's second line
  '#sessions .subs .who-btn > span:last-child',   // panel · セッション: a subagent's name (in its button)
  '.spec-row .nm',                // panel · spec の進み具合: the spec's name (in its button)
  '.pg-toggle small',             // panel · セッション: a project group's summary (in its button)
  '#ticker .what',                // the log strip: an event's text (2.3.6: a cross-session message was cut there)
  '#ticker .kind',                // the log strip: an event's kind
  '.talk-peer-name',                // card · トーク (2.3.6): the peer's name in the talk's header (in its button)
  '.talk-row-name',                  // card · トーク: a peer's name in the list of talks (in its button)
].join(', ');
const FULLTEXT = { el: null, anchor: null, owner: null, host: null, via: null, soon: 0 };
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
/* Where the tag goes (requester 10-20: 「いやホバーで出る位置をもっと左にしてよ」 — next to the card, a 2000-char command
   covered the 3D from its middle to the right, top to bottom; ticket 2026-10-20-jui-viz-fulltext-float-covers-the-scene).
   One rule for every member of the family (the card, the side panel, the log strip), never beside the line:
     * the 3D left free: the scene's box, less the robot card when it is open (a side card: what is left of it; a bottom
       sheet, narrow: what is above it);
     * the tag sits at the left of that free box, FULLTEXT_PAD in, as wide as its text needs up to
       min(FULLTEXT_MAX_W, FULLTEXT_SHARE of the free box's width) (a long text: that width, so it stays readable);
       its right edge is then left of the free box's middle (the view's centre point stays clear; with the card open the
       camera puts the selected robot there, so the tag may cover the robot's left side, never its middle) and never on
       the card (the free box ends at the card);
     * its top is level with the line, moved up or down to stay inside the free box (the log strip's line is below the
       scene: the tag sits on the scene's bottom, above the strip); taller than the free box, it scrolls inside. */
const FULLTEXT_PAD = 16, FULLTEXT_MAX_W = 420, FULLTEXT_SHARE = 0.4;
function fulltextFree() {
  const sb = sceneEl.getBoundingClientRect();
  const f = { left: Math.max(sb.left, 0), top: Math.max(sb.top, 0), right: Math.min(sb.right, window.innerWidth), bottom: Math.min(sb.bottom, window.innerHeight) };
  const card = document.getElementById('rb');
  if (card && !card.hidden) {
    const cb = card.getBoundingClientRect();
    if (cb.left > f.left + (f.right - f.left) * 0.25) f.right = Math.min(f.right, cb.left);   // a side card
    else f.bottom = Math.min(f.bottom, cb.top);                                                 // a bottom sheet
  }
  return f;
}
function fulltextPlace() {
  const { el, anchor } = FULLTEXT;
  if (!el || el.hidden || !anchor) return;
  const lb = anchor.getBoundingClientRect(), f = fulltextFree();
  const w = Math.max(0, Math.min(FULLTEXT_MAX_W, (f.right - f.left) * FULLTEXT_SHARE));
  const h = Math.max(0, f.bottom - f.top - FULLTEXT_PAD * 2);
  el.style.maxWidth = `${Math.floor(w)}px`;
  el.style.maxHeight = `${Math.floor(h)}px`;
  el.style.left = '0px'; el.style.top = '0px';
  const r = el.getBoundingClientRect();
  const x = f.left + FULLTEXT_PAD;
  const y = Math.max(f.top + FULLTEXT_PAD, Math.min(lb.top, f.bottom - FULLTEXT_PAD - r.height));
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
  if (FULLTEXT.anchor.contains(e.target) && !(to && (FULLTEXT.anchor.contains(to) || FULLTEXT.el.contains(to)))) fulltextHideSoon();
});
/* The tag is away from its line (at the 3D's left): the pointer crossing to it, to select its text, passes over the card
   and the 3D first. It goes FULLTEXT_TRAVEL_MS after the pointer left the line, unless by then the pointer is on the tag
   or back on the line. */
const FULLTEXT_TRAVEL_MS = 700;
function fulltextHideSoon() {
  const anchor = FULLTEXT.anchor;
  clearTimeout(FULLTEXT.soon);
  FULLTEXT.soon = setTimeout(() => {
    if (FULLTEXT.anchor !== anchor || FULLTEXT.via !== 'pointer') return;
    if (FULLTEXT.el.matches(':hover') || (anchor.isConnected && anchor.matches(':hover'))) return;
    fulltextHide();
  }, FULLTEXT_TRAVEL_MS);
}
/* A press anywhere but the tag and its line, while it is crossing time: the pointer is not on its way to the tag. */
document.addEventListener('pointerdown', (e) => {
  if (FULLTEXT.via !== 'pointer' || !FULLTEXT.anchor || !FULLTEXT.el) return;
  if (FULLTEXT.el.contains(e.target) || FULLTEXT.anchor.contains(e.target)) return;
  fulltextHide();
}, true);
document.addEventListener('focusin', (e) => {
  const t = e.target;
  // a box focused by the mouse (the history pane takes the focus on a click) shows nothing: only a keyboard visit
  // to a box names its first cut line (10-20: the tag of an unrelated line popped up under the pointer and took the click)
  const viaKeys = !!(t.matches && t.matches(':focus-visible'));
  const line = t.matches && t.matches(FULLTEXT_LINES) ? t : viaKeys ? [...(t.querySelectorAll ? t.querySelectorAll(FULLTEXT_LINES) : [])].find(fulltextCut) : null;
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
