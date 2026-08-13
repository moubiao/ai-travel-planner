// API 封装：统一处理请求、错误提示与 JWT 令牌
const BASE = '/api'
const TOKEN_KEY = 'travel_planner_token'
const USER_KEY = 'travel_planner_username'

/** 获取本地保存的令牌 */
export function getToken() {
  return localStorage.getItem(TOKEN_KEY) || ''
}

/** 保存登录状态 */
export function saveAuth(token, username) {
  localStorage.setItem(TOKEN_KEY, token)
  localStorage.setItem(USER_KEY, username)
}

/** 清除登录状态 */
export function clearAuth() {
  localStorage.removeItem(TOKEN_KEY)
  localStorage.removeItem(USER_KEY)
}

/** 当前登录用户名 */
export function getUsername() {
  return localStorage.getItem(USER_KEY) || ''
}

/** 是否已登录 */
export function isLoggedIn() {
  return !!getToken()
}

async function request(path, payload, options = {}) {
  const headers = { 'Content-Type': 'application/json' }
  const token = getToken()
  if (token) headers['Authorization'] = `Bearer ${token}`

  const resp = await fetch(BASE + path, {
    method: options.method || 'POST',
    headers,
    body: payload !== undefined ? JSON.stringify(payload) : undefined,
  })
  const data = await resp.json().catch(() => ({}))
  if (!resp.ok) {
    if (resp.status === 401) {
      clearAuth()
      throw new Error(data.detail || '登录已过期，请重新登录')
    }
    throw new Error(data.detail || `请求失败（${resp.status}）`)
  }
  return data
}

// ---------- 旅行方案 ----------
/** 生成旅行方案（Agent 工作流） */
export function generatePlan(payload) {
  return request('/plans/generate', payload)
}

/** 对话式调整方案 */
export function adjustPlan(payload) {
  return request('/plans/adjust', payload)
}

// ---------- 用户认证 ----------
export function register(payload) {
  return request('/auth/register', payload)
}

export function login(payload) {
  return request('/auth/login', payload)
}

// ---------- 历史方案 ----------
export function savePlan(payload) {
  return request('/history/save', payload)
}

export function listPlans() {
  return request('/history/list', undefined, { method: 'GET' })
}

export function getPlan(planId) {
  return request(`/history/${planId}`, undefined, { method: 'GET' })
}

export function deletePlan(planId) {
  return request(`/history/${planId}`, undefined, { method: 'DELETE' })
}

// ---------- 多模态视觉 ----------
/** 上传照片，推荐相似景点（multipart） */
export async function visionSimilar(file, city = '', topK = 5) {
  const formData = new FormData()
  formData.append('file', file)
  formData.append('city', city)
  formData.append('top_k', String(topK))
  const resp = await fetch(BASE + '/vision/similar', {
    method: 'POST',
    body: formData,
  })
  const data = await resp.json().catch(() => ({}))
  if (!resp.ok) {
    throw new Error(data.detail || `请求失败（${resp.status}）`)
  }
  return data
}
