// 全局方案状态：跨页面传递当前方案与结构化需求
import { reactive } from 'vue'

export const planStore = reactive({
  plan: null, // 当前旅行方案
  requirement: null, // 结构化旅行需求
  references: [], // 方案引用的知识库来源
  agentTrace: [], // Agent 执行过程（节点日志）
  weather: null, // 天气预报信息
  planWarnings: [], // 行程校验警告
  quality: null, // 方案质量报告（规则+LLM 双引擎评分）
  variants: null, // 对比方案 {budget: {...}, comfort: {...}}（可选）
})
