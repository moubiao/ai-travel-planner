<script setup>
// 结果页：展示旅行方案 + 对话式调整
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import * as echarts from 'echarts'

import { adjustPlan, isLoggedIn, savePlan, visionSimilar } from '../api'
import { planStore } from '../stores/planStore'
import AuthDialog from '../components/AuthDialog.vue'
import ItineraryMap from '../components/ItineraryMap.vue'
import html2canvas from 'html2canvas'
import { jsPDF } from 'jspdf'

const router = useRouter()
// 对比方案模式：variants 存在时展示当前选中变体，否则展示单方案
const variants = computed(() => planStore.variants)
const activeVariant = ref('budget')
const plan = computed(() => (variants.value ? variants.value[activeVariant.value]?.plan : planStore.plan))
const displayRefs = computed(() => (variants.value ? variants.value[activeVariant.value]?.references : planStore.references))
const displayTrace = computed(() => (variants.value ? variants.value[activeVariant.value]?.agent_trace : planStore.agentTrace))
const displayWeather = computed(() => (variants.value ? variants.value[activeVariant.value]?.weather : planStore.weather))
const displayWarnings = computed(() => (variants.value ? variants.value[activeVariant.value]?.plan_warnings : planStore.planWarnings))
const displayQuality = computed(() => (variants.value ? variants.value[activeVariant.value]?.quality_report : planStore.quality))
// 旅行意图理解（来自需求解析的深层推断）
const intent = computed(() => planStore.requirement?.intent || null)
const qualityTagType = computed(() => {
  const level = displayQuality.value?.level
  if (level === '优秀') return 'success'
  if (level === '良好') return 'primary'
  if (level === '一般') return 'warning'
  return 'danger'
})
const adjustInstruction = ref('')
const adjusting = ref(false)
const showAuth = ref(false)
const saving = ref(false)
// 图片相似景点推荐
const visionUploading = ref(false)
const visionResults = ref([])
const visionImageUrl = ref('')

async function onVisionUpload(file) {
  // Element Plus before-upload 钩子传入的是原生 File 对象
  const isImage = file.type.startsWith('image/')
  if (!isImage) {
    ElMessage.warning('请上传图片文件')
    return false
  }
  visionUploading.value = true
  try {
    const city = planStore.requirement?.destination || ''
    const result = await visionSimilar(file, city)
    visionResults.value = result.results || []
    visionImageUrl.value = URL.createObjectURL(file)
    if (!visionResults.value.length) {
      ElMessage.warning('未找到相似景点')
    }
  } catch (err) {
    ElMessage.error(err.message || '图片分析失败')
  } finally {
    visionUploading.value = false
  }
  return false // 阻止默认上传行为
}

function formatScore(score) {
  return (Number(score) * 100).toFixed(1) + '%'
}

// 金额格式化
function formatMoney(value) {
  const num = Number(value) || 0
  return `¥${num.toLocaleString('zh-CN')}`
}

// 每日安排时段（上午/下午/晚上）
const timeSlots = [
  { key: 'morning', label: '上午', icon: '🌅' },
  { key: 'afternoon', label: '下午', icon: '☀️' },
  { key: 'evening', label: '晚上', icon: '🌙' },
]

// ---------- 费用估算饼图 ----------
const chartRef = ref(null)
let chart = null

function renderChart() {
  if (!chartRef.value || !plan.value?.basic_info?.budget_breakdown) return
  if (!chart) chart = echarts.init(chartRef.value)
  const breakdown = plan.value.basic_info.budget_breakdown
  chart.setOption({
    tooltip: { trigger: 'item', formatter: '{b}: ¥{c} ({d}%)' },
    legend: { bottom: 0 },
    series: [
      {
        name: '费用',
        type: 'pie',
        radius: ['40%', '65%'],
        center: ['50%', '45%'],
        label: { formatter: '{b}\n¥{c}' },
        data: Object.entries(breakdown).map(([name, value]) => ({ name, value })),
      },
    ],
  })
}

