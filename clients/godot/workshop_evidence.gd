extends RefCounted
## Original workshop transactions remain provable after later chest activity.
const Notes = preload("res://entity_note_evidence.gd")
const Canvas = preload("res://entity_canvas_evidence.gd")
const TYPES = ["build_workshop", "craft_tool", "deposit_wood", "withdraw_wood"]
const RECIPES = [
	{"id": "workbench.v1", "definitionId": "workbench", "woodCost": 3, "requiresWorkbench": false, "requiresTool": false},
	{"id": "wooden_mallet.v1", "definitionId": "wooden_mallet", "woodCost": 1, "requiresWorkbench": true, "requiresTool": false},
	{"id": "wooden_chest.v1", "definitionId": "wooden_chest", "woodCost": 3, "requiresWorkbench": false, "requiresTool": true}]
const DETAIL_FIELDS = ["capabilityVersion", "authorActorId", "operatorId", "commandId", "action", "entity", "tool", "quantity",
	"inventoryWoodBefore", "inventoryWood", "storedWoodBefore", "storedWood", "position", "stateVersion", "eventCursor", "completedAtUtc"]

static func is_action(value: Variant) -> bool:
	return value in TYPES

static func same(a: Variant, b: Variant) -> bool:
	if typeof(a) in [TYPE_INT, TYPE_FLOAT] and typeof(b) in [TYPE_INT, TYPE_FLOAT]:
		return a == b
	if a is Array and b is Array:
		if a.size() != b.size():
			return false
		for i in a.size():
			if not same(a[i], b[i]):
				return false
		return true
	if a is Dictionary and b is Dictionary:
		if a.size() != b.size():
			return false
		for key in a:
			if not b.has(key) or not same(a[key], b[key]):
				return false
		return true
	return typeof(a) == typeof(b) and a == b

static func half_size(definition: String) -> Vector2:
	return {"platform": Vector2.ONE, "bridge": Vector2(2.4, 0.8), "workbench": Vector2(1, 0.5), "wooden_chest": Vector2(0.5, 0.5)}.get(definition, Vector2.ZERO)

static func valid_entity(value: Variant) -> bool:
	return value is Dictionary and value.size() == 7 and Notes.id(value.get("entityId"), "e") \
		and value.get("definitionId") in ["workbench", "wooden_chest"] and value.get("definitionVersion") == 1 \
		and value.get("rulesVersion") == "r10" and value.get("ownerActorId") in Notes.ROSTER \
		and Notes.point(value.get("position")) and value.get("embodiedWood") == 3

static func valid_tool(value: Variant) -> bool:
	return value is Dictionary and value.size() == 9 and Notes.id(value.get("toolId"), "t") \
		and value.get("definitionId") == "wooden_mallet" and value.get("definitionVersion") == 1 \
		and value.get("ownerActorId") in Notes.ROSTER and value.get("embodiedWood") == 1 \
		and Notes.id(value.get("workbenchId"), "e") and value.get("commandId") is String and not value.commandId.is_empty() \
		and Notes.whole(value.get("stateVersion")) and value.stateVersion > 0 \
		and Notes.whole(value.get("eventCursor")) and value.eventCursor == value.stateVersion + 1

static func supported(observed: Dictionary) -> bool:
	var cap = observed.get("workshop")
	if observed.get("rulesVersion") != "r10" or not cap is Dictionary or cap.get("capability") != "workshop-v1" \
		or cap.get("version") != 1 or cap.get("buildReach") != 3.2 or cap.get("interactReach") != 1.6 \
		or cap.get("inventoryCapacity") != 12 or cap.get("chestCapacity") != 12 or cap.get("workbenchAccess") != "public" \
		or cap.get("chestAccess") != "owner" or not Canvas.valid_adoption(cap.get("adoption")) \
		or cap.adoption.worldInstanceId != observed.get("world", {}).get("instanceId") \
		or cap.adoption.stateVersion > observed.get("stateVersion", -1) or not same(cap.get("recipes"), RECIPES) \
		or not cap.get("workbenches") is Array or not cap.get("tools") is Array or not cap.get("chests") is Array \
		or not observed.get("entities") is Array:
		return false
	var benches: Array = []
	var chests: Array = []
	for entity in observed.entities:
		if not entity is Dictionary or half_size(str(entity.get("definitionId"))).is_zero_approx():
			return false
		if entity.definitionId in ["workbench", "wooden_chest"] and not valid_entity(entity):
			return false
		if entity.definitionId == "workbench":
			benches.append(entity)
		if entity.definitionId == "wooden_chest" and entity.ownerActorId == observed.get("self", {}).get("actorId"):
			chests.append(entity)
	if not same(benches, cap.workbenches) or chests.size() != cap.chests.size():
		return false
	var seen: Array = []
	for tool in cap.tools:
		if not valid_tool(tool) or tool.ownerActorId != observed.self.actorId or tool.stateVersion > observed.stateVersion or tool.toolId in seen \
			or not benches.any(func(e): return e.entityId == tool.workbenchId):
			return false
		seen.append(tool.toolId)
	for i in chests.size():
		var chest = cap.chests[i]
		if not chest is Dictionary or chest.size() != 3 or not same(chests[i], chest.get("entity")) \
			or chest.get("capacity") != 12 or not Notes.whole(chest.get("storedWood")) or chest.storedWood > 12:
			return false
	return true

