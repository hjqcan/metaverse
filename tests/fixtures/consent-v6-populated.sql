PRAGMA user_version=6;
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
INSERT INTO "events" VALUES(1,'foundation-01',0,'{"seq":1,"stateVersion":0,"commandId":null,"actorId":null,"type":"worldSeeded","quantity":12,"source":"ITER-0007 initial allocation"}');
INSERT INTO "events" VALUES(2,'foundation-01',1,'{"seq":2,"stateVersion":1,"commandId":"8d314a0266d24a6d90b7dcbdeb816ffc","actorId":"a1","type":"moved","position":[1,2]}');
INSERT INTO "events" VALUES(3,'foundation-01',2,'{"seq":3,"stateVersion":2,"commandId":"ef94999726bb490d9f925b427e2c66ec","actorId":"a1","type":"moved","position":[1,3]}');
INSERT INTO "events" VALUES(4,'foundation-01',3,'{"seq":4,"stateVersion":3,"commandId":"0bede8a8ca264c8a95749c27771d321c","actorId":"a1","type":"moved","position":[1,4]}');
INSERT INTO "events" VALUES(5,'foundation-01',4,'{"seq":5,"stateVersion":4,"commandId":"3a8a2860178b4bddb68c0ffe7e892611","actorId":"a1","type":"moved","position":[1,5]}');
INSERT INTO "events" VALUES(6,'foundation-01',5,'{"seq":6,"stateVersion":5,"commandId":"22f2e080e4004f75b539b8c53798b84c","actorId":"a1","type":"moved","position":[1,6]}');
INSERT INTO "events" VALUES(7,'foundation-01',6,'{"seq":7,"stateVersion":6,"commandId":"535838832c0f41b69772de8ba343dc45","actorId":"a1","type":"visited","activityId":"garden","position":[1,6]}');
INSERT INTO "events" VALUES(8,'foundation-01',7,'{"seq":8,"type":"mosaic_painted","actorId":"a1","activityId":"garden","authorActorId":"a1","commandId":"5b270b406c8c4db08fe8e46568e30f9e","visitCommandId":"535838832c0f41b69772de8ba343dc45","baseRevision":0,"revision":1,"patch":[{"x":1,"y":2,"color":"river"},{"x":2,"y":2,"color":"river"},{"x":3,"y":2,"color":"river"}],"stateVersion":7,"paintedAtUtc":"2026-10-25T15:04:32.5950645\u002B00:00","position":[1,6]}');
INSERT INTO "events" VALUES(9,'foundation-01',8,'{"seq":9,"stateVersion":8,"commandId":"bd799bf545544fab826ecc8ca88acd47","actorId":"a1","type":"moved","position":[1,5]}');
INSERT INTO "events" VALUES(10,'foundation-01',9,'{"seq":10,"stateVersion":9,"commandId":"f7319078403e479bac054b92ebf34cfc","actorId":"a1","type":"moved","position":[1,4]}');
INSERT INTO "events" VALUES(11,'foundation-01',10,'{"seq":11,"stateVersion":10,"commandId":"78d1e92b42984b6db7ce27a282269888","actorId":"a1","type":"moved","position":[1,3]}');
INSERT INTO "events" VALUES(12,'foundation-01',11,'{"seq":12,"stateVersion":11,"commandId":"a325be10a4244a4687f42b595e024d28","actorId":"a1","type":"moved","position":[1,2]}');
INSERT INTO "events" VALUES(13,'foundation-01',12,'{"seq":13,"stateVersion":12,"commandId":"9840d2b3a72148c5a2a1fa3c1741beba","actorId":"a1","type":"moved","position":[1,1]}');
INSERT INTO "events" VALUES(14,'foundation-01',13,'{"seq":14,"stateVersion":13,"commandId":"5000647ac11249d7877283a638844838","actorId":"a2","type":"moved","position":[1,3]}');
INSERT INTO "events" VALUES(15,'foundation-01',14,'{"seq":15,"stateVersion":14,"commandId":"8775423339534af29905b16637c3ab3c","actorId":"a2","type":"moved","position":[1,4]}');
INSERT INTO "events" VALUES(16,'foundation-01',15,'{"seq":16,"stateVersion":15,"commandId":"8af40fea28a8424397139ec812e3eb54","actorId":"a2","type":"moved","position":[1,5]}');
INSERT INTO "events" VALUES(17,'foundation-01',16,'{"seq":17,"stateVersion":16,"commandId":"db2bfd22feac4ec08bdaa7f288a2c847","actorId":"a2","type":"moved","position":[1,6]}');
INSERT INTO "events" VALUES(18,'foundation-01',17,'{"seq":18,"stateVersion":17,"commandId":"098129af864748c1929b802764e9ea10","actorId":"a2","type":"visited","activityId":"garden","position":[1,6]}');
INSERT INTO "events" VALUES(19,'foundation-01',18,'{"activityId":"garden","authorActorId":"a2","targetActorId":"a1","commandId":"b5f0b41f95ae44ee9821acbe9de0b63b","visitCommandId":"098129af864748c1929b802764e9ea10","baseRevision":1,"patch":[{"x":1,"y":2,"color":"sun"}],"text":"\u539F\u753B\u8005a1\uFF1A\u5EFA\u8BAE\u60A8\u4EC5\u5C06\u84DD\u8272\u6CB3\u6D41\u5DE6\u7AEF\u70B9\uFF081,2\uFF09\u7531\u6CB3\u84DD\u6539\u4E3A\u65E5\u9EC4\uFF0C\u4F5C\u4E3A\u9633\u5149\u6807\u8BB0\uFF0C\u4E3A\u82B1\u56ED\u589E\u6DFB\u6696\u610F\uFF0C\u5176\u4F59\u683C\u5B50\u4FDD\u6301\u4E0D\u53D8\u3002\u8FD9\u53EA\u662F\u63D0\u8BAE\uFF0C\u5C1A\u672A\u6539\u56FE\uFF0C\u8BF7\u60A8\u81EA\u884C\u5BA1\u9605\u51B3\u5B9A\u3002","stateVersion":18,"proposedAtUtc":"2026-10-25T15:04:43.7765431\u002B00:00","position":[1,6],"seq":19,"type":"mosaic_proposed","actorId":"a2"}');
INSERT INTO "events" VALUES(20,'foundation-01',19,'{"seq":20,"stateVersion":19,"commandId":"dcc236e333e54036a102d679adf98970","actorId":"a2","type":"moved","position":[1,5]}');
INSERT INTO "events" VALUES(21,'foundation-01',20,'{"seq":21,"stateVersion":20,"commandId":"1415f82e47c94a6e913f2798cb163262","actorId":"a2","type":"moved","position":[1,4]}');
INSERT INTO "events" VALUES(22,'foundation-01',21,'{"seq":22,"stateVersion":21,"commandId":"3a548234a91441c7a20ea6edb1182f20","actorId":"a2","type":"moved","position":[1,3]}');
INSERT INTO "events" VALUES(23,'foundation-01',22,'{"seq":23,"stateVersion":22,"commandId":"0d1e688d018a4fd59a1a262604da0b66","actorId":"a2","type":"moved","position":[1,2]}');
INSERT INTO "events" VALUES(24,'foundation-01',23,'{"seq":24,"stateVersion":23,"commandId":"c4acda10ca99434d91bedbca9e0a6730","actorId":"a1","type":"moved","position":[1,2]}');
INSERT INTO "events" VALUES(25,'foundation-01',24,'{"seq":25,"stateVersion":24,"commandId":"8479b53c4d324cdea1a977b6eb6adfb7","actorId":"a1","type":"moved","position":[1,3]}');
INSERT INTO "events" VALUES(26,'foundation-01',25,'{"seq":26,"stateVersion":25,"commandId":"fed0e8508fc440b4abc71dcbda10a70c","actorId":"a1","type":"moved","position":[1,4]}');
INSERT INTO "events" VALUES(27,'foundation-01',26,'{"seq":27,"stateVersion":26,"commandId":"596f23ceb70049558542fad5de6b419e","actorId":"a1","type":"moved","position":[1,5]}');
INSERT INTO "events" VALUES(28,'foundation-01',27,'{"seq":28,"stateVersion":27,"commandId":"5c6ba9d0eb4f42eb9dde19020457f199","actorId":"a1","type":"moved","position":[1,6]}');
INSERT INTO "events" VALUES(29,'foundation-01',28,'{"seq":29,"stateVersion":28,"commandId":"efb84e089dfa415090fa2b219f68ad67","actorId":"a1","type":"visited","activityId":"garden","position":[1,6]}');
INSERT INTO "events" VALUES(30,'foundation-01',29,'{"activityId":"garden","authorActorId":"a1","commandId":"b64d1d9ae37b465ba2e485748e0956bd","visitCommandId":"efb84e089dfa415090fa2b219f68ad67","proposalActorId":"a2","proposalCommandId":"b5f0b41f95ae44ee9821acbe9de0b63b","decision":"accept","text":"\u539F\u63D0\u8BAE\u4EC5\u5C06\u84DD\u8272\u6CB3\u6D41\u5DE6\u7AEF\u70B9\uFF081,2\uFF09\u6539\u4E3A\u65E5\u9EC4\uFF0C\u5176\u4ED6\u683C\u4E0D\u53D8\uFF0C\u4E14baseRevision\u4E0E\u5F53\u524Drevision\u5747\u4E3A1\uFF0C\u7B26\u5408\u63A5\u53D7\u6761\u4EF6\u3002","stateVersion":29,"reviewedAtUtc":"2026-10-25T15:04:51.2616486\u002B00:00","position":[1,6],"mosaicEdit":{"activityId":"garden","authorActorId":"a1","commandId":"b64d1d9ae37b465ba2e485748e0956bd","visitCommandId":"efb84e089dfa415090fa2b219f68ad67","baseRevision":1,"revision":2,"patch":[{"x":1,"y":2,"color":"sun"}],"stateVersion":29,"paintedAtUtc":"2026-10-25T15:04:51.2616486\u002B00:00","position":[1,6]},"seq":30,"type":"mosaic_reviewed","actorId":"a1"}');
INSERT INTO "events" VALUES(31,'foundation-01',30,'{"seq":31,"stateVersion":30,"commandId":"2a760e48bfd84c3aaa0ee2069a7e7f48","actorId":"a1","type":"moved","position":[1,5]}');
INSERT INTO "events" VALUES(32,'foundation-01',31,'{"seq":32,"stateVersion":31,"commandId":"b531406e6f154dc69e4eae27093e712d","actorId":"a1","type":"moved","position":[1,4]}');
INSERT INTO "events" VALUES(33,'foundation-01',32,'{"seq":33,"stateVersion":32,"commandId":"40f6f57a972f4b17be0e9309a9f2565c","actorId":"a1","type":"moved","position":[1,3]}');
INSERT INTO "events" VALUES(34,'foundation-01',33,'{"seq":34,"stateVersion":33,"commandId":"80eae7894da34375b906fd3ca6ae3b33","actorId":"a1","type":"moved","position":[1,2]}');
INSERT INTO "events" VALUES(35,'foundation-01',34,'{"seq":35,"stateVersion":34,"commandId":"5b35804cc91341869904680ec941cebc","actorId":"a1","type":"moved","position":[1,1]}');
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
INSERT INTO "mosaic_cells" VALUES('foundation-01','garden',0,0,'blank',NULL,NULL,NULL);
INSERT INTO "mosaic_cells" VALUES('foundation-01','garden',1,0,'blank',NULL,NULL,NULL);
INSERT INTO "mosaic_cells" VALUES('foundation-01','garden',2,0,'blank',NULL,NULL,NULL);
INSERT INTO "mosaic_cells" VALUES('foundation-01','garden',3,0,'blank',NULL,NULL,NULL);
INSERT INTO "mosaic_cells" VALUES('foundation-01','garden',4,0,'blank',NULL,NULL,NULL);
INSERT INTO "mosaic_cells" VALUES('foundation-01','garden',0,1,'blank',NULL,NULL,NULL);
INSERT INTO "mosaic_cells" VALUES('foundation-01','garden',1,1,'blank',NULL,NULL,NULL);
INSERT INTO "mosaic_cells" VALUES('foundation-01','garden',2,1,'blank',NULL,NULL,NULL);
INSERT INTO "mosaic_cells" VALUES('foundation-01','garden',3,1,'blank',NULL,NULL,NULL);
INSERT INTO "mosaic_cells" VALUES('foundation-01','garden',4,1,'blank',NULL,NULL,NULL);
INSERT INTO "mosaic_cells" VALUES('foundation-01','garden',0,2,'blank',NULL,NULL,NULL);
INSERT INTO "mosaic_cells" VALUES('foundation-01','garden',1,2,'sun','a1','b64d1d9ae37b465ba2e485748e0956bd',29);
INSERT INTO "mosaic_cells" VALUES('foundation-01','garden',2,2,'river','a1','5b270b406c8c4db08fe8e46568e30f9e',7);
INSERT INTO "mosaic_cells" VALUES('foundation-01','garden',3,2,'river','a1','5b270b406c8c4db08fe8e46568e30f9e',7);
INSERT INTO "mosaic_cells" VALUES('foundation-01','garden',4,2,'blank',NULL,NULL,NULL);
INSERT INTO "mosaic_cells" VALUES('foundation-01','garden',0,3,'blank',NULL,NULL,NULL);
INSERT INTO "mosaic_cells" VALUES('foundation-01','garden',1,3,'blank',NULL,NULL,NULL);
INSERT INTO "mosaic_cells" VALUES('foundation-01','garden',2,3,'blank',NULL,NULL,NULL);
INSERT INTO "mosaic_cells" VALUES('foundation-01','garden',3,3,'blank',NULL,NULL,NULL);
INSERT INTO "mosaic_cells" VALUES('foundation-01','garden',4,3,'blank',NULL,NULL,NULL);
INSERT INTO "mosaic_cells" VALUES('foundation-01','garden',0,4,'blank',NULL,NULL,NULL);
INSERT INTO "mosaic_cells" VALUES('foundation-01','garden',1,4,'blank',NULL,NULL,NULL);
INSERT INTO "mosaic_cells" VALUES('foundation-01','garden',2,4,'blank',NULL,NULL,NULL);
INSERT INTO "mosaic_cells" VALUES('foundation-01','garden',3,4,'blank',NULL,NULL,NULL);
INSERT INTO "mosaic_cells" VALUES('foundation-01','garden',4,4,'blank',NULL,NULL,NULL);
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
INSERT INTO "mosaic_edits" VALUES('foundation-01','garden','a1','5b270b406c8c4db08fe8e46568e30f9e','535838832c0f41b69772de8ba343dc45',0,1,'[{"x":1,"y":2,"color":"river"},{"x":2,"y":2,"color":"river"},{"x":3,"y":2,"color":"river"}]',7,'2026-10-25T15:04:32.5950645+00:00',1,6);
INSERT INTO "mosaic_edits" VALUES('foundation-01','garden','a1','b64d1d9ae37b465ba2e485748e0956bd','efb84e089dfa415090fa2b219f68ad67',1,2,'[{"x":1,"y":2,"color":"sun"}]',29,'2026-10-25T15:04:51.2616486+00:00',1,6);
CREATE TABLE mosaic_proposals(
  world_id TEXT NOT NULL, activity_id TEXT NOT NULL CHECK(activity_id='garden'),
  author_actor_id TEXT NOT NULL, target_actor_id TEXT NOT NULL CHECK(target_actor_id<>author_actor_id),
  command_id TEXT NOT NULL, visit_command_id TEXT NOT NULL,
  base_revision INTEGER NOT NULL CHECK(typeof(base_revision)='integer' AND base_revision>=0),
  patch_json TEXT NOT NULL CHECK(json_valid(patch_json) AND json_type(patch_json)='array' AND json_array_length(patch_json) BETWEEN 1 AND 8),
  text TEXT NOT NULL, state_version INTEGER NOT NULL, proposed_at_utc TEXT NOT NULL,
  x INTEGER NOT NULL CHECK(x=1), y INTEGER NOT NULL CHECK(y=6),
  PRIMARY KEY(world_id,author_actor_id,command_id), UNIQUE(world_id,state_version),
  UNIQUE(world_id,author_actor_id,visit_command_id),
  UNIQUE(world_id,author_actor_id,command_id,target_actor_id),
  FOREIGN KEY(world_id,activity_id) REFERENCES mosaics(world_id,activity_id),
  FOREIGN KEY(world_id,target_actor_id) REFERENCES residents(world_id,actor_id),
  FOREIGN KEY(world_id,author_actor_id,visit_command_id) REFERENCES visits(world_id,actor_id,command_id),
  FOREIGN KEY(world_id,state_version) REFERENCES events(world_id,state_version) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY(world_id,author_actor_id,command_id) REFERENCES receipts(world_id,actor_id,command_id) DEFERRABLE INITIALLY DEFERRED);
