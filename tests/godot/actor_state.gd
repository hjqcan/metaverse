extends SceneTree
const Evidence = preload("res://command_evidence.gd")
var checks: Array = []
var app: Node
var client: Node
var output: String

func _initialize() -> void:
	call_deferred("run")
func check(ok: bool, label: String) -> void:
	checks.append({"name": label, "passed": ok})
	if not ok:
		push_error(label)
func idle() -> void:
	for i in 500:
		await create_timer(0.02).timeout
		if not client.busy:
			return
	check(false, "HTTP deadline")
func key(pressed: bool) -> void:
	var event = InputEventKey.new()
	event.physical_keycode = KEY_W
	event.keycode = KEY_W
	event.pressed = pressed
	Input.parse_input_event(event)
	await process_frame
func finish() -> void:
	var passed = checks.all(func(item): return item.passed)
	var file = FileAccess.open(output+".json", FileAccess.WRITE)
	file.store_string(JSON.stringify({"passed": passed, "checks": checks}, "  "))
	file.close()
	quit(0 if passed else 1)
func run() -> void:
	output = OS.get_environment("GODOT_TEST_OUTPUT")
	var mode = OS.get_environment("GODOT_TEST_MODE")
	if mode in ["held", "route"]:
		app = load("res://main.tscn").instantiate()
		root.add_child(app)
		client = app.client
		await idle()
		await create_timer(0.5).timeout
		check(client.healthy, "authenticated native app")
		if mode == "held":
			await key(true)
		else:
			await app._clicked(Vector2(4, 6), "")
		await create_timer(1.2).timeout
		await idle()
		check(client.last_receipt.get("error", {}).get("code") == "STALE_ACTOR_STATE", "same actor later success rejects old input")
		check(client.pending.is_empty() and not app.walking and not app.planning, "confirmed conflict settles and cancels route")
		var version = client.observation.stateVersion
		await create_timer(0.7).timeout
		await idle()
		check(client.observation.stateVersion == version, "old intent cannot silently resume")
		if mode == "held":
			check(app.input_suspended, "held key remains suspended")
			await key(false)
			await create_timer(0.1).timeout
			await key(true)
			await create_timer(0.25).timeout
			await key(false)
		else:
			await app._clicked(Vector2(4, 6), "")
			await create_timer(0.5).timeout
			app._stop_walk()
		await idle()
		check(client.observation.stateVersion > version, "explicit new input resumes")
	else:
		client = load("res://world_client.gd").new()
		root.add_child(client)
		var access = JSON.parse_string(FileAccess.get_file_as_string(OS.get_environment("WORLD_ACCESS_FILE")))
		await client.connect_world(OS.get_environment("WORLD_URL"), access.sessions.a1.token)
		if mode == "strict-return":
			check(client.pending.get("recordVersion") == 2, "old strict v2 preserved despite new capability")
			check(not JSON.parse_string(client.pending.body).has("preconditionMode"), "saved strict body not upgraded")
			await client.recover(true)
			check(client.pending.is_empty() and client.observation.self.inventory.wood == 1, "original strict retry commits once")
		else:
			check(client.healthy, "authenticated observation")
			await client.send_action({"type": "gather", "nodeId": "tree-west-north"})
			if mode == "unrelated":
				check(client.pending.is_empty() and client.observation.self.inventory.wood == 1, "unrelated real walk permits original gather")
				check(client.last_receipt.execution.appliedOnStateVersion > client.last_receipt.execution.observedStateVersion, "actual application exceeds frozen anchor")
			elif mode == "strict-save":
				check(client.pending.get("recordVersion") == 2 and not client.can_act(), "old server capability creates strict v2")
			else:
				check(client.pending.get("recordVersion") == 3 and not client.can_act(), "forged receipt retains v3 original")
				var original: String = client.pending.body
				var damaged = client.pending.duplicate(true)
				damaged.before = '{"position":null,"inventoryWood":0,"nodePosition":[6.2,7.8],"remainingWood":3}'
				check(not client._valid_record(damaged), "damaged before facts rejected before network")
				await client.recover()
				check(client.pending.is_empty() and client.observation.self.inventory.wood == 1, "valid lookup settles original exactly once")
				check(client.last_receipt.commandId == JSON.parse_string(original).commandId, "recovered original ID")
	# A past transaction cannot reject a future observation for a normal business reason.
	var command = {"preconditionMode": Evidence.MODE, "expectedStateVersion": 42}
	var refusal = {"stateVersion": 0, "execution": {"preconditionMode": Evidence.MODE, "observedStateVersion": 42, "appliedOnStateVersion": 0}, "error": {"code": "RESOURCE_DEPLETED"}}
	check(not Evidence.execution(refusal, command, false), "impossible past business rejection is not evidence")
	refusal.error.code = "STATE_VERSION_AHEAD"
	check(Evidence.execution(refusal, command, false), "genuine future anchor rejection remains valid")
	finish()
