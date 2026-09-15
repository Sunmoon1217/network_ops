# AGENTS.md

## 项目概述

网络运维管理平台：Django REST 后端 + Vue 3 前端。

后端提供数据模型与 REST API，负责设备配置的解析与入库。前端构建产物默认可由 Django 直接托管（便于开发调试）；生产/集成环境则使用 `nginx/` 作为统一入口，静态资源直出、`/api` 反向代理到 Django。

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
│   ├── assets/          # 全部数据模型（单文件，38 个模型）
│   │   ├── models.py
│   │   └── api/{serializers.py, urls.py, views.py}
│   └── ops/             # 操作层：解析、存储、路径追踪
│       ├── api/{configs.py, parsers.py, trace.py, urls.py}
│       ├── parsers/factory.py + tmpls/{configs,running}/
│       ├── savers/{base,registry,interface,lb,firewall,routing}.py
│       ├── config_repo.py       # Git 配置仓库管理
│       ├── path_tracer.py       # 路径追踪算法
│       ├── signals.py           # DeviceConfig 保存后的解析与入库
│       ├── models.py            # 空文件
│       └── ansible/             # ⚠️ 仅剩 __pycache__，源文件已移除
├── data/
│   ├── config_repo/     # Git 配置仓库（含 .git）
│   └── configs/
├── docs/compose/
├── frontend/            # Vue 3 + TypeScript + Vite
│   ├── dist/            # 构建产物（不入库，由 nginx 直接托管）
│   └── src/{api,assets,composables,layout,router,stores,ui,utils,views}
├── nginx/               # 反向代理（静态直出 + API 代理）
│   ├── conf.d/          # netops.conf(80)、netops-ssl.conf.disabled(443)
│   ├── ssl/             # TLS 证书（不入库）
│   └── gen-self-signed-cert.sh
├── www/                 # collectstatic 产物（不入库，由 nginx 直接托管）
├── tmp/
├── docker-compose.yml   # db(TimescaleDB) / redis / nginx
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
| `POSTGRES_DB` | `netops` | 数据库名 |
| `POSTGRES_USER` | `netops` | 数据库用户 |
| `POSTGRES_PASSWORD` | `netops_password` | 数据库密码 |
| `POSTGRES_HOST` | `localhost` | 数据库主机 |
| `POSTGRES_PORT` | `5432` | 数据库端口 |
| `DJANGO_ALLOWED_HOSTS` | `*` | 逗号分隔，映射到 `ALLOWED_HOSTS`；无域名阶段默认放开 |

> 项目中**不存在** `.env` / `.env.example`，配置直接来自环境变量。

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
- **模型集中**：`assets` 的所有模型都在单文件 `apps/assets/models.py`，没有 models 子目录。
- **应用注册**：`core.apps.CoreConfig`、`ops.apps.OperatorConfig`、`assets.apps.AssetsConfig`。
- **无 Celery / 无任务队列**：所有处理在请求周期内同步完成。
- **前端托管**：`netops/views.py` 从 `frontend/dist/` 读取 `index.html` 与静态资源；`netops/urls.py` 用正则把非 `/api`、`/admin`、`/static`、`/assets`、`/media` 的请求交给 Vue 路由。
- **反向代理**：`nginx/` 作为统一入口（80/443）。静态资源由 nginx 直出：`/assets/*` → `frontend/dist`，`/static/*` → `www`（collectstatic 产物）；`/api/*`、`/admin/*`、`/media/*` 代理到宿主机 Django。详见 `nginx/README.md`。
- **代理感知配置**：`SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")` 让 Django 识别 nginx 传来的原始协议；`ALLOWED_HOSTS` 由环境变量 `DJANGO_ALLOWED_HOSTS` 控制（默认 `*`）。
- **前端请求路径**：以 `/api/` 开头（如 `/api/assets/devices/`）。
- **前端自动导入**：使用 `unplugin-auto-import` + `unplugin-vue-components`（`ElementPlusResolver`）。
- **前端函数风格**：`.vue` 与 `.ts` 一律使用箭头函数，不使用 `function` 声明——普通函数 `const fn = (a: T) => {}`、异步 `const fn = async () => {}`、泛型 `const fn = <T>(a: T) => {}`。原因是 `function` 声明会被提升，容易掩盖定义顺序问题，也与项目既有写法保持一致。自检命令（应无输出）：
  `grep -rnE "^[ \t]*(export )?(async )?function [A-Za-z_$]" frontend/src --include=*.ts --include=*.vue`
