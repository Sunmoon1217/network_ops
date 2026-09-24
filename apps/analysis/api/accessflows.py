"""``/api/access-flows/``：访问流（策略展开结果）的只读查询。

只读——AccessFlow 是派生数据，唯一的写入口是 access_flow_consumer（单写者）；
要改数据就重建源头的策略，再 ``rebuild_access_flows``。

过滤参数（都命中索引）：

- ``?device=<id>``：contexts 里挂着这台设备的行（``device_ids`` GIN 包含过滤）；
- ``?policy=<id>``：命中这条策略的行（``policy_ids`` GIN 包含过滤）；
- ``?action=allow|deny``：按行级动作过滤（action 进唯一键后每行动作单一，面板的
  「允许/拒绝」筛选走这里；非法值 400）；
- ``?search=<词>``：键字段里的 IP / 端口 / 协议子串（DRF SearchFilter）。
"""

from rest_framework import serializers, viewsets
from rest_framework.exceptions import ValidationError

from analysis.models import AccessFlow


class AccessFlowSerializer(serializers.ModelSerializer):
    class Meta:
        model = AccessFlow
        fields = (
            "id",
            "src_ip",
            "src_prefix",
            "src_range_end",
            "dst_ip",
            "dst_prefix",
            "dst_range_end",
            "protocol",
            "port",
            "port2",
            "action",
            "contexts",
            "device_ids",
            "policy_ids",
            "created_at",
            "updated_at",
        )


class AccessFlowViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = AccessFlowSerializer
    search_fields = ("src_ip", "dst_ip", "src_range_end", "dst_range_end", "protocol", "port", "port2")
    ordering_fields = ("src_ip", "dst_ip", "protocol", "port", "action", "updated_at")

    def get_queryset(self):
        queryset = AccessFlow.objects.all()
        device = self._int_param("device")
        if device is not None:
            queryset = queryset.filter(device_ids__contains=[device])
        policy = self._int_param("policy")
        if policy is not None:
            queryset = queryset.filter(policy_ids__contains=[policy])
        action = self.request.query_params.get("action")
        if action:
            if action not in ("allow", "deny"):
                raise ValidationError({"action": "必须是 allow 或 deny"})
            queryset = queryset.filter(action=action)
        return queryset

    def _int_param(self, name: str) -> int | None:
        raw = self.request.query_params.get(name)
        if raw in (None, ""):
            return None
        try:
            return int(raw)
        except ValueError:
            raise ValidationError({name: "必须是整数 ID"}) from None
