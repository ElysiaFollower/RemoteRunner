# Remote Runner Overview

## 核心灯塔

Remote Runner 是一个安装在本地的轻量级远程机器操作 CLI。它把远程机器包装成可查询、可诊断、可调用的稳定资源，让人类或 Agent 能创建会话、在远程目录执行命令、显式传输文件、读取结构化输出、保存日志、管理产物，并在此基础上支撑实验、科研、运维、训练、benchmark 等上层工作流。

项目不以 research、SEED、SSH、tmux 或 sshfs 为边界。远程交互接口才是核心；research/SEED/operations/model-training/benchmark 都是 profile 或 use case。

当前 MVP 支持三条持久 session backend：Linux/SSH + tmux、direct Windows OpenSSH + Windows agent + PowerShell 7，以及本机 tmux 托管的 OpenSSH 交互 PTY。Windows + WSL 的 `startup_commands` 路径仍只是兼容历史和未来 backend 输入；详见 `docs/platform-support.md`。

## 一句话定义

Remote Runner turns remote machines into local, agent-friendly sessions with structured command results, logs, and artifacts, while keeping normal workflows away from repeated credential and connection-detail handling.

中文定义：

> Remote Runner 是一个本地轻量级远程机器操作 CLI，让用户把远程机器配置成稳定接口；使用者不需要反复处理 SSH 凭据和连接细节，只需要通过 CLI 创建会话、执行远程命令、读取输出并管理日志和产物。

## 用户与痛点

目标用户是需要反复操控远程机器的人，包括做实验、科研复现、模型训练、benchmark、远程开发、系统编译、服务排障和运维任务的人。

核心痛点：

- 用户或 Agent 不应该在正常任务流里反复处理密码、私钥内容、跳板机细节和连接字符串。
- 使用者经常把上下文和行动预算浪费在 SSH、tmux、挂载、同步和日志查找上。
- 远程命令输出、退出码、时间戳、日志和产物分散，导致中断后难恢复、结果缺证据。
- SEEDRunner 原型验证了需求，但把项目边界绑在 SEED、research、sshfs 或 tmux 上会限制长期方向。

## 范围

MVP 必须做：

- 本地机器配置和连接诊断。
- 机器列表、机器详情、会话创建、会话查询、命令执行、日志查询和会话销毁。
- `session exec --json` 返回 stdout、stderr、退出码、时间戳、耗时和本地日志路径。
- 显式文件传输：`file put/get/list --json`，不依赖 sshfs、FUSE、反向 SSH 或长期挂载。
- 本地状态目录保存机器、会话、命令历史、日志和后续产物索引。
- 凭据不出现在 stdout、stderr、日志、报告和 handoff 中。

MVP 不优先做：

- 完美凭据隔离、系统钥匙串、守护进程、权限隔离或企业认证集成。
- GUI、Web 控制台、MCP 服务、多 Agent 调度。
- Slurm/Kubernetes/Docker/实验追踪平台替代。
- 特定领域的完整自动化平台，例如完整科研报告生成或完整运维平台。

## 核心术语

- Remote Runner：目标产品和架构边界；工作名可后续再改。
- `seed-runner`：当前可运行原型 CLI，SEED-focused，仍使用 mount/session 兼容接口。
- Machine：用户在本地登记的远程机器配置，包含 host、port、user、auth type、credential reference/default cwd、platform、backend 和 shell。
- Session：使用者面向的持久终端上下文，包含 session id、machine id、cwd、状态、append-only transcript 和日志位置；不等同于 tmux session。基础契约是原样 `send` 和增量 `read`；具备真实 terminal control 的 backend 还提供 `interrupt`/`Ctrl-C` 恢复。结构化 `session exec` 是部分 backend 的兼容接口，不得反向定义 session 为 in-band RPC 或 batch runner。
- Command result：一次远程命令的结构化记录，至少包含命令、cwd、stdout、stderr、exit code、开始/结束时间、耗时和日志路径。
- Transfer：一次显式文件上传、下载或远程列表操作，必须写入本地状态。
- Artifact：远程运行产生并被本地记录或回收的文件、目录、manifest 或证据。
- Profile/use case：建立在通用远程会话层之上的领域流程，例如 `operations`、`seed`、`paper-reproduction`、`model-training`、`benchmark`。

