extends PanelContainer
## Explicit recipient and amount; the authoritative command decides the transfer.
signal requested(recipient: String, amount: int)
const Evidence = preload("res://command_evidence.gd")
var recipient: OptionButton
var quantity: SpinBox
var send_button: Button
var hint: Label
var observed: Dictionary = {}
var available = false

func _ready() -> void:
	var box = VBoxContainer.new()
	box.add_theme_constant_override("separation", 10)
	add_child(box)
	var title = Label.new()
	title.text = "赠送木材"
	title.add_theme_font_size_override("font_size", 20)
	box.add_child(title)
	recipient = OptionButton.new()
	box.add_child(recipient)
	recipient.item_selected.connect(func(_index): _update_amount())
	var row = HBoxContainer.new()
	box.add_child(row)
	var label = Label.new()
	label.text = "数量"
	row.add_child(label)
	quantity = SpinBox.new()
	quantity.min_value = 1
	quantity.max_value = 12
	quantity.step = 1
	quantity.value = 1
	quantity.custom_minimum_size.x = 140
	row.add_child(quantity)
	quantity.value_changed.connect(func(_value): _update_amount())
	hint = Label.new()
	hint.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	hint.custom_minimum_size = Vector2(320, 52)
	box.add_child(hint)
	send_button = Button.new()
	send_button.text = "赠送"
	send_button.custom_minimum_size.y = 38
	send_button.pressed.connect(func():
		if not send_button.disabled and recipient.selected >= 0:
			requested.emit(str(recipient.get_item_metadata(recipient.selected)), int(quantity.value)))
	box.add_child(send_button)
	var close = Button.new()
	close.text = "关闭"
	close.pressed.connect(func(): hide())
	box.add_child(close)
	hide()

func update_world(value: Dictionary, can_act: bool) -> void:
	observed = value
	available = can_act and Evidence.transfer_supported(value)
	var selected = recipient.get_item_metadata(recipient.selected) if recipient.selected >= 0 else ""
	var ids: Array[String] = []
	for resident in value.get("residents", []):
		if resident.get("actorId") is String and resident.actorId != value.get("self", {}).get("actorId"):
			ids.append(resident.actorId)
	var existing: Array[String] = []
	for index in recipient.item_count:
		existing.append(str(recipient.get_item_metadata(index)))
	if ids != existing:
		recipient.clear()
		for actor in ids:
			recipient.add_item("居民 " + actor)
			recipient.set_item_metadata(recipient.item_count - 1, actor)
			if actor == selected:
				recipient.select(recipient.item_count - 1)
	_update_amount()

func _update_amount() -> void:
	if send_button == null:
		return
	send_button.disabled = true
	recipient.disabled = not available
	quantity.editable = available
	hint.text = "双方需在 1.6 米内，且之间没有障碍。"
	if not available or recipient.selected < 0:
		return
	var actor = str(recipient.get_item_metadata(recipient.selected))
	var amount = int(quantity.value)
	var wood = int(observed.get("self", {}).get("inventory", {}).get("wood", 0))
	for resident in observed.get("residents", []):
		if resident.get("actorId") == actor:
			var distance = Evidence.distance(observed.self.position, resident.position)
			hint.text = "送给 %s · %d 木材\n距离 %.1f 米，需在 1.6 米内且没有障碍。" % [actor, amount, distance]
			if wood < amount:
				hint.text += "\n你的木材不足。"
			send_button.disabled = wood < amount or distance > 1.6
			return
