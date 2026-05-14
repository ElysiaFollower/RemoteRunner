<!--
职责：为实现 agent 定义一个 active task 合同，让范围、验收、验证和交接可执行。
边界：不要在这里累积长期架构事实、原始日志或无关 follow-up 想法。
-->

# Remote Runner 持久 Terminal Session

## 目标

解决 GitHub issue #5：在现有 automation-safe `session exec` 之外，新增一等持久 terminal session 能力。用户或上层 UI 可以创建一个真实远程 shell/terminal，上下文在多次输入之间连续保留，后续命令输出追加到同一 transcript，适合 Socratic 的学生可见 shell panel。

## 非目标

- 本任务不把现有 `remote-runner session exec` 默认语义改成持久 shell；同步命令、后台命令、run once 仍保持 automation-safe、结构化、命令级记录。
- 本任务不把 tmux 写成产品边界；如果使用 tmux，只作为 Linux/SSH terminal backend 的第一实现。
- 本任务不实现完整浏览器 UI、多人协作权限、课程/学生身份模型、PTY resize、实时 websocket streaming 或复杂交互程序协议。
- 本任务不支持带 `startup_commands` 的 Windows/WSL terminal 后端；若暂不安全，必须返回清晰错误并记录后续项。
- 本任务不把真实机器 host、账号、密码、key 内容或私人路径写入仓库。

## 当前仓库事实

- 入口规则：`AGENTS.md`
- 初始化契约：`harness/bootstrap-contract.md`
- 当前功能项：`F-019`
- 上游 issue：`https://github.com/ElysiaFollower/SEEDRunner/issues/5`
- 相关文件/模块：`remote_runner/remote_session.py`、`remote_runner/remote_backend.py`、`remote_runner/remote_state.py`、`remote_runner/cli.py`、`tests/test_remote_runner_mvp.py`、`tests/test_remote_runner_launch_suite.py`、`tests/test_remote_runner_real_integration.py`、`docs/reference/REMOTE_RUNNER_API.md`、`docs/specs/machine-session-file-mvp.md`、`SKILL.md`。
- 已知约束：当前 `session exec --mode wait/background` 通过独立 SSH command/remote state 文件实现，不保留 shell-local state；后台命令能力已解决长任务轮询，但不提供 terminal transcript；真实测试只能写 `REMOTE_RUNNER_REAL_TEST_CWD`。

## 允许改动

- 新增 terminal session CLI，例如 `remote-runner terminal create/list/show/send/read/destroy --json`，或在不混淆现有 session command 的前提下使用等价清晰命名。
- 新增 terminal state schema，记录 terminal_id、machine_id、cwd、backend、status、created_at、updated_at、transcript/log 引用、read cursor 或 transcript offset。
- 扩展 SSH backend，优先实现 Linux/SSH + tmux 后端：创建 named tmux session、向 pane 发送输入、capture-pane 读取 transcript、destroy 时杀掉对应 tmux session。
- 新增 fake-backed 单元测试、launch acceptance 覆盖，以及真实 Linux/SSH opt-in 测试。
- 更新 API/spec/getting-started/SKILL/harness，并在 PR 或 issue 里说明实现边界。

## 禁止改动

- 不删除或破坏 `session exec --mode wait/background`、`session command show/result/wait/stop`、`file put/get/list`、`run once`。
- 不要求上层系统直接调用 raw ssh、scp、rsync、tmux 或 sshfs。
- 不把 terminal transcript 设计成只存在当前 Python 进程内存；新 CLI 进程必须能恢复查询。
- 不在真实机器测试中写入 `REMOTE_RUNNER_REAL_TEST_CWD` 以外的目录。
- 不在仓库中记录真实机器敏感信息。

## 验收标准

- `remote-runner terminal create --machine <id> --cwd <remote_cwd> --json` 创建可恢复 terminal，返回 terminal_id、machine_id、cwd、status、backend、created_at、transcript/log 引用。
- `remote-runner terminal send --terminal <terminal_id> --input <text> --json` 向同一个 terminal 发送输入，不等待 shell 命令完成；同一 terminal 内 `cd`、`export` 等 shell-local state 在后续输入中保留。
- `remote-runner terminal read --terminal <terminal_id> --json` 能跨 CLI 进程返回连续 transcript 或增量 transcript，并带 cursor/offset 信息。
- `remote-runner terminal list/show/destroy --json` 可恢复查询和销毁 terminal；destroy 保留本地状态和 transcript 引用。
- 现有非交互命令生命周期不受影响，旧测试继续通过。
- 真实 Linux/SSH 蓝本在安全测试目录内能创建 terminal、发送 `pwd`、`cd`、`export`、后续 `pwd/printf` 验证连续 shell state，最后 destroy 并清理。

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

- 无法提供跨 CLI 进程恢复的 terminal transcript，只能依赖当前进程内存。
- 真实 Linux/SSH 蓝本缺少 tmux 且第一实现需要 tmux；需决定是否安装依赖、降级为 shell backend，或先标为 blocked。
- 需要在安全测试目录以外写真实机器文件。
- 需要把现有 `session exec` 语义改成持久 shell 才能实现本任务。

## 下一步最佳动作

1. 设计 terminal state 和 CLI 子命令，保持与现有 session command lifecycle 分离。
2. 用 fake backend 测试驱动实现 Linux/SSH terminal backend。
3. 用真实 Linux/SSH 蓝本验证同一 terminal 内 shell-local state 连续保留。
