# Platform Support

Remote Runner 当前支持三条持久 session 路径：Linux/SSH + tmux、direct Windows
OpenSSH + Windows agent + PowerShell 7，以及本机 tmux 托管的 OpenSSH 交互 PTY。这些路径共享同一套 `machine -> session ->
command/logs/file/artifacts` 产品抽象；平台差异是 backend 细节。

## Linux / SSH / tmux

Linux 路径要求远端具备：

- 可用的 POSIX shell / `bash`
- `tmux`，用于持久 session backend
- SSH/SFTP，用于命令通道和显式文件传输
- 一个用户明确授权的可写工作目录

Linux backend 当前支持 `session create/exec/send/read/interrupt/destroy`、`session exec --mode
background`、`session command show/wait/stop`、`file put/get/list` 和 `run once`。其中 live
tmux terminal 只承载 `send/read/interrupt`；结构化 exec/background/run once 通过独立 SSH
batch transport 执行，不进入 pane，也不共享 terminal shell-local state。

## Direct Windows OpenSSH / PowerShell

Windows 路径面向不进入 WSL 的 direct Windows OpenSSH 机器。机器记录应显式设置：

```json
{
  "platform": "windows",
  "backend": "windows-agent",
  "shell": "pwsh"
}
```

也可以用配置命令修正已有机器：

```bash
remote-runner machine configure-platform lab-win-01 \
  --platform windows \
  --json
```

Windows backend 当前要求远端具备：

- OpenSSH Server 和 SFTP subsystem
- PowerShell 7，可通过 `pwsh` 启动
- Python 3，可通过 `python` 启动
- 一个用户明确授权的可写工作目录
- 当前用户可创建并运行用户级 Windows Scheduled Task

Windows backend 会通过 SSH/SFTP 把内嵌 Python agent 放到远端工作目录下的
`.remote-runner/windows-agent/<session_id>/`，再用用户级 Scheduled Task 启动 agent。agent
维护一个长期 `pwsh` 子进程，`session exec` 通过 JSON request/result 文件投递命令并读取结构化
结果。这个实现不要求管理员权限、Windows Service、WSL、tmux 或第三方 terminal multiplexer。

当前 Windows P0 支持：

- `machine doctor`
- `session create/exec/send/read/destroy`
- 同一 session 内 PowerShell cwd、环境变量等 shell-local state 持久化
- `file put/get/list`
- `run once`

当前 Windows P0 不支持：

- `session interrupt`；piped PowerShell transport 没有可靠的 console-control channel
- `session exec --mode background`
- `session command stop` 一类后台命令控制
- `cmd.exe` 作为一等目标 shell
- Windows Service 安装或开机常驻 agent

## Local tmux / OpenSSH PTY

`openssh-pty` 路径面向只能通过本机 OpenSSH alias 交互登录的机器。典型入口是：

```bash
ssh -tt <SSH_ALIAS>
```

机器记录应显式设置：

```json
{
  "platform": "linux",
  "backend": "openssh-pty",
  "auth_type": "manual",
  "ssh_alias": "<SSH_ALIAS>",
  "shell": "bash"
}
```

该 backend 要求本机具备：

- `tmux`，用于托管长期 OpenSSH PTY。
- `/usr/bin/ssh` 或 PATH 中可用的 `ssh`。
- 用户能在 `session attach` 中手动完成密码、OTP、跳板机或平台网关提示。

当前 `openssh-pty` 支持：

- `machine add/list/show/doctor`
- `session create/attach/send/read/interrupt/destroy`
- 同一交互 shell 内 cwd、环境变量等 shell-local state 持久化
- pane 输出的 append-only transcript；agent 和 attach 中的人类观察同一输入输出流

当前 `openssh-pty` 不支持：

- `file put/get/list`；该 backend 没有独立文件 transport，live PTY 不承载文件协议
- `run once`
- `session exec`（包括 wait/background）；live PTY 不承载隐藏 wrapper RPC
- 无人值守认证、密码保存或平台网关状态机硬编码
- 远端 tmux 自动接管

## Windows + WSL Compatibility

仓库历史上验证过两类 Windows/WSL 兼容能力：

- `startup_commands`：SSH 登录后先执行 `wsl` 等预置指令。
- `path_mappings`：命令侧 `/mnt/c/...` 路径和 SFTP 侧 `C:/...` 路径之间的显式映射。

这些能力仍保留为兼容/未来 backend 输入，但它们不是 direct Windows backend。当前持久 session
不要把 `startup_commands=["wsl"]` 当作 Windows 主支持路径；Windows 主支持路径是
`windows-agent` + `pwsh`。

## 不是长期产品边界

Linux、Windows、SSH、本机或远端 tmux、Scheduled Task、PowerShell、Python agent 和 SFTP 都是 backend
选择，不是永久产品边界。长期产品抽象仍然是：

```text
machine -> session -> command/logs/file/artifacts
```

当未来引入 screen、ConPTY/native agent、container backend 或调度 backend 时，公开 CLI 应尽量保持
session 抽象稳定。
