extends Node3D

const Client = preload("res://world_client.gd")
const View = preload("res://world_view.gd")
var client: Node
var world_view: SubViewportContainer
var inventory_label: Label
var status_label: Label
var target_label: Label
var gather_button: Button
var platform_button: Button
var bridge_button: Button
var query_button: Button
var retry_button: Button
var url_input: LineEdit
var token_input: LineEdit
var connection_panel: PanelContainer
var selected_node = ""
var destination = Vector2.ZERO
var walking = false
var build_recipe = ""
var build_point = Vector2.ZERO
var cooldown = 0.0
var poll_time = 0.0
var motion_elapsed = 0.08
var known_version = -1
var known_actor = ""
var receipt_id = ""
var input_suspended = false
var message_until = 0.0

func _ready() -> void:
	client = Client.new()
	add_child(client)
	_build_ui()
	client.changed.connect(_render)
	_render()
	var path = OS.get_environment("WORLD_ACCESS_FILE")
	if not path.is_empty() and FileAccess.file_exists(path):
		var access = JSON.parse_string(FileAccess.get_file_as_string(path))
		var actor = OS.get_environment("WORLD_ACTOR")
		if actor.is_empty():
			actor = "a1"
		if access is Dictionary and access.get("sessions",{}).get(actor,{}).get("token") is String:
			await client.connect_world(url_input.text,access.sessions[actor].token)
			connection_panel.visible = not client.healthy

func _style(color: Color) -> StyleBoxFlat:
	var style = StyleBoxFlat.new()
	style.bg_color = color
	style.set_corner_radius_all(8)
	style.content_margin_left = 16
	style.content_margin_right = 16
	style.content_margin_top = 10
	style.content_margin_bottom = 10
	return style

func _text(parent: Node, text: String, font_size: int = 16, color: Color = Color("e9ead8")) -> Label:
	var label = Label.new()
	label.text = text
	label.add_theme_font_size_override("font_size",font_size)
	label.add_theme_color_override("font_color",color)
	parent.add_child(label)
	return label

func _button(parent: Node, text: String, callback: Callable) -> Button:
	var button = Button.new()
	button.text = text
	button.focus_mode = Control.FOCUS_NONE
	button.custom_minimum_size.y = 38
	button.pressed.connect(callback)
	parent.add_child(button)
	return button

func _panel(parent: Control, anchor: int, margin: Vector2) -> PanelContainer:
	var panel = PanelContainer.new()
	panel.set_anchors_and_offsets_preset(anchor)
	panel.position += margin
	panel.add_theme_stylebox_override("panel",_style(Color(0.09,0.15,0.12,0.88)))
	parent.add_child(panel)
	return panel

func _build_ui() -> void:
	var layer = CanvasLayer.new()
	add_child(layer)
	var root = Control.new()
	root.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	root.mouse_filter = Control.MOUSE_FILTER_IGNORE
	layer.add_child(root)
	var theme = Theme.new()
	var font = SystemFont.new()
	font.font_names = PackedStringArray(["Noto Sans CJK SC","sans-serif"])
	theme.default_font = font
	theme.default_font_size = 15
	for state in ["normal","hover","pressed","disabled"]:
		theme.set_stylebox(state,"Button",_style(Color("354c39") if state=="normal" else Color("506645") if state=="hover" else Color("253629")))
	theme.set_color("font_disabled_color","Button",Color("81917c"))
	root.theme = theme
	world_view = View.new()
	world_view.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	root.add_child(world_view)
	world_view.ground_clicked.connect(_clicked)
	world_view.ground_hovered.connect(_hovered)
	var top = _panel(root,Control.PRESET_TOP_LEFT,Vector2(24,24))
	var info = VBoxContainer.new()
	top.add_child(info)
	_text(info,"荒野  /  最初的居民",21)
	inventory_label = _text(info,"正在进入世界…",16,Color("e6c98a"))
	var controls = VBoxContainer.new()
	controls.set_anchors_and_offsets_preset(Control.PRESET_TOP_RIGHT)
	controls.offset_left = -190
	controls.offset_top = 24
	controls.offset_right = -24
	root.add_child(controls)
	_button(controls,"连接 / 切换居民",func():
		walking = false
		connection_panel.visible = not connection_panel.visible)
	connection_panel = _panel(root,Control.PRESET_TOP_RIGHT,Vector2(-420,80))
	connection_panel.custom_minimum_size.x = 396
	var connection = VBoxContainer.new()
	connection_panel.add_child(connection)
	_text(connection,"连接世界",19)
	url_input = LineEdit.new()
	url_input.text = OS.get_environment("WORLD_URL") if OS.has_environment("WORLD_URL") else "http://127.0.0.1:5089"
	connection.add_child(url_input)
	token_input = LineEdit.new()
	token_input.secret = true
	token_input.placeholder_text = "居民令牌"
	connection.add_child(token_input)
	_button(connection,"进入",func():
		walking = false
		var token = token_input.text
		token_input.clear()
		await client.connect_world(url_input.text,token)
		connection_panel.visible = not client.healthy)
	var bottom = PanelContainer.new()
	bottom.set_anchors_and_offsets_preset(Control.PRESET_CENTER_BOTTOM)
	bottom.offset_left = -326
	bottom.offset_right = 326
	bottom.offset_top = -158
	bottom.offset_bottom = -24
	bottom.add_theme_stylebox_override("panel",_style(Color(0.09,0.15,0.12,0.9)))
	root.add_child(bottom)
	var actions = VBoxContainer.new()
	bottom.add_child(actions)
	target_label = _text(actions,"走近树木，采集你的第一块木材。",16,Color("e6d5a5"))
	var row = HBoxContainer.new()
	row.add_theme_constant_override("separation",8)
	actions.add_child(row)
	gather_button = _button(row,"[E]  砍树",_gather)
	platform_button = _button(row,"[1]  平台 · 3 木材",func(): _begin_build("platform.v1"))
	bridge_button = _button(row,"[2]  木桥 · 6 木材",func(): _begin_build("bridge.v1"))
	query_button = _button(row,"查询原动作",func(): client.recover())
	retry_button = _button(row,"原样重试",func(): client.recover(true))
	status_label = _text(actions,"WASD 行走 · 点击地面前往 · 滚轮缩放 · Esc 取消",13,Color("b7c2a4"))

