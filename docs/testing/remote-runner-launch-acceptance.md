# Remote Runner Launch Acceptance Suite

## 目的

这套测试是上线前长期复用资产，用于回答一个问题：Remote Runner 的核心底座是否真的可用。

核心底座定义为：基于 SSH 的本地 CLI，让 AI 能通过稳定命令访问外部机器终端、执行命令、收集结构化输出、日志和产物。

## 测试分层

### 默认门禁

默认门禁不依赖真实机器，不触碰网络，也不读取用户真实凭据。

```sh
python3 -m pytest tests/test_remote_runner_launch_suite.py -q
```

覆盖内容：

- `remote_runner` 目标包名和 legacy `seed_runner` compatibility wrapper。
- machine 配置、脱敏展示、platform/backend/shell、startup commands、path mappings 和本地 state
  落盘；其中 startup/path mapping 是兼容配置覆盖，不代表 Windows/WSL 是 direct Windows 主路径。
- session create/exec/logs/destroy。
- file put/list/get 和 transfer records。
- run once 输入上传、命令执行、artifact 拉回、run manifest 和 session destroy。
- artifact manifest、session state、run state 可恢复读取。

### 真实机器门禁

真实机器门禁默认 skip。只有显式设置以下环境变量才运行：

```sh
REMOTE_RUNNER_RUN_REAL_TESTS=1 \
REMOTE_RUNNER_REAL_MACHINE=<machine_id> \
REMOTE_RUNNER_REAL_TEST_CWD=<remote_cwd> \
python3 -m pytest tests/test_remote_runner_launch_suite.py tests/test_remote_runner_real_integration.py -q
```

direct Windows 真实机器需要额外声明平台：

```sh
REMOTE_RUNNER_RUN_REAL_TESTS=1 \
REMOTE_RUNNER_REAL_PLATFORM=windows \
REMOTE_RUNNER_REAL_MACHINE=<machine_id> \
REMOTE_RUNNER_REAL_TEST_CWD=<remote_cwd> \
python3 -m pytest tests/test_remote_runner_real_integration.py -q
```

安全边界：

- 当前上线主路径包括 Linux/SSH + tmux 和 direct Windows OpenSSH + windows-agent/pwsh。
- Linux 真实机器要求远端可用 `tmux`；direct Windows 真实机器要求远端可用 SFTP、Python 3 和
  PowerShell 7。
- `REMOTE_RUNNER_REAL_TEST_CWD` 必须是明确允许写入的远程测试目录。
- 测试只在该目录下创建随机前缀探针文件。
- 测试结束会执行 cleanup 并 destroy session。
- 不要把真实机器 host、用户名、密码或私人路径写入仓库、handoff 或 issue。

真实机器覆盖内容：

- `machine doctor`
- `session create`
- `session exec`
- `file put/list/get`
- `run once` 上传输入、执行命令、拉回 artifact
- 远程 cleanup
- session destroy

## 上线判定

上线前至少满足：

```sh
python3 -m pytest tests/test_remote_runner_launch_suite.py -q
python3 -m pytest tests/test_remote_runner_real_integration.py -q
python3 -m pytest -q
./scripts/harness-check.sh
git diff --check
```

如果存在真实机器环境，还应额外运行真实机器门禁。真实机器不可用时，不应阻塞默认本地验证，但必须在 release note 或 handoff 中标明“真实机器验收未运行”。
