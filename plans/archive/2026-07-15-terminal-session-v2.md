<!--
职责：定义“session 就是人类终端”的单一重构任务合同。
边界：批处理/job、完整跨平台 shell integration 和真实服务器认证不在本任务内。
-->

# Remote Runner Terminal Session V2

## 目标

让 tmux-backed Remote Runner session 具备与人类终端一致的核心语义：`session send`
原样输入用户文本，`session read` 从单调追加的 terminal transcript 按 cursor 读取新增输出，
`session interrupt` 等价于按下 `Ctrl-C`；人类 attach 时看到的命令与 Agent 发送的命令一致。

## 非目标

- 本任务不在共享人工 PTY 上继续追求可靠拆分 stdout/stderr 或通过隐藏 `eval` wrapper
  捕获退出码。
- 不在本任务内完成 job/batch API、上传-执行-下载编排或 Windows shell integration 重构。
- 不要求真实 Linux 服务器；SSH transport 的真实 smoke 作为可选末级验证，不阻塞本地
  tmux 核心语义完成。
- 不迁移、销毁或改写 stable runtime 使用的 `~/.remote-runner` 状态和现有 tmux session。

## 当前仓库事实

- 入口规则：`AGENTS.md`
- 初始化契约：`harness/bootstrap-contract.md`
- 当前功能项：`F-027`
- 相关文件/模块：`remote_runner/remote_backend.py`、`remote_runner/remote_session.py`、
  `remote_runner/cli.py`、`remote_runner/remote_state.py`、`tests/test_remote_runner_mvp.py`、
  `tests/test_terminal_session_v2.py`、`SKILL.md` 和目标 API 文档。
- 已知约束：stable 的 base/seedrunner 安装仍 editable 指向旧 worktree；本分支位于独立
  worktree，开发环境和 state 必须隔离。当前 `openssh-pty session exec` 会向人工 shell
  注入 marker + `eval` wrapper，snapshot transcript 合并已在真实使用中产生重复。
- 当前协作模式：高自治；开发原则：library/CLI maintenance。

## 允许改动

- 为 tmux backend 增加 append-only transcript transport，并保留 legacy session 的兼容读取。
- 让 `session send` 保证原样输入，增加 `session interrupt` 和输入串行保护。
- 对 `openssh-pty session exec` 明确拒绝隐藏 wrapper，错误信息引导使用 send/read；保留
  其他 backend 的现有结构化 exec 作为兼容路径，后续迁移到 job 层。
- 增加真实本地 tmux bash/zsh 测试、fake-backed 契约测试、CLI 帮助/错误测试。
- 同步 README、requirements、API、platform support、getting started、skill 和 harness。

## 禁止改动

- 不修改 `/Users/ely/workspace/research/agent/RemoteRunner` stable worktree、其 Python 安装、
  `~/.remote-runner` 或现有 `rr_*` tmux session。
- 不让开发测试连接真实机器、读取真实 machine state 或复用真实 session id。
- 不用 shell command wrapper、base64 payload 或 marker 注入来伪装原样 terminal 输入。
- 不把 tmux 写成长期产品边界；append-only recorder 是当前 backend 实现。

## 验收标准

- 本地真实 tmux 中，bash 和 zsh 都能看到 Agent 原样发送的一行命令及其输出；连续
  `cd`/`export` 保持同一 shell 状态。
- `session read --since <cursor>` 多次读取只返回新增内容，不重复历史；长输出和重复读取
  不依赖 `capture-pane` overlap 猜测。
- `session interrupt` 能终止前台长命令，shell 随后仍可继续接收普通输入。
- `openssh-pty session exec` 在发送任何 pane 输入前失败，并给出 send/read 迁移提示。
- `session send` 在 legacy structured command busy 时拒绝交错普通输入。
- 现有非 openssh backend、file/run、legacy seed-runner 的默认测试不回归。

## 关键锚点

配套检查文件：`plans/active/2026-07-15-terminal-session-v2.check.json`

- Append-only transcript：tmux output 不再依靠 screen snapshot 合并来形成历史。
- Raw input + interrupt：公开 session 操作对应普通终端输入与 `Ctrl-C`。
- Real local tmux evidence：真实 bash/zsh pane 验证可见输入、cursor、状态连续和中断恢复。
- Skill/API migration：Agent 默认走 send/read，结构化 batch 不再冒充人工 terminal。

## 验证命令

```sh
REMOTE_RUNNER_STATE_DIR=/tmp/remote-runner-v2-test python3 -m pytest tests/test_terminal_session_v2.py -q
python3 -m pytest tests/test_remote_runner_mvp.py -q
python3 -m pytest tests/test_remote_runner_launch_suite.py -q
python3 -m pytest -q
./scripts/harness-check.sh
git diff --check
```

## Evidence 记录要求

验证通过后，将命令、结果、本地 tmux shell 类型、关键输出摘要和未运行的真实 SSH 验证
限制写入 `harness/feature_list.json` 的 `F-027.evidence`。不得记录真实机器 host、密码、
token、私钥、现有 session transcript 或私人远程路径。

## 完成定义

- 请求行为已实现。
- 非目标没有被触碰。
- 关键锚点已满足；若锚点因方案变化不再合理，已先更新任务合同并记录原因。
- 上方验证命令已运行；未运行的命令已说明原因。
- `harness/feature_list.json` 状态和 evidence 已更新。
- 公共接口、兼容边界、skill、docs、测试和 handoff 已同步。
- 没有测试 tmux session、开发 state、临时日志或下载缓存遗留。
- `harness/session-handoff.md` 能让下一位 agent 在三分钟内恢复。

## 阻塞条件

- 本机 tmux 无法提供持续 output recorder，且只能退回不可靠的 snapshot overlap 合并。
- 为获得 completion/exit code 必须重新向人工 shell 注入隐藏 wrapper。
- 需要触碰 stable worktree、stable state 或现有真实 session 才能继续。

## 下一步最佳动作

任务已完成。结果：Terminal V2 聚焦 14 passed（真实本地 tmux bash/zsh 13 + remote
recorder 构造单测 1）；MVP 56 passed；全仓 93 passed, 4 skipped；harness-check 和
git diff --check 通过。真实 SSH smoke 未运行，按本
任务合同不阻塞。后续独立任务应把 structured exec 和 PTY file-get protocol 迁移到
job/file transport。
