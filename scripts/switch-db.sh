#!/bin/bash
# 部署前切换数据库后端（PostgreSQL / MySQL）：改写根 .env 的 DB_SERVICE，并检查/修复数据库相关键。
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
#
# .env 只检查/修复数据库相关的 5 个键：
#   DB_SERVICE / DB_IMAGE_POSTGRES / DB_IMAGE_MYSQL / DB_PORT_POSTGRES / DB_PORT_MYSQL
#   --fix 只做安全修复：CRLF 与行尾空白归一、重复键保留最后一个（dotenv 的生效规则）、
#   补齐缺失键（默认值取自 .example.env）、DB_SERVICE 的 pg/postgres/mariadb 别名归一。
#   非法值不猜，报出来让人改；修不到全绿就不落盘（不写半成品）。
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="$ROOT/.env"
ENV_KEYS="DB_SERVICE DB_IMAGE_POSTGRES DB_IMAGE_MYSQL DB_PORT_POSTGRES DB_PORT_MYSQL"
TMP=""
ENV_ERRORS=0
ENV_WARNS=0

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
  ./scripts/switch-db.sh                    # 当前后端、.env 与内置库自检结果、连接地址
  ./scripts/switch-db.sh mysql              # 改写 .env 的 DB_SERVICE
  ./scripts/switch-db.sh mysql --dry-run    # 只显示改动
  ./scripts/switch-db.sh --check            # 只读校验 .env 的数据库键 + 配置链路
  ./scripts/switch-db.sh --fix              # 修复 .env：CRLF/行尾空白、重复键、缺失键
  ./scripts/switch-db.sh mysql --fix        # 先修 .env 再切换

  --check 与 --dry-run 都不写文件；--check 有错误时退出码 1。
后端取值: postgresql（默认）| mysql（CLI 也接受 pg/postgres/mariadb 别名）
EOF
}

default_port() {
    case "$1" in mysql) printf '3306\n' ;; *) printf '5432\n' ;; esac
}

# 读某个 env 文件里某个键的值：去行内注释、去引号与空白
read_key() {
    local file="$1" key="$2"
    sed -nE "s|^[[:space:]]*${key}=(.*)$|\1|p" "$file" 2>/dev/null \
        | tail -n 1 \
        | sed -E 's/(^|[[:space:]]+)#.*$//' \
        | sed -E 's/[[:space:]]+$//; s/^["'"'"']//; s/["'"'"']$//'
}

read_var() {
    local value
    value="$(read_key "$ENV_FILE" "$1")"
    printf '%s\n' "${value:-$2}"
}

read_service() { read_key "$ENV_FILE" DB_SERVICE; }

env_key_count() {
    grep -cE "^[[:space:]]*$2=" "$1" 2>/dev/null || true
}

env_default_value() {
    local key="$1" value=""
    if [ -f "$ROOT/.example.env" ]; then value="$(read_key "$ROOT/.example.env" "$key")"; fi
    if [ -z "$value" ]; then
        case "$key" in
            DB_SERVICE) value=postgresql ;;
            DB_IMAGE_POSTGRES) value=timescale/timescaledb:2.27.1-pg16 ;;
            DB_IMAGE_MYSQL) value=mysql:8.4-oracle ;;
            DB_PORT_POSTGRES) value=5432 ;;
            DB_PORT_MYSQL) value=3306 ;;
        esac
    fi
    printf '%s\n' "$value"
}

normalize() {
    case "$1" in
        postgresql|postgres|pg) printf 'postgresql\n' ;;
        mysql|mariadb) printf 'mysql\n' ;;
        *) die "不支持的数据库后端: $1（只接受 postgresql / mysql）" ;;
    esac
}

env_error() { ENV_ERRORS=$((ENV_ERRORS + 1)); info "  错误: $*"; }
env_warn() { ENV_WARNS=$((ENV_WARNS + 1)); info "  提示: $*"; }

