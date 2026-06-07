<template>
  <div class="slam-view">
    <el-row :gutter="12">
      <!-- 地图可视化 -->
      <el-col :xs="24" :sm="16">
        <div class="tech-card">
          <div class="card-header">
            <span class="card-title"><el-icon><MapLocation /></el-icon> 实时地图</span>
            <div class="actions">
              <el-tag size="small" :type="slamStatus?.running ? 'success' : 'info'">
                {{ slamStatus?.running ? '建图中' : '已停止' }}
              </el-tag>
              <el-button size="small" text @click="resetMapView">复位</el-button>
            </div>
          </div>
          <div class="map-wrap">
            <canvas ref="mapCanvasRef" class="map-canvas"
              @wheel="onWheel" @mousedown="onMouseDown"
              @mousemove="onMouseMove" @mouseup="onMouseUp">
            </canvas>
            <div class="map-legend">
              <span class="legend-item free">空闲</span>
              <span class="legend-item occupied">障碍</span>
              <span class="legend-item unknown">未知</span>
              <span class="legend-item robot">机器人</span>
            </div>
          </div>
        </div>
      </el-col>

      <!-- 控制面板 -->
      <el-col :xs="24" :sm="8">
        <div class="tech-card">
          <div class="card-header"><span class="card-title">SLAM 控制</span></div>

          <!-- 算法选择 -->
          <div class="ctrl-section">
            <div class="ctrl-label">建图算法</div>
            <el-select v-model="selectedAlgo" size="small" class="full-width">
              <el-option v-for="a in algorithms" :key="a" :label="a" :value="a" />
            </el-select>
          </div>

          <!-- 启停按钮 -->
          <div class="ctrl-section btn-group">
            <el-button type="primary" size="small" :disabled="slamStatus?.running" @click="startSlam">
              <el-icon><VideoPlay /></el-icon> 开始建图
            </el-button>
            <el-button type="danger" size="small" :disabled="!slamStatus?.running" @click="stopSlam">
              <el-icon><VideoPause /></el-icon> 停止建图
            </el-button>
          </div>

          <!-- 地图保存 -->
          <div class="ctrl-section">
            <div class="ctrl-label">保存地图</div>
            <div class="save-row">
              <el-input v-model="mapName" size="small" placeholder="地图名称" />
              <el-button size="small" type="primary" @click="saveMap">保存</el-button>
            </div>
          </div>

          <!-- 状态信息 -->
          <div class="status-section">
            <div class="status-item">
              <span class="label">算法</span>
              <span class="val">{{ slamStatus?.algorithm ?? '--' }}</span>
            </div>
            <div class="status-item">
              <span class="label">位置 X</span>
              <span class="val mono">{{ slamStatus?.pose?.x?.toFixed(3) ?? '--' }}</span>
            </div>
            <div class="status-item">
              <span class="label">位置 Y</span>
              <span class="val mono">{{ slamStatus?.pose?.y?.toFixed(3) ?? '--' }}</span>
            </div>
            <div class="status-item">
              <span class="label">朝向</span>
              <span class="val mono">{{ slamStatus?.pose?.yaw ? (slamStatus.pose.yaw * 180 / Math.PI).toFixed(1) + '°' : '--' }}</span>
            </div>
            <div class="status-item">
              <span class="label">轨迹点</span>
              <span class="val mono">{{ slamStatus?.trajectory_length ?? 0 }}</span>
            </div>
          </div>
        </div>

        <!-- 地图列表 -->
        <div class="tech-card mt8">
          <div class="card-header">
            <span class="card-title">已保存地图</span>
            <el-button size="small" text @click="loadMapList"><el-icon><Refresh /></el-icon></el-button>
          </div>
          <div class="map-list">
            <div v-for="m in mapList" :key="m.name" class="map-item">
              <span class="map-name">{{ m.name }}</span>
              <div class="map-actions">
                <el-button size="small" text @click="loadMap(m.path)">加载</el-button>
                <el-button size="small" text type="danger" @click="deleteMap(m.name)">删除</el-button>
              </div>
            </div>
            <div v-if="!mapList.length" class="empty-tip">暂无保存的地图</div>
          </div>
        </div>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { wsClient } from '@/api/websocket'
