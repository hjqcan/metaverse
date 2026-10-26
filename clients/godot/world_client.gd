extends Node
## Engine adapter: serialized HTTP, authoritative observations, durable original commands.
signal changed

const API = "/v1/worlds/foundation-01"
const PendingStore = preload("res://pending_store.gd")
const Evidence = preload("res://command_evidence.gd")
const INSTANCE_HEADER = "World-Instance-Id"
var endpoint = "http://127.0.0.1:5089"
var token = ""
var observation: Dictionary = {}
var identity: Dictionary = {}
var pending: Dictionary = {}
var journal: Dictionary = {}
var pending_store: RefCounted
var healthy = false
var busy = false
var storage_ok = true
var message = "连接世界后开始探索。"
var last_receipt: Dictionary = {}
var state_path = "user://continuous-pending.json"
var floor_version = 0
var retry_allowed = false
var connection_generation = 0
var instance_id = ""
var binding_known = false
var legacy_unbound = false
var foreign_pending = 0
var scanned_connection = -1

func _ready() -> void:
	if OS.has_environment("WORLD_CLIENT_STATE"):
		state_path = OS.get_environment("WORLD_CLIENT_STATE")
	pending_store = PendingStore.new(state_path, _valid_record)
	pending_store.read("")
	storage_ok = pending_store.healthy

func _valid_record(record: Variant) -> bool:
	if not record is Dictionary or not record.get("body") is String or not record.get("actorId") is String or not record.get("commandId") is String:
		return false
	var record_version := 0
	if record.has("recordVersion"):
		if not Evidence.whole(record.recordVersion):
			return false
		record_version = int(record.recordVersion)
		if record_version not in [2, 3, 4, 5, 6, 7] or not _valid_instance(record.get("instanceId")) \
			or record.get("worldId") != "foundation-01" or not record.get("endpoint") is String:
			return false
	elif record.has("instanceId"):
		return false
	var parser = JSON.new()
	if parser.parse(record.body) != OK or not parser.data is Dictionary:
		return false
	var command: Dictionary = parser.data
	if record_version in [3, 4, 5, 6, 7]:
		if (record_version in [4, 5, 6, 7]) != (command.get("rulesVersion") == "r10"):
			return false
		if command.get("preconditionMode") != Evidence.MODE or not record.get("before") is String:
			return false
		var before = JSON.parse_string(record.before)
		if not command.get("action") is Dictionary or not Evidence.valid_before(command.action, before):
			return false
		if command.action.get("type") == "transfer" and before.get("senderActorId") != record.actorId:
			return false
		if command.action.get("type") in ["reserve_material", "cancel_reservation", "harvest_material"] and before.get("materialActorId") != record.actorId:
			return false
		if command.action.get("type") == "paint_entity_canvas" and (before.get("canvasActorId") != record.actorId or before.get("canvasAdoption", {}).get("worldInstanceId") != record.instanceId):
			return false
		if (record_version == 7) != Evidence.Forestry.is_action(command.action.get("type")):
			return false
		if record_version == 7 and (before.get("forestryActorId") != record.actorId or before.get("forestryAdoption", {}).get("worldInstanceId") != record.instanceId):
			return false
		if (record_version == 6) != Evidence.Workshop.is_action(command.action.get("type")):
			return false
		if record_version == 6 and (before.get("workshopActorId") != record.actorId or before.get("workshopAdoption", {}).get("worldInstanceId") != record.instanceId):
			return false
		if (record_version == 5) != (command.action.get("type") == "paint_entity_canvas"):
			return false
		if command.action.get("type") == "append_entity_note" and before.get("noteActorId") != record.actorId:
			return false
	elif command.has("preconditionMode"):
		return false
	return command.get("commandId") == record.commandId and command.get("schemaVersion") == 1 \
		and command.get("rulesVersion") in ["r8", "r9", "r10"] and Evidence.whole(command.get("expectedStateVersion")) \
		and (command.rulesVersion != "r10" or record_version in [4, 5, 6, 7]) \
		and command.get("action") is Dictionary and (command.action.get("type") in ["walk", "gather", "build"] \
			or (command.action.get("type") == "transfer" and command.rulesVersion in ["r9", "r10"] and record_version in [3, 4]) \
			or (command.action.get("type") in ["reserve_material", "cancel_reservation", "harvest_material", "append_entity_note"] and command.rulesVersion == "r10" and record_version == 4) \
			or (command.action.get("type") == "paint_entity_canvas" and command.rulesVersion == "r10" and record_version == 5) \
			or (Evidence.Workshop.is_action(command.action.get("type")) and command.rulesVersion == "r10" and record_version == 6) \
			or (Evidence.Forestry.is_action(command.action.get("type")) and command.rulesVersion == "r10" and record_version == 7))

