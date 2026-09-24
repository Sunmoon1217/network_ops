# AGENTS.md

## 项目概述

网络运维管理平台：Django REST 后端 + Vue 3 前端。

后端提供数据模型与 REST API，负责设备配置的解析与入库。前端构建产物默认可由 Django 直接托管（便于开发调试）；生产/集成环境使用 `docker compose` 起 db / redis / app / worker / nginx，由 `nginx/` 作为统一入口（静态资源直出，`/api` 反向代理到 app 容器）。

## 项目结构

```
network_ops/
├── manage.py            # Django 入口
├── main.py
├── netops/              # 项目配置
│   ├── settings/        # env 动态项在 base 只写一遍；环境文件只放硬差异与守卫
│   │   ├── __init__.py  # 白名单分发（DJANGO_ENV，未知即拒）+ 助手导出 + apps/ 进 sys.path
│   │   ├── base.py      # 全部 env 动态配置（*_FILE > env > 默认 链）+ 静态（_env_list/_env_or_file）
│   │   ├── dev.py       # 空壳：base 即 dev 语义 ← 不设 DJANGO_ENV 的默认
│   │   ├── container.py # 守卫：POSTGRES_HOST / REDIS_HOST 必须由 env/app.env 注入
│   │   └── prod.py      # DEBUG=False 硬覆盖 + 5 个关键 env 必填守卫（fail loud）
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
│   ├── ingest/             # 数据采集与解析入库（配置管道：Git 仓库 → TTP 解析 → Saver 写库）
│   │   ├── api/{configs.py, parsers.py, urls.py}
│   │   ├── mapping.py        # 解析产出归一（键/字段别名）+ Saver→模型关联声明
│   │   ├── parsers/{factory.py, template_keys.py, contract.py} + tmpls/{configs,running}/
│   │   ├── savers/{base,registry,interface,lb,firewall,routing}.py
│   │   ├── config_owner.py      # 配置属主解析（堆叠组备机归属主设备）
│   │   ├── config_repo.py       # Git 配置仓库管理
│   │   ├── signals.py           # DeviceConfig 保存后触发解析与入库（薄壳，实现见 pipeline.py）
│   │   ├── pipeline.py          # 配置处理流水线：读 Git → 解析 → 分发 Saver
│   │   ├── workflow.py          # 任务工作流入口：start_task / dispatch_stage / cancel_task / submit_config_job
│   │   ├── management/commands/reparse.py  # 重跑已入库配置的解析与入库
│   │   ├── management/commands/purge_configs.py  # 清理配置解析产物（默认 dry-run，含 analysis 的缓存）
│   │   └── ansible/             # ⚠️ 仅剩 __pycache__，源文件已移除
│   └── analysis/        # 分析域（只读消费 ingest 与 assets，不许被它们反向依赖）
│       ├── api/{trace.py, analysis.py, urls.py}   # /api/trace/*、/api/internet-analysis/*（URL 前缀沿用拆分前）
│       ├── path_tracer.py       # 路径追踪算法（模拟报文逐跳转发）
│       ├── models.py            # InternetAnalysis（分析结果缓存）
│       └── migrations/0001_initial.py  # 从 operator 迁入：state 删除 + RunSQL RENAME，数据随表走
├── data/                 # 运行期数据（不入库）：configs 是 bind 进 app 的输入，config_repo 只是宿主机直跑用的那份
│   ├── config_repo/     # 宿主机直跑时的 Git 配置仓库；**Docker 部署用的是命名卷 config_repo_data**，两者互不影响
│   └── configs/         # Excel「配置文件」sheet 的 config_dir 源目录；→ app 的 /app/data/configs（只读 bind）
├── .dsh/skills/         # 跨会话知识库的**入口软链**（已被 .gitignore/.dockerignore 忽略）：
│                        # 真身在用户级 `~/.dsh/skills`（独立 git 仓库），那里放第三方软件的实测行为，
│                        # 目录清单自动进每个会话、正文按需加载（skill 工具或 /name）。见「知识库」一节
├── tests/               # 测试（按应用分目录，pytest testpaths 指向此处）
│   ├── analysis/        # 资产分析 / 缓存 / 导出 / 路由采集
│   ├── assets/          # device_group / serializer_migration / service_unique
│   ├── core/            # 认证（登录 CSRF / 注册 / 任务接口）与部署契约
│   ├── deploy/          # 反向代理与 Django 的接口契约（nginx Host 透传 / CSRF 可信来源）
│   └── ingest/             # parsers / parser_contract / pipeline / reparse / saver / workflow
├── frontend/            # Vue 3 + TypeScript + Vite
│   ├── dist/            # 构建产物（不入库，由 nginx 直接托管）
│   └── src/{api,assets,components,composables,constants,layout,router,stores,types,utils,views}
├── nginx/               # 反向代理（静态直出 + API 代理）
│   ├── conf.d/          # netops.conf(80)、netops-ssl.conf.disabled(443)
│   ├── docker-entrypoint.d/  # 05-netops-resolver.sh：启动时把 runtime 的 DNS 写成 resolver.conf
│   ├── ssl/             # TLS 证书（不入库）
│   └── gen-self-signed-cert.sh
├── www/                 # collectstatic 产物（不入库，镜像构建时 COPY 进 app）
├── env/                 # 给容器的配置：按服务分的 env 文件（app/db/gunicorn/celery.env）+ secrets/（密钥，不入库）
├── tmp/
├── docker/
│   ├── entrypoint.sh    # 应用容器入口：静态成品复制进命名卷 → 按需迁移 → 零配置建管理员 → 拼出整条 gunicorn 命令启动
│   └── README.md        # **容器化构建手册**：构建顺序与命令、两个镜像的分层取舍、`uv sync` 参数、冒烟清单
│                        # 契约、compose 里"看不出来"的约束（本文档只放指针，三个指令文件头部也只留一行）
├── Dockerfile.base      # 环境镜像（只装依赖，不含源码）
├── Dockerfile.app       # 项目镜像（源码 + 宿主机构建好的静态成品）
├── .dockerignore
├── docker-compose.yml   # db(TimescaleDB) / redis / app / worker / nginx
├── .env.example         # **compose 自己**的变量模板（宿主端口 / 镜像 / secrets 路径）：cp 成 .env
├── pyproject.toml       # Python 依赖、pytest、ruff 配置
└── uv.lock
```

## 知识库（跨会话共享的实测结论）

第三方软件（Docker / docker compose、容器里的 git / GitPython、Django / DRF、nginx、容器健康检查与凭据）的**实测行为**不写在本文档里，而是**用户级技能**（全局目录、跨项目）：

- 事实源：**`~/.dsh/skills/<name>/SKILL.md`**（它自身是一个 git 仓库，要跨机器/跨人共享就 push + clone 它；`~/.dsh/skills/_about/README.md` 记着同一套规矩）
- 本项目的 `.dsh/skills/<name>` 只是**软链**到上面那个目录（方便在项目树里直接看到），并且 `.dsh/` 同时写在 `.gitignore` 与 `.dockerignore` 里——所以它**不入库、不进镜像**，换机器 clone 也不会留下断链

