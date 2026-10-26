-- Generated through actual strict r8 HTTP at 8aadf53; no actor-state mode.
-- DLL SHA256 1473453f8e35c7591b926926c7765bfbd239c1fcceaa356bebb9b65ada00d90f.
-- Only session hashes/expiry replaced with public fixture-r2-a1/a2 test credentials.
PRAGMA user_version=8;
BEGIN TRANSACTION;
CREATE TABLE entities(
  entity_id TEXT PRIMARY KEY, world_id TEXT NOT NULL, owner_actor_id TEXT NOT NULL,
  recipe_id TEXT NOT NULL REFERENCES recipes(id), definition_id TEXT NOT NULL,
  definition_version INTEGER NOT NULL, rules_version TEXT NOT NULL,
  x REAL NOT NULL CHECK(x BETWEEN 0 AND 32), y REAL NOT NULL CHECK(y BETWEEN 0 AND 24),
  embodied_wood INTEGER NOT NULL CHECK(embodied_wood IN(3,6)), UNIQUE(world_id,x,y),
  FOREIGN KEY(world_id,owner_actor_id) REFERENCES residents(world_id,actor_id));
CREATE TABLE events(
  seq INTEGER PRIMARY KEY AUTOINCREMENT, world_id TEXT NOT NULL REFERENCES worlds(id),
  state_version INTEGER NOT NULL, event_json TEXT NOT NULL, UNIQUE(world_id,state_version));
INSERT INTO "events" VALUES(1,'foundation-01',0,'{"seq":1,"stateVersion":0,"commandId":null,"actorId":null,"type":"worldSeeded","quantity":12,"source":"ITER-0014 initial wild wood"}');
INSERT INTO "events" VALUES(2,'foundation-01',1,'{"seq":2,"stateVersion":1,"commandId":"legacy_strict_gather","actorId":"a1","type":"gathered","nodeId":"tree-west-north","quantity":1,"position":[6.2,7.8],"remainingWood":2}');
CREATE TABLE receipts(
  world_id TEXT NOT NULL, actor_id TEXT NOT NULL, command_id TEXT NOT NULL,
  request_hash TEXT NOT NULL, status_code INTEGER NOT NULL, result_json TEXT NOT NULL,
  PRIMARY KEY(world_id,actor_id,command_id), FOREIGN KEY(world_id,actor_id) REFERENCES residents(world_id,actor_id));
INSERT INTO "receipts" VALUES('foundation-01','a1','legacy_strict_gather','FAF019C2BCE2584EDE2D8F82B1A9069B0FAE04429C19719C266A47BB37A72F04',200,'{"schemaVersion":1,"rulesVersion":"r8","stateVersion":1,"commandId":"legacy_strict_gather","identity":{"operatorId":"local-operator","actorId":"a1","sessionId":"s2e0179039f264771b264203d67998ad3"},"eventCursor":2,"error":null,"status":"committed","result":{"action":"gather","nodeId":"tree-west-north","quantity":1,"position":[6.2,7.8],"remainingWood":2,"inventoryWood":1}}');
CREATE TABLE recipes(
  id TEXT PRIMARY KEY, definition_id TEXT NOT NULL, definition_version INTEGER NOT NULL,
  rules_version TEXT NOT NULL, wood_cost INTEGER NOT NULL CHECK(wood_cost>0));
INSERT INTO "recipes" VALUES('platform.v1','platform',1,'r8',3);
INSERT INTO "recipes" VALUES('bridge.v1','bridge',1,'r8',6);
CREATE TABLE residents(
  world_id TEXT NOT NULL REFERENCES worlds(id), actor_id TEXT NOT NULL, operator_id TEXT NOT NULL,
  x REAL NOT NULL CHECK(x BETWEEN 0 AND 32), y REAL NOT NULL CHECK(y BETWEEN 0 AND 24),
  wood INTEGER NOT NULL CHECK(wood BETWEEN 0 AND 12), last_walk_ms INTEGER NOT NULL DEFAULT 0, walk_credit REAL NOT NULL DEFAULT 0.6, PRIMARY KEY(world_id,actor_id));
