# nginx 反向代理

为网络运维平台提供统一入口：**两类静态资源由 nginx 直接返回，动态请求反向代理到 `app` 容器**。

## 架构

```
                        ┌─ /assets/*  ──▶ /usr/share/nginx/html/assets/*   (Vue 构建产物)
                        ├─ /static/*  ──▶ /usr/share/nginx/static/*       (collectstatic 产物)
client ──▶ nginx ───────┤
          (80/443)      ├─ /api/*     ──▶ app:8000                        (compose 的 app 服务)
                        ├─ /admin/*   ──▶ app:8000
                        ├─ /media/*   ──▶ app:8000
                        └─ 其它        ──▶ try_files → index.html (SPA 路由)
```

两类静态资源都绕过了 Django，不再经过 Python 进程。

### 静态产物是怎么到 nginx 的

产物的源头是**宿主机**，流程是「宿主机构建 → COPY 进 app 镜像 → 命名卷 → nginx」：

1. 宿主机上执行 `cd frontend && pnpm build` 与 `uv run python manage.py collectstatic --noinput`；
2. `Dockerfile.app` 把 `frontend/dist` 与 `www` **COPY 进 app 镜像**
   （`.dockerignore` 特意放开了这两个目录）；这两个路径同时就是 Django 的
   `STATIC_ROOT` 与 `FRONTEND`，DEBUG 下 Django 自己也从这里托管；
3. 容器启动时 `docker/entrypoint.sh` 把它们复制**另一份**到命名卷（**一个**卷，按 URL 前缀布局）；
4. nginx 只读挂载这**一个**卷。

镜像里因此**没有任何 node/npm/pnpm**，构建也只需秒级。代价是构建前必须先在宿主机
把成品构建出来——镜像里有断言，`frontend/dist` 缺 `index.html` 或 `www` 为空都会
直接构建失败。

### 为什么必须用卷

nginx 是独立容器，**读不到 app 容器镜像里的文件**。Docker 里跨容器共享挂载只有卷这一条路：

| 方式 | 能否跨容器共享 |
|------|---------------|
| 命名卷 / 绑定挂载 | ✅ |
| `tmpfs` | ❌ 每个容器各自私有、内存文件系统，`--volumes-from` 也拿不到（Docker 没有共享 tmpfs 的机制），且容器一停内容即丢 |

而卷挂在有内容的目录上会**遮住镜像里的同名目录**，Docker 又只在卷首次创建时用镜像内容播种一次——重建镜像后旧卷不会更新，表现就是「镜像里产物是新的，页面还是旧的」。

所以命名卷挂在镜像里**故意留空的目录** `/var/lib/netops-static` 上：卷的初始内容为空，内容唯一来源就是 entrypoint 启动时的复制，不存在「播种过一次就不更新」的歧义。复制是**权威**的（先清空再铺），所以上一版带 hash 的遗留资源也不会堆在卷里。

卷内的目录布局**按 URL 前缀设计**，这样 nginx 一个 `root` 就能覆盖全部静态请求：

```
<卷>/
├── index.html   ← Vite 产物（SPA 入口，/ 走 try_files 兜底）
├── assets/*     ← Vite 产物（/assets/*）
└── static/*     ← collectstatic 产物（/static/*，STATIC_URL 就是 /static/）
```

宿主机上 `www/` 与 `frontend/dist/` 仍然是各自独立的目录、各自的工具负责清空（`collectstatic --clear` / `pnpm build` 的 `emptyOutDir`），只有容器里的**这一份副本**被合到一起，所以两个清空动作互不干扰。

### 为什么用显式命名卷，而不是 `volumes_from`

`volumes_from: ["app:ro"]` 也能让 nginx 拿到卷（compose 支持，还会隐式加上 `depends_on`），但有两个副作用：

