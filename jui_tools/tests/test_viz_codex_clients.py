"""Daemon membership survives terminal exit; only confirmed open-file ownership is terminal liveness. A thread that
leaves (its terminal exited, or 退勤) is unsubscribed from, and comes back when a terminal works in it again."""
import asyncio
from types import SimpleNamespace

from jui_cli.viz.ingest import World
from jui_cli.viz.sources import codex_clients
from jui_cli.viz.sources.codex_app_server import CodexLink
from jui_cli.viz.state import VizState

ROOT = '01a17b1a-6f55-7673-b69d-be249f2f4227'
CHILD = '01a17b1a-6f95-7962-ba43-35f2ea4cfff4'


def test_tui_is_matched_to_the_home_not_just_any_codex_process(tmp_path):
    (tmp_path / 'logs_2.sqlite').touch()
    procs = {10: '/bin/codex app-server --managed-daemon', 20: '/bin/codex hello', 30: '/bin/python viz serve'}
    assert codex_clients.alive(tmp_path, lambda: procs, lambda _: {10, 20}) is True
    assert codex_clients.alive(tmp_path, lambda: procs, lambda _: {10}) is False
    assert codex_clients.alive(tmp_path, lambda: procs, lambda _: {10, 30}) is False


def test_missing_processes_noninteractive_commands_and_reused_pids_are_not_tuis(tmp_path):
    (tmp_path / 'logs_2.sqlite').touch()
    for command in ['/bin/codex app-server --listen unix://', '/bin/codex exec hello', '/bin/python different-job']:
        assert codex_clients.alive(tmp_path, lambda: {10: command}, lambda _: {10}) is False
    assert codex_clients.alive(tmp_path, lambda: {99: '/bin/codex'}, lambda _: {10}) is False
    assert codex_clients.alive(tmp_path, lambda: {10: '/bin/codex resume ' + ROOT}, lambda _: {10}) is True


def test_unavailable_evidence_is_unknown_never_a_confirmed_exit(tmp_path):
    assert codex_clients.alive(tmp_path) is None
    (tmp_path / 'logs_2.sqlite').touch()
    assert codex_clients.alive(tmp_path, lambda: None, lambda _: {10}) is None
    assert codex_clients.alive(tmp_path, lambda: {10: '/bin/codex'}, lambda _: None) is None


def test_ps_and_lsof_errors_are_unknown(monkeypatch, tmp_path):
    monkeypatch.setattr(codex_clients.subprocess, 'run', lambda *a, **kw: SimpleNamespace(returncode=1, stdout=''))
    assert codex_clients.processes() is None
    assert codex_clients.owners(tmp_path) is None
    monkeypatch.setattr(codex_clients.subprocess, 'run', lambda *a, **kw: SimpleNamespace(returncode=0, stdout='permission denied'))
    assert codex_clients.processes() is None
    assert codex_clients.owners(tmp_path) is None


def make_link(terminal):
    world = World(VizState())
    class Sink:
        def apply(self, payloads, titles):
            world.apply_codex(payloads, titles, world._now + 1)
            world.publish()
    link = CodexLink(Sink(), lambda *a: None, terminal_state=lambda _: terminal[0])
    link._ws = SimpleNamespace(closed=False)
    return link, world


class Daemon:
    """The daemon's answers to the link's calls: loaded threads, their rows, thread/read's status; every call kept."""

    def __init__(self, loaded, status='idle', **row):
        self.loaded, self.status, self.row, self.calls, self.refuse = loaded, status, row, [], set()

    async def __call__(self, method, params):
        self.calls.append((method, params.get('threadId')))
        if method in self.refuse:
            return None   # a JSON-RPC error reads as None (CodexLink._call)
        if method == 'thread/loaded/list':
            return {'data': list(self.loaded)}
        if method == 'thread/unsubscribe':
            return {'status': 'unsubscribed'}
        if method == 'thread/read':
            return {'thread': {'id': params['threadId'], 'status': {'type': self.status}}}
        return {'thread': {'id': params['threadId'], 'cwd': '/work/demo', **self.row,
                           **({'parentThreadId': ROOT} if params['threadId'] == CHILD else {})}}

    def called(self, method):
        return [t for m, t in self.calls if m == method]


