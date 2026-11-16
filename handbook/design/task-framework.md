# core 承载通用任务机制

> **状态：实施中（2026-11-16 起）。步骤 1 已落地，步骤 2 / 3 未动。**
> 分层总图与依赖矩阵见 [`layering.md`](layering.md)。
> 进度与实测差异见文末 §「实施进度」——**别拿本文当现状**，现状看
> [`../ingest.md`](../ingest.md)。

## 结论先行

**`Task` / `Stage` 留在 core**，任务控制函数下沉到 core，**其他域引用 core 的任务 API**
来实现自己的阶段。

这与「把 Task/Stage 搬到 ingest」相反——搬到 ingest 会让 core 依赖 ingest，
core 就不是底层服务了。

## 现状实测

### 任务链路不是「读 Redis 改记录」

Redis 只是**投递通道**，不是状态来源。真实链路：

```
创建 Task（写 PostgreSQL，status=running）
    ↓
dispatch_stage() → 创建 Stage（status=running）→ .delay() 投递到 Redis
    ↓
worker 取出消息 → 执行 ingest/tasks.py 里的 @shared_task
    ↓
任务体直接 UPDATE Stage.status / Task.status（写 PostgreSQL）
    ↓
Stage 的 post_save 信号 → 判断下一阶段 → dispatch_stage() 循环
```

**状态存 PostgreSQL，不存 Redis。** Redis 不可达时任务记录会停在 running 或被标记
failed（`start_task` 里有 try/except 兜底，`workflow.py:73-84`）。

这 对分层是好事——任务状态不依赖 Redis 生命周期，worker 重启不丢记录。

### core 对 assets 只有一行

```python
# apps/core/models.py:115
device = models.ForeignKey("assets.Device", on_delete=models.SET_NULL, null=True, blank=True,
                            related_name="tasks", verbose_name="关联设备")
```

core 的其余模型（`User` / `Token` / `UserPreference`）只依赖 `settings.AUTH_USER_MODEL`。

### 但控制函数分裂在两半

| 函数 | 位置 | 谁在用 |
|---|---|---|
| `start_task()` | `ingest/workflow.py:64` | core 的 serializer 调它 |
| `dispatch_stage()` | `ingest/workflow.py:46` | ingest 的信号调它 |
| `cancel_task()` | `ingest/workflow.py:103` | core 的 view 调它 |
| 阶段推进信号 | `ingest/signals.py:28` | 监听 `core.Stage` |
| `_NEXT_STAGE` 表 | `ingest/signals.py:28` | ingest |

**core 持有模型和 API，却调用 ingest 的函数；ingest 持有控制逻辑，却操作 core 的模型。**
这是「模型与控制分离」的半成品状态，也正是 core 依赖 assets 的根源——
`start_task(device, ...)` 的签名里就有 `Device`。

### core 对 ingest 的 4 处依赖

| 位置 | 依赖 |
|---|---|
| `core/api/serializers.py:195` | `from ingest.workflow import start_task` |
| `core/api/views.py:72` | `from ingest.workflow import cancel_task` |
| `core/api/serializers.py:4` | 注释 |
| `core/api/views.py:4` | 注释 |

## 目标形态

### core 提供通用任务机制（不含业务词汇）

```python
# core/tasks.py（新增）
def create_task(task_type: str, *, params=None, device=None) -> Task: ...
def dispatch(task: Task, stage_type: str, input_data=None) -> Stage: ...
def cancel(task: Task) -> None: ...

# core/task_types.py（新增）—— 注册表，各业务域在 ready() 里注册
def register_task_type(task_type: str, label: str, first_stage: str) -> None: ...
def register_stage(stage_type: str, label: str, handler) -> None: ...
def label_for(kind: str) -> str: ...
def first_stage_of(task_type: str) -> str: ...
```

`dispatch` 的 handler **从注册表按 `stage_type` 解析，不再由调用方传参**。
两条硬边界（2026-11-16 评审补）：

1. **handler 不能跨 broker 传递**——Celery 消息必须可序列化，函数对象过不了 Redis。
   所以 handler 的解析只能发生在**投递方进程内**：`dispatch` 是同进程函数，从注册表
   拿到 Celery task 对象后 `.delay()` 投递；`dispatch` 自己永远不是 Celery 任务。
   （原文「dispatch 接受一个 handler」是同进程语义没错，但会把难题甩给调用方——
   core 的 serializer 手里没有 handler 可传，这正是「first_stage 硬编码」矛盾的根源。）
