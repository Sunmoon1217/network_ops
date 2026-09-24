<script setup lang="ts">
import PageLayout from '@/layout/PageLayout.vue'
import DataTable from '@/components/DataTable.vue'
import api from '@/api/index'
import { InfoFilled } from '@element-plus/icons-vue'

import type {
  ParserConsumer, ParserMappingItem, MissingProducer,
  MappingSummary, MappingResult, StatCard,
} from '@/types'

const loading = ref(false)
const result = ref<MappingResult | null>(null)

const parsers = computed(() => result.value?.parsers ?? [])
const missingProducers = computed(() => result.value?.missing_producers ?? [])
/** 是否存在声明与模板不一致的解析器，用于顶部告警 */
const hasMismatch = computed(() => parsers.value.some((item) => !item.keys_match))

/** 动态组名模板的提示文案（键名取自动态组名前缀，随配置内容变化） */
const dynamicGroupTip = '模板使用了 {{ }} 动态组名，产出键名取自动态组名前缀，会随配置内容变化'

/** 统计卡片：任一异常数 >0 时切换到 warning / danger 级别 */
const statCards = computed<StatCard[]>(() => {
  const summary = result.value?.summary
  if (!summary) return []
  return [
    { label: '解析器数', value: summary.parser_count, hint: '已注册的解析器数量', level: 'normal' },
    { label: 'Saver 数', value: summary.saver_count, hint: '已注册的 Saver 数量', level: 'normal' },
    {
      label: '声明与模板不一致',
      value: summary.keys_mismatch,
      hint: 'provides_keys 与模板静态提取键不一致',
      level: summary.keys_mismatch > 0 ? 'danger' : 'normal',
    },
    {
      label: '未消费键',
      value: summary.unconsumed_count,
      hint: '解析器产出但无 Saver 消费',
      level: summary.unconsumed_count > 0 ? 'warning' : 'normal',
    },
    {
      label: '消费无产出',
      value: summary.missing_producer_count,
      hint: 'Saver 消费但无解析器产出',
      level: summary.missing_producer_count > 0 ? 'danger' : 'normal',
    },
  ]
})

/** keys_match 为 false 的行整体高亮为 danger */
const rowClassName = ({ row }: { row: ParserMappingItem }) => (row.keys_match ? '' : 'row-keys-mismatch')

/** 拉取解析映射（解析器 → 模板 → 产出键 → Saver 的契约关系） */
const fetchMapping = async () => {
  loading.value = true
  try {
    const res = await api.get('/api/parsers/mapping/')
    result.value = res.data as MappingResult
  } catch (e: any) {
    result.value = null
    ElMessage.error(e?.response?.data?.detail || e?.response?.data?.error || '获取解析映射失败')
  } finally {
    loading.value = false
  }
}

/** 刷新：重新拉取映射数据 */
const handleRefresh = () => {
  fetchMapping()
}

onMounted(() => {
  fetchMapping()
})
</script>

