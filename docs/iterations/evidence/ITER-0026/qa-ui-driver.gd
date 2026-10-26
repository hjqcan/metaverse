extends SceneTree
const Canvas = preload("res://entity_canvas_evidence.gd")
var app: Node
var client: Node
var panel: Node
var output: String
var checks: Array = []
var inputs: Array = []
var frames: Array = []
var fixtures: Dictionary = {}
var original: Dictionary = {}
var requested_count := 0
var destination_count := 0
var current_group := "startup"

func _initialize() -> void:
    call_deferred("run")

func check(ok: bool, label: String) -> void:
    checks.append({"group":current_group,"name":label,"passed":ok})
    if not ok:
        push_error(label)
        write_report(false)

func write_json(path: String, value: Variant) -> void:
    var file := FileAccess.open(path, FileAccess.WRITE)
    file.store_string(JSON.stringify(value,"  "))
    file.close()

func write_report(passed: bool) -> void:
    write_json(output+".json",{"passed":passed,"checks":checks,"inputEvents":inputs,"frames":frames,
        "actualObservation":original,"syntheticObservationFixtures":fixtures,"businessSignals":requested_count,
        "destinationSignals":destination_count,"actualModelCalls":0})

func phase(name: String) -> void:
    current_group=name
    write_json(OS.get_environment("QA_PHASE_FILE"),{"phase":name})

func idle() -> void:
    for i in 500:
        await create_timer(0.02).timeout
        if not client.busy:return
    check(false,"initial HTTP deadline")

func click(control: Control, label: String) -> void:
    await process_frame
    check(control.is_visible_in_tree(),label+" visible to mouse")
    var point: Vector2=control.get_global_rect().get_center()
    var move := InputEventMouseMotion.new()
    move.position=point;move.global_position=point
    Input.parse_input_event(move)
    await process_frame
    var event := InputEventMouseButton.new()
    event.position=point;event.global_position=point;event.button_index=MOUSE_BUTTON_LEFT;event.pressed=true
    Input.parse_input_event(event)
    await process_frame
    event=event.duplicate();event.pressed=false
    Input.parse_input_event(event)
    await process_frame
    inputs.append({"kind":"mouse_click","label":label,"point":[point.x,point.y],"group":current_group})

func select_history(index: int) -> void:
    await click(panel.history_selector,"open recent creation selector")
    var popup: PopupMenu=panel.history_selector.get_popup()
    await process_frame
    check(popup.visible,"native history popup is visible")
    check(popup.item_count<=3,"actual mouse selection uses original two or labelled three-item menu")
    var point := Vector2(float(popup.size.x)/2.0,(float(index)+0.5)*float(popup.size.y)/float(popup.item_count))
    var move := InputEventMouseMotion.new()
    var global_point: Vector2=Vector2(popup.position)+point
    move.position=global_point;move.global_position=global_point
    Input.parse_input_event(move)
    await process_frame
    var event := InputEventMouseButton.new()
    event.position=global_point;event.global_position=global_point;event.button_index=MOUSE_BUTTON_LEFT;event.pressed=true
    Input.parse_input_event(event)
    await process_frame
    event=event.duplicate();event.pressed=false
    Input.parse_input_event(event)
    await process_frame
    inputs.append({"kind":"native_popup_mouse_click","index":index,"localPoint":[point.x,point.y],"globalPoint":[global_point.x,global_point.y],"inputMethod":"Input.parse_input_event","group":current_group})
    check(not popup.visible and panel.history_selector.selected==index,"native mouse selects intended record "+str(index))

func surface() -> Array:
    var result: Array=[]
    for node in app.world_view.objects.get_children():
        if node.has_meta("canvas_cell"):
            result.append({"cell":node.get_meta("canvas_cell"),"color":node.get_meta("canvas_color"),"author":node.get_meta("canvas_author")})
    return result

