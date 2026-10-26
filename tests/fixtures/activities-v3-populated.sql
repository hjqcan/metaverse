-- Completed ITER-0004 panorama-model r3 world; authentication hashes replaced by public fixture strings.
PRAGMA user_version=3;
BEGIN TRANSACTION;
CREATE TABLE entities(
  entity_id TEXT PRIMARY KEY, world_id TEXT NOT NULL, owner_actor_id TEXT NOT NULL,
  recipe_id TEXT NOT NULL REFERENCES recipes(id), definition_id TEXT NOT NULL,
  definition_version INTEGER NOT NULL, rules_version TEXT NOT NULL,
  x INTEGER NOT NULL CHECK(x BETWEEN 0 AND 7), y INTEGER NOT NULL CHECK(y BETWEEN 0 AND 7),
  embodied_wood INTEGER NOT NULL CHECK(embodied_wood=3), UNIQUE(world_id,x,y),
  FOREIGN KEY(world_id,owner_actor_id) REFERENCES residents(world_id,actor_id), CHECK(NOT(x=3 AND y<=2)));
INSERT INTO "entities" VALUES('ea5c812aa8f9e40649a7b544cd8a4253f','foundation-01','a1','bridge.v1','bridge',1,'r3',4,3,3);
INSERT INTO "entities" VALUES('e8abcc1e1851d4433a80c6b01611bd53a','foundation-01','a1','bridge.v1','bridge',1,'r3',5,3,3);
CREATE TABLE events(
  seq INTEGER PRIMARY KEY AUTOINCREMENT, world_id TEXT NOT NULL REFERENCES worlds(id),
  state_version INTEGER NOT NULL, event_json TEXT NOT NULL, UNIQUE(world_id,state_version));
