import re
from pathlib import Path

from assets.models import (
    Cabinet,
    DataCenter,
    Device,
    DeviceConfig,
    DeviceConnection,
    DeviceGroup,
    DeviceGroupMember,
    DeviceModel,
    Room,
    SecurityZone,
    Vendor,
)
from ingest.config_repo import save_config

# ---------------------------------------------------------------------------
# Connection config map
# ---------------------------------------------------------------------------

CONNECTION_CONFIG_MAP = {
    ("H3C", "switch"): {"connection_type": "napalm", "driver": "h3c_comware"},
    ("H3C", "router"): {"connection_type": "napalm", "driver": "h3c_comware"},
    ("锐捷", "switch"): {"connection_type": "netmiko", "driver": "ruijie_os"},
    ("思科", "firewall"): {"connection_type": "napalm", "driver": "asa"},
    ("山石", "firewall"): {"connection_type": "netmiko", "driver": "hillstone_stoneos"},
    ("F5", "slb"): {"connection_type": "netmiko", "driver": "f5_ltm"},
    ("F5", "gslb"): {"connection_type": "netmiko", "driver": "f5_gtm"},
    ("A10", "slb"): {"connection_type": "netmiko", "driver": "a10"},
}


def _get_connection_config(vendor_name, device_type):
    return CONNECTION_CONFIG_MAP.get(
        (vendor_name, device_type),
        {"connection_type": "netmiko", "driver": ""},
    )


def _import_datacenters(ws):
    created, updated, errors = 0, 0, []
    for row_idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        if not row[0]:
            continue
        name = str(row[0]).strip()
        defaults = {
            "address": str(row[1] or "").strip(),
            "contact": str(row[2] or "").strip(),
            "phone": str(row[3] or "").strip(),
            "remark": str(row[4] or "").strip(),
        }
        try:
            _, is_created = DataCenter.objects.update_or_create(name=name, defaults=defaults)
            created += 1 if is_created else 0
            updated += 0 if is_created else 1
        except Exception as e:
            errors.append(f"行 {row_idx}: {e}")
    return {"created": created, "updated": updated, "errors": errors}


def _import_rooms(ws):
    created, updated, errors = 0, 0, []
    for row_idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        if not row[0] or not row[1]:
            continue
        try:
            dc = DataCenter.objects.get(name=str(row[0]).strip())
            _, is_created = Room.objects.update_or_create(
                datacenter=dc,
                name=str(row[1]).strip(),
                defaults={"contact": str(row[2] or "").strip(), "remark": str(row[3] or "").strip()},
            )
            created += 1 if is_created else 0
            updated += 0 if is_created else 1
        except DataCenter.DoesNotExist:
            errors.append(f"行 {row_idx}: 数据中心 '{row[0]}' 不存在")
        except Exception as e:
            errors.append(f"行 {row_idx}: {e}")
    return {"created": created, "updated": updated, "errors": errors}


def _import_cabinets(ws):
    created, updated, errors = 0, 0, []
    for row_idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        if not row[0] or not row[1] or not row[2]:
            continue
        try:
            dc = DataCenter.objects.get(name=str(row[0]).strip())
            room = Room.objects.get(datacenter=dc, name=str(row[1]).strip())
            _, is_created = Cabinet.objects.update_or_create(
                room=room,
                name=str(row[2]).strip(),
                defaults={
                    "row": str(row[3] or "").strip(),
                    "total_u": int(row[4] or 42),
                    "power_capacity": float(row[5]) if row[5] else None,
                    "status": str(row[6] or "active").strip(),
                    "remark": str(row[7] or "").strip(),
                },
            )
            created += 1 if is_created else 0
            updated += 0 if is_created else 1
        except DataCenter.DoesNotExist:
            errors.append(f"行 {row_idx}: 数据中心 '{row[0]}' 不存在")
        except Room.DoesNotExist:
            errors.append(f"行 {row_idx}: 机房 '{row[1]}' 不存在")
        except Exception as e:
            errors.append(f"行 {row_idx}: {e}")
    return {"created": created, "updated": updated, "errors": errors}


