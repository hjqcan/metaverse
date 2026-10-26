-- Historical ITER-0001 schema and populated state. Session hashes use public test-only fixture-a1 / fixture-a2.
BEGIN TRANSACTION;
CREATE TABLE entities(
  entity_id TEXT PRIMARY KEY, world_id TEXT NOT NULL, owner_actor_id TEXT NOT NULL,
  recipe_id TEXT NOT NULL REFERENCES recipes(id), definition_id TEXT NOT NULL,
  definition_version INTEGER NOT NULL, rules_version TEXT NOT NULL,
  x INTEGER NOT NULL CHECK(x BETWEEN 0 AND 7), y INTEGER NOT NULL CHECK(y BETWEEN 0 AND 7),
  embodied_wood INTEGER NOT NULL CHECK(embodied_wood=3), UNIQUE(world_id,x,y),
  FOREIGN KEY(world_id,owner_actor_id) REFERENCES residents(world_id,actor_id), CHECK(NOT(x=3 AND y<=2)));
INSERT INTO "entities" VALUES('e8eb07131188943b4b80aa4b0c8bdaf8b','foundation-01','a1','platform.v1','platform',1,'r1',1,1,3);
CREATE TABLE events(
  seq INTEGER PRIMARY KEY AUTOINCREMENT, world_id TEXT NOT NULL REFERENCES worlds(id),
  state_version INTEGER NOT NULL, event_json TEXT NOT NULL, UNIQUE(world_id,state_version));
INSERT INTO "events" VALUES(1,'foundation-01',0,'{"seq":1,"stateVersion":0,"commandId":null,"actorId":null,"type":"worldSeeded","quantity":12,"source":"ITER-0001 initial allocation"}');
INSERT INTO "events" VALUES(2,'foundation-01',1,'{"seq":2,"stateVersion":1,"commandId":"4bf69676c47d4c599fc6650907176a87","actorId":"a1","type":"claimed","quantity":6}');
INSERT INTO "events" VALUES(3,'foundation-01',2,'{"seq":3,"stateVersion":2,"commandId":"fdf86463d5954a11bcdabf21373df1a5","actorId":"a1","type":"built","entityId":"e8eb07131188943b4b80aa4b0c8bdaf8b","position":[1,1]}');
INSERT INTO "events" VALUES(4,'foundation-01',3,'{"seq":4,"stateVersion":3,"commandId":"382ee2fb60aa408ca879dc9fc763033b","actorId":"a1","type":"moved","position":[2,1]}');
CREATE TABLE receipts(
  world_id TEXT NOT NULL, actor_id TEXT NOT NULL, command_id TEXT NOT NULL,
  request_hash TEXT NOT NULL, status_code INTEGER NOT NULL, result_json TEXT NOT NULL,
  PRIMARY KEY(world_id,actor_id,command_id), FOREIGN KEY(world_id,actor_id) REFERENCES residents(world_id,actor_id));
INSERT INTO "receipts" VALUES('foundation-01','a1','4bf69676c47d4c599fc6650907176a87','79B771C71AF06D0270733CAA38B1A91A4C7035D3D6DF6ABE6C2C3C31D76A072A',200,'{"schemaVersion":1,"rulesVersion":"r1","stateVersion":1,"commandId":"4bf69676c47d4c599fc6650907176a87","identity":{"operatorId":"local-operator","actorId":"a1","sessionId":"s81046aa9b5d24df2b1706ee51a4d45ab"},"eventCursor":2,"error":null,"status":"committed","result":{"action":"claim","quantity":6,"inventoryWood":6,"depotWood":6}}');
INSERT INTO "receipts" VALUES('foundation-01','a1','fdf86463d5954a11bcdabf21373df1a5','54EB607426E5971CFB3CD564F7D0582346A1B613567D7CA4D41C3DF848B64B8D',200,'{"schemaVersion":1,"rulesVersion":"r1","stateVersion":2,"commandId":"fdf86463d5954a11bcdabf21373df1a5","identity":{"operatorId":"local-operator","actorId":"a1","sessionId":"s81046aa9b5d24df2b1706ee51a4d45ab"},"eventCursor":3,"error":null,"status":"committed","result":{"action":"build","entityId":"e8eb07131188943b4b80aa4b0c8bdaf8b","position":[1,1],"inventoryWood":3}}');
INSERT INTO "receipts" VALUES('foundation-01','a1','382ee2fb60aa408ca879dc9fc763033b','C10AD8F1F9976F24FC1F2BA2B3BB23BF717374E019CD355D5D11FE5A83C8BBCF',200,'{"schemaVersion":1,"rulesVersion":"r1","stateVersion":3,"commandId":"382ee2fb60aa408ca879dc9fc763033b","identity":{"operatorId":"local-operator","actorId":"a1","sessionId":"s81046aa9b5d24df2b1706ee51a4d45ab"},"eventCursor":4,"error":null,"status":"committed","result":{"action":"move","position":[2,1]}}');
CREATE TABLE recipes(
  id TEXT PRIMARY KEY, definition_id TEXT NOT NULL, definition_version INTEGER NOT NULL,
  rules_version TEXT NOT NULL, wood_cost INTEGER NOT NULL CHECK(wood_cost>0));
