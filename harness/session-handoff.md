<!--
职责：提供最新的紧凑交接信息，让新 agent 能无歧义恢复当前任务。
边界：只保留当前可恢复状态；历史放 progress.md，稳定事实放 docs 或代码。
-->

# 会话交接

## 仓库状态

- 分支：`dev-windows-agent-pwsh-backend`。
- 最近计划：`plans/archive/2026-06-13-windows-agent-pwsh-backend.md`。
- 当前功能项：`F-022 Remote Runner Windows Agent PowerShell Backend` passing；`F-020`、`F-021` passing；`F-005` profile/report 层未开始。
- 当前目标状态：Remote Runner 已支持两条持久 session backend：Linux/SSH + tmux，以及 direct Windows OpenSSH + windows-agent + PowerShell 7。
- 当前策略：同一 Remote Runner API，不拆 Windows/Linux 产品分支；机器注册显式记录 `platform`，Windows 默认 `backend=windows-agent`、`shell=pwsh`，Linux/mac 默认 `backend=ssh-tmux`、`shell=bash`。

## 本轮完成

- 新建隔离分支 `dev-windows-agent-pwsh-backend`，避免破坏当前 Linux/tmux 稳定路径。
- 新增并归档任务合同和 check anchors：
  - `plans/archive/2026-06-13-windows-agent-pwsh-backend.md`
  - `plans/archive/2026-06-13-windows-agent-pwsh-backend.check.json`
- `RemoteMachine` 新增兼容字段：`platform`、`backend`、`shell`。旧记录默认 `linux / ssh-tmux / bash`。
- `machine add` 新增 `--platform/--backend/--shell`；交互式注册会询问 `linux/windows/mac`。
- 新增 `machine configure-platform <machine_id> --platform ...`，用于不重填凭据地修正既有机器平台/backend/shell。
- 新增 `remote_runner/windows_agent.py` 嵌入式 Windows agent 源码。
- `ParamikoRemoteBackend` 新增 `windows-agent` 分支：
  - `doctor` 使用 PowerShell cwd/pwsh probe。
  - `session create` 上传 agent 到远端工作目录下 `.remote-runner/windows-agent/<session_id>/`，用用户级 Windows Scheduled Task 启动 agent。
  - `session exec --mode wait` 通过 JSON request/result 文件和持久 `pwsh` 子进程执行。
  - `session send/read` 支持原始输入和 transcript 读取。
  - `session destroy` 发送 destroy request 并删除对应 Scheduled Task。
  - Windows SFTP `C:/...` 路径 mkdir bug 已修复。
- `session exec --mode background` 对 `windows-agent` 明确拒绝；P0 不承诺 Windows 后台 stop 语义。
- 文档已同步：README、Skill、Requirements、platform support、API、getting-started、MVP spec、launch acceptance suite、overview、core lighthouse。

## 验证证据

- `python3 -m py_compile remote_runner/remote_machine.py remote_runner/cli.py remote_runner/windows_agent.py remote_runner/remote_backend.py remote_runner/remote_session.py tests/test_remote_runner_real_integration.py tests/test_remote_runner_mvp.py` 通过。
- `python3 -m pytest tests/test_remote_runner_mvp.py -q` 通过 `39 passed`。
- `python3 -m pytest tests/test_remote_runner_real_integration.py -q` 默认通过 `2 skipped`。
- `python3 -m pytest tests/test_remote_runner_launch_suite.py -q` 通过 `2 passed, 1 skipped`。
- `python3 -m pytest -q` 通过 `62 passed, 4 skipped`。
- `./scripts/harness-check.sh` 通过。
- `git diff --check` 通过。
- direct Windows opt-in 真实测试通过 `1 passed, 1 skipped`，覆盖 doctor、session create、跨多次 wait-mode exec 的 PowerShell 状态保持、session read transcript、file put/list/get、run once artifact pullback、cleanup 和 session destroy。
- 收尾确认远端无残留 `RemoteRunner_` Windows Scheduled Tasks。

## 仍未完成

- Windows backend 当前支持持久 wait-mode execution、send/read、destroy、file put/list/get、run once；不支持 background command/stop。
- `docs/issues/` 是本轮开始前已存在的未跟踪目录；未纳入本任务处理。

## 安全与隐私边界

- Windows agent 通过用户级 Scheduled Task 启动，不要求管理员权限、Windows Service、WSL、tmux 或第三方 terminal multiplexer。
- direct Windows P0 目标 shell 是 PowerShell 7 (`pwsh`)；`cmd.exe` 一等支持未开始。
- Windows/WSL `startup_commands` + `path_mappings` 保留为兼容输入，不是 direct Windows 主路径。
- 真实机器细节、host、用户名、密码、私有路径未写入仓库。
- 真实 Windows 测试只写入显式配置的测试目录；收尾确认无残留 `RemoteRunner_` Windows Scheduled Tasks。

## 下一步最佳动作

1. Review 当前 diff，确认 Windows agent backend 的协议和文档范围。
2. 推送 `dev-windows-agent-pwsh-backend` 并创建 PR。
3. 后续单独切任务处理 Windows background command/stop、安装器/native gateway、ConPTY 或更完整的 agent 生命周期管理。

## 常用命令

- 初始化：`./init.sh`
- Harness 检查：`./scripts/harness-check.sh`
- 聚焦测试：`python3 -m pytest tests/test_remote_runner_mvp.py -q`
- 默认真实测试入口：`python3 -m pytest tests/test_remote_runner_real_integration.py -q`
- Windows opt-in 真实测试：`REMOTE_RUNNER_RUN_REAL_TESTS=1 REMOTE_RUNNER_REAL_PLATFORM=windows REMOTE_RUNNER_REAL_MACHINE=<windows_machine_id> REMOTE_RUNNER_REAL_TEST_CWD=<windows_test_cwd> python3 -m pytest tests/test_remote_runner_real_integration.py -q`
- 完整验证：`python3 -m pytest -q`