func position_2d() -> Vector2:
	var p = client.observation.get("self",{}).get("position",[0,0])
	return Vector2(p[0],p[1])

func _node(id: String) -> Dictionary:
	for tree in client.observation.get("resourceNodes",[]):
		if tree.nodeId == id:
			return tree
	return {}

func _nearest() -> Dictionary:
	var nearest: Dictionary = {}
	var distance = 1.6
	for tree in client.observation.get("resourceNodes",[]):
		var d = position_2d().distance_to(Vector2(tree.position[0],tree.position[1]))
		if tree.remainingWood > 0 and d <= distance:
			distance = d
			nearest = tree
	return nearest

func _render() -> void:
	var observation: Dictionary = client.observation
	query_button.visible = not client.pending.is_empty()
	retry_button.visible = not client.pending.is_empty()
	query_button.disabled = client.busy
	retry_button.disabled = client.busy
	var ready: bool = client.can_act()
	gather_button.disabled = not ready or _nearest().is_empty()
	platform_button.disabled = not ready or observation.get("self",{}).get("inventory",{}).get("wood",0) < 3
	bridge_button.disabled = not ready or observation.get("self",{}).get("inventory",{}).get("wood",0) < 6
	if observation.is_empty():
		status_label.text = client.message
		return
	if observation.stateVersion != known_version or observation.identity.actorId != known_actor:
		known_version = observation.stateVersion
		if observation.identity.actorId != known_actor:
			walking = false
			selected_node = ""
		known_actor = observation.identity.actorId
		world_view.update_world(observation)
	inventory_label.text = "居民 %s   ·   木材 %d" % [observation.identity.actorId,observation.self.inventory.wood]
	if not client.last_receipt.is_empty() and client.last_receipt.commandId != receipt_id:
		receipt_id = client.last_receipt.commandId
		if client.last_receipt.status == "committed" and client.last_receipt.result.action == "walk":
			if client.last_receipt.result.get("blocked",false):
				walking = false
				world_view.marker.visible = false
		elif client.last_receipt.status == "rejected":
			status_label.text = client.message
			message_until = Time.get_ticks_msec()/1000.0+3
		else:
			if client.last_receipt.result.action == "gather":
				world_view.gather_feedback(client.last_receipt.result.nodeId)
			status_label.text = "采集完成  +1 木材" if client.last_receipt.result.action == "gather" else "建造完成"
			message_until = Time.get_ticks_msec()/1000.0+2
	if not client.healthy and not client.busy:
		input_suspended = true
		walking = false
		status_label.text = client.message
	elif Time.get_ticks_msec()/1000.0 > message_until:
		status_label.text = "WASD 行走 · 点击地面前往 · 滚轮缩放 · Esc 取消"
	if not build_recipe.is_empty():
		target_label.text = "选择建造位置 · 左键确认 · Esc 取消"
	elif not _nearest().is_empty():
		target_label.text = "树木就在身旁，按 E 采集木材。"
	else:
		target_label.text = "探索河谷，寻找树木与合适的营地。"

func _clicked(point: Vector2, node_id: String) -> void:
	while client.busy:
		await client.changed
	if not client.can_act():
		return
	if not build_recipe.is_empty():
		_hovered(point)
		if _placement_valid(build_point,build_recipe):
			var action = {"type":"build","recipeId":build_recipe,"at":[build_point.x,build_point.y]}
			_cancel()
			await client.send_action(action)
		return
	selected_node = node_id
	if not node_id.is_empty():
		var tree = _node(node_id)
		destination = Vector2(tree.position[0],tree.position[1])
	else:
		destination = Vector2(clampf(point.x,0.28,31.72),clampf(point.y,0.28,23.72))
	walking = true
	world_view.show_destination(destination)

