extends RefCounted
## The immutable note, original receipt and original event must agree.
const ROSTER = {"a1": "local-operator", "a1_alias": "local-operator", "a2": "declared-late", "a3": "declared-third"}
const NOTE_FIELDS = ["noteId", "entityId", "authorActorId", "operatorId", "commandId", "text", "replyToNoteId", "capabilityVersion", "stateVersion", "eventCursor", "sharedAtUtc", "position", "inventoryWood"]

static func whole(value: Variant) -> bool:
	return typeof(value) in [TYPE_INT, TYPE_FLOAT] and is_finite(float(value)) and value >= 0 \
		and value <= 9007199254740991 and value == floor(float(value))

static func point(value: Variant) -> bool:
	return value is Array and value.size() == 2 and typeof(value[0]) in [TYPE_INT, TYPE_FLOAT] \
		and typeof(value[1]) in [TYPE_INT, TYPE_FLOAT] and is_finite(float(value[0])) and is_finite(float(value[1]))

static func distance(a: Array, b: Array) -> float:
	return Vector2(a[0], a[1]).distance_to(Vector2(b[0], b[1]))

static func id(value: Variant, prefix: String) -> bool:
	if not value is String or value.length() != 33 or not value.begins_with(prefix):
		return false
	for character in value.substr(1):
		if not "0123456789abcdef".contains(character):
			return false
	return true

static func valid_text(value: Variant) -> bool:
	if not value is String or value.length() < 1 or value.length() > 160:
		return false
	var content := false
	for index in value.length():
		var code: int = value.unicode_at(index)
		if code < 32 or (code >= 127 and code <= 159) or (code >= 0xd800 and code <= 0xdfff):
			return false
		var whitespace: bool = code in [32, 0xa0, 0x1680, 0x2028, 0x2029, 0x202f, 0x205f, 0x3000] or (code >= 0x2000 and code <= 0x200a)
		content = content or not whitespace
	return content

static func valid_target(target: Variant) -> bool:
	return target is Dictionary and id(target.get("entityId"), "e") and target.get("definitionId") == "bridge" \
		and target.get("definitionVersion") == 1 and target.get("rulesVersion") == "r10" and target.get("embodiedWood") == 6 \
		and target.get("ownerActorId") in ROSTER and point(target.get("position"))

static func same_target(left: Dictionary, right: Dictionary) -> bool:
	if not valid_target(left) or not valid_target(right):
		return false
	for field in ["entityId", "definitionId", "definitionVersion", "rulesVersion", "embodiedWood", "ownerActorId"]:
		if left[field] != right[field]:
			return false
	return distance(left.position, right.position) <= 0.000001

static func valid_note(note: Variant) -> bool:
	if not note is Dictionary:
		return false
	for field in NOTE_FIELDS:
		if not note.has(field):
			return false
	return id(note.noteId, "n") and id(note.entityId, "e") and note.authorActorId in ROSTER \
		and note.operatorId == ROSTER[note.authorActorId] and note.commandId is String and not note.commandId.is_empty() \
		and valid_text(note.text) and (note.replyToNoteId == null or id(note.replyToNoteId, "n")) \
		and note.capabilityVersion == 1 and whole(note.stateVersion) and whole(note.eventCursor) \
		and note.stateVersion > 0 and note.eventCursor > 0 and note.sharedAtUtc is String and not note.sharedAtUtc.is_empty() \
		and point(note.position) and whole(note.inventoryWood) and note.inventoryWood <= 12

static func same_note(left: Dictionary, right: Dictionary) -> bool:
	if not valid_note(left) or not valid_note(right):
		return false
	for field in NOTE_FIELDS:
		if field == "position":
			if distance(left.position, right.position) > 0.000001:
				return false
		elif left[field] != right[field]:
			return false
	return true

