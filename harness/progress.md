<!--
职责：记录跨会话进度、状态变化、阻塞和验证摘要，让新会话能快速恢复。
边界：不要存放聊天记录、原始日志、密钥，或更适合由代码、测试、ADR、任务计划表达的内容。
-->

# 进度日志

## 当前状态

- 当前功能项：`F-024 Remote Runner readable session names` passing；`F-023`、`F-022`、`F-021`、`F-020` passing；`F-005` profile/report 层未开始。
- 最近任务计划：`plans/archive/2026-06-24-readable-session-names.md`。
- 当前阶段性分支：`dev-windows-agent-pwsh-backend`，用于隔离 direct Windows OpenSSH 支持工作，避免破坏当前 Linux/tmux 稳定路径。
- 上次验证：2026-06-19，stale tmux session recovery 通过：`python3 -m py_compile remote_runner/remote_backend.py remote_runner/remote_session.py tests/test_remote_runner_mvp.py` 通过；`python3 -m pytest tests/test_remote_runner_mvp.py -q` 通过 41 passed；默认 `python3 -m pytest tests/test_remote_runner_real_integration.py -q` 通过 2 skipped；configured Linux/tmux machine 压力自测覆盖大量输出、静默 wait、同步 timeout 后恢复、后台轮询/wait/stop、file put/list/get、run once、外部 kill tmux 后 lost/exec reject/destroy、最终 exec 和 cleanup；另一台 Linux/tmux machine 深度自测覆盖持久 shell、timeout 恢复、后台 wait、file、run once 和 lost/destroy；真实 opt-in `tests/test_remote_runner_real_integration.py` 通过 1 passed, 1 skipped；真实 opt-in `tests/test_remote_runner_launch_suite.py` 通过 3 passed；完整 `python3 -m pytest -q` 通过 64 passed, 4 skipped；`./scripts/harness-check.sh` 0 warnings；`git diff --check` 通过；真实历史 stale command 已从 running 收敛为 failed，真实历史 busy session 已从 active/busy 收敛为 lost/failed。
- 下一步最佳动作：提交 F-023；后续如需要可增加显式 `session recover/list --refresh` 命令批量收敛历史状态。
- 2026-06-24：完成本地未跟踪 `docs/issues/` 分拣；确认 `2026-06-09-readable-session-names.md` 是真实可用性缺口并直接实现。`session create --name` 已落地，session/file 命令通过统一 resolver 支持 `session_id` 或唯一 name；非法 name、同机未销毁重名、跨机歧义和旧无 name session 兼容均有测试。同步 README、REQUIREMENTS、API、getting-started、SKILL 和 harness；删除临时 `docs/issues/`。验证：MVP 45 passed，launch 2 passed/1 skipped，默认 real integration 2 skipped，完整 pytest 68 passed/4 skipped，harness-check 0 warnings，git diff --check 通过。
- 2026-06-09 诊断记录：实践中发现服务器侧刚更新用户组后，Remote Runner `session destroy && session create` 仍可能看不到新补充组。代码确认当前 Linux/SSH + tmux backend 不是持久登录用户账号；它通过 SSH 执行 `tmux new-session`，创建新的 Remote Runner session 和新的 tmux session。但如果该用户已有 tmux server 进程，新的 shell 可能由既有 tmux server fork，继续继承该 server 的旧 Unix 补充组。当前 API 没有独立 `restart/refresh-auth`，公开重启路径只有 destroy/create；若既有 tmux server 仍存活，授权上下文可能继续过时。
- 2026-06-09：`F-021 Remote Runner tmux server 安全重启接口` 完成并归档至 `plans/archive/2026-06-09-remote-runner-tmux-server-restart.md`。已新增 `docs/lessons-learned/2026-06-09-tmux-server-auth-context.md`，并实现 `machine restart-tmux-server` direct-SSH 接口；验证通过：`./scripts/harness-check.sh` 0 warnings，`python3 -m pytest tests/test_remote_runner_mvp.py -q` 36 passed，`python3 -m pytest -q` 59 passed, 3 skipped，`git diff --check` 通过。

## 状态约定

- `not_started`：尚未开始。
- `active`：当前唯一在制任务。
- `blocked`：缺少输入、环境、依赖或决策。
- `passing`：验证通过且 evidence 已记录。

