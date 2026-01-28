import logging
from netmiko import ConnectHandler
from netmiko.base_connection import BaseConnection
from typing import Dict, Any, Union

# Configure logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

class NetmikoService:
    """
    Netmiko服务类，负责与网络设备的连接和命令执行
    """
    
    @staticmethod
    def create_connection(device_info: Dict[str, Any]) -> BaseConnection:
        """
        创建并返回网络设备连接
        
        Args:
            device_info: 设备信息字典，包含device_type, ip, username, password等
            
        Returns:
            建立好的网络设备连接对象
        
        Raises:
            Exception: 连接失败时抛出异常
        """
        logger.info(f"Creating connection to device: {device_info.get('hostname', 'unknown')} ({device_info['address']})")
        
        # 创建连接参数
        connection_params = {
            "device_type": device_info["device_type"],
            "ip": device_info["address"],
            "username": device_info["username"],
            "password": device_info["password"],
            "timeout": 30,
        }
        logger.debug(f"Connection params: {connection_params}")
        
        # 连接到设备
        logger.info(f"Connecting to {device_info['address']}...")
        conn = ConnectHandler(**connection_params)
        logger.info(f"Successfully connected to {device_info['address']}")
        
        # Enter enable mode if needed
        if device_info["device_type"].startswith('cisco'):
            logger.info(f"Entering enable mode on {device_info['address']}")
            conn.enable()
            logger.debug(f"Enabled enable mode on {device_info['address']}")
        
        return conn
    
    @staticmethod
    def execute_command(conn: BaseConnection, command: str):
        """
        在已建立的连接上执行命令
        
        Args:
            conn: 已建立的网络设备连接对象
            command: 要执行的命令字符串
            
        Returns:
            命令执行结果
        
        Raises:
            Exception: 命令执行失败时抛出异常
        """
        logger.info(f"Executing command: '{command}' on {conn.host}")
        result = conn.send_command(command)
        logger.debug(f"Command result: {result[:100]}..." if isinstance(result, str) and len(result) > 100 else 
                     f"Command result: {result}" if not isinstance(result, str) and isinstance(result, list) and len(result) > 100 else f"Command result: {result}")    
        return result
    
    @staticmethod
    def get_device_config(device_info: Dict[str, Any]):
        """
        获取网络设备的运行配置
        
        Args:
            device_info: 设备信息字典，包含device_type, ip, username, password等
            
        Returns:
            设备的运行配置字符串
        
        Raises:
            Exception: 连接失败或获取配置失败时抛出异常
        """
        hostname = device_info.get('hostname', 'unknown')
        config = ""
        logger.info(f"Getting running config for {hostname} ({device_info['address']})")
        
        # 使用with语句确保连接会被关闭
        with NetmikoService.create_connection(device_info) as conn:
            # Get running configuration
            if conn.device_type == "hp_comware":
                config = NetmikoService.execute_command(conn, "display current-config")
            elif conn.device_type == "hillstone_stoneos":
                config = NetmikoService.execute_command(conn, "show configuration")
            logger.info(f"Successfully got running config for {hostname}")
        if config and isinstance(config, str):
            return config
