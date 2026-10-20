"""The sheet's 操作 carries the spec's own fields (ticket 2026-10-20-jui-viz-spec-events-as-table): action,
processing and destination (userAction in screen_spec_schema), each its own column on the page; nothing is read
out of the text."""

from jui_cli.viz.sheet import build_doc

IMPL = {"total": 0, "done": 0}


def test_user_actions_are_action_processing_destination():
    spec = {"userActions": [{"action": "地図を開く", "processing": "地図アプリを開く", "destination": "地図アプリ", "notes": "n"},
                            {"action": "戻る", "processing": "pop"}]}
    assert build_doc(spec, [], [], IMPL)["userActions"] == [["地図を開く", "地図アプリを開く", "地図アプリ"], ["戻る", "pop", ""]]


def test_event_handlers_stay_name_and_description():
    spec = {"stateManagement": {"eventHandlers": [{"name": "onDateChange", "description": "日付の変更（引数 value: String）", "notes": "x"}]}}
    assert build_doc(spec, [], [], IMPL)["eventHandlers"] == [["onDateChange", "日付の変更（引数 value: String）"]]
