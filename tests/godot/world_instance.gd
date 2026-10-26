extends SceneTree
## Process-boundary regression: a saved original never follows a replacement DB.
var client: Node
var checks: Array = []
var output = OS.get_environment("INSTANCE_TEST_OUTPUT")

func _initialize() -> void:
	call_deferred("run")

func check(condition: bool, label: String) -> void:
	checks.append({"name": label, "passed": condition})
	if not condition:
		push_error(label)

func run() -> void:
	client = load("res://world_client.gd").new()
	root.add_child(client)
	var access = JSON.parse_string(FileAccess.get_file_as_string(OS.get_environment("INSTANCE_TEST_ACCESS")))
	var token: String = access.sessions.a1.token if access.has("sessions") else access.token
	var mode = OS.get_environment("INSTANCE_TEST_MODE")
	await client.connect_world(OS.get_environment("WORLD_URL"), token)
	if mode == "save":
		check(client.can_act() and not client.instance_id.is_empty(), "new world establishes instance binding")
		await client.send_action({"type": "gather", "nodeId": "tree-west-north"})
		check(not client.pending.is_empty() and not client.can_act(), "lost response retains original protected record")
		check(client.pending.get("recordVersion") == 2 and client.pending.get("instanceId") == client.instance_id, "original freezes persistent world identity")
		var saved = FileAccess.open(OS.get_environment("INSTANCE_TEST_ORIGINAL"), FileAccess.WRITE)
		saved.store_string(JSON.stringify(client.pending))
		saved.close()
	elif mode == "replacement":
		var original = JSON.parse_string(FileAccess.get_file_as_string(OS.get_environment("INSTANCE_TEST_ORIGINAL")))
		check(client.instance_id != original.instanceId, "same endpoint identifies a different world")
		check(client.pending.is_empty() and client.foreign_pending == 1, "replacement does not load original but reports its retained record")
		await client.recover(true)
		check(client.observation.self.inventory.wood == 0 and client.last_receipt.is_empty(), "recovery sends no original action to replacement")
		check(client.can_act(), "explicitly connected replacement can use its own independent records")
	elif mode == "return":
		var original = JSON.parse_string(FileAccess.get_file_as_string(OS.get_environment("INSTANCE_TEST_ORIGINAL")))
		check(client.instance_id == original.instanceId, "relocated original keeps its identity after token rotation")
		if not client.pending.is_empty():
			check(client.pending.commandId == original.commandId and client.pending.body == original.body, "unsubmitted original stays byte-identical")
			await client.recover(true)
		check(client.pending.is_empty() and client.can_act(), "original world resolves the original command")
		check(client.last_receipt.commandId == original.commandId and client.observation.self.inventory.wood == 1, "original command has exactly one material effect")
	elif mode == "legacy":
		check(client.legacy_unbound and not client.can_act(), "old unbound pending is not adopted into protected world")
		await client.recover(true)
		await client.send_action({"type": "gather", "nodeId": "tree-west-north"})
		check(client.last_receipt.is_empty() and client.observation.self.inventory.wood == 0, "legacy barrier cannot send a replacement command")
	elif mode == "corrupt":
		check(not client.storage_ok and not client.can_act(), "protected format missing instance is corruption, not legacy")
		await client.send_action({"type": "gather", "nodeId": "tree-west-north"})
		check(client.last_receipt.is_empty(), "corrupt protected record prevents replacement action")
	else:
		check(false, "known test mode")
	var passed = checks.all(func(item): return item.passed)
	var file = FileAccess.open(output, FileAccess.WRITE)
	file.store_string(JSON.stringify({"passed": passed, "checks": checks}, "  "))
	file.close()
	quit(0 if passed else 1)