## 日志

### 2026-05-07 - 定位重构分支建立

- 创建分支 `dev/research-runner-positioning`。
- 将 README、需求、Agent 指令、Skill 和 API 文档从 SEEDRunner 专用叙事改为通用远程机器操作 CLI 定位。
- 新增目标 API 合同 `docs/reference/REMOTE_RUNNER_API.md`。
- 验证：`python3 -m pytest -q` 通过 21 passed, 1 skipped, 20 warnings。

### 2026-05-07 - Harness 初始化与核心灯塔固化

- 按 `harness-project-initializer-zh` scaffold 创建 repo-native harness。
- 将 `AGENTS.md` 路由化，新增 `docs/architecture/core-lighthouse.md`。
- 明确当前事实与目标事实、冲突裁决、术语定义、需求边界和开发顺序。
- 验证：`./scripts/harness-check.sh` 通过；`python3 -m pytest -q` 通过 21 passed, 1 skipped, 20 warnings。

### 2026-05-07 - 灯塔从 research 专用纠偏为远程机器操作接口

- 根据用户校正，将项目工作名从 Research Runner 调整为 Remote Runner。
- 明确 research、实验、科研和运维都是上层 use case/profile；远程交互接口才是核心。
- 更新目标 API 路径为 `docs/reference/REMOTE_RUNNER_API.md`。
- 验证：`./scripts/harness-check.sh` 通过 0 warnings；`./init.sh` 通过；`python3 -m pytest -q` 通过 21 passed, 1 skipped, 20 warnings。

### 2026-05-07 - 第一轮重构准备文档落地

- 创建分支 `dev/remote-runner-machine-session-mvp`。
- 新增 ADR：`docs/adr/0001-no-mount-core.md`。
- 新增 Spec：`docs/specs/machine-session-file-mvp.md`。
- 新增 Active Plan：`plans/active/2026-05-07-remote-runner-machine-session-file-mvp.md`（完成后归档为 `plans/archive/2026-05-08-remote-runner-machine-session-file-mvp.md`）。
- 将 `F-002` 标为 active，明确第一轮 MVP 包含 machine、session exec/logs 和 file put/get/list。
- 验证：`./scripts/harness-check.sh` 通过 0 warnings；`python3 -m pytest -q` 通过 21 passed, 1 skipped, 20 warnings。

### 2026-05-08 - Remote Runner mount-free MVP 实现落地

- 新增 `remote-runner` console script，当前包名暂保留 `seed_runner`。
- 新增 mount-free 模块：`remote_state.py`、`remote_machine.py`、`remote_backend.py`、`remote_session.py`、`remote_file.py`、`remote_cli.py`。
- 目标状态根为 `~/.remote-runner/`，测试可用 `REMOTE_RUNNER_STATE_DIR` 覆盖；机器、会话、命令日志、传输记录和 artifact manifest 均落本地状态。
- 命令执行直接通过 SSH backend 在远程 `cwd` 执行，不依赖 mount；非零 exit code 保留日志且不销毁 session；同一 session 并发 exec 会返回 busy。
- 文件传输通过显式 SFTP backend 的 put/get/list；失败传输也写入本地 transfer 记录；成功 get 会写入 artifact manifest。
- 新增 `tests/test_remote_runner_mvp.py` 覆盖 machine/session/file 核心行为和 CLI JSON 脱敏。
- 验证：`python3 -m pytest tests/test_remote_runner_mvp.py -q` 通过 6 passed；`python3 -m pytest -q` 通过 27 passed, 1 skipped, 59 warnings；`./scripts/harness-check.sh` 通过 0 warnings；`git diff --check` 通过。

### 2026-05-08 - SSH 机器交互式配置接口落地

- 新增 `F-006` 任务合同并完成归档：`plans/archive/2026-05-08-remote-runner-ssh-machine-config.md`。
- `remote-runner machine add` 支持缺失字段交互式输入；prompt 写到 stderr，`--json` stdout 保持单 JSON。
- 密码认证走 `getpass` 隐藏输入；`--password` flag 保留但文档标为不推荐。
- 同名机器默认拒绝；`--replace` 需要交互式精确输入 machine ID，或非交互 `--confirm-replace <machine_id>`。
- 覆盖保留原 `created_at`，写入 `updated_at`，不删除已有 session/log/transfer/artifact。
- 文档同步 README、REQUIREMENTS、Remote Runner API 和 MVP spec。
- 验证：`python3 -m pytest tests/test_remote_runner_mvp.py -q` 通过 13 passed；`python3 -m pytest -q` 通过 34 passed, 1 skipped, 68 warnings；black check 通过；`./scripts/harness-check.sh` 通过 0 warnings；尾随空白扫描无结果；`git diff --check` 因本机 Xcode license 未接受被阻断。

