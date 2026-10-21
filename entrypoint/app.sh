#!/bin/sh
#
# 应用容器入口：数据库迁移 + 零配置建管理员 + 按参数启动 gunicorn。
#
# 静态产物的分发已移到 code-init（entrypoint/init.sh），这里不再碰 static_data 卷。
#
# 关于启动什么：
#   gunicorn 的**整条命令**都在下面拼装：硬要求（--worker-class / --bind）写死，
#   可调参数取环境变量并带默认值（${GUNICORN_WORKERS:-1} 这种写法）。于是：
#     $1 以 - 开头（或没有参数）→ 视为「给默认命令的参数」，在拼好的命令后面追加
#     否则                      → 视为「整条命令」，原样执行
#   三类用法因此都成立：
#     docker compose run --rm app --workers 4                 # 追加参数（覆盖同名项）
#     docker compose run --rm app python manage.py migrate    # 换整条命令
#     docker compose run --rm app gunicorn netops.asgi:application -w 4
#
#   变量由 compose 的 env_file 注入（app 服务把 env/app.env + env/gunicorn.env 注入），
#   所以在 env/gunicorn.env 里改 GUNICORN_* 即可，不必碰 compose。
#
# 迁移在下面第 1 步**自动跑**：只在确实有未应用的迁移时才执行，且整段「检查 + 迁移」由
# migrate_if_needed 用数据库自带的命名锁（PG advisory / MySQL GET_LOCK）串行化，所以多副本同时启动不会互相竞争
# （Django 自己不给 migrate 加锁，裸的两行 shell 会撞车）。想让迁移必须人工放行，
# 把 MIGRATE_ON_START 设为 0：docker compose run --rm app python manage.py migrate
#
# 初始管理员在下面第 2 步**零配置创建**：库里一个超级用户都没有时，创建一个 admin 并把随机
# 初始密码打印在启动日志里；已经有时什么都不做。

set -e

# 1) 数据库迁移：**有未应用的迁移才跑**（首次部署的第一次启动即自动建表）。失败就退出
#    （set -e）——宁可起不来，也不要带着过期表结构对外服务。
if [ "${MIGRATE_ON_START:-1}" = "1" ]; then
    python manage.py migrate_if_needed
else
    echo "[entrypoint] MIGRATE_ON_START=0，跳过迁移（需要时执行 docker compose run --rm app python manage.py migrate）"
fi

# 2) 初始管理员：**不需要任何配置**。库里还没有超级用户时创建 `admin`，随机初始密码直接打印在
#    启动日志里（登录后请立即修改）；已经有超级用户就是空操作。人工用法：
#     docker compose exec app python manage.py ensure_superuser --username ops --password '...'
python manage.py ensure_superuser

# 3) 启动。$1 以 - 开头（或压根没有参数）→ 视为「给默认命令的参数」，在下面这条
#    命令后面追加；否则视为「整条命令」原样执行。
#
#    这里只放**硬要求**（漏了会出事的），可调参数（--workers / 超时 / 日志）取环境变量：
#      --bind 0.0.0.0:8000  与 nginx 的 upstream 耦合，改它必须同步 nginx 配置；且
#                           gunicorn 的默认值是 127.0.0.1:8000，一旦漏掉就 502；--bind
#                           又是 append 语义，追加只会多一个监听、覆盖不掉。
#      --worker-class       决定 ASGI 能否工作，同理写死。
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
