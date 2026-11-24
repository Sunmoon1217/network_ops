# settings 分层与环境变量

`DJANGO_SETTINGS_MODULE` 恒为 `netops.settings`（包），环境旋钮只有 **`DJANGO_ENV`**：
`dev`（默认，不设即此）/ `container` / `prod`，**未知值拒绝启动**（拼错如 `prd` 不静默落 dev）。

## 分层依据

1. **可被环境变量影响的配置只在 `base.py` 定义一遍**。环境变量本身就是环境区分机制：
   同一个 `os.environ.get` / `_env_list` 写一遍，靠各环境注入不同的值即可，
   不需要每个环境文件重写一遍读取逻辑。
2. **环境文件只放「不走环境变量、但必须按环境硬改」的东西**：
   - `dev.py`：空壳，base 即 dev 语义；
   - `container.py`：两条 host 必填守卫；
   - `prod.py`：`DEBUG=False` 硬覆盖 + 5 项必填守卫。
3. **覆盖顺序**：`from .base import *` 在前、`from .<env> import *` 在后，
   所以环境文件的少数硬差异（含「守卫即 import 副作用」）胜出。
4. **防循环导入硬规矩**：`base.py` 与三个环境文件只允许 `from .base import ...`、
   标准库与 Django 的 import；**禁止** `from netops.settings import ...` / `from . import ...`
   ——反向依赖父包执行结果会在 `__init__` 半初始化时炸（`ModuleNotFoundError` /
   `ImportError: cannot import name`；`BASE_DIR` 那次事故就是这个形态）。

包入口 `netops/settings/__init__.py` 另做两件事：把 `_env_list` / `_env_or_file` 显式补导出
（`import *` 不带下划线名字，而 `tests/deploy` 直接用 `netops.settings._env_or_file`）；
把 `BASE_DIR` 与 `apps/` 插进 `sys.path`（根下 `llmtools`、`apps/` 下的 `core/ingest/...`
以顶层包出现，不依赖 CWD）。

### 策略参数：代码默认 + 按环境区分

`settings/defaults.py` 集中放**确实随环境不同**的策略默认值（目前是 `MCP_ENABLED` 与
`DJANGO_API_DOCS_REQUIRE_LOGIN`），`base.py` 按 `DJANGO_ENV` 选一套，读取顺序是
`env > defaults.py > 代码兜底`。`compose.yml` 把 `DJANGO_ENV` 显式注入四个应用进程，
所以生产容器写 `DJANGO_ENV=prod` 就能生效。

其余旋钮（AccessFlow 阈值、大屏周期、各 HTTP 超时、Dify 分段等）的默认值仍写在 base，
**通常不用写进 `envs/*.env`**；要现场调整时 export 同名变量或在 env 文件里取消注释即可。
下表「谁注入」只说明常规来源，不代表必须写进 env 文件。

## 凭据链

统一为 **`<NAME>_FILE` > 同名环境变量 > 默认值**，实现在 `base._env_or_file`：

- `*_FILE` 指向的文件优先（Docker secrets 在 compose 下就是 `/run/secrets/<name>` 文件）；
- 文件存在但读不出来时**直接报错**，不静默回退到默认密码——那只会把「密钥配错了」
  伪装成「数据库连不上」；
- 内容 `strip()`，与 postgres 官方 entrypoint 的 `$(cat file)` 行为一致（否则末尾换行
  会变成密码的一部分）；
- **使用约定**：`*_FILE` 在容器里由 `envs/container.env` 指向 `/run/secrets/*`；宿主机直跑
  默认不设 `*_FILE`，自然走同名环境变量层，想与容器共用同一份密钥就在 `envs/host.env` 里给
  **相对路径**（按 `BASE_DIR` 解析）——三个环境的链路统一，不分叉。

## 宿主直跑的 `.env` 兜底（`load_dotenv`）

`base.py` 顶部（`BASE_DIR` 之后）做一次环境文件兜底，**真实进程环境永远优先**：

1. `NETOPS_SKIP_DOTENV=1` → 全部跳过（`tests/deploy` 用它拿纯净默认值，不吃本机实例）；
2. `load_dotenv(envs/common.env)`；
3. `DJANGO_ENV != container` 时再 `load_dotenv(envs/host.env)`——容器里代码卷也带着 `envs/`，
   不做这一步区分会把宿主的 `DB_HOST=127.0.0.1` 泄进容器。

