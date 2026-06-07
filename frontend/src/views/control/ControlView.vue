<template>
  <div class="control-view">
    <el-row :gutter="12">
      <!-- 左列：摇杆 + 方向按钮 + 键盘提示 -->
      <el-col :xs="24" :sm="10">
        <div class="tech-card">
          <div class="card-header">
            <span class="card-title"><el-icon><Promotion /></el-icon> 运动控制</span>
            <div style="display:flex;align-items:center;gap:8px;">
              <!-- 控制模式切换 -->
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

          <!-- 方向按钮（触屏友好） -->
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
                @click="emergencyStop"
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

      <!-- 右列：速度参数 + 实时状态 + 里程计 -->
      <el-col :xs="24" :sm="14">
        <!-- 速度参数卡片 -->
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
            @click="emergencyStop"
          >
            <el-icon><VideoPause /></el-icon>
            紧急停止 (Space)
          </el-button>
        </div>

        <!-- 里程计 + 位姿卡片 -->
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

        <!-- 控制日志卡片 -->
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

const linearSpeed = ref(ROBOT_DEFAULT_LINEAR_VEL)
const angularSpeed = ref(ROBOT_DEFAULT_ANGULAR_VEL)

// 发送中的速度（用于仪表盘显示）
const cmdVx = ref(0)
const cmdWz = ref(0)

// 里程计偏移（重置用）
const odomOffsetX = ref(0)
const odomOffsetY = ref(0)
const odomOffsetYaw = ref(0)

// 控制日志
interface CtrlLog { time: string; msg: string; level: 'info' | 'warn' | 'error' }
const controlLogs = ref<CtrlLog[]>([])

const keys = ref({ w: false, a: false, s: false, d: false })

// ---- 控制模式 ----
// tapMode=false: 长按模式（松开归零）
// tapMode=true:  点按模式（每次按键递增/递减，不自动归零）
const tapMode = ref(false)
// 点按模式下的当前目标速度
const tapVx = ref(0)
const tapWz = ref(0)
// 点按模式步进量
const TAP_VX_STEP = 0.05   // 每次按键线速度步进 (m/s)
const TAP_WZ_STEP = 0.1    // 每次按键角速度步进 (rad/s)

function toggleMode() {
  tapMode.value = !tapMode.value
  // 切换模式时先停车
  tapVx.value = 0
  tapWz.value = 0
  targetVx = 0
  targetWz = 0
  smoothVx = 0
  smoothWz = 0
  keys.value = { w: false, a: false, s: false, d: false }
  sendVelocity(0, 0, 0)
  addLog(`已切换到${tapMode.value ? '点按' : '长按'}模式`, 'info')
}

let joystick: ReturnType<typeof nipplejs.create> | null = null
let unsubOdom: (() => void) | null = null

// ---- 计算属性 ----

// 显示速度：优先使用里程计真实速度，无数据时用指令速度
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
  return {
    x: p.x - odomOffsetX.value,
    y: p.y - odomOffsetY.value,
    yaw: p.yaw - odomOffsetYaw.value,
  }
})

const totalDistance = computed(() => {
  return robotStore.odomData?.odometry?.total_distance
    ?? robotStore.robotStatus?.odometry?.total_distance
    ?? 0
})

function velBarClass(val: number) {
  const abs = Math.abs(val)
  if (abs > 0.6) return 'high'
  if (abs > 0.2) return 'mid'
  return 'low'
}

// ---- 控制参数 ----
const JOYSTICK_DEADZONE = 0.08      // 摇杆死区（force 比例，0~1）
const JOYSTICK_SIZE = 140           // 摇杆尺寸（px），越大精度越高
const LP_ALPHA = 0.18               // 低通滤波系数（保留，用于无方向变化的平滑过渡）
const LP_ALPHA_UP = 0.30            // 加速时响应更快（同向加速或从零启动）
const LP_ALPHA_DOWN = 0.40          // 减速/归零/反向时较果断（不能太大，否则每帧值不同导致抖动）
const SEND_INTERVAL_MS = 50         // 速度指令发送间隔（ms），20Hz
const DIAGONAL_SCALE = 0.707        // 对角线移动时速度归一化系数（1/√2）
// 归零阈值：低于此值强制归零，防止舵机持续收到微小角速度指令抖动
const VX_ZERO_THRESHOLD = 0.01      // 线速度归零阈值 (m/s)
const WZ_ZERO_THRESHOLD = 0.02      // 角速度归零阈值 (rad/s)，与 stm32_bridge 20mrad/s 死区对齐
// 发送变化检测阈值：变化小于此值不发送，减少无效串口帧
const VX_SEND_THRESHOLD = 0.01
const WZ_SEND_THRESHOLD = 0.015

