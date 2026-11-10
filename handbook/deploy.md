# 部署与容器化

compose 起 **db(TimescaleDB) / redis / app / worker / nginx**，nginx 是统一入口。
本文档收「部署侧的硬要求与代价」；构建顺序、分层取舍、`uv sync` 参数、冒烟清单契约见
`entrypoint/README.md` 与三个 Dockerfile 头部指针。第三方软件的实测行为（compose 插值、
挂载属主、容器里 git、健康检查、nginx resolver、uv）在 `.dsh/skills`，本文只点名。

## 入口与静态资源

`nginx/` 作为统一入口（80/443）：`/api/*`、`/admin/*`、`/media/*` 代理到 compose 里的
**app 容器**（不再指向宿主机 Django），`/assets/*`、`/static/*` 由 nginx 直出。

静态资源的流向：

```
宿主机（pnpm build + collectstatic）
  → Dockerfile.app COPY 进镜像的 /app/www 与 /app/frontend/dist（即 STATIC_ROOT / FRONTEND）
  → 启动时 entrypoint 复制另一份到命名卷 static_data
  → nginx 只读挂载该卷
```

**静态卷的布局按 URL 前缀设计**：`<卷>/index.html` + `<卷>/assets/*`（Vite）+
`<卷>/static/*`（collectstatic），所以 nginx **一个 root**（`/usr/share/nginx/html`）就覆盖
`/`、`/assets/*`、`/static/*`；宿主机上 `www/` 与 `frontend/dist/` 仍各由自己的工具清空
（`collectstatic --clear` / `pnpm build` 的 `emptyOutDir`），只有容器里这一份被合并。
为什么非要绕一层卷（跨容器只能靠卷；卷会遮住镜像内容且只播种一次）：技能
`nginx-container-proxy` 第 6 节。入口脚本每次都**权威**重铺，清卷根时用 `! -name static`
排除 `static/`。

**不用 `volumes_from`**：它会把源容器的**所有**卷带过来、且容器内路径被绑死；显式写
`static_data:/usr/share/nginx/html:ro` 才能只读、挑卷、放在 nginx 自己的路径上。

**nginx 侧与本项目耦合的两条硬要求**：

1. 后端地址用**变量式** upstream（`set $netops_upstream "app:8000"`）并配 `resolver`，
   `resolver` 地址在启动时从 runtime 的 `/etc/resolv.conf` 推导（写死 `127.0.0.11` 换
   Podman 就 502）——做法见 `nginx/docker-entrypoint.d/05-netops-resolver.sh`；
2. conf.d 必须用 `$http_host`（含端口）透传 Host，否则后台登录 403（`$host` 会丢端口）。

这条契约由 `tests/deploy/test_reverse_proxy_config.py` 守。

## 两个数据目录：卷 vs 只读 bind

| 路径 | 形式 | 为什么 |
|------|------|--------|
| `/app/data/config_repo` | **命名卷** `config_repo_data`（读写） | 解析流水线的内部工作目录，**不需要宿主可见**；属主继承自镜像、容器 root 写自己的卷，无需 uid 对齐（技能 `docker-mounts-and-ownership`） |
| `/app/data/configs` | **只读 bind** `./data/configs:ro`（long syntax + 显式 `create_host_path: false`） | 运维放文件的地方（Excel「配置文件」sheet 的 `config_dir`，按**进程 CWD** 解析）；缺 `data/configs` 时 `up` 直接报错，而不是让 dockerd 建一个 root 属主、宿主用户写不进也删不掉的空目录——**首次部署要先 `mkdir -p data/configs`** |

worker **只**挂那个卷（导入配置是 app 的接口）。

`config_repo` 是**每台设备一个独立仓库**（`init_repo(hostname)` 在
`data/config_repo/<hostname>/` 下 git init + 初始 commit），`save_config` / `get_config` /
`diff_configs` / `get_history` 都按设备打开；内容未变时返回**自己**的上次提交
（`configs` 表按 `(device, hash)` 去重因此天然命中，不会拿到别的设备的 commit）。首次打开
某设备仓库时，自动把旧**共享仓库**（根 `.git`，只读兜底、不主动创建）里该设备的历史重放
进来并回写 `DeviceConfig.git_commit_hash`。

