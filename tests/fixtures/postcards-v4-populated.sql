-- Source: completed ITER-0005 two-resident real-model acceptance world; only session hashes/expiry sanitized.
PRAGMA user_version=4;
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
INSERT INTO "events" VALUES(1,'foundation-01',0,'{"seq":1,"stateVersion":0,"commandId":null,"actorId":null,"type":"worldSeeded","quantity":12,"source":"ITER-0005 initial allocation"}');
INSERT INTO "events" VALUES(2,'foundation-01',1,'{"seq":2,"stateVersion":1,"commandId":"1e111991fc3640a09ece325719558c34","actorId":"a1","type":"moved","position":[1,2]}');
INSERT INTO "events" VALUES(3,'foundation-01',2,'{"seq":3,"stateVersion":2,"commandId":"03b74b0e958d4a709013e87410897e57","actorId":"a1","type":"moved","position":[1,3]}');
INSERT INTO "events" VALUES(4,'foundation-01',3,'{"seq":4,"stateVersion":3,"commandId":"86a8793d992f47adbb89ec807e7ccbc8","actorId":"a1","type":"moved","position":[1,4]}');
INSERT INTO "events" VALUES(5,'foundation-01',4,'{"seq":5,"stateVersion":4,"commandId":"e32df34143f54f8484e52b9a50ae36ba","actorId":"a1","type":"moved","position":[1,5]}');
INSERT INTO "events" VALUES(6,'foundation-01',5,'{"seq":6,"stateVersion":5,"commandId":"310610252e4449d89d64db1fcf7be6cf","actorId":"a1","type":"moved","position":[1,6]}');
INSERT INTO "events" VALUES(7,'foundation-01',6,'{"seq":7,"stateVersion":6,"commandId":"37db3125e89c4691896f6fd101b0733e","actorId":"a1","type":"visited","activityId":"garden","position":[1,6]}');
INSERT INTO "events" VALUES(8,'foundation-01',7,'{"seq":8,"type":"postcard_shared","actorId":"a1","activityId":"garden","authorActorId":"a1","commandId":"c7bf16cceb94426d8af40e70fd9d8896","visitCommandId":"37db3125e89c4691896f6fd101b0733e","text":"\u613F\u6765\u5230\u9759\u8C27\u82B1\u56ED\u7684\u4F60\uFF0C\u80FD\u6682\u7F13\u811A\u6B65\uFF0C\u7ED9\u81EA\u5DF1\u4E00\u70B9\u4ECE\u5BB9\u7684\u65F6\u95F4\u3002\u795D\u4F60\u6563\u6B65\u6109\u5FEB\uFF0C\u5F52\u9014\u5B89\u7136\u3002","stateVersion":7,"sharedAtUtc":"2026-10-25T13:15:56.0839594\u002B00:00","position":[1,6]}');
INSERT INTO "events" VALUES(9,'foundation-01',8,'{"seq":9,"stateVersion":8,"commandId":"ee65da5322fe43b6995ed613d4de6248","actorId":"a1","type":"moved","position":[1,5]}');
INSERT INTO "events" VALUES(10,'foundation-01',9,'{"seq":10,"stateVersion":9,"commandId":"1d6e5765c1e44038a5f531e18044ccb5","actorId":"a1","type":"moved","position":[1,4]}');
INSERT INTO "events" VALUES(11,'foundation-01',10,'{"seq":11,"stateVersion":10,"commandId":"ca2b40d3c47a43ed906a97f381d28443","actorId":"a1","type":"moved","position":[1,3]}');
INSERT INTO "events" VALUES(12,'foundation-01',11,'{"seq":12,"stateVersion":11,"commandId":"26a983b214a047f9901204a6e6fcf350","actorId":"a1","type":"moved","position":[1,2]}');
INSERT INTO "events" VALUES(13,'foundation-01',12,'{"seq":13,"stateVersion":12,"commandId":"d0daced9ebe448df9c48e139fb3d8f51","actorId":"a1","type":"moved","position":[1,1]}');
INSERT INTO "events" VALUES(14,'foundation-01',13,'{"seq":14,"stateVersion":13,"commandId":"7348a90cd84e43a8a8ad6da2bc376ec9","actorId":"a2","type":"moved","position":[1,3]}');
INSERT INTO "events" VALUES(15,'foundation-01',14,'{"seq":15,"stateVersion":14,"commandId":"ee69b44ba448415e884ef89f96f97973","actorId":"a2","type":"moved","position":[1,4]}');
INSERT INTO "events" VALUES(16,'foundation-01',15,'{"seq":16,"stateVersion":15,"commandId":"5db80023efdb451d9512f71c77e36961","actorId":"a2","type":"moved","position":[1,5]}');
INSERT INTO "events" VALUES(17,'foundation-01',16,'{"seq":17,"stateVersion":16,"commandId":"a4c670da34a845ffb634f478d0ddc056","actorId":"a2","type":"moved","position":[1,6]}');
INSERT INTO "events" VALUES(18,'foundation-01',17,'{"seq":18,"stateVersion":17,"commandId":"3b4ef7a2eb4b495e912675060b3b77ef","actorId":"a2","type":"visited","activityId":"garden","position":[1,6]}');
INSERT INTO "events" VALUES(19,'foundation-01',18,'{"seq":19,"type":"postcard_shared","actorId":"a2","activityId":"garden","authorActorId":"a2","commandId":"82c04f55988d41ef9c316f5bc0148734","visitCommandId":"3b4ef7a2eb4b495e912675060b3b77ef","text":"\u8C22\u8C22\u4F60\u5173\u4E8E\u4ECE\u5BB9\u4E0E\u5F52\u9014\u5B89\u7136\u7684\u795D\u613F\u3002\u613F\u8FD9\u4EFD\u6E29\u67D4\u4E5F\u4F20\u7ED9\u540E\u6765\u8005\uFF1A\u7ED9\u81EA\u5DF1\u4E00\u70B9\u65F6\u95F4\uFF0C\u6162\u6162\u8D70\uFF0C\u5E73\u5B89\u5F52\u3002","stateVersion":18,"sharedAtUtc":"2026-10-25T13:16:06.0847302\u002B00:00","position":[1,6]}');
INSERT INTO "events" VALUES(20,'foundation-01',19,'{"seq":20,"stateVersion":19,"commandId":"e6a2d8a0bfb348008d6844777bafb066","actorId":"a2","type":"moved","position":[1,5]}');
INSERT INTO "events" VALUES(21,'foundation-01',20,'{"seq":21,"stateVersion":20,"commandId":"b175901cf7d745418abe46ea857b154f","actorId":"a2","type":"moved","position":[1,4]}');
INSERT INTO "events" VALUES(22,'foundation-01',21,'{"seq":22,"stateVersion":21,"commandId":"9af5f636efa74da782e3fe9f1485e5d6","actorId":"a2","type":"moved","position":[1,3]}');
INSERT INTO "events" VALUES(23,'foundation-01',22,'{"seq":23,"stateVersion":22,"commandId":"a8497d3c7e234f4aa54ae03470f1b3ba","actorId":"a2","type":"moved","position":[1,2]}');
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
INSERT INTO "postcards" VALUES('foundation-01','a1','c7bf16cceb94426d8af40e70fd9d8896','37db3125e89c4691896f6fd101b0733e','garden','愿来到静谧花园的你，能暂缓脚步，给自己一点从容的时间。祝你散步愉快，归途安然。',7,'2026-10-25T13:15:56.0839594+00:00',1,6);
INSERT INTO "postcards" VALUES('foundation-01','a2','82c04f55988d41ef9c316f5bc0148734','3b4ef7a2eb4b495e912675060b3b77ef','garden','谢谢你关于从容与归途安然的祝愿。愿这份温柔也传给后来者：给自己一点时间，慢慢走，平安归。',18,'2026-10-25T13:16:06.0847302+00:00',1,6);
CREATE TABLE receipts(
  world_id TEXT NOT NULL, actor_id TEXT NOT NULL, command_id TEXT NOT NULL,
  request_hash TEXT NOT NULL, status_code INTEGER NOT NULL, result_json TEXT NOT NULL,
  PRIMARY KEY(world_id,actor_id,command_id), FOREIGN KEY(world_id,actor_id) REFERENCES residents(world_id,actor_id));
