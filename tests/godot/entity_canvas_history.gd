extends SceneTree
## Recorded product data plus explicitly synthetic interface-boundary observations.
## No WorldClient is instantiated; submit signals are captured, never executed.
const CanvasPanel = preload("res://entity_canvas_panel.gd")
const View = preload("res://world_view.gd")
const Canvas = preload("res://entity_canvas_evidence.gd")
const GROUPS = ["original_two_creations", "draft_and_stale_revision",
	"pending_and_non_author_viewer", "blank_and_current_picture", "recent_window",
	"identity_changes", "unknown_capability", "current_editing_signals"]

var panel: CanvasPanel
var world_view: View
var open_button: Button
var banner: Label
var original: Dictionary
var checks: Array = []
var groups: Array = []
var mouse_events: Array = []
var requested: Array = []
var destinations: Array = []
var screenshots: Array = []
var generation := 0
var current_group := "setup"
var output: String
var shot_dir: String
var finished := false

func _initialize() -> void:
	call_deferred("run")

func check(ok: bool, label: String) -> void:
	checks.append({"group": current_group, "name": label, "passed": ok})
	if not ok:
		push_error(current_group + ": " + label)

func frames(count: int = 2) -> void:
	for _frame in count:
		await process_frame

func move_mouse(point: Vector2) -> void:
	var event := InputEventMouseMotion.new()
	event.position = point
	event.global_position = point
	Input.parse_input_event(event)
	await process_frame

func click_point(point: Vector2, label: String) -> void:
	await move_mouse(point)
	var press := InputEventMouseButton.new()
	press.position = point
	press.global_position = point
	press.button_index = MOUSE_BUTTON_LEFT
	press.pressed = true
	Input.parse_input_event(press)
	await process_frame
	var release: InputEventMouseButton = press.duplicate()
	release.pressed = false
	Input.parse_input_event(release)
	await frames()
	mouse_events.append({"group": current_group, "control": label, "point": [point.x, point.y],
		"coordinates": "root window", "inputMethod": "Input.parse_input_event"})

func click(control: Control, label: String) -> bool:
	if not control.is_visible_in_tree():
		check(false, "mouse target is visible: " + label)
		return false
	var parent: Node = control.get_parent()
	while parent != null:
		if parent is ScrollContainer:
			parent.ensure_control_visible(control)
			await frames()
		parent = parent.get_parent()
	var point := control.get_global_rect().get_center()
	if not Rect2(Vector2.ZERO, Vector2(root.size)).has_point(point):
		check(false, "mouse target is inside the rendered window: " + label)
		return false
	await click_point(point, label)
	return true

func choose(index: int) -> bool:
	if not await click(panel.history_selector, "history dropdown"):
		return false
	var popup: PopupMenu = panel.history_selector.get_popup()
	check(popup.visible, "mouse opens the actual history popup")
	if not popup.visible:
		return false
	# Embedded popups receive root-window coordinates. Click actual rows without
	# emitting item_selected or depending on PopupMenu's hover-focus bookkeeping.
	var row_height := popup.get_theme_font("font").get_height(popup.get_theme_font_size("font_size")) \
		+ popup.get_theme_constant("v_separation")
	var top := popup.get_theme_stylebox("panel").get_content_margin(SIDE_TOP)
	var point := Vector2(popup.size.x / 2.0, top + (index + 0.5) * row_height)
	if popup.item_count <= 3:
		point.y = (index + 0.5) * popup.size.y / popup.item_count
	await click_point(Vector2(popup.position) + point, "history item " + str(index))
	var selected := not popup.visible and panel.history_selector.selected == index
	check(selected, "mouse chooses history item " + str(index))
	if not selected:
		print("Popup diagnostic: ", {"position": popup.position, "size": popup.size,
			"rowHeight": row_height, "top": top, "clickLocal": point, "selected": panel.history_selector.selected})
		await screenshot("failed-popup-" + current_group)
		popup.hide()
	return selected

