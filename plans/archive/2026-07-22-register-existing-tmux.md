<!-- 职责：定义把单 pane 的既有本地 tmux 非拥有式注册为 RR Session 的实现合同。 -->

# Register Existing Local tmux

## 目标

增加 `session register`，让 Agent 或人类把一个已经存在的本地 tmux Session 纳入同一套
send/key/read/tail/show/attach Interface，而不重启 shell、不引入第二 Terminal/backend，也不把
外部 tmux 的生命周期所有权转给 RR。

## 公共合同

- CLI：`remote-runner session register --tmux-session <tmux-name> [--name <rr-name>]`。
- tmux Session 必须精确存在且恰好包含一个 pane；多 pane 因目标含糊而拒绝。
- pane 已有 `pipe-pane` 或 RR ownership marker 时拒绝，绝不覆盖已有 recorder/注册关系。
- transcript 只包含注册成功后的 raw pane output；不调用 `capture-pane` 伪造既往 raw 历史。
- `session show` 增加直接事实 `tmux_session_origin`，值为 `created` 或 `registered`。
- registered Session 的 `initial_cwd` 是注册时 `pane_current_path`，`local_shell_path` 为 null，因为
  RR 没有启动也无法诚实知道该 shell。
- registered Session 的 `destroy` 停止属于该 RR Session 的 recorder、清除 marker、保留原 tmux，
  然后按普通 RR 生命周期保留 transcript、释放名称；purge 不变。
- created Session 的现有 destroy 语义不变，仍终止 RR 创建的 tmux Session。
- registered pane/recorder/marker 任一丢失时收敛为 lost，不自动修复或重新注册。
- 同一个 pane 不能同时对应两个 live RR Session；并行任务仍使用独立 tmux/RR Session。

## 状态兼容判断

本改动不更换 state 根 schema：现有 V4 Session 只有 `created` 这一种可能来源，读取缺少新字段的
既有 V4 record 时对外报告 `created`；所有新 record 都显式写入 `tmux_session_origin`。这不是旧
产品迁移或 alias，不读取任何 V4 之前的 state。

## 验收

- 独立 tmux socket 覆盖注册、透明输入输出、show 字段、destroy 后外部 tmux 存活、名称复用。
- 覆盖不存在、同名 prefix、多 pane、已有 pipe、重复注册、lost recorder/marker。
- created Session 回归证明 destroy 仍杀 RR-owned tmux，既有 V4 record 缺字段仍解释为 created。
- README、requirements、overview/lighthouse、CLI reference、Skill、tests 和 harness 同步。
- 不修改 main、系统 editable runtime、默认 state/default tmux 或 global Skill。

## 验证

```bash
python3 -m pytest -q
python3 -m black --check remote_runner tests
python3 -m flake8 remote_runner tests --ignore=E203,W503,E501
python3 -m mypy remote_runner
./scripts/harness-check.sh
git diff --check
```

## 完成证据

- 2026-07-22 完整测试 40 passed，其中真实隔离 tmux 10 passed。
- Black、Flake8、mypy、harness、init、diff 与 canonical Skill validation 通过。
- 0.5.0 wheel 在临时目录非 editable 安装，从源码目录外完成 register/send/tail/destroy；外部
  tmux 在 destroy 后仍存活，recorder 已移除。
- 实现与发布材料已准备完毕，但仍隔离于开发 worktree；未修改 main、当前 editable runtime、
  默认 state/default tmux 或 global Skill。

## 生产切换

- 用户授权后 main 从 `14fae03` fast-forward 到 `30ba4d0`，系统 editable distribution 更新为
  0.5.0，global Skill 原子同步为 SHA-256 `7dea116...`。
- 默认环境 production smoke 完成 register/send/tail/show/destroy/purge；RR destroy 后外部 tmux
  保持存活，最终清理后既有 tmux 与 state 集合逐项不变。
- 切换后完整门禁与 global Skill validation 再次通过。
