"""Ansible API 视图"""
import logging

from django.http import JsonResponse
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny

logger = logging.getLogger(__name__)


@api_view(["GET"])
@permission_classes([AllowAny])
def list_playbooks(request):
    from .api import list_templates
    return JsonResponse({"templates": list_templates()})


@api_view(["POST"])
@permission_classes([AllowAny])
def run_playbook(request):
    from .api import run_playbook as _run_playbook
    data = request.data
    playbook = data.get("playbook")
    if not playbook:
        return JsonResponse({"error": "请指定 playbook"}, status=400)
    result = _run_playbook(playbook_name=playbook, device_ids=data.get("device_ids"),
                           extra_vars=data.get("extra_vars"))
    return JsonResponse(result)


@api_view(["GET"])
@permission_classes([AllowAny])
def generate_inventory(request):
    from .api import _build_inventory_string
    device_ids_str = request.GET.get("device_ids", "")
    device_ids = [int(x) for x in device_ids_str.split(",") if x.strip()] if device_ids_str else None
    return JsonResponse({"inventory": _build_inventory_string(device_ids)})
