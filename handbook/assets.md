# assets：资产模型、API 与导入

## 模型

模型用 `apps/assets/models/` 包，`__init__.py` **只做 re-export、不写模型定义**，并用
`__all__` 显式列出 51 个公开名字（与 `analysis/models/` 同一套做法，不用 `noqa: F401`）：
历史网络域模型集中在 `network.py`（原单文件 `models.py` 的内容一字未改，35 处跨类直接引用
都还在同一模块，无循环 import），统一配置项体系（T1）在 `ci.py`。`from assets.models import X`
与 `app_label` 不变，历史迁移照样对得上。
**不能同时留 `models.py` 与 `models/`**（包优先，单文件被静默忽略）。配置解析产物都继承
`ConfigBase`，`purge_configs` 用 `ConfigBase.__subclasses__()` 运行时枚举它们（当前 24 个子类，
其中 22 个已配 Saver）。

| 领域 | 模型 |
|------|------|
| DCIM | SecurityZone, DataCenter, Room, Cabinet |
| 设备 | Vendor, DeviceModel, Device, DeviceConnection, DeviceConfig, DeviceAccount, DeviceGroup, DeviceGroupMember |
| 配置基类 | `ConfigBase`（被 Vrf / Interface / LTM / GTM / 防火墙等模型继承） |
| 网络 | Vlan, Vrf, Interface, SnmpConfig, NtpConfig, SyslogConfig |
| 负载均衡 LTM | LtmVirtualServer, LtmPool, LtmPoolMember, LtmProfile, LtmIRule, LtmSNAT, LtmPersist |
| 全局负载均衡 GTM | GtmDatacenter, GtmWideip, GtmPool, GtmServer, GtmVServer |
| 防火墙 | AddressBook, Service, Policy, NatRule |
| IPAM | Tag, Subnet, IPAddress, SubnetUsageLog |
| 路由与其它 | Route, Topology, ArpMac |
| 人工维护 | ServerOwner（服务器 IP ↔ 负责人；不从设备配置提取，故不进 `ConfigBase`） |

两条容易踩的：`Topology` 是单模型，图数据存 `graph_data` JSON，没有独立的节点/边表；
`Device` 没有 `address` 字段，地址在 `DeviceConnection` 里。

`ConfigBase` 化的代价与 `LtmPoolMember` 的 `pool_name` 取舍见 [`ingest.md`](ingest.md)。

几条约束的理由：

| 模型 | 约束 | 为什么 |
|------|------|--------|
| `Service` | 行级自然键 `(device, name, protocol, port, port2)` | 一个服务名允许多行端口定义（`tcp 22` 与 `udp 53` 各一行）。2026-09 前按 `(device, name)` 唯一，多协议端口被迫合并进一条 protocol/port，udp 语义直接丢失。仍按设备隔离：不同设备可以有同名服务 |
| `LtmPoolMember` | 唯一性带 `port` | F5 同一节点可以在多个端口上做成员；剥掉 `/Common/node_a:80` 的端口后 name 都是 `node_a`，只约束 name 会误杀 |
| `NatRule` | 三个匹配维度 `blank=True` | 不同厂商能提供的信息差别很大（cisco 的 nat group 只有 host/public_ip，完全给不出 service） |
| `Subnet.network` 及同类 CIDR 字段 | `max_length=45` | IPv6 CIDR 全展开最长 43 字符（`ffff:...:ffff/128`），18 只够 IPv4 |

## 统一配置项体系（T1）

现阶段目标是**资产信息的录入与查询**（见 [`roadmap.md`](roadmap.md)「现阶段目标与范围边界」），
不含生命周期管理。这一层给所有资产一个跨类型的统一身份与查询入口，是 T2 业务归属、
T3 统一关系表、T6 统一资产目录的基础。

| 模型 | 作用 |
|------|------|
| `ConfigurationItem` | 主表：`ci_id` / `ci_type` / `name` / `description` / `tags` / `monitor_status` + 时间戳；公共属性上收在这里 |
| `PhysicalServer` / `VirtualMachine` / `DatabaseInstance` / `ApplicationService` | 4 类新增 CI 的专属属性，一对一挂主表（`_CIExtension` 抽象基类） |

几条容易踩的：

- **`ci_id` 是稳定锚点，不是主键也不是名字**：格式 `CI-<12位hex>`，创建时生成、之后永不改；
  T15 自动纳管会把它写进 Zabbix 主机标签，改名等于锚点失效。类型**不**编进标识，纳管按
  `ci_type` 字段路由实例。序列化器与 admin 都把它设为只读。
- **CI 台账刻意不继承 `ConfigBase`**：`purge_configs` 靠 `ConfigBase.__subclasses__()` 枚举清理
  配置解析产物（见 [`ingest.md`](ingest.md)），CI 是人工录入 / 导入维护的台账，不能被一并清掉。
  契约测试 `tests/assets/test_configuration_item.py` 锁住这条。
- **`monitor_status` 是 T15 状态回写的预留落点**：与业务状态分离，现阶段只是空字段、只读，
  不接任何回写 / 对账逻辑。T2 的业务归属字段（负责人 / 业务 / 部门 / 环境）是告警富化的数据源，
  字段命名要按「能直接塞进告警上下文」来定。
- **`ci_type` 类型词汇集中在 `CIType`**（字符串常量，不用 `Enum`——同值字符串与 Enum 成员哈希不同，
  作为 dict 键会查不到）。现阶段只落地 4 类新增 CI；其余类型是现有资产模型的类型词汇，
  T4 接入统一 CI 时按此清单路由。
