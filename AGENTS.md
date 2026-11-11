# AGENTS.md

> 本文件是**约定与入口**：能一眼看完的规则写在这里，细节一律放 `handbook/`（索引见
> [`handbook/README.md`](handbook/README.md)）。第三方软件的实测行为放 `.dsh/skills`（见「知识库」）。
> 写代码或改注释前，先看「关键约定」与对应域的那份 handbook。

## 项目概述

网络运维管理平台：Django REST 后端 + Vue 3 前端。

后端提供数据模型与 REST API，负责设备配置的解析与入库，并经 `ingest/collectors/` 接入外部数据
源（Zabbix / Autotask）给总览大屏供数。前端构建产物默认可由 Django 直接托管（便于开发调试），
Vite 另打一个**大屏入口**（`index.html` 主站 / `dashboard.html` 大屏）。生产/集成环境用
`docker compose` 起 db / redis / code-init（一次性，把代码与静态成品铺进命名卷）/ app / worker /
consumer / nginx，由 `nginx/` 作为统一入口（静态资源直出，`/api`、`/mcp` 反向代理到 app 容器）。
宿主直跑用 `scripts/deploy-host.sh`（app / worker / consumer 三进程），与容器共用 `envs/*.env`。

## 项目拓扑

```
外网远程开发 <--git--> 托管平台 <-- 代理git --> 内网开发 | 内网沙箱 <--ssh--> 内网服务器
```

- 代码以托管平台为汇聚点（外网侧直接 push / pull）；
- 内网不能直连外网托管平台，经**代理 git** 同步；
- 内网开发 / 内网沙箱 ↔ 内网服务器走 **ssh**（部署、调试、远程执行都在内网服务器上）。

## 项目结构

```
network_ops/
├── netops/              # 项目配置：settings/（base 集中 env 动态项 + dev/container/prod 三个环境文件）、urls、asgi、lifespan（ASGI 握手）、views、schema（外部 DTO 基类）
├── apps/
│   ├── core/            # 用户与认证、Task/Stage 模型、运维命令（ensure_superuser / migrate_if_needed / queue_*）
│   ├── assets/          # 网络域数据模型（单文件 models.py）+ 序列化器 + API + Excel 导入
│   ├── ingest/          # 采集与解析入库：parsers(TTP) / savers / mapping / pipeline / workflow / config_repo + collectors/（外部数据源：zabbix / autotask / 大屏编排）
│   ├── analysis/        # 只读消费侧：路径追踪、策略展开与访问流、互联网资产分析、运行监控、大屏供数；**models/ 是包**（不是单文件）
│   ├── cloud/           # 阿里云接入：客户端封装 + 云资源缓存（暂无对外 API）
│   └── docs/            # **功能域**：表格编辑 + 文档转换 + Dify 推送（app label 就是 docs，与 handbook/ 无关）
├── llmtools/            # MCP 工具子系统（根目录包、非 app）：server / registry / query / entity_tools / tools / domains
├── frontend/            # Vue 3 + TS + Vite，双入口（index.html / dashboard.html）；src/{shared,netops,dashboard} 三层，dist/ 由 nginx 直出
├── nginx/               # 反向代理（静态直出 + API/MCP 代理 + 启动时的 resolver 推导）
├── entrypoint/          # 容器入口脚本（code_init / app / worker / consumer）+ README（**容器化构建手册**）
├── envs/                # 容器与宿主共用的一套配置：common.env 共享 + container/host.env 差异 + gunicorn/celery.env + secrets/（凭据，不入库）
├── handbook/            # 设计说明（长解释的家，见 handbook/README.md）；不入镜像
├── scripts/             # deploy-host.sh（宿主 app/worker/consumer 三进程）+ switch-branch / setup-git-hooks
├── tests/               # 按应用分目录，pytest testpaths 指向此处
├── typings/             # 第三方库存根（zabbix_utils 等；pyrefly 的 site-packages-path）
├── data/                # 运行期数据（不入库）：config_repo（宿主直跑那份）、configs（Excel 源目录，只读 bind 进 app）、run/logs
├── dockerfile*          # .base（只装系统依赖）/ .venv（uv sync）/ .code（源码 + 静态成品）/ 传统 dockerfile（备选）
├── compose.yml          # db(TimescaleDB) / redis / code-init / app / worker / consumer / nginx
└── pyproject.toml       # 依赖、pytest、ruff、pyrefly 配置
```

