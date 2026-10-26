extends PanelContainer

signal requested(action: Dictionary)
signal approach_requested(target: Dictionary)
const Forestry = preload("res://forestry_evidence.gd")
const Geometry = preload("res://workshop_geometry.gd")
const NAMES = {"forest-west-north": "西岸北林位", "forest-west-south": "西岸南林位", "forest-east-north": "东岸北林位", "forest-east-far": "东岸远林位"}
var observed: Dictionary = {}
var can_submit := false
var binding := ""
var selected_plot := "forest-west-north"
var selected_bench := ""
var selected_tool := ""
var summary: Label
var queue_status: Label
var plot_status: Label
var nursery_status: Label
var notice: Label
var bench_status: Label
var plot_picker: OptionButton
var bench_picker: OptionButton
var tool_picker: OptionButton
var reserve_button: Button
var cancel_button: Button
var collect_button: Button
var plant_button: Button
var harvest_button: Button
var craft_axe_button: Button
var nursery_go: Button
var plot_go: Button
var bench_go: Button
var tabs: TabContainer
var scroll: ScrollContainer

func _label(parent: Node, text: String = "") -> Label:
	var item := Label.new()
	item.text = text
	item.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	item.custom_minimum_size.x = 335
	parent.add_child(item)
	return item

func _button(parent: Node, text: String, callback: Callable) -> Button:
	var item := Button.new()
	item.text = text
	item.custom_minimum_size.y = 34
	item.focus_mode = Control.FOCUS_NONE
	item.pressed.connect(callback)
	parent.add_child(item)
	return item

func _row(parent: Node) -> HBoxContainer:
	var row := HBoxContainer.new()
	parent.add_child(row)
	return row

func _picker(parent: Node, callback: Callable) -> OptionButton:
	var item := OptionButton.new()
	item.custom_minimum_size.y = 32
	item.item_selected.connect(callback)
	parent.add_child(item)
	return item

func _ready() -> void:
	custom_minimum_size.x = 400
	var box := VBoxContainer.new()
	box.add_theme_constant_override("separation", 5)
	scroll = ScrollContainer.new()
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	scroll.custom_minimum_size.y = 500
	add_child(scroll)
	box.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	scroll.add_child(box)
	var title := _row(box)
	var label := Label.new()
	label.text = "公共育林"
	label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	label.add_theme_font_size_override("font_size", 20)
	title.add_child(label)
	_button(title, "关闭", close_panel)
	summary = _label(box)
	tabs = TabContainer.new()
	box.add_child(tabs)
	var forest_tab := VBoxContainer.new()
	forest_tab.name = "种植与采收"
	tabs.add_child(forest_tab)
	_label(forest_tab, "种前90服务秒；种下后生长120秒；成熟后60秒优先采收，过期原树交给下一位。")
	queue_status = _label(forest_tab)
	var queue_actions := _row(forest_tab)
	reserve_button = _button(queue_actions, "申请下一轮育林", func(): _send("reserve_forest"))
	cancel_button = _button(queue_actions, "取消种前排队", func(): _send("cancel_forest_reservation"))
	nursery_status = _label(forest_tab)
	var nursery_actions := _row(forest_tab)
	nursery_go = _button(nursery_actions, "走到采种点", func(): approach_requested.emit({"entityId": "nursery-west", "position": [7, 6]}))
	collect_button = _button(nursery_actions, "领取原保留种子", func(): _send("collect_seed"))
	plot_picker = _picker(forest_tab, func(i: int): selected_plot = str(plot_picker.get_item_metadata(i)); _controls())
	plot_status = _label(forest_tab)
	plot_go = _button(forest_tab, "走到林位旁", func(): approach_requested.emit(_plot_target()))
	var plot_actions := _row(forest_tab)
	plant_button = _button(plot_actions, "种下 · 1种", func(): _send("plant_tree"))
	harvest_button = _button(plot_actions, "整株采收 · 3木+1种", func(): _send("harvest_tree"))
	_label(forest_tab, "采收使用的本人木斧")
	tool_picker = _picker(forest_tab, func(i: int): selected_tool = str(tool_picker.get_item_metadata(i)); _controls())
	var craft_tab := VBoxContainer.new()
	craft_tab.name = "制作木斧"
	tabs.add_child(craft_tab)
	_label(craft_tab, "在公共台用本人2木制作，木斧持续保留。")
	bench_picker = _picker(craft_tab, func(i: int): selected_bench = str(bench_picker.get_item_metadata(i)); _controls())
	bench_status = _label(craft_tab)
	var craft_actions := _row(craft_tab)
	bench_go = _button(craft_actions, "走到台旁", func(): approach_requested.emit(_bench()))
	craft_axe_button = _button(craft_actions, "制作木斧 · 2木", func(): _send("craft_forestry_tool"))
	_label(craft_tab, "已有木工锤和储物箱仍在“工作台与储物”中。")
	notice = _label(box, "种前90秒，种下后生长120服务秒；成熟后有60秒优先采收。")
	notice.add_theme_font_size_override("font_size", 13)
	hide()

