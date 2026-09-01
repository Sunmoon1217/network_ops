"""Ansible API views"""
import logging

from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

logger = logging.getLogger(__name__)


@api_view(["GET"])
@permission_classes([AllowAny])
def list_playbooks(request):
    from ops.ansible.api import list_templates
    return Response({"templates": list_templates()})


@api_view(["POST"])
@permission_classes([AllowAny])
def run_playbook(request):
    from ops.ansible.api import run_playbook as _run_playbook
    data = request.data
    playbook = data.get("playbook")
    if not playbook:
        return Response({"error": "playbook required"}, status=status.HTTP_400_BAD_REQUEST)
    result = _run_playbook(playbook_name=playbook, device_ids=data.get("device_ids"),
                           extra_vars=data.get("extra_vars"))
    http_status = status.HTTP_200_OK if result.get("success") else status.HTTP_400_BAD_REQUEST
    return Response(result, status=http_status)
