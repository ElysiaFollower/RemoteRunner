<!--
职责：关闭 Terminal Session V2 审计发现的同类故障和本轮新引入的扩展性债务。
边界：不把“兼容”当作保留隐藏 terminal protocol 的理由，也不在本任务重写 Windows agent。
-->

# Terminal Session V2 债务清零审计

## 目标

让所有 tmux-backed live session 都严格遵守 terminal 契约：公开操作只能原样单行输入、
append-only 增量读取和 Ctrl-C，不再注入隐藏 wrapper/marker/eval；结构化 batch 走 `run once`
的非 terminal 执行通道。删除无法满足该边界的 PTY file-get 兼容协议，并证明 remote
transcript 增量读取不会随历史长度产生 O(n²) 传输。

## 非目标

- 不重写 `windows-agent`；它已有独立 request/result protocol，不是 tmux pane 内的隐藏协议。
- 不新增半成品 `job` 顶级资源；当前结构化闭环统一收敛到已有 `run once`。
- 不连接或修改 stable runtime、真实 machine state、既有 tmux session。

## 当前仓库事实

- 入口规则：`AGENTS.md`
- 初始化契约：`harness/bootstrap-contract.md`
- 当前功能项：`F-028`
- 相关文件/模块：`remote_runner/remote_backend.py`、`remote_runner/remote_session.py`、
  `remote_runner/remote_run.py`、`remote_runner/remote_file.py`、`tests/test_terminal_session_v2.py`、
  `tests/test_remote_runner_mvp.py`、API/skill/harness。
- 已知约束：F-027 已移除 openssh-pty exec，但 ssh-tmux exec 仍 source wrapper；
  openssh-pty file get 仍抢占 pipe-pane 并 eval；remote transcript 当前每次全量 SFTP 读取。

## 允许改动

- 将 ssh-tmux `session exec` 改为独立 direct-SSH batch transport，不写 live pane；
  openssh-pty 继续拒绝，windows-agent 保留其独立 request/result protocol。
- 让 `run once` 在 ssh-tmux 上使用独立 direct-SSH batch command，而不是 live terminal。
- 删除/明确拒绝 openssh-pty file get，并同步撤销不再真实的 feature/docs/skill 承诺。
- 为 remote append-only transcript 增加 byte cursor + UTF-8 tail 的真正增量 SFTP 读取。
- 增加故障注入、长历史、重复读取、shell liveness 和无隐藏输入回归。

## 禁止改动

- 不通过更复杂的隐藏 marker、alternate screen、trap 或 shell option 操作“修好” live PTY 协议。
- 不为了保留错误兼容而继续暴露无法可靠满足的结构化 exit-code 语义。
- 不热更新全局安装或 global skill。

## 验收标准

- openssh-pty `session exec` 在 pane input 前失败；ssh-tmux `session exec` 通过独立 batch
  transport 返回结构化结果且不写 pane；代码中不存在 tmux session command wrapper/eval 路径。
- openssh-pty `file get` 明确拒绝，不抢占 recorder、不写 pane；文档和 feature list 不再宣称支持。
- ssh-tmux `run once` 仍能返回 stdout/stderr/exit code，但 command 通过独立 batch transport，
  不进入 session pane。
- remote transcript 第二次读取只获取 cursor 后新增字节；重复空读为 0 bytes；UTF-8 跨块不损坏。
- 真实本地 tmux 压力循环后 shell 存活、输入可见、cursor 单调，且无测试 session 遗留。

## 关键锚点

配套检查文件：`plans/archive/2026-07-15-terminal-debt-audit.check.json`

- No hidden tmux protocol：live tmux session 不再承载 eval/marker/file-transfer RPC。
- Batch separation：`run once` 的 structured result 不依赖 `session exec`。
- Incremental remote transcript：SFTP 读取量与新增输出成正比，并正确处理 UTF-8 边界。
- Failure stress：故障注入和多轮真实本地 tmux 测试证明 shell/recorder 可恢复。

## 验证命令

```sh
/Users/ely/.cache/remote-runner-terminal-v2-venv/bin/python -m pytest tests/test_terminal_debt_audit.py -q
/Users/ely/.cache/remote-runner-terminal-v2-venv/bin/python -m pytest tests/test_terminal_session_v2.py tests/test_remote_runner_mvp.py -q
/Users/ely/.cache/remote-runner-terminal-v2-venv/bin/python -m pytest -q
./scripts/harness-check.sh
git diff --check
```

## Evidence 记录要求

验证通过后，将失败复现、修复后 shell liveness、实际读取字节量、测试轮数和未运行的真实
SSH 边界写入 `F-028.evidence`；不得写真实 host、凭据或 session transcript。

## 完成定义

- 请求行为已实现，原始故障类和审计发现均有 deterministic regression。
- 代码、API、skill、feature list 对当前能力的陈述一致，不保留“未来再迁”的半套公开抽象。
- 上方验证全部通过；debug instrumentation 和测试 tmux/state 已清理。
- active plan 归档，F-028 passing，handoff 写明证据和真正剩余的外部验证边界。

## 阻塞条件

- 若删除不安全兼容会导致用户数据不可恢复，必须停下并先设计显式迁移路径；当前仓库状态中
  file-get 仅为可重新执行的操作接口，不持有唯一数据。
- 若真实 SSH transport 出现本地无法模拟的认证/服务端差异，记录为外部 smoke 边界，不用
  隐藏 terminal protocol 兜底。

## 下一步最佳动作

1. 先写三个失败回归：PTY file-get 无 pane 写入、ssh-tmux exec 无 wrapper、remote cursor 只读 delta。
