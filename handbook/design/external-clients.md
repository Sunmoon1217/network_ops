# core 承载外部连接实例与 client 生命周期

> **状态：切片式实施中（2026-11-16 起）。Step 1–4 已落地（连接配置统一 + AUTOTASK 收口；
> `core/integrations/` 骨架 + Zabbix 下沉 + 释放钩子；`IntegrationHealth` + beat 探活 + 只读接口），
> 只剩 Step 5（Dify / 阿里云接入 provider）未做——2026-11-25 起阿里云改按无状态通道落地
> （`core/integrations/aliyun/`，不注册 provider），实际只剩 Dify。**
> **现状文档见 [`../integrations.md`](../integrations.md)**——本文保留设计论证与未完成部分。
> 分层总图与依赖矩阵见 [`layering.md`](layering.md)；core 的任务机制（已落地）见
> [`../tasks.md`](../tasks.md)。

## 结论先行

**外部系统的 client 实例从各域的模块全局变量，收归 `core/integrations/` 统一持有。**

调用方（ingest 采集器、将来的 egest、SLS / 混合云写侧、MCP 工具）一律从 core 取实例；
各域只交出一个**工厂函数**，不交实现；core 负责实例的懒建、复用与释放。

这不是「新建一层抽象」，而是**搬家 + 统一生命周期**：Zabbix 的 client 现在就已经是
进程级单例（`apps/ingest/collectors/zabbix/client.py`），只是住在域里。

## 现状实测（2026-11-16）

### 四个外部系统，四种连接形态

| 外部 | 连接配置 | client 实现 | 形态 |
|---|---|---|---|
| 阿里云 | `settings.ALIYUN_CONFIG`（region + endpoints + accounts） | `core/integrations/aliyun/client.py` | 同步 SDK，per-call `AcsClient` / ASAPI |
| Zabbix | `settings.ZABBIX_CONFIG`（url + token/user/password） | `apps/ingest/collectors/zabbix/zabbix.py` | **异步进程级单例**，绑事件循环 |
| Dify | `settings.DIFY_CONFIG`（api_base_url + api_key + dataset_id） | `apps/docs/dify.py` | 同步 `requests`，无状态 |
| Autotask | **代码里硬编码 `BASE_URL`**（`collectors/autotask/client.py:11`） | `apps/ingest/collectors/autotask/client.py` | 异步 `httpx2`，per-call |

四套配置字段名各不相同（`url` / `api_base_url`）、超时散落、错误语义三套
（`ImproperlyConfigured` / 返 503 / 直接 KeyError）、「是否已配置」的判定各写各的。

> 上表是 2026-11-16 的盘点原貌。**2026-11-19 Step 1 已统一**：四套配置都有
> `base_url` / `credential_ref` / `timeout` / `enabled`，autotask 地址走 `AUTOTASK_BASE_URL`。

### Zabbix 单例已经是目标形态，只是住错了地方

`apps/ingest/collectors/zabbix/client.py` 现有实现：

```python
_zapi: TypedZabbixAPI | None = None       # :118 模块级全局
_zapi_loop: asyncio.AbstractEventLoop | None = None

async def get_zapi() -> TypedZabbixAPI:   # :122 懒建 + 登录 + 循环亲和检查
async def close_zapi() -> None:           # :155 登出 + 关 session
async def _dispose(zapi) -> None:         # :167
```

**已经是懒建 + 复用 + 显式释放**，只差「归谁管」。

### `close_zapi()` 全项目没有调用点

grep 结果：只在 `apps/ingest/collectors/zabbix/__init__.py` 里 re-export，
**没有任何地方调用它**。Zabbix 的 session 一直泄漏到进程退出。

这是本方案最直接可兑现的收益。**已兑现（Step 3）**：ASGI lifespan 与 Celery
`worker_process_shutdown` 都调 `core.integrations.release_all()`，见
[`../integrations.md`](../integrations.md) §释放。

