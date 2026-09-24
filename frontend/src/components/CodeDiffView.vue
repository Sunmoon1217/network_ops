<script setup lang="ts">
import { CodeDiff } from 'v-code-diff'
import { useThemeStore } from '@/stores/theme'

const props = defineProps<{
  diff: string
  oldText?: string
  newText?: string
}>()

const themeStore = useThemeStore()
const outputFormat = ref<'side-by-side' | 'line-by-line'>('side-by-side')

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
</script>

<template>
  <div class="code-diff-container">
    <div v-if="!diff && !oldText" class="empty">无变更</div>
    <CodeDiff
      v-else
      :old-string="parsedContent.oldStr"
      :new-string="parsedContent.newStr"
      :theme="themeStore.isDark ? 'dark' : 'light'"
      :output-format="outputFormat"
      :context="999"
      :hide-stat="false"
      language="plaintext"
    >
      <template #header-actions>
        <el-radio-group v-model="outputFormat" size="small" class="format-toggle">
          <el-radio-button value="side-by-side">并排</el-radio-button>
          <el-radio-button value="line-by-line">行对行</el-radio-button>
        </el-radio-group>
      </template>
    </CodeDiff>
  </div>
</template>

<style scoped>
.code-diff-container {
  height: 100%;
  overflow: auto;
  background: var(--el-fill-color-blank);
}

.empty {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: var(--el-text-color-secondary);
}

.format-toggle {
  margin-left: auto;
}
</style>

<style>
/* 全局样式 - 固定 file-header（统计和导航按钮），两种输出模式的表都走表内滚动 */
.code-diff-container .code-diff-view {
  display: flex;
  flex-direction: column;
  height: 100%;
}

.code-diff-container .file-header {
  position: sticky;
  top: 0;
  z-index: 10;
  background: var(--el-fill-color-blank);
  border-bottom: 1px solid var(--el-border-color-lighter);
  padding: 8px 12px;
}

.code-diff-container .diff-table {
  flex: 1;
  min-height: 0;
  overflow: auto;
}
</style>