onMounted(() => nextTick(renderChart))
watch(plan, () => nextTick(renderChart))
onBeforeUnmount(() => chart && chart.dispose())

// ---------- 对比方案：对比表格 ----------
const compareRows = computed(() => {
  if (!variants.value) return []
  const v1 = variants.value.budget?.plan || {}
  const v2 = variants.value.comfort?.plan || {}
  const avgFood = (p) => {
    const foods = p.food_recommendations || []
    if (!foods.length) return '-'
    const avg = foods.reduce((s, f) => s + (Number(f.price_per_person) || 0), 0) / foods.length
    return '¥' + Math.round(avg).toLocaleString('zh-CN')
  }
  const fmt = (v) => '¥' + (Number(v) || 0).toLocaleString('zh-CN')
  return [
    { metric: '总预算', budget: fmt(v1.basic_info?.total_budget), comfort: fmt(v2.basic_info?.total_budget) },
    { metric: '酒店', budget: v1.hotel_recommendation?.name || '-', comfort: v2.hotel_recommendation?.name || '-' },
    { metric: '酒店房价/晚', budget: fmt(v1.hotel_recommendation?.price_per_night), comfort: fmt(v2.hotel_recommendation?.price_per_night) },
    { metric: '美食推荐', budget: (v1.food_recommendations?.length || 0) + ' 家', comfort: (v2.food_recommendations?.length || 0) + ' 家' },
    { metric: '餐饮人均', budget: avgFood(v1), comfort: avgFood(v2) },
    { metric: '行程天数', budget: (v1.daily_schedule?.length || 0) + ' 天', comfort: (v2.daily_schedule?.length || 0) + ' 天' },
  ]
})

// ---------- 每日行程地图 ----------
const MAP_KEY = import.meta.env.VITE_AMAP_JS_KEY || ''
const activeMapDay = ref('1')
const refMap = computed(() => {
  const map = {}
  for (const r of displayRefs.value || []) {
    if (r.type === 'attraction' && r.coordinates?.length === 2) {
      map[r.id] = { name: r.name, coordinates: r.coordinates }
    }
  }
  return map
})
const mapReady = computed(() => plan.value?.daily_schedule?.length && Object.keys(refMap.value).length > 0)

// ---------- 导出行程单（PDF / 长图） ----------
const exporting = ref(false)
const exportRef = ref(null)

async function captureExport() {
  // 隐藏不需要导出的卡片（对比/Agent过程/地图/保存/视觉/调整/导出按钮）
  const hidden = exportRef.value.querySelectorAll('.exclude-export')
  const prev = []
  hidden.forEach((el) => {
    prev.push(el.style.display)
    el.style.display = 'none'
  })
  try {
    return await html2canvas(exportRef.value, {
      scale: 2,
      backgroundColor: '#fff',
      useCORS: true,
      logging: false,
    })
  } finally {
    hidden.forEach((el, i) => { el.style.display = prev[i] })
  }
}

function exportFileName() {
  const dest = plan.value?.basic_info?.destination || '旅行方案'
  return `旅行方案_${dest}_${new Date().toISOString().slice(0, 10)}`
}

async function exportImage() {
  exporting.value = true
  try {
    const canvas = await captureExport()
    const link = document.createElement('a')
    link.download = exportFileName() + '.png'
    link.href = canvas.toDataURL('image/png')
    link.click()
    ElMessage.success('行程单图片已导出')
  } catch (err) {
    ElMessage.error('导出失败：' + (err.message || '未知错误'))
  } finally {
    exporting.value = false
  }
}

