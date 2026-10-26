extends SceneTree
var app: Node
var checks: Array = []
var output: String

func _initialize() -> void:
	call_deferred("run")
func check(ok: bool, label: String) -> void:
	checks.append({"name":label,"passed":ok})
	if not ok:
		push_error(label)
		finish(1)
func finish(code: int) -> void:
	if checks.any(func(item): return not item.passed):
		code = 1
	var file = FileAccess.open(output+".json",FileAccess.WRITE)
	file.store_string(JSON.stringify({"passed":code==0,"checks":checks},"  "))
	file.close()
	quit(code)
func idle() -> void:
	for i in 500:
		await create_timer(0.025).timeout
		if not app.client.busy:
			return
	check(false,"request deadline")
func screenshot(label: String) -> void:
	await process_frame
	await RenderingServer.frame_post_draw
	check(root.get_texture().get_image().save_png(output+"-"+label+".png")==OK,"rendered "+label)
func key(code: int, pressed: bool) -> void:
	var event = InputEventKey.new()
	event.physical_keycode = code
	event.keycode = code
	event.pressed = pressed
	Input.parse_input_event(event)
	await process_frame
func click(point: Vector2) -> void:
	for pressed in [true,false]:
		var event = InputEventMouseButton.new()
		event.position = point
		event.global_position = point
		event.button_index = MOUSE_BUTTON_LEFT
		event.pressed = pressed
		Input.parse_input_event(event)
		await process_frame
func run() -> void:
	output = OS.get_environment("GODOT_TEST_OUTPUT")
	app = load("res://main.tscn").instantiate()
	root.add_child(app)
	await idle()
	check(app.client.healthy,"r8 observation authenticated")
	await create_timer(0.5).timeout
	await screenshot("initial")
	if OS.get_environment("GODOT_TEST_MODE") == "input-loss":
		await key(KEY_W,true)
		await create_timer(2.8).timeout
		await idle()
		check(app.client.healthy and app.client.pending.is_empty(),"automatic lookup recovers dropped walk receipt")
		var settled: int = app.client.observation.stateVersion
		await create_timer(0.7).timeout
		await idle()
		check(app.client.observation.stateVersion==settled,"held key does not resume after uncertain result")
		await key(KEY_W,false)
		await create_timer(0.15).timeout
		await key(KEY_W,true)
		await create_timer(0.4).timeout
		await key(KEY_W,false)
		await idle()
		check(app.client.observation.stateVersion>settled,"fresh key press resumes movement")
		finish(0)
		return
	if OS.get_environment("GODOT_TEST_MODE") == "bridge":
		await key(KEY_2,true)
		await key(KEY_2,false)
		await idle()
		check(app.build_recipe=="bridge.v1","whole bridge preview selected")
		app._hovered(Vector2(18,12))
		check(app._placement_valid(Vector2(18,12),"bridge.v1"),"bridge spans natural river from near bank")
		await idle()
		await click(app.world_view.camera.unproject_position(Vector3(18,0.15,12)))
		await idle()
		check(app.client.observation.entities.size()==1 and app.client.observation.self.inventory.wood==0,"six gathered wood builds one complete bridge")
		await screenshot("bridge-built")
		await idle()
		await click(app.world_view.camera.unproject_position(Vector3(20.5,0.15,12)))
		for i in 300:
			await create_timer(0.04).timeout
			if not app.walking and not app.client.busy:
				break
		check(app.position_2d().x>20,"builder crosses actual bridge")
		var access = JSON.parse_string(FileAccess.get_file_as_string(OS.get_environment("WORLD_ACCESS_FILE")))
		await app._connect(app.client.endpoint,access.sessions.a2.token)
		await create_timer(0.6).timeout
		await idle()
		check(app.client.observation.identity.actorId=="a2","bridge reuse really switches to second resident")
		await click(app.world_view.camera.unproject_position(Vector3(15.2,0.15,12)))
		for i in 300:
			await create_timer(0.04).timeout
			if not app.walking and not app.client.busy:
				break
		check(app.position_2d().x<15.4 and app.client.observation.self.inventory.wood==0,"other resident reuses bridge without wood")
		await screenshot("bridge-reused")
		finish(0)
		return
	var start: Vector2 = app.position_2d()
	await key(KEY_W,true)
	await create_timer(0.65).timeout
	await key(KEY_W,false)
	await idle()
	var moved: Vector2 = app.position_2d()
	check(moved.y < start.y-0.35 and moved.y > start.y-3,"held WASD moves in metres")
	check(absf(moved.y-roundf(moved.y))>0.001,"position has actual fractional coordinates")
	var click_target = Vector2(4.0,6.5)
	var screen: Vector2 = app.world_view.camera.unproject_position(Vector3(click_target.x,0.15,click_target.y))
	await click(screen)
	for i in 100:
		await create_timer(0.04).timeout
		if not app.walking and not app.client.busy:
			break
	check(app.position_2d().distance_to(click_target)<0.12,"mouse walks to unsnapped ground coordinate")
	# Return near the initial tree, choose it by clicking its canopy, then gather via E.
	await app.client.send_action({"type":"walk","to":[4.5,7.0]})
	await idle()
	var tree_screen: Vector2 = app.world_view.camera.unproject_position(Vector3(6.2,2,7.8))
	await click(tree_screen)
	for i in 200:
		await create_timer(0.04).timeout
		if not app.walking and not app.client.busy:
			break
	check(app.selected_node=="tree-west-north","canopy raycast selects real tree")
	check(app.position_2d().distance_to(Vector2(6.2,7.8))<=1.6,"walk approaches tree without entering trunk")
	for i in 3:
		await key(KEY_E,true)
		await key(KEY_E,false)
		await idle()
	check(app.client.observation.self.inventory.wood==3,"E gathers three authoritative units")
	await key(KEY_1,true)
	await key(KEY_1,false)
	await idle()
	check(app.build_recipe=="platform.v1","build shortcut opens preview")
	app._hovered(Vector2(4.2,7.3))
	check(app.world_view.ghost.visible,"continuous footprint preview visible")
	await screenshot("preview")
	await idle()
	await app._clicked(Vector2(4.2,7.3),"")
	await idle()
	check(app.client.observation.entities.size()==1,"platform constructed from collected wood")
	check(Vector2(app.client.observation.entities[0].position[0],app.client.observation.entities[0].position[1]).distance_to(Vector2(4.2,7.3))<0.00001,"building position preserves fractions")
	check(app.client.observation.resourceAudit.conserved,"resource audit conserved")
	await screenshot("built")
	root.size = Vector2i(1024,768)
	await create_timer(0.3).timeout
	await screenshot("compact")
	finish(0)
