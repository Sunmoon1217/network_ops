# assets / configs 域拆分方案

> **状态：基本落地（2026-11-16 起）。切片 1–9 已完成：26 张表 + 序列化器 + parsers/savers/mapping
> + admin 26 注册 + API 26 端点（含 `resolve_config_owner`）+ llmtools 域目录改名 `network/`
> + 软资产归并拆成「configs 算 / assets 写」+ Excel 导入迁 ingest + `purge_configs` 迁 scripts
> + `overview` 概览跨域聚合迁 analysis（assets 至此真正成为叶子）。
> 只剩 `existing_asset_registry` 的归属待定（§待定项 6）。**
> 分层总图与依赖矩阵见 [`layering.md`](layering.md)。
> 进度与实测差异见文末 §「实施进度」。

## 为什么要拆

`handbook/assets.md`「资产分类边界」已经给出了判据：

> 设备内部功能（Vlan / Vrf / Interface / Route / ArpMac 等）、DCIM 位置维度、
> 关系与元数据**不算资产**。

但 ConfigBase 的 24 个子类（Vlan、Vrf、Interface、DeviceAccount、Snmp/Ntp/SyslogConfig、
Ltm* 7 个、Gtm* 5 个、AddressBook、Service、Policy、NatRule、Route）**全都住在
名为 `assets` 的 app 里**。它们是「某台设备上的一条配置行」，身份是
`(设备, 名称/编号)`，跨设备没有独立身份——按项目自己的定义，它们不是资产。

这是命名与职责的错配。拆分把它纠正过来。

### 收益

1. **assets 名副其实**：DCIM / 设备台账 / IPAM / CI 统一台账，就是「基础资产信息」。
2. **配置语义闭环**：模型 + 解析 + 写入 + 归一全在 configs 一个域内。
3. **依赖单向化**：assets 成为叶子节点（`layering.md` 的目标）。

### 代价

- **26 张表要迁**（ConfigBase 家族 25——含改继承并入的 ArpMac + `DeviceConfig`）；
- 149 处跨模块 import 要改（生产 72 + 测试 77）；
- admin 注册 26 个、REST 端点 26 个要随模型搬（此前遗漏，2026-11-16 补，见 §「admin
  与 API 层搬迁」）；
- llmtools 的 MCP 域要跟着调整（import 修复必须与模型搬迁**同提交**）；
- 有一处真正的横跨功能（软资产归并）必须拆成两半。

## 拆分边界

### 留在 assets

| 组 | 模型 |
|---|---|
| DCIM | SecurityZone、DataCenter、Room、Cabinet |
| 设备台账 | Vendor、DeviceModel、Device、DeviceConnection、DeviceGroup、DeviceGroupMember |
| IPAM | Tag、Subnet、IPAddress、SubnetUsageLog |
| CI 统一台账 | ConfigurationItem、PhysicalServer、VirtualMachine、DatabaseInstance、ApplicationService |
| CI 关系与注册 | CIObjectLink、CIRelationship、CIType、CIRelationType、CIObjectType |
| 软资产扩展表 | DomainAsset、LoadBalancerService |
| 其它 | Topology、ServerOwner |

（`ArpMac` 原列在此组，2026-11-16 拍板改判：**改继承 `ConfigBase` 并随家族迁 configs**，
见 §「ArpMac：改继承 ConfigBase」。）

### 迁到 configs

| 组 | 模型 |
|---|---|
| 配置基类 | `ConfigBase`（抽象）+ 24 个子类 + **`ArpMac`（改继承并入，第 25 个子类）** |
| 配置快照 | `DeviceConfig` |
| 解析 | `parsers/`（contract、factory、template_keys） |
| 写入 | `savers/`（base、registry、network、routing、interface、account、firewall、lb、a10_lb） |
| 归一 | `mapping.py` |
| Excel 导入（编排层） | `device_import.py` 整体迁 **ingest**（见 §「Excel 导入整体迁 ingest」） |

### 为什么 `DeviceConfig` 归 configs

`DeviceConfig` 的字段是 `git_commit_hash` + `config_json` + `device` FK，
语义是「某设备在某 commit 上的配置快照」——是配置，不是资产。

它**不继承 `ConfigBase`**（刻意：CI 台账不能被 `purge_configs` 枚举清理），
但归属上和 ConfigBase 家族是同一主题的两面，分开放会让「配置」这个概念裂成两半。

### ArpMac：改继承 ConfigBase，随家族迁 configs（2026-11-16 拍板）

**判据矛盾的原委**：本文引用的 `handbook/assets.md`「资产分类边界」把 `ArpMac` 与
`Vlan` / `Interface` 并列点名「不算资产」，拆分表却把它留在 assets——自相矛盾。
拍板结论：**ArpMac 本就该是 ConfigBase 家族成员**。

现状它是裸 `models.Model`（`network.py:1050`）：身份 `(device, ip_address, mac_address)`
唯一约束 `uni_arpmac_device_ip_mac`，与 ConfigBase 的「(设备, 名称/编号)」身份形态同构；
ARP/MAC 表是设备运行数据，与配置行同族、同生命周期（可再生、可清理）。

改造动作（两步，都独立可验证）：

1. **先在 assets 内改继承**：`class ArpMac(ConfigBase)`——删自带的 `device` FK 用基类的
   （原字段 `related_name="arp_mac_entries"` 全项目**零消费点**（已实测，仅模型定义与
   `0015` 历史迁移命中），丢弃无碍）；补 `is_active`（AddField）。
   `0015_add_arpmac` 历史迁移不动，新增一条 `AlterModelBase` + `AddField` 迁移。
2. **随家族 RENAME 迁 configs**（约束名 `uni_arpmac_*` 不含 app 前缀，随表走）。

**语义变化要知情**：并入后 `purge_configs` 会清 ARP/MAC 表（`__subclasses__()` 枚举）。
ARP/MAC 是可再生的设备运行数据，被清属可接受——但这是行为变化，写进
`handbook/ingest.md` 的 purge 说明。契约测试按 **25 子类** 锁集合。

