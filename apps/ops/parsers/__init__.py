# 导入厂商解析器以触发 @ParserFactory.register 装饰器
from ops.parsers.factory import (
    A10SLBParser,
    CiscoFWParser,
    F5GTMParser,
    F5LTMParser,
    H3CRouterParser,
    H3CSwitchParser,
    HillstoneFWParser,
    HuaweiSwitchParser,
)

__all__ = [
    "A10SLBParser",
    "CiscoFWParser",
    "F5GTMParser",
    "F5LTMParser",
    "H3CSwitchParser",
    "H3CRouterParser",
    "HillstoneFWParser",
    "HuaweiSwitchParser",
]
