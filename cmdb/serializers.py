from rest_framework import serializers
from .models import Device, DeviceConfig
import ipaddress

class DeviceSerializer(serializers.ModelSerializer):
    """网络设备序列化器"""
    class Meta:
        model = Device
        fields = ['id', 'hostname', 'address', 'username', 'device_type', 'connect_failed_at']
        read_only_fields = ['id']
        extra_kwargs = {
            'password': {'write_only': True}  # 密码只在写入时使用，不返回
        }

class DeviceConfigSerializer(serializers.ModelSerializer):
    """设备配置序列化器"""
    device = serializers.SlugRelatedField(slug_field='hostname', read_only=True)
    
    class Meta:
        model = DeviceConfig
        fields = ['id', 'device', 'config_text', 'time']
        read_only_fields = ['id', 'time']

class InterfaceSerializer(serializers.Serializer):
    """接口信息序列化器"""
    device_id = serializers.IntegerField(required=True, allow_null=True)
    device_name = serializers.CharField(required=True, max_length=100)
    interface = serializers.CharField(required=True, max_length=100)
    shutdown = serializers.BooleanField(required=False, default=False)
    description = serializers.CharField(required=False, allow_blank=True)
    mode = serializers.CharField(required=False, allow_blank=True)
    access_vlan = serializers.IntegerField(required=False, allow_null=True)
    combo_type = serializers.CharField(required=False, allow_blank=True)
    vrf = serializers.CharField(required=False, allow_blank=True)
    # ip_address = serializers.IPAddressField(required=False, allow_null=True)
    # subnet_mask = serializers.IPAddressField(required=False, allow_null=True)
    if_address = serializers.SerializerMethodField(method_name='get_if_address')
    
    def get_if_address(self, obj):
        """将IP地址和子网掩码转换为接口地址格式"""
        if obj.get('ip_address') and obj.get('subnet_mask'):
            try:
                # 创建IP接口对象
                ip_interface = ipaddress.IPv4Interface(f"{obj['ip_address']}/{obj['subnet_mask']}")
                return str(ip_interface)
            except ValueError:
                return None
        return None
