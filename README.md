# RDK S100 智能机器人上位机系统

基于 FastAPI + Vue3 的 Web 上位机，部署在 RDK S100 设备上，通过局域网浏览器访问，无需安装客户端。

## 功能模块

| 模块 | 说明 |
|------|------|
| 综合监控 | CPU/内存/温度实时曲线、机器人状态、日志 |
| 视频监控 | RGB + 深度图像实时显示、截图、全屏（v6.0 D435i 真实相机 + YOLO 检测标注） |
| 激光雷达 | Livox Mid-360S 3D 点云实时显示（PointCloud2） |
| IMU 姿态 | Three.js 3D 姿态展示、加速度(g)/角速度(rad/s)曲线、互补滤波姿态解算（v5.0 真实接入） |
| 机器人控制 | 虚拟摇杆、WASD 键盘、长按/点按双模式、速度调节、急停、里程计实时显示（v8.0 流畅度+稳定性优化） |
| 目标检测 | YOLOv5 目标检测 + D435i 深度测距，带框+距离标注视频推送（v6.0 新增） |
| SLAM 建图 | Cartographer 2D/3D 建图（v7.0 真实接入 + v8.0 前倾40° TF 补偿）、占据栅格地图、轨迹、地图保存/加载 |
| 导航规划 | Nav2 目标点设置、多点巡逻（预留） |
| 设备管理 | 设备信息、传感器状态、参数配置 |

## 目录结构

```
rdks100_slam/
├── backend/                  # FastAPI 后端
│   ├── app/
│   │   ├── core/
│   │   │   ├── config.py     # 全局宏定义（修改此文件配置参数）
│   │   │   └── websocket_manager.py
│   │   ├── services/
│   │   │   ├── mock_data.py  # 模拟数据生成器
│   │   │   ├── ros2_bridge.py
│   │   │   └── data_pusher.py
│   │   └── api/
│   │       ├── control.py    # 速度控制（线速度+角速度双斜坡加速度限幅）
│   │       ├── slam.py
│   │       ├── navigation.py
│   │       └── device.py
│   ├── main.py
│   ├── requirements.txt
│   └── static/dist/          # 前端构建产物（自动生成）
├── frontend/                 # Vue3 前端
│   ├── src/
│   │   ├── config/index.ts   # 前端宏定义
│   │   ├── views/            # 各功能页面
│   │   ├── stores/robot.ts   # Pinia 全局状态
│   │   └── api/              # HTTP + WebSocket 封装
│   └── package.json
├── ros2_ws/                  # ROS2 工作空间（统一管理所有 ROS2 包）
│   └── src/
│       ├── ldlidar_ros2/          # LD14/14P 激光雷达驱动
│       ├── livox_ros_driver2/     # Livox Mid-360S 驱动
│       ├── d435i_bringup/         # D435i 相机启动包（v6.0 新增）
│       │   └── launch/d435i_camera.launch.py # 启动 realsense2_camera_node
│       ├── d435i_detection/       # YOLOv5 目标检测+深度测距（v6.0 新增）
│       │   ├── d435i_detection/detection_node.py  # 核心检测节点（双缓冲+独立推理线程）
│       │   └── launch/detection.launch.py          # 一键启动相机+检测
│       ├── czybot_navigation2/    # 机器人运动控制（STM32 串口桥接 + 终端键盘控制）
│       │   └── scripts/
│       │       ├── stm32_bridge.py           # STM32 串口桥接节点（三层防抖）
│       │       └── ackermann_teleop_key.py   # 终端键盘遥控（select 非阻塞读取）
│       └── czybot_slam/           # Cartographer SLAM 建图（v7.0 新增）
│           ├── launch/                        # 3 种启动文件（2D/3D/slam_toolbox）
│           │   ├── cartographer_2d_slam.launch.py
│           │   ├── cartographer_3d_slam.launch.py
│           │   └── slam_toolbox_mapping.launch.py
│           ├── config/                        # 参数配置
│           │   ├── cartographer_2d.lua / cartographer_3d.lua
│           │   ├── pointcloud_to_laserscan.yaml
│           │   └── slam_toolbox_params.yaml
│           ├── scripts/
│           │   ├── scan_dedup.py              # LaserScan 时间戳去重节点
│           │   └── save_map.sh                # 地图保存脚本（nav2_map_server）
│           └── rviz/
│               ├── slam_2d.rviz / slam_3d.rviz # RViz2 可视化配置
├── d435i_ros2/               # YOLOv5 源码 + 权重文件（v6.0 新增，随 deploy.sh 打包）
├── deploy.sh                 # 部署到 RDK 脚本
├── build_ros2_ws.sh          # ROS2 工作空间编译脚本
├── MID360S_RVIZ_SETUP.md     # Livox Mid-360S RViz2 远程可视化配置指南
├── LIVOX_MID360_MIGRATION.md # LD14P → Mid-360S 迁移方案
├── MODULE_PLAN.txt           # 模块化迭代演进方案
├── start.sh                  # 一键启动脚本
└── README.md
```

