<script setup lang="ts">
import { ref, watch } from 'vue'

const props = defineProps<{ node: any }>()
const emit = defineEmits<{
  (e: 'update', data: any): void
  (e: 'save', data: any): void
  (e: 'cancel'): void
}>()

const note = ref('')
const label = ref('')

watch(() => props.node, (n) => {
  if (n) {
    label.value = n.label || n.id || ''
    note.value = n.data?.note || ''
  }
}, { immediate: true })

const getUpdatedNode = () => {
  return {
    ...props.node,
    label: label.value,
    data: { ...(props.node.data || {}), note: note.value },
  }
}

const handleSave = () => {
  emit('save', getUpdatedNode())
}

const handleCancel = () => {
  emit('cancel')
}
</script>

<template>
  <el-form label-position="top" size="small">
    <el-form-item label="名称">
      <el-input v-model="label" />
    </el-form-item>
    <el-form-item label="备注">
      <el-input v-model="note" type="textarea" :rows="3" />
    </el-form-item>
    <el-form-item label="类型">
      <el-tag>{{ node.data?.device_type || '自定义' }}</el-tag>
    </el-form-item>
    <el-form-item>
      <div style="display:flex;gap:8px;justify-content:flex-end;width:100%;">
        <el-button size="small" @click="handleCancel">取消</el-button>
        <el-button type="primary" size="small" @click="handleSave">保存</el-button>
      </div>
    </el-form-item>
  </el-form>
</template>
