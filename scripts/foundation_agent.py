#!/usr/bin/env python3
"""A bounded, deterministic resident using only the world's public HTTP API."""

import argparse
from collections import deque
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import time
import urllib.error
import urllib.request
import uuid


INSTANCE_HEADER = "World-Instance-Id"


def valid_world_instance(value):
    return isinstance(value, str) and re.fullmatch(r"w_[0-9a-f]{32}", value) is not None


class WorldBindingError(RuntimeError):
    """No conclusion about the original command may be drawn from this response."""


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class WorldClient:
    def __init__(self, url, token, world="foundation-01"):
        self.url = url.rstrip("/")
        self.token = token
        self.prefix = f"/v1/worlds/{world}"
        self.world_instance_id = None
        self.binding_observed = False
        self.response_instance_id = None
        self._opener = urllib.request.build_opener(_NoRedirect())

    def bind_instance(self, instance_id):
        """Pin a saved mission's identity before observing or recovering it.

        None means an explicitly unbound legacy mission, not permission to adopt
        whatever instance currently occupies its previous URL.
        """
        if instance_id is not None and not valid_world_instance(instance_id):
            raise WorldBindingError("Invalid persisted world instance")
        if self.binding_observed and self.world_instance_id != instance_id:
            raise WorldBindingError("Client is already bound to another world")
        self.world_instance_id = instance_id
        self.binding_observed = True

    def request(self, method, path, payload=None, headers=None):
        body = json.dumps(payload).encode() if payload is not None else None
        world_request = path.startswith("/v1/")
        request_headers = {"Authorization": "Bearer " + self.token, "Content-Type": "application/json"}
        if world_request and self.world_instance_id is not None:
            request_headers[INSTANCE_HEADER] = self.world_instance_id
        for key, value in (headers or {}).items():
            if key.lower() == INSTANCE_HEADER.lower() and self.binding_observed and value != self.world_instance_id:
                raise WorldBindingError("Cannot override the pinned world instance")
            request_headers[key] = value
        request = urllib.request.Request(
            self.url + path, data=body, method=method,
            headers=request_headers,
        )
        try:
            response = self._opener.open(request, timeout=10)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            values = response.headers.get_all(INSTANCE_HEADER, [])
            self.response_instance_id = values[0] if len(values) == 1 and valid_world_instance(values[0]) else None
            if values and self.response_instance_id is None:
                raise WorldBindingError("Malformed world instance response")
            if world_request and self.world_instance_id is not None and response.status != 401 and response.status < 500:
                if self.response_instance_id != self.world_instance_id or response.status in (412, 428):
                    raise WorldBindingError("World instance response does not match the original world")
            raw = response.read()
            return response.status, json.loads(raw) if raw else None

    def observe(self):
        status, result = self.request("GET", self.prefix + "/observation")
        if status != 200:
            raise RuntimeError(f"Observation failed: HTTP {status}, {result.get('error', {}).get('code')}")
        instance = result.get("world", {}).get("instanceId")
        capability = result.get("commandBinding")
        if instance is not None or capability is not None or self.response_instance_id is not None:
            if (not valid_world_instance(instance) or self.response_instance_id != instance
                    or capability != {"version": 1, "required": True, "header": INSTANCE_HEADER}):
                raise WorldBindingError("Observation has inconsistent world instance binding")
        if self.binding_observed and self.world_instance_id != instance:
            raise WorldBindingError("Observation belongs to a different world")
        self.bind_instance(instance)
        return result

    def command(self, intent):
        return self.request("POST", self.prefix + "/commands", intent)

    def resolve(self, intent):
        """A transport failure does not create a fresh intention or command ID."""
        last_error = None
        for attempt in range(3):
            try:
                if attempt:
                    status, result = self.request("GET", self.prefix + "/commands/" + intent["commandId"])
                    if status != 404 or not isinstance(result, dict) or (result.get("error") or {}).get("code") != "COMMAND_NOT_FOUND":
                        return status, result
                return self.command(intent)
            except (OSError, urllib.error.URLError) as error:
                last_error = type(error).__name__
                time.sleep(0.2 * (attempt + 1))
        raise RuntimeError(f"Command outcome unknown; keep {intent['commandId']} for recovery ({last_error})")


def route(start, goal, width, height, blocked):
    start, goal = tuple(start), tuple(goal)
    forbidden = {tuple(cell) for cell in blocked}
    queue = deque([start])
    previous = {start: None}
    # Fixed tie-break order makes the policy deterministic for a given observation.
    for_current = ((1, 0), (0, 1), (-1, 0), (0, -1))
    while queue:
        cell = queue.popleft()
        if cell == goal:
            path = []
            while previous[cell] is not None:
                parent = previous[cell]
                path.append((cell[0] - parent[0], cell[1] - parent[1]))
                cell = parent
            return list(reversed(path))
        for dx, dy in for_current:
            candidate = cell[0] + dx, cell[1] + dy
            if (0 <= candidate[0] < width and 0 <= candidate[1] < height
                    and candidate not in forbidden and candidate not in previous):
                previous[candidate] = cell
                queue.append(candidate)
    raise RuntimeError("Goal is unreachable in the observed map")


def run_resident(client, command_budget=100, seconds_budget=600):
    started = time.monotonic()
    started_at = datetime.now(timezone.utc).isoformat()
    trace = []
    initial = client.observe()
    observed = initial
    for _ in range(command_budget):
        if time.monotonic() - started >= seconds_budget:
            raise RuntimeError("Resident time budget exhausted")
        world = observed["world"]
        if observed["self"]["position"] == world["goal"]:
            return {
                "policy": "fixed-bfs-v1", "actorId": observed["self"]["actorId"],
                "startedAtUtc": started_at,
                "initial": initial, "trace": trace, "final": observed,
                "commands": len(trace), "elapsedSeconds": time.monotonic() - started,
                "modelCalls": 0, "goalReached": True,
            }
        dx, dy = route(observed["self"]["position"], world["goal"], world["width"], world["height"], world["blocked"])[0]
        intent = {
            "schemaVersion": 1, "rulesVersion": observed["rulesVersion"],
            "commandId": uuid.uuid4().hex, "expectedStateVersion": observed["stateVersion"],
            "action": {"type": "move", "dx": dx, "dy": dy},
        }
        status, result = client.resolve(intent)
        trace.append({"request": intent, "httpStatus": status, "response": result})
        if status != 200 and not (status == 409 and result["error"]["code"] == "STALE_STATE"):
            raise RuntimeError(f"Resident action rejected: HTTP {status}, {result.get('error')}")
        observed = client.observe()
    raise RuntimeError("Resident command budget exhausted")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:5080")
    parser.add_argument("--access-file", type=Path, default=Path(".local/world/access.json"))
    parser.add_argument("--actor", choices=("a1", "a2"), default="a2")
    parser.add_argument("--output", type=Path, default=Path(".local/world/resident-trace.json"))
    args = parser.parse_args()
    access = json.loads(args.access_file.read_text())
    token = access["sessions"][args.actor]["token"]
    result = run_resident(WorldClient(args.url, token))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"actorId": args.actor, "goalReached": result["goalReached"], "commands": result["commands"], "output": str(args.output)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
