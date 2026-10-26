#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
export WORLD_DATA_DIR="${WORLD_DATA_DIR:-$PWD/.local/world}"
export WORLD_URL="${WORLD_URL:-http://127.0.0.1:5080}"
# Fault injection belongs to dedicated test instances, never the normal preview.
export WORLD_ENABLE_FAULTS=0
dotnet restore src/World.Server/World.Server.csproj --locked-mode
dotnet build src/World.Server/World.Server.csproj --no-restore
exec dotnet src/World.Server/bin/Debug/net10.0/World.Server.dll
