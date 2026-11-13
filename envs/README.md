# envs/ —— 全部「环境配置」都在这里：**一套文件，两种部署共用**

直接部署（宿主直跑 `uv run manage.py …`）与 compose 部署读**同一套**文件：
共享值只写一份（`common.env`），部署差异各留一个几乎恒定的小文件。改常规配置只动
`common.env`，两边同时生效，不存在「宿主一份、容器一份」的漂移。

## 分层

| 文件 | 层 | 谁加载 | 放什么 |
|------|----|--------|--------|
| `common.env` | **共享层** | 容器：compose `env_file`；宿主：`settings/base.py` 启动时 `load_dotenv` | 两种部署**完全一致**的值（`DB_ENGINE` 给宿主直跑、Redis、`DJANGO_*`、阿里云/Dify/Zabbix 非密钥项）——日常维护的主要文件 |
| `container.env` | 容器差异层 | compose `env_file`（排在**最后**，只给四个应用进程） | 只在容器成立的东西：`REDIS_HOST=redis`、阿里云 `*_FILE`、`CONFIG_REPO_PATH=/configs`、`DJANGO_ENV=container`、`MIGRATE_ON_START` |
| `db.env` | **数据库连接层** | compose `env_file`（四个应用进程 + db 容器） | 一套 `DB_*`（引擎/库名/用户/凭据文件路径），再用 `${}` **嵌套**成镜像认的 `POSTGRES_*` / `MYSQL_*`；改库名/用户只改这里与根 `.env` |
| `host.env` | 宿主差异层 | `base.py` 启动时 `load_dotenv`（`DJANGO_ENV ≠ container` 时） | 只在宿主成立的东西：`DB_HOST=127.0.0.1` / `REDIS_HOST=127.0.0.1`（**不写 localhost**：Windows 上会先试 `::1`、每次连接白等约 10s）；可选：把 `*_FILE` 指到 `envs/secrets/*` 与容器共用同一份密钥（相对路径按 `BASE_DIR` 解析） |
| `gunicorn.env` / `celery.env` | 服务层 | compose `env_file`（只给对应服务） | 每个服务自己的旋钮，与部署方式无关 |
| `secrets/*` | 密钥 | 容器：`secrets` 挂载 `/run/secrets/*`；宿主：经 `host.env` 的相对 `*_FILE` | 数据库/阿里云凭据；只有密钥被 `.gitignore` 排除，见 `secrets/README.md` |

`common.env` / `container.env` / `host.env` 的注入组合（compose.yml）：

```yaml
db:            # 两个后端模板都是这一行
  env_file: [envs/db.env]
app:
  env_file: [envs/common.env, envs/gunicorn.env, envs/db.env, envs/container.env]
worker:
  env_file: [envs/common.env, envs/celery.env, envs/db.env, envs/container.env]
consumer:
  env_file: [envs/common.env, envs/db.env, envs/container.env]
beat:
  env_file: [envs/common.env, envs/celery.env, envs/db.env, envs/container.env]
```

## 加载与优先级（宿主侧）

`netops/settings/base.py` import 时：

1. `NETOPS_SKIP_DOTENV=1` → 全部跳过（tests/deploy 用它拿到纯净默认值，不吃本机 envs/ 实例）；
2. `load_dotenv(envs/common.env)`；
3. `DJANGO_ENV ≠ container` 时再 `load_dotenv(envs/host.env)`——容器里代码卷也带着
   `envs/`，不区分会把宿主值（`DB_HOST=127.0.0.1` 等）泄进容器。

`load_dotenv` 全程 `override=False`：**真实进程环境永远优先**（compose 注入的值、手工
`export` 的值都赢过文件），文件只是兜底——想临时覆盖某个值，直接 export 即可，不用改文件。

## 密钥：一份文件，两种部署

凭据链 `*_FILE > 同名环境变量 > 默认值` 统一在 `settings/base.py`：

- 容器：`container.env` 给绝对路径 `/run/secrets/*`（compose 挂载）；
- 宿主：默认不设 `*_FILE`、走同名环境变量或 base 默认值（开发语义）；取消 `host.env`
  里对应注释行即可与容器**共用同一份** `envs/secrets/*`——相对路径（如
  `envs/secrets/db_user`）由 `base.py` 按 `BASE_DIR` 解析。

