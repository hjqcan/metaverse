extends SceneTree
## Runs the actual scene and adapter against an isolated real World.Server.
var app: Node
var checks: Array = []
var output: String

func _initialize() -> void:
	call_deferred("run")

func check(condition: bool, name: String) -> void:
	checks.append({"name": name, "passed": condition})
	if not condition:
		push_error(name)
		finish(1)

func finish(code: int) -> void:
	var file = FileAccess.open(output + ".json", FileAccess.WRITE)
	file.store_string(JSON.stringify({"passed": code == 0, "checks": checks}, "  "))
	file.close()
	quit(code)

func idle() -> void:
	for i in 500:
		await create_timer(0.025).timeout
		if not app.client.busy:
			return
	check(false, "request finished before deadline")

func click(at: Vector2) -> void:
	for pressed in [true, false]:
		var event = InputEventMouseButton.new()
		event.button_index = MOUSE_BUTTON_LEFT
		event.pressed = pressed
		event.position = at
		event.global_position = at
		Input.parse_input_event(event)
		await process_frame
	await create_timer(0.04).timeout

func select(cell: Vector2i) -> void:
	var tree_height = 1.1 if cell == Vector2i(0, 1) and app.client.observation.self.inventory.wood == 0 and app.client.observation.entities.is_empty() else 0.0
	var at = app.world_view.camera.unproject_position(Vector3(cell.x, tree_height, cell.y)) + app.world_view.global_position
	await click(at)
	check(app.selection == cell, "mouse selected cell " + str(cell))

func button(control: Button) -> void:
	check(not control.disabled and control.visible, "enabled button: " + control.text)
	await click(control.get_global_rect().get_center())
	await idle()

func walk(cell: Vector2i) -> void:
	await select(cell)
	await button(app.move_button)
	for i in 500:
		if not app.walking:
			break
		await create_timer(0.03).timeout
	check(app._own_cell() == cell, "walk reached " + str(cell))

func screenshot(name: String) -> void:
	await process_frame
	await RenderingServer.frame_post_draw
	var code = root.get_texture().get_image().save_png(output + "-" + name + ".png")
	check(code == OK, "rendered screenshot " + name)

