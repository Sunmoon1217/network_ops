"""配置域模型（包形式，与 ``assets/models/`` 同一套做法：定义在子模块，本文件只 re-export）。"""

from .base import ConfigBase
from .network import Vlan

__all__ = ["ConfigBase", "Vlan"]