| 技能 | 覆盖 |
|------|------|
| `docker-compose-behavior` | 插值只读根 `.env`、`$$` 转义与 config 再转义、`up -d --build` 不换容器、`run/exec` 与 entrypoint 的 `$1` 约定、`down -v` 与残留卷、driver_opts |
| `docker-mounts-and-ownership` | bind vs 命名卷的属主/权限、dockerd 建源目录、镜像里 chmod 是死代码、uid 映射与宿主属主（root 或宿主 uid）、`:ro` 的 EROFS |
| `git-in-containers` | 提交身份（**root 也一样失败**）、dubious ownership 与 `safe.directory`、`getpwuid` KeyError |
| `django-drf-gotchas` | `SessionAuthentication` 自己调 `enforce_csrf()`、迁移命名锁、`Path` 按 CWD 解析、pytest 资源定位 |
| `container-healthchecks` | healthcheck 的执行用户、`pg_isready -U`、`celery inspect -d`、`--noproxy '*'`、secrets vs 环境变量 |
| `nginx-container-proxy` | `resolver` 推导、变量式 upstream、envsubst 静默失效、`$http_host` 与 Origin 校验 |
| `uv-package-and-lockfile` | uv 不读 pip 配置（只有 `UV_DEFAULT_INDEX` 有效）、`uv.lock` 固化 registry / wheel URL、依赖层镜像的重建时机 |
| `ttp-template-gotchas` | 模板按 **XML** 解析（注释里的尖括号会炸）、`re()` 可内联正则、**单条命中给 dict / 多条给 list**、内置 `IPV6` 不含点号 |
| `frontend-types` | 前端数据类型组织：具名类型进 `src/types/` + `import type ... from '@/types'`、barrel 撞名语义化改名、`.ts` / `.d.ts` 分工、忘 export / 复制不接线的坑 |
| `git-branch-flow` | **本仓分支模型**：feature 一律从 `develop` 切（**不从 master**）、合并只在 develop 侧、master 只整批收 develop 的发布合并；commit/merge message 用中文；含切分支→提交→合并→推送命令序列 |

**为什么放技能而不是本文档**：

- 技能**目录清单自动进每个会话**（首次请求前以 user 消息注入 name + description），正文**按需加载**（`skill` 工具或 `/name`）——不占常驻上下文；本文档是每轮都在的，塞进去等于长期付费。
- 每个技能写的是「**结论 + 证据命令 + 怎么做**」，未来可以照着重跑一遍验证，而不是二手结论。
- 扫描优先级：`<项目根>/.dsh/skills`（100）> `<项目根>/.agents/skills`（200）> `~/.dsh/skills`（400）> `~/.agents/skills`（500）。**通用**结论放全局，**本项目特有**的放 `<项目根>/.dsh/skills/`（同名覆盖全局那份）；项目特有技能的**真身也建在全局仓库**、项目侧只放软链入口（`frontend-types` 即如此），真身一律在全局仓库提交。

**写新技能的两条规矩**：

1. frontmatter 的 `description` / `whenToUse` 一律用 `>-` **折叠块标量**——值里出现半角 `: `（例如 `fatal: unable to ...`、`FATAL: role "root" ...`）会让 YAML 解析失败，**整条技能被丢弃**（只在 `skill` 工具加载时报 `unknown or no longer available` 才看得出来，目录清单里会莫名少一条）。
2. 加完用 `skill` 工具加载一次确认正文能读出来；技能是每个目录一个 `SKILL.md`（嵌套的 `**/SKILL.md` **不会**被发现）。投影/生效都不需要重启：provider 在 watch 目录，新技能当场进目录清单。
3. 改完记得在**全局那个仓库**里提交（`cd ~/.dsh/skills && git add -A && git commit`）——项目里的软链只是入口，不承载内容。

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

数据库为 **PostgreSQL**，通过进程环境变量配置（见 `netops/settings/`）：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `POSTGRES_DB` | `netops` | 数据库名（容器部署时在 `env/app.env` 与 `env/db.env` 里） |
| `POSTGRES_USER` / `POSTGRES_PASSWORD` | — | **走 docker secrets**：`env/secrets/postgres_user`、`env/secrets/postgres_password` → 容器内 `/run/secrets/*`；`settings/base.py` 的 `_env_or_file()` 读 `POSTGRES_USER_FILE` / `POSTGRES_PASSWORD_FILE`（没有 `*_FILE` 时回退同名环境变量，供宿主机直跑）。见 `env/secrets/README.md` |
| `POSTGRES_HOST` | `localhost` | 数据库主机（容器里由 `env/app.env` 给 `db`） |
| `POSTGRES_PORT` | `5432` | 数据库端口（容器内固定 5432；根 `.env` 里那个是**宿主映射**端口） |
| `DJANGO_ALLOWED_HOSTS` | `*` | 逗号分隔，映射到 `ALLOWED_HOSTS`；无域名阶段默认放开 |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | 空 | 逗号分隔，映射到 `CSRF_TRUSTED_ORIGINS`（Django 4+ 的 Origin 校验）；**正常拓扑留空即可** |

> 配置按「谁读」分三处（完整表格见 `env/README.md`）：**`.env`（根）** 只给 compose 自己插值（`cp .env.example .env`；已被 `.gitignore` 忽略）；**`env/*.env`** 按服务注入容器（`app.env` 给 app+worker、`db.env` 给 db、`gunicorn.env` 给 app、`celery.env` 给 worker）；**`env/secrets/*`** 只读挂载给凭据。Django 自己不读任何 `.env`——宿主机直跑时要 `set -a; . ./.env; set +a`，再 `export POSTGRES_HOST=localhost REDIS_HOST=localhost POSTGRES_USER=netops POSTGRES_PASSWORD=<值>`（**凭据只走环境变量**；`*_FILE` / secrets 文件机制**只在容器里使用**——链路统一在 `settings/base.py`：`*_FILE > 同名环境变量 > 默认值`，宿主不设 `_FILE` 即走环境变量层）。

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

> 本节只写**本项目自己的约定**（路径、服务、旋钮、契约）。第三方软件（Docker / docker compose、容器里的 git、Django / DRF、nginx、健康检查与凭据、uv）的**实测行为**在 `.dsh/skills`：需要时用 `skill` 工具加载对应技能，本节只在关键处点名，不复述细节。

