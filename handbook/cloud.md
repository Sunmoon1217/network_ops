# cloud：阿里云接入

`apps/cloud/` 目前**没有对外 API**：只是一个客户端封装 + 云资源缓存模型，供后续的
云资产采集使用。

## 账号与 endpoint

一朵云、两个资源集（生产 / 测试），两套账号，**共用 region**；各产品 endpoint 不同，
分别由环境变量传入（清单见 [`settings.md`](settings.md)）。凭据链路同为
`*_FILE > 环境变量 > 空`。

`client.get_client(account, product)` 按账户名 + 产品代码返回预配置的 `AcsClient`，
传了 `product` 时给它绑上该产品的 endpoint（产品代码：`Ecs` / `Vpc` / `Slb` / `Sls` /
`Asapi`）。

## 三个模块的分工

| 模块 | 职责 |
|------|------|
| `client.py` | `AcsClient` 封装 + `aliyunapi` 的动作表（每个产品的 `list` / `info` 的 version 与 action 名）；另有 `AliyunASAPI`（走 ASAPI 网关，`timeout=30`、`verify=False`，异常统一转 `RuntimeError`） |
| `products.py` | 各产品的调用封装：`ecs_call` / `vpc_call` / `slb_call` / `sls_call`，统一走 `_call`（注入 `RegionId`、按 `set_<Param>` 设参数、空响应直接报错） |
| `response.py` | 云 API 响应类型对象 |
| `models.py` | 云资源缓存模型（`AliyunVPC` 等），把拉回来的资源落库，避免每次分析都打云 API |

`products._call` 的 `request_cls` 支持两种写法（模块或类都行，`_resolve_class` 兼容），
模块 docstring 里有两种导入方式的对照示例，新增产品照着复制即可。

## 为什么资源要落缓存表

云 API 有配额与延迟，分析/展示链路直接打云 API 既慢又容易触发限流；缓存表让「读」变成
纯本地查询，拉取变成显式的同步动作。缓存模型与 assets 的资产模型**不共用表**：云上资源
是外部事实，重新同步即可重建，而 assets 里的行有一部分是人工维护的。
