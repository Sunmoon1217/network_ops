# 容器化说明（构建手册）

> 这份文档只讲**怎么构建、每个镜像层为什么这么写、哪些改动会踩坑**——也就是原先散在
> `Dockerfile.base` / `Dockerfile.app` / `docker-compose.yml` 注释里的内容。
>
> 别处的既有说明（**不在这里复述**）：
> `AGENTS.md`「关键约定」= 项目自身的挂载点语义 / 静态卷 / env 分工 / healthcheck / gunicorn 旋钮 / 启动流程；
> `env/README.md`、`env/secrets/README.md` = 变量与密钥；`nginx/README.md` = 反向代理；
> 第三方软件的实测行为 = 技能（见 §6）。

## 1. 三个文件的职责

| 文件 | 职责 | 变它意味着 |
|------|------|-----------|
| `Dockerfile.base` | 环境镜像：Python 运行时 + 依赖，**不含项目代码** | 重建一次、长期复用；`pyproject.toml` / `uv.lock` 变了必须重建 |
| `Dockerfile.app` | 项目镜像：`FROM ${BASE_IMAGE}` + 源码 + **宿主机构建好的静态成品** | 每次改源码 / 入口脚本都要重建 |
| `docker-compose.yml` | db / redis / app / worker / nginx 的编排 | 只改 env 文件的话不必重建镜像 |

## 2. 构建顺序与命令

```bash
# ① 基础镜像（改了 pyproject.toml / uv.lock 就要重跑）
docker build --network=host -f Dockerfile.base -t network-ops-base:py312 .

# ② 静态成品：必须在**宿主机**做，镜像里不跑 pnpm / collectstatic
cd frontend && pnpm build && cd ..
uv run python manage.py collectstatic --noinput

# ③ 项目镜像
docker build -f Dockerfile.app -t network-ops:latest .
#    换基础镜像（app 与 worker 一起，用同一个 build arg）：
BASE_IMAGE=registry.example.com/netops-base:py312 docker compose build app worker

# ④ 换容器（构建与替换是两步，见 AGENTS.md / 技能 docker-compose-behavior 第 3 节）
docker compose up -d app worker
```

- `--network=host`：构建容器默认走 Docker 自己的网络栈（`daemon.json` 的 `proxies` 只作用于拉基础镜像）。受限网络下拉 APK / PyPI 慢就加它；**加了就别再传** `--build-arg http_proxy=...`——此时容器不再有 `172.17.0.1` 这个网关，代理地址要换成宿主真实地址。
- 三条命令都不带 `--build`：`docker compose up -d --build` 只构建、**不换容器**（坑与正确做法：技能 `docker-compose-behavior` 第 3 节）。

## 3. `Dockerfile.base`（环境镜像）

### 3.1 分层与取舍

| 写法 | 为什么 |
|------|--------|
| 只 `COPY pyproject.toml uv.lock` | 源码改动不破坏依赖层缓存（源码在 `Dockerfile.app` 才进来） |
| uv 用 `--mount=from=ghcr.io/astral-sh/uv:0.12` 临时挂载 | uv 只在构建期存在、**不落进镜像**——镜像里没有任何包管理器（要装包就再临时挂一次） |
| `ENV VIRTUAL_ENV=/opt/venv` | venv 独立于 `/app`，项目代码被覆盖时不影响它 |
| `ENV UV_PYTHON_DOWNLOADS=never` | 只用镜像内的解释器，禁止 uv 联网下载 Python |
| `rm -rf .../site-packages /usr/local/bin/pip*` | 删掉基础镜像自带的系统 pip（约 7MB），依赖都在 `/opt/venv`。⚠️ 换 Python 版本要同步改这个路径 |
| 不装 `gcc` / `musl-dev` | `psycopg2-binary`、`cffi` 都有 `cp312 musllinux` 轮子。真开始编轮子了再加，别预先装 |
| `libpq` 与 `git` 分成两个 `RUN` | git 带十来个 APK 依赖、受限网络下更容易超时；分开后成功那层可复用，重跑只补 git |
| 运行期必须有 `git` 可执行文件 | `apps/ingest/config_repo.py` 用 GitPython（底层是 git CLI）操作配置仓库 |

### 3.2 `uv sync` 的参数

`uv sync --frozen --no-dev --no-install-project --active --no-cache`，一层到底（装完即清理）：

