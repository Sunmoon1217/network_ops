from pydantic import BaseModel

class DeviceInfo(BaseModel):
    """
    设备信息模型，用于验证和传递设备连接信息
    """
    hostname: str
    address: str
    username: str
    password: str
    device_type: str

class ConfigResponse(BaseModel):
    """
    配置响应模型，用于定义API返回的数据结构
    """
    success: bool
    hostname: str
    address: str
    config: str
