extends SceneTree
## Recorded live observations, original HTTP facts, and explicit UI-only mutations.
const Main = preload("res://main.gd")
const Forestry = preload("res://forestry_evidence.gd")
var checks: Array = []
var screen: Node
var output: String

func _initialize() -> void:
	call_deferred("run")

func check(value: bool, label: String) -> void:
	checks.append({"name": label, "passed": value})
	if not value:
		push_error(label)

func frames(count: int = 3) -> void:
	for i in count:
		await process_frame

func click(button: Control) -> void:
	var point: Vector2 = root.get_final_transform() * button.get_global_rect().get_center()
	var motion := InputEventMouseMotion.new()
	motion.position = point
	motion.global_position = point
	Input.parse_input_event(motion)
	await process_frame
	var press := InputEventMouseButton.new()
	press.position = point
	press.global_position = point
	press.button_index = MOUSE_BUTTON_LEFT
	press.pressed = true
	Input.parse_input_event(press)
	await process_frame
	var release: InputEventMouseButton = press.duplicate()
	release.pressed = false
	Input.parse_input_event(release)
	await frames()

func shot(name: String) -> void:
	await RenderingServer.frame_post_draw
	var file := OS.get_environment("GODOT_TEST_SCREENSHOTS").path_join(name + ".png")
	check(root.get_texture().get_image().save_png(file) == OK, "actual OpenGL screenshot: " + name)

func run() -> void:
	output = OS.get_environment("GODOT_TEST_OUTPUT")
	var fixture = JSON.parse_string(FileAccess.get_file_as_string(OS.get_environment("GODOT_TEST_FIXTURE")))
	var facts: Array = fixture.facts
	for receipt in facts:
		var d: Dictionary = receipt.result.forestryAction
		check(Forestry.valid_detail(d), "recorded original " + d.action.type + " has a valid state transition")
		var changed: Dictionary = d.duplicate(true)
		changed.seeds += 1
		check(not Forestry.valid_detail(changed), "invented seed rejected: " + d.action.type)
	var o: Dictionary = fixture.growing
	check(Forestry.supported(o), "actual growing observation and public circles accepted")
	var bad: Dictionary = o.duplicate(true)
	bad.forestry.version = 2
	check(not Forestry.supported(bad), "unknown forestry version rejected")
	bad = o.duplicate(true)
	bad.forestry.plants[0].maturesAtMs += 1
	check(not Forestry.supported(bad), "growth duration cannot drift")
	bad = o.duplicate(true)
	bad.terrain.obstacles = bad.terrain.obstacles.filter(func(item): return item.kind != "forestry_tree")
	check(not Forestry.supported(bad), "missing live trunk collision rejected")
	var r: Dictionary = o.forestry.reservations[0]
	var changed_reservation: Dictionary = r.duplicate(true)
	changed_reservation.status = "preparing"
	changed_reservation.plantId = null
	changed_reservation.reservedSeed = 1
	changed_reservation.expiresAtMs = r.grantedAtMs + 90000
	var queued: Dictionary = changed_reservation.duplicate(true)
	queued.merge({"status": "queued", "plotId": null, "reservedSeed": 0, "grantedAtMs": null, "expiresAtMs": null}, true)
	check(Forestry.same_reservation_before({"type": "cancel_forest_reservation"}, changed_reservation, queued), "queued cancellation accepts same original actual grant")
	changed_reservation.reservationId = "fr" + "a".repeat(32)
	check(not Forestry.same_reservation_before({"type": "cancel_forest_reservation"}, changed_reservation, queued), "queued cancellation cannot switch reservation")
	screen = Main.new()
	root.add_child(screen)
	screen.set_physics_process(false)
	await frames()
	screen.client.observation = screen.client._integer_fields(o.duplicate(true))
	screen.client.identity = o.identity.duplicate(true)
	screen.client.healthy = true
	screen.connection_panel.hide()
	screen._render()
	await frames(8)
	check(screen.forestry_button.visible, "forestry menu shown in actual main scene")
	await click(screen.forestry_button)
	check(screen.forestry_panel.visible, "actual mouse opens forestry panel")
	check(screen.forestry_panel.queue_status.text.contains("生长"), "original growing grant displayed")
	check(screen.forestry_panel.plant_button.disabled and screen.forestry_panel.harvest_button.disabled, "growing tree cannot be planted or harvested again")
	var rule_visible := false
	for label in screen.forestry_panel.find_children("*", "Label", true, false):
		if label.text.contains("种前90") and label.text.contains("120") and label.text.contains("60"):
			rule_visible = label.is_visible_in_tree()
	check(rule_visible, "fixed timing and priority explanation survives polling")
	check(screen.forestry_panel.harvest_button.get_global_rect().end.x <= screen.forestry_panel.scroll.get_global_rect().end.x, "whole-tree harvest button fits without horizontal clipping")
	await shot("forestry-growing-1280")
	root.size = Vector2i(1000, 720)
	screen._render()
	await frames(8)
	check(screen.forestry_panel.get_global_rect().end.y <= root.get_visible_rect().size.y, "panel remains within shorter window")
	await shot("forestry-growing-1000")
	screen.forestry_panel.update_world(o, false, {"commandId": "pending-original"}, {}, 0)
	check(screen.forestry_panel.reserve_button.disabled and screen.forestry_panel.collect_button.disabled and screen.forestry_panel.harvest_button.disabled, "pending blocks new forestry effects")
	check(Forestry.supported(fixture.completed), "actual harvested observation preserves empty plot and seed")
	var geometry := preload("res://workshop_geometry.gd")
	var center := Vector2(7, 12)
	check(not geometry.walkable(o, center), "planted trunk blocks ordinary walk")
	check(geometry.clear(o, Vector2(8.2, 12), center, o.forestry.plants[0].plantId), "interaction excludes only original target trunk")
	check(not geometry.clear(o, Vector2(8.2, 12), center, "p" + "0".repeat(32)), "wrong target ID cannot ignore trunk")
	screen.navigation.update_geometry(fixture.completed)
	for i in 600:
		if screen.navigation.is_ready():
			break
		await physics_frame
	var approach: PackedVector2Array = screen.navigation.workshop_approach(Vector2(7, 12), {"entityId": "forest-west-north", "position": [7, 12]}, fixture.completed)
	check(not approach.is_empty() and approach[-1].distance_to(Vector2(7, 12)) >= 0.8, "empty plot center moves outside the future trunk before planting")
	var passed: bool = checks.all(func(c): return c.passed)
	var file := FileAccess.open(output, FileAccess.WRITE)
	file.store_string(JSON.stringify({"passed": passed, "checks": checks, "worldRequests": 0, "actualModelCalls": 0,
		"evidenceScope": "recorded live facts, actual main scene mouse open and rendering; boundary mutations are UI fixtures"}, "  "))
	file.close()
	screen.queue_free()
	await frames()
	quit(0 if passed else 1)
