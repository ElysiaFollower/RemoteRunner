<!--
职责：提供最新的紧凑交接信息，让新 agent 能无歧义恢复当前任务。
边界：只保留当前可恢复状态；历史放 progress.md，稳定事实放 docs 或代码。
-->

# 会话交接

## 仓库状态

- 分支：`dev-windows-agent-pwsh-backend`。
- 最近计划：`plans/archive/2026-06-24-readable-session-names.md`。
- 当前功能项：`F-024 Remote Runner readable session names` passing；`F-023`、`F-022`、`F-021`、`F-020` passing；`F-005` profile/report 层未开始。
- 当前目标状态：Remote Runner 已支持 Linux/SSH + tmux 和 direct Windows OpenSSH + windows-agent；本轮已处理本地 `docs/issues/` 中确认真实的可读 session name 缺口。

## 本轮完成

- 已实现 `session create --name`，session state/public response 保存并返回 `name`。
- 新增 `RemoteSessionManager.resolve_session_id`，按精确 `session_id` 优先，其次解析唯一 readable name；歧义时报错。
- `session show/exec/command list/show/wait/stop/send/read/logs/destroy` 和 `file put/get/list` 均支持 `session_id` 或唯一 name。
- 新增 name 校验：非空、只允许字母/数字/`.`/`_`/`-`、不得以 `sess_` 开头；同机未销毁 session 重名拒绝，destroyed 后可复用。
- 旧 session state 没有 `name` 时仍可按 `session_id` 使用。
- 同步 README、REQUIREMENTS、Remote Runner API、getting-started、SKILL、feature list、progress 和 handoff。
- 已删除已解决的本地 `docs/issues/` 暂存文件。

## 验证证据

- `python3 -m py_compile remote_runner/remote_backend.py remote_runner/remote_session.py tests/test_remote_runner_mvp.py` 通过。
- `python3 -m pytest tests/test_remote_runner_mvp.py -q` 通过 `45 passed`。
- `python3 -m remote_runner.cli session create --help` 显示 `--name`。
- `python3 -m pytest tests/test_remote_runner_launch_suite.py -q` 通过 `2 passed, 1 skipped`。
- `python3 -m pytest tests/test_remote_runner_real_integration.py -q` 默认通过 `2 skipped`。
- `python3 -m pytest -q` 通过 `68 passed, 4 skipped`。
- `./scripts/harness-check.sh` 通过 `0 warnings`。
- `git diff --check` 通过。
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
- `docs/issues/` 暂存目录已清空；其中 readable session name 问题已由 F-024 处理。

## 安全与隐私边界

- 不把密码、密钥、真实 host、真实账号或私人路径写入仓库、handoff 或提交信息。
- configured Linux/tmux machine 真实验证只读取 Remote Runner 状态和运行轻量探针；没有启动训练、没有杀未知业务进程、没有删除历史日志。
- 本轮只收敛本地 Remote Runner 状态；远端历史 `.remote-runner` command 目录保留。

## 下一步最佳动作

1. 提交 F-024 readable session names 修复。
2. 后续可单独设计批量 recover/list refresh 和更明确的 timeout UX。

## 常用命令

- Harness 检查：`./scripts/harness-check.sh`
- 聚焦测试：`python3 -m pytest tests/test_remote_runner_mvp.py -q`
- 默认真实测试入口：`python3 -m pytest tests/test_remote_runner_real_integration.py -q`
- 完整验证：`python3 -m pytest -q`
