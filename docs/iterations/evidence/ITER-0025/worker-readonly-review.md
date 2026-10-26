# ITER-0025 报告接入只读审查

2026-10-26，构建 agent2。只读 `src/World.Server/wwwroot/entity-canvas-report.js` 和 `resident.js`；唯一写入本文件，未修改产品、启动服务或联网。以下是源码审查和只读 Node VM 反例，不是浏览器或独立在线验收。

审查指纹：

- `entity-canvas-report.js`: `2c02c65566e0daa556b2c105848b24a8158b003d9fedb68c2fa42a7027e78d16`
- `resident.js`: `ccb215d99232425ab1c41c3c3cde0ab5ba6a3e270857945e8a96058f253b4359`

输入为真实作者自检 `.local/iter0025/python/20261026T065216Z-072bdc/` 的报告。VM 执行地画模块及 resident 的 `validate` 函数所在前缀；与变更无关的 MaterialReport、EntityNoteReport 验证器为空桩，Mosaic/Consent 校验为占位，因此只对这里列明的地画及基础预算、步骤规则作结论。没有执行 DOM、加载页面或 HTTP 请求。

## 需要处理的问题

1. **P2：伪造累计查询/命令数仍通过校验并被评为一致。** `entity-canvas-report.js:50` 只要求 queries 是非负整数；`assess:67-77` 不检查预算与步骤。把真实首份已完成报告的 `budget.used.queries` 从 81 改为 0、`budget.used.commands` 从 77 改为 0，保留 77 条原步骤，`resident.validate` 仍通过，`assess` 返回 `{uses:true,verified:true,consistent:true}`。`resident.js:395,414-416` 的完成降级条件没有预算一致性；403-410 仅对超上限产生警告，0 值不触发。另将查询改为 801/800 仍返回同一 assessment，只会出现超预算警告而不降级完成标记。建议核对本任务命令数与步骤数、查询至少包含首次读取及确认所需读取、累计次数不超过限额；对合法“已确认绘画但未完成返程”的报告继续单独保留绘画事实，只将矛盾的整体完成/预算标记降级。公共报告没有完整查询日志，不应声称已复原所有失败查询，只能检查可观察的自洽关系。

2. **P2：原绘画事实仍依赖当前能力快照存在。** `entity-canvas-report.js:68-74` 强制 `capability(world.entityCanvas)`。删除真实首份报告的 `world.entityCanvas`，保留原目标、世界实体、`entityCanvasEdit` 和对应已提交步骤/完整 `entityCanvasEvidence`，结构校验通过，但 assessment 变为 `{uses:true,verified:false,consistent:false}`，render 把已经核对的原绘制降成“尚未确认”。当前 Python 在后来观察缺失或能力不完整时不会用其授权新绘制，但可凭原 receipt/edit/event 确认旧成功，公共快照也可不再带 entityCanvas；契约明确未知/不完整能力不使旧成功回执失效。建议将原事实核对绑定到原目标实体、原任务与 edit/step，当前图单独标为缺失/未知；不能用当前图缺失抹掉原绘画事实。

3. **P2：合法固定 patch 的输入顺序与报告验证规则不一致。** `entity-canvas-report.js:16-18,25-27` 把所有任务/动作 patch 都要求为 y/x 已排序；`assess:71,75` 又按数组原顺序对比 immutable edit。当前冻结 Python 接受不同输入顺序的互异格子，保留任务/请求原 patch，三方证据比较时才 canonicalize；服务器也规范化 edit。将真实首份报告中 `mission.goal.entityCanvas.patch` 和那一条 paint step 的 `action.patch` 同时反序，保留规范化的 edit/evidence，代表相同明确请求格子与合法成功结果，但 `resident.validate` 报“第39条步骤缺少原命令的前置模式或观察版本”。建议只对 immutable edit 要求规范顺序，对固定任务/动作校验互异坐标并做规范化语义比较，同时继续核对原 action 与原任务；或由协调者统一生产端规范化且考虑已经保存的原 pending 兼容。此项是两端规范化不一致，不能仅通过提示“前置模式错误”处理。

## 已核对正确的边界

