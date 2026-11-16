# core 外部连接实例（`core/integrations/`）

外部系统（Zabbix / 阿里云 / Dify / 未来的 egest 写侧）的 **client 实例归 core 统管**。
业务域只交一个 provider，不交实现；core 负责懒建、复用与释放。

设计取向与未落地部分见 [`design/external-clients.md`](design/external-clients.md)；
本文只写**现在已经这么跑**的行为。

## 为什么不是「各域自己管单例」

迁移前 Zabbix 的单例住在 `apps/ingest/collectors/zabbix/zabbix.py`，形态本身是对的
（懒建 + 复用 + 显式释放），但两个问题：

1. **`close_zapi()` 全项目没有调用点**——session 一直泄漏到进程退出；
2. 实例住在业务域里，将来 egest / MCP 写侧要用同一个 client 时，只能反向 import ingest。

现在的分工：实例与生命周期归 core，**「用哪个系统、连哪个实例」归业务域**（在
`AppConfig.ready()` 里注册 provider）。

## 目录

```
apps/core/integrations/
├── __init__.py          对外出口：acquire / acquire_sync / release_all / register_provider
├── provider.py          Provider 协议（system / instance / acquire / release / describe）
├── registry.py          注册表（纯 dict，不 import models、不 import 业务域）
└── providers/
    └── zabbix/          具体系统：client.py（单例）+ schemas.py（DTO）+ provider.py
```

## 取用

```python
from core.integrations import acquire, acquire_sync

zapi = await acquire("zabbix")        # 异步 client（Zabbix / autotask 这类）
client = acquire_sync("dify")         # 同步 client：provider 需显式实现 acquire_sync()
```

规则：

- **未注册立刻报错**（`LookupError`），不返回 `None`、不静默降级——拿不到 client 就该炸，
  而不是让上游拿到空数据当成「今天没有告警」；
- `acquire_sync` **只给实现了 `acquire_sync()` 的 provider 用**。async-only 的 provider
  直接 `TypeError`：绝不在同步栈里偷偷 `asyncio.run`（会跟 Celery 任务自己的循环打架）；
- core **不缓存第二份实例**——谁持有实例由 provider 决定，否则「以为释放了其实没有」。

## 注册

方向永远是 **域 → core**（`tests/core/test_layering.py` 扫 core 的 import，反向会被拦）：

```python
# apps/ingest/apps.py
def ready(self):
    from core.integrations import register_provider
    from core.integrations.providers.zabbix import ZabbixProvider

    register_provider(ZabbixProvider())
```

同键重复注册以**最后一次**为准（测试可借此替换实现）；`registered()` 给测试与排障看。

## 释放

| 进程 | 挂载点 |
|---|---|
| ASGI（gunicorn worker） | `netops/asgi.py` 的 `LIFESPAN_HOOKS`（`_release_integrations`），由 `netops/lifespan.py` 的 `AsyncExitStack` 逆序退出 |
| Celery prefork 子进程 | `netops/celery.py` 的 `worker_process_shutdown` 信号（子进程各持一份实例，只能在这里释放） |

两处都只调 `release_all()`：逐个 provider `release()`，**单个失败只记日志**（收尾阶段不能
让一个外部系统挡住其它进程退出），并保证重复触发安全（provider 的 `release` 必须幂等）。
实例是进程内的，所以**没有跨进程的「全局释放」这回事**。

## Zabbix 这条链的具体形态

- 单例、登录、循环亲和检查都在 `providers/zabbix/client.py`：Celery 每个采集任务一次
  `asyncio.run(...)` = 一个新事件循环，实例绑在旧 loop 上就必须先释放再重建
  （`_zapi_loop is loop` 判定）。**这条判定留在 provider 实现里，不上提到 registry**——
  否则 core 得懂事件循环，provider 变成哑的。
- `apps/ingest/collectors/zabbix/zabbix.py` 是**薄转发**（`from core.integrations.providers.zabbix import ...`），
  目的是让 `queries.py` 的 9 处 `await get_zapi()` 与
  `tests/ingest/test_link_cache.py` 的 `patch.object(queries, "get_zapi")` 都不用动。
  新代码请直接走 `acquire("zabbix")`。
- `queries.py`（查什么、怎么组装）**没搬**：那是采集语义，留在 ingest。
- 进程收尾时实例常绑在已关闭的 loop 上，`_dispose` 对登出与 `session.close()` 都兜住异常
  ——迁移前 `close_zapi()` 无人调用是「不释放」，这里是「想关但关不掉也不炸」。

## 还没做的（设计稿 Step 4 / 5）

- **健康状态外化**：`IntegrationHealth` 表 + 周期 `probe_all` + `GET /api/core/integrations/`
  只读接口。实例是进程内的，要跨进程看状态必须落 DB/Redis，这部分未实现。
- **Dify / 阿里云接入 provider**：无状态、每次新建，接进来只为统一入口，收益有限，按需做。
- **多实例**：注册键已经支持 `(system, instance)`，目前只有 `default`。

## 与「被管设备连接」的边界

`assets.DeviceConnection` 存的是**网络设备**的 SSH / napalm / netmiko 连接（地址、账号、
enable 密码），属于「平台 ↔ 被管设备」；本模块管的是「平台 ↔ 外部平台」。两者不要混，
`DeviceConnection` 的明文密码问题另议（见设计稿待定项 3）。