INSERT INTO "events" VALUES(1,'foundation-01',0,'{"seq":1,"stateVersion":0,"commandId":null,"actorId":null,"type":"worldSeeded","quantity":12,"source":"ITER-0004 initial allocation"}');
INSERT INTO "events" VALUES(2,'foundation-01',1,'{"seq":2,"stateVersion":1,"commandId":"d9d6da96515e4e6ca9a8f68b35dc265a","actorId":"a1","type":"claimed","quantity":6}');
INSERT INTO "events" VALUES(3,'foundation-01',2,'{"seq":3,"stateVersion":2,"commandId":"d715f7b30aa741399a0ab3299dcc29c5","actorId":"a1","type":"moved","position":[2,1]}');
INSERT INTO "events" VALUES(4,'foundation-01',3,'{"seq":4,"stateVersion":3,"commandId":"9f2bb9c2c807411fb619ae2d51fbf208","actorId":"a1","type":"moved","position":[2,2]}');
INSERT INTO "events" VALUES(5,'foundation-01',4,'{"seq":5,"stateVersion":4,"commandId":"8c839b9d3465466ca121a3dbcefec214","actorId":"a1","type":"moved","position":[2,3]}');
INSERT INTO "events" VALUES(6,'foundation-01',5,'{"seq":6,"stateVersion":5,"commandId":"e852a3b0108f4546915a7ba827d7caca","actorId":"a1","type":"moved","position":[3,3]}');
INSERT INTO "events" VALUES(7,'foundation-01',6,'{"seq":7,"stateVersion":6,"commandId":"f66b3e8d6bcd45a4bd201dc6b99ec1d5","actorId":"a1","type":"built","entityId":"ea5c812aa8f9e40649a7b544cd8a4253f","position":[4,3]}');
INSERT INTO "events" VALUES(8,'foundation-01',7,'{"seq":8,"stateVersion":7,"commandId":"ad15a1614b7648b095418a6d782bcc43","actorId":"a1","type":"moved","position":[4,3]}');
INSERT INTO "events" VALUES(9,'foundation-01',8,'{"seq":9,"stateVersion":8,"commandId":"e38dc8b383e142e38cf48f9cf696e5ff","actorId":"a1","type":"built","entityId":"e8abcc1e1851d4433a80c6b01611bd53a","position":[5,3]}');
INSERT INTO "events" VALUES(10,'foundation-01',9,'{"seq":10,"stateVersion":9,"commandId":"d4f5711659b147408ffd081829928f9b","actorId":"a1","type":"moved","position":[5,3]}');
INSERT INTO "events" VALUES(11,'foundation-01',10,'{"seq":11,"stateVersion":10,"commandId":"098e39be87aa4d70aca786f244de4059","actorId":"a1","type":"moved","position":[6,3]}');
INSERT INTO "events" VALUES(12,'foundation-01',11,'{"seq":12,"stateVersion":11,"commandId":"e1566384e4734979a38091ae04575804","actorId":"a1","type":"moved","position":[6,2]}');
INSERT INTO "events" VALUES(13,'foundation-01',12,'{"seq":13,"stateVersion":12,"commandId":"68b8291519c441d29ed60484f6730159","actorId":"a1","type":"moved","position":[6,1]}');
INSERT INTO "events" VALUES(14,'foundation-01',13,'{"seq":14,"stateVersion":13,"commandId":"51a57b766dbf45259ce82cdb20b682b6","actorId":"a1","type":"visited","activityId":"lookout","position":[6,1]}');
INSERT INTO "events" VALUES(15,'foundation-01',14,'{"seq":15,"stateVersion":14,"commandId":"2da105fc6d1f45948a7550fba5d306d4","actorId":"a1","type":"moved","position":[6,2]}');
INSERT INTO "events" VALUES(16,'foundation-01',15,'{"seq":16,"stateVersion":15,"commandId":"1860fb3d59984edcb4f0fc5d63e6fd79","actorId":"a1","type":"moved","position":[6,3]}');
INSERT INTO "events" VALUES(17,'foundation-01',16,'{"seq":17,"stateVersion":16,"commandId":"28f44509f47c47b2bd8646f34c8582b0","actorId":"a1","type":"moved","position":[5,3]}');
INSERT INTO "events" VALUES(18,'foundation-01',17,'{"seq":18,"stateVersion":17,"commandId":"5c400a2444334daeb23d037420145b67","actorId":"a1","type":"moved","position":[4,3]}');
INSERT INTO "events" VALUES(19,'foundation-01',18,'{"seq":19,"stateVersion":18,"commandId":"17b5ec1e823d476a9f8ebf73ad275390","actorId":"a1","type":"moved","position":[3,3]}');
INSERT INTO "events" VALUES(20,'foundation-01',19,'{"seq":20,"stateVersion":19,"commandId":"6034ca4cecdb42acad9c533b87aa4339","actorId":"a1","type":"moved","position":[2,3]}');
INSERT INTO "events" VALUES(21,'foundation-01',20,'{"seq":21,"stateVersion":20,"commandId":"617fbcdfd08244a18aec14876c589cbd","actorId":"a1","type":"moved","position":[1,3]}');
INSERT INTO "events" VALUES(22,'foundation-01',21,'{"seq":22,"stateVersion":21,"commandId":"03187bdd78e0491d9a469cfc890810e5","actorId":"a1","type":"moved","position":[1,2]}');
INSERT INTO "events" VALUES(23,'foundation-01',22,'{"seq":23,"stateVersion":22,"commandId":"1b86f0e65887458a8c734ee8d8dae423","actorId":"a1","type":"moved","position":[1,1]}');
CREATE TABLE receipts(
  world_id TEXT NOT NULL, actor_id TEXT NOT NULL, command_id TEXT NOT NULL,
  request_hash TEXT NOT NULL, status_code INTEGER NOT NULL, result_json TEXT NOT NULL,
  PRIMARY KEY(world_id,actor_id,command_id), FOREIGN KEY(world_id,actor_id) REFERENCES residents(world_id,actor_id));
