# RDK S100 智能机器人上位机系统

基于 FastAPI + Vue3 的 Web 上位机，部署在 RDK S100 设备上，通过局域网浏览器访问，无需安装客户端。

## 功能模块

| 模块 | 说明 |
|------|------|
| 综合监控 | CPU/内存/温度实时曲线、机器人状态、日志 |
| 视频监控 | RGB + 深度图像实时显示、截图、全屏（v6.0 D435i 真实相机 + YOLO 检测标注） |
| 激光雷达 | Livox Mid-360S 3D 点云实时显示（PointCloud2，v8.1 支持安装俯仰角补偿） |
| IMU 姿态 | Three.js 3D 姿态展示、加速度(g)/角速度(rad/s)曲线、互补滤波姿态解算（v5.0 真实接入） |
| 机器人控制 | 虚拟摇杆、WASD 键盘、长按/点按双模式、速度调节、急停、里程计实时显示（v9.0 SafetyGate + 多层安全停车） |
| 目标检测 | YOLOv5 目标检测 + D435i 深度测距，带框+距离标注视频推送（v6.0 新增） |
| 场景理解 | VLM 视觉语言场景理解：D435i 关键帧 + 检测框 → Qwen-VL → 自然语言描述（v12.0 新增） |
| SLAM 建图 | Cartographer 2D/3D 建图（v7.0 真实接入 + v9.0 重影二次优化）、占据栅格地图、轨迹、地图保存/加载 |
| 导航规划 | Nav2 实车导航链路接入（v10.0，SmacPlanner2D + MPPI Ackermann，联调未完全成功） |
| 设备管理 | 设备信息、传感器状态、参数配置 |

## v12.0 更新摘要

v12.0 在现有 D435i 相机、YOLO/DOSOD 检测、FastAPI WebSocket 和 Vue3 视频监控链路上接入 VLM（视觉语言模型）场景理解。新增 ROS2 包 `vlm_scene`，由 `vlm_node` 订阅 RGB 图像与 `/detection/results`，通过关键帧节流调用 Qwen-VL/OpenAI 兼容 provider，输出 `/vlm/scene_description` 与 `/vlm/status`；后端新增 VLM API、ROS2Bridge 订阅与 WebSocket 推送；前端取消独立 `/vlm` 页面，把“场景理解”面板嵌入 `VideoView.vue` 的视频监控页。

当前 VLM 数据链路：

```
D435i 相机 → YOLO/DOSOD 检测 → vlm_node 关键帧节流
  → Qwen-VL API → 自然语言描述
  → ROS topic + FastAPI WebSocket → 前端 VideoView 场景理解面板
```

板端启动顺序：

```bash
# 终端 A：后端 + 相机 + 检测
cd /home/sunrise/rdks100_slam
./start.sh prod

# 终端 B：VLM 场景理解节点
cd /home/sunrise/rdks100_slam/ros2_ws
source install/setup.bash
ros2 launch vlm_scene vlm.launch.py

# 终端 C：浏览器访问
http://10.21.1.145:8000/#/video
```

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
│   │       ├── vlm.py        # VLM 状态/最新结果/历史/手动 ask API（v12.0）
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
│       ├── vlm_scene/             # VLM 场景理解（v12.0 新增，Qwen-VL/OpenAI/mock provider）
│       │   ├── vlm_scene/vlm_node.py
│       │   ├── vlm_scene/providers/
│       │   ├── vlm_scene/utils/
│       │   ├── config/vlm_params.yaml
│       │   └── launch/vlm.launch.py
│       ├── czybot_navigation2/    # 机器人运动控制/Nav2（STM32 串口桥接 + 阿克曼导航参数）
│       │   └── scripts/
│       │       ├── stm32_bridge.py           # STM32 串口桥接节点（v9.0 限速/急停/watchdog）
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

**v8.x Livox Mid-360S 水平安装恢复**：

雷达现按水平放置处理，`base_link → livox_frame` 静态 TF 只包含安装高度 `0.15m`，四元数为单位旋转 `0.0, 0.0, 0.0, 1.0`。下游 Cartographer、slam_toolbox、pointcloud_to_laserscan 不再使用 40° 前倾补偿。

