# analysis：路径追踪、策略展开、访问流

`apps/analysis/` 是**只读消费侧**：读 ingest 解析入库的资产，算出路径、访问流与缓存，
不反向依赖 assets / ingest。

## 一、路径追踪（`path_tracer.py`）

模拟报文从源到目的逐跳转发：

1. 整理源目地址端口，找源/目的设备（先按 Subnet 的 gateway 找网关设备，再退到接口地址）；
2. 查源目 VRF，相同则直接返回一跳；无端口且源在 `internet` 时要报错（必须给目的端口）；
3. 循环（`MAX_HOPS = 50`，同时做 VRF 环路检测）：LB 检查 VS → 防火墙策略匹配 →
   NAT 转换 → 查最精确路由 → 直连则结束 → 否则切到下一跳设备与接收接口的 VRF。

`original_src` 单独留一份：策略匹配始终用**原始源地址**，NAT 改过 `current_src` 之后
不能拿它去匹配策略。

### VRF 判定优先级（`_find_vrf_for_ip`）

Subnet 表有 `0.0.0.0/0` 兜底，所以必定命中，不需要回退到 Interface 表：

1. `subnet.vrf` 非空 → 直接用它；
2. 子网带「专线」tag → 用合作方名称当 VRF（没有合作方 tag 时叫「未知合作方」）；
3. `prefixlen == 0` → `internet`；
4. `datacenter` + `security_zone` 都有 → 走路由表跟踪（下一节）；
5. 有 gateway → 网关设备的 VRF（优先 `default`，否则取 pk 最小的那条）；
6. 其他 → `default`。

### 路由链跟踪（`_find_vrf_from_routing_table`）

取所有「包含该网段、且前缀长度相同」的路由，按设备分组各留最长前缀，然后从任意设备
沿下一跳（IP 或出接口）走，**终点 = 没有该网段特定路由的设备**（只剩默认路由那台）。
例：

```
intyw-cs:default       /23 → intyw-fw
intyw-fw:default       /23 → intyw-cs:VRF-INTYW
intyw-cs:VRF-INTYW     /23 → intyw-slb
intyw-slb:default      default → intyw-cs:VRF-INTYW   (无 /23 特定路由，是终点)
```

终点是 `intyw-slb:default`，返回 `default`。

### 已知坑（改之前先看）

- **路由版本必须显式比对**：`ipaddress` 的 `subnet_of` 在 IPv4/IPv6 混用时会抛
  `TypeError: not of the same version`。早期靠 `# type: ignore` 掩盖，结果是
  「IPv6 静态路由 + IPv4 目的地址」让整个追踪接口 500。
- **`vrf_name` 必须是字符串**，不能赋 `Vrf` 对象：它后面会被拿去
  `Vrf.objects.filter(name=...)`、放进 `visited_vrfs` 做环路判断、塞进 `HopResult.vrf`
  直接返回；赋对象会查询匹配不上、环路判断永不成立、接口序列化 500。
- **缓存是进程级的函数属性**：`_subnet_cache` / `_route_cache` 挂在函数对象上，
  `trace_path` 每次入口清路由缓存、子网缓存保留（测试用 `_clear_*_cache` 手动清）。
- **NAT 端口解析要跳过占位行**：同名服务允许多行端口定义，`any` 占位行的 `port` 是空串，
  `first()` 恰好命中占位就会把存在的端口答成 `None`——所以排除空 port 后按 pk 取首个。
- **LB 后端查询**：`queryset` 与最终实例分开命名，避免类型检查器把后面那个 Optional
  实例当成 QuerySet。

## 二、策略展开（`policy_expand.py`）

一条策略的三个维度是笛卡尔积（7×7×7 ≈ 343 行/策略），但**同一条访问流可能出现在多台
设备、多条策略上**——所以唯一键是归一化后的**十元组**（源 ip/prefix/range_end + 目的
三段 + protocol/port/port2 + **action**），`(device_id, policy_pk)` 作为上下文聚进同一行
的 `contexts`。同五元组被 allow 与 deny 命中时是**两行**（键里含 action，天然分开）。

`contexts` 的键语义（别改坏）：

- 键带的是**策略主键**而不是内容——同一台设备上内容重复的两条策略各占一个键、互不覆盖，
  这正是「设备内重复策略 / 多开」审计的数据来源；
