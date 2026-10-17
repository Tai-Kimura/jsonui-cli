// The P1–P2 check page: connection state, the server slice, the last 100 events.
// Every string goes in through textContent.
const conn = document.getElementById('conn');
const revEl = document.getElementById('rev');
const serverEl = document.getElementById('server');
const list = document.getElementById('events');
const KEEP = 100;

function setConn(text, ok) {
  conn.textContent = text;
  conn.className = ok ? 'ok' : 'ng';
}

async function freshToken() {
  // The token changes when the server restarts; read it again from the page.
  const res = await fetch('/', { cache: 'no-store' });
  const html = await res.text();
  const doc = new DOMParser().parseFromString(html, 'text/html');
  return doc.querySelector('meta[name="jui-viz-token"]')?.content || '';
}

const COLUMNS = {
  projects: ['name', 'displayRoot', 'jsonui', 'order'],
  sessions: ['label', 'status', 'waitingFor', 'cwd', 'title', 'lastPrompt'],
  agents: ['label', 'kind', 'role', 'agentType', 'state', 'act'],
};

function renderTable(name, rows) {
  const table = document.getElementById(name);
  if (!table || !Array.isArray(rows)) return;
  const cols = COLUMNS[name];
  table.replaceChildren();
  const head = table.insertRow();
  for (const c of cols) {
    const th = document.createElement('th');
    th.textContent = c;
    head.appendChild(th);
  }
  for (const row of rows) {
    const tr = table.insertRow();
    for (const c of cols) {
      const v = row[c];
      tr.insertCell().textContent = v === undefined || v === null ? '' : String(v);
    }
  }
}

function renderSlices(slices) {
  for (const name of Object.keys(COLUMNS)) {
    if (name in slices) renderTable(name, slices[name]);
  }
}

function addEvents(items) {
  for (const e of items) {
    const li = document.createElement('li');
    li.textContent = `${new Date(e.at).toLocaleTimeString()} ${e.kind || '?'} ${e.text || ''}`;
    list.prepend(li);
  }
  while (list.children.length > KEEP) list.lastElementChild.remove();
}

function connect(token, retry) {
  const ws = new WebSocket(`ws://${location.host}/ws`);
  ws.onopen = () => ws.send(JSON.stringify({ type: 'auth', token }));
  ws.onmessage = (ev) => {
    let m;
    try { m = JSON.parse(ev.data); } catch { return; }
    if (m.type === 'snapshot') {
      setConn('接続中', true);
      revEl.textContent = `rev ${m.rev}`;
      serverEl.textContent = JSON.stringify(m.slices.server, null, 2);
      renderSlices(m.slices);
    } else if (m.type === 'slices') {
      revEl.textContent = `rev ${m.rev}`;
      if (m.changed.server) serverEl.textContent = JSON.stringify(m.changed.server, null, 2);
      renderSlices(m.changed);
    } else if (m.type === 'events') {
      addEvents(m.items || []);
    }
  };
  ws.onclose = async (ev) => {
    setConn(ev.code === 4401 ? '認証に失敗（再取得します）' : '切断（再接続します）', false);
    setTimeout(async () => {
      let next = token;
      try { next = await freshToken(); } catch { /* server down: retry later */ }
      connect(next, Math.min((retry || 1000) * 2, 10000));
    }, retry || 1000);
  };
}

connect(document.querySelector('meta[name="jui-viz-token"]').content, 1000);
