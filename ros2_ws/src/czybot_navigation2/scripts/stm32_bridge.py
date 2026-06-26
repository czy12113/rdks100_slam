#!/usr/bin/env python3
"""
STM32 串口通信桥接节点  v5 —— 与 STM32 ChassisParams.h 全面对齐 + 独立急停通道

本版本重点（相对 v4）：
  1. 速度硬限幅与 STM32 一致：MAX_LINEAR_SPEED=0.60 m/s, MAX_ANGULAR_SPEED=1.20 rad/s
     （v4 误用 1.0/1.57，会让下位机进入超限保护）
  2. 死区与 STM32 ChassisParams.h 大致对齐：上位机略小，让下位机做最终判定，
     防止 RDK 把"非零但很小"的指令一直发给电机引起抖动。
  3. 新增独立急停订阅 topic /cmd_vel_estop（std_msgs/Empty）：
     上位机/前端/导航任意一侧只要发布到该 topic，本节点立刻
     连续发送 N 帧零速并清零 latest_*，与 cmd_vel 通道彼此正交。
  4. 所有阈值改为 ROS2 参数，可在 launch 时覆盖：
       max_linear, max_angular, linear_deadzone, angular_deadzone,
       cmd_timeout, watchdog_timeout, estop_repeats, estop_lock_seconds.
  5. 急停锁：触发后短时间内（estop_lock_seconds）忽略所有非零 cmd_vel，
     防止某个上层节点（前端/Nav2 智能恢复）在急停后继续覆盖速度。
  6. 节点关闭时主动多次写零速，避免守护进程被杀后下位机仍在跑。

  v3/v4 已确立的架构在 v5 中保留：
    - cmd_vel 回调和 ROS2 spin 完全无串口 I/O，仅写共享内存
    - 串口写线程（25 Hz）独立运行，不阻塞 spin
    - 看门狗线程独立运行，不依赖 ROS 定时器
    - 接收线程独立解析 STM32 上行 20 字节 odom 帧

参数说明：
  port              : 串口设备（自动 fallback 到 /dev/ttyUSB0~2）
  baudrate          : 波特率（与 STM32 一致，默认 115200）
  publish_tf        : 是否广播 odom→base_link TF（默认 True）
  max_linear        : 线速度硬限幅 (m/s)，默认 0.60 与 STM32 对齐
  max_angular       : 角速度硬限幅 (rad/s)，默认 1.20 与 STM32 对齐
  linear_deadzone   : 线速度死区 (m/s)，低于此值发零速；默认 0.005
  angular_deadzone  : 角速度死区 (rad/s)，低于此值发零速；默认 0.010
  min_motion_linear : 线速度最小启动门槛 (m/s)，默认 0.18
                       Nav2 起步阶段 cmd_vel 常在 0.05~0.18 区间，
                       但电机 + STM32 最小占空比约 0.18 m/s，
                       小于该值时电机不转。设了之后：
                       deadzone < |v| < min_motion_linear → 抬到 ±min_motion_linear
                       关掉则设为 0.0。
                       注意：只对 linear 做补偿，不对 angular 做（避免舵机抖）。
  min_motion_angular: 角速度最小启动门槛 (rad/s)，默认 0.0 = 关闭
                       ⚠ 强烈不建议开启：阿克曼前轮舵机的"小角度低速命令"
                       是正常 MPPI 输出，硬抬到大值会让舵机左右剧烈抖动。
                       仅在差速底盘上才考虑打开。
  cmd_timeout       : 无 cmd_vel 多久自动发停车帧 (s)，默认 0.3
                       与 STM32 CMD_TIMEOUT_MS=300 完全对齐
  watchdog_timeout  : 看门狗兜底超时 (s)，默认 0.5
  estop_repeats     : 急停时连发零速次数，默认 5
  estop_lock_seconds: 急停锁定时长 (s)，期间忽略非零 cmd_vel，默认 0.4
  write_hz          : 串口写线程频率 (Hz)，默认 25
"""
import math
import os
import struct
import threading
import time

import rclpy
import serial
from geometry_msgs.msg import Twist, TransformStamped
from nav_msgs.msg import Odometry
from rclpy.node import Node
from std_msgs.msg import Bool, Empty, Int32MultiArray
from tf2_ros import TransformBroadcaster