def _import_security_zones(ws):
    created, updated, errors = 0, 0, []
    for row_idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        if not row[0]:
            continue
        try:
            _, is_created = SecurityZone.objects.update_or_create(
                name=str(row[0]).strip(),
                defaults={"color": str(row[1] or "#3b82f6").strip(), "description": str(row[2] or "").strip()},
            )
            created += 1 if is_created else 0
            updated += 0 if is_created else 1
        except Exception as e:
            errors.append(f"行 {row_idx}: {e}")
    return {"created": created, "updated": updated, "errors": errors}


def _import_devices(ws):
    created, updated, errors = 0, 0, []
    for row_idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        if not row[0]:
            continue
        hostname = str(row[0]).strip()
        device_type = str(row[2] or "switch").strip()
        ip_address = str(row[1] or "").strip()

        vendor = None
        device_model = None
        vendor_name = str(row[3] or "").strip()
        model_name = str(row[4] or "").strip()
        if vendor_name:
            vendor, _ = Vendor.objects.get_or_create(name=vendor_name)
        if model_name and vendor:
            device_model, _ = DeviceModel.objects.get_or_create(name=model_name, vendor=vendor)

        dc = None
        cabinet = None
        dc_name = str(row[5] or "").strip()
        room_name = str(row[6] or "").strip()
        cab_name = str(row[7] or "").strip()
        if dc_name and room_name and cab_name:
            try:
                dc = DataCenter.objects.get(name=dc_name)
                room = Room.objects.get(datacenter=dc, name=room_name)
                cabinet = Cabinet.objects.get(room=room, name=cab_name)
            except (DataCenter.DoesNotExist, Room.DoesNotExist, Cabinet.DoesNotExist):
                errors.append(f"行 {row_idx}: 机柜路径 '{dc_name}/{room_name}/{cab_name}' 不存在")

        security_zone = None
        zone_name = str(row[8] or "").strip()
        if zone_name:
            security_zone = SecurityZone.objects.filter(name=zone_name).first()

        device_defaults = {
            "device_type": device_type,
            "ip_address": ip_address,
            "device_model": device_model,
            "idc": dc,
            "cabinet": cabinet,
            "security_zone": security_zone,
            "u_position": int(row[9]) if row[9] else None,
            "height": int(row[10] or 1),
            "remark": str(row[11] or "").strip(),
        }

        try:
            device, is_created = Device.objects.update_or_create(hostname=hostname, defaults=device_defaults)
            created += 1 if is_created else 0
            updated += 0 if is_created else 1
        except Exception as e:
            errors.append(f"行 {row_idx}: {e}")
            continue

        account_type = str(row[12] or "").strip()
        username = str(row[13] or "").strip()
        password = str(row[14] or "").strip()
        if username and password:
            conn_config = _get_connection_config(vendor_name, device_type)
            conn_defaults = {
                "connection_type": conn_config["connection_type"],
                "driver": conn_config["driver"],
                "account_type": account_type or "admin",
                "username": username,
                "password": password,
                "enable_password": str(row[15] or "").strip(),
                "port": int(row[16] or 22) if row[16] else 22,
                "timeout": int(row[17] or 30) if row[17] else 30,
            }
            try:
                DeviceConnection.objects.update_or_create(
                    device=device, account_type=account_type or "admin", defaults=conn_defaults
                )
            except Exception as e:
                errors.append(f"行 {row_idx} 连接: {e}")

    return {"created": created, "updated": updated, "errors": errors}


def _choice_key(raw, choices, default=None):
    """把表格里写的枚举值（如组类型）归一成模型的 key。

    key（``stack``）与显示名（``堆叠``）都接受，空值取 ``default``，识别不了返回 ``None`` 交给调用方报错。
    """
    text = str(raw or "").strip()
    if not text:
        return default
    for key, label in choices:
        if text in (key, label):
            return key
    return None


