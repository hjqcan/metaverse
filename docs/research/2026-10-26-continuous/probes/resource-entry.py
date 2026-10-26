#!/usr/bin/env python3
"""Research counterexample on an isolated real r7 service; never calls a model.

This is an experiment, not a product change or an independent release gate.
Run from any directory after building World.Server. Output defaults to .local.
"""
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[4]
sys.path[:0] = [str(ROOT / "tests"), str(ROOT / "scripts")]
import foundation_api
import activities_api
from activities_api import ActivityCandidate
from passage_agent import plan
from resident_mission import run_mission


def main():
    run = ROOT / ".local/research/resource-entry" / (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:6])
    run.mkdir(parents=True, mode=0o700)
    binary = ROOT / "src/World.Server/bin/Debug/net10.0"
    shutil.copytree(binary, run / "binary")
    foundation_api.DLL = run / "binary/World.Server.dll"
    activities_api.RUN_ROOT = run
    tracked = [ROOT / path for path in (
        "src/World.Server/WorldDatabase.cs", "src/World.Server/WorldService.cs",
        "src/World.Server/WorldScenario.cs", "scripts/resident_mission.py",
        "scripts/passage_agent.py", "scripts/foundation_agent.py")]
    hashes = lambda: {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in tracked}
    before_hashes = hashes()
    world = ActivityCandidate("legal-exhaustion", scenario="wilderness-v1")
    trace = []
    report = {
        "recordedAtUtc": datetime.now(timezone.utc).isoformat(),
        "baseCommit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "kind": "research-counterexample", "actualModelCalls": 0,
        "policy": "explicit-fixed-program", "worldScenario": "wilderness-v1",
        "sourceHashes": before_hashes,
        "assemblySha256": hashlib.sha256(foundation_api.DLL.read_bytes()).hexdigest(),
        "dataDirectory": str(world.data.relative_to(ROOT)),
        "scope": "a2 is a pre-existing resident acting later; no dynamic registration was tested",
    }

    def snapshot(client):
        observed = client.observe()
        return {"stateVersion": observed["stateVersion"], "self": {
            "actorId": observed["self"]["actorId"], "position": observed["self"]["position"],
            "inventory": observed["self"]["inventory"]}, "resourceAudit": observed["resourceAudit"],
            "resourceNodes": observed["resourceNodes"], "entities": observed["entities"]}

    def send(client, action, expected_status=200):
        observed = client.observe()
        command = {"schemaVersion": 1, "rulesVersion": observed["rulesVersion"],
                   "commandId": "probe_" + uuid.uuid4().hex,
                   "expectedStateVersion": observed["stateVersion"], "action": action}
        status, response = client.resolve(command)
        trace.append({"actorId": observed["self"]["actorId"], "request": command,
                      "httpStatus": status, "status": response.get("status"),
                      "stateVersion": response.get("stateVersion"),
                      "result": response.get("result"), "error": response.get("error")})
        assert status == expected_status, trace[-1]
        assert response["commandId"] == command["commandId"]
        assert response["identity"]["actorId"] == observed["self"]["actorId"]
        return response

    def walk(client, target):
        for _ in range(100):
            observed = client.observe()
            position = observed["self"]["position"]
            if position == list(target):
                return
            route = plan(observed, target, False)
            assert route and route[0], (position, target)
            nxt = route[0][0]
            send(client, {"type": "move", "dx": nxt[0] - position[0], "dy": nxt[1] - position[1]})
        raise AssertionError("bounded walk exhausted")

    def harvest(client, node_id):
        observed = client.observe()
        node = next(n for n in observed["resourceNodes"] if n["nodeId"] == node_id)
        x, y = node["position"]
        candidates = []
        for target in ((x + 1, y), (x, y + 1), (x - 1, y), (x, y - 1)):
            route = plan(observed, target, False)
            if route is not None:
                candidates.append((len(route[0]), target))
        assert candidates, node_id
        walk(client, min(candidates)[1])
        for _ in range(node["remainingWood"]):
            send(client, {"type": "gather", "nodeId": node_id})

    try:
        a, b = world.client("a1"), world.client("a2")
        report["initial"] = snapshot(a)
        spec = json.loads((ROOT / "examples/resident/builder.json").read_text())
        spec["missionId"] = "research-r7-existing-builder"
        choose = lambda _: {"goalId": "far-bank", "reason": "Explicit fixed research decision, not a model call.",
                            "provider": {"kind": "test-double", "model": "research-fixed", "usage": {}}}
        mission = run_mission(a, spec, world.data / "baseline-mission.json", choose)
        report["existingMission"] = {"status": mission["mission"]["status"],
            "reason": mission["mission"]["reason"], "used": mission["budget"]["used"],
            "worldVersionUnchanged": a.observe()["stateVersion"] == report["initial"]["stateVersion"]}
        assert report["existingMission"]["status"] == "blocked"
        assert report["existingMission"]["reason"] == "natural_material_collection_required"
        assert report["existingMission"]["worldVersionUnchanged"]

        for node in ("tree-west-north", "tree-west-south"):
            harvest(a, node)
        walk(a, (3, 3))
        send(a, {"type": "build", "recipeId": "bridge.v1", "at": [4, 3]})
        walk(a, (4, 3))
        send(a, {"type": "build", "recipeId": "bridge.v1", "at": [5, 3]})
        for node in ("tree-east-north", "tree-east-south"):
            harvest(a, node)
        report["afterEarlyResident"] = snapshot(a)
        audit = report["afterEarlyResident"]["resourceAudit"]
        assert audit == {"issuedWood": 12, "wildWood": 0, "depotWood": 0,
                         "inventoryWood": 6, "embodiedWood": 6, "conserved": True}
        report["laterResidentBefore"] = snapshot(b)
        failure = send(b, {"type": "build", "recipeId": "platform.v1", "at": [6, 6]}, 422)
        assert failure["error"]["code"] == "INSUFFICIENT_RESOURCE"
        report["laterBuildFailure"] = trace[-1]
        walk(b, (1, 1))
        walk(b, (6, 6))
        report["laterResidentAfter"] = snapshot(b)
        assert report["laterResidentAfter"]["self"]["inventory"]["wood"] == 0
        report["sharedBridgeStillUsable"] = True
        before_restart = snapshot(b)
        world.restart()
        report["restartPreservesState"] = snapshot(b) == before_restart
        assert report["restartPreservesState"]
    finally:
        world.stop()
        (world.data / "public-trace.json").write_text(json.dumps(trace, ensure_ascii=False, indent=2) + "\n")

    with sqlite3.connect(f"file:{world.data / 'world.db'}?mode=ro", uri=True) as db:
        balances = defaultdict(int)
        for src, dst, quantity in db.execute("SELECT source_account,destination_account,quantity FROM resource_ledger"):
            balances[src] -= quantity
            balances[dst] += quantity
        actors = dict(db.execute("SELECT actor_id,wood FROM residents"))
        entities = dict(db.execute("SELECT entity_id,embodied_wood FROM entities"))
        wild = db.execute("SELECT sum(remaining_wood) FROM resource_nodes").fetchone()[0]
        assert balances["initial-issuance"] == -12 and balances["wild-wood"] == wild == 0
        assert all(balances["inventory:" + a] == wood for a, wood in actors.items())
        assert all(balances["entity:" + e] == wood for e, wood in entities.items())
        assert sum(actors.values()) + sum(entities.values()) + wild == 12
        assert db.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
        report["stoppedDatabaseAudit"] = {"conserved": True, "wildWood": wild,
            "residentWood": actors, "embodiedWood": sum(entities.values()),
            "gatheredCommands": db.execute("SELECT count(*) FROM resource_ledger WHERE source_account='wild-wood'").fetchone()[0],
            "integrityCheck": "ok", "foreignKeyViolations": 0}
    report["sourceUnchangedDuringExperiment"] = before_hashes == hashes()
    assert report["sourceUnchangedDuringExperiment"]
    report["commands"] = len(trace)
    report["counterexampleConfirmed"] = True
    report["allExperimentProcessesStopped"] = world.process.poll() is not None
    path = run / "results.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print("Evidence:", path)
    print(json.dumps({key: report[key] for key in ("existingMission", "stoppedDatabaseAudit", "commands", "counterexampleConfirmed")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
