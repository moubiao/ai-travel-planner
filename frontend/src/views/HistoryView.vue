<script setup>
// 历史记录页：我的旅行方案列表
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'

import { deletePlan, getPlan, isLoggedIn, listPlans } from '../api'
import { planStore } from '../stores/planStore'

const router = useRouter()
const plans = ref([])
const loading = ref(false)
const total = ref(0)

async function load() {
  if (!isLoggedIn()) {
    ElMessage.warning('请先登录后查看历史方案')
    router.push('/')
    return
  }
  loading.value = true
  try {
    const result = await listPlans()
    plans.value = result.plans
    total.value = result.total
  } catch (err) {
    ElMessage.error(err.message || '加载失败')
  } finally {
    loading.value = false
  }
}

// 查看方案详情
async function viewPlan(planId) {
  try {
    const detail = await getPlan(planId)
    planStore.variants = null // 历史方案走单方案模式
    planStore.plan = detail.plan
    planStore.requirement = detail.requirement
    planStore.references = detail.references || []
    planStore.agentTrace = []
    planStore.weather = null
    planStore.planWarnings = []
    planStore.quality = null
    router.push('/result')
  } catch (err) {
    ElMessage.error(err.message || '加载方案失败')
  }
}

// 删除方案
async function removePlan(planId) {
  try {
    await ElMessageBox.confirm('确定删除该方案吗？', '删除确认', { type: 'warning' })
    await deletePlan(planId)
    ElMessage.success('已删除')
    load()
  } catch (err) {
    if (err !== 'cancel' && err?.message !== 'cancel') {
      ElMessage.error(err.message || '删除失败')
    }
  }
}

onMounted(load)
</script>

<template>
  <el-card shadow="never" class="history-card">
    <template #header>
      <div class="card-header">
        <span class="card-title">📂 我的历史方案</span>
        <span class="card-subtitle">共 {{ total }} 个方案</span>
      </div>
    </template>

    <div v-loading="loading">
      <el-empty v-if="!loading && plans.length === 0" description="还没有保存过方案">
        <el-button type="primary" @click="router.push('/')">去规划第一个方案</el-button>
      </el-empty>

      <el-table v-else :data="plans" style="width: 100%">
        <el-table-column prop="title" label="方案标题" min-width="180" />
        <el-table-column prop="created_at" label="保存时间" width="170" />
        <el-table-column label="操作" width="160">
          <template #default="{ row }">
            <el-button size="small" type="primary" text @click="viewPlan(row.id)">查看</el-button>
            <el-button size="small" type="danger" text @click="removePlan(row.id)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </el-card>
</template>

<style scoped>
.history-card {
  border-radius: 12px;
}

.card-header {
  display: flex;
  align-items: baseline;
  gap: 12px;
}

.card-title {
  font-size: 18px;
  font-weight: 600;
}

.card-subtitle {
  font-size: 13px;
  color: #909399;
}
</style>
