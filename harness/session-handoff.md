<!--
职责：提供最新的紧凑交接信息，让新 agent 能无歧义恢复当前任务。
边界：只保留当前可恢复状态；历史放 progress.md，稳定事实放 docs 或代码。
-->

# 会话交接

## 仓库状态

- 分支：`dev-windows-agent-pwsh-backend`。
- 最近计划：`plans/archive/2026-06-19-stale-tmux-session-recovery.md`。
- 当前功能项：`F-023 Remote Runner stale tmux session recovery` passing；`F-022`、`F-021`、`F-020` passing；`F-005` profile/report 层未开始。
- 当前目标状态：Remote Runner 已支持 Linux/SSH + tmux 和 direct Windows OpenSSH + windows-agent；本轮补齐 Linux/tmux 历史 stale 状态恢复。

## 本轮完成

- 通过 configured Linux/tmux machine 历史状态复现 agent 容易卡住的形态：本地 session 仍为 `active`/`busy`，command 仍为 `running`，但远端 tmux session 已不存在。
- 新增 `ParamikoRemoteBackend.terminal_exists`，用于判断 Linux/tmux terminal 或 Windows agent task 是否仍存在。
- `session command show/wait` 对 stale running command 不再无限等待；当 tmux session 已丢失时，命令会收敛为 `failed`，并返回解释性 `error`。
- `session show/exec/destroy` 会恢复 stale `active_command`：落一条 failed command record、清除 `busy`，并把不可用 session 标为 `lost`。
- `session exec` 现在拒绝非 `active` session；`destroy` 仍可把 `lost` session 收尾为 `destroyed`。
- 新增单元测试覆盖 stale running background command 和 stale active command reservation。

## 验证证据

- `python3 -m py_compile remote_runner/remote_backend.py remote_runner/remote_session.py tests/test_remote_runner_mvp.py` 通过。
- `python3 -m pytest tests/test_remote_runner_mvp.py -q` 通过 `41 passed`。
- `python3 -m pytest tests/test_remote_runner_real_integration.py -q` 默认通过 `2 skipped`。
- configured Linux/tmux machine 新鲜压力自测通过：大量 stdout 截断、12 秒静默 wait、同步 timeout 后恢复、后台命令轮询/wait/stop、file put/list/get、run once、外部 kill tmux 后 lost/exec reject/destroy、最终 exec、cleanup 和 destroy。
- 另一台 Linux/tmux machine 深度自测通过：持久 shell 状态、同步 timeout 后恢复、后台 wait、file put/get、run once、外部 kill tmux 后 lost/destroy、cleanup 和 destroy。
- `REMOTE_RUNNER_RUN_REAL_TESTS=1 REMOTE_RUNNER_REAL_MACHINE=<linux_machine_id> REMOTE_RUNNER_REAL_TEST_CWD=<remote_cwd> python3 -m pytest tests/test_remote_runner_real_integration.py -q` 通过 `1 passed, 1 skipped`。
- `REMOTE_RUNNER_RUN_REAL_TESTS=1 REMOTE_RUNNER_REAL_MACHINE=<linux_machine_id> REMOTE_RUNNER_REAL_TEST_CWD=<remote_cwd> python3 -m pytest tests/test_remote_runner_launch_suite.py -q` 通过 `3 passed`。
- `python3 -m pytest -q` 通过 `64 passed, 4 skipped`。
- `./scripts/harness-check.sh` 通过 `0 warnings`。
- `git diff --check` 通过。
- configured Linux/tmux machine 历史 stale command 已由 `running` 收敛为 `failed`，error 为远端 tmux session 已不存在。
- configured Linux/tmux machine 历史 stale busy session 已由 `active`/`busy` 收敛为 `lost`/`failed`。

## 仍未完成

- 尚未批量收敛所有历史 session；当前逻辑是在 `session show`、`session command show/wait`、`session exec`、`session destroy` 触达时惰性恢复。
- 可以后续新增显式 `session recover` 或 `session list --refresh`，批量标记历史 stale session。
- Windows backend 仍不支持 background command/stop。
- `docs/issues/` 是本轮开始前已存在的未跟踪目录；未纳入本任务处理。

## 安全与隐私边界

- 不把密码、密钥、真实 host、真实账号或私人路径写入仓库、handoff 或提交信息。
- configured Linux/tmux machine 真实验证只读取 Remote Runner 状态和运行轻量探针；没有启动训练、没有杀未知业务进程、没有删除历史日志。
- 本轮只收敛本地 Remote Runner 状态；远端历史 `.remote-runner` command 目录保留。

## 下一步最佳动作

1. 提交 F-023 stale recovery 修复。
2. 后续可单独设计批量 recover/list refresh 和更明确的 timeout UX。

## 常用命令

- Harness 检查：`./scripts/harness-check.sh`
- 聚焦测试：`python3 -m pytest tests/test_remote_runner_mvp.py -q`
- 默认真实测试入口：`python3 -m pytest tests/test_remote_runner_real_integration.py -q`
- 完整验证：`python3 -m pytest -q`
