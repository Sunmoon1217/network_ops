from httpx2 import AsyncClient

from .schemas import Case, CaseResp, Inspect, InspectResp, Slb, SlbResp


async def fetch_case():
    results: list[Case] = []
    async with AsyncClient() as client:
        response = await client.get("http://10.15.13.83:8000/devices/search-network-gongdan")
        if not response.status_code == 200:
            raise

        data = response.json().get("message", [])
        if not data:
            raise

        list_resp = [CaseResp.model_validate(item) for item in data]
        for resp in list_resp:
            results.append(
                Case(
                    case_no=resp.gongdanhao,
                    title=resp.gongdan_title,
                    shenqing=resp.gongdan_appli,
                )
            )

    return results


async def fetch_inspect():
    results: list[Inspect] = []
    async with AsyncClient() as client:
        response = await client.get("http://10.15.13.83:8000/devices/device-inspect", timeout=300)
        if not response.status_code == 200:
            raise

        data = response.json().get("message", [])
        if not data:
            raise

        list_resp = [InspectResp.model_validate(item) for item in data]
        for resp in list_resp:
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
    async with AsyncClient() as client:
        response = await client.get("http://10.15.13.83:8000/qianyun/get-slb-info")
        if not response.status_code == 200:
            raise

        data = response.json()
        if not data:
            raise

        resp = SlbResp.model_validate(data)
        results = [Slb(instance=resp.slb_number, listener=resp.licencer_number)]

    return results


async def fetch_line():
    pass
