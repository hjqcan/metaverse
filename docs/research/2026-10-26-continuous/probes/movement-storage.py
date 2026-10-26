#!/usr/bin/env python3
"""Measure persisted rows/bytes for an isolated r8 movement workload.

Uses a specified frozen build, not a live preview. The accelerated workload is
for storage measurement, not a claim about sustainable latency or throughput.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[4]
sys.path[:0] = [str(ROOT / "tests"), str(ROOT / "scripts")]
import foundation_api
import activities_api
from activities_api import ActivityCandidate


def audit(path):
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as db:
        page_size = db.execute("PRAGMA page_size").fetchone()[0]
        pages = db.execute("PRAGMA page_count").fetchone()[0]
        return {"fileBytes": path.stat().st_size, "pageSize": page_size, "pages": pages,
                "allocatedPageBytes": page_size * pages,
                "receipts": db.execute("SELECT count(*) FROM receipts").fetchone()[0],
                "events": db.execute("SELECT count(*) FROM events").fetchone()[0],
                "receiptJsonBytes": db.execute("SELECT coalesce(sum(length(CAST(result_json AS BLOB))),0) FROM receipts").fetchone()[0],
                "eventJsonBytes": db.execute("SELECT coalesce(sum(length(CAST(event_json AS BLOB))),0) FROM events").fetchone()[0],
                "integrity": db.execute("PRAGMA integrity_check").fetchone()[0]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--count", type=int, default=2000)
    args = parser.parse_args()
    if not 100 <= args.count <= 5000:
        parser.error("count must be 100..5000")
    run = ROOT / ".local/research/movement-storage" / (
        datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:6])
    run.mkdir(parents=True, mode=0o700)
    shutil.copytree(args.binary, run / "binary")
    foundation_api.DLL = run / "binary/World.Server.dll"
    activities_api.RUN_ROOT = run
    world = ActivityCandidate("movement", scenario="wilderness-continuous-v1")
    world.stop()
    before = audit(world.data / "world.db")
    try:
        world.start()
        client = world.client()
        initial = client.observe()
        version = initial["stateVersion"]
        started = time.monotonic()
        for index in range(args.count):
            request = {"schemaVersion": 1, "rulesVersion": "r8",
                       "commandId": "godot_" + uuid.uuid4().hex,
                       "expectedStateVersion": version,
                       "action": {"type": "walk", "to": [4.6 if index % 2 == 0 else 5.0, 7.0]}}
            status, reply = client.command(request)
            assert status == 200 and reply["status"] == "committed", (index, status, reply)
            assert reply["stateVersion"] == version + 1
            version = reply["stateVersion"]
        elapsed = time.monotonic() - started
        final = client.observe()
        assert final["stateVersion"] == args.count
        assert final["resourceAudit"]["wildWood"] == 12 and final["resourceAudit"]["inventoryWood"] == 0
    finally:
        world.stop()
    after = audit(world.data / "world.db")
    assert after["receipts"] - before["receipts"] == args.count
    assert after["events"] - before["events"] == args.count
    delta = {key: after[key] - before[key] for key in ("fileBytes", "allocatedPageBytes", "receiptJsonBytes", "eventJsonBytes")}
    report = {"recordedAtUtc": datetime.now(timezone.utc).isoformat(),
              "kind": "isolated-r8-movement-storage-measurement",
              "binarySource": str(args.binary),
              "assemblySha256": hashlib.sha256(foundation_api.DLL.read_bytes()).hexdigest(),
              "actualModelCalls": 0, "commands": args.count,
              "acceleratedGenerationElapsedSeconds": elapsed,
              "scope": "storage delta of successful movement commands in a stopped database; no long-duration or client UX claim",
              "before": before, "after": after, "delta": delta,
              "allocatedBytesPerCommandInThisSample": delta["allocatedPageBytes"] / args.count,
              "payloadBytesPerCommandInThisSample": (delta["receiptJsonBytes"] + delta["eventJsonBytes"]) / args.count,
              "allExperimentProcessesStopped": world.process.poll() is not None}
    output = run / "results.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print("Evidence:", output)
    print(json.dumps({k: report[k] for k in ("commands", "allocatedBytesPerCommandInThisSample", "payloadBytesPerCommandInThisSample")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