def _cell(row, idx):
    """按位置取单元格文本并 strip；行尾缺列 / 空单元格一律给空串（设备组 Sheet 里空值是常态）。"""
    if idx >= len(row) or row[idx] is None:
        return ""
    return str(row[idx]).strip()


def _split_device_names(text):
    """设备名单元格按中英文逗号 / 顿号 / 空白切开——一行填多台设备用。"""
    return [name for name in re.split(r"[,，、\s]+", text) if name]


def _group_name(group_type, names):
    """组名**不由表格填**：非集群 = 主设备（第一台）hostname；集群 = 所有设备名的最长公共前缀。

    例：``cs-1`` / ``cs-2`` 的交集是 ``cs-``（逐字符取，不按分隔符截）。只有一台设备、
    或者毫无公共前缀时回退第一台 hostname，保证组名永远非空。
    """
    if group_type != "cluster":
        return names[0]
    prefix = names[0]
    for hostname in names[1:]:
        while prefix and not hostname.startswith(prefix):
            prefix = prefix[:-1]
    return prefix or names[0]


def _device_roles(group_type, count):
    """角色按位置推，不填表：非集群第一台 = 主、第二台 = 备，其余 = 成员；集群内全部 = 成员。"""
    if group_type == "cluster":
        return ["member"] * count
    roles = ["member"] * count
    roles[0] = "master"
    if count > 1:
        roles[1] = "backup"
    return roles


def _import_device_groups(ws):
    """设备组 Sheet：组类型 | 设备名(多个用逗号分隔) | 描述，**一行 = 一个设备组**。

    组名与角色都不用填，由导入推出来（见 ``_group_name`` / ``_device_roles``）——设备组除集群
    外都是 1–2 台成组，逐格填组名 / 角色纯属重复劳动。三条硬规矩：

    - 行里的设备必须都已存在，缺任一台**整行报错、不建半截组**（设备 Sheet 排在前面）；
    - 行是该组的**完整快照**：不在这一行里的既有成员会被摘掉，改了组成以本次为准；
    - 计数一行 = 一个设备组（created = 新建组，updated = 已有组被再次导入）。
    """
    created, updated, errors = 0, 0, []
    for row_idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        cells = [_cell(row, i) for i in range(3)]
        if not any(cells):
            continue  # 整行空白

        group_type = _choice_key(cells[0], DeviceGroup.GROUP_TYPE_CHOICES, default="single")
        if group_type is None:
            keys = "/".join(k for k, _ in DeviceGroup.GROUP_TYPE_CHOICES)
            errors.append(f"行 {row_idx}: 未知组类型 '{cells[0]}'，可选 {keys}")
            continue

        names = _split_device_names(cells[1])
        if not names:
            errors.append(f"行 {row_idx}: 缺少设备名")
            continue

        found = {device.hostname: device for device in Device.objects.filter(hostname__in=names)}
        missing = [hostname for hostname in names if hostname not in found]
        if missing:
            errors.append(f"行 {row_idx}: 设备 '{', '.join(missing)}' 不存在，请先导入设备")
            continue
        devices = [found[hostname] for hostname in names]

        name = _group_name(group_type, names)
        roles = _device_roles(group_type, len(devices))
        try:
            group, group_created = DeviceGroup.objects.update_or_create(
                name=name,
                defaults={"group_type": group_type, "description": cells[2]},
            )
            for device, role in zip(devices, roles):
                DeviceGroupMember.objects.update_or_create(group=group, device=device, defaults={"device_role": role})
            group.members.exclude(device__in=devices).delete()
        except Exception as e:
            errors.append(f"行 {row_idx}: {e}")
            continue

        created += 1 if group_created else 0
        updated += 0 if group_created else 1

    return {"created": created, "updated": updated, "errors": errors}


