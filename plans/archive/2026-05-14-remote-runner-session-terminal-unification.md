<!--
职责：为实现 agent 定义一个 active task 合同，让范围、验收、验证和交接可执行。
边界：不要在这里累积长期架构事实、原始日志或无关 follow-up 想法。
-->

# Remote Runner Session 即持久 Terminal

## 目标

把 Remote Runner 的公开工作上下文统一回 `session`：用户创建 session 后得到一个持久远程 shell/terminal，上下文在多次命令和输入之间连续保留；`session exec`、`session send`、`session read`、`session destroy` 都挂在同一个 session 下。当前 PR #6 中新增的顶层 `terminal` 能力只作为 tmux backend 实现素材，不作为长期公开产品 API。

## 非目标

- 本任务不继续扩展顶层 `remote-runner terminal ...` API。
- 本任务不实现完整实时 streaming daemon、websocket、多人协作权限、PTY resize、asciinema 记录格式或浏览器 UI。
- 本任务不支持依赖 `startup_commands` 的 Windows/WSL 持久 session；若遇到该机器类型，必须返回清晰错误，不假装支持。
- 本任务不删除 `session command show/wait/stop` 的结构化查询能力；如果实现路径变化，CLI 合同仍应可用。
- 本任务不把真实机器 host、账号、密码、key 内容或私人路径写入仓库。

## 当前仓库事实

- 入口规则：`AGENTS.md`
- 初始化契约：`harness/bootstrap-contract.md`
- 当前功能项：`F-020`
- 相关文件/模块：`remote_runner/remote_session.py`、`remote_runner/remote_backend.py`、`remote_runner/remote_state.py`、`remote_runner/cli.py`、`tests/test_remote_runner_mvp.py`、`tests/test_remote_runner_launch_suite.py`、`tests/test_remote_runner_real_integration.py`、`docs/reference/REMOTE_RUNNER_API.md`、`docs/specs/machine-session-file-mvp.md`、`SKILL.md`、`README.md`。
- 已知约束：当前 `F-019` 已把 tmux terminal 做成顶层 API；用户已明确指出这会导致职责不清，要求 session 承担持久 terminal 语义。

## 允许改动

- 修改 session state schema，使 session 记录 backend、remote terminal/tmux 名称、transcript/log 路径、cursor 和 destroyed backend 状态。
- 扩展 `RemoteSessionManager`，让 `session create` 创建持久 tmux backend，`session exec` 在同一 backend shell 中执行并返回 command_id、exit_code、stdout/stderr、日志路径，`session send/read` 提供原始 terminal 输入和 transcript 读取。
- 复用或迁移 F-019 的 tmux backend 代码，但公开 CLI 和文档应以 `session` 为核心。
- 更新 tests、README、API spec、getting-started、Remote Runner skill、feature list、progress 和 handoff。
- 更新 draft PR #6 的标题/正文或后续说明，避免宣称顶层 terminal 是目标 API。

## 禁止改动

- 不要求上层系统直接调用 raw ssh、scp、rsync、tmux 或 sshfs。
- 不把 session transcript 或 command state 设计成只存在当前 Python 进程内存；新 CLI 进程必须能恢复读取。
- 不破坏 machine 配置、file put/get/list、run once 和已存在的 session command 查询入口。
- 不在真实机器测试中写入 `REMOTE_RUNNER_REAL_TEST_CWD` 以外的目录。
- 不在仓库中记录真实机器敏感信息。

## 验收标准

- `remote-runner session create --machine <id> --cwd <remote_cwd> --json` 创建一个持久 session，返回 backend、transcript/log 引用，并在远端建立可销毁的 backend shell。
- `remote-runner session exec --session <session_id> --cmd <cmd> --json` 在同一个 session shell 中执行；前一次 `cd`、`export` 等 shell-local state 会影响后续 exec。
- `session exec` 返回稳定的 `command_id`、`exit_code`、`stdout`、`stderr`、timestamps、duration 和本地 log；命令边界不能只靠聊天记忆。
- `remote-runner session send/read --session <session_id> --json` 支持原始输入和 transcript/cursor 增量读取。
- `remote-runner session destroy --session <session_id> --json` 销毁远端 backend session，同时保留本地 session state、command logs 和 transcript。
- 顶层 `remote-runner terminal ...` 不再出现在目标 API、README、getting-started 或 skill 的主路径中。
- 默认本地测试、launch suite 和 opt-in Linux/SSH 真实集成测试通过。

## 验证命令

```sh
./scripts/harness-check.sh
python3 -m pytest tests/test_remote_runner_mvp.py -q
python3 -m pytest tests/test_remote_runner_launch_suite.py -q
python3 -m pytest tests/test_remote_runner_real_integration.py -q
python3 -m pytest -q
git diff --check
REMOTE_RUNNER_RUN_REAL_TESTS=1 REMOTE_RUNNER_REAL_MACHINE=<machine_id> REMOTE_RUNNER_REAL_TEST_CWD=<remote_cwd> python3 -m pytest tests/test_remote_runner_real_integration.py -q
```

真实机器验证默认 opt-in；未运行时必须在 evidence 中说明原因。真实验证只允许写入 `REMOTE_RUNNER_REAL_TEST_CWD`。

## Evidence 记录要求

验证通过后，将命令、结果、关键输出摘要或 artifact 路径写入 `harness/feature_list.json` 的 `evidence`。真实机器 evidence 只能记录抽象机器类型、测试目录由环境变量提供、命令类型和结果，不记录 host、账号、密码、key 内容或私人路径。

## 完成定义

- 请求行为已实现。
- 非目标没有被触碰。
- 上方验证命令已运行；未运行的命令必须说明原因。
- `harness/feature_list.json` 状态和 evidence 已更新。
- 职责、接口、setup 或边界改变时，docs、注释、测试或 harness 文件已更新。
- `harness/session-handoff.md` 写明当前状态、风险和下一步。
- 清洁状态检查已说明。

## 阻塞条件

- 无法让 `session exec` 在同一持久 shell 中稳定恢复 command boundary 和 exit code。
- 真实 Linux/SSH 蓝本缺少 tmux 且第一实现需要 tmux；需决定是否安装依赖、降级为 shell backend，或先标为 blocked。
- 需要在安全测试目录以外写真实机器文件。
- 需要保留顶层 `terminal` 公开 API 才能通过验收。

## 下一步最佳动作

1. 先让 session state 和 manager 接管 F-019 的 tmux backend，再把 CLI 和测试从 `terminal` 迁移到 `session send/read/exec`。
