<template>
  <div class="video-view">
    <!-- 第一行：RGB 原图 + 深度图 -->
    <el-row :gutter="12">
      <!-- RGB 原图 -->
      <el-col :xs="24" :sm="12">
        <div class="tech-card video-card">
          <div class="card-header">
            <span class="card-title"><el-icon><VideoCamera /></el-icon> RGB 图像</span>
            <div class="actions">
              <el-tag size="small" :type="rgbConnected ? 'success' : 'danger'">
                {{ rgbConnected ? '实时' : '离线' }}
              </el-tag>
              <el-button size="small" text @click="screenshot('rgb')"><el-icon><Camera /></el-icon></el-button>
              <el-button size="small" text @click="openFullscreen(rgbSrc)"><el-icon><FullScreen /></el-icon></el-button>
            </div>
          </div>
          <div class="video-container" ref="rgbContainer">
            <img v-if="rgbSrc" :src="rgbSrc" class="video-frame" alt="RGB" />
            <div v-else class="video-placeholder">
              <el-icon size="48"><VideoCamera /></el-icon>
              <p>等待 RGB 图像...</p>
            </div>
            <div class="video-overlay">
              <span class="fps-badge">{{ rgbFps }} fps</span>
              <span class="res-badge">{{ rgbWidth }}×{{ rgbHeight }}</span>
            </div>
          </div>
        </div>
      </el-col>

      <!-- 深度图像 -->
      <el-col :xs="24" :sm="12">
        <div class="tech-card video-card">
          <div class="card-header">
            <span class="card-title"><el-icon><View /></el-icon> 深度图像</span>
            <div class="actions">
              <el-tag size="small" :type="depthConnected ? 'success' : 'danger'">
                {{ depthConnected ? '实时' : '离线' }}
              </el-tag>
              <el-button size="small" text @click="screenshot('depth')"><el-icon><Camera /></el-icon></el-button>
              <el-button size="small" text @click="openFullscreen(depthSrc)"><el-icon><FullScreen /></el-icon></el-button>
            </div>
          </div>
          <div class="video-container" ref="depthContainer">
            <img v-if="depthSrc" :src="depthSrc" class="video-frame" alt="Depth" />
            <div v-else class="video-placeholder">
              <el-icon size="48"><View /></el-icon>
              <p>等待深度图像...</p>
            </div>
            <div class="video-overlay">
              <span class="fps-badge">{{ depthFps }} fps</span>
            </div>
          </div>
          <div class="depth-legend">
            <span class="legend-label">近</span>
            <div class="legend-bar"></div>
            <span class="legend-label">远</span>
          </div>
        </div>
      </el-col>
    </el-row>

    <!-- 第二行：AI 标注图像 + 识别结果列表 -->
    <el-row :gutter="12" class="mt12">
      <!-- 带标注框的 AI 检测图像 -->
      <el-col :xs="24" :sm="14">
        <div class="tech-card video-card">
          <div class="card-header">
            <span class="card-title">
              <el-icon><MagicStick /></el-icon> AI 目标检测
            </span>
            <div class="actions">
              <el-tag size="small" :type="annoConnected ? 'success' : 'info'">
                {{ annoConnected ? '检测中' : '未启动' }}
              </el-tag>
              <span class="det-badge">{{ detections.length }} 目标</span>
              <el-button size="small" text @click="openFullscreen(annoSrc)"><el-icon><FullScreen /></el-icon></el-button>
            </div>
          </div>
          <div class="video-container">
            <img v-if="annoSrc" :src="annoSrc" class="video-frame" alt="Annotated" />
            <div v-else class="video-placeholder">
              <el-icon size="48"><MagicStick /></el-icon>
              <p>等待检测节点发布图像...</p>
              <p class="hint">ros2 launch d435i_detection detection.launch.py</p>
            </div>
            <div class="video-overlay">
              <span class="fps-badge">{{ annoFps }} fps</span>
              <span class="infer-badge" v-if="lastInferMs > 0">{{ lastInferMs }}ms</span>
            </div>
          </div>
        </div>
      </el-col>

      <!-- 识别结果列表 -->
      <el-col :xs="24" :sm="10">
        <div class="tech-card det-panel">
          <div class="card-header">
            <span class="card-title"><el-icon><List /></el-icon> 识别结果</span>
            <div class="actions">
              <span class="det-count">共 {{ detections.length }} 个</span>
            </div>
          </div>

          <!-- 空状态 -->
          <div v-if="detections.length === 0" class="det-empty">
            <el-icon size="32"><Search /></el-icon>
            <p>暂未检测到目标</p>
          </div>

          <!-- 检测结果列表 -->
          <div v-else class="det-list">
            <div
              v-for="(det, idx) in detections"
              :key="idx"
              class="det-item"
            >
              <div class="det-row">
                <span class="det-cls" :style="{ color: classColor(det.class_id) }">
                  {{ det.class_name }}
                </span>
                <span class="det-dist" v-if="det.distance_m > 0">
                  {{ det.distance_m.toFixed(2) }} m
                </span>
                <span class="det-dist dist-unknown" v-else>--</span>
              </div>
              <div class="det-row">
                <div class="conf-bar-wrap">
                  <div
                    class="conf-bar"
                    :style="{
                      width: (det.confidence * 100).toFixed(0) + '%',
                      background: confColor(det.confidence),
                    }"
                  ></div>
                </div>
                <span class="conf-val">{{ (det.confidence * 100).toFixed(0) }}%</span>
              </div>
            </div>
          </div>

          <!-- 帧统计 -->
          <div class="det-footer">
            <span>frame #{{ lastFrameId }}</span>
            <span>{{ lastDetCount }} det</span>
            <span>{{ lastInferMs }} ms</span>
          </div>
        </div>
      </el-col>
    </el-row>

    <!-- 第三行：相机参数 -->
    <el-row :gutter="12" class="mt12">
      <el-col :span="24">
        <div class="tech-card">
          <div class="card-header">
            <span class="card-title"><el-icon><Setting /></el-icon> 相机参数</span>
          </div>
          <el-row :gutter="16">
            <el-col :xs="12" :sm="6" v-for="item in cameraParams" :key="item.label">
              <div class="param-item">
                <span class="param-label">{{ item.label }}</span>
                <span class="param-value">{{ item.value }}</span>
              </div>
            </el-col>
          </el-row>
        </div>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { wsClient } from '@/api/websocket'