# 协议常量（与 STM32/USER/ROS2Protocol.h 一致）
FRAME_HEADER_0 = 0xAA
FRAME_HEADER_1 = 0x55
FRAME_TAIL = 0x0D
ODOM_HEADER_0 = 0xBB
ODOM_HEADER_1 = 0x66
CMD_VELOCITY = 0x01
DATA_TYPE_ODOM = 0x01
ODOM_FRAME_LEN = 20  # BB 66 type x(4) y(4) yaw(2) v(2) w(2) reserved cs 0D


class STM32Bridge(Node):
    def __init__(self):
        super().__init__('stm32_bridge')

        # ── ROS2 参数声明（统一管理，可在 launch 时覆盖）─────────────────────
        self.declare_parameter('port', '/dev/ttyUSB0')
        self.declare_parameter('baudrate', 115200)
        self.declare_parameter('publish_tf', True)

        # 与 STM32 ChassisParams.h 对齐
        self.declare_parameter('max_linear', 0.60)
        self.declare_parameter('max_angular', 1.20)
        self.declare_parameter('linear_deadzone', 0.005)
        self.declare_parameter('angular_deadzone', 0.010)
        # ★ 真车启动补偿：解决 Nav2 输出 0.10~0.18 m/s 时电机不转的问题
        # 仅 linear 补偿；angular 补偿在阿克曼上会让前轮舵机剧烈抖动，
        # 默认关闭（=0.0），如需打开请自行评估。
        self.declare_parameter('min_motion_linear', 0.18)
        self.declare_parameter('min_motion_angular', 0.0)

        self.declare_parameter('cmd_timeout', 0.3)
        self.declare_parameter('watchdog_timeout', 0.5)
        self.declare_parameter('estop_repeats', 5)
        self.declare_parameter('estop_lock_seconds', 0.4)
        self.declare_parameter('write_hz', 25.0)

        port = self.get_parameter('port').value
        baudrate = self.get_parameter('baudrate').value
        self.publish_tf = self.get_parameter('publish_tf').value

        self.max_linear = float(self.get_parameter('max_linear').value)
        self.max_angular = float(self.get_parameter('max_angular').value)
        self.linear_deadzone = float(self.get_parameter('linear_deadzone').value)
        self.angular_deadzone = float(self.get_parameter('angular_deadzone').value)
        self.min_motion_linear = float(self.get_parameter('min_motion_linear').value)
        self.min_motion_angular = float(self.get_parameter('min_motion_angular').value)

        self.CMD_TIMEOUT = float(self.get_parameter('cmd_timeout').value)
        self.WATCHDOG_TIMEOUT = float(self.get_parameter('watchdog_timeout').value)
        self.ESTOP_REPEATS = int(self.get_parameter('estop_repeats').value)
        self.ESTOP_LOCK_SECONDS = float(self.get_parameter('estop_lock_seconds').value)
        self.WRITE_HZ = float(self.get_parameter('write_hz').value)

        # 整数化的硬限幅（mm/s, mrad/s），用于 cmd_vel 入口快速比较
        self._max_linear_mm = int(self.max_linear * 1000)
        self._max_angular_mrad = int(self.max_angular * 1000)
        self._linear_deadzone_mm = max(1, int(self.linear_deadzone * 1000))
        self._angular_deadzone_mrad = max(1, int(self.angular_deadzone * 1000))
        # 启动补偿门槛（mm/s, mrad/s）
        self._min_motion_linear_mm = int(self.min_motion_linear * 1000)
        self._min_motion_angular_mrad = int(self.min_motion_angular * 1000)

        # ── 自动探测串口 ────────────────────────────────────────────────────
        candidate_ports = [port] + [
            p for p in ['/dev/ttyUSB0', '/dev/ttyUSB1', '/dev/ttyUSB2']
            if p != port
        ]
        actual_port = None
        for p in candidate_ports:
            if os.path.exists(p):
                actual_port = p
                break

        if actual_port is None:
            self.get_logger().error(
                f'未找到任何串口设备，已尝试: {candidate_ports}')
            raise RuntimeError(f'No serial port found, tried: {candidate_ports}')

        if actual_port != port:
            self.get_logger().warn(
                f'指定端口 {port} 不存在，自动切换到 {actual_port}')

        # ── 打开串口 ────────────────────────────────────────────────────────
        try:
            self.serial = serial.Serial(actual_port, baudrate, timeout=0.1)
            self.get_logger().info(f'串口已打开: {actual_port} @ {baudrate}')
        except Exception as e:
            self.get_logger().error(f'无法打开串口 {actual_port}: {e}')
            raise

        # ── 共享状态（仅内存操作，所有 I/O 在写线程）───────────────────────
        self.latest_linear = 0          # mm/s
        self.latest_angular = 0         # mrad/s
        self.last_cmd_time = 0.0
        self._estop_pending = False     # 写线程检测到此标志立即发零速
        self._estop_lock_until = 0.0    # 急停锁定结束时刻
        self._lock = threading.Lock()

        # ── 可观测性统计（用于 1 Hz info 日志和 /stm32_bridge/tx_cmd）──────
        # 现场可用 ros2 topic echo /stm32_bridge/tx_cmd 直接看实际写串口的值，
        # 避免被 /cmd_vel → bridge → 串口 → STM32 任意一段卡死时无法定位。
        self._last_rx_time = 0.0     # 最近一次 cmd_vel 回调时间（time.time()）
        self._last_rx_v = 0          # 最近一次 cmd_vel 入参（限幅+死区+补偿后, mm/s）
        self._last_rx_w = 0
        self._last_tx_time = 0.0     # 最近一次实际写串口时间
        self._last_tx_v = 0
        self._last_tx_w = 0
        self._rx_count = 0           # 累计 cmd_vel 回调次数
        self._tx_count = 0           # 累计 _raw_write 成功次数
        self._prev_rx_count = 0
        self._prev_tx_count = 0

        # ── ROS2 订阅/发布 ──────────────────────────────────────────────────
        # 主控制通道：cmd_vel
        self.cmd_sub = self.create_subscription(
            Twist, 'cmd_vel', self.cmd_vel_callback, 10)
        # 独立急停通道：发布任意 std_msgs/Empty 或 Bool 都视为急停
        self.estop_empty_sub = self.create_subscription(
            Empty, 'cmd_vel_estop', self._estop_callback_empty, 10)
        self.estop_bool_sub = self.create_subscription(
            Bool, 'estop', self._estop_callback_bool, 10)
        # 上行：里程计
        self.odom_pub = self.create_publisher(Odometry, 'odom', 10)
        # 调试：实际写入串口的速度 [linear_mm/s, angular_mrad/s]
        # 现场用 `ros2 topic echo /stm32_bridge/tx_cmd` 验证：
        #   - 没有任何输出   → bridge 完全没向串口写（被死区/急停/超时清零）
        #   - 输出值非零但车不动 → 问题在串口/STM32/电机/odom 反馈
        #   - 输出值持续为 0 但 /cmd_vel 非零 → bridge 入口被清零（看 1Hz log）
        self.tx_cmd_pub = self.create_publisher(
            Int32MultiArray, 'stm32_bridge/tx_cmd', 10)

        if self.publish_tf:
            self.tf_broadcaster = TransformBroadcaster(self)
            self.publish_initial_tf()
            self.initial_tf_timer = self.create_timer(
                0.05, self.publish_initial_tf_callback)
            self.received_odom_data = False

        # 接收缓冲区
        self.rx_buffer = bytearray()

        # ── 启动后台线程 ────────────────────────────────────────────────────
        self.running = True

        self.rx_thread = threading.Thread(
            target=self._receive_thread, daemon=True, name='stm32_rx')
        self.rx_thread.start()

        self._write_thread = threading.Thread(
            target=self._serial_write_thread, daemon=True, name='stm32_tx')
        self._write_thread.start()

        self._watchdog_thread = threading.Thread(
            target=self._watchdog_loop, daemon=True, name='stm32_wd')
        self._watchdog_thread.start()

        # 1 Hz 可观测性日志（rx/tx 速率 + 最近值 + 急停锁状态）
        self._observability_timer = self.create_timer(
            1.0, self._observability_callback)

        self.get_logger().info(
            f'[stm32_bridge v5] 已就绪：限速 v={self.max_linear:.2f}m/s, '
            f'w={self.max_angular:.2f}rad/s, cmd_timeout={self.CMD_TIMEOUT}s, '
            f'watchdog={self.WATCHDOG_TIMEOUT}s')

    # ────────────────────────────────────────────────────────────────────────
    # TF 初始化
    # ────────────────────────────────────────────────────────────────────────
    def publish_initial_tf_callback(self):
        if not self.received_odom_data:
            self.publish_initial_tf()
        else:
            if hasattr(self, 'initial_tf_timer'):
                self.initial_tf_timer.cancel()
                self.get_logger().info('收到真实里程计数据，停止发布初始 TF')

    def publish_initial_tf(self):
        t = TransformStamped()
        t.header.stamp = self.get_clock().now().to_msg()
        t.header.frame_id = 'odom'
        t.child_frame_id = 'base_link'
        t.transform.rotation.w = 1.0
        self.tf_broadcaster.sendTransform(t)

    # ────────────────────────────────────────────────────────────────────────
    # cmd_vel 回调（纯内存操作）
    # ────────────────────────────────────────────────────────────────────────
    def cmd_vel_callback(self, msg):
        """
        统一控制入口：
          - 急停锁定期间（_estop_lock_until），一律按零速处理，
            阻止 Nav2 智能恢复或前端误发把急停冲掉。
          - 硬限幅与 STM32 ChassisParams.h 一致。
          - 死区过滤：低于阈值视为 0。
        """
        now = time.time()
        linear_mm = int(msg.linear.x * 1000)
        angular_mrad = int(msg.angular.z * 1000)

        # 硬限幅（mm/s, mrad/s）
        if linear_mm > self._max_linear_mm:
            linear_mm = self._max_linear_mm
        elif linear_mm < -self._max_linear_mm:
            linear_mm = -self._max_linear_mm
        if angular_mrad > self._max_angular_mrad:
            angular_mrad = self._max_angular_mrad
        elif angular_mrad < -self._max_angular_mrad:
            angular_mrad = -self._max_angular_mrad

        # 死区
        if abs(linear_mm) < self._linear_deadzone_mm:
            linear_mm = 0
        if abs(angular_mrad) < self._angular_deadzone_mrad:
            angular_mrad = 0

        # ★ 启动补偿（kickstart）：
        # 死区之外但低于电机最小启动门槛的值，统一抬到门槛值，
        # 否则 Nav2 在 0.10~0.18 m/s 命令下电机会原地卡死。
        # 仅对 linear 做：angular 补偿会让阿克曼前轮舵机抖动（实测有效）。
        if self._min_motion_linear_mm > 0 and 0 < abs(linear_mm) < self._min_motion_linear_mm:
            linear_mm = self._min_motion_linear_mm if linear_mm > 0 else -self._min_motion_linear_mm
        # angular 默认关闭补偿（min_motion_angular=0.0）。如需开启，
        # 在 launch 显式设置 min_motion_angular > 0.0
        if self._min_motion_angular_mrad > 0 and 0 < abs(angular_mrad) < self._min_motion_angular_mrad:
            angular_mrad = self._min_motion_angular_mrad if angular_mrad > 0 else -self._min_motion_angular_mrad

        with self._lock:
            # 可观测性：无论是否被急停清零，都先记录"上层确实送来了命令"
            self._last_rx_time = now
            self._last_rx_v = linear_mm
            self._last_rx_w = angular_mrad
            self._rx_count += 1

            if now < self._estop_lock_until:
                # 急停锁定中：强制零速，不更新 last_cmd_time，
                # 这样如果上层一直发非零速，watchdog 仍会兜底。
                self.latest_linear = 0
                self.latest_angular = 0
                return
            self.latest_linear = linear_mm
            self.latest_angular = angular_mrad
            self.last_cmd_time = now

    # ────────────────────────────────────────────────────────────────────────
    # 独立急停回调
    # ────────────────────────────────────────────────────────────────────────
    def _estop_callback_empty(self, _msg):
        self._trigger_estop('topic:cmd_vel_estop')

    def _estop_callback_bool(self, msg):
        # /estop True → 触发；False 不解锁（解锁由超时自动完成）
        if msg.data:
            self._trigger_estop('topic:estop')

    def _trigger_estop(self, source: str):
        with self._lock:
            self._estop_pending = True
            self.latest_linear = 0
            self.latest_angular = 0
            self._estop_lock_until = time.time() + self.ESTOP_LOCK_SECONDS
        self.get_logger().warn(f'[ESTOP] 急停触发，来源={source}')

    # ────────────────────────────────────────────────────────────────────────
    # 串口写线程
    # ────────────────────────────────────────────────────────────────────────
    def _serial_write_thread(self):
        """
        25 Hz 独立运行的串口写线程。
        优先级：急停 > cmd_timeout 自动停车 > 正常发送。
        """
        interval = 1.0 / max(1.0, self.WRITE_HZ)
        sent_linear = 0
        sent_angular = 0

        while self.running:
            loop_start = time.time()

            with self._lock:
                estop = self._estop_pending
                latest_v = self.latest_linear
                latest_w = self.latest_angular
                last_t = self.last_cmd_time

            # ── 1. 急停（最高优先级）──────────────────────────────────────
            if estop:
                self.get_logger().info(
                    f'[TX] 急停：连发 {self.ESTOP_REPEATS} 帧零速')
                for _ in range(self.ESTOP_REPEATS):
                    self._raw_write(0, 0)
                    time.sleep(0.02)
                sent_linear = 0
                sent_angular = 0
                with self._lock:
                    self._estop_pending = False
                    self.latest_linear = 0
                    self.latest_angular = 0
                # 急停后等下一拍
                elapsed = time.time() - loop_start
                time.sleep(max(0.0, interval - elapsed))
                continue

            now = time.time()

            # ── 2. cmd_vel 超时停车 ───────────────────────────────────────
            if (last_t > 0
                    and now - last_t > self.CMD_TIMEOUT
                    and (sent_linear != 0 or sent_angular != 0)):
                self.get_logger().debug('[TX] cmd_vel 超时，自动停车')
                self._raw_write(0, 0)
                sent_linear = 0
                sent_angular = 0
                with self._lock:
                    self.latest_linear = 0
                    self.latest_angular = 0
                elapsed = time.time() - loop_start
                time.sleep(max(0.0, interval - elapsed))
                continue

            # ── 3. 正常发送 ───────────────────────────────────────────────
            if latest_v != 0 or latest_w != 0:
                self._raw_write(latest_v, latest_w)
                sent_linear = latest_v
                sent_angular = latest_w
            elif sent_linear != 0 or sent_angular != 0:
                # 目标刚归零：补一帧零速
                self._raw_write(0, 0)
                sent_linear = 0
                sent_angular = 0
            # else: 持续零速，不重复刷串口

            elapsed = time.time() - loop_start
            time.sleep(max(0.0, interval - elapsed))

    def _raw_write(self, linear_vel: int, angular_vel: int):
        """直接写串口（仅在 _serial_write_thread 或析构时调用）"""
        cmd = self.build_control_cmd(linear_vel, angular_vel)
        try:
            self.serial.write(cmd)
            # 发布 debug topic：实际进入串口的整数速度
            try:
                tx_msg = Int32MultiArray()
                tx_msg.data = [int(linear_vel), int(angular_vel)]
                self.tx_cmd_pub.publish(tx_msg)
            except Exception:
                # 发布失败不影响串口主链路
                pass
            with self._lock:
                self._last_tx_time = time.time()
                self._last_tx_v = int(linear_vel)
                self._last_tx_w = int(angular_vel)
                self._tx_count += 1
            self.get_logger().debug(
                f'[TX] linear={linear_vel} mm/s, angular={angular_vel} mrad/s')
        except Exception as e:
            self.get_logger().error(f'[TX] 串口写入失败: {e}')

    # ────────────────────────────────────────────────────────────────────────
    # 1 Hz 可观测性日志
    # ────────────────────────────────────────────────────────────────────────
    def _observability_callback(self):
        """
        每秒打印一次：rx/tx 速率、最近 cmd_vel 入参、最近写串口值、急停锁状态。
        现场用这条日志可以快速区分三种"车不动"故障：
          - rx=0/s  → bridge 根本没收到 /cmd_vel（话题/QoS/重映射问题）
          - rx>0 但 last_rx 长时间为 0 → 上层在发零速（Nav2 失败/前端误发）
          - rx>0、last_rx 非零，但 tx=0/s → 入口被死区/急停/超时清零
          - rx>0、tx>0 但车不动 → 问题在串口下游（STM32/电机/odom）
        """
        now = time.time()
        with self._lock:
            rx_count = self._rx_count
            tx_count = self._tx_count
            last_rx_v = self._last_rx_v
            last_rx_w = self._last_rx_w
            last_rx_t = self._last_rx_time
            last_tx_v = self._last_tx_v
            last_tx_w = self._last_tx_w
            last_tx_t = self._last_tx_time
            latest_v = self.latest_linear
            latest_w = self.latest_angular
            estop_locked = now < self._estop_lock_until

        drx = rx_count - self._prev_rx_count
        dtx = tx_count - self._prev_tx_count
        self._prev_rx_count = rx_count
        self._prev_tx_count = tx_count

        rx_age = (now - last_rx_t) if last_rx_t > 0 else -1.0
        tx_age = (now - last_tx_t) if last_tx_t > 0 else -1.0

        self.get_logger().info(
            f'[OBS] rx={drx}/s(total={rx_count}) '
            f'last_rx=(v={last_rx_v}mm/s,w={last_rx_w}mrad/s,age={rx_age:.2f}s) | '
            f'tx={dtx}/s(total={tx_count}) '
            f'last_tx=(v={last_tx_v}mm/s,w={last_tx_w}mrad/s,age={tx_age:.2f}s) | '
            f'latest=(v={latest_v},w={latest_w}) '
            f'estop_lock={estop_locked}'
        )

    # ────────────────────────────────────────────────────────────────────────
    # 看门狗线程
    # ────────────────────────────────────────────────────────────────────────
    def _watchdog_loop(self):
        """
        最终安全兜底：每 100 ms 检查一次。
        若超过 watchdog_timeout 未收到新命令，且 latest_* 非零，
        则直接旁路写线程把零速怼到串口，与 STM32 自身超时形成双保险。
        """
        check_interval = 0.1

        while self.running:
            time.sleep(check_interval)

            with self._lock:
                last_t = self.last_cmd_time
                latest_v = self.latest_linear
                latest_w = self.latest_angular

            if last_t == 0.0:
                continue

            elapsed = time.time() - last_t

            if elapsed > self.WATCHDOG_TIMEOUT and (latest_v != 0 or latest_w != 0):
                self.get_logger().warn(
                    f'[WD] 超时 {elapsed:.2f}s 未收到 cmd_vel，强制停车')
                for _ in range(self.ESTOP_REPEATS):
                    try:
                        self.serial.write(self.build_control_cmd(0, 0))
                    except Exception:
                        pass
                    time.sleep(0.02)
                with self._lock:
                    self.latest_linear = 0
                    self.latest_angular = 0

    # ────────────────────────────────────────────────────────────────────────
    # 帧构造
    # ────────────────────────────────────────────────────────────────────────
    def build_control_cmd(self, linear_vel: int, angular_vel: int) -> bytes:
        """
        构造 10 字节控制帧：
          AA 55 01 <vx:int16 LE> <wz:int16 LE> 00 <cs> 0D
          checksum = sum(byte[2..6]) & 0xFF
        """
        data = bytearray([FRAME_HEADER_0, FRAME_HEADER_1, CMD_VELOCITY])
        data.extend(struct.pack('<h', linear_vel))
        data.extend(struct.pack('<h', angular_vel))
        data.append(0x00)
        checksum = sum(data[2:7]) & 0xFF
        data.append(checksum)
        data.append(FRAME_TAIL)
        return bytes(data)

    # ────────────────────────────────────────────────────────────────────────
    # 接收线程：解析 STM32 上行 odom 帧
    # ────────────────────────────────────────────────────────────────────────
    def _receive_thread(self):
        while self.running and rclpy.ok():
            try:
                data = self.serial.read(self.serial.in_waiting or 1)
                if data:
                    self.rx_buffer.extend(data)
                    self._process_rx_buffer()
            except Exception as e:
                err_str = str(e)
                if 'returned no data' in err_str:
                    time.sleep(0.01)
                else:
                    self.get_logger().error(f'[RX] 接收数据错误: {e}')

    def _process_rx_buffer(self):
        """
        解析 20 字节里程计帧：
          BB 66 type x(int32) y(int32) yaw(int16) v(int16) w(int16) reserved cs 0D
          checksum = sum(byte[2..17]) & 0xFF
        """
        while len(self.rx_buffer) >= ODOM_FRAME_LEN:
            if self.rx_buffer[0] != ODOM_HEADER_0 or self.rx_buffer[1] != ODOM_HEADER_1:
                self.rx_buffer.pop(0)
                continue

            frame = self.rx_buffer[:ODOM_FRAME_LEN]

            if frame[19] != FRAME_TAIL:
                self.rx_buffer.pop(0)
                continue

            checksum_calc = sum(frame[2:18]) & 0xFF
            checksum_recv = frame[18]
            if checksum_calc != checksum_recv:
                self.get_logger().warn(
                    f'[RX] 校验和错误: 计算={checksum_calc}, 接收={checksum_recv}')
                self.rx_buffer.pop(0)
                continue

            data_type = frame[2]
            if data_type == DATA_TYPE_ODOM:
                self._parse_odom_data(frame)

            self.rx_buffer = self.rx_buffer[ODOM_FRAME_LEN:]

    def _parse_odom_data(self, frame):
        if self.publish_tf:
            self.received_odom_data = True

        pos_x = struct.unpack('<i', frame[3:7])[0]
        pos_y = struct.unpack('<i', frame[7:11])[0]
        yaw = struct.unpack('<h', frame[11:13])[0]
        linear_vel = struct.unpack('<h', frame[13:15])[0]
        angular_vel = struct.unpack('<h', frame[15:17])[0]

        x = pos_x / 1000.0
        y = pos_y / 1000.0
        theta = yaw / 1000.0
        vx = linear_vel / 1000.0
        vth = angular_vel / 1000.0

        current_time = self.get_clock().now()
        cy = math.cos(theta / 2.0)
        sy = math.sin(theta / 2.0)

        if self.publish_tf:
            t = TransformStamped()
            t.header.stamp = current_time.to_msg()
            t.header.frame_id = 'odom'
            t.child_frame_id = 'base_link'
            t.transform.translation.x = x
            t.transform.translation.y = y
            t.transform.translation.z = 0.0
            t.transform.rotation.w = cy
            t.transform.rotation.x = 0.0
            t.transform.rotation.y = 0.0
            t.transform.rotation.z = sy
            self.tf_broadcaster.sendTransform(t)

        odom = Odometry()
        odom.header.stamp = current_time.to_msg()
        odom.header.frame_id = 'odom'
        odom.child_frame_id = 'base_link'
        odom.pose.pose.position.x = x
        odom.pose.pose.position.y = y
        odom.pose.pose.position.z = 0.0
        odom.pose.pose.orientation.w = cy
        odom.pose.pose.orientation.x = 0.0
        odom.pose.pose.orientation.y = 0.0
        odom.pose.pose.orientation.z = sy
        odom.twist.twist.linear.x = vx
        odom.twist.twist.linear.y = 0.0
        odom.twist.twist.angular.z = vth

        self.odom_pub.publish(odom)
        self.get_logger().debug(
            f'[RX] x={x:.3f}, y={y:.3f}, yaw={theta:.3f}, '
            f'vx={vx:.3f}, vth={vth:.3f}')

    # ────────────────────────────────────────────────────────────────────────
    # 清理
    # ────────────────────────────────────────────────────────────────────────
    def destroy_node(self):
        self.running = False
        # 强制写多帧零速，确保 STM32 收到
        for _ in range(self.ESTOP_REPEATS):
            try:
                self.serial.write(self.build_control_cmd(0, 0))
                time.sleep(0.02)
            except Exception:
                pass
        for t in [
            getattr(self, 'rx_thread', None),
            getattr(self, '_write_thread', None),
            getattr(self, '_watchdog_thread', None),
        ]:
            if t and t.is_alive():
                t.join(timeout=1.0)
        if hasattr(self, 'serial') and self.serial.is_open:
            self.serial.close()
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = STM32Bridge()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
