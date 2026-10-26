extends RefCounted
## Frozen pre-submit facts for the opt-in actor-state protocol.
const MODE = "actor-state-v1"

static func continuous_world(observed: Dictionary) -> bool:
	return {"r8": "wilderness-continuous-v1", "r9": "wilderness-cooperation-v1", "r10": "wilderness-material-access-v1"}.get(observed.get("rulesVersion"), "") \
		== observed.get("world", {}).get("scenarioId", "?")

static func transfer_supported(observed: Dictionary) -> bool:
	return observed.get("rulesVersion") in ["r9", "r10"] and continuous_world(observed) \
		and observed.get("materialTransfer") == {"version": 1, "resource": "wood", "maxQuantity": 12, "reach": 1.6, "recipientConfirmation": false}

static func material_supported(observed: Dictionary) -> bool:
	var source = observed.get("materialAccess")
	if observed.get("rulesVersion") != "r10" or not continuous_world(observed) or not source is Dictionary:
		return false
	if source.get("version") != 1 or source.get("sourceId") != "wood-source-east" \
		or source.get("position") != [28, 10] or source.get("buildExclusion") != [27, 9, 29, 11] \
		or source.get("inputBudget") != 12 or source.get("capacity") != 6 or source.get("reservationQuantity") != 3 \
		or source.get("leaseMs") != 60000 or source.get("productionIntervalMs") != 10000 or not source.get("active") is bool:
		return false
	for field in ["serviceMs", "stockWood", "freeWood", "generatedWood"]:
		if not whole(source.get(field)):
			return false
	if not source.get("queue") is Array or not source.get("recentReservations") is Array:
		return false
	for reservation in source.queue + source.recentReservations:
		if not valid_reservation(reservation):
			return false
	return source.stockWood <= 6 and source.freeWood <= source.stockWood and source.stockWood <= source.generatedWood \
		and source.generatedWood <= 12 and source.get("queue") is Array and source.get("recentReservations") is Array \
		and source.has("currentReservation") and (source.currentReservation == null or valid_reservation(source.currentReservation))

static func valid_reservation(value: Variant) -> bool:
	if not value is Dictionary:
		return false
	for field in ["reservationId", "actorId", "operatorId", "requestCommandId"]:
		if not value.get(field) is String or value[field].is_empty():
			return false
	if not whole(value.get("queueSequence")) or value.queueSequence < 1 or not whole(value.get("requestedAtMs")) \
		or not whole(value.get("remaining")) or value.remaining > 3 or value.get("status") not in ["queued", "active", "completed", "cancelled", "expired"]:
		return false
	if value.get("status") == "queued":
		return value.remaining == 3 and value.get("grantedAtMs") == null and value.get("expiresAtMs") == null
	if value.get("status") == "active":
		return value.remaining > 0 and whole(value.get("grantedAtMs")) and whole(value.get("expiresAtMs")) and value.expiresAtMs == value.grantedAtMs + 60000
	return true

static func supported(observed: Dictionary) -> bool:
	var capability = observed.get("commandConcurrency")
	return continuous_world(observed) and observed.get("world", {}).get("instanceId") is String and capability is Dictionary \
		and capability.get("version") == 1 and capability.get("supportedModes") is Array \
		and MODE in capability.supportedModes

static func whole(value: Variant) -> bool:
	return typeof(value) in [TYPE_INT, TYPE_FLOAT] and is_finite(float(value)) \
		and value >= 0 and value <= 9007199254740991 and value == floor(float(value))

static func point(value: Variant) -> bool:
	return value is Array and value.size() == 2 \
		and typeof(value[0]) in [TYPE_INT, TYPE_FLOAT] and typeof(value[1]) in [TYPE_INT, TYPE_FLOAT] \
		and is_finite(float(value[0])) and is_finite(float(value[1]))

static func capture(observed: Dictionary, action: Dictionary) -> Dictionary:
	var before = {"position": observed.get("self", {}).get("position"),
		"inventoryWood": observed.get("self", {}).get("inventory", {}).get("wood")}
	match action.get("type"):
		"walk":
			before.maxStepDistance = observed.get("movement", {}).get("maxStepDistance")
		"gather":
			for node in observed.get("resourceNodes", []):
				if node.get("nodeId") == action.get("nodeId"):
					before.nodePosition = node.get("position")
					before.remainingWood = node.get("remainingWood")
		"build":
			for recipe in observed.get("recipes", []):
				if recipe.get("id") == action.get("recipeId"):
					before.woodCost = recipe.get("woodCost")
		"transfer":
			if not transfer_supported(observed):
				return {}
			before.senderActorId = observed.self.actorId
		"reserve_material", "cancel_reservation", "harvest_material":
			if not material_supported(observed):
				return {}
			before.materialActorId = observed.self.actorId
			before.sourceId = observed.materialAccess.sourceId
			before.serviceMs = observed.materialAccess.serviceMs
			if action.type != "reserve_material":
				var reservation = observed.materialAccess.currentReservation
				if not reservation is Dictionary or reservation.get("actorId") != observed.self.actorId \
					or reservation.get("reservationId") != action.get("reservationId"):
					return {}
				before.reservationId = reservation.reservationId
				before.reservationStatus = reservation.get("status")
				before.remaining = reservation.get("remaining")
				before.expiresAtMs = reservation.get("expiresAtMs")
	return before if valid_before(action, before) else {}

