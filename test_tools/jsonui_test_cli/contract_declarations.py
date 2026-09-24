"""The declarations the contract-gap check reads, and their shape.

The check compares what an API declares (every response status of every
operation a screen reaches) against what the screen's branch contracts
cover. A plain set difference cannot tell "forgot to declare" from "does not
distinguish on purpose" — the absence means both — so the second meaning
needs a place to be written down. Three places, and this module is the one
reader of all of them:

- ``branchContracts.methods.<M>.excludedOutcomes`` —
  ``{"api.<op>": {"<status>": {by, reason, platforms?}}}``: this method
  reaches the operation but does not need a row for that status, and why.
  ``by`` is closed: ``unit`` (a unit test covers it), ``unreachable`` (the
  status cannot arrive here), ``unexpressible`` (only a note branch can say
  it). There is no ``distinguish: false`` — folding a status into another
  outcome is written as a row, which a generated test then checks — and no
  ``by: method``: delegating to another method is the claim the unit of
  coverage already refuses.
- ``branchContracts.unreachedOps`` — ``{"api.<op>": {reason, platforms?}}``:
  no contracted method on this screen calls the operation (the parent does,
  say). The generated tests verify the claim once calls are bounded.
- ``apiOutcomeRules`` in the app contracts spec — outcomes the APP handles
  for every screen (a 401 on an authenticated call signs out). Either a row
  template (``then``) that becomes a generated test per screen, or, as the
  last resort, ``vm: "not-reached"`` with where it is handled and which unit
  cases verify it.

Plus ``metadata.platforms`` on a screen: the platforms the screen exists on.

WHAT THIS CHECKS IS THE SHAPE, NOTHING ELSE. Keys, types, closed sets, and
references inside the same document (a ``verifiedBy`` name must be a unit
case the same file declares). Whether an excluded status is stale, whether
an op resolves, whether a rule's security scheme exists, whether a row and
an exclusion claim the same outcome — those need the OpenAPI document and
the rows, and belong to the coverage command. A shape error here is an
ERROR in ``jsonui-doc validate spec``, which imports this module inside the
check (never at module level), so a failed import is an ERROR on the
document that declares something, not a warning that swallows the whole
spec validation.

One parser for both readers — the spec validator and the coverage command —
so the two cannot accept different documents.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

#: The platforms a screen, an exclusion or an unreached op may be limited to.
PLATFORMS = ("ios", "android", "web")

#: `by` of an excluded outcome. Closed on purpose (see the module docstring).
EXCLUSION_BY = ("unit", "unreachable", "unexpressible")

#: The one `vm` value an outcome rule may carry.
RULE_VM = ("not-reached",)

#: Keys a rule's `then` may carry in v1. The value is checked against the
#: expanding screen's own `transitions[].destination` when the rule expands,
#: so the app spec carries no transition vocabulary of its own.
RULE_THEN_KEYS = ("transition",)

#: A response key as OpenAPI spells it: a status (`404`) or a range (`4XX`).
#: `default` is not a status and is refused with its own message.
_STATUS_KEY = re.compile(r"^[1-5](?:\d\d|XX)$")
_OP_KEY = re.compile(r"^api\.\S+$")

_EXCLUSION_KEYS = ("by", "reason", "platforms")
_UNREACHED_KEYS = ("reason", "platforms")
_RULE_KEYS = ("id", "statuses", "security", "then", "vm", "handledBy",
              "verifiedBy", "except", "reason")
_EXCEPT_KEYS = ("operationId", "reason")

APP_CONTRACTS_SPEC = "app_contracts_spec"


@dataclass(frozen=True)
class DeclarationError:
    path: str
    message: str


@dataclass(frozen=True)
class Exclusion:
    method: str
    op: str                   # as written, `api.` prefix removed
    status: str               # a status or a range key, as written
    by: str
    reason: str
    platforms: tuple | None   # None = every platform


@dataclass(frozen=True)
class UnreachedOp:
    op: str
    reason: str
    platforms: tuple | None


@dataclass(frozen=True)
class OutcomeRule:
    id: str
    statuses: tuple
    security: str | tuple     # "*" or scheme names
    then: dict | None
    vm: str | None
    handled_by: str | None
    verified_by: tuple
    exceptions: tuple         # ((operationId, reason), ...)
    reason: str


@dataclass
class Declarations:
    exclusions: list = field(default_factory=list)
    unreached_ops: list = field(default_factory=list)
    rules: list = field(default_factory=list)
    #: `metadata.platforms` of a screen; None = not declared.
    platforms: tuple | None = None
    errors: list = field(default_factory=list)


def parse_declarations(spec: dict) -> Declarations:
    """Every declaration in one spec document, and every shape error in them.

    An app contracts spec carries `apiOutcomeRules`; a screen document (any
    other type) carries the other three. A declaration in the wrong kind of
    document is an error rather than ignored: written but never read is the
    failure this vocabulary exists to prevent.
    """
    out = Declarations()
    if not isinstance(spec, dict):
        return out
    is_app = spec.get("type") == APP_CONTRACTS_SPEC
    if is_app:
        if "apiOutcomeRules" in spec:
            _parse_rules(spec["apiOutcomeRules"], _unit_case_names(spec), out)
        return out

    if "apiOutcomeRules" in spec:
        out.errors.append(DeclarationError(
            "apiOutcomeRules",
            f"apiOutcomeRules belongs in the {APP_CONTRACTS_SPEC} — it declares "
            "what the app does for every screen. A screen's own handling is "
            "a row in branchContracts, or methods.<M>.excludedOutcomes"))
    metadata = spec.get("metadata")
    if isinstance(metadata, dict) and "platforms" in metadata:
        out.platforms = _platforms(metadata["platforms"], "metadata.platforms", out,
                                   allow_absent=False)
    bc = spec.get("branchContracts")
    if not isinstance(bc, dict):
        return out
    if "unreachedOps" in bc:
        _parse_unreached(bc["unreachedOps"], out)
    methods = bc.get("methods")
    if isinstance(methods, dict):
        for name, contract in methods.items():
            if isinstance(contract, dict) and "excludedOutcomes" in contract:
                _parse_exclusions(name, contract["excludedOutcomes"], out)
    return out


# ---------------------------------------------------------------- helpers ---

def _err(out: Declarations, path: str, message: str) -> None:
    out.errors.append(DeclarationError(path, message))


def _nonempty_str(value) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _unknown_keys(obj: dict, allowed: tuple, path: str, out: Declarations) -> None:
    for key in obj:
        if key not in allowed:
            _err(out, f"{path}.{key}",
                 f"Unknown key — allowed: {', '.join(repr(k) for k in allowed)}")


def _platforms(value, path: str, out: Declarations, *, allow_absent=True):
    """A non-empty list of distinct platform names, or None when absent."""
    if value is None and allow_absent:
        return None
    if not isinstance(value, list) or not value:
        _err(out, path, "platforms must be a non-empty array of "
             f"{', '.join(repr(p) for p in PLATFORMS)} — omit it to mean every platform")
        return None
    seen: list = []
    for i, p in enumerate(value):
        if p not in PLATFORMS:
            _err(out, f"{path}[{i}]",
                 f"Unknown platform {p!r} — allowed: {', '.join(repr(x) for x in PLATFORMS)}")
        elif p in seen:
            _err(out, f"{path}[{i}]", f"Platform {p!r} is listed twice")
        else:
            seen.append(p)
    return tuple(seen) if seen else None


def _status_key(key, path: str, out: Declarations) -> bool:
    if key == "default":
        _err(out, path, "'default' is not a status — it is the catch-all "
             "response and is counted as n/a, never required. Name the "
             "status (\"404\") or the range (\"4XX\")")
        return False
    if not isinstance(key, str) or not _STATUS_KEY.match(key):
        hint = " (write it as a string, as OpenAPI does)" if isinstance(key, int) else ""
        _err(out, path, f"{key!r} is not a response key — a status such as "
             f"\"404\" or a range such as \"4XX\"{hint}")
        return False
    return True


def _op_key(key, path: str, out: Declarations) -> str | None:
    if not isinstance(key, str) or not _OP_KEY.match(key):
        _err(out, path, f"{key!r} must name an operation as 'api.<op>' — the "
             "same spelling a branch uses in when/then")
        return None
    return key[len("api."):]


# ------------------------------------------------------------ screen side ---

def _parse_exclusions(method: str, value, out: Declarations) -> None:
    base = f"branchContracts.methods.{method}.excludedOutcomes"
    if not isinstance(value, dict) or not value:
        _err(out, base, "excludedOutcomes must be a non-empty object of "
             "{\"api.<op>\": {\"<status>\": {by, reason}}} — omit it when "
             "nothing is excluded")
        return
    for op_key, statuses in value.items():
        op_path = f"{base}.{op_key}"
        op = _op_key(op_key, op_path, out)
        if not isinstance(statuses, dict) or not statuses:
            _err(out, op_path, "must be a non-empty object of "
                 "{\"<status>\": {by, reason, platforms?}}")
            continue
        for status, entry in statuses.items():
            path = f"{op_path}.{status}"
            ok = _status_key(status, path, out)
            if not isinstance(entry, dict):
                _err(out, path, "must be an object {by, reason, platforms?}")
                continue
            _unknown_keys(entry, _EXCLUSION_KEYS, path, out)
            by = entry.get("by")
            if by == "method":
                _err(out, f"{path}.by", "'method' is not an exclusion: this "
                     "method reaches the operation, so its own row can always "
                     "be written — write the row")
                ok = False
            elif by not in EXCLUSION_BY:
                _err(out, f"{path}.by", f"by must be one of "
                     f"{', '.join(repr(b) for b in EXCLUSION_BY)}, got {by!r}")
                ok = False
            if not _nonempty_str(entry.get("reason")):
                _err(out, f"{path}.reason", "reason is required — an exclusion "
                     "is a claim nothing checks, so it has to say why")
                ok = False
            platforms = _platforms(entry.get("platforms"), f"{path}.platforms", out)
            if ok and op is not None:
                out.exclusions.append(Exclusion(
                    method=method, op=op, status=status, by=by,
                    reason=entry["reason"], platforms=platforms))


def _parse_unreached(value, out: Declarations) -> None:
    base = "branchContracts.unreachedOps"
    if not isinstance(value, dict) or not value:
        _err(out, base, "unreachedOps must be a non-empty object of "
             "{\"api.<op>\": {reason, platforms?}} — omit it when every "
             "declared operation is reached")
        return
    for op_key, entry in value.items():
        path = f"{base}.{op_key}"
        op = _op_key(op_key, path, out)
        if not isinstance(entry, dict):
            _err(out, path, "must be an object {reason, platforms?}")
            continue
        _unknown_keys(entry, _UNREACHED_KEYS, path, out)
        ok = True
        if not _nonempty_str(entry.get("reason")):
            _err(out, f"{path}.reason", "reason is required — say which screen "
                 "or component calls this operation instead")
            ok = False
        platforms = _platforms(entry.get("platforms"), f"{path}.platforms", out)
        if ok and op is not None:
            out.unreached_ops.append(UnreachedOp(
                op=op, reason=entry["reason"], platforms=platforms))


# --------------------------------------------------------------- app side ---

def _unit_case_names(spec: dict) -> set:
    uc = spec.get("unitContracts")
    blocks = [uc] if isinstance(uc, dict) else (uc if isinstance(uc, list) else [])
    names = set()
    for block in blocks:
        if not isinstance(block, dict):
            continue
        for case in block.get("cases") or []:
            if isinstance(case, dict) and isinstance(case.get("name"), str):
                names.add(case["name"])
    return names


def _parse_rules(value, case_names: set, out: Declarations) -> None:
    base = "apiOutcomeRules"
    if not isinstance(value, list) or not value:
        _err(out, base, "apiOutcomeRules must be a non-empty array of rules — "
             "a block that declares nothing reads the same as no block at all")
        return
    ids: dict = {}
    for i, rule in enumerate(value):
        path = f"{base}[{i}]"
        if not isinstance(rule, dict):
            _err(out, path, f"must be an object, got {type(rule).__name__}")
            continue
        _unknown_keys(rule, _RULE_KEYS, path, out)
        ok = True

        rule_id = rule.get("id")
        if not _nonempty_str(rule_id):
            _err(out, f"{path}.id", "id is required (a name the report can cite)")
            ok = False
        elif rule_id in ids:
            _err(out, f"{path}.id", f"id {rule_id!r} is already used by {base}[{ids[rule_id]}]")
            ok = False
        else:
            ids[rule_id] = i

        statuses = rule.get("statuses")
        parsed_statuses: list = []
        if not isinstance(statuses, list) or not statuses:
            _err(out, f"{path}.statuses", "statuses must be a non-empty array "
                 "of response keys (\"401\", \"5XX\")")
            ok = False
        else:
            for j, s in enumerate(statuses):
                if not _status_key(s, f"{path}.statuses[{j}]", out):
                    ok = False
                elif s in parsed_statuses:
                    _err(out, f"{path}.statuses[{j}]", f"{s!r} is listed twice")
                    ok = False
                else:
                    parsed_statuses.append(s)

        security = rule.get("security")
        parsed_security = None
        if security == "*":
            parsed_security = "*"
        elif (isinstance(security, list) and security
              and all(_nonempty_str(s) for s in security)):
            if len(set(security)) != len(security):
                _err(out, f"{path}.security", "a scheme name is listed twice")
                ok = False
            parsed_security = tuple(security)
        else:
            _err(out, f"{path}.security", "security is required: scheme names "
                 "(\"bearerAuth\") or \"*\" for every operation. Leaving it out "
                 "would silently match operations that carry no credentials")
            ok = False

        has_then, has_vm = "then" in rule, "vm" in rule
        then = rule.get("then")
        vm = rule.get("vm")
        handled_by = rule.get("handledBy")
        verified_by = rule.get("verifiedBy")
        if has_then == has_vm:
            _err(out, path, "a rule carries exactly one of 'then' (a row template, "
                 "expanded into each screen's generated tests) or "
                 "'vm': \"not-reached\" (the last resort)")
            ok = False
        if has_then:
            if not isinstance(then, dict) or not then:
                _err(out, f"{path}.then", "then must be a non-empty object")
                ok = False
            else:
                for key, v in then.items():
                    if key not in RULE_THEN_KEYS:
                        _err(out, f"{path}.then.{key}", f"a rule's then may only "
                             f"carry {', '.join(repr(k) for k in RULE_THEN_KEYS)} — "
                             "a screen's own words (data.*) belong in that "
                             "screen's rows")
                        ok = False
                    elif not _nonempty_str(v):
                        _err(out, f"{path}.then.{key}", "must be a non-empty string")
                        ok = False
            for key in ("handledBy", "verifiedBy"):
                if key in rule:
                    _err(out, f"{path}.{key}", f"{key} goes with vm: \"not-reached\"; "
                         "a then rule is verified by the tests it expands into")
                    ok = False
        if has_vm:
            if vm not in RULE_VM:
                _err(out, f"{path}.vm", f"vm must be \"not-reached\", got {vm!r}")
                ok = False
            if not _nonempty_str(handled_by):
                _err(out, f"{path}.handledBy", "handledBy is required with "
                     "vm: \"not-reached\" — where the outcome is handled")
                ok = False
            if (not isinstance(verified_by, list) or not verified_by
                    or not all(_nonempty_str(v) for v in verified_by)):
                _err(out, f"{path}.verifiedBy", "verifiedBy is required with "
                     "vm: \"not-reached\": the names of unit cases in this "
                     "file's unitContracts that check the handling")
                ok = False
            else:
                for j, name in enumerate(verified_by):
                    if name not in case_names:
                        _err(out, f"{path}.verifiedBy[{j}]", f"{name!r} is not a "
                             "case in this file's unitContracts")
                        ok = False

        exceptions: list = []
        if "except" in rule:
            exc = rule["except"]
            if not isinstance(exc, list) or not exc:
                _err(out, f"{path}.except", "except must be a non-empty array of "
                     "{operationId, reason}")
                ok = False
            else:
                seen_ids: set = set()
                for j, entry in enumerate(exc):
                    epath = f"{path}.except[{j}]"
                    if not isinstance(entry, dict):
                        _err(out, epath, "must be an object {operationId, reason}")
                        ok = False
                        continue
                    _unknown_keys(entry, _EXCEPT_KEYS, epath, out)
                    op_id = entry.get("operationId")
                    if not _nonempty_str(op_id):
                        _err(out, f"{epath}.operationId", "operationId is required")
                        ok = False
                    elif op_id in seen_ids:
                        _err(out, f"{epath}.operationId", f"{op_id!r} is listed twice")
                        ok = False
                    else:
                        seen_ids.add(op_id)
                    if not _nonempty_str(entry.get("reason")):
                        _err(out, f"{epath}.reason", "reason is required")
                        ok = False
                    if _nonempty_str(op_id) and _nonempty_str(entry.get("reason")):
                        exceptions.append((op_id, entry["reason"]))

        if not _nonempty_str(rule.get("reason")):
            _err(out, f"{path}.reason", "reason is required — what the app does "
                 "with these outcomes, in one sentence")
            ok = False

        if ok:
            out.rules.append(OutcomeRule(
                id=rule_id, statuses=tuple(parsed_statuses), security=parsed_security,
                then=dict(then) if has_then else None, vm=vm if has_vm else None,
                handled_by=handled_by if has_vm else None,
                verified_by=tuple(verified_by) if has_vm else (),
                exceptions=tuple(exceptions), reason=rule["reason"]))
