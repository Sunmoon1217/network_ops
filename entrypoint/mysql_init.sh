#!/bin/sh
# 为应用账号授予测试库权限（MySQL 首次初始化脚本）：授权按库名模式 test_<库>% 生效；
# prod 直接跳过。触发时机与手动执行方式见 handbook/deploy.md。

set -eu

# 环境类型：初始化阶段由 env_file 注入；手动 exec 不继承容器环境，回退读 PID 1 的 environ。
# 只允许 dev / container，其余（prod、未设置、拼错）一律跳过——宁可不授权，也不在 prod 放权。
env_kind="${DJANGO_ENV:-}"
if [ -z "$env_kind" ] && [ -r /proc/1/environ ]; then
    env_kind=$(tr '\0' '\n' < /proc/1/environ 2>/dev/null | sed -n 's/^DJANGO_ENV=//p' | tail -n 1)
fi
case "$env_kind" in
    dev|container) ;;
    *)
        echo "DJANGO_ENV=${env_kind:-<unset>} 不是 dev/container，跳过测试库授权" >&2
        exit 0
        ;;
esac

db="${MYSQL_DATABASE:-${DB_NAME:-netops}}"
user="${MYSQL_USER:-${DB_USER:-netops}}"

# GRANT 里 _ / % 是通配符，库名自身的这两个字符要转义成字面量
db_escaped=$(printf '%s' "$db" | sed 's/_/\\_/g; s/%/\\%/g')

sql="GRANT ALL PRIVILEGES ON \`test\\_${db_escaped}%\`.* TO '${user}'@'%';"

# 初始化脚本由 entrypoint 在 `gosu mysql` 之后执行，读不到 600 的 secret；
# 入口在降权前已 file_env 导出 MYSQL_ROOT_PASSWORD，这里优先用它。
# 手动 exec（root 身份）没有该变量，回退读 secret 文件。
if [ -z "${MYSQL_ROOT_PASSWORD:-}" ]; then
    MYSQL_ROOT_PASSWORD="$(cat "${DB_PASSWORD_FILE:-/run/secrets/db_password}")"
fi

MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql --protocol=socket -uroot -e "$sql"