- **settings：env 动态项在 base 只定义一遍，环境文件只放「不走环境变量的硬差异与守卫」（环境旋钮唯一 `DJANGO_ENV`，`DJANGO_SETTINGS_MODULE` 恒为 `netops.settings`）**：`netops/settings/`——`base.py` 集中全部可被环境变量影响的配置（`SECRET_KEY` / `DEBUG` / `ALLOWED_HOSTS` / `CSRF` / `DATABASES` / Redis，凭据链 `*_FILE > 同名环境变量 > 默认值`），**同一段读取逻辑写一遍、靠各环境注入不同的值区分**，不在每个环境文件里重复接线；三个环境文件只放环境变量表达不了的东西：`dev.py` **空壳**（base 即 dev 语义）、`container.py` 两条 host 必填守卫（env_file 被误删一行时**启动即拒**，而不是退到 localhost 等首个请求才 connection refused——Django 连接是惰性的）、`prod.py` `DEBUG=False` **硬覆盖**（不吃 `DJANGO_DEBUG` 后门）+ 5 个守卫（`DJANGO_SECRET_KEY`、`ALLOWED_HOSTS` 空或 `*`、`POSTGRES_HOST`、`POSTGRES_PASSWORD(_FILE)`、`REDIS_HOST`——查 `os.environ` 原始值，因为 base 的 default 会兜底，缺失即拒绝启动）。环境选择：**不设 → dev**（manage/asgi/wsgi/celery 的 setdefault、pytest 都指包）；容器由 `env/app.env` 注入 `DJANGO_ENV=container`；生产显式 `DJANGO_ENV=prod`；**白名单**：未知值（拼错如 `prd`）拒绝启动，不静默落 dev。`*_FILE` secrets **只在容器里设置**（宿主操作上不用它，链路三环境不分叉）。**防循环硬规矩**：`base.py` 与三个环境文件禁止 `from netops.settings import ...` / `from . import ...`，只允许 `from .base import ...`（反向依赖父包执行结果会在 `__init__` 半初始化时炸——BASE_DIR 那次事故的形态）。守卫与分发矩阵由 `tests/deploy/test_settings_environments.py` 守。
- **`.env` / `env/*.env` 里含 `$` 或 `#` 的值一律用单引号**：compose 会插值 `$`（`pa$word` 只剩 `pa`，要字面量得写 `$$`），`#` 前有空格即行内注释，**双引号不保护 `$`**。细节与实测：技能 `docker-compose-behavior`。
- **模型集中**：`assets` 的所有模型都在单文件 `apps/assets/models.py`，没有 models 子目录。
- **应用注册**：`core.apps.CoreConfig`、`ingest.apps.OperatorConfig`、`assets.apps.AssetsConfig`、`analysis.apps.AnalysisConfig`。
- **Celery 分阶段工作流**：采集→解析→存储三个阶段由 Celery 任务串联（`ingest/tasks.py` 的 `run_collection_stage` / `run_parsing_stage` / `run_storage_stage`），`Stage` 状态回写触发下一阶段（`ingest/signals.py`）。**入口是 `/api/tasks/`**：`ingest/workflow.py` 的 `start_task` 建 Task 并投递第一个（采集）阶段——此前 Task/Stage 只有模型与任务、没有任何创建者，整条链在产品里不可达；阶段失败或任务被取消时，信号负责收尾/停止推进。批量导入配置（`_import_configs`）走另一条链：`submit_config_job` = `run_config_parsing → run_config_storage`（用 `.si()` 保证两个任务拿到同一个 `config_id`）。broker/backend 都是 Redis（`REDIS_HOST`/`REDIS_PORT`）；**必须有 worker 消费**（否则 `.delay()` 只把消息堆在 Redis 里）——compose 的 `worker` 服务就是干这个的。**访问流（AccessFlow）是第三条链**：`PolicySaver` 保存成功后 `ingest.access_stream.request_rebuild` 投递 `ingest.rebuild_access_flows`（任务级 `acks_late` + 背压 `self.retry` + 设备锁，独立队列 `access_flow` 由 compose 的 `worker` 以 `-Q celery,access_flow --concurrency=2` 一并消费——曾有独占的 `worker-access` 服务做隔离，实测其常驻 677MB/16 进程，而两条链皆低频、共享 2 槽最坏只是秒级排队，故合并；**队列仍独立**，出现主链被饿死的实测证据再拆回独占服务）→ 展开结果 `XADD` 进 `access_flow_stream` → `manage.py access_flow_consumer`（compose 的 `access-flow-consumer`，**单写者、只能跑一个实例**）以「先合并、再摘残留」的幂等方式入库、**成功才 `XACK`**；细节见 `docker/README.md` §5 与 `ingest/policy_expand.py` 模块注释。手工补跑：`manage.py rebuild_access_flows --device <H> [--sync]`；投递总开关 `ACCESS_FLOW_DISPATCH`（测试里 conftest 统一置 False，防测试把消息发进真实 Redis）。
- **DeviceConfig 的解析入库默认仍是同步的**：走 `ingest.pipeline.run_config_pipeline`，在 `post_save` 的调用栈里跑完（见下文「配置处理流程」）。**例外是批量导入**：`_import_configs` 在 save 之前给实例挂 `_defer_pipeline`，信号据此跳过同步处理，改由 `ingest.workflow.submit_config_job` 投递 celery 链（几十行配置不该在一个请求里串行跑几十次解析+入库）。两套链路并存，别混。
- **前端托管**：`netops/views.py` 从 `frontend/dist/` 读取 `index.html` 与静态资源；`netops/urls.py` 用正则把非 `/api`、`/admin`、`/static`、`/assets`、`/media` 的请求交给 Vue 路由。
- **反向代理与容器化**：`nginx/` 作为统一入口（80/443）：`/api/*`、`/admin/*`、`/media/*` 代理到 compose 里的 **app 容器**（不再指向宿主机 Django），`/assets/*`、`/static/*` 由 nginx 直出。静态资源的流向是**宿主机**（`pnpm build` + `collectstatic`）→ `Dockerfile.app` COPY 进镜像的 `/app/www` 与 `/app/frontend/dist`（同时就是 Django 的 `STATIC_ROOT` / `FRONTEND`）→ 启动时 `docker/entrypoint.sh` 复制**另一份**到命名卷 `static_data` → nginx 只读挂载。详见 `nginx/README.md`。
- **静态卷的布局按 URL 前缀设计**：`<卷>/index.html` + `<卷>/assets/*`（Vite）+ `<卷>/static/*`（collectstatic，因为 `STATIC_URL` 就是 `/static/`），所以 nginx **一个 root**（`/usr/share/nginx/html`）就覆盖 `/`、`/assets/*`、`/static/*`；宿主机上 `www/` 与 `frontend/dist/` 仍各由自己的工具清空（`collectstatic --clear` / `pnpm build` 的 `emptyOutDir`），只有容器里这一份被合并。**为什么非要绕这一层卷**（跨容器只能靠卷；卷会遮住镜像内容且只播种一次）：技能 `nginx-container-proxy` 第 6 节。入口脚本每次都**权威**重铺，清卷根时用 `! -name static` 排除 `static/`。
- **配置仓库是命名卷、配置源目录是只读 bind**：app 挂 `config_repo_data:/app/data/config_repo`（**命名卷**，读写）+ `./data/configs:/app/data/configs:ro`（**只读 bind**，写成 long syntax 并显式 **`create_host_path: false`**：缺 `data/configs` 时 `up` 直接报错，而不是让 dockerd 建一个 root 属主、宿主用户写不进也删不掉的空目录——**首次部署要先 `mkdir -p data/configs`**；这是唯一需要宿主目录的挂载点），worker **只**挂那个卷（导入配置是 app 的接口）。`config_repo` 是解析流水线的**内部工作目录**（`ingest/config_repo.py`；`init_repo()` mkdir + git init + commit、`save_config()` 每次导入都提交，连 `get_config` / `list_devices` 这些**读**路径也先调 `init_repo()`），**不需要宿主可见**，所以用命名卷（属主继承自镜像、容器 root 写自己的卷，无需 uid 对齐——语义见技能 `docker-mounts-and-ownership`）；`configs` 是运维放文件的地方（Excel「配置文件」sheet 的 C 列 `config_dir`，按**进程 CWD** 解析，容器里写 `data/configs`），所以是 bind 且挂 `:ro`。**沿革别绕回去**：它曾经是 bind，为此要「容器跑成宿主 uid + `export UID GID` + `HOME=/tmp` + 静态卷 777 + `safe.directory` + 两处挂载点自检」，这些**已全部删除**；唯一保留的是**镜像里的 git 提交身份**（`user.name` / `user.email`），它不是为 bind 服务的——原因见技能 `git-in-containers`。**代价**：宿主侧看不到这份仓库，宿主直跑 Django 用的是 `<项目根>/data/config_repo`（**另一份**，dev 用）。看 / 清理容器那份：`docker compose exec app git -C /app/data/config_repo log --oneline`、`docker compose exec app python manage.py purge_configs --all --purge-repo --yes`；把已有宿主仓库搬进**空卷**：`docker compose run --rm --no-deps -v ./data/config_repo:/from:ro app sh -c 'cp -a /from/. /app/data/config_repo/'`。卷名用新的 `config_repo_data`（不复用旧 `app_data`，避免静默合并两份历史）。
- **不用 `volumes_from`**：它会把源容器的**所有**卷带过来、且容器内路径被绑死；显式写 `static_data:/usr/share/nginx/html:ro` 才能只读、挑卷、放在 nginx 自己的路径上。理由与替代方案：技能 `nginx-container-proxy` 第 6 节。
- **nginx 侧与本项目耦合的两条硬要求**：① 后端地址用**变量式** upstream（`set $netops_upstream "app:8000"`）并配 `resolver`，`resolver` 地址在启动时从 runtime 的 `/etc/resolv.conf` 推导（写死 `127.0.0.11` 换 Podman 就 502）——做法见 `nginx/docker-entrypoint.d/05-netops-resolver.sh`，原理与 envsubst 陷阱见技能 `nginx-container-proxy`；② conf.d 必须用 `$http_host`（含端口）透传 Host，否则后台登录 403。这条契约由 `tests/deploy/test_reverse_proxy_config.py` 守。
- **改动基础镜像的时机**：`pyproject.toml` / `uv.lock` 变了必须重建 `Dockerfile.base`，否则运行期才报 `ModuleNotFoundError`；换源要用 uv 自己的变量、且必须重新 `uv lock`——见技能 `uv-package-and-lockfile`。**基础镜像本身可换**：`Dockerfile.app` 用 `ARG BASE_IMAGE=network-ops-base:py312` + `FROM ${BASE_IMAGE}`（`FROM` 里只能用 `ARG`），compose 用 `x-app-build` 锚点给 app 与 worker 传同一个 build arg（`${BASE_IMAGE:-network-ops-base:py312}`，一处定义不会漂移），所以换私有 registry / Python 版本只需 `BASE_IMAGE=registry.example.com/netops-base:py312 docker compose build app worker`。**构建顺序与命令、两个镜像的分层取舍、`uv sync` 参数、冒烟清单契约、compose 里"看不出来"的约束、改回去会踩的坑**：`docker/README.md`（三个 Dockerfile/compose 文件只在头部留一行指针，注释一律外迁到那里）。
- **启动命令整条在 entrypoint 里拼：硬要求写死，可调参数取环境变量**：`docker/entrypoint.sh` 拼出 `gunicorn netops.asgi:application --worker-class uvicorn_worker.UvicornWorker --bind 0.0.0.0:8000 --workers "${GUNICORN_WORKERS:-1}" …`；**镜像里刻意没有 CMD**（同一个镜像还要当 celery worker 用——worker 在 compose 里被整条换掉、走不到这里；且 CMD 的 exec 形式不展开 `${...}`）。entrypoint 按「`$1` 以 `-` 开头就追加、否则整条替换」的通行写法，三种用法都成立：`docker compose run --rm app --workers 4`（追加）、`docker compose run --rm app python manage.py migrate`（换整条）、worker 的 `entrypoint: ["/bin/sh","-c"]` + `command:`（`exec celery ...`）。
- **gunicorn 可调参数在 `env/gunicorn.env`**：app 用 `env_file: [env/app.env, env/gunicorn.env]`；worker 只有 `env/app.env` + `env/celery.env`（**拿不到**这些旋钮）。清单：`GUNICORN_WORKERS` / `GUNICORN_TIMEOUT` / `GUNICORN_GRACEFUL_TIMEOUT` / `GUNICORN_KEEP_ALIVE` / `GUNICORN_MAX_REQUESTS` / `GUNICORN_MAX_REQUESTS_JITTER` / `GUNICORN_LOG_LEVEL`（空值 / 未设置取默认，写 `0` 就是 0）；**默认值只在 entrypoint 写一份**。改 env 文件后 `docker compose up -d app` 生效、不必重建镜像；**改 `docker/entrypoint.sh` 或任何源码必须重建镜像**，而且 `up -d --build` 这**一条**命令**不会**让容器换镜像（坑与正确做法：技能 `docker-compose-behavior` 第 3 节）。验证：`docker compose exec app grep -n <特征> <文件>`。这些名字是 compose 层定的，不是 gunicorn 官方机制（它只认 `GUNICORN_CMD_ARGS`，而那是**追加**语义，对 `--bind` 只会多一个监听，所以没用）；celery 侧只有一个 `CELERY_LOGLEVEL`（`--concurrency` 刻意不暴露：同设备并发会写坏数据，见下文「关于并发」）。
- **`--bind` 与 `--worker-class` 写死、不做成变量**：`--bind` 与 nginx 的 upstream 耦合（改地址必须同步 nginx），gunicorn 默认值 `127.0.0.1:8000` 一旦漏掉就是 502，且它是 **append** 语义（追加只会多一个监听）。给变量等于给一个必然配错的旋钮。
- **数据库迁移在容器启动时按需自动跑**：第 3 步调 `python manage.py migrate_if_needed`（`apps/core/management/commands/migrate_if_needed.py`），只在**确实有未应用迁移**时才 `migrate --noinput`（依据 `MigrationExecutor.migration_plan(loader.graph.leaf_nodes())`），已是最新就打印一行跳过，日常重启无额外开销。**并发由数据库命名锁（PG advisory / MySQL `GET_LOCK`）串行化**，所以多副本同时启动不会互相竞争——为什么必须自己加锁、以及 PgBouncer transaction pooling 的禁忌：技能 `django-drf-gotchas` 第 2 节。开关 `env/app.env` 的 `MIGRATE_ON_START`（默认 1；设 0 交给外部流水线或人工）；迁移失败 `set -e` 直接退出，**不会**带着过期表结构起 gunicorn。
- **初始管理员零配置创建**：第 4 步无条件调 `manage.py ensure_superuser`——**不占环境变量、不进 compose、不用 secret**（初始管理员属于「零配置起步」那一环，进了环境变量就会出现在 `docker inspect` / `/proc/1/environ` 里）。判定只看数据库：**一个超管都没有**时才建 `admin`，随机密码**打印在启动日志**（`docker compose logs app`）。四条边界：① 已有超管 → 只跳过；② 同名但不是超管 → 只警告、**不自动提权**、也不改密码；③ 人工用法 `--username ops --password '...'`（密码不回显）、`--update-password`；④ 首次登录不需要预建 Token。
- **四个容器都有健康检查**（细节与实测：技能 `container-healthchecks`）：app 探 8000 的 TCP（`socket.create_connection`）；db 探 `pg_isready -U "$$(cat /run/secrets/postgres_user)"`（**`-U` 不能省**——healthcheck 由 docker 以镜像默认用户 root 执行，不带 `-U` 会刷 `role "root" does not exist` 而容器照样 healthy）；nginx 探 `curl -fsS -m 3 --noproxy '*' -o /dev/null http://127.0.0.1/`（**`--noproxy '*'` 不能省**，且别用 busybox `wget` 当探针——它不认 `no_proxy`；`-f` 让 4xx/5xx 也算失败）；worker 探 `celery -A netops inspect ping -d "celery@$$HOSTNAME" --timeout 5`（**必须 `-d` 限定自己**，它走 broker，同时验证「进程活着」+「连得上 Redis」）。worker 的 `depends_on: app: service_healthy` 是为了**等迁移跑完**；nginx 探 80 还能发现「conf.d 没挂进来」（没有 server 块 nginx 照样启动）。
- **环境变量按「谁读」分三处**：`.env`（根）只给 compose 插值；`env/*.env` 按服务 `env_file` 注入（见 `env/README.md`）；`env/secrets/*` 只读挂载给凭据。三条规则：**compose 的 `${VAR}` 只读根 `.env`**、`environment:` 优先于 `env_file`、多个 `env_file` **后面的覆盖前面的**。一个坑：worker 的 `--loglevel` 要读 `env/celery.env`，而 compose 会对自己的文件做 `${...}` 替换（读不到那些文件），所以那里写 `$${CELERY_LOGLEVEL:-info}`——`$$` 到容器里才是 `$`，由 `sh -c` 展开。
- **数据库凭据走 docker secrets，不进 `.env` / 环境变量**：`env/secrets/postgres_user` / `postgres_password` 由 compose 顶层 `secrets:` 只读挂到 `/run/secrets/*`；`env/db.env` 与 `env/app.env` 里只写 `POSTGRES_USER_FILE` / `POSTGRES_PASSWORD_FILE`（db 由 postgres 官方镜像读，app / worker 由 `settings/base.py` 的 `_env_or_file()` 读，没有 `*_FILE` 时回退同名环境变量，宿主机直跑不受影响）。**两条别改回去**：① postgres 官方 entrypoint 规定 `POSTGRES_USER` 与 `POSTGRES_USER_FILE` 同时设置就报错退出，所以只留 `_FILE`；② db 的 healthcheck 靠容器内 `sh` 读 secret，**`-U` 必须显式给**（见上一条）。生成 / 迁移：`bash env/secrets/generate.sh`（默认**沿用旧值**；postgres 只在**首次初始化数据卷**时应用凭据，换值不改库里已有密码——详见 `env/secrets/README.md`）。密钥不入库（`.gitignore`）、不进构建上下文（`.dockerignore`）；redis 密码仍是环境变量（官方镜像没有 `*_FILE` 机制）。为什么不用环境变量（`docker inspect` / `/proc/1/environ` 里是明文）：技能 `container-healthchecks` 第 5 节。
- **代理感知配置**：`SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")` 让 Django 识别 nginx 传来的原始协议；`ALLOWED_HOSTS` 由 `DJANGO_ALLOWED_HOSTS` 控制（默认 `*`），CSRF 可信来源由 `DJANGO_CSRF_TRUSTED_ORIGINS` 控制（默认空；**正常拓扑留空即可**）。
- **「账号密码换 token」的接口必须显式 `@authentication_classes([])`**（`login` / `register` 都是）：否则浏览器带着已登录的 `sessionid` 打过来会被 DRF 的 `SessionAuthentication` 拦成 403——**换个 host 就"好了"是假象**（cookie 域不同而已）。原理见技能 `django-drf-gotchas` 第 1 节；回归测试 `tests/core/test_auth_login_csrf.py`。
- **注册开放，但只创建普通账号**：`POST /api/auth/register/`（`core/api/serializers.py` 的 `RegisterSerializer` + `core/api/auth.py` 的 `register`）只开放 `username` / `password` / `email`（可选）/ `phone`（可选），`is_staff` / `is_superuser` / `is_active` 由服务端决定，走 `create_user()`（**不是** `create_superuser()`）。四条要点：① 视图显式 `@authentication_classes([])`；② 密码过 Django 的 `AUTH_PASSWORD_VALIDATORS`（`validate_password(password, user=candidate)`，**必须传候选用户**，否则相似度校验不生效）；③ 用户名用 `iexact` 判重（数据库唯一约束**大小写敏感**，只查 `exact` 会放过 `Admin` 与 `admin` 并存）；④ 成功直接返回 token（与 `login` 同形 `{token, user:{id,username}}`）。**没有邮箱验证 / 审批 / 限流**（项目没配 `CACHES`，DRF 限流只会退化成单进程计数），要收紧得自己加开关 / 邀请码 / 审批；`email` 不是 unique。前端：`frontend/src/views/auth/Register.vue` + 路由 `/register`（`meta.skipLayout`）。
- **前端请求路径**：以 `/api/` 开头（如 `/api/assets/devices/`）。
- **前端自动导入**：使用 `unplugin-auto-import` + `unplugin-vue-components`（`ElementPlusResolver`）。
- **前端函数风格**：`.vue` 与 `.ts` 一律使用箭头函数，不使用 `function` 声明——普通函数 `const fn = (a: T) => {}`、异步 `const fn = async () => {}`、泛型 `const fn = <T>(a: T) => {}`（`function` 声明会被提升，容易掩盖定义顺序问题）。自检命令（应无输出）：
  `grep -rnE "^[ \t]*(export )?(async )?function [A-Za-z_$]" frontend/src --include=*.ts --include=*.vue`