| 文件 | 参数 | 当前值 | 原因 |
|------|------|------|------|
| `cartographer_2d_slam.launch.py` | 静态TF四元数 | `0.0, 0.0, 0.0, 1.0` | 雷达水平安装 |
| `cartographer_3d_slam.launch.py` | 静态TF四元数 | 同上 | 同上 |
| `slam_toolbox_mapping.launch.py` | 静态TF四元数 | 同上 | 同上 |
| `pointcloud_to_laserscan.yaml` | `min_height/max_height` | `0.15 / 0.90` | v9.0 避开地面杂点并覆盖箱子/桌面高度 |

> **说明**：
> - launch/yaml/lua 均为资源文件，`--symlink-install` 模式下修改立即生效，无需重新编译
> - 编译报错是 build 缓存引用了旧路径 `/home/sunrise`（环境迁移遗留问题），`rm -rf build/ install/` 后重新编译即可

**v8.1 前端可视化点云安装俯仰角补偿**：

根本原因：ROS2 launch 中的静态 TF 只作用于 SLAM/ROS2 TF 链路，前端 3D 点云显示走的是 `ros2_bridge.py → WebSocket → Settings/LidarView` 链路，原先没有读取和应用雷达安装俯仰角，导致前端可视化点云没有做前倾补偿。

- `config.py`：`LIDAR_MOUNT_PITCH_DEG = 0.0`，默认按水平安装处理，支持环境变量覆盖。
- `ros2_bridge.py`：`_parse_pointcloud2()` 增加 Y 轴俯仰旋转补偿：
  `x' = x * cosθ + z * sinθ`，`z' = -x * sinθ + z * cosθ`，`θ = -mount_pitch`；水平安装时 `mount_pitch=0`，该步骤为 no-op。
- `device.py`：`GET /api/device/config` 新增暴露 `mount_pitch` 字段，前端初始化读取默认值。
- `SettingsView.vue`：激光雷达配置卡片新增“安装俯仰角”输入框，范围 `-90°~90°`，步长 `1°`，同步默认值和重置逻辑。

部署构建：

```bash
cd /home/kkk/rdks100_slam/frontend
npm run build
```

构建产物输出到 `backend/static/dist`。后端重启后加载新构建包；修改前端配置后点云补偿热生效，不需要重启服务。

**v8.2（GPT修改版）Cartographer 2D SLAM 建图重影专项优化**：

- `cartographer_2d_slam.launch.py` 重写为干净 ASCII launch 文件，保留原一键启动链路，并新增 `lidar_*`、`scan_*`、`rewrite_scan_stamps` 等现场调参入口。
- `pointcloud_to_laserscan.yaml` 默认切片恢复为水平安装的 `0.05m~0.50m`，`range_max` 调整为 `12.0m`，减少地面、桌腿、门框上沿、多层高度点投影到同一 2D 扫描面导致的双墙/重影。
- `cartographer_2d.lua` 调整为更保守的 2D 建图参数：收紧实时相关性匹配窗口，提高闭环匹配阈值，暂不默认融合未标定 STM32 `/odom`。
- `scan_dedup.py` 参数化 `min_interval_ms`、`rewrite_stamps`、`stamp_step_ms`，增加丢帧/修复统计，并修复 Ctrl-C 退出时重复 `rclpy.shutdown()` 报错。

推荐运行环境仍为目标板：

```bash
source /opt/ros/humble/setup.bash && source ~/rdks100_slam/ros2_ws/install/setup.bash
ros2 launch czybot_slam cartographer_2d_slam.launch.py
```

> **当前默认（v9.0）**：雷达水平安装，3 个 launch 文件四元数为 `0.0, 0.0, 0.0, 1.0`；`pointcloud_to_laserscan.yaml` 与 launch 默认 `min_height=0.15`、`max_height=0.90`。

**v9.0 手动控制安全闭环 + Nav2 阿克曼参数 + Cartographer 重影二次优化**：

