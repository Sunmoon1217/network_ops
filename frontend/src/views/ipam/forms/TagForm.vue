<script setup lang="ts">
import FormPage from '@/ui/FormPage.vue'
import { getTag, createTag, updateTag } from '@/api/ipam'

const route = useRoute()
const router = useRouter()
const form = ref<any>({ name: '', color: '#3b82f6' })
const loading = ref(false)
const isNew = computed(() => !route.params.id)

onMounted(async () => {
  if (!route.params.id) return
  loading.value = true
  try {
    const res = await getTag(Number(route.params.id))
    form.value = { ...res.data }
  } finally { loading.value = false }
})

const save = async () => {
  if (!form.value?.name) { ElMessage.warning('请输入标签名称'); return }
  try {
    if (isNew.value) await createTag(form.value)
    else await updateTag(form.value.id, form.value)
    ElMessage.success('保存成功')
    router.push('/ipam/tags')
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.name?.[0] || '保存失败')
  }
}
</script>

<template>
  <FormPage :title="isNew ? '新增标签' : '编辑标签'" :loading="loading" max-width="400px" @save="save" @cancel="router.back()">
    <el-form-item label="名称" required><el-input v-model="form.name" /></el-form-item>
    <el-form-item label="颜色"><el-color-picker v-model="form.color" /></el-form-item>
  </FormPage>
</template>
