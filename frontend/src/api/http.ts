// =============================================================================
// HTTP API 封装（axios）
// =============================================================================

import axios from 'axios'
import { API_BASE_URL } from '@/config'

// 通用请求实例（较长超时，用于非实时接口）
const http = axios.create({
  baseURL: API_BASE_URL,
  timeout: 10000,
  headers: { 'Content-Type': 'application/json' },
})

// 急停专用实例：适中超时（800ms），急停必须送达，不能太短
// 注意：速度控制已迁移到 WebSocket 通道，不再需要 ctrlHttp 发速度
const stopHttp = axios.create({
  baseURL: API_BASE_URL,
  timeout: 800,
  headers: { 'Content-Type': 'application/json' },
})

// 响应拦截器（通用）
http.interceptors.response.use(
  (res) => res.data,
  (err) => {
    console.error('[API]', err.response?.data || err.message)
    return Promise.reject(err)
  },
)

// 响应拦截器（急停专用，静默失败但记录警告）
stopHttp.interceptors.response.use(
  (res) => res.data,
  (err) => {
    if (axios.isCancel(err)) return Promise.reject(err)
    console.warn('[ESTOP]', err.response?.data || err.message)
    return Promise.reject(err)
  },
)

// =============================================================================
// 急停请求
// 速度控制已通过 WebSocket 通道发送（wsClient.sendCmdVel），HTTP 只保留急停。
// 急停独立通道，不受 WebSocket 速度消息影响。
// =============================================================================
function sendStopRequest() {
  return stopHttp.post('/api/control/stop')
}

// =============================================================================
// HTTP fallback 速度请求（WebSocket 不可用时使用）
// 零速（停车）帧不使用 AbortController，确保不被后续请求取消
// =============================================================================
let _velAbortController: AbortController | null = null

function sendVelocityRequest(linear_x: number, linear_y: number, angular_z: number) {
  const isStop = linear_x === 0 && linear_y === 0 && angular_z === 0

  if (isStop) {
    // 零速帧：独立请求，不参与 abort 链，确保停车必然到达
    if (_velAbortController) {
      _velAbortController.abort()
      _velAbortController = null
    }
    return http.post('/api/control/velocity', { linear_x: 0, linear_y: 0, angular_z: 0 })
  }

  // 非零速：取消上一个还未完成的速度请求，防止请求堆积
  if (_velAbortController) {
    _velAbortController.abort()
  }
  _velAbortController = new AbortController()

  return http.post(
    '/api/control/velocity',
    { linear_x, linear_y, angular_z },
    { signal: _velAbortController.signal, timeout: 400 },
  )
}

// =============================================================================
// 控制 API
// =============================================================================
export const controlApi = {
  /** 急停（HTTP 独立通道，始终可靠送达） */
  stop: sendStopRequest,
  /** HTTP fallback 速度控制（正常情况用 wsClient.sendCmdVel） */
  setVelocity: sendVelocityRequest,
  setMode: (mode: string) => http.post('/api/control/mode', { mode }),
  getParams: () => http.get('/api/control/params'),
}

// =============================================================================
// SLAM API
// =============================================================================
export const slamApi = {
  getAlgorithms: () => http.get('/api/slam/algorithms'),
  start: (algorithm: string) => http.post('/api/slam/start', { algorithm }),
  stop: () => http.post('/api/slam/stop'),
  getStatus: () => http.get('/api/slam/status'),
  saveMap: (name: string) => http.post('/api/slam/map/save', { name }),
  loadMap: (path: string) => http.post('/api/slam/map/load', { path }),
  listMaps: () => http.get('/api/slam/map/list'),
  deleteMap: (name: string) => http.delete(`/api/slam/map/${name}`),
}

// =============================================================================
// 导航 API
// =============================================================================
export const navigationApi = {
  getAlgorithms: () => http.get('/api/navigation/algorithms'),
  setGoal: (x: number, y: number, yaw: number = 0) =>
    http.post('/api/navigation/goal', { x, y, yaw }),
  cancel: () => http.post('/api/navigation/cancel'),
  getStatus: () => http.get('/api/navigation/status'),
  setWaypoints: (waypoints: Array<{ x: number; y: number; yaw?: number }>) =>
    http.post('/api/navigation/waypoints', { waypoints }),
  getParams: () => http.get('/api/navigation/params'),
}

// =============================================================================
// 设备 API
// =============================================================================
export const deviceApi = {
  getInfo: () => http.get('/api/device/info'),
  getStatus: () => http.get('/api/device/status'),
  getConfig: () => http.get('/api/device/config'),
  updateConfig: (config: Record<string, unknown>) =>
    http.post('/api/device/config', { config }),
  resetConfig: () => http.post('/api/device/config/reset'),
  getSensors: () => http.get('/api/device/sensors'),
  reboot: () => http.post('/api/device/reboot'),
  ros2Diag: () => http.get('/api/device/ros2/diag'),
}

// =============================================================================
// 系统 API
// =============================================================================
export const systemApi = {
  health: () => http.get('/api/health'),
  wsStats: () => http.get('/api/ws/stats'),
}

export default http
