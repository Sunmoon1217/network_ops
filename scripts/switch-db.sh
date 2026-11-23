#!/bin/bash
# 部署前切换数据库后端（PostgreSQL / MySQL）：只改写根 .env 的 DB_SERVICE。
#
# 它改的是什么：
#   * compose：compose.yml 的 db 服务用 ${DB_SERVICE} 选 compose.db.yml 的模板；
#   * 两种部署都相关的一点：envs/common.env 的 DB_ENGINE=${DB_SERVICE:-postgresql} 由加载方
#     （compose 的 env_file / 宿主侧的 python-dotenv）插值，决定 Django 用哪个驱动。
#
# 它不管什么（数据库可以在任何地方）：
#   * 连到哪由 DB_HOST / DB_PORT 决定（container.env / host.env / 进程环境），本脚本不改；
#     库在外部时，切后端只是换驱动，目标库里必须本来就是对应的库；
#   * 只有用内置 db 服务时才谈数据卷（network-ops-pgdata / network-ops-mysqldata）：
#     两套卷互不相通，卷不删、切回去旧数据还在；
#   * 宿主直跑（deploy-host.sh）不读根 .env，只认进程环境：
#       export DB_SERVICE=mysql && ./scripts/deploy-host.sh deploy
#   * 不 stop / up 容器、不 migrate、不连库、不依赖 docker。
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="$ROOT/.env"
TMP=""

cleanup() {
    if [ -n "$TMP" ] && [ -f "$TMP" ]; then rm -f "$TMP"; fi
    return 0
}
trap cleanup EXIT

info() { printf '%s\n' "$*"; }
warn() { printf '警告: %s\n' "$*" >&2; }
die() { printf '错误: %s\n' "$*" >&2; exit 1; }

usage() {
    cat <<'EOF'
用法:
  ./scripts/switch-db.sh                    # 显示当前后端与连接地址
  ./scripts/switch-db.sh mysql              # 写入 .env
  ./scripts/switch-db.sh mysql --dry-run    # 只显示改动
  ./scripts/switch-db.sh --check            # 只做静态校验，不写
  ./scripts/switch-db.sh mysql --check      # 校验切到 mysql 是否自洽，不写

后端取值: postgresql（默认）| mysql
EOF
}

default_port() {
    case "$1" in mysql) printf '3306\n' ;; *) printf '5432\n' ;; esac
}

# 读某个 env 文件里的变量（只用于展示与告警，不参与 .env 改写）
read_file_var() {
    local file="$1" name="$2" value
    value="$(sed -nE "s|^${name}=(.*)$|\1|p" "$file" 2>/dev/null | tail -n 1 | sed -E 's/["'"'"']//g')"
    printf '%s\n' "$value"
}

read_var() {
    local value
    value="$(read_file_var "$ENV_FILE" "$1")"
    printf '%s\n' "${value:-$2}"
}

read_service() {
    sed -nE 's|^[[:space:]]*DB_SERVICE=([^#[:space:]]*).*|\1|p' "$ENV_FILE" | tail -n 1 | sed -E 's/["'"'"']//g'
}

normalize() {
    case "$1" in
        postgresql|postgres|pg) printf 'postgresql\n' ;;
        mysql|mariadb) printf 'mysql\n' ;;
        *) die "不支持的数据库后端: $1（只接受 postgresql / mysql）" ;;
    esac
}

