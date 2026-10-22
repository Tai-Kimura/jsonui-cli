"""The demo (`/?demo=1`) suites: the prototype's checks (reference/prototype/tests/*.js), made deterministic.

Each suite drives the same steps as its prototype script, with the demo script frozen at a fixed time, and
returns what it read from the page. run.py compares that with expect_demo.json, which was recorded by running
these same suites against the prototype page itself (`run.py --record-demo <url>`) — so a difference means the
port no longer behaves like the prototype.
"""

from __future__ import annotations

from common import DESKTOP, PHONE, board_point, freeze, gone, new_page, ready, robot_point, settle, shown, squash


async def shots(browser, url, watch, out):
    """shot4.js: 3D clicks, the spec board, the task board, the side panel toggle; dark; 390 px."""
    res = {}
    page = await new_page(browser, watch, "shots-light", **DESKTOP)
    await page.goto(url)
    await ready(page)
    await freeze(page, 27)
    await page.screenshot(path=f"{out}/s-main.png")
    res["panel"] = await page.evaluate("""() => ({
      filters: [...document.querySelectorAll('#spec-filter button')].map((b) => b.textContent),
      rows: [...document.querySelectorAll('#spec-list .spec-row')].map((b) => b.textContent.replace(/\\s+/g, ' ').trim()),
      taskSum: document.getElementById('task-sum').textContent })""")
    for name, which in (("tile-login", 1), ("board", "board"), ("tasks", "tasks")):
        x, y = await board_point(page, which)
        await page.mouse.click(x, y)
        el = "tb" if name == "tasks" else "wb"
        await shown(page, el)
        res[f"click_{name}"] = await page.evaluate("""() => ({ wb: !document.getElementById('wb').hidden,
          tb: !document.getElementById('tb').hidden, title: document.getElementById('wb-title').textContent })""")
        await page.screenshot(path=f"{out}/s-click-{name}.png")
        await page.keyboard.press("Escape")
        await gone(page, el)
        await settle(page)
    await page.click("#btn-specboard")
    await shown(page, "wb")
    await page.screenshot(path=f"{out}/s-overview.png")
    res["overview"] = await page.evaluate("""() => ({ cards: document.querySelectorAll('.ov-card').length,
      groups: [...document.querySelectorAll('.ov-group h3')].map((h) => h.textContent) })""")
    await page.click('.ov-card[data-idx="1"]')
    await page.wait_for_timeout(1200)
    await page.screenshot(path=f"{out}/s-login.png")
    res["login"] = await page.evaluate("""() => ({ title: document.getElementById('wb-title').textContent,
      empty: document.querySelectorAll('#wb-code .sc-empty').length, writing: document.querySelectorAll('#wb-code .sc-writing').length,
      act: (document.querySelector('#wb-code [data-act]') || {}).id || null, focus: document.activeElement.id })""")
    await page.click('#wb-side-list [data-idx="4"]')
    await page.wait_for_timeout(1200)
    await page.screenshot(path=f"{out}/s-home.png")
    res["home"] = await page.evaluate("""() => ({ nav: [...document.querySelectorAll('#wb-nav button')]
      .map((b) => `${b.className || '-'}:${b.textContent.trim()}`) })""")
    for idx, shot in (("8", "s-detail"), ("16", "s-order")):
        await page.click(f'#wb-side-list [data-idx="{idx}"]')
        await page.wait_for_timeout(1200)
        await page.screenshot(path=f"{out}/{shot}.png")
    await page.keyboard.press("Escape")
    await gone(page, "wb")
    await settle(page)
    await page.click("#btn-taskboard")
    await shown(page, "tb")
    await page.screenshot(path=f"{out}/s-tasks.png")
    await page.keyboard.press("Escape")
    await gone(page, "tb")
    await settle(page)
    await page.click("#btn-side")
    await page.wait_for_timeout(1500)
    await page.screenshot(path=f"{out}/s-wide.png")
    res["wideBtn"] = await page.evaluate("() => document.getElementById('btn-side').textContent")
    await page.close()

    page = await new_page(browser, watch, "shots-dark", color_scheme="dark", **DESKTOP)
    await page.goto(url)
    await ready(page)
    await freeze(page, 27)
    await page.screenshot(path=f"{out}/d-main.png")
    await page.click('#spec-list .spec-row[data-idx="1"]')
    await shown(page, "wb")
    await page.screenshot(path=f"{out}/d-login.png")
    await page.click('#wb-side-list [data-idx="-1"]')
    await page.wait_for_timeout(1200)
    await page.screenshot(path=f"{out}/d-overview.png")
    await page.keyboard.press("Escape")
    await gone(page, "wb")
    await settle(page)
    await page.click("#btn-taskboard")
    await shown(page, "tb")
    await page.screenshot(path=f"{out}/d-tasks.png")
    await page.close()

    page = await new_page(browser, watch, "shots-phone", **PHONE)
    await page.goto(url)
    await ready(page)
    await freeze(page, 27)
    res["phone"] = await page.evaluate("() => ({ sw: document.documentElement.scrollWidth })")
    await page.screenshot(path=f"{out}/p-main.png")
    await page.click('#spec-list .spec-row[data-idx="4"]')
    await shown(page, "wb")
    await page.screenshot(path=f"{out}/p-home.png")
    await page.click("#wb-side-btn")
    await page.wait_for_timeout(800)
    await page.screenshot(path=f"{out}/p-drawer.png")
    res["phoneDrawer"] = await page.evaluate("""() => ({ open: !document.getElementById('wb-body').classList.contains('side-closed'),
      pos: getComputedStyle(document.getElementById('wb-side')).position })""")
    await page.keyboard.press("Escape")
    await page.wait_for_timeout(500)
    res["phoneDrawerClosed"] = await page.evaluate("() => document.getElementById('wb-body').classList.contains('side-closed')")
    await page.keyboard.press("Escape")
    await gone(page, "wb")
    await settle(page)
    await page.click("#btn-taskboard")
    await shown(page, "tb")
    await page.screenshot(path=f"{out}/p-tasks.png")
    res["phoneTasks"] = await page.evaluate("""() => ({ sw: document.documentElement.scrollWidth,
      cols: getComputedStyle(document.getElementById('kanban')).gridTemplateColumns })""")
    await page.close()
    return res


