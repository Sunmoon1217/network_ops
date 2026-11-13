#!/bin/sh
#
# beat 容器入口：先补一次数据（链路缓存同步刷 + 设备组 / Autotask 投递），再启动 celery beat。
#
# 为什么要补，以及为什么是两种补法：
#   - 链路缓存：Redis 空的时候大屏链路图会空白，所以**同步**刷一次（采集完才启动 beat）。
#   - 设备组 / Autotask：Celery 的 interval 条目在**首次加入时**把 last_run_at 记为「加入
#     时刻」（celery.beat.Entry），第一次发送要等满一个周期；Autotask 默认 600s，不补投
#     的话 beat 起来后前 10 分钟大屏没有工单 / SLB / 巡检。这里用 collect_dashboard
#     **投递**（不阻塞启动，worker 起来后消费）。
#   两者失败都不阻塞：Zabbix / Autotask 短暂不可用时 beat 仍要起来，周期任务会重试。
#
# 调度自检：启动前把 beat 实际加载到的条目打进日志。日志里「没有某条任务」时先看这一行
#   —— 条目不在 = beat 读到的代码还是旧的（code 卷没重铺 / 容器没重启），不是调度写错了。
#
# --schedule / --pidfile 必须放 /tmp：/app 是 code 卷的只读挂载（volumes_from: [app:ro]），
# celery 默认往 cwd 写 celerybeat-schedule，会直接 EROFS。
#
# 参数约定与 worker.sh 一致：$1 起原样追加给 celery beat。

set -e

python manage.py refresh_link_cache || echo "警告：启动时链路缓存刷新失败，beat 继续启动（下个周期重试）" >&2

python manage.py collect_dashboard || echo "警告：启动时大屏采集投递失败，beat 继续启动（首个周期会重试）" >&2

python manage.py shell -c "from netops.celery import app; print('[beat] 生效调度:', {name: (entry['task'], entry['schedule']) for name, entry in app.conf.beat_schedule.items()})" \
    || echo "警告：beat 调度自检失败（不影响调度本身）" >&2

exec celery -A netops beat \
    --loglevel="${CELERY_LOGLEVEL:-info}" \
    --schedule=/tmp/celerybeat-schedule \
    --pidfile=/tmp/celerybeat.pid \
    "$@"
