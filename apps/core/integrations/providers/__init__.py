"""各外部系统的 provider 实现（core 内的「实现目录」，注册表本身不知道这里有什么）。

放这里的理由：client 实现要 import 三方 SDK、要管 session / 事件循环，属于「会写代码的
适配层」；core 的 ``registry`` / ``provider`` 只定义协议与查表。业务域在 ``ready()`` 里
把这里的实例注册进去，core 其余部分仍然不认识任何具体系统。

**迁移前住在各域**：Zabbix 在 ``apps/ingest/collectors/zabbix/``（那时 ``close_zapi()``
全项目没有调用点，session 泄到进程退出）。搬家后由 ``core.integrations.release_all()``
在 ASGI / Celery 收尾统一释放。
"""
