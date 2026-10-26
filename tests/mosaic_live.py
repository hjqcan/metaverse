#!/usr/bin/env python3
"""Two actual GPT-6 residents contribute to one mosaic; two calls maximum, no rerolls."""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import json
import sqlite3
import uuid

import mosaic_api
from mosaic_api import MosaicCandidate, ROOT
from activity_comparison import audit_database, write
from codex_goal_selector import CodexGoalSelector
from resident_mission import run_mission


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--account-one", required=True)
    parser.add_argument("--account-two", required=True)
    args = parser.parse_args()
    data = ROOT / ".local/iter0006/live" / (datetime.now().strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:6])
    data.mkdir(parents=True, mode=0o700)
    mosaic_api.RUN_ROOT = data / "worlds"
    result = {"schemaVersion": 1, "kind": "shared-mosaic-session", "recordedAtUtc": datetime.now(timezone.utc).isoformat(),
              "modelAttemptLimit": 2, "actualModelCalls": 0, "runs": [], "passed": False}
    world = None
    try:
        world = MosaicCandidate("shared-world")
        for index, (actor, sample, account) in enumerate([("a1", "first", args.account_one), ("a2", "second", args.account_two)]):
            record = {"actorId": actor, "report": None, "decisionInput": None, "error": None, "actualModelCalls": 0}
            result["runs"].append(record)
            decisions = data / "decisions" / sample
            selector = CodexGoalSelector(account, evidence_dir=decisions)
            calls = 0

            def choose(context):
                nonlocal calls
                assert calls == 0, "No second choice or retry is permitted"
                calls += 1
                write(data / "attempts.json", {"started": index + 1, "limit": 2, "current": actor})
                # This is exactly the executor's reduced, credential-free input, including public painted tiles and their authors.
                record["decisionInput"] = deepcopy(context)
                write(data / "session.json", result)
                return selector(context)

            try:
                job = json.loads((ROOT / f"examples/mosaic/{sample}.json").read_text())
                report = run_mission(world.client(actor), job, data / f"{sample}.state.json", choose)
                record["report"] = report
                write(data / f"{sample}.json", report)
                observed = world.client(actor).observe()
                edit = report["facts"].get("mosaicEdit")
                record["executionVerified"] = bool(report["mission"]["status"] == "completed" and report["facts"].get("activityCompleted")
                    and report["facts"].get("mosaicPainted") and report["facts"]["returned"] and edit
                    and edit in observed["self"]["mosaicEdits"] and edit in world.client("a2" if actor == "a1" else "a1").observe()["mosaicEdits"]
                    and edit["authorActorId"] == actor and edit["visitCommandId"] == report["facts"]["activityVisit"]["commandId"]
                    and edit["patch"] == report["decision"]["mosaicPatch"] and observed["self"]["position"] == report["mission"]["origin"])
                record["expectedGoalMatch"] = report["mission"]["goal"] is not None and report["mission"]["goal"]["id"] == "garden"
                initial = record["decisionInput"]["observation"]["mosaic"]
                if index == 0:
                    coords = {(c["x"], c["y"]) for c in edit["patch"]} if edit else set()
                    reached = set()
                    if coords:
                        todo = [next(iter(coords))]
                        while todo:
                            p = todo.pop()
                            if p in reached: continue
                            reached.add(p)
                            todo.extend(q for q in coords - reached if abs(q[0]-p[0])+abs(q[1]-p[1]) == 1)
                    record["purposeVerified"] = bool(edit and all(c["color"] == "river" for c in edit["patch"]) and coords == reached)
                else:
                    first_board = (result["runs"][0]["report"] or {}).get("world", {}).get("mosaic")
                    record["firstTilesPresentInDecisionInput"] = bool(first_board and first_board == initial)
                    record["firstTilesPreserved"] = bool(first_board and all(c == observed["mosaic"]["cells"][i]
                        for i, c in enumerate(first_board["cells"]) if c["color"] != "blank"))
                    record["purposeVerified"] = bool(edit and any(c["color"] == "leaf" for c in edit["patch"])
                        and all(c["color"] in ["leaf", "rose"] and initial["cells"][c["y"]*5+c["x"]]["color"] == "blank" for c in edit["patch"]))
            except Exception as error:
                record["error"] = {"type": type(error).__name__, "message": str(error)[:500]}
            finally:
                events = [json.loads(p.read_text()) for p in sorted(decisions.glob("decision-*.json"))] if decisions.exists() else []
                record["decisionEvents"] = [{k: v for k, v in e.items() if k != "accountAlias"} for e in events]
                record["actualModelCalls"] = len(events)
                result["actualModelCalls"] += len(events)
                write(data / "session.json", result)
                print(json.dumps({"actorId": actor, "actualModelCalls": record["actualModelCalls"], "executionVerified": record.get("executionVerified", False),
                                  "expectedGoalMatch": record.get("expectedGoalMatch", False), "error": record["error"]}, ensure_ascii=False), flush=True)
        observed = world.client().observe()
        result["finalMosaic"] = observed["mosaic"]
        result["publicMosaicEdits"] = observed["mosaicEdits"]
        result["resourceAudit"] = observed["resourceAudit"]
        result["passed"] = bool(result["actualModelCalls"] == 2 and len(result["runs"]) == 2
            and all(r.get("executionVerified") and r.get("expectedGoalMatch") and r.get("purposeVerified") and r["error"] is None for r in result["runs"])
            and result["runs"][1].get("firstTilesPresentInDecisionInput") and result["runs"][1].get("firstTilesPreserved"))
    finally:
        if world:
            world.stop()
            result["databaseAudit"] = audit_database(world.data / "world.db")
            with sqlite3.connect(f"file:{world.data / 'world.db'}?mode=ro", uri=True) as db:
                result["databaseAudit"]["mosaicEditRows"] = db.execute("SELECT count(*) FROM mosaic_edits").fetchone()[0]
                events = [json.loads(row[0]) for row in db.execute("SELECT event_json FROM events ORDER BY state_version")]
                edits = [e for e in events if e["type"] == "mosaic_painted"]
                for edit in edits:
                    actor, command, visit = edit["authorActorId"], edit["commandId"], edit["visitCommandId"]
                    receipt = json.loads(db.execute("SELECT result_json FROM receipts WHERE actor_id=? AND command_id=?", (actor, command)).fetchone()[0])
                    assert receipt["status"] == "committed" and receipt["result"]["patch"] == edit["patch"] and receipt["result"]["visitCommandId"] == visit
                    assert db.execute("SELECT count(*) FROM visits WHERE actor_id=? AND command_id=? AND state_version<?", (actor, visit, edit["stateVersion"])).fetchone()[0] == 1
                result["passed"] = bool(result["passed"] and len(edits) == 2 and result["databaseAudit"]["mosaicEditRows"] == 2 and result["databaseAudit"]["conserved"])
        result["finishedAtUtc"] = datetime.now(timezone.utc).isoformat()
        write(data / "session.json", result)
        print("Evidence:", data / "session.json", flush=True)
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
