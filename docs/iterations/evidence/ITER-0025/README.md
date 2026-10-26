# ITER-0025 证据索引

2026-10-26。[结果报告](../../ITER-0025-results.md)说明采用范围、原自然时间线、修复与剩余问题。此目录保留原始报告，不把初次失败改成成功；`provenance.json`列出每个文件的原本机路径、字节数和SHA-256。报告里的`.local`路径为历史来源，已清理的临时数据库不再可打开。凭据、数据库及运行二进制不入库。

| 证据 | 内容 |
|---|---|
| [覆盖表](coverage.json)／[整套入口](author-full-regression.json) | 29套HTTP／Python：333项中332通过、1旧手记服务探针跳过；20套Chrome共199通过。全部49份子报告在`regression/`。 |
| [Godot组合](author-native-all.json) | 11套67组902断言；两处产品代码在组合期间修正，`sourceUnchanged=false`保留。`regression/native-entity_canvas_godot.json`为最终native-v3的7组88断言，源码未变。 |
| [独立范围总表](qa-summary.json) | 原自然史与各客户端支路、逐组通过范围、版本、指纹和清理。某原run整体失败时，只接收其中明确已完成组及后续修复复验。 |
| [原自然史](qa-natural-v1.json) | 原实例、平台、两次实际绘制及双方返回，296次walk、2次paint；旧材料／实体／手记／回执保持，来源正常生产单列。 |
| [采用矩阵](qa-adoption-partial-v1.json)／[协议与历史](qa-protocol-faults-history-v1.json) | 原子采用、权限和并发、提交前后故障、原ID及超过最近50条的精确edit。采用矩阵所在原run整体false保持。 |
| [整数损坏反例](qa-storage-counterexample-v1.json)／[补充](qa-storage-corruption-supplement.json)／[v2复验](qa-storage-fix-v2.json) | SQLite REAL值被v1读取截断；v2拒绝原反例和补充字段，合法原自然史可继续读取。 |
| [Python CLI与恢复](qa-python-cli-recovery.json)／[坏证据](qa-python-evidence-partial.json)／[预算](qa-python-budget.json) | 独立5组；queries4实际原起点等于目标，returned=true但budget_exhausted，不能写成“未返回”。 |
| [Godot恢复v2](qa-native-recovery-v2.json)／[异实例反例](qa-native-foreign-failure-v2.json)／[v3复验](qa-native-v3-capability-foreign.json) | 原命令、7种坏HTTP证据、旧记录4、未知／缺失能力、记录5异实例提示；原记录不丢失、不向错误实例发命令。 |
| [最终三阶段](qa-native-three-stages-v3.json)／[请求记录](qa-native-three-stages-traffic.json) | 原阶段副本，5 GET、0 POST、39断言，原阶段hash不变。镜头调整用于直接看清原平台，实际鼠标悬停作者。 |
| [Chrome最终13项](qa-chrome-13.json) | 11类坏报告、实际独立输入、明确标记的合成反例、移动布局及0世界请求。旧`qa-chrome-12.json`第三项标题不精确，保留作历史，不用它证明真实新快照。 |
| [worker交付](worker-python-handoff.json)／[只读审查](worker-readonly-review.md) | 自检和默认入口复核；不是另一次独立活动验收。 |
| [最终源码核对](final-source-audit.json) | core-v2、native-v3、web-v1与当前源码匹配；组合期间5处产品／测试差异逐项保留。各版manifest记录历史冻结状态，冻结时的“待验证”备注不改写，后续以本目录结果为准。 |
| [作者数据库清理](author-completed-run-cleanup.json)／[独立客户端清理](qa-client-cleanup.json)／[补图清理](qa-visual-cleanup.json) | 已结束临时数据库删除，保留文件指纹不变。组合入口的`removedTemporaryBinaries`另记临时二进制清理。 |

`author-native-first-ui-failure.json`保留按钮不可见导致未提交的首轮失败；`historical-harness-failures/`保留独立驱动的旧路径、数字序列化和过强断言失败。它们与存储类型／pending的实际产品缺陷分别解释，不能合计为成功测试。

截图：同一原平台的[空白](screenshots/original-platform-blank.png)、[第一幅](screenshots/original-platform-first.png)、[两人续画](screenshots/original-platform-both.png)、[第二位作者](screenshots/original-platform-both-second-author.png)，以及报告页[历史与作者](screenshots/history-mobile.png)、[queries4预算](screenshots/query4-mobile.png)。四幅原平台图及移动报告已目检。没有真人趣味或长期社会关系验收，真实模型调用0。
