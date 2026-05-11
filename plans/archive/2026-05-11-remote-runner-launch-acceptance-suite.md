# Remote Runner 上线验收测试资产

## 目标

建立一套长期可复用的 Remote Runner launch acceptance suite，用于上线前验证核心能力：目标包名/legacy 兼容、机器配置脱敏、session exec、日志状态、file put/get/list、run once、产物 manifest，以及真实机器 opt-in 闭环。

## 非目标

- 不改变产品功能、CLI schema、状态目录或真实机器配置。
- 不默认运行真实机器测试；真实测试必须显式 opt-in，并只写入 `REMOTE_RUNNER_REAL_TEST_CWD`。
- 不把真实机器 host、用户名、密码、私人路径或探针输出写入仓库。
- 不替代单元测试；本任务新增的是上线验收层。

## 当前仓库事实

- 入口规则：`AGENTS.md`
- 初始化契约：`harness/bootstrap-contract.md`
- 当前功能项：`F-017` passing
- 相关文件/模块：`tests/test_remote_runner_launch_suite.py`、`tests/remote_runner_launch_support.py`、`docs/testing/remote-runner-launch-acceptance.md`、`tests/test_remote_runner_real_integration.py`
- 已知约束：Remote Runner 核心目标是基于 SSH 的本地 CLI，让 AI 能通过稳定命令访问外部机器终端、执行命令、收集结构化输出、日志和产物。

## 允许改动

- 新增 launch acceptance 测试文件和复用 helper。
- 新增测试说明文档，列出默认门禁、真实机器门禁、环境变量和安全边界。
- 同步 feature list、progress、handoff 和归档计划。

## 禁止改动

- 禁止写入真实机器目录之外的任何路径。
- 禁止提交真实凭据、host、用户名或本机私人路径。
- 禁止把默认测试变成依赖真实机器。

## 验收标准

- 默认 launch suite 可在无真实机器环境下运行，验证公共接口和 fake-backed 核心闭环。
- 真实机器 launch smoke 默认 skip；显式设置环境变量后验证 doctor、session exec、file put/get/list、run once、artifact pullback、cleanup 和 session destroy。
- 测试资产文档说明测试分层、命令、环境变量和上线判定。
- 完整本地测试、harness 检查和 diff check 通过。

## 验证命令

```sh
python3 -m pytest tests/test_remote_runner_launch_suite.py -q
python3 -m pytest tests/test_remote_runner_real_integration.py -q
python3 -m pytest -q
./scripts/harness-check.sh
git diff --check
```

可选真实机器验收：

```sh
REMOTE_RUNNER_RUN_REAL_TESTS=1 \
REMOTE_RUNNER_REAL_MACHINE=<machine_id> \
REMOTE_RUNNER_REAL_TEST_CWD=<remote_cwd> \
python3 -m pytest tests/test_remote_runner_launch_suite.py tests/test_remote_runner_real_integration.py -q
```

## Evidence 记录要求

验证通过后，将默认测试结果、真实机器验证结果或未运行原因写入 `harness/feature_list.json` 的 `F-017.evidence`。

## 完成定义

- 请求行为已实现。
- 非目标没有被触碰。
- 上方验证命令已运行；未运行的命令必须说明原因。
- `harness/feature_list.json` 状态和 evidence 已更新。
- `harness/session-handoff.md` 写明当前状态、风险和下一步。
- 任务完成后将本计划归档到 `plans/archive/`。

## 阻塞条件

- 若真实机器不可达或凭据失效，默认测试仍应可通过；真实机器结果标为未验证或 blocked，不猜测原因。
- 若上线验收需要修改产品行为而不是测试资产，应暂停并另开实现任务。

## 下一步最佳动作

1. 上线或发 PR 前按测试说明重跑默认门禁和真实机器 opt-in 门禁。
2. 若继续产品能力演进，为 `F-005` profile/report 层建立新的 active plan。

## 完成记录

- 新增默认 launch acceptance suite：`tests/test_remote_runner_launch_suite.py`。
- 新增复用 helper：`tests/remote_runner_launch_support.py`。
- 新增测试说明：`docs/testing/remote-runner-launch-acceptance.md`，README 已增加入口。
- 默认 suite 覆盖目标包名、legacy wrapper、机器配置脱敏、startup commands、path mapping、session exec/logs/destroy、file put/list/get、transfer records、run once、artifact manifest、session state 和 run state。
- 真实机器 opt-in smoke 覆盖 doctor、session create/exec、file put/list/get、run once artifact pullback、远程 cleanup 和 session destroy。
- 验证：`python3 -m pytest tests/test_remote_runner_launch_suite.py -q` 通过 2 passed, 1 skipped；`python3 -m pytest tests/test_remote_runner_real_integration.py -q` 通过 1 skipped；`python3 -m pytest -q` 通过 49 passed, 3 skipped；`./scripts/harness-check.sh` 通过 0 warnings；`git diff --check` 通过；真实机器 opt-in launch+integration smoke 通过 4 passed。
