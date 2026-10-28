"""Messages cross transports, remain in both talks, and are never duplicated by retries/restarts."""
import asyncio
from types import SimpleNamespace

import pytest

from jui_cli.viz.messaging import Refused, Router
from jui_cli.viz.talk import TalkHub, TalkIndex, conv_id
from jui_cli.viz import talk_contract

A = '11111111-1111-4111-8111-111111111111'
B = '22222222-2222-4222-8222-222222222222'
C = '33333333-3333-4333-8333-333333333333'


def setup(tmp_path):
    sessions = {A: {'title': 'Claude', 'status': 'idle'},
                B: {'title': 'Codex', 'cli': 'codex', 'status': 'idle'},
                C: {'title': 'Local', 'cli': 'codex', 'modelProvider': 'lmstudio', 'status': 'idle'}}
    delivered = []
    async def submit(sid, text, at):
        delivered.append((sid, text))
        return None
    world = SimpleNamespace(sessions=sessions, prompt_refusal=lambda sid: None, submit_prompt=submit)
    hub = TalkHub(lambda: TalkIndex(tmp_path / 'talk.db', tmp_path / 'projects', tmp_path / 'sessions', registry=lambda: []),
                  sessions=lambda: sessions, agents=lambda: {sid: {} for sid in sessions})
    return world, hub, Router(world, hub), delivered


def test_both_directions_and_local_provider_share_persistent_talks(tmp_path):
    async def run():
        world, hub, router, delivered = setup(tmp_path)
        hub.watch[object()] = B
        try:
            for i, (sender, receiver) in enumerate([(A, B), (B, A), (B, C), (C, B)]):
                result = await router.send({'id': f'message-{i}', 'sender': sender, 'recipient': receiver, 'text': '日本語 <script>data</script>'})
                assert result['ok'] and result['state'] == 'sent'
                assert delivered[-1][0] == receiver
                assert sender in delivered[-1][1] and 'not a user instruction' in delivered[-1][1]
            for _, frame in hub.frames:
                assert not talk_contract.validate(frame), talk_contract.validate(frame)
            assert hub.badges[B] >= 1
            for sender, receiver, count in [(A, B, 2), (B, C, 2)]:
                cid = conv_id(sender, receiver)
                outgoing = await hub.run(lambda: hub._ensure().messages(sender, cid))
                incoming = await hub.run(lambda: hub._ensure().messages(receiver, cid))
                assert len(outgoing[0]) == len(incoming[0]) == count
                assert {m['dir'] for m in incoming[0]} == {'in', 'out'}
                for message in incoming[0]:
                    assert message['readAt'] is None and message['state'] == 'sent'
            # Codex is alive even though it has no ~/.claude/sessions entry.
            extra = [{'sessionId': sid, 'name': row['title']} for sid, row in world.sessions.items()]
            await hub.run(lambda: hub._ensure().step(2_000_000_000_000, extra))
            conv = await hub.run(lambda: hub._ensure().conversation(conv_id(A, B), A, 2_000_000_000_000))
            assert conv['peer']['alive']
        finally:
            hub.close()
    asyncio.run(run())


def test_concurrent_retry_and_restart_do_not_send_twice(tmp_path):
    async def run():
        world, hub, router, delivered = setup(tmp_path)
        body = {'id': 'same-message', 'sender': A, 'recipient': B, 'text': 'one message'}
        try:
            one, two = await asyncio.gather(router.send(body), router.send(body))
            assert one == two and len(delivered) == 1
            with pytest.raises(Refused, match='different content'):
                await router.send({**body, 'text': 'changed'})
        finally:
            hub.close()
        world, hub, router, delivered = setup(tmp_path)
        try:
            assert await router.send(body) == one
            assert not delivered
        finally:
            hub.close()
    asyncio.run(run())


def test_failures_are_visible_and_not_retried(tmp_path):
    async def run():
        world, hub, router, delivered = setup(tmp_path)
        async def refuse(*args):
            delivered.append(args)
            return 409, 'session is disconnected'
        world.submit_prompt = refuse
        body = {'id': 'failed-message', 'sender': A, 'recipient': C, 'text': 'hello'}
        try:
            result = await router.send(body)
            assert not result['ok'] and result['state'] == 'undelivered'
            assert await router.send(body) == result and len(delivered) == 1
            rows = await hub.run(lambda: hub._ensure().messages(C, conv_id(A, C)))
            assert rows[0][0]['state'] == 'undelivered'
        finally:
            hub.close()
    asyncio.run(run())


