extends SceneTree
const Client = preload("res://world_client.gd")
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
	for i in 600:
		await create_timer(0.02).timeout
		if not client.busy:
			return
	check(false, "HTTP deadline")

func click(button: Control) -> void:
	await idle()
	app.poll_time = 0
	await process_frame
	var point = button.get_global_rect().get_center()
	var motion = InputEventMouseMotion.new()
	motion.position = point
	motion.global_position = point
	Input.parse_input_event(motion)
	await process_frame
	print("UI click ", button.name, " ", button.get_global_rect(), " disabled=", button.disabled, " visible=", button.is_visible_in_tree())
	var event = InputEventMouseButton.new()
	event.position = point
	event.global_position = event.position
	event.button_index = MOUSE_BUTTON_LEFT
	event.pressed = true
	Input.parse_input_event(event)
	await process_frame
	event = event.duplicate()
	event.pressed = false
	Input.parse_input_event(event)
	await process_frame
	await idle()

func key(pressed: bool) -> void:
	var event = InputEventKey.new()
	event.keycode = KEY_D
	event.physical_keycode = KEY_D
	event.pressed = pressed
	Input.parse_input_event(event)
	await process_frame

func screenshot(name: String) -> void:
	await process_frame
	await RenderingServer.frame_post_draw
	check(root.get_texture().get_image().save_png(output + "-" + name + ".png") == OK, "rendered " + name)

func run() -> void:
	output = OS.get_environment("GODOT_TEST_OUTPUT")
	var mode = OS.get_environment("GODOT_TEST_MODE")
	var access = JSON.parse_string(FileAccess.get_file_as_string(OS.get_environment("WORLD_ACCESS_FILE")))
	if mode in ["ui", "incoming"]:
		app = load("res://main.tscn").instantiate()
		root.add_child(app)
		client = app.client
		await idle()
		await create_timer(0.4).timeout
		await idle()
		check(client.healthy and client.observation.rulesVersion == "r9", "native r9 world authenticated")
		if mode == "ui":
			check(app.transfer_button.visible and not app.transfer_button.disabled, "gift entry advertised")
			await click(app.transfer_button)
			check(app.transfer_panel.visible, "actual mouse opens recipient and amount")
			app.transfer_panel.quantity.value = 3
			check(app.transfer_panel.recipient.get_item_metadata(app.transfer_panel.recipient.selected) == "a2", "recipient explicitly displayed as a2")
			await screenshot("gift-choice")
			await click(app.transfer_panel.send_button)
			check(client.pending.is_empty() and client.last_receipt.get("result", {}).get("action") == "transfer", "actual submit settles gift receipt")
			check(client.observation.self.inventory.wood == 3 and "你 → a2 · 3 木材" in app.transfer_history.text, "sender sees completed delivery distinct from construction")
			await app._connect(client.endpoint, access.sessions.a2.token)
			await idle()
			check(client.observation.self.inventory.wood == 3 and "a1 → 你 · 3 木材" in app.transfer_history.text, "recipient sees the actual source event")
			app._begin_build("platform.v1")
			await app._clicked(Vector2(28, 16), "")
			await idle()
			check(client.last_receipt.get("result", {}).get("action") == "build" and client.observation.self.inventory.wood == 0, "recipient uses delivered material for own platform")
			var built = client.observation.entities.filter(func(e): return e.definitionId == "platform")
			check(built.size() == 1 and built[0].ownerActorId == "a2", "construction belongs to its actual recipient builder")
			await screenshot("recipient-built")
		else:
			await app._connect(client.endpoint, access.sessions.a2.token)
			await idle()
			await create_timer(.15).timeout
			await key(true)
			await create_timer(1).timeout
			await idle()
			check(client.last_receipt.get("error", {}).get("code") == "STALE_ACTOR_STATE", "incoming gift rejects recipient old walk")
			var version = client.observation.stateVersion
			await create_timer(0.8).timeout
			await idle()
			check(client.observation.stateVersion == version and app.input_suspended, "held input stays stopped without renewed command")
			check("a1 → 你 · 3 木材" in app.transfer_history.text, "receipt rejection does not hide actual incoming material")
			await key(false)
			await create_timer(.1).timeout
			await key(true)
			await create_timer(.25).timeout
			await key(false)
			await idle()
			check(client.observation.stateVersion > version, "fresh user input may proceed")
	else:
		client = Client.new()
		root.add_child(client)
		await client.connect_world(OS.get_environment("WORLD_URL"), access.sessions.a1.token)
		if mode.ends_with("-return"):
			if not client.pending.is_empty():
				await client.recover(true)
			check(client.pending.is_empty() and client.observation.self.inventory.wood == 3, "fresh process recovers original gift exactly once")
		else:
			check(client.healthy, "r9 adapter authenticated")
			await client.send_action({"type": "transfer", "recipientActorId": "a2", "resource": "wood", "quantity": 3})
			check(client.pending.get("recordVersion") == 3 and not client.can_act(), "unknown gift preserves original v3 record")
			if mode == "corrupt":
				var original: String = client.pending.body
				var reply: Dictionary = await client._request(client.API + "/commands/" + client.pending.commandId)
				for field in ["senderActorId", "recipientActorId", "quantity", "resource", "inventoryWood"]:
					var wrong = reply.duplicate(true)
					wrong.data.result.erase(field)
					check(not await client._settle(wrong) and client.pending.body == original, "missing " + field + " cannot settle")
				var wrong = reply.duplicate(true)
				wrong.data.rulesVersion = "r8"
				check(not await client._settle(wrong), "other accepted rule version cannot settle original r9")
				wrong = reply.duplicate(true)
				wrong.data.result.quantity = true
				check(not await client._settle(wrong), "boolean amount is not transfer evidence")
				wrong = reply.duplicate(true)
				wrong.data.erase("execution")
				check(not await client._settle(wrong), "missing execution retains original")
				var record: Dictionary = client.pending.duplicate(true)
				var before = JSON.parse_string(record.before)
				before.senderActorId = "a2"
				record.before = JSON.stringify(before)
				check(not client._valid_record(record), "saved sender cannot disagree with original actor")
				record = client.pending.duplicate(true)
				before = JSON.parse_string(record.before)
				before.inventoryWood = 2
				record.before = JSON.stringify(before)
				check(not client._valid_record(record), "saved inventory must have funded the original gift")
				await client.recover()
				check(client.pending.is_empty() and client.observation.self.inventory.wood == 3, "authoritative original receipt settles once")
	var passed = checks.all(func(item): return item.passed)
	var file = FileAccess.open(output + ".json", FileAccess.WRITE)
	file.store_string(JSON.stringify({"passed": passed, "checks": checks}, "  "))
	file.close()
	quit(0 if passed else 1)
