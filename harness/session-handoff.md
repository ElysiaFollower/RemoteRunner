<!-- 当前可恢复状态；历史过程见 harness/progress.md。 -->

# 会话交接

## 仓库状态

- 分支：`main`，工作区未提交；不要覆盖现有 F-025 及更早修改。
- 当前功能：`F-026 OpenSSH PTY session 文件回收` passing；任务合同已归档到 `plans/archive/2026-07-10-openssh-pty-file-get.md`。
- 91_A100 当前 recovery session：`91_A100-recovery-20260710` / `sess_20260710_070047_290193_8b06dcf6`，保留给后续实验。
- 真实 shell 已验证：用户 `lujingyu`，目录 `/home/lujingyu/project/ljm`，shell 已进入 zsh。
- 清洁状态：无 active task plan；工作区仍有 F-025 以来的未提交代码、文档和计划文件，本轮没有替用户提交或清理。

## 本轮完成

- 复现了同一 `openssh-pty` session 中 `session exec` 成功、`file get` 固定拒绝的问题。
- 根因：文件管理器只把 machine 路由给 SFTP backend；PTY backend 已有登录态 session，却没有 session-aware 文件通道。
- 为 `openssh-pty` 实现普通文件 `file get`：
  - 复用已登录且空闲的 session，不创建第二条 SSH/SFTP 连接；
  - 本地 tmux `pipe-pane` 捕获传输输出；
  - 1 MiB 分块 base64；
  - 远端先读取 size/SHA-256；
  - 本地写同目录 partial 文件，全部校验后 `os.replace`；
  - 失败不覆盖已有目标文件，并保留 failed transfer record。
- `file put`、目录下载、`file list`、`run once`、PTY background command 仍明确不支持。
- 同步 README、REQUIREMENTS、API、getting-started、platform-support、MVP spec、feature list 和 progress。

## 验证证据

- `91_A100-recovery-20260710` 成功回收 26 个研究产物，包括最大约 5.8 MB 的 stereo WAV；每个成功 response 均包含远端 size/SHA-256。
- F-Actor eval3 三条主 WAV 本地 `file` 验证为 22.05 kHz、16-bit stereo，拆分声道为 mono。
- 聚焦回归：`3 passed`。
- MVP：`56 passed`。
- 全仓：`79 passed, 4 skipped`。
- Black check、`git diff --check`、`./scripts/harness-check.sh`、`./init.sh` 全部通过。

## 研究交付

唯一入口：

```text
/Users/ely/workspace/research/audio/DuplexOmni/competitor_audit_20260708/deliverables/README.md
```

该目录包含最终中文报告、项目查重索引、评估方案、试听指南、当前 listening manifest，以及从远端回收的 F-Actor/dGSLM/Behavior-SD/BayLing 等关键音频。远端只保留仓库、模型和运行环境，不再承担交付完整性。

## 仍未完成

- PTY 传输会短暂使用 terminal alternate screen；真实回归未污染持久 transcript，但若进程被 `SIGKILL`，终端显示恢复仍缺专门回归。
- PTY 普通文件下载当前要求远端有 `sha256sum`、`dd` 和 `base64`。
- `remote-runner` console script 在 `seedrunner` 环境的 editable install 仍可能缺失模块；本轮可靠入口是仓库根目录执行 `conda run -n seedrunner python -m remote_runner.cli ...`。
- 当前工作区包含此前未提交的 F-025 与文档改动；本轮未提交、未清理这些修改。

## 安全与隐私边界

- 没有把密码、真实 gateway host、密钥或 `.env.machines` 内容写入代码、日志、研究报告或 handoff。
- 真实文件操作只读取 `/home/lujingyu/project/ljm` 下既有研究产物；没有删除远端文件、修改模型权重或操作他人 GPU 进程。
- 本地研究目录只新增/迁移审计交付物，没有复制远端模型权重或 conda 环境。

## 下一步最佳动作

优先继续双工模型研究和试听。Remote Runner 只有在真实工作流再次遇到边界时，才扩展 `file put`、目录传输、`file list` 或 `run once`；不要为对称性提前堆功能。

## 常用命令

```bash
conda run -n seedrunner python -m remote_runner.cli session show --session 91_A100-recovery-20260710 --json
conda run -n seedrunner python -m pytest tests/test_remote_runner_mvp.py -q
conda run -n seedrunner python -m pytest -q
./scripts/harness-check.sh
git diff --check
```
