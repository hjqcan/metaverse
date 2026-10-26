#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export WORLD_SCENARIO=postcards-v1
export WORLD_DATA_DIR="${WORLD_DATA_DIR:-$PWD/.local/postcards}"
export WORLD_URL="${WORLD_URL:-http://127.0.0.1:5083}"
exec bash scripts/run_world.sh
