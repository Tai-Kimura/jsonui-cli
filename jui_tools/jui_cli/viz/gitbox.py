"""git push and git pull in a session's Bash, for the cardboard box in the room (2.3.4, requester 10-19:
"Gitのプッシュとかの場合はダンボールにコミットしたコード量に応じて書類をロボットが入れに行く(表示でコミットしたブランチ名とか
情報を出す) 逆にプルした時は箱から書類を持って机に帰る").

What is seen: only git that a Claude session ran through its Bash tool (PreToolUse / PostToolUse of Bash). The
requester's own terminal, an editor's git screen and a merge on the hosting site are not — they send no hook.

Which commands count — read from the program and its subcommand, the way robots.test_platform reads a test run
(c94fc068), never from a word in the text:
  * ``git push`` (not ``--dry-run`` / ``-n``) and ``git pull`` (not ``--dry-run``), with git's own options before the
    subcommand (``-C <dir>``, ``-c k=v``, ``--git-dir=…``, ``--no-pager`` …) and after ``cd <dir> &&``, ``env X=1``,
    ``timeout 60`` and the like. ``-C`` and ``cd`` move the folder the range is counted in.
  * ``git fetch`` followed by ``git merge`` does not count: a merge alone cannot be told from a local merge.
  * a string that only mentions git (``echo "git push"``, ``grep 'git pull'``, a heredoc body) does not.

What is read:
  * push: git's report (stderr) ``  <old>..<new>  <src> -> <dst>`` per ref, ``[new branch]``, ``[new tag]``,
    ``[deleted]``, ``[rejected]`` / ``[remote rejected]``, ``(forced update)``, ``Everything up-to-date``. The amount
    is counted afterwards in the session's folder (or the ``-C`` one) with ``git diff --shortstat <old>..<new>`` and
    ``git rev-list --count <old>..<new>`` — read-only (GIT_OPTIONAL_LOCKS=0), a short timeout, silent on failure. A new
    branch is counted from where it leaves origin's default branch, when that can be found; else it has no amount.
    The remote's URL is never kept (it can hold a token).
  * pull: ``Updating <old>..<new>``, ``N files changed, X insertions(+), Y deletions(-)``, ``Already up to date``,
    a conflict or ``fatal:`` / ``error:``. The commits are counted the same way when the range is known.
"""
from __future__ import annotations

import os
import re
import subprocess

from .robots import _head, simple_commands

COUNT_TIMEOUT_SEC = 3
_GIT_OPTS_WITH_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--config-env", "--super-prefix",
                        "--exec-path", "--list-cmds"}
_REF_LINE = re.compile(r"^\s*([ +*!=-])\s+(\[[^\]]+\]|[0-9a-f]{4,}\.\.\.?[0-9a-f]{4,})\s+(\S+)(?:\s+->\s+(\S+))?(?:\s+\((.+)\))?\s*$")
_STAT = re.compile(r"(\d+) files? changed(?:, (\d+) insertions?\(\+\))?(?:, (\d+) deletions?\(-\))?")
_UPDATING = re.compile(r"^Updating ([0-9a-f]{4,})\.\.([0-9a-f]{4,})\s*$", re.M)
_FETCH_BRANCH = re.compile(r"^\s*\*\s+branch\s+(\S+)\s+->\s+FETCH_HEAD", re.M)
_REBASED = re.compile(r"Successfully rebased and updated refs/heads/(\S+?)\.?\s*$", re.M)
LABEL_MAX = 60


def _join(base: str | None, path: str) -> str:
    path = os.path.expanduser(path)
    return path if os.path.isabs(path) or not base else os.path.normpath(os.path.join(base, path))


