# syntax=docker/dockerfile:1
#
# 项目镜像 —— 在不变的基础环境镜像之上，只叠加项目源码。
#
# 依赖装在基础镜像的 /opt/venv 里，PATH / VIRTUAL_ENV / WORKDIR 均已由
# Dockerfile.base 设置，所以这里只有 COPY —— 没有任何依赖安装步骤：
#
#   docker build --network=host -f Dockerfile.base -t network-ops-base:py312 .  # 环境变了才重建
#   docker build -f Dockerfile.app -t network-ops:latest .                      # 每次都跑，秒级完成
#
# 运行（数据库在 compose 里，容器内用服务名 db 访问）：
#   docker run --rm -p 8000:8000 --network network_ops_internal \
#     -e POSTGRES_HOST=db -e POSTGRES_PASSWORD=... network-ops:latest

FROM network-ops-base:py312

WORKDIR /app

# 只复制运行期需要的目录；tests/ 依赖 dev 组（pytest），不进运行镜像
COPY manage.py pyproject.toml uv.lock ./
COPY netops/ ./netops/
COPY apps/ ./apps/

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

# ASGI 启动：gunicorn + uvicorn worker（uvicorn.workers 已被移除，用独立包）。
# 需要多进程时在运行时覆盖，如 `docker run ... network-ops:latest gunicorn
# netops.asgi:application -k uvicorn_worker.UvicornWorker -b 0.0.0.0:8000 -w 4`。
CMD ["gunicorn", "netops.asgi:application", \
     "--worker-class", "uvicorn_worker.UvicornWorker", \
     "--bind", "0.0.0.0:8000", \
     "--access-logfile", "-", \
     "--error-logfile", "-"]