<template>
  <PageLayout title="解析映射">
    <template #actions>
      <el-button :loading="loading" @click="handleRefresh">刷新</el-button>
    </template>

    <div v-loading="loading" class="mapping-body">
      <!-- 页面说明：本页用于发现「模板改结构后 Saver 静默失效」这类契约问题 -->
      <el-alert
        type="info"
        :closable="false"
        show-icon
        class="intro-alert"
        title="解析器 → 模板 → 产出键 → Saver 的映射关系"
        description="用于发现「模板改结构后 Saver 静默失效」这类问题：对照解析器声明、模板实际产出键与 Saver 消费，暴露契约缺口。"
      />

      <!-- 声明与模板不一致时顶部告警 -->
      <el-alert
        v-if="hasMismatch"
        type="error"
        :closable="false"
        show-icon
        class="intro-alert"
        :title="`有 ${result?.summary.keys_mismatch ?? 0} 个解析器的声明键与模板实际键不一致`"
        description="模板结构可能已变更，下方高亮行需要重点核对：对应的 Saver 可能已经静默失效。"
      />

      <template v-if="result">
        <!-- 统计卡片 -->
        <div class="stat-row">
          <div v-for="card in statCards" :key="card.label" class="stat-card" :class="`stat-${card.level}`">
            <div class="stat-label">{{ card.label }}</div>
            <div class="stat-value">{{ card.value }}</div>
            <div class="stat-hint">{{ card.hint }}</div>
          </div>
        </div>

        <!-- 主体：解析器映射表 -->
        <el-card shadow="never" class="block-card">
          <template #header>
            <div class="block-header">
              <span class="block-title">解析器 → 模板 → 产出键 → Saver</span>
              <span class="muted">共 {{ parsers.length }} 个解析器</span>
            </div>
          </template>

          <el-empty v-if="!parsers.length" description="暂无解析器映射数据" />

          <DataTable v-else :data="parsers" size="small" class="mapping-table" :row-class-name="rowClassName">
            <el-table-column prop="vendor" label="厂商" width="90" />
            <el-table-column label="设备类型" width="150">
              <template #default="{ row }">
                <span class="mono">{{ row.device_type || '—' }}</span>
              </template>
            </el-table-column>
            <el-table-column label="解析器类" min-width="150">
              <template #default="{ row }">
                <span class="mono">{{ row.class_name || '—' }}</span>
              </template>
            </el-table-column>
            <el-table-column label="模板文件" min-width="180">
              <template #default="{ row }">
                <div class="template-cell">
                  <span class="mono">{{ row.template_name || '—' }}</span>
                  <el-tag v-if="!row.template_exists" size="small" type="danger">模板缺失</el-tag>
                  <!-- 动态组名：键名取自主名前缀，需要额外说明 -->
                  <el-tooltip v-if="row.has_dynamic_group_names" :content="dynamicGroupTip" placement="top">
                    <el-icon class="tip-icon"><InfoFilled /></el-icon>
                  </el-tooltip>
                </div>
              </template>
            </el-table-column>

            <!-- 声明键：解析器 provides_keys -->
            <el-table-column label="产出键（声明）" min-width="170">
              <template #default="{ row }">
                <div v-if="row.provides_keys.length" class="tag-group">
                  <el-tag v-for="key in row.provides_keys" :key="key" size="small" effect="plain">{{ key }}</el-tag>
                </div>
                <el-tag v-else size="small" type="warning" effect="plain">无声明</el-tag>
              </template>
            </el-table-column>

            <!-- 模板实际键：keys_match 为 false 时与声明列并排对比 -->
            <el-table-column label="模板实际键" min-width="170">
              <template #default="{ row }">
                <el-tag v-if="row.keys_match" size="small" type="success" effect="plain">与声明一致</el-tag>
                <div v-else-if="row.template_keys.length" class="tag-group">
                  <el-tag
                    v-for="key in row.template_keys"
                    :key="key"
                    size="small"
                    type="danger"
                    effect="plain"
                  >
                    {{ key }}
                  </el-tag>
                </div>
                <el-tag v-else size="small" type="danger" effect="plain">模板未提取到键</el-tag>
              </template>
            </el-table-column>

            <!-- 消费者：产出键 → Saver -->
            <el-table-column label="消费者（键 → Saver）" min-width="220">
              <template #default="{ row }">
                <div v-if="row.consumers.length" class="tag-group">
                  <el-tag
                    v-for="consumer in row.consumers"
                    :key="`${consumer.key}-${consumer.saver}`"
                    size="small"
                    type="success"
                    effect="plain"
                  >
                    {{ consumer.key }} → {{ consumer.saver }}
                  </el-tag>
                </div>
                <el-tag v-else size="small" type="danger" effect="plain">无 Saver 消费</el-tag>
              </template>
            </el-table-column>

            <!-- 未消费键：产出但无人消费，warning 色 -->
            <el-table-column label="未消费键" min-width="170">
              <template #default="{ row }">
                <div v-if="row.unconsumed_keys.length" class="tag-group">
                  <el-tag
                    v-for="key in row.unconsumed_keys"
                    :key="key"
                    size="small"
                    type="warning"
                    effect="plain"
                  >
                    {{ key }}
                  </el-tag>
                </div>
                <span v-else class="muted">—</span>
              </template>
            </el-table-column>
          </DataTable>
        </el-card>

        <!-- 契约缺口：Saver 消费了但没有任何解析器产出 -->
        <el-card shadow="never" class="block-card">
          <template #header>
            <div class="block-header">
              <span class="block-title">契约缺口：Saver 消费但无解析器产出</span>
              <el-tag v-if="missingProducers.length" size="small" type="danger">{{ missingProducers.length }} 项</el-tag>
              <el-tag v-else size="small" type="success">无缺口</el-tag>
            </div>
          </template>

          <el-empty v-if="!missingProducers.length" description="没有发现契约缺口" :image-size="60" />

          <DataTable v-else :data="missingProducers" size="small">
            <el-table-column label="设备类型" width="160">
              <template #default="{ row }">
                <span class="mono">{{ row.device_type || '—' }}</span>
              </template>
            </el-table-column>
            <el-table-column label="消费键" width="180">
              <template #default="{ row }">
                <el-tag size="small" type="warning" effect="plain">{{ row.key }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="Saver" min-width="180">
              <template #default="{ row }">
                <span class="mono">{{ row.saver || '—' }}</span>
              </template>
            </el-table-column>
            <el-table-column label="说明" min-width="240">
              <template #default="{ row }">
                <span class="muted">{{ row.note || '—' }}</span>
              </template>
            </el-table-column>
          </DataTable>
        </el-card>
      </template>

      <el-empty v-else-if="!loading" description="暂无映射数据，请点击刷新重试" />
    </div>
  </PageLayout>
</template>

<style scoped>
.mapping-body {
  flex: 1;
  min-height: 0;
  overflow: auto;
}
.intro-alert { margin-bottom: 12px; }

/* 统计卡片：默认 primary 左边框，异常时切换为 warning / danger */
.stat-row {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 12px;
}
.stat-card {
  flex: 1 1 170px;
  min-width: 160px;
  padding: 12px 14px;
  border: 1px solid var(--el-border-color-lighter);
  border-left: 3px solid var(--el-color-primary);
  border-radius: 10px;
  background: var(--el-fill-color-blank);
}
.stat-card.stat-warning {
  border-left-color: var(--el-color-warning);
  background: var(--el-color-warning-light-9, rgba(230, 162, 60, 0.06));
}
.stat-card.stat-danger {
  border-left-color: var(--el-color-danger);
  background: var(--el-color-danger-light-9, rgba(245, 108, 108, 0.06));
}
.stat-label { font-size: 12px; color: var(--el-text-color-secondary); }
.stat-value {
  margin: 2px 0;
  font-size: 22px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}
.stat-card.stat-warning .stat-value { color: var(--el-color-warning); }
.stat-card.stat-danger .stat-value { color: var(--el-color-danger); }
.stat-hint { font-size: 11px; color: var(--el-text-color-placeholder); }

.block-card { margin-bottom: 12px; }
.block-header { display: flex; align-items: center; gap: 8px; }
.block-title { font-size: 14px; font-weight: 600; }

.tag-group { display: flex; flex-wrap: wrap; gap: 4px; }
.template-cell { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.tip-icon { color: var(--el-color-info); cursor: help; }

/* keys_match === false 的行整体高亮为 danger（td 自带背景色，需覆盖） */
.mapping-table :deep(.row-keys-mismatch) td.el-table__cell {
  background: var(--el-color-danger-light-9) !important;
}
.mapping-table :deep(.row-keys-mismatch:hover) td.el-table__cell {
  background: var(--el-color-danger-light-8) !important;
}

.mono { font-family: Menlo, Consolas, monospace; font-size: 12px; }
.muted { font-size: 12px; color: var(--el-text-color-secondary); }
</style>
