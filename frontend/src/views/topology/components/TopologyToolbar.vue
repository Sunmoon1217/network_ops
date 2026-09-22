<script setup lang="ts">
import { Edit, Check, Delete, Plus } from '@element-plus/icons-vue'

defineProps<{ editing: boolean }>()
const emit = defineEmits<{
  'add-device': []
  'add-custom': []
  'delete-selected': []
  save: []
  'toggle-edit': []
}>()
</script>

<template>
  <div class="topology-toolbar">
    <template v-if="!editing">
      <el-button type="primary" @click="emit('toggle-edit')">
        <el-icon><Edit /></el-icon>编辑
      </el-button>
    </template>
    <template v-else>
      <el-button @click="emit('add-device')"><el-icon><Plus /></el-icon>添加设备</el-button>
      <el-button @click="emit('add-custom')">自定义节点</el-button>
      <el-button type="danger" plain @click="emit('delete-selected')"><el-icon><Delete /></el-icon>删除选中</el-button>
      <el-button type="success" @click="emit('save')"><el-icon><Check /></el-icon>保存</el-button>
      <el-button @click="emit('toggle-edit')">退出编辑</el-button>
    </template>
  </div>
</template>

<style scoped>
.topology-toolbar { display: flex; gap: 8px; padding: 8px 0; }
</style>
