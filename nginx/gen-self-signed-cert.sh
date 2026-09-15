#!/usr/bin/env bash
#
# 生成自签证书（仅用于本地开发 / 测试环境）
#
# 用法：
#   bash nginx/gen-self-signed-cert.sh
#   SSL_CN=netops.local bash nginx/gen-self-signed-cert.sh   # 自定义域名
#
set -euo pipefail

SSL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/ssl"
mkdir -p "$SSL_DIR"

CRT="$SSL_DIR/server.crt"
KEY="$SSL_DIR/server.key"

if [[ -f "$CRT" || -f "$KEY" ]]; then
  echo "⚠️  证书已存在，跳过生成。如需重新生成，请先删除："
  echo "     $CRT"
  echo "     $KEY"
  exit 0
fi

CN="${SSL_CN:-localhost}"
DAYS="${SSL_DAYS:-3650}"

openssl req -x509 -nodes -newkey rsa:2048 \
  -days "$DAYS" \
  -keyout "$KEY" \
  -out "$CRT" \
  -subj "/C=CN/ST=State/L=City/O=NetworkOps/CN=${CN}" \
  -addext "subjectAltName=DNS:localhost,DNS:${CN},IP:127.0.0.1"

chmod 600 "$KEY"
chmod 644 "$CRT"

echo "✅ 自签证书已生成："
echo "     证书：$CRT"
echo "     私钥：$KEY"
echo "     有效期：${DAYS} 天"
echo
echo "下一步："
echo "   1) 将 nginx/conf.d/netops-ssl.conf.disabled 重命名为 netops-ssl.conf"
echo "   2) docker compose restart nginx"
echo
echo "⚠️  自签证书仅供本地开发，浏览器会提示证书不受信任。"
