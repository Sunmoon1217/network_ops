# Network Ops

网络运维管理平台 — Django REST 后端 + Vue 3 前端

## 功能模块

| 模块 | 路由 | 功能 |
|------|------|------|
| **总览** | `/overview` | 全局统计仪表盘（ECharts 图表）+ 任务队列监控卡片 |
| **资产** | `/asset/*` | 设备台账与配置快照（`devices`，含历史/对比）、网卡接口（`interfaces`）、VLAN（`vlans`）、IP 与网段（`ip-addresses` / `subnets`，含标签与使用趋势）、负载均衡与域名（软资产视图） |
| **配置** | `/config/*` | 负载均衡（`slb` / `gslb`）、防火墙与访问策略（`firewall` / `policy`）、路由表（`routing-table`）、ARP/MAC（`arp-mac`）、基线（`baseline`：SNMP / NTP / Syslog）、解析器模板（`parsers`）、设备账号（`accounts`） |
| **拓扑** | `/topology` | 拓扑视图（编辑页在建） |
| **监控** | `/monitor/*` | 任务/阶段管理（`tasks`，Celery 采集→解析→存储）、运行监控（`status`：celery / Redis / 队列积压巡检） |
| **文档** | `/docs/*` | 知识库、临时文档、在线表格（`spreadsheet`） |
| **工具** | `/tools/*` | 路径追踪（策略匹配 + NAT + 路由 + 负载均衡）、机柜 U 位视图、子网计算器、DNS 查询、互联网资产、解析映射对照 |
| **总览大屏** | `/dashboard`、`/dashboard.html`（独立入口；`/` 302 到大屏） | Zabbix / Autotask 供数的可视化大屏；数据由 `analysis.write_dashboard` 写库、`GET /api/dashboard/` 只读 |

> 旧的 `/devices`、`/ipam`、`/tasks`、`/tools/spreadsheet` 路径保留 redirect，收藏夹不会 404。

## 技术栈

**后端**
- Python 3.12 / Django 6.1 / Django REST Framework
- PostgreSQL（TimescaleDB）+ Redis
- Celery 异步任务（采集→解析→存储；访问流重建；大屏采集→写库）
- TTP 模板解析（设备配置 → 结构化数据入库）
- OpenAPI 3 文档（drf-spectacular，浏览器入口 `/api/schema/` → Swagger UI；描述文件 `/api/schema/openapi.yaml`，UI 走本地 sidecar）
- 外部平台连接：client 实例与生命周期由 `apps/core/integrations/` 统管（当前接入 Zabbix，
  `providers/zabbix/` 持单例并按事件循环释放），采集侧只留查询编排
  `apps/ingest/collectors/zabbix/`；Autotask 工单 / SLB / 巡检客户端在
  `apps/ingest/collectors/autotask/`（pydantic DTO）
- MCP Server（官方 Python SDK 2.x，`/mcp` Streamable HTTP；基建与出口在根目录 `llmtools/`，各域注册实体，通用工具只认注册表，工具由 `llmtools/tools.py` 统一注册）

**前端**
- Vue 3 + TypeScript + Vite
- Element Plus UI
- ECharts / G6 图可视化
- Pinia 状态管理

## 项目结构

```
network_ops/
├── netops/          # Django 项目配置与基建（settings / urls / asgi / lifespan / celery / pagination）
├── apps/
│   ├── core/        # 用户认证、Token、Task/Stage、外部连接实例（integrations/）、Git 配置仓库（config_repo.py）、运维命令
│   ├── assets/      # 基础资产（叶子域）：DCIM / 设备台账 / IPAM / CI 统一台账 + 软资产扩展表
│   ├── configs/     # 配置域：ConfigBase 25 子类 + DeviceConfig 快照、TTP 解析（parsers/）、入库（savers/ + mapping.py）、软资产归并计算、admin / API / 序列化器
│   ├── ingest/      # 采集与入库编排（pipeline / workflow / 信号 / Celery 任务）+ Excel 导入（device_import.py）+ collectors/（Zabbix 查询编排、Autotask）
│   ├── analysis/    # 分析与观测（资产总览聚合、路径追踪、访问流、互联网分析、队列与 Redis 巡检、大屏供数），models/ 是包
│   ├── cloud/       # 云平台接入（阿里云 API 客户端 + 云资源缓存）
│   └── docs/        # 表格编辑 + 文档转换 + Dify 推送
├── llmtools/        # MCP 工具子系统（基建 + 注册表 + 各域实体声明与工具）
├── frontend/        # Vue 3 + TypeScript + Vite，双入口（index.html / dashboard.html），src/{shared,netops,dashboard}
├── tests/           # pytest 测试（按应用分目录：core / assets / configs / ingest / analysis / docs / deploy / mcp / netops / scripts）
├── scripts/         # 运维与开发脚本（purge_configs.py、setup-git-hooks.sh、部署与数据库辅助）
├── handbook/        # 领域手册 + design/（设计提案）+ roadmap.md
├── nginx/           # 反向代理（静态直出 + /api、/mcp 代理）
├── entrypoint/      # 容器入口脚本 + 容器化构建手册（entrypoint/README.md）
├── envs/            # 配置分层（common / container / host / db）+ gunicorn / celery + secrets/（密钥，不入库）
├── dockerfile.base / dockerfile.venv / dockerfile.code / compose.yml
└── pyproject.toml / uv.lock
```