INSERT INTO "receipts" VALUES('foundation-01','a1','d9d6da96515e4e6ca9a8f68b35dc265a','DC46F434CE48B9E25620923C6404744107D887B87A030033808C1FCFDD6D3BF0',200,'{"schemaVersion":1,"rulesVersion":"r3","stateVersion":1,"commandId":"d9d6da96515e4e6ca9a8f68b35dc265a","identity":{"operatorId":"local-operator","actorId":"a1","sessionId":"s11705e4a4697422eb3a2a7f23e49df00"},"eventCursor":2,"error":null,"status":"committed","result":{"action":"claim","quantity":6,"inventoryWood":6,"depotWood":6}}');
INSERT INTO "receipts" VALUES('foundation-01','a1','d715f7b30aa741399a0ab3299dcc29c5','697BE507E76FFEF757AEE33FFC87A235213CEC380E3E8E74F2B99D592CE89490',200,'{"schemaVersion":1,"rulesVersion":"r3","stateVersion":2,"commandId":"d715f7b30aa741399a0ab3299dcc29c5","identity":{"operatorId":"local-operator","actorId":"a1","sessionId":"s11705e4a4697422eb3a2a7f23e49df00"},"eventCursor":3,"error":null,"status":"committed","result":{"action":"move","position":[2,1]}}');
INSERT INTO "receipts" VALUES('foundation-01','a1','9f2bb9c2c807411fb619ae2d51fbf208','A31C259D417879F8AE1A6059A95ECEC78B68AA48B595D4F97F8B7C8AE3241B1D',200,'{"schemaVersion":1,"rulesVersion":"r3","stateVersion":3,"commandId":"9f2bb9c2c807411fb619ae2d51fbf208","identity":{"operatorId":"local-operator","actorId":"a1","sessionId":"s11705e4a4697422eb3a2a7f23e49df00"},"eventCursor":4,"error":null,"status":"committed","result":{"action":"move","position":[2,2]}}');
INSERT INTO "receipts" VALUES('foundation-01','a1','8c839b9d3465466ca121a3dbcefec214','8C668B38DA7005DFEEA3B9F73A7807FBD8181A34A6BE38040794797BCDF08DEB',200,'{"schemaVersion":1,"rulesVersion":"r3","stateVersion":4,"commandId":"8c839b9d3465466ca121a3dbcefec214","identity":{"operatorId":"local-operator","actorId":"a1","sessionId":"s11705e4a4697422eb3a2a7f23e49df00"},"eventCursor":5,"error":null,"status":"committed","result":{"action":"move","position":[2,3]}}');
INSERT INTO "receipts" VALUES('foundation-01','a1','e852a3b0108f4546915a7ba827d7caca','C0AF38A5E00FE27943AC8BC09D2F0D1828036611A1E7B480F8960BEB5E2ED8F7',200,'{"schemaVersion":1,"rulesVersion":"r3","stateVersion":5,"commandId":"e852a3b0108f4546915a7ba827d7caca","identity":{"operatorId":"local-operator","actorId":"a1","sessionId":"s11705e4a4697422eb3a2a7f23e49df00"},"eventCursor":6,"error":null,"status":"committed","result":{"action":"move","position":[3,3]}}');
INSERT INTO "receipts" VALUES('foundation-01','a1','f66b3e8d6bcd45a4bd201dc6b99ec1d5','6C583237C7E9E1BC1C82C4CA701B480BF0EE9C04915BCDD8D3C57CA19ED39B80',200,'{"schemaVersion":1,"rulesVersion":"r3","stateVersion":6,"commandId":"f66b3e8d6bcd45a4bd201dc6b99ec1d5","identity":{"operatorId":"local-operator","actorId":"a1","sessionId":"s11705e4a4697422eb3a2a7f23e49df00"},"eventCursor":7,"error":null,"status":"committed","result":{"action":"build","entityId":"ea5c812aa8f9e40649a7b544cd8a4253f","position":[4,3],"inventoryWood":3}}');
INSERT INTO "receipts" VALUES('foundation-01','a1','ad15a1614b7648b095418a6d782bcc43','ED62E3EA4F6DA7AB0263E9B3B8C3C11024223D8C3A48D74BBC51352F51E68CA6',200,'{"schemaVersion":1,"rulesVersion":"r3","stateVersion":7,"commandId":"ad15a1614b7648b095418a6d782bcc43","identity":{"operatorId":"local-operator","actorId":"a1","sessionId":"s11705e4a4697422eb3a2a7f23e49df00"},"eventCursor":8,"error":null,"status":"committed","result":{"action":"move","position":[4,3]}}');
INSERT INTO "receipts" VALUES('foundation-01','a1','e38dc8b383e142e38cf48f9cf696e5ff','F900FD01CBAF9FB41CB4A214076795321838FD8335F9CD135557376D73E09BE4',200,'{"schemaVersion":1,"rulesVersion":"r3","stateVersion":8,"commandId":"e38dc8b383e142e38cf48f9cf696e5ff","identity":{"operatorId":"local-operator","actorId":"a1","sessionId":"s11705e4a4697422eb3a2a7f23e49df00"},"eventCursor":9,"error":null,"status":"committed","result":{"action":"build","entityId":"e8abcc1e1851d4433a80c6b01611bd53a","position":[5,3],"inventoryWood":0}}');
INSERT INTO "receipts" VALUES('foundation-01','a1','d4f5711659b147408ffd081829928f9b','80735DD56903F4188CB87B6359A73350FA42ED8347BA5D9B1BC84C67CF5795F0',200,'{"schemaVersion":1,"rulesVersion":"r3","stateVersion":9,"commandId":"d4f5711659b147408ffd081829928f9b","identity":{"operatorId":"local-operator","actorId":"a1","sessionId":"s11705e4a4697422eb3a2a7f23e49df00"},"eventCursor":10,"error":null,"status":"committed","result":{"action":"move","position":[5,3]}}');
INSERT INTO "receipts" VALUES('foundation-01','a1','098e39be87aa4d70aca786f244de4059','103251AEBA8889E1AF827A753EB42A4ABFE23F61EF6FE56A4D7FC453D8A76F0A',200,'{"schemaVersion":1,"rulesVersion":"r3","stateVersion":10,"commandId":"098e39be87aa4d70aca786f244de4059","identity":{"operatorId":"local-operator","actorId":"a1","sessionId":"s11705e4a4697422eb3a2a7f23e49df00"},"eventCursor":11,"error":null,"status":"committed","result":{"action":"move","position":[6,3]}}');
INSERT INTO "receipts" VALUES('foundation-01','a1','e1566384e4734979a38091ae04575804','34AF304DD2FDA0F6E46E821E291A936E710B4546B438BC17DC6F0EF71C7193ED',200,'{"schemaVersion":1,"rulesVersion":"r3","stateVersion":11,"commandId":"e1566384e4734979a38091ae04575804","identity":{"operatorId":"local-operator","actorId":"a1","sessionId":"s11705e4a4697422eb3a2a7f23e49df00"},"eventCursor":12,"error":null,"status":"committed","result":{"action":"move","position":[6,2]}}');
INSERT INTO "receipts" VALUES('foundation-01','a1','68b8291519c441d29ed60484f6730159','33B13C177F0D96415B4F90D06278C4104B46D9B814C5C336EA50891FDD9E2E15',200,'{"schemaVersion":1,"rulesVersion":"r3","stateVersion":12,"commandId":"68b8291519c441d29ed60484f6730159","identity":{"operatorId":"local-operator","actorId":"a1","sessionId":"s11705e4a4697422eb3a2a7f23e49df00"},"eventCursor":13,"error":null,"status":"committed","result":{"action":"move","position":[6,1]}}');
INSERT INTO "receipts" VALUES('foundation-01','a1','51a57b766dbf45259ce82cdb20b682b6','33D134A19015F5E67104E10F9E9F6FEF3AC97BED76F2F9DE1233C57EE3C17D12',200,'{"schemaVersion":1,"rulesVersion":"r3","stateVersion":13,"commandId":"51a57b766dbf45259ce82cdb20b682b6","identity":{"operatorId":"local-operator","actorId":"a1","sessionId":"s11705e4a4697422eb3a2a7f23e49df00"},"eventCursor":14,"error":null,"status":"committed","result":{"action":"visit","activityId":"lookout","position":[6,1],"visitedAtUtc":"2026-10-25T11:32:22.8683022\u002B00:00"}}');
INSERT INTO "receipts" VALUES('foundation-01','a1','2da105fc6d1f45948a7550fba5d306d4','7F9A299945E84E494CDA9919C2A0E6A071F4A03698FD8D78786DF435AB70B699',200,'{"schemaVersion":1,"rulesVersion":"r3","stateVersion":14,"commandId":"2da105fc6d1f45948a7550fba5d306d4","identity":{"operatorId":"local-operator","actorId":"a1","sessionId":"s11705e4a4697422eb3a2a7f23e49df00"},"eventCursor":15,"error":null,"status":"committed","result":{"action":"move","position":[6,2]}}');
INSERT INTO "receipts" VALUES('foundation-01','a1','1860fb3d59984edcb4f0fc5d63e6fd79','4106EE75A5F0A79A1168EB8D448B32C50A74C20778684C65DA4EF1154E3AAE0A',200,'{"schemaVersion":1,"rulesVersion":"r3","stateVersion":15,"commandId":"1860fb3d59984edcb4f0fc5d63e6fd79","identity":{"operatorId":"local-operator","actorId":"a1","sessionId":"s11705e4a4697422eb3a2a7f23e49df00"},"eventCursor":16,"error":null,"status":"committed","result":{"action":"move","position":[6,3]}}');
INSERT INTO "receipts" VALUES('foundation-01','a1','28f44509f47c47b2bd8646f34c8582b0','E98EE54BC12F91FB8461FF85351F5B144F608232712D0AB0D7720EB8F82D3D2D',200,'{"schemaVersion":1,"rulesVersion":"r3","stateVersion":16,"commandId":"28f44509f47c47b2bd8646f34c8582b0","identity":{"operatorId":"local-operator","actorId":"a1","sessionId":"s11705e4a4697422eb3a2a7f23e49df00"},"eventCursor":17,"error":null,"status":"committed","result":{"action":"move","position":[5,3]}}');
INSERT INTO "receipts" VALUES('foundation-01','a1','5c400a2444334daeb23d037420145b67','7700E08C3FCA102FD14AD6492929D223601277BA79F0D1140AC2F63B6EBFBEA6',200,'{"schemaVersion":1,"rulesVersion":"r3","stateVersion":17,"commandId":"5c400a2444334daeb23d037420145b67","identity":{"operatorId":"local-operator","actorId":"a1","sessionId":"s11705e4a4697422eb3a2a7f23e49df00"},"eventCursor":18,"error":null,"status":"committed","result":{"action":"move","position":[4,3]}}');
INSERT INTO "receipts" VALUES('foundation-01','a1','17b5ec1e823d476a9f8ebf73ad275390','C5AF0584F08AA3C5BAE36B98C4534F87CB4D4038FA5DCA770E5ED397BE3D80C6',200,'{"schemaVersion":1,"rulesVersion":"r3","stateVersion":18,"commandId":"17b5ec1e823d476a9f8ebf73ad275390","identity":{"operatorId":"local-operator","actorId":"a1","sessionId":"s11705e4a4697422eb3a2a7f23e49df00"},"eventCursor":19,"error":null,"status":"committed","result":{"action":"move","position":[3,3]}}');
INSERT INTO "receipts" VALUES('foundation-01','a1','6034ca4cecdb42acad9c533b87aa4339','A3FADB5E9C5C2AE3D3BFF34617EE71A1D643E95AD58ACC269690FA82EED7118E',200,'{"schemaVersion":1,"rulesVersion":"r3","stateVersion":19,"commandId":"6034ca4cecdb42acad9c533b87aa4339","identity":{"operatorId":"local-operator","actorId":"a1","sessionId":"s11705e4a4697422eb3a2a7f23e49df00"},"eventCursor":20,"error":null,"status":"committed","result":{"action":"move","position":[2,3]}}');
INSERT INTO "receipts" VALUES('foundation-01','a1','617fbcdfd08244a18aec14876c589cbd','BD2A2FE5C8B21738A17467149DD7E642A64174CB85A8E409C228BEFD2BB26F94',200,'{"schemaVersion":1,"rulesVersion":"r3","stateVersion":20,"commandId":"617fbcdfd08244a18aec14876c589cbd","identity":{"operatorId":"local-operator","actorId":"a1","sessionId":"s11705e4a4697422eb3a2a7f23e49df00"},"eventCursor":21,"error":null,"status":"committed","result":{"action":"move","position":[1,3]}}');
INSERT INTO "receipts" VALUES('foundation-01','a1','03187bdd78e0491d9a469cfc890810e5','E4DB339FD94277898DABABA3E0D9842A455A1F68FFB0608945F82695F153C4E2',200,'{"schemaVersion":1,"rulesVersion":"r3","stateVersion":21,"commandId":"03187bdd78e0491d9a469cfc890810e5","identity":{"operatorId":"local-operator","actorId":"a1","sessionId":"s11705e4a4697422eb3a2a7f23e49df00"},"eventCursor":22,"error":null,"status":"committed","result":{"action":"move","position":[1,2]}}');
INSERT INTO "receipts" VALUES('foundation-01','a1','1b86f0e65887458a8c734ee8d8dae423','E82CB9C0BD931FE628E407C8DB3F1578F6E58517D48722282DD12955BB76AC20',200,'{"schemaVersion":1,"rulesVersion":"r3","stateVersion":22,"commandId":"1b86f0e65887458a8c734ee8d8dae423","identity":{"operatorId":"local-operator","actorId":"a1","sessionId":"s11705e4a4697422eb3a2a7f23e49df00"},"eventCursor":23,"error":null,"status":"committed","result":{"action":"move","position":[1,1]}}');
CREATE TABLE recipes(
  id TEXT PRIMARY KEY, definition_id TEXT NOT NULL, definition_version INTEGER NOT NULL,
  rules_version TEXT NOT NULL, wood_cost INTEGER NOT NULL CHECK(wood_cost>0));
