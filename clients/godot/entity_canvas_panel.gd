extends PanelContainer
## The confirmed picture, local draft, and pending command are separate states.
signal requested(action: Dictionary)
signal destination_requested(point: Vector2)
const Canvas = preload("res://entity_canvas_evidence.gd")
var observed: Dictionary = {}
var title: Label
var hint: Label
var status: Label
var legend: Label
var send_button: Button
var reset_button: Button
var travel_button: Button
var cells: Array[Button] = []
var palette_buttons: Array[Button] = []
var described = -1
var selected = "river"
var draft: Dictionary = {}
var base_cells: Array = []
var base_revision = -1
var identity_key = ""
var pending_id = ""
var available = false
var editable = false
var content_scroll: ScrollContainer
var editor_widgets: Array[Control] = []
var history_button: Button
var history_box: VBoxContainer
var history_summary: Label
var history_selector: OptionButton
var history_detail: Label
var history_cells: Array[Button] = []
var history_mode := false
var selected_history_key := ""
var history_binding := ""
var history_revision := -1
var history_edits: Array = []
var history_window_notice := ""

func label(parent: Node, text: String) -> Label:
	var node := Label.new()
	node.text = text
	node.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	node.custom_minimum_size.x = 360
	parent.add_child(node)
	return node

func button(parent: Node, text: String, callback: Callable) -> Button:
	var node := Button.new()
	node.text = text
	node.custom_minimum_size.y = 36
	node.pressed.connect(callback)
	parent.add_child(node)
	return node

func _ready() -> void:
	var layout := VBoxContainer.new()
	add_child(layout)
	var scroll := ScrollContainer.new()
	content_scroll = scroll
	scroll.custom_minimum_size = Vector2(382, 420)
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	layout.add_child(scroll)
	var box := VBoxContainer.new()
	box.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	box.add_theme_constant_override("separation", 7)
	scroll.add_child(box)
	title = label(box, "平台地画")
	title.add_theme_font_size_override("font_size", 20)
	editor_widgets.append(label(box, "已确认图 · 标有 ● 的格子仅是你的草图"))
	var grid := GridContainer.new()
	grid.columns = 5
	grid.add_theme_constant_override("h_separation", 4)
	grid.add_theme_constant_override("v_separation", 4)
	box.add_child(grid)
	editor_widgets.append(grid)
	for i in 25:
		var cell := button(grid, "", func(): _paint(i))
		cell.custom_minimum_size = Vector2(68, 34)
		cell.mouse_entered.connect(func(): _describe(i))
		cells.append(cell)
	legend = label(box, "格子未署名时可画；本人格可改，他人格须保留。")
	editor_widgets.append(legend)
	var palette := GridContainer.new()
	palette.columns = 3
	box.add_child(palette)
	editor_widgets.append(palette)
	var labels := ["空白", "叶绿", "河蓝", "日黄", "花红", "墨色"]
	for i in 6:
		var color_button := button(palette, labels[i], func():
			selected = Canvas.COLORS[i]
			_update())
		color_button.custom_minimum_size.x = 116
		color_button.tooltip_text = labels[i] + " · 空白颜色也保留作者"
		palette_buttons.append(color_button)
	hint = label(box, "")
	status = label(box, "")
	editor_widgets.append_array([hint, status])
	history_box = VBoxContainer.new()
	history_box.add_theme_constant_override("separation", 7)
	box.add_child(history_box)
	history_summary = label(history_box, "还没有创作。")
	history_selector = OptionButton.new()
	history_selector.custom_minimum_size.y = 34
	history_selector.item_selected.connect(_select_history)
	history_box.add_child(history_selector)
	history_detail = label(history_box, "选择一条创作查看。")
	label(history_box, "本次修改，非当时完整图面\n· 表示本次未改；空白色仍是一次绘制。")
	var history_grid := GridContainer.new()
	history_grid.columns = 5
	history_grid.add_theme_constant_override("h_separation", 4)
	history_grid.add_theme_constant_override("v_separation", 4)
	history_box.add_child(history_grid)
	for i in 25:
		var cell := Button.new()
		cell.custom_minimum_size = Vector2(68, 28)
		cell.focus_mode = Control.FOCUS_NONE
		history_grid.add_child(cell)
		history_cells.append(cell)
	var actions := HBoxContainer.new()
	layout.add_child(actions)
	send_button = button(actions, "提交草图", _submit)
	travel_button = button(actions, "走到平台", func():
		if Canvas.supported(observed):
			var p: Array = observed.entityCanvas.target.position
			hide()
			destination_requested.emit(Vector2(p[0], p[1])))
	history_button = button(actions, "近期创作", func(): _show_history(not history_mode))
	button(actions, "关闭", close_panel)
	reset_button = button(layout, "从当前图新建草图", _new_draft)
	_set_history_visibility()
	hide()