| `volumes_from` 的行为 | 后果 |
|----------------------|------|
| 把源容器的**所有**卷都带过来，且不能挑 | nginx 会连 `app_data`（`data/config_repo` 那个 git 仓库）一起拿到 |
| 卷在目标容器里的路径 = 源容器的路径 | nginx 只能看到 `/app/www`、`/app/frontend/dist`，`root` 得写成 app 的内部路径，配置被绑死 |

所以 compose 里显式写 `static_data:/usr/share/nginx/html:ro`：只读、能挑卷、放在 nginx 自己的常规路径上，一个 root 覆盖 `/`、`/assets/*`、`/static/*`。

## 目录结构

```
nginx/
├── conf.d/
│   ├── netops.conf                  # HTTP(80) 配置，默认启用
│   └── netops-ssl.conf.disabled     # HTTPS(443) 配置，默认未启用
├── docker-entrypoint.d/
│   └── 05-netops-resolver.sh        # 启动时把当前 runtime 的 DNS 写成 /etc/nginx/netops/resolver.conf
├── ssl/
│   ├── .gitkeep
│   ├── server.crt                   # 证书（不提交）
│   └── server.key                   # 私钥（不提交）
├── gen-self-signed-cert.sh          # 自签证书生成脚本
└── README.md
```

nginx 只加载 `/etc/nginx/conf.d/*.conf`，故 `.disabled` 后缀的文件不会生效。
`docker-entrypoint.d/05-netops-resolver.sh` 由镜像的 entrypoint 在启动 nginx 之前执行，
生成 `/etc/nginx/netops/resolver.conf`（**不是** conf.d），再被 conf.d 里的配置 `include` 进来。

## 卷挂载关系

| 卷 | app 容器 | nginx 容器 | 内容 |
|----|---------|-----------|------|
| `static_data` | `/var/lib/netops-static`（读写） | `/usr/share/nginx/html`（只读） | `index.html` + `assets/`（Vite）与 `static/`（collectstatic） |
| `app_data` | `/app/data`（读写） | — | 配置仓库（必须持久化） |

app 侧的挂载点在镜像里是**空目录**，只作为命名卷的落点；镜像里真正放产物的是
`/app/frontend/dist` 与 `/app/www`（Django 用），entrypoint 负责把它们复制进卷
（`dist` → 卷根，`www` → 卷内 `static/`）。

`static_data` 属于**可丢弃数据**：删掉卷后 `docker compose up -d app` 会从镜像重新同步出来（`app_data` 则必须保留）。

## 使用方法

```bash
# 0. 先在宿主机构建静态成品（镜像只是把它们 COPY 进去）
cd frontend && pnpm build && cd ..
uv run python manage.py collectstatic --noinput

# 首次构建镜像并启动全套（db / redis / app / worker / nginx）
docker compose up -d --build

# 数据库迁移不用手跑：app 容器启动时只在「有未应用的迁移」时才执行
# （manage.py migrate_if_needed，多副本由数据库自带的命名锁串行化）。
# 想人工放行就设 MIGRATE_ON_START=0 再执行：
docker compose run --rm app python manage.py migrate

# 创建管理员
docker compose run --rm app python manage.py createsuperuser
```

访问 <http://localhost>（端口可用 `NGINX_PORT` 覆盖）。

### 后端地址为什么用 `resolver` + 变量

配置里写的是：

```nginx
include /etc/nginx/netops/resolver.conf;   # ← 由 docker-entrypoint.d/ 的脚本在启动时生成
set $netops_upstream "app:8000";
...
proxy_pass http://$netops_upstream;
```

而不是 `upstream` 块，原因有两点：

1. `upstream` **只在启动时解析一次**。`app` 容器重建后会拿到新 IP，nginx 仍指向旧 IP，表现为「重建 app 之后一直 502，直到 reload nginx」。变量形式让 nginx 按 `valid` 周期重新解析。
2. 静态 `upstream` 一旦解析不到 `app` 就直接 `emerg` 退出——脱离 compose 网络连 `nginx -t` 都过不了；变量形式只在真正转发时才解析。

#### resolver 的地址不能写死（地址由 runtime 决定）