- 新增后端 `SafetyGate`，统一处理限速、死区、急停锁和 watchdog；`control.py`、`websocket_manager.py`、`main.py` 的速度出口统一走安全门面。
- `ros2_bridge.py` 增加 `/cmd_vel_estop` 发布与 `publish_estop()`；急停同时走 estop topic 和多帧零速。
- 前端 `ControlView.vue` / `App.vue` 增加失焦、切页、鼠标离窗、页面卸载、WS 断开等兜底停车；`websocket.ts` 增加 `sendBeacon` 急停。
- `stm32_bridge.py` v5 对齐硬限幅 `0.60 m/s` / `1.20 rad/s`，订阅 `/cmd_vel_estop`，并保留 300ms 超时停车。
- `nav2_params.yaml` 改为 Ackermann：MPPI `motion_model=Ackermann`，SmacPlannerHybrid + DUBIN，`minimum_turning_radius=0.45`，移除 `spin/backup`。
- Cartographer 二次调参：子图帧数 `90→35`，优化频率 `70→20`，里程计权重降到 `1e3`，点云切片改为 `0.15m~0.90m`。

关键速度参数：

| 项 | 前端 | 后端 SafetyGate | stm32_bridge | STM32 |
|----|------|-----------------|--------------|-------|
| 最大线速度 | 0.60 m/s | 0.60 m/s | 0.60 m/s | 0.60 m/s |
| 最大角速度 | 1.20 rad/s | 1.20 rad/s | 1.20 rad/s | 1.20 rad/s |
| 软件线速度死区 | 0.005 | 0.005 | 0.005 | 0.02 |
| 软件角速度死区 | 0.010 | 0.010 | 0.010 | 0.03 |
| Watchdog/超时 | 失焦立即触发 | 400 ms | 300-500 ms | 300 ms |

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

### Cartographer SLAM 建图（v9.0 重影二次优化）

一键启动 2D/3D Cartographer 建图（自动按时序启动所有节点）：

```bash
cd ~/rdks100_slam/ros2_ws
source /opt/ros/humble/setup.bash
colcon build --packages-select czybot_slam --symlink-install
source install/setup.bash

# 2D 建图（推荐）
ros2 launch czybot_slam cartographer_2d_slam.launch.py

# 备选：slam_toolbox 建图（更低 CPU）
ros2 launch czybot_slam slam_toolbox_mapping.launch.py
```

> **说明**：v9.0 默认切片 `0.15m~0.90m`，Cartographer 弱化未标定轮式里程计 yaw，让激光匹配主导朝向。启动后遥控小车低速走动，9 秒后 RViz2 自动打开显示实时建图效果。
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

在独立终端中启动 ROS2 STM32 桥接节点，用于将 `/cmd_vel` 指令转发给底盘 STM32，并消费 `/cmd_vel_estop` 急停兜底：

```bash
# 首次编译 ROS2 工作空间
bash /home/sunrise/rdks100_slam/build_ros2_ws.sh

# 加载工作空间环境
source /home/sunrise/rdks100_slam/ros2_ws/install/setup.bash

# 启动 STM32 桥接节点
ros2 run czybot_navigation2 stm32_bridge
```

> **注意**：默认串口为 `/dev/ttyUSB0`，波特率 `115200`。v9.0 中 `stm32_bridge.py` 对齐硬限幅 `0.60 m/s` / `1.20 rad/s`，并保留 300ms 指令超时停车。如需修改串口，编辑 `ros2_ws/src/czybot_navigation2/scripts/stm32_bridge.py` 中的 `SERIAL_PORT` 和 `BAUD_RATE`。

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

### VLM 场景理解（v12.0 新增）

相机和检测节点启动后，启动 VLM 节点：

```bash
cd ~/rdks100_slam/ros2_ws
colcon build --packages-select vlm_scene --symlink-install
source install/setup.bash

# 默认 provider=qwen_vl，调用 DashScope OpenAI 兼容接口
ros2 launch vlm_scene vlm.launch.py

# 离线联调前端时可切到 mock provider
ros2 launch vlm_scene vlm.launch.py provider:=mock

# 手动触发一次分析
ros2 service call /vlm/ask std_srvs/srv/Trigger {}
```

