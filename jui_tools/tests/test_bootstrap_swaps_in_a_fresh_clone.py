"""The bootstrap clones next to the install folder and swaps the clone in; it never empties the live folder first.

🚨 WHY THIS FILE EXISTS. 2026-10-20 13:11:18, the 2.3.7 distribution: `bash
installer/bootstrap.sh` exited 1 with a viz server (2.3.6) running, and
~/.jsonui-cli was left holding only viz/server.json — no VERSION, no
jui_tools; `jui` was a ModuleNotFoundError until the bootstrap was run again.

The writer is the running server's copy of server.json for the jui-viz plugin
1.0.0 (viz_cmd._legacy_mirror_write): every LEGACY_MIRROR_SEC it re-creates
~/.jsonui-cli/viz/server.json whenever ~/.jsonui-cli is a folder. The old
re-install did `rm -rf "$INSTALL_DIR"` then `git clone` into it. `rm -rf`
removes the contents first and the folder last; a write landing in between
makes the last rmdir fail ("Directory not empty"), rm exits 1, `set -e` ends
the script, and what is left is exactly that one file. Measured with the real
rm on a 4787-file tree and a writer with the mirror's rule: rc 1, only
viz/server.json left (the rm took 0.27 s against a 2 s period, so about one
distribution in seven). A writer during `git clone` into the folder it has just
created was also measured: the clone succeeds; that window is not the one.

Here the window is made deterministic with two stubs put first on PATH: an
`rm` that, for a folder named .jsonui-cli*, removes the contents, lets the viz
stand-in write, then removes the folder (rm's own order, with the write placed
inside it), and a `git` that lets the stand-in write before every clone. The
stand-in follows the mirror's rule: it writes only when ~/.jsonui-cli is a
folder and creates viz/ without parents.

The clone source is a local bare repository reached through `url.insteadOf`,
so nothing here touches the network, the real HOME or the real ~/.jsonui-cli.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
BOOTSTRAP = REPO / "installer" / "bootstrap.sh"
REPO_URL = "https://github.com/Tai-Kimura/jsonui-cli.git"
REAL_GIT = shutil.which("git")

MIRROR = {"pid": 4242, "port": 7788, "mirrorOf": "/x/.local/state/jui-viz/server.json"}

STANDIN = """#!/bin/bash
# The running viz server's mirror write: only into an existing install folder, viz/ without parents.
inst="$HOME/.jsonui-cli"
[ -d "$inst" ] || exit 0
mkdir "$inst/viz" 2>/dev/null
n=$(( $(cat "$STANDIN_LOG" 2>/dev/null | wc -l) + 1 ))
printf '{"pid": 4242, "port": 7788, "mirrorOf": "standin", "write": %s}' "$n" > "$inst/viz/server.json" 2>/dev/null \\
    && echo "$1" >> "$STANDIN_LOG"
exit 0
"""

RM = """#!/bin/bash
# rm, except that a folder named .jsonui-cli* is removed in rm -rf's own order (contents, then the folder)
# with the viz stand-in writing in between.
flags=(); ops=(); rec=0
for a in "$@"; do
    case "$a" in
        -*) flags+=("$a"); case "$a" in *r*|*R*) rec=1 ;; esac ;;
        *) ops+=("$a") ;;
    esac
done
st=0
for op in "${ops[@]}"; do
    base="${op##*/}"
    if [ "$rec" = 1 ] && [ -d "$op" ] && [ ! -L "$op" ] && [[ "$base" == .jsonui-cli* ]]; then
        find "$op" -mindepth 1 -maxdepth 1 -exec /bin/rm -rf {} + || st=1
        "$STANDIN" "rm $base"
        /bin/rmdir "$op" 2>/dev/null || { echo "rm: $op: Directory not empty" >&2; st=1; }
    else
        /bin/rm "${flags[@]}" "$op" || st=1
    fi
