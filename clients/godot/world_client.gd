extends Node
## Engine adapter: serialized HTTP, authoritative observations, durable original commands.
signal changed

const API = "/v1/worlds/foundation-01"
var endpoint = "http://127.0.0.1:5088"
var token = ""
var observation: Dictionary = {}
var identity: Dictionary = {}
var pending: Dictionary = {}
var journal: Dictionary = {}
var healthy = false
var busy = false
var storage_ok = true
var message = "连接世界后开始探索。"
var last_receipt: Dictionary = {}
var state_path = "user://pending.json"
var floor_version = 0

func _ready() -> void:
	if OS.has_environment("WORLD_CLIENT_STATE"):
		state_path = OS.get_environment("WORLD_CLIENT_STATE")
	if FileAccess.file_exists(state_path):
		var saved = JSON.parse_string(FileAccess.get_file_as_string(state_path))
		if saved is Dictionary:
			journal = saved
			for key in journal:
				var record = journal[key]
				if not _valid_record(record):
					storage_ok = false
		else:
			storage_ok = false

func _valid_record(record: Variant) -> bool:
	if not record is Dictionary or not record.get("body") is String or not record.get("actorId") is String or not record.get("commandId") is String:
		return false
	var parser = JSON.new()
	if parser.parse(record.body) != OK or not parser.data is Dictionary:
		return false
	var command: Dictionary = parser.data
	return command.get("commandId") == record.commandId and command.get("schemaVersion") == 1 \
		and command.get("rulesVersion") == "r7" and typeof(command.get("expectedStateVersion")) in [TYPE_INT, TYPE_FLOAT] \
		and command.expectedStateVersion >= 0 and command.expectedStateVersion <= 9007199254740991 \
		and command.get("action") is Dictionary and command.action.get("type") in ["move", "gather", "build"]

func can_act() -> bool:
	return healthy and not busy and storage_ok and pending.is_empty()

func connect_world(url: String, secret: String) -> void:
	if busy:
		return
	endpoint = url.strip_edges().trim_suffix("/")
	token = secret.strip_edges()
	observation = {}
	identity = {}
	pending = {}
	floor_version = 0
	healthy = false
	last_receipt = {}
	if token.is_empty() or not (endpoint.begins_with("http://") or endpoint.begins_with("https://")):
		message = "填写服务地址和居民令牌。"
		changed.emit()
		return
	await refresh()

func _key() -> String:
	return (endpoint + "/foundation-01/" + str(identity.get("actorId", ""))).sha256_text()

func _save() -> bool:
	var temporary = state_path + ".tmp"
	var file = FileAccess.open(temporary, FileAccess.WRITE)
	if file == null:
		storage_ok = false
		return false
	file.store_string(JSON.stringify(journal))
	file.flush()
	var write_error = file.get_error()
	file.close()
	storage_ok = write_error == OK and DirAccess.rename_absolute(temporary, state_path) == OK
	return storage_ok

func _request(path: String, method: int = HTTPClient.METHOD_GET, body: String = "") -> Dictionary:
	var request = HTTPRequest.new()
	request.timeout = 6.0
	request.max_redirects = 0
	request.body_size_limit = 2 * 1024 * 1024
	add_child(request)
	var error = request.request(endpoint + path, ["Authorization: Bearer " + token, "Content-Type: application/json"], method, body)
	if error != OK:
		request.queue_free()
		return {"code": 0, "data": {}}
	var reply = await request.request_completed
	request.queue_free()
	var parser = JSON.new()
	var parse_error = parser.parse(reply[3].get_string_from_utf8())
	var parsed = _integer_fields(parser.data) if parse_error == OK else {}
	return {"code": reply[1] if reply[0] == HTTPRequest.RESULT_SUCCESS else 0, "data": parsed if parsed is Dictionary else {}}

