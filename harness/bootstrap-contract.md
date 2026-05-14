<!--
职责：定义本项目被新 agent 无歧义接手的初始化契约。
边界：不要记录业务实现进度；进度放 progress.md，具体任务放 plans/active/。
-->

# 初始化契约

## 自举条件

- 能启动：当前没有长运行服务；运行 `python3 -m seed_runner.cli --help` 或安装后运行 `seed-runner --help` 可确认原型 CLI 可加载。
- 能测试：`python3 -m pytest -q`
- 能看进度：`harness/progress.md` 和 `harness/feature_list.json`
- 能接手下一步：`harness/session-handoff.md` 和 `plans/active/`

## 环境

- 技术栈：Python CLI 工具；当前包名 `seed_runner`；目标产品工作名 Remote Runner。
- 运行时版本：`pyproject.toml` 声明 Python `>=3.8`；当前本地验证使用 Python 3.13。
- 依赖安装：`python3 -m pip install -e ".[dev]"`
- 本地服务：无常驻本地服务。真实 VM 集成测试需要人工预配置 `.env.machines` 和远程机器。

## 标准命令

```sh
python3 -m pip install -e ".[dev]"
python3 -m seed_runner.cli --help
./scripts/harness-check.sh
python3 -m pytest tests/test_config.py tests/test_workflow_state.py -q
python3 -m pytest -q
SEED_RUNNER_RUN_REAL_VM_TESTS=1 python3 -m pytest tests/test_real_vm_integration.py -q
```

## 初始化验收清单

- [x] 从干净 checkout 可安装依赖：`python3 -m pip install -e ".[dev]"`。
- [x] 项目无需启动长服务；CLI help 可加载。
- [x] 至少一个可靠验证命令能运行：`python3 -m pytest -q`。
- [x] `./scripts/harness-check.sh` 通过。
- [x] 新 agent 只看仓库能回答：是什么、怎么跑、怎么测、当前进度、下一步。

## 已知缺口

- `remote-runner` 目标 CLI 尚未实现，当前可运行入口仍是 `seed-runner`。
- 当前原型仍依赖 `.env.machines`、tmux、sshfs 和 mount/session 流程。
- 真实 VM 集成测试默认跳过，只有在人工配置目标机器后才能运行。