- 重跑/重放时同键覆盖（策略改内容会更新），不同键各自保留，幂等；
- 摘除按设备前缀（`f"{device_id}:"`）整体剥离，带冒号是为了不让 `"1:"` 误伤 `"11:x"`。

写库方式是**先查后合并 + bulk_create/bulk_update**（不是 `update_or_create`——逐行往返
在万级策略下不可用）。这条路径**只给单写者用**（见下一节），所以不需要 ON CONFLICT / 行锁。

几个容易忽略的归一规则：

- 地址维度的「任意」哨兵是 `("0.0.0.0", 0, "")`，与显式 `0.0.0.0/0` 同键——语义相同；
- range 没有前缀语义，`prefix` 固定 0，区分度靠 `range_end` 非空；
- 空地址组（PolicySaver 的占位记录、或还没填内容）按 **any** 处理——宁可保守标成
  「任意」也不静默丢掉整条策略；
- `action` 在键里再兜一次底（`allow/deny` 小写）：模型 choices 管不到没走序列化器的手工数据；
- `port` 空即空串（非 NULL，参与唯一约束），纯数字去前导零（`080 == 80`），
  `port2 == port` 时归一成空串（`80-80` 就是单端口）。

### 同步语义（`sync_device`）

`sync_device` = 先合并写入、再摘残留上下文，整段一个事务：

- 重放同一批数据时两步都是空操作（**真幂等**，行 pk 不抖动、`created` 不虚高）；
- 策略改了则是新键并入、旧键残留被摘掉；
- 中途失败不会留下「合了一半」的残局；
- 判据必须是**行键（十元组）**而不是 context 键：同一条策略的 context 会出现在它笛卡尔积
  的每一行上，策略换了地址后旧行与本批是同一个 `(设备, 策略)` 键、行却不同，按 context
  键保留就漏摘了。

## 三、访问流链路

```
celery worker（analysis.rebuild_access_flows，队列 access_flow，多进程并行）
    展开一台设备的策略 ──XADD──> access_flow_stream
                                      │
access_flow_consumer（独立进程，**唯一**写 AccessFlow 的人）
    XREADGROUP → 摘旧上下文 + 合并入库（一个事务）→ 入库成功才 XACK
```

### 为什么单写者

并行**展开**没问题，冲突都在**写库**：同一条访问流可能被多台设备的策略命中，多个进程
同时「先查后合并」会互相覆盖 `contexts`。只有一个进程写，就能沿用先查后合并 + bulk，
而不需要 ON CONFLICT / 行锁；代价是入库吞吐上限取决于这一个进程（单条毫秒级，够用）。

**消费者只能跑一个实例**：消费者组会把消息摊给多个成员，多起一个就变成多写者，
「先查后合并」的前提就没了。compose 里的 `access-flow-consumer` 就是这一个。

### 恢复语义

`XACK` 在事务提交**之后**：消费者崩溃时消息留在 PEL，重启后由 `XAUTOCLAIM` 接管重投
（空闲 60s 才接管，避免抢正在处理的批次），而 `handle_message` 幂等（dict 覆盖 + 冗余
数组按最终状态重算），重放不脏数据。处理失败**不 ack**：留在 PEL 等下一轮收尸，
失败在日志里持续可见。

### 生产者侧（`tasks.py`）

- 只做展开与投递，**不写库**；路由到独立队列 `access_flow`；
- 任务级 `acks_late` + `reject_on_worker_lost`：worker 崩溃/被杀时任务重回队列；
- **背压**：`backlog() > ACCESS_FLOW_MAX_QUEUE` 就 `self.retry(countdown=2)` 让路——
  **绝不在任务里 sleep**，那会占死 worker 进程，执行队列的进程全被占住就整池瘫痪；
- **同设备互斥**：`device_lock` 用 `blocking=False`，拿不到立刻重试（等待同样是占死进程）；
- `max_retries=150` × 2s ≈ 5 分钟上限：队列持续堵塞时必须以可见的 FAILURE 收场，
  不能无限重试把问题埋掉。

### 关键参数与坑

