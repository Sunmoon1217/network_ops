<script setup lang="ts">
import FormPage from '@/components/FormPage.vue'
import { getSubnet, createSubnet, updateSubnet } from '@/api/ipam'
import { fetchAllPages } from '@/utils/fetchAllPages'

const route = useRoute()
const router = useRouter()
const form = ref<any>({ network: '', gateway: '', vlan: '', description: '', tags: [] })
const loading = ref(false)
const tags = ref<any[]>([])
const isNew = computed(() => !route.params.id)

onMounted(async () => {
  loading.value = true
  try {
    tags.value = await fetchAllPages('/api/assets/tags/', { ordering: 'name' })
    if (route.params.id) {
      const res = await getSubnet(Number(route.params.id))
      form.value = { ...res.data, tags: res.data.tags || [] }
    }
  } finally { loading.value = false }
})

const save = async () => {
  if (!form.value?.network) { ElMessage.warning('请输入网段'); return }
  try {
    if (isNew.value) await createSubnet(form.value)
    else await updateSubnet(form.value.id, form.value)
    ElMessage.success('保存成功')
    router.push('/ipam/subnets')
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.network?.[0] || '保存失败')
  }
}
</script>

<template>
  <FormPage :title="isNew ? '新增网段' : '编辑网段'" :loading="loading" @save="save" @cancel="router.back()">
    <el-form-item label="网段" required><el-input v-model="form.network" placeholder="如 10.0.0.0/24" /></el-form-item>
    <el-form-item label="网关"><el-input v-model="form.gateway" placeholder="如 10.0.0.1" /></el-form-item>
    <el-form-item label="VLAN"><el-input v-model="form.vlan" /></el-form-item>
    <el-form-item label="标签">
      <el-select v-model="form.tags" multiple filterable placeholder="选择标签" style="width: 100%">
        <el-option v-for="t in tags" :key="t.id" :label="t.name" :value="t.id" />
      </el-select>
    </el-form-item>
    <el-form-item label="描述"><el-input v-model="form.description" type="textarea" :rows="2" /></el-form-item>
  </FormPage>
</template>