- **前端数据类型集中管理**：所有具名 `interface` / `type` / `enum` 定义在 `frontend/src/types/`（按域分文件 + `index.ts` barrel `export *` 聚合），引用一律 `import type { ... } from '@/types'`——业务文件（`.ts` / `.vue`）不落具名类型定义，也**不做类型中转导出**；例外只有匿名内联参数类型与第三方库类型转发（`useG6.ts` 的 `GraphData`）。barrel 同名不同结构必须**语义化改名**（`GslbDeviceOption` 先例，勿用 `Xxx_` 下划线避让）；`types/index.ts` 用 `.ts` 不是 `.d.ts`（`.d.ts` 只留给 auto-imports / components / vite-env 这类工具生成与环境声明）。自检（应只剩 useG6 的 GraphData 转发一行）：
  `grep -rnE "^(export )?(interface|type|enum) " frontend/src --include=*.ts --include=*.vue | grep -v "^src/types/"`。细节与三个实测坑：技能 `frontend-types`。
- **表格列宽偏好的 tableKey 只认注册表**：全部 key 集中在 `frontend/src/constants/tableKeys.ts`（`TABLE_KEYS`，命名 `<路由顶级域>.<路径余段>[.<表区分>]`，一页多表各一条、**全局唯一**），调用一律 `useTablePrefs(TABLE_KEYS.xxx)`——入参类型 `TableKey` 由注册表派生，拼错编译期即红。**后端 `/api/me/preferences/` 只是按用户存取的不透明 JSON KV，从不解析 key/value**，撞名/写错的防线全在前端这一处，所以不要在页面里散写字符串字面量。改 key 走同文件的 `TABLE_KEY_RENAMES`（旧→新）登记，读端自动回退旧键、用户已存宽度不丢。接入三件套：`useTablePrefs(TABLE_KEYS.xxx)` + `<DataTable @header-dragend="onHeaderDragend">` + 列上 `:width="widthFor('prop', 默认宽)"`（无 prop 的列必须给 `column-key`）；只写第一行等于没接，拖了不保存。
- **Ruff**：`line-length = 120`；`select = ["E","F","I","N","W"]`，忽略 `F405/F403/E402`；`known-first-party = ["assets","core","ingest"]`；`**/migrations/*` 忽略 `E501`，并通过 `[tool.ruff.format]` 排除（迁移文件不参与格式化）。
- **测试**：pytest + pytest-django，`DJANGO_SETTINGS_MODULE = "netops.settings"`（pyproject；不设 `DJANGO_ENV` → 默认 dev，环境机制见上文 settings 条目），`testpaths = ["tests"]`；测试统一放项目根 `tests/<应用>/`（不散落在应用目录内，应用下不留脚手架的 `tests.py`——pytest 不收集该文件名），各层带 `__init__.py`，路径形如 `tests.assets.test_analysis`。
- **测试内的资源定位**：用包路径（`Path(ingest.__file__).parent / ...`）或 `settings.BASE_DIR`，**不要**用 `Path(__file__).parent.parent`——依赖测试文件自身位置，目录一挪就静默失效（踩过一次，测试因 `exists()` 判断长期"空跑通过"）。

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

