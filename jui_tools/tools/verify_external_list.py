"""The fix list a consumer lane gets from `jui verify`'s externally authored layout check (ticket 2026-10-21-jui-
verify-skips-every-consumer-screen): one line per name the spec does not declare — the screen's spec, the name, the
kind, the layout file and where to declare it. Read from `jui verify --json`'s externalFindings, so the list and the
report's WARNING are one computation (the arm counts both).

    cd <the lane> && jui verify --json /tmp/v.json
    python3 tools/verify_external_list.py /tmp/v.json <the lane> > list.md
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

KINDS = {"binding": "binding", "data": "data", "cellData": "cellData にしか無い", "elsewhere": "data に入らない欄にしか無い"}
_ELSEWHERE = re.compile(r"declared only in (\S+), which never goes into the data section")


def kind_of(finding: dict) -> str:
    if "stateManagement.cellData" in finding["why"]:
        return "cellData"
    return "elsewhere" if _ELSEWHERE.search(finding["why"]) else finding["kind"]


def is_handler(finding: dict) -> bool:
    """onSaveTap, pagerOnNextTap (an include's handler, spelled with its id in front), or a data entry typed as a
    function."""
    return bool(re.search(r"(^on|[a-z0-9]On)[A-Z]", finding["name"])) or "->" in finding["why"]


def where_to(finding: dict) -> str:
    """Every name a layout binds goes in stateManagement.uiVariables: the layout's bindings resolve against the data
    section `jui g project` writes from them (layout_generator), and a screen's eventHandlers are view-local — never
    in that data, and doc validate wants them named ^on[A-Z], which an include's prefixed handler is not. A handler
    takes a callback type."""
    m = _ELSEWHERE.search(finding["why"])
    moved = ("（cellData から移す）" if kind_of(finding) == "cellData"
             else f"（{m.group(1)} の宣言は残してよい）" if m else "")
    if is_handler(finding):
        return f'stateManagement.uiVariables（型 "(() -> Void)?"）{moved}'
    return f"stateManagement.uiVariables{moved}"


def spec_paths(root: Path) -> dict[str, Path]:
    """spec stem ("home.spec") -> its path, under the lane's spec_directory."""
    cfg = json.loads((root / "jui.config.json").read_text(encoding="utf-8"))
    spec_dir = (root / cfg.get("spec_directory", "docs/screens/json")).resolve()
    return {p.name[:-len(".json")]: p for p in sorted(spec_dir.rglob("*.spec.json"))}


def scope(root: Path) -> dict:
    """What was counted: the spec folder as the lane's config names it, the glob, the specs by type, the parents' sub
    specs, and the specs that write stateManagement.cellData (in the same folder only)."""
    cfg = json.loads((root / "jui.config.json").read_text(encoding="utf-8"))
    spec_dir = cfg.get("spec_directory", "docs/screens/json")
    types, parents, cell = {}, {}, []
    for stem, path in spec_paths(root).items():
        data = json.loads(path.read_text(encoding="utf-8"))
        types[data.get("type")] = types.get(data.get("type"), 0) + 1
        if data.get("type") == "screen_parent_spec":
            parents[stem] = [e.get("file") for e in data.get("subSpecs") or [] if isinstance(e, dict)]
        if '"cellData"' in path.read_text(encoding="utf-8"):
            cell.append(os.path.relpath(path, root.resolve()))
    return {"spec_dir": spec_dir, "types": types, "parents": parents, "cellData": sorted(cell)}


def rows(summary: dict, root: Path) -> list[dict]:
    specs, parents = spec_paths(root), scope(root)["parents"]
    out = []
    for stem, findings in sorted(summary.get("externalFindings", {}).items()):
        path = specs.get(stem)
        layout = None
        if path is not None:
            layout = (json.loads(path.read_text(encoding="utf-8")).get("metadata") or {}).get("layoutFile")
        rel = os.path.relpath(path, root.resolve()) if path is not None else stem   # as the lane's config spells it
        for f in findings:
            if stem in parents:
                rel += "（親、sub spec を merge した後）"
            out.append({"spec": rel, "name": f["name"], "kind": kind_of(f), "layout": f"{layout}.json" if layout else "?",
                        "where": where_to(f), "why": f["why"]})
    return out


def render(lane: str, summary: dict, items: list[dict], sc: dict | None = None, where: str = "") -> str:
    lines = [f"# {lane}: jui verify の外部 Layout の照合で、spec に宣言の無い名前", "",
             f"- 照合した画面: {summary.get('externalChecked')} / {summary.get('externalTotal')}、"
             f"見つけた名前: {len(items)}（画面 {len(summary.get('externalFindings', {}))}）",
             "- 決まり: include の中の束縛は、含める側の画面の spec が、include の id を前に付けた名前で宣言する。"
             "stateManagement.cellData は宣言にならない（jui は読まない）。",
             "- 直し方: 各行の名前を「足す先」の欄に宣言する（型と説明を付ける）。Layout はそのまま。"
             "使っていない名前なら、Layout から消してもよい。",
             "- 足す先が stateManagement.uiVariables なのは、Layout の束縛が jui g project の作る data 節（uiVariables から作る）"
             "に解決するため。依頼者の決め（10-21 02:53「ビューで使わない値はdataに入っちゃダメよ」）で、data 節に入らない欄"
             "（dataFlow.viewModel の vars・methods、stateManagement.eventHandlers）にしか無い名前は宣言と数えない。そこにある宣言は"
             "残したまま、uiVariables にも宣言すればよい。", ""]
    if sc is not None:
        t = sc["types"]
        lines += ["## 数えた範囲", "",
                  f"- spec: {where}{sc['spec_dir']}/**/*.spec.json（jui.config.json の spec_directory）。Layout は layouts_directory。"
                  "ほかのフォルダ（別の subproject、worktree、html）は数えない。",
                  f"- spec の種類: screen_spec {t.get('screen_spec', 0)}、screen_parent_spec {t.get('screen_parent_spec', 0)}、"
                  f"screen_sub_spec {t.get('screen_sub_spec', 0)}（親に merge して数える。別の行にはしない）、"
                  f"それ以外（app_contracts_spec など、画面でない物）{sum(n for k, n in t.items() if k not in ('screen_spec', 'screen_parent_spec', 'screen_sub_spec'))}（数えない）。",
                  f"- stateManagement.cellData を書いている spec: {len(sc['cellData'])} 本"
                  + (f"（{', '.join(sc['cellData'])}）" if sc["cellData"] else "") + "。", ""]
        if sc["parents"]:
            lines += ["### sub spec を持つ親", "",
                      "verify は sub spec を親に merge した 1 画面として照合する。親の行の名前は、親の Layout が include する sub spec の "
                      "Layout から来た物もある。宣言は親でも、その名前を使う sub spec でもよい（どちらも merge される）。", ""]
            lines += [f"- {stem}: {', '.join(subs)}" for stem, subs in sorted(sc["parents"].items())] + [""]
    if summary.get("externalNotChecked"):
        lines += ["## 照合できなかった画面", ""]
        lines += [f"- {k}: {v}" for k, v in sorted(summary["externalNotChecked"].items())] + [""]
    lines += ["## 一覧", "", "| spec | 名前 | 種類 | Layout | 足す先 |", "|---|---|---|---|---|"]
    lines += [f"| {r['spec']} | `{r['name']}` | {KINDS[r['kind']]} | {r['layout']} | {r['where']} |" for r in items]
    return "\n".join(lines) + "\n"


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) < 2:
        print(__doc__, file=sys.stderr)
        return 2
    summary = json.loads(Path(argv[0]).read_text(encoding="utf-8"))
    root = Path(argv[1])
    lane = argv[2] if len(argv) > 2 else root.name
    where = argv[3] if len(argv) > 3 else ""
    sys.stdout.write(render(lane, summary, rows(summary, root), scope(root), where))
    return 0


if __name__ == "__main__":
    sys.exit(main())