def test_exit_unsubscribes_idle_roots_and_children_once_and_a_turn_held_elsewhere_brings_them_back():
    async def run():
        terminal = [True]
        link, world = make_link(terminal)
        daemon = Daemon([ROOT, CHILD], source='vscode')
        link._call = daemon
        await link._poll()
        assert world.sessions[ROOT]['status'] == 'idle'
        assert link.can_prompt(ROOT)
        assert daemon.called('thread/unsubscribe') == []
        terminal[0] = False
        await link._poll()
        assert world.sessions[ROOT]['status'] == 'ended'
        assert 'leftAt' in world.agents[ROOT] and 'leftAt' in world.agents[CHILD]
        assert not link.can_prompt(ROOT)
        assert daemon.called('thread/unsubscribe') == [CHILD, ROOT]   # subagents first, then the root
        # still loaded (the daemon closes it after its unload delay): watched, never subscribed to again while idle
        count, resumes = len(world.state.events), len(daemon.called('thread/resume'))
        terminal[0] = True   # a new TUI in this home cannot bring every old loaded thread back
        await link._poll()
        assert len(world.state.events) == count and len(daemon.called('thread/resume')) == resumes
        assert daemon.called('thread/read')[-1:] == [ROOT]
        # a late approval or completion for a thread let go makes nothing
        link._dispatch({'id': 9, 'method': 'item/commandExecution/requestApproval',
                        'params': {'threadId': ROOT, 'itemId': 'old', 'command': 'echo late'}})
        link._dispatch({'method': 'turn/completed', 'params': {'threadId': ROOT, 'turn': {'id': 'old'}}})
        assert world.sessions[ROOT]['status'] == 'ended' and len(world.state.events) == count
        # a turn in it (thread/read: active) means a terminal holds it again: subscribed again, the robot is back
        daemon.status = 'active'
        await link._poll()
        assert daemon.called('thread/resume')[resumes:] == [ROOT, CHILD]
        assert world.sessions[ROOT]['status'] == 'idle'
        assert 'leftAt' not in world.agents[ROOT]
        assert link.can_prompt(ROOT)
    asyncio.run(run())


def test_a_thread_the_daemon_closed_after_leaving_is_forgotten_without_a_second_clock_out():
    async def run():
        link, world = make_link([False])
        daemon = Daemon([ROOT], source='vscode')
        link._call = daemon
        await link._poll()
        assert world.sessions[ROOT]['status'] == 'ended'
        count = len(world.state.events)
        link._dispatch({'method': 'thread/closed', 'params': {'threadId': ROOT}})   # told to unsubscribed clients too
        assert ROOT not in link._retired and len(world.state.events) == count
        daemon.loaded = []
        await link._poll()
        daemon.loaded = [ROOT]   # `codex resume` loads it again later: a new arrival
        daemon.status = 'idle'
        link.terminal_state = lambda _: True
        await link._poll()
        assert world.sessions[ROOT]['status'] == 'idle'
    asyncio.run(run())


def test_idle_and_stop_do_not_retire_a_live_tui_and_any_source_or_originator_retires_without_one():
    """Neither source nor originator names a daemon thread's own client (10-29, 0.165.0): a TUI's is vscode, and the
    originator is whichever client first initialized the daemon — jui_viz when viz connected first (01a17fb0)."""
    async def run():
        for row in [{'source': 'cli'}, {'source': 'vscode', 'originator': 'jui_viz'}, {'source': 'exec'}, {}]:
            link, world = make_link([True])
            link._call = Daemon([ROOT], **row)
            world.apply_codex(link.tr.thread_seen({'id': ROOT, **row}), {}, 1)
            for alive in [True, None]:
                link._terminal_alive = alive
                link._dispatch({'method': 'turn/completed', 'params': {'threadId': ROOT, 'turn': {'id': 't'}}})
                await link._retire_terminals()
                assert world.sessions[ROOT]['status'] == 'idle'
            link._terminal_alive = False
            link.tr.turns[ROOT] = 'running'
            await link._retire_terminals()
            assert world.sessions[ROOT]['status'] == 'idle'
            link.tr.turns.clear()
            await link._retire_terminals()
            assert world.sessions[ROOT]['status'] == 'ended', row
    asyncio.run(run())


def test_clock_out_leaves_the_thread_without_signalling_and_says_when_a_terminal_runs_in_the_home():
    async def run():
        for alive, note in [(False, ''), (True, 'a Codex terminal runs'), (None, 'whether a Codex terminal runs')]:
            link, world = make_link([alive])
            daemon = Daemon([ROOT, CHILD])
            link._call = daemon
            await link._poll()
            assert world.sessions[ROOT]['status'] == ('ended' if alive is False else 'idle')
            if alive is False:
                continue   # nothing left to clock out: its terminal's exit took it out
            status, text = await link.end(ROOT)
            assert status == 200 and text.startswith(note)
            assert daemon.called('thread/unsubscribe') == [CHILD, ROOT]
            assert world.sessions[ROOT]['status'] == 'ended' and 'leftAt' in world.agents[CHILD]
            assert world.state.events[-1]['text'].endswith('clocked out from the page') or 'clocked out from the page' in world.state.events[-1]['text']
            assert (await link.end(ROOT))[0] == 409   # gone from the room: nothing to clock out
    asyncio.run(run())


def test_clock_out_is_refused_while_a_turn_runs_when_unconnected_and_when_the_daemon_refuses():
    async def run():
        link, world = make_link([True])
        daemon = Daemon([ROOT, CHILD])
        link._call = daemon
        await link._poll()
        assert (await link.end(CHILD))[0] == 409   # a subagent is not a session
        link.tr.turns[CHILD] = 'sub-running'
        assert (await link.end(ROOT)) == (409, 'a turn is running in this Codex session: stop it first')
        link.tr.turns.clear()
        daemon.refuse.add('thread/unsubscribe')
        assert (await link.end(ROOT))[0] == 502
        assert world.sessions[ROOT]['status'] == 'idle' and ROOT not in link._retired and link.can_prompt(ROOT)
        link._ws = SimpleNamespace(closed=True)
        assert (await link.end(ROOT))[0] == 409
        assert world.sessions[ROOT]['status'] == 'idle'
    asyncio.run(run())


