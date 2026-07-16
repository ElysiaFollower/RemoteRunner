# Remote Runner 需求文档

## 1. 项目目标

Remote Runner 要构建一个安装在本地的轻量级 CLI 工具，让用户把远程机器配置成可查询、可诊断、可调用的稳定接口。它不局限于科研：实验、开发、运维、模型训练、benchmark、远程调试等场景都应该能建立在同一套远程交互接口之上。

核心价值不是“少写 SSH 命令”，而是：

- 用户或 Agent 不需要反复处理 SSH 凭据、密钥路径、跳板机和连接细节。
- 上层使用者能通过稳定 CLI 查询机器、创建会话、执行远程命令、读取结构化输出和日志。
- 命令、退出码、时间戳、日志和产物形成可恢复、可审计的证据链。
- 科研实验闭环、SEED profile、运维 runbook、训练任务和 benchmark 都是建立在远程会话能力之上的 profile/use case。

一句话定义：

> Remote Runner 是一个本地轻量级远程机器操作 CLI，让用户把远程机器配置成稳定接口；使用者不需要反复处理 SSH 凭据和连接细节，只需要通过 CLI 创建会话、执行远程命令、读取输出并管理日志和产物。

## 2. 核心不变量

### 2.1 远程交互接口是核心

稳定抽象是：

```text
机器配置 -> 会话 -> 远程目录命令执行 -> 显式文件传输 -> 结构化输出/退出码/日志/产物
```

Research、SEED、运维、训练和 benchmark 都不能反向定义底层产品。底层只承诺把远程机器变成可操作、可观察、可恢复的本地 CLI 资源。

### 2.2 MVP 可用性优先

第一版最重要的是能快速配置、快速连接、快速执行、快速排障。安全设计要服务于可用性，而不是把 MVP 卡死在钥匙串、守护进程、权限隔离或企业认证集成上。

MVP 可以接受本地明文配置，但必须满足底线：

- 默认配置目录不在项目仓库内。
- 创建配置文件时尽量使用较严格的本地文件权限。
- 不把密码打印到 stdout、stderr、日志、报告或 handoff。
- 配置格式简单，人类可以直接理解和修改。

更强安全能力作为后续增强：系统钥匙串、本地加密存储、SSH agent、读取 `~/.ssh/config`、Teleport、Boundary、Tailscale SSH、Cloudflare Access 等。

### 2.3 本地轻量 CLI

工具运行在用户自己的电脑上。第一版优先做 CLI，后续再考虑 GUI、托盘应用、本地守护进程、MCP 服务或网页控制台。

### 2.4 机器与会话是产品抽象

用户和 Agent 使用机器名、会话 ID、远程目录和命令，不直接依赖 SSH、tmux、sshfs、rsync、Slurm 或容器实现细节。

会话是产品抽象，不等于 tmux session。底层可以直接 SSH 执行，也可以用 tmux、screen、Slurm、Docker、Kubernetes 或其他机制；API 不应暴露这些 backend 语义。

### 2.5 当前平台边界

当前 MVP 支持三条持久 session backend：通过 SSH/SFTP 访问的 Linux 机器使用 `ssh-tmux` backend，direct Windows OpenSSH 机器使用 `windows-agent` backend 和 PowerShell 7；只能通过本机 OpenSSH alias 交互登录的机器可使用 `openssh-pty` backend，由本机 `tmux` 托管 `ssh -tt <alias>`。

Windows backend 要求远端可通过 OpenSSH/SFTP 访问、可启动 `python` 和 `pwsh`，并能创建用户级 Windows Scheduled Task。P0 支持 `session create/exec/send/read/tail/destroy`、文件传输和 `run once`；暂不支持 `session exec --mode background`、后台命令 stop 或 `cmd.exe` 一等 shell。

Windows OpenSSH + WSL 不是 direct Windows 主路径。仓库历史上验证过 `startup_commands` 和 `path_mappings`，可以表达“登录 Windows OpenSSH 后先运行 `wsl`，并把命令侧 `/mnt/c/...` 路径映射到 SFTP 侧 `C:/...` 路径”。这些能力保留为兼容/未来 backend 输入，但当前持久 session backend 不承诺支持依赖 `startup_commands` 的机器。

