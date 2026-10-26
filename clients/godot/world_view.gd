extends SubViewportContainer
## Continuous landscape. All collision and resource facts come from World.Server.
signal ground_clicked(point: Vector2, node_id: String)
signal ground_hovered(point: Vector2)

var viewport: SubViewport
var scene: Node3D
var camera: Camera3D
var terrain: Node3D
var objects: Node3D
var effects: Node3D
var actors: Dictionary = {}
var targets: Dictionary = {}
var tree_nodes: Dictionary = {}
var structure_labels: Dictionary = {}
var caption_font: SystemFont
var self_ring_material: StandardMaterial3D
var resident_ring_material: StandardMaterial3D
var world_instance := ""
var own_actor = ""
var centerline: Array = []
var zoom = 18.0
var focus = Vector3(8, 0, 9)
var initialized = false
var object_stamp = ""
var marker: MeshInstance3D
var ghost: MeshInstance3D
var route_dots: MultiMeshInstance3D
var bridges: Array = []
var clock = 0.0
var gather_effect = 0.0
var foliage_materials: Array[StandardMaterial3D] = []
var trunk_material: StandardMaterial3D

func _ready() -> void:
	stretch = true
	mouse_filter = Control.MOUSE_FILTER_PASS
	viewport = SubViewport.new()
	viewport.own_world_3d = true
	viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	viewport.msaa_3d = Viewport.MSAA_2X
	add_child(viewport)
	scene = Node3D.new()
	viewport.add_child(scene)
	camera = Camera3D.new()
	camera.projection = Camera3D.PROJECTION_ORTHOGONAL
	camera.size = zoom
	camera.far = 180
	scene.add_child(camera)
	camera.make_current()
	var sun = DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-48, -35, 0)
	sun.light_color = Color("fff0cf")
	sun.light_energy = 0.85
	sun.light_angular_distance = 2.0
	sun.shadow_opacity = 0.65
	sun.shadow_enabled = true
	sun.directional_shadow_max_distance = 80
	scene.add_child(sun)
	var environment = WorldEnvironment.new()
	var env = Environment.new()
	env.background_mode = Environment.BG_COLOR
	env.background_color = Color("b5c7bc")
	env.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	env.ambient_light_color = Color("c2d9d4")
	env.ambient_light_energy = 0.7
	env.tonemap_mode = Environment.TONE_MAPPER_FILMIC
	environment.environment = env
	scene.add_child(environment)
	terrain = Node3D.new()
	scene.add_child(terrain)
	objects = Node3D.new()
	scene.add_child(objects)
	effects = Node3D.new()
	scene.add_child(effects)
	caption_font = SystemFont.new()
	caption_font.font_names = PackedStringArray(["Noto Sans CJK SC", "sans-serif"])
	self_ring_material = material(Color("e2c270"))
	resident_ring_material = material(Color("8fbbb8"))
	for tint in ["4c713e", "638746", "7e984f", "3b633d"]:
		foliage_materials.append(material(Color(tint)))
	trunk_material = material(Color("795b3e"))
	marker = mesh(scene, CylinderMesh.new(), Vector3.ZERO, material(Color("e8cd7b")))
	marker.mesh.top_radius = 0.18
	marker.mesh.bottom_radius = 0.18
	marker.mesh.height = 0.025
	marker.visible = false
	route_dots = MultiMeshInstance3D.new()
	route_dots.multimesh = MultiMesh.new()
	route_dots.multimesh.transform_format = MultiMesh.TRANSFORM_3D
	var dot := CylinderMesh.new()
	dot.top_radius = 0.045
	dot.bottom_radius = 0.045
	dot.height = 0.015
	route_dots.multimesh.mesh = dot
	route_dots.multimesh.instance_count = 256
	route_dots.multimesh.visible_instance_count = 0
	route_dots.material_override = marker.material_override
	scene.add_child(route_dots)
	ghost = mesh(scene, BoxMesh.new(), Vector3.ZERO, material(Color(0.8, 0.9, 0.7, 0.55)))
	ghost.visible = false
	gui_input.connect(_pointer)

func material(color: Color) -> StandardMaterial3D:
	var mat = StandardMaterial3D.new()
	mat.albedo_color = color.srgb_to_linear()
	mat.roughness = 0.93
	if color.a < 1:
		mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
	return mat

