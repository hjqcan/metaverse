extends Node3D

const Client = preload("res://world_client.gd")
const View = preload("res://world_view.gd")
const Navigation = preload("res://world_navigation.gd")
const TransferPanel = preload("res://transfer_panel.gd")
var client: Node
var navigation: Node
var world_view: SubViewportContainer
var inventory_label: Label
var status_label: Label
var target_label: Label
var gather_button: Button
var platform_button: Button
var bridge_button: Button
var query_button: Button
var retry_button: Button
var transfer_button: Button
var transfer_panel: PanelContainer
var transfer_history: Label
var url_input: LineEdit
var token_input: LineEdit
var connection_panel: PanelContainer
var selected_node = ""
var destination = Vector2.ZERO
var walking = false
var planning = false
var route := PackedVector2Array()
var route_index := 0
var route_request := 0
var build_recipe = ""
var build_point = Vector2.ZERO
var cooldown = 0.0
var poll_time = 0.0
var motion_elapsed = 0.08
var known_version = -1
var known_actor = ""
var known_connection = -1
var receipt_id = ""
var input_suspended = false
var message_until = 0.0

func _ready() -> void:
	client = Client.new()
	add_child(client)
	navigation = Navigation.new()
	add_child(navigation)
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
	transfer_history = _text(info,"",13,Color("b7c2a4"))
	transfer_history.hide()
	var controls = VBoxContainer.new()
	controls.set_anchors_and_offsets_preset(Control.PRESET_TOP_RIGHT)
	controls.offset_left = -190
	controls.offset_top = 24
	controls.offset_right = -24
	root.add_child(controls)
	_button(controls,"连接 / 切换居民",func():
		_stop_walk()
		transfer_panel.hide()
		connection_panel.visible = not connection_panel.visible)
	transfer_button = _button(controls,"赠送木材",func():
		_stop_walk()
		connection_panel.hide()
		transfer_panel.visible = not transfer_panel.visible)
	transfer_panel = TransferPanel.new()
	transfer_panel.set_anchors_and_offsets_preset(Control.PRESET_TOP_RIGHT)
	transfer_panel.offset_left = -420
	transfer_panel.offset_right = -24
	transfer_panel.offset_top = 125
	transfer_panel.add_theme_stylebox_override("panel", _style(Color(0.09,0.15,0.12,0.96)))
	root.add_child(transfer_panel)
	transfer_panel.requested.connect(_transfer)
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
		var token = token_input.text
		token_input.clear()
		_connect(url_input.text, token))
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