func screenshot(name: String) -> void:
	await frames()
	await RenderingServer.frame_post_draw
	var file := shot_dir.path_join(name + ".png")
	var image := root.get_texture().get_image()
	check(image != null and image.save_png(file) == OK, "rendered screenshot " + name)
	screenshots.append(name + ".png")

func surface() -> Array:
	return world_view.objects.get_children().filter(func(node: Node) -> bool:
		return node.has_meta("canvas_cell"))

func surface_state() -> Array:
	var result: Array = []
	for node: Node in surface():
		result.append([node.get_meta("canvas_cell"), node.get_meta("canvas_color"), node.get_meta("canvas_author")])
	return result

func changed_count() -> int:
	return panel.history_cells.filter(func(cell: Button) -> bool:
		return cell.get_meta("history_changed", false)).size()

func expected_patch(edit: Dictionary) -> void:
	var colors: Dictionary = {}
	for cell: Dictionary in edit.patch:
		colors[int(cell.y) * 5 + int(cell.x)] = cell.color
	var matches := true
	for i in 25:
		var cell: Button = panel.history_cells[i]
		matches = matches and cell.get_meta("history_changed", false) == colors.has(i)
		matches = matches and cell.get_meta("history_color", "") == colors.get(i, "")
	check(matches, "displayed 25 cells exactly match the selected original patch")
	check(panel.history_detail.text.contains(str(edit.authorActorId))
		and panel.history_detail.text.contains("第%d次" % edit.revision)
		and panel.history_detail.text.contains("%d格" % edit.patch.size()),
		"selected author, revision and patch count are visible")

func apply_observation(value: Dictionary, can_act: bool = true,
		pending: Dictionary = {}, receipt: Dictionary = {}) -> void:
	panel.update_world(value, can_act, pending, receipt, generation)
	world_view.update_world(value)
	var target: Array = value.get("entityCanvas", {}).get("target", {}).get("position", [24, 7])
	world_view.focus = Vector3(target[0], 0, target[1])
	world_view.zoom = 8.0
	# Fix only the harness camera on the original platform; otherwise the product
	# animation loop follows the remote viewer away from this read-only evidence.
	world_view.camera.size = world_view.zoom
	world_view.camera.position = world_view.focus + Vector3(0, 18, 18)
	world_view.camera.look_at(world_view.focus)
	await frames()

func begin(value: Dictionary, source: String, can_act: bool = true,
		pending: Dictionary = {}, receipt: Dictionary = {}) -> bool:
	generation += 1
	banner.text = source
	check(Canvas.supported(value), "input passes the unchanged product capability validator")
	await apply_observation(value, can_act, pending, receipt)
	await click(open_button, "open original product panel")
	check(panel.visible and not panel.history_mode, "panel opens in current-work mode")
	return panel.visible

func enter_history() -> bool:
	await click(panel.history_button, "recent creations")
	check(panel.history_mode, "mouse enters history viewing")
	return panel.history_mode

func synthetic_next(value: Dictionary, color: String = "ink") -> Dictionary:
	var next: Dictionary = value.duplicate(true)
	var cap: Dictionary = next.entityCanvas
	var edit: Dictionary = original.entityCanvas.recentEdits[1].duplicate(true)
	edit.baseRevision = cap.revision
	edit.revision = int(cap.revision) + 1
	edit.commandId = "synthetic-ui-edit-%d" % edit.revision
	edit.stateVersion = int(next.stateVersion) + 1
	edit.eventCursor = edit.stateVersion + 1
	edit.patch = [{"x": 0, "y": 0, "color": color}]
	next.stateVersion = edit.stateVersion
	next.eventCursor = edit.eventCursor
	cap.revision = edit.revision
	cap.editCount = edit.revision
	cap.recentEdits.append(edit)
	if cap.recentEdits.size() > 50:
		cap.recentEdits.pop_front()
	cap.cells[0] = {"x": 0, "y": 0, "color": color, "authorActorId": edit.authorActorId,
		"commandId": edit.commandId, "stateVersion": edit.stateVersion}
	return next