> **说明**：VLM 节点发布 `/vlm/scene_description` 和 `/vlm/status`，前端在 `/#/video` 的“场景理解”区域展示最新描述、状态和历史记录。

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

## VLM 场景理解（v12.0 新增）

`vlm_scene` 功能包把 D435i RGB 关键帧与 YOLO/DOSOD 检测结果送入视觉语言模型，输出适合前端展示或后续 TTS 播报的自然语言场景描述。

### 数据流

```
/camera/camera/color/image_raw
  + /detection/results
    → vlm_node（关键帧节流：冷却 3s + 心跳 20s + 距离变化 0.5m）
      → provider（qwen_vl / openai_vision / deepseek_text / internvl_local / mock）
        → /vlm/scene_description + /vlm/status
          → ros2_bridge → data_pusher → WebSocket
            → VideoView.vue「场景理解」面板
```

### ROS2 包结构

```
ros2_ws/src/vlm_scene/
├── package.xml
├── setup.py
├── setup.cfg
├── config/vlm_params.yaml
├── launch/vlm.launch.py
├── README.md
└── vlm_scene/
    ├── vlm_node.py
    ├── utils/
    │   ├── image_ops.py
    │   └── keyframe.py
    └── providers/
        ├── base.py
        ├── factory.py
        ├── keys.py
        ├── qwen_vl.py
        ├── openai_vision.py
        ├── deepseek_text.py
        ├── internvl_local.py
        └── mock.py
```

### 关键设计

- HTTP 调用使用 Python 标准库 `urllib`，不额外引入 `requests` 或 OpenAI SDK。
- 图像解码由 `image_ops.py` 手写完成，不依赖 `cv_bridge`。
- 检测数据格式与 `d435i_detection` 对齐：`class_id`、`class_name`、`confidence`、`bbox/x1y1x2y2`、`distance_m`。
- provider 统一实现 `describe(VLMRequest) -> VLMResponse`，节点只通过 `create_provider()` 创建实例。
- API Key 与模型名集中在 `providers/keys.py`，读取优先级为环境变量 > 文件常量 > fallback。
- `vlm_node` 启动时只发布一次 ready 状态，后续在关键帧触发或手动 `/vlm/ask` 时更新描述。

### 后端与前端接入

- `backend/app/core/config.py` 新增 `ROS2_TOPIC_VLM_DESCRIPTION`、`ROS2_TOPIC_VLM_STATUS`、`ROS2_SERVICE_VLM_ASK`。
- `backend/app/services/ros2_bridge.py` 新增 VLM topic 订阅、状态/描述解析和 `call_vlm_ask()` service client。
- `backend/app/services/data_pusher.py` 新增 `push_vlm_description()` 与 `push_vlm_status()`。
- `backend/app/core/websocket_manager.py` 新增 `vlm_description` 与 `vlm_status` topic。
- `backend/app/api/vlm.py` 提供 `GET /api/vlm/status`、`GET /api/vlm/latest`、`GET /api/vlm/history?limit=20`、`POST /api/vlm/ask`。
- `frontend/src/views/video/VideoView.vue` 在视频监控页嵌入“场景理解”区域，包含状态 tag、立即分析按钮、描述卡片、手动 prompt 和历史折叠面板。
- 独立 `/vlm` 路由已删除，`vlm_description` 按需订阅，`vlm_status` 默认自动订阅。

### 板端部署

```bash
# 本地部署
bash /home/kkk/rdks100_slam/deploy.sh

# 板端首次依赖
ssh sunrise@10.21.1.145
sudo apt install -y ros-humble-std-srvs
source /home/sunrise/rdks100_slam/backend/venv/bin/activate
pip install --no-cache-dir opencv-python-headless==4.8.1.78 numpy
deactivate

# 编译 VLM 包
cd /home/sunrise/rdks100_slam/ros2_ws
colcon build --packages-select vlm_scene --symlink-install
source install/setup.bash
```

