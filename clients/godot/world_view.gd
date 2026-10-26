extends SubViewportContainer
## Only projects server facts into meshes. No resource or movement rules live here.
signal cell_selected(cell: Vector2i)
var scene: Node3D
var content: Node3D
var camera: Camera3D
var marker: MeshInstance3D
var selected = Vector2i(-1, -1)
var snapshot: Dictionary = {}
var font: SystemFont

func _ready() -> void:
	stretch = true
	size_flags_horizontal = Control.SIZE_EXPAND_FILL
	size_flags_vertical = Control.SIZE_EXPAND_FILL
	var viewport = SubViewport.new()
	viewport.own_world_3d = true
	viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	add_child(viewport)
	scene = Node3D.new()
	viewport.add_child(scene)
	var environment = WorldEnvironment.new()
	environment.environment = Environment.new()
	environment.environment.background_mode = Environment.BG_COLOR
	environment.environment.background_color = Color("243c42")
	environment.environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	environment.environment.ambient_light_color = Color("d0e3d3")
	environment.environment.ambient_light_energy = 0.35
	environment.environment.tonemap_mode = Environment.TONE_MAPPER_FILMIC
	scene.add_child(environment)
	var sun = DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-55, -30, 0)
	sun.light_color = Color("fff0ce")
	sun.light_energy = 0.7
	sun.shadow_enabled = true
	scene.add_child(sun)
	camera = Camera3D.new()
	scene.add_child(camera)
	camera.projection = Camera3D.PROJECTION_ORTHOGONAL
	camera.size = 11.5
	camera.position = Vector3(3.5, 12, 12)
	camera.look_at(Vector3(3.5, 0, 3.5))
	font = SystemFont.new()
	font.font_names = PackedStringArray(["Noto Sans CJK SC", "WenQuanYi Micro Hei", "sans-serif"])
	content = Node3D.new()
	scene.add_child(content)
	marker = _box(scene, Vector3(0, 0.08, 0), Vector3(1.02, 0.05, 1.02), Color("e5ba66"))
	marker.visible = false
	gui_input.connect(_input_map)

func _material(color: Color) -> StandardMaterial3D:
	var material = StandardMaterial3D.new()
	material.albedo_color = color.srgb_to_linear()
	material.roughness = 0.95
	return material

func _mesh(parent: Node3D, mesh: Mesh, at: Vector3, color: Color) -> MeshInstance3D:
	var result = MeshInstance3D.new()
	result.mesh = mesh
	result.material_override = _material(color)
	result.position = at
	parent.add_child(result)
	return result

func _box(parent: Node3D, at: Vector3, dimensions: Vector3, color: Color) -> MeshInstance3D:
	var mesh = BoxMesh.new()
	mesh.size = dimensions
	return _mesh(parent, mesh, at, color)

func _cylinder(at: Vector3, radius: float, height: float, color: Color, top: float = -1) -> void:
	var mesh = CylinderMesh.new()
	mesh.top_radius = radius if top < 0 else top
	mesh.bottom_radius = radius
	mesh.height = height
	mesh.radial_segments = 7
	_mesh(content, mesh, at, color)

func _label(text: String, at: Vector3, color: Color = Color.WHITE) -> void:
	var label = Label3D.new()
	label.text = text
	label.font = font
	label.font_size = 42
	label.pixel_size = 0.007
	label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	label.position = at
	label.modulate = color
	label.outline_size = 8
	content.add_child(label)

func _pick_box(cell: Vector2i, height: float) -> void:
	var body = StaticBody3D.new()
	body.position = Vector3(cell.x, height / 2, cell.y)
	body.set_meta("cell", cell)
	var shape = BoxShape3D.new()
	shape.size = Vector3(0.98, height, 0.98)
	var collision = CollisionShape3D.new()
	collision.shape = shape
	body.add_child(collision)
	content.add_child(body)

