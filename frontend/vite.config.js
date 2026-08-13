import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// Vite 配置：开发服务器 + 后端 API 代理
export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    // 将 /api 请求转发到 FastAPI 后端，避免跨域问题
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8003',
        changeOrigin: true,
      },
    },
  },
})
