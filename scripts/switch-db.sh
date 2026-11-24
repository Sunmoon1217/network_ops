#!/bin/bash
# 切换数据库后端（postgresql / mysql）：同步改写根 .env 的 DB_SERVICE 与 envs/common.env
# 里 DB_ENGINE 的宿主默认值，并做只读自检（.env 五个数据库键、后端链路、内置库配置）。
# 不改连接地址、不连库、不启停容器；完整语义见 handbook/deploy.md「MySQL 后端」。
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="$ROOT/.env"
COMMON_FILE="$ROOT/envs/common.env"
ENV_KEYS="DB_SERVICE DB_IMAGE_POSTGRES DB_IMAGE_MYSQL DB_PORT_POSTGRES DB_PORT_MYSQL"
TMP=""
COMMON_TMP=""
ENV_ERRORS=0
ENV_WARNS=0
CFG_ERRORS=0

cleanup() {
    if [ -n "$TMP" ] && [ -f "$TMP" ]; then rm -f "$TMP"; fi
    if [ -n "$COMMON_TMP" ] && [ -f "$COMMON_TMP" ]; then rm -f "$COMMON_TMP"; fi
    return 0
}
trap cleanup EXIT

info() { printf '%s\n' "$*"; }
warn() { printf '警告: %s\n' "$*" >&2; }
die() { printf '错误: %s\n' "$*" >&2; exit 1; }

usage() {
    cat <<'EOF'
用法:
  ./scripts/switch-db.sh                    # 本帮助
  ./scripts/switch-db.sh mysql              # 同步改写 .env 与 envs/common.env（检查通过才落盘）
  ./scripts/switch-db.sh mysql --dry-run    # 只显示两个文件的改动，不写文件
  ./scripts/switch-db.sh --check            # 只读自检：当前后端、.env 键、后端链路、内置库、连接地址

  --check 只报告问题、不改文件；有错误时退出码 1。
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

# 某后端用的内置库镜像（只用于展示）
image_for() {
    case "$1" in
        mysql) read_var DB_IMAGE_MYSQL mysql:8.4-oracle ;;
        postgresql) read_var DB_IMAGE_POSTGRES timescale/timescaledb:2.27.1-pg16 ;;
        *) printf '未知\n' ;;
    esac
}

