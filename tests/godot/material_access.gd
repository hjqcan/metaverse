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
	for i in 700:
		await create_timer(0.02).timeout
		if not client.busy:
			return
	check(false, "HTTP deadline")

func click(button: Control) -> void:
	await idle()
	app.poll_time = 0
	await process_frame
	var point = button.get_global_rect().get_center()
	var motion := InputEventMouseMotion.new()
	motion.position = point
	motion.global_position = point
	Input.parse_input_event(motion)
	await process_frame
	var event := InputEventMouseButton.new()
	event.position = point
	event.global_position = point
	event.button_index = MOUSE_BUTTON_LEFT
	event.pressed = true
	Input.parse_input_event(event)
	await process_frame
	event = event.duplicate()
	event.pressed = false
	Input.parse_input_event(event)
	await process_frame
	await idle()

func screenshot(name: String) -> void:
	await process_frame
	await RenderingServer.frame_post_draw
	check(root.get_texture().get_image().save_png(output + "-" + name + ".png") == OK, "rendered " + name)

func run() -> void:
	output = OS.get_environment("GODOT_TEST_OUTPUT")
	var mode = OS.get_environment("GODOT_TEST_MODE")
	var access = JSON.parse_string(FileAccess.get_file_as_string(OS.get_environment("WORLD_ACCESS_FILE")))
	if mode == "ui":
		app = load("res://main.tscn").instantiate()
		root.add_child(app)
		client = app.client
		await idle()
		await app._connect(client.endpoint, access.sessions.a3.token)
		await idle()
		check(client.healthy and client.observation.rulesVersion == "r10", "actual r10 adapter authenticated")
		check(app.material_panel.visible and not app.material_panel.request_button.disabled, "source request shown for unfunded resident")
		check(not app._placement_valid(Vector2(28,10), "platform.v1"), "empty source footprint excluded in placement preview")
		await click(app.material_panel.request_button)
		check(client.pending.is_empty() and client.last_receipt.get("result", {}).get("action") == "reserve_material", "mouse request settled through original event")
		var reservation_id: String = client.last_receipt.result.reservationId
		await screenshot("queued")
		for i in 180:
			var r = client.observation.materialAccess.currentReservation
			if r is Dictionary and r.get("status") == "active":
				break
			await create_timer(.1).timeout
			await idle()
		check(client.observation.materialAccess.currentReservation.get("status") == "active", "real production grants original reservation")
		check(client.observation.materialAccess.currentReservation.reservationId == reservation_id, "grant keeps original reservation identity")
		await click(app.material_panel.travel_button)
		for i in 200:
			if app.position_2d().distance_to(Vector2(28,10)) < .06 and not app.walking:
				break
			await create_timer(.05).timeout
		await idle()
		check(app.position_2d().distance_to(Vector2(28,10)) < .06, "actual walk reaches nonblocking source")
		for i in 3:
			check(not app.material_panel.harvest_button.disabled, "harvest button enabled for original owner %d" % i)
			await click(app.material_panel.harvest_button)
			check(client.pending.is_empty() and client.last_receipt.get("result", {}).get("action") == "harvest_material", "harvest receipt settled %d" % i)
		check(client.observation.self.inventory.wood == 3, "three actual harvests fund own construction")
		await app._begin_build("platform.v1")
		await app._clicked(Vector2(30,10), "")
		await idle()
		check(client.last_receipt.get("result", {}).get("action") == "build" and client.observation.self.inventory.wood == 0, "original builder uses source wood for platform")
		check(client.can_act() and client.pending.is_empty() and client.pending_store.read(client._key()).is_empty(), "completed build clears durable original and restores controls")
		await client.refresh()
		check(client.can_act() and not app.query_button.visible, "fresh observation keeps completed client ready")
		var entity = client.observation.entities.filter(func(e): return e.definitionId == "platform")
		check(entity.size() == 1 and entity[0].ownerActorId == "a3", "platform author confirmed from actual observation")
		check(not app._placement_valid(Vector2(28,10), "platform.v1"), "source reservation remains after stock consumed")
		await screenshot("built")
	else:
		client = Client.new()
		root.add_child(client)
		await client.connect_world(OS.get_environment("WORLD_URL"), access.sessions.a3.token)
		var kind: String = mode.split("-")[0]
		if mode.ends_with("-return"):
			if not client.pending.is_empty():
				await client.recover(true)
			check(client.can_act() and client.pending.is_empty() and client.pending_store.read(client._key()).is_empty(), "fresh client settles original r10 action and disk record")
			if kind == "harvest":
				check(client.observation.self.inventory.wood == 1, "interrupted harvest occurs exactly once")
			elif kind == "reserve":
				check(client.observation.materialAccess.currentReservation is Dictionary, "original request retained one qualification")
			else:
				check(client.observation.materialAccess.currentReservation == null, "original cancellation retained")
		else:
			check(client.healthy, "r10 native adapter connected")
			var action: Dictionary = {"type": "reserve_material", "sourceId": "wood-source-east"}
			if kind != "reserve":
				action = {"type": "harvest_material" if kind == "harvest" else "cancel_reservation", "reservationId": client.observation.materialAccess.currentReservation.reservationId}
			await client.send_action(action)
			check(client.pending.get("recordVersion") == 4 and not client.can_act(), "unknown r10 action keeps version4 original record")
			check(client._valid_record(JSON.parse_string(JSON.stringify(client.pending))), "version4 record remains valid after disk JSON number conversion")
			if mode.ends_with("corrupt"):
				var original: String = client.pending.body
				var reply: Dictionary = await client._request(client.API + "/commands/" + client.pending.commandId)
				var fields: Array = ["sourceId", "reservationId", "queueSequence", "requestedAtMs"] if kind == "reserve" else ["sourceId", "reservationId", "remainingBefore", "remaining", "inventoryWoodBefore", "inventoryWood"]
				for field in fields:
					var wrong = reply.duplicate(true)
					wrong.data.result.erase(field)
					check(not await client._settle(wrong) and client.pending.body == original, "missing " + field + " retains original")
				var wrong = reply.duplicate(true)
				wrong.data.result.reservationId = "m_wrong"
				check(not await client._settle(wrong) and client.pending.body == original, "unrelated reservation cannot settle original")
				var record = client.pending.duplicate(true)
				record.recordVersion = 3
				check(not client._valid_record(record), "r10 record cannot masquerade as old record format")
				record = client.pending.duplicate(true)
				var before = JSON.parse_string(record.before)
				before.materialActorId = "a2"
				record.before = JSON.stringify(before)
				check(not client._valid_record(record), "original actor bound into source evidence")
				await client.recover()
				check(client.can_act() and client.pending.is_empty(), "original authoritative receipt and reference settle")
	var passed: bool = not checks.is_empty() and checks.all(func(item): return item.passed)
	var file := FileAccess.open(output + ".json", FileAccess.WRITE)
	file.store_string(JSON.stringify({"passed": passed, "checks": checks}, "  "))
	file.close()
	quit(0 if passed else 1)