static func valid_before(action: Dictionary, before: Variant) -> bool:
	if not before is Dictionary or not point(before.get("position")) or not whole(before.get("inventoryWood")) or before.inventoryWood > 12:
		return false
	match action.get("type"):
		"walk":
			return point(action.get("to")) and before.get("maxStepDistance") == 0.6
		"gather":
			return action.get("nodeId") is String and point(before.get("nodePosition")) \
				and whole(before.get("remainingWood")) and before.remainingWood > 0 and before.remainingWood <= 3
		"build":
			var cost = {"platform.v1": 3, "bridge.v1": 6}.get(action.get("recipeId"), -1)
			return point(action.get("at")) and cost > 0 and before.get("woodCost") == cost
		"transfer":
			return action.size() == 4 and action.get("resource") == "wood" \
				and action.get("recipientActorId") is String and not action.recipientActorId.is_empty() \
				and before.get("senderActorId") is String and not before.senderActorId.is_empty() \
				and action.recipientActorId != before.senderActorId \
				and whole(action.get("quantity")) and action.quantity >= 1 and action.quantity <= 12 \
				and before.inventoryWood >= action.quantity
		"reserve_material", "cancel_reservation", "harvest_material":
			if action.size() != 2 or before.get("sourceId") != "wood-source-east" \
				or not before.get("materialActorId") is String or before.materialActorId.is_empty() or not whole(before.get("serviceMs")):
				return false
			if action.type == "reserve_material":
				return action.get("sourceId") == before.sourceId
			if not action.get("reservationId") is String or action.reservationId.is_empty() \
				or before.get("reservationId") != action.reservationId or not whole(before.get("remaining")) \
				or before.remaining < 1 or before.remaining > 3:
				return false
			if action.type == "cancel_reservation" and before.get("reservationStatus") == "queued":
				return before.remaining == 3 and before.get("expiresAtMs") == null
			return before.get("reservationStatus") == "active" and whole(before.get("expiresAtMs")) \
				and before.expiresAtMs > before.serviceMs and (action.type != "harvest_material" or before.inventoryWood < 12)
	return false

static func execution(data: Dictionary, command: Dictionary, committed: bool) -> bool:
	var basis = data.get("execution")
	if command.get("preconditionMode") != MODE or not basis is Dictionary \
		or basis.get("preconditionMode") != MODE or not whole(basis.get("observedStateVersion")) \
		or basis.observedStateVersion != command.get("expectedStateVersion") \
		or not whole(basis.get("appliedOnStateVersion")) or not whole(data.get("stateVersion")):
		return false
	var applied = basis.appliedOnStateVersion
	if committed:
		return data.stateVersion == applied + 1 and applied >= basis.observedStateVersion
	return data.stateVersion == applied and (applied >= basis.observedStateVersion \
		or data.get("error", {}).get("code") == "STATE_VERSION_AHEAD")

static func distance(left: Array, right: Array) -> float:
	return sqrt(pow(float(left[0]) - float(right[0]), 2) + pow(float(left[1]) - float(right[1]), 2))