**依赖方向**：`llmtools → apps`，`analysis → ingest → assets`（单向）。
`assets` 不许 import `ingest`；`ingest` 除 `purge_configs` 这类跨域运维工具外不许 import
`analysis`；`llmtools` 的子模块不许 import 任何业务域（`domains/` 是唯一例外）。

## 文档地图

| 想知道 | 看 |
|--------|-----|
| 全是 HTTP 接口 / 认证与注册约定 / 分页搜索 | [`handbook/api.md`](handbook/api.md) |
| 部署、容器、nginx、卷、健康检查、凭据、镜像 | [`handbook/deploy.md`](handbook/deploy.md) |
| settings 分层、环境变量全表、守卫矩阵 | [`handbook/settings.md`](handbook/settings.md) |
| 采集/解析/入库链路、阶段推进、Saver 契约、并发与性能 | [`handbook/ingest.md`](handbook/ingest.md) |
| 路径追踪、访问流、资产分析、队列监控 | [`handbook/analysis.md`](handbook/analysis.md) |
| 资产模型与导入、admin 约定 | [`handbook/assets.md`](handbook/assets.md) |
| 文档转换规则与 Dify 推送 | [`handbook/docs-domain.md`](handbook/docs-domain.md) |
| MCP 工具子系统 | [`handbook/llmtools.md`](handbook/llmtools.md) |
| 阿里云接入 | [`handbook/cloud.md`](handbook/cloud.md) |

## 知识库（跨会话共享的实测结论）

第三方软件（Docker / docker compose、容器里的 git / GitPython、Django / DRF、nginx、容器健康
检查与凭据、uv）的**实测行为**不写在本文件里，而是**用户级技能**（全局目录、跨项目）：

- 事实源：**`~/.dsh/skills/<name>/SKILL.md`**（它自身是一个 git 仓库，跨机器共享就 push + clone；
  `~/.dsh/skills/_about/README.md` 有同一套规矩）
- 本项目的 `.dsh/skills/<name>` 只是**软链**，`.dsh/` 同时写在 `.gitignore` 与 `.dockerignore` 里
  ——不入库、不进镜像，换机器 clone 也不会留下断链
- 技能目录清单自动进每个会话（name + description），正文按需加载（`skill` 工具或 `/name`）

| 技能 | 覆盖 |
|------|------|
| `docker-compose-behavior` | 插值只读根 `.env`、`$$` 转义、`up -d --build` 不换容器、`run/exec` 与 entrypoint 的 `$1` 约定、`down -v` 与残留卷 |
| `docker-mounts-and-ownership` | bind vs 命名卷的属主/权限、镜像里 chmod 是死代码、uid 映射、`:ro` 的 EROFS |
| `git-in-containers` | 提交身份（root 也一样失败）、dubious ownership 与 `safe.directory`、`getpwuid` KeyError |
| `django-drf-gotchas` | `SessionAuthentication` 自己调 `enforce_csrf()`、迁移命名锁、`Path` 按 CWD 解析、pytest 资源定位 |
| `container-healthchecks` | healthcheck 的执行用户、`pg_isready -U`、`celery inspect -d`、`--noproxy '*'`、secrets vs 环境变量 |
| `nginx-container-proxy` | `resolver` 推导、变量式 upstream、envsubst 静默失效、`$http_host`、静态卷布局 |
| `uv-package-and-lockfile` | uv 不读 pip 配置（只有 `UV_DEFAULT_INDEX` 有效）、`uv.lock` 固化 registry、依赖层镜像的重建时机 |
| `ttp-template-gotchas` | 模板按 **XML** 解析（注释里的尖括号会炸）、`re()` 可内联正则、**单条命中给 dict / 多条给 list**、内置 `IPV6` 不含点号 |
| `frontend-types` | 具名类型进 `src/shared/types/` + barrel、撞名语义化改名、`.ts` / `.d.ts` 分工 |
| `git-branch-flow` | **本仓分支模型**：feature 从 `develop` 切、一需求一分支、**新分支用 worktree 建在 `.worktrees/`**、每个改动及时 commit、**除非用户要求不合并** |
| `product-roadmap` | **项目本地**技能：产品功能开发列表（四阶段 18 项 + MCP 路线 + 硬约束） |

