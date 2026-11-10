# env/secrets/

数据库凭据放这里，走 **docker secrets**（放在 `env/` 下是为了和 `env/*.env` 这类「给容器的配置」聚在一起；
它俩的区别只在**密钥文件被 `.gitignore` 排除**，并且只读挂给需要的容器）（compose 在非 swarm 模式下就是把文件只读挂到容器内的
`/run/secrets/<name>`），不再放进 `.env`、也不再进容器环境变量——环境变量会被
`docker inspect`、`/proc/1/environ` 看到，而 secret 文件只有挂它的容器读得到。

| 文件 | 容器内路径 | 谁读 |
|------|-----------|------|
| `postgres_user` | `/run/secrets/postgres_user` | db（postgres 官方镜像的 `POSTGRES_USER_FILE`）、app / worker（`settings/base.py` 的 `_env_or_file()`） |
| `postgres_password` | `/run/secrets/postgres_password` | 同上（`POSTGRES_PASSWORD_FILE`） |

阿里云 API 凭据（生产/测试两套）：

| 文件 | 容器内路径 | 谁读 |
|------|-----------|------|
| `aliyun_prod_access_key_id` | `/run/secrets/aliyun_prod_access_key_id` | app / worker（`settings/base.py` 的 `_env_or_file()`） |
| `aliyun_prod_access_key_secret` | `/run/secrets/aliyun_prod_access_key_secret` | 同上 |
| `aliyun_test_access_key_id` | `/run/secrets/aliyun_test_access_key_id` | 同上 |
| `aliyun_test_access_key_secret` | `/run/secrets/aliyun_test_access_key_secret` | 同上 |

> 阿里云 AK/Secret **不是随机生成的**——从阿里云控制台获取后手工写入这四个文件。
> 宿主机直跑 Django 时默认走同名环境变量（`ALIYUN_PROD_ACCESS_KEY_ID` 等，export 即可）；
> 也可取消 `envs/host.env` 里对应 `*_FILE` 注释行，与容器共用同一份密钥文件。

这两个文件**不入库**（`.gitignore` 排除）、不进构建上下文（`.dockerignore` 排除）。

## 生成

```bash
bash env/secrets/generate.sh            # 沿用 .env 里的 POSTGRES_USER / POSTGRES_PASSWORD（默认）
bash env/secrets/generate.sh --random   # 生成随机强密码（**只适用于全新的数据卷**）
bash env/secrets/generate.sh --force    # 覆盖已存在的文件
```

默认沿用 `.env` 的值，是为了让**已有部署**平滑迁移：postgres 只在**首次初始化数据卷**时
应用这套凭据，之后改文件不会改库里的密码。因此：

- 已有 `postgres_data` 卷：跑默认模式（沿用 `.env` 的值）→ `docker compose up -d` 后 app 照旧能连。
- 想真正换密码：`--random` 之后要么删掉 `postgres_data` 卷重建（**数据会没**），要么进库改：
  `docker compose exec db psql -U <user> -c "ALTER USER <user> WITH PASSWORD '<新密码>';"`
- 数据卷还是空的（全新部署）：随便哪种模式都行，`--random` 更好。

## 其他

- 权限：脚本用 `umask 077` + `chmod 600`，文件默认只有当前用户可读写。
- 指向这两个文件的 `POSTGRES_USER_FILE` / `POSTGRES_PASSWORD_FILE` 写在 `envs/container.env`
  （容器差异层，db / app / worker / consumer 共用）里，值就是 `/run/secrets/*`——见 `envs/README.md`。
- 路径可改：compose 里 `secrets.*.file` 用的是 `${POSTGRES_USER_SECRET_FILE:-./envs/secrets/postgres_user}`
  这类写法，也可以指到别处（例如 `/etc/netops/secrets/...`）。
- `POSTGRES_DB`（库名）不算密钥，在 `envs/common.env` 里。
- redis 密码**没有**走 secrets：redis 官方镜像没有 `*_FILE` 机制，`REDIS_PASSWORD` 仍是
  环境变量（留空即不启用）。
- 宿主机直跑 Django 时默认不用 secrets：读取链路统一在 `settings/base.py`
  （`*_FILE > 同名环境变量 > 默认值`）——`export POSTGRES_PASSWORD=<值>` 即可。
  想与容器**共用同一份密钥文件**，取消 `envs/host.env` 里 `*_FILE` 的注释行
  （相对路径按 `BASE_DIR` 解析，见 `envs/README.md`「密钥」一节）。
