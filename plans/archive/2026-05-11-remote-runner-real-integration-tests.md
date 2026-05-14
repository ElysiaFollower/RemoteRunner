<!--
职责：为实现 agent 定义一个 active task 合同，让范围、验收、验证和交接可执行。
边界：不要在这里累积长期架构事实、原始日志或无关 follow-up 想法。
-->

# Remote Runner 真实机器 Opt-in 集成测试

## 目标

新增 Remote Runner 专用真实机器集成测试，把 machine doctor、session exec、file put/list/get 和 cleanup 变成可重复验证。测试默认跳过，只有显式设置环境变量时才连接真实机器；本轮使用用户允许的 Windows `SSHRunner` 目录跑一次真实验证。

## 非目标

- 不替换 legacy `tests/test_real_vm_integration.py`。
- 不要求 CI 默认拥有真实 SSH 机器。
- 不新增机器配置或写入凭据。
- 不在用户指定测试目录外创建、上传、下载或删除远程文件。

## 当前仓库事实

- 入口规则：`AGENTS.md`
- 初始化契约：`harness/bootstrap-contract.md`
- 当前功能项：F-010
- 相关文件/模块：`tests/test_remote_runner_real_integration.py`、`seed_runner/remote_cli.py`、`harness/feature_list.json`、`harness/progress.md`、`harness/session-handoff.md`
- 已知约束：真实机器 `windows-wsl` 已配置；允许写入目录为 `/mnt/c/Users/example/Desktop/SSHRunner`；文件传输需要 path mapping。

## 允许改动

- 新增 opt-in pytest 文件。
- 更新 harness 状态、证据和交接。
- 运行一次真实测试，环境变量显式指向 `SSHRunner`。

## 禁止改动

- 禁止硬编码真实 host、密码、密钥或用户隐私信息到测试文件。
- 禁止让真实集成测试默认运行。
- 禁止在真实 Windows 机器的 `SSHRunner` 目录外写入或删除文件。

## 验收标准

- 未设置环境变量时，新增真实测试自动 skip。
- 设置真实机器和测试 cwd 后，测试通过 machine doctor、创建 session、执行只读命令、上传探针文件、list 找到文件、get 下载并比对内容、远程删除探针文件、销毁 session。
- 失败时尽量销毁 session 并删除探针文件。
- 本地完整 pytest 仍通过。

## 验证命令

```sh
./scripts/harness-check.sh
python3 -m pytest tests/test_remote_runner_real_integration.py -q
REMOTE_RUNNER_RUN_REAL_TESTS=1 REMOTE_RUNNER_REAL_MACHINE='<machine_id>' REMOTE_RUNNER_REAL_TEST_CWD='<remote_cwd>' python3 -m pytest tests/test_remote_runner_real_integration.py -q
python3 -m pytest -q
git diff --check
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

- 真实机器无法 SSH/SFTP 连接。
- 测试需要在指定 `SSHRunner` 目录外写入文件才能继续。

## 下一步最佳动作

1. 新增 opt-in pytest，并用当前 Windows `SSHRunner` 配置跑一次真实验证。
