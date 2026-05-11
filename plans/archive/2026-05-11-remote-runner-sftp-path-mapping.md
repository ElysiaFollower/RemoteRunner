<!--
职责：为实现 agent 定义一个 active task 合同，让范围、验收、验证和交接可执行。
边界：不要在这里累积长期架构事实、原始日志或无关 follow-up 想法。
-->

# Remote Runner SFTP 路径映射与真实文件传输验证

## 目标

让 Remote Runner 在“命令执行路径”和“SFTP 文件传输路径”不一致的机器上可用。用户仍以 session 的远程工作目录路径表达文件位置；机器配置可显式记录从命令路径前缀到文件传输路径前缀的映射，file put/get/list 在 SFTP backend 前自动应用映射，并把原始用户路径保留到 transfer/artifact 记录中。

## 非目标

- 不重构包名、legacy `seed-runner` 原型或已有 mount/tmux 代码。
- 不引入 sshfs、rsync、常驻服务、系统钥匙串或 `~/.ssh/config` 解析。
- 不在真实 Windows 机器的 `SSHRunner` 目录外创建、修改、删除文件。
- 不把 Windows/WSL 路径映射做成自动猜测；本轮只支持用户显式配置。

## 当前仓库事实

- 入口规则：`AGENTS.md`
- 初始化契约：`harness/bootstrap-contract.md`
- 当前功能项：F-008
- 相关文件/模块：`seed_runner/remote_machine.py`、`seed_runner/remote_backend.py`、`seed_runner/remote_cli.py`、`seed_runner/remote_file.py`、`tests/test_remote_runner_mvp.py`、`docs/reference/REMOTE_RUNNER_API.md`、`REQUIREMENTS.md`
- 已知约束：真实机器 `windows-wsl` 需要先执行 `wsl`；命令目录为 `/mnt/c/Users/example/Desktop/SSHRunner`，SFTP 可见目录为 `C:/Users/example/Desktop/SSHRunner`；只允许触碰 `SSHRunner` 内文件。

## 允许改动

- 新增机器字段，用于保存显式文件路径映射。
- 新增或扩展机器配置 CLI，用于在不重填账密的情况下配置路径映射。
- 在 SFTP put/get/list 前应用路径映射。
- 增加单元测试、文档、harness 状态和真实验证 evidence。

## 禁止改动

- 禁止把真实 host、密码、密钥或额外机器细节写入仓库文件。
- 禁止在真实 Windows 机器的 `SSHRunner` 目录外写入、删除或移动文件。
- 禁止更改已有 session/command 的本地状态语义：用户传入路径仍应作为 source/destination 记录。

## 验收标准

- 机器记录可保存、展示和更新 `path_mappings`，展示时不泄露凭据。
- `file put/get/list` 在 backend 层应用映射，使用户可用 WSL 命令路径访问 Windows SFTP 路径。
- transfer 记录和 artifact manifest 仍记录用户输入的原始 remote path。
- 真实 Windows 验证中，只在 `SSHRunner` 内完成 put/list/get/delete 流程。

## 验证命令

```sh
./scripts/harness-check.sh
python3 -m pytest tests/test_remote_runner_mvp.py -q
python3 -m pytest -q
python3 -m black --check seed_runner/remote_machine.py seed_runner/remote_cli.py seed_runner/remote_backend.py seed_runner/remote_file.py tests/test_remote_runner_mvp.py
git diff --check
```

真实验证：

```sh
python3 -m seed_runner.remote_cli machine configure-path-map 'windows-wsl' --command-prefix /mnt/c/Users/example/Desktop/SSHRunner --file-prefix C:/Users/example/Desktop/SSHRunner --json
python3 -m seed_runner.remote_cli file put --session <session_id> --local <local_probe> --remote /mnt/c/Users/example/Desktop/SSHRunner/<probe_file> --json
python3 -m seed_runner.remote_cli file list --session <session_id> --remote /mnt/c/Users/example/Desktop/SSHRunner --json
python3 -m seed_runner.remote_cli file get --session <session_id> --remote /mnt/c/Users/example/Desktop/SSHRunner/<probe_file> --local <download_probe> --json
python3 -m seed_runner.remote_cli session exec --session <session_id> --cmd 'rm -f <probe_file> && test ! -e <probe_file>' --json
```

## Evidence 记录要求

验证通过后，将命令、结果、关键输出摘要或 artifact 路径写入 `harness/feature_list.json` 的 `evidence`。

## 完成定义

- 请求行为已实现。
- 非目标没有被触碰。
- 上方验证命令已运行；未运行的命令必须说明原因。
- `harness/feature_list.json` 状态和 evidence 已更新。
- 职责、接口、setup 或边界改变时，docs、注释、测试或 harness 文件已更新。
- `harness/session-handoff.md` 写明当前状态、风险和下一步。
- 清洁状态检查已说明。

## 阻塞条件

- 真实 Windows 机器无法 SSH/SFTP 连接。
- 需要在 `SSHRunner` 目录外写入文件才能继续验证。
- 映射语义需要从“显式前缀映射”改成自动发现或复杂多 backend 规则。

## 下一步最佳动作

1. 实现机器 path_mappings schema、配置 CLI 和 SFTP backend 映射。
