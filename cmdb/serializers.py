from ctypes import addressof
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
    id = serializers.IntegerField(required=False, allow_null=True)
    device_id = serializers.SerializerMethodField(method_name='get_device_id')
    device_name = serializers.SerializerMethodField(method_name='get_device_name')
    interface = serializers.CharField(required=True, max_length=100)
    shutdown = serializers.BooleanField(required=False, default=False)
    description = serializers.CharField(required=False, allow_blank=True)
    mode = serializers.CharField(required=False, allow_blank=True)
    access_vlan = serializers.IntegerField(required=False, allow_null=True)
    combo_type = serializers.CharField(required=False, allow_blank=True)
    vrf = serializers.CharField(required=False, allow_blank=True)
    if_address = serializers.SerializerMethodField(method_name='get_if_address')
    
    def get_if_address(self, obj):
        """将IP地址和子网掩码转换为接口地址格式"""
        if obj.ip_address and obj.subnet_mask:
            try:
                # 创建IP接口对象
                ip_interface = ipaddress.IPv4Interface(f"{obj.ip_address}/{obj.subnet_mask}")
                return str(ip_interface)
            except ValueError:
                return None
        return None

    def get_device_id(self, obj):
        return getattr(obj.config.device, 'id') 
    
    def get_device_name(self, obj):
        return getattr(obj.config.device, 'hostname') 

class VirtualSerializer(serializers.Serializer):
    id = serializers.IntegerField(required=False, allow_null=True)
    device_id = serializers.SerializerMethodField(method_name='get_device_id')
    device_name = serializers.SerializerMethodField(method_name='get_device_name')
    name = serializers.CharField(required=True, max_length=100)
    pool = serializers.CharField(required=True, max_length=100)
    protocol = serializers.CharField(required=True, max_length=100)
    vs_address = serializers.CharField(required=True, max_length=100)
    vs_port = serializers.CharField(required=True, max_length=100)
    profiles = serializers.ListField(required=True, max_length=100)
    
    def get_device_id(self, obj):
        return getattr(obj.config.device, 'id') 
    
    def get_device_name(self, obj):
        return getattr(obj.config.device, 'hostname') 