### 为什么 parsers / savers / mapping 归 configs

- **parsers 是纯函数**：`factory.py` 只依赖 `abc` / `pathlib` / `ttp`，
  **零 Django 依赖、零模型 import**。它做的是「设备配置文本 → 配置结构」的转换，
  产出（`config_json`）就是 configs 域的核心数据形态。
  放 ingest 会让「配置语义」散在两个域。
- **savers 写的模型零例外是 ConfigBase 家族**（实测 22 个 Saver 的 `model_paths` 全部
  指向 `assets.models.*` 的 ConfigBase 子类）。它们是「写配置行」的实现，
  与配置行模型放一起才自洽。
- **mapping 是 savers 的直接依赖**：`savers/base.py:83` 的 `save()` 调
  `ingest.mapping.normalize_config`。不一起搬就是 `configs → ingest` 反向依赖。
  而它的职责是「配置键归一 + 字段规范化」（别名键 `acl`/`rules` → 规范键 `policies`），
  本就是配置语义。

### 依赖方向的冲突点：savers 的序列化器

`savers/base.py` 的 `upsert()` / `bulk_upsert()` 接受 `serializer_cls` 参数，
由各 saver 文件 import：

```python
from assets.serializers.views import VlanSerializer   # → 改成 configs.serializers.views
```

序列化器搬 configs 后，savers 在 configs 域内引用 configs 域的序列化器 ✓ 自洽。

## admin 与 API 层搬迁（此前遗漏，2026-11-16 实测盘点）

拆分不只是模型搬家——admin 与 REST 端点跟着模型走，工作量此前没进方案：

| 层 | 数量 | 说明 |
|---|---|---|
| admin | **26 个注册** | `assets/admin.py` 的 `@admin.register`（ConfigBase 家族 25 含 ArpMac + `DeviceConfig`），迁 `configs/admin.py`；`autocomplete_fields` / `list_filter` / 搜索字段跟着改 |
| REST 端点 | **26 个** | `api/urls.py` 的 `device-configs`、`device-accounts`、`vlans`、`vrfs`、`interfaces`、`snmp/ntp/syslog-configs`、`ltm-*` 7 个、`gtm-*` 5 个、`address-books`、`services`、`policies`、`nat-rules`、`routes`、`arp-mac` |
| views | 对应 ViewSet | 含 `DeviceConfigViewSet`（内嵌 `resolve_config_owner` 调用，见下节），随迁 |

「URL 前缀不变」适用到底：`netops/urls.py` 把 `configs.api.urls` 挂在与现状相同的
`/api/` 路径段下（多 app 共用前缀已验证可行），`basename` 与 `permission_classes`
照抄，前端零改动。

## resolve_config_owner 迁 configs

`ingest/config_owner.py` 的 `resolve_config_owner` 读 `DeviceGroup`（assets 模型）。
调用方拆分后分居三处：

| 调用点 | 拆分后所在域 | 依赖方向 |
|---|---|---|
| `assets/api/views.py:347`（DeviceConfigViewSet 内） | configs | configs → ingest ✗ 违禁 |
| `ingest/pipeline.py:64` | ingest | ingest → configs ✓ |
| `purge_configs` | `scripts/`（运维工具） | 工具层豁免 |

所以 `config_owner.py` **整体搬 configs**（读 `DeviceGroup` 是 configs → assets ✓）。
资产侧唯一调用点恰在 `DeviceConfigViewSet`——它本身随 `DeviceConfig` 迁 configs，
正好闭合。ingest 侧两处 import 改路径。

## Excel 导入（device_import.py）整体迁 ingest（2026-11-16 拍板）

三处反向依赖中 ①③ 的根因，拆法：

- `assets/device_import.py` 整体搬 `ingest/device_import.py`；
- **端点随迁**（`assets/api/views.py:10` 的 `from assets.device_import import IMPORT_SHEETS`
  对应的导入视图），ingest 的 api 挂原前缀，前端零改动；
- 设备台账 sheet 落库：ingest 调 assets 的服务 / ORM——ingest → assets ✓；
- 配置文件 sheet：`save_config`（Git 仓库，ingest 域内自洽）+ `submit_config_job`
  （投递采集链，ingest 域内自洽）；
- 结果：`assets → ingest` 的两处 import（`device_import.py:17` / `:340`）随搬迁消失，
  加上 `views.py:347` 的 resolve_config_owner 随 DeviceConfigViewSet 归 configs，
  **三处反向依赖全部清零**。

> **已落地（2026-11-16，切片 7）**：`apps/ingest/device_import.py` + `apps/ingest/api/imports.py`；
> `assets/api/urls.py` 的两条路由删除，`ingest/api/urls.py` 以同路径同名注册；
> 两个测试文件迁 `tests/ingest/`。`grep -rn "from ingest" apps/assets` 现在**无命中**。

## 软资产归并：唯一的横跨功能

`apps/assets/services/soft_asset_sync.py` 现在**同时读 configs 的模型、写 assets 的模型**：

```python
from assets.models import (CIType, ConfigurationItem, DomainAsset, GtmPool, ...)
```

这是整个代码库里唯一横跨两域做读写的地方，必须拆。

### 拆法：读与算在 configs，写在 assets

| 环节 | 依赖 | 归属 |
|---|---|---|
| 读配置行、分组、算字段并集、算冲突 | 只要配置行 | **configs** |
| 判断资产是否存在、字段是否变化 | 需要 assets 的现有数据 | **assets** |
| 写 CI 主表 + 扩展表 | assets 的模型 | **assets** |

**拆分点落在「算出候选值」与「落库」之间**，而不是把整个模块搬走——因为
「是否需要更新」的判断依赖 assets 侧已有数据：

```python
asset = DomainAsset.objects.filter(fqdn=group.fqdn).select_related("ci").first()
if asset is None:
    ci = ConfigurationItem.objects.create(ci_type=CIType.DOMAIN, name=group.fqdn)
    ...
changed = any(getattr(asset, name) != value for name, value in values.items())
```