### 设备侧连接是另一回事

`apps/assets/models/network.py:193` 的 `DeviceConnection` 存的是**网络设备**的
SSH / napalm / netmiko 连接（address / port / username / password / enable_password），
它属于**被管设备**，不是**外部平台**。

`layering.md` 里 egest 的待定项「是否复用 ingest 的采集通道（napalm / netmiko 连接管理）」
问的正是这一块。**本方案管的是「平台 ↔ 外部系统」，不覆盖「平台 ↔ 被管设备」**——
两者不要混。`DeviceConnection` 存明文密码的问题另议（见 §「待定项」）。

## 三条不可破的边界

| 边界 | 具体含义 | 违反后果 |
|---|---|---|
| **依赖单向** | 域 → core。core **不 import 任何域模块**；注册由域在 `AppConfig.ready()` 里完成 | `core → ingest` 反向 = 循环导入 |
| **循环亲和归 provider** | Zabbix 的 `_zapi_loop is loop` 检查留在 provider 里，core 不懂事件循环 | 每个 Celery 任务 `asyncio.run` 都是新 loop，实例绑死旧 loop 而炸 |
| **密钥不落库** | `credential_ref` 指向 env / `*_FILE`；DB 只存引用名 | 复制 `DeviceConnection` 存明文 password 的坏先例 |

### 边界一：注册范式

照抄 `core/tasktypes.py` 的既有约定（现状见 [`../tasks.md`](../tasks.md)）——**各域在
`ready()` 里追加**：

```python
# apps/ingest/apps.py（现状已有同类写法）
def ready():
    import ingest.savers   # noqa: F401 —— 触发 __init_subclass__ 自动注册
    import ingest.signals  # noqa: F401
```

集成侧同理：

```python
# apps/ingest/apps.py
def ready():
    import ingest.savers
    import ingest.signals
    from ingest.integrations import register_providers
    register_providers()
```

**core 侧 `registry.py` 不得在模块级 import models**——它会被域的 `ready()` 触发，
早于 `AppRegistryNotReady`。registry 保持纯 dict，模型访问放函数内。

### 边界二：为什么循环亲和检查留在 provider

`apps/ingest/tasks.py:253` 每个采集任务都 `asyncio.run(collect(source))`，
**每个 Celery 任务一个新事件循环**。现有 `get_zapi()` 靠 `_zapi_loop is loop` 判定
"实例是否还绑在当前 loop 上"，不同则先 `_dispose` 再重建。

实例归 core 之后，这条逻辑有两种放法：

| 放法 | 评价 |
|---|---|
| 搬进 core | core 得懂事件循环，provider 变成哑的——不取 |
| **留在 provider**（推荐） | core 保持 dumb：只调 `provider.acquire()`，拿到什么用什么 |

core 只需约定 provider 接口里有"当前实例是否仍然可用"这层语义，具体判定由 provider 自己实现。

### 边界三：密钥引用而非明文

现有凭据链是 `*_FILE > 环境变量 > 默认值`（`netops/settings/base.py` 的 `_env_or_file`），
沿用。连接元数据里只存**引用名**：

```python
credential_ref = "ZABBIX_TOKEN"     # 指向 env / *_FILE 的名字，不是值
```

## 目标形态

```
core/integrations/
├── __init__.py      导出 get_client / register_provider / acquire
├── registry.py      工厂注册表 + 实例持有表（纯 dict，不 import models）
├── provider.py      Provider 协议（描述 + 取实例 + 释放）
├── metadata.py      连接元数据读取（现读 settings，将来读 DB）
├── health.py        健康状态记录（写 DB，供跨进程查询）
└── providers/       各系统的 provider 实现
    └── zabbix.py    从 ingest 迁入
```

### core 最终形态（任务机制已并入后）