func test_original_two_creations() -> bool:
	var value: Dictionary = original.duplicate(true)
	var serialized := JSON.stringify(value)
	await begin(value, "记录的原自然史观察 · 本轮只读界面验收，未连接世界")
	var initial_surface: Array = surface_state()
	check(surface().size() == 25 and surface().filter(func(n: Node) -> bool:
		return n.get_meta("canvas_author") != "").size() == 9, "current original platform has 9 authored cells")
	await enter_history()
	check(panel.history_selector.item_count == 2 and panel.selected_history_key.is_empty(),
		"two original creations in order, with no implicit initial selection")
	check(panel.history_summary.text.contains("共2次") and panel.history_summary.text.contains("最近2次"),
		"total and recent count are shown")
	if not await choose(0): return false
	expected_patch(value.entityCanvas.recentEdits[0])
	check(changed_count() == 5, "first creation displays its original 5 cells")
	await screenshot("original-first-five")
	if not await choose(1): return false
	expected_patch(value.entityCanvas.recentEdits[1])
	check(changed_count() == 4, "second creation displays its original 4 cells")
	await screenshot("original-second-four")
	check(surface_state() == initial_surface, "selecting old creations leaves the 3D current surface unchanged")
	await click(panel.history_button, "return to current work")
	check(not panel.history_mode and panel.cells[0].visible, "mouse returns to current-work editor")
	check(surface_state() == initial_surface, "returning still displays the original 9-cell current platform")
	check(JSON.stringify(value) == serialized and requested.is_empty() and destinations.is_empty(),
		"original observation is unchanged and viewing emitted no business signal")
	await screenshot("original-current-nine")
	return true

func test_draft_and_stale_revision() -> bool:
	var value: Dictionary = original.duplicate(true)
	await begin(value, "原观察上的本地未提交草图；后续revision为合成界面输入")
	await click(panel.cells[24], "local draft cell")
	var patch: Array = panel.patch().duplicate(true)
	var base: int = panel.base_revision
	check(patch.size() == 1, "real mouse creates one local unsubmitted draft cell")
	await enter_history()
	if not await choose(0): return false
	var key: String = panel.selected_history_key
	await click(panel.history_cells[5], "readonly historical cell")
	check(panel.patch() == patch and panel.base_revision == base, "clicking history cannot paint or rebase the draft")
	check(not panel.send_button.is_visible_in_tree() and not panel.reset_button.is_visible_in_tree()
		and not panel.travel_button.is_visible_in_tree(), "history hides submit, new-draft and travel actions")
	var newer: Dictionary = synthetic_next(value)
	check(Canvas.supported(newer), "labelled synthetic later observation is structurally valid")
	await apply_observation(newer)
	check(panel.selected_history_key == key and changed_count() == 5, "new revision preserves selection by original edit identity")
	await click(panel.history_button, "return with stale original draft")
	check(panel.patch() == patch and panel.base_revision == base and panel.send_button.disabled,
		"return keeps original patch and stale base, and stops old submission")
	check(panel.hint.text.contains("旧草图保留"), "stale draft is explained")
	panel.close_panel()
	await click(open_button, "reopen original draft")
	check(panel.patch() == patch and panel.base_revision == base, "closing and reopening preserves the original unsubmitted draft")
	check(requested.is_empty() and destinations.is_empty(), "draft/history interaction emits no business signal")
	return true

