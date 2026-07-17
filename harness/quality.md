<!-- 职责：记录当前版本的质量判断和仍未覆盖的边界。 -->

# 质量状态

## 当前判断

Local Terminal V4 已完成本机生产切换：公共 Interface 小而一致，生产实现只有一个 tmux
Terminal，旧 backend 与兼容分支已删除。当前不以“旧测试数量”冒充质量；证据来自新合同的
边界测试、真实隔离 tmux、安装后 smoke 和默认生产环境 smoke。

## 已验证的高风险边界

- recorder 先于真实 shell 启动，启动门闩可在中断窗口恢复，不遗漏首字节。
- active 同时要求 pane 与 `pipe-pane` recorder 存活；缺任一者收敛为 lost。
- `send` 通过临时 tmux buffer 精确送入一行，buffer 随即删除，输入不进入 RR state/返回。
- TTY no-echo 下的秘密不进入 transcript；普通 Agent/人工 attach 输入按真实终端回显。
- transcript range/tail 使用 raw byte cursor 和单次 size snapshot，不隐藏 reader state。
- bootstrap 全程独占 writer lock；失败/超时保留可接管 Session，worker 结束后才返回。
- state fresh initialization 经并发压力测试；旧/异版本 state 拒绝且不改动原目录。
- destroy 保留历史并释放名称；purge 要求 destroyed exact UUID 双重确认。
- wheel 在临时 venv 中以非 editable 方式安装，并通过隔离 tmux create/send/tail/destroy。

## 有意不承诺

- 未在 Linux RR host 上实跑；代码与 mypy 目标兼容 Python 3.10，当前 RR host 实测环境是
  macOS、Python 3.13.12、tmux 3.7b。
- 已连接真实高延迟 Linux SSH target，验证登录、状态连续、延时前台命令和退出回本地 shell。
  Windows target 未实跑；两者都只是 terminal 中的普通输入，不是 RR backend。
- 不保证本机重启、tmux 被杀、SSH 断线或远端进程的存活与恢复。
- transcript 不轮转、不压缩；长任务由使用者按文件系统容量自行管理并在明确需要时 purge。

## Cutover result

- 已发布 Skill 通过 `skill-maintainer/scripts/quick_validate.py`；所有示例命令已与 V4 CLI help
  核对，状态字段与 CLI reference、实现和测试一致，旧 machine/exec/file/run/interrupt/`--since`
  工作流没有残留。
- Skill 明确排除开发/调试 Remote Runner 本身、普通本地 shell 和概念性 SSH 问题，避免工具
  自举和泛触发；canonical 文件 SHA-256 为
  `c2130e7061e80d63f025432ed2fd4dad0c5c62d1cd62b871f180d153740fff2c`。
- 准备改动后完整代码门禁再次通过，并重新构建 0.4.0 wheel，在临时 venv 非 editable 安装，
  用独立 state/tmux 完成 create/send/tail/show/destroy/purge。
- main 已整分支 fast-forward；系统安装为 `remote-runner 0.4.0` editable，旧 `seed-runner`
  metadata 已消失；global Skill hash 与 canonical 文件一致。
- 默认 state/default tmux smoke 验证初始 prompt、透明输入、真实输出、prompt 恢复、show 元信息、
  destroy/purge 和空 Session 列表。旧 state 与旧 Skill 备份保留。执行证据与回退合同见
  `plans/archive/2026-07-17-local-terminal-v4-cutover.md`。
