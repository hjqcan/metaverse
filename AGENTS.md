# 协作约定

- 使用 subagent 要谨慎，只允许 GPT-6 系列模型。别说废话，直接报告结果和证据。
- 先读 `docs/00-project-charter.md`、`docs/09-decisions-and-open-questions.md`，区分确认方向、建议与实际实现。
- 多账号研发使用 Orca orchestration；先读取当前安装版本的 `orchestration` skill。
- 账号绑定与启动见 `docs/12-multi-account-agents.md`。账号配置保存在被 Git 忽略的 `.local/agents/`；凭据由现有 Codex/Orca 管理，不复制进项目。
- 派工明确目标、可修改文件、约束和可观察验收；同一文件同一时间只交给一个写入者。协调者负责集成。
- worker 使用当前 Dispatch 下发的身份回报；完成后由协调者接续或释放。子 agent 不自行扩展账号、任务或并发规模。
