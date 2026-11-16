#!/bin/sh
# Convenience wrapper: codegen all conformance fixtures into this host.
# See scripts/generate.mjs for options (JSONUI_CONFORMANCE_DIR, RJUI_TOOLS_PATH).
set -e
cd "$(dirname "$0")"
node scripts/generate.mjs "$@"
