# tasks：core 的通用任务机制

`core.Task` / `core.Stage` 是**平台级**异步任务记录：各域都能建任务、都能被取消、进度都能在
同一张列表里看，但 core 不认识任何具体业务。业务域在 `AppConfig.ready()` 里把自己的词汇、
阶段实现、作用目标解析器注册进来，core 只在需要时按 key 反查。

> 这么分层的理由与依赖矩阵见 [`design/layering.md`](design/layering.md)（已基本落地，
> 现状与矩阵一致；只剩外部连接的部分步骤未做）。**任务链路的业务视角**——ingest 的三阶段怎么跑、
> 信号怎么防重入——在 [`ingest.md`](ingest.md)，本文不重复。

## 模块分工

| 位置 | 职责 | 出现业务词汇 |
|---|---|---|
| `apps/core/models.py` | `Task` / `Stage` 两张表 | ✗ |
| `apps/core/tasks.py` | `create_task` / `dispatch` / `cancel` | ✗ |
| `apps/core/task_types.py` | 词汇注册表（任务类型 / 阶段 / 作用目标） | ✗（纯 dict） |
| `apps/core/api/` | `/api/tasks/`、`/api/stages/` 与 admin | ✗ |
| `apps/<域>/apps.py` | `ready()` 里登记词汇 | ✓ |
| `apps/<域>/tasks.py` | 阶段实现（`@shared_task`） | ✓ |

`core/task_types.py` 是第一张表，`core/tasks.py` 是唯一控制入口。**其他域不要自己
`Task.objects.create()` + `.delay()`**——绕过 `create_task` 就没有投递失败的收尾逻辑。

## 链路

```
create_task()  写 Task(status=running) → dispatch(注册表反查出的首个阶段)
    ↓
dispatch()     写 Stage(status=running) → 从注册表取 handler → handler.delay(stage.pk)
    ↓
worker         执行阶段任务 → UPDATE Stage/Task → Stage 的 post_save 信号推进下一阶段
```

四条不变量，改动时别破：

- **状态只存 PostgreSQL**。Redis 只是投递通道，worker 重启不丢记录；broker 不可达时
  任务落 `failed` 而不是停在 `running`。
- **投递失败必须收尾**。`create_task` 里 `dispatch` 抛异常时把 Task 写成 `failed` +
  `completed_at`（否则前端看到一个永远不动的进度条，失败原因只留在日志里）。
- **handler 只在投递方进程内解析**。Celery 消息必须可序列化，函数对象过不了 broker，
  所以 `dispatch` 是普通函数、永远不是 celery 任务。
- **`Task.celery_task_id` 表达「当前在跑的那次投递」**，不是整个任务的生命周期——
  一个任务推进多个阶段，每投递一次就被覆盖，用于排错与取消。

## 注册表（`core/task_types.py`）

```python
register_task_type(task_type, label, first_stage)          # 词汇 + 首个阶段
register_stage(stage_type, label, handler)                 # 词汇 + celery 任务对象
register_target_type(target_type, label, resolver, *, feeds_device_fields=False)  # 作用目标
```

| 查询函数 | 用途 | 查不到时 |
|---|---|---|
| `label_for(key)` | `*_display` 反查显示名（任务类型 + 阶段两张表合并查） | 回落 key |
| `first_stage_of(task_type)` | `create_task` 决定投第一个阶段 | `LookupError` |
| `handler_for(stage_type)` | `dispatch` 取 celery 任务 | `LookupError` |
| `is_registered_task_type(key)` | API 层校验（未知词 → 400） | `False` |
| `resolve_target_label(type, id)` | 校验作用目标存在 + 取名字 | `None` |
| `device_field_target_type()` | 谁填 `Task.device` / `device_hostname` | `""` |
| `*_choices()` | 运行期快照，喂 admin `list_filter` / DRF `ChoiceField` | `[]` |

两条硬约束：

1. **本模块顶层不许 import 任何模型**。它被业务域的 `ready()` 触发，那一刻 app registry
   还没就绪，import 模型会 `AppRegistryNotReady`。这里只维护纯 dict。
2. **`register_stage` 当场校验 `handler.delay`**。注册表是唯一 resolve 点，接错对象
   （传了普通函数）要在启动时炸，而不是等第一次投递。

