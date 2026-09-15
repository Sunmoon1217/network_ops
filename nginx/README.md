# nginx 反向代理

为网络运维平台提供统一入口：**静态资源由 nginx 直接返回，动态请求反向代理到宿主机 Django**。

## 架构

```
                        ┌─ /assets/*  ──▶ /usr/share/nginx/html/assets/*   (Vue 构建产物)
                        ├─ /static/*  ──▶ /usr/share/nginx/static/*       (collectstatic 产物)
client ──▶ nginx ───────┤
          (80/443)      ├─ /api/*     ──▶ host.docker.internal:8000       (宿主机 Django)
                        ├─ /admin/*   ──▶ host.docker.internal:8000
                        ├─ /media/*   ──▶ host.docker.internal:8000
                        └─ 其它        ──▶ try_files → index.html (SPA 路由)
```

两类静态资源都绕过了 Django，不再经过 Python 进程，显著降低后端负载。

> 容器访问宿主机依赖 `docker-compose.yml` 中 nginx 服务的：
> ```yaml
> extra_hosts:
>   - "host.docker.internal:host-gateway"
> ```

## 目录结构

```
nginx/
├── conf.d/
│   ├── netops.conf                  # HTTP(80) 配置，默认启用
│   └── netops-ssl.conf.disabled     # HTTPS(443) 配置，默认未启用
├── ssl/
│   ├── .gitkeep
│   ├── server.crt                   # 证书（不提交）
│   └── server.key                   # 私钥（不提交）
├── gen-self-signed-cert.sh          # 自签证书生成脚本
└── README.md
```

nginx 只加载 `/etc/nginx/conf.d/*.conf`，故 `.disabled` 后缀的文件不会生效。

## 前置条件：准备两类静态资源

nginx 托管的是**构建产物**，启动前必须先生成，否则页面 404：

```bash
# 1. Vue 构建产物 → frontend/dist/
cd frontend && pnpm build && cd ..

# 2. Django 静态文件 → www/  （STATIC_ROOT = BASE_DIR / "www"）
uv run python manage.py collectstatic --noinput
```

`docker-compose.yml` 的挂载关系：

| 宿主机 | 容器内 | 对应 URL |
|--------|--------|---------|
| `./frontend/dist` | `/usr/share/nginx/html` | `/assets/*` |
| `./www` | `/usr/share/nginx/static` | `/static/*` |

> **若这两个目录不存在**，Docker 会创建空目录，相应资源将 404 —— 这是最常见的问题。

## 使用方法

### 1. 启动依赖与应用

```bash
# PostgreSQL + Redis
docker compose up -d db redis

# Django（宿主机）
uv run python manage.py migrate
uv run python manage.py runserver 0.0.0.0:8000
```

> 必须监听 `0.0.0.0:8000` 而非默认的 `127.0.0.1:8000`，
> 否则容器内的 nginx 无法访问。

### 2. 启动 nginx

```bash
docker compose up -d nginx
```

访问 <http://localhost>（端口可用 `NGINX_PORT` 覆盖）。

### 3. 启用 HTTPS（可选）

```bash
# 生成自签证书（本地开发）
bash nginx/gen-self-signed-cert.sh

# 启用 HTTPS 配置
mv nginx/conf.d/netops-ssl.conf.disabled nginx/conf.d/netops-ssl.conf

# 重载
docker compose restart nginx
```

访问 <https://localhost>（端口可用 `NGINX_SSL_PORT` 覆盖）。
浏览器会提示自签证书不受信任，属正常现象。生产环境请替换为正式证书。

## 静态资源策略

| 路径 | 处理方式 | 缓存 |
|------|---------|------|
| `/assets/*` | nginx 直出（Vue 产物） | `public, max-age=31536000, immutable` |
| `/static/*` | nginx 直出（collectstatic 产物） | `public, max-age=2592000`（30 天） |
| `/index.html` | nginx 直出 | `no-cache, no-store, must-revalidate` |
| `/api/*` | 代理到 Django | — |
| `/admin/*`、`/media/*` | 代理到 Django | — |
| 其它路径 | SPA 兜底 → `index.html` | — |

已启用 gzip（`text/*`、`application/javascript`、`application/json`、`image/svg+xml`、字体等）。

### 为什么 index.html 不缓存，assets 长期缓存？

Vite 构建产物的文件名带内容 hash（如 `accounts-CLRZcrUY.js`），内容变了文件名就变，
因此可以安全地长期缓存；而 `index.html` 引用了这些文件名，必须不缓存才能让发版立即生效。

## 可配置的环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `NGINX_PORT` | `80` | HTTP 映射端口 |
| `NGINX_SSL_PORT` | `443` | HTTPS 映射端口 |

## 常用运维命令

```bash
# 校验配置语法（改完配置先跑）
docker compose exec nginx nginx -t

# 重载配置（不中断连接）
docker compose exec nginx nginx -s reload

# 查看日志
docker compose logs -f nginx

# 查看访问日志
docker compose exec nginx tail -f /var/log/nginx/netops.access.log
```

## 发版流程

```bash
cd frontend && pnpm build && cd ..        # 重新构建前端
uv run python manage.py collectstatic --noinput   # 若后端静态文件有变更
docker compose restart nginx              # 或 nginx -s reload
```

由于 `assets` 带 hash 且 `index.html` 不缓存，用户刷新即可生效，无需清缓存。

## 说明

- **上传大小**：`100m`，用于设备 Excel 导入。
- **超时**：`proxy_read_timeout 300s`，因路径追踪、配置解析等操作较慢。
- **关闭缓冲**：`/api/` 关闭 `proxy_buffering`，便于流式响应。

## 排查

| 现象 | 原因与处理 |
|------|-----------|
| 首页 404 / 空白 | `frontend/dist` 为空，执行 `cd frontend && pnpm build` |
| admin 后台无样式 | `www/` 为空，执行 `uv run python manage.py collectstatic --noinput` |
| `502 Bad Gateway` | 宿主机 Django 未启动，或未监听 `0.0.0.0` |
| 接口返回 html 而非 JSON | 请求被 SPA 兜底，检查 location 匹配顺序 |
| 容器内解析不到 `host.docker.internal` | nginx 服务缺少 `extra_hosts` |
| 修改配置未生效 | 执行 `docker compose restart nginx` 或 `nginx -s reload` |
| HTTPS 启动失败 | 证书缺失，运行 `bash nginx/gen-self-signed-cert.sh` |
