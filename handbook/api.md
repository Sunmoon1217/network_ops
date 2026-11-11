# API 路由

`netops/urls.py` 依次 include 五个应用的 urls，全部挂载在 `/api/` 下。
其余路径交给前端 SPA（`netops/views.py` 托管 `frontend/dist`）。

## 认证约定

- **「账号密码换 token」的接口必须显式 `@authentication_classes([])`**（`login` / `register`
  都是）：否则浏览器带着已登录的 `sessionid` 打过来会被 DRF 的 `SessionAuthentication` 拦成
  403——**换个 host 就"好了"是假象**（cookie 域不同而已）。原理见技能
  `django-drf-gotchas` 第 1 节；回归测试 `tests/core/test_auth_login_csrf.py`。
- **注册开放，但只创建普通账号**：`POST /api/auth/register/` 只开放 `username` / `password` /
  `email`（可选）/ `phone`（可选），`is_staff` / `is_superuser` / `is_active` 由服务端决定，
  走 `create_user()`（**不是** `create_superuser()`）。四条要点：① 视图显式
  `@authentication_classes([])`；② 密码过 `AUTH_PASSWORD_VALIDATORS` 的
  `validate_password(password, user=candidate)`（**必须传候选用户**，否则相似度校验不生效）；
  ③ 用户名用 `iexact` 判重（数据库唯一约束**大小写敏感**，只查 `exact` 会放过 `Admin` 与
  `admin` 并存）；④ 成功直接返回 token（与 `login` 同形 `{token, user:{id,username}}`）。
  **没有邮箱验证 / 审批 / 限流**（项目没配 `CACHES`，DRF 限流只会退化成单进程计数），要收紧得
  自己加开关 / 邀请码 / 审批；`email` 不是 unique。前端：`views/auth/Register.vue` + `/register`
  （`meta.skipLayout`）。
- 权限走全局默认 `IsOperatorOrReadOnly`：读任何已认证用户可用，写限操作员（`role=operator`）
  或超管；`/api/me/` 返回派生的写权限，前端据此隐藏写入口，不必复刻后端规则。
- 分页与搜索排序是全局默认（`netops/pagination.py` 的 `StandardPagination`：默认 50 条/页、
  最大 500，`?page_size=` 覆盖），列表返回 `{count, next, previous, results}`；各 ViewSet 声明
  `search_fields` / `ordering_fields`。前端统一用 `useCrudApi` + `DataPagination` 消费；
  必须全量的场景（下拉选项、前端聚合统计）用 `fetchAllPages`。

## core（`core/api/urls.py`）

| 路径 | 说明 |
|------|------|
| `/api/auth/register/` | 注册普通账号（**开放**，成功即返回 token） |
| `/api/auth/login/` | 登录获取 Token |
| `/api/auth/logout/` | 登出 |
| `/api/me/` | 当前用户信息 |
| `/api/me/preferences/` | 当前用户的前端配置（表格列宽等）：GET 全量 / PUT 单条 upsert（`value=null` 即删）/ DELETE `?key=`；按用户隔离 |
| `/api/tasks/` | 任务列表 / 新建（**新建即投递采集阶段**，是 Celery 工作流的入口） |
| `/api/tasks/<id>/` | 任务详情（含嵌套的阶段数组） |
| `/api/tasks/<id>/cancel/` | 取消任务（已结束的返回 400） |
| `/api/stages/` | 阶段列表（只读，可按 `task` / `stage_type` / `status` 过滤） |

## assets（`assets/api/urls.py`，前缀 `/api/assets/`）

DRF `SimpleRouter`（`trailing_slash=True`），资源列表：

```
security-zones, datacenters, rooms, cabinets,
vendors, device-models, devices, device-configs, device-connections, device-accounts,
device-groups, device-group-members,
vlans, vrfs, interfaces,
snmp-configs, ntp-configs, syslog-configs,
ltm-virtual-servers, ltm-pools, ltm-pool-members, ltm-profiles, ltm-irules, ltm-snats, ltm-persists,
gtm-datacenters, gtm-wideips, gtm-pools, gtm-servers, gtm-vservers,
address-books, services, policies, nat-rules,
routes, topologies, arp-mac, subnet-usage-logs,
tags, subnets, ip-addresses
```

