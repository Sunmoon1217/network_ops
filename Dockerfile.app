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
#   （tmpfs 是每容器私有的内存文件系统，无法共享）。而卷挂在 /app/www、
#   /app/frontend/dist 上会遮住镜像里的同名目录，且 Docker 只在卷首次创建时用
#   镜像内容播种一次——重建镜像后旧卷不会更新。因此构建期先把成品另存到
#   /opt/static（staging），运行时由 docker/entrypoint.sh 同步进两个挂载点，
#   保证「重建镜像 → 卷里的产物跟着更新」。
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

# 校验成品 + 拷到 staging。
# staging 必须是另一个路径：运行时命名卷会挂到 /app/www 与 /app/frontend/dist 上，
# 把镜像里这两个目录遮住（见文件头说明）。
# /app/data 是配置仓库（GitPython 操作的 git 仓库）的挂载点，先建出来。
RUN set -eux; \
    if [ ! -f /app/frontend/dist/index.html ]; then \
        echo "错误：frontend/dist 缺少 index.html。请先在宿主机执行 cd frontend && pnpm build" >&2; \
        exit 1; \
    fi; \
    if [ -z "$(ls -A /app/www)" ]; then \
        echo "错误：www 是空目录。请先在宿主机执行 uv run python manage.py collectstatic --noinput" >&2; \
        exit 1; \
    fi; \
    mkdir -p /app/data /opt/static; \
    cp -a /app/www /opt/static/www; \
    cp -a /app/frontend/dist /opt/static/dist; \
    echo "static files: www=$(find /opt/static/www -type f | wc -l) dist=$(find /opt/static/dist -type f | wc -l)"

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
