"""开发环境（宿主直跑）：**无覆盖**——base 就是本环境的语义。

所有可被环境变量影响的配置统一定义在 base（env 动态 + 开发期默认值：localhost、
DEBUG 默认开、HOSTS 默认 `*`），dev 不需要额外文件参与；`DJANGO_ENV` 不设即分发到本文件。

凭据链路与容器统一（`*_FILE > 同名环境变量 > 默认值`，见 base._env_or_file）；
**操作约定**：宿主机直跑不使用 `*_FILE`——按 .env.example 指南只 export 环境变量，
不设 *_FILE 即走环境变量层。
"""
