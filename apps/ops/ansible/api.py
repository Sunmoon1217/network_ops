"""Ansible 执行模块"""
import logging
import tempfile
from pathlib import Path

from ansible import context
from ansible.executor.playbook_executor import PlaybookExecutor
from ansible.inventory.manager import InventoryManager
from ansible.module_utils.common.collections import ImmutableDict
from ansible.parsing.dataloader import DataLoader
from ansible.vars.manager import VariableManager

logger = logging.getLogger(__name__)


def _init_ansible_context():
    context._init_global_context(ImmutableDict(
        connection="smart", module_path=None, forks=10,
        become=None, become_method=None, become_user=None, check=False, diff=False,
    ))


def _build_inventory_string(device_ids=None):
    from assets.models import Device, DeviceConnection

    devices = Device.objects.filter(pk__in=device_ids) if device_ids else Device.objects.all()
    lines = ["[all]"]
    for d in devices:
        try:
            conn = DeviceConnection.objects.filter(device=d).first()
            if not conn:
                continue
            address = conn.get_address()
            if not address:
                continue
            line = f"{d.hostname} ansible_host={address}"
            if conn.port != 22:
                line += f" ansible_port={conn.port}"
            if conn.username:
                line += f" ansible_user={conn.username}"
            if conn.password:
                line += f" ansible_password={conn.password}"
            lines.append(line)
        except Exception:
            continue
    return "\n".join(lines)


def run_playbook(playbook_name: str, device_ids=None, extra_vars=None):
    from ops.models import AnsiblePlaybook, AnsibleTaskRecord

    try:
        playbook = AnsiblePlaybook.objects.get(name=playbook_name, is_active=True)
    except AnsiblePlaybook.DoesNotExist:
        return {"success": False, "error": f"Playbook '{playbook_name}' 不存在"}

    task_record = AnsibleTaskRecord.objects.create(
        playbook=playbook, task_type="playbook", status="running", target_devices=device_ids,
    )

    try:
        playbook_content = playbook.render()
        playbook_file = tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False, encoding="utf-8")
        playbook_file.write(playbook_content)
        playbook_file.close()

        _init_ansible_context()
        loader = DataLoader()
        inventory = InventoryManager(loader=loader, sources=[])
        variable_manager = VariableManager(loader=loader, inventory=inventory)

        inventory_content = _build_inventory_string(device_ids)
        inventory_file = tempfile.NamedTemporaryFile(mode="w", suffix=".ini", delete=False, encoding="utf-8")
        inventory_file.write(inventory_content)
        inventory_file.close()
        inventory.add_host(Path(inventory_file.name))

        pb = PlaybookExecutor(
            playbooks=[str(playbook_file)], inventory=inventory,
            variable_manager=variable_manager, loader=loader, passwords={},
        )
        result = pb.run()

        task_record.status = "success" if result == 0 else "failed"
        task_record.result = {"return_code": result}
        task_record.save()
        return {"success": result == 0, "return_code": result, "task_id": task_record.pk}
    except Exception as e:
        task_record.status = "failed"
        task_record.error_message = str(e)
        task_record.save()
        return {"success": False, "error": str(e)}


def list_templates():
    from ops.ansible.templates import PLAYBOOK_TEMPLATES
    return [{"name": k, "description": v["description"]} for k, v in PLAYBOOK_TEMPLATES.items()]
