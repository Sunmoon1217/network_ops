import logging
import asyncio
from rest_framework import viewsets, status
from rest_framework.permissions import AllowAny
from rest_framework.decorators import action
from rest_framework.response import Response
from asyncio import run as asyncio_run
from asgiref.sync import async_to_sync
from django.db import transaction
from django.http import JsonResponse
from cmdb.models import Device, DeviceConfig, Interface, LtmVirtualServer
from .serializers import DeviceSerializer, DeviceConfigSerializer, InterfaceSerializer, VirtualSerializer
from .services import batch_fetch_configs, async_fetch_config

# Import config parser
from .utils import config_parser
from netops.utils import CustomPagination

# Configure logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


def api_index(request):
    """API欢迎页面视图"""
    return JsonResponse({
        "message": "欢迎使用网络运维平台API",
        "status": "success",
        "service": "NetOps API",
        "version": "1.0.0"
    })



class DeviceViewSet(viewsets.ModelViewSet):
    """网络设备的RESTful API视图集
    提供完整的CRUD操作：
    - GET /api/devices/ - 获取所有设备
    - GET /api/devices/{id}/ - 获取单个设备
    - POST /api/devices/ - 创建新设备
    - PUT /api/devices/{id}/ - 更新设备
    - PATCH /api/devices/{id}/ - 部分更新设备
    - DELETE /api/devices/{id}/ - 删除设备
    - POST /api/devices/{id}/fetch-config - 获取设备配置并保存
    """
    queryset = Device.objects.all()  # type: ignore
    serializer_class = DeviceSerializer
    permission_classes = [AllowAny]  # 允许所有访问，生产环境应使用更严格的权限
    
    def list(self, request, *args, **kwargs):
        """自定义列表视图，返回更友好的响应格式"""
        response = super().list(request, *args, **kwargs)
        return response
    
   
    @action(detail=True, methods=['post'], url_path='fetch-config')
    def fetch_config(self, request, pk=None):
        """
        调用FastAPI接口获取单个设备配置并保存到数据库
        
        Args:
            request: HTTP请求对象
            pk: 设备ID
            
        Returns:
            Response: 包含操作结果的HTTP响应
        """
        logger.info(f"开始处理设备{pk}的配置获取请求")
        
        # 获取设备对象
        device = self.get_object() 
        logger.debug(f"获取到设备信息: {device.hostname} ({device.address})")
        # 调用异步函数获取配置
        result = async_to_sync(async_fetch_config)(device)
        
        return Response(result, status=status.HTTP_200_OK)
        
    @action(detail=True, methods=['get'], url_path='config')
    def get_device_config(self, request, pk=None):
        """
        获取设备的最新配置
        
        Args:
            request: HTTP请求对象
            pk: 设备ID
            
        Returns:
            Response: 包含设备最新配置的HTTP响应
        """
        logger.info(f"开始获取设备{pk}的最新配置")
        
        # 获取设备对象
        device = self.get_object()
        logger.debug(f"获取到设备信息: {device.hostname} ({device.address})")
        
        try:
            # 获取设备的最新配置
            logger.debug(f"查询设备{pk}的最新配置")
            latest_config = DeviceConfig.objects.filter(device=device).order_by('-time').first()
            
            if latest_config:
                logger.info(f"成功获取设备{pk}的最新配置，配置ID: {latest_config.id}")
                # 序列化返回结果
                serializer = DeviceConfigSerializer(latest_config)
                logger.debug(f"序列化返回结果: {serializer.data}")
                
                return Response(
                    {
                        "success": True,
                        "message": f"成功获取{device.hostname}的最新配置",
                        "config": serializer.data
                    },
                    status=status.HTTP_200_OK
                )
            else:
                logger.warning(f"设备{pk}没有配置记录")
                return Response(
                    {
                        "success": False,
                        "message": f"设备{device.hostname}没有配置记录",
                        "config": None
                    },
                    status=status.HTTP_200_OK
                )
        except Exception as e:
            logger.error(f"获取设备{pk}最新配置失败: {str(e)}", exc_info=True)
            return Response(
                {
                    "success": False,
                    "message": f"获取配置失败: {str(e)}",
                    "config": None
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    
    @action(detail=False, methods=['post'], url_path='batch-fetch-config')
    def batch_fetch_config(self, request):
        """
        批量调用FastAPI接口获取多个设备配置并保存到数据库
        
        Args:
            request: HTTP请求对象，可包含device_ids参数指定要获取配置的设备ID列表
            
        Returns:
            Response: 包含批量操作结果的HTTP响应
        """
        # 获取请求参数中的设备ID列表
        device_ids = request.data.get("device_ids", [])
        
        # 如果没有指定设备ID，获取所有设备
        if not device_ids:
            devices = Device.objects.all() 
        else:
            devices = Device.objects.filter(id__in=device_ids) 
        
        # 调用异步函数获取配置
        result = async_to_sync(batch_fetch_configs)(devices)
        
        return Response(result, status=status.HTTP_200_OK)

    @action(detail=True, methods=['get'], url_path='history')
    def get_config_history(self, request, pk=None):
        """
        获取设备的历史配置
        
        Args:
            request: HTTP请求对象
            pk: 设备ID
            
        Returns:
            Response: 包含设备最新配置的HTTP响应
        """
        logger.info(f"开始获取设备{pk}的最新配置")
        
        # 获取设备对象
        device = self.get_object()
        logger.debug(f"获取到设备信息: {device.hostname} ({device.address})")
        
        try:
            # 获取设备的最新配置
            logger.debug(f"查询设备{pk}的历史配置列表")
            config_list_objs = DeviceConfig.objects.filter(device=device)
            
            if config_list_objs:
                logger.info(f"成功获取设备{pk}的历史配置列表")
                # 序列化返回结果
                config_list = [(obj.id, obj.time) for obj in config_list_objs]
                return Response(
                    {
                        "success": True,
                        "message": f"成功获取{device.hostname}的最新配置",
                        "config": config_list
                    },
                    status=status.HTTP_200_OK
                )
            else:
                logger.warning(f"设备{pk}没有配置记录")
                return Response(
                    {
                        "success": False,
                        "message": f"设备{device.hostname}没有配置记录",
                        "config": None
                    },
                    status=status.HTTP_200_OK
                )
        except Exception as e:
            logger.error(f"获取设备{pk}最新配置失败: {str(e)}", exc_info=True)
            return Response(
                {
                    "success": False,
                    "message": f"获取配置失败: {str(e)}",
                    "config": None
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
    

class DeviceConfigViewSet(viewsets.ModelViewSet):
    """设备配置的RESTful API视图集
    提供完整的CRUD操作：
    - GET /api/configs/ - 获取所有设备配置
    - GET /api/configs/{id}/ - 获取单个配置
    - GET /api/configs/?device=hostname - 按设备过滤配置
    - POST /api/configs/ - 创建新配置
    - PUT /api/configs/{id}/ - 更新配置
    - PATCH /api/configs/{id}/ - 部分更新配置
    - DELETE /api/configs/{id}/ - 删除配置
    """
    queryset = DeviceConfig.objects.all()  # type: ignore
    serializer_class = DeviceConfigSerializer
    permission_classes = [AllowAny]  # 允许所有访问，生产环境应使用更严格的权限
    filterset_fields = ['device']  # 支持按设备过滤
    
    def get_queryset(self):
        """自定义查询集，支持按设备主机名过滤"""
        queryset = super().get_queryset()
        device = self.request.query_params.get('device')
        if device:
            queryset = queryset.filter(device__pk=device)
        return queryset


class VirtualServerViewSet(viewsets.ModelViewSet):
    queryset = LtmVirtualServer.objects.select_related('config__device').all()  # type: ignore
    serializer_class = VirtualSerializer
    permission_classes = [AllowAny]  # 允许所有访问，生产环境应使用更严格的权限
    filterset_fields = ['config']  # 支持按设备过滤

    pagination_class = CustomPagination

class InterfaceViewSet(viewsets.ModelViewSet):
    queryset = Interface.objects.select_related('config__device').all()
    serializer_class = InterfaceSerializer
    permission_classes = [AllowAny]
    filterset_fields = ['config']

    pagination_class = CustomPagination