from pathlib import Path
from ttp import ttp
from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)

class ConfigParser:
    """
    配置解析服务类，使用TTP模板解析设备配置
    """
    
    def __init__(self):
        self.template_dir = Path(__file__).parent / 'ttp_tmpl'
    
    def get_template_path(self, device_type: str) -> str:
        """
        根据设备类型获取对应的TTP模板路径
        
        Args:
            device_type: 设备类型，如 'hp_comware', 'cisco_ios' 等
            
        Returns:
            TTP模板文件路径
        """
        template_map = {
            'hp_comware': 'h3c.ttp',
            'f5': 'f5.ttp',
            'f5_bigip': 'f5.ttp',
            # 可以添加更多设备类型的模板映射
            # 'cisco_ios': 'cisco_ios_template.ttp',
            # 'juniper_junos': 'juniper_junos_template.ttp',
        }
        
        template_file = template_map.get(device_type, '')
        template_path = self.template_dir / template_file
        logger.info(f"模板路径: {template_path}")
        
        # 如果模板文件不存在，使用默认模板
        if not template_path.exists():
            raise FileNotFoundError(f"模板文件不存在: {template_path}")
        
        return template_path.as_posix()
    
    def parse_config(self, config: str, device_type: str) -> Dict[str, Any]:
        """
        使用TTP模板解析设备配置
        
        Args:
            config: 原始设备配置文本
            device_type: 设备类型
            
        Returns:
            解析后的配置字典
        """
        # 获取模板路径
        template_path = self.get_template_path(device_type)
        
        # 创建TTP解析器
        parser = ttp(data=config, template=template_path)
        
        # 执行解析
        parser.parse()
        
        # 获取解析结果
        parsed_result = parser.result()
        
        # 检查解析结果是否为空
        if not parsed_result:
            raise ValueError("解析结果为空")

        # 提取解析结果中的第一个元素
        parsed_result = parsed_result[0][0]
        
        
        return parsed_result

# 创建全局配置解析器实例
config_parser = ConfigParser()