`load_dotenv` 全程 `override=False`，所以 compose `env_file` 注入的值与手工 `export` 都赢过文件。
目录约定与逐文件职责见 [`envs/README.md`](../envs/README.md)。

## 环境变量全表（Django 侧）

「谁注入」一列只说明常规来源；容器里的注入文件与插值规则见 `envs/README.md`。

### Django 自身

| 变量 | 默认 | 说明 |
|------|------|------|
| `DJANGO_SECRET_KEY` | 内置开发期密钥 | 生产必须注入（`prod.py` 查原始值，不吃 fallback） |
| `DJANGO_DEBUG` | `1` | `0/false/no` 收紧；prod 硬覆盖为 `False`，此变量无效 |
| `DJANGO_ALLOWED_HOSTS` | `*` | 逗号分隔；nginx 用 `proxy_set_header Host $http_host` 透传原样 Host（含端口），Django 校验时剥端口再比对，所以必须放行；prod 必填且不许 `*` |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | 空 | 正常拓扑留空（Origin 天然等于当前 host）。只在「浏览器看到的来源 ≠ 转给 Django 的 Host」时才需要（外层 LB 改写 Host、TLS 提前终结）；值带 scheme，逗号分隔 |
| `DJANGO_LOG_LEVEL` | `INFO` | 业务命名空间（`core/ingest/assets/analysis/cloud/docs/llmtools/netops`）的日志级别，见下方 `LOGGING` |
| `DJANGO_API_DOCS_REQUIRE_LOGIN` | dev/container 关、prod 开 | 控制 `/api/schema/*` 是否收紧成 `IsAuthenticated`；默认值在 `settings/defaults.py`，env 可覆盖 |

### 数据库 / Redis

| 变量 | 默认 | 说明 |
|------|------|------|
| `DB_ENGINE` | `postgresql` | `postgresql` / `mysql`，其它值**拒绝启动**；MySQL 的默认端口因此变成 3306 |
| `DB_NAME` | `netops` | 库名 |
| `DB_USER` / `DB_USER_FILE` | `netops` | 走凭据链 |
| `DB_PASSWORD` / `DB_PASSWORD_FILE` | `netops_password` | 走凭据链；prod 必须给出其一 |
| `DB_HOST` | `127.0.0.1` | 容器注入 `db`；container / prod 必填 |
| `DB_PORT` | `5432`（MySQL 下 `3306`） | 容器内固定为后端默认端口 |
| `REDIS_HOST` | `127.0.0.1` | 容器注入 `redis`；container / prod 必填 |
| `REDIS_PORT` / `REDIS_DB` | `6379` / `0` | |
| `REDIS_PASSWORD` | 空 | 非空时拼进 `REDIS_URL`；redis 官方镜像没有 `*_FILE` 机制，密码只走环境变量 |

`CELERY_BROKER_URL` 与 `CELERY_RESULT_BACKEND` 都等于 `REDIS_URL`。

**连接参数统一用 `DB_*`**（`DB_ENGINE` / `DB_NAME` / `DB_USER` / `DB_PASSWORD` / `DB_HOST` /
`DB_PORT`）：settings 只认这一套名字，两种部署一致。各数据库镜像自己认的 `POSTGRES_*` /
`MYSQL_*` 在 `envs/common.env` 里用 `${}` 嵌套出来（`DB_NAME → POSTGRES_DB/MYSQL_DATABASE`、
`DB_USER → MYSQL_USER`），不进 settings。`DB_ENGINE` / `DB_NAME` / `DB_USER` **只在 common.env
定义一次**（两种部署一致）：容器侧 `DB_ENGINE=${DB_SERVICE:-<默认值>}` 由根 `.env` 的
`DB_SERVICE` 插值决定；宿主直跑同名变量不设时取 `${}` 里的默认值，`switch-db.sh` 切换后端时
会同步改写它（因此宿主无需再 `export DB_SERVICE`），真实进程环境仍永远优先。

MySQL 驱动是 **mysqlclient**（C 扩展）。它在 PyPI 没有 cp312 manylinux 轮子，宿主直跑要先装
`pkg-config` 与 `libmariadb-dev`（`uv sync` 才编得出来）；镜像里由 `dockerfile.venv` 的两阶段
构建解决，运行阶段只保留 `libmariadb3`。跨库差异清单见 [`deploy.md`](deploy.md) 的「MySQL 后端」。

