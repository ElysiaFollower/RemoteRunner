# Remote Runner Overview

## 核心灯塔

Remote Runner 是一个安装在本地的轻量级远程机器操作 CLI。它把远程机器包装成可查询、可诊断、可调用的稳定资源，让人类或 Agent 能创建会话、在远程目录执行命令、显式传输文件、读取结构化输出、保存日志、管理产物，并在此基础上支撑实验、科研、运维、训练、benchmark 等上层工作流。

项目不以 research、SEED、SSH、tmux 或 sshfs 为边界。远程交互接口才是核心；research/SEED/operations/model-training/benchmark 都是 profile 或 use case。

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
- Machine：用户在本地登记的远程机器配置，包含 host、port、user、auth type、credential reference/default cwd。
- Session：使用者面向的远程执行上下文，包含 session id、machine id、cwd、状态、命令历史和日志位置；不等同于 tmux session。
- Command result：一次远程命令的结构化记录，至少包含命令、cwd、stdout、stderr、exit code、开始/结束时间、耗时和日志路径。
- Transfer：一次显式文件上传、下载或远程列表操作，必须写入本地状态。
- Artifact：远程运行产生并被本地记录或回收的文件、目录、manifest 或证据。
- Profile/use case：建立在通用远程会话层之上的领域流程，例如 `operations`、`seed`、`paper-reproduction`、`model-training`、`benchmark`。

## 当前事实与目标事实

当前事实：

- 主要实现仍在 `seed_runner`，用于保持 legacy 原型兼容。
- 目标包名 facade 是 `remote_runner`，`remote-runner` console script 指向 `remote_runner.cli:main`。
- Remote Runner 公共模块也可通过 `remote_runner.remote_*` facade 导入；当前仍委托 `seed_runner.remote_*`。
- legacy 原型命令仍是 `seed-runner`。
- 当前原型依赖 `.env.machines`、SSH key、tmux、sshfs 和 mount/session 流程。
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
