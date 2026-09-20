#!/bin/sh
#
# 应用容器入口：把镜像里的静态产物复制进命名卷，然后按参数启动进程。
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
#   参数为什么全部收在这里、而不是放镜像的 CMD 里（见 Dockerfile.app）：
#     * 同一个镜像还要当 celery worker 用，worker 是靠 compose 的 entrypoint + command
#       改成 `celery ...` 的，根本走不到这里——gunicorn 的默认值放 CMD 只对 app 有意义；
#     * CMD 是 exec 形式，环境变量不会被展开（要展开得退回 shell 形式，那样又会绕过
#       「$1 以 - 开头」这套判断）；把默认值写成 shell 插值，`.env` 才能直接改参数；
#     * 环境变量在这里是**替换**语义（位置固定），不是 gunicorn 的 GUNICORN_CMD_ARGS
#       那种「追加到最后」——后者对 --bind 只会多出一个监听，覆盖不掉。
#   注意 GUNICORN_* 里的 0 与空串不同：`:-` 只对「未设置或空」取默认值，写 0 就是 0。
#
#   变量由 compose 的 env_file 注入（docker-compose.yml 的 app 服务把 .env 整份注入），
#   所以在 .env 里改 GUNICORN_* 即可，不必碰 compose。
#
# 卷的目录布局**按 URL 前缀设计**，这样 nginx 一个 root 就能覆盖全部静态请求：
#
#   <卷>/index.html   ← Vite 产物（SPA 入口，/ 走 try_files 兜底）
#   <卷>/assets/*     ← Vite 产物（/assets/*）
#   <卷>/static/*     ← collectstatic 产物（/static/*，STATIC_URL 就是 /static/）
#
# 为什么要复制：nginx 是独立容器，**读不到本容器镜像里的文件**，只能通过命名卷
# 拿静态产物。卷挂在镜像里**故意留空的**目录上，所以卷里内容唯一来源就是这里的
# 复制——不存在「Docker 只在卷首次创建时用镜像内容播种一次、之后重建镜像也不更新」
# 那种陈旧问题。
#
#   镜像里 /app/www 与 /app/frontend/dist 保持原样不动（Django 的 STATIC_ROOT 与
#   FRONTEND 就指这两个路径，DEBUG 下由 Django 自己托管），复制的是**另一份**。
#
# 复制是**权威**的（先清空再铺），否则上一版带 hash 的遗留资源会一直堆在卷里。
# 注意卷根清空时要**排除 static/**：它由第 2 步单独同步，不能被第 1 步顺带删掉。
#
# 注意这里**不跑 migrate**：迁移是有副作用的操作，多副本同时启动会互相竞争。
# 首次部署与版本升级请显式执行：
#   docker compose run --rm app python manage.py migrate

set -e

VOL=/var/lib/netops-static

mkdir -p /app/data "$VOL" "$VOL/static"

# 1) SPA（Vite 产物）→ 卷根；保留 static/ 给下一步
find "$VOL" -mindepth 1 -maxdepth 1 ! -name static -exec rm -rf {} +
cp -a /app/frontend/dist/. "$VOL"/

# 2) Django collectstatic 产物 → 卷内的 static/ 子目录
find "$VOL/static" -mindepth 1 -delete
cp -a /app/www/. "$VOL/static"/

# 3) 启动。$1 以 - 开头（或压根没有参数）→ 视为「给默认命令的参数」，在下面这条
#    命令后面追加；否则视为「整条命令」原样执行。这是官方镜像的通行写法（docker run
#    python -c ...：以 - 开头就补上 python），三类覆盖因此都成立，也不需要任何
#    「追加参数」的猜测。
#
#    这里只放**硬要求**（漏了会出事的），可调参数（--workers / 超时 / 日志）取环境变量：
#      --bind 0.0.0.0:8000  与 nginx 的 upstream 耦合，改它必须同步 nginx 配置；
#                           且 gunicorn 的默认值是 127.0.0.1:8000，一旦被「只覆盖部分
#                           参数」漏掉就会 502；而 --bind 又是 append 语义，追加一个
#                           只会多出一个监听、覆盖不掉。三条加起来，它不适合做成变量。
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