static func valid_action(a: Dictionary) -> bool:
	if not is_action(a.get("type")) or a.get("capabilityVersion") != 1:
		return false
	match a.type:
		"build_workshop":
			return a.size() == 5 and a.get("recipeId") in ["workbench.v1", "wooden_chest.v1"] and Notes.point(a.get("at")) \
				and a.has("toolId") and (a.toolId == null if a.recipeId == "workbench.v1" else Notes.id(a.toolId, "t"))
		"craft_tool":
			return a.size() == 4 and Notes.id(a.get("entityId"), "e") and a.get("recipeId") == "wooden_mallet.v1"
		_:
			return a.size() == 4 and Notes.id(a.get("entityId"), "e") and Notes.whole(a.get("quantity")) and a.quantity >= 1 and a.quantity <= 12

static func capture(observed: Dictionary, action: Dictionary) -> Dictionary:
	if not supported(observed) or not valid_action(action):
		return {}
	var cap: Dictionary = observed.workshop
	var before := {"position": observed.self.position.duplicate(), "inventoryWood": observed.self.inventory.wood,
		"workshopActorId": observed.identity.actorId, "workshopOperatorId": observed.identity.operatorId,
		"workshopAdoption": cap.adoption.duplicate(true), "entity": null, "tool": null, "storedWood": null,
		"entityIds": observed.entities.map(func(e): return e.entityId), "toolIds": cap.tools.map(func(t): return t.toolId)}
	for e in observed.entities:
		if e.entityId == action.get("entityId"):
			before.entity = e.duplicate(true)
	for tool in cap.tools:
		if tool.toolId == action.get("toolId"):
			before.tool = tool.duplicate(true)
	for chest in cap.chests:
		if chest.entity.entityId == action.get("entityId"):
			before.storedWood = chest.storedWood
	return before if valid_before(action, before) else {}

static func valid_before(a: Dictionary, b: Variant) -> bool:
	if not valid_action(a) or not b is Dictionary or not Notes.point(b.get("position")) or not Notes.whole(b.get("inventoryWood")) \
		or b.inventoryWood > 12 or b.get("workshopActorId") not in Notes.ROSTER or b.get("workshopOperatorId") != Notes.ROSTER[b.workshopActorId] \
		or not Canvas.valid_adoption(b.get("workshopAdoption")) or not b.get("entityIds") is Array or not b.get("toolIds") is Array \
		or not b.has("entity") or not b.has("tool") or not b.has("storedWood"):
		return false
	if a.type == "build_workshop":
		return b.entity == null and b.storedWood == null and b.inventoryWood >= 3 \
			and (b.tool == null if a.recipeId == "workbench.v1" else valid_tool(b.tool) and b.tool.toolId == a.toolId and b.tool.ownerActorId == b.workshopActorId)
	if not valid_entity(b.entity) or b.entity.entityId != a.entityId or b.tool != null:
		return false
	if a.type == "craft_tool":
		return b.entity.definitionId == "workbench" and b.storedWood == null and b.inventoryWood >= 1
	if b.entity.definitionId != "wooden_chest" or b.entity.ownerActorId != b.workshopActorId or not Notes.whole(b.storedWood) or b.storedWood > 12:
		return false
	return (b.inventoryWood >= a.quantity and b.storedWood + a.quantity <= 12) if a.type == "deposit_wood" \
		else (b.storedWood >= a.quantity and b.inventoryWood + a.quantity <= 12)