| 项 | 值 | 理由 |
|----|-----|------|
| `socket_timeout` | 10s | **必须 > 消费端 `XREADGROUP` 的 `block`（5s）**：两者相等时 stream 一空，服务端阻塞满 5s 才回包、客户端 5s 就断读，每轮必抛 TimeoutError（实测消费循环空转 32 次/6 分钟） |
| `decode_responses` | `False` | 消息体按 bytes 处理；**凡读响应做比较/拼接/展示都要过 `as_str()`**——组名是 bytes 时与 str 常量比较恒为 False，`str(bytes)` 又会拼出 `"b'...'"` 伪 ID（喂给 XRANGE 报错） |
| Stream `maxlen` | `ACCESS_FLOW_MAX_QUEUE * 4` | 背压是主动限流，maxlen 是爆内存的最后防线 |
| 心跳 TTL | 300s | 每轮循环**开头**盖章（不能等 `XREADGROUP` 成功：读超时走 except 也该盖章，否则持续失败会让心跳停更、把活着的进程判死） |
| 设备锁 | 600s | 超时后 Redis 自动释放，`release()` 失败只告警 |

**积压口径是 `XINFO GROUPS` 的 `lag`，不是 XLEN**：XACK 不删条目，已消费的会一直躺到
maxlen trim 才走——用 XLEN 会把「消化完了但条目还躺着」误判成积压，阈值调低后必然误触发。
Redis 不可达时 `backlog()` 返回 0（不背压）：真正的失败会在随后的加锁/投递处暴露并转成重试。

**兼容旧 wire 格式**：升级前的消息是九元组（没有 action 一位），消费侧按 `allow` 兜底，
否则 `key[9]` 直接 IndexError 崩掉 consumer；deny 混行由下一次 rebuild 的 `sync_device` 拆正。

### 任务名与依赖方向

任务名的**唯一定义处**是 `settings.ACCESS_FLOW_TASK`。ingest 侧的投递触点
（`ingest.access_flow_trigger`）按这个名字 `send_task`，**不 import analysis**
（依赖方向 `analysis → ingest` 单向）。三处（常量 / 装饰器 `name=` /
`CELERY_TASK_ROUTES` 的 key）由 `tests/analysis/test_access_flow_task.py` 对账。

**改名部署注意**：Redis 里未消费的旧名消息会 `Unknown task`——升级前停 worker、
清空 `access_flow` 队列再滚动。2026-09 由 `ingest.rebuild_access_flows` 迁到
`analysis.rebuild_access_flows` 时就是这套动作（队列名、stream 名、心跳键、命令名都没变）。

### 队列与消费者部署

`worker` 以 `-Q celery,access_flow --concurrency=2` 一并消费。曾为它单开过
`worker-access` 服务做故障域隔离，**已合并**：两条链皆低频，共享 2 个槽最坏是秒级排队，
而独占服务是 +677MB / +16 进程的常驻保费；队列本身保持独立，出现主链被饿死的实测证据时
再把独占服务加回来。

## 四、互联网资产分析（`api/analysis.py`）与 SLB/GTM 链路（`api/lb_chain.py`）

### 链路解析

从 GSLB 设备的 WideIP 出发逐层解析到最终后端：

```
GSLB 设备
  └─ GtmWideip（域名，pools 为池名列表）
      └─ GtmPool（池，members 形如 "server_name:vs_name"）
          └─ GtmVServer（GTM 侧虚拟服务器，含 IP 与端口）
              ├─ 未找到 → 结果标记「未找到」
              └─ 找到 → 用 IP:端口 查 LtmVirtualServer
                  ├─ 未找到 → 返回 vserver 的 IP:端口
                  └─ 找到 → LtmPool → LtmPoolMember
                      └─ 用成员的 IP:端口 再查 LtmVirtualServer（级联 LB，最多 3 层）
```

整个过程只做 4 次查询（WideIP / GTM VServer / LTM VS / LTM 成员各一次），再在内存里
索引匹配，避免逐条查库。

**结果不实时计算**：分析成本不低而结果变化不频繁，只在手动触发
`POST /api/internet-analysis/analyze/` 时重算并写入 `InternetAnalysis` 缓存表；
`GET /api/internet-analysis/` 与导出接口都只读缓存。

### 三个容易踩的点

- **GTM 池成员有三种形态**：模板产出 `{"server_name", "vs_name"}`、`GtmPoolSaver`
  入库后的口径 `{"server", "vserver"}`（`_normalize_members` 会改名）、手工录入的
  `"server:vs"` 字符串。只认第一种会让 `vs_name` 恒为空，链路在第一步就被判成
  「GTM 虚拟服务器未找到」。
