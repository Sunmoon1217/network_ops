# llmtools：MCP 工具子系统

根目录的普通 Python 包（**不是** Django app），与 `apps/` 下各业务域平级、且位于它们之上：
MCP 的基建、实体注册表、通用工具与出口都在这里，`core` 只管用户 / 认证 / 任务。

| 模块 | 职责 |
|------|------|
| `server.py` | 根 server 单例 `mcpserver` + `with_db_lifecycle` + `build_transport_security` |
| `registry.py` | 实体注册表 `SPEC` / `EDGES`：各域把可查的模型或视图登记进来 |
| `query.py` | QueryPlan 编译器（受控 AND/OR / 排序 / 投影 / offset） |
| `entity_tools.py` | 通用工具实现（find / list_records / query / get_record / bundle / relations），纯函数 |
| `tools.py` | 工具注册表：汇总各域名单 + 统一套 `with_db_lifecycle` + `add_tool()` |
| `domains/<域>/` | 各域接入：`specs.py` 实体声明 + `tools.py` 纯函数，契约 `register()` / `TOOLS` |

## import 本包 = 完成整条接线

组合根就是 `llmtools/__init__.py`：先 `assets.register()`（登记实体与边，**边要求端点
先登记**），再 `register_all()`（把 `TOOLS` 逐个挂到根 server）。传输层不在这里——
`mcpserver.streamable_http_app()` 由 `netops.asgi` 调用，本包不认识 Django、也不决定站点
怎么装配；对外只暴露 `mcpserver` 与 `build_transport_security`。

两条使用前提：

- 本包会拉各域 models / serializers，**必须在 `django.setup()` 之后 import**；连
  `from llmtools.registry import SPEC` 这种子模块导入也会连带初始化整条链路。
- **目录名绝不能叫 `mcp/`**：项目根在 `sys.path` 最前，会遮蔽 PyPI 的 mcp SDK
  （`from mcp.server import MCPServer` 变成 `ModuleNotFoundError: No module named 'mcp.server'`）。

## 为什么工具数不随表增长

实体表有 40+ 张，工具却只 6 个，靠的是把「实体」下沉成数据：`find` / `list_records` /
`query` / `get_record` 覆盖全部登记类型，新增一张表只加一条 `EntitySpec`。真正需要独立
工具的只有两类：

- **多步查库 + 算法**（`relations` 的变深遍历、`bundle` 的横切拼装）——参数化的多跳查询
  不是 `filters` 能表达的；
- **结构化查询**（`query`）——`list_records` 的 filters 只支持「别名 → 单值」，表达不了
  AND/OR、多字段排序、字段投影与 offset；`query` 走受控编译层，字段路径与操作符仍走白名单。

判断标准只有一条：**能用 spec 的 `filters` / `include` 表达的，一律不新开工具**。
域专属工具（如资产域的 `locate`）放在各域的 `tools.py`，不混进通用模块。

## 三条返回纪律

1. 列表给摘要，详情才给全字段（`detail=True`）——18 个字段 × 20 条是纯噪音；
2. 必须回 `total`，否则 LLM 会拿首页当全集下结论；
3. 错误信息带可用值——粗粒度工具里 LLM 猜错枚举是常态，错误串是它唯一的纠正信号。

## 查询计划的安全口径（`query.py`）

把调用方给的 `QueryPlan`（纯数据）编译成经过白名单校验的 `QuerySet`，
**不接受任何 ORM 字符串或任意 `__` 查找**：

- 过滤字段：只允许 `EntitySpec.filters` 里声明过的路径（含多跳，如
  `device_model__vendor__name`）与业务键；
- 排序字段：只允许 `EntitySpec.order`、业务键与 `id`；
- 投影字段：默认摘要，`fields=["*"]` 才给全字段；
- 操作符：`exact` / `iexact` / `icontains` / `istartswith` / `gte` / `lte` / `in` / `isnull`。

路径逐段过 `_meta.get_field`：spec 写错时在编译期就报错，而不是把 `FieldError` 抛给调用方。

