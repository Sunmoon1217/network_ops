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
│       ├── management/commands/reparse.py  # 重跑已入库配置的解析与入库
│       ├── models.py            # InternetAnalysis（分析结果缓存）
│       └── ansible/             # ⚠️ 仅剩 __pycache__，源文件已移除
├── data/
│   ├── config_repo/     # Git 配置仓库（含 .git）
│   └── configs/
├── tests/               # 测试（按应用分目录，pytest testpaths 指向此处）
│   ├── assets/          # device_group / serializer_migration / service_unique
│   └── ops/             # parsers / parser_contract / pipeline / analysis / reparse
├── docs/compose/
├── frontend/            # Vue 3 + TypeScript + Vite
│   ├── dist/            # 构建产物（不入库，由 nginx 直接托管）
│   └── src/{api,assets,composables,layout,router,stores,ui,utils,views}
├── nginx/               # 反向代理（静态直出 + API 代理）
│   ├── conf.d/          # netops.conf(80)、netops-ssl.conf.disabled(443)
│   ├── ssl/             # TLS 证书（不入库）
│   └── gen-self-signed-cert.sh
├── www/                 # collectstatic 产物（不入库，镜像构建时 COPY 进 app）
├── tmp/
├── docker/entrypoint.sh # 应用容器入口：把镜像里的静态成品复制进命名卷（空目录挂载点）
├── Dockerfile.base      # 环境镜像（只装依赖，不含源码）
├── Dockerfile.app       # 项目镜像（源码 + 宿主机构建好的静态成品）
├── .dockerignore
├── docker-compose.yml   # db(TimescaleDB) / redis / app / worker / nginx
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
- **Celery 分阶段工作流**：采集→解析→存储三个阶段由 Celery 任务串联（`ops/tasks.py` 的 `run_collection_stage` / `run_parsing_stage` / `run_storage_stage`），`Stage` 状态回写触发下一阶段（`ops/signals.py`）。broker/backend 都是 Redis（`REDIS_HOST`/`REDIS_PORT`）。**必须有 worker 消费队列**，否则 `.delay()` 只会把消息堆在 Redis 里永远不执行——`docker-compose.yml` 里的 `worker` 服务就是干这个的。
- **DeviceConfig 的解析入库仍是同步的**：走 `ops.pipeline.run_config_pipeline`，在 `post_save` 的调用栈里跑完（见下文「配置处理流程」）。两套链路并存，别混。
- **前端托管**：`netops/views.py` 从 `frontend/dist/` 读取 `index.html` 与静态资源；`netops/urls.py` 用正则把非 `/api`、`/admin`、`/static`、`/assets`、`/media` 的请求交给 Vue 路由。
- **反向代理与容器化**：`nginx/` 作为统一入口（80/443）。`/api/*`、`/admin/*`、`/media/*` 代理到 compose 里的 **app 容器**（不再指向宿主机 Django）；`/assets/*`、`/static/*` 由 nginx 直出。两类静态资源的源头是**宿主机**（`pnpm build` + `collectstatic`），`Dockerfile.app` 把它们 COPY 进镜像的 `/app/www` 与 `/app/frontend/dist`（同时就是 Django 的 `STATIC_ROOT` / `FRONTEND`），容器启动时 `docker/entrypoint.sh` 复制**另一份**到 `www_data`/`dist_data` 两个命名卷，nginx 只读挂载。详见 `nginx/README.md`。
- **为什么必须绕一层命名卷**：nginx 是独立容器，读不到 app 镜像里的文件；跨容器共享只有卷这一条路（tmpfs 是每容器私有的内存文件系统，`--volumes-from` 也拿不到，实测过）。命名卷挂在镜像里**故意留空的** `/var/lib/netops-static/{www,dist}` 上——挂到有内容的目录会遮住镜像内容，而 Docker 只在卷首次创建时播种一次，于是「重建镜像后页面还是旧的」。入口脚本每次都**权威**重铺（先 `find -delete` 再 cp），顺带清掉上一版带 hash 的遗留资源。
- **不用 `volumes_from`**：它会把源容器的所有卷都带过来（nginx 会白拿 `app_data` 里的配置仓库），且卷在目标容器里的路径与源容器相同（nginx 只能看到 `/app/www`，配置被绑死）。显式写 `www_data:/usr/share/nginx/static:ro` 才能只读、挑卷、并放在 nginx 自己的路径上。
- **nginx 的后端地址用 `resolver` + 变量**（`set $netops_upstream "app:8000"`）而不是 `upstream` 块：`upstream` 只在启动时解析一次，app 容器重建换 IP 后会一直 502；变量形式按 `valid` 周期重解析，也让 `nginx -t` 脱离 compose 网络能通过。
- **改动基础镜像的时机**：`pyproject.toml` / `uv.lock` 变了（例如新增 celery）必须重建 `Dockerfile.base`，否则项目镜像会在运行期才报 `ModuleNotFoundError`。`Dockerfile.base` 的冒烟自检清单要与 `dependencies` 对齐，就是为了让这种问题在基础镜像构建时就暴露。
- **代理感知配置**：`SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")` 让 Django 识别 nginx 传来的原始协议；`ALLOWED_HOSTS` 由环境变量 `DJANGO_ALLOWED_HOSTS` 控制（默认 `*`）。
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
- **导入服务器负责人**：`python manage.py import_server_owners --file x.xlsx`（sheet `servers`，列 `hostname` / `ip` / `owner`，另有 `--sheet` / `--dry-run`）。**按列名取而不是按位置**——表头可以换序、可以夹带无关列，缺列直接报错并列出实际表头，避免把 `ip` 静默串到 `hostname` 上。`ip` 是唯一键（导入时用 `ipaddress` 规范化，`2001:DB8::1` 与 `2001:db8::1` 落同一条），文件内重复取最后一行；更新**只覆盖 hostname / owner，不动 `status`**（这份表没有 status 列，不能把手工停用的记录导成启用）。有非法行时**整批不导入**并以非零退出码收尾，不做「写一半再报错」。
- **「负责人」列**：按链路**最后的 IP**反查 `ServerOwner`，回退顺序是 `slb_member_address → llb_member_address → gtm_ip`（见 `_final_ip`）。匹配前两边都过 `_normalize_ip`，否则 `2001:DB8::1` 与压缩写法对不上。负责人**不进分析缓存**——它挂在 `build_path_rows`/`GET` 响应上现查，改了负责人不必重跑分析。前端表格自己扁平化、拿不到数据库，所以 GET 响应额外给一份 `owners`（键是链路最后 IP 的**原始写法**，与前端用同一份回退规则取值），避免在 JS 里重实现 IPv6 规范化。
- `Topology` 是单模型，图数据存于 `graph_data` JSON 字段，没有独立的节点/边表。
- `Device` 没有 `address` 字段，地址信息在 `DeviceConnection` 中。
- 操作层应用目录名为 `ops`（避免与 Python 标准库 `operator` 冲突）。
- 前端拓扑图使用 `@antv/g6` 5.x。

## 语言约定

- **思考过程用中文展示**：Agent 的分析、推理、解释等思考过程必须使用中文输出。
- 代码注释、commit message、PR 描述等技术文档使用中文。