```
core/
├── models.py         User / Token / UserPreference / Task / Stage
│                    + IntegrationHealth（新增）
├── tasks.py          create_task / dispatch / cancel（通用机制）
├── tasktypes.py     业务词汇注册表（各域在 ready() 里追加）
├── integrations/     外部连接实例与 client 生命周期 ★ 新增
├── permissions.py    IsOperatorOrReadOnly
├── api/              auth / preferences / tasks / stages
│                    + integrations（只读列实例与健康状态）
└── management/       ensure_superuser / migrate_if_needed / queue_*
```

**零业务依赖，零 assets 依赖。** core 不知道 Zabbix 是什么——
它只持有域交上来的 provider 对象。

### Provider 协议

```python
class Provider(Protocol):
    """外部系统的 client 持有者。core 只认这个协议，不认具体系统。"""

    system: str          # "zabbix" / "aliyun" / "dify"
    instance: str        # "default" / "prod" / "test"

    async def acquire(self) -> Any:
        """取 client 实例；同步 client 也走 async 入口（内部直接返回）。"""

    async def release(self) -> None:
        """释放底层资源（关 session / 登出）。幂等。"""

    def describe(self) -> dict:
        """自描述：url / 是否配置 / 后端类型。core 只用它序列化，不 import 域的类型。"""
```

**同步与异步并存**：Zabbix、autotask 是 async（需要 `await`），Dify 是同步 `requests`
（在 DRF 线程池里跑），阿里云是同步 SDK。core 需要同时提供两条取用路径，
否则 Dify 被硬塞进 async 反而更糟：

```python
await core.integrations.acquire("zabbix")     # async client
core.integrations.acquire_sync("dify")        # sync client
```

## 调用方视角

```python
# apps/ingest/collectors/zabbix/queries.py（现状）
zapi = await get_zapi()

# 之后
zapi = await core.integrations.acquire("zabbix")
```

**迁移期保留薄转发**：`apps/ingest/collectors/zabbix/__init__.py` 继续
`from ... import get_zapi`，让 `get_zapi` 内部转调 core。
这样 9 处 `queries.py` 调用点与 `tests/ingest/test_link_cache.py` 里
`patch.object(queries, "get_zapi")` 这个 patch 点**都不用动**。

## 释放钩子

| 进程 | 挂载点 | 备注 |
|---|---|---|
| ASGI | `netops/asgi.py` 的 `LIFESPAN_HOOKS` 组合点（`mcpserver.session_manager.run` 旁边） | `netops/lifespan.py` 已有 `AsyncExitStack` 逆序退出机制 |
| Celery worker | `worker_process_shutdown` 信号（`netops/celery.py` 里接 `signals`） | prefork 子进程各持一份实例 |
| beat / consumer | 同上（同一 Celery app） | beat 不建 client，无副作用 |

`netops/lifespan.py` 的钩子语义是「无参 → 异步上下文管理器」：

```python
@asynccontextmanager
async def zabbix_client():
    try:
        yield
    finally:
        await core.integrations.release_all()
```

## 健康状态必须外化

**实例是进程内的**：ASGI worker / Celery worker / consumer / beat 是四个独立进程，
admin 与 MCP 工具所在的进程**看不到**采集进程持有的实例。

所以"健康状态"要能在 admin 或 MCP 里查到，必须落到 DB 或 Redis，不能是 core 内存字段。

建议新建一张只写状态、不写业务数据的小表：

```python
class IntegrationHealth(models.Model):
    system = models.CharField(max_length=32)
    instance = models.CharField(max_length=32)
    status = models.CharField(max_length=16)      # ok / degraded / down / unknown
    checked_at = models.DateTimeField()
    error = models.TextField(blank=True, default="")
```

选 DB 而非 Redis 的理由：T16 要做「状态不一致对账」，需要「上次成功时间」这类历史。

`probe`（怎么探活）由域注册，core 只调度与记录：

```python
# apps/ingest/integrations.py
def register_providers():
    register_provider(ZabbixProvider(system="zabbix", instance="default"))
```

