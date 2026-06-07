// =============================================================================
// 前端全局配置（宏定义）
// 所有可变参数集中在此，方便按需修改
// =============================================================================

// -----------------------------------------------------------------------------
// 后端连接配置
// 开发时通过 vite proxy 转发，生产时直接访问设备 IP
// -----------------------------------------------------------------------------

/** 后端 API 基础地址（开发时留空走 vite proxy，生产时填设备 IP:PORT） */
export const API_BASE_URL: string = import.meta.env.VITE_API_BASE_URL || ''

/** 后端 WebSocket 地址（自动根据当前页面 host 推断） */
export const WS_BASE_URL: string = (() => {
  if (import.meta.env.VITE_WS_BASE_URL) return import.meta.env.VITE_WS_BASE_URL
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const host = window.location.host
  return `${protocol}//${host}`
})()

/** WebSocket 完整地址 */
export const WS_URL: string = `${WS_BASE_URL}/ws`

// -----------------------------------------------------------------------------
// WebSocket 重连配置
// -----------------------------------------------------------------------------
/** 初始重连延迟（毫秒） */
export const WS_RECONNECT_DELAY_MS: number = 2000
/** 最大重连延迟（毫秒） */
export const WS_RECONNECT_MAX_DELAY_MS: number = 30000
/** 重连延迟倍增系数 */
export const WS_RECONNECT_BACKOFF: number = 1.5
/** 心跳间隔（毫秒） */
export const WS_HEARTBEAT_MS: number = 5000

// -----------------------------------------------------------------------------
// 数据显示配置
// -----------------------------------------------------------------------------
/** 实时曲线最大数据点数 */
export const CHART_MAX_POINTS: number = 100
/** 日志最大显示行数 */
export const LOG_MAX_LINES: number = 500
/** 3D 激光雷达点云最大点数（Livox Mid-360S，降采样后约 8000~10000 点） */
export const LIDAR_MAX_POINTS: number = 10000

// -----------------------------------------------------------------------------
// 机器人控制参数
// -----------------------------------------------------------------------------
/** 最大线速度（m/s） */
export const ROBOT_MAX_LINEAR_VEL: number = 1.0
/** 最大角速度（rad/s） */
export const ROBOT_MAX_ANGULAR_VEL: number = 1.5
/** 默认线速度（m/s） */
export const ROBOT_DEFAULT_LINEAR_VEL: number = 0.3
/** 默认角速度（rad/s） */
export const ROBOT_DEFAULT_ANGULAR_VEL: number = 0.5
/** 键盘控制发送间隔（毫秒） */
export const KEYBOARD_SEND_INTERVAL_MS: number = 100

// -----------------------------------------------------------------------------
// 激光雷达可视化配置（3D Livox Mid-360S）
// -----------------------------------------------------------------------------
/** 激光雷达最大显示范围（米），Mid-360S 量程 40m，俯视图默认显示 10m 半径 */
export const LIDAR_DISPLAY_RANGE: number = 10.0
/** 障碍物警告距离（米） */
export const LIDAR_WARN_DISTANCE: number = 0.5
/** 3D 点云高度着色范围：z 最小值（米），低于此值显示为蓝色 */
export const LIDAR_Z_MIN: number = -0.5
/** 3D 点云高度着色范围：z 最大值（米），高于此值显示为红色 */
export const LIDAR_Z_MAX: number = 2.0

// -----------------------------------------------------------------------------
// IMU 可视化配置
// -----------------------------------------------------------------------------
/** IMU 曲线刷新间隔（毫秒） */
export const IMU_CHART_INTERVAL_MS: number = 50

// -----------------------------------------------------------------------------
// 系统监控阈值（与后端保持一致）
// -----------------------------------------------------------------------------
export const SYS_CPU_WARN: number = 80
export const SYS_MEM_WARN: number = 85
export const SYS_TEMP_WARN: number = 75
export const SYS_TEMP_CRITICAL: number = 90
export const BATTERY_WARN: number = 20
export const BATTERY_CRITICAL: number = 10

// -----------------------------------------------------------------------------
// UI 主题色（深色科技风）
// -----------------------------------------------------------------------------
export const THEME = {
  primary: '#00d4ff',
  success: '#00ff88',
  warning: '#ffaa00',
  danger: '#ff4444',
  info: '#8888ff',
  bg: '#0a0e1a',
  bgCard: '#0d1526',
  bgPanel: '#111827',
  border: '#1e3a5f',
  text: '#e0e6f0',
  textMuted: '#6b7a99',
} as const