两个 `HOST` 的默认值写 `127.0.0.1` 而不是 `localhost`：Windows 上 `localhost` 优先解析成
`::1`，而本机的 PostgreSQL / Redis 通常只监听 IPv4，驱动会逐个地址回退——每次连接白等
约 10s（实测 10.03s vs 0.03s）。pytest 一个会话要建两三条连接，setup 直接被拖到 40s 级。

### 访问流（AccessFlow）链路

| 变量 | 默认 | 说明 |
|------|------|------|
| `ACCESS_FLOW_MAX_QUEUE` | `500` | 背压阈值，口径是 Stream **未投递积压**（`XINFO GROUPS` 的 lag，不是 XLEN）。取值理由与事故复盘见 [`analysis.md`](analysis.md) |
| `ACCESS_FLOW_DISPATCH` | `1` | 投递总开关；测试里 conftest 统一置 False，避免保存策略就往真实 Redis 发消息 |
| `ACCESS_FLOW_TASK` | `analysis.rebuild_access_flows` | 任务名的**唯一定义处**：装饰器 `name=` 与 `CELERY_TASK_ROUTES` 的 key 必须与之一致，`tests/analysis/test_access_flow_task.py` 对账 |

### 大屏（Dashboard）链路

| 变量 | 默认 | 说明 |
|------|------|------|
| `DASHBOARD_WRITE_TASK` | `analysis.write_dashboard` | 任务名的**唯一定义处**：`ingest.tasks.collect_dashboard` 按它 `send_task`（不 import analysis）。`tests/ingest/test_dashboard_collect.py` + `tests/analysis/test_dashboard_write.py` 对账 |
| `DASHBOARD_PAYLOAD_VIA_REDIS` | `0` | `0` = payload 随消息直投（A 方案）；`1` = payload 暂存 Redis、只投 `{"__redis_key__": …}`（C 方案） |
| `DASHBOARD_PAYLOAD_TTL` | `600` | C 方案下暂存 key 的 TTL（秒） |
| `DASHBOARD_COLLECT_SECONDS` | `180` | 设备组采集周期（秒）：内置 beat 投递 `ingest.collect_dashboard("zabbix")`，**必须 > 0** |
| `DASHBOARD_AUTOTASK_SECONDS` | `600` | 工单 / SLB / 巡检采集周期（秒）：投递 `ingest.collect_dashboard("autotask")`，外部系统较慢故默认更长 |
| `DASHBOARD_LINKS_FILE` | `conf/links.json` | 链路清单与展示 label 的唯一权威；容器 `/etc/netops/conf/links.json`、宿主相对 `BASE_DIR` 解析 |
| `DASHBOARD_LINK_CACHE_KEY` | `dashboard:link:series` | 链路缓存 key（常量，不支持 env 覆盖）；ingest 写、analysis 只读 |
| `DASHBOARD_LINK_CACHE_TTL` | `600` | 缓存 TTL（秒），应大于刷新周期，Zabbix 抖动时保留上一份 |
| `DASHBOARD_LINK_REFRESH_SECONDS` | `180` | beat 刷新周期（秒）；管理命令 `refresh_link_cache` 可立即刷新 |
| `DASHBOARD_LINK_WINDOW_HOURS` | `3` | 链路折线窗口（小时） |

### 外部连接健康探活

| 变量 | 默认 | 说明 |
|------|------|------|
| `INTEGRATION_PROBE_TASK` | `core.integrations.probe_all` | 任务名的**唯一定义处**：`apps/core/tasks.py` 的装饰器 `name=` 与 beat key 必须与之一致（`tests/core/test_integration_health.py` 对账） |
| `INTEGRATION_PROBE_SECONDS` | `300` | beat 探活周期（秒）；结果 upsert 到 `core.IntegrationHealth`，`GET /api/core/integrations/` 只读 |

### MCP 工具出口（`/mcp`）

| 变量 | 默认 | 说明 |
|------|------|------|
| `MCP_ENABLED` | dev/container 开、prod 关 | `0` = 不 import `llmtools`、不建 MCP 子应用、不装 lifespan 钩子，`/mcp` 明确回 404（**不能**交给 Django，SPA 兜底会返回 `index.html`）。默认值在 `settings/defaults.py`，env 可覆盖。见 [`llmtools.md`](llmtools.md) |
| `MCP_RATE_LIMIT_PER_MINUTE` | `60` | 匿名出口的护栏：按客户端 IP 的分钟固定窗口，`0` = 不限流；Redis 不可用时**放行**（只告警）。身份口径见 `netops/mcp_gateway.py` 模块注释 |

