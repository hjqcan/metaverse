extends SceneTree
## Real separate processes share one recovery directory; no world mutations.
const Store = preload("res://pending_store.gd")
const Client = preload("res://world_client.gd")
var validator = Client.new()
var checks: Array = []
var failures = 0
var state_path = OS.get_environment("RECOVERY_STATE")
var binding = "same-endpoint-and-actor".sha256_text()

func _initialize() -> void:
	call_deferred("run")

func check(condition: bool, label: String) -> void:
	checks.append({"name": label, "passed": condition})
	if not condition:
		failures += 1
		push_error(label)

func record(command_id: String, actor: String = "a1") -> Dictionary:
	return {"actorId": actor, "commandId": command_id, "body": JSON.stringify({
		"schemaVersion": 1, "rulesVersion": "r8", "expectedStateVersion": 0,
		"commandId": command_id, "action": {"type": "walk", "to": [6, 7]}})}

func write_json(path: String, data: Dictionary) -> void:
	var file = FileAccess.open(path, FileAccess.WRITE)
	file.store_string(JSON.stringify(data))
	file.close()

func run() -> void:
	var mode = OS.get_environment("RECOVERY_MODE")
	var store = Store.new(state_path, validator._valid_record)
	if mode == "writer":
		var writer = OS.get_environment("RECOVERY_WRITER")
		store.read(binding)
		write_json(OS.get_environment("RECOVERY_READY"), {"ready": true})
		var deadline = Time.get_ticks_msec() + 10000
		while not FileAccess.file_exists(OS.get_environment("RECOVERY_GO")) and Time.get_ticks_msec() < deadline:
			await create_timer(0.01).timeout
		check(FileAccess.file_exists(OS.get_environment("RECOVERY_GO")), "both writers reached barrier")
		for index in 64:
			var original = record(writer + "_" + str(index))
			check(store.put(binding, original), "publish " + original.commandId)
			if index % 2 == 0:
				check(store.settle(binding, original), "settle only " + original.commandId)
	elif mode == "verify-concurrent":
		var records = store.read(binding)
		check(store.healthy and records.size() == 64, "both processes retained all 64 unresolved commands")
		for writer in ["first", "second"]:
			for index in 64:
				var command_id = writer + "_" + str(index)
				check(records.has(command_id) == (index % 2 == 1), "exact pending state " + command_id)
		for original in records.values():
			check(store.settle(binding, original), "settle recovered " + original.commandId)
		check(store.read(binding).is_empty() and store.healthy, "all recovered records settled")
	elif mode == "legacy":
		var original = record("legacy_original")
		write_json(state_path, {binding: original})
		var legacy_bytes = FileAccess.get_file_as_bytes(state_path)
		var second_binding = "other-actor".sha256_text()
		var second = record("other_actor", "a2")
		check(store.read(binding).get(original.commandId) == original, "read original aggregate")
		check(store.put(second_binding, second), "other actor persists separately")
		check(store.settle(second_binding, second), "other actor settles separately")
		var restarted = Store.new(state_path, validator._valid_record)
		check(restarted.read(binding).get(original.commandId) == original, "restart still finds original actor")
		check(restarted.settle(binding, original), "settle original legacy entry")
		var again = Store.new(state_path, validator._valid_record)
		check(again.read(binding).is_empty() and again.healthy, "settled legacy command does not reappear")
		check(FileAccess.get_file_as_bytes(state_path) == legacy_bytes, "legacy file remains unchanged")
	elif mode == "conflict":
		var original = record("original")
		check(store.put(binding, original), "save original command")
		var altered = original.duplicate(true)
		altered.body = altered.body.replace('[6,7]', '[8,7]')
		check(not store.put(binding, altered), "reject changed body for same command")
		var restarted = Store.new(state_path, validator._valid_record)
		check(restarted.read(binding).get(original.commandId) == original, "conflict preserves original")
	elif mode == "corrupt":
		var original = record("corrupt")
		check(store.put(binding, original), "save before corruption")
		var filename = state_path + ".d/" + binding + "/" + original.commandId.sha256_text() + ".json"
		write_json(filename, {"version": 99, "binding": binding, "record": original})
		var restarted = Store.new(state_path, validator._valid_record)
		restarted.read(binding)
		check(not restarted.healthy, "unknown record schema pauses recovery")
	else:
		check(false, "unknown test mode")
	write_json(OS.get_environment("RECOVERY_OUTPUT"), {"passed": failures == 0, "checks": checks})
	validator.free()
	quit(0 if failures == 0 else 1)
