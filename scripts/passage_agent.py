#!/usr/bin/env python3
"""Bounded public-API resident: least-material bridge route and a round trip."""

import argparse
from datetime import datetime, timezone
import heapq
import itertools
import json
import os
from pathlib import Path
import time
import uuid

from foundation_agent import WorldClient


def plan(observed, goal, allow_build):
    """Lexicographic Dijkstra: new bridge cells, then moves, then fixed order."""
    world = observed["world"]
    start, goal = tuple(observed["self"]["position"]), tuple(goal)
    blocked = {tuple(p) for p in world["blocked"]}
    water = {tuple(p) for p in world.get("water", [])}
    bridgeable = blocked & water if allow_build else set()
    order = itertools.count()
    queue = [(0, 0, next(order), start)]
    best, previous = {start: (0, 0)}, {start: None}
    while queue:
        bridges, steps, _, cell = heapq.heappop(queue)
        if (bridges, steps) != best[cell]:
            continue
        if cell == goal:
            cells = []
            while previous[cell] is not None:
                cells.append(cell)
                cell = previous[cell]
            return list(reversed(cells)), bridges
        for dx, dy in ((1, 0), (0, 1), (-1, 0), (0, -1)):
            nxt = cell[0] + dx, cell[1] + dy
            if not (0 <= nxt[0] < world["width"] and 0 <= nxt[1] < world["height"]):
                continue
            if nxt in blocked and nxt not in bridgeable:
                continue
            cost = bridges + int(nxt in bridgeable), steps + 1
            if nxt not in best or cost < best[nxt]:
                best[nxt], previous[nxt] = cost, cell
                heapq.heappush(queue, (*cost, next(order), nxt))
    return None


