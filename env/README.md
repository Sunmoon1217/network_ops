# env/ —— 全部「给容器的配置」都在这里

本目录两类东西，都只进容器、不进镜像：

| 路径 | 怎么进容器 | 内容 |
|------|-----------|------|
| `*.env` | compose 的 `env_file`（环境变量） | 按服务分：`app.env` / `db.env` / `gunicorn.env` / `celery.env` |
| `secrets/*` | compose 的 `secrets`（只读文件挂到 `/run/secrets/*`） | 数据库用户名与密码；只有密钥文件被 `.gitignore` 排除，见 `secrets/README.md` |

`env_file` 一个服务只拿自己需要的：

| 文件 | 注入到 | 内容 |
|------|--------|------|
| `app.env` | app、worker | Django 运行时：数据库、Redis、`DJANGO_*` |
| `db.env` | db | `POSTGRES_DB` / `POSTGRES_USER_FILE` / `POSTGRES_PASSWORD_FILE` / `PGDATA` |
| `gunicorn.env` | app | `GUNICORN_*`（`docker/entrypoint.sh` 拼启动命令用） |
| `celery.env` | worker | `CELERY_LOGLEVEL` |

```yaml
app:
  env_file: [env/app.env, env/gunicorn.env]
worker:
  env_file: [env/app.env, env/celery.env]
db:
  env_file: [env/db.env]
```

## 与另外两类配置的分工

| 位置 | 谁读 | 放什么 |
|------|------|--------|
| `.env`（项目根） | **compose 自己**（`${VAR}` 插值） | 宿主映射端口（`NGINX_PORT` / `POSTGRES_PORT` / `REDIS_PORT`）、`BASE_IMAGE`、secrets 文件路径 |
| `env/*.env`（本目录） | **容器进程**（`env_file`） | 服务运行时读的变量（本目录各文件） |
| `env/secrets/*` | 容器进程（只读挂载 `/run/secrets/*`） | 密钥：数据库用户名、密码（只有密钥被 `.gitignore` 排除） |

三条容易踩的规则：

1. **compose 的 `${VAR}` 只读根目录的 `.env`**，不会读 `env/*.env`。所以要在 compose 文件里
   插值的变量必须留在根 `.env`；反过来，只想给容器用的变量放这里就够了。
2. 同一个变量同时出现在 `environment:` 与 `env_file` 时 **`environment` 优先**。
3. 多个 `env_file` 按顺序合并，**后面的覆盖前面的**（本目录里的文件都是互补的，正常不会撞）。

## 这些文件入库吗？

入库。它们**不含密钥**（用户名和密码在 `env/secrets/`，那里只有密钥文件被 `.gitignore` 排除），所以直接改这里
就能调整运行参数；要让某台机器单独覆盖，改这些文件或另加一个 `env_file` 即可。

改完 `docker compose up -d app worker db` 生效（改的是注入的环境变量，不需要重建镜像；
`entrypoint.sh` / `Dockerfile` 本身有改动才要 `--build`）。

## 语法提醒

这些文件与根 `.env` 用的是同一套 compose dotenv 解析规则：`$` 会做变量插值（要字面量 `$` 写
`$$`）、`#` 前面有空格就是行内注释、行尾空格会被去掉、含特殊字符的值用单引号。
