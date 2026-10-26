extends Node3D

const Client = preload("res://world_client.gd")
const View = preload("res://world_view.gd")
var client: Node
var world_view: SubViewportContainer
var url_input: LineEdit
var token_input: LineEdit
var connect_button: Button
var status_label: Label
var inventory_label: Label
var target_label: Label
var move_button: Button
var gather_button: Button
var platform_button: Button
var bridge_button: Button
var query_button: Button
var retry_button: Button
var stop_button: Button
var directions: Array[Button] = []
var selection = Vector2i(-1, -1)
var walking = false
var walk_epoch = 0
var rendered_version = -1
var rendered_actor = ""

func _ready() -> void:
	client = Client.new()
	add_child(client)
	_build_ui()
	client.changed.connect(_render)
	var poll = Timer.new()
	poll.wait_time = 2.0
	poll.timeout.connect(func():
		if not walking:
			client.refresh())
	add_child(poll)
	poll.start()
	_render()
	var access_path = OS.get_environment("WORLD_ACCESS_FILE")
	if not access_path.is_empty() and FileAccess.file_exists(access_path):
		var access = JSON.parse_string(FileAccess.get_file_as_string(access_path))
		var actor = OS.get_environment("WORLD_ACTOR")
		if actor.is_empty():
			actor = "a1"
		if access is Dictionary and access.get("sessions", {}).get(actor, {}).get("token") is String:
			await client.connect_world(url_input.text, access.sessions[actor].token)

func _style(color: Color) -> StyleBoxFlat:
	var style = StyleBoxFlat.new()
	style.bg_color = color
	style.corner_radius_top_left = 8
	style.corner_radius_top_right = 8
	style.corner_radius_bottom_left = 8
	style.corner_radius_bottom_right = 8
	style.content_margin_left = 14
	style.content_margin_right = 14
	style.content_margin_top = 9
	style.content_margin_bottom = 9
	return style

func _text(parent: Node, text: String, size: int = 16, color: Color = Color("e4ede6")) -> Label:
	var label = Label.new()
	label.text = text
	label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	label.add_theme_font_size_override("font_size", size)
	label.add_theme_color_override("font_color", color)
	parent.add_child(label)
	return label

func _button(parent: Node, text: String, callback: Callable) -> Button:
	var button = Button.new()
	button.text = text
	button.custom_minimum_size.y = 38
	button.pressed.connect(callback)
	parent.add_child(button)
	return button

