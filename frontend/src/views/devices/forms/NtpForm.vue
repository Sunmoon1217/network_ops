<script setup lang="ts">
import FormPage from '@/ui/FormPage.vue'
import { getNtpConfig, createNtpConfig, updateNtpConfig } from '@/api/baseline'
import { fetchAllPages } from '@/utils/fetchAllPages'

const route = useRoute()
const router = useRouter()
const form = ref<any>({ device: '', server1: '', timezone: 'UTC', sync_interval: 64, enabled: true })
const loading = ref(false)
const devices = ref<any[]>([])
const isNew = computed(() => !route.params.id)

onMounted(async () => {
  loading.value = true
  try {
    devices.value = await fetchAllPages('/api/assets/devices/', { ordering: 'hostname' })
    if (route.params.id) {
      const res = await getNtpConfig(Number(route.params.id))
      form.value = { ...res.data }
    }
  } finally { loading.value = false }
})

const save = async () => {
  try {
    if (isNew.value) await createNtpConfig(form.value)
    else await updateNtpConfig(form.value.id, form.value)
    ElMessage.success('保存成功')
    router.push('/devices/baseline')
  } catch { ElMessage.error('保存失败') }
}
</script>

<template>
  <FormPage :title="isNew ? '新增 NTP 配置' : '编辑 NTP 配置'" :loading="loading" @save="save" @cancel="router.back()">
    <el-form-item label="设备" required>
      <el-select v-model="form.device" filterable style="width: 100%">
        <el-option v-for="d in devices" :key="d.id" :label="d.hostname" :value="d.id" />
      </el-select>
    </el-form-item>
    <el-form-item label="NTP 服务器1" required><el-input v-model="form.server1" /></el-form-item>
    <el-form-item label="NTP 服务器2"><el-input v-model="form.server2" /></el-form-item>
    <el-form-item label="NTP 服务器3"><el-input v-model="form.server3" /></el-form-item>
    <el-form-item label="时区"><el-input v-model="form.timezone" /></el-form-item>
    <el-form-item label="同步间隔"><el-input-number v-model="form.sync_interval" :min="1" /></el-form-item>
  </FormPage>
</template>
