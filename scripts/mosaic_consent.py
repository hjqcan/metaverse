"""consent-v1 public records and exact evidence for a persisted original command."""

from copy import deepcopy
from datetime import datetime, timedelta

from mosaic_patch import canonical_patch
from postcard_text import valid_postcard_text


PROPOSAL_FIELDS = ("activityId", "authorActorId", "targetActorId", "commandId", "visitCommandId",
                   "baseRevision", "patch", "text", "stateVersion", "proposedAtUtc", "position")
REVIEW_FIELDS = ("activityId", "authorActorId", "commandId", "visitCommandId", "proposalActorId",
                 "proposalCommandId", "decision", "text", "stateVersion", "reviewedAtUtc", "position", "mosaicEdit")
EDIT_FIELDS = ("activityId", "authorActorId", "commandId", "visitCommandId", "baseRevision", "revision",
               "patch", "stateVersion", "paintedAtUtc", "position")


def _pick(value, fields):
    return {key: deepcopy(value[key]) for key in fields}


def public_proposal(value):
    """Whitelist the complete public record, including a whitelisted nested review."""
    proposal = _pick(value, PROPOSAL_FIELDS)
    review = value.get("review")
    proposal["review"] = None if review is None else _pick(review, REVIEW_FIELDS)
    if review is not None and review.get("mosaicEdit") is not None:
        proposal["review"]["mosaicEdit"] = _pick(review["mosaicEdit"], EDIT_FIELDS)
    return proposal


def _nonempty(value):
    return isinstance(value, str) and bool(value)


def _position(value):
    return (isinstance(value, list) and value == [1, 6]
            and all(type(n) is int for n in value))


def _utc_timestamp(value):
    if not _nonempty(value):
        return False
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return "T" in value and parsed.utcoffset() == timedelta(0)
    except ValueError:
        return False


def valid_proposal(value):
    if (not isinstance(value, dict) or not set(PROPOSAL_FIELDS) <= set(value)
            or value["activityId"] != "garden" or not _position(value["position"])
            or any(not _nonempty(value[key]) for key in
                   ("authorActorId", "targetActorId", "commandId", "visitCommandId"))
            or not _utc_timestamp(value["proposedAtUtc"])
            or value["authorActorId"] == value["targetActorId"]
            or type(value["baseRevision"]) is not int or value["baseRevision"] < 0
            or type(value["stateVersion"]) is not int or value["stateVersion"] < 1
            or not valid_postcard_text(value["text"])):
        return False
    try:
        return canonical_patch(value["patch"]) == value["patch"]
    except ValueError:
        return False


def select_proposal(observed, reference):
    """Only an unreviewed public proposal directed at this actor can be selected."""
    proposals = observed.get("mosaicProposals")
    if not isinstance(proposals, list):
        raise ValueError("invalid_mosaic_consent_capability")
    matches = [p for p in proposals if isinstance(p, dict)
               and p.get("authorActorId") == reference["proposalActorId"]
               and p.get("commandId") == reference["proposalCommandId"]]
    if len(matches) != 1:
        raise ValueError("mosaic_proposal_not_found")
    proposal = matches[0]
    if (not valid_proposal(proposal) or "review" not in proposal
            or proposal["stateVersion"] > observed["stateVersion"]
            or proposal["baseRevision"] > observed["mosaic"]["revision"]):
        raise ValueError("invalid_mosaic_proposal")
    if proposal["targetActorId"] != observed["self"]["actorId"]:
        raise ValueError("mosaic_review_forbidden")
    if proposal["review"] is not None:
        raise ValueError("mosaic_proposal_reviewed")
    return public_proposal(proposal)


def _common(value, intent, goal, actor_id, visit, action_type):
    action = intent["action"]
    return (isinstance(value, dict) and isinstance(visit, dict)
            and intent.get("rulesVersion") == "r6" and action.get("type") == action_type
            and goal.get("activityId") == "garden" and _position(goal.get("target"))
            and action.get("activityId") == "garden" and visit.get("activityId") == "garden"
            and _position(visit.get("position")) and _nonempty(visit.get("commandId"))
            and _nonempty(visit.get("visitedAtUtc"))
            and action.get("visitCommandId") == visit["commandId"]
            and value.get("activityId") == "garden" and _position(value.get("position"))
            and value.get("authorActorId") == actor_id and value.get("commandId") == intent["commandId"]
            and value.get("visitCommandId") == visit["commandId"]
            and type(visit.get("stateVersion")) is int and type(intent.get("expectedStateVersion")) is int
            and 0 < visit["stateVersion"] <= intent["expectedStateVersion"]
            and type(value.get("stateVersion")) is int
            and value["stateVersion"] == intent["expectedStateVersion"] + 1)


def proposal_evidence(value, intent, goal, actor_id, visit, decision):
    if (not _common(value, intent, goal, actor_id, visit, "mosaic_propose")
            or not valid_proposal(value)):
        return None
    action = intent["action"]
    base = decision.get("mosaicBaseRevision")
    text = decision.get("proposalText")
    if (type(base) is not int or base < 0
            or type(action.get("expectedMosaicRevision")) is not int
            or action["expectedMosaicRevision"] != base or value["baseRevision"] != base
            or not valid_postcard_text(text) or action.get("text") != text or value["text"] != text
            or value["targetActorId"] != decision.get("mosaicTargetActorId")):
        return None
    try:
        patch = canonical_patch(decision.get("mosaicPatch"))
        if canonical_patch(action.get("patch")) != patch or value["patch"] != patch:
            return None
    except ValueError:
        return None
    return _pick(value, PROPOSAL_FIELDS)


def review_evidence(value, intent, goal, actor_id, visit, decision):
    if not _common(value, intent, goal, actor_id, visit, "mosaic_review"):
        return None
    proposal, action = decision.get("mosaicProposal"), intent["action"]
    choice, text = decision.get("reviewDecision"), decision.get("reviewText")
    if (not valid_proposal(proposal) or proposal.get("review") is not None
            or proposal["targetActorId"] != actor_id
            or proposal["stateVersion"] > intent["expectedStateVersion"]
            or choice not in ("accept", "reject") or not valid_postcard_text(text)
            or not _utc_timestamp(value.get("reviewedAtUtc")) or "mosaicEdit" not in value):
        return None
    for key, expected in (("proposalActorId", proposal["authorActorId"]),
                          ("proposalCommandId", proposal["commandId"]), ("decision", choice), ("text", text)):
        if action.get(key) != expected or value.get(key) != expected:
            return None
    edit = value["mosaicEdit"]
    if choice == "reject":
        if edit is not None:
            return None
    else:
        expected = {"activityId": "garden", "authorActorId": actor_id, "commandId": intent["commandId"],
                    "visitCommandId": visit["commandId"], "baseRevision": proposal["baseRevision"],
                    "revision": proposal["baseRevision"] + 1, "patch": proposal["patch"],
                    "stateVersion": value["stateVersion"], "paintedAtUtc": value["reviewedAtUtc"], "position": [1, 6]}
        if (not isinstance(edit, dict) or not set(EDIT_FIELDS) <= set(edit)
                or any(type(edit.get(k)) is not int for k in ("baseRevision", "revision", "stateVersion"))
                or not _position(edit.get("position")) or _pick(edit, EDIT_FIELDS) != expected):
            return None
        try:
            if canonical_patch(edit["patch"]) != proposal["patch"]:
                return None
        except ValueError:
            return None
    review = _pick(value, REVIEW_FIELDS)
    if edit is not None:
        review["mosaicEdit"] = _pick(edit, EDIT_FIELDS)
    return review
