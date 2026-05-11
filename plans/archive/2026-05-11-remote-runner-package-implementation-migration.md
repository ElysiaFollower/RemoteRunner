# Remote Runner 包实现迁移第一切片

## 目标

让 `remote_runner` 从 facade 变成 Remote Runner 真实实现包：`remote_runner.remote_backend`、`remote_machine`、`remote_session`、`remote_file`、`remote_run`、`remote_state`、`cli` 承载实现代码；`seed_runner.remote_*` 退为 legacy compatibility wrappers，继续 re-export 目标实现，保证旧导入不破坏。

## 非目标

- 不改 CLI 用户界面、JSON schema、状态目录、真实机器配置格式或命令语义。
- 不删除 legacy `seed-runner` 原型，也不删除 `seed_runner.remote_*` 兼容导入。
- 不运行真实机器 opt-in 测试，除非用户明确要求；默认验证不触碰外部机器。
- 不在本轮实现 profile、验收 DSL、报告层或凭据系统升级。

## 当前仓库事实

- 入口规则：`AGENTS.md`
- 初始化契约：`harness/bootstrap-contract.md`
- 当前功能项：`F-014`
- 相关文件/模块：`remote_runner/`、`seed_runner/remote_*.py`、`tests/test_remote_runner_mvp.py`、`tests/test_remote_runner_real_integration.py`、`pyproject.toml`、`README.md`、`docs/overview.md`
- 已知约束：目标项目是一套基于 SSH 的本地 CLI；`remote-runner` 是目标 CLI/包名，`seed-runner` 是 legacy 原型；不得把真实机器细节、密码、host 或私人路径写入仓库。

## 允许改动

- 将 Remote Runner 实现从 `seed_runner.remote_*` 迁移到 `remote_runner.*`。
- 将 `seed_runner.remote_*` 改为薄兼容 wrapper。
- 更新测试 import，验证目标包名是真实实现来源，legacy import 仍可用。
- 同步 README、overview、feature list、progress、handoff 和归档计划。

## 禁止改动

- 禁止修改真实用户机器状态或运行默认会写远程文件的命令。
- 禁止把 `seed_runner` legacy 原型整体重命名或删除。
- 禁止改变现有 `remote-runner` CLI JSON 输出合同。
- 禁止把真实 SSH 凭据或本机路径写入文档、测试或 handoff。

## 验收标准

- `remote_runner.*` 模块直接包含目标实现，不再只是从 `seed_runner.remote_*` re-export。
- `seed_runner.remote_*` 仍可导入，并 re-export `remote_runner.*` 的同一批公开对象。
- `remote-runner` console script 和 `python3 -m remote_runner.cli --help` 正常。
- Remote Runner MVP 聚焦测试和完整测试通过；默认真实机器测试仍 skip。
- docs/harness 明确当前事实：目标实现已迁移到 `remote_runner`，legacy wrapper 仍保留。

## 验证命令

```sh
python3 -m remote_runner.cli --help
python3 -m pytest tests/test_remote_runner_mvp.py -q
python3 -m pytest tests/test_remote_runner_real_integration.py -q
python3 -m pytest -q
./scripts/harness-check.sh
git diff --check
```

## Evidence 记录要求

验证通过后，将命令、结果、关键输出摘要写入 `harness/feature_list.json` 的 `F-014.evidence`，并在 `harness/progress.md` 和 `harness/session-handoff.md` 记录迁移边界、未验证项和下一步。

## 完成定义

- 请求行为已实现。
- 非目标没有被触碰。
- 上方验证命令已运行；未运行的命令必须说明原因。
- `harness/feature_list.json` 状态和 evidence 已更新。
- 职责、接口、setup 或边界改变时，docs、测试或 harness 文件已更新。
- `harness/session-handoff.md` 写明当前状态、风险和下一步。
- 任务完成后将本计划归档到 `plans/archive/`。

## 阻塞条件

- 若发现 `seed_runner` legacy CLI 与 `remote_runner` 目标实现无法在不破坏兼容的前提下分离，应暂停并让用户决策兼容边界。
- 若迁移要求改变状态 schema、CLI 输出或真实机器配置格式，应暂停并让用户确认。

## 下一步最佳动作

1. 先机械迁移 `remote_runner` 实现与内部 import。
2. 再把 `seed_runner.remote_*` 改为兼容 wrapper 并更新测试。

## 完成记录

- `remote_runner.cli`、`remote_runner.remote_backend`、`remote_machine`、`remote_session`、`remote_file`、`remote_run`、`remote_state` 已承载真实实现。
- `seed_runner.remote_*` 已改为 legacy compatibility wrappers。
- `tests/test_remote_runner_mvp.py` 默认从 `remote_runner.*` 导入，并验证 legacy wrappers 指向同一目标实现对象。
- `tests/test_remote_runner_real_integration.py` 默认使用 `python3 -m remote_runner.cli`，仍保持 opt-in skip 行为。
- 已同步 README、overview、feature list、progress 和 handoff。