func close_panel() -> void:
	hide()

func _own() -> Dictionary:
	for r in observed.get("forestry", {}).get("reservations", []):
		if r.actorId == observed.self.actorId:
			return r
	return {}

func _plant() -> Dictionary:
	for p in observed.get("forestry", {}).get("plants", []):
		if p.plotId == selected_plot:
			return p
	return {}

func _plot_target() -> Dictionary:
	var p := _plant()
	return {"entityId": selected_plot if p.is_empty() else p.plantId, "position": Forestry.PLOTS[selected_plot]}

func _bench() -> Dictionary:
	for b in observed.get("workshop", {}).get("workbenches", []):
		if b.entityId == selected_bench:
			return b
	return {}

func _fill(picker: OptionButton, entries: Array, selected: String, empty: String) -> String:
	if picker.get_popup().visible:
		return selected
	picker.clear()
	picker.disabled = entries.is_empty()
	if entries.is_empty():
		picker.add_item(empty)
		picker.set_item_metadata(0, "")
		return ""
	var index := 0
	for i in entries.size():
		picker.add_item(entries[i].label)
		picker.set_item_metadata(i, entries[i].id)
		if entries[i].id == selected:
			index = i
	picker.select(index)
	return entries[index].id

func update_world(value: Dictionary, ready: bool, pending: Dictionary, receipt: Dictionary, generation: int) -> void:
	if not is_node_ready():
		return
	var next := str(generation) + "/" + str(value.get("world", {}).get("instanceId")) + "/" + str(value.get("self", {}).get("actorId"))
	if next != binding:
		binding = next
		selected_plot = "forest-west-north"
		selected_bench = ""
		selected_tool = ""
		hide()
	scroll.custom_minimum_size.y = clampf(get_viewport_rect().size.y - 320, 240, 550)
	observed = value
	can_submit = ready and Forestry.supported(value)
	if not Forestry.supported(value):
		hide()
		return
	var plots: Array = []
	for id in Forestry.PLOTS:
		plots.append({"id": id, "label": NAMES[id] + " · " + str(Forestry.PLOTS[id])})
	selected_plot = _fill(plot_picker, plots, selected_plot, "")
	var benches: Array = []
	for b in value.workshop.workbenches:
		benches.append({"id": b.entityId, "label": "%s的台 · %.1f, %.1f · %s" % [b.ownerActorId, b.position[0], b.position[1], b.entityId.left(7)]})
	selected_bench = _fill(bench_picker, benches, selected_bench, "尚无公共台，请先搭建")
	var tools: Array = []
	for item in value.forestry.tools:
		tools.append({"id": item.toolId, "label": "本人木斧 · " + item.toolId.left(9)})
	selected_tool = _fill(tool_picker, tools, selected_tool, "尚无木斧，请到公共台制作")
	summary.text = "携带 %d/12木 · 种子 %d份 · 本人木斧 %d把" % [value.self.inventory.wood, value.forestry.seeds, tools.size()]
	notice.text = "成熟不占更多路；到期未采的树会交给下一位。采完后须重新申请。"
	if not pending.is_empty():
		notice.text = "原动作待查证，育林操作暂停。"
	elif receipt.get("status") == "committed" and Forestry.is_action(receipt.get("result", {}).get("action")):
		var d: Dictionary = receipt.result.forestryAction
		notice.text = "已确认：%s · %s" % [{"craft_forestry_tool": "木斧制成", "reserve_forest": "原申请已入队", "cancel_forest_reservation": "原授权取消", "collect_seed": "领到1种", "plant_tree": "原株已种下", "harvest_tree": "原株采得3木和1种"}[d.action.type], d.commandId.right(8)]
	_controls()

