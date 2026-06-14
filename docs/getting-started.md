# Remote Runner 使用指南

这是给本地 agent 和人类共用的最小上手说明。目标是：先把工具装进 `seedrunner` conda 环境，再用稳定命令登记机器、验证连通、跑会话、传文件、执行一次性闭环。

当前支持两条持久 session 路径：Linux/SSH + tmux，以及 direct Windows OpenSSH + windows-agent + PowerShell 7。

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
remote-runner session create --machine linux-01 --cwd /home/ely/tmp --json
remote-runner session exec --session <SESSION_ID> --cmd 'pwd && whoami' --json
remote-runner session logs --session <SESSION_ID> --json
remote-runner session destroy --session <SESSION_ID> --json
```

建议把可写测试目录固定在 `/home/ely/tmp` 或其他你确认可写的目录。若该目录是 root-owned 或不可写，就换成别的安全目录，不要默认假设它能写。

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

`session` 本身就是持久 shell 工作上下文。连续的 `session exec` 会保留 `cd`、`export`
等 shell-local state；如果需要原始 shell panel 输入和 transcript，用 `session send/read`。
Linux 持久 session 后端要求 Linux/SSH 机器上有 `tmux`。Windows 持久 session 后端见下方 direct Windows 章节。

```bash
remote-runner session create \
  --machine linux-01 \
  --cwd /home/ely/tmp \
  --json

remote-runner session exec \
  --session <SESSION_ID> \
  --cmd 'cd /home/ely/tmp' \
  --json

remote-runner session exec \
  --session <SESSION_ID> \
  --cmd 'export RR_DEMO=ok' \
  --json

remote-runner session exec \
  --session <SESSION_ID> \
  --cmd 'pwd && printf "$RR_DEMO\n"' \
  --json

remote-runner session read \
  --session <SESSION_ID> \
  --json

remote-runner session destroy \
  --session <SESSION_ID> \
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
remote-runner session create --machine win-01 --cwd C:/Users/<USERNAME> --json
remote-runner session exec --session <SESSION_ID> --cmd 'Write-Output ((Get-Location).Path)' --json
remote-runner session exec --session <SESSION_ID> --cmd '$env:RR_DEMO="ok"' --json
remote-runner session exec --session <SESSION_ID> --cmd 'Write-Output $env:RR_DEMO' --json
remote-runner session read --session <SESSION_ID> --json
remote-runner session destroy --session <SESSION_ID> --json
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

## 9. 真实机器验收

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

## 10. 记住这几个规则

- `--json` 的 stdout 应该能被 `json.loads()` 直接解析。
- 密码不会写到日志、handoff 或测试输出里。
- 所有真实测试都必须只写入你明确指定的安全目录。
- `session` 是连续 shell transcript；`session exec` 在同一 session shell 中提供结构化命令结果。
- 如果 shell 找不到 `remote-runner`，先确认你在 `seedrunner` 环境里，或者直接用 `conda run -n seedrunner ...`。