- **扩展模型必须挂在匹配类型的 CI 上**：模型 `save()` 抛 `ValueError` 兜住 ORM 直写，
  序列化器 `CIExtensionSerializerMixin` 在 API 层挡成 400（否则 ValueError 会变 500）。
- **关系不在这里建外键**：VM→宿主机、DB→主机等归 T3 统一关系表（只存 `ci_id` + 关系类型），
  扩展模型里只留 `host_name` 之类的名字字段，避免每加一类资产都回改字段。

API（`/api/assets/`）：`configuration-items/`（列表支持 `?ci_type=`、`search`、分页）、
`physical-servers/`、`virtual-machines/`、`database-instances/`、`application-services/`。
列表分页走全局 `StandardPagination`，统一检索直接在主表上做，不需要把配置链全量算进内存。

## 统一关系表（T3）

T3 只做**跨类型关系的录入与查询**，不物化传递闭包、不替代现有外键 / M2M。

| 模型 | 作用 |
|------|------|
| `CIRelationship` | 一条直接关系：`src_ci_id --[relation_type]--> dst_ci_id` + 时间戳 |
| `CIRelationType` | 六类关系词汇：`runs_on` / `depends_on` / `deployed_on` / `connected_to` / `located_in` / `member_of` |

几条约定：

- **两端存 `ci_id` 字符串，不建外键**：关系两端可以是任意 CI 类型（含 T4 才接入统一 CI 的现有资产
  模型），用 FK 会把类型绑死。引用完整性由序列化器在录入时校验 `ci_id` 存在，数据库层只约束
  `(src, dst, type)` 唯一与禁止自环；代价是 CI 删除后可能留孤儿行，批量清理等 T4 之后补。
- **上级归属只存最近一跳**：VM `runs_on` 物理机、物理机 `located_in` 机柜，只存这两条，
  不额外存 VM `located_in` 机柜。多跳遍历是 T7 关系图谱的事，别加 `depth` / `path` 字段。
- **现有专用外键 / M2M 保留为强约束**：`Interface.vrf`、`Policy.services` 等照旧，本表只补跨类型弱关联。
- 刻意不继承 `ConfigBase`，避免被 `purge_configs` 枚举清理；契约测试 `tests/assets/test_ci_relationship.py` 锁住。

API：`/api/assets/ci-relationships/`（列表支持 `?ci_id=` 命中任一端、`?src_ci_id=`、`?dst_ci_id=`、
`?relation_type=`、`search`、分页）。写入走全局 `IsOperatorOrReadOnly`。

## API 视图（`api/views.py`）

- **堆叠组备机没有自己的配置记录**，查询统一回退到组内主设备（`resolve_config_owner`）。
- **M2M 展示字段一次取回**：策略列表要展示源/目的地址（`AddressBook`）与端口
  （`Service`），视图侧 `prefetch_related` 三个 M2M，序列化器再给格式化好的字符串，
  前端表格列不必逐条展开——否则逐行查询是 N+1。
- 列表接口的搜索/排序/分页是全局默认（`netops/settings/base.py` 的 `REST_FRAMEWORK`），
  各 ViewSet 只声明 `search_fields` / `ordering_fields`。

## Admin（`admin.py`）

全库约 500 台设备，所以：

- 外键过滤器一律 `RelatedOnly`——只列「库里实际出现过」的对象，下拉不混入从未被引用的行；
  表单侧统一 `autocomplete`（可搜索），不用裸 select；
- **大 JSON / 敏感字段不进列表**（`config_json`、`vlans`、`community`、`profiles`、
  `raw`、`pools`、`members`、`graph_data`），列表页只放扫读需要的列，详情页看全量；
- 列表过滤补齐了审计高频维度（`device_type`、`action`、`status`、`protocol`、`arp_type`）；
  `translated_*` 指向整张地址簿/服务表（下拉动辄上千项），所以改用有限取值的 `nat_type`，
  按具体地址找规则走搜索。

## Excel 导入（`device_import.py`）

- **`IMPORT_SHEETS` 是 Sheet 清单 / 顺序 / 列头 / 导入函数的唯一来源**：
  `import_excel` 按它逐个分发，模板下载接口按它生成表头——两边读同一份表，
  加删 Sheet 只改这里。列头必须与各 `_import_*` 里按下标取的列严格对齐
  （改列头 = 改导入函数，反之亦然）。
- **「配置文件」sheet 的 `config_dir` 为空时**取 `DEFAULT_CONFIG_DIR`：容器内是
  data 卷（宿主 `data/` 绑到 `/data`）下的 `configs/`；宿主机直跑时该路径通常不存在，
  表里显式填写即可。
- **用「先查后建」而不是 `update_or_create`**：`DeviceConfig` 代表「某设备在某 commit 上的
  配置快照」，重复导入同一版本不该动它。`update_or_create` 会把已解析好的 `config_json`
  清空，而 `created=False` 又不触发重新解析，解析结果就永久丢了。
- **批量导入不在请求里跑同步流水线**：每台设备解析 + 入库要 0.2–12 s，几十行就是几十秒
  串行。这里挂 `_defer_pipeline` 让信号跳过同步处理，再投递 celery 链（解析 → 存储）；
  单个上传仍走同步路径，失败能直接在响应里报错。见 [`ingest.md`](ingest.md)。
- Sheet 顺序有意义：「设备组」排在「设备」之后（行里的设备必须已存在）；组名 / 角色
  不填表，由导入推导。