### 已完成的工作

**YOLO 检测修复**（CPU 版 `detection_node.py`）：

- 根因：`torch.load` 手动加载 YOLOv5 时 `model(tensor)` 返回原始锚点张量（shape `[1,25200,85]`），未做 NMS 直接遍历导致全场景覆盖框；同时 `frame_count` 变量名拼写错误
- 修复：加入完整 `apply_nms()` + `_greedy_nms()` fallback，修复变量名

**BPU 检测节点**（`detection_node_bpu.py`，板端用户实现）：

- 使用 `hbm_runtime.HB_HBMRuntime` + `/opt/hobot/model/s100/basic/yolov5x_672x672_nv12.hbm`
- 依赖 `/app/pydev_demo/utils` 中的 `preprocess_utils / postprocess_utils / common_utils / draw_utils`
- 修复了 `self._pub_anno` 变量名冲突（发布者对象覆盖 topic 字符串），改为 `self._pub_anno_node`
- `setup.py` 已注册 `detection_node_bpu` 入口点

**前端/后端 topic 分离**：

- 问题：`data_pusher.py` 把带框 `annotated_image` 优先推送到 `video_rgb`，导致 RGB 原图板块也显示检测框
- 修复：`websocket_manager.py`：新增 `"video_annotated"` topic
- `data_pusher.py`：`video_rgb` 只推纯原图；带框图像改推 `video_annotated`（无数据时不推占位帧）
- `VideoView.vue`：`unsubAnno` 改订阅 `video_annotated`

**v7.0 SLAM 建图**（`czybot_slam` 功能包）：

- 实现了真实小车 odom→map 坐标系链接，Cartographer 建图 → /map → WebSocket → 前端
- 新增 `scan_dedup.py`：修复 pointcloud_to_laserscan 重复时间戳导致 Cartographer 丢弃帧问题
- 新增 `save_map.sh`：nav2_map_server 地图保存脚本，含 my_map 副本用于导航
- Cartographer 2D/3D 参数已针对 Livox Mid-360S + RDK S100 优化

**其他已修改文件**：

- `detection_params.yaml`：增加 `iou_threshold / max_detections / target_classes` 参数及 COCO 类别 ID 速查注释
- `VideoView.vue`：第二行新增 AI 检测标注图区域 + 识别结果列表面板
- `websocket_manager.py`：新增 `detection_results` topic
- `ros2_bridge.py`：新增 `/detection/results` 订阅 + `_parse_detection_results()`
- `data_pusher.py`：新增 `push_detection_results()` 10Hz 推送任务
- `requirements.txt`：`opencv-python` → `opencv-python-headless==4.9.0.80`，启用 `numpy==1.26.4`

**v8.0 前端控制流畅度与稳定性优化**：

- 对虚拟摇杆、WASD 键盘、长按/点按双模式的响应延迟进行了全面优化
- 小车控制更加稳定，消除操控过程中的卡顿和指令抖动
- WebSocket 控制指令传输优化，降低网络延迟对实时操控的影响

**v8.0 Livox Mid-360S 前倾 40° 安装 TF 旋转补偿**：

雷达实际安装前倾约 40°，`livox_frame` 坐标系的 X 轴朝前下方倾斜，通过修改 6 个文件在静态 TF 中加入旋转补偿，让下游所有节点（Cartographer、slam_toolbox、pointcloud_to_laserscan）都工作在正确的坐标系下。

**四元数计算（pitch = -40°，绕 Y 轴，前倾为负）：**
```
qx = 0.0
qy = sin(-20°) = -0.342
qz = 0.0
qw = cos(-20°) = 0.940
```

| 文件 | 参数 | 原值 | 新值 | 原因 |
|------|------|------|------|------|
| `cartographer_2d_slam.launch.py` | 静态TF四元数 | `0.0, 0.0, 0.0, 1.0` | `0.0, -0.342, 0.0, 0.940` | 补偿前倾旋转 |
| `cartographer_3d_slam.launch.py` | 静态TF四元数 | 同上 | 同上 | 同上 |
| `slam_toolbox_mapping.launch.py` | 静态TF四元数 | 同上 | 同上 | 同上 |
| `pointcloud_to_laserscan.yaml` | `min_height` | `0.05` | `-1.5` | 前倾后前方3m处障碍物 z≈-1.78m，需负值才能采到 |
| `pointcloud_to_laserscan.yaml` | `max_height` | `0.5` | `1.2` | 覆盖近距离仰视方向点云 |
| `cartographer_2d.lua` | 注释 | — | 新增前倾补偿说明 | 文档化补偿机制 |
| `cartographer_3d.lua` | 注释 | — | 新增前倾补偿+IMU自动旋转说明 | 文档化补偿机制 |

