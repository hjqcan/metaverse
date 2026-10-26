extends SceneTree
## Uses the actual adapter and on-disk journal; the Python proxy controls transport loss.
const Client = preload("res://world_client.gd")
var checks: Array = []
var client: Node

func _initialize() -> void:
	call_deferred("run")

func check(ok: bool, label: String) -> void:
	checks.append({"name": label, "passed": ok})
	if not ok:
		push_error(label)

func run() -> void:
	var mode := OS.get_environment("GODOT_TEST_MODE")
	var output := OS.get_environment("GODOT_TEST_OUTPUT")
	var action = JSON.parse_string(OS.get_environment("WORKSHOP_TEST_ACTION"))
	var access = JSON.parse_string(FileAccess.get_file_as_string(OS.get_environment("WORLD_ACCESS_FILE")))
	client = Client.new()
	root.add_child(client)
	# Environment JSON uses Godot floats; restore protocol integer fields as the
	# actual UI does before producing a strict command body.
	action = client._integer_fields(action)
	await client.connect_world(OS.get_environment("WORLD_URL"), access.sessions.a2.token)
	if mode == "hold":
		check(not client.healthy and not client.can_act(), "unknown furniture capability pauses native adapter")
	elif mode == "return":
		if not client.pending.is_empty():
			await client.recover(true)
		check(client.can_act() and client.pending.is_empty(), "restarted native adapter settles original command")
		check(client.last_receipt.get("commandId") == OS.get_environment("WORKSHOP_TEST_COMMAND"), "original command ID survives process restart")
		check(client.last_receipt.get("result", {}).get("action") == action.type, "original action survives process restart")
		check(client.pending_store.read(client._key()).is_empty(), "original disk journal settles")
		if action.type != "walk":
			var detail = client.last_receipt.get("result", {}).get("workshopAction", {})
			check(detail.get("action") == action and detail.get("authorActorId") == "a2", "original action and author proven by three responses")
			if action.type in ["deposit_wood", "withdraw_wood"]:
				check(detail.get("quantity") == action.quantity, "original transfer quantity retained")
	else:
		check(client.healthy, "native adapter observes the actual world")
		await client.send_action(action)
		check(not client.pending.is_empty() and not client.can_act(), "lost or corrupted evidence retains unresolved original")
		if not client.pending.is_empty():
			var record: Dictionary = client.pending.duplicate(true)
			var original: String = record.body
			check(record.recordVersion == (4 if action.type == "walk" else 6), "action uses its own compatible journal format")
			check(client._valid_record(JSON.parse_string(JSON.stringify(record))), "journal validates after numeric JSON roundtrip")
			check(client.pending_store.other_worlds(client.endpoint, "a2", "w_" + "0".repeat(32)) == 1, "original remains discoverable after switching world")
			record.actorId = "a1"
			check(not client._valid_record(record) if action.type != "walk" else true, "workshop original author cannot be replaced")
			if action.type != "walk":
				record = client.pending.duplicate(true)
				record.recordVersion = 4
				check(not client._valid_record(record), "new action cannot masquerade as legacy format")
			check(client.pending.body == original, "validation preserves original serialized request")
	var passed: bool = checks.all(func(c): return c.passed)
	var file := FileAccess.open(output, FileAccess.WRITE)
	file.store_string(JSON.stringify({"passed": passed, "checks": checks, "pending": client.pending, "receipt": client.last_receipt}, "  "))
	file.close()
	quit(0 if passed else 1)
