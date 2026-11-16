# 域分层：依赖矩阵与职责边界

> **状态：实施中（2026-11-16 起）。core 去业务依赖已全部落地；
> configs 拆分进行中（模型 / 解析 / 写入 / 序列化器已迁，admin / API / 软资产未迁）；
> ingest 收窄与外部连接收归 core 未动。**
> 代码里的依赖方向在落地前仍以 `AGENTS.md` 现有描述为准。

本文定义 network_ops 的域分层。目标不是「拆得好看」，而是让每个域**只依赖它下面的域**，
消除当前三处反向依赖与两处跨 app 外键。

## 现状实测（2026-11-16）

改之前先把事实钉住。以下数字来自对 `develop` 分支的实际扫描：

| 项 | 数字 |
|---|---|
| `apps/assets/` 代码量 | 6278 行（不含 migrations），6 个 app 里最大（analysis 5516 / ingest 5673） |
| assets 模型数 | 51（`models/__init__.py` 的 `__all__`） |
| assets REST 端点 | 49（`api/urls.py` 的 `router.register`） |
| assets 迁移文件 | 37 |
| 引用 assets 的跨模块 import | 149 处（生产 72 + 测试 77） |
| assets 内部 FK 指向 | **全部指向 assets 自己的表，零跨 app 外键** |

### 三个反向依赖（assets → ingest）

违反 `AGENTS.md` 声明的「`analysis → ingest → assets` 单向」：

| # | 位置 | 性质 |
|---|---|---|
| ① | `apps/assets/device_import.py:17` 顶层 `from ingest.config_repo import save_config` | **模块级 import**，写 Git 仓库 |
| ② | `apps/assets/api/views.py:347` 惰性 `from ingest.config_owner import resolve_config_owner` | 读设备组语义 |
| ③ | `apps/assets/device_import.py:340` 惰性 `from ingest.workflow import submit_config_job` | 投递 Celery 链 |

①③ 的根因是**「Excel 导入」这个用例整体住在 assets**，而「配置文件」sheet 恰好就是
ConfigBase 家族 24 个子类的入口。② 的根因是 `resolve_config_owner` 被 ingest 自己用着
（`ingest/pipeline.py:64`、`ingest/management/commands/purge_configs.py:25`），
搬走它会让 ingest 反过来依赖 assets。

**处置（2026-11-16 拍板）**：①③ → **Excel 导入（`device_import.py`）整体迁 ingest**，
端点随迁、URL 前缀不变；设备台账 sheet 由 ingest 调 assets 服务落库（ingest → assets ✓）。
② → `resolve_config_owner` **迁 configs**（读 `DeviceGroup` 是 configs → assets ✓，
`DeviceConfigViewSet` 本就随 DeviceConfig 归 configs）。细节见
[`assets-configs-split.md`](assets-configs-split.md)。

### 跨 app 外键（指向 assets）

| 位置 | 目标 |
|---|---|
| `apps/analysis/models/internet_analysis.py:16` | `InternetAnalysis.device → assets.Device` |

`Task.device` 原先是第二处，**2026-11-16 已改成软引用**（`target_type` + `target_id`，
见 [`../tasks.md`](../tasks.md) §作用目标），现在 core 侧一处也不剩。

`AccessFlow` 刻意**不挂外键**（用 `device_ids` / `policy_ids` JSON 数组 + GIN 索引），
说明项目已经有「物化表不依赖源表外键」的成熟做法。

### core 对 assets 的依赖已是 0

```python
# apps/core/models.py（改造前）
device = models.ForeignKey("assets.Device", on_delete=models.SET_NULL, ...)

# apps/core/models.py（现在）
target_type = models.CharField(max_length=50, blank=True, default="")
target_id = models.BigIntegerField(null=True, blank=True)
target_label = models.CharField(max_length=255, blank=True, default="")
```

