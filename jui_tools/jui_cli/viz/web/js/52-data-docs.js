/* ---------- the data server's sheet (requester, 10-19; 2.3.5): a JsonUI room's API and DB specifications ----------
   Opened by pressing the rack (40-scene.js, kind 'data'). Read from the server then (SOURCE.dataDocs: POST
   /api/data-docs, the room's id only), never kept: closing drops it, opening again reads it again (a changed file
   shows). Two tabs, each only when the room has that kind: API 仕様書 — per document its endpoints (method, path,
   summary), a row opening its parameters, request body and responses; DB 仕様書 — per database its ER diagram
   (document_tools' Mermaid text, drawn strict like the data flow) and its tables, column by column as the generated
   schema page shows them. Every text is the specification's own, escaped here. */
const dsEl = $('ds'), dsBody = $('ds-body'), dsTabs = $('ds-tabs');
const ds = { open: false, project: null, tab: 'api', doc: null, error: '', loading: false, ep: null, seq: 0, opener: null };
async function openDataDocs(project, opener) {
  if (wb.open) closeWhiteboard();
  if (tb.open) closeTaskBoard();
  if (rbState.id) closeRobot(true);
  if (pr.open) closePrices();   // 54-bills.js
  Object.assign(ds, { open: true, project, doc: null, error: '', loading: true, ep: null, opener: opener || null });
  setText($('ds-room'), PROJECT[project] ? PROJECT[project].name : '');
  showOverlay(dsEl);
  liveSoloSync();   // the room's 'back to the floor' box hides under the sheet
  renderDataDocs();
  $('ds-close').focus({ preventScroll: true });
  const seq = ++ds.seq;
  const got = typeof SOURCE.dataDocs === 'function' ? await SOURCE.dataDocs(project) : { ok: false, error: 'ライブ表示だけで見られます' };
  if (seq !== ds.seq || !ds.open) return;
  ds.loading = false;
  if (!got.ok) ds.error = got.error || '読めなかった';
  else { ds.doc = got.doc; ds.tab = got.doc.api.length ? 'api' : 'db'; }
  renderDataDocs();
}
function closeDataDocs() {
  if (!ds.open) return;
  ds.open = false; ds.doc = null; ds.seq += 1;
  hideOverlay(dsEl);
  liveSoloSync();
  if (ds.opener && ds.opener.focus) ds.opener.focus({ preventScroll: true });
}
$('ds-close').addEventListener('click', closeDataDocs);
dsTabs.addEventListener('click', (e) => {
  const b = e.target.closest('[data-ds-tab]');
  if (!b || !ds.doc) return;
  ds.tab = b.dataset.dsTab; ds.ep = null;
  renderDataDocs();
});
dsBody.addEventListener('click', (e) => {
  const b = e.target.closest('[data-ep]');
  if (!b) return;
  ds.ep = ds.ep === b.dataset.ep ? null : b.dataset.ep;
  renderDataDocs();
});
const DS_METHODS = new Set(['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS']);
// A schema as text, a $ref to the document's own schemas followed one level (the name, then what it holds).
function dsSchemaText(schema, schemas) {
  if (!schema || typeof schema !== 'object') return '';
  const ref = typeof schema.$ref === 'string' ? schema.$ref : schema.items && typeof schema.items.$ref === 'string' ? schema.items.$ref : '';
  const name = ref.split('/').pop();
  const target = ref && schemas && typeof schemas === 'object' ? schemas[name] : null;
  const head = ref ? `${schema.items ? `${name}[]` : name}\n` : '';
  return head + JSON.stringify(target || schema, null, 2);
}
function dsContentHTML(content, schemas) {
  if (!content || typeof content !== 'object') return '';
  const partsHTML = Object.entries(content).slice(0, 8).map(([type, c]) => `<p class="ds-ct">${esc(type)}</p><pre class="ds-json">${esc(dsSchemaText(c && c.schema, schemas))}</pre>`);
  return partsHTML.join('');
}
function dsParamType(p) { return p.schema && typeof p.schema === 'object' ? String(p.schema.type || (p.schema.$ref || '').split('/').pop() || '') : ''; }
function dsEndpointHTML(e, schemas) {
  const params = (Array.isArray(e.parameters) ? e.parameters : []).filter((p) => p && typeof p === 'object');
  const paramRowsHTML = params.map((p) => `<tr><td><code>${esc(p.name || '')}</code></td><td>${esc(p.in || '')}</td><td>${p.required ? '必須' : ''}</td><td><code>${esc(dsParamType(p))}</code></td><td>${esc(p.description || '')}</td></tr>`).join('');
  const paramsHTML = params.length ? `<table class="ds-table"><thead><tr><th>名前</th><th>場所</th><th>必須</th><th>型</th><th>説明</th></tr></thead><tbody>${paramRowsHTML}</tbody></table>` : '<p class="ds-none">パラメータなし</p>';
  const rb = e.requestBody && typeof e.requestBody === 'object' ? e.requestBody : null;
  const rbDescHTML = rb && rb.description ? `<p>${esc(rb.description)}</p>` : '';
  const reqHTML = rb ? rbDescHTML + dsContentHTML(rb.content, schemas) : '<p class="ds-none">リクエストの本文なし</p>';
  const responses = Object.entries(e.responses && typeof e.responses === 'object' ? e.responses : {}).slice(0, 20);
  const resRowsHTML = responses.map(([code, r]) => `<div class="ds-res"><p><b class="ds-code">${esc(code)}</b> ${esc((r && r.description) || '')}</p>${dsContentHTML(r && r.content, schemas)}</div>`).join('');
  const resHTML = resRowsHTML || '<p class="ds-none">レスポンスの記述なし</p>';
  const descHTML = e.description ? `<p class="ds-desc">${esc(e.description)}</p>` : '';
  return `<div class="ds-detail">${descHTML}<h5>パラメータ</h5>${paramsHTML}<h5>リクエスト</h5>${reqHTML}<h5>レスポンス</h5>${resHTML}</div>`;
}
function dsEpHTML(e, i, k, schemas) {
  const key = `${i}:${k}`, open = ds.ep === key, m = DS_METHODS.has(e.method) ? e.method : 'GET';
  const detailHTML = open ? dsEndpointHTML(e, schemas) : '';
  return `<li><button type="button" class="ds-ep" data-ep="${esc(key)}" data-fk="ds-ep-${esc(key)}" aria-expanded="${open ? 'true' : 'false'}"><span class="http http-${esc(m)}">${esc(e.method)}</span><code>${esc(e.path)}</code><span class="desc">${esc(e.summary || e.operationId || '')}</span></button>${detailHTML}</li>`;
}
function dsApiHTML(doc) {
  const docsHTML = doc.api.map((d, i) => {
    const epsHTML = d.endpoints.map((e, k) => dsEpHTML(e, i, k, d.schemas)).join('');
    const verHTML = d.version ? `<span class="chip">v${esc(d.version)}</span>` : '';
    const descHTML = d.description ? `<p class="ds-desc">${esc(d.description)}</p>` : '';
    return `<section class="ds-doc"><header><h3>${esc(d.title)}</h3>${verHTML}<code>${esc(d.file)}</code></header>${descHTML}<ul class="ds-eps">${epsHTML}</ul></section>`;
  });
  return docsHTML.join('');
}
function dsTableHTML(t) {
  const descHTML = t.description ? `<p class="ds-desc">${esc(t.description)}</p>` : '';
  if (Array.isArray(t.enum)) {
    const valsHTML = t.enum.map((v) => `<code>${esc(v)}</code>`).join(' ');
    return `<div class="ds-tbl"><h4>${esc(t.name)} <span class="chip">enum</span></h4>${descHTML}<p>${valsHTML}</p></div>`;
  }
  const rowsHTML = t.columns.map((c) => {
    const keysHTML = c.keys.map((x) => `<span class="ds-key">${esc(x)}</span>`).join(' ') || '-';
    const consHTML = c.constraints.map((x) => esc(x)).join('<br>') || '-';
    const notesHTML = c.notes.map((x) => esc(x)).join('<br>') || '-';
    return `<tr><td><code>${esc(c.name)}</code></td><td><code>${esc(c.type)}</code></td><td>${esc(c.description)}</td><td><code>${esc(c.default)}</code></td><td>${keysHTML}</td><td>${consHTML}</td><td>${notesHTML}</td></tr>`;
  }).join('');
  return `<div class="ds-tbl"><h4>${esc(t.name)}</h4><code class="ds-file">${esc(t.file || '')}</code>${descHTML}<table class="ds-table"><thead><tr><th>列</th><th>型</th><th>説明</th><th>既定</th><th>キー</th><th>制約</th><th>メモ</th></tr></thead><tbody>${rowsHTML}</tbody></table></div>`;
}
function dsDbHTML(doc) {
  const dbsHTML = doc.db.map((d, k) => {
    const erdHTML = d.erd ? `<div class="flow-mmd ds-erd" data-erd="${k}" role="img" aria-label="${esc(d.name)} の ER 図"></div>` : '';
    const tablesHTML = d.tables.map((t) => dsTableHTML(t)).join('');
    return `<section class="ds-doc"><header><h3>${esc(d.name)}</h3><span class="chip">${Number(d.tables.length)} 件</span></header>${erdHTML}${tablesHTML}</section>`;
  });
  return dbsHTML.join('');
}
function renderDataDocs() {
  if (!ds.open) return;
  const doc = ds.doc;
  const tabs = doc ? [['api', 'API 仕様書', doc.api.length], ['db', 'DB 仕様書', doc.db.length]].filter((t) => t[2] > 0) : [];
  const tabsHTML = tabs.map(([k, label, n]) => `<button type="button" role="tab" class="ds-tab" data-ds-tab="${esc(k)}" data-fk="ds-tab-${esc(k)}" aria-selected="${ds.tab === k ? 'true' : 'false'}">${esc(label)}<b>${Number(n)}</b></button>`).join('');
  setHTML(dsTabs, tabsHTML);
  const bodyHTML = ds.loading ? '<p class="ds-none">読み込み中…</p>'
    : ds.error ? `<p class="ds-none">${esc(ds.error)}</p>`
    : !tabs.length ? '<p class="ds-none">この部屋の docs/api・docs/db に仕様書が見つかりません</p>'
    : ds.tab === 'db' ? dsDbHTML(doc) : dsApiHTML(doc);
  const skippedHTML = doc && doc.skipped ? `<p class="ds-none">大きさの上限で ${Number(doc.skipped)} 件を読んでいません</p>` : '';
  const sheetHTML = `${bodyHTML}${skippedHTML}`;
  setHTML(dsBody, sheetHTML);
  if (doc && ds.tab === 'db') dsBody.querySelectorAll('[data-erd]').forEach((el) => { const d = doc.db[Number(el.dataset.erd)]; if (d && d.erd) drawMermaid(el, d.erd); });
}
