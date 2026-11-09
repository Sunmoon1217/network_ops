from netops.schema import ExtraModel


class CaseResp(ExtraModel):
    gongdan_appli: str
    gongdan_title: str
    gongdanhao: str


class Case(ExtraModel):
    case_no: str
    title: str
    shenqing: str


class InspectResp(ExtraModel):
    name: str
    ip: str
    device_type: str
    device_zones: str
    hostid: str
    cpu_itemid: str
    memory_itemid: str
    cpu_avg: int
    cpu_max: int
    memory_avg: int
    memory_max: int


class Inspect(ExtraModel):
    name: str
    cpu_avg: int
    cpu_max: int
    memory_avg: int
    memory_max: int


class SlbResp(ExtraModel):
    slb_number: int
    licencer_number: int


class Slb(ExtraModel):
    instance: int
    listener: int
