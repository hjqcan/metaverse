"""Plan a bounded material detour from observed trees; never mutates world facts."""
from copy import deepcopy

from passage_agent import plan
from math import isfinite
from command_preconditions import ACTOR_STATE, integer, valid_execution


def collection_plan(observed, quantity):
    """Return actions and a private forecast, or no partial plan on shortage.

    Only already walkable routes may lead to a source. Depleting a tree opens
    its cell in this forecast; each actual command still requires a fresh read.
    """
    if (observed.get("rulesVersion") != "r7"
            or observed.get("gathering") != {"version": 1, "quantityPerAction": 1}):
        return {"reason": "gathering_unavailable", "actions": []}
    forecast = deepcopy(observed)
    actions = []
    while quantity > 0:
        choices = []
        for node in forecast.get("resourceNodes", []):
            if node["kind"] != "tree" or node["remainingWood"] <= 0:
                continue
            x, y = node["position"]
            for order, (dx, dy) in enumerate(((1, 0), (0, 1), (-1, 0), (0, -1))):
                route = plan(forecast, [x + dx, y + dy], False)
                if route is not None:
                    choices.append((len(route[0]), node["nodeId"], order, route[0], node))
        if not choices:
            return {"reason": "insufficient_reachable_natural_material", "actions": []}
        _, _, _, cells, node = min(choices, key=lambda item: item[:3])
        for cell in cells:
            position = forecast["self"]["position"]
            actions.append({"type": "move", "dx": cell[0] - position[0], "dy": cell[1] - position[1]})
            forecast["self"]["position"] = list(cell)
        harvested = min(quantity, node["remainingWood"])
        actions.extend({"type": "gather", "nodeId": node["nodeId"]} for _ in range(harvested))
        forecast["self"]["inventory"]["wood"] += harvested
        node["remainingWood"] -= harvested
        quantity -= harvested
        if node["remainingWood"] == 0:
            forecast["world"]["blocked"] = [p for p in forecast["world"]["blocked"] if p != node["position"]]
    return {"reason": None, "actions": actions, "forecast": forecast}


def valid_gather_receipt(receipt, intent, actor, before):
    """Match the original cut, including pre-submit quantities, after reconnect."""
    result = receipt.get("result")
    if (not isinstance(result, dict) or not isinstance(before, dict)
            or not isinstance(receipt.get("identity"), dict)
            or not integer(before.get('remainingWood')) or not integer(before.get('inventoryWood'))
            or not isinstance(before.get('position'), list) or len(before['position']) != 2):
        return False
    remaining = before['remainingWood']
    if intent.get('preconditionMode') == ACTOR_STATE:
        remaining = result.get('remainingWoodBefore')
        if not integer(remaining) or not 1 <= remaining <= before['remainingWood']:
            return False
    expected = {"action": "gather", "nodeId": intent["action"]["nodeId"], "quantity": 1,
                "position": before["position"], "remainingWood": remaining - 1,
                "inventoryWood": before["inventoryWood"] + 1}
    return (type(receipt.get("schemaVersion")) is int and receipt["schemaVersion"] == 1
            and receipt.get("rulesVersion") == intent["rulesVersion"] in ("r7", "r8", "r9", "r10")
            and receipt.get("identity", {}).get("actorId") == actor
            and valid_execution(receipt, intent)
            and all(result.get(key) == value and type(result.get(key)) is type(value)
                    for key, value in expected.items())
            and all(type(n) is int if intent['rulesVersion'] == 'r7' else type(n) in (int, float) and isfinite(n)
                    for n in result["position"]))