async function exportPdf() {
  exporting.value = true
  try {
    const canvas = await captureExport()
    const pdf = new jsPDF('p', 'mm', 'a4')
    const pageW = 210
    const pageH = 297
    const imgW = pageW
    const imgH = (canvas.height * pageW) / canvas.width
    const imgData = canvas.toDataURL('image/jpeg', 0.92)
    let heightLeft = imgH
    let position = 0
    pdf.addImage(imgData, 'JPEG', 0, position, imgW, imgH)
    heightLeft -= pageH
    while (heightLeft > 0) {
      position -= pageH
      pdf.addPage()
      pdf.addImage(imgData, 'JPEG', 0, position, imgW, imgH)
      heightLeft -= pageH
    }
    pdf.save(exportFileName() + '.pdf')
    ElMessage.success('行程单 PDF 已导出')
  } catch (err) {
    ElMessage.error('导出失败：' + (err.message || '未知错误'))
  } finally {
    exporting.value = false
  }
}

// ---------- 保存方案 ----------
async function save() {
  if (!isLoggedIn()) {
    showAuth.value = true
    return
  }
  try {
    const { value: title } = await ElMessageBox.prompt('给这个方案起个标题', '保存方案', {
      inputPlaceholder: '如：成都3天2夜美食文化之旅',
      inputValidator: (v) => (v && v.trim() ? true : '请输入标题'),
    })
    saving.value = true
    await savePlan({
      title: title.trim(),
      requirement: planStore.requirement,
      plan: plan.value,
      references: displayRefs.value,
    })
    ElMessage.success('方案已保存到历史记录')
  } catch (err) {
    if (err !== 'cancel' && err?.message !== 'cancel') {
      ElMessage.error(err.message || '保存失败')
    }
  } finally {
    saving.value = false
  }
}

async function adjust() {
  if (!adjustInstruction.value.trim()) {
    ElMessage.warning('请输入修改要求，例如「预算减少500元」')
    return
  }
  adjusting.value = true
  try {
    const result = await adjustPlan({
      plan: plan.value,
      instruction: adjustInstruction.value.trim(),
    })
    if (variants.value) {
      // 对比模式：只更新当前选中的变体
      planStore.variants[activeVariant.value].plan = result.plan
    } else {
      planStore.plan = result.plan
    }
    adjustInstruction.value = ''
    ElMessage.success('方案已更新！')
  } catch (err) {
    ElMessage.error(err.message || '调整失败，请重试')
  } finally {
    adjusting.value = false
  }
}
</script>