import { ElMessage } from 'element-plus'

// ── 图像流状态 ────────────────────────────────────────────────────────────────
const rgbSrc      = ref('')
const depthSrc    = ref('')
const annoSrc     = ref('')        // 带标注框的 AI 检测图像
const rgbConnected   = ref(false)
const depthConnected = ref(false)
const annoConnected  = ref(false)

const rgbFps    = ref(0)
const depthFps  = ref(0)
const annoFps   = ref(0)
const rgbWidth  = ref(640)
const rgbHeight = ref(480)

let rgbFrameCount   = 0
let depthFrameCount = 0
let annoFrameCount  = 0
let fpsTimer: ReturnType<typeof setInterval>

// ── 检测结果状态 ──────────────────────────────────────────────────────────────
interface Detection {
  class_id:   number
  class_name: string
  confidence: number
  bbox: { x1: number; y1: number; x2: number; y2: number }
  distance_m: number
}

const detections   = ref<Detection[]>([])
const lastFrameId  = ref(0)
const lastInferMs  = ref(0)
const lastDetCount = ref(0)

// ── 颜色映射（按类别 ID 生成固定色，视觉区分度高）────────────────────────────
const CLASS_PALETTE = [
  '#00d4ff', '#00ff88', '#ffaa00', '#ff6b6b', '#a78bfa',
  '#34d399', '#fbbf24', '#f472b6', '#60a5fa', '#4ade80',
]
function classColor(cls_id: number): string {
  return CLASS_PALETTE[cls_id % CLASS_PALETTE.length]
}
function confColor(conf: number): string {
  if (conf >= 0.7) return '#00ff88'
  if (conf >= 0.5) return '#ffaa00'
  return '#ff6b6b'
}

