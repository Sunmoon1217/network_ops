# Network Ops

网络运维管理平台 — Django REST 后端 + Vue 3 前端

## 功能模块

| 模块 | 路由 | 功能 |
|------|------|------|
| **总览** | `/` | 全局统计仪表盘（ECharts 图表） |
| **设备管理** | `/devices` | 设备列表、接口管理、基线管理（SNMP/NTP/Syslog）、解析器模板、配置对比 |
| **配置管理** | `/config` | 负载均衡（SLB/GSLB）、域名解析、NAT 管理、路由表、ARP/MAC、访问策略 |
| **IP 管理** | `/ipam` | 子网、IP 地址、标签管理 |
| **工具** | `/tools` | 路径追踪（防火墙策略匹配 + NAT + 路由 + 负载均衡）、机柜可视化（U 位视图） |

## 技术栈

**后端**
- Python 3.12+ / Django 5 / DRF
- Celery 异步任务（采集→解析→存储）
- Napalm / Netmiko 网络设备采集
- TTP 模板解析

**前端**
- Vue 3 + TypeScript + Vite
- Element Plus UI
- ECharts / vue-echarts 图表
- Pinia 状态管理
- Vue Router 5

## 项目结构

```
network_ops/
├── manage.py
├── netops/                 # Django 项目配置
├── apps/
│   ├── core/               # 用户认证、Token、Task/Stage
│   ├── assets/             # 数据模型（设备、机柜、IP、配置）
│   └── ops/                # 采集器、解析器、路径追踪
├── frontend/
│   └── src/
│       ├── api/            # API 模块（auth、devices、ipam、config、baseline、parsers、interfaces）
│       ├── composables/    # Vue Composables（useCrudApi、useEcharts、useTableHeight、useTagType）
│       ├── ui/             # 通用组件（PageLayout、FormPage、DataTable、ChartCard、StatCard、DeviceFilter、UserBar）
│       │   └── navigation/ # 导航组件（AppNav、menu-icons）
│       ├── stores/         # Pinia Store（auth、layout、theme）
│       ├── views/
│       │   ├── dashboard/  # 总览页
│       │   ├── devices/    # 设备管理
│       │   │   ├── forms/  # 表单页（DeviceForm、InterfaceForm、SnmpForm、NtpForm、SyslogForm）
│       │   │   └── dialogs/# 组件弹窗（CompareDialog、ImportDevice）
│       │   ├── config/     # 配置管理
│       │   │   ├── lb/     # 负载均衡（slb、gslb）
│       │   │   ├── firewall/ # 防火墙（firewall、policy）
│       │   │   └── network/  # 路由表
│       │   ├── ipam/       # IP 管理
│       │   │   └── forms/  # 表单页（SubnetForm、IpAddressForm、TagForm）
│       │   ├── tools/      # 工具（路径追踪、机柜视图）
│       │   └── login/      # 登录页
│       ├── layout/         # 布局组件（SideLayout）
│       ├── router/         # 路由配置
│       └── utils/          # 工具函数（token）
├── pyproject.toml
└── frontend/package.json
```

## 快速开始

```bash
# 后端
uv sync
uv run python manage.py migrate
uv run python manage.py createsuperuser
uv run python manage.py runserver

# 前端
cd frontend && pnpm install && pnpm dev
```

## 通用组件说明

| 组件 | 用途 |
|------|------|
| `PageLayout` | 页面布局框架（标题 + 操作区 + 内容插槽） |
| `FormPage` | 表单页布局（标题 + 保存/取消 + 表单插槽） |
| `DataTable` | el-table 包装器（默认 stripe/border/height/loading） |
| `ChartCard` | ECharts 图表卡片（autoresize） |
| `StatCard` | 数字统计卡片（支持图标、颜色） |
| `DeviceFilter` | 设备选择器（自动加载设备列表，v-model） |
| `UserBar` | 内容区顶部栏（全局搜索 + 主题切换 + 用户名 + 登出） |

## Composables 说明

| Composable | 用途 |
|------------|------|
| `useCrudApi` | 通用 CRUD 数据管理（loading/search/filter/fetch/save/delete） |
| `useEcharts` | ECharts 注册 + 图表配置工厂（pieOpt/barOpt/gaugeOpt） |
| `useTableHeight` | 表格高度自适应（resize 监听 + 自动清理） |
| `useTagType` | Tag 颜色映射（protocolTagType/modeTagType/statusTagType） |