> 注意：前端变更需要在本地先执行 `npm run build`，再执行 `deploy.sh`。当前部署脚本排除了 `frontend/node_modules`，板端不会重新构建前端。

### 验证

```bash
ros2 topic echo /vlm/status --once
ros2 topic echo /vlm/scene_description --once
ros2 service call /vlm/ask std_srvs/srv/Trigger {}
curl http://10.21.1.145:8000/api/vlm/status
```

## SLAM 建图（v7.0 新增，v9.0 GPT修改版优化）

### 概述

`czybot_slam` 功能包实现了 Cartographer SLAM 建图，支持 2D 和 3D 两种模式，以及 slam_toolbox 备选方案。v9.0 GPT修改版继续针对 2D 建图重影问题优化：降低未标定轮式里程计 yaw 权重，缩短 submap，提升全局优化频率，并把点云转 LaserScan 默认切片改为 `0.15m~0.90m`。

### 数据流（2D Cartographer，推荐）

```
Mid-360S → /livox/lidar (PointCloud2, 10Hz, livox_frame坐标系，水平安装)
  → pointcloud_to_laserscan（base_link坐标系下默认切片 0.15m~0.90m，range_max=12m）
    → /scan (LaserScan)
      → scan_dedup.py（限频 + 可选时间戳单调修复，发布统计日志）
        → /scan_dedup
          → cartographer_node（降低轮式里程计权重，激光扫描匹配主导朝向）
            → cartographer_occupancy_grid_node
              → /map (OccupancyGrid) → ros2_bridge → WebSocket → 前端 SlamView
```

### TF 树

```
map/odom/base_link   (Cartographer 维护 SLAM 位姿；STM32 在该 launch 中 publish_tf=false)
base_link → livox_frame (静态 TF，默认高度 0.15m + 单位旋转；支持 lidar_* 参数现场微调)
```

> **当前默认**：雷达水平安装，`base_link→livox_frame` 静态 TF 四元数为 `0.0, 0.0, 0.0, 1.0`。
>
> **v9.0**：重影根因按“轮式里程计 yaw 带打滑误差却被当作强真值”处理。`cartographer_2d.lua` 将 odometry 权重降到 `1e3`，让激光匹配主导朝向；后续若 D435i IMU 接入 Cartographer，可再开启 `use_imu_data=true`。

### 启动命令

```bash
cd ~/rdks100_slam/ros2_ws
source /opt/ros/humble/setup.bash
colcon build --packages-select czybot_slam
source install/setup.bash

# 方案一：Cartographer 2D（推荐，最稳定）
ros2 launch czybot_slam cartographer_2d_slam.launch.py

# 常用调参：v9.0 默认切片
ros2 launch czybot_slam cartographer_2d_slam.launch.py scan_min_height:=0.15 scan_max_height:=0.90 scan_range_max:=12.0

# 对比测试：关闭 scan_dedup 人工改时间戳
ros2 launch czybot_slam cartographer_2d_slam.launch.py rewrite_scan_stamps:=false

# 现场外参微调示例
ros2 launch czybot_slam cartographer_2d_slam.launch.py lidar_x:=0.02 lidar_y:=0.00 lidar_z:=0.15

# 方案二：slam_toolbox（更低 CPU 占用）
ros2 launch czybot_slam slam_toolbox_mapping.launch.py

# 方案三：Cartographer 3D（需更多 CPU，可选启用 IMU）
ros2 launch czybot_slam cartographer_3d_slam.launch.py use_imu:=true
```

