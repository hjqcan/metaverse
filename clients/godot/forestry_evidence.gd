extends RefCounted
## Each original tree and queue authorization remains distinct across generations.
const Workshop = preload("res://workshop_evidence.gd")
const Notes = preload("res://entity_note_evidence.gd")
const TYPES = ["craft_forestry_tool", "reserve_forest", "cancel_forest_reservation", "collect_seed", "plant_tree", "harvest_tree"]
const PLOTS = {"forest-west-north": [7, 12], "forest-west-south": [7, 16], "forest-east-north": [21, 7], "forest-east-far": [29, 5]}
const POLICY = {"seedIntervalMs": 60000, "nurseryCapacity": 4, "preparationLeaseMs": 90000, "growthMs": 120000,
	"harvestLeaseMs": 60000, "woodPerTree": 3, "seedsPerHarvest": 1, "groupLimit": 1, "interactReach": 1.6}
const RECIPES = [{"id": "wooden_axe.v1", "definitionId": "wooden_axe", "woodCost": 2, "requiresWorkbench": true}]
const DETAIL_FIELDS = ["authorActorId", "operatorId", "commandId", "action", "position", "serviceMs", "stateVersion", "eventCursor",
	"completedAtUtc", "inventoryWoodBefore", "inventoryWood", "seedsBefore", "seeds", "nurseryStockBefore", "nurseryStock",
	"reservationBefore", "reservation", "plantBefore", "plant", "tool", "capabilityVersion"]

static func is_action(value: Variant) -> bool:
	return value in TYPES

static func same(a: Variant, b: Variant) -> bool:
	return Workshop.same(a, b)

static func uid(value: Variant, prefix: String) -> bool:
	if not value is String or value.length() != prefix.length() + 32 or not value.begins_with(prefix):
		return false
	for c in value.substr(prefix.length()):
		if not "0123456789abcdef".contains(c):
			return false
	return true

static func original_id(value: Variant) -> bool:
	if not value is String or value.length() < 1 or value.length() > 128:
		return false
	for c in value:
		if not "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_".contains(c):
			return false
	return true

static func adoption(value: Variant) -> bool:
	return value is Dictionary and value.size() == 5 and uid(value.get("worldInstanceId"), "w_") \
		and Notes.whole(value.get("adoptedServiceMs")) and Notes.whole(value.get("stateVersion")) and value.stateVersion > 0 \
		and Notes.whole(value.get("eventCursor")) and value.eventCursor == value.stateVersion + 1 and value.get("baseStorageVersion") == 13

static func reservation(value: Variant) -> bool:
	if not value is Dictionary or value.size() != 12 or not value.has_all(["reservationId", "actorId", "operatorId", "commandId", "requestedAtMs", "queueOrder", "status", "plotId", "plantId", "reservedSeed", "grantedAtMs", "expiresAtMs"]) or not uid(value.get("reservationId"), "fr") \
		or value.get("actorId") not in Notes.ROSTER or value.get("operatorId") != Notes.ROSTER[value.actorId] \
		or not original_id(value.get("commandId")) or not Notes.whole(value.get("requestedAtMs")) \
		or not Notes.whole(value.get("queueOrder")) or value.queueOrder < 1 or not Notes.whole(value.get("reservedSeed")) \
		or value.reservedSeed > 1 or value.get("status") not in ["queued", "preparing", "growing", "harvesting", "expired", "cancelled", "completed"]:
		return false
	if not value.has_all(["plotId", "plantId", "grantedAtMs", "expiresAtMs"]):
		return false
	if value.plotId != null and value.plotId not in PLOTS or value.plantId != null and not uid(value.plantId, "p"):
		return false
	if value.grantedAtMs != null and (not Notes.whole(value.grantedAtMs) or value.grantedAtMs < value.requestedAtMs):
		return false
	if value.expiresAtMs != null and (not Notes.whole(value.expiresAtMs) or value.grantedAtMs == null or value.expiresAtMs <= value.grantedAtMs):
		return false
	match value.status:
		"queued":
			return value.plotId == null and value.plantId == null and value.grantedAtMs == null and value.expiresAtMs == null and value.reservedSeed == 0
		"preparing":
			return value.plotId in PLOTS and value.plantId == null and value.grantedAtMs != null and value.expiresAtMs == value.grantedAtMs + 90000
		"growing":
			return value.plotId in PLOTS and value.plantId != null and value.grantedAtMs != null and value.expiresAtMs == null and value.reservedSeed == 0
		"harvesting":
			return value.plotId in PLOTS and value.plantId != null and value.grantedAtMs != null and value.expiresAtMs != null and value.reservedSeed == 0
		_:
			return value.reservedSeed == 0

