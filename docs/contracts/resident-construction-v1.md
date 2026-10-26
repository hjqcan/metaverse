# 指定设施建设任务 v1

扩展 [连续居民任务](continuous-resident-v1.md)，使用现有 r8 世界、配方与事务，不增加资源发行。目标由固定策略或原有高层选择器选择一次，确定性执行器完成采集、建造、到达和返回。

## 输入

目标可带 `buildRecipeId: "platform.v1"` 或 `"bridge.v1"`，`target: [x,z]` 同时是固定设施中心与到达地点。任务必须 `allowBuild: true`，该目标不能同时带 `activityId`。平台消耗 3 木、整座桥消耗 6 木；`allowGather` 决定是否允许采集材料缺额。任务起点、目标候选、配方、权限和累计预算在恢复时保持。

建造前检查公开配方、占地、河岸条件、障碍、现有实体、现有通路及完整材料缺额。只建本次选中的设施，不为抵达建造点额外造桥；不可达地点返回受阻。材料预算不足或禁止采集时不发采集命令。命令预算逐条扣除，耗尽时已确认的采集不会撤销。

平台需要整片占地位于陆地；桥中心须与公布的河道中心线匹配。树木采空后成为可通行地形，设施占地仍由服务器最后裁决。有限候选路线用于规划，不承诺全局最短或任意地图完备搜索。

## 建造事实

发送前保存原命令、材料消耗和建造前库存。确认必须同时满足：原命令 ID、身份、r8/schema、状态版本、动作、配方目标、回执库存扣减一致；回执实体 ID 在后续公共观察中存在，其所有者、定义与版本、中心、内含材料与本次一致。

确认后原子保存 `facts.constructionBuilt`、`facts.construction`、原步骤的 `entityId`、累计木材与清除 pending。`construction` 包含 commandId、entityId、recipeId、definitionId、ownerActorId、position、woodSpent、stateVersion。建造不会把角色移动到设施中心；到达标记按建成后的实际位置重新确认，建造前曾到过这里不能代替建成后到访。之后仍需实际行走到达，再返回原起点。

丢响应或证据不一致保留原命令。恢复先查询原回执；只有明确未找到才原样重发。看到旧设施、只到达坐标、缺失实体、错误身份或错误材料都不能确认建设。原命令的明确 `STALE_STATE` 拒绝允许重新观察后发起新尝试；未知结果不换命令。

报告页核对建设目标与权限、原提交步骤、实体和材料的一致性。只读导入文件，不重新访问世界服务；页面“已核实”描述记录内部的一致证据，不表示独立在线审计。老的普通通行任务即使沿途造桥，也不会被改写成指定设施建设任务。

## 示例

`examples/construction/platform.json` 是 a1 西岸短任务。以下链路使用同一个 r8 世界：a1 造桥，a2 在东岸造平台，a1 零材料复用桥去平台再返回。已有设施占据同一目标时，新建任务会受阻，访问任务仍可使用。

```bash
python3 scripts/run_resident.py --url http://127.0.0.1:5089 \
  --access-file .local/continuous/access.json --actor a1 --fixed-reference \
  --spec examples/construction/bridge.json \
  --state .local/continuous/bridge-task.json --output .local/continuous/bridge-report.json

python3 scripts/run_resident.py --url http://127.0.0.1:5089 \
  --access-file .local/continuous/access.json --actor a2 --fixed-reference \
  --spec examples/construction/platform-east.json \
  --state .local/continuous/platform-task.json --output .local/continuous/platform-report.json

python3 scripts/run_resident.py --url http://127.0.0.1:5089 \
  --access-file .local/continuous/access.json --actor a1 --fixed-reference \
  --spec examples/construction/visit.json \
  --state .local/continuous/visit-task.json --output .local/continuous/visit-report.json
```

这些命令会真实消耗该世界的材料。固定策略调用模型 0 次；`--account` 才启用原有模型选择器。任务 state 与公开报告分开保存；中断恢复重用同一 state 和 spec。
