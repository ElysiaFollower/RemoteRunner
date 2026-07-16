<!--
职责：定义 Terminal Observation V3 的单一实现合同。
边界：只收紧 terminal send/read/tail 的观测接口与 skill，不引入完成检测、prompt 解析或多 Agent 调度。
-->

# Remote Runner Terminal Observation V3

## 目标

让 Remote Runner terminal 接口像普通终端一样清楚：`send` 快速确认原样输入，`read`
按显式 cursor 无损读取，`tail` 按调用者明确指定的窗口查看最新终端流；返回值只保留操作结果、
cursor 和输入/输出时间等必要元信息，不重复完整 session 对象。完整 transcript 继续 append-only
持久化，但调用者不必顺序消费全部历史。

## 非目标

- 不自动跳过、摘要、压缩或解释 terminal 输出。
- 不检测 prompt、命令完成、退出码或前台进程 busy；不注入 marker、wrapper、hook 或 shell
  integration。
- 不为一个 session 设计多 Agent 调度、租约或长期写锁；一个 session 默认只有一个当前操作者，
  并行工作使用多个独立 session。
- 不修改 stable worktree、editable install、global live skill、真实 Remote Runner state 或现有
  tmux session。

## 当前仓库事实

- 入口规则：`AGENTS.md`；初始化契约：`harness/bootstrap-contract.md`。
- 当前功能项：`F-029`。
- 隔离 worktree：`/Users/ely/workspace/research/agent/RemoteRunner-terminal-v3`；分支：
  `codex/rr-terminal-observation-v3`。
- 当前 `send`/`read` 返回完整 `_public_session`，真实 transcript 被大量重复 metadata 包围；
  `read` 即使指定 `since` 也会把本地 transcript 全量读入内存；`max_chars` 截断时返回的 cursor
  指向完整末尾，存在跳过未返回内容的风险。
- 当前协作模式：高自治；开发原则：公共 CLI/library maintenance；canonical skill 只在分支内
  更新，不发布到 global skill。

## 允许改动

- 收紧 `session send/read` 的 Python/CLI 返回合同，增加显式 `session tail` 和可选 plain 输出。
- 将 transcript cursor 明确定义为 UTF-8 byte offset，按范围读取本地 append-only 文件，避免
  长 transcript 每次全量加载；为旧 session state 提供可解释迁移。
- 增加 `last_input_at`、`last_output_at`、`output_idle_ms`、`start_cursor`、`next_cursor`、
  `last_cursor` 等直接观测元信息。
- 更新 README、requirements、API、getting started、platform support、canonical skill、feature
  list、progress 和 handoff。
- 增加 fake backend、真实本地 bash/zsh tmux、长输出、Unicode cursor、CLI JSON/plain 和 skill
  契约测试。

## 禁止改动

- 不改 `main`，不运行 `pip install -e`，不复制 canonical skill 到 `/Users/ely/.agents/skills`。
- 不连接真实机器，不读取或写入真实 session transcript/state，不创建业务 session。
- 不根据 idle 时间、tmux process name、prompt 文本或输出内容推断 busy/completed。
- 不让 tail 隐式替代 read；跳过历史必须来自调用者显式调用 tail。
- 不在截断读取中把 next cursor 跳到未返回内容之后。

## 公共契约

- `send` 立即返回 compact acknowledgement；不等待命令完成。
- `read --since N` 从 N 开始无损读取；若显式限制大小，`next_cursor` 只前进到实际返回内容末尾，
  `last_cursor` 表示当前完整 transcript 末尾。
- `tail --bytes N` 是显式有损观察：返回最新至多 N bytes，并用 start/last cursor 明确省略范围；
  不删除或改写 transcript。
- JSON 中 terminal 内容使用单一明确字段；plain 模式只写 terminal 内容，不混入 metadata。
- 时间字段是 RR 直接记录或观察到的事实；`output_idle_ms` 只由 `last_output_at` 计算，不表示
  命令完成或 terminal idle。
- canonical skill 要求新 shell 命令发送前先看 tail 并确认 prompt；交互程序响应不属于新 shell
  命令；一个 session 同时只给一个 Agent 使用，并行任务创建独立 session。

## 验收标准

- compact send/read/tail JSON 不含 log path、machine/cwd、command counters 等重复 session metadata。
- 真实本地 tmux 的 prompt、输入回显和输出都能通过 tail/read 看到；plain 模式不输出 JSON。
- 生成多 MiB transcript 后，tail 和 bounded read 的读取量与返回窗口成正比，不全量加载文件。
- ASCII/Unicode 输出的 byte cursor 单调且不会重复、丢失或从 UTF-8 中间返回乱码。
- bounded read、tail、空输出、destroyed/lost session、并发 reader 和旧 state migration 有回归。
- 全部默认测试、harness、格式和非格式 lint gate 通过；无测试 tmux/state/process 残留。

## 验证命令

```sh
python3 -m pytest tests/test_terminal_observation_v3.py -q
python3 -m pytest tests/test_terminal_session_v2.py tests/test_terminal_debt_audit.py -q
python3 -m pytest tests/test_remote_runner_mvp.py -q
python3 -m pytest tests/test_remote_runner_launch_suite.py -q
python3 -m pytest -q
./scripts/harness-check.sh
git diff --check
```

## 完成定义

- 公共契约、实现、测试、文档、canonical skill 和 harness 事实一致。
- F-029 记录验证 evidence 后转为 passing，任务合同及检查文件归档。
- stable runtime/global skill 保持不变；隔离分支提交完整、worktree clean，可由用户审阅后合并。
- handoff 明确兼容性变化、验证证据、未运行的真实 SSH 边界和同步步骤。

## 阻塞条件

- 正确 tail/range 读取必须全量载入 transcript，且没有可维护的 byte cursor 实现路径。
- 目标行为只能通过 prompt 检测、命令 wrapper 或 shell integration 获得。
- 继续开发必须触碰 stable runtime、global skill、真实 state 或现有业务 tmux session。