def run_trip(client, allow_build=False, command_budget=100, seconds_budget=600, pending_path=None):
    started = time.monotonic()
    initial = client.observe()
    observed = initial
    origin = initial["self"]["position"]
    goal = initial["world"]["goal"]
    actor = initial["self"]["actorId"]
    trace, reached = [], False
    binding = {"url": client.url, "world": initial["world"]["id"], "actorId": actor}
    pending_path = Path(pending_path) if pending_path else None

    def finish(outcome, reason=None):
        return {"policy": "least-material-bridge-v1" if allow_build else "walk-only-v1",
                "actorId": actor, "outcome": outcome, "reason": reason, "origin": origin, "goal": goal,
                "startedAtUtc": started_at, "initial": initial, "final": observed,
                "trace": trace, "commands": len(trace), "goalReached": reached,
                "roundTripCompleted": outcome == "completed", "modelCalls": 0,
                "elapsedSeconds": time.monotonic() - started}

    def save_pending(intent):
        if pending_path:
            pending_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = pending_path.with_suffix(pending_path.suffix + ".tmp")
            with os.fdopen(os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w") as stream:
                json.dump({**binding, "request": intent, "trip": {"origin": origin, "goal": goal, "reached": reached}}, stream)
                stream.flush()
                os.fsync(stream.fileno())
            temporary.replace(pending_path)

    started_at = datetime.now(timezone.utc).isoformat()
    pending = None
    if pending_path and pending_path.exists():
        saved = json.loads(pending_path.read_text())
        if any(saved.get(key) != value for key, value in binding.items()):
            raise ValueError("Pending command belongs to a different endpoint/world/actor")
        # Command recovery must retain the trip's meaning as well as its command ID.
        # Re-basing the return leg at the current position would silently shorten the task.
        trip = saved.get("trip")
        if not isinstance(trip, dict) or not isinstance(trip.get("reached"), bool):
            raise ValueError("Pending command has no recoverable trip context")
        for cell in (trip.get("origin"), trip.get("goal")):
            if (not isinstance(cell, list) or len(cell) != 2
                    or any(type(value) is not int or value < 0 or value >= 8 for value in cell)):
                raise ValueError("Pending trip coordinates are invalid")
        origin, goal, reached = trip["origin"], trip["goal"], trip["reached"]
        pending = saved["request"]

    for _ in range(command_budget):
        if time.monotonic() - started >= seconds_budget:
            return finish("budget_exhausted", "time")
        recovery = pending is not None
        if not recovery:
            position = observed["self"]["position"]
            if position == goal:
                reached = True
            target = origin if reached else goal
            if reached and position == origin:
                return finish("completed")
            route = plan(observed, target, allow_build)
            if route is None:
                return finish("blocked", "no_route")
            cells, new_bridges = route
            recipes = {r["id"]: r for r in observed.get("recipes", [])}
            if new_bridges and "bridge.v1" not in recipes:
                return finish("blocked", "bridge_recipe_unavailable")
            wood_needed = new_bridges * recipes.get("bridge.v1", {}).get("woodCost", 3)
            inventory = observed["self"]["inventory"]["wood"]
            if wood_needed > inventory:
                quantity = wood_needed - inventory
                if observed["depot"]["wood"] < quantity:
                    return finish("blocked", "insufficient_public_material")
                depot = observed["depot"]["position"]
                if sum(abs(a-b) for a, b in zip(position, depot)) <= 1:
                    action = {"type": "claim", "quantity": quantity}
                else:
                    depot_route = plan(observed, depot, False)
                    if depot_route is None:
                        return finish("blocked", "depot_unreachable")
                    nxt = depot_route[0][0]
                    action = {"type": "move", "dx": nxt[0]-position[0], "dy": nxt[1]-position[1]}
            else:
                nxt = cells[0]
                if nxt in {tuple(p) for p in observed["world"]["blocked"]}:
                    action = {"type": "build", "recipeId": "bridge.v1", "at": list(nxt)}
                else:
                    action = {"type": "move", "dx": nxt[0]-position[0], "dy": nxt[1]-position[1]}
            pending = {"schemaVersion": 1, "rulesVersion": observed["rulesVersion"],
                       "commandId": uuid.uuid4().hex, "expectedStateVersion": observed["stateVersion"],
                       "action": action}
            save_pending(pending)
        try:
            if recovery:
                status, result = client.request("GET", client.prefix + "/commands/" + pending["commandId"])
                if status == 404:
                    status, result = client.resolve(pending)
            else:
                status, result = client.resolve(pending)
        except (OSError, RuntimeError) as error:
            trace.append({"request": pending, "transportError": type(error).__name__})
            return finish("unknown", "pending_command_retained")
        trace.append({"request": pending, "httpStatus": status, "response": result, "recovery": recovery})
        if status >= 500 or (result.get("error") and result["error"].get("mutated") is None):
            return finish("unknown", "pending_command_retained")
        # Expired credentials do not resolve an earlier command's outcome.
        if status == 401:
            return finish("unknown", "session_required_for_recovery")
        if pending_path:
            pending_path.unlink(missing_ok=True)
        pending = None
        observed = client.observe()
        if status != 200 and not (status == 409 and result["error"]["code"] in ("STALE_STATE", "CELL_OCCUPIED")):
            return finish("rejected", result.get("error", {}).get("code"))
    return finish("budget_exhausted", "commands")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:5081")
    parser.add_argument("--access-file", type=Path, default=Path(".local/passage/access.json"))
    parser.add_argument("--actor", choices=("a1", "a2"), default="a2")
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--output", type=Path, default=Path(".local/passage/resident-trace.json"))
    args = parser.parse_args()
    token = json.loads(args.access_file.read_text())["sessions"][args.actor]["token"]
    result = run_trip(WorldClient(args.url, token), args.build, pending_path=args.output.with_suffix(".pending.json"))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({k: result[k] for k in ("actorId", "outcome", "commands", "modelCalls")}, ensure_ascii=False))
    return 0 if result["outcome"] in ("completed", "blocked") else 1


if __name__ == "__main__":
    raise SystemExit(main())
