"""负载均衡 / 域名解析页面的关联链聚合接口（只读）。

两个页面各把一条关联链压进一行展示：

- 负载均衡：``LtmVirtualServer → LtmPool → LtmPoolMember``（VS / pool / member）
- 域名解析：``GtmWideip → GtmPool → GtmVServer``（wideip / pool / vs）

逐个 ViewSet 让前端再拼必然 N+1（每行两次查询），所以这里按页聚合、
固定条数查库返回整链。**不建辅助表**：单页默认 50 行只有个位数查询，
且配置入库是低频动作、数据随时可能被重新解析覆盖，实时查即可——
真出现慢查询再考虑缓存表，别提前背上失效同步的包袱。

URL 前缀 ``/api/lb-chain/`` 沿用 analysis「路由跟 view 走」的惯例挂进
``analysis/api/urls.py``；聚合口径（GTM 成员三种形态的兼容）复用
``analysis.api.analysis._parse_member_entry``，避免两处各写一份漂移。
"""

from django.db.models import Q
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny

from analysis.api.analysis import _parse_member_entry
from assets.models import GtmPool, GtmServer, GtmVServer, GtmWideip, LtmPool, LtmPoolMember, LtmVirtualServer
from netops.pagination import StandardPagination

# 模糊搜索反查出的 (device, pool) 组合上限：搜索词极短时可能命中全表，
# 组合 Q 是逐条 OR 展开的，必须封顶防止构造出巨型查询
MAX_SEARCH_PAIRS = 500

# 允许的排序字段（与 LTM/GTM 各 ViewSet 的 ordering_fields 对齐），
# 默认按 设备 + 名字 排，保证翻页稳定
ORDERABLE = {"name", "device_hostname", "created_at"}
DEFAULT_ORDER = ("device__hostname", "name")


def _device_filter(request, qs):
    device_id = request.query_params.get("device")
    return qs.filter(device_id=device_id) if device_id else qs


def _pairs_q(pairs, value_field: str) -> Q:
    """把 (device_id, 名字) 组合列表展开成 OR 查询。

    组合条件没法用单个 ``__in`` 表达（两个维度要成对匹配），只能逐对 OR；
    ``value_field`` 是第二个维度落到的字段名（如 ``pool`` / ``name``）。
    调用方负责用 ``MAX_SEARCH_PAIRS`` 封顶。
    """
    q = Q()
    for device_id, value in pairs:
        q |= Q(device_id=device_id, **{value_field: value})
    return q


def _order(qs, request, allowed_extra: dict):
    """按 ?ordering= 排序：前缀 '-' 即倒序，未知字段回退默认序。"""
    raw = request.query_params.get("ordering") or ""
    desc = raw.startswith("-")
    field = raw.lstrip("-")
    if field in ORDERABLE:
        field = allowed_extra.get(field, field)
        return qs.order_by(f"-{field}" if desc else field)
    return qs.order_by(*DEFAULT_ORDER)


def _page(request, qs):
    """统一走 StandardPagination（50/页、上限 500），返回 (当页列表, 分页器)。"""
    paginator = StandardPagination()
    page = paginator.paginate_queryset(qs, request)
    return list(page or []), paginator


# ---------------------------------------------------------------------------
# LTM：VS → 池 → 成员
# ---------------------------------------------------------------------------


def _split_addr_port(term: str):
    """把 ``地址:端口`` / ``地址#端口`` 拆成 (地址, 端口)；拆不出合法组合返回 None。

    支持的检索形态与坑：

    - ``#`` 是项目展示层的地址端口分隔符（与互联网资产分析同约定），天然无歧义；
    - ``:`` 必须防 IPv6 误拆——``2001:db8::1`` 的最后一段也是纯数字，直接按最后
      一个冒号切会把地址切残。规则：**最后一段是 1~5 位纯数字、且地址部分不以
      冒号结尾**才拆（``10.0.0.1:443``、``2001:db8::1:80`` 能拆，``2001:db8::1``
      不拆、退化成整串模糊匹配地址）；
    - 端口用**精确匹配**（搜 ``:80`` 不能命中 ``8080``）。
    """
    if "#" in term:
        addr, sep, port = term.rpartition("#")
    elif ":" in term:
        addr, sep, port = term.rpartition(":")
    else:
        return None
    if not (addr and sep and port.isdigit() and len(port) <= 5) or addr.endswith(":"):
        return None
    return addr.strip(), port


