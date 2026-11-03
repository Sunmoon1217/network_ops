#!/bin/sh
#
# worker 容器入口：启动 celery worker 进程。
#
# 关于启动什么：
#   celery 的**整条命令**都在下面拼装：硬要求（-A netops worker -Q celery,access_flow）写死，
#   可调参数取环境变量并带默认值（--concurrency="${CELERY_CONCURRENCY:-2}"）。
#     $1 以 - 开头（或没有参数）→ 视为「给默认命令的参数」，在拼好的命令后面追加
#     否则                      → 视为「整条命令」，原样执行
#
#   参数为什么全部收在这里、而不是放镜像的 CMD 里：
#     * worker 在 compose 里被整条换成 celery 命令，根本走不到 app 的 entrypoint；
#     * CMD 是 exec 形式，环境变量不会被展开（要展开得退回 shell 形式，那样又会绕过
#       「$1 以 - 开头」这套判断）；把默认值写成 shell 插值，`.env` 才能直接改参数；
#     * 环境变量在这里是**替换**语义（位置固定），不是 celery 的 CELERY_WORKER_ARGS
#       那种「追加到最后」——后者对 --concurrency 只会多出一个监听，覆盖不掉。
#   注意 CELERY_* 里的 0 与空串不同：`:-` 只对「未设置或空」取默认值，写 0 就是 0。
#
# 变量由 compose 的 env_file 注入（docker-compose.yml 的 worker 服务把 env/app.env + env/celery.env 注入），
# 所以在 env/celery.env 里改 CELERY_* 即可，不必碰 compose。
#
# 关于并发：
#   --concurrency=2 写死：默认池按 CPU 核数起（16 核 = 16 子进程 × 81M，空载即爆炸），
#   且同设备并发入库会写坏数据（见 AGENTS.md），2 保留跨设备并行、压缩同设备撞车窗口。

set -e

# 同时消费主队列与 access_flow 队列（settings 的 CELERY_TASK_ROUTES）。两条链都是
# 低频、毫秒~秒级，共享并发槽的最坏代价是秒级排队——比为每个可能堵的队列各开一个
# 677MB 的 prefork 池便宜得多；真出现主链被饿死的实测证据再拆出独立服务即可。
exec celery -A netops worker \
    -Q celery,access_flow \
    --concurrency="${CELERY_CONCURRENCY:-2}" \
    --loglevel="${CELERY_LOGLEVEL:-info}" \
    "$@"