func run() -> void:
	output = OS.get_environment("GODOT_TEST_OUTPUT")
	app = load("res://main.tscn").instantiate()
	root.add_child(app)
	await idle()
	var mode = OS.get_environment("GODOT_TEST_MODE")
	check(app.client.healthy or (mode == "retry" and not app.client.identity.is_empty()), "authenticated real observation")
	if mode == "corrupt-journal":
		check(not app.client.storage_ok and not app.client.can_act(), "invalid recovery record pauses actions")
		await app.client.send_action({"type": "gather", "nodeId": "tree-west-north"})
		check(app.client.observation.self.inventory.wood == 0, "invalid storage sends no new action")
		finish(0)
		return
	if mode == "offline":
		await app.client.send_action({"type": "gather", "nodeId": "tree-west-north"})
		check(app.client.last_receipt.status == "committed" and app.client.pending.is_empty(), "known completion retained before observation failure")
		check(not app.client.healthy and not app.client.can_act(), "failed observation pauses new actions")
		finish(0)
		return
	if mode == "reconnect":
		check(app.client.pending.is_empty(), "restart resolves original persisted command")
		check(app.client.observation.self.inventory.wood == 1, "exactly one unit after lost response and restart")
		finish(0)
		return
	if mode == "retry":
		check(not app.client.pending.is_empty(), "missing receipt does not discard original")
		var body: String = app.client.pending.body
		await app.client.recover(true)
		check(app.client.pending.is_empty() and app.client.observation.self.inventory.wood == 1, "retry completes original once")
		check(app.client.last_receipt.commandId == JSON.parse_string(body).commandId, "retry preserves original ID")
		finish(0)
		return
	if mode == "lost":
		await app.client.send_action({"type": "gather", "nodeId": "tree-west-north"})
		check(not app.client.pending.is_empty() and not app.client.can_act(), "uncertain command retained and new actions paused")
		var access = JSON.parse_string(FileAccess.get_file_as_string(OS.get_environment("WORLD_ACCESS_FILE")))
		await app.client.connect_world(app.client.endpoint, access.sessions.a2.token)
		check(app.client.pending.is_empty() and app.client.observation.self.actorId == "a2", "other identity cannot inherit pending command")
		check(app.client.observation.self.inventory.wood == 0, "other resident inventory unchanged")
		finish(0)
		return
	if mode == "stale":
		await app.client.send_action({"type": "gather", "nodeId": "tree-west-north"})
		check(app.client.pending.is_empty() and app.client.last_receipt.status == "rejected", "stale response settled as rejection")
		check(app.client.last_receipt.error.code == "STALE_STATE" and app.client.observation.self.inventory.wood == 0, "stale action does not manufacture resources")
		finish(0)
		return
	if mode == "bridge":
		await select(Vector2i(0, 1))
		for i in 3:
			await button(app.gather_button)
		await walk(Vector2i(1, 5))
		await select(Vector2i(2, 5))
		for i in 3:
			await button(app.gather_button)
		await walk(Vector2i(3, 3))
		await select(Vector2i(4, 3))
		await button(app.bridge_button)
		await walk(Vector2i(4, 3))
		await select(Vector2i(5, 3))
		await button(app.bridge_button)
		check(app.client.observation.entities.size() == 2 and app.client.observation.self.inventory.wood == 0, "two bridge segments cost six harvested wood")
		var access = JSON.parse_string(FileAccess.get_file_as_string(OS.get_environment("WORLD_ACCESS_FILE")))
		await app.client.connect_world(app.client.endpoint, access.sessions.a2.token)
		await walk(Vector2i(1, 1))
		check(app.client.observation.self.inventory.wood == 0 and app.client.observation.entities.size() == 2, "later resident crosses existing bridge without consuming wood")
		await screenshot("bridge")
		finish(0)
		return
	check(app.client.observation.self.position == [1, 1] and app.client.observation.self.inventory.wood == 0, "scattered empty-handed initial state")
	await screenshot("initial")
	await select(Vector2i(0, 1))
	for i in 3:
		await button(app.gather_button)
		check(app.client.observation.self.inventory.wood == i + 1, "actual gather receipt and inventory " + str(i + 1))
	check(app.gather_button.disabled, "depleted tree cannot be gathered")
	await button(app.platform_button)
	check(app.client.observation.self.inventory.wood == 0 and app.client.observation.entities.size() == 1, "construction spends harvested wood")
	await screenshot("built")
	await select(Vector2i(1, 5))
	await button(app.move_button)
	for i in 500:
		if not app.walking:
			break
		await create_timer(0.03).timeout
	check(app.client.observation.self.position == [1, 5], "click to walk uses confirmed discrete moves")
	var input = InputEventKey.new()
	input.physical_keycode = KEY_S
	input.pressed = true
	Input.parse_input_event(input)
	await idle()
	check(app.client.observation.self.position == [1, 6], "keyboard movement")
	var saved = app.client.observation.duplicate(true)
	await app.client.connect_world(app.client.endpoint, "invalid-session")
	check(not app.client.can_act() and app.client.pending.is_empty(), "invalid authentication cannot act")
	var access = JSON.parse_string(FileAccess.get_file_as_string(OS.get_environment("WORLD_ACCESS_FILE")))
	await app.client.connect_world(app.client.endpoint, access.sessions.a2.token)
	check(app.client.observation.self.actorId == "a2" and app.client.observation.self.position == [6, 6], "second resident retains separate spawn")
	check(app.client.observation.entities == saved.entities, "second resident sees persistent shared construction")
	root.size = Vector2i(1024, 720)
	await screenshot("compact")
	finish(0)
