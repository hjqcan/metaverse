-- Exported from completed ITER-0006 actual two-resident mosaic world; session hashes and expiry only sanitized.
PRAGMA user_version=5;
BEGIN TRANSACTION;
CREATE TABLE entities(
  entity_id TEXT PRIMARY KEY, world_id TEXT NOT NULL, owner_actor_id TEXT NOT NULL,
  recipe_id TEXT NOT NULL REFERENCES recipes(id), definition_id TEXT NOT NULL,
  definition_version INTEGER NOT NULL, rules_version TEXT NOT NULL,
  x INTEGER NOT NULL CHECK(x BETWEEN 0 AND 7), y INTEGER NOT NULL CHECK(y BETWEEN 0 AND 7),
  embodied_wood INTEGER NOT NULL CHECK(embodied_wood=3), UNIQUE(world_id,x,y),
  FOREIGN KEY(world_id,owner_actor_id) REFERENCES residents(world_id,actor_id), CHECK(NOT(x=3 AND y<=2)));
CREATE TABLE events(
  seq INTEGER PRIMARY KEY AUTOINCREMENT, world_id TEXT NOT NULL REFERENCES worlds(id),
  state_version INTEGER NOT NULL, event_json TEXT NOT NULL, UNIQUE(world_id,state_version));
