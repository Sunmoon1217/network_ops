<script setup lang="ts">
import FormPage from '@/ui/FormPage.vue'
import { getInterface, updateInterface } from '@/api/interfaces'

const route = useRoute()
const router = useRouter()
const form = ref<any>({})
const loading = ref(false)

const modeOptions = [
  { label: '三层接口', value: 'layer3' },
  { label: 'Access', value: 'access' },
  { label: 'Hybrid', value: 'hybrid' },
  { label: 'Trunk', value: 'trunk' },
]

onMounted(async () => {
  if (!route.params.id) return
  loading.value = true
  try {
    const res = await getInterface(Number(route.params.id))
    form.value = { ...res.data }
  } finally { loading.value = false }
})

const save = async () => {
  try {
    await updateInterface(form.value.id, {
      mode: form.value.mode,
      ip_address: form.value.ip_address,
      subnet_mask: form.value.subnet_mask,
      description: form.value.description,
      enabled: form.value.enabled,
    })
    ElMessage.success('保存成功')
    router.push('/devices/interfaces')
  } catch { ElMessage.error('保存失败') }
}
</script>

<template>
  <FormPage title="编辑接口" :loading="loading" @save="save" @cancel="router.back()">
    <el-form-item label="设备"><el-input :model-value="form.device_hostname" disabled /></el-form-item>
    <el-form-item label="接口"><el-input :model-value="form.interface" disabled /></el-form-item>
    <el-form-item label="模式">
      <el-select v-model="form.mode" clearable style="width: 100%">
        <el-option v-for="m in modeOptions" :key="m.value" :label="m.label" :value="m.value" />
      </el-select>
    </el-form-item>
    <el-form-item label="IP 地址"><el-input v-model="form.ip_address" /></el-form-item>
    <el-form-item label="子网掩码"><el-input v-model="form.subnet_mask" /></el-form-item>
    <el-form-item label="启用"><el-switch v-model="form.enabled" /></el-form-item>
    <el-form-item label="描述"><el-input v-model="form.description" type="textarea" :rows="2" /></el-form-item>
  </FormPage>
</template>
