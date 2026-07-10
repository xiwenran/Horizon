#!/usr/bin/env bash
# Horizon local run (no git pull, no gh-pages deploy)
# Usage: ./scripts/local-run.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

log() {
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"
}

cd "$PROJECT_DIR"

log "Starting Horizon local run..."

# uv is resolved via PATH (the launchd plist provides it; interactive shells already have it)
uv run horizon --hours 24

log "Done."
