extends Node
## Local route suggestions only. World.Server remains authoritative for every step.

const CELL_SIZE := 0.05
const CLEARANCE := 0.07
var map: RID
var region: RID
var geometry_key := ""
var revision := 0
var bake_ms := 0.0
var baking := false
var pending_iteration := -1
var pending_region_iteration := -1
var bounds := Rect2(0, 0, 32, 24)

func _ready() -> void:
	map = NavigationServer3D.map_create()
	NavigationServer3D.map_set_cell_size(map, CELL_SIZE)
	NavigationServer3D.map_set_cell_height(map, CELL_SIZE)
	NavigationServer3D.map_set_active(map, true)
	NavigationServer3D.map_set_use_async_iterations(map, false)
	region = NavigationServer3D.region_create()
	NavigationServer3D.region_set_use_async_iterations(region, false)
	NavigationServer3D.region_set_map(region, map)

func _exit_tree() -> void:
	NavigationServer3D.free_rid(region)
	NavigationServer3D.free_rid(map)

func is_ready() -> bool:
	return not baking and not geometry_key.is_empty() and NavigationServer3D.map_get_iteration_id(map) > pending_iteration and NavigationServer3D.region_get_iteration_id(region) > pending_region_iteration

func update_geometry(observation: Dictionary) -> bool:
	var circles: Array = observation.terrain.obstacles.duplicate(true)
	for tree: Dictionary in observation.resourceNodes:
		if tree.remainingWood > 0:
			circles.append({"position": tree.position, "radius": 0.45})
	var bridges: Array = []
	for entity: Dictionary in observation.entities:
		if entity.definitionId == "bridge":
			bridges.append(entity.position)
	var radius: float = observation.movement.radius + CLEARANCE
	var key := JSON.stringify([observation.world.bounds, radius, observation.terrain.river.polygon, circles, bridges])
	if key == geometry_key:
		return false
	geometry_key = key
	revision += 1
	var started := Time.get_ticks_usec()
	var b: Array = observation.world.bounds
	bounds = Rect2(b[0], b[1], b[2] - b[0], b[3] - b[1])
	var geometry := NavigationMeshSourceGeometryData3D.new()
	var corners := _rectangle(bounds)
	geometry.add_faces(PackedVector3Array([
		_xz(corners[0]), _xz(corners[1]), _xz(corners[2]),
		_xz(corners[0]), _xz(corners[2]), _xz(corners[3])]), Transform3D.IDENTITY)
	# The server permits water only inside a bridge inset by the resident radius.
	# Expand the water first, subtract inset bridges, then carve without a second offset.
	var river := PackedVector2Array()
	for point: Array in observation.terrain.river.polygon:
		river.append(Vector2(point[0], point[1]))
	var water: Array[PackedVector2Array] = Geometry2D.offset_polygon(river, radius, Geometry2D.JOIN_ROUND)
	for bridge: Array in bridges:
		var center := Vector2(bridge[0], bridge[1])
		var half := Vector2(2.4, 0.8) - Vector2.ONE * radius
		var opening := _rectangle(Rect2(center - half, half * 2))
		var remainder: Array[PackedVector2Array] = []
		for polygon: PackedVector2Array in water:
			remainder.append_array(Geometry2D.clip_polygons(polygon, opening))
		water = remainder
	for polygon: PackedVector2Array in water:
		_obstruct(geometry, polygon, true)
	for circle: Dictionary in circles:
		var outline := PackedVector2Array()
		var center := Vector2(circle.position[0], circle.position[1])
		# Circumscribe, so the polygon never cuts inside a real circular obstacle.
		var obstacle_radius: float = circle.radius / cos(PI / 24)
		for i in 24:
			outline.append(center + Vector2.from_angle(TAU * i / 24) * obstacle_radius)
		_obstruct(geometry, outline, false)
	var mesh := NavigationMesh.new()
	mesh.cell_size = CELL_SIZE
	mesh.cell_height = CELL_SIZE
	mesh.agent_radius = radius
	mesh.edge_max_error = 0.2
	mesh.region_min_size = 0.0
	baking = true
	NavigationServer3D.bake_from_source_geometry_data_async(mesh, geometry, _baked.bind(mesh, key, started))
	return true

func _baked(mesh: NavigationMesh, key: String, started: int) -> void:
	if key != geometry_key:
		return
	pending_iteration = NavigationServer3D.map_get_iteration_id(map)
	pending_region_iteration = NavigationServer3D.region_get_iteration_id(region)
	NavigationServer3D.region_set_navigation_mesh(region, mesh)
	bake_ms = (Time.get_ticks_usec() - started) / 1000.0
	baking = false

func _rectangle(rect: Rect2) -> PackedVector2Array:
	return PackedVector2Array([rect.position, Vector2(rect.end.x, rect.position.y), rect.end, Vector2(rect.position.x, rect.end.y)])

func _xz(point: Vector2) -> Vector3:
	return Vector3(point.x, 0, point.y)

func _obstruct(geometry: NavigationMeshSourceGeometryData3D, polygon: PackedVector2Array, carve: bool) -> void:
	var vertices := PackedVector3Array()
	for point: Vector2 in polygon:
		vertices.append(_xz(point))
	geometry.add_projected_obstruction(vertices, -0.5, 3.0, carve)

func path(start: Vector2, target: Vector2) -> PackedVector2Array:
	if not is_ready():
		return PackedVector2Array()
	var nearest := NavigationServer3D.map_get_closest_point(map, _xz(target))
	# A small edge adjustment is visible in the destination marker. Never silently
	# turn an unreachable bank or a point deep inside an obstacle into another goal.
	if Vector2(nearest.x, nearest.z).distance_to(target) > 0.22:
		return PackedVector2Array()
	var query := NavigationPathQueryParameters3D.new()
	query.map = map
	query.start_position = _xz(start)
	query.target_position = nearest
	query.simplify_path = true
	query.simplify_epsilon = 0.015
	var reply := NavigationPathQueryResult3D.new()
	NavigationServer3D.query_path(query, reply)
	var points := reply.get_path()
	if points.is_empty() or points[-1].distance_to(nearest) > 0.03:
		return PackedVector2Array()
	var result := PackedVector2Array()
	for point: Vector3 in points:
		result.append(Vector2(point.x, point.z))
	return result

func approach(start: Vector2, center: Vector2) -> PackedVector2Array:
	if start.distance_to(center) <= 1.3:
		return PackedVector2Array([start])
	var best := PackedVector2Array()
	var best_length := INF
	var angle := (start - center).angle()
	for i in 16:
		var candidate := path(start, center + Vector2.from_angle(angle + TAU * i / 16) * 1.2)
		if candidate.is_empty() or candidate[-1].distance_to(center) > 1.4:
			continue
		var length := start.distance_to(candidate[0])
		for j in range(1, candidate.size()):
			length += candidate[j - 1].distance_to(candidate[j])
		if length < best_length:
			best_length = length
			best = candidate
	return best
