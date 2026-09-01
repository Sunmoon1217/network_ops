"""采集器基类"""
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class CollectResult:
    success: bool
    hostname: str
    config: str = ""
    error: str = ""
    device_id: int | None = None
    message: str = ""
    config_id: int | None = None
    saved: bool = False


class BaseCollector(ABC):
    @abstractmethod
    def collect(self, device, connection) -> CollectResult:
        """采集设备配置"""
