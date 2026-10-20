/* The view's words (viz/i18n.py). The server writes the merged table into index.html — English, the configured
   language over it, the person's own words over that — and tl() reads it. A value is words with {name} slots, or
   {one, other, …} for words that change with a count (params.n picks the form, Intl.PluralRules). A key the table
   does not have comes back as itself: the gate (tests/test_viz_i18n.py) keeps such keys out of the source. */
const I18N = (() => {
  try {
    const data = JSON.parse(document.getElementById('jui-viz-strings').textContent);
    if (data && typeof data.strings === 'object') return data;
  } catch (err) { /* a page without the server's words (debug.html): English keys as they are */ }
  return { language: 'en', locale: 'en-US', strings: {} };
})();
const LOCALE = I18N.locale || 'en-US';
const PLURAL = new Intl.PluralRules(LOCALE);
function tlWords(key, p) {
  const v = I18N.strings[key];
  if (v === undefined) return key;
  return typeof v === 'object' ? v[PLURAL.select(Number(p.n))] ?? v.other ?? key : v;
}
function tl(key, params) {
  const p = params || {};
  return tlWords(key, p).replace(/\{(\w+)\}/g, (m, name) => (name in p ? String(p[name]) : m));
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
    if (slot && slot[1] in p) return tlEsc(p[slot[1]]);
    return tlEsc(part).replace(/&#96;/g, '\x60');
  }).join('').replace(TL_CODE, '<code>$1</code>');
}
/* Times and counts in the language's own form */
const fmtTime = (d, opts) => new Date(d).toLocaleTimeString(LOCALE, opts);
const fmtNum = (n, opts) => Number(n).toLocaleString(LOCALE, opts);
