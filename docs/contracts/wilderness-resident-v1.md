# 原始世界的有界居民任务

2026-10-26，ITER-0013。世界接口继续使用 r7 / schema 7；只扩展原有 Python 居民执行器与报告，不迁移数据库。依据 [提案](../proposals/ITER-0013-wilderness-resident.md) 和 [原始采集契约](wilderness-v1.md)。

## 权限与规划

任务增加可选布尔 `allowGather`，省略等同 false。模型只能在原 `goals` 中选目标，不能增加采集权限。旧持久任务保存的 spec 必须原样恢复，不能在同一状态文件中补上 true；旧世界仍按原规则领料。`allowBuild` 与木材、命令、时间预算继续生效。

显式允许采集的 r7 任务，在目标需要新桥且库存不足时，先规划可达树木的采集路径。只经当前可步行的路线走到树旁，不把尚未连通的对岸来源计入供给；按路径长度、节点 ID 和固定方向顺序选择来源。模拟采空后的通行变化，仅用于计划，不修改观察或世界事实。

整个材料缺口都能由当前可达来源补足才开始采集；不足返回 `insufficient_reachable_natural_material`，不会先砍一部分再发现短缺。每次行动前重读实际位置、库存、树木和路径；只补当前剩余桥梁成本的缺口，不囤积额外材料。默认未允许时维持 `natural_material_collection_required`。

每次采集计一条命令，行走、建造照常计数。木材预算依然统计本任务实际建造消耗，不能用预存库存绕过。候选目标的命令估算包含采集绕行、逐次采集、建桥与返回。实际执行受累计预算限制；其他居民同时行动可能改变估算。

本轮不实现为清路而砍树、依赖新桥才能到达的分阶段供料、通用长期采集目标或资源再生；无法满足当前任务时保留准确受阻原因。目标与原起点保持不变。

## 原命令与报告

每次采集发送前保存原命令，以及来源坐标、来源余量和本人库存。成功回执须匹配原命令、身份、r7、节点、单次数量1、提交前数量变化、世界版本 expected+1。错误或不完整回执保持 unknown；恢复先查原 ID，只有原结果确认为不存在时才原样重发。结算采集计数与清除 pending 在同一次本地原子写入中完成。

报告追加 `mission.allowGather` 与 `facts.woodGathered`，旧报告缺字段按 false／0 读取。`woodClaimed` 继续只统计公共领取，不能把采集算成领料。采集步骤保留原 `nodeId`，步骤位置仍是居民所在格，不能误用回执里的树木位置。报告查看器显示两类来源；汇总、步骤、权限不一致时完成标记须复核。页面只读历史报告，不会因打开文件而行动。

`--fixed-reference` 使用已有确定性成本策略，不调用模型；与 `--account` 互斥。报告中的 provider 为 `fixed-reference`，沿用旧预算字段 `modelCalls` 记录一次目标选择，界面显示“目标选择次数 / 外部模型 0 次”。`--account` 仍为一次真实 GPT-6 高层选择，未在本轮实际调用。

## 运行

已运行的原始世界可使用以下显式命令。这会让指定居民在该世界行动；状态与报告路径必须不同。同一任务恢复时使用完全相同的参数，不改 missionId 或预算。

```bash
python3 scripts/run_resident.py \
  --url http://127.0.0.1:5088 --access-file .local/wilderness/access.json \
  --actor a1 --fixed-reference --spec examples/wilderness/builder.json \
  --state .local/wilderness-builder/state.json --output .local/wilderness-builder/report.json

python3 scripts/run_resident.py \
  --url http://127.0.0.1:5088 --access-file .local/wilderness/access.json \
  --actor a2 --fixed-reference --spec examples/wilderness/traveler.json \
  --state .local/wilderness-traveler/state.json --output .local/wilderness-traveler/report.json
```

在 `resident.html` 导入生成的 report.json 可查看材料来源、原命令和轨迹。独立验证入口：`python3 tests/wilderness_mission_api.py`、`node tests/browser/wilderness-resident.mjs`；已加入 `npm test`。测试启动自己的随机端口服务和临时数据库，全部结束后关闭，不运行上述现有世界命令。
