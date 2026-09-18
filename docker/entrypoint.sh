#!/bin/sh
#
# 应用容器入口：把镜像里的静态产物复制进命名卷，然后执行 CMD。
#
# 卷的目录布局**按 URL 前缀设计**，这样 nginx 一个 root 就能覆盖全部静态请求：
#
#   <卷>/index.html   ← Vite 产物（SPA 入口，/ 走 try_files 兜底）
#   <卷>/assets/*     ← Vite 产物（/assets/*）
#   <卷>/static/*     ← collectstatic 产物（/static/*，STATIC_URL 就是 /static/）
#
# 为什么要复制：nginx 是独立容器，**读不到本容器镜像里的文件**，只能通过命名卷
# 拿静态产物。卷挂在镜像里**故意留空的**目录上，所以卷里内容唯一来源就是这里的
# 复制——不存在「Docker 只在卷首次创建时用镜像内容播种一次、之后重建镜像也不更新」
# 那种陈旧问题。
#
#   镜像里 /app/www 与 /app/frontend/dist 保持原样不动（Django 的 STATIC_ROOT 与
#   FRONTEND 就指这两个路径，DEBUG 下由 Django 自己托管），复制的是**另一份**。
#
# 复制是**权威**的（先清空再铺），否则上一版带 hash 的遗留资源会一直堆在卷里。
# 注意卷根清空时要**排除 static/**：它由第 2 步单独同步，不能被第 1 步顺带删掉。
#
# 注意这里**不跑 migrate**：迁移是有副作用的操作，多副本同时启动会互相竞争。
# 首次部署与版本升级请显式执行：
#   docker compose run --rm app python manage.py migrate

set -e

VOL=/var/lib/netops-static

mkdir -p /app/data "$VOL" "$VOL/static"

# 1) SPA（Vite 产物）→ 卷根；保留 static/ 给下一步
find "$VOL" -mindepth 1 -maxdepth 1 ! -name static -exec rm -rf {} +
cp -a /app/frontend/dist/. "$VOL"/

# 2) Django collectstatic 产物 → 卷内的 static/ 子目录
find "$VOL/static" -mindepth 1 -delete
cp -a /app/www/. "$VOL/static"/

exec "$@"