### Git 配置仓库（`core/config_repo.py`）

| 变量 | 默认 | 说明 |
|------|------|------|
| `CONFIG_REPO_PATH` | `<项目根>/data/config_repo` | 配置快照仓库根：**每台设备一个独立仓库** `<CONFIG_REPO_PATH>/<hostname>/`。容器里覆盖成命名卷挂载点（`/configs`，见 [`deploy.md`](deploy.md)）——宿主与容器各一份历史，互不影响 |

路径的唯一来源是 `settings.CONFIG_REPO_PATH`：`core/config_repo.py` **每次调用都读**（不缓存成
模块常量），所以测试用 `override_settings(CONFIG_REPO_PATH=tmp_path)` 就能换目录，
`scripts/purge_configs.py --purge-repo` 也读同一个值。

### 外部连接配置（统一 schema）

四套外部连接（Zabbix / 阿里云 / Dify / autotask）的配置字典共用四个字段，消费方一律看
`enabled`，不再各自判断 url / api_key / AK 是否存在：

| 字段 | 含义 |
|------|------|
| `base_url` | 入口地址；阿里云按 `region` + 各产品 endpoint 接入，没有单一入口，固定为空 |
| `credential_ref` | 凭据的**环境变量名**（不是值）；值的链路仍是 `*_FILE > 环境变量 > 默认值` |
| `timeout` | HTTP / SDK 超时秒数 |
| `enabled` | 地址与必填项是否齐备；为假时消费方抛 `ImproperlyConfigured`（Dify 推送接口返回 503） |

域特有项原样保留（阿里云 `region` / `endpoints` / `accounts`、Dify 的 `dataset_id` 与分段规则、
Zabbix 的 `token` / `user` / `password`）。

### Zabbix（`core/integrations/providers/zabbix`，实例由 core 统管）

| 变量 | 默认 | 说明 |
|------|------|------|
| `ZABBIX_URL` | 空 | Zabbix 前端地址；未配置（或凭据不全）则 `get_zapi` 拒绝创建 |
| `ZABBIX_TOKEN` / `ZABBIX_TOKEN_FILE` | 空 | API Token（Zabbix ≥ 5.4），**优先于**用户名密码 |
| `ZABBIX_USER` / `ZABBIX_PASSWORD`（含 `_FILE`） | 空 | 用户名登录（Zabbix < 7.2 走 `user.login`） |
| `ZABBIX_TIMEOUT` | `30` | HTTP 超时秒数 |

`zabbix_utils` 自身也会读同名 env 兜底，这里显式传参以 `settings.ZABBIX_CONFIG` 为准。
client 单例与登录逻辑在 `core/integrations/providers/zabbix/client.py`（见
[`integrations.md`](integrations.md)）；采集侧只留查询编排 `ingest/collectors/zabbix/queries.py`。

### 阿里云

一朵云、两个资源集（生产/测试），两套账号，共用 region；各产品 endpoint 不同，分别传参。
凭据链路同其他凭据（`*_FILE` > 环境变量 > 空）。

| 变量 | 说明 |
|------|------|
| `ALIYUN_REGION` | 区域，例 `cn-hangzhou`（两个账号共用） |
| `ALIYUN_ECS_ENDPOINT` | ECS endpoint |
| `ALIYUN_VPC_ENDPOINT` | VPC（含 VSwitch）endpoint |
| `ALIYUN_SLB_ENDPOINT` | SLB endpoint |
| `ALIYUN_SLS_ENDPOINT` | SLS endpoint |
| `ALIYUN_ASAPI_ENDPOINT` | ASAPI endpoint |
| `ALIYUN_TIMEOUT` | SDK 超时秒数，默认 `30` |
| `ALIYUN_PROD_ACCESS_KEY_ID` / `..._SECRET` | 生产账号 AK |
| `ALIYUN_TEST_ACCESS_KEY_ID` / `..._SECRET` | 测试账号 AK |

### Dify 知识库（`apps/docs` 文档转换的推送目标）

