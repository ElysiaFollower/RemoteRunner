#!/usr/bin/env sh
# 职责：初始化本地项目 harness，并运行最便宜且可靠的 sanity checks。
# 边界：不要安装全局工具、写入密钥、启动长运行服务，或意外修改项目源码。

set -eu

repo_root=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
cd "$repo_root"

echo "项目：Remote Runner"
echo "灯塔：本地轻量远程机器操作 CLI；machine -> session -> command/file -> logs/artifacts"
echo "当前原型：seed-runner CLI，Python package seed_runner"
echo

if [ -x "./scripts/harness-check.sh" ]; then
  ./scripts/harness-check.sh
else
  echo "缺少可执行文件 scripts/harness-check.sh"
fi

cat <<'EOF'

事实来源：
- docs/overview.md
- docs/architecture/core-lighthouse.md
- REQUIREMENTS.md
- docs/reference/REMOTE_RUNNER_API.md
- docs/reference/SEED_RUNNER_API.md
- harness/feature_list.json
- harness/session-handoff.md

启动/检查：
- 当前原型 CLI：python3 -m seed_runner.cli --help
- 依赖安装：python3 -m pip install -e ".[dev]"

聚焦验证：
- python3 -m pytest tests/test_config.py tests/test_workflow_state.py -q

完整验证：
- python3 -m pytest -q

真实 VM 验证：
- SEED_RUNNER_RUN_REAL_VM_TESTS=1 python3 -m pytest tests/test_real_vm_integration.py -q
EOF
