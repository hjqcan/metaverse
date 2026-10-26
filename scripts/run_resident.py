#!/usr/bin/env python3
"""Run or resume one durable resident mission; GPT-6 chooses once, facts decide success."""

import argparse
import json
from pathlib import Path

from codex_goal_selector import CodexGoalSelector
from foundation_agent import WorldClient
from resident_mission import run_mission


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:5081")
    parser.add_argument("--access-file", type=Path, default=Path(".local/passage/access.json"))
    parser.add_argument("--actor", choices=("a1", "a2"), required=True)
    parser.add_argument("--account", required=True, help="Pinned account alias from agent_accounts.py")
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-steps", type=int)
    args = parser.parse_args()
    if args.state.resolve() == args.output.resolve():
        parser.error("State and report paths must differ")
    spec = json.loads(args.spec.read_text())
    token = json.loads(args.access_file.read_text())["sessions"][args.actor]["token"]
    choose = CodexGoalSelector(args.account, evidence_dir=args.state.parent / "decisions")
    report = run_mission(WorldClient(args.url, token), spec, args.state, choose, max_steps=args.max_steps)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"missionId": report["mission"]["id"], "status": report["mission"]["status"],
                      "used": report["budget"]["used"], "report": str(args.output)}, ensure_ascii=False))
    return 0 if report["mission"]["status"] in ("completed", "paused", "blocked", "budget_exhausted") else 1


if __name__ == "__main__":
    raise SystemExit(main())
