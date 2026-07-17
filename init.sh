#!/usr/bin/env sh

set -eu

if [ ! -f "AGENTS.md" ]; then
  printf '%s\n' "请从 Remote Runner 仓库根目录运行 ./init.sh" >&2
  exit 1
fi

./scripts/harness-check.sh

printf '%s\n' "项目：Remote Runner Local Terminal V4"
printf '%s\n' "灯塔：本地 tmux pane -> 真实 shell -> raw append-only transcript -> 显式操作/查询"
printf '%s\n' "平台：macOS/Linux + tmux；Windows 仅可作为 shell 中显式 SSH 的目标"
printf '\n%s\n' "事实来源："
printf '%s\n' "- CONTEXT.md"
printf '%s\n' "- docs/overview.md"
printf '%s\n' "- docs/architecture/core-lighthouse.md"
printf '%s\n' "- REQUIREMENTS.md"
printf '%s\n' "- docs/reference/REMOTE_RUNNER_API.md"
printf '%s\n' "- harness/feature_list.json"
printf '%s\n' "- harness/session-handoff.md"
printf '\n%s\n' "验证："
printf '%s\n' "- python3 -m pytest -q"
printf '%s\n' "- ./scripts/harness-check.sh"
printf '%s\n' "- git diff --check"
