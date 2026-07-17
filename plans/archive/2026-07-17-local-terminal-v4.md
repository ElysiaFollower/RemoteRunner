<!--
职责：定义 Remote Runner Local Terminal V4 的单一实现合同。
边界：本任务是不兼容重写；不迁移旧 state，不触碰 stable worktree、editable install、global skill 或业务 tmux。
-->

# Remote Runner Local Terminal V4（已完成）

## 目标

把 Remote Runner 收敛成一个透明的本地持久终端工具：每个 Session 由本机 tmux 承载，
`pipe-pane` 从 shell 启动前持续写入 append-only raw transcript。Agent 与人类通过同一个
终端输入、观察和协作；SSH、`su`、远端 tmux、Slurm、`nohup` 等都是使用者在 shell 中明确
执行的普通操作，不是 RR 的隐藏 backend。

## 核心分层

1. Session 层：创建本地 tmux shell，可选调用 instance bootstrap 获得目标 shell。
2. Terminal 层：`send`、`key`、`read`、`tail`、`attach`、`destroy`。
3. State 层：持久化身份、生命周期、tmux/transcript 定位和直接可观测时间；不推断 busy、
   prompt、命令完成或远端存活。

## 公共合同

- 运行平台仅为装有 tmux 的 macOS/Linux；Windows 可以是 shell 中显式 SSH 的目标，但不是
  RR 运行平台，也没有专用 backend。
- `session_name` 是 active/lost Session 的人类可读唯一引用；`session_id` 是永不复用的内部
  UUID 和历史索引。destroy 后名称可复用，旧 transcript 继续由 ID 访问。
- tmux 名称可读且含短 ID；`session show` 返回 tmux 名称和 transcript 绝对路径，人类可以
  直接 attach，Agent 可以直接检查原始文件。
- `send` 发送一行文本和 Enter，只返回 `session_name` 与发送前的 `read_from_cursor`；不返回
  或持久化原始输入。
- `key` 发送一个明确的终端按键并返回同样的 cursor anchor；不保留 `interrupt` 别名。
- `read`/`tail` 默认只写原始 terminal bytes；显式 `--json` 才返回文本和最小 cursor 信息。
- `show` 独立返回 state：`last_rr_input_at`、`time_since_last_rr_input_ms`、
  `last_output_at`、`time_since_last_output_ms`、`transcript_end_cursor` 等直接事实。
- `destroy` 只终止 tmux、标记历史并释放名称；`purge` 才删除已 destroyed Session 的状态和
  transcript，并要求精确 ID 确认。
- active 记录对应 tmux 缺失时收敛为 `lost`。`send/key/attach` 返回 `session_lost`；
  `show` 正常报告 lost；`read/tail` 仍可读取 transcript；destroy 对缺失 tmux 幂等。
- RR 自身失败使用非零退出码和 stderr `error.code/message`；shell 内命令失败只是 transcript。

## Instance/bootstrap 合同

- Instance 只是可选 bootstrap profile，不是 Session backend。
- 每个 instance 指向一份独立、可审查的 Python bootstrap 文件，导出
  `bootstrap(session)`；hook 只通过同一 `send/key/read/tail/show` Interface 操作终端。
- `session create --instance` 在本地 shell 就绪后同步且独占地运行 bootstrap。成功、失败或
  超时后才返回，之后绝无后台 bootstrap 输入。
- bootstrap 自己负责等待和识别 prompt；RR 不包含 SSH/login/prompt 状态机。
- bootstrap 失败或超时保留 Session、transcript 和诊断日志，供 Agent 接管。
- 密码可由 hook 从环境或本地配置读取后发送；RR 不保存、返回或在进程参数中暴露输入原文。

## 并发与 transcript 不变量

- Session 是单操作者终端；并行任务使用独立 Session。
- 普通 `send/key` 仅在单次写入期间持 per-session writer lock；bootstrap 整段持锁；读取不锁。
- transcript 是 tmux pane 发出的原始 append-only byte stream。普通 TTY echo 会记录输入，
  no-echo 密码不会记录；RR 不清洗 ANSI、回车、退格或全屏程序输出。
- recorder 必须先于真实 shell 启动，避免漏掉初始 prompt；不提供自动轮转、摘要或屏幕快照。
- cursor 是 transcript byte offset；读取不维护隐藏的 per-reader cursor。

## 破坏性收敛

- 删除 machine、remote tmux、openssh-pty、windows-agent、structured exec/background、file、
  run、artifact 和 legacy seed-runner 兼容路径。
- 新 state 带显式 schema version；旧目录不迁移、不静默读取，检测到旧 schema 时明确失败。
- 不保留旧字段、旧命令或兼容 alias。

## 验收标准

- 生产代码中不存在 Paramiko、Windows agent、remote backend 或结构化 batch/file 分支。
- 真实隔离 tmux 覆盖：初始输出零丢失、shell state 连续、普通输入与人工输入可见、密码不回显、
  named key/Ctrl-C、human attach 目标、lost/destroy/reuse/purge 和多 MiB range/tail。
- 契约测试覆盖 CLI raw/JSON、stdout/stderr/exit code、无原始输入泄漏、state 字段精确集合、
  instance bootstrap success/failure/timeout/exclusivity、旧 schema 拒绝和无测试 tmux 残留。
- README、overview、lighthouse、requirements、CLI reference、platform support、SKILL、feature、
  progress、handoff 与实现一致。

## 验证命令

```sh
python3 -m pytest tests/test_state.py tests/test_session.py tests/test_bootstrap.py tests/test_cli.py -q
python3 -m pytest tests/test_tmux_integration.py -q
python3 -m pytest -q
python3 -m black --check remote_runner tests
python3 -m flake8 remote_runner tests --ignore=E203,W503,E501
python3 -m mypy remote_runner
./scripts/harness-check.sh
git diff --check
```

## 安全与隔离

- 只修改 `/Users/ely/workspace/research/agent/RemoteRunner-terminal-v3`。
- 测试使用独立 tmux server socket 和 pytest 临时 state，finally 必须 kill-server。
- 不运行 `pip install -e`，不发布 global skill，不读真实 RR state，不操作默认 tmux server。

## 完成定义

- F-030 有完整验证 evidence 并转为 passing；任务合同归档。
- 分支代码、文档、测试和 harness 无冲突；worktree 只有已解释的任务改动和删除项，无临时
  state、cache、日志或测试进程，可供用户审阅后做破坏性切换。
- handoff 明确旧工具未受影响、新 state 的 cutover 前置动作和所有未验证边界。
