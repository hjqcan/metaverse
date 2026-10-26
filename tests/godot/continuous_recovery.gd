extends SceneTree
var client: Node
var checks: Array = []
var output: String
func _initialize() -> void:
	call_deferred("run")
func check(ok: bool, label: String) -> void:
	checks.append({"name":label,"passed":ok})
	if not ok:
		push_error(label)
func finish() -> void:
	var ok = checks.all(func(item): return item.passed)
	var file = FileAccess.open(output+".json",FileAccess.WRITE)
	file.store_string(JSON.stringify({"passed":ok,"checks":checks},"  "))
	file.close()
	quit(0 if ok else 1)
func run() -> void:
	output = OS.get_environment("GODOT_TEST_OUTPUT")
	client = load("res://world_client.gd").new()
	root.add_child(client)
	var access = JSON.parse_string(FileAccess.get_file_as_string(OS.get_environment("WORLD_ACCESS_FILE")))
	await client.connect_world(OS.get_environment("WORLD_URL"),access.sessions.a1.token)
	var mode = OS.get_environment("GODOT_TEST_MODE")
	if mode == "reconnect":
		check(client.pending.is_empty() and client.healthy,"restart resolves original persisted command")
		check(client.observation.self.inventory.wood==1,"lost response has exactly one effect")
	elif mode == "retry":
		check(not client.pending.is_empty(),"404 preserves original request")
		var body: String = client.pending.body
		await client.recover(true)
		check(client.pending.is_empty() and client.observation.self.inventory.wood==1,"original retry commits once")
		check(client.last_receipt.commandId==JSON.parse_string(body).commandId,"original command ID preserved")
	elif mode == "corrupt-journal":
		check(not client.storage_ok and not client.can_act(),"invalid durable record blocks actions")
		await client.send_action({"type":"gather","nodeId":"tree-west-north"})
		check(client.observation.self.inventory.wood==0,"invalid journal cannot mutate")
	else:
		check(client.healthy,"r8 initial observation")
		await client.send_action({"type":"gather","nodeId":"tree-west-north"})
		if mode == "lost":
			check(not client.pending.is_empty() and not client.can_act(),"lost response retains request and blocks new actions")
			await client.connect_world(client.endpoint,access.sessions.a2.token)
			check(client.pending.is_empty() and client.observation.self.actorId=="a2","other identity cannot inherit pending command")
			check(client.observation.self.inventory.wood==0,"other resident remains unchanged")
		elif mode == "wrong-receipt":
			check(not client.pending.is_empty() and not client.can_act(),"wrong node receipt cannot settle original")
			await client.recover()
			check(client.pending.is_empty() and client.observation.self.inventory.wood==1,"lookup resolves original once")
		elif mode == "stale":
			check(client.pending.is_empty() and client.last_receipt.status=="rejected","stale command settled as rejection")
			check(client.last_receipt.error.code=="STALE_STATE" and client.observation.self.inventory.wood==0,"stale command creates no material")
		elif mode == "offline":
			check(client.pending.is_empty() and not client.can_act(),"known receipt retained while observation unavailable")
			check(client.last_receipt.status=="committed","commit remains known during observation outage")
			await client.send_action({"type":"gather","nodeId":"tree-west-north"})
			check(not client.can_act(),"outage blocks further action")
	finish()
