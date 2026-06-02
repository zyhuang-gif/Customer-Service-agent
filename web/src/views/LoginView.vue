<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '../stores/auth'

const username = ref('agent')
const password = ref('agent123')
const loading = ref(false)
const auth = useAuthStore()
const router = useRouter()

async function doLogin() {
  loading.value = true
  try {
    await auth.login(username.value, password.value)
    ElMessage.success('登录成功')
    router.push('/agent-desk')
  } catch (e) {
    ElMessage.error(e.message || '登录失败')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="login-page">
    <el-card class="login-card">
      <h2>坐席登录</h2>
      <el-form @submit.prevent="doLogin">
        <el-form-item>
          <el-input v-model="username" placeholder="用户名" />
        </el-form-item>
        <el-form-item>
          <el-input v-model="password" type="password" placeholder="密码" show-password />
        </el-form-item>
        <el-button type="primary" :loading="loading" style="width: 100%" @click="doLogin">登录</el-button>
      </el-form>
      <p class="hint">演示账号：agent / agent123</p>
    </el-card>
  </div>
</template>

<style scoped>
.login-page { display: flex; justify-content: center; align-items: center; height: 100vh; background: #f5f7fa; }
.login-card { width: 360px; }
.hint { color: #909399; font-size: 13px; margin-top: 12px; text-align: center; }
</style>
