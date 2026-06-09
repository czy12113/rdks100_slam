<template>
  <div class="control-view">
    <el-row :gutter="12">
      <!-- 左列：摇杆 + 方向按钮 + 键盘提示 -->
      <el-col :xs="24" :sm="10">
        <div class="tech-card">
          <div class="card-header">
            <span class="card-title"><el-icon><Promotion /></el-icon> 运动控制</span>
            <div style="display:flex;align-items:center;gap:8px;">
              <el-tooltip :content="tapMode ? '点按模式：每次按键递增/递减速度，空格急停' : '长按模式：松开按键自动停车'" placement="bottom">
                <el-button
                  size="small"
                  :type="tapMode ? 'warning' : 'primary'"
                  @click="toggleMode"
                  style="font-size:11px;padding:4px 8px;"
                >
                  <el-icon style="margin-right:3px;"><component :is="tapMode ? 'Pointer' : 'Aim'" /></el-icon>
                  {{ tapMode ? '点按' : '长按' }}
                </el-button>
              </el-tooltip>
              <el-tag size="small" :type="robotStore.isOnline ? 'success' : 'danger'">
                {{ robotStore.isOnline ? '在线' : '离线' }}
              </el-tag>
            </div>
          </div>

          <!-- 虚拟摇杆区域 -->
          <div class="joystick-area">
            <div ref="joystickRef" class="joystick-zone"></div>
            <div class="joystick-hint">拖动摇杆控制移动</div>
          </div>

          <!-- 方向按钮 -->
          <div class="dpad-area">
            <div class="dpad-row">
              <button
                class="dpad-btn"
                :class="{ active: keys.w }"
                @pointerdown="(e) => onDpadDown(e, 'w')"
                @pointerup="onDpadUp('w')"
                @pointercancel="onDpadUp('w')"
              >
                <el-icon><ArrowUp /></el-icon>
              </button>
            </div>
            <div class="dpad-row">
              <button
                class="dpad-btn"
                :class="{ active: keys.a }"
                @pointerdown="(e) => onDpadDown(e, 'a')"
                @pointerup="onDpadUp('a')"
                @pointercancel="onDpadUp('a')"
              >
                <el-icon><ArrowLeft /></el-icon>
              </button>
              <button
                class="dpad-btn stop-btn"
                @pointerdown.prevent="emergencyStop"
              >
                <el-icon><VideoPause /></el-icon>
              </button>
              <button
                class="dpad-btn"
                :class="{ active: keys.d }"
                @pointerdown="(e) => onDpadDown(e, 'd')"
                @pointerup="onDpadUp('d')"
                @pointercancel="onDpadUp('d')"
              >
                <el-icon><ArrowRight /></el-icon>
              </button>
            </div>
            <div class="dpad-row">
              <button
                class="dpad-btn"
                :class="{ active: keys.s }"
                @pointerdown="(e) => onDpadDown(e, 's')"
                @pointerup="onDpadUp('s')"
                @pointercancel="onDpadUp('s')"
              >
                <el-icon><ArrowDown /></el-icon>
              </button>
            </div>
          </div>

          <!-- 点按模式速度显示 -->
          <div v-if="tapMode" class="tap-vel-display">
            <div class="tap-vel-item">
              <span class="tap-label">线速度</span>
              <span class="tap-val mono" :class="tapVx > 0 ? 'pos' : tapVx < 0 ? 'neg' : ''">
                {{ tapVx >= 0 ? '+' : '' }}{{ tapVx.toFixed(2) }} <span class="unit">m/s</span>
              </span>
            </div>
            <div class="tap-vel-item">
              <span class="tap-label">角速度</span>
              <span class="tap-val mono" :class="tapWz > 0 ? 'pos' : tapWz < 0 ? 'neg' : ''">
                {{ tapWz >= 0 ? '+' : '' }}{{ tapWz.toFixed(2) }} <span class="unit">rad/s</span>
              </span>
            </div>
          </div>

          <!-- WASD 键盘提示 -->
          <div class="keyboard-hint">
            <div class="key-row"><div class="key" :class="{ active: keys.w }">W</div></div>
            <div class="key-row">
              <div class="key" :class="{ active: keys.a }">A</div>
              <div class="key" :class="{ active: keys.s }">S</div>
              <div class="key" :class="{ active: keys.d }">D</div>
            </div>
            <div class="key-desc" v-if="!tapMode">前进 / 左转 / 后退 / 右转 &nbsp;|&nbsp; 空格键急停</div>
            <div class="key-desc" v-else>每次按键递增/递减速度 &nbsp;|&nbsp; 空格键急停归零</div>
          </div>
        </div>
      </el-col>

      <!-- 右列 -->
      <el-col :xs="24" :sm="14">
        <div class="tech-card">
          <div class="card-header">
            <span class="card-title">速度参数</span>
          </div>
          <div class="speed-control">
            <div class="speed-row">
              <span class="label">线速度</span>
              <el-slider v-model="linearSpeed" :min="0.05" :max="ROBOT_MAX_LINEAR_VEL" :step="0.05" show-input size="small" class="slider" />
              <span class="unit">m/s</span>
            </div>
            <div class="speed-row">
              <span class="label">角速度</span>
              <el-slider v-model="angularSpeed" :min="0.05" :max="ROBOT_MAX_ANGULAR_VEL" :step="0.05" show-input size="small" class="slider" />
              <span class="unit">rad/s</span>
            </div>
          </div>

          <!-- 实时速度仪表盘 -->
          <div class="vel-dashboard">
            <div class="vel-gauge">
              <div class="gauge-label">线速度</div>
              <div class="gauge-bar-wrap">
                <div
                  class="gauge-bar"
                  :class="velBarClass(displayVx)"
                  :style="{ width: Math.abs(displayVx) / ROBOT_MAX_LINEAR_VEL * 100 + '%', marginLeft: displayVx < 0 ? 'auto' : '0' }"
                ></div>
              </div>
              <div class="gauge-val mono">{{ displayVx.toFixed(3) }} <span class="unit">m/s</span></div>
            </div>
            <div class="vel-gauge">
              <div class="gauge-label">角速度</div>
              <div class="gauge-bar-wrap">
                <div
                  class="gauge-bar angular"
                  :class="velBarClass(displayWz)"
                  :style="{ width: Math.abs(displayWz) / ROBOT_MAX_ANGULAR_VEL * 100 + '%', marginLeft: displayWz < 0 ? 'auto' : '0' }"
                ></div>
              </div>
              <div class="gauge-val mono">{{ displayWz.toFixed(3) }} <span class="unit">rad/s</span></div>
            </div>
          </div>

          <!-- 急停按钮 -->
          <el-button
            type="danger"
            size="large"
            class="estop-btn"
            @pointerdown.prevent="emergencyStop"
          >
            <el-icon><VideoPause /></el-icon>
            紧急停止 (Space)
          </el-button>
        </div>

        <!-- 里程计卡片 -->
        <div class="tech-card" style="margin-top: 12px;">
          <div class="card-header">
            <span class="card-title"><el-icon><Position /></el-icon> 里程计 / 位姿</span>
            <el-button size="small" text @click="resetOdom">重置</el-button>
          </div>
          <div class="odom-grid">
            <div class="odom-item">
              <span class="odom-label">X 坐标</span>
              <span class="odom-val mono">{{ displayPose.x.toFixed(3) }} <span class="unit">m</span></span>
            </div>
            <div class="odom-item">
              <span class="odom-label">Y 坐标</span>
              <span class="odom-val mono">{{ displayPose.y.toFixed(3) }} <span class="unit">m</span></span>
            </div>
            <div class="odom-item">
              <span class="odom-label">朝向角</span>
              <span class="odom-val mono">{{ (displayPose.yaw * 180 / Math.PI).toFixed(1) }} <span class="unit">°</span></span>
            </div>
            <div class="odom-item">
              <span class="odom-label">累计距离</span>
              <span class="odom-val mono">{{ totalDistance.toFixed(2) }} <span class="unit">m</span></span>
            </div>
          </div>
        </div>

        <!-- 控制日志 -->
        <div class="tech-card" style="margin-top: 12px;">
          <div class="card-header">
            <span class="card-title"><el-icon><Document /></el-icon> 控制日志</span>
            <el-button size="small" text @click="controlLogs = []">清空</el-button>
          </div>
          <div ref="logRef" class="ctrl-log-area">
            <div
              v-for="(log, i) in controlLogs.slice(-50)"
              :key="i"
              class="ctrl-log-line"
              :class="`log-${log.level}`"
            >
              <span class="log-time">{{ log.time }}</span>
              <span class="log-msg">{{ log.msg }}</span>
            </div>
            <div v-if="controlLogs.length === 0" class="log-empty">暂无控制日志</div>
          </div>
        </div>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import nipplejs from 'nipplejs'
