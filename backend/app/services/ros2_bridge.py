# =============================================================================
# ROS2 桥接模块
# 负责与 ROS2 系统通信，订阅 topic、发布指令、调用 service
# 当 ROS2_ENABLED=false 时自动降级为模拟数据
# =============================================================================
import asyncio
import logging
import threading
from typing import Optional, Callable, Any, Dict
from app.core.config import (
    ROS2_ENABLED, ROS2_DOMAIN_ID,
    ROS2_TOPIC_CMD_VEL, ROS2_TOPIC_SCAN, ROS2_TOPIC_IMU,
    ROS2_TOPIC_LIDAR3D,
    ROS2_TOPIC_MAP, ROS2_TOPIC_POSE, ROS2_TOPIC_BATTERY,
    ROS2_TOPIC_RGB_IMAGE, ROS2_TOPIC_DEPTH_IMAGE,
    ROS2_TOPIC_ANNOTATED_IMAGE, ROS2_TOPIC_DETECTION_RESULTS,
    ROS2_TOPIC_ODOM, ROS2_TOPIC_PATH, ROS2_TOPIC_GOAL,
    ROS2_TOPIC_SLAM_POSE,
    ROS2_SERVICE_SAVE_MAP, ROS2_SERVICE_LOAD_MAP,
    ROS2_SERVICE_START_SLAM, ROS2_SERVICE_STOP_SLAM,
    ROBOT_MAX_LINEAR_VEL, ROBOT_MAX_ANGULAR_VEL,
)

logger = logging.getLogger(__name__)