func _can_reach(target: Dictionary) -> bool:
	return not target.is_empty() and Geometry.can_interact(observed, Vector2(observed.self.position[0], observed.self.position[1]), target)

func _controls() -> void:
	if not is_node_ready() or not Forestry.supported(observed):
		return
	var f: Dictionary = observed.forestry
	var own := _own()
	var p := _plant()
	var now: int = int(f.nursery.serviceMs)
	var grouped: bool = f.reservations.any(func(r): return r.operatorId == observed.identity.operatorId)
	reserve_button.disabled = not can_submit or grouped
	cancel_button.disabled = not can_submit or own.get("status") not in ["queued", "preparing"]
	queue_status.text = "当前没有本人育林申请。"
	if grouped and own.is_empty():
		queue_status.text = "同声明控制组的另一居民已有申请。"
	if not own.is_empty():
		var labels := {"queued": "等候分配", "preparing": "准备种植", "growing": "原株生长中", "harvesting": "原株可采收"}
		queue_status.text = "%s · %s" % [labels[own.status], NAMES.get(own.plotId, "林位待分配")]
		if own.expiresAtMs != null:
			queue_status.text += " · 剩余%d秒" % maxi(0, ceili((own.expiresAtMs - now) / 1000.0))
		if own.plotId != null and own.plotId != selected_plot:
			queue_status.text += "\n请在下方选择原授权林位。"
	nursery_status.text = "采种点 %d/4种 · 已保留%d · 下次周期约%d秒" % [f.nursery.stockSeeds, f.nursery.reservedSeeds, maxi(0, ceili((f.nursery.nextProductionAtMs - now) / 1000.0))]
	nursery_go.disabled = not can_submit
	collect_button.disabled = not can_submit or own.get("status") != "preparing" or own.get("reservedSeed") != 1 or not _can_reach({"entityId": "nursery-west", "position": [7, 6]})
	plot_go.disabled = not can_submit
	var plot_center: Array = Forestry.PLOTS[selected_plot]
	var occupied_by_resident: bool = observed.residents.any(func(resident): return Forestry.Notes.distance(resident.position, plot_center) < 0.73 - 0.000000001)
	plant_button.disabled = occupied_by_resident or not can_submit or own.get("status") != "preparing" or own.get("plotId") != selected_plot or not p.is_empty() or f.seeds < 1 or not _can_reach(_plot_target())
	harvest_button.disabled = not can_submit or own.get("status") != "harvesting" or own.get("plantId") != p.get("plantId", "") or selected_tool.is_empty() \
		or observed.self.inventory.wood > 9 or not _can_reach(_plot_target())
	plot_status.text = NAMES[selected_plot] + " · 空林位"
	if not p.is_empty():
		plot_status.text = "%s种下 · %s\n%s" % [p.planterActorId, "成熟 · 3木" if p.state == "mature" else "生长中 · 约%d秒" % maxi(0, ceili((p.maturesAtMs-now)/1000.0)), p.plantId.left(14)]
	if p.is_empty() and occupied_by_resident:
		plot_status.text += "\n树干位置有人，请先走到林位旁。"
	if observed.self.inventory.wood > 9:
		plot_status.text += "\n整株采收需腾出3木容量。"
	var b := _bench()
	bench_go.disabled = not can_submit or b.is_empty()
	craft_axe_button.disabled = not can_submit or observed.self.inventory.wood < 2 or not _can_reach(b)
	bench_status.text = "尚无工作台。" if b.is_empty() else "距台%.2f米 · 制斧须在1.6米内且通路可达。" % Forestry.Notes.distance(observed.self.position, b.position)

func _send(type: String) -> void:
	if not can_submit:
		return
	var a := {"type": type, "capabilityVersion": 1}
	var own := _own()
	match type:
		"craft_forestry_tool":
			a.merge({"entityId": selected_bench, "recipeId": "wooden_axe.v1"})
		"cancel_forest_reservation":
			a.reservationId = own.get("reservationId", "")
		"collect_seed":
			a.merge({"sourceId": "nursery-west", "reservationId": own.get("reservationId", "")})
		"plant_tree":
			a.merge({"plotId": selected_plot, "reservationId": own.get("reservationId", "")})
		"harvest_tree":
			a.merge({"plantId": _plant().get("plantId", ""), "reservationId": own.get("reservationId", ""), "toolId": selected_tool})
	if Forestry.valid_action(a):
		requested.emit(a)