INSERT INTO "mosaic_proposals" VALUES('foundation-01','garden','a2','a1','b5f0b41f95ae44ee9821acbe9de0b63b','098129af864748c1929b802764e9ea10',1,'[{"x":1,"y":2,"color":"sun"}]','原画者a1：建议您仅将蓝色河流左端点（1,2）由河蓝改为日黄，作为阳光标记，为花园增添暖意，其余格子保持不变。这只是提议，尚未改图，请您自行审阅决定。',18,'2026-10-25T15:04:43.7765431+00:00',1,6);
CREATE TABLE mosaic_reviews(
  world_id TEXT NOT NULL, activity_id TEXT NOT NULL CHECK(activity_id='garden'),
  author_actor_id TEXT NOT NULL, command_id TEXT NOT NULL, visit_command_id TEXT NOT NULL,
  proposal_actor_id TEXT NOT NULL, proposal_command_id TEXT NOT NULL,
  decision TEXT NOT NULL CHECK(decision IN('accept','reject')), text TEXT NOT NULL,
  state_version INTEGER NOT NULL, reviewed_at_utc TEXT NOT NULL,
  x INTEGER NOT NULL CHECK(x=1), y INTEGER NOT NULL CHECK(y=6), edit_command_id TEXT,
  CHECK((decision='accept' AND edit_command_id IS NOT NULL AND edit_command_id=command_id) OR
        (decision='reject' AND edit_command_id IS NULL)),
  PRIMARY KEY(world_id,author_actor_id,command_id), UNIQUE(world_id,state_version),
  UNIQUE(world_id,proposal_actor_id,proposal_command_id),
  FOREIGN KEY(world_id,activity_id) REFERENCES mosaics(world_id,activity_id),
  FOREIGN KEY(world_id,proposal_actor_id,proposal_command_id,author_actor_id)
    REFERENCES mosaic_proposals(world_id,author_actor_id,command_id,target_actor_id),
  FOREIGN KEY(world_id,author_actor_id,visit_command_id) REFERENCES visits(world_id,actor_id,command_id),
  FOREIGN KEY(world_id,author_actor_id,edit_command_id) REFERENCES mosaic_edits(world_id,author_actor_id,command_id),
  FOREIGN KEY(world_id,state_version) REFERENCES events(world_id,state_version) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY(world_id,author_actor_id,command_id) REFERENCES receipts(world_id,actor_id,command_id) DEFERRABLE INITIALLY DEFERRED);