另有函数视图：

| 路径 | 说明 |
|------|------|
| `/api/assets/overview/` | 总览聚合统计 |
| `/api/assets/import-devices/` | Excel 导入设备。Sheet 清单 / 顺序 / 列头 / 导入函数唯一来源是 `assets/device_import.py` 的 `IMPORT_SHEETS`；含「设备组」Sheet：`组类型 \| 设备名(多个用逗号分隔) \| 描述`，**一行 = 一个设备组**。组名与角色不填表、由导入推：非集群第一台 = 主、第二台 = 备且组名 = 主设备 hostname；集群全部 = 成员且组名由设备名结构里的「安全区+设备类型」得到（设备名 `NET-<数据中心+机柜位置>-<安全区>-<设备类型+编号>`，首段 `NET` 大小写不敏感、段数 ≥ 4，安全区与类型取最后两段、类型段去尾部编号，如 `NET-SH01-R05-SEC-FW01`/`…FW02` → `SEC-FW`），不符合结构或同行拆出的安全区/类型不一致则回退第一台 hostname。行是该组的**完整快照**，不在行里的既有成员会被摘掉 |
| `/api/assets/import-template/` | 下载导入模板 xlsx：按 `IMPORT_SHEETS` 生成表头（与导入分发同源，只写表头、不放示例行） |

## ingest（`ingest/api/urls.py`）

| 路径 | 说明 |
|------|------|
| `/api/configs/git-content/` | 获取指定 commit 的配置内容 |
| `/api/configs/git-diff/` | 对比两个版本的配置差异 |
| `/api/configs/history/` | 设备配置变更历史 |
| `/api/configs/devices/` | 列出有配置的设备 |
| `/api/parsers/` | 已注册解析器列表 |
| `/api/parsers/mapping/` | 解析器 → 模板 → 产出键 → Saver 的映射清单与契约缺口（顶层增量字段 `key_aliases` / `field_aliases` / `savers`，`consumers` 条目附 `canonical_key` / `models`） |
| `/api/parsers/templates/` | TTP 模板文件列表（`configs/` + `running/`） |
| `/api/parsers/templates/<name>/` | 模板文件内容 |
| `/api/parsers/templates/<name>/update/` | 更新模板文件内容（PUT） |

## analysis（`analysis/api/urls.py`，前缀沿用拆分前，前端零改动）

| 路径 | 说明 |
|------|------|
| `/api/trace/` | 路径追踪 |
| `/api/trace/route-collect/` | 路由采集 |
| `/api/trace/route-collect-raw/` | 路由采集（原始输出） |
| `/api/trace/routes/` | 路由列表 |
| `/api/trace/dns-query/` | DNS 查询 |
| `/api/internet-analysis/` | 互联网资产分析结果（**只读缓存**，未分析过返回 404） |
| `/api/internet-analysis/analyze/` | **触发分析**并刷新缓存（POST） |
| `/api/internet-analysis/export/` | 导出缓存结果为 xlsx（只读缓存） |
| `/api/access-flows/` | 访问流（策略展开结果）**只读**列表，`?device=` / `?policy=` 走 GIN 包含过滤 |
| `/api/analysis/queue-status/` | 队列积压巡检（只读）：celery 队列 / Stream lag / PEL / 消费者心跳 + 告警列表，Home 页卡片 30s 轮询 |
| `/api/analysis/redis-status/` | Redis 服务状态（只读，INFO 口径）：内存/连接/命中率/键空间/运行时长，「任务中心 → 运行监控」页轮询 |
| `/api/analysis/celery-status/` | Celery worker/任务（只读，inspect 口径）：worker 名单 / 执行中 / 排队 / 延迟，同页轮询 |
| `/api/analysis/lb-chain/slb/`、`/api/analysis/lb-chain/gslb/` 等 | SLB/GSLB 链路查询与导出（含 `facets/`、`export/`） |
| `/api/analysis/gslb-clusters/`、`/api/analysis/ltm-groups/`、`/api/analysis/firewall-groups/` | 分组聚合查询（列表 / `facets/` / `export/`；防火墙分 `policies/` 与 `nat-rules/`） |

## docs 业务域（`apps/docs/api/urls.py`，前缀 `/api/docs/`）

