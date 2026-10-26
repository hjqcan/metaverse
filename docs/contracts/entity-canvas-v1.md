# 原平台地画 · entity-canvas-v1

2026-10-26。ITER-0025实施契约，已完成本轮本机实现及独立验收，见[结果](../iterations/ITER-0025-results.md)。采用[研究17](../research/2026-10-26-continuous/17-space-after-continuous-materials.md)的唯一平台地画实验。以下为本轮局部规则，不新增用户已确认的完整产权、土地或治理制度。

## 目标与采用

只在已合法采用持续材料政策的原r10／存储11实例离线执行：

```text
dotnet World.Server.dll adopt-entity-canvas --instance <原实例> --entity <原平台entityId>
```

旧服务必须已退出且自动重启关闭，使用原规范数据目录及材料计时锁。采用原子追加一条`entityCanvasAdopted`环境事件、空白5×5格和地画元数据，存储11升12；r10、instance、原坐标和动作语义保持。不初始化世界、不移动或重造实体、不发木材、不修改来源相位／预约／手记。不因为采用推进服务时间。原平台必须是本实例platform/1、r10、含木3；同实例仅开放这一平台。重复同一采用只返回已采用；换实例／目标、缺损或未知采用拒绝且保留原库。

本轮自然基线：ITER-0024独立连续史`w_15ced6889f624d8da8a3d2129ba26874`，state754、755事件、736回执、一桥五平台、两手记。目标`e926486325c2c4e3e924610139ee26711`，a2建造、[24,7]。目标必须从实际基线复核，不能凭位置换ID。当前a1_alias库存0，但与a1同声明控制组；a2为declared-late，不宣称已核实现实独立身份。

未采用的r1—r10世界行为保持。存储12仅支持原r10持续材料＋地画合法组合；旧服务冷启动拒绝。此处不声称能终止已运行的旧进程。旧客户端不具备新绘制UI，原其他动作及其pending按原协议继续；新绘制pending由新客户端处理，旧程序保留并暂停未知记录。

## 观察

`GET /v1/worlds/foundation-01/observation`只在采用后增加`entityCanvas`：

- `capability: "entity-canvas-v1"`、`version: 1`、`width: 5`、`height: 5`、`reach: 1.6`、`maxPatchCells: 8`、`paintRule: "unowned-or-author-v1"`。
- `target`沿用公开实体字段：entityId、definitionId、definitionVersion、rulesVersion、ownerActorId、position、embodiedWood。平台建造者与格子作者分开。
- `adoption`为`{worldInstanceId,stateVersion,eventCursor}`，对应原采用事件。
- `palette`复用原6色板（blank、leaf、river、sun、rose、ink）及id／label／hex。
- `revision`从0开始，每次成功绘制加1；`editCount`等于成功修改总数。`recentEdits`只含最近50次、按revision升序，不是完整历史。
- `cells`恰好25格，按y/x排序；每格为`{x,y,color,authorActorId,commandId,stateVersion}`。初始blank且后三项null；画成blank也保留最后作者、命令与状态版本。

观察内的采用、当前格和最近记录在同一读取事务。未知／不完整能力不能授权新绘制；它不使旧成功回执自动失效。

## 绘制动作与规则

沿用认证、`World-Instance-Id`、r10、原命令账本和可选`actor-state-v1`。新动作精确字段：

```json
{"type":"paint_entity_canvas","entityId":"原平台entityId","capabilityVersion":1,"expectedCanvasRevision":0,"patch":[{"x":1,"y":1,"color":"river"}]}
```

`expectedCanvasRevision`必须非负整数，capabilityVersion只接受整数1。patch包含1—8个互异整数格坐标0…4及已知颜色，规范按y/x排序；拒绝额外字段、重复格或类型错误。原mosaic动作的canonical/hash语义完全不变。

居民须在原平台中心1.6米内，当前位置可走且到中心无障碍。当前地画revision必须等于请求基准；每格必须无人署名或最后作者为本人actorId；任何一格颜色未变化则拒绝整批。不能依据同operator、平台建造者或blank颜色覆盖他人格。没有提议、审批、清除署名、自动换空格或自动采用新revision。

业务拒绝写原持久回执：未采用`422 ENTITY_CANVAS_UNAVAILABLE`；非开放目标`404 CANVAS_TARGET_UNAVAILABLE`；不在现场`422 UNREACHABLE`；旧基准`409 CANVAS_REVISION_MISMATCH`；他人格`409 CANVAS_CONSENT_REQUIRED`；未变化`422 CANVAS_UNCHANGED`。语法错误沿原`400 INVALID_REQUEST`。既有原回执优先，即使目前条件改变也不改为成功。

