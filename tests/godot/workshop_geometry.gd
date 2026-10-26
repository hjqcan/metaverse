extends SceneTree
## Regression for the actual river/bridge boundary reported during ITER-0027.
const Navigation = preload("res://world_navigation.gd")
const Geometry = preload("res://workshop_geometry.gd")
var checks: Array = []

func _initialize() -> void:
	call_deferred("run")

func check(name: String, passed: bool) -> void:
	checks.append({"name": name, "passed": passed})

func run() -> void:
	var fixture: Dictionary = JSON.parse_string(FileAccess.get_file_as_string("res://../../tests/fixtures/workshop-geometry.json"))
	var observed: Dictionary = fixture.observation
	var entity: Dictionary = observed.entities[-1]
	var start := Vector2(fixture.start[0], fixture.start[1])
	var alternative := Vector2(fixture.alternative[0], fixture.alternative[1])
	check("legal bridge-edge start", Geometry.walkable(observed, start))
	check("nearby target still blocked by water", not Geometry.can_interact(observed, start, entity))
	check("alternative movement is clear", Geometry.clear(observed, start, alternative))
	check("alternative interaction is clear", Geometry.can_interact(observed, alternative, entity))
	check("solid bench center cannot be occupied", not Geometry.walkable(observed, Vector2(entity.position[0], entity.position[1])))
	var node := Navigation.new()
	root.add_child(node)
	node.update_geometry(observed)
	var deadline := Time.get_ticks_msec() + 15000
	while not node.is_ready() and Time.get_ticks_msec() < deadline:
		await physics_frame
	check("actual navigation bake completed", node.is_ready())
	var route: PackedVector2Array = node.workshop_approach(start, entity, observed)
	check("approach changes the blocked position", not route.is_empty() and route[-1].distance_to(start) > 0.01)
	check("selected endpoint can interact", not route.is_empty() and Geometry.can_interact(observed, route[-1], entity))
	var previous := start
	var clear_route := not route.is_empty()
	for point: Vector2 in route:
		clear_route = clear_route and Geometry.clear(observed, previous, point)
		previous = point
	check("entire navigation route is clear", clear_route)
	var points: Array = []
	for point: Vector2 in route:
		points.append([point.x, point.y])
	var passed := checks.all(func(item: Dictionary) -> bool: return item.passed)
	var result := {"passed": passed, "checks": checks, "route": points, "worldCommands": 0, "actualModelCalls": 0,
		"scope": "Actual native navigation on retained terrain plus a synthetic bench; no world mutation."}
	var output := OS.get_environment("GODOT_TEST_OUTPUT")
	if not output.is_empty():
		var file := FileAccess.open(output, FileAccess.WRITE)
		file.store_string(JSON.stringify(result, "  ") + "\n")
		file.close()
	print(JSON.stringify(result))
	node.queue_free()
	await process_frame
	quit(0 if passed else 1)
