<script setup lang="ts">
import { CodeDiff } from 'v-code-diff'
import { useThemeStore } from '@/stores/theme'

const props = defineProps<{
  diff: string
  oldText?: string
  newText?: string
  /** 工具栏里 old/new 版本标识（通常传 hash 短码） */
  filename?: string
  newFilename?: string
}>()

const emit = defineEmits<{ diff: [stat: { isChanged: boolean; addNum: number; delNum: number }] }>()

const themeStore = useThemeStore()
const outputFormat = ref<'side-by-side' | 'line-by-line'>('side-by-side')

// 组件自带 header 被 hide-header 隐藏，导航/统计由宿主经 toolbar 插槽外置
const stat = ref({ addNum: 0, delNum: 0 })
const rootRef = ref<HTMLElement | null>(null)
let currentDiffIndex = -1

// CodeDiff 的 @diff 载荷是 DiffResult（{ stat: {...} }），解出扁平统计再转发
const onDiff = (diffResult: { stat: { isChanged: boolean; addNum: number; delNum: number } }) => {
  const s = diffResult.stat
  stat.value = { addNum: s.addNum, delNum: s.delNum }
  currentDiffIndex = -1
  emit('diff', s)
}

/** 复刻 v-code-diff 的 goToNext/PrevDiff：定位变更行 → 高亮 + 滚到视口中央 */
const jumpTo = (step: 1 | -1) => {
  const root = rootRef.value
  if (!root) return
  const diffs = root.querySelectorAll('[data-diff-change]')
  if (!diffs.length) return
  const next = currentDiffIndex + step
  if (next < 0 || next >= diffs.length) return
  currentDiffIndex = next
  root.querySelectorAll('.current-diff').forEach((el) => el.classList.remove('current-diff'))
  const target = diffs[currentDiffIndex]
  target.querySelectorAll('.blob-code').forEach((el) => el.classList.add('current-diff'))
  target.scrollIntoView({ behavior: 'smooth', block: 'center' })
}
const nextDiff = () => jumpTo(1)
const prevDiff = () => jumpTo(-1)

const parseUnifiedDiff = (diffText: string): { oldStr: string; newStr: string } => {
  const oldLines: string[] = []
  const newLines: string[] = []

  const lines = diffText.split('\n')
  for (const line of lines) {
    if (line.startsWith('---') || line.startsWith('+++') || line.startsWith('@@')) {
      continue
    }
    if (line.startsWith('-')) {
      oldLines.push(line.substring(1))
    } else if (line.startsWith('+')) {
      newLines.push(line.substring(1))
    } else {
      const content = line.startsWith(' ') ? line.substring(1) : line
      oldLines.push(content)
      newLines.push(content)
    }
  }

  return {
    oldStr: oldLines.join('\n'),
    newStr: newLines.join('\n'),
  }
}

const parsedContent = computed(() => {
  if (props.oldText && props.newText) {
    return { oldStr: props.oldText, newStr: props.newText }
  }

  if (props.diff) {
    return parseUnifiedDiff(props.diff)
  }

  return { oldStr: '', newStr: '' }
})

// 有 diff 才算有内容可渲染（oldText/newText 只是更完整的输入源，不单独构成「有 diff 可看」）；
// 两版相同时 diff 为空 → 走 empty 插槽（由宿主区分「请选择」/「无变更」）
const hasContent = computed(() => !!props.diff)
</script>

<template>
  <div ref="rootRef" class="code-diff-container">
    <!-- 宿主用 toolbar 插槽把这组控件放进自己的工具条（如版本选择器那排） -->
    <slot
      name="toolbar"
      :filename="filename"
      :new-filename="newFilename"
      :add-num="stat.addNum"
      :del-num="stat.delNum"
      :output-format="outputFormat"
      :set-output-format="(v: string | number | boolean | undefined) => { if (v === 'side-by-side' || v === 'line-by-line') outputFormat = v }"
      :prev="prevDiff"
      :next="nextDiff"
    />
    <!-- 空态：无 diff 且无全文 → 由宿主经 empty 插槽自定义文案 -->
    <div v-if="!hasContent" class="empty">
      <slot name="empty">无变更</slot>
    </div>
    <CodeDiff
      v-else
      :old-string="parsedContent.oldStr"
      :new-string="parsedContent.newStr"
      :theme="themeStore.isDark ? 'dark' : 'light'"
      :output-format="outputFormat"
      :context="999"
      hide-header
      language="plaintext"
      @diff="onDiff"
    />
  </div>
</template>

<style scoped>
.code-diff-container {
  /* 容器做 flex 列：toolbar 插槽（宿主外置的导航/统计/切换）固定在顶部，diff 区在下方滚动 */
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  background: var(--el-fill-color-blank);
}

.empty {
  display: flex;
  align-items: center;
  justify-content: center;
  flex: 1;
  color: var(--el-text-color-secondary);
}
</style>

<style>
/* 全局样式 - 单一滚动容器（toolbar 由宿主外置到选择器排，这里 hide-header 后只剩 diff 表）
   .code-diff-view 是唯一的 overflow:auto 滚动容器；.diff-table 是 display:table，
   overflow/flex 对它都不生效，故不参与滚动，只随内容撑高 */
.code-diff-container .code-diff-view {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  overflow: auto;
}
</style>