**权限钩子**：`EntitySpec.base_queryset` 为空时按全库查询（当前内网可信部署）。将来接上
用户身份后，只需在 spec 上挂一个「按 request 过滤」的函数，编译器以它为起点——
**权限条件永远不来自调用方输入**。

## 两条防循环硬规矩（`server.py`）

1. `llmtools` 包**禁止 import 任何域模块**（`assets` / `analysis` / `docs` …）——叶子 import
   本包、本包再 import 叶子即成环；组合责任只在 `__init__.py`。
2. **禁止 import core 的业务模块**（`core.models` / `core.api` / `core.permissions` /
   `core.tasks`）：MCP 只提供查询基建，不读用户、权限、任务数据。

## 为什么要 `with_db_lifecycle`

MCP 同步工具跑在 AnyIO 短命工作线程，不像 Django 视图自带 `request_finished` 时的
`close_old_connections`——连接会随线程对象滞留到 GC 才关闭（测试库销毁时报
"being accessed by other users" 就是它）。包装在调用前后各补一次 `close_old_connections()`：
本项目 `CONN_MAX_AGE` 默认 0，调用结束即关连接，语义与一次 Web 请求对齐。
**`functools.wraps` 必须保留**——SDK 沿 `__wrapped__` 链读签名生成入参 schema，
去掉 wraps 工具就没有参数说明书了。

## 工具写法三条

1. 只做「参数校验 → 查库 → 序列化」，字段口径复用 `assets.serializers`；
2. 同步 `def` 别写 `async def`（事件循环里调 ORM 会 `SynchronousOnlyOperation`）；
3. 模型可读的失败抛 `ToolError`（原文达模型、可自我纠正，如「设备不存在：xxx，可先用 find
   搜索」）；程序 bug 不用管（SDK 泛化为 `Error executing tool …`，traceback 只进服务端日志）。

**返回注解用 `dict[str, Any]` 而不是 `TypedDict`**：实体类型由注册表驱动、字段随序列化器走，
固定结构不存在，写假 TypedDict 只会让类型检查放过字段漂移——字段口径的正确性由序列化器 +
`tests/mcp/` 保证。工具名是全局平面命名空间，按域前缀（未来 `config_*` / `cloud_*` /
`zabbix_*`）防撞名。测试模式：`mcp.Client(server)` 内存传输整链 + `django_db(transaction=True)`。

**注册是集中式的**：域里既没有 `@mcp.tool()`，也不 import MCP 基建；重名在 `register_all()`
启动期即抛错（SDK 默认是静默覆盖）。**没有任何「import 即注册」**：`specs.py` 底部不自动调用
`register()`，声明模块 import 进来是纯的；接线只发生在 `__init__.py`。防循环靠导入顺序——
基建（`server` / `registry` / `query` / `entity_tools`）先、`domains` 次之、`tools` 最后，而
`domains/*` 只 import `registry` / `entity_tools`，绝不 import `tools` 或包本身。

现状：资产域为实体注册表形态（`domains/assets/specs.py` 持 `NodeType` / `EntitySpec` 与
`EDGES`），七个工具（`find` / `list_records` / `query` / `get_record` / `bundle` / `relations` /
`locate`）只做「spec → queryset → 序列化」，**新增表 = 注册表加一行，工具层零改动**；
新增实体类型先进 `NodeType` 占位防拼写分叉。

## 会话管理器的单次约束

`mcpserver.streamable_http_app()` 的 HTTP 传输（`session_manager`）是**懒创建**的，
全进程只应调用一次：重复调用会替换 `session_manager`，使先前那个 ASGI app 持有失效的
manager（表现是能连上但会话不通）。

## ASGI 装配（`netops/asgi.py`）

四层，顺序不能反：

```
django_application = get_asgi_application()          # 先完成 django.setup()
mcp_http_app = McpGuardMiddleware(                   # 出口护栏（匿名限流），只管 /mcp
    mcpserver.streamable_http_app(...)               # 建完才有 session_manager
)
_dispatch            → /mcp* 给 mcp_http_app，其余给 django_application
LifespanApp(_dispatch, [mcpserver.session_manager.run])
```

