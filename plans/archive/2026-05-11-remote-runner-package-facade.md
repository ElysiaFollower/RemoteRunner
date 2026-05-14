<!--
职责：为实现 agent 定义一个 active task 合同，让范围、验收、验证和交接可执行。
边界：不要在这里累积长期架构事实、原始日志或无关 follow-up 想法。
-->

# Remote Runner 包名 Facade 迁移切片

## 目标

新增目标包名 `remote_runner` 的最小 facade，让 `remote-runner` console script 指向 `remote_runner.cli:main`，同时继续复用当前 `seed_runner.remote_cli` 实现。这样先稳定目标入口，不破坏 legacy `seed-runner` 原型和内部模块。

## 非目标

- 不批量移动 `seed_runner/remote_*.py` 文件。
- 不删除 legacy `seed-runner` CLI 或 `seed_runner` 包。
- 不重命名所有 import。
- 不改变 machine/session/file/run 行为。

## 当前仓库事实

- 入口规则：`AGENTS.md`
- 初始化契约：`harness/bootstrap-contract.md`
- 当前功能项：F-012
- 相关文件/模块：`pyproject.toml`、`remote_runner/cli.py`、`remote_runner/__init__.py`、`tests/test_remote_runner_mvp.py`、`README.md`、`harness/feature_list.json`
- 已知约束：当前 console script `remote-runner` 已存在，但入口仍指向 `seed_runner.remote_cli:main`；legacy `seed-runner` 必须继续可用。

## 允许改动

- 新增 `remote_runner` facade package。
- 更新 `pyproject.toml` 的 `remote-runner` console script。
- 增加轻量测试验证 facade 入口。
- 更新 docs/harness 状态。

## 禁止改动

- 禁止删除或重排 legacy `seed_runner` 模块。
- 禁止破坏现有 `seed-runner` console script。
- 禁止把 facade 写成复制实现；本轮应委托现有实现。

## 验收标准

- `python3 -m remote_runner.cli --help` 可运行。
- `remote-runner` console script 指向 `remote_runner.cli:main`。
- legacy `seed-runner` 原型测试继续通过。
- 本地完整 pytest 继续通过。

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

- 目标包名 facade 需要变成完整包迁移才能继续。

## 下一步最佳动作

1. 新增 `remote_runner` facade package 并切换 console script。
