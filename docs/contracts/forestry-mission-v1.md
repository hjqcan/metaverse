# Python 林业固定任务 v1

2026-10-26，ITER-0028 接入契约。固定执行器与报告页已实现，作者专项验收已完成；独立验收和整体采用由迭代结果记录。权威规则见 [forestry-v1](forestry-v1.md)。本文件的任务形式不改变世界规则。

一次任务只执行一个明确林业动作，以及必要行走、明确允许的原对象等待和可选返程。六种动作分别授权；两轮生产由新的明确任务顺序完成，不能把前一次成功当作自动续种权限。固定任务不调用目标选择器或模型。

```json
{
  "missionId": "forest-harvest-first",
  "objective": "等原植株成熟后，用本人原木斧采收，并返回起点。",
  "goals": [{
    "id": "harvest-first", "label": "采收原植株", "target": [7, 12],
    "forestry": {
      "worldInstanceId": "w_00000000000000000000000000000000", "actorId": "a3",
      "waitForReady": true, "returnToOrigin": true,
      "action": {"type": "harvest_tree", "capabilityVersion": 1,
        "plantId": "replace-original-plant", "reservationId": "replace-original-reservation",
        "toolId": "replace-owned-axe"}
    }
  }],
  "allowBuild": false,
  "allowCraftForestryTool": false, "allowReserveForest": false,
  "allowCancelForestReservation": false, "allowCollectSeed": false,
  "allowPlantTree": false, "allowHarvestTree": true,
  "budgets": {"commands": 200, "queries": 1000, "wood": 0, "woodHarvested": 3,
    "seedsCollected": 0, "seedsPlanted": 0, "seedsHarvested": 1,
    "seconds": 600, "modelCalls": 0}
}
```

全零实例和 `replace-` ID 是待绑定占位值。原实例、居民、权限及完整原动作必须明确给出。六个权限全部必填，只有本次动作对应项为 true；`allowBuild` 为 false。旧工坊权限不隐含林业权限，任务也不自动领取旧来源木材、制斧、存木、续租或换树。

`goals` 只能有一项。制作、领种、种植、采收的 `target` 必须是原台、采种点或原林位的精确中心；执行器前往可达操作侧，不要求站到碰撞体中心。申请与取消不需要空间目标，输入 `target:null`，原地执行；报告中的目标坐标记实际原起点，以便继续使用地图与回放格式。

`forestry.action` 严格使用权威契约中的完整字段，不允许额外字段、布尔版本或浮点版本。`waitForReady` 与 `returnToOrigin` 必须显式为布尔值。只有原授权排队和原植株生长可以在 `waitForReady:true` 时继续观察；目标不符合原任务、授权已不再有效、无保留种子、本人在任务外发生动作或原动作被拒绝时停止。原排队回执只证明入队，原种植回执只证明种下；都不能替代成熟或采收。

任务绑定原实例、居民、操作者、采用记录、固定设施与原工具。原授权绑定其不可变入队身份；权威分配可推进原授权状态，不允许替换 reservationId。种植明确原 plotId，采收明确原 plantId 和 toolId；每次发命令之前冻结当时原授权、原植株和相关前事实。恢复只查证或重发该原请求，不根据当前林位切换下一代。

| 预算 | 范围与计数 |
|---|---|
| `commands` | 1—1000；每个新逻辑命令发送前计数并保存，原 ID 重发不重复计数 |
| `queries` | 1—5000；每次观察、原回执、原动作明细及事件 GET 尝试均预先计数，失败也消耗 |
| `wood` | 0—12；仅确认的木斧配方用材2 |
| `woodHarvested` | 0—12；仅原采收确认转入的3木，不将环境成熟发行当作本人采得 |
| `seedsCollected` | 0—4；原领种确认的1种 |
| `seedsPlanted` | 0—4；原种植确认消耗的1种 |
| `seedsHarvested` | 0—4；原整株采收确认产生的1种 |
| `seconds` | 1—600；首次启动后的累计墙钟时间，暂停和重启不重置；世界生长仍只认服务时间 |
| `modelCalls` | 固定0 |

等待以有限间隔观察同一对象，消耗查询与时间预算。`max_steps` 仅限制当前调用处理的逻辑命令数，不重置总预算。剩余查询预算可用于查证已存在的 pending，即使时间已到；时间到后不能发新命令或重发。初次观察失败仍留下原启动与查询账。观察、规划和最后一次持久化均可能越过截止时间，POST 紧前重新读取累计时间。

