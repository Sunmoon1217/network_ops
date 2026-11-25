#!/bin/sh
# 应用容器入口：按需迁移 + 建初始管理员 + 启动 gunicorn。
# 无参数或 $1 以 - 开头时追加给默认命令，否则 $1 起视为整条命令；细节见 handbook/deploy.md。

set -e

# 1) 有未应用的迁移才跑；失败直接退出，不带着过期表结构对外服务
if [ "${MIGRATE_ON_START:-1}" = "1" ]; then
    python manage.py migrate_if_needed
else
    echo "[entrypoint] MIGRATE_ON_START=0，跳过迁移（需要时执行 docker compose run --rm app python manage.py migrate）"
fi

# 2) 初始管理员：库里没有超管时才创建（随机密码打印在启动日志）。
#    注意：当前显式传了 --password；要恢复随机密码，去掉该参数即可。
python manage.py ensure_superuser --username admin --password 'admin123'

# 3) 启动。--bind / --worker-class 是与 nginx、ASGI 耦合的硬要求，写死；
#    其余参数取环境变量（默认值只在 entrypoint 写一份）。
if [ "$#" -eq 0 ] || [ "${1#-}" != "$1" ]; then
    set -- gunicorn netops.asgi:application \
        --worker-class uvicorn_worker.UvicornWorker \
        --bind 0.0.0.0:8000 \
        --workers "${GUNICORN_WORKERS:-1}" \
        --timeout "${GUNICORN_TIMEOUT:-30}" \
        --graceful-timeout "${GUNICORN_GRACEFUL_TIMEOUT:-30}" \
        --keep-alive "${GUNICORN_KEEP_ALIVE:-2}" \
        --max-requests "${GUNICORN_MAX_REQUESTS:-0}" \
        --max-requests-jitter "${GUNICORN_MAX_REQUESTS_JITTER:-0}" \
        --log-level "${GUNICORN_LOG_LEVEL:-info}" \
        --access-logfile - \
        --error-logfile - \
        "$@"
fi

exec "$@"