<template>
  <div v-if="plan" class="result-page" ref="exportRef">
    <!-- 方案对比（变体模式） -->
    <el-card v-if="variants" shadow="never" class="section-card compare-card exclude-export">
      <template #header>
        <span class="section-title">⚖️ 方案对比</span>
        <span class="ref-subtitle">两套风格方案并行生成，点击标签切换查看</span>
      </template>
      <div class="compare-row">
        <el-radio-group v-model="activeVariant" size="large">
          <el-radio-button value="budget">💸 {{ variants.budget?.label }}</el-radio-button>
          <el-radio-button value="comfort">✨ {{ variants.comfort?.label }}</el-radio-button>
        </el-radio-group>
        <span class="save-hint">当前查看：{{ variants[activeVariant]?.label }}（总预算 {{ formatMoney(variants[activeVariant]?.plan?.basic_info?.total_budget) }}）</span>
      </div>
      <el-table :data="compareRows" size="small" border class="compare-table">
        <el-table-column prop="metric" label="对比项" width="110" />
        <el-table-column prop="budget" :label="variants.budget?.label" />
        <el-table-column prop="comfort" :label="variants.comfort?.label" />
      </el-table>
    </el-card>

    <!-- Agent 执行过程 -->
    <el-card v-if="displayTrace?.length" shadow="never" class="section-card agent-card exclude-export">
      <template #header>
        <span class="section-title">🤖 Agent 规划过程</span>
        <span class="ref-subtitle">LangGraph 工作流：需求分析 → 知识检索 → 天气查询 → 专家Agent并行 → 方案生成 → 行程校验 → 质量评估</span>
      </template>
      <el-timeline>
        <el-timeline-item
          v-for="(t, i) in displayTrace"
          :key="i"
          :type="i === displayTrace.length - 1 ? 'success' : 'primary'"
        >
          <div class="agent-node">
            <span class="agent-node-name">{{ t.node }}</span>
            <span class="agent-node-time">{{ t.time }}</span>
          </div>
          <div class="agent-node-detail">{{ t.detail }}</div>
        </el-timeline-item>
      </el-timeline>
    </el-card>

    <!-- 方案质量评分 -->
    <el-card v-if="displayQuality?.overall_score != null" shadow="never" class="section-card quality-card">
      <template #header>
        <span class="section-title">📊 方案质量评分</span>
        <span class="ref-subtitle">规则 + LLM 双引擎自动评估，低分自动改进重生成</span>
      </template>
      <div class="quality-row">
        <el-progress
          type="dashboard"
          :percentage="displayQuality.overall_score"
          :width="110"
          :stroke-width="10"
          :color="displayQuality.overall_score >= 85 ? '#67c23a' : displayQuality.overall_score >= 70 ? '#409eff' : '#e6a23c'"
        >
          <template #default>
            <div class="quality-score">
              <div class="quality-num">{{ displayQuality.overall_score }}</div>
              <el-tag :type="qualityTagType" size="small" effect="dark">{{ displayQuality.level }}</el-tag>
            </div>
          </template>
        </el-progress>
        <div class="quality-dims">
          <div v-for="d in displayQuality.dimensions" :key="d.name" class="quality-dim">
            <div class="quality-dim-head">
              <span class="quality-dim-name">{{ d.name }}</span>
              <span class="quality-dim-score" :class="{ 'low': d.score < 80 }">{{ d.score }}分</span>
            </div>
            <el-progress
              :percentage="d.score"
              :stroke-width="8"
              :color="d.score >= 80 ? '#67c23a' : d.score >= 60 ? '#e6a23c' : '#f56c6c'"
            />
            <div class="quality-dim-detail">{{ d.detail }}</div>
          </div>
        </div>
      </div>
      <el-alert
        v-for="(s, i) in displayQuality.suggestions"
        :key="i"
        :title="'改进建议：' + s"
        type="warning"
        :closable="false"
        show-icon
        class="tip-item"
      />
    </el-card>

    <!-- 旅行意图理解 -->
    <el-card v-if="intent" shadow="never" class="section-card intent-card">
      <template #header>
        <span class="section-title">🧠 旅行意图理解</span>
        <span class="ref-subtitle">AI 对需求的深层理解（隐含意图推断）</span>
      </template>
      <div class="intent-summary">「{{ intent.summary }}」</div>
      <div class="intent-row">
        <span class="intent-label">关键约束</span>
        <el-tag v-for="p in intent.priorities" :key="p" type="primary" effect="plain" class="ref-tag">{{ p }}</el-tag>
      </div>
      <div v-if="intent.hidden_needs?.length" class="intent-row">
        <span class="intent-label">隐含需求</span>
        <el-tag v-for="h in intent.hidden_needs" :key="h" type="warning" effect="plain" class="ref-tag">{{ h }}</el-tag>
      </div>
    </el-card>

    <!-- 天气预报 -->
    <el-card v-if="displayWeather?.days?.length" shadow="never" class="section-card">
      <template #header>
        <span class="section-title">🌤️ 行程天气预报</span>
        <span v-if="displayWeather.is_demo" class="ref-subtitle">演示数据（配置和风天气 key 后使用真实预报）</span>
      </template>
      <el-row :gutter="12">
        <el-col v-for="day in displayWeather.days" :key="day.date + (day.city || '')" :span="Math.floor(24 / displayWeather.days.length)">
          <div class="weather-day" :class="{ 'weather-rain': day.is_rain }">
            <div class="weather-date">{{ day.date }}<span v-if="day.city"> · {{ day.city }}</span></div>
            <div class="weather-text">{{ day.is_rain ? '🌧️ ' : '☀️ ' }}{{ day.text_day }}</div>
            <div class="weather-temp">{{ day.temp_min }}~{{ day.temp_max }}°C</div>
            <div class="weather-precip">降水 {{ day.precip_prob }}%</div>
            <el-tag v-if="day.is_rain" type="danger" size="small">雨天·建议室内</el-tag>
          </div>
        </el-col>
      </el-row>
    </el-card>

    <!-- 基本信息 -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <span class="section-title">📋 行程基本信息</span>
      </template>
      <el-descriptions :column="3" border>
        <el-descriptions-item label="目的地">{{ plan.basic_info?.destination }}</el-descriptions-item>
        <el-descriptions-item label="旅行天数">{{ plan.basic_info?.trip_days }} 天</el-descriptions-item>
        <el-descriptions-item label="出行人数">{{ plan.basic_info?.people }} 人</el-descriptions-item>
        <el-descriptions-item label="日期">{{ plan.basic_info?.dates || '未指定' }}</el-descriptions-item>
        <el-descriptions-item label="总预算">{{ formatMoney(plan.basic_info?.total_budget) }}</el-descriptions-item>
        <el-descriptions-item label="人均预算">
          {{ formatMoney((plan.basic_info?.total_budget || 0) / (plan.basic_info?.people || 1)) }}
        </el-descriptions-item>
      </el-descriptions>
    </el-card>

    <!-- 每日安排 -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <span class="section-title">🗓️ 每日行程安排</span>
      </template>
      <el-timeline>
        <el-timeline-item
          v-for="day in plan.daily_schedule"
          :key="day.day"
          :timestamp="`Day ${day.day} ${day.date || ''} · ${day.city || ''}${day.city ? ' · ' : ''}${day.theme || ''}`"
          placement="top"
          :type="day.day % 2 === 0 ? 'success' : 'primary'"
        >
          <el-row :gutter="12">
            <el-col v-for="slot in timeSlots" :key="slot.key" :span="8">
              <div class="slot-card">
                <div class="slot-title">{{ slot.icon }} {{ slot.label }}</div>
                <div class="slot-activity">{{ day[slot.key]?.activity }}</div>
                <div v-if="day[slot.key]?.location" class="slot-location">
                  📍 {{ day[slot.key].location }}
                </div>
                <div class="slot-reason">{{ day[slot.key]?.reason }}</div>
                <div class="slot-cost">{{ formatMoney(day[slot.key]?.cost) }}</div>
              </div>
            </el-col>
          </el-row>
        </el-timeline-item>
      </el-timeline>
    </el-card>

    <!-- 每日行程地图 -->
    <el-card v-if="mapReady" shadow="never" class="section-card map-card exclude-export">
      <template #header>
        <span class="section-title">🗺️ 每日行程地图</span>
        <span class="ref-subtitle">{{ MAP_KEY ? '高德地图 · 序号为当日景点顺序' : '示意地图（frontend/.env 配置 VITE_AMAP_JS_KEY 后启用真实地图）' }}</span>
      </template>
      <el-tabs v-model="activeMapDay">
        <el-tab-pane
          v-for="d in plan.daily_schedule"
          :key="d.day"
          :label="`Day ${d.day}${d.date ? ' · ' + d.date.slice(5) : ''}${d.city ? ' · ' + d.city : ''}`"
          :name="String(d.day)"
          lazy
        >
          <ItineraryMap :day="d" :ref-map="refMap" />
        </el-tab-pane>
      </el-tabs>
    </el-card>

    <el-row :gutter="16">
      <!-- 美食推荐 -->
      <el-col :span="14">
        <el-card shadow="never" class="section-card">
          <template #header>
            <span class="section-title">🍜 美食推荐</span>
          </template>
          <el-table :data="plan.food_recommendations" size="small">
            <el-table-column prop="name" label="美食" min-width="120" />
            <el-table-column prop="category" label="类型" width="80" />
            <el-table-column prop="area" label="区域" width="90" />
            <el-table-column label="人均" width="90">
              <template #default="{ row }">{{ formatMoney(row.price_per_person) }}</template>
            </el-table-column>
            <el-table-column prop="reason" label="推荐理由" min-width="160" />
          </el-table>
        </el-card>
      </el-col>

      <!-- 酒店推荐 + 费用估算 -->
      <el-col :span="10">
        <el-card shadow="never" class="section-card">
          <template #header>
            <span class="section-title">🏨 酒店推荐</span>
          </template>
          <div class="hotel-name">{{ plan.hotel_recommendation?.name }}</div>
          <div class="hotel-meta">📍 {{ plan.hotel_recommendation?.area }}</div>
          <div class="hotel-meta">{{ formatMoney(plan.hotel_recommendation?.price_per_night) }} / 晚</div>
          <div class="slot-reason">{{ plan.hotel_recommendation?.reason }}</div>
        </el-card>

        <el-card shadow="never" class="section-card">
          <template #header>
            <span class="section-title">💰 费用估算</span>
          </template>
          <div ref="chartRef" class="chart-box" />
        </el-card>
      </el-col>
    </el-row>

    <!-- 实用建议 -->
    <el-card v-if="plan.tips?.length" shadow="never" class="section-card">
      <template #header>
        <span class="section-title">💡 实用建议</span>
      </template>
      <el-alert
        v-for="(tip, i) in plan.tips"
        :key="i"
        :title="tip"
        type="info"
        :closable="false"
        class="tip-item"
      />
    </el-card>

    <!-- 知识库引用来源 -->
    <el-card v-if="displayRefs?.length" shadow="never" class="section-card">
      <template #header>
        <span class="section-title">📚 知识库引用来源</span>
        <span class="ref-subtitle">方案中的推荐均来自旅游知识库（RAG 检索）</span>
      </template>
      <el-tooltip
        v-for="ref in displayRefs"
        :key="ref.id"
        placement="top"
        :content="`${ref.city_name || ''} · ${ref.type === 'attraction' ? '景点' : ref.type === 'food' ? '美食' : '酒店'} · 来源：${ref.source || '未标注'}${ref.verified_at ? ' · 校验于 ' + ref.verified_at : ''}`"
      >
        <el-tag
          :type="ref.type === 'attraction' ? 'primary' : ref.type === 'food' ? 'warning' : 'success'"
          class="ref-tag"
          effect="plain"
        >
          {{ ref.name }}
        </el-tag>
      </el-tooltip>
    </el-card>

    <!-- 行程校验警告 -->
    <el-card v-if="displayWarnings?.length" shadow="never" class="section-card warn-card">
      <template #header>
        <span class="section-title">⚠️ 行程校验提示</span>
        <span class="ref-subtitle">AI 自动检测的行程合理性建议</span>
      </template>
      <el-alert
        v-for="(w, i) in displayWarnings"
        :key="i"
        :title="w.message"
        :type="w.level === 'warning' ? 'warning' : 'info'"
        :closable="false"
        show-icon
        class="tip-item"
      />
    </el-card>

    <!-- 导出行程单 -->
    <el-card shadow="never" class="section-card export-card exclude-export">
      <template #header>
        <span class="section-title">📤 导出行程单</span>
        <span class="ref-subtitle">生成可打印 / 分享的行程单</span>
      </template>
      <div class="save-row">
        <span class="save-hint">包含基本信息、每日行程、美食酒店与费用估算</span>
        <div>
          <el-button :loading="exporting" @click="exportPdf">📄 导出 PDF</el-button>
          <el-button type="primary" plain :loading="exporting" @click="exportImage">🖼️ 导出图片</el-button>
        </div>
      </div>
    </el-card>

    <!-- 保存方案 -->
    <el-card shadow="never" class="section-card save-card exclude-export">
      <template #header>
        <span class="section-title">💾 保存方案</span>
      </template>
      <div class="save-row">
        <span class="save-hint">登录后可保存方案到历史记录，随时回看</span>
        <el-button type="success" :loading="saving" @click="save">保存到历史记录</el-button>
      </div>
    </el-card>

    <!-- 多模态：上传照片找相似景点 -->
    <el-card shadow="never" class="section-card vision-card exclude-export">
      <template #header>
        <span class="section-title">📷 上传照片，AI 帮你找相似景点</span>
        <span class="ref-subtitle">多模态理解（Chinese-CLIP）：分析照片风格，推荐知识库中相似的地点</span>
      </template>
      <div class="vision-row">
        <el-upload
          :show-file-list="false"
          :before-upload="onVisionUpload"
          accept="image/*"
        >
          <el-button type="primary" plain :loading="visionUploading">
            {{ visionUploading ? 'AI 分析中…' : '📤 上传旅行照片' }}
          </el-button>
        </el-upload>
        <span class="save-hint">支持 jpg/png/webp，推荐与当前目的地（{{ planStore.requirement?.destination || '全部城市' }}）相似的景点</span>
      </div>
      <div v-if="visionResults.length" class="vision-results">
        <el-row :gutter="12">
          <el-col :span="6" v-if="visionImageUrl">
            <el-image :src="visionImageUrl" fit="cover" class="vision-img" />
          </el-col>
          <el-col v-for="r in visionResults" :key="r.id" :span="visionImageUrl ? 18 / visionResults.length : 24 / visionResults.length">
            <div class="vision-item">
              <div class="vision-name">📍 {{ r.name }}</div>
              <div class="vision-meta">{{ r.city_name }} · 相似度 {{ formatScore(r.score) }}</div>
              <div class="vision-desc">{{ r.description }}</div>
            </div>
          </el-col>
        </el-row>
      </div>
    </el-card>

    <!-- 对话式调整 -->
    <el-card shadow="never" class="section-card adjust-card exclude-export">
      <template #header>
        <span class="section-title">🔄 调整方案</span>
      </template>
      <div class="adjust-row">
        <el-input
          v-model="adjustInstruction"
          placeholder="告诉 AI 你想怎么改，例如：预算减少500元 / 不要寺庙，多安排购物"
          @keyup.enter="adjust"
        />
        <el-button type="primary" :loading="adjusting" @click="adjust">调整</el-button>
      </div>
      <div class="adjust-actions">
        <el-button text type="primary" @click="router.push('/')">不满意？重新规划</el-button>
      </div>
    </el-card>
  </div>

  <!-- 无方案时（直接访问结果页） -->
  <el-empty v-else description="还没有旅行方案，先去规划一个吧">
    <el-button type="primary" @click="router.push('/')">去规划</el-button>
  </el-empty>

  <AuthDialog v-model="showAuth" />
