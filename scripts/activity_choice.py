#!/usr/bin/env python3
"""Fixed cost reference for activity missions; no model or external calls."""


def choose_lowest_cost(context):
    """Choose a feasible goal by wood, commands, then ID, ignoring purpose."""
    candidates = [candidate for candidate in context["candidates"] if candidate.get("feasible") is True]
    if not candidates:
        raise ValueError("No feasible activity candidate")
    chosen = min(candidates, key=lambda candidate: (
        candidate["woodRequired"], candidate["estimatedCommands"], candidate["id"]))
    return {"goalId": chosen["id"], "reason": "固定成本参考：按木材、预计命令数、目标 ID 升序选择可行目标。",
            "provider": {"kind": "fixed-reference", "model": "least-cost-v1", "usage": {}}}