func _connect(url: String, secret: String) -> void:
	_stop_walk()
	var request := route_request
	while client.busy:
		await client.changed
	if request != route_request:
		return
	await client.connect_world(url, secret)
	connection_panel.visible = not client.healthy

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
	transfer_button.visible = Client.Evidence.transfer_supported(observation)
	transfer_button.disabled = not ready
	transfer_panel.update_world(observation, ready)
	if not transfer_button.visible:
		transfer_panel.hide()
	transfer_history.visible = transfer_button.visible
	var history: Array[String] = []
	for event in observation.get("recentTransfers", {}).get("items", []).slice(-3):
		if event.get("type") == "woodTransferred" and event.get("actorId") is String \
			and event.get("recipientActorId") is String and Client.Evidence.whole(event.get("quantity")):
			var sender = "你" if event.actorId == observation.get("self", {}).get("actorId") else event.actorId
			var recipient = "你" if event.recipientActorId == observation.get("self", {}).get("actorId") else event.recipientActorId
			history.append("%s → %s · %d 木材" % [sender, recipient, event.quantity])
	transfer_history.text = "最近交付\n" + "\n".join(history) if not history.is_empty() else "尚无木材交付记录"
	if observation.is_empty():
		status_label.text = client.message
		return
	var connection_changed: bool = client.connection_generation != known_connection
	if connection_changed or observation.stateVersion != known_version or observation.identity.actorId != known_actor:
		known_connection = client.connection_generation
		known_version = observation.stateVersion
		if connection_changed or observation.identity.actorId != known_actor:
			_stop_walk()
			selected_node = ""
			build_recipe = ""
			world_view.ghost.visible = false
			transfer_panel.hide()
			input_suspended = true
		if connection_changed:
			receipt_id = ""
			status_label.text = client.message
			message_until = Time.get_ticks_msec()/1000.0 + 3
		known_actor = observation.identity.actorId
		world_view.update_world(observation, connection_changed)
		if navigation.update_geometry(observation) and walking:
			_plan_walk(destination, selected_node)
	inventory_label.text = "居民 %s   ·   木材 %d" % [observation.identity.actorId,observation.self.inventory.wood]
	if not client.last_receipt.is_empty() and client.last_receipt.commandId != receipt_id:
		receipt_id = client.last_receipt.commandId
		if client.last_receipt.status == "committed" and client.last_receipt.result.action == "walk":
			if client.last_receipt.result.get("blocked",false):
				_stop_walk()
				status_label.text = "前路受阻，请重新选择目的地。"
				message_until = Time.get_ticks_msec()/1000.0+3
		elif client.last_receipt.status == "rejected":
			if client.last_receipt.get("error", {}).get("code") == "STALE_ACTOR_STATE":
				_stop_walk()
				input_suspended = true
			status_label.text = client.message
			message_until = Time.get_ticks_msec()/1000.0+3
		else:
			if client.last_receipt.result.action == "gather":
				world_view.gather_feedback(client.last_receipt.result.nodeId)
			if client.last_receipt.result.action == "transfer":
				status_label.text = "已向 %s 赠送 %d 木材" % [client.last_receipt.result.recipientActorId, client.last_receipt.result.quantity]
				transfer_panel.hide()
			else:
				status_label.text = "采集完成  +1 木材" if client.last_receipt.result.action == "gather" else "建造完成"
			message_until = Time.get_ticks_msec()/1000.0+2
	if not ready and not client.busy:
		input_suspended = true
		_stop_walk()
		status_label.text = client.message
	elif Time.get_ticks_msec()/1000.0 > message_until:
		status_label.text = "另一个世界的未确认动作已保留；切回原世界查询。" if client.foreign_pending > 0 else "WASD 行走 · 点击地面前往 · 滚轮缩放 · Esc 取消"
	if not build_recipe.is_empty():
		target_label.text = "选择建造位置 · 左键确认 · Esc 取消"
	elif not _nearest().is_empty():
		target_label.text = "树木就在身旁，按 E 采集木材。"
	else:
		target_label.text = "探索河谷，寻找树木与合适的营地。"

func _clicked(point: Vector2, node_id: String) -> void:
	if transfer_panel.visible:
		return
	_stop_walk()
	var request := route_request
	while client.busy:
		await client.changed
	if request != route_request or not client.can_act():
		return
	if not build_recipe.is_empty():
		_hovered(point)
		if _placement_valid(build_point,build_recipe):
			var action = {"type":"build","recipeId":build_recipe,"at":[build_point.x,build_point.y]}
			_cancel()
			await client.send_action(action)
		return
	await _plan_walk(point, node_id)

func _stop_walk() -> void:
	route_request += 1
	walking = false
	planning = false
	route.clear()
	route_index = 0
	if is_instance_valid(world_view):
		world_view.clear_route()

