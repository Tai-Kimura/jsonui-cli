"""The currency (plan, 依頼者の決め 4): USD only. jui.config.json's infra.currency may name a converter for later —
{"plugin": "<module>:<function>"} or {"rates": "<a JSON inside the room>"} — and this version reads only its shape:
nothing is loaded, every amount stays USD, and a configured converter is said to be unused."""
from __future__ import annotations

import re
from pathlib import Path

from .. import room as R

PLUGIN = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*:[A-Za-z_][A-Za-z0-9_]*$")


def config(root: Path) -> tuple[dict | None, list[str]]:
    """(the converter's setting, or None, and warnings). A setting of the wrong shape is a warning and not used."""
    try:
        infra = R._infra_section(Path(root)) or {}
    except R.Refused as r:
        return None, [f"jui.config.json cannot be read: {r.message}"]
    cfg = infra.get("currency")
    if cfg is None:
        return None, []
    if not isinstance(cfg, dict) or len(cfg) != 1 or not (
            isinstance(cfg.get("plugin"), str) and PLUGIN.match(cfg["plugin"])
            or isinstance(cfg.get("rates"), str) and R._rel_ok(cfg["rates"])):
        return None, ['infra.currency must be {"plugin": "<module>:<function>"} or {"rates": "<a path in the room>"}']
    return cfg, ["infra.currency is set, but this version converts nothing: amounts are USD"]


def convert(usd: float | None, cfg: dict | None) -> dict:
    """The amount to show: {"usd": usd} — and, when a converter is used (a later version), its currency and value."""
    return {"usd": usd}