### 2026-05-08 - SSH 后预置指令与 Windows WSL 验证落地

- 新增 `startup_commands` 机器字段，用于 SSH 登录后按序发送预置指令。
- `remote-runner machine add` 交互式配置会询问 startup commands；已有机器可用 `machine configure-startup` 修改 startup commands 和 default cwd，不需要重填账密。
- 后端在存在 startup commands 时使用交互式 SSH shell，发送 carriage return 以兼容 Windows conhost，并用 sentinel 捕获用户命令退出码。
- `machine doctor` 和 `session exec` 已支持 startup-aware 执行路径。
- 为交互式 stdout 增加 ANSI/control 清理和 sentinel 行过滤，避免 JSON/log 被 Windows conhost 输出淹没。
- 真实验证：Windows+WSL 蓝本配置 `startup_commands=["wsl"]`、`default_cwd=/mnt/c/Users/example/Desktop/SSHRunner`；`machine doctor` 通过；`session exec` 在该目录内创建、读取、删除 `rr_probe.txt` 后 exit_code=0；只读 `pwd && printf` 复验通过；测试 session 已 destroy。
- 验证：`python3 -m pytest tests/test_remote_runner_mvp.py -q` 通过 15 passed；`python3 -m pytest -q` 通过 36 passed, 1 skipped, 73 warnings；`./scripts/harness-check.sh` 通过 0 warnings；black check 通过；`git diff --check` 通过；尾随空白扫描无结果。

### 2026-05-11 - SFTP 路径映射与真实文件传输验证落地

- 新增 `path_mappings` 机器字段，用于显式记录命令路径前缀到 SFTP 文件路径前缀的映射。
- 新增 `remote-runner machine configure-path-map`，可在不重填账密的情况下更新已有机器路径映射。
- SFTP backend 在 `file put/get/list` 前应用路径映射，`file list` 返回路径回映射到用户输入的命令侧路径。
- 传输记录和 artifact manifest 保持用户传入的原始 remote path，不暴露 backend 内部路径作为主接口。
- 修复真实验证中发现的并发 ID 碰撞：`generate_id` 增加随机后缀，避免多个 CLI 进程在同一微秒生成相同 `transfer_id`。
- 真实验证：Windows+WSL 蓝本配置 `/mnt/c/Users/example/Desktop/SSHRunner` -> `C:/Users/example/Desktop/SSHRunner`；在 `SSHRunner` 内完成 `rr_sftp_probe_20260511.txt` 的 file put/list/get，本地 `cmp` 内容一致，随后用 session exec 删除并复验目录为空；测试 session 已 destroy。
- 验证：`python3 -m pytest tests/test_remote_runner_mvp.py -q` 通过 19 passed；`python3 -m pytest -q` 通过 40 passed, 1 skipped, 79 warnings；`./scripts/harness-check.sh` 通过 0 warnings；black check 通过；`git diff --check` 通过。

### 2026-05-11 - 交互式 SSH 输出清理落地

- startup-aware interactive SSH 新增 begin marker 与 exit marker，用户命令输出只截取两者之间的内容。
- 进入 startup 后的目标 shell 会尝试清空 `PS1` 并关闭 echo，减少 prompt 和输入回显。
- 清理器支持把真实终端中同一行的 runtime marker 拆出来，避免 conhost/WSL 光标控制序列导致用户输出被误删。
- 单元测试覆盖 Windows banner、startup/cd/命令回显、prompt、sentinel 过滤。
- 真实验证：Windows+WSL 蓝本 doctor 通过；在 `SSHRunner` 内只读执行 `pwd && printf "remote-runner-clean-output\n"`，stdout 只包含 `/mnt/c/Users/example/Desktop/SSHRunner` 和 `remote-runner-clean-output`；测试 session 已 destroy。
- 验证：`python3 -m pytest tests/test_remote_runner_mvp.py -q` 通过 19 passed；`python3 -m pytest -q` 通过 40 passed, 1 skipped, 79 warnings；`./scripts/harness-check.sh` 通过 0 warnings；black check 通过；`git diff --check` 通过。