static func plant(value: Variant) -> bool:
	if not value is Dictionary or value.size() != 16 or not value.has_all(["plantId", "plotId", "planterActorId", "operatorId", "reservationId", "commandId", "plantedAtMs", "maturesAtMs", "state", "standingWood", "stateVersion", "eventCursor", "matureEventCursor", "harvestActorId", "harvestCommandId", "harvestEventCursor"]) or not uid(value.get("plantId"), "p") or value.get("plotId") not in PLOTS \
		or value.get("planterActorId") not in Notes.ROSTER or value.get("operatorId") != Notes.ROSTER[value.planterActorId] \
		or not uid(value.get("reservationId"), "fr") or not original_id(value.get("commandId")) \
		or not Notes.whole(value.get("plantedAtMs")) or not Notes.whole(value.get("maturesAtMs")) or value.maturesAtMs != value.plantedAtMs + 120000 \
		or not Notes.whole(value.get("stateVersion")) or value.stateVersion < 1 or not Notes.whole(value.get("eventCursor")) \
		or value.eventCursor != value.stateVersion + 1 or not value.has_all(["matureEventCursor", "harvestActorId", "harvestCommandId", "harvestEventCursor"]):
		return false
	if value.state == "growing":
		return value.standingWood == 0 and value.matureEventCursor == null and value.harvestActorId == null and value.harvestCommandId == null and value.harvestEventCursor == null
	if value.state not in ["mature", "harvested"] or not Notes.whole(value.matureEventCursor) or value.matureEventCursor <= value.eventCursor:
		return false
	return (value.standingWood == 3 and value.harvestActorId == null and value.harvestCommandId == null and value.harvestEventCursor == null) if value.state == "mature" \
		else (value.standingWood == 0 and value.harvestActorId in Notes.ROSTER and original_id(value.harvestCommandId) and Notes.whole(value.harvestEventCursor) and value.harvestEventCursor > value.matureEventCursor)

static func tool(value: Variant) -> bool:
	return value is Dictionary and value.size() == 9 and value.has_all(["toolId", "ownerActorId", "workbenchId", "commandId", "stateVersion", "eventCursor", "definitionId", "definitionVersion", "embodiedWood"]) and uid(value.get("toolId"), "t") and value.get("ownerActorId") in Notes.ROSTER \
		and uid(value.get("workbenchId"), "e") and original_id(value.get("commandId")) and value.get("definitionId") == "wooden_axe" \
		and value.get("definitionVersion") == 1 and value.get("embodiedWood") == 2 and Notes.whole(value.get("stateVersion")) \
		and value.stateVersion > 0 and Notes.whole(value.get("eventCursor")) and value.eventCursor == value.stateVersion + 1

