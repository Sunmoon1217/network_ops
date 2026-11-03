"""设备库 MCP 工具（assets 域）。

注册模式与 Django admin 同构：``netops.mcp_server`` 持有根 server 单例（根注册表），
本模块顶层 ``@mcp.tool()`` 直接装饰（**import 即注册**，没有 register 包装函数）。
组合方（netops/asgi.py 或测试）``import assets.mcp.tools`` 即完成接入；
``netops.mcp_server`` 严禁反向 import 本模块（防循环，硬规矩）。

只做「参数校验 → 查库 → 序列化」三件事：字段口径复用 assets.api.serializers 的
DeviceSerializer（与 REST API 同一套字段规则），不在工具层重复业务逻辑。

返回注解必须是 TypedDict：SDK 按它生成输出 schema、并用 pydantic 校验返回值
（裸 dict 注解没有结构化输出，客户端只拿得到一段 JSON 文本；缺字段/类型不符
会直接把工具打成错误）。DeviceInfo 与 DeviceSerializer 的字段一一对应——
序列化器加/删字段要同步改这里，tests/mcp/test_device_tools.py 会跑出校验错误。
"""

from typing import TypedDict, cast

from django.db.models import Q
from mcp.server.mcpserver.exceptions import ToolError

from assets.api.serializers import DeviceSerializer
from assets.models import Device, DeviceGroup
from netops.mcp_server import mcp, with_db_lifecycle


class DeviceInfo(TypedDict):
    """DeviceSerializer 输出的全部键（与 REST API 字段口径一致）。"""

    id: int
    hostname: str
    device_type: str
    device_type_display: str
    device_model: int | None
    device_model_name: str | None
    idc: int | None
    idc_name: str | None
    cabinet: int | None
    cabinet_name: str | None
    room_name: str | None
    security_zone: int | None
    security_zone_name: str | None
    u_position: int | None
    height: int
    ip_address: str
    remark: str
    created_at: str


class DeviceGroupRef(TypedDict):
    """设备所在组（get_device 用）。"""

    group_name: str
    group_type: str
    group_type_display: str
    device_role: str


class SearchDevicesResult(TypedDict):
    total: int
    page: int
    page_size: int
    devices: list[DeviceInfo]


class GetDeviceResult(TypedDict):
    device: DeviceInfo
    groups: list[DeviceGroupRef]


class DeviceGroupMemberInfo(TypedDict):
    hostname: str
    device_role: str


class DeviceGroupInfo(TypedDict):
    name: str
    group_type: str
    group_type_display: str
    description: str
    members: list[DeviceGroupMemberInfo]


class ListDeviceGroupsResult(TypedDict):
    total: int
    page: int
    page_size: int
    groups: list[DeviceGroupInfo]


DEVICE_TYPES = tuple(key for key, _ in Device.DEVICE_TYPE_CHOICES)
MAX_PAGE_SIZE = 100


def _page_slice(page: int, page_size: int) -> tuple[int, int]:
    """分页参数校验，返回 queryset 切片的 [start, stop)。"""
    if page < 1:
        raise ToolError("page 从 1 开始计数")
    if not 1 <= page_size <= MAX_PAGE_SIZE:
        raise ToolError(f"page_size 取 1~{MAX_PAGE_SIZE}")
    start = (page - 1) * page_size
    return start, start + page_size


@mcp.tool()
@with_db_lifecycle
def search_devices(keyword: str = "", device_type: str = "", vendor: str = "", group: str = "", page: int = 1, page_size: int = 20) -> SearchDevicesResult:
    """搜索设备库，返回分页的设备摘要。

    参数：
    - keyword：模糊匹配 主机名 / 管理IP / 备注，留空不过滤
    - device_type：设备类型精确匹配，可选值 firewall/switch/slb/gslb/router/server/dns/dwdm/internalac/wirelessac
    - vendor：厂商名模糊匹配（如 huawei、H3C）
    - group：设备组名模糊匹配
    - page / page_size：分页，page_size 最大 100

    返回：{total, page, page_size, devices:[设备档案]}，按主机名排序。
    """
    start, stop = _page_slice(page, page_size)
    if device_type and device_type not in DEVICE_TYPES:
        raise ToolError(f"device_type 无效：{device_type}；可选值 {'/'.join(DEVICE_TYPES)}")
    qs = Device.objects.select_related("device_model__vendor", "idc", "cabinet__room", "security_zone")
    if keyword:
        qs = qs.filter(Q(hostname__icontains=keyword) | Q(ip_address__icontains=keyword) | Q(remark__icontains=keyword))
    if device_type:
        qs = qs.filter(device_type=device_type)
    if vendor:
        qs = qs.filter(device_model__vendor__name__icontains=vendor)
    if group:
        qs = qs.filter(group_memberships__group__name__icontains=group).distinct()
    total = qs.count()
    # 序列化器输出是 ReturnDict，字段口径由 tests/mcp/test_device_tools.py 与 DeviceInfo 对账
    devices = [cast(DeviceInfo, DeviceSerializer(device).data) for device in qs[start:stop]]
    return {"total": total, "page": page, "page_size": page_size, "devices": devices}


@mcp.tool()
@with_db_lifecycle
def get_device(hostname: str) -> GetDeviceResult:
    """按主机名查单台设备的完整档案，含所属设备组与在组内角色。

    参数：hostname：设备主机名（大小写不敏感）。

    返回：{device:设备档案, groups:[{group_name, group_type, group_type_display, device_role}]}；
    设备不存在时返回错误。
    """
    device = Device.objects.select_related("device_model__vendor", "idc", "cabinet__room", "security_zone").filter(hostname__iexact=hostname).first()
    if device is None:
        raise ToolError(f"设备不存在：{hostname}（可先用 search_devices 按关键字搜索）")
    groups = [
        DeviceGroupRef(
            group_name=membership.group.name,
            group_type=membership.group.group_type,
            group_type_display=membership.group.get_group_type_display(),
            device_role=membership.device_role,
        )
        for membership in device.group_memberships.select_related("group")
    ]
    return {"device": cast(DeviceInfo, DeviceSerializer(device).data), "groups": groups}


@mcp.tool()
@with_db_lifecycle
def list_device_groups(keyword: str = "", page: int = 1, page_size: int = 20) -> ListDeviceGroupsResult:
    """列出设备组及成员（组类型、成员主机名、成员角色）。

    参数：
    - keyword：模糊匹配组名或描述，留空不过滤
    - page / page_size：分页，page_size 最大 100

    返回：{total, page, page_size, groups:[{name, group_type, group_type_display,
    description, members:[{hostname, device_role}]}]}，按组名排序。
    """
    start, stop = _page_slice(page, page_size)
    qs = DeviceGroup.objects.prefetch_related("members__device")
    if keyword:
        qs = qs.filter(Q(name__icontains=keyword) | Q(description__icontains=keyword))
    total = qs.count()
    groups = [
        DeviceGroupInfo(
            name=group.name,
            group_type=group.group_type,
            group_type_display=group.get_group_type_display(),
            description=group.description,
            members=[DeviceGroupMemberInfo(hostname=member.device.hostname, device_role=member.device_role) for member in group.members.all()],
        )
        for group in qs[start:stop]
    ]
    return {"total": total, "page": page, "page_size": page_size, "groups": groups}
