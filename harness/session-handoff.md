<!-- 当前可恢复状态；历史过程见 harness/progress.md。 -->

# 会话交接

## 仓库状态

- 开发 worktree：`/Users/ely/workspace/research/agent/RemoteRunner-terminal-v2`
- 分支：`codex/rr-terminal-session-v2`
- stable worktree、editable install、真实 Remote Runner state 和既有 tmux session 均未修改。
- `F-027`、`F-028` passing；任务合同分别归档于
  `plans/archive/2026-07-15-terminal-session-v2.md` 和
  `plans/archive/2026-07-15-terminal-debt-audit.md`。
- canonical `SKILL.md` 已在当前分支更新；global live skill 未热更新。

## 当前设计事实

- tmux-backed session 是人类式持久 terminal：`send` 原样发送一行，`read` 读取 append-only
  transcript/cursor，`interrupt` 发送 `Ctrl-C`，人工 attach 与 agent 看到同一流。
- live pane 不承载 structured exec、marker、eval、exit-code wrapper 或 file-transfer protocol。
- `ssh-tmux session exec/background` 是与 session 关联的独立 direct-SSH batch，不进入 pane，
  不读取或改变 terminal 的 cwd/env/alias/function；`run once` 直接调用同一 batch transport，
  不委托给 `session exec`。
- `openssh-pty` 只支持 `create/attach/send/read/interrupt/destroy`；因没有独立文件 transport，
  `file put/get/list` 明确拒绝。不会为了兼容借用 PTY 传 base64 或隐藏脚本。
- `windows-agent` 保留显式 JSON request/result PowerShell 协议；wait 轮询已修复。其 piped
  PowerShell 无可靠 console-control channel，所以 `session interrupt` 明确拒绝。
- remote tmux transcript 通过 byte cursor 只读新增 SFTP bytes，保存跨块 UTF-8 tail；manager
  用 cursor compare 避免并发 reader 重复 append。
- `command_backend=tmux/local_tmux` 的 inspect/stop 仅用于升级前 persisted legacy record 的
  只读恢复或显式停止；新命令只产生 `direct_ssh` / `direct_ssh_background`。

## 验证证据

- deterministic debt regressions：10 passed。覆盖 exec/background/run once 零 pane input、
  PTY file get 零 pane input、remote delta bytes/UTF-8、manager cursor 持久化、并发读去重、
  Windows wait/interrupt/destroy 边界。
- remote delta 计量：首读 12002 bytes；追加后只读 7 bytes；重复空读 0 bytes；并发双读
  回归连续运行 20 次无重复 append。
- 真实本地 tmux：`tests/test_terminal_session_v2.py` 16 passed，bash/zsh 各执行 20 轮
  `false` 后继续输出；每轮输入原文可见、cursor 单调，最终 shell 存活，无 marker/eval。
- MVP：54 passed。Launch：2 passed, 1 skipped。
- 完整验证：103 passed, 4 skipped；默认 skips 只包含显式 opt-in 的真实机器/VM 测试。
- Black check、flake8 非格式规则、`git diff --check`、JSON parse 和 harness-check 通过；
  harness-check 0 warnings。测试结束无 `rr_local_sess_*` 或开发 shim 进程遗留。
- mypy 不是当前可用 gate：配置仍声明 Python 3.8，而安装的 mypy 已不支持 3.8；同时仓库有
  既存 Windows 分支类型错误和缺失 Paramiko stubs。本轮暴露的新增类型推断错误已修复，且
  mypy 发现的 Windows destroy 缺失返回也已补回归。

## 仍未完成

- stable editable runtime 和 global skill 尚未切换；这是为了不影响运行中任务，必须留到合并
  后的安全窗口执行。
- 未运行真实 SSH server smoke；它只覆盖认证、网络、远端 tmux/SFTP 环境边界，不阻塞当前
  terminal/batch 协议正确性。
- mypy 尚不能作为仓库 gate；需要单独任务升级 Python typing baseline、补 Paramiko stubs 并
  清理既存跨平台类型错误，不能在本次 terminal 重构里用大范围无关修改掩盖。

## 安全与隐私边界

- 未连接真实机器，未读取或写入真实 session transcript/state，未记录 host、密码、token、
  私钥内容或真实远程目录。
- 未运行真实 SSH server smoke。核心 terminal transport 已由真实本地 tmux 覆盖；真实 smoke
  只验证认证、网络、远端 tmux/SFTP 的环境边界，不是隐藏协议的替代方案。
- 合并前保持 stable editable runtime 不变。只有确认依赖旧版本的运行中任务都结束后，才可
  切换 editable install 并发布当前 canonical skill 到 global skill。

## 下一步最佳动作

1. 审阅当前分支 diff 和提交。
2. 合并后，在安全窗口切换 editable install/global skill。
3. 可选对一台预配置 SSH machine 做只写测试目录的
   `create -> send -> read -> interrupt -> destroy` 和 direct batch smoke。

## 常用命令

```bash
cd /Users/ely/workspace/research/agent/RemoteRunner-terminal-v2
/Users/ely/.cache/remote-runner-terminal-v2-venv/bin/python -m pytest tests/test_terminal_debt_audit.py -q
/Users/ely/.cache/remote-runner-terminal-v2-venv/bin/python -m pytest tests/test_terminal_session_v2.py -q
/Users/ely/.cache/remote-runner-terminal-v2-venv/bin/python -m pytest -q
./scripts/harness-check.sh
git diff --check
```
