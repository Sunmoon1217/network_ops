# AGENTS.md

> 本文件是**约定与入口**：能一眼看完的规则写在这里，细节一律放 `handbook/`（索引见
> [`handbook/README.md`](handbook/README.md)）。第三方软件实测行为放 `.dsh/skills`（见「知识库」）。
> 写代码或改注释前，先看「关键约定」与对应域的那份 handbook。

## 项目概述

网络运维管理平台：Django REST 后端 + Vue 3 前端。

- 后端：数据模型 + REST API；设备配置解析入库（`ingest/parsers` TTP + `savers`）；
  `ingest/collectors/` 接 Zabbix / Autotask 给总览大屏供数。
- 前端：Vite **双入口**（`index.html` 主站 / `dashboard.html` 大屏），构建产物可由 Django 直接托管（开发调试）。
- 生产：`docker compose` 起 db / redis / code-init（一次性把代码与静态成品铺进命名卷）/ app / worker /
  consumer / beat / nginx；nginx 统一入口（静态直出，`/api`、`/mcp` 反代 app）。
  宿主直跑 `scripts/deploy-host.sh`，与容器共用 `envs/*.env`。

## 项目拓扑

```
外网远程开发 <--git--> 托管平台 <-- 代理git --> 内网开发 | 内网沙箱 <--ssh--> 内网服务器
```

- 代码以托管平台为汇聚点（外网直接 push / pull）；内网经**代理 git** 同步；
  内网 ↔ 内网服务器走 **ssh**（部署、调试、远程执行都在内网服务器上）。

## 项目结构

```
network_ops/
├── netops/          # settings/（base 集中 env 动态项 + dev/container/prod）、urls、asgi、lifespan、views、schema（外部 DTO 基类）
├── apps/
│   ├── core/        # 用户与认证、Task/Stage、运维命令（ensure_superuser / migrate_if_needed / queue_*）
│   ├── assets/      # 网络域模型（单文件 models.py）+ 序列化器 + API + Excel 导入
│   ├── ingest/      # 采集/解析/入库：parsers(TTP) / savers / mapping / pipeline / workflow / config_repo + collectors/（外部数据源）
│   ├── analysis/    # 只读消费侧：路径追踪、访问流、互联网资产、监控、大屏供数；models/ 是包
│   ├── cloud/       # 阿里云接入：客户端封装 + 云资源缓存（暂无对外 API）
│   └── docs/        # 功能域：表格编辑 + 文档转换 + Dify 推送（与 handbook/ 无关）
├── llmtools/        # MCP 工具子系统（根目录包、非 app）：server / registry / query / entity_tools / tools / domains
├── frontend/        # Vue 3 + TS + Vite 双入口；src/{shared,netops,dashboard} 三层，dist/ 由 nginx 直出
├── nginx/           # 反向代理（静态直出 + API/MCP 代理 + 启动时 resolver 推导）
├── entrypoint/      # 容器入口脚本（code_init / app / worker / consumer / beat）+ README（容器化构建手册）
├── envs/            # common.env 共享 + container/host 差异 + gunicorn/celery.env + secrets/（凭据，不入库）
├── conf/            # 平台自身结构化配置（links.json），入库；运行时只读挂 /etc/netops/conf（与 data/configs 设备配置区分）
├── handbook/        # 设计说明（索引 handbook/README.md）；不入镜像
├── scripts/         # deploy-host.sh + switch-branch / setup-git-hooks
├── tests/           # 按应用分目录，pytest testpaths 指向此处
├── typings/         # 第三方库存根（zabbix_utils 等；pyrefly 的 site-packages-path）
├── data/            # 运行期数据（不入库）：config_repo、configs（Excel 源）、run/logs
├── dockerfile*      # .base（系统依赖）/ .venv（uv sync）/ .code（源码+静态成品）/ 传统 dockerfile（备选）
├── compose.yml      # db(TimescaleDB) / redis / code-init / app / worker / consumer / beat / nginx
└── pyproject.toml   # 依赖、pytest、ruff、pyrefly 配置
```

