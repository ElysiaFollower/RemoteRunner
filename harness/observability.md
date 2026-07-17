<!-- 职责：定义运行时信号和验证证据。 -->

# 可观测性

## 运行时事实

- `session show`：生命周期、tmux 名/pane、last RR input、last transcript output、elapsed time、
  transcript path/end cursor。
- `session tail`：最新 raw terminal bytes。
- `session read --json`：明确 byte range 和下一 cursor。
- `transcript_path`：完整 raw append-only 事实源。
- `bootstrap_log_path`：bootstrap 进程自身诊断，不替代 terminal transcript。

这些信号不表示 busy、prompt、命令完成、exit code 或远端进程存活。

## RR 错误

RR 自身错误写 stderr JSON，包含稳定 `error.code/message` 和已知恢复上下文。内部异常尽量
给出私有 `diagnostic_path`。shell 命令失败只存在于 transcript。

## 验证证据

- feature passing 必须记录日期、命令和结果。
- tmux 集成测试必须说明使用独立 socket，并检查无残留。
- bootstrap timeout 必须证明子进程已经结束，返回后不再输入。
- 凭据、真实 host、私钥和业务 transcript 不进入 evidence/handoff。