func patch_is(edit: Dictionary, label: String) -> void:
    var expected: Dictionary={}
    for cell in edit.patch:expected[int(cell.y)*5+int(cell.x)]=cell.color
    var correct := true
    for i in 25:
        var button: Button=panel.history_cells[i]
        var style: StyleBoxFlat=button.get_theme_stylebox("normal")
        if expected.has(i):
            correct=correct and button.get_meta("history_changed") and button.get_meta("history_color")==expected[i]
            correct=correct and style.bg_color==Color(Canvas.HEX[Canvas.COLORS.find(expected[i])])
            correct=correct and button.text=="" and button.tooltip_text.contains(edit.authorActorId)
        else:
            correct=correct and not button.get_meta("history_changed") and button.text=="·" and button.tooltip_text.contains("本次未修改")
            for color in Canvas.HEX:correct=correct and style.bg_color!=Color(color)
    check(correct,label+" exact patch colors, author and neutral unchanged cells")
    check(panel.history_detail.text.contains(edit.authorActorId) and panel.history_detail.text.contains("第%d次创作"%edit.revision),label+" original author and ordinal")
    check(panel.selected_history_key.contains(edit.commandId),label+" original command identity")
    check(not panel.send_button.visible and not panel.travel_button.visible and not panel.reset_button.visible,label+" editing and travel actions hidden")

func capture(name: String, kind: String) -> void:
    await process_frame
    await RenderingServer.frame_post_draw
    var file: String=output+"-"+name+".png"
    check(root.get_texture().get_image().save_png(file)==OK,"saved "+name)
    frames.append({"name":name,"kind":kind,"path":file,"historyMode":panel.history_mode,"selectedOriginal":panel.selected_history_key,
        "detail":panel.history_detail.text,"summary":panel.history_summary.text})

func synthetic(revision: int) -> Dictionary:
    var value: Dictionary=original.duplicate(true)
    var cap: Dictionary=value.entityCanvas
    if revision==0:
        cap.revision=0;cap.editCount=0;cap.recentEdits=[]
        for cell in cap.cells:
            cell.color="blank";cell.authorActorId=null;cell.commandId=null;cell.stateVersion=null
        return value
    for number in range(3,revision+1):
        var edit: Dictionary=original.entityCanvas.recentEdits[1].duplicate(true)
        edit.baseRevision=number-1;edit.revision=number;edit.commandId="explicit-synthetic-creation-"+str(number)
        edit.stateVersion=int(original.stateVersion)+number-2;edit.eventCursor=edit.stateVersion+1
        edit.patch=[{"x":0,"y":0,"color":"blank" if number==3 else "sun" if number%2==0 else "ink"}]
        cap.recentEdits.append(edit)
        cap.cells[0].color=edit.patch[0].color;cap.cells[0].commandId=edit.commandId;cap.cells[0].stateVersion=edit.stateVersion
    cap.revision=revision;cap.editCount=revision
    if cap.recentEdits.size()>50:cap.recentEdits=cap.recentEdits.slice(-50)
    value.stateVersion=int(original.stateVersion)+maxi(0,revision-2);value.eventCursor=value.stateVersion+1
    return value

func apply_fixture(value: Dictionary, ready: bool, pending: Dictionary, receipt: Dictionary, generation: int, name: String) -> void:
    fixtures[name]=value.duplicate(true)
    check(Canvas.supported(value),name+" passes existing capability validation")
    panel.update_world(value,ready,pending,receipt,generation)

