# Network Ops

网络运维管理平台（2.0.0）— Django REST 后端 + Vue 3 前端。

后端提供资产模型、配置解析入库、分析域与 REST API；前端由 Vite 打出两个入口：运维主站 `index.html` 与总览大屏 `dashboard.html`。生产/集成环境用 `compose.yml` 起 `db / redis / app / worker / consumer / nginx`（外加一次性的 `code-init`），nginx 是统一入口（静态资源直出，`/api` 反向代理到 app）。

## 功能模块

| 模块 | 路由 / 入口 | 功能 |
|------|------|------|
| **运维主站** | `/`（`index.html`） | 设备管理、配置管理、IPAM、工具、任务中心、文档 |
| **总览大屏** | `dashboard.html` → `/api/dashboard/` | 设备状态 / CPU / 内存、链路带宽折线、SLB、巡检、ITSM 工单、机柜 U 位；数据源 Zabbix + Autotask + 资产库，全部由后端采集/投影，**免认证、前端不带 Token** |
| **设备管理** | `/devices` | 设备列表、接口管理、基线管理（SNMP/NTP/Syslog）、解析器模板、配置对比 |
| **配置管理** | `/config` | 负载均衡（SLB/GSLB）、域名解析、NAT 管理、路由表、ARP/MAC、访问策略 |
| **IP 管理** | `/ipam` | 子网、IP 地址、标签管理 |
| **工具** | `/tools` | 路径追踪（防火墙策略匹配 + NAT + 路由 + 负载均衡）、机柜可视化（U 位视图） |
| **任务中心** | — | 任务/阶段管理（Celery 采集→解析→存储）、访问流单写者消费者、运行监控（celery / Redis / 队列积压巡检） |
| **文档** | `/api/docs/` | 通用表格工作簿编辑、文档转换（md / 自包含 html）与 Dify 知识库推送 |
| **API 文档** | `/api/schema/`、`/api/schema/swagger-ui/`、`/api/schema/redoc/` | OpenAPI 3（drf-spectacular），UI 静态资源走本地 sidecar |

## 技术栈

**后端**
- Python 3.12 / Django 6.1 / Django REST Framework / drf-spectacular
- PostgreSQL（TimescaleDB）+ Redis
- Celery 异步任务（采集→解析→存储 / 访问流重建 / 大屏采集与写库）
- TTP 模板解析（设备配置 → 结构化数据入库）
- `zabbix-utils[async]`（Zabbix JSON-RPC）、pydantic（外部数据源 DTO）、`python-dotenv`（配置分层）、GitPython（每设备一个配置仓库）
- MCP Server（官方 Python SDK，LLM 工具接口，已注册设备库工具，尚未挂网络路由）

**前端**
- Vue 3 + TypeScript + Vite（多页面构建：`netops` / `dashboard` 两个入口）
- Element Plus UI
- ECharts / G6 图可视化
- Pinia 状态管理

## 项目结构

