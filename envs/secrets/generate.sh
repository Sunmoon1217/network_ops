#!/bin/bash
# 生成 docker secrets 文件到 envs/secrets/（db_user / db_password / 四个 aliyun_*）。
# 默认沿用 .env 的值（避免已有数据卷密码被改）；--random 生成随机密码，--force 覆盖。
# 凭据语义与轮换注意见 envs/secrets/README.md 与 handbook/deploy.md。

set -eu

cd "$(dirname "$0")/../.."   # 切到项目根：.env 在根、密钥在 envs/secrets/

SECRETS_DIR=envs/secrets
MODE=from-env
FORCE=0

usage() {
    cat <<'EOF'
生成 docker secrets 文件（db_user / db_password / 四个 aliyun_*）

用法：
  bash envs/secrets/generate.sh            # 默认：沿用 .env 里现有的 DB_USER / DB_PASSWORD
  bash envs/secrets/generate.sh --random   # 生成随机强密码（只适用于全新的数据卷）
  bash envs/secrets/generate.sh --force    # 覆盖已存在的文件
EOF
}

for arg in "$@"; do
    case "$arg" in
        --random) MODE=random ;;
        --force) FORCE=1 ;;
        -h | --help)
            usage
            exit 0
            ;;
        *)
            echo "未知参数：$arg（用 --help 看用法）" >&2
            exit 2
            ;;
    esac
done

# 从 .env 取值（简化解析：行内注释、行尾空格、成对引号、$$ → $；复杂密码请手工建文件）
env_value() {
    [ -f .env ] || return 0
    sed -n "s/^$1=//p" .env | tail -n 1 |
        sed -e 's/[[:space:]]#.*$//' -e 's/[[:space:]]*$//' \
            -e 's/^"\(.*\)"$/\1/' -e "s/^'\(.*\)'$/\1/" -e 's/\$\$/\$/g'
}

random_secret() {
    # 只取字母数字：避免各类 cfg/URL 里再出现转义问题
    tr -dc 'A-Za-z0-9' < /dev/urandom | head -c 32
}

write_secret() {
    name=$1
    value=$2
    path="$SECRETS_DIR/$name"
    if [ -e "$path" ] && [ "$FORCE" -ne 1 ]; then
        echo "跳过 $path（已存在；要覆盖加 --force）"
        return 0
    fi
    printf '%s\n' "$value" > "$path"
    chmod 600 "$path"
    echo "已写入 $path"
}

# 从环境变量或 .env 取一个值（环境变量优先）
pick() {
    eval "value=\${$1:-}"
    [ -n "$value" ] || value=$(env_value "$1")
    printf '%s' "$value"
}

# 允许为空的 secret：文件必须存在（compose 会校验），内容可以之后再填
write_optional_secret() {
    name=$1
    value=$2
    path="$SECRETS_DIR/$name"
    if [ -e "$path" ] && [ "$FORCE" -ne 1 ]; then
        echo "跳过 $path（已存在；要覆盖加 --force）"
        return 0
    fi
    printf '%s\n' "$value" > "$path"
    chmod 600 "$path"
    if [ -z "$value" ]; then
        echo "已创建空文件 $path（未提供凭据：在环境变量或 .env 里填 ALIYUN_* 后重跑 --force）"
    else
        echo "已写入 $path"
    fi
}

umask 077
mkdir -p "$SECRETS_DIR"

user=$(env_value DB_USER)
[ -n "$user" ] || user=netops

if [ "$MODE" = random ]; then
    password=$(random_secret)
    echo "使用随机密码（请确认数据卷是新的，或之后进库 ALTER USER 改密码）"
else
    password=$(env_value DB_PASSWORD)
    [ -n "$password" ] || password=netops_password
    echo "沿用 .env 里的 DB_USER / DB_PASSWORD（没有就用默认值）"
fi

write_secret db_user "$user"
write_secret db_password "$password"

# 阿里云 AK/SK：来源优先级 环境变量 > 根 .env；缺省写空文件
write_optional_secret prod_ak "$(pick ALIYUN_PROD_ACCESS_KEY_ID)"
write_optional_secret prod_sk "$(pick ALIYUN_PROD_ACCESS_KEY_SECRET)"
write_optional_secret test_ak "$(pick ALIYUN_TEST_ACCESS_KEY_ID)"
write_optional_secret test_sk "$(pick ALIYUN_TEST_ACCESS_KEY_SECRET)"

cat <<'EOF'

下一步：
  docker compose up -d db            # 首次部署：数据卷会按这份凭据初始化
  docker compose up -d --build app worker
查看（可选）：cat envs/secrets/db_password
EOF