INSERT INTO "mosaic_reviews" VALUES('foundation-01','garden','a1','b64d1d9ae37b465ba2e485748e0956bd','efb84e089dfa415090fa2b219f68ad67','a2','b5f0b41f95ae44ee9821acbe9de0b63b','accept','原提议仅将蓝色河流左端点（1,2）改为日黄，其他格不变，且baseRevision与当前revision均为1，符合接受条件。',29,'2026-10-25T15:04:51.2616486+00:00',1,6,'b64d1d9ae37b465ba2e485748e0956bd');
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
INSERT INTO "receipts" VALUES('foundation-01','a1','8d314a0266d24a6d90b7dcbdeb816ffc','4474975E8F830A537564C0BAF0B406ADABE0216D562C1CB7F5C9EDB6C268D82F',200,'{"schemaVersion":1,"rulesVersion":"r6","stateVersion":1,"commandId":"8d314a0266d24a6d90b7dcbdeb816ffc","identity":{"operatorId":"local-operator","actorId":"a1","sessionId":"s18f00abcbbf84f1b8eb5a3d3e60f3527"},"eventCursor":2,"error":null,"status":"committed","result":{"action":"move","position":[1,2]}}');
INSERT INTO "receipts" VALUES('foundation-01','a1','ef94999726bb490d9f925b427e2c66ec','352C3089F2E98FEDD39C32BD6C5102166A0AAEE1F8F697A9EBA59F50E9C8171D',200,'{"schemaVersion":1,"rulesVersion":"r6","stateVersion":2,"commandId":"ef94999726bb490d9f925b427e2c66ec","identity":{"operatorId":"local-operator","actorId":"a1","sessionId":"s18f00abcbbf84f1b8eb5a3d3e60f3527"},"eventCursor":3,"error":null,"status":"committed","result":{"action":"move","position":[1,3]}}');
INSERT INTO "receipts" VALUES('foundation-01','a1','0bede8a8ca264c8a95749c27771d321c','82FEFEBF2DDF7F6D2632B362AA42B227EC4E211452DDCEC956B69175187FCD3B',200,'{"schemaVersion":1,"rulesVersion":"r6","stateVersion":3,"commandId":"0bede8a8ca264c8a95749c27771d321c","identity":{"operatorId":"local-operator","actorId":"a1","sessionId":"s18f00abcbbf84f1b8eb5a3d3e60f3527"},"eventCursor":4,"error":null,"status":"committed","result":{"action":"move","position":[1,4]}}');
INSERT INTO "receipts" VALUES('foundation-01','a1','3a8a2860178b4bddb68c0ffe7e892611','5EDF738722787DEFABF4C6ED48B4F96366113964A0A2776E6A3CDCCB7AC2D80D',200,'{"schemaVersion":1,"rulesVersion":"r6","stateVersion":4,"commandId":"3a8a2860178b4bddb68c0ffe7e892611","identity":{"operatorId":"local-operator","actorId":"a1","sessionId":"s18f00abcbbf84f1b8eb5a3d3e60f3527"},"eventCursor":5,"error":null,"status":"committed","result":{"action":"move","position":[1,5]}}');
INSERT INTO "receipts" VALUES('foundation-01','a1','22f2e080e4004f75b539b8c53798b84c','15268636B8507E36A826D2E7DD55E35591A4A34B5706480AADAB25E0EB8DC146',200,'{"schemaVersion":1,"rulesVersion":"r6","stateVersion":5,"commandId":"22f2e080e4004f75b539b8c53798b84c","identity":{"operatorId":"local-operator","actorId":"a1","sessionId":"s18f00abcbbf84f1b8eb5a3d3e60f3527"},"eventCursor":6,"error":null,"status":"committed","result":{"action":"move","position":[1,6]}}');
INSERT INTO "receipts" VALUES('foundation-01','a1','535838832c0f41b69772de8ba343dc45','2FAC5F946FA428AC698B5B76CA06BEBB4276303651464BAE3E65D8459CC5288F',200,'{"schemaVersion":1,"rulesVersion":"r6","stateVersion":6,"commandId":"535838832c0f41b69772de8ba343dc45","identity":{"operatorId":"local-operator","actorId":"a1","sessionId":"s18f00abcbbf84f1b8eb5a3d3e60f3527"},"eventCursor":7,"error":null,"status":"committed","result":{"action":"visit","activityId":"garden","position":[1,6],"visitedAtUtc":"2026-10-25T15:04:32.5849950\u002B00:00"}}');
INSERT INTO "receipts" VALUES('foundation-01','a1','5b270b406c8c4db08fe8e46568e30f9e','E539065D6356CDB83280F0DD0A116FDAD721896763FC23E634B5CB95BD647375',200,'{"schemaVersion":1,"rulesVersion":"r6","stateVersion":7,"commandId":"5b270b406c8c4db08fe8e46568e30f9e","identity":{"operatorId":"local-operator","actorId":"a1","sessionId":"s18f00abcbbf84f1b8eb5a3d3e60f3527"},"eventCursor":8,"error":null,"status":"committed","result":{"action":"mosaic","activityId":"garden","authorActorId":"a1","commandId":"5b270b406c8c4db08fe8e46568e30f9e","visitCommandId":"535838832c0f41b69772de8ba343dc45","baseRevision":0,"revision":1,"patch":[{"x":1,"y":2,"color":"river"},{"x":2,"y":2,"color":"river"},{"x":3,"y":2,"color":"river"}],"stateVersion":7,"paintedAtUtc":"2026-10-25T15:04:32.5950645\u002B00:00","position":[1,6]}}');
INSERT INTO "receipts" VALUES('foundation-01','a1','bd799bf545544fab826ecc8ca88acd47','51F6DA9124940F6EA14EA989D3BE65EC87725F5A2001D4E5843F0826DCEE086A',200,'{"schemaVersion":1,"rulesVersion":"r6","stateVersion":8,"commandId":"bd799bf545544fab826ecc8ca88acd47","identity":{"operatorId":"local-operator","actorId":"a1","sessionId":"s18f00abcbbf84f1b8eb5a3d3e60f3527"},"eventCursor":9,"error":null,"status":"committed","result":{"action":"move","position":[1,5]}}');
INSERT INTO "receipts" VALUES('foundation-01','a1','f7319078403e479bac054b92ebf34cfc','D0B399481E5F3A81FE16469B0B3F486877304F3ED45DE3559B3CBBDABD88CBA4',200,'{"schemaVersion":1,"rulesVersion":"r6","stateVersion":9,"commandId":"f7319078403e479bac054b92ebf34cfc","identity":{"operatorId":"local-operator","actorId":"a1","sessionId":"s18f00abcbbf84f1b8eb5a3d3e60f3527"},"eventCursor":10,"error":null,"status":"committed","result":{"action":"move","position":[1,4]}}');
INSERT INTO "receipts" VALUES('foundation-01','a1','78d1e92b42984b6db7ce27a282269888','FF07C43916EF1E1B71548EBECA877BA5455C4137A1A66CE696A7EB6E4128E911',200,'{"schemaVersion":1,"rulesVersion":"r6","stateVersion":10,"commandId":"78d1e92b42984b6db7ce27a282269888","identity":{"operatorId":"local-operator","actorId":"a1","sessionId":"s18f00abcbbf84f1b8eb5a3d3e60f3527"},"eventCursor":11,"error":null,"status":"committed","result":{"action":"move","position":[1,3]}}');
INSERT INTO "receipts" VALUES('foundation-01','a1','a325be10a4244a4687f42b595e024d28','6D98E63A0762C7A1C1EF8E61D3B94345EA4D4C9F9378CA438746C367FE35B610',200,'{"schemaVersion":1,"rulesVersion":"r6","stateVersion":11,"commandId":"a325be10a4244a4687f42b595e024d28","identity":{"operatorId":"local-operator","actorId":"a1","sessionId":"s18f00abcbbf84f1b8eb5a3d3e60f3527"},"eventCursor":12,"error":null,"status":"committed","result":{"action":"move","position":[1,2]}}');
INSERT INTO "receipts" VALUES('foundation-01','a1','9840d2b3a72148c5a2a1fa3c1741beba','686F2EA81E7D33E5A7B8157EE05DE4752542D559D6A12FDBD6C58BEE629048D6',200,'{"schemaVersion":1,"rulesVersion":"r6","stateVersion":12,"commandId":"9840d2b3a72148c5a2a1fa3c1741beba","identity":{"operatorId":"local-operator","actorId":"a1","sessionId":"s18f00abcbbf84f1b8eb5a3d3e60f3527"},"eventCursor":13,"error":null,"status":"committed","result":{"action":"move","position":[1,1]}}');
INSERT INTO "receipts" VALUES('foundation-01','a2','5000647ac11249d7877283a638844838','01F740C0E8C588B3DD974EBE16C1AE64739A18F3BB39F8D1C4A0EE80CBB714DF',200,'{"schemaVersion":1,"rulesVersion":"r6","stateVersion":13,"commandId":"5000647ac11249d7877283a638844838","identity":{"operatorId":"local-operator","actorId":"a2","sessionId":"sb9d0ebe17a76417f99795e676808bb04"},"eventCursor":14,"error":null,"status":"committed","result":{"action":"move","position":[1,3]}}');
INSERT INTO "receipts" VALUES('foundation-01','a2','8775423339534af29905b16637c3ab3c','F777DD03836E8D21643FDC0B40E57A69BEF82F4E6C5FF1FB209F26D8A06E4D3F',200,'{"schemaVersion":1,"rulesVersion":"r6","stateVersion":14,"commandId":"8775423339534af29905b16637c3ab3c","identity":{"operatorId":"local-operator","actorId":"a2","sessionId":"sb9d0ebe17a76417f99795e676808bb04"},"eventCursor":15,"error":null,"status":"committed","result":{"action":"move","position":[1,4]}}');
INSERT INTO "receipts" VALUES('foundation-01','a2','8af40fea28a8424397139ec812e3eb54','7886EA3D7CD65549D361FFB1DB409BC6CCB2D66426610F9868B6B8BFB0D6BEFF',200,'{"schemaVersion":1,"rulesVersion":"r6","stateVersion":15,"commandId":"8af40fea28a8424397139ec812e3eb54","identity":{"operatorId":"local-operator","actorId":"a2","sessionId":"sb9d0ebe17a76417f99795e676808bb04"},"eventCursor":16,"error":null,"status":"committed","result":{"action":"move","position":[1,5]}}');
INSERT INTO "receipts" VALUES('foundation-01','a2','db2bfd22feac4ec08bdaa7f288a2c847','FBA2F9FF72F5189E471824F6952EA9BB791C0FDA63831645A64365EB028D865C',200,'{"schemaVersion":1,"rulesVersion":"r6","stateVersion":16,"commandId":"db2bfd22feac4ec08bdaa7f288a2c847","identity":{"operatorId":"local-operator","actorId":"a2","sessionId":"sb9d0ebe17a76417f99795e676808bb04"},"eventCursor":17,"error":null,"status":"committed","result":{"action":"move","position":[1,6]}}');
INSERT INTO "receipts" VALUES('foundation-01','a2','098129af864748c1929b802764e9ea10','EDCF13AEA3C08D9831DEAA24CFDB73BD8767A98E8C870212F0968715700B13D4',200,'{"schemaVersion":1,"rulesVersion":"r6","stateVersion":17,"commandId":"098129af864748c1929b802764e9ea10","identity":{"operatorId":"local-operator","actorId":"a2","sessionId":"sb9d0ebe17a76417f99795e676808bb04"},"eventCursor":18,"error":null,"status":"committed","result":{"action":"visit","activityId":"garden","position":[1,6],"visitedAtUtc":"2026-10-25T15:04:43.7680948\u002B00:00"}}');
INSERT INTO "receipts" VALUES('foundation-01','a2','b5f0b41f95ae44ee9821acbe9de0b63b','C4DEFBA4D0D11B3BEFCA27BD05C8B328DE4BF57B4B3997E2B4D20D1BFD2B612D',200,'{"schemaVersion":1,"rulesVersion":"r6","stateVersion":18,"commandId":"b5f0b41f95ae44ee9821acbe9de0b63b","identity":{"operatorId":"local-operator","actorId":"a2","sessionId":"sb9d0ebe17a76417f99795e676808bb04"},"eventCursor":19,"error":null,"status":"committed","result":{"activityId":"garden","authorActorId":"a2","targetActorId":"a1","commandId":"b5f0b41f95ae44ee9821acbe9de0b63b","visitCommandId":"098129af864748c1929b802764e9ea10","baseRevision":1,"patch":[{"x":1,"y":2,"color":"sun"}],"text":"\u539F\u753B\u8005a1\uFF1A\u5EFA\u8BAE\u60A8\u4EC5\u5C06\u84DD\u8272\u6CB3\u6D41\u5DE6\u7AEF\u70B9\uFF081,2\uFF09\u7531\u6CB3\u84DD\u6539\u4E3A\u65E5\u9EC4\uFF0C\u4F5C\u4E3A\u9633\u5149\u6807\u8BB0\uFF0C\u4E3A\u82B1\u56ED\u589E\u6DFB\u6696\u610F\uFF0C\u5176\u4F59\u683C\u5B50\u4FDD\u6301\u4E0D\u53D8\u3002\u8FD9\u53EA\u662F\u63D0\u8BAE\uFF0C\u5C1A\u672A\u6539\u56FE\uFF0C\u8BF7\u60A8\u81EA\u884C\u5BA1\u9605\u51B3\u5B9A\u3002","stateVersion":18,"proposedAtUtc":"2026-10-25T15:04:43.7765431\u002B00:00","position":[1,6],"action":"mosaic_propose"}}');
INSERT INTO "receipts" VALUES('foundation-01','a2','dcc236e333e54036a102d679adf98970','51438B3A751EAFF652365C0E746CDB460C3C2E15F0D61296CD75BBC39DAAB395',200,'{"schemaVersion":1,"rulesVersion":"r6","stateVersion":19,"commandId":"dcc236e333e54036a102d679adf98970","identity":{"operatorId":"local-operator","actorId":"a2","sessionId":"sb9d0ebe17a76417f99795e676808bb04"},"eventCursor":20,"error":null,"status":"committed","result":{"action":"move","position":[1,5]}}');
INSERT INTO "receipts" VALUES('foundation-01','a2','1415f82e47c94a6e913f2798cb163262','DE37FD9C1BFD2744FA6E978D5BA50D483254B268AF1B314494B377E8A331F1BC',200,'{"schemaVersion":1,"rulesVersion":"r6","stateVersion":20,"commandId":"1415f82e47c94a6e913f2798cb163262","identity":{"operatorId":"local-operator","actorId":"a2","sessionId":"sb9d0ebe17a76417f99795e676808bb04"},"eventCursor":21,"error":null,"status":"committed","result":{"action":"move","position":[1,4]}}');
INSERT INTO "receipts" VALUES('foundation-01','a2','3a548234a91441c7a20ea6edb1182f20','172ED7608F328C7C98B751E54E003DD6C98C081C76FDC89665100A701F6572E5',200,'{"schemaVersion":1,"rulesVersion":"r6","stateVersion":21,"commandId":"3a548234a91441c7a20ea6edb1182f20","identity":{"operatorId":"local-operator","actorId":"a2","sessionId":"sb9d0ebe17a76417f99795e676808bb04"},"eventCursor":22,"error":null,"status":"committed","result":{"action":"move","position":[1,3]}}');
INSERT INTO "receipts" VALUES('foundation-01','a2','0d1e688d018a4fd59a1a262604da0b66','C9485BC1CFA6E08ACC17BF9426ACE081D112446203CC2AD2C49C12290C94FE14',200,'{"schemaVersion":1,"rulesVersion":"r6","stateVersion":22,"commandId":"0d1e688d018a4fd59a1a262604da0b66","identity":{"operatorId":"local-operator","actorId":"a2","sessionId":"sb9d0ebe17a76417f99795e676808bb04"},"eventCursor":23,"error":null,"status":"committed","result":{"action":"move","position":[1,2]}}');
INSERT INTO "receipts" VALUES('foundation-01','a1','c4acda10ca99434d91bedbca9e0a6730','4143B108E9E110764B44BC46EA66ECF4179E7AB43EF84214904C6637640EDFE1',200,'{"schemaVersion":1,"rulesVersion":"r6","stateVersion":23,"commandId":"c4acda10ca99434d91bedbca9e0a6730","identity":{"operatorId":"local-operator","actorId":"a1","sessionId":"s18f00abcbbf84f1b8eb5a3d3e60f3527"},"eventCursor":24,"error":null,"status":"committed","result":{"action":"move","position":[1,2]}}');
INSERT INTO "receipts" VALUES('foundation-01','a1','8479b53c4d324cdea1a977b6eb6adfb7','797A08D9EDF581C726F35786338F8E56A5845ADAF1ECEBBBF0A88DD9F0EA86C9',200,'{"schemaVersion":1,"rulesVersion":"r6","stateVersion":24,"commandId":"8479b53c4d324cdea1a977b6eb6adfb7","identity":{"operatorId":"local-operator","actorId":"a1","sessionId":"s18f00abcbbf84f1b8eb5a3d3e60f3527"},"eventCursor":25,"error":null,"status":"committed","result":{"action":"move","position":[1,3]}}');
INSERT INTO "receipts" VALUES('foundation-01','a1','fed0e8508fc440b4abc71dcbda10a70c','2017026B950F231051409ADC7E77A5497F680B1168158C85336A88CD08924900',200,'{"schemaVersion":1,"rulesVersion":"r6","stateVersion":25,"commandId":"fed0e8508fc440b4abc71dcbda10a70c","identity":{"operatorId":"local-operator","actorId":"a1","sessionId":"s18f00abcbbf84f1b8eb5a3d3e60f3527"},"eventCursor":26,"error":null,"status":"committed","result":{"action":"move","position":[1,4]}}');
INSERT INTO "receipts" VALUES('foundation-01','a1','596f23ceb70049558542fad5de6b419e','558A4ADB2888B1027208B25746EC131D2A48F2E3B3DBE528D864EA71C14EC225',200,'{"schemaVersion":1,"rulesVersion":"r6","stateVersion":26,"commandId":"596f23ceb70049558542fad5de6b419e","identity":{"operatorId":"local-operator","actorId":"a1","sessionId":"s18f00abcbbf84f1b8eb5a3d3e60f3527"},"eventCursor":27,"error":null,"status":"committed","result":{"action":"move","position":[1,5]}}');
INSERT INTO "receipts" VALUES('foundation-01','a1','5c6ba9d0eb4f42eb9dde19020457f199','411015D6C2C49CDD460A885B26EFC72E38F5179CC6F5CD9E5FDA2B4CF0112FA9',200,'{"schemaVersion":1,"rulesVersion":"r6","stateVersion":27,"commandId":"5c6ba9d0eb4f42eb9dde19020457f199","identity":{"operatorId":"local-operator","actorId":"a1","sessionId":"s18f00abcbbf84f1b8eb5a3d3e60f3527"},"eventCursor":28,"error":null,"status":"committed","result":{"action":"move","position":[1,6]}}');
INSERT INTO "receipts" VALUES('foundation-01','a1','efb84e089dfa415090fa2b219f68ad67','9723C4AE21113E3259D87F22B0F75CE7B51D4EE40BCE9094DF044E7912A7A555',200,'{"schemaVersion":1,"rulesVersion":"r6","stateVersion":28,"commandId":"efb84e089dfa415090fa2b219f68ad67","identity":{"operatorId":"local-operator","actorId":"a1","sessionId":"s18f00abcbbf84f1b8eb5a3d3e60f3527"},"eventCursor":29,"error":null,"status":"committed","result":{"action":"visit","activityId":"garden","position":[1,6],"visitedAtUtc":"2026-10-25T15:04:51.2531566\u002B00:00"}}');
INSERT INTO "receipts" VALUES('foundation-01','a1','b64d1d9ae37b465ba2e485748e0956bd','0B60F5F30A194B46F6D1D543237050AEEDBF32CE547EB7A6ACEB4323FD47E6D7',200,'{"schemaVersion":1,"rulesVersion":"r6","stateVersion":29,"commandId":"b64d1d9ae37b465ba2e485748e0956bd","identity":{"operatorId":"local-operator","actorId":"a1","sessionId":"s18f00abcbbf84f1b8eb5a3d3e60f3527"},"eventCursor":30,"error":null,"status":"committed","result":{"activityId":"garden","authorActorId":"a1","commandId":"b64d1d9ae37b465ba2e485748e0956bd","visitCommandId":"efb84e089dfa415090fa2b219f68ad67","proposalActorId":"a2","proposalCommandId":"b5f0b41f95ae44ee9821acbe9de0b63b","decision":"accept","text":"\u539F\u63D0\u8BAE\u4EC5\u5C06\u84DD\u8272\u6CB3\u6D41\u5DE6\u7AEF\u70B9\uFF081,2\uFF09\u6539\u4E3A\u65E5\u9EC4\uFF0C\u5176\u4ED6\u683C\u4E0D\u53D8\uFF0C\u4E14baseRevision\u4E0E\u5F53\u524Drevision\u5747\u4E3A1\uFF0C\u7B26\u5408\u63A5\u53D7\u6761\u4EF6\u3002","stateVersion":29,"reviewedAtUtc":"2026-10-25T15:04:51.2616486\u002B00:00","position":[1,6],"mosaicEdit":{"activityId":"garden","authorActorId":"a1","commandId":"b64d1d9ae37b465ba2e485748e0956bd","visitCommandId":"efb84e089dfa415090fa2b219f68ad67","baseRevision":1,"revision":2,"patch":[{"x":1,"y":2,"color":"sun"}],"stateVersion":29,"paintedAtUtc":"2026-10-25T15:04:51.2616486\u002B00:00","position":[1,6]},"action":"mosaic_review"}}');
INSERT INTO "receipts" VALUES('foundation-01','a1','2a760e48bfd84c3aaa0ee2069a7e7f48','113E30ACC5AB7C9C0952F451B9D676B24B348716552598967613388A1BC69E60',200,'{"schemaVersion":1,"rulesVersion":"r6","stateVersion":30,"commandId":"2a760e48bfd84c3aaa0ee2069a7e7f48","identity":{"operatorId":"local-operator","actorId":"a1","sessionId":"s18f00abcbbf84f1b8eb5a3d3e60f3527"},"eventCursor":31,"error":null,"status":"committed","result":{"action":"move","position":[1,5]}}');
INSERT INTO "receipts" VALUES('foundation-01','a1','b531406e6f154dc69e4eae27093e712d','6EB3633F9A838C86801D36E76CBFA777FB27EDE0C21F453BFEB9801627C62B1F',200,'{"schemaVersion":1,"rulesVersion":"r6","stateVersion":31,"commandId":"b531406e6f154dc69e4eae27093e712d","identity":{"operatorId":"local-operator","actorId":"a1","sessionId":"s18f00abcbbf84f1b8eb5a3d3e60f3527"},"eventCursor":32,"error":null,"status":"committed","result":{"action":"move","position":[1,4]}}');
INSERT INTO "receipts" VALUES('foundation-01','a1','40f6f57a972f4b17be0e9309a9f2565c','AD03F4F63999DEAFE6BCCF9A2ED5BE222A9396C79A82D760D10601E30D3C5259',200,'{"schemaVersion":1,"rulesVersion":"r6","stateVersion":32,"commandId":"40f6f57a972f4b17be0e9309a9f2565c","identity":{"operatorId":"local-operator","actorId":"a1","sessionId":"s18f00abcbbf84f1b8eb5a3d3e60f3527"},"eventCursor":33,"error":null,"status":"committed","result":{"action":"move","position":[1,3]}}');
INSERT INTO "receipts" VALUES('foundation-01','a1','80eae7894da34375b906fd3ca6ae3b33','0A32793BA2A2CDFADACA65DFC24790AE75B695C5887A2BF3F3393F4F702B1312',200,'{"schemaVersion":1,"rulesVersion":"r6","stateVersion":33,"commandId":"80eae7894da34375b906fd3ca6ae3b33","identity":{"operatorId":"local-operator","actorId":"a1","sessionId":"s18f00abcbbf84f1b8eb5a3d3e60f3527"},"eventCursor":34,"error":null,"status":"committed","result":{"action":"move","position":[1,2]}}');
INSERT INTO "receipts" VALUES('foundation-01','a1','5b35804cc91341869904680ec941cebc','04CB522F15251626A9F9B084BB7AEDEFD2FDBB5E9C131E2C445F754F035E0443',200,'{"schemaVersion":1,"rulesVersion":"r6","stateVersion":34,"commandId":"5b35804cc91341869904680ec941cebc","identity":{"operatorId":"local-operator","actorId":"a1","sessionId":"s18f00abcbbf84f1b8eb5a3d3e60f3527"},"eventCursor":35,"error":null,"status":"committed","result":{"action":"move","position":[1,1]}}');
CREATE TABLE recipes(
  id TEXT PRIMARY KEY, definition_id TEXT NOT NULL, definition_version INTEGER NOT NULL,
  rules_version TEXT NOT NULL, wood_cost INTEGER NOT NULL CHECK(wood_cost>0));