- **IPv6 地址必须规范化后比较**：`GtmVServer.ip_address` 是 `GenericIPAddressField`
  （Django 已小写 + 压缩），`LtmVirtualServer.vs_address` 是 `CharField`（原样存）。
  直接字符串比较时 `2001:DB8::1` / `2001:0db8::1` 匹配不上，IPv6 链路断在
  「找不到对应的 LLB 虚拟服务器」。
- **地址与端口分隔符是 `#`，不是 `:`**：IPv6 本身带冒号，`2001:db8::1:80` 分不清哪段
  是端口（`[...]:80` 虽标准，但 IPv4 用方括号又多余）。`#` 不可能出现在地址里，
  含义唯一且紧凑。前端 `internet-asset.vue` 的 `TARGET_SEPARATOR` 与后端保持一致。

### 负责人列

按链路**最后的 IP** 反查 `ServerOwner`，回退顺序是
`slb_member_address → llb_member_address → gtm_ip`（见 `_final_ip`）。匹配前两边都过
`_normalize_ip`，否则 `2001:DB8::1` 与压缩写法对不上。负责人**不进分析缓存**——它挂在
`build_path_rows` / `GET` 响应上现查，改了负责人不必重跑分析。前端表格自己扁平化、拿不到
数据库，所以 GET 响应额外给一份 `owners`（键是链路最后 IP 的**原始写法**，与前端用同一份
回退规则取值），避免在 JS 里重实现 IPv6 规范化。

### 扁平表与导出

一行 = 一条从域名到最终后端的完整链路。只保留 LLB / SLB 两级虚拟服务器与最后一跳的
服务器：**LLB 的池成员就是 SLB 的虚拟服务器**（同一份地址:端口），占两组列是重复的，
所以合并成 `LLB_VS` / `SLB_VS` / 服务器 三段。

导出是 openpyxl 后端生成 xlsx、前端只下载 Blob（与互联网资产分析同模式）。
**列序与前端 `slb.vue` / `gslb.vue` 的扁平列组手工保持一致**——表格渲染在前端、
导出在后端的两份扁平化并存是项目既定先例（见 internet-asset 的 `build_path_rows`），
改列时两边一起改。

互联网资产分析当前 7 列：域名 / LLB_VS地址#端口 / LLB_Rule规则 / SLB_VS地址#端口 /
SLB_Rule规则 / 服务器地址#端口 / 负责人。几个别顺手改坏的细节：

- **「服务器地址#端口」是链路最后一跳的池成员**：两级取 SLB 的、一级取 LLB 的，断链时回退到
  GTM 地址（见 `_final_target`）。有测试 `test_llb_member_equals_slb_virtual_server` 守这个前提。
- 行字典里仍保留 `llb_address` / `llb_port` / `slb_member_address` 这类**分列字段**（导出与展示时
  再按 `TARGET_SEPARATOR` 拼成 `地址#端口`）；`note` / `rtype` / `gtm_ip` 也仍在行里，只是不再
  出现在表格与导出中——`note` 还被前端用来算「已解析」条数，删列时别顺手删字段。
- `EXPORT_COLUMN_WIDTHS` 的条数必须与 `EXPORT_HEADERS` 相同（有测试守），列宽按序号用
  `get_column_letter` 生成，别写死 `"ABCDEFGHIJKLM"`。
- 分隔符是两端各一个常量（后端 `TARGET_SEPARATOR`、前端 `internet-asset.vue` 同名常量），
  改要一起改；有测试守「`#` 不可能出现在 IP 里、且能唯一切回」。
- 前端模板里**不要把 `row` 作为参数传给函数**（`serverTarget(row)`）：Element Plus 插槽给的
  `row` 是它自己的 `DefaultRow`，传给形参类型为 `PathRow` 的函数会 `vue-tsc` 报错；把拼好的值
  预先算进行字段（`llbTarget` / `slbTarget` / `serverTarget`）再读属性即可。

## 五、队列积压巡检（`queue_monitor.py`）

