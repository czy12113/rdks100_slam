// =============================================================================
// HTTP API 封装（axios）
// =============================================================================

import axios from 'axios'
import type { AxiosInstance } from 'axios'
import { API_BASE_URL } from '@/config'

// 通用请求实例（较长超时，用于非实时接口）
const http = axios.create({
  baseURL: API_BASE_URL,
  timeout: 10000,
  headers: { 'Content-Type': 'application/json' },
})

// 控制专用实例：适中超时（500ms），既保证实时性又容忍网络波动
// 太短（200ms）会导致正常请求频繁超时 → _sendingInFlight 锁定时间内跳帧
const ctrlHttp = axios.create({
  baseURL: API_BASE_URL,
  timeout: 500,
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

// 响应拦截器（控制专用，静默失败）
ctrlHttp.interceptors.response.use(
  (res) => res.data,
  (err) => {
    // 被主动取消或超时都静默
    if (axios.isCancel(err) || err.code === 'ECONNABORTED') {
      return Promise.reject(err)
    }
    console.warn('[CTRL]', err.response?.data || err.message)
    return Promise.reject(err)
  },
)

// =============================================================================
// 防堆积速度请求管理器
// 核心思路：每次发送新的速度指令时，取消上一个还在排队/传输中的请求。
// 这确保后端永远只处理「最新的」速度值，不会有旧的高速请求堵在管道里。
// 急停请求不参与取消链——它永远独立发送。
// =============================================================================
let _velAbortController: AbortController | null = null

function sendVelocityRequest(linear_x: number, linear_y: number, angular_z: number) {
  // 取消上一个还未完成的速度请求
  if (_velAbortController) {
    _velAbortController.abort()
  }
  _velAbortController = new AbortController()

  return ctrlHttp.post(
    '/api/control/velocity',
    { linear_x, linear_y, angular_z },
    { signal: _velAbortController.signal },
  )
}

// 急停请求：独立 AbortController，永不被其他请求取消
function sendStopRequest() {
  // 先取消所有待发送的速度请求，防止排队的旧速度覆盖急停
  if (_velAbortController) {
    _velAbortController.abort()
    _velAbortController = null
  }
  return ctrlHttp.post('/api/control/stop')
}

// =============================================================================
// 控制 API（防堆积 + 短超时）
// =============================================================================
export const controlApi = {
  setVelocity: sendVelocityRequest,
  stop: sendStopRequest,
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
