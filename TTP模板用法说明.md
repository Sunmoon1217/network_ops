# TTP函数说明
## 🔸 一、Action Functions（动作函数）

用于**转换、赋值、记录或处理匹配结果**。

| 函数 | 作用 | 用法示例 |
|------|------|--------|
| `append(string)` | 在匹配结果末尾追加字符串 | `{{ name \| append(" - active") }}` → `"Gi0/1 - active"` |
| `chain(var_name)` | 调用预定义的函数链（避免重复写长管道） | `<vars> f = "split(',') \| join(':')"</vars> {{ vlans \| chain('f') }}` |
| `copy(var_name)` | 将当前匹配值复制到另一个变量 | `{{ ip \| copy("original_ip") }}` |
| `count(var=..., globvar=...)` | 对匹配计数（支持 per-input 和全局计数器） | `{{ up \| equal("up") \| count(globvar="total_up") }}` |
| `default(value)` | 若无匹配，使用默认值 | `{{ ip \| default("N/A") }}` |
| `dns(...)` | 对匹配的域名执行 DNS 正向解析（需 dnspython） | `{{ host \| dns(record='A') }}` → `["1.2.3.4"]` |
| `geoip_lookup(db, add_field="geoip")` | 使用 GeoIP2 数据库查询 IP 地理信息（需 geoip2） | `{{ ip \| geoip_lookup("db.citY") }}` |
| `gpvlookup(name, ...)` | 使用 Glob 模式字典进行分类查找 | `{{ hostname \| gpvlookup("domains", add_field="domain") }}` |
| `ip_info` | 返回 IP 地址/接口的详细信息字典（基于 ipaddress） | `{{ ip \| to_ip \| ip_info }}` |
| `item(index)` | 获取列表/字符串中指定索引的元素 | `{{ list \| item(0) }}` 或 `{{ word \| item(-1) }}` |
| `join(char)` | 对**单个匹配结果**（如列表）用字符连接 | `{{ items \| split() \| join(",") }}` |
| `joinmatches(char='\n')` | **跨多行匹配**，将多次匹配结果合并为一个字符串/列表 | `{{ vlan \| joinmatches(",") }}` |
| `let(value)` 或 `let(var, value)` | 静态赋值（替换匹配结果或创建新字段） | `{{ desc \| let("unknown") }}` |
| `lookup(name, ...)` | 在 lookup 表中查找匹配值并返回（支持 CSV/INI/Python） | `{{ asn \| lookup("ASNs", add_field="info") }}` |
| `mac_eui` | 标准化 MAC 地址格式为 `aa:bb:cc:dd:ee:ff` | `{{ mac \| mac_eui }}` → `"aa:bb:cc:dd:ee:ff"` |
| `macro(name)` | 调用自定义 Python 宏函数处理匹配结果 | `{{ interface \| macro("classify_intf") }}` |
| `prepend(string)` | 在匹配结果开头插入字符串 | `{{ name \| prepend("IF-") }}` → `"IF-Gi0/1"` |
| `print` | 打印当前匹配值（用于调试） | `{{ data \| split() \| print }}` |
| `raise("msg")` | 抛出 RuntimeError（用于中断解析） | `{{ error_line \| raise("Invalid config!") }}` |
| `rdns(...)` | 对 IP 执行反向 DNS 查询（需 dnspython） | `{{ ip \| rdns() }}` → `"dns.google"` |
| `record(var_name)` | 将匹配结果存入模板变量（可被 `set` 引用） | `{{ vrf \| record("VRF") }}` |
| `replaceall(...)` | 批量字符串替换（支持变量、列表、字典） | `{{ intf \| replaceall('Ge', 'GigabitEthernet', 'TenGig') }}` |
| `resub(old, new, count=1)` | 单次正则替换 | `{{ intf \| resub("^GigabitEthernet", "Ge") }}` |
| `resuball(...)` | 批量正则替换（类似 `replaceall` 但用 re.sub） | `{{ intf \| resuball({'Ge': ['^Gigabit']}) }}` |
| `rlookup(name, ...)` | 在 lookup 表中**搜索 key 是否出现在匹配值中** | `{{ desc \| rlookup("locations", add_field="city") }}` |
| `set(value)` | **条件性赋值**：若该行匹配，则设字段为 value（value 可是变量名） | `shutdown {{ disabled \| set(true) }}` |
| `sformat(fmt)` | 使用 Python `.format()` 格式化字符串 | `{{ ip \| sformat("IP: {}") }}` |
| `to_cidr` | 将子网掩码（如 `255.255.255.0`）转为 CIDR（`24`） | `{{ mask \| to_cidr }}` |
| `to_float` | 转为浮点数 | `{{ "3.14" \| to_float }}` → `3.14` |
| `to_int` | 转为整数 | `{{ "42" \| to_int }}` → `42` |
| `to_ip` | 转为 `ipaddress.IPv4Address/Interface` 对象 | `{{ "192.168.1.1/24" \| to_ip }}` |
| `to_list` | 将匹配结果转为单元素列表 | `{{ ip \| to_list }}` → `["192.168.1.1"]` |
| `to_net` | 转为 `ipaddress.IPv4Network` 对象 | `{{ "192.168.0.0/24" \| to_net }}` |
| `to_str` | 转为字符串 | `{{ 123 \| to_str }}` → `"123"` |
| `to_unicode` | （Python 2）转为 Unicode 字符串 | `{{ "abc" \| to_unicode }}` |
| `truncate(count)` | 截断为前 N 个单词 | `{{ "a b c d" \| truncate(2) }}` → `"a b"` |
| `unrange(rangechar='-', joinchar=',')` | 展开数字范围（如 `100-102` → `100,101,102`） | `{{ "10,20-22" \| unrange() }}` → `"10,20,21,22"` |
| `uptimeparse(format="seconds\|dict")` | 解析 uptime 字符串为秒数或字典 | `{{ "2 hours, 5 mins" \| uptimeparse() }}` → `7500` |
| `void` | **使匹配无效**（返回 False，用于过滤） | `{{ unwanted \| void }}` |