// 低通滤波目标值（摇杆/键盘写入，发送循环读取）
let targetVx = 0
let targetWz = 0
// 当前平滑后的发送值
let smoothVx = 0
let smoothWz = 0
// 发送定时器（替代 keyboardTimer，统一处理摇杆+键盘）
let sendTimer: ReturnType<typeof setInterval> | null = null
// 摇杆是否激活（激活时忽略键盘输入）
let joystickActive = false

// ---- 摇杆控制 ----
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
    // 死区过滤：force 小于阈值时视为零输入
    if (force < JOYSTICK_DEADZONE) {
      targetVx = 0
      targetWz = 0
      return
    }
    // 将 force 重新映射到 [0,1]（去掉死区后线性拉伸）
    const mappedForce = (force - JOYSTICK_DEADZONE) / (1 - JOYSTICK_DEADZONE)
    const angle = data.angle.radian
    // nipplejs: angle 0=右, π/2=上, π=左, 3π/2=下
    // 前后：sin(angle)  → 上=+vx（前进），下=-vx（后退）
    // 左右：-cos(angle) → 左=+wz（左转），右=-wz（右转），符合 ROS2 右手坐标系
    targetVx = Math.sin(angle) * mappedForce * linearSpeed.value
    targetWz = -Math.cos(angle) * mappedForce * angularSpeed.value
  })

  joystick.on('end', () => {
    joystickActive = false
    targetVx = 0
    targetWz = 0
  })
}

// ---- 方向按钮（触屏，setPointerCapture 防多指误触） ----
function onDpadDown(e: PointerEvent, key: 'w' | 'a' | 's' | 'd') {
  ;(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId)
  if (tapMode.value) {
    // 点按模式：每次按下递增/递减，不设置 keys（不会在松开时归零）
    tapStep(key)
  } else {
    keys.value[key] = true
  }
}
function onDpadUp(key: 'w' | 'a' | 's' | 'd') {
  if (!tapMode.value) {
    keys.value[key] = false
  }
}

// 点按模式：按一次步进
function tapStep(key: 'w' | 'a' | 's' | 'd') {
  const maxVx = ROBOT_MAX_LINEAR_VEL
  const maxWz = ROBOT_MAX_ANGULAR_VEL
  if (key === 'w') tapVx.value = Math.min(tapVx.value + TAP_VX_STEP, maxVx)
  if (key === 's') tapVx.value = Math.max(tapVx.value - TAP_VX_STEP, -maxVx)
  if (key === 'a') tapWz.value = Math.min(tapWz.value + TAP_WZ_STEP, maxWz)
  if (key === 'd') tapWz.value = Math.max(tapWz.value - TAP_WZ_STEP, -maxWz)
  // 点按模式直接更新目标值，绕过键盘状态
  targetVx = tapVx.value
  targetWz = tapWz.value
  addLog(`点按 ${key.toUpperCase()}: vx=${tapVx.value.toFixed(2)}, wz=${tapWz.value.toFixed(2)}`, 'info')
}

// ---- 键盘控制 ----
function onKeyDown(e: KeyboardEvent) {
  const tag = (e.target as HTMLElement).tagName
  if (tag === 'INPUT' || tag === 'TEXTAREA') return
  const k = e.key.toLowerCase()
  if (k === ' ') { emergencyStop(); e.preventDefault(); return }

  if (tapMode.value) {
    // 点按模式：keydown 只触发一次（不重复）
    if (e.repeat) return
    if (k === 'w' || k === 'arrowup') { tapStep('w'); e.preventDefault() }
    if (k === 'a' || k === 'arrowleft') { tapStep('a'); e.preventDefault() }
    if (k === 's' || k === 'arrowdown') { tapStep('s'); e.preventDefault() }
    if (k === 'd' || k === 'arrowright') { tapStep('d'); e.preventDefault() }
  } else {
    // 长按模式
    if (k === 'w' || k === 'arrowup') { keys.value.w = true; e.preventDefault() }
    if (k === 'a' || k === 'arrowleft') { keys.value.a = true; e.preventDefault() }
    if (k === 's' || k === 'arrowdown') { keys.value.s = true; e.preventDefault() }
    if (k === 'd' || k === 'arrowright') { keys.value.d = true; e.preventDefault() }
  }
}