func mesh(parent: Node, shape: Mesh, at: Vector3, mat: Material) -> MeshInstance3D:
	var item = MeshInstance3D.new()
	item.mesh = shape
	item.material_override = mat
	item.position = at
	parent.add_child(item)
	return item

func _caption(parent: Node, text: String, at: Vector3, color: Color) -> Label3D:
	var label := Label3D.new()
	label.text = text
	label.font = caption_font
	label.font_size = 36
	label.pixel_size = 0.009
	label.outline_size = 8
	label.outline_modulate = Color("24362c")
	label.modulate = color
	label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	label.no_depth_test = true
	label.render_priority = 10
	label.outline_render_priority = 9
	label.position = at
	parent.add_child(label)
	return label

func _clear_children(parent: Node) -> void:
	for child: Node in parent.get_children():
		parent.remove_child(child)
		child.queue_free()

func _reset_world() -> void:
	# A new connection is a new visual baseline, even at the same actor/version.
	_clear_children(terrain)
	_clear_children(objects)
	_clear_children(effects)
	for actor: Node3D in actors.values():
		scene.remove_child(actor)
		actor.queue_free()
	actors.clear()
	targets.clear()
	tree_nodes.clear()
	structure_labels.clear()
	object_stamp = ""
	initialized = false
	gather_effect = 0.0
	clear_route()
	ghost.visible = false

func _resident_name(id: String) -> String:
	return "你 · %s" % id if id == own_actor else "居民 %s" % id

func _update_identity() -> void:
	for id: String in actors:
		var actor: Node3D = actors[id]
		var ring: MeshInstance3D = actor.get_node("IdentityRing")
		ring.material_override = self_ring_material if id == own_actor else resident_ring_material
		var label: Label3D = actor.get_node("Nameplate")
		label.text = _resident_name(id)
		label.modulate = Color("ffe2a3") if id == own_actor else Color("cbe7e2")
	for entry: Dictionary in structure_labels.values():
		var owner: String = entry.owner
		entry.label.text = "%s\n%s 建造" % [entry.title, _resident_name(owner)]

func river_x(z: float) -> float:
	if centerline.size() < 2:
		return 16
	var i = 0
	while i < centerline.size()-2 and float(centerline[i+1][1]) < z:
		i += 1
	var span = float(centerline[i+1][1])-float(centerline[i][1])
	return lerpf(float(centerline[i][0]),float(centerline[i+1][0]),(z-float(centerline[i][1]))/span)

func height_at(x: float, z: float) -> float:
	var away = absf(x - river_x(z)) - 1.4
	var height = 0.22 + sin(x * 0.27) * 0.1 + cos(z * 0.31) * 0.08
	return lerpf(-0.24, height, smoothstep(-0.12, 1.05, away))