**依赖方向**：`llmtools → apps`，`analysis → ingest → assets`（单向）。`assets` 不许 import
`ingest`；`ingest` 除 `purge_configs` 这类跨域运维工具外不许 import `analysis`；`llmtools` 的
子模块不许 import 任何业务域（`domains/` 是唯一例外）。

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
| 产品路线图（四阶段 18 项 + MCP 工具域路线） | [`handbook/roadmap.md`](handbook/roadmap.md) |

## 知识库（跨会话共享的实测结论）

第三方软件的实测行为放**用户级技能**（跨项目）：事实源 `~/.local/share/dsh/skills/<name>/SKILL.md`
（全局是 git 仓库，跨机器共享就 push + clone；本项目 `.dsh/skills/<name>` 只是软链，`.dsh/` 在
`.gitignore` / `.dockerignore`，不入库不进镜像）。技能清单自动进会话，正文按需加载。

写新技能：① frontmatter 的 `description` / `whenToUse` 用 `>-` 折叠块（值含半角 `: ` 会让整条
技能被丢弃）；② 每个目录一个 `SKILL.md`（嵌套不会被发现）；③ 加完用 `skill` 工具加载确认；
④ 改完在全局仓库提交。

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

## 环境搭建

需要 Python >= 3.12，用 `uv` 管理包。

```bash
uv venv --python 3.12
uv sync --all-groups          # 主依赖 + dev + test
cp envs/example/*.env envs/   # 首次：模板入库，实例不入库（日常只改 envs/common.env）
cd frontend && pnpm install
```

数据库 **PostgreSQL**，配置走环境变量（全表见 [`handbook/settings.md`](handbook/settings.md)）。
配置三处：根 `.env` 只给 compose 插值；`envs/*.env` 是容器与宿主**共用的一套**（`common` 共享 +
`container`/`host` 差异 + `gunicorn`/`celery` 旋钮）；`envs/secrets/*` 凭据只读挂载（见 `envs/README.md`）。
宿主直跑时 `base.py` 自己 `load_dotenv(envs/common.env)`，非 container 再叠 `envs/host.env`
（`override=False`，真实进程环境变量永远优先；`NETOPS_SKIP_DOTENV=1` 全跳过）。
凭据链 `*_FILE > 同名环境变量 > 默认值`，容器里 `*_FILE` 指向 `/run/secrets/*`。

## 常用命令

```bash
# 后端（项目根）
uv run python manage.py migrate | createsuperuser | runserver
uv run python manage.py queue_status          # 队列积压巡检（--json；超阈值退出码 1，可接 cron）
uv run python manage.py queue_backlog         # 积压明细（--json / --limit）
uv run python manage.py reparse | purge_configs | import_server_owners   # 见 handbook/ingest.md
uv run python manage.py rebuild_access_flows --device <H> [--sync]
./scripts/deploy-host.sh deploy | status      # 宿主部署：app / worker / consumer 三进程

# 前端（frontend/）
pnpm dev | build | type-check

# 容器（换代码镜像后必须先重跑 code-init：app 挂的是 code 卷，不是镜像里的 /app）
docker compose up -d code-init && docker compose up -d

# 质量
uv run pytest                                 # 单进程；排查单个文件时用它
uv run pytest -n auto --dist loadfile         # 全量多进程（每 worker 建自己的 test_netops_gwN）
uv run ruff check ; uv run ruff format ; uv run pyrefly check
```

> pytest 加 `-v --tb=short`（输出非流式，只有 `-v` 逐条可见；范围大按 `tests/<域>` 拆跑）。
> `-n` 需数据库账号有 createdb 权限（dev 的 `netops` 已具备）；Windows 上
> `test_reparse_command` 两个 fork 用例本来就红；xdist 别混 `-q`。**别用管道截断 pytest
> 输出**（管道提前关闭杀进程、留脏测试库）；要实时进度就独立进程写日志再 tail。

## 关键约定

> 只写本项目自己的约定（路径、服务、旋钮、契约）。第三方实测行为在 `.dsh/skills`，部署侧
> 硬要求与代价在 [`handbook/deploy.md`](handbook/deploy.md)，这里只留「会被踩坏的那一句」。