# Checks of the port's own (not in expect_demo.json, which the prototype recorded): run.py adds these to its failures.
CHECKS: list[str] = []
# Each of the permission strip's buttons, hit at its centre: the button itself (or what is inside it) takes the pointer
# (ticket 2026-10-20-jui-viz-board-kanban-header-covers-perm-strip: the columns' headers lay over 拒否 in 2.3.5).
STRIP_HITS = """() => [...document.querySelectorAll('#perm-strip [data-do]')].filter((b) => b.offsetParent).map((b) => {
  const r = b.getBoundingClientRect(), x = r.left + r.width / 2, y = r.top + r.height / 2, hit = document.elementFromPoint(x, y);
  return { do: b.dataset.do, perm: b.dataset.perm, ok: !!hit && (hit === b || b.contains(hit)),
           hit: hit ? hit.tagName.toLowerCase() + (hit.className ? '.' + String(hit.className).split(' ')[0] : '') : null }; })"""


async def strip_hits(page, label):
    """Every strip button hit-testable, with the question strip as it is and with it absent (hidden for the check, in the
    same call, so no redraw comes in between)."""
    for absent in (False, True):
        got = await page.evaluate("""(absent) => { document.getElementById('perm-strip').scrollIntoView({ block: 'nearest' }); const q = document.getElementById('q-strip'), was = q.hidden;
          if (absent) q.hidden = true;
          const out = { q: !q.hidden, hits: (""" + STRIP_HITS + """)() };
          q.hidden = was; return out; }""", absent)
        bad = [h for h in got["hits"] if not h["ok"]]
        if not got["hits"] or bad or not {"allow", "deny"} <= {h["do"] for h in got["hits"]}:
            CHECKS.append(f"demo/perm/{label}: the permission strip's buttons are hit at their centre (question strip shown: {got['q']}): {bad or got['hits']}")


