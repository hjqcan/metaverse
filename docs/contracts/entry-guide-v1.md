# 当代入驻导览：ITER-0009

2026-10-26，实施前冻结。基于主分支新增 C13—C17，先让居民知道当前世界实际能去哪里、已有设施能否使用、材料来自哪里。这是 EXP-0002 的读取与入驻前置能力，不宣称共享工坊、自动化、动态注册或防垄断机制已实现。

原 r1—r6、schema、动作和账本不变。observation 同一只读事务追加 `entryGuide`：

- `version:1`、`stateVersion`、`actorId`、`position` 必须与本次观察一致。
- `sharedBridges:[{entityId,ownerActorId,position}]` 仅含已建桥段，记录建设者；建造菜单不是已有服务。
- `places:[{id,label,position,activityId,reachable,walkingSteps,route,bridgeEntityIds}]`。有活动场景使用原三地点；r1/r2 使用原目标 `id=goal,label=目标地,activityId=null`。当前位置出发，以现有墙／未铺桥水面为阻挡作最短步行路径，邻居顺序右、下、左、上；route 不含起点、含终点。当前位置即目的地为0步空路径；不可达为false/null/空路径/空桥ID。bridgeEntityIds 按路径首次出现顺序列出实际使用的桥实体ID，不因桥数量大于0就声称已通行。
- `materials:{publicWood,ownWood,depotPosition:[1,1]}` 只展示公共储备与本人库存，不公开同伴库存、不发放资源、不预留材料。
- `participation:{walkWoodCost:0,visitSupported,postcardSupported,mosaicSupported,foreignMosaicNeedsConsent}` 对应原场景能力；功能支持与地点当前可达分开。

浏览器连接后在创作区上方展示当前居民、观察版本、已有桥段及作者、各地点能否到达和步数、有限材料、零木材活动与创作条件。查看路线／选择地点仅更新本地选项，不移动、到访或领取材料；不可达仍能查看原因。观察失败标为上次状态并停止导览操作；身份切换清除旧身份内容。旧服务无字段时隐藏导览，原操作继续。390px 可读且无横向溢出。

新任务传给模型的公开观察可携带同一个导览，只按明确字段白名单复制；不携带 session 或凭据。旧服务和已有持久任务保持兼容；导览是观察时快照，不替代服务器动作确认。

验收使用实际 HTTP 与 Chrome：无桥／一段桥／完整通路，另一居民先建桥后 a2 首次读取和零木材往返，旧库不变、身份和路径合法、公共储备耗尽后的真实限制与零材料活动、重启、导览无写入、旧服务回退、窄屏。固定程序活动与模型调用分开；本轮真实居民模型调用预算0。构建和回归通过后按用户明确要求提交并正常推送 main，不强制推送，不新建工作树。
