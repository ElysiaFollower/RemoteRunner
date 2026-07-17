# Agents

本文件是 Remote Runner 仓库的入口路由。长期事实放 `docs/`，状态放 `harness/`，任务合同放
`plans/`，可执行检查放 `scripts/`。

## 项目灯塔

Remote Runner 为 Agent 和人类提供同一个本地持久 shell：一个 Session 对应一个本机 tmux pane，
pane 的 raw output 从 shell 启动前持续写入 append-only transcript。SSH、远端 tmux、Slurm、
`nohup` 等都是使用者在 shell 中明确执行的普通操作。

V4 是不兼容重写：不保留 machine、remote-tmux、openssh-pty、Windows agent、structured exec、
file/run/artifact、seed-runner 或旧 state 兼容路径。

## 事实来源地图

- 目标、边界和术语：`docs/overview.md`、`CONTEXT.md`
- 不变量和职责：`docs/architecture/core-lighthouse.md`
- 需求与验收：`REQUIREMENTS.md`
- CLI 和 bootstrap 合同：`docs/reference/REMOTE_RUNNER_API.md`
- 当前功能状态：`harness/feature_list.json`
- 进度和交接：`harness/progress.md`、`harness/session-handoff.md`

## 开始流程

1. 运行 `./init.sh`。
2. 阅读 `docs/overview.md` 和 active task。
3. 检查 `git status --short`，不要覆盖用户改动。
4. 开发功能前确保 `plans/active/` 只有一个任务合同、feature 只有一个 active。

## 硬性规则

1. Session 核心只能是本地 tmux Terminal，不重新引入 backend enum 或远端控制分支。
2. transcript 是 raw append-only 事实源；不清洗、推断、摘要、轮转或改写。
3. RR 不推断 busy、prompt、完成、exit code 或远端存活；Skill 教 Agent 看可见 prompt。
4. RR 不保存或返回原始输入，不把密码、密钥或 host 敏感信息写入报告、handoff 或提交。
5. Instance 只挂载独立 bootstrap hook；prompt/login 判断留在 hook，不进入 core。
6. 人类 attach 是正式用法；state 必须暴露 tmux 名和 transcript 绝对路径。
7. destroy 保留历史，purge 才删除；lost Session 绝不自动重建。
8. 新 state 拒绝旧 schema，不新增迁移或兼容 alias。
9. 默认 WIP=1；passing 必须有可复现 evidence。
10. 修改公共 Interface 时同步需求、CLI 文档、Skill、测试和 handoff。
11. 测试必须使用独立 tmux socket 和临时 state，不得操作默认/业务 tmux。
12. 不在隔离开发中运行 editable install 或发布 global Skill。

## 验证阶梯

```bash
python3 -m pytest tests/test_state.py tests/test_session.py tests/test_bootstrap.py tests/test_cli.py -q
python3 -m pytest tests/test_tmux_integration.py -q
python3 -m pytest -q
python3 -m black --check remote_runner tests
python3 -m flake8 remote_runner tests --ignore=E203,W503,E501
python3 -m mypy remote_runner
./scripts/harness-check.sh
git diff --check
```

## 完成定义

- 代码、文档、Skill、测试和 active task 的职责与字段完全一致。
- 真实隔离 tmux 覆盖输入、输出、human attach、no-echo、key、lost/destroy/purge 和 bootstrap。
- 无旧 backend/兼容模块、无测试 tmux/state/process 残留、无秘密或临时日志进入仓库。
- `harness/session-handoff.md` 能让新 Agent 三分钟内恢复状态和风险。

## 退出流程

1. 跑完整验证与 `./scripts/harness-check.sh`。
2. 更新 feature、progress、quality 和 handoff。
3. 记录最终 `git status --short`。
4. 报告改动、证据、残留风险和破坏性切换前置动作。