`openssh-pty` 是本地交互式 gateway 适配层，不保存密码或网关细节。机器配置保存 `ssh_alias`、`auth_type=manual`、`backend=openssh-pty` 和默认目录；`session create` 启动本地 tmux session，先接入 append-only transcript recorder，再在 pane 中可见地启动 `ssh -tt <alias>`。`session attach` 让用户手动完成登录并用 `Ctrl-b d` 脱离，之后 `session send/read/tail/interrupt/destroy` 操作同一个交互 shell。该 backend 没有独立文件通道，因此明确拒绝 `session exec`、`file put/get/list`、`run once`、后台命令和无人值守认证；不得借 live terminal 传输隐藏文件协议。

详细平台边界见 `docs/platform-support.md`。

### 2.6 上层闭环建立在远程会话之上

第一层能力：

```text
本地工具 -> 机器配置 -> 会话 -> 命令执行 -> 文件传输 -> 输出和日志
```

第二层能力：

```text
领域输入 -> 远程执行 -> 日志证据 -> 产物回收 -> 验收判断 -> 报告/运维记录/任务结果
```

如果第一层不稳定，第二层会变成脆弱的 prompt 工程或脚本拼接。

## 3. MVP 功能需求

### 3.1 机器管理

必要命令：

```bash
remote-runner machine add
remote-runner machine list
remote-runner machine show
remote-runner machine doctor
remote-runner machine remove
```

机器配置至少包含：

- `machine_id`
- `host`
- `port`
- `user`
- `auth_type`
- `password` 或 `key_path`
- `ssh_alias`（仅 `openssh-pty`）
- `platform`
- `backend`
- `shell`
- `startup_commands`
- `default_cwd`
- `path_mappings`

MVP 至少支持三种配置路径：

- 交互式添加：用户按提示输入机器名、host/IP、端口、user、认证方式、platform、password 或 key path、SSH 登录后的预置指令序列，以及预置指令执行后的默认远程目录。Windows 默认选择 `backend=windows-agent` 和 `shell=pwsh`；Linux/mac 默认选择 `backend=ssh-tmux` 和 `shell=bash`。
- OpenSSH alias 添加：用户通过 `--backend openssh-pty --ssh-alias <alias> --auth-type manual` 登记本机 OpenSSH 交互入口，不输入 host/user/password。
- 手动编辑：用户可以直接打开本地配置文件修改机器信息。

密码认证的推荐路径是隐藏交互式输入；`--password` 命令行参数只作为兼容和测试入口，不推荐用于真实凭据，因为 shell history 容易泄漏。交互式 prompt 必须写到 stderr，`--json` 的 stdout 必须保持为单个 JSON 对象。同名机器覆盖必须显式确认，不得静默覆盖已有配置，也不得删除既有 session、日志、传输记录或产物索引。

`startup_commands` 用于表达“SSH 连接成功后先按序输入哪些指令”，而不是把远程目录当成黑盒起点。例如兼容型 Windows OpenSSH 机器可以先执行 `wsl`，再把 `default_cwd` 设置为 `/mnt/c/Users/example/Desktop/SSHRunner`。已有机器可用 `machine configure-startup` 更新该字段，不需要重新输入账密。direct Windows 主路径不使用 `startup_commands`，而是显式配置 `platform=windows`、`backend=windows-agent`、`shell=pwsh`。

当命令执行路径和 SFTP 可见路径不一致时，机器配置可以显式保存 `path_mappings`。例如命令侧使用 `/mnt/c/Users/.../SSHRunner`，而 SFTP 侧使用 `C:/Users/.../SSHRunner`。`file put/get/list` 在传输前应用该映射，但传输记录和 artifact manifest 仍保留用户输入的原始远程路径。路径映射不做自动猜测，必须由用户或配置命令明确写入。

使用者必须能通过 `machine list/show/doctor --json` 查询可用机器和连接诊断结果。

### 3.2 会话管理

必要命令：

