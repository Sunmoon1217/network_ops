# 部署与容器化

compose 起 **db（PostgreSQL/TimescaleDB 或 MySQL，由根 `.env` 的 `DB_SERVICE` 选）/ redis /
code-init（一次性）/ app / worker / consumer / beat / nginx**，
nginx 是统一入口。本文档收「部署侧的硬要求与代价」；构建顺序、分层取舍、`uv sync` 参数、
冒烟清单契约见 `entrypoint/README.md`。第三方软件的实测行为（compose 插值、挂载属主、容器里
git、健康检查、nginx resolver、uv）在 `.dsh/skills`，本文只点名。

## 入口与静态资源（代码卷 + 静态卷）

`nginx/` 作为统一入口（80/443）：`/api/*`、`/admin/*`、`/media/*`、`/mcp` 代理到 compose 里
的 **app 容器**，`/assets/*`、`/static/*` 与两个入口 html（`/`、`/dashboard*`）由 nginx 直出。

静态成品与源码都走「镜像 → 一次性容器 → 命名卷」这一条路：

```
宿主机（pnpm build + collectstatic）
  → dockerfile.code COPY 源码到 /opt/netops/code、静态成品到 /opt/netops/http
  → code-init（entrypoint/code_init.sh）把这两份**权威**铺进 code / static 两个命名卷
  → app / worker / consumer / beat 挂 code:/app:ro 运行；nginx 只读挂 static:/usr/share/nginx/html:ro
```

**换代码镜像或改源码后必须重跑 `code-init` 再 `up -d`**：app 用的是卷里的代码，不是镜像里的
`/app`（`up -d --build` 也不会换容器，见技能 `docker-compose-behavior` 第 3 节）。

**静态卷的布局按 URL 前缀设计**：`<卷>/index.html` + `<卷>/dashboard.html` +
`<卷>/assets/*`（Vite）+ `<卷>/static/*`（collectstatic），所以 nginx **一个 root**
（`/usr/share/nginx/html`）就覆盖 `/`、`/dashboard*`、`/assets/*`、`/static/*`。
`code_init.sh` 每次 `rm -rf` 再 `cp -a`（权威重铺）——不清会留下上一版带 hash 的遗留资源；
宿主侧 `www/` 与 `frontend/dist/` 仍由各自工具清空（`collectstatic --clear` / Vite 的
`emptyOutDir`），互不干扰。为什么非要绕一层卷（跨容器只能靠卷；卷遮住镜像内容且只播种一次）：
技能 `nginx-container-proxy` 第 6 节。

**nginx 侧显式写卷、worker / consumer / beat 用 `volumes_from`**：nginx 只写
`static:/usr/share/nginx/html:ro` 才能只读、挑卷、放在自己的路径上（`volumes_from` 会把源容器
**所有**卷带过来且路径被绑死）；反过来 worker / consumer / beat 正是要**完全一致**的代码、
配置仓库与 `conf/` 路径，所以用 `volumes_from: [app:ro]`（`code` 是只读卷，不会引入多写者）。

**nginx 侧与本项目耦合的两条硬要求**：

1. 后端地址用**变量式** upstream（`set $netops_upstream "app:8000"`）并配 `resolver`，
   `resolver` 地址在启动时从 runtime 的 `/etc/resolv.conf` 推导（写死 `127.0.0.11` 换
   Podman 就 502）——做法见 `nginx/docker-entrypoint.d/05-netops-resolver.sh`；
2. conf.d 必须用 `$http_host`（含端口）透传 Host，否则后台登录 403（`$host` 会丢端口）。

这条契约由 `tests/deploy/test_reverse_proxy_config.py` 守。

### 双入口：大屏必须单独接管

Vite 打的是 `index.html`（主站，挂载点 `#app`）与 `dashboard.html`（大屏，挂载点
`#dashboard`），两者共用 `/assets/*` 里同一份 main chunk，靠页面里的挂载点决定启动哪个应用。
所以静态卷里必须有 `dashboard.html`，且两条静态链路都不能把大屏请求交给 SPA 兜底：

| 链路 | 单独处理 |
|------|---------|
| nginx 直出（`nginx/conf.d/netops.conf`） | `location = /dashboard.html` 显式返回并设 `no-cache`（入口 html 引用带 hash 的 assets，缓存会让发版不生效）；`location = /dashboard` 与 `= /dashboard/` 内部重定向回 `dashboard.html`；`location /` 的 `try_files` 仍只兜主站 `/index.html` |
| Django 托管（`netops/urls.py` + `netops/views.py`，宿主直跑 / 只暴露 443 时） | 兜底前的 `path("dashboard.html")` 与 `re_path(r"^dashboard/?$")` 交给 `views.vue_dashboard`；`vue_index` 仍只回主站 `index.html` |