function onKeyUp(e: KeyboardEvent) {
  if (tapMode.value) return  // 点按模式不处理 keyup
  const tag = (e.target as HTMLElement).tagName
  if (tag === 'INPUT' || tag === 'TEXTAREA') return
  const k = e.key.toLowerCase()
  if (k === 'w' || k === 'arrowup') keys.value.w = false
  if (k === 'a' || k === 'arrowleft') keys.value.a = false
  if (k === 's' || k === 'arrowdown') keys.value.s = false
  if (k === 'd' || k === 'arrowright') keys.value.d = false
}

// 从键盘状态计算目标速度（长按模式，对角线归一化）
function calcKeyTarget(): { vx: number; wz: number } {
  let vx = 0, wz = 0
  if (keys.value.w) vx += linearSpeed.value
  if (keys.value.s) vx -= linearSpeed.value
  if (keys.value.a) wz += angularSpeed.value
  if (keys.value.d) wz -= angularSpeed.value
  // 对角线同时按下时，速度向量归一化（防止斜向超速）
  if (vx !== 0 && wz !== 0) {
    vx *= DIAGONAL_SCALE
    wz *= DIAGONAL_SCALE
  }
  return { vx, wz }
}

// ---- 非对称低通滤波：加速快响应，减速/归零/反向快衰减 ----
function smoothStep(current: number, target: number): number {
  // 归零：直接清零，不做低通，避免拖尾期间持续发送微小值给舵机
  if (target === 0) {
    return current + LP_ALPHA_DOWN * (target - current)
  }
  // 方向反转：快速过零，避免反向惯性拖尾
  if (target * current < 0) {
    return current + LP_ALPHA_DOWN * (target - current)
  }
  // 加速（同向增大幅值）或从零启动：灵敏响应
  if (Math.abs(target) > Math.abs(current)) {
    return current + LP_ALPHA_UP * (target - current)
  }
  // 减速（同向减小幅值）：较平滑，防止急停冲击
  return current + LP_ALPHA_DOWN * (target - current)
}

// ---- 统一发送循环（非对称低通滤波 + 节流） ----
function startSendLoop() {
  sendTimer = setInterval(() => {
    // 摇杆激活时两种模式都忽略键盘/点按
    if (!joystickActive) {
      if (tapMode.value) {
        // 点按模式：targetVx/Wz 由 tapStep 直接写入，此处不覆盖
      } else {
        // 长按模式：从键盘状态实时计算
        const kt = calcKeyTarget()
        targetVx = kt.vx
        targetWz = kt.wz
      }
    }
    // 非对称低通滤波：加速快、减速/归零/反向更果断
    smoothVx = smoothStep(smoothVx, targetVx)
    smoothWz = smoothStep(smoothWz, targetWz)
    // 归零死区：两种模式都生效，防止舵机持续收到微小角速度指令抖动
    // 注意：死区阈值要与 stm32_bridge 侧死区（8mm/s, 20mrad/s）对齐
    if (Math.abs(smoothVx) < VX_ZERO_THRESHOLD) smoothVx = 0
    if (Math.abs(smoothWz) < WZ_ZERO_THRESHOLD) smoothWz = 0
    // 点按模式：smoothWz 归零后同步清零 tapWz，防止下次循环重新拉起
    if (tapMode.value && smoothWz === 0 && targetWz !== 0 && Math.abs(targetWz) < WZ_ZERO_THRESHOLD) {
      tapWz.value = 0
      targetWz = 0
    }
    // 只在值有明显变化时发送，过滤掉低通滤波尾部的微小波动
    const vxChanged = Math.abs(smoothVx - cmdVx.value) > VX_SEND_THRESHOLD
    const wzChanged = Math.abs(smoothWz - cmdWz.value) > WZ_SEND_THRESHOLD
    if (vxChanged || wzChanged) {
      sendVelocity(smoothVx, 0, smoothWz)
    }
  }, SEND_INTERVAL_MS)
}

