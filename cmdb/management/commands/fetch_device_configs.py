from django.core.management.base import BaseCommand
import requests
from cmdb.models import Device, DeviceConfig

class Command(BaseCommand):
    """
    从网络设备获取配置并保存到数据库的管理命令
    """
    help = 'Fetch device configurations from network devices using FastAPI'

    def handle(self, *args, **options):
        """
        执行命令逻辑
        """
        # 获取所有设备
        devices = Device.objects.all()
        self.stdout.write(f'Found {len(devices)} devices to process')
        
        # FastAPI接口地址
        fastapi_url = 'http://localhost:8001/get-device-config'
        
        for device in devices:
            self.stdout.write(f'Processing device: {device.hostname} ({device.address})')
            
            try:
                # 准备设备信息
                device_info = {
                    'hostname': device.hostname,
                    'address': device.address,
                    'username': device.username,
                    'password': device.password,
                    'device_type': device.device_type
                }
                
                # 调用FastAPI接口获取配置
                response = requests.post(fastapi_url, json=device_info, timeout=60)
                response.raise_for_status()  # 如果请求失败，抛出异常
                
                # 解析响应
                result = response.json()
                
                if result['success']:
                    # 保存配置到数据库
                    DeviceConfig.objects.create(
                        device=device,
                        config=result['config']
                    )
                    self.stdout.write(self.style.SUCCESS(f'Successfully fetched config for {device.hostname}'))
                else:
                    self.stdout.write(self.style.ERROR(f'Failed to fetch config for {device.hostname}: {result.get("detail", "Unknown error")}'))
                    
            except requests.exceptions.RequestException as e:
                self.stdout.write(self.style.ERROR(f'Network error for {device.hostname}: {str(e)}'))
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'Error processing {device.hostname}: {str(e)}'))
        
        self.stdout.write(self.style.SUCCESS('Configuration fetch completed'))