**沿革别绕回去**：它曾经是 bind，为此要「容器跑成宿主 uid + `export UID GID` +
`HOME=/tmp` + 静态卷 777 + `safe.directory` + 两处挂载点自检」，这些**已全部删除**；唯一
保留的是**镜像里的 git 提交身份**（`user.name` / `user.email`），它不是为 bind 服务的
（原因见技能 `git-in-containers`）。

**代价**：宿主侧看不到这份仓库，宿主直跑 Django 用的是 `<项目根>/data/config_repo`
（另一份，dev 用）。看/清理容器那份：

```bash
docker compose exec app git -C /app/data/config_repo/<hostname> log --oneline
docker compose exec app python manage.py purge_configs --all --purge-repo --yes
# 把已有宿主仓库搬进空卷
docker compose run --rm --no-deps -v ./data/config_repo:/from:ro app sh -c 'cp -a /from/. /app/data/config_repo/'
```

卷名用新的 `config_repo_data`（不复用旧 `app_data`，避免静默合并两份历史）；旧的
`network_ops_app_data` 卷不会自动删除，确认空后可 `docker volume rm`。

## 启动命令与旋钮

**整条启动命令在 entrypoint 里拼：硬要求写死，可调参数取环境变量**。`entrypoint/app.sh`
拼出 `gunicorn netops.asgi:application --worker-class uvicorn_worker.UvicornWorker --bind
0.0.0.0:8000 --workers "${GUNICORN_WORKERS:-1}" …`；**镜像里刻意没有 CMD**（同一个镜像还要
当 celery worker 用——worker 在 compose 里被整条换掉、走不到这里；且 CMD 的 exec 形式不展开
`${...}`）。entrypoint 按「`$1` 以 `-` 开头就追加、否则整条替换」的通行写法：

- `docker compose run --rm app --workers 4`（追加）
- `docker compose run --rm app python manage.py migrate`（换整条）
- worker 的 `entrypoint: ["/bin/sh","-c"]` + `command:`（`exec celery ...`）

**gunicorn 可调参数在 `env/gunicorn.env`**（app 用 `env_file: [env/app.env, env/gunicorn.env]`；
worker 只有 `env/app.env` + `env/celery.env`，**拿不到**这些旋钮）：`GUNICORN_WORKERS` /
`GUNICORN_TIMEOUT` / `GUNICORN_GRACEFUL_TIMEOUT` / `GUNICORN_KEEP_ALIVE` /
`GUNICORN_MAX_REQUESTS` / `GUNICORN_MAX_REQUESTS_JITTER` / `GUNICORN_LOG_LEVEL`（空值/未设置
取默认，写 `0` 就是 0）；**默认值只在 entrypoint 写一份**。改 env 文件后
`docker compose up -d app` 生效、不必重建镜像；**改 `entrypoint/` 或任何源码必须重建镜像**，
而且 `up -d --build` 这**一条**命令**不会**让容器换镜像（技能 `docker-compose-behavior` 第 3 节）。

`--bind` 与 `--worker-class` **写死、不做成变量**：`--bind` 与 nginx 的 upstream 耦合
（改地址必须同步 nginx），gunicorn 默认 `127.0.0.1:8000` 一旦漏掉就是 502，且它是 **append**
语义（追加只会多一个监听）。给变量等于给一个必然配错的旋钮。
celery 侧只有一个 `CELERY_LOGLEVEL`——`--concurrency` 刻意不暴露（同设备并发会写坏数据，
见 [`ingest.md`](ingest.md)「并发」）。

## 启动四步（entrypoint）

1. 静态成品复制进命名卷；
2. 拼出整条 gunicorn 命令；
3. **按需迁移** `migrate_if_needed`：只在**确实有未应用迁移**时才 `migrate --noinput`
   （依据 `MigrationExecutor.migration_plan(loader.graph.leaf_nodes())`），已是最新就打印一行
   跳过。**并发由数据库命名锁（PG advisory / MySQL `GET_LOCK`）串行化**，多副本同时启动不会
   互相竞争——为什么必须自己加锁、PgBouncer transaction pooling 的禁忌：技能
   `django-drf-gotchas` 第 2 节。开关 `env/app.env` 的 `MIGRATE_ON_START`（默认 1；设 0 交给
   外部流水线或人工）；迁移失败 `set -e` 直接退出，**不会**带着过期表结构起 gunicorn；