### 数据管道层 `ingest/`

数据采集与解析入库（配置的「采、解、存」三段，与 Celery 三阶段工作流对应）。

| 模块 | 职责 |
|------|------|
| `parsers/factory.py` | `ParserFactory` + `BaseParser`(ABC)，按 `(vendor, device_type)` 注册 |
| `parsers/tmpls/` | TTP 解析模板（`configs/`、`running/`） |
| `mapping.py` | 解析产出归一（`KEY_ALIASES` / `FIELD_ALIASES`，纯函数幂等）与 Saver→模型关联（`model_paths`） |
| `savers/base.py` | `BaseSaver`(ABC)，`__init_subclass__` 自动注册；`save()` 入口先归一再交 `_save` |
| `savers/registry.py` | Saver 注册表（按**原始键**分组，含别名） |
| `config_repo.py` | Git 配置仓库的读取、历史、diff |
| `signals.py` | `DeviceConfig` 保存后触发解析与入库 |
| `config_owner.py` | 配置属主解析（堆叠组备机归属主设备） |
| `parsers/template_keys.py` | 从 TTP 模板静态提取顶层数据键 |
| `parsers/contract.py` | 解析器 / Saver 的契约缺口清单（测试与接口共用） |
| `pipeline.py` | 配置处理流水线，信号与 `reparse` 命令共用 |
| `workflow.py` | 任务工作流的入口：`start_task`（建 Task + 投递采集阶段）、`dispatch_stage`、`cancel_task`、`submit_config_job` |