INSERT INTO "events" VALUES(1,'foundation-01',0,'{"seq":1,"stateVersion":0,"commandId":null,"actorId":null,"type":"worldSeeded","quantity":12,"source":"ITER-0006 initial allocation"}');
INSERT INTO "events" VALUES(2,'foundation-01',1,'{"seq":2,"stateVersion":1,"commandId":"05ad338493c340469b1a212b9f3b2a94","actorId":"a1","type":"moved","position":[1,2]}');
INSERT INTO "events" VALUES(3,'foundation-01',2,'{"seq":3,"stateVersion":2,"commandId":"77cd05faf3ce4cbf8085c91e6d5ef2ca","actorId":"a1","type":"moved","position":[1,3]}');
INSERT INTO "events" VALUES(4,'foundation-01',3,'{"seq":4,"stateVersion":3,"commandId":"22a683385511414584642f51c99d772d","actorId":"a1","type":"moved","position":[1,4]}');
INSERT INTO "events" VALUES(5,'foundation-01',4,'{"seq":5,"stateVersion":4,"commandId":"c915f60990dd4d499c86a5cdb264f708","actorId":"a1","type":"moved","position":[1,5]}');
INSERT INTO "events" VALUES(6,'foundation-01',5,'{"seq":6,"stateVersion":5,"commandId":"8c3ee5b471e143c0bf71dff90e8ba71c","actorId":"a1","type":"moved","position":[1,6]}');
INSERT INTO "events" VALUES(7,'foundation-01',6,'{"seq":7,"stateVersion":6,"commandId":"de4fe5c6587e4741a72df4f72e114fba","actorId":"a1","type":"visited","activityId":"garden","position":[1,6]}');
INSERT INTO "events" VALUES(8,'foundation-01',7,'{"seq":8,"type":"mosaic_painted","actorId":"a1","activityId":"garden","authorActorId":"a1","commandId":"e86f2642363e4ca3be25c801e353b35f","visitCommandId":"de4fe5c6587e4741a72df4f72e114fba","baseRevision":0,"revision":1,"patch":[{"x":0,"y":1,"color":"river"},{"x":1,"y":1,"color":"river"},{"x":1,"y":2,"color":"river"},{"x":2,"y":2,"color":"river"},{"x":3,"y":2,"color":"river"},{"x":3,"y":3,"color":"river"},{"x":4,"y":3,"color":"river"}],"stateVersion":7,"paintedAtUtc":"2026-10-25T14:29:03.0188847\u002B00:00","position":[1,6]}');
INSERT INTO "events" VALUES(9,'foundation-01',8,'{"seq":9,"stateVersion":8,"commandId":"f903b9ce309947baa87b38318c28a949","actorId":"a1","type":"moved","position":[1,5]}');
INSERT INTO "events" VALUES(10,'foundation-01',9,'{"seq":10,"stateVersion":9,"commandId":"9632672c420646f6b63ea8ad565b92ca","actorId":"a1","type":"moved","position":[1,4]}');
INSERT INTO "events" VALUES(11,'foundation-01',10,'{"seq":11,"stateVersion":10,"commandId":"6dec48e726704e1ab217e1b4ae7a06b4","actorId":"a1","type":"moved","position":[1,3]}');
INSERT INTO "events" VALUES(12,'foundation-01',11,'{"seq":12,"stateVersion":11,"commandId":"ee90fd86bc7347b799e795023cc74333","actorId":"a1","type":"moved","position":[1,2]}');
INSERT INTO "events" VALUES(13,'foundation-01',12,'{"seq":13,"stateVersion":12,"commandId":"f1a72fd80e474b8ab151935387f26c1e","actorId":"a1","type":"moved","position":[1,1]}');
INSERT INTO "events" VALUES(14,'foundation-01',13,'{"seq":14,"stateVersion":13,"commandId":"7af268fdb1c648708672f021e409fc5f","actorId":"a2","type":"moved","position":[1,3]}');
INSERT INTO "events" VALUES(15,'foundation-01',14,'{"seq":15,"stateVersion":14,"commandId":"e1cd45fa7dcf41a0af4d79027b55b17d","actorId":"a2","type":"moved","position":[1,4]}');
INSERT INTO "events" VALUES(16,'foundation-01',15,'{"seq":16,"stateVersion":15,"commandId":"8061e6386550427f8231ebfcb2335771","actorId":"a2","type":"moved","position":[1,5]}');
INSERT INTO "events" VALUES(17,'foundation-01',16,'{"seq":17,"stateVersion":16,"commandId":"34ab8830ac334716b983416a47e3c804","actorId":"a2","type":"moved","position":[1,6]}');
INSERT INTO "events" VALUES(18,'foundation-01',17,'{"seq":18,"stateVersion":17,"commandId":"c12d6617cb5e4ae3aa5b3d48f7b5efe9","actorId":"a2","type":"visited","activityId":"garden","position":[1,6]}');
INSERT INTO "events" VALUES(19,'foundation-01',18,'{"seq":19,"type":"mosaic_painted","actorId":"a2","activityId":"garden","authorActorId":"a2","commandId":"49bd14213c4245a3a1034dd704e6723c","visitCommandId":"c12d6617cb5e4ae3aa5b3d48f7b5efe9","baseRevision":1,"revision":2,"patch":[{"x":0,"y":0,"color":"leaf"},{"x":1,"y":0,"color":"rose"},{"x":2,"y":1,"color":"leaf"},{"x":3,"y":1,"color":"rose"},{"x":0,"y":2,"color":"leaf"},{"x":1,"y":3,"color":"leaf"},{"x":2,"y":3,"color":"leaf"},{"x":4,"y":4,"color":"leaf"}],"stateVersion":18,"paintedAtUtc":"2026-10-25T14:29:15.0483553\u002B00:00","position":[1,6]}');
INSERT INTO "events" VALUES(20,'foundation-01',19,'{"seq":20,"stateVersion":19,"commandId":"9c8fdf4c9ba94989a4dea6d9c4b0e182","actorId":"a2","type":"moved","position":[1,5]}');
INSERT INTO "events" VALUES(21,'foundation-01',20,'{"seq":21,"stateVersion":20,"commandId":"6430ec5253864203b3c7cb2ba417ec0b","actorId":"a2","type":"moved","position":[1,4]}');
INSERT INTO "events" VALUES(22,'foundation-01',21,'{"seq":22,"stateVersion":21,"commandId":"44d3ed83defa4ad3a316212d4f1bf54b","actorId":"a2","type":"moved","position":[1,3]}');
INSERT INTO "events" VALUES(23,'foundation-01',22,'{"seq":23,"stateVersion":22,"commandId":"3a475ace10a047cfae97cf6bddcce3b8","actorId":"a2","type":"moved","position":[1,2]}');
CREATE TABLE mosaic_cells(
  world_id TEXT NOT NULL, activity_id TEXT NOT NULL CHECK(activity_id='garden'),
  x INTEGER NOT NULL CHECK(typeof(x)='integer' AND x BETWEEN 0 AND 4),
  y INTEGER NOT NULL CHECK(typeof(y)='integer' AND y BETWEEN 0 AND 4),
  color TEXT NOT NULL CHECK(color IN('blank','leaf','river','sun','rose','ink')),
  author_actor_id TEXT, command_id TEXT, state_version INTEGER,
  PRIMARY KEY(world_id,activity_id,x,y),
  CHECK((color='blank' AND author_actor_id IS NULL AND command_id IS NULL AND state_version IS NULL) OR
        (author_actor_id IS NOT NULL AND command_id IS NOT NULL AND state_version IS NOT NULL)),
  FOREIGN KEY(world_id,activity_id) REFERENCES mosaics(world_id,activity_id),
  FOREIGN KEY(world_id,author_actor_id,command_id) REFERENCES mosaic_edits(world_id,author_actor_id,command_id),
  FOREIGN KEY(world_id,state_version) REFERENCES events(world_id,state_version) DEFERRABLE INITIALLY DEFERRED);