---

## 🔸 二、Condition Functions（条件函数）

用于**验证匹配结果**，返回 `True/False`，常用于过滤。

| 函数 | 作用 | 用法示例 |
|------|------|--------|
| `equal(value)` | 判断是否等于某值 | `{{ state \| equal("up") }}` |
| `notequal(value)` | 判断是否不等于某值 | `{{ type \| notequal("Loopback") }}` |
| `startswith_re(pattern)` | 正则判断是否以某模式开头 | `{{ line \| startswith_re("^interface") }}` |
| `endswith_re(pattern)` | 正则判断是否以某模式结尾 | `{{ line \| endswith_re("shutdown$") }}` |
| `contains_re(pattern)` | 正则判断是否包含某模式 | `{{ desc \| contains_re("core.*router") }}` |
| `contains(pattern1, pattern2, ...)` | 判断是否包含任一字符串 | `{{ intf \| contains("Vlan", "Loopback") }}` |
| `notstartswith_re(pattern)` | 不以某正则开头 | — |
| `notendswith_re(pattern)` | 不以某正则结尾 | — |
| `exclude_re(pattern)` | 不包含某正则 | — |
| `exclude(pattern)` | 不包含某字符串 | `{{ intf \| exclude("Tunnel") }}` |
| `isdigit` | 判断是否为纯数字字符串 | `{{ vlan \| isdigit }}` |
| `notdigit` | 判断是否非数字 | — |
| `greaterthan(value)` | 数值比较（大于） | `{{ age \| greaterthan("100") }}` |
| `lessthan(value)` | 数值比较（小于） | `{{ metric \| lessthan("10") }}` |
| `is_ip` | 判断是否为合法 IP（地址或接口） | `{{ addr \| is_ip }}` |
| `cidr_match(prefix)` | 判断 IP 是否属于某网段 | `{{ ip \| cidr_match("192.168.0.0/16") }}` |

