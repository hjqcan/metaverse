extends RefCounted
## Exact finite sweep checks for choosing an interaction side. The server decides.
const Workshop = preload("res://workshop_evidence.gd")
const RADIUS := 0.28

static func _point(value: Array) -> Vector2:
	return Vector2(value[0], value[1])

static func _segment_distance(p: Vector2, a: Vector2, b: Vector2) -> float:
	var delta := b - a
	var fraction := clampf((p - a).dot(delta) / delta.length_squared(), 0, 1) if delta.length_squared() > 0 else 0.0
	return p.distance_to(a + delta * fraction)

static func walkable(observed: Dictionary, point: Vector2, excluded: String = "") -> bool:
	if point.x < RADIUS or point.x > 32 - RADIUS or point.y < RADIUS or point.y > 24 - RADIUS:
		return false
	for rock in observed.terrain.obstacles:
		if point.distance_to(_point(rock.position)) < rock.radius + RADIUS - 0.000000001:
			return false
	for tree in observed.resourceNodes:
		if tree.remainingWood > 0 and point.distance_to(_point(tree.position)) < 0.45 + RADIUS - 0.000000001:
			return false
	for entity in observed.entities:
		if entity.definitionId not in ["workbench", "wooden_chest"] or entity.entityId == excluded:
			continue
		var center := _point(entity.position)
		var half := Workshop.half_size(entity.definitionId)
		var nearest := Vector2(clampf(point.x, center.x - half.x, center.x + half.x), clampf(point.y, center.y - half.y, center.y + half.y))
		if point.distance_to(nearest) < RADIUS - 0.000000001:
			return false
	for entity in observed.entities:
		if entity.definitionId == "bridge" and absf(point.x - entity.position[0]) <= 2.4 - RADIUS and absf(point.y - entity.position[1]) <= 0.8 - RADIUS:
			return true
	var polygon: Array = observed.terrain.river.polygon
	var inside := false
	for i in polygon.size():
		var a := _point(polygon[i])
		var b := _point(polygon[(i + 1) % polygon.size()])
		if (a.y > point.y) != (b.y > point.y) and point.x < (b.x - a.x) * (point.y - a.y) / (b.y - a.y) + a.x:
			inside = not inside
		if _segment_distance(point, a, b) < RADIUS - 0.000000001:
			return false
	return not inside

static func _cut(cuts: Array[float], value: float) -> void:
	if value > 0 and value < 1 and is_finite(value):
		cuts.append(value)

static func _circle(cuts: Array[float], start: Vector2, delta: Vector2, center: Vector2, radius: float) -> void:
	var a := delta.length_squared()
	var b := 2 * (start - center).dot(delta)
	var c := (start - center).length_squared() - radius * radius
	var discriminant := b * b - 4 * a * c
	if discriminant >= 0 and a > 0:
		var root := sqrt(discriminant)
		_cut(cuts, (-b - root) / (2 * a))
		_cut(cuts, (-b + root) / (2 * a))

static func _axis(cuts: Array[float], start: float, delta: float, edge: float) -> void:
	if absf(delta) > 0.00000000000001:
		_cut(cuts, (edge - start) / delta)

static func clear(observed: Dictionary, start: Vector2, finish: Vector2, excluded: String = "") -> bool:
	if not walkable(observed, start, excluded) or not walkable(observed, finish, excluded):
		return false
	var delta := finish - start
	if delta.length_squared() < 0.000000000000000001:
		return true
	var cuts: Array[float] = [0.0, 1.0]
	for rock in observed.terrain.obstacles:
		_circle(cuts, start, delta, _point(rock.position), rock.radius + RADIUS)
	for tree in observed.resourceNodes:
		if tree.remainingWood > 0:
			_circle(cuts, start, delta, _point(tree.position), 0.45 + RADIUS)
	var polygon: Array = observed.terrain.river.polygon
	for i in polygon.size():
		var a := _point(polygon[i])
		var b := _point(polygon[(i + 1) % polygon.size()])
		var edge := b - a
		var denominator := edge.cross(delta)
		var initial := edge.cross(start - a)
		if absf(denominator) > 0.00000000000001:
			for offset in [-RADIUS * edge.length(), 0.0, RADIUS * edge.length()]:
				_cut(cuts, (offset - initial) / denominator)
		_circle(cuts, start, delta, a, RADIUS)
	for entity in observed.entities:
		var center := _point(entity.position)
		if entity.definitionId == "bridge":
			for x in [center.x - 2.4 + RADIUS, center.x + 2.4 - RADIUS]:
				_axis(cuts, start.x, delta.x, x)
			for z in [center.y - 0.8 + RADIUS, center.y + 0.8 - RADIUS]:
				_axis(cuts, start.y, delta.y, z)
		elif entity.definitionId in ["workbench", "wooden_chest"] and entity.entityId != excluded:
			var half := Workshop.half_size(entity.definitionId)
			for x in [center.x - half.x, center.x + half.x]:
				for offset in [-RADIUS, 0.0, RADIUS]:
					_axis(cuts, start.x, delta.x, x + offset)
				for z in [center.y - half.y, center.y + half.y]:
					_circle(cuts, start, delta, Vector2(x, z), RADIUS)
			for z in [center.y - half.y, center.y + half.y]:
				for offset in [-RADIUS, 0.0, RADIUS]:
					_axis(cuts, start.y, delta.y, z + offset)
	cuts.sort()
	for i in cuts.size() - 1:
		if not walkable(observed, start + delta * ((cuts[i] + cuts[i + 1]) / 2), excluded):
			return false
	return true

static func can_interact(observed: Dictionary, start: Vector2, entity: Dictionary) -> bool:
	return not entity.is_empty() and start.distance_to(_point(entity.position)) <= 1.6 \
		and walkable(observed, start) and clear(observed, start, _point(entity.position), entity.entityId)
