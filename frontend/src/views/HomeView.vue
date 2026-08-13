<script setup>
// 首页：旅行需求输入（表单 + 自然语言两种方式）
import { reactive, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'

import { generatePlan } from '../api'
import { planStore } from '../stores/planStore'

const router = useRouter()
const loading = ref(false)
const listening = ref(false)

// 语音输入（Web Speech API，Chrome/Edge 支持）
function startVoiceInput() {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition
  if (!SpeechRecognition) {
    ElMessage.warning('当前浏览器不支持语音输入，请使用 Chrome 或 Edge')
    return
  }
  const recognition = new SpeechRecognition()
  recognition.lang = 'zh-CN'
  recognition.interimResults = false
  recognition.onstart = () => {
    listening.value = true
    ElMessage.info('正在聆听，请说出你的旅行需求…')
  }
  recognition.onresult = (event) => {
    const text = event.results[0][0].transcript
    form.requirement = (form.requirement + ' ' + text).trim()
    ElMessage.success('已识别：' + text)
  }
  recognition.onerror = () => {
    listening.value = false
    ElMessage.error('语音识别失败，请检查麦克风权限')
  }
  recognition.onend = () => {
    listening.value = false
  }
  recognition.start()
}

// 表单数据
const form = reactive({
  requirement: '',
  destination: '',
  dateRange: [],
  days: 3,
  people: 2,
  budget: 4000,
  preferences: [],
  specialRequirements: '',
  variants: false, // 是否生成对比方案
  pace: 'standard', // 行程节奏：fast/standard/slow
})

// 行程节奏选项
const paceOptions = [
  { value: 'fast', label: '🔥 特种兵式', desc: '每天4-6个活动，行程紧凑' },
  { value: 'standard', label: '👍 标准', desc: '劳逸结合，节奏适中' },
  { value: 'slow', label: '🍵 慢游', desc: '每天1-2个主景点，深度体验' },
]

// 偏好选项
const preferenceOptions = [
  '美食', '自然风光', '历史文化', '购物', '亲子', '户外', '城市休闲', '夜生活',
]

// 示例需求：点击快速填充
const examples = [
  '成都3天2夜，两个人，预算4000，喜欢美食和历史文化，不要购物',
  '昆明4天3夜，一家三口带5岁小孩，预算6000，喜欢自然风光，节奏慢一点',
  '成都5天，一个人，预算3000，喜欢户外和摄影',
]

function fillExample(text) {
  form.requirement = text
}

// 选择日期范围时自动计算天数
watch(() => form.dateRange, (range) => {
  if (range && range.length === 2) {
    const start = new Date(range[0])
    const end = new Date(range[1])
    const diff = Math.round((end - start) / 86400000)
    form.days = diff + 1
  }
})

async function submit() {
  // 校验：自然语言 或 目的地 至少填一个
  const hasRequirement = form.requirement.trim() !== ''
  const hasForm = form.destination.trim() !== ''
  if (!hasRequirement && !hasForm) {
    ElMessage.warning('请填写目的地，或直接描述你的旅行需求')
    return
  }
  loading.value = true
  try {
    let payload
    if (hasRequirement && !hasForm) {
      // 只填了自然语言：交给后端解析，避免表单默认值覆盖自然语言信息
      payload = { requirement: form.requirement.trim(), variants: form.variants, pace: form.pace }
    } else {
      // 填了表单（或两者都填）：表单字段优先，自然语言作为补充
      payload = {
        requirement: form.requirement.trim(),
        destination: form.destination.trim(),
        start_date: form.dateRange[0] || '',
        days: form.days,
        people: form.people,
        budget: form.budget,
        preferences: form.preferences,
        special_requirements: form.specialRequirements.trim(),
        variants: form.variants,
        pace: form.pace,
      }
    }
    const result = await generatePlan(payload)
    if (result.variants) {
      // 对比模式：两套方案（性价比版/舒适版）
      planStore.variants = result.variants
      planStore.plan = null
      planStore.references = []
      planStore.agentTrace = []
      planStore.weather = null
      planStore.planWarnings = []
      planStore.quality = null
    } else {
      planStore.variants = null
      planStore.plan = result.plan
      planStore.references = result.references || []
      planStore.agentTrace = result.agent_trace || []
      planStore.weather = result.weather || null
      planStore.planWarnings = result.plan_warnings || []
      planStore.quality = result.quality_report || null
    }
    planStore.requirement = result.structured_requirement
    router.push('/result')
  } catch (err) {
    ElMessage.error(err.message || '生成失败，请重试')
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <el-card shadow="never" class="home-card">
    <template #header>
      <div class="card-header">
        <span class="card-title">🌏 开始规划你的旅程</span>
        <span class="card-subtitle">AI 帮你定制个性化旅行方案</span>
      </div>
    </template>

    <!-- 自然语言输入 -->
    <el-form label-position="top">
      <el-form-item label="直接描述你的旅行需求">
        <div class="voice-row">
          <el-input
            v-model="form.requirement"
            type="textarea"
            :rows="3"
            placeholder="例如：成都3天2夜，两个人，预算4000，喜欢美食和历史文化，不要购物"
          />
          <el-tooltip content="语音输入（需 Chrome/Edge）" placement="top">
            <el-button
              :type="listening ? 'danger' : 'primary'"
              circle
              class="voice-btn"
              @click="startVoiceInput"
            >
              <span :class="{ 'voice-pulse': listening }">🎤</span>
            </el-button>
          </el-tooltip>
        </div>
        <div class="example-row">
          <span class="example-label">试试：</span>
          <el-tag
            v-for="(ex, i) in examples"
            :key="i"
            class="example-tag"
            type="info"
            effect="plain"
            @click="fillExample(ex)"
          >
            {{ ex }}
          </el-tag>
        </div>
      </el-form-item>

      <el-divider content-position="center">或填写详细表单</el-divider>

      <el-row :gutter="16">
        <el-col :span="12">
          <el-form-item label="目的地">
            <el-input v-model="form.destination" placeholder="如：成都 / 昆明" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="出行日期">
            <el-date-picker
              v-model="form.dateRange"
              type="daterange"
              range-separator="至"
              start-placeholder="出发日期"
              end-placeholder="返回日期"
              value-format="YYYY-MM-DD"
              style="width: 100%"
            />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="旅行天数">
            <el-input-number v-model="form.days" :min="1" :max="30" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="出行人数">
            <el-input-number v-model="form.people" :min="1" :max="20" />
          </el-form-item>
        </el-col>
        <el-col :span="24">
          <el-form-item label="总预算（元）">
            <el-input-number v-model="form.budget" :min="100" :max="100000" :step="500" />
          </el-form-item>
        </el-col>
        <el-col :span="24">
          <el-form-item label="兴趣偏好">
            <el-checkbox-group v-model="form.preferences">
              <el-checkbox v-for="opt in preferenceOptions" :key="opt" :label="opt" />
            </el-checkbox-group>
          </el-form-item>
        </el-col>
        <el-col :span="24">
          <el-form-item label="特殊需求">
            <el-input
              v-model="form.specialRequirements"
              placeholder="如：不要寺庙、需要无障碍设施、每天不要太赶…"
            />
          </el-form-item>
        </el-col>
      </el-row>

      <el-form-item label="行程节奏">
        <el-radio-group v-model="form.pace">
          <el-radio-button v-for="p in paceOptions" :key="p.value" :value="p.value">
            {{ p.label }}
          </el-radio-button>
        </el-radio-group>
        <div class="pace-desc">{{ paceOptions.find(p => p.value === form.pace)?.desc }}</div>
      </el-form-item>

      <el-form-item>
        <el-button type="primary" size="large" :loading="loading" @click="submit">
          生成旅行方案
        </el-button>
        <el-checkbox v-model="form.variants" class="variants-check">
          ⚖️ 生成对比方案（性价比版 vs 舒适版，两套并行生成，耗时稍长）
        </el-checkbox>
      </el-form-item>
    </el-form>
  </el-card>
</template>

<style scoped>
.home-card {
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

.example-row {
  margin-top: 8px;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

.voice-row {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  width: 100%;
}

.voice-btn {
  margin-top: 4px;
  flex-shrink: 0;
  font-size: 16px;
}

.voice-pulse {
  animation: voice-pulse 1s infinite;
}

@keyframes voice-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.3; }
}

.example-label {
  font-size: 13px;
  color: #909399;
}

.example-tag {
  cursor: pointer;
}

.variants-check {
  margin-left: 16px;
}

.pace-desc {
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
}
</style>