func can_act() -> bool:
	return healthy and not busy and storage_ok and not legacy_unbound and pending.is_empty()

func _valid_instance(value: Variant) -> bool:
	if not value is String or value.length() != 34 or not value.begins_with("w_"):
		return false
	for character in value.substr(2):
		if not "0123456789abcdef".contains(character):
			return false
	return true

func connect_world(url: String, secret: String) -> void:
	if busy:
		return
	connection_generation += 1
	endpoint = url.strip_edges().trim_suffix("/")
	token = secret.strip_edges()
	observation = {}
	identity = {}
	pending = {}
	instance_id = ""
	binding_known = false
	legacy_unbound = false
	foreign_pending = 0
	floor_version = 0
	healthy = false
	last_receipt = {}
	if token.is_empty() or not (endpoint.begins_with("http://") or endpoint.begins_with("https://")):
		message = "填写服务地址和居民令牌。"
		changed.emit()
		return
	await refresh()

func _key() -> String:
	if not instance_id.is_empty():
		return ("instance/" + instance_id + "/foundation-01/" + str(identity.get("actorId", ""))).sha256_text()
	return _legacy_key()

func _legacy_key() -> String:
	return (endpoint + "/foundation-01/" + str(identity.get("actorId", ""))).sha256_text()

func _load_pending() -> void:
	journal = pending_store.read(_key())
	legacy_unbound = not instance_id.is_empty() and not pending_store.read(_legacy_key()).is_empty()
	for record in journal.values():
		if record.actorId != identity.get("actorId") or record.get("instanceId", "") != instance_id:
			pending_store.healthy = false
	if scanned_connection != connection_generation or foreign_pending > 0:
		foreign_pending = pending_store.other_worlds(endpoint, str(identity.get("actorId", "")), instance_id)
		scanned_connection = connection_generation
	storage_ok = pending_store.healthy
	if storage_ok and pending.is_empty() and not journal.is_empty():
		pending = journal.values()[0]

func _request(path: String, method: int = HTTPClient.METHOD_GET, body: String = "") -> Dictionary:
	var request = HTTPRequest.new()
	request.timeout = 6.0
	request.max_redirects = 0
	request.body_size_limit = 2 * 1024 * 1024
	add_child(request)
	var headers = PackedStringArray(["Authorization: Bearer " + token, "Content-Type: application/json", "World-Capabilities: workshop-v1,forestry-v1"])
	if not instance_id.is_empty():
		headers.append(INSTANCE_HEADER + ": " + instance_id)
	var error = request.request(endpoint + path, headers, method, body)
	if error != OK:
		request.queue_free()
		return {"code": 0, "data": {}}
	var reply = await request.request_completed
	request.queue_free()
	var parser = JSON.new()
	var parse_error = parser.parse(reply[3].get_string_from_utf8())
	var parsed = _integer_fields(parser.data) if parse_error == OK else {}
	var instances: Array[String] = []
	for header in reply[2]:
		var separator = header.find(":")
		if separator > 0 and header.substr(0, separator).to_lower() == INSTANCE_HEADER.to_lower():
			instances.append(header.substr(separator + 1).strip_edges())
	var response_instance = instances[0] if instances.size() == 1 else ""
	return {"code": reply[1] if reply[0] == HTTPRequest.RESULT_SUCCESS else 0, "data": parsed if parsed is Dictionary else {},
		"instanceId": response_instance, "bindingValid": instances.is_empty() or (instances.size() == 1 and _valid_instance(response_instance))}

func _reply_binding(reply: Dictionary) -> bool:
	return reply.get("bindingValid", false) and reply.get("instanceId", "") == instance_id

func _observation_binding(reply: Dictionary) -> bool:
	var world_id = reply.data.get("world", {}).get("instanceId", "")
	if not reply.get("bindingValid", false) or reply.get("instanceId", "") != world_id:
		return false
	if world_id != "":
		if not _valid_instance(world_id) or reply.data.get("commandBinding") != {"version": 1, "required": true, "header": INSTANCE_HEADER}:
			return false
	elif reply.data.has("commandBinding"):
		return false
	if binding_known and instance_id != world_id:
		return false
	instance_id = world_id
	binding_known = true
	return true

func _integer_fields(value: Variant) -> Variant:
	# JSON counts become integers; fractional metre coordinates stay fractional.
	if value is float and is_finite(value) and value == floor(value) and abs(value) <= 9007199254740991:
		return int(value)
	if value is Array:
		return value.map(_integer_fields)
	if value is Dictionary:
		for key in value:
			value[key] = _integer_fields(value[key])
	return value

