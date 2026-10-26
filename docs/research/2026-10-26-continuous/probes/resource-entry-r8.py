#!/usr/bin/env python3
"""Repeat the material-entry counterexample in a protected continuous r8 world.

All movement, collection and construction use actual HTTP commands. No model,
privileged material mutation, existing preview or shared source edit is used.
"""
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[4]
sys.path[:0] = [str(ROOT / "tests"), str(ROOT / "scripts")]
import foundation_api
import activities_api
import continuous_navigation
from activities_api import ActivityCandidate


def main():
    run = ROOT / ".local/research/resource-entry-r8" / (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:6])
    run.mkdir(parents=True, mode=0o700)
    shutil.copytree(ROOT / "src/World.Server/bin/Debug/net10.0", run / "binary")
    foundation_api.DLL = run / "binary/World.Server.dll"
    activities_api.RUN_ROOT = run
    source_paths = [ROOT / "scripts/continuous_navigation.py", ROOT / "scripts/foundation_agent.py"]
    source_hashes = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in source_paths}
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    world = ActivityCandidate("material-entry", scenario="wilderness-continuous-v1")
    trace = []
    positions_b = []
    try:
        a, b = world.client(), world.client("a2")
        initial = a.observe()
        initial_b = b.observe()
        assert initial["world"]["instanceId"] == initial_b["world"]["instanceId"]
        assert initial["commandBinding"]["required"] is True
        actor_b_start = initial_b["self"]["position"]

        def send(client, action, expected=200):
            observed = client.observe()
            request = {"schemaVersion": 1, "rulesVersion": "r8", "commandId": "research_" + uuid.uuid4().hex,
                       "expectedStateVersion": observed["stateVersion"], "action": action}
            status, reply = client.command(request)
            assert status == expected, (status, reply)
            trace.append({"actorId": observed["self"]["actorId"], "request": request, "status": status, "response": reply})
            if expected == 200:
                assert reply["status"] == "committed"
                assert reply["stateVersion"] == observed["stateVersion"] + 1
            return reply

        def walk(client, target):
            deadline = time.monotonic() + 90
            for _ in range(400):
                observed = client.observe()
                if observed["self"]["actorId"] == "a2":
                    positions_b.append(observed["self"]["position"])
                if math.dist(observed["self"]["position"], target) <= 0.06:
                    return observed
                assert time.monotonic() < deadline, ("walk timeout", target)
                plan = continuous_navigation.route_info(observed, target, False, False)
                assert plan["reason"] is None and plan["nextAction"], (target, plan)
                time.sleep(observed["movement"]["maxStepDistance"] / observed["movement"]["speed"])
                reply = send(client, plan["nextAction"])
                assert reply["result"]["action"] == "walk" and not reply["result"]["blocked"], reply
            raise AssertionError("walk command bound exhausted")

        def gather(node):
            observed = a.observe()
            point = next(item["position"] for item in observed["resourceNodes"] if item["nodeId"] == node)
            start = observed["self"]["position"]
            if math.dist(start, point) > 1.5:
                nav = continuous_navigation.navigation(observed)
                candidates = []
                for index in range(24):
                    angle = 2 * math.pi * index / 24
                    target = [point[0] + 1.2 * math.cos(angle), point[1] + 1.2 * math.sin(angle)]
                    path = nav.route(start, target)
                    if path is not None:
                        candidates.append((continuous_navigation.path_length(start, path), target))
                assert candidates, ("no reachable gathering position", node)
                walk(a, min(candidates)[1])
            for _ in range(3):
                reply = send(a, {"type": "gather", "nodeId": node})
                assert reply["result"]["quantity"] == 1

        gather("tree-west-north")
        gather("tree-west-south")
        assert a.observe()["self"]["inventory"]["wood"] == 6
        print("West material collected: 6", flush=True)
        walk(a, [15.7, 12.0])
        bridge = send(a, {"type": "build", "recipeId": "bridge.v1", "at": [18.0, 12.0]})
        walk(a, [20.7, 12.0])
        gather("tree-east-north")
        gather("tree-east-south")
        exhausted_a, exhausted_b = a.observe(), b.observe()
        assert exhausted_a["resourceAudit"] == {"issuedWood": 12, "wildWood": 0, "depotWood": 0,
            "inventoryWood": 6, "embodiedWood": 6, "conserved": True}
        assert exhausted_a["self"]["inventory"]["wood"] == 6
        assert exhausted_b["self"]["inventory"]["wood"] == 0
        print("All four trees depleted legally; A holds 6, bridge embodies 6", flush=True)
        denied = send(b, {"type": "build", "recipeId": "platform.v1", "at": [26.0, 17.0]}, expected=422)
        assert denied["error"]["code"] == "INSUFFICIENT_RESOURCE" and denied["error"]["mutated"] is False
        assert b.observe()["stateVersion"] == exhausted_b["stateVersion"]
        walk(b, [15.0, 12.0])
        returned = walk(b, actor_b_start)
        assert returned["self"]["inventory"]["wood"] == 0
        assert any(16.6 <= p[0] <= 19.4 and 11.5 <= p[1] <= 12.5 for p in positions_b)
        print("B crossed the public bridge and returned with zero material", flush=True)
        before_restart = a.observe()
        world.restart()
        after_restart = a.observe()
        assert before_restart == after_restart
        report = {"recordedAtUtc": datetime.now(timezone.utc).isoformat(),
                  "kind": "actual-http-resource-entry-counterexample", "scenario": "wilderness-continuous-v1",
                  "repositoryHeadAtRun": head, "assemblySha256": hashlib.sha256(foundation_api.DLL.read_bytes()).hexdigest(),
                  "sourceHashesAtStart": source_hashes,
                  "sourceFilesUnchangedDuringRun": all(source_hashes[str(p.relative_to(ROOT))] == hashlib.sha256(p.read_bytes()).hexdigest() for p in source_paths),
                  "actualModelCalls": 0, "nativeClientExecuted": False, "persistentMissionExecuted": False,
                  "protectedInstance": True, "worldInstanceId": initial["world"]["instanceId"],
                  "actualCommands": len(trace), "gatheredWood": sum(1 for t in trace if t["status"] == 200 and t["request"]["action"]["type"] == "gather"),
                  "aInventoryWoodAfterExhaustion": 6, "bInventoryWoodAfterExhaustion": 0,
                  "resourceAudit": exhausted_a["resourceAudit"], "bridgeReceipt": bridge,
                  "bPlatformRejected": {"httpStatus": 422, "code": denied["error"]["code"], "stateUnchanged": True},
                  "bPublicCrossing": {"start": actor_b_start, "westTarget": [15.0, 12.0],
                                      "end": returned["self"]["position"], "inventoryWood": 0,
                                      "positions": positions_b, "verified": True},
                  "restartObservationUnchanged": True, "counterexampleConfirmed": True}
    finally:
        world.stop()
        (run / "trace.json").write_text(json.dumps(trace, ensure_ascii=False, indent=2) + "\n")
    with sqlite3.connect(f"file:{world.data / 'world.db'}?mode=ro", uri=True) as db:
        report["stoppedDatabaseAudit"] = {
            "worldVersion": db.execute("SELECT state_version FROM worlds").fetchone()[0],
            "wildWood": db.execute("SELECT sum(remaining_wood) FROM resource_nodes").fetchone()[0],
            "inventoryByActor": dict(db.execute("SELECT actor_id,wood FROM residents")),
            "entityMaterial": db.execute("SELECT sum(embodied_wood) FROM entities").fetchone()[0],
            "entities": db.execute("SELECT count(*) FROM entities").fetchone()[0],
            "gatherEvents": db.execute("SELECT count(*) FROM events WHERE json_extract(event_json,'$.type')='gathered'").fetchone()[0],
            "integrity": db.execute("PRAGMA integrity_check").fetchone()[0],
            "foreignKeyErrors": len(db.execute("PRAGMA foreign_key_check").fetchall())}
    assert report["stoppedDatabaseAudit"]["inventoryByActor"] == {"a1": 6, "a2": 0}
    assert report["stoppedDatabaseAudit"]["gatherEvents"] == 12
    report["allExperimentProcessesStopped"] = world.process.poll() is not None
    output = run / "results.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print("Evidence:", output)
    print(json.dumps({k: report[k] for k in ("actualCommands", "protectedInstance", "counterexampleConfirmed", "stoppedDatabaseAudit")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
