// 路由配置：首页（需求输入）→ 结果页（方案展示与调整）
import { createRouter, createWebHistory } from 'vue-router'

import HomeView from '../views/HomeView.vue'
import ResultView from '../views/ResultView.vue'
import HistoryView from '../views/HistoryView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'home', component: HomeView },
    { path: '/result', name: 'result', component: ResultView },
    { path: '/history', name: 'history', component: HistoryView },
  ],
})

export default router
