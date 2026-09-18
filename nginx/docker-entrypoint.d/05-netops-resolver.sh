#!/bin/sh
# 生成 nginx 的运行时 DNS 解析器配置：/etc/nginx/netops/resolver.conf
#
# 为什么要有这个脚本，而不是在 conf.d 里写死 resolver：
#   镜像是同一个（官方 nginx 镜像与 runtime 无关，resolver 行为也一样），不一样的只是
#   **runtime 给容器写的 /etc/resolv.conf**——所以「解析器地址」只有 runtime 知道：
#     Docker（用户自定义 bridge）→ 内置 DNS 127.0.0.11
#     Podman                     → aardvark-dns 在网络**网关**上，例如 10.89.3.1
#   原先 conf.d 里写死的就是 127.0.0.11（按「只部署 Docker」定的值），在 Podman 上会得到：
#     recv() failed (111: Connection refused) while resolving, resolver: 127.0.0.11:53
#   网络完全正常，只是解析器地址不对 → app 解析不出来 → 前端 502。
#
# 也不能干脆删掉 resolver：nginx 的 resolver 只接受**显式地址**（`system`、文件路径都非法），
# 而变量形式的 proxy_pass 不配 resolver 时——`nginx -t` 能过，但每个请求都会
#   502 + "no resolver defined to resolve app"。所以方向是**把地址推导出来**，不是去掉。
#
# 为什么不用官方镜像的 envsubst 模板机制（templates/*.template）：
#   那条路要求额外设置 NGINX_ENTRYPOINT_LOCAL_RESOLVERS=1——否则镜像自带的
#   15-local-resolvers.envsh 直接 return，占位符原样留在配置里，而 `nginx -t`
#   **竟然仍然通过**，故障要等真正转发时才暴露（实测过）；它还要求输出目录已存在且
#   可写，否则静默跳过。这里直接从 /etc/resolv.conf 推导并写出结果，取不到 nameserver
#   就**报错退出**，让问题在容器启动时立刻暴露。
#
# 执行时机：nginx 官方镜像的 entrypoint 会把 /docker-entrypoint.d/ 下的可执行文件按
# 名字顺序跑完，之后才启动 nginx。docker-compose.yml 把本文件挂到那个目录里。

set -e

OUT_DIR=/etc/nginx/netops
OUT_FILE="$OUT_DIR/resolver.conf"

# 与官方 15-local-resolvers.envsh 相同的取值逻辑：多个就用空格分隔，IPv6 加方括号
nameservers=$(awk 'BEGIN { ORS=" " } $1 == "nameserver" { if ($2 ~ ":") print "["$2"]"; else print $2 }' /etc/resolv.conf)
nameservers=${nameservers% }

if [ -z "$nameservers" ]; then
    echo "[netops] /etc/resolv.conf 里没有 nameserver，无法生成 resolver 配置" >&2
    exit 1
fi

mkdir -p "$OUT_DIR"
# resolver_timeout 只是「等多久放弃」的上界（默认 30s）——它不能让失败的解析变成功，
# 但 DNS 万一不可达时，请求会以 ~2s 收尾而不是挂 30s。
{
    printf 'resolver %s valid=10s ipv6=off;\n' "$nameservers"
    printf 'resolver_timeout 2s;\n'
} > "$OUT_FILE"
echo "[netops] 已生成 $OUT_FILE：resolver $nameservers valid=10s ipv6=off; resolver_timeout 2s;"