**依赖方向**：`analysis → ingest → assets` 单向；`ingest` 可以用 assets 的模型与序列化器，
**assets 不许 import ingest**；`ingest`（除 `purge_configs` 这类跨域运维工具外）**不许 import analysis**。

### 分析层 `analysis/`

路径追踪、路由采集、DNS 查询与互联网资产分析——**只读**消费 ingest 与 assets 的产出，
自身不采集、不写配置。2026-09 从 ingest 拆出（URL 前缀 `/api/trace/`、`/api/internet-analysis/`
保持不变，前端零改动）。

| 模块 | 职责 |
|------|------|
| `path_tracer.py` | 路径追踪（模拟报文逐跳转发） |
| `api/trace.py` | 路径追踪 / 路由采集 / DNS 查询接口（路由采集用 TTP 模板，路径经 `ingest.parsers.template_keys.TMPLS_DIR` 取） |
| `api/analysis.py` | 互联网资产分析的查询 / 分析 / 导出接口 |
| `models.py` | `InternetAnalysis`：分析结果缓存（每台 GSLB 一份最新结果） |
| `migrations/0001_initial.py` | 从 `operator` 迁入：**不重建表**——operator.0003 只删 state，本迁移 `RunSQL RENAME`，数据随表走 |

**已注册解析器**（`@ParserFactory.register`）：

`A10/slb`、`Cisco/firewall`、`F5/gslb`、`F5/slb`、`H3C/switch`、`H3C/router`、`Hillstone/firewall`、`Huawei/switch`、`Maipu/switch`、`Ruijie/switch`

**Saver 实现**：InterfaceSaver、VrfSaver、RouteSaver、VlanSaver、SnmpConfigSaver、LBVirtualServerSaver、LBPoolSaver、LBSnatSaver、GTMWideipSaver、GtmDatacenterSaver、GtmServerSaver、GtmPoolSaver、AddressBookSaver、ServiceSaver、PolicySaver、DeviceAccountSaver、NatRuleSaver

其中 Route / Vlan / SnmpConfig / Policy / GTM 三个 / DeviceAccount / AddressBook / NatRule / LtmProfile / LtmIRule / LtmPersist 走「Saver 调用序列化器」路径（`BaseSaver.upsert`），其余仍是原生 ORM，待逐步迁移。`LBVirtualServerSaver` 除虚拟服务器外，还负责同一份 `virtuals` 产出里嵌套的 `LtmProfile` / `LtmIRule` / `LtmPersist`（这三个是设备级清单，没有指向 virtual server 的外键）。`GtmServerSaver` 同理兼写 `GtmVServer`。

`ConfigBase` 下有 24 个子模型，其中 22 个已配 Saver。几个需要留意的点：

- `Vlan` / `Route` / `SnmpConfig` / `NtpConfig` / `SyslogConfig` 原为裸 `models.Model`，已改为继承 `ConfigBase`（migration `0023` / `0024`）。代价与收益：`SnmpConfig` / `NtpConfig` / `SyslogConfig` 的 `device` 由一对一变成外键（基数 1:1 → 1:N），各自重复声明的 `created_at` / `updated_at` 与基类同名同义故删除，`related_name` 变为默认的 `<model>_set`；`Vlan.device` 由可空变为必填；`Route` 新增 `device`，与 `vrf.device` 冗余，Saver 入库时用 `vrf` 保证一致，缺失时挂到设备的 `default` VRF。
- `LtmPoolMember` 原为裸 `models.Model`，只有 `pool_name` 字符串、没有 `device`，已改为继承 `ConfigBase`（migration `0026`）。**它保留 `pool_name` 而不是改成指向 `LtmPool` 的外键**：归属靠 `device` 限定，因为 `LtmPool` 的 `(device, name)` 唯一，「设备 + 池名」才能定位到唯一的池。唯一约束是 `(device, pool_name, name, port)`——必须带 `port`，F5 同一节点可以在多个端口上做成员，剥掉 `/Common/node_a:80` 的端口后 `name` 都是 `node_a`，只约束 `name` 会误杀合法数据。存量迁移只有 `pool_name` 可用，无法唯一映射到设备的行（孤儿 / 多台设备同名池）直接删除并在迁移输出里逐条打印，之后再按新唯一键去重。所有按 `pool_name` 查成员的地方（`LBPoolSaver`、`analysis/api/analysis.py`、`analysis/path_tracer.py`）都必须同时限定 `device`，否则不同设备上的同名池会互相串；`LBPoolSaver` 先删后建时也会跨设备误删。
- `NatRule` 的三个匹配 M2M（`source_addresses` / `destination_addresses` / `services`）是 `blank=True`——不同厂商的 NAT 配置能提供的信息差别很大，cisco 的 `nat` group 只有 `network_name`/`host_ip`/`public_ip`，给不出任何 service。
- `static_routes` 的模板字段名不统一（Maipu / Ruijie 用 `subnet_mask`，其余用 `mask`；cisco 还带 `interface_name` 与 `metric`）：`subnet_mask → mask` 已由 `ingest.mapping.FIELD_ALIASES` 在 Saver 入口归一，`RouteSaver` 只读 `mask`。
- `SnmpConfigSaver` 兼容两种产出形态：Huawei / H3C router 的 `community` + `access_type` + `host_ip`，以及 H3C switch（Comware V7）的 `target_hosts[].ip` + `securityname`。
- `PolicySaver` 消费 `policies` / `acl` / `rules` 三种**原始键**，键别名与字段差异（hillstone `rule_id`/`rule_name`、cisco `acl_name` → `policy_id`/`name`）由 `ingest.mapping` 在 `BaseSaver.save` 入口归一；值语义与结构转换仍留在 Saver——hillstone 的 `rules` 是扁平的分列地址，会先落成 `AddressBook` 再挂 M2M：带 `/` 的 `-ip` 是子网、不带是主机；`-address` 是**地址簿引用**（按名字取用，不存在则建占位记录，内容留给 AddressBookSaver 填）；`-range` 拆成 `ip_start` / `ip_end`；`-host` 是主机。`action` 各厂商用词不同（`permit` / `drop` ...），Saver 统一归一为模型的 `allow` / `deny`。
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
按 key 分发给对应 Saver → save() 入口经 ingest.mapping 归一（键/字段）→ 写入数据库
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

