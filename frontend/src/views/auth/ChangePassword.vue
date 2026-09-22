<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import type { FormInstance, FormRules } from 'element-plus'

const router = useRouter()
const authStore = useAuthStore()
const formRef = ref<FormInstance | null>(null)
const loading = ref(false)

const formData = ref({ old_password: '', new_password: '', confirm_password: '' })

const rules: FormRules = {
    old_password: [{ required: true, message: '请输入旧密码', trigger: 'blur' }],
    new_password: [{ required: true, message: '请输入新密码', trigger: 'blur' }],
    confirm_password: [
        { required: true, message: '请确认新密码', trigger: 'blur' },
        {
            validator: (rule, value) => {
                if (value !== formData.value.new_password) {
                    return Promise.reject(new Error('两次输入的密码不一致'))
                }
                return Promise.resolve()
            },
            trigger: 'blur',
        },
    ],
}

const handle = async () => {
    if (!formRef.value) return
    try {
        await formRef.value.validate()
    } catch { return }
    loading.value = true
    try {
        const result = await authStore.changePassword(formData.value)
        if (result) {
            ElMessage.success('密码修改成功')
        } else {
            ElMessage.error('密码修改失败')
        }
        // router.push('/login')
    } catch (error: any) {
        ElMessage.error(error?.response?.data?.error || '修改密码失败')
    } finally {
        loading.value = false
    }
}
</script>

<template>
    <div class="container">
        <div class="card">

            <div class="login-header">
                <h1>修改密码</h1>
            </div>

            <el-form ref="formRef" :model="formData" :rules="rules" label-position="top" size="large"
                :disabled="loading" @keyup.enter="handle">
                <el-form-item label="旧密码" prop="oldpassword">
                    <el-input v-model="formData.old_password" type="password" show-password placeholder="请输入旧密码"
                        autocomplete="old_password" />
                </el-form-item>
                <el-form-item label="新密码" prop="password">
                    <el-input v-model="formData.new_password" type="password" show-password placeholder="请输入新密码"
                        autocomplete="new_password" />
                </el-form-item>
                <el-form-item label="确认新密码" prop="confirmPassword">
                    <el-input v-model="formData.confirm_password" type="password" show-password placeholder="请确认新密码"
                        autocomplete="confirm_password" />
                </el-form-item>
                <el-form-item>
                    <el-button type="primary" class="login-button" size="large" :loading="loading"
                        @click="handle">确认</el-button>
                </el-form-item>
            </el-form>
        </div>
    </div>
</template>

<style scoped>
.container {
    display: flex;
    margin-left: 10%;
    /* align-items: center; */
    /* justify-content: center; */
    /* min-height: 100vh; */
    background: var(--el-bg-color-page);
}

.card {
    position: relative;
    width: 600px;
    padding: 5% 36px 32px;
    /* border-radius: 12px; */
    /* background: var(--el-fill-color-blank); */
    /* box-shadow: var(--el-box-shadow-light); */
}

/* .theme-toggle {
    position: absolute;
    top: 12px;
    right: 12px;
} */

.login-header {
    text-align: center;
    margin-bottom: 36px;
}

.login-header h1 {
    margin: 0 0 6px;
    font-size: 22px;
    font-weight: 600;
    color: var(--el-text-color-primary);
}

.login-header p {
    margin: 0;
    font-size: 13px;
    color: var(--el-text-color-secondary);
}

.login-button {
    width: 100%;
    margin-top: 8px;
}

.login-footer {
    margin-top: 4px;
    text-align: center;
    font-size: 13px;
    color: var(--el-text-color-secondary);
}
</style>
