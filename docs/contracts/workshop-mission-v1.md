# Python 工作台固定任务 v1

2026-10-26，ITER-0027 接入契约。Python 执行器与报告已实现；本地专项、独立验收和整体采用状态以本轮结果中的分列证据为准。权威动作、材料和空间规则见 [workshop-v1](workshop-v1.md)。

一次任务只执行一个明确的工作台动作，以及所需行走和可选返程。建台、制锤、建箱、存入、取出分别为任务；下一任务引用上次三方证据已确认的产物 ID，不在恢复时另选台、锤或箱。固定任务不调用目标选择器或模型。

```json
{
  "missionId": "workshop-bench-001",
  "objective": "在指定位置搭公共工作台，并返回原起点。",
  "goals": [{
    "id": "build-bench", "label": "公共工作台", "target": [26, 20],
    "workshop": {
      "worldInstanceId": "w_00000000000000000000000000000000",
      "actorId": "a2", "returnToOrigin": true,
      "action": {"type": "build_workshop", "capabilityVersion": 1,
                 "recipeId": "workbench.v1", "at": [26, 20], "toolId": null}
    }
  }],
  "allowBuild": false,
  "allowWorkshopBuild": true, "allowCraftTool": false,
  "allowDepositWood": false, "allowWithdrawWood": false,
  "budgets": {"commands": 100, "queries": 500, "wood": 3,
              "woodMoved": 0, "seconds": 600, "modelCalls": 0}
}
```

示例中的全零实例是待替换值，不能作为实际目标。台、工具、箱 ID 必须来自原世界的已确认记录；坐标须与原目标一致。每个任务只有一个 `goals` 项，`workshop` 必须同时给出实例、居民、动作和 `returnToOrigin`。四个新权限均须明确写出，并且只有本次动作对应的权限为 true；旧 `allowBuild` 固定为 false。存取不能借用建造或制作权限。没有自动领取、采集、赠送或补造设施。

`action` 严格使用权威契约中的完整字段。建造的 `toolId` 必填，台为 null，箱为本人实际锤 ID；制锤明确台 ID；存取明确本人箱 ID 和 1—12 的整数数量。浮点数量、布尔版本、未知字段和未知动作在网络请求前拒绝。实例和居民由任务明确指定，操作者、采用记录、原实体和工具快照在初次合法观察时绑定。

预算如下：

| 字段 | 上限范围与计数 |
|---|---|
| `commands` | 1—1000；新逻辑命令在发送前计数并保存，原 ID 重发不另计一次命令 |
| `queries` | 1—5000；每次观察、回执、动作明细、事件 GET 尝试在请求前计数，失败同样计数 |
| `wood` | 0—12；只核算本任务确认的配方用材，建台/箱3、制锤1，不将存入当作材料消耗 |
| `woodMoved` | 0—12；确认的存入或取出数量；与配方用材独立核算 |
| `seconds` | 1—600；从首次启动计时，暂停与重启不重置起点或已用时间 |
| `modelCalls` | 固定0；不会调用传入的选择器，不能通过 `--account` 赋予新权限 |

POST 对应已计费的原逻辑命令；恢复重发前必须有一次计费的明确 `COMMAND_NOT_FOUND` 查询。404 本身不代表失败或成功，也不产生新 ID。时间、命令或分段上限停止新发送；已有 pending 可在剩余查询预算内查证原结果，不能因上限耗尽丢弃 pending。观察、规划或持久化可能耗尽时间，因此首次发送前及404后的能力观察返回后均重新检查累计用时，不能沿用请求前的时间判断。`max_steps` 是本次处理的逻辑命令数，不重置任务预算。

状态保存沿用原子写入与文件互斥。绑定、规范化任务、权限、查询日志、原请求、前事实、已用预算与证据在网络或模型调用前校验。未确认请求先持久化，再发送；网络失败、401、500、未知能力或不完整证据保留原请求和身份。拒绝或碰撞截停的原回执、清除pending与任务终态一并原子保存，不能在两次写入之间留下无法恢复的中间状态。换端口恢复须仍为原实例、原居民和原操作者。原居民状态前置版本从本任务最近确认的动作推进，不能用一次新观察掩盖本人在任务之外的动作。

