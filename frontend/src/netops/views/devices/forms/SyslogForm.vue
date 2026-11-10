<script setup lang="ts">
import FormPage from '@/components/FormPage.vue'
import { getSyslogConfig, createSyslogConfig, updateSyslogConfig } from '@/api/baseline'
import { fetchAllPages } from '@/utils/fetchAllPages'

const route = useRoute()
const router = useRouter()
const form = ref<any>({ device: '', port: 514, facility: 'local7', level: 'informational', enabled: true })
const loading = ref(false)
const devices = ref<any[]>([])
const isNew = computed(() => !route.params.id)

onMounted(async () => {
  loading.value = true
  try {
    devices.value = await fetchAllPages('/api/assets/devices/', { ordering: 'hostname' })
    if (route.params.id) {
      const res = await getSyslogConfig(Number(route.params.id))
      form.value = { ...res.data }
    }
  } finally { loading.value = false }
})

const save = async () => {
  try {
    if (isNew.value) await createSyslogConfig(form.value)
    else await updateSyslogConfig(form.value.id, form.value)
    ElMessage.success('保存成功')
    router.push('/devices/baseline')
  } catch { ElMessage.error('保存失败') }
}
</script>

<template>
  <FormPage :title="isNew ? '新增 Syslog 配置' : '编辑 Syslog 配置'" :loading="loading" @save="save" @cancel="router.back()">
    <el-form-item label="设备" required>
      <el-select v-model="form.device" filterable style="width: 100%">
        <el-option v-for="d in devices" :key="d.id" :label="d.hostname" :value="d.id" />
      </el-select>
    </el-form-item>
    <el-form-item label="日志服务器1" required><el-input v-model="form.server1" /></el-form-item>
    <el-form-item label="日志服务器2"><el-input v-model="form.server2" /></el-form-item>
    <el-form-item label="端口"><el-input-number v-model="form.port" :min="1" :max="65535" /></el-form-item>
    <el-form-item label="Facility">
      <el-select v-model="form.facility" style="width: 100%">
        <el-option v-for="i in 8" :key="i" :label="`local${i-1}`" :value="`local${i-1}`" />
      </el-select>
    </el-form-item>
    <el-form-item label="日志级别">
      <el-select v-model="form.level" style="width: 100%">
        <el-option v-for="l in ['emergency','alert','critical','error','warning','notice','informational','debugging']" :key="l" :label="l" :value="l" />
      </el-select>
    </el-form-item>
  </FormPage>
</template>
