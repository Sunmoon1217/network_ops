"""项目级 Pydantic 基类：外部 API 响应的 DTO 允许额外字段。

第三方字段随版本变化，未声明字段保留在实例上（model_dump() 也带上），不被静默丢弃。
跨 app 共用，故放 netops/；用法 `from netops.schema import ExtraModel`。
"""

from pydantic import BaseModel, ConfigDict

__all__ = ["ExtraModel"]


class ExtraModel(BaseModel):
    """允许额外字段的 DTO 基类：已声明字段校验类型，未声明字段原样保留。"""

    model_config = ConfigDict(extra="allow")
