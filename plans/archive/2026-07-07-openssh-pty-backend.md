<!--
职责：为实现 agent 定义一个 active task 合同，让范围、验收、验证和交接可执行。
边界：不要在这里累积长期架构事实、原始日志或无关 follow-up 想法。
-->

# OpenSSH PTY Backend

## 目标

让 Remote Runner 能登记只适合通过本机 OpenSSH 交互入口访问的机器，例如 `ssh -tt 91_A100`。Remote Runner 使用本机 `tmux` 托管该 OpenSSH PTY；用户在 `session attach` 中手动完成密码和平台网关登录后，Remote Runner 能通过本地 tmux session 发送输入、读取 transcript、执行 wait-mode 命令并销毁 session。

## 非目标

- 不把该机器的真实 host、user、password、私钥或网关细节写入配置、日志、测试或文档。
- 不实现 SFTP/file put/get/list、background command、run once、端口转发、ControlMaster 管理、无人值守认证或远端 tmux 自动接管。
- 不改坏现有 `ssh-tmux` 和 `windows-agent` 后端的公开行为。

## 当前仓库事实

- 入口规则：`AGENTS.md`
- 初始化契约：`harness/bootstrap-contract.md`
- 当前功能项：`F-025`
- 相关文件/模块：`remote_runner/remote_machine.py`、`remote_runner/remote_backend.py`、`remote_runner/remote_session.py`、`remote_runner/cli.py`、`tests/test_remote_runner_mvp.py`、`docs/reference/REMOTE_RUNNER_API.md`、`docs/getting-started.md`
- 已知约束：当前 `ParamikoRemoteBackend` 通过 Paramiko `exec_command`/SFTP 操作标准 SSH 机器；`91_A100` 类机器需要 `ssh -tt <alias>` 交互登录，不能假设标准 SSH exec、SFTP 或 BatchMode 可用。`openssh-pty` 后端明确依赖本机 `tmux` 和 `/usr/bin/ssh`。

## 允许改动

- 增加 `openssh-pty` machine backend 和 `ssh_alias` 配置字段。
- 增加本地 tmux adapter，用于托管 `/usr/bin/ssh -tt <alias>` 并通过 tmux send/capture 控制 PTY。
- 增加 `session attach` CLI，用于用户手动登录并用 `Ctrl-b d` 脱离。
- 为 `openssh-pty` 增加 wait-mode `session exec`、`session send/read/destroy` 支持。
- 增加聚焦测试、API/上手文档和 harness 状态记录。

## 禁止改动

- 不要求用户把密码传给 Remote Runner，也不在 `machine add` 中采集该密码。
- 不改变现有 machine state 文件位置或既有机器记录兼容性。
- 不让 `openssh-pty` 冒充完整 `ssh-tmux` 后端；未支持能力必须明确拒绝或文档标注。

## 验收标准

- 用户可以用 alias 注册机器：`machine add --backend openssh-pty --ssh-alias 91_A100`，无需 host/user/password。
- `session create` 为该机器启动本地 tmux session，并返回 attach 命令；`session attach` 可进入该 PTY，用户手动登录后按 `Ctrl-b d` 脱离。
- 登录完成后，`session send/read` 能读写同一持久交互 shell transcript。
- 登录完成后，wait-mode `session exec` 能返回 `stdout`、`exit_code`、timestamps 和 command log；不支持的 background/file/run 能清楚失败。
- 现有 `ssh-tmux`、`windows-agent` 测试继续通过。

## 关键锚点

配套检查文件：`plans/active/2026-07-07-openssh-pty-backend.check.json`

- `remote_runner/remote_backend.py` 中的 local tmux adapter：证明本地 tmux 托管 OpenSSH PTY 的控制面已落地。
- `remote_runner/remote_machine.py` 中的 `openssh-pty`/`ssh_alias`：证明 machine schema 能表达 OpenSSH alias，不要求 host/user/password。
- `remote_runner/cli.py` 中的 `session attach`：证明用户手动登录入口是公开 CLI 合同的一部分。
- `tests/test_remote_runner_mvp.py` 覆盖 `openssh-pty`：证明新增 backend 有契约测试且不只是手工脚本。
- `harness/feature_list.json` 中 `F-025` evidence：证明验证结果已写回仓库事实源。

## 验证命令

```sh
./scripts/harness-check.sh
python3 -m pytest tests/test_remote_runner_mvp.py -q
python3 -m pytest -q
git diff --check
python3 -m remote_runner.cli machine add --machine-id 91_A100 --backend openssh-pty --ssh-alias 91_A100 --platform linux --default-cwd /root --replace --confirm-replace 91_A100 --json
python3 -m remote_runner.cli session create --machine 91_A100 --name a100-pty --cwd /root --json
python3 -m remote_runner.cli session attach --session a100-pty
python3 -m remote_runner.cli session exec --session a100-pty --cmd 'hostname; whoami; pwd; command -v tmux' --timeout 30 --json
python3 -m remote_runner.cli session destroy --session a100-pty --json
```

## Evidence 记录要求

验证通过后，将命令、结果、关键输出摘要或 artifact 路径写入 `harness/feature_list.json` 的 `evidence`。真实 `91_A100` 验证不得记录真实 host/user/password；只记录 machine alias、命令类别和通过/失败原因。

## 完成定义

- 请求行为已实现。
- 非目标没有被触碰。
- 关键锚点已满足；若锚点因方案变化不再合理，已先更新 active plan 和 `.check.json` 并记录原因。
- 上方验证命令已运行；未运行的命令必须说明原因。
- `harness/feature_list.json` 状态和 evidence 已更新。
- 职责、接口、setup 或边界改变时，docs、注释、测试或 harness 文件已更新。
- `harness/session-handoff.md` 写明当前状态、风险和下一步。
- 清洁状态检查已说明。

## 阻塞条件

- 如果本地 tmux 无法安装或无法稳定托管 `ssh -tt 91_A100`，或者真实 `ssh -tt 91_A100` 在 attach 中无法保持登录后的 shell，则停下来报告证据，不改成保存密码或硬编码网关流程。

## 下一步最佳动作

1. 安装/验证本地 tmux，并实现 `openssh-pty` machine schema、local tmux adapter、session attach 和 wait-mode exec。
