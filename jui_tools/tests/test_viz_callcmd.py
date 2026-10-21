"""The call button's command (viz/callcmd.py, 2.3.5): whatever the name, the role text and the project folder hold, the
line handed to the person passes each as exactly one argument, in zsh and in bash, run with -c and pasted at an
interactive prompt. The CLI is never started: a shell function of the same name prints $PWD and its arguments."""
from __future__ import annotations

import json
import os
import subprocess

import pytest

from jui_cli.viz import callcmd as C

SHELLS = [s for s in ("/bin/zsh", "/bin/bash") if os.path.exists(s)]
NASTY = [
    "plain", "two words", "it's", 'say "hi"', "$(touch PWNED)", "`touch PWNED`", "a; touch PWNED", "a && touch PWNED",
    "a | tee PWNED", "back\\slash", "!!", "!touch", "bang!x", "-x", "--help", "--name=evil", "-n", "${HOME}", "$HOME",
    "日本語の担当", "絵文字🤖✨", "tab?", "a'b\"c$d`e\\f!g", "*", "~", "#comment", "x" * 64,
]
ROLES = ["", "一行", "二行目まで\n二行目", "line1\nline2; touch PWNED\n$(touch PWNED)", "'; touch PWNED; '",
         "-starts with a dash", "cr\rhere", "esc\x1b[2Jclear", "csi\u009b31m", "del\x7fx", "tab\there", "y" * 4000,
         "end with backslash\\", "!!:p and !-1"]


def _run(shell: str, root: str, line: str, interactive: bool, tmp_path, locale: str = "en_US.UTF-8") -> list[str]:
    out = tmp_path / "argv.bin"
    if out.exists():
        out.unlink()
    defs = f"claude() {{ printf '%s\\0' \"$PWD\" \"$@\" > {C.sh_quote(str(out))}; }}"
    env = {"PATH": "/usr/bin:/bin", "HOME": str(tmp_path), **({"LC_ALL": locale} if locale else {})}
    base = [shell, "-f"] if shell.endswith("zsh") else [shell, "--norc", "--noprofile"]
    if interactive:   # pasted at a prompt: history expansion and the line editor's rules apply
        subprocess.run(base + ["-i"], input=(defs + "\n" + line + "\nexit\n").encode(), cwd=tmp_path, env=env,
                       capture_output=True, timeout=20)
    else:
        subprocess.run(base + ["-c", defs + "\n" + line], cwd=tmp_path, env=env, capture_output=True, timeout=20)
    assert out.exists(), f"{shell} did not run the line: {line!r}"
    return out.read_bytes().decode("utf-8").split("\0")[:-1]


@pytest.fixture
def root(tmp_path):
    d = tmp_path / "proj a b'c\"$(touch PWNED)`touch PWNED`;!x\\y -z"
    d.mkdir()
    return str(d)


@pytest.mark.skipif(not SHELLS, reason="no zsh or bash")
@pytest.mark.parametrize("shell", SHELLS)
@pytest.mark.parametrize("interactive", [False, True], ids=["-c", "pasted"])
@pytest.mark.parametrize("locale", ["en_US.UTF-8", "C", ""], ids=["utf8", "C", "unset"])
def test_every_name_and_role_is_one_argument(shell, interactive, locale, root, tmp_path):
    for i, name in enumerate(NASTY):
        role = ROLES[i % len(ROLES)]
        line = C.command(root, name, role, "--channels")
        got = _run(shell, root, line, interactive, tmp_path, locale)
        assert got == [os.path.realpath(root), *C.argv_of(name, role, "--channels")], (shell, name, role, line)
    assert not list(tmp_path.rglob("PWNED")), "a name, a role or the folder ran a command"


@pytest.mark.skipif(not SHELLS, reason="no zsh or bash")
@pytest.mark.parametrize("shell", SHELLS)
def test_every_role_is_one_argument(shell, root, tmp_path):
    for role in ROLES:
        got = _run(shell, root, C.command(root, "role-check", role, "--dangerously-load-development-channels"), True, tmp_path)
        assert got[-1] == C.prompt_of("role-check", role) and len(got) == 5, (shell, role)
    assert not list(tmp_path.rglob("PWNED"))


