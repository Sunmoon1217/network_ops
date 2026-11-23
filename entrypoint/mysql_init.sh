#!/bin/sh
# 为应用账号授予「测试库」的全部权限（MySQL 初始化脚本）。
#
# 为什么用库名模式：MySQL 的库级权限存放在 mysql.db，键是「库名模式」，不绑定库对象。
# Django 每次测试会 DROP/CREATE test_<库名>（pytest-xdist 还会追加 _gwN），
# 授权一次后，之后新建的测试库自动继承，不需要每次重建后再授权。
#
# 触发时机：官方 mysql 镜像只在数据目录为空（首次初始化）时执行
# /docker-entrypoint-initdb.d/ 下的脚本。数据卷已存在时手动跑一次：
#   docker compose exec -u root db sh /docker-entrypoint-initdb.d/01-grant-test-db.sh
set -eu

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