| 输入 | validate | assess | 证据 |
| --- | --- | --- | --- |
| 真实 a1_alias 首次往返 | 通过 | verified/consistent=true | 77 条命令、81 次查询，原 edit rev1 |
| 本人后续擦白，原返程被 STALE 拒绝 | 通过 | verified/consistent=true | 任务仍 blocked，原 painted=true/returned=false |
| 他人续画 51 次，原 edit 已不在 recent50 | 通过 | verified/consistent=true | 当前 rev52，原 edit rev1，任务完成 |
| queries=4，三方核对后预算耗尽 | 通过 | verified/consistent=true | 原 edit state773/rev1，最后观察 endState772/rev0，任务仍 budget_exhausted |
| 仅伪造汇总 edit.commandId | 通过结构检查 | verified/consistent=false | 与原步骤不符；完成降级路径具备条件 |

`resident.js:151-157` 使用 `execution.appliedOnStateVersion` 验证结果版本，没有错误改回 `E+1`。真实首份报告第5步为 E759、S760、结果761，校验通过。queries=4 的快照旧于成功事实问题已经由协调者修正，本次审查没有再要求 edit 的版本小于最后观察；`render:90-92` 明确标注最后观察及快照早于本次确认。原 edit 核对没有搜索 recent50，也没有要求当前格颜色仍等于本次 patch。

伪造预算、缺失当前图、非规范输入顺序的反例是对真实报告的内存副本变更，未改写原报告文件。上述发现仅指这些指纹下的导入自洽性和显示条件；报告导入本身仍不认证在线世界。

## 修复后的补充复核

2026-10-26 07:07 UTC。协调者修复后，本次只读复核的指纹与其 `.local/iter0025/web-v1/manifest.json` 相符：

- `entity-canvas-report.js`: `3fd49e9b123500df4d3be3c470da17b9cfbcf91bce9d26b8b490e5bad56baa27`
- `resident.js`: `70db026e79198f9ff3a0207a6b1f7cb1f3f94eff9c4493e516e316fd78a962f8`

原三项反例已修复，首轮记录保留供追溯。补复核仍为相同只读 Node VM 范围，9/9 个检查符合预期：真实首份往返、本人后续重画、recent50 外原 edit、queries4 旧快照四个正常例均保持 `verified=true,budgetConsistent=true`；伪造 0 查询/0 命令以及 801/800 超额两例保留 `verified=true`，但 `budgetConsistent=false`；缺少当前图、原请求乱序两例恢复为 `verified=true,budgetConsistent=true`；仅伪造 edit.commandId 仍为 `verified=false,consistent=false`。

具体变化：

- `entity-canvas-report.js:78-82` 将预算一致性独立核对，`resident.js:383,396,415-417` 将它接入警告和整体完成降级，未擦除原绘画事实。查询检查为公共信息能支持的最低读取数量及上限，不宣称凭公共报告还原全部失败读取日志。
- `entity-canvas-report.js:69-76` 改为使用原 entities 内的同 ID 平台核对目标；当前图不再是原 edit 成立的前提。当前图存在时仍独立检查其世界、实体和观察版本。
- `entity-canvas-report.js:16-29,73,76` 接受原任务/动作的互异未排序 patch，将其规范化后与 immutable edit 比较，immutable edit 自身仍要求规范顺序；原 action 仍逐字段匹配原任务，未默默改草图。

另只读核对协调者提供的 `.local/iter0025/browser/2026-10-26T07-05-06-898Z/results.json`：作者 Chrome 152.0.7977.82 记录 `passed=true,testsRun=19,errors=[],worldRequests=[]`，包含本三项回归及手机网格检查。没有重新运行浏览器，也不将作者浏览器记录或本次 VM 复核称作独立在线验收。Python 作者测试单文件由协调者为动态基线可复现性接管修改，本次审查未改动 Python 产品或测试。

## 默认验收入口只读审查（等待默认实跑结果）

2026-10-26 07:11 UTC。按协调者新范围，只读检查默认基线、动态 Python 任务和浏览器入口；未重跑作者套件。当前指纹：

- `tests/entity_canvas_api.py`: `a45cf49af2435192459ef26a7570373a708a7e96f146b5680083d4e8da6d966c`
- `tests/entity_canvas_mission_api.py`: `af23dc157e0ceec8e0781cb6414543fcc8e4d5221ad17a817f02a2a6c650b237`
- `tests/browser/entity-canvas-resident.mjs`: `0cf6304cdfa6be5f70b8ca8555833526bb7403972e7da2128728afaa7602375c`