「作用目标是设备时怎么校验、怎么显示名字」由 assets 在 `ready()` 里注册进
`core/task_types`（`register_target_type("device", ..., feeds_device_fields=True)`），
core 自己既没有那个外键，也不认识 `"device"` 这个词。

core 的其余模型（`User` / `Token` / `UserPreference`）只依赖 `settings.AUTH_USER_MODEL`。

**但 core 对 ingest 有 4 处**：`core/api/serializers.py:195`（`start_task`）、
`core/api/views.py:72`（`cancel_task`）、以及两处注释。加上那行外键，
core 曾传递依赖 `ingest → assets`。

> **2026-11-16 更新：这 4 处已清零。** 任务控制函数已下沉到
> `core/tasks.py`，调用方改道，注释同步改掉。现在 core 对 ingest 的 import 是 0。
>
> **同时实测出原文漏数的两处 core → analysis**：
> `core/management/commands/queue_status.py:25`、`queue_backlog.py:26` 都
> `from analysis.queue_monitor import ...`。按本表「例外与豁免」登记为运维工具例外
> （精确到「文件 + 模块」），由 `tests/core/test_layering.py` 的 AST 断言守住，
> 且例外失效会被 `test_operational_exceptions_are_still_needed` 抓出来。

## 分层总图

```
netops         项目基建：settings / urls / schema / pagination / mcp_gateway / lifespan
                ← 不属于业务分层，任何域都可引用

core           底层服务：用户 / 认证 / Token / 权限 / 用户偏好
                + 通用任务机制（Task / Stage / create / dispatch / cancel）
                + 外部连接实例与 client 生命周期（integrations/，各域注册 provider）
                ← 零业务依赖，零 assets 依赖

assets         基础资产信息：DCIM / 设备台账 / IPAM / CI 统一台账
                + 软资产扩展表（DomainAsset / LoadBalancerService）
                ← 零上层依赖（目标态：叶子节点）

configs        配置行：ConfigBase 家族 25 子类（ArpMac 改继承并入）+ DeviceConfig
                + parsers/（文本 → dict）+ savers/（写配置行）+ mapping/（键归一）
                ← → assets

ingest         采集与入库编排：Git 仓库 / Excel 导入 / 设备采集（collectors/）
                + 阶段实现（collection → parsing → storage）
                ← → assets, configs, core

egest          配置下发 / 消息推送（新增域）
                + 自己的阶段实现
                ← → assets, configs, core

analysis       前端资源整合：跨域联合查询 + 物化表
                ← → assets, configs

docs           独立功能：表格编辑 / 文档转换 / Dify 推送
                ← 零业务依赖
```

`llmtools` 是**根目录普通 Python 包、不是 Django app**，定位在所有域之上（现状如此）：

```
llmtools ← assets, configs, analysis
```

## 依赖矩阵

行 = 谁，列 = 依赖谁。✓ 允许，✗ 禁止。

|  ↓依赖 → | core | assets | configs | ingest | analysis | egest |
|---|:---:|:---:|:---:|:---:|:---:|:---:|
| **core** | — | ✗ | ✗ | ✗ | ✗ | ✗ |
| **assets** | ✓ | — | ✗ | ✗ | ✗ | ✗ |
| **configs** | ✓ | ✓ | — | ✗ | ✗ | ✗ |
| **ingest** | ✓ | ✓ | ✓ | — | ✗ | ✗ |
| **egest** | ✓ | ✓ | ✓ | ✓ | ✗ | ✗ |
| **analysis** | ✓ | ✓ | ✓ | ✓ | — | ✗ |
| **docs** | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ |

（docs 行按实测收敛：`apps/docs` 只 import Django / 三方库与自身模块，业务依赖只有
core 的认证。原矩阵把 docs 对 assets/configs/ingest/analysis 全标 ✓，与「零业务依赖」
的文字自相矛盾，2026-11-16 修正。）

三条硬约束：