func _landscape(observation: Dictionary) -> void:
	centerline = observation.terrain.river.centerline
	var st = SurfaceTool.new()
	st.begin(Mesh.PRIMITIVE_TRIANGLES)
	var grass = material(Color.WHITE)
	grass.vertex_color_use_as_albedo = true
	for row in range(-32, 80):
		var z = row * 0.5
		for column in range(-32, 96):
			var x = column * 0.5
			for corner in [Vector2(0,0),Vector2(1,0),Vector2(0,1),Vector2(1,0),Vector2(1,1),Vector2(0,1)]:
				var px = x + corner.x * 0.5
				var pz = z + corner.y * 0.5
				var n = (sin(px * 0.46 + sin(pz * 0.4)) + cos(pz * 0.7)) * 0.5
				var edge = absf(px - river_x(pz)) - 1.4
				var color = Color("a4aa78").lerp(Color("83945f"), n * 0.35 + 0.35)
				color = Color("a09a7c").lerp(color, smoothstep(0.2, 1.4, edge))
				st.set_color(color.srgb_to_linear())
				st.set_normal(Vector3.UP)
				st.add_vertex(Vector3(px, height_at(px, pz), pz))
	mesh(terrain, st.commit(), Vector3.ZERO, grass)
	var water = SurfaceTool.new()
	water.begin(Mesh.PRIMITIVE_TRIANGLES)
	for row in range(-32, 80):
		var z = row * 0.5
		var a = Vector3(river_x(z)-1.4, 0.015, z)
		var b = Vector3(river_x(z)+1.4, 0.015, z)
		var c = Vector3(river_x(z+0.5)-1.4, 0.015, z+0.5)
		var d = Vector3(river_x(z+0.5)+1.4, 0.015, z+0.5)
		for point in [a,c,b,b,c,d]:
			water.add_vertex(point)
	water.generate_normals()
	var water_mat = ShaderMaterial.new()
	water_mat.shader = load("res://river.gdshader")
	mesh(terrain, water.commit(), Vector3.ZERO, water_mat)
	var rng = RandomNumberGenerator.new()
	rng.seed = 71643
	# Ground cover is instanced in one draw; it does not define navigation cells.
	var blades = SurfaceTool.new()
	blades.begin(Mesh.PRIMITIVE_TRIANGLES)
	for i in 1700:
		var x = rng.randf_range(-10, 42)
		var z = rng.randf_range(-10, 34)
		if absf(x-river_x(z)) < 2.1:
			continue
		var base = Vector3(x,height_at(x,z),z)
		var size = rng.randf_range(0.12,0.34)
		var tint = Color("819954").lerp(Color("a2ab65"),rng.randf()).srgb_to_linear()
		for angle in [rng.randf_range(0,PI),rng.randf_range(0,PI)]:
			var side = Vector3(cos(angle),0,sin(angle))*size*0.35
			for point in [base-side,base+Vector3(0,size,0),base+side]:
				blades.set_color(tint)
				blades.add_vertex(point)
	blades.generate_normals()
	var blade_mat = material(Color.WHITE)
	blade_mat.vertex_color_use_as_albedo = true
	blade_mat.cull_mode = BaseMaterial3D.CULL_DISABLED
	mesh(terrain, blades.commit(),Vector3.ZERO,blade_mat)
	# Forest continues beyond the playable clearing; these distant silhouettes are scenery.
	for i in 48:
		var x = rng.randf_range(-9,41)
		var z = rng.randf_range(-9,33)
		if x > -1.5 and x < 33.5 and z > -1.5 and z < 25.5:
			continue
		if absf(x-river_x(z)) < 2.5:
			continue
		_tree(terrain,Vector2(x,z),"",1,rng.randf_range(0.8,1.3))
	for rock in observation.terrain.obstacles:
		var at = Vector2(rock.position[0],rock.position[1])
		var shape = SphereMesh.new()
		shape.radial_segments = 7
		shape.rings = 3
		shape.radius = rock.radius
		shape.height = rock.radius * 1.5
		var item = mesh(terrain,shape,Vector3(at.x,height_at(at.x,at.y)+rock.radius*0.48,at.y),material(Color("858a78")))
		item.rotation.y = rng.randf_range(0,TAU)
		var small = SphereMesh.new()
		small.radius = rock.radius * 0.35
		small.height = rock.radius * 0.5
		small.radial_segments = 6
		small.rings = 2
		mesh(terrain,small,item.position+Vector3(rock.radius*0.55,-rock.radius*0.3,0.4),material(Color("9a9b85")))
	initialized = true

func _tree(parent: Node, at: Vector2, id: String, wood: int, scale_factor: float = 1.0) -> Node3D:
	var root = Node3D.new()
	parent.add_child(root)
	root.position = Vector3(at.x,height_at(at.x,at.y),at.y)
	var trunk = CylinderMesh.new()
	trunk.top_radius = 0.16 if wood > 0 else 0.31
	trunk.bottom_radius = 0.32
	trunk.height = 2.1 if wood > 0 else 0.25
	trunk.radial_segments = 7
	mesh(root,trunk,Vector3(0,trunk.height/2,0),trunk_material)
	if wood > 0:
		var crowns = [Vector3(-0.5,2.0,0.2),Vector3(0.65,2.25,0),Vector3(0,2.8,-0.15),Vector3(0.15,2.1,0.6)]
		for i in crowns.size():
			var crown = SphereMesh.new()
			crown.radius = 0.92 if i < 3 else 0.7
			crown.height = crown.radius * 1.75
			crown.radial_segments = 8
			crown.rings = 4
			var crown_mat = foliage_materials[i]
			if not id.is_empty():
				crown_mat = crown_mat.duplicate()
				crown_mat.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
			var crown_node = mesh(root,crown,crowns[i],crown_mat)
			crown_node.set_meta("crown",true)
		if not id.is_empty():
			var pick = StaticBody3D.new()
			pick.collision_layer = 2
			pick.collision_mask = 0
			pick.set_meta("node_id",id)
			var collider = CollisionShape3D.new()
			var shape = CapsuleShape3D.new()
			shape.radius = 0.8
			shape.height = 3.2
			collider.shape = shape
			collider.position.y = 1.6
			pick.add_child(collider)
			root.add_child(pick)
	root.scale = Vector3.ONE*scale_factor
	return root