async def perm(browser, url, watch, out):
    """perm.js: permission chip, strip, notes, detail, always / deny, robot card from a 3D click; 390 px sheet."""
    res = {}
    for scheme in ("light", "dark"):
        page = await new_page(browser, watch, f"perm-{scheme}", color_scheme=scheme, **DESKTOP)
        await page.goto(url)
        await ready(page)
        await freeze(page, 27)
        R = {}
        R["side"] = await page.evaluate("""() => ({
          chip: document.getElementById('chip-perm').hidden ? null : document.getElementById('chip-perm').textContent,
          rows: [...document.querySelectorAll('#tasks > li')].slice(0, 3).map((li) => li.className + ' | ' + li.textContent.replace(/\\s+/g, ' ').slice(0, 90)),
          sum: document.getElementById('task-sum').textContent })""")
        if scheme == "light":
            await page.screenshot(path=f"{out}/q-side.png")
        await page.click("#chip-perm")
        await shown(page, "tb")
        R["board"] = await page.evaluate("""() => ({
          strip: [...document.querySelectorAll('#perm-strip .pcard')].map((c) => c.textContent.replace(/\\s+/g, ' ').slice(0, 80)),
          permNotes: [...document.querySelectorAll('#kanban .note.n-perm')].map((n) => n.querySelector('.n-subj').textContent) })""")
        await page.screenshot(path=f"{out}/q-board-{scheme}.png")
        await page.click("#tb-wide[aria-expanded='false']")   # the strips wide for their buttons, then folded again for the columns
        await strip_hits(page, f"board-{scheme}")
        await page.click("#tb-wide[aria-expanded='true']")
        await page.click("#kanban .note.n-perm .note-open")
        await page.wait_for_timeout(900)
        await page.screenshot(path=f"{out}/q-detail-{scheme}.png")
        R["detail"] = await page.evaluate("""() => ({ title: document.getElementById('tbd-title').textContent,
          perm: !!document.querySelector('#tb-detail .tbd-perm'), act: (document.querySelector('#tb-detail [data-live-act]') || {}).textContent,
          focus: document.activeElement.id })""")
        if scheme == "light":
            await page.click('#tb-detail [data-do="always"]')
            await page.wait_for_timeout(900)
            R["afterAlways"] = await page.evaluate("""() => ({ toast: document.getElementById('toast').textContent,
              hist: [...document.querySelectorAll('#tb-detail .tbd-list li')].map((l) => l.textContent).slice(0, 2),
              rules: (document.querySelector('#perm-strip .ps-rules') || {}).textContent, chip: document.getElementById('chip-perm').textContent,
              focus: document.activeElement.id || document.activeElement.className })""")
            await page.screenshot(path=f"{out}/q-after-always.png")
            await page.keyboard.press("Escape")
            await page.wait_for_timeout(400)
            R["detailClosed"] = await page.evaluate("""() => ({ hidden: document.getElementById('tb-detail').hidden,
              focus: document.activeElement.className })""")
            await page.click("#tb-wide[aria-expanded='false']")
            await page.click('#perm-strip [data-do="deny"]')
            await page.wait_for_timeout(900)
            R["afterDeny"] = await page.evaluate("""() => ({ chipHidden: document.getElementById('chip-perm').hidden,
              stripCards: document.querySelectorAll('#perm-strip .pcard').length,
              log: [...document.querySelectorAll('#ticker li')].slice(0, 2).map((l) => l.textContent) })""")
        if await page.evaluate("() => !document.getElementById('tb-detail').hidden"):
            await page.keyboard.press("Escape")
        await page.keyboard.press("Escape")
        await gone(page, "tb")
        await settle(page)
        x, y = await robot_point(page, "a3")
        await page.mouse.click(x, y)
        await shown(page, "rb")
        await page.wait_for_timeout(1500)
        await page.screenshot(path=f"{out}/q-robot-a3-{scheme}.png")
        R["robot"] = await page.evaluate("""() => ({ name: document.getElementById('rb-title').textContent,
          state: document.querySelector('[data-rb-state]').textContent, act: document.querySelector('[data-rb-act]').textContent,
          tasks: [...document.querySelectorAll('.rb-tasks li')].map((l) => l.textContent.replace(/\\s+/g, ' ')),
          spec: (document.querySelector('.rb-spec') || {}).textContent, recent: document.querySelectorAll('#rb [data-recent] li').length })""")
        if scheme == "light":
            await page.click('#sessions [data-robot-open="b4"]')
            await page.wait_for_timeout(2500)
            await page.screenshot(path=f"{out}/q-robot-b4.png")
            R["robotB4"] = await page.evaluate("""() => ({ name: document.getElementById('rb-title').textContent,
              tasks: document.querySelectorAll('.rb-tasks li').length,
              subs: [...document.querySelectorAll('.rb-subs li')].map((l) => l.textContent.replace(/\\s+/g, ' ').slice(0, 60)) })""")
            await page.click('.rb-tasks [data-open="b4#3"]')
            await shown(page, "tb")
            await page.wait_for_timeout(800)
            R["fromRobot"] = await page.evaluate("""() => ({ rbHidden: document.getElementById('rb').hidden,
              detail: document.getElementById('tbd-title').textContent })""")
            await page.keyboard.press("Escape")
            await page.keyboard.press("Escape")
            await gone(page, "tb")
        res[scheme] = R
        await page.close()
    page = await new_page(browser, watch, "perm-phone", **PHONE)
    await page.goto(url)
    await ready(page)
    await freeze(page, 27)
    await page.click('#sessions [data-robot-open="c9"]')
    await shown(page, "rb")
    await page.wait_for_timeout(1500)
    await page.screenshot(path=f"{out}/q-phone-robot.png")
    res["phone"] = await page.evaluate("""() => ({ sw: document.documentElement.scrollWidth,
      rbPos: getComputedStyle(document.getElementById('rb')).position, perm: !!document.querySelector('#rb .tbd-perm') })""")
    await page.keyboard.press("Escape")
    await gone(page, "rb")
    await page.close()
    return res