func _new_draft() -> void:
	if history_mode or not Canvas.supported(observed) or not editable:
		return
	draft.clear()
	base_revision = int(observed.entityCanvas.revision)
	base_cells = observed.entityCanvas.cells.duplicate(true)
	status.text = "新草图使用当前已确认图；尚未提交。"
	_update()

func close_panel() -> void:
	_show_history(false)
	hide()

func _paint(index: int) -> void:
	if history_mode or not editable or base_cells.size() != 25 or base_revision != observed.get("entityCanvas", {}).get("revision"):
		return
	var cell: Dictionary = base_cells[index]
	if cell.authorActorId != null and cell.authorActorId != observed.self.actorId:
		return
	if selected == cell.color:
		draft.erase(index)
	elif draft.has(index) or draft.size() < 8:
		draft[index] = selected
	else:
		status.text = "每次最多提交8格。其余草图保留。"
	_update()
	_describe(index)

func _describe(index: int) -> void:
	if not Canvas.supported(observed):
		return
	described = index
	var cell: Dictionary = observed.entityCanvas.cells[index]
	legend.text = "(%d,%d) · 已确认 %s · 作者 %s" % [cell.x, cell.y, cell.color, "无人" if cell.authorActorId == null else cell.authorActorId]
	if draft.has(index):
		legend.text += "\n草图：" + draft[index] + "（未提交）"

func patch() -> Array:
	var result: Array = []
	for index in 25:
		if draft.has(index):
			result.append({"x": index % 5, "y": index / 5, "color": draft[index]})
	return result

func _submit() -> void:
	if history_mode or send_button.disabled:
		return
	requested.emit({"type": "paint_entity_canvas", "entityId": observed.entityCanvas.target.entityId,
		"capabilityVersion": 1, "expectedCanvasRevision": base_revision, "patch": patch()})

func update_world(value: Dictionary, can_act: bool, pending: Dictionary, receipt: Dictionary, generation: int) -> void:
	observed = value
	var key := str(generation) + ":" + str(value.get("world", {}).get("instanceId")) + ":" + str(value.get("self", {}).get("actorId"))
	if key != identity_key:
		identity_key = key
		draft.clear()
		base_cells.clear()
		base_revision = -1
		pending_id = ""
		described = -1
		status.text = ""
		_clear_history()
		hide()
	available = can_act and Canvas.supported(value)
	editable = available and pending.is_empty()
	if not Canvas.supported(value):
		_clear_history()
		hide()
		return
	var cap: Dictionary = value.entityCanvas
	title.text = "平台地画 · 确认图 #%d\n平台建造者：%s" % [cap.revision, cap.target.ownerActorId]
	var original = JSON.parse_string(pending.get("body", "{}"))
	if original is Dictionary and original.get("action", {}).get("type") == "paint_entity_canvas":
		pending_id = str(original.commandId)
		status.text = "未确认 · 原草图请求已保存。请查询原动作，关闭面板不会重画。"
	elif not pending_id.is_empty() and receipt.get("commandId") == pending_id:
		if receipt.get("status") == "committed":
			status.text = "已确认本次绘制 · #%d · 居民 %s\n当前图可能已由后续绘制更新，原修改仍保留。" % [receipt.result.revision, receipt.result.authorActorId]
			draft.clear()
		else:
			status.text = "未绘制 · " + str(receipt.get("error", {}).get("message", "请求被拒绝")) + "\n草图保留，不会自动重发。"
		pending_id = ""
	if base_revision < 0 or draft.is_empty():
		base_revision = int(cap.revision)
		base_cells = cap.cells.duplicate(true)
	_update()
	_update_history()

func _history_key(edit: Dictionary) -> String:
	return JSON.stringify([observed.world.instanceId, observed.entityCanvas.target.entityId, edit.authorActorId, edit.commandId])

func _clear_history() -> void:
	history_mode = false
	selected_history_key = ""
	history_binding = ""
	history_revision = -1
	history_edits.clear()
	history_window_notice = ""
	history_selector.clear()
	history_summary.text = "还没有创作。"
	_render_history()
	_set_history_visibility()

func _show_history(show_history: bool) -> void:
	if show_history and not Canvas.supported(observed):
		return
	history_mode = show_history
	_set_history_visibility()
	content_scroll.scroll_vertical = 0

func _set_history_visibility() -> void:
	for widget in editor_widgets:
		widget.visible = not history_mode
	history_box.visible = history_mode
	send_button.visible = not history_mode
	travel_button.visible = not history_mode
	reset_button.visible = not history_mode
	history_button.text = "当前作品" if history_mode else "近期创作"

