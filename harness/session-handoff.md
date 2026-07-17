<!-- 职责：让下一个 Agent 在三分钟内恢复当前 V4 任务。 -->

# Session Handoff

## 仓库状态

- Local Terminal V4 已在隔离 worktree `/Users/ely/workspace/research/agent/RemoteRunner-terminal-v3`
  完成实现，分支 `codex/rr-terminal-observation-v3`。
- 该分支从 main 依次保留 V3 设计过程提交 `eee5aa5`、`3afef80`，最终 V4 提交完全取代其
  运行时设计。Cutover 应合并整个分支，不要只 cherry-pick 最后一个相对提交。
- 主仓库 `/Users/ely/workspace/research/agent/RemoteRunner` 仍是 `main`，稳定 editable import 仍
  指向主仓库；本任务没有安装、合并或发布 global Skill。
- V4 是不兼容重写：生产包只剩 `remote_runner`；旧 remote/Windows/batch/file/run/artifact 和
  `seed_runner` 路径已删除。
- F-030 已标为 passing，任务合同已归档；F-031 是唯一 active WIP，切换合同位于
  `plans/active/2026-07-17-local-terminal-v4-cutover.md`。

## 验证证据

最终门禁已运行：

```bash
python3 -m pytest -q
python3 -m black --check remote_runner tests
python3 -m flake8 remote_runner tests --ignore=E203,W503,E501
python3 -m mypy remote_runner
./scripts/harness-check.sh
git diff --check
```

结果：34 passed；Black 16 files；Flake8 通过；mypy 9 source files；harness 0 warnings；
`init.sh` 与 diff check 通过。fresh state 的 128-way 初始化压力用例另连续运行 10 轮。

最终隔离 wheel smoke 已完成：构建 `remote-runner 0.4.0` wheel，在临时 venv 中非 editable
安装，从源码目录外使用独立 tmux socket 完成 create/send/tail/destroy。完整 evidence 在 F-030。

Cutover 准备改动后再次运行同一质量门禁，结果仍为 34 passed、Black 16 files、Flake8、mypy
9 source files、harness/init/diff 通过；重新构建 wheel 并在全新临时 venv、state 和 tmux 中完成
create/send/tail/show/destroy/purge。待发布 Skill 通过 quick validation，canonical SHA-256 为
`c2130e7061e80d63f025432ed2fd4dad0c5c62d1cd62b871f180d153740fff2c`。
第一次 smoke driver 因使用 zsh 只读变量名而在产品检查通过途中退出，并留下自己的唯一 socket
tmux server；该 server 已精确 kill，driver 修正后从头通过，最终进程检查无残留。

追加真实 SSH smoke：使用临时 state/独立 tmux socket 登录一台已配置的高延迟 Linux target，
验证双层 prompt、远端 `cd`/环境变量连续性、Linux 输出、延时前台命令和 `exit` 回本地 prompt。
远端只执行只读探针；本地测试 Session 已 destroy/purge，tmux server 与临时 state 已删除。

## 安全与隐私边界

- 所有测试使用唯一 `REMOTE_RUNNER_TMUX_SOCKET` 与 pytest 临时 state；fixture finally
  `kill-server`。没有连接真实机器或读取真实 RR state。
- 未运行 `pip install -e`；wheel 只安装进临时 venv，并在退出时删除。
- `send --stdin` 可避免秘密进入 process argv；RR 不保存或返回输入。密码是否出现在 transcript
  由真实 TTY echo/no-echo 决定。
- evidence、日志和仓库内没有真实 host、密码、私钥或业务 transcript。

## 仍未完成

- 尚未在 Linux RR host/Python 3.10 上实跑；真实 Linux SSH target 已验证，但两者不能混称。
  host 兼容性当前由 Python 3.10 mypy 配置与无 macOS 专用生产分支支持。
- 尚未合入或切换主仓库、editable runtime、旧 package metadata 或 global Skill；这是用户
  明确授权后才执行的破坏性 cutover。

## Cutover 准备状态

- stable main `f65ee33` 是 V4 分支祖先，可整分支 `--ff-only`；不得只 cherry-pick 最后提交。
- 当前系统仍是 `seed-runner 0.1.0` editable，import 与 console script 均指向 stable 主仓库；
  切换时必须先卸载旧 distribution，再安装 `remote-runner 0.4.0`。
- `/Users/ely/.remote-runner` 只确认存在，未读取；切换时归档改名，不迁移、不删除。
- global Skill 与 stable/V4 仓库版本都不同，必须在 skills discovery 目录之外独立备份后，才可
  用 V4 canonical `SKILL.md` 完整替换。
- 待发布 Skill 已补充负触发边界：开发/调试 Remote Runner 本身、普通本地 shell 和概念性 SSH
  问题不触发。正式切换的停止条件、执行顺序、生产 smoke 与失败回退均在 active 合同中。

## 下一步最佳动作

1. 等待用户明确下令，期间不得修改 stable runtime、真实 state 或 global Skill。
2. 下令后按 `plans/active/2026-07-17-local-terminal-v4-cutover.md` 重新预检并执行，不临场改顺序。
3. production smoke 与回归通过后更新 evidence、归档合同并报告实际备份路径。

## 常用命令

```bash
cd /Users/ely/workspace/research/agent/RemoteRunner-terminal-v3
./init.sh
git status --short
python3 -m pytest -q
```
