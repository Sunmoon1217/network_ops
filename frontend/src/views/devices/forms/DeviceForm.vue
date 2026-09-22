<script setup lang="ts">
import FormPage from '@/components/FormPage.vue'
import { getDevice } from '@/api/devices'
import api from '@/api/index'

const route = useRoute()
const router = useRouter()
const form = ref<any>({ hostname: '', device_type: 'switch', ip_address: '', remark: '' })
const loading = ref(false)
const isNew = computed(() => !route.params.id)

onMounted(async () => {
  if (!route.params.id) return
  loading.value = true
  try {
    const res = await getDevice(Number(route.params.id))
    form.value = { ...res.data }
  } finally { loading.value = false }
})

const save = async () => {
  if (!form.value?.hostname) { ElMessage.warning('请输入主机名'); return }
  try {
    if (isNew.value) await api.post('/api/assets/devices/', form.value)
    else await api.put(`/api/assets/devices/${form.value.id}/`, form.value)
    ElMessage.success('保存成功')
    router.push('/devices')
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.hostname?.[0] || '保存失败')
  }
}
</script>

<template>
  <FormPage :title="isNew ? '新建设备' : '编辑设备'" :loading="loading" @save="save" @cancel="router.back()">
    <el-form-item label="主机名" required><el-input v-model="form.hostname" /></el-form-item>
    <el-form-item label="类型">
      <el-select v-model="form.device_type" style="width: 100%">
        <el-option label="防火墙" value="firewall" /><el-option label="交换机" value="switch" />
        <el-option label="服务器负载均衡" value="slb" /><el-option label="全局负载均衡" value="gslb" />
        <el-option label="路由器" value="router" />
        <el-option label="服务器" value="server" />
      </el-select>
    </el-form-item>
    <el-form-item label="管理IP"><el-input v-model="form.ip_address" /></el-form-item>
    <el-form-item label="备注"><el-input v-model="form.remark" type="textarea" :rows="2" /></el-form-item>
  </FormPage>
</template>