# 静态校验：只确认「一个开关」这条链路没被改断，不解析 compose、不碰任何服务
check_config() {
    local target="$1" image_var port_var other
    case "$target" in
        postgresql) image_var=DB_IMAGE_POSTGRES; port_var=DB_PORT_POSTGRES ;;
        mysql) image_var=DB_IMAGE_MYSQL; port_var=DB_PORT_MYSQL ;;
    esac

    grep -qF 'DB_ENGINE=${DB_SERVICE:-postgresql}' "$ROOT/envs/common.env" \
        || die "envs/common.env 的 DB_ENGINE 必须是 \${DB_SERVICE:-postgresql}（切后端的唯一连接点）"
    grep -qE "^  ${target}:[[:space:]]*$" "$ROOT/compose.db.yml" \
        || die "compose.db.yml 缺少 ${target} 模板"
    grep -qF 'service: ${DB_SERVICE:-postgresql}' "$ROOT/compose.yml" \
        || die "compose.yml 的 db 服务应写 service: \${DB_SERVICE:-postgresql}"

    grep -qE "^${image_var}=" "$ENV_FILE" || warn ".env 没有 ${image_var}=，compose 部署会用内置默认镜像"
    grep -qE "^${port_var}=" "$ENV_FILE" || warn ".env 没有 ${port_var}=，compose 部署会用内置默认端口"

    for other in container host db gunicorn celery; do
        if grep -qE '^[[:space:]]*DB_ENGINE=' "$ROOT/envs/$other.env" 2>/dev/null; then
            warn "envs/$other.env 里出现 DB_ENGINE=，会干扰 common.env 的唯一连接点，建议删掉"
        fi
    done

    # 凭据只在容器里走 /run/secrets/*；缺了说明还没在部署机上生成，不是配置错误
    local missing=""
    for other in db_user db_password; do
        [ -s "$ROOT/envs/secrets/$other" ] || missing="$missing $other"
    done
    [ -z "$missing" ] || warn "envs/secrets/ 缺少:$missing（容器部署需要，在部署机上生成：bash envs/secrets/generate.sh）"
}

# 连接地址：切换后端不会改 DB_HOST / DB_PORT，提示清楚库在哪里
show_endpoints() {
    local target="$1" c_host c_port h_host h_port volume
    c_host="$(read_file_var "$ROOT/envs/container.env" DB_HOST)"
    c_port="$(read_file_var "$ROOT/envs/container.env" DB_PORT)"
    h_host="$(read_file_var "$ROOT/envs/host.env" DB_HOST)"
    h_port="$(read_file_var "$ROOT/envs/host.env" DB_PORT)"

    if [ -z "$c_host" ]; then c_host=db; fi
    if [ -z "$c_port" ]; then c_port="$(default_port "$target")"; fi
    if [ -z "$h_host" ]; then h_host=127.0.0.1; fi
    if [ -z "$h_port" ]; then h_port="$(default_port "$target")"; fi

    if [ "$c_host" = db ]; then
        case "$target" in
            mysql) volume=network-ops-mysqldata ;;
            postgresql) volume=network-ops-pgdata ;;
        esac
        info "容器连库 : $c_host:$c_port（内置 db 服务，数据卷 $volume）"
    else
        info "容器连库 : $c_host:$c_port（外部库，与本机数据卷无关）"
    fi
    info "宿主连库 : $h_host:$h_port（envs/host.env；进程环境可覆盖）"

    # 显式写了 DB_PORT 时，切后端不会跟着改端口——最常见的连错库来源
    local explicit_port
    explicit_port="$(read_file_var "$ROOT/envs/container.env" DB_PORT)"
    [ -z "$explicit_port" ] || case "$explicit_port" in
        "$(default_port "$target")") ;;
        *) warn "envs/container.env 显式写了 DB_PORT=$explicit_port，与 ${target} 默认端口不一致，切换后端不会改它" ;;
    esac
    explicit_port="$(read_file_var "$ROOT/envs/host.env" DB_PORT)"
    [ -z "$explicit_port" ] || case "$explicit_port" in
        "$(default_port "$target")") ;;
        *) warn "envs/host.env 显式写了 DB_PORT=$explicit_port，与 ${target} 默认端口不一致" ;;
    esac

    if [ "$c_host" != db ] && [ "$target" = mysql ]; then
        warn "目标是 MySQL 而容器连的是外部库 $c_host：确认那台库是 MySQL 8.0.17+，且里面是 MySQL 的表"
    fi
    if [ "$c_host" != db ] && [ "$target" = postgresql ]; then
        warn "目标是 PostgreSQL 而容器连的是外部库 $c_host：确认那台库是 PostgreSQL"
    fi
}

