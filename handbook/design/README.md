# handbook/design/ —— 设计文档（尚未实现）

本目录收**「已经想清楚、但代码里还没这么写」**的设计。

与 `handbook/` 根目录的区别是硬性的：

| | `handbook/` 根目录 | `handbook/design/` |
|---|---|---|
| 描述的是 | **已实现**的行为 | **待实施**的设计 |
| 读者在 | 改代码前查约定 | 决定要不要做、做之前查方案 |
| 过期风险 | 跟着代码走，改代码就改文档 | 方案落地后要迁回根目录或删掉 |
| 与代码的一致性 | 必须一致 | **故意不一致**（代码还没改） |

**代码里不要引用本目录的结论当既定事实**——这些是提案，不是现状。现状查根目录的文档。
真要引用某条设计时，写「见 `handbook/design/` 的 X（提案）」并注明「尚未实施」。

## 目录

| 文件 | 内容 | 状态 |
|------|------|------|
| [`layering.md`](layering.md) | 域分层总图、依赖矩阵、各域职责边界、跨域调用与写入规范 | 实施中（core 去业务依赖已全部落地；configs 拆分 / ingest 收窄 / 外部连接未动） |
| [`assets-configs-split.md`](assets-configs-split.md) | assets / configs 域拆分方案：模型归属、软资产归并、Saver 与解析器归属、迁移手法 | 实施中（切片 1–4 已落地：26 张表 + 序列化器 + parsers/savers/mapping + admin 26/API 26；剩 llmtools 改名/软资产/purge 迁 scripts，2026-11-16） |
| [`external-clients.md`](external-clients.md) | core 承载外部连接实例与 client 生命周期：provider 注册、实例持有、释放钩子、健康状态 | 提案（2026-11-16 评审修正），待实施 |

## 这批设计的共同前提

四份文档共享同一套分层约定，任何一份单独看都不完整：

- **域只依赖它下面的域**，没有反向依赖，没有跨层。
- **跨域调用不 import 对方的模块**，用 Celery 任务名 + `send_task`（范本见 `apps/ingest/access_flow_trigger.py`）。
- **跨域写入走服务调用**，不直接 ORM 写对方的表；写入权归属明确写在分层文档里。
- **URL 前缀不变**——拆分是内部结构调整，前端零改动（范本：analysis 拆分时沿用 `/api/trace/`、`/api/internet-analysis/`）。
- **core 零业务依赖**——core 只持有各域在 `ready()` 里注册进来的对象（业务词汇、provider），
  自己不 import 任何域模块，也不认识具体业务对象。

## 状态标记

每份文档开头有状态标记，实施过程中逐条更新：

- **提案**：设计已成型，未动手
- **实施中**：正在改代码，改到哪写到哪
- **已落地**：代码与设计一致，**迁回 `handbook/` 根目录或删掉**

## 评审记录

- **2026-11-16 落地归档**：`task-framework.md` 三步全部落地，内容已并入
  [`../tasks.md`](../tasks.md)（现状）与本文件的历史记录，设计稿删除。
  本文与其他两份提案里对它的引用相应改指 `../tasks.md`。
- **2026-11-16 二次评审**：修正四份提案的内部矛盾与遗漏——core 任务机制补
  stage→handler 注册表（消除 first_stage 硬编码矛盾）、词汇 choices 改「字段去 choices +
  注册表」（原「ready() 注册进 choices」会造成迁移漂移，不可行）、Task.device 补 RunPython
  数据迁移、ArpMac 拍板改继承 ConfigBase 随家族迁 configs、device_import 拍板整体迁 ingest、
  `soft_assets_stale` 信号对象迁 configs（实测发送辅助函数在 assets/signals.py，原文有误）、
  resolve_config_owner 迁 configs、补 admin（26 注册）与 API 层（26 端点）搬迁清单、
  configs 初始迁移对 assets 的 dependencies 声明、llmtools import 修复必须与拆分同提交、
  依赖矩阵 docs 行按实测收敛为只依赖 core、IntegrationHealth probe 调度定为 Celery beat。