### 2026-05-11 - Remote Runner 真实机器 opt-in 集成测试落地

- 新增 `tests/test_remote_runner_real_integration.py`，默认未设置 `REMOTE_RUNNER_RUN_REAL_TESTS=1` 时 skip。
- 显式设置 `REMOTE_RUNNER_REAL_MACHINE` 和 `REMOTE_RUNNER_REAL_TEST_CWD` 后，测试覆盖 doctor、session create/exec、file put/list/get、内容比对、远程 cleanup 和 session destroy。
- 测试只写入 `REMOTE_RUNNER_REAL_TEST_CWD` 下的随机探针文件，finally 尽量清理远程文件并销毁 session。
- README 和 AGENTS 验证阶梯新增 Remote Runner 真实集成测试命令。
- 真实验证：使用当前 Windows `SSHRunner` 目录运行 opt-in 测试 1 passed。
- 验证：默认 `python3 -m pytest tests/test_remote_runner_real_integration.py -q` 为 1 skipped；真实 opt-in 运行 1 passed；`python3 -m pytest -q` 通过 40 passed, 2 skipped, 79 warnings；`./scripts/harness-check.sh` 通过 0 warnings；black check 通过；`git diff --check` 通过。

### 2026-05-11 - Run Once 通用闭环落地

- 新增 run state：`~/.remote-runner/runs/<run_id>.json`。
- 新增 `RemoteRunManager`，编排 session create、input put、command exec、artifact get、run manifest 保存和默认 session destroy。
- 新增 CLI：`remote-runner run once/list/show`。
- `run once` 支持 `--input LOCAL=REMOTE` 和 `--artifact REMOTE=LOCAL`；使用 `=` 避免 Windows 路径冒号冲突。
- run manifest 记录 run_id、machine_id、session_id、cwd、command、inputs、command_result、artifacts、status、started_at、ended_at 和 destroy_session_result。
- 非零退出码会将 run 标记为 failed，但保留命令日志和 manifest。
- 真实验证：Windows+WSL 蓝本的 `SSHRunner` 目录内 run once 上传输入、执行命令生成输出、拉回 artifact、本地 cmp 成功；随后清理远程 input/output 探针文件并销毁 cleanup session；`run list/show` 可恢复查询 manifest。
- 验证：`python3 -m pytest tests/test_remote_runner_mvp.py -q` 通过 21 passed；`python3 -m pytest -q` 通过 42 passed, 2 skipped, 101 warnings；`./scripts/harness-check.sh` 通过 0 warnings；black check 通过；`git diff --check` 通过。

### 2026-05-11 - Remote Runner 包名 facade 落地

- 新增 `remote_runner` package facade。
- `remote_runner.cli` 委托 `seed_runner.remote_cli.main`，避免复制实现。
- `pyproject.toml` 中 `remote-runner` console script 改为 `remote_runner.cli:main`；legacy `seed-runner` 仍指向 `seed_runner.cli:main`。
- README 和 overview 同步：当前实现仍主要在 `seed_runner`，目标包名 facade 是 `remote_runner`。
- 验证：`python3 -m remote_runner.cli --help` 通过；`python3 -m pytest tests/test_remote_runner_mvp.py -q` 通过 22 passed；`python3 -m pytest -q` 通过 43 passed, 2 skipped, 101 warnings；`./scripts/harness-check.sh` 通过 0 warnings；black check 通过；`git diff --check` 通过。

### 2026-05-11 - Remote Runner 公共模块 facade 落地

- 新增 `remote_runner.remote_backend`、`remote_runner.remote_machine`、`remote_runner.remote_session`、`remote_runner.remote_file`、`remote_runner.remote_run`、`remote_runner.remote_state`。
- 这些 facade 模块 re-export 当前 `seed_runner.remote_*` 实现，不复制逻辑。
- 新增测试验证 facade 公共对象与 `seed_runner` 实现对象一致。
- README 和 overview 同步：Remote Runner 公共模块可通过 `remote_runner.remote_*` 导入，当前仍委托 `seed_runner.remote_*`。
- 验证：`python3 -m remote_runner.cli --help` 通过；目标 import path smoke 通过；`python3 -m pytest tests/test_remote_runner_mvp.py -q` 通过 23 passed；`python3 -m pytest -q` 通过 44 passed, 2 skipped, 101 warnings；`./scripts/harness-check.sh` 通过 0 warnings；black check 通过；`git diff --check` 通过。

