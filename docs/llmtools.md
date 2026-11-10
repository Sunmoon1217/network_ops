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

## 会话管理器的单次约束

`mcpserver.streamable_http_app()` 的 HTTP 传输（`session_manager`）是**懒创建**的，
全进程只应调用一次：重复调用会替换 `session_manager`，使先前那个 ASGI app 持有失效的
manager（表现是能连上但会话不通）。
