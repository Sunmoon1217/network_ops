#!/bin/sh
#
# 应用容器入口：把镜像里的静态产物同步进命名卷，然后执行 CMD。
#
# 为什么需要这一步：
#   nginx 是独立容器，**读不到本容器镜像里的文件**，只能通过命名卷拿静态产物
#   （compose 里 www_data / dist_data）。但把卷挂在 /app/www 与 /app/frontend/dist
#   上会**遮住镜像里同名目录**的内容——Docker 仅在卷首次创建时用镜像内容播种一次，
#   之后重建镜像（前端重新构建、静态文件更新）旧卷不会更新，表现为「镜像里产物是
#   新的，页面还是旧的」。
#
#   所以构建期把产物另存一份到 /opt/static（staging），每次启动从这里覆盖同步进
#   两个挂载点，保证卷内容始终跟随镜像。
#
# 同步是**权威**的：先清空挂载点内容再铺（用 find -mindepth 1 -delete，
# 保留挂载点目录本身，也不漏掉点开头的文件）。只 cp 不删的话，上一版带 hash 的
# 旧资源会一直堆在卷里。
#
# 注意这里**不跑 migrate**：迁移是有副作用的操作，多副本同时启动会互相竞争。
# 首次部署与版本升级请显式执行：
#   docker compose run --rm app python manage.py migrate

set -e

mkdir -p /app/data /app/www /app/frontend/dist

sync_dir() {
    src="$1"
    dst="$2"
    [ -d "$src" ] || return 0
    find "$dst" -mindepth 1 -delete
    # 结尾的 /. 表示同步目录内容而不是目录本身
    cp -a "$src"/. "$dst"/
}

sync_dir /opt/static/www /app/www
sync_dir /opt/static/dist /app/frontend/dist

exec "$@"