import { controlApi } from '@/api/http'
import { wsClient } from '@/api/websocket'
import { useRobotStore } from '@/stores/robot'
import {
  ROBOT_MAX_LINEAR_VEL, ROBOT_MAX_ANGULAR_VEL,
  ROBOT_DEFAULT_LINEAR_VEL, ROBOT_DEFAULT_ANGULAR_VEL,
} from '@/config'
import { ElMessage } from 'element-plus'
import dayjs from 'dayjs'

const robotStore = useRobotStore()
const joystickRef = ref<HTMLElement>()
const logRef = ref<HTMLElement>()

const linearSpeed  = ref(ROBOT_DEFAULT_LINEAR_VEL)
const angularSpeed = ref(ROBOT_DEFAULT_ANGULAR_VEL)

const cmdVx = ref(0)
const cmdWz = ref(0)

const odomOffsetX   = ref(0)
const odomOffsetY   = ref(0)
const odomOffsetYaw = ref(0)

interface CtrlLog { time: string; msg: string; level: 'info' | 'warn' | 'error' }
const controlLogs = ref<CtrlLog[]>([])

const keys = ref({ w: false, a: false, s: false, d: false })

// ── 控制模式 ──────────────────────────────────────────────────────────
const tapMode = ref(false)
const tapVx   = ref(0)
const tapWz   = ref(0)
const TAP_VX_STEP = 0.05
const TAP_WZ_STEP = 0.1

