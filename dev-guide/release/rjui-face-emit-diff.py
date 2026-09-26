#!/usr/bin/env python3
"""Build web faces with two rjui trees and compare what they emit, byte for byte.

    dev-guide/release/rjui-face-emit-diff.py --a 9f0bd629 --b WORKTREE FACE_DIR [FACE_DIR ...]

A face is a directory holding `rjui.config.json`. For each tree (a git ref of
this repository, or `WORKTREE` for the files as they are) the face's layouts
and config are copied into a scratch project with that tree's rjui_tools
(links dereferenced) and built; the generated components and data models are
compared file by file. Nothing is written into the face.

Why it exists: on 2026-09-26 the position stamp rjui's generator puts on every
node (2de6da9b) made a data-only element `{ "data": [...] }` render as an empty
<div /> on every web face that declares its data that way. The suites were
green — no spec drew such a layout — and only rebuilding the faces and
comparing the bytes showed it. A change that is meant to leave the faces
alone is claimed with this script's `0`, and a change that is meant to move
them lists every line that moved, to be matched to its intent.

Exit: 0 every face built on both trees and emitted the same bytes; 1 some
file differs (each is printed, with its changed lines under --lines); 2 a
build failed on either tree, so that face was NOT compared (it is named).
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))


def tree_copy(ref, into):
    os.makedirs(into)
    if ref == 'WORKTREE':
        for part in ('rjui_tools', 'shared'):
            shutil.copytree(os.path.join(REPO, part), os.path.join(into, part), symlinks=True,
                            ignore=shutil.ignore_patterns('spec', 'node_modules'))
    else:
        archive = subprocess.run(['git', '-C', REPO, 'archive', ref, 'rjui_tools', 'shared'],
                                 check=True, capture_output=True).stdout
        subprocess.run(['tar', '-x', '-C', into], input=archive, check=True)


def build(face, tool_tree, into):
    config = json.load(open(os.path.join(face, 'rjui.config.json'), encoding='utf-8'))
    layouts = config.get('layouts_directory') or 'src/Layouts'
    os.makedirs(into)
    shutil.copytree(os.path.join(face, layouts), os.path.join(into, layouts))
    json.dump(config, open(os.path.join(into, 'rjui.config.json'), 'w', encoding='utf-8'))
    subprocess.run(['cp', '-RL', os.path.join(tool_tree, 'rjui_tools'), into], check=True)
    env = dict(os.environ, LANG='en_US.UTF-8', LC_ALL='en_US.UTF-8')
    run = subprocess.run(['ruby', os.path.join(into, 'rjui_tools', 'bin', 'rjui'), 'build'],
                         cwd=into, env=env, capture_output=True, text=True)
    out = {}
    for key, default in (('components_directory', 'src/generated/components'),
                         ('data_directory', 'src/generated/data')):
        root = os.path.join(into, config.get(key) or default)
        for dirpath, _, files in os.walk(root):
            for name in files:
                path = os.path.join(dirpath, name)
                out[os.path.relpath(path, into)] = open(path, 'rb').read()
    return run.returncode, out


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--a', required=True, help='git ref, or WORKTREE')
    parser.add_argument('--b', required=True, help='git ref, or WORKTREE')
    parser.add_argument('--lines', action='store_true', help='print the changed lines of each file')
    parser.add_argument('faces', nargs='+')
    args = parser.parse_args()

    scratch = tempfile.mkdtemp(prefix='rjui_face_emit_')
    trees = {}
    for side, ref in (('a', args.a), ('b', args.b)):
        trees[side] = os.path.join(scratch, 'tree_' + side)
        tree_copy(ref, trees[side])

    status = 0
    for face in args.faces:
        face = os.path.abspath(face)
        name = face.replace('/', '_')
        (rc_a, a), (rc_b, b) = (build(face, trees[s], os.path.join(scratch, s, name)) for s in ('a', 'b'))
        if rc_a != 0 or rc_b != 0:
            print(f'NOT COMPARED {face}: build exit {rc_a} on {args.a}, {rc_b} on {args.b}')
            status = max(status, 2)
            continue
        moved = sorted(k for k in set(a) | set(b) if a.get(k) != b.get(k))
        print(f'{face}: {len(set(a) | set(b))} files, {len(moved)} differ')
        for path in moved:
            print(f'  {path}')
            if args.lines:
                old = (a.get(path) or b'').decode('utf-8', 'replace').splitlines()
                new = (b.get(path) or b'').decode('utf-8', 'replace').splitlines()
                for line in sorted(set(old) - set(new)):
                    print(f'    - {line.strip()}')
                for line in sorted(set(new) - set(old)):
                    print(f'    + {line.strip()}')
        if moved:
            status = max(status, 1)
    shutil.rmtree(scratch, ignore_errors=True)
    return status


if __name__ == '__main__':
    sys.exit(main())