漏掉任意一边，症状都是「打开大屏却是主站登录页 / 一片空白」：拿到的是 `index.html`，页面里
没有 `#dashboard`。`pnpm dev` 由 `dashboardEntryPlugin` 把 `/dashboard` 归一到
`dashboard.html`（Vite 自带的 SPA fallback 原本会改写成 `/index.html`）；两个 Dockerfile
构建时都校验两个入口齐全，`code-init` 把整份 dist 铺进静态卷。契约由
`tests/deploy/test_dashboard_entry.py` 守。

## 四个挂载：仓库卷 / 配置源 bind / 配置目录 / 代码卷

| 路径 | 形式 | 为什么 |
|------|------|--------|
| `/configs`（`CONFIG_REPO_PATH`） | **命名卷** `repo`（读写） | 解析流水线的内部工作目录，**不需要宿主可见**；属主继承自镜像、容器 root 写自己的卷，无需 uid 对齐（技能 `docker-mounts-and-ownership`） |
| `/data` | **bind** `${PWD}/data`（`driver_opts: type none, o bind`） | 运维放文件的地方（Excel「配置文件」sheet 的 `config_dir` 默认 `/data/configs`）；宿主目录不存在时 `up` 直接失败，**首次部署要先 `mkdir -p data`**；同名卷已存在时 `driver_opts` 被静默忽略，换绑定点要先 `docker volume rm network-ops-extradata` |
| `/etc/netops/conf` | **bind** `./conf`（`ro`） | 平台自身的结构化配置（`conf/links.json`）：入库、随版本走；不在 code/static 卷里，**重跑 `code-init` / recreate 都不会覆盖现场内容**；挂载点刻意避开容器内已有的 `/configs`（repo 卷）与 `/data/configs` |
| `/app`（代码） | **命名卷** `code`（`ro` 挂进 app / worker / consumer / beat） | 由 `code-init` 铺入，跨沙箱只传镜像不复制源码 |

worker / consumer / beat 用 `volumes_from: [app:ro]` 继承同一组卷（导入配置是 app 的接口）。

`config_repo` 是**每台设备一个独立仓库**（`init_repo(hostname)` 在
`<CONFIG_REPO_PATH>/<hostname>/` 下 git init + 初始 commit），`save_config` / `get_config` /
`diff_configs` / `get_history` 都按设备打开；内容未变时返回**自己**的上次提交
（`configs` 表按 `(device, hash)` 去重因此天然命中，不会拿到别的设备的 commit）。首次打开
某设备仓库时，自动把旧**共享仓库**（根 `.git`，只读兜底、不主动创建）里该设备的历史重放
进来并回写 `DeviceConfig.git_commit_hash`。

**沿革别绕回去**：它曾经是 bind，为此要「容器跑成宿主 uid + `export UID GID` +
`HOME=/tmp` + 静态卷 777 + `safe.directory` + 两处挂载点自检」，这些**已全部删除**；唯一
保留的是**镜像里的 git 提交身份**（`user.name` / `user.email`），它不是为 bind 服务的
（原因见技能 `git-in-containers`）。一旦改回 bind 或给容器加 `user:`，必须补回镜像层的
`git config --system --add safe.directory '*'`。

**代价**：宿主侧看不到这份仓库，宿主直跑 Django 用的是 `<项目根>/data/config_repo`
（另一份，dev 用）。看/清理容器那份：

```bash
docker compose exec app git -C /configs/<hostname> log --oneline
docker compose exec app python manage.py purge_configs --all --purge-repo --yes
```

卷名用新的 `repo` / `data`（不复用旧 `network_ops_app_data`，避免静默合并两份历史）；旧的
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

**gunicorn 可调参数在 `envs/gunicorn.env`**（app 用
`env_file: [envs/common.env, envs/gunicorn.env, envs/container.env]`；worker 只有
`common.env` + `celery.env` + `container.env`，**拿不到**这些旋钮）：`GUNICORN_WORKERS` /
`GUNICORN_TIMEOUT` / `GUNICORN_GRACEFUL_TIMEOUT` / `GUNICORN_KEEP_ALIVE` /
`GUNICORN_MAX_REQUESTS` / `GUNICORN_MAX_REQUESTS_JITTER` / `GUNICORN_LOG_LEVEL`（空值/未设置
取默认，写 `0` 就是 0）；**默认值只在 entrypoint 写一份**。改 env 文件后
`docker compose up -d app` 生效、不必重建镜像；**改 `entrypoint/`、任何源码或依赖必须重建
venv / code 镜像并重跑 `code-init`**（技能 `docker-compose-behavior` 第 3 节）。