`netops/urls.py` 依次 include 四个应用的 urls，全部挂载在 `/api/` 下。

**core**（`core/api/urls.py`）

| 路径 | 说明 |
|------|------|
| `/api/auth/register/` | 注册普通账号（**开放**，成功即返回 token） |
| `/api/auth/login/` | 登录获取 Token |
| `/api/auth/logout/` | 登出 |
| `/api/me/` | 当前用户信息 |
| `/api/me/preferences/` | 当前用户的前端配置（表格列宽等）：GET 全量 / PUT 单条 upsert（value=null 即删）/ DELETE ?key=；按用户隔离 |
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

**ingest**（`ingest/api/urls.py`）

| 路径 | 说明 |
|------|------|
| `/api/configs/git-content/` | 获取指定 commit 的配置内容 |
| `/api/configs/git-diff/` | 对比两个版本的配置差异 |
| `/api/configs/history/` | 设备配置变更历史 |
| `/api/configs/devices/` | 列出有配置的设备 |
| `/api/parsers/` | 已注册解析器列表 |
| `/api/parsers/mapping/` | 解析器 → 模板 → 产出键 → Saver 的映射清单与契约缺口 |
| `/api/parsers/templates/` | TTP 模板文件列表（`configs/` + `running/`） |
| `/api/parsers/templates/<name>/` | 模板文件内容 |
| `/api/parsers/templates/<name>/update/` | 更新模板文件内容（PUT） |
| `/api/access-flows/` | 访问流（策略展开结果）**只读**列表，`?device=` / `?policy=` 走 GIN 包含过滤 |

**analysis**（`analysis/api/urls.py`，前缀沿用拆分前，前端零改动）

| 路径 | 说明 |
|------|------|
| `/api/trace/` | 路径追踪 |
| `/api/trace/route-collect/` | 路由采集 |
| `/api/trace/route-collect-raw/` | 路由采集（原始输出） |
| `/api/trace/routes/` | 路由列表 |
| `/api/trace/dns-query/` | DNS 查询 |
| `/api/internet-analysis/` | 互联网资产分析结果（**只读缓存**，未分析过返回 404） |
| `/api/internet-analysis/analyze/` | **触发分析**并刷新缓存（POST） |
| `/api/internet-analysis/export/` | 导出缓存结果为 xlsx（只读缓存） |

## 注意事项

