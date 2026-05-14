# Remote Runner shared utils 迁移切片

## 目标

让 `remote_runner` 实现不再依赖 `seed_runner.utils`：把共享 helper 实现迁移到 `remote_runner.utils`，并将 `seed_runner.utils` 改为 legacy compatibility wrapper。

## 非目标

- 不改变任何 helper 的行为、函数名、参数或返回格式。
- 不改变 CLI schema、状态目录、真实机器配置或 legacy `seed-runner` 原型命令。
- 不运行真实机器 opt-in 测试。

## 当前仓库事实

- 入口规则：`AGENTS.md`
- 初始化契约：`harness/bootstrap-contract.md`
- 当前功能项：`F-016`
- 相关文件/模块：`remote_runner/utils.py`、`seed_runner/utils.py`、`remote_runner/*.py`、legacy `seed_runner` 模块、`tests/test_remote_runner_mvp.py`
- 已知约束：`seed_runner` legacy 代码仍大量从 `seed_runner.utils` 导入；wrapper 必须保持旧导入可用。

## 允许改动

- 新增 `remote_runner/utils.py` 并放置 shared helper 实现。
- 将 `remote_runner` 内部 import 改为 `remote_runner.utils`。
- 将 `seed_runner/utils.py` 改为 re-export wrapper。
- 更新测试验证目标 helper 模块归属和 legacy wrapper 兼容。
- 同步 feature list、progress、handoff 和归档计划。

## 禁止改动

- 禁止改变 helper 输出格式或异常行为。
- 禁止删除 `seed_runner.utils`。
- 禁止触碰真实机器或真实凭据。

## 验收标准

- `remote_runner` 包内不再导入 `seed_runner.*`。
- `seed_runner.utils` 继续导出 legacy 调用所需 helper。
- Remote Runner 和 legacy seed-runner 测试通过。

## 验证命令

```sh
rg -n "from seed_runner|import seed_runner" remote_runner -S
python3 -m pytest tests/test_remote_runner_mvp.py -q
python3 -m pytest -q
./scripts/harness-check.sh
git diff --check
```

## Evidence 记录要求

验证通过后，将命令、结果和 import 边界检查写入 `harness/feature_list.json` 的 `F-016.evidence`。

## 完成定义

- 请求行为已实现。
- 非目标没有被触碰。
- 上方验证命令已运行；未运行的命令必须说明原因。
- `harness/feature_list.json` 状态和 evidence 已更新。
- `harness/session-handoff.md` 写明当前状态、风险和下一步。
- 任务完成后将本计划归档到 `plans/archive/`。

## 阻塞条件

- 若迁移会改变 legacy `seed_runner` 行为或破坏旧测试，应暂停并修复兼容 wrapper；无法兼容时再请求用户决策。

## 下一步最佳动作

1. 复制 shared helper 实现到 `remote_runner.utils`。
2. 改写 import 并让 `seed_runner.utils` re-export 目标实现。

## 完成记录

- `remote_runner.utils` 承载 shared helper 实现；`remote_runner` 包内不再依赖 `seed_runner.utils`。
- `seed_runner.utils` 改为兼容 wrapper，继续 re-export 目标 helper。
- 更新测试验证 target helper 归属与 legacy wrapper 同一对象。
- 验证：`python3 -m pytest tests/test_remote_runner_mvp.py -q` 通过 26 passed；`python3 -m pytest -q` 通过 47 passed, 2 skipped；`./scripts/harness-check.sh` 通过 0 warnings；`git diff --check` 通过。
