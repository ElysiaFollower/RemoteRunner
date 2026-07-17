<!-- 职责：只记录当前实现进度；历史由 Git 和归档任务保存。 -->

# 当前进度

## Local Terminal V4 cutover

- 状态：实现与发布验证完成；切换前基线、顺序和失败回退已审计，等待用户明确授权执行破坏性
  cutover。
- 分支：`codex/rr-terminal-observation-v3`。
- 隔离 worktree：`/Users/ely/workspace/research/agent/RemoteRunner-terminal-v3`。
- 稳定主仓库、editable runtime、global Skill、真实 RR state 和默认 tmux 均未修改。

已完成：

- 收敛为本地 tmux Terminal、Session/Bootstrap、State 三个生产 Module。
- `pipe-pane` 在真实 shell 启动前记录 raw transcript，并检测 pane 与 recorder 双重健康。
- 实现透明 `send/key/read/tail/show/attach/destroy/purge` Interface。
- 实现 UUID 历史、存活期可读名称、直接时间元信息和不兼容 state schema。
- 实现可审查、同步、独占、可超时终止的 Instance bootstrap hook。
- 删除 remote/Windows/batch/file/run/artifact/seed-runner 生产路径、依赖、CLI 和测试债务。
- 新测试覆盖真实隔离 tmux、PTY attach、no-echo、Ctrl-C、lost/reuse/purge、bootstrap、
  state 初始化竞态和 wheel 安装 smoke。

最终门禁：34 passed；Black、Flake8、mypy、harness、init、diff 和非 editable wheel smoke
全部通过。实现任务合同已归档；当前唯一 WIP 是
`plans/active/2026-07-17-local-terminal-v4-cutover.md`。预检确认整个分支可 fast-forward，且旧
package metadata、真实 state 与独立 global Skill 都有明确的备份和回退边界。当前稳定工具未受
影响。
