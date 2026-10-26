extends PanelContainer
## Plain text drafts are separate from immutable published notes and pending commands.
signal requested(action: Dictionary)
signal destination_requested(point: Vector2)
const Notes = preload("res://entity_note_evidence.gd")
var title: Label
var entries: VBoxContainer
var draft: LineEdit
var reference: Label
var status: Label
var hint: Label
var send_button: Button
var travel_button: Button
var observed: Dictionary = {}
var available = false
var can_edit = false
var reply_id: Variant = null
var identity_key = ""
var notes_key = ""
var pending_id = ""

func label(parent: Node, text: String) -> Label:
	var node = Label.new()
	node.text = text
	node.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	node.custom_minimum_size.x = 360
	parent.add_child(node)
	return node

func _ready() -> void:
	var box = VBoxContainer.new()
	box.add_theme_constant_override("separation", 8)
	add_child(box)
	title = label(box, "旧桥共同手记")
	title.add_theme_font_size_override("font_size", 20)
	var scroll = ScrollContainer.new()
	scroll.custom_minimum_size = Vector2(370, 180)
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	box.add_child(scroll)
	entries = VBoxContainer.new()
	entries.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	entries.add_theme_constant_override("separation", 8)
	scroll.add_child(entries)
	reference = label(box, "草稿 · 独立留言")
	draft = LineEdit.new()
	draft.placeholder_text = "写下你想留给后来者的话（最多160字）"
	draft.max_length = 160
	draft.custom_minimum_size.y = 42
	box.add_child(draft)
	draft.text_changed.connect(func(_value): _update_send())
	hint = label(box, "")
	var status_scroll = ScrollContainer.new()
	status_scroll.custom_minimum_size = Vector2(370, 64)
	status_scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	box.add_child(status_scroll)
	status = label(status_scroll, "")
	status.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	var row = HBoxContainer.new()
	box.add_child(row)
	send_button = Button.new()
	send_button.text = "发表手记"
	send_button.pressed.connect(func():
		if not send_button.disabled:
			requested.emit({"type": "append_entity_note", "entityId": observed.entityNotes.target.entityId,
				"text": draft.text, "replyToNoteId": reply_id}))
	row.add_child(send_button)
	travel_button = Button.new()
	travel_button.text = "走到旧桥"
	travel_button.pressed.connect(func():
		if Notes.supported(observed):
			var point: Array = observed.entityNotes.target.position
			hide()
			destination_requested.emit(Vector2(point[0], point[1])))
	row.add_child(travel_button)
	var clear = Button.new()
	clear.text = "新留言"
	clear.pressed.connect(clear_draft)
	row.add_child(clear)
	var close = Button.new()
	close.text = "关闭"
	close.pressed.connect(close_panel)
	row.add_child(close)
	hide()

func clear_draft() -> void:
	draft.clear()
	reply_id = null
	reference.text = "草稿 · 独立留言"
	_update_send()

func close_panel() -> void:
	clear_draft()
	hide()

func update_world(value: Dictionary, can_act: bool, pending: Dictionary, receipt: Dictionary, generation: int) -> void:
	observed = value
	var key = str(generation) + ":" + str(value.get("world", {}).get("instanceId")) + ":" + str(value.get("self", {}).get("actorId"))
	if key != identity_key:
		identity_key = key
		clear_draft()
		pending_id = ""
		status.text = ""
		hide()
	available = can_act and Notes.supported(value)
	can_edit = pending.is_empty() and Notes.supported(value)
	if not Notes.supported(value):
		hide()
		return
	var data: Dictionary = value.entityNotes
	title.text = "旧桥共同手记\n设施建造者：%s" % data.target.ownerActorId
	var signature = JSON.stringify(data.notes)
	if signature != notes_key:
		notes_key = signature
		for child in entries.get_children():
			entries.remove_child(child)
			child.queue_free()
		if data.notes.is_empty():
			label(entries, "还没有人留下手记。你可以只读，也可以走近旧桥写下第一句。")
		var indexes: Dictionary = {}
		for note in data.notes:
			indexes[note.noteId] = indexes.size() + 1
			var caption = "#%d · 居民 %s" % [indexes[note.noteId], note.authorActorId]
			if note.replyToNoteId != null:
				caption += " · 接写 #%d" % indexes.get(note.replyToNoteId, 0)
			label(entries, caption)
			label(entries, note.text)
			var reply = Button.new()
			reply.text = "接写 #%d" % indexes[note.noteId]
			reply.pressed.connect(func():
				reply_id = note.noteId
				reference.text = "草稿 · 接写居民 %s 的 #%d" % [note.authorActorId, indexes[note.noteId]]
				draft.grab_focus()
				_update_send())
			entries.add_child(reply)
	var original = JSON.parse_string(pending.get("body", "{}"))
	if not original is Dictionary:
		original = {}
	if original.get("action", {}).get("type") == "append_entity_note":
		pending_id = str(original.get("commandId"))
		status.text = "未确认 · 原文：" + str(original.action.text) + "\n请查询原动作；关闭面板仍会保留原请求。"
	elif not pending_id.is_empty() and receipt.get("commandId") == pending_id:
		status.text = "已确认发表 · " + str(receipt.get("result", {}).get("text", "")) if receipt.get("status") == "committed" else "未发表 · " + str(receipt.get("error", {}).get("message", "原动作被拒绝"))
		pending_id = ""
		clear_draft()
	_update_send()

func _update_send() -> void:
	if send_button == null:
		return
	send_button.disabled = true
	draft.editable = can_edit
	travel_button.disabled = not available
	if not Notes.supported(observed):
		return
	var data: Dictionary = observed.entityNotes
	var distance = Notes.distance(observed.self.position, data.target.position)
	hint.text = "%d / 160 字 · 你已发表 %d / 2 · 共 %d / 6\n距离旧桥 %.1f 米，走近至1.6米内可发表。" % [draft.text.length(), data.selfCount, data.totalCount, distance]
	send_button.disabled = not available or not Notes.valid_text(draft.text) or distance > 1.6 or data.selfCount >= 2 or data.totalCount >= 6
	if data.selfCount >= 2 or data.totalCount >= 6:
		hint.text += "\n本次共同手记已达发表上限，仍可阅读。"
