"""mosaic-v1 public snapshots and strict, canonical bounded patches."""

from copy import deepcopy


COLORS = ("blank", "leaf", "river", "sun", "rose", "ink")


def public_mosaic(value):
    """Copy only the public canvas fields; never forward arbitrary observation data."""
    if value is None:
        return None
    return {**{key: deepcopy(value[key]) for key in ("activityId", "width", "height", "revision")},
            "palette": [{key: deepcopy(color[key]) for key in ("id", "label", "hex")}
                        for color in value["palette"]],
            "cells": [{key: deepcopy(cell[key]) for key in
                       ("x", "y", "color", "authorActorId", "commandId", "stateVersion")}
                      for cell in value["cells"]]}


def validate_mosaic(value):
    """Require the r5 garden capability, including all 25 distinct current cells."""
    if (not isinstance(value, dict) or value.get("activityId") != "garden"
            or any(type(value.get(key)) is not int or value[key] != 5 for key in ("width", "height"))
            or type(value.get("revision")) is not int or value["revision"] < 0
            or not isinstance(value.get("palette"), list)
            or not isinstance(value.get("cells"), list) or len(value["cells"]) != 25):
        raise ValueError("invalid_mosaic_capability")
    if (any(not isinstance(color, dict) or not isinstance(color.get("label"), str)
            or not isinstance(color.get("hex"), str) for color in value["palette"])
            or [color.get("id") for color in value["palette"]] != list(COLORS)):
        raise ValueError("invalid_mosaic_capability")
    for index, cell in enumerate(value["cells"]):
        if (not isinstance(cell, dict)
                or type(cell.get("x")) is not int or type(cell.get("y")) is not int
                or (cell["x"], cell["y"]) != (index % 5, index // 5)
                or cell.get("color") not in COLORS
                or any(key not in cell for key in ("authorActorId", "commandId", "stateVersion"))):
            raise ValueError("invalid_mosaic_capability")
        author, command, version = (cell[key] for key in ("authorActorId", "commandId", "stateVersion"))
        if author is None:
            if command is not None or version is not None:
                raise ValueError("invalid_mosaic_capability")
        elif (not isinstance(author, str) or not author or not isinstance(command, str) or not command
              or type(version) is not int or version < 1):
            raise ValueError("invalid_mosaic_capability")
    return value


def canonical_patch(value, mosaic=None):
    """Validate exact structure and optional observed colors, then sort by y/x."""
    if not isinstance(value, list) or not 1 <= len(value) <= 8:
        raise ValueError("invalid_mosaic_patch")
    seen = set()
    for cell in value:
        if (not isinstance(cell, dict) or set(cell) != {"x", "y", "color"}
                or any(type(cell[key]) is not int or not 0 <= cell[key] < 5 for key in ("x", "y"))
                or cell["color"] not in COLORS):
            raise ValueError("invalid_mosaic_patch")
        coordinate = cell["x"], cell["y"]
        if coordinate in seen:
            raise ValueError("invalid_mosaic_patch")
        seen.add(coordinate)
    if mosaic is not None:
        validate_mosaic(mosaic)
        colors = {(cell["x"], cell["y"]): cell["color"] for cell in mosaic["cells"]}
        if any(colors[cell["x"], cell["y"]] == cell["color"] for cell in value):
            raise ValueError("mosaic_patch_unchanged")
    return [{key: deepcopy(cell[key]) for key in ("x", "y", "color")}
            for cell in sorted(value, key=lambda cell: (cell["y"], cell["x"]))]


def patch_target(patch, mosaic, actor_id, *, proposing=False):
    """Check r6 provenance even for blank cells; return a proposal's sole target."""
    validate_mosaic(mosaic)
    authors = []
    cells = {(cell["x"], cell["y"]): cell for cell in mosaic["cells"]}
    for change in canonical_patch(patch):
        authors.append(cells[change["x"], change["y"]]["authorActorId"])
    if proposing:
        if any(author is None or author == actor_id for author in authors) or len(set(authors)) != 1:
            raise ValueError("mosaic_proposal_target_invalid")
        return authors[0]
    if any(author is not None and author != actor_id for author in authors):
        raise ValueError("mosaic_consent_required")
    return None