function toggleMode() {
  tapMode.value = !tapMode.value
  tapVx.value = 0
  tapWz.value = 0
  targetVx = 0
  targetWz = 0
  keys.value = { w: false, a: false, s: false, d: false }
  doSendVelocity(0, 0)
  addLog(`已切换到${tapMode.value ? '点按' : '长按'}模式`, 'info')
}

let joystick: ReturnType<typeof nipplejs.create> | null = null
let unsubOdom: (() => void) | null = null

// ── 计算属性 ──────────────────────────────────────────────────────────
const displayVx = computed(() => {
  const odom = robotStore.odomData
  if (odom) return odom.velocity.linear_x
  return cmdVx.value
})
const displayWz = computed(() => {
  const odom = robotStore.odomData
  if (odom) return odom.velocity.angular_z
  return cmdWz.value
})
const displayPose = computed(() => {
  const p = robotStore.currentPose
  return { x: p.x - odomOffsetX.value, y: p.y - odomOffsetY.value, yaw: p.yaw - odomOffsetYaw.value }
})
const totalDistance = computed(() => {
  return robotStore.odomData?.odometry?.total_distance ?? robotStore.robotStatus?.odometry?.total_distance ?? 0
})
function velBarClass(val: number) {
  const abs = Math.abs(val)
  if (abs > 0.6) return 'high'
  if (abs > 0.2) return 'mid'
  return 'low'
}