### 目标形态

```python
# configs/services/soft_asset_builder.py —— 纯计算，零写操作
@dataclass
class SoftAssetDraft:
    kind: str      # "domain" | "lb_service"（字符串，不是 CIType 常量）
    key: str       # 归一键：FQDN 或 VIP#port
    name: str
    values: dict

def build_domain_drafts() -> list[SoftAssetDraft]: ...
def build_lb_drafts() -> list[SoftAssetDraft]: ...
```

```python
# assets/services/soft_asset_sync.py —— 落库
_CI_TYPE_BY_KIND = {"domain": CIType.DOMAIN, "lb_service": CIType.LOAD_BALANCER_SERVICE}

def apply_soft_assets(drafts: list[SoftAssetDraft]) -> SyncStats:
    ...
```

`kind` 用字符串而非 `CIType` 常量，**让 configs 完全不需要 import assets 的 CIType**。

### 编排：同进程调用，不走 Celery

现在的归并是**一个事务**：

```python
@transaction.atomic
def sync_soft_assets(asset_type="all"):
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_xact_lock(%s)", [_SYNC_LOCK_KEY])
    stats.merge(sync_domain_assets())
    stats.merge(sync_load_balancer_services())
```

**如果拆成「configs 算完 → Celery → assets 写」，会坏三处**：

1. **事务原子性没了**——计算与写入分属两个事务，中间有窗口期；
2. **`pg_advisory_xact_lock` 是事务级锁，跨进程无效**——得改成 session 级锁或换 Redis 锁；
3. **锁的粒度变了**——现在是「整个归并串行」，拆开后只有「写入阶段串行」，
   计算阶段可能并发。

**所以用同进程函数调用，在同一个事务里串起两步**：

```python
with transaction.atomic():
    drafts = configs.build_soft_assets()
    stats = assets.apply_soft_assets(drafts)
```

既消除写依赖（assets 不再被 configs 直接写），又保住事务原子性。

**依赖方向**：`configs → assets`（调用 assets 的 `apply_soft_assets`，跨层向下 ✓），
`assets` 完全不知道 configs 存在。**双向依赖问题彻底消除。**

### 触发点归属

现状触发点：`apps/assets/signals.py` 的 `soft_assets_stale` 信号 +
`manage.py sync_soft_assets` 命令。

拆分后：

- **信号接收器放 configs 侧**（它是「配置变了」的响应，在配置域）；
  它调 configs 的 builder + assets 的 apply —— 上层调下层 ✓
- **命令 `sync_soft_assets` 搬到 configs**（本质是「从配置重建资产」，
  且它需要调 configs 的 builder）；命令名不变，命令路径在 app 内不影响调用方式。

信号**发送方**的实测事实（2026-11-16 修正）：信号对象 `soft_assets_stale` 与发送辅助函数
`request_soft_asset_sync` 都定义在 `assets/signals.py:24-32`（**不在 ingest**）；ingest 的
4 处调用（`tasks.py:127,198`、`signals.py:85`、`reparse.py:136`）是
`from assets.signals import request_soft_asset_sync` 后调用。

拆分后的归属：**信号对象随接收器一起迁 configs**（`configs/signals.py`，语义是
「配置变了」）；ingest 的 4 处 import 改指 configs——`ingest → configs` ✓ 合法；
assets 侧不再持有这个信号，软资产同步链路对 assets 变成纯被动（只提供 `apply_soft_assets`）。

> **已落地（2026-11-16，切片 6）**：本节全部实现——builder / apply / 编排三处落点见 §实施进度
> 切片 6；`assets/signals.py` 与 assets 侧的命令已删除，`assets/services/soft_asset_sync.py`
> 只剩 `SyncStats` + `apply_soft_assets`，AST 守卫钉住「算不 import assets、写不 import configs」。

### 一个刻意保留的设计

软资产表存 **hostname 列表**而非 device_id：

```python
group.devices.append(wideip.device.hostname)
```

这是去标识化设计——删设备不会级联影响资产记录。拆分后不变 ✓。

## llmtools：MCP 域不按 app 划分

### 结论：可行，且这本来就是现状

`llmtools` 的注册机制**不按 app 组织**：

- `SPEC` 是全局单例 dict，`register_entity(spec, override=False)` 按 `node_type` 键注册；
- `register_edge` 只要求**两端先注册**，不要求同域；
- `llmtools/domains/network/` 下**现在只有一个目录**，它已经同时包含 assets 域模型
  （Device、Subnet、IPAddress、DeviceGroup、ServerOwner）和 ConfigBase 家族模型
  （Interface、Vlan、Policy、Ltm*、Gtm*、NatRule、AddressBook、Service、Route）。

**MCP 域早就是"混合"的**，只是恰好只混了 assets 内部的两块。ConfigBase 迁出后，
`llmtools/domains/network/` 继续 import 两个 app 的模型即可：

```python
from assets import models            # Device, Subnet, IPAddress, DeviceGroup...
from configs import models as cm     # Interface, Vlan, Policy, Ltm*, Gtm*...
```

### 需要处理的

| # | 事项 | 说明 |
|---|---|---|
| 1 | 目录改名 | **已落地**：`domains/assets/` → `domains/network/`（覆盖「网络设备及其配置」话题，两个 app 的模型都归它）。改动面只有目录重命名 + `llmtools/__init__.py` / `llmtools/tools.py` 两处 import |
| 2 | `specs/ipam.py` 跨域 | 该文件同时含 Device/DeviceGroup（assets）与 Interface/Vlan/Vrf/Route（configs）。**保持混合**，逐个改 model 来源即可 |
| 3 | `specs/slb.py` 13 个实体 | 全是 ConfigBase 家族 → 改 `models.` 为 `cm.` |
| 4 | `specs/firewall.py` 4 个实体 | 同上 |
| 5 | `edges.py` 36 条边 | `_by_device(models.Interface)` → `_by_device(cm.Interface)`。**边跨域不是问题**（注册表是全局的），只要两端都已注册 |
| 6 | `tools.py` 的 `locate` | 跨域工具，同时遍历两个域的实体。**不属于任何一边**，留在该域即可 |

