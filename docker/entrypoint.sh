#!/bin/sh
#
# 应用容器入口：把镜像里的静态产物复制进命名卷，然后执行 CMD。
#
# 为什么要复制：
#   nginx 是独立容器，**读不到本容器镜像里的文件**，只能通过命名卷拿静态产物。
#   卷挂在**空目录**上（/var/lib/netops-static/...，镜像里是空的），所以卷里的内容
#   唯一来源就是这里的复制 —— 不存在「Docker 只在卷首次创建时用镜像内容播种一次」
#   那种歧义，也不会出现「重建镜像后卷里还是旧产物」。
#
#   镜像里的 /app/www 与 /app/frontend/dist 保持原样不动（Django 的 STATIC_ROOT 与
#   FRONTEND 就指这两个路径，DEBUG 下由 Django 自己托管），复制的是**另一份**到卷里
#   给 nginx 用，两边互不干扰。
#
# 复制是**权威**的：先清空挂载点内容再铺（find -mindepth 1 -delete，保留挂载点目录
# 本身，也不漏点开头的文件）。只 cp 不删的话，上一版带 hash 的旧资源会一直堆在卷里。
#
# 注意这里**不跑 migrate**：迁移是有副作用的操作，多副本同时启动会互相竞争。
# 首次部署与版本升级请显式执行：
#   docker compose run --rm app python manage.py migrate

set -e

STATIC_ROOT_DIR=/var/lib/netops-static

mkdir -p /app/data "$STATIC_ROOT_DIR/www" "$STATIC_ROOT_DIR/dist"

sync_dir() {
    src="$1"
    dst="$2"
    [ -d "$src" ] || return 0
    find "$dst" -mindepth 1 -delete
    # 结尾的 /. 表示同步目录内容而不是目录本身
    cp -a "$src"/. "$dst"/
}

sync_dir /app/www "$STATIC_ROOT_DIR/www"
sync_dir /app/frontend/dist "$STATIC_ROOT_DIR/dist"

exec "$@"