// ── 控制参数 ──────────────────────────────────────────────────────────
const JOYSTICK_DEADZONE = 0.08
const JOYSTICK_SIZE     = 140
const SEND_INTERVAL_MS  = 50     // 发送间隔 50ms（20Hz）
const DIAGONAL_SCALE    = 0.707

let targetVx = 0
let targetWz = 0
let sendTimer: ReturnType<typeof setInterval> | null = null
let joystickActive = false

// ── 发送机制 ─────────────────────────────────────────────────────────
// 核心设计：
//   1. sendTimer 以 50ms 间隔触发，每次都发送（不跳帧）
//   2. http.ts 的 AbortController 确保网络层同时只有 1 个请求在飞
//      （新请求自动 abort 上一个未完成的，不会堆积）
//   3. 急停和松键停车通过 controlApi.stop() 独立通道发送
//   4. 不再使用 _sendingInFlight 互斥——它会导致跳帧过多，
//      在网络延迟 > 50ms 时电机因收不到持续指令而被 bridge 超时归零
let _lastSentVx = 0
let _lastSentWz = 0

/** 发送速度指令（每次调用都发，AbortController 防堆积） */
function doSendVelocity(vx: number, wz: number) {
  cmdVx.value = vx
  cmdWz.value = wz
  _lastSentVx = vx
  _lastSentWz = wz

  // http.ts 内部：AbortController 会先取消上一个未完成的请求
  controlApi.setVelocity(vx, 0, wz)
    .catch(() => { /* 被 abort 或超时都静默 */ })
}

/** 强制发送停车（通过独立的 /stop 接口） */
function doForceStop() {
  cmdVx.value = 0
  cmdWz.value = 0
  _lastSentVx = 0
  _lastSentWz = 0
  // stop() 内部会先 abort 所有排队的 velocity 请求
  controlApi.stop().catch(() => {})
  // 同时直接发一个零速，双保险
  controlApi.setVelocity(0, 0, 0).catch(() => {})
}

// ── 摇杆 ─────────────────────────────────────────────────────────────
function initJoystick() {
  if (!joystickRef.value) return
  joystick = nipplejs.create({
    zone: joystickRef.value,
    mode: 'static',
    position: { left: '50%', top: '50%' },
    color: '#00d4ff',
    size: JOYSTICK_SIZE,
    restOpacity: 0.6,
    fadeTime: 100,
  })

  joystick.on('start', () => { joystickActive = true })

  joystick.on('move', (_evt: any, data: any) => {
    const force = Math.min(data.force, 1)
    if (force < JOYSTICK_DEADZONE) {
      targetVx = 0
      targetWz = 0
      return
    }
    const mappedForce = (force - JOYSTICK_DEADZONE) / (1 - JOYSTICK_DEADZONE)
    const angle = data.angle.radian
    targetVx =  Math.sin(angle) * mappedForce * linearSpeed.value
    targetWz = -Math.cos(angle) * mappedForce * angularSpeed.value
  })

  joystick.on('end', () => {
    joystickActive = false
    targetVx = 0
    targetWz = 0
    doForceStop()
  })
}

// ── 方向按钮 ─────────────────────────────────────────────────────────
function onDpadDown(e: PointerEvent, key: 'w' | 'a' | 's' | 'd') {
  ;(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId)
  if (tapMode.value) {
    tapStep(key)
  } else {
    keys.value[key] = true
  }
}
function onDpadUp(key: 'w' | 'a' | 's' | 'd') {
  if (!tapMode.value) {
    keys.value[key] = false
    if (!keys.value.w && !keys.value.a && !keys.value.s && !keys.value.d && !joystickActive) {
      targetVx = 0
      targetWz = 0
      doForceStop()
    }
  }
}

