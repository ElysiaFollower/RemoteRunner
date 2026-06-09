# Remote Runner Tmux Server Restart Interface

## 目标

为 Linux/SSH + tmux backend 增加一个 direct-SSH 机器级接口，用于在确认没有依赖该 tmux server 的活跃 tmux session 后重启远端用户的 tmux server，从而刷新 tmux-backed shell 继承的 Unix 补充组和登录上下文。

## 非目标

- 不改变 `session create/exec/send/read/destroy` 的持久 shell 模型。
- 不默认杀掉非 Remote Runner 管理的 tmux session。
- 不实现 sudo、systemd、daemon、非 tmux backend 或 Windows/WSL 持久 session 支持。
- 不修复所有历史坏状态记录；只让新接口能基于当前状态安全拒绝或执行。

## 当前仓库事实

- 入口规则：`AGENTS.md`
- 初始化契约：`harness/bootstrap-contract.md`
- 当前功能项：`F-021`
- 相关文件/模块：`remote_runner/cli.py`、`remote_runner/remote_machine.py`、`remote_runner/remote_backend.py`、`remote_runner/remote_state.py`、`tests/test_remote_runner_mvp.py`、`docs/reference/REMOTE_RUNNER_API.md`、`docs/overview.md`、`docs/lessons-learned/`
- 已知约束：当前持久 session 第一 backend 是 Linux/SSH + tmux；`tmux kill-server` 会杀掉该用户所有 tmux session，因此接口必须先检查 active Remote Runner tmux session 和远端现存 tmux sessions。

## 允许改动

- 新增经验教训记录目录和本问题条目。
- 新增 machine 级 CLI/API：`remote-runner machine restart-tmux-server <machine_id> --json`。
- 新增 backend direct-SSH 方法，用于检查远端 tmux session 并执行 `tmux kill-server`。
- 新增 focused 单元测试和 CLI JSON 测试。
- 同步 API 文档、overview、feature list、progress 和 session handoff。

## 禁止改动

- 不绕过凭据脱敏要求。
- 不把 host、私钥、密码、真实机器敏感细节写入文档或测试 fixture。
- 不把 tmux 写成长期产品边界；只记录为当前 Linux/SSH backend 实现细节。
- 不改 `seed-runner` legacy mount/session 行为。

## 验收标准

- 当同一 machine 存在 active Remote Runner tmux session 时，restart 接口拒绝执行并返回阻塞 session 列表。
- 当远端 `tmux ls` 仍存在任何 session 时，restart 接口拒绝执行并返回远端 session 列表，避免误杀非 Remote Runner tmux session。
- 当没有 active Remote Runner tmux session 且远端 tmux server 存在但无 session 时，接口通过 direct SSH 执行 `tmux kill-server` 并返回 `restarted`。
- 当远端没有 tmux server 时，接口返回 `not_running`，不视为错误。
- CLI 输出保持单 JSON 对象，错误走现有 JSON error 机制。

## 验证命令

```sh
./scripts/harness-check.sh
python3 -m pytest tests/test_remote_runner_mvp.py -q
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

- 无法在不误杀非 Remote Runner tmux session 的情况下判断远端 tmux session 状态。
- 现有 state schema 无法可靠识别当前 backend 类型，且没有保守拒绝路径。

## 下一步最佳动作

1. 实现 backend direct-SSH `restart_tmux_server` 方法和 machine manager 安全检查。
