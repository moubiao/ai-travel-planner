<script setup>
// 应用外壳：顶部导航 + 用户登录 + 页面出口
import { ref } from 'vue'
import { ElMessage } from 'element-plus'

import AuthDialog from './components/AuthDialog.vue'
import { clearAuth, getUsername, isLoggedIn } from './api'

const showAuth = ref(false)
const username = ref(getUsername())

function handleAuthSuccess(name) {
  username.value = name
}

function logout() {
  clearAuth()
  username.value = ''
  ElMessage.success('已退出登录')
}
</script>

<template>
  <el-container class="app-container">
    <el-header class="app-header">
      <div class="header-left">
        <div class="header-title" @click="$router.push('/')">✈️ AI旅行规划助手</div>
        <el-button text @click="$router.push('/')">开始规划</el-button>
        <el-button text @click="$router.push('/history')">历史记录</el-button>
      </div>
      <div class="header-right">
        <template v-if="username">
          <el-dropdown @command="(cmd) => cmd === 'logout' && logout()">
            <span class="user-name">👤 {{ username }}</span>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="logout">退出登录</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </template>
        <el-button v-else type="primary" size="small" @click="showAuth = true">登录 / 注册</el-button>
      </div>
    </el-header>
    <el-main class="app-main">
      <router-view />
    </el-main>

    <AuthDialog v-model="showAuth" @success="handleAuthSuccess" />
  </el-container>
</template>

<style>
/* 全局基础样式 */
body {
  margin: 0;
  background: #f5f7fa;
  font-family: 'Helvetica Neue', Helvetica, 'PingFang SC', 'Microsoft YaHei', Arial, sans-serif;
}

.app-container {
  min-height: 100vh;
}

.app-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: #fff;
  border-bottom: 1px solid #e4e7ed;
}

.header-left {
  display: flex;
  align-items: center;
}

.header-title {
  font-size: 20px;
  font-weight: 600;
  color: #409eff;
  cursor: pointer;
  margin-right: 8px;
}

.header-right {
  display: flex;
  align-items: center;
}

.user-name {
  cursor: pointer;
  color: #303133;
  font-size: 14px;
}

.app-main {
  max-width: 1000px;
  width: 100%;
  margin: 0 auto;
  padding-top: 24px;
}
</style>