// ── WebSocket 订阅 ────────────────────────────────────────────────────────────

// RGB 原图帧
const unsubRgb = wsClient.on('video_rgb', (data: any) => {
  if (data?.data) {
    rgbSrc.value     = `data:image/jpeg;base64,${data.data}`
    rgbConnected.value = true
    rgbWidth.value   = data.width  ?? 640
    rgbHeight.value  = data.height ?? 480
    rgbFrameCount++
  }
})

// 深度图帧
const unsubDepth = wsClient.on('video_depth', (data: any) => {
  if (data?.data) {
    depthSrc.value      = `data:image/jpeg;base64,${data.data}`
    depthConnected.value = true
    depthFrameCount++
  }
})

// 带标注框的 AI 检测图像（detection_node 发布 /detection/annotated_image
// → backend 以 video_annotated topic 推送，与 video_rgb 纯原图完全分离）
const unsubAnno = wsClient.on('video_annotated', (data: any) => {
  if (data?.data) {
    annoSrc.value       = `data:image/jpeg;base64,${data.data}`
    annoConnected.value = true
    annoFrameCount++
  }
})

// 纯 JSON 检测结果（/detection/results → backend 可选转发）
// 目前 backend 尚未单独推送此 topic，通过 annotated_image 的配套结果推送：
// 若后续 backend 增加 'detection_results' topic 推送，在此处接收
const unsubResults = wsClient.on('detection_results', (data: any) => {
  if (!data) return
  detections.value   = data.detections   ?? []
  lastFrameId.value  = data.frame_id     ?? 0
  lastInferMs.value  = data.infer_ms     ?? 0
  lastDetCount.value = data.count        ?? 0
})

// ── FPS 计算 ─────────────────────────────────────────────────────────────────
const cameraParams = computed(() => [
  { label: 'RGB 分辨率', value: `${rgbWidth.value}×${rgbHeight.value}` },
  { label: 'RGB FPS',   value: `${rgbFps.value}` },
  { label: '深度范围',  value: '0.1 ~ 10.0 m' },
  { label: '视场角',   value: '87° × 58°' },
])

// ── 工具函数 ─────────────────────────────────────────────────────────────────
function screenshot(type: 'rgb' | 'depth') {
  const src = type === 'rgb' ? rgbSrc.value : depthSrc.value
  if (!src) { ElMessage.warning('暂无图像'); return }
  const a = document.createElement('a')
  a.href     = src
  a.download = `${type}_${Date.now()}.jpg`
  a.click()
  ElMessage.success('截图已保存')
}

function openFullscreen(src: string) {
  if (!src) return
  const win = window.open('', '_blank')
  if (win) {
    win.document.write(
      `<html><body style="margin:0;background:#000">` +
      `<img src="${src}" style="max-width:100%;max-height:100vh">` +
      `</body></html>`
    )
  }
}

// ── 生命周期 ─────────────────────────────────────────────────────────────────
onMounted(() => {
  fpsTimer = setInterval(() => {
    rgbFps.value    = rgbFrameCount
    depthFps.value  = depthFrameCount
    annoFps.value   = annoFrameCount
    rgbFrameCount   = 0
    depthFrameCount = 0
    annoFrameCount  = 0
  }, 1000)
})

onUnmounted(() => {
  unsubRgb()
  unsubDepth()
  unsubAnno()
  unsubResults()
  clearInterval(fpsTimer)
})
</script>

<style lang="scss" scoped>
.video-view { display: flex; flex-direction: column; gap: 12px; }
.mt12 { margin-top: 0; }

// ── 视频卡片 ──────────────────────────────────────────────────────────────────
.video-card {
  .actions { display: flex; align-items: center; gap: 4px; }
}

