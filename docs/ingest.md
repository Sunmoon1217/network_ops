# ingest：配置采集 → 解析 → 入库

输入是 Git 配置仓库里的设备配置原文，输出是 assets 里的资产行。
`apps/ingest/signals.py` 只是薄壳，真正的实现在 `pipeline.py`（同步路径）与
`tasks.py`（异步路径）里。

## 三条链

| 链 | 入口 | 任务 | 说明 |
|----|------|------|------|
| 阶段式工作流 | `/api/tasks/` → `workflow.start_task` | `run_collection_stage` → `run_parsing_stage` → `run_storage_stage` | 设备维度的采集/解析/存储，进度落在 `core.Stage` |
| 配置导入 | `assets.api.views._import_configs` → `workflow.submit_config_job` | `run_config_parsing` → `run_config_storage`（celery chain，两者都 `.si(config_id)`） | Excel 里的配置文件批量导入，走 DeviceConfig |
| 访问流重建 | `PolicySaver` 保存成功后 `ingest.access_flow_trigger.request_rebuild` | `analysis.rebuild_access_flows` | 见 [`analysis.md`](analysis.md) |

## 阶段推进与取消

`signals.on_stage_complete` 监听 `core.Stage` 的 post_save，按
`_NEXT_STAGE = {"collection": "parsing", "parsing": "storage"}` 推进：
storage 成功即整个任务完成（写 `status=success` + `completed_at`）。

- **阶段失败必须收尾 Task**：否则任务永远挂在「运行中」，前端只看到一个不动的进度，
  失败原因只留在 Stage 上。
- **取消的语义**：`workflow.cancel_task` 里的 `revoke(terminate=True)` 只是尽力而为
  （要求 worker 在线、broker 可达）。**真正保证链条停下的是信号里的
  「`task.status == "cancelled"` 就不再推进」**——即使撤不掉正在跑的那一次，
  它也会在下一个阶段边界停住。信号里也顺带避免 storage 完成后把 cancelled 改回 success。
- **两次防重入**：写回 `config_json` 会再次触发 DeviceConfig 的 post_save，Stage 状态回写
  也会再次触发 Stage 的 post_save，所以各有一个模块级 `set[int]` 记录正在处理的 pk。

## DeviceConfig 的两条处理路径

`signals.on_device_config_saved` 默认**同步**跑 `pipeline.run_config_pipeline`
（从 Git 读原文 → 解析 → 写回 `config_json` → 分发 Saver 入库）。

批量导入（`_import_configs`）在 `save()` 之前给实例挂 `_defer_pipeline = True`，
信号据此跳过同步流水线，由调用方投递上面那条 celery 链——否则一个请求里会串行跑
几十次同步解析。

`pipeline.py` 单独成文件（而不是塞进信号）有两个原因：重跑时不必伪造 `created` 标志
骗过信号；失败原因能作为返回值带出来（信号里只打日志，批量重跑需要知道是哪台设备、
哪个 key 失败）。`manage.py reparse` 与管理命令共用这一份逻辑，`force_parse=True`
表示忽略已有 `config_json` 重新解析（改了 TTP 模板、或补上设备厂商/型号之后需要）。

**堆叠组备机不解析**：`config_owner.resolve_config_owner` 把配置归属判给主设备，
备机的流水线直接把原因写进 `PipelineResult.skipped` 返回。

## Saver 分组规则

`registry.get_savers_for_config` 返回的是 `[(keys, saver)]`，`keys` 是**一个列表**：
一个 Saver 可能注册多个 key（`PolicySaver` 覆盖 `policies` / `acl` / `rules`）。
按 key 逐个返回会让调用方只能把第一个键的数据传进去，Saver 内部 `a or b or c` 的
短路链会把其余键的数据静默丢弃。

`registry.build_saver_payloads` 是唯一的 payload 组装口，调用方不要自己拼：

- 命中同一 Saver 的多个 key 一起传，且只传有值的键；
- 这条规则原先在 `pipeline._dispatch_savers` 与两个 Celery 存储任务里各写了一遍，
  其中 `run_storage_stage` 把 `keys`（列表）当成单个 key 用，
  `parsed_data.get(["policies", "acl"])` 直接抛 `TypeError: unhashable type`，
  凡是匹配到 Saver 的设备都存不进去。收敛到一处，避免再各写一份；