## `MIGRATE_ON_START` 与初始管理员

`container.env` 里的 `MIGRATE_ON_START=1`（默认）让 app 容器启动时**按需**跑数据库迁移：
只在确实有未应用的迁移时才执行 `migrate --noinput`，且整段「检查 + 迁移」由**数据库自带的
命名锁**串行化（PostgreSQL 用 `pg_advisory_lock`、MySQL 用 `GET_LOCK`，Django 自己不给
migrate 加锁），所以多副本同时启动不会互相竞争；其它后端直接报错，不做「静默不加锁」的
降级。设成 0 就跳过、交给外部发布流水线或人工：
`docker compose run --rm app python manage.py migrate`。实现见
`apps/core/management/commands/migrate_if_needed.py`。

**初始管理员不需要任何配置**（不占环境变量、不进 compose、不用 secret）：app 启动时调
`manage.py ensure_superuser`，只在「库里一个超级用户都没有」时创建 `admin`，把随机初始密码
**打印在启动日志里**（`docker compose logs app`），已经有超管就是空操作——不覆盖已有密码、
也不把同名普通账号静默提权。登录后请立即改密码。实现见
`apps/core/management/commands/ensure_superuser.py`。

## 与其它配置的分工

| 位置 | 谁读 | 放什么 |
|------|------|--------|
| `.env`（项目根） | **compose 自己**（`${VAR}` 插值） | 宿主映射端口（`NGINX_PORT` / `DB_PORT` / `MYSQL_HOST_PORT` / `REDIS_PORT`）、数据库后端 `DB_SERVICE`、镜像 tag、secrets 文件路径 |
| `envs/*.env`（本目录） | **容器进程**（env_file）与**宿主进程**（load_dotenv） | 上表各层 |
| `envs/secrets/*` | 容器进程（`/run/secrets/*`）与宿主进程（相对 `*_FILE`） | 密钥 |
| `conf/*.json`（项目根） | **进程直接读文件**（如 ingest 的 `link_config`） | 平台自身的结构化配置（链路清单与展示 label）；**入库、随版本走**，单值项可被同名环境变量覆盖 |

三条容易踩的规则：

1. **compose 的 `${VAR}` 只读根目录的 `.env`**，不会读 `envs/*.env`。要在 compose 文件里
   插值的变量（宿主映射端口等）必须留在根 `.env`；反过来，给进程用的变量放这里就够了。
   注意根 `.env` 的 `DB_PORT` / `MYSQL_HOST_PORT` 是**宿主映射端口**；容器内端口固定
   （PG 5432 / MySQL 3306），由 `settings/base.py` 按 `DB_ENGINE` 取默认，`common.env` 里不写。
2. 同一个变量同时出现在 `environment:` 与 `env_file` 时 **`environment` 优先**。
3. 多个 `env_file` 按顺序合并，**后面的覆盖前面的**（本目录里各层互补，正常不会撞；
   `container.env` 排最后就是利用这条保证容器差异一定生效）。
4. **同名配置的优先级**：环境变量覆盖配置文件（`env > conf/*.json > 代码默认`），与
   `load_dotenv(override=False)` 一致；只覆盖顶层单值（路径、TTL 等），数组 / 映射结构
   不做环境变量覆盖。

## 这些文件入库吗？

`envs/*.env`（`example/` 除外）**不入库**（已被 `.gitignore` 排除）——部署本地的运行配置，
不同环境/部署的值不同。入库的是 `envs/example/*.env` 模板（与实际文件同构，列全部所需变量
及注释说明）。首次部署/克隆后：

```bash
cp envs/example/*.env envs/
```

然后按实际环境修改 `envs/common.env` 的值（差异层通常不用动）；compose 的 `env_file`
与 `base.py` 指向的都是无 `.example` 后缀的实例。

`conf/*.json` 相反：**入库、随版本走**（现场值不同时走 git 提交或 env 同名覆盖），
不参与上面的 `cp envs/example/*.env envs/` 初始化。

## 语法提醒

这些文件与根 `.env` 用的是同一套 compose dotenv 解析规则：`$` 会做变量插值（要字面量 `$`
写 `$$`）、`#` 前面有空格就是行内注释、行尾空格会被去掉、含特殊字符的值用单引号。
