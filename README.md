# Network Ops

网络运维管理平台 — Django REST 后端 + Vue 3 前端

## 功能模块

| 模块 | 路由 | 功能 |
|------|------|------|
| **总览** | `/` | 全局统计仪表盘（ECharts 图表）+ 任务队列监控卡片 |
| **设备管理** | `/devices` | 设备列表、接口管理、基线管理（SNMP/NTP/Syslog）、解析器模板、配置对比 |
| **配置管理** | `/config` | 负载均衡（SLB/GSLB）、域名解析、NAT 管理、路由表、ARP/MAC、访问策略 |
| **IP 管理** | `/ipam` | 子网、IP 地址、标签管理 |
| **工具** | `/tools` | 路径追踪（防火墙策略匹配 + NAT + 路由 + 负载均衡）、机柜可视化（U 位视图） |
| **任务中心** | — | 任务/阶段管理（Celery 采集→解析→存储）、运行监控（celery / Redis / 队列积压巡检） |

## 技术栈

**后端**
- Python 3.12 / Django 6.1 / Django REST Framework
- PostgreSQL（TimescaleDB）+ Redis
- Celery 异步任务（采集→解析→存储；访问流重建）
- TTP 模板解析（设备配置 → 结构化数据入库）
- MCP Server（官方 Python SDK 2.x，`/mcp` Streamable HTTP；基建在 `apps/core/mcp/`，各域注册实体，通用工具只认注册表）

**前端**
- Vue 3 + TypeScript + Vite
- Element Plus UI
- ECharts / G6 图可视化
- Pinia 状态管理

## 项目结构

```
network_ops/
├── netops/          # Django 项目配置与基建（settings / urls / asgi / celery / pagination / mcp_server 兼容壳）
├── apps/
│   ├── core/        # 用户认证、Token、Task/Stage、前端偏好、运维命令 + MCP 基建（server/registry/query/通用工具）
│   ├── assets/      # 网络域数据模型（设备/配置/IPAM/LTM/GTM/防火墙…）+ MCP 实体声明（specs）与域专属工具（locate）
│   ├── ingest/      # 配置采集解析入库（每设备 Git 仓库 → TTP 解析 → Saver 写库）
│   ├── analysis/    # 分析与观测（路径追踪/访问流/互联网分析/队列与 Redis 巡检）
│   └── cloud/       # 云平台接入（阿里云 API 客户端 + 云资源缓存）
├── frontend/        # Vue 3 + TypeScript + Vite（src/{api,components,views,...}）
├── tests/           # pytest 测试（按应用分目录：core/assets/ingest/analysis/deploy/mcp）
├── nginx/           # 反向代理（静态直出 + /api 代理）
├── docker/          # 容器化构建手册（docker/README.md）与入口脚本
├── env/             # 容器 env 文件（app/db/gunicorn/celery）+ secrets/（密钥，不入库）
├── Dockerfile.base / Dockerfile.app / docker-compose.yml
└── pyproject.toml / uv.lock
```

## 快速开始

```bash
# 后端
uv sync --all-groups
uv run python manage.py migrate
uv run python manage.py createsuperuser
uv run python manage.py runserver

# 前端
cd frontend && pnpm install && pnpm dev
```

宿主机直跑需要自行导出数据库/Redis 环境变量（`POSTGRES_*`、`REDIS_HOST`），凭据见 `env/secrets/`；完整说明在 `env/README.md`。

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
- **工具**：`apps/assets/mcp/` 实体注册表（`entities.py` 的 `EntitySpec` / `EDGES`）+ 六个薄壳工具（`find` / `list_records` / `get_record` / `bundle` / `relations` / `locate`），字段口径复用 `assets/serializers`——新增表 = 注册表加一行，工具层零改动
- **本地运行与验证**（`manage.py runserver` 走 WSGI，没有 `/mcp`）：

```bash
uv run uvicorn netops.asgi:application --reload   # ASGI 入口，与生产 gunicorn+UvicornWorker 同构
uv run pytest tests/mcp/                          # 工具测试：mcp.Client 内存传输整链
```

## 部署

生产/集成环境用 `docker compose`（db / redis / app / worker / nginx 等，nginx 为统一入口）：

```bash
cp .env.example .env          # 按需改宿主端口 / 镜像
bash env/secrets/generate.sh  # 生成数据库凭据（默认沿用旧值）
mkdir -p data/configs         # 配置源目录（唯一需要宿主目录的挂载点）
docker compose up -d --build  # 构建顺序见 docker/README.md
```

细节见三份手册：`docker/README.md`（容器化构建）、`nginx/README.md`（反向代理）、`env/README.md`（配置分层）。

## 通用组件说明

| 组件 | 用途 |
|------|------|
| `PageLayout` | 页面布局框架（标题 + 操作区 + 内容插槽） |
| `FormPage` | 表单页布局（标题 + 保存/取消 + 表单插槽） |
| `DataTable` | el-table 包装器（默认 stripe/border/height/loading + 列宽偏好） |
| `DataColumn` | 列级封装（偏好列宽 + 固定/弹性宽度档位） |
| `ChartCard` | ECharts 图表卡片（autoresize） |
| `StatCard` | 数字统计卡片（支持图标、颜色） |
| `DeviceFilter` | 设备选择器（自动加载设备列表，v-model） |
| `UserBar` | 内容区顶部栏（全局搜索 + 主题切换 + 用户名 + 登出） |

## Composables 说明

| Composable | 用途 |
|------------|------|
| `useCrudApi` | 通用 CRUD 数据管理（loading/search/filter/fetch/save/delete） |
| `useEcharts` | ECharts 注册 + 图表配置工厂（pieOpt/barOpt/gaugeOpt） |
| `useTableHeight` | 表格高度自适应（resize 监听 + 自动清理） |
| `useTagType` | Tag 颜色映射（protocolTagType/modeTagType/statusTagType） |

> 前端约定（类型组织、主题变量、表格列规范）与后端开发约定统一见 `AGENTS.md`。