2. **注册表是唯一 resolve 点**——core 的 API（建任务）、ingest 的推进信号都只传
   `stage_type` 字符串，由注册表换 handler。core 仍不认识任何业务模块：
   注册动作由业务域主动发起（业务域 → core），方向不倒。

### 业务域提供阶段实现

```python
# ingest/apps.py（改造后）
def ready():
    from core.task_types import register_task_type, register_stage
    from ingest.tasks import run_collection_stage, run_parsing_stage, run_storage_stage

    register_task_type("collect_config", "采集配置", first_stage="collection")
    register_task_type("batch_collect", "批量采集", first_stage="collection")
    register_stage("collection", "数据采集", run_collection_stage)
    register_stage("parsing", "配置解析", run_parsing_stage)
    register_stage("storage", "数据存储", run_storage_stage)
```

`_NEXT_STAGE` 推进表仍留在 ingest（见下节方案 A），不进注册表——
「下一个阶段是什么」是链路知识，不是通用机制。

### 阶段推进

现状推进信号在 ingest（`ingest/signals.py:28`，监听 `sender="core.Stage"`）。
这已经是「上层驱动下层」的形态，**方向合法 ✓**，可以保留。

**但要注意**：`ingest/signals.py` 里 `from ingest.workflow import dispatch_stage` 要改成
`from core.tasks import dispatch`；handler 不再由信号侧查 `_STAGE_HANDLERS` 传参，
`dispatch` 内部按 `stage_type` 从 core 注册表解析。注册表与方案 A 不冲突：
core 的注册表由业务域主动注册（方向仍是业务域 → core），core 不反向认识任何域。

**推进表放哪？** 两个选择：

| 方案 | 做法 | 代价 |
|---|---|---|
| A. 保留在 ingest（推荐） | 推进表 `_NEXT_STAGE` 在 ingest，信号接收器也在 ingest | 改动最小；core 完全不认识 ingest |
| B. 下沉到 core | core 提供 `register_chain()`，业务域在 `ready()` 里注册 | core 要提供注册表机制；core 仍不认识具体阶段名 |

**推荐 A**——core 只提供 `dispatch` 这个动作，「下一个阶段是什么」是业务知识，
属于业务域。

## 必须处理的三件事

### ① `Task.device` —— 唯一的硬骨头

这是 core 依赖 assets 的唯一来源，也是唯一有真实代价的改动。

| 方案 | 做法 | 代价 |
|---|---|---|
| A. 保留 FK | `Task.device → assets.Device` 不动 | core 仍依赖 assets ✗ 分层不成立 |
| B. 去掉 device 字段 | 设备信息进 `params` JSON | 丢失索引与 DRF 搜索字段；`purge_configs` 的 Task 清理要改 JSON 查询 |
| C. 通用多态引用 | `target_type`（字符串）+ `target_id`（int） | 查询按 type 分派；索引不如 FK 直观 |

**推荐 C（通用多态引用）**，理由：

- `Task` 是「任务记录表」，不是业务实体表。它的作用对象是动态、多样的——
  一个设备、一批设备、一个站点、甚至无对象。用强外键表达「作用目标」本就不对，
  外键会把 core 绑死在 assets 上。
- 方案 B 把「作用目标」这个结构化概念拍平成 `params` 里的字符串，丢失了
  「这是对某个实体的引用」的语义，查询、索引、关联都不如真正的引用字段。
- 方案 C（`target_type` + `target_id`）既保留「引用一个实体」的语义，又让 core
  不认识具体业务类型：`target_type` 是自由字符串（`"device"` / `"device_group"` /
  `"site"`），`target_id` 是数字。这正是「通用任务机制」该有的形态。
- 与 `AccessFlow` 已用的「物化表不挂外键、用 JSON 数组 + GIN 索引」同一哲学：
  去具体外键、保留引用语义。

代价（可接受）：`target_type` 无外键级联、无 DB 层完整性约束，是「软引用」。
对任务记录表这正合适——设备删了任务记录本就该保留（`SET_NULL` 语义下 FK 反而不合适）。

> 注：方案 A（保留 FK）仍是「core 零 assets 依赖」目标达成前的过渡态，
> 可作为第一步的暂态；最终落点是 C。

**方案 C 的影响面**（实测）：