INSERT INTO "recipes" VALUES('platform.v1','platform',1,'r3',3);
INSERT INTO "recipes" VALUES('bridge.v1','bridge',1,'r3',3);
CREATE TABLE residents(
  world_id TEXT NOT NULL REFERENCES worlds(id), actor_id TEXT NOT NULL, operator_id TEXT NOT NULL,
  x INTEGER NOT NULL CHECK(x BETWEEN 0 AND 7), y INTEGER NOT NULL CHECK(y BETWEEN 0 AND 7),
  wood INTEGER NOT NULL CHECK(wood BETWEEN 0 AND 12), PRIMARY KEY(world_id,actor_id), CHECK(NOT(x=3 AND y<=2)));
INSERT INTO "residents" VALUES('foundation-01','a1','local-operator',1,1,0);
INSERT INTO "residents" VALUES('foundation-01','a2','local-operator',1,2,0);
CREATE TABLE resource_ledger(
  id INTEGER PRIMARY KEY, world_id TEXT NOT NULL REFERENCES worlds(id), event_seq INTEGER NOT NULL UNIQUE REFERENCES events(seq),
  command_id TEXT, actor_id TEXT, source_account TEXT NOT NULL, destination_account TEXT NOT NULL,
  quantity INTEGER NOT NULL CHECK(quantity BETWEEN 1 AND 12));