INSERT INTO "recipes" VALUES('platform.v1','platform',1,'r1',3);
CREATE TABLE residents(
  world_id TEXT NOT NULL REFERENCES worlds(id), actor_id TEXT NOT NULL, operator_id TEXT NOT NULL,
  x INTEGER NOT NULL CHECK(x BETWEEN 0 AND 7), y INTEGER NOT NULL CHECK(y BETWEEN 0 AND 7),
  wood INTEGER NOT NULL CHECK(wood BETWEEN 0 AND 12), PRIMARY KEY(world_id,actor_id), CHECK(NOT(x=3 AND y<=2)));
INSERT INTO "residents" VALUES('foundation-01','a1','local-operator',2,1,3);
INSERT INTO "residents" VALUES('foundation-01','a2','local-operator',1,2,0);
CREATE TABLE resource_ledger(
  id INTEGER PRIMARY KEY, world_id TEXT NOT NULL REFERENCES worlds(id), event_seq INTEGER NOT NULL UNIQUE REFERENCES events(seq),
  command_id TEXT, actor_id TEXT, source_account TEXT NOT NULL, destination_account TEXT NOT NULL,
  quantity INTEGER NOT NULL CHECK(quantity BETWEEN 1 AND 12));
INSERT INTO "resource_ledger" VALUES(1,'foundation-01',1,NULL,NULL,'initial-issuance','depot',12);
INSERT INTO "resource_ledger" VALUES(2,'foundation-01',2,'4bf69676c47d4c599fc6650907176a87','a1','depot','inventory:a1',6);
INSERT INTO "resource_ledger" VALUES(3,'foundation-01',3,'fdf86463d5954a11bcdabf21373df1a5','a1','inventory:a1','entity:e8eb07131188943b4b80aa4b0c8bdaf8b',3);
CREATE TABLE sessions(
  session_id TEXT PRIMARY KEY, world_id TEXT NOT NULL, actor_id TEXT NOT NULL, token_hash TEXT NOT NULL UNIQUE,
  expires_at_ms INTEGER NOT NULL, revoked INTEGER NOT NULL CHECK(revoked IN(0,1)),
  FOREIGN KEY(world_id,actor_id) REFERENCES residents(world_id,actor_id));
INSERT INTO "sessions" VALUES('s81046aa9b5d24df2b1706ee51a4d45ab','foundation-01','a1','5BF6FC6243B6E20142CB2ECC349E2DE2C19EA945380FF392CB3040F2595085B3',4102444800000,0);
INSERT INTO "sessions" VALUES('s57d873c0aec247189d161daa268feba6','foundation-01','a2','94AB6A682F13779E9FA892582BA46A858E9E85930F62B797AE179FB319FEB6DD',4102444800000,0);
CREATE TABLE worlds(
  id TEXT PRIMARY KEY CHECK(id='foundation-01'), rules_version TEXT NOT NULL CHECK(rules_version='r1'),
  state_version INTEGER NOT NULL CHECK(typeof(state_version)='integer' AND state_version>=0),
  issued_wood INTEGER NOT NULL CHECK(issued_wood=12), depot_wood INTEGER NOT NULL CHECK(depot_wood BETWEEN 0 AND 12));
INSERT INTO "worlds" VALUES('foundation-01','r1',3,12,6);
CREATE UNIQUE INDEX one_session_per_actor ON sessions(world_id,actor_id) WHERE revoked=0;
CREATE TRIGGER immutable_recipe_update BEFORE UPDATE ON recipes BEGIN SELECT RAISE(ABORT,'immutable recipe'); END;
CREATE TRIGGER immutable_recipe_delete BEFORE DELETE ON recipes BEGIN SELECT RAISE(ABORT,'immutable recipe'); END;
CREATE TRIGGER immutable_event_update BEFORE UPDATE ON events BEGIN SELECT RAISE(ABORT,'immutable event'); END;
CREATE TRIGGER immutable_event_delete BEFORE DELETE ON events BEGIN SELECT RAISE(ABORT,'immutable event'); END;
CREATE TRIGGER immutable_ledger_update BEFORE UPDATE ON resource_ledger BEGIN SELECT RAISE(ABORT,'immutable ledger'); END;
CREATE TRIGGER immutable_ledger_delete BEFORE DELETE ON resource_ledger BEGIN SELECT RAISE(ABORT,'immutable ledger'); END;
CREATE TRIGGER immutable_receipt_update BEFORE UPDATE ON receipts BEGIN SELECT RAISE(ABORT,'immutable receipt'); END;
CREATE TRIGGER immutable_receipt_delete BEFORE DELETE ON receipts BEGIN SELECT RAISE(ABORT,'immutable receipt'); END;
DELETE FROM "sqlite_sequence";
INSERT INTO "sqlite_sequence" VALUES('events',4);
COMMIT;
PRAGMA user_version=1;