static func valid_detail(d: Variant) -> bool:
	if not d is Dictionary or d.size() != DETAIL_FIELDS.size():
		return false
	for field in DETAIL_FIELDS:
		if not d.has(field):
			return false
	if d.capabilityVersion != 1 or d.authorActorId not in Notes.ROSTER or d.operatorId != Notes.ROSTER[d.authorActorId] \
		or not d.commandId is String or d.commandId.is_empty() or not d.action is Dictionary or not valid_action(d.action) \
		or not valid_entity(d.entity) or not Notes.whole(d.quantity) or d.quantity < 1 or d.quantity > 12 \
		or not Notes.whole(d.inventoryWoodBefore) or d.inventoryWoodBefore > 12 or not Notes.whole(d.inventoryWood) or d.inventoryWood > 12 \
		or not Notes.point(d.position) or not Notes.whole(d.stateVersion) or d.stateVersion < 1 \
		or not Notes.whole(d.eventCursor) or d.eventCursor != d.stateVersion + 1 or not d.completedAtUtc is String or d.completedAtUtc.is_empty():
		return false
	var a: Dictionary = d.action
	var delta: int = int(d.quantity) if a.type == "withdraw_wood" else -int(d.quantity)
	if d.inventoryWood != d.inventoryWoodBefore + delta:
		return false
	if a.type == "build_workshop":
		if d.quantity != 3 or a.recipeId != d.entity.definitionId + ".v1" or not same(a.at, d.entity.position) or d.entity.ownerActorId != d.authorActorId:
			return false
		return (d.tool == null and d.storedWoodBefore == null and d.storedWood == null) if a.recipeId == "workbench.v1" \
			else (valid_tool(d.tool) and d.tool.toolId == a.toolId and d.tool.ownerActorId == d.authorActorId and d.storedWoodBefore == 0 and d.storedWood == 0)
	if a.entityId != d.entity.entityId:
		return false
	if a.type == "craft_tool":
		return d.entity.definitionId == "workbench" and d.quantity == 1 and valid_tool(d.tool) and d.tool.ownerActorId == d.authorActorId \
			and d.tool.commandId == d.commandId and d.tool.workbenchId == a.entityId and d.tool.stateVersion == d.stateVersion \
			and d.tool.eventCursor == d.eventCursor and d.storedWoodBefore == null and d.storedWood == null
	return d.entity.definitionId == "wooden_chest" and d.entity.ownerActorId == d.authorActorId and d.tool == null \
		and d.quantity == a.quantity and Notes.whole(d.storedWoodBefore) and d.storedWoodBefore <= 12 \
		and Notes.whole(d.storedWood) and d.storedWood <= 12 and d.storedWood == d.storedWoodBefore - delta

static func result(data: Dictionary, command: Dictionary, before: Dictionary) -> bool:
	var d = data.get("result", {}).get("workshopAction")
	if not valid_before(command.action, before) or not valid_detail(d) or not same(d.action, command.action) \
		or data.get("result", {}).get("action") != command.action.type or d.authorActorId != before.workshopActorId \
		or d.operatorId != before.workshopOperatorId or data.get("identity", {}).get("actorId") != d.authorActorId \
		or data.get("identity", {}).get("operatorId") != d.operatorId or d.commandId != command.commandId \
		or d.stateVersion != data.get("stateVersion") or d.eventCursor != data.get("eventCursor") \
		or d.stateVersion <= before.workshopAdoption.stateVersion or not same(d.position, before.position) \
		or d.inventoryWoodBefore != before.inventoryWood:
		return false
	if command.action.type == "build_workshop":
		return d.entity.entityId not in before.entityIds and same(d.tool, before.tool) and Notes.distance(before.position, d.entity.position) <= 3.200001
	if not same(d.entity, before.entity) or Notes.distance(before.position, d.entity.position) > 1.600001:
		return false
	return d.tool.toolId not in before.toolIds if command.action.type == "craft_tool" else d.storedWoodBefore == before.storedWood

static func event(value: Variant, data: Dictionary) -> bool:
	return value is Dictionary and value.get("type") == "workshopActionCompleted" and value.get("actorId") == data.identity.actorId \
		and value.get("commandId") == data.commandId and value.get("seq") == data.eventCursor and value.get("stateVersion") == data.stateVersion \
		and same(value.get("workshopAction"), data.result.workshopAction)

static func detail(value: Dictionary, data: Dictionary) -> bool:
	return value.get("schemaVersion") == 1 and value.get("rulesVersion") == "r10" and value.get("error") == null \
		and same(value.get("workshopAction"), data.result.workshopAction) and Notes.whole(value.get("stateVersion")) \
		and value.stateVersion >= data.stateVersion and value.get("identity", {}).get("actorId") == data.identity.actorId

static func retry_supported(observed: Dictionary, before: Dictionary) -> bool:
	if not supported(observed) or not same(observed.workshop.adoption, before.workshopAdoption):
		return false
	if before.entity != null and not observed.entities.any(func(e): return same(e, before.entity)):
		return false
	return before.tool == null or observed.workshop.tools.any(func(t): return same(t, before.tool))
