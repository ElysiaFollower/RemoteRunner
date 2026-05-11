<!--
职责：总结仓库 harness 的健康状态和下一步维护动作。
边界：不要存放完整审计日志、任务历史或项目架构细节。
-->

# Harness 质量

## 快照

- 上次审查：2026-05-08
- 审查者：Codex
- 总体状态：mvp-local-passing

## 健康信号

- `AGENTS.md` 长度：短路由，低于 150 行。
- WIP limit：1。
- 功能清单有效性：`./scripts/harness-check.sh` 通过。
- 交接新鲜度：2026-05-08 已更新。
- 验证命令健康度：`./scripts/harness-check.sh` 通过 0 warnings；`python3 -m pytest -q` 通过 36 passed, 1 skipped, 73 warnings；black check 通过；`git diff --check` 通过；尾随空白扫描无结果；Windows SSHRunner 真实 startup 验证通过。
- 冷启动测试：`./init.sh` 已运行通过，指向事实来源和验证命令。
- 端到端覆盖：真实 VM opt-in 测试存在但本次未运行。
- 重复失败是否已执行化：已增加 `tests/test_remote_runner_mvp.py` 覆盖 no-mount machine/session/file 核心行为和 legacy 回归。

## 维护队列

- 真实 SSH session exec 已在 Windows/WSL 机器上验证；真实 SFTP 行为还需要 Remote Runner 专用 integration 测试或人工验证。
- 交互式 `remote-runner machine add` 已落地；后续可考虑 credential reference 或系统钥匙串。
- Windows 文件写入验证必须限制在 `/mnt/c/Users/example/Desktop/SSHRunner` 或对应 Windows `SSHRunner` 目录内。
- 继续扩展 harness-check 或测试，检查目标 CLI 文档和实现是否同步。
- 处理现有 `datetime.utcnow()` 弃用警告。
- 后续大改前先保护 legacy `seed-runner` 可验证路径，避免无意破坏原型。