- **被引用的维表先写**：`ServiceSaver` 排在最前（pk 稳定后 Policy 才挂 M2M）。
  同批全量解析下 `PolicySaver._replace_m2m` 按最新 ids 全量重建关联；反序
  （Policy 先建关联、Service 后删改端口行）会让级联删除打断关联且无人重建。
  排序只固定 Service 的相对位置，其余保持注册顺序。

## 解析产出归一（`mapping.py`）

不同厂商/类型的解析器对**同一语义**给出的结构并不一致：

- **键级差异**：H3C 产出 `vpn_instances`、Cisco 产出 `acl`、Hillstone 产出
  `rules` / `addresses`——语义上分别是 vrfs / policies / address_books；
- **字段级差异**：Maipu / Ruijie 的静态路由用 `subnet_mask`，其余用 `mask`；
  Hillstone 的 `rule_id` / `rule_name`、Cisco 的 `acl_name` 对不上
  `PolicySaver` 期望的 `policy_id` / `name`。

两类差异收敛成声明式字典（`KEY_ALIASES` / `FIELD_ALIASES`），由
`BaseSaver.save` 在入口统一归一（键先归一、记录字段再归一），子类 `_save` 只读规范字段。

分层约定（越界即混层）：

1. **键级 / 字段级结构归一** → 声明表；
2. **值语义转换**（permit→allow、enable/disable→bool、route→layer3）→ 留在 Saver：
   那是业务规则，不是结构改名，混进声明表会被误读成「字段同义」；
3. **结构级差异**（SNMP 的 community / target_hosts 两种形态、Hillstone 扁平地址拆
   AddressBook）→ 留在 Saver：需要遍历/拼接，声明表表达不了。

声明表**不带厂商维度**：同一规范键下的字段同义性是「键的字段字典」级别的事实
（`static_routes` 下 `subnet_mask` 恒等于 `mask`，无论谁产出），按厂商拆反而会让
无型号的 device（测试里常见）归一失败。真出现「同名字段在不同厂商下含义不同」时，
再给 `FIELD_ALIASES` 加厂商维度。

两条死别名约定：源键必须有真实生产者（模板顶层 group），目标键必须有 Saver 消费，
由 `tests/ingest/test_mapping.py` 守。

`_merge` 对同义键的两份产出做**记录拼接**而不是字段合并：TTP 单条命中给 dict，
dict 与 dict 合并字段会把两条独立规则揉成一条；消费方本就要兼容 dict / list。

## 任务失败必须向上抛

`tasks.py` 里每个阶段都在 `except` 里回写 Stage/Task 状态后 `raise`：
不抛会让 Celery 把失败任务记成 `SUCCESS`，`AsyncResult` / Flower 的失败告警与重试
全部失效。

## Saver 基类（`savers/base.py`）

`BaseSaver.save` 是模板方法：先 `ingest.mapping.normalize_config` 归一键与字段，
再交给子类 `_save`。归一放在这一口而不是 pipeline，是为了让**绕过分发直调 `save`**
的调用方（命令重跑、测试）拿到同样的规范结构。

`device_types` / `keys` / `model_paths` 三个类属性即注册契约：
`keys` 是消费的**原始**产出键（含别名），注册表按原始键分组，保证解析产出的每个键
都有消费方；`model_paths` 是写入模型的点路径（首个是主模型），接口清单与契约测试用它
回答「这个关键字最终进哪些表」。

### 为什么批量写

`upsert` 走序列化器（`partial=True` + 把 `device` 放进 payload——带
`unique_together(device, ...)` 的模型，DRF 的 `UniqueTogetherValidator` 在 create 时
会强制要求这些字段，仅靠 `save(device=device)` 注入过不了校验）。

`bulk_upsert` 把「每行一次 SELECT + 一次 INSERT/UPDATE」压成「一次 SELECT +
一次 bulk_create / 一次 bulk_update」。理由是本机的 Postgres 跑在容器里、经宿主机端口
映射，**每跳往返约 0.95 ms**，语句条数就是主要成本——逐行写时一次导入能发出上万条
SQL；实测 `PolicySaver` 平均 19.8 条 SQL/行、`LBPoolSaver` 10 条/行。

配套约定：

- 给了 `serializer_cls` 就逐行走序列化器校验，**保证 views 与 savers 共用同一套字段
  规则**；不给就直接落库（原本就用原生 ORM 的 Saver）；