def test_the_line_is_plain_printable_ascii():
    for i, name in enumerate(NASTY):
        line = C.command("/w/日本語 app", name, ROLES[i % len(ROLES)], "--channels")
        assert all(0x20 <= ord(ch) <= 0x7E for ch in line), repr(line)


@pytest.mark.viz_ja
def test_the_prompt_never_begins_with_a_dash_and_carries_the_name():
    p = C.prompt_of("-x", "--help")
    assert p.startswith(C.preface()) and "セッション名: -x" in p and p.endswith("\n--help")
    assert C.argv_of("-x", "", "--channels")[2] == "--name=-x"
    assert C.prompt_of("n", "   ") == f"{C.preface()}\nセッション名: n"


@pytest.mark.parametrize("name, role, why", [
    ("", "", "担当名を入れてください"), ("   ", "", "担当名を入れてください"), ("a\0b", "", "NUL"), ("a", "b\0", "NUL"),
    ("two\nlines", "", "1 行で"), ("tab\there", "", "1 行で"), ("x" * 65, "", "64 文字まで"), ("a", "y" * 4001, "4000 文字まで"),
    (None, "", "文字列"), ("a", 3, "文字列"),
])
@pytest.mark.viz_ja
def test_what_cannot_make_a_command(name, role, why):
    assert why in (C.check(name, role) or "")
    with pytest.raises(ValueError):
        C.command("/w/app", name, role, "--channels")


def test_quote_keeps_a_plain_word_bare_and_refuses_nul():
    assert C.sh_quote("plugin:jui-viz@jsonui") == "plugin:jui-viz@jsonui" and C.sh_quote("") == "''"
    assert C.sh_quote("it's") == "'it'\\''s'"
    with pytest.raises(ValueError):
        C.sh_quote("a\0b")


@pytest.mark.parametrize("settings, flag", [
    (None, "--dangerously-load-development-channels"),
    ({"channelsEnabled": True, "allowedChannelPlugins": ["jui-viz@jsonui"]}, "--channels"),
    ({"channelsEnabled": True, "allowedChannelPlugins": [{"plugin": "jui-viz", "marketplace": "jsonui"}]}, "--channels"),
    ({"channelsEnabled": False, "allowedChannelPlugins": ["jui-viz@jsonui"]}, "--dangerously-load-development-channels"),
    ({"channelsEnabled": "true", "allowedChannelPlugins": ["jui-viz@jsonui"]}, "--dangerously-load-development-channels"),
    ({"channelsEnabled": True, "allowedChannelPlugins": ["other@jsonui"]}, "--dangerously-load-development-channels"),
    ({"channelsEnabled": True}, "--dangerously-load-development-channels"),
    ({"channelsEnabled": True, "allowedChannelPlugins": "jui-viz@jsonui"}, "--dangerously-load-development-channels"),
    ("not json {", "--dangerously-load-development-channels"),
    ([1, 2], "--dangerously-load-development-channels"),
])
def test_the_channels_flag_follows_the_managed_settings(settings, flag, tmp_path):
    p = tmp_path / "managed-settings.json"
    if settings is not None:
        p.write_text(settings if isinstance(settings, str) else json.dumps(settings))
    assert C.channels_flag(str(p)) == flag


def test_the_channels_flag_only_reads(tmp_path):
    p = tmp_path / "managed-settings.json"
    p.write_text(json.dumps({"channelsEnabled": True, "allowedChannelPlugins": ["jui-viz@jsonui"]}))
    before = (p.stat().st_mtime_ns, p.read_bytes(), sorted(os.listdir(tmp_path)))
    C.channels_flag(str(p))
    assert (p.stat().st_mtime_ns, p.read_bytes(), sorted(os.listdir(tmp_path))) == before