> **说明**：
> - launch/yaml/lua 均为资源文件，`--symlink-install` 模式下修改立即生效，无需重新编译
> - 编译报错是 build 缓存引用了旧路径 `/home/sunrise`（环境迁移遗留问题），`rm -rf build/ install/` 后重新编译即可

> **⚠ 重要标注（后续可能还原到正常状态）：**
> - 若雷达恢复**水平安装**，需还原：3个launch文件四元数改回 `0.0, 0.0, 0.0, 1.0`；`pointcloud_to_laserscan.yaml` 的 `min_height` 改回 `0.05`、`max_height` 改回 `0.5`
> - 若实际前倾角度不是精确 40°，调整四元数公式：`qy = sin(-angle/2)`, `qw = cos(-angle/2)`，`angle` 单位为弧度

### 新增功能一：D435i 相机 ROS2 启动包 `d435i_bringup`

**位置**：`rdks100_slam/ros2_ws/src/d435i_bringup/`

新建标准 ROS2 包，负责启动 Intel RealSense D435i 相机驱动节点。

新增文件：

- `package.xml` — 包声明，依赖 `realsense2_camera`
- `CMakeLists.txt` — 构建配置
- `config/d435i_params.yaml` — 相机参数（640×480×30fps，RGB+深度流，深度自动对齐到彩色帧，D435i 内置 IMU 已启用）
- `launch/d435i_camera.launch.py` — 启动 `realsense2_camera_node`，将对齐深度 topic `/camera/aligned_depth_to_color/image_raw` 重映射为后端 `config.py` 期望的 `/camera/depth/image_raw`

---

### 新增功能二：视频推送改造（真实相机数据接入）

**位置**：`rdks100_slam/backend/app/services/data_pusher.py`

将原 `push_mock_video`（纯色渐变占位 PNG）替换为 `push_video`（真实相机数据优先，降级模拟兜底）。

数据流：

```
realsense2_camera_node
  → /camera/color/image_raw
  → /camera/depth/image_raw
    ↓
ros2_bridge.get_latest("rgb_image") / get_latest("depth_image")
    ↓
data_pusher.push_video()
    ↓
WebSocket → 前端视频窗口
```

关键特性：

- `ros2_bridge.is_enabled=true` 且相机在线时自动切换为真实 JPEG 帧
- 无相机时无缝降级为占位 PNG，前端不空白
- 每帧携带 `source` 字段（`realsense_d435i` / `mock`），方便前端区分数据来源
- 诊断日志：数据源切换时立即打印，每 100 帧打一次常规日志

---

### 新增功能三：YOLOv5 目标检测 + 深度测距 ROS2 节点 `d435i_detection`

**位置**：`rdks100_slam/ros2_ws/src/d435i_detection/`

将 `d435i_ros2/main_debug.py` 中的 YOLO 检测+深度测距逻辑，改造为可被 `colcon build` 识别的标准 ROS2 Python 包。

新增文件：

- `package.xml` / `setup.py` / `setup.cfg` — 标准包骨架
- `d435i_detection/detection_node.py` — 核心节点
- `config/detection_params.yaml` — 参数配置（模型路径、置信度、采样点数等）
- `launch/detection.launch.py` — 一键启动相机+检测，支持 `camera:=false` 单独启动检测节点

**节点行为**：

- 订阅 `/camera/color/image_raw`（RGB8）+ `/camera/depth/image_raw`（Z16 对齐深度）
- 使用 `yolov5s` CPU 推理进行目标检测（后续可换 BPU 量化模型，已完成 GPU 模型适配）
- 对每个检测框在中心区域随机采样 24 个深度点，经中值滤波得到距离估计（移植自 `main_debug.py` 的 `get_mid_pos` 函数）
- 发布 `/detection/results`（`std_msgs/String`，JSON 格式，含类别、置信度、bbox 坐标、距离单位米）
- 发布 `/detection/annotated_image`（带绿框+距离标注的 BGR 图像）
- **线程架构**：spin 线程只写双缓冲，独立推理线程负责 YOLO+测距+发布，互不阻塞

## 快速开始

### 环境要求

- Python 3.8+
- Node.js 18+（仅构建前端时需要）
- ROS2 Humble（可选，无 ROS2 时自动使用模拟数据）

### 方式一：一键启动（推荐）

```bash
cd /home/sunrise/rdks100_slam
chmod +x start.sh

# 生产模式（构建前端 + 启动后端）
./start.sh prod

# 开发模式（后端 + 前端热重载）
./start.sh dev
```

### 方式二：手动启动

**后端：**
```bash
cd /home/sunrise/rdks100_slam/backend

# 创建虚拟环境
python3 -m venv venv
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 加载 ROS2 环境（可选）
source /opt/ros/humble/setup.bash

# 启动
python3 main.py
```

**前端（开发模式）：**
```bash
cd /home/sunrise/rdks100_slam/frontend
npm install
npm run dev
```

**前端（生产构建）：**
```bash
cd /home/sunrise/rdks100_slam/frontend
npm run build
# 构建产物自动输出到 backend/static/dist/
```

