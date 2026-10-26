#!/usr/bin/env python3
"""Two actual GPT-6 residents write in one isolated world; two calls maximum, no rerolls."""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
import json
import sqlite3
import uuid

import postcards_api
from postcards_api import PostcardCandidate, ROOT
from activity_comparison import audit_database, write
from codex_goal_selector import CodexGoalSelector
from resident_mission import run_mission


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--account-one", required=True)
    parser.add_argument("--account-two", required=True)
    args = parser.parse_args()
    data = ROOT / ".local/iter0005/live" / (datetime.now().strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:6])
    data.mkdir(parents=True, mode=0o700)
    postcards_api.RUN_ROOT = data / "worlds"
    result = {"schemaVersion": 1, "kind": "shared-postcard-session", "recordedAtUtc": datetime.now(timezone.utc).isoformat(),
              "modelAttemptLimit": 2, "actualModelCalls": 0, "runs": [], "passed": False}
    world = None
    try:
        world = PostcardCandidate("shared-world")
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
                # This is exactly the executor's reduced, credential-free input, including public authored text.
                record["decisionInput"] = deepcopy(context)
                write(data / "session.json", result)
                return selector(context)

            try:
                job = json.loads((ROOT / f"examples/postcards/{sample}.json").read_text())
                report = run_mission(world.client(actor), job, data / f"{sample}.state.json", choose)
                record["report"] = report
                write(data / f"{sample}.json", report)
                observed = world.client(actor).observe()
                card = report["facts"].get("postcard")
                record["executionVerified"] = bool(report["mission"]["status"] == "completed" and report["facts"].get("activityCompleted")
                    and report["facts"].get("postcardShared") and report["facts"]["returned"] and card
                    and card in observed["self"]["postcards"] and card in world.client("a2" if actor == "a1" else "a1").observe()["postcards"]
                    and card["authorActorId"] == actor and card["visitCommandId"] == report["facts"]["activityVisit"]["commandId"]
                    and card["text"] == report["decision"]["postcardText"] and observed["self"]["position"] == report["mission"]["origin"])
                record["expectedGoalMatch"] = report["mission"]["goal"] is not None and report["mission"]["goal"]["id"] == "garden"
                if index == 1:
                    first_card = (result["runs"][0]["report"] or {}).get("facts", {}).get("postcard")
                    public_input = (record["decisionInput"] or {}).get("observation", {}).get("postcards", [])
                    record["firstPostcardPresentInDecisionInput"] = bool(first_card and first_card in public_input)
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
        result["publicPostcards"] = observed["postcards"]
        result["resourceAudit"] = observed["resourceAudit"]
        result["passed"] = bool(result["actualModelCalls"] == 2 and len(result["runs"]) == 2
            and all(r.get("executionVerified") and r.get("expectedGoalMatch") and r["error"] is None for r in result["runs"])
            and result["runs"][1].get("firstPostcardPresentInDecisionInput"))
    finally:
        if world:
            world.stop()
            result["databaseAudit"] = audit_database(world.data / "world.db")
            with sqlite3.connect(f"file:{world.data / 'world.db'}?mode=ro", uri=True) as db:
                rows = db.execute("SELECT author_actor_id,command_id,visit_command_id,text,state_version FROM postcards ORDER BY state_version").fetchall()
                result["databaseAudit"]["postcardRows"] = len(rows)
                for actor, command, visit, text, version in rows:
                    receipt = json.loads(db.execute("SELECT result_json FROM receipts WHERE actor_id=? AND command_id=?", (actor, command)).fetchone()[0])
                    assert receipt["status"] == "committed" and receipt["result"]["text"] == text and receipt["result"]["visitCommandId"] == visit
                    assert db.execute("SELECT count(*) FROM visits WHERE actor_id=? AND command_id=? AND state_version<?", (actor, visit, version)).fetchone()[0] == 1
                result["passed"] = bool(result["passed"] and len(rows) == 2 and result["databaseAudit"]["conserved"])
        result["finishedAtUtc"] = datetime.now(timezone.utc).isoformat()
        write(data / "session.json", result)
        print("Evidence:", data / "session.json", flush=True)
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
