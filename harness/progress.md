<!-- 职责：只记录当前实现进度；历史由 Git 和归档任务保存。 -->

# 当前进度

## F-032 Register Existing tmux（已切换）

- 隔离 worktree 已完成非拥有式注册：`session register` 从注册时刻记录单 pane 外部 tmux，
  `destroy` 只移除 RR recorder 和 marker，保留外部 tmux。
- 精确名称、单 pane、无既有 pipe/marker、唯一 live owner 和归属异常边界已有真实 tmux 测试。
- 完整门禁 40 passed；0.5.0 wheel 非 editable 安装和默认环境生产 smoke 均通过。任务合同已归档到
  `plans/archive/2026-07-22-register-existing-tmux.md`。
- main、系统 editable runtime 和 global Skill 已同步到 0.5.0；生产 smoke 清理后既有业务 tmux
  与 state 集合保持不变。

## Local Terminal V4

- 状态：已完成实现、主仓库同步、系统安装、global Skill 发布和默认生产环境 smoke。
- 主仓库：`/Users/ely/workspace/research/agent/RemoteRunner`，`main` 已包含完整 V4 分支。
- 系统 runtime：`remote-runner 0.5.0` editable 指向主仓库；旧 `seed-runner` metadata 已卸载。
- global Skill：已与仓库内 canonical `SKILL.md` 同步。

已完成：

- 收敛为本地 tmux Terminal、Session/Bootstrap、State 三个生产 Module。
- `pipe-pane` 在真实 shell 启动前记录 raw transcript，并检测 pane 与 recorder 双重健康。
- 实现透明 `send/key/read/tail/show/attach/destroy/purge` Interface。
- 实现 UUID 历史、存活期可读名称、直接时间元信息和不兼容 state schema。
- 实现可审查、同步、独占、可超时终止的 Instance bootstrap hook。
- 删除 remote/Windows/batch/file/run/artifact/seed-runner 生产路径、依赖、CLI 和测试债务。
- 新测试覆盖真实隔离 tmux、PTY attach、no-echo、Ctrl-C、lost/reuse/purge、bootstrap、
  state 初始化竞态和 wheel 安装 smoke。

最终门禁：34 passed；Black、Flake8、mypy、harness、init、diff、非 editable wheel smoke 和
默认 state/default tmux production smoke 全部通过。旧 state 与旧 Skill 已独立归档，测试
Session 已 destroy/purge。F-030、F-031、F-032 均为 passing，当前无 active WIP。
