<!-- 当前可恢复状态；历史过程见 harness/progress.md。 -->

# 会话交接

## 仓库状态

- 开发 worktree：`/Users/ely/workspace/research/agent/RemoteRunner-terminal-v2`
- 分支：`codex/rr-terminal-session-v2`
- 隔离基线提交：`1982ecb Capture OpenSSH PTY runtime baseline`
- 当前功能：`F-027 Remote Runner 人类式 Terminal Session V2` passing；任务合同已归档到
  `plans/archive/2026-07-15-terminal-session-v2.md`。
- stable worktree `/Users/ely/workspace/research/agent/RemoteRunner`、其 editable Python 安装、
  真实 Remote Runner state 和现有 tmux session 均未修改。
- 实现和文档已提交到当前分支，提交标题为 `Implement human-style terminal sessions`；tracked
  worktree 清洁。不要把 ignored `.env.machines` 或开发 venv/state 提交。

## 本轮完成

- tmux-backed session 创建时建立 append-only transcript recorder；`session read` 不再依赖
  `capture-pane` snapshot overlap 猜测。
- `openssh-pty` 先创建 pane、接上 recorder，再在 pane 中可见地输入
  `exec ssh -tt <alias>`，避免遗漏最早的 SSH 输出。
- `session send` 只接受一行 terminal input，返回 accepted `input`，busy 时拒绝交错输入。
- 新增 `session interrupt`，等价于对同一 pane 发送 `Ctrl-C`。
- `openssh-pty session exec` 在任何 pane 输入前明确拒绝；原 marker/`eval` command path 已移除。
- `ssh-tmux` 和 `windows-agent` 的 structured exec 暂作兼容；长期迁移目标是独立 job 层。
- 同步 README、REQUIREMENTS、overview、core lighthouse、API、platform support、getting
  started、canonical `SKILL.md`、feature list 和测试。
- canonical skill 只改在本分支；开发期间没有热更新全局 live skill。

## 验证证据

- Terminal V2 聚焦测试：`tests/test_terminal_session_v2.py`，14 passed；其中真实本地 tmux
  bash/zsh 场景 13 个，另有 remote tmux create/recorder 命令构造单元测试 1 个。
  覆盖原样可见输入、cwd/env 连续、append-only cursor、Ctrl-C 后同一 shell 恢复、exec/busy/
  multiline 拒绝和 CLI interrupt parser。
- MVP：`tests/test_remote_runner_mvp.py`，56 passed。
- Launch：`tests/test_remote_runner_launch_suite.py`，2 passed, 1 skipped。
- 全仓：93 passed, 4 skipped。
- `git diff --check` 通过；`./scripts/harness-check.sh` 通过。
- 测试完成后没有 `rr_local_sess_*` tmux session 遗留。
- 未运行真实 SSH server smoke；任务合同明确本地 tmux 已覆盖核心 terminal transport，真实
  SSH 只验证认证/网络边界，不阻塞本切片。

## 仍未完成

- `openssh-pty file get` 仍是借用已登录 PTY 的 legacy transfer protocol。它不属于新的
  `session send` 契约；传输结束后会恢复 append-only recorder，但长期应迁移到独立 file
  transport，避免 live terminal 承担协议流量。
- `ssh-tmux` / `windows-agent session exec` 仍保留结构化兼容语义。不要把这个兼容层继续
  扩张成 session 的核心抽象；新 batch 能力应进入 job/run 边界。
- transcript 是 terminal stream，PTY 不承诺独立 stdout/stderr；结构化 stdout/stderr/exit
  code 应由 job/run 提供。
- 全局安装与 skill 尚未切换到本分支，这是刻意的稳定性隔离，不是遗漏。

## 安全与隐私边界

- 未连接真实机器，未读取或写入真实 Remote Runner session transcript/state。
- 未记录 host、密码、token、私钥内容或真实远程目录。
- ignored `.env.machines` 仅为隔离 worktree 的 legacy 测试配置，不进入 git diff。
- 测试只创建随机 `rr_local_sess_*` 本地 tmux session，并已全部销毁；当前列出的其他 tmux
  session 属于既有工作，不得操作。

## 下一步最佳动作

1. 审阅本分支 diff，确认兼容边界后提交/合并。
2. 在没有正在运行的旧 Remote Runner 工作时，重新安装 editable package，并从本分支发布
   canonical `SKILL.md` 到全局 skill 位置。
3. 可选运行一台真实 SSH 机器 smoke，只验证 `create -> send -> read -> interrupt -> destroy`；
   不需要为核心 terminal 语义重复本地 tmux 已覆盖的测试。
4. 后续单独建任务迁移 structured exec 和 PTY file-get protocol 到 job/file transport。

## 常用命令

```bash
cd /Users/ely/workspace/research/agent/RemoteRunner-terminal-v2
/Users/ely/.cache/remote-runner-terminal-v2-venv/bin/python -m pytest tests/test_terminal_session_v2.py -q
/Users/ely/.cache/remote-runner-terminal-v2-venv/bin/python -m pytest -q
./scripts/harness-check.sh
git diff --check
```
