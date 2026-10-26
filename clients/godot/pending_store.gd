extends RefCounted
## Each command owns its file; another client never rewrites a shared snapshot.
var path: String
var validate: Callable
var healthy = true

func _same_record(left: Dictionary, right: Dictionary) -> bool:
	# Godot's JSON parser represents version numbers as floats. Compare the flat
	# record fields rather than Dictionary equality, which distinguishes 2 and 2.0.
	if left.size() != right.size():
		return false
	for key in left:
		if not right.has(key) or left[key] != right[key]:
			return false
	return true

func _init(base_path: String, record_validator: Callable) -> void:
	path = base_path
	validate = record_validator

func _json(file_path: String, may_disappear: bool = false) -> Variant:
	var file = FileAccess.open(file_path, FileAccess.READ)
	if file == null:
		if not may_disappear or FileAccess.file_exists(file_path):
			healthy = false
		return null
	var parser = JSON.new()
	var error = parser.parse(file.get_as_text())
	file.close()
	if error != OK:
		healthy = false
		return null
	return parser.data

func _legacy() -> Dictionary:
	if not FileAccess.file_exists(path):
		return {}
	var saved = _json(path)
	if not saved is Dictionary:
		healthy = false
		return {}
	for key in saved:
		if not validate.call(saved[key]):
			healthy = false
	return saved

func _entry_path(binding: String, command_id: String) -> String:
	return path + ".d/" + binding + "/" + command_id.sha256_text() + ".json"

func _marker(binding: String, record: Dictionary) -> Dictionary:
	return {"version": 1, "binding": binding, "commandId": record.commandId, "requestHash": record.body.sha256_text()}

func _settled(binding: String, record: Dictionary) -> bool:
	var marker_path = _entry_path(binding, record.commandId) + ".done"
	if not FileAccess.file_exists(marker_path):
		return false
	var saved = _json(marker_path)
	if not saved is Dictionary or saved.get("version") != 1 or saved.get("binding") != binding \
		or saved.get("commandId") != record.commandId or saved.get("requestHash") != record.body.sha256_text():
		healthy = false
	return healthy

func read(binding: String) -> Dictionary:
	var records: Dictionary = {}
	var legacy = _legacy()
	if not healthy or binding.is_empty():
		return records
	if legacy.has(binding) and not _settled(binding, legacy[binding]):
		records[legacy[binding].commandId] = legacy[binding]
	if not healthy:
		return records
	var directory_path = path + ".d/" + binding
	if not DirAccess.dir_exists_absolute(directory_path):
		return records
	var directory = DirAccess.open(directory_path)
	if directory == null:
		healthy = false
		return records
	for filename in directory.get_files():
		if not filename.ends_with(".json"):
			continue
		var file_path = directory_path + "/" + filename
		var data = _json(file_path, true)
		# A different process may have settled this command after enumeration.
		if data == null and not FileAccess.file_exists(file_path):
			continue
		if not data is Dictionary or data.get("version") != 1 or data.get("binding") != binding or not validate.call(data.get("record")):
			healthy = false
			return records
		var record: Dictionary = data.record
		if file_path != _entry_path(binding, record.commandId) or (records.has(record.commandId) and not _same_record(records[record.commandId], record)):
			healthy = false
			return records
		if not _settled(binding, record):
			records[record.commandId] = record
		if not healthy:
			return records
	return records

func other_worlds(endpoint: String, actor: String, instance: String) -> int:
	# Used only on explicit connection, to keep another world's originals visible.
	var directory = DirAccess.open(path + ".d")
	if directory == null:
		return 0
	var count = 0
	for binding in directory.get_directories():
		for record in read(binding).values():
			if (record.get("recordVersion") == 2 or record.get("recordVersion") == 3 or record.get("recordVersion") == 4 or record.get("recordVersion") == 5 or record.get("recordVersion") == 6 or record.get("recordVersion") == 7) and record.get("endpoint") == endpoint \
				and record.actorId == actor and record.instanceId != instance:
				count += 1
	return count

func _write(file_path: String, value: Dictionary) -> bool:
	if DirAccess.make_dir_recursive_absolute(file_path.get_base_dir()) != OK:
		healthy = false
		return false
	var temporary = file_path + "." + Crypto.new().generate_random_bytes(16).hex_encode() + ".tmp"
	var file = FileAccess.open(temporary, FileAccess.WRITE)
	if file == null:
		healthy = false
		return false
	file.store_string(JSON.stringify(value))
	file.flush()
	var write_error = file.get_error()
	file.close()
	healthy = write_error == OK and DirAccess.rename_absolute(temporary, file_path) == OK
	if not healthy and FileAccess.file_exists(temporary):
		DirAccess.remove_absolute(temporary)
	return healthy

func put(binding: String, record: Dictionary) -> bool:
	var records = read(binding)
	if not healthy or not validate.call(record):
		healthy = false
		return false
	if records.has(record.commandId):
		healthy = _same_record(records[record.commandId], record)
		return healthy
	return _write(_entry_path(binding, record.commandId), {"version": 1, "binding": binding, "record": record})

func settle(binding: String, record: Dictionary) -> bool:
	var legacy = _legacy()
	if not healthy:
		return false
	# Old aggregate journals remain read-only. A per-command marker prevents their
	# completed records from reappearing without overwriting another actor's entry.
	if legacy.has(binding) and legacy[binding].commandId == record.commandId:
		if not _same_record(legacy[binding], record):
			healthy = false
			return false
		if not _write(_entry_path(binding, record.commandId) + ".done", _marker(binding, record)):
			return false
	var file_path = _entry_path(binding, record.commandId)
	if FileAccess.file_exists(file_path):
		var data = _json(file_path, true)
		if data == null and not FileAccess.file_exists(file_path):
			return healthy
		if not data is Dictionary or not data.get("record") is Dictionary or not _same_record(data.record, record):
			healthy = false
			return false
		var error = DirAccess.remove_absolute(file_path)
		if error != OK and FileAccess.file_exists(file_path):
			healthy = false
			return false
	return healthy