func _valid_observation(data: Dictionary) -> bool:
	for field in ["world", "identity", "self"]:
		if not data.get(field) is Dictionary:
			return false
	if data.has("forestry") and not Evidence.Forestry.supported(data):
		return false
	for obstacle in data.get("terrain", {}).get("obstacles", []):
		if obstacle.get("kind") in ["forestry_nursery", "forestry_tree"] and not data.has("forestry"):
			return false
	if data.has("workshop") and not Evidence.Workshop.supported(data):
		return false
	for entity in data.get("entities", []):
		if not entity is Dictionary or Evidence.Workshop.half_size(str(entity.get("definitionId"))).is_zero_approx() \
			or (entity.get("definitionId") in ["workbench", "wooden_chest"] and not data.has("workshop")):
			return false
	return data.get("schemaVersion") == 1 and Evidence.continuous_world(data) \
		and data.get("world", {}).get("id") == "foundation-01" \
		and (data.rulesVersion not in ["r9", "r10"] or (Evidence.transfer_supported(data) and data.get("recentTransfers") is Dictionary \
			and data.recentTransfers.get("items") is Array and data.recentTransfers.get("truncated") is bool)) \
		and (data.rulesVersion != "r10" or Evidence.material_supported(data)) \
		and data.get("identity", {}).get("actorId", "") == data.get("self", {}).get("actorId", "?") \
		and data.get("stateVersion") is int and data.get("stateVersion", -1) >= floor_version \
		and (identity.is_empty() or data.get("identity", {}).get("actorId") == identity.get("actorId")) \
		and data.get("self", {}).get("position", []).size() == 2 \
		and data.get("resourceNodes") is Array and data.get("entities") is Array \
		and data.get("movement", {}).get("kind") == "continuous"

func _observe() -> bool:
	var reply = await _request(API + "/observation")
	if reply.code != 200 or not _valid_observation(reply.data) or not _observation_binding(reply):
		healthy = false
		message = "世界未同步，操作暂停。请检查连接、令牌及连续荒野场景。"
		return false
	observation = reply.data
	identity = observation.identity
	floor_version = int(observation.stateVersion)
	_load_pending()
	healthy = true
	return true

func refresh() -> void:
	if busy or token.is_empty():
		return
	busy = true
	changed.emit()
	var was_healthy = healthy
	if await _observe():
		if not storage_ok:
			message = "恢复记录损坏或无法读取。原文件已保留，请修复后重启客户端。"
		elif legacy_unbound:
			message = "旧动作尚不能确认属于这个世界。记录已保留，先回原世界确认。"
		elif not pending.is_empty():
			await _lookup()
		elif not was_healthy:
			message = "已进入荒野。走到树旁，采集木材，再搭建。"
			if foreign_pending > 0:
				message += " 另一个世界的未确认动作已保留。"
	busy = false
	changed.emit()