static func supported(o: Dictionary) -> bool:
	var f = o.get("forestry")
	if not Workshop.supported(o) or not f is Dictionary or f.get("capability") != "forestry-v1" or not Notes.whole(f.get("version")) or f.version != 1 \
		or not adoption(f.get("adoption")) or f.adoption.worldInstanceId != o.world.instanceId or f.adoption.stateVersion > o.stateVersion \
		or not same(f.get("policy"), POLICY) or not same(f.get("recipes"), RECIPES) or not f.get("nursery") is Dictionary \
		or not f.get("plots") is Array or f.plots.size() != 4 or not f.get("plants") is Array or not f.get("reservations") is Array \
		or not f.get("tools") is Array or not Notes.whole(f.get("seeds")):
		return false
	var n: Dictionary = f.nursery
	if n.get("sourceId") != "nursery-west" or not same(n.get("position"), [7, 6]) or n.get("radius") != 0.3 or not same(n.get("buildExclusion"), [5.5, 4.5, 8.5, 7.5]):
		return false
	for key in ["serviceMs", "nextProductionAtMs", "productionPeriod", "generatedSeeds", "stockSeeds", "reservedSeeds", "freeSeeds"]:
		if not Notes.whole(n.get(key)):
			return false
	if n.serviceMs != o.get("materialAccess", {}).get("serviceMs") or n.serviceMs < f.adoption.adoptedServiceMs \
		or n.nextProductionAtMs <= n.serviceMs or n.nextProductionAtMs != f.adoption.adoptedServiceMs + (n.productionPeriod + 1) * 60000 \
		or n.stockSeeds > 4 or n.reservedSeeds > n.stockSeeds or n.freeSeeds != n.stockSeeds - n.reservedSeeds:
		return false
	for i in f.plots.size():
		var id: String = PLOTS.keys()[i]
		var pos: Array = PLOTS[id]
		if not same(f.plots[i], {"plotId": id, "position": pos, "radius": 0.45, "buildExclusion": [pos[0]-1.5, pos[1]-1.5, pos[0]+1.5, pos[1]+1.5]}):
			return false
	var expected_obstacles := [{"id": "nursery-west", "kind": "forestry_nursery", "position": [7, 6], "radius": 0.3}]
	var ids: Array = []
	var occupied: Array = []
	for p in f.plants:
		if not plant(p) or p.state == "harvested" or p.plantId in ids or p.plotId in occupied or p.stateVersion > o.stateVersion \
			or (p.state == "growing" and p.maturesAtMs <= n.serviceMs):
			return false
		ids.append(p.plantId)
		occupied.append(p.plotId)
		expected_obstacles.append({"id": p.plantId, "kind": "forestry_tree", "position": PLOTS[p.plotId], "radius": 0.45})
	var actual: Array = []
	for obstacle in o.get("terrain", {}).get("obstacles", []):
		if obstacle.get("kind") in ["forestry_nursery", "forestry_tree"]:
			actual.append(obstacle)
		elif obstacle.get("kind") != "rock":
			return false
	if not same(actual, expected_obstacles):
		return false
	var groups: Array = []
	var reserved := 0
	var previous_order := 0
	for r in f.reservations:
		if not reservation(r) or r.status not in ["queued", "preparing", "growing", "harvesting"] or r.operatorId in groups or r.queueOrder <= previous_order \
			or r.requestedAtMs > n.serviceMs or (r.expiresAtMs != null and r.expiresAtMs <= n.serviceMs):
			return false
		groups.append(r.operatorId)
		previous_order = int(r.queueOrder)
		reserved += int(r.reservedSeed)
		if r.plantId != null and not f.plants.any(func(p): return p.plantId == r.plantId and p.plotId == r.plotId and p.state == ("growing" if r.status == "growing" else "mature")):
			return false
	if reserved != n.reservedSeeds:
		return false
	ids = []
	for item in f.tools:
		if not tool(item) or item.ownerActorId != o.self.actorId or item.toolId in ids or item.stateVersion > o.stateVersion \
			or not o.workshop.workbenches.any(func(b): return b.entityId == item.workbenchId):
			return false
		ids.append(item.toolId)
	return true

