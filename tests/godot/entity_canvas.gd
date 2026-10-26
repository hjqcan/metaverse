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

func tiles() -> Array:
	return app.world_view.objects.get_children().filter(func(n): return n.has_meta("canvas_cell"))

func run() -> void:
	output = OS.get_environment("GODOT_TEST_OUTPUT")
	var mode = OS.get_environment("GODOT_TEST_MODE")
	var access = JSON.parse_string(FileAccess.get_file_as_string(OS.get_environment("WORLD_ACCESS_FILE")))
	if mode == "ui":
		app = load("res://main.tscn").instantiate()
		root.add_child(app)
		client = app.client
		await idle()
		await app._connect(client.endpoint, access.sessions.a1_alias.token)
		await idle()
		check(client.healthy and app.canvas_button.visible, "native client validates original platform capability")
		check(tiles().size() == 25 and tiles().all(func(n): return n.get_meta("canvas_color") == "blank"), "actual blank 5 by 5 platform surface")
		var entities: Array = client.observation.entities.duplicate(true)
		var target: Array = client.observation.entityCanvas.target.position
		app.world_view.focus = Vector3(target[0], 0, target[1])
		app.world_view.zoom = 9.0
		await click(app.canvas_button)
		check(app.canvas_panel.visible, "mouse opens platform canvas panel")
		await screenshot("blank")
		await click(app.canvas_panel.cells[6])
		check(app.canvas_panel.draft.size() == 1 and client.observation.entityCanvas.revision == 0, "mouse changes local draft without submitting")
		app.canvas_panel.close_panel()
		await click(app.canvas_button)
		check(app.canvas_panel.draft.size() == 1, "closing panel preserves local draft without sending")
		check(not app.canvas_panel.send_button.disabled and client.observation.self.inventory.wood == 0, "zero inventory resident may submit near platform")
		await screenshot("draft")
		await click(app.canvas_panel.send_button)
		check(client.pending.is_empty() and client.last_receipt.get("result", {}).get("action") == "paint_entity_canvas", "mouse submit settles receipt event and exact edit")
		check(app.canvas_panel.status.text.begins_with("已确认本次绘制"), "confirmed edit distinct from draft")
		check(tiles().filter(func(n): return n.get_meta("canvas_color") == "river").size() == 1, "actual surface refreshed when entity list did not change")
		check(client.observation.entities == entities, "painting preserves original entity and builder")
		await screenshot("first")
		await app._connect(client.endpoint, access.sessions.a2.token)
		await idle()
		await click(app.canvas_button)
		check(app.canvas_panel.draft.is_empty() and app.canvas_panel.cells[6].disabled, "next resident sees original author and cannot overwrite it")
		var scroll: ScrollContainer = app.canvas_panel.palette_buttons[3].get_parent().get_parent().get_parent()
		scroll.ensure_control_visible(app.canvas_panel.palette_buttons[3])
		await process_frame
		await click(app.canvas_panel.palette_buttons[3])
		check(app.canvas_panel.selected == "sun", "actual palette mouse input selects sun")
		scroll.scroll_vertical = 0
		await process_frame
		await click(app.canvas_panel.cells[8])
		await click(app.canvas_panel.send_button)
		check(client.pending.is_empty() and client.observation.entityCanvas.revision == 2, "second resident explicitly paints an empty cell")
		check(not app.canvas_panel.legend.text.contains("未提交"), "confirmed cell description clears old draft label")
		check(tiles().filter(func(n): return n.get_meta("canvas_author") == "a1_alias").size() == 1 \
			and tiles().filter(func(n): return n.get_meta("canvas_author") == "a2").size() == 1, "rendered original and new authors both remain")
		await screenshot("both")
		# A new shared revision preserves a local draft until explicit new input.
		app.set_physics_process(false)
		await click(app.canvas_panel.cells[9])
		var changed: Dictionary = client.observation.duplicate(true)
		changed.entityCanvas.revision += 1
		changed.entityCanvas.editCount += 1
		var edit: Dictionary = changed.entityCanvas.recentEdits[-1].duplicate(true)
		edit.baseRevision += 1
		edit.revision += 1
		changed.entityCanvas.recentEdits.append(edit)
		app.canvas_panel.update_world(changed, true, {}, {}, client.connection_generation)
		check(app.canvas_panel.draft.size() == 1 and app.canvas_panel.send_button.disabled, "new shared revision preserves stale draft and disables submit")
		await click(app.canvas_panel.reset_button)
		check(app.canvas_panel.draft.is_empty() and app.canvas_panel.base_revision == 3, "explicit new draft accepts fresh revision")
	else:
		client = Client.new()
		root.add_child(client)
		await client.connect_world(OS.get_environment("WORLD_URL"), access.sessions.a1_alias.token)
		if mode == "return":
			if not client.pending.is_empty():
				await client.recover(true)
			check(client.can_act() and client.pending.is_empty(), "restarted adapter confirms original immutable edit")
			check(client.last_receipt.get("result", {}).get("baseRevision") == 0 and client.last_receipt.get("result", {}).get("patch", [{}])[0].get("color") == "river", "original success retained even after later current picture changes")
			check(client.pending_store.read(client._key()).is_empty(), "original disk pending settled")
			if not Client.Evidence.Canvas.supported(client.observation):
				await client.send_action({"type":"paint_entity_canvas", "entityId":client.last_receipt.result.entityId,
					"capabilityVersion":1, "expectedCanvasRevision":1, "patch":[{"x":2,"y":2,"color":"sun"}]})
				check(client.pending.is_empty() and client.last_receipt.result.baseRevision == 0, "unknown current capability cannot authorize a new paint")
		else:
			check(client.healthy and Client.Evidence.Canvas.supported(client.observation), "actual capability fully validated")
			var malformed: Dictionary = client.observation.duplicate(true)
			malformed.entities = []
			check(not Client.Evidence.Canvas.supported(malformed), "capability cannot replace original platform")
			await client.send_action({"type":"paint_entity_canvas", "entityId":client.observation.entityCanvas.target.entityId,
				"capabilityVersion":1, "expectedCanvasRevision":0, "patch":[{"x":1,"y":1,"color":"river"}]})
			check(not client.pending.is_empty() and not client.can_act(), "missing or damaged evidence preserves pending")
			check(client.pending.recordVersion == 5 and client._valid_record(JSON.parse_string(JSON.stringify(client.pending))), "original version 5 paint record survives JSON reload")
			check(client.pending_store.other_worlds(client.endpoint, "a1_alias", "w_" + "0".repeat(32)) == 1, "version 5 original remains visible when connecting to another world")
			var original: String = client.pending.body
			var record: Dictionary = client.pending.duplicate(true)
			var before = JSON.parse_string(record.before)
			before.canvasPatch[0].color = "sun"
			record.before = JSON.stringify(before)
			check(not client._valid_record(record), "changed frozen patch rejected")
			record = client.pending.duplicate(true)
			record.recordVersion = 4
			check(not client._valid_record(record), "new paint cannot masquerade as old record format")
			check(client.pending.body == original, "validation never replaces original body")
	var passed = checks.all(func(c): return c.passed)
	var file = FileAccess.open(output + ".json", FileAccess.WRITE)
	file.store_string(JSON.stringify({"passed":passed,"checks":checks}, "  "))
	file.close()
	quit(0 if passed else 1)