func send_action(action: Dictionary) -> void:
	if not can_act():
		return
	if Evidence.Forestry.is_action(action.get("type")) and (not Evidence.Forestry.supported(observation) or not Evidence.supported(observation)):
		message = "当前世界尚未提供可核对的育林能力。"
		changed.emit()
		return
	if Evidence.Workshop.is_action(action.get("type")) and (not Evidence.Workshop.supported(observation) or not Evidence.supported(observation)):
		message = "这个世界尚未提供可核对的工作台和储物箱。"
		changed.emit()
		return
	if action.get("type") == "paint_entity_canvas" and (not Evidence.Canvas.supported(observation) or not Evidence.supported(observation)):
		message = "当前世界尚未提供可核对的平台地画。"
		changed.emit()
		return
	if action.get("type") == "append_entity_note" and (not Evidence.Notes.supported(observation) or not Evidence.supported(observation)):
		message = "这个世界尚未提供旧桥共同手记。"
		changed.emit()
		return
	if action.get("type") == "transfer" and (not Evidence.transfer_supported(observation) or not Evidence.supported(observation)):
		message = "这个世界尚未提供木材赠送。"
		changed.emit()
		return
	if action.get("type") in ["reserve_material", "cancel_reservation", "harvest_material"] \
		and (not Evidence.material_supported(observation) or not Evidence.supported(observation)):
		message = "这个世界尚未提供预约采集。"
		changed.emit()
		return
	# Another process may have saved an unresolved command since the last poll.
	_load_pending()
	if not can_act():
		message = "另一个客户端留下的原动作尚待确认。请先查询原结果。"
		changed.emit()
		return
	var command_id = "godot_" + Crypto.new().generate_random_bytes(16).hex_encode()
	var command = {"schemaVersion": 1, "rulesVersion": observation.rulesVersion,
		"commandId": command_id, "expectedStateVersion": int(observation.stateVersion), "action": action}
	var before: Dictionary = {}
	var actor_mode = Evidence.supported(observation)
	if actor_mode:
		before = Evidence.capture(observation, action)
		if before.is_empty():
			healthy = false
			message = "当前动作依据不完整，请重新观察。"
			changed.emit()
			return
		command.preconditionMode = Evidence.MODE
	pending = {"actorId": identity.actorId, "commandId": command_id, "body": JSON.stringify(command)}
	if not instance_id.is_empty():
		pending.merge({"recordVersion": 7 if Evidence.Forestry.is_action(action.get("type")) else 6 if Evidence.Workshop.is_action(action.get("type")) else 5 if action.get("type") == "paint_entity_canvas" else 4 if observation.rulesVersion == "r10" else 3 if actor_mode else 2, "instanceId": instance_id, "worldId": "foundation-01", "endpoint": endpoint})
		if actor_mode:
			# Keep records flat so disk JSON number coercion cannot change equality.
			pending.before = JSON.stringify(before)
	if not pending_store.put(_key(), pending):
		storage_ok = false
		message = "无法保存动作恢复记录，尚未发送。检查本地存储后重新连接。"
		changed.emit()
		return
	journal[pending.commandId] = pending
	busy = true
	message = "等待世界确认…"
	changed.emit()
	await _submit()
	busy = false
	changed.emit()

func _settle(reply: Dictionary) -> bool:
	var data = reply.data
	if pending.is_empty() or not _reply_binding(reply) or not data.get("identity") is Dictionary or data.get("commandId") != pending.commandId \
		or data.get("identity", {}).get("actorId") != pending.actorId \
		or data.get("schemaVersion") != 1 \
		or data.get("stateVersion", -1) < 0:
		return false
	var command = JSON.parse_string(pending.body)
	if data.get("rulesVersion") != command.get("rulesVersion"):
		return false
	var committed = reply.code == 200 and data.get("status") == "committed" and data.get("error") == null
	var rejected = reply.code in [403, 404, 409, 422] and data.get("status") == "rejected" and data.get("error") is Dictionary and data.error.get("mutated") == false
	var actor_mode = command.get("preconditionMode") == Evidence.MODE
	if actor_mode and not Evidence.execution(data, command, committed):
		return false
	if committed and not data.get("result") is Dictionary:
		return false
	if committed and (data.get("result", {}).get("action") != command.action.type or (not actor_mode and data.stateVersion != command.expectedStateVersion + 1)):
		return false
	if committed and command.action.type == "gather" and (data.result.get("nodeId") != command.action.nodeId or data.result.get("quantity") != 1):
		return false
	if not committed and not rejected:
		return false
	var observed_build = false
	if actor_mode and committed:
		var before: Dictionary = JSON.parse_string(pending.before)
		if not Evidence.result(data, command, before):
			return false
		if command.action.type in ["reserve_material", "append_entity_note", "paint_entity_canvas"] or Evidence.Workshop.is_action(command.action.type) or Evidence.Forestry.is_action(command.action.type):
			if not Evidence.whole(data.get("eventCursor")) or data.eventCursor < 1:
				return false
			var events_reply: Dictionary = await _request(API + "/events?after=" + str(int(data.eventCursor) - 1))
			if events_reply.code != 200 or not _reply_binding(events_reply) or not events_reply.data.get("events") is Array \
				or events_reply.data.events.is_empty():
				return false
			if Evidence.Forestry.is_action(command.action.type) and not Evidence.Forestry.event(events_reply.data.events[0], data):
				return false
			if Evidence.Workshop.is_action(command.action.type) and not Evidence.Workshop.event(events_reply.data.events[0], data):
				return false
			if command.action.type == "reserve_material" and not Evidence.reserved_event(events_reply.data.events[0], data, command):
				return false
			if command.action.type == "append_entity_note" and not Evidence.Notes.event(events_reply.data.events[0], data):
				return false
			if command.action.type == "paint_entity_canvas" and not Evidence.Canvas.event(events_reply.data.events[0], data):
				return false
		if Evidence.Forestry.is_action(command.action.type):
			var forestry_reply: Dictionary = await _request(API + "/forestry/actions/" + pending.actorId.uri_encode() + "/" + pending.commandId.uri_encode())
			if forestry_reply.code != 200 or not _reply_binding(forestry_reply) or not Evidence.Forestry.detail(forestry_reply.data, data):
				return false
		if Evidence.Workshop.is_action(command.action.type):
			var workshop_reply: Dictionary = await _request(API + "/workshop/actions/" + pending.actorId.uri_encode() + "/" + pending.commandId.uri_encode())
			if workshop_reply.code != 200 or not _reply_binding(workshop_reply) or not Evidence.Workshop.detail(workshop_reply.data, data):
				return false
		if command.action.type == "paint_entity_canvas":
			var edit_reply: Dictionary = await _request(API + "/entities/" + command.action.entityId.uri_encode() + "/canvas/edits/" + pending.actorId.uri_encode() + "/" + pending.commandId.uri_encode())
			if edit_reply.code != 200 or not _reply_binding(edit_reply) or not Evidence.Canvas.detail(edit_reply.data, data):
				return false
		if command.action.type == "append_entity_note":
			if not await _observe() or not Evidence.Notes.confirmed(observation, data, before):
				return false
			observed_build = true
		if command.action.type == "build":
			if not await _observe() or not Evidence.built_entity(observation, data, command, before, pending.actorId):
				return false
			observed_build = true
	last_receipt = data
	floor_version = maxi(floor_version, int(data.stateVersion))
	if not pending_store.settle(_key(), pending):
		storage_ok = false
		message = "动作已有回执，但恢复记录未能更新。检查本地存储。"
		return false
	journal.erase(pending.commandId)
	pending = {}
	healthy = false
	message = "动作已完成。" if committed else "操作未完成：" + str(data.error.get("message", "请求被拒绝"))
	if not observed_build:
		await _observe()
	else:
		healthy = true
	return true