### Cartographer SLAM 建图（v7.0 新增，真实 odom→map）

一键启动 2D/3D Cartographer 建图（自动按时序启动所有节点）：

```bash
cd ~/rdks100_slam/ros2_ws
source install/setup.bash

# 2D 建图（推荐）
ros2 launch czybot_slam cartographer_2d_slam.launch.py

# 备选：slam_toolbox 建图（更低 CPU）
ros2 launch czybot_slam slam_toolbox_mapping.launch.py
```

> **说明**：启动后遥控小车走动，9 秒后 RViz2 自动打开显示实时建图效果。
> 建图完成后执行 `bash ~/rdks100_slam/ros2_ws/src/czybot_slam/scripts/save_map.sh` 保存地图。

### Livox Mid-360S 雷达驱动启动（3D 点云 + IMU 数据源）

在独立终端中启动 Livox 雷达驱动，提供 `/livox/lidar`（PointCloud2）和 `/livox/imu` 两个 topic：

```bash
# 加载 ROS2 工作空间环境
source /home/sunrise/rdks100_slam/ros2_ws/install/setup.bash

# 启动 Mid-360S 雷达驱动（PointCloud2 + IMU）
ros2 launch livox_ros_driver2 msg_MID360s_launch.py
```

> **说明**：`msg_MID360s_launch.py` 使用 `MID360s_config.json` 配置，xfer_format=0（PointCloud2 格式），
> 与后端 `_parse_pointcloud2()` 匹配。另有一个 `msg_MID360_launch.py`（使用 `MID360_config.json`），
> 内含特定设备 bd_code，一般使用 `msg_MID360s_launch.py` 即可。
>
> 启动后可用以下命令验证数据是否正常：
> ```bash
> ros2 topic list | grep livox    # 应看到 /livox/lidar 和 /livox/imu
> ros2 topic hz /livox/imu        # 约 200 Hz
> ros2 topic hz /livox/lidar      # 约 10 Hz
> ```

### STM32 串口桥接节点（真实机器人运动控制）

在独立终端中启动 ROS2 STM32 桥接节点，用于将 `/cmd_vel` 指令转发给底盘 STM32：

```bash
# 首次编译 ROS2 工作空间
bash /home/sunrise/rdks100_slam/build_ros2_ws.sh

# 加载工作空间环境
source /home/sunrise/rdks100_slam/ros2_ws/install/setup.bash

# 启动 STM32 桥接节点
ros2 run czybot_navigation2 stm32_bridge
```

> **注意**：默认串口为 `/dev/ttyUSB0`，波特率 `115200`。如需修改，编辑
> `ros2_ws/src/czybot_navigation2/scripts/stm32_bridge.py` 中的 `SERIAL_PORT` 和 `BAUD_RATE`。

### 终端键盘遥控（调试用）

```bash
source /home/sunrise/rdks100_slam/ros2_ws/install/setup.bash
ros2 run czybot_navigation2 ackermann_teleop_key
```

> 使用 WASD 控制小车，Q 键退出。已优化为非阻塞读取，按键响应灵敏。最大线速度 0.5 m/s，最大角速度 0.8 rad/s。

### D435i 相机启动（v6.0 新增）

在独立终端中启动 D435i 相机驱动：

```bash
cd ~/rdks100_slam/ros2_ws
colcon build --packages-select d435i_bringup
source install/setup.bash
ros2 launch d435i_bringup d435i_camera.launch.py
```

> **说明**：发布 `/camera/camera/color/image_raw`（RGB8 30Hz）和 `/camera/camera/aligned_depth_to_color/image_raw`（Z16 对齐深度）。
> 验证：`ros2 topic hz /camera/camera/color/image_raw` → 约 30 Hz。

### YOLOv5 目标检测 + 深度测距（v6.0 新增）

相机启动后，启动检测节点：

```bash
cd ~/rdks100_slam/ros2_ws
colcon build --packages-select d435i_detection
source install/setup.bash

# 仅检测节点（相机已单独启动）
ros2 launch d435i_detection detection.launch.py camera:=false
```

> **说明**：yolov5s CPU 推理 ~2FPS。发布 `/detection/results`（JSON）和 `/detection/annotated_image`（BGR8 带框+距离）。
> 后端 `data_pusher.push_video()` 三级降级：ros2_annotated → ros2 → mock。

### 访问

启动后在局域网内任意浏览器访问：

```
http://<设备IP>:8000
```

例如：`http://10.21.1.145:8000`

## IMU 真实接入（v5.0）

### 硬件特性

系统使用 Livox Mid-360S 内置 IMU，发布到 `/livox/imu`（`sensor_msgs/Imu`），频率 200Hz。

| 特性 | 参数 |
|------|------|
| 加速度量程 | ±8g |
| 陀螺仪量程 | ±2000°/s |
| 输出频率 | 200 Hz |
| 姿态四元数 | 恒为单位四元数 (0,0,0,1)，IMU 不输出姿态 |
| 加速度单位 | g（不是 m/s²） |
| 角速度单位 | rad/s |