</template>

<style scoped>
.result-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.section-card {
  border-radius: 12px;
}

.section-title {
  font-size: 16px;
  font-weight: 600;
}

/* 每日时段卡片 */
.slot-card {
  background: #f5f7fa;
  border-radius: 8px;
  padding: 10px 12px;
  height: 100%;
  box-sizing: border-box;
}

.slot-title {
  font-weight: 600;
  color: #303133;
  margin-bottom: 6px;
}

.slot-activity {
  font-size: 14px;
  color: #303133;
  font-weight: 500;
}

.slot-location {
  font-size: 12px;
  color: #409eff;
  margin: 4px 0;
}

.slot-reason {
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
}

.slot-cost {
  font-size: 13px;
  color: #e6a23c;
  font-weight: 600;
  margin-top: 6px;
}

/* 酒店卡片 */
.hotel-name {
  font-size: 15px;
  font-weight: 600;
  color: #303133;
  margin-bottom: 6px;
}

.hotel-meta {
  font-size: 13px;
  color: #606266;
  margin-bottom: 4px;
}

/* 费用饼图 */
.chart-box {
  width: 100%;
  height: 240px;
}

/* 建议 */
.tip-item {
  margin-bottom: 8px;
}

/* Agent 过程卡片 */
.agent-card {
  border-color: #409eff;
}