### 2026-05-11 - 阶段性提交整理

- 将大工作树整理为三段可审计提交：Remote Runner 灯塔/harness 文档、mount-free machine/session/file/run CLI 实现、真实机器 opt-in 集成测试。
- 提交前将仓库文档和测试中的真实机器别名与本机 Windows 用户路径替换为通用示例，避免把机器细节写入提交历史。
- handoff/progress 作为单独收尾提交记录当前状态。
- 验证：`python3 -m pytest tests/test_remote_runner_mvp.py -q` 通过 23 passed, 81 warnings。
- 收尾验证发现 `scripts/harness-check.sh` 对 handoff 旧标题的检查已过期，同时 `$heading` 后接中文标点在 `set -u` 下触发解析问题；已改为检查当前 handoff 标题并用 `${heading}` 展开。

### 2026-05-11 - Remote Runner 包实现迁移开工

- 新增 active plan：`plans/active/2026-05-11-remote-runner-package-implementation-migration.md`。
- 新增 `F-014` active：目标是让 `remote_runner` 承载真实实现，`seed_runner.remote_*` 退为兼容 wrapper。
- 非目标：不改变 CLI schema、不删除 legacy 原型、不运行真实机器 opt-in 测试、不触碰用户远程机器。

### 2026-05-11 - Remote Runner 包实现迁移完成

- 将 `remote_runner.cli`、`remote_runner.remote_backend`、`remote_machine`、`remote_session`、`remote_file`、`remote_run`、`remote_state` 从 facade 改为真实实现模块。
- 将 `seed_runner.remote_*` 改为 legacy compatibility wrappers，继续 re-export 目标实现，旧导入不破坏。
- 更新测试默认从 `remote_runner.*` 导入，并增加检查：目标类/函数的 `__module__` 属于 `remote_runner.*`，legacy wrapper 返回同一对象。
- 默认真实机器集成测试入口改为 `python3 -m remote_runner.cli`，仍默认 skip，不触碰远程机器。
- 同步 README 和 overview 中的包名事实。
- 验证：`python3 -m remote_runner.cli --help` 通过；`python3 -m seed_runner.remote_cli --help` 通过；`python3 -m pytest tests/test_remote_runner_mvp.py -q` 通过 24 passed；`python3 -m pytest tests/test_remote_runner_real_integration.py -q` 通过 1 skipped；`python3 -m pytest -q` 通过 45 passed, 2 skipped, 101 warnings；black check 通过；`./scripts/harness-check.sh` 通过 0 warnings；`git diff --check` 通过。

### 2026-05-11 - Timezone-aware 时间戳清理开工

- 新增 active plan：`plans/active/2026-05-11-timezone-aware-timestamps.md`。
- 新增 `F-015` active：目标是移除 `datetime.utcnow()` deprecation warnings，同时保持 timestamp 和 id 输出格式兼容。

### 2026-05-11 - Timezone-aware 时间戳清理完成

- `seed_runner.utils.get_timestamp()` 改为使用 `datetime.now(timezone.utc)`，保持 `Z` 后缀输出。
- `seed_runner.utils.generate_id()` 改为 timezone-aware UTC 时间片，保持微秒时间片和随机后缀。
- 新增测试确认 `get_timestamp()` 输出以 `Z` 结尾且不包含 `+00:00`。
- 验证：`python3 -m pytest tests/test_remote_runner_mvp.py -q` 通过 25 passed；`python3 -m pytest -q` 通过 46 passed, 2 skipped，且无 warnings；`./scripts/harness-check.sh` 通过 0 warnings；`git diff --check` 通过；`remote_runner` 与 legacy `seed_runner.remote_cli` help 均通过。

### 2026-05-11 - Remote Runner shared utils 迁移开工

