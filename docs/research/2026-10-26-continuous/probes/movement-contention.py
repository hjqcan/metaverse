#!/usr/bin/env python3
"""Construct a legal r8 interleaving that prevents a second actor from moving.

This is a liveness counterexample, not a latency or real-player benchmark.
Only isolated services and database files are used; no model is called.
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
import uuid

ROOT = Path(__file__).resolve().parents[4]
sys.path[:0] = [str(ROOT / "tests"), str(ROOT / "scripts")]
import foundation_api
import activities_api
from activities_api import ActivityCandidate


def intent(observed, target):
    return {"schemaVersion": 1, "rulesVersion": "r8", "commandId": uuid.uuid4().hex,
            "expectedStateVersion": observed["stateVersion"],
            "action": {"type": "walk", "to": target}}


def main():
    run = ROOT / ".local/research/movement-contention" / (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:6])
    run.mkdir(parents=True, mode=0o700)
    shutil.copytree(ROOT / "src/World.Server/bin/Debug/net10.0", run / "binary")
    foundation_api.DLL = run / "binary/World.Server.dll"
    activities_api.RUN_ROOT = run
    world = ActivityCandidate("interleaving", scenario="wilderness-continuous-v1")
    trace = []
    try:
        a, b = world.client(), world.client("a2")
        initial_a, initial_b = a.observe(), b.observe()
        assert initial_a["rulesVersion"] == "r8"
        assert "commandBinding" not in initial_a, "This probe targets the recorded pre-binding baseline"
        target = [initial_b["self"]["position"][0] + 0.1, initial_b["self"]["position"][1]]
        for index in range(20):
            observed_b = b.observe()
            observed_a = a.observe()
            assert observed_a["stateVersion"] == observed_b["stateVersion"]
            request_a = intent(observed_a, observed_a["self"]["position"])
            request_b = intent(observed_b, target)
            status_a, reply_a = a.command(request_a)
            status_b, reply_b = b.command(request_b)
            assert status_a == 200 and reply_a["status"] == "committed"
            assert reply_a["result"]["position"] == initial_a["self"]["position"]
            assert status_b == 409 and reply_b["status"] == "rejected"
            assert reply_b["error"]["code"] == "STALE_STATE"
            trace.append({"round": index + 1, "a": {"request": request_a, "status": status_a, "response": reply_a},
                          "b": {"request": request_b, "status": status_b, "response": reply_b}})
        after_interleaving = b.observe()
        assert after_interleaving["self"]["position"] == initial_b["self"]["position"]
        assert after_interleaving["stateVersion"] == 20
        # Control: stop the interfering actor; the same target is reachable.
        control_request = intent(after_interleaving, target)
        control_status, control_reply = b.command(control_request)
        assert control_status == 200 and control_reply["status"] == "committed"
        final = b.observe()
        assert math.dist(final["self"]["position"], initial_b["self"]["position"]) > 0
        report = {
            "recordedAtUtc": datetime.now(timezone.utc).isoformat(),
            "baseCommit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
            "assemblySha256": hashlib.sha256(foundation_api.DLL.read_bytes()).hexdigest(),
            "kind": "research-liveness-counterexample", "scenario": "wilderness-continuous-v1",
            "actualModelCalls": 0,
            "scope": "20 explicitly controlled HTTP interleavings, not a native-client or actual mission run",
            "schedule": "B observes; A observes the same version and commits walk to its own position; B submits original walk",
            "aCommittedZeroDistanceWalks": 20, "bConfirmedStaleRejections": 20,
            "aStartPosition": initial_a["self"]["position"],
            "aEndPositionDuringInterference": a.observe()["self"]["position"],
            "bStartPosition": initial_b["self"]["position"],
            "bEndPositionDuringInterference": after_interleaving["self"]["position"],
            "worldVersionAfterInterference": after_interleaving["stateVersion"],
            "quietControl": {"request": control_request, "status": control_status, "response": control_reply,
                             "distanceMoved": math.dist(final["self"]["position"], initial_b["self"]["position"])},
            "counterexampleConfirmed": True,
        }
        (run / "trace.json").write_text(json.dumps(trace, ensure_ascii=False, indent=2) + "\n")
    finally:
        world.stop()
    with sqlite3.connect(f"file:{world.data / 'world.db'}?mode=ro", uri=True) as db:
        report["stoppedDatabaseAudit"] = {
            "stateVersion": db.execute("SELECT state_version FROM worlds").fetchone()[0],
            "events": db.execute("SELECT count(*) FROM events").fetchone()[0],
            "receiptsByStatus": dict(db.execute("SELECT json_extract(result_json,'$.status'),count(*) FROM receipts GROUP BY 1")),
            "remainingWildWood": db.execute("SELECT sum(remaining_wood) FROM resource_nodes").fetchone()[0],
            "residentInventoryWood": db.execute("SELECT sum(wood) FROM residents").fetchone()[0],
            "integrity": db.execute("PRAGMA integrity_check").fetchone()[0],
            "foreignKeyErrors": len(db.execute("PRAGMA foreign_key_check").fetchall()),
        }
    assert report["stoppedDatabaseAudit"] == {"stateVersion": 21, "events": 22,
        "receiptsByStatus": {"committed": 21, "rejected": 20}, "remainingWildWood": 12,
        "residentInventoryWood": 0, "integrity": "ok", "foreignKeyErrors": 0}
    report["allExperimentProcessesStopped"] = world.process.poll() is not None
    output = run / "results.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print("Evidence:", output)
    print(json.dumps({k: report[k] for k in ("counterexampleConfirmed", "bConfirmedStaleRejections", "stoppedDatabaseAudit")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
