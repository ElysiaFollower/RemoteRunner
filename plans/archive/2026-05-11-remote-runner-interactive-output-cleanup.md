<!--
职责：为实现 agent 定义一个 active task 合同，让范围、验收、验证和交接可执行。
边界：不要在这里累积长期架构事实、原始日志或无关 follow-up 想法。
-->

# Remote Runner 交互式 SSH 输出清理

## 目标

让带 `startup_commands` 的 `session exec` 返回更接近真实用户命令输出的 stdout。Windows OpenSSH 进入 WSL 的交互式 shell 不应把 Windows banner、启动命令回显、`cd` 回显、sentinel 回显、`exit` 回显和 shell prompt 当作用户命令输出返回。

## 非目标

- 不重构 SSH backend 架构或替换 Paramiko。
- 不改变 `startup_commands`、`path_mappings`、file transfer 或本地状态 schema。
- 不在真实 Windows 机器的 `SSHRunner` 目录外写入、删除或移动文件。
- 不承诺彻底清理所有远程 shell 的任意 prompt 变体；本轮以 marker 截取和关闭 echo 解决已验证的 Windows/WSL 噪声。

## 当前仓库事实

- 入口规则：`AGENTS.md`
- 初始化契约：`harness/bootstrap-contract.md`
- 当前功能项：F-009
- 相关文件/模块：`seed_runner/remote_backend.py`、`tests/test_remote_runner_mvp.py`、`harness/feature_list.json`、`harness/progress.md`、`harness/session-handoff.md`
- 已知约束：真实机器 `windows-wsl` 需要先执行 `wsl`；允许测试目录仅为 `/mnt/c/Users/example/Desktop/SSHRunner`。

## 允许改动

- 调整 startup-aware interactive SSH 的 marker、echo 控制和 stdout 清理逻辑。
- 增加单元测试覆盖 Windows banner、命令回显、prompt 和 sentinel 过滤。
- 做只读真实验证：在 `SSHRunner` 工作目录执行 `pwd && printf ...`，不创建远程文件。
- 更新 harness 状态、证据和交接。

## 禁止改动

- 禁止把真实 host、密码、密钥或额外机器细节写入仓库文件。
- 禁止在真实 Windows 机器的 `SSHRunner` 目录外写入或删除文件。
- 禁止把 stderr/stdout 清理做成会丢失用户命令真实输出的大范围正则。

## 验收标准

- 单元测试证明 Windows banner、启动命令回显、`cd` 回显、用户命令回显和 sentinel 不出现在返回 stdout。
- 用户命令的真实 stdout 保留，exit code 仍通过 sentinel 捕获。
- 真实 `windows-wsl` 只读验证返回 stdout 中包含 `SSHRunner` 路径和探针文本，不包含 Windows banner 或 `wsl`/`cd`/命令回显。
- 现有 Remote Runner 和 legacy 测试继续通过。

## 验证命令

```sh
./scripts/harness-check.sh
python3 -m pytest tests/test_remote_runner_mvp.py -q
python3 -m pytest -q
python3 -m black --check seed_runner/remote_backend.py tests/test_remote_runner_mvp.py
git diff --check
```

真实验证：

```sh
python3 -m seed_runner.remote_cli machine doctor 'windows-wsl' --json
python3 -m seed_runner.remote_cli session create --machine 'windows-wsl' --json
python3 -m seed_runner.remote_cli session exec --session <session_id> --cmd 'pwd && printf "remote-runner-clean-output\n"' --json
python3 -m seed_runner.remote_cli session destroy --session <session_id> --json
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

- 真实 Windows 机器无法 SSH 连接。
- 需要在 `SSHRunner` 目录外写入文件才能验证。
- 输出清理需求升级为任意 shell 的通用终端仿真。

## 下一步最佳动作

1. 在 interactive backend 中增加 begin marker 和 echo/prompt 控制，并补回归测试。