env_key_count() {
    grep -cE "^[[:space:]]*$2=" "$1" 2>/dev/null || true
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
cfg_error() { CFG_ERRORS=$((CFG_ERRORS + 1)); info "  错误: $*"; }

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
                env_error "$key 只有被注释掉的一行，等于没配"
            else
                env_error "缺少 $key"
            fi
            continue
        fi
        [ "$count" -eq 1 ] || env_error "$key 出现 $count 次（dotenv 取最后一个）"
        value="$(read_key "$file" "$key")"
        case "$key" in
            DB_SERVICE)
                case "$value" in
                    postgresql|mysql) ;;
                    "") env_error "DB_SERVICE 为空" ;;
                    *) env_error "DB_SERVICE=$value 非法（compose 要用它选模板，只接受 postgresql / mysql）" ;;
                esac
                ;;
            DB_IMAGE_*)
                [ -n "$value" ] || env_error "$key 为空"
                ;;
            DB_PORT_*)
                if ! printf '%s' "$value" | grep -qE '^[0-9]+$'; then
                    env_error "$key=$value 不是端口号"
                elif [ "$value" -lt 1 ] || [ "$value" -gt 65535 ]; then
                    env_error "$key=$value 超出 1-65535"
                fi
                ;;
        esac
    done

    if [ "$ENV_ERRORS" -eq 0 ] && [ "$ENV_WARNS" -eq 0 ]; then
        info "  通过：5 个数据库键齐全且合法"
    elif [ "$ENV_ERRORS" -eq 0 ]; then
        info "  通过（${ENV_WARNS} 处提示）"
    fi
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
    local target="$1" db_env="$ROOT/envs/db.env" common="${2:-$ROOT/envs/common.env}"
    local block vol_block s vol name

    block="$(block_of "$ROOT/compose.db.yml" "$target")"
    if [ -z "$block" ]; then
        cfg_error "compose.db.yml 缺少 ${target} 模板"
        return
    fi

    case "$target" in
        postgresql)
            has "$block" 'envs/db.env'                           || cfg_error "postgresql 模板没加载 envs/db.env，库拿不到 POSTGRES_*"
            has "$block" '- db_user'                             || cfg_error "postgresql 模板没挂 db_user secret，POSTGRES_USER_FILE 读不到"
            has "$block" '- db_password'                         || cfg_error "postgresql 模板没挂 db_password secret"
            has "$block" 'postgres_data:/var/lib/postgresql/data' || cfg_error "postgresql 模板的数据卷挂载点被改了"
            has "$block" '}:5432"'                               || cfg_error "postgresql 模板的容器端口不是 5432"
            has "$block" 'pg_isready'                            || cfg_error "postgresql 模板的 healthcheck 不是 pg_isready"
            ;;
        mysql)
            has "$block" 'envs/db.env'                           || cfg_error "mysql 模板没加载 envs/db.env，库拿不到 MYSQL_*"
            has "$block" '- db_password'                         || cfg_error "mysql 模板没挂 db_password secret，MYSQL_ROOT_PASSWORD_FILE 读不到"
            has "$block" 'mysql_data:/var/lib/mysql'             || cfg_error "mysql 模板的数据卷挂载点被改了"
            has "$block" '}:3306"'                               || cfg_error "mysql 模板的容器端口不是 3306"
            has "$block" 'mysqladmin ping'                       || cfg_error "mysql 模板的 healthcheck 不是 mysqladmin ping"
            ;;
    esac

    # 顶层 volumes / secrets 不被 extends 继承，必须在 compose.yml 里声明
    for s in postgres_data:network-ops-pgdata mysql_data:network-ops-mysqldata; do
        vol="${s%%:*}"; name="${s#*:}"
        vol_block="$(block_of "$ROOT/compose.yml" "$vol")"
        [ -n "$vol_block" ] || cfg_error "compose.yml 的 volumes 没声明 ${vol}（extends 不继承顶层 volumes）"
        has "$vol_block" "name: $name" || cfg_error "compose.yml 的 ${vol} 名字应为 $name"
    done
    for s in db_user db_password; do
        vol_block="$(block_of "$ROOT/compose.yml" "$s")"
        [ -n "$vol_block" ] || cfg_error "compose.yml 的 secrets 没声明 $s（${target} 模板引用了它）"
        has "$vol_block" 'file:' || cfg_error "compose.yml 的 secrets.$s 没有 file: 源"
    done

    # envs/db.env：只给 *_FILE，且按后端嵌套到镜像认的名字
    if [ ! -f "$db_env" ]; then
        cfg_error "envs/db.env 不存在（容器凭据层）"
        return
    fi
    grep -qE '^DB_USER_FILE=/run/secrets/db_user$' "$db_env" || cfg_error "envs/db.env 的 DB_USER_FILE 应指向 /run/secrets/db_user"
    grep -qE '^DB_PASSWORD_FILE=/run/secrets/db_password$' "$db_env" || cfg_error "envs/db.env 的 DB_PASSWORD_FILE 应指向 /run/secrets/db_password"
    if grep -qE '^POSTGRES_USER=' "$db_env" || grep -qE '^POSTGRES_PASSWORD=' "$db_env"; then
        cfg_error "envs/db.env 不能同时给 POSTGRES_USER / POSTGRES_PASSWORD：与 *_FILE 冲突，官方 entrypoint 会直接退出"
    fi
    if grep -qE '^MYSQL_USER_FILE=' "$db_env"; then
        cfg_error "envs/db.env 不能给 MYSQL_USER_FILE：MySQL 镜像没有这个机制（用户名走 MYSQL_USER）"
    fi
    case "$target" in
        postgresql)
            grep -qF 'POSTGRES_USER_FILE=${DB_USER_FILE}' "$db_env" || cfg_error "envs/db.env 需要 POSTGRES_USER_FILE=\${DB_USER_FILE}"
            grep -qF 'POSTGRES_PASSWORD_FILE=${DB_PASSWORD_FILE}' "$db_env" || cfg_error "envs/db.env 需要 POSTGRES_PASSWORD_FILE=\${DB_PASSWORD_FILE}"
            ;;
        mysql)
            grep -qF 'MYSQL_PASSWORD_FILE=${DB_PASSWORD_FILE}' "$db_env" || cfg_error "envs/db.env 需要 MYSQL_PASSWORD_FILE=\${DB_PASSWORD_FILE}"
            grep -qF 'MYSQL_ROOT_PASSWORD_FILE=${DB_PASSWORD_FILE}' "$db_env" || cfg_error "envs/db.env 需要 MYSQL_ROOT_PASSWORD_FILE=\${DB_PASSWORD_FILE}"
            ;;
    esac

    # common.env：库名 / 账号只定义一次，镜像认的名字靠同文件嵌套
    local db_name db_user
    db_name="$(read_key "$common" DB_NAME)"
    db_user="$(read_key "$common" DB_USER)"
    [ -n "$db_name" ] || cfg_error "envs/common.env 的 DB_NAME 为空"
    [ -n "$db_user" ] || cfg_error "envs/common.env 的 DB_USER 为空"
    grep -qF 'POSTGRES_DB=${DB_NAME}' "$common" || cfg_error "envs/common.env 的 POSTGRES_DB 应嵌套 \${DB_NAME}"
    grep -qF 'MYSQL_DATABASE=${DB_NAME}' "$common" || cfg_error "envs/common.env 的 MYSQL_DATABASE 应嵌套 \${DB_NAME}"
    grep -qF 'MYSQL_USER=${DB_USER}' "$common" || cfg_error "envs/common.env 的 MYSQL_USER 应嵌套 \${DB_USER}"

    # 凭据内容与 DB_USER 对齐：PG 用文件的用户名建库，MySQL 用 MYSQL_USER 建账号
    if [ -s "$ROOT/envs/secrets/db_user" ]; then
        local sec_user
        sec_user="$(tr -d '\r\n' < "$ROOT/envs/secrets/db_user")"
        if [ -n "$sec_user" ] && [ "$sec_user" != "$db_user" ]; then
            warn "envs/secrets/db_user 与 envs/common.env 的 DB_USER 不一致：两种后端的建库账号会不同，应用可能连不上"
        fi
    fi
}

