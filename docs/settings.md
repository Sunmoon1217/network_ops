# settings 分层与环境变量

`DJANGO_SETTINGS_MODULE` 恒为 `netops.settings`（包），环境旋钮只有 **`DJANGO_ENV`**：
`dev`（默认，不设即此）/ `container` / `prod`，**未知值拒绝启动**（拼错如 `prd` 不静默落 dev）。

## 分层依据

1. **可被环境变量影响的配置只在 `base.py` 定义一遍**。环境变量本身就是环境区分机制：
   同一个 `os.environ.get` / `_env_list` 写一遍，靠各环境注入不同的值即可，
   不需要每个环境文件重写一遍读取逻辑。
2. **环境文件只放「不走环境变量、但必须按环境硬改」的东西**：
   - `dev.py`：空壳，base 即 dev 语义；
   - `container.py`：两条 host 必填守卫；
   - `prod.py`：`DEBUG=False` 硬覆盖 + 5 项必填守卫。
3. **覆盖顺序**：`from .base import *` 在前、`from .<env> import *` 在后，
   所以环境文件的少数硬差异（含「守卫即 import 副作用」）胜出。
4. **防循环导入硬规矩**：`base.py` 与三个环境文件只允许 `from .base import ...`、
   标准库与 Django 的 import；**禁止** `from netops.settings import ...` / `from . import ...`
   ——反向依赖父包执行结果会在 `__init__` 半初始化时炸（`ModuleNotFoundError` /
   `ImportError: cannot import name`；`BASE_DIR` 那次事故就是这个形态）。

包入口 `netops/settings/__init__.py` 另做两件事：把 `_env_list` / `_env_or_file` 显式补导出
（`import *` 不带下划线名字，而 `tests/deploy` 直接用 `netops.settings._env_or_file`）；
把 `BASE_DIR` 与 `apps/` 插进 `sys.path`（根下 `llmtools`、`apps/` 下的 `core/ingest/...`
以顶层包出现，不依赖 CWD）。

## 凭据链

统一为 **`<NAME>_FILE` > 同名环境变量 > 默认值**，实现在 `base._env_or_file`：

- `*_FILE` 指向的文件优先（Docker secrets 在 compose 下就是 `/run/secrets/<name>` 文件）；
- 文件存在但读不出来时**直接报错**，不静默回退到默认密码——那只会把「密钥配错了」
  伪装成「数据库连不上」；
- 内容 `strip()`，与 postgres 官方 entrypoint 的 `$(cat file)` 行为一致（否则末尾换行
  会变成密码的一部分）；
- **使用约定**：`*_FILE` 只在容器里设置（`env/app.env`）。宿主机直跑不设 `*_FILE`，
  自然走同名环境变量层——三个环境的链路统一，不分叉。

## 环境变量全表（Django 侧）

「谁注入」一列只说明常规来源；容器里的注入文件与插值规则见 `env/README.md`。

### Django 自身

| 变量 | 默认 | 说明 |
|------|------|------|
| `DJANGO_SECRET_KEY` | 内置开发期密钥 | 生产必须注入（`prod.py` 查原始值，不吃 fallback） |
| `DJANGO_DEBUG` | `1` | `0/false/no` 收紧；prod 硬覆盖为 `False`，此变量无效 |
| `DJANGO_ALLOWED_HOSTS` | `*` | 逗号分隔；nginx 用 `proxy_set_header Host $http_host` 透传原样 Host（含端口），Django 校验时剥端口再比对，所以必须放行；prod 必填且不许 `*` |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | 空 | 正常拓扑留空（Origin 天然等于当前 host）。只在「浏览器看到的来源 ≠ 转给 Django 的 Host」时才需要（外层 LB 改写 Host、TLS 提前终结）；值带 scheme，逗号分隔 |

### 数据库 / Redis

| 变量 | 默认 | 说明 |
|------|------|------|
| `POSTGRES_DB` | `netops` | 库名 |
| `POSTGRES_USER` / `POSTGRES_USER_FILE` | `netops` | 走凭据链 |
| `POSTGRES_PASSWORD` / `POSTGRES_PASSWORD_FILE` | `netops_password` | 走凭据链；prod 必须给出其一 |
| `POSTGRES_HOST` | `localhost` | 容器注入 `db`；container / prod 必填 |
| `POSTGRES_PORT` | `5432` | 容器内固定 5432 |
| `REDIS_HOST` | `localhost` | 容器注入 `redis`；container / prod 必填 |
| `REDIS_PORT` / `REDIS_DB` | `6379` / `0` | |
| `REDIS_PASSWORD` | 空 | 非空时拼进 `REDIS_URL`；redis 官方镜像没有 `*_FILE` 机制，密码只走环境变量 |