**调度者（2026-11-16 补）**：用 **Celery beat 周期任务**触发——在 `netops/celery.py` 的
`beat_schedule` 注册一条（默认每 5 分钟）`core.integrations.probe_all` 任务，逐 provider
`acquire()` 成功即记 ok、异常记 down + error。beat 进程本就不建 client（见 §「释放钩子」），
探测在 worker 里执行，与实例亲和检查同一套循环亲和逻辑（provider 内判定，core 不懂事件循环）。

## 实施顺序

每步独立可验证、可停下。每步跑全量测试（当前基线 `854 passed, 66 subtests passed`）。

### Step 1 — 补漏（低风险，零架构改动）

**状态：已落地（2026-11-19）**。四件事全部完成：

1. `apps/ingest/collectors/autotask/client.py` 的硬编码 `BASE_URL` 收进
   `settings.AUTOTASK_CONFIG`（`AUTOTASK_BASE_URL` / `AUTOTASK_TIMEOUT`）——全项目最后一处
   游离在配置外的连接信息清零；
2. 四套 CONFIG 统一字段 `base_url` / `credential_ref` / `timeout` / `enabled`，域特有项保留
   （阿里云的 `region` + `endpoints` + `accounts`、Dify 的 `dataset_id` 与分段规则、
   Zabbix 的 `token` / `user` / `password`）；
3. 「是否已配置」统一看 `enabled`，消费方一律抛 `ImproperlyConfigured`（Dify 的推送接口仍按
   业务约定把它翻成 503）；阿里云账号级缺钥匙也从 `KeyError` 改成明确报错；
4. `handbook/settings.md` 增加统一 schema 小节与 autotask / `ALIYUN_TIMEOUT` 变量，
   `envs/example/common.env` 同步。

实现与契约：`netops/settings/base.py` 的四份 CONFIG、`tests/core/test_external_config.py`
（字段齐备 + 各系统未配置时的报错口径）。

### Step 2 — 建 `core/integrations/` 骨架（不动现有调用）

**状态：已落地（2026-11-16）**。`provider.py`（Protocol）、`registry.py`（注册表 +
`acquire` / `acquire_sync` / `release_all` / `describe_all` / `registered`）与包出口。
`acquire_sync` 的实现取向：**只有 provider 显式实现 `acquire_sync()` 才可用**，async-only
的直接 `TypeError`——不在同步栈里偷偷起事件循环。

### Step 3 — 迁 Zabbix（唯一真正需要持有实例的）

**状态：已落地（2026-11-16）**。落点与设计稿略有差异：

| 项 | 实际落点 |
|---|---|
| client + DTO | `core/integrations/providers/zabbix/{client,schemas}.py`（`schemas.py` 一起搬，否则 core → ingest 反向依赖） |
| provider | `core/integrations/providers/zabbix/provider.py`（只转发 `get_zapi` / `close_zapi`，不持第二份状态） |
| 注册 | `apps/ingest/apps.py.ready()`（「用不用 Zabbix」是采集域的决定） |
| 薄转发 | `apps/ingest/collectors/zabbix/client.py` 只 re-export core 的符号，`queries.py` 的 9 处调用与 `patch.object(queries, "get_zapi")` 全不动 |
| 释放钩子 | `netops/asgi.py` 的 `LIFESPAN_HOOKS`（`_release_integrations`，排最后 → 逆序先执行）+ `netops/celery.py` 的 `worker_process_shutdown` |
| 收尾健壮性 | `_dispose` 对 `logout` / `session.close()` 都兜异常：进程收尾时实例常绑在已关闭的 loop 上，**关不掉也不能炸** |

`queries.py`（查什么、怎么组装）**没有跟着搬**——那是采集语义，留在 ingest。

### Step 4 — 状态外化与多实例（T16 前完成）

**状态：已落地（2026-11-19）**。注册键本来就是 `(system, instance)`；本次补齐外化部分：