func _update_history() -> void:
	var cap: Dictionary = observed.entityCanvas
	var binding: String = identity_key + ":" + str(cap.target.entityId)
	if binding != history_binding:
		_clear_history()
		history_binding = binding
	if history_revision == int(cap.revision):
		return
	history_revision = int(cap.revision)
	history_edits = cap.recentEdits.duplicate(true)
	history_selector.clear()
	var selected_index := -1
	for i in history_edits.size():
		var edit: Dictionary = history_edits[i]
		var key := _history_key(edit)
		history_selector.add_item("%s · 第%d次 · %d格" % [edit.authorActorId, edit.revision, edit.patch.size()])
		history_selector.set_item_metadata(i, key)
		if key == selected_history_key:
			selected_index = i
	if not selected_history_key.is_empty() and selected_index < 0:
		selected_history_key = ""
		history_window_notice = "所选创作已超出最近50次，可重新选择。"
	history_selector.select(selected_index)
	history_selector.disabled = history_edits.is_empty()
	if selected_index < 0:
		history_selector.text = "还没有创作" if history_edits.is_empty() else "选择一次创作"
	_history_summary()
	_render_history()

func _history_summary() -> void:
	history_summary.text = "还没有创作。" if history_edits.is_empty() else "共%d次，显示最近%d次" % [history_revision, history_edits.size()]
	if history_revision > 50:
		history_summary.text += "\n这里仅显示最近50次，更早记录仍保留。"
	if not history_window_notice.is_empty():
		history_summary.text += "\n" + history_window_notice

func _select_history(index: int) -> void:
	if index < 0 or index >= history_edits.size() or not Canvas.supported(observed):
		return
	selected_history_key = _history_key(history_edits[index])
	history_selector.select(index)
	history_window_notice = ""
	_history_summary()
	_render_history()

func _render_history() -> void:
	var chosen: Dictionary = {}
	for edit in history_edits:
		if _history_key(edit) == selected_history_key:
			chosen = edit
			break
	var colors: Dictionary = {}
	history_detail.text = "选择一条创作查看。"
	if not chosen.is_empty():
		history_detail.text = "%s · 第%d次创作 · %d格\n%s" % [chosen.authorActorId, chosen.revision, chosen.patch.size(), chosen.paintedAtUtc]
		for cell in chosen.patch:
			colors[int(cell.y) * 5 + int(cell.x)] = cell.color
	for i in 25:
		var changed: bool = colors.has(i)
		var style := StyleBoxFlat.new()
		style.bg_color = Color(Canvas.HEX[Canvas.COLORS.find(colors[i])]) if changed else Color("747d82")
		style.set_border_width_all(2 if changed else 1)
		style.border_color = Color("e4b858") if changed else Color("a2acaf")
		for state in ["normal", "hover", "pressed", "disabled", "focus"]:
			history_cells[i].add_theme_stylebox_override(state, style)
		history_cells[i].text = "" if changed else "·"
		history_cells[i].set_meta("history_changed", changed)
		history_cells[i].set_meta("history_color", colors.get(i, ""))
		history_cells[i].tooltip_text = "(%d,%d) · " % [i % 5, i / 5] + ("本次绘制 %s · 作者 %s" % [colors[i], chosen.authorActorId] if changed else "本次未修改")

func _update() -> void:
	if send_button == null or not Canvas.supported(observed):
		return
	var cap: Dictionary = observed.entityCanvas
	var stale: bool = base_revision != int(cap.revision)
	var distance: float = Canvas.Notes.distance(observed.self.position, cap.target.position)
	for i in 25:
		var cell: Dictionary = cap.cells[i]
		var color: String = draft.get(i, cell.color)
		var style := StyleBoxFlat.new()
		style.bg_color = Color(Canvas.HEX[Canvas.COLORS.find(color)])
		style.set_border_width_all(3 if draft.has(i) else 1)
		style.border_color = Color("e4b858") if draft.has(i) else Color("637569")
		for state in ["normal", "hover", "pressed", "disabled", "focus"]:
			cells[i].add_theme_stylebox_override(state, style)
		cells[i].text = "●" if draft.has(i) else ""
		cells[i].add_theme_color_override("font_color", Color("18271f"))
		cells[i].disabled = not editable or stale or (cell.authorActorId != null and cell.authorActorId != observed.self.actorId)
		cells[i].tooltip_text = "(%d,%d) · 作者 %s · 已确认 %s" % [cell.x, cell.y, "无人" if cell.authorActorId == null else cell.authorActorId, cell.color]
	hint.text = "选择 %s · 草图 %d / 8 格 · 基准 #%d\n距离平台 %.1f 米；1.6米内可提交，无木材支出。" % [selected, draft.size(), base_revision, distance]
	if stale:
		hint.text += "\n确认图已更新，旧草图保留。需要明确新建草图。"
	send_button.disabled = not available or stale or draft.is_empty() or distance > 1.6
	travel_button.disabled = not available
	reset_button.disabled = not editable
	if described >= 0:
		_describe(described)
