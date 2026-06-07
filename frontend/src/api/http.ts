// =============================================================================
// HTTP API 封装（axios）
// =============================================================================

import axios from 'axios'
import { API_BASE_URL } from '@/config'

const http = axios.create({
  baseURL: API_BASE_URL,
  timeout: 10000,
  headers: { 'Content-Type': 'application/json' },
})

// 响应拦截器
http.interceptors.response.use(
  (res) => res.data,
  (err) => {
    console.error('[API]', err.response?.data || err.message)
    return Promise.reject(err)
  },
)

// =============================================================================
// 控制 API
// =============================================================================
export const controlApi = {
  setVelocity: (linear_x: number, linear_y: number, angular_z: number) =>
    http.post('/api/control/velocity', { linear_x, linear_y, angular_z }),
  stop: () => http.post('/api/control/stop'),
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