1. `core.IntegrationHealth` + 迁移 `core/0007_integration_health`，唯一键 `(system, instance)`；
2. beat 每 `INTEGRATION_PROBE_SECONDS`（默认 300）投递 `core.integrations.probe_all`，
   逐 provider `acquire()` 成功后立刻 `release()`；`ok` / `down` + error 落库；
3. `GET /api/core/integrations/` 只读列出「已注册实例 ∪ 健康行」（未探过 = `unknown`），
   复用默认权限 `IsOperatorOrReadOnly`（读：已认证即可；本接口无写操作）。
   路径挂在 core 的域前缀 `/api/core/` 下（与 `/api/core/tasks/` 一致）。

### Step 5 — Dify / 阿里云接入（按需）

**状态：阿里云已落地（2026-11-25），Dify 未做。**

阿里云的落地方式与原设想不同：它无状态、每次新建，**没有需要 core 托管的东西**，所以没有
注册成 provider，而是作为 `core/integrations/aliyun/` 的通道直接 import（同步与异步调用方
共享同一套构造逻辑，用 `acquire_sync` 只会让路径更绕）。无状态系统接进 registry 只会
换来一个恒为 `ok` 的假健康行——`acquire()` 只是构造对象，永远不会失败。Dify 同理，
接入前先确认探活语义，否则别为了「统一」硬注册。

## 与其他设计稿的关系

| 设计稿 | 关系 |
|---|---|
| [`layering.md`](layering.md) | 本方案是 core 的第三块职责（用户/认证 + 任务机制 + 外部连接实例）。依赖矩阵里 core 一行**仍是零业务依赖**——core 持有的是域交上来的 provider 对象，不 import 域 |
| [`../tasks.md`](../tasks.md) | **范本**（已落地的现状文档）。`core/tasktypes.py` 的「各域在 `ready()` 里追加业务词汇」与本方案的 provider 注册是同一范式，实现照抄 |
| [`assets-configs.md`](assets-configs.md) | 无直接关系。assets 拆 configs 不触及外部连接 |

**与 egest 的关系**：egest（配置下发 / 消息推送）将来做设备侧写操作时，取外部连接走本方案
（`core.integrations`），不需要 import 任何上游域。`layering.md` 已定 **egest 不 import ingest**
（2026-11-25）：两者方向相反，复用 napalm / netmiko 的连接管理必须上提到 core，而不是让
下发路径反向依赖采集域。**外部平台连接归 core 的 integrations，被管设备连接仍归 assets 的
`DeviceConnection`**。

## 待定项

| # | 待定 | 影响 |
|---|---|---|
| 1 | `instance` 命名：固定枚举（`prod`/`test`/`default`）还是允许自定义名（如 `zabbix-生产机房`） | 后者对 T16 的「实例职责边界」更友好，但要求可读且唯一 |
| 2 | 健康状态落 DB 还是 Redis | 本文倾向 DB（要记「上次成功时间」供对账） |
| 3 | `DeviceConnection` 的明文密码要不要一并治 | 与本方案**边界不同**（被管设备 vs 外部平台），但同属「凭据存储」问题，可一起排期 |
| 4 | MCP 工具能否直接用 core 的 client 实例 | `llmtools/registry.py` 现有硬规矩是「不 import core 业务模块」；`core.integrations` 是否算「业务模块」需明确，否则 MCP 工具只能走各域自带的 `zabbix_*` / `aliyun_*` 工具 |

## 附带发现（不在本方案范围）

1. **`handbook/roadmap.md` 与代码不一致**：roadmap 写「McpToolCall 审计表（core）✅」，
   但在 `develop` 与所有本地分支都搜不到该模型定义（只在 roadmap 文本里命中）。
   写侧审计要落地的话，这张表得先补。
2. **MCP 出口当前是匿名的**：`netops/mcp.py` 注明「能访问到 `/mcp` 就能调工具」。
   外部写侧工具开放前必须先补鉴权，否则等于把写操作裸露出去。
