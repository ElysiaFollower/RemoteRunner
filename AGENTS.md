# Agents

本文件是 Remote Runner 仓库的 agent 入口路由。不要把它扩写成百科全书；长期事实放 `docs/`，状态放 `harness/`，任务合同放 `plans/`，可执行检查放 `scripts/`。

## 项目灯塔

Remote Runner 是本地轻量级远程机器操作 CLI：用户在本地登记远程机器，使用者通过稳定 CLI 查询机器、创建会话、在远程目录执行命令、读取结构化输出、日志和产物。

当前仓库仍包含可运行的 `seed-runner` 原型。原型验证了 SSH/tmux/sshfs 复杂性需要被工具吸收，但 SEED、research、sshfs、tmux 都不是长期项目边界。

## 事实来源地图

- 项目目标、受众、范围、术语和冲突裁决：`docs/overview.md`
- 核心灯塔和不可变原则：`docs/architecture/core-lighthouse.md`
- MVP 需求和验收标准：`REQUIREMENTS.md`
- 目标 CLI 合同：`docs/reference/REMOTE_RUNNER_API.md`
- 当前原型 CLI：`docs/reference/SEED_RUNNER_API.md`
- 当前功能状态：`harness/feature_list.json`
- 进度和下一步：`harness/progress.md`、`harness/session-handoff.md`
- 质量和完成评估：`harness/evaluator-rubric.md`、`harness/quality.md`

## 开始流程

1. 运行 `./init.sh` 读取项目状态并执行 harness 检查。
2. 阅读 `docs/overview.md`，确认当前工作属于目标设计、原型兼容、profile/use case，还是 harness 维护。
3. 查看 `harness/feature_list.json` 和 `harness/session-handoff.md`，确认 WIP 状态。
4. 若要开发功能，先在 `plans/active/` 建立一个任务合同；默认 WIP=1。
5. 修改前检查 `git status --short`，不要覆盖他人或用户已有改动。

## 硬性规则

1. 仓库是唯一事实来源；会影响后续 agent 的目标、状态、决策和验证必须写回仓库。
2. 不把 research、SEED、实验或运维任一场景当作项目边界；它们只能是 profile/use case。
3. 不把 sshfs、tmux、rsync、Slurm 或某个库写成长期需求；它们只能是可替换 backend。
4. 不声称 `remote-runner` CLI 已实现，除非代码和测试已经落地。
5. 当前可运行行为以 `seed-runner` 原型、测试和 legacy API 为准；目标行为以 Remote Runner API 合同为准。
6. 正常工作流不得要求用户反复提供密码、私钥内容、跳板机细节或临时认证材料。
7. 不把密码、密钥、主机敏感细节写入日志、报告、issue、handoff 或提交。
8. 默认 WIP=1；`harness/feature_list.json` 最多一个 `active`。
9. `passing` 必须有验证命令和 evidence，不能只凭主观判断。
10. 初始化和定位整理不做业务功能迁移；大改前先保持目标、需求和定义无冲突。
11. 修改公共接口、状态目录、CLI 名称或兼容策略时，同步更新 requirements、API 文档、feature list 和 handoff。
12. 会话结束前更新 `harness/session-handoff.md`，记录验证证据、风险、脏文件和下一步。

## 验证阶梯

- Harness 检查：`./scripts/harness-check.sh`
- 聚焦验证：`python3 -m pytest tests/test_config.py tests/test_workflow_state.py -q`
- 完整本地验证：`python3 -m pytest -q`
- Remote Runner 真实机器验证：`REMOTE_RUNNER_RUN_REAL_TESTS=1 REMOTE_RUNNER_REAL_MACHINE=<machine_id> REMOTE_RUNNER_REAL_TEST_CWD=<remote_cwd> python3 -m pytest tests/test_remote_runner_real_integration.py -q`
- 真实 VM 验证：`SEED_RUNNER_RUN_REAL_VM_TESTS=1 python3 -m pytest tests/test_real_vm_integration.py -q`

真实机器/VM 验证需要人工预配置目标机器；默认本地验证不应依赖它。Remote Runner 真实测试只允许写入 `REMOTE_RUNNER_REAL_TEST_CWD` 指定目录。

## 完成定义

一次任务完成必须同时满足：

- 目标、范围、实现或文档改动与当前任务合同一致。
- 相关事实来源已同步更新，没有目标/需求/定义冲突。
- 必要验证已运行，结果和限制写入 handoff 或 feature evidence。
- 没有未解释的占位符、密钥、下载缓存、临时日志或机器特定状态进入仓库。
- `harness/session-handoff.md` 能让新 agent 三分钟内恢复上下文。

## 退出流程

1. 运行最小可靠验证，至少包括 `./scripts/harness-check.sh`。
2. 更新 `harness/feature_list.json`、`harness/progress.md` 和 `harness/session-handoff.md`。
3. 用 `git status --short` 记录最终脏文件。
4. 向用户报告改动、验证、残留风险和下一步。