> **水平安装说明**：启动文件默认不包含 pitch 旋转补偿，3 个 launch 文件中的四元数均为 `0.0, 0.0, 0.0, 1.0`。

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
| pointcloud_to_laserscan 连续帧输出相同时间戳，Cartographer 要求严格递增 | `scan_dedup.py`：支持限频、可选时间戳单调修复、统计 `dropped_fast/dropped_non_monotonic/fixed` |
| STM32 启动延迟导致 Cartographer 报 TF 异常 | TF 超时容忍 0.3s |
| 地面反射杂点和低位噪声进入扫描 | v9.0 默认切片 `0.15m~0.90m`，避开地面以下杂点并覆盖箱子/桌面高度 |
| 远距离稀疏点和反射点影响匹配 | 2D 建图 `range_max` 默认调为 `12.0m` |
| 雷达安装外参 | 静态 TF base_link→livox_frame 默认 `(0,0,0.15)` + q=`0,0,0,1`，支持 `lidar_*` launch 参数微调 |
| 轮式里程计 yaw 打滑误差固化进地图 | v9.0 将 `odometry_rotation_weight` / `odometry_translation_weight` 降为 `1e3`，子图帧数 `90→35`，优化频率 `70→20` |
| Ctrl-C 退出时 scan_dedup 报 `rcl_shutdown already called` | 增加 `if rclpy.ok(): rclpy.shutdown()` 保护 |

### 验证

```bash
# 检查 TF 树
ros2 run tf2_tools view_frames

# 检查 /map 发布频率
ros2 topic hz /map

# 查看地图数据
ros2 topic echo /map --once
```

## Nav2 导航（v10.0 实车联调）

`czybot_navigation2/launch/livox_navigation.launch.py` 是当前实车导航入口。它复用 SLAM 链路中的 Livox 点云处理流程，并把 Cartographer 替换为 `map_server + AMCL + Nav2`：STM32 负责 `/odom` 与 `odom→base_link`，AMCL 负责 `map→odom`，Nav2 输出 `/cmd_vel`，最后由 `stm32_bridge.py` 发送到底盘。

当前状态：导航链路已经接入并可进入 RViz 联调，但还没有完全成功；短距离目标、终点减速、局部代价地图误报和底盘响应仍需继续现场调参。

### 启动

```bash
cd ~/rdks100_slam/ros2_ws
source /opt/ros/humble/setup.bash
source install/setup.bash

ros2 launch czybot_navigation2 livox_navigation.launch.py \
    map:=/home/sunrise/rdks100_slam/my_map/map_20260625_162331.yaml \
    use_rviz:=true
```

`use_rviz` 在 launch 中默认是 `false`，因为 RK S100 板端同时运行 Livox/Nav2/RViz2 容易抢内存。现场为了看 `/map`、AMCL 位姿、`/scan_filtered`、`/plan`、local/global costmap，可以临时设为 `true`；稳定演示时建议在远程 PC 上开 RViz。

### 启动链路

```
stm32_bridge（/odom + odom→base_link + /cmd_vel）
  → base_link→livox_frame 静态 TF
  → livox_ros_driver2 (/livox/lidar)
  → pointcloud_to_laserscan (/scan)
  → scan_dedup (/scan_dedup)
  → scan_filter (/scan_filtered)
  → nav2_bringup (map_server + AMCL + planner/controller/bt_navigator)
  → RViz2（可选）
```

### 关键参数

| 模块 | 参数 | 当前值 |
|------|------|--------|
| MPPIController | `motion_model` | `Ackermann` |
| MPPIController | `vx_max / vx_min / wz_max / vy_max` | `0.15 / 0.0 / 0.50 / 0.0` |
| MPPIController | `AckermannConstraints.min_turning_r` | `0.30` |
| GoalChecker | `xy_goal_tolerance / yaw_goal_tolerance` | `0.20 / 3.14` |
| Planner | `planner_plugin` | `SmacPlanner2D` |
| Planner | `motion_model_for_search` | `MOORE` |
| Behaviors | `behavior_plugins` | `drive_on_heading / wait / assisted_teleop` |
| velocity_smoother | `max_velocity` | `[0.15, 0.0, 0.50]` |
| velocity_smoother | `deadband_velocity` | `[0.005, 0.0, 0.010]` |
| collision_monitor | `cmd_vel_out_topic` | `/cmd_vel_collision_monitor`（当前最小验证链路中旁路保留） |

### 验证

