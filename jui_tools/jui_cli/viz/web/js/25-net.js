/* ---------- live: the WebSocket to `jui viz serve` (plan 04 §5, plan 07 §5) ----------
   hello → auth (the token from <meta name="jui-viz-token">) → snapshot → slices / events / notice / ack.
   - rev only grows. A slices message carries every slice changed since the server's last push whole, so a rev
     that grows by more than one is not a gap: a rev at or below ours is dropped, a higher one is applied.
     A new snapshot (after connecting again, or on snapshot.get) replaces everything.
   - Closed: try again after 1, 2, 4, 8 s, then every 10 s. The server closes a bad or late auth with 4401; it
     also changes its token when it restarts, so on 4401 (or when a socket never got as far as a snapshot) the
     page fetches / again and reads the new token from its meta — without reloading the page.
   - presence every 5 s and whenever the tab is shown or hidden (plan 04 §5; used from P6). */
const NET = {
  ws: null, state: 'connecting', rev: -1, token: '', reqSeq: 0, waits: new Map(), retry: 0, timer: 0,
  gotSnapshot: false, lastError: '', handlers: null,
};
function readTokenFrom(html) {
  const m = /<meta name="jui-viz-token" content="([^"]*)">/.exec(html);
  return m ? m[1] : '';
}
NET.token = (document.querySelector('meta[name="jui-viz-token"]') || {}).content || '';
async function refetchToken() {
  try {
    const res = await fetch('/', { cache: 'no-store', credentials: 'same-origin' });
    if (res.ok) { const t = readTokenFrom(await res.text()); if (t) NET.token = t; }
  } catch (err) { /* the server is not back yet: the next attempt asks again */ }
}
function netSend(msg) {
  if (!NET.ws || NET.ws.readyState !== WebSocket.OPEN) return false;
  NET.ws.send(JSON.stringify(msg));
  return true;
}
/* A request that gets an ack: resolves with { ok, error }; a closed socket answers { ok: false, error: 'offline' }. */
function netRequest(type, body = {}) {
  const reqId = `r${++NET.reqSeq}`;
  return new Promise((resolve) => {
    if (!netSend({ type, reqId, ...body })) { resolve({ ok: false, error: 'offline' }); return; }
    const timer = setTimeout(() => { NET.waits.delete(reqId); resolve({ ok: false, error: 'timeout' }); }, 15000);
    NET.waits.set(reqId, (ack) => { clearTimeout(timer); resolve(ack); });
  });
}
function netSetState(state) {
  if (NET.state === state) return;
  NET.state = state;
  if (NET.handlers) NET.handlers.state(state);
}
function netConnect() {
  clearTimeout(NET.timer);
  netSetState(NET.retry ? 'reconnecting' : 'connecting');
  NET.gotSnapshot = false;
  let ws;
  try {
    ws = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws`);
  } catch (err) { netScheduleRetry(false); return; }
  NET.ws = ws;
  ws.addEventListener('open', () => { ws.send(JSON.stringify({ type: 'auth', token: NET.token })); });
  ws.addEventListener('message', (ev) => {
    let msg;
    try { msg = JSON.parse(ev.data); } catch (err) { return; }
    if (!msg || typeof msg !== 'object') return;
    const H = NET.handlers;
    switch (msg.type) {
      case 'hello': break;
      case 'snapshot':
        NET.rev = Number(msg.rev) || 0; NET.gotSnapshot = true; NET.retry = 0;
        netSetState('connected');
        if (H) H.snapshot(msg.slices || {});
        break;
      case 'slices': {
        const rev = Number(msg.rev);
        if (!(rev > NET.rev)) break;           // old or repeated: dropped (plan 04 §5)
        NET.rev = rev;
        if (H) H.slices(msg.changed || {});
        break;
      }
      case 'events': if (H) H.events(Array.isArray(msg.items) ? msg.items : [], !!msg.older); break;
      case 'notice': if (H) H.notice(msg.level === 'warn' ? 'warn' : 'info', String(msg.text || '')); break;
      case 'ack': { const w = NET.waits.get(msg.reqId); if (w) { NET.waits.delete(msg.reqId); w({ ok: !!msg.ok, error: msg.error }); } break; }
      default: break;
    }
  });
  ws.addEventListener('close', (ev) => {
    if (NET.ws !== ws) return;
    NET.ws = null;
    for (const w of NET.waits.values()) w({ ok: false, error: 'offline' });
    NET.waits.clear();
    netScheduleRetry(ev.code === 4401 || !NET.gotSnapshot);
  });
}
function netScheduleRetry(newToken) {
  netSetState('reconnecting');
  const wait = Math.min(10, 2 ** NET.retry) * 1000;   // 1, 2, 4, 8, then 10 s
  NET.retry += 1;
  NET.timer = setTimeout(async () => { if (newToken) await refetchToken(); netConnect(); }, wait);
}
function netPresence() { netSend({ type: 'presence', visible: document.visibilityState === 'visible' }); }
document.addEventListener('visibilitychange', netPresence);
setInterval(netPresence, 5000);