func _build_ui() -> void:
	var layer = CanvasLayer.new()
	add_child(layer)
	var root = HBoxContainer.new()
	root.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	root.add_theme_constant_override("separation", 0)
	layer.add_child(root)
	var theme = Theme.new()
	var font = SystemFont.new()
	font.font_names = PackedStringArray(["Noto Sans CJK SC", "WenQuanYi Micro Hei", "sans-serif"])
	theme.default_font = font
	theme.default_font_size = 15
	theme.set_stylebox("normal", "Button", _style(Color("304940")))
	theme.set_stylebox("hover", "Button", _style(Color("496756")))
	theme.set_stylebox("pressed", "Button", _style(Color("6c794a")))
	theme.set_stylebox("disabled", "Button", _style(Color("223330")))
	theme.set_color("font_disabled_color", "Button", Color("73827a"))
	root.theme = theme
	var panel = PanelContainer.new()
	panel.custom_minimum_size.x = 324
	panel.add_theme_stylebox_override("panel", _style(Color("162923")))
	root.add_child(panel)
	var scroll = ScrollContainer.new()
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	panel.add_child(scroll)
	var side = VBoxContainer.new()
	side.custom_minimum_size.x = 284
	side.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	side.add_theme_constant_override("separation", 8)
	scroll.add_child(side)
	_text(side, "M E T A V E R S E", 12, Color("b9c39f"))
	_text(side, "荒野 · 最初的居民", 25)
	_text(side, "从一棵树，到一处栖身之地。", 14, Color("afc0ad"))
	inventory_label = _text(side, "木材 —  ·  位置 —", 19, Color("edcf88"))
	status_label = _text(side, "", 14)
	status_label.custom_minimum_size.y = 58
	target_label = _text(side, "点击地块或树木", 17)
	move_button = _button(side, "走到这里", _walk_to_selection)
	gather_button = _button(side, "砍取木材  +1", _gather)
	platform_button = _button(side, "搭建平台  ·  3 木材", func(): _build("platform.v1"))
	bridge_button = _button(side, "铺设桥段  ·  3 木材", func(): _build("bridge.v1"))
	var row = HBoxContainer.new()
	side.add_child(row)
	for item in [["←", Vector2i(-1, 0)], ["↑", Vector2i(0, -1)], ["↓", Vector2i(0, 1)], ["→", Vector2i(1, 0)]]:
		var direction: Vector2i = item[1]
		var button = _button(row, item[0], func(): _move(direction))
		button.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		directions.append(button)
	stop_button = _button(side, "停止行走", _stop_walk)
	query_button = _button(side, "查询原动作结果", func(): client.recover())
	retry_button = _button(side, "原样重试", func(): client.recover(true))
	_text(side, "WASD / 方向键移动 · E 砍树\n鼠标选地块 · 滚轮缩放", 13, Color("a0b6a4"))
	var divider = HSeparator.new()
	side.add_child(divider)
	_text(side, "连接世界", 14, Color("b9c39f"))
	url_input = LineEdit.new()
	url_input.text = OS.get_environment("WORLD_URL") if OS.has_environment("WORLD_URL") else "http://127.0.0.1:5088"
	url_input.placeholder_text = "服务地址"
	side.add_child(url_input)
	token_input = LineEdit.new()
	token_input.secret = true
	token_input.placeholder_text = "居民令牌（仅在内存中使用）"
	side.add_child(token_input)
	connect_button = _button(side, "连接 / 切换居民", func():
		_stop_walk()
		var secret = token_input.text
		token_input.clear()
		client.connect_world(url_input.text, secret))
	world_view = View.new()
	root.add_child(world_view)
	world_view.cell_selected.connect(_select)

func _select(cell: Vector2i) -> void:
	_stop_walk()
	selection = cell
	world_view.set_selection(cell)
	_render()

func _tree() -> Dictionary:
	for tree in client.observation.get("resourceNodes", []):
		if Vector2i(tree.position[0], tree.position[1]) == selection:
			return tree
	return {}

func _own_cell() -> Vector2i:
	var p = client.observation.get("self", {}).get("position", [-20, -20])
	return Vector2i(p[0], p[1])

func _distance(a: Vector2i, b: Vector2i) -> int:
	return absi(a.x - b.x) + absi(a.y - b.y)

func _render() -> void:
	var data: Dictionary = client.observation
	if not data.is_empty():
		if rendered_version != int(data.stateVersion) or rendered_actor != data.self.actorId:
			world_view.show_world(data)
			rendered_version = int(data.stateVersion)
			rendered_actor = data.self.actorId
		inventory_label.text = "木材 %d  ·  居民 %s\n位置 (%d, %d)" % [data.self.inventory.wood, data.self.actorId, _own_cell().x, _own_cell().y]
	status_label.text = client.message if client.storage_ok else "本地恢复记录不可用，操作暂停。"
	var tree = _tree()
	var selected_valid = selection.x >= 0
	var distance = _distance(_own_cell(), selection)
	target_label.text = "选择 (%d, %d)" % [selection.x, selection.y] if selected_valid else "点击地块或树木"
	if not tree.is_empty():
		target_label.text += "  ·  树木 %d 木" % tree.remainingWood if tree.remainingWood > 0 else "  ·  树桩"
	var ready = client.can_act() and not walking
	move_button.text = "走到树旁" if not tree.is_empty() and tree.remainingWood > 0 else "走到这里"
	move_button.disabled = not ready or not selected_valid
	gather_button.disabled = not ready or tree.is_empty() or tree.get("remainingWood", 0) <= 0 or distance != 1
	var cell = [selection.x, selection.y]
	var water = cell in data.get("world", {}).get("water", [])
	var blocked = cell in data.get("world", {}).get("blocked", [])
	var occupied = data.get("entities", []).any(func(e): return e.position == cell)
	var wood = data.get("self", {}).get("inventory", {}).get("wood", 0)
	var buildable = ready and selected_valid and distance <= 1 and wood >= 3 and not occupied
	platform_button.disabled = not buildable or blocked or water
	bridge_button.disabled = not buildable or not water
	for button in directions:
		button.disabled = not ready
	stop_button.visible = walking
	query_button.visible = not client.pending.is_empty()
	retry_button.visible = query_button.visible
	query_button.disabled = client.busy
	retry_button.disabled = client.busy or not client.storage_ok
	connect_button.disabled = client.busy
	url_input.editable = not client.busy
	token_input.editable = not client.busy