- **Ruff**：`line-length = 120`；`select = ["E","F","I","N","W"]`，忽略 `F405/F403/E402`；`known-first-party = ["assets","core","ops"]`；`**/migrations/*` 忽略 `E501`，并通过 `[tool.ruff.format]` 排除（Django 生成的迁移文件不参与格式化）。
- **测试**：pytest + pytest-django，`DJANGO_SETTINGS_MODULE = "netops.settings"`。

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
| 设备 | Vendor, DeviceModel, Device, DeviceConnection, DeviceConfig, DeviceAccount |
| 配置基类 | `ConfigBase`（被 Vrf/Interface/LTM/GTM/防火墙等模型继承） |
| 网络 | Vlan, Vrf, Interface, SnmpConfig, NtpConfig, SyslogConfig |
| 负载均衡 LTM | LtmVirtualServer, LtmPool, LtmPoolMember, LtmProfile, LtmIRule, LtmSNAT, LtmPersist |
| 全局负载均衡 GTM | GtmDatacenter, GtmWideip, GtmPool |
| 防火墙 | AddressBook, Service, Policy, NatRule |
| IPAM | Tag, Subnet, IPAddress, SubnetUsageLog |
| 路由与其它 | Route, Topology, ArpMac |

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

**已注册解析器**（`@ParserFactory.register`）：

`A10/loadbalancer`、`Cisco/firewall`、`F5/loadbalancer`、`F5/loadbalancer_ltm`、`H3C/switch`、`H3C/router`、`Hillstone/firewall`、`Huawei/switch`

**Saver 实现**：InterfaceSaver、VrfSaver、LBVirtualServerSaver、LBPoolSaver、LBSnatSaver、GTMWideipSaver、AddressBookSaver、ServiceSaver、PolicySaver

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

## API 路由

`netops/urls.py` 依次 include 三个应用的 urls，全部挂载在 `/api/` 下。

**core**（`core/api/urls.py`）

| 路径 | 说明 |
|------|------|
| `/api/auth/login/` | 登录获取 Token |
| `/api/auth/logout/` | 登出 |
| `/api/me/` | 当前用户信息 |

**assets**（`assets/api/urls.py`，前缀 `/api/assets/`）

DRF `SimpleRouter`（`trailing_slash=True`），资源列表：

```
security-zones, datacenters, rooms, cabinets,
vendors, device-models, devices, device-configs, device-connections, device-accounts,
vlans, vrfs, interfaces,
snmp-configs, ntp-configs, syslog-configs,
ltm-virtual-servers, ltm-pools, ltm-pool-members, ltm-profiles, ltm-irules, ltm-snats, ltm-persists,
gtm-datacenters, gtm-wideips, gtm-pools,
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

## 注意事项

- **⚠️ 已知缺陷：`ops/api/configs.py` 与 `ops/api/parsers.py` 的视图未注册路由。**
  两模块定义了 `git_content`、`git_diff`、`config_history`、`config_devices`、`parser_list`、
  `parser_template_list`、`parser_template_detail`、`parser_template_update` 等视图，但
  `ops/api/urls.py` 只注册了 trace 相关路由。而前端 `api/config.ts`、`api/parsers.ts` 已在调用
  `/api/configs/*` 与 `/api/parsers/*`，因此这些功能当前会 404。
- **列表分页与搜索排序**：DRF 全局启用数字分页（`netops/pagination.py` 的 `StandardPagination`，默认 50 条/页、最大 500 条，客户端可用 `?page_size=` 覆盖），列表接口返回 `{count, next, previous, results}`；`DEFAULT_FILTER_BACKENDS` 启用 `SearchFilter` / `OrderingFilter`，各 ViewSet 通过 `search_fields` / `ordering_fields` 声明可用字段。前端统一用 `useCrudApi` + `DataPagination` 消费；必须全量的场景（下拉选项、前端聚合统计）用 `fetchAllPages`。时序大表（ARP/MAC、路由、子网使用率）后续可单独启用游标分页。
- **`apps/ops/ansible/` 只剩 `__pycache__`**，源文件已删除，属重构残留。
- `apps/ops/models.py` 为空文件。
- `Topology` 是单模型，图数据存于 `graph_data` JSON 字段，没有独立的节点/边表。
- `Device` 没有 `address` 字段，地址信息在 `DeviceConnection` 中。
- 操作层应用目录名为 `ops`（避免与 Python 标准库 `operator` 冲突）。
- 前端拓扑图使用 `@antv/g6` 5.x。

## 语言约定

- **思考过程用中文展示**：Agent 的分析、推理、解释等思考过程必须使用中文输出。
- 代码注释、commit message、PR 描述等技术文档使用中文。