```bash
remote-runner session create
remote-runner session list
remote-runner session show
remote-runner session exec
remote-runner session send
remote-runner session read
remote-runner session tail
remote-runner session interrupt
remote-runner session logs
remote-runner session destroy
```

会话至少包含：

- `session_id`
- `name`（可选，可读短标签；`session_id` 仍是主键）
- `machine_id`
- `cwd`
- `status`
- `created_at`
- `last_command`
- `last_exit_code`
- `command_count`
- `log_dir_local`

`session create` 应支持可选 `--name`。`name` 只能包含字母、数字、`.`、`_`、`-`，
且不得以 `sess_` 开头。同一台机器上未销毁 session 的 `name` 不得重复。`session`
和 `file` 相关命令的 `--session` 参数应接受真实 `session_id` 或唯一可解析的 `name`；
歧义时必须报错，不能猜测。

### 3.3 远程命令执行

核心能力：

```bash
remote-runner session exec \
  --session sess_abc123 \
  --cwd /home/user/project \
  --cmd "pytest -q" \
  --timeout 300 \
  --json
```

返回结果至少包含：

- `session_id`
- `machine_id`
- `cwd`
- `command`
- `exit_code`
- `stdout`
- `stderr`
- `started_at`
- `ended_at`
- `duration_ms`
- `log_file_local`

命令失败时仍应返回结构化信息。非零退出码是任务失败，不应自动销毁会话。

session 的基础契约是持久终端流，而不是 RPC：`session send` 把调用者提供的文本原样写入终端并按需发送 Enter；终端中的输入和输出都进入 append-only transcript；`session read --since <cursor>` 按显式 UTF-8 byte cursor 无损读取；`session tail --bytes <n>` 只在调用者明确要求时查看有界尾部；支持真实 terminal control 的 tmux-backed backend 用 `session interrupt` 向当前前台进程发送 `Ctrl-C`。同一个 session 必须保留 `cwd`、环境变量、alias、shell function 等 shell-local state。backend 不得自动跳过、压缩或解释输出，也不得为了识别命令边界而向终端注入隐藏的 `eval`、marker、退出码 wrapper、prompt detector、shell hook 或批处理脚本。`last_input_at`、`last_output_at`、`output_idle_ms` 和 cursor 是观测元信息，不代表 busy 或命令完成。`windows-agent` 的 piped PowerShell transport 当前无法可靠发送 console interrupt，必须明确拒绝而不是伪装成功。

`send/read/tail/interrupt` 的常规返回必须保持精简，不重复 machine、cwd、日志路径和命令计数等完整 session metadata；需要完整状态时使用 `session show`。bounded read 的 next cursor 只能移动到实际返回内容末尾，不能跳过未返回区域。plain 模式只输出 terminal 文本。

一个 session 默认只有一个当前操作者。新 shell 命令发送前，Agent 应先查看 tail 并确认上一条命令结束且 prompt 已返回；交互前台程序请求的输入是例外。并行 Agent 必须使用独立 session，Remote Runner 不在一个 terminal 内提供多 Agent 调度。

`session exec` 是现有 `ssh-tmux` 和 `windows-agent` backend 的结构化兼容接口，不是 session 的基础语义。`ssh-tmux` 通过独立 direct-SSH batch transport 执行，不进入 live pane，也不读取或改变 terminal 的 cwd、环境变量、alias、function 等 shell-local state；`windows-agent` 使用其显式 request/result 通道。`openssh-pty` 在 pane 输入前拒绝。需要上传—执行—下载闭环时应使用 `run once`，它在 `ssh-tmux` 上同样直接走 batch transport，不委托给 terminal exec。

`exit`、`logout` 等关闭 shell 的输入属于 session 生命周期操作；需要关闭会话时使用 `session destroy`。独立 batch 工作不得阻塞 tmux-backed terminal 的 `send`；仅当某 backend 的结构化协议与 terminal 共享同一状态机时，才可用 busy 拒绝交错输入。

### 3.4 文件传输

必要命令：

```bash
remote-runner file put
remote-runner file get
remote-runner file list
```

要求：

