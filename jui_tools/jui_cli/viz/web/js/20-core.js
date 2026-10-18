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
  if (k === 0 || k === 6 || !s.implPhase) return { kind: 'written', f: 1, text: '記入済み' };
  const c = s.implN[k];
  return { kind: c >= n ? 'done' : 'impl', f: n ? c / n : 1, text: c >= n ? '実装済み' : `実装 ${c}/${n}` };
}
const KCOLS = [['todo', '未着手'], ['wait', '待ち'], ['doing', '作業中'], ['done', '完了']];
/* Where a card came from (requester, 10-18): a turn — a prompt the session received, done at Stop — or the task tools
   (TodoWrite, the task hooks, ~/.claude/tasks/). A turn reads 指示 n where a task reads #n. */
const isTurn = (x) => !!x && x.source === 'turn';
const taskRef = (x) => (isTurn(x) ? `指示 ${x.turn}` : `#${x.id}`);
const waitLabel = (x) => (isTurn(x) ? '許可待ち' : x.blockedBy ? `#${x.blockedBy} 待ち` : '待ち');
const permSummary = (p) => p.input.command || p.input.file_path || '';
const ruleCovers = (p, abs) => alwaysRules.has(p.rule) && alwaysRules.get(p.rule) < abs;
