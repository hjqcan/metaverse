# ITER-0019 · Python 任务与报告适配

2026-10-26。本文件记录 Python／报告部分的实现和作者验证；服务端与 Godot 的整轮集成由主目录另行汇总。[冻结契约](../contracts/actor-state-v1.md)保持原 r8 物理规则和资源总量。

## 实际改动

新任务只在受实例保护的 r8 明确公布能力后选择 `actor-state-v1`，将选择写入私有 binding 和公开 mission。旧任务缺少新字段时继续严格模式；新标记缺模式、两处不一致或 pending 的模式／锚点／提交前事实损坏，在访问网络前拒绝。已有任务不因重新观察而换模式，完成任务仍离线读取原报告。

行走、采集、建造共用执行版本校验：观察锚点 E、实际执行基准 S、提交版本 S+1 必须对应原命令。采集同时核对事务前节点余量与扣减、本人的原库存+1；建造核对材料、原目标和实际实体。显式建设和自动建桥都保留原建造依据。未知结果不换 ID、body、模式或版本，错误回执不清 pending。

同一居民被另一客户端操作后，`STALE_ACTOR_STATE` 的持久拒绝结清原 pending 并停止当前任务；再次读取该任务不会联网或自动继续旧目标。它不代表控制权或权限已经转移。其他居民的无关动作则允许在当前材料、位置和几何仍有效时继续执行。

公开步骤保留原观察版本和已验证 execution。报告页面检查模式、实例、锚点与终态版本是否一致；未确认步骤不能携带已确认 execution。页面保持只读，没有增加协议操作入口，也不重新向世界核验导入文件。

## 验证结果

| 验证范围 | 结果与证据 |
|---|---|
| 新模式实际 HTTP／SQLite | [12 项通过](evidence/ITER-0019/python-http-results.json)：每次提交前的远处移动干扰、同居民 ABA 停止、合法建桥会合后的同树采集、提交前后退出、三类动作的损坏 execution、节点事务余量、旧任务、冻结模式和损坏记录预检 |
| 旧严格模式冲突 | [2 项通过](evidence/ITER-0019/python-strict-regression.json)：walk/build 原观察后插入他人动作，仍先持久拒绝，再用新意图继续 |
| 新模式真实 Chrome | [9 项通过](evidence/ITER-0019/python-browser-results.json)：导入真实干扰报告、错误 execution／模式／锚点、未知建造、拒绝版本、旧报告和390px布局；JS错误0，世界请求0 |
| 原建设报告 Chrome | [8 项通过](evidence/ITER-0019/python-construction-browser-regression.json)：建造事实、未知状态、错配材料／身份／实体、建后到达、旧桥报告与移动端 |
| 当前源码构建 | 接入服务端提交 `6e1eb5b247b83f28af367b1c7c12c91c4b8b77df` 后，`dotnet build src/World.Server/World.Server.csproj --no-restore` 为0警告、0错误 |

新 HTTP 套件使用主目录的不可变服务候选，DLL SHA-256 为 `de5364860d1b2b8805f3f6ec836008aa4e09ddbb1f7dfa522a8faf355b1dca08`；12项运行前后产品源码哈希相同，所有自启服务已停止。完整文件哈希见[最终清单](evidence/ITER-0019/python-source-manifest.json)。外部模型调用全部为0；HTTP任务的选择器是明确测试替身，不把预算里的“一次选择”算作真实模型调用。

[实际干扰报告](evidence/ITER-0019/python-interference-report.json)完成一次平台建设、到达与返回；每条本人命令前都有另一居民实际移动，行走／采集／建造均提交。[停止报告](evidence/ITER-0019/python-stopped-task-report.json)保留原命令的拒绝及原预算，未继续采集或建造。页面截图为[桌面](evidence/ITER-0019/python-desktop.png)和[移动端](evidence/ITER-0019/python-mobile.png)。

首轮12项检查对应当时“同居民拒绝后重试”的候选，仅作为[历史自测记录](evidence/ITER-0019/python-initial-results.json)保留，最终策略已改为停止并完整重跑。首次 Chrome 检查出现两个测试脚本问题：把测试替身报告当成固定策略文案，以及只用 exitCode 判断 Python 静态服务的信号退出；[失败记录](evidence/ITER-0019/python-browser-initial-failure.json)保留原因，修正仅涉及测试脚本，随后9项全过。

独立测试由另一测试会话在主目录私有副本执行，其证据与最终采用结论由集成报告分别列出。本文件的作者自测不替代独立验收。

## 复跑与交接

先构建当前服务，再运行：

```bash
python3 tests/actor_mission_api.py
node tests/browser/actor-resident.mjs
node tests/browser/construction-resident.mjs
```

`ACTOR_TEST_DLL` 可指定已有不可变服务 DLL；`ACTOR_REPORT` 可让 Chrome 使用已经生成的真实干扰报告，省去重复旅程。测试只使用隔离 `.local` 数据与回环端口，结束时停止自己的服务。

用户要求收尾后删除 Orca tree。本轮原始 Python／Chrome 记录迁入主目录 `.local/tree-handoff-20261026/iter0019-python/`，无凭据摘要及必要报告进入 Git。资源转让仍只是单独的 ITER-0020 草案，未实现；本轮不新增资源供给，也不据此宣称并发公平、长期经济或防垄断要求已完成。