成功在同事务更新全部格、revision、不可变edit、环境之外的居民事件和回执。绘制不改库存或资源账、不新增实体；正常后台来源生产另记。严格版本与actor-state的原并发语义不放宽；地画revision是额外共享对象前置条件。

## 完成事实与原历史读取

`result`为`action:"paint_entity_canvas"`及以下完整edit字段：entityId、capabilityVersion(1)、authorActorId、operatorId、commandId、baseRevision、revision、patch、stateVersion、eventCursor、paintedAtUtc、position、inventoryWood。revision=baseRevision+1，位置／库存是提交时真实值。事件在这些字段外带`type:"entityCanvasPainted"`、seq=eventCursor、actorId=authorActorId。

另有认证只读接口：

```text
GET /v1/worlds/foundation-01/entities/{entityId}/canvas/edits/{authorActorId}/{commandId}
```

响应为标准世界envelope加`edit`，返回完整不可变原edit；请求者可以读取公开他人edit。未采用／目标错误同上；原edit不存在为`404 CANVAS_EDIT_NOT_FOUND`。有instance响应头且在同一读取事务核对认证／原世界；不改变状态。不能以最近50条中没有找到代替此查询。无新增历史分页或搜索系统。

完成要核对原请求／回执、上述不可变原edit及原event三方，身份、目标、规范patch、基准／新revision、状态版本／游标全部一致。当前图可以后来被本人再次修改，不能因此否认原成功；当前颜色相同也不能凭空证明本次命令成功。

## 客户端与任务

Godot显示平台表面的已确认5×5图，点平台或现有侧栏入口打开网格；区分平台建造者、格子作者、当前已确认图和本地草图。编辑1—8格后明确提交，显示现场距离／冲突；别人修改后保留草图并要求新的明确输入，不自动改基准重发。观察只变地画、entities不变时仍刷新图面。纯表现色块不新增碰撞／资源。沿用已有键盘／点击行走和原恢复存储。

新绘制pending使用Godot记录version5；原动作仍用既有版本，新版读取兼容旧记录。保存原instance／actor／目标、能力绑定、原revision／patch／request/body。真实404允许原样重试；503、错世界或不完整事实保留pending。原成功丢响应先查原回执和原edit，绝不因当前图变了重画。未知版本旧客户端保留原文件暂停。

Python沿用`run_resident.py`和现有有界任务；明确`allowEntityCanvas:true`，单一目标的`entityCanvas:{entityId,expectedCanvasRevision,patch}`及target必须绑定真实原平台，其他采集／建造／转让／手记／材料预约权限不得混用。用户提供固定patch，本轮不加入模型自动绘画或自动选空格。先读当前图再创建第二份明确任务；执行器不会替原任务追新revision。

任务持久保留原起点、实例／居民、目标、patch／基准、预算及所有原命令；查询在I/O前扣额，首次观察、失败查询、原回执／edit／event核对均计入，恢复不补额。`facts.entityCanvasPainted`与完整`facts.entityCanvasEdit`分别记录本次确认事实，往返完成另计；当前图被后来修改不抹去事实。报告`world.entityCanvas`保留实际快照，显示本次edit、当前图和预算；报告导入只核对自身一致性，不认证在线世界。

## 验收范围

接续上述真实原世界，在指定原平台采用，a1_alias实际走到、画明确固定河流片段并返回，a2看到原图、到场在空格接绘并返回。核对原实体／建造者／木材、两手记、旧回执及材料账保持；正常来源生产单列。Godot实际三阶段图面和近场网格可操作、桌面／手机报告可读。零库存说法只归经观察核对的a1_alias；a2只称零支出。

必要回归覆盖：重复采用及提交前后失败、旧服务冷启动拒绝；同revision并发只一份成功；他人格混批原子拒绝、本人改色／擦白署名；成功丢响应后后来改画仍确认原edit，真实404／503及错证据保留原请求；超过最近50条仍按原引用查证；原r5/r6与r10材料／手记任务兼容。自检和独立验收分列；不复制运行库，完成测试清理临时程序与缓存。

25格仍可能被先占，本人重画不等于后来者永远有空间。本轮不加入覆盖审批、更多平台、拆除、扩图、自动化、开放注册或长期经济结论；无真人反馈时不声称好玩、被认可或形成社会关系。
