"""上限で停止 (ticket 2026-10-29-viz-limit-stopped-robot-dazed): a turn that ends on the plan's usage limit leaves its
robot dazed (state ``limited``) until the session's next prompt or start. Claude Code says so in StopFailure's own
``error`` (rate_limit; claude 2.1.312), Codex in the failed turn's codexErrorInfo (usageLimitExceeded, measured on the
daemon 10-29). Other errors (server_error, overloaded, ...) stop the turn as before."""
from jui_cli.viz import i18n
from jui_cli.viz.ingest import World
from jui_cli.viz.sources.codex_app_server import Translator
from jui_cli.viz.state import VizState

SID = 'c1000000-0000-4000-8000-00000000d0ed'
LIMIT_WORDS = "You've hit your monthly spend limit · your weekly limit resets Oct 30 at 2pm (Asia/Tokyo)"


def hook(world, kind, at, **extra):
    world.apply_hook({'hook_event_name': kind, 'session_id': SID, 'cwd': '/work/dazed', **extra}, at)


def started(at=1_000):
    world = World(VizState())
    hook(world, 'SessionStart', at, source='startup')
    hook(world, 'UserPromptSubmit', at + 10, prompt='go on')
    return world


def test_a_rate_limit_stop_dazes_the_robot_with_the_limits_own_words_until_the_next_prompt():
    world = started()
    hook(world, 'StopFailure', 2_000, error='rate_limit', last_assistant_message=LIMIT_WORDS)
    agent, session = world.agents[SID], world.sessions[SID]
    assert agent['state'] == 'limited' and agent['act'] == i18n.tl('act.limited')
    assert agent['lastMessage'] == LIMIT_WORDS and session['limited'] == 2_000
    assert world.state.events[-1]['text'] == i18n.tl('ev.stop.limited')
    world.tick(2_000 + 600_000)   # no timer takes it back to idle
    assert world.agents[SID]['state'] == 'limited'
    hook(world, 'UserPromptSubmit', 900_000, prompt='again')
    assert world.agents[SID]['state'] != 'limited' and 'limited' not in world.sessions[SID]


def test_a_new_start_also_ends_the_daze():
    world = started()
    hook(world, 'StopFailure', 2_000, error='rate_limit')
    hook(world, 'SessionStart', 3_000, source='resume')
    assert world.agents[SID]['state'] == 'idle' and 'limited' not in world.sessions[SID]


def test_other_stop_failures_and_a_subagents_do_not_daze():
    for error in ['server_error', 'overloaded', 'oauth_org_not_allowed', 'unknown', None]:
        world = started()
        hook(world, 'StopFailure', 2_000, **({'error': error} if error else {}))
        assert world.agents[SID]['state'] == 'done' and 'limited' not in world.sessions[SID], error
        assert world.state.events[-1]['text'] == i18n.tl('ev.stop.failed')
    world = started()
    hook(world, 'StopFailure', 2_000, error='rate_limit', agent_id='sub-1', agent_type='Explore')
    assert world.agents[SID]['state'] != 'limited' and 'limited' not in world.sessions[SID]


def codex_turn(tr, status, error=None):
    turn = {'id': 't1', 'status': status, **({'error': error} if error else {})}
    return tr.event('turn/completed', {'threadId': 'root', 'turn': turn})


def test_a_codex_turn_failed_on_the_plan_reads_as_a_rate_limit_stop_failure():
    tr = Translator()
    tr.thread_seen({'id': 'root', 'cwd': '/work/dazed'})
    words = 'Your workspace is out of credits. Add credits to continue.'
    for info in ['usageLimitExceeded', 'rateLimitExceeded']:
        [out] = codex_turn(tr, 'failed', {'message': words, 'codexErrorInfo': info, 'additionalDetails': None})
        assert out['hook_event_name'] == 'StopFailure' and out['error'] == 'rate_limit' and out['last_assistant_message'] == words
    [out] = codex_turn(tr, 'failed', {'message': 'boom', 'codexErrorInfo': 'internalServerError'})
    assert out['error'] == 'server_error'
    [out] = codex_turn(tr, 'failed', {'message': 'odd', 'codexErrorInfo': {'httpConnectionFailed': {'httpStatusCode': 502}}})
    assert out['error'] == 'unknown'
    [out] = codex_turn(tr, 'completed')
    assert out['hook_event_name'] == 'Stop' and 'error' not in out
    [out] = codex_turn(tr, 'interrupted')
    assert out['hook_event_name'] == 'Stop'


def test_a_codex_session_on_its_limit_is_dazed_and_comes_back_with_its_next_prompt():
    world, tr = World(VizState()), Translator()
    world.apply_codex(tr.thread_seen({'id': 'root', 'cwd': '/work/dazed'}), {}, 1_000)
    world.apply_codex(codex_turn(tr, 'failed', {'message': 'out of credits', 'codexErrorInfo': 'usageLimitExceeded'}), {}, 2_000)
    assert world.agents['root']['state'] == 'limited' and world.sessions['root']['limited'] == 2_000
    prompt = tr.event('item/started', {'threadId': 'root', 'item': {'type': 'userMessage', 'id': 'u2',
                                                                    'content': [{'type': 'text', 'text': 'retry'}]}})
    world.apply_codex(prompt, {}, 3_000)
    assert world.agents['root']['state'] != 'limited' and 'limited' not in world.sessions['root']