### 互补滤波姿态解算

后端 `ros2_bridge._parse_imu()` 使用互补滤波从原始 6 轴数据解算姿态：

- **Roll/Pitch**：α=0.98 互补滤波，0.98×(陀螺仪积分) + 0.02×(加速度计修正)
- **Yaw**：纯陀螺仪积分（无磁力计，长时间漂移）
- **dt**：用 ROS2 消息时间戳计算，异常时默认 0.01s

### 数据格式

`_parse_imu()` 输出与 `mock_data.get_imu_data()` 一致：

```json
{
  "timestamp": 1234567890.123,
  "orientation": {
    "roll": 1.5,
    "pitch": -0.3,
    "yaw": 45.0,
    "quaternion": {"x": 0, "y": 0, "z": 0, "w": 1}
  },
  "angular_velocity": {"x": 0.01, "y": -0.02, "z": 0.05},
  "linear_acceleration": {"x": 0.01, "y": -0.02, "z": 0.98},
  "temperature": 0.0
}
```

> **注意**：`linear_acceleration` 单位为 g（1g ≈ 9.81 m/s²），`angular_velocity` 单位为 rad/s。
> `quaternion` 为 Livox 原始值，始终为单位四元数；姿态角（roll/pitch/yaw）由互补滤波计算。

### 已知局限

- **Yaw 漂移**：无磁力计或外部参考，Yaw 角会随时间累积漂移，需要 SLAM（LIO-SAM/FAST-LIO）或磁力计修正
- **精度限制**：互补滤波适合姿态展示和基本状态监控，不适合精确导航定位
- **加速度单位**：Livox IMU 输出单位为 g，前端已适配显示；mock 数据也使用相同单位

> **⚠ 重要：以上局限仅影响前端 IMU 页面展示，不影响后续 SLAM 建图。**
> SLAM（LIO-SAM/FAST-LIO）不依赖互补滤波输出的姿态角，而是直接使用 IMU 原始 6 轴数据
>（200Hz 角速度 + 加速度）与 LiDAR 点云做紧耦合融合：
> - IMU 提供 200Hz 高频运动预测 → 解决帧间运动估计
> - LiDAR 提供低频绝对位置修正 → 消除 IMU 积分漂移
> - 因子图优化 / 迭代卡尔曼滤波自动估计并补偿 IMU bias
>
> 原始 IMU 数据（200Hz、±8g、±2000°/s）质量完全满足 LIO-SAM/FAST-LIO 的输入要求。

## 相机与目标检测（v6.0 新增）

### 硬件特性

系统使用 Intel RealSense D435i 深度相机，通过 `d435i_bringup` 包启动驱动。

| 特性 | 参数 |
|------|------|
| 分辨率 | 640×480 |
| 帧率 | 30 fps |
| RGB Topic | `/camera/camera/color/image_raw` (RGB8) |
| 深度 Topic | `/camera/camera/aligned_depth_to_color/image_raw` (Z16，对齐) |
| 内置 IMU | 已启用（6 轴加速度+陀螺仪） |

### 视频推送三级降级（data_pusher.push_video）

`push_video()` 替代了原有的 `push_mock_video()`：

| 优先级 | source 值 | 条件 |
|--------|-----------|------|
| ① 最优 | `ros2_annotated` | 检测节点在线，推送带检测框+距离标注的图像 |
| ② 次选 | `ros2` | 相机在线但检测未启动，推送原始 RGB 图像 |
| ③ 兜底 | `mock` | 相机离线，推送占位 PNG，前端不空白 |

### YOLOv5 目标检测 + 深度测距（d435i_detection）

**数据流：**
```
D435i → /camera/camera/color/image_raw (30Hz)
      → d435i_detection → YOLOv5s GPU ~2FPS
      → /detection/annotated_image (BGR8 带框+距离)
      → ros2_bridge._parse_annotated_image() → JPEG base64
      → data_pusher.push_video() → WebSocket → 前端 VideoView.vue
```

**检测结果格式（`/detection/results`，JSON）：**
```json
{
  "detections": [
    {
      "class": "person",
      "confidence": 0.87,
      "bbox": {"x1": 120, "y1": 80, "x2": 380, "y2": 450},
      "distance_m": 2.35
    }
  ],
  "num_detections": 1
}
```

**线程架构：**
- **spin 线程**：订阅图像 → 写入双缓冲（不阻塞推理）
- **推理线程**：读取双缓冲 → YOLOv5 推理 → 深度采样中值滤波 → 发布结果

**深度测距（`get_mid_pos`）：**
- 对每个检测框中心区域随机采样 24 个深度点
- 中值滤波去除离群值，得到稳定距离估计（单位：米）

### 部署说明