INSERT INTO "mosaic_cells" VALUES('foundation-01','garden',0,0,'leaf','a2','49bd14213c4245a3a1034dd704e6723c',18);
INSERT INTO "mosaic_cells" VALUES('foundation-01','garden',1,0,'rose','a2','49bd14213c4245a3a1034dd704e6723c',18);
INSERT INTO "mosaic_cells" VALUES('foundation-01','garden',2,0,'blank',NULL,NULL,NULL);
INSERT INTO "mosaic_cells" VALUES('foundation-01','garden',3,0,'blank',NULL,NULL,NULL);
INSERT INTO "mosaic_cells" VALUES('foundation-01','garden',4,0,'blank',NULL,NULL,NULL);
INSERT INTO "mosaic_cells" VALUES('foundation-01','garden',0,1,'river','a1','e86f2642363e4ca3be25c801e353b35f',7);
INSERT INTO "mosaic_cells" VALUES('foundation-01','garden',1,1,'river','a1','e86f2642363e4ca3be25c801e353b35f',7);
INSERT INTO "mosaic_cells" VALUES('foundation-01','garden',2,1,'leaf','a2','49bd14213c4245a3a1034dd704e6723c',18);
INSERT INTO "mosaic_cells" VALUES('foundation-01','garden',3,1,'rose','a2','49bd14213c4245a3a1034dd704e6723c',18);
INSERT INTO "mosaic_cells" VALUES('foundation-01','garden',4,1,'blank',NULL,NULL,NULL);
INSERT INTO "mosaic_cells" VALUES('foundation-01','garden',0,2,'leaf','a2','49bd14213c4245a3a1034dd704e6723c',18);
INSERT INTO "mosaic_cells" VALUES('foundation-01','garden',1,2,'river','a1','e86f2642363e4ca3be25c801e353b35f',7);
INSERT INTO "mosaic_cells" VALUES('foundation-01','garden',2,2,'river','a1','e86f2642363e4ca3be25c801e353b35f',7);
INSERT INTO "mosaic_cells" VALUES('foundation-01','garden',3,2,'river','a1','e86f2642363e4ca3be25c801e353b35f',7);
INSERT INTO "mosaic_cells" VALUES('foundation-01','garden',4,2,'blank',NULL,NULL,NULL);
INSERT INTO "mosaic_cells" VALUES('foundation-01','garden',0,3,'blank',NULL,NULL,NULL);
INSERT INTO "mosaic_cells" VALUES('foundation-01','garden',1,3,'leaf','a2','49bd14213c4245a3a1034dd704e6723c',18);
INSERT INTO "mosaic_cells" VALUES('foundation-01','garden',2,3,'leaf','a2','49bd14213c4245a3a1034dd704e6723c',18);
INSERT INTO "mosaic_cells" VALUES('foundation-01','garden',3,3,'river','a1','e86f2642363e4ca3be25c801e353b35f',7);
INSERT INTO "mosaic_cells" VALUES('foundation-01','garden',4,3,'river','a1','e86f2642363e4ca3be25c801e353b35f',7);
INSERT INTO "mosaic_cells" VALUES('foundation-01','garden',0,4,'blank',NULL,NULL,NULL);
INSERT INTO "mosaic_cells" VALUES('foundation-01','garden',1,4,'blank',NULL,NULL,NULL);
INSERT INTO "mosaic_cells" VALUES('foundation-01','garden',2,4,'blank',NULL,NULL,NULL);
INSERT INTO "mosaic_cells" VALUES('foundation-01','garden',3,4,'blank',NULL,NULL,NULL);
INSERT INTO "mosaic_cells" VALUES('foundation-01','garden',4,4,'leaf','a2','49bd14213c4245a3a1034dd704e6723c',18);
CREATE TABLE mosaic_edits(
  world_id TEXT NOT NULL, activity_id TEXT NOT NULL CHECK(activity_id='garden'),
  author_actor_id TEXT NOT NULL, command_id TEXT NOT NULL, visit_command_id TEXT NOT NULL,
  base_revision INTEGER NOT NULL CHECK(typeof(base_revision)='integer' AND base_revision>=0),
  revision INTEGER NOT NULL CHECK(typeof(revision)='integer' AND revision=base_revision+1),
  patch_json TEXT NOT NULL CHECK(json_valid(patch_json) AND json_type(patch_json)='array' AND json_array_length(patch_json) BETWEEN 1 AND 8),
  state_version INTEGER NOT NULL, painted_at_utc TEXT NOT NULL,
  x INTEGER NOT NULL CHECK(x=1), y INTEGER NOT NULL CHECK(y=6),
  PRIMARY KEY(world_id,author_actor_id,command_id), UNIQUE(world_id,state_version),
  UNIQUE(world_id,activity_id,revision), UNIQUE(world_id,author_actor_id,visit_command_id),
  FOREIGN KEY(world_id,activity_id) REFERENCES mosaics(world_id,activity_id),
  FOREIGN KEY(world_id,author_actor_id,visit_command_id) REFERENCES visits(world_id,actor_id,command_id),
  FOREIGN KEY(world_id,state_version) REFERENCES events(world_id,state_version) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY(world_id,author_actor_id,command_id) REFERENCES receipts(world_id,actor_id,command_id) DEFERRABLE INITIALLY DEFERRED);