import { slamApi } from '@/api/http'
import { ElMessage } from 'element-plus'

const mapCanvasRef = ref<HTMLCanvasElement>()
const slamStatus = ref<any>(null)
const mapData = ref<any>(null)
const algorithms = ref<string[]>(['cartographer', 'rtab_map', 'orb_slam3', 'lego_loam', 'lio_sam'])
const selectedAlgo = ref('cartographer')
const mapName = ref('my_map')
const mapList = ref<any[]>([])
let zoom = 2.0, offsetX = 0, offsetY = 0
let isDragging = false, dragSX = 0, dragSY = 0

const unsubSlam = wsClient.on('slam_map', (data: any) => {
  mapData.value = data
  slamStatus.value = { running: true, algorithm: selectedAlgo.value, pose: data.robot_pose, trajectory_length: data.trajectory?.length ?? 0 }
  drawMap()
})

function resetMapView() { zoom = 2.0; offsetX = 0; offsetY = 0; drawMap() }
function onWheel(e: WheelEvent) { e.preventDefault(); zoom = Math.max(0.5, Math.min(20, zoom - e.deltaY * 0.005)); drawMap() }
function onMouseDown(e: MouseEvent) { isDragging = true; dragSX = e.clientX - offsetX; dragSY = e.clientY - offsetY }
function onMouseMove(e: MouseEvent) { if (!isDragging) return; offsetX = e.clientX - dragSX; offsetY = e.clientY - dragSY; drawMap() }
function onMouseUp() { isDragging = false }

function drawMap() {
  const canvas = mapCanvasRef.value
  if (!canvas || !mapData.value) return
  const ctx = canvas.getContext('2d')!
  const W = canvas.width, H = canvas.height
  ctx.clearRect(0, 0, W, H)
  ctx.fillStyle = '#050a14'; ctx.fillRect(0, 0, W, H)

  const map = mapData.value
  const cellSize = zoom
  const cx = W / 2 + offsetX, cy = H / 2 + offsetY
  const originX = cx + map.origin.x / map.resolution * cellSize
  const originY = cy - map.origin.y / map.resolution * cellSize

  // 绘制栅格
  for (let row = 0; row < map.height; row++) {
    for (let col = 0; col < map.width; col++) {
      const val = map.data[row]?.[col] ?? -1
      if (val === -1) ctx.fillStyle = 'rgba(107,122,153,0.3)'
      else if (val === 0) ctx.fillStyle = 'rgba(224,230,240,0.15)'
      else ctx.fillStyle = 'rgba(255,68,68,0.8)'
      ctx.fillRect(originX + col * cellSize, originY - row * cellSize, cellSize, cellSize)
    }
  }

  // 绘制轨迹
  if (map.trajectory?.length > 1) {
    ctx.strokeStyle = 'rgba(0,212,255,0.6)'; ctx.lineWidth = 1.5
    ctx.beginPath()
    for (let i = 0; i < map.trajectory.length; i++) {
      const pt = map.trajectory[i]
      const px = originX + pt.x / map.resolution * cellSize
      const py = originY - pt.y / map.resolution * cellSize
      i === 0 ? ctx.moveTo(px, py) : ctx.lineTo(px, py)
    }
    ctx.stroke()
  }

  // 绘制机器人
  if (map.robot_pose) {
    const rx = originX + map.robot_pose.x / map.resolution * cellSize
    const ry = originY - map.robot_pose.y / map.resolution * cellSize
    ctx.fillStyle = '#00d4ff'; ctx.beginPath(); ctx.arc(rx, ry, 5, 0, Math.PI * 2); ctx.fill()
    // 朝向箭头
    const yaw = map.robot_pose.yaw
    ctx.strokeStyle = '#00ff88'; ctx.lineWidth = 2
    ctx.beginPath(); ctx.moveTo(rx, ry)
    ctx.lineTo(rx + Math.cos(yaw) * 12, ry - Math.sin(yaw) * 12); ctx.stroke()
  }
}

