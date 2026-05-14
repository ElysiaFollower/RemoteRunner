# Harness 与核心灯塔初始化归档

## 任务

按 `harness-project-initializer-zh` 重整仓库结构，把项目目标、需求和定义整理清楚，确保核心灯塔没有二义性和冲突。

## 范围

- 使用 scaffold 补齐 repo-native harness。
- 路由化 `AGENTS.md`。
- 明确 Remote Runner 目标、当前 `seed-runner` 原型、MVP 需求、术语和冲突裁决。
- 不做业务功能迁移，不实现新 `remote-runner` CLI。

## 结果

- `docs/overview.md`：项目定义、用户痛点、范围、术语、当前事实/目标事实、冲突裁决。
- `docs/architecture/core-lighthouse.md`：不可变目标、边界、分层、安全承诺、实现约束。
- `harness/`：功能清单、进度、决策、交接、质量和评估标准。
- `init.sh` 与 `scripts/harness-check.sh`：冷启动和机器门禁。

## 验证

- `./scripts/harness-check.sh`
- `python3 -m pytest -q`

## 后续

从 `F-002 Remote Runner 机器管理 MVP` 开始，先创建 active plan，再实现配置格式、状态目录和旧 `.env.machines` 兼容策略。