- 护栏包在 MCP 子应用外面而**不是** `_dispatch` 外面：`/api`、静态资源、admin 的请求量比
  `/mcp` 大得多，没必要每条都过卡。
- `MCP_ENABLED=0` 时这一整段都不存在（不 import `llmtools`、不建子应用、`LIFESPAN_HOOKS` 空），
  `/mcp` 由 `_dispatch` 自己回 404——**不能**交给 Django，SPA 兜底会返回 200 + `index.html`。

- `session_manager.run()` 是**生命周期钩子**，由 `netops/lifespan.py` 的 `LifespanApp` 在
  `lifespan.startup` 时进入（全进程一次）、`shutdown` 时退出。Django 6.1 的 ASGI handler 收到
  lifespan scope 直接抛 `ValueError`，所以 lifespan 必须在外层接走，**不能**转给 Django
  （转发给 MCP 子应用也不必——它的 lifespan 就是 `session_manager.run()`）。
- `transport_security` 必须显式传 `build_transport_security()`：默认值只信任 localhost，用
  IP / 域名访问会 421。
- 不用 Starlette `Mount`：`streamable_http_app()` 内部路由就是 `/mcp`，`Mount("/mcp", …)` 会把
  端点叠成 `/mcp/mcp`，`Mount("/", …)` 又会被 Django 侧整体吞掉。
- 钩子清单只在 `asgi.py` 组合（基建不自己注册），由 `tests/deploy/test_asgi_lifespan.py` 守；
  换掉 `--worker-class uvicorn_worker.UvicornWorker` 就等于没有 lifespan（首个请求上告警一次）。
- nginx 与 Vite 都已代理 `/mcp`（漏了会落到 SPA 兜底返回 `index.html`，表现为「被路由守卫跳
  登录」）；流式响应用 SSE 分块下发，反代要 `proxy_buffering off` + 长读超时，由
  `tests/deploy/test_reverse_proxy_config.py` 守。

## 出口（`/mcp`）：匿名 + 按 IP 限流

现状**匿名**：能访问到端点就能调工具，身份与配额只到「客户端 IP」这一层
（`netops/mcp_gateway.py`）。这是有意的临时状态——先把出口打通，鉴权后补。

- **为什么 `Mcp-Session-Id` 不算凭证**：它在 `initialize` 的应答里下发，而 SDK 自己不做认证
  （`scope["user"]` 由外层给）。没有外层身份时，`_session_owners` 的归属比对退化成
  `None == None`，任何人都能开会话。SDK 只保证「同一会话同一身份」，不回答「你是谁」。
- **要加鉴权时**：改 `_guard` 一处即可——验完 token 把调用者写进
  `scope["user"] = AuthenticatedUser(AccessToken(token=…, client_id=…, scopes=[], subject=…))`
  （`mcp.server.auth.middleware.bearer_auth` / `mcp.server.auth.provider`），SDK 随即接管
  会话归属绑定：别人拿着你的 session id 请求会被回 404「Session not found」（故意伪装成不存在）。
  每个请求都要重新带 `Authorization`——归属比对看的是**本请求**的 `scope["user"]`。
- **限流口径**：按 IP 的分钟固定窗口（`INCR` + `EXPIRE`，跨分钟最多宽限一个窗口），默认
  60 次/分钟，`0` = 不限流。IP 取值顺序 `X-Real-IP` → `X-Forwarded-For` 首跳 → ASGI `client`：
  nginx 用 `$remote_addr` 覆盖前者（伪造不了），而 `$proxy_add_x_forwarded_for` 会保留客户端
  自带的前缀。不经 nginx 直连时两者都可伪造，此时限流只是「防手滑」，不是防护墙。
- **Redis 故障 fail-open**：只记 warning 后放行。限流是护栏不是业务，不该把出口搞挂。
