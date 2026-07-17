<!--
职责：定义 Local Terminal V4 从隔离分支切换到本机生产环境的唯一操作合同。
状态：已按合同完成并验证；旧 state 与旧 Skill 备份保留。
-->

# Local Terminal V4 Cutover

## 目标

把已经验证的 `codex/rr-terminal-observation-v3` 整分支 fast-forward 到主仓库，完成旧
`seed-runner` editable 安装到 `remote-runner 0.4.0` 的包名交接，并把仓库内 canonical
`SKILL.md` 发布为 global Skill。切换后用真实默认 state 与默认 tmux server 做最小生产 smoke。

## 不变量与停止条件

- 用户明确下令之前只允许只读预检和隔离 worktree 内的准备修改。
- 切换前必须确认没有 Agent 或人类仍在使用旧 Remote Runner；工具不会尝试猜测这一点。
- 主仓库与开发 worktree 都必须 clean，且主仓库 HEAD 必须是开发分支祖先；只允许
  `git merge --ff-only`，不 cherry-pick、不 force、不改写历史。
- 旧 `~/.remote-runner` 只归档改名，不读取、不迁移、不删除。新 V4 必须从 fresh state 开始。
- 现有 global Skill 必须先备份到 `/Users/ely/.agents/backups/remote-runner/`，即 skills
  discovery 目录之外；发布时只复制仓库内 canonical `SKILL.md`。
- 任一前置事实与本合同记录不一致时停止，不把意外状态覆盖成预期状态。

## 已确认的切换前基线

- stable 主仓库：`/Users/ely/workspace/research/agent/RemoteRunner`，HEAD `f65ee33`。
- V4 worktree：`/Users/ely/workspace/research/agent/RemoteRunner-terminal-v3`，分支
  `codex/rr-terminal-observation-v3`；stable HEAD 是该分支祖先。
- 当前系统包：`seed-runner 0.1.0` editable 指向 stable 主仓库；不存在
  `remote-runner` distribution metadata。
- 当前 console script：`/Users/ely/miniconda3/bin/remote-runner`；从源码目录外 import
  指向 stable 主仓库。
- 旧 state `/Users/ely/.remote-runner` 存在，权限为 owner-only；预检没有读取其内容。
- 当前 global Skill 是普通文件，SHA-256 为
  `c7cc97fa715882b08b493e573f6f7bac05d44bc7c95b19179092d3dc5e6cd6a5`，与 stable 和 V4
  仓库内版本都不同，因此不能把 Git 中旧 `SKILL.md` 当作回滚副本。

这些值是异常检测锚点，不是永久事实。正式执行前必须重新读取；任何变化都要先解释。

## 正式执行顺序

1. 重新运行完整门禁，确认两个 worktree clean，并核验上述 ancestry、安装归属和 Skill hash。
2. 生成同一个 UTC 时间戳；将旧 state 改名为带该时间戳的 sibling 目录，并把现有 global
   Skill 复制到 `/Users/ely/.agents/backups/remote-runner/<timestamp>/`。
3. 在 stable 主仓库执行 `git merge --ff-only codex/rr-terminal-observation-v3`。这是整分支
   切换；不得只 cherry-pick 最后一个提交。
4. 先卸载 `seed-runner` metadata，再从 stable 主仓库执行
   `python3 -m pip install --no-deps -e .`。顺序不可反转，因为两个 distribution 都声明同名
   `remote-runner` console script。
5. 用部署复制把 stable 主仓库 `SKILL.md` 原样发布到
   `/Users/ely/.agents/skills/remote-runner/SKILL.md`；不得手工维护第二份内容。
6. 从源码目录外核验 distribution 名称、版本、import path、console script、CLI help 和 global
   Skill hash。`seed-runner` metadata 必须消失，import 必须指向 stable 主仓库。
7. 使用默认 state/default tmux 创建唯一命名的本地 Session，发送一行可识别的无副作用命令，
   从 tail 看到输出与恢复后的 prompt，再 show、destroy、purge。不得连接远端或复用已有名字。
8. 重跑 harness 与聚焦 smoke，记录实际 archive 路径和证据；F-031 passing 后归档本合同。

## 失败回退

- 在旧 state 归档前失败：没有生产状态变化，修正原因后重新预检。
- 在 V4 state 创建后失败：先把失败的 V4 state 改名保留，再原名恢复旧 state；不覆盖任一目录。
- global Skill 从 `/Users/ely/.agents/backups/remote-runner/<timestamp>/` 恢复。
- runtime 回退时先卸载 `remote-runner`。旧提交 `f65ee33` 仍是新 main 的祖先，可临时创建 detached
  worktree 并用 `python3 -m pip install --no-deps <old-worktree>` 安装旧 `seed-runner`，验证后再
  删除该临时 worktree。不要让 editable 安装指向随后会被删除的目录。
- 不自动 reset 或重写 main。若生产 smoke 失败但 Git 已 fast-forward，先恢复可用 runtime/state/
  Skill，再根据失败原因决定修复 V4 还是用显式 revert 提交恢复主分支。

## 完成标准

- stable main、系统 import、console script、distribution metadata、global Skill 和 fresh V4 state
  指向同一 V4 合同。
- 生产 smoke 完成且测试 Session 已 destroy/purge；没有临时 tmux、测试进程或临时 worktree。
- 旧 state 与旧 global Skill 备份路径已记录且未删除。
- feature、progress、quality、handoff 和本合同归档状态与实际部署一致。

## 执行结果

- 用户明确授权后重新运行完整门禁；代码、Skill、worktree 和 fast-forward ancestry 通过。
- 预检发现 global Skill 在准备后被外部维护，SHA-256 从记录的 `c7cc97f...` 变为
  `4a6d760...`。切换因此暂停并只读审计；变化仍只服务 V4 已删除的旧 API。实际覆盖前版本已
  原样备份，没有静默丢失或混入 V4。
- 同一 UTC 时间戳 `20260717T113718Z` 下，旧 state 归档为
  `/Users/ely/.remote-runner.pre-v4-20260717T113718Z`，旧 Skill 归档为
  `/Users/ely/.agents/backups/remote-runner/20260717T113718Z/SKILL.md`。
- main 从 `f65ee33` 整分支 fast-forward 到 `0799092`；卸载 `seed-runner 0.1.0` 后安装
  `remote-runner 0.4.0` editable，import 与 console script 指向 stable 主仓库。
- canonical Skill 以原子部署复制发布，global/source SHA-256 同为 `c2130e7...`。
- 默认 state/default tmux production smoke 验证初始 prompt、命令回显、真实输出
  `RR_V4_PRODUCTION_SMOKE=42`、prompt 恢复和 show 元信息；测试 Session 已 destroy/purge。
- 切换后再次通过 34 tests、Black、Flake8、mypy、harness、init、diff、Skill validation 和
  distribution/import/CLI/backup/state 一致性审计。