func _hovered(point: Vector2) -> void:
	if build_recipe.is_empty():
		return
	build_point = point
	if build_recipe == "bridge.v1":
		build_point.x = world_view.river_x(point.y)
	world_view.show_build(build_point,build_recipe,_placement_valid(build_point,build_recipe))

func _placement_valid(point: Vector2, recipe: String) -> bool:
	var bridge = recipe == "bridge.v1"
	var half = Vector2(2.4,0.8) if bridge else Vector2.ONE
	if position_2d().distance_to(point)>3.2 or point.x<half.x or point.y<half.y or point.x>32-half.x or point.y>24-half.y:
		return false
	if not bridge:
		for z in [point.y-1,point.y+1]:
			if point.x+1>world_view.river_x(z)-1.4 and point.x-1<world_view.river_x(z)+1.4:
				return false
	for obstacle in client.observation.get("terrain",{}).get("obstacles",[]) + client.observation.get("resourceNodes",[]):
		if obstacle.get("remainingWood",1)==0:
			continue
		var p = Vector2(obstacle.position[0],obstacle.position[1])
		var closest = Vector2(clampf(p.x,point.x-half.x,point.x+half.x),clampf(p.y,point.y-half.y,point.y+half.y))
		if p.distance_to(closest) < obstacle.get("radius",0.45):
			return false
	for entity in client.observation.get("entities",[]):
		var other = Vector2(2.4,0.8) if entity.definitionId=="bridge" else Vector2.ONE
		if absf(point.x-entity.position[0])<half.x+other.x and absf(point.y-entity.position[1])<half.y+other.y:
			return false
	return true

func _begin_build(recipe: String) -> void:
	while client.busy:
		await client.changed
	if not client.can_act():
		return
	walking = false
	build_recipe = recipe
	_hovered(position_2d()+Vector2(0,-2))
	_render()

func _cancel() -> void:
	walking = false
	selected_node = ""
	build_recipe = ""
	world_view.ghost.visible = false
	world_view.marker.visible = false
	_render()

func _gather() -> void:
	walking = false
	while client.busy:
		await client.changed
	if not client.can_act():
		return
	var tree = _nearest()
	if tree.is_empty():
		return
	walking = false
	await client.send_action({"type":"gather","nodeId":tree.nodeId})

func _unhandled_key_input(event: InputEvent) -> void:
	if not event is InputEventKey or not event.pressed or event.echo or get_viewport().gui_get_focus_owner() is LineEdit:
		return
	match event.physical_keycode:
		KEY_E: _gather()
		KEY_1: _begin_build("platform.v1")
		KEY_2: _begin_build("bridge.v1")
		KEY_ESCAPE: _cancel()

func _physics_process(delta: float) -> void:
	cooldown -= delta
	poll_time += delta
	motion_elapsed = minf(0.2,motion_elapsed+delta)
	if client == null:
		return
	if not client.can_act():
		if not client.busy and poll_time >= 1.0 and not client.token.is_empty():
			poll_time = 0
			await client.refresh()
		return
	var direction = Vector2.ZERO
	if not get_viewport().gui_get_focus_owner() is LineEdit and build_recipe.is_empty():
		direction = Vector2(int(Input.is_physical_key_pressed(KEY_D) or Input.is_physical_key_pressed(KEY_RIGHT))-int(Input.is_physical_key_pressed(KEY_A) or Input.is_physical_key_pressed(KEY_LEFT)),int(Input.is_physical_key_pressed(KEY_S) or Input.is_physical_key_pressed(KEY_DOWN))-int(Input.is_physical_key_pressed(KEY_W) or Input.is_physical_key_pressed(KEY_UP))).normalized()
	if direction == Vector2.ZERO:
		input_suspended = false
	elif input_suspended:
		direction = Vector2.ZERO
	if direction != Vector2.ZERO:
		walking = false
		world_view.marker.visible = false
	elif walking:
		var stop_distance = 1.3 if not selected_node.is_empty() else 0.06
		if position_2d().distance_to(destination) <= stop_distance:
			walking = false
			world_view.marker.visible = false
		else:
			direction = position_2d().direction_to(destination)
	if direction != Vector2.ZERO and cooldown <= 0:
		cooldown = 0.08
		poll_time = 0
		var step_distance = clampf(motion_elapsed*3,0.01,0.6)
		motion_elapsed = 0
		var distance = minf(step_distance,position_2d().distance_to(destination)) if walking else step_distance
		var to = position_2d()+direction*distance
		await client.send_action({"type":"walk","to":[to.x,to.y]})
	elif poll_time >= 0.6 and not client.busy:
		poll_time = 0
		await client.refresh()

func _notification(what: int) -> void:
	if what == NOTIFICATION_APPLICATION_FOCUS_OUT:
		walking = false
		input_suspended = true