### MCP 侧的简化模型（配合 analysis 物化表）

给 MCP 用的简化模型走 `netops/schema.py` 的 `ExtraModel` 基类（项目已有此设施：
允许额外字段，适合外部数据投影）。

复杂查询建议**重定向到 analysis 的物化表**，而不是让 MCP 直接查 configs 的
25 张配置行表。

## 序列化器：先合并新旧，再搬

现状两套并存：

| 文件 | 行数 | 状态 |
|---|---|---|
| `apps/assets/api/serializers.py` | 822 | 旧，41 个同名类 |
| `apps/assets/serializers/views.py` | 424 | 新（改造版） |

`serializers/__init__.py` 的注释写着「`api/serializers.py` 目前仍保留，
待引用切换完成后再删除」。旧文件目前只被一处引用：

```python
# apps/analysis/api/firewall_groups.py:25
from assets.api.serializers import _format_address_entry, _format_service_entry
```

这两个私有函数处理的是 `AddressBook` / `Service`（都是 ConfigBase 家族）。

### 顺序

1. **先合并**：把两个私有函数搬进 `serializers/views.py`，删掉 `api/serializers.py`，
   改 `analysis/api/firewall_groups.py` 的 import。
   `tests/assets/test_serializer_migration.py` 是新旧对比的契约测试，
   合并后需要重写为「旧模块已删除」的对账断言。
2. **再搬**：ConfigBase 家族那 20 多个序列化器跟模型走 configs，其余留 assets。

**先合并再搬的理由**：旧文件里有 41 个同名类重复定义，拆的时候要拆两套重复的，
工作量翻倍且容易漏。

### analysis 引用 configs 时要不要带 device 模型

`firewall_groups.py` 只需要那两个**纯函数**（读 entry 的属性，不 import 模型），
所以**只改 import 一行，不需要带 device 模型**。

但如果 analysis 的接口要返回**带设备信息的策略列表**，那确实要同时拿两边的模型：

```python
from assets.models import Device
from configs.models import Policy, NatRule
```

`analysis → assets` + `analysis → configs`，两条都合法 ✓——这正是 analysis
「面向前端的联合查询」的定位。

## 迁移手法

### 范本：analysis.0002_accessflow

项目里已有成熟的同款手法（`apps/analysis/migrations/0002_accessflow.py` 顶部注释）：

> `operator.0005` 只从迁移状态删除模型（database_operations 为空），表原样保留；
> 本迁移在 state 层建出 `analysis.AccessFlow`（字段/约束/索引照抄 0004 之后的终态），
> DB 层只执行一次 `RENAME`——表名对齐新 app，数据与 GIN 索引随表走
> （索引名 `gin_accessflow_*`、约束名 `uni_accessflow_action_key` 不含 app 名，不需要改）。

即 **`SeparateDatabaseAndState` + state 层 CreateModel + DB 层 RenameModel**，
不重建表、不丢数据。fresh 库（从零 migrate）与存量库升级走同一条路径。

### label 是迁移历史的主键

`apps/ingest/apps.py` 的注释：

> label 是**迁移历史的主键**（django_migrations.app 全是 'operator'），改它会让已有库的
> 迁移记录对不上——目录与 name 可以改，label 永远不动。

**所以拆出的 `configs` app 用新 label**（如 `configs`），表名从 `assets_vlan` 变成
`configs_vlan`，**这正是需要 RENAME 迁移的原因**。

不能沿用 `assets` label —— 两个 app 同 label 会让 Django 报 `ImproperlyConfigured`。

### configs 初始迁移的依赖声明（2026-11-16 补）

`ConfigBase.device → assets.Device` 拆分后是**跨 app 外键**（configs → assets，矩阵允许，
方向合法）。configs 的 `0001` 初始迁移在 state 层 CreateModel 时必须声明
`dependencies = [("assets", "<当时 assets 最新迁移名>")]`，否则 fresh 库从零
`migrate` 时建表顺序错乱（外键目标表还没建）。存量库不受影响（表已存在），但
fresh 库路径必须与存量库同路径跑通——这正是范本 `analysis.0002` 强调的双路径验证。

### 索引与约束名

`analysis.0002` 的注释提到：索引名 `gin_accessflow_*`、约束名
`uni_accessflow_action_key` **不含 app 名**，所以不需要改。

**本次迁移要逐个核对**：ConfigBase 家族 25 张表（含 ArpMac）的索引 / 约束名里是否含
`assets_` 前缀。含的要在 `SeparateDatabaseAndState` 里显式改名（`AlterModelTable` 之外的
`RenameIndex` / `AlterConstraint`）。

### `ConfigBase.__subclasses__()` 的运行时枚举

`purge_configs` 靠 `ConfigBase.__subclasses__()` 枚举 24 个子类
（`purge_configs.py:117`；ArpMac 并入后为 **25**）。

- 迁到**同一 Django 项目内的另一个 app** → 枚举照常工作（Django 的 app registry
  会加载所有 models 模块）；
- 但它**依赖「Django 已完全启动」这个前提**——若在 `AppConfig.ready()` 里调用，
  会漏掉尚未 import 的类。

**要加一条契约测试**锁住「ConfigBase 子类集合与预期一致」，
现有 `tests/assets/test_soft_assets.py` 已有类似断言（CI 台账不继承 ConfigBase），
迁移后要跟着改路径。

### purge_configs 的归属

`purge_configs` 同时清四样东西：

| 清理组 | 内容 | 归属 |
|---|---|---|
| 配置解析产物 | `ConfigBase.__subclasses__()` 全 24 子类（ArpMac 并入后 25） | configs |
| 配置记录 | `DeviceConfig` | configs |
| 派生缓存 | `InternetAnalysis`、`AccessFlow` | analysis |
| 工作流记录（可选） | `core.Stage` / `core.Task` | core |
| Git 仓库（可选） | `CONFIG_REPO_PATH` 整个目录 | ingest |