新动作完成必须同时核对原回执、`workshopActionCompleted` 原事件和本人动作详情，三者的身份、原命令、动作、实体/工具快照、数量和前后库存一致。三次响应的实例头也须一致。当前库存、现在有一把锤、当前箱内余额均不能代替历史事实。已确认配方用材和转移量只结算一次；原拒绝终结本次意图，不自动换 ID 再尝试。

导航使用完整家具碰撞及包含家具的缓存键。制作和存取选择可达操作侧；交互射段仅排除本次目标家具，正常行走不排除。建造不会把实体中心作为必须到达的位置。旧桥、平台配方和旧 `build` 请求仍沿用原含义。

CLI 沿用 `python3 scripts/run_resident.py --url ... --access-file ... --actor a2 --spec ... --state ... --output ...`。工作台任务默认固定执行，不需要模型账号；指定账号会被拒绝。完整链使用五份明确任务，产物 ID 从上一任务 `facts.workshopAction.entity.entityId` 或 `facts.workshopAction.tool.toolId` 读取，只有 `facts.workshopCompleted` 且证据一致后才用于下一任务。领取更多原材料仍使用已有明确授权的材料入口任务或居民操作，不隐含在制作中。

报告继续使用 `resident-mission-report`。`facts.workshopCompleted` 与 `facts.workshopAction` 表示原动作已确认；`facts.returned` 仅表示已确认位置在原起点，不因省略返程而写成 true。`returnToOrigin:false` 允许动作已确认但未返程时完成；true 则必须额外确认返程。未知结果、动作完成但返程中断、完整完成分别显示。`world.observedSelf` 保存最近实际观察的本人位置与库存，配合 `observedStateVersion`：若该观察比任务最后确认回执更新，返程事实使用该实际位置。任务外移动触发停止后，不能沿用旧起点位置宣称已返回。报告中的地图仍为最近实际观察，不能把本地规划或产物推断当作即时世界图。

真实 CLI 链路、重启与中断、预算、权限、未知能力和损坏恢复文件的验证在冻结后端上执行。纯夹具只能证明相应软件边界，不能作为真实世界或自然活动验收。

五份待绑定模板位于 `examples/workshop-build-workbench.json`、`workshop-craft-mallet.json`、`workshop-build-chest.json`、`workshop-deposit-wood.json`、`workshop-withdraw-wood.json`。每份必须先替换原实例和相关产物 ID，确认居民、坐标、返程选择与预算；它们不是可直接写入任意世界的默认命令。

专项测试不依赖隐式私人路径，也不为了默认测试伪造原历史。运行实际历史支线需要显式指定已停服的原 `world.db`／`access.json` 所在目录与冻结 DLL：

```sh
WORKSHOP_BASELINE=/absolute/original-snapshot \
WORLD_SERVER_DLL=/absolute/frozen/World.Server.dll \
python3 tests/workshop_mission_api.py
```

该入口只备份读取来源，在自己的临时目录按正式命令续会话、显式采用能力，以真实 HTTP 领取和行走执行任务；没有 SQL 发料或改位置。结束时保留小型报告、请求和审计，停止自己启动的服务并删除自己的数据库与凭据副本。它不修改或替代原自然活动主线。

Chrome 报告专项只导入上项产生的实际报告，不发送世界请求：

```sh
WORKSHOP_REPORT_DIR=/absolute/mission-evidence \
node tests/browser/workshop-resident.mjs
```

这两项分别由 `test:workshop:mission` 和 `test:workshop:report` 专项入口接入，不要求通用回归拥有私人原历史。测试双身份仍为声明控制身份，不由账号数量推断独立真人；复用公共台与自建台的材料比较须列明相同初始库存、实际新增领取、配方用材和最终余额，不能用初始库存差异推断制作效率。