- **解析器 / Saver / 模型的关联与归一**：三层关联 = 解析器按 (vendor, device_type) 产出**原始**键 → `ingest.mapping` 归一（`KEY_ALIASES` 键别名、`FIELD_ALIASES` 字段别名；纯函数、幂等、**无厂商维度**——同一规范键下的字段同义性与厂商无关，无型号的 device 也要能归一）→ Saver 按 (device_type, key) 消费、以 `model_paths` 声明写入的模型。归一住在 `BaseSaver.save`（模板方法，子类实现 `_save` 只读规范字段）而不是 pipeline：绕过分发直调 `save` 的调用方拿到同样结构。**分层规矩**：结构改名进声明表；**值语义**（permit→allow、enable/disable、route→layer3）留 Saver；**结构级差异**（SNMP 的 community/target_hosts 两形态、Hillstone 扁平地址拆 AddressBook）留 Saver——声明表只做纯改名，混入值转换会被误读成"字段同义"。契约测试：`tests/ingest/test_parser_contract.py`（产出/消费对账切**归一口径**，`KNOWN_MISSING_PRODUCER` 因此只剩 slb 的 snat 两条）+ `tests/ingest/test_mapping.py`（归一行为 + 声明不许说谎：死别名、未声明模型都会红）。清单接口 `/api/parsers/mapping/` 顶层新增 `key_aliases` / `field_aliases` / `savers`（按 Saver 聚合，带 `model_paths`），`consumers` 条目附 `canonical_key` / `models`——均为**增量字段**，前端旧消费不受影响。
- **解析器模板管理页面**（`frontend/src/views/devices/parsers.vue`）以**模板文件**为中心：单表展示 `分组(configs/running) | 文件名 | 关联解析器`，解析器对模板的引用降级为该表的「关联解析器」列（未被引用的显示「未关联解析器」，可用「仅看未关联」筛选），点击行在右侧预览/编辑。此前「解析器列表 + 模板文件列表」两张表的写法存在信息重叠——8 个已注册解析器必然出现在文件列表中，故已合并。
- **F5 池成员的端口分隔符有两种**：名字是普通串或 IPv4 时用冒号（`/Common/node:80`），名字本身是 IPv6 字面量时 F5 改用一个点号（`/Common/2001:db8::1.80`）。所以 `f5_ltm.ttp` 的 `pools` 里成员有两条备选行（点号那条是回退），**并且端口必须限成纯数字**（`vars` 块里的 `PORT`）——不限的话冒号那条会把 IPv6 成员贪婪切成 `name="/Common/2001:db8:"`、`port="1.80"`，永远轮不到回退行，表现为「端口被相邻成员的值带偏」。
- **TTP 模板的引擎行为**（细节 + 内置模式表 + 复现脚本：技能 `ttp-template-gotchas`）：① 模板是被当 **XML** 解析的，所以注释是纯文本——注释行里出现尖括号（直接写 `<vars>` / `<group>`）会被当成未闭合标签，整个模板解析失败（`ParseError: mismatched tag`）；② `re()` 的解析顺序是 `vars` → 内置模式表 → **原样当正则**，也就是说**可以内联写正则**（旧笔记里「不能内联写正则」的说法是**错的**，2026-09 实测纠正）；③ **单条命中给 `dict`、多条命中给 `list`**，消费方两种都要兼容（`savers/lb.py` 注释记的正是这个）；④ 内置 `IPV6` 正则只认十六进制与冒号、**不含点号**（`::ffff:192.168.1.1` 匹配不到）。
- **`parsers/tmpls/running/` 下的模板不在 `ParserFactory` 注册表内**（`route.ttp`、`arp.ttp`、`mac.ttp`、`lldp.ttp`、`h3c_route.ttp`），由路径追踪/路由采集接口（`analysis/api/trace.py`）按名称动态调用；它们在页面上显示为「未关联解析器」，但不代表可以删除。
- **列表分页与搜索排序**：DRF 全局启用数字分页（`netops/pagination.py` 的 `StandardPagination`，默认 50 条/页、最大 500 条，客户端可用 `?page_size=` 覆盖），列表接口返回 `{count, next, previous, results}`；`DEFAULT_FILTER_BACKENDS` 启用 `SearchFilter` / `OrderingFilter`，各 ViewSet 通过 `search_fields` / `ordering_fields` 声明可用字段。前端统一用 `useCrudApi` + `DataPagination` 消费；必须全量的场景（下拉选项、前端聚合统计）用 `fetchAllPages`。时序大表（ARP/MAC、路由、子网使用率）后续可单独启用游标分页。
- **`apps/ingest/ansible/` 只剩 `__pycache__`**，源文件已删除，属重构残留。
- `ingest` 应用的 label 是 `operator`（`OperatorConfig.label`），migrate 时用 `operator` 而非 `ingest`。**拆分只动 Python 路径、不动 label**：`InternetAnalysis` 的迁移历史留在 `operator.0001`（`operator.0003` 仅删 state；`0002_accessflow` 是主仓原有的 AccessFlow），新表名靠 `analysis.0001` 的 `RunSQL RENAME` 对齐——改 label 会让 `django_migrations` 里的历史对不上，别动。
- **互联网资产分析走缓存**：结果存 `analysis.models.InternetAnalysis`（app `analysis`，2026-09 从 ingest 拆出），只有 `POST /api/internet-analysis/analyze/` 才真正计算；查询与导出接口都只读缓存，未分析过时返回 404。
- **资产分析的表格列**：后端 `build_path_rows` 与前端 `internet-asset.vue` 里的 `buildPathRows` 是**两份各自独立**的扁平化实现（列序必须手工保持一致）。当前 7 列：域名 / LLB_VS地址#端口 / LLB_Rule规则 / SLB_VS地址#端口 / SLB_Rule规则 / 服务器地址#端口 / 负责人。
- **地址与端口之间用 `#`，不要用 `:`**：IPv6 地址本身带冒号，`2001:db8::1:80` 分不清哪一段是端口（回退写法 `[...]:80` 虽标准，但 IPv4 用方括号又多余）。`#` 不可能出现在 IPv4/IPv6 里，含义唯一且紧凑。分隔符是两端各一个常量——后端 `analysis.py` 的 `TARGET_SEPARATOR`、前端 `internet-asset.vue` 的同名常量，改要一起改（有测试守 `#` 不可能出现在 IP 里、且能唯一切回）。`ip_port` / `matched_ip_port` / `fallback_ip_port` 这几个内部字段也走同一个拼接函数，它们只出现在前端类型声明里、从未被展示。
- **为什么只有 7 列**：**LLB 的池成员地址#端口 就是 SLB 虚拟服务器的地址#端口**（同一份数据，LLB 池成员指向下一级 SLB），所以不各占一列；「服务器地址#端口」是链路最后一跳的池成员（两级取 SLB 的、一级取 LLB 的，断链时回退到 GTM 地址，见 `_final_target`）。有测试 `test_llb_member_equals_slb_virtual_server` 守这个前提。
- 行字典里仍保留 `llb_address`/`llb_port`/`slb_member_address` 这类**分列字段**（导出与前端展示时再按 `TARGET_SEPARATOR` 拼成 `地址#端口`），`note`/`rtype`/`gtm_ip` 也仍在行里，只是不再出现在表格与导出中——`note` 还被前端用来算「已解析」条数，删列时别顺手删字段。`EXPORT_COLUMN_WIDTHS` 的条数必须与 `EXPORT_HEADERS` 相同（有测试守），列宽按序号用 `get_column_letter` 生成，别再写死 `"ABCDEFGHIJKLM"`。
- 前端模板里**不要把 `row` 作为参数传给函数**（`serverTarget(row)`）：Element Plus 插槽给的 `row` 是它自己的 `DefaultRow`，传给形参类型为 `PathRow` 的函数会 `vue-tsc` 报错；把拼接好的值预先算进行字段（如 `llbTarget`/`slbTarget`/`serverTarget`）再读属性即可。
- **清理配置数据要用 `manage.py purge_configs`**：配置**原文**只在 Git 仓库里，解析**结果**写在各资产表里，而这些表与 `DeviceConfig` **没有任何外键**——所以删 `DeviceConfig`、删仓库都不会级联清掉它们，手工清必漏。命令把「配置解析产物」定义为 `ConfigBase.__subclasses__()`（运行时枚举，当前 24 个；实测 Saver 写入的模型全部是它的子类，不存在"配了 Saver 却不属于 ConfigBase"的漏网之鱼），再加上 `DeviceConfig` 与 `InternetAnalysis` / `AccessFlow` 派生缓存（AccessFlow 是跨设备聚合行、没有 device 字段，按 `device_ids` 的 jsonb 包含过滤圈定）。默认**只报告**（dry-run），`--yes` 才删；`--with-workflow` 才清 Task/Stage（`Stage.output_data` 里可能存着配置**全文**）；`--purge-repo` 才动文件系统，且它会删掉**整个**仓库、所以强制 `--all`。人工 / Excel 数据（Device、DCIM、ServerOwner 等）永远不动；堆叠组的备机不持有配置，`--device <备机>` 会用 `resolve_config_owner` 折算到主设备。两个坑：`Route`/`Vrf` 与运行态采集接口（`/api/trace/route-collect*`）共用同一张表，按表清分不出来源；另外 config_repo 的**位置取决于在哪跑**：Docker 部署里它是命名卷 `config_repo_data` 的挂载点，`--purge-repo` 只有 `docker compose exec app python manage.py purge_configs ...` 才动得到部署那一份，宿主机直跑时才是 `<项目根>/data/config_repo`——两者互不影响，别在宿主上删完以为容器里也干净了。旧的 `network_ops_app_data` 卷是上个方案的**另一份**历史，不会自动删除，确认里空后可以 `docker volume rm network_ops_app_data`。执行前先 `docker compose stop worker`。
- **导入服务器负责人**：`python manage.py import_server_owners --file x.xlsx`（sheet `servers`，列 `hostname` / `ip` / `owner`，另有 `--sheet` / `--dry-run`）。**按列名取而不是按位置**——表头可以换序、可以夹带无关列，缺列直接报错并列出实际表头，避免把 `ip` 静默串到 `hostname` 上。`ip` 是唯一键（导入时用 `ipaddress` 规范化，`2001:DB8::1` 与 `2001:db8::1` 落同一条），文件内重复取最后一行；更新**只覆盖 hostname / owner，不动 `status`**（这份表没有 status 列，不能把手工停用的记录导成启用）。有非法行时**整批不导入**并以非零退出码收尾，不做「写一半再报错」。
- **「负责人」列**：按链路**最后的 IP**反查 `ServerOwner`，回退顺序是 `slb_member_address → llb_member_address → gtm_ip`（见 `_final_ip`）。匹配前两边都过 `_normalize_ip`，否则 `2001:DB8::1` 与压缩写法对不上。负责人**不进分析缓存**——它挂在 `build_path_rows`/`GET` 响应上现查，改了负责人不必重跑分析。前端表格自己扁平化、拿不到数据库，所以 GET 响应额外给一份 `owners`（键是链路最后 IP 的**原始写法**，与前端用同一份回退规则取值），避免在 JS 里重实现 IPv6 规范化。
- `Topology` 是单模型，图数据存于 `graph_data` JSON 字段，没有独立的节点/边表。
- `Device` 没有 `address` 字段，地址信息在 `DeviceConnection` 中。
- **app 改名 `ingest`**（2026-09 由 `ops` 改，作用域＝数据采集与解析入库的「采、解、存」三段）：目录 / `AppConfig.name` / 全部 `import` / **celery 任务名**（`ingest.run_*`、`ingest.rebuild_access_flows`，`task_routes` 同步改）一起改；**`label` 仍是 `operator`**（上一条，迁移历史挂在它上面）、`OperatorConfig` 类名同理保留。**URL 全部不变**，前端零改动。**部署注意**：任务名变了，Redis 里未消费的旧 `ops.*` 消息会 `Unknown task`——升级前停 worker、清空队列再滚动。
- 前端拓扑图使用 `@antv/g6` 5.x。

## 语言约定

- **思考过程用中文展示**：Agent 的分析、推理、解释等思考过程必须使用中文输出。
- 代码注释、commit message、PR 描述等技术文档使用中文。