def test_ambiguous_ended_self_and_oversize_targets_are_refused(tmp_path):
    async def run():
        world, hub, router, delivered = setup(tmp_path)
        body = {'id': 'validation-id', 'sender': A, 'recipient': B, 'text': 'hello'}
        try:
            world.sessions[B]['title'] = world.sessions[C]['title'] = 'same'
            with pytest.raises(Refused, match='ambiguous'):
                await router.send({**body, 'recipient': 'same'})
            world.sessions[B]['status'] = 'ended'
            for bad in [{**body}, {**body, 'recipient': A}, {**body, 'text': 'x' * 20_001}, {**body, 'id': '../bad'}]:
                with pytest.raises(Refused):
                    await router.send(bad)
            assert not delivered
        finally:
            hub.close()
    asyncio.run(run())


def test_interrupted_delivery_stays_unknown_after_retry(tmp_path):
    async def run():
        world, hub, router, delivered = setup(tmp_path)
        entered = asyncio.Event()
        async def pause(*args):
            delivered.append(args)
            entered.set()
            await asyncio.Event().wait()
        world.submit_prompt = pause
        body = {'id': 'cancelled-id', 'sender': A, 'recipient': B, 'text': 'hello'}
        try:
            task = asyncio.create_task(router.send(body))
            await entered.wait()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            with pytest.raises(Refused, match='outcome unknown'):
                await router.send(body)
            assert len(delivered) == 1
        finally:
            hub.close()
    asyncio.run(run())


def test_real_world_routes_to_claude_queue_and_each_codex_link(tmp_path):
    from jui_cli.viz.ingest import World
    from jui_cli.viz.state import VizState
    from jui_cli.viz.sources.codex_app_server import CodexLink
    async def run():
        world = World(VizState())
        world.apply_hook({'hook_event_name': 'SessionStart', 'session_id': A, 'cwd': '/work'}, 1)
        channel = world.channel_hello(None, None, A, 2, ['prompt'], 'plugin')
        world.read_argv = lambda pid: ['claude', '--dangerously-load-development-channels', 'plugin:jui-viz@jsonui']
        world.apply_agents_list([{'sessionId': A, 'pid': 4242, 'cwd': '/work', 'entrypoint': 'cli'}], 2)
        links, calls = {}, []
        for sid in (B, C):
            link = CodexLink(None, lambda *a: None)
            link._ws = SimpleNamespace(closed=False)
            link.tr.thread_seen({'id': sid})
            async def call(method, params, sid=sid):
                calls.append((sid, method, params))
                return {'turn': {'id': 'turn-' + sid}}
            link._call = call
            links[sid] = link
            world.apply_codex([{'hook_event_name': 'SessionStart', 'session_id': sid, 'cwd': '/work'}], {}, 3)
        world.codex_ready = lambda sid: sid in links
        async def codex_prompt(sid, text):
            return await links[sid].send_prompt(sid, text)
        world.codex_prompt = codex_prompt
        hub = TalkHub(lambda: TalkIndex(tmp_path / 'talk.db', tmp_path / 'projects', tmp_path / 'sessions', registry=lambda: []),
                      sessions=lambda: world.sessions, agents=lambda: world.agents)
        router = Router(world, hub)
        try:
            for i, (sender, receiver) in enumerate([(A, B), (B, A), (B, C)]):
                assert (await router.send({'id': f'world-test-{i}', 'sender': sender, 'recipient': receiver, 'text': 'hello'}))['ok']
            assert [(sid, method) for sid, method, _ in calls] == [(B, 'turn/start'), (C, 'turn/start')]
            prompts = world.perms.take_prompts(channel)
            assert len(prompts) == 1 and B in prompts[0]['text']
            assert not world.perms.take_prompts(channel)
        finally:
            hub.close()
    asyncio.run(run())


def test_http_message_routes_require_same_origin_token_and_bounded_json(tmp_path):
    from jui_cli.viz import message_client
    from jui_tools.tests.test_viz_server import _ctx, _client, _host
    async def run():
        world, hub, router, delivered = setup(tmp_path)
        ctx = _ctx(world=world, talk=hub)
        client = await _client(ctx)
        headers = {**_host(ctx), 'Origin': f'http://127.0.0.1:{ctx.port}', 'X-Jui-Viz-Token': ctx.token}
        body = {'id': 'http-test-1', 'sender': A, 'recipient': B, 'text': 'hello'}
        try:
            for bad in [{**headers, 'Origin': 'https://other.example'}, {**headers, 'X-Jui-Viz-Token': 'wrong'}]:
                res = await client.post('/api/messages/send', json=body, headers=bad)
                assert res.status in (401, 403)
            res = await client.post('/api/messages/send', data='x' * 128_001, headers=headers)
            assert res.status in (413, 415)
            res = await client.post('/api/messages/peers', json={}, headers=headers)
            assert res.status == 200 and len((await res.json())['sessions']) == 3
            res = await client.post('/api/messages/send', json=body, headers=headers)
            assert res.status == 200 and (await res.json())['ok']
            res = await client.post('/api/messages/send', json=body, headers=headers)
            assert res.status == 200 and len(delivered) == 1
            original = message_client.read_server
            message_client.read_server = lambda: {'port': ctx.port, 'token': ctx.token}
            try:
                result = await asyncio.to_thread(message_client.request, 'send', body)
                assert result['ok'] and len(delivered) == 1
            finally:
                message_client.read_server = original
            res = await client.get('/api/messages/send', headers=headers)
            assert res.status == 405
        finally:
            await client.close()
            hub.close()
    asyncio.run(run())