INSERT INTO "resource_ledger" VALUES(1,'foundation-01',1,NULL,NULL,'initial-issuance','depot',12);
INSERT INTO "resource_ledger" VALUES(2,'foundation-01',2,'d9d6da96515e4e6ca9a8f68b35dc265a','a1','depot','inventory:a1',6);
INSERT INTO "resource_ledger" VALUES(3,'foundation-01',7,'f66b3e8d6bcd45a4bd201dc6b99ec1d5','a1','inventory:a1','entity:ea5c812aa8f9e40649a7b544cd8a4253f',3);
INSERT INTO "resource_ledger" VALUES(4,'foundation-01',9,'e38dc8b383e142e38cf48f9cf696e5ff','a1','inventory:a1','entity:e8abcc1e1851d4433a80c6b01611bd53a',3);
CREATE TABLE sessions(
  session_id TEXT PRIMARY KEY, world_id TEXT NOT NULL, actor_id TEXT NOT NULL, token_hash TEXT NOT NULL UNIQUE,
  expires_at_ms INTEGER NOT NULL, revoked INTEGER NOT NULL CHECK(revoked IN(0,1)),
  FOREIGN KEY(world_id,actor_id) REFERENCES residents(world_id,actor_id));
INSERT INTO "sessions" VALUES('s11705e4a4697422eb3a2a7f23e49df00','foundation-01','a1','1DAD737C6D494989E97AA701275047C42AB1320A2F24C4498597674CFFAB0DB5',4102444800000,0);
INSERT INTO "sessions" VALUES('sbd85f403a9774fc1afd3f426f924389f','foundation-01','a2','6DFB6F84C8425B3AEE2231CDC482BC81035FD9877780908443EFB705B9F6D459',4102444800000,0);
CREATE TABLE visits(
  world_id TEXT NOT NULL, actor_id TEXT NOT NULL, command_id TEXT NOT NULL,
  activity_id TEXT NOT NULL, state_version INTEGER NOT NULL,
  visited_at_utc TEXT NOT NULL,
  x INTEGER NOT NULL CHECK(x BETWEEN 0 AND 7), y INTEGER NOT NULL CHECK(y BETWEEN 0 AND 7),
  PRIMARY KEY(world_id,actor_id,command_id), UNIQUE(world_id,state_version),
  FOREIGN KEY(world_id,actor_id) REFERENCES residents(world_id,actor_id),
  FOREIGN KEY(world_id,state_version) REFERENCES events(world_id,state_version) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY(world_id,actor_id,command_id) REFERENCES receipts(world_id,actor_id,command_id) DEFERRABLE INITIALLY DEFERRED);
INSERT INTO "visits" VALUES('foundation-01','a1','51a57b766dbf45259ce82cdb20b682b6','lookout',13,'2026-10-25T11:32:22.8683022+00:00',6,1);
CREATE TABLE worlds(
  id TEXT PRIMARY KEY CHECK(id='foundation-01'), scenario_id TEXT NOT NULL,
  rules_version TEXT NOT NULL,
  state_version INTEGER NOT NULL CHECK(typeof(state_version)='integer' AND state_version>=0),
  issued_wood INTEGER NOT NULL CHECK(issued_wood=12), depot_wood INTEGER NOT NULL CHECK(depot_wood BETWEEN 0 AND 12),
  CHECK(scenario_id='activities-v1' AND rules_version='r3'));
INSERT INTO "worlds" VALUES('foundation-01','activities-v1','r3',22,12,6);
CREATE TRIGGER immutable_scenario BEFORE UPDATE OF scenario_id,rules_version ON worlds
  BEGIN SELECT RAISE(ABORT,'immutable scenario'); END;
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
DELETE FROM "sqlite_sequence";
INSERT INTO "sqlite_sequence" VALUES('events',23);
COMMIT;