static func supported(observed: Dictionary) -> bool:
	var data = observed.get("entityNotes")
	if observed.get("rulesVersion") != "r10" or observed.get("world", {}).get("scenarioId") != "wilderness-material-access-v1" \
		or not data is Dictionary or data.get("capability") != "entity-notes-v1" or data.get("version") != 1 \
		or data.get("reach") != 1.6 or data.get("maxTextScalars") != 160 or data.get("maxPerOperator") != 2 or data.get("maxTotal") != 6 \
		or not valid_target(data.get("target")) or not whole(data.get("selfCount")) or not whole(data.get("totalCount")) \
		or data.selfCount > 2 or data.totalCount > 6 or not data.get("notes") is Array or data.notes.size() != data.totalCount:
		return false
	if not observed.get("entities") is Array or not observed.entities.any(func(entity):
		return entity is Dictionary and same_target(entity, data.target)):
		return false
	var counts: Dictionary = {}
	var ids: Dictionary = {}
	var previous := 0
	for note in data.notes:
		if not valid_note(note) or note.entityId != data.target.entityId or ids.has(note.noteId) or note.eventCursor <= previous:
			return false
		if note.replyToNoteId != null and not ids.has(note.replyToNoteId):
			return false
		ids[note.noteId] = true
		counts[note.operatorId] = counts.get(note.operatorId, 0) + 1
		if counts[note.operatorId] > 2:
			return false
		previous = int(note.eventCursor)
	return data.selfCount == counts.get(observed.get("identity", {}).get("operatorId"), 0)

static func capture(observed: Dictionary, action: Dictionary) -> Dictionary:
	if not supported(observed) or action.get("entityId") != observed.entityNotes.target.entityId:
		return {}
	var reference = null
	for note in observed.entityNotes.notes:
		if note.noteId == action.get("replyToNoteId"):
			reference = note.duplicate(true)
	var before = {"position": observed.self.position.duplicate(), "inventoryWood": observed.self.inventory.wood,
		"noteActorId": observed.identity.actorId, "noteOperatorId": observed.identity.operatorId, "noteCapabilityVersion": 1,
		"noteTarget": observed.entityNotes.target.duplicate(true), "noteText": action.get("text"),
		"noteReplyToId": action.get("replyToNoteId"), "noteReference": reference}
	return before if valid_before(action, before) else {}

static func valid_before(action: Dictionary, before: Variant) -> bool:
	if not before is Dictionary or action.size() != 4 or action.get("type") != "append_entity_note" \
		or not point(before.get("position")) or not whole(before.get("inventoryWood")) or before.inventoryWood > 12 \
		or before.get("noteActorId") not in ROSTER or before.get("noteOperatorId") != ROSTER[before.noteActorId] \
		or before.get("noteCapabilityVersion") != 1 or not valid_target(before.get("noteTarget")) \
		or action.get("entityId") != before.noteTarget.entityId or not valid_text(action.get("text")) \
		or action.text != before.get("noteText") or not action.has("replyToNoteId") or not before.has("noteReplyToId") \
		or action.replyToNoteId != before.noteReplyToId or not before.has("noteReference"):
		return false
	if action.replyToNoteId == null:
		return before.noteReference == null
	return id(action.replyToNoteId, "n") and valid_note(before.noteReference) \
		and before.noteReference.noteId == action.replyToNoteId and before.noteReference.entityId == action.entityId

static func result(data: Dictionary, command: Dictionary, before: Dictionary) -> bool:
	var actual = data.get("result")
	return valid_before(command.action, before) and valid_note(actual) and actual.get("action") == "append_entity_note" \
		and data.get("identity", {}).get("actorId") == before.noteActorId and data.get("identity", {}).get("operatorId") == before.noteOperatorId \
		and actual.authorActorId == before.noteActorId and actual.operatorId == before.noteOperatorId \
		and actual.commandId == command.commandId and actual.entityId == command.action.entityId \
		and actual.text == command.action.text and actual.replyToNoteId == command.action.replyToNoteId \
		and actual.stateVersion == data.get("stateVersion") and actual.eventCursor == data.get("eventCursor") \
		and distance(actual.position, before.position) <= 0.000001 and actual.inventoryWood == before.inventoryWood \
		and distance(before.position, before.noteTarget.position) <= 1.600001

static func event(value: Variant, data: Dictionary) -> bool:
	return value is Dictionary and value.get("type") == "entityNoteAppended" and value.get("actorId") == data.result.authorActorId \
		and value.get("seq") == data.eventCursor and same_note(value, data.result)

static func confirmed(observed: Dictionary, data: Dictionary, before: Dictionary) -> bool:
	if not supported(observed) or observed.get("stateVersion", -1) < data.stateVersion \
		or observed.get("identity", {}).get("actorId") != before.noteActorId or not same_target(observed.entityNotes.target, before.noteTarget):
		return false
	for note in observed.entityNotes.notes:
		if note.noteId == data.result.noteId:
			return same_note(note, data.result)
	return false
