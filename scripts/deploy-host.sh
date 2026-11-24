#!/bin/bash
# 服务器直接部署（宿主直跑）：四个进程与 compose 的 app / worker / consumer / beat 一一对应，
# 启动命令与 entrypoint/*.sh 保持一致。用法见下方 case，进程语义与旋钮见 handbook/deploy.md。
# 不导出业务 env：settings/base.py 自己 load_dotenv（进程环境永远优先）。

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

RUN_DIR="$PROJECT_DIR/data/run"
LOG_DIR="$PROJECT_DIR/data/logs"
mkdir -p "$RUN_DIR" "$LOG_DIR"

# 运行时旋钮：与容器共用 envs/gunicorn.env、envs/celery.env，缺省用内置默认值
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

# 前置检查
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

# build：依赖 + 前端 + 静态
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

# migrate：迁移 + 初始管理员
do_migrate() {
    check_envs
    echo "==> migrate_if_needed（只跑未应用的迁移，库级命名锁串行化）"
    uv run python manage.py migrate_if_needed

    echo "==> ensure_superuser（库里没有超管时创建 admin 并打印初始密码）"
    uv run python manage.py ensure_superuser
}

# 进程管理
SERVICES=("app" "worker" "consumer" "beat")

get_pid_file() {
    local service="$1"
    echo "$RUN_DIR/${service}.pid"
}

validate_service() {
    local service="$1"
    local valid=false
    for s in "${SERVICES[@]}"; do
        if [ "$s" == "$service" ]; then
            valid=true
            break
        fi
    done
    if [ "$valid" == false ]; then
        echo "错误：未知的服务 '$service'。可用服务：${SERVICES[*]}" >&2
        exit 1
    fi
}

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

    # nohup 只 exec 可执行文件，接 shell 函数会失败；这里在子 shell 里手动实现
    # nohup 的两件事（忽略 SIGHUP、断开 stdin），cmd_* 内部用 exec 顶替子 shell，
    # 使 $! 就是服务进程本身，且 SIG_IGN 经 exec 保留。
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

# 命令封装：与容器入口一一对应，用 exec 顶替子 shell（见 start_service）。
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
    # 与 entrypoint/beat.sh 一致：先刷链路缓存、补投一次采集，再打印调度自检并起调度。
    uv run python manage.py refresh_link_cache || echo "警告：启动时链路缓存刷新失败，beat 继续启动" >&2
    uv run python manage.py collect_dashboard || echo "警告：启动时大屏采集投递失败，beat 继续启动" >&2
    uv run python manage.py shell -c "from netops.celery import app; print('[beat] 生效调度:', {name: (entry['task'], entry['schedule']) for name, entry in app.conf.beat_schedule.items()})" \
        || echo "警告：beat 调度自检失败（不影响调度本身）" >&2
    exec uv run celery -A netops beat \
        --loglevel="$CELERY_LOGLEVEL" \
        --schedule="$RUN_DIR/celerybeat-schedule" \
        --pidfile="$RUN_DIR/celerybeat.pid"
}

do_start() {
    check_envs
    local target="${1:-}"

    if [ -n "$target" ]; then
        validate_service "$target"
        echo "==> 启动服务: $target"
        case "$target" in
            app)      start_service app      "$(get_pid_file app)"      cmd_app ;;
            worker)   start_service worker   "$(get_pid_file worker)"   cmd_worker ;;
            consumer) start_service consumer "$(get_pid_file consumer)" cmd_consumer ;;
            beat)     start_service beat     "$(get_pid_file beat)"     cmd_beat ;;
        esac
    else
        echo "==> 启动所有四个进程"
        start_service app      "$(get_pid_file app)"      cmd_app
        start_service worker   "$(get_pid_file worker)"   cmd_worker
        start_service consumer "$(get_pid_file consumer)" cmd_consumer
        start_service beat     "$(get_pid_file beat)"     cmd_beat
    fi
}

do_stop() {
    local target="${1:-}"

    if [ -n "$target" ]; then
        validate_service "$target"
        echo "==> 停止服务: $target"
        stop_service "$target" "$(get_pid_file "$target")"
    else
        echo "==> 停止所有四个进程"
        stop_service app      "$(get_pid_file app)"
        stop_service worker   "$(get_pid_file worker)"
        stop_service consumer "$(get_pid_file consumer)"
        stop_service beat     "$(get_pid_file beat)"
    fi
}

do_status() {
    local target="${1:-}"

    if [ -n "$target" ]; then
        validate_service "$target"
        status_service "$target" "$(get_pid_file "$target")"
    else
        status_service app      "$(get_pid_file app)"
        status_service worker   "$(get_pid_file worker)"
        status_service consumer "$(get_pid_file consumer)"
        status_service beat     "$(get_pid_file beat)"
    fi
}

# 入口
case "${1:-}" in
    build)   do_build ;;
    migrate) do_migrate ;;
    start)   do_start "${2:-}" ;;
    stop)    do_stop "${2:-}" ;;
    restart) do_stop "${2:-}"; do_start "${2:-}" ;;
    status)  do_status "${2:-}" ;;
    deploy)  do_build; do_migrate; do_stop; do_start ;;
    *)
        echo "用法: $0 {build|migrate|start|stop|restart|status|deploy} [app|worker|consumer|beat]"
        echo "  deploy = build + migrate + restart（完整发布）"
        echo "  start/stop/restart/status 后可跟服务名，不跟则操作所有服务"
        exit 1
        ;;
esac
