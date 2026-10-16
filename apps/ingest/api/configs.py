from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from ingest.config_repo import diff_configs, get_config, get_history, list_devices


@api_view(["GET"])
def git_content(request):
    """获取指定 commit 的配置内容"""
    hostname = request.query_params.get("hostname", "")
    commit_hash = request.query_params.get("commit_hash")
    if not hostname:
        return Response({"error": "缺少 hostname"}, status=status.HTTP_400_BAD_REQUEST)

    config_text = get_config(hostname, commit_hash)
    if config_text is None:
        return Response({"error": "配置不存在"}, status=status.HTTP_404_NOT_FOUND)

    return Response(
        {
            "hostname": hostname,
            "commit_hash": commit_hash or "HEAD",
            "config_text": config_text,
        }
    )


@api_view(["GET"])
def git_diff(request):
    """对比两个版本的配置差异"""
    hostname = request.query_params.get("hostname", "")
    old_hash = request.query_params.get("old_hash")
    new_hash = request.query_params.get("new_hash")
    if not hostname:
        return Response({"error": "缺少 hostname"}, status=status.HTTP_400_BAD_REQUEST)

    diff_text = diff_configs(hostname, old_hash, new_hash)
    return Response({"diff": diff_text or ""})


@api_view(["GET"])
def config_history(request):
    """获取设备配置变更历史"""
    hostname = request.query_params.get("hostname", "")
    limit = int(request.query_params.get("limit", "20"))
    if not hostname:
        return Response({"error": "缺少 hostname"}, status=status.HTTP_400_BAD_REQUEST)

    return Response({"history": get_history(hostname, limit)})


@api_view(["GET"])
def config_devices(request):
    """列出有配置的设备"""
    return Response({"devices": list_devices()})