- **不支持 M2M**：带 M2M 的模型（`Policy` / `NatRule`）关联表由调用方自己写；
- 同批同键按顺序后者覆盖（与逐条 upsert 一致），不去重会直接撞唯一约束；
- `bulk_update` 不走 `pre_save`，`auto_now` 的 `updated_at` 得自己填。

### 名字清理为什么在 Python 侧

F5 配置里对象名普遍带 `/Common/` 分区前缀，库里存末段（`_leaf`），关联也依赖两边写法
一致。清理不放在 TTP 模板里：模板函数做不了整串替换——`replaceall` 是逐字符语义，
`re()` 又只认 `<vars>` 里声明的名字、且是「从行里抓取」的匹配函数，链在 `strip('"')`
之后拿不到标量。

### 启停状态双轨

`status_enabled(item, *legacy_keys)` 是新旧形态并存期的统一入口：新形态是模板统一后
的 `enabled` int 0/1；旧/手工形态是 `status` / `rule_status` / `pool_status` /
`member_status` 等 str（`enabled/disabled`、`enable/disable`）。都没有时用 `default`，
给手工 payload 兜底。

## 负载均衡 Saver 的约定（`savers/lb.py`）

- **`virtuals` 里的 profiles / rules / persist 是设备级清单**（`LtmProfile` /
  `LtmIRule` / `LtmPersist` 没有指向 virtual server 的外键），所以在
  `LBVirtualServerSaver` 里一并落库，来源记进 `raw`；同名被多个 virtual 引用时只留
  一条（后来者覆盖，与逐条 upsert 一致）；
- **`LtmPoolMember` 没有独立自然键**，只能「先清后建」；清理范围按「设备 + 池名」圈定
  ——只按 `pool_name` 全局匹配会误删其他设备上同名池的成员。池在配置里出现过就以配置
  为准（成员清空也要删旧记录）；
- **显式 0 必须留住**（`pool_order=0`、`member ratio=0` 都是合法值），只有 `None` 才兜底；
  早期写成 `x or 1` 会把 `ratio=0` 静默改成 1；
- `GtmPool.fallback_ip` 是 `GenericIPAddressField`，空串会被序列化器判非法，所以只在
  有值时才放进 payload。

`virtuals` 里 profiles / rules / persist 的实测三种形态（TTP 单条命中给 dict 而不是 list）：

```python
profiles -> [{"name": "/Common/http"}, ...]
rules    -> {"name": ["/Common/irule_redirect"]}
persist  -> {"name": "/Common/cookie"}
```

## 防火墙 Saver 的映射约定（`savers/firewall.py`）

### AddressBookSaver

hillstone 模板用动态组名 `addresses.{{ address_name }}`，产出形如：

```python
{"addresses": {"office": {"ip": ["10.0.0.0/24"]},
               "web": {"host": ["1.1.1.1"],
                       "range": [["3.3.3.1", "3.3.3.10"]]}}}
```

**地址簿名在字典的键上、不在记录体里**，所以父记录按字典键建
（`address_type="addressbook"`），各地址条目作为 `parent` 指向它的子记录。
父记录刚批量写完就一次把 pk 取回来（早期版本每本书都要再 `filter().first()` 查一次）。

尚未落库的内容：`address "其他地址簿"` 这种地址簿引用，模型没有对应字段，
只能记进 `description`。

### NatRuleSaver

`cisco_fw.ttp` 的 nat group 产出的是 ASA 的「object network + nat static」结构，
与 `NatRule` 模型不是一一对应：

| 模型字段 | 来源 |
|----------|------|
| `name` | `network_name` |
| `order` | 产出列表序号（模型上是 `unique(device, order)`，故用它做 upsert 键） |
| `nat_type` | 固定 `dnat`：`nat (inside,outside) static` 是入向目的地址转换 |
| `source_addresses` | `host_ip`，先落成 AddressBook 再关联 |
| `translated_destination` | `public_ip`，同样先落成 AddressBook（`get_or_create`，同名地址簿可能是人工维护的，不擅自改它的地址） |
| `description` | `nat (inside,outside)` 的接口对 |
| `services` | 留空：cisco 的 nat group 给不出任何服务信息 |

配置里没写的维度（目标地址、服务）在库里就是空的，这也是这三个 M2M 改成
`blank=True` 的原因。

### ServiceSaver