**镜像与 runtime 无关**：官方 nginx 镜像是同一个，`resolver` 的行为也一样。不一样的只是
**runtime 给容器写的 `/etc/resolv.conf`**，所以「DNS 解析器地址」这件事只有 runtime 知道：

| runtime | 容器内 `/etc/resolv.conf` | 说明 |
|---------|--------------------------|------|
| Docker（用户自定义 bridge） | `nameserver 127.0.0.11` | Docker 内置 DNS |
| **Podman** | 例如 `nameserver 10.89.3.1` | aardvark-dns 在**网络网关**上提供 DNS，**没有 127.0.0.11** |

原先这里写死的是 `resolver 127.0.0.11`——那是按「只部署在 Docker」定的值（`876fbf9` 的
注释原文就是「127.0.0.11 是 Docker 的内置 DNS」）。硬编码在别的 runtime 上就是：

```
recv() failed (111: Connection refused) while resolving, resolver: 127.0.0.11:53
```

网络本身完全正常，只是解析器地址不对 → `app` 解析失败 → 前端 **502**。

> 为什么不干脆删掉 `resolver`（那样就不需要地址了）：那就得回到静态 `upstream` 块，
> 而它有两个已经实测过的代价——只在启动时解析一次（app 重建换 IP 后一直 502 直到
> reload），以及解析不到 `app` 时直接 `emerg` 退出（脱离 compose 网络连 `nginx -t`
> 都过不了）。变量形式必须配 `resolver`，而 `resolver` 必须显式给地址；所以正确的
> 做法是**把地址的来源参数化/推导出来**，而不是去掉它。

所以改成**启动时推导**：`nginx/docker-entrypoint.d/05-netops-resolver.sh` 从容器自己的
`/etc/resolv.conf` 取出 `nameserver`，写成 `/etc/nginx/netops/resolver.conf`，conf.d 里的两个
server 块（80 与 443）再 `include` 它。`docker-compose.yml` 只把这**一个文件**挂到镜像的
`/docker-entrypoint.d/`——**不要挂整个目录**，那会遮住镜像自带的 entrypoint 脚本；它由镜像
entrypoint 在启动 nginx 之前执行（`docker logs nginx` 里能看到 `Launching .../05-netops-resolver.sh`）。

脚本行为，以及为什么不走官方 envsubst 模板：

- 多个 `nameserver` 用空格拼接，IPv6 自动加方括号（与镜像自带的 `15-local-resolvers.envsh` 同逻辑）。
- **取不到 nameserver 就报错退出**，容器启动即失败，不会留下坏配置。
- 官方模板机制（`templates/*.template` + `NGINX_LOCAL_RESOLVERS`）也能做，但它要求额外设置
  `NGINX_ENTRYPOINT_LOCAL_RESOLVERS=1`：**不设那个变量，镜像自带的脚本会直接 return，占位符
  原样留在配置里，而 `nginx -t` 竟然仍然通过**（实测过），故障要等真正转发时才暴露；它还要求
  输出目录已存在且可写，否则静默跳过（所以还得再挂个 `tmpfs`）。相比之下这个脚本失败即响。

> 验证：`docker compose exec nginx cat /etc/nginx/netops/resolver.conf`，应与容器
> `/etc/resolv.conf` 里的 `nameserver` 一致；`docker compose exec nginx nginx -T | grep resolver`
> 确认已生效。注意 `/etc/nginx/netops/` 是容器内目录（每次启动重新生成），不需要持久化。

> 若要让 nginx 指向**宿主机**上直接跑的 Django（不用 app 容器）：把 `$netops_upstream` 改成 `host.docker.internal:8000`，并给 nginx 服务加回
> ```yaml
> extra_hosts:
>   - "host.docker.internal:host-gateway"
> ```

### Host 必须透传端口（`$http_host`，不是 `$host`）

`conf.d` 里两个 server 块都用：

```nginx
proxy_set_header Host             $http_host;   # 客户端原样的 Host，**含端口**
proxy_set_header X-Forwarded-Host $http_host;
```

