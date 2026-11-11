#!/bin/sh
#
# beat 容器入口：先同步刷新一次链路缓存，再启动 celery beat。
#
# 为什么先刷新：Redis 空的时候大屏链路图会空白，而 beat 的第一个周期任务要等
# DASHBOARD_LINK_REFRESH_SECONDS 才到；先跑一次保证启动即可用。
# 失败不阻塞：Zabbix 短暂不可用时 beat 仍要起来，周期任务会重试，缓存保留上一份。
#
# --schedule / --pidfile 必须放 /tmp：/app 是 code 卷的只读挂载（volumes_from: [app:ro]），
# celery 默认往 cwd 写 celerybeat-schedule，会直接 EROFS。
#
# 参数约定与 worker.sh 一致：$1 起原样追加给 celery beat。

set -e

python manage.py refresh_link_cache || echo "警告：启动时链路缓存刷新失败，beat 继续启动（下个周期重试）" >&2

exec celery -A netops beat \
    --loglevel="${CELERY_LOGLEVEL:-info}" \
    --schedule=/tmp/celerybeat-schedule \
    --pidfile=/tmp/celerybeat.pid \
    "$@"
