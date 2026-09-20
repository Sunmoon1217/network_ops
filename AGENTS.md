# AGENTS.md

## 项目概述

网络运维管理平台：Django REST 后端 + Vue 3 前端。

后端提供数据模型与 REST API，负责设备配置的解析与入库。前端构建产物默认可由 Django 直接托管（便于开发调试）；生产/集成环境使用 `docker compose` 起 db / redis / app / worker / nginx，由 `nginx/` 作为统一入口（静态资源直出，`/api` 反向代理到 app 容器）。

## 项目结构

```
network_ops/
├── manage.py            # Django 入口
├── main.py
├── netops/              # 项目配置（单一 settings，不按环境分发）
│   ├── settings.py      # 全部配置（DEBUG 硬编码为 True）
│   ├── urls.py          # /admin/、/api/、前端 SPA 兜底
│   ├── views.py         # 托管 frontend/dist（index.html、assets、favicon）
│   ├── asgi.py
│   └── wsgi.py
├── apps/
│   ├── core/            # 用户与认证
│   │   ├── models.py            # User、Token
│   │   └── api/{auth.py, urls.py}
│   ├── assets/          # 全部数据模型（单文件，41 个模型）
│   │   ├── models.py
│   │   ├── serializers/{base.py, views.py}   # 序列化器（API 视图与解析入库共用）
│   │   ├── management/commands/import_server_owners.py  # xlsx 导入服务器负责人
│   │   └── api/{serializers.py, urls.py, views.py}
│   └── ops/             # 操作层：解析、存储、路径追踪
│       ├── api/{configs.py, parsers.py, trace.py, urls.py}
│       ├── parsers/{factory.py, template_keys.py, contract.py} + tmpls/{configs,running}/
│       ├── savers/{base,registry,interface,lb,firewall,routing}.py
│       ├── config_owner.py      # 配置属主解析（堆叠组备机归属主设备）
│       ├── config_repo.py       # Git 配置仓库管理
│       ├── path_tracer.py       # 路径追踪算法
│       ├── signals.py           # DeviceConfig 保存后触发解析与入库（薄壳，实现见 pipeline.py）
│       ├── pipeline.py          # 配置处理流水线：读 Git → 解析 → 分发 Saver
│       ├── workflow.py          # 任务工作流入口：start_task / dispatch_stage / cancel_task / submit_config_job
│       ├── management/commands/reparse.py  # 重跑已入库配置的解析与入库
│       ├── management/commands/purge_configs.py  # 清理配置解析产物（默认 dry-run）
│       ├── models.py            # InternetAnalysis（分析结果缓存）
│       └── ansible/             # ⚠️ 仅剩 __pycache__，源文件已移除
├── data/
│   ├── config_repo/     # Git 配置仓库（含 .git）
│   └── configs/
├── tests/               # 测试（按应用分目录，pytest testpaths 指向此处）
│   ├── assets/          # device_group / serializer_migration / service_unique
│   ├── deploy/          # 反向代理与 Django 的接口契约（nginx Host 透传 / CSRF 可信来源）
│   └── ops/             # parsers / parser_contract / pipeline / analysis / reparse
├── docs/compose/
├── frontend/            # Vue 3 + TypeScript + Vite
│   ├── dist/            # 构建产物（不入库，由 nginx 直接托管）
│   └── src/{api,assets,composables,layout,router,stores,ui,utils,views}
├── nginx/               # 反向代理（静态直出 + API 代理）
│   ├── conf.d/          # netops.conf(80)、netops-ssl.conf.disabled(443)
│   ├── docker-entrypoint.d/  # 05-netops-resolver.sh：启动时把 runtime 的 DNS 写成 resolver.conf
│   ├── ssl/             # TLS 证书（不入库）
│   └── gen-self-signed-cert.sh
├── www/                 # collectstatic 产物（不入库，镜像构建时 COPY 进 app）
├── env/                 # 给容器的配置：按服务分的 env 文件（app/db/gunicorn/celery.env）+ secrets/（密钥，不入库）
├── tmp/
├── docker/entrypoint.sh # 应用容器入口：静态成品复制进命名卷 → 按需迁移 → 零配置建管理员 → 拼出整条 gunicorn 命令启动
├── Dockerfile.base      # 环境镜像（只装依赖，不含源码）
├── Dockerfile.app       # 项目镜像（源码 + 宿主机构建好的静态成品）
├── .dockerignore
├── docker-compose.yml   # db(TimescaleDB) / redis / app / worker / nginx
├── .env.example         # **compose 自己**的变量模板（宿主端口 / 镜像 / secrets 路径）：cp 成 .env
├── pyproject.toml       # Python 依赖、pytest、ruff 配置
└── uv.lock
```

## 环境搭建

需要 Python >= 3.12，使用 `uv` 管理包。

```bash
# 创建虚拟环境
uv venv --python 3.12

# 安装所有依赖（主依赖 + dev + test）
uv sync --all-groups

# 前端
cd frontend && pnpm install
```