`--bind` 与 `--worker-class` **写死、不做成变量**：`--bind` 与 nginx 的 upstream 耦合
（改地址必须同步 nginx），gunicorn 默认 `127.0.0.1:8000` 一旦漏掉就是 502，且它是 **append**
语义（追加只会多一个监听）。给变量等于给一个必然配错的旋钮。
celery 侧只有一个 `CELERY_LOGLEVEL`——`--concurrency` 刻意不暴露（同设备并发会写坏数据，
见 [`ingest.md`](ingest.md)「并发」）。

**beat 的启动钩子**（`entrypoint/beat.sh`，`scripts/deploy-host.sh` 的 `cmd_beat` 同构）：

1. `python manage.py refresh_link_cache` —— **同步**刷一次链路缓存（失败只警告、不阻塞启动）；
2. `python manage.py collect_dashboard` —— **投递**一次设备组 + Autotask 采集（异步，worker 消费）。
   为什么必须补这一次：Celery 的 interval 条目在**首次加入时**把 `last_run_at` 记为「加入时刻」
   （`celery.beat.Entry`），第一次发送要等满一个周期。Autotask 默认 600s，不补投的话 beat 起来
   后前 10 分钟大屏没有工单 / SLB / 巡检数据——这不是调度没生效。
3. `manage.py shell -c "...print(app.conf.beat_schedule)"` 打印**生效调度**（条目名 / 任务 / 周期）。
   日志里「没有某条任务」时先看这一行：条目不在 = beat 读到的代码还是旧的（code 卷没重铺或容器
   没重启），不是调度写错。
4. `exec celery -A netops beat --schedule=/tmp/celerybeat-schedule --pidfile=/tmp/celerybeat.pid`。

`/app` 是只读 code 卷，celery 默认往 cwd 写 schedule 会直接 EROFS；beat **单实例**，
不能 scale（会重复调度）。**换代码后只重启 `beat` 不够**：code 卷没重铺时它读到的还是旧
settings，必须先 `docker compose up -d code-init` 再重启 `beat`。

两条启动路径（`entrypoint/beat.sh` 与 `scripts/deploy-host.sh` 的 `cmd_beat`）必须同构，
由 `tests/deploy/test_beat_startup_hooks.py` 对账：同步刷链路缓存 → 补投两个采集源 →
打印生效调度 → `exec celery beat`，且每步都有 `|| echo` 兜底（`set -e` 下失败不阻塞启动）。
漏掉补投会让大屏空 10 分钟，而调度条目测试全绿——这类脚本级回归只有这条契约能拦住。

## 启动三步（`entrypoint/app.sh`）

1. 拼出整条 gunicorn 命令（静态成品已由 `code-init` 铺进静态卷，这里不再复制）；
2. **按需迁移** `migrate_if_needed`：只在**确实有未应用迁移**时才 `migrate --noinput`
   （依据 `MigrationExecutor.migration_plan(loader.graph.leaf_nodes())`），已是最新就打印一行
   跳过。**并发由数据库命名锁（PG advisory / MySQL `GET_LOCK`）串行化**，多副本同时启动不会
   互相竞争——为什么必须自己加锁、PgBouncer transaction pooling 的禁忌：技能
   `django-drf-gotchas` 第 2 节。开关 `envs/container.env` 的 `MIGRATE_ON_START`（默认 1；设 0
   交给外部流水线或人工）；迁移失败 `set -e` 直接退出，**不会**带着过期表结构起 gunicorn；
3. **零配置建管理员** `ensure_superuser`：不占环境变量、不进 compose、不用 secret（进了环境
   变量就会出现在 `docker inspect` / `/proc/1/environ` 里）。判定只看数据库：**一个超管都没有**
   时才建 `admin`，随机密码打印在启动日志（`docker compose logs app`）。四条边界：① 已有超管
   → 只跳过；② 同名但不是超管 → 只警告、**不自动提权**、也不改密码；③ 人工用法
   `--username ops --password '...'`、`--update-password`；④ 首次登录不需要预建 Token。

## 健康检查

compose 只给 **db / redis / nginx** 配了 healthcheck，app / worker / consumer / beat 没有
（`depends_on` 用 `service_started`，由 `restart: unless-stopped` 兜底；consumer 的判活依据是
Redis 里的 `access_flow:heartbeat` 键，TTL 300s；beat 额外等 `redis: service_healthy`，
因为启动即刷缓存需要 Redis 就绪）。细节与实测：技能 `container-healthchecks`。

