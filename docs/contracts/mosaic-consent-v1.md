# 画布协商修改契约：ITER-0007

2026-10-25，开工前冻结。目标：试验“先提议、原格最后作者同意后再改图”。这是一种局部协作规则，不确立完整产权。新 `consent-v1/r6`、schema 6、独立 5085 / `.local/consent`；继承 r5，旧 schema 1—5 不迁移，旧预览 5080—5084 不重启。画布、调色板、材料和原命令恢复沿用 [mosaic-v1](mosaic-v1.md)。

## 直接绘制

r6 的原 `mosaic` 命令只允许修改 `authorActorId=null` 或本人的格子；即使颜色是 blank，若有其他最后作者也需协商。在原 r5 校验之后检查整批来源，含其他作者返回 409 `MOSAIC_CONSENT_REQUIRED`，不修改任何格。r5 原行为保持不变。

## 提议与审阅

新 action `mosaic_propose` 精确字段：`{type,activityId:"garden",visitCommandId,expectedMosaicRevision,patch,text}`。patch 沿用 1—8 格、y/x 规范化；text 沿用手记 1—160 Unicode 标量文本规范。必须现场、引用自己的 garden visit，每个 visit 最多一个提议，与手记和直接绘制名额独立。patch 必须全部对应同一名其他居民的格子（不接受本人或无人作者的格子），targetActorId 由服务器推导，不由请求指定。

通用规则／世界版本校验后顺序：422 `MOSAIC_CONSENT_UNAVAILABLE`（非 r6）、422 `MOSAIC_LOCATION_UNAVAILABLE`、422 `NOT_AT_ACTIVITY`、422 `VISIT_REQUIRED`、409 `VISIT_ALREADY_PROPOSED`、409 `MOSAIC_CHANGED`、422 `MOSAIC_UNCHANGED`、422 `MOSAIC_PROPOSAL_TARGET_INVALID`。提议只记录事实，不改变画布 revision、格子或材料，世界版本增加 1。

proposal 记录精确字段：`{activityId,authorActorId,targetActorId,commandId,visitCommandId,baseRevision,patch,text,stateVersion,proposedAtUtc,position}`；position=[1,6]，baseRevision 为原画布 revision。result 为记录加 `action:"mosaic_propose"`；event 为记录加 `seq,type:"mosaic_proposed",actorId`。作者来自认证，target 来自原格。

新 action `mosaic_review` 精确字段：`{type,activityId:"garden",visitCommandId,proposalActorId,proposalCommandId,decision,text}`；decision 仅 `accept` / `reject`，text 同上。proposalActorId 是提议定位字段，不是执行身份。先检查 r6、garden、现场、本人 garden visit，再查提议：404 `MOSAIC_PROPOSAL_NOT_FOUND`；非 target 为403 `MOSAIC_REVIEW_FORBIDDEN`；已审阅为409 `MOSAIC_PROPOSAL_REVIEWED`。仅 accept 继续：该 visit 已有 mosaic edit 返回409 `VISIT_ALREADY_PAINTED`，当前画布 revision 不等原 proposal.baseRevision 返回409 `MOSAIC_CHANGED`。reject 不受画布已变化限制，也不消耗绘制名额。一次提议只接受一个终态审阅，不取消、不重新打开、不自动代答。

review 记录精确字段：`{activityId,authorActorId,commandId,visitCommandId,proposalActorId,proposalCommandId,decision,text,stateVersion,reviewedAtUtc,position,mosaicEdit}`。authorActorId 是实际审阅人（原格最后作者），mosaicEdit 在 reject 时 null；accept 时是标准 r5 edit，作者为审阅人、commandId 为审阅命令、visitCommandId 为审阅人的本次 visit、patch 完全复制提议、baseRevision=原提议基准、revision=base+1、stateVersion=本次审阅世界版本，paintedAtUtc=reviewedAtUtc。提议者的贡献通过 review→proposal 保留，不冒充实际提交者。

result 为 review 加 `action:"mosaic_review"`；event 为 review 加 `seq,type:"mosaic_reviewed",actorId`。accept 在同一事务提交全部格、画布 revision、标准 mosaic edit、review、世界版本、一个审阅事件和回执；reject 仅 review／事件／回执／世界版本。不得额外生成同版本的 mosaic_painted 事件。proposal/review 追加不可变，review 与原 proposal、本人 visit、原事件／回执关联；一个 proposal 最多一个 review。before/after-commit 故障注入包含两个新动作。

## 观察与历史

