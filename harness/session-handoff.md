<!-- 当前可恢复状态；历史过程见 harness/progress.md。 -->

# 会话交接

## 仓库状态

- `F-029 Terminal Observation V3 精简观测接口` 已完成并标为 passing；任务合同归档于
  `plans/archive/2026-07-16-terminal-observation-v3.md`。
- 完整实现位于隔离 worktree
  `/Users/ely/workspace/research/agent/RemoteRunner-terminal-v3` 和分支
  `codex/rr-terminal-observation-v3`。它尚未合入 `main`。
- stable worktree `main` 仍是 `f65ee33` 且 clean；从独立目录导入 `remote_runner` 仍解析到
  `/Users/ely/workspace/research/agent/RemoteRunner/remote_runner/__init__.py`。本任务没有运行
  `pip install -e`，没有发布分支 `SKILL.md`，也没有读写真实 Remote Runner state。
- 唯一现存的非测试 tmux 是任务开始前已有且仍 attached 的业务 session；本任务未向其发送
  输入、未加锁、未销毁。测试创建的 `rr_local_*` 和 local SSH shim 均已清理。

## 已完成设计

- `session send` 只快速确认原样输入，不等待命令结束；`send/read/tail/interrupt` 不再重复
  machine、cwd、日志路径和 command counters 等完整 session 对象。
- transcript cursor 统一为 UTF-8 byte offset。`read --since N --max-bytes M` 的
  `next_cursor` 只前进到实际返回内容末尾，`last_cursor` 表示观测到的完整末尾，不会跨过
  未返回 bytes。`cursor`/`since` 保留为兼容 alias。
- `session tail --bytes N` 是调用者明确选择的有界尾部视图；`history_before` 和 range cursor
  明示被省略的历史。工具不自动跳过、摘要、压缩或解释输出。`--plain` 只写 transcript。
- `last_input_at`、`last_output_at`、`output_idle_ms` 是直接观测元信息，不代表 busy、命令完成、
  exit code 或 prompt 状态。旧 character cursor state 在下一次观测时迁移为 byte cursor。
- local append-only transcript 的 bounded read/tail 使用单文件句柄、单一 size snapshot 和范围
  读取；即使 pipe 正在追加，返回的 cursor 仍自洽。5.5 MiB 回归确认 tail 不走全文件 text read。
- `openssh-pty` 的 `pipe-pane` 文件由 manager 直接按范围读取；`ssh-tmux` 和
  `windows-agent` transcript 只同步远端尚未见过的 byte delta，并保留 UTF-8 跨块尾字节。
- canonical `SKILL.md` 把 session 定义为 single-operator terminal：发送每条新 shell command
  前先看 tail 并确认可见 prompt 已返回；密码、确认、REPL 等 interactive foreground input
  是例外；并行 Agent 使用独立 session。Skill 不要求工具推断 prompt/busy/completion。

## 验证证据

- `python3 -m pytest tests/test_terminal_observation_v3.py tests/test_terminal_session_v2.py tests/test_terminal_debt_audit.py -q`：49 passed。
- `python3 -m pytest -q`：126 passed, 4 skipped。4 个 skip 均为显式 opt-in 的真实机器/VM
  测试；默认套件没有环境性失败。
- 真实本地 tmux 覆盖 bash 和 zsh：输入原文、输出和 shell prompt 均进入 raw transcript；zsh
  prompt 后的 ANSI/bracketed-paste 控制序列也原样保留。另覆盖 Ctrl-C 恢复、长输出、20 轮失败
  命令和 shell state 连续性。
- 回归还覆盖 compact key contract、JSON/plain、5.5 MiB tail、UTF-8 split/cursor、CRLF、空和
  zero tail、负 limit、非法 cursor、lost/destroyed history、旧 state 迁移、remote/Windows delta
  计量及并发 reader 去重。
- legacy CLI subprocess 测试显式使用 pytest 临时 `.env.machines` 和分支 `PYTHONPATH`；完整
  验证在没有 ignored 配置 symlink 的 clean worktree 中通过。
- 变更 Python 文件通过 Black、flake8 非格式规则和 py_compile；`git diff --check`、skill
  `quick_validate.py`、`./scripts/harness-check.sh` 通过，harness 0 warnings。

## 仍未完成

- 未运行真实 SSH server 或 Windows host opt-in smoke，因此认证、网络、真实远端 tmux/SFTP 和
  PowerShell 环境仍需部署前在预配置测试目录验证。核心 terminal 行为已由真实本地 tmux 覆盖。
- 对 `ssh-tmux`/`windows-agent`，完整 transcript 的权威文件在远端。为了保留完整本地镜像，
  一次观察会同步从已提交 remote cursor 起尚未见过的 delta；它不会反复读取既有历史，但若两次
  观察之间产生超大输出，首次 tail 的网络读取量会大于 tail window。`openssh-pty` 的 transcript
  本来就在本地，不存在这项网络边界。
- V3 把非 ASCII cursor 从 character count 改成 byte offset。ASCII 数值不变；持有旧非 ASCII
  cursor 的调用者应先获取新的 tail/read 响应。完整 session 字段改由 `session show` 查询。

## 安全与隐私边界

- 本任务只操作隔离 worktree 中的代码、文档和 pytest 临时 state。没有读取密码、token、私钥、
  真实 transcript 或远端目录，也没有连接真实机器。
- 没有修改 stable worktree、editable install、global skill 或现有业务 tmux。测试 session 使用
  随机精确名称并在 fixture finally 中销毁；收尾检查未发现测试 pane 或 shim 残留。

## 下一步最佳动作

1. 在隔离 worktree 审阅分支 diff 和提交。
2. 用户确认后，从 stable worktree 将 `codex/rr-terminal-observation-v3` 合入 `main`；不要在仍有
   依赖旧接口的 Agent 工作时切换。
3. editable install 会随主 worktree 代码更新；随后再把仓库 canonical `SKILL.md` 发布到 global
   `remote-runner` skill。
4. 在安全的预配置机器/目录运行 AGENTS.md 中的 Remote Runner 真实测试，再允许业务 Agent 使用
   新合同。

## 常用命令

```bash
cd /Users/ely/workspace/research/agent/RemoteRunner-terminal-v3
python3 -m pytest tests/test_terminal_observation_v3.py tests/test_terminal_session_v2.py tests/test_terminal_debt_audit.py -q
python3 -m pytest -q
./scripts/harness-check.sh
git diff --check
```
