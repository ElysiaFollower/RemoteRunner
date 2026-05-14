<!--
职责：总结仓库 harness 的健康状态和下一步维护动作。
边界：不要存放完整审计日志、任务历史或项目架构细节。
-->

# Harness 质量

## 快照

- 上次审查：2026-05-14
- 审查者：Codex
- 总体状态：mvp-local-passing

## 健康信号

- `AGENTS.md` 长度：短路由，低于 150 行。
- WIP limit：1。
- 功能清单有效性：`./scripts/harness-check.sh` 通过。
- 交接新鲜度：2026-05-14 已更新。
- 验证命令健康度：`./scripts/harness-check.sh` 通过 0 warnings；`python3 -m pytest tests/test_remote_runner_mvp.py -q` 通过 31 passed；`python3 -m pytest tests/test_remote_runner_launch_suite.py -q` 通过 2 passed, 1 skipped；`python3 -m pytest -q` 通过 54 passed, 3 skipped；`git diff --check` 通过；Remote Runner Linux/SSH opt-in 真实集成测试通过 1 passed。
- 冷启动测试：`./init.sh` 已运行通过，指向事实来源和验证命令。
- 端到端覆盖：真实 VM opt-in 测试存在但本次未运行。
- 重复失败是否已执行化：已增加 `tests/test_remote_runner_mvp.py` 覆盖 no-mount machine/session/file 核心行为和 legacy 回归；已增加 `tests/test_remote_runner_launch_suite.py` 作为上线前长期复用验收资产。

## 维护队列

- 当前主支持平台已收束为 Linux/SSH + tmux；真实 session、后台命令、SFTP file put/get/list 和 cleanup 已在 Linux/SSH opt-in 测试中验证；默认测试仍不依赖真实机器。
- 交互式 `remote-runner machine add` 已落地；后续可考虑 credential reference 或系统钥匙串。
- Windows/WSL `startup_commands` 和 `path_mappings` 仅保留为兼容/未来 backend 输入；若未来重新验证，文件写入必须限制在用户明确授权目录内。
- 继续扩展 harness-check 或测试，检查目标 CLI 文档和实现是否同步。
- 后续大改前先保护 legacy `seed-runner` 可验证路径，避免无意破坏原型。
