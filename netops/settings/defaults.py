"""按 ``DJANGO_ENV`` 区分的「代码默认值」。

只放**确实随环境不同**的策略项：现场值（域名、地址、路径、凭据）仍然只由 env 文件提供，
不进本文件。读取顺序统一在 ``base.py``：

    env（含 *_FILE）> 本文件的默认值 > 代码兜底

硬覆盖（不论 env 怎么写都生效）不在这里，留在 ``prod.py``（``DEBUG=False``）与各环境
守卫里——那是安全/合规项，不是可调旋钮。
"""

from typing import TypedDict


class EnvDefaults(TypedDict):
    """一套环境默认值；新增项时同步 dev / container / prod 三份。"""

    DJANGO_API_DOCS_REQUIRE_LOGIN: bool
    MCP_ENABLED: bool


ENV_DEFAULTS: dict[str, EnvDefaults] = {
    # 开发与容器：内网默认放开（schema 只暴露接口元数据；MCP 出口匿名）
    "dev": {
        "DJANGO_API_DOCS_REQUIRE_LOGIN": False,
        "MCP_ENABLED": True,
    },
    "container": {
        "DJANGO_API_DOCS_REQUIRE_LOGIN": False,
        "MCP_ENABLED": True,
    },
    # 生产默认收紧：文档要登录，MCP 出口默认摘掉；需要时显式设 MCP_ENABLED=1 打开
    "prod": {
        "DJANGO_API_DOCS_REQUIRE_LOGIN": True,
        "MCP_ENABLED": False,
    },
}