代码里已经明确写了立场：

> InternetAnalysis / AccessFlow 住在 analysis app，但**清理仍归本命令**：purge_configs
> 的语义是「配置解析产物一把清」，它是跨域的运维工具（工具层允许跨域 import），别把这段搬走。

**建议：迁出 app，改为独立运维脚本 `scripts/purge_configs.py`。**

理由：

1. 它没有业务链路调用点（全项目仅 `manage.py purge_configs` 一个命令行入口），
   和 `scripts/reset-db.sh` 等运维脚本同性质。
2. 迁出后它不再是 ingest 域的一部分，`layering.md` 里的「跨域运维工具豁免」
   自然取消——不参与依赖矩阵，也就不再纠结「留 ingest 还是搬 configs」。
3. 迁 scripts 后，`from assets.models import ConfigBase` →
   `from configs.models import ConfigBase` 是唯一需要的 import 改动。

实现要点：脚本用 `django.setup()` 引导（它需要访问 ORM 清 25 张配置行表），
入口从 `manage.py purge_configs` 改为 `python scripts/purge_configs.py`，
同步更新 `AGENTS.md` 与 `handbook/ingest.md` 里的命令示例。

## 测试影响

| 文件 | 影响 |
|---|---|
| `tests/assets/` 17 个文件 | 其中 4 个测软资产归并（`test_soft_asset_sync.py`、`test_soft_assets.py`、`test_soft_asset_signal.py`、`test_soft_asset_api.py`），拆分后要拆成两边 |
| `tests/ingest/` 27 个文件 | Saver 相关（`test_saver_*.py` 共 8 个）的 import 路径要改 |
| `tests/mcp/` 6 个文件 | llmtools 域调整后要重跑 |
| `tests/assets/test_serializer_migration.py` | 序列化器合并后要重写为「旧模块已删除」的对账断言 |
| `tests/assets/test_device_group.py` | `resolve_config_owner` 的 import 路径 |
| `tests/configs/test_configbase_registry.py`（新增） | 锁死 `ConfigBase` **25 子类集合（含 ArpMac）** + `DeviceConfig` 不继承 `ConfigBase`（防 `purge_configs` 误枚举）+ purge_configs 两组清理各自正确 |
| `tests/assets/` 里 ArpMac 相关用例（admin / API / serializer） | 改继承 ConfigBase 后随模型迁 `tests/configs/`；`is_active` 新字段的默认值行为补测 |

## 待定项

| # | 待定 | 影响 |
|---|---|---|
| 1 | `Task.device` 保留 FK 还是改 JSON | **已落地**：方案 C（多态引用），见 [`../tasks.md`](../tasks.md) §作用目标 |
| 2 | `egest` 是否独立成域 | 若复用 ingest 的采集通道，可能更适合做成 ingest 子模块 |
| 3 | `llmtools/domains/assets/` 改名成什么 | **已定 `network/`**（2026-11-16，切片 5 落地）；`infra/` 覆盖过宽（还会想塞采集与告警），不用 |
| 4 | `analysis/api/parsers.py`（映射清单接口）的归属 | 涉及 parsers 与 savers 两边，实现可留 ingest，路径不变 |
| 5 | `assets/api/views.py` 的 `overview`（`/api/assets/overview/`）跨域聚合 | **已落地（切片 9，2026-11-16）**：整个端点迁 `analysis/api/overview.py`——它是 assets + configs 的只读聚合，只能落在两者之上；**URL 与 name 原样保留**，前端零改动。configs 单侧统计不做拆接口（`analysis` 已在矩阵里允许同时读两个域，再拆成两个接口只会让前端多一次请求）。 |
| 6 | `assets/services/existing_asset_registry.py`（既有资产判重）是否随 Excel 导入迁 ingest | 目前只被 ingest 的导入链路调用，但「资产唯一性口径」必须与 assets 的模型约束同处一地（否则两边各写一份判重规则必然漂移）。倾向**留在 assets**，待导入链路再变动时定 |

## 建议的最小验证切片

**先不要一次全做。** 最长的链路是「迁模型 + RENAME 表 + 测试全绿」，
它最容易出意外（label、索引名、迁移依赖链）。

建议的验证切片：

1. 新建 `configs` app（label = `configs`），只迁 `ConfigBase` + **1 个子类**（如 `Vlan`）；
2. 写 `SeparateDatabaseAndState` + `RenameModel` 迁移；
3. 跑 `migrate`（存量库）+ 全量测试；
4. 确认表名、索引、约束、`__subclasses__()` 枚举都正确。

**通过后再批量迁其余 24 张子类表 + `DeviceConfig`。** 一次迁 26 张表，出了问题不好定位。

## 实施进度

### 切片 1 — 已落地（2026-11-16）

| 项 | 落点 |
|---|---|
| 新 app | `apps/configs/`（`label = "configs"`，`INSTALLED_APPS` 排在 `assets` 之后） |
| 基类 | `configs/models/base.py` 的 `ConfigBase`；`device` 用**字符串** `"assets.Device"`，不 import assets 的模型 |
| 首个模型 | `configs/models/network.py` 的 `Vlan` |
| assets 侧 | `assets/models/network.py` 删掉基类与 `Vlan` 的定义，改为 `from configs.models.base import ConfigBase`；`assets/models/__init__.py` 不再导出二者 |
| 迁移 | `assets/0036_remove_vlan_state`（`SeparateDatabaseAndState` 只删 state）→ `configs/0001_initial`（建 state + `RunSQL` 把 `assets_vlan` 改名 `configs_vlan`） |
| 引用点 | 生产 11 处（admin / api / serializers / saver / purge_configs / llmtools）+ 测试 13 处改指 `configs.models` |
| 工具链 | `pyproject.toml` 的 ruff `known-first-party` 补 `configs`（顺带补上同样漏掉的 `cloud`） |

