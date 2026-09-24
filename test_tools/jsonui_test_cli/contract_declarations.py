"""The declarations the contract-gap check reads, and their shape.

The check compares what an API declares (every response status of every
operation a screen reaches) against what the screen's branch contracts
cover. A plain set difference cannot tell "forgot to declare" from "does not
distinguish on purpose" — the absence means both — so the second meaning
needs a place to be written down. This module is the one reader of every
such place:

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
- ``branchContracts.methods.<M>.branches[].alsoStatuses`` —
  ``{"api.<op>": ["401", "429"]}`` on a row: the row's ``then`` holds for
  these statuses of that operation too (the VM treats them alike). Each
  status becomes its own generated test, so the claim is checked rather
  than excluded. The key must be an ``api.<op>`` the row's ``when`` names
  with a scenario; statuses are plain numbers — no ranges, no ``default``.
- ``apiOutcomeRules`` in the app contracts spec —
  ``{id, statuses, sideCalls, verifiedBy, reason}``, all required: the
  HTTP calls the app's network layer makes on its own when a request ends
  in one of these statuses (a logout POST after a terminal 401), which a
  screen's generated test may therefore record. A rule only ADMITS those
  calls; it says nothing about how the screen handles the status. What the
  app does for every screen (sign out, an overlay, a refresh) is tested by
  ``unitContracts`` in the same file — ``verifiedBy`` names those cases —
  and is outside a screen's coverage.
- ``harnessConditions`` in the app contracts spec (design v4.11, P2d) —
  ``{"<name>": {values, default, reason}}``: a precondition outside the
  ViewModel that changes what it calls (a signed-in session), which a
  generated test cannot otherwise arrange. A row names one in its ``when``
  as ``"harness.<name>": "<value>"``; every generated test calls the
  consumer's ``arrangeCondition(name, value)`` for EVERY declared condition —
  the row's value or the ``default`` — after the mock goes in and before the
  harness is built. Not ``when.cond``, which names a
  ``branchContracts.conditions`` witness that writes ViewModel state — the
  key is ``harness.`` rather than ``condition.`` so the two do not read
  alike (ee, 2026-09-25).

Plus ``metadata.platforms`` on a screen: the platforms the screen exists on.

WHAT THIS CHECKS IS THE SHAPE, NOTHING ELSE. Keys, types, closed sets, and
references inside the same document (a ``verifiedBy`` name must be a unit
case the same file declares; an ``alsoStatuses`` key must be named in its
row's ``when``). Whether an excluded status is stale, whether an op or a
``sideCalls`` operationId resolves, whether a row and an exclusion claim the
same outcome — those need the OpenAPI document, the mocks and the rows, and
belong to the coverage command. A shape error here is an
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

#: A response key as OpenAPI spells it: a status (`404`) or a range (`4XX`).
#: `default` is not a status and is refused with its own message.
_STATUS_KEY = re.compile(r"^[1-5](?:\d\d|XX)$")
#: A plain status, for `alsoStatuses` and a rule's `statuses` (v1: a range
#: or `default` would make the generator read OpenAPI to know what it means).
_STATUS_NUMBER = re.compile(r"^[1-5]\d\d$")
_OP_KEY = re.compile(r"^api\.\S+$")
#: `VERB /path` — the spelling `sideCalls` does NOT take (operationIds only).
_VERB_PATH = re.compile(r"^[A-Za-z]+\s+/")
#: A harness condition's name: an identifier, because it is spelled inside a
#: `when` key (`harness.<name>`) and handed to three languages' hooks.
_CONDITION_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
#: The `when` key prefix a row names a harness condition with.
CONDITION_PREFIX = "harness."

_EXCLUSION_KEYS = ("by", "reason", "platforms")
_UNREACHED_KEYS = ("reason", "platforms")
_RULE_KEYS = ("id", "statuses", "sideCalls", "verifiedBy", "reason")
_CONDITION_KEYS = ("values", "default", "reason")
#: Rule keys of design v3, withdrawn in v4 (2026-09-24). Named so a rule
#: written to the old shape is told what happened, not just "unknown key".
_RULE_WITHDRAWN = ("then", "vm", "handledBy", "security", "except")

APP_CONTRACTS_SPEC = "app_contracts_spec"

#: Every place `parse_declarations` reads, as dotted paths (`*` = any method
#: name). The spec validator keeps its own copy for the one moment it cannot
#: import this module — to say that a declaring document could not be
#: checked — and an arm holds the two equal, so a site added here and not
#: there cannot go quiet on a machine without test_tools.
#: `[]` after a segment means "each element of that list".
DECLARATION_SITES = (
    "apiOutcomeRules",
    "harnessConditions",
    "metadata.platforms",
    "branchContracts.unreachedOps",
    "branchContracts.methods.*.excludedOutcomes",
    "branchContracts.methods.*.branches[].alsoStatuses",
)


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
class AlsoStatuses:
    method: str
    branch: int               # 0-based index into the method's branches
    op: str                   # as written, `api.` prefix removed
    statuses: tuple           # plain statuses, in the order written


@dataclass(frozen=True)
class OutcomeRule:
    id: str
    statuses: tuple           # plain statuses
    side_calls: tuple         # operationIds
    verified_by: tuple        # unit case names in the same file
    reason: str


@dataclass(frozen=True)
class HarnessCondition:
    name: str
    values: tuple             # two or more, in the order written
    default: str              # one of `values`
    reason: str


@dataclass(frozen=True)
class ConditionUse:
    """A row's `when` naming a harness condition (`harness.<name>`) — as written, not yet
    checked against the app's declaration (that needs both documents)."""
    method: str
    branch: int               # 0-based index into the method's branches
    name: str
    value: object             # a string when well-formed; checked by check_condition_uses


