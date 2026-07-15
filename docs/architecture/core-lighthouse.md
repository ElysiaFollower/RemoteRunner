# Core Lighthouse

## 不可变目标

Remote Runner 的不可变目标是：

```text
本地轻量工具 -> 远程机器配置 -> 可用会话 -> 远程目录命令执行 -> 显式文件传输 -> 结构化输出/日志/产物 -> 上层工作流
```

任何架构、API 或实现选择都必须服务这条链路。远程交互接口是核心，不是 research 或 SEED 的附属能力。

## 不可混淆的边界

- Remote Runner 不是 SEEDRunner 改名。SEEDRunner 是原型，SEED 是 profile。
- Remote Runner 不是 Research Runner。科研是重要应用场景，但不是产品边界。
- Remote Runner 不是 SSH wrapper。SSH 是 backend，价值在可用、可恢复、可审计的远程会话接口。
- Remote Runner 不是密码管理器。MVP 可以使用本地明文配置，但不得在正常工作流中暴露凭据。
- Remote Runner 不是调度平台。Slurm、Docker、Kubernetes、tmux、sshfs、rsync 都是可替换实现。
- Remote Runner 不是挂载工具。mount/sshfs 只属于 legacy 原型或未来可选 backend，不是核心机制。
- Remote Runner 第一层不是报告生成或运维平台。报告、runbook 和验收必须建立在可靠命令记录、日志和产物之上。

## 分层

1. 机器层：本地登记远程机器，支持查询、展示、诊断和删除。
2. 会话层：为机器和远程目录创建可恢复执行上下文。
3. 命令层：执行命令并返回结构化结果，保存完整日志。
4. 文件与产物层：显式上传、下载、列出文件，记录 transfer history 和 artifact manifest。
5. Profile 层：operations、SEED、paper reproduction、model training、benchmark 等领域流程。

低层不稳定时，不允许把复杂度堆到高层 prompt、报告模板或运维脚本上。

## MVP 安全承诺

MVP 的安全承诺是精确且有限的：

- 正常工作流不需要反复处理 SSH 凭据和连接细节。
- 工具不把密码打印到 stdout、stderr、日志、报告或 handoff。
- 配置默认放在用户 home 下的本地状态目录，而不是项目仓库。

MVP 不承诺抵御拥有同一系统用户 shell 权限的恶意 Agent。更强隔离需要后续守护进程、权限策略、钥匙串或企业访问工具。

## 实现约束

- 当前原型可以继续作为兼容层存在。
- 当前 MVP 支持 Linux/SSH + tmux、direct Windows OpenSSH + windows-agent/pwsh、本机 tmux + OpenSSH PTY 三条持久 session backend；Windows/WSL `startup_commands` 只作为兼容历史和未来 backend 输入。
- 大规模迁移前必须保持 legacy `seed-runner` 行为可验证。
- 新 `remote-runner` API 落地时，应优先增加兼容入口或迁移文档，而不是直接破坏已有测试。
- 公共命令必须面向非交互使用，优先提供 `--json`。