def git_action(command: str, cwd: str | None = None) -> dict | None:
    """{"kind": "push" | "pull", "dir": the folder git ran in} for the last push or pull of the command, or None."""
    where, found = cwd, None
    for words in simple_commands(command):
        words = _head(words)
        if not words:
            continue
        exe, args = os.path.basename(words[0]), words[1:]
        if exe == "cd":
            where = _join(where, args[0]) if args and args[0] != "-" else where
            continue
        if exe != "git":
            continue
        here, i = where, 0
        while i < len(args) and args[i].startswith("-"):
            opt = args[i]
            if opt == "-C" and i + 1 < len(args):
                here = _join(here, args[i + 1])
                i += 2
            elif opt in _GIT_OPTS_WITH_VALUE:
                i += 2
            else:
                i += 1       # --no-pager, -P, --bare, --git-dir=x, --work-tree=x …
        if i >= len(args):
            continue
        sub, rest = args[i], args[i + 1:]
        if "--help" in rest or "-h" in rest:
            continue
        if sub == "push" and not ({"--dry-run", "-n"} & set(rest)):
            found = {"kind": "push", "dir": here}
        elif sub == "pull" and "--dry-run" not in rest:
            found = {"kind": "pull", "dir": here}
    return found


def _short(name: str | None) -> str | None:
    if not name:
        return None
    for prefix in ("refs/heads/", "refs/tags/", "refs/remotes/"):
        if name.startswith(prefix):
            name = name[len(prefix):]
    return name[:LABEL_MAX]


def parse_push(output: str) -> dict:
    """What a push said: {"status", "branch", "old", "new", "src", "refs": n}. status is one of pushed, forced, new,
    tag, deleted, rejected, uptodate, unknown; the first branch ref wins over tags."""
    refs = []
    for line in output.splitlines():
        m = _REF_LINE.match(line)
        if not m:
            continue
        flag, what, src, dst, note = m.groups()
        if what.startswith("["):
            kind = what.strip("[]")
            status = ("rejected" if "rejected" in kind else "new" if kind == "new branch" else "tag" if kind == "new tag"
                      else "deleted" if kind == "deleted" else "unknown")
            old = new = None
        else:
            old, new = re.split(r"\.\.\.?", what)
            status = "forced" if flag == "+" else "pushed"
        is_tag = status == "tag" or (dst or src).startswith("refs/tags/")
        refs.append({"status": status, "old": old, "new": new, "src": src, "dst": dst or src, "tag": is_tag})
    if not refs:
        return {"status": "uptodate" if "Everything up-to-date" in output else "unknown", "branch": None, "refs": 0}
    main = next((r for r in refs if not r["tag"]), refs[0])
    return {"status": main["status"], "branch": _short(main["dst"]), "old": main["old"], "new": main["new"],
            "src": main["src"], "refs": len(refs)}


def parse_pull(output: str) -> dict:
    """What a pull said: {"status", "branch", "old", "new", "files", "ins", "dels"}. status: pulled, uptodate,
    conflict, failed, rebased, unknown."""
    out: dict = {"status": "unknown", "branch": None, "old": None, "new": None, "files": None, "ins": None, "dels": None}
    b = _FETCH_BRANCH.search(output) or _REBASED.search(output)
    out["branch"] = _short(b.group(1)) if b else None
    if re.search(r"Already up[ -]to[ -]date", output):
        out["status"] = "uptodate"
        return out
    if "CONFLICT" in output or "Automatic merge failed" in output:
        out["status"] = "conflict"
    elif re.search(r"^(fatal|error):", output, re.M):
        out["status"] = "failed"
        return out
    u = _UPDATING.search(output)
    if u:
        out["old"], out["new"] = u.group(1), u.group(2)
    stats = _STAT.findall(output)
    if stats:
        f, i, d = stats[-1]
        out["files"], out["ins"], out["dels"] = int(f), int(i or 0), int(d or 0)
    if out["status"] == "unknown":
        out["status"] = "rebased" if _REBASED.search(output) else "pulled" if (u or stats) else "unknown"
    return out