| 位置 | 现状 | 改后 |
|---|---|---|
| `core/models.py:115` | `device = FK("assets.Device", ...)` | `target_type = CharField` + `target_id = BigIntegerField` |
| `ingest/workflow.py:66-68` | `start_task(device, ...)` → `device=device` | `start_task(target_type="device", target_id=device.pk, ...)` |
| `ingest/tasks.py:39,68,105` | `stage.task.device` / `task.device` | 按 `target_type` / `target_id` 查（type 分派） |
| `core/api/serializers.py:153` | `device_hostname = source="device.hostname"` | 保留 `device_hostname` 字段，改由 `target_id` 反查 Device 生成（前端契约不变） |
| `core/api/views.py:30-40` | `select_related("device")` / `search_fields=("device__hostname",)` / `qs.filter(device_id=device)` | 查询按 `target_type` + `target_id` 分派；搜索字段改走 `device_hostname` 反查或注解 |
| `core/admin.py:90-123` | `device__hostname` / `task__device__hostname` / `autocomplete_fields=("device",)` | 同上；admin 的 device 过滤改 `target_type`/`target_id` |
| `purge_configs.py:163-164` | `task__device_id__in` / `device_id__in` | `task__target_type="device"` + `task__target_id__in` |

**前端契约保持不变**：`Task.device`（数字）与 `Task.device_hostname`（字符串）两个
字段继续由 serializer 输出——`device` 由 `target_type=="device"` 时的 `target_id` 映射，
`device_hostname` 由 `target_id` 反查 Device 生成。前端零改动。

**存量数据迁移（此前遗漏，2026-11-16 补）**：影响面表只列了代码改动，schema 迁移之外
还要一条 **RunPython 数据迁移**：存量行 `device_id` → `target_type="device"` +
`target_id=device_id`，并在迁移内校验计数一致（非空 `device_id` 的行数 ==
`target_type=="device"` 且 `target_id` 非空的行数），漏掉这步存量库的关联设备全部丢失。

**一处需实测确认**：`select_related("device")` 与 `search_fields=("device__hostname",)`
改成软引用后，需要按 `target_type` 分派查询。若发现查询体验明显变差，可在
`TaskViewSet` 里对 `target_type=="device"` 做一次 join（`FilteredRelation` 或子查询）
补回索引效果——这是方案 C 的实施细节，不改变方案选择。

### ② 去掉硬编码的业务词汇

```python
TASK_TYPES = ("collect_config", "backup_config", "ansible_playbook", "batch_collect", "config_backup")
STAGE_TYPES = ("collection", "parsing", "storage")
```

**这些是业务词汇**：前两个是采集语义，`collection`/`parsing`/`storage` 是 ingest 的三阶段，
`ansible_playbook` 是未来 egest 的语义。core 不该知道。

改法：

- `task_type` / `stage_type` 改成**自由字符串**（去掉 `choices`）；或
- 保留 `choices` 但注释标明「词汇表由各业务域定义，core 只做存储与流转」。

**去掉 choices 的连带影响**：`get_task_type_display()` / `get_stage_type_display()`
会失效，而 `TaskSerializer` / `StageSerializer` 用了它们
（`core/api/serializers.py:127,155`），前端也在用 `task_type_display`。

**已定方案（2026-11-16 评审修正）：去掉 `choices` 改自由字符串，display 走注册表。**

~~保留 `choices`、由业务域在 `ready()` 里往里注册~~——**此路不通**：`choices` 是
模型字段的类属性，`makemigrations` 会对 choices 漂移持续生成迁移；运行时注册会让
迁移状态与代码状态永远对不上（每注册一个词就报一次 migration drift）。

正确做法：

- 模型字段：`task_type` / `stage_type` 去掉 `choices`，纯自由字符串（一条 `AlterField`
  迁移），词汇通过 `core/task_types.py` 的 `register_task_type` / `register_stage` 注册；
- display：`TaskSerializer` / `StageSerializer` 的 `*_display` 字段改为
  `task_types.label_for(...)` 反查，前端契约（`task_type_display`）不变；
- Django 表单 / admin 若要 choices 效果，运行期读注册表快照（`task_types.choices()`）
  喂给 `ChoiceField` 与 `admin list_filter`——运行期取值，不进迁移。

### ③ core/api 的 Task/Stage 端点

`core/api/urls.py` 注册了：

```python
router.register(r"tasks", views.TaskViewSet, basename="task")
router.register(r"stages", views.StageViewSet, basename="stage")
```