func _move(direction: Vector2i) -> void:
	_stop_walk()
	await client.send_action({"type": "move", "dx": direction.x, "dy": direction.y})

func _gather() -> void:
	if not gather_button.disabled:
		await client.send_action({"type": "gather", "nodeId": _tree().nodeId})

func _build(recipe: String) -> void:
	if (recipe == "platform.v1" and platform_button.disabled) or (recipe == "bridge.v1" and bridge_button.disabled):
		return
	await client.send_action({"type": "build", "recipeId": recipe, "at": [selection.x, selection.y]})

func _stop_walk() -> void:
	walk_epoch += 1
	walking = false

func _route(target: Vector2i, adjacent: bool) -> Array:
	var start = _own_cell()
	var queue: Array[Vector2i] = [start]
	var previous = {start: start}
	var blocked: Array = client.observation.world.blocked
	while not queue.is_empty():
		var cell = queue.pop_front()
		if (adjacent and _distance(cell, target) == 1) or (not adjacent and cell == target):
			var path: Array = []
			while cell != start:
				path.push_front(cell)
				cell = previous[cell]
			return path
		for delta in [Vector2i.LEFT, Vector2i.RIGHT, Vector2i.UP, Vector2i.DOWN]:
			var next: Vector2i = cell + delta
			if next.x >= 0 and next.x < 8 and next.y >= 0 and next.y < 8 and not previous.has(next) and [next.x, next.y] not in blocked:
				previous[next] = cell
				queue.append(next)
	return []

func _walk_to_selection() -> void:
	if not client.can_act() or walking:
		return
	walking = true
	walk_epoch += 1
	var epoch = walk_epoch
	var tree = _tree()
	var path = _route(selection, tree.get("remainingWood", 0) > 0)
	if path.is_empty():
		client.message = "已到达，或当前没有可通行的路线。"
	for cell in path:
		if epoch != walk_epoch or not client.can_act():
			break
		var delta: Vector2i = cell - _own_cell()
		await client.send_action({"type": "move", "dx": delta.x, "dy": delta.y})
		if client.last_receipt.get("status") != "committed":
			break
		await get_tree().create_timer(0.12).timeout
	if epoch == walk_epoch:
		walking = false
	_render()

func _unhandled_key_input(event: InputEvent) -> void:
	if not event is InputEventKey or not event.pressed or event.echo:
		return
	if get_viewport().gui_get_focus_owner() is LineEdit:
		return
	match event.physical_keycode:
		KEY_W, KEY_UP: _move(Vector2i.UP)
		KEY_S, KEY_DOWN: _move(Vector2i.DOWN)
		KEY_A, KEY_LEFT: _move(Vector2i.LEFT)
		KEY_D, KEY_RIGHT: _move(Vector2i.RIGHT)
		KEY_E: _gather()
		KEY_ESCAPE: _stop_walk()
