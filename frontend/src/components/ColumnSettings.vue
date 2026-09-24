<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { Rank, RefreshLeft, Setting } from '@element-plus/icons-vue'
import Sortable from 'sortablejs'
import { useTablePrefs } from '@/composables/useTablePrefs'

import type { SortableEvent } from 'sortablejs'
import type { ColumnMeta, TableKey } from '@/types'

/**
 * 列设置（方案 A）：列顺序拖拽管理 + 列显隐的弹窗入口。
 *
 * 拖拽发生在**弹窗列清单**内（SortableJS），不拖表头——表格/表头零触碰，
 * 规开「表头 DOM 拖动 vs 偏好驱动 vnode 重排」的双真相源回弹与
 * fixed 列独立表头副本两个坑。顺序与显隐都走 useTablePrefs 的列布局偏好
 * （`table:<key>:column-layout`），刷新/换设备后依旧生效。
 */
const props = defineProps<{
  /** 所属表格的注册表 key（偏好命名空间） */
  tableKey: TableKey
  /** 列元数据（全量，含已隐藏的列——要能取消隐藏） */
  columns: ColumnMeta[]
}>()

const { columnOrder, hiddenKeys, saveOrder, toggleColumn, resetColumnLayout } = useTablePrefs(props.tableKey)

const visible = ref(false)
const listRef = ref<HTMLElement>()
let sortable: Sortable | null = null

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

/** 拖拽结束：把 DOM 移动折算成全量 key 序保存；保存后数据驱动重渲即恢复 Vue 对 DOM 的控制 */
const handleDragEnd = (evt: SortableEvent) => {
  const { oldIndex, newIndex } = evt
  if (oldIndex == null || newIndex == null || oldIndex === newIndex) return
  const keys = ordered.value.map((c) => c.key)
  const [moved] = keys.splice(oldIndex, 1)
  keys.splice(newIndex, 0, moved)
  saveOrder(keys)
}

/** el-dialog 内容懒渲染：首次打开后才建 Sortable（容器级委托，v-for 增减列不受影响） */
const initSortable = async () => {
  await nextTick()
  if (sortable || !listRef.value) return
  sortable = Sortable.create(listRef.value, {
    draggable: '.col-row',
    animation: 150,
    // 勾选显隐不触发拖拽，且不吞 checkbox 的点击（preventOnFilter 默认 true 会拦点击）
    filter: '.el-checkbox',
    preventOnFilter: false,
    onEnd: handleDragEnd,
  })
}

watch(visible, (v) => {
  if (v) initSortable()
})

onBeforeUnmount(() => {
  sortable?.destroy()
  sortable = null
})

const handleReset = () => {
  resetColumnLayout()
  visible.value = false
}
</script>

<template>
  <el-button class="settings-btn" :icon="Setting" size="small" circle @click="visible = true" />
  <el-dialog v-model="visible" title="列设置" width="380px" append-to-body>
    <div ref="listRef" class="col-list">
      <div v-for="col in ordered" :key="col.key" class="col-row">
        <el-checkbox
          :model-value="!hiddenKeys.has(col.key)"
          @change="toggleColumn(col.key)"
        >
          {{ col.label }}
        </el-checkbox>
        <el-icon class="drag-handle"><Rank /></el-icon>
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
.col-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 2px 0;
  cursor: grab;
}
.col-row:active { cursor: grabbing; }
.drag-handle { color: var(--el-text-color-secondary); }
</style>