| 变量 | 默认 | 说明 |
|------|------|------|
| `DIFY_API_BASE_URL` | 空 | 知识库 API 地址（含 `/v1`），如 `https://dify.example.com/v1` |
| `DIFY_API_KEY` / `DIFY_API_KEY_FILE` | 空 | Bearer 认证，走凭据链 |
| `DIFY_DATASET_ID` | 空 | 目标知识库（dataset）ID |
| `DIFY_INDEXING_TECHNIQUE` | `high_quality` | 或 `economy` |
| `DIFY_TIMEOUT` | `30` | HTTP 超时秒数 |
| `DIFY_PROCESS_MODE` | `automatic` | 分段模式，或 `custom` |
| `DIFY_SEGMENT_SEPARATOR` | `\n` | custom 模式的分段分隔符（`\n` / `\t` 转义会被还原） |
| `DIFY_SEGMENT_MAX_TOKENS` | `500` | custom 模式的分段 token 上限 |

前三项（`base_url` / `api_key` / `dataset_id`）齐备才启用推送；缺失时推送接口返回 503，
转换与留档不受影响。

### autotask（大屏的工单 / 巡检 / SLB 源）

| 变量 | 默认 | 说明 |
|------|------|------|
| `AUTOTASK_BASE_URL` | 空 | 工单 / 巡检 / SLB 服务地址；未配置则大屏的 autotask 源失败（其余源不受影响） |
| `AUTOTASK_TIMEOUT` | `30` | HTTP 超时秒数 |

内网服务，无凭据。地址原先硬编码在 `ingest/collectors/autotask/autotask.py`，2026-11-19 起走 env。

## 守卫矩阵（什么时候拒绝启动）

| 环境 | 硬覆盖 | 守卫（缺即 `ImproperlyConfigured`） |
|------|--------|-----------------------------------|
| `dev` | 无 | 无 |
| `container` | 无 | `DB_HOST`、`REDIS_HOST` 必须由 `envs/container.env` 注入 |
| `prod` | `DEBUG = False` | `DJANGO_SECRET_KEY`、`DJANGO_ALLOWED_HOSTS`（非空且不含 `*`）、`DB_HOST`、`DB_PASSWORD(_FILE)`、`REDIS_HOST` |

两条设计取舍：

- **container 守卫存在的理由是「发现得早」**：base 里 `HOST` 默认 `127.0.0.1`，
  而 Django 的数据库连接是惰性的——env_file 少一行不会在启动时报错，要到首个请求才
  `connection refused`，故障发现晚一拍。守卫让它启动即拒。
- **守卫一次报全**：缺几个就一条消息列出几个，不做「修一个、再启动、又缺一个」的挤牙膏式失败。

守卫与分发矩阵由 `tests/deploy/test_settings_environments.py` 守。

## LOGGING：只给项目命名空间装 handler

Django 的 `DEFAULT_LOGGING` 只给 `django` / `django.server` 装了 handler，业务模块的
`getLogger(__name__)` 一路传播到 root 也没有 handler，只剩 `logging.lastResort`——它只放行
WARNING 以上，INFO 全被静默丢弃。常驻的 consumer 运行期输出全是 INFO，于是「日志文件里除了
报错什么都没有」。

`base.py` 的 `LOGGING` 给 `core / ingest / assets / analysis / cloud / docs / llmtools / netops`
各配一个 `StreamHandler(ext://sys.stderr)`，级别取 `DJANGO_LOG_LEVEL`：

- **不动 root**：celery worker 会 hijack root，第三方库的 INFO 也不该跟着喷进日志；
- **不动 Django 默认配置**：`django.request` / `mail_admins` 保持原样；
- `propagate` 保持默认 True，pytest 的 `caplog`（挂在 root）仍能捕获这些记录；
- 输出走 stderr：`StreamHandler` 每次 emit 都 flush，宿主重定向的 `data/logs/*.log` 与
  `docker logs` 都能实时收到；
- **命令给操作者看的输出不属于日志**，走 `BaseCommand` 的 `self.stdout` / `self.stderr`
  （见 `access_flow_consumer`），不受日志级别影响。

## API 文档（OpenAPI 3）

`REST_FRAMEWORK.DEFAULT_SCHEMA_CLASS` 指向 `drf_spectacular.openapi.AutoSchema`；
`SPECTACULAR_SETTINGS` 的 UI 资源一律 `SIDECAR`（内网不通外网，随 `collectstatic` 进
`/static/` 由 nginx 直出），`SERVE_INCLUDE_SCHEMA=False`；权限取 `API_DOCS_PERMISSION`
（dev/container 默认 `AllowAny`、prod 默认 `IsAuthenticated`，见 `settings/defaults.py`；
env 设 `DJANGO_API_DOCS_REQUIRE_LOGIN` 可覆盖）。
路由见 [`api.md`](api.md)。
