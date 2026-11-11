#!/bin/bash
#
# 服务器直接部署（宿主直跑，不经容器编排）。
#
# 与 compose 部署共用同一套配置：settings/base.py 启动时自动 load_dotenv
# envs/common.env + envs/host.env（DJANGO_ENV ≠ container 时），进程环境 export 的值
# 永远优先（override=False）——所以本脚本**不导出**任何业务 env，Django 自己会读。
#
# 用法：
#   ./scripts/deploy-host.sh build     # 装依赖 + 前端构建 + collectstatic
#   ./scripts/deploy-host.sh migrate   # migrate_if_needed（带库级锁）+ ensure_superuser
#   ./scripts/deploy-host.sh start     # 后台启动 app / worker / consumer / beat 四个进程
#   ./scripts/deploy-host.sh stop      # 停止四个进程
#   ./scripts/deploy-host.sh restart   # stop + start
#   ./scripts/deploy-host.sh status    # 查看四个进程状态
#   ./scripts/deploy-host.sh deploy    # build + migrate + restart（完整发布）
#
# 四个进程与 compose 的 app / worker / consumer / beat 一一对应，命令与 entrypoint/*.sh 保持一致：
#   app      gunicorn + UvicornWorker，监听 0.0.0.0:8000（与 nginx upstream 耦合，勿改 bind）
#   worker   celery worker，同时消费 celery,access_flow 两个队列，并发固定 2
#            （同设备并发入库会写坏数据，见 AGENTS.md；默认池按 CPU 起会空载爆炸）
#   consumer 访问流消费者，AccessFlow 的唯一写者——**全机只能起一个实例**，
#            本脚本对已存活进程跳过启动，靠 PID 文件防止误起第二份
#   beat     大屏链路缓存周期投递，**单实例**；启动前先同步刷一次缓存
#
# PID 与日志：data/run/*.pid、data/logs/*.log（data/ 是运行期目录，不入库）。
# gunicorn / celery 的可调旋钮沿用 envs/gunicorn.env、envs/celery.env（存在则 source，
# 不存在用内置默认值）——与容器侧同一份文件，不存在「两边各调各的」漂移。

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

RUN_DIR="$PROJECT_DIR/data/run"
LOG_DIR="$PROJECT_DIR/data/logs"
mkdir -p "$RUN_DIR" "$LOG_DIR"

# ---- 运行时旋钮：与容器共用 envs/gunicorn.env / envs/celery.env，缺省即内置默认 ----
[ -f envs/gunicorn.env ] && source envs/gunicorn.env
[ -f envs/celery.env ] && source envs/celery.env

GUNICORN_BIND="${GUNICORN_BIND:-0.0.0.0:8000}"
GUNICORN_WORKERS="${GUNICORN_WORKERS:-1}"
GUNICORN_TIMEOUT="${GUNICORN_TIMEOUT:-30}"
GUNICORN_GRACEFUL_TIMEOUT="${GUNICORN_GRACEFUL_TIMEOUT:-30}"
GUNICORN_KEEP_ALIVE="${GUNICORN_KEEP_ALIVE:-2}"
GUNICORN_MAX_REQUESTS="${GUNICORN_MAX_REQUESTS:-0}"
GUNICORN_MAX_REQUESTS_JITTER="${GUNICORN_MAX_REQUESTS_JITTER:-0}"
GUNICORN_LOG_LEVEL="${GUNICORN_LOG_LEVEL:-info}"

CELERY_CONCURRENCY="${CELERY_CONCURRENCY:-2}"
CELERY_LOGLEVEL="${CELERY_LOGLEVEL:-info}"

# ---- 前置检查 ----------------------------------------------------------------

need_cmd() {
    if ! command -v "$1" >/dev/null 2>&1; then
        echo "错误：缺少命令 $1 —— $2" >&2
        exit 1
    fi
}

check_envs() {
    if [ ! -f envs/common.env ]; then
        echo "错误：envs/common.env 不存在。首次部署先执行：" >&2
        echo "  cp envs/example/*.env envs/   然后按实际环境修改" >&2
        exit 1
    fi
}