# 检查 .env 的数据库键：存在、唯一、取值合法；CRLF / 行尾空白只提示
check_env_file() {
    local file="$1" key count value
    ENV_ERRORS=0
    ENV_WARNS=0

    if [ "$file" = "$ENV_FILE" ]; then
        info "数据库键检查（.env）："
    else
        info "数据库键检查（候选内容）："
    fi
    if grep -q $'\r' "$file"; then env_warn "文件含 CRLF 换行，值里会带上 \\r"; fi
    if grep -qE '[[:space:]]+$' "$file"; then env_warn "存在行尾空白"; fi

    for key in $ENV_KEYS; do
        count="$(env_key_count "$file" "$key")"
        if [ "$count" -eq 0 ]; then
            if grep -qE "^[[:space:]]*#[[:space:]]*${key}=" "$file"; then
                env_error "$key 只有被注释掉的一行，等于没配（--fix 可修）"
            else
                env_error "缺少 $key（--fix 可修）"
            fi
            continue
        fi
        [ "$count" -eq 1 ] || env_error "$key 出现 $count 次（dotenv 取最后一个；--fix 可修）"
        value="$(read_key "$file" "$key")"
        case "$key" in
            DB_SERVICE)
                case "$value" in
                    postgresql|mysql) ;;
                    "") env_error "DB_SERVICE 为空" ;;
                    *) env_error "DB_SERVICE=$value 非法（compose 要用它选模板，只接受 postgresql / mysql；pg/postgres/mariadb 别名可由 --fix 归一，其它需手工改）" ;;
                esac
                ;;
            DB_IMAGE_*)
                [ -n "$value" ] || env_error "$key 为空（需手工改）"
                ;;
            DB_PORT_*)
                if ! printf '%s' "$value" | grep -qE '^[0-9]+$'; then
                    env_error "$key=$value 不是端口号（需手工改）"
                elif [ "$value" -lt 1 ] || [ "$value" -gt 65535 ]; then
                    env_error "$key=$value 超出 1-65535（需手工改）"
                fi
                ;;
        esac
    done

    if [ "$ENV_ERRORS" -eq 0 ] && [ "$ENV_WARNS" -eq 0 ]; then
        info "  通过：5 个数据库键齐全且合法"
    elif [ "$ENV_ERRORS" -eq 0 ]; then
        info "  通过（${ENV_WARNS} 处提示，--fix 可修）"
    fi
}

# 生成修复后的候选文件：CRLF/行尾空白、重复键（保最后一个）、缺失键补齐
fix_into() {
    local dest="$1" key value added=0
    sed -E 's/\r$//; s/[[:space:]]+$//' "$ENV_FILE" \
        | awk -v keys="$ENV_KEYS" '
            BEGIN { nk = split(keys, K, " ") }
            {
                line[NR] = $0
                for (i = 1; i <= nk; i++)
                    if ($0 ~ "^[[:space:]]*" K[i] "=") { seen[K[i]] = 1; last[K[i]] = NR }
            }
            END {
                for (n = 1; n <= NR; n++) {
                    drop = 0
                    for (i = 1; i <= nk; i++) {
                        k = K[i]
                        if (seen[k] && line[n] ~ "^[[:space:]]*" k "=" && n != last[k]) drop = 1
                    }
                    if (!drop) print line[n]
                }
            }
        ' > "$dest"

    for key in $ENV_KEYS; do
        [ "$(env_key_count "$dest" "$key")" -eq 0 ] || continue
        value="$(env_default_value "$key")"
        if [ "$added" -eq 0 ]; then
            printf '\n# switch-db.sh --fix：补齐数据库键\n' >> "$dest"
            added=1
        fi
        printf '%s=%s\n' "$key" "$value" >> "$dest"
    done

    # DB_SERVICE 的别名归一（compose 只认 postgresql / mysql）
    value="$(read_key "$dest" DB_SERVICE)"
    case "$value" in
        postgres|pg) sed -i -E 's|^([[:space:]]*DB_SERVICE=)[^#[:space:]]*|\1postgresql|' "$dest" ;;
        mariadb) sed -i -E 's|^([[:space:]]*DB_SERVICE=)[^#[:space:]]*|\1mysql|' "$dest" ;;
    esac
}

# 取 compose 文件里某个 service / volume / secret 的块（按 2 空格缩进切）
block_of() {
    awk -v key="$2" '
        !inside && $0 ~ "^  " key ":[[:space:]]*$" { inside = 1; next }
        inside && ($0 ~ /^[^[:space:]]/ || $0 ~ "^  [A-Za-z0-9_.-]+:[[:space:]]*$") { exit }
        inside { print }
    ' "$1"
}

