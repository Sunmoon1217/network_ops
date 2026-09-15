<script setup lang="ts">
import FormPage from '@/ui/FormPage.vue'
import { getIpAddress, createIpAddress, updateIpAddress } from '@/api/ipam'
import { fetchAllPages } from '@/utils/fetchAllPages'

const route = useRoute()
const router = useRouter()
const form = ref<any>({ ip_address: '', status: 'used', description: '' })
const loading = ref(false)
const devices = ref<any[]>([])
const isNew = computed(() => !route.params.id)

const statusOptions = [
  { label: '已使用', value: 'used' },
  { label: '预留', value: 'reserved' },
  { label: '可用', value: 'available' },
]

onMounted(async () => {
  loading.value = true
  try {
    devices.value = await fetchAllPages('/api/assets/devices/', { ordering: 'hostname' })
    if (route.params.id) {
      const res = await getIpAddress(Number(route.params.id))
      form.value = { ...res.data }
    }
  } finally { loading.value = false }
})

const save = async () => {
  if (!form.value?.ip_address) { ElMessage.warning('请输入 IP 地址'); return }
  try {
    if (isNew.value) await createIpAddress(form.value)
    else await updateIpAddress(form.value.id, form.value)
    ElMessage.success('保存成功')
    router.push('/ipam/ip-addresses')
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.ip_address?.[0] || '保存失败')
  }
}
</script>

<template>
  <FormPage :title="isNew ? '新增 IP 地址' : '编辑 IP 地址'" :loading="loading" @save="save" @cancel="router.back()">
    <el-form-item label="IP 地址" required><el-input v-model="form.ip_address" placeholder="如 10.0.1.1" /></el-form-item>
    <el-form-item label="状态">
      <el-select v-model="form.status" style="width: 100%">
        <el-option v-for="s in statusOptions" :key="s.value" :label="s.label" :value="s.value" />
      </el-select>
    </el-form-item>
    <el-form-item label="关联设备">
      <el-select v-model="form.device" clearable filterable placeholder="选择设备" style="width: 100%">
        <el-option v-for="d in devices" :key="d.id" :label="d.hostname" :value="d.id" />
      </el-select>
    </el-form-item>
    <el-form-item label="接口"><el-input v-model="form.interface" /></el-form-item>
    <el-form-item label="描述"><el-input v-model="form.description" type="textarea" :rows="2" /></el-form-item>
  </FormPage>
</template>