**不能用 `$host`**：nginx 的 `$host` 会丢掉端口。宿主机映射到非标准端口时（`.env` 里
`NGINX_PORT=8000`）浏览器发的是 `Host: localhost:8000`，而 `$host` 把它变成 `localhost`，
于是 Django 的 `request.get_host()` 得到 `localhost` —— Django 4+ 的 CSRF **Origin 校验**
只认「当前 host」与 `CSRF_TRUSTED_ORIGINS`，而浏览器的 `Origin` 是 `http://localhost:8000`，
登录后台就会 403：

```
Forbidden (Origin checking failed - http://localhost:8000 does not match any trusted origins.): /admin/login/
```

实测对照（同一个请求，只换 Host）：

| 发给 nginx 的 Host | Django 看到的 host | 结果 |
|---|---|---|
| `localhost:8000` | `localhost:8000` | Origin 校验**通过**，失败原因变成「CSRF cookie not set」（curl 没带 cookie） |
| `localhost`（即 `$host` 的行为） | `localhost` | `Origin checking failed - http://localhost:8000 ...` |

所以**端口必须原样传下去**，不要用 `$host`。端口映射本身不需要改：`NGINX_PORT` 想用
多少都行。

例外情况：如果外层还有一层 LB / 网关会改写 Host，或者 TLS 在外层终结、Django 看到的
来源与浏览器不一致，那就不是 nginx 一个文件能解决的——用环境变量显式声明公网来源：

```
# .env（值必须带 scheme，含 :// 与端口，必须用单引号）
DJANGO_CSRF_TRUSTED_ORIGINS='https://netops.example.com,http://localhost:8000'
```

契约由 `tests/deploy/test_reverse_proxy_config.py` 守。

### 启用 HTTPS（可选）

```bash
# 1. 生成自签证书（本地开发）
bash nginx/gen-self-signed-cert.sh

# 2. 启用 HTTPS 配置
mv nginx/conf.d/netops-ssl.conf.disabled nginx/conf.d/netops-ssl.conf

# 3. 重载
docker compose restart nginx
```

访问 <https://localhost>（端口可用 `NGINX_SSL_PORT` 覆盖）。
浏览器会提示自签证书不受信任，属正常现象。生产环境请替换为正式证书。

> HTTPS 配置目前只做反向代理，不做静态直出（静态由 80 端口的 server 处理）。
> 若生产上只暴露 443，需要把 `netops.conf` 里的静态 `location` 一并复制过去。

## 静态资源策略

| 路径 | 处理方式 | 缓存 |
|------|---------|------|
| `/assets/*` | nginx 直出（Vue 产物） | `public, max-age=31536000, immutable` |
| `/static/*` | nginx 直出（collectstatic 产物） | `public, max-age=2592000`（30 天） |
| `/index.html` | nginx 直出 | `no-cache, no-store, must-revalidate` |
| `/api/*` | 代理到 app | — |
| `/admin/*`、`/media/*` | 代理到 app | — |
| 其它路径 | SPA 兜底 → `index.html` | — |

已启用 gzip（`text/*`、`application/javascript`、`application/json`、`image/svg+xml`、字体等）。

### 为什么 index.html 不缓存，assets 长期缓存？

Vite 构建产物的文件名带内容 hash（如 `accounts-CLRZcrUY.js`），内容变了文件名就变，因此可以安全地长期缓存；而 `index.html` 引用了这些文件名，必须不缓存才能让发版立即生效。

## 可配置的环境变量

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `NGINX_PORT` | `80` | HTTP 映射端口 |
| `NGINX_SSL_PORT` | `443` | HTTPS 映射端口 |

app 容器的 gunicorn 可调参数走 `GUNICORN_*` 环境变量（`env/gunicorn.env` 由 compose 的
`env_file` 注入 app 容器 → `docker/entrypoint.sh` 的 shell 插值，见文末「说明」），
不在这里读。

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