INSERT INTO "residents" VALUES('foundation-01','a1','local-operator',5.0,7.0,1,0,0.6);
INSERT INTO "residents" VALUES('foundation-01','a2','local-operator',26.0,17.0,0,0,0.6);
CREATE TABLE resource_ledger(
  id INTEGER PRIMARY KEY, world_id TEXT NOT NULL REFERENCES worlds(id), event_seq INTEGER NOT NULL UNIQUE REFERENCES events(seq),
  command_id TEXT, actor_id TEXT, source_account TEXT NOT NULL, destination_account TEXT NOT NULL,
  quantity INTEGER NOT NULL CHECK(quantity BETWEEN 1 AND 12));
INSERT INTO "resource_ledger" VALUES(1,'foundation-01',1,NULL,NULL,'initial-issuance','wild-wood',12);
INSERT INTO "resource_ledger" VALUES(2,'foundation-01',2,'legacy_strict_gather','a1','wild-wood','inventory:a1',1);
CREATE TABLE resource_nodes(
  world_id TEXT NOT NULL REFERENCES worlds(id), node_id TEXT NOT NULL, kind TEXT NOT NULL CHECK(kind='tree'),
  x REAL NOT NULL CHECK(x BETWEEN 0 AND 32), y REAL NOT NULL CHECK(y BETWEEN 0 AND 24),
  initial_wood INTEGER NOT NULL CHECK(initial_wood=3),
  remaining_wood INTEGER NOT NULL CHECK(typeof(remaining_wood)='integer' AND remaining_wood BETWEEN 0 AND initial_wood),
  PRIMARY KEY(world_id,node_id), UNIQUE(world_id,x,y));
INSERT INTO "resource_nodes" VALUES('foundation-01','tree-west-north','tree',6.2,7.8,3,2);
INSERT INTO "resource_nodes" VALUES('foundation-01','tree-west-south','tree',9.2,16.3,3,3);
INSERT INTO "resource_nodes" VALUES('foundation-01','tree-east-north','tree',25.4,5.8,3,3);
INSERT INTO "resource_nodes" VALUES('foundation-01','tree-east-south','tree',25.7,18.2,3,3);
CREATE TABLE sessions(
  session_id TEXT PRIMARY KEY, world_id TEXT NOT NULL, actor_id TEXT NOT NULL, token_hash TEXT NOT NULL UNIQUE,
  expires_at_ms INTEGER NOT NULL, revoked INTEGER NOT NULL CHECK(revoked IN(0,1)),
  FOREIGN KEY(world_id,actor_id) REFERENCES residents(world_id,actor_id));
INSERT INTO "sessions" VALUES('s2e0179039f264771b264203d67998ad3','foundation-01','a1','1435284AFE1DB87D7129FDF2DDC9FC7A9C851109834C8526ED698A56E213DDE4',2524608000000,0);
INSERT INTO "sessions" VALUES('s09ec389d8d6c4507a20c0b11b0a48215','foundation-01','a2','70617E7EE16D6EF2C48A94DF93FA6E951CE1221FF291DDEEDC204B7417818ED5',2524608000000,0);
CREATE TABLE visits(
  world_id TEXT NOT NULL, actor_id TEXT NOT NULL, command_id TEXT NOT NULL,
  activity_id TEXT NOT NULL, state_version INTEGER NOT NULL,
  visited_at_utc TEXT NOT NULL,
  x REAL NOT NULL CHECK(x BETWEEN 0 AND 32), y REAL NOT NULL CHECK(y BETWEEN 0 AND 24),
  PRIMARY KEY(world_id,actor_id,command_id), UNIQUE(world_id,state_version),
  FOREIGN KEY(world_id,actor_id) REFERENCES residents(world_id,actor_id),
  FOREIGN KEY(world_id,state_version) REFERENCES events(world_id,state_version) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY(world_id,actor_id,command_id) REFERENCES receipts(world_id,actor_id,command_id) DEFERRABLE INITIALLY DEFERRED);
