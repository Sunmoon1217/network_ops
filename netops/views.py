from django.http import JsonResponse, HttpResponse
from django.conf import settings
from pathlib import Path
import sqlite3


def index(request):
    """API欢迎页面视图"""
    return JsonResponse({
        "message": "欢迎使用网络运维平台API",
        "status": "success",
        "service": "NetOps API",
        "version": "1.0.0"
    })


def vue_index(request):
    """返回Vue构建的index.html文件"""
    index_path = Path(settings.BASE_DIR) / 'templates' / 'index.html'
    if index_path.exists():
        with open(index_path, 'rb') as f:
            return HttpResponse(f.read(), content_type='text/html')
    return JsonResponse({"error": "Index.html not found"}, status=404)



def favicon(request):
    """返回favicon.ico文件"""
    favicon_path = Path(settings.BASE_DIR) / 'templates' / 'dist' / 'favicon.ico'
    if favicon_path.exists():
        with open(favicon_path, 'rb') as f:
            return HttpResponse(f.read(), content_type='image/x-icon')
    return HttpResponse(status=404)


def check_wal_mode(request):
    """
    检查SQLite数据库的WAL模式是否开启
    
    Args:
        request: HTTP请求对象
        
    Returns:
        JsonResponse: 包含WAL模式状态的响应
    """
    try:
        # 获取数据库文件路径
        db_path = Path(settings.BASE_DIR) / 'db.sqlite3'
        
        # 连接数据库并执行查询
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("PRAGMA journal_mode;")
        result = cursor.fetchone()
        conn.close()
        
        # 解析结果
        journal_mode = result[0] if result else "unknown"
        is_wal_enabled = journal_mode.lower() == "wal"
        
        # 返回响应
        return JsonResponse({
            "success": True,
            "journal_mode": journal_mode,
            "wal_enabled": is_wal_enabled,
            "message": f"数据库日志模式: {journal_mode}"
        })
    except Exception as e:
        return JsonResponse(
            {
                "success": False,
                "error": str(e),
                "message": "检查WAL模式失败"
            },
            status=500
        )