访问流是「celery 队列 → Redis Stream → 单写者 consumer」三段接力，任何一段卡死
（worker 挂了 / consumer OOM 循环 / 毒消息反复重投）都表现为**静默积压**——
2026-10 的实盘事故就是 Stream 里 47 条消息无人消化、consumer 反复 OOM 重启，外部没有任何信号。
本模块把三段的关键指标一次采出来，供三个出口共用：

- `manage.py queue_status`：人看表格 / `--json` 机器可读，超阈值退出码 1（可接 cron 告警）；
- `/api/analysis/queue-status/`：前端 Home 页的积压监控卡片每 30s 轮询；
- `manage.py queue_backlog`：积压**明细**（`collect_backlog`），回答「积压了哪些」。

采集全是 O(1) 的 Redis 命令（LLEN / HLEN / XLEN / XINFO GROUPS / XPENDING 明细限量 50 条 /
GET），不碰 worker、不碰数据库，30s 轮询无压力。

| 指标 | 口径 |
|------|------|
| `queues` | 各 celery 队列的 LLEN——排队**未执行**的任务数 |
| `unacked` | `unacked` hash 的 HLEN——已取走未确认的**执行中**任务数（worker 死掉会滞留，是先行指标） |
| `stream.lag` | XINFO GROUPS 的 `lag`——从未投递给消费者的积压（真实待消费量） |
| `stream.pending` | PEL 条数——已投递未确认（含正在处理 + 卡住的） |
| `stream.top_pending` | 按重投次数排序的前 5 条——`deliveries` 高就是毒消息（反复失败不 ack、被 XAUTOCLAIM 反复捞回） |
| `heartbeat_age` | `access_flow:heartbeat` 距今秒数——consumer 活性的唯一外部信号 |

阈值默认值见 `DEFAULT_THRESHOLDS`（单队列 1000 / unacked 100 / lag 200 / PEL 50 /
重投 10 / 心跳 600s）。**Redis 不可达不抛异常**：返回 `redis_ok=False` + critical 告警——
监控自身炸掉比被监控对象炸掉更没意义。

`collect_backlog` 的三段：各队列 `LRANGE` 头部若干条（broker 消息是 JSON + base64 body，
解不动按原文截断）、PEL 逐条点名、`last-delivered` 之后的未投递部分（**不含**已消费
未 trim 的旧条目）。

## 大屏供数（Dashboard）

两条链，接缝仍是「只认任务名字符串」：设备状态 / 工单 / SLB / 巡检仍落库；**链路带宽**
改为 Zabbix 直取 + Redis 缓存，不落库。

```
ingest.collect_dashboard(source)        # 设备组 / Autotask：纯 dict payload
  ← 内置 beat 投递：zabbix 每 DASHBOARD_COLLECT_SECONDS（180s）
                   autotask 每 DASHBOARD_AUTOTASK_SECONDS（600s）
  → send_task(settings.DASHBOARD_WRITE_TASK)
analysis.write_dashboard(payload)       # 唯一写库入口（一个事务内 upsert）

conf/links.json                         # 链路清单与展示 label 的唯一权威
  → ingest.refresh_link_cache           # beat 周期 / 管理命令 / beat 启动钩子
  → Zabbix history.get（3 分钟分桶，多监控项取 max）
  → SET dashboard:link:series（TTL > 刷新周期）

GET /api/dashboard/                     # 只读：指标表 + 链路缓存
```

**写库（`analysis/tasks.py: write_dashboard`）**：事务内 `update_or_create`
`DashboardMetric` / `MetricSample` / `ItsmCase`；工单再物化成 `panel=itsmtask` 的指标行；
全量快照里消失的工单置 `is_active=False` 并删旧指标；每批另写一行 `CollectionRun`（不覆盖，
供新鲜度审计）。唯一键保证**重复投递幂等**。

**两种投递方式**（`settings/base.py`）：默认 payload 随消息直投（A 方案）；
`DASHBOARD_PAYLOAD_VIA_REDIS=1` 时存 Redis、只投 `{"__redis_key__": …}`（C 方案，避免大 payload
塞进 broker 消息），TTL `DASHBOARD_PAYLOAD_TTL=600`，写库侧取完即删、key 丢失直接报错。

**模型（`analysis/models/dashboard.py`）**：

