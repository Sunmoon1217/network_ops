<script setup lang="ts">
import { computed, ref } from 'vue'
import { Bottom, RefreshLeft, Setting, Top } from '@element-plus/icons-vue'
import { useTablePrefs } from '@/composables/useTablePrefs'

import type { ColumnMeta, TableKey } from '@/types'

/**
 * 列设置（方案 C）：列顺序管理 + 列显隐的弹窗入口。
 *
 * 不是拖拽换列——上移/下移 + 勾选显隐，全部走 useTablePrefs 的列布局偏好
 * （`table:<key>:column-layout`），刷新/换设备后依旧生效；挂 table-key 的表格
 * 由 DataTable 渲染本组件（按钮悬浮表格右上角），其余页面零接入成本。
 */
const props = defineProps<{
  /** 所属表格的注册表 key（偏好命名空间） */
  tableKey: TableKey
  /** 列元数据（全量，含已隐藏的列——要能取消隐藏） */
  columns: ColumnMeta[]
}>()

const { columnOrder, hiddenKeys, moveColumn, toggleColumn, resetColumnLayout } = useTablePrefs(props.tableKey)

const visible = ref(false)

/** 弹窗列清单 = 当前有效顺序：order 里登记的优先，未登记列按槽序排尾部 */
const ordered = computed(() => {
  const order = columnOrder.value
  const rank = (key: string) => {
    const idx = order.indexOf(key)
    return idx < 0 ? Number.MAX_SAFE_INTEGER : idx
  }
  return props.columns
    .map((col, idx) => ({ col, idx }))
    .sort((a, b) => rank(a.col.key) - rank(b.col.key) || a.idx - b.idx)
    .map((x) => x.col)
})

const handleReset = () => {
  resetColumnLayout()
  visible.value = false
}
</script>

<template>
  <el-button class="settings-btn" :icon="Setting" size="small" circle @click="visible = true" />
  <el-dialog v-model="visible" title="列设置" width="380px" append-to-body>
    <div class="col-list">
      <div v-for="(col, idx) in ordered" :key="col.key" class="col-row">
        <el-checkbox
          :model-value="!hiddenKeys.has(col.key)"
          @change="toggleColumn(col.key)"
        >
          {{ col.label }}
        </el-checkbox>
        <span class="col-move">
          <el-button text :icon="Top" :disabled="idx === 0" @click="moveColumn(col.key, -1)" />
          <el-button text :icon="Bottom" :disabled="idx === ordered.length - 1" @click="moveColumn(col.key, 1)" />
        </span>
      </div>
    </div>
    <template #footer>
      <el-button :icon="RefreshLeft" @click="handleReset">恢复默认</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.settings-btn {
  position: absolute;
  top: 6px;
  right: 14px;
  z-index: 5;
  opacity: 0.5;
}
.settings-btn:hover { opacity: 1; }
.col-list { max-height: 50vh; overflow: auto; }
.col-row { display: flex; align-items: center; justify-content: space-between; padding: 2px 0; }
.col-move .el-button + .el-button { margin-left: 2px; }
</style>