## 当前事实与目标事实

当前事实：

- Remote Runner 目标实现位于 `remote_runner`，`remote-runner` console script 指向 `remote_runner.cli:main`。
- `seed_runner.remote_*` 仅作为 legacy compatibility wrapper，继续 re-export `remote_runner.*` 公开对象。
- legacy 原型命令仍是 `seed-runner`。
- 当前主实现不依赖 mount；持久 session backend 包含 Linux/SSH + tmux、Windows OpenSSH + windows-agent/pwsh，以及本机 tmux + OpenSSH PTY。
- 当前 `session create` 通过 SSH 执行 `tmux new-session`，创建新的 Remote Runner session 和新的 tmux session；后续 `send/read/interrupt/destroy` 控制该 tmux session，结构化 `exec/background` 则走独立 SSH batch transport。Remote Runner 不持久化登录某个 user account；但如果远端该用户已有 tmux server 进程，新的 tmux session 可能由这个既有 tmux server fork 出 shell，而不是直接由本次 SSH 登录进程 fork。服务器侧组成员或登录策略变化后，公开重启路径是 `session destroy` 后重新 `session create`，但只要既有 tmux server 仍带着旧进程凭据存活，该路径不保证刷新 Unix 补充组。
- 当前提供 `machine restart-tmux-server` 作为 Linux/tmux backend 维护接口：它通过 direct SSH 检查 active Remote Runner tmux session 和远端 tmux session 列表，只有确认没有 session 依赖该 server 后才执行 `tmux kill-server`，用于刷新后续 tmux-backed shell 的进程授权上下文。
- 当前 Windows backend 使用用户级 Scheduled Task 启动远端 Python agent，由 agent 维护持久 PowerShell 7 (`pwsh`) 子进程；P0 支持 wait-mode session exec、send/read/destroy、file 和 run once，不支持 background mode。
- 当前 tmux-backed session 用 `pipe-pane` 形成 append-only transcript；远端 transcript 按 byte cursor 增量读取并保留跨块 UTF-8 尾字节。live pane 只承载 `send/read/interrupt`，不承载隐藏 exec 或 file-transfer protocol。`openssh-pty` 拒绝结构化 exec 和所有 file 操作；`ssh-tmux session exec/background` 与 `run once` 走独立 SSH batch transport。
- legacy `seed-runner` 原型依赖 `.env.machines`、SSH key、tmux、sshfs 和 mount/session 流程。
- 旧 API 记录在 `docs/reference/SEED_RUNNER_API.md`。

目标事实：

- 目标 CLI 工作名是 `remote-runner`，目标包名是 `remote_runner`。
- 目标一级对象是 machine、session、command log、transfer 和 artifact。
- 默认状态根应迁移到 `~/.remote-runner/`。
- 目标 API 记录在 `docs/reference/REMOTE_RUNNER_API.md`。

## 冲突裁决

当文档或实现出现冲突时，按以下规则处理：

1. 产品灯塔以本文件和 `docs/architecture/core-lighthouse.md` 为准。
2. MVP 需求以 `REQUIREMENTS.md` 为准。
3. 目标 CLI 合同以 `docs/reference/REMOTE_RUNNER_API.md` 为准。
4. 当前可运行原型以代码、测试和 `docs/reference/SEED_RUNNER_API.md` 为准。
5. 若目标合同和当前代码不同，不要修改叙述来掩盖差异；应明确标为迁移缺口，并进入 `harness/feature_list.json` 或任务计划。

## 开发顺序

1. 统一灯塔、需求、术语和 harness 状态。
2. 实现机器配置和 `machine list/show/doctor/remove`。
3. 重建 session create/list/show/exec/logs/destroy 合同。
4. 加入显式 file put/get/list，不把 mount/sshfs 作为核心机制。
5. 加入凭据脱敏、稳定错误码、超时、恢复和 artifact manifest。
6. 在通用远程交互层之上添加 operations、SEED、research 等 profile。