- **新需求先查路线图**：接到新需求 / 想加新功能，先对照 [`handbook/roadmap.md`](handbook/roadmap.md)
  判断是否属于既有规划（四阶段 T1–T18 或 MCP 工具域路线）——属于则按对应任务实施并回写状态，
  不属于再确认是否偏离蓝图定位（资产与关系的权威源 + 运营流程起点），避免脱离规划随意加功能。
- **settings 分层**：可被环境变量影响的配置**只在 `base.py` 定义一遍**；三个环境文件只放硬差异
  （`dev.py` 空壳；`container.py` 两条 host 必填守卫；`prod.py` `DEBUG=False` 硬覆盖 + 5 项守卫）。
  环境旋钮唯一 `DJANGO_ENV`（不设 → dev，白名单，拼错拒启动），`DJANGO_SETTINGS_MODULE` 恒为
  `netops.settings`。`base.py` 与三个环境文件**禁止** `from netops.settings import ...` /
  `from . import ...`（半初始化时会炸）。细节：[`handbook/settings.md`](handbook/settings.md)。
- **数据库后端二选一**：`DB_ENGINE=postgresql|mysql`（默认 PG；其它值拒启动），变量名沿用
  `POSTGRES_*`。MySQL 走 `docker compose -f compose.yml -f compose.mysql.yml`，驱动 mysqlclient
  靠 `dockerfile.venv` 两阶段构建编译。跨库差异（GIN 只在 PG、`Service` 唯一键在 MySQL 用函数
  索引、JSON 成员查询在 MySQL 无索引、DDL 不可回滚）见 [`handbook/deploy.md`](handbook/deploy.md)。
- **`.env` / `envs/*.env` 里含 `$` 或 `#` 的值一律用单引号**（compose 会插值 `$`，`#` 前有空格即
  注释，双引号不保护 `$`）。技能 `docker-compose-behavior`。
- **模型集中**：`assets` 所有模型在单文件 `apps/assets/models.py`；`analysis` 相反是 `models/` 包
  （`access_flow` / `internet_analysis` / `dashboard` + `__init__.py` re-export）——不能同时留
  `models.py` 与 `models/`（包优先，单文件被静默忽略）。
- **应用注册**：`core.apps.CoreConfig`、`ingest.apps.OperatorConfig`（label 仍是 `operator`）、
  `assets.apps.AssetsConfig`、`analysis.apps.AnalysisConfig`、`cloud.apps.CloudConfig`、
  `docs.apps.DocsConfig`；另加 `drf_spectacular` / `drf_spectacular_sidecar`。
- **五条 Celery 链**：① 阶段式工作流（`/api/tasks/` 唯一入口，采集→解析→存储由 `Stage` 回写推进）；
  ② 批量导入配置（`.si()` 串 `run_config_parsing → run_config_storage`）；③ 访问流重建
  （`ACCESS_FLOW_TASK` 投独立队列 → 单写者 consumer）；④ 大屏落库（beat 投
  `ingest.collect_dashboard` → `DASHBOARD_WRITE_TASK` → `analysis.write_dashboard` 唯一写库）；
  ⑤ 大屏链路缓存（beat 投 `ingest.refresh_link_cache` → Zabbix `history.get` → Redis
  `dashboard:link:series`，**不落库**）。broker/backend 都是 Redis，**必须有 worker 消费**；大屏
  三链周期都在 `CELERY_BEAT_SCHEDULE`，仓库外不要再挂调度器。细节：handbook/ingest.md、analysis.md。
- **采集器边界**：`ingest/collectors/` 只做「调外部接口 → 归一成可 JSON 序列化的 dict」
  （DTO 用 pydantic + `netops.schema.ExtraModel`），**不碰数据库、不 import `analysis`**；
  连接配置在 `settings.ZABBIX_CONFIG`（Token 优先于用户名密码）。
- **OpenAPI 3 文档**：`/api/schema/` 是浏览器入口（302 → Swagger UI）；描述文件在
  `/api/schema/openapi.yaml`（`name="schema"`，**别把 schema 视图挂回 `/api/schema/`**，否则 UI
  拉到 HTML）；另有 `/api/schema/swagger-ui/`、`/api/schema/redoc/`（**不叫 `/api/docs/`**，那是
  docs 业务域）；UI 资源走 sidecar（内网不通外网），权限由 `DJANGO_API_DOCS_REQUIRE_LOGIN` 控制。
  见 [`handbook/api.md`](handbook/api.md)。