async def scope(browser, url, watch, out):
    """scope.js: the project switcher, a project's boards, the session and robot pickers, room labels, filters."""
    res = {}
    page = await new_page(browser, watch, "scope", **DESKTOP)
    await page.goto(url)
    await ready(page)
    await freeze(page, 31)
    await page.screenshot(path=f"{out}/s1-all.png")
    res["all"] = await page.evaluate("""() => ({
      scope: document.getElementById('scope-top').textContent, chips: [document.getElementById('chip-sessions').textContent, document.getElementById('chip-perm').textContent],
      groups: [...document.querySelectorAll('#sessions .pg-toggle')].map((b) => b.textContent), sessFilter: document.getElementById('sess-filter').textContent,
      specGroups: [...document.querySelectorAll('#spec-list .sl-group')].map((x) => x.textContent) })""")
    await page.click("#scope-top")
    await page.wait_for_timeout(400)
    await page.screenshot(path=f"{out}/s2-pop.png")
    res["pop"] = await page.evaluate("() => [...document.querySelectorAll('#pop [role=\"option\"]')].map((o) => o.textContent.replace(/\\s+/g, ' '))")
    for _ in range(3):
        await page.keyboard.press("ArrowDown")
    await page.keyboard.press("Enter")
    await page.wait_for_timeout(2500)
    await page.screenshot(path=f"{out}/s3-doc.png")
    res["doc"] = await page.evaluate("""() => ({
      scope: document.getElementById('scope-top').textContent, popHidden: document.getElementById('pop').hidden, focus: document.activeElement.id,
      chips: document.getElementById('chip-sessions').textContent, groups: [...document.querySelectorAll('#sessions .pg-toggle')].map((b) => b.textContent),
      specs: [...document.querySelectorAll('#spec-list .spec-row')].map((b) => b.textContent.replace(/\\s+/g, ' ')), tests: document.getElementById('tests').textContent,
      tasks: [...document.querySelectorAll('#tasks > li')].map((li) => li.textContent.replace(/\\s+/g, ' ').slice(0, 60)),
      ticker: [...document.querySelectorAll('#ticker li')].map((l) => l.textContent.slice(0, 40)) })""")
    await page.click("#btn-specboard")
    await shown(page, "wb")
    await page.screenshot(path=f"{out}/s4-doc-specs.png")
    res["docSpecs"] = await page.evaluate("""() => ({ title: document.getElementById('wb-title').textContent,
      cards: document.querySelectorAll('.ov-card').length, side: document.querySelectorAll('#wb-side-list .ws-item').length })""")
    await page.keyboard.press("Escape")
    await gone(page, "wb")
    await settle(page)
    await page.click("#btn-taskboard")
    await shown(page, "tb")
    await page.screenshot(path=f"{out}/s5-doc-tasks.png")
    res["docTasks"] = await page.evaluate("""() => ({ title: document.getElementById('tb-title').textContent,
      notes: document.querySelectorAll('#kanban .note').length, strip: document.getElementById('perm-strip').textContent.replace(/\\s+/g, ' ').slice(0, 200),
      sess: document.getElementById('tb-sess').textContent })""")
    await page.click("#tb-sess")
    await page.wait_for_timeout(400)
    await page.screenshot(path=f"{out}/s6-sess-pop.png")
    res["sessPop"] = await page.evaluate("() => [...document.querySelectorAll('#pop .pg-item')].map((x) => x.textContent.replace(/\\s+/g, ' '))")
    await page.click('#pop [data-pick-list="e1"]')
    await page.wait_for_timeout(400)
    res["afterUncheck"] = await page.evaluate("""() => ({ notes: document.querySelectorAll('#kanban .note').length,
      sess: document.getElementById('tb-sess').textContent, count: document.querySelector('#pop [data-pop-count]').textContent })""")
    await page.keyboard.press("Escape")
    await page.wait_for_timeout(300)
    res["popClosed"] = await page.evaluate("""() => ({ hidden: document.getElementById('pop').hidden,
      focus: document.activeElement.id, tbOpen: !document.getElementById('tb').hidden })""")
    await page.click("#perm-strip [data-set-all]")
    await page.wait_for_timeout(1200)
    await page.click("#tb-lanes")
    await page.wait_for_timeout(1000)
    await page.screenshot(path=f"{out}/s7-lanes.png")
    res["lanes"] = await page.evaluate("""() => ({ lanes: [...document.querySelectorAll('#kanban .lane .lane-head')].map((h) => h.textContent.replace(/\\s+/g, ' ')),
      stripCards: document.querySelectorAll('#perm-strip .pcard').length, sess: document.getElementById('tb-sess').textContent })""")
    await page.keyboard.press("Escape")
    await gone(page, "tb")
    await settle(page)
    await page.click("#btn-log")
    await page.wait_for_timeout(500)
    await page.click("#log-who")
    await page.wait_for_timeout(400)
    await page.screenshot(path=f"{out}/s8-log-pop.png")
    await page.click('#pop [data-pick-session="a0"]')
    await page.wait_for_timeout(400)
    res["log"] = await page.evaluate("""() => ({ who: document.getElementById('log-who').textContent,
      count: document.getElementById('log-count').textContent,
      rowsWithA0: [...document.querySelectorAll('#log-rows tr.ev td.who')].filter((td) => /\\ba[0357]\\b/.test(td.textContent)).length })""")
    await page.keyboard.press("Escape")
    await page.keyboard.press("Escape")
    await page.wait_for_timeout(500)
    await page.click('.tag.room[data-set-project="cli"]')
    await page.wait_for_timeout(2500)
    await page.screenshot(path=f"{out}/s9-cli.png")
    res["cli"] = await page.evaluate("""() => ({ scope: document.getElementById('scope-top').textContent,
      specs: document.getElementById('spec-list').textContent,
      tagOn: document.querySelector('.tag.room.on') && document.querySelector('.tag.room.on').textContent })""")
    await page.click("#scope-top")
    await page.wait_for_timeout(300)
    await page.click('#pop [data-pick-project="all"]')
    await page.wait_for_timeout(800)
    await page.click('#sess-filter [data-sf="waiting"]')
    await page.wait_for_timeout(400)
    res["waitingOnly"] = await page.evaluate("() => [...document.querySelectorAll('#sessions .session .srow')].map((x) => x.textContent.replace(/\\s+/g, ' '))")
    await page.click('#sess-filter [data-sf="all"]')
    await page.click('#sessions [data-fold="shop"]')
    await page.wait_for_timeout(400)
    res["folded"] = await page.evaluate("""() => ({ expanded: document.querySelector('#sessions [data-fold="shop"]').getAttribute('aria-expanded'),
      shopSessions: document.querySelectorAll('#sessions .pgroup:first-child .session').length })""")
    await page.click('#sessions [data-fold="shop"]')
    await page.close()
    dp = await new_page(browser, watch, "scope-phone-dark", color_scheme="dark", **PHONE)
    await dp.goto(url)
    await ready(dp)
    await freeze(dp, 31)
    await dp.click("#scope-top")
    await dp.wait_for_timeout(500)
    await dp.screenshot(path=f"{out}/s10-phone-pop.png")
    res["phone"] = await dp.evaluate("""() => { const r = document.getElementById('pop').getBoundingClientRect();
      return { left: r.left, right: r.right, sw: document.documentElement.scrollWidth }; }""")
    await dp.close()
    return res


