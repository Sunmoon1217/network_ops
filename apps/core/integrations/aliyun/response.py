from typing import cast


class AsapiResponse:
    def __init__(self, response):
        if response is None:
            raise ValueError("无响应")
        if not isinstance(response, dict):
            raise ValueError("响应对象类型不是字典")
        resp_success = response.get("asapiSuccess", None)
        if resp_success is None:
            raise ValueError("")
        if not cast(bool, resp_success):
            raise ValueError(f"{response['message']}")
        self.response = response


class LoadBalancesResponse(AsapiResponse):
    def __init__(self, response):
        super().__init__(response)

    @property
    def loadbalances(self):
        return self.response["LoadBalances"]["LoadBalance"]
