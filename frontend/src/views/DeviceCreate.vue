<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import api from '../utils/django_api'

const router = useRouter()

const form = ref({
  hostname: '',
  address: '',
  username: '',
  device_type: '',
  // password may be optional depending on backend
  password: '',
})

const submitting = ref(false)
const error = ref<string | null>(null)

async function submit() {
  submitting.value = true
  error.value = null
  try {
    await api.post('/devices/', form.value)
    router.push('/devices')
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Unknown error'
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <div class="device-create-container">
    <h2>新增设备</h2>

    <div v-if="error" class="error">{{ error }}</div>

    <form @submit.prevent="submit" class="device-form">
      <label>
        主机名
        <input v-model="form.hostname" required />
      </label>

      <label>
        IP 地址
        <input v-model="form.address" required />
      </label>

      <label>
        用户名
        <input v-model="form.username" />
      </label>

      <label>
        设备类型
        <input v-model="form.device_type" />
      </label>

      <label>
        密码
        <input v-model="form.password" type="password" />
      </label>

      <div class="form-actions">
        <button type="submit" :disabled="submitting">保存</button>
        <button type="button" @click="router.push('/devices')">取消</button>
      </div>
    </form>
  </div>
</template>

<style scoped>
.device-create-container {
  max-width: 720px;
  margin: 20px auto;
  padding: 20px;
  background: #fff;
  border-radius: 8px;
  box-shadow: 0 2px 6px rgba(0,0,0,0.06);
}

.device-form {
  display: grid;
  gap: 12px;
}

.device-form label {
  display: flex;
  flex-direction: column;
  font-size: 0.95rem;
}

.device-form input {
  padding: 8px 10px;
  border: 1px solid #dcdfe6;
  border-radius: 6px;
}

.form-actions {
  display: flex;
  gap: 10px;
  margin-top: 8px;
}

.form-actions button[type="submit"] {
  background: #409eff;
  color: white;
  border: none;
  padding: 8px 14px;
  border-radius: 6px;
  cursor: pointer;
}

.form-actions button[type="button"] {
  background: #f5f7fa;
  border: 1px solid #dcdfe6;
  padding: 8px 14px;
  border-radius: 6px;
  cursor: pointer;
}
</style>