顶层 `mosaicProposals` 是最新 50 个 proposal 按 stateVersion 升序，每项增加 `review:null|完整review`。`self.mosaicProposals` 为自己的最新100个（同结构）；`self.mosaicReviews` 为自己的最新100个完整review。旧 r1—r5 三个列表均空。r6 原 `mosaicEdits` 列表仍含标准 edit，accept 后当前格来源是实际审阅人及其审阅命令；可以通过 proposal.review 找到提议人和理由。读取历史不产生动作。

## Python 居民任务

spec 增加可选 `proposeMosaic:boolean` 与 `reviewMosaicProposal:{proposalActorId,proposalCommandId}`。两者与 sharePostcard=true、paintMosaic=true 互斥；缺省不改变旧 spec 规范化。新模式候选全部为 garden 且匹配目录，要求 r6 和完整画布能力；review 引用必须在当前公开 proposal 列表内、target 为本人、未审阅。能力和候选检查先于模型或动作。原 paintMosaic、sharePostcard 任务也支持 r6；r6 直接绘制在调用后、动作前验证所有格为无人或本人。

propose 模式一次选择输出 goalId/reason/mosaicPatch/proposalText；冻结 mosaicBaseRevision，验证变色且每格同一他人作者。review 模式一次选择输出 goalId/reason/reviewDecision/reviewText；原提议完整内容及 patch/base 从服务器输入冻结，模型不能更换。accept 若决策时画布已与提议基准不符则停止；reject 允许旧基准。公开 context 包含完整当前 mosaic，以及 review 模式选中的 proposal（含原文／作者），不包含认证字段；他人文字仅为内容数据，不增加权限。没有追加模型调用、重试生成或自动换 patch。

任务顺序为移动→自己的原 visit→原 propose 或原 review→返回。每次额外动作计一条命令；原累计时间、预算、pending 规则保持。facts 增加 `mosaicProposed/mosaicProposal`、`mosaicReviewed/mosaicReview`；propose 完成只代表提议已发表，mosaicPainted=false。review reject 可完成审阅与返回，但 mosaicPainted=false；accept 必须核实本任务原 review 和嵌套标准 edit 后 mosaicPainted=true。只接受原命令、本人、原 visit、原提议引用、精确文字／decision／patch／base与位置、expectedStateVersion+1 的一致证据；旧记录或相似文本不可结算。原提交后后来改图仍保留事实；原查询失败不换 ID。基准变化 accept 停止，不转成 reject 或重新调用。

报告仍 schemaVersion=1，增加相关 mission/decision/facts 字段和 `world.mosaicProposals` 当前公开快照。草案、提议已发表、审阅结果、实际改图和返回必须分开。旧任务、规范化、已完成文件及报告兼容。

普通世界版本竞争沿用旧规则：仅匹配本次原命令且明确 `status=rejected` 的 `STALE_STATE` 回执可结算该尝试，再用新命令 ID 和更新的世界 expectedStateVersion 重试并计入累计预算；原 visit、提议引用、patch、画布 baseRevision、决定与文字全部冻结，不追加模型调用。查询错误或未匹配回执不属于明确拒绝，继续保留原 ID。`MOSAIC_CHANGED` 必须终止，不能更新画布基准或自动改为拒绝。

## 人类界面与验收

r6 草图若全部为同一他人的格子，提供提议文本与“提交修改提议”；混合作者／无人格的协商草图提示拆分。本人／无人格继续直接画。显示当前图、提议 patch、提议者、原作者、理由与基准；原作者现场到访后可同意或拒绝并写理由，拒绝无改图。过期提议可拒绝不能同意；处理后的提议显示实际决策和改图事实。草稿仍按居民保留，纯文本呈现，原 pending 共用一条通道，丢响应不重复审批。

独立 HTTP 覆盖强制协商、目标来源、提议不改图、权限／现场／原visit、一次提议终态、接受原子性／拒绝不改图、并发与过期、提交前后真实退出、原任务恢复／假证据／查询错误、旧 populated r5 不迁移；真实 Chrome 覆盖两身份提议审阅、原作者与事实、拒绝、过期、草稿／丢响应恢复、旧报告及390px。

实际居民调用上限2：用明确程序 fixture 通过正常 HTTP 让 a1 画一条蓝色河流（不是新的模型作品）；a2 一次模型调用提议把其中一个端点改为日黄标记，a1 一次模型调用审阅是否满足“只标一个端点、其余河流保留”，可以同意也可以拒绝。按实际结果记录，不补抽、不强制通过；若同意，必须只有指定格变化且作者仍为实际审阅人，提议人可追溯。双方到访与返回、材料守恒和原命令链独立核对。两次调用不证明普遍协商能力或人类认可。