- 新增 active plan：`plans/active/2026-05-11-remote-runner-utils-migration.md`。
- 新增 `F-016` active：目标是让 `remote_runner` 包内不再依赖 `seed_runner.utils`，同时保持 legacy `seed_runner.utils` 导入可用。

### 2026-05-11 - Remote Runner shared utils 迁移完成

- `remote_runner.utils` 承载 shared helper 实现；`remote_runner` 包内不再依赖 `seed_runner.utils`。
- `seed_runner.utils` 改为 legacy compatibility wrapper，并继续 re-export 目标 helper。
- 新增测试确认 legacy wrapper 与 target helper 同一对象，且 `remote_runner` 内部 import 边界已清理。
- 验证：`python3 -m pytest tests/test_remote_runner_mvp.py -q` 通过 26 passed；`python3 -m pytest -q` 通过 47 passed, 2 skipped；`./scripts/harness-check.sh` 通过 0 warnings；`git diff --check` 通过；`remote_runner` import 边界检查无残留 `seed_runner.utils` 引用。

### 2026-05-11 - 上线验收测试资产开工

- 新增 active plan：`plans/active/2026-05-11-remote-runner-launch-acceptance-suite.md`。
- 新增 `F-017` active：目标是建立长期可复用 launch acceptance suite，覆盖默认 fake-backed 核心闭环和真实机器 opt-in 烟雾测试。
- 安全边界：真实机器验收默认 skip，只有显式设置 `REMOTE_RUNNER_RUN_REAL_TESTS=1`、机器 ID 和测试目录时才运行，并只写 `REMOTE_RUNNER_REAL_TEST_CWD`。

### 2026-05-11 - 上线验收测试资产完成

- 新增 `tests/test_remote_runner_launch_suite.py` 和 `tests/remote_runner_launch_support.py`，默认覆盖目标公共接口、legacy wrapper、机器配置脱敏、startup commands、path mapping、session exec/logs/destroy、file put/list/get、transfer records、run once、artifact manifest、session state 和 run state。
- 新增 `docs/testing/remote-runner-launch-acceptance.md`，说明默认门禁、真实机器门禁、环境变量、安全边界和上线判定；README 增加入口链接。
- 真实机器 opt-in smoke 覆盖 doctor、session create/exec、file put/list/get、run once artifact pullback、远程 cleanup 和 session destroy；测试只写入显式安全测试目录，未把真实机器细节写入仓库。
- 验证：`python3 -m pytest tests/test_remote_runner_launch_suite.py -q` 通过 2 passed, 1 skipped；`python3 -m pytest tests/test_remote_runner_real_integration.py -q` 通过 1 skipped；`python3 -m pytest -q` 通过 49 passed, 3 skipped；`./scripts/harness-check.sh` 通过 0 warnings；`git diff --check` 通过；真实机器 opt-in launch+integration smoke 通过 4 passed。

### 2026-05-12 - seedrunner 环境安装与 Linux 蓝本复核

- 已在 `seedrunner` conda 环境中执行 `python -m pip install -e .`，`remote-runner` console script 可直接调用。
- 新增 `docs/getting-started.md`，补齐安装、基础用法、Windows+WSL、真实机器验收和可写测试目录要求。
- 两台 Linux 蓝本中，一台真实 launch+integration smoke 通过；另一台的 `/home/ely/tmp` 目录为 root-owned 且不可写，导致真实文件传输在该目录上出现权限阻塞。

### 2026-05-13 - Remote Runner skill 去 legacy 化

- 仓库根目录 `SKILL.md` 已改为纯 `remote-runner` skill，不再保留 `seed-runner mount/sshfs/tmux` workflow。
- 已安装 skill 从 `~/.codex/skills/seed-runner` 迁移为 `~/.codex/skills/remote-runner`，旧目录已删除，避免后续 agent 触发旧流程。
- skill 现在要求先 `machine doctor`，通过 `session exec`、`file put/get/list` 和 `run once` 操作远程机器；失败时按 auth、远程路径权限、SFTP subsystem 和 path mapping 分类。

### 2026-05-13 - 后台会话命令任务开工

- 创建分支 `dev/remote-runner-background-commands`。
- 新增 active plan：`plans/active/2026-05-13-remote-runner-background-session-commands.md`。
- 新增 `F-018` active：目标是让 session 下长时间运行的远程命令可后台启动、按 `command_id` 查询状态/有界输出、等待完成或停止，同时保留现有同步 `session exec` 行为。
- 范围边界：第一切片不实现完整 attach shell、stdin streaming、PTY、实时输出推送、tmux/daemon 依赖或 profile/report 层。