def _import_configs(ws):
    from ingest.workflow import submit_config_job

    created, skipped, errors = 0, 0, []

    for row_idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        if not row[0]:
            continue

        hostname = str(row[0]).strip()
        filename = row[1] and str(row[1]).strip() or hostname + ".txt"
        config_dir = str(row[2] or "").strip()

        try:
            device = Device.objects.get(hostname=hostname)
        except Device.DoesNotExist:
            errors.append(f"行 {row_idx}: 设备 '{hostname}' 不存在，请先导入设备")
            continue

        from ingest.config_repo import CONFIG_REPO_PATH

        if config_dir:
            config_path = Path(config_dir) / filename
        else:
            config_path = CONFIG_REPO_PATH / hostname / filename

        if not config_path.exists():
            errors.append(f"行 {row_idx}: 配置文件不存在: {config_path}")
            continue

        try:
            config_text = config_path.read_text(encoding="utf-8")
        except Exception as e:
            errors.append(f"行 {row_idx}: 读取失败: {e}")
            continue

        if not config_text.strip():
            errors.append(f"行 {row_idx}: 配置文件为空")
            continue

        try:
            commit_hash = save_config(hostname, config_text, message=f"import: {hostname} config")
        except Exception as e:
            errors.append(f"行 {row_idx}: 保存到 Git 失败: {e}")
            continue

        # 用「先查后建」而不是 update_or_create：这条记录代表"某设备在某 commit 上的
        # 配置快照"，重复导入同一版本时不该动它。用 update_or_create 会把已经解析好的
        # config_json 清空，而 created=False 又不会触发重新解析，解析结果就永久丢了。
        #
        # 批量导入**不在请求里跑同步流水线**：每台设备解析+入库要 0.2–12 s，几十行就是
        # 几十秒串行。这里挂 `_defer_pipeline` 让 signals 跳过同步处理，再投递 celery 链
        # （解析 → 存储）；单个上传仍走同步路径，失败能直接在响应里报错。
        if DeviceConfig.objects.filter(device=device, git_commit_hash=commit_hash).exists():
            skipped += 1
            continue

        config = DeviceConfig(device=device, git_commit_hash=commit_hash, config_json={})
        config._defer_pipeline = True  # type: ignore[attr-defined]
        config.save()
        try:
            submit_config_job(config.pk)
        except Exception as e:
            errors.append(f"行 {row_idx}: 配置已保存，但投递解析任务失败: {e}")
        created += 1

    return {"created": created, "skipped": skipped, "errors": errors}


# 导入支持的 Sheet：**清单 / 顺序 / 列头 / 导入函数的唯一来源**。
# `import_excel` 按它逐个分发，模板下载接口按它生成表头——两边读同一份表，加删 Sheet 只改这里。
# 列头必须与各 `_import_*` 里按下标取的列严格对齐（改列头 = 改导入函数，反之亦然）。
IMPORT_SHEETS = {
    "数据中心": {
        "headers": ["名称", "地址", "联系人", "电话", "备注"],
        "importer": _import_datacenters,
    },
    "机房": {
        "headers": ["数据中心", "机房名称", "联系人", "备注"],
        "importer": _import_rooms,
    },
    "机柜": {
        "headers": ["数据中心", "机房", "机柜编号", "排", "U数", "功率", "状态", "备注"],
        "importer": _import_cabinets,
    },
    "安全区": {
        "headers": ["名称", "颜色", "描述"],
        "importer": _import_security_zones,
    },
    "设备": {
        "headers": [
            "主机名",
            "IP",
            "类型",
            "厂商",
            "型号",
            "数据中心",
            "机房",
            "机柜",
            "安全区",
            "U位",
            "高度",
            "备注",
            "账号类型",
            "用户名",
            "密码",
            "Enable密码",
            "端口",
            "超时",
        ],
        "importer": _import_devices,
    },
    # 排在「设备」之后：行里的设备必须已存在。组名 / 角色不填表，由导入推（见 _import_device_groups）
    "设备组": {
        "headers": ["组类型", "设备名(多个用逗号分隔)", "描述"],
        "importer": _import_device_groups,
    },
    "配置文件": {
        "headers": ["主机名", "文件名(可选)", "配置目录(可选)"],
        "importer": _import_configs,
    },
}
