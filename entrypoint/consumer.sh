#!/bin/sh
# consumer 容器入口：启动访问流消费者（唯一启动命令，无可调参数）。
# AccessFlow 的唯一写者，全机只能跑一个实例；见 handbook/analysis.md。

set -e

# 心跳键 access_flow:heartbeat 由消费循环每轮盖章，TTL 300s
exec python manage.py access_flow_consumer "$@"