INSERT INTO "mosaic_edits" VALUES('foundation-01','garden','a1','e86f2642363e4ca3be25c801e353b35f','de4fe5c6587e4741a72df4f72e114fba',0,1,'[{"x":0,"y":1,"color":"river"},{"x":1,"y":1,"color":"river"},{"x":1,"y":2,"color":"river"},{"x":2,"y":2,"color":"river"},{"x":3,"y":2,"color":"river"},{"x":3,"y":3,"color":"river"},{"x":4,"y":3,"color":"river"}]',7,'2026-10-25T14:29:03.0188847+00:00',1,6);
INSERT INTO "mosaic_edits" VALUES('foundation-01','garden','a2','49bd14213c4245a3a1034dd704e6723c','c12d6617cb5e4ae3aa5b3d48f7b5efe9',1,2,'[{"x":0,"y":0,"color":"leaf"},{"x":1,"y":0,"color":"rose"},{"x":2,"y":1,"color":"leaf"},{"x":3,"y":1,"color":"rose"},{"x":0,"y":2,"color":"leaf"},{"x":1,"y":3,"color":"leaf"},{"x":2,"y":3,"color":"leaf"},{"x":4,"y":4,"color":"leaf"}]',18,'2026-10-25T14:29:15.0483553+00:00',1,6);
CREATE TABLE mosaics(
  world_id TEXT NOT NULL REFERENCES worlds(id), activity_id TEXT NOT NULL CHECK(activity_id='garden'),
  revision INTEGER NOT NULL CHECK(typeof(revision)='integer' AND revision>=0),
  PRIMARY KEY(world_id,activity_id));
INSERT INTO "mosaics" VALUES('foundation-01','garden',2);
CREATE TABLE postcards(
  world_id TEXT NOT NULL, author_actor_id TEXT NOT NULL, command_id TEXT NOT NULL,
  visit_command_id TEXT NOT NULL, activity_id TEXT NOT NULL, text TEXT NOT NULL,
  state_version INTEGER NOT NULL, shared_at_utc TEXT NOT NULL,
  x INTEGER NOT NULL CHECK(x BETWEEN 0 AND 7), y INTEGER NOT NULL CHECK(y BETWEEN 0 AND 7),
  PRIMARY KEY(world_id,author_actor_id,command_id), UNIQUE(world_id,state_version),
  UNIQUE(world_id,author_actor_id,visit_command_id),
  FOREIGN KEY(world_id,author_actor_id,visit_command_id) REFERENCES visits(world_id,actor_id,command_id),
  FOREIGN KEY(world_id,state_version) REFERENCES events(world_id,state_version) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY(world_id,author_actor_id,command_id) REFERENCES receipts(world_id,actor_id,command_id) DEFERRABLE INITIALLY DEFERRED);
CREATE TABLE receipts(
  world_id TEXT NOT NULL, actor_id TEXT NOT NULL, command_id TEXT NOT NULL,
  request_hash TEXT NOT NULL, status_code INTEGER NOT NULL, result_json TEXT NOT NULL,
  PRIMARY KEY(world_id,actor_id,command_id), FOREIGN KEY(world_id,actor_id) REFERENCES residents(world_id,actor_id));
