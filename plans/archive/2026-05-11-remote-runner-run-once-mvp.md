<!--
职责：为实现 agent 定义一个 active task 合同，让范围、验收、验证和交接可执行。
边界：不要在这里累积长期架构事实、原始日志或无关 follow-up 想法。
-->

# Remote Runner Run Once 闭环 MVP

## 目标

新增通用 `remote-runner run once`，把一次远程工作闭环固化为可恢复 run manifest：创建会话、可选上传输入、执行命令、可选拉回产物、记录命令/传输/产物证据、默认销毁会话并保留日志。

## 非目标

- 不引入 research、SEED、operations、training 或 benchmark 的专用 profile。
- 不做任务队列、并发调度、重试策略、报告生成或验收 DSL。
- 不改变已有 machine/session/file CLI 行为。
- 不在真实 Windows 机器的 `SSHRunner` 目录外写入、删除或移动文件。

## 当前仓库事实

- 入口规则：`AGENTS.md`
- 初始化契约：`harness/bootstrap-contract.md`
- 当前功能项：F-011
- 相关文件/模块：`seed_runner/remote_run.py`、`seed_runner/remote_state.py`、`seed_runner/remote_cli.py`、`tests/test_remote_runner_mvp.py`、`docs/reference/REMOTE_RUNNER_API.md`、`REQUIREMENTS.md`
- 已知约束：基础 machine/session/file 能力已通过真实 Windows `SSHRunner` 验证；本轮 run 只编排这些能力，不新增 backend。

## 允许改动

- 新增 run state 目录和 run manifest 读写 helper。
- 新增 `RemoteRunManager` 和 `remote-runner run once/list/show`。
- 增加单元测试、CLI 文档、需求文档、harness 状态和真实验证 evidence。

## 禁止改动

- 禁止把真实 host、密码、密钥或额外机器细节写入仓库文件。
- 禁止在真实 Windows 机器的 `SSHRunner` 目录外写入或删除文件。
- 禁止把 profile/use case 绑定到底层 run API。

## 验收标准

- `run once` 可接收 `--input LOCAL=REMOTE` 和 `--artifact REMOTE=LOCAL`，并按顺序完成上传、执行、拉回。
- run manifest 记录 run_id、machine_id、session_id、cwd、command、inputs、artifacts、command_result、status、started_at、ended_at、destroy_session_result。
- 命令非零退出码不丢日志；run 状态为 failed，session 默认销毁。
- `run list/show` 可恢复查询 run manifest。
- 真实 Windows `SSHRunner` 验证中，run once 上传输入、执行命令生成产物、拉回产物并本地比对成功；远程探针文件最终清理。

## 验证命令

```sh
./scripts/harness-check.sh
python3 -m pytest tests/test_remote_runner_mvp.py -q
python3 -m pytest -q
python3 -m black --check seed_runner/remote_run.py seed_runner/remote_state.py seed_runner/remote_cli.py tests/test_remote_runner_mvp.py
git diff --check
```

真实验证：

```sh
python3 -m seed_runner.remote_cli run once --machine 'windows-wsl' --cwd /mnt/c/Users/example/Desktop/SSHRunner --input <local_input>=/mnt/c/Users/example/Desktop/SSHRunner/<input_name> --cmd '<command>' --artifact /mnt/c/Users/example/Desktop/SSHRunner/<output_name>=<local_output> --json
```

## Evidence 记录要求

验证通过后，将命令、结果、关键输出摘要或 artifact 路径写入 `harness/feature_list.json` 的 `evidence`。

## 完成定义

- 请求行为已实现。
- 非目标没有被触碰。
- 上方验证命令已运行；未运行的命令必须说明原因。
- `harness/feature_list.json` 状态和 evidence 已更新。
- 职责、接口、setup 或边界改变时，docs、注释、测试或 harness 文件已更新。
- `harness/session-handoff.md` 写明当前状态、风险和下一步。
- 清洁状态检查已说明。

## 阻塞条件

- run API 需要升级为 profile、队列或复杂验收 DSL 才能继续。
- 真实验证需要在 `SSHRunner` 目录外写入文件。

## 下一步最佳动作

1. 实现 `RemoteRunManager`、run state helper 和 CLI 编排。