def test_cli_finds_codex_or_claude_parent_and_reports_failures(monkeypatch, capsys):
    from jui_cli.viz import message_client as client
    monkeypatch.setenv('CODEX_THREAD_ID', B)
    assert client.own_session() == B
    monkeypatch.delenv('CODEX_THREAD_ID')
    monkeypatch.delenv('CLAUDE_SESSION_ID', raising=False)
    monkeypatch.setattr(client.os, 'getppid', lambda: 42)
    monkeypatch.setattr(client, 'session_id_of', lambda pid: A if pid == 43 else None)
    monkeypatch.setattr(client.subprocess, 'run', lambda *a, **kw: SimpleNamespace(stdout='43'))
    assert client.own_session() == A
    sent = []
    monkeypatch.setattr(client, 'request', lambda path, body: sent.append(body) or {'ok': True, 'id': body['id']})
    args = SimpleNamespace(viz_cmd='message', sender=None, recipient=C, text='hello', message_id='cli-retry-id')
    assert client.command(args) == 0
    assert sent == [{'id': 'cli-retry-id', 'sender': A, 'recipient': C, 'text': 'hello'}]
    assert 'cli-retry-id' in capsys.readouterr().out
    monkeypatch.setattr(client, 'request', lambda *a: {'ok': False, 'error': 'disconnected'})
    assert client.command(args) == 1
    def timeout(*args):
        raise TimeoutError('response lost')
    monkeypatch.setattr(client, 'request', timeout)
    monkeypatch.setattr(client.uuid, 'uuid4', lambda: 'network-retry-id')
    args.message_id = None
    assert client.command(args) == 1
    assert 'message id: network-retry-id' in capsys.readouterr().err


def test_rebuilding_transcript_index_preserves_relay_history_but_not_expired_bodies(tmp_path):
    async def run():
        world, hub, router, delivered = setup(tmp_path)
        try:
            await router.send({'id': 'rebuild-msg', 'sender': A, 'recipient': B, 'text': 'keep this relay'})
            await hub.run(lambda: hub._ensure().db.execute("UPDATE meta SET v='old' WHERE k='schema'"))
        finally:
            hub.close()
        world, hub, router, delivered = setup(tmp_path)
        try:
            rows = await hub.run(lambda: hub._ensure().messages(B, conv_id(A, B)))
            assert rows[0][0]['text'] == 'keep this relay'
            await hub.run(lambda: hub._ensure()._remove_session(A, 2_000_000_000_000))
        finally:
            hub.close()
        world, hub, router, delivered = setup(tmp_path)
        try:
            assert await hub.run(lambda: hub._ensure().messages(B, conv_id(A, B))) is None
        finally:
            hub.close()
    asyncio.run(run())


