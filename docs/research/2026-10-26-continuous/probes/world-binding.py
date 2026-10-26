#!/usr/bin/env python3
"""Check whether an original pending command distinguishes two fresh databases.

Only isolated test instances are created. No existing world is reset or changed.
"""
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


def main():
    run = ROOT / ".local/research/world-binding" / (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:6])
    run.mkdir(parents=True, mode=0o700)
    shutil.copytree(ROOT / "src/World.Server/bin/Debug/net10.0", run / "binary")
    foundation_api.DLL = run / "binary/World.Server.dll"
    activities_api.RUN_ROOT = run
    worlds = []
    try:
        old = ActivityCandidate("original-world", scenario="wilderness-v1")
        worlds.append(old)
        original = old.client().observe()
        request = {"schemaVersion": 1, "rulesVersion": "r7", "commandId": "old_pending_" + uuid.uuid4().hex,
                   "expectedStateVersion": original["stateVersion"],
                   "action": {"type": "gather", "nodeId": "tree-west-north"}}
        journal_key = hashlib.sha256((old.url + "/foundation-01/a1").encode()).hexdigest()
        # The original command was saved but never submitted to the old world.
        old.stop()
        replacement = ActivityCandidate("fresh-world", scenario="wilderness-v1")
        worlds.append(replacement)
        replacement.stop()
        replacement.port, replacement.url = old.port, old.url
        replacement.env["WORLD_URL"] = old.url
        replacement.start()
        client = replacement.client()
        observed = client.observe()
        query_status, query = client.request("GET", client.prefix + "/commands/" + request["commandId"])
        assert query_status == 404 and query["error"]["code"] == "COMMAND_NOT_FOUND"
        status, response = client.command(request)
        after = client.observe()
        assert status == 200 and response["status"] == "committed"
        assert after["self"]["inventory"]["wood"] == 1
        report = {
            "recordedAtUtc": datetime.now(timezone.utc).isoformat(),
            "baseCommit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
            "kind": "research-counterexample", "actualModelCalls": 0,
            "assemblySha256": hashlib.sha256(foundation_api.DLL.read_bytes()).hexdigest(),
            "condition": "fresh database later served at the same endpoint; explicitly authenticated with its own new token",
            "scope": "actual HTTP proof plus existing Godot key derivation; not a native client execution",
            "sameUrl": old.url == replacement.url,
            "sameWorldId": original["world"]["id"] == observed["world"]["id"],
            "sameActorId": original["self"]["actorId"] == observed["self"]["actorId"],
            "sameRulesVersion": original["rulesVersion"] == observed["rulesVersion"],
            "sameInitialStateVersion": original["stateVersion"] == observed["stateVersion"] == 0,
            "differentSessionId": original["identity"]["sessionId"] != observed["identity"]["sessionId"],
            "godotJournalKeyCollides": journal_key == hashlib.sha256((replacement.url + "/foundation-01/a1").encode()).hexdigest(),
            "originalRequest": request, "lookupStatus": query_status,
            "lookupError": query["error"]["code"],
            "replayStatus": status, "replayResult": response["result"],
            "newWorldStateVersion": after["stateVersion"],
            "newWorldInventoryWood": after["self"]["inventory"]["wood"],
            "counterexampleConfirmed": True,
        }
    finally:
        for world in worlds:
            world.stop()
    report["stoppedDatabaseInventory"] = {}
    for world in worlds:
        with sqlite3.connect(f"file:{world.data / 'world.db'}?mode=ro", uri=True) as db:
            report["stoppedDatabaseInventory"][world.data.name] = dict(db.execute("SELECT actor_id,wood FROM residents"))
    assert report["stoppedDatabaseInventory"] == {"original-world": {"a1": 0, "a2": 0}, "fresh-world": {"a1": 1, "a2": 0}}
    report["allExperimentProcessesStopped"] = all(w.process.poll() is not None for w in worlds)
    output = run / "results.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print("Evidence:", output)
    print(json.dumps({k: report[k] for k in ("counterexampleConfirmed", "godotJournalKeyCollides", "stoppedDatabaseInventory")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
