# =============================================================================
# RDK S100 智能机器人上位机系统 - 全局配置（宏定义）
# 所有可变参数集中在此文件，方便后续按需修改
# =============================================================================

from typing import List
import os

# -----------------------------------------------------------------------------
# 设备基础配置
# -----------------------------------------------------------------------------
DEVICE_HOST: str = os.getenv("DEVICE_HOST", "0.0.0.0")   # 后端监听地址，0.0.0.0 表示监听所有网卡
DEVICE_PORT: int = int(os.getenv("DEVICE_PORT", "8000"))  # 后端服务端口
DEVICE_NAME: str = "RDK S100 智能机器人"                   # 设备名称
DEVICE_VERSION: str = "1.0.0"                              # 系统版本

# -----------------------------------------------------------------------------
# CORS 跨域配置（前端开发时需要）
# -----------------------------------------------------------------------------
CORS_ORIGINS: List[str] = [
    "http://localhost",
    "http://localhost:3000",
    "http://localhost:5173",
    "http://localhost:8080",
    "http://127.0.0.1",
    "http://127.0.0.1:3000",
    "http://127.0.0.1:5173",
    "*",  # 局域网访问，生产环境可改为具体IP段
]

# -----------------------------------------------------------------------------
# WebSocket 配置
# -----------------------------------------------------------------------------
WS_HEARTBEAT_INTERVAL: float = 5.0    # WebSocket 心跳间隔（秒）
WS_MAX_CONNECTIONS: int = 50           # 最大 WebSocket 连接数
WS_MESSAGE_QUEUE_SIZE: int = 100       # 消息队列大小

# -----------------------------------------------------------------------------
# 数据推送频率配置（Hz -> 秒间隔）
# -----------------------------------------------------------------------------
PUSH_RATE_SYSTEM_INFO: float = 1.0     # 系统信息推送间隔（秒）
PUSH_RATE_ROBOT_STATUS: float = 0.1    # 机器人状态推送间隔（秒，10Hz）
PUSH_RATE_LIDAR: float = 0.1           # 激光雷达数据推送间隔（秒，10Hz）
PUSH_RATE_IMU: float = 0.05            # IMU 数据推送间隔（秒，20Hz）
PUSH_RATE_SLAM_MAP: float = 0.5        # SLAM 地图推送间隔（秒，2Hz）
PUSH_RATE_VIDEO: float = 0.033         # 视频帧推送间隔（秒，~30fps）
PUSH_RATE_LOG: float = 0.5             # 日志推送间隔（秒）

# -----------------------------------------------------------------------------
# ROS2 配置
# -----------------------------------------------------------------------------
# ROS2_ENABLED 默认 true：只要 rclpy 可导入就启用真实数据；
# 若 rclpy 不存在，ros2_bridge 内部会自动捕获 ImportError 并降级为模拟模式。
# 如需强制模拟模式，设置环境变量 ROS2_ENABLED=false
ROS2_ENABLED: bool = os.getenv("ROS2_ENABLED", "true").lower() == "true"
ROS2_DOMAIN_ID: int = int(os.getenv("ROS_DOMAIN_ID", "0"))

# ROS2 Topic 名称（标准命名，可按实际修改）
ROS2_TOPIC_CMD_VEL: str = "/cmd_vel"                        # 速度控制
ROS2_TOPIC_ODOM: str = "/odom"                              # 里程计
ROS2_TOPIC_SCAN: str = "/scan"                              # 2D 激光雷达扫描（已弃用，保留兼容）
ROS2_TOPIC_LIDAR3D: str = "/livox/lidar"                    # 3D 激光雷达点云（Livox Mid-360S）
ROS2_TOPIC_IMU: str = "/livox/imu"                          # IMU 数据（Livox 内置 IMU）
ROS2_TOPIC_MAP: str = "/map"                                # SLAM 地图
ROS2_TOPIC_POSE: str = "/robot_pose"                        # 机器人位姿
ROS2_TOPIC_BATTERY: str = "/battery_state"                  # 电池状态
ROS2_TOPIC_RGB_IMAGE: str = "/camera/camera/color/image_raw"       # RGB 图像（RealSense 实际 topic）
ROS2_TOPIC_DEPTH_IMAGE: str = "/camera/camera/aligned_depth_to_color/image_raw"  # 对齐到 RGB 的深度图像
ROS2_TOPIC_ANNOTATED_IMAGE: str = "/detection/annotated_image"   # 带检测框+距离标注的 RGB 图像（BGR8）
ROS2_TOPIC_DETECTION_RESULTS: str = "/detection/results"          # YOLO 检测结果 JSON（std_msgs/String）
ROS2_TOPIC_CAMERA_INFO: str = "/camera/camera/color/camera_info"   # 相机信息
ROS2_TOPIC_POINTCLOUD: str = "/livox/lidar"                 # 3D 点云数据（与 LIDAR3D 同源）
ROS2_TOPIC_SLAM_POSE: str = "/slam/pose"                    # SLAM 位姿
ROS2_TOPIC_PATH: str = "/plan"                              # 规划路径
ROS2_TOPIC_GOAL: str = "/goal_pose"                         # 导航目标点
ROS2_TOPIC_DIAGNOSTICS: str = "/diagnostics"                # 诊断信息