func _submit() -> void:
	var reply = await _request(API + "/commands", HTTPClient.METHOD_POST, pending.body)
	if not await _settle(reply):
		healthy = false
		message = "动作结果待确认。原请求已保留；可查询或原样重试。"

func _lookup() -> void:
	retry_allowed = false
	var reply = await _request(API + "/commands/" + pending.commandId.uri_encode())
	if not await _settle(reply):
		retry_allowed = _reply_binding(reply) and reply.code == 404 and reply.data.get("error", {}).get("code") == "COMMAND_NOT_FOUND" and reply.data.get("identity", {}).get("actorId") == pending.actorId
		var command = JSON.parse_string(pending.body)
		if Evidence.Forestry.is_action(command.action.get("type")):
			var capable := false
			var before = JSON.parse_string(pending.before)
			if await _observe():
				capable = Evidence.Forestry.retry_supported(observation, before)
			retry_allowed = retry_allowed and capable
			if not capable:
				healthy = false
				message = "原育林请求已保留。恢复原实例与林业能力后继续查证。"
				return
		if Evidence.Workshop.is_action(command.action.get("type")):
			var capable := false
			var before = JSON.parse_string(pending.before)
			if await _observe():
				capable = Evidence.Workshop.retry_supported(observation, before)
			retry_allowed = retry_allowed and capable
			if not capable:
				healthy = false
				message = "原制作或存取请求已保留。请恢复原工作坊能力和目标后查证。"
				return
		if command.action.get("type") == "paint_entity_canvas":
			var capable := false
			var before = JSON.parse_string(pending.before)
			if await _observe():
				capable = Evidence.Canvas.supported(observation) and Evidence.Canvas.same_target(observation.entityCanvas.target, before.canvasTarget)
			retry_allowed = retry_allowed and capable
			if not capable:
				healthy = false
				message = "原地画请求已保留。当前服务缺少原平台地画能力，请恢复后查询。"
				return
		if command.action.get("type") == "append_entity_note":
			# An old r10 service parses POST before receipt lookup. Never let its
			# unknown-action response replace the result of this original request.
			var capable := false
			if await _observe():
				capable = Evidence.Notes.supported(observation)
			retry_allowed = retry_allowed and capable
			if not capable:
				healthy = false
				message = "原手记请求已保留。当前服务缺少手记能力，请恢复支持该能力的服务后查询。"
				return
		healthy = false
		message = "尚未确认原动作。新动作暂停；可查询或原样重试。"

func recover(retry: bool = false) -> void:
	if busy or pending.is_empty() or identity.get("actorId") != pending.get("actorId"):
		return
	busy = true
	changed.emit()
	var original_id: String = pending.commandId
	await _lookup()
	if retry and retry_allowed and pending.get("commandId") == original_id and storage_ok:
		await _submit()
	busy = false
	changed.emit()
