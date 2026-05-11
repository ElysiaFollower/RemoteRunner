文件结构建议
README.md
AGENTS.md
docs/
  overview.md     # 项目定位、核心目标、与原型的关系
  strategy/       # 战略总纲、产品边界、长期路线
  architecture/   # 系统结构、边界、核心模块
  adr/            # 架构决策记录
  how-to/         # 操作手册、发布、排障、迁移
  reference/      # API、配置、目录说明、脚本说明
  explanation/    # 设计动机、取舍、历史背景
  runbooks/       # 线上/运维/值班处理流程
plans/
  active/         # 正在做的任务 spec / plan
  archive/        # 已完成但暂时保留的执行计划
.github/
  ISSUE_TEMPLATE/
  pull_request_template.md
  CODEOWNERS
  workflows/
evals/            # 如果你在做 AI 功能，放评测样本与脚本
