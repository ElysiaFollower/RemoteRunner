# Remote Runner 使用指南

这是给本地 agent 和人类共用的最小上手说明。目标是：先把工具装进 `seedrunner` conda 环境，再用稳定命令登记机器、验证连通、跑会话、传文件、执行一次性闭环。

当前支持三条持久 session 路径：Linux/SSH + tmux、direct Windows OpenSSH + windows-agent + PowerShell 7，以及本机 tmux 托管的 OpenSSH 交互 PTY。

## 1. 安装到 seedrunner 环境

```bash
conda activate seedrunner
cd /Users/ely/workspace/research/agent/SEEDRunner
python -m pip install -e .
```

验证入口是否可用：

```bash
remote-runner --help
remote-runner machine list --json
```

如果当前 shell 没有激活 conda 环境，也可以直接：

```bash
conda run -n seedrunner remote-runner --help
```

## 2. 添加一台 Linux 机器

推荐交互式输入。只需要准备 `host`、`user`、`password`，其余可以先用默认值。

```bash
remote-runner machine add \
  --machine-id linux-01 \
  --host <IP> \
  --user <USERNAME> \
  --auth-type password \
  --platform linux \
  --default-cwd /home/<USERNAME> \
  --json
```

说明：

- 密码会在终端隐藏输入，不会回显。
- `--json` 时，stdout 只输出 JSON，交互提示写到 stderr。
- Linux 机器通常不需要 `startup-command`。

添加后建议立即检查：

```bash
remote-runner machine show linux-01 --json
remote-runner machine doctor linux-01 --json
```

## 3. 基本会话流程

先创建会话，再执行命令，再看日志，最后销毁会话。

```bash
remote-runner session create --machine linux-01 --cwd /home/ely/tmp --name smoke-test --json
remote-runner session exec --session smoke-test --cmd 'pwd && whoami' --json
remote-runner session logs --session smoke-test --json
remote-runner session destroy --session smoke-test --json
```

建议把可写测试目录固定在 `/home/ely/tmp` 或其他你确认可写的目录。若该目录是 root-owned 或不可写，就换成别的安全目录，不要默认假设它能写。
`--name` 可选；非临时会话建议提供可读名称。后续 `--session` 可以使用真实 `session_id`
或唯一可解析的 name。

如果任务是长时间运行的，先用后台模式启动，再用 `session command show/wait/stop` 查询：

```bash
remote-runner session exec \
  --session <SESSION_ID> \
  --cmd 'python long_job.py' \
  --mode background \
  --json

remote-runner session command show \
  --session <SESSION_ID> \
  --command-id <COMMAND_ID> \
  --json

remote-runner session command wait \
  --session <SESSION_ID> \
  --command-id <COMMAND_ID> \
  --timeout 30 \
  --json

remote-runner session command stop \
  --session <SESSION_ID> \
  --command-id <COMMAND_ID> \
  --json
```

## 4. 文件传输

```bash
remote-runner file put \
  --session <SESSION_ID> \
  --local ./input.txt \
  --remote /home/ely/tmp/input.txt \
  --json

remote-runner file list \
  --session <SESSION_ID> \
  --remote /home/ely/tmp \
  --json

remote-runner file get \
  --session <SESSION_ID> \
  --remote /home/ely/tmp/output.txt \
  --local ./output.txt \
  --json
```

## 5. 持久 Session Transcript

`session` 本身就是持久终端。它的基础操作是 `session send/read/interrupt`：原样键入、按
cursor 读取 append-only transcript、向前台进程发送 `Ctrl-C`。同一个 shell 会保留 `cd`、
`export` 等 shell-local state。
Linux 持久 session 后端要求 Linux/SSH 机器上有 `tmux`。Windows 持久 session 后端见下方 direct Windows 章节。

`session exec` 目前是 `ssh-tmux` 和 `windows-agent` 的结构化兼容接口，不是 session 的
基础语义。需要多步脚本、产物回收和进程级退出语义时，用 `run once`。

```bash
remote-runner session create \
  --machine linux-01 \
  --cwd /home/ely/tmp \
  --name demo-shell \
  --json

remote-runner session exec \
  --session demo-shell \
  --cmd 'cd /home/ely/tmp' \
  --json

remote-runner session exec \
  --session demo-shell \
  --cmd 'export RR_DEMO=ok' \
  --json

remote-runner session exec \
  --session demo-shell \
  --cmd 'pwd && printf "$RR_DEMO\n"' \
  --json

remote-runner session read \
  --session demo-shell \
  --json

remote-runner session destroy \
  --session demo-shell \
  --json
```

`session read` 会返回 transcript 和 cursor；下次可以用 `--since <cursor>` 读取增量输出。

## 6. 一次性闭环

`run once` 适合“上传输入 -> 执行命令 -> 拉回产物 -> 保存 run manifest”的一轮任务。

```bash
remote-runner run once \
  --machine linux-01 \
  --cwd /home/ely/tmp \
  --input ./input.txt=/home/ely/tmp/input.txt \
  --cmd 'cp input.txt output.txt' \
  --artifact /home/ely/tmp/output.txt=./output.txt \
  --json
```

## 7. 添加一台 direct Windows OpenSSH 机器

Windows 主路径不进入 WSL，而是通过远端 Python agent 托管 PowerShell 7 session。远端需要：

- OpenSSH Server / SFTP 可用
- `python` 可启动 Python 3
- `pwsh` 可启动 PowerShell 7
- 当前用户可创建用户级 Scheduled Task

```bash
remote-runner machine add \
  --machine-id win-01 \
  --host <IP_OR_ALIAS> \
  --user <USERNAME> \
  --auth-type key \
  --key-path ~/.ssh/id_ed25519 \
  --platform windows \
  --default-cwd C:/Users/<USERNAME> \
  --json
```