三条登记函数都是**幂等**的（同 key 覆盖旧值、`feeds_device_fields` 记为最后一个声明的类型）：
`ready()` 在测试里会被重放多次，覆盖语义比「重复登记报错」省事。`label_for` 查两张表是
有意的——`task_type` 与 `stage_type` 命名空间互不相干，将来同名也不该串。

**为什么词汇不放模型字段的 `choices`**：`choices` 是类属性、会被 `makemigrations` 写进
迁移状态，运行期往 `choices` 追加词汇必然造成「代码注册了、迁移没动」的永久漂移。
所以 `Task.task_type` / `Stage.stage_type` 是自由字符串（迁移 `core/0005` 摘掉 `choices`），
显示名由模型方法 `get_task_type_display()` / `get_stage_type_display()` 委托 `label_for()`。

## 作用目标：软引用

`Task` 的作用对象是动态的（一台设备、一批设备、将来的某个站点、或者没有），用强外键表达
本就不对——外键会把 core 绑死在 assets 上。所以：

| 字段 | 类型 | 说明 |
|---|---|---|
| `target_type` | `CharField(50)` | 自由字符串，如 `"device"`；由业务域登记 |
| `target_id` | `BigIntegerField(null)` | 目标实体主键；无目标时留空 |
| `target_label` | `CharField(255)` | **建任务时记下的名字**（反规范化，见下） |

`(target_type, target_id)` 有复合索引 `task_target_idx`——软引用没有外键索引撑着，
列表过滤与 `purge_configs` 清理都靠它。

**为什么要 `target_label`**（提案里没有，落地时加的）：只有 type+id 的话，列表要显示设备名
就得回查 Device——N+1，而且 core 得 import assets 的模型。建任务时把名字记下来，列表零查询、
admin 可搜索。代价是设备改名后历史任务仍显示旧名，对任务记录这是**对的**（记录当时的状态）。

**resolver 契约**：`resolver(target_id) -> str | None`，目标不存在必须返回 `None`。
`None` 是「这个目标不成立」的唯一信号——API 据此把非法 device 拒成 400，`create_task`
据此顺带把名字写进 `target_label`。core 自己不查任何业务表。

**历史字段 `device` / `device_hostname`**：前端还在读这两个键，但它们已经不是字段了，
是 `Task` 上的一对只读 property，取值规则由注册表回答——谁在 `register_target_type` 时
声明 `feeds_device_fields=True`，谁就填它们（现状是 assets 注册的 `"device"`）。
core 里因此不出现 `"device"` 字面量。

## 新增一个任务类型要改哪几处

1. `apps/<域>/tasks.py`：写阶段的 `@shared_task`（接收 `stage_id`，自己读 Stage/Task）；
2. `apps/<域>/apps.py` 的 `ready()`：`register_task_type(...)` + `register_stage(...)`；
3. 若作用目标是新的实体类型：`register_target_type(key, label, resolver)`。

**不需要迁移**——词表在注册表里，不在字段 `choices` 里。这也是步骤 2 的主要收益：
以前加一个任务类型要改 `choices` 并生成一条空的 `AlterField` 迁移。

## 阶段推进与取消

**推进表留在业务域**。「下一个阶段是什么」是链路知识，不是通用机制——现状是
`ingest/signals.py` 的 `_NEXT_STAGE`，core 只提供 `dispatch` 这个动作。新域要串多阶段，
就在自己的 `signals.py` 里监听 `core.Stage` 的 `post_save` 并调 `core.tasks.dispatch`。

**取消是尽力而为的**。`cancel()` 里的 `revoke(terminate=True)` 要求 worker 在线、broker
可达；**真正保证链条停下的是业务域信号里那句「`task.status == "cancelled"` 就不再推进」**。
所以新域的信号里也必须抄这一句检查，否则取消只对「还没开始跑」的任务有效。

## 迁移手法：外键 → 软引用（`core/0006_task_soft_target`）

Django 自动生成的顺序是**错的**——它把 `RemoveField` 排在 `AddField` 前面，跑上去存量数据
全丢。手写迁移必须是这个顺序：

```
AddField(target_type) → AddField(target_id) → AddField(target_label)
    → RunPython(回填) → RemoveField(device) → AddIndex
```