### 2026-05-13 - 后台会话命令完成

- `remote-runner session exec --mode background` 已实现，返回 durable `command_id`、远端状态目录和本地摘要日志路径。
- 新增 `remote-runner session command list/show/wait/stop`，可跨 CLI 进程恢复后台命令状态、查看有界输出、等待完成或停止命令。
- 代码与文档同步更新：API contract、spec、getting-started、README 和 Remote Runner skill 都已补齐后台命令语义。
- 真实验证：`seed-lab` Linux/SSH 蓝本在 `/tmp` 安全目录中通过 opt-in 集成测试 1 passed；背景命令可启动、show 可见中间输出、wait 可收回最终结果，cleanup 与 session destroy 均成功。

### 2026-05-14 - 持久 Terminal Session 开工

- 创建分支 `dev/remote-runner-persistent-terminals`。
- 读取 GitHub issue #5，确认需求是面向 Socratic 学生 shell panel 的真实 terminal transcript：同一个 UI tab 对应同一个持续 shell，上下文和 transcript 在多次输入之间保留。
- 新增 active plan：`plans/active/2026-05-14-remote-runner-persistent-terminal-sessions.md`。
- 新增 `F-019` active：目标是新增 `terminal` 能力，而不是把现有 automation-safe `session exec` 改为持久 shell。

### 2026-05-14 - 持久 Terminal Session 完成

- 新增 `remote-runner terminal create/list/show/send/read/destroy`。
- 新增 terminal 本地状态和 transcript 保存；`terminal read` 返回 transcript、cursor、since 和截断标记，支持新 CLI 进程恢复读取。
- Linux/SSH 第一后端使用 tmux；terminal 多次 send 会进入同一个远程 shell，上下文可保留 `cd`、环境变量等 shell-local state。
- 现有 `session exec --mode wait/background`、`session command ...`、`file`、`run once` 语义保持不变。
- 真实验证：Linux/SSH 蓝本在 `/tmp` 安全目录中通过 opt-in 集成测试 1 passed；同一 terminal 内 `cd/export/pwd/printf` 状态连续保留，destroy 后保留本地 transcript。

### 2026-05-14 - Session 持久 Terminal 统一模型开工

- 用户指出顶层 `terminal` 与 `session` 平级会造成职责不清；项目仍未正式上线，不应积累这个 API 包袱。
- 新增 active plan：`plans/active/2026-05-14-remote-runner-session-terminal-unification.md`。
- 新增 `F-020` active：目标是把持久 shell/terminal 语义并入 `session`，让 `session exec/send/read/destroy` 都作用于同一个远程工作上下文。
- 当前 PR #6 保持 draft，F-019 的 tmux 实现可作为 backend 素材，但公开 API 和文档需要改成 session 统一模型。

### 2026-05-14 - Session 持久 Terminal 统一模型完成

- `session create` 现在创建 tmux-backed 持久 shell，并把 backend、remote tmux 名称、transcript 路径和 cursor 记录在 session state。
- `session exec` 现在在同一 session shell 内通过 wrapper 执行命令，返回稳定的 `command_id`、stdout/stderr、exit code、timestamps、duration、日志和远端 state 文件引用。
- `session send/read` 提供原始输入和 transcript/cursor 读取；顶层 `remote-runner terminal ...` CLI 和 `remote_terminal` 模块已移除，不再作为目标公开 API。
- `session destroy` 会销毁远端 backend shell，同时保留本地 session state、命令日志、传输记录、artifact manifest 和 transcript。
- 真实验证：Linux/SSH 蓝本在 `/tmp` 安全目录中通过 opt-in 集成测试 1 passed；同一 session 内 `cd/export/pwd/printf` 状态连续保留，后台命令 wait/stop、文件传输和 cleanup 均通过。

### 2026-05-14 - 平台边界文档收束