已有机器可不重填凭据，直接修正平台/backend/shell：

```bash
remote-runner machine configure-platform win-01 \
  --platform windows \
  --json
```

Windows session 用法和 Linux 相同：

```bash
remote-runner session create --machine win-01 --cwd C:/Users/<USERNAME> --name win-shell --json
remote-runner session exec --session win-shell --cmd 'Write-Output ((Get-Location).Path)' --json
remote-runner session exec --session win-shell --cmd '$env:RR_DEMO="ok"' --json
remote-runner session exec --session win-shell --cmd 'Write-Output $env:RR_DEMO' --json
remote-runner session read --session win-shell --json
remote-runner session destroy --session win-shell --json
```

Windows P0 暂不支持 `session exec --mode background` 和后台命令 stop。

## 8. Windows + WSL 兼容配置

如果远程机器是 Windows OpenSSH，且兼容 backend 需要先进入 WSL 再执行 Linux 命令，可以记录：

```bash
remote-runner machine configure-startup my-windows \
  --startup-command wsl \
  --default-cwd /mnt/c/Users/<USER>/Desktop/SSHRunner \
  --json

remote-runner machine configure-path-map my-windows \
  --command-prefix /mnt/c/Users/<USER>/Desktop/SSHRunner \
  --file-prefix C:/Users/<USER>/Desktop/SSHRunner \
  --json
```

注意：这是兼容路径，不是 direct Windows 主路径。direct Windows 主路径应使用 `platform=windows`
和 `backend=windows-agent`。

## 9. OpenSSH 交互 PTY 机器

有些机器不能稳定支持标准 SSH exec/SFTP，但人类可以通过本机 OpenSSH alias 进入：

```bash
ssh -tt <SSH_ALIAS>
```

这类机器可以用 `openssh-pty` backend。它依赖本机 `tmux`，由本地 tmux 持有 `ssh -tt`
进程；你通过 `session attach` 手动输入密码、OTP 或走平台网关流程，脱离后 agent 继续控制同一个交互 shell。

```bash
remote-runner machine add \
  --machine-id interactive-01 \
  --backend openssh-pty \
  --ssh-alias <SSH_ALIAS> \
  --auth-type manual \
  --platform linux \
  --default-cwd /home/<USERNAME> \
  --json
```

创建 session 后先 attach：

```bash
remote-runner session create \
  --machine interactive-01 \
  --cwd /home/<USERNAME> \
  --name interactive-shell \
  --json

remote-runner session attach --session interactive-shell
```

如果给了可读 `--name`，返回的本地 tmux attach 命令也会尽量使用这个名字，例如
`tmux attach-session -t rr_interactive-shell`；只有本机 tmux 已经占用同名 session 时才会追加短后缀。

在 attach 界面里完成登录；看到目标 shell 后可以手动切到安全工作目录，再按 `Ctrl-b d`
脱离本地 tmux，不要 `exit`。`openssh-pty` 的 `--cwd` / `default_cwd` 只是 session
元数据；后续输入沿用你脱离时的 shell 状态。需要切换目录时，像人类一样显式发送
`cd`。之后可以运行：

```bash
remote-runner session send --session interactive-shell --input 'pwd && whoami' --json
remote-runner session send --session interactive-shell --input 'echo hello' --json
remote-runner session read --session interactive-shell --json
remote-runner session interrupt --session interactive-shell --json
remote-runner session destroy --session interactive-shell --json
```

人类 attach 着观察时，会在同一个 tmux panel 中看到 agent 输入的原文和 shell 输出；
`session read` 读取的也是这条 append-only 流。`openssh-pty` 会在向 pane 写入任何东西前
拒绝 `session exec`，避免隐藏 `eval`、marker 或退出码 wrapper 污染 live shell。

边界：`openssh-pty` 支持 `session create/attach/send/read/interrupt/destroy`，以及从已登录且空闲的
session 下载普通文件的 `file get`。下载会分块传输，校验远端 size/SHA-256 后原子落盘。
它仍不支持 `file put`、目录下载、`file list`、`run once`、任何 `session exec`
或无人值守认证；密码不写入 Remote Runner 配置。

## 10. 真实机器验收

默认测试不依赖真实机器。要跑真实门禁，必须显式设置环境变量：

```bash
REMOTE_RUNNER_RUN_REAL_TESTS=1 \
REMOTE_RUNNER_REAL_MACHINE=linux-01 \
REMOTE_RUNNER_REAL_TEST_CWD=/home/ely/tmp \
python3 -m pytest tests/test_remote_runner_launch_suite.py tests/test_remote_runner_real_integration.py -q
```

Windows opt-in 验收需要额外设置平台：

```bash
REMOTE_RUNNER_RUN_REAL_TESTS=1 \
REMOTE_RUNNER_REAL_PLATFORM=windows \
REMOTE_RUNNER_REAL_MACHINE=win-01 \
REMOTE_RUNNER_REAL_TEST_CWD=C:/Users/<USERNAME> \
python3 -m pytest tests/test_remote_runner_real_integration.py -q
```

## 11. 记住这几个规则

- `--json` 的 stdout 应该能被 `json.loads()` 直接解析。
- 密码不会写到日志、handoff 或测试输出里。
- 所有真实测试都必须只写入你明确指定的安全目录。
- `session` 是连续终端流；`send/read/interrupt` 是基础契约，结构化命令属于兼容或 job 层。
- 如果 shell 找不到 `remote-runner`，先确认你在 `seedrunner` 环境里，或者直接用 `conda run -n seedrunner ...`。