| 服务 | 探针 | 不能省的参数 |
|------|------|--------------|
| db | `pg_isready -U "$$(cat /run/secrets/db_user)" -d "$${DB_NAME:-netops}"` | **`-U` 不能省**：healthcheck 由 docker 以镜像默认用户 root 执行，不带 `-U` 会刷 `role "root" does not exist` 而容器照样 healthy |
| redis | `redis-cli ping` | — |
| nginx | `curl -fsS -m 3 --noproxy '*' -o /dev/null http://127.0.0.1/` | **`--noproxy '*'` 不能省**；别用 busybox `wget`（不认 `no_proxy`）；`-f` 让 4xx/5xx 也算失败；探 80 还能发现「conf.d 没挂进来」（没有 server 块 nginx 照样启动） |

app 的 `depends_on: code-init: service_completed_successfully` 是为了**等代码卷铺完**；
worker / consumer 只是 `app: service_started`；beat 等 `code-init` 完成 + `redis: service_healthy`。

## 环境变量与凭据

按「谁读」分三处（完整表格见 `envs/README.md`）：根 `.env` 只给 compose 插值；`envs/*.env`
按服务 `env_file` 注入（容器）；`envs/secrets/*` 只读挂载给凭据。三条规则：**compose 的
`${VAR}` 只读根 `.env`**、`environment:` 优先于 `env_file`、多个 `env_file` **后面的覆盖前面
的**（所以 `container.env` 排最后，容器差异一定生效）。宿主直跑读同一份 `common.env` +
`host.env`，由 `base.py` 的 `load_dotenv` 兜底（见 [`settings.md`](settings.md)）。
链路配置路径 `DASHBOARD_LINKS_FILE` 写在 `envs/container.env`（`/etc/netops/conf/links.json`），
宿主直跑用默认的 `conf/links.json`（相对 `BASE_DIR`）。

命令已在 `entrypoint/*.sh` 里拼好，compose 里没有需要 `$$` 转义的 shell 字符串；`$$` 只出现在
healthcheck 的 `CMD-SHELL` 里（要留给容器内的 `sh` 展开）。

**数据库与阿里云凭据走 docker secrets，不进 `.env` / 环境变量**（为什么不用环境变量：技能
`container-healthchecks` 第 5 节）：`envs/secrets/db_user` / `db_password` /
`aliyun_{prod,test}_access_key_{id,secret}` 由 compose 顶层 `secrets:` 只读挂到 `/run/secrets/*`。
数据库连接参数集中在 **`envs/db.env`** 一份文件里，compose 直接用 `env_file` 加载它：

- 文件里先定义一套 `DB_*`（引擎、库名、用户、`DB_HOST=db`、凭据文件路径），再用 `${}` **在同一个
  文件内嵌套**出各镜像认的名字：`POSTGRES_DB=${DB_NAME}`、`MYSQL_DATABASE=${DB_NAME}`、
  `POSTGRES_USER_FILE=${DB_USER_FILE}`、`MYSQL_PASSWORD_FILE=${DB_PASSWORD_FILE}` 等。
  这是 **env_file 自身的插值**（Compose 加载时展开），右侧引用的 `DB_SERVICE` / `DB_NAME` /
  `DB_USER` 来自根 `.env`，所以后端与库名仍然只在根 `.env` 维护一份；
- 四个应用进程与 db 容器都 `env_file: envs/db.env`：应用只认 `DB_*`（settings 的 `_env_or_file()`
  读 `*_FILE`），db 镜像各取自己那份 `POSTGRES_*` / `MYSQL_*`，对方的变量被忽略；
- `envs/container.env` 不再放数据库连接（它同时注入四个应用进程，放这里对 db 容器毫无意义）。

**两条别改回去**：

1. postgres 官方 entrypoint 规定 `POSTGRES_USER` 与 `POSTGRES_USER_FILE` 同时设置就报错退出，
   所以 `envs/db.env` 里只给 `_FILE`；
2. db 的 healthcheck 靠容器内 `sh` 读 secret，**`-U` 必须显式给**。

生成 / 迁移：`bash envs/secrets/generate.sh`（默认**沿用旧值**；postgres 只在**首次初始化数据卷**
时应用凭据，换值不改库里已有密码——详见 `envs/secrets/README.md`）。密钥不入库（`.gitignore`）、
不进构建上下文（`.dockerignore`）；redis 密码仍是环境变量（官方镜像没有 `*_FILE` 机制）。

## MySQL 后端（可选部署形态）

默认仍是 PostgreSQL（TimescaleDB 镜像）。换后端只改根 `.env` 一行，不用改 compose、也不用多带 `-f`：

