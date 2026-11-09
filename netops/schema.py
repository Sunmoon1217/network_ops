"""项目级 Pydantic 基类：外部 API 响应的 DTO 统一允许额外字段。

第三方 API（Zabbix、云平台等）返回的字段随版本变化，逐项声明既不现实也没必要：
继承本基类后，已声明字段照常做类型校验，未声明字段保留在实例上
（``model_dump()`` 也会带上），不会像 pydantic 默认的 ``extra="ignore"`` 那样被静默丢弃。

放在 ``netops/`` 而不是某个业务 app：这是跨 app 的项目级约定，与
``netops/pagination.py``（DRF 全站分页）、``netops/mcp_server.py``（MCP 根单例）
同类；域模块按既有方向 ``from netops.schema import ExtraModel`` 引用，不让
``ingest`` 之类的数据域反向依赖 ``core``（用户与认证域）。
"""

from pydantic import BaseModel, ConfigDict

__all__ = ["ExtraModel"]


class ExtraModel(BaseModel):
    """允许额外字段的 DTO 基类：已声明字段校验类型，未声明字段原样保留。"""

    model_config = ConfigDict(extra="allow")
