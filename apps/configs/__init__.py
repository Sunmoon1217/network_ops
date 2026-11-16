"""configs 域：设备配置行（ConfigBase 家族）与配置快照。

为什么单独成域：这些模型的身份是「某台设备上的一条配置行」——``(设备, 名称/编号)``，
跨设备没有独立身份，按 ``handbook/assets.md``「资产分类边界」的判据**不算资产**。
详见 ``handbook/design/assets-configs-split.md``。

依赖方向：``configs → assets``（引用 ``Device`` 外键）、``configs → core``；
assets 不反向依赖 configs。拆分进行中，尚未迁完的兄弟模型仍在 ``assets.models``。
"""