# ---- build：依赖 + 前端 + 静态 ------------------------------------------------

do_build() {
    check_envs
    need_cmd uv "Python 依赖管理（https://docs.astral.sh/uv/）"

    echo "==> uv sync --frozen --no-dev（严格按 uv.lock，不装 dev 组）"
    uv sync --frozen --no-dev

    if command -v pnpm >/dev/null 2>&1; then
        echo "==> 前端构建（vue-tsc 类型检查 + vite build → frontend/dist）"
        (cd frontend && pnpm install --frozen-lockfile && pnpm build)
    elif [ -d frontend/dist ] && [ -n "$(ls -A frontend/dist 2>/dev/null)" ]; then
        echo "==> 本机无 pnpm，使用已有 frontend/dist 成品"
    else
        echo "错误：本机无 pnpm 且 frontend/dist 不存在——静态资源无从谈起。" >&2
        echo "  在能跑 pnpm 的机器上构建后同步 dist 目录，或安装 pnpm 后重跑。" >&2
        exit 1
    fi

    echo "==> collectstatic（→ www/，Django 托管 /static 与管理后台）"
    uv run python manage.py collectstatic --noinput

    echo "==> build 完成"
}

# ---- migrate：迁移 + 初始管理员 ----------------------------------------------

do_migrate() {
    check_envs
    echo "==> migrate_if_needed（只跑未应用的迁移，库级命名锁串行化）"
    uv run python manage.py migrate_if_needed

    echo "==> ensure_superuser（库里没有超管时创建 admin 并打印初始密码）"
    uv run python manage.py ensure_superuser
}

# ---- 进程管理 ----------------------------------------------------------------

# start_service <name> <pidfile> <shell-function>
start_service() {
    local name="$1" pidfile="$2"
    shift 2

    if [ -f "$pidfile" ] && kill -0 "$(cat "$pidfile")" 2>/dev/null; then
        echo "  $name 已在运行（PID $(cat "$pidfile")），跳过"
        return
    fi
    # 残留的陈旧 PID 文件（进程已死）清掉再启动
    rm -f "$pidfile"

    # nohup 是外部命令，只会 exec 可执行文件，接 shell 函数（cmd_*）会直接报
    # "nohup: failed to run command 'cmd_app': No such file or directory"。
    # 这里在 fork 出的子 shell 里手动做 nohup 的两件事：忽略 SIGHUP、断开 stdin；
    # 函数与变量随 fork 继承，cmd_* 内部用 exec 顶替子 shell，于是 $! 就是服务进程
    # 本身（stop 的 kill 能命中），而 SIG_IGN 经 exec 仍保留，效果等同 nohup。
    ( trap '' HUP; "$@" ) </dev/null >>"$LOG_DIR/$name.log" 2>&1 &
    echo $! >"$pidfile"
    sleep 1
    if kill -0 "$(cat "$pidfile")" 2>/dev/null; then
        echo "  $name 已启动（PID $(cat "$pidfile")，日志 $LOG_DIR/$name.log）"
    else
        echo "  $name 启动失败——查 $LOG_DIR/$name.log" >&2
        rm -f "$pidfile"
        exit 1
    fi
}

stop_service() {
    local name="$1" pidfile="$2"
    if [ -f "$pidfile" ]; then
        local pid
        pid="$(cat "$pidfile")"
        if kill -0 "$pid" 2>/dev/null; then
            echo "  停止 $name（PID $pid）"
            kill "$pid"
            # 等优雅退出（worker/consumer 在收尾），超 15s 强杀
            for _ in $(seq 1 15); do
                kill -0 "$pid" 2>/dev/null || break
                sleep 1
            done
            kill -0 "$pid" 2>/dev/null && { echo "  $name 未在 15s 内退出，强杀"; kill -9 "$pid" 2>/dev/null || true; }
        fi
        rm -f "$pidfile"
    else
        echo "  $name 未在运行（无 PID 文件）"
    fi
}