static func result(data: Dictionary, command: Dictionary, before: Dictionary) -> bool:
	var actual = data.get("result")
	var action: Dictionary = command.action
	if not actual is Dictionary or actual.get("action") != action.get("type") or not valid_before(action, before):
		return false
	match action.type:
		"walk":
			if not point(actual.get("position")) or not actual.get("blocked") is bool \
				or distance(before.position, actual.position) > before.maxStepDistance + 0.000001:
				return false
			var dx = float(action.to[0]) - float(before.position[0])
			var dz = float(action.to[1]) - float(before.position[1])
			var squared = dx * dx + dz * dz
			var fraction = 0.0 if squared < 0.000000000000000001 else clampf( \
				((float(actual.position[0]) - float(before.position[0])) * dx \
				+ (float(actual.position[1]) - float(before.position[1])) * dz) / squared, 0, 1)
			return distance(actual.position, [before.position[0] + fraction * dx, before.position[1] + fraction * dz]) <= 0.000001
		"gather":
			return actual.get("nodeId") == action.nodeId and whole(actual.get("quantity")) and actual.quantity == 1 \
				and point(actual.get("position")) and distance(actual.position, before.nodePosition) <= 0.000001 \
				and whole(actual.get("inventoryWood")) and actual.inventoryWood == before.inventoryWood + 1 \
				and whole(actual.get("remainingWoodBefore")) and actual.remainingWoodBefore > 0 \
				and actual.remainingWoodBefore <= before.remainingWood and whole(actual.get("remainingWood")) \
				and actual.remainingWood == actual.remainingWoodBefore - 1
		"build":
			return actual.get("entityId") is String and not actual.entityId.is_empty() \
				and point(actual.get("position")) and distance(actual.position, action.at) <= 0.000001 \
				and whole(actual.get("inventoryWood")) and actual.inventoryWood == before.inventoryWood - before.woodCost
		"transfer":
			return actual.get("resource") == action.resource and whole(actual.get("quantity")) \
				and actual.quantity == action.quantity and actual.get("senderActorId") == before.senderActorId \
				and actual.senderActorId == data.get("identity", {}).get("actorId") \
				and actual.get("recipientActorId") == action.recipientActorId \
				and whole(actual.get("inventoryWood")) and actual.inventoryWood == before.inventoryWood - action.quantity
		"reserve_material":
			return command.get("rulesVersion") == "r10" and actual.get("sourceId") == before.sourceId \
				and actual.get("reservationId") is String and not actual.reservationId.is_empty() \
				and whole(actual.get("queueSequence")) and actual.queueSequence > 0 and actual.get("status") == "queued" \
				and whole(actual.get("requestedAtMs")) and actual.requestedAtMs >= before.serviceMs \
				and data.get("identity", {}).get("actorId") == before.materialActorId
		"cancel_reservation":
			return command.get("rulesVersion") == "r10" and actual.get("sourceId") == before.sourceId \
				and actual.get("reservationId") == action.reservationId and actual.get("status") == "cancelled" \
				and whole(actual.get("releasedQuantity")) and (actual.releasedQuantity == before.remaining \
					or (before.reservationStatus == "queued" and actual.releasedQuantity == 0)) \
				and data.get("identity", {}).get("actorId") == before.materialActorId
		"harvest_material":
			return command.get("rulesVersion") == "r10" and actual.get("sourceId") == before.sourceId \
				and actual.get("reservationId") == action.reservationId and whole(actual.get("quantity")) and actual.quantity == 1 \
				and actual.get("position") == [28, 10] and whole(actual.get("remainingBefore")) and actual.remainingBefore == before.remaining \
				and whole(actual.get("remaining")) and actual.remaining == before.remaining - 1 \
				and whole(actual.get("inventoryWoodBefore")) and actual.inventoryWoodBefore == before.inventoryWood \
				and whole(actual.get("inventoryWood")) and actual.inventoryWood == before.inventoryWood + 1 \
				and data.get("identity", {}).get("actorId") == before.materialActorId
	return false

static func reserved_event(event: Variant, data: Dictionary, command: Dictionary) -> bool:
	return event is Dictionary and event.get("type") == "materialReserved" and event.get("commandId") == command.commandId \
		and event.get("actorId") == data.get("identity", {}).get("actorId") and event.get("operatorId") == data.get("identity", {}).get("operatorId") \
		and whole(event.get("seq")) and event.seq == data.get("eventCursor") and event.get("stateVersion") == data.stateVersion \
		and event.get("sourceId") == data.result.sourceId and event.get("reservationId") == data.result.reservationId \
		and event.get("queueSequence") == data.result.queueSequence and event.get("serviceMs") == data.result.requestedAtMs

static func built_entity(observed: Dictionary, data: Dictionary, command: Dictionary, before: Dictionary, actor: String) -> bool:
	if observed.get("self", {}).get("actorId") != actor or observed.get("stateVersion", -1) < data.stateVersion:
		return false
	for entity in observed.get("entities", []):
		if entity.get("entityId") == data.result.entityId:
			return entity.get("ownerActorId") == actor and entity.get("rulesVersion") == command.get("rulesVersion") \
				and entity.get("definitionId") == command.action.recipeId.trim_suffix(".v1") \
				and entity.get("definitionVersion") == 1 and entity.get("embodiedWood") == before.woodCost \
				and point(entity.get("position")) and distance(entity.position, command.action.at) <= 0.000001
	return false
