<script setup lang="ts">
import PageLayout from '@/ui/PageLayout.vue'

defineProps<{
  title: string
  loading?: boolean
  maxWidth?: string
}>()

const emit = defineEmits<{ (e: 'save'): void; (e: 'cancel'): void }>()
</script>

<template>
  <PageLayout :title="title">
    <template #actions>
      <el-button @click="emit('cancel')">取消</el-button>
      <el-button type="primary" :loading="loading" @click="emit('save')">保存</el-button>
    </template>
    <div class="form-body" :style="{ maxWidth: maxWidth || '560px' }">
      <el-form v-loading="loading" label-width="100px">
        <slot />
      </el-form>
    </div>
  </PageLayout>
</template>

<style scoped>
.form-body { background: #fff; border-radius: 8px; padding: 24px; }
</style>