static func valid_action(a: Dictionary) -> bool:
	if not is_action(a.get("type")) or not Notes.whole(a.get("capabilityVersion")) or a.capabilityVersion != 1:
		return false
	match a.type:
		"craft_forestry_tool":
			return a.size() == 4 and uid(a.get("entityId"), "e") and a.get("recipeId") == "wooden_axe.v1"
		"reserve_forest":
			return a.size() == 2
		"cancel_forest_reservation":
			return a.size() == 3 and uid(a.get("reservationId"), "fr")
		"collect_seed":
			return a.size() == 4 and uid(a.get("reservationId"), "fr") and a.get("sourceId") == "nursery-west"
		"plant_tree":
			return a.size() == 4 and uid(a.get("reservationId"), "fr") and a.get("plotId") in PLOTS
		_:
			return a.size() == 5 and uid(a.get("reservationId"), "fr") and uid(a.get("plantId"), "p") and uid(a.get("toolId"), "t")

static func capture(o: Dictionary, a: Dictionary) -> Dictionary:
	if not supported(o) or not valid_action(a):
		return {}
	var b := {"position": o.self.position.duplicate(), "inventoryWood": o.self.inventory.wood, "seeds": o.forestry.seeds,
		"forestryActorId": o.identity.actorId, "forestryOperatorId": o.identity.operatorId, "forestryAdoption": o.forestry.adoption.duplicate(true),
		"serviceMs": o.forestry.nursery.serviceMs, "reservation": null, "plant": null, "tool": null, "bench": null,
		"plantIds": o.forestry.plants.map(func(p): return p.plantId), "toolIds": o.forestry.tools.map(func(x): return x.toolId)}
	for r in o.forestry.reservations:
		if r.reservationId == a.get("reservationId"):
			b.reservation = r.duplicate(true)
	for p in o.forestry.plants:
		if p.plantId == a.get("plantId"):
			b.plant = p.duplicate(true)
	for item in o.forestry.tools:
		if item.toolId == a.get("toolId"):
			b.tool = item.duplicate(true)
	for item in o.workshop.workbenches:
		if item.entityId == a.get("entityId"):
			b.bench = item.duplicate(true)
	return b if valid_before(a, b) else {}

static func valid_before(a: Dictionary, b: Variant) -> bool:
	if not valid_action(a) or not b is Dictionary or not Notes.point(b.get("position")) or not Notes.whole(b.get("inventoryWood")) or b.inventoryWood > 12 \
		or not Notes.whole(b.get("seeds")) or b.get("forestryActorId") not in Notes.ROSTER or b.get("forestryOperatorId") != Notes.ROSTER[b.forestryActorId] \
		or not adoption(b.get("forestryAdoption")) or not Notes.whole(b.get("serviceMs")) or not b.get("plantIds") is Array or not b.get("toolIds") is Array \
		or not b.has_all(["reservation", "plant", "tool", "bench"]):
		return false
	if a.type == "craft_forestry_tool":
		return Workshop.valid_entity(b.bench) and b.bench.definitionId == "workbench" and b.bench.entityId == a.entityId and b.inventoryWood >= 2 \
			and b.reservation == null and b.plant == null and b.tool == null
	if a.type == "reserve_forest":
		return b.reservation == null and b.plant == null and b.tool == null and b.bench == null
	if not reservation(b.reservation) or b.reservation.reservationId != a.reservationId or b.reservation.actorId != b.forestryActorId or b.bench != null:
		return false
	var r: Dictionary = b.reservation
	match a.type:
		"cancel_forest_reservation":
			return r.status in ["queued", "preparing"] and b.plant == null and b.tool == null
		"collect_seed":
			return r.status == "preparing" and r.expiresAtMs > b.serviceMs and r.reservedSeed == 1 and b.plant == null and b.tool == null
		"plant_tree":
			return r.status == "preparing" and r.expiresAtMs > b.serviceMs and r.plotId == a.plotId and b.seeds >= 1 and b.plant == null and b.tool == null
		_:
			return r.status == "harvesting" and r.expiresAtMs > b.serviceMs and plant(b.plant) and b.plant.state == "mature" and r.plantId == a.plantId \
				and b.plant.plantId == a.plantId and tool(b.tool) and b.tool.toolId == a.toolId and b.tool.ownerActorId == b.forestryActorId and b.inventoryWood <= 9