```dotenv
DB_SERVICE=mysql          # postgresql（默认）/ mysql
```

`compose.yml` 里的 `db` 服务用 **`extends`** 引入 `compose.db.yml` 的同名模板：

```yaml
db:
  extends:
    file: compose.db.yml
    service: ${DB_SERVICE:-postgresql}
```

模板文件里只有 `postgresql` / `mysql` 两份**服务定义**，不是两个服务——最终模型里 `db` 只有一个，
`up -d` 不会把两个库都起起来。四个应用进程的 `DB_ENGINE` 由 `x-db-env` 锚点跟随同一个
`${DB_SERVICE}` 注入，所以容器里不需要另改 `envs/common.env`（宿主直跑才读它）。

三条硬约束（都是 `extends` 的语义，实测过）：

1. **`compose.db.yml` 不能再用 `-f` 传**——一旦当 `-f` 传，两个模板会变成真实服务，两个库都会起；
2. 顶层 `volumes:` / `secrets:` **不继承**，`compose.yml` 里必须声明两套卷（未引用的不会被创建）；
3. `depends_on` / `links` / `volumes_from` **不继承**，模板里不要写。

官方 mysql 镜像**没有 `MYSQL_USER_FILE`**：用户名走 `MYSQL_USER`（不是秘密），密码走
`envs/secrets/db_password`（root 复用同一份，不新增轮换流程）。两个后端共用
`envs/secrets/db_user` / `db_password`。

**不能复用 PG 的数据卷**：换后端等于换一套库（`network-ops-pgdata` ↔ `network-ops-mysqldata`），
数据不会互通。

跨库差异（2026-11 在 MySQL 8.4.13 上实测，`-n auto` 全量 769 项通过）：

| 项 | PostgreSQL | MySQL | 处理 |
|----|-----------|-------|------|
| `AccessFlow.device_ids` / `policy_ids` 的索引 | `GinIndex` | JSON 列不能直接建索引（3152） | 建表不带索引，按后端补建（`operator.0002`）：PG 用 `CREATE INDEX ... USING gin`，MySQL 8.0.17+ 用多值索引 `((CAST(col AS UNSIGNED ARRAY)))`。20 万行实测：MySQL 全表扫描 160 ms → 1.3 ms，写入约 +50%；PG 顺序扫描 47 ms → GIN 1.5 ms |
| `Service` 五列自然键 | 3108 字节没问题 | 超 InnoDB 3072 字节上限（1071） | 按后端分建：PG 普通唯一约束，MySQL 函数唯一索引 `(device_id, MD5(CONCAT_WS(...)))`（`assets.0029`） |
| 大小写 | 唯一键与 `exact` 区分大小写 | `utf8mb4_0900_ai_ci` 不区分 | 已知差异：普通唯一键会把 `SW-01` / `sw-01` 判重；上面那个函数索引按字节哈希，仍区分 |
| DDL 回滚 | 迁移失败可回滚 | DDL 隐式提交，回滚不了 | 迁移失败会留半套 schema；MySQL 部署以「删库重建」为恢复手段，见下 |
| `bulk_create` 取主键 | 支持 `RETURNING` | 不支持 | 代码本来就不用返回值，无影响 |

MySQL 侧要求 **8.0.17+**（多值索引；函数索引只要 8.0.13，Django 6.1 的下限是 8.0.11）。迁移失败（MySQL 上不可回滚）
的处理：停止 app → `DROP DATABASE netops` → 重建空库 → 重跑 `migrate_if_needed`；MySQL 只面向
新部署，不接受从 PG 迁移数据。

## 镜像

`pyproject.toml` / `uv.lock` 变了必须重建 `dockerfile.venv`（不是 base），否则运行期才报
`ModuleNotFoundError`；换源要用 uv 自己的变量、且必须重新 `uv lock`——见技能
`uv-package-and-lockfile`。

**分层与重建时机**：`dockerfile.base`（OS：git / libpq5，不含 Python 依赖）→
`dockerfile.venv`（`uv sync --frozen --no-dev --no-install-project`）→ `dockerfile.code`
（busybox + 源码 + 静态成品，跨沙箱传输用）/ `dockerfile`（传统项目镜像，备选）。换 Python 版本
或系统包才重建 base；只改依赖就只重建 venv；改源码 / 入口脚本要重建 code 镜像并重跑
`code-init`。compose 的 app / worker / consumer 共用 `VENV_IMAGE`（根 `.env`，`x-app-base` 锚点
保证不漂移），`code-init` 用 `CODE_IMAGE`（git SHA 做 tag 便于回滚）；换私有 registry 只改这两个
镜像变量，不必改 compose。