func _person(id: String) -> Node3D:
	var root = Node3D.new()
	scene.add_child(root)
	var body = Node3D.new()
	body.name = "Body"
	root.add_child(body)
	var cloth = material(Color("c58d52") if id == "a1" else Color("6a8f91"))
	var skin = material(Color("d1ac7d"))
	var torso = CylinderMesh.new()
	torso.top_radius = 0.2
	torso.bottom_radius = 0.3
	torso.height = 0.52
	torso.radial_segments = 7
	mesh(body,torso,Vector3(0,0.8,0),cloth)
	var head = SphereMesh.new()
	head.radius = 0.22
	head.height = 0.43
	head.radial_segments = 10
	head.rings = 5
	mesh(body,head,Vector3(0,1.26,0),skin)
	var hair = SphereMesh.new()
	hair.radius = 0.225
	hair.height = 0.3
	hair.radial_segments = 8
	hair.rings = 3
	mesh(body,hair,Vector3(0,1.4,0.025),material(Color("493e32")))
	for side in [-1,1]:
		var leg = Node3D.new()
		leg.name = "LegL" if side < 0 else "LegR"
		leg.position = Vector3(side*0.12,0.57,0)
		body.add_child(leg)
		var limb = CapsuleMesh.new()
		limb.radius = 0.085
		limb.height = 0.53
		mesh(leg,limb,Vector3(0,-0.25,0),skin)
		var arm = Node3D.new()
		arm.name = "ArmL" if side < 0 else "ArmR"
		arm.position = Vector3(side*0.26,0.98,0)
		body.add_child(arm)
		var hand = CapsuleMesh.new()
		hand.radius = 0.07
		hand.height = 0.5
		mesh(arm,hand,Vector3(0,-0.2,0),skin)
	var ring = CylinderMesh.new()
	ring.top_radius = 0.36
	ring.bottom_radius = 0.36
	ring.height = 0.018
	mesh(root,ring,Vector3(0,0.025,0),resident_ring_material).name = "IdentityRing"
	_caption(root, "", Vector3(0,1.9,0), Color.WHITE).name = "Nameplate"
	return root

func _material_source(source: Dictionary) -> void:
	var center := Vector2(source.position[0], source.position[1])
	var y := height_at(center.x, center.y) + 0.05
	var tint := material(Color("a4bb6b") if source.active else Color("a6946a"))
	for side in [-1, 1]:
		var horizontal := BoxMesh.new()
		horizontal.size = Vector3(2.04, 0.025, 0.065)
		mesh(objects, horizontal, Vector3(center.x, y, center.y + side), tint)
		var vertical := BoxMesh.new()
		vertical.size = Vector3(0.065, 0.025, 2.04)
		mesh(objects, vertical, Vector3(center.x + side, y, center.y), tint)
	for i in int(source.stockWood):
		var log_mesh := BoxMesh.new()
		log_mesh.size = Vector3(0.46, 0.12, 0.16)
		mesh(objects, log_mesh, Vector3(center.x - 0.3 + (i % 2) * 0.6, y + 0.08 + (i / 2) * 0.14, center.y), trunk_material)
	var caption := _caption(objects, "采集区 · %d 木材\n保留地，不能建造" % source.stockWood,
		Vector3(center.x, y + 0.15, center.y + 1.8), Color("e7e9b5"))
	caption.font_size = 28