static func valid_detail(d: Variant) -> bool:
	if not d is Dictionary or d.size() != DETAIL_FIELDS.size() or not d.has_all(DETAIL_FIELDS) or d.capabilityVersion != 1 \
		or d.authorActorId not in Notes.ROSTER or d.operatorId != Notes.ROSTER[d.authorActorId] or not original_id(d.commandId) \
		or not d.action is Dictionary or not valid_action(d.action) or not Notes.point(d.position) or not Notes.whole(d.serviceMs) \
		or not Notes.whole(d.stateVersion) or d.stateVersion < 1 or not Notes.whole(d.eventCursor) or d.eventCursor != d.stateVersion + 1 \
		or not d.completedAtUtc is String or d.completedAtUtc.is_empty():
		return false
	for key in ["inventoryWoodBefore", "inventoryWood", "seedsBefore", "seeds", "nurseryStockBefore", "nurseryStock"]:
		if not Notes.whole(d[key]):
			return false
	if d.inventoryWoodBefore > 12 or d.inventoryWood > 12 or d.nurseryStockBefore > 4 or d.nurseryStock > 4:
		return false
	var a: Dictionary = d.action
	var wood_delta := -2 if a.type == "craft_forestry_tool" else 3 if a.type == "harvest_tree" else 0
	var seed_delta := -1 if a.type == "plant_tree" else 1 if a.type in ["collect_seed", "harvest_tree"] else 0
	if d.inventoryWood != d.inventoryWoodBefore + wood_delta or d.seeds != d.seedsBefore + seed_delta \
		or d.nurseryStock != d.nurseryStockBefore - (1 if a.type == "collect_seed" else 0):
		return false
	if a.type == "craft_forestry_tool":
		return d.reservationBefore == null and d.reservation == null and d.plantBefore == null and d.plant == null and tool(d.tool) \
			and d.tool.ownerActorId == d.authorActorId and d.tool.workbenchId == a.entityId and d.tool.commandId == d.commandId \
			and d.tool.stateVersion == d.stateVersion and d.tool.eventCursor == d.eventCursor
	if not reservation(d.reservation) or d.reservation.actorId != d.authorActorId:
		return false
	if a.type == "reserve_forest":
		return d.reservationBefore == null and d.plantBefore == null and d.plant == null and d.tool == null and d.reservation.status == "queued" \
			and d.reservation.commandId == d.commandId and d.reservation.requestedAtMs == d.serviceMs and d.reservation.queueOrder == d.eventCursor
	if not reservation(d.reservationBefore) or d.reservationBefore.reservationId != a.reservationId or d.reservationBefore.actorId != d.authorActorId:
		return false
	var expected: Dictionary = d.reservationBefore.duplicate(true)
	match a.type:
		"cancel_forest_reservation":
			if expected.status not in ["queued", "preparing"] or d.plantBefore != null or d.plant != null or d.tool != null:
				return false
			expected.status = "cancelled"
			expected.reservedSeed = 0
		"collect_seed":
			if expected.status != "preparing" or expected.expiresAtMs <= d.serviceMs or expected.reservedSeed != 1 or d.plantBefore != null or d.plant != null or d.tool != null:
				return false
			expected.reservedSeed = 0
		"plant_tree":
			if expected.status != "preparing" or expected.expiresAtMs <= d.serviceMs or expected.plotId != a.plotId or d.plantBefore != null or not plant(d.plant) \
				or d.plant.state != "growing" or d.tool != null or d.plant.plotId != a.plotId or d.plant.reservationId != a.reservationId \
				or d.plant.planterActorId != d.authorActorId or d.plant.operatorId != d.operatorId or d.plant.commandId != d.commandId \
				or d.plant.stateVersion != d.stateVersion or d.plant.eventCursor != d.eventCursor or d.plant.plantedAtMs != d.serviceMs:
				return false
			expected.status = "growing"
			expected.plantId = d.plant.plantId
			expected.reservedSeed = 0
			expected.expiresAtMs = null
		"harvest_tree":
			if expected.status != "harvesting" or expected.expiresAtMs <= d.serviceMs or expected.plantId != a.plantId \
				or not plant(d.plantBefore) or d.plantBefore.state != "mature" or d.plantBefore.plantId != a.plantId or not plant(d.plant) \
				or not tool(d.tool) or d.tool.toolId != a.toolId or d.tool.ownerActorId != d.authorActorId:
				return false
			var harvested: Dictionary = d.plantBefore.duplicate(true)
			harvested.merge({"state": "harvested", "standingWood": 0, "harvestActorId": d.authorActorId, "harvestCommandId": d.commandId, "harvestEventCursor": d.eventCursor}, true)
			if not same(harvested, d.plant):
				return false
			expected.status = "completed"
	return same(expected, d.reservation)