```
network_ops/
├── manage.py
├── netops/          # 项目配置与基建
│   ├── settings/    # base（全部 env 动态项 + LOGGING）+ dev/container/prod（硬差异与守卫）
│   ├── urls.py      # /admin/、/api/schema/*（OpenAPI）、5 个应用 /api/、SPA 兜底
│   └── celery / asgi / lifespan / views / pagination / schema(ExtraModel) / mcp_server
├── apps/
│   ├── core/        # 用户认证、Token、Task/Stage、前端偏好、权限、运维命令
│   ├── assets/      # 网络域数据模型（单文件 models.py）+ Excel 导入 + MCP 设备库工具
│   ├── ingest/      # 配置管道：parsers/tmpls、savers、config_repo、signals、pipeline、workflow、tasks
│   │   └── collectors/   # 外部数据源：zabbix/（异步客户端 + 查询层）、autotask/（工单/SLB/巡检）、dashboard.py（大屏采集编排）
│   ├── analysis/    # 路径追踪、访问流、运行监控、大屏写库与只读供数
│   │   ├── models/  # 模型包：access_flow / internet_analysis / dashboard
│   │   └── api/     # trace / analysis / lb_chain / accessflows / monitor / dashboard / urls
│   ├── cloud/       # 阿里云 API 客户端 + 云资源缓存（暂无对外 API）
│   └── docs/        # 通用表格编辑 + 文档转换 + Dify 知识库推送
├── frontend/
│   ├── index.html / dashboard.html   # Vite 双入口（vite.config.ts 的 rollupOptions.input）
│   ├── dist/        # 构建产物（不入库，由 nginx 直出）
│   └── src/         # main.ts（双入口启动）+ vite-env.d.ts
│       ├── shared/     # 通用能力层：api（含大屏接口 dashboard.ts）/ components（含 PageLayout）/ composables / constants / types（含 dashboard.ts）/ utils / assets
│       ├── netops/     # 主站专属：App.vue / router / views / layout / stores / components（CodeDiffView）
│       └── dashboard/  # 大屏独立代码（App.vue / views / ui / types / utils）
├── tests/           # pytest：core / assets / ingest / analysis / docs / deploy / mcp
├── envs/            # 配置分层：common / container / host / gunicorn / celery.env + example/ + secrets/
├── entrypoint/      # 容器入口 app / worker / consumer / code_init.sh + README（镜像构建手册）
├── scripts/         # 宿主直接部署（deploy-host.sh）与分支/数据库运维脚本
├── nginx/           # conf.d / docker-entrypoint.d（resolver 推导）/ ssl
├── data/            # 运行期数据：config_repo / configs / run(PID) / logs（不入库）
├── www/             # collectstatic 产物（不入库）
├── typings/         # 第三方库类型存根
├── compose.yml      # db / redis / code-init / app / worker / consumer / nginx
├── dockerfile.base / dockerfile.venv / dockerfile.code / dockerfile   # OS / venv / 代码 / 传统项目镜像
├── .env.example     # compose 自己的插值模板（cp 成 .env）
└── pyproject.toml / uv.lock
```

> 目录按三层划分：`src/shared/` 是通用能力层，`src/netops/` 是主站专属（页面、路由、导航骨架、store、依赖主站主题的 `CodeDiffView`），`src/dashboard/` 是大屏应用。别名在 `vite.config.ts` 与 `tsconfig.json` 同步：`@ → src/shared`、`@netops → src/netops`、`@dashboard → src/dashboard`；**shared 不反向依赖两个 app**。`src/shared/api/index.ts` 是带 Token / 401 跳转的主站认证客户端；大屏接口集中在 `src/shared/api/dashboard.ts`，用独立免认证实例，业务类型在 `src/shared/types/dashboard.ts`（由 `dashboard/types/index.d.ts` 转发，大屏组件仍只认 `@dashboard/types`）。
>
> 两套前端共用 `src/main.ts`，按 `#app` / `#dashboard` 两个挂载点分别启动，双入口由 `vite.config.ts` 注册，两个 app 各自 `createPinia()`（状态不共享）。大屏只消费免认证的 `/api/dashboard/` 与 `/api/dashboard/cabinets/`（带 `{status,message,result}` 包装），前端不带 Token、不做登录跳转；Zabbix / Autotask 的采集落库与资产数据的投影全部在后端完成。

## 快速开始

```bash
cp envs/example/*.env envs/       # 首次克隆：生成配置实例（envs/*.env 不入库）
uv sync --all-groups
cd frontend && pnpm install && cd ..

uv run python manage.py migrate
uv run python manage.py runserver
cd frontend && pnpm dev           # Vite 开发服务器，/api 代理到 localhost:8000
```

宿主直跑时 `netops/settings/base.py` 会自动 `load_dotenv(envs/common.env)` +（非 container 时）`envs/host.env`；**真实进程环境变量优先**，`NETOPS_SKIP_DOTENV=1` 可全部跳过。数据库/Redis 连本机，凭据用同名环境变量（或在 `host.env` 里给相对 `*_FILE` 与容器共用 `envs/secrets/*`）。完整配置分层见 `envs/README.md`。

服务器上不经容器直接部署用同一个脚本（app / worker / consumer 三进程，PID 在 `data/run/`、日志在 `data/logs/`）：

```bash
./scripts/deploy-host.sh deploy   # build + migrate + restart
./scripts/deploy-host.sh status
```

## 部署