has() { printf '%s\n' "$1" | grep -qF -- "$2"; }

# 内置 db 服务相关配置是否自洽：模板引用、envs 嵌套、卷与 secret 声明、凭据内容。
# 纯文本核对——不解析 compose、不连库、不依赖 docker。
check_internal_db() {
    local target="$1" db_env="$ROOT/envs/db.env" common="$ROOT/envs/common.env"
    local block vol_block s vol name

    block="$(block_of "$ROOT/compose.db.yml" "$target")"
    [ -n "$block" ] || die "compose.db.yml 缺少 ${target} 模板"

    case "$target" in
        postgresql)
            has "$block" 'envs/db.env'                           || die "postgresql 模板没加载 envs/db.env，库拿不到 POSTGRES_*"
            has "$block" '- db_user'                             || die "postgresql 模板没挂 db_user secret，POSTGRES_USER_FILE 读不到"
            has "$block" '- db_password'                         || die "postgresql 模板没挂 db_password secret"
            has "$block" 'postgres_data:/var/lib/postgresql/data' || die "postgresql 模板的数据卷挂载点被改了"
            has "$block" '}:5432"'                               || die "postgresql 模板的容器端口不是 5432"
            has "$block" 'pg_isready'                            || die "postgresql 模板的 healthcheck 不是 pg_isready"
            ;;
        mysql)
            has "$block" 'envs/db.env'                           || die "mysql 模板没加载 envs/db.env，库拿不到 MYSQL_*"
            has "$block" '- db_password'                         || die "mysql 模板没挂 db_password secret，MYSQL_ROOT_PASSWORD_FILE 读不到"
            has "$block" 'mysql_data:/var/lib/mysql'             || die "mysql 模板的数据卷挂载点被改了"
            has "$block" '}:3306"'                               || die "mysql 模板的容器端口不是 3306"
            has "$block" 'mysqladmin ping'                       || die "mysql 模板的 healthcheck 不是 mysqladmin ping"
            ;;
    esac

    # 顶层 volumes / secrets 不被 extends 继承，必须在 compose.yml 里声明
    for s in postgres_data:network-ops-pgdata mysql_data:network-ops-mysqldata; do
        vol="${s%%:*}"; name="${s#*:}"
        vol_block="$(block_of "$ROOT/compose.yml" "$vol")"
        [ -n "$vol_block" ] || die "compose.yml 的 volumes 没声明 ${vol}（extends 不继承顶层 volumes）"
        has "$vol_block" "name: $name" || die "compose.yml 的 ${vol} 名字应为 $name"
    done
    for s in db_user db_password; do
        vol_block="$(block_of "$ROOT/compose.yml" "$s")"
        [ -n "$vol_block" ] || die "compose.yml 的 secrets 没声明 $s（${target} 模板引用了它）"
        has "$vol_block" 'file:' || die "compose.yml 的 secrets.$s 没有 file: 源"
    done

    # envs/db.env：只给 *_FILE，且按后端嵌套到镜像认的名字
    [ -f "$db_env" ] || die "envs/db.env 不存在（容器凭据层）"
    grep -qE '^DB_USER_FILE=/run/secrets/db_user$' "$db_env" || die "envs/db.env 的 DB_USER_FILE 应指向 /run/secrets/db_user"
    grep -qE '^DB_PASSWORD_FILE=/run/secrets/db_password$' "$db_env" || die "envs/db.env 的 DB_PASSWORD_FILE 应指向 /run/secrets/db_password"
    if grep -qE '^POSTGRES_USER=' "$db_env" || grep -qE '^POSTGRES_PASSWORD=' "$db_env"; then
        die "envs/db.env 不能同时给 POSTGRES_USER / POSTGRES_PASSWORD：与 *_FILE 冲突，官方 entrypoint 会直接退出"
    fi
    if grep -qE '^MYSQL_USER_FILE=' "$db_env"; then
        die "envs/db.env 不能给 MYSQL_USER_FILE：MySQL 镜像没有这个机制（用户名走 MYSQL_USER）"
    fi
    case "$target" in
        postgresql)
            grep -qF 'POSTGRES_USER_FILE=${DB_USER_FILE}' "$db_env" || die "envs/db.env 需要 POSTGRES_USER_FILE=\${DB_USER_FILE}"
            grep -qF 'POSTGRES_PASSWORD_FILE=${DB_PASSWORD_FILE}' "$db_env" || die "envs/db.env 需要 POSTGRES_PASSWORD_FILE=\${DB_PASSWORD_FILE}"
            ;;
        mysql)
            grep -qF 'MYSQL_PASSWORD_FILE=${DB_PASSWORD_FILE}' "$db_env" || die "envs/db.env 需要 MYSQL_PASSWORD_FILE=\${DB_PASSWORD_FILE}"
            grep -qF 'MYSQL_ROOT_PASSWORD_FILE=${DB_PASSWORD_FILE}' "$db_env" || die "envs/db.env 需要 MYSQL_ROOT_PASSWORD_FILE=\${DB_PASSWORD_FILE}"
            ;;
    esac

    # common.env：库名 / 账号只定义一次，镜像认的名字靠同文件嵌套
    local db_name db_user
    db_name="$(read_key "$common" DB_NAME)"
    db_user="$(read_key "$common" DB_USER)"
    [ -n "$db_name" ] || die "envs/common.env 的 DB_NAME 为空"
    [ -n "$db_user" ] || die "envs/common.env 的 DB_USER 为空"
    grep -qF 'POSTGRES_DB=${DB_NAME}' "$common" || die "envs/common.env 的 POSTGRES_DB 应嵌套 \${DB_NAME}"
    grep -qF 'MYSQL_DATABASE=${DB_NAME}' "$common" || die "envs/common.env 的 MYSQL_DATABASE 应嵌套 \${DB_NAME}"
    grep -qF 'MYSQL_USER=${DB_USER}' "$common" || die "envs/common.env 的 MYSQL_USER 应嵌套 \${DB_USER}"

    # 凭据内容与 DB_USER 对齐：PG 用文件的用户名建库，MySQL 用 MYSQL_USER 建账号
    if [ -s "$ROOT/envs/secrets/db_user" ]; then
        local sec_user
        sec_user="$(tr -d '\r\n' < "$ROOT/envs/secrets/db_user")"
        if [ -n "$sec_user" ] && [ "$sec_user" != "$db_user" ]; then
            warn "envs/secrets/db_user 与 envs/common.env 的 DB_USER 不一致：两种后端的建库账号会不同，应用可能连不上"
        fi
    fi
}

