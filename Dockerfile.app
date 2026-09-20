# syntax=docker/dockerfile:1
#
# 项目镜像：${BASE_IMAGE}（环境镜像）+ 源码 + 宿主机构建好的静态成品。
# 构建前置与命令、COPY 范围、挂载点、git 身份与 safe.directory：docker/README.md §2、§4

ARG BASE_IMAGE=network-ops-base:py312

FROM ${BASE_IMAGE}

WORKDIR /app

COPY manage.py pyproject.toml uv.lock ./
COPY netops/ ./netops/
COPY apps/ ./apps/
COPY frontend/dist ./frontend/dist
COPY www ./www

RUN set -eux; \
    if [ ! -f /app/frontend/dist/index.html ]; then \
        echo "错误：frontend/dist 缺少 index.html。请先在宿主机执行 cd frontend && pnpm build" >&2; \
        exit 1; \
    fi; \
    if [ -z "$(ls -A /app/www)" ]; then \
        echo "错误：www 是空目录。请先在宿主机执行 uv run python manage.py collectstatic --noinput" >&2; \
        exit 1; \
    fi; \
    mkdir -p /app/data/config_repo /app/data/configs /var/lib/netops-static; \
    echo "static files: www=$(find /app/www -type f | wc -l) dist=$(find /app/frontend/dist -type f | wc -l)"

RUN git config --system user.name "netops" && git config --system user.email "netops@localhost"

COPY docker/entrypoint.sh /usr/local/bin/netops-entrypoint
RUN chmod +x /usr/local/bin/netops-entrypoint

RUN set -eux; \
    python -c "import os, django; \
os.environ.setdefault('DJANGO_SETTINGS_MODULE','netops.settings'); \
django.setup(); \
from netops.asgi import application; \
print('django app ok:', application.__class__.__name__)"

EXPOSE 8000

ENTRYPOINT ["/usr/local/bin/netops-entrypoint"]
