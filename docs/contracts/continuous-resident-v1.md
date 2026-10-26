# 连续世界居民任务 v1

对应 [r8 世界契约](continuous-world-v1.md) 与 [ITER-0015](../proposals/ITER-0015-continuous-resident.md)。当前实现是有界任务执行器；目标选择与实际移动分开，不新增服务端规则。

## 输入和预算

`run_resident.py` 使用原任务结构。r8 目标为有限实数 `[x,z]`，单位米；`allowBuild`、`allowGather` 分别授权建桥、采集，采集默认关闭。命令上限 1000，木材上限 12，墙钟时间上限 600 秒，目标选择仍只有一次。旧 r1—r7 仍要求整数目标、至多 100 条命令。

墙钟时间包含规划、等待、暂停和重启；新动作前检查累计预算。预算耗尽不阻止查询或原样恢复此前已计入预算的未决命令。路径估算只帮助目标选择，不预扣、不替代实际命令和材料记账。固定策略使用 `--fixed-reference`，外部模型调用为 0；`--account` 才调用原有 GPT-6 选择器，两者互斥。

## 连续路径

从公开的河道多边形、圆形岩石、存活树木、公共桥和角色半径建立可见路径图。节点是绕障和桥岸的候选实际坐标，不是世界格子；直线段必须满足几何净空。每次移动后读取服务端位置，按当前地形重新规划。当前实现采用有限候选和启发式顺序，不承诺全局最短路线或任意地形的完备搜索。

同岸路径优先。需要跨河且任务授权时，先检查是否能采齐一座桥所缺木材；只采缺额。采空树的预测仅用于规划，实际材料和碰撞变化须由服务器确认。桥的位置按公开河道中心线选择；现有桥可被后来者零材料复用。不自动造平台，不把多桥网络、动态避让或城市规划标记为已实现。

每次 `walk` 等待当前公布的 `maxStepDistance / speed` 额度，再发送原目标方向。服务器决定本次实际移动距离；客户端没有预测位置。到达和返回使用欧氏距离 ≤0.06 米，报告保留完整小数，界面仅把显示值保留两位。

## 持久化与完成事实

发送前保存原命令 ID、原请求、原起点、最大步长和累计预算。结果未知时保留未决命令；恢复先查询其回执，404 才重发同一请求。必须匹配原命令、身份、r8、schema、状态版本和动作类型；确认位置必须位于原起点到原目标的线段上，距离不得超过原最大步长。伪造位置、错身份或错版本不能确认移动。

`blocked:true` 是一次已提交的碰撞截停，保存实际位置后停止本轮执行，不当作到达目标。明确的原命令 `STALE_STATE` 拒绝可以重新观察和规划；未决状态不换 ID。采集仍核对原树、数量、剩余木材、个人库存和版本。所有材料变化沿用服务器事务账本。

完成要求真实观察支持到达与返回；报告页再次核对已提交位置轨迹与采集数量的一致性。报告页只读导入文件，不调用世界动作接口，也不独立重新查询服务器。地形、树木和设施为结束快照，滑块回看位置轨迹，不声称复原每一步的全部地形。

## 运行示例

先启动独立 r8 世界并持有其 `access.json`。以下使用连续世界预览地址；不要把旧世界 access 文件与新地址混用。

```bash
python3 scripts/run_resident.py --url http://127.0.0.1:5089 \
  --access-file .local/continuous/access.json --actor a1 --fixed-reference \
  --spec examples/continuous/builder.json \
  --state .local/continuous/builder-state.json --output .local/continuous/builder-report.json

python3 scripts/run_resident.py --url http://127.0.0.1:5089 \
  --access-file .local/continuous/access.json --actor a2 --fixed-reference \
  --spec examples/continuous/traveler.json \
  --state .local/continuous/traveler-state.json --output .local/continuous/traveler-report.json
```

也提供同岸短任务 `examples/continuous/walk.json`。恢复使用完全相同的身份、地址、spec 和 state；状态与公开报告文件须分开。导入 `resident.html` 可回看自然河道、桥面、真实小数位置和材料。已有场景被其他居民改变时，实际命令数和路线会变化。