4. **零配置建管理员** `ensure_superuser`：不占环境变量、不进 compose、不用 secret（进了环境
   变量就会出现在 `docker inspect` / `/proc/1/environ` 里）。判定只看数据库：**一个超管都没有**
   时才建 `admin`，随机密码打印在启动日志（`docker compose logs app`）。四条边界：① 已有超管
   → 只跳过；② 同名但不是超管 → 只警告、**不自动提权**、也不改密码；③ 人工用法
   `--username ops --password '...'`、`--update-password`；④ 首次登录不需要预建 Token。

## 健康检查

四个容器都有健康检查（细节与实测：技能 `container-healthchecks`）：

| 服务 | 探针 | 不能省的参数 |
|------|------|--------------|
| app | 8000 的 TCP（`socket.create_connection`） | — |
| db | `pg_isready -U "$$(cat /run/secrets/postgres_user)"` | **`-U` 不能省**：healthcheck 由 docker 以镜像默认用户 root 执行，不带 `-U` 会刷 `role "root" does not exist` 而容器照样 healthy |
| nginx | `curl -fsS -m 3 --noproxy '*' -o /dev/null http://127.0.0.1/` | **`--noproxy '*'` 不能省**；别用 busybox `wget`（不认 `no_proxy`）；`-f` 让 4xx/5xx 也算失败 |
| worker | `celery -A netops inspect ping -d "celery@$$HOSTNAME" --timeout 5` | **必须 `-d` 限定自己**：走 broker，同时验证「进程活着」+「连得上 Redis」 |

worker 的 `depends_on: app: service_healthy` 是为了**等迁移跑完**；nginx 探 80 还能发现
「conf.d 没挂进来」（没有 server 块 nginx 照样启动）。

## 环境变量与凭据

按「谁读」分三处（完整表格见 `env/README.md`）：根 `.env` 只给 compose 插值；`env/*.env`
按服务 `env_file` 注入；`env/secrets/*` 只读挂载给凭据。三条规则：**compose 的 `${VAR}` 只读
根 `.env`**、`environment:` 优先于 `env_file`、多个 `env_file` **后面的覆盖前面的**。

一个坑：worker 的 `--loglevel` 要读 `env/celery.env`，而 compose 会对自己的文件做 `${...}`
替换（读不到那些文件），所以那里写 `$${CELERY_LOGLEVEL:-info}`——`$$` 到容器里才是 `$`，
由 `sh -c` 展开。

**数据库凭据走 docker secrets，不进 `.env` / 环境变量**（为什么不用环境变量：技能
`container-healthchecks` 第 5 节）：`env/secrets/postgres_user` / `postgres_password` 由 compose
顶层 `secrets:` 只读挂到 `/run/secrets/*`；`env/db.env` 与 `env/app.env` 里只写
`POSTGRES_USER_FILE` / `POSTGRES_PASSWORD_FILE`（db 由 postgres 官方镜像读，app / worker 由
`settings/base.py` 的 `_env_or_file()` 读，没有 `*_FILE` 时回退同名环境变量）。**两条别改回去**：

1. postgres 官方 entrypoint 规定 `POSTGRES_USER` 与 `POSTGRES_USER_FILE` 同时设置就报错退出，
   所以只留 `_FILE`；
2. db 的 healthcheck 靠容器内 `sh` 读 secret，**`-U` 必须显式给**。

生成 / 迁移：`bash env/secrets/generate.sh`（默认**沿用旧值**；postgres 只在**首次初始化数据卷**
时应用凭据，换值不改库里已有密码——详见 `env/secrets/README.md`）。密钥不入库（`.gitignore`）、
不进构建上下文（`.dockerignore`）；redis 密码仍是环境变量（官方镜像没有 `*_FILE` 机制）。

## 镜像

`pyproject.toml` / `uv.lock` 变了必须重建 `Dockerfile.base`，否则运行期才报
`ModuleNotFoundError`；换源要用 uv 自己的变量、且必须重新 `uv lock`——见技能
`uv-package-and-lockfile`。

**基础镜像本身可换**：`Dockerfile.app` 用 `ARG BASE_IMAGE=network-ops-base:py312` +
`FROM ${BASE_IMAGE}`（`FROM` 里只能用 `ARG`），compose 用 `x-app-build` 锚点给 app 与 worker
传同一个 build arg（`${BASE_IMAGE:-network-ops-base:py312}`，一处定义不会漂移），所以换私有
registry / Python 版本只需 `BASE_IMAGE=registry.example.com/netops-base:py312 docker compose
build app worker`。