# 确认静态产物已经同步进卷
docker compose exec nginx ls /usr/share/nginx/html
docker compose exec nginx ls /usr/share/nginx/html/static | head
```

## 发版流程

```bash
# 1. 宿主机重新构建静态成品
cd frontend && pnpm build && cd ..
uv run python manage.py collectstatic --noinput

# 2. 重建 app/worker/nginx（镜像里换成新成品，容器启动时同步进卷）
docker compose up -d --build app worker nginx

# 有数据库变更时（app 容器下一次启动会自己按需迁移，这条只是不想等重启时的做法）
docker compose run --rm app python manage.py migrate
```

app 容器启动时会把新产物同步进那个静态卷，nginx 无需重启即可读到
（`index.html` 不缓存，`assets` 文件名带内容 hash）。

## 说明

- **上传大小**：`100m`，用于设备 Excel 导入。
- **超时**：`proxy_read_timeout 300s`，因路径追踪、配置解析等操作较慢。
- **关闭缓冲**：`/api/` 关闭 `proxy_buffering`，便于流式响应。
- **gunicorn 调参**：常用参数（`GUNICORN_WORKERS` / `GUNICORN_TIMEOUT` / `GUNICORN_KEEP_ALIVE` / `GUNICORN_MAX_REQUESTS` / `GUNICORN_LOG_LEVEL` …）在 `env/gunicorn.env` 里设，compose 的 app 服务把 `env/gunicorn.env`（连同 `env/app.env`）经 `env_file` 注入容器（同名时 `environment:` 优先），`docker/entrypoint.sh` 再用 shell 插值（`${GUNICORN_WORKERS:-1}` 等，默认值就写在那一份）拼出整条 gunicorn 命令，改完 `docker compose up -d app` 生效（不必重建镜像，compose 里也没有 command 要改）。一次性临时调参仍可覆盖：`docker compose run --rm app --workers 4`（追加在默认命令之后，gunicorn 对同名选项是后者胜）；传整条命令则原样执行。**`--bind` 没有环境变量、也不在这里覆盖**：它与本目录 `conf.d` 里的 upstream（现在是 `app:8000`）耦合，改端口必须同步改 nginx 配置；而且 gunicorn 的 `--bind` 是 append 语义，追加一个只会多一个监听、覆盖不掉。要换地址就整条命令替换。
- **同一个镜像的三种用法**：不传参（或只给 `-` 开头的参数）= web；`entrypoint: ["celery"]` + `command:` 放参数 = worker（刻意跳过铺静态产物那一步，worker 不挂 `static_data`）；`docker compose run --rm app python manage.py migrate` = 一次性容器。

## 排查

| 现象 | 原因与处理 |
|------|-----------|
| 首页 404 / 空白 | 静态卷为空：`docker compose up -d --build app` 重建并同步；或看 app 日志里 entrypoint 是否报错 |
| admin 后台无样式 | 卷里 `static/` 没拿到产物，同上 |
| 页面还是旧版本 | 两步都要做：宿主机 `pnpm build` 重新构建成品，再 `docker compose up -d --build app`（产物是 COPY 进镜像的，少了前一步镜像里就是旧文件） |
| `502 Bad Gateway` | app 容器没起来或未通过健康检查：`docker compose ps`、`docker compose logs app` |
| 后台登录 403 `Origin checking failed - http://localhost:8000 ...` | nginx 把端口丢了（用了 `$host`）：Host 必须是 `$http_host`，见上文「Host 必须透传端口」 |
| 重建 app 后一直 502 | 说明 upstream 被写回了 `upstream` 块（启动时只解析一次）；本配置用变量形式可避免，检查是否被改回 |
| 接口返回 html 而非 JSON | 请求被 SPA 兜底，检查 location 匹配顺序 |
| 修改配置未生效 | 执行 `docker compose exec nginx nginx -s reload` |
| HTTPS 启动失败 | 证书缺失，运行 `bash nginx/gen-self-signed-cert.sh` |