func update_world(observation: Dictionary, connection_changed := false) -> void:
	var instance: String = observation.world.get("instanceId", "")
	if connection_changed or instance != world_instance:
		_reset_world()
	world_instance = instance
	own_actor = observation.identity.actorId
	bridges = observation.entities.filter(func(entity): return entity.definitionId == "bridge")
	if not initialized:
		_landscape(observation)
		focus = Vector3(observation.self.position[0],0,observation.self.position[1])
	var source: Dictionary = observation.get("materialAccess", {})
	var stamp = JSON.stringify([observation.resourceNodes,observation.entities,source.get("active"),source.get("stockWood")])
	if stamp != object_stamp:
		object_stamp = stamp
		_clear_children(objects)
		tree_nodes.clear()
		structure_labels.clear()
		if not source.is_empty():
			_material_source(source)
		for tree in observation.resourceNodes:
			tree_nodes[tree.nodeId] = _tree(objects,Vector2(tree.position[0],tree.position[1]),tree.nodeId,tree.remainingWood)
		for entity in observation.entities:
			var bridge = entity.definitionId == "bridge"
			var length = 4.8 if bridge else 2.0
			var width = 1.6 if bridge else 2.0
			var p = Vector3(entity.position[0],0.23 if bridge else height_at(entity.position[0],entity.position[1])+0.08,entity.position[1])
			var label := _caption(objects, "", p + Vector3(0,1.15,0), Color("f0e2c0"))
			label.font_size = 30
			structure_labels[entity.entityId] = {"label":label, "owner":entity.ownerActorId,
				"title":"木桥" if bridge else "平台"}
			for i in int(length/0.2):
				var plank = BoxMesh.new()
				plank.size = Vector3(0.18,0.12,width)
				mesh(objects,plank,p+Vector3(-length/2+i*0.2+0.1,0,0),material(Color("a48553") if i%3 else Color("957447")))
			if bridge:
				for side in [-1,1]:
					var rail = BoxMesh.new()
					rail.size = Vector3(length,0.1,0.08)
					mesh(objects,rail,p+Vector3(0,0.6,side*width*0.5),trunk_material)
					for x in [-2.1,0,2.1]:
						var post = BoxMesh.new()
						post.size = Vector3(0.12,0.75,0.12)
						mesh(objects,post,p+Vector3(x,0.25,side*width*0.5),trunk_material)
	var observed_actors: Dictionary = {}
	for resident in observation.residents:
		observed_actors[resident.actorId] = true
		var p = Vector3(resident.position[0],height_at(resident.position[0],resident.position[1]),resident.position[1])
		for entity in observation.entities:
			if entity.definitionId == "bridge" and absf(p.x-entity.position[0]) < 2.4 and absf(p.z-entity.position[1]) < 0.8:
				p.y = 0.31
			elif entity.definitionId == "platform" and absf(p.x-entity.position[0]) < 1 and absf(p.z-entity.position[1]) < 1:
				p.y += 0.15
		if not actors.has(resident.actorId):
			actors[resident.actorId] = _person(resident.actorId)
			actors[resident.actorId].position = p
		targets[resident.actorId] = p
	for id: String in actors.keys():
		if not observed_actors.has(id):
			var actor: Node3D = actors[id]
			scene.remove_child(actor)
			actor.queue_free()
			actors.erase(id)
			targets.erase(id)
	_update_identity()

func show_destination(point: Vector2) -> void:
	marker.position = _route_position(point)
	marker.visible = true

func _route_position(point: Vector2) -> Vector3:
	var height := height_at(point.x, point.y) + 0.04
	for bridge: Dictionary in bridges:
		if absf(point.x - bridge.position[0]) < 2.4 and absf(point.y - bridge.position[1]) < 0.8:
			height = 0.35
	return Vector3(point.x, height, point.y)

func show_route(points: PackedVector2Array) -> void:
	show_destination(points[-1])
	trim_route(points[0], points)

func trim_route(start: Vector2, points: PackedVector2Array) -> void:
	var previous := start
	var remainder := 0.3
	var count := 0
	for point: Vector2 in points:
		var length := previous.distance_to(point)
		while remainder < length and count < 256:
			var at := previous.lerp(point, remainder / length)
			route_dots.multimesh.set_instance_transform(count, Transform3D(Basis.IDENTITY, _route_position(at)))
			count += 1
			remainder += 0.45
		remainder -= length
		previous = point
	route_dots.multimesh.visible_instance_count = count

func clear_route() -> void:
	marker.visible = false
	route_dots.multimesh.visible_instance_count = 0