```bash
# 1. 下载 YOLOv5 权重（部署前执行一次）
wget -P /home/sunrise/d435i_ros2/weights \
  https://github.com/ultralytics/yolov5/releases/download/v7.0/yolov5s.pt
cp -r /home/sunrise/d435i_ros2 /home/sunrise/rdks100_slam/d435i_ros2

# 2. 部署到 RDK
bash /home/sunrise/rdks100_slam/deploy.sh

# 3. RDK 上编译新包
cd ~/rdks100_slam/ros2_ws
colcon build --packages-select d435i_bringup d435i_detection
source install/setup.bash

# 4. 启动相机
ros2 launch d435i_bringup d435i_camera.launch.py

# 5. 启动检测节点
ros2 launch d435i_detection detection.launch.py camera:=false
```

## SLAM 建图（v7.0 新增）

### 概述

`czybot_slam` 功能包实现了 Cartographer SLAM 建图，支持 2D 和 3D 两种模式，以及 slam_toolbox 备选方案。核心通过 Cartographer 发布 `map→odom` TF 变换，打通了真实小车的 odom→map 坐标系。

### 数据流（2D Cartographer，推荐）

```
Mid-360S → /livox/lidar (PointCloud2, 10Hz, livox_frame坐标系，有40°前倾)
  → pointcloud_to_laserscan（base_link坐标系下切片 -1.5m~1.2m，TF已补偿前倾）
    → /scan (LaserScan)
      → scan_dedup.py（时间戳去重，丢弃重复帧）
        → /scan_dedup
          → cartographer_node（2D 纯激光扫描匹配 + STM32 里程计融合）
            → cartographer_occupancy_grid_node
              → /map (OccupancyGrid) → ros2_bridge → WebSocket → 前端 SlamView
```

### TF 树

```
map → odom          (Cartographer 发布，回环优化后更新)
odom → base_link     (STM32 stm32_bridge 发布，轮式里程计)
base_link → livox_frame (静态 TF，雷达安装高度 0.15m + 前倾40°旋转补偿，v8.0)
```

> **v8.0**：雷达前倾约 40°，`base_link→livox_frame` 静态 TF 已加入 pitch=-40° 旋转补偿（四元数 `0.0, -0.342, 0.0, 0.940`），
> 下游 Cartographer/slam_toolbox/pointcloud_to_laserscan 均工作在正确的补偿坐标系下。

### 启动命令

```bash
cd ~/rdks100_slam/ros2_ws
colcon build --packages-select czybot_slam
source install/setup.bash

# 方案一：Cartographer 2D（推荐，最稳定）
ros2 launch czybot_slam cartographer_2d_slam.launch.py

# 方案二：slam_toolbox（更低 CPU 占用）
ros2 launch czybot_slam slam_toolbox_mapping.launch.py

# 方案三：Cartographer 3D（需更多 CPU，可选启用 IMU）
ros2 launch czybot_slam cartographer_3d_slam.launch.py use_imu:=true
```

> **v8.0 说明**：启动文件已包含雷达前倾 40° 的 TF 旋转补偿（静态 TF 四元数 `0.0, -0.342, 0.0, 0.940`），
> 若雷达恢复水平安装，需将 3 个 launch 文件中的四元数改回 `0.0, 0.0, 0.0, 1.0`。

> **说明**：启动文件自动按时序启动所有节点（STM32 桥接 → Livox 驱动 → 点云转换 → 去重 → Cartographer → 地图栅格 → RViz2），
> 9 秒后 RViz2 自动打开 `/map`、`/scan_dedup`、`/submap_list` 显示。

### 地图保存

```bash
# 建图完成后保存地图
bash ~/rdks100_slam/ros2_ws/src/czybot_slam/scripts/save_map.sh

# 或指定地图名称
bash ~/rdks100_slam/ros2_ws/src/czybot_slam/scripts/save_map.sh my_lab_map
```

地图保存至 `~/rdks100_slam/my_map/`，同时自动生成 `my_map.pgm` / `my_map.yaml` 最新副本，供后续 Nav2 导航直接使用。

### 关键技术修复

| 问题 | 方案 |
|------|------|
| pointcloud_to_laserscan 连续帧输出相同时间戳，Cartographer 要求严格递增 | `scan_dedup.py`：只转发 `ts > last_ts` 的帧到 `/scan_dedup` |
| STM32 启动延迟导致 Cartographer 报 TF 异常 | TF 超时容忍 0.3s |
| 地面反射和车体遮挡干扰建图 | pointcloud_to_laserscan 切片高度 0.05m~0.5m（v8.0 前倾后调整为 -1.5m~1.2m） |
| 雷达安装外参 | 静态 TF base_link→livox_frame：(0, 0, 0.15)（v8.0 新增前倾40°旋转补偿 qy=-0.342, qw=0.940） |
| 雷达前倾40°导致前方障碍物点云丢失（v8.0） | 静态TF旋转补偿 + pointcloud_to_laserscan min_height→-1.5m |