static func same_reservation_before(a: Dictionary, actual: Variant, before: Variant) -> bool:
	if same(actual, before):
		return true
	# Queued cancellation may observe a real grant inside the command transaction.
	if a.type != "cancel_forest_reservation" or not reservation(actual) or not reservation(before) or before.status != "queued" or actual.status != "preparing":
		return false
	for key in ["reservationId", "actorId", "operatorId", "commandId", "requestedAtMs", "queueOrder"]:
		if actual[key] != before[key]:
			return false
	return true

static func result(data: Dictionary, command: Dictionary, b: Dictionary) -> bool:
	var d = data.get("result", {}).get("forestryAction")
	if not valid_before(command.action, b) or not valid_detail(d) or not same(d.action, command.action) or data.result.get("action") != command.action.type \
		or d.authorActorId != b.forestryActorId or d.operatorId != b.forestryOperatorId or d.commandId != command.commandId \
		or data.get("identity", {}).get("actorId") != d.authorActorId or data.get("identity", {}).get("operatorId") != d.operatorId \
		or d.stateVersion != data.get("stateVersion") or d.eventCursor != data.get("eventCursor") or d.stateVersion <= b.forestryAdoption.stateVersion \
		or not same(d.position, b.position) or d.inventoryWoodBefore != b.inventoryWood or d.seedsBefore != b.seeds \
		or d.serviceMs < b.serviceMs or not same_reservation_before(command.action, d.reservationBefore, b.reservation) or not same(d.plantBefore, b.plant):
		return false
	match command.action.type:
		"craft_forestry_tool":
			return d.tool.toolId not in b.toolIds and Notes.distance(b.position, b.bench.position) <= 1.600001
		"collect_seed":
			return Notes.distance(b.position, [7, 6]) <= 1.600001
		"plant_tree":
			return d.plant.plantId not in b.plantIds and Notes.distance(b.position, PLOTS[command.action.plotId]) <= 1.600001
		"harvest_tree":
			return same(d.tool, b.tool) and Notes.distance(b.position, PLOTS[b.plant.plotId]) <= 1.600001
	return true

static func event(value: Variant, data: Dictionary) -> bool:
	return value is Dictionary and value.get("type") == "forestryActionCompleted" and value.get("actorId") == data.identity.actorId \
		and value.get("commandId") == data.commandId and value.get("seq") == data.eventCursor and value.get("stateVersion") == data.stateVersion \
		and same(value.get("forestryAction"), data.result.forestryAction)

static func detail(value: Dictionary, data: Dictionary) -> bool:
	return value.get("schemaVersion") == 1 and value.get("rulesVersion") == "r10" and value.get("error") == null \
		and same(value.get("forestryAction"), data.result.forestryAction) and Notes.whole(value.get("stateVersion")) \
		and value.stateVersion >= data.stateVersion and value.get("identity", {}).get("actorId") == data.identity.actorId

static func retry_supported(o: Dictionary, b: Dictionary) -> bool:
	if not supported(o) or not same(o.forestry.adoption, b.forestryAdoption):
		return false
	if b.bench != null and not o.workshop.workbenches.any(func(e): return same(e, b.bench)):
		return false
	return b.tool == null or o.forestry.tools.any(func(item): return same(item, b.tool))
