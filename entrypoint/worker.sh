#!/bin/sh
# worker 容器入口：启动 celery worker。无参数或 $1 以 - 开头时追加给默认命令，
# 否则 $1 起视为整条命令；参数来源与并发口径见 handbook/deploy.md。

set -e

# 同时消费主队列与 access_flow 队列（CELERY_TASK_ROUTES）；并发固定 2，避免同设备并发入库。
exec celery -A netops worker \
    -Q celery,access_flow \
    --concurrency="${CELERY_CONCURRENCY:-2}" \
    --loglevel="${CELERY_LOGLEVEL:-info}" \
    "$@"