INSERT INTO "receipts" VALUES('foundation-01','a1','1e111991fc3640a09ece325719558c34','46CDB6186E92C10EFE8913AC805391F5D108200050BFF8D2ACBF7AB2664491C1',200,'{"schemaVersion":1,"rulesVersion":"r4","stateVersion":1,"commandId":"1e111991fc3640a09ece325719558c34","identity":{"operatorId":"local-operator","actorId":"a1","sessionId":"s357c722477b1468b848fedb8d77b9a44"},"eventCursor":2,"error":null,"status":"committed","result":{"action":"move","position":[1,2]}}');
INSERT INTO "receipts" VALUES('foundation-01','a1','03b74b0e958d4a709013e87410897e57','051D9A79E6926C2558DD4C74D40D29ECB960171F51B3EBD0DE89EB58292645E9',200,'{"schemaVersion":1,"rulesVersion":"r4","stateVersion":2,"commandId":"03b74b0e958d4a709013e87410897e57","identity":{"operatorId":"local-operator","actorId":"a1","sessionId":"s357c722477b1468b848fedb8d77b9a44"},"eventCursor":3,"error":null,"status":"committed","result":{"action":"move","position":[1,3]}}');
INSERT INTO "receipts" VALUES('foundation-01','a1','86a8793d992f47adbb89ec807e7ccbc8','B5C024207661A7A96D36A848737036126AD8B9F852DCF95E00CECFAE852B4FE9',200,'{"schemaVersion":1,"rulesVersion":"r4","stateVersion":3,"commandId":"86a8793d992f47adbb89ec807e7ccbc8","identity":{"operatorId":"local-operator","actorId":"a1","sessionId":"s357c722477b1468b848fedb8d77b9a44"},"eventCursor":4,"error":null,"status":"committed","result":{"action":"move","position":[1,4]}}');
INSERT INTO "receipts" VALUES('foundation-01','a1','e32df34143f54f8484e52b9a50ae36ba','94DFDDE95F00B2F7B43377186524BB89F1072C1F44EEE011B0A47AEBCFBDF4F0',200,'{"schemaVersion":1,"rulesVersion":"r4","stateVersion":4,"commandId":"e32df34143f54f8484e52b9a50ae36ba","identity":{"operatorId":"local-operator","actorId":"a1","sessionId":"s357c722477b1468b848fedb8d77b9a44"},"eventCursor":5,"error":null,"status":"committed","result":{"action":"move","position":[1,5]}}');
INSERT INTO "receipts" VALUES('foundation-01','a1','310610252e4449d89d64db1fcf7be6cf','959C4B9B947934DA368B9AEAA246BAC243717ED9F4A0C0300C710B2BD6668953',200,'{"schemaVersion":1,"rulesVersion":"r4","stateVersion":5,"commandId":"310610252e4449d89d64db1fcf7be6cf","identity":{"operatorId":"local-operator","actorId":"a1","sessionId":"s357c722477b1468b848fedb8d77b9a44"},"eventCursor":6,"error":null,"status":"committed","result":{"action":"move","position":[1,6]}}');
INSERT INTO "receipts" VALUES('foundation-01','a1','37db3125e89c4691896f6fd101b0733e','4ACB31734887B08092E4C3C7165908B0B2A229B3984405D0D5F78221B59101BE',200,'{"schemaVersion":1,"rulesVersion":"r4","stateVersion":6,"commandId":"37db3125e89c4691896f6fd101b0733e","identity":{"operatorId":"local-operator","actorId":"a1","sessionId":"s357c722477b1468b848fedb8d77b9a44"},"eventCursor":7,"error":null,"status":"committed","result":{"action":"visit","activityId":"garden","position":[1,6],"visitedAtUtc":"2026-10-25T13:15:56.0749449\u002B00:00"}}');
INSERT INTO "receipts" VALUES('foundation-01','a1','c7bf16cceb94426d8af40e70fd9d8896','2F8AE7EA84C1B0860ADF5FA6C7840F914F10C4112C0540CD973AB57C84472862',200,'{"schemaVersion":1,"rulesVersion":"r4","stateVersion":7,"commandId":"c7bf16cceb94426d8af40e70fd9d8896","identity":{"operatorId":"local-operator","actorId":"a1","sessionId":"s357c722477b1468b848fedb8d77b9a44"},"eventCursor":8,"error":null,"status":"committed","result":{"action":"postcard","activityId":"garden","authorActorId":"a1","commandId":"c7bf16cceb94426d8af40e70fd9d8896","visitCommandId":"37db3125e89c4691896f6fd101b0733e","text":"\u613F\u6765\u5230\u9759\u8C27\u82B1\u56ED\u7684\u4F60\uFF0C\u80FD\u6682\u7F13\u811A\u6B65\uFF0C\u7ED9\u81EA\u5DF1\u4E00\u70B9\u4ECE\u5BB9\u7684\u65F6\u95F4\u3002\u795D\u4F60\u6563\u6B65\u6109\u5FEB\uFF0C\u5F52\u9014\u5B89\u7136\u3002","stateVersion":7,"sharedAtUtc":"2026-10-25T13:15:56.0839594\u002B00:00","position":[1,6]}}');
INSERT INTO "receipts" VALUES('foundation-01','a1','ee65da5322fe43b6995ed613d4de6248','0598FE783CE34F82B74DD0E511DC9673050DC52F392B4FF09169EBF44BB69EE0',200,'{"schemaVersion":1,"rulesVersion":"r4","stateVersion":8,"commandId":"ee65da5322fe43b6995ed613d4de6248","identity":{"operatorId":"local-operator","actorId":"a1","sessionId":"s357c722477b1468b848fedb8d77b9a44"},"eventCursor":9,"error":null,"status":"committed","result":{"action":"move","position":[1,5]}}');
INSERT INTO "receipts" VALUES('foundation-01','a1','1d6e5765c1e44038a5f531e18044ccb5','0F897F30D751F62B87FE1F827933B857AAE2B1808B888BA03F7365A3773EAF49',200,'{"schemaVersion":1,"rulesVersion":"r4","stateVersion":9,"commandId":"1d6e5765c1e44038a5f531e18044ccb5","identity":{"operatorId":"local-operator","actorId":"a1","sessionId":"s357c722477b1468b848fedb8d77b9a44"},"eventCursor":10,"error":null,"status":"committed","result":{"action":"move","position":[1,4]}}');
INSERT INTO "receipts" VALUES('foundation-01','a1','ca2b40d3c47a43ed906a97f381d28443','89DAB47F623E6CBBC1330125219590E68CC6DE8E08DE8989E85A65CBA814B2B9',200,'{"schemaVersion":1,"rulesVersion":"r4","stateVersion":10,"commandId":"ca2b40d3c47a43ed906a97f381d28443","identity":{"operatorId":"local-operator","actorId":"a1","sessionId":"s357c722477b1468b848fedb8d77b9a44"},"eventCursor":11,"error":null,"status":"committed","result":{"action":"move","position":[1,3]}}');
INSERT INTO "receipts" VALUES('foundation-01','a1','26a983b214a047f9901204a6e6fcf350','F312E73AB5EDF3A5618DA572B045186FC86E6FEBB6E3EB264134D6C55F11E677',200,'{"schemaVersion":1,"rulesVersion":"r4","stateVersion":11,"commandId":"26a983b214a047f9901204a6e6fcf350","identity":{"operatorId":"local-operator","actorId":"a1","sessionId":"s357c722477b1468b848fedb8d77b9a44"},"eventCursor":12,"error":null,"status":"committed","result":{"action":"move","position":[1,2]}}');
INSERT INTO "receipts" VALUES('foundation-01','a1','d0daced9ebe448df9c48e139fb3d8f51','2E4A78411D77045E8A93BDE02C89164D88A44462821C33E506F041360D91F0EC',200,'{"schemaVersion":1,"rulesVersion":"r4","stateVersion":12,"commandId":"d0daced9ebe448df9c48e139fb3d8f51","identity":{"operatorId":"local-operator","actorId":"a1","sessionId":"s357c722477b1468b848fedb8d77b9a44"},"eventCursor":13,"error":null,"status":"committed","result":{"action":"move","position":[1,1]}}');
INSERT INTO "receipts" VALUES('foundation-01','a2','7348a90cd84e43a8a8ad6da2bc376ec9','142E2D3B67137F6E3896D4C321C8AB9CC18544916E4B7385B59FE64E1A4957DA',200,'{"schemaVersion":1,"rulesVersion":"r4","stateVersion":13,"commandId":"7348a90cd84e43a8a8ad6da2bc376ec9","identity":{"operatorId":"local-operator","actorId":"a2","sessionId":"sc8b4026449bc4460b29c8d06654ccf7a"},"eventCursor":14,"error":null,"status":"committed","result":{"action":"move","position":[1,3]}}');
INSERT INTO "receipts" VALUES('foundation-01','a2','ee69b44ba448415e884ef89f96f97973','034C085DCB5561589E688E23DFD931896921499FC3B3CD35319AA5A7A4806782',200,'{"schemaVersion":1,"rulesVersion":"r4","stateVersion":14,"commandId":"ee69b44ba448415e884ef89f96f97973","identity":{"operatorId":"local-operator","actorId":"a2","sessionId":"sc8b4026449bc4460b29c8d06654ccf7a"},"eventCursor":15,"error":null,"status":"committed","result":{"action":"move","position":[1,4]}}');
INSERT INTO "receipts" VALUES('foundation-01','a2','5db80023efdb451d9512f71c77e36961','42E29E79B8563DB043D27AAABFFE4508490B54FDF1A8889EF218A68DE95629E0',200,'{"schemaVersion":1,"rulesVersion":"r4","stateVersion":15,"commandId":"5db80023efdb451d9512f71c77e36961","identity":{"operatorId":"local-operator","actorId":"a2","sessionId":"sc8b4026449bc4460b29c8d06654ccf7a"},"eventCursor":16,"error":null,"status":"committed","result":{"action":"move","position":[1,5]}}');
INSERT INTO "receipts" VALUES('foundation-01','a2','a4c670da34a845ffb634f478d0ddc056','F83440BD10C263B237C78E61526884FCB4C1DEE7EB6F5CEEB07D185131A40EF2',200,'{"schemaVersion":1,"rulesVersion":"r4","stateVersion":16,"commandId":"a4c670da34a845ffb634f478d0ddc056","identity":{"operatorId":"local-operator","actorId":"a2","sessionId":"sc8b4026449bc4460b29c8d06654ccf7a"},"eventCursor":17,"error":null,"status":"committed","result":{"action":"move","position":[1,6]}}');
INSERT INTO "receipts" VALUES('foundation-01','a2','3b4ef7a2eb4b495e912675060b3b77ef','08B845BDECD5806C610D4E5BC267A3EFEAB0DA3203DFDD9E128963379A53E360',200,'{"schemaVersion":1,"rulesVersion":"r4","stateVersion":17,"commandId":"3b4ef7a2eb4b495e912675060b3b77ef","identity":{"operatorId":"local-operator","actorId":"a2","sessionId":"sc8b4026449bc4460b29c8d06654ccf7a"},"eventCursor":18,"error":null,"status":"committed","result":{"action":"visit","activityId":"garden","position":[1,6],"visitedAtUtc":"2026-10-25T13:16:06.0790677\u002B00:00"}}');
INSERT INTO "receipts" VALUES('foundation-01','a2','82c04f55988d41ef9c316f5bc0148734','6AC130C48032B05041FEC3B4D90C053E01227F8C9D2444A63FAA709FB4A28CB1',200,'{"schemaVersion":1,"rulesVersion":"r4","stateVersion":18,"commandId":"82c04f55988d41ef9c316f5bc0148734","identity":{"operatorId":"local-operator","actorId":"a2","sessionId":"sc8b4026449bc4460b29c8d06654ccf7a"},"eventCursor":19,"error":null,"status":"committed","result":{"action":"postcard","activityId":"garden","authorActorId":"a2","commandId":"82c04f55988d41ef9c316f5bc0148734","visitCommandId":"3b4ef7a2eb4b495e912675060b3b77ef","text":"\u8C22\u8C22\u4F60\u5173\u4E8E\u4ECE\u5BB9\u4E0E\u5F52\u9014\u5B89\u7136\u7684\u795D\u613F\u3002\u613F\u8FD9\u4EFD\u6E29\u67D4\u4E5F\u4F20\u7ED9\u540E\u6765\u8005\uFF1A\u7ED9\u81EA\u5DF1\u4E00\u70B9\u65F6\u95F4\uFF0C\u6162\u6162\u8D70\uFF0C\u5E73\u5B89\u5F52\u3002","stateVersion":18,"sharedAtUtc":"2026-10-25T13:16:06.0847302\u002B00:00","position":[1,6]}}');
INSERT INTO "receipts" VALUES('foundation-01','a2','e6a2d8a0bfb348008d6844777bafb066','9A009A9825363ADBFF70D54090DFFC24253F7FA93090EC6CB03701D2EE93E50C',200,'{"schemaVersion":1,"rulesVersion":"r4","stateVersion":19,"commandId":"e6a2d8a0bfb348008d6844777bafb066","identity":{"operatorId":"local-operator","actorId":"a2","sessionId":"sc8b4026449bc4460b29c8d06654ccf7a"},"eventCursor":20,"error":null,"status":"committed","result":{"action":"move","position":[1,5]}}');
INSERT INTO "receipts" VALUES('foundation-01','a2','b175901cf7d745418abe46ea857b154f','83B09FC8D5220FE5D7B4F537C0806B40673EEAE9A9B26F77B6DA4F7170DEBCE2',200,'{"schemaVersion":1,"rulesVersion":"r4","stateVersion":20,"commandId":"b175901cf7d745418abe46ea857b154f","identity":{"operatorId":"local-operator","actorId":"a2","sessionId":"sc8b4026449bc4460b29c8d06654ccf7a"},"eventCursor":21,"error":null,"status":"committed","result":{"action":"move","position":[1,4]}}');
INSERT INTO "receipts" VALUES('foundation-01','a2','9af5f636efa74da782e3fe9f1485e5d6','480B8F7BA15C396EC198A8FE48F2302B5A2DD0710027AEE7EEA9D2D2D3443131',200,'{"schemaVersion":1,"rulesVersion":"r4","stateVersion":21,"commandId":"9af5f636efa74da782e3fe9f1485e5d6","identity":{"operatorId":"local-operator","actorId":"a2","sessionId":"sc8b4026449bc4460b29c8d06654ccf7a"},"eventCursor":22,"error":null,"status":"committed","result":{"action":"move","position":[1,3]}}');
INSERT INTO "receipts" VALUES('foundation-01','a2','a8497d3c7e234f4aa54ae03470f1b3ba','B6BEF8FB28F9C6777C40DDA6755ACE417EC6FC466CDEB769E5CF1ADB8697CEBF',200,'{"schemaVersion":1,"rulesVersion":"r4","stateVersion":22,"commandId":"a8497d3c7e234f4aa54ae03470f1b3ba","identity":{"operatorId":"local-operator","actorId":"a2","sessionId":"sc8b4026449bc4460b29c8d06654ccf7a"},"eventCursor":23,"error":null,"status":"committed","result":{"action":"move","position":[1,2]}}');
CREATE TABLE recipes(
  id TEXT PRIMARY KEY, definition_id TEXT NOT NULL, definition_version INTEGER NOT NULL,
  rules_version TEXT NOT NULL, wood_cost INTEGER NOT NULL CHECK(wood_cost>0));