写新技能两条规矩：① frontmatter 的 `description` / `whenToUse` 用 `>-` 折叠块（值里出现半角
`: ` 会让 YAML 解析失败，整条技能被丢弃）；② 加完用 `skill` 工具加载一次确认能读出来；文件夹是
每个目录一个 `SKILL.md`（嵌套的不会被发现）。改完记得在**全局那个仓库**提交。

## 环境搭建

需要 Python >= 3.12，用 `uv` 管理包。

```bash
uv venv --python 3.12
uv sync --all-groups          # 主依赖 + dev + test
cp envs/example/*.env envs/   # 首次：配置实例不入库，模板入库（日常只改 envs/common.env）
cd frontend && pnpm install
```

数据库是 **PostgreSQL**，配置走环境变量（全表见 [`handbook/settings.md`](handbook/settings.md)）。
配置分三处：根 `.env` 只给 compose 插值（`cp .env.example .env`）；`envs/*.env` 是容器与宿主
**共用的一套**（`common` 共享 + `container`/`host` 差异 + `gunicorn`/`celery` 服务旋钮）；
`envs/secrets/*` 只读挂载给凭据（见 `envs/README.md`）。宿主直跑时 `base.py` 自己
`load_dotenv(envs/common.env)`，非 container 再叠 `envs/host.env`（`override=False`，真实进程
环境变量永远优先；`NETOPS_SKIP_DOTENV=1` 全跳过，`tests/deploy` 用它拿纯净默认值）。
凭据链 `*_FILE > 同名环境变量 > 默认值`，`*_FILE` 在容器里指向 `/run/secrets/*`。

## 常用命令

```bash
# 后端（项目根）
uv run python manage.py migrate | createsuperuser | runserver
uv run python manage.py queue_status   # 队列积压巡检（--json；超阈值退出码 1，可接 cron）
uv run python manage.py queue_backlog  # 积压明细（--json / --limit）
uv run python manage.py reparse | purge_configs | import_server_owners   # 见 handbook/ingest.md
uv run python manage.py rebuild_access_flows --device <H> [--sync]
./scripts/deploy-host.sh deploy | status   # 宿主直接部署：app / worker / consumer 三进程

# 前端（frontend/）
pnpm dev | build | type-check

# 容器（换代码镜像后必须先重跑 code-init：app 挂的是 code 卷，不是镜像里的 /app）
docker compose up -d code-init && docker compose up -d

# 质量
uv run pytest                                   # 单进程；排查单个文件时用它
uv run pytest -n auto --dist loadfile           # 全量：多进程（每个 worker 建自己的 test_netops_gwN）
uv run ruff check ; uv run ruff format ; uv run pyrefly check
```