默认生成链静态自洽：`entity_canvas_api.baseline:61-87` 未设置外部基线时调用既有实际命令基线，采用持续来源，实际预约/领取3木、在[24,7]建平台、返回[26,17]，目标取原 build receipt 的 entityId；没有硬编码旧 QA 目录。外部基线是显式环境输入，并要求 ENTITY_CANVAS_ENTITY_ID。Python `setUpClass:58-65` 在任何测试前覆盖 TARGET/INSTANCE；`mission:43-46` 将 fixture 中的旧 entityId 替换为当前实际目标。库存来自每个副本的原 residents 表，完成和资源守恒核对均用该初值；损坏 before 反例使用 `(initial+1)%13`，不会因默认 a2 库存0而误改成原值。固定 patch 不被改写。浏览器入口未提供 REPORT_DIR 时选择实际生成 test01、04、05、07 四组报告，按本次 Evidence 路径读取同一批输出，未回退旧目录；未排序 patch 回归同时改变原 goal/action，保持规范 edit，和已复核的语义一致。

临时体积：CanvasWorld 复制 DB/WAL/SHM/access 到私有 staging 并只在 staging checkpoint，正常构造后删除 staging；运行库始终复用传入 DLL，没有按候选复制程序目录。Python 测试注册 `addCleanup(world.stop)`，正常和 unittest 测试失败路径会停止候选；默认基线用 finally 停止其候选。浏览器正常路径在 finally 关闭 Chrome 和自己启动的静态服务。

**P2：浏览器默认报告生成器超时会终止 Python 父进程，却不清理它启动的候选服务。** `tests/browser/entity-canvas-resident.mjs:34-39` 使用 `spawnSync(... timeout:240000)` 直接运行四组 Python；超时由 Node 向这个 Python 进程发终止信号，Python 的 unittest tearDown/addCleanup/finally 不会因此自动执行。其候选 .NET 是独立子进程，浏览器 `finally:169-173` 只知道 Chrome 和后面才创建的静态 `service`，不知道这些候选 PID。因此慢机或默认基线+四组耗时达到240秒时，控制流可以留下本次孤儿候选。未实际触发超时、未启动新进程来重现，不能称当前默认运行已泄漏。建议用本次生成任务专属进程组并在超时/异常时等待并终止该组，或在生成器自身处理终止信号并执行所注册清理；只调整超时时间不能保证异常退出清理。不得用全局按名称 kill 的方式影响其他 agent 服务。

其余当前范围未发现确认问题。默认结果及对应 source 稳定性仍待协调者全 check 输出，不把静态无旧目录依赖等同于默认入口已实际通过。

## 默认生成器清理修复复核

2026-10-26 07:16 UTC。协调者接受上述超时控制流发现，并修改默认浏览器入口；最新 `tests/browser/entity-canvas-resident.mjs` SHA-256 为 `f014c9fc1624cbc4f4d0e13783d82a8cffff806321e06bf57a13030f6e1c38f5`。本节只读核对源码，没有启动 Python、浏览器或候选服务。

`spawnSync` 现带 `detached:true`，四组 Python 报告生成结束后，在断言退出状态前向 `-run.pid` 发 SIGTERM，ESRCH 视为进程组已退出。`Continued.start` 的候选 `Popen` 没有另建 session/group，继承该生成任务进程组，因此默认超时或子进程异常退出路径也会向本任务遗留候选发终止信号。作用域为此次生成器拥有的进程组，没有按全局进程名称终止服务。两份 Python 测试以及产品 Web 指纹与上节一致。

原发现中“只终止 Python 父进程、未向候选发清理信号”的控制流缺口已经修正。当前实现发信号后没有等待整个进程组消失，因此本次静态检查仅确认清理信号覆盖；实际默认运行结果和结束后的候选退出状态仍待协调者证据。未注入超时，不宣称超时清理已经实测通过。

## 默认 HTTP 与 Python 运行结果核对

2026-10-26 07:23 UTC。只读核对协调者本轮默认入口输出，未另跑测试：

