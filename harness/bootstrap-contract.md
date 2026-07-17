<!-- 职责：定义新 Agent 如何无歧义启动本项目。 -->

# 初始化契约

## 环境

- Python 3.10+
- macOS/Linux
- local tmux
- 无网络、远端机器、daemon 或数据库前置条件

## 启动

```bash
./init.sh
python3 -m remote_runner.cli --help
```

## 验证

```bash
python3 -m pytest -q
python3 -m black --check remote_runner tests
python3 -m flake8 remote_runner tests --ignore=E203,W503,E501
python3 -m mypy remote_runner
./scripts/harness-check.sh
git diff --check
```

测试只使用独立 tmux socket 和 pytest 临时 state，不应出现默认 tmux 或真实用户 state 写入。

## 恢复路径

- 当前目标和不变量：`docs/overview.md`、`docs/architecture/core-lighthouse.md`
- 当前任务：`plans/active/`
- 当前状态：`harness/session-handoff.md`
- 当前功能：`harness/feature_list.json`
