"""配置属主解析。

堆叠（stack）组内多台物理设备共用一份配置文件：备机不持有自己的 DeviceConfig，
解析与查询都归属该组的主设备。

    DeviceGroup(stack)
      ├── master: 主机 —— 持有配置文件
      └── backup: 备机 —— 无配置，查询时回退到主机

注意此处只解决"配置归属"，不改动设备自身的数据：
备机的接口/路由等模型数据本就不存在（堆叠在逻辑上是同一台设备）。
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from assets.models import Device


def resolve_config_owner(device: "Device"):
    """返回该设备的配置属主。

    - 设备属于 stack 组且不是主机 → 返回该组主设备
    - 其余情况（无组、非 stack 组、本身就是主机、组内无主设备）→ 返回设备自身

    同一设备同时属于多个 stack 组时，取 group_id 最小的那个组，保证结果确定。
    不递归求解（避免主设备又指向他人造成环）。
    """
    from assets.models import DeviceGroupMember

    membership = (
        DeviceGroupMember.objects.filter(device=device, group__group_type="stack")
        .select_related("group")
        .order_by("group_id")
        .first()
    )
    if not membership or membership.device_role == "master":
        return device

    master = (
        DeviceGroupMember.objects.filter(group=membership.group, device_role="master")
        .select_related("device")
        .order_by("pk")
        .first()
    )
    if not master or master.device == device:
        return device
    return master.device