```bash
ros2 lifecycle get /bt_navigator
ros2 lifecycle get /planner_server
ros2 lifecycle get /controller_server
ros2 topic hz /cmd_vel
ros2 param get /controller_server FollowPath.motion_model
ros2 param get /controller_server FollowPath.vx_max
ros2 param get /controller_server FollowPath.wz_max
ros2 param get /planner_server GridBased.plugin
```

RViz 给目标点后，应能看到 `/plan` 发布并在 `/cmd_vel` 出现控制输出。当前目标是先保证 `linear.x >= 0`、角速度不超过 `0.50`、小车能按低速前进；到点抖动、短距离目标失败或 costmap 误报属于 v10.0 后续继续调试项。

## 机器人控制说明

### 控制方式

> **v9.0**：手动控制统一走 SafetyGate 安全门面，任何一层断开、失败或异常，下游都能独立停车。

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

### 控制安全参数（v9.0）

前端 → SafetyGate → ros2_bridge → stm32_bridge → STM32，多层安全链路逐级兜底：

| 层级 | 参数 | 值 | 说明 |
|------|------|----|------|
| **前端** | 最大线速度 / 最大角速度 | 0.60 m/s / 1.20 rad/s | 与后端、ROS2、STM32 对齐 |
| | 发送间隔 | 50 ms (20 Hz) | WebSocket 主通道，HTTP fallback |
| | 死区 | 0.005 / 0.010 | 低于阈值归零 |
| | 兜底事件 | visibilitychange / blur / mouseleave / pagehide / beforeunload / WS 断开 | 全部触发停车 |
| | 急停锁 | 300 ms | 防止急停后立即被旧速度拉起 |
| **后端 SafetyGate** | 最大线速度 / 最大角速度 | 0.60 m/s / 1.20 rad/s | 统一限速入口 |
| | 死区 | 0.005 / 0.010 | 统一归零入口 |
| | Watchdog | 400 ms | 超时自动发零速 |
| | 急停锁 | 500 ms | 急停期间拒绝非零速度 |
| **ros2_bridge** | 控制 Topic | `/cmd_vel` + `/cmd_vel_estop` | 急停 topic 与零速帧并行兜底 |
| **STM32桥接** | 最大线速度 / 最大角速度 | 0.60 m/s / 1.20 rad/s | 最后一层硬限幅 |
| | 死区 | 0.005 / 0.010 | ROS2 层归零 |
| | Watchdog / cmd 超时 | 500 ms / 300 ms | 上游异常时自动停车 |
| | 急停锁 | 400 ms | 消费 `/cmd_vel_estop` 后锁定停车 |
| **STM32** | 死区 | 0.02 / 0.03 | 下位机自身死区 |
| | CMD_TIMEOUT | 300 ms | 串口指令中断时自身停车 |

### 防抖链路

```
手动控制：前端 → SafetyGate → ros2_bridge → /cmd_vel → stm32_bridge → STM32
急停兜底：前端/后端 → /cmd_vel_estop + 多帧零速 → stm32_bridge 急停锁 → STM32
导航控制（v10.0 当前最小链路）：Nav2(SmacPlanner2D + MPPI Ackermann) → /cmd_vel → stm32_bridge → STM32
```

### 安全验证

