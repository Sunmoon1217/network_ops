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
# 基础镜像可以换（私有 registry、别的 python 版本等），默认 network-ops-base:py312：
#   BASE_IMAGE=registry.example.com/netops-base:py312 docker compose build app worker
#   docker build --build-arg BASE_IMAGE=network-ops-base:py312 -f Dockerfile.app -t network-ops:latest .
# 注意 FROM 里只能用 ARG：ENV 在 FROM 之前不生效，所以这里不是 ENV。
#
# 数据库迁移在**容器启动时自动跑**（有未应用的迁移才跑，见 docker/entrypoint.sh 第 3 步与
# manage.py migrate_if_needed；多副本同时启动由数据库自带的命名锁串行化）。
# 想让迁移改为人工放行，设 MIGRATE_ON_START=0 后显式执行：
#   docker compose run --rm app python manage.py migrate
#
# 初始管理员同样在启动时**零配置创建**（第 4 步 manage.py ensure_superuser）：只在库里一个
# 超级用户都没有时创建 admin，随机初始密码打印在启动日志里；已经有就是空操作。
#
# CMD 只放**可调参数**（--workers / 超时 / 日志等），固定部分（--worker-class / --bind）
# 在 entrypoint 里，见文件末尾。

ARG BASE_IMAGE=network-ops-base:py312

FROM ${BASE_IMAGE}

WORKDIR /app

# 只复制运行期需要的目录；tests/ 依赖 dev 组（pytest），不进运行镜像
COPY manage.py pyproject.toml uv.lock ./
COPY netops/ ./netops/
COPY apps/ ./apps/

# 宿主机构建好的静态成品（.dockerignore 已放开这两个目录）
COPY frontend/dist ./frontend/dist
COPY www ./www

# 校验成品，并建出运行时要用的空目录：
#   /app/data/config_repo     `config_repo_data` 命名卷的挂载点。**镜像里保持空**：卷只在首次创建时
#                             用这里的内容播种一次，空目录 → 卷是空的 → `init_repo()` 在里面 git init。
#   /app/data/configs         Excel 导入用的配置源目录挂载点（app 以 :ro 把宿主机 ./data/configs 挂上来）
#   /var/lib/netops-static    静态产物命名卷的挂载点，同样是**故意留空**；卷内布局按 URL
#                             前缀设计（index.html + assets/ + static/），内容只由
#                             entrypoint 从 /app/www、/app/frontend/dist 复制进来
# 挂载点建在镜像里（而不是留给 dockerd 在容器启动时创建），是为了让"路径存在"这件事可预期：
# 缺了它 Docker 会以 root 建出来，行为看着一样但没人知道是从哪来的。
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

# git 提交必须有「提交者身份」。没配 user.email 时 git 会退化成 `用户@主机名`，而容器主机名是个**没有域名
# 部分**的容器 id，于是它直接拒绝、让你先去配（实测 root 与任意 uid 一样，都会失败）：
#     fatal: unable to auto-detect email address (got 'root@0649f8566bbe.(none)')
# 配上之后 `init_repo()` 的首次提交、`save_config()` 的每次导入才走得通。这里给一个中性身份；要换成
# 团队自己的，用容器环境变量覆盖即可（它们优先于配置）：
#   GIT_AUTHOR_NAME / GIT_AUTHOR_EMAIL / GIT_COMMITTER_NAME / GIT_COMMITTER_EMAIL
RUN git config --system user.name "netops" && git config --system user.email "netops@localhost"

# 这里**不放** `git config --system safe.directory`：那一条是「容器进程与仓库属主不是同一个用户」才需要的
# （`fatal: detected dubious ownership in repository`），而它现在不会发生——配置仓库是命名卷、容器以 root
# 跑，卷里的文件就是 root 建的，属主与进程用户一致。⚠️ 哪天把 config_repo 改回 bind、或给容器加 `user:`，
# 这条要加回来，而且必须加在**镜像层**：worker 走 compose 给的 celery 命令、不执行 entrypoint，
# 写在 entrypoint 里 worker 拿不到（此前漏过一次，worker 一直报 dubious ownership）。

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

# 启动命令**整条在 docker/entrypoint.sh 里拼装**，这里刻意**不定义 CMD**
# （基础镜像 Dockerfile.base 也不定义，否则会被继承）：
#
#   entrypoint 里：gunicorn netops.asgi:application --worker-class uvicorn_worker.UvicornWorker
#                  --bind 0.0.0.0:8000            ← 硬要求，写死
#                  --workers ${GUNICORN_WORKERS:-1} ...  ← 可调参数，取环境变量
#
# 为什么不放 CMD：
#   * 同一个镜像还要当 celery worker 用，而 worker 在 docker-compose.yml 里用
#     `entrypoint: ["celery"]` + `command:` 换掉了整条命令，**走不到** gunicorn 这条路径
#     ——默认值写在 CMD 里只对 app 有意义，反而多一处要同步的地方；
#   * CMD 是 exec 形式，里面的 ${GUNICORN_*} 不会被展开（要展开得退回 shell 形式，
#     而那又会绕过 entrypoint 的「$1 以 - 开头」判断）。
#
# 覆盖规则（entrypoint 里按官方镜像的通行写法判断 $1 是否以 - 开头；两种都成立）：
#
#   docker compose run --rm app --workers 4                  # 追加参数 → 覆盖同名项
#   docker compose run --rm app python manage.py migrate     # 整条命令 → 原样执行
#   docker compose run --rm app gunicorn netops.asgi:application -k uvicorn_worker.UvicornWorker
#
# 可调参数一律走环境变量：`.env` → compose 的 x-gunicorn-environment（app 服务）
# → entrypoint 的 shell 插值。清单、默认值与含义见 .env.example 的「gunicorn」段。
# 环境变量在这里是**替换**语义（位置固定），不是 gunicorn 自带的 GUNICORN_CMD_ARGS 那种
# 「追加到最后」——后者对 --bind 只会多出一个监听，覆盖不掉，所以没有用它。
#
# 为什么 --bind / --worker-class 不做成变量：--bind 跟 nginx 的 upstream 绑在一起（改地址必须
# 同步 nginx 配置），而 gunicorn 自己的默认值是 127.0.0.1:8000——「只覆盖部分参数」时漏掉它
# nginx 就连不上（502）；并且 --bind 是 append 语义（`gunicorn/config.py` 的
# `action = "append"`），追加一个只会**多一个监听**。--worker-class 决定 ASGI 能否工作，同理。