func run() -> void:
    output=OS.get_environment("QA_OUTPUT")
    create_timer(70).timeout.connect(func():write_report(false);quit(2))
    app=load("res://main.tscn").instantiate()
    root.add_child(app)
    app.set_physics_process(false) # Isolate selection from the existing periodic refresh loop.
    client=app.client;panel=app.canvas_panel
    await idle()
    original=client.observation.duplicate(true)
    check(client.healthy and original.self.actorId=="a3","actual authenticated non-author observation")
    check(Canvas.supported(original) and original.entityCanvas.revision==2,"actual original revision two")
    check(Canvas.Notes.distance(original.self.position,original.entityCanvas.target.position)>1.6,"viewer outside submit distance")
    check(original.entityCanvas.cells.all(func(c):return c.authorActorId!="a3"),"viewer owns none of the current cells")
    var original_surface: Array=surface()
    check(original_surface.size()==25,"actual current platform has 25 cells")
    var client_pending: String=JSON.stringify(client.pending)
    var client_receipt: String=JSON.stringify(client.last_receipt)
    panel.requested.connect(func(_action):requested_count+=1)
    panel.destination_requested.connect(func(_point):destination_count+=1)
    var target: Array=original.entityCanvas.target.position
    app.world_view.set_process(false)
    app.world_view.focus=Vector3(target[0],0,target[1]);app.world_view.camera.size=7.0
    app.world_view.camera.position=app.world_view.focus+Vector3(0,16,24);app.world_view.camera.look_at(app.world_view.focus)
    phase("actual_original_5_4_9")
    await click(app.canvas_button,"open original canvas as a3")
    await capture("actual-current-nine","actual original observation")
    await click(panel.history_button,"open recent creations")
    check(panel.history_mode and panel.history_selector.item_count==2,"two original records offered")
    await select_history(0);patch_is(original.entityCanvas.recentEdits[0],"first original five cells")
    check(surface()==original_surface,"first history view leaves 3D current nine-cell picture unchanged")
    await capture("actual-first-five","actual original observation")
    await select_history(1);patch_is(original.entityCanvas.recentEdits[1],"second original four cells")
    check(surface()==original_surface,"second history view leaves 3D current picture unchanged")
    await capture("actual-second-four","actual original observation")
    await click(panel.history_button,"return to current work")
    check(not panel.history_mode and panel.cells.size()==25,"returns to actual current editor")
    check(surface()==original_surface and client.observation==original,"view selection does not mutate actual observation or scene")
    await capture("actual-returned-nine","actual original observation")

    phase("actual_local_draft_preservation")
    await click(panel.cells[1],"draft on one unowned cell without sending")
    var saved_draft: String=JSON.stringify(panel.draft)
    var saved_base: int=panel.base_revision
    check(panel.draft.size()==1 and saved_base==2,"actual local mouse draft uses original revision")
    await click(panel.history_button,"browse with an existing draft")
    await select_history(0)
    await click(panel.history_cells[5],"inspect historical cell only")
    await select_history(1)
    check(JSON.stringify(panel.draft)==saved_draft and panel.base_revision==saved_base,"history selection preserves draft and original base")
    var close_button: Button=panel.history_button.get_parent().get_children()[-1]
    await click(close_button,"close history panel")
    await click(app.canvas_button,"reopen canvas")
    check(not panel.history_mode and JSON.stringify(panel.draft)==saved_draft,"closing opens current work and preserves draft")

    phase("recorded_pending_and_zero_wood_ui_fixture")
    var pending: Dictionary=JSON.parse_string(FileAccess.get_file_as_string(OS.get_environment("QA_PENDING_INPUT")))
    var receipt: Dictionary=JSON.parse_string(FileAccess.get_file_as_string(OS.get_environment("QA_RECEIPT_INPUT")))
    var pending_before: String=JSON.stringify(pending)
    var receipt_before: String=JSON.stringify(receipt)
    var zero: Dictionary=original.duplicate(true);zero.self.inventory.wood=0
    var generation: int=client.connection_generation
    apply_fixture(zero,false,pending,receipt,generation,"explicit_zero_wood_pending_view")
    panel.show()
    await click(panel.history_button,"history while business actions unavailable")
    await select_history(0);patch_is(original.entityCanvas.recentEdits[0],"zero wood pending viewer original five")
    await click(panel.history_button,"return with pending preserved")
    check(JSON.stringify(pending)==pending_before and JSON.stringify(receipt)==receipt_before,"recorded pending and unrelated receipt inputs untouched")
    check(JSON.stringify(panel.draft)==saved_draft and panel.base_revision==saved_base,"pending viewing retains original local draft")
    check(panel.send_button.disabled and panel.reset_button.disabled,"pending current editor remains unable to act")

    phase("explicit_later_edit_and_blank_ui_fixture")
    var third: Dictionary=synthetic(3)
    apply_fixture(third,true,{}, {},generation,"explicit_later_same_author_blank")
    check(JSON.stringify(panel.draft)==saved_draft and panel.base_revision==2 and panel.send_button.disabled,"later revision retains stale draft and prevents old submit")
    await click(panel.history_button,"browse original after later repaint")
    await select_history(1);patch_is(original.entityCanvas.recentEdits[1],"older leaf remains in original edit")
    await select_history(2);patch_is(third.entityCanvas.recentEdits[2],"later blank is one changed cell")
    check(panel.history_cells[0].get_theme_stylebox("normal").bg_color!=panel.history_cells[1].get_theme_stylebox("normal").bg_color,"painted blank differs visibly from unchanged neutral cell")
    await capture("synthetic-blank-patch","explicit synthetic observation; no new world edit")
    await click(panel.history_button,"current synthetic later blank")
    check(panel.cells[0].get_theme_stylebox("normal").bg_color==Color(Canvas.HEX[0]),"current fixture shows later blank while old entry kept original leaf")
    check(panel.base_revision==2 and JSON.stringify(panel.draft)==saved_draft,"return did not silently rebase stale draft")
    await click(panel.reset_button,"explicitly choose a new draft after stale warning")
    check(panel.base_revision==3 and panel.draft.is_empty(),"only explicit new draft adopts current revision")

    phase("explicit_recent_window_fixtures")
    generation+=1
    apply_fixture(original.duplicate(true),true,{}, {},generation,"recorded_two_edits_new_connection_fixture")
    panel.show();await click(panel.history_button,"choose stable original before window changes")
    await select_history(1)
    var key: String=panel.selected_history_key
    var fifty: Dictionary=synthetic(50);apply_fixture(fifty,true,{}, {},generation,"explicit_fifty_edits")
    check(panel.history_selector.item_count==50 and panel.selected_history_key==key and panel.history_selector.selected==1,"fifty records keep same original selected")
    var fifty_one: Dictionary=synthetic(51);apply_fixture(fifty_one,true,{}, {},generation,"explicit_fifty_one_edits")
    check(panel.history_selector.item_count==50 and panel.selected_history_key==key and panel.history_selector.selected==0,"window shift preserves command identity at its new index")
    patch_is(original.entityCanvas.recentEdits[1],"same original after index moved")
    check(panel.history_summary.text.contains("共51次") and panel.history_summary.text.contains("仅显示最近50次"),"total and truncated recent range explicit")
    var fifty_two: Dictionary=synthetic(52);apply_fixture(fifty_two,true,{}, {},generation,"explicit_selected_edit_outside_window")
    check(panel.selected_history_key=="" and panel.history_selector.selected==-1,"slid-out original selection cleared without picking replacement")
    check(panel.history_summary.text.contains("所选创作已超出最近50次") and panel.history_cells.all(func(c):return not c.get_meta("history_changed")),"slid-out notice and unselected neutral grid")
    await capture("synthetic-window-slide","explicit synthetic fifty-two-edit observation")
    generation+=1
    var blank: Dictionary=synthetic(0);apply_fixture(blank,true,{}, {},generation,"explicit_no_edits")
    panel.show();await click(panel.history_button,"open explicitly empty history")
    check(panel.history_selector.item_count==0 and panel.history_selector.disabled and panel.history_summary.text.contains("还没有创作"),"empty history has explicit disabled choice")

    phase("explicit_identity_and_capability_fixtures")
    for kind in ["actor","generation","instance","target","unknown"]:
        generation+=1
        apply_fixture(original.duplicate(true),true,{}, {},generation,"before_"+kind)
        panel.show();await click(panel.history_button,"open prior selection before "+kind);await select_history(0)
        var changed: Dictionary=original.duplicate(true)
        if kind=="actor":
            changed.self.actorId="a1";changed.identity.actorId="a1";changed.identity.operatorId="local-operator"
        elif kind=="generation":generation+=1
        elif kind=="instance":
            changed.world.instanceId="w_"+"1".repeat(32);changed.entityCanvas.adoption.worldInstanceId=changed.world.instanceId
        elif kind=="target":
            var old_id: String=changed.entityCanvas.target.entityId
            var new_id: String="e"+"1".repeat(32)
            changed.entityCanvas.target.entityId=new_id
            for entity in changed.entities:
                if entity.entityId==old_id:entity.entityId=new_id
            for edit in changed.entityCanvas.recentEdits:edit.entityId=new_id
        else:changed.entityCanvas.version=99
        if kind=="unknown":
            fixtures[kind]=changed.duplicate(true);panel.update_world(changed,true,{}, {},generation)
        else:apply_fixture(changed,true,{}, {},generation,"changed_"+kind)
        check(not panel.history_mode and panel.selected_history_key=="",kind+" clears old selection")
        if kind!="target":check(not panel.visible,kind+" closes old view")

    phase("final_no_world_side_effects")
    check(requested_count==0 and destination_count==0,"all viewing and fixture interactions emitted zero business or travel signals")
    check(client.observation==original and surface()==original_surface,"original real observation and 3D cells remain untouched")
    check(JSON.stringify(client.pending)==client_pending and JSON.stringify(client.last_receipt)==client_receipt,"actual client original pending and receipt untouched")
    write_report(checks.all(func(c):return c.passed))
    quit(0 if checks.all(func(c):return c.passed) else 1)