INSERT INTO "recipes" VALUES('platform.v1','platform',1,'r4',3);
INSERT INTO "recipes" VALUES('bridge.v1','bridge',1,'r4',3);
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
INSERT INTO "sessions" VALUES('s357c722477b1468b848fedb8d77b9a44','foundation-01','a1','63AC3A91052C814F76CF24182EA0508D635E3D893B88E1B9D647F1B900EE2D7C',4102444800000,0);
INSERT INTO "sessions" VALUES('sc8b4026449bc4460b29c8d06654ccf7a','foundation-01','a2','9BCAF55EC60E6B7427D23E124E27F5AAD891F9585D48D4498A2314B7AB11ABB4',4102444800000,0);
CREATE TABLE visits(
  world_id TEXT NOT NULL, actor_id TEXT NOT NULL, command_id TEXT NOT NULL,
  activity_id TEXT NOT NULL, state_version INTEGER NOT NULL,
  visited_at_utc TEXT NOT NULL,
  x INTEGER NOT NULL CHECK(x BETWEEN 0 AND 7), y INTEGER NOT NULL CHECK(y BETWEEN 0 AND 7),
  PRIMARY KEY(world_id,actor_id,command_id), UNIQUE(world_id,state_version),
  FOREIGN KEY(world_id,actor_id) REFERENCES residents(world_id,actor_id),
  FOREIGN KEY(world_id,state_version) REFERENCES events(world_id,state_version) DEFERRABLE INITIALLY DEFERRED,
  FOREIGN KEY(world_id,actor_id,command_id) REFERENCES receipts(world_id,actor_id,command_id) DEFERRABLE INITIALLY DEFERRED);
INSERT INTO "visits" VALUES('foundation-01','a1','37db3125e89c4691896f6fd101b0733e','garden',6,'2026-10-25T13:15:56.0749449+00:00',1,6);
INSERT INTO "visits" VALUES('foundation-01','a2','3b4ef7a2eb4b495e912675060b3b77ef','garden',17,'2026-10-25T13:16:06.0790677+00:00',1,6);
CREATE TABLE worlds(
  id TEXT PRIMARY KEY CHECK(id='foundation-01'), scenario_id TEXT NOT NULL,
  rules_version TEXT NOT NULL,
  state_version INTEGER NOT NULL CHECK(typeof(state_version)='integer' AND state_version>=0),
  issued_wood INTEGER NOT NULL CHECK(issued_wood=12), depot_wood INTEGER NOT NULL CHECK(depot_wood BETWEEN 0 AND 12),
  CHECK(scenario_id='postcards-v1' AND rules_version='r4'));
INSERT INTO "worlds" VALUES('foundation-01','postcards-v1','r4',22,12,12);
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
DELETE FROM "sqlite_sequence";
INSERT INTO "sqlite_sequence" VALUES('events',23);
COMMIT;