func show_build(point: Vector2, recipe: String, valid: bool) -> void:
	ghost.visible = not recipe.is_empty()
	if not ghost.visible:
		return
	ghost.mesh.size = Vector3(4.8,0.15,1.6) if recipe == "bridge.v1" else Vector3(2,0.15,2)
	ghost.position = Vector3(point.x,0.25,point.y)
	ghost.material_override = material(Color(0.6,0.84,0.55,0.6) if valid else Color(0.85,0.35,0.27,0.6))

func gather_feedback(node_id: String) -> void:
	gather_effect = 0.45
	if tree_nodes.has(node_id):
		var tree: Node3D = tree_nodes[node_id]
		var tween = tree.create_tween()
		tween.tween_property(tree,"rotation:z",0.065,0.09)
		tween.tween_property(tree,"rotation:z",-0.04,0.1)
		tween.tween_property(tree,"rotation:z",0.0,0.15)
	if actors.has(own_actor):
		var label := _caption(effects, "+1 木材", actors[own_actor].position + Vector3(0,2.4,0), Color("f1d291"))
		label.font_size = 44
		label.pixel_size = 0.008
		var tween = label.create_tween()
		tween.tween_property(label,"position:y",label.position.y+0.7,0.8)
		tween.parallel().tween_property(label,"modulate:a",0.0,0.8)
		tween.tween_callback(label.queue_free)

func _process(delta: float) -> void:
	clock += delta
	gather_effect = maxf(0,gather_effect-delta)
	for id in actors:
		var actor: Node3D = actors[id]
		var before = actor.position
		actor.position = actor.position.lerp(targets[id],1-exp(-20*delta))
		var motion = actor.position-before
		var moving = motion.length() > 0.0008
		var body: Node3D = actor.get_node("Body")
		if moving:
			body.rotation.y = lerp_angle(body.rotation.y,atan2(-motion.x,-motion.z),1-exp(-15*delta))
		var swing = sin(clock*13)*0.55 if moving else 0.0
		body.get_node("LegL").rotation.x = swing
		body.get_node("LegR").rotation.x = -swing
		body.get_node("ArmL").rotation.x = -swing*0.7
		body.get_node("ArmR").rotation.x = -sin(gather_effect/0.45*PI)*1.6 if id == own_actor and gather_effect > 0 else swing*0.7
	if actors.has(own_actor):
		var p: Vector3 = actors[own_actor].position
		for tree in tree_nodes.values():
			var fades = tree.position.z > p.z-0.4 and tree.position.z < p.z+3.0 and absf(tree.position.x-p.x)<1.4
			for child in tree.get_children():
				if child is MeshInstance3D and child.get_meta("crown",false):
					var alpha: float = child.material_override.albedo_color.a
					child.material_override.albedo_color.a = lerpf(alpha,0.3 if fades else 1.0,1-exp(-9*delta))
		var desired = Vector3(clampf(p.x,4,28),0,clampf(p.z,3,21))
		focus = focus.lerp(desired,1-exp(-5*delta))
	camera.size = zoom
	camera.position = focus+Vector3(0,18,18)
	camera.look_at(focus)

func _point(screen: Vector2) -> Vector2:
	var origin = camera.project_ray_origin(screen)
	var direction = camera.project_ray_normal(screen)
	var hit = Plane(Vector3.UP,0.15).intersects_ray(origin,direction)
	return Vector2(hit.x,hit.z) if hit != null else Vector2(-100,-100)

func _pointer(event: InputEvent) -> void:
	if event is InputEventMouseMotion:
		ground_hovered.emit(_point(event.position))
	if not event is InputEventMouseButton or not event.pressed:
		return
	if event.button_index == MOUSE_BUTTON_WHEEL_UP:
		zoom = maxf(11,zoom-1)
	elif event.button_index == MOUSE_BUTTON_WHEEL_DOWN:
		zoom = minf(28,zoom+1)
	elif event.button_index == MOUSE_BUTTON_LEFT:
		var origin = camera.project_ray_origin(event.position)
		var end = origin + camera.project_ray_normal(event.position)*100
		var query = PhysicsRayQueryParameters3D.create(origin,end,2)
		var hit = scene.get_world_3d().direct_space_state.intersect_ray(query)
		ground_clicked.emit(_point(event.position),str(hit.collider.get_meta("node_id","")) if not hit.is_empty() else "")
