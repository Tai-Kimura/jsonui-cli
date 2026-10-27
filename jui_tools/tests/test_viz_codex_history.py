"""Codex prompts acknowledged by the daemon and bounded, on-demand rollout history."""
import asyncio
import json
from types import SimpleNamespace


from jui_cli.viz.ingest import World
from jui_cli.viz.sources import codex_history, history
from jui_cli.viz.sources.codex_app_server import CodexLink, Translator
from jui_cli.viz.state import VizState

SID = '01a1750c-564e-7711-ac44-2de86897a988'


def record(kind, **payload):
    return {'type': 'response_item', 'timestamp': '2026-10-27T01:00:00Z', 'payload': {'type': kind, **payload}}


def message(role, text):
    return record('message', role=role, content=[{'type': 'input_text' if role == 'user' else 'output_text', 'text': text}])


def rollout(home, records):
    p = home / 'sessions/2026/10/27/rollout.jsonl'
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in records))
    return p


def test_conversation_tools_and_no_duplicate_event_or_private_reasoning(tmp_path):
    p = rollout(tmp_path, [
        {'type': 'session_meta', 'payload': {'base_instructions': 'SECRET'}},
        message('developer', 'SECRET'), message('user', 'hello <script>'),
        {'type': 'event_msg', 'payload': {'type': 'user_message', 'message': 'hello <script>'}},
        record('reasoning', summary=[{'text': 'SECRET'}], encrypted_content='SECRET'),
        record('function_call', name='exec_command', call_id='call-1', arguments='{"cmd":"pwd"}'),
        record('function_call_output', call_id='call-1', output='result'),
        record('custom_tool_call', name='apply_patch', call_id='call-2', input='patch'),
        record('custom_tool_call_output', call_id='call-2', output='done'),
        message('assistant', '**finished**'),
        {'type': 'event_msg', 'payload': {'type': 'agent_message', 'message': '**finished**'}},
    ])
    got = codex_history.read(tmp_path, str(p))
    assert [i['kind'] for i in got['items']] == ['user', 'tool', 'tool', 'assistant']
    assert got['items'][1]['out'] == 'result'
    assert got['items'][2]['out'] == 'done'
    assert 'SECRET' not in json.dumps(got)
    assert got['items'][0]['at'] == 1793062800000


def test_older_pages_and_polling_join_results_across_pages(tmp_path):
    records = [message('user', 'oldest'), record('function_call', call_id='c', name='exec', arguments='{}')]
    records += [message('assistant', str(i)) for i in range(50)]
    records += [record('function_call_output', call_id='c', output='finished')]
    p = rollout(tmp_path, records)
    tail = codex_history.read(tmp_path, str(p))
    assert len(tail['items']) == history.ITEMS_MAX and tail['more']
    assert tail['results']['c']['out'] == 'finished'
    older = codex_history.read(tmp_path, str(p), end=tail['from'])
    assert older['items'][0]['text'] == 'oldest'
    assert len(older['items']) + len(tail['items']) == 52
    latest = codex_history.read(tmp_path, str(p), stop=tail['from'])
    assert latest['items'] == tail['items']


def test_large_malformed_records_and_tool_output_are_bounded(tmp_path):
    p = rollout(tmp_path, [message('user', 'x' * 10000), record('function_call', name='x', call_id='c', arguments='a' * 2000),
                           record('function_call_output', call_id='c', output='b' * 3000)])
    with p.open('ab') as f:
        f.write(b'{broken}\n[]\n' + b'x' * (history.LINE_MAX + 1) + b'\n')
    got = codex_history.read(tmp_path, str(p))
    assert got['bytes'] <= history.BYTES_MAX and got['bad'] == 1
    assert len(got['items'][0]['text']) == history.TEXT_MAX and got['items'][0]['cut']
    assert len(got['items'][1]['out']) == history.IO_MAX and got['items'][1]['outCut']