> ⚠️ 条件函数通常用在 **group 的起始行**（`_start_` 行），若返回 `False`，整个 group 匹配会被丢弃。

---

## 🔸 三、特殊伪变量（Indicators）

这些不是函数，而是控制解析行为的**特殊标记**：

| 伪变量 | 作用 |
|-------|------|
| `_start_` | 显式标记 group 的开始行 |
| `_end_` | 标记 group 结束行（如 `!{{ _end_ }}`） |
| `_exact_` | 启用**整行精确匹配**（禁用数字泛化等） |
| `_exact_space_` | 启用**空格精确匹配**（禁用 `\s+` 泛化） |
| `_headers_` | 基于表头自动解析固定宽度表格 |
| `_line_` | 匹配整行原始内容（高级用法） |

---

## 🔸 四、使用建议

1. **组合使用**：函数可链式调用，如  
   `{{ trunk_vlans \| unrange() \| split(',') \| join(':') }}`
2. **避免过度匹配**：对关键字（如 `ipv4` vs `ipv6`）使用 `_exact_`
3. **表格解析**：优先用 `_headers_` 处理对齐输出
4. **调试技巧**：用 `print` 查看中间结果
5. **性能优化**：用 `chain` 管理复杂函数链

---

> 📌 **注意**：所有函数均在 TTP 模板的 `{{ }}` 内使用，通过 `|` 管道连接。

你提供的文档详细介绍了 **TTP（Template Text Parser）中的正则表达式（Regex）模式与用法**。下面是对这部分内容的**系统化整理与解读**，帮助你快速掌握 TTP 如何使用内置和自定义正则进行精准解析。

---
# TTP正则表达式模式与用法说明
***
## 🔹 五、核心理念

> **TTP 的底层是正则表达式，但对用户隐藏了复杂性**。  
> 你可以通过 **`re()` 函数** 或 **内置命名模式（如 `IP`, `WORD` 等）** 显式控制匹配行为。

---

## 🔸 六、正则指定方式：`re("pattern")`

### ✅ 语法：
```ttp
{{ variable | re("pattern_name_or_value") }}
```

### 🔍 匹配顺序（TTP 自动查找）：
1. **模板变量**（`<vars>` 中定义）
2. **内置命名模式**（如 `"IP"`, `"DIGIT"`）
3. **直接当作正则字符串使用**

---

### ✅ 示例 1：混合使用三种方式
```ttp
<vars>
GE_INTF = "GigabitEthernet\\S+"
</vars>

Internet  {{ ip | re("IP") }}  {{ age | re("\\d+") }}  {{ mac }}  ARPA  {{ intf | re("GE_INTF") }}
```
- `re("IP")` → 使用内置 IPv4 模式
- `re("\\d+")` → 直接写正则（注意转义）
- `re("GE_INTF")` → 引用 `<vars>` 中的自定义正则

> 💡 最终生成的正则会自动处理空格泛化（`\ +`）、命名捕获组等。

---

### ⚠️ 重要限制：**不能在 `re()` 内直接写 `|` 分支**
```ttp
❌ {{ intf | re("GigabitEthernet\\S+|Fast\\S+") }}  // 不支持！
```

### ✅ 解决方案：
#### 方案 A：通过 `<vars>` 定义
```ttp
<vars>
INTF_RE = r"GigabitEthernet\\S+|Fast\\S+"
</vars>
{{ intf | re("INTF_RE") }}
```

#### 方案 B：链式调用多个 `re()`
```ttp
{{ intf | re(r"GigabitEthernet\\S+") | re(r"Fast\\S+") }}
```
→ TTP 会将其合并为 `(?:Gigabit...)|(?:Fast...)`

---

## 🔸 七、内置命名正则模式（Built-in Patterns）