- 按下 W 后松开 W：松开瞬间应发送零速。
- 按住 W 后切换标签页：`visibilitychange` 应触发停车。
- 按住 W 后鼠标移出窗口：`mouseleave` 应触发停车。
- 按住 W 后断开网络或杀掉后端：WS 断开应触发强急停。
- 按住 W 后关闭浏览器：`beforeunload` + `sendBeacon` 应触发强急停。
- 后端 watchdog：模拟 `safety_gate._last_cmd_time -= 1` 后，0.4s 内日志应出现自动零速。
- STM32 watchdog：串口 RX 断开约 0.5s 后，下位机自身 `CMD_TIMEOUT` 应停车。

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
ROS2_TOPIC_CMD_VEL_ESTOP = "/cmd_vel_estop"
ROS2_TOPIC_ODOM = "/odom"
ROS2_TOPIC_RGB_IMAGE: str = "/camera/camera/color/image_raw"              # RGB 图像（D435i 实际 topic）
ROS2_TOPIC_DEPTH_IMAGE: str = "/camera/camera/aligned_depth_to_color/image_raw"  # 对齐深度
ROS2_TOPIC_ANNOTATED_IMAGE: str = "/detection/annotated_image"   # YOLO 检测标注图（v6.0）
ROS2_TOPIC_VLM_DESCRIPTION: str = "/vlm/scene_description"       # VLM 场景描述（v12.0）
ROS2_TOPIC_VLM_STATUS: str = "/vlm/status"                       # VLM 节点状态（v12.0）
ROS2_SERVICE_VLM_ASK: str = "/vlm/ask"                           # VLM 手动触发服务（v12.0）
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
| `/cmd_vel_estop` | `geometry_msgs/Twist` | 急停兜底 Topic（v9.0，stm32_bridge 订阅） |
| `/battery_state` | `sensor_msgs/BatteryState` | 电池 |
| `/camera/camera/color/image_raw` | `sensor_msgs/Image` | RGB 图像（v6.0 D435i 真实接入，30Hz） |
| `/camera/camera/aligned_depth_to_color/image_raw` | `sensor_msgs/Image` | 对齐深度图像（v6.0 真实接入） |
| `/detection/results` | `std_msgs/String` | YOLOv5 检测结果 JSON（v6.0 新增） |
| `/detection/annotated_image` | `sensor_msgs/Image` | 检测标注图像 BGR8（v6.0，后端→WebSocket） |
| `/vlm/scene_description` | `std_msgs/String` | VLM 场景理解结果 JSON（v12.0 新增） |
| `/vlm/status` | `std_msgs/String` | VLM provider、ready、耗时、错误等状态（v12.0 新增） |

发布 Topic：

| Topic | 消息类型 | 说明 |
|-------|---------|------|
| `/cmd_vel` | `geometry_msgs/Twist` | 速度控制（由 STM32 桥接节点消费） |
| `/cmd_vel_estop` | `geometry_msgs/Twist` | 急停兜底（后端 SafetyGate/ros2_bridge 发布） |
| `/goal_pose` | `geometry_msgs/PoseStamped` | 导航目标 |

服务：

| Service | 类型 | 说明 |
|---------|------|------|
| `/vlm/ask` | `std_srvs/srv/Trigger` | 手动触发一次 VLM 场景分析（v12.0 新增） |

### STM32 桥接节点（`czybot_navigation2`）

`stm32_bridge.py` 是连接 ROS2 与底盘 STM32 的核心节点：

- 订阅 `/cmd_vel`，将 Twist 消息转换为 STM32 串口协议帧发送
- 订阅 `/cmd_vel_estop`，收到急停后进入急停锁并主动发送停车帧
- 接收 STM32 上报的里程计数据，发布到 `/odom`
- 内置硬限幅：线速度不超过 `0.60 m/s`，角速度不超过 `1.20 rad/s`
- 内置死区滤波和 watchdog：ROS2 层死区 `0.005 / 0.010`，无新指令约 300ms 自动停车

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

支持的 Topic：`system`, `robot_status`, `lidar`, `imu`, `slam_map`, `video_rgb`, `video_depth`, `video_annotated`, `detection_results`, `vlm_description`, `vlm_status`, `navigation`, `log`, `heartbeat`, `odom`

> **v6.0 视频推送**：
> - `video_rgb`：纯 RGB 原图，自动选择最佳数据源（ros2 → mock），前端通过 `source` 字段区分
> - `video_annotated`：AI 检测标注图（带绿框+距离），仅检测节点在线时推送
> - `detection_results`：YOLO 检测结果 JSON，10Hz 推送
>
> **v12.0 VLM 推送**：
> - `vlm_status`：VLM 节点 ready/provider/last_error/elapsed_ms 等状态，默认自动订阅
> - `vlm_description`：场景自然语言描述，前端视频监控页按需订阅并保存最近历史

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