1. **`core` 不依赖任何业务域。** 它是平台服务，用户 / 认证 / 权限不该认识设备。
2. **`assets` 不依赖任何上层域。** 它是事实的权威源，不该知道谁在消费它。
3. **不允许跨层**（如 ingest 直接依赖 analysis）。要跨只能走 §「跨域调用」。

**`analysis -> ingest` 是允许的**（与 `AGENTS.md` 声明的单向链一致）：analysis 作为只读消费侧，
读采集产物（链路缓存、大屏供数）是它的本职。现状三处依赖里，`dashboard.py` 的 `link_cache`
与 `rebuild_access_flows.py` 的 `request_rebuild` 方向合法、保持不动；仅 `trace.py` 的
`TMPLS_DIR` 会随 `parsers/` 归 configs 而变成 `analysis -> configs`（见
[`assets-configs-split.md`](assets-configs-split.md)）。

### 例外与豁免

| 位置 | 例外 | 理由 |
|---|---|---|
| `scripts/purge_configs.py` | 迁出 app，改为独立运维脚本 | 跨域**运维工具**，脱离业务域后不再参与依赖矩阵，豁免自然取消。见 [`assets-configs-split.md`](assets-configs-split.md) |
| `core/management/commands/queue_status.py`<br>`core/management/commands/queue_backlog.py` | import `analysis.queue_monitor`（精确到文件+模块，不是整个目录） | 队列巡检是**平台级运维命令**（`AGENTS.md` 约定运维命令统一放 core），而积压指标来自 analysis 的访问流，与 API / 前端卡片同源；复制一份会让同一份口径裂成两处实现。见 `tests/core/test_layering.py::OPERATIONAL_EXCEPTIONS` |
| `ingest/access_flow_trigger.py` | 不 import analysis，用任务名 | 见 §「跨域调用」 |
| `ingest/collectors/dashboard.py` | 不 import analysis，用任务名 | 同上 |

## 各域职责边界

### core —— 平台服务与通用任务机制

**装什么**：用户 / 认证 / Token / 权限 / 用户偏好；`Task` / `Stage` 模型与通用任务控制
（`create_task` / `dispatch` / `cancel`）；外部连接实例与 client 生命周期
（`core/integrations/`：各域在 `ready()` 里注册 provider，core 持有实例并负责释放）。

**不装什么**：设备、配置行、任何业务词汇。

现状的 `Task.task_type`（`collect_config` / `ansible_playbook` …）与
`Stage.stage_type`（`collection` / `parsing` / `storage`）是**ingest 的词汇**，
`ansible_playbook` 更是未来 egest 的词汇——core 不该知道这些。
**2026-11-16 已落成自由字符串 + 注册表**。

详见 [`../tasks.md`](../tasks.md)。

外部连接实例（Zabbix / 阿里云 / Dify 等 client）的归属见
[`external-clients.md`](external-clients.md)。它与被管设备的连接
（`assets.DeviceConnection`，SSH / napalm / netmiko）**是两回事**：
前者是「平台 ↔ 外部平台」，后者是「平台 ↔ 被管设备」，不要混。

### assets —— 基础资产信息与 CI 统一台账

**装什么**：DCIM（SecurityZone / DataCenter / Room / Cabinet）、设备台账
（Vendor / DeviceModel / Device / DeviceConnection / DeviceGroup*）、IPAM
（Tag / Subnet / IPAddress / SubnetUsageLog）、CI 统一台账（`ConfigurationItem` +
4 类 `_CIExtension` + `CIObjectLink` + `CIRelationship`）、软资产扩展表
（`DomainAsset` / `LoadBalancerService`）、DCIM 与位置维度。

**不装什么**：配置行（ConfigBase 家族）、设备配置快照（`DeviceConfig`）、
解析器、Saver。

**IPAM 留在本域**：按 `handbook/assets.md`「资产分类边界」，`SUBNET` / `IP_ADDRESS`
本来就在 `CIType.SOFT_TYPES` 里——它们**已经是软资产**。且 IPAM 只有 4 张表、
4 个端点，功能薄，不值得单列一个域。

