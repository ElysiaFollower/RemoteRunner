<!--
职责：定义本项目 harness 的运行时信号、过程工件和验证证据采集方式。
边界：不要存放完整日志；日志应由工具产生，本文只说明采集与解释规则。
-->

# 可观测性

## 运行时信号

- CLI 启动/就绪：`python3 -m seed_runner.cli --help` 当前应成功加载；未来为 `remote-runner --help`。
- 机器配置健康：目标 MVP 使用 `remote-runner machine doctor <machine-id> --json`；当前原型通过配置测试和真实 VM opt-in 测试覆盖。
- 命令执行健康：目标 MVP 以 `session exec --json` 的 `exit_code`、stdout、stderr、duration、`log_file_local` 为主信号。
- 日志健康：每条命令必须有本地日志路径；完整输出不可只存在于聊天上下文。
- 凭据安全信号：stdout、stderr、日志、handoff、报告和 feature evidence 不得包含密码或私钥内容。

## 过程工件

- 任务合同：`plans/active/`
- 功能状态：`harness/feature_list.json`
- 验证证据：feature item 的 `evidence`
- 设计决策：`harness/decisions.md`
- 进度日志：`harness/progress.md`
- 会话交接：`harness/session-handoff.md`
- 质量评估：`harness/evaluator-rubric.md` 和 `harness/quality.md`

## 面向 agent 的错误消息规则

验证失败时，错误消息应说明：

- 哪个命令失败；
- 失败的可观察症状；
- 最可能的检查位置；
- 下一步修复建议。

不要只写 “test failed”。如果失败来自目标/原型差异，应明确标为迁移缺口，不要改文档掩盖。

## 证据记录规则

- `passing` feature evidence 必须包含日期、命令和结果。
- 真实 VM 验证必须注明机器配置前提和是否跳过。
- 文档整理类任务也要跑 `./scripts/harness-check.sh`，防止占位符、WIP 和 handoff 漂移。
