#!/usr/bin/env python3
"""Four frozen cases, paired fresh worlds, at most four real GPT-6 calls; no retries."""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import time
import uuid

import activities_api
from activities_api import ActivityCandidate, ROOT
from activity_choice import choose_lowest_cost
from codex_goal_selector import CodexGoalSelector
from resident_mission import run_mission


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def initial_facts(observed):
    return {key: deepcopy(observed[key]) for key in ("rulesVersion", "stateVersion", "world", "self", "residents", "depot", "entities", "recipes", "activities", "resourceAudit")}


def audit_database(path):
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as db:
        depot = db.execute("SELECT depot_wood FROM worlds").fetchone()[0]
        inventory = db.execute("SELECT coalesce(sum(wood),0) FROM residents").fetchone()[0]
        embodied = db.execute("SELECT coalesce(sum(embodied_wood),0) FROM entities").fetchone()[0]
        ledger_build = db.execute("SELECT coalesce(sum(quantity),0) FROM resource_ledger WHERE destination_account LIKE 'entity:%'").fetchone()[0]
        visits = db.execute("SELECT count(*) FROM visits").fetchone()[0]
        version = db.execute("SELECT state_version FROM worlds").fetchone()[0]
        events = db.execute("SELECT count(*) FROM events").fetchone()[0]
        foreign_keys = db.execute("PRAGMA foreign_key_check").fetchall()
        assert depot + inventory + embodied == 12 and embodied == ledger_build
        assert events == version + 1 and not foreign_keys
        return {"issuedWood": 12, "depotWood": depot, "inventoryWood": inventory,
                "embodiedWood": embodied, "conserved": True, "visitRows": visits,
                "stateVersion": version, "eventRows": events, "foreignKeyErrors": 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--account-one", required=True)
    parser.add_argument("--account-two", required=True)
    args = parser.parse_args()
    cases = json.loads((ROOT / "examples/activities/cases.json").read_text())["cases"]
    assert len(cases) == 4, "This acceptance has a fixed four-call ceiling"
    data = ROOT / ".local/iter0004/comparison" / (datetime.now().strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:6])
    data.mkdir(parents=True, mode=0o700)
    activities_api.RUN_ROOT = data / "worlds"
    result = {"schemaVersion": 1, "kind": "activity-choice-comparison", "recordedAtUtc": datetime.now(timezone.utc).isoformat(),
              "actualModelCalls": 0, "modelAttemptLimit": 4, "cases": [], "passed": False}
    attempts = 0
    try:
        for index, case in enumerate(cases):
            entry = {"id": case["id"], "objective": case["spec"]["objective"], "expectedGoalId": case["expectedGoalId"],
                     "initialEquivalent": False, "runs": []}
            result["cases"].append(entry)
            originals = []
            for kind in ("fixed-reference", "codex-exec"):
                key = case["id"] + ("-fixed" if kind == "fixed-reference" else "-model")
                world = None
                record = {"kind": kind, "report": None, "actualModelCalls": 0, "error": None}
                entry["runs"].append(record)
                start = time.monotonic()
                decision_dir = data / "decisions" / key
                try:
                    world = ActivityCandidate(key)
                    observed = world.client().observe()
                    original = initial_facts(observed)
                    originals.append(original)
                    record["initialDigest"] = hashlib.sha256(json.dumps(original, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
                    job = deepcopy(case["spec"]); job["missionId"] = key
                    choose = choose_lowest_cost
                    if kind == "codex-exec":
                        assert attempts < 4
                        attempts += 1
                        write(data / "attempts.json", {"started": attempts, "limit": 4, "current": key})
                        account = args.account_one if index % 2 == 0 else args.account_two
                        choose = CodexGoalSelector(account, evidence_dir=decision_dir)
                    report = run_mission(world.client(), job, data / (key + ".state.json"), choose)
                    record["report"] = report
                    record["expectedGoalMatch"] = report["mission"]["goal"] is not None and report["mission"]["goal"]["id"] == case["expectedGoalId"]
                    record["executionVerified"] = report["mission"]["status"] == "completed" and report["facts"]["goalReached"] and report["facts"]["activityCompleted"] and report["facts"]["returned"]
                    if record["executionVerified"]:
                        visit = report["facts"]["activityVisit"]
                        final = world.client().observe()
                        assert final["self"]["position"] == [1, 1]
                        assert any(v == visit for v in final["self"]["visits"])
                    write(data / (key + ".json"), report)
                except Exception as error:
                    # No fallback, reroll or hidden extra call. Preserve each failed row and continue the remaining frozen cases.
                    record["error"] = {"type": type(error).__name__, "message": str(error)[:500]}
                finally:
                    if world:
                        world.stop()
                        try: record["databaseAudit"] = audit_database(world.data / "world.db")
                        except Exception as error: record["error"] = {"type": type(error).__name__, "message": "Independent database audit failed"}
                    records = [json.loads(p.read_text()) for p in sorted(decision_dir.glob("decision-*.json"))] if decision_dir.exists() else []
                    record["actualModelCalls"] = len(records)
                    record["decisionEvents"] = [{k: v for k, v in r.items() if k != "accountAlias"} for r in records]
                    result["actualModelCalls"] += len(records)
                    record["elapsedSeconds"] = round(time.monotonic() - start, 6)
                    write(data / "comparison.json", result)
                print(json.dumps({"case": case["id"], "kind": kind, "goal": (record["report"] or {}).get("mission", {}).get("goal"),
                                  "expectedGoalMatch": record.get("expectedGoalMatch", False), "executionVerified": record.get("executionVerified", False),
                                  "actualModelCalls": record["actualModelCalls"], "error": record["error"]}, ensure_ascii=False), flush=True)
            entry["initialEquivalent"] = len(originals) == 2 and originals[0] == originals[1]
            write(data / "comparison.json", result)
        result["passed"] = all(c["initialEquivalent"] and all(r.get("executionVerified") and r["error"] is None for r in c["runs"]) for c in result["cases"])
        result["summary"] = {kind: {"purposeMatches": sum(r.get("expectedGoalMatch", False) for c in result["cases"] for r in c["runs"] if r["kind"] == kind),
                                      "executionsVerified": sum(r.get("executionVerified", False) for c in result["cases"] for r in c["runs"] if r["kind"] == kind)}
                             for kind in ("fixed-reference", "codex-exec")}
    finally:
        result["finishedAtUtc"] = datetime.now(timezone.utc).isoformat()
        write(data / "comparison.json", result)
        print("Evidence:", data / "comparison.json", flush=True)
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
