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

func type_text(value: String) -> void:
	for character in value:
		var event = InputEventKey.new()
		event.unicode = character.unicode_at(0)
		event.pressed = true
		Input.parse_input_event(event)
		await process_frame

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
		check(client.healthy and app.notes_button.visible, "native client sees opted-in old bridge")
		await click(app.notes_button)
		check(app.notes_panel.visible, "mouse opens bridge notes")
		await click(app.notes_panel.draft)
		await type_text("关闭这份草稿不会发表")
		check(app.notes_panel.draft.text == "关闭这份草稿不会发表", "native Unicode draft input")
		app.notes_panel.close_panel()
		check(client.observation.entityNotes.totalCount == 0 and client.pending.is_empty(), "closing a draft sends no command")
		await click(app.notes_button)
		check(app.notes_panel.draft.text.is_empty(), "closed draft cleared")
		await click(app.notes_panel.draft)
		await type_text("这座桥连接了两岸。")
		await idle()
		check(not app.notes_panel.send_button.disabled, "empty inventory can publish nearby")
		await screenshot("draft")
		await click(app.notes_panel.send_button)
		check(client.pending.is_empty() and client.last_receipt.get("result", {}).get("action") == "append_entity_note", "actual note settled with receipt event and observation")
		check(app.notes_panel.status.text.begins_with("已确认发表"), "confirmed state distinct from draft")
		var first: Dictionary = client.observation.entityNotes.notes[0]
		await screenshot("published")
		await app._connect(client.endpoint, access.sessions.a3.token)
		await idle()
		check(app.notes_panel.draft.text.is_empty() and app.notes_panel.reply_id == null, "identity switch clears previous draft and reference")
		await click(app.notes_button)
		check(client.observation.entityNotes.notes[0].text == first.text, "next resident reads original published text")
		var buttons = app.notes_panel.entries.get_children().filter(func(n): return n is Button)
		check(buttons.size() == 1, "original note has reply action")
		await click(buttons[0])
		await type_text("我读到了你的话，也从这座桥经过。")
		check(app.notes_panel.reply_id == first.noteId, "reply pins original note identity")
		await click(app.notes_panel.send_button)
		check(client.pending.is_empty() and client.observation.entityNotes.totalCount == 2, "second resident publishes exactly one reply")
		check(client.observation.entityNotes.notes[1].replyToNoteId == first.noteId, "server retains original reference")
		await screenshot("reply")
	else:
		client = Client.new()
		root.add_child(client)
		await client.connect_world(OS.get_environment("WORLD_URL"), access.sessions.a2.token)
		if mode == "return":
			if not client.pending.is_empty():
				await client.recover(true)
			check(client.can_act() and client.pending.is_empty(), "restarted adapter settles original note")
			check(client.observation.entityNotes.totalCount == 1, "exactly one immutable note")
			check(client.pending_store.read(client._key()).is_empty(), "original disk record settled")
		else:
			check(client.healthy and Client.Evidence.Notes.supported(client.observation), "actual capability fully validated")
			var missing_bridge = client.observation.duplicate(true)
			missing_bridge.entities = []
			check(not Client.Evidence.Notes.supported(missing_bridge), "capability alone cannot replace original bridge entity")
			await client.send_action({"type":"append_entity_note", "entityId":client.observation.entityNotes.target.entityId,
				"text":"原请求不会在重连时换成另一句话。", "replyToNoteId":null})
			check(not client.pending.is_empty() and not client.can_act(), "missing or damaged evidence preserves pending")
			check(client._valid_record(JSON.parse_string(JSON.stringify(client.pending))), "original v4 note survives JSON number conversion")
			var original: String = client.pending.body
			var record = client.pending.duplicate(true)
			var before = JSON.parse_string(record.before)
			before.noteText = "different"
			record.before = JSON.stringify(before)
			check(not client._valid_record(record), "changed frozen text rejected")
			check(client.pending.body == original, "validation never replaces original body")
	var passed = checks.all(func(c): return c.passed)
	var file = FileAccess.open(output + ".json", FileAccess.WRITE)
	file.store_string(JSON.stringify({"passed":passed,"checks":checks}, "  "))
	file.close()
	quit(0 if passed else 1)