async def waiting(browser, url, watch, out):
    """waiting.js: the "waiting for permission" session filter and the project picker's badges."""
    res = {}
    page = await new_page(browser, watch, "waiting", **DESKTOP)
    await page.goto(url)
    await ready(page)
    await freeze(page, 32)
    await page.wait_for_function("() => document.querySelector('#sess-filter [data-sf=\"waiting\"]').lastElementChild.textContent === '2'")
    res["chips"] = await page.evaluate("() => [...document.querySelectorAll('#sess-filter button')].map((b) => b.textContent)")
    await page.click('#sess-filter [data-sf="waiting"]')
    await page.wait_for_function("() => document.querySelectorAll('#sessions .session .srow').length === 2")
    res["waitingRows"] = await page.evaluate("() => [...document.querySelectorAll('#sessions .session .srow')].map((x) => x.textContent.replace(/\\s+/g, ' ').trim())")
    res["groupNotes"] = await page.evaluate("() => [...document.querySelectorAll('#sessions .empty-note')].map((x) => x.textContent)")
    await page.screenshot(path=f"{out}/w-waiting.png")
    await page.click('#sess-filter [data-sf="idle"]')
    await page.wait_for_timeout(1500)
    res["idleRows"] = await page.evaluate("() => [...document.querySelectorAll('#sessions .session .srow')].map((x) => x.textContent.replace(/\\s+/g, ' ').trim())")
    await page.click('#sess-filter [data-sf="all"]')
    await page.click("#scope-top")
    await page.wait_for_function("() => !document.getElementById('pop').hidden")
    await page.wait_for_timeout(600)
    res["pop"] = await page.evaluate("() => [...document.querySelectorAll('#pop [data-pick-project]')].map((x) => x.textContent.replace(/\\s+/g, ' ').trim())")
    await page.screenshot(path=f"{out}/w-pop.png")
    await page.close()
    return res