func show_world(data: Dictionary) -> void:
	snapshot = data
	for child in content.get_children():
		child.free()
	_box(content, Vector3(3.5, -0.42, 3.5), Vector3(8.4, 0.65, 8.4), Color("776c54"))
	var water: Array = data.world.water
	var trees: Array = data.resourceNodes
	var tree_cells = trees.map(func(tree): return tree.position)
	for x in int(data.world.width):
		for y in int(data.world.height):
			var cell = [x, y]
			var color = Color("3a8391") if cell in water else Color("7e9863") if (x + y) % 2 == 0 else Color("869e6c")
			_box(content, Vector3(x, -0.08, y), Vector3(0.985, 0.16, 0.985), color)
			var live_tree = trees.any(func(tree): return tree.position == cell and tree.remainingWood > 0)
			_pick_box(Vector2i(x, y), 1.7 if live_tree else 0.15)
			if cell in data.world.blocked and cell not in water and cell not in tree_cells:
				var rock = _box(content, Vector3(x, 0.30, y), Vector3(0.78, 0.62, 0.82), Color("a6aaa0"))
				rock.rotation_degrees.y = 14 * (y + 1)
				_box(content, Vector3(x + 0.14, 0.68, y), Vector3(0.48, 0.28, 0.52), Color("bdc0ad"))
	for tree in trees:
		var at = Vector3(tree.position[0], 0, tree.position[1])
		var alive = tree.remainingWood > 0
		_cylinder(at + Vector3(0, 0.26 if alive else 0.13, 0), 0.13, 0.52 if alive else 0.26, Color("78533e"))
		if alive:
			_cylinder(at + Vector3(0, 0.88, 0), 0.46, 0.9, Color("315d47"), 0)
			_cylinder(at + Vector3(0, 1.28, 0), 0.35, 0.8, Color("407857"), 0)
		_label(str(int(tree.remainingWood)) + " 木", at + Vector3(0, 1.95 if alive else 0.48, 0), Color("f6e8b8"))
	for entity in data.entities:
		var at = Vector3(entity.position[0], 0.12, entity.position[1])
		for plank in 5:
			_box(content, at + Vector3(0, 0, (plank - 2) * 0.18), Vector3(0.95, 0.15, 0.15), Color("ba8b52"))
		if entity.definitionId == "bridge":
			for edge in [-0.44, 0.44]:
				_box(content, at + Vector3(0, 0.25, edge), Vector3(1.0, 0.08, 0.06), Color("795b3e"))
	for resident in data.residents:
		var at = Vector3(resident.position[0], 0, resident.position[1])
		var own = resident.actorId == data.self.actorId
		var body = CapsuleMesh.new()
		body.radius = 0.18
		body.height = 0.58
		_mesh(content, body, at + Vector3(0, 0.42, 0), Color("f3c36c") if own else Color("e3a18a"))
		var head = SphereMesh.new()
		head.radius = 0.14
		head.height = 0.28
		_mesh(content, head, at + Vector3(0, 0.81, 0), Color("f2d4ad"))
		_label(("你 · " if own else "居民 · ") + resident.actorId, at + Vector3(0, 1.21, 0))
	set_selection(selected)

func set_selection(cell: Vector2i) -> void:
	selected = cell
	marker.visible = cell.x >= 0 and cell.x < 8 and cell.y >= 0 and cell.y < 8
	marker.position = Vector3(cell.x, 0.055, cell.y)

func screen_cell(point: Vector2) -> Vector2i:
	var origin = camera.project_ray_origin(point)
	var direction = camera.project_ray_normal(point)
	var query = PhysicsRayQueryParameters3D.create(origin, origin + direction * 100)
	var picked = scene.get_world_3d().direct_space_state.intersect_ray(query)
	if not picked.is_empty() and picked.collider.has_meta("cell"):
		return picked.collider.get_meta("cell")
	var hit = Plane(Vector3.UP, 0).intersects_ray(origin, direction)
	if hit == null:
		return Vector2i(-1, -1)
	return Vector2i(roundi(hit.x), roundi(hit.z))

func _input_map(event: InputEvent) -> void:
	if event is InputEventMouseButton and event.pressed:
		if event.button_index == MOUSE_BUTTON_LEFT:
			var cell = screen_cell(event.position)
			if cell.x >= 0 and cell.x < 8 and cell.y >= 0 and cell.y < 8:
				set_selection(cell)
				cell_selected.emit(cell)
		elif event.button_index == MOUSE_BUTTON_WHEEL_UP:
			camera.size = maxf(7.5, camera.size - 0.5)
		elif event.button_index == MOUSE_BUTTON_WHEEL_DOWN:
			camera.size = minf(15, camera.size + 0.5)