# 静态校验：后端链路 + 内置库配套
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

    for other in container host db gunicorn celery; do
        if grep -qE '^[[:space:]]*DB_ENGINE=' "$ROOT/envs/$other.env" 2>/dev/null; then
            warn "envs/$other.env 里出现 DB_ENGINE=，会干扰 common.env 的唯一连接点，建议删掉"
        fi
    done

    # 凭据只在容器里走 /run/secrets/*；缺了说明还没在部署机上生成，不是配置错误
    local missing="" s
    for s in db_user db_password; do
        [ -s "$ROOT/envs/secrets/$s" ] || missing="$missing $s"
    done
    [ -z "$missing" ] || warn "envs/secrets/ 缺少:$missing（容器部署需要，在部署机上生成：bash envs/secrets/generate.sh）"

    check_internal_db "$target"
}

# 连接地址：切换后端不会改 DB_HOST / DB_PORT，提示清楚库在哪里
show_endpoints() {
    local target="$1" c_host c_port h_host h_port volume
    c_host="$(read_key "$ROOT/envs/container.env" DB_HOST)"
    c_port="$(read_key "$ROOT/envs/container.env" DB_PORT)"
    h_host="$(read_key "$ROOT/envs/host.env" DB_HOST)"
    h_port="$(read_key "$ROOT/envs/host.env" DB_PORT)"

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
    explicit_port="$(read_key "$ROOT/envs/container.env" DB_PORT)"
    [ -z "$explicit_port" ] || case "$explicit_port" in
        "$(default_port "$target")") ;;
        *) warn "envs/container.env 显式写了 DB_PORT=$explicit_port，与 ${target} 默认端口不一致，切换后端不会改它" ;;
    esac
    explicit_port="$(read_key "$ROOT/envs/host.env" DB_PORT)"
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

    if check_env_file "$ENV_FILE" >/dev/null; then
        if [ "$ENV_ERRORS" -eq 0 ]; then
            info "  .env   : 数据库键正常（${ENV_WARNS} 处提示）"
        else
            info "  .env   : ${ENV_ERRORS} 个错误 / ${ENV_WARNS} 处提示（--check 看详情，--fix 修可修的）"
        fi
    fi

    if [ "$current" = mysql ] || [ "$current" = postgresql ]; then
        if ( check_internal_db "$current" ) 2>/dev/null; then
            info "  内部库 : 自检通过"
        else
            info "  内部库 : 自检未通过（./scripts/switch-db.sh --check 看原因）"
        fi
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
    local target="" dry_run=0 check_only=0 fix=0 arg
    for arg in "$@"; do
        case "$arg" in
            -h|--help) usage; return 0 ;;
            --dry-run) dry_run=1 ;;
            --check) check_only=1 ;;
            --fix) fix=1 ;;
            -*) die "未知参数: $arg（用 --help 看用法）" ;;
            *) [ -z "$target" ] || die "一次只能指定一个后端"; target="$arg" ;;
        esac
    done

    [ -f "$ENV_FILE" ] || die ".env 不存在：先 cp .example.env .env 再按需修改"
    [ -z "$target" ] || target="$(normalize "$target")"

    local current
    current="$(read_service)"
    if [ -z "$current" ]; then
        if [ "$fix" -eq 1 ]; then
            current=postgresql
        else
            die ".env 缺少 DB_SERVICE=（用 --fix 补齐，或手工加一行按 postgresql 兜底）"
        fi
    fi

    # 只看现状
    if [ -z "$target" ] && [ "$fix" -eq 0 ] && [ "$check_only" -eq 0 ]; then
        show_status "$current"
        return 0
    fi

    # 1) 候选文件：--fix 先做安全修复
    TMP="$(mktemp "$ROOT/.env.tmp.XXXXXX")"
    if [ "$fix" -eq 1 ]; then
        fix_into "$TMP"
    else
        cp "$ENV_FILE" "$TMP"
    fi

    # 2) 按目标改 DB_SERVICE
    if [ -n "$target" ]; then
        sed -i -E "s|^([[:space:]]*DB_SERVICE=)[^#[:space:]]*(.*)$|\1${target}\2|" "$TMP"
    fi
    chmod --reference="$ENV_FILE" "$TMP" 2>/dev/null || true

    # 3) 落盘前必须检查通过：不写半成品
    check_env_file "$TMP"

    # 4) --check 或切换时，同时校验后端链路与内置库配套
    if [ "$check_only" -eq 1 ] || [ -n "$target" ]; then
        check_config "${target:-$current}"
    fi

    if [ "$ENV_ERRORS" -gt 0 ]; then
        if [ "$check_only" -eq 1 ]; then
            info ""
            info "共 ${ENV_ERRORS} 处错误（--fix 可修 CRLF / 行尾空白 / 重复键 / 缺失键）"
            return 1
        fi
        if [ "$fix" -eq 1 ]; then
            die "还有 ${ENV_ERRORS} 处需要手工改（见上），.env 未改动；改掉后再跑一次 --fix"
        fi
        die "先处理上面的 ${ENV_ERRORS} 处错误（--fix 可修 CRLF/重复/缺失），.env 未改动"
    fi

    if cmp -s "$ENV_FILE" "$TMP"; then
        info ".env 无需改动"
        if [ "$check_only" -eq 1 ]; then
            info "校验通过：数据库键、后端链路与内置库配置自洽（未写入，未连库）"
            show_endpoints "${target:-$current}"
        elif [ -n "$target" ]; then
            report "$target"
        fi
        return 0
    fi

    info "--- .env 改动 ---"
    diff -u --label .env --label .env.new "$ENV_FILE" "$TMP" || true

    if [ "$dry_run" -eq 1 ] || [ "$check_only" -eq 1 ]; then
        info ""
        info "未写入（--dry-run / --check 只读）。去掉后即生效。"
        if [ "$check_only" -eq 1 ]; then
            show_endpoints "${target:-$current}"
        fi
        return 0
    fi

    mv "$TMP" "$ENV_FILE"
    TMP=""
    info ""
    if [ -n "$target" ]; then
        info "已写入 $ENV_FILE"
        report "$target"
    else
        info "已修复 $ENV_FILE"
    fi
}

main "$@"