Task/Stage 留在 core，**这两个端点也留在 core，URL 前缀 `/api/tasks/`、`/api/stages/`
不变**（前端零改动）。改动只是把 `from ingest.workflow import start_task` 换成
`from core.tasks import create_task`。

**注意**：`core/api/serializers.py` 的 `TaskSerializer.create()` 现在是
「建任务即投递采集阶段」——这个语义是 ingest 的。改成 core 后，core 只能提供
「建任务 + 投递第一个阶段」，**第一个阶段是什么由注册表按 task_type 查**
（注册方是业务域，"collection" 从不出现在 core 代码里）：

```python
def create(self, validated_data):
    from core import task_types
    from core.tasks import create_task
    return create_task(
        task_type=validated_data["task_type"],
        params=validated_data.get("params") or {},
        device=validated_data.get("device"),
        first_stage=task_types.first_stage_of(validated_data["task_type"]),
    )
```

这样 core 不含业务词汇，但 API 契约（建任务即投递采集）不变。
（原文示例把 `first_stage="collection"` 硬编码进 core 的 serializer，与本设计
「core 零业务词汇」自相矛盾，已按注册表方案修正。）

## core 最终形态

```
core/
├── models.py         User / Token / UserPreference / Task / Stage
├── tasks.py          create_task / dispatch / cancel（通用机制）★ 新增
├── task_types.py     业务词汇注册表（各域在 ready() 里追加）★ 新增
├── permissions.py    IsOperatorOrReadOnly
├── api/              auth / preferences / tasks / stages
└── management/       ensure_superuser / migrate_if_needed / queue_*
```

**零业务依赖，零 assets 依赖。**

## 与 egest 的关系

egest（配置下发 / 消息推送）将来也用同一套机制：

```python
# egest/apps.py
def ready():
    from core.task_types import register_task_type, register_stage
    from egest.tasks import run_push_stage

    register_task_type("config_push", "配置下发", first_stage="push")
    register_stage("push", "配置下发", run_push_stage)
```

**core 完全不知道 egest 存在**，但 egest 的任务能被 core 的 API 创建、展示、取消。

这正是「其他域创建异步任务，通过 celery 投递做记录，core 负责控制」的完整形态。

## 与 Task.device 方案 C 的配套：作用目标的表达

方案 C 下，`Task` 用两个通用字段表达「作用目标」，不 import 任何业务模型：

```python
# core/models.py
target_type = models.CharField(max_length=50, blank=True, default="")  # "device" / "device_group" / "site"
target_id   = models.BigIntegerField(null=True, blank=True)             # 目标实体主键
```

**约定**：

- `target_type` 是自由字符串（业务域在 `ready()` 里注册到 `core.task_types` 的词汇表），
  core 不解释、不预设；
- `target_id` 是目标实体的主键，配合 `target_type` 构成软引用；
- 无作用目标的任务（如「批量采集」）留空两个字段。

core 的 API 层不解释 `target_type`，但 `TaskViewSet` 的过滤、admin 搜索、
`purge_configs` 的清理按 `target_type` / `target_id` 走。查询按 type 分派，
索引不如 FK 直观，但对任务记录表是可接受的代价（见 §①）。

**如果将来 egest 要作用到非设备对象**，只需注册新的 `target_type` 词汇，
无需改 core 模型。

## 实施顺序建议

1. **建 `core/tasks.py` + `core/task_types.py` 注册表，控制函数下沉**（`start_task` /
   `dispatch_stage` / `cancel_task` 搬 core；ingest 在 `ready()` 里注册 stage handler 与
   task_type→first_stage 映射；core 的 serializer / view 改调 core 函数）——这一步
   **不动模型**，风险最低，且立刻消掉 core → ingest 的 4 处依赖；
2. **业务词汇落地**：`task_type` / `stage_type` 去 `choices` 改自由字符串（一条
   `AlterField` 迁移），serializer 的 `*_display` 改走注册表；
3. **再改 `Task.device`**（方案 C，方案 A 为过渡态）：schema 迁移 + **RunPython 数据迁移**
   （见 §①「存量数据迁移」），影响面见上表。

每步跑全量测试（基线 `822 passed, 66 subtests passed`）。

## 待定项

