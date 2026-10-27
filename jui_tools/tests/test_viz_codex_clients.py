"""Daemon membership survives terminal exit; only confirmed open-file ownership is terminal liveness."""
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


def test_exit_retires_idle_roots_and_children_once_without_resurrecting_on_loaded_poll():
    async def run():
        terminal = [True]
        link, world = make_link(terminal)
        async def call(method, params):
            if method == 'thread/loaded/list':
                return {'data': [ROOT, CHILD]}
            return {'thread': {'id': params['threadId'], 'source': 'cli', 'cwd': '/work/demo',
                               **({'parentThreadId': ROOT} if params['threadId'] == CHILD else {})}}
        link._call = call
        await link._poll()
        assert world.sessions[ROOT]['status'] == 'idle'
        assert link.can_prompt(ROOT)
        terminal[0] = False
        await link._poll()
        assert world.sessions[ROOT]['status'] == 'ended'
        assert 'leftAt' in world.agents[ROOT] and 'leftAt' in world.agents[CHILD]
        assert not link.can_prompt(ROOT)
        count = len(world.state.events)
        await link._poll()
        assert len(world.state.events) == count
        link._dispatch({'method': 'turn/completed', 'params': {'threadId': ROOT, 'turn': {'id': 'old'}}})
        assert world.sessions[ROOT]['status'] == 'ended'
        link._dispatch({'id': 9, 'method': 'item/commandExecution/requestApproval',
                        'params': {'threadId': ROOT, 'itemId': 'old', 'command': 'echo late'}})
        assert world.sessions[ROOT]['status'] == 'ended'
        # A new TUI in this home cannot resurrect every old loaded thread.
        terminal[0] = True
        await link._poll()
        assert world.sessions[ROOT]['status'] == 'ended'
        # Explicit activity on this thread proves its resume, even before the next process poll.
        link._dispatch({'method': 'turn/started', 'params': {'threadId': ROOT, 'turn': {'id': 'new'}}})
        assert world.sessions[ROOT]['status'] == 'idle'
        assert 'leftAt' not in world.agents[ROOT]
        assert link.can_prompt(ROOT)
    asyncio.run(run())


def test_idle_and_stop_do_not_retire_a_live_tui_and_unknown_or_exec_sources_are_kept():
    async def run():
        terminal = [True]
        link, world = make_link(terminal)
        world.apply_codex(link.tr.thread_seen({'id': ROOT, 'source': 'cli'}), {}, 1)
        for alive in [True, None]:
            link._terminal_alive = alive
            link._dispatch({'method': 'turn/completed', 'params': {'threadId': ROOT, 'turn': {'id': 't'}}})
            link._retire_terminals()
            assert world.sessions[ROOT]['status'] == 'idle'
        link._terminal_alive = False
        for source in ['exec', 'vscode', None]:
            link.tr.threads[ROOT]['source'] = source
            link._retire_terminals()
            assert world.sessions[ROOT]['status'] == 'idle'
        link.tr.threads[ROOT]['source'] = 'cli'
        link.tr.turns[ROOT] = 'running'
        link._retire_terminals()
        assert world.sessions[ROOT]['status'] == 'idle'
        link.tr.turns.clear()
        link._retire_terminals()
        assert world.sessions[ROOT]['status'] == 'ended'
    asyncio.run(run())


def test_real_open_file_owner_disappears_when_its_process_exits(tmp_path):
    import shutil
    import subprocess
    import time
    import pytest

    if not shutil.which('lsof'):
        pytest.skip('lsof is unavailable: its failure path is covered separately')
    binary = tmp_path / 'codex'
    binary.symlink_to(shutil.which('sleep'))
    with (tmp_path / 'logs_2.sqlite').open('w') as opened:
        child = subprocess.Popen([str(binary), '60'], pass_fds=(opened.fileno(),))
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


def test_daemon_vscode_source_with_verified_tui_originator_retires(tmp_path):
    import json
    async def run():
        sessions = tmp_path / 'sessions'
        sessions.mkdir()
        rollout = sessions / 'rollout.jsonl'
        rollout.write_text(json.dumps({'type': 'session_meta', 'payload': {
            'id': ROOT, 'source': 'vscode', 'originator': 'codex-tui'}}) + '\n')
        link, world = make_link([False])
        link.path = tmp_path / 'app-server-control' / 'app-server-control.sock'
        async def call(method, params):
            if method == 'thread/loaded/list':
                return {'data': [ROOT]}
            return {'thread': {'id': ROOT, 'source': 'vscode', 'path': str(rollout)}}
        link._call = call
        await link._poll()
        assert link.tr.threads[ROOT]['originator'] == 'codex-tui'
        assert world.sessions[ROOT]['status'] == 'ended'
        assert world.agents[ROOT]['leftAt']
    asyncio.run(run())


def test_originator_header_is_bounded_scoped_and_identity_checked(tmp_path):
    import json
    from jui_cli.viz.sources.codex_history import originator
    sessions = tmp_path / 'sessions'
    sessions.mkdir()
    path = sessions / 'rollout.jsonl'
    good = json.dumps({'type': 'session_meta', 'payload': {'id': ROOT, 'originator': 'codex-tui'}})
    path.write_text(good + '\nprivate later data')
    assert originator(tmp_path, str(path), ROOT) == 'codex-tui'
    assert originator(tmp_path, str(path), CHILD) is None
    outside = tmp_path / 'outside.jsonl'
    outside.write_text(good)
    assert originator(tmp_path, str(outside), ROOT) is None
    path.write_text('x' * (1024 * 1024 + 1))
    assert originator(tmp_path, str(path), ROOT) is None
    path.write_text('invalid')
    assert originator(tmp_path, str(path), ROOT) is None
    path.unlink()
    assert originator(tmp_path, str(path), ROOT) is None
