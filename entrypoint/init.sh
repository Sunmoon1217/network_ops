#!/bin/sh
#
# code-init 容器入口：把代码镜像里的内容权威铺进两个命名卷。
#
#   1) 代码 → code_data（app/worker/consumer 挂 /app:ro）
#   2) 静态产物 → static_data（nginx 挂 /usr/share/nginx/html:ro）
#
# 静态卷的目录布局**按 URL 前缀设计**，nginx 一个 root 就能覆盖全部静态请求：
#   <卷>/index.html   ← Vite 产物（SPA 入口，/ 走 try_files 兜底）
#   <卷>/assets/*     ← Vite 产物（/assets/*）
#   <卷>/static/*     ← collectstatic 产物（/static/*，STATIC_URL 就是 /static/）
#
# 两次复制都是**权威**的（先清再铺），否则上一版带 hash 的遗留资源会一直堆在卷里，
# 且删掉的源文件会在卷里残留。清卷根时要**排除 static/**：它由下一步单独同步。

set -e

CODE_DIR=/opt/netops/code
STATIC_DIR=/static

# 1) 代码 → code_data（权威覆盖）
rm -rf "${CODE_DIR:?}/"*
cp -a /app/. "${CODE_DIR}/"

# 2) Vite 产物 → 静态卷根；保留 static/ 给下一步
mkdir -p "${STATIC_DIR}/static"
find "${STATIC_DIR}" -mindepth 1 -maxdepth 1 ! -name static -exec rm -rf {} +
cp -a /app/frontend/dist/. "${STATIC_DIR}/"

# 3) collectstatic 产物 → 静态卷的 static/ 子目录
find "${STATIC_DIR}/static" -mindepth 1 -delete
cp -a /app/www/. "${STATIC_DIR}/static/"

echo "code initialized: code=$(find "${CODE_DIR}" -type f | wc -l) files, static=$(find "${STATIC_DIR}" -type f | wc -l) files"
