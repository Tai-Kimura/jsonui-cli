/* ---------- shared by the demo and the live view (from the prototype's main-1-data.js) ---------- */
const sceneEl = document.getElementById('scene');
const canvas = document.getElementById('scene-canvas');
const tagsEl = document.getElementById('tags');
const readToken = (name, fallback) => getComputedStyle(document.documentElement).getPropertyValue(name).trim() || fallback;
const clamp01 = (v) => Math.max(0, Math.min(1, v));
const frac = (t, a, b) => clamp01((t - a) / (b - a));
const pct = (v) => Math.round(v * 100);
const esc = (s) => String(s).replace(/[&<>"]/g, (ch) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[ch]));
const ROLE_INK = { debug: '#2a2000' };
/* A session's name (/rename, `claude -n`; 10-19): the server's title, one line, at most NAME_MAX characters. Panels and
   cards show all of it next to the two-letter mark; the tag over the robot shows it alone, cut at its end with "…". */
const NAME_MAX = 80;
const sessionName = (t) => (typeof t === 'string' ? t.replace(/\s+/g, ' ').trim().slice(0, NAME_MAX) : '');
const NAMES = { rev: 0 };   // bumped when a robot's name changes: the panels' keys carry it
const pill = (label, role) => `<span class="pill" style="--c:${ROLES[role].color};--t:${ROLE_INK[role] || '#ffffff'}">${esc(label)}</span>`;
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
/* What a diagram may not set for itself (dd's review, 10-19): Mermaid reads an init / config directive (%%{…}%%) and a
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
  // round (dd's review 2, 10-19: "%%{x}%%---\nconfig: …" passed one round of each)
  let t = String(text), prev = null;
  for (let k = 0; k < 50 && t !== prev; k++) { prev = t; t = t.replace(MERMAID_FRONT, '').replace(MERMAID_DIRECTIVE, ''); }
  if (t !== prev) return '';                                  // still changing after 50 rounds: no diagram
  if (/^[^\S\n\r]*-{3}\s*[\n\r]/.test(t)) return '';   // an unclosed front matter: no diagram
  return mermaidNoUrl(t.split('%%{').join('%% {'));   // never a directive; no url() out of the diagram
}
/* A url() that is not a reference inside the diagram (#…) becomes one to nothing, and @import goes: in the text before
   it is drawn — Mermaid puts the SVG in the page to measure it, and a style or classDef of a class or state diagram
   (fill:url(/x)) was fetched then (dd's review 2) — and in the SVG it gave back. Every kind of diagram goes through. */
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
const ROLE_JA = { main: 'メインセッション', define: 'spec を書く担当', ground: '初期設定の担当', implement: '実装の担当', navigation: '画面遷移の担当', test: 'テストの担当', debug: '調査の担当', other: 'その他' };
const SECTIONS = ['概要', '構造', '状態', 'データ', '操作', '遷移', '分岐'];
const sumImpl = (arr) => arr.slice(1, 6).reduce((a, b) => a + b, 0);
const BUCKETS = [['live', '作業中'], ['partial', '途中'], ['todo', '未着手'], ['done', '完了']];
const bucketCounts = (specs) => Object.fromEntries(BUCKETS.map(([b]) => [b, specs.filter((s) => s.bucket === b).length]));
const activeSec = (s) => (s.writingIdx >= 0 ? s.writingIdx : s.implIdx >= 0 ? s.implIdx : s.testIdx);
/* One section of one spec: what its bar and its chip show. */
function secState(s, k) {
  const w = s.written[k], n = s.totals[k];
  if (w <= 0) return { kind: 'empty', f: 0, text: '未記入' };
  if (w < 1) return { kind: 'writing', f: w, text: `${s.by ? '書き込み中' : '記入'} ${pct(w)}%` };
  if (k === 6 && s.implPhase) { const c = s.implN[6]; return { kind: c >= n ? 'tested' : 'test', f: n ? c / n : 1, text: `テスト ${c}/${n}` }; }
  if (k === 0 || k === 6 || !s.implPhase || (s.unmeasured && s.unmeasured[k])) return { kind: 'written', f: 1, text: '記入済み' };
  if (k === 1 && s.measure && !s.measure.components) {
    return s.measure.layout ? { kind: 'done', f: 1, text: '実装済み（layout あり）' } : { kind: 'impl', f: 0, text: s.measure.layout === false ? 'layout がまだ無い' : 'layout の指定なし' };
  }
  const c = s.implN[k];
  return { kind: c >= n ? 'done' : 'impl', f: n ? c / n : 1, text: c >= n ? '実装済み' : `実装 ${c}/${n}` };
}
const KCOLS = [['todo', '未着手'], ['wait', '待ち'], ['doing', '作業中'], ['done', '完了']];
/* Where a card came from (requester, 10-18): a turn — a prompt the session received, done at Stop — or the task tools
   (TodoWrite, the task hooks, ~/.claude/tasks/). A turn reads 指示 n where a task reads #n. */
const isTurn = (x) => !!x && x.source === 'turn';
const taskRef = (x) => (isTurn(x) ? `指示 ${x.turn}` : `#${x.id}`);
const waitLabel = (x) => (isTurn(x) ? (x.waitingFor === 'question' ? '質問に回答待ち' : '許可待ち') : x.blockedBy ? `#${x.blockedBy} 待ち` : '待ち');
const permSummary = (p) => p.input.command || p.input.file_path || '';
const ruleCovers = (p, abs) => alwaysRules.has(p.rule) && alwaysRules.get(p.rule) < abs;
