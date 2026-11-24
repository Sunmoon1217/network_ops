#!/bin/sh
# 生成 nginx 的运行时 DNS 解析器配置 /etc/nginx/netops/resolver.conf。
# 解析器地址只有 runtime 知道（Docker 127.0.0.11 / Podman 网关），不能写死；
# 也不能删 resolver（变量式 proxy_pass 会 502）。完整取舍见 handbook/deploy.md。

set -e

OUT_DIR=/etc/nginx/netops
OUT_FILE="$OUT_DIR/resolver.conf"

# 与官方 15-local-resolvers.envsh 相同的取值逻辑
nameservers=$(awk 'BEGIN { ORS=" " } $1 == "nameserver" { if ($2 ~ ":") print "["$2"]"; else print $2 }' /etc/resolv.conf)
nameservers=${nameservers% }

if [ -z "$nameservers" ]; then
    echo "[netops] /etc/resolv.conf 里没有 nameserver，无法生成 resolver 配置" >&2
    exit 1
fi

mkdir -p "$OUT_DIR"
# resolver_timeout 只限制等待上界，DNS 不可达时请求约 2s 收尾而不是挂 30s
{
    printf 'resolver %s valid=10s ipv6=off;\n' "$nameservers"
    printf 'resolver_timeout 2s;\n'
} > "$OUT_FILE"
echo "[netops] 已生成 $OUT_FILE：resolver $nameservers valid=10s ipv6=off; resolver_timeout 2s;"
