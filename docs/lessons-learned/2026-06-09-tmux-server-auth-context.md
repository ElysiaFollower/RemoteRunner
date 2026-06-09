# 2026-06-09 - Tmux Server 授权上下文不会随 Session Destroy 自动刷新

## 现象

用户将远端账号加入 `docker` 组后，Remote Runner 销毁旧 session 并重新 `session create`，新 session 内 `id` 仍只显示旧补充组，`docker ps` 仍提示无权访问 Docker socket。与此同时，`id <user>` 和 `getent group docker` 已经显示该用户属于 `docker` 组。

## 根因

当前 Linux/SSH + tmux backend 的 `session create` 通过 SSH 执行 `tmux new-session`。这会创建新的 Remote Runner session 和新的 tmux session，但不一定创建新的 tmux server。

如果该用户已有 tmux server 进程，新的 tmux session 会由既有 tmux server fork 出 shell。Linux 进程的补充组在进程创建时固定，后续 `/etc/group` 或用户数据库变化不会自动更新到已存在的 tmux server。因此，即使 Remote Runner session 是新的，shell 仍可能继承旧 tmux server 的旧补充组。

## 验证摘要

只销毁 Remote Runner session 后，新建 session 仍显示：

```text
id: groups=1000(ely),100(users)
id ely: groups=1000(ely),100(users),110(docker)
docker ps: permission denied
```

重启远端 tmux server 后再新建 session，显示：

```text
id: groups=1000(ely),100(users),110(docker)
docker ps: exit_code=0
```

## 影响

`session destroy && session create` 只保证重建 Remote Runner session 和目标 tmux session，不保证刷新远端 tmux server 的 Unix 授权上下文。对 Docker、Unix group、登录策略、环境初始化等依赖进程创建时上下文的场景，单纯重建 session 可能不够。

## 处理

新增 machine 级 direct-SSH 接口，用于在确认没有活跃 Remote Runner tmux session 且远端 tmux session 列表为空后重启该用户的 tmux server。该接口不能在 tmux session 内执行，否则会杀死承载自己的 session，导致命令状态无法正常收尾。

## 后续原则

- 把 tmux server 与 Remote Runner session 分开考虑。
- 涉及 shell 授权上下文刷新时，先检查 `id`、`id <user>`、`getent group <group>` 和 tmux server/session 状态。
- `tmux kill-server` 是危险操作，会杀掉该用户所有 tmux session；接口必须保守检查并默认拒绝误杀非 Remote Runner tmux session。