| 模型 | 用途 |
|------|------|
| `DashboardMetric` | 当前值（EAV：`panel` / `group` / `name` / `value`，`value` 是 JSONField 保住 `string \| number`） |
| `MetricSample` | 时序（唯一键含 `sampled_at`，同一时间点重跑不重复；为将来转 TimescaleDB hypertable 留路） |
| `ItsmCase` | 工单快照（`is_active` 标记本轮是否仍在） |
| `CollectionRun` | 每批采集一行（status / 时间 / 计数），只追加 |
| `LinkTarget` | 链路目标配置表（**当前不使用**；链路清单在 `conf/links.json`，采集器不能反向读 analysis 的表） |

**读接口**：`GET /api/dashboard/?panel=&group=&name=`（`analysis/api/dashboard.py`）只读；
`group=linechart` 或 `name=bandwidth-*` 时**不查 `MetricSample`**，读 Redis 缓存
`dashboard:link:series` 并拼回旧 EAV 行视图；响应的 `meta` 带脱敏的 panels / scopes /
target label（不含 host / ifname），前端一次请求拿全。缓存未生成时返回空数组，前端保留
上一次成功结果。它是全项目唯一用 `{status, message, result}` 包装的响应。契约测试：
`tests/ingest/test_dashboard_collect.py` + `tests/ingest/test_link_cache.py` +
`tests/analysis/test_dashboard_write.py` + `tests/analysis/test_dashboard_api.py`。

### 链路带宽：配置、缓存与刷新

- **配置**：`conf/links.json`（入库、随版本走；宿主 `conf/` 只读挂到容器
  `/etc/netops/conf`）。`panels` 是图标题 + scope 分组，`scopes` 是 scope 中文名，
  `targets` 是 `scope / subject / label / host / ifname / enabled`。`subject` 是稳定数据键，
  `label` 可随意改；`host` / `ifname` 只给采集侧，不下发免认证接口。
- **刷新**：`ingest.refresh_link_cache`（beat 周期 `DASHBOARD_LINK_REFRESH_SECONDS`，默认
  180s）与管理命令 `python manage.py refresh_link_cache [--check]`；beat 启动时先同步刷一次
  （失败不阻塞，下个周期重试）。TTL `DASHBOARD_LINK_CACHE_TTL`（默认 600s）大于刷新周期，
  Zabbix 抖动时还能读到上一份。
- **失败隔离**：单条链路失败只 warning、其余照常；全部失败抛 `LinkCollectionError`（消息里
  带每个 target 的原因摘要、`from None` 去掉异常链），全挂时**不再逐条 warning**。
  - 管理命令：异常照旧上抛 → 非零退出（`refresh_link_cache` 的 `CommandError`）。
  - Celery 任务：`refresh_link_cache_task` **捕获 `LinkCollectionError`**，记一条 `ERROR`
    并返回 `{"status": "failed", "error": ...}`，**不 raise**——外部源整体不可用时 worker
    日志不再打整段 traceback（180s 一轮会刷屏），下个周期自动重试；Redis / `conf/links.json`
    这类真实故障仍上抛，Celery 记 FAILURE、traceback 保留。
- **缓存未生成时的降级**：`read_link_cache()` 返回 `None` 时，读接口用
  `empty_link_payload()` 下发「静态 meta + `points: []` + `refreshed_at: null`」空壳——
  **不写 Redis、不造 0 值曲线**（全 0 会把 Zabbix 全挂伪装成零流量）。meta 来自
  `conf/links.json`（`LinkConfig.meta()`，静态部分用 `lru_cache` 缓存），前端据此仍能拿到
  panels / scopes / targets 画出空图框并显示「暂无链路采样数据」，而不是整块折线图消失；
  `refreshed_at` 为空且前端仍保留旧图时提示「数据未更新，显示上一次结果」，避免热重启后的静默陈旧。
- **前端**：`LinkBandwidthWidget` 不再硬编码 `SCOPE_LABELS` / `SUBJECT_LABELS`，label、分组、
  停用过滤都来自响应 `meta`；全量取（3 小时窗口约几十 KB），新数据到达前保留旧值，
  `LineCharts` 用 `replaceMerge` 清掉已删除的 series。
- 前端那份 `dashboard.config.json` 没有采用（只改 UI，不解决「监控哪几条线」）；
  `MetricSample` 里旧的 `link_bandwidth` 样本不再被读，可忽略；`LinkTarget` 表仍未启用。
