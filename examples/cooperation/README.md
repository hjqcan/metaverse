# 自愿赠送与合作建设：固定策略 CLI 示例

从仓库根目录运行，使用显式 `wilderness-cooperation-v1 / r9` 世界。流程为 a1 空手出发，采西岸6木材建桥，过桥后再采3木材，在 `[26,17]` 向 a2 赠送3木材并回到原点；然后 a2 用收到的材料在 `[28,16]` 建平台并返回。最后可让 a1 零材料往返访问这座平台。

| 顺序 | 居民 | 输入 | 允许的材料支出 |
| --- | --- | --- | --- |
| 1 | a1 | [gift-wood.json](gift-wood.json) | 桥6＋赠送3，共9；允许采集 |
| 2 | a2 | [recipient-platform.json](recipient-platform.json) | 平台3；不允许采集或赠送 |
| 3（可选） | a1 | [visit-shared-platform.json](visit-shared-platform.json) | 0；只沿已有设施行走 |

三项均使用 `--fixed-reference`，实际模型调用为0。任务格式中的 `budgets.modelCalls=1` 是当前契约要求的上限；报告沿用 `budget.used.modelCalls=1` 记录一次目标选择，实际选择来源看 `decision.provider.kind=fixed-reference`，不能把这个历史字段误读为真实模型调用。赠送、收到材料与建造分别由原命令、公开事件和实体事实确认；任务说明中的“赠送材料”不会建立新的材料批次追踪规则。

## 启动候选世界

第一个终端运行：

```bash
npm run start:cooperation
```

默认地址为 `http://127.0.0.1:5090`，数据和本机访问文件为 `.local/cooperation/`、`.local/cooperation/access.json`。这组示例的完整初态演练要求新建 r9 世界：a1 在 `[5,7]`、a2 在 `[26,17]`，双方库存为0，四棵树共12木材，无桥或平台。已有数据库会继续原状态，启动命令不会重置世界；不要删除存档来重复示例。若该目录已有活动历史，可为单独演练指定新的 `WORLD_DATA_DIR` 和空闲 loopback `WORLD_URL`，并在下面所有命令中使用对应地址、访问文件和任务目录。

各阶段顺序运行，保持 a2 留在约定会面点，并避免同时用另一个客户端控制同一居民。接收者离开会面范围、位置被占用、材料或预算不足时，任务可以停止；它不会追逐接收者或自动扩大授权。

## 依次执行三个任务

第二个终端在仓库根目录运行第一项：

```bash
python3 scripts/run_resident.py \
  --url http://127.0.0.1:5090 \
  --access-file .local/cooperation/access.json \
  --actor a1 --fixed-reference \
  --spec examples/cooperation/gift-wood.json \
  --state .local/cooperation/missions/gift-wood.state.json \
  --output .local/cooperation/reports/gift-wood.json
```

确认输出的 `status` 为 `completed` 后，a1 已返回，a2 有3木材；再运行第二项：

```bash
python3 scripts/run_resident.py \
  --url http://127.0.0.1:5090 \
  --access-file .local/cooperation/access.json \
  --actor a2 --fixed-reference \
  --spec examples/cooperation/recipient-platform.json \
  --state .local/cooperation/missions/recipient-platform.state.json \
  --output .local/cooperation/reports/recipient-platform.json
```

确认 `status=completed` 且 `facts.constructionBuilt=true` 后，可运行第三项：

```bash
python3 scripts/run_resident.py \
  --url http://127.0.0.1:5090 \
  --access-file .local/cooperation/access.json \
  --actor a1 --fixed-reference \
  --spec examples/cooperation/visit-shared-platform.json \
  --state .local/cooperation/missions/visit-shared-platform.state.json \
  --output .local/cooperation/reports/visit-shared-platform.json
```

访问任务只验证到达指定坐标与返回；先完成第二项并核对实际平台，才能将第三项解释为复用作品。访问不产生新的建造事实或材料消耗。

## 检查报告与恢复

CLI 对 `paused`、`blocked` 和 `budget_exhausted` 也可返回退出码0，不能只凭 shell 成功判定完成。三项跑完后可汇总实际报告：

```bash
python3 - <<'PY'
import json
from pathlib import Path

reports = {}
for name in ('gift-wood', 'recipient-platform', 'visit-shared-platform'):
    report = json.loads((Path('.local/cooperation/reports') / (name + '.json')).read_text())
    reports[name] = report
    print(name, report['mission']['status'], report['budget']['used'])
    assert report['mission']['status'] == 'completed', report['mission']
    assert report['facts']['returned'] and report['facts']['goalReached']
    assert report['decision']['provider']['kind'] == 'fixed-reference'
    assert report['budget']['used']['modelCalls'] == 1  # 一次固定目标选择，外部模型0次
gift, built, visit = (reports[k] for k in ('gift-wood', 'recipient-platform', 'visit-shared-platform'))
assert len({r['mission']['worldInstanceId'] for r in reports.values()}) == 1
assert gift['facts']['transferCompleted'] and gift['facts']['woodTransferred'] == 3
assert gift['budget']['used']['wood'] == 9
assert built['facts']['constructionBuilt'] and built['facts']['construction']['ownerActorId'] == 'a2'
assert built['facts']['woodGathered'] == 0 and built['budget']['used']['wood'] == 3
assert visit['budget']['used']['wood'] == 0 and visit['facts']['woodGathered'] == 0
print('三项报告一致；世界账本仍以服务端持久记录为准。')
PY
```

第一项完成时应为：自然余量3、a1库存0、a2库存3、桥内含6，总12。第二项完成后应为：自然余量3、双方库存0、桥6、平台3，总12。第三项不改变材料分布。这里采集总量是9；契约中的“采完12后赠送”的独立验收是另一场景，不能混用最终库存。

中断后保留原 `--state` 和 `--spec`，重新执行原命令。状态文件绑定原世界实例、居民、目标和累计预算；同库迁址只改访问地址与对应访问文件，不能将原状态用于另一个新世界。收到 `STALE_ACTOR_STATE` 后旧任务停止，需显式新任务／输入；不要删掉 pending、换命令 ID 或清零预算来强行续跑。完成报告可重复读取，不会再次赠送或建造。

本示例验证自愿合作和已有作品复用；不证明拒绝赠送时的独立材料入口、长期公平经济或自主文明已经成立。规则、恢复与授权以 [material-transfer-v1](../../docs/contracts/material-transfer-v1.md) 为准。
