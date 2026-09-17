#!/bin/bash
# 重建当前分支的数据库
set -e

BRANCH_NAME="${1:-$(git branch --show-current)}"
DB_NAME="netops_$(echo "$BRANCH_NAME" | tr '/' '_' | tr '-' '_')"

echo "重建数据库: $DB_NAME"

docker compose exec -T db psql -U netops -d postgres -c \
  "DROP DATABASE IF EXISTS $DB_NAME;" && \
docker compose exec -T db psql -U netops -d postgres -c \
  "CREATE DATABASE $DB_NAME;" && \
echo "数据库 $DB_NAME 已重建"

POSTGRES_DB=$DB_NAME uv run python manage.py migrate
echo "迁移完成"