- HTTP：`.local/iter0025/api/20261026T071653Z-f98e7f/results.json` 为 `passed=true, testsRun=9, failures=[], skipped=[]`；对应 check 日志记录 245.403 秒。基线是本次 `seed/continued`，实际目标 `e42490b38d4a24604a9f2e90fc3ad4a28`，并非先前原自然历史的固定 ID。
- Python：`.local/iter0025/python/20261026T071717Z-0719fd/results.json` 为 `passed=true, testsRun=8, failureDetails=[]`；对应 check 日志记录 248.655 秒（包含构造基线）。声明验证层级仍是 `builder-self-check`。七份源码的 before/after 哈希一致，逐份重算也与当前文件一致；`sourceStable=true, allStartedServicesStopped=true, temporaryRuntimeCreated=false`。
- 两组记录的 DLL 均为 `src/World.Server/bin/Debug/net10.0/World.Server.dll`，SHA-256 `5f9426ac1df94cab856262688d02ab6265096bfb74f18747fd39e443b2f3e1de`，均声明 DLL 未变化；本次重算当前 DLL 相符。

实际 Python 两份报告绑定本次新实例 `w_8cada4dca4cc46b793f0a23aff679506`、目标 `e76de84a5d368445091f74c03469bc763`，两次任务均 `completed/round_trip_verified`，原 edit 分别 rev1、rev2，`entityCanvasPainted=true, returned=true`。a1_alias 为 77 命令 / 81 查询，a2 为 35 命令 / 39 查询；两者 `wood=0`，本次默认 a2 的绘画时库存也是 0，旧原自然历史 a2 库存 9 的断言没有污染默认入口。报告中的 `modelCalls=1` 为既有固定任务选择预算，运行总表明确 `actualModelCalls=0`。

这些是协调者默认作者回归记录及本次只读证据核对，不等同于对原自然历史的独立验收。默认浏览器目录 `.local/iter0025/browser/2026-10-26T07-21-57-568Z` 已建立，但最终结果当时尚未落盘；其四组 Python 生成器为另一个本轮目录 `.local/iter0025/python/20261026T072157Z-94f780`，仍等待完成。

## 默认浏览器结果与正常退出核对

2026-10-26 07:26 UTC。默认浏览器 `.local/iter0025/browser/2026-10-26T07-21-57-568Z/results.json` 已记录 `passed=true, testsRun=19, errors=[], worldRequests=[]`，Chrome `152.0.7977.82`，`actualModelCalls=0`。其 `inputs.json.inputDir` 精确指向本轮 `.local/iter0025/python/20261026T072157Z-94f780`，未复用旧作者报告。

该四组生成器 `results.json` 为 `passed=true, testsRun=4, failureDetails=[]`；`mission.log` 记录 213.583 秒，正常完成，未触发 240 秒超时。七份源码 before/after 与当前重算一致，DLL 与当前重算一致；`allStartedServicesStopped=true, temporaryRuntimeCreated=false`。浏览器入口仍为 `f014c9fc1624cbc4f4d0e13783d82a8cffff806321e06bf57a13030f6e1c38f5`，两份产品 Web 指纹仍与前述修复版本一致。

07:26:35.990635 UTC 额外只读检查 `/proc` 命令行和 cwd：精确限定本工作区 cwd，匹配 dotnet 的 `World.Server.dll`、Node 的 `entity-canvas-resident.mjs`、Python 的 `entity_canvas_mission_api.py` 及指向 `src/World.Server/wwwroot` 的 `http.server`，结果为 `matchingWorkspaceProcesses=[], unverifiedCwd=[]`。这支持本次正常结束后未遗留这些候选或静态服务；没有读进程环境、凭据、数据库，也没有发送终止信号。未注入超时，不能将正常退出观察写成超时分支实测通过。

本轮只读审查闭合：三项产品报告反例已修复并通过 9/9 针对性 VM 复核；默认生成器清理信号覆盖已静态确认，默认 HTTP 9/9、Python 8/8、浏览器生成器 4/4、Chrome 19/19 的协调者原始结果已核对。本次没有新开服务或重复作者套件，唯一写入本审查文件。协调者 07:26:33 通知全 check 已通过并要求停止扩测；最终全项目源码归属、证据归档和产品集成由协调者负责，后续保持现有终端等待下一候选。
