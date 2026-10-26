extends RefCounted
## An immutable original edit is distinct from the later current picture.
const Notes = preload("res://entity_note_evidence.gd")
const COLORS = ["blank", "leaf", "river", "sun", "rose", "ink"]
const HEX = ["#F4F0E6", "#42745B", "#477FA3", "#E4B858", "#C86A70", "#37444D"]
const EDIT_FIELDS = ["entityId", "capabilityVersion", "authorActorId", "operatorId", "commandId", "baseRevision", "revision", "patch", "stateVersion", "eventCursor", "paintedAtUtc", "position", "inventoryWood"]

static func valid_target(value: Variant) -> bool:
	return value is Dictionary and Notes.id(value.get("entityId"), "e") and value.get("definitionId") == "platform" \
		and value.get("definitionVersion") == 1 and value.get("rulesVersion") == "r10" and value.get("embodiedWood") == 3 \
		and value.get("ownerActorId") in Notes.ROSTER and Notes.point(value.get("position"))

static func same_target(a: Dictionary, b: Dictionary) -> bool:
	if not valid_target(a) or not valid_target(b):
		return false
	for field in ["entityId", "definitionId", "definitionVersion", "rulesVersion", "ownerActorId", "embodiedWood"]:
		if a[field] != b[field]:
			return false
	return Notes.distance(a.position, b.position) <= 0.000001

static func valid_patch(value: Variant) -> bool:
	if not value is Array or value.is_empty() or value.size() > 8:
		return false
	var previous := -1
	for cell in value:
		if not cell is Dictionary or cell.size() != 3 or not Notes.whole(cell.get("x")) or not Notes.whole(cell.get("y")) \
			or cell.x >= 5 or cell.y >= 5 or cell.get("color") not in COLORS:
			return false
		var index := int(cell.y) * 5 + int(cell.x)
		if index <= previous:
			return false
		previous = index
	return true

static func same_patch(a: Array, b: Array) -> bool:
	if not valid_patch(a) or not valid_patch(b) or a.size() != b.size():
		return false
	for i in a.size():
		for field in ["x", "y", "color"]:
			if a[i][field] != b[i][field]:
				return false
	return true

static func valid_cells(value: Variant) -> bool:
	if not value is Array or value.size() != 25:
		return false
	for i in 25:
		var cell = value[i]
		if not cell is Dictionary or not Notes.whole(cell.get("x")) or not Notes.whole(cell.get("y")) \
			or cell.x != i % 5 or cell.y != i / 5 or cell.get("color") not in COLORS \
			or not cell.has("authorActorId") or not cell.has("commandId") or not cell.has("stateVersion"):
			return false
		if cell.authorActorId == null:
			if cell.color != "blank" or cell.commandId != null or cell.stateVersion != null:
				return false
		elif cell.authorActorId not in Notes.ROSTER or not cell.commandId is String or cell.commandId.is_empty() \
			or not Notes.whole(cell.stateVersion) or cell.stateVersion < 1:
			return false
	return true

static func valid_edit(edit: Variant) -> bool:
	if not edit is Dictionary:
		return false
	for field in EDIT_FIELDS:
		if not edit.has(field):
			return false
	return Notes.id(edit.entityId, "e") and Notes.whole(edit.capabilityVersion) and edit.capabilityVersion == 1 \
		and edit.authorActorId in Notes.ROSTER and edit.operatorId == Notes.ROSTER[edit.authorActorId] \
		and edit.commandId is String and not edit.commandId.is_empty() and Notes.whole(edit.baseRevision) \
		and Notes.whole(edit.revision) and edit.revision == edit.baseRevision + 1 and valid_patch(edit.patch) \
		and Notes.whole(edit.stateVersion) and edit.stateVersion > 0 and Notes.whole(edit.eventCursor) \
		and edit.eventCursor == edit.stateVersion + 1 and edit.paintedAtUtc is String and not edit.paintedAtUtc.is_empty() \
		and Notes.point(edit.position) and Notes.whole(edit.inventoryWood) and edit.inventoryWood <= 12

static func same_edit(a: Dictionary, b: Dictionary) -> bool:
	if not valid_edit(a) or not valid_edit(b):
		return false
	for field in EDIT_FIELDS:
		if field == "position":
			if Notes.distance(a.position, b.position) > 0.000001:
				return false
		elif field == "patch":
			if not same_patch(a.patch, b.patch):
				return false
		elif a[field] != b[field]:
			return false
	return true

static func valid_adoption(value: Variant) -> bool:
	return value is Dictionary and value.size() == 3 and value.get("worldInstanceId") is String \
		and value.worldInstanceId.begins_with("w_") and Notes.whole(value.get("stateVersion")) and value.stateVersion > 0 \
		and Notes.whole(value.get("eventCursor")) and value.eventCursor == value.stateVersion + 1