CREATE TABLE world_instance(
  singleton INTEGER PRIMARY KEY CHECK(singleton=1),
  instance_id TEXT NOT NULL UNIQUE,
  binding_version INTEGER NOT NULL CHECK(binding_version=1)
);
INSERT INTO "world_instance" VALUES(1,'w_c705c97492234c78be0ee93788136ab9',1);
CREATE TABLE worlds(
  id TEXT PRIMARY KEY CHECK(id='foundation-01'), scenario_id TEXT NOT NULL,
  rules_version TEXT NOT NULL,
  state_version INTEGER NOT NULL CHECK(typeof(state_version)='integer' AND state_version>=0),
  issued_wood INTEGER NOT NULL CHECK(issued_wood=12), depot_wood INTEGER NOT NULL CHECK(depot_wood=0),
  CHECK(scenario_id='wilderness-continuous-v1' AND rules_version='r8'));
INSERT INTO "worlds" VALUES('foundation-01','wilderness-continuous-v1','r8',1,12,0);
CREATE TRIGGER immutable_scenario BEFORE UPDATE OF scenario_id,rules_version ON worlds
  BEGIN SELECT RAISE(ABORT,'immutable scenario'); END;
CREATE TRIGGER immutable_resource_definition BEFORE UPDATE OF world_id,node_id,kind,x,y,initial_wood ON resource_nodes
  BEGIN SELECT RAISE(ABORT,'immutable resource definition'); END;
CREATE TRIGGER immutable_resource_delete BEFORE DELETE ON resource_nodes
  BEGIN SELECT RAISE(ABORT,'immutable resource definition'); END;
CREATE UNIQUE INDEX one_session_per_actor ON sessions(world_id,actor_id) WHERE revoked=0;
CREATE TRIGGER immutable_recipe_update BEFORE UPDATE ON recipes BEGIN SELECT RAISE(ABORT,'immutable recipe'); END;
CREATE TRIGGER immutable_recipe_delete BEFORE DELETE ON recipes BEGIN SELECT RAISE(ABORT,'immutable recipe'); END;
CREATE TRIGGER immutable_event_update BEFORE UPDATE ON events BEGIN SELECT RAISE(ABORT,'immutable event'); END;
CREATE TRIGGER immutable_event_delete BEFORE DELETE ON events BEGIN SELECT RAISE(ABORT,'immutable event'); END;
CREATE TRIGGER immutable_ledger_update BEFORE UPDATE ON resource_ledger BEGIN SELECT RAISE(ABORT,'immutable ledger'); END;
CREATE TRIGGER immutable_ledger_delete BEFORE DELETE ON resource_ledger BEGIN SELECT RAISE(ABORT,'immutable ledger'); END;
CREATE TRIGGER immutable_receipt_update BEFORE UPDATE ON receipts BEGIN SELECT RAISE(ABORT,'immutable receipt'); END;
CREATE TRIGGER immutable_receipt_delete BEFORE DELETE ON receipts BEGIN SELECT RAISE(ABORT,'immutable receipt'); END;
CREATE INDEX recent_visits ON visits(world_id,actor_id,state_version);
CREATE TRIGGER immutable_visit_update BEFORE UPDATE ON visits BEGIN SELECT RAISE(ABORT,'immutable visit'); END;
CREATE TRIGGER immutable_visit_delete BEFORE DELETE ON visits BEGIN SELECT RAISE(ABORT,'immutable visit'); END;
CREATE TRIGGER immutable_world_instance_update BEFORE UPDATE ON world_instance
  BEGIN SELECT RAISE(ABORT,'immutable world instance'); END;
CREATE TRIGGER immutable_world_instance_delete BEFORE DELETE ON world_instance
  BEGIN SELECT RAISE(ABORT,'immutable world instance'); END;
DELETE FROM "sqlite_sequence";
INSERT INTO "sqlite_sequence" VALUES('events',2);
COMMIT;
