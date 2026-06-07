<template>
  <div class="nav-view">
    <el-row :gutter="12">
      <!-- 地图导航区域 -->
      <el-col :xs="24" :sm="16">
        <div class="tech-card">
          <div class="card-header">
            <span class="card-title"><el-icon><Position /></el-icon> 导航地图</span>
            <div class="actions">
              <el-tag size="small" :type="navStatus.active ? 'success' : 'info'">
                {{ navStatus.active ? '导航中' : '空闲' }}
              </el-tag>
            </div>
          </div>
          <div class="nav-map-area">
            <div class="placeholder-content">
              <el-icon size="64"><MapLocation /></el-icon>
              <h3>导航与路径规划模块</h3>
              <p>此模块为预留功能，待接入 Nav2 后启用</p>
              <div class="feature-list">
                <div class="feature-item"><el-icon><Check /></el-icon> 地图选点导航</div>
                <div class="feature-item"><el-icon><Check /></el-icon> 路径规划可视化</div>
                <div class="feature-item"><el-icon><Check /></el-icon> 动态避障显示</div>
                <div class="feature-item"><el-icon><Check /></el-icon> 多点巡航</div>
                <div class="feature-item"><el-icon><Check /></el-icon> A*、RRT、DWA、TEB 算法扩展</div>
              </div>
            </div>
          </div>
        </div>
      </el-col>

      <!-- 导航控制面板 -->
      <el-col :xs="24" :sm="8">
        <div class="tech-card">
          <div class="card-header"><span class="card-title">导航控制</span></div>

          <!-- 算法选择 -->
          <div class="ctrl-section">
            <div class="ctrl-label">规划算法</div>
            <el-select v-model="selectedAlgo" size="small" class="full-width">
              <el-option v-for="a in algorithms" :key="a" :label="a" :value="a" />
            </el-select>
          </div>

          <!-- 目标点设置 -->
          <div class="ctrl-section">
            <div class="ctrl-label">目标点坐标</div>
            <el-row :gutter="6">
              <el-col :span="8">
                <el-input v-model.number="goalX" size="small" placeholder="X" />
              </el-col>
              <el-col :span="8">
                <el-input v-model.number="goalY" size="small" placeholder="Y" />
              </el-col>
              <el-col :span="8">
                <el-input v-model.number="goalYaw" size="small" placeholder="Yaw" />
              </el-col>
            </el-row>
          </div>

          <div class="ctrl-section btn-group">
            <el-button type="primary" size="small" @click="sendGoal">
              <el-icon><Position /></el-icon> 开始导航
            </el-button>
            <el-button type="danger" size="small" @click="cancelNav">
              <el-icon><Close /></el-icon> 取消
            </el-button>
          </div>

          <!-- 导航状态 -->
          <div class="status-section">
            <div class="status-item">
              <span class="label">状态</span>
              <span class="val">{{ navStatus.status }}</span>
            </div>
            <div class="status-item">
              <span class="label">剩余距离</span>
              <span class="val mono">{{ navStatus.distance_to_goal?.toFixed(2) ?? '--' }} m</span>
            </div>
            <div class="status-item">
              <span class="label">算法</span>
              <span class="val">{{ navStatus.algorithm ?? '--' }}</span>
            </div>
          </div>
        </div>

        <!-- 多点巡航 -->
        <div class="tech-card mt8">
          <div class="card-header">
            <span class="card-title">多点巡航（预留）</span>
          </div>
          <div class="waypoint-area">
            <div v-for="(wp, i) in waypoints" :key="i" class="wp-item">
              <span class="wp-idx">#{{ i + 1 }}</span>
              <span class="wp-coord">X:{{ wp.x }} Y:{{ wp.y }}</span>
              <el-button size="small" text type="danger" @click="waypoints.splice(i, 1)">×</el-button>
            </div>
            <el-button size="small" text @click="addWaypoint">+ 添加巡航点</el-button>
          </div>
          <el-button size="small" type="primary" :disabled="waypoints.length < 2" @click="startPatrol" class="mt8">
            开始巡航
          </el-button>
        </div>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { wsClient } from '@/api/websocket'
import { navigationApi } from '@/api/http'
import { ElMessage } from 'element-plus'

const algorithms = ref(['nav2_default', 'a_star', 'rrt', 'dwa', 'teb'])
const selectedAlgo = ref('nav2_default')
const goalX = ref(1.0)
const goalY = ref(0.0)
const goalYaw = ref(0.0)
const navStatus = ref<any>({ active: false, status: 'idle', distance_to_goal: 0, algorithm: '' })
const waypoints = ref<Array<{ x: number; y: number }>>([])

const unsubNav = wsClient.on('navigation', (data: any) => { navStatus.value = data })

async function sendGoal() {
  try {
    await navigationApi.setGoal(goalX.value, goalY.value, goalYaw.value)
    ElMessage.success('导航目标已设置')
  } catch { ElMessage.error('设置失败') }
}

async function cancelNav() {
  try {
    await navigationApi.cancel()
    ElMessage.info('导航已取消')
  } catch { ElMessage.error('取消失败') }
}

function addWaypoint() {
  waypoints.value.push({ x: Math.round(Math.random() * 4 * 10) / 10, y: Math.round(Math.random() * 4 * 10) / 10 })
}

async function startPatrol() {
  try {
    await navigationApi.setWaypoints(waypoints.value)
    ElMessage.success(`已设置 ${waypoints.value.length} 个巡航点`)
  } catch { ElMessage.error('巡航设置失败') }
}

onMounted(() => { navigationApi.getStatus().then((r: any) => { navStatus.value = r }).catch(() => {}) })
onUnmounted(() => { unsubNav() })
</script>

<style lang="scss" scoped>
.nav-view { display: flex; flex-direction: column; gap: 12px; }
.mt8 { margin-top: 12px; }
.actions { display: flex; align-items: center; gap: 6px; }
.full-width { width: 100%; }

.nav-map-area {
  height: 400px; background: #050a14; border-radius: 6px;
  display: flex; align-items: center; justify-content: center;
  .placeholder-content {
    text-align: center; color: var(--color-text-muted);
    h3 { color: var(--color-primary); margin: 12px 0 8px; font-size: 16px; }
    p { font-size: 12px; margin-bottom: 16px; }
    .feature-list {
      text-align: left; display: inline-block;
      .feature-item {
        display: flex; align-items: center; gap: 6px; padding: 4px 0;
        font-size: 12px; color: var(--color-text-muted);
        .el-icon { color: var(--color-success); }
      }
    }
  }
}

.ctrl-section {
  margin-bottom: 12px;
  .ctrl-label { font-size: 11px; color: var(--color-text-muted); margin-bottom: 6px; }
  &.btn-group { display: flex; gap: 8px; }
}

.status-section {
  margin-top: 12px;
  .status-item {
    display: flex; justify-content: space-between; padding: 5px 0;
    border-bottom: 1px solid rgba(30,58,95,0.4);
    .label { font-size: 11px; color: var(--color-text-muted); }
    .val { font-size: 12px; color: var(--color-text); }
    .mono { font-family: var(--font-mono); }
  }
}

.waypoint-area {
  .wp-item {
    display: flex; align-items: center; gap: 8px; padding: 4px 0;
    border-bottom: 1px solid rgba(30,58,95,0.3);
    .wp-idx { font-size: 11px; color: var(--color-primary); font-weight: 600; }
    .wp-coord { font-size: 11px; font-family: var(--font-mono); color: var(--color-text); flex: 1; }
  }
}
</style>
