# Remote Runner 使用指南

这是给本地 agent 和人类共用的最小上手说明。目标是：先把工具装进 `seedrunner` conda 环境，再用稳定命令登记机器、验证连通、跑会话、传文件、执行一次性闭环。

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

## 5. 一次性闭环

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

## 6. Windows + WSL 机器

如果远程机器是 Windows OpenSSH，需要先进入 WSL 再执行 Linux 命令：

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

## 7. 真实机器验收

默认测试不依赖真实机器。要跑真实门禁，必须显式设置环境变量：

```bash
REMOTE_RUNNER_RUN_REAL_TESTS=1 \
REMOTE_RUNNER_REAL_MACHINE=linux-01 \
REMOTE_RUNNER_REAL_TEST_CWD=/home/ely/tmp \
python3 -m pytest tests/test_remote_runner_launch_suite.py tests/test_remote_runner_real_integration.py -q
```

## 8. 记住这几个规则

- `--json` 的 stdout 应该能被 `json.loads()` 直接解析。
- 密码不会写到日志、handoff 或测试输出里。
- 所有真实测试都必须只写入你明确指定的安全目录。
- 如果 shell 找不到 `remote-runner`，先确认你在 `seedrunner` 环境里，或者直接用 `conda run -n seedrunner ...`。
