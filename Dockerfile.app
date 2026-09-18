# syntax=docker/dockerfile:1
#
# 项目镜像 —— 在不变的基础环境镜像之上，叠加项目源码与**静态成品**。
#
# 静态成品不在镜像内构建，直接用宿主机已经构建好的：
#   frontend/dist  ←  cd frontend && pnpm build
#   www            ←  uv run python manage.py collectstatic --noinput
# 所以构建前必须先跑这两步；镜像里有断言，产物缺失或为空会直接构建失败。
# （好处：镜像里没有任何 node/npm/pnpm，构建也只需秒级）
#
# 成品为什么要进镜像、再经命名卷给 nginx：
#   nginx 是独立容器，**读不到本镜像里的文件**，跨容器共享只有卷这一条路
#   （tmpfs 是每容器私有的内存文件系统，无法共享）。所以 /app/www 与
#   /app/frontend/dist 保持原样（Django 的 STATIC_ROOT / FRONTEND 就指这里），
#   容器启动时由 docker/entrypoint.sh 复制**另一份**到命名卷给 nginx 用。
#   卷挂在空目录上，内容唯一来源就是这次复制，不存在「Docker 只播种一次、
#   重建镜像后卷里还是旧产物」的问题。
#
# 构建：
#   docker build --network=host -f Dockerfile.base -t network-ops-base:py312 .  # pyproject/uv.lock 变了才重建
#   docker build -f Dockerfile.app -t network-ops:latest .                     # 每次发版都跑
#
# 首次部署与升级后要显式跑迁移（不在 entrypoint 里自动跑）：
#   docker compose run --rm app python manage.py migrate

FROM network-ops-base:py312

WORKDIR /app

# 只复制运行期需要的目录；tests/ 依赖 dev 组（pytest），不进运行镜像
COPY manage.py pyproject.toml uv.lock ./
COPY netops/ ./netops/
COPY apps/ ./apps/

# 宿主机构建好的静态成品（.dockerignore 已放开这两个目录）
COPY frontend/dist ./frontend/dist
COPY www ./www

# 校验成品，并建出运行时要用的空目录：
#   /app/data                       配置仓库（GitPython 操作的 git 仓库）的挂载点
#   /var/lib/netops-static/{www,dist}  命名卷挂载点，镜像里**故意留空**，
#                                      内容只由 entrypoint 从 /app/{www,frontend/dist} 复制进来
RUN set -eux; \
    if [ ! -f /app/frontend/dist/index.html ]; then \
        echo "错误：frontend/dist 缺少 index.html。请先在宿主机执行 cd frontend && pnpm build" >&2; \
        exit 1; \
    fi; \
    if [ -z "$(ls -A /app/www)" ]; then \
        echo "错误：www 是空目录。请先在宿主机执行 uv run python manage.py collectstatic --noinput" >&2; \
        exit 1; \
    fi; \
    mkdir -p /app/data /var/lib/netops-static/www /var/lib/netops-static/dist; \
    echo "static files: www=$(find /app/www -type f | wc -l) dist=$(find /app/frontend/dist -type f | wc -l)"

COPY docker/entrypoint.sh /usr/local/bin/netops-entrypoint
RUN chmod +x /usr/local/bin/netops-entrypoint

# 构建期校验：把 netops.settings 真正加载一遍，并导入 ASGI 入口。
# 只 import 模块发现不了「INSTALLED_APPS 里某个包没装」，django.setup() 可以；
# 这一步不连数据库，因此 build 阶段无需 DB。
RUN set -eux; \
    python -c "import os, django; \
os.environ.setdefault('DJANGO_SETTINGS_MODULE','netops.settings'); \
django.setup(); \
from netops.asgi import application; \
print('django app ok:', application.__class__.__name__)"

EXPOSE 8000

ENTRYPOINT ["/usr/local/bin/netops-entrypoint"]

# ASGI 启动：gunicorn + uvicorn worker（uvicorn.workers 已被移除，用独立包）。
# 需要多进程时在运行时覆盖，如 `docker compose run --rm app gunicorn
# netops.asgi:application -k uvicorn_worker.UvicornWorker -b 0.0.0.0:8000 -w 4`。
CMD ["gunicorn", "netops.asgi:application", \
     "--worker-class", "uvicorn_worker.UvicornWorker", \
     "--bind", "0.0.0.0:8000", \
     "--access-logfile", "-", \
     "--error-logfile", "-"]
