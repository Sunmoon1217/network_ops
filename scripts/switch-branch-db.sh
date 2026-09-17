#!/bin/bash
# 切换分支并设置数据库环境变量
set -e

BRANCH_NAME="${1:-$(git branch --show-current)}"
DB_NAME="netops_$(echo "$BRANCH_NAME" | tr '/' '_' | tr '-' '_')"

# 创建数据库（如果不存在）
./scripts/create-branch-db.sh "$BRANCH_NAME"

# 生成 .env.db
cat > .env.db << EOF
POSTGRES_DB=$DB_NAME
EOF

echo "切换到 $BRANCH_NAME，数据库: $DB_NAME"
echo "执行: export \$(cat .env.db | xargs) && uv run python manage.py migrate"
