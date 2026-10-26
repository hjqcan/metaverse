extends PanelContainer

signal requested(action: Dictionary)
signal build_requested(recipe: String, tool_id: String)
signal approach_requested(entity: Dictionary)
const Workshop = preload("res://workshop_evidence.gd")
const Geometry = preload("res://workshop_geometry.gd")
var observed: Dictionary = {}
var can_submit := false
var binding := ""
var selected_bench := ""
var selected_chest := ""
var selected_tool := ""
var summary: Label
var notice: Label
var bench_status: Label
var chest_status: Label
var bench_picker: OptionButton
var chest_picker: OptionButton
var tool_picker: OptionButton
var amount: SpinBox
var bench_build: Button
var chest_build: Button
var craft: Button
var deposit: Button
var withdraw: Button
var bench_go: Button
var chest_go: Button
var tabs: TabContainer

func _label(parent: Node, text: String) -> Label:
	var label := Label.new()
	label.text = text
	label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	label.custom_minimum_size.x = 340
	parent.add_child(label)
	return label

func _button(parent: Node, text: String, callback: Callable) -> Button:
	var button := Button.new()
	button.text = text
	button.custom_minimum_size.y = 36
	button.focus_mode = Control.FOCUS_NONE
	button.pressed.connect(callback)
	parent.add_child(button)
	return button

func _picker(parent: Node, callback: Callable) -> OptionButton:
	var picker := OptionButton.new()
	picker.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	picker.custom_minimum_size.y = 34
	picker.item_selected.connect(callback)
	parent.add_child(picker)
	return picker

func _ready() -> void:
	custom_minimum_size.x = 396
	var box := VBoxContainer.new()
	box.add_theme_constant_override("separation", 7)
	add_child(box)
	var title := HBoxContainer.new()
	box.add_child(title)
	var heading := Label.new()
	heading.text = "工作台与储物"
	heading.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	heading.add_theme_font_size_override("font_size", 20)
	title.add_child(heading)
	_button(title, "关闭", close_panel)
	summary = _label(box, "")
	var builds := HBoxContainer.new()
	box.add_child(builds)
	bench_build = _button(builds, "搭工作台 · 3木", func(): build_requested.emit("workbench.v1", ""))
	chest_build = _button(builds, "搭储物箱 · 3木", func(): build_requested.emit("wooden_chest.v1", selected_tool))
	_label(box, "建箱使用的本人木工锤")
	tool_picker = _picker(box, func(index: int): selected_tool = str(tool_picker.get_item_metadata(index)); _update_controls())
	tabs = TabContainer.new()
	box.add_child(tabs)
	var bench_tab := VBoxContainer.new()
	bench_tab.name = "制作工具"
	tabs.add_child(bench_tab)
	_label(bench_tab, "公共工作台 · 用本人材料制作")
	bench_picker = _picker(bench_tab, func(index: int): selected_bench = str(bench_picker.get_item_metadata(index)); _update_controls())
	bench_status = _label(bench_tab, "")
	var bench_actions := HBoxContainer.new()
	bench_tab.add_child(bench_actions)
	bench_go = _button(bench_actions, "走到台旁", func(): approach_requested.emit(_entity(selected_bench)))
	craft = _button(bench_actions, "制作木工锤 · 1木", func(): requested.emit({"type": "craft_tool", "capabilityVersion": 1, "entityId": selected_bench, "recipeId": "wooden_mallet.v1"}))
	var chest_tab := VBoxContainer.new()
	chest_tab.name = "存取木材"
	tabs.add_child(chest_tab)
	_label(chest_tab, "本人储物箱 · 每箱容量12木")
	chest_picker = _picker(chest_tab, func(index: int): selected_chest = str(chest_picker.get_item_metadata(index)); _update_controls())
	chest_status = _label(chest_tab, "")
	var chest_actions := HBoxContainer.new()
	chest_tab.add_child(chest_actions)
	chest_go = _button(chest_actions, "走到箱旁", func(): approach_requested.emit(_entity(selected_chest)))
	amount = SpinBox.new()
	amount.min_value = 1
	amount.max_value = 12
	amount.step = 1
	amount.value = 1
	amount.custom_minimum_size.x = 70
	amount.value_changed.connect(func(_value): _update_controls())
	chest_actions.add_child(amount)
	deposit = _button(chest_actions, "存入", func(): _store("deposit_wood"))
	withdraw = _button(chest_actions, "取出", func(): _store("withdraw_wood"))
	notice = _label(box, "")
	notice.add_theme_font_size_override("font_size", 13)
	hide()

func close_panel() -> void:
	hide()

func _store(type: String) -> void:
	requested.emit({"type": type, "capabilityVersion": 1, "entityId": selected_chest, "quantity": int(amount.value)})

func _entity(id: String) -> Dictionary:
	for entity in observed.get("entities", []):
		if entity.entityId == id:
			return entity
	return {}

func _fill(picker: OptionButton, entries: Array, selected: String, empty: String) -> String:
	picker.clear()
	if entries.is_empty():
		picker.add_item(empty)
		picker.set_item_metadata(0, "")
		picker.disabled = true
		return ""
	picker.disabled = false
	var index := 0
	for i in entries.size():
		picker.add_item(entries[i].label)
		picker.set_item_metadata(i, entries[i].id)
		if entries[i].id == selected:
			index = i
	picker.select(index)
	return entries[index].id