func test_pending_and_non_author_viewer() -> bool:
	var value: Dictionary = original.duplicate(true)
	value.self.actorId = "a3"
	value.self.inventory.wood = 0
	value.self.position = [5, 7]
	value.identity.actorId = "a3"
	value.identity.operatorId = Canvas.Notes.ROSTER.a3
	var pending := {"recordVersion": 5, "body": JSON.stringify({"commandId": "unresolved-own-command",
		"action": {"type": "paint_entity_canvas", "entityId": value.entityCanvas.target.entityId,
		"capabilityVersion": 1, "expectedCanvasRevision": 2, "patch": [{"x": 4, "y": 4, "color": "river"}]}})}
	var receipt := {"commandId": "previous-own-receipt", "status": "committed", "result": {"action": "walk"}}
	var before := JSON.stringify([value, pending, receipt])
	await begin(value, "合成边界：非作者a3、零库存、远处、禁止业务动作且有原pending", false, pending, receipt)
	await enter_history()
	if not await choose(0): return false
	expected_patch(value.entityCanvas.recentEdits[0])
	if not await choose(1): return false
	expected_patch(value.entityCanvas.recentEdits[1])
	await click(panel.history_button, "return while original command remains pending")
	check(JSON.stringify([value, pending, receipt]) == before, "viewing preserves the exact pending body, previous receipt and observation inputs")
	check(panel.pending_id == "unresolved-own-command" and panel.status.text.contains("未确认"),
		"another author's history never settles the viewer's pending command")
	check(requested.is_empty() and destinations.is_empty(), "non-author viewing does not retry, submit or travel")
	return true

func test_blank_and_current_picture() -> bool:
	var value: Dictionary = synthetic_next(original, "blank")
	await begin(value, "合成界面边界：a2后来擦白；原第2次创作仍为leaf")
	var current_surface: Array = surface_state()
	await enter_history()
	if not await choose(1): return false
	check(panel.history_cells[0].get_meta("history_color") == "leaf", "old creation keeps its original color after a later blank repaint")
	if not await choose(2): return false
	check(changed_count() == 1 and panel.history_cells[0].get_meta("history_color") == "blank",
		"blank is still one authored changed cell")
	check(not panel.history_cells[1].get_meta("history_changed") and panel.history_cells[1].get_meta("history_color") == ""
		and panel.history_cells[1].text == "·", "untouched cell is a neutral mark, not blank paint")
	var changed_style: StyleBoxFlat = panel.history_cells[0].get_theme_stylebox("normal")
	var untouched_style: StyleBoxFlat = panel.history_cells[1].get_theme_stylebox("normal")
	check(changed_style.bg_color != untouched_style.bg_color, "blank paint and untouched cells render in different colors")
	check(panel.history_cells[0].tooltip_text.contains("a2") and panel.history_cells[1].tooltip_text.contains("本次未修改"),
		"blank author and untouched meaning are available in cell descriptions")
	check(surface_state() == current_surface, "historic selection does not repaint the current platform")
	await screenshot("synthetic-blank-versus-untouched")
	return true

func test_recent_window() -> bool:
	var empty: Dictionary = original.duplicate(true)
	empty.entityCanvas.revision = 0
	empty.entityCanvas.editCount = 0
	empty.entityCanvas.recentEdits = []
	for cell: Dictionary in empty.entityCanvas.cells:
		cell.color = "blank"
		cell.authorActorId = null
		cell.commandId = null
		cell.stateVersion = null
	await begin(empty, "合成界面边界：0次创作")
	await enter_history()
	check(panel.history_selector.item_count == 0 and panel.history_selector.disabled
		and panel.history_summary.text.contains("还没有创作"), "zero creations have an honest empty state")
	var window: Dictionary = original.duplicate(true)
	while window.entityCanvas.revision < 51:
		window = synthetic_next(window, "leaf" if int(window.entityCanvas.revision) % 2 == 0 else "blank")
	await begin(window, "合成界面边界：51次修改、最近50条；未执行这些世界动作")
	await enter_history()
	check(panel.history_selector.item_count == 50 and panel.history_summary.text.contains("共51次")
		and panel.history_summary.text.contains("最近50次"), "51 revisions explicitly expose only the latest 50")
	if not await choose(1): return false
	var retained_key: String = panel.selected_history_key
	var later: Dictionary = synthetic_next(window)
	await apply_observation(later)
	check(panel.selected_history_key == retained_key and panel.history_selector.selected == 0,
		"selected original edit survives its array index changing")
	await begin(window, "合成界面边界：选择最旧可见记录，然后滑出最近50条")
	await enter_history()
	if not await choose(0): return false
	var expired_key: String = panel.selected_history_key
	await apply_observation(later)
	check(not expired_key.is_empty() and panel.selected_history_key.is_empty() and panel.history_selector.selected == -1,
		"expired selection is cleared instead of silently selecting the same index")
	check(changed_count() == 0 and panel.history_summary.text.contains("超出最近50次"),
		"expired selection shows no replacement patch and explains the recent window")
	return true

