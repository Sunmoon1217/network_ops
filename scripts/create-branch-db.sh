#!/bin/bash
# 为当前分支创建专属数据库
set -e

BRANCH_NAME="${1:-$(git branch --show-current)}"
DB_NAME="netops_$(echo "$BRANCH_NAME" | tr '/' '_' | tr '-' '_')"

echo "分支: $BRANCH_NAME → 数据库: $DB_NAME"

docker compose exec -T db psql -U netops -d postgres -tc \
  "SELECT 1 FROM pg_database WHERE datname='$DB_NAME'" | grep -q 1 && \
  echo "已存在" && exit 0

docker compose exec -T db psql -U netops -d postgres -c "CREATE DATABASE $DB_NAME;"
echo "创建成功"
