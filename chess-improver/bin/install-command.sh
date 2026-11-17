#!/usr/bin/env bash
# Installs the repo-local `chess` launcher onto the user's PATH.
set -euo pipefail
SCRIPT_DIR="$(cd -P "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$SCRIPT_DIR/chess" install
