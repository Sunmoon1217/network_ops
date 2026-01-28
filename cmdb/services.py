import logging
import httpx
from django.utils import timezone
from datetime import timedelta
from cmdb.models import Device, DeviceConfig
from cmdb.serializers import DeviceConfigSerializer
from cmdb.utils import config_parser
# 异步版本的服务方法，用于支持原生异步调用
import asyncio

logger = logging.getLogger(__name__)


async def async_fetch_config(device):
    """
    异步从FastAPI获取单个设备的配置并保存到数据库
    
    Args:
        device: Device对象，要获取配置的设备
    
    Returns:
        dict: 包含操作结果的字典
    """
    try:
        # 准备设备信息
        device_info = {
            "hostname": device.hostname,
            "address": device.address,
            "username": device.username,
            "password": device.password,
            "device_type": device.device_type
        }
        logger.debug(f"准备调用FastAPI接口，设备信息: {device_info}")
        
        # 调用FastAPI接口
        fastapi_url = "http://localhost:8001/get-device-config"
        logger.info(f"调用FastAPI接口: {fastapi_url}")
        
        # 使用httpx的异步客户端
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.post(fastapi_url, json=device_info)
            logger.debug(f"FastAPI接口响应状态码: {response.status_code}")
            response.raise_for_status()
            
            # 解析响应
            result = response.json()
            logger.debug(f"FastAPI接口响应内容: {result}")
        
        if result.get("success"):
            logger.info(f"成功获取{device.hostname}的配置")
            
            # 获取配置内容
            config_content = result.get("config")
            
            # 检查是否需要保存新配置
            save_new_config = True
            latest_config = None
            
            # 获取设备最新的配置记录 - 使用异步ORM
            try:
                logger.debug(f"查询设备{device.hostname}的最新配置")
                latest_config = await DeviceConfig.objects.filter(device=device).order_by('-time').afirst()
                logger.debug(f"查询完成，是否找到最新配置: {latest_config is not None}")
                
                if latest_config:
                    # 比对配置内容是否一致
                    if latest_config.config_text == config_content:
                        logger.info(f"获取的配置与最新配置一致")
                        
                        # 检查是否在一天内
                        one_day_ago = timezone.now() - timedelta(days=1)
                        if latest_config.time >= one_day_ago:
                            logger.info(f"最新配置在一天内，无需保存重复配置")
                            save_new_config = False
                        else:
                            logger.info(f"最新配置超过一天，需要保存新配置")
                    else:
                        logger.info(f"获取的配置与最新配置不一致，需要保存新配置")
                else:
                    logger.info(f"设备无历史配置，需要保存新配置")
            except Exception as e:
                logger.error(f"查询设备{device.hostname}最新配置时发生错误: {str(e)}", exc_info=True)
                # 出现错误时，默认保存新配置
                save_new_config = True
                latest_config = None
            
            if save_new_config:
                # 保存配置到数据库 - 使用异步ORM
                config_obj = await DeviceConfig.objects.acreate(
                    device=device,
                    config_text=config_content
                )
                logger.info(f"配置已保存到数据库，配置ID: {config_obj.pk}")
                
                # 使用TTP解析配置
                parsed_config = config_parser.parse_config(config_content, device.device_type)
                logger.debug(f"配置解析结果: {parsed_config}")
                
                # 更新设备的解析后配置 - 使用异步ORM
                config_obj.interface_json = parsed_config
                await config_obj.asave()
                logger.info(f"已更新{device.hostname}的解析后配置")
                
                # 序列化返回结果
                serializer = DeviceConfigSerializer(config_obj)
                
                return {
                    "success": True,
                    "message": f"成功获取{device.hostname}的配置并解析",
                    "config": serializer.data,
                    "saved": True
                }
            else:
                # 配置未保存，返回最新配置信息
                serializer = DeviceConfigSerializer(latest_config)
                
                return {
                    "success": True,
                    "message": f"获取的配置与最新配置一致，无需保存",
                    "config": serializer.data,
                    "saved": False
                }
        else:
            error_msg = result.get('detail', '未知错误')
            logger.error(f"获取{device.hostname}配置失败: {error_msg}")
            return {
                "success": False,
                "message": f"获取{device.hostname}配置失败: {error_msg}"
            }
    except httpx.RequestError as e:
        logger.error(f"网络请求失败: {str(e)}", exc_info=True)
        return {
            "success": False,
            "message": f"网络请求失败: {str(e)}"
        }
    except Exception as e:
        logger.error(f"处理失败: {str(e)}", exc_info=True)
        return {
            "success": False,
            "message": f"处理失败: {str(e)}"
        }


async def batch_fetch_configs(devices):
    """
    异步批量从FastAPI获取多个设备的配置并保存到数据库
    
    Args:
        devices: Device对象列表或查询集，要获取配置的设备
    
    Returns:
        dict: 包含批量操作结果的字典
    """
    # 初始化结果统计
    success_count = 0
    failed_count = 0
    results = []
    
    # 将devices转换为列表，避免重复查询
    devices_list = []
    # 检查devices是否是异步查询集
    if hasattr(devices, '__aiter__'):
        # 如果是异步查询集，使用异步迭代
        async for device in devices:
            devices_list.append(device)
    else:
        # 如果是普通列表，使用普通迭代
        devices_list = list(devices)
    
    if not devices_list:
        return {
            "success": True,
            "total_devices": 0,
            "success_count": 0,
            "failed_count": 0,
            "results": []
        }
    
    # 创建任务列表
    tasks = []
    for device in devices_list:
        tasks.append(async_fetch_config(device))
    
    # 并发执行所有任务，收集异常
    task_results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # 处理任务结果
    for i, result in enumerate(task_results):
        device = devices_list[i]
        try:
            if isinstance(result, Exception):
                # 处理异常
                logger.error(f"处理设备{device.hostname}失败: {str(result)}", exc_info=True)
                results.append({
                    "device_id": device.id,
                    "hostname": device.hostname,
                    "success": False,
                    "message": f"处理失败: {str(result)}"
                })
                failed_count += 1
            elif isinstance(result, dict):
                # 记录结果
                device_result = {
                    "device_id": device.id,
                    "hostname": device.hostname,
                    "success": result["success"],
                    "message": result["message"]
                }
                
                # 如果成功，添加配置ID
                if result["success"]:
                    device_result["config_id"] = result["config"]["id"]
                    success_count += 1
                else:
                    failed_count += 1
                
                results.append(device_result)
        except Exception as e:
            # 记录其他失败
            logger.error(f"处理设备{device.hostname}结果失败: {str(e)}", exc_info=True)
            results.append({
                "device_id": device.id,
                "hostname": device.hostname,
                "success": False,
                "message": f"处理失败: {str(e)}"
            })
            failed_count += 1
    
    # 返回批量操作结果
    return {
        "success": True,
        "total_devices": len(devices_list),
        "success_count": success_count,
        "failed_count": failed_count,
        "results": results
    }