数据库为 **PostgreSQL**，通过进程环境变量配置（见 `netops/settings.py`）：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `POSTGRES_DB` | `netops` | 数据库名（容器部署时在 `env/app.env` 与 `env/db.env` 里） |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` | — | **走 docker secrets**：`env/secrets/postgres_user`、`env/secrets/postgres_password` → 容器内 `/run/secrets/*`；`settings.py` 的 `_env_or_file()` 读 `POSTGRES_USER_FILE` / `POSTGRES_PASSWORD_FILE`（没有 `*_FILE` 时回退同名环境变量，供宿主机直跑）。见 `env/secrets/README.md` |
| `POSTGRES_HOST` | `localhost` | 数据库主机（容器里由 `env/app.env` 给 `db`） |
| `POSTGRES_PORT` | `5432` | 数据库端口（容器内固定 5432；根 `.env` 里那个是**宿主映射**端口） |
| `DJANGO_ALLOWED_HOSTS` | `*` | 逗号分隔，映射到 `ALLOWED_HOSTS`；无域名阶段默认放开 |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | 空 | 逗号分隔，映射到 `CSRF_TRUSTED_ORIGINS`（Django 4+ 的 Origin 校验）；**正常拓扑留空即可** |

> 配置按「谁读」分三处（完整表格见 `env/README.md`）：**`.env`（根）** 只给 compose 自己插值（`cp .env.example .env`；已被 `.gitignore` 忽略）；**`env/*.env`** 按服务注入容器（`app.env` 给 app+worker、`db.env` 给 db、`gunicorn.env` 给 app、`celery.env` 给 worker）；**`env/secrets/*`** 只读挂载给凭据。Django 自己不读任何 `.env`——宿主机直跑时要 `set -a; . ./.env; set +a`，再 `export POSTGRES_HOST=localhost REDIS_HOST=localhost POSTGRES_USER_FILE=env/secrets/postgres_user POSTGRES_PASSWORD_FILE=env/secrets/postgres_password`。

## 常用命令

**后端（项目根目录）：**

```bash
uv run python manage.py migrate
uv run python manage.py createsuperuser
uv run python manage.py runserver
```

**前端（`frontend/` 目录）：**

```bash
pnpm dev          # Vite 开发服务器
pnpm build        # vue-tsc 类型检查 + vite build（输出 frontend/dist）
pnpm type-check   # 仅 TypeScript 检查
```

**测试与代码检查（项目根目录）：**

```bash
uv run pytest
uv run ruff check
uv run ruff format
```

## 关键约定

- **单一配置**：`netops/settings.py` 包含全部配置，无 `settings_d/` 分发，无 `DJANGO_ENV`。
- **`.env` 的解析坑（compose 实测，密码最容易中招）**：`$` 会做变量插值——`POSTGRES_PASSWORD=pa$word` 实际只得到 `pa`；要字面量 `$` 必须写 `$$`（`pa$$word` → `pa$word`）或用**单引号** `'a#b $c'`（**双引号不保护 `$`**：`"a#b $c"` → `a#b `）。`#` 前面有空格就是行内注释（`p #ss` → `p`），紧贴则保留（`p#ss` → `p#ss`）；行尾空格会被去掉。**含 `$` / `#` 的值一律用单引号。**
- **模型集中**：`assets` 的所有模型都在单文件 `apps/assets/models.py`，没有 models 子目录。
- **应用注册**：`core.apps.CoreConfig`、`ops.apps.OperatorConfig`、`assets.apps.AssetsConfig`。
- **Celery 分阶段工作流**：采集→解析→存储三个阶段由 Celery 任务串联（`ops/tasks.py` 的 `run_collection_stage` / `run_parsing_stage` / `run_storage_stage`），`Stage` 状态回写触发下一阶段（`ops/signals.py`）。**入口是 `/api/tasks/`**：`ops/workflow.py` 的 `start_task` 建 Task 并投递第一个（采集）阶段——此前 Task/Stage 只有模型与任务、没有任何创建者，整条链在产品里不可达；阶段失败或任务被取消时，信号负责收尾/停止推进。批量导入配置（`_import_configs`）走另一条链：`submit_config_job` = `run_config_parsing → run_config_storage`（用 `.si()` 保证两个任务拿到同一个 `config_id`）。broker/backend 都是 Redis（`REDIS_HOST`/`REDIS_PORT`）。**必须有 worker 消费队列**，否则 `.delay()` 只会把消息堆在 Redis 里永远不执行——`docker-compose.yml` 里的 `worker` 服务就是干这个的。
- **DeviceConfig 的解析入库默认仍是同步的**：走 `ops.pipeline.run_config_pipeline`，在 `post_save` 的调用栈里跑完（见下文「配置处理流程」）。**例外是批量导入**：`_import_configs` 在 save 之前给实例挂 `_defer_pipeline`，信号据此跳过同步处理，改由 `ops.workflow.submit_config_job` 投递 celery 链（几十行配置不该在一个请求里串行跑几十次解析+入库）。两套链路并存，别混。
- **前端托管**：`netops/views.py` 从 `frontend/dist/` 读取 `index.html` 与静态资源；`netops/urls.py` 用正则把非 `/api`、`/admin`、`/static`、`/assets`、`/media` 的请求交给 Vue 路由。
- **反向代理与容器化**：`nginx/` 作为统一入口（80/443）。`/api/*`、`/admin/*`、`/media/*` 代理到 compose 里的 **app 容器**（不再指向宿主机 Django）；`/assets/*`、`/static/*` 由 nginx 直出。两类静态资源的源头是**宿主机**（`pnpm build` + `collectstatic`），`Dockerfile.app` 把它们 COPY 进镜像的 `/app/www` 与 `/app/frontend/dist`（同时就是 Django 的 `STATIC_ROOT` / `FRONTEND`），容器启动时 `docker/entrypoint.sh` 复制**另一份**到**一个**命名卷 `static_data`，nginx 只读挂载。详见 `nginx/README.md`。
- **静态卷的布局按 URL 前缀设计**：`<卷>/index.html` + `<卷>/assets/*`（Vite）+ `<卷>/static/*`（collectstatic，因为 `STATIC_URL` 就是 `/static/`）。因此 nginx **一个 root**（`/usr/share/nginx/html`）就覆盖 `/`、`/assets/*`、`/static/*`，`location /static/` 不需要再写 root 覆盖。宿主机上 `www/` 与 `frontend/dist/` 仍是各自独立的目录、各由自己的工具清空（`collectstatic --clear`、`pnpm build` 的 `emptyOutDir`），只有容器里这一份副本被合到一起，所以两个清空动作互不干扰。
- **为什么必须绕一层命名卷**：nginx 是独立容器，读不到 app 镜像里的文件；跨容器共享只有卷这一条路（tmpfs 是每容器私有的内存文件系统，`--volumes-from` 也拿不到，实测过）。命名卷挂在镜像里**故意留空的** `/var/lib/netops-static` 上——挂到有内容的目录会遮住镜像内容，而 Docker 只在卷首次创建时播种一次，于是「重建镜像后页面还是旧的」。入口脚本每次都**权威**重铺，注意清卷根时要 `! -name static` 排除掉 `static/`（它由下一步单独同步）。
- **配置仓库与运行期数据是宿主机 `./data` 的 bind 挂载（不是命名卷）**：`docker-compose.yml` 里 app 与 worker 都挂 `./data:/app/data`（2026-09 从命名卷 `app_data` 改过来，当时那边是**另一份**、两边互不影响）。好处：宿主机的 git / 编辑器直接看得到，`purge_configs --purge-repo` 与容器动的是同一份。代价是**属主不一致**，两个方向都踩过：① 容器以 root 跑，它新建的文件在宿主机上属于容器 root → 宿主侧要改得 sudo；② 宿主已有的文件属主是宿主用户，容器里的 git 直接拒绝操作（`fatal: detected dubious ownership in repository at '/app/data/config_repo'`），而 GitPython 走的就是 git CLI，于是配置仓库会静默全挂——所以 `docker/entrypoint.sh` 第 0 步会 `git config --system --add safe.directory '*'`（放 `*` 而不是写死路径：仓库位置可由 `CONFIG_REPO_PATH` 覆盖，写死等于复制一份 `ops/config_repo.py` 的默认值）。旧命名卷 `network_ops_app_data` 不会被自动删除，确认空之后可 `docker volume rm`。
- **不用 `volumes_from`**：它会把源容器的所有卷都带过来（nginx 会白拿配置仓库那个挂载，即宿主机 `./data` 的 bind），且卷在目标容器里的路径与源容器相同（nginx 只能看到 `/app/www`，配置被绑死）。显式写 `static_data:/usr/share/nginx/html:ro` 才能只读、挑卷、并放在 nginx 自己的路径上。
- **nginx 的后端地址用 `resolver` + 变量**（`set $netops_upstream "app:8000"`）而不是 `upstream` 块：`upstream` 只在启动时解析一次，app 容器重建换 IP 后会一直 502；变量形式按 `valid` 周期重解析，也让 `nginx -t` 脱离 compose 网络能通过。
- **`resolver` 的地址不能写死（地址由 runtime 决定）**：**镜像与 runtime 无关**——官方 nginx 镜像同一个、`resolver` 行为也一样；不一样的只是 runtime 给容器写的 `/etc/resolv.conf`。Docker 用户自定义网络是内置 DNS `127.0.0.11`，而 **Podman 把 DNS 放在网络网关**（aardvark-dns，例如 `10.89.3.1`），Podman 根本没有 `127.0.0.11`。原先写死的 `127.0.0.11` 是按「只部署 Docker」定的（`876fbf9` 的注释原文即「127.0.0.11 是 Docker 的内置 DNS」），换 runtime 就是 `recv() failed (111: Connection refused) while resolving, resolver: 127.0.0.11:53`——网络完全正常、只是解析器地址不对，然后 `app` 解析失败、前端 502。**注意这不是"能省就省"的问题**：删掉 `resolver` 就得回到静态 `upstream` 块，那会失去按 `valid` 重解析（app 重建换 IP 后一直 502）并且解析不到就直接 `emerg`；变量形式必须配 `resolver`，而 `resolver` 必须显式给地址——所以要把地址**推导**出来而不是去掉。做法：`nginx/docker-entrypoint.d/05-netops-resolver.sh` 在容器启动时从 `/etc/resolv.conf` 推导并写出 `/etc/nginx/netops/resolver.conf`，conf.d 里的 server 块（80/443）`include` 它；compose 只把这**一个文件**挂到 `/docker-entrypoint.d/`（**挂目录会遮住镜像自带的 entrypoint 脚本**）。脚本取不到 nameserver 就报错退出（失败即响），IPv6 会加方括号。**不要改用官方 envsubst 模板机制**：它要求额外设 `NGINX_ENTRYPOINT_LOCAL_RESOLVERS=1`，而不设时占位符会原样留在配置里、`nginx -t` **竟然仍然通过**（实测），故障推迟到转发时才暴露。
- **改动基础镜像的时机**：`pyproject.toml` / `uv.lock` 变了（例如新增 celery）必须重建 `Dockerfile.base`，否则项目镜像会在运行期才报 `ModuleNotFoundError`。`Dockerfile.base` 的冒烟自检清单要与 `dependencies` 对齐，就是为了让这种问题在基础镜像构建时就暴露。**换镜像源要用 uv 自己的变量**：`uv` 不读 pip 的配置（`PIP_INDEX_URL` / `pip.conf` 全部忽略——实测把它指向连不上的地址，`uv sync` 照样成功地去 PyPI 拉包），要换源得用 `UV_DEFAULT_INDEX` / `--default-index`。另外 `uv.lock` 会**固化**解析时的 registry 与 wheel URL（本项目锁文件里就是腾讯镜像的路径），`--frozen` 安装按 lock 走，所以换源要重新 `uv lock --default-index <新源>`。**项目镜像的基础镜像本身可换**：`Dockerfile.app` 用 `ARG BASE_IMAGE=network-ops-base:py312` + `FROM ${BASE_IMAGE}`（`FROM` 里只能用 `ARG`——`ENV` 在 `FROM` 之前不生效），compose 用 `x-app-build` 锚点统一给 app 与 worker 传这个 build arg（`${BASE_IMAGE:-network-ops-base:py312}` —— 一处定义，两个服务不会漂移成两个基础镜像），所以换私有 registry / 换 python 版本只改环境变量：`BASE_IMAGE=registry.example.com/netops-base:py312 docker compose build app worker`；直接 `docker build` 时写成 `BASE_IMAGE=... docker build --build-arg BASE_IMAGE ...`（**只写名字**即取同名环境变量的值）。
- **启动命令整条在 entrypoint 里拼：硬要求写死，可调参数取环境变量**：`docker/entrypoint.sh` 拼出 `gunicorn netops.asgi:application --worker-class uvicorn_worker.UvicornWorker --bind 0.0.0.0:8000 --workers "${GUNICORN_WORKERS:-1}" … --access-logfile - --error-logfile -`。**镜像里刻意没有 CMD**（`Dockerfile.base` 也不定义，否则会被继承）：同一个镜像还要当 celery worker 用，而 worker 在 compose 里用 `entrypoint: ["celery"]` + `command:` 换掉整条命令、走不到 gunicorn 这条路径，默认值放 CMD 只对 app 有意义；何况 CMD 是 exec 形式、`${GUNICORN_*}` 不会被展开（退回 shell 形式又会绕过 `$1` 判断）。entrypoint 按官方镜像的通行写法判断 `$1` 是否以 `-` 开头：是（或没有参数）就用拼好的默认命令、再把 `$@` 追加在尾部，否则整条命令原样执行。于是三种用法都成立：`docker compose run --rm app --workers 4`（追加；gunicorn 是 store 语义、同名的后者胜——实测 `--workers 1 … --workers 2` 起了 2 个 worker）、`docker compose run --rm app python manage.py migrate`（换整条命令）、worker 的 `entrypoint: ["celery"]` + `command:`（见 `docker-compose.yml`）。
- **gunicorn 可调参数在 `env/gunicorn.env`**：compose 的 app 服务用 `env_file: [env/app.env, env/gunicorn.env]` 按用途分别注入（worker 拿的是 `env/app.env` + `env/celery.env`，**拿不到** gunicorn 的旋钮），`docker/entrypoint.sh` 再用 shell 插值把它们拼进启动命令。**默认值只在 entrypoint 写一份**，文件里列出的就是同样的默认值，删掉或留空效果一样。清单：`GUNICORN_WORKERS` / `GUNICORN_TIMEOUT` / `GUNICORN_GRACEFUL_TIMEOUT` / `GUNICORN_KEEP_ALIVE` / `GUNICORN_MAX_REQUESTS` / `GUNICORN_MAX_REQUESTS_JITTER` / `GUNICORN_LOG_LEVEL`；空值 / 未设置都取默认（`:-` 语义），写 `0` 就是 0。改 `env/gunicorn.env` 后 `docker compose up -d app` 生效、不必重建镜像（但**改 `docker/entrypoint.sh` 或任何源码就得重建镜像**——它们都是 COPY 进镜像的，重启容器不会更新。**实测的坑**：`docker compose up -d --build app worker` 这**一条**命令里构建确实跑了（`app Built`、tag 换成新镜像 ID），但**容器不会跟着换**——同一次调用里容器的收敛判断用的是构建前的镜像解析，表现就是「改了代码却不生效」。可靠做法是把两步拆开：`docker compose build app worker && docker compose up -d app worker`（第二条会发现 tag 指向的镜像 ID 变了并重建；实测只 tag 换镜像、连 `up -d` 不带 `--build` 也会重建），或一条命令加 `--force-recreate`。验证手段 `docker compose exec app grep -n <新代码里的特征> <文件>`），`docker compose config` 可核对注入结果。**这些名字是 compose 层定的，不是 gunicorn 官方机制**：gunicorn 自己只认 `GUNICORN_CMD_ARGS`（把值当参数**追加**到最后）、`PORT`、`WEB_CONCURRENCY`，没有通用的 `GUNICORN_<SETTING>` 映射；也正因为 `GUNICORN_CMD_ARGS` 是追加语义（对 `--bind` = 多一个监听），**没有**用它。celery 那侧同理只有一个 `CELERY_LOGLEVEL`（`--concurrency` 刻意不暴露：同设备并发会写坏数据，见下文「关于并发」）。
- **`--bind` 是硬要求，不是可调参数**：它与 nginx 的 upstream 耦合（改地址必须同步 nginx 配置），而 gunicorn 自己的默认值是 `127.0.0.1:8000`——「只覆盖部分参数」时漏掉它就是 502；并且 `--bind` 是 **append** 语义（`gunicorn/config.py` 的 `action = "append"`），在默认命令之后再追加只会**多一个监听**、覆盖不掉。所以它和 `--worker-class` 一起写死在 entrypoint 的拼装命令里，**没有** `GUNICORN_BIND` 这类变量。（`--bind` 当然可以写成 `${GUNICORN_BIND:-0.0.0.0:8000}`——shell 插值是替换、不是追加，机制上完全可行；不做是**策略**选择：改地址必须同步改 nginx 的 upstream，给个变量等于给一个必然配错的旋钮。）
- **数据库迁移在容器启动时按需自动跑，并发由 advisory lock 串行化**：`docker/entrypoint.sh` 第 3 步调 `python manage.py migrate_if_needed`（`apps/core/management/commands/migrate_if_needed.py`），它只在**确实有未应用的迁移**时才执行 `migrate --noinput`——判断依据是 `MigrationExecutor.migration_plan(loader.graph.leaf_nodes())`（`migrate --check` 内部用的就是这套），已经是最新就只打印一行跳过，所以日常重启没有额外开销。**为什么包成管理命令、而不是 entrypoint 里两行 shell（`migrate --check || migrate`）**：Django 自己**不给 migrate 加锁**（翻遍 6.1.1 源码，`advisory` 零命中），多个 app 副本同时启动时两边的 `--check` 会同时看到「有未应用迁移」然后一起执行，轻则撞 `django_migrations` 的唯一约束、重则留下半应用状态；管理命令用**数据库自带的命名锁**把「检查 + 迁移」整段串起来——`postgresql` 走会话级 advisory lock（`SELECT pg_advisory_lock(0x6E65746F7073)`，lock/unlock 与迁移都走同一条默认连接），`mysql` 走 `GET_LOCK('netops_migrate', -1)` / `RELEASE_LOCK`（同样是会话级、不建库不建表，实测 `-1` 时被挡 4196 ms 后拿到锁、无人持锁时 216 ms 即返回），**其它后端直接 `ImproperlyConfigured` 报错**而不是「退化成不加锁」（那种假安全最坏；SQLite 是进程内嵌库、单实例部署不需要锁）——**先到的副本迁移，其余副本在锁上排队，拿到锁后再检查一次**（实测：另一个进程持锁 6 s 时，`migrate_if_needed` 被挡了 5.57 s，解锁后才检测并应用迁移）。开关是 `env/app.env` 的 `MIGRATE_ON_START`（默认 1；设 0 就整段跳过，交给外部发布流水线或人工），迁移失败则 `set -e` 直接退出、**不会**带着过期表结构起 gunicorn（实测：该命令不存在时容器启动即失败退出）。于是首次部署的第一次启动会自动建表，管理员则由下一步（`ensure_superuser`）零配置创建。**PG 前面不要挂 PgBouncer 的 transaction pooling**：官方特性表写着 `Session-level advisory locks` 在该模式下是 *Never*（事务一结束连接就被回收，`pg_advisory_unlock` 可能发到另一个后端上）；现在 app 直连 db、没有 pooler，不受影响。
- **初始管理员在容器启动时零配置创建**：`docker/entrypoint.sh` 第 4 步无条件调 `manage.py ensure_superuser`——**不占环境变量、不进 compose、不用 secret**（这是刻意的：初始管理员属于「零配置起步」那一环，挂到环境变量/compose/secrets 上等于要求每台部署机先准备一份配置，而这些值一旦进了环境变量就会出现在 `docker inspect`、`/proc/1/environ` 里）。判定只看数据库：**一个超级用户都没有**时才创建 `admin`，随机密码（`secrets.token_urlsafe()`）**直接打印在启动日志里**（`docker compose logs app`，抄下来即可登录），已有超管就是空操作。四条边界别改坏：① 已有超管 → 只打印一行跳过，不碰任何账号；② 同名账号存在但不是超管 → 只警告、**不自动提权**（静默把普通账号变超管是安全事故），也不改它的密码；③ 人工用法 `manage.py ensure_superuser --username ops --password '...'`（显式给的密码**不回显**）、`--update-password` 重置已有账号（新随机密码同样进日志）；④ 首次登录不需要预建 Token：`/api/auth/login/` 里是 `DRFToken.objects.get_or_create(user=user)`。
- **四个容器都有健康检查，worker 还依赖 app 的 healthy（为了等迁移跑完）**：app 探 8000 的 TCP（`socket.create_connection`），db 探 `pg_isready -U "$$(cat /run/secrets/postgres_user)"`（为什么不能省 `-U` 见上一条），nginx 探 `curl -fsS -m 3 --noproxy '*' -o /dev/null http://127.0.0.1/`（**必须 `--noproxy '*'`**：宿主机 shell 配了 `http_proxy` 时 Docker CLI 会把这些变量注入容器，`no_proxy` 由运维配置、很多环境里没有 127.0.0.1——实测不给 `no_proxy` 时裸 `curl` 返回 000/exit 7、busybox wget 直接 exit 1（它压根不认 `no_proxy`），带上 `--noproxy '*'` 才稳定 200；`-f` 让 4xx/5xx 也算失败——静态卷为空时 nginx 回 403/exit 22；curl 是 nginx:alpine 自带包 8.22.0），worker 探自己那个 celery 节点 `celery -A netops inspect ping -d "celery@$$HOSTNAME" --timeout 5`。worker 必须用 `-d` 把目标限定成自己：不限定就是「任意节点答了就算健康」，多副本时坏节点会被好节点掩盖；它走 broker，所以同时验证了「worker 进程活着」+「能连上 Redis」，比 `pgrep celery` 只看进程存在强。已知误报场景：worker 卡在长 CPU 任务里时控制命令要排队（故 timeout 10 s、retries 3 摊平）。worker 的 `depends_on: app: service_healthy`（而不是 `service_started`）是为了**等迁移完成**——worker 一上来就要读写那些表。nginx 的健康检查也不只是「探活」：**没有任何 server 块时 nginx 照样正常启动**（只是不监听端口），`conf.d` 没挂进来这类事故在 `docker compose ps` 里只会显示 Up，用 `wget` 探 80 才能把它变成 unhealthy（那次「访问 nginx 被 reset」就是这么暴露的）。
- **环境变量按「谁读」分三处**：`.env`（根）只给 compose 自己插值；`env/*.env` 按服务 `env_file` 注入容器（见 `env/README.md`）；`env/secrets/*` 只读挂载给凭据。三条规则：**compose 的 `${VAR}` 只读根 `.env`**（要在 compose 文件里插值的变量必须留在那儿；反过来说「只给容器用」的放 `env/*.env` 就够）、`environment:` 优先于 `env_file`、多个 `env_file` **后面的覆盖前面的**。一个顺带的坑：worker 的 `--loglevel` 要读 `env/celery.env`，而 compose 会对自己的文件做 `${...}` 替换（读不到那些文件），所以那里写的是 `$${CELERY_LOGLEVEL:-info}`——`$$` 被还原成字面 `$`，再交给容器内的 `sh -c` 展开（`entrypoint: ["/bin/sh", "-c"]` + `exec` 保证 celery 是 PID 1、能收到信号）。
- **数据库凭据走 docker secrets，不再进 `.env` / 环境变量**：`env/secrets/postgres_user`、`env/secrets/postgres_password` 由 compose 顶层 `secrets:` 挂进容器（非 swarm 模式就是只读 bind mount 到 `/run/secrets/<name>`）；指向它们的 `POSTGRES_USER_FILE` / `POSTGRES_PASSWORD_FILE` 写在 `env/db.env`（给 db）与 `env/app.env`（给 app / worker）里——db 由 postgres 官方镜像自己读，app / worker 由 `settings.py` 的 `_env_or_file()` 读（没有 `*_FILE` 时回退同名环境变量，宿主机直跑 Django 不受影响）。为什么要换：环境变量在 `docker inspect`、`/proc/1/environ` 里都是明文，secret 文件只有挂它的容器看得到。生成与迁移：`bash env/secrets/generate.sh`（默认**沿用 `.env` 里旧的值**——postgres 只在**首次初始化数据卷**时应用凭据，换值不会改库里已有的密码，详见 `env/secrets/README.md`）；密钥文件不入库（`.gitignore`）、不进构建上下文（`.dockerignore`）。两个连带改动别改回去：① postgres 官方 entrypoint 规定 `POSTGRES_USER` 与 `POSTGRES_USER_FILE` **同时设置就直接报错退出**，所以 env 文件里只留 `_FILE`；② db 的 healthcheck 不能用 `pg_isready -U ${POSTGRES_USER:...}`（用户名只在 secret 文件里，compose 插值取不到），但**也不能省掉 `-U`**：healthcheck 由 docker 以镜像默认用户（**root**，官方 postgres 镜像容器里就是 root，entrypoint 内部才 gosu）执行，不带 `-U` 会拿 root 去连、postgres 日志被 `FATAL: role "root" does not exist` 刷屏，而 pg_isready 仍返回 0（只看服务器是否响应）→ 容器照样 healthy、问题不暴露。正确写法是让容器内的 sh 读 secret：`pg_isready -U "$$(cat /run/secrets/postgres_user)" -d "$${POSTGRES_DB:-netops}"`（compose 的 `$$` 到容器里才是 `$`）。`POSTGRES_DB` 不是密钥，仍在 `env/db.env` / `env/app.env` 里；redis 密码仍是环境变量（redis 官方镜像没有 `*_FILE` 机制）。
- **代理感知配置**：`SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")` 让 Django 识别 nginx 传来的原始协议；`ALLOWED_HOSTS` 由环境变量 `DJANGO_ALLOWED_HOSTS` 控制（默认 `*`），CSRF 可信来源由 `DJANGO_CSRF_TRUSTED_ORIGINS` 控制（默认空）。
- **nginx 必须透传带端口的 Host（`$http_host`），否则后台登录 403**：nginx 变量 `$host` **不含端口**，所以宿主映射到非标准端口（`.env` 的 `NGINX_PORT=8000`）时 Django 的 `request.get_host()` 得到 `localhost`，而浏览器 Origin 是 `http://localhost:8000`——Django 4+ 的 Origin 校验只认「当前 host」与 `CSRF_TRUSTED_ORIGINS`，于是 `/admin/login/` 直接 403：`Forbidden (Origin checking failed - http://localhost:8000 does not match any trusted origins.)`。**实测对照**：同一个请求只把 Host 从 `localhost:8000` 换成 `localhost`，失败原因立刻从 Origin 变成「CSRF cookie not set」（即 Origin 已通过）——端口就是唯一变量。所以 conf.d 的两个 server 块都用 `$http_host`（客户端原样的 Host，含端口），`X-Forwarded-Host` 同理。`DJANGO_CSRF_TRUSTED_ORIGINS` 只在「浏览器看到的来源 ≠ 转发给 Django 的 Host」时才需要（外层还有 LB/网关改写 Host、TLS 在外层终结等），值必须带 scheme。这条契约由 `tests/deploy/test_reverse_proxy_config.py` 守（含一条「Host 带端口则同源 Origin 可信」的 Django 侧测试）。
- **「账号密码换 token」的接口必须显式 `@authentication_classes([])`**：DRF 的 `SessionAuthentication` 一旦发现请求带着**已认证的 session** 就会自己调 `enforce_csrf()`——这条路径是 DRF 发起的，**绕开**中间件层面的 `csrf_exempt`（`APIView.as_view()` 本就对整个视图 csrf_exempt）。所以浏览器里登录过 `/admin/` 之后，`/api/auth/login/` 会因为带 `sessionid` 而 403（`{"detail": "CSRF Failed: ..."}`）；而换个 host 就"好了"——`localhost:8000` 与 `127.0.0.1:8000` 的 cookie 互相带不上，**别被这种"换个地址就好了"骗过去**（本仓库真踩过：先以为是 nginx 丢端口，改完 nginx 仍然 403）。`login` 不需要任何身份、也就没有需要 CSRF 保护的东西，已在视图上关掉认证；`logout` / `me` 前端都会带 `Authorization`，TokenAuthentication 先命中就返回，`SessionAuthentication` 根本不执行，故不受影响。三条测试分别守「不带 cookie 正常」「带 session cookie 不被 CSRF 拦」「带 token 的请求不受 session cookie 影响」：`tests/core/test_auth_login_csrf.py`。
- **前端请求路径**：以 `/api/` 开头（如 `/api/assets/devices/`）。
- **前端自动导入**：使用 `unplugin-auto-import` + `unplugin-vue-components`（`ElementPlusResolver`）。
- **前端函数风格**：`.vue` 与 `.ts` 一律使用箭头函数，不使用 `function` 声明——普通函数 `const fn = (a: T) => {}`、异步 `const fn = async () => {}`、泛型 `const fn = <T>(a: T) => {}`。原因是 `function` 声明会被提升，容易掩盖定义顺序问题，也与项目既有写法保持一致。自检命令（应无输出）：
  `grep -rnE "^[ \t]*(export )?(async )?function [A-Za-z_$]" frontend/src --include=*.ts --include=*.vue`
- **Ruff**：`line-length = 120`；`select = ["E","F","I","N","W"]`，忽略 `F405/F403/E402`；`known-first-party = ["assets","core","ops"]`；`**/migrations/*` 忽略 `E501`，并通过 `[tool.ruff.format]` 排除（Django 生成的迁移文件不参与格式化）。
- **测试**：pytest + pytest-django，`DJANGO_SETTINGS_MODULE = "netops.settings"`，`testpaths = ["tests"]`。测试统一放项目根 `tests/<应用>/`，不散落在应用目录内；应用下不再保留 Django 脚手架的 `tests.py`（pytest 不收集该文件名，留着只会误导）。各层目录带 `__init__.py`，测试模块路径形如 `tests.assets.test_analysis`。
- **测试内的资源定位**：用包路径（`Path(ops.__file__).parent / ...`）或 `settings.BASE_DIR`，**不要**用 `Path(__file__).parent.parent`——后者依赖测试文件自身位置，目录一挪动就静默失效（曾导致 `data/configs/` 被解析成 `apps/ops/data/configs`，测试因 `exists()` 判断而长期空跑）。

## 三层架构

### 核心层 `core/`

用户与认证。

| 模型 | 职责 |
|------|------|
| `User` | 扩展 `AbstractUser`，增加 `phone`、`avatar` 字段 |
| `Token` | API Token，`key` 由 `secrets.token_hex(32)` 自动生成 |

### 资产层 `assets/`

全部数据模型集中在 `apps/assets/models.py`，按领域分组：

| 领域 | 模型 |
|------|------|
| DCIM | SecurityZone, DataCenter, Room, Cabinet |
| 设备 | Vendor, DeviceModel, Device, DeviceConnection, DeviceConfig, DeviceAccount, DeviceGroup, DeviceGroupMember |
| 配置基类 | `ConfigBase`（被 Vrf/Interface/LTM/GTM/防火墙等模型继承） |
| 网络 | Vlan, Vrf, Interface, SnmpConfig, NtpConfig, SyslogConfig |
| 负载均衡 LTM | LtmVirtualServer, LtmPool, LtmPoolMember, LtmProfile, LtmIRule, LtmSNAT, LtmPersist |
| 全局负载均衡 GTM | GtmDatacenter, GtmWideip, GtmPool, GtmServer, GtmVServer |
| 防火墙 | AddressBook, Service, Policy, NatRule |
| IPAM | Tag, Subnet, IPAddress, SubnetUsageLog |
| 路由与其它 | Route, Topology, ArpMac |
| 人工维护 | ServerOwner（服务器 IP ↔ 负责人；不从设备配置提取，故不进 `ConfigBase`） |

### 操作层 `ops/`

配置解析、存储与路径追踪。

| 模块 | 职责 |
|------|------|
| `parsers/factory.py` | `ParserFactory` + `BaseParser`(ABC)，按 `(vendor, device_type)` 注册 |
| `parsers/tmpls/` | TTP 解析模板（`configs/`、`running/`） |
| `savers/base.py` | `BaseSaver`(ABC)，通过 `__init_subclass__` 自动注册 |
| `savers/registry.py` | Saver 注册表 |
| `config_repo.py` | Git 配置仓库的读取、历史、diff |
| `path_tracer.py` | 路径追踪（模拟报文逐跳转发） |
| `signals.py` | `DeviceConfig` 保存后触发解析与入库 |
| `config_owner.py` | 配置属主解析（堆叠组备机归属主设备） |
| `parsers/template_keys.py` | 从 TTP 模板静态提取顶层数据键 |
| `parsers/contract.py` | 解析器 / Saver 的契约缺口清单（测试与接口共用） |
| `pipeline.py` | 配置处理流水线，信号与 `reparse` 命令共用 |
| `workflow.py` | 任务工作流的入口：`start_task`（建 Task + 投递采集阶段）、`dispatch_stage`、`cancel_task`、`submit_config_job` |
| `models.py` | `InternetAnalysis`：互联网资产分析结果缓存 |
| `api/analysis.py` | 互联网资产分析的查询 / 分析 / 导出接口 |

**已注册解析器**（`@ParserFactory.register`）：

`A10/slb`、`Cisco/firewall`、`F5/gslb`、`F5/slb`、`H3C/switch`、`H3C/router`、`Hillstone/firewall`、`Huawei/switch`、`Maipu/switch`、`Ruijie/switch`

**Saver 实现**：InterfaceSaver、VrfSaver、RouteSaver、VlanSaver、SnmpConfigSaver、LBVirtualServerSaver、LBPoolSaver、LBSnatSaver、GTMWideipSaver、GtmDatacenterSaver、GtmServerSaver、GtmPoolSaver、AddressBookSaver、ServiceSaver、PolicySaver、DeviceAccountSaver、NatRuleSaver

其中 Route / Vlan / SnmpConfig / Policy / GTM 三个 / DeviceAccount / AddressBook / NatRule / LtmProfile / LtmIRule / LtmPersist 走「Saver 调用序列化器」路径（`BaseSaver.upsert`），其余仍是原生 ORM，待逐步迁移。`LBVirtualServerSaver` 除虚拟服务器外，还负责同一份 `virtuals` 产出里嵌套的 `LtmProfile` / `LtmIRule` / `LtmPersist`（这三个是设备级清单，没有指向 virtual server 的外键）。`GtmServerSaver` 同理兼写 `GtmVServer`。

`ConfigBase` 下有 24 个子模型，其中 22 个已配 Saver。几个需要留意的点：

- `Vlan` / `Route` / `SnmpConfig` / `NtpConfig` / `SyslogConfig` 原为裸 `models.Model`，已改为继承 `ConfigBase`（migration `0023` / `0024`）。代价与收益：`SnmpConfig` / `NtpConfig` / `SyslogConfig` 的 `device` 由一对一变成外键（基数 1:1 → 1:N），各自重复声明的 `created_at` / `updated_at` 与基类同名同义故删除，`related_name` 变为默认的 `<model>_set`；`Vlan.device` 由可空变为必填；`Route` 新增 `device`，与 `vrf.device` 冗余，Saver 入库时用 `vrf` 保证一致，缺失时挂到设备的 `default` VRF。
- `LtmPoolMember` 原为裸 `models.Model`，只有 `pool_name` 字符串、没有 `device`，已改为继承 `ConfigBase`（migration `0026`）。**它保留 `pool_name` 而不是改成指向 `LtmPool` 的外键**：归属靠 `device` 限定，因为 `LtmPool` 的 `(device, name)` 唯一，「设备 + 池名」才能定位到唯一的池。唯一约束是 `(device, pool_name, name, port)`——必须带 `port`，F5 同一节点可以在多个端口上做成员，剥掉 `/Common/node_a:80` 的端口后 `name` 都是 `node_a`，只约束 `name` 会误杀合法数据。存量迁移只有 `pool_name` 可用，无法唯一映射到设备的行（孤儿 / 多台设备同名池）直接删除并在迁移输出里逐条打印，之后再按新唯一键去重。所有按 `pool_name` 查成员的地方（`LBPoolSaver`、`ops/api/analysis.py`、`ops/path_tracer.py`）都必须同时限定 `device`，否则不同设备上的同名池会互相串；`LBPoolSaver` 先删后建时也会跨设备误删。
- `NatRule` 的三个匹配 M2M（`source_addresses` / `destination_addresses` / `services`）是 `blank=True`——不同厂商的 NAT 配置能提供的信息差别很大，cisco 的 `nat` group 只有 `network_name`/`host_ip`/`public_ip`，给不出任何 service。
- `RouteSaver` 的 `static_routes` 模板键名不统一：Maipu / Ruijie 用 `subnet_mask`，其余用 `mask`；cisco 还带 `interface_name` 与 `metric`。
- `SnmpConfigSaver` 兼容两种产出形态：Huawei / H3C router 的 `community` + `access_type` + `host_ip`，以及 H3C switch（Comware V7）的 `target_hosts[].ip` + `securityname`。
- `PolicySaver` 消费 `policies` / `acl` / `rules` 三种形态。hillstone 的 `rules` 是扁平的分列地址，会先落成 `AddressBook` 再挂 M2M：带 `/` 的 `-ip` 是子网、不带是主机；`-address` 是**地址簿引用**（按名字取用，不存在则建占位记录，内容留给 AddressBookSaver 填）；`-range` 拆成 `ip_start` / `ip_end`；`-host` 是主机。`action` 各厂商用词不同（`permit` / `drop` ...），Saver 统一归一为模型的 `allow` / `deny`。
- hillstone 模板原先同时存在 `rules` 与 `rules2` 两套提取规则（同一批 `rule id` 会被解析两遍：`rules` 多一层 `src` / `dst` 嵌套但**完全不提取 range**）。现已合并为单一的 `rules`（扁平形态），并把 `src-range` / `dst-range` 的变量名分开——原先两者都叫 `range`，两个值会混进同一个列表而分不清源/目的。仅为旧 `rules` 服务的 `<vars>` 与 `<macro>` 也已移除。

**尚未覆盖的两处**：

- `NtpConfig` / `SyslogConfig` 已继承 `ConfigBase`，但**没有 Saver**：模板侧还没有 ntp / syslog 产出，写了也永不触发。补齐需连模板一起加 group。
- `SecurityZone` 保持裸 `models.Model`：它是安全域这类人工维护的信息，不从设备配置提取，故不纳入 `ConfigBase`。

## 配置处理流程（信号驱动）

```
DeviceConfig 保存（post_save 信号）
    ↓
从 Git 读取配置原文（config_repo）
    ↓
ParserFactory 按 (vendor, device_type) 选择解析器
    ↓
TTP 模板解析 → 结果写回 config_json
    ↓
按 key 分发给对应 Saver → 写入数据库
```

`signals.py` 的处理器仅在 `created=True` 时触发，并用 `_processing` 集合防止递归。

**关于并发（实测结论）**：

- 信号是**完全同步**的：在 `DeviceConfig.save()` 的调用栈里跑完「读 Git → 解析 → 全部 Saver」，无线程池、无队列、无 async。`_processing` 是模块级 set，只在本进程内有效，且键是 `DeviceConfig.pk` 而非设备 id——**同一台设备的两个 DeviceConfig 并行进入流水线时它挡不住**。注意它其实只在「同一 pk 再次 `created=True`」时才会生效，而这不可能发生（pk 唯一），所以当前流程里它是冗余的；嵌套那次 `config_json` 回写是 `created=False`，在第 21 行的 `not created` 就已经返回。**更新已有的 DeviceConfig 永远不会触发流水线。**
- **不同设备可以并行**：`runserver` 默认多线程（`--nothreading` 是 `store_false`），而负载是 DB 往返瓶颈（每语句约 0.95 ms，Postgres 跑在容器里、经宿主机端口映射），socket I/O 期间释放 GIL。实测 4 台设备 4 线程 18.34 s → 5.49 s（3.34x）。
- **同一设备并行会写坏数据**：同一设备 4 线程并发写 4 份不同配置（100 个池），8/8 轮最终成员表混进 2–3 份配置的地址，并出现 19 次 `duplicate key ... uni_pool_member_device_pool_node_port`。2 线程时是间歇性的（6 轮中 1 次、10 轮中 0 次），更难发现。而且失败被 `_dispatch_savers` 按 Saver 吞掉只打日志，HTTP 请求照样返回成功。
- `reparse --workers N` 的并行单位是**设备**，且命令内部保证每台设备只派一个任务（同一个 hostname 重复传入会去重）。它**只保证本命令内部**不会同设备并发；Web 导入路径没有设备级互斥。

**Saver 的写库方式与性能**：瓶颈是**语句条数**，不是事务数——本机 Postgres 跑在容器里（`netops-db`，端口映射到宿主机），每跳往返约 0.95 ms，而 `COMMIT` 几乎免费（`synchronous_commit=off` 与包一层事务都只有 1.5x 左右，说明不是 fsync 的问题）。所以 `BaseSaver` 提供两个写入入口：

- `upsert(...)`：单条，按自然键定位后走序列化器保存。
- `bulk_upsert(model, device, rows, key_fields=..., serializer_cls=...)`：一次 SELECT 取现有行，再一次 `bulk_create` / 一次 `bulk_update`。**仍然逐行走序列化器校验**（保持 views 与 savers 共用同一套字段规则），只是把语句数压下来。同批内相同键按「后来者覆盖」去重，否则会直接撞唯一约束；键字段用 `.get`，可空键（如只在 range 上才有的 `ip_start`）缺失即 `None`。`bulk_update` 不走 `pre_save`，`updated_at` 由助手自己填。**不支持 M2M**：带 M2M 的模型要在调用方自己批量写关联表（见 `PolicySaver._replace_m2m`，用 `attname` 传 pk，字段名那个描述符只接受模型实例）。

实测（200 行规模，合成真实配置）：按 Saver 合计 **53.92 s / 13985 条 SQL → 9.47 s / 2802 条**（5.7x，每行 6.2 → 1.7 条）；端到端 4 台设备 **37.39 s → 7.64 s**（4.9x），F5 SLB 那台 12.21 s → 0.24 s。剩下每行约 1–2 条 SQL 来自 DRF 自身：`PrimaryKeyRelatedField` 无条件 `queryset.get(pk=...)`（DRF 没有「传模型实例就短路」的分支），以及 `UniqueTogetherValidator` 每次校验一条查询——这两项是「Saver 走序列化器」的固有代价，没有动。

`LBPoolSaver` 的池成员没有独立自然键，只能「先清后建」，清理范围按「设备 + 池名」圈定并整批一次 DELETE + 一次 `bulk_create`；池名列表为空时不动成员。

## API 路由

`netops/urls.py` 依次 include 三个应用的 urls，全部挂载在 `/api/` 下。

**core**（`core/api/urls.py`）

| 路径 | 说明 |
|------|------|
| `/api/auth/login/` | 登录获取 Token |
| `/api/auth/logout/` | 登出 |
| `/api/me/` | 当前用户信息 |
| `/api/tasks/` | 任务列表 / 新建（**新建即投递采集阶段**，是 Celery 工作流的入口） |
| `/api/tasks/<id>/` | 任务详情（含嵌套的阶段数组） |
| `/api/tasks/<id>/cancel/` | 取消任务（已结束的返回 400） |
| `/api/stages/` | 阶段列表（只读，可按 `task` / `stage_type` / `status` 过滤） |

**assets**（`assets/api/urls.py`，前缀 `/api/assets/`）

DRF `SimpleRouter`（`trailing_slash=True`），资源列表：

```
security-zones, datacenters, rooms, cabinets,
vendors, device-models, devices, device-configs, device-connections, device-accounts,
device-groups, device-group-members,
vlans, vrfs, interfaces,
snmp-configs, ntp-configs, syslog-configs,
ltm-virtual-servers, ltm-pools, ltm-pool-members, ltm-profiles, ltm-irules, ltm-snats, ltm-persists,
gtm-datacenters, gtm-wideips, gtm-pools, gtm-servers, gtm-vservers,
address-books, services, policies, nat-rules,
routes, topologies, arp-mac, subnet-usage-logs,
tags, subnets, ip-addresses
```

另有函数视图：

| 路径 | 说明 |
|------|------|
| `/api/assets/overview/` | 总览聚合统计 |
| `/api/assets/import-devices/` | Excel 导入设备 |

**ops**（`ops/api/urls.py`）

| 路径 | 说明 |
|------|------|
| `/api/trace/` | 路径追踪 |
| `/api/trace/route-collect/` | 路由采集 |
| `/api/trace/route-collect-raw/` | 路由采集（原始输出） |
| `/api/trace/routes/` | 路由列表 |
| `/api/trace/dns-query/` | DNS 查询 |
| `/api/configs/git-content/` | 获取指定 commit 的配置内容 |
| `/api/configs/git-diff/` | 对比两个版本的配置差异 |
| `/api/configs/history/` | 设备配置变更历史 |
| `/api/configs/devices/` | 列出有配置的设备 |
| `/api/parsers/` | 已注册解析器列表 |
| `/api/parsers/mapping/` | 解析器 → 模板 → 产出键 → Saver 的映射清单与契约缺口 |
| `/api/parsers/templates/` | TTP 模板文件列表（`configs/` + `running/`） |
| `/api/parsers/templates/<name>/` | 模板文件内容 |
| `/api/parsers/templates/<name>/update/` | 更新模板文件内容（PUT） |
| `/api/internet-analysis/` | 互联网资产分析结果（**只读缓存**，未分析过返回 404） |
| `/api/internet-analysis/analyze/` | **触发分析**并刷新缓存（POST） |
| `/api/internet-analysis/export/` | 导出缓存结果为 xlsx（只读缓存） |

## 注意事项

- **解析器模板管理页面**（`frontend/src/views/devices/parsers.vue`）以**模板文件**为中心：单表展示 `分组(configs/running) | 文件名 | 关联解析器`，解析器对模板的引用降级为该表的「关联解析器」列（未被引用的显示「未关联解析器」，可用「仅看未关联」筛选），点击行在右侧预览/编辑。此前「解析器列表 + 模板文件列表」两张表的写法存在信息重叠——8 个已注册解析器必然出现在文件列表中，故已合并。
- **F5 池成员的端口分隔符有两种**：名字是普通串或 IPv4 时用冒号（`/Common/node:80`），名字本身是 IPv6 字面量时 F5 改用一个点号（`/Common/2001:db8::1.80`）。所以 `f5_ltm.ttp` 的 `pools` 里成员有两条备选行（点号那条是回退），**并且端口必须限成纯数字**（`vars` 块里的 `PORT`）——不限的话冒号那条会把 IPv6 成员贪婪切成 `name="/Common/2001:db8:"`、`port="1.80"`，永远轮不到回退行，表现为「端口被相邻成员的值带偏」。
- **TTP 模板里的注释是纯文本、不是 XML 注释**：注释行里出现尖括号（例如直接写 `<vars>` 或 `<group>`）会被当成未闭合标签，整个模板解析失败。`re()` 只认内置名（`IP` / `IPV6`）或 `vars` 块里声明的名字，不能内联写正则。内置 `IPV6` 正则只认十六进制与冒号、**不含点号**，覆盖它要谨慎。
- **`parsers/tmpls/running/` 下的模板不在 `ParserFactory` 注册表内**（`route.ttp`、`arp.ttp`、`mac.ttp`、`lldp.ttp`、`h3c_route.ttp`），由路径追踪/路由采集接口（`ops/api/trace.py`）按名称动态调用；它们在页面上显示为「未关联解析器」，但不代表可以删除。
- **列表分页与搜索排序**：DRF 全局启用数字分页（`netops/pagination.py` 的 `StandardPagination`，默认 50 条/页、最大 500 条，客户端可用 `?page_size=` 覆盖），列表接口返回 `{count, next, previous, results}`；`DEFAULT_FILTER_BACKENDS` 启用 `SearchFilter` / `OrderingFilter`，各 ViewSet 通过 `search_fields` / `ordering_fields` 声明可用字段。前端统一用 `useCrudApi` + `DataPagination` 消费；必须全量的场景（下拉选项、前端聚合统计）用 `fetchAllPages`。时序大表（ARP/MAC、路由、子网使用率）后续可单独启用游标分页。
- **`apps/ops/ansible/` 只剩 `__pycache__`**，源文件已删除，属重构残留。
- `ops` 应用的 label 是 `operator`（`OperatorConfig.label`），migrate 时用 `operator` 而非 `ops`。
- **互联网资产分析走缓存**：结果存 `ops.models.InternetAnalysis`，只有 `POST /api/internet-analysis/analyze/` 才真正计算；查询与导出接口都只读缓存，未分析过时返回 404。
- **资产分析的表格列**：后端 `build_path_rows` 与前端 `internet-asset.vue` 里的 `buildPathRows` 是**两份各自独立**的扁平化实现（列序必须手工保持一致）。当前 7 列：域名 / LLB_VS地址#端口 / LLB_Rule规则 / SLB_VS地址#端口 / SLB_Rule规则 / 服务器地址#端口 / 负责人。
- **地址与端口之间用 `#`，不要用 `:`**：IPv6 地址本身带冒号，`2001:db8::1:80` 分不清哪一段是端口（回退写法 `[...]:80` 虽标准，但 IPv4 用方括号又多余）。`#` 不可能出现在 IPv4/IPv6 里，含义唯一且紧凑。分隔符是两端各一个常量——后端 `analysis.py` 的 `TARGET_SEPARATOR`、前端 `internet-asset.vue` 的同名常量，改要一起改（有测试守 `#` 不可能出现在 IP 里、且能唯一切回）。`ip_port` / `matched_ip_port` / `fallback_ip_port` 这几个内部字段也走同一个拼接函数，它们只出现在前端类型声明里、从未被展示。
- **为什么只有 7 列**：**LLB 的池成员地址#端口 就是 SLB 虚拟服务器的地址#端口**（同一份数据，LLB 池成员指向下一级 SLB），所以不各占一列；「服务器地址#端口」是链路最后一跳的池成员（两级取 SLB 的、一级取 LLB 的，断链时回退到 GTM 地址，见 `_final_target`）。有测试 `test_llb_member_equals_slb_virtual_server` 守这个前提。
- 行字典里仍保留 `llb_address`/`llb_port`/`slb_member_address` 这类**分列字段**（导出与前端展示时再按 `TARGET_SEPARATOR` 拼成 `地址#端口`），`note`/`rtype`/`gtm_ip` 也仍在行里，只是不再出现在表格与导出中——`note` 还被前端用来算「已解析」条数，删列时别顺手删字段。`EXPORT_COLUMN_WIDTHS` 的条数必须与 `EXPORT_HEADERS` 相同（有测试守），列宽按序号用 `get_column_letter` 生成，别再写死 `"ABCDEFGHIJKLM"`。
- 前端模板里**不要把 `row` 作为参数传给函数**（`serverTarget(row)`）：Element Plus 插槽给的 `row` 是它自己的 `DefaultRow`，传给形参类型为 `PathRow` 的函数会 `vue-tsc` 报错；把拼接好的值预先算进行字段（如 `llbTarget`/`slbTarget`/`serverTarget`）再读属性即可。
- **清理配置数据要用 `manage.py purge_configs`**：配置**原文**只在 Git 仓库里，解析**结果**写在各资产表里，而这些表与 `DeviceConfig` **没有任何外键**——所以删 `DeviceConfig`、删仓库都不会级联清掉它们，手工清必漏。命令把「配置解析产物」定义为 `ConfigBase.__subclasses__()`（运行时枚举，当前 24 个；实测 Saver 写入的模型全部是它的子类，不存在"配了 Saver 却不属于 ConfigBase"的漏网之鱼），再加上 `DeviceConfig` 与 `InternetAnalysis` 派生缓存。默认**只报告**（dry-run），`--yes` 才删；`--with-workflow` 才清 Task/Stage（`Stage.output_data` 里可能存着配置**全文**）；`--purge-repo` 才动文件系统，且它会删掉**整个**仓库、所以强制 `--all`。人工 / Excel 数据（Device、DCIM、ServerOwner 等）永远不动；堆叠组的备机不持有配置，`--device <备机>` 会用 `resolve_config_owner` 折算到主设备。两个坑：`Route`/`Vrf` 与运行态采集接口（`/api/trace/route-collect*`）共用同一张表，按表清分不出来源；另外 config_repo 现在**只有一份**：宿主机的 `./data` 直接 bind 到 app/worker 的 `/app/data`（以前是命名卷 `app_data`，两边各一份、互不影响），所以宿主侧删仓库就是容器里删仓库；若旧卷还在，它是**另一份**历史数据，要单独处理（`docker volume rm network_ops_app_data`）。执行前先 `docker compose stop worker`。
- **导入服务器负责人**：`python manage.py import_server_owners --file x.xlsx`（sheet `servers`，列 `hostname` / `ip` / `owner`，另有 `--sheet` / `--dry-run`）。**按列名取而不是按位置**——表头可以换序、可以夹带无关列，缺列直接报错并列出实际表头，避免把 `ip` 静默串到 `hostname` 上。`ip` 是唯一键（导入时用 `ipaddress` 规范化，`2001:DB8::1` 与 `2001:db8::1` 落同一条），文件内重复取最后一行；更新**只覆盖 hostname / owner，不动 `status`**（这份表没有 status 列，不能把手工停用的记录导成启用）。有非法行时**整批不导入**并以非零退出码收尾，不做「写一半再报错」。
- **「负责人」列**：按链路**最后的 IP**反查 `ServerOwner`，回退顺序是 `slb_member_address → llb_member_address → gtm_ip`（见 `_final_ip`）。匹配前两边都过 `_normalize_ip`，否则 `2001:DB8::1` 与压缩写法对不上。负责人**不进分析缓存**——它挂在 `build_path_rows`/`GET` 响应上现查，改了负责人不必重跑分析。前端表格自己扁平化、拿不到数据库，所以 GET 响应额外给一份 `owners`（键是链路最后 IP 的**原始写法**，与前端用同一份回退规则取值），避免在 JS 里重实现 IPv6 规范化。
- `Topology` 是单模型，图数据存于 `graph_data` JSON 字段，没有独立的节点/边表。
- `Device` 没有 `address` 字段，地址信息在 `DeviceConnection` 中。
- 操作层应用目录名为 `ops`（避免与 Python 标准库 `operator` 冲突）。
- 前端拓扑图使用 `@antv/g6` 5.x。

## 语言约定

- **思考过程用中文展示**：Agent 的分析、推理、解释等思考过程必须使用中文输出。
- 代码注释、commit message、PR 描述等技术文档使用中文。
