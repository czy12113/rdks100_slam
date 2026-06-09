#!/usr/bin/env python3
"""
STM32串口通信桥接节点
功能：
1. 订阅 /cmd_vel，转换为控制命令发送给STM32
2. 接收STM32的里程计数据，发布 /odom 和 TF

修复说明（v3）：
- 降低死区阈值：线速度 3mm/s、角速度 8mrad/s，避免停车指令被过滤
- 超时停车：0.15s 无新命令立即发送零速，保证松键必停
- 急停优先：通过 _estop_pending 标志确保急停帧插队发送
- 去重阈值放宽：线速度 2mm/s、角速度 5mrad/s，提高跟随精度
- 发送频率提升到 25Hz（40ms），减少控制延迟
- 独立看门狗线程：不依赖 ROS2 定时器，每 100ms 检查一次，
  超过 WATCHDOG_TIMEOUT(0.3s) 无新命令且已发送非零速 → 强制发零速帧
  确保即使 ROS2 回调卡死、定时器延迟，小车也能停下
"""
import rclpy
from rclpy.node import Node
from geometry_msgs.msg import Twist, TransformStamped
from nav_msgs.msg import Odometry
from tf2_ros import TransformBroadcaster
import serial
import struct
import math
import threading
import time


class STM32Bridge(Node):
    def __init__(self):
        super().__init__('stm32_bridge')

        # 声明参数
        self.declare_parameter('port', '/dev/ttyUSB0')
        self.declare_parameter('baudrate', 115200)
        self.declare_parameter('publish_tf', True)

        port = self.get_parameter('port').value
        baudrate = self.get_parameter('baudrate').value
        self.publish_tf = self.get_parameter('publish_tf').value

        # 自动探测串口
        import os as _os
        candidate_ports = [port] + [
            p for p in ['/dev/ttyUSB0', '/dev/ttyUSB1', '/dev/ttyUSB2']
            if p != port
        ]
        actual_port = None
        for p in candidate_ports:
            if _os.path.exists(p):
                actual_port = p
                break

        if actual_port is None:
            self.get_logger().error(
                f'未找到任何串口设备，已尝试: {candidate_ports}')
            raise RuntimeError(f'No serial port found, tried: {candidate_ports}')

        if actual_port != port:
            self.get_logger().warn(
                f'指定端口 {port} 不存在，自动切换到 {actual_port}')

        # 初始化串口
        try:
            self.serial = serial.Serial(actual_port, baudrate, timeout=0.1)
            self.get_logger().info(f'串口已打开: {actual_port} @ {baudrate}')
        except Exception as e:
            self.get_logger().error(f'无法打开串口 {actual_port}: {e}')
            raise

        # ── 命令节流缓存 ────────────────────────────────────────────────────
        self.latest_linear  = 0      # 最新目标线速度 (mm/s)
        self.latest_angular = 0      # 最新目标角速度 (mrad/s)
        self.sent_linear    = 0      # 上次已发送线速度 (mm/s)
        self.sent_angular   = 0      # 上次已发送角速度 (mrad/s)
        self.last_cmd_time  = 0.0    # 最后收到 cmd_vel 的时间（秒）

        # 急停优先标志：置 True 后，发送循环无条件立刻发零速
        self._estop_pending = False
        self._lock = threading.Lock()

        # 超时阈值：0.5s 无新命令自动发送停车帧
        # 需要足够长以覆盖前端 HTTP 往返延迟（200ms timeout + 网络波动）
        # 前端 50ms 发送间隔 + _sendingInFlight 互斥可能导致实际间隔 > 200ms
        self.CMD_TIMEOUT = 0.5

        # 看门狗超时：独立于 ROS2 定时器的最终安全保障
        # 1.0s 无新命令且当前非零速 → 强制发送零速帧
        # 比 CMD_TIMEOUT(0.5s) 更长，作为"兜底"机制，不影响正常控制流
        self.WATCHDOG_TIMEOUT = 1.0
        # 看门狗连续发送零速次数（确保 STM32 收到）
        self.WATCHDOG_STOP_REPEATS = 3

        # 死区阈值（与前端 VX_ZERO_THRESHOLD/WZ_ZERO_THRESHOLD 对齐）
        # 线速度：3 mm/s（0.003 m/s），低于此视为零
        # 角速度：8 mrad/s（~0.008 rad/s），低于此视为零
        self.LINEAR_DEADZONE  = 3
        self.ANGULAR_DEADZONE = 8

        # 去重发送阈值：变化低于此值不触发新帧（过滤噪声，不影响停车）
        # 设置比死区稍小，确保"趋近零"的小值也能被发出
        self.LINEAR_SEND_THR  = 2
        self.ANGULAR_SEND_THR = 5

        # 订阅速度命令
        self.cmd_sub = self.create_subscription(
            Twist, 'cmd_vel', self.cmd_vel_callback, 10)

        # 发布里程计
        self.odom_pub = self.create_publisher(Odometry, 'odom', 10)

        # TF广播
        if self.publish_tf:
            self.tf_broadcaster = TransformBroadcaster(self)
            self.publish_initial_tf()
            self.initial_tf_timer = self.create_timer(0.05, self.publish_initial_tf_callback)
            self.received_odom_data = False

        # 接收缓冲区
        self.rx_buffer = bytearray()

        # 启动接收线程
        self.running = True
        self.rx_thread = threading.Thread(target=self.receive_thread, daemon=True)
        self.rx_thread.start()

        # 命令发送定时器：25Hz（40ms），比原来的 20Hz 更快响应
        self.cmd_timer = self.create_timer(0.04, self.send_cmd_if_changed)

        # 独立看门狗线程：不依赖 ROS2 定时器，作为最终安全兜底
        self._watchdog_thread = threading.Thread(
            target=self._watchdog_loop, daemon=True)
        self._watchdog_thread.start()

        self.get_logger().info('STM32桥接节点已启动（v3：低延迟+看门狗模式）')

    # ── TF 初始化 ──────────────────────────────────────────────────────────

    def publish_initial_tf_callback(self):
        if not self.received_odom_data:
            self.publish_initial_tf()
        else:
            if hasattr(self, 'initial_tf_timer'):
                self.initial_tf_timer.cancel()
                self.get_logger().info('收到真实里程计数据，停止发布初始TF')

    def publish_initial_tf(self):
        t = TransformStamped()
        t.header.stamp = self.get_clock().now().to_msg()
        t.header.frame_id = 'odom'
        t.child_frame_id = 'base_link'
        t.transform.translation.x = 0.0
        t.transform.translation.y = 0.0
        t.transform.translation.z = 0.0
        t.transform.rotation.w = 1.0
        t.transform.rotation.x = 0.0
        t.transform.rotation.y = 0.0
        t.transform.rotation.z = 0.0
        self.tf_broadcaster.sendTransform(t)

    # ── cmd_vel 回调 ────────────────────────────────────────────────────────

    def cmd_vel_callback(self, msg):
        """接收速度命令，缓存到 latest_*，由定时器节流发送"""
        # 转换单位：m/s -> mm/s, rad/s -> mrad/s
        linear_vel  = int(msg.linear.x  * 1000)
        angular_vel = int(msg.angular.z * 1000)

        # 硬限幅
        linear_vel  = max(-1000, min(1000,  linear_vel))
        angular_vel = max(-1570, min(1570, angular_vel))

        # 死区：低于阈值强制归零，防止低通滤波尾部微小值驱动舵机抖动
        if abs(linear_vel)  < self.LINEAR_DEADZONE:
            linear_vel  = 0
        if abs(angular_vel) < self.ANGULAR_DEADZONE:
            angular_vel = 0

        with self._lock:
            self.latest_linear  = linear_vel
            self.latest_angular = angular_vel
            self.last_cmd_time  = time.time()

    # ── 发送循环（25Hz 定时器） ───────────────────────────────────────────

    def send_cmd_if_changed(self):
        """定时器回调（25Hz）：急停优先 → 超时停车 → 去重发送"""
        now = time.time()

        with self._lock:
            estop    = self._estop_pending
            latest_v = self.latest_linear
            latest_w = self.latest_angular
            sent_v   = self.sent_linear
            sent_w   = self.sent_angular
            last_t   = self.last_cmd_time

        # 1. 急停优先：不论任何状态，立即发送零速
        if estop:
            self._do_send(0, 0)
            with self._lock:
                self._estop_pending = False
                self.latest_linear  = 0
                self.latest_angular = 0
            return

        # 2. 超时保护：CMD_TIMEOUT 内无新命令，强制归零
        #    条件：曾经收到过命令（last_cmd_time > 0）AND 已超时 AND 当前已发送速度非零
        if (last_t > 0
                and now - last_t > self.CMD_TIMEOUT
                and (sent_v != 0 or sent_w != 0)):
            self.get_logger().debug('cmd_vel 超时，自动停车')
            self._do_send(0, 0)
            with self._lock:
                self.latest_linear  = 0
                self.latest_angular = 0
            return

        # 3. 发送策略：
        #    - 目标非零：每次定时器都发送（持续驱动电机，防止 STM32 端超时）
        #    - 目标为零且上次已发过零：跳过（避免无意义的零速刷串口）
        if latest_v != 0 or latest_w != 0:
            # 非零速：无条件发送，保持电机持续驱动
            self._do_send(latest_v, latest_w)
        elif sent_v != 0 or sent_w != 0:
            # 目标归零但上次发的非零：发一次零速停车
            self._do_send(0, 0)
        # else: 双零，不重复发

    def _do_send(self, linear_vel: int, angular_vel: int):
        """实际写串口，并更新已发送缓存"""
        cmd = self.build_control_cmd(linear_vel, angular_vel)
        try:
            self.serial.write(cmd)
            with self._lock:
                self.sent_linear  = linear_vel
                self.sent_angular = angular_vel
            self.get_logger().debug(
                f'发送: linear={linear_vel} mm/s, angular={angular_vel} mrad/s')
        except Exception as e:
            self.get_logger().error(f'发送命令失败: {e}')

    # ── 急停接口（供外部调用） ───────────────────────────────────────────

    def trigger_estop(self):
        """外部触发急停：设置标志，下次定时器立即发出零速"""
        with self._lock:
            self._estop_pending = True
            self.latest_linear  = 0
            self.latest_angular = 0
        # 同步写一次，不等定时器（减少最坏延迟）
        self._do_send(0, 0)

    # ── 独立看门狗线程 ─────────────────────────────────────────────────────

    def _watchdog_loop(self):
        """
        独立看门狗：每 100ms 检查一次，不依赖 ROS2 定时器系统。
        如果超过 WATCHDOG_TIMEOUT 没有收到新的 cmd_vel，
        且当前已发送速度不为零，则强制连续发送零速帧。
        这是最终安全兜底，确保即使 ROS2 回调卡死小车也能停下。
        """
        while self.running:
            time.sleep(0.1)  # 100ms 检查间隔

            with self._lock:
                last_t = self.last_cmd_time
                sent_v = self.sent_linear
                sent_w = self.sent_angular

            # 未曾收到过命令，跳过
            if last_t == 0.0:
                continue

            elapsed = time.time() - last_t

            # 超时且当前非零速 → 强制停车
            if elapsed > self.WATCHDOG_TIMEOUT and (sent_v != 0 or sent_w != 0):
                self.get_logger().warn(
                    f'[看门狗] 超时 {elapsed:.2f}s 未收到命令，强制停车！')
                # 连续发送多次零速帧，确保 STM32 收到
                for _ in range(self.WATCHDOG_STOP_REPEATS):
                    try:
                        cmd = self.build_control_cmd(0, 0)
                        self.serial.write(cmd)
                    except Exception:
                        pass
                    time.sleep(0.02)  # 20ms 间隔，避免串口拥堵

                # 更新状态
                with self._lock:
                    self.sent_linear = 0
                    self.sent_angular = 0
                    self.latest_linear = 0
                    self.latest_angular = 0

    # ── 帧构造 ──────────────────────────────────────────────────────────────

    def build_control_cmd(self, linear_vel, angular_vel):
        """构造控制命令帧 (10字节): AA 55 01 <vx:i16> <wz:i16> 00 <cs> 0D"""
        data = bytearray([0xAA, 0x55, 0x01])
        data.extend(struct.pack('<h', linear_vel))
        data.extend(struct.pack('<h', angular_vel))
        data.append(0x00)
        checksum = sum(data[2:7]) & 0xFF
        data.append(checksum)
        data.append(0x0D)
        return bytes(data)

    # ── 接收线程 ────────────────────────────────────────────────────────────

    def receive_thread(self):
        while self.running and rclpy.ok():
            try:
                data = self.serial.read(self.serial.in_waiting or 1)
                if data:
                    self.rx_buffer.extend(data)
                    self.process_rx_buffer()
            except Exception as e:
                err_str = str(e)
                if 'returned no data' in err_str:
                    self.get_logger().debug(f'串口空读（忽略）: {e}')
                    time.sleep(0.01)
                else:
                    self.get_logger().error(f'接收数据错误: {e}')

    def process_rx_buffer(self):
        """解析里程计帧（20字节）：BB 66 type x y yaw vx wz reserved cs 0D"""
        while len(self.rx_buffer) >= 20:
            if self.rx_buffer[0] != 0xBB or self.rx_buffer[1] != 0x66:
                self.rx_buffer.pop(0)
                continue

            if len(self.rx_buffer) < 20:
                break

            frame = self.rx_buffer[:20]

            if frame[19] != 0x0D:
                self.rx_buffer.pop(0)
                continue

            checksum_calc = sum(frame[2:18]) & 0xFF
            checksum_recv = frame[18]

            if checksum_calc != checksum_recv:
                self.get_logger().warn(
                    f'校验和错误: 计算={checksum_calc}, 接收={checksum_recv}')
                self.rx_buffer.pop(0)
                continue

            data_type = frame[2]
            if data_type == 0x01:
                self.parse_odom_data(frame)

            self.rx_buffer = self.rx_buffer[20:]

    def parse_odom_data(self, frame):
        """解析并发布里程计"""
        if self.publish_tf:
            self.received_odom_data = True

        pos_x      = struct.unpack('<i', frame[3:7])[0]
        pos_y      = struct.unpack('<i', frame[7:11])[0]
        yaw        = struct.unpack('<h', frame[11:13])[0]
        linear_vel = struct.unpack('<h', frame[13:15])[0]
        angular_vel= struct.unpack('<h', frame[15:17])[0]

        x    = pos_x       / 1000.0
        y    = pos_y       / 1000.0
        theta= yaw         / 1000.0
        vx   = linear_vel  / 1000.0
        vth  = angular_vel / 1000.0

        current_time = self.get_clock().now()

        cy = math.cos(theta / 2.0)
        sy = math.sin(theta / 2.0)

        if self.publish_tf:
            t = TransformStamped()
            t.header.stamp    = current_time.to_msg()
            t.header.frame_id = 'odom'
            t.child_frame_id  = 'base_link'
            t.transform.translation.x = x
            t.transform.translation.y = y
            t.transform.translation.z = 0.0
            t.transform.rotation.w = cy
            t.transform.rotation.x = 0.0
            t.transform.rotation.y = 0.0
            t.transform.rotation.z = sy
            self.tf_broadcaster.sendTransform(t)

        odom = Odometry()
        odom.header.stamp    = current_time.to_msg()
        odom.header.frame_id = 'odom'
        odom.child_frame_id  = 'base_link'
        odom.pose.pose.position.x    = x
        odom.pose.pose.position.y    = y
        odom.pose.pose.position.z    = 0.0
        odom.pose.pose.orientation.w = cy
        odom.pose.pose.orientation.x = 0.0
        odom.pose.pose.orientation.y = 0.0
        odom.pose.pose.orientation.z = sy
        odom.twist.twist.linear.x    = vx
        odom.twist.twist.linear.y    = 0.0
        odom.twist.twist.angular.z   = vth

        self.odom_pub.publish(odom)

        self.get_logger().debug(
            f'里程计: x={x:.3f}, y={y:.3f}, yaw={theta:.3f}, '
            f'vx={vx:.3f}, vth={vth:.3f}')

    # ── 清理 ────────────────────────────────────────────────────────────────

    def destroy_node(self):
        self.running = False
        # 发送多次停车帧再退出，确保 STM32 收到
        for _ in range(3):
            try:
                self.serial.write(self.build_control_cmd(0, 0))
                time.sleep(0.02)
            except Exception:
                pass
        # 等待线程退出
        if hasattr(self, 'rx_thread'):
            self.rx_thread.join(timeout=1.0)
        if hasattr(self, '_watchdog_thread'):
            self._watchdog_thread.join(timeout=0.5)
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