INSERT INTO "receipts" VALUES('foundation-01','a1','05ad338493c340469b1a212b9f3b2a94','C575EE3576EAEE46BB8DFDBDB96B13DA4A016FA6DED24A6C4A527AD4A5133206',200,'{"schemaVersion":1,"rulesVersion":"r5","stateVersion":1,"commandId":"05ad338493c340469b1a212b9f3b2a94","identity":{"operatorId":"local-operator","actorId":"a1","sessionId":"s6c86d0e53c3f4218a2875c0d1d404596"},"eventCursor":2,"error":null,"status":"committed","result":{"action":"move","position":[1,2]}}');
INSERT INTO "receipts" VALUES('foundation-01','a1','77cd05faf3ce4cbf8085c91e6d5ef2ca','92A50B5D1D5CCD4C598024B0BD760B057AABD977BDB5E97709B27FA7603F2738',200,'{"schemaVersion":1,"rulesVersion":"r5","stateVersion":2,"commandId":"77cd05faf3ce4cbf8085c91e6d5ef2ca","identity":{"operatorId":"local-operator","actorId":"a1","sessionId":"s6c86d0e53c3f4218a2875c0d1d404596"},"eventCursor":3,"error":null,"status":"committed","result":{"action":"move","position":[1,3]}}');
INSERT INTO "receipts" VALUES('foundation-01','a1','22a683385511414584642f51c99d772d','81CE613936B017D39AC59659D9681B97ED4176917EFE86EE546CC52BE5A9072A',200,'{"schemaVersion":1,"rulesVersion":"r5","stateVersion":3,"commandId":"22a683385511414584642f51c99d772d","identity":{"operatorId":"local-operator","actorId":"a1","sessionId":"s6c86d0e53c3f4218a2875c0d1d404596"},"eventCursor":4,"error":null,"status":"committed","result":{"action":"move","position":[1,4]}}');
INSERT INTO "receipts" VALUES('foundation-01','a1','c915f60990dd4d499c86a5cdb264f708','93EFBC903BDE81727935054C28EF2D492F7F913DD16160792AD0D4EBE7A0CF13',200,'{"schemaVersion":1,"rulesVersion":"r5","stateVersion":4,"commandId":"c915f60990dd4d499c86a5cdb264f708","identity":{"operatorId":"local-operator","actorId":"a1","sessionId":"s6c86d0e53c3f4218a2875c0d1d404596"},"eventCursor":5,"error":null,"status":"committed","result":{"action":"move","position":[1,5]}}');
INSERT INTO "receipts" VALUES('foundation-01','a1','8c3ee5b471e143c0bf71dff90e8ba71c','F41A7A6A86D20E67BE0F86AEDDE17C9F13930F80C704E9E39F3DA0E073002C7F',200,'{"schemaVersion":1,"rulesVersion":"r5","stateVersion":5,"commandId":"8c3ee5b471e143c0bf71dff90e8ba71c","identity":{"operatorId":"local-operator","actorId":"a1","sessionId":"s6c86d0e53c3f4218a2875c0d1d404596"},"eventCursor":6,"error":null,"status":"committed","result":{"action":"move","position":[1,6]}}');
INSERT INTO "receipts" VALUES('foundation-01','a1','de4fe5c6587e4741a72df4f72e114fba','FBAA4C78A530F031E501E783470EC8B7E0528C176C269C9CF4ECA37BA33C247A',200,'{"schemaVersion":1,"rulesVersion":"r5","stateVersion":6,"commandId":"de4fe5c6587e4741a72df4f72e114fba","identity":{"operatorId":"local-operator","actorId":"a1","sessionId":"s6c86d0e53c3f4218a2875c0d1d404596"},"eventCursor":7,"error":null,"status":"committed","result":{"action":"visit","activityId":"garden","position":[1,6],"visitedAtUtc":"2026-10-25T14:29:03.0084915\u002B00:00"}}');
INSERT INTO "receipts" VALUES('foundation-01','a1','e86f2642363e4ca3be25c801e353b35f','1BFA4FF1611596028B4760F3518C4F48E3EDDB537BF15B5E3CDCAB1BD5AB92B9',200,'{"schemaVersion":1,"rulesVersion":"r5","stateVersion":7,"commandId":"e86f2642363e4ca3be25c801e353b35f","identity":{"operatorId":"local-operator","actorId":"a1","sessionId":"s6c86d0e53c3f4218a2875c0d1d404596"},"eventCursor":8,"error":null,"status":"committed","result":{"action":"mosaic","activityId":"garden","authorActorId":"a1","commandId":"e86f2642363e4ca3be25c801e353b35f","visitCommandId":"de4fe5c6587e4741a72df4f72e114fba","baseRevision":0,"revision":1,"patch":[{"x":0,"y":1,"color":"river"},{"x":1,"y":1,"color":"river"},{"x":1,"y":2,"color":"river"},{"x":2,"y":2,"color":"river"},{"x":3,"y":2,"color":"river"},{"x":3,"y":3,"color":"river"},{"x":4,"y":3,"color":"river"}],"stateVersion":7,"paintedAtUtc":"2026-10-25T14:29:03.0188847\u002B00:00","position":[1,6]}}');
INSERT INTO "receipts" VALUES('foundation-01','a1','f903b9ce309947baa87b38318c28a949','D543B3F08755071C7DC07A67F675CA8346BF602D6188AD75FA898A1B6A23BF15',200,'{"schemaVersion":1,"rulesVersion":"r5","stateVersion":8,"commandId":"f903b9ce309947baa87b38318c28a949","identity":{"operatorId":"local-operator","actorId":"a1","sessionId":"s6c86d0e53c3f4218a2875c0d1d404596"},"eventCursor":9,"error":null,"status":"committed","result":{"action":"move","position":[1,5]}}');
INSERT INTO "receipts" VALUES('foundation-01','a1','9632672c420646f6b63ea8ad565b92ca','A4830E11DF66F05EB0A0C941229A4C1E579BAE7F47A3BDDCB24F0C9760FFD9BA',200,'{"schemaVersion":1,"rulesVersion":"r5","stateVersion":9,"commandId":"9632672c420646f6b63ea8ad565b92ca","identity":{"operatorId":"local-operator","actorId":"a1","sessionId":"s6c86d0e53c3f4218a2875c0d1d404596"},"eventCursor":10,"error":null,"status":"committed","result":{"action":"move","position":[1,4]}}');
INSERT INTO "receipts" VALUES('foundation-01','a1','6dec48e726704e1ab217e1b4ae7a06b4','7A70C03E072FC0B47EC8956C854393989B79449E825579393CB4A191693152A6',200,'{"schemaVersion":1,"rulesVersion":"r5","stateVersion":10,"commandId":"6dec48e726704e1ab217e1b4ae7a06b4","identity":{"operatorId":"local-operator","actorId":"a1","sessionId":"s6c86d0e53c3f4218a2875c0d1d404596"},"eventCursor":11,"error":null,"status":"committed","result":{"action":"move","position":[1,3]}}');
INSERT INTO "receipts" VALUES('foundation-01','a1','ee90fd86bc7347b799e795023cc74333','715457F4E66A36102DA87B856182B78F99F54362458B62F68E1CE21AA596BF87',200,'{"schemaVersion":1,"rulesVersion":"r5","stateVersion":11,"commandId":"ee90fd86bc7347b799e795023cc74333","identity":{"operatorId":"local-operator","actorId":"a1","sessionId":"s6c86d0e53c3f4218a2875c0d1d404596"},"eventCursor":12,"error":null,"status":"committed","result":{"action":"move","position":[1,2]}}');
INSERT INTO "receipts" VALUES('foundation-01','a1','f1a72fd80e474b8ab151935387f26c1e','770E1DE008C57FA93D1AFE225C18F69193974486BF49093EA4A8DACA11D74E9C',200,'{"schemaVersion":1,"rulesVersion":"r5","stateVersion":12,"commandId":"f1a72fd80e474b8ab151935387f26c1e","identity":{"operatorId":"local-operator","actorId":"a1","sessionId":"s6c86d0e53c3f4218a2875c0d1d404596"},"eventCursor":13,"error":null,"status":"committed","result":{"action":"move","position":[1,1]}}');
INSERT INTO "receipts" VALUES('foundation-01','a2','7af268fdb1c648708672f021e409fc5f','9B30B8B5BEDB387F111B7C37EC85C423603615A91BBF140F07A88A7206D10A59',200,'{"schemaVersion":1,"rulesVersion":"r5","stateVersion":13,"commandId":"7af268fdb1c648708672f021e409fc5f","identity":{"operatorId":"local-operator","actorId":"a2","sessionId":"se4272c7581ae477fb9386c33d5a2a866"},"eventCursor":14,"error":null,"status":"committed","result":{"action":"move","position":[1,3]}}');
INSERT INTO "receipts" VALUES('foundation-01','a2','e1cd45fa7dcf41a0af4d79027b55b17d','B6F2D03E1D2C24F06E2B4B4ABCD0988BB71C57E5EF91733240F8884CD00F7202',200,'{"schemaVersion":1,"rulesVersion":"r5","stateVersion":14,"commandId":"e1cd45fa7dcf41a0af4d79027b55b17d","identity":{"operatorId":"local-operator","actorId":"a2","sessionId":"se4272c7581ae477fb9386c33d5a2a866"},"eventCursor":15,"error":null,"status":"committed","result":{"action":"move","position":[1,4]}}');
INSERT INTO "receipts" VALUES('foundation-01','a2','8061e6386550427f8231ebfcb2335771','DFAAB46628DDA2F476F51AC4BCF5343C0D6E6EBC8CA18C0BDD00FA166B12AC3F',200,'{"schemaVersion":1,"rulesVersion":"r5","stateVersion":15,"commandId":"8061e6386550427f8231ebfcb2335771","identity":{"operatorId":"local-operator","actorId":"a2","sessionId":"se4272c7581ae477fb9386c33d5a2a866"},"eventCursor":16,"error":null,"status":"committed","result":{"action":"move","position":[1,5]}}');
INSERT INTO "receipts" VALUES('foundation-01','a2','34ab8830ac334716b983416a47e3c804','A7A043FB04846F7B7AEE294E389EA2B663BFB8B1C89806B53DE28F9DA80F99E8',200,'{"schemaVersion":1,"rulesVersion":"r5","stateVersion":16,"commandId":"34ab8830ac334716b983416a47e3c804","identity":{"operatorId":"local-operator","actorId":"a2","sessionId":"se4272c7581ae477fb9386c33d5a2a866"},"eventCursor":17,"error":null,"status":"committed","result":{"action":"move","position":[1,6]}}');
INSERT INTO "receipts" VALUES('foundation-01','a2','c12d6617cb5e4ae3aa5b3d48f7b5efe9','F38ECDDEC919FB1ED9B1B7901EC19B517D5D22B9CF91D34C84FCDE810EF71CF7',200,'{"schemaVersion":1,"rulesVersion":"r5","stateVersion":17,"commandId":"c12d6617cb5e4ae3aa5b3d48f7b5efe9","identity":{"operatorId":"local-operator","actorId":"a2","sessionId":"se4272c7581ae477fb9386c33d5a2a866"},"eventCursor":18,"error":null,"status":"committed","result":{"action":"visit","activityId":"garden","position":[1,6],"visitedAtUtc":"2026-10-25T14:29:15.0413577\u002B00:00"}}');
INSERT INTO "receipts" VALUES('foundation-01','a2','49bd14213c4245a3a1034dd704e6723c','07553671EB98B24D606027B37929255B13287F2A569D7D7E115D99280625EA7C',200,'{"schemaVersion":1,"rulesVersion":"r5","stateVersion":18,"commandId":"49bd14213c4245a3a1034dd704e6723c","identity":{"operatorId":"local-operator","actorId":"a2","sessionId":"se4272c7581ae477fb9386c33d5a2a866"},"eventCursor":19,"error":null,"status":"committed","result":{"action":"mosaic","activityId":"garden","authorActorId":"a2","commandId":"49bd14213c4245a3a1034dd704e6723c","visitCommandId":"c12d6617cb5e4ae3aa5b3d48f7b5efe9","baseRevision":1,"revision":2,"patch":[{"x":0,"y":0,"color":"leaf"},{"x":1,"y":0,"color":"rose"},{"x":2,"y":1,"color":"leaf"},{"x":3,"y":1,"color":"rose"},{"x":0,"y":2,"color":"leaf"},{"x":1,"y":3,"color":"leaf"},{"x":2,"y":3,"color":"leaf"},{"x":4,"y":4,"color":"leaf"}],"stateVersion":18,"paintedAtUtc":"2026-10-25T14:29:15.0483553\u002B00:00","position":[1,6]}}');
INSERT INTO "receipts" VALUES('foundation-01','a2','9c8fdf4c9ba94989a4dea6d9c4b0e182','9503769F811231713A09580B1AB6B52DCB45654D5A5D9F3696F7697B293068A6',200,'{"schemaVersion":1,"rulesVersion":"r5","stateVersion":19,"commandId":"9c8fdf4c9ba94989a4dea6d9c4b0e182","identity":{"operatorId":"local-operator","actorId":"a2","sessionId":"se4272c7581ae477fb9386c33d5a2a866"},"eventCursor":20,"error":null,"status":"committed","result":{"action":"move","position":[1,5]}}');
INSERT INTO "receipts" VALUES('foundation-01','a2','6430ec5253864203b3c7cb2ba417ec0b','3A16936964987CEF50AB44017A9BC3163212896EC454CCCFE4CBF2081DE30B80',200,'{"schemaVersion":1,"rulesVersion":"r5","stateVersion":20,"commandId":"6430ec5253864203b3c7cb2ba417ec0b","identity":{"operatorId":"local-operator","actorId":"a2","sessionId":"se4272c7581ae477fb9386c33d5a2a866"},"eventCursor":21,"error":null,"status":"committed","result":{"action":"move","position":[1,4]}}');
INSERT INTO "receipts" VALUES('foundation-01','a2','44d3ed83defa4ad3a316212d4f1bf54b','0894A52EA85AB1493C70CA40C7D500D54ABFA870BE5049EE945D348C394E7D88',200,'{"schemaVersion":1,"rulesVersion":"r5","stateVersion":21,"commandId":"44d3ed83defa4ad3a316212d4f1bf54b","identity":{"operatorId":"local-operator","actorId":"a2","sessionId":"se4272c7581ae477fb9386c33d5a2a866"},"eventCursor":22,"error":null,"status":"committed","result":{"action":"move","position":[1,3]}}');
INSERT INTO "receipts" VALUES('foundation-01','a2','3a475ace10a047cfae97cf6bddcce3b8','07992AC2FD4683D6F08B4B9B542505A40BD0320A451EAC38E7E9B3A7AF6657D3',200,'{"schemaVersion":1,"rulesVersion":"r5","stateVersion":22,"commandId":"3a475ace10a047cfae97cf6bddcce3b8","identity":{"operatorId":"local-operator","actorId":"a2","sessionId":"se4272c7581ae477fb9386c33d5a2a866"},"eventCursor":23,"error":null,"status":"committed","result":{"action":"move","position":[1,2]}}');
CREATE TABLE recipes(
  id TEXT PRIMARY KEY, definition_id TEXT NOT NULL, definition_version INTEGER NOT NULL,
  rules_version TEXT NOT NULL, wood_cost INTEGER NOT NULL CHECK(wood_cost>0));