- **业务日志**：`LOGGING` 只给项目命名空间（core/ingest/assets/analysis/cloud/docs/llmtools/netops）
  装 stderr handler，级别 `DJANGO_LOG_LEVEL`（默认 INFO）；**不动 root**（celery 会 hijack）、
  `propagate` 保持 True（`caplog` 仍可捕获）。
- **DeviceConfig 解析入库默认同步**（`pipeline.run_config_pipeline` 在 post_save 调用栈里跑完）；
  **例外是批量导入**（挂 `_defer_pipeline` 后投 celery 链）。两套链路并存，别混。
- **部署**：nginx 是统一入口；静态资源走「宿主机构建 → 镜像 COPY → `code-init` 铺进命名卷 →
  nginx 只读挂载」（**换代码镜像或改源码后必须重跑 `code-init`**：app 挂的是 `code` 卷，不是镜像里的
  `/app`）。`repo` 命名卷、`data` 只读 bind（首次先 `mkdir -p data`）、`conf/` 只读 bind（重跑
  `code-init` 都不覆盖）。app / worker / consumer / **beat** 四进程并存，beat 单实例、启动先刷链路缓存。
  nginx 用**变量式** upstream + 启动时推 `resolver`；conf.d 必须 `$http_host` 透传 Host（否则后台
  登录 403）。细节：[`handbook/deploy.md`](handbook/deploy.md)。
- **双入口静态托管**：`frontend/dist/` 有 `index.html`（主站 `#app`）与 `dashboard.html`
  （大屏 `#dashboard`），共用 `/assets/*` 的 main chunk。**nginx 与 Django 都必须单独返回
  `dashboard.html`**（Django 兜底前的 `vue_dashboard`），SPA 兜底只回主站 `index.html`；
  `/dashboard` 是三处（Vite dev / nginx / Django）一致的友好 URL。漏配表现「大屏变主站登录页 / 空白」。
- **代理感知**：`SECURE_PROXY_SSL_HEADER` 让 Django 识别 nginx 传来的原始协议；`ALLOWED_HOSTS`
  默认 `*`；`DJANGO_CSRF_TRUSTED_ORIGINS` 正常拓扑**留空即可**。
- **「账号密码换 token」的接口必须 `@authentication_classes([])`**（login / register），否则带
  `sessionid` 打过来会被 DRF 拦成 403；注册只创建普通账号。
- **前端**：请求路径以 `/api/` 开头；自动导入用 `unplugin-auto-import` + `unplugin-vue-components`；
  图表用 `@antv/g6` 5.x。
- **前端三层目录**：`src/shared/`（别名 `@`）、`src/netops/`（`@netops`）、`src/dashboard/`
  （`@dashboard`）。两个入口共用 `src/main.ts`，按页面里的 `#app` / `#dashboard` 各自建 app +
  pinia + router；**共享层不许反向 import 两个应用**。
- **`auto-imports.d.ts` / `components.d.ts` 不入库，但 `vue-tsc` 必须要它们**（vite 插件在
  **buildEnd** 写出）：`pnpm build` = `vite build && vue-tsc --noEmit`（先出产物、后检查）；
  `pnpm type-check` / pre-commit 先跑 `pnpm gen-dts` 补全声明再 `vue-tsc`。**别**把 `vue-tsc`
  排到 build 前面：声明还是上一轮的，组件类型静默退化成 any，检查假绿。
- **前端函数风格**：`.vue` / `.ts` 一律箭头函数，不用 `function` 声明。自检（应无输出）：
  `grep -rnE "^[ \t]*(export )?(async )?function [A-Za-z_$]" frontend/src --include=*.ts --include=*.vue`
- **前端类型集中**：具名 `interface` / `type` / `enum` 全在 `frontend/src/shared/types/`（按域分
  文件 + `index.ts` barrel），一律 `import type { ... } from '@/types'`；业务文件不落具名类型定义、
  不做中转导出；barrel 撞名**语义化改名**（别用下划线避让）；`types/index.ts` 用 `.ts` 不是
  `.d.ts`。大屏自有类型在 `src/dashboard/types/`。细节与坑：技能 `frontend-types`。