.agent-node {
  display: flex;
  align-items: center;
  gap: 8px;
}

.agent-node-name {
  font-weight: 600;
  color: #409eff;
}

.agent-node-time {
  font-size: 12px;
  color: #909399;
}

.agent-node-detail {
  font-size: 13px;
  color: #606266;
  white-space: pre-wrap;
  word-break: break-all;
}

/* 天气卡片 */
.weather-day {
  background: #f5f7fa;
  border-radius: 8px;
  padding: 10px;
  text-align: center;
}

.weather-rain {
  background: #fef0f0;
  border: 1px solid #f56c6c;
}

.weather-date {
  font-size: 12px;
  color: #909399;
}

.weather-text {
  font-size: 15px;
  font-weight: 600;
  color: #303133;
  margin: 4px 0;
}

.weather-temp {
  font-size: 13px;
  color: #e6a23c;
  font-weight: 600;
}

.weather-precip {
  font-size: 12px;
  color: #909399;
  margin-bottom: 4px;
}

/* 引用来源 */
.ref-subtitle {
  font-size: 12px;
  color: #909399;
  margin-left: 8px;
  font-weight: normal;
}

.ref-tag {
  margin: 0 8px 8px 0;
}

/* 保存区 */
.save-card {
  border-color: #67c23a;
}

