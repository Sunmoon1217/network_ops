<script setup lang="ts">
import FormPage from '@/components/FormPage.vue'
import { getSnmpConfig, createSnmpConfig, updateSnmpConfig } from '@/api/baseline'
import { fetchAllPages } from '@/utils/fetchAllPages'

const route = useRoute()
const router = useRouter()
const form = ref<any>({ device: '', version: 'v2c', port: 161, trap_port: 162, enabled: true })
const loading = ref(false)
const devices = ref<any[]>([])
const isNew = computed(() => !route.params.id)

onMounted(async () => {
  loading.value = true
  try {
    devices.value = await fetchAllPages('/api/assets/devices/', { ordering: 'hostname' })
    if (route.params.id) {
      const res = await getSnmpConfig(Number(route.params.id))
      form.value = { ...res.data }
    }
  } finally { loading.value = false }
})

const save = async () => {
  try {
    if (isNew.value) await createSnmpConfig(form.value)
    else await updateSnmpConfig(form.value.id, form.value)
    ElMessage.success('保存成功')
    router.push('/devices/baseline')
  } catch { ElMessage.error('保存失败') }
}
</script>

<template>
  <FormPage :title="isNew ? '新增 SNMP 配置' : '编辑 SNMP 配置'" :loading="loading" @save="save" @cancel="router.back()">
    <el-form-item label="设备" required>
      <el-select v-model="form.device" filterable style="width: 100%">
        <el-option v-for="d in devices" :key="d.id" :label="d.hostname" :value="d.id" />
      </el-select>
    </el-form-item>
    <el-form-item label="SNMP 版本">
      <el-select v-model="form.version" style="width: 100%">
        <el-option label="v1" value="v1" /><el-option label="v2c" value="v2c" /><el-option label="v3" value="v3" />
      </el-select>
    </el-form-item>
    <el-form-item label="读社区"><el-input v-model="form.community_read" /></el-form-item>
    <el-form-item label="写社区"><el-input v-model="form.community_write" /></el-form-item>
    <el-form-item label="端口"><el-input-number v-model="form.port" :min="1" :max="65535" /></el-form-item>
    <el-form-item label="启用 Trap"><el-switch v-model="form.trap_enabled" /></el-form-item>
    <el-form-item v-if="form.trap_enabled" label="Trap 服务器"><el-input v-model="form.trap_server" /></el-form-item>
  </FormPage>
</template>
