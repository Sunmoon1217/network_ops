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

EXPOSE 8000

CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
