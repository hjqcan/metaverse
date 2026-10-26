#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export WORLD_URL="${WORLD_URL:-http://127.0.0.1:5091}"
export WORLD_ACCESS_FILE="${WORLD_ACCESS_FILE:-$PWD/.local/material-access/access.json}"
export WORLD_CLIENT_STATE="${WORLD_CLIENT_STATE:-user://material-access-pending.json}"
exec bash scripts/run_godot.sh "$@"
