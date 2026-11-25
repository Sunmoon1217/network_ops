#!/bin/sh
# beat 容器入口：先刷一次链路缓存、补投一次采集，再启动 celery beat。
# 补投原因（interval 条目首轮要等满周期）与调度自检见 handbook/deploy.md；参数原样追加给 celery beat。

set -e

python manage.py refresh_link_cache || echo "警告：启动时链路缓存刷新失败，beat 继续启动（下个周期重试）" >&2

python manage.py collect_dashboard || echo "警告：启动时大屏采集投递失败，beat 继续启动（首个周期会重试）" >&2

python manage.py shell -c "from netops.celery import app; print('[beat] 生效调度:', {name: (entry['task'], entry['schedule']) for name, entry in app.conf.beat_schedule.items()})" \
    || echo "警告：beat 调度自检失败（不影响调度本身）" >&2

# --schedule / --pidfile 放 /tmp：/app 是只读 code 卷，写 cwd 会 EROFS
exec celery -A netops beat \
    --loglevel="${CELERY_LOGLEVEL:-info}" \
    --schedule=/tmp/celerybeat-schedule \
    --pidfile=/tmp/celerybeat.pid \
    "$@"
