"""实体声明用到的域内小工具（MAC 归一化）。

只被 ``specs/ipam.py``（``arp_mac`` 的 ``extra_search``）与 ``assets/tools.py``
（``locate``）使用——**不是**对外的实体声明，别把它当接口。
"""

import re

from django.db.models import Q


def _mac_compact(text: str) -> str:
    """去掉分隔符后的 12 位小写十六进制；不是 MAC 形态返回空串。

    三种写法（``aa-bb-cc-dd-ee-ff`` / ``aabb.ccdd.eeff`` / ``AA:BB:CC``）都出现过，
    不先归一化，MAC 查询十次有九次查不到。
    """
    compact = re.sub(r"[^0-9a-fA-F]", "", text or "").lower()
    return compact if len(compact) == 12 else ""


def _mac_variants(compact: str) -> list[str]:
    pairs = [compact[i : i + 2] for i in range(0, 12, 2)]
    # 点分形态是 3 组、每组 4 个十六进制（aabb.ccdd.eeff），所以按「两对一拼」走 0/2/4
    dotted = ".".join("".join(pairs[i : i + 2]) for i in range(0, 6, 2))
    return list(dict.fromkeys([":".join(pairs), "-".join(pairs), dotted, compact]))


def _arp_extra_search(text: str) -> list[Q]:
    """MAC 三种分隔符归一后的额外匹配条件（挂到 arp_mac 的 spec 上）。"""
    compact = _mac_compact(text)
    if not compact:
        return []
    return [Q(mac_address__iexact=variant) for variant in _mac_variants(compact)]


__all__ = ["_arp_extra_search", "_mac_compact", "_mac_variants"]
