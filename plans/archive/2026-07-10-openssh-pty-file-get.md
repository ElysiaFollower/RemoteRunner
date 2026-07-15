# OpenSSH PTY Artifact Pull

## 目标

让已完成交互登录的 `openssh-pty` session 支持 `remote-runner file get`，用于把远端实验产物可靠回收到本地。

## 范围

- 只支持普通文件下载；目录、上传、list 和 run once 不在本任务内。
- 复用现有 session 的本地 tmux PTY，不建立第二条 SSH/SFTP 连接。
- 分块传输，校验远端大小和 SHA-256，本地临时文件校验成功后原子替换目标文件。
- 失败必须留下 transfer record，但不得留下部分目标文件。

## 验收

- 单测覆盖 openssh-pty session-aware 路由、成功下载、哈希不一致和非普通文件失败。
- `91_A100` 真实 `file get` 拉回 F-Actor WAV，并验证本地/远端 SHA-256 一致。
- 更新 API、平台边界、feature list、progress 和 handoff。

## 验证

```bash
python3 -m pytest tests/test_remote_runner_mvp.py -q -k openssh_pty_file_get
python3 -m pytest tests/test_remote_runner_mvp.py -q
./scripts/harness-check.sh
git diff --check
```