def test_only_regular_rollouts_inside_the_daemons_home(tmp_path):
    p = rollout(tmp_path, [message('user', 'hello')])
    outside = tmp_path / 'outside.jsonl'
    outside.write_text(p.read_text())
    link = p.parent / 'link.jsonl'
    link.symlink_to(outside)
    assert codex_history.read(tmp_path, str(outside)) is None
    assert codex_history.read(tmp_path, str(link)) is None
    assert codex_history.read(tmp_path, str(p.parent)) is None
    assert codex_history.read(tmp_path, str(p), end=1)['items'] == []


def world():
    w = World(VizState())
    tr = Translator()
    w.apply_codex(tr.thread_seen({'id': SID, 'cwd': '/work/app'}), {}, 1)
    return w


def test_world_codex_capability_routes_prompt_and_history_without_a_claude_relay():
    async def run():
        w = world()
        sent = []
        async def send(sid, text):
            sent.append((sid, text))
        w.codex_prompt, w.codex_ready = send, lambda sid: sid == SID
        w.publish()
        assert w.state.slices['sessions'][0]['prompt'] is True
        assert w.state.slices['sessions'][0]['relay'] is False
        assert await w.submit_prompt(SID, 'hello', 3) is None
        assert sent == [(SID, 'hello')]
        assert any(e['kind'] == 'PromptSent' for e in w.state.events)
        w.codex_history = lambda aid, **kw: {'items': [message('user', aid)], **kw}
        assert w.history(SID, end=100)['end'] == 100
        w.codex_ready = lambda sid: False
        w.publish()
        assert not w.state.slices['sessions'][0]['prompt']
        assert (await w.submit_prompt(SID, 'not sent', 4))[0] == 409
        assert len(sent) == 1
    asyncio.run(run())


def test_link_waits_for_ack_and_steers_active_turn_without_changing_settings():
    async def run():
        link = CodexLink(None, lambda *a: None)
        link.tr.thread_seen({'id': SID})
        link._ws = SimpleNamespace(closed=False)
        calls = []
        async def call(method, params):
            calls.append((method, params))
            return {'turn': {'id': 't1'}} if method == 'turn/start' else {'turnId': 't1'}
        link._call = call
        assert await link.send_prompt(SID, 'first') is None
        link.tr.event('turn/started', {'threadId': SID, 'turn': {'id': 't1'}})
        assert await link.send_prompt(SID, 'second') is None
        assert calls == [('turn/start', {'threadId': SID, 'input': [{'type': 'text', 'text': 'first', 'text_elements': []}]}),
                         ('turn/steer', {'threadId': SID, 'expectedTurnId': 't1', 'input': [{'type': 'text', 'text': 'second', 'text_elements': []}]})]
        async def refused(*a):
            return None
        link._call = refused
        assert (await link.send_prompt(SID, 'refused'))[0] == 409
        async def timeout(*a):
            raise asyncio.TimeoutError
        link._call = timeout
        assert (await link.send_prompt(SID, 'uncertain'))[0] == 503
        assert not link._sending
        link._ws.closed = True
        assert not link.can_prompt(SID)
        assert (await link.send_prompt(SID, 'offline'))[0] == 409
    asyncio.run(run())


