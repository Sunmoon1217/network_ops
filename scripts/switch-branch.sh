#!/bin/bash
# 切换分支并自动设置数据库环境变量
set -e

BRANCH_NAME="${1:-}"

if [ -z "$BRANCH_NAME" ]; then
    echo "用法: ./scripts/switch-branch.sh <branch_name>"
    echo "当前分支: $(git branch --show-current)"
    echo "可用分支:"
    git branch --list | sed 's/^[* ]*/  /'
    exit 0
fi

# 切换分支
git checkout "$BRANCH_NAME"

# 生成数据库名
DB_NAME="netops_$(echo "$BRANCH_NAME" | tr '/' '_' | tr '-' '_')"

# 写入 .env.db
cat > /home/sunmoon/projects/network_ops/.env.db << EOF
# 分支: $BRANCH_NAME
POSTGRES_DB=$DB_NAME
EOF

echo "已切换到 $BRANCH_NAME"
echo "数据库: $DB_NAME"
echo ""
echo "执行以下命令加载环境变量:"
echo "  export \$(cat .env.db | xargs)"
echo "  uv run python manage.py migrate"
