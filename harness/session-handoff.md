<!--
职责：提供最新的紧凑交接信息，让新 agent 能无歧义恢复当前任务。
边界：只保留当前可恢复状态；历史放 progress.md，稳定事实放 docs 或代码。
-->

# 会话交接

## 仓库状态

- 分支：`dev/remote-runner-machine-session-mvp`
- 当前阶段性提交：
  - `561c349 docs(harness): define remote runner lighthouse`
  - `9097b9e feat(remote-runner): add mount-free machine session file run CLI`
  - `f80f490 test(remote-runner): add opt-in real machine integration`
  - `bf47cc1 docs(harness): record staged remote runner handoff`
  - 另有本文件所在的 harness-check handoff 标题检查修复提交
- 当前计划：无 active；上一轮完成计划已归档至 `plans/archive/2026-05-11-remote-runner-utils-migration.md`。
- 当前功能项：无 active；`F-001`、`F-002`、`F-003`、`F-004`、`F-006`、`F-007`、`F-008`、`F-009`、`F-010`、`F-011`、`F-012`、`F-013`、`F-014`、`F-015`、`F-016` passing；`F-005` profile/report 层未开始。

## 已落地能力

- Remote Runner 定位、核心灯塔、no-mount ADR、machine/session/file MVP spec、harness 和 archived plans 已提交。
- `remote-runner` CLI 已实现 machine、session、file、run once 基础能力；核心实现现在位于 `remote_runner`。
- `seed_runner.remote_*` 目前是 legacy compatibility wrappers，继续 re-export `remote_runner.*` 目标实现对象。
- 机器配置支持交互式 SSH 信息录入、隐藏密码输入、同名覆盖确认、`startup_commands` 和 `path_mappings`。
- session exec 不依赖 mount；带 startup commands 的交互式 SSH 已清理 banner、命令回显、prompt 和 sentinel。
- SFTP `file put/get/list` 支持路径前缀映射，transfer records 和 artifact manifest 保留用户输入的远程路径。
- `run once` 支持上传输入、执行命令、拉回产物、保存 run manifest，并默认销毁临时 session。
- 默认跳过的真实机器 opt-in 集成测试已提交：显式设置机器和测试目录后验证 doctor、session exec、file put/list/get、内容比对、远程 cleanup 和 session destroy。
- 时间戳已改为 timezone-aware UTC API，测试输出不再有 `datetime.utcnow()` deprecation warnings。
- `remote_runner` 现在不再依赖 `seed_runner.utils`；shared helper 实现已迁移到 `remote_runner.utils`，legacy `seed_runner.utils` 仅作为兼容 wrapper。

## 验证证据

- 最近验证：`python3 -m remote_runner.cli --help` 通过；`python3 -m seed_runner.remote_cli --help` 通过；`python3 -m pytest tests/test_remote_runner_mvp.py -q` 通过 26 passed；`python3 -m pytest -q` 通过 47 passed, 2 skipped；`./scripts/harness-check.sh` 通过 0 warnings；`git diff --check` 通过；`remote_runner` import 边界检查无残留 `seed_runner.utils` 引用。
- 此前 harness 验证：`./init.sh` 通过；`./scripts/harness-check.sh` 0 warnings。
- 此前 CLI/import 验证：`python3 -m remote_runner.cli --help` 通过；`remote_runner.remote_*` import smoke 通过。
- 此前真实机器验证：machine/session/file/run 基础闭环通过；真实机器细节不写入仓库，测试写入范围限制在显式 `REMOTE_RUNNER_REAL_TEST_CWD`。

## 安全与隐私边界

- 提交前已将仓库文档和测试中的真实机器别名与本机 Windows 用户路径替换为通用示例。
- 不应把密码、密钥、host、真实 machine id 或私人路径写入 docs、handoff、issue、commit message 或测试 fixture。
- 真实机器测试只能写入 `REMOTE_RUNNER_REAL_TEST_CWD` 指定目录；不要默认运行 opt-in 测试。

## 仍未完成

- 共享工具函数仍在 `seed_runner.utils`，`remote_runner` 实现仍复用这些通用 helper；是否迁移 shared utils 需要单独小任务评估。
- `F-005` 上层 profile、验收 DSL、报告层未开始；通用 `run once` 只是基础闭环。
- legacy 真实 VM opt-in 测试未运行。

## 下一步最佳动作

1. 开始新 active plan：profile/report 层第一切片，或评估是否迁移共享 `utils` 到 `remote_runner.utils`。
2. 若继续真实机器验证，必须显式设置 `REMOTE_RUNNER_REAL_TEST_CWD`，且只写该目录。
3. 若准备发 PR，先运行 `./scripts/harness-check.sh`、`python3 -m pytest -q`、`git diff --check`。

## 常用命令

- 初始化：`./init.sh`
- Harness 检查：`./scripts/harness-check.sh`
- Remote Runner MVP 聚焦验证：`python3 -m pytest tests/test_remote_runner_mvp.py -q`
- 完整验证：`python3 -m pytest -q`
- Remote Runner 真实机器验证：`REMOTE_RUNNER_RUN_REAL_TESTS=1 REMOTE_RUNNER_REAL_MACHINE=<machine_id> REMOTE_RUNNER_REAL_TEST_CWD=<remote_cwd> python3 -m pytest tests/test_remote_runner_real_integration.py -q`
- legacy 真实 VM 验证：`SEED_RUNNER_RUN_REAL_VM_TESTS=1 python3 -m pytest tests/test_real_vm_integration.py -q`