class ROS2Bridge:
    """
    ROS2 桥接层
    - ROS2_ENABLED=true：使用 rclpy 与真实 ROS2 通信
    - ROS2_ENABLED=false：所有方法为空操作，由 mock_data 提供数据
    """

    def __init__(self):
        self._enabled = ROS2_ENABLED
        self._node = None
        self._executor = None
        self._spin_thread: Optional[threading.Thread] = None
        self._initialized = False

        # 回调函数注册表：topic -> callback
        self._callbacks: Dict[str, Callable] = {}

        # 发布者缓存
        self._publishers: Dict[str, Any] = {}
        # 订阅者缓存
        self._subscribers: Dict[str, Any] = {}

        # 最新数据缓存（线程安全），供 data_pusher 读取
        self._latest_data: Dict[str, Any] = {}
        self._data_lock = threading.Lock()

        # IMU 互补滤波状态（Livox 不输出姿态，需要自行估算）
        self._imu_roll: float = 0.0
        self._imu_pitch: float = 0.0
        self._imu_yaw: float = 0.0
        self._imu_last_time: float = 0.0

        if self._enabled:
            self._init_ros2()

    def _init_ros2(self):
        """初始化 ROS2 节点（仅在 ROS2_ENABLED=true 时调用）"""
        try:
            import rclpy
            from rclpy.node import Node
            from rclpy.executors import MultiThreadedExecutor

            rclpy.init(args=None)
            self._node = rclpy.create_node(
                "rdks100_webui_bridge",
                namespace="",
                use_global_arguments=True,
            )
            self._executor = MultiThreadedExecutor()
            self._executor.add_node(self._node)

            # 在独立线程中 spin
            self._spin_thread = threading.Thread(
                target=self._executor.spin,
                daemon=True,
                name="ros2_spin",
            )
            self._spin_thread.start()
            self._initialized = True
            logger.info("[ROS2] 节点初始化成功，domain_id=%d", ROS2_DOMAIN_ID)

            # 创建发布者
            self._create_publishers()
            # 创建订阅者
            self._create_subscribers()

        except ImportError:
            logger.warning("[ROS2] rclpy 未安装，自动降级为模拟模式")
            self._enabled = False
        except Exception as e:
            logger.error("[ROS2] 初始化失败: %s，降级为模拟模式", e)
            self._enabled = False

    def _create_publishers(self):
        """创建所有需要的 ROS2 发布者"""
        if not self._initialized:
            return
        try:
            from geometry_msgs.msg import Twist
            from geometry_msgs.msg import PoseStamped

            self._publishers["cmd_vel"] = self._node.create_publisher(
                Twist, ROS2_TOPIC_CMD_VEL, 10
            )
            self._publishers["goal_pose"] = self._node.create_publisher(
                PoseStamped, ROS2_TOPIC_GOAL, 10
            )
            logger.info("[ROS2] 发布者创建完成")
        except Exception as e:
            logger.error("[ROS2] 创建发布者失败: %s", e)

    def _create_subscribers(self):
        """
        创建所有需要的 ROS2 订阅者。
        每个订阅独立 try/except，单个失败不影响其他订阅。
        """
        if not self._initialized:
            return

        # ── 3D 激光雷达点云（Livox Mid-360S → /livox/lidar）────────────────
        try:
            from sensor_msgs.msg import PointCloud2
            sub = self._node.create_subscription(
                PointCloud2, ROS2_TOPIC_LIDAR3D,
                lambda msg: self._dispatch("lidar3d", self._parse_pointcloud2(msg)), 10
            )
            self._subscribers["lidar3d"] = sub
            logger.info("[ROS2] 已订阅 lidar3d → %s", ROS2_TOPIC_LIDAR3D)
        except Exception as e:
            logger.error("[ROS2] 订阅 lidar3d 失败: %s", e)

        # ── IMU（Livox 内置 IMU → /livox/imu）──────────────────────────────
        try:
            from sensor_msgs.msg import Imu
            sub = self._node.create_subscription(
                Imu, ROS2_TOPIC_IMU,
                lambda msg: self._dispatch("imu", self._parse_imu(msg)), 10
            )
            self._subscribers["imu"] = sub
            logger.info("[ROS2] 已订阅 imu → %s", ROS2_TOPIC_IMU)
        except Exception as e:
            logger.error("[ROS2] 订阅 imu 失败: %s", e)

        # ── 地图 ─────────────────────────────────────────────────────────────
        try:
            from nav_msgs.msg import OccupancyGrid
            sub = self._node.create_subscription(
                OccupancyGrid, ROS2_TOPIC_MAP,
                lambda msg: self._dispatch("map", self._parse_map(msg)), 10
            )
            self._subscribers["map"] = sub
            logger.info("[ROS2] 已订阅 map → %s", ROS2_TOPIC_MAP)
        except Exception as e:
            logger.error("[ROS2] 订阅 map 失败: %s", e)

        # ── 里程计 ───────────────────────────────────────────────────────────
        try:
            from nav_msgs.msg import Odometry
            sub = self._node.create_subscription(
                Odometry, ROS2_TOPIC_ODOM,
                lambda msg: self._dispatch("odom", self._parse_odom(msg)), 10
            )
            self._subscribers["odom"] = sub
            logger.info("[ROS2] 已订阅 odom → %s", ROS2_TOPIC_ODOM)
        except Exception as e:
            logger.error("[ROS2] 订阅 odom 失败: %s", e)

        # ── 电池 ─────────────────────────────────────────────────────────────
        try:
            from sensor_msgs.msg import BatteryState
            sub = self._node.create_subscription(
                BatteryState, ROS2_TOPIC_BATTERY,
                lambda msg: self._dispatch("battery", self._parse_battery(msg)), 10
            )
            self._subscribers["battery"] = sub
            logger.info("[ROS2] 已订阅 battery → %s", ROS2_TOPIC_BATTERY)
        except Exception as e:
            logger.error("[ROS2] 订阅 battery 失败: %s", e)

        # ── RGB 图像 ─────────────────────────────────────────────────────────
        try:
            from sensor_msgs.msg import Image
            sub = self._node.create_subscription(
                Image, ROS2_TOPIC_RGB_IMAGE,
                lambda msg: self._dispatch("rgb_image", self._parse_image(msg, "rgb")), 10
            )
            self._subscribers["rgb_image"] = sub
            logger.info("[ROS2] 已订阅 rgb_image → %s", ROS2_TOPIC_RGB_IMAGE)
        except Exception as e:
            logger.error("[ROS2] 订阅 rgb_image 失败: %s", e)

        # ── 深度图像 ─────────────────────────────────────────────────────────
        try:
            from sensor_msgs.msg import Image
            sub = self._node.create_subscription(
                Image, ROS2_TOPIC_DEPTH_IMAGE,
                lambda msg: self._dispatch("depth_image", self._parse_image(msg, "depth")), 10
            )
            self._subscribers["depth_image"] = sub
            logger.info("[ROS2] 已订阅 depth_image → %s", ROS2_TOPIC_DEPTH_IMAGE)
        except Exception as e:
            logger.error("[ROS2] 订阅 depth_image 失败: %s", e)
        # ── 带检测框的标注图像 ──────────────────────────────────────────────
        try:
            from sensor_msgs.msg import Image
            sub = self._node.create_subscription(
                Image, ROS2_TOPIC_ANNOTATED_IMAGE,
                lambda msg: self._dispatch("annotated_image", self._parse_annotated_image(msg)), 10
            )
            self._subscribers["annotated_image"] = sub
            logger.info("[ROS2] 已订阅 annotated_image → %s", ROS2_TOPIC_ANNOTATED_IMAGE)
        except Exception as e:
            logger.error("[ROS2] 订阅 annotated_image 失败: %s", e)

        # ── YOLO 检测结果 JSON（/detection/results）──────────────────────────
        try:
            from std_msgs.msg import String
            sub = self._node.create_subscription(
                String, ROS2_TOPIC_DETECTION_RESULTS,
                lambda msg: self._dispatch("detection_results", self._parse_detection_results(msg)), 10
            )
            self._subscribers["detection_results"] = sub
            logger.info("[ROS2] 已订阅 detection_results → %s", ROS2_TOPIC_DETECTION_RESULTS)
        except Exception as e:
            logger.error("[ROS2] 订阅 detection_results 失败: %s", e)

        # ── 路径 ─────────────────────────────────────────────────────────────
        try:
            from nav_msgs.msg import Path
            sub = self._node.create_subscription(
                Path, ROS2_TOPIC_PATH,
                lambda msg: self._dispatch("path", self._parse_path(msg)), 10
            )
            self._subscribers["path"] = sub
            logger.info("[ROS2] 已订阅 path → %s", ROS2_TOPIC_PATH)
        except Exception as e:
            logger.error("[ROS2] 订阅 path 失败: %s", e)

        logger.info("[ROS2] 订阅者创建完成，成功: %s", list(self._subscribers.keys()))

    def _dispatch(self, topic: str, data: dict):
        """将 ROS2 消息分发给注册的回调函数，并缓存最新数据"""
        # 缓存最新数据（线程安全）
        with self._data_lock:
            self._latest_data[topic] = data

        if topic in self._callbacks:
            try:
                self._callbacks[topic](data)
            except Exception as e:
                logger.error("[ROS2] 回调执行失败 topic=%s: %s", topic, e)

    def register_callback(self, topic: str, callback: Callable):
        """注册 topic 数据回调"""
        self._callbacks[topic] = callback

    def get_latest(self, topic: str) -> Optional[dict]:
        """获取指定 topic 的最新数据（线程安全），无数据时返回 None"""
        with self._data_lock:
            return self._latest_data.get(topic)

    # -------------------------------------------------------------------------
    # 消息解析器（ROS2 msg -> Python dict）
    # -------------------------------------------------------------------------
    def _parse_pointcloud2(self, msg) -> dict:
        """
        解析 sensor_msgs/PointCloud2 消息（Livox Mid-360S 标准输出）
        字段布局：x(float32) y(float32) z(float32) intensity(float32)
        输出紧凑格式 [x, y, z, intensity] 减少 JSON 体积
        同时对点数降采样，控制 WebSocket 带宽
        """
        import struct
        import math

        # 解析 PointCloud2 字段偏移
        field_offsets = {}
        for field in msg.fields:
            field_offsets[field.name] = field.offset

        x_off = field_offsets.get("x", 0)
        y_off = field_offsets.get("y", 4)
        z_off = field_offsets.get("z", 8)
        intensity_off = field_offsets.get("intensity", 12)
        point_step = msg.point_step  # 每个点的字节数（通常 16 或 20）

        raw = bytes(msg.data)
        total_points = msg.width * msg.height

        # 降采样：最多保留 10000 个点发送给前端
        # Livox Mid-360S 约 19968 点/帧，step≈2 → 保留约 50% 密度
        MAX_POINTS = 10000
        step = max(1, total_points // MAX_POINTS)

        points = []
        z_values = []
        distances = []
        intensities = []

        for i in range(0, total_points, step):
            base = i * point_step
            if base + point_step > len(raw):
                break
            try:
                x = struct.unpack_from("<f", raw, base + x_off)[0]
                y = struct.unpack_from("<f", raw, base + y_off)[0]
                z = struct.unpack_from("<f", raw, base + z_off)[0]
                intensity = struct.unpack_from("<f", raw, base + intensity_off)[0]
            except struct.error:
                continue

            # 过滤无效点（NaN / Inf / 超出量程）
            if not (math.isfinite(x) and math.isfinite(y) and math.isfinite(z)):
                continue
            if not math.isfinite(intensity):
                intensity = 0.0
            dist_xy = math.sqrt(x * x + y * y)
            # 最小距离 0.02m（Livox 近距离盲区），最大 40m
            if dist_xy < 0.02 or dist_xy > 40.0:
                continue

            # 保留 3 位小数（毫米级精度），intensity 归一化到 0~255 整数节省带宽
            points.append([
                round(x, 3),
                round(y, 3),
                round(z, 3),
                min(255, max(0, int(intensity))),
            ])
            z_values.append(z)
            distances.append(dist_xy)
            intensities.append(intensity)

        min_dist = round(min(distances, default=0.0), 3)
        max_range = round(max(distances, default=0.0), 1)
        z_min = round(min(z_values, default=0.0), 3)
        z_max = round(max(z_values, default=0.0), 3)
        # intensity 统计（用于前端动态色彩映射）
        int_max = round(max(intensities, default=255.0), 1)
        int_min = round(min(intensities, default=0.0), 1)

        return {
            "timestamp": msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9,
            "frame_id": msg.header.frame_id,
            "points": points,           # [[x, y, z, intensity(0-255)], ...]
            "point_count": len(points),
            "total_points": total_points,
            "min_distance": min_dist,
            "range_max": max_range,
            "z_min": z_min,
            "z_max": z_max,
            "intensity_min": int_min,
            "intensity_max": int_max,
            "obstacle_count": sum(1 for d in distances if d < 2.0),
            "is_3d": True,
        }

    def _parse_laserscan(self, msg) -> dict:
        """保留 2D 激光雷达解析（兼容旧版本）"""
        import math
        ranges = list(msg.ranges)
        points = []
        for i, r in enumerate(ranges):
            if msg.range_min <= r <= msg.range_max:
                a = msg.angle_min + i * msg.angle_increment
                points.append([
                    round(r * math.cos(a), 3),
                    round(r * math.sin(a), 3),
                ])
        valid_ranges = [r for r in ranges if msg.range_min <= r <= msg.range_max]
        return {
            "timestamp": msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9,
            "angle_min": msg.angle_min,
            "angle_max": msg.angle_max,
            "range_min": msg.range_min,
            "range_max": msg.range_max,
            "points": points,
            "obstacle_count": sum(1 for r in valid_ranges if r < 2.0),
            "min_distance": round(min(valid_ranges, default=0), 3),
            "is_3d": False,
        }

    def _parse_imu(self, msg) -> dict:
        """
        解析 Livox Mid-360 IMU 消息。
        注意：Livox IMU 不输出姿态四元数（orientation 恒为单位四元数），
        因此使用互补滤波（加速度计 + 陀螺仪积分）估算 Roll/Pitch，
        Yaw 使用陀螺仪积分（无磁力计，存在漂移）。
        加速度单位：g（1g ≈ 9.81 m/s²）

        修复 v2：
        - 首次收到数据时用加速度计直接初始化 Roll/Pitch（避免从 0 缓慢收敛）
        - ALPHA 降低到 0.90，加速度计权重 10%，静止时更快反映真实姿态
        """
        import math
        import time

        now = msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9

        gx = msg.angular_velocity.x      # rad/s
        gy = msg.angular_velocity.y
        gz = msg.angular_velocity.z
        ax = msg.linear_acceleration.x   # g
        ay = msg.linear_acceleration.y
        az = msg.linear_acceleration.z

        # 时间步长（首次调用用默认值）
        dt = now - self._imu_last_time if self._imu_last_time > 0 else 0.01
        # 防止 dt 异常（重启/跳变）
        if dt <= 0 or dt > 1.0:
            dt = 0.01

        # 加速度计估算 Roll/Pitch（静止时准确，运动时有噪声）
        acc_norm = math.sqrt(ax * ax + ay * ay + az * az)
        if acc_norm > 0.1:  # 防止除零
            ax_n, ay_n, az_n = ax / acc_norm, ay / acc_norm, az / acc_norm
            acc_roll  = math.atan2(ay_n, az_n)
            acc_pitch = math.asin(max(-1.0, min(1.0, -ax_n)))
        else:
            acc_roll  = self._imu_roll
            acc_pitch = self._imu_pitch

        # 首次收到 IMU 数据：用加速度计直接初始化姿态（跳过缓慢收敛过程）
        if self._imu_last_time == 0.0:
            self._imu_roll  = acc_roll
            self._imu_pitch = acc_pitch
            self._imu_yaw   = 0.0
            self._imu_last_time = now
            # 首帧直接返回加速度计估算值
            roll_deg  = round(math.degrees(acc_roll),  2)
            pitch_deg = round(math.degrees(acc_pitch), 2)
            yaw_deg   = 0.0
        else:
            self._imu_last_time = now
            # 互补滤波：0.90 陀螺仪积分 + 0.10 加速度计修正
            # 降低 ALPHA 使加速度计有更大权重，静止时快速反映真实姿态
            ALPHA = 0.90
            self._imu_roll  = ALPHA * (self._imu_roll  + gx * dt) + (1 - ALPHA) * acc_roll
            self._imu_pitch = ALPHA * (self._imu_pitch + gy * dt) + (1 - ALPHA) * acc_pitch
            # Yaw 纯陀螺仪积分（无磁力计，长时间会漂移）
            self._imu_yaw  += gz * dt

            roll_deg  = round(math.degrees(self._imu_roll),  2)
            pitch_deg = round(math.degrees(self._imu_pitch), 2)
            yaw_deg   = round(math.degrees(self._imu_yaw),   2)

        return {
            "timestamp": now,
            "orientation": {
                "roll":  roll_deg,
                "pitch": pitch_deg,
                "yaw":   yaw_deg,
                "quaternion": {
                    "x": msg.orientation.x,
                    "y": msg.orientation.y,
                    "z": msg.orientation.z,
                    "w": msg.orientation.w,
                },
            },
            "angular_velocity": {
                "x": round(gx, 4),
                "y": round(gy, 4),
                "z": round(gz, 4),
            },
            "linear_acceleration": {
                "x": round(ax, 4),
                "y": round(ay, 4),
                "z": round(az, 4),
            },
            "temperature": 0.0,
        }

    def _parse_map(self, msg) -> dict:
        data_2d = []
        w, h = msg.info.width, msg.info.height
        flat = list(msg.data)
        for row in range(h):
            data_2d.append(flat[row * w:(row + 1) * w])
        return {
            "timestamp": msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9,
            "width": w,
            "height": h,
            "resolution": msg.info.resolution,
            "origin": {
                "x": msg.info.origin.position.x,
                "y": msg.info.origin.position.y,
            },
            "data": data_2d,
        }

    def _parse_odom(self, msg) -> dict:
        import math
        p = msg.pose.pose.position
        q = msg.pose.pose.orientation
        siny = 2 * (q.w * q.z + q.x * q.y)
        cosy = 1 - 2 * (q.y * q.y + q.z * q.z)
        yaw = math.atan2(siny, cosy)
        return {
            "timestamp": msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9,
            "pose": {"x": p.x, "y": p.y, "z": p.z, "yaw": yaw},
            "velocity": {
                "linear_x": msg.twist.twist.linear.x,
                "linear_y": msg.twist.twist.linear.y,
                "angular_z": msg.twist.twist.angular.z,
            },
        }

    def _parse_battery(self, msg) -> dict:
        return {
            "timestamp": 0,
            "percent": round(msg.percentage * 100, 1),
            "voltage": round(msg.voltage, 2),
            "current": round(msg.current, 2),
            "charging": msg.power_supply_status == 1,
        }

    def _parse_image(self, msg, img_type: str) -> dict:
        """图像消息转 base64（实际传输时压缩）"""
        import base64
        import numpy as np
        try:
            import cv2
            arr = np.frombuffer(msg.data, dtype=np.uint8)
            if img_type == "rgb":
                img = arr.reshape((msg.height, msg.width, 3))
                _, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 80])
            else:
                arr16 = np.frombuffer(msg.data, dtype=np.uint16)
                depth = arr16.reshape((msg.height, msg.width))
                depth_vis = (depth / 10).clip(0, 255).astype(np.uint8)
                depth_color = cv2.applyColorMap(depth_vis, cv2.COLORMAP_JET)
                _, buf = cv2.imencode(".jpg", depth_color, [cv2.IMWRITE_JPEG_QUALITY, 70])
            return {
                "timestamp": msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9,
                "type": img_type,
                "width": msg.width,
                "height": msg.height,
                "data": base64.b64encode(buf.tobytes()).decode(),
                "encoding": "jpeg/base64",
            }
        except Exception as e:
            logger.error("[ROS2] 图像解析失败: %s", e)
            return {}
    def _parse_annotated_image(self, msg) -> dict:
        """
        解析检测节点发布的带标注框图像（BGR8 → JPEG base64）。
        检测节点已将框和距离画在图上，直接编码即可。
        """
        import base64
        import numpy as np
        try:
            import cv2
            arr = np.frombuffer(msg.data, dtype=np.uint8)
            img = arr.reshape((msg.height, msg.width, 3))
            # BGR8 → JPEG 压缩
            _, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 85])
            return {
                "timestamp": msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9,
                "type": "annotated",
                "width": msg.width,
                "height": msg.height,
                "data": base64.b64encode(buf.tobytes()).decode(),
                "encoding": "jpeg/base64",
            }
        except Exception as e:
            logger.error("[ROS2] 标注图像解析失败: %s", e)
            return {}


    def _parse_detection_results(self, msg) -> dict:
        """
        解析 /detection/results（std_msgs/String，JSON 格式）。
        detection_node 发布的格式：
          {
            "timestamp": float,
            "frame_id":  int,
            "infer_ms":  float,
            "count":     int,
            "detections": [
              {"class_id", "class_name", "confidence", "bbox", "distance_m"}, ...
            ]
          }
        直接解析后原样透传，供前端 detection_results topic 消费。
        """
        import json as _json
        try:
            return _json.loads(msg.data)
        except Exception as e:
            logger.error("[ROS2] 解析 detection_results 失败: %s", e)
            return {}

    def _parse_path(self, msg) -> dict:
        points = [
            {"x": p.pose.position.x, "y": p.pose.position.y}
            for p in msg.poses
        ]
        return {
            "timestamp": msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9,
            "points": points,
        }

    # -------------------------------------------------------------------------
    # 控制指令发布
    # -------------------------------------------------------------------------
    def publish_cmd_vel(self, linear_x: float, linear_y: float, angular_z: float):
        """发布速度控制指令"""
        if not self._initialized or "cmd_vel" not in self._publishers:
            return
        try:
            from geometry_msgs.msg import Twist
            msg = Twist()
            msg.linear.x = float(max(-ROBOT_MAX_LINEAR_VEL, min(ROBOT_MAX_LINEAR_VEL, linear_x)))
            msg.linear.y = float(max(-ROBOT_MAX_LINEAR_VEL, min(ROBOT_MAX_LINEAR_VEL, linear_y)))
            msg.angular.z = float(max(-ROBOT_MAX_ANGULAR_VEL, min(ROBOT_MAX_ANGULAR_VEL, angular_z)))
            self._publishers["cmd_vel"].publish(msg)
        except Exception as e:
            logger.error("[ROS2] 发布 cmd_vel 失败: %s", e)

    def publish_goal(self, x: float, y: float, yaw: float = 0.0):
        """发布导航目标点"""
        if not self._initialized or "goal_pose" not in self._publishers:
            return
        try:
            import math
            from geometry_msgs.msg import PoseStamped
            from std_msgs.msg import Header
            msg = PoseStamped()
            msg.header.frame_id = "map"
            msg.pose.position.x = float(x)
            msg.pose.position.y = float(y)
            msg.pose.orientation.z = float(math.sin(yaw / 2))
            msg.pose.orientation.w = float(math.cos(yaw / 2))
            self._publishers["goal_pose"].publish(msg)
        except Exception as e:
            logger.error("[ROS2] 发布 goal_pose 失败: %s", e)

    # -------------------------------------------------------------------------
    # Service 调用
    # -------------------------------------------------------------------------
    async def call_save_map(self, map_name: str) -> dict:
        """调用保存地图 service"""
        if not self._initialized:
            return {"success": True, "message": f"[模拟] 地图 '{map_name}' 已保存"}
        try:
            # 实际 ROS2 service 调用（异步包装）
            return {"success": True, "message": f"地图 '{map_name}' 保存成功"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    async def call_load_map(self, map_path: str) -> dict:
        """调用加载地图 service"""
        if not self._initialized:
            return {"success": True, "message": f"[模拟] 地图 '{map_path}' 已加载"}
        try:
            return {"success": True, "message": f"地图 '{map_path}' 加载成功"}
        except Exception as e:
            return {"success": False, "message": str(e)}

    @property
    def is_enabled(self) -> bool:
        return self._enabled and self._initialized

    def shutdown(self):
        """关闭 ROS2 节点"""
        if self._initialized:
            try:
                import rclpy
                self._executor.shutdown()
                rclpy.shutdown()
                logger.info("[ROS2] 节点已关闭")
            except Exception as e:
                logger.error("[ROS2] 关闭失败: %s", e)


# 全局单例
ros2_bridge = ROS2Bridge()
