<!--
职责：记录会影响后续 agent 决策的重要选择及其理由。
边界：不要记录每次小改动、聊天摘要或可从代码直接看出的事实。
-->

# 决策日志

## 记录规则

重要决策必须写明：日期、决策、原因、否决方案、后续约束。

## 决策

### 2026-05-07 - 项目灯塔从 SEEDRunner 调整为 Remote Runner

- 决策：项目长期边界是本地轻量远程机器操作 CLI，工作名 Remote Runner，而不是 SEED 实验自动化工具或科研专用工具。
- 原因：用户明确指出本质是提供一套便捷操控远程机器的 CLI 接口；实验、科研、运维都只是上层场景。
- 否决方案：继续把 research、SEED、sshfs、tmux 或“一键完成 SEED 实验”当作项目核心定义。
- 后续约束：所有目标、需求和 API 文档必须区分目标产品与当前 `seed-runner` 原型。

### 2026-05-07 - MVP 可用性优先于完美安全隔离

- 决策：MVP 允许本地明文配置作为起点，但必须避免在命令输出、日志、报告和 handoff 中泄露凭据。
- 原因：第一版核心体验是快速配置、快速连接、快速执行和清晰排障；过早引入钥匙串、守护进程和权限隔离会阻塞闭环。
- 否决方案：把系统钥匙串、本地加密、企业认证或 daemon 隔离作为 MVP 前置条件。
- 后续约束：安全承诺必须精确，不能宣称抵御拥有同一系统用户 shell 权限的恶意 Agent。

### 2026-05-07 - 采用 repo-native harness 管理目标、状态和验证

- 决策：使用仓库内 harness 保存指令、状态、验证、决策、质量和交接。
- 原因：即将“大刀阔斧改革”，必须先让核心灯塔、任务状态和验证门禁跨会话可恢复，避免目标漂移和重复推翻。
- 否决方案：只依赖聊天上下文、单个巨型 `AGENTS.md` 或外部 strategy 文档。
- 后续约束：后续任务默认 WIP=1；`passing` 必须有 evidence；会话结束必须更新 handoff。

### 2026-05-07 - 目标核心移除挂载机制

- 决策：Remote Runner 第一轮 MVP 不以 mount/sshfs 为核心机制，改为严格本地状态维护、直接远程命令执行和显式文件传输。
- 原因：很多远程机器不方便或不允许 FUSE/sshfs、反向 SSH、挂载权限或长期挂载；挂载会把状态来源变得不清晰。
- 否决方案：继续把当前 `seed-runner mount create` 扩展为目标 API。
- 后续约束：`seed-runner mount/session` 仅作为 legacy 原型兼容路径；目标 API 必须提供 `file put/get/list`。

### 2026-05-11 - 文件传输路径采用显式前缀映射

- 决策：当命令执行路径与 SFTP 可见路径不一致时，机器配置保存显式 `path_mappings`，由 `file put/get/list` 在 backend 前应用。
- 原因：Windows OpenSSH + WSL 机器中，命令侧路径可能是 `/mnt/c/...`，SFTP 侧路径可能是 `C:/...`；自动猜测容易误伤真实文件系统边界。
- 否决方案：要求用户每次手动传 SFTP 路径，或在 MVP 中做自动路径发现。
- 后续约束：transfer 记录和 artifact manifest 保留用户输入的命令侧路径；真实验证只能在用户明确允许的远程目录内写入和删除测试文件。

### 2026-07-17 - 核心收敛为本地 tmux 持久终端

- 决策：Remote Runner 只管理本机 macOS/Linux 上的 tmux Session 和 raw transcript；SSH、
  `su`、远端 tmux、Slurm 等由 Agent 像人类一样在 shell 中显式操作。Instance 只挂载透明的
  bootstrap hook，不形成 backend。
- 原因：真实产品目标是为 Agent 提供清楚、持久、可由人类共同 attach 的 shell；原先把远端
  tmux、交互 SSH、Windows 管道、batch exec 和文件传输塞入 Session，造成 Interface 语义不等价、
  transcript 同步阻塞和大量条件分支。
- 否决方案：继续维护 `ssh-tmux`、`openssh-pty`、`windows-agent` 三套 Session 实现；由 RR 推断
  prompt/busy/completion；自动在 SSH 后创建远端 tmux；把 batch/file 协议塞入 live terminal。
- 后续约束：V4 不兼容旧 state、Session、CLI 或 backend；只保留本地 tmux Terminal Module、
  Instance bootstrap Module 和 State Module。远端连接断开后的恢复或任务持久化由使用 Agent 决定。
  本决策取代此前关于 machine/file/run 产品边界、seed-runner 兼容和多 backend 演进的约束；
  旧条目只保留为历史背景。