def test_http_prompt_and_websocket_history_use_the_same_codex_thread(tmp_path):
    from aiohttp import web
    from aiohttp.test_utils import TestClient, TestServer
    from jui_cli.viz.config import VizConfig
    from jui_cli.viz.server import ServerContext, make_app

    async def run():
        w = world()
        p = rollout(tmp_path, [message('user', 'earlier'), message('assistant', 'previous answer')])
        link = CodexLink(None, lambda *a: None, path=tmp_path / 'app-server-control/s.sock')
        link.tr.thread_seen({'id': SID})
        link.rollouts[SID] = str(p)
        received = []
        async def daemon_socket(request):
            ws = web.WebSocketResponse()
            await ws.prepare(request)
            async for frame in ws:
                call = json.loads(frame.data)
                received.append(call)
                text = call['params']['input'][0]['text']
                with p.open('a') as f:
                    f.write(json.dumps(message('user', text)) + '\n')
                    f.write(json.dumps(message('assistant', 'new answer')) + '\n')
                await ws.send_json({'id': call['id'], 'result': {'turn': {'id': 'new-turn', 'status': 'inProgress'}}})
            return ws
        app = web.Application()
        app.router.add_get('/', daemon_socket)
        async with TestClient(TestServer(app)) as daemon:
            link._ws = await daemon.ws_connect('/')
            reading = asyncio.create_task(link._read(link._ws))
            w.codex_prompt, w.codex_ready, w.codex_history = link.send_prompt, link.can_prompt, link.history
            import socket
            with socket.socket() as probe:
                probe.bind(('127.0.0.1', 0))
                port = probe.getsockname()[1]
            ctx = ServerContext(config=VizConfig(), port=port, token='test-token', state=w.state, world=w, publish=w.publish)
            async with TestClient(TestServer(make_app(ctx), host='127.0.0.1', port=port)) as page:
                ctx.port = page.port
                origin = f'http://127.0.0.1:{page.port}'
                headers = {'Origin': origin, 'X-Jui-Viz-Token': ctx.token}
                bad = await page.post('/api/prompt', json={'sessionId': SID, 'text': 'no'}, headers={**headers, 'Origin': 'https://other.test'})
                assert bad.status == 403 and not received
                ok = await page.post('/api/prompt', json={'sessionId': SID, 'text': 'from page'}, headers=headers)
                assert ok.status == 200 and (await ok.json())['ok']
                assert received[0]['method'] == 'turn/start'
                ws = await page.ws_connect('/ws', headers={'Origin': origin})
                await ws.receive_json()
                await ws.send_json({'type': 'auth', 'token': ctx.token})
                await ws.receive_json()
                snapshot = await ws.receive_json()
                assert 'previous answer' not in json.dumps(snapshot)
                await ws.send_json({'type': 'history.get', 'reqId': 'codex-history', 'agentId': SID})
                got = await ws.receive_json()
                assert got['type'] == 'history'
                assert [i['text'] for i in got['items']] == ['earlier', 'previous answer', 'from page', 'new answer']
                assert str(tmp_path) not in json.dumps(got)
                await ws.close()
            await link._ws.close()
            await reading
    asyncio.run(run())


def test_attaching_to_an_active_thread_seeds_the_running_turn_and_rollout(tmp_path):
    async def run():
        class Sink:
            def apply(self, *a):
                pass
        link = CodexLink(Sink(), lambda *a: None)
        p = rollout(tmp_path, [message('user', 'hi')])
        calls = []
        async def call(method, params):
            calls.append((method, params))
            if method == 'thread/loaded/list':
                return {'data': [SID]}
            if method == 'thread/resume':
                return {'thread': {'id': SID, 'path': str(p), 'status': {'type': 'active'}}}
            return {'data': [{'id': 'already-running', 'status': 'inProgress'}]}
        link._call = call
        await link._poll()
        assert link.tr.turns[SID] == 'already-running'
        assert link.rollouts[SID] == str(p)
        assert calls[-1] == ('thread/turns/list', {'threadId': SID, 'limit': 1, 'itemsView': 'notLoaded'})
    asyncio.run(run())


def test_no_false_sent_event_when_daemon_rejects_and_no_duplicate_submit():
    async def run():
        w = world()
        async def reject(*a):
            return 409, 'busy'
        w.codex_ready, w.codex_prompt = lambda sid: True, reject
        assert (await w.submit_prompt(SID, 'refused', 2))[0] == 409
        assert not any(e['kind'] == 'PromptSent' for e in w.state.events)
        link = CodexLink(None, lambda *a: None)
        link.tr.thread_seen({'id': SID})
        link._ws = SimpleNamespace(closed=False)
        entered, release = asyncio.Event(), asyncio.Event()
        async def waiting(*a):
            entered.set()
            await release.wait()
            return {'turn': {'id': 't'}}
        link._call = waiting
        task = asyncio.create_task(link.send_prompt(SID, 'first'))
        await entered.wait()
        assert (await link.send_prompt(SID, 'duplicate'))[0] == 429
        release.set()
        assert await task is None
    asyncio.run(run())
