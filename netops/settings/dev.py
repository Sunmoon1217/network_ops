"""开发环境（宿主直跑）：无覆盖——base 就是本环境的语义，DJANGO_ENV 不设即分发到这里。

宿主机直跑不使用 *_FILE（那是容器 secrets 的机制）：base 会 load_dotenv 补进
envs/common.env + envs/host.env，共享值改 common.env 一处即可。
"""
