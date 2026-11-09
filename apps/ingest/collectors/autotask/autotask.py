"""autotask（工单 / 巡检 / SLB）的 HTTP 客户端：**只采集，不落库**。

原样保留旧项目的三个接口地址；工单 DTO 用 ``ExtraModel(extra="allow")`` 透传外部额外
字段（前端表格要 zhixing / shijian / status），不再只拷 case_no / title / shenqing。
"""

from httpx2 import AsyncClient

from .schemas import Case, CaseResp, Inspect, InspectResp, Slb, SlbResp

BASE_URL = "http://10.15.13.83:8000"


async def fetch_case():
    results: list[Case] = []
    url = f"{BASE_URL}/devices/search-network-gongdan"
    async with AsyncClient() as client:
        response = await client.get(url)
        if response.status_code != 200:
            raise RuntimeError(f"工单接口 HTTP {response.status_code}: {url}")

        data = response.json().get("message", [])
        if not data:
            raise RuntimeError(f"工单接口返回空数据: {url}")

        for item in data:
            resp = CaseResp.model_validate(item)
            results.append(
                Case.model_validate(
                    {
                        **resp.model_dump(),
                        "case_no": resp.gongdanhao,
                        "title": resp.gongdan_title,
                        "shenqing": resp.gongdan_appli,
                    }
                )
            )

    return results


async def fetch_inspect():
    results: list[Inspect] = []
    url = f"{BASE_URL}/devices/device-inspect"
    async with AsyncClient() as client:
        response = await client.get(url, timeout=300)
        if response.status_code != 200:
            raise RuntimeError(f"巡检接口 HTTP {response.status_code}: {url}")

        data = response.json().get("message", [])
        if not data:
            raise RuntimeError(f"巡检接口返回空数据: {url}")

        for item in data:
            resp = InspectResp.model_validate(item)
            results.append(
                Inspect(
                    name=resp.name,
                    cpu_avg=resp.cpu_avg,
                    cpu_max=resp.cpu_max,
                    memory_avg=resp.memory_avg,
                    memory_max=resp.memory_max,
                )
            )

    return results


async def fetch_slb():
    results: list[Slb] = []
    url = f"{BASE_URL}/qianyun/get-slb-info"
    async with AsyncClient() as client:
        response = await client.get(url)
        if response.status_code != 200:
            raise RuntimeError(f"SLB 接口 HTTP {response.status_code}: {url}")

        data = response.json()
        if not data:
            raise RuntimeError(f"SLB 接口返回空数据: {url}")

        resp = SlbResp.model_validate(data)
        results = [Slb(instance=resp.slb_number, listener=resp.licencer_number)]

    return results


async def fetch_line():
    """线路接口旧项目未实现；返回空列表而不是 None，调用方无需特判。"""
    return []