func test_identity_changes() -> bool:
	for kind: String in ["actor", "instance", "generation", "entity"]:
		var value: Dictionary = original.duplicate(true)
		await begin(value, "合成身份边界：" + kind)
		await enter_history()
		if not await choose(0): return false
		var changed: Dictionary = value.duplicate(true)
		if kind == "actor":
			changed.self.actorId = "a1"
			changed.identity.actorId = "a1"
			changed.identity.operatorId = Canvas.Notes.ROSTER.a1
		elif kind == "instance":
			changed.world.instanceId = "w_" + "f".repeat(32)
			changed.entityCanvas.adoption.worldInstanceId = changed.world.instanceId
		elif kind == "generation":
			generation += 1
		else:
			var old_id: String = changed.entityCanvas.target.entityId
			var new_id := "e" + "f".repeat(32)
			changed.entityCanvas.target.entityId = new_id
			for entity: Dictionary in changed.entities:
				if entity.entityId == old_id: entity.entityId = new_id
			for edit: Dictionary in changed.entityCanvas.recentEdits:
				edit.entityId = new_id
		check(Canvas.supported(changed), "synthetic " + kind + " observation passes the existing validator")
		await apply_observation(changed)
		check(not panel.history_mode and panel.selected_history_key.is_empty() and changed_count() == 0,
			kind + " change clears the prior world's viewing state")
		if kind != "entity":
			check(not panel.visible, kind + " change closes the old panel")
	return true

func test_unknown_capability() -> bool:
	for kind: String in ["missing", "unknown-version", "malformed-patch"]:
		await begin(original.duplicate(true), "合成能力边界：" + kind)
		await enter_history()
		if not await choose(0): return false
		var invalid: Dictionary = original.duplicate(true)
		if kind == "missing": invalid.erase("entityCanvas")
		elif kind == "unknown-version": invalid.entityCanvas.version = 99
		else: invalid.entityCanvas.recentEdits[0].patch[0].x = 0.5
		check(not Canvas.supported(invalid), "invalid " + kind + " capability is rejected by the original validator")
		panel.update_world(invalid, false, {}, {}, generation)
		await frames()
		check(not panel.visible and not panel.history_mode and panel.selected_history_key.is_empty()
			and changed_count() == 0, "invalid " + kind + " capability removes the previous viewing state")
		panel._show_history(true)
		check(not panel.history_mode, "invalid capability cannot reopen cached history")
	return true

func test_current_editing_signals() -> bool:
	var value: Dictionary = original.duplicate(true)
	value.self.position = value.entityCanvas.target.position.duplicate()
	value.self.inventory.wood = 0
	await begin(value, "合成输入：零库存a2在平台旁；只捕获提交信号，不执行世界命令")
	await click(panel.cells[24], "current-mode draft cell")
	var patch: Array = panel.patch().duplicate(true)
	check(patch.size() == 1 and not panel.send_button.disabled, "current mode still allows a nearby zero-inventory draft")
	await enter_history()
	if not await choose(0): return false
	await click(panel.history_cells[24], "readonly untouched historical cell")
	panel._submit()
	panel._new_draft()
	check(requested.is_empty() and panel.patch() == patch, "viewing mode guards submit/new-draft without losing the original patch")
	await click(panel.history_button, "return to editable current work")
	await click(panel.send_button, "current-mode submit signal only")
	check(requested.size() == 1 and requested[0] == {"type": "paint_entity_canvas",
		"entityId": value.entityCanvas.target.entityId, "capabilityVersion": 1,
		"expectedCanvasRevision": 2, "patch": patch}, "real mouse emits the original current-mode submit action exactly once")
	check(destinations.is_empty(), "viewing never emits a travel signal")
	return true

