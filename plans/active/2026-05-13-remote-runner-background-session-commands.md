<!--
职责：为实现 agent 定义一个 active task 合同，让范围、验收、验证和交接可执行。
边界：不要在这里累积长期架构事实、原始日志或无关 follow-up 想法。
-->

# Remote Runner 后台会话命令

## 目标

实现 Remote Runner session 下的一等后台命令能力：用户或上层 agent 能启动长时间运行的远程命令并立即拿到 `command_id`，之后可用稳定 CLI 查询状态、读取有界输出、等待完成或停止命令。现有短命令 `session exec` 的同步等待行为必须继续可用。

## 非目标

- 本任务不实现完整 attach 到持久交互式 shell，不做 stdin streaming、PTY resize、实时 WebSocket/output delta。
- 本任务不引入 tmux、sshfs、mount、远程常驻 daemon 或必须手动 ssh 的工作流。
- 本任务不重做 `run once` profile/report 层；若需要集成 `run once`，只做不破坏现有行为的最小调整。
- 本任务不解决 SSH host key policy、系统钥匙串、认证配置重构或 Windows+WSL 后台命令完整语义；若第一切片无法安全支持 `startup_commands` 机器，必须显式返回可诊断错误并记录后续项。
- 本任务不把真实机器 host、账号、密码、key 内容或私人路径写入仓库。

## 当前仓库事实

- 入口规则：`AGENTS.md`
- 初始化契约：`harness/bootstrap-contract.md`
- 当前功能项：`F-018`
- 相关文件/模块：`remote_runner/remote_session.py`、`remote_runner/remote_backend.py`、`remote_runner/remote_state.py`、`remote_runner/cli.py`、`remote_runner/remote_run.py`、`tests/test_remote_runner_mvp.py`、`tests/test_remote_runner_launch_suite.py`、`tests/test_remote_runner_real_integration.py`、`docs/reference/REMOTE_RUNNER_API.md`、`docs/specs/machine-session-file-mvp.md`、`docs/testing/remote-runner-launch-acceptance.md`。
- 已知约束：当前 `RemoteSessionManager.exec()` 会 reserve session、调用 `backend.run()` 阻塞到命令结束、再持久化 command record；`ParamikoRemoteBackend.run()` 每次新建 SSH 执行命令并读取完整 stdout/stderr；`session logs` 只列出已完成记录；`run once` 依赖同步 exec；状态根为 `~/.remote-runner/`，测试可用 `REMOTE_RUNNER_STATE_DIR` 覆盖。
- 上游需求：GitHub issue #3 要求 `run_and_wait`、`run_background`、`get_command_result` 三种语义，服务 Socratic Agent Generator 的 session-bound lab machine tool。
- 参考设计：OpenAI Codex 的 command exec/unified exec 将 process id、输出增量、终止和最终结果分开；Remote Runner 不能照搬内存进程表，因为本 CLI 跨进程运行，必须以本地 state 和远程日志/status 文件作为恢复来源。

## 允许改动

- 扩展 Remote Runner CLI：`session exec --mode wait|background`，以及 `session command list/show/wait/stop` 或等价清晰子命令。
- 扩展 session command state schema，新增 `command_id`、`status`、`mode`、`remote_pid` 或 backend reference、stdout/stderr 本地/远程日志引用、truncation 标记、started/ended timestamps、duration、exit_code、error。
- 扩展 SSH backend，优先实现 Linux/SSH 后台命令 MVP：远端写 status/stdout/stderr/pid/exit code，CLI 查询时同步必要摘要到本地状态。
- 更新 `docs/reference/REMOTE_RUNNER_API.md`、MVP spec、getting-started/testing 文档和 Remote Runner skill 中与 session command 语义相关的内容。
- 新增或扩展 fake-backed 单元测试、launch acceptance 测试和 opt-in 真实机器验证。
- 更新 harness：`harness/feature_list.json`、`harness/progress.md`、`harness/session-handoff.md`。

## 禁止改动

- 不删除或破坏现有 `session exec` 默认同步行为、`file put/get/list`、`run once`、机器配置和 launch acceptance 默认测试。
- 不要求用户或上层系统直接使用 raw ssh/scp/rsync/tmux/sshfs。
- 不把真实机器敏感信息写进测试 fixture、docs、handoff、progress、commit message 或 issue comment。
- 不让后台命令只存在于当前 Python 进程内存；新 CLI 进程必须能恢复查询。
- 不在真实机器测试中写入 `REMOTE_RUNNER_REAL_TEST_CWD` 以外的目录。

## 验收标准

- `remote-runner session exec --mode wait` 或默认 `session exec` 保持现有短命令 JSON 合同，已有测试继续通过。
- `remote-runner session exec --mode background --session <id> --cmd <cmd> --json` 能快速返回 `command_id`、`status=running`、`session_id`、`machine_id`、`cwd`、`started_at` 和日志/status 引用，不等待长命令结束。
- `remote-runner session command show --session <id> --command-id <id> --json` 能跨 CLI 进程查询后台命令，返回 `running|exited|failed|timed_out|stopped` 之一、bounded stdout/stderr excerpt、truncation 标记、exit_code（若已结束）和本地日志路径。
- `remote-runner session command wait --session <id> --command-id <id> --timeout <seconds> --json` 只限制本次等待调用，不误杀远程命令；命令仍运行时返回 running/timeout-style poll result，命令完成时返回最终 exit_code。
- `remote-runner session command stop --session <id> --command-id <id> --json` 能对后台命令发出停止请求，状态和日志保留；已结束命令重复 stop 有清晰结果。
- 后台命令 stdout/stderr 较大时 JSON 只返回有界摘要，完整内容或可恢复位置保存在本地/远端日志引用中。
- session state、command state、logs 在非零 exit、stop、查询失败和 CLI 中断后仍可恢复。
- 在真实 Linux/SSH 蓝本的安全测试目录内，能启动一个会持续写输出的后台命令，轮询到中间输出，再等待完成或 stop，并清理探针文件。

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

- 无法设计跨 CLI 进程可恢复的后台命令状态，只能依赖当前进程内存。
- 真实 Linux/SSH 蓝本不可达，且 fake-backed 测试不足以证明关键行为。
- 需要在安全测试目录以外写真实机器文件。
- 需要用户决定是否接受 tmux/daemon/PTY 作为 MVP 前提。

## 下一步最佳动作

1. 先更新 API/spec，确认 `mode background` 与 `session command show/wait/stop` 的 JSON 合同。
2. 设计 command state 与远程状态文件布局，保证新 CLI 进程可恢复。
3. 以 fake backend 测试驱动实现，再跑真实 Linux/SSH opt-in 验证。