INSERT INTO "recipes" VALUES('platform.v1','platform',1,'r5',3);
INSERT INTO "recipes" VALUES('bridge.v1','bridge',1,'r5',3);
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
CREATE TABLE sessions(
  session_id TEXT PRIMARY KEY, world_id TEXT NOT NULL, actor_id TEXT NOT NULL, token_hash TEXT NOT NULL UNIQUE,
  expires_at_ms INTEGER NOT NULL, revoked INTEGER NOT NULL CHECK(revoked IN(0,1)),
  FOREIGN KEY(world_id,actor_id) REFERENCES residents(world_id,actor_id));
INSERT INTO "sessions" VALUES('s6c86d0e53c3f4218a2875c0d1d404596','foundation-01','a1','8C0B2CE1A757C675D5A5312E2D5FF69BBDE9364B0B8DE5AB49B0346D8146C264',4102444800000,0);
INSERT INTO "sessions" VALUES('se4272c7581ae477fb9386c33d5a2a866','foundation-01','a2','727BD31E67B6DCA43BAAB5CC71622F6018AE760439B69FDF4A88A832F285F6E2',4102444800000,0);
CREATE TABLE visits(
  world_id TEXT NOT NULL, actor_id TEXT NOT NULL, command_id TEXT NOT NULL,
  activity_id TEXT NOT NULL, state_version INTEGER NOT NULL,
  visited_at_utc TEXT NOT NULL,
  x INTEGER NOT NULL CHECK(x BETWEEN 0 AND 7), y INTEGER NOT NULL CHECK(y BETWEEN 0 AND 7),
  PRIMARY KEY(world_id,actor_id,command_id), UNIQUE(world_id,state_version),
  FOREIGN KEY(world_id,actor_id) REFERENCES residents(world_id,actor_id),
  FOREIGN KEY(world_id,state_version) REFERENCES events(world_id,state_version) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY(world_id,actor_id,command_id) REFERENCES receipts(world_id,actor_id,command_id) DEFERRABLE INITIALLY DEFERRED);
