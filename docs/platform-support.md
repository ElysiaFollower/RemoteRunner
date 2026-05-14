# Platform Support

Remote Runner 当前采用 Linux-first 支持策略。

## 当前主支持平台

MVP 主支持平台是通过 SSH 访问的 Linux 机器，要求远端具备：

- 可用的 POSIX shell / `bash`
- `tmux`，用于持久 session backend
- SSH/SFTP，用于命令通道和显式文件传输
- 一个用户明确授权的可写工作目录

当前真实集成测试以 Linux/SSH 机器为准。上线判定应优先看 Linux/SSH opt-in 测试是否通过。

## Windows / WSL 状态

Windows OpenSSH + WSL 不是当前主支持平台。

历史实现验证过两类 Windows/WSL 兼容能力：

- `startup_commands`：SSH 登录后先执行 `wsl` 等预置指令。
- `path_mappings`：命令侧 `/mnt/c/...` 路径和 SFTP 侧 `C:/...` 路径之间的显式映射。

这些能力保留在机器配置和历史测试中，但当前持久 session backend 不支持依赖
`startup_commands` 的机器。原因是当前 backend 在 `session create` 时需要直接在远端 Linux shell
里创建并控制 `tmux` session；Windows OpenSSH 先进入 WSL 的交互链路尚未被设计成稳定、可恢复、
可销毁的持久 session backend。

因此：

- 可以继续保留 Windows/WSL 机器配置作为兼容/未来 backend 输入。
- 不应把 Windows/WSL 作为当前上线主路径。
- 不应承诺 Windows/WSL 支持 `session create/exec/send/read/destroy` 的持久 shell 语义。
- 若后续要支持 Windows/WSL，应作为单独 backend 任务设计和验收。

## 不是长期产品边界

Linux、SSH、tmux、SFTP 都是当前 MVP backend 选择，不是永久产品边界。长期产品抽象仍然是：

```text
machine -> session -> command/logs/file/artifacts
```

当未来引入 screen、native SSH shell、Windows/WSL backend、container backend 或调度 backend 时，公开
CLI 应尽量保持 session 抽象稳定。