status_service() {
    local name="$1" pidfile="$2"
    if [ -f "$pidfile" ] && kill -0 "$(cat "$pidfile")" 2>/dev/null; then
        echo "  $name  运行中（PID $(cat "$pidfile")）"
    else
        echo "  $name  未运行"
    fi
}

# 三个命令封装成函数，与容器入口一一对应；函数体用 exec 顶替 fork 出的子 shell，
# 让 start_service 记录的 $! 就是服务进程，stop 时 kill 能直接命中（见 start_service）。

cmd_app() {
    # 命令与 entrypoint/app.sh 一致：硬要求（worker-class / bind）写死，旋钮取 envs/gunicorn.env
    exec uv run gunicorn netops.asgi:application \
        --worker-class uvicorn_worker.UvicornWorker \
        --bind "$GUNICORN_BIND" \
        --workers "$GUNICORN_WORKERS" \
        --timeout "$GUNICORN_TIMEOUT" \
        --graceful-timeout "$GUNICORN_GRACEFUL_TIMEOUT" \
        --keep-alive "$GUNICORN_KEEP_ALIVE" \
        --max-requests "$GUNICORN_MAX_REQUESTS" \
        --max-requests-jitter "$GUNICORN_MAX_REQUESTS_JITTER" \
        --log-level "$GUNICORN_LOG_LEVEL"
}

cmd_worker() {
    # 命令与 entrypoint/worker.sh 一致：两个队列一起消费，并发默认 2
    exec uv run celery -A netops worker \
        -Q celery,access_flow \
        --concurrency="$CELERY_CONCURRENCY" \
        --loglevel="$CELERY_LOGLEVEL"
}

cmd_consumer() {
    # 命令与 entrypoint/consumer.sh 一致：单写者，只跑一个实例
    exec uv run python manage.py access_flow_consumer
}

cmd_beat() {
    # 与 entrypoint/beat.sh 一致：先同步刷一次链路缓存（失败不阻塞），再起调度；
    # --schedule / --pidfile 放 data/run，避免往项目根写运行期文件。
    uv run python manage.py refresh_link_cache || echo "警告：启动时链路缓存刷新失败，beat 继续启动" >&2
    exec uv run celery -A netops beat \
        --loglevel="$CELERY_LOGLEVEL" \
        --schedule="$RUN_DIR/celerybeat-schedule" \
        --pidfile="$RUN_DIR/celerybeat.pid"
}

do_start() {
    check_envs
    echo "==> 启动四个进程"
    start_service app      "$RUN_DIR/app.pid"      cmd_app
    start_service worker   "$RUN_DIR/worker.pid"   cmd_worker
    start_service consumer "$RUN_DIR/consumer.pid" cmd_consumer
    start_service beat     "$RUN_DIR/beat.pid"     cmd_beat
}

do_stop() {
    echo "==> 停止四个进程"
    stop_service app      "$RUN_DIR/app.pid"
    stop_service worker   "$RUN_DIR/worker.pid"
    stop_service consumer "$RUN_DIR/consumer.pid"
    stop_service beat     "$RUN_DIR/beat.pid"
}

do_status() {
    status_service app      "$RUN_DIR/app.pid"
    status_service worker   "$RUN_DIR/worker.pid"
    status_service consumer "$RUN_DIR/consumer.pid"
    status_service beat     "$RUN_DIR/beat.pid"
}

# ---- 入口 --------------------------------------------------------------------

case "${1:-}" in
    build)   do_build ;;
    migrate) do_migrate ;;
    start)   do_start ;;
    stop)    do_stop ;;
    restart) do_stop; do_start ;;
    status)  do_status ;;
    deploy)  do_build; do_migrate; do_stop; do_start ;;
    *)
        echo "用法: $0 {build|migrate|start|stop|restart|status|deploy}"
        echo "  deploy = build + migrate + restart（完整发布）"
        exit 1
        ;;
esac