**依赖方向**：`llmtools → analysis → ingest → configs → assets`（单向）。`assets` 是叶子域，
`configs` 拥有全部配置行模型，`ingest` 只做采集与编排。分层由
`tests/core/test_layering.py` 的 AST 守卫兜底，架构细节见 `handbook/design/layering.md`。

## 快速开始

```bash
# 后端
uv sync --all-groups
cp envs/example/*.env envs/     # 首次：配置实例不入库（日常只改 envs/common.env）
uv run python manage.py migrate
uv run python manage.py createsuperuser
uv run python manage.py runserver

# 前端
cd frontend && pnpm install && pnpm dev
```

宿主机直跑由 `netops/settings/base.py` 自动 `load_dotenv(envs/common.env)`（非 container 再叠
`envs/host.env`），凭据见 `envs/secrets/`；完整说明在 `envs/README.md`。

### 常用运维命令

```bash
uv run python manage.py reparse              # 重跑已入库配置的解析与入库
uv run python manage.py sync_soft_assets     # 重建软资产（域名 / 负载均衡服务），加 --dry-run 只报告
uv run python scripts/purge_configs.py       # 清理配置解析产物（默认 dry-run）
```

`purge_configs` 是**独立脚本**不是管理命令（它横跨 configs / assets / analysis / core 四个域，
迁到 `scripts/` 以脱离依赖矩阵）；容器里对应 `docker compose exec app python scripts/purge_configs.py`。

### 提交前检查（git hooks）

hook 脚本随仓库走（`.githooks/`），**每台机器 clone 后跑一次**启用：

```bash
sh scripts/setup-git-hooks.sh    # 等价于 git config core.hooksPath .githooks
```

| 检查 | 触发条件 | 阻断 |
|------|----------|------|
| 冲突标记（`<<<<<<<` / `>>>>>>>`） | 有暂存文件 | 是 |
| `ruff check`（配置取自 `pyproject.toml`） | 暂存了 `.py` | 是 |
| `ruff format --check`（migrations 除外） | 暂存了 `.py` | 否，只警告（`NETOPS_HOOK_STRICT_FORMAT=1` 升级为阻断） |
| `pyrefly check`（配置 `[tool.pyrefly]`） | 暂存了 `.py` | 是（**只有落在暂存文件里的错误阻断**，其他文件的存量/WIP 报错只提示） |
| `vue-tsc --noEmit` | 暂存了 `.ts/.tsx/.vue` 且 `frontend/node_modules` 存在 | 是 |

- 没有相关暂存文件时直接退出；`pyrefly` 约 2 秒（`NETOPS_SKIP_PYREFLY=1` 跳过），前端类型检查约 6~10 秒（`NETOPS_SKIP_FRONTEND=1` 跳过）。
- `pyrefly` 先跑全项目：失败时再单独检查暂存文件，只有这批文件自己报错才拒绝提交——避免同事/自己未提交的其他文件把无关提交挡住。
- `core.hooksPath` 是相对路径，按工作区根解析——`.worktrees/` 下的 worktree 各用自己 checkout 出来的 `.githooks/`，新分支自动生效。
- 应急跳过单次检查：`git commit --no-verify`（hook 自身脚本改动用它提交，否则会被自己拦）。

### MCP 工具接口（LLM 出口）

