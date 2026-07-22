<!-- 职责：让下一个 Agent 在三分钟内恢复当前 V4 状态。 -->

# Session Handoff

## 仓库状态

- F-032 已同步到 main、系统 editable distribution 和 global Skill，当前版本为 0.5.0。
- 新 CLI 是 `remote-runner session register --tmux-session <tmux-name> [--name <rr-name>]`。
  它非拥有式接入精确的单 pane 本地 tmux；destroy 仅注销 RR recorder，保留外部 tmux。
- Local Terminal V4 已完整同步到主仓库 `main`；隔离实现分支
  `codex/rr-terminal-observation-v3` 的切换基点为 `0799092`。
- 系统 distribution 是 `remote-runner 0.5.0` editable，import 与 console script 均指向
  `/Users/ely/workspace/research/agent/RemoteRunner`；旧 `seed-runner` metadata 已卸载。
- global Skill 已由主仓库 canonical `SKILL.md` 原子替换，SHA-256 为
  `7dea1164754e378d896385ce6620dac8952bd672c7cc0b8b835d45785811ab7d`。
- V4 默认 state 已 fresh 初始化；当前包含正常业务 Session。F-032 production smoke 使用随机命名
  测试对象并已 destroy/purge，前后业务 tmux/state 集合一致。
- F-030、F-031、F-032 均为 passing，任务合同均已归档，当前无 active WIP。

## 验证证据

- F-032 完整测试 40 passed，其中真实隔离 tmux 10 passed；Black 16 files、Flake8、mypy 9 source
  files、harness/init/diff 和 canonical Skill validation 全部通过。
- 当前源码复制到临时目录后构建 0.5.0 wheel，非 editable 安装并从源码目录外完成
  register/send/tail/destroy；外部 tmux 保持存活，RR recorder 已移除。所有测试使用独立 socket 和
  临时 state。
- 用户授权后 main 从 `14fae03` fast-forward 到 `30ba4d0`，editable metadata 更新为 0.5.0，
  canonical Skill 原子发布。默认环境 production smoke 完成 register/send/tail/show/destroy/purge；
  RR destroy 后外部 tmux 仍存活，最终清理后既有 tmux/state 集合逐项不变。
- 旧 state 未读取、未迁移、未删除，归档在
  `/Users/ely/.remote-runner.pre-v4-20260717T113718Z`。
- 切换前 global Skill 在准备后被外部维护过；实际覆盖前版本 SHA-256 为 `4a6d760...`，已原样
  备份到 `/Users/ely/.agents/backups/remote-runner/20260717T113718Z/SKILL.md`。审计确认该变化
  仍只涉及 V4 已删除的旧 machine/backend/run/file 工作流，因此没有混入 canonical V4 Skill。
- main 从 `f65ee33` 整分支 fast-forward 到 V4；没有 cherry-pick、force 或历史改写。
- 默认 state/default tmux production smoke 创建唯一 Session，看到初始 zsh prompt；发送
  `printf` 后 transcript 同时包含真实命令回显、`RR_V4_PRODUCTION_SMOKE=42` 和恢复后的 prompt；
  `show` 的状态、时间和 cursor 正确。测试 Session 随后 destroy/purge，列表为空。

### 最终门禁

```bash
python3 -m pytest -q
python3 -m black --check remote_runner tests
python3 -m flake8 remote_runner tests --ignore=E203,W503,E501
python3 -m mypy remote_runner
./scripts/harness-check.sh
./init.sh
git diff --check
```

当前 F-032 结果：40 passed；Black 16 files；Flake8、mypy 9 source files、harness/init/diff、
global Skill validation、0.5.0 wheel smoke 和默认环境 production smoke 全部通过。

切换前另已完成：fresh state 128-way 初始化压力连续 10 轮、非 editable wheel 安装 smoke、真实
高延迟 Linux SSH target 的登录/状态连续/延时命令/退出回本地 prompt 验证。

## 安全与隐私边界

- F-032 开发与 wheel 测试使用隔离 tmux/state；production smoke 只创建随机命名测试对象，未向
  既有业务 Session 发送输入。清理后既有 tmux/state 集合不变。
- 旧 state 只做同文件系统改名归档；没有读取、迁移、合并或删除其中内容。
- global Skill 覆盖前版本保存在 skills discovery 目录之外；canonical 部署过程不保留临时文件。
- production smoke 没有连接远端、写入业务目录或使用敏感输入；唯一测试 Session 已彻底 purge。
- 仓库、handoff 和测试 evidence 不包含 host、密码、私钥或业务 transcript。

## 仍未完成

- 尚未在 Linux RR host/Python 3.10 上单独实跑；当前 RR host 是 macOS、Python 3.13.12、
  tmux 3.7b。Linux SSH target 验证不能冒充 Linux host 验证。
- RR 只保证本地 tmux shell；不保证本机重启、tmux 被杀、SSH 断线或远端进程存活。
- transcript 不自动轮转或压缩；长期大输出需要使用者管理磁盘并显式 purge。
- 旧 state 与旧 Skill 备份尚未删除；这是有意保留的回退窗口，不是未完成迁移。

## 下一步最佳动作

- 正常任务直接使用已发布的 V4 Skill 和 `remote-runner session ...` Interface。
- 旧 state 与旧 Skill 备份先保留；确认无需回退后再由用户明确决定是否删除。
- 新功能开发前在 `plans/active/` 建立唯一任务合同，不恢复旧 backend 或兼容路径。

## 常用命令

```bash
cd /Users/ely/workspace/research/agent/RemoteRunner
./init.sh
remote-runner session list
remote-runner session create --name <readable-name>
remote-runner session register --tmux-session <tmux-name> --name <readable-name>
remote-runner session show --session <readable-name>
remote-runner session tail --session <readable-name>
```