function tapStep(key: 'w' | 'a' | 's' | 'd') {
  const maxVx = ROBOT_MAX_LINEAR_VEL
  const maxWz = ROBOT_MAX_ANGULAR_VEL
  if (key === 'w') tapVx.value = Math.min(tapVx.value + TAP_VX_STEP, maxVx)
  if (key === 's') tapVx.value = Math.max(tapVx.value - TAP_VX_STEP, -maxVx)
  if (key === 'a') tapWz.value = Math.min(tapWz.value + TAP_WZ_STEP, maxWz)
  if (key === 'd') tapWz.value = Math.max(tapWz.value - TAP_WZ_STEP, -maxWz)
  targetVx = tapVx.value
  targetWz = tapWz.value
  addLog(`点按 ${key.toUpperCase()}: vx=${tapVx.value.toFixed(2)}, wz=${tapWz.value.toFixed(2)}`, 'info')
}

// ── 键盘 ─────────────────────────────────────────────────────────────
function onKeyDown(e: KeyboardEvent) {
  const tag = (e.target as HTMLElement).tagName
  if (tag === 'INPUT' || tag === 'TEXTAREA') return
  const k = e.key.toLowerCase()
  if (k === ' ') { emergencyStop(); e.preventDefault(); return }

  if (tapMode.value) {
    if (e.repeat) return
    if (k === 'w' || k === 'arrowup')    { tapStep('w'); e.preventDefault() }
    if (k === 'a' || k === 'arrowleft')  { tapStep('a'); e.preventDefault() }
    if (k === 's' || k === 'arrowdown')  { tapStep('s'); e.preventDefault() }
    if (k === 'd' || k === 'arrowright') { tapStep('d'); e.preventDefault() }
  } else {
    if (k === 'w' || k === 'arrowup')    { keys.value.w = true; e.preventDefault() }
    if (k === 'a' || k === 'arrowleft')  { keys.value.a = true; e.preventDefault() }
    if (k === 's' || k === 'arrowdown')  { keys.value.s = true; e.preventDefault() }
    if (k === 'd' || k === 'arrowright') { keys.value.d = true; e.preventDefault() }
  }
}

function onKeyUp(e: KeyboardEvent) {
  if (tapMode.value) return
  const tag = (e.target as HTMLElement).tagName
  if (tag === 'INPUT' || tag === 'TEXTAREA') return
  const k = e.key.toLowerCase()
  if (k === 'w' || k === 'arrowup')    keys.value.w = false
  if (k === 'a' || k === 'arrowleft')  keys.value.a = false
  if (k === 's' || k === 'arrowdown')  keys.value.s = false
  if (k === 'd' || k === 'arrowright') keys.value.d = false

  if (!keys.value.w && !keys.value.a && !keys.value.s && !keys.value.d && !joystickActive) {
    targetVx = 0
    targetWz = 0
    doForceStop()
  }
}

function calcKeyTarget(): { vx: number; wz: number } {
  let vx = 0, wz = 0
  if (keys.value.w) vx += linearSpeed.value
  if (keys.value.s) vx -= linearSpeed.value
  if (keys.value.a) wz += angularSpeed.value
  if (keys.value.d) wz -= angularSpeed.value
  if (vx !== 0 && wz !== 0) {
    vx *= DIAGONAL_SCALE
    wz *= DIAGONAL_SCALE
  }
  return { vx, wz }
}

// ── 发送循环 ─────────────────────────────────────────────────────────
// 设计原则：
//   - 每 50ms 触发一次（20Hz），每次都发（AbortController 防堆积）
//   - 停车指令通过 doForceStop() 走独立通道，不受本循环限制
function startSendLoop() {
  sendTimer = setInterval(() => {
    // 从键盘/点按模式计算当前目标
    if (!joystickActive) {
      if (tapMode.value) {
        // tap 模式 targetVx/Wz 由 tapStep 写入
      } else {
        const kt = calcKeyTarget()
        targetVx = kt.vx
        targetWz = kt.wz
      }
    }

    // 仅在有有效速度时发送（零速由 doForceStop 专门处理，避免重复刷零）
    if (targetVx === 0 && targetWz === 0) {
      // 如果上次发送的也是零，则不再重复发
      if (_lastSentVx === 0 && _lastSentWz === 0) return
    }

    doSendVelocity(targetVx, targetWz)
  }, SEND_INTERVAL_MS)
}

