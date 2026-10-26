extends "continuous.gd"

var paths: Array = []
var blocked := 0
var seen_receipts: Dictionary = {}

func record_receipt() -> void:
	var receipt: Dictionary = app.client.last_receipt
	if receipt.is_empty() or seen_receipts.has(receipt.commandId):
		return
	seen_receipts[receipt.commandId] = true
	if receipt.get("result", {}).get("action", "") == "walk" and receipt.result.get("blocked", false):
		blocked += 1

func settled() -> void:
	for i in 900:
		await create_timer(0.025).timeout
		if not app.walking and not app.planning and not app.client.busy:
			return
	check(false, "walking deadline")

func ready_nav() -> void:
	for i in 120:
		await physics_frame
		if app.navigation.is_ready():
			return
	check(false, "navigation sync deadline")

func go(point: Vector2, mouse := false) -> void:
	if mouse:
		await click(app.world_view.camera.unproject_position(Vector3(point.x, 0.15, point.y)))
	else:
		await app._clicked(point, "")
	var route: Array = []
	for waypoint: Vector2 in app.route:
		route.append([waypoint.x, waypoint.y])
	paths.append(route)
	await settled()
	check(app.position_2d().distance_to(point) < 0.12, "authoritative arrival at %s" % point)

func run() -> void:
	output = OS.get_environment("GODOT_TEST_OUTPUT")
	app = load("res://main.tscn").instantiate()
	root.add_child(app)
	await idle()
	await ready_nav()
	app.client.changed.connect(record_receipt)
	check(app.client.healthy, "authenticated r8 navigation world")
	var mode := OS.get_environment("GODOT_TEST_MODE")
	if mode == "obstacles":
		var revision: int = app.navigation.revision
		await go(Vector2(8,9), true)
		check(paths[-1].size() > 2, "mouse route detours around live tree")
		await go(Vector2(13,8.5), true)
		check(paths[-1].size() > 2, "mouse route detours around rock")
		check(app.navigation.revision == revision, "walking does not rebake geometry")
		var version: int = app.client.observation.stateVersion
		await app._clicked(Vector2(26,17), "")
		await settled()
		check(app.client.observation.stateVersion == version and not app.world_view.marker.visible, "unreachable bank issues no walk")
		check("无法到达" in app.status_label.text, "unreachable location explains failure")
		await app._clicked(Vector2(5,7), "")
		await create_timer(0.3).timeout
		await screenshot("route")
		await settled()
	elif mode == "tree-change":
		var before: PackedVector2Array = app.navigation.path(Vector2(5,7),Vector2(8,9))
		var revision: int = app.navigation.revision
		for i in 3:
			await app.client.send_action({"type":"gather","nodeId":"tree-west-north"})
			await idle()
			if i < 2:
				check(app.navigation.revision == revision, "partially gathered tree keeps navigation")
		await ready_nav()
		check(app.navigation.revision == revision+1, "depleted tree rebuilds navigation once")
		var after: PackedVector2Array = app.navigation.path(Vector2(5,7),Vector2(8,9))
		check(before.size()>2 and after.size()==2, "depleted trunk opens direct route")
		await go(Vector2(8,9))
		await go(Vector2(5,7))
	elif mode == "bridge":
		var version: int = app.client.observation.stateVersion
		await app._clicked(Vector2(26,9), "")
		check(not app.walking and app.client.observation.stateVersion == version, "before building other bank is unreachable")
		await app.client.send_action({"type":"build","recipeId":"bridge.v1","at":[18,12]})
		await idle()
		await ready_nav()
		check(app.client.observation.entities.size()==1 and app.client.observation.self.inventory.wood==0, "real gathered materials build one bridge")
		await go(Vector2(26,9))
		check(paths[-1].size()>2, "distant destination routes through bridge")
		await screenshot("crossed")
		var access: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(OS.get_environment("WORLD_ACCESS_FILE")))
		app.client.refresh()
		check(app.client.busy, "resident switch requested during active polling")
		await app._connect(app.client.endpoint, access.sessions.a2.token)
		await idle()
		await ready_nav()
		check(app.client.observation.identity.actorId == "a2", "connection switched to the second resident")
		await go(Vector2(13,7))
		check(app.client.observation.self.inventory.wood==0, "second resident crosses existing bridge with zero wood")
		await screenshot("reused")
	elif mode == "cancel":
		await app._clicked(Vector2(13,8.5), "")
		await create_timer(0.15).timeout
		await key(KEY_ESCAPE, true)
		await key(KEY_ESCAPE, false)
		await idle()
		var stopped: Vector2 = app.position_2d()
		await create_timer(0.3).timeout
		check(not app.walking and app.position_2d().distance_to(stopped)<0.001, "escape cancels route after outstanding request")
		await app._clicked(Vector2(13,8.5), "")
		await key(KEY_W, true)
		await create_timer(0.2).timeout
		await key(KEY_W, false)
		await idle()
		check(not app.walking and not app.planning, "WASD cancels automatic route")
		app._clicked(Vector2(13,8.5), "")
		app._clicked(Vector2(4,6), "")
		await settled()
		check(app.position_2d().distance_to(Vector2(4,6))<0.06, "newest queued click wins")
		# A click waiting behind HTTP must not resume after Esc.
		app.client.send_action({"type":"walk","to":[4,6.2]})
		app._clicked(Vector2(13,8.5), "")
		app._cancel()
		await idle()
		await create_timer(0.2).timeout
		check(not app.walking and not app.planning, "cancel invalidates click awaiting HTTP")
		check(not app.world_view.marker.visible and app.world_view.route_dots.multimesh.visible_instance_count==0, "cancel clears destination and route dots")
	elif mode == "route-loss":
		await app._clicked(Vector2(13,8.5), "")
		await create_timer(2.8).timeout
		await idle()
		check(app.client.healthy and app.client.pending.is_empty(), "lost step recovered by original receipt lookup")
		var version: int = app.client.observation.stateVersion
		await create_timer(0.5).timeout
		await idle()
		check(not app.walking and app.client.observation.stateVersion == version, "recovery does not silently resume canceled route")
		await go(Vector2(8,9))
	else:
		check(false, "known navigation test mode")
	check(blocked == 0, "all navigation steps accepted without collision")
	var file := FileAccess.open(output+"-paths.json", FileAccess.WRITE)
	file.store_string(JSON.stringify({"paths":paths,"blocked":blocked,"bakeMs":app.navigation.bake_ms}, "  "))
	file.close()
	finish(0)