`compose.yml` 的部署方式是「**代码与静态成品经代码镜像 + 命名卷分发**」：`code-init` 一次性把 `dockerfile.code` 里的 `/opt/netops/code` 与 `/opt/netops/http` 铺进 `code` / `static` 两个卷，app / worker / consumer 用 `VENV_IMAGE`（只装依赖）挂 `code:/app:ro` 启动，nginx 只读挂 `static` 卷。

```bash
cp .env.example .env                  # CODE_IMAGE / VENV_IMAGE / 宿主映射端口
cp envs/example/*.env envs/           # 按现场修改 envs/common.env
bash envs/secrets/generate.sh         # 数据库凭据；阿里云 4 个 AK 文件需手工补齐（见 envs/secrets/README.md）
mkdir -p data                         # data 卷是 bind，缺目录时 up 直接失败

cd frontend && pnpm build && cd ..    # 静态成品必须在宿主机构建
uv run python manage.py collectstatic --noinput

TAG=$(git rev-parse --short HEAD)
docker build --network=host -f dockerfile.base -t network-ops-base:py312 .
docker build --network=host -f dockerfile.venv -t network-ops-venv:dev --build-arg BASE_IMAGE=network-ops-base:py312 .
docker build -f dockerfile.code -t network-ops-code:$TAG .
CODE_IMAGE=network-ops-code:$TAG VENV_IMAGE=network-ops-venv:dev docker compose up -d code-init
docker compose up -d
```

细节见四份手册：`entrypoint/README.md`（镜像分层、构建顺序、卷与冒烟清单；文中 `Dockerfile.*` 为旧名，实际文件全小写）、`envs/README.md`（配置三层与优先级）、`envs/secrets/README.md`（密钥生成与轮换）、`nginx/README.md`（反向代理与静态卷）。改依赖（`pyproject.toml` / `uv.lock`）必须重建 `dockerfile.venv`；改源码后重建代码镜像并**重新跑 `code-init`**（`up -d --build` 不会换容器）。

## 大屏数据流

```
外部投递 ingest.collect_dashboard(source)      # source = zabbix | autotask
  → ingest/collectors/dashboard.py            # asyncio 采集，返回纯 dict，不碰数据库
  → send_task("analysis.write_dashboard")     # 按任务名字符串投递，不 import analysis
  → analysis/tasks.py::write_dashboard       # 唯一写库入口：事务内 upsert 大屏表
  → GET /api/dashboard/                      # 只读免认证，折线由最近 3 小时样本聚合
  → GET /api/dashboard/cabinets/             # 只读免认证，机柜 U 位最小字段投影（不读需登录的 assets 列表）
```

采集 payload 默认随消息直投（A 方案），`DASHBOARD_PAYLOAD_VIA_REDIS=1` 时暂存 Redis、只投 `__redis_key__`（C 方案）。任务名只在 `settings.DASHBOARD_WRITE_TASK` 定义一次，由测试对账。

## 通用组件说明

| 组件 | 用途 |
|------|------|
| `DataTable` | el-table 包装器（分页/loading/列宽偏好 + `table-key`） |
| `DataColumn` | 列级封装（偏好列宽 + 固定/弹性宽度档位） |
| `DataPagination` | 分页控件，配合 `useCrudApi` 的 `fetchAllPages` |
| `ChartCard` / `StatCard` | ECharts 卡片（autoresize）/ 数字统计卡片 |
| `FormPage` / `FilterBar` | 表单页布局 / 通用筛选栏 |
| `DeviceFilter` | 设备选择器（自动加载设备列表，v-model） |
| `ColumnSettings` / `CodeDiffView` | 列显隐与宽度设置 / 代码差异对比 |
| `AppNav` / `SideLayout` / `UserBar` | 主站布局组件（`src/netops/layout/`） |

## Composables 说明

| Composable | 用途 |
|------------|------|
| `useCrudApi` | 通用 CRUD 数据管理（loading/search/filter/fetch/save/delete） |
| `useEcharts` / `useG6` | ECharts 配置工厂 / G6 拓扑图注册 |
| `useTablePrefs` | 表格列宽偏好读写（key 只认 `constants/tableKeys.ts` 注册表） |
| `useSearchSync` | 搜索条件与 URL / 列表状态同步 |
| `useTagType` | Tag 颜色映射（protocol/mode/status） |

> 前端约定（类型组织、主题变量、函数风格、表格列规范）与后端开发约定统一见 `AGENTS.md`。