INSERT INTO "recipes" VALUES('platform.v1','platform',1,'r6',3);
INSERT INTO "recipes" VALUES('bridge.v1','bridge',1,'r6',3);
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
INSERT INTO "sessions" VALUES('s18f00abcbbf84f1b8eb5a3d3e60f3527','foundation-01','a1','E17425B858808D686DC0921BD42E72AB3C1AEBEA9DB3AED8BE5CD112D12A5F70',4102444800000,0);
INSERT INTO "sessions" VALUES('sb9d0ebe17a76417f99795e676808bb04','foundation-01','a2','3FA4860DA07A42E476C6CB6E36FBD399665A3FA5BF61C02436791AAA9EDCC8E5',4102444800000,0);
CREATE TABLE visits(
  world_id TEXT NOT NULL, actor_id TEXT NOT NULL, command_id TEXT NOT NULL,
  activity_id TEXT NOT NULL, state_version INTEGER NOT NULL,
  visited_at_utc TEXT NOT NULL,
  x INTEGER NOT NULL CHECK(x BETWEEN 0 AND 7), y INTEGER NOT NULL CHECK(y BETWEEN 0 AND 7),
  PRIMARY KEY(world_id,actor_id,command_id), UNIQUE(world_id,state_version),
  FOREIGN KEY(world_id,actor_id) REFERENCES residents(world_id,actor_id),
  FOREIGN KEY(world_id,state_version) REFERENCES events(world_id,state_version) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY(world_id,actor_id,command_id) REFERENCES receipts(world_id,actor_id,command_id) DEFERRABLE INITIALLY DEFERRED);