### configs —— 配置行及其产生过程

**装什么**：`ConfigBase` + 25 个子类（含改继承并入的 ArpMac）、`DeviceConfig`；
`parsers/`（文本 → dict，纯函数）、`savers/`（写配置行）、`mapping/`（键归一）。

**为什么解析器和 Saver 归本域**：它们操作的全部是配置行模型（实测 22 个 Saver
写的模型**零例外**都是 ConfigBase 家族），产出的 `config_json` 就是本域的核心数据形态。
放在 ingest 会让「配置语义」散在两个域。

`model_paths` 用字符串路径声明写入模型（`"assets.models.Route"`），本就是为跨 app
搬移预留的设计（注释原话：「savers 的 import 时机早于 app registry 就绪是不可控的」），
迁移时只需改字符串。

### ingest —— 采集与入库编排

**装什么**：Git 配置仓库（`config_repo.py`）、Excel 导入（含 `device_import.py` 模块
与其端点，自 assets 整体迁入，URL 前缀不变）、采集器（`collectors/`）、
阶段推进编排（`workflow.py`）。

**不装什么**：配置语义（解析、归一、写入配置行都归 configs）。

按新分层，ingest 只负责「**把配置原文弄到手**」，不碰配置长什么样。

### egest —— 配置下发与消息推送（新增域）

**装什么**：配置下发、设备侧写操作、消息推送；自己的阶段实现。

**待定**：是否复用 ingest 的采集通道（`napalm` / `netmiko` 连接管理）。若复用，
egest 会依赖 ingest 的连接管理代码——那可能更适合做成 ingest 的子模块而非独立 app。

### analysis —— 前端资源整合

**装什么**：跨域联合查询接口；物化表（`AccessFlow` / `InternetAnalysis` 已是此模式）；
给 MCP 用的简化模型。

**不装什么**：源表的事实（配置行归 configs，CI 台账归 assets）。

物化表**不挂源表外键**（`AccessFlow` 用 `device_ids` JSON 数组 + GIN 索引），
这条现有做法继续沿用。

### docs —— 独立功能

表格编辑 / 文档转换 / Dify 推送。与设备、配置无关，只依赖 core 的认证。

## 跨域调用：Celery 任务名机制

上层要触发下层、或同级要触发对方时，**不 import 对方的模块**，用任务名 + `send_task`。

范本 `apps/ingest/access_flow_trigger.py`（原文口径）：

> ingest 不许 import analysis。所以这里不 import 任务对象，而是按
> `settings.ACCESS_FLOW_TASK` 的**任务名字符串** send_task。

机制要点：

1. 任务名的唯一定义处是 `settings.ACCESS_FLOW_TASK`；
2. 任务装饰器的 `name=` 与 `CELERY_TASK_ROUTES` 的 key 必须一致；
3. `tests/analysis/test_access_flow_task.py` 有对账断言，改名不同步直接红；
4. 投递方不 import 任务对象，worker 收到后按名字查自己的注册表执行
   （`autodiscover_tasks` 已加载各域 tasks）；
5. broker 不可达**只告警不抛出**——主链路已成功，重建晚一点没关系。

**新增跨域调用照抄这套**：加 `settings.XXX_TASK` 常量 + 任务装饰器 `name=` +
`CELERY_TASK_ROUTES` key + 对账测试。

同进程内的普通函数调用**不受此限**——只要方向合法（上层调下层），
直接 import 是可以的。

**例外：事务性跨域写入不走 Celery。** 需要同进程同事务保证原子性的跨域协作
（如软资产归并：configs 计算 + assets 落库共享一个 `pg_advisory_xact_lock`），
用**同进程服务函数调用**串联，不走任务名。判断标准：**跨域协作是否需要与调用方
共享事务边界**——需要就同进程调用，不需要就走 Celery 任务名。详见
[`assets-configs-split.md`](assets-configs-split.md)。