**实测结论**（克隆开发库 + 空库，两路径都跑了）：

1. **数据完整**：迁移前 `assets_vlan` 2 行 → 迁移后 `configs_vlan` 2 行，ORM 读到的 device hostname 正确。
2. **约束与索引随表走，不需要改名**：`uni_vlan_device_vid` 不含 app 名；`devices_vlan_pkey` /
   `devices_vlan_vid_check` 是更早表名（`devices_vlan`）时代的历史命名，`assets_vlan_device_id_*`
   是 FK 自动索引——RENAME 不改它们，**Django 也不按这些名字做状态比较**，所以既无漂移也无功能
   影响。提案预留的「逐个核对并在 `SeparateDatabaseAndState` 里改索引/约束名」这一步，实测结论是
   **核对后确认无需改**（新迁的表若显式命名了带 `assets_` 前缀的索引，仍要单独处理）。
3. **fresh 库必须显式依赖 assets**：`configs/0001` 的 `dependencies` 指向 `assets/0036`，
   否则从零 migrate 时外键目标表还没建。两条路径（存量升级 / fresh）都验证过。
4. **反向可用**：`migrate configs zero` → `migrate assets 0035`，表名改回 `assets_vlan`、2 行数据仍在。
5. **运行时枚举不受影响**：`ConfigBase.__subclasses__()` 仍是 24 个，`Vlan` 的
   `app_label` 变成 `configs`，`purge_configs` 的枚举照常工作。
6. **手写 state 与模型严格一致**：`makemigrations --check` 只剩 `cloud` 那 8 条既存漂移。

**与提案的差异**：

1. **切片期存在临时反向依赖**：其余 23 个 `ConfigBase` 子类还在 `assets/models/network.py`，
   只能 `from configs.models.base import ConfigBase` —— 即 **assets → configs**。提案按「一次迁完」
   写，没提这个过渡态。它会在最后一批子类迁走时消失，切片阶段**不给 assets 加分层守卫**
   （否则等于给过渡态写一条假约束）。
2. **`assets/models/__init__.py` 不做 re-export**。re-export 能让 47 处 import 零改动，但会把
   「模型已经不在 assets」这件事藏起来，批量迁移时也分不清哪些是真引用。全部改指 `configs.models`。
3. **`configs` 只是新 app 的起点，`apps.py` 暂时没有 `ready()`**：本域目前没有要在启动时注册的
   东西（软资产信号、词汇注册都随后续步骤进来）。

### 切片 2 — 已落地（2026-11-16）

| 项 | 落点 |
|---|---|
| ArpMac 改继承 | `assets/0037_arpmac_configbase`：删自带 device FK 的 related_name、补 `is_active`；改名同义的 created_at/updated_at 不重复添加 |
| 模型 | 23 个子类 + ArpMac 进 `configs/models/network.py`（与 Vlan 同模块，保留类名直接引用）；`DeviceConfig` 独占 `configs/models/device_config.py`，device 改字符串引用 `assets.Device` |
| 迁移 | `assets/0038_remove_config_state`（**SeparateDatabaseAndState，只删 state，DB 不动**）→ `configs/0002_bulk_models`（state 建 25 模型 + 31 条 `ALTER TABLE … RENAME`，含 Policy/NatRule 的 6 张 M2M 中间表） |
| 字段对齐 | CreateModel 的字段/约束从 `assets/0037` 的 ProjectState 逐字段生成；跨模型 FK 的 `to=` 改为 `configs.*`（Vrf / GtmServer / AddressBook / Service），保留 `assets.device` |
| 引用点 | 生产 + 测试 67 个文件的 import / 属性访问 / saver 的 `model_paths` 字符串统一改指 configs；`assets/models/__init__.py` 不再 re-export 这 25 个名字；`ingest/signals.py` 的 lazy sender 改 `configs.DeviceConfig` |
| 契约 | 新增 `tests/configs/test_configbase_registry.py`：锁死 25 子类集合、全部 app_label=configs、DeviceConfig 不被枚举 |

**实测结论**：
1. 克隆存量库造数（Vrf + Policy）→ `migrate` → `configs_vrf` / `configs_policy` 数据完好、ORM 可读；
   `migrate configs zero` + `migrate assets 0037` 反向后表名与数据都回到 `assets_*`。
2. fresh 库全量 `migrate` 与 pytest 建测试库都通过：全量 **846 passed, 66 subtests**
   （842 基线 + 4 条新契约）。
3. `makemigrations --check` 只剩 `cloud` 那 8 条既存漂移。
4. **两个必须踩的坑**：`assets/0038` 的 DeleteModel 若不放进 `SeparateDatabaseAndState`，
   fresh 库会直接 DROP 表；`configs/0002` 的 CreateModel 若不做 state-only，会与历史迁移
   已建的同名表/constraint 冲突。两边都靠 `database_operations=[]` 才对。

**仍然是过渡态**（切片 2 结束时）：`assets/admin.py`、`assets/api/views.py`、`assets/serializers/views.py`
等仍 import configs 的模型（合法的下层依赖），admin / API 本身还没搬；`ArpMac` 并入后
`purge_configs` 会清 ARP/MAC 表（已写进 `handbook/ingest.md`）。其中解析 / 写入 / 序列化器
部分已在切片 3 迁走。

### 切片 3 — 已落地（2026-11-16）

| 项 | 落点 |
|---|---|
| 序列化器合并 | 两个私有展示函数并入 `assets/serializers/views.py`，删除 `assets/api/serializers.py`；`analysis/api/firewall_groups.py` 改 import；契约测试改成「旧模块已删除」对账 |
| 配置类序列化器 | 26 个（25 子类 + DeviceConfig）→ `configs/serializers/views.py`，继承 `assets.serializers.base`；`PolicySerializer` 保留三个 `*_display` 展示字段（API 口径不变） |
| 解析 / 写入 / 归一 | `ingest/parsers/`、`ingest/savers/`、`ingest/mapping.py` 整体迁 `configs/`；`access_flow_trigger.py` 随 PolicySaver 迁 configs（按任务名 send_task，仍不 import analysis） |
| 注册与模板路径 | Saver 注册点从 `ingest.apps.ready()` 移到 `configs.apps.ready()`；解析器模板按 `configs.parsers.__file__` 定位，模板管理接口同步 |
| 引用点 | 34 个文件的模块路径改指 configs；savers 的序列化器 import 改 `configs.serializers.views`；llmtools 规格改为 `s`（assets）+ `cs`（configs）双引用 |