- 明确当前 MVP 主支持平台为 Linux/SSH + tmux；Windows OpenSSH + WSL 不作为当前上线主路径。
- 新增 `docs/platform-support.md`，同步 README、需求、overview、核心灯塔、API、spec、getting-started、skill 和 launch acceptance 文档。
- `startup_commands` 与 `path_mappings` 保留为兼容/未来 backend 输入；当前持久 session backend 可拒绝依赖这些启动链路的机器。
- 验证：`./scripts/harness-check.sh` 通过 0 warnings；`python3 -m pytest tests/test_remote_runner_mvp.py -q` 通过 31 passed；`python3 -m pytest tests/test_remote_runner_launch_suite.py -q` 通过 2 passed, 1 skipped；`python3 -m pytest -q` 通过 54 passed, 3 skipped；`git diff --check` 通过。

### 2026-05-14 - PR #6 review transcript 持久化修复

- 针对 reviewer 提出的 transcript 覆盖风险，`session read` 改为把远端 tmux capture 增量合并到本地累计 transcript，不再用有限 tmux buffer 覆盖本地文件。
- 本地 transcript 文件读写和 session state 更新统一放入 `remote_state_lock`，并避免无变化时重复写文件。
- 新增回归测试模拟远端 capture 因 history rotation 只剩尾部内容时，本地 transcript 仍保留旧历史并只追加新增行。
- 验证：`python3 -m py_compile remote_runner/remote_session.py` 通过；`python3 -m pytest tests/test_remote_runner_mvp.py -q` 通过 32 passed；`python3 -m pytest tests/test_remote_runner_launch_suite.py -q` 通过 2 passed, 1 skipped；`python3 -m pytest -q` 通过 55 passed, 3 skipped；`./scripts/harness-check.sh` 通过 0 warnings；`git diff --check` 通过。

### 2026-06-13 - Direct Windows OpenSSH Backend 完成

- 新增 `F-022 Remote Runner Windows Agent PowerShell Backend` 并归档任务合同。
- 机器记录新增 `platform`、`backend`、`shell` 字段；旧机器默认 `linux / ssh-tmux / bash`，direct Windows 默认 `windows / windows-agent / pwsh`。
- 新增 `remote-runner machine configure-platform`，可在不重填凭据的情况下修正既有机器的 OS/backend/shell。
- 新增 `remote_runner/windows_agent.py` 和 `windows-agent` backend：通过 SSH/SFTP 上传 Python agent，用用户级 Windows Scheduled Task 启动持久 `pwsh`，通过 JSON request/result 文件执行 wait-mode 命令并维护 transcript。
- `session exec --mode background` 对 Windows backend 明确拒绝；P0 只承诺持久 wait-mode exec、send/read、destroy、file put/list/get 和 run once。
- 文档同步 README、Skill、Requirements、platform support、API、getting-started、MVP spec 和 launch acceptance suite，明确 direct Windows 是当前支持路径，Windows/WSL startup/path mapping 只是兼容输入。
- 验证：py_compile 通过；MVP 测试 39 passed；默认真实集成入口 2 skipped；launch suite 2 passed, 1 skipped；完整 pytest 62 passed, 4 skipped；harness-check 通过；git diff --check 通过；direct Windows opt-in 真实测试 1 passed, 1 skipped，覆盖 persistent PowerShell 状态保持、transcript、文件传输、run once 和 cleanup。

### 2026-06-19 - stale tmux session recovery 完成

- 诊断 configured Linux/tmux machine 历史状态，发现多个本地 `active`/`busy` session 与 `running` command 残留；远端对应 tmux session 已不存在，但远端 command status 文件仍停在 `running`。
- 新增 backend `terminal_exists`，用于判断 Linux/tmux 和 Windows agent terminal 是否仍存在。
- `session command show/wait` 遇到 running command 但 tmux session 已消失时，改为返回 `failed`，写入解释性 `error`，避免 agent 无限等待。
- `session show/exec/destroy` 会恢复 stale `active_command`：清除 `busy`、落一条 failed command record，并把不可用 session 标为 `lost`；后续 `session exec` 会拒绝非 active session。
- configured Linux/tmux machine 新鲜压力自测通过：大量 stdout 截断、12 秒静默 wait、后台命令轮询/wait、最终 exec、cleanup 和 destroy 均正常。
- 验证：py_compile 通过；`python3 -m pytest tests/test_remote_runner_mvp.py -q` 41 passed；默认真实集成入口 2 skipped；真实历史 stale command/session 已按预期收敛。