func _plan_walk(point: Vector2, node_id: String) -> void:
	_stop_walk()
	var request := route_request
	planning = true
	selected_node = node_id
	destination = point
	for i in 120:
		if request != route_request:
			return
		if navigation.is_ready() and not client.busy:
			break
		await get_tree().physics_frame
	if request != route_request:
		return
	planning = false
	if not client.can_act():
		return
	if node_id.is_empty():
		route = navigation.path(position_2d(), point)
	else:
		var tree := _node(node_id)
		if not tree.is_empty() and tree.remainingWood > 0:
			route = navigation.approach(position_2d(), Vector2(tree.position[0], tree.position[1]))
	if route.is_empty():
		status_label.text = "暂时无法到达那里，请选择可通行的位置。"
		message_until = Time.get_ticks_msec()/1000.0+3
		return
	destination = route[-1]
	walking = true
	world_view.show_route(route)
	status_label.text = "沿路线前往 · WASD / Esc 停止"
	message_until = Time.get_ticks_msec()/1000.0+2

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
	_stop_walk()
	var request := route_request
	while client.busy:
		await client.changed
	if request != route_request or not client.can_act():
		return
	build_recipe = recipe
	_hovered(position_2d()+Vector2(0,-2))
	_render()

func _cancel() -> void:
	transfer_panel.hide()
	_stop_walk()
	selected_node = ""
	build_recipe = ""
	world_view.ghost.visible = false
	world_view.marker.visible = false
	_render()

func _gather() -> void:
	_stop_walk()
	var request := route_request
	while client.busy:
		await client.changed
	if request != route_request or not client.can_act():
		return
	var tree = _nearest()
	if tree.is_empty():
		return
	await client.send_action({"type":"gather","nodeId":tree.nodeId})

func _transfer(recipient: String, amount: int) -> void:
	_stop_walk()
	input_suspended = true
	await client.send_action({"type": "transfer", "recipientActorId": recipient, "resource": "wood", "quantity": amount})

func _unhandled_key_input(event: InputEvent) -> void:
	if not event is InputEventKey or not event.pressed or event.echo or get_viewport().gui_get_focus_owner() is LineEdit:
		return
	if transfer_panel.visible:
		if event.physical_keycode == KEY_ESCAPE:
			transfer_panel.hide()
		return
	match event.physical_keycode:
		KEY_W, KEY_A, KEY_S, KEY_D, KEY_UP, KEY_LEFT, KEY_DOWN, KEY_RIGHT: _stop_walk()
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
	if not get_viewport().gui_get_focus_owner() is LineEdit and build_recipe.is_empty() and not transfer_panel.visible:
		direction = Vector2(int(Input.is_physical_key_pressed(KEY_D) or Input.is_physical_key_pressed(KEY_RIGHT))-int(Input.is_physical_key_pressed(KEY_A) or Input.is_physical_key_pressed(KEY_LEFT)),int(Input.is_physical_key_pressed(KEY_S) or Input.is_physical_key_pressed(KEY_DOWN))-int(Input.is_physical_key_pressed(KEY_W) or Input.is_physical_key_pressed(KEY_UP))).normalized()
	if direction == Vector2.ZERO:
		input_suspended = false
	elif input_suspended:
		direction = Vector2.ZERO
	if direction != Vector2.ZERO:
		if walking or planning:
			_stop_walk()
	elif walking:
		while route_index < route.size() and position_2d().distance_to(route[route_index]) <= 0.025:
			route_index += 1
		if route_index >= route.size():
			_stop_walk()
		else:
			direction = position_2d().direction_to(route[route_index])
			world_view.trim_route(position_2d(), route.slice(route_index))
	if direction != Vector2.ZERO and cooldown <= 0:
		cooldown = 0.08
		poll_time = 0
		var step_distance = clampf(motion_elapsed*3,0.01,0.6)
		motion_elapsed = 0
		var distance = minf(step_distance,position_2d().distance_to(route[route_index])) if walking else step_distance
		var to = position_2d()+direction*distance
		await client.send_action({"type":"walk","to":[to.x,to.y]})
	elif poll_time >= 0.6 and not client.busy:
		poll_time = 0
		await client.refresh()

func _notification(what: int) -> void:
	if what == NOTIFICATION_APPLICATION_FOCUS_OUT:
		_stop_walk()
		input_suspended = true
