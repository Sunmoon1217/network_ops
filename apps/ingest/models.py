"""运维操作层（数据采集与解析入库）的模型。

这里原本只有访问流（AccessFlow）——它是策略展开的派生/分析产物，不进配置解析入库
管道（唯一写入口是 access_flow_consumer 单写者），2026-09 随域拆分迁往
``analysis.models.AccessFlow``；本模块不再有模型。

迁移历史仍留在本 app 的 label（``operator``）：0002/0004 是 AccessFlow 的建表与加键，
0005 只从 state 摘除（表由 analysis.0002 RENAME 接管），别改写。
"""
