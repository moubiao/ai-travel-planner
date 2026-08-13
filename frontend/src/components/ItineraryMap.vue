<script setup>
// 行程地图：展示某一天的景点路线
// - 配置 VITE_AMAP_JS_KEY（高德 JS API key）后使用真实地图（标记 + 连线 + 视野自适应）
// - 未配置时使用 SVG 示意地图（按经纬度相对位置绘制，保证演示效果）
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = defineProps({
  day: { type: Object, required: true }, // 当日行程 {day, date, theme, morning/afternoon/evening}
  refMap: { type: Object, required: true }, // source_id -> {name, coordinates:[lng,lat]}
})

const MAP_KEY = import.meta.env.VITE_AMAP_JS_KEY || ''
const containerRef = ref(null)
let amap = null // 高德地图实例
let markers = []
let polyline = null

// 按时段顺序提取当日景点（有坐标的）
const spots = computed(() => {
  const list = []
  for (const slot of ['morning', 'afternoon', 'evening']) {
    const s = props.day[slot]
    if (s?.source_id && props.refMap[s.source_id]?.coordinates?.length === 2) {
      const ref = props.refMap[s.source_id]
      list.push({ id: s.source_id, name: ref.name, slot, coordinates: ref.coordinates })
    }
  }
  return list
})

const useAmap = computed(() => MAP_KEY && spots.value.length > 0)

// 时段配色（SVG 模式用）
const slotColors = { morning: '#409eff', afternoon: '#e6a23c', evening: '#b37feb' }

// ---------- 高德 JS API 模式 ----------
let amapLoading = false

function loadAmapScript() {
  return new Promise((resolve, reject) => {
    if (window.AMap) return resolve()
    if (amapLoading) return
    amapLoading = true
    const script = document.createElement('script')
    script.src = `https://webapi.amap.com/maps?v=1.4.15&key=${MAP_KEY}`
    script.onload = () => resolve()
    script.onerror = () => reject(new Error('高德地图脚本加载失败'))
    document.head.appendChild(script)
  })
}

async function renderAmap() {
  if (!containerRef.value) return
  try {
    await loadAmapScript()
    if (!amap) {
      amap = new window.AMap.Map(containerRef.value, { zoom: 11 })
    }
    clearAmapOverlays()
    const path = spots.value.map((s) => s.coordinates)
    // 连线
    if (path.length > 1) {
      polyline = new window.AMap.Polyline({
        path,
        strokeColor: '#409eff',
        strokeWeight: 4,
        strokeOpacity: 0.8,
        lineJoin: 'round',
      })
      amap.add(polyline)
    }
    // 标记（带顺序号）
    spots.value.forEach((s, i) => {
      const marker = new window.AMap.Marker({
        position: s.coordinates,
        label: {
          content: `<div class="map-label">${i + 1}</div>`,
          direction: 'center',
          offset: new window.AMap.Pixel(-13, -13),
        },
        title: s.name,
      })
      marker.on('click', () => {
        window.AMap.plugin('AMap.InfoWindow', () => {
          const info = new window.AMap.InfoWindow({ content: `<div style="padding:6px 10px;font-size:13px">${s.name}</div>` })
          info.open(amap, s.coordinates)
        })
      })
      amap.add(marker)
      markers.push(marker)
    })
    amap.setFitView([...markers, ...(polyline ? [polyline] : [])], false, [60, 60, 60, 60])
  } catch (err) {
    console.warn('[map] 高德地图不可用，使用示意地图:', err)
  }
}

function clearAmapOverlays() {
  if (amap) {
    markers.forEach((m) => amap.remove(m))
    if (polyline) amap.remove(polyline)
  }
  markers = []
  polyline = null
}

watch(spots, () => {
  if (useAmap.value) renderAmap()
}, { deep: true })

onMounted(() => {
  if (useAmap.value) renderAmap()
})

onBeforeUnmount(() => {
  clearAmapOverlays()
  if (amap) {
    amap.destroy()
    amap = null
  }
})

// ---------- SVG 示意模式 ----------
const SVG_W = 400
const SVG_H = 260

