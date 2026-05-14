# Timezone-aware 时间戳清理

## 目标

移除当前测试中的 `datetime.utcnow()` deprecation warnings，同时保持 Remote Runner 和 legacy seed-runner 现有 timestamp/id 输出格式兼容。

## 非目标

- 不改变状态 schema、JSON 字段名、时间戳语义或 ID 前缀格式。
- 不迁移 `seed_runner.utils` 到 `remote_runner.utils`。
- 不触碰真实机器、不运行真实机器 opt-in 测试。

## 当前仓库事实

- 入口规则：`AGENTS.md`
- 初始化契约：`harness/bootstrap-contract.md`
- 当前功能项：`F-015`
- 相关文件/模块：`seed_runner/utils.py`、`tests/test_remote_runner_mvp.py`
- 已知约束：`get_timestamp()` 输出应继续是 UTC ISO 字符串并以 `Z` 结尾；`generate_id()` 应继续包含微秒时间片和随机后缀。

## 允许改动

- 修改 `seed_runner/utils.py` 的 UTC 时间获取方式。
- 更新相关单元测试 monkeypatch。
- 同步 feature list、progress、handoff 和归档计划。

## 禁止改动

- 禁止改变 CLI 输出合同或状态文件 schema。
- 禁止修改真实机器配置或运行会写远程机器的测试。

## 验收标准

- `python3 -m pytest -q` 不再出现 `datetime.utcnow()` deprecation warnings。
- `get_timestamp()` 仍返回以 `Z` 结尾的 UTC timestamp。
- `generate_id()` 仍保持唯一性测试通过。

## 验证命令

```sh
python3 -m pytest tests/test_remote_runner_mvp.py -q
python3 -m pytest -q
./scripts/harness-check.sh
git diff --check
```

## Evidence 记录要求

验证通过后，将命令、结果和 warning 清理结果写入 `harness/feature_list.json` 的 `F-015.evidence`。

## 完成定义

- 请求行为已实现。
- 非目标没有被触碰。
- 上方验证命令已运行；未运行的命令必须说明原因。
- `harness/feature_list.json` 状态和 evidence 已更新。
- `harness/session-handoff.md` 写明当前状态、风险和下一步。
- 任务完成后将本计划归档到 `plans/archive/`。

## 阻塞条件

- 若清理 warning 会改变 timestamp 字符串格式或破坏现有状态恢复，应暂停并重新评估兼容策略。

## 下一步最佳动作

1. 用 `datetime.now(timezone.utc)` 替代 `datetime.utcnow()`。
2. 更新固定时间测试并运行聚焦验证。

## 完成记录

- `seed_runner.utils.get_timestamp()` 改为 `datetime.now(timezone.utc)`，仍输出 `Z` 后缀。
- `seed_runner.utils.generate_id()` 改为 timezone-aware UTC 时间片，仍保留微秒和随机后缀。
- 更新测试覆盖 timestamp 的 `Z` 后缀和 ID 时间碰撞唯一性。
- 验证后 `python3 -m pytest -q` 不再输出 deprecation warnings。
