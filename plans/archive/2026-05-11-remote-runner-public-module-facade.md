<!--
职责：为实现 agent 定义一个 active task 合同，让范围、验收、验证和交接可执行。
边界：不要在这里累积长期架构事实、原始日志或无关 follow-up 想法。
-->

# Remote Runner 公共模块 Facade 迁移切片

## 目标

让目标包名 `remote_runner` 暴露公共模块 facade：`remote_runner.remote_machine`、`remote_runner.remote_session`、`remote_runner.remote_file`、`remote_runner.remote_run`、`remote_runner.remote_backend`、`remote_runner.remote_state`。这些模块暂时 re-export 当前 `seed_runner.remote_*` 实现，使新代码可以开始使用目标 import path，同时 legacy 实现保持不动。

## 非目标

- 不搬移或删除 `seed_runner/remote_*.py`。
- 不重写内部 import。
- 不改变 CLI、state、真实机器行为或 legacy `seed-runner`。
- 不把 facade 变成复制实现。

## 当前仓库事实

- 入口规则：`AGENTS.md`
- 初始化契约：`harness/bootstrap-contract.md`
- 当前功能项：F-013
- 相关文件/模块：`remote_runner/`、`tests/test_remote_runner_mvp.py`、`README.md`、`docs/overview.md`、`harness/feature_list.json`
- 已知约束：F-012 已让 `remote-runner` console script 指向 `remote_runner.cli:main`；实现仍在 `seed_runner.remote_*`。

## 允许改动

- 新增 `remote_runner.remote_*` facade 模块。
- 更新测试，验证目标 import path 和旧实现对象一致。
- 更新文档/harness 状态。

## 禁止改动

- 禁止删除或重排 legacy `seed_runner` 模块。
- 禁止修改真实机器配置、凭据或本地 Remote Runner state。
- 禁止改变任何已有 CLI 参数或 JSON 响应形状。

## 验收标准

- `python3 -c "from remote_runner.remote_run import RemoteRunManager"` 可运行。
- `remote_runner.remote_*` facade 中的公共 manager/class 与 `seed_runner.remote_*` 当前实现保持同一对象。
- `python3 -m remote_runner.cli --help` 继续可用。
- 完整 pytest 继续通过。

## 验证命令

```sh
./scripts/harness-check.sh
python3 -m remote_runner.cli --help
python3 -m pytest tests/test_remote_runner_mvp.py -q
python3 -m pytest -q
python3 -m black --check remote_runner tests/test_remote_runner_mvp.py
git diff --check
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

- facade 不能满足 import 需求，必须立即完整搬移实现。

## 下一步最佳动作

1. 新增 `remote_runner.remote_*` re-export 模块并补测试。
