/* The view's words (viz/i18n.py). The server writes the merged table into index.html — English, the configured
   language over it, the person's own words over that — and tl() reads it. A value is words with {name} slots, or
   {one, other, …} for words that change with a count (params.n picks the form, Intl.PluralRules). A key the table
   does not have comes back as itself: the gate (tests/test_viz_i18n.py) keeps such keys out of the source. */
const I18N = (() => {
  try {
    const data = JSON.parse(document.getElementById('jui-viz-strings').textContent);
    if (data && typeof data.strings === 'object') return { ...data, served: true };
  } catch (err) { /* a page without the server's words (debug.html): English keys as they are */ }
  return { language: 'en', words: 'en', locale: 'en-US', strings: {} };
})();
const LOCALE = I18N.locale || 'en-US';
const PLURAL = new Intl.PluralRules(LOCALE);
/* A key the table lacks, or a slot a call leaves unfilled, would read on the page as the key or as {name}, silently:
   each is said once on the console as a warning (ticket 2026-10-21-viz-english-screen-checks). The browser tests fail
   on any console warning, in Japanese and in English. Only with the server's table: debug.html has none. */
const TL_SAID = new Set();
function tlSay(what, key) {
  if (!I18N.served || TL_SAID.has(`${what} ${key}`)) return;
  TL_SAID.add(`${what} ${key}`);
  console.warn(`[viz i18n] ${what}: ${key}`);
}
function tlWords(key, p) {
  const v = I18N.strings[key];
  if (v === undefined) { tlSay('no words for the key', key); return key; }
  if (typeof v !== 'object') return v;
  const form = v[PLURAL.select(Number(p.n))] ?? v.other;
  if (form === undefined) { tlSay('no plural form for the key', key); return key; }
  return form;
}
function tlSlot(key, p, name) {
  if (name in p) return true;
  tlSay(`slot {${name}} not filled`, key);
  return false;
}
function tl(key, params) {
  const p = params || {};
  return tlWords(key, p).replace(/\{(\w+)\}/g, (m, name) => (tlSlot(key, p, name) ? String(p[name]) : m));
}
/* tl() as HTML, for words that hold markup: the words and every slot escaped, then `…` in the words drawn as
   <code>…</code> — the only markup a table's words can make (a slot's backtick is escaped first, so it makes none). */
const TL_ESC = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;', '\x60': '&#96;' };   // \x60: the backtick
const TL_CODE = new RegExp('\\x60([^\\x60]*)\\x60', 'g');
const tlEsc = (s) => String(s).replace(/[&<>"'\x60]/g, (c) => TL_ESC[c]);
function tlHTML(key, params) {
  const p = params || {};
  return tlWords(key, p).split(/(\{\w+\})/).map((part) => {
    const slot = /^\{(\w+)\}$/.exec(part);
    if (slot && tlSlot(key, p, slot[1])) return tlEsc(p[slot[1]]);
    return tlEsc(part).replace(/&#96;/g, '\x60');
  }).join('').replace(TL_CODE, '<code>$1</code>');
}
/* app.css's words: `content: var(--tl-name, 'the words as written')`. Each key css.name of the table is set on
   :root as --tl-name, a CSS string (its backslashes and quotes escaped, a line break as \A); a key the table lacks
   keeps the words as written. The gate holds the words as written to the Japanese table, letter for letter. */
const TL_CSS_ESC = new RegExp('[\\\\"]', 'g');
const tlCss = (v) => '"' + String(v).replace(TL_CSS_ESC, (c) => '\\' + c).replace(/\n/g, '\\A ') + '"';
if (document.documentElement) {
  for (const [key, v] of Object.entries(I18N.strings)) {
    if (key.startsWith('css.') && typeof v === 'string') document.documentElement.style.setProperty('--tl-' + key.slice(4).replace(/\./g, '-'), tlCss(v));
  }
}
/* Times and counts in the language's own form */
const fmtTime = (d, opts) => new Date(d).toLocaleTimeString(LOCALE, opts);
const fmtNum = (n, opts) => Number(n).toLocaleString(LOCALE, opts);