def test_real_open_file_owner_disappears_when_its_process_exits(tmp_path):
    import shutil
    import subprocess
    import time
    import pytest

    if not shutil.which('lsof'):
        pytest.skip('lsof is unavailable: its failure path is covered separately')
    binary = tmp_path / 'codex'
    binary.symlink_to('/bin/bash')   # not sleep: a multi-call coreutils (Ubuntu 26.04) refuses to run as codex
    with (tmp_path / 'logs_2.sqlite').open('w') as opened:
        child = subprocess.Popen([str(binary), '-c', 'read -t 60'], stdin=subprocess.PIPE, pass_fds=(opened.fileno(),))
        try:
            deadline = time.monotonic() + 6
            while codex_clients.alive(tmp_path) is not True:
                assert time.monotonic() < deadline, 'the stand-in terminal is not observed'
                time.sleep(.02)
            child.terminate()
            child.wait(timeout=5)
            assert codex_clients.alive(tmp_path) is False
        finally:
            if child.poll() is None:
                child.terminate()
                child.wait(timeout=5)
            child.stdin.close()


def test_the_page_clocks_a_codex_session_out_through_its_link_and_never_the_claude_path(tmp_path, monkeypatch):
    import json
    import socket
    from aiohttp.test_utils import TestClient, TestServer
    from jui_cli.viz import clockout
    from jui_cli.viz.config import VizConfig
    from jui_cli.viz.server import ServerContext, make_app

    monkeypatch.setenv('HOME', str(tmp_path))
    def claude_path(*a, **kw):
        raise AssertionError('a Codex session never reaches clockout.end_session')
    monkeypatch.setattr(clockout, 'end_session', claude_path)
    monkeypatch.setattr(clockout, '_kill', claude_path)

    async def run():
        link, world = make_link([True])
        daemon = Daemon([ROOT, CHILD])
        link._call = daemon
        await link._poll()
        world.codex_end = link.end
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', 0))
            port = probe.getsockname()[1]
        ctx = ServerContext(config=VizConfig(), port=port, token='test-token', state=world.state, world=world, publish=world.publish)
        async with TestClient(TestServer(make_app(ctx), host='127.0.0.1', port=port)) as page:
            ctx.port = page.port
            headers = {'Origin': f'http://127.0.0.1:{page.port}', 'X-Jui-Viz-Token': ctx.token}
            sub = await page.post('/api/session/end', json={'sessionId': ROOT, 'agentId': CHILD}, headers=headers)
            assert sub.status == 403
            link.tr.turns[ROOT] = 'running'
            busy = await page.post('/api/session/end', json={'sessionId': ROOT, 'agentId': ROOT}, headers=headers)
            assert busy.status == 409 and 'stop it first' in await busy.text()
            assert world.sessions[ROOT]['status'] != 'ended' and daemon.called('thread/unsubscribe') == []
            link.tr.turns.clear()
            ok = await page.post('/api/session/end', json={'sessionId': ROOT, 'agentId': ROOT}, headers=headers)
            got = await ok.json()
            assert ok.status == 200 and got['ok'] and got['note'].startswith('a Codex terminal runs')
            assert world.sessions[ROOT]['status'] == 'ended' and world.sessions[ROOT]['clockedOut']
            assert daemon.called('thread/unsubscribe') == [CHILD, ROOT]
            again = await page.post('/api/session/end', json={'sessionId': ROOT, 'agentId': ROOT}, headers=headers)
            assert again.status == 404
        log = [json.loads(line) for line in (tmp_path / '.local/state/jui-viz/clock-out.log').read_text().splitlines()]
        assert [(r['status'], r['result']) for r in log] == [(403, 'refused'), (409, 'refused'), (200, 'ended'), (404, 'refused')]
        assert log[2]['cli'] == 'codex' and log[2]['note'].startswith('a Codex terminal runs')
        assert 'pid' not in log[2] and 'ledger' not in log[2]
        # the event log says the thread was let go, not that a signal was sent (the requester, 10-29)
        from jui_cli.viz import i18n
        lines = [e['text'] for e in world.state.events if e['kind'] == 'ClockOut']
        label = world.sessions[ROOT]['label']
        assert lines[1] == i18n.tl('ev.clockout.codex', label=label, how=i18n.tl('ev.clockout.refused'),
                                   why=': a turn is running in this Codex session: stop it first')
        assert lines[2] == i18n.tl('ev.clockout.codex', label=label, how=i18n.tl('ev.clockout.ended'), why='')
        assert all(i18n.tl('ev.clockout', label='', pid='', how='', why='').strip() not in t for t in lines[1:3])
    asyncio.run(run())