function resizeCanvas() {
  const canvas = mapCanvasRef.value; if (!canvas) return
  const p = canvas.parentElement!
  canvas.width = p.clientWidth; canvas.height = p.clientHeight; drawMap()
}

async function startSlam() {
  try { await slamApi.start(selectedAlgo.value); ElMessage.success('SLAM 已启动') } catch { ElMessage.error('启动失败') }
}
async function stopSlam() {
  try { await slamApi.stop(); ElMessage.success('SLAM 已停止') } catch { ElMessage.error('停止失败') }
}
async function saveMap() {
  if (!mapName.value) { ElMessage.warning('请输入地图名称'); return }
  try { await slamApi.saveMap(mapName.value); ElMessage.success('地图已保存'); loadMapList() } catch { ElMessage.error('保存失败') }
}
async function loadMap(path: string) {
  try { await slamApi.loadMap(path); ElMessage.success('地图已加载') } catch { ElMessage.error('加载失败') }
}
async function deleteMap(name: string) {
  try { await slamApi.deleteMap(name); ElMessage.success('已删除'); loadMapList() } catch { ElMessage.error('删除失败') }
}
async function loadMapList() {
  try { const res: any = await slamApi.listMaps(); mapList.value = res.maps ?? [] } catch {}
}

onMounted(() => { resizeCanvas(); loadMapList(); window.addEventListener('resize', resizeCanvas) })
onUnmounted(() => { unsubSlam(); window.removeEventListener('resize', resizeCanvas) })
</script>

<style lang="scss" scoped>
.slam-view { display: flex; flex-direction: column; gap: 12px; }
.mt8 { margin-top: 12px; }
.actions { display: flex; align-items: center; gap: 6px; }
.full-width { width: 100%; }

.map-wrap {
  position: relative; background: #050a14; border-radius: 6px; overflow: hidden; height: 420px;
  .map-canvas { width: 100%; height: 100%; cursor: grab; &:active { cursor: grabbing; } }
  .map-legend {
    position: absolute; bottom: 8px; left: 8px; display: flex; gap: 8px;
    .legend-item {
      font-size: 10px; padding: 2px 6px; border-radius: 3px;
      &.free     { background: rgba(224,230,240,0.15); color: var(--color-text-muted); }
      &.occupied { background: rgba(255,68,68,0.3); color: var(--color-danger); }
      &.unknown  { background: rgba(107,122,153,0.3); color: var(--color-text-muted); }
      &.robot    { background: rgba(0,212,255,0.2); color: var(--color-primary); }
    }
  }
}

.ctrl-section {
  margin-bottom: 12px;
  .ctrl-label { font-size: 11px; color: var(--color-text-muted); margin-bottom: 6px; }
  &.btn-group { display: flex; gap: 8px; }
  .save-row { display: flex; gap: 6px; }
}

.status-section {
  .status-item {
    display: flex; justify-content: space-between; padding: 5px 0;
    border-bottom: 1px solid rgba(30,58,95,0.4);
    .label { font-size: 11px; color: var(--color-text-muted); }
    .val { font-size: 12px; color: var(--color-text); }
    .mono { font-family: var(--font-mono); }
  }
}

.map-list {
  max-height: 160px; overflow-y: auto;
  .map-item {
    display: flex; justify-content: space-between; align-items: center;
    padding: 6px 0; border-bottom: 1px solid rgba(30,58,95,0.3);
    .map-name { font-size: 12px; color: var(--color-text); }
    .map-actions { display: flex; gap: 4px; }
  }
  .empty-tip { font-size: 11px; color: var(--color-text-muted); text-align: center; padding: 12px; }
}
</style>