INSERT INTO "visits" VALUES('foundation-01','a1','535838832c0f41b69772de8ba343dc45','garden',6,'2026-10-25T15:04:32.5849950+00:00',1,6);
INSERT INTO "visits" VALUES('foundation-01','a2','098129af864748c1929b802764e9ea10','garden',17,'2026-10-25T15:04:43.7680948+00:00',1,6);
INSERT INTO "visits" VALUES('foundation-01','a1','efb84e089dfa415090fa2b219f68ad67','garden',28,'2026-10-25T15:04:51.2531566+00:00',1,6);
CREATE TABLE worlds(
  id TEXT PRIMARY KEY CHECK(id='foundation-01'), scenario_id TEXT NOT NULL,
  rules_version TEXT NOT NULL,
  state_version INTEGER NOT NULL CHECK(typeof(state_version)='integer' AND state_version>=0),
  issued_wood INTEGER NOT NULL CHECK(issued_wood=12), depot_wood INTEGER NOT NULL CHECK(depot_wood BETWEEN 0 AND 12),
  CHECK(scenario_id='consent-v1' AND rules_version='r6'));
INSERT INTO "worlds" VALUES('foundation-01','consent-v1','r6',34,12,12);
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
CREATE INDEX recent_mosaic_proposals_by_author ON mosaic_proposals(world_id,author_actor_id,state_version);
CREATE TRIGGER immutable_mosaic_proposal_update BEFORE UPDATE ON mosaic_proposals BEGIN SELECT RAISE(ABORT,'immutable mosaic proposal'); END;
CREATE TRIGGER immutable_mosaic_proposal_delete BEFORE DELETE ON mosaic_proposals BEGIN SELECT RAISE(ABORT,'immutable mosaic proposal'); END;
CREATE INDEX recent_mosaic_reviews_by_author ON mosaic_reviews(world_id,author_actor_id,state_version);
CREATE TRIGGER immutable_mosaic_review_update BEFORE UPDATE ON mosaic_reviews BEGIN SELECT RAISE(ABORT,'immutable mosaic review'); END;
CREATE TRIGGER immutable_mosaic_review_delete BEFORE DELETE ON mosaic_reviews BEGIN SELECT RAISE(ABORT,'immutable mosaic review'); END;
DELETE FROM "sqlite_sequence";
INSERT INTO "sqlite_sequence" VALUES('events',35);
COMMIT;