# 后端链路：一个开关 → Django 驱动 / compose 模板选择
check_chain() {
    local target="$1" common="${2:-$ROOT/envs/common.env}" other
    local expected="DB_ENGINE=\${DB_SERVICE:-${target}}"

    grep -qF "$expected" "$common" \
        || cfg_error "envs/common.env 的 DB_ENGINE 应为 ${expected}（宿主默认值跟随当前后端；运行 ./scripts/switch-db.sh ${target} 同步）"
    grep -qE "^  ${target}:[[:space:]]*$" "$ROOT/compose.db.yml" \
        || cfg_error "compose.db.yml 缺少 ${target} 模板"
    grep -qF 'service: ${DB_SERVICE:-postgresql}' "$ROOT/compose.yml" \
        || cfg_error "compose.yml 的 db 服务应写 service: \${DB_SERVICE:-postgresql}"

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
}

# 后端链路 + 内置库一并检查（切换路径用；第二个参数是候选 common.env）
check_config() {
    check_chain "$1" "$2"
    check_internal_db "$1" "$2"
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

report() {
    local target="$1" image
    image="$(image_for "$target")"
    info ""
    info "后端     : $target"
    info "镜像     : $image（仅内置 db 服务使用）"
    info "部署     : docker compose up -d        # 应用按 container.env 的 DB_HOST 连库"
    info "宿主直跑 : ./scripts/deploy-host.sh deploy（common.env 默认值已同步为 $target；进程环境仍可覆盖）"
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

    # 无参数：只给用法
    if [ "$#" -eq 0 ]; then
        usage
        return 0
    fi

    [ -f "$ENV_FILE" ] || die ".env 不存在：先 cp .example.env .env 再按需修改"
    [ -f "$COMMON_FILE" ] || die "envs/common.env 不存在：先 cp envs/example/*.env envs/"
    [ -z "$target" ] || target="$(normalize "$target")"

    local current
    current="$(read_service)"
    [ -n "$current" ] || die ".env 缺少 DB_SERVICE= 这一行（容器侧靠它选后端）"

    # --check：只读自检 + 校验，逐项打印结果，发现问题全部列出来，不改文件
    if [ "$check_only" -eq 1 ]; then
        local backend="$current" before
        if [ -n "$target" ]; then backend="$target"; fi

        info "当前后端 : DB_SERVICE=$current（$(image_for "$current")，仅内置 db 服务使用）"
        if [ "$backend" != "$current" ]; then
            info "目标后端 : $backend（$(image_for "$backend")）"
        fi

        check_env_file "$ENV_FILE"

        before=$CFG_ERRORS
        info "后端链路 :"
        check_chain "$backend"
        if [ "$CFG_ERRORS" -eq "$before" ]; then
            info "  通过：DB_SERVICE → DB_ENGINE 连接点、compose 模板与 extends 写法"
        fi

        before=$CFG_ERRORS
        info "内置库（$backend）："
        check_internal_db "$backend"
        if [ "$CFG_ERRORS" -eq "$before" ]; then
            info "  通过：模板 / 卷与 secret 声明 / envs 嵌套 / 凭据一致"
        fi

        info "连接地址 :"
        show_endpoints "$backend"

        info ""
        if [ "$ENV_ERRORS" -gt 0 ] || [ "$CFG_ERRORS" -gt 0 ]; then
            info "共 $ENV_ERRORS 处 .env 错误、$CFG_ERRORS 处配置错误、$ENV_WARNS 处提示（只报告，不改文件）"
            return 1
        fi
        info "全部通过（$backend）：数据库键、后端链路与内置库配置自洽（未写入，未连库；$ENV_WARNS 处提示）"
        return 0
    fi

    # 只给 --dry-run、没给后端：没有可做的事
    if [ -z "$target" ]; then
        usage
        return 0
    fi

    # 候选文件：同时换 DB_SERVICE 与 common.env 的宿主默认值，检查通过才落盘
    TMP="$(mktemp "$ROOT/.env.tmp.XXXXXX")"
    COMMON_TMP="$(mktemp "$ROOT/common.env.tmp.XXXXXX")"
    cp "$ENV_FILE" "$TMP"
    cp "$COMMON_FILE" "$COMMON_TMP"
    sed -i -E "s|^([[:space:]]*DB_SERVICE=)[^#[:space:]]*(.*)$|\1${target}\2|" "$TMP"
    # 只替换 ${DB_SERVICE:-...} 里的默认值，保留 ${} 插值链路与行尾内容
    sed -i -E 's|^([[:space:]]*DB_ENGINE=\$\{DB_SERVICE:-)[^}]*\}|\1'"${target}"'}|' "$COMMON_TMP"
    chmod --reference="$ENV_FILE" "$TMP" 2>/dev/null || true
    chmod --reference="$COMMON_FILE" "$COMMON_TMP" 2>/dev/null || true

    check_env_file "$TMP"
    check_config "$target" "$COMMON_TMP"
    if [ "$ENV_ERRORS" -gt 0 ] || [ "$CFG_ERRORS" -gt 0 ]; then
        die "配置检查未通过（.env 错误 $ENV_ERRORS / 配置错误 $CFG_ERRORS），两个文件都未改动"
    fi

    if cmp -s "$ENV_FILE" "$TMP" && cmp -s "$COMMON_FILE" "$COMMON_TMP"; then
        info "当前已经是 ${target}，无需改动"
        report "$target"
        return 0
    fi

    info "--- .env 改动 ---"
    diff -u --label .env --label .env.new "$ENV_FILE" "$TMP" || true
    info "--- envs/common.env 改动 ---"
    diff -u --label envs/common.env --label envs/common.env.new "$COMMON_FILE" "$COMMON_TMP" || true

    if [ "$dry_run" -eq 1 ]; then
        info ""
        info "未写入（--dry-run）。去掉后即生效。"
        return 0
    fi

    mv "$TMP" "$ENV_FILE"
    TMP=""
    mv "$COMMON_TMP" "$COMMON_FILE" || die "envs/common.env 写入失败；请重跑 ./scripts/switch-db.sh ${target} 修正"
    COMMON_TMP=""
    info ""
    info "已写入 $ENV_FILE 与 $COMMON_FILE"
    report "$target"
}

main "$@"