func write_result() -> void:
	var passed := groups.size() == GROUPS.size() and checks.size() > 0 \
		and checks.all(func(item: Dictionary) -> bool: return item.passed)
	var report := {"passed": passed, "groups": groups, "checks": checks, "mouseEvents": mouse_events,
		"screenshots": screenshots, "unexecutedSubmitSignals": requested, "travelSignals": destinations,
		"dataSources": {"original": "byte-identical ITER25 stage-both public observation",
			"synthetic": "explicitly labelled in each boundary group and screenshot banner"},
		"limitations": ["No live world service or HTTP adapter was used.",
			"Pending and receipt input dictionaries and action signals were checked; recovery-file I/O was not exercised."]}
	var file := FileAccess.open(output, FileAccess.WRITE)
	if file == null:
		push_error("Cannot write test results")
		quit(1)
		return
	file.store_string(JSON.stringify(report, "  "))
	file.close()
	finished = true
	quit(0 if passed else 1)

func run() -> void:
	output = OS.get_environment("GODOT_TEST_OUTPUT")
	shot_dir = OS.get_environment("GODOT_TEST_SCREENSHOTS")
	var watchdog := Timer.new()
	watchdog.one_shot = true
	root.add_child(watchdog)
	watchdog.timeout.connect(func():
		if not finished:
			check(false, "native UI runner exceeded its deadline")
			write_result())
	watchdog.start(120)
	root.gui_embed_subwindows = true
	var parsed: Variant = JSON.parse_string(FileAccess.get_file_as_string(OS.get_environment("GODOT_TEST_FIXTURE")))
	if not parsed is Dictionary:
		check(false, "recorded fixture is a JSON object")
		write_result()
		return
	original = parsed
	var background := Control.new()
	root.add_child(background)
	background.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	var theme := Theme.new()
	var font := SystemFont.new()
	font.font_names = PackedStringArray(["Noto Sans CJK SC", "sans-serif"])
	theme.default_font = font
	theme.default_font_size = 16
	background.theme = theme
	banner = Label.new()
	banner.position = Vector2(20, 14)
	banner.size = Vector2(1240, 50)
	banner.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	background.add_child(banner)
	world_view = View.new()
	world_view.position = Vector2(0, 100)
	world_view.size = Vector2(820, 800)
	background.add_child(world_view)
	world_view.set_process(false)
	panel = CanvasPanel.new()
	panel.position = Vector2(840, 90)
	panel.custom_minimum_size.x = 416
	var style := StyleBoxFlat.new()
	style.bg_color = Color("182c23")
	style.content_margin_left = 10
	style.content_margin_right = 10
	style.content_margin_top = 10
	style.content_margin_bottom = 10
	panel.add_theme_stylebox_override("panel", style)
	background.add_child(panel)
	panel.requested.connect(func(action: Dictionary): requested.append(action.duplicate(true)))
	panel.destination_requested.connect(func(point: Vector2): destinations.append([point.x, point.y]))
	open_button = Button.new()
	open_button.text = "平台地画"
	open_button.position = Vector2(20, 66)
	open_button.size = Vector2(150, 36)
	open_button.pressed.connect(func(): panel.show())
	background.add_child(open_button)
	await frames()
	for group: String in GROUPS:
		current_group = group
		var start := checks.size()
		var completed: Variant = await call("test_" + group)
		check(completed == true, "group completed all required interactions")
		var passed := checks.slice(start).all(func(item: Dictionary) -> bool: return item.passed)
		groups.append({"name": group, "passed": passed, "assertions": checks.size() - start,
			"source": "recorded original observation" if group == "original_two_creations" else "labelled synthetic UI boundary input"})
		print(group + (": PASS" if passed else ": FAIL"))
	write_result()