- 第一版文件传输优先使用 SSH/SFTP，不要求远程机器支持 sshfs、FUSE、反向 SSH 或常驻服务。
- `file put` 将本地文件或目录上传到远程路径。
- `file get` 将远程文件或目录下载到本地路径。
- `file list` 查询远程路径的文件元数据。
- 如果机器配置了 `path_mappings`，文件传输 backend 应在调用 SFTP 前把命令侧远程路径转换为文件传输侧路径。
- 每条传输记录必须写入本地状态，至少包含 source、destination、direction、timestamp、status、size/hash if available、error if failed。

### 3.5 日志和本地状态

建议本地状态目录：

```text
~/.remote-runner/
  machines.json
  sessions/
  logs/
  transfers/
  artifacts/
  runs/
```

要求：

- 使用者可以通过 CLI 查询所有机器、会话、命令历史和日志路径。
- 状态不能只存在于聊天上下文中。
- 日志必须保留命令、输出、退出码和时间戳。
- 传输历史必须保留方向、源、目标、状态和失败原因。
- 输出可截断，但完整内容必须落到日志文件。

### 3.6 文件与产物

MVP 第一阶段不做复杂同步系统，但必须支持显式文件传输：

- 推送输入目录到远程工作目录。
- 拉回产物目录到本地状态目录。
- 生成 artifact manifest。
- 关联命令、日志和产物。

sshfs 和 mount 不是目标核心机制。它们可以保留为 legacy 原型或未来可选 backend，但不应成为 MVP 前提。

### 3.7 通用 Run 闭环

必要命令：

```bash
remote-runner run once
remote-runner run list
remote-runner run show
```

`run once` 是 machine/session/file 之上的通用编排层，不绑定科研、SEED、运维、训练或 benchmark profile。它至少支持：

- 创建一个临时 session。
- 通过 `--input LOCAL=REMOTE` 显式上传输入文件或目录，可重复。
- 在远程 cwd 执行一个命令。
- 通过 `--artifact REMOTE=LOCAL` 显式拉回产物文件或目录，可重复。
- 生成本地 run manifest，记录 run_id、machine_id、session_id、cwd、command、inputs、command_result、artifacts、status、started_at、ended_at 和销毁会话结果。
- 默认销毁临时 session，但保留 session 日志、transfer 记录和 artifact manifest；可通过 `--keep-session` 保留会话。

非零退出码应把 run 标为 failed，但不得丢失命令日志和 run manifest。

## 4. 非目标

- 不重写 OpenSSH。
- 不做通用密码管理器。
- 不替代 Slurm、Kubernetes、Docker 或实验追踪平台。
- 不承诺在无隔离条件下抵御拥有同一系统用户 shell 权限的恶意 Agent。
- 不优先做复杂 GUI。
- 不把科研、SEED、实验或运维任一场景当成唯一业务边界。
- 不把 sshfs、mount、tmux 或某个具体库写成长期需求。

## 5. 与 SEEDRunner 原型的关系

当前仓库里的 `seed-runner` 是早期原型。它验证了用户和 Agent 需要统一工具隐藏 SSH、tmux、sshfs 等复杂性，并获得日志和产物。

后续合理结构是：

```text
Remote Runner
  通用远程机器与会话层
  通用命令执行与日志层
  通用产物管理层
  profiles/
    operations/
    seed/
    paper-reproduction/
    model-training/
    benchmark/
```

SEED 应该成为第一个强 demo/profile，而不是项目名称、架构边界或唯一目标用户。

## 6. 项目级验收标准

MVP 通过的最低标准：

- 用户能添加或编辑机器配置。
- 用户能用 `machine doctor` 测试连接并获得可理解的错误。
- 使用者能列出机器并创建会话。
- 使用者能在远程指定目录执行命令。
- 使用者能显式上传、下载和列出远程文件，不依赖挂载。
- `session exec --json` 返回 stdout、stderr、退出码、时间戳、耗时和日志路径。
- 密码不会出现在命令输出、日志、报告或 handoff 中。
- 会话、命令历史、传输历史和日志可在中断后通过 CLI 恢复。
- SEED 原型能力可以作为 profile 或兼容层保留，不阻塞通用远程交互能力。