> 跑测试时加 `-v --tb=short`：命令输出不是流式的（进程结束才回显），只有 `-v` 才能看出逐条
> 用例与百分比；范围大就按 `tests/<域>` 拆开跑。`-n` 需要数据库账号有 createdb 权限（dev 的
> `netops` 是超级用户，已具备）；Windows 上 `test_reparse_command` 两个 fork 用例本来就红。
> xdist 并行时 `-v` 仍是逐条输出（`[gwN] [ 12%] PASSED ...`），**不要混 `-q`**（会退化成每
> worker 的字符进度）。要在运行**过程中**看进度，就让 pytest 跑在独立进程里写日志再 tail：
>
> ```powershell
> $log = "$env:TEMP\netops_pytest.log"
> Start-Process .\.venv\Scripts\python.exe -ArgumentList "-m","pytest","-n","auto","--dist","loadfile","-v" `
>   -RedirectStandardOutput $log -RedirectStandardError "$env:TEMP\netops_pytest.err" -NoNewWindow
> Get-Content $log -Tail 8        # 反复执行即可看到实时百分比
> ```
>
> 别用 `| Select-Object -First N` 截 pytest 输出：管道提前关闭会杀掉进程、留下脏测试库。

## 关键约定

> 只写本项目自己的约定（路径、服务、旋钮、契约）。第三方软件的实测行为在 `.dsh/skills`，
> 部署侧的硬要求与代价在 [`handbook/deploy.md`](handbook/deploy.md)，这里只留「会被踩坏的那一句」。

- **settings 分层**：可被环境变量影响的配置**只在 `base.py` 定义一遍**（靠注入不同的值区分环境）；
  三个环境文件只放硬差异——`dev.py` 空壳、`container.py` 两条 host 必填守卫（env_file 误删一行时
  启动即拒，而不是等首个请求 connection refused）、`prod.py` `DEBUG=False` 硬覆盖 + 5 项守卫。
  环境旋钮唯一 `DJANGO_ENV`（不设 → dev，白名单，拼错拒启动），`DJANGO_SETTINGS_MODULE` 恒为
  `netops.settings`。`base.py` 与三个环境文件**禁止** `from netops.settings import ...` /
  `from . import ...`（半初始化时会炸）。细节：[`handbook/settings.md`](handbook/settings.md)。
- **`.env` / `envs/*.env` 里含 `$` 或 `#` 的值一律用单引号**（compose 会插值 `$`，`#` 前有空格即
  注释，双引号不保护 `$`）。技能 `docker-compose-behavior`。
- **模型集中**：`assets` 的所有模型在单文件 `apps/assets/models.py`（没有 models 子目录）。
  `analysis` 相反，**是 `models/` 包**（`access_flow` / `internet_analysis` / `dashboard` +
  `__init__.py` re-export）——不能同时留 `models.py` 与 `models/`（包优先，单文件被静默忽略）。
- **应用注册**：`core.apps.CoreConfig`、`ingest.apps.OperatorConfig`（label 仍是 `operator`）、
  `assets.apps.AssetsConfig`、`analysis.apps.AnalysisConfig`、`cloud.apps.CloudConfig`、
  `docs.apps.DocsConfig`；另加 `drf_spectacular` / `drf_spectacular_sidecar`（OpenAPI 文档）。
- **四条 Celery 链**：① 阶段式工作流（`/api/tasks/` 是唯一入口，采集→解析→存储由 `Stage`
  状态回写推进）；② 批量导入配置（`.si()` 串 `run_config_parsing → run_config_storage`）；
  ③ 访问流重建（`ACCESS_FLOW_TASK` 字符串投递 → 独立队列 → 单写者 consumer）；
  ④ 大屏供数（`ingest.collect_dashboard` 采集 → `DASHBOARD_WRITE_TASK` 投递 →
  `analysis.write_dashboard` 唯一写库；仓库内没有 beat/定时配置，调度在外部）。
  broker/backend 都是 Redis，**必须有 worker 消费**。链路细节与坑：
  [`handbook/ingest.md`](handbook/ingest.md)、[`handbook/analysis.md`](handbook/analysis.md)。
- **采集器边界**：`ingest/collectors/` 只做「调外部接口 → 归一成可 JSON 序列化的 dict」
  （Zabbix / Autotask，DTO 用 pydantic + `netops.schema.ExtraModel`），**不碰数据库、不 import
  `analysis`**；连接配置在 `settings.ZABBIX_CONFIG`（Token 优先于用户名密码）。
- **OpenAPI 3 文档**：`netops/urls.py` 挂 `/api/schema/`、`/api/schema/swagger-ui/`、
  `/api/schema/redoc/`（**不叫 `/api/docs/`**，那是 docs 业务域）；UI 资源走 sidecar（内网不通外网），
  权限由 `DJANGO_API_DOCS_REQUIRE_LOGIN` 控制（默认放开）。见 [`handbook/api.md`](handbook/api.md)。
- **业务日志**：`settings/base.py` 的 `LOGGING` 只给项目命名空间（`core/ingest/assets/analysis/
  cloud/docs/llmtools/netops`）装 stderr handler，级别 `DJANGO_LOG_LEVEL`（默认 INFO）；**不动
  root**（celery 会 hijack）、`propagate` 保持 True（`caplog` 仍可捕获）。
- **DeviceConfig 解析入库默认同步**（`pipeline.run_config_pipeline` 在 post_save 调用栈里跑完）；
  **例外是批量导入**（挂 `_defer_pipeline` 后投 celery 链）。两套链路并存，别混。
- **部署**：nginx 是统一入口；静态资源走「宿主机构建 → 镜像 COPY → `code-init` 铺进命名卷 →
  nginx 只读挂载」（**换代码镜像或改源码后必须重跑 `code-init`**：app 挂的是 `code` 卷，不是镜像里的
  `/app`）；仓库卷 `repo` 是**命名卷**、`data` 是**只读 bind**（首次部署先 `mkdir -p data`）。两条硬
  要求：nginx 用**变量式** upstream + 启动时推导 `resolver`、conf.d 必须 `$http_host` 透传 Host
  （否则后台登录 403）。容器启动四步、健康检查、凭据、镜像重建时机：
  [`handbook/deploy.md`](handbook/deploy.md)。
- **代理感知**：`SECURE_PROXY_SSL_HEADER` 让 Django 识别 nginx 传来的原始协议；`ALLOWED_HOSTS`
  默认 `*`；`DJANGO_CSRF_TRUSTED_ORIGINS` 正常拓扑**留空即可**。
- **「账号密码换 token」的接口必须 `@authentication_classes([])`**（login / register），否则带
  `sessionid` 打过来会被 DRF 拦成 403；注册只创建普通账号。见 [`handbook/api.md`](handbook/api.md)。
- **前端**：请求路径以 `/api/` 开头；自动导入用 `unplugin-auto-import` + `unplugin-vue-components`；
  图表用 `@antv/g6` 5.x。
- **前端三层目录**：`src/shared/`（跨应用公共层，别名 `@`）、`src/netops/`（主站，别名 `@netops`）、
  `src/dashboard/`（大屏，别名 `@dashboard`）。两个入口共用 `src/main.ts`，按页面里的 `#app` /
  `#dashboard` 各自建 app + pinia + router；**共享层不许反向 import 两个应用**。
- **`auto-imports.d.ts` / `components.d.ts` 不入库，但 `vue-tsc` 必须要它们**：两个文件由 vite
  插件在 **buildEnd** 写出，所以 `pnpm build` 是「先打包、后类型检查」的单次构建
  （`vite build && vue-tsc --noEmit`）——别改成先 `vue-tsc`，新 clone 上会因缺声明报
  "Cannot find name"。要单独补声明用 `pnpm gen-dts`（`vite build --mode gen-dts`，产物丢
  `node_modules/.cache`、不碰 `dist`）；`pnpm type-check` 与 `.githooks` 只在**文件缺失**时
  自动补（`scripts/ensure-dts.mjs`），避免多跑一遍打包。dev 服务器写不全 `components.d.ts`
  （只覆盖被请求到的模块），别拿它当生成手段。**改插件配置（imports / resolvers）后**记得
  `pnpm gen-dts`。
- **前端函数风格**：`.vue` / `.ts` 一律箭头函数，不用 `function` 声明。自检（应无输出）：
  `grep -rnE "^[ \t]*(export )?(async )?function [A-Za-z_$]" frontend/src --include=*.ts --include=*.vue`
- **前端类型集中**：具名 `interface` / `type` / `enum` 全在 `frontend/src/shared/types/`（按域分文件 +
  `index.ts` barrel），一律 `import type { ... } from '@/types'`；业务文件不落具名类型定义、不做中转
  导出；barrel 撞名**语义化改名**（别用下划线避让）；`types/index.ts` 用 `.ts` 不是 `.d.ts`。
  大屏自有类型在 `src/dashboard/types/`。细节与坑：技能 `frontend-types`。
- **前端颜色禁用硬编码**：UI 颜色只用 `var(--el-*)`（否则暗色主题不跟随）。三类例外保留字面量：
  图表/数据系列色（echarts / G6 canvas 不读 CSS 变量）、品牌主色 `#34c8ff`、主题变量定义源头
  （`netops/stores/theme.ts`）。`var(--el-bg-color, #fafafa)` 的 fallback 不算硬编码。
- **表格列宽偏好只认注册表**：key 集中在 `frontend/src/shared/constants/tableKeys.ts`（`TABLE_KEYS`），
  页面只传 `<DataTable :table-key="TABLE_KEYS.xxx">`，不自己调 `useTablePrefs` / `widthFor`；
  后端 `/api/me/preferences/` 只是按用户存取的不透明 JSON KV。改 key 走 `TABLE_KEY_RENAMES`。
- **表格列一律 `<DataColumn>`**，不裸写 `el-table-column`：列 key 解析偏好宽度、内容列走
  `min-width` 参与富余空间分配、锚点列（`anchor` 或 `fixed`）用固定 `width`。
- **Ruff**：`line-length = 180`，`select = ["E","F","I","N","W"]`，忽略 `F405/F403/E402`；
  `**/migrations/*` 忽略 `E501` 且不参与格式化。
- **提交前检查（git hooks）**：hook 随仓库走（`.githooks/pre-commit`），首次需
  `sh scripts/setup-git-hooks.sh`（clone 后不跑 = 没有检查）。只检查**暂存文件**：冲突标记、
  `ruff check`、`ruff format --check`（只警告，`NETOPS_HOOK_STRICT_FORMAT=1` 才阻断）、
  `pyrefly check`（阻断；`NETOPS_SKIP_PYREFLY=1` 跳过）、暂存的 `.ts/.tsx/.vue` 跑
  `vue-tsc --noEmit`（阻断；`NETOPS_SKIP_FRONTEND=1` 跳过）。改 hook 自身要
  `git commit --no-verify`。
- **测试**：pytest + pytest-django，`testpaths = ["tests"]`，统一放 `tests/<应用>/`（应用目录下
  不留脚手架的 `tests.py`——pytest 不收集该文件名）。**测试内资源定位**用包路径
  （`Path(ingest.__file__).parent / ...`）或 `settings.BASE_DIR`，**不要** `Path(__file__).parent.parent`
  ——依赖测试文件自身位置，目录一挪就静默失效。
- **提交与分支**：commit message / 注释 / 文档用中文；分支模型见技能 `git-branch-flow`
  （feature 从 `develop` 切、新分支用 `.worktrees/`、**除非用户主动要求不做合并**）。

## 三层架构

| 层 | 职责 | 细节 |
|----|------|------|
| `core/` | 用户与认证、`Task` / `Stage`、运维命令（积压巡检命令也在这里，跨域 import 采集） | [`handbook/api.md`](handbook/api.md) |
| `assets/` | 网络域数据模型（`ConfigBase` 基类）+ 序列化器 + API + Excel 导入 | [`handbook/assets.md`](handbook/assets.md) |
| `ingest/` | 采集、TTP 解析、Saver 写库、Git 配置仓库；三阶段工作流与访问流 / 大屏投递触点；`collectors/` 接外部数据源 | [`handbook/ingest.md`](handbook/ingest.md) |
| `analysis/` | 路径追踪、策略展开 / 访问流、资产分析、队列与运行监控、大屏供数（只读消费，写自己的派生缓存） | [`handbook/analysis.md`](handbook/analysis.md) |
| `cloud/` | 阿里云客户端封装 + 云资源缓存（暂无对外 API） | [`handbook/cloud.md`](handbook/cloud.md) |
| `docs/`（app） | 表格编辑 + 文档转换 + Dify 推送 | [`handbook/docs-domain.md`](handbook/docs-domain.md) |
| `llmtools/` | MCP 工具出口（根目录包，与 `api/` 平行） | [`handbook/llmtools.md`](handbook/llmtools.md) |

## 注意事项

- **解析器 / Saver / 模型的三层关联**：解析器按 `(vendor, device_type)` 产出**原始**键 →
  `ingest.mapping` 归一（键别名 + 字段别名，纯函数、幂等、**无厂商维度**）→ Saver 按
  `(device_type, key)` 消费、以 `model_paths` 声明写入的模型。归一住在 `BaseSaver.save`（模板
  方法），值语义与结构级差异留 Saver——声明表只做纯改名。契约测试
  `tests/ingest/test_parser_contract.py` + `test_mapping.py`；清单接口 `/api/parsers/mapping/`。
  细节：[`handbook/ingest.md`](handbook/ingest.md)。
- **解析器模板管理页面**（`frontend/src/netops/views/devices/parsers.vue`）以**模板文件**为中心单表
  展示，解析器降级为「关联解析器」列。
- **`parsers/tmpls/running/` 的模板不在 `ParserFactory` 注册表内**（`route.ttp` / `arp.ttp` /
  `mac.ttp` / `lldp.ttp` / `h3c_route.ttp`），由路径追踪 / 路由采集接口按名称动态调用——页面上
  「未关联解析器」不代表可删。
- **TTP 模板引擎**：① 模板按 **XML** 解析，注释里写尖括号（`<vars>` / `<group>`）会整模板炸；
  ② `re()` 可以**内联写正则**；③ **单条命中给 `dict`、多条给 `list`**，消费方两种都要兼容；
  ④ 内置 `IPV6` 不含点号。技能 `ttp-template-gotchas`。
- **F5 池成员端口分隔符有两种**：普通串 / IPv4 用冒号（`/Common/node:80`），名字本身是 IPv6 字面量
  时用一个点号（`/Common/2001:db8::1.80`）——所以 `f5_ltm.ttp` 有两条备选行，且端口必须限成纯数字，
  否则冒号那条会把 IPv6 成员贪婪切开、永远轮不到回退行。
- **互联网资产分析走缓存**：只有 `POST /api/internet-analysis/analyze/` 才计算，查询与导出只读
  `InternetAnalysis`（未分析过 404）。表格列、`#` 分隔符与负责人回退顺序：
  [`handbook/analysis.md`](handbook/analysis.md)。
- **`ingest` 的 app label 是 `operator`**（`OperatorConfig.label`）：migrate 时用 `operator`；拆分只
  动 Python 路径、**不动 label**（迁移历史挂在它上面，改 label 会让 `django_migrations` 对不上）。
- **改 celery 任务名要按部署步骤走**：Redis 里未消费的旧名消息会 `Unknown task`——升级前停 worker、
  清空对应队列再滚动。
- **清理配置数据用 `manage.py purge_configs`**（默认 dry-run）：配置原文在 Git 仓库、解析结果在
  资产表，两者与 `DeviceConfig` 无外键，手工清必漏；`--purge-repo` 只删当前环境的仓库
  （容器 vs 宿主机各一份）。边界与坑：[`handbook/ingest.md`](handbook/ingest.md)。
- **导入服务器负责人**：`manage.py import_server_owners --file x.xlsx`（sheet `servers`，**按列名取**
  而不是按位置，缺列直接报错；`ip` 是唯一键、导入时规范化；更新只覆盖 hostname / owner，不动
  `status`；有非法行则整批不导入并非零退出）。
- `Topology` 是单模型（图数据存 `graph_data` JSON，没有节点/边表）；`Device` 没有 `address` 字段
  （地址在 `DeviceConnection`）。
- **大屏供数（Dashboard）读写分离**：采集在 `ingest`（`collect_dashboard` / `collectors/`）、写库
  只在 `analysis.write_dashboard` 一个事务里 upsert，`GET /api/dashboard/` 只读。这是全项目**唯一**
  用 `{status, message, result}` 包装的接口（旧大屏前端拦截器只取 `res.result`）。`DASHBOARD_WRITE_TASK`
  / `DASHBOARD_PAYLOAD_VIA_REDIS` / `DASHBOARD_PAYLOAD_TTL` 三处定义在 `base.py`；任务名由
  `tests/ingest/test_dashboard_collect.py` + `tests/analysis/test_dashboard_write.py` 对账。
  细节：[`handbook/analysis.md`](handbook/analysis.md)。
- **`asgi.py` 三层**：`django_application` → `_dispatch`（`/mcp*` 交 MCP，其余交 Django）→
  `LifespanApp`（握手 + `LIFESPAN_HOOKS`，当前是 MCP 的 `session_manager.run`）。钩子清单只在
  `asgi.py` 组合，基建不自己注册；换掉 `--worker-class uvicorn_worker.UvicornWorker` 就没有
  lifespan（`LifespanApp` 会在首个请求上告警一次）。见 [`handbook/llmtools.md`](handbook/llmtools.md)。

## 语言约定

- **思考过程用中文展示**：Agent 的分析、推理、解释等思考过程必须使用中文输出。
- 代码注释、commit message、PR 描述等技术文档使用中文。