.save-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.save-hint {
  font-size: 13px;
  color: #909399;
}

/* 多模态视觉区 */
.vision-card {
  border-color: #b37feb;
}

.vision-row {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.vision-results {
  margin-top: 16px;
}

.vision-img {
  width: 100%;
  height: 120px;
  border-radius: 8px;
}

.vision-item {
  background: #f5f7fa;
  border-radius: 8px;
  padding: 10px;
  margin-bottom: 8px;
  height: 100%;
  box-sizing: border-box;
}

.vision-name {
  font-weight: 600;
  color: #303133;
  font-size: 14px;
}

.vision-meta {
  font-size: 12px;
  color: #b37feb;
  margin: 4px 0;
}

.vision-desc {
  font-size: 12px;
  color: #909399;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

/* 警告卡片 */
.warn-card {
  border-color: #e6a23c;
}

/* 方案对比区 */
.compare-card {
  border-color: #409eff;
}

.compare-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 12px;
}

.compare-table {
  width: 100%;
}

/* 地图卡片 */
.map-card {
  border-color: #409eff;
}

/* 质量评分卡 */
.quality-card {
  border-color: #67c23a;
}

.quality-row {
  display: flex;
  gap: 24px;
  align-items: flex-start;
  flex-wrap: wrap;
}

.quality-score {
  text-align: center;
}

.quality-num {
  font-size: 26px;
  font-weight: 700;
  color: #303133;
  line-height: 1.2;
}

.quality-dims {
  flex: 1;
  min-width: 260px;
}

.quality-dim {
  margin-bottom: 12px;
}

.quality-dim-head {
  display: flex;
  justify-content: space-between;
  margin-bottom: 4px;
}

.quality-dim-name {
  font-size: 13px;
  color: #303133;
  font-weight: 500;
}

.quality-dim-score {
  font-size: 13px;
  font-weight: 600;
  color: #67c23a;
}

.quality-dim-score.low {
  color: #e6a23c;
}

.quality-dim-detail {
  font-size: 12px;
  color: #909399;
  margin-top: 3px;
}

/* 意图理解卡 */
.intent-card {
  border-color: #b37feb;
}

.intent-summary {
  font-size: 15px;
  font-weight: 600;
  color: #303133;
  margin-bottom: 8px;
}

.intent-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px;
  margin-bottom: 4px;
}

.intent-label {
  font-size: 13px;
  color: #909399;
  margin-right: 8px;
}

/* 导出区 */
.export-card {
  border-color: #409eff;
}

/* 调整区 */
.adjust-card {
  border-color: #e6a23c;
}

.adjust-row {
  display: flex;
  gap: 12px;
}

.adjust-actions {
  margin-top: 8px;
  text-align: right;
}
</style>
