#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ -n "${GODOT_BIN:-}" ]]; then
  godot_binary="$(command -v "$GODOT_BIN" || true)"
else
  godot_binary="$PWD/.local/tools/godot/Godot_v4.7.2-stable_linux.x86_64"
  if [[ ! -x "$godot_binary" ]]; then
    godot_binary="$(command -v godot || command -v godot4 || true)"
  fi
fi
if [[ -z "$godot_binary" || ! -x "$godot_binary" ]]; then
  echo 'Install Godot 4.7.2 or set GODOT_BIN to its executable.' >&2
  exit 1
fi
export WORLD_URL="${WORLD_URL:-http://127.0.0.1:5089}"
export WORLD_ACCESS_FILE="${WORLD_ACCESS_FILE:-$PWD/.local/continuous/access.json}"
export WORLD_ACTOR="${WORLD_ACTOR:-a1}"
exec "$godot_binary" --path clients/godot "$@"
