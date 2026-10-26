extends "continuous.gd"

func perform(action: Dictionary) -> void:
	await idle()
	var previous: String = app.client.last_receipt.get("commandId", "")
	await app.client.send_action(action)
	await idle()
	var receipt: Dictionary = app.client.last_receipt
	check(not receipt.is_empty() and receipt.commandId != previous and receipt.status == "committed",
		"actual %s command commits a new receipt" % action.type)

func identity_matches(id: String) -> bool:
	var view: SubViewportContainer = app.world_view
	for actor_id: String in view.actors:
		var actor: Node3D = view.actors[actor_id]
		var label: Label3D = actor.get_node("Nameplate")
		var ring: MeshInstance3D = actor.get_node("IdentityRing")
		if actor_id == id:
			if label.text != "你 · %s" % id or ring.material_override != view.self_ring_material:
				return false
		elif label.text != "居民 %s" % actor_id or ring.material_override != view.resident_ring_material:
			return false
	return true

func author_matches(entity: Dictionary, own: bool) -> bool:
	var entry: Dictionary = app.world_view.structure_labels[entity.entityId]
	var label: Label3D = entry.label
	var author := "你 · %s" % entity.ownerActorId if own else "居民 %s" % entity.ownerActorId
	return entry.owner == entity.ownerActorId and label.text == "平台\n%s 建造" % author

func run() -> void:
	output = OS.get_environment("GODOT_TEST_OUTPUT")
	app = load("res://main.tscn").instantiate()
	root.add_child(app)
	await idle()
	check(app.client.healthy and app.client.identity.actorId == "a1", "authenticated first resident")
	check(identity_matches("a1"), "first identity nameplates and rings match observation")
	var first_entity: Dictionary = app.client.observation.entities[0]
	check(first_entity.ownerActorId == "a1" and author_matches(first_entity, true), "actual first platform credits its builder")
	await create_timer(0.4).timeout
	await screenshot("first-resident")
	var access: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(OS.get_environment("WORLD_ACCESS_FILE")))
	app.client.refresh()
	check(app.client.busy, "switch starts while a read is in flight")
	await app._connect(app.client.endpoint, access.sessions.a2.token)
	await idle()
	check(app.client.identity.actorId == "a2" and identity_matches("a2"), "authenticated switch moves own marker to a2 and removes it from a1")
	check(author_matches(first_entity, false), "switching controller preserves the first platform builder")
	await perform({"type":"gather", "nodeId":"tree-east-south"})
	check(app.client.observation.self.inventory.wood == 1 and app.world_view.effects.get_child_count() == 1, "real gather produces one temporary material caption")
	var actor: Node3D = app.world_view.actors.a2
	var old_visual: Vector3 = actor.position
	app.world_view.set_process(false)
	await perform({"type":"walk", "to":[26,16.4]})
	check(app.world_view.actors.a2 == actor and actor.position == old_visual, "ordinary observation keeps the live visual actor for interpolation")
	check(app.world_view.targets.a2.distance_to(old_visual) > 0.2, "interpolation target follows a committed movement")
	await app._connect(app.client.endpoint, access.sessions.a2.token)
	await idle()
	check(app.world_view.actors.a2 != actor and app.world_view.actors.a2.position == app.world_view.targets.a2, "same-instance reconnect snaps to the authoritative position")
	check(app.world_view.effects.get_child_count() == 0 and app.world_view.gather_effect == 0, "reconnect removes old material captions and arm effects")
	app.world_view.set_process(true)
	# Return within gathering range and create the second resident's own work.
	await create_timer(0.21).timeout
	await perform({"type":"walk", "to":[26,17]})
	for i in 2:
		await perform({"type":"gather", "nodeId":"tree-east-south"})
	await perform({"type":"build", "recipeId":"platform.v1", "at":[26,15.4]})
	check(app.client.observation.self.inventory.wood == 0 and app.client.observation.entities.size() == 2, "second resident spends its own three gathered wood on a platform")
	for entity: Dictionary in app.client.observation.entities:
		check(author_matches(entity, entity.ownerActorId == "a2"), "observed platform attribution stays with %s" % entity.ownerActorId)
	await create_timer(0.9).timeout
	await screenshot("second-resident")
	var original_instance: String = app.client.instance_id
	var replacement: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(OS.get_environment("WORLD_REPLACEMENT_ACCESS")))
	await app._connect(OS.get_environment("WORLD_REPLACEMENT_URL"), replacement.sessions.a2.token)
	await idle()
	check(app.client.instance_id != original_instance and app.client.identity.actorId == "a2", "same resident connects to a different persistent world")
	check(app.world_view.structure_labels.is_empty() and app.client.observation.entities.is_empty(), "replacement world contains no old platform or builder captions")
	check(identity_matches("a2") and app.world_view.actors.a2.position == app.world_view.targets.a2, "replacement identity and position form a fresh visual baseline")
	check(app.world_view.effects.get_child_count() == 0 and not app.world_view.marker.visible and not app.world_view.ghost.visible, "replacement clears temporary effects and action visuals")
	await create_timer(0.4).timeout
	await screenshot("replacement-world")
	finish(0)