async function sendVelocity(vx: number, vy: number, wz: number) {
  cmdVx.value = vx
  cmdWz.value = wz
  try {
    await controlApi.setVelocity(vx, vy, wz)
  } catch { /* 静默失败，避免频繁报错 */ }
}

async function emergencyStop() {
  cmdVx.value = 0
  cmdWz.value = 0
  keys.value = { w: false, a: false, s: false, d: false }
  // 点按模式下急停同时清零目标速度
  tapVx.value = 0
  tapWz.value = 0
  targetVx = 0
  targetWz = 0
  smoothVx = 0
  smoothWz = 0
  try {
    await controlApi.stop()
    addLog('急停已执行', 'warn')
    ElMessage.warning('急停已执行')
  } catch (e) {
    addLog('急停指令发送失败', 'error')
    ElMessage.error('急停指令发送失败')
  }
}

function resetOdom() {
  const p = robotStore.currentPose
  odomOffsetX.value = p.x
  odomOffsetY.value = p.y
  odomOffsetYaw.value = p.yaw
  addLog('里程计已重置', 'info')
  ElMessage.success('里程计已重置')
}

function addLog(msg: string, level: 'info' | 'warn' | 'error' = 'info') {
  controlLogs.value.push({
    time: dayjs().format('HH:mm:ss'),
    msg,
    level,
  })
  if (controlLogs.value.length > 200) controlLogs.value.shift()
}

// 自动滚动日志
watch(() => controlLogs.value.length, async () => {
  await nextTick()
  if (logRef.value) logRef.value.scrollTop = logRef.value.scrollHeight
})

onMounted(() => {
  initJoystick()
  window.addEventListener('keydown', onKeyDown)
  window.addEventListener('keyup', onKeyUp)
  startSendLoop()

  // 订阅里程计数据（store 已自动更新，此处仅保留取消订阅句柄）
  unsubOdom = wsClient.on('odom', () => {})

  addLog('控制界面已就绪，WASD/方向键控制，空格急停', 'info')
})

onUnmounted(() => {
  joystick?.destroy()
  window.removeEventListener('keydown', onKeyDown)
  window.removeEventListener('keyup', onKeyUp)
  if (sendTimer) clearInterval(sendTimer)
  if (unsubOdom) unsubOdom()
  // 离开页面时发送停止指令
  controlApi.stop().catch(() => {})
})
</script>

<style lang="scss" scoped>
.control-view { display: flex; flex-direction: column; gap: 12px; }

// ---- 摇杆 ----
.joystick-area {
  display: flex; flex-direction: column; align-items: center; gap: 8px;
  .joystick-zone {
    // 与 JOYSTICK_SIZE(140px) 保持一致，给摇杆留足操作空间
    width: 180px; height: 180px; background: rgba(0,212,255,0.05);
    border: 2px solid var(--color-border); border-radius: 50%; position: relative;
  }
  .joystick-hint { font-size: 11px; color: var(--color-text-muted); }
}

// ---- 方向按钮 ----
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

// ---- 键盘提示 ----
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

// ---- 速度参数 ----
.speed-control {
  display: flex; flex-direction: column; gap: 12px; margin-bottom: 16px;
  .speed-row {
    display: flex; align-items: center; gap: 10px;
    .label { font-size: 12px; color: var(--color-text-muted); min-width: 50px; }
    .slider { flex: 1; }
    .unit { font-size: 11px; color: var(--color-text-muted); min-width: 36px; }
  }
}

// ---- 速度仪表盘 ----
.vel-dashboard {
  display: flex; flex-direction: column; gap: 10px; margin-bottom: 16px;
}

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

// ---- 急停按钮 ----
.estop-btn {
  width: 100%; height: 44px; font-size: 14px; font-weight: 700;
  background: rgba(255,68,68,0.1) !important;
  border: 2px solid var(--color-danger) !important;
  color: var(--color-danger) !important;
  &:hover { background: rgba(255,68,68,0.2) !important; }
  &:active { transform: scale(0.98); }
}

// ---- 里程计 ----
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

// ---- 控制日志 ----
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

// ---- 点按模式速度显示 ----
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
