#!/bin/bash
#
# Wait for CI on ONE named SHA, and require EVERY run on it to be green.
#
# Usage: wait-for-ci.sh <sha> [branch] [budget-seconds]
#
# Hand-typed three releases running, each time as
# `[.[] | select(.headSha==$SHA)][0].databaseId` -- which takes the FIRST
# matching run and waits only on that. One workflow exists today, so the
# loop has never been wrong; it has also never been checked. A re-run, or a
# second workflow added later, would make it report green off one arm while
# another was still running or already red, and nothing would say so.
#
# A consumer lane hit the two-run case for real (a tag SHA carrying both a
# release-check run and a main run) and adopted "do not treat one green as
# the answer when several runs exist on the SHA". This is that rule, here.
#
# Exits: 0 all runs on the SHA completed successfully
#        1 some run did not succeed (named)
#        2 no run appeared, or the budget ran out (said plainly, not green)
set -u

SHA="${1:?usage: wait-for-ci.sh <sha> [branch] [budget-seconds]}"
BRANCH="${2:-release-check}"
BUDGET="${3:-900}"
DEADLINE=$(( $(date +%s) + BUDGET ))

runs_json() {
    gh run list --branch "$BRANCH" --limit 30 \
        --json databaseId,headSha,name,status,conclusion \
        --jq "[.[] | select(.headSha==\"$SHA\")]"
}

# Appearing at all is the first thing that can fail: a workflow whose
# trigger does not include this branch produces an empty list forever, and
# an empty list must never read as "nothing failed".
while [ "$(date +%s)" -lt "$DEADLINE" ]; do
    count="$(runs_json | jq 'length')"
    [ "$count" -gt 0 ] 2>/dev/null && break
    sleep 10
done
count="$(runs_json | jq 'length')"
if [ "${count:-0}" -eq 0 ]; then
    echo "NO RUN on $SHA (branch $BRANCH) within ${BUDGET}s." >&2
    echo "  Check the workflow's branch triggers before reading this as calm." >&2
    exit 2
fi
echo "runs on $SHA: $count"

while [ "$(date +%s)" -lt "$DEADLINE" ]; do
    pending="$(runs_json | jq '[.[] | select(.status != "completed")] | length')"
    [ "${pending:-1}" -eq 0 ] && break
    sleep 20
done

runs_json | jq -r '.[] | "  \(.databaseId)  \(.name)  \(.status)  \(.conclusion // "-")"'

incomplete="$(runs_json | jq '[.[] | select(.status != "completed")] | length')"
if [ "${incomplete:-1}" -ne 0 ]; then
    echo "STILL RUNNING after ${BUDGET}s — not green, just unfinished." >&2
    exit 2
fi
failed="$(runs_json | jq -r '[.[] | select(.conclusion != "success") | .databaseId] | join(" ")')"
if [ -n "$failed" ]; then
    echo "NOT GREEN: run(s) $failed did not succeed on $SHA" >&2
    exit 1
fi
echo "ALL $count run(s) green on $SHA"