// ── 急停 ─────────────────────────────────────────────────────────────
function emergencyStop() {
  // 立即清零所有状态
  keys.value = { w: false, a: false, s: false, d: false }
  tapVx.value = 0
  tapWz.value = 0
  targetVx = 0
  targetWz = 0
  joystickActive = false

  // 通过独立通道强制停车
  doForceStop()

  addLog('急停已触发', 'warn')
  ElMessage.warning('急停已执行')
}

function resetOdom() {
  const p = robotStore.currentPose
  odomOffsetX.value   = p.x
  odomOffsetY.value   = p.y
  odomOffsetYaw.value = p.yaw
  addLog('里程计已重置', 'info')
  ElMessage.success('里程计已重置')
}

function addLog(msg: string, level: 'info' | 'warn' | 'error' = 'info') {
  controlLogs.value.push({ time: dayjs().format('HH:mm:ss'), msg, level })
  if (controlLogs.value.length > 200) controlLogs.value.shift()
}

watch(() => controlLogs.value.length, async () => {
  await nextTick()
  if (logRef.value) logRef.value.scrollTop = logRef.value.scrollHeight
})

onMounted(() => {
  initJoystick()
  window.addEventListener('keydown', onKeyDown)
  window.addEventListener('keyup', onKeyUp)
  startSendLoop()
  unsubOdom = wsClient.on('odom', () => {})
  addLog('控制界面已就绪，WASD/方向键控制，空格急停', 'info')
})

onUnmounted(() => {
  joystick?.destroy()
  window.removeEventListener('keydown', onKeyDown)
  window.removeEventListener('keyup', onKeyUp)
  if (sendTimer) clearInterval(sendTimer)
  if (unsubOdom) unsubOdom()
  controlApi.stop().catch(() => {})
})
</script>

<style lang="scss" scoped>
.control-view { display: flex; flex-direction: column; gap: 12px; }

.joystick-area {
  display: flex; flex-direction: column; align-items: center; gap: 8px;
  .joystick-zone {
    width: 180px; height: 180px; background: rgba(0,212,255,0.05);
    border: 2px solid var(--color-border); border-radius: 50%; position: relative;
  }
  .joystick-hint { font-size: 11px; color: var(--color-text-muted); }
}

.dpad-area {
  display: flex; flex-direction: column; align-items: center; gap: 4px; margin: 12px 0;
  .dpad-row { display: flex; gap: 4px; }
}

.dpad-btn {
  width: 44px; height: 44px;
  background: var(--color-bg-panel);
  border: 1px solid var(--color-border);
  border-radius: 8px;
  color: var(--color-text-muted);
  font-size: 18px;
  cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  transition: all 0.1s;
  user-select: none;
  -webkit-user-select: none;
  touch-action: none;
  &:hover { border-color: var(--color-primary); color: var(--color-primary); }
  &.active {
    background: rgba(0,212,255,0.15);
    border-color: var(--color-primary);
    color: var(--color-primary);
    transform: scale(0.95);
  }
  &.stop-btn {
    background: rgba(255,68,68,0.1);
    border-color: var(--color-danger);
    color: var(--color-danger);
    &:hover { background: rgba(255,68,68,0.2); }
    &:active { transform: scale(0.95); }
  }
}

.keyboard-hint {
  display: flex; flex-direction: column; align-items: center; gap: 4px; margin-top: 4px;
  .key-row { display: flex; gap: 4px; }
  .key {
    width: 28px; height: 28px; border: 1px solid var(--color-border);
    border-radius: 4px; display: flex; align-items: center; justify-content: center;
    font-size: 11px; font-weight: 600; color: var(--color-text-muted);
    background: var(--color-bg-panel); transition: all 0.1s;
    &.active { background: rgba(0,212,255,0.2); border-color: var(--color-primary); color: var(--color-primary); }
  }
  .key-desc { font-size: 10px; color: var(--color-text-muted); margin-top: 4px; }
}