def test_browser_shows_cross_provider_messages_on_both_robot_cards(tmp_path):
    api = pytest.importorskip('playwright.async_api')
    from jui_cli.viz.ingest import World
    from jui_cli.viz.state import VizState
    from jui_tools.tests.test_viz_server import _ctx, _client, _host
    async def run():
        world = World(VizState())
        world.apply_hook({'hook_event_name': 'SessionStart', 'session_id': A, 'cwd': '/work/messaging'}, 1)
        world.apply_codex([{'hook_event_name': 'SessionStart', 'session_id': B, 'cwd': '/work/messaging'}], {B: 'Codex peer'}, 2)
        world.sessions[A]['title'] = 'Claude peer'
        world.agents[A]['title'] = 'Claude peer'
        world.prompt_refusal = lambda sid: None
        accepted = []
        async def submit(sid, text, at):
            accepted.append((sid, text))
        world.submit_prompt = submit
        world.publish()
        hub = TalkHub(lambda: TalkIndex(tmp_path / 'talk.db', tmp_path / 'projects', tmp_path / 'sessions', registry=lambda: []),
                      sessions=lambda: world.sessions, agents=lambda: world.agents)
        ctx = _ctx(world=world, talk=hub, publish=world.publish)
        ctx.state = world.state
        client = await _client(ctx)
        headers = {**_host(ctx), 'Origin': f'http://127.0.0.1:{ctx.port}', 'X-Jui-Viz-Token': ctx.token}
        errors = []
        try:
            for i, (sender, receiver) in enumerate([(A, B), (B, A)]):
                res = await client.post('/api/messages/send', headers=headers,
                    json={'id': f'browser-message-{i}', 'sender': sender, 'recipient': receiver, 'text': f'peer message {i} <script>literal</script>'})
                assert res.status == 200 and (await res.json())['ok']
            async def uncertain(*args):
                return 503, 'response lost'
            world.submit_prompt = uncertain
            res = await client.post('/api/messages/send', headers=headers,
                json={'id': 'browser-message-unknown', 'sender': A, 'recipient': B, 'text': 'uncertain attempt'})
            assert (await res.json())['state'] == 'unknown'
            async with api.async_playwright() as pw:
                try:
                    browser = await pw.chromium.launch(args=['--no-sandbox', '--use-angle=swiftshader', '--enable-unsafe-swiftshader'])
                except api.Error as exc:
                    if 'Executable doesn' in str(exc):
                        pytest.skip('Chromium is not installed')
                    raise
                try:
                    page = await browser.new_page(viewport={'width': 1440, 'height': 1000})
                    page.on('pageerror', lambda err: errors.append(str(err)))
                    await page.goto(str(client.make_url('/')))
                    await page.locator('.chip.demo[data-net="connected"]').wait_for(timeout=30000)
                    for name in ('Claude peer', 'Codex peer'):
                        await page.locator('#sessions [data-robot-open]').filter(has_text=name).first.click()
                        await api.expect(page.locator('#rb h2').first).to_have_text(name)
                        if await page.locator('#rb [data-rb-talk]').get_attribute('aria-pressed') != 'true':
                            await page.locator('#rb [data-rb-talk]').click()
                        await page.locator('#rb [data-tk-conv]').first.click()
                        await api.expect(page.locator('#rb [data-tk-msg]')).to_have_count(3)
                        await api.expect(page.locator('#rb [data-tk-state="unknown"]')).to_have_count(1)
                        assert (await page.locator('#rb [data-tk-state="unknown"]').inner_text()).strip()
                        assert 'peer message 0 <script>literal</script>' in await page.locator('#rb').inner_text()
                        assert 'peer message 1 <script>literal</script>' in await page.locator('#rb').inner_text()
                        assert not await page.locator('#rb script').count()
                        await page.screenshot(path=str(tmp_path / (name.split()[0] + '-talk.png')))
                    assert len(accepted) == 2 and not errors
                finally:
                    await browser.close()
        finally:
            await client.close()
            hub.close()
    asyncio.run(run())


def test_hub_keeps_codex_alive_without_resurrecting_an_absent_claude_session(tmp_path):
    import time
    async def run():
        world, hub, router, delivered = setup(tmp_path)
        try:
            await router.send({'id': 'live-state-id', 'sender': A, 'recipient': B, 'text': 'hello'})
            # World can retain a Claude robot after its session file disappeared. Its file remains authoritative.
            hub.tick(int(time.time() * 1000) + 10)
            await asyncio.wrap_future(hub._job)
            a = await hub.run(lambda: hub._ensure().conversation(conv_id(A, B), A, int(time.time() * 1000)))
            b = await hub.run(lambda: hub._ensure().conversation(conv_id(A, B), B, int(time.time() * 1000)))
            assert a['peer']['alive'] is True
            assert b['peer']['alive'] is False
        finally:
            hub.close()
    asyncio.run(run())


@pytest.mark.parametrize('exception', [True, False])
def test_timeout_and_uncertain_daemon_ack_stay_unknown_and_are_not_retried(tmp_path, exception):
    async def run():
        world, hub, router, delivered = setup(tmp_path)
        async def uncertain(*args):
            delivered.append(args)
            if exception:
                raise TimeoutError('response lost')
            return 503, 'delivery could not be confirmed'
        world.submit_prompt = uncertain
        hub.watch[object()] = A
        body = {'id': 'uncertain-id', 'sender': A, 'recipient': B, 'text': 'hello'}
        try:
            result = await router.send(body)
            assert result['state'] == 'unknown' and not result['ok']
            assert await router.send(body) == result and len(delivered) == 1
            for _, frame in hub.frames:
                assert not talk_contract.validate(frame)
            rows = await hub.run(lambda: hub._ensure().messages(A, conv_id(A, B)))
            assert rows[0][0]['state'] == 'unknown'
        finally:
            hub.close()
    asyncio.run(run())
