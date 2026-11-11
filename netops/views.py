from pathlib import Path

from django.http import HttpResponse, JsonResponse

FRONTEND = Path(__file__).resolve().parent.parent / "frontend" / "dist"


def _frontend_html(filename):
    """读取 frontend/dist/ 下的入口 html；两个入口共用 assets/，但页面不能互换。"""
    file_path = FRONTEND / filename
    if file_path.exists() and file_path.is_file():
        return HttpResponse(file_path.read_bytes(), content_type="text/html")
    return JsonResponse({"error": f"{filename} not found"}, status=404)


def vue_index(request):
    """主站入口 index.html（挂载点 #app），也是 SPA 兜底。"""
    return _frontend_html("index.html")


def vue_dashboard(request):
    """大屏入口 dashboard.html（挂载点 #dashboard），必须单独返回。

    两个 Vite 入口共用同一份 main chunk，靠页面里的挂载点决定启动哪个应用；
    若把大屏请求交给 SPA 兜底返回 index.html，页面里没有 #dashboard，大屏就是空白。
    """
    return _frontend_html("dashboard.html")


def favicon(request):
    """返回 favicon.ico"""
    favicon_path = FRONTEND / "favicon.ico"
    if favicon_path.exists():
        return HttpResponse(favicon_path.read_bytes(), content_type="image/x-icon")
    return HttpResponse(status=404)


def serve_frontend_assets(request, path):
    """服务 frontend/dist/assets/ 下的静态资源"""
    file_path = FRONTEND / "assets" / path
    if file_path.exists() and file_path.is_file():
        content_type = (
            "application/javascript" if path.endswith(".js") else "text/css" if path.endswith(".css") else "image/svg+xml" if path.endswith(".svg") else "application/octet-stream"
        )
        return HttpResponse(file_path.read_bytes(), content_type=content_type)
    return JsonResponse({"error": "Not found"}, status=404)