.speed-control {
  display: flex; flex-direction: column; gap: 12px; margin-bottom: 16px;
  .speed-row {
    display: flex; align-items: center; gap: 10px;
    .label { font-size: 12px; color: var(--color-text-muted); min-width: 50px; }
    .slider { flex: 1; }
    .unit { font-size: 11px; color: var(--color-text-muted); min-width: 36px; }
  }
}

.vel-dashboard { display: flex; flex-direction: column; gap: 10px; margin-bottom: 16px; }

.vel-gauge {
  display: flex; align-items: center; gap: 10px;
  .gauge-label { font-size: 11px; color: var(--color-text-muted); min-width: 44px; }
  .gauge-bar-wrap {
    flex: 1; height: 8px; background: rgba(255,255,255,0.05);
    border-radius: 4px; overflow: hidden; position: relative;
    display: flex; align-items: center;
  }
  .gauge-bar {
    height: 100%; border-radius: 4px; transition: width 0.1s ease;
    background: var(--color-success);
    &.mid { background: var(--color-warning); }
    &.high { background: var(--color-danger); }
  }
  .gauge-val {
    font-family: var(--font-mono); font-size: 12px; color: var(--color-primary);
    min-width: 80px; text-align: right;
    .unit { font-size: 10px; color: var(--color-text-muted); }
  }
}

.estop-btn {
  width: 100%; height: 44px; font-size: 14px; font-weight: 700;
  background: rgba(255,68,68,0.1) !important;
  border: 2px solid var(--color-danger) !important;
  color: var(--color-danger) !important;
  &:hover { background: rgba(255,68,68,0.2) !important; }
  &:active { transform: scale(0.98); }
}

.odom-grid {
  display: grid; grid-template-columns: 1fr 1fr; gap: 10px;
  .odom-item {
    display: flex; flex-direction: column; gap: 2px;
    padding: 8px; background: rgba(0,212,255,0.03);
    border: 1px solid rgba(30,58,95,0.5); border-radius: 6px;
    .odom-label { font-size: 11px; color: var(--color-text-muted); }
    .odom-val {
      font-family: var(--font-mono); font-size: 14px; color: var(--color-primary);
      .unit { font-size: 10px; color: var(--color-text-muted); }
    }
  }
}

.ctrl-log-area {
  height: 120px; overflow-y: auto; font-family: var(--font-mono); font-size: 11px;
  .ctrl-log-line {
    padding: 2px 0; border-bottom: 1px solid rgba(30,58,95,0.3);
    display: flex; gap: 8px;
    .log-time { color: var(--color-text-muted); flex-shrink: 0; }
    .log-msg { color: var(--color-text); }
    &.log-warn .log-msg { color: var(--color-warning); }
    &.log-error .log-msg { color: var(--color-danger); }
    &.log-info .log-msg { color: var(--color-text); }
  }
  .log-empty { color: var(--color-text-muted); font-size: 11px; padding: 8px 0; }
}

.mono { font-family: var(--font-mono); }
.unit { font-size: 10px; color: var(--color-text-muted); }

.tap-vel-display {
  display: flex; gap: 12px; margin: 8px 0 4px;
  padding: 8px 12px;
  background: rgba(255,170,0,0.06);
  border: 1px solid rgba(255,170,0,0.3);
  border-radius: 8px;
  .tap-vel-item {
    display: flex; flex-direction: column; gap: 2px; flex: 1;
    .tap-label { font-size: 10px; color: var(--color-text-muted); }
    .tap-val {
      font-family: var(--font-mono); font-size: 15px; font-weight: 600;
      color: var(--color-text);
      &.pos { color: var(--color-success); }
      &.neg { color: var(--color-danger); }
      .unit { font-size: 10px; color: var(--color-text-muted); font-weight: 400; }
    }
  }
}
</style>