| # | 待定 | 影响 |
|---|---|---|
| 1 | `Task.device` 方案 A / B / C | 已定为 C（多态引用），A 为过渡态；含 RunPython 数据迁移 |
| 2 | 业务词汇注册表的具体形态 | 已定（2026-11-16）：字段去 `choices` + `core/task_types.py` 注册表（词汇 / display / first_stage / handler 四合一）；~~choices 运行时注册~~ 不可行（迁移漂移） |
| 3 | `target_type` 的取值约定 | 已定：自由字符串，与词汇同表登记；display 同表反查 |

## 实施进度

### 步骤 1 — 已落地（2026-11-16）

| 项 | 落点 |
|---|---|
| 通用机制 | `apps/core/tasks.py`：`create_task` / `dispatch` / `cancel` |
| 词汇注册表 | `apps/core/task_types.py`：`register_task_type` / `register_stage` / `label_for` / `first_stage_of` / `handler_for` / `*_choices` |
| 业务域注册 | `apps/ingest/apps.py` 的 `ready()` 登记 5 个 task_type + 3 个 stage handler |
| 调用方改道 | `core/api/serializers.py`（建任务）、`core/api/views.py`（取消）、`ingest/signals.py`（推进） |
| ingest 侧残留 | `ingest/workflow.py` 只剩 `submit_config_job`（批量导入的旁路链） |

与提案的差异（实测修正，后续步骤按这里写的为准）：

1. **`create_task` 内部反查 `first_stage`，调用方不传**。原文让 serializer 写
   `first_stage=task_types.first_stage_of(...)`，等于把「谁是第一个阶段」这个问题
   又推回 API 层；现在 core 的 API 只说「建一个 collect_config 任务」。
2. **`register_stage` 当场校验 `handler.delay`**。注册表是唯一 resolve 点，
   接错对象（比如传了普通函数）会在启动时炸，而不是等第一次投递。
3. **serializer 新增 `validate_task_type`**：未知类型返回 400。否则 `LookupError`
   会被 `create()` 的 `except` 吞成 503，客户端写错词看起来像服务端挂了。
4. **新发现的第 5、6 处 core 反向依赖**：`core/management/commands/queue_status.py`、
   `queue_backlog.py` import `analysis.queue_monitor`——原文只数了 core→ingest 的 4 处。
   按 `layering.md`「运维工具豁免」登记为**精确例外**（文件 + 模块），并由
   `tests/core/test_layering.py::test_operational_exceptions_are_still_needed` 防白名单腐化。
5. **验证方式从 grep 升级成 AST 断言**：`tests/core/test_layering.py` 扫
   `apps/core/**` 的绝对 import，新增的反向依赖直接红。

### 步骤 2 — 已落地（2026-11-16）

| 项 | 落点 |
|---|---|
| 字段去词汇 | `Task.task_type` / `Stage.stage_type` 去掉 `choices`，类属性 `TASK_TYPES` / `STAGE_TYPES` 删除；迁移 `0005_alter_stage_stage_type_alter_task_task_type`（`choices` 不进 DDL，纯状态迁移） |
| 显示名 | 覆盖 `get_task_type_display()` / `get_stage_type_display()`，实现委托 `task_types.label_for()`；未登记的旧词回落 key |
| admin | `core/admin.py` 的 `VocabularyListFilter` 基类 + `TaskTypeFilter` / `StageTypeFilter`，运行期读注册表快照 |
| 契约不变 | 序列化器的 `task_type_display` / `stage_type_display` 与前端类型零改动 |
| 锁 | `tests/core/test_task_types.py`：注册表覆盖历史词汇、字段无 `choices`、display 委托注册表；`tests/core/test_task_api.py` 新增「未注册词 → 400」 |

与提案的差异（承接上面的编号）：

6. **display 改在模型方法上，序列化器一行没动**。原文让 serializer 的 `*_display` 字段直接调
   `label_for`；但 `__str__`、admin、`ingest/signals.py` 的 `instance.get_stage_type_display()`
   都在调模型方法，只改 serializer 会留下两条反查路径。覆盖那两个方法后 core 里依然没有业务
   词汇（只是把「查哪张表」委托出去），所有调用方零改动。
7. **admin 必须显式给过滤器**。`choices` 摘掉后 `list_filter = ("task_type",)` 会静默退化成
   `AllValuesFieldListFilter`（按库里出现过的字符串过滤、没有中文标签）；改成注册表快照后
   选项带标签，业务域新登记的词自动出现，且不产生迁移。

### 步骤 3 — 未开始

- `Task.device` 方案 C：
  `tests/core/test_layering.py::test_known_debt_task_device_fk_still_points_at_assets`
  是那条债的记号，落地时删。
