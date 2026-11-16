"""Title + CLI/usage on the first row; all remaining controls on one desktop row, wrapping on phones."""
from pathlib import Path

from common import LAUNCH_ARGS, Watch, new_page, ready


async def run_header_rows(pw, out, failures, Server):
    out = Path(out) / 'header-rows'
    out.mkdir(parents=True, exist_ok=True)
    server = Server()
    browser = await pw.chromium.launch(args=LAUNCH_ARGS)
    try:
        watch = Watch(origin=server.url)
        page = await new_page(browser, watch, 'header-rows', viewport={'width': 1440, 'height': 1000})
        await page.goto(server.url + '/?demo=1')
        await ready(page)
        # Populate both limits and a busy header. Layout must not depend on either account supplying usage now.
        await page.evaluate('''() => {
          document.querySelector('#usage-cli').hidden = false;
          const u = document.querySelector('#usage'); u.hidden = false;
          for (const text of ['5時間 9%（あと 4:52）', '週 7%（あと 6日 1時間）']) {
            const chip = document.createElement('span'); chip.className='uw'; chip.textContent=text; u.append(chip);
          }
          for (const [id,text] of [['chip-sessions','セッション 6 / 29'],['chip-robots','ロボット 6 / 29'],
                                   ['chip-input','… 入力待ち 1'],['chip-askwait','質問は viz で 30分待つ']]) {
            const chip=document.getElementById(id);chip.hidden=false;chip.textContent=text;
          }
          const scope=document.getElementById('scope-top');
          scope.replaceChildren();const name=document.createElement('b');name.textContent='JsonUI-Agents-for-claude/';scope.append(name);
          document.getElementById('btn-play').hidden=true;document.getElementById('btn-speed').hidden=true;
          document.getElementById('btn-devices').hidden=false;document.getElementById('btn-notify').hidden=false;
        }''')
        for scheme in ('light', 'dark'):
            await page.emulate_media(color_scheme=scheme)
            for width in (2048, 1440, 390):
                await page.set_viewport_size({'width':width,'height':1000})
                boxes = await page.evaluate('''() => {
                  const box=(q)=>document.querySelector(q).getBoundingClientRect();
                  const menu=[...document.querySelectorAll('#scope-top,.topbar-menu .chips > *,.topbar-menu .controls > *')]
                    .filter(e=>e.offsetParent!==null).map(e=>{const b=e.getBoundingClientRect();return b.top+b.height/2;});
                  return {brandRight:box('.brand').right, cliLeft:box('#usage-cli').left,
                    titleBottom:box('.topbar-title').bottom,menuTop:box('.topbar-menu').top,
                    rowSpread:Math.max(...menu)-Math.min(...menu),sw:document.documentElement.scrollWidth};
                }''')
                if boxes['menuTop'] < boxes['titleBottom']:
                    failures.append(f'header-rows: title/menu overlap ({scheme}, {width}): {boxes}')
                if width >= 1440 and (boxes['cliLeft'] < boxes['brandRight'] or boxes['rowSpread'] > 5):
                    failures.append(f'header-rows: desktop controls wrap ({scheme}, {width}): {boxes}')
                if boxes['sw'] > width:
                    failures.append(f'header-rows: horizontal overflow ({scheme}, {width}): {boxes}')
                await page.screenshot(path=str(out/f'{scheme}-{width}.png'),clip={'x':0,'y':0,'width':width,'height':min(500,1000)})
        # Every button at once (ticket 2026-11-04-viz-en-phone-card-header-overflows-10px): wider than a phone in either
        # language (ja 438 px, en 520 px), so this holds whichever language the run is in. They wrap inside the page, keep
        # to the right, and none lies on another; on a desktop they stay on one line.
        await page.emulate_media(color_scheme='light')
        for width in (320, 360, 375, 390, 414, 480, 600, 768, 900, 1440):
            await page.set_viewport_size({'width':width,'height':1000})
            r = await page.evaluate('''() => {
              const btns=[...document.querySelectorAll('.controls button')];
              for (const b of btns) b.hidden=false;
              const boxes=btns.map(b=>b.getBoundingClientRect());
              const vw=document.documentElement.clientWidth;
              return {sw:document.documentElement.scrollWidth,vw,
                out:btns.filter((b,i)=>boxes[i].left<0||boxes[i].right>vw).map(b=>b.id),
                covered:btns.filter((b,i)=>{const hit=document.elementFromPoint(boxes[i].left+boxes[i].width/2,boxes[i].top+boxes[i].height/2);return hit!==b;}).map(b=>b.id),
                rows:new Set(boxes.map(b=>Math.round(b.top))).size,
                rightGap:vw-Math.max(...boxes.map(b=>b.right)),count:btns.length};
            }''')
            if r['sw'] > r['vw'] or r['out']:
                failures.append(f'header-rows: every button, sideways at {width}: {r}')
            if r['covered']:
                failures.append(f'header-rows: every button, one covered at {width}: {r}')
            if r['count'] != 6:
                failures.append(f'header-rows: every button, expected the six at {width}: {r}')
            if width <= 414 and r['rows'] < 2:
                failures.append(f'header-rows: every button, did not reach the wrap at {width}: {r}')
            if width >= 900 and r['rows'] != 1:
                failures.append(f'header-rows: every button, wrapped on a wide page at {width}: {r}')
            if not 15 <= r['rightGap'] <= 17:
                failures.append(f'header-rows: every button, not at the right at {width}: {r}')
            if width in (390, 1440):
                await page.screenshot(path=str(out/f'every-button-{width}.png'),clip={'x':0,'y':0,'width':width,'height':400})
        for error in [*watch.console, *watch.csp, *watch.foreign]:
            failures.append('header-rows: '+str(error))
    finally:
        await browser.close()
        server.stop()
