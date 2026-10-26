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
		await create_timer(.02).timeout
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
	var event = InputEventMouseButton.new()
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
		await app._connect(client.endpoint, access.sessions.a2.token)
		await idle()
		check(client.healthy and client.observation.materialAccess.version == 2, "native adapter accepts adopted original r10 world")
		check(client.observation.entities.size() == 5 and client.observation.entityNotes.totalCount == 2, "five original entities and two old notes visible")
		var notes: Array = client.observation.entityNotes.notes.duplicate(true)
		check(app.material_panel.summary.text.contains("累计产出") and app.material_panel.summary.text.contains("每10服务秒最多产3") \
			and not app.material_panel.summary.text.contains("剩余来源额度"), "continuous UI distinguishes stock rate and cumulative production")
		check(not app.material_panel.request_button.disabled, "exhausted original lifetime budget no longer disables new explicit request")
		await click(app.notes_button)
		check(app.notes_panel.visible and app.notes_panel.entries.get_children().size() >= 2, "old bridge notes readable through actual panel")
		check(notes[1].replyToNoteId == notes[0].noteId, "original reference preserved")
		await screenshot("old-notes")
		app.notes_panel.close_panel()
		await click(app.material_panel.request_button)
		check(client.pending.is_empty() and client.last_receipt.get("result", {}).get("action") == "reserve_material", "mouse request confirms original receipt and event")
		var rid: String = client.last_receipt.result.reservationId
		for i in 160:
			await create_timer(.1).timeout
			await idle()
			if client.observation.materialAccess.currentReservation.get("status") == "active":
				break
		check(client.observation.materialAccess.currentReservation.reservationId == rid \
			and client.observation.materialAccess.currentReservation.status == "active", "real service production grants original request")
		await click(app.material_panel.travel_button)
		for i in 500:
			await create_timer(.05).timeout
			if app.position_2d().distance_to(Vector2(28,10)) < .06 and not app.walking:
				break
		await idle()
		check(app.position_2d().distance_to(Vector2(28,10)) < .06, "actual late resident walks to source")
		for i in 3:
			check(not app.material_panel.harvest_button.disabled, "own original harvest enabled %d" % i)
			await click(app.material_panel.harvest_button)
			check(client.pending.is_empty() and client.last_receipt.get("result", {}).get("action") == "harvest_material", "actual harvest confirmed %d" % i)
		check(client.observation.self.inventory.wood == 3, "three actual source units in late resident inventory")
		await app._begin_build("platform.v1")
		await app._clicked(Vector2(30,10), "")
		await idle()
		check(client.pending.is_empty() and client.last_receipt.get("result", {}).get("action") == "build", "actual fifth platform build confirmed")
		check(client.observation.entities.size() == 6 and client.observation.self.inventory.wood == 0, "new platform consumes three units while old entities remain")
		check(client.observation.entities.filter(func(e): return e.definitionId == "platform" and e.ownerActorId == "a2").size() == 1, "new platform belongs to late resident")
		check(client.observation.entityNotes.notes == notes, "material actions preserve original note text author and reference")
		app.set_process(false)
		await idle()
		await client.refresh()
		check(client.can_act() and not app.query_button.visible and not app.material_panel.request_button.disabled, "completed original restores controls for next explicit action")
		await screenshot("built")
	else:
		client = Client.new()
		root.add_child(client)
		await client.connect_world(OS.get_environment("WORLD_URL"), access.sessions.a2.token)
		if mode == "return":
			if not client.pending.is_empty():
				await client.recover(true)
			check(client.can_act() and client.pending.is_empty(), "restarted native adapter settles original material request")
			check(client.pending_store.read(client._key()).is_empty(), "original pending disk record settles")
			check(client.observation.materialAccess.currentReservation is Dictionary, "same original qualification observed")
		elif mode == "policy":
			check(client.healthy and Client.Evidence.material_supported(client.observation), "complete policy accepted from real service")
			for field in ["id", "version", "adoptedAtServiceMs", "adoptedAtStateVersion", "adoptedAtEventCursor", "generatedWoodAtAdoption", "productionPeriodAtAdoption"]:
				var wrong = client.observation.duplicate(true)
				wrong.materialAccess.productionPolicy.erase(field)
				check(not client._valid_observation(wrong), "missing policy " + field + " pauses observation")
			var wrong = client.observation.duplicate(true)
			wrong.materialAccess.inputBudget = 12
			check(not client._valid_observation(wrong), "v2 cannot masquerade as finite lifetime budget")
			wrong = client.observation.duplicate(true)
			wrong.materialAccess.version = 1
			check(not client._valid_observation(wrong), "v1 cannot silently carry adopted policy")
			wrong = client.observation.duplicate(true)
			wrong.materialAccess.productionPolicy.adoptedAtServiceMs = wrong.materialAccess.serviceMs + 1
			check(not client._valid_observation(wrong), "future adoption clock cannot pass current capability")
			check(client.observation.entityNotes.totalCount == 2 and Client.Evidence.Notes.supported(client.observation), "notes capability continues in adopted material world")
		else:
			check(client.healthy, "actual policy adapter authenticated")
			await client.send_action({"type":"reserve_material", "sourceId":"wood-source-east"})
			check(not client.pending.is_empty() and client.pending.recordVersion == 4, "unknown request retains shared original v4 record")
			check(client._valid_record(JSON.parse_string(JSON.stringify(client.pending))), "unchanged r10 body and before facts remain recoverable")
	var passed = not checks.is_empty() and checks.all(func(c): return c.passed)
	var file = FileAccess.open(output + ".json", FileAccess.WRITE)
	file.store_string(JSON.stringify({"passed":passed,"checks":checks}, "  "))
	file.close()
	quit(0 if passed else 1)
