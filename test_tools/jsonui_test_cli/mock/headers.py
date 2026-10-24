"""A scenario's response headers (ticket 2026-10-24-jsonui-test-mock-scenario-cannot-set-response-headers).

`"headers": {"Retry-After": "30"}` on a scenario is sent with its response — by `mock serve` and by the three
runtimes `generate branch-tests` writes — so a branch that reads a header (a wait from `Retry-After`, a file name
from `Content-Disposition`, an inquiry number from `X-Request-ID`) can be a row. One rule here, read by the
validator, the server and the branch-test emitter, so a header one of them sends is one each of them sends.

Not sent: a name that is not an HTTP token, a value that is not a string or holds a line break (written as is, it
would end the header and start another), and `Content-Type` / `Content-Length`, which the scenario's `contentType`
and the body decide.
"""

from __future__ import annotations

import re

#: RFC 9110's token: the characters a header's name is made of.
_TOKEN = re.compile(r"^[!#$%&'*+.^_`|~0-9A-Za-z-]+\Z")
#: Names the server writes itself, from `contentType` and the body.
RESERVED = ("content-type", "content-length")


def header_problems(headers) -> list[str]:
    """Why each entry of a scenario's `headers` is not sent (empty: all are)."""
    if not isinstance(headers, dict):
        return ["'headers' must be an object of header names to string values"]
    problems = []
    for name, value in headers.items():
        if not isinstance(name, str) or not _TOKEN.match(name):
            problems.append(f"{name!r} is not a header name (letters, digits and !#$%&'*+.^_`|~-)")
        elif name.lower() in RESERVED:
            problems.append(f"{name!r} is written by the server — set the scenario's 'contentType' "
                            "(Content-Type) or its body (Content-Length) instead")
        elif not isinstance(value, str):
            problems.append(f"{name!r}: a header's value is a string, got {value!r}")
        elif "\r" in value or "\n" in value:
            problems.append(f"{name!r}: a header's value must not hold a line break")
    return problems


def served_headers(scenario) -> dict:
    """The headers a scenario's response is sent with: the entries `header_problems` passes, in their order."""
    headers = scenario.get("headers") if isinstance(scenario, dict) else None
    if not isinstance(headers, dict):
        return {}
    return {name: value for name, value in headers.items() if not header_problems({name: value})}