.video-container {
  position: relative; background: #000; border-radius: 6px;
  overflow: hidden; aspect-ratio: 4/3;

  .video-frame {
    width: 100%; height: 100%; object-fit: contain; display: block;
  }
  .video-placeholder {
    display: flex; flex-direction: column; align-items: center; justify-content: center;
    height: 100%; color: var(--color-text-muted); gap: 8px;
    p { font-size: 12px; margin: 0; }
    .hint { font-size: 10px; font-family: var(--font-mono); color: var(--color-primary); opacity: 0.6; }
  }
  .video-overlay {
    position: absolute; bottom: 6px; left: 6px; display: flex; gap: 6px;
    .fps-badge, .res-badge, .infer-badge {
      background: rgba(0,0,0,0.65); color: var(--color-primary);
      font-size: 10px; font-family: var(--font-mono);
      padding: 2px 6px; border-radius: 3px;
    }
    .infer-badge { color: var(--color-warning); }
  }
}

// ── AI 检测面板标题徽章 ───────────────────────────────────────────────────────
.det-badge {
  font-size: 11px; font-family: var(--font-mono);
  color: var(--color-success);
  background: rgba(0, 255, 136, 0.1);
  padding: 1px 7px; border-radius: 10px;
  border: 1px solid rgba(0, 255, 136, 0.3);
}

// ── 识别结果面板 ──────────────────────────────────────────────────────────────
.det-panel {
  display: flex; flex-direction: column; height: 100%;

  .det-empty {
    flex: 1; display: flex; flex-direction: column;
    align-items: center; justify-content: center;
    color: var(--color-text-muted); gap: 8px; padding: 24px 0;
    p { font-size: 12px; margin: 0; }
  }

  .det-list {
    flex: 1; overflow-y: auto; display: flex; flex-direction: column; gap: 6px;
    padding: 4px 0;
    max-height: 340px;

    // 滚动条美化
    &::-webkit-scrollbar { width: 4px; }
    &::-webkit-scrollbar-track { background: transparent; }
    &::-webkit-scrollbar-thumb { background: var(--color-border); border-radius: 2px; }
  }

  .det-item {
    background: rgba(30, 58, 95, 0.25);
    border: 1px solid rgba(30, 58, 95, 0.5);
    border-radius: 6px; padding: 7px 10px;
    display: flex; flex-direction: column; gap: 5px;
    transition: border-color 0.2s;
    &:hover { border-color: var(--color-primary); }
  }

  .det-row {
    display: flex; align-items: center; justify-content: space-between; gap: 8px;
  }

  .det-cls {
    font-size: 13px; font-weight: 600; font-family: var(--font-mono);
    text-transform: capitalize;
  }
  .det-dist {
    font-size: 12px; font-family: var(--font-mono);
    color: var(--color-warning); white-space: nowrap;
  }
  .dist-unknown { color: var(--color-text-muted); }

  .conf-bar-wrap {
    flex: 1; height: 4px; background: rgba(255,255,255,0.08);
    border-radius: 2px; overflow: hidden;
    .conf-bar {
      height: 100%; border-radius: 2px;
      transition: width 0.3s ease;
    }
  }
  .conf-val {
    font-size: 10px; font-family: var(--font-mono);
    color: var(--color-text-muted); white-space: nowrap;
  }

  .det-count {
    font-size: 11px; font-family: var(--font-mono); color: var(--color-primary);
  }

  .det-footer {
    display: flex; gap: 12px; padding-top: 8px;
    border-top: 1px solid rgba(30,58,95,0.4);
    font-size: 10px; font-family: var(--font-mono); color: var(--color-text-muted);
  }
}

// ── 深度图例 ──────────────────────────────────────────────────────────────────
.depth-legend {
  display: flex; align-items: center; gap: 8px; margin-top: 8px;
  .legend-label { font-size: 10px; color: var(--color-text-muted); }
  .legend-bar {
    flex: 1; height: 6px; border-radius: 3px;
    background: linear-gradient(90deg, #ff0000, #ffff00, #00ff00, #00ffff, #0000ff);
  }
}

// ── 相机参数 ──────────────────────────────────────────────────────────────────
.param-item {
  display: flex; flex-direction: column; padding: 8px 0;
  border-bottom: 1px solid rgba(30,58,95,0.4);
  .param-label { font-size: 11px; color: var(--color-text-muted); }
  .param-value {
    font-size: 13px; font-family: var(--font-mono);
    color: var(--color-primary); margin-top: 2px;
  }
}
</style>
