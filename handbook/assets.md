# assets：资产模型、API 与导入

## 模型

全部模型集中在单文件 `apps/assets/models.py`（没有 models 子目录），这样「一张表在哪」
不需要再翻包。配置解析产物都继承 `ConfigBase`，`purge_configs` 用
`ConfigBase.__subclasses__()` 运行时枚举它们（当前 24 个子类，其中 22 个已配 Saver）。

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
