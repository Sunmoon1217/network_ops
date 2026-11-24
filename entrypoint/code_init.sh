#!/bin/sh
# code-init 容器入口：把镜像里的代码与静态产物权威铺进 code / static 两个命名卷
# （先清再铺，避免上一版带 hash 的遗留资源）。卷布局与重跑时机见 handbook/deploy.md。

set -e

SRC=/opt/netops
CODE_DIR=/app
STATIC_DIR=/static

# 代码 → code 卷（app / worker / consumer / beat 以 /app:ro 使用）
rm -rf "${CODE_DIR:?}/"*
cp -a "${SRC}/code/." "${CODE_DIR}/"

# 静态产物 → static 卷（nginx 以 /usr/share/nginx/html:ro 使用）
rm -rf "${STATIC_DIR:?}/"*
cp -a "${SRC}/http/." "${STATIC_DIR}/"

echo "code initialized: code=$(find "${CODE_DIR}" -type f | wc -l) files, static=$(find "${STATIC_DIR}" -type f | wc -l) files"