**实测结论**：全量 **846 passed, 66 subtests passed**；`manage.py check` 无问题；configs 侧对
`ingest` / `analysis` 的 import 为 0（`access_flow_trigger` 只按任务名字符串投递）。
failures 修了两处：`PolicySerializer` 的展示字段随合并丢了（已补回），解析器测试的模板目录
断言仍指向 `ingest`（已改按 `configs.parsers` 包定位）。

### 切片 4 — 已落地（2026-11-16）

| 项 | 落点 |
|---|---|
| admin | 26 个 `@admin.register`（含 `DeviceConfigAdmin`）从 `assets/admin.py` 迁 `configs/admin.py`；`DEVICE_FILTER` 同口径另立一份，列表/搜索/筛选逐字照抄 |
| API ViewSet | 26 个 ViewSet 迁 `configs/api/views.py`；类体内的局部模型/序列化器 import 上提到模块头 |
| 路由 | 新建 `configs/api/urls.py`（自己的 `SimpleRouter`，`path("assets/", …)`），`netops/urls.py` 与 assets 并列挂载；`basename` 原样，反解结果不变（`/api/assets/vlans/` 等） |
| `resolve_config_owner` | `ingest/config_owner.py` 迁 `configs/config_owner.py`；ingest 的 pipeline / purge_configs、analysis 注释、测试同步改路径 |
| 实测 | `configs` admin 注册数 = 26；`reverse("vlan-list")` 等仍是 `/api/assets/...`；全量 **846 passed, 66 subtests** |

**踩点**：`assets/api/urls.py` 与 `configs/api/urls.py` 两个 include 都写 `path("assets/", …)`，
靠 Django「按顺序尝试、命中即止」共存——不要为了"干净"去合并成单 router，那会把 assets 与
configs 重新绑在一起。

### 切片 5 — 已落地（2026-11-16）

| 项 | 落点 |
|---|---|
| 目录 | `llmtools/domains/assets/` → `llmtools/domains/network/`（10 个文件整体 `git mv`） |
| 组合根 | `llmtools/__init__.py` / `llmtools/tools.py`：`from llmtools.domains import network`、`network.register()`、`*network.TOOLS` |
| 域内引用 | `domains/network/tools.py` 的 `specs._helpers` 绝对导入改指 `llmtools.domains.network.specs` |
| 文档 | `README.md`、`handbook/llmtools.md`、`apps/assets/models/ci.py` docstring（`NodeType` 交叉引用）、本稿 §llmtools |

**为什么不按 app 拆成两个域**：`specs/ipam.py` 一个文件里就有 Device/DeviceGroup（assets）与
Interface/Vlan/Vrf/Route（configs），`edges.py` 36 条边也横跨两边。注册表本身是全局的
（`node_type` 键 + 「两端先注册」），硬拆只会把同一话题的实体分到两个包再互相 import。
按**话题**划分是对的，按 app 划分不是。

**踩点**：批量替换脚本先 `git mv` 再 rglob 遍历，结果 SKIP 集合里的 `".worktrees"` 命中了
项目根自身的路径段（worktree 就住在 `.worktrees/` 下），整棵树被跳过、只有两个显式文件生效。
批量改名用 `git ls-files` 枚举跟踪文件，别用 `rglob` + 目录黑名单。

### 切片 6 — 已落地（2026-11-16）

| 项 | 落点 |
|---|---|
| 算（只读） | `configs/services/soft_asset_builder.py`：`SoftAssetDraft`（kind/key/values）+ `BuildResult`（drafts/skipped）+ `build_domain_drafts()` / `build_lb_drafts()` |
| 写（只写 assets） | `assets/services/soft_asset_sync.py`：`SyncStats` + `apply_soft_assets(drafts)`；`kind` → (CIType, 模型, 归一键字段) 一张表查完，两个 `_sync_*_group` 合成一个通用 `_apply_draft` |
| 编排 | `configs/services/soft_asset_sync.py`：`sync_domain_assets` / `sync_load_balancer_services` / `sync_soft_assets`，单事务 + `pg_advisory_xact_lock`（原样保留） |
| 信号 | `assets/signals.py` → `configs/signals.py`（信号对象 + `request_soft_asset_sync` + 接收器）；`configs/apps.py.ready()` 里 import |
| 命令 | `manage.py sync_soft_assets` 从 assets 迁 configs，命令名与参数不变 |
| 引用 | ingest 4 处惰性 import、测试 2 个文件改指 configs；`assets/apps.py` 不再 import `assets.signals` |
| 守卫 | `tests/configs/test_soft_asset_boundary.py`：AST 钉住「builder 不 import assets、writer 不 import configs」 |

**为什么类型用 `Protocol` 而不是共用 dataclass**：`apply_soft_assets` 的入参若标注
`configs...SoftAssetDraft`，assets 就得 import configs（矩阵禁止）。改用只读属性的
`Protocol`（结构化类型），冻结 dataclass 天然满足，一个 import 都不用加。

**实测**：`tests/configs` 25 passed；全量 **851 passed, 66 subtests passed**（846 基线 + 5 条
新增：计算段无写操作 / 落库段按 kind 建 CI / lb draft 不带 CIType + 两条 AST 边界守卫）；
`manage.py check` 干净，`manage.py help sync_soft_assets` 仍能发现命令（命令发现与 app 标签无关）。

### 切片 7 — 已落地（2026-11-16）

