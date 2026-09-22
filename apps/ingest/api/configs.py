from django.http import JsonResponse
from django.views.decorators.http import require_GET

from ingest.config_repo import diff_configs, get_config, get_history, list_devices


@require_GET
def git_content(request):
    """获取指定 commit 的配置内容"""
    hostname = request.GET.get("hostname", "")
    commit_hash = request.GET.get("commit_hash")
    if not hostname:
        return JsonResponse({"error": "缺少 hostname"}, status=400)

    config_text = get_config(hostname, commit_hash)
    if config_text is None:
        return JsonResponse({"error": "配置不存在"}, status=404)

    return JsonResponse(
        {
            "hostname": hostname,
            "commit_hash": commit_hash or "HEAD",
            "config_text": config_text,
        }
    )


@require_GET
def git_diff(request):
    """对比两个版本的配置差异"""
    hostname = request.GET.get("hostname", "")
    old_hash = request.GET.get("old_hash")
    new_hash = request.GET.get("new_hash")
    if not hostname:
        return JsonResponse({"error": "缺少 hostname"}, status=400)

    diff_text = diff_configs(hostname, old_hash, new_hash)
    return JsonResponse({"diff": diff_text or ""})


@require_GET
def config_history(request):
    """获取设备配置变更历史"""
    hostname = request.GET.get("hostname", "")
    limit = int(request.GET.get("limit", "20"))
    if not hostname:
        return JsonResponse({"error": "缺少 hostname"}, status=400)

    return JsonResponse({"history": get_history(hostname, limit)})


@require_GET
def config_devices(request):
    """列出有配置的设备"""
    return JsonResponse({"devices": list_devices()})