# ROS2 Service 名称
ROS2_SERVICE_SAVE_MAP: str = "/slam/save_map"               # 保存地图
ROS2_SERVICE_LOAD_MAP: str = "/map_server/load_map"         # 加载地图
ROS2_SERVICE_START_SLAM: str = "/slam/start"                # 启动 SLAM
ROS2_SERVICE_STOP_SLAM: str = "/slam/stop"                  # 停止 SLAM
ROS2_SERVICE_CLEAR_COSTMAP: str = "/clear_costmaps"         # 清除代价地图

# -----------------------------------------------------------------------------
# 机器人运动参数
# -----------------------------------------------------------------------------
ROBOT_MAX_LINEAR_VEL: float = 1.0      # 最大线速度（m/s）
ROBOT_MAX_ANGULAR_VEL: float = 1.5     # 最大角速度（rad/s）
ROBOT_DEFAULT_LINEAR_VEL: float = 0.3  # 默认线速度（m/s）
ROBOT_DEFAULT_ANGULAR_VEL: float = 0.5 # 默认角速度（rad/s）
ROBOT_EMERGENCY_STOP_DECEL: float = 2.0 # 急停减速度（m/s²）

# -----------------------------------------------------------------------------
# 激光雷达配置
# -----------------------------------------------------------------------------
LIDAR_MAX_RANGE: float = 12.0          # 最大测距范围（米）
LIDAR_MIN_RANGE: float = 0.1           # 最小测距范围（米）
LIDAR_ANGLE_MIN: float = -3.14159      # 最小角度（rad）
LIDAR_ANGLE_MAX: float = 3.14159       # 最大角度（rad）
LIDAR_POINTS_PER_SCAN: int = 360       # 每圈点数

# -----------------------------------------------------------------------------
# 相机配置
# -----------------------------------------------------------------------------
CAMERA_RGB_WIDTH: int = 640            # RGB 图像宽度
CAMERA_RGB_HEIGHT: int = 480           # RGB 图像高度
CAMERA_DEPTH_WIDTH: int = 640          # 深度图像宽度
CAMERA_DEPTH_HEIGHT: int = 480         # 深度图像高度
CAMERA_FPS: int = 30                   # 帧率
CAMERA_JPEG_QUALITY: int = 80          # JPEG 压缩质量（0-100）

# -----------------------------------------------------------------------------
# IMU 配置
# -----------------------------------------------------------------------------
IMU_SAMPLE_RATE: int = 200             # IMU 采样率（Hz）
IMU_ACCEL_RANGE: float = 16.0          # 加速度计量程（g）
IMU_GYRO_RANGE: float = 2000.0         # 陀螺仪量程（°/s）

# -----------------------------------------------------------------------------
# SLAM 配置
# -----------------------------------------------------------------------------
SLAM_ALGORITHMS: list = [
    "cartographer",   # Google Cartographer（激光SLAM）
    "rtab_map",       # RTAB-Map（视觉/融合SLAM）
    "orb_slam3",      # ORB-SLAM3（视觉SLAM）
    "lego_loam",      # LeGO-LOAM（激光SLAM）
    "lio_sam",        # LIO-SAM（融合SLAM）
]
SLAM_DEFAULT_ALGORITHM: str = "cartographer"
SLAM_MAP_SAVE_PATH: str = "/home/sunrise/maps"  # 地图保存路径（sunrise用户目录）
SLAM_MAP_RESOLUTION: float = 0.05       # 地图分辨率（米/像素）
SLAM_MAP_MAX_SIZE: int = 1000           # 地图最大尺寸（像素）

# -----------------------------------------------------------------------------
# 导航配置
# -----------------------------------------------------------------------------
NAV_ALGORITHMS: list = [
    "nav2_default",   # Nav2 默认
    "a_star",         # A* 算法
    "rrt",            # RRT 算法
    "dwa",            # DWA 局部规划
    "teb",            # TEB 局部规划
]
NAV_DEFAULT_ALGORITHM: str = "nav2_default"
NAV_GOAL_TOLERANCE: float = 0.1        # 到达目标点容差（米）
NAV_WAYPOINT_TOLERANCE: float = 0.2    # 途经点容差（米）

# -----------------------------------------------------------------------------
# 系统监控配置
# -----------------------------------------------------------------------------
SYS_CPU_WARN_THRESHOLD: float = 80.0   # CPU 使用率警告阈值（%）
SYS_MEM_WARN_THRESHOLD: float = 85.0   # 内存使用率警告阈值（%）
SYS_TEMP_WARN_THRESHOLD: float = 75.0  # 温度警告阈值（°C）
SYS_TEMP_CRITICAL_THRESHOLD: float = 90.0  # 温度危险阈值（°C）
SYS_BATTERY_WARN_THRESHOLD: float = 20.0   # 电池电量警告阈值（%）
SYS_BATTERY_CRITICAL_THRESHOLD: float = 10.0  # 电池电量危险阈值（%）

# -----------------------------------------------------------------------------
# 日志配置
# -----------------------------------------------------------------------------
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
LOG_MAX_LINES: int = 500               # 前端日志最大显示行数
LOG_FILE_PATH: str = "/home/sunrise/logs/rdks100_webui.log"  # 日志文件路径

# -----------------------------------------------------------------------------
# 模拟数据配置（硬件未就绪时使用）
# -----------------------------------------------------------------------------
MOCK_MODE: bool = os.getenv("MOCK_MODE", "true").lower() == "true"  # 模拟模式开关
MOCK_ROBOT_NAME: str = "RDK-S100-001"