async def phone(browser, url, watch, out):
    """phone.js + phonepop.js: the task board's columns and the project picker at 390 px, light and dark."""
    res = {}
    for scheme in ("light", "dark"):
        page = await new_page(browser, watch, f"phone-{scheme}", color_scheme=scheme, **PHONE)
        await page.goto(url)
        await ready(page)
        await freeze(page, 27)
        await page.click('#spec-list .spec-row[data-idx="4"]')
        await shown(page, "wb")
        await page.keyboard.press("Escape")
        await gone(page, "wb")
        await settle(page)
        await page.click("#btn-taskboard")
        await shown(page, "tb")
        await page.screenshot(path=f"{out}/ph-tasks-{scheme}.png")
        res[f"tasks-{scheme}"] = await page.evaluate("""() => {
          const cols = [...document.querySelectorAll('.kcol')].map((c) => c.getBoundingClientRect());
          let overlap = false;
          for (let i = 1; i < cols.length; i++) if (cols[i].top < cols[i - 1].bottom - 1 && Math.abs(cols[i].left - cols[i - 1].left) < 5) overlap = true;
          const notesOut = [...document.querySelectorAll('.kcol')].some((c) => { const b = c.getBoundingClientRect(); return [...c.querySelectorAll('.note')].some((n) => n.getBoundingClientRect().bottom > b.bottom + 1); });
          return { overlap, notesOut, sw: document.documentElement.scrollWidth, kanbanScroll: document.getElementById('kanban').scrollHeight > document.getElementById('kanban').clientHeight }; }""")
        await page.keyboard.press("Escape")
        await gone(page, "tb")
        await settle(page)
        await page.click("#scope-top")
        await page.wait_for_function("() => !document.getElementById('pop').hidden")
        await page.wait_for_timeout(800)
        res[f"pop-{scheme}"] = await page.evaluate("""() => { const r = document.getElementById('pop').getBoundingClientRect();
          const rows = [...document.querySelectorAll('#pop .po-badges')].map((b) => ({ h: Math.round(b.getBoundingClientRect().height), over: b.scrollWidth > b.clientWidth }));
          return { left: Math.round(r.left), right: Math.round(r.right), sw: document.documentElement.scrollWidth, rows }; }""")
        await page.screenshot(path=f"{out}/ph-pop-{scheme}.png")
        await page.close()
    return res


SUITES = {"shots": shots, "perm": perm, "scope": scope, "waiting": waiting, "phone": phone}