### 验证

```bash
# 检查 TF 树
ros2 run tf2_tools view_frames

# 检查 /map 发布频率
ros2 topic hz /map

# 查看地图数据
ros2 topic echo /map --once
```

## 机器人控制说明

### 控制方式

> **v8.0**：对 WebSocket 控制指令传输进行了优化，虚拟摇杆/WASD/点按模式的响应延迟显著降低，小车操控更加流畅稳定。

| 方式 | 说明 |
|------|------|
| 虚拟摇杆 | 触屏/鼠标拖拽，支持死区过滤（8%）和 smoothStep 自适应滤波 |
| WASD 键盘 | W/S 控制线速度，A/D 控制角速度，支持 smoothStep 平滑 |
| 方向 D-pad | 屏幕方向按钮，支持多点触控防误触 |

### 控制模式

| 模式 | 说明 |
|------|------|
| 长按模式（默认） | 按键/摇杆松开后小车立即停止，适合精确控制 |
| 点按模式 | 每次按键速度递增/递减（步进 0.05 m/s / 0.1 rad/s），松开不归零，适合长距离匀速行驶 |

点击控制页面右上角的 **长按 / 点按** 按钮切换模式。急停按钮在两种模式下均立即清零所有速度。

### 控制优化参数（防抖专项 v5）

前端 → 后端 → STM32 桥接 → 底盘，四层防抖链路逐级兜底：

| 层级 | 参数 | 值 | 说明 |
|------|------|----|------|
| **前端** | 摇杆死区 | 8% | 消除手指抖动引起的误触 |
| | 自适应滤波（加速） | α=0.30 | 加速阶段响应更快，更跟手 |
| | 自适应滤波（减速/归零/反向） | α=0.40 | 减速/松手快速响应，防舵机抖动 |
| | 发送间隔 | 50 ms (20 Hz) | 节流，避免 HTTP 请求堆积 |
| | 线速度零阈值 | 0.01 m/s | 低于此值归零，与 STM32 8mm/s 死区对齐 |
| | 角速度零阈值 | 0.02 rad/s | 低于此值归零，与 STM32 20mrad/s 死区对齐 |
| **后端** | 线速度加速度限幅 | 2.0 m/s² | 防止速度突变冲击底盘 |
| | 角速度加速度限幅 | 4.0 rad/s² | 防止舵机急转抖动 |
| **STM32桥接** | 线速度死区 | 8 mm/s | 硬件层消除微小速度指令 |
| | 角速度死区 | 20 mrad/s | 硬件层消除舵机抖动 |
| | 去重阈值（线速度） | 5 mm/s | 变化量低于此值不重复发送 |
| | 去重阈值（角速度） | 10 mrad/s | 变化量低于此值不重复发送 |
| | 超时保护 | 0.3 s | 无新指令自动发送停车帧，松手即停 |

### 防抖链路

```
前端 smoothStep(加速α=0.30/减速α=0.40) + 死区 0.02rad/s + 变化检测
  → 后端 线速度2.0m/s² + 角速度4.0rad/s² 双斜坡限幅
    → STM32桥接 死区20mrad/s + 去重10mrad/s + 0.3s超时自动停车
      → STM32 舵机
```

## 激光雷达可视化

支持两种方式查看 Livox Mid-360S 3D 点云：

| 方式 | 说明 | 文档 |
|------|------|------|
| RViz2 (X11) | SSH -X 远程 RViz2，原生 3D 点云 | [MID360S_RVIZ_SETUP.md](MID360S_RVIZ_SETUP.md) |
| Web UI (Three.js) | 浏览器访问 `:8000`，实时 3D 点云可旋转 | 见下方说明 |

### Web UI 3D 点云特性

- **Three.js + OrbitControls**：左键旋转、右键平移、滚轮缩放
- **10000 点/帧 @ 10Hz**：保留约 50% 原始密度，流畅推送
- **3 种着色模式**：高度 / 强度 / 距离，5 段渐变色表
- **AdditiveBlending**：密集区域自然变亮，增强立体感
- **高度过滤**：Z 轴滑块实时过滤，聚焦感兴趣区域
- **视角预设**：俯视 / 正视 / 侧视 / 等轴一键切换
- **FPS + 点数 overlay**：实时监控渲染性能

### ROS2 诊断接口

```bash
# 检查 ROS2 桥接状态（排查数据不通问题）
curl http://<设备IP>:8000/api/device/ros2/diag
```

## 配置说明

### 后端配置（`backend/app/core/config.py`）

