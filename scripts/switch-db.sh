#!/bin/bash
# 部署前切换数据库后端（PostgreSQL / MySQL）：只改写根 .env 的 DB_SERVICE。
#
# 为什么一个开关就够：
#   compose.yml 的 db 服务用 ${DB_SERVICE} 选 compose.db.yml 的模板；
#   envs/common.env 的 DB_ENGINE=${DB_SERVICE:-postgresql} 由 compose 加载 env_file 时插值，
#   四个应用进程一起跟着走——改完 .env，按正常流程 `docker compose up -d` 就是新后端。
#
# 三条边界：
#   * 两个后端各一套数据卷（network-ops-pgdata / network-ops-mysqldata），互不相通；
#     卷不删，切回去旧数据还在；切到 MySQL 等同换一套空库（MySQL 只面向新部署，不迁数据）。
#   * 宿主直跑（scripts/deploy-host.sh）不读根 .env，只认进程环境：
#       export DB_SERVICE=mysql && ./scripts/deploy-host.sh deploy
#   * 本脚本不 stop / up 容器、不 migrate、不删卷——部署仍由 compose / deploy-host.sh 负责。
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
  ./scripts/switch-db.sh                    # 显示当前后端与解析结果
  ./scripts/switch-db.sh mysql              # 写入 .env
  ./scripts/switch-db.sh mysql --dry-run    # 只显示改动（仍做解析自检）
  ./scripts/switch-db.sh --check            # 只校验现状，不写
  ./scripts/switch-db.sh mysql --check      # 校验切到 mysql 是否自洽，不写

后端取值: postgresql（默认）| mysql
EOF
}

# 读 .env 里某一行的值（去引号），缺省时给默认值
read_var() {
    local name="$1" default="$2" value
    value="$(sed -nE "s|^${name}=(.*)$|\1|p" "$ENV_FILE" | tail -n 1 | sed -E 's/["'"'"']//g')"
    printf '%s\n' "${value:-$default}"
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

# 静态校验：确认「一个开关」这条链路没被人改断
check_config() {
    local target="$1" image_var port_var other
    case "$target" in
        postgresql) image_var=DB_IMAGE_POSTGRES; port_var=DB_PORT_POSTGRES ;;
        mysql) image_var=DB_IMAGE_MYSQL; port_var=DB_PORT_MYSQL ;;
    esac

    grep -qF 'DB_ENGINE=${DB_SERVICE:-postgresql}' "$ROOT/envs/common.env" \
        || die "envs/common.env 的 DB_ENGINE 必须是 \${DB_SERVICE:-postgresql}（容器与宿主唯一连接点）"
    grep -qE "^  ${target}:[[:space:]]*$" "$ROOT/compose.db.yml" \
        || die "compose.db.yml 缺少 ${target} 模板"
    grep -qF 'service: ${DB_SERVICE:-postgresql}' "$ROOT/compose.yml" \
        || die "compose.yml 的 db 服务应写 service: \${DB_SERVICE:-postgresql}"

    local s
    for s in db_user db_password; do
        [ -s "$ROOT/envs/secrets/$s" ] || die "缺少凭据文件 envs/secrets/$s（生成：bash envs/secrets/generate.sh）"
    done

    grep -qE "^${image_var}=" "$ENV_FILE" || warn ".env 没有 ${image_var}=，将使用 compose 内置默认镜像"
    grep -qE "^${port_var}=" "$ENV_FILE" || warn ".env 没有 ${port_var}=，将使用 compose 内置默认端口"

    for other in container host db gunicorn celery; do
        if grep -qE '^[[:space:]]*DB_ENGINE=' "$ROOT/envs/$other.env" 2>/dev/null; then
            warn "envs/$other.env 里出现 DB_ENGINE=，会干扰 common.env 的唯一连接点，建议删掉"
        fi
    done
}

# 解析自检：只用 `compose config` 算模型，不起任何容器
verify_resolved() {
    local file="$1" target="$2" resolved
    command -v docker >/dev/null 2>&1 || { warn "没有 docker，跳过 compose 解析自检"; return 0; }
    if ! resolved="$(cd "$ROOT" && docker compose --env-file "$file" config 2>&1)"; then
        warn "compose 解析失败，跳过自检：$(printf '%s' "$resolved" | tail -n 1)"
        return 0
    fi
    if [ "$target" = mysql ]; then
        printf '%s\n' "$resolved" | grep -q 'DB_ENGINE: mysql' || return 1
        printf '%s\n' "$resolved" | grep -qE 'image: [^ ]*mysql:' || return 1
    else
        printf '%s\n' "$resolved" | grep -q 'DB_ENGINE: postgresql' || return 1
        printf '%s\n' "$resolved" | grep -qE 'image: ([^ ]*timescaledb|[^ ]*postgres):' || return 1
    fi
}

show_status() {
    local current="$1" volume image
    case "$current" in
        mysql) volume=network-ops-mysqldata; image="$(read_var DB_IMAGE_MYSQL mysql:8.4-oracle)" ;;
        postgresql) volume=network-ops-pgdata; image="$(read_var DB_IMAGE_POSTGRES timescale/timescaledb:2.27.1-pg16)" ;;
        *) volume="未知"; image="未知" ;;
    esac
    info "根 .env 当前后端: DB_SERVICE=$current"
    info "  镜像   : $image"
    info "  数据卷 : $volume"
    info "  可用   : postgresql | mysql"
    info "  切换   : ./scripts/switch-db.sh mysql    （只改配置，部署仍走 compose）"

    if [ "$current" = mysql ] || [ "$current" = postgresql ]; then
        if ! verify_resolved "$ENV_FILE" "$current"; then
            warn "当前 .env 解析出的后端与 DB_SERVICE=$current 不一致，用 --check 排查"
        fi
    fi
}

report() {
    local target="$1" volume image
    case "$target" in
        mysql) volume=network-ops-mysqldata; image="$(read_var DB_IMAGE_MYSQL mysql:8.4-oracle)" ;;
        postgresql) volume=network-ops-pgdata; image="$(read_var DB_IMAGE_POSTGRES timescale/timescaledb:2.27.1-pg16)" ;;
    esac
    info ""
    info "后端     : $target"
    info "镜像     : $image"
    info "数据卷   : $volume"
    info "部署     : docker compose up -d        # 首次用该后端会自动建空库并迁移"
    info "宿主直跑 : export DB_SERVICE=$target && ./scripts/deploy-host.sh deploy"
    info "回滚     : ./scripts/switch-db.sh <另一个后端>    # 卷不删，旧数据仍在"
    if [ "$target" = mysql ]; then
        info ""
        warn "MySQL 只面向新部署：不迁 PG 数据；DDL 不可回滚，迁移失败要删库重建（见 handbook/deploy.md）"
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

    if ! verify_resolved "$TMP" "$target"; then
        die "自检失败：compose 解析出的后端不是 ${target}（.env 未改动）"
    fi

    if [ "$check_only" -eq 1 ]; then
        info "校验通过：切到 ${target} 的配置自洽（未写入）"
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