done
exit $st
"""

GIT = """#!/bin/bash
[ "$1" = "clone" ] && "$STANDIN" "git clone"
exec "{real}" "$@"
"""


def _write_exec(path: Path, text: str) -> Path:
    path.write_text(text)
    path.chmod(0o755)
    return path


def _git(*args: str, cwd: Path) -> str:
    return subprocess.run([REAL_GIT, "-c", "user.name=t", "-c", "user.email=t@t", *args], cwd=cwd,
                          check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture()
def world(tmp_path):
    """A temp HOME with an installed (old) tree, a running server's state, and a bare repo to clone."""
    src = tmp_path / "src"
    (src / "sjui_tools" / "bin").mkdir(parents=True)
    (src / "sjui_tools" / "bin" / "sjui").write_text("#!/bin/sh\necho new\n")
    (src / "installer").mkdir()
    (src / "installer" / "bootstrap.sh").write_text("# not this one\n")
    (src / "VERSION").write_text("9.9.9\n")
    _git("init", "-q", "-b", "main", cwd=src)
    _git("add", "-A", cwd=src)
    _git("commit", "-q", "-m", "new", cwd=src)
    sha = _git("rev-parse", "HEAD", cwd=src)
    bare = tmp_path / "bare.git"
    _git("clone", "-q", "--bare", str(src), str(bare), cwd=tmp_path)

    home = tmp_path / "home"
    install = home / ".jsonui-cli"
    (install / "sjui_tools" / "bin").mkdir(parents=True)
    (install / "sjui_tools" / "bin" / "sjui").write_text("#!/bin/sh\necho old\n")
    (install / "VERSION").write_text("1.0.0\n")
    (install / "SOURCE_SHA").write_text("0" * 40 + "\n")
    # the running server: its own files in the state folder, its mirror in the install folder
    state = home / ".local" / "state" / "jui-viz"
    state.mkdir(parents=True)
    (state / "server.json").write_text(json.dumps(dict(MIRROR, mirrorOf=None)))
    (install / "viz").mkdir()
    (install / "viz" / "server.json").write_text(json.dumps(MIRROR))
    # what a 2.1.0 install left behind: moved to the state folder by migrate_viz_state
    (install / "viz" / "backups").mkdir()
    (install / "viz" / "backups" / "settings.json.1").write_text("backup")

    stubs = tmp_path / "stubs"
    stubs.mkdir()
    standin = _write_exec(tmp_path / "standin.sh", STANDIN)
    log = tmp_path / "standin.log"

    def run(race: bool = False, source: str | None = None) -> subprocess.CompletedProcess:
        env = {k: v for k, v in os.environ.items()
               if k not in ("JUI_VIZ_HOME", "XDG_STATE_HOME", "JSONUI_CLI_DIR", "JSONUI_INSTALL_DIR",
                            "JSONUI_TOOLS", "PYTHONPATH") and not k.startswith("GIT_")}
        path = f"{Path(REAL_GIT).parent}:/usr/bin:/bin"
        if race:
            _write_exec(stubs / "rm", RM)
            _write_exec(stubs / "git", GIT.replace("{real}", REAL_GIT))
            path = f"{stubs}:{path}"
        env.update(HOME=str(home), PATH=path, SHELL="/bin/bash", JSONUI_TOOLS="sjui",
                   STANDIN=str(standin), STANDIN_LOG=str(log),
                   GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_COUNT="1",
                   GIT_CONFIG_KEY_0=f"url.{source or bare.as_uri()}.insteadOf", GIT_CONFIG_VALUE_0=REPO_URL)
        return subprocess.run(["bash", str(BOOTSTRAP)], env=env, cwd=tmp_path, capture_output=True,
                              text=True, timeout=120)

    return {"home": home, "install": install, "state": state, "sha": sha, "run": run, "log": log,
            "tmp": tmp_path}


def _snapshot(root: Path) -> dict:
    return {str(p.relative_to(root)): (p.read_bytes() if p.is_file() else None)
            for p in sorted(root.rglob("*"))}


def _assert_complete(w) -> None:
    install = w["install"]
    assert (install / "VERSION").read_text() == "9.9.9\n"
    assert (install / "SOURCE_SHA").read_text().strip() == w["sha"]
    assert os.access(install / "sjui_tools" / "bin" / "sjui", os.X_OK)
    assert not (install / ".git").exists() and not (install / "installer").exists()


def _siblings(w) -> list[str]:
    """What the swap may have left next to the install folder."""
    return sorted(p.name for p in w["home"].iterdir() if "jsonui-cli" in p.name and p.name != ".jsonui-cli")


# ---------------------------------------------------------------- the race of 2026-10-20 13:11:18


def test_the_viz_writing_during_the_reinstall_does_not_break_it(world):
    r = world["run"](race=True)
    assert r.returncode == 0, r.stdout + r.stderr
    _assert_complete(world)
    assert (world["install"] / "viz" / "server.json").is_file()
    assert _siblings(world) == []


def test_the_stand_in_did_write_during_the_run(world):
    # 陽性対照 for the arm above: a stand-in that never wrote would make it pass on any script.
    world["run"](race=True)
    writes = world["log"].read_text().splitlines()
    assert any(w.startswith("rm ") for w in writes), f"the viz stand-in never wrote inside a deletion: {writes}"


# ---------------------------------------------------------------- a clone that fails


def test_a_failed_clone_leaves_the_old_install_untouched(world):
    before = _snapshot(world["install"])
    r = world["run"](source=(world["tmp"] / "no-such-repo.git").as_uri())
    assert r.returncode != 0
    assert _snapshot(world["install"]) == before
    assert _siblings(world) == []


def test_a_failed_clone_with_the_viz_writing_leaves_the_old_install_whole(world):
    r = world["run"](race=True, source=(world["tmp"] / "no-such-repo.git").as_uri())
    assert r.returncode != 0
    assert (world["install"] / "VERSION").read_text() == "1.0.0\n"
    assert (world["install"] / "sjui_tools" / "bin" / "sjui").read_text() == "#!/bin/sh\necho old\n"
    assert _siblings(world) == []


# ---------------------------------------------------------------- the normal path


def test_a_reinstall_replaces_the_tree_and_keeps_the_viz_folder(world):
    mirror = (world["install"] / "viz" / "server.json").read_bytes()
    r = world["run"]()
    assert r.returncode == 0, r.stdout + r.stderr
    _assert_complete(world)
    # the running server's mirror for the plugin 1.0.0 is carried across the swap, byte for byte
    assert (world["install"] / "viz" / "server.json").read_bytes() == mirror
    # and the earlier fix still runs first: what 2.1.0 left is moved to the state folder
    assert (world["state"] / "backups" / "settings.json.1").read_text() == "backup"
    assert not (world["install"] / "viz" / "backups").exists()
    assert _siblings(world) == []


def test_a_first_install_clones_into_place(world):
    shutil.rmtree(world["install"])
    r = world["run"]()
    assert r.returncode == 0, r.stdout + r.stderr
    _assert_complete(world)
    assert not (world["install"] / "viz").exists()
    assert _siblings(world) == []