## 跨域写入：写入权归属

跨域写入**走服务调用，不直接 ORM 写对方的表**。每张表的写入权明确归属：

| 表 | 写入权 | 其他域怎么写 |
|---|---|---|
| `ConfigurationItem`（CI 主表） | **assets** | 调 assets 的 service |
| `DomainAsset` / `LoadBalancerService` | **assets** | 调 assets 的 `apply_soft_assets` |
| ConfigBase 家族 25 表（含 ArpMac） | **configs** | 调 configs 的 Saver |
| `DeviceConfig` | **configs** | — |
| `Task` / `Stage` | **core** | 调 core 的任务 API |
| `AccessFlow` / `InternetAnalysis` | **analysis** | — |

这条约束不是形式主义：CI 主表将来加字段时，写入方若散在两个域，
「谁负责填这个字段」会立刻变成扯皮。

## URL 前缀不变

拆分是内部结构调整，**前端零改动**。因此：

- 端点搬家但**路径字符串不变**（`/api/assets/devices/` 搬走也还是这个路径）；
- 范本：analysis 从 ingest 拆出时沿用了 `/api/trace/`、`/api/internet-analysis/`
  （见 `netops/urls.py` 注释「URL 前缀沿用拆分前的 /api/trace/、/api/internet-analysis/（前端零改动）」）；
- `netops/urls.py` 里多个 app 的 `include` 可以挂在同一前缀下，不冲突。

## 与 `AGENTS.md` 的关系

`AGENTS.md`「项目结构」一节现在写的是：

> **依赖方向**：`llmtools → apps`，`analysis → ingest → assets`（单向）。`assets` 不许 import
> `ingest`；`ingest` 除 `purge_configs` 这类跨域运维工具外不许 import `analysis`

**这套描述与本文的分层不一致**（本文把 ingest 拆成 ingest + configs，把 core 的
任务机制单列）。落地时需同步更新 `AGENTS.md`——在代码改动落地前，`AGENTS.md` 保持现状。

**切换时机（唯一、可判定）**：`configs` app 首次通过全量测试那一刻。

- 在此之前：`AGENTS.md` 的「项目结构 / 依赖方向」一节顶部加一行临时指引：
  `分层规范以 handbook/design/layering.md 为准（实施中，未完全落地）`。
- 之后：用新的分层描述替换旧的 `analysis → ingest → assets` 单向描述，删除临时指引。

## 实施顺序建议

分层是全局约束，**不要一次性全改**。建议按「先让下层变干净」的顺序：

1. **core 去除业务依赖**（✅ 2026-11-16 已落地，现状见 [`../tasks.md`](../tasks.md)）
   ——core 变叶子后，上面的拆分才有稳定的基座；
2. **拆 configs 域**（[`assets-configs-split.md`](assets-configs-split.md)）——迁模型、
   迁 parsers/savers、拆软资产归并；
3. **ingest 收窄**——去掉配置语义，只留采集与编排；
4. **外部连接收归 core**（[`external-clients.md`](external-clients.md)）。

   `egest`（配置下发 / 消息推送）是 roadmap 的**未来功能**，不在本批实施范围内，
   此处不安排落地步骤。依赖矩阵里的 `egest` 行只表达目标态的依赖方向。
5. **llmtools 域目录调整**——按话题而非 app 划分。

   **注意（2026-11-16 评审修正）**：llmtools 的 **import 修复不能等到第 5 步**——
   第 2 步模型搬走的瞬间，`llmtools/domains/assets/` 里 ConfigBase 家族的 import
   就断，必须与第 2 步**同提交**落地（只改 import 来源，保证测试全绿）；能独立推迟的
   只有目录改名这一项。**结果**：import 修复随切片 2/3 落地，目录改名（`assets/` →
   `network/`）作为切片 5 单独提交，第 5 步已收尾。

每一步都要能独立跑通全量测试（基线：`822 passed, 66 subtests passed`）。