func _integer_fields(value: Variant) -> Variant:
	# Godot's JSON reader produces floats; protocol coordinates and counts are integers.
	# Normalize once so array membership uses the same representation as local grid cells.
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
	return data.get("schemaVersion") == 1 and data.get("rulesVersion") == "r7" \
		and data.get("world", {}).get("id") == "foundation-01" \
		and data.get("world", {}).get("scenarioId") == "wilderness-v1" \
		and data.get("identity", {}).get("actorId", "") == data.get("self", {}).get("actorId", "?") \
		and data.get("stateVersion") is int and data.get("stateVersion", -1) >= floor_version \
		and (identity.is_empty() or data.get("identity", {}).get("actorId") == identity.get("actorId")) \
		and data.get("self", {}).get("position", []).size() == 2 \
		and data.get("resourceNodes") is Array and data.get("entities") is Array

func _observe() -> bool:
	var reply = await _request(API + "/observation")
	if reply.code != 200 or not _valid_observation(reply.data):
		healthy = false
		message = "世界未同步，操作暂停。请检查连接、令牌及 wilderness-v1 场景。"
		return false
	observation = reply.data
	identity = observation.identity
	floor_version = int(observation.stateVersion)
	pending = journal.get(_key(), {}) if storage_ok else {}
	healthy = true
	return true

func refresh() -> void:
	if busy or token.is_empty():
		return
	busy = true
	changed.emit()
	var was_healthy = healthy
	if await _observe():
		if not pending.is_empty():
			await _lookup()
		elif not was_healthy:
			message = "已进入荒野。走到树旁，采集木材，再搭建。"
	busy = false
	changed.emit()

func send_action(action: Dictionary) -> void:
	if not can_act():
		return
	var command_id = "godot_" + Crypto.new().generate_random_bytes(16).hex_encode()
	var command = {"schemaVersion": 1, "rulesVersion": observation.rulesVersion,
		"commandId": command_id, "expectedStateVersion": int(observation.stateVersion), "action": action}
	pending = {"actorId": identity.actorId, "commandId": command_id, "body": JSON.stringify(command)}
	journal[_key()] = pending
	if not _save():
		message = "无法保存动作恢复记录，尚未发送。检查本地存储后重新连接。"
		changed.emit()
		return
	busy = true
	message = "等待世界确认…"
	changed.emit()
	await _submit()
	busy = false
	changed.emit()

func _settle(reply: Dictionary) -> bool:
	var data = reply.data
	if pending.is_empty() or not data.get("identity") is Dictionary or data.get("commandId") != pending.commandId \
		or data.get("identity", {}).get("actorId") != pending.actorId \
		or data.get("schemaVersion") != 1 or data.get("rulesVersion") != "r7" \
		or data.get("stateVersion", -1) < 0:
		return false
	var command = JSON.parse_string(pending.body)
	var committed = reply.code == 200 and data.get("status") == "committed" and data.get("error") == null
	var rejected = reply.code in [403, 404, 409, 422] and data.get("status") == "rejected" and data.get("error") is Dictionary and data.error.get("mutated") == false
	if committed and not data.get("result") is Dictionary:
		return false
	if committed and (data.get("result", {}).get("action") != command.action.type or data.stateVersion != command.expectedStateVersion + 1):
		return false
	if committed and command.action.type == "gather" and (data.result.get("nodeId") != command.action.nodeId or data.result.get("quantity") != 1):
		return false
	if not committed and not rejected:
		return false
	last_receipt = data
	floor_version = maxi(floor_version, int(data.stateVersion))
	journal.erase(_key())
	if not _save():
		message = "动作已有回执，但恢复记录未能更新。检查本地存储。"
		return false
	pending = {}
	healthy = false
	message = "动作已完成。" if committed else "操作未完成：" + str(data.error.get("message", "请求被拒绝"))
	await _observe()
	return true

func _submit() -> void:
	var reply = await _request(API + "/commands", HTTPClient.METHOD_POST, pending.body)
	if not await _settle(reply):
		healthy = false
		message = "动作结果待确认。原请求已保留；可查询或原样重试。"

func _lookup() -> void:
	var reply = await _request(API + "/commands/" + pending.commandId.uri_encode())
	if not await _settle(reply):
		healthy = false
		message = "尚未确认原动作。新动作暂停；可查询或原样重试。"

func recover(retry: bool = false) -> void:
	if busy or pending.is_empty() or identity.get("actorId") != pending.get("actorId"):
		return
	busy = true
	changed.emit()
	await _lookup()
	if retry and not pending.is_empty() and storage_ok:
		await _submit()
	busy = false
	changed.emit()