| 模式 | 作用 | 匹配示例 | 注意事项 |
|------|------|--------|--------|
| `WORD` | 单词（无空格） | `Gi0/1`, `up` | 等价于 `\S+` |
| `PHRASE` | 多个单词（**单空格分隔**） | `Core Router` | 不支持多空格 |
| `ORPHRASE` | 单词 **或** 短语 | `Loopback0` 或 `BGP Peer - DC1` | ✅ 最适合描述字段 |
| `_line_` | 整行任意内容 | `任何文本` | 常用于调试或通配 |
| `ROW` | 表格行（多空格分隔列） | `Lo0    up    1000` | 保留原始空格 |
| `DIGIT` | 数字（含前导零） | `00123`, `42` | 等价于 `\d+` |
| `IP` | IPv4 地址 | `192.168.1.1` | ❌ **不验证合法性**（如 `999.999.1.1` 也能匹配） |
| `PREFIX` | IPv4 前缀 | `10.0.0.0/24` | 同上，需配合 `is_ip` 验证 |
| `IPV6` | IPv6 地址 | `2001::1` | ❌ 可能匹配非法格式 |
| `PREFIXV6` | IPv6 前缀 | `2001::/64` | 同上 |
| `MAC` | MAC 地址 | `aa:bb:cc:dd:ee:ff``aabb.ccdd.eeff` | 支持多种格式 |

> ✅ **验证建议**：对 `IP`/`PREFIX` 等，务必配合条件函数 `is_ip` 过滤无效结果：
> ```ttp
> {{ ip | IP | is_ip }}
> ```

---

## 🔸 八、典型应用场景

### 1. **提取接口描述（可能含空格）**
```ttp
description {{ desc | ORPHRASE }}
```
✅ 匹配：
- `description Uplink to Core`
- `description Server_VLAN`

---

### 2. **解析 ARP 表（混合接口类型）**
```ttp
<vars>
INTF_TYPES = r"(?:GigabitEthernet|FastEthernet|Loopback)\S+"
</vars>

Internet  {{ ip | IP }}  {{ age | DIGIT }}  {{ mac | MAC }}  ARPA  {{ intf | re("INTF_TYPES") }}
```

---

### 3. **提取表格行（保留列结构）**
```ttp
Interfaces: {{ _start_ }}
  {{ interfaces | ROW }}
```
→ `interfaces` 字段将包含原始行：`"Loopback101      Vlan707"`

> 若需进一步拆分为列表，可后续用 `split()`：
> ```ttp
> {{ interfaces | ROW | split() }}
> ```

---

### 4. **精确匹配 IP 并验证**
```ttp
ip address {{ ip | PREFIX | is_ip }}
```
→ 只有合法 IP/前缀才会被保留。

---

## 🔸 九、最佳实践建议

| 场景 | 推荐做法 |
|------|--------|
| **通用单词** | 用 `WORD` |
| **描述/注释字段** | 用 `ORPHRASE`（最安全） |
| **IP/MAC 地址** | 用内置模式 + `is_ip`/`mac_eui` 后处理 |
| **多选正则** | 通过 `<vars>` 定义，避免 inline `|` |
| **表格数据** | 先用 `ROW` 提取整行，再 `split()` 处理 |
| **调试** | 用 `{{ line | _line_ | print }}` 查看原始行 |

---

## ✅ 总结

| 类型 | 关键点 |
|------|------|
| **自定义正则** | 用 `re("name")`，优先定义在 `<vars>` |
| **内置模式** | `IP`, `MAC`, `ORPHRASE` 等简化常见场景 |
| **验证** | 内置模式**不验证合法性**，需配合 `is_ip` 等条件函数 |
| **灵活性** | 链式 `re()` 或 `<vars>` 解决复杂匹配 |

> 📌 **记住**：TTP 的目标是 **“用最简模板，做最准解析”** —— 合理组合内置模式与自定义正则，能极大提升效率和准确性。

如果你有具体的文本样例需要解析，我可以帮你写出最优 TTP 模板！