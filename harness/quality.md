<!-- 职责：记录当前版本的质量判断和仍未覆盖的边界。 -->

# 质量状态

## 当前判断

Local Terminal V4 已达到当前定义的生产切换门槛：公共 Interface 小而一致，生产实现只有一个
tmux Terminal，旧 backend 与兼容分支已删除。当前不以“旧测试数量”冒充质量；证据来自新
合同的边界测试、真实隔离 tmux 和安装后 smoke。

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