static func supported(observed: Dictionary) -> bool:
	var cap = observed.get("entityCanvas")
	if observed.get("rulesVersion") != "r10" or not cap is Dictionary or cap.get("capability") != "entity-canvas-v1" \
		or not Notes.whole(cap.get("version")) or cap.version != 1 or cap.get("width") != 5 or cap.get("height") != 5 \
		or cap.get("reach") != 1.6 or cap.get("maxPatchCells") != 8 or cap.get("paintRule") != "unowned-or-author-v1" \
		or not valid_target(cap.get("target")) or not valid_adoption(cap.get("adoption")) \
		or cap.adoption.worldInstanceId != observed.get("world", {}).get("instanceId") \
		or cap.adoption.stateVersion > observed.get("stateVersion", -1) or not valid_cells(cap.get("cells")) \
		or not Notes.whole(cap.get("revision")) or not Notes.whole(cap.get("editCount")) or cap.editCount != cap.revision \
		or not cap.get("recentEdits") is Array or cap.recentEdits.size() != mini(int(cap.editCount), 50) \
		or not cap.get("palette") is Array or cap.palette.size() != 6 or not observed.get("entities") is Array:
		return false
	if not observed.entities.any(func(entity): return entity is Dictionary and same_target(entity, cap.target)):
		return false
	for i in 6:
		if not cap.palette[i] is Dictionary or cap.palette[i].get("id") != COLORS[i] or cap.palette[i].get("hex") != HEX[i] \
			or not cap.palette[i].get("label") is String:
			return false
	for i in cap.recentEdits.size():
		var edit = cap.recentEdits[i]
		if not valid_edit(edit) or edit.entityId != cap.target.entityId \
			or edit.revision != cap.revision - cap.recentEdits.size() + i + 1 or edit.stateVersion > observed.stateVersion:
			return false
	for cell in cap.cells:
		if cell.authorActorId != null and (cell.stateVersion <= cap.adoption.stateVersion or cell.stateVersion > observed.stateVersion):
			return false
	return true

static func capture(observed: Dictionary, action: Dictionary) -> Dictionary:
	if not supported(observed):
		return {}
	var cap: Dictionary = observed.entityCanvas
	var before := {"position": observed.self.position.duplicate(), "inventoryWood": observed.self.inventory.wood,
		"canvasActorId": observed.identity.actorId, "canvasOperatorId": observed.identity.operatorId, "canvasVersion": 1,
		"canvasTarget": cap.target.duplicate(true), "canvasAdoption": cap.adoption.duplicate(true),
		"canvasRevision": cap.revision, "canvasPatch": action.get("patch"), "canvasCells": cap.cells.duplicate(true)}
	return before if valid_before(action, before) else {}

static func valid_before(action: Dictionary, before: Variant) -> bool:
	if not before is Dictionary or action.size() != 5 or action.get("type") != "paint_entity_canvas" \
		or not Notes.point(before.get("position")) or not Notes.whole(before.get("inventoryWood")) or before.inventoryWood > 12 \
		or before.get("canvasActorId") not in Notes.ROSTER or before.get("canvasOperatorId") != Notes.ROSTER[before.canvasActorId] \
		or before.get("canvasVersion") != 1 or not valid_target(before.get("canvasTarget")) or not valid_adoption(before.get("canvasAdoption")) \
		or action.get("entityId") != before.canvasTarget.entityId or not Notes.whole(action.get("capabilityVersion")) or action.capabilityVersion != 1 \
		or not Notes.whole(action.get("expectedCanvasRevision")) or not Notes.whole(before.get("canvasRevision")) \
		or action.expectedCanvasRevision != before.canvasRevision or not valid_patch(action.get("patch")) \
		or not before.get("canvasPatch") is Array or not same_patch(action.patch, before.canvasPatch) or not valid_cells(before.get("canvasCells")):
		return false
	for change in action.patch:
		var cell: Dictionary = before.canvasCells[int(change.y) * 5 + int(change.x)]
		if cell.color == change.color or cell.authorActorId != null and cell.authorActorId != before.canvasActorId:
			return false
	return true

static func result(data: Dictionary, command: Dictionary, before: Dictionary) -> bool:
	var edit = data.get("result")
	return valid_before(command.action, before) and valid_edit(edit) and edit.get("action") == "paint_entity_canvas" \
		and data.get("identity", {}).get("actorId") == before.canvasActorId and data.get("identity", {}).get("operatorId") == before.canvasOperatorId \
		and edit.authorActorId == before.canvasActorId and edit.operatorId == before.canvasOperatorId \
		and edit.commandId == command.commandId and edit.entityId == command.action.entityId and edit.baseRevision == command.action.expectedCanvasRevision \
		and same_patch(edit.patch, command.action.patch) and edit.stateVersion == data.get("stateVersion") and edit.eventCursor == data.get("eventCursor") \
		and Notes.distance(edit.position, before.position) <= 0.000001 and edit.inventoryWood == before.inventoryWood \
		and Notes.distance(before.position, before.canvasTarget.position) <= 1.600001

static func event(value: Variant, data: Dictionary) -> bool:
	return value is Dictionary and value.get("type") == "entityCanvasPainted" and value.get("actorId") == data.result.authorActorId \
		and value.get("seq") == data.eventCursor and same_edit(value, data.result)

static func detail(value: Dictionary, data: Dictionary) -> bool:
	return value.get("schemaVersion") == 1 and value.get("rulesVersion") == "r10" and value.get("error") == null \
		and value.get("edit") is Dictionary and same_edit(value.edit, data.result) and Notes.whole(value.get("stateVersion")) \
		and value.stateVersion >= data.stateVersion and value.get("identity", {}).get("actorId") == data.identity.actorId