`CELERY_BROKER_URL` 与 `CELERY_RESULT_BACKEND` 都等于 `REDIS_URL`。

### 访问流（AccessFlow）链路

| 变量 | 默认 | 说明 |
|------|------|------|
| `ACCESS_FLOW_MAX_QUEUE` | `500` | 背压阈值，口径是 Stream **未投递积压**（`XINFO GROUPS` 的 lag，不是 XLEN）。取值理由与事故复盘见 [`analysis.md`](analysis.md) |
| `ACCESS_FLOW_DISPATCH` | `1` | 投递总开关；测试里 conftest 统一置 False，避免保存策略就往真实 Redis 发消息 |
| `ACCESS_FLOW_TASK` | `analysis.rebuild_access_flows` | 任务名的**唯一定义处**：装饰器 `name=` 与 `CELERY_TASK_ROUTES` 的 key 必须与之一致，`tests/analysis/test_access_flow_task.py` 对账 |

### 阿里云

一朵云、两个资源集（生产/测试），两套账号，共用 region；各产品 endpoint 不同，分别传参。
凭据链路同其他凭据（`*_FILE` > 环境变量 > 空）。

| 变量 | 说明 |
|------|------|
| `ALIYUN_REGION` | 区域，例 `cn-hangzhou`（两个账号共用） |
| `ALIYUN_ECS_ENDPOINT` | ECS endpoint |
| `ALIYUN_VPC_ENDPOINT` | VPC（含 VSwitch）endpoint |
| `ALIYUN_SLB_ENDPOINT` | SLB endpoint |
| `ALIYUN_SLS_ENDPOINT` | SLS endpoint |
| `ALIYUN_ASAPI_ENDPOINT` | ASAPI endpoint |
| `ALIYUN_PROD_ACCESS_KEY_ID` / `..._SECRET` | 生产账号 AK |
| `ALIYUN_TEST_ACCESS_KEY_ID` / `..._SECRET` | 测试账号 AK |

### Dify 知识库（`apps/docs` 文档转换的推送目标）

| 变量 | 默认 | 说明 |
|------|------|------|
| `DIFY_API_BASE_URL` | 空 | 知识库 API 地址（含 `/v1`），如 `https://dify.example.com/v1` |
| `DIFY_API_KEY` / `DIFY_API_KEY_FILE` | 空 | Bearer 认证，走凭据链 |
| `DIFY_DATASET_ID` | 空 | 目标知识库（dataset）ID |
| `DIFY_INDEXING_TECHNIQUE` | `high_quality` | 或 `economy` |
| `DIFY_TIMEOUT` | `30` | HTTP 超时秒数 |
| `DIFY_PROCESS_MODE` | `automatic` | 分段模式，或 `custom` |
| `DIFY_SEGMENT_SEPARATOR` | `\n` | custom 模式的分段分隔符（`\n` / `\t` 转义会被还原） |
| `DIFY_SEGMENT_MAX_TOKENS` | `500` | custom 模式的分段 token 上限 |

前三项（`base_url` / `api_key` / `dataset_id`）齐备才启用推送；缺失时推送接口返回 503，
转换与留档不受影响。

## 守卫矩阵（什么时候拒绝启动）

| 环境 | 硬覆盖 | 守卫（缺即 `ImproperlyConfigured`） |
|------|--------|-----------------------------------|
| `dev` | 无 | 无 |
| `container` | 无 | `POSTGRES_HOST`、`REDIS_HOST` 必须由 `env/app.env` 注入 |
| `prod` | `DEBUG = False` | `DJANGO_SECRET_KEY`、`DJANGO_ALLOWED_HOSTS`（非空且不含 `*`）、`POSTGRES_HOST`、`POSTGRES_PASSWORD(_FILE)`、`REDIS_HOST` |

两条设计取舍：

- **container 守卫存在的理由是「发现得早」**：base 里 `HOST` 默认 `localhost`，
  而 Django 的数据库连接是惰性的——env_file 少一行不会在启动时报错，要到首个请求才
  `connection refused`，故障发现晚一拍。守卫让它启动即拒。
- **守卫一次报全**：缺几个就一条消息列出几个，不做「修一个、再启动、又缺一个」的挤牙膏式失败。

守卫与分发矩阵由 `tests/deploy/test_settings_environments.py` 守。
