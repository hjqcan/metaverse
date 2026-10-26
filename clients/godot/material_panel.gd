extends PanelContainer
## Read current qualification separately from the immutable request receipt.
signal action_requested(action: Dictionary)
signal destination_requested(point: Vector2)
const Evidence = preload("res://command_evidence.gd")
var summary: Label
var reservation_label: Label
var request_button: Button
var travel_button: Button
var harvest_button: Button
var cancel_button: Button
var observed: Dictionary = {}

func _ready() -> void:
	var box := VBoxContainer.new()
	box.add_theme_constant_override("separation", 7)
	add_child(box)
	var title := Label.new()
	title.text = "东岸采集区"
	title.add_theme_font_size_override("font_size", 18)
	box.add_child(title)
	summary = Label.new()
	box.add_child(summary)
	reservation_label = Label.new()
	reservation_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	reservation_label.custom_minimum_size = Vector2(265, 54)
	box.add_child(reservation_label)
	var row := HBoxContainer.new()
	box.add_child(row)
	request_button = _button(row, "预约3木材", func(): action_requested.emit({"type": "reserve_material", "sourceId": "wood-source-east"}))
	travel_button = _button(row, "前往采集区", func(): destination_requested.emit(Vector2(28, 10)))
	var actions := HBoxContainer.new()
	box.add_child(actions)
	harvest_button = _button(actions, "采集1木材", func(): _request_current("harvest_material"))
	cancel_button = _button(actions, "取消预约", func(): _request_current("cancel_reservation"))
	hide()

func _button(parent: Node, title: String, callback: Callable) -> Button:
	var button := Button.new()
	button.text = title
	button.focus_mode = Control.FOCUS_NONE
	button.custom_minimum_size.y = 36
	button.pressed.connect(callback)
	parent.add_child(button)
	return button

func _request_current(type: String) -> void:
	var reservation = observed.get("materialAccess", {}).get("currentReservation")
	if reservation is Dictionary and reservation.get("actorId") == observed.get("self", {}).get("actorId"):
		action_requested.emit({"type": type, "reservationId": reservation.reservationId})

func update_world(value: Dictionary, can_act: bool) -> void:
	observed = value
	visible = Evidence.material_supported(value)
	if not visible:
		return
	var source: Dictionary = value.materialAccess
	var reservation = source.currentReservation
	summary.text = "未采木材 %d / 6 · 剩余来源额度 %d" % [source.stockWood, 12 - source.generatedWood]
	request_button.disabled = not can_act or not source.active or reservation != null
	travel_button.disabled = not can_act
	harvest_button.disabled = true
	cancel_button.disabled = true
	if not source.active:
		reservation_label.text = "采集区尚未开启。此处可通行，保留用于采集。"
	elif not reservation is Dictionary:
		reservation_label.text = "预约后按顺序获得3份采集资格。\n需要亲自到达采集区，每次采集1木材。"
		if source.stockWood + 12 - source.generatedWood < 3:
			reservation_label.text = "本来源剩余材料不足3份，无法接受新预约。"
			request_button.disabled = true
	else:
		var own: bool = reservation.get("actorId") == value.self.actorId
		if not own:
			reservation_label.text = "本组已有居民 %s 的预约。\n该资格由原预约居民采集。" % reservation.get("actorId", "")
		elif reservation.get("status") == "queued":
			var ahead := 0
			for entry in source.queue:
				if entry.get("queueSequence", 0) < reservation.queueSequence:
					ahead += 1
			reservation_label.text = "排队中 · 前方 %d 份请求\n授予后有60服务秒采集，不计停服时间。" % ahead
			cancel_button.disabled = not can_act
		elif reservation.get("status") == "active":
			var remaining_ms: int = maxi(0, int(reservation.expiresAtMs) - int(source.serviceMs))
			reservation_label.text = "可采 %d 木材 · 剩余 %d 服务秒\n靠近采集区后逐次采集，未采部分到期释放。" % [reservation.remaining, ceili(remaining_ms / 1000.0)]
			harvest_button.disabled = not can_act or remaining_ms == 0 or value.self.inventory.wood >= 12 \
				or Evidence.distance(value.self.position, source.position) > 1.6
			cancel_button.disabled = not can_act