| 项 | 落点 |
|---|---|
| 导入器 | `apps/assets/device_import.py` → `apps/ingest/device_import.py`（441 行整体 `git mv`，加了一段「为什么在 ingest」的模块注释） |
| 接口 | 两个视图（上传分发 / 模板下载）从 `assets/api/views.py` 提到 `ingest/api/imports.py`；`assets/api/urls.py` 删两条路由，`ingest/api/urls.py` 以**同路径同名**注册（`assets/import-devices/`、`assets/import-template/`） |
| 清理 | `assets/api/views.py` 去掉 `IMPORT_SHEETS` / `HttpResponse` / `Worksheet` / `cast` / `logger` 等只被搬走代码用到的导入 |
| 测试 | `test_import_configs_async.py` / `test_import_device_group.py` → `tests/ingest/`，模块路径改 `ingest.device_import`；URL 断言不用改（前缀与 name 都没动） |
| 文档 | `handbook/assets.md` 该节改成指针，正文搬 `handbook/ingest.md`；`handbook/api.md`、`AGENTS.md` 的架构表与目录树同步 |

**结果**：`grep -rn "from ingest" apps/assets` **无命中**——`assets → ingest` 清零，
矩阵里 assets 行的四个 ✗ 只剩 `assets → configs`（就是待定项 5 的 `overview`）。

### 切片 8 — 已落地（2026-11-16）

| 项 | 落点 |
|---|---|
| 脚本 | `scripts/purge_configs.py`（原 `apps/ingest/management/commands/purge_configs.py` 删除）：同样四个开关、同样默认 dry-run，`main(argv, out)` 可注入输出，退出码 0 / 2 |
| 结构 | 逻辑从 `Command` 类改成 `_Purge` 类 + `main()`；模型导入全部下移到用到的函数里（脚本 import 时不碰 Django 应用加载，`main()` 里才 `django.setup()`） |
| 测试 | `tests/ingest/test_purge_configs_command.py` → `tests/scripts/test_purge_configs.py`（12 条语义不变；错误断言从 `CommandError` 改成「退出码 2 + 输出含提示」，缺 `--device/--all` 由 argparse 抛 `SystemExit(2)`） |
| 工具链 | `pyproject.toml` 的 ruff `known-first-party` 补 `scripts`（否则 `from scripts import …` 被当第三方包排到最前） |
| 文档 | `handbook/ingest.md` 的命令表与「为什么存在」、`deploy.md` 的容器调用、`AGENTS.md` 三条、`layering.md` 的例外表 |

**结果**：`ingest` 不再 import `analysis`——矩阵里 ingest 行的 ✗ 成立；`layering.md`
「例外与豁免」表里 purge_configs 那行从「待迁出」变成「已迁出」，只剩 `core/queue_*` 两条。
**调用方式变了**：`manage.py purge_configs` → `python scripts/purge_configs.py`（容器里
`docker compose exec app python scripts/purge_configs.py …`）。

### 切片 9 — 已落地（2026-11-16）

`overview` 是**读取侧**唯一同时消费 assets 与 configs 的查询（机柜 / 设备 / 网段 + 接口 /
VLAN / 路由 / 策略 / NAT / SLB / GTM / ARP 的分布）。切片 4 把 26 个 ViewSet 迁走之后，
它成了 assets 里最后一个 `configs` import——叶子节点往上够。

| 项 | 落点 |
|---|---|
| 视图 | `apps/assets/api/views.py` 的 `overview` → **新模块** `apps/analysis/api/overview.py`（函数改名 `assets_overview`，逻辑逐行照抄） |
| 路由 | `assets/api/urls.py` 删一行；`analysis/api/urls.py` 以 `path("assets/overview/", …)` + `name="assets-overview"` 注册——**路径与 name 一字未改**，`frontend/src/netops/views/Home.vue` 与 `reverse()` 零改动 |
| 清理 | `assets/api/views.py` 去掉 `configs.models` 15 个模型导入、`logging` / `logger` / `api_view` / `Response`（只剩 DCIM ViewSet，assets 全目录对上层域 import 归零） |
| 守卫 | `tests/core/test_layering.py` 新增 `test_assets_imports_no_upper_domain`：AST 扫 `apps/assets`，出现 `configs/ingest/analysis/egest/docs/cloud` 即失败 |
| 契约 | 新增 `tests/analysis/test_overview_api.py`：普通用户 200 + **41 个顶层字段的冻结清单**（前端整包消费，少一个就是一块空白卡片），外加「两侧计数同时生效」用例 |
| 文档 | `handbook/api.md` 该行从 assets 表移入 analysis 表并注明 URL 不变；`layering.md` 的 assets 行从「目标态」改为「叶子节点（有守卫）」 |

**为什么落 analysis 而不是 configs**：`analysis → ingest → configs → assets`，analysis 本来
就装着 dashboard / lb-chain / 设备组合并这些跨域只读聚合；搬到 configs 还得让 configs
反向读 assets 的机柜与设备，等于把刚解开的一条反向依赖换成另一条。

**为什么不做「拆成两个接口」**：那两条出路都会动前端契约（Home 页要并发两次请求再合并），
而 analysis 在矩阵里本来就允许同时读两个域——收益只有「少一个跨域点」，代价是前端与
缓存口径都要重排，不划算。

**实测**：`tests/core/test_permissions.py` + `tests/core/test_layering.py` 16 passed；
`tests/analysis/test_overview_api.py` 2 passed（字段清单与实测响应完全一致）；
`reverse("assets-overview")` = `/api/assets/overview/`，`resolve()` 落在
`analysis.api.overview`；全量 **854 passed, 66 subtests passed**（851 基线 + 3 条新增）；
`manage.py check` 干净；OpenAPI schema 的 warnings / errors 计数（11 / 273）与 develop 基线
**完全一致**——`api_view` 的 serializer 推断告警是这类函数视图的既有现象，不是本次引入。

### 下一步

1. （待定）`existing_asset_registry` 的归属，见 §待定项 6——目前倾向留在 assets，
   不阻塞拆分收尾。

