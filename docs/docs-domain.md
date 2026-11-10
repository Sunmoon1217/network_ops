# docs 业务域：文档转换与 Dify 推送

> `apps/docs/` 是**功能域**（表格编辑 + 文档转换 + 推 Dify），与项目根的 `docs/`
> 说明目录无关，名字撞车纯属巧合。

## 转换规则（`convert.py` 的 `convert()` 唯一入口）

| 输入 | 产物 |
|------|------|
| `txt` | md（UTF-8 / GB18030 自适应解码） |
| `md` | md；引用的本地图片随附上传后内嵌 → 自包含 html |
| `docx` | md；含内嵌图片 → 自包含 html（base64 内嵌） |
| `html` / `htm` | html（本地图片引用随附上传后 base64 内嵌；无图原样保留） |
| `xlsx` | md（每 sheet：网格表 + 行式键值「行记录」双写） |
| `csv` | md（网格表 + 行式键值「行记录」双写） |
| `pdf` | 直传（不转换；Dify 原生解析保留版式与图片） |

**「有图 → html」的由来**：Dify 知识库 `document/create-by-file` **一次只收一个文件**
（多文件报 `too_many_files`），图片不能和 md 分开上传——所以含图文档统一转成
**base64 内嵌的自包含 html** 作为单文件推送。

**表格为什么双写**：Dify 的分段是「分隔符 + max_tokens」机械切分、不认表格结构
（社区有 content-aware chunker 专门绕这一点）——大表网格会被拦腰切、表头留在上一个
chunk，行碎片 `| 甲 | 1 |` 缺列名语义，向量/关键词检索都吃亏。「行记录」段落每行自带
「列名：值」、天然抗分段切断；网格表保留给人看与编辑。

**本地图片引用**（相对路径或裸文件名）必须随附上传（接口的 `attachments` 字段）：
引用全部能解析到 → 内嵌；解析不到 → **转换报错**，不静默产出缺图的文档。
`http(s)` / `data:` 远程引用不内嵌、原样保留。

两个实现级注意点：

- xlsx 走 `parse_xlsx` 而不是裸调 openpyxl：它带「样式表损坏免疫」（降级跳过样式、
  自扫 `numFmt` 保日期）与合并单元格填充——裸调会在坏 `styles.xml` 上整个判死
  （`TypeError: expected <class 'openpyxl.styles.fills.Fill'>`）；
- `parse_xlsx` 内部**短暂替换 openpyxl 的样式入口、用完即还原**（并发上传的最坏情况
  只是另一请求拿到同款宽松样式解析，值不受影响）。

## 管道（`api/documents.py`）

三步走，每步独立接口，产物全程留档在库、版本可回滚：

1. `POST /api/docs/documents/` 上传转换——主文档 + 可选图片附件
   （multipart：`file` + `attachments`），落 `converted` 状态与 v1 版本快照
   （转换失败直接 400，不落记录）；
2. 修改：`PUT /api/docs/documents/<id>/` 编辑转换产物文本，或
   `POST /api/docs/documents/<id>/reconvert/` 替换源文件重新转换——都落新版本快照
   （`DocumentRevision`），已推送文档标记 `pending_sync` 等待重推；
3. `POST /api/docs/documents/<id>/push/` 推送 Dify：未推送走 create
   （md/html 用 `create_by_text`、pdf 用 `create-by-file`）；已推送且有待同步修改走
   **update 原地更新**（`update_by-text` / `update-by-file`），不产生重复文档。

另有查看与历史：`/download/` 源文件下载、`/revisions/` 版本列表 / 快照详情 / 回滚
（恢复以新版本落地）。pdf 源文件直传不转换、无产物可编辑——改内容只能替换源文件重新转换。
权限走全局默认 `IsOperatorOrReadOnly`：读任何已认证用户可用，写（上传 / 编辑 / 重转 /
推送 / 回滚 / 删除）限操作员。

推送失败的处理：知识库里仍是旧版（文档还在），所以**只记错误、保持 `pending_sync`**
等重试，不回滚本地状态。