show_status() {
    local current="$1" image
    case "$current" in
        mysql) image="$(read_var DB_IMAGE_MYSQL mysql:8.4-oracle)" ;;
        postgresql) image="$(read_var DB_IMAGE_POSTGRES timescale/timescaledb:2.27.1-pg16)" ;;
        *) image="未知" ;;
    esac
    info "根 .env 当前后端: DB_SERVICE=$current"
    info "  镜像   : $image（仅内置 db 服务使用）"
    info "  可用   : postgresql | mysql"
    info "  切换   : ./scripts/switch-db.sh mysql    （只改配置，部署仍走 compose）"
    if [ "$current" = mysql ] || [ "$current" = postgresql ]; then
        show_endpoints "$current"
    fi
}

report() {
    local target="$1" image
    case "$target" in
        mysql) image="$(read_var DB_IMAGE_MYSQL mysql:8.4-oracle)" ;;
        postgresql) image="$(read_var DB_IMAGE_POSTGRES timescale/timescaledb:2.27.1-pg16)" ;;
    esac
    info ""
    info "后端     : $target"
    info "镜像     : $image（仅内置 db 服务使用）"
    info "部署     : docker compose up -d        # 应用按 container.env 的 DB_HOST 连库"
    info "宿主直跑 : export DB_SERVICE=$target && ./scripts/deploy-host.sh deploy"
    info "回滚     : ./scripts/switch-db.sh <另一个后端>    # 内置库的旧卷仍在，外部库不受影响"
    show_endpoints "$target"
    if [ "$target" = mysql ]; then
        info ""
        warn "MySQL 侧要求 8.0.17+；DDL 不可回滚，迁移失败只能删库重建（见 handbook/deploy.md）"
    fi
}

main() {
    local target="" dry_run=0 check_only=0 arg
    for arg in "$@"; do
        case "$arg" in
            -h|--help) usage; return 0 ;;
            --dry-run) dry_run=1 ;;
            --check) check_only=1 ;;
            -*) die "未知参数: $arg（用 --help 看用法）" ;;
            *) [ -z "$target" ] || die "一次只能指定一个后端"; target="$arg" ;;
        esac
    done

    [ -f "$ENV_FILE" ] || die ".env 不存在：先 cp .example.env .env 再按需修改"

    local current
    current="$(read_service)"
    [ -n "$current" ] || die ".env 里缺少 DB_SERVICE= 这一行（容器侧靠它选后端）"

    if [ -z "$target" ]; then
        show_status "$current"
        return 0
    fi

    target="$(normalize "$target")"
    check_config "$target"

    # 候选文件：保留行内注释，只换值
    TMP="$(mktemp "$ROOT/.env.tmp.XXXXXX")"
    sed -E "s|^([[:space:]]*DB_SERVICE=)[^#[:space:]]*(.*)$|\1${target}\2|" "$ENV_FILE" > "$TMP"
    chmod --reference="$ENV_FILE" "$TMP" 2>/dev/null || true

    if [ "$check_only" -eq 1 ]; then
        info "静态校验通过：切到 ${target} 的配置链路完整（未写入，未连库）"
        show_endpoints "$target"
        return 0
    fi

    if [ "$target" = "$current" ]; then
        info "当前已经是 ${target}，无需改写 .env"
        report "$target"
        return 0
    fi

    info "--- .env 改动 ---"
    diff -u --label .env --label .env.new "$ENV_FILE" "$TMP" || true

    if [ "$dry_run" -eq 1 ]; then
        info ""
        info "dry-run：未写入。去掉 --dry-run 即生效。"
        return 0
    fi

    mv "$TMP" "$ENV_FILE"
    TMP=""
    info ""
    info "已写入 $ENV_FILE"
    report "$target"
}

main "$@"
