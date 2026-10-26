#!/usr/bin/env python3
"""Explicit live acceptance: exactly two GPT-6 goal decisions on an isolated world."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import sys
import uuid

import passage_api
from foundation_api import ROOT
from resident_mission_api import spec
from resident_mission import run_mission
from codex_goal_selector import CodexGoalSelector


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--builder-account", required=True)
    parser.add_argument("--traveler-account", required=True)
    args = parser.parse_args()
    data = ROOT / ".local/iter0003/live" / (datetime.now().strftime("%Y%m%dT%H%M%S")+"-"+uuid.uuid4().hex[:6])
    passage_api.RUN_ROOT = data
    candidate = passage_api.PassageCandidate("world")
    results = {"suite": "resident-real-gpt6-v1", "recordedAtUtc": datetime.now(timezone.utc).isoformat(),
               "passed": False, "dataRoot": str(data.relative_to(ROOT)), "missions": []}
    try:
        for actor, role, account in (("a1", "builder", args.builder_account), ("a2", "traveler", args.traveler_account)):
            job = spec("live-"+role, wood=6 if role == "builder" else 0)
            if role == "traveler":
                job["allowBuild"] = False
                job["objective"] = "只游玩：希望走别人已建好的公共跨河桥去彼岸看看，再回起点，不领取也不建造。"
            (data / (role+"-spec.json")).write_text(json.dumps(job, ensure_ascii=False, indent=2))
            choose = CodexGoalSelector(account, evidence_dir=data / "decisions")
            report = run_mission(candidate.client(actor), job, data / (role+".state.json"), choose)
            (data / (role+".json")).write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n")
            results["missions"].append({"role": role, "status": report["mission"]["status"],
                                        "goalId": (report["decision"] or {}).get("goalId"),
                                        "provider": (report["decision"] or {}).get("provider"),
                                        "used": report["budget"]["used"]})
            assert report["mission"]["status"] == "completed", report["mission"]
            assert report["decision"]["goalId"] == "far-bank", report["decision"]
            assert report["facts"]["goalReached"] and report["facts"]["returned"]
            assert report["decision"]["provider"]["kind"] == "codex-exec"
            assert report["budget"]["used"]["modelCalls"] == 1
            if role == "builder":
                assert report["budget"]["used"]["wood"] == 6
                assert len(report["facts"]["createdEntityIds"]) == 2
            else:
                assert report["facts"]["woodClaimed"] == 0
                assert all(s["action"]["type"] == "move" for s in report["steps"])
            print(json.dumps(results["missions"][-1], ensure_ascii=False), flush=True)
        final = candidate.client().observe()
        assert final["resourceAudit"] == {"issuedWood": 12, "depotWood": 6, "inventoryWood": 0, "embodiedWood": 6, "conserved": True}
        candidate.stop()
        with sqlite3.connect(f"file:{candidate.data / 'world.db'}?mode=ro", uri=True) as db:
            assert db.execute("SELECT sum(embodied_wood) FROM entities").fetchone()[0] == 6
            assert db.execute("SELECT sum(quantity) FROM resource_ledger WHERE destination_account LIKE 'entity:%'").fetchone()[0] == 6
            assert db.execute("SELECT depot_wood FROM worlds").fetchone()[0] == 6
            assert db.execute("SELECT sum(wood) FROM residents").fetchone()[0] == 0
        results.update(passed=True, actualModelCalls=2, finalAudit=final["resourceAudit"])
    except Exception as error:
        results["failure"] = {"type": type(error).__name__, "message": str(error)}
        raise
    finally:
        candidate.stop()
        (data / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2)+"\n")
        print("Evidence:", data / "results.json", flush=True)


if __name__ == "__main__":
    main()