def _ltm_search(qs, search: str):
    """SLB 页搜索：VS 名 / 虚拟地址 / 池名 / 设备名 直接匹配；成员走反查拼进 OR。

    词里带端口（``vsaddress:port`` / ``poolmemberaddress:port``）时拆成
    地址与端口两个条件**同时**命中——跨字段组合是整串 icontains 做不到的：

    - VS 侧：``vs_address`` 命中地址 且 ``vs_port`` 精确等于端口；
    - 成员侧：成员表按 address + port 查出 (device, pool_name)，再折算回
      「该设备上引用这些池的 VS」（VS 行上没有成员字段，只能这样反查）。
    """
    q = (
        Q(name__icontains=search)
        | Q(vs_address__icontains=search)
        | Q(pool__icontains=search)
        | Q(device__hostname__icontains=search)
    )
    pair = _split_addr_port(search)
    addr, port = pair if pair else (search, None)
    if pair:
        # 地址:端口 组合——VS 自身命中，或成员按 地址+端口 命中后反查
        q |= Q(vs_address__icontains=addr, vs_port=port)
    member_q = Q(address__icontains=addr)
    if port:
        member_q &= Q(port=port)
    hits = set(LtmPoolMember.objects.filter(member_q).values_list("device_id", "pool_name")[:MAX_SEARCH_PAIRS])
    if hits:
        # (device_id, pool_name) → 该设备上 pool 名命中的 VS
        q |= _pairs_q(hits, value_field="pool")
    return qs.filter(q)


def _ltm_rows(page: list[LtmVirtualServer]) -> list[dict]:
    """按页批量取池与成员，拼成 VS 行（每类一次查询，不逐行查库）。"""
    pool_keys = {(vs.device_id, vs.pool) for vs in page if vs.pool}
    device_ids = {vs.device_id for vs in page}
    pool_names = {name for _, name in pool_keys}

    pools: dict[tuple[int, str], LtmPool] = {}
    if pool_keys:
        pools = {
            (p.device_id, p.name): p
            for p in LtmPool.objects.filter(device_id__in=device_ids, name__in=pool_names).select_related("device")
        }

    members: dict[tuple[int, str], list[LtmPoolMember]] = {}
    if pool_names:
        for m in LtmPoolMember.objects.filter(device_id__in=device_ids, pool_name__in=pool_names):
            members.setdefault((m.device_id, m.pool_name), []).append(m)

    rows = []
    for vs in page:
        pool = pools.get((vs.device_id, vs.pool)) if vs.pool else None
        rows.append(
            {
                "device": vs.device_id,
                "device_hostname": vs.device.hostname,
                "name": vs.name,
                "vs_address": vs.vs_address,
                "vs_port": vs.vs_port or "",
                "protocol": vs.protocol or "",
                "status": vs.status,
                "snat_type": vs.snat_type or "",
                "persist": vs.persist or "",
                "pool": (
                    {
                        "name": pool.name,
                        "mode": pool.mode,
                        "monitors": pool.monitors or [],
                    }
                    if pool
                    else None
                ),
                "members": [
                    {"name": m.name, "address": m.address, "port": m.port or ""}
                    for m in members.get((vs.device_id, vs.pool), [])
                ],
            }
        )
    return rows


@api_view(["GET"])
@permission_classes([AllowAny])
def ltm_chains(request):
    """负载均衡关联链：GET /api/lb-chain/slb/?device=&search=&ordering=&page="""
    qs = _device_filter(request, LtmVirtualServer.objects.select_related("device").all())
    search = (request.query_params.get("search") or "").strip()
    if search:
        qs = _ltm_search(qs, search)
    qs = _order(qs, request, allowed_extra={"device_hostname": "device__hostname"})

    page, paginator = _page(request, qs)
    if page is None:  # 页码非法时 paginate_queryset 已经抛 NotFound，这里只兜空页
        page = []
    return paginator.get_paginated_response(_ltm_rows(page))