INSERT INTO "visits" VALUES('foundation-01','a1','de4fe5c6587e4741a72df4f72e114fba','garden',6,'2026-10-25T14:29:03.0084915+00:00',1,6);
INSERT INTO "visits" VALUES('foundation-01','a2','c12d6617cb5e4ae3aa5b3d48f7b5efe9','garden',17,'2026-10-25T14:29:15.0413577+00:00',1,6);
CREATE TABLE worlds(
  id TEXT PRIMARY KEY CHECK(id='foundation-01'), scenario_id TEXT NOT NULL,
  rules_version TEXT NOT NULL,
  state_version INTEGER NOT NULL CHECK(typeof(state_version)='integer' AND state_version>=0),
  issued_wood INTEGER NOT NULL CHECK(issued_wood=12), depot_wood INTEGER NOT NULL CHECK(depot_wood BETWEEN 0 AND 12),
  CHECK(scenario_id='mosaic-v1' AND rules_version='r5'));
INSERT INTO "worlds" VALUES('foundation-01','mosaic-v1','r5',22,12,12);
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
CREATE INDEX recent_postcards_by_author ON postcards(world_id,author_actor_id,state_version);
CREATE TRIGGER immutable_postcard_update BEFORE UPDATE ON postcards BEGIN SELECT RAISE(ABORT,'immutable postcard'); END;
CREATE TRIGGER immutable_postcard_delete BEFORE DELETE ON postcards BEGIN SELECT RAISE(ABORT,'immutable postcard'); END;
CREATE INDEX recent_mosaic_edits_by_author ON mosaic_edits(world_id,author_actor_id,revision);
CREATE TRIGGER immutable_mosaic_edit_update BEFORE UPDATE ON mosaic_edits BEGIN SELECT RAISE(ABORT,'immutable mosaic edit'); END;
CREATE TRIGGER immutable_mosaic_edit_delete BEFORE DELETE ON mosaic_edits BEGIN SELECT RAISE(ABORT,'immutable mosaic edit'); END;
DELETE FROM "sqlite_sequence";
INSERT INTO "sqlite_sequence" VALUES('events',23);
COMMIT;