- **前端颜色禁用硬编码**：UI 颜色只用 `var(--el-*)`（否则暗色主题不跟随）。三类例外保留字面量：
  图表/数据系列色（canvas 不读 CSS 变量）、品牌主色 `#34c8ff`、主题变量定义源头
  （`netops/stores/theme.ts`）。`var(--el-bg-color, #fafafa)` 的 fallback 不算硬编码。
- **表格列宽偏好只认注册表**：key 集中在 `frontend/src/shared/constants/tableKeys.ts`
  （`TABLE_KEYS`），页面只传 `<DataTable :table-key="TABLE_KEYS.xxx">`，不自己调 `useTablePrefs` /
  `widthFor`；后端 `/api/me/preferences/` 只是按用户存取的不透明 JSON KV；改 key 走
  `TABLE_KEY_RENAMES`。
- **表格列一律 `<DataColumn>`**，不裸写 `el-table-column`：列 key 解析偏好宽度、内容列走
  `min-width` 参与富余空间分配、锚点列（`anchor` 或 `fixed`）用固定 `width`。
- **Ruff**：`line-length = 180`，`select = ["E","F","I","N","W"]`，忽略 `F405/F403/E402`；
  `**/migrations/*` 忽略 `E501` 且不参与格式化。
- **提交前检查（git hooks）**：hook 随仓库走（`.githooks/pre-commit`），首次需
  `sh scripts/setup-git-hooks.sh`。只检查**暂存文件**：冲突标记、`ruff check`、
  `ruff format --check`（只警告，`NETOPS_HOOK_STRICT_FORMAT=1` 才阻断）、`pyrefly check`
  （阻断；`NETOPS_SKIP_PYREFLY=1` 跳过）、暂存的 `.ts/.tsx/.vue` 跑 `vue-tsc --noEmit`
  （阻断；`NETOPS_SKIP_FRONTEND=1` 跳过）。改 hook 自身要 `git commit --no-verify`。
- **测试**：pytest + pytest-django，`testpaths = ["tests"]`，统一放 `tests/<应用>/`（应用目录下
  不留脚手架的 `tests.py`）。测试内资源定位用包路径（`Path(ingest.__file__).parent / ...`）或
  `settings.BASE_DIR`，**不要** `Path(__file__).parent.parent`（目录一挪就静默失效）。
- **提交与分支（本仓分支模型，2026-11 从技能 `git-branch-flow` 上收为约定）**：`master` 只整批接收
  `Merge branch 'develop'`（发布线），`develop` 是汇聚线——**feature / fix 一律从 `develop` 切**，
  合并在 develop 侧（`--no-ff`，中文说明）。**一需求 = `feature/<主题>`，一 bug = `fix/<主题>`**；
  多轮迭代在原分支继续 commit，开新分支的判据是「需求 / 问题变了」。**新分支必须 worktree 建在
  `.worktrees/`（`git worktree add .worktrees/<主题> -b <分支> develop`），主工作区常驻 develop**，
  开发 / 构建 / type-check 都在 worktree 里做；合并后可 remove 目录，分支不删（远程留档）。
  **每个改动及时 commit**（中文 conventional message），合并后 `push origin develop <分支>`；
  **除非用户主动要求，不做任何 merge / 合并推送**——默认终点是「已提交在 worktree 分支里」。

## 三层架构

| 层 | 职责 | 细节 |
|----|------|------|
| `core/` | 用户与认证、`Task` / `Stage`、运维命令（积压巡检也在这里） | [`handbook/api.md`](handbook/api.md) |
| `assets/` | 网络域数据模型（`ConfigBase` 基类）+ 序列化器 + API + Excel 导入 | [`handbook/assets.md`](handbook/assets.md) |
| `ingest/` | 采集、TTP 解析、Saver 写库、Git 配置仓库；三阶段工作流与访问流 / 大屏投递触点；`collectors/` 接外部数据源 | [`handbook/ingest.md`](handbook/ingest.md) |
| `analysis/` | 路径追踪、策略展开 / 访问流、资产分析、队列与运行监控、大屏供数（只读消费） | [`handbook/analysis.md`](handbook/analysis.md) |
| `cloud/` | 阿里云客户端封装 + 云资源缓存（暂无对外 API） | [`handbook/cloud.md`](handbook/cloud.md) |
| `docs/`（app） | 表格编辑 + 文档转换 + Dify 推送 | [`handbook/docs-domain.md`](handbook/docs-domain.md) |
| `llmtools/` | MCP 工具出口（根目录包，与 `api/` 平行） | [`handbook/llmtools.md`](handbook/llmtools.md) |

