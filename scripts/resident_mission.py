#!/usr/bin/env python3
"""Persistent bounded missions; models select goals, public HTTP establishes facts.

The seconds limit is wall time since mission creation, including pauses/restarts.
Only the state owner should write the JSON; keep its adjacent .lock file in place.
"""

from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import re
import tempfile
import time
import uuid

from passage_agent import plan
from postcard_text import valid_postcard_text
from mosaic_patch import canonical_patch, public_mosaic, validate_mosaic, patch_target
from mosaic_consent import public_proposal, proposal_evidence, review_evidence
from mosaic_inbox import review_input
from entry_guide import public_entry_guide
from wilderness_materials import collection_plan, valid_gather_receipt
import continuous_navigation as continuous
import resident_construction as construction


def _utc():
    return datetime.now(timezone.utc).isoformat()


def _integer(value, low, high):
    return type(value) is int and low <= value <= high


def _spec(value):
    required = {"missionId", "objective", "goals", "allowBuild", "budgets"}
    if (not isinstance(value, dict) or not required <= set(value)
            or set(value) - required - {"allowGather", "sharePostcard", "paintMosaic", "proposeMosaic", "reviewMosaicProposal"}):
        raise ValueError("Invalid mission spec fields")
    if not isinstance(value["missionId"], str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", value["missionId"]):
        raise ValueError("Invalid missionId")
    if not isinstance(value["objective"], str) or not 1 <= len(value["objective"]) <= 500:
        raise ValueError("Invalid objective")
    if type(value["allowBuild"]) is not bool:
        raise ValueError("allowBuild must be boolean")
    if "allowGather" in value and type(value["allowGather"]) is not bool:
        raise ValueError("allowGather must be boolean")
    if "sharePostcard" in value and type(value["sharePostcard"]) is not bool:
        raise ValueError("sharePostcard must be boolean")
    if "paintMosaic" in value and type(value["paintMosaic"]) is not bool:
        raise ValueError("paintMosaic must be boolean")
    if "proposeMosaic" in value and type(value["proposeMosaic"]) is not bool:
        raise ValueError("proposeMosaic must be boolean")
    if "reviewMosaicProposal" in value:
        reference = value["reviewMosaicProposal"]
        if (not isinstance(reference, dict) or set(reference) != {"proposalActorId", "proposalCommandId"}
                or any(not isinstance(v, str) or not v for v in reference.values())):
            raise ValueError("Invalid reviewMosaicProposal reference")
    if sum(bool(value.get(k)) for k in ("sharePostcard", "paintMosaic", "proposeMosaic", "reviewMosaicProposal")) > 1:
        raise ValueError("Postcard, painting, proposal and review modes are mutually exclusive")
    goals = value["goals"]
    if not isinstance(goals, list) or not 1 <= len(goals) <= 8:
        raise ValueError("Expected 1 to 8 goals")
    ids = set()
    for goal in goals:
        if (not isinstance(goal, dict) or not {'id', 'label', 'target'} <= set(goal)
                or set(goal) - {'id', 'label', 'target', 'activityId', 'buildRecipeId'}):
            raise ValueError("Invalid goal fields")
        if 'buildRecipeId' in goal:
            if (not isinstance(goal['buildRecipeId'], str) or goal['buildRecipeId'] not in construction.RECIPES or not value['allowBuild']
                    or 'activityId' in goal):
                raise ValueError('Construction goals require an allowed recipe, build permission and no activityId')
        if "activityId" in goal and (not isinstance(goal["activityId"], str) or not goal["activityId"]):
            raise ValueError("activityId must be a nonempty string")
        if value.get("sharePostcard") and "activityId" not in goal:
            raise ValueError("Postcard goals must have activityId")
        if any(value.get(k) for k in ("paintMosaic", "proposeMosaic", "reviewMosaicProposal")) and goal.get("activityId") != "garden":
            raise ValueError("Mosaic goals must have activityId garden")
        if not isinstance(goal["id"], str) or not goal["id"] or goal["id"] in ids:
            raise ValueError("Goal IDs must be nonempty and unique")
        if not isinstance(goal["label"], str) or not goal["label"]:
            raise ValueError("Goal label must be nonempty")
        ids.add(goal["id"])
        if (not isinstance(goal["target"], list) or len(goal["target"]) != 2
                or any(not continuous.finite(n) or n < 0 for n in goal["target"])):
            raise ValueError("Goal target must be two nonnegative finite coordinates")
    budget = value["budgets"]
    bounds = {"commands": (1, 1000), "wood": (0, 12), "seconds": (1, 600), "modelCalls": (1, 1)}
    if not isinstance(budget, dict) or set(budget) != set(bounds):
        raise ValueError("Invalid budgets")
    if any(not _integer(budget[key], *limits) for key, limits in bounds.items()):
        raise ValueError("Budget outside mission limits")
    return deepcopy(value)


@contextmanager
def _lock(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(path) + ".lock", os.O_RDWR | os.O_CREAT, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("Mission state is locked by another executor") from None
        yield
    finally:
        os.close(fd)


def _save(path, state):
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(state, stream, ensure_ascii=False, allow_nan=False, indent=2)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _public(observed, share_postcard=False, paint_mosaic=False, consent=False):
    """No session identity, credentials, private peer inventory or client fields."""
    world = {key: deepcopy(observed["world"][key])
             for key in ("id", "instanceId", "width", "height", "blocked", "water", "goal", "coordinateSystem", "bounds") if key in observed["world"]}
    world["entities"] = [{key: deepcopy(entity[key]) for key in (
        "entityId", "definitionId", "definitionVersion", "rulesVersion", "ownerActorId", "position", "embodiedWood")
        if key in entity} for entity in observed.get("entities", [])]
    activities = [{key: deepcopy(activity[key]) for key in ("id", "label", "position", "description")}
                  for activity in observed.get("activities", [])]
    if "activities" in observed:
        world["activities"] = deepcopy(activities)
    public = {"rulesVersion": observed["rulesVersion"], "stateVersion": observed["stateVersion"],
            "self": {"actorId": observed["self"]["actorId"], "position": deepcopy(observed["self"]["position"]),
                     "inventory": {"wood": observed["self"]["inventory"]["wood"]}},
            "world": world, "depot": {key: deepcopy(observed["depot"][key]) for key in ("position", "wood") if key in observed["depot"]},
            "recipes": [{key: recipe[key] for key in ("id", "woodCost")} for recipe in observed.get("recipes", [])],
            "activities": activities}
    if observed.get('gathering', {}).get('version') == 1:
        public['gathering'] = {key: observed['gathering'][key] for key in ('version', 'quantityPerAction')}
        public['resourceNodes'] = [{key: deepcopy(node[key]) for key in
                                   ('nodeId', 'kind', 'position', 'initialWood', 'remainingWood')}
                                  for node in observed.get('resourceNodes', [])]
        public['depot']['available'] = observed['depot'].get('available', True)
    if continuous.continuous(observed):
        public['entities'] = deepcopy(world['entities'])
        public['movement'] = {key: observed['movement'][key] for key in ('version', 'kind', 'speed', 'radius', 'maxStepDistance', 'gatherReach', 'buildReach')}
        public['terrain'] = continuous.public_geometry(observed)
        world['terrain'] = deepcopy(public['terrain'])
        world['resourceNodes'] = deepcopy(public['resourceNodes'])
    entry = public_entry_guide(observed)
    if entry is not None:
        public["entryGuide"] = entry
    if share_postcard:
        # The server returns ascending versions; preserve order and original text.
        public["postcards"] = [{key: deepcopy(card[key]) for key in (
            "activityId", "authorActorId", "commandId", "visitCommandId", "text",
            "stateVersion", "sharedAtUtc", "position")} for card in observed.get("postcards", [])[-5:]]
    if paint_mosaic or consent:
        public["mosaic"] = public_mosaic(observed["mosaic"])
    return public


def _validate_goals(spec, observed):
    free_movement = continuous.continuous(observed)
    if free_movement:
        continuous.validate_observation(observed)
    elif spec['budgets']['commands'] > 100 or any(type(n) is not int for goal in spec['goals'] for n in goal['target']):
        raise ValueError('Legacy grid missions require integer goals and at most 100 commands')
    if spec.get("sharePostcard") and observed.get("rulesVersion") not in ("r4", "r5", "r6"):
        raise ValueError("Postcard sharing requires rulesVersion r4, r5 or r6")
    if spec.get("paintMosaic"):
        if observed.get("rulesVersion") not in ("r5", "r6"):
            raise ValueError("Mosaic painting requires rulesVersion r5 or r6")
        validate_mosaic(observed.get("mosaic"))
    if spec.get("proposeMosaic") or spec.get("reviewMosaicProposal"):
        if observed.get("rulesVersion") != "r6":
            raise ValueError("Mosaic consent requires rulesVersion r6")
        validate_mosaic(observed.get("mosaic"))
        if (not isinstance(observed.get("mosaicProposals"), list)
                or any(not isinstance(observed["self"].get(k), list) for k in ("mosaicProposals", "mosaicReviews"))):
            raise ValueError("invalid_mosaic_consent_capability")
    for goal in spec["goals"]:
        if 'buildRecipeId' in goal and not free_movement:
            raise ValueError('Explicit construction goals require the continuous r8 world')
        if any(n >= bound for n, bound in zip(goal["target"], (observed["world"]["width"], observed["world"]["height"]))):
            raise ValueError("Goal target outside world")
        if "activityId" in goal:
            matches = [activity for activity in observed.get("activities", [])
                       if activity.get("id") == goal["activityId"]]
            if len(matches) != 1 or matches[0].get("position") != goal["target"]:
                raise ValueError("Activity goal must match the server catalog position")


def _activity_visit(value, intent, goal):
    """Accept only evidence for this task's original visit command and target."""
    if (not isinstance(value, dict) or intent["action"]["type"] != "visit"
            or intent["action"].get("activityId") != goal.get("activityId")
            or value.get("commandId") != intent["commandId"]
            or value.get("activityId") != goal.get("activityId")
            or value.get("position") != goal["target"]
            or not isinstance(value.get("position"), list)
            or any(type(n) is not int for n in value["position"])
            or type(value.get("stateVersion")) is not int
            or type(intent.get("expectedStateVersion")) is not int
            or value["stateVersion"] != intent["expectedStateVersion"] + 1
            or not isinstance(value.get("visitedAtUtc"), str) or not value["visitedAtUtc"]):
        return None
    return {key: deepcopy(value[key]) for key in
            ("activityId", "commandId", "stateVersion", "visitedAtUtc", "position")}


def _postcard(value, intent, goal, actor_id, visit, text):
    """Only the original task's exact share and confirmed visit can settle it."""
    action = intent["action"]
    if (not isinstance(value, dict) or not isinstance(visit, dict)
            or action.get("type") != "postcard" or intent.get("rulesVersion") not in ("r4", "r5", "r6")
            or action.get("activityId") != goal.get("activityId")
            or visit.get("activityId") != goal.get("activityId")
            or visit.get("position") != goal["target"]
            or not isinstance(visit.get("commandId"), str) or not visit["commandId"]
            or action.get("visitCommandId") != visit["commandId"]
            or not valid_postcard_text(text) or action.get("text") != text
            or value.get("commandId") != intent["commandId"]
            or value.get("authorActorId") != actor_id
            or value.get("activityId") != goal.get("activityId")
            or value.get("visitCommandId") != visit["commandId"]
            or value.get("text") != text or value.get("position") != goal["target"]
            or not isinstance(value.get("position"), list)
            or any(type(n) is not int for n in value["position"])
            or type(value.get("stateVersion")) is not int
            or type(visit.get("stateVersion")) is not int
            or type(intent.get("expectedStateVersion")) is not int
            or not 0 < visit["stateVersion"] <= intent["expectedStateVersion"]
            or value["stateVersion"] != intent["expectedStateVersion"] + 1
            or not isinstance(value.get("sharedAtUtc"), str) or not value["sharedAtUtc"]):
        return None
    return {key: deepcopy(value[key]) for key in (
        "activityId", "authorActorId", "commandId", "visitCommandId", "text",
        "stateVersion", "sharedAtUtc", "position")}


def _mosaic_edit(value, intent, goal, actor_id, visit, decision):
    """A draft or current cell state cannot establish this original edit's commit."""
    action = intent["action"]
    base = decision.get("mosaicBaseRevision")
    if (not isinstance(value, dict) or not isinstance(visit, dict)
            or action.get("type") != "mosaic" or intent.get("rulesVersion") not in ("r5", "r6")
            or goal.get("activityId") != "garden" or action.get("activityId") != "garden"
            or visit.get("activityId") != "garden" or visit.get("position") != goal["target"]
            or not isinstance(visit.get("commandId"), str) or not visit["commandId"]
            or action.get("visitCommandId") != visit["commandId"]
            or type(base) is not int or base < 0
            or type(action.get("expectedMosaicRevision")) is not int
            or action["expectedMosaicRevision"] != base
            or value.get("commandId") != intent["commandId"]
            or value.get("authorActorId") != actor_id
            or value.get("activityId") != "garden"
            or value.get("visitCommandId") != visit["commandId"]
            or type(value.get("baseRevision")) is not int or value["baseRevision"] != base
            or type(value.get("revision")) is not int or value["revision"] != base + 1
            or not isinstance(value.get("position"), list) or value["position"] != goal["target"]
            or any(type(n) is not int for n in value["position"])
            or type(value.get("stateVersion")) is not int
            or type(visit.get("stateVersion")) is not int
            or type(intent.get("expectedStateVersion")) is not int
            or not 0 < visit["stateVersion"] <= intent["expectedStateVersion"]
            or value["stateVersion"] != intent["expectedStateVersion"] + 1
            or not isinstance(value.get("paintedAtUtc"), str) or not value["paintedAtUtc"]):
        return None
    try:
        patch = canonical_patch(decision.get("mosaicPatch"))
        if (canonical_patch(action.get("patch")) != patch
                or canonical_patch(value.get("patch")) != patch
                or value["patch"] != patch):
            return None
    except ValueError:
        return None
    return {key: deepcopy(value[key]) for key in (
        "activityId", "authorActorId", "commandId", "visitCommandId", "baseRevision", "revision",
        "patch", "stateVersion", "paintedAtUtc", "position")}


def _route_info(observed, target, allow_build, allow_gather=False):
    if continuous.continuous(observed):
        return continuous.route_info(observed, target, allow_build, allow_gather)
    route = plan(observed, target, allow_build)
    if route is None:
        return {"reason": "no_route", "cells": [], "bridges": None, "wood": None, "commands": None}
    cells, bridges = route
    recipe = next((r for r in observed.get("recipes", []) if r["id"] == "bridge.v1"), None)
    if bridges and (recipe is None or not _integer(recipe["woodCost"], 1, 12)):
        return {"reason": "bridge_recipe_unavailable", "cells": cells, "bridges": bridges, "wood": None, "commands": None}
    wood = bridges * recipe["woodCost"] if bridges else 0
    shortage = max(0, wood - observed["self"]["inventory"]["wood"])
    reason, detour = None, 0
    if shortage and allow_gather and observed.get("gathering"):
        collecting = collection_plan(observed, shortage)
        if collecting["reason"]:
            return {"reason": collecting["reason"], "cells": cells, "bridges": bridges,
                    "wood": wood, "commands": None}
        forecast = collecting["forecast"]
        onward = plan(forecast, target, allow_build)
        if onward is None:
            return {"reason": "no_route", "cells": [], "bridges": bridges, "wood": wood, "commands": None}
        forecast["world"]["blocked"] = [p for p in forecast["world"]["blocked"] if tuple(p) not in onward[0]]
        forecast["self"]["position"] = list(target)
        back = plan(forecast, observed["self"]["position"], False)
        return {"reason": None if back is not None else "no_return_route", "cells": cells,
                "bridges": bridges, "wood": wood, "collection": collecting["actions"],
                "commands": len(collecting["actions"]) + len(onward[0]) + onward[1] + (len(back[0]) if back else 0)}
    if shortage > observed["depot"]["wood"]:
        reason = "natural_material_collection_required" if observed.get("gathering") else "insufficient_public_material"
    elif shortage and sum(abs(a-b) for a, b in zip(observed["self"]["position"], observed["depot"]["position"])) > 1:
        depot_route = plan(observed, observed["depot"]["position"], False)
        if depot_route is None:
            reason = "depot_unreachable"
        else:
            # An upper estimate: visit the depot and return along the same path.
            detour = 2 * len(depot_route[0])
    return {"reason": reason, "cells": cells, "bridges": bridges, "wood": wood,
            "commands": 2 * len(cells) + bridges + int(shortage > 0) + detour}


def _context(spec, observed):
    candidates = []
    for goal in spec["goals"]:
        info = (construction.plan(observed, goal, spec.get('allowGather', False)) if 'buildRecipeId' in goal
                else _route_info(observed, goal["target"], spec["allowBuild"], spec.get("allowGather", False)))
        activity = next((a for a in observed.get("activities", []) if a["id"] == goal.get("activityId")), None)
        if activity is not None and info["commands"] is not None:
            info["commands"] += 1
            if any(spec.get(k) for k in ("sharePostcard", "paintMosaic", "proposeMosaic", "reviewMosaicProposal")):
                info["commands"] += 1
        reason = info["reason"]
        if reason is None and info["wood"] > spec["budgets"]["wood"]:
            reason = "wood_budget"
        if reason is None and info["commands"] > spec["budgets"]["commands"]:
            reason = "command_budget_estimate"
        candidates.append({**deepcopy(goal), "newBridges": info["bridges"], "woodRequired": info["wood"],
                           "estimatedCommands": info["commands"], "feasible": reason is None, "reason": reason})
        if activity is not None:
            candidates[-1]["description"] = activity["description"]
    context = {"purpose": spec["objective"], "spec": deepcopy(spec), "observation": deepcopy(observed), "candidates": candidates}
    if spec.get("sharePostcard"):
        context["postcardSharing"] = True
    if spec.get("paintMosaic"):
        context["mosaicPainting"] = True
    if spec.get("proposeMosaic"):
        context["mosaicProposing"] = True
    if spec.get("reviewMosaicProposal"):
        context["mosaicReviewing"] = True
    return context


def _decision(value, spec, initial=None):
    if not isinstance(value, dict) or value.get("goalId") not in [g["id"] for g in spec["goals"]]:
        raise ValueError("invalid_goal")
    if not isinstance(value.get("reason"), str) or not 1 <= len(value["reason"]) <= 500:
        raise ValueError("invalid_decision_reason")
    provider = value.get("provider")
    if not isinstance(provider, dict) or provider.get("kind") not in ("codex-exec", "fixed-reference", "test-double"):
        raise ValueError("invalid_provider")
    if not isinstance(provider.get("model"), str) or not 1 <= len(provider["model"]) <= 200:
        raise ValueError("invalid_model")
    if provider["kind"] == "codex-exec" and not re.fullmatch(r"gpt-6(?:[.-][a-zA-Z0-9.-]+)?", provider["model"]):
        raise ValueError("model_must_be_gpt_6")
    if not isinstance(provider.get("usage"), dict):
        raise ValueError("invalid_usage")
    metadata = {key: deepcopy(provider[key]) for key in ("kind", "model", "usage")}
    if len(json.dumps(metadata, allow_nan=False).encode()) > 8192:
        raise ValueError("provider_metadata_too_large")
    # Extra model output is never merged into the report or persisted spec.
    decision = {"goalId": value["goalId"], "reason": value["reason"], "provider": metadata}
    if spec.get("sharePostcard"):
        if not valid_postcard_text(value.get("postcardText")):
            raise ValueError("invalid_postcard_text")
        decision["postcardText"] = value["postcardText"]
    if spec.get("paintMosaic") or spec.get("proposeMosaic"):
        mosaic = validate_mosaic((initial or {}).get("mosaic"))
        decision["mosaicPatch"] = canonical_patch(value.get("mosaicPatch"), mosaic)
        # Only the original observation supplies the revision, never model output
        # or a later poll after movement/another resident's edit.
        decision["mosaicBaseRevision"] = mosaic["revision"]
        if initial["rulesVersion"] == "r6":
            target = patch_target(decision["mosaicPatch"], mosaic, initial["self"]["actorId"],
                                  proposing=bool(spec.get("proposeMosaic")))
            if spec.get("proposeMosaic"):
                decision["mosaicTargetActorId"] = target
    if spec.get("proposeMosaic"):
        if not valid_postcard_text(value.get("proposalText")):
            raise ValueError("invalid_proposal_text")
        decision["proposalText"] = value["proposalText"]
    if spec.get("reviewMosaicProposal"):
        if value.get("reviewDecision") not in ("accept", "reject") or not valid_postcard_text(value.get("reviewText")):
            raise ValueError("invalid_mosaic_review")
        # The model never supplies the proposal, its patch or its base revision.
        proposal = deepcopy(initial["mosaicProposal"])
        decision.update(reviewDecision=value["reviewDecision"], reviewText=value["reviewText"],
                        mosaicProposal=proposal, mosaicPatch=deepcopy(proposal["patch"]),
                        mosaicBaseRevision=proposal["baseRevision"])
    return decision


def _saved_instance(state):
    """An old unbound task may never adopt whichever database is now at its URL."""
    binding = state['_state']['binding']
    version, instance = binding.get('bindingVersion'), binding.get('instanceId')
    if version == 1 and type(version) is int:
        if not isinstance(instance, str) or not re.fullmatch(r'w_[0-9a-f]{32}', instance):
            raise ValueError('Protected mission is missing its valid original world instance')
    elif version is None or type(version) is int and version == 0:
        if instance is not None or state['mission'].get('worldInstanceId') is not None:
            raise ValueError('World instance binding cannot be downgraded to legacy')
    else:
        raise ValueError('Unknown world instance binding version')
    if state['mission'].get('worldInstanceId', instance) != instance:
        raise ValueError('Mission and persisted world instance disagree')
    return instance


def run_mission(client, spec, state_path, choose, *, max_steps=None):
    """Run/resume one task; return the contract report, excluding internal state.

    Invalid input/binding and simultaneous writers raise ValueError/RuntimeError.
    A missing initial observation also raises (there is no bound mission yet).
    Later observation/transport failures return a durable unknown report.
    max_steps counts logical commands handled in this call, including recovery;
    receipt queries do not consume the mission's command budget.
    """
    spec = _spec(spec)
    if max_steps is not None and not _integer(max_steps, 0, 1000):
        raise ValueError("max_steps must be an integer from 0 to 1000, or None")
    path = Path(state_path).resolve()
    with _lock(path):
        state = json.loads(path.read_text()) if path.exists() else None
        endpoint = {"url": client.url.rstrip("/"), "prefix": client.prefix}
        if state is not None:
            saved = state["_state"]
            if saved["spec"] != spec:
                raise ValueError("State belongs to a different mission spec")

        def report():
            result = deepcopy({k: v for k, v in state.items() if k != "_state"})
            # Historical terminal files remain untouched, including their timestamps.
            result["mission"].setdefault("sharePostcard", spec.get("sharePostcard", False))
            result["mission"].setdefault("allowGather", spec.get("allowGather", False))
            result['mission'].setdefault('allowBuild', spec['allowBuild'])
            result["facts"].setdefault("woodGathered", 0)
            result["mission"].setdefault("paintMosaic", spec.get("paintMosaic", False))
            result["mission"].setdefault("proposeMosaic", spec.get("proposeMosaic", False))
            result["mission"].setdefault("reviewMosaicProposal", deepcopy(spec.get("reviewMosaicProposal")))
            result["facts"].setdefault("activityCompleted", False)
            result["facts"].setdefault("activityVisit", None)
            result["facts"].setdefault("postcardShared", False)
            result["facts"].setdefault("postcard", None)
            result["facts"].setdefault("mosaicPainted", False)
            result["facts"].setdefault("mosaicEdit", None)
            for key, default in (("mosaicProposed", False), ("mosaicProposal", None),
                                 ("mosaicReviewed", False), ("mosaicReview", None)):
                result["facts"].setdefault(key, default)
            result["world"].setdefault("mosaic", None)
            result["world"].setdefault("mosaicProposals", [])
            return result

        def save():
            state["budget"]["used"]["seconds"] = max(
                state["budget"]["used"]["seconds"], time.time() - state["_state"]["startedEpoch"])
            _save(path, state)

        def finish(status, reason):
            state["mission"].update(status=status, reason=reason)
            summary = "已核验活动到访与返回" if state["facts"].get("activityCompleted") else "已核验到达与返回"
            if state["facts"].get("postcardShared"):
                summary = "已核验活动到访、共同手记分享与返回"
            if state["facts"].get("mosaicPainted"):
                summary = "已核验活动到访、共同画布修改与返回"
            if state["facts"].get("mosaicProposed"):
                summary = "已核验活动到访、修改提议发表与返回；提议本身未改图"
            if state["facts"].get("mosaicReviewed"):
                summary = ("已核验活动到访、接受提议、实际改图与返回" if state["facts"].get("mosaicPainted")
                           else "已核验活动到访、拒绝提议与返回；未改图")
            if state['facts'].get('constructionBuilt'):
                summary = '已核验指定设施建成、到达与返回'
            state["feedback"] = {"summary": summary if status == "completed" else reason,
                                 "issues": [] if status in ("completed", "paused") else [reason], "suggestions": []}
            save()
            return report()

        def bind(observed):
            return {**endpoint, "worldId": observed["world"]["id"], "actorId": observed["self"]["actorId"],
                    "rulesVersion": observed["rulesVersion"], "instanceId": observed['world'].get('instanceId'),
                    "bindingVersion": 1 if observed['world'].get('instanceId') is not None else 0}

        def observe():
            observed = client.observe()
            actual, original = bind(observed), state['_state']['binding']
            if any(actual[k] != original.get(k) for k in ('worldId', 'actorId', 'rulesVersion', 'instanceId')):
                raise ValueError("State belongs to a different world, actor or rules version")
            # A user-supplied new endpoint is accepted only after the original
            # persistent instance and actor have been authenticated there.
            if original.get('instanceId') is not None:
                original.update(endpoint)
            return observed

        # Terminal reports are historical reads. In particular a canvas conflict
        # cannot restart the journey, reselect, or send a replacement drawing.
        if state is not None and (state["mission"]["status"] in ("completed", "decision_failed")
                                  or (state["mission"]["status"] == "blocked"
                                      and (state["mission"]["reason"] == "command_rejected:MOSAIC_CHANGED"
                                           or ((spec.get("proposeMosaic") or spec.get("reviewMosaicProposal"))
                                               and state["mission"]["reason"].startswith("command_rejected:"))))):
            return report()

        if state is not None:
            instance = _saved_instance(state)
            if instance is None and any(state['_state']['binding'][k] != v for k, v in endpoint.items()):
                raise ValueError('Legacy mission belongs to a different endpoint')

        try:
            if state is not None:
                client.bind_instance(instance)
            observed = observe() if state else client.observe()
        except (OSError, RuntimeError) as error:
            if state is None:
                raise
            return finish("unknown", "observation_unavailable:" + type(error).__name__)
        _validate_goals(spec, observed)
        if not continuous.continuous(observed) and max_steps is not None and max_steps > 100:
            raise ValueError('Legacy grid missions allow at most 100 steps per invocation')
        if state is None:
            proposal = None
            if spec.get("reviewMosaicProposal"):
                observed, proposal = review_input(client, observed, spec["reviewMosaicProposal"])
                _validate_goals(spec, observed)
            public = _public(observed, spec.get("sharePostcard", False), spec.get("paintMosaic", False),
                             bool(spec.get("proposeMosaic") or spec.get("reviewMosaicProposal")))
            if spec.get("reviewMosaicProposal"):
                public["mosaicProposal"] = proposal
            state = {"schemaVersion": 1, "kind": "resident-mission-report",
                     "mission": {"id": spec["missionId"], "objective": spec["objective"],
                                 "allowBuild": spec['allowBuild'],
                                 "allowGather": spec.get("allowGather", False),
                                 "arrivalTolerance": continuous.ARRIVAL_TOLERANCE if continuous.continuous(observed) else 0,
                                 "sharePostcard": spec.get("sharePostcard", False),
                                 "paintMosaic": spec.get("paintMosaic", False),
                                 "proposeMosaic": spec.get("proposeMosaic", False),
                                 "reviewMosaicProposal": deepcopy(spec.get("reviewMosaicProposal")),
                                 "actorId": observed["self"]["actorId"], "worldId": observed["world"]["id"],
                                 "worldInstanceId": observed['world'].get('instanceId'),
                                 "rulesVersion": observed["rulesVersion"], "origin": deepcopy(observed["self"]["position"]),
                                 "goal": None, "status": "running", "reason": "awaiting_decision"},
                     "decision": None, "budget": {"limits": deepcopy(spec["budgets"]),
                                                  "used": {"commands": 0, "wood": 0, "modelCalls": 0, "seconds": 0}},
                     "facts": {"goalReached": False, "returned": True,
                               "activityCompleted": False, "activityVisit": None,
                               "postcardShared": False, "postcard": None,
                               "mosaicPainted": False, "mosaicEdit": None,
                               "mosaicProposed": False, "mosaicProposal": None,
                               "mosaicReviewed": False, "mosaicReview": None,
                               "startStateVersion": observed["stateVersion"],
                               "endStateVersion": observed["stateVersion"], "woodClaimed": 0,
                               "createdEntityIds": [], "verifiedAtUtc": _utc()},
                     "steps": [], "feedback": {"summary": "awaiting_decision", "issues": [], "suggestions": []},
                     "world": {**public["world"], "mosaic": public_mosaic(observed.get("mosaic")),
                               "mosaicProposals": [public_proposal(p) for p in observed.get("mosaicProposals", [])]},
                     "_state": {"spec": spec, "binding": bind(observed), "startedEpoch": time.time(),
                                "pending": None, "initial": public, "decisionStarted": False}}
            save()

        used, limits, facts = state["budget"]["used"], state["budget"]["limits"], state["facts"]
        facts.setdefault("woodGathered", 0)
        facts.setdefault('constructionBuilt', False)
        facts.setdefault('construction', None)
        facts.setdefault("activityCompleted", False)
        facts.setdefault("activityVisit", None)
        facts.setdefault("postcardShared", False)
        facts.setdefault("postcard", None)
        facts.setdefault("mosaicPainted", False)
        facts.setdefault("mosaicEdit", None)
        for key, default in (("mosaicProposed", False), ("mosaicProposal", None),
                             ("mosaicReviewed", False), ("mosaicReview", None)):
            facts.setdefault(key, default)

        def record_observation(observed):
            position = observed["self"]["position"]
            goal = state["mission"]["goal"]
            reached = continuous.near if continuous.continuous(observed) else lambda a, b: a == b
            if goal and reached(position, goal["target"]):
                facts["goalReached"] = True
            facts["returned"] = reached(position, state["mission"]["origin"])
            facts["endStateVersion"] = observed["stateVersion"]
            facts["verifiedAtUtc"] = _utc()
            public = _public(observed, spec.get("sharePostcard", False), spec.get("paintMosaic", False))
            state["world"] = public["world"]
            state["world"]["mosaic"] = public_mosaic(observed.get("mosaic"))
            state["world"]["mosaicProposals"] = [public_proposal(p) for p in observed.get("mosaicProposals", [])]
            if spec.get("sharePostcard"):
                state["world"]["postcards"] = public["postcards"]
            save()

        if state["decision"] is None:
            if state["_state"]["decisionStarted"] or used["modelCalls"]:
                return finish("decision_failed", "decision_interrupted")
            save()
            if used["seconds"] >= limits["seconds"]:
                return finish("budget_exhausted", "seconds")
            state["_state"]["decisionStarted"] = True
            used["modelCalls"] += 1
            save()  # Durable before entering a fallible, potentially slow callback.
            try:
                chosen = _decision(choose(_context(spec, state["_state"]["initial"])), spec,
                                   state["_state"]["initial"])
            except Exception as error:
                # Do not persist arbitrary exception text: it may contain credentials.
                if isinstance(error, ValueError) and str(error) in (
                        "invalid_postcard_text", "invalid_mosaic_patch", "mosaic_patch_unchanged",
                        "mosaic_consent_required", "mosaic_proposal_target_invalid",
                        "invalid_proposal_text", "invalid_mosaic_review"):
                    return finish("decision_failed", "invalid_decision:" + str(error))
                return finish("decision_failed", "decision_failed:" + type(error).__name__)
            state["decision"] = chosen
            state["mission"]["goal"] = deepcopy(next(g for g in spec["goals"] if g["id"] == chosen["goalId"]))
            save()

        handled = 0
        while True:
            try:
                observed = observe()
            except (OSError, RuntimeError) as error:
                return finish("unknown", "observation_unavailable:" + type(error).__name__)
            record_observation(observed)
            pending = state["_state"]["pending"]
            goal = state["mission"]["goal"]
            needs_visit = "activityId" in goal and not facts["activityCompleted"]
            needs_postcard = spec.get("sharePostcard", False) and not facts["postcardShared"]
            needs_mosaic = spec.get("paintMosaic", False) and not facts["mosaicPainted"]
            needs_proposal = spec.get("proposeMosaic", False) and not facts["mosaicProposed"]
            needs_review = bool(spec.get("reviewMosaicProposal")) and not facts["mosaicReviewed"]
            needs_construction = 'buildRecipeId' in goal and not facts['constructionBuilt']
            ready_to_return = (facts["goalReached"] and not any((needs_visit, needs_postcard, needs_mosaic,
                                                               needs_proposal, needs_review, needs_construction)))
            if pending is None:
                if ready_to_return and facts["returned"]:
                    return finish("completed", "round_trip_verified")
                frozen_base_required = (needs_mosaic or needs_proposal
                                        or (needs_review and state["decision"]["reviewDecision"] == "accept"))
                if frozen_base_required and observed["mosaic"]["revision"] != state["decision"]["mosaicBaseRevision"]:
                    return finish("blocked", "command_rejected:MOSAIC_CHANGED")
                if max_steps is not None and handled >= max_steps:
                    return finish("paused", "max_steps")
                if used["seconds"] >= limits["seconds"]:
                    return finish("budget_exhausted", "seconds")
                if used["commands"] >= limits["commands"]:
                    return finish("budget_exhausted", "commands")
                returning = ready_to_return
                target = state["mission"]["origin"] if returning else goal["target"]
                info = (construction.plan(observed, goal, spec.get('allowGather', False)) if needs_construction
                        else _route_info(observed, target, spec['allowBuild'] and 'buildRecipeId' not in goal,
                                         spec.get('allowGather', False)))
                if continuous.continuous(observed):
                    save()  # Geometric planning is part of the wall-time budget.
                    if used['seconds'] >= limits['seconds']:
                        return finish('budget_exhausted', 'seconds')
                if info["reason"]:
                    return finish("blocked", info["reason"])
                if used["wood"] + info["wood"] > limits["wood"]:
                    return finish("budget_exhausted", "wood")
                position = observed["self"]["position"]
                shortage = max(0, info["wood"] - observed["self"]["inventory"]["wood"])
                cost = 0
                if continuous.continuous(observed) and info.get('nextAction'):
                    action, reason = deepcopy(info['nextAction']), info['nextReason']
                    if action['type'] == 'build':
                        cost = next(r['woodCost'] for r in observed['recipes'] if r['id'] == action['recipeId'])
                    if action['type'] == 'walk':
                        time.sleep(observed['movement']['maxStepDistance'] / observed['movement']['speed'] + .005)
                        save()
                        if used['seconds'] >= limits['seconds']:
                            return finish('budget_exhausted', 'seconds')
                elif needs_visit and position == goal["target"]:
                    action, reason = {"type": "visit", "activityId": goal["activityId"]}, "在已选活动地点确认到访"
                elif needs_postcard and position == goal["target"]:
                    action = {"type": "postcard", "activityId": goal["activityId"],
                              "visitCommandId": facts["activityVisit"]["commandId"],
                              "text": state["decision"]["postcardText"]}
                    reason = "在已确认到访的地点分享共同手记草稿"
                elif needs_mosaic and position == goal["target"]:
                    action = {"type": "mosaic", "activityId": "garden",
                              "visitCommandId": facts["activityVisit"]["commandId"],
                              "expectedMosaicRevision": state["decision"]["mosaicBaseRevision"],
                              "patch": deepcopy(state["decision"]["mosaicPatch"])}
                    reason = "在已确认到访的花园提交原画布草图"
                elif needs_proposal and position == goal["target"]:
                    action = {"type": "mosaic_propose", "activityId": "garden",
                              "visitCommandId": facts["activityVisit"]["commandId"],
                              "expectedMosaicRevision": state["decision"]["mosaicBaseRevision"],
                              "patch": deepcopy(state["decision"]["mosaicPatch"]),
                              "text": state["decision"]["proposalText"]}
                    reason = "在已确认到访的花园提交原修改提议；提议不改图"
                elif needs_review and position == goal["target"]:
                    proposal = state["decision"]["mosaicProposal"]
                    action = {"type": "mosaic_review", "activityId": "garden",
                              "visitCommandId": facts["activityVisit"]["commandId"],
                              "proposalActorId": proposal["authorActorId"], "proposalCommandId": proposal["commandId"],
                              "decision": state["decision"]["reviewDecision"], "text": state["decision"]["reviewText"]}
                    reason = "在已确认到访的花园提交原提议的审阅决定"
                elif shortage:
                    depot = observed["depot"]["position"]
                    if info.get("collection"):
                        action = deepcopy(info["collection"][0])
                        reason = "采集剩余桥梁所需木材" if action["type"] == "gather" else "走到可达树木旁补足建桥材料"
                    elif sum(abs(a-b) for a, b in zip(position, depot)) <= 1:
                        action, reason = {"type": "claim", "quantity": shortage}, "为剩余桥梁补足材料"
                    else:
                        nxt = plan(observed, depot, False)[0][0]
                        action = {"type": "move", "dx": nxt[0]-position[0], "dy": nxt[1]-position[1]}
                        reason = "前往公共储备点"
                else:
                    nxt = info["cells"][0]
                    if nxt in {tuple(p) for p in observed["world"]["blocked"]}:
                        action = {"type": "build", "recipeId": "bridge.v1", "at": list(nxt)}
                        cost = next(r["woodCost"] for r in observed["recipes"] if r["id"] == "bridge.v1")
                        reason = "建造通向任务目标的桥段"
                    else:
                        action = {"type": "move", "dx": nxt[0]-position[0], "dy": nxt[1]-position[1]}
                        reason = "返回原起点" if returning else "前往已选目标"
                intent = {"schemaVersion": 1, "rulesVersion": observed["rulesVersion"], "commandId": uuid.uuid4().hex,
                          "expectedStateVersion": observed["stateVersion"], "action": action}
                pending = {"request": intent, "woodCost": cost}
                if needs_construction and action['type'] == 'build':
                    pending['constructionBefore'] = {'inventoryWood': observed['self']['inventory']['wood']}
                if action['type'] == 'walk':
                    pending['walkBefore'] = {'position': deepcopy(position), 'maxStepDistance': observed['movement']['maxStepDistance']}
                if action["type"] == "gather":
                    node = next(n for n in observed["resourceNodes"] if n["nodeId"] == action["nodeId"])
                    pending["gatherBefore"] = {"position": deepcopy(node["position"]),
                                              "remainingWood": node["remainingWood"],
                                              "inventoryWood": observed["self"]["inventory"]["wood"]}
                state["_state"]["pending"] = pending
                used["commands"] += 1
                state["steps"].append({"index": used["commands"], "commandId": intent["commandId"],
                                       "action": deepcopy(action), "reason": reason, "status": "pending",
                                       "stateVersion": observed["stateVersion"], "position": deepcopy(position),
                                       "inventoryWood": observed["self"]["inventory"]["wood"]})
                state["mission"].update(status="running", reason="command_pending")
                save()  # A crash after this point must recover this exact request.
                recovery = False
            else:
                intent = pending["request"]
                recovery = True

            step = state["steps"][-1]
            consent_kind = intent["action"]["type"]
            consent_validator = {"mosaic_propose": proposal_evidence, "mosaic_review": review_evidence}.get(consent_kind)
            def consent_fact(record):
                if consent_kind == "mosaic_propose":
                    facts.update(mosaicProposed=True, mosaicProposal=record)
                else:
                    facts.update(mosaicReviewed=True, mosaicReview=record,
                                 mosaicPainted=record["decision"] == "accept", mosaicEdit=deepcopy(record["mosaicEdit"]))

            if recovery and consent_validator:
                collection = "mosaicProposals" if consent_kind == "mosaic_propose" else "mosaicReviews"
                records = [consent_validator(record, intent, goal, state["mission"]["actorId"],
                                             facts["activityVisit"], state["decision"])
                           for record in observed["self"].get(collection, [])]
                record = next((r for r in records if r is not None and r["stateVersion"] <= observed["stateVersion"]), None)
                if record is not None:
                    consent_fact(record)
                    step.update(status="committed", stateVersion=record["stateVersion"],
                                position=deepcopy(record["position"]), evidenceSource="self." + collection)
                    state["_state"]["pending"] = None
                    save()
                    handled += 1
                    continue
            if recovery and intent["action"]["type"] == "visit":
                # Only this actor's server observation and the persisted command ID
                # qualify. Never infer completion from an earlier visit or a peer.
                visits = [_activity_visit(v, intent, goal) for v in observed["self"].get("visits", [])]
                visit = next((v for v in visits if v is not None and v["stateVersion"] <= observed["stateVersion"]), None)
                if visit is not None:
                    facts.update(activityCompleted=True, activityVisit=visit, goalReached=True)
                    step.update(status="committed", stateVersion=visit["stateVersion"],
                                position=deepcopy(visit["position"]), evidenceSource="self.visits")
                    state["_state"]["pending"] = None
                    save()
                    handled += 1
                    continue
            if recovery and intent["action"]["type"] == "postcard":
                cards = [_postcard(card, intent, goal, state["mission"]["actorId"],
                                   facts["activityVisit"], state["decision"].get("postcardText"))
                         for card in observed["self"].get("postcards", [])]
                card = next((card for card in cards if card is not None
                             and card["stateVersion"] <= observed["stateVersion"]), None)
                if card is not None:
                    facts.update(postcardShared=True, postcard=card)
                    step.update(status="committed", stateVersion=card["stateVersion"],
                                position=deepcopy(card["position"]), evidenceSource="self.postcards")
                    state["_state"]["pending"] = None
                    save()
                    handled += 1
                    continue
            if recovery and intent["action"]["type"] == "mosaic":
                edits = [_mosaic_edit(edit, intent, goal, state["mission"]["actorId"],
                                      facts["activityVisit"], state["decision"])
                         for edit in observed["self"].get("mosaicEdits", [])]
                edit = next((edit for edit in edits if edit is not None
                             and edit["stateVersion"] <= observed["stateVersion"]), None)
                if edit is not None:
                    facts.update(mosaicPainted=True, mosaicEdit=edit)
                    step.update(status="committed", stateVersion=edit["stateVersion"],
                                position=deepcopy(edit["position"]), evidenceSource="self.mosaicEdits")
                    state["_state"]["pending"] = None
                    save()
                    handled += 1
                    continue
            receipt_query = recovery
            try:
                if recovery:
                    status, result = client.request("GET", client.prefix + "/commands/" + intent["commandId"])
                    if status == 404 and isinstance(result, dict) and (result.get("error") or {}).get("code") == "COMMAND_NOT_FOUND":
                        # A confirmed absent original submission may not accept a stale base.
                        # Query errors never reach this branch or justify a replacement ID.
                        if (intent["action"]["type"] in ("mosaic_propose", "mosaic_review")
                                and (intent["action"]["type"] == "mosaic_propose"
                                     or intent["action"].get("decision") == "accept")
                                and observed["mosaic"]["revision"] != state["decision"]["mosaicBaseRevision"]):
                            return finish("blocked", "command_rejected:MOSAIC_CHANGED")
                        if used["seconds"] >= limits["seconds"]:
                            return finish("budget_exhausted", "seconds_pending_not_sent")
                        if max_steps is not None and handled >= max_steps:
                            return finish("paused", "max_steps_pending_not_sent")
                        receipt_query = False
                        status, result = client.command(deepcopy(intent))
                else:
                    status, result = client.command(deepcopy(intent))
            except (OSError, RuntimeError, ValueError) as error:
                step["status"] = "unknown"
                return finish("unknown", "pending_command_retained:" + type(error).__name__)
            step["httpStatus"] = status
            error = result.get("error") if isinstance(result, dict) else None
            if status == 401 or status >= 500:
                step["status"] = "unknown"
                return finish("unknown", "session_required_for_recovery" if status == 401 else "pending_command_retained")
            committed = (status == 200 and isinstance(result, dict) and result.get("status") == "committed"
                         and result.get("commandId") == intent["commandId"] and not error)
            rejected = (400 <= status < 500 and isinstance(error, dict) and error.get("mutated") is False
                        and status not in (404, 412, 428)
                        and error.get("code") not in ("IDEMPOTENCY_CONFLICT", "INVALID_WORLD_INSTANCE",
                                                     "WORLD_INSTANCE_REQUIRED", "WORLD_INSTANCE_MISMATCH", "WORLD_INSTANCE_UNAVAILABLE")
                        and (not receipt_query or (result.get("status") == "rejected"
                                                   and result.get("commandId") == intent["commandId"])))
            if consent_validator and isinstance(error, dict) and error.get("code") == "STALE_STATE":
                # Only this attempt's authoritative rejection permits a fresh ID.
                # A proxy/query error that resembles STALE_STATE cannot settle it.
                rejected = (rejected and result.get("status") == "rejected"
                            and result.get("commandId") == intent["commandId"])
            if (intent["action"]["type"] in ("gather", "walk") or 'constructionBefore' in pending) and rejected:
                rejected = (result.get("status") == "rejected" and result.get("commandId") == intent["commandId"]
                            and isinstance(result.get("identity"), dict)
                            and result["identity"].get("actorId") == state["mission"]["actorId"]
                            and result.get("schemaVersion") == 1 and result.get("rulesVersion") == intent['rulesVersion'])
            if not committed and not rejected:
                step["status"] = "unknown"
                return finish("unknown", "unconfirmed_receipt")
            if committed:
                result_action = result.get("result", {})
                if not isinstance(result_action, dict) or result_action.get("action") != intent["action"]["type"]:
                    step["status"] = "unknown"
                    return finish("unknown", "unexpected_receipt_action")
                if intent['action']['type'] == 'walk':
                    if not continuous.valid_walk_receipt(result, intent, state['mission']['actorId'], pending.get('walkBefore')):
                        step['status'] = 'unknown'
                        return finish('unknown', 'unconfirmed_walk_receipt')
                    step['position'] = deepcopy(result_action['position'])
                    step['blocked'] = result_action['blocked']
                    step['evidenceSource'] = 'command_receipt'
                elif intent["action"]["type"] == "gather":
                    if not valid_gather_receipt(result, intent, state["mission"]["actorId"], pending.get("gatherBefore")):
                        step["status"] = "unknown"
                        return finish("unknown", "unconfirmed_gather_receipt")
                    facts["woodGathered"] += 1
                    step["evidenceSource"] = "command_receipt"
                elif 'constructionBefore' in pending:
                    try:
                        after_build = observe()
                    except (OSError, RuntimeError, ValueError):
                        step['status'] = 'unknown'
                        return finish('unknown', 'construction_observation_unavailable')
                    built = construction.evidence(result, intent, state['mission']['actorId'],
                                                  pending['constructionBefore'], after_build)
                    if built is None:
                        step['status'] = 'unknown'
                        return finish('unknown', 'unconfirmed_construction_receipt')
                    record_observation(after_build)
                    # A visit before construction cannot replace visiting the
                    # completed facility. The actor may already be at its center.
                    facts.update(constructionBuilt=True, construction=built,
                                 goalReached=continuous.near(after_build['self']['position'], goal['target']))
                    step['entityId'] = built['entityId']
                    step['evidenceSource'] = 'command_receipt_and_entity'
                elif intent["action"]["type"] == "visit":
                    visit = _activity_visit({**result_action, "commandId": result["commandId"],
                                             "stateVersion": result.get("stateVersion")}, intent, goal)
                    if visit is None:
                        step["status"] = "unknown"
                        return finish("unknown", "unconfirmed_activity_receipt")
                    facts.update(activityCompleted=True, activityVisit=visit, goalReached=True)
                    step["position"] = deepcopy(visit["position"])
                    step["evidenceSource"] = "command_receipt"
                elif intent["action"]["type"] == "postcard":
                    card = _postcard(result_action, intent, goal, state["mission"]["actorId"],
                                     facts["activityVisit"], state["decision"].get("postcardText"))
                    if (card is None or type(result.get("stateVersion")) is not int
                            or card["stateVersion"] != result["stateVersion"]):
                        step["status"] = "unknown"
                        return finish("unknown", "unconfirmed_postcard_receipt")
                    facts.update(postcardShared=True, postcard=card)
                    step["position"] = deepcopy(card["position"])
                    step["evidenceSource"] = "command_receipt"
                elif intent["action"]["type"] == "mosaic":
                    edit = _mosaic_edit(result_action, intent, goal, state["mission"]["actorId"],
                                        facts["activityVisit"], state["decision"])
                    if (edit is None or type(result.get("stateVersion")) is not int
                            or edit["stateVersion"] != result["stateVersion"]):
                        step["status"] = "unknown"
                        return finish("unknown", "unconfirmed_mosaic_receipt")
                    facts.update(mosaicPainted=True, mosaicEdit=edit)
                    step["position"] = deepcopy(edit["position"])
                    step["evidenceSource"] = "command_receipt"
                elif consent_validator:
                    record = consent_validator(result_action, intent, goal, state["mission"]["actorId"],
                                               facts["activityVisit"], state["decision"])
                    if (record is None or type(result.get("stateVersion")) is not int
                            or record["stateVersion"] != result["stateVersion"]):
                        step["status"] = "unknown"
                        return finish("unknown", "unconfirmed_" + consent_kind + "_receipt")
                    consent_fact(record)
                    step["position"] = deepcopy(record["position"])
                    step["evidenceSource"] = "command_receipt"
                step["status"] = "committed"
                step["stateVersion"] = result["stateVersion"]
                if intent["action"]["type"] == "build":
                    used["wood"] += pending["woodCost"]
                    facts["createdEntityIds"].append(result_action["entityId"])
                elif intent["action"]["type"] == "claim":
                    facts["woodClaimed"] += intent["action"]["quantity"]
                if "inventoryWood" in result_action:
                    step["inventoryWood"] = result_action["inventoryWood"]
                if intent["action"]["type"] == "move":
                    step["position"] = deepcopy(result_action["position"])
            else:
                step.update(status="rejected", errorCode=error.get("code"))
            # Settlement, accounting and clearing pending are one atomic write.
            state["_state"]["pending"] = None
            save()
            handled += 1
            if committed and intent['action']['type'] == 'walk' and result_action['blocked']:
                return finish('blocked', 'movement_collision')
            retryable = ("STALE_STATE",) if consent_validator else ("STALE_STATE", "CELL_OCCUPIED")
            if rejected and error.get("code") not in retryable:
                return finish("blocked", "command_rejected:" + str(error.get("code")))