| 参数 | 含义 |
|------|------|
| `--frozen` | 严格按 `uv.lock` 装，不重新解析 |
| `--no-dev` | 不装 dev 组（pytest / ruff） |
| `--no-install-project` | 不装项目自身——源码这时还没 COPY 进来 |
| `--active` | 装进 `VIRTUAL_ENV`（`/opt/venv`），而不是另建 `.venv` |
| `--no-cache` | 不读也不写缓存，层里不留 `~/.cache/uv` |

### 3.3 冒烟自检（**契约：与 `dependencies` 对齐**）

```dockerfile
RUN python -c "import importlib.metadata as m; [__import__(n) for n in (...)]; print('deps ok:', {...})"
```

- **清单必须与 `pyproject.toml` 的 `dependencies` 一致**：漏检的包会让这里"看起来构建成功"，到 `Dockerfile.app` 运行期（甚至只在某个功能被调用时）才 `ModuleNotFoundError`。**加依赖要改两处**。
- 版本号只能走 `importlib.metadata`——`ttp` 这类包没有 `__version__`。

### 3.4 镜像源

- `APK_MIRROR`：`sed` 替换 `/etc/apk/repositories`。
- `UV_DEFAULT_INDEX`：⚠️ Python 包**只能**用 uv 自己的变量（uv 不读 `pip.conf` / `PIP_*`）；且 `uv.lock` 固化了 registry 与 wheel URL → **换源后必须 `uv lock` 重解析**。细节与实测：技能 `uv-package-and-lockfile`。

### 3.5 刻意不定义 `CMD` / `ENTRYPOINT`

本镜像只有环境、单独 `docker run` 跑不起来。一旦写了会被项目镜像**继承**，等于把 gunicorn 参数钉回镜像、`env/gunicorn.env` 的 `GUNICORN_*` 就调不动了（命令整条在 `docker/entrypoint.sh` 里拼）。

## 4. `Dockerfile.app`（项目镜像）

### 4.1 构建前置（镜像里不做）

`frontend/dist`（`pnpm build`）与 `www`（`collectstatic`）必须是宿主机构建好的成品——镜像里没有 node，也不该在构建期跑 Django。下面的 `RUN` 会**校验**这两个目录，缺了直接构建失败并打印要执行的命令（比构建成功、运行起来才 404 好）。

### 4.2 `COPY` 范围

| 复制 | 不复制 |
|------|--------|
| `manage.py`、`pyproject.toml`、`uv.lock`、`netops/`、`apps/` | `tests/`（它依赖 dev 组的 pytest，镜像里没装） |
| `frontend/dist`、`www`（靠 `.dockerignore` 放开） | `data/`、`.dsh/`、`frontend/src` 等（`data/*` 与 `.dsh/` 已在 `.dockerignore` 里忽略） |

`frontend/dist` 与 `www` 是 `.dockerignore` 里**唯一被显式放开**的构建产物目录——改 `.dockerignore` 时别顺手加通配把这两个也忽略掉。

### 4.3 `mkdir -p` 的三个挂载点

`/app/data/config_repo`（命名卷 `config_repo_data`）、`/app/data/configs`（只读 bind）、`/var/lib/netops-static`（命名卷 `static_data`）。

- 都**建成空目录**：命名卷首次创建时属主 / 布局继承自镜像目录（技能 `docker-mounts-and-ownership`），挂载点必须存在、且存在与否可预期。
- `data/configs` 那侧是 `create_host_path: false`，宿主机目录得先 `mkdir -p data/configs`（语义与沿革：`AGENTS.md`「配置仓库是命名卷、配置源目录是只读 bind」）。

### 4.4 git 提交身份

`git config --system user.name / user.email`：容器主机名没有域名段，git 自己推断不出邮箱、**root 也提交不了**，而配置仓库每次导入都要 commit。原因与复现：技能 `git-in-containers`。

### 4.5 刻意**不放** `safe.directory`（⚠️ 改回去时必须加回）

现在配置仓库是命名卷 + root，仓库属主与进程用户一致，用不到 `safe.directory`。**一旦**改回 bind、或给容器加 `user:`（uid 与卷不符），必须补回**镜像层**的：

```dockerfile
RUN git config --system --add safe.directory '*'
```

否则 GitPython 走 git CLI 会因 `dubious ownership` 静默失败（保存配置"成功"但仓库里什么都没提交）——技能 `git-in-containers`。