# ---------------------------------------------------------------------------
# GTM：WideIP → 池 → GTM 虚拟服务器
# ---------------------------------------------------------------------------


def _gtm_search(qs, search: str):
    """域名 / 设备名直接匹配；池名走反查（wideip.pools 是 JSON 名字列表）。"""
    q = Q(name__icontains=search) | Q(device__hostname__icontains=search)
    hits = set(GtmPool.objects.filter(name__icontains=search).values_list("device_id", "name")[:MAX_SEARCH_PAIRS])
    if hits:
        # JSON 包含语义（pools 列表含该池名）不是普通等值，逐对展开
        pairs_q = Q()
        for device_id, pool_name in hits:
            pairs_q |= Q(device_id=device_id, pools__contains=[pool_name])
        q |= pairs_q
    return qs.filter(q)


def _gtm_rows(page: list[GtmWideip]) -> list[dict]:
    """按页批量取 GTM 池与虚拟服务器，把成员折算出 IP/端口。

    成员只存 ``server``/``vserver`` 名字，IP 在 ``GtmVServer`` 上，
    需要 (device, server 名, vs 名) 三元组才能定位——按页建索引一次查齐。
    """
    device_ids = {w.device_id for w in page}
    wideip_pool_names = {name for w in page for name in (w.pools or [])}

    pools: dict[tuple[int, str], GtmPool] = {}
    if wideip_pool_names:
        pools = {
            (p.device_id, p.name): p
            for p in GtmPool.objects.filter(device_id__in=device_ids, name__in=wideip_pool_names)
        }

    # (device_id, server 名, vs 名) → GtmVServer；server 是 FK，名字在 GtmServer 上
    vserver_index: dict[tuple[int, str, str], GtmVServer] = {}
    if device_ids:
        server_names = dict(GtmServer.objects.filter(device_id__in=device_ids).values_list("id", "name").iterator())
        for vs in GtmVServer.objects.filter(device_id__in=device_ids).select_related("server"):
            vserver_index[(vs.device_id, server_names.get(vs.server_id) or vs.server.name, vs.name)] = vs

    rows = []
    for w in page:
        pool_out = []
        for pool_name in w.pools or []:
            pool = pools.get((w.device_id, pool_name))
            member_out = []
            if pool:
                for entry in pool.members or []:
                    server_name, vs_name, raw = _parse_member_entry(entry)
                    target = vserver_index.get((w.device_id, server_name, vs_name))
                    member_out.append(
                        {
                            "server": server_name,
                            "vserver": vs_name,
                            "status": str(raw.get("status") or raw.get("member_status") or ""),
                            # 找不到 GtmVServer 就没有 IP——前端回退显示 server/vserver 名字
                            "address": target.ip_address if target else None,
                            "port": (target.port if target else "") or "",
                            "found": target is not None,
                        }
                    )
            pool_out.append(
                {
                    "name": pool_name,
                    # wideip 引用了但池记录不存在：给空骨架，前端才能显示「池缺失」而不是吞掉
                    "lb_mode": pool.lb_mode if pool else "",
                    "fallback_ip": (pool.fallback_ip if pool else None) or "",
                    "ttl": pool.ttl if pool else None,
                    "members": member_out,
                }
            )
        rows.append(
            {
                "device": w.device_id,
                "device_hostname": w.device.hostname,
                "name": w.name,
                "rtype": w.rtype or "",
                "lb_mode": w.lb_mode or "",
                "pools": pool_out,
            }
        )
    return rows


@api_view(["GET"])
@permission_classes([AllowAny])
def gtm_chains(request):
    """域名解析关联链：GET /api/lb-chain/gslb/?device=&search=&ordering=&page="""
    qs = _device_filter(request, GtmWideip.objects.select_related("device").all())
    search = (request.query_params.get("search") or "").strip()
    if search:
        qs = _gtm_search(qs, search)
    qs = _order(qs, request, allowed_extra={"device_hostname": "device__hostname"})

    page, paginator = _page(request, qs)
    if page is None:
        page = []
    return paginator.get_paginated_response(_gtm_rows(page))