def _git(folder: str, *args: str, timeout: float = COUNT_TIMEOUT_SEC) -> str | None:
    """git, read-only, in folder: its stdout, or None on any failure (no repo, a timeout, git missing)."""
    if not folder or not os.path.isdir(folder):
        return None
    env = {**os.environ, "GIT_OPTIONAL_LOCKS": "0", "GIT_TERMINAL_PROMPT": "0", "GIT_PAGER": "cat", "LC_ALL": "C"}
    try:
        done = subprocess.run(["git", "-C", folder, *args], capture_output=True, text=True, timeout=timeout, env=env,
                              stdin=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout if done.returncode == 0 else None


def count_range(folder: str | None, old: str | None, new: str | None) -> dict | None:
    """{"commits", "files", "ins", "dels"} of old..new in folder, read without writing anything; None when unknown.
    old None (a new branch): from where new leaves origin's default branch, when that can be found."""
    if not folder or not new:
        return None
    if not old:
        head = _git(folder, "rev-parse", "--verify", "-q", "refs/remotes/origin/HEAD")
        base = _git(folder, "merge-base", new, head.strip()) if head else None
        if not base:
            return None
        old = base.strip()
    commits = _git(folder, "rev-list", "--count", f"{old}..{new}")
    stat = _git(folder, "diff", "--shortstat", f"{old}..{new}")
    if commits is None or stat is None:
        return None
    m = _STAT.search(stat)
    files, ins, dels = (int(m.group(1)), int(m.group(2) or 0), int(m.group(3) or 0)) if m else (0, 0, 0)
    return {"commits": int(commits.strip() or 0), "files": files, "ins": ins, "dels": dels}


def trip_of(command: str, cwd: str | None, response) -> dict | None:
    """The robot's trip for one finished Bash call (PostToolUse): kind, status, branch, the range and what to count;
    None when the command was not a push or a pull."""
    act = git_action(command, cwd)
    if act is None:
        return None
    if isinstance(response, dict):
        text = f"{response.get('stdout') or ''}\n{response.get('stderr') or ''}"
    else:
        text = str(response or "")
    info = parse_push(text) if act["kind"] == "push" else parse_pull(text)
    trip = {"kind": act["kind"], **{k: v for k, v in info.items() if k not in ("src", "refs")}}
    if act["kind"] == "pull" and info.get("files") is not None:
        trip["counted"] = {"commits": None, "files": info["files"], "ins": info["ins"], "dels": info["dels"]}
    want = act["kind"] == "push" and info["status"] in ("pushed", "forced", "new") or \
        act["kind"] == "pull" and info["status"] in ("pulled", "conflict") and info.get("old")
    if want:
        trip["_count"] = {"folder": act["dir"], "old": info.get("old"), "new": info.get("new") or info.get("src")}
    return trip


def label(trip: dict) -> str:
    """The short line over the robot, in the panel and in the log: ↑ main 3 コミット +120 −8."""
    arrow = "↑ push" if trip["kind"] == "push" else "↓ pull"
    branch = trip.get("branch") or ""          # an up-to-date pull does not say the branch: no name, not a "?"
    status = trip.get("status")
    if status == "uptodate":
        return f"{arrow} {branch + ' ' if branch else ''}— 変更なし"
    if status == "rejected":
        return f"{arrow} {branch + ' ' if branch else ''}— 突き返された"
    if status in ("failed", "conflict"):
        return f"{arrow} {branch + ' ' if branch else ''}— {'衝突' if status == 'conflict' else '失敗'}"
    if status == "deleted":
        return f"{arrow} {branch + ' ' if branch else ''}— 削除"
    if status == "tag":
        return f"{arrow} タグ {branch}"
    c = trip.get("counted") or {}
    parts = [f"{arrow}{' ' + branch if branch else ''}{'（新しいブランチ）' if status == 'new' else ''}{'（強制）' if status == 'forced' else ''}"]
    if c.get("commits") is not None:
        parts.append(f"{c['commits']} コミット")
    if c.get("ins") is not None:
        parts.append(f"+{c['ins']} −{c['dels']}")
    return " ".join(parts)
