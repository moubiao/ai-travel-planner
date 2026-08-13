<script setup>
// 登录/注册对话框
import { reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'

import { login, register, saveAuth } from '../api'

const props = defineProps({
  modelValue: Boolean, // 是否显示
})
const emit = defineEmits(['update:modelValue', 'success'])

const mode = ref('login') // login / register
const loading = ref(false)
const form = reactive({ username: '', password: '', confirm: '' })

function close() {
  emit('update:modelValue', false)
}

async function submit() {
  // 校验
  if (!form.username.trim() || !form.password) {
    ElMessage.warning('请输入用户名和密码')
    return
  }
  if (mode.value === 'register') {
    if (form.password.length < 6) {
      ElMessage.warning('密码至少 6 位')
      return
    }
    if (form.password !== form.confirm) {
      ElMessage.warning('两次输入的密码不一致')
      return
    }
  }

  loading.value = true
  try {
    const result = mode.value === 'login'
      ? await login({ username: form.username.trim(), password: form.password })
      : await register({ username: form.username.trim(), password: form.password })
    saveAuth(result.token, result.username)
    ElMessage.success(mode.value === 'login' ? '登录成功！' : '注册成功，已自动登录！')
    emit('success', result.username)
    close()
  } catch (err) {
    ElMessage.error(err.message || '操作失败')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <el-dialog
    :model-value="props.modelValue"
    :title="mode === 'login' ? '登录' : '注册账号'"
    width="400px"
    @update:model-value="emit('update:modelValue', $event)"
  >
    <el-form label-position="top" @submit.prevent>
      <el-form-item label="用户名">
        <el-input v-model="form.username" placeholder="2-20位，支持中文" maxlength="20" />
      </el-form-item>
      <el-form-item label="密码">
        <el-input v-model="form.password" type="password" show-password
          placeholder="至少 6 位" @keyup.enter="submit" />
      </el-form-item>
      <el-form-item v-if="mode === 'register'" label="确认密码">
        <el-input v-model="form.confirm" type="password" show-password
          placeholder="再次输入密码" @keyup.enter="submit" />
      </el-form-item>
    </el-form>
    <template #footer>
      <div class="auth-footer">
        <el-button text type="primary" @click="mode = mode === 'login' ? 'register' : 'login'">
          {{ mode === 'login' ? '没有账号？去注册' : '已有账号？去登录' }}
        </el-button>
        <div>
          <el-button @click="close">取消</el-button>
          <el-button type="primary" :loading="loading" @click="submit">
            {{ mode === 'login' ? '登录' : '注册' }}
          </el-button>
        </div>
      </div>
    </template>
  </el-dialog>
</template>

<style scoped>
.auth-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
</style>