| 路径 | 说明 |
|------|------|
| `/api/docs/spreadsheets/` | 通用表格工作簿列表 / 上传 xlsx 建簿（原 `/api/sheets/`） |
| `/api/docs/spreadsheets/<id>/`、`/export/`、`/revisions/…` | 详情 / 保存编辑 / 导出 xlsx / 修改历史与回滚 |
| `/api/docs/documents/` | 文档列表 / **上传转换**（multipart：`file` 主文档 + `attachments` 图片附件）；转换规则见 [`docs-domain.md`](docs-domain.md) |
| `/api/docs/documents/<id>/` | 详情（含转换产物）/ **编辑产物**（PUT，落新版本快照）/ 删除 |
| `/api/docs/documents/<id>/preview/` | 查看用渲染产物（md 由后端 markdown 库渲染 html，前端沙箱 iframe 展示） |
| `/api/docs/documents/<id>/download/` | 源文件下载（docx/pdf 等原文件留档） |
| `/api/docs/documents/<id>/reconvert/` | 替换源文件重新转换（产物落新版本；人工修改被覆盖但旧产物在历史里可回滚） |
| `/api/docs/documents/<id>/revisions/…` | 版本历史（`DocumentRevision` 产物快照）/ 快照详情 / 回滚（恢复以新版本落地，历史不改写） |
| `/api/docs/documents/<id>/push/` | 推送 Dify 知识库，**两态**：未推送 create（md/html 走 `create_by_text`、pdf 走 `create-by-file`）；已推送且 `pending_sync` 走 `update_by-text` / `update-by-file` 按 `dify_document_id` **原地更新**（不产生重复文档）；已推送无待同步 409、未配置 503、失败 502（保持待同步可重试） |
| `/api/docs/documents/<id>/status/` | 从 Dify 同步索引进度（waiting / indexing / completed / error） |

Dify 推送配置在 `settings/base.py` 的 `DIFY_CONFIG`，变量清单见 [`settings.md`](settings.md)；
非密钥项在 `envs/common.env`（模板 `envs/example/common.env`），API Key 按部署方式在
`envs/container.env` / `envs/host.env` 给 `*_FILE` 或环境变量。

## API 文档（OpenAPI 3，drf-spectacular）

| 路径 | 说明 |
|------|------|
| `/api/schema/` | 浏览器入口，302 重定向到 Swagger UI（打开手册用这个） |
| `/api/schema/swagger-ui/` | Swagger UI |
| `/api/schema/redoc/` | ReDoc |
| `/api/schema/openapi.yaml` | OpenAPI 3 描述文件（YAML；`?format=json` 取 JSON），给 Postman / 代码生成器 / curl 用 |

**不叫 `/api/docs/`**——那是 docs 业务域前缀。两个 UI 都靠 `name="schema"` 反解描述文件地址，
所以 `/api/schema/` 不能再挂 `SpectacularAPIView`：那会让 UI 拉到重定向后的 HTML。重定向是
302（不缓存），也不透传 query string——原来 `/api/schema/?format=json`、`?lang=xx` 这类用法
改走 `/api/schema/openapi.yaml`。UI 资源走本地 sidecar（内网不通外网，随
`collectstatic` 进 `/static/` 由 nginx 直出）；权限由 `DJANGO_API_DOCS_REQUIRE_LOGIN` 控制
（默认放开，`SERVE_PERMISSIONS` 同时作用于四条路由）。四条路由按 `/api/` 前缀天然不会被 SPA
兜底吃掉，`tests/deploy/test_api_docs.py` 守。

## 大屏供数（`analysis/api/dashboard.py`）

| 路径 | 说明 |
|------|------|
| `GET /api/dashboard/` | **只读**供数：`?panel=` / `?group=` / `?name=` 过滤当前值；`group=linechart` 或 `name=bandwidth-*` 时把最近 3 小时的 `MetricSample` 聚合回 EAV 行视图 |

这是全项目**唯一**用 `{status, message, result}` 包装的响应（旧大屏前端的 axios 拦截器只取
`res.result`），别按 `{count, next, previous, results}` 的口径去改。写入口只有
`analysis.write_dashboard` 这个 celery 任务，没有写接口。
