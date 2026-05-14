<!--
职责：提供最新的紧凑交接信息，让新 agent 能无歧义恢复当前任务。
边界：只保留当前可恢复状态；历史放 progress.md，稳定事实放 docs 或代码。
-->

# 会话交接

## 仓库状态

- 分支：`dev/remote-runner-persistent-terminals`
- 当前计划：`plans/archive/2026-05-14-remote-runner-persistent-terminal-sessions.md`。
- 当前功能项：`F-019 Remote Runner 持久 Terminal Session` passing；`F-001` 到 `F-004`、`F-006` 到 `F-019` 均为 passing；`F-005` profile/report 层未开始。
- 当前目标：Remote Runner 是基于 SSH 的本地 CLI，让 AI 能通过稳定命令访问外部机器终端、执行命令、收集结构化输出、日志和产物。
- `seedrunner` conda 环境已安装本仓库的 editable 包，`remote-runner` 现在可直接调用。
- 已安装 skill 已迁移为 `~/.codex/skills/remote-runner/SKILL.md`；旧 `~/.codex/skills/seed-runner` 已删除，不再保留 legacy skill 入口。

## 已落地能力

- Remote Runner 定位、核心灯塔、no-mount ADR、machine/session/file MVP spec、harness 和 archived plans 已提交。
- `remote-runner` CLI 已实现 machine、session、file、run once 基础能力；核心实现位于 `remote_runner`。
- `seed_runner.remote_*` 与 `seed_runner.utils` 目前是 legacy compatibility wrappers，继续 re-export `remote_runner.*` 目标实现对象。
- 机器配置支持交互式 SSH 信息录入、隐藏密码输入、同名覆盖确认、`startup_commands` 和 `path_mappings`。
- session exec 不依赖 mount；带 startup commands 的交互式 SSH 已清理 banner、命令回显、prompt 和 sentinel。
- SFTP `file put/get/list` 支持路径前缀映射，transfer records 和 artifact manifest 保留用户输入的远程路径。
- `run once` 支持上传输入、执行命令、拉回产物、保存 run manifest，并默认销毁临时 session。
- 后台 session command 已支持 `session exec --mode background`、`session command show/result/wait/stop`，并通过本地 state + 远端 command state 文件恢复跨 CLI 进程查询。
- 持久 terminal 已支持 `terminal create/list/show/send/read/destroy`，Linux/SSH 第一后端使用 tmux；同一 terminal 内多次输入保留 shell-local state，并保存本地 transcript。
- 新增上线验收资产：`tests/test_remote_runner_launch_suite.py`、`tests/remote_runner_launch_support.py`、`docs/testing/remote-runner-launch-acceptance.md`。
- 仓库根目录 `SKILL.md` 是当前 Remote Runner 操作 skill 的来源，不包含旧 mount/sshfs/tmux workflow。

## 验证证据

- 默认上线验收：`python3 -m pytest tests/test_remote_runner_launch_suite.py -q` 通过 2 passed, 1 skipped。
- 默认真实集成入口：`python3 -m pytest tests/test_remote_runner_real_integration.py -q` 通过 1 skipped。
- 完整本地验证：`python3 -m pytest -q` 通过 54 passed, 3 skipped。
- Harness 与格式检查：`./scripts/harness-check.sh` 通过 0 warnings；`git diff --check` 通过。
- 真实机器 opt-in 验收：`REMOTE_RUNNER_RUN_REAL_TESTS=1 REMOTE_RUNNER_REAL_MACHINE=linux-01 REMOTE_RUNNER_REAL_TEST_CWD=/tmp python3 -m pytest tests/test_remote_runner_real_integration.py -q` 通过 1 passed；写入范围限制在已配置安全测试目录，未记录真实机器细节；后台命令自然完成/stop 路径与 terminal 连续 shell state 都已覆盖。
- 环境入口验证：`conda run -n seedrunner remote-runner --help` 通过；`conda run -n seedrunner python -m remote_runner.cli --help` 通过。

## 安全与隐私边界

- 不应把密码、密钥、host、真实 machine id 或私人路径写入 docs、handoff、issue、commit message 或测试 fixture。
- 真实机器测试只能写入 `REMOTE_RUNNER_REAL_TEST_CWD` 指定目录；默认测试不得依赖真实机器。
- 当前真实机器验证已使用随机探针文件并 cleanup；仓库内只记录抽象验证结果。

## 仍未完成

- `F-005` 上层 profile、验收 DSL、报告层未开始；通用 `run once` 只是基础闭环。
- terminal 第一后端依赖远程 Linux/SSH 机器安装 tmux；带 `startup_commands` 的 Windows/WSL 机器暂不支持 terminal。
- legacy 真实 VM opt-in 测试未运行。
- 后续上线前仍建议按 `docs/testing/remote-runner-launch-acceptance.md` 重跑默认门禁和真实机器 opt-in 门禁。
- 一台 Linux 蓝本在密码更新后 `/tmp` 文件传输闭环已通过；`/home/ely/tmp` 是否可写仍取决于远端目录权限。

## 下一步最佳动作

1. 审阅 F-019 分支 diff，决定是否基于 PR #4 开堆叠 PR，或等 #4 合并后 rebase 再发 PR。
2. 如果继续演进 terminal，优先考虑 startup_commands/Windows 支持、PTY resize、实时输出 streaming 和访问控制。
3. 真实验证仍必须显式设置 `REMOTE_RUNNER_REAL_TEST_CWD`，且只写该目录。

## 常用命令

- 初始化：`./init.sh`
- Harness 检查：`./scripts/harness-check.sh`
- 上线验收默认门禁：`python3 -m pytest tests/test_remote_runner_launch_suite.py -q`
- Remote Runner MVP 聚焦验证：`python3 -m pytest tests/test_remote_runner_mvp.py -q`
- 完整验证：`python3 -m pytest -q`
- Remote Runner 真实机器验证：`REMOTE_RUNNER_RUN_REAL_TESTS=1 REMOTE_RUNNER_REAL_MACHINE=<machine_id> REMOTE_RUNNER_REAL_TEST_CWD=<remote_cwd> python3 -m pytest tests/test_remote_runner_launch_suite.py tests/test_remote_runner_real_integration.py -q`
- legacy 真实 VM 验证：`SEED_RUNNER_RUN_REAL_VM_TESTS=1 python3 -m pytest tests/test_real_vm_integration.py -q`
