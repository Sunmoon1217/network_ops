#!/usr/bin/env python3

"""
测试H3C交换机TTP模板的解析功能
"""

from pathlib import Path
from ttp import ttp


def test_h3c_template():
    """测试H3C交换机TTP模板"""
    # 获取模板路径
    template_path = Path(__file__).parent.parent / 'ttp_tmpl' / 'h3c_comprehensive.ttp'
    
    # 获取配置文件路径
    config_path = Path(__file__).parent / 'config.txt'
    
    # 检查文件是否存在
    if not template_path.exists():
        print(f"模板文件不存在: {template_path}")
        return False
    
    if not config_path.exists():
        print(f"配置文件不存在: {config_path}")
        return False
    
    # 读取配置文件内容
    with open(config_path, 'r', encoding='utf-8') as f:
        config_content = f.read()
    
    # 创建TTP解析器
    parser = ttp(data=config_content, template=template_path.as_posix())
    
    # 执行解析
    parser.parse()
    
    # 获取解析结果
    parsed_result = parser.result()
    
    # 检查解析结果
    if not parsed_result:
        print("解析结果为空")
        return False
    
    # 提取解析结果
    result = parsed_result[0][0]
    
    # 打印解析结果摘要
    print("解析结果摘要:")
    print(f"系统版本: {result.get('version', {}).get('version')}")
    print(f"主机名: {result.get('hostname', {}).get('hostname')}")
    print(f"VLAN数量: {len(result.get('vlans', []))}")
    print(f"接口数量: {len(result.get('interfaces', []))}")
    print(f"静态路由数量: {len(result.get('static_routes', []))}")
    print(f"本地用户数量: {len(result.get('local_users', []))}")
    
    # 打印详细解析结果（可选）
    # import json
    # print(json.dumps(result, indent=2, ensure_ascii=False))
    
    return True


if __name__ == "__main__":
    test_h3c_template()