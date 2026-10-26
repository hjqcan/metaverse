#!/usr/bin/env python3
"""Run or resume one durable resident mission; GPT-6 chooses once, facts decide success."""

import argparse
import json
from pathlib import Path

from codex_goal_selector import CodexGoalSelector
from foundation_agent import WorldClient
from resident_mission import run_mission
from activity_choice import choose_lowest_cost
from resident_workshop import uses as workshop_task


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:5081")
    parser.add_argument("--access-file", type=Path, default=Path(".local/passage/access.json"))
    parser.add_argument("--actor", choices=("a1", "a1_alias", "a2", "a3"), required=True)
    selection = parser.add_mutually_exclusive_group()
    selection.add_argument("--account", help="Pinned account alias from agent_accounts.py; one real GPT-6 choice")
    selection.add_argument("--fixed-reference", action="store_true", help="Use the deterministic cost reference; no model calls")
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-steps", type=int)
    args = parser.parse_args()
    if args.state.resolve() == args.output.resolve():
        parser.error("State and report paths must differ")
    spec = json.loads(args.spec.read_text())
    if workshop_task(spec) and args.account:
        parser.error('Workshop tasks execute the explicitly authorized fixed action; --account is not supported')
    if workshop_task(spec) and spec['goals'][0].get('workshop', {}).get('actorId') != args.actor:
        parser.error('The CLI actor differs from the explicitly bound workshop actor')
    if not args.account and not args.fixed_reference and not workshop_task(spec) and not any('entityNote' in g or 'entityCanvas' in g for g in spec.get('goals', [])):
        parser.error('Select --account or --fixed-reference; explicit entity-note and entity-canvas tasks default to the fixed reference')
    sessions = json.loads(args.access_file.read_text()).get('sessions', {})
    session = sessions.get(args.actor)
    if not isinstance(session, dict) or not isinstance(session.get('token'), str) or not session['token']:
        parser.error('The selected actor has no session in the supplied access file')
    token = session['token']
    choose = CodexGoalSelector(args.account, evidence_dir=args.state.parent / "decisions") if args.account else choose_lowest_cost
    report = run_mission(WorldClient(args.url, token), spec, args.state, choose, max_steps=args.max_steps)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"missionId": report["mission"]["id"], "status": report["mission"]["status"],
                      "used": report["budget"]["used"], "report": str(args.output)}, ensure_ascii=False))
    return 0 if report["mission"]["status"] in ("completed", "paused", "blocked", "budget_exhausted") else 1


if __name__ == "__main__":
    raise SystemExit(main())