### 4.6 构建期校验

`django.setup()` + `from netops.asgi import application`：只有它能发现「`INSTALLED_APPS` 里某个包没装」这类问题（依赖齐全但应用注册不上）。

### 4.7 不定义 `CMD`

基础镜像也没有。同一镜像还要当 celery worker 用，worker 在 compose 里被整条 `command` 换掉、走不到 gunicorn；且 `CMD` 的 exec 形式不展开 `${...}`。

## 5. `docker-compose.yml` 里"看不出来"的约束

- **app 不映射端口、也不写 `expose`**：容器之间能不能通只取决于进程有没有在监听；对外统一走 nginx 入口。调试用 `docker compose exec app python manage.py shell`。
- **nginx 的 resolver 脚本只挂单个文件**（`./nginx/docker-entrypoint.d/05-netops-resolver.sh`）：挂整个目录会**遮住 nginx 镜像自带**的 entrypoint 脚本。
- nginx 探活用的 `curl` 是 `nginx:alpine` **自带**的（实测 8.22.0）；换基础镜像若不带 curl，healthcheck 会直接失败（`-f` 让 4xx/5xx 也算失败，负向验证要用「空目录 / 死端口」，别用一个随便的 404 路径——SPA 有 `try_files` 兜底）。
- `static_data` 是**可丢弃**数据：入口脚本每次启动权威重铺，删了也能由重建镜像恢复。
- 卷名 `config_repo_data` **刻意不复用**旧的 `network_ops_app_data`——那里面是上个方案的另一份历史，复用等于把两份不相干的历史静默合并。旧卷不会自动删除，确认空了再 `docker volume rm network_ops_app_data`。
- **访问流的 Celery 队列与消费者**：策略展开走独立的 `access_flow` Celery 队列（`settings.CELERY_TASK_ROUTES`），由 `worker` 一并消费（command 里的 `-Q celery,access_flow` + `--concurrency=2`）。曾为它单开 `worker-access` 服务做故障域隔离，**已合并**：两条链皆低频，共享 2 个并发槽的最坏代价是秒级排队，而独占服务是 +677MB/+16 进程的常驻保费；队列本身保持独立，出现主链被饿死的实测证据时，把独占服务加回来即可。`access-flow-consumer` 是 AccessFlow 的**唯一写者**：只能跑一个实例（`scale` 起多份 = 多写者，先查后合并的前提就没了），它不挂任何卷、只连 db 与 redis；探活看 redis 里的 `access_flow:heartbeat` 键（消费循环**每轮开头**盖章、TTL 300s，healthcheck 阈值 120s；心跳必须在 `XREADGROUP` **之前**盖——读超时走进 except 分支时也得盖，否则读持续失败会让心跳停更、把活着的进程判死），光看 PID 判断不了死循环卡住。**`get_redis()` 的 `socket_timeout=10` 必须 > 消费端的 `block=5000`**：两者相等时 stream 一空，服务端恰好阻塞满 5s 才回包、客户端 5s 就断读，每轮必抛 TimeoutError（实测消费循环空转 32 次/6 分钟）。背压阈值是 `ACCESS_FLOW_MAX_QUEUE`（env/app.env 可覆盖，默认 50000）：生产者投递前查 Stream 长度，超了就 `self.retry` 让路——绝不在任务里 sleep 等待（会占死 worker 进程）。

## 6. 其余主题去哪儿看

| 主题 | 出处 |
|------|------|
| 挂载与属主、卷的播种时机 | 技能 `docker-mounts-and-ownership` |
| `${VAR}` 插值 / `$$` / `up -d --build` / 残留卷 | 技能 `docker-compose-behavior` |
| healthcheck 的执行用户、`-U`、`--noproxy '*'`、`-d`、secrets | 技能 `container-healthchecks` |
| 容器里的 git | 技能 `git-in-containers` |
| uv 换源与 lock 固化 | 技能 `uv-package-and-lockfile` |
| nginx resolver / 变量式 upstream / 静态卷布局 | 技能 `nginx-container-proxy`、`nginx/README.md` |
| 变量与密钥的生成、轮换 | `env/README.md`、`env/secrets/README.md` |
| 迁移 / 初始管理员 / gunicorn 旋钮 / 挂载点语义 | `AGENTS.md`「关键约定」 |