@dataclass
class Declarations:
    exclusions: list = field(default_factory=list)
    unreached_ops: list = field(default_factory=list)
    rules: list = field(default_factory=list)
    also_statuses: list = field(default_factory=list)
    #: `harnessConditions` of an app contracts spec, in declaration order;
    #: None = the key is absent (a screen document is always None).
    harness_conditions: list | None = None
    #: Every `harness.<name>` a screen's rows name.
    condition_uses: list = field(default_factory=list)
    #: `metadata.platforms` of a screen; None = not declared.
    platforms: tuple | None = None
    errors: list = field(default_factory=list)


def parse_declarations(spec: dict) -> Declarations:
    """Every declaration in one spec document, and every shape error in them.

    An app contracts spec carries `apiOutcomeRules`; a screen document (any
    other type) carries the rest. A declaration in the wrong kind of
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
        if "harnessConditions" in spec:
            _parse_harness_conditions(spec["harnessConditions"], out)
        return out

    if "apiOutcomeRules" in spec:
        out.errors.append(DeclarationError(
            "apiOutcomeRules",
            f"apiOutcomeRules belongs in the {APP_CONTRACTS_SPEC} — it admits "
            "the calls the app's network layer makes for every screen. A "
            "screen's own handling of a status is a row in branchContracts "
            "(alsoStatuses for statuses the row treats alike)"))
    if "harnessConditions" in spec:
        out.errors.append(DeclarationError(
            "harnessConditions",
            f"harnessConditions belongs in the {APP_CONTRACTS_SPEC} — the "
            "consumer's arrangeCondition hook is one per app, and every "
            "screen's rows name the conditions it declares"))
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
            if not isinstance(contract, dict):
                continue
            if "excludedOutcomes" in contract:
                _parse_exclusions(name, contract["excludedOutcomes"], out)
            branches = contract.get("branches")
            if isinstance(branches, list):
                for index, branch in enumerate(branches):
                    if isinstance(branch, dict) and "alsoStatuses" in branch:
                        _parse_also_statuses(name, index, branch, out)
                    if isinstance(branch, dict) and isinstance(branch.get("when"), dict):
                        for key, value in branch["when"].items():
                            if isinstance(key, str) and key.startswith(CONDITION_PREFIX):
                                out.condition_uses.append(ConditionUse(
                                    method=name, branch=index,
                                    name=key[len(CONDITION_PREFIX):], value=value))
    return out


def check_condition_uses(uses: list, conditions: list | None,
                         app_file: str | None = None) -> list:
    """The rows' `harness.<name>` against the app's `harnessConditions`.

    Needs both documents, so it is not part of `parse_declarations`: the
    generator and `contracts coverage` call it with the app spec they found
    (design v4.11 red-check xxviii). `conditions` None means no app contracts
    spec declares `harnessConditions`. Every error names the row and the key.
    """
    errors = []
    by_name = {c.name: c for c in (conditions or [])}
    for use in uses:
        where = (f"branchContracts.methods.{use.method}.branches[{use.branch}]"
                 f".when.{CONDITION_PREFIX}{use.name}")
        if conditions is None:
            errors.append(DeclarationError(where, (
                f"'{CONDITION_PREFIX}{use.name}' names a harness condition, and "
                f"no {APP_CONTRACTS_SPEC} declares harnessConditions — declare "
                f"'{use.name}' there with its values, default and reason")))
            continue
        condition = by_name.get(use.name)
        if condition is None:
            declared = ", ".join(repr(n) for n in by_name) or "none"
            errors.append(DeclarationError(where, (
                f"'{use.name}' is not a declared harness condition — "
                f"harnessConditions{f' in {app_file}' if app_file else ''} "
                f"declares: {declared}")))
            continue
        if use.value not in condition.values:
            errors.append(DeclarationError(where, (
                f"{use.value!r} is not a value of harness condition "
                f"'{use.name}' — allowed: "
                f"{', '.join(repr(v) for v in condition.values)}")))
    return errors


def arranged_conditions(conditions: list | None, when: dict) -> list:
    """`[(name, value)]` for EVERY declared condition, in declaration order:
    the row's value when it names one, else the condition's `default`.

    Every one, not only those the row names: a condition left to the
    harness's bare state would make `default` mean whatever that happens to
    be. `[]` when the app declares none — and then nothing is emitted.
    """
    if not conditions:
        return []
    when = when if isinstance(when, dict) else {}
    return [(c.name, when.get(f"{CONDITION_PREFIX}{c.name}", c.default))
            for c in conditions]


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


def _plain_status(value, path: str, out: Declarations, what: str) -> bool:
    """A plain status string ("429"). Ranges and `default` are refused (v1)."""
    if value == "default":
        _err(out, path, f"'default' is not a status — {what} takes plain "
             "statuses such as \"500\"")
        return False
    if isinstance(value, str) and _STATUS_KEY.match(value) and "XX" in value:
        _err(out, path, f"{value!r} is a range — {what} takes plain statuses "
             "(v1: a range would make the generator read OpenAPI to know which "
             "statuses it stands for). List the statuses")
        return False
    if not isinstance(value, str) or not _STATUS_NUMBER.match(value):
        hint = " (write it as a string, as OpenAPI does)" if isinstance(value, int) else ""
        _err(out, path, f"{value!r} is not a status such as \"429\"{hint}")
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


def _parse_also_statuses(method: str, index: int, branch: dict, out: Declarations) -> None:
    base = f"branchContracts.methods.{method}.branches[{index}].alsoStatuses"
    value = branch["alsoStatuses"]
    if "note" in branch:
        _err(out, base, "alsoStatuses cannot sit on a note branch — a note has "
             "no when/then to repeat for another status")
        return
    if not isinstance(value, dict) or not value:
        _err(out, base, "alsoStatuses must be a non-empty object of "
             "{\"api.<op>\": [\"<status>\", ...]} — omit it when the row "
             "stands for its own scenario only")
        return
    when = branch.get("when") if isinstance(branch.get("when"), dict) else {}
    for op_key, statuses in value.items():
        path = f"{base}.{op_key}"
        op = _op_key(op_key, path, out)
        ok = op is not None
        if ok and not isinstance(when.get(op_key), str):
            _err(out, path, f"{op_key!r} must be named in this row's when with a "
                 "scenario — alsoStatuses repeats that when for other statuses "
                 "of the same operation")
            ok = False
        if not isinstance(statuses, list) or not statuses:
            _err(out, path, "must be a non-empty array of statuses (\"429\")")
            continue
        seen: list = []
        for j, status in enumerate(statuses):
            spath = f"{path}[{j}]"
            if not _plain_status(status, spath, out, "alsoStatuses"):
                ok = False
            elif status in seen:
                _err(out, spath, f"{status!r} is listed twice")
                ok = False
            else:
                seen.append(status)
        if ok:
            out.also_statuses.append(AlsoStatuses(
                method=method, branch=index, op=op, statuses=tuple(seen)))


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
        ok = True
        for key in rule:
            if key in _RULE_KEYS:
                continue
            ok = False
            if key in _RULE_WITHDRAWN:
                _err(out, f"{path}.{key}", f"{key!r} was withdrawn (design v4, "
                     "2026-09-24): a rule only admits the calls the network "
                     "layer makes on these statuses. How a screen handles a "
                     "status is a row in its branchContracts; what the app does "
                     "for every screen is a unit case here, named in verifiedBy")
            else:
                _err(out, f"{path}.{key}", "Unknown key — allowed: "
                     f"{', '.join(repr(k) for k in _RULE_KEYS)}")

        rule_id = rule.get("id")
        if not _nonempty_str(rule_id):
            _err(out, f"{path}.id", "id is required (a name the report can cite)")
            ok = False
        elif rule_id in ids:
            _err(out, f"{path}.id", f"id {rule_id!r} is already used by {base}[{ids[rule_id]}]")
            ok = False
        else:
            ids[rule_id] = i

        statuses = _string_list(rule.get("statuses"), f"{path}.statuses", out,
                                "statuses is required: the plain statuses (\"401\") "
                                "on which the side calls may appear")
        if statuses is None:
            ok = False
        else:
            for j, status in enumerate(statuses):
                if not _plain_status(status, f"{path}.statuses[{j}]", out, "a rule's statuses"):
                    ok = False

        side_calls = _string_list(rule.get("sideCalls"), f"{path}.sideCalls", out,
                                  "sideCalls is required: the operationIds the network "
                                  "layer calls on these statuses")
        if side_calls is None:
            ok = False
        else:
            for j, op_id in enumerate(side_calls):
                if not _nonempty_str(op_id):
                    _err(out, f"{path}.sideCalls[{j}]", "must be a non-empty operationId")
                    ok = False
                elif _VERB_PATH.match(op_id):
                    _err(out, f"{path}.sideCalls[{j}]", f"{op_id!r} is a 'VERB /path' — "
                         "sideCalls take the OpenAPI operationId, so there is one "
                         "spelling to resolve")
                    ok = False

        verified_by = _string_list(rule.get("verifiedBy"), f"{path}.verifiedBy", out,
                                   "verifiedBy is required: the unit cases in this "
                                   "file's unitContracts that test the network layer's "
                                   "handling")
        if verified_by is None:
            ok = False
        else:
            for j, name in enumerate(verified_by):
                if not _nonempty_str(name):
                    _err(out, f"{path}.verifiedBy[{j}]", "must be a non-empty case name")
                    ok = False
                elif name not in case_names:
                    _err(out, f"{path}.verifiedBy[{j}]", f"{name!r} is not a case in "
                         "this file's unitContracts")
                    ok = False

        if not _nonempty_str(rule.get("reason")):
            _err(out, f"{path}.reason", "reason is required — what the network "
                 "layer does on these statuses, in one sentence")
            ok = False

        if ok:
            out.rules.append(OutcomeRule(
                id=rule_id, statuses=tuple(statuses), side_calls=tuple(side_calls),
                verified_by=tuple(verified_by), reason=rule["reason"]))


def _parse_harness_conditions(value, out: Declarations) -> None:
    base = "harnessConditions"
    if not isinstance(value, dict) or not value:
        _err(out, base, "harnessConditions must be a non-empty object of "
             "{\"<name>\": {values, default, reason}} — omit it when the app "
             "has none")
        out.harness_conditions = []
        return
    conditions: list = []
    for name, entry in value.items():
        path = f"{base}.{name}"
        ok = True
        if not isinstance(name, str) or not _CONDITION_NAME.match(name):
            _err(out, path, f"{name!r} is not a condition name — a letter, then "
                 "letters, digits or '_' (it is spelled in a when key as "
                 f"'{CONDITION_PREFIX}<name>' and passed to arrangeCondition)")
            ok = False
        if not isinstance(entry, dict):
            _err(out, path, "must be an object {values, default, reason}")
            continue
        if any(key not in _CONDITION_KEYS for key in entry):
            # Refused, as a rule with an unknown key is: a misspelt field is
            # a field nothing reads.
            _unknown_keys(entry, _CONDITION_KEYS, path, out)
            ok = False
        values = entry.get("values")
        if not isinstance(values, list) or len(values) < 2:
            _err(out, f"{path}.values", "values must be an array of two or more "
                 "strings — a condition with one value arranges nothing a row "
                 "could choose")
            ok = False
            values = []
        seen: list = []
        for j, v in enumerate(values):
            if not _nonempty_str(v):
                _err(out, f"{path}.values[{j}]", f"{v!r} is not a non-empty string")
                ok = False
            elif v in seen:
                _err(out, f"{path}.values[{j}]", f"{v!r} is listed twice")
                ok = False
            else:
                seen.append(v)
        default = entry.get("default")
        if "default" not in entry:
            _err(out, f"{path}.default", "default is required: the value every "
                 "row that does not name this condition is arranged with")
            ok = False
        elif default not in seen:
            _err(out, f"{path}.default", f"{default!r} is not one of values "
                 f"({', '.join(repr(v) for v in seen) or 'none'})")
            ok = False
        if not _nonempty_str(entry.get("reason")):
            _err(out, f"{path}.reason", "reason is required — what outside the "
                 "ViewModel this condition stands for, and why a row cannot "
                 "arrange it through the mocks")
            ok = False
        if ok:
            conditions.append(HarnessCondition(
                name=name, values=tuple(seen), default=default,
                reason=entry["reason"]))
    out.harness_conditions = conditions


def _string_list(value, path: str, out: Declarations, missing: str):
    """A non-empty list without repeats, or None (with the error recorded)."""
    if value is None:
        _err(out, path, missing)
        return None
    if not isinstance(value, list) or not value:
        _err(out, path, "must be a non-empty array")
        return None
    seen: list = []
    ok = True
    for j, item in enumerate(value):
        if item in seen:
            _err(out, f"{path}[{j}]", f"{item!r} is listed twice")
            ok = False
        else:
            seen.append(item)
    return seen if ok else None