一个 service 块的多行（`tcp 22` / `udp 53`）是同一个名字下的多个端口定义，
**逐行落库、不合并**（合并会把多协议压进一条 protocol/port，udp 语义丢失、
port 变成 `"22,53"` 脏值——2026-09 修复）。落库方式是**自然键差量**而不是
「先清后建」：在的行原样复用（pk 稳定 → 策略 M2M 不被级联打断），只建缺失、删多余；
多余行 = 配置里真删掉的端口行，其关联靠 `PolicySaver` 同批 `_replace_m2m` 全量重建，
顺序由 `build_saver_payloads` 保证 ServiceSaver 先跑。

`_entries` 兼容三种形态（结构级差异，按分层约定留在 Saver）：

1. 平铺单条 `{name: ..., protocol: ...}`——手工喂入 / 普通组单条命中；
2. 动态字典 `{服务名: 内容}`——hillstone 动态组名 `services.{{ service_name }}`，
   内容单行给 dict、多行给 list（TTP 单/多条规则）；
3. 旧的带星列表 `[{服务名: 内容}, ...]`——去星前的存量 `config_json` 兜底。

src 行单独成行：`port` 照落端口值、`description` 标注 `src: ...` 保留源端口语义
（表里没有独立的源端口字段）。

### PolicySaver

三种原始键（`policies` / `acl`(cisco) / `rules`(hillstone)）与字段差异已在
`BaseSaver.save` 入口由 `ingest.mapping` 归一，Saver 内部只处理**值语义**与
hillstone 的结构级特征。

hillstone 的地址按来源分列：

- `-ip`：带 `/` 是子网（顺带拆出 `ip_netmask`），不带是主机；
- `-addr`：**地址簿引用**，按名字取用；地址簿不存在时先建占位记录，内容留给
  AddressBookSaver 去填；
- `-range`：`"起始 结束"` 形式，拆成 `ip_start` / `ip_end`；
- `-host`：主机地址。

两条容易改坏的约束：

- **服务只按名字定位、协议未知时先记 `any`**，且不能用 `bulk_upsert`：它会用 payload
  覆盖已有记录，把 ServiceSaver 填好的 protocol 冲成 `any`。同名允许多行端口定义，
  所以 `name → [pk...]`（引用一个服务名 = 挂它的全部端口行），不能用 `name → 单 pk`。
- **计数只上报策略本身**：地址簿与服务的账由各自的 Saver 报，这里再计一遍会让
  流水线汇总重复。

`_replace_m2m` 直接写 through 表（逐条 `m2m.set()` 每个策略要发 3 条左右语句），
用 `attname` 而不是字段名——字段名描述符只接受模型实例，传 pk 会报
`must be a Policy instance`。

## 管理命令

| 命令 | 用途 |
|------|------|
| `manage.py reparse` | 重跑已入库配置的解析与入库（`force_parse` 语义） |
| `manage.py purge_configs` | 清理配置解析产物（默认 dry-run，含 analysis 的缓存） |
| `manage.py import_server_owners` | xlsx 导入服务器负责人 |

### `purge_configs` 为什么存在

配置**原文**只存在一份（Git 仓库），但**解析结果**写进了各资产表，而这些表与
`DeviceConfig` 之间**没有任何外键**——删 `DeviceConfig`、删仓库都不会级联清掉它们，
手工清又容易漏。本命令把「哪些行来自配置解析」集中到一处，并且默认只报告。

「配置解析产物」用 `ConfigBase.__subclasses__()` 运行时枚举，这个定义自维护：新增 Saver
或模型自动纳入（实测 Saver 里写的模型全是 `ConfigBase` 子类，没有漏网之鱼）。
`InternetAnalysis` / `AccessFlow` 住在 analysis app，但清理仍归本命令——它是跨域的
运维工具（工具层允许跨域 import）。

边界（报告里也会逐条列出）：

- `--with-workflow` 默认关闭：Task/Stage 是工作流历史，但 `Stage.output_data` 可能存着
  配置**全文**（`run_collection_stage` 会写 `{"config": ...}`），要清得显式加；
- `--purge-repo` 删的是**整个**仓库，所以强制要求 `--all`；Git 历史里的原文不做重写；
- 人工 / Excel / 运行态采集的数据不会动。注意 `Route` / `Vrf` 同时也是运行态采集接口
  （`/api/trace/route-collect*`）的落点，与解析产物共用一张表，按表清无法区分来源；
- 堆叠组：备机不持有配置，产物记在**主设备**名下，所以 `--device <备机>` 会自动折算到
  主设备；
- 数据库删除在一个事务里，文件系统删除不能回滚，放在事务提交之后。
