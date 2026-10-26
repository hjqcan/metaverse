# 多账号 Agent 研发准备

日期：2026-10-25。适用环境：本机 Linux、Orca 1.4.240、Codex CLI 0.164.0。

本文件描述研发工具准备，不表示世界引擎或居民 Agent 已实现。验收记录在本文件末尾；实际账号标识及启动回执只保留在本机 `.local/agents/`。

## 1. 组织方式

由当前主 Agent 负责协调，通过 Orca orchestration 管理多个独立 Codex 进程。账号提供登录和使用额度，研究、构建、测试是任务角色，两者不固定绑定。所有 worker 只使用 GPT-6 系列，默认沿用当前选择的 `gpt-6-astra`、`xhigh`。

会话内 subagent 与独立 Codex worker 是两种机制。前者共享当前会话的并发限制，不能作为切换 ChatGPT 账号的接口；后者各自绑定登录环境，由 Orca 的 Run、Task、Dispatch 跟踪工作。新增账号不会自动提高平台允许的额度或解除限制。

初期按需启动，每个账号先分配一个 worker，依据实际任务和运行结果调整。遇到账号额度或登录失败，记录状态并暂停该任务，不自动换账号重放未完成任务。该并发安排由协调者执行；当前脚本负责账号绑定和启动，不是常驻调度器或自动负载均衡服务。

## 2. 账号绑定

辅助工具 `scripts/agent_accounts.py` 只使用 Python 标准库。它读取 Orca 账号清单，将别名固定到具体账号身份及现有 Codex 状态目录，不复制认证文件、不切换全局默认登录。

```bash
python3 scripts/agent_accounts.py list
python3 scripts/agent_accounts.py bind newton-ming --account system
python3 scripts/agent_accounts.py bind hjqcan --account <Orca账号ID>
python3 scripts/agent_accounts.py doctor
```

首次绑定可通过全局参数 `--orca /absolute/path/to/orca` 指定本次会话使用的 Orca CLI；后续沿用已保存路径。绑定信息写入 `.local/agents/accounts.json`，被 Git 忽略。默认账号也校验具体账号 ID，系统登录变化时需要明确重新绑定。

启动前同时检查 Orca 元数据、认证文件中的账号 ID 以及 `codex login status`。这些检查只证明本地身份和登录缓存；真实模型调用成功需要运行任务验证。

Codex 通过自己的 `CODEX_HOME` 指定配置、认证和会话目录，使用 `--no-daemon` 避免接入其他进程的共享服务器。该设置只作用于新进程，不改变协调者环境或其他会话。[官方环境变量说明](https://learn.chatgpt.com/docs/config-file/environment-variables)、[认证说明](https://learn.chatgpt.com/docs/auth)。

## 3. 启动及监督

当前 Orca CLI 的 `worker-start` 没有 Codex 账号选择参数，因此采用其技能文档规定的自定义命令入口，再将已有终端交给 `worker-start --terminal` 管理。终端创建只是启动，不代表任务已受监督或已完成。

```bash
python3 scripts/agent_accounts.py start newton-ming --title research
python3 scripts/agent_accounts.py start hjqcan --title build
```

这两个命令返回 Orca 终端 handle。协调者使用当前安装版本的 `orchestration` skill 完成后续流程：

1. 创建或绑定本轮 Run，明确目标与停止条件。
2. 检查新终端已进入 Codex 就绪状态，确认账号和模型；不把登录提示当作就绪。
3. 使用 `orchestration worker-start --terminal <handle> --worktree current --spec <完整任务>` 创建受监督任务。
4. 收取问题、进度和 `worker_done`，核对 Task、Dispatch 和实际证据。
5. 完成后接续明确的新任务，或执行 `worker-release` 并读取其实际结果。此自定义启动方式产生的终端在当前 Orca 中标记为 `external_terminal`，release 返回 `retained`、`processAction: none`，不会关闭进程。由创建终端的协调者保存证据，确认任务结算且空闲后发送 `/exit`，再用 `terminal wait --for exit` 核实进程退出。不要把 retained 当成已回收，也不要据此关闭其他终端。

模型和 effort 在账号终端启动时确定，`worker-start --terminal` 不再次传模型参数。Orca 终端 handle 只在对应 runtime 内有效，重启后必须重新发现。

账号路由以子进程的 `CODEX_HOME` 和真实认证身份为准；自定义命令启动并不自动更新 Orca 界面的账号选择状态，因此不能仅依据界面默认账号标识判断 worker 的实际账号。

当前版本可能返回 `turn_start_unobserved` / `outcome_unknown`，即输入已送达，但回合开始事件未被观测。保持原 Task/Dispatch，通过 `worker-show`、`worker-read` 和邮箱继续核实；不得当成启动失败重发任务。实际 `worker_done` 能正常结算该 Dispatch。

## 4. 工作分工

- 每个任务写明目标、输入、可修改路径、约束和验收条件。
- 只读调研可以共享当前 checkout；写代码时明确文件所有权，出现重叠则串行或使用明确分配的独立工作区。
- worker 不自行启动后代、增加任务或放宽验收。协调者按用户目标安排下一轮。
- 构建者提交实现和验证结果；验证者按约定场景核查。不同账号不等于结论天然独立。
- 密钥、认证文件、完整环境变量和账号使用数据不进入公共文档或 Git。

## 5. 后续加入账号

在本机 Orca 添加 Codex 账号并完成登录，也可以使用 `orca account add --agent codex` 发起登录流程。然后执行 `list` 找到新 ID，`bind <新别名> --account <ID>`，再执行 `doctor <新别名>`。

最后运行一个小任务，核对实际账号、模型、Task/Dispatch、结果与回收。验证后即可分配研究、构建或测试角色，无须改调度代码。脚本目前只覆盖本机 Linux 的系统默认账号和 Orca host 托管账号；远端和 WSL 需单独验证。

## 6. 本轮验收

本轮以两个真实 ChatGPT Pro 登录完成以下验证：

| 本机别名 | 实际模型 | 任务 | 结果 |
|---|---|---|---|
| `newton-ming` | GPT-6-Astra / xhigh | 读取项目文档，归纳最小世界的三项前置决定 | `worker_done: succeeded`，Task 已完成 |
| `hjqcan` | GPT-6-Astra / xhigh | 提出资源不足、重复命令、重启恢复的最小验收场景 | `worker_done: succeeded`，Task 已完成 |

两个独立 Codex 进程同时存在，任务本轮依次派发。已通过各终端 `/status` 核对不同真实账号与模型，并由 worker 核对自身账号别名、状态目录和 ChatGPT 登录。已处理并确认全部完成消息，保存本机回执；两个临时 worker 最终均正常退出，退出码为 0。

另有 6 项账号隔离回归检查通过，覆盖账号消失、默认登录变化、Orca 缓存与认证身份不一致、父子环境隔离、API 认证覆盖及非 GPT-6 模型拒绝：

```bash
python3 -m unittest discover -s scripts -p 'test_*.py' -v
```

证据保存在被 Git 忽略的 `.local/agents/verification/`。本轮验证的是账号绑定、实际模型调用和任务通信；游戏验收场景仍是建议，没有实际世界测试结果，也未进行高并发或长期运行测试。
