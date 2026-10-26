"""Read one original public proposal independently of the recent observation window."""

import re

from mosaic_consent import select_proposal


def _integer(value):
    return type(value) is int and value >= 0


def _binding(observed):
    return (observed["world"]["id"], observed["self"]["actorId"], observed["rulesVersion"])


def _capability(observed):
    value = observed.get("mosaicProposalInbox")
    if (not isinstance(value, dict) or type(value.get("version")) is not int
            or value["version"] != 1 or type(value.get("maxPageSize")) is not int
            or value["maxPageSize"] != 20 or observed.get("rulesVersion") != "r6"):
        raise ValueError("invalid_mosaic_inbox_capability")


def review_input(client, observed, reference):
    """New-task preflight only. Existing pending work never calls this lookup again."""
    if "mosaicProposalInbox" not in observed:
        return observed, select_proposal(observed, reference)
    _capability(observed)
    if any(not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", value) for value in reference.values()):
        raise ValueError("invalid_mosaic_proposal_reference")
    status, response = client.request(
        "GET", client.prefix + "/mosaic-proposals/" + reference["proposalActorId"]
        + "/" + reference["proposalCommandId"])
    if status != 200:
        if (status == 404 and isinstance(response, dict)
                and isinstance(response.get("error"), dict)
                and response["error"].get("code") == "MOSAIC_PROPOSAL_NOT_FOUND"):
            raise ValueError("mosaic_proposal_not_found")
        raise RuntimeError("mosaic_proposal_lookup_unavailable")
    if (not isinstance(response, dict) or type(response.get("schemaVersion")) is not int
            or response["schemaVersion"] != 1 or response.get("rulesVersion") != "r6"
            or response.get("error") is not None or not _integer(response.get("stateVersion"))
            or not _integer(response.get("eventCursor"))
            or not isinstance(response.get("identity"), dict)
            or response["identity"].get("actorId") != observed["self"]["actorId"]):
        raise ValueError("invalid_mosaic_proposal_lookup")
    proposal = response.get("proposal")
    if (not isinstance(proposal, dict)
            or proposal.get("authorActorId") != reference["proposalActorId"]
            or proposal.get("commandId") != reference["proposalCommandId"]
            or not _integer(proposal.get("stateVersion"))
            or proposal["stateVersion"] > response["stateVersion"]):
        raise ValueError("invalid_mosaic_proposal_lookup")
    if response["stateVersion"] > observed["stateVersion"]:
        refreshed = client.observe()
        if (_binding(refreshed) != _binding(observed)
                or not _integer(refreshed.get("stateVersion"))
                or refreshed["stateVersion"] < response["stateVersion"]):
            raise ValueError("mosaic_proposal_observation_changed")
        _capability(refreshed)
        observed = refreshed
    # Reuse the complete proposal/target/review/baseline checks, never a text match.
    proposal = select_proposal({**observed, "mosaicProposals": [proposal]}, reference)
    return observed, proposal