- **端点**：`/mcp`（Streamable HTTP，官方 Python SDK 2.x，由 `netops/asgi.py` 的路径分发器挂载；`/mcp*` 走 MCP，其余走 Django）
- **反向代理**：Vite（`vite.config.ts`）与 nginx（`conf.d/netops.conf`）都已代理 `/mcp`——缺这条时请求会落到 SPA 兜底返回 `index.html`，表现是「被 Vue Router 守卫拦截跳登录」，其实根本没到 Django。新增反代层别漏。MCP 是 SSE 长连接，代理要 `proxy_buffering off` + 长读超时
- **工具**：根目录 `llmtools/`（基建 + 工具注册表，`__init__.py` 即组合根），域接入在 `llmtools/domains/network/`（`specs/` 里的 `EntitySpec`、`edges.py` 的 `EDGES`、`tools.py` 的 `locate`）；通用六工具在 `llmtools/entity_tools.py`（`find` / `list_records` / `query` / `get_record` / `bundle` / `relations`），字段口径复用各域序列化器（`assets/serializers` / `configs/serializers`）——新增表 = 注册表加一行，工具层零改动
- **本地运行与验证**（`manage.py runserver` 走 WSGI，没有 `/mcp`）：

```bash
uv run uvicorn netops.asgi:application --reload   # ASGI 入口，与生产 gunicorn+UvicornWorker 同构
uv run pytest tests/mcp/                          # 工具测试：mcp.Client 内存传输整链
```

## 部署

生产/集成环境用 `docker compose`（db / redis / code-init / app / worker / consumer / beat / nginx，nginx 为统一入口）：

```bash
cp .env.example .env            # 按需改宿主端口 / 镜像
cp envs/example/*.env envs/     # 配置实例（common / container / host / db / gunicorn / celery）
bash envs/secrets/generate.sh   # 生成数据库凭据（默认沿用旧值）
mkdir -p data                   # data 是唯一的 bind 挂载点
docker compose up -d --build    # 构建顺序见 entrypoint/README.md
docker compose up -d code-init  # 换代码镜像后必须重跑（app 挂的是 code 卷）
```

细节见三份手册：`entrypoint/README.md`（容器化构建）、`nginx/README.md`（反向代理）、`envs/README.md`（配置分层）。

## 通用组件说明

| 组件 | 用途 |
|------|------|
| `PageLayout` | 页面布局框架（标题 + 操作区 + 内容插槽） |
| `FormPage` | 表单页布局（标题 + 保存/取消 + 表单插槽） |
| `DataTable` | el-table 包装器（默认 stripe/border/height/loading + 列宽偏好） |
| `DataColumn` | 列级封装（偏好列宽 + 固定/弹性宽度档位） |
| `ColumnSettings` | 列设置（拖拽排序 / 重置 / 显隐，写入用户偏好） |
| `DataPagination` | 列表分页（页码 + 每页条数 + 总数） |
| `FilterBar` | 列表页通用过滤条（设备下拉 + 附加过滤器插槽 + 搜索框） |
| `ChartCard` | ECharts 图表卡片（autoresize） |
| `StatCard` | 数字统计卡片（支持图标、颜色） |
| `DeviceFilter` | 设备选择器（自动加载设备列表，v-model） |
| `UserBar` | 内容区顶部栏（全局搜索 + 主题切换 + 用户名 + 登出），在 `netops/layout/UserBar.vue` |

## Composables 说明

| Composable | 用途 |
|------------|------|
| `useCrudApi` | 通用 CRUD 数据管理（loading/search/filter/fetch/save/delete） |
| `useEcharts` | ECharts 按需注册 + 图表配置工厂（`pieOpt` / `barOpt` / `gaugeOpt` / `lineOpt`，另导出 `COLORS`、`lookup`、`mapItems`） |
| `useTablePrefs` | 表格列偏好（列顺序 / 宽度 / 显隐）的模块级缓存与读写，登录态切换时重置 |
| `useTagType` | Tag 颜色映射（protocolTagType/modeTagType/statusTagType） |
| `useG6` | G6 按需引入（绕过全量 preset，只注册实际使用的行为/布局/元素） |
| `useSearchSync` | 页面级共享搜索词（同页多个 tab 各持一个 `useCrudApi` 时同步 search） |

> 前端约定（类型组织、主题变量、表格列规范）与后端开发约定统一见 `AGENTS.md`。