回填内做计数校验（非空 `device_id` 的行数 == `target_type="device"` 且 `target_id` 非空的行数），
漏了这步库里的设备关联会静默清零。反向迁移把 `target_*` 写回 `device_id`。

**这类迁移必须真跑一遍**，别只信 `makemigrations --check`。做法（scratch 库，不动开发库）：

1. `DB_NAME=<scratch> migrate` 到最新 → `migrate core 0004` 回到有 `device_id` 的状态；
2. raw SQL 造一条只带 `device_id` 的任务（此时 `target_*` 列还不存在，ORM 用不了）；
3. `migrate core 0006` → 查 `target_type` / `target_id` / `target_label` 是否按预期回填、
   `device_id` 列是否已删；
4. 再 `migrate core 0005` 回退 → `device_id` 是否被写回。

## 分层守卫

`tests/core/test_layering.py` 用 AST 扫 `apps/core/**` 的**绝对 import**，core 一旦出现
业务域依赖直接红。三条防线：

| 用例 | 守什么 |
|---|---|
| `test_core_imports_no_domain_app` | core 不 import 任何业务域 |
| `test_core_models_have_no_cross_domain_foreign_key` | 字符串外键（AST 扫不到的那种）也拦住 |
| `test_operational_exceptions_are_still_needed` | 例外白名单不许腐化（例外修好要删） |

**例外白名单精确到「文件 + 模块」**，现有一条：`core/management/commands/queue_*.py`
读 `analysis.queue_monitor`——平台级队列巡检，AGENTS.md 约定运维命令统一放 core，
复制一份会让同一口径裂成两处。

## 踩坑

- **`admin.SimpleListFilter` 的 `params` 值必须是 list**。内部取 `value[-1]`，传字符串会
  静默取到末字符，过滤器看起来"不生效"却不报错。构造过滤器还要传真 `HttpRequest`（测试用
  `RequestFactory`），传 `None` / dict 能跑但类型检查不过。
- **去 `choices` 后 admin 的 `list_filter` 会静默退化**成 `AllValuesFieldListFilter`
  （按库里出现过的字符串过滤、没有中文标签）。项目用的是 `VocabularyListFilter` 基类 +
  `TaskTypeFilter` / `StageTypeFilter` / `TargetTypeFilter`，运行期读注册表快照。
- **参数校验放 `validate()`，不要放 `create()`**。视图把 `save()` 的任何异常兜成 503，
  在 `create()` 里抛「设备不存在」会让客户端以为服务端挂了。
- **未知词汇的 display 回落 key 而不是抛异常**（`label_for`）。前端展示优先，历史数据里
  出现已下线的词时不该让整个列表 500。
- **注册表在测试里会被 `reset()`**，用例之间要保证 `ready()` 已重放过，否则 `first_stage_of`
  会 `LookupError`。
- **`celery_app.control` 类型存根说是方法、运行时是 property**。写成 `control()` 直接炸；
  `cancel()` 里用 `cast("Control", celery_app.control)` 才既拿得到 `.revoke`，又保住对这个
  名字的检查（比 `type: ignore` 好）。

## 前端契约

`/api/tasks/` 的响应形状没变过，拆分前后一致：

- `device`（数字或 null）、`device_hostname`（字符串）——历史字段，语义是「作用目标是设备时」；
- `task_type` / `stage_type` 的**原始值**与 `*_display` 显示名并存；
- `progress` 由 Stage 状态现算，`stages` 内嵌阶段列表。

新域若要作用到非设备对象，前端需要读 `target_type` / `target_label` 才会看到新目标名——
`device` 系列只对设备有值。按 `device=<id>` 过滤时，若没有任何域声明设备类型，结果是**空集**
而不是全量（`views.get_queryset` 直接 `qs.none()`）。

**接口不开放改状态**。`/api/tasks/` 只有列表 / 详情 / 新建 / 取消，阶段只读；`Task` / `Stage`
的状态由 celery 阶段任务与业务域推进信号写。放开写会让库里的记录与真实执行状态脱节——
前端进度条说谎，`cancel()` 也无从判断「任务是否还在跑」。

`progress` 由当前阶段列表现算：`success` / `failed` / `skipped` 都算已完成，无阶段时为 0。
