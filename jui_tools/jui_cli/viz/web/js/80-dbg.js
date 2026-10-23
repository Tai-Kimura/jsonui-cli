/* ---------- browser-test hook (appended only when the server runs with JUI_VIZ_E2E=1) ---------- */
// The e2e scripts press the 3D boards through these, as the prototype's agent-test.html did.
// Demo: setSim(seconds) jumps the script. Live: setSim(factor) sets the replay speed instead (25-net.js).
const SPIRIT_DBG = { delay: 0 };   // spiritLoadDelay's wait (ms)
window.__dbg = {
  // the server room (ticket 2026-10-20-jui-viz-server-room): the door's press, the keypad, the bubble, the view
  sr: () => {
    const k = srKeypad(SR.project, 0), V = SR.view;
    let door = null;
    const at = srDoorNow();
    if (at) { const v = new THREE.Vector3(); at.D.root.getWorldPosition(v); v.y = 1.1; v.project(camera); const r = canvas.getBoundingClientRect(); door = [Math.round(r.left + (v.x + 1) / 2 * r.width), Math.round(r.top + (1 - v.y) / 2 * r.height)]; }
    return { phase: SR.phase, project: SR.project, seq: SR.seq, keypad: k.state, stars: k.stars, built: !!at, door, place: at ? at.place : null,
      bubble: srBubbleEl.hidden ? null : { kind: srBubbleEl.dataset.kind, text: srBubbleEl.querySelector('.sr-short').textContent, full: srBubbleEl.querySelector('.sr-full').textContent },
      open: !srEl.hidden, lod: V ? V.lod : null, lines: V ? { plain: V.plainLines.visible, cross: V.crossLines.visible, sparse: !!V.sparse } : null, labels: V ? V.shownLabels || 0 : 0, cellPx: V ? +srCellPx(V).toFixed(2) : null, stats: SR.stats, shown: SR.shown || null,
      frames: V ? V.frames.slice(-90) : [], icons: V ? V.iconCount || 0 : 0, env: V ? V.env : null, log: SR.log.slice(0, 20).map((l) => l.text),
      board: srEl.hidden ? '' : $('sr-board').textContent, layers: V ? { near: V.near.visible, far: V.far.visible } : null,
      bubbleRect: srBubbleEl.hidden ? null : (({ left, top, right, bottom }) => [left, top, right, bottom].map(Math.round))(srBubbleEl.getBoundingClientRect()),
      gpu: V ? { geometries: V.renderer.info.memory.geometries, textures: V.renderer.info.memory.textures, calls: V.renderer.info.render.calls, triangles: V.renderer.info.render.triangles } : null };
  },
  srGroups: () => (SR.view ? SR.view.L.floors.filter((G) => G.g.id).map((G) => ({ id: G.g.id, nodes: srCountNodes(G), closed: !!G.closed })) : []),
  srSelectGroup: (id) => { SR.selected = null; SR.selectedGroup = id; srRenderBoard(); return !!document.querySelector('#sr-board [data-sr-act="toggle"]'); },
  srEdges: () => (SR.view ? SR.view.L.edges.map((e) => `${e.from}>${e.to}`) : []),
  mainFrames: () => renderer.info.render.frame,
  // the server room's arms (the independent verification, 10-20): what is drawn and how, without changing anything
  srTiming: () => ({ took: SR.took ?? null, waitMs: SR.waitMs ?? null, fastMs: SR.fastMs, okMs: SR.okMs }),
  srIconKeys: () => (SR.view ? { ...(SR.view.iconKeys || {}) } : {}),
  srNodeEnvs: () => (SR.view ? SR.view.L.nodes.map((n) => [n.id, Array.isArray(n.environments) ? n.environments : []]) : []),
  srAlive: () => !!SR.view,
  srProviders: () => (SR.view ? { only: [...SR.only], drawn: SR.view.L.nodes.map((n) => [n.id, n.providerResolved || n.provider || '']), groups: SR.view.L.floors.length, emptyFloors: SR.view.L.floors.filter((G) => srCountNodes(G) === 0).map((G) => G.g.id || '(none)'), cross: SR.view.L.edges.filter((e) => e.crossProvider).map((e) => [e.from, e.to]) } : null),
  srTheme: () => { const V = SR.view; if (!V) return null; const lab = document.querySelector('#sr-labels .sr-label:not([hidden])'), cs = lab ? getComputedStyle(lab) : null;
    return { dark: V.dark, bg: `#${V.scene.background.getHexString()}`, floors: [...new Set(V.floorColors)], label: cs ? [cs.color, cs.backgroundColor] : null }; },
  srLines: () => { const V = SR.view; return V ? { mode: SR.lines, plainOpacity: V.plainLines.material.opacity, crossOpacity: V.crossLines.material.opacity,
    plainVisible: V.plainLines.visible, crossVisible: V.crossLines.visible,
    far: { plainOpacity: V.farPlain.material.opacity, crossOpacity: V.farCross.material.opacity, plainVisible: V.farPlain.visible, crossVisible: V.farCross.visible,
      // how many bundles each layer draws (two points a line): a "not seen" on an empty layer would prove nothing
      plainCount: srCableCount(V.farPlain), crossCount: srCableCount(V.farCross) },
    // how wide a cable is on the page at least (px), each layer: SR_CABLE through the shader's uniform
    px: { plain: V.plainLines.material.uniforms.uPx.value, cross: V.crossLines.material.uniforms.uPx.value, focus: V.focusLines.material.uniforms.uPx.value, bundle: V.farPlain.material.uniforms.uPx.value },
    boardSelected: !!document.querySelector('#sr-board .sr-sel'), focus: V.focusCount || 0, selected: SR.selected } : null; },
  srSelect: (id) => { srSelect(id); return SR.view ? SR.view.focusCount || 0 : null; },
  // つながっている物を全部見せる: what it holds, each drawn node's colour now (faint or not), the strong cables, the camera
  srReach: () => { const V = SR.view; if (!V) return null; const c = new THREE.Color(), k = new THREE.Color(), faint = [], full = [];
    // faint: drawn in another colour than the one the shape was kept with (no colour kept: as drawn at the build)
    for (const mesh of V.nodeSets[V.detail && !V.flat ? 'detail' : 'simple'].children) if (mesh.instanceColor) mesh.userData.nodes.forEach((id, i) => {
      mesh.getColorAt(i, c); const base = mesh.userData.baseColors; (base && !k.fromArray(base, i * 3).equals(c) ? faint : full).push(id); });
    const R = SR.reach;
    const v = new THREE.Vector3(), inView = R ? [...R.ids].filter((id) => { const p = V.L.pos.get(id); if (!p) return false; v.set(p.x, p.y + 0.75, p.z).project(V.camera); return Math.abs(v.x) <= 1 && Math.abs(v.y) <= 1 && v.z < 1; }) : [];
    return { on: !!R, id: R ? R.id : null, hops: SR.reachHops, inView, edgesAll: V.L.edges.map((e) => [e.from, e.to]), drawn: V.L.nodes.map((n) => [n.id, n.label || n.id]), ids: R ? [...R.ids] : [], edges: R ? R.edges.size : 0, focus: V.focusCount || 0, faint, full,
      plainOpacity: V.plainLines.material.opacity, pressed: (document.querySelector('#sr-board [data-sr-act="reach"]') || {}).ariaPressed || null,
      cam: [...V.camera.position.toArray(), ...V.controls.target.toArray(), ...(V.flat ? [V.camera.zoom] : [])].map((x) => +x.toFixed(3)), labels: [...document.querySelectorAll('#sr-labels .sr-label:not([hidden])')].map((l) => l.textContent) }; },
  // how wide the strong cables are drawn, in drawn pixels: a frame drawn now and read back whole, the pixels near the focus
  // colour counted, over the strong cables' length on the page (device px). A 1 px line comes out near 1.
  srCableInk: () => { const V = SR.view; if (!V) return null; V.renderer.render(V.scene, V.camera);
    const gl = V.renderer.getContext(), w = gl.drawingBufferWidth, h = gl.drawingBufferHeight, px = new Uint8Array(w * h * 4);
    gl.readPixels(0, 0, w, h, gl.RGBA, gl.UNSIGNED_BYTE, px);
    const f = V.focusLines.material.uniforms.uColor.value.clone().convertLinearToSRGB(), want = [f.r * 255, f.g * 255, f.b * 255];
    let ink = 0; for (let i = 0; i < px.length; i += 4) if (Math.abs(px[i] - want[0]) + Math.abs(px[i + 1] - want[1]) + Math.abs(px[i + 2] - want[2]) < 60) ink++;
    // the length on the page of what is in view only (64 steps a cable, a step counted when both its ends are on the page)
    const a = new THREE.Vector3(), b = new THREE.Vector3(), on = (v) => v.z > -1 && v.z < 1 && Math.abs(v.x) <= 1 && Math.abs(v.y) <= 1;
    let len = 0; for (let i = 0; i < srCableCount(V.focusLines); i++) { const pts = srCablePts(V.focusLines, i);   // along its path
      for (let s = 0; s + 1 < pts.length; s++) { const P = new THREE.Vector3().fromArray(pts[s]), Q = new THREE.Vector3().fromArray(pts[s + 1]);
        for (let k = 0; k < 64; k++) {
          a.lerpVectors(P, Q, k / 64).project(V.camera); b.lerpVectors(P, Q, (k + 1) / 64).project(V.camera);
          if (on(a) && on(b)) len += Math.hypot((a.x - b.x) * w / 2, (a.y - b.y) * h / 2);
        } } }
    return { ink, len: Math.round(len), width: len ? +(ink / len).toFixed(2) : null, cables: srCableCount(V.focusLines), page: w * h,
      ends: srCableCount(V.focusLines) ? srCableGet(V.focusLines, 0) : null }; },
  // the camera put at a point looking at another (the arms: a cable with one end behind it)
  // the camera put at a point looking at another, as it is (no controls' limits), and the strong cables measured at once,
  // before the next frame's controls move it (the arms: a cable with an end behind the camera, or on it)
  // the camera put at a point looking at another, through the controls (as a person turning the view would)
  srRoutePerf: () => { const V = SR.view; return V ? { reroutes: V.reroutes || 0, ms: V.rerouteMs || 0, detail: V.detail, inView: V.inView, segs: [V.plainLines, V.crossLines].map((L) => L.geometry.getAttribute('cableStart').count / 4) } : null; },
  srCamSet: (pos, target) => { const V = SR.view; if (!V) return false; V.camera.position.fromArray(pos); V.controls.target.fromArray(target); V.controls.update(); return true; },
  srCamInk: (pos, target) => { const V = SR.view; if (!V) return null; V.camera.position.fromArray(pos); V.camera.lookAt(new THREE.Vector3().fromArray(target));
    V.camera.updateMatrixWorld(); return window.__dbg.srCableInk(); },
  // one cable layer's width as drawn: the layer alone over black, in white at full strength, its pixels over its length on
  // the page (as srCableInk), then the frame as it was
  srLayerWidth: (name) => { const V = SR.view, L = V && V[name]; if (!L) return null;
    const keep = { bg: V.scene.background, vis: new Map(), color: L.material.uniforms.uColor.value.clone(), op: L.material.uniforms.uOpacity.value };
    V.scene.traverse((o) => { if (o !== V.scene) keep.vis.set(o, o.visible); });
    V.scene.traverse((o) => { if (o.isMesh || o.isInstancedMesh || o.isSprite || o.isLine || o.isPoints) o.visible = false; });
    for (let o = L; o; o = o.parent) o.visible = true;
    V.scene.background = new THREE.Color(0, 0, 0); L.material.uniforms.uColor.value.setRGB(1, 1, 1); L.material.uniforms.uOpacity.value = 1;
    V.renderer.render(V.scene, V.camera);
    const gl = V.renderer.getContext(), w = gl.drawingBufferWidth, h = gl.drawingBufferHeight, px = new Uint8Array(w * h * 4);
    gl.readPixels(0, 0, w, h, gl.RGBA, gl.UNSIGNED_BYTE, px);
    let ink = 0; for (let i = 0; i < px.length; i += 4) ink += (px[i] + px[i + 1] + px[i + 2]) / 765;   // partial coverage counts as part
    for (const [o, v] of keep.vis) o.visible = v;
    V.scene.background = keep.bg; L.material.uniforms.uColor.value.copy(keep.color); L.material.uniforms.uOpacity.value = keep.op;
    const a = new THREE.Vector3(), b = new THREE.Vector3(), on = (v) => v.z > -1 && v.z < 1 && Math.abs(v.x) <= 1 && Math.abs(v.y) <= 1;
    let len = 0; for (let i = 0; i < srCableCount(L); i++) { const pts = srCablePts(L, i);   // along its path
      for (let s = 0; s + 1 < pts.length; s++) { const P = new THREE.Vector3().fromArray(pts[s]), Q = new THREE.Vector3().fromArray(pts[s + 1]);
        for (let k = 0; k < 32; k++) { a.lerpVectors(P, Q, k / 32).project(V.camera); b.lerpVectors(P, Q, (k + 1) / 32).project(V.camera); if (on(a) && on(b)) len += Math.hypot((a.x - b.x) * w / 2, (a.y - b.y) * h / 2); } } }
    return { ink: Math.round(ink), len: Math.round(len), width: len ? +(ink / len).toFixed(2) : null, cables: srCableCount(L), ratio: V.renderer.getPixelRatio() }; },
  // the cables over the nodes: the frame drawn with the cables and without, the pixels that differ are the cables seen;
  // the nodes (shapes, models, icons) drawn alone give where the nodes are; the count of cable pixels over a node
  // above: looked at from straight over the target (the camera put back after): a cable on a node's side then stops at
  // the node's outline, one over it or into its middle lies on it — from the usual slant a cable in front of a node's
  // side lies on its picture however well it is grounded
  srCablesOverNodes: (above) => { const V = SR.view; if (!V) return null; const gl = V.renderer.getContext(), w = gl.drawingBufferWidth, h = gl.drawingBufferHeight;
    const cam = { p: V.camera.position.clone(), q: V.camera.quaternion.clone() };
    if (above && !V.flat) { const d = V.camera.position.distanceTo(V.controls.target); V.camera.position.copy(V.controls.target).add(new THREE.Vector3(0, d, 0.0001)); V.camera.lookAt(V.controls.target); V.camera.updateMatrixWorld(); }
    const shot = () => { V.renderer.render(V.scene, V.camera); const px = new Uint8Array(w * h * 4); gl.readPixels(0, 0, w, h, gl.RGBA, gl.UNSIGNED_BYTE, px); return px; };
    const cables = [V.plainLines, V.crossLines, V.focusLines, V.focusCross], was = cables.map((c) => c.visible);
    const withC = shot(); cables.forEach((c) => { c.visible = false; }); const without = shot(); cables.forEach((c, i) => { c.visible = was[i]; });
    const isNode = (o) => (o.isInstancedMesh && (o.userData.nodes || o.userData.shape)) || (V.modelLayer && (o === V.modelLayer || V.modelLayer.children.includes(o)));
    const keep = new Map(); V.scene.traverse((o) => { if (o !== V.scene) keep.set(o, o.visible); });
    const bg = V.scene.background; V.scene.background = new THREE.Color(0, 0, 0);
    V.scene.traverse((o) => { if ((o.isMesh || o.isInstancedMesh || o.isSprite || o.isLine) && !isNode(o) && !(V.modelLayer && o.parent && V.modelLayer.children.includes(o.parent))) o.visible = false; });
    const nodes = shot();
    for (const [o, v] of keep) o.visible = v; V.scene.background = bg;
    V.camera.position.copy(cam.p); V.camera.quaternion.copy(cam.q); V.camera.updateMatrixWorld();
    let cable = 0, over = 0;
    for (let i = 0; i < withC.length; i += 4) {
      if (Math.abs(withC[i] - without[i]) + Math.abs(withC[i + 1] - without[i + 1]) + Math.abs(withC[i + 2] - without[i + 2]) < 24) continue;
      cable++; if (nodes[i] + nodes[i + 1] + nodes[i + 2] > 12) over++; }
    return { cable, over, share: cable ? +(over / cable).toFixed(3) : null, detail: V.detail, lod: V.lod }; },
  // every cable laid: its ends on its nodes' outlines (as drawn) at a height within each node; flat (two points) when
  // nothing stands on its straight line; rising when something does, and over that thing's top at its middle
  // want: the heights promised, from the arm (not read from SR_ROUTE, so a changed number is caught): side above a node's
  // foot (half its height at most), clear over the tallest thing crossed, cross the crossing cables' lift
  srCableRoutes: (want) => { const V = SR.view; if (!V) return null; if (V.flat) return window.__dbg.srCableRoutesFlat(); const grid = srFootGrid(V), feet = [...new Set(grid.feet.values())];
    const W = Object.assign({ side: 0.3, clear: 0.25, cross: 0.06 }, want || {});
    const out = { cables: 0, ends: 0, offOutline: 0, offHeight: 0, offSide: 0, flat: 0, notFlat: 0, rising: 0, notRising: 0, under: 0, lowOver: 0, worst: null, flatNodes: [] };
    const allFlat = new Map();   // a node's cables, all flat?
    const yAt = (pts, x, z) => { let best = null, bd = Infinity;   // the path's height at the point of it nearest (x, z)
      for (let k = 0; k + 1 < pts.length; k++) { const a = pts[k], b = pts[k + 1], dx = b[0] - a[0], dz = b[2] - a[2], l2 = dx * dx + dz * dz;
        const u = l2 ? Math.max(0, Math.min(1, ((x - a[0]) * dx + (z - a[2]) * dz) / l2)) : 0, px = a[0] + dx * u, pz = a[2] + dz * u, d = Math.hypot(px - x, pz - z);
        if (d < bd) { bd = d; best = a[1] + (b[1] - a[1]) * u; } } return best; };
    const segs = { plain: 0, cross: 0 };
    for (const e of V.L.edges) { const set = e.crossProvider ? 'cross' : 'plain', L = set === 'cross' ? V.crossLines : V.plainLines, j = segs[set]++;
      const pts = srCablePts(L, j), A = pts[0], Z = pts[pts.length - 1];
      if (A[0] === Z[0] && A[2] === Z[2]) continue;
      out.cables++;
      for (const [end, id, other] of [[A, e.from, Z], [Z, e.to, A]]) { const f = grid.feet.get(id); out.ends++;
        const d = Math.hypot(end[0] - f.x, end[2] - f.z), ux = (other[0] - f.x), uz = (other[2] - f.z), ul = Math.hypot(ux, uz) || 1;
        const want = srFootExit(f, ux / ul, uz / ul);
        if (Math.abs(d - want) > 0.05) { out.offOutline++; out.worst = out.worst || { id, d: +d.toFixed(3), want: +want.toFixed(3) }; }
        if (end[1] < f.y0 - 1e-3 || end[1] > f.y1 + 1e-3) out.offHeight++;
        const side = Math.min(f.y0 + W.side, (f.y0 + f.y1) / 2) + (e.crossProvider ? W.cross : 0);
        if (Math.abs(end[1] - side) > 0.02) out.offSide++; }
      const fa = grid.feet.get(e.from), fb = grid.feet.get(e.to), P = [A[0], A[2]], Q = [Z[0], Z[2]];
      // what stands on its way: a node's or a box's foot, with the clearance a cable keeps (SR_ROUTE.margin)
      const hits = feet.map((f) => (f !== fa && f !== fb ? [f, srFootSpan(f, P, Q, SR_ROUTE.margin)] : null)).filter((h) => h && h[1]);
      for (const id of [e.from, e.to]) allFlat.set(id, (allFlat.get(id) ?? true) && !hits.length);
      if (!hits.length) { if (pts.length === 2) out.flat++; else out.notFlat++; continue; }
      if (pts.length > 2) { out.rising++; if (!out.risingSample) out.risingSample = { from: e.from, to: e.to, pts }; } else out.notRising++;
      for (const [f, sp] of hits) {   // over it: the path's height where the straight line is inside the foot, at that stretch's middle
        const t = (sp[0] + sp[1]) / 2, y = yAt(pts, P[0] + (Q[0] - P[0]) * t, P[1] + (Q[1] - P[1]) * t);
        if (y === null || y < f.y1) out.under++;
        if (y === null || y < f.y1 + W.clear - 0.02) out.lowOver++; } }
    out.flatNodes = [...allFlat].filter(([, v]) => v).map(([id]) => id).sort();
    // the far view's bundles: each from the side of one top group's box to the other's, at a height within the boxes
    out.bundles = 0; out.bundlesOff = 0;
    const bs = { plain: 0, cross: 0 }, box = (G) => ({ x: G.x + G.w / 2, z: G.z + G.d / 2, hx: G.w * 0.46, hz: G.d * 0.46, round: false });
    for (const B of V.bundles || []) { const L = B.cross ? V.farCross : V.farPlain, j = bs[B.cross ? 'cross' : 'plain']++, pts = srCablePts(L, j), A = pts[0], Z = pts[pts.length - 1];
      if (A[0] === Z[0] && A[2] === Z[2]) continue;
      out.bundles++;
      for (const [end, G, other] of [[A, B.a, Z], [Z, B.b, A]]) { const f = box(G), ux = other[0] - f.x, uz = other[2] - f.z, ul = Math.hypot(ux, uz) || 1;
        if (Math.abs(Math.hypot(end[0] - f.x, end[2] - f.z) - srFootExit(f, ux / ul, uz / ul)) > 0.05 || end[1] < 0 || end[1] > G.boxH) out.bundlesOff++; } }
    out.y = [V.plainLines, V.crossLines].map((L) => (srCableCount(L) ? srCablePts(L, 0)[0][1] : null));
    return out; },
  // 2D (56-server-room.js srCablePathFlat): every cable at one height, each end on its tile's outline toward the point
  // next to it; straight when nothing is on its way, else bent with square corners and through no other tile; `blocked`:
  // a cable left straight across a tile because no route was clear
  srCableRoutesFlat: () => { const V = SR.view; if (!V || !V.flat) return null; const grid = srFootGrid(V), feet = [...new Set(grid.feet.values())];
    const out = { flatView: true, cables: 0, ends: 0, offOutline: 0, offHeight: 0, flat: 0, notFlat: 0, bent: 0, notSquare: 0, crossing: 0, blocked: 0, worst: null, flatNodes: [] };
    // on the way: within the router's clearance (srFlatClear); through: into a tile itself (no clearance)
    const allFlat = new Map(), segs = { plain: 0, cross: 0 };
    const onWay = (P, Q, skip) => feet.some((f) => !skip.includes(f) && srFootSpan(f, P, Q, SR_FLAT_ROUTE.margin));
    const through = (P, Q, skip) => feet.some((f) => !skip.includes(f) && srFootSpan(f, P, Q, 0));
    for (const e of V.L.edges) { const set = e.crossProvider ? 'cross' : 'plain', L = set === 'cross' ? V.crossLines : V.plainLines, j = segs[set]++;
      const pts = srCablePts(L, j), A = pts[0], Z = pts[pts.length - 1];
      if (A[0] === Z[0] && A[2] === Z[2]) continue;
      out.cables++;
      if (pts.some((q) => Math.abs(q[1] - A[1]) > 1e-6)) out.offHeight++;
      for (const [end, id, next] of [[A, e.from, pts[1]], [Z, e.to, pts[pts.length - 2]]]) { const f = grid.feet.get(id); out.ends++;
        const d = Math.hypot(end[0] - f.x, end[2] - f.z), ux = next[0] - f.x, uz = next[2] - f.z, ul = Math.hypot(ux, uz) || 1, want = srFootExit(f, ux / ul, uz / ul);
        if (Math.abs(d - want) > 0.05) { out.offOutline++; out.worst = out.worst || { id, d: +d.toFixed(3), want: +want.toFixed(3) }; } }
      const fa = grid.feet.get(e.from), fb = grid.feet.get(e.to), skip = [fa, fb];
      // the straight line the router tried first: between the two tiles' edges toward each other's middle
      const sd = Math.hypot(fb.x - fa.x, fb.z - fa.z) || 1, ux = (fb.x - fa.x) / sd, uz = (fb.z - fa.z) / sd, ea = srFootExit(fa, ux, uz), eb = srFootExit(fb, -ux, -uz);
      const straightHits = onWay([fa.x + ux * ea, fa.z + uz * ea], [fb.x - ux * eb, fb.z - uz * eb], skip);
      for (const id of [e.from, e.to]) allFlat.set(id, (allFlat.get(id) ?? true) && !straightHits && pts.length === 2);
      if (pts.length === 2) { if (straightHits) out.blocked++; else out.flat++; continue; }
      if (!straightHits) out.notFlat++;
      out.bent++;
      for (let k = 0; k + 1 < pts.length; k++) { const a = pts[k], b = pts[k + 1];
        if (k > 0 && k + 2 < pts.length && Math.abs(a[0] - b[0]) > 1e-6 && Math.abs(a[2] - b[2]) > 1e-6) out.notSquare++;
        if (through([a[0], a[2]], [b[0], b[2]], skip)) out.crossing++; } }
    out.flatNodes = [...allFlat].filter(([, v]) => v).map(([id]) => id).sort();
    out.bundles = 0; out.bundlesOff = 0;
    const bs = { plain: 0, cross: 0 }, box = (G) => ({ x: G.x + G.w / 2, z: G.z + G.d / 2, hx: G.w * 0.46, hz: G.d * 0.46, round: false });
    for (const B of V.bundles || []) { const L = B.cross ? V.farCross : V.farPlain, j = bs[B.cross ? 'cross' : 'plain']++, pts = srCablePts(L, j), A = pts[0], Z = pts[pts.length - 1];
      if (A[0] === Z[0] && A[2] === Z[2]) continue;
      out.bundles++;
      for (const [end, G, other] of [[A, B.a, Z], [Z, B.b, A]]) { const f = box(G), ux = other[0] - f.x, uz = other[2] - f.z, ul = Math.hypot(ux, uz) || 1;
        if (Math.abs(Math.hypot(end[0] - f.x, end[2] - f.z) - srFootExit(f, ux / ul, uz / ul)) > 0.05) out.bundlesOff++; } }
    return out; },
  srReachPress: () => { const b = document.querySelector('#sr-board [data-sr-act="reach"]'); if (b) b.click(); return !!b; },
  srReachHopsSet: (v) => { const sel = document.querySelector('#sr-board [data-sr-reach-hops]'); if (!sel) return false; sel.value = v; sel.dispatchEvent(new Event('change', { bubbles: true })); return true; },
  srEdgesOf: (id) => (SR.view ? SR.view.L.edges.filter((e) => e.from === id || e.to === id).length : null),
  // up close (the server room ticket §5): the look, how many nodes are in view, each drawn node's shape in the set shown,
  // and the tags given out; the thresholds may be set for an arm
  srDetail: (set) => { const V = SR.view; if (!V) return null; if (set) Object.assign(SR.detail, set);
    const shapesOf = (set) => { const o = {}; for (const m of V.nodeMeshes[set]) m.userData.nodes.forEach((id) => { o[id] = m.userData.shape; }); return o; };
    return { detail: V.detail, inView: V.inView ?? null, enter: SR.detail.enter, leave: SR.detail.leave, simple: shapesOf('simple'), byService: shapesOf('detail'),
      shown: { simple: V.nodeSets.simple.visible, detail: V.nodeSets.detail.visible }, picks: V.pick.filter((m) => m.userData.nodes).map((m) => m.userData.shape),
      tags: [...document.querySelectorAll('#sr-labels .sr-label:not([hidden])')].filter((s) => s.dataset.kind !== 'group').map((s) => s.textContent),
      // up close, the models standing (node → kind), what each node in view should be (srModelKind), the cap, and whether the
      // shapes by service are drawn under them
      models: V.models ? Object.fromEntries([...V.models].map(([id, g]) => [id, g.userData.kind])) : {}, modelMax: SR_MODEL.max,
      inViewIds: (V.inViewIds || []), kinds: Object.fromEntries((V.inViewIds || []).map((id) => [id, srModelKind(V.L.pos.get(id).n)])),
      detailDrawn: V.nodeMeshes.detail.map((m) => m.material.visible) }; },
  // the colours as drawn (sRGB hex): each node's instanced shape with its cloud, the legend's chips, and up close each
  // model's own colour (its tone-0 parts) — one cloud is one colour wherever it is shown
  srColors: () => { const V = SR.view; if (!V) return null; const c = new THREE.Color(), nodes = {}, models = {};
    for (const mesh of V.nodeMeshes.simple) mesh.userData.nodes.forEach((id, i) => { mesh.getColorAt(i, c); const n = V.L.pos.get(id).n; nodes[id] = [n.providerResolved || n.provider || null, `#${c.getHexString()}`]; });
    if (V.models) for (const [id, g] of V.models) { const part = g.children.find((x) => x.userData.tone === 0); models[id] = part ? `#${part.material.color.getHexString()}` : null; }
    const chips = Object.fromEntries([...document.querySelectorAll('#sr-board .sr-prov')].filter((b) => b.querySelector('.sr-chip')).map((b) => [b.dataset.srProv, getComputedStyle(b.querySelector('.sr-chip')).backgroundColor]));
    return { nodes, models, chips }; },
  srTagOf: (id) => { const n = SR.model && (SR.model.nodes || []).find((x) => x.id === id); return n ? srDetailText(n) : null; },   // a node's tag up close
  // a flow playing (59-sr-flows.js): what it is at, what it said, what it waits for
  srFlow: () => { const P = SR_FLOW.player, V = SR.view; return { starts: V && V.flowStarts ? V.flowStarts.slice() : [], speed: SR_FLOW.speed, auto: SR_FLOW.auto,
    playing: P ? P.flow.id : null, state: P ? P.state : null, pos: P ? P.pos : null, log: P ? P.log.slice() : [], arrivals: P ? P.arrivals.slice() : [],
    reached: P ? P.reached.slice() : [],
    // the lights moving in their cables (a draining tail is not one), and what they are made of: the e2e holds that no
    // ball travels (no sphere in the flow's layer) and that the light is the cable's own shader
    lights: P ? P.lights.filter((o) => o.userData.flowLight && o.userData.moving).length : 0, chosen: P ? P.chosen.slice() : [],
    spheres: V && V.flowLayer ? V.flowLayer.children.filter((o) => o.geometry && o.geometry.type === 'SphereGeometry').length : 0,
    // every light on its cable's path: the same points, a tube a segment
    lightOnPath: P && V ? P.lights.filter((o) => o.userData.flowLight).every((o) => { const want = srCablePathOf(V, o.userData.from, o.userData.to, srFlowCrossing(V, o.userData.from, o.userData.to));
      return o.userData.parts.length === want.length - 1 && o.userData.pts.length === want.length && o.userData.pts.every((q, i) => q.distanceTo(new THREE.Vector3(...want[i])) < 1e-4); }) : null,
    lightMaterials: P ? P.lights.filter((o) => o.userData.flowLight).map((o) => [o.userData.glow, o.userData.core].map((m) => m.material.type + (m.material.uniforms && m.material.uniforms.uHead ? ':uHead' : '')).join('+')) : [],
    // the smallest moving light's glow radius on the screen at its head, in pixels (null: none moving)
    lightPx: (() => { const d = P && V ? P.lights.filter((o) => o.userData.flowLight && o.userData.moving) : [];
      return d.length ? Math.min(...d.map((o) => +(o.userData.glow.scale.x * srFlowPxPerUnit(V, o.userData.head)).toFixed(2))) : null; })(),
    lightHead: (() => { const d = P ? P.lights.filter((o) => o.userData.flowLight && o.userData.moving) : [];
      return d.length ? +(d[0].userData.k || 0).toFixed(3) : null; })(),   // on its whole path (srFlowLightAt)
    hints: P && P.hints ? P.hints.userData.hints : 0, choices: [...document.querySelectorAll('#sr-choices:not([hidden]) [data-sr-choice]')].map((b) => b.dataset.srChoice),
    toasts: [...document.querySelectorAll('#sr-toasts .sr-toast')].map((t) => t.textContent), history: P ? P.history.length : 0 }; },
  srFlowSpeed: (s) => { SR_FLOW.speed = s; srFlowRenderBar(); return SR_FLOW.speed; },
  // a migration plan (59-sr-migration.js): what is drawn read from the 3D itself — each changed node's size from its
  // instance matrix (and its model's), each changed edge's length from the line's positions — and the plan's own lists
  srMig: () => {
    const P = SR_MIG.P, V = SR.view;
    const plans = srMigPlans().map((m) => ({ name: m.name, ok: m.ok, steps: m.steps.length, codes: (m.problems || []).map((p) => p.code), shorts: (m.problems || []).map((p) => p.short) }));
    if (!P || !V) return { open: false, plans };
    const m4 = new THREE.Matrix4(), pos = new THREE.Vector3(), q = new THREE.Quaternion(), sc = new THREE.Vector3(), sizes = {};
    const vers = {};   // a replaced node's two versions: the old one's size and the new one's
    for (const [id, list] of V.migNodes || []) for (const it of list) {
      it.mesh.getMatrixAt(it.i, m4); m4.decompose(pos, q, sc);
      const s = Math.round(sc.x / it.sc.x * 1000) / 1000;
      sizes[id] = Math.max(sizes[id] || 0, s); (vers[id] = vers[id] || {})[it.ver] = Math.max((vers[id] || {})[it.ver] || 0, s);
    }
    const lengths = {}, sent = {};   // sent: how many times each edge's cables were handed to the GPU (needsUpdate: version)
    for (const M of V.migEdges || []) {
      sent[M.key] = M.line.geometry.getAttribute('cableStart').version;
      lengths[M.key] = Math.round(srCableShown(M.line, M.j) * 1000) / 1000;   // how much of its path is drawn
    }
    const models = {};
    if (V.models) for (const g of V.models.values()) models[g.userData.node] = { kind: g.userData.kind, visible: g.visible };
    const drawnNodes = [...V.L.pos.values()].filter((p) => !p.hiddenIn && !srMigHides(p.n.id)).map((p) => p.n.id).sort();
    const drawnEdges = V.L.edges.filter((e) => !srMigEdgeHidden(e)).map(srMigKey).sort();
    const shapes = {};
    for (const set of ['simple', 'detail']) for (const mesh of V.nodeMeshes[set]) mesh.userData.nodes.forEach((id) => { if (srMigAt(P.entry)[id]) (shapes[id] = shapes[id] || {})[set] = mesh.userData.shape; });
    const specs = {};   // the version of each changed node the room is drawn with now: its spec's values
    for (const p of V.L.pos.values()) if (srMigAt(P.entry)[p.n.id]) specs[p.n.id] = (p.n.spec || []).map((x) => x.value).join(',');
    const nowEl = $('sr-mplayer').querySelector('[data-sr-mp-now]');
    return { open: true, plans, name: P.entry.name, k: P.k, specs, vers, builds: SR.builds || 0, idle: P.idle || 0, now: nowEl ? nowEl.textContent : null, nowClass: nowEl ? nowEl.className : '',
      fx: P.fx ? { from: P.fx.from, to: P.fx.to, delta: P.fx.delta } : null,
      tags: [...document.querySelectorAll('#sr-toasts [data-sr-mig-tag]')].map((el) => ({ node: el.dataset.srMigTag, step: Number(el.dataset.srMigStep), text: el.textContent, up: el.classList.contains('sr-up'), opacity: Number(el.style.opacity || 1), transform: el.style.transform })),
      barStep: P.anim ? P.anim.i : P.k, barDiff: (($('sr-mplayer').querySelector('[data-sr-mp-diff]') || {}).textContent || ''),
      moved: (($('sr-mplayer').querySelector('[data-sr-mp-moved]') || {}).textContent || ''), n: P.entry.steps.length, state: P.state, anim: P.anim ? { i: P.anim.i, t: P.anim.t } : null,
      log: P.log.slice(), sizes, lengths, sent, models, shapes, lights: P.lights.size, floors: (V.migFloorShown || []).slice().sort(), drawnNodes, drawnEdges,
      newNodes: P.entry.model.nodes.filter((n) => srVisible(n, V.env) && (V.fold || !n.fold)).map((n) => n.id).sort(),
      newEdges: P.entry.model.edges.filter((e) => srVisible(e, V.env)).map(srMigKey).sort(),
      newGroups: P.entry.model.groups.filter((g) => srVisible(g, V.env)).map((g) => g.id).sort(),
      cost: P.cost ? (P.cost.ok ? { old: P.cost.old.usd, new: P.cost.new.usd, diff: P.cost.diff.usd, steps: P.cost.steps.map((s) => s.usd), unpricedChanged: P.cost.unpricedChanged } : { ok: false }) : null,
      bar: ($('sr-mplayer').querySelector('[data-sr-mp-cost]') || {}).textContent || '' };
  },
  srMigStart: (name) => srMigStart(name),
  srMigUsd: (v) => srMigUsd(v),   // the migration's money format (the e2e compares the engine's numbers as shown)
  srMigSigned: (v) => srMigSigned(v),   // a difference, signed, as shown
  // each frame's camera (position and target) while on: off gives what was kept (a rebuild must not move it a frame)
  // where 全体を見る puts the camera (position and target), without moving it
  srFitCamera: () => { const V = SR.view; if (!V) return null; const p = V.camera.position.clone(), q = V.controls.target.clone(); srFit(true);
    const out = V.camera.position.toArray().concat(V.controls.target.toArray()); V.camera.position.copy(p); V.controls.target.copy(q); V.controls.update(); return out; },
  // the room built again where it stands (what a theme or an environment does, with nothing to look different)
  srRebuildHere: () => { const V = SR.view; if (!V) return null; srBuild(srCamKeep(V)); return SR.builds; },
  srPixTrail: (on) => { const got = SR.pixTrail || []; SR.pixTrail = on ? [] : null; return got; },
  srCamTrail: (on) => { const got = SR.camTrail || []; SR.camTrail = on ? [] : null; return got; },   // the cost view's own money format (the e2e compares the engine's numbers as shown)
  srMigSpeed: (s) => { SR_MIG.speed = s; srMigRenderBar(); return SR_MIG.speed; },
  // 2D: each node's tag against its own tile on the page — its bottom (px) above the tile's top edge, else listed
  srTagsOnTiles: () => { const V = SR.view; if (!V || !V.flat) return null; const cv = V.renderer.domElement.getBoundingClientRect(), on = [];
    let n = 0, first = null;
    for (const l of document.querySelectorAll('#sr-labels .sr-label:not([hidden])')) { const id = l.dataset.node; if (!id) continue;
      const p = V.L.pos.get(id), f = srNodeFoot(V, p), top = new THREE.Vector3(p.x, p.y + 0.75, f.z - f.hz).project(V.camera), r = l.getBoundingClientRect();
      const topY = cv.top + (1 - top.y) / 2 * cv.height; n++;
      if (r.bottom > topY + 1) on.push([id, Math.round(r.bottom), Math.round(topY)]);
      if (n === 1) { const c = new THREE.Vector3(p.x, p.y + 0.75, p.z).project(V.camera);
        first = { id, text: l.textContent, rect: [r.left, r.top, r.right, r.bottom].map(Math.round), center: Math.round(cv.top + (1 - c.y) / 2 * cv.height), topY: Math.round(topY), hz: f.hz, canvas: [cv.left, cv.top, cv.width, cv.height].map(Math.round), transform: l.style.transform, z: p.z }; } }
    return { tags: n, on: on.slice(0, 6), first }; },
  srLabelRects: () => [...document.querySelectorAll('#sr-labels .sr-label:not([hidden])')].map((s) => { const r = s.getBoundingClientRect(); return [r.left, r.top, r.right, r.bottom].map(Math.round); }),
  // a robot of the room up close moved onto the line from the camera to the door, at a robot's height: it then stands in
  // front of the door from this view (D2: the door must still take the press, as the bell and the rack do)
  srRobotBeforeDoor: () => {
    const at = srDoorNow();
    if (!at) return null;
    // live: a robot of that room; the demo: a seated one (the walker is placed by the script each frame)
    const R = robots.find((x) => x.robot && x.robot.root && x.robot.root.visible && (SOURCE.mode === 'live' ? x.def.room === at.room : !x.def.walk));
    if (!R) return null;
    const door = new THREE.Vector3(); at.D.root.getWorldPosition(door); door.y = 1.1;
    const cam = camera.position, t = (cam.y - 1.0) / (cam.y - door.y), p = cam.clone().lerp(door, Math.min(0.97, Math.max(0, t)));
    R.robot.root.position.set(p.x, 0, p.z);
    R.robot.root.updateMatrixWorld(true);
    // what a ray from the camera through the door's point meets first: the robot, if it stands in front
    const ray = new THREE.Raycaster(cam.clone(), door.clone().sub(cam).normalize());
    ray.camera = camera;   // a sprite (a robot's sign) is hit only with the camera given
    const first = ray.intersectObjects([...robots.map((x) => x.robot.root), at.D.root, at.D.pad].filter(Boolean), true)[0];
    return { id: R.def.id, first: first ? (robotOf(first.object) !== undefined ? `robot:${robotOf(first.object)}` : first.object.userData.serverDoor ? 'door' : 'other') : null };
  },
  // the cost simulator (L-C): the mode, the scenario, the month's shape drawn, the day's hour and rows, the 3D paused
  srCost: () => ({ mode: SRC.mode, scenario: SRC.scenario, account: !!(SRC.month && SRC.month.account && SRC.month.account.on), asked: SRC.account, error: SRC.error, paused: !!SR.paused, raf: !!(SR.view && SR.view.raf),
    month: SRC.month ? { usd: SRC.month.usd, days: SRC.month.days.length, bars: document.querySelectorAll('#sr-cost .src-day').length,
      total: ($('sr-cost').querySelector('[data-src-total]') || {}).textContent || '', overDays: document.querySelectorAll('#sr-cost .src-over').length,
      chips: [...document.querySelectorAll('#sr-cost [data-src-chip]')].map((c) => [c.dataset.srcChip, Number(c.querySelector('b').textContent)]),
      free: ($('sr-cost').querySelector('[data-src-free]') || {}).textContent || '',
      acctSwitch: !!$('sr-cost').querySelector("[data-src-act='acct-on']"), acct: ($('sr-cost').querySelector('[data-src-acct]') || {}).textContent || '',
      by: SRC.month.by, keys: SRC.month.keys.map((k) => k.key) } : null,
    day: SRC.day ? { date: SRC.date, hour: SRC.hour, playing: !!SRC.timer, rows: document.querySelectorAll('#sr-cost .src-row').length,
      clock: ($('sr-cost').querySelector('[data-src-clock]') || {}).textContent || '',
      acct: ($('sr-cost').querySelector('[data-src-dayacct]') || {}).textContent || '',
      segments: [...document.querySelectorAll('#sr-cost .src-seg')].map((s) => s.getAttribute('aria-label')),
      red: [...document.querySelectorAll('#sr-cost [data-src-over]')].map((s) => s.textContent),
      price: ($('sr-cost').querySelector('[data-src-price]') || {}).textContent || '' } : null }),
  srCostPlayMs: (ms) => { SRC.playMs = ms; return ms; },
  srFramesReset: () => { if (SR.view) SR.view.frames = []; return !!SR.view; },
  // the box (2.3.11 item 6): the nodes on the page now (client px; null behind the camera), the camera, what the last box held
  srScreen: () => { const V = SR.view; if (!V) return null; V.camera.updateMatrixWorld(); const r = V.renderer.domElement.getBoundingClientRect();
    return { rect: [r.left, r.top, r.right, r.bottom], lod: V.lod, nodes: srBoxPoints(V).map(([id, v]) => { const s = srScreenAt(V, v, r.width, r.height); return [id, s ? [r.left + s[0], r.top + s[1]] : null]; }) }; },
  srCam: () => { const V = SR.view; return V ? { target: V.controls.target.toArray().map((x) => +x.toFixed(3)), dist: +srViewDist(V).toFixed(3),
    pos: V.camera.position.toArray().map((x) => +x.toFixed(3)), flat: V.flat, zoom: +V.camera.zoom.toFixed(4), span: +srSpan(V).toFixed(3) } : null; },
  srBox: () => ({ armed: SR.box.armed, drawing: !!SR.box.drag, shown: !$('sr-box').hidden, last: SR.view ? SR.view.lastBox || null : null }),
  srZoom: (factor) => { const V = SR.view; if (!V) return null; srSetSpan(V, V.controls.target.x, V.controls.target.z, srSpan(V) * factor); V.controls.update(); return +srCellPx(V).toFixed(2); },
  srEnter: (project) => srEnter(project, null),
  srCross: () => { const V = SR.view; return V ? { drawn: srCableCount(V.crossLines), dashed: V.crossLines.material.uniforms.uDash.value > 0, plain: srCableCount(V.plainLines) } : null; },
  // the browser notifications (2.3.6): what this tab has looked at, its switches, the board and the card open now
  notifySeen: () => [...NOTIFY.seen],
  notifyBased: () => NOTIFY.based.perm && NOTIFY.based.ask,
  notifyPings: () => NOTIFY.pings,
  notifyAudio: () => (NOTIFY.audio ? NOTIFY.audio.state : null),
  notifyLastChime: () => NOTIFY.lastChime || null,
  notifyPanel: () => { notifyOpenPanel(null); return !notifyEl.hidden; },   // opened without a press (a press would wake the sound)
  notifyOn: () => ({ ...NOTIFY.on }),
  notifyVolume: () => NOTIFY.volume,
  notifySayStop: () => { clearInterval(NOTIFY.sayTimer); return true; },   // a hidden tab's throttled timers, at their worst
  notifyPeers: () => [...NOTIFY.peers.values()].map((p) => p.running),
  // a test's way to make this tab take events later than the others (which tab takes one first is not fixed)
  notifyDelay: (ms) => { const orig = notifyEvent; notifyEvent = (...a) => setTimeout(() => orig(...a), ms); return true; },
  notifyPresenceSay: () => notifyPresenceSay(),
  notifySet: (o) => { Object.assign(NOTIFY.on, o || {}); notifySavePrefs(); notifyPresenceSay(); return { ...NOTIFY.on }; },
  board: () => ({ open: !!tb.open, detail: tb.detail || null, waitView: !!tb.waitView, robot: rbState.id || null }),
  questions: () => QUESTIONS.map((q) => ({ id: q.id, status: q.status, hookWaiting: !!q.hookWaiting, waitEndReason: q.waitEndReason || null })),
  questionRelease: (id) => SOURCE.releaseQuestion(id),
  // the bill over a robot (54-bills.js): the message ids the page has taken from the bills slice (shown or not)
  billSeen: () => [...BILL.seen.keys()],
  camera, sbTile, sbPoint, SB, KB, THREE, robots,
  // Mermaid (2.3.5): draw a text into a box of its own and say what came out — whether it was read yet, the config it
  // runs with, the svg's nodes, and anything that could run (a script, an on* attribute, a javascript: link)
  mermaid: async (text) => {
    const before = !!window.mermaid;
    let box = document.getElementById('e2e-mermaid');
    if (!box) { box = document.createElement('div'); box.id = 'e2e-mermaid'; document.body.appendChild(box); }
    let svg = null, error = null;
    try { svg = await renderMermaid(box, text); } catch (err) { error = String(err && err.message || err); }
    const all = [...box.querySelectorAll('*')];
    return { loadedBefore: before, error, svg: !!svg, nodes: box.querySelectorAll('g.node').length, text: box.textContent,
      scripts: box.querySelectorAll('script').length, onAttrs: all.filter((e) => [...e.attributes].some((a) => /^on/i.test(a.name))).length,
      jsLinks: all.filter((e) => /^\s*javascript:/i.test(e.getAttribute('href') || e.getAttribute('xlink:href') || '')).length,
      foreignObjects: box.querySelectorAll('foreignObject').length, imgs: box.querySelectorAll('img, image').length,
      securityLevel: window.mermaid ? window.mermaid.mermaidAPI.getConfig().securityLevel : null, htmlLabels: window.mermaid ? window.mermaid.mermaidAPI.getConfig().htmlLabels : null, theme: box.dataset.theme || null,
      src: [...document.scripts].map((x) => x.getAttribute('src')).filter((x) => x && x.includes('mermaid')) };
  },
  // the data server (2.3.5): its rack (built, its box, where it is on the screen) and its sheet (open, tab, what shows)
  dataServer: () => {
    const S = PROPS.dataServer, b = new THREE.Box3(), r = canvas.getBoundingClientRect();
    let box = null, screen = null;
    if (S) {
      S.group.updateMatrixWorld(true); b.setFromObject(S.group);
      box = [b.min.x, b.max.x, b.min.z, b.max.z].map((v) => +v.toFixed(3));
      const c = b.getCenter(new THREE.Vector3()).project(camera);
      screen = [r.left + (c.x + 1) / 2 * r.width, r.top + (1 - c.y) / 2 * r.height];
    }
    return { room: PROPS.room, docs: PROPS.room && PROJECT[PROPS.room] ? PROJECT[PROPS.room].dataDocs : null, built: !!S, box, screen, spot: PROPS.place ? PROPS.place.dataServer.rect : null, wanted: PROPS.room ? dataServerWanted(PROPS.room) : null,
      open: ds.open, tab: ds.tab, loading: ds.loading, error: ds.error, api: ds.doc ? ds.doc.api.length : null, db: ds.doc ? ds.doc.db.length : null };
  },
  mermaidSafeText: (t) => mermaidSafeText(t),   // the text as it is handed to Mermaid (2.3.5)
  mermaidSafeSvg: (svg) => mermaidSafeSvg(svg),  // the drawn SVG as it goes into the page
  // the `secure` lock alone: the text drawn WITHOUT mermaidSafeText (this test hook only; the page never does)
  mermaidRenderUnsanitized: async (text) => {
    let box = document.getElementById('e2e-mermaid-raw');
    if (!box) { box = document.createElement('div'); box.id = 'e2e-mermaid-raw'; document.body.appendChild(box); }
    let svg = null, error = null;
    try { svg = await mermaidDraw(box, text, false); } catch (err) { error = String(err && err.message || err); }
    return { svg: !!svg, error, foreignObjects: box.querySelectorAll('foreignObject').length, imgs: box.querySelectorAll('img, image').length,
      htmlLabels: window.mermaid ? window.mermaid.mermaidAPI.getConfig().htmlLabels : null };
  },
  robotState: () => robotState,   // the model behind the robots (live: what the last slice said)
  // typed text through a redraw (50-panel.js keepFields): every keyed box of the panel, the board and the card's history drawn
  // again now, as a new record, a new question or a new order would draw them
  redrawTyped: () => { for (const el of [$('questions'), $('q-strip'), $('tasks'), $('tb-detail'), HIST.cards].filter(Boolean)) { el._sig = null; el._html = null; } refreshNow(); histCardsPaint(); },
  pricesRedraw: () => renderPrices(true),
  openPrices: () => openPrices(document.body),
  openTaskBoard: (detail) => openTaskBoard(document.body, detail),
  pendingPerms: () => latestModel.pending.filter((p) => p.status === 'pending').map((p) => p.id),
  drafts: () => Object.fromEntries(DRAFTS),
  histFold: () => { const el = HIST.cards, pane = typeof histPane === 'function' ? histPane() : null; return { folded: !!el && el.classList.contains('h-folded'), bar: el && el.querySelector('[data-h-fold]') ? el.querySelector('[data-h-fold]').textContent : null, fresh: !!(el && el.querySelector('.h-fold-new')), histH: pane ? pane.clientHeight : 0, cardsH: el ? el.clientHeight : 0 }; },
  // the outside (10-18): the arms force a season ('spring' …) or a weather ({ kind, isDay }); null gives it back
  outside: (opts) => {
    if (opts && 'season' in opts) OUTSIDE.force = opts.season;
    if (opts && 'weather' in opts) OUTSIDE.weatherForce = opts.weather;
    const g = TOWER.group;
    const find = (name) => (g ? g.children.find((o) => o.userData.outside === name) : null);
    const crowns = find('crowns'), c = new THREE.Color();
    return { season: season(), weather: weatherNow(), built: TOWER.outside || null, sky: sceneEl.dataset.sky || '',
      fall: TOWER.fall ? { kind: TOWER.fall.kind, n: TOWER.fall.n } : null, fog: !!scene.fog,
      crown: crowns && crowns.instanceColor ? '#' + (crowns.getColorAt(0, c), c.getHexString()) : null,
      branches: !!find('branches'), cicadas: find('cicadas') ? find('cicadas').count : 0, roofSnow: !!find('roofSnow'),
      ground: find('plaza') ? '#' + find('plaza').material.color.getHexString() : null,
      fallY: TOWER.fall ? Array.from({ length: Math.min(5, TOWER.fall.n) }, (_, i) => +TOWER.fall.pos[i * 3 + 1].toFixed(3)) : [] };
  },
  // play (10-18): the arms shorten the times; the real defaults stay in 40-scene.js
  play: (opts) => { if (opts) { if (opts.solo) Object.assign(SOLO, opts.solo, { next: 0 }); Object.assign(PLAY, opts, { next: 0 }); if ('restMaxSec' in opts) robots.forEach((R) => { R.restUntil = 0; }); if (opts.endAll) [...PLAY.list].forEach(playEnd); } return { ends: PLAY.ends.slice(), list: PLAY.list.map((G) => ({ room: G.room, kind: G.kind, players: G.players.map((R) => R.def.id), started: !!G.t0,
    ball: G.ball ? [+G.ball.position.x.toFixed(2), +G.ball.position.y.toFixed(2)] : null })),
    robots: robots.map((R) => ({ id: R.def.id, play: R.play ? R.play.phase : null, back: !!R.playBack, vis: R.robot.state, lamp: R.robot.lampState || R.robot.state, pose: R.robot.play ? R.robot.play.kind : null, rps: !!(R.robot.rps && R.robot.rps.visible),
      solo: R.solo ? R.solo.kind : null, zzz: !!(R.robot.zzz && R.robot.zzz.visible), bento: !!(R.robot.bento && R.robot.bento.visible), desk: !!(R.robot.desk && R.robot.desk.visible), seatKey: R.seatKey, tag: R.callText || '',
      x: +R.robot.root.position.x.toFixed(2), z: +R.robot.root.position.z.toFixed(2), seat: R.def.pos, room: R.def.room, path: R.path.length })) }; },
  rps: { round: rpsRound, T: RPS_T },   // じゃんけん's rounds (2.3.3): the arm finds a tie and reads the round after it
  towerPlay: () => TOWER.floors.map((F) => F.bays.map((b) => b.play || '')),   // a game's name on its window (2.3.3)
  calls: () => robots.map((R) => ({ id: R.def.id, call: R.robot.call ? { role: R.robot.call.role, state: R.robot.call.state, peer: R.robot.call.peer } : null,
    handset: !!R.robot.handset, ring: !!(R.robot.ring && R.robot.ring.visible), tag: R.callText || '', state: R.robot.state })),   // phone calls (10-18)
  model: () => latestModel,       // what the panels and boards draw from
  live3d: () => (SOURCE.mode === 'live' ? LIVE3D : null),   // the live rooms' boards
  links: () => links,             // the robot → board lines
  room: (id) => { const r = PROJECT[id]; return r ? { x0: r.x0, x1: r.x1, z0: r.z0, z1: r.z1, shown: !!r.shown, doors: r.doors || null } : null; },
  walls: () => (SOURCE.mode === 'live' ? liveWalls() : null),   // the wall pieces, door gaps cut out (the e2e checks no robot is in one)
  seats: () => (SOURCE.mode === 'live' ? JSON.parse(JSON.stringify(LIVE.seatOf)) : null),
  // desk spots (the floor room's coordinates, 0.1 apart) whose robot's tag would hold the page point pt in the room up
  // close: the robot at seatPos, its tag at + TAG_UP projected as placeRobotTags puts it, a tag's size as one drawn now
  // (the e2e pins one, so a tag covers the call bell in every run: ticket 2026-10-20-jui-viz-robot-tag-covers-a-fixture-in-a-crowded-room)
  // the things to press as tagFixtureRects sees them now, in page coordinates ([x0, x1, y0, y1] each), and which of a
  // robot's tag, bill and wait bubble are let through over one (.over-fixture)
  fixRects: () => { const r = canvas.getBoundingClientRect(); return tagFixtureRects(canvas.clientWidth, canvas.clientHeight).map(([x0, x1, y0, y1]) => [x0 + r.left, x1 + r.left, y0 + r.top, y1 + r.top]); },
  overFixture: (label) => { const R = robots.find((x) => x.def.id === label); if (!R) return null; const box = (e) => { if (!e || e.hidden) return null; const b = e.getBoundingClientRect(); return [b.left, b.right, b.top, b.bottom]; };
    return { tag: R.tag.classList.contains('over-fixture'), bill: !!(R.bill && R.bill.classList.contains('over-fixture')), wait: !!(R.waitEl && R.waitEl.classList.contains('over-fixture')), waitBox: box(R.waitEl), tagBox: box(R.tag), realId: R.def.realId || null }; },
  // the looks' limit (PROPS.max) for an arm: below the room's robots, the looks go with no relayout (the room grows at the
  // same count, roomSize, so the boundary alone never shows what dropping the looks does by itself); null puts it back
  propsMax: (n) => { if (PROPS.maxAsBuilt === undefined) PROPS.maxAsBuilt = PROPS.max; PROPS.max = n == null ? PROPS.maxAsBuilt : n; return PROPS.max; },
  // the floor of a room as drawn, read from the room (not PROPS): its material's id and whether it has a texture
  floorOf: (id) => { const R = LIVE3D.rooms[id]; return R ? { mat: R.floor.material.uuid, map: !!R.floor.material.map } : null; },
  // avoid: page rects ([x0, x1, y0, y1]) the tag must not touch (the bell, for a tag over the rack alone); away: desk spots
  // already pinned, which a remembered desk must keep clear of to be kept (takeSeat: seatsClear)
  tagPinsOver: (pt, avoid, away) => {
    if (SOURCE.mode !== 'live') return null;   // the seats are the live source's (30-source-live.js)
    const room = PROJECT[liveSolo()], t = robots.find((R) => R.tag.style.visibility !== 'hidden' && !R.tag.hidden);
    if (!room || !t) return null;
    const tb = t.tag.getBoundingClientRect(), w = tb.width, h = tb.height, r = canvas.getBoundingClientRect(), a = seatArea(room.baseW, room.baseD), out = [], v = new THREE.Vector3();
    for (let dx = Math.ceil(a.x0 * 10) / 10; dx <= a.x1; dx += 0.1) for (let dz = Math.ceil(a.z0 * 10) / 10; dz <= a.z1; dz += 0.1) {
      const p = seatPos(room, { dx, dz, standing: false }).pos;
      v.set(p[0], 0, p[1]).add(TAG_UP).project(camera);
      const x = r.left + (v.x + 1) / 2 * r.width, y = r.top + (1 - v.y) / 2 * r.height;
      const pts = Array.isArray(pt[0]) ? pt : [pt];   // one point, or several the one tag must hold (the bell and the rack)
      const clear = (away || []).every((q) => seatsClear([dx, dz], q)) && !(avoid || []).some((f) => x - w / 2 < f[1] && f[0] < x + w / 2 && y - h < f[3] && f[2] < y);
      if (clear && pts.every((q) => q[0] > x - w / 2 + 6 && q[0] < x + w / 2 - 6 && q[1] > y - h + 4 && q[1] < y - 4)) out.push([+dx.toFixed(2), +dz.toFixed(2), Math.max(...pts.map((q) => Math.hypot(x - q[0], y - h / 2 - q[1])))]);
    }
    // best: the spot whose tag's middle is nearest the point(s) (the most room on every side)
    const best = out.slice().sort((p, q) => p[2] - q[2])[0];
    return { n: out.length, best: best ? best.slice(0, 2) : null, bestOff: best ? +best[2].toFixed(1) : null, tag: [w, h] };
  },
  solo: () => (SOURCE.mode === 'live' ? liveSolo() : null),
  // the room's robot list (53-roster.js): its rows as the page shows them, the room's robots as the 3D draws them, where
  // the list and the room's name box sit, and what this browser keeps for the room
  roster: () => { const box = document.getElementById('roster'), solo = SOURCE.mode === 'live' ? liveSolo() : null, rect = (el) => { if (!el || el.hidden) return null; const r = el.getBoundingClientRect(); return [r.left, r.top, r.right, r.bottom].map(Math.round); };
    const rows = [...document.querySelectorAll('#roster-list .roster-row')].map((li) => ({ key: li.dataset.rosterKey, id: li.dataset.robot, on: li.querySelector('.roster-check').checked,
      wait: li.dataset.wait || null, alert: li.classList.contains('roster-alert'), name: li.querySelector('.roster-nm').textContent, lamp: li.querySelector('.roster-lamp').style.getPropertyValue('--lamp'),
      current: li.getAttribute('aria-current') === 'true', inView: (() => { const L = li.parentElement.getBoundingClientRect(), r = li.getBoundingClientRect(), at = document.elementFromPoint(r.left + 12, (r.top + r.bottom) / 2);
        return r.top >= L.top - 1 && r.bottom <= L.bottom + 1 && !!at && li.contains(at); })() }));
    const bots = solo ? robots.filter((R) => R.def.room === solo).map((R) => ({ id: R.def.id, sid: R.def.sessionId, kind: R.def.kind, root: R.robot.root.visible,
      tag: R.tag.style.visibility || '', desk: !!(R.robot.desk && R.robot.desk.visible), busy: !!(R.play || R.solo || R.brk), play: R.play ? R.play.phase : null, main: R.def.kind === 'sub' ? R.def.mainLabel : null,
      spiritBubble: R.spirit && R.spirit.bubbleEl && !R.spirit.bubbleEl.hidden ? (R.spirit.bubbleEl.style.visibility || 'visible') : null })) : [];
    const alert = document.getElementById('roster-alert');
    return { shown: !!box && !box.hidden, solo, rows, bots, alert: alert && !alert.hidden ? alert.textContent : null, count: (document.getElementById('roster-count') || {}).textContent || '',
      folded: !!box && box.classList.contains('roster-folded'), rect: rect(box), err: rect(document.getElementById('live-error')), soloBox: rect(document.getElementById('room-solo')), card: rect(document.querySelector('#rb.show')), waits: rect(document.getElementById('rb-waits')),
      scene: rect(document.getElementById('scene')), ring: selRing.visible, floorNav: rect(document.getElementById('floor-nav')),
      // every control shown on the page that the list lies on (the live suite's floor check, OVERLAP_JS, asks the same)
      hits: (() => { if (!box || box.hidden) return []; const vis = (el) => { if (!el || el.closest('[hidden]')) return false; const st = getComputedStyle(el);
          if (st.display === 'none' || st.visibility === 'hidden') return false; const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
        const a = box.getBoundingClientRect();
        return [...document.querySelectorAll('button, input, select, textarea, a[href], [role="option"], [role="dialog"], [tabindex]:not([tabindex="-1"])')]
          .filter((el) => vis(el) && !box.contains(el) && !el.closest('.tags'))
          .filter((el) => { const b = el.getBoundingClientRect(); return a.left < b.right && b.left < a.right && a.top < b.bottom && b.top < a.bottom; })
          .map((el) => el.id || el.className || el.tagName); })(), permChip: (($('chip-perm') || {}).hidden === false) ? $('chip-perm').textContent : null, saved: solo ? readPref(`roster:${solo}`, '') : '',
      sort: ($('roster-sort') || {}).value || null, order: solo ? readPref(`roster-order:${solo}`, '') : '', focusKey: (() => { const f = document.activeElement; const r = f && f.closest && f.closest('.roster-row'); return r ? r.dataset.rosterKey : null; })() }; },
  // robots' name tags as drawn (10-19): the screen rect of each visible one, and placeRobotTags' cost
  tags: () => robots.filter((R) => R.tag.style.visibility !== 'hidden' && !R.tag.hidden && !tagsEl.hidden).map((R) => {
    const b = R.tag.getBoundingClientRect(); return { id: R.def.id, text: R.tag.textContent, x0: b.left, x1: b.right, y0: b.top, y1: b.bottom }; }),
  // tags left on each other (2.3.6, the click on a tag): false turns off keeping them apart, so the e2e can put one
  // robot's tag over another's and check the nearer takes the click; true (or nothing) puts the passes back
  tagsApart: (on) => { if (TAGS.passesAsBuilt === undefined) TAGS.passesAsBuilt = TAGS.maxPasses; TAGS.maxPasses = on === false ? 0 : TAGS.passesAsBuilt; return TAGS.maxPasses; },
  // a bill over robot `label` now (54-bills.js), without a response: the click-on-a-bill arm
  billShow: (label, usd) => { billShow(label, { id: `e2e-${label}-${performance.now()}`, usd, tokens: 1200, model: 'e2e-model', from: 'default' }); return !!(robots.find((x) => x.def.id === label) || {}).bill; },
  // placeRobotTags' own CPU time, k placements in a row in this call (2.3.5): the cost arm reads this, not the frames a
  // loaded machine happened to draw (1–2 in 3 s at load 90–130). The frame stats are left as they were.
  tagBench: (k) => { const keep = { ...TAGS.stats }; let sum = 0, max = 0;
    for (let i = 0; i < k; i++) { const t = performance.now(); placeRobotTags(); const ms = performance.now() - t; sum += ms; max = Math.max(max, ms); }
    Object.assign(TAGS.stats, keep); return { n: robots.length, runs: k, meanMs: sum / k, maxMs: max }; },
  tagStats: (reset) => { const S0 = TAGS.stats, out = { n: S0.n, frames: S0.frames, meanMs: S0.frames ? S0.sumMs / S0.frames : 0, maxMs: S0.maxMs };
    if (reset) Object.assign(S0, { sumMs: 0, maxMs: 0, frames: 0 }); return out; },
  // the shredder (10-19): where it is and its box, the bits in flight, and each robot's errand
  shred: () => ({ shredder: PROPS.shredder ? { x: PROPS.shredder.x, z: PROPS.shredder.z, spot: PROPS.shredder.spot, box: PROPS.shredder.box } : null,
    bits: (PROPS.bits || []).length, boxes: PROPS.boxes,
    robots: robots.map((R) => ({ id: R.def.id, room: R.def.room, phase: R.shred ? R.shred.phase : null, held: !!(R.shred && R.shred.held),
      back: !!R.playBack, tilt: !!R.tiltUntil, x: +R.robot.root.position.x.toFixed(2), z: +R.robot.root.position.z.toFixed(2), seat: R.def.pos,
      path: R.path.length, act: R.act, tag: R.text.textContent })) }),
  // the room up close (10-18): what is placed, where the vacuum is, the boxes it keeps clear of, and three's counts
  // the call bell (2.3.5): its place, whether it is built, and where its dome is on the page (for a real click)
  bell: () => {
    if (!PROPS.bell) return { built: false, place: PROPS.place ? PROPS.place.callButton : null };
    const v = new THREE.Vector3(PROPS.bell.position.x, BELL.h - 0.02, PROPS.bell.position.z).project(camera), r = canvas.getBoundingClientRect();
    return { built: true, place: PROPS.place.callButton, room: PROPS.room, open: !document.getElementById('call').hidden,
      screen: [Math.round(r.left + ((v.x + 1) / 2) * r.width), Math.round(r.top + ((1 - v.y) / 2) * r.height)], inView: v.z > -1 && v.z < 1 };
  },
  // what lies under a page point in the live office, nearest first (one entry per thing): the e2e shows a robot stands in
  // front of the bell or the rack before it presses there (ticket 2026-10-20-jui-viz-callbell-bell-hidden-behind-a-desk)
  under: ([x, y]) => {
    if (SOURCE.mode !== 'live' || TOWER.on) return null;
    const r = canvas.getBoundingClientRect(), ray = new THREE.Raycaster();
    ray.setFromCamera(new THREE.Vector2(((x - r.left) / r.width) * 2 - 1, -((y - r.top) / r.height) * 2 + 1), camera);
    const seen = [];
    for (const h of ray.intersectObjects(liveTargets(), true)) {
      const rid = robotOf(h.object), k = rid !== undefined ? `robot:${rid}` : isFixture(h.object) ? (h.object.userData.dataServer ? 'rack' : h.object.userData.serverDoor ? 'door' : 'bell') : 'board';
      if (!seen.includes(k)) seen.push(k);
    }
    return seen;
  },
  props: () => {
    const R = PROPS.room ? LIVE3D.rooms[PROPS.room] : null, v = PROPS.vac, sv = PROPS.server;
    return { room: PROPS.room, server: sv ? [+sv.position.x.toFixed(2), +sv.position.z.toFixed(2)] : null,
      vac: v ? [+v.position.x.toFixed(3), +v.position.z.toFixed(3)] : null, radius: PROPS.radius, boxes: PROPS.boxes,
      area: PROPS.room ? propsArea() : null, wood: !!(R && R.floor.material === PROPS.woodMat && PROPS.woodMat && PROPS.woodMat.map),
      floorMap: Object.values(LIVE3D.rooms).some((x) => !!x.floor.material.map), sceneChildren: scene.children.length - robots.length,   // less the robots, which come and go
      memory: { ...renderer.info.memory },
      // the two sets (2.3.10): the looks only with PROPS.max robots or fewer; the things with a use, one group kept across it
      fun: !!PROPS.fun, groupId: PROPS.group ? PROPS.group.uuid : null, funGroupId: PROPS.funGroup ? PROPS.funGroup.uuid : null,
      uses: { shredder: !!PROPS.shredder, gitDesk: !!PROPS.gitDesk, bell: !!PROPS.bell, dataServer: !!PROPS.dataServer, serverDoor: !!PROPS.serverDoor },
      looks: { booth: !!PROPS.booth, vend: !!PROPS.vend, vac: !!PROPS.vac, server: !!PROPS.server } };
  },
  // breaks (10-19): the arms shorten the times (the real defaults stay in 40-scene.js); where the props stand, for a room
  // as it is or for any rectangle and doors (the arms try every size the layout makes); who is on a break
  brk: (opts) => {
    if (opts) { Object.assign(BRK, opts, { next: 0 }); if (opts.p) BRK.p = { ...opts.p }; if ('restMaxSec' in opts) robots.forEach((R) => { R.restUntil = 0; }); if (opts.endAll) robots.forEach((R) => { if (R.brk) brkStop(R, 'e2e', performance.now() / 1000); }); }
    const P = PROPS.place;
    const top = (o) => { if (!o) return null; const b = new THREE.Box3(); o.updateMatrixWorld(true); o.traverseVisible((m) => { if (m.isMesh) b.expandByObject(m, true); }); return [+b.min.y.toFixed(3), +b.max.y.toFixed(3)]; };
    const xz = (o) => { if (!o) return null; const b = new THREE.Box3(); o.updateMatrixWorld(true); o.traverseVisible((m) => { if (m.isMesh) b.expandByObject(m, true); }); return [b.min.x, b.max.x, b.min.z, b.max.z].map((v) => +v.toFixed(3)); };
    return { ends: BRK.ends.slice(), place: P ? JSON.parse(JSON.stringify(P)) : null, meshBoxes: { booth: xz(PROPS.booth), vend: xz(PROPS.vend), server: xz(PROPS.server), bell: xz(PROPS.bell), ...(PROPS.dataServer ? { dataServer: xz(PROPS.dataServer.group) } : {}) }, heights: { vend: top(PROPS.vend), robots: robots.filter((R) => R.robot.root.visible).map((R) => [R.def.id, top(R.robot.root), !!(R.robot.desk && R.robot.desk.visible)]) },
      deskBoxes: robots.filter((R) => R.def.room === PROPS.room && !R.brk && !R.playBack && !R.path.length && R.robot.root.visible).map((R) => [R.def.id, xz(R.robot.root)]), built: { booth: !!PROPS.booth, vend: !!PROPS.vend, fan: PROPS.fan ? +PROPS.fan.rotation.z.toFixed(2) : null },
      smoke: PROPS.smoke.filter((q) => q.s.visible).length, puffs: PROPS.smoke.filter((q) => q.s.visible).map((q) => [...q.s.position.toArray().map((v) => +v.toFixed(2)), +q.s.scale.x.toFixed(2), +q.s.material.opacity.toFixed(2)]), smokeMax: PROPS.smoke.length,
      robots: robots.map((R) => ({ id: R.def.id, kind: R.brk ? R.brk.kind : null, phase: R.brk ? R.brk.phase : null, at: !!R.robot.brk, back: !!R.playBack,
        hand: R.robot.brkHandKind || null, tag: R.callText || '', vis: R.robot.state, lamp: R.robot.lampState || R.robot.state, desk: !!(R.robot.desk && R.robot.desk.visible),
        play: !!R.play, solo: R.solo ? R.solo.kind : null, x: +R.robot.root.position.x.toFixed(3), z: +R.robot.root.position.z.toFixed(3), seat: R.def.pos, room: R.def.room, path: R.path.length })) };
  },
  propsPlace: (r) => propsPlace(r),
  seatGeom: () => ({ SEAT: JSON.parse(JSON.stringify(SEAT)), SEAT_SOLO: { ...SEAT_SOLO }, SOLO_GROW, DOOR_W, roomSize: [1, 7, 11].map(roomSize), doorAt: doorAt({ x0: 0, x1: 0, z0: 0, z1: 0 }) }),
  // the usage chips as drawn (10-18): per window its text, the number's and the %'s colours, 上限到達, the note
  usage: () => [...document.querySelectorAll('#usage .uw')].map((e) => ({ window: e.dataset.window || null, text: e.textContent, title: e.title,
    num: e.querySelector('.num') ? getComputedStyle(e.querySelector('.num')).color : null,
    pc: e.querySelector('.pc') ? getComputedStyle(e.querySelector('.pc')).color : null,
    limit: !!e.querySelector('.limit'), limitColor: e.querySelector('.limit') ? getComputedStyle(e.querySelector('.limit')).color : null,
    note: e.querySelector('.stale') ? e.querySelector('.stale').textContent : '' })),
  // every header chip as laid out (10-19): its box and its text's box — a stale note must not swell the row
  chipBoxes: () => [...document.querySelectorAll('.chips > :not(.usage), .chips > .usage > *')].filter((e) => e.offsetParent !== null).map((e) => {
    const b = e.getBoundingClientRect(), r = document.createRange();
    r.selectNodeContents(e);
    const t = r.getBoundingClientRect();
    return { name: e.id || e.className, h: +b.height.toFixed(1), top: +b.top.toFixed(1), bottom: +b.bottom.toFixed(1),
             mid: +((b.top + b.bottom) / 2).toFixed(1), textMid: +((t.top + t.bottom) / 2).toFixed(1) };
  }),
  usageHue: SOURCE.mode === 'live' ? usageHue : null,
  usageColor: SOURCE.mode === 'live' ? usageColor : null,   // (pct, dark) → the colour the header would use
  inkSoft: () => { const e = document.createElement('span'); e.style.color = 'var(--ink-soft)'; document.body.append(e); const c = getComputedStyle(e).color; e.remove(); return c; },
  floors: () => ({ floors: LIVE.floors, floor: LIVE.floor, rank: LIVE.rank, tower: TOWER.on, look: TOWER.look }),
  beats: () => (SOURCE.mode === 'demo' ? DEMO_BEATS : null),
  director: () => ({ userAt: DIRECTOR.userAt }),
  condition: (id) => robotCondition(id),
  assignFloors: SOURCE.mode === 'live' ? assignFloors : null,
  goFloor: SOURCE.mode === 'live' ? liveFloorStep : null,
  tower: (on) => (on ? towerEnter() : towerLeave(LIVE.floor)),
  // What a press at (x, y) on the canvas hits in the building — the same ray and towerHit the pointer uses.
  towerAt: (x, y) => {
    if (!TOWER.on) return null;
    const r = document.getElementById('scene-canvas').getBoundingClientRect(), ray = new THREE.Raycaster();
    ray.setFromCamera(new THREE.Vector2(((x - r.left) / r.width) * 2 - 1, -((y - r.top) / r.height) * 2 + 1), camera);
    const h = towerHit(ray);
    return h ? { k: h.k, project: h.project } : null;
  },
  project: () => UI.project,
  towerDistance: () => { const want = towerPose(); return { at: +camera.position.distanceTo(want.t).toFixed(1), want: +want.p.distanceTo(want.t).toFixed(1) }; },
  towerActors: () => (TOWER.actors ? Object.fromEntries(Object.entries(TOWER.actors).map(([k, m]) => [k, m.count])) : null),
  towerLook: (k) => { const y = towerY(k), t = new THREE.Vector3(0, y, TOWER.D / 2); flyTo(t.clone().add(new THREE.Vector3(2, 1.5, 30)), t, controls.target, 0, () => { controls.target.copy(t); controls.update(); }); },
  setClock: (ms) => { VIZ_CLOCK.at = ms; },
  sky: () => ({ phase: (sceneEl.dataset.sky || '').split(':')[0], background: sceneEl.style.background }),
  snack: SOURCE.mode === 'live' ? (o) => { Object.assign(SNACK, o || {}); SNACK.rng = null; SNACK.next = 0; } : null,
  gestures: () => robots.map((R) => ({ id: R.def.id, state: R.robot.state, gesture: R.robot.gesture ? R.robot.gesture.kind : null, tired: !!R.robot.tired, drinks: R.robot.drinks || 0,
    heavy: heavyCauses(R.robot).length > 0, sweat: !!(R.robot.sweat && R.robot.sweat.visible), act: R.text ? R.text.textContent : '', actShown: R.text ? getComputedStyle(R.text).display !== 'none' : false })),
  // heavy work's three looks (2.3.6): force a robot's causes or tiredness (null gives them back), and read each look
  // from the robot itself: its causes, the look now, the screen's colour (a pixel of the face canvas, below the
  // mouth, clear of the eyes and the lines), the face drawn, the whistle, the sweat, the arm and the antenna
  force: (id, o) => { const R = robots.find((x) => x.def.id === id); if (!R) return false; R.robot.force = o ? { ...(R.robot.force || {}), ...o } : null; return true; },
  looks: (ids) => robots.filter((R) => !ids || ids.includes(R.def.id)).map((R) => {
    const r = R.robot, probe = makeCanvas(1, 1).getContext('2d', { willReadFrequently: true });
    probe.drawImage(r.faceCanvas, 60, 112, 1, 1, 0, 0, 1, 1);
    const px = probe.getImageData(0, 0, 1, 1).data;
    return { id: R.def.id, role: r.role, state: r.state, tired: !!r.tired, looks: heavyCauses(r), look: r.look,
      tint: r.tint ? r.tint.map((v, i) => (i < 3 ? Math.round(v) : +v.toFixed(3))) : null, face: String(r.faceMode).split('|')[0],
      screen: [px[0], px[1], px[2]], whistle: !!(r.whistle && r.whistle.visible), pipi: !!(r.pipi && r.pipi.visible), sweat: !!(r.sweat && r.sweat.visible),
      armRz: +r.armR.rotation.z.toFixed(3), antenna: +r.antenna.rotation.x.toFixed(3), period: LOOK_PERIOD, reduced: reduceMotion,
      eased: !r.tint || (r.look ? LOOK_TINT[r.look] : [r.tint[0], r.tint[1], r.tint[2], 0]).every((v, i) => Math.abs(v - r.tint[i]) < (i < 3 ? 3 : 0.01)) };
  }),
  // a close look at one robot's face, from in front of it (for the pictures of the looks)
  faceCam: (id, dist = 3.6) => {
    const R = robots.find((x) => x.def.id === id); if (!R) return false;
    const head = R.robot.head.localToWorld(new THREE.Vector3(0, 0.3, 0)), ry = R.robot.root.rotation.y;
    const eye = head.clone().add(new THREE.Vector3(Math.sin(ry) * dist, 1.4, Math.cos(ry) * dist));   // within maxPolarAngle
    controls.minDistance = Math.min(controls.minDistance, dist);   // the orbit's floor (8) would push it back out
    flyTo(eye, head, controls.target, 0, () => { controls.target.copy(head); controls.update(); });
    return true;
  },
  towerLines: (text) => { const f = towerNameFit(makeCanvas(8, 8).getContext('2d'), text, towerBays()[0].w - 8); return [f.size, ...f.lines]; },
  openRobot: (id) => openRobot(id, document.getElementById('scene-canvas')),
  selectRobot: (id) => selectRobot(id, document.getElementById('scene-canvas')),   // a pick from outside the view (a talk, a notification)
  // a robot's wait as 3D shows it (53-waits.js): its kind, lamp, pose and bubble; what a bubble's press picked
  waitLook: (id) => { const R = robots.find((x) => x.def.id === id); if (!R) return null; const b = R.waitEl;
    return { kind: R.robot.waitKind || null, lamp: R.robot.lampKey || null, pose: R.robot.poseName || null,
      bubble: b && !b.hidden ? b.textContent : null, bubbleShown: !!(b && !b.hidden && b.style.visibility === 'visible') }; },
  waitPicked: () => WAIT.picked,
  tl: (k, a) => tl(k, a),   // the page's words, as the e2e compares them
  closeTaskBoard: () => closeTaskBoard(),
  towerStateOf: (id) => (SOURCE.mode === 'live' ? towerState(id) : null),
  // a session's main robot and a robot's project, as the page has them (tools/viz_e2e/project_switch.py)
  labelOfSession: (sid) => (typeof SESSION_UUID === 'undefined' ? null : Object.keys(SESSION_UUID).find((l) => SESSION_UUID[l] === sid) || null),
  robotProject: (id) => projectOfRobot(id) || null,
  // the デバイス pane (tools/viz_e2e/devices_pane.py): the picked robot, the project, the server's machine slice, the
  // button's colour per level, a project switch as the picker does it, the robot a project remembers
  devState: () => ({ robot: rbState.id, project: UI.project, card: !document.getElementById('rb').hidden, pane: !document.getElementById('dev-pane').hidden }),
  devMachine: () => (SOURCE.mode === 'live' ? LIVE.slices.machine || null : null),
  devColours: () => { const b = document.getElementById('btn-devices'), keep = b.dataset.load;
    const out = Object.fromEntries(['ok', 'busy', 'high'].map((l) => { b.dataset.load = l; return [l, getComputedStyle(b).backgroundColor]; }));
    b.dataset.load = keep; return out; },
  setProject: (id) => setProject(id, { camera: false }),
  lastRobot: (id) => (LAST_ROBOT.has(id) ? LAST_ROBOT.get(id) : undefined),
  // the box (2.3.4): its desk, what it overlaps, the papers in it, each robot's trip and the trips' ends
  gitBox: () => ({ room: PROPS.room, desk: !!PROPS.gitDesk, fill: PROPS.gitFill, spot: PROPS.place ? PROPS.place.git : null,
    overlaps: gitDeskOverlaps(), ends: GITBOX.ends.slice(),
    trips: Object.fromEntries(robots.filter((R) => R.git).map((R) => [R.def.id, { id: R.git.trip.id, phase: R.git.phase, kind: R.git.trip.kind, sheets: R.robot.carrySheets,
      look: R.robot.state, at: R.robot.root.position.toArray().map((v) => +v.toFixed(2)) }])),
    said: Object.fromEntries(robots.map((R) => [R.def.id, R.text.textContent])),
    why: Object.fromEntries(robots.map((R) => { const st = robotState[R.def.id] || {}; return [R.def.id, { trip: st.git ? { id: st.git.id, pending: st.git.pending, at: st.git.at, kind: st.git.kind } : null,
      seen: R.gitSeen || null, git: R.git ? R.git.phase : null, path: R.path.length, pos: R.robot.root.position.toArray().map((v) => +v.toFixed(2)), desk: R.def.pos, play: !!(R.play || R.playBack || R.solo), standing: !!R.def.standing, room: R.def.room, propsRoom: PROPS.room, state: st.state }]; })) }),
  // a fresh trip on the page alone, as if the server had sent it (the trip-vs-break arm: a trip that comes during a break)
  gitPoke: (id, trip) => { const st = robotState[id]; if (st) st.git = { at: vizNow(), pending: false, kind: 'push', status: 'pushed', ...trip }; return !!st; },
  liveSeenSeq: () => LIVE.seenSeq,   // the last event the page took in (a hook that rings nothing leaves no other trace)
  gitLog: () => logItems.filter((e) => e.kind === 'GitPush' || e.kind === 'GitPull').map((e) => `${e.kind} ${e.what}`),
  gitSet: (o) => { Object.assign(GITBOX, o || {}); return { ...GITBOX, ends: undefined }; },
  // the camera on a robot (10-18): its orbit, how its view was chosen, and what stands in the way now
  focus: () => {
    const R = rbState.id ? robots.find((x) => x.def.id === rbState.id) : null;
    const now = R ? [...focusBlockers(R, camera.position)] : [];
    return { id: FOCUS.id, az: +FOCUS.az.toFixed(4), el: +FOCUS.el.toFixed(4), dist: +FOCUS.dist.toFixed(3), chosen: FOCUS.chosen,
      cam: camera.position.toArray().map((v) => +v.toFixed(3)), zoomed: zoom.zoomed, tween: !!camTween,
      blockersNow: now.length, blockersFaded: now.filter((o) => FOCUS.faded.has(o)).length, faded: FOCUS.faded.size,
      fadedOpacity: [...FOCUS.faded.keys()].map((o) => [].concat(o.material)[0].opacity) };
  },
  // the card and the camera agree (ticket 2026-10-21-jui-viz-3d-zoom-lost-after-project-switch): how far what the camera
  // looks at is from the open robot, and how far the camera is from the room's (or the floor's) own view
  // rbFollow (50-panel.js): the card's mark when its robot moved and the view did not follow, and the last switch by hand
  follow: () => ({ moved: rbState.moved, seen: rbState.seen, handAt: FOLLOW.handAt, toast: document.getElementById('toast').textContent }),
  // a skill in use (45-spirits.js): the robot's skill, its spirit's model and phase, what it wears and hides, its badge
  // and bubble; and the page's whole count of standing spirits
  spirit: (id) => {
    const R = robots.find((x) => x.def.id === id); if (!R) return null;
    const S = R.spirit, st = robotState[id] || {};
    const shown = (el) => !!el && !el.hidden && el.style.visibility !== 'hidden';
    return { skill: st.skill ? st.skill.name : null, model: S && S.model ? S.model.id : null, phase: S ? S.phase : null,
      figure: !!(S && S.figure), holders: S ? S.holders.length : 0, error: S ? S.error || null : null,
      band: R.robot.band.visible, cheek: !!(S && S.tagCheek),
      ghost: !!(S && S.ghost), eyes: R.robot.spiritEyes ? R.robot.spiritEyes.shape : null, face: R.robot.faceMode || null,
      pose: R.robot.spiritPose || null,
      near: S ? S.near !== false : null, figureShown: !!(S && S.figure && S.figure.visible),
      mixerTime: S && S.mixer ? +S.mixer.time.toFixed(3) : null,
      bubbleBox: S && shown(S.bubbleEl) ? (({ left, top, right, bottom }) => ({ left, top, right, bottom }))(S.bubbleEl.getBoundingClientRect()) : null,
      fx: S && S.fx ? { aura: !!S.fx.aura, glow: !!S.fx.glow, bolt: !!S.fx.bolt, clones: S.fx.clones.length,
        // the aura's look: its style, its flame tongues and their heights summed (they rise: it changes), its brightest
        auraStyle: S.fx.aura ? S.fx.aura.style || 'column' : null, tongues: S.fx.aura && S.fx.aura.tongues ? S.fx.aura.tongues.length : 0,
        tongueY: S.fx.aura && S.fx.aura.tongues ? +S.fx.aura.tongues.reduce((t, x) => t + x.sp.position.y, 0).toFixed(3) : null,
        tongueTop: S.fx.aura && S.fx.aura.tongues ? +Math.max(...S.fx.aura.tongues.map((x) => x.sp.material.opacity)).toFixed(3) : null,
        sparkPool: S.fx.sparks.length,
        // outline and glow shells left in the afterimages (each is a copy of the figure: 0, a faint copy draws neither)
        cloneShells: S.fx.clones.reduce((t, cl) => { let n = 0; cl.c.traverse((o) => { if (o.isMesh && (o.userData.spiritGlow || o.userData.spiritOutline)) n++; }); return t + n; }, 0),
        // the lightning: its bolts, each a ribbon of meshes (a core in a glow, so it has width), and whether one shows now
        bolts: Array.isArray(S.fx.bolts) ? S.fx.bolts.length : (S.fx.bolt ? 1 : 0),
        boltWidth: Array.isArray(S.fx.bolts) && S.fx.bolts[0] ? +S.fx.bolts[0][0][1].scale.x.toFixed(3) : 0,
        // how far each bolt's segment ends from where the next begins (0: one unbroken zigzag)
        boltGap: Array.isArray(S.fx.bolts) ? +Math.max(0, ...S.fx.bolts.flatMap((segs) => segs.slice(1).map(([c], i) => {
          const p = segs[i][0]; return new THREE.Vector3(0, 0, p.scale.z).applyQuaternion(p.quaternion).add(p.position).distanceTo(c.position); }))).toFixed(4) : null,
        boltShown: !!S.fx.bolt && (S.fx.bolt.glow ? S.fx.bolt.glow.opacity > 0 : S.fx.bolt.material.opacity > 0),
        sparks: S.fx.sparks.filter((x) => x.sp.visible).length, shouts: S.fx.shouts.filter((x) => x.sp.visible).length } : null,
      textures: (() => { let maps = 0, loaded = 0; if (S && S.figure) S.figure.traverse((o) => { if (!o.isMesh) return;
        for (const m of [].concat(o.material)) if (m.map) { maps++; const im = m.map.image; if (im && (im.width || im.naturalWidth)) loaded++; } });
        return { maps, loaded }; })(),
      badge: shown(R.skillEl) ? R.skillEl.textContent : null,
      bubble: S && shown(S.bubbleEl) ? { text: S.bubbleEl.textContent, ruby: (S.bubbleEl.querySelector('rt') || {}).textContent || null,
        target: S.bubbleEl.dataset.target } : null };
  },
  // the shells on the figure ('outline', or 'glow': effects.glow), each matched to the mesh it goes round (its parent,
  // else the mesh sharing its geometry): how many, how many figure meshes have none and how many under an fx_… node
  // have one, and the most any shell's world matrix (and, skinned, each bone's) differs from its mesh's now (0: posed
  // as the figure is); for the glow, the most its rim differs from the one wanted, in parts (0: the same on every mesh,
  // whatever its own scale); how many are hidden (spiritLod)
  spiritShells: (id, kind) => {
    const R = robots.find((x) => x.def.id === id), S = R && R.spirit;
    if (!S || !S.figure) return null;
    const isShell = (x) => x.userData.spiritOutline || x.userData.spiritGlow;
    const own = [], fxOwn = new Set();
    const walk = (o, fx) => { fx = fx || /^fx_/.test(o.name || ''); if (o.isMesh && !isShell(o)) { own.push(o); if (fx) fxOwn.add(o); } o.children.forEach((c) => walk(c, fx)); };
    walk(S.figure, false);
    const shells = [];
    if (kind === 'glow') { const G = S.fx && S.fx.glow; if (!G) return null;
      (Array.isArray(G) ? G : (() => { const l = []; G.traverse((x) => { if (x.isMesh && !x.userData.spiritOutline) l.push(x); }); return l; })()).forEach((x) => shells.push(x)); }
    else S.figure.traverse((x) => { if (x.isMesh && x.userData.spiritOutline) shells.push(x); });
    scene.updateMatrixWorld(true);
    const off = (x, y) => Math.max(...x.matrixWorld.elements.map((v, k) => Math.abs(v - y.matrixWorld.elements[k])));
    let gap = 0, bones = 0, lost = 0, reach = 0;
    const covered = new Set(), fig = S.figure.getWorldScale(new THREE.Vector3()).x || 1, ws = new THREE.Vector3();
    for (const sh of shells) {
      const m = own.includes(sh.parent) ? sh.parent : own.find((x) => x.geometry === sh.geometry); if (!m) { lost++; continue; }
      covered.add(m);
      gap = Math.max(gap, off(sh, m));
      // a glow's rim as drawn (the shader's uWidth times the mesh's scale in the figure) against the one wanted; not
      // compiled yet: 1 (as far off as it can be said)
      const u = sh.material.userData, drawn = sh.material.spiritShader && sh.material.spiritShader.uniforms.uWidth.value;
      if (u.reach) reach = Math.max(reach, Number.isFinite(drawn) ? Math.abs(drawn * (sh.getWorldScale(ws).x / fig) / u.reach - 1) : 1);
      if (sh.isSkinnedMesh && m.isSkinnedMesh) sh.skeleton.bones.forEach((bone, j) => { bones++; gap = Math.max(gap, off(bone, m.skeleton.bones[j])); });
    }
    const pose = own.reduce((t, m) => t + m.matrixWorld.elements.reduce((u, v) => u + v, 0)
      + (m.isSkinnedMesh ? m.skeleton.bones.reduce((u, x) => u + x.matrixWorld.elements.reduce((w, v) => w + v, 0), 0) : 0), 0);   // the figure's pose, summed: changes as it moves
    return { shells: shells.length, meshes: own.length, fxMeshes: fxOwn.size, bare: own.filter((m) => !fxOwn.has(m) && !covered.has(m)).length,
      onFx: [...fxOwn].filter((m) => covered.has(m)).length, lost, bones, gap: +gap.toFixed(4), pose: +pose.toFixed(4),
      reach: +reach.toFixed(4), hidden: shells.filter((x) => !x.visible).length,
      mixerTime: S.mixer ? +S.mixer.time.toFixed(3) : null };
  },
  spiritsStanding: () => robots.filter((x) => x.spirit && x.spirit.figure).length,
  mainDraw: () => ({ calls: renderer.info.render.calls, triangles: renderer.info.render.triangles }),   // the last frame's
  spiritHide: (what) => { SPIRIT.hide = what || null; },
  // a slow model read, as on a loaded machine (the room's list arm): each spirit's models come ms later
  spiritLoadDelay: (ms) => { if (!spiritLoad.slowed) { const read = spiritLoad; spiritLoad = async (m) => { const got = await read(m);
      await new Promise((r) => setTimeout(r, SPIRIT_DBG.delay)); return got; }; spiritLoad.slowed = true; } SPIRIT_DBG.delay = ms || 0; return SPIRIT_DBG.delay; },   // the frame-cost samples: what to leave out (45-spirits.js)
  projectName: (id) => (PROJECT[id] ? PROJECT[id].name : null),
  // where a robot stands in the 3D (the room under it) and whether it is still walking
  robotAt: (id) => { const R = robots.find((x) => x.def.id === id); if (!R) return null; const q = R.robot.root.position;
    return { room: roomAtPoint([q.x, q.z]), walking: R.path.length > 0 }; },
  camOn: () => {
    const t = zoom.zoomed ? viewTarget : controls.target, R = rbState.id ? robots.find((x) => x.def.id === rbState.id) : null;
    const room = roomPose(UI.project);
    const flat = (a, b) => Math.hypot(a.x - b.x, a.z - b.z);
    return { card: rbState.id, zoomed: zoom.zoomed, tween: !!camTween, waitFor: zoom.waitFor, inScene: !!R,
      toRobot: R ? +flat(t, R.robot.root.position).toFixed(2) : null, toRoom: +camera.position.distanceTo(room.p).toFixed(2),
      returnToRoom: zoom.returnPose ? +zoom.returnPose.p.distanceTo(room.p).toFixed(2) : null };
  },
  // what holds the 3D view (ticket 2026-10-20-jui-viz-data-server-from-robot-card-freezes-3d): the camera's zoom and
  // tween, whether the orbit takes input, the card, every screen open over the 3D, the tags layer
  view: () => ({ zoomed: zoom.zoomed, controls: controls.enabled, tween: !!camTween, card: rbState.id,
    open: { rb: !rbEl.hidden, wb: wb.open, tb: tb.open, ds: ds.open, pr: pr.open, log: logState.open },
    tagsHidden: tagsEl.hidden, held: typeof VIEW_HOLD === 'undefined' ? null : [...VIEW_HOLD] }),
  // the rack pressed (40-scene.js's pick, kind 'data', makes this same call) — for when the camera, framing a robot's
  // card, leaves the rack off the screen
  pressRack: () => { if (!PROPS.dataServer || !PROPS.room) return false; openDataDocs(PROPS.room, canvas); return true; },
  // a robot's spot on the screen (a real click there opens its card)
  robotXY: (id) => {
    const R = robots.find((x) => x.def.id === id);
    if (!R) return null;
    const v = R.robot.root.position.clone().add(new THREE.Vector3(0, 1.0, 0)).project(camera), r = canvas.getBoundingClientRect();
    return [r.left + ((v.x + 1) / 2) * r.width, r.top + ((1 - v.y) / 2) * r.height];
  },
  // the arm turns the camera back to the usual direction, as a drag would (to see the faint walls)
  focusSet: (o) => { if ('az' in o) FOCUS.az = o.az; if ('el' in o) FOCUS.el = o.el; if ('dist' in o) FOCUS.dist = o.dist; return { az: FOCUS.az, el: FOCUS.el }; },
  focusBase: () => ({ ...FOCUS_BASE }),
  // the camera put at its pose for FOCUS now, as the follow (a lerp a frame) would end up: the arm's specimen search reads
  // the faint meshes of exact directions, not of wherever the follow had got to (frame-rate dependent: focus-cam flake, 10-19)
  focusSnap: () => {
    const R = rbState.id ? robots.find((x) => x.def.id === rbState.id) : null;
    if (!R || camTween || !zoom.zoomed) return false;
    const pose = focusPose(R, FOCUS.az, FOCUS.el, FOCUS.dist);
    camera.position.copy(pose.p); viewTarget.copy(pose.t); camera.lookAt(viewTarget);
    return true;
  },
  // how far the camera is from its pose for FOCUS now (0 once the follow has arrived)
  focusAt: () => { const R = rbState.id ? robots.find((x) => x.def.id === rbState.id) : null; return R ? camera.position.distanceTo(focusPose(R, FOCUS.az, FOCUS.el, FOCUS.dist).p) : null; },
  // the faint meshes: whether still in the scene, their room, whether their own material is a shared one; and a mark
  // on each own material's dispose (the arm sees whether taking a room down disposes it)
  fadedInfo: () => (liveShared(), [...FOCUS.faded.entries()]).map(([o, mat]) => {
    let inScene = false; for (let x = o; x; x = x.parent) if (x === scene) inScene = true;
    const room = Object.keys(LIVE3D.rooms).find((id) => { let hit = false; LIVE3D.rooms[id].group.traverse((c) => { if (c === o) hit = true; }); return hit; }) || null;
    // exclusive: no other mesh in the scene uses its own material — the only case taking the room down could leak it
    const own = [].concat(mat); let others = 0;
    scene.traverse((c) => { if (c !== o && c.material && [].concat(c.material).some((m) => own.includes(m))) others += 1; });
    return { uuid: o.uuid, inScene, room, shared: own.some((m) => LIVE3D.sharedMat.has(m)), exclusive: others === 0 };
  }),
  markOwnMaterials: () => {
    window.__disposed = window.__disposed || {};
    return [...FOCUS.faded.entries()].map(([o, mat]) => {
      for (const m of [].concat(mat)) { const d = m.dispose.bind(m); m.dispose = () => { window.__disposed[o.uuid] = (window.__disposed[o.uuid] || 0) + 1; d(); }; }
      return o.uuid;
    });
  },
  disposedMarks: () => ({ ...(window.__disposed || {}) }),
  inScene: (uuid) => !!scene.getObjectByProperty('uuid', uuid),
  projectPath: (id) => (PROJECT[id] ? PROJECT[id].path : null),
  // what a robot's view would cross from the usual direction (the arm looks for a robot the usual view cannot see)
  usualBlockers: (id) => { const R = robots.find((x) => x.def.id === id); return R ? focusBlockers(R, focusPose(R, FOCUS_BASE.az, FOCUS_BASE.el, 8).p).size : -1; },
  renderInfo: () => (renderer ? { calls: renderer.info.render.calls, triangles: renderer.info.render.triangles, geometries: renderer.info.memory.geometries, textures: renderer.info.memory.textures } : null),
  setSim: SOURCE.mode === 'demo' ? (v) => { simT = v; prevSim = v - 0.001; } : (v) => SOURCE.setReplaySpeed(v),
};
// the prompt box's waits (55-history.js): an arm shortens 「届いていない」 instead of waiting a minute
window.__dbg.promptWait = PROMPT_WAIT;
// Settled, for the e2e's waits (tools/viz_e2e/waits.py, 2.3.5): what animates per frame — a pose blending into the
// next (0.4 s of capped frame time), a robot walking, a tag easing up — read only when it has arrived, never sampled
// on the wall clock. ids: robot labels (all robots when omitted). A robot is settled when its pose has finished
// blending, it has no path left and is not leaving, and its tag stands where it was going.
window.__dbg.settleInfo = (ids) => robots.filter((R) => !ids || ids.includes(R.def.id)).map((R) => ({
  id: R.def.id, state: R.robot.state, blend: +R.robot.blend.toFixed(3), path: (R.path || []).length, leaving: !!(typeof LIVE !== 'undefined' && LIVE.leaving[R.def.id]),
  tag: R.tagTarget === undefined || R.tag.style.visibility === 'hidden' ? null : +(R.tagDy - R.tagTarget).toFixed(2),
  out: !!R.out, exitIn: R.exitAt ? Math.round(R.exitAt - performance.now()) : null,
  // ms from the page learning it left (LIVE.leaving's since) to its walk out (exitAt): 2500 when counted from the event
  exitAfter: R.exitAt && typeof LIVE !== 'undefined' && LIVE.leaving[R.def.id] && LIVE.leaving[R.def.id].since
    ? Math.round(R.exitAt - (performance.now() - (Date.now() - LIVE.leaving[R.def.id].since))) : null,
  leftAgo: typeof LIVE !== 'undefined' && LIVE.leaving[R.def.id] && LIVE.leaving[R.def.id].since ? Date.now() - LIVE.leaving[R.def.id].since : null }));
window.__dbg.settle = (ids) => window.__dbg.settleInfo(ids).every((x) => x.blend >= 1 && !x.path && !x.leaving && (x.tag === null || x.tag === 0));
// A gap between frames, as a hidden tab makes (rAF stops; minutes later it resumes): the next frame walks with `sec`
// more of real time (liveUpdateRobots' walkDt), and nothing else is touched.
window.__dbg.walkGap = (sec) => { LIVE3D.lastWalk -= sec * 1000; return true; };
// The walking speed now (m/s): liveWalk's WALK_SPEED, faster in a fast replay (the e2e's lower bound on a walk's time)
window.__dbg.walkSpeed = () => WALK_SPEED * (SOURCE.replaySpeed > 1 ? Math.min(4, SOURCE.replaySpeed) : 1);
// One call at the end of each frame's update of the robots (a recorder of what the frame did; null: none)
window.__dbg.afterFrame = (fn) => { LIVE3D.afterFrame = fn || null; return true; };
// Send robot `id` on foot from its room to the middle of room `to`, through the doors (liveRoute, as every walk goes):
// with walkGap, the whole route in one frame, around the doors' corners (rooms.py: the wall watcher follows the path)
window.__dbg.walkRoute = (id, to) => {
  const R = robots.find((x) => x.def.id === id), r = PROJECT[to];
  if (!R || !r) return null;
  const end = [(r.x0 + r.x1) / 2, (r.z0 + r.z1) / 2], p = R.robot.root.position;
  R.path = [...liveRoute(R.def.room, to), end];
  return { from: [p.x, p.z], to: end, points: R.path.length };
};
// how far the camera following a robot is from where it is going (0 once it has arrived)
window.__dbg.camFollowGap = () => (rbState.id && zoom.zoomed ? camera.position.distanceTo(robotPose(rbState.id).p) : null);
/* The wide history's camera (ticket 2026-10-20-jui-viz-wide-history-camera-jitters): a recorder of the camera and of where it is
   going (robotPose), every frame, to a list the arm reads; the fixed box it fits (FOCUS_BOX) and the robot's shown meshes in its
   own space (the widest corners over the frames recorded), to check that the box holds the pose. */
window.__dbg.camRecord = (id) => {
  const rec = window.__camRec = { frames: [], states: new Set(), env: null, rootY: [Infinity, -Infinity] };
  const inv = new THREE.Matrix4(), box = new THREE.Box3(), v = new THREE.Vector3();
  LIVE3D.afterFrame = () => {
    const R = robots.find((x) => x.def.id === id), root = R.robot.root, pose = robotPose(id);
    rec.frames.push([...camera.position.toArray(), ...viewTarget.toArray(), ...pose.p.toArray(), ...pose.t.toArray()]);
    rec.rootY[0] = Math.min(rec.rootY[0], root.position.y); rec.rootY[1] = Math.max(rec.rootY[1], root.position.y);
    rec.states.add(`${R.robot.state}|${!!R.robot.tired}|${!!(R.robot.sweat && R.robot.sweat.visible)}|${R.robot.look || ''}`);
    root.updateMatrixWorld(true);
    inv.copy(root.matrixWorld).invert();
    const e = rec.env || (rec.env = { x: [Infinity, -Infinity], y: [Infinity, -Infinity], z: [Infinity, -Infinity] });
    root.traverse((o) => {
      if (!o.isMesh || !shownChain(o)) return;
      box.setFromObject(o);
      for (let i = 0; i < 8; i++) {
        v.set(i & 1 ? box.max.x : box.min.x, i & 2 ? box.max.y : box.min.y, i & 4 ? box.max.z : box.min.z).applyMatrix4(inv);
        for (const k of ['x', 'y', 'z']) { e[k][0] = Math.min(e[k][0], v[k]); e[k][1] = Math.max(e[k][1], v[k]); }
      }
    });
  };
  return true;
};
window.__dbg.camRecorded = () => { const r = window.__camRec; return r ? { frames: r.frames, states: [...r.states], env: r.env, rootY: r.rootY } : null; };
// the fixed box's width as focusExtent gives it for the focused robot, at the camera's turn and distance now (before a back-off),
// with what the arm needs to work it out on its own: the robot's size and turn, the camera's direction and right
window.__dbg.focusFit = () => {
  const R = rbState.id ? robots.find((x) => x.def.id === rbState.id) : null;
  if (!R) return null;
  const dir = focusDir(FOCUS.az, FOCUS.el), right = new THREE.Vector3().crossVectors(dir.clone().negate(), new THREE.Vector3(0, 1, 0)).normalize();
  const e = focusExtent(R, right, dir, FOCUS.dist);
  return { id: R.def.id, size: R.robot.size || 1, l: e.l, r: e.r, dist: FOCUS.dist, dir: dir.toArray(), right: right.toArray(), quat: R.robot.root.quaternion.toArray() };
};
window.__dbg.focusBox = () => JSON.parse(JSON.stringify(FOCUS_BOX));
// background work (2.3.5): the headset, the notes and the laptop of each robot; and a pose's keystroke, sampled
window.__dbg.bgLook = () => robots.map((R) => {
  const r = R.robot, notes = r.notes ? r.notes.children : [], lap = r.props.background;
  return { id: R.def.id, state: r.state, kind: R.def.kind, headset: !!(r.headset && r.headset.visible && r.headset.parent),
    noteSprites: notes.length, notes: r.notes && r.notes.visible ? notes.map((n) => [+n.position.x.toFixed(3), +n.position.y.toFixed(3), +n.material.opacity.toFixed(2)]) : [],
    laptop: !!(lap && lap.group.visible), armL: +r.armL.rotation.x.toFixed(4), play: !!R.play, brk: !!R.brk, solo: !!R.solo,
    call: r.call ? `${r.call.role}:${r.call.state}` : null, onLine: !!(r.call && CALL_ON_LINE.has(r.call.state) && !(r.call.role === 'callee' && (r.call.state === 'ringing' || r.call.state === 'dialing'))),
    handset: !!r.handset };
});
// the notes' places at two pose times (still under reduced motion, rising otherwise): read without sampling frames
window.__dbg.notesAt = (id, times) => { const R = robots.find((x) => x.def.id === id); return times.map((t) => [0, 1, 2].map((k) => { const n = notePose(R.robot, k, t); return [+n.x.toFixed(3), +n.y.toFixed(3)]; })); };
// a robot that went to a game, a nap, a bento or a break, from now on, every frame (the arm reads it when it is done)
window.__dbg.watchOuting = (ids) => { const seen = Object.fromEntries(ids.map((i) => [i, false])); window.__outing = seen;
  const tick = () => { for (const R of robots) if (R.def.id in seen && (R.play || R.brk || R.solo)) seen[R.def.id] = true; if (window.__outing === seen) requestAnimationFrame(tick); };
  requestAnimationFrame(tick); return true; };
window.__dbg.poseStats = (state) => {   // the left arm over 20 s of pose time: its swing and how many strokes a second
  let lo = Infinity, hi = -Infinity, strokes = 0, prev = null;
  for (let i = 0; i <= 4000; i++) {
    const s = i * 0.005, a = poseFor(state, s).aLx;
    lo = Math.min(lo, a); hi = Math.max(hi, a);
    const up = prev !== null && a > prev; if (up && prev !== null && !window.__dbgRising) strokes += 1; window.__dbgRising = up; prev = a;
  }
  window.__dbgRising = false;
  return { swing: +(hi - lo).toFixed(4), strokesPerSec: +(strokes / 20).toFixed(2) };
};
// a subagent's work clothes and size (2.3.5): what each robot wears, its height as drawn, where its tag hangs
window.__dbg.wear = () => robots.map((R) => {
  const r = R.robot, T = THREE, box = new T.Box3(), b = new T.Box3();
  r.hips.updateWorldMatrix(true, true);
  r.hips.traverse((o) => {
    if (!o.isMesh) return;
    for (let x = o; x && x !== r.hips; x = x.parent) if (!x.visible) return;
    o.geometry.computeBoundingBox(); b.copy(o.geometry.boundingBox).applyMatrix4(o.matrixWorld); box.union(b);
  });
  const hex = (m) => (m && m.color ? '#' + m.color.getHexString() : null);
  const w = r.wear || {}, hand = r.armL.children.find((c) => c.geometry === S.geo.hand), deskTop = r.desk ? r.desk.children[0] : null;
  return { id: R.def.id, kind: R.def.kind || 'main', role: R.def.role, size: +r.root.scale.x.toFixed(3), cap: !!w.cap, patch: w.fill ? hex(w.fill.material) : null,
    patchEdge: w.patch ? hex(w.patch.children[0].material) : null, body: hex(r.torso.children[0].material), roleColor: ROLES[R.def.role].color,
    height: +(box.max.y - box.min.y).toFixed(3), top: +box.max.y.toFixed(3), bottom: +box.min.y.toFixed(3), rootY: +r.root.position.y.toFixed(3),
    tagY: +(r.root.position.y + TAG_UP.y * (r.size || 1)).toFixed(3),
    handY: hand ? +hand.getWorldPosition(new T.Vector3()).y.toFixed(3) : null, deskY: deskTop ? +deskTop.getWorldPosition(new T.Vector3()).y.toFixed(3) : null,
    torso: r.torso.children[0].getWorldPosition(new T.Vector3()).toArray().map((v) => +v.toFixed(3)) };
});
// the headset over the work cap, in the head's own space: the band's top against the crown's, the cups against its sides
window.__dbg.wearFit = (id) => {
  const R = robots.find((x) => x.def.id === id), r = R && R.robot;
  if (!r || !r.wear || !r.wear.crown) return null;
  if (!r.headset) bgGear(r);
  const bb = (mesh) => { mesh.updateMatrix(); mesh.geometry.computeBoundingBox(); return mesh.geometry.boundingBox.clone().applyMatrix4(mesh.matrix); };
  const crown = bb(r.wear.crown), parts = r.headset.children.map(bb);
  const arc = parts[0], cups = parts.slice(1, 5);
  return { crownTop: +crown.max.y.toFixed(3), arcTop: +arc.max.y.toFixed(3), crownHalfW: +crown.max.x.toFixed(3),
    cupInnerX: +Math.min(...cups.map((c) => Math.min(Math.abs(c.min.x), Math.abs(c.max.x)))).toFixed(3),
    overlapCrownCups: cups.some((c) => c.intersectsBox(crown)) };
};
window.__dbg.setVisState = (id, state) => { robotState[id] = { ...(robotState[id] || {}), state }; };
window.__dbg.wearColors = () => ({ main: ROLES.main.color, overall: WEAR.overall, edge: WEAR.edge, rim: WEAR.rim, roles: Object.fromEntries(Object.entries(ROLES).map(([k, v]) => [k, v.color])) });
// トーク (2.3.6, 58-talk.js): its state, the requests it sent and refused, and in the demo the stand-in server's hands
window.__dbg.talk = () => ({ on: TALK.on, owner: TALK.owner, agent: TALK.agent, opened: TALK.opened, conv: TALK.conv, atEnd: TALK.atEnd, newer: TALK.newer,
  list: TALK.list ? TALK.list.map((c) => ({ id: c.id, name: c.peer.name, unread: c.unread, alive: c.peer.alive, agentId: c.peer.agentId })) : null,
  msgs: TALK.conv && TALK.msgs.get(TALK.conv) ? TALK.msgs.get(TALK.conv).items.length : 0, more: TALK.conv && TALK.msgs.get(TALK.conv) ? TALK.msgs.get(TALK.conv).more : null,
  badges: { ...TALK.badges }, sent: TALK.sent.map((f) => ({ ...f })), refused: TALK.refused.length });
window.__dbg.talkFrame = (type, fields) => talkFrame(type, fields);
window.__dbg.talkDemo = SOURCE.talkDemo || null;
window.__dbg.talkAgentId = (label) => SOURCE.talkAgentId(label);
window.__dbg.talkPage = (n) => { TALK.page = n; };   // a smaller page, so paging shows on a short talk
// every role's pill as drawn (2.3.6, ticket 2026-10-20-jui-viz-main-pill-text-contrast): pill() in the page with its CSS
// (the computed background and text), and drawRolePill on a canvas (a pixel of the background, and the text's colour:
// the commonest opaque colour other than the background, a large glyph so its inside is solid)
window.__dbg.rolePills = () => {
  const box = document.createElement('div');
  box.style.cssText = 'position:absolute;left:-9999px;top:0';
  box.innerHTML = Object.keys(ROLES).map((r) => pill(r, r)).join('');
  document.body.append(box);
  const html = Object.fromEntries([...box.children].map((p) => [p.textContent, { bg: getComputedStyle(p).backgroundColor, fg: getComputedStyle(p).color }]));
  box.remove();
  const W = 240, H = 120, cv = makeCanvas(W, H), ctx = cv.getContext('2d', { willReadFrequently: true });
  const hx = (d, i) => '#' + [d[i], d[i + 1], d[i + 2]].map((v) => v.toString(16).padStart(2, '0')).join('');
  const canvas = Object.fromEntries(Object.keys(ROLES).map((r) => {
    ctx.clearRect(0, 0, W, H);
    drawRolePill(ctx, r, 'M', 0, 0, W, H, 96, 100);
    const d = ctx.getImageData(0, 0, W, H).data, bg = hx(d, ((H >> 1) * W + 30) * 4), n = {};
    for (let i = 0; i < d.length; i += 4) if (d[i + 3] === 255) { const c = hx(d, i); if (c !== bg) n[c] = (n[c] || 0) + 1; }
    const fg = Object.entries(n).sort((a, b) => b[1] - a[1])[0];
    return [r, { bg, fg: fg ? fg[0] : null }];
  }));
  return { html, canvas, body: Object.fromEntries(Object.entries(ROLES).map(([k, v]) => [k, v.color])) };
};
// reading the web (10-20): the dictionary on the desk of each robot, read from the robot itself: shown (it and every
// parent visible, in the scene), the held book, each page's turn (radians, 0 on the right block, π on the left one)
// and whether it is drawn; dictAt: the pages' turns at pose times (still under reduced motion, turning otherwise)
window.__dbg.webLook = () => robots.map((R) => {
  const r = R.robot, d = r.dict, book = r.props.reading;
  let shown = !!d; for (let x = d ? d.book : null; x; x = x.parent) { if (!x.visible) shown = false; if (!x.parent && x !== scene) shown = false; }
  return { id: R.def.id, kind: R.def.kind, state: r.state, readKind: r.readKind || null, dict: shown, book: !!(book && book.group.visible),
    pages: d ? d.pages.map((h) => +(-h.rotation.z).toFixed(3)) : [], pagesShown: d ? d.pages.filter((h) => h.visible).length : 0,
    armRz: +r.armR.rotation.z.toFixed(4), look: r.look || null, headset: !!(r.headset && r.headset.visible), reduced: reduceMotion,
    play: !!R.play, brk: !!R.brk, solo: !!R.solo, walking: R.path.length > 0 };
});
window.__dbg.dictAt = (times) => times.map((s) => [...Array(DICT_PAGES).keys()].map((k) => +(Math.PI * dictFlip(s, k)).toFixed(3)));
// a mark on the dispose of each geometry and material of a robot's dictionary that is its own (the arm sees whether
// taking the robot down disposes them); returns how many were marked
window.__dbg.markDict = (id) => {
  const R = robots.find((x) => x.def.id === id), d = R && R.robot.dict;
  if (!d) return 0;
  window.__disposed = window.__disposed || {};
  liveShared();
  const seen = new Set();
  d.book.traverse((o) => {
    const own = [o.geometry, ...[].concat(o.material || [])].filter((x) => x && !seen.has(x) && !LIVE3D.sharedGeo.has(x) && !LIVE3D.sharedMat.has(x));
    for (const x of own) { seen.add(x); const key = `dict:${x.uuid}`, f = x.dispose.bind(x); window.__disposed[key] = 0; x.dispose = () => { window.__disposed[key] += 1; f(); }; }
  });
  return seen.size;
};
// calling a subagent (10-20): the whistle of each robot read from the robot itself, and the script's time (demo)
window.__dbg.launchLook = () => ({ t: latestModel ? +latestModel.t.toFixed(3) : null, now: vizNow(), robots: robots.map((R) => {
  const r = R.robot;
  return { id: R.def.id, state: r.state, launch: !!r.launch, whistle: !!(r.whistle && r.whistle.visible), pipi: !!(r.pipi && r.pipi.visible),
    pipiLong: !!(r.pipiLong && r.pipiLong.visible), look: r.look || null, face: String(r.faceMode).split('|')[0], sweat: !!(r.sweat && r.sweat.visible),
    armRz: +r.armR.rotation.z.toFixed(3), reduced: reduceMotion, until: (robotState[R.def.id] || {}).whistle ? robotState[R.def.id].whistle.until : null };
}) });
window.__dbg.launchBeats = () => (typeof DEMO_BEATS !== 'undefined' && DEMO_BEATS.launch ? { beats: DEMO_BEATS.launch, sec: DEMO_BEATS.launchSec } : null);
// the other surfaces with text on a role's colour (2.3.7, ticket 2026-10-20-jui-viz-talk-pill-contrast-and-version-comments):
// the talk's marks (each peer's pill in the list and the header, with the role of its robot), and the phones' headers,
// drawn per role by each drawer this page has (drawPhoneUI; drawCartUI in the demo; drawLivePhone in the live view) on
// a stand-in robot: a pixel of the header clear of the text, and the commonest opaque colour other than it (the clock
// and the battery are drawn in the text's colour)
window.__dbg.talkMarks = () => [...document.querySelectorAll('#rb .talk-mark .pill')].map((p) => ({ label: p.textContent,
  role: DEF[p.textContent] ? DEF[p.textContent].role : null, where: p.closest('.talk-row') ? 'row' : 'head',
  bg: getComputedStyle(p).backgroundColor, fg: getComputedStyle(p).color }));
window.__dbg.phoneHeads = () => {
  const hx = (d, i) => '#' + [d[i], d[i + 1], d[i + 2]].map((v) => v.toString(16).padStart(2, '0')).join('');
  const drawers = { phoneUI: drawPhoneUI };
  if (SOURCE.mode === 'demo') drawers.cart = drawCartUI; else drawers.live = drawLivePhone;
  const out = {};
  for (const [name, draw] of Object.entries(drawers)) {
    out[name] = {};
    for (const role of Object.keys(ROLES)) {
      const r = { role, label: '__probe', phoneCanvas: makeCanvas(240, 400), phoneTex: {}, phoneScreenTex: {} };
      try { draw(r, 0); } catch (e) { out[name][role] = { error: String(e) }; continue; }
      const d = r.phoneCanvas.getContext('2d', { willReadFrequently: true }).getImageData(24, 24, 192, 44).data, bg = hx(d, (40 * 192 + 186) * 4), n = {};
      for (let i = 0; i < d.length; i += 4) if (d[i + 3] === 255) { const c = hx(d, i); if (c !== bg) n[c] = (n[c] || 0) + 1; }
      const fg = Object.entries(n).sort((a, b) => b[1] - a[1])[0];
      out[name][role] = { bg, fg: fg ? fg[0] : null };
    }
  }
  return out;
};
