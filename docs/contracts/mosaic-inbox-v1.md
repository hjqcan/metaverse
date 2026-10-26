# 画布提议收件箱契约：ITER-0008

2026-10-25，开工前冻结。修复：当前公共观察只含最近 50 条提议，老的未处理提议会被已处理记录挤出；人类界面和新建审阅任务都无法再找到它。原 r6 的提议、审阅、画布、预算和原命令规则全部沿用 [consent-v1](mosaic-consent-v1.md)，不增加规则版本、动作或 schema。新预览 5086 / `.local/inbox` 仍为 `consent-v1/r6`；旧 5080—5085 不重启、不迁移。

## 新只读接口

所有路径位于 `/v1/worlds/{worldId}`，沿用认证、公开内容与标准 envelope。GET 不改变世界版本、事件、回执、session 或数据库逻辑内容。旧 r1—r5 返回 422 `MOSAIC_CONSENT_UNAVAILABLE`，不访问缺失表。新 r6 observation 仅追加 `mosaicProposalInbox:{version:1,maxPageSize:20}`，原最近 50／100 列表和顺序不变；旧场景不追加此字段。

`GET /mosaic-proposals` 查询只允许 `scope`、`status`、`before`、`limit`，每个最多出现一次。scope=`received|sent|all`，默认 received；status=`pending|reviewed|all`，默认 pending；before 可省略，出现时为正整数且在 Int64 内，排除 proposal.stateVersion >= before；limit 默认20，显式值为1—20纯十进制整数。空值、未知／重复键、符号、溢出、未知枚举返回400 `INVALID_REQUEST`。筛选身份只来自认证，不接受 actorId 查询。

响应在标准 envelope 内增加：

- `query:{scope,status,before:null|integer,limit}`，回显规范化查询。
- `counts:{pending,reviewed,all}`，按 scope 在完整数据库计数，不受 before/status/limit 影响，all=pending+reviewed。
- `items:[完整proposal加review:null|完整review]`，按 proposal.stateVersion 严格降序，最多 limit。
- `nextBefore:null|integer`，只有过滤后的更老记录确实存在时为本页最后一项的 proposal.stateVersion，否则 null。并发新提议不进入持有旧 before 的更早页面，不使用 offset。

received 为 targetActorId=本人，sent 为 authorActorId=本人，all 为本世界全部公开提议。pending 是无 review，reviewed 是已终态；过期而未决定仍属于 pending，不能自动拒绝。counts、items、嵌套 review 和 envelope 版本来自同一只读事务。分页期间别人的审阅可以改变过滤集合；不承诺跨请求快照，刷新从第一页重新读。

`GET /mosaic-proposals/{proposalActorId}/{proposalCommandId}` 不接受查询参数。两段均符合现有 `Protocol.ValidCommandId`，否则400。返回标准 envelope 加 `proposal:完整proposal加review`；任一已认证居民可读公开内容，审阅权限不变。完整库不存在为404 `MOSAIC_PROPOSAL_NOT_FOUND`；可以读取公开最近50条以外的记录及已完成记录。

## 人类界面

capability 存在时以新接口读取协商区，默认“发给我的”＋“等待决定”。三个范围为发给我的／我提出的／全部提议，状态为等待决定／已处理／全部，展示完整库相应计数和当前页，不把最近列表冒充全部。每页最多20，提供更早、返回较新页及回到最新；不无限自动拉取。筛选／游标按身份隔离，切换身份不泄露上一身份待办和文字；提议与审阅草稿仍按原身份保存。

轮询原观察时更新当前页；过期请求、切换范围或身份前发出的响应不得覆盖新状态。请求失败保留旧内容并标明未更新，禁用受影响审阅，不假装待办为0；恢复后可继续。保持已有项 DOM 身份与正在输入的理由、焦点和选区，其他提议插入不打断编辑。提交后的列表按真实结果更新，原 pending 全程共用，不重复审阅。

每项继续展示提议人、目标作者、patch、基准、原文、决定与实际改图。旧基准只可拒绝；现场和本人到访规则不变。协商区提供清楚的当前位置／去花园提示和“记录花园到访”按钮，复用原 visit 提交通道，不自动移动或审阅。原按钮和所有草稿恢复保留。

兼容旧 r6 服务缺少 capability 的情况：继续读原最近50条并明确说明范围有限，不发送不存在的新接口。r1—r5 无协商区。旧协商浏览器用例可明确切到全部／全部检验原完整流程，新套件单独验收默认收件箱。

## Python 审阅任务

原 spec、一次选择、模型输出与报告格式不变。仅新建 reviewMosaicProposal 任务：有 capability 时调用详情接口定位原引用，再构造原完整决策输入；无 capability 时保留最近公开列表路径。校验 schema、rules、认证 actor、无error、非负整数版本／cursor、原作者与原命令完全一致、有效完整 proposal、target=本人、未reviewed。任何错误／异常都在模型或动作前失败，不回退到相似记录，不换引用。

详情 envelope.stateVersion 必须不早于 proposal.stateVersion。若详情版本超出原观察，重新 observe 一次并核对原世界／身份／规则，要求观察版本 >= 详情版本，再冻结当前画布与目标；期间其他审阅最终仍由原命令规则拒绝。新任务累计预算从预检成功后持久化开始；详情读取不计世界命令，不调用模型。已存在任务、未决恢复和完成报告不重新选提议、不重新读取详情或重置预算。报告的 decision.mosaicProposal 保留完整选中提议，即使 world.mosaicProposals 最近列表不包含它。

## 验收与真实调用

独立 HTTP：超过50／100记录仍可找到最早待办，完整计数、所有范围／状态、严格查询、稳定游标、新插入和审阅变化、详情权限与原审阅权限、GET 逻辑库完全不变、旧 populated r6 schema不迁移、r1—r5兼容、Python原引用详情输入／错误绑定先于模型、旧服务回退和持久任务恢复。

独立 Chrome：默认待办定位老提议、范围／状态与分页、作者和实际结果、理由焦点跨更新保留、错误及迟到响应、身份隔离、现场到访入口、丢响应恢复与390px。旧套件继续回归；worker 自检与独立验收分开。

真实模型调用上限2：同一隔离 r6 世界先以明确程序种入三格河流；a2 一次真实调用发表原单格端点提议并返回；再以程序生成51条更新且已拒绝的提议，不改图，明确不计模型作品；a1 根据收件箱定位唯一待处理原提议，按真实引用新建任务，一次调用独立接受或拒绝并返回。验证最初提议已不在公开最近50列表、收件箱仍可发现、详情完整进入真实模型输入、决定与实际改图一致、材料和数据库不变式。无补抽，不扩大账号或常驻调度。
