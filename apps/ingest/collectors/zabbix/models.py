from pydantic import BaseModel, ConfigDict


class ExtraModel(BaseModel):
    model_config = ConfigDict(extra="allow")


class ZAPIGroup(ExtraModel):
    groupid: str


class ZAPIHost(ExtraModel):
    hostid: str


class ZAPIItem(ExtraModel):
    itemid: str
    hosts: list[dict]
    key_: str | None = None
    lastvalue: str | None = None


class ZAPITrigger(ExtraModel):
    triggerid: str


class ZAPIProblem(ExtraModel):
    eventid: str
    objectid: str
    host: ZAPIHost | None
    trigger: ZAPITrigger | None


class ZAPIHistory(BaseModel):
    itemid: str
    clock: str
    value: str
