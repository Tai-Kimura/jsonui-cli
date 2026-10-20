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
function tl(key, params) {
  let v = I18N.strings[key];
  if (v === undefined) return key;
  const p = params || {};
  if (typeof v === 'object') v = v[PLURAL.select(Number(p.n))] ?? v.other ?? key;
  return v.replace(/\{(\w+)\}/g, (m, name) => (name in p ? String(p[name]) : m));
}
/* Times and counts in the language's own form */
const fmtTime = (d, opts) => new Date(d).toLocaleTimeString(LOCALE, opts);
const fmtNum = (n, opts) => Number(n).toLocaleString(LOCALE, opts);
