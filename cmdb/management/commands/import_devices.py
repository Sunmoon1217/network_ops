import csv
from django.core.management.base import BaseCommand
from cmdb.models import Device

class Command(BaseCommand):
    """导入设备列表从CSV文件到数据库"""
    help = '导入设备列表从CSV文件到数据库'
    
    def add_arguments(self, parser):
        parser.add_argument('csv_file', type=str, nargs='?', default='device_list.csv', 
                          help='CSV文件路径，默认为当前目录下的device_list.csv')
    
    def handle(self, *args, **options):
        csv_file = options['csv_file']
        
        try:
            with open(csv_file, 'r', encoding='utf-8') as file:
                reader = csv.reader(file)
                imported_count = 0
                skipped_count = 0
                
                for row in reader:
                    if len(row) != 5:
                        self.stdout.write(self.style.WARNING(f'跳过无效行: {row}'))
                        skipped_count += 1
                        continue
                        
                    hostname, address, device_type, username, password = row
                    
                    # 处理IP地址，去掉.xsh后缀
                    address = address.replace('.xsh', '')
                    
                    # 检查设备是否已存在
                    if Device.objects.filter(hostname=hostname).exists():
                        self.stdout.write(self.style.WARNING(f'设备 {hostname} 已存在，跳过'))
                        skipped_count += 1
                        continue
                    
                    # 创建设备对象
                    device = Device(
                        hostname=hostname,
                        address=address,
                        username=username,
                        password=password,
                        device_type=device_type
                    )
                    device.save()
                    
                    imported_count += 1
                    self.stdout.write(self.style.SUCCESS(f'成功导入设备: {hostname}'))
                
                self.stdout.write(self.style.SUCCESS(f'\n导入完成！'))
                self.stdout.write(self.style.SUCCESS(f'成功导入: {imported_count} 个设备'))
                self.stdout.write(self.style.WARNING(f'跳过: {skipped_count} 个设备'))
                
        except FileNotFoundError:
            self.stdout.write(self.style.ERROR(f'文件 {csv_file} 不存在'))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'导入失败: {str(e)}'))