## 注意事项

- **解析器 / Saver / 模型三层关联**：解析器按 `(vendor, device_type)` 产出**原始**键 →
  `ingest.mapping` 归一（键别名 + 字段别名，纯函数、幂等、**无厂商维度**）→ Saver 按
  `(device_type, key)` 消费、以 `model_paths` 声明写入的模型。归一住在 `BaseSaver.save`
  （模板方法），值语义与结构级差异留 Saver。契约测试 `tests/ingest/test_parser_contract.py` +
  `test_mapping.py`；清单接口 `/api/parsers/mapping/`。
- **解析器模板管理页面**以**模板文件**为中心单表展示，解析器降级为「关联解析器」列。
- **`parsers/tmpls/running/` 的模板不在 `ParserFactory` 注册表内**（`route.ttp` / `arp.ttp` /
  `mac.ttp` / `lldp.ttp` / `h3c_route.ttp`），由路径追踪 / 路由采集接口按名称动态调用——
  「未关联解析器」不代表可删。
- **TTP 模板引擎**：① 按 **XML** 解析，注释里的尖括号会整模板炸；② `re()` 可内联正则；
  ③ **单条命中给 `dict`、多条给 `list`**，消费方两种都要兼容；④ 内置 `IPV6` 不含点号。
- **F5 池成员端口分隔符有两种**：普通串 / IPv4 用冒号，名字是 IPv6 字面量时用一个点号——
  `f5_ltm.ttp` 两条备选行，端口必须限纯数字，否则冒号那条会贪婪切开 IPv6 成员。
- **互联网资产分析走缓存**：只有 `POST /api/internet-analysis/analyze/` 才计算，查询与导出只读
  `InternetAnalysis`（未分析过 404）。
- **`ingest` 的 app label 是 `operator`**：migrate 时用 `operator`；拆分只动 Python 路径、
  **不动 label**（迁移历史挂在它上面）。
- **改 celery 任务名要按部署步骤走**：Redis 里未消费的旧名消息会 `Unknown task`——升级前停
  worker、清空对应队列再滚动。
- **清理配置数据用 `manage.py purge_configs`**（默认 dry-run）：配置原文在 Git 仓库、解析结果在
  资产表，两者与 `DeviceConfig` 无外键，手工清必漏；`--purge-repo` 只删当前环境的仓库。
- **导入服务器负责人**：`manage.py import_server_owners --file x.xlsx`（sheet `servers`，**按列名
  取**、缺列直接报错；`ip` 是唯一键；只覆盖 hostname / owner，不动 `status`；有非法行整批不导入）。
- `Topology` 是单模型（图数据存 `graph_data` JSON）；`Device` 没有 `address` 字段（在
  `DeviceConnection`）。
- **大屏供数读写分离**：采集在 `ingest`（`collect_dashboard`）、写库只在 `analysis.write_dashboard`
  一个事务里 upsert；**链路带宽不走库**（`conf/links.json` → Redis），`GET /api/dashboard/?group=linechart`
  直读缓存。这是全项目**唯一**用 `{status, message, result}` 包装的接口（旧大屏拦截器只取
  `res.result`）；任务名由 tests/ingest/test_dashboard_collect.py 等三个测试文件对账。
- **`asgi.py` 三层**：`django_application` → `_dispatch`（`/mcp*` 交 MCP，其余交 Django）→
  `LifespanApp`（握手 + `LIFESPAN_HOOKS`）。钩子清单只在 `asgi.py` 组合，基建不自己注册；
  换掉 uvicorn worker 就没有 lifespan（`LifespanApp` 会在首个请求上告警一次）。

## 语言约定

- Agent 的思考 / 分析 / 解释用中文；代码注释、commit message、PR 描述、文档用中文。