func update_world(value: Dictionary, can_act: bool, pending: Dictionary, receipt: Dictionary, generation: int) -> void:
	if not is_node_ready():
		return
	var next := str(generation) + "/" + str(value.get("world", {}).get("instanceId", "")) + "/" + str(value.get("identity", {}).get("actorId", ""))
	if next != binding:
		binding = next
		selected_bench = ""
		selected_chest = ""
		selected_tool = ""
		amount.value = 1
		hide()
	observed = value
	can_submit = can_act and Workshop.supported(value)
	if not Workshop.supported(value):
		hide()
		return
	var benches: Array = []
	for e in value.workshop.workbenches:
		benches.append({"id": e.entityId, "label": "%s的台 · %.1f, %.1f · %s" % [e.ownerActorId, e.position[0], e.position[1], e.entityId.left(7)]})
	var chests: Array = []
	for c in value.workshop.chests:
		chests.append({"id": c.entity.entityId, "label": "箱 %s · %d/12木 · %.1f, %.1f" % [c.entity.entityId.left(7), c.storedWood, c.entity.position[0], c.entity.position[1]]})
	var tools: Array = []
	for tool in value.workshop.tools:
		tools.append({"id": tool.toolId, "label": "木工锤 %s · 本人持有" % tool.toolId.left(9)})
	# Avoid replacing an open popup during the ordinary observation poll.
	if not bench_picker.get_popup().visible:
		selected_bench = _fill(bench_picker, benches, selected_bench, "尚无工作台，先用3木搭建")
	if not chest_picker.get_popup().visible:
		selected_chest = _fill(chest_picker, chests, selected_chest, "尚无本人储物箱")
	if not tool_picker.get_popup().visible:
		selected_tool = _fill(tool_picker, tools, selected_tool, "尚无木工锤，先到公共台制作")
	summary.text = "携带 %d/12木 · 本人木工锤 %d把" % [value.self.inventory.wood, tools.size()]
	notice.text = "台可供后来者使用；锤持续保留，箱内木材只有你能存取。"
	if not pending.is_empty():
		notice.text = "原动作待确认，制作和存取暂停。"
	elif receipt.get("status") == "committed" and Workshop.is_action(receipt.get("result", {}).get("action")):
		var d: Dictionary = receipt.result.workshopAction
		notice.text = "已确认：%s · 原命令 %s" % [{"build_workshop": "建造完成", "craft_tool": "木工锤已制成", "deposit_wood": "存入%d木" % d.quantity, "withdraw_wood": "取出%d木" % d.quantity}[d.action.type], d.commandId.right(8)]
	_update_controls()

func select_entity(id: String) -> void:
	var entity := _entity(id)
	if entity.is_empty():
		return
	if entity.definitionId == "workbench":
		selected_bench = id
		tabs.current_tab = 0
		for i in bench_picker.item_count:
			if bench_picker.get_item_metadata(i) == id:
				bench_picker.select(i)
	elif entity.definitionId == "wooden_chest":
		tabs.current_tab = 1
		if entity.ownerActorId == observed.self.actorId:
			selected_chest = id
			for i in chest_picker.item_count:
				if chest_picker.get_item_metadata(i) == id:
					chest_picker.select(i)
		else:
			notice.text = "这是%s的私人箱，只有箱主能存取。" % entity.ownerActorId
	_update_controls()

func _update_controls() -> void:
	if not is_node_ready() or observed.is_empty() or not Workshop.supported(observed):
		return
	var wood: int = int(observed.self.inventory.wood)
	bench_build.disabled = not can_submit or wood < 3
	chest_build.disabled = not can_submit or wood < 3 or selected_tool.is_empty()
	var bench := _entity(selected_bench)
	var chest := _entity(selected_chest)
	var bench_distance: float = INF if bench.is_empty() else Workshop.Notes.distance(observed.self.position, bench.position)
	var chest_distance: float = INF if chest.is_empty() else Workshop.Notes.distance(observed.self.position, chest.position)
	bench_go.disabled = not can_submit or bench.is_empty()
	var point := Vector2(observed.self.position[0], observed.self.position[1])
	var bench_reachable: bool = not bench.is_empty() and Geometry.can_interact(observed, point, bench)
	var chest_reachable: bool = not chest.is_empty() and Geometry.can_interact(observed, point, chest)
	craft.disabled = not can_submit or not bench_reachable or wood < 1
	bench_status.text = "先搭一张工作台。" if bench.is_empty() else "距台 %.2f米 · 制作须在1.6米内，用1木" % bench_distance
	if not bench.is_empty() and bench_distance <= 1.6 and not bench_reachable:
		bench_status.text += "\n前方受阻，请点走到台旁换操作侧。"
	chest_go.disabled = not can_submit or chest.is_empty()
	var stock := 0
	for item in observed.workshop.chests:
		if item.entity.entityId == selected_chest:
			stock = int(item.storedWood)
	chest_status.text = "先制锤，再搭储物箱。" if chest.is_empty() else "距箱 %.2f米 · 箱内%d/12木 · 携带%d/12木" % [chest_distance, stock, wood]
	if not chest.is_empty() and chest_distance <= 1.6 and not chest_reachable:
		chest_status.text += "\n前方受阻，请点走到箱旁换操作侧。"
	deposit.disabled = not can_submit or not chest_reachable or wood < amount.value or stock + amount.value > 12
	withdraw.disabled = not can_submit or not chest_reachable or stock < amount.value or wood + amount.value > 12
