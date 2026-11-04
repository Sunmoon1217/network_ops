#!/bin/sh
#
# consumer 容器入口：启动访问流消费者进程。
#
# 关于启动什么：
#   python manage.py access_flow_consumer 是唯一的启动命令，没有可调参数。
#     $1 以 - 开头（或没有参数）→ 视为「给默认命令的参数」，在拼好的命令后面追加
#     否则                      → 视为「整条命令」，原样执行
#
#   参数为什么全部收在这里、而不是放镜像的 CMD 里：
#     * consumer 在 compose 里被整条换成 python manage.py access_flow_consumer，
#       根本走不到 app 的 entrypoint；
#     * CMD 是 exec 形式，环境变量不会被展开（要展开得退回 shell 形式，那样又会绕过
#       「$1 以 - 开头」这套判断）；把默认值写成 shell 插值，`.env` 才能直接改参数；
#     * 环境变量在这里是**替换**语义（位置固定），不是 celery 的 CELERY_WORKER_ARGS
#       那种「追加到最后」——后者对 --concurrency 只会多出一个监听，覆盖不掉。
#   注意 CELERY_* 里的 0 与空串不同：`:-` 只对「未设置或空」取默认值，写 0 就是 0。
#
# 变量由 compose 的 env_file 注入（docker-compose.yml 的 consumer 服务把 env/app.env 注入），
# 所以在 env/app.env 里改 ACCESS_FLOW_* 即可，不必碰 compose。
#
# 关于单写者：
#   consumer 是 AccessFlow 的**唯一写者**：只能跑一个实例（消费者组会把消息摊给多个成员，
#   多一个就是多写者，「先查后合并」的前提就没了；不要靠 scale 起多份）。

set -e

# 启动访问流消费者（心跳键 access_flow:heartbeat 由消费循环每轮盖章，TTL 300s）。
#
# `-u` 不能省：stdout 接 docker logs 的管道时 Python 是**块缓冲**（约 8KB），进程活着
# 期间 self.stdout.write 的「访问流消费启动」短行一直卡在缓冲区里、docker logs 全黑，
# 只有进程退出冲刷才突然冒出来（2026-11 实测排障结论）。应急（不重建 code 镜像）可在
# env/app.env 加 PYTHONUNBUFFERED=1 等效。
# 另一半根因与这里无关：logger.info「已入库 …」走 settings.LOGGING 给项目 logger 挂的
# console handler（stderr 行缓冲）——root 无 handler 时 lastResort 只放行 WARNING，INFO
# 会被整段丢掉，日志配置见 netops/settings/base.py 的 LOGGING。
exec python -u manage.py access_flow_consumer "$@"
