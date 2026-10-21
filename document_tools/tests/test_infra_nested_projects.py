"""Another project inside the project is left out by jui.config.json's infra.exclude (ticket
doc-infra-check-walks-into-nested-projects, 2.3.17).

The root's walk (iac_tables.walk_project: seed and the infra-iac / infra-code checks alike) read a nested product's
compose and code, and the root's room got that product's services as missing_in_doc. A folder of its own
(jui.config.json, its own git) is no sure sign: measured 10-22, a project's own apps in their own repositories look the
same as another product. So the project lists it: infra.exclude. A folder that looks like a project of its own and is
not listed is walked as before, and said once.
"""
from __future__ import annotations

import json
from pathlib import Path

from jsonui_doc_cli.check import infra_check as C
from jsonui_doc_cli.infra import iac_tables as T
from jsonui_doc_cli.infra import room as R
from jsonui_doc_cli.infra import seed as S
from jsonui_doc_cli.project_config import load_checks

NODES = [{"id": "api", "category": "compute.container", "provider": "docker", "iac": ["docker-compose.yml#services.api"]}]
FILES = {
    "docker-compose.yml": "services:\n  api:\n    build: .\n",
    # another product, in its own repository (a submodule's .git is a file) with its own JsonUI project
    "other-product/jui.config.json": "{}",
    "other-product/.git": "gitdir: ../.git/modules/other-product\n",
    "other-product/docker-compose.yml": "services:\n  web:\n    build: .\n  db:\n    image: postgres:17\n",
    "other-product/backend/docker-compose.yml": "services:\n  worker:\n    build: .\n",
    "other-product/web/firebase.ts": "import { initializeApp } from 'firebase/app'\n",
    # a part of this project with a JsonUI project of its own: walked, said once
    "app-part/jui.config.json": "{}",
    "app-part/src/pay.py": "import stripe\n",
}
OTHER = {"docker/docker-compose.yml#services.web", "docker/docker-compose.yml#services.db"}


def _room(tmp_path: Path, infra: dict | None = None) -> Path:
    root = tmp_path / "proj"
    (root / "docs" / "infra").mkdir(parents=True)
    (root / "docs" / "infra" / "m.json").write_text(json.dumps({"version": 0, "nodes": NODES}))
    for rel, text in FILES.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text)
    cfg = {"checks": [{"name": "iac", "type": "builtin:infra-iac"}, {"name": "code", "type": "builtin:infra-code"}]}
    if infra is not None:
        cfg["infra"] = infra
    (root / "jui.config.json").write_text(json.dumps(cfg))
    return root


def _check(root: Path, name: str):
    decl = {d.name: d for d in load_checks(json.loads((root / "jui.config.json").read_text()), root)}[name]
    return (C.run_infra_iac if name == "iac" else C.run_infra_code)(decl, root)


def _missing(rep) -> list[str]:
    return sorted(r.target for r in rep.results if r.status in ("missing_in_doc", "warning") and r.actual)


def test_another_projects_services_are_missing_in_doc_unless_it_is_excluded(tmp_path):
    """The ticket's shape: without infra.exclude the nested product's three services are missing_in_doc in the root's
    room (2.3.16, and still with no list); listed, none, and the root's own service is ok."""
    walked = _check(_room(tmp_path / "a"), "iac")
    assert [t for t in _missing(walked) if t.startswith("docker/")] == [
        "docker/other-product/backend/docker-compose.yml#services.worker",
        "docker/other-product/docker-compose.yml#services.db", "docker/other-product/docker-compose.yml#services.web"]
    listed = _check(_room(tmp_path / "b", {"exclude": ["other-product"]}), "iac")
    assert _missing(listed) == [] and {r.target: r.status for r in listed.results}["docker/api"] == "ok"


def test_the_root_counts_nothing_inside_an_excluded_folder(tmp_path):
    """Its files are not walked (seed and both checks): no IaC, no code hint, no seeded node from it."""
    root = _room(tmp_path, {"exclude": ["other-product/"]})
    assert R.infra_exclude(root) == ["other-product"]
    rels, _stopped = T.walk_project(root, [root / p for p in R.infra_exclude(root)])
    assert [r for r, _ in rels if r.startswith("other-product/")] == [] and "app-part/src/pay.py" in [r for r, _ in rels]
    items, _u = C.scan_iac(root)
    assert sorted(i["address"] for i in items) == ["docker-compose.yml#services.api"]
    hints, _n = C.scan_code(root)
    assert {h["file"].split("/")[0] for h in hints} == {"app-part"}
    out = root / "seed-out"   # the command, as a person runs it: it reads infra.exclude itself
    assert S.run(root, out_dir=out, echo=lambda *_a: None, err=lambda *_a: None) == 0
    doc = json.loads((out / S.DRAFT_NAME).read_text())
    assert doc["nodes"]          # the root's own compose service is seeded
    assert not [n for n in doc["nodes"] for ev in n.get("evidence") or [] if ev["file"].startswith("other-product/")]
    assert not [n for n in doc["nodes"] if any(a.startswith("other-product/") for a in n.get("iac") or [])]


def test_a_folder_that_looks_like_a_project_is_walked_and_said_once(tmp_path):
    root = _room(tmp_path)
    rep = _check(root, "code")
    said = [w for w in rep.warnings if "infra.exclude" in w]
    assert len(said) == 2 and any(w.startswith("[unverified] *: app-part/ has its own jui.config.json") for w in said)
    assert any("other-product/ has its own jui.config.json and its own git" in w for w in said)
    # listed: walked no more, said no more
    root2 = _room(tmp_path / "x", {"exclude": ["other-product"]})
    said2 = [w for w in _check(root2, "iac").warnings + _check(root2, "code").warnings if "infra.exclude" in w]
    assert said2 and all("other-product" not in w for w in said2)


def test_a_listed_folder_that_is_not_there_or_points_outside_is_said_by_validate(tmp_path):
    root = _room(tmp_path, {"exclude": ["gone", "../elsewhere", 3, "other-product"]})
    got = R.read(root)
    by = {p["path"]: p for p in got["problems"] if p["code"] == "config.exclude"}
    assert by["/infra/exclude/0"]["severity"] == "warning" and "no such folder" in by["/infra/exclude/0"]["message"]
    assert by["/infra/exclude/1"]["severity"] == by["/infra/exclude/2"]["severity"] == "error"
    assert "/infra/exclude/3" not in by and R.infra_exclude(root) == ["other-product"]