const svgPoints = computed(() => {
  const pts = spots.value
  if (!pts.length) return []
  const lons = pts.map((p) => p.coordinates[0])
  const lats = pts.map((p) => p.coordinates[1])
  const minLon = Math.min(...lons)
  const maxLon = Math.max(...lons)
  const minLat = Math.min(...lats)
  const maxLat = Math.max(...lats)
  const pad = 40
  const lonSpan = maxLon - minLon || 0.01
  const latSpan = maxLat - minLat || 0.01
  return pts.map((p, i) => {
    const x = pad + ((p.coordinates[0] - minLon) / lonSpan) * (SVG_W - pad * 2)
    // SVG y 轴向下，纬度越高越靠上 → 取反
    const y = pad + ((maxLat - p.coordinates[1]) / latSpan) * (SVG_H - pad * 2)
    return { ...p, x, y, color: slotColors[p.slot] || '#409eff', order: i + 1 }
  })
})

const svgLinePath = computed(() => {
  if (svgPoints.value.length < 2) return ''
  return svgPoints.value.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(' ')
})
</script>

<template>
  <div class="itinerary-map">
    <!-- 高德真实地图 -->
    <div v-if="useAmap" ref="containerRef" class="map-container" />
    <!-- SVG 示意地图（无 key 降级） -->
    <svg v-else-if="svgPoints.length" :viewBox="`0 0 ${SVG_W} ${SVG_H}`" class="map-svg">
      <rect :width="SVG_W" :height="SVG_H" rx="8" fill="#f0f6ff" />
      <!-- 网格线 -->
      <g stroke="#dbe9ff" stroke-width="1">
        <line v-for="i in 5" :key="`v${i}`" :x1="i * SVG_W / 5" y1="0" :x2="i * SVG_W / 5" :y2="SVG_H" />
        <line v-for="i in 4" :key="`h${i}`" x1="0" :y1="i * SVG_H / 4" :x2="SVG_W" :y2="i * SVG_H / 4" />
      </g>
      <!-- 路线连线 -->
      <path
        v-if="svgLinePath"
        :d="svgLinePath"
        fill="none"
        stroke="#409eff"
        stroke-width="2.5"
        stroke-dasharray="6 4"
        stroke-linecap="round"
      />
      <!-- 景点标记 -->
      <g v-for="p in svgPoints" :key="p.id">
        <circle :cx="p.x" :cy="p.y" r="13" fill="#fff" :stroke="p.color" stroke-width="2.5" />
        <text :x="p.x" :y="p.y" text-anchor="middle" dominant-baseline="central" :fill="p.color" font-size="12" font-weight="700">
          {{ p.order }}
        </text>
        <text :x="p.x" :y="p.y + 28" text-anchor="middle" font-size="11" fill="#303133" font-weight="500">
          {{ p.name }}
        </text>
      </g>
      <!-- 图例 -->
      <g font-size="10" fill="#909399">
        <circle cx="14" :cy="SVG_H - 18" r="5" fill="#409eff" />
        <text x="24" :y="SVG_H - 14">上午</text>
        <circle cx="64" :cy="SVG_H - 18" r="5" fill="#e6a23c" />
        <text x="74" :y="SVG_H - 14">下午</text>
        <circle cx="114" :cy="SVG_H - 18" r="5" fill="#b37feb" />
        <text x="124" :y="SVG_H - 14">晚上</text>
      </g>
    </svg>
    <div v-else class="map-empty">本日暂无带坐标的景点</div>
  </div>
</template>

<style scoped>
.itinerary-map {
  width: 100%;
}

.map-container {
  width: 100%;
  height: 300px;
  border-radius: 8px;
  overflow: hidden;
}

.map-svg {
  width: 100%;
  height: 260px;
  display: block;
}

.map-empty {
  height: 120px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #909399;
  font-size: 13px;
  background: #f5f7fa;
  border-radius: 8px;
}
</style>

<style>
/* 高德标记序号（非 scoped，AMap 注入 DOM 需要） */
.map-label {
  background: #409eff;
  color: #fff;
  width: 26px;
  height: 26px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 13px;
  font-weight: 600;
  border: 2px solid #fff;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.25);
}
</style>