```python
ROS2_ENABLED = True                    # 默认 true，rclpy 不存在时自动降级模拟
DEVICE_PORT = 8000                     # 后端端口
PUSH_RATE_LIDAR = 0.1                  # 点云推送间隔（秒，10Hz）

# ROS2 Topic 名称（按实际修改）
ROS2_TOPIC_LIDAR3D = "/livox/lidar"    # Livox Mid-360S PointCloud2
ROS2_TOPIC_IMU = "/livox/imu"          # Livox 内置 IMU
ROS2_TOPIC_CMD_VEL = "/cmd_vel"
ROS2_TOPIC_ODOM = "/odom"
ROS2_TOPIC_RGB_IMAGE: str = "/camera/camera/color/image_raw"              # RGB 图像（D435i 实际 topic）
ROS2_TOPIC_DEPTH_IMAGE: str = "/camera/camera/aligned_depth_to_color/image_raw"  # 对齐深度
ROS2_TOPIC_ANNOTATED_IMAGE: str = "/detection/annotated_image"   # YOLO 检测标注图（v6.0）
```

### 前端配置（`frontend/src/config/index.ts`）

```typescript
// WebSocket 地址自动从 window.location 推断，无需手动配置
// 如需固定地址，设置环境变量 VITE_WS_BASE_URL
export const LIDAR_MAX_POINTS = 10000  // 前端最大渲染点数
export const LIDAR_Z_MIN = -0.5        // 高度过滤下限
export const LIDAR_Z_MAX = 2.0         // 高度过滤上限
```

## ROS2 集成

当 `MOCK_MODE = False` 且 `ROS2_ENABLED = True` 时，系统自动订阅以下 Topic：

| Topic | 消息类型 | 说明 |
|-------|---------|------|
| `/livox/lidar` | `sensor_msgs/PointCloud2` | 激光雷达（Mid-360S） |
| `/livox/imu` | `sensor_msgs/Imu` | 雷达内置 IMU（v5.0 真实接入，互补滤波解算） |
| `/scan` | `sensor_msgs/LaserScan` | 激光雷达（LD14P 兼容，已废弃） |
| `/odom` | `nav_msgs/Odometry` | 里程计（由 STM32 桥接节点发布） |
| `/map` | `nav_msgs/OccupancyGrid` | SLAM 地图（v7.0 Cartographer 真实建图输出） |
| `/battery_state` | `sensor_msgs/BatteryState` | 电池 |
| `/camera/camera/color/image_raw` | `sensor_msgs/Image` | RGB 图像（v6.0 D435i 真实接入，30Hz） |
| `/camera/camera/aligned_depth_to_color/image_raw` | `sensor_msgs/Image` | 对齐深度图像（v6.0 真实接入） |
| `/detection/results` | `std_msgs/String` | YOLOv5 检测结果 JSON（v6.0 新增） |
| `/detection/annotated_image` | `sensor_msgs/Image` | 检测标注图像 BGR8（v6.0，后端→WebSocket） |

发布 Topic：

| Topic | 消息类型 | 说明 |
|-------|---------|------|
| `/cmd_vel` | `geometry_msgs/Twist` | 速度控制（由 STM32 桥接节点消费） |
| `/goal_pose` | `geometry_msgs/PoseStamped` | 导航目标 |

### STM32 桥接节点（`czybot_navigation2`）

`stm32_bridge.py` 是连接 ROS2 与底盘 STM32 的核心节点：

- 订阅 `/cmd_vel`，将 Twist 消息转换为 STM32 串口协议帧发送
- 接收 STM32 上报的里程计数据，发布到 `/odom`
- 内置死区滤波：线速度 < 5 mm/s 或角速度 < 15 mrad/s 时置零，消除舵机抖动

## WebSocket 协议

连接地址：`ws://<host>:8000/ws` 或 `ws://<host>:8000/ws/lidar,imu`

消息格式：
```json
{
  "topic": "robot_status",
  "data": { ... },
  "timestamp": 1234567890.123
}
```

支持的 Topic：`system`, `robot_status`, `lidar`, `imu`, `slam_map`, `video_rgb`, `video_depth`, `video_annotated`, `detection_results`, `navigation`, `log`, `heartbeat`, `odom`

> **v6.0 视频推送**：
> - `video_rgb`：纯 RGB 原图，自动选择最佳数据源（ros2 → mock），前端通过 `source` 字段区分
> - `video_annotated`：AI 检测标注图（带绿框+距离），仅检测节点在线时推送
> - `detection_results`：YOLO 检测结果 JSON，10Hz 推送

## 网络配置

| 设备 | IP | 说明 |
|------|-----|------|
| RDK S100 Wi-Fi | `10.21.1.145` | PC 通过此 IP 访问 |
| RDK S100 eth1 | `192.168.1.50/24` | 连接雷达的网口 |
| Livox Mid-360S | `192.168.1.138` | 雷达固定 IP |

## 开发说明

- 所有可配置参数集中在 `config.py`（后端）和 `config/index.ts`（前端），修改后重启生效
- 模拟数据模式下无需任何硬件即可完整体验所有功能
- 前端构建产物由 FastAPI 作为静态文件服务，生产环境只需启动后端一个进程
- 控制优化采用三层死区方案：前端零阈值 → 后端线速度加速度限幅 → STM32 硬件死区，彻底消除舵机抖动