原请求、原 ID、前事实和计数先原子保存，再 POST。只有带原实例证明且明确为 `COMMAND_NOT_FOUND` 的原 ID 查询才能进入原请求重发路径；重发前再观察原能力，保持相同请求体。401、5xx、超时、不完整证据、未知能力或异实例均保留 pending。原拒绝回执、清除 pending 与终态一次原子保存。终态重放不访问网络。

成功须核对原回执、本人原事件和 `forestry/actions/{actorId}/{commandId}` 原明细，三份响应的实例头一致，动作、身份、事件、库存增减与原对象一致。环境可能在观察与事务之间生产种子，因此事务的 nurseryStockBefore 是原事实，不能用早先观察余额冒充；每次动作仍严格核对其应有增减和原授权。当前库存、当前树形或当前授权不能代替原动作三方事实。

`forestryCompleted/forestryAction` 表示单一原动作已确认；`goalReached` 随该原动作，不代表排队后已种或种植后已采。报告另列最近实际观察中的生长状态和服务时间。`returned` 由最近可信实际位置判断；省略返程不会把 false 改为 true。原动作完成与整个任务完成分开显示，环境成熟与本人实际采收分开显示。

CLI 沿用 `run_resident.py --url ... --access-file ... --actor ... --spec ... --state ... --output ...`。林业任务默认固定执行，拒绝 `--account` 和与任务不符的居民。两轮链必须从三方已确认的上一动作读取产物 ID，再以新的明确任务申请、领种、种植或采收。采用后的原历史隔离支线用于实际测试，等待实际服务时间，不用 SQL 生成种子、斧、木材、成熟或完成事实。

实际链式编排需要把行走与返程计入原租约。首轮隔离试验中，领种任务明确要求返回东南起点，执行用时122.61秒；再赴林地时原90秒准备租约已到期，种植正确停止，已领取树种保持。该失败任务和原记录不改写。新的链式任务可显式选择领种、种植和首轮采收后不返程，在原对象附近接续；不能据此改变已保存任务、自动续租或延长期限。

几何使用权威公开圆形障碍。正常行走保留灌木及全部未采完树干；仅正在交互的原目标可从交互射段排除。成熟不改变树干大小。未知林业能力或不完整几何不能作为可走空地使用。

后端冻结后再执行真实 HTTP/CLI 与 Chrome 报告导入验收；初败、源码 SHA、原命令和审计分列保留。原生自然史由协调者与独立验收方接续，本任务只使用自己的隔离副本；结束后停止自己的服务并清理已用数据库、凭据及私有缓存。

作者验证包括26组真实 HTTP/CLI 与故障注入专项、29组真实 Chrome 林业报告检查，以及同版报告页的23组旧工坊回归。实际两代种植与采收使用真实服务时间，第二代使用第一代返还树种，再用3木材建平台；最终个人3木1种、林业发行6木、全世界累计发行82木，木材和树种守恒。生长、成熟、备份及最终停服前后7个数据库检查点均完整，原作品、手记和地画保持。固定输入及隔离历史分支不等于真人体验、长期生态或防垄断验收。

审计异常单列：旧测试读取流程曾在停服后同一 Python 进程报 `database disk image is malformed`，首次失败库已被旧清理流程删除，留下证据缺口。保留旧连接用法的隔离对照再次复现同样报错；这次保留的冷文件在新进程复制检查中完整性正常、外键检查为空，冷库重启与原命令重放也通过。当前测试显式关闭 SQLite 连接后全26组通过。结论仅为旧读取流程可复现错误、保留冷文件未显示损坏，不推断 SQLite 的唯一内部根因，也不改写旧失败结果。对照源码差异、冷库与独立诊断按协调者要求保留。

专项入口 `tests/forestry_mission_api.py` 需要 `FORESTRY_BASELINE` 指向原 v1352/storage13 冷副本，`WORLD_SERVER_DLL` 指向协调者冻结候选。真实两轮链产生的成熟中间副本附有原始命令、服务时间与 SHA 来源，可通过 `FORESTRY_READY_BASELINE` 复用于恢复反例，使用后删除。浏览器入口 `tests/browser/forestry-resident.mjs` 需要 `FORESTRY_REPORT_DIR` 指向完成两轮链的证据目录，`FORESTRY_CANCEL_REPORT_DIR` 指向预约取消专项目录；`FORESTRY_RECOVERY_REPORT_DIR` 可补入真实丢响应与查询预算反例。浏览器只导入原报告，不访问世界服务；截图、检查结果、浏览器版本与源码 SHA 写入 `.local/iter0028/browser/`。
