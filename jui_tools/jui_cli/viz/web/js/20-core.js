/* ---------- shared by the demo and the live view (from the prototype's main-1-data.js) ---------- */
const sceneEl = document.getElementById('scene');
const canvas = document.getElementById('scene-canvas');
const tagsEl = document.getElementById('tags');
const readToken = (name, fallback) => getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
const clamp01 = (v) => Math.max(0, Math.min(1, v));
const frac = (t, a, b) => clamp01((t - a) / (b - a));
const pct = (v) => Math.round(v * 100);
const esc = (s) => String(s).replace(/[&<>"]/g, (ch) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[ch]));
/* An amount in dollars, one rule wherever the page shows one (10-23): to the cent, under $1 too ($0.79, not $0.7852);
   under a cent "< $0.01" (never a $0.00 that is not 0); 0 is $0.00. signed: + on a rise (a difference); a fall always
   has its −, the under-a-cent one too (−(< $0.01)). */
function usdText(v, signed) {
  const a = Math.abs(v), sign = v < 0 ? '−' : signed && v > 0 ? '+' : '';
  if (a > 0 && a < 0.01) return sign ? sign + '(< $0.01)' : '< $0.01';
  return sign + new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(a);
}
const ROLE_INK = { debug: '#2a2000' };   // dark ink where white would not read on the pill (debug's yellow)
/* A role's pill: its background (ROLES[role].pill, else its colour) and its text (ROLE_INK, else white). One source for
   the HTML pills (pill()), the canvas ones (drawRolePill, the boards), the talk's marks and the phones' headers.
   pillBg sits next to ROLES (10-robot-core.js), which the phones' drawers there read. */
const pillInk = (role) => ROLE_INK[role] || '#ffffff';
/* A session's name (/rename, `claude -n`; 10-19): the server's title, one line, at most NAME_MAX characters. Panels and
   cards show all of it next to the two-letter mark; the tag over the robot shows it alone, cut at its end with "…". */
const NAME_MAX = 80;
const sessionName = (t) => (typeof t === 'string' ? t.replace(/\s+/g, ' ').trim().slice(0, NAME_MAX) : '');
const NAMES = { rev: 0 };   // bumped when a robot's name changes: the panels' keys carry it
/* Which CLI runs a robot (codex_app_server.py; requester 10-26: 「UIでclaudeかcodexかわかるようにしたい」): a robot's
   pill is ringed in its CLI's colour (--cli-claude / --cli-codex, app.css), and so are its tag in the 3D, its card's
   number and its talk mark. A label that is no robot's (a session id head, a test's) gets no ring. */
const CLI_NAME = { claude: 'Claude', codex: 'Codex' };
const cliOf = (label) => (DEF[label] && DEF[label].cli === 'codex' ? 'codex' : 'claude');
const pillCli = (label) => (DEF[label] ? ` cli-${cliOf(label)}` : '');
const pill = (label, role) => `<span class="pill${esc(pillCli(label))}" style="--c:${ROLES[role].pill || ROLES[role].color};--t:${ROLE_INK[role] || '#ffffff'}">${esc(label)}</span>`;   // = pillBg / pillInk (the escape gate reads the tables)
/* The time the view shows (the sky, the 8-hour tiredness): the machine's clock, unless a test or the demo sets one. */
const VIZ_CLOCK = { at: null };
const vizNow = () => (VIZ_CLOCK.at !== null ? VIZ_CLOCK.at : Date.now());
/* Six rooms to a floor (the live office's floors and the building's bays, in both views). */
const ROOM_MAX = 6;
/* Rooms that exist only in the building view (the demo's other teams): id -> name. Empty in the live view. */
const TOWER_NAMES = {};
/* Eight hours into its session a main robot gets tired (requester, 10-18); never without the session's own start. */
const TIRED_MS = 8 * 3600 * 1000;
const isTired = (since, now) => Number.isFinite(since) && since > 0 && now - since >= TIRED_MS;
const isDark = () => { const th = document.documentElement.dataset.theme; return th === 'dark' || (th !== 'light' && window.matchMedia('(prefers-color-scheme: dark)').matches); };
const readPref = (key, fallback) => { try { return localStorage.getItem(`agent-view:${key}`) || fallback; } catch (err) { return fallback; } };
const writePref = (key, value) => { try { localStorage.setItem(`agent-view:${key}`, value); } catch (err) { /* storage blocked: the choice lasts until reload */ } };
/* Mermaid (2.3.5): vendored (vendor/VENDOR.md), read only when a diagram is first drawn, never at page load (3.6 MB).
   export-demo leaves it out: the demo's hand-written sheets draw no diagram. securityLevel 'strict': the
   text is a spec's, so labels are sanitized and no click / script in a diagram runs. htmlLabels off: a label is SVG
   text, never HTML (with HTML labels, strict still lets an <img src> through and the page fetched it — measured
   10-19). The theme follows the page's. */
const MERMAID = { src: 'vendor/mermaid-11.17.2/mermaid.min.js', loading: null, theme: '', n: 0, drawn: new Map() };
function loadMermaid() {
  if (!MERMAID.loading) {
    MERMAID.loading = new Promise((resolve, reject) => {
      const el = document.createElement('script');
      el.src = MERMAID.src;
      el.onload = () => (window.mermaid ? resolve(window.mermaid) : reject(new Error('mermaid did not load')));
      el.onerror = () => { MERMAID.loading = null; reject(new Error('mermaid did not load')); };
      document.head.appendChild(el);
    });
  }
  return MERMAID.loading;
}
/* What a diagram may not set for itself (the independent review, 10-19): Mermaid reads an init / config directive (%%{…}%%) and a
   front-matter config (--- config: … ---) from the text and lets them change everything but its six `secure` keys —
   htmlLabels back on (an <img> in a label, fetched), themeCSS with url() (fetched). The text is the spec's: both are
   taken out before it is drawn, with Mermaid's own patterns (11.17.2), and anything left of a directive is broken
   up; the keys below are made secure as well, in case one gets through. */
const MERMAID_FRONT = /^([^\S\n\r]*)-{3}\s*[\n\r](.*?)[\n\r]\1-{3}\s*[\n\r]+/s;
const MERMAID_DIRECTIVE = /%{2}{\s*(?:(\w+)\s*:|(\w+))\s*(?:(\w+)|((?:(?!}%{2}).|\r?\n)*))?\s*(?:}%{2})?/gi;
const MERMAID_SECURE = ['secure', 'securityLevel', 'startOnLoad', 'maxTextSize', 'suppressErrorRendering', 'maxEdges', 'htmlLabels', 'flowchart', 'er',
  'theme', 'themeCSS', 'themeVariables', 'darkMode', 'fontFamily', 'altFontFamily', 'look', 'layout', 'markdownAutoWrap', 'dompurifyConfig', 'deterministicIds'];
function mermaidSafeText(text) {
  // until nothing more comes off: a directive taken out can leave a front matter at the start, and the other way
  // round (the independent review 2, 10-19: "%%{x}%%---\nconfig: …" passed one round of each)
  let t = String(text), prev = null;
  for (let k = 0; k < 50 && t !== prev; k++) { prev = t; t = t.replace(MERMAID_FRONT, '').replace(MERMAID_DIRECTIVE, ''); }
  if (t !== prev) return '';                                  // still changing after 50 rounds: no diagram
  if (/^[^\S\n\r]*-{3}\s*[\n\r]/.test(t)) return '';   // an unclosed front matter: no diagram
  return mermaidNoUrl(t.split('%%{').join('%% {'));   // never a directive; no url() out of the diagram
}
/* A url() that is not a reference inside the diagram (#…) becomes one to nothing, and @import goes: in the text before
   it is drawn — Mermaid puts the SVG in the page to measure it, and a style or classDef of a class or state diagram
   (fill:url(/x)) was fetched then (the independent review 2) — and in the SVG it gave back. Every kind of diagram goes through. */
function mermaidNoUrl(t) {
  return String(t).replace(/url\(\s*(?!['"]?\s*#)/gi, 'url(#blocked-').replace(/@import/gi, '@blocked');
}
function mermaidSafeSvg(svg) { return mermaidNoUrl(svg); }
async function renderMermaid(el, text) { return mermaidDraw(el, text, true); }
/* cleanText false only for the arm that checks the `secure` lock on its own (the test hook, never the page). */
async function mermaidDraw(el, text, cleanText) {
  const mm = await loadMermaid();
  const theme = isDark() ? 'dark' : 'default';
  if (MERMAID.theme !== theme) {
    // every key of Mermaid's own config is secure (no diagram changes any: class.htmlLabels got through a list of names)
    const secure = [...new Set([...MERMAID_SECURE, ...Object.keys(mm.mermaidAPI.getConfig())])];
    mm.initialize({ startOnLoad: false, securityLevel: 'strict', theme, fontFamily: 'var(--font-body)', htmlLabels: false, flowchart: { htmlLabels: false },
      class: { htmlLabels: false }, er: { useMaxWidth: false }, secure });
    MERMAID.theme = theme;
  }
  MERMAID.n += 1;
  const svg = mermaidSafeSvg((await mm.render(`mmd-${MERMAID.n}`, cleanText ? mermaidSafeText(text) : String(text))).svg);
  el.innerHTML = svg;   // Mermaid's own SVG, its labels sanitized (securityLevel 'strict')
  el.dataset.theme = theme;
  if (MERMAID.drawn.size >= 40) MERMAID.drawn.clear();
  MERMAID.drawn.set(`${theme}\n${text}`, svg);
  return el.querySelector('svg');
}
/* A diagram in a box the panels rebuild: the same text in the same theme is drawn once and put back as it was. */
function drawMermaid(el, text) {
  const theme = isDark() ? 'dark' : 'default', key = `${theme}\n${text}`;
  if (el.dataset.drawn === key) return Promise.resolve(el.querySelector('svg'));
  el.dataset.drawn = key;
  const svg = MERMAID.drawn.get(key);
  if (svg) { el.innerHTML = svg; el.dataset.theme = theme; return Promise.resolve(el.querySelector('svg')); }   // drawn before (strict)
  return renderMermaid(el, text).catch(() => { delete el.dataset.drawn; el.classList.add('mmd-failed'); return null; });
}
const ROLE_JA = { main: tl('core.role.main'), define: tl('core.role.define'), ground: tl('core.role.ground'), implement: tl('core.role.implement'), navigation: tl('core.role.navigation'), test: tl('core.role.test'), debug: tl('core.role.debug'), other: tl('core.role.other') };
const SECTIONS = [tl('core.sec.metadata'), tl('core.sec.structure'), tl('core.sec.state'), tl('core.sec.data'), tl('core.sec.actions'), tl('core.sec.transitions'), tl('core.sec.branches')];
const sumImpl = (arr) => arr.slice(1, 6).reduce((a, b) => a + b, 0);
/* The spec lists' order (ticket 2026-10-23-viz-spec-list-not-recent-first): the spec that moved on last first
   (advancedAt, the server's: its write, its Layout's write, its newest test result), then the order SPECS has (room,
   then file). On [spec, index] pairs: the panel, the board and its side list sort with this one, inside their groups. */
function specNewer(a, b) { return (b[0].advancedAt || 0) - (a[0].advancedAt || 0) || a[1] - b[1]; }
/* When a spec last moved on, beside its share wherever the share is shown (ticket 2026-10-23-viz-spec-no-last-updated-time):
   the same advancedAt specNewer sorts by, so the order and the times agree, in the reader's clock — 12:34 today,
   昨日 12:34, else 10/21 12:34. The title has the whole time and what moved it (the spec, its Layout, a test result).
   null when the server sent none (the demo). */
function specWhen(s, now = new Date()) {
  if (!(s.advancedAt > 0)) return null;
  const p2 = (n) => String(n).padStart(2, '0');
  const d = new Date(s.advancedAt), time = `${p2(d.getHours())}:${p2(d.getMinutes())}`;
  const day = (x) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime(), days = Math.round((day(now) - day(d)) / 86400000);
  const text = days === 0 ? tl('spec.when.today', { time }) : days === 1 ? tl('spec.when.yesterday', { time })
    : tl('spec.when.older', { date: `${d.getMonth() + 1}/${d.getDate()}`, time });
  const full = `${d.getFullYear()}/${p2(d.getMonth() + 1)}/${p2(d.getDate())} ${time}:${p2(d.getSeconds())}`;
  const what = s.advancedBy === 'layout' ? tl('spec.when.by.layout') : s.advancedBy === 'test' ? tl('spec.when.by.test') : tl('spec.when.by.spec');
  return { text, title: tl('spec.when.title', { full, what }) };
}
/* A spec's share (s.status.text) with that time beside it: { text, title } for every place the share is shown. */
function specStatus(s, prefix = '') {
  const w = specWhen(s), text = `${prefix}${s.status.text}`;
  return w ? { text: tl('spec.when.beside', { status: text, when: w.text }), title: w.title } : { text, title: '' };
}
function paintStatus(el, st) { setText(el, st.text); if (el.title !== st.title) el.title = st.title; }
const BUCKETS = [['live', tl('core.bucket.live')], ['partial', tl('core.bucket.partial')], ['todo', tl('core.bucket.todo')], ['done', tl('core.bucket.done')]];
const bucketCounts = (specs) => Object.fromEntries(BUCKETS.map(([b]) => [b, specs.filter((s) => s.bucket === b).length]));
const activeSec = (s) => (s.writingIdx >= 0 ? s.writingIdx : s.implIdx >= 0 ? s.implIdx : s.testIdx);
/* One section of one spec: what its bar and its chip show. */
function secState(s, k) {
  const w = s.written[k], n = s.totals[k];
  if (w <= 0) return { kind: 'empty', f: 0, text: tl('core.sec.empty') };
  if (w < 1) return { kind: 'writing', f: w, text: `${s.by ? tl('core.sec.writing') : tl('core.sec.filling')} ${pct(w)}%` };
  if (k === 6 && s.implPhase) { const c = s.implN[6], n = s.testsNeeded || s.totals[6]; return { kind: c >= n ? 'tested' : 'test', f: n ? c / n : 1, text: tl('core.sec.tests', { c, n }) }; }
  if (k === 0 || k === 6 || !s.implPhase || (s.unmeasured && s.unmeasured[k])) return { kind: 'written', f: 1, text: tl('core.sec.written') };
  if (k === 1 && s.measure && !s.measure.components) {
    return s.measure.layout ? { kind: 'done', f: 1, text: tl('core.sec.layout.done') } : { kind: 'impl', f: 0, text: s.measure.layout === false ? tl('core.sec.layout.missing') : tl('core.sec.layout.unnamed') };
  }
  const c = s.implN[k];
  return { kind: c >= n ? 'done' : 'impl', f: n ? c / n : 1, text: c >= n ? tl('core.sec.implemented') : tl('core.sec.impl', { c, n }) };
}
const KCOLS = [['todo', tl('core.col.todo')], ['wait', tl('core.wait')], ['doing', tl('core.col.doing')], ['done', tl('core.col.done')]];
/* Where a card came from (requester, 10-18): a turn — a prompt the session received, done at Stop — or the task tools
   (TodoWrite, the task hooks, ~/.claude/tasks/). A turn reads 指示 n where a task reads #n. */
const isTurn = (x) => !!x && x.source === 'turn';
const taskRef = (x) => (isTurn(x) ? tl('core.task.turn', { n: x.turn }) : `#${x.id}`);
const waitLabel = (x) => (isTurn(x) ? (x.waitingFor === 'question' ? tl('status.asking') : tl('status.waiting')) : x.blockedBy ? tl('core.wait.on', { id: x.blockedBy }) : tl('core.wait'));
const permSummary = (p) => p.input.command || p.input.file_path || '';
const ruleCovers = (p, abs) => alwaysRules.has(p.rule) && alwaysRules.get(p.rule) < abs;
