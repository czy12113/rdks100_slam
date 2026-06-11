#!/usr/bin/env python3
"""
STM32串口通信桥接节点  v4 —— 串口写线程完全解耦

架构变化（相对 v3）：
  v3 的根本缺陷：_do_send() 在 ROS2 定时器回调中直接调用 serial.write()。
  serial.write() 是同步阻塞 I/O，一旦串口缓冲区满或系统调度延迟，
  整个 ROS2 MultiThreadedExecutor 的 spin 线程被阻塞，导致：
    - cmd_vel_callback 无法及时处理新消息
    - latest_linear/angular 无法更新
    - 松键后的零速帧堆积在 ROS2 回调队列里，迟迟发不出去
    - 看上去就是"速度锁死"

v4 方案：
  1. ROS2 定时器 + cmd_vel_callback 只操作内存变量（无任何 I/O）
  2. 独立串口写线程（_serial_write_thread）以 25Hz 从内存读取最新速度并写串口
     - 串口 I/O 完全在独立线程，永远不阻塞 ROS2 spin
  3. 独立看门狗线程保留，作为最终安全兜底
  4. CMD_TIMEOUT 降为 0.3s（前端 50ms 发送间隔，0.3s 远大于正常延迟）
  5. WATCHDOG_TIMEOUT 降为 0.6s

参数说明：
  - LINEAR_DEADZONE  3 mm/s   ：低于此视为零速
  - ANGULAR_DEADZONE 8 mrad/s ：低于此视为零速
  - CMD_TIMEOUT      0.3s     ：无新命令后自动停车
  - WATCHDOG_TIMEOUT 0.6s     ：看门狗兜底超时
  - WRITE_HZ         25       ：串口写线程频率
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

        port     = self.get_parameter('port').value
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

        # ── 共享状态（只由内存操作，无 I/O）────────────────────────────────
        # latest_*：cmd_vel_callback 写入的最新目标速度（mm/s, mrad/s）
        self.latest_linear  = 0
        self.latest_angular = 0
        # last_cmd_time：最后一次收到 cmd_vel 的时间戳
        self.last_cmd_time  = 0.0
        # 急停标志：置 True 后串口写线程立即发零速
        self._estop_pending = False
        # 全局锁（保护上述所有字段）
        self._lock = threading.Lock()

        # ── 超时阈值 ─────────────────────────────────────────────────────────
        # 前端 50ms 发一次，正常延迟 < 100ms；0.3s 是充裕的超时保护
        self.CMD_TIMEOUT      = 0.3   # 秒：无新命令后自动停车
        self.WATCHDOG_TIMEOUT = 0.6   # 秒：看门狗兜底超时
        self.WATCHDOG_STOP_REPEATS = 5

        # 死区阈值（与前端对齐）
        self.LINEAR_DEADZONE  = 3    # mm/s
        self.ANGULAR_DEADZONE = 8    # mrad/s

        # ── ROS2 订阅/发布 ──────────────────────────────────────────────────
        self.cmd_sub  = self.create_subscription(
            Twist, 'cmd_vel', self.cmd_vel_callback, 10)
        self.odom_pub = self.create_publisher(Odometry, 'odom', 10)

        # TF 广播
        if self.publish_tf:
            self.tf_broadcaster = TransformBroadcaster(self)
            self.publish_initial_tf()
            self.initial_tf_timer = self.create_timer(
                0.05, self.publish_initial_tf_callback)
            self.received_odom_data = False

        # 接收缓冲区
        self.rx_buffer = bytearray()

        # ── 启动线程 ─────────────────────────────────────────────────────────
        self.running = True

        # 串口接收线程（不变）
        self.rx_thread = threading.Thread(
            target=self._receive_thread, daemon=True, name='stm32_rx')
        self.rx_thread.start()

        # 串口写线程（v4 新增）：25Hz，完全独立，不阻塞 ROS2 spin
        self.WRITE_HZ = 25
        self._write_thread = threading.Thread(
            target=self._serial_write_thread, daemon=True, name='stm32_tx')
        self._write_thread.start()

        # 独立看门狗线程（兜底）
        self._watchdog_thread = threading.Thread(
            target=self._watchdog_loop, daemon=True, name='stm32_wd')
        self._watchdog_thread.start()

        self.get_logger().info(
            'STM32桥接节点已启动（v4：串口写线程解耦模式）')

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
        t.header.stamp    = self.get_clock().now().to_msg()
        t.header.frame_id = 'odom'
        t.child_frame_id  = 'base_link'
        t.transform.rotation.w = 1.0
        self.tf_broadcaster.sendTransform(t)

    # ── cmd_vel 回调（纯内存操作，无 I/O）────────────────────────────────

    def cmd_vel_callback(self, msg):
        """
        接收 ROS2 cmd_vel 消息，仅更新内存变量。
        不做任何串口操作，永远不阻塞 ROS2 spin 线程。
        """
        linear_vel  = int(msg.linear.x  * 1000)
        angular_vel = int(msg.angular.z * 1000)

        # 硬限幅
        linear_vel  = max(-1000, min(1000,  linear_vel))
        angular_vel = max(-1570, min(1570, angular_vel))

        # 死区：低于阈值强制归零
        if abs(linear_vel)  < self.LINEAR_DEADZONE:
            linear_vel  = 0
        if abs(angular_vel) < self.ANGULAR_DEADZONE:
            angular_vel = 0

        with self._lock:
            self.latest_linear  = linear_vel
            self.latest_angular = angular_vel
            self.last_cmd_time  = time.time()

    # ── 串口写线程（v4 核心）───────────────────────────────────────────────

    def _serial_write_thread(self):
        """
        独立串口写线程，25Hz 运行。
        所有 serial.write() 调用都在这个线程，永远不会阻塞 ROS2 spin。

        发送策略：
          1. 急停优先：_estop_pending=True → 发 5 帧零速，然后清标志
          2. CMD_TIMEOUT 超时：无新命令且上次发的非零 → 发零速停车
          3. 非零速目标：每帧都发（持续驱动 STM32，防止 STM32 端超时）
          4. 零速状态：只在"刚从非零变零"时发一次，之后不重复发
        """
        interval = 1.0 / self.WRITE_HZ   # 40ms
        sent_linear  = 0   # 上次已发送的线速度
        sent_angular = 0   # 上次已发送的角速度

        while self.running:
            loop_start = time.time()

            with self._lock:
                estop    = self._estop_pending
                latest_v = self.latest_linear
                latest_w = self.latest_angular
                last_t   = self.last_cmd_time

            # ── 1. 急停优先 ──────────────────────────────────────────────
            if estop:
                self.get_logger().info('[TX] 急停：连续发送 5 帧零速')
                for _ in range(5):
                    self._raw_write(0, 0)
                    time.sleep(0.02)
                sent_linear  = 0
                sent_angular = 0
                with self._lock:
                    self._estop_pending = False
                    self.latest_linear  = 0
                    self.latest_angular = 0
                # 急停后等下一拍，跳过本轮剩余逻辑
                elapsed = time.time() - loop_start
                time.sleep(max(0.0, interval - elapsed))
                continue

            now = time.time()

            # ── 2. CMD_TIMEOUT 超时停车 ──────────────────────────────────
            if (last_t > 0
                    and now - last_t > self.CMD_TIMEOUT
                    and (sent_linear != 0 or sent_angular != 0)):
                self.get_logger().debug('[TX] cmd_vel 超时，自动停车')
                self._raw_write(0, 0)
                sent_linear  = 0
                sent_angular = 0
                with self._lock:
                    self.latest_linear  = 0
                    self.latest_angular = 0
                elapsed = time.time() - loop_start
                time.sleep(max(0.0, interval - elapsed))
                continue

            # ── 3. 正常发送 ──────────────────────────────────────────────
            if latest_v != 0 or latest_w != 0:
                # 非零速：每帧都发，保持电机连续驱动
                self._raw_write(latest_v, latest_w)
                sent_linear  = latest_v
                sent_angular = latest_w
            elif sent_linear != 0 or sent_angular != 0:
                # 目标归零但上次发的非零：发一次零速停车
                self._raw_write(0, 0)
                sent_linear  = 0
                sent_angular = 0
            # else: 双零，不重复发串口

            elapsed = time.time() - loop_start
            time.sleep(max(0.0, interval - elapsed))

    def _raw_write(self, linear_vel: int, angular_vel: int):
        """直接写串口（只在 _serial_write_thread 中调用）"""
        cmd = self.build_control_cmd(linear_vel, angular_vel)
        try:
            self.serial.write(cmd)
            self.get_logger().debug(
                f'[TX] linear={linear_vel} mm/s, angular={angular_vel} mrad/s')
        except Exception as e:
            self.get_logger().error(f'[TX] 串口写入失败: {e}')

    # ── 看门狗线程（兜底，不依赖任何 ROS2 机制）──────────────────────────

    def _watchdog_loop(self):
        """
        最终安全兜底：每 150ms 检查一次。
        若超过 WATCHDOG_TIMEOUT(0.6s) 未收到新命令，
        且串口写线程上次发的是非零速，则强制直接写串口停车。
        （这里直接写串口而不是通过 _estop_pending，避免看门狗被写线程延迟）
        """
        last_wd_sent_zero = False

        while self.running:
            time.sleep(0.15)

            with self._lock:
                last_t   = self.last_cmd_time
                latest_v = self.latest_linear
                latest_w = self.latest_angular

            if last_t == 0.0:
                continue

            elapsed = time.time() - last_t

            if elapsed > self.WATCHDOG_TIMEOUT and (latest_v != 0 or latest_w != 0):
                self.get_logger().warn(
                    f'[WD] 超时 {elapsed:.2f}s 未收到命令，强制停车！')
                # 直接写串口（绕过写线程，确保即时送达）
                for _ in range(self.WATCHDOG_STOP_REPEATS):
                    try:
                        self.serial.write(self.build_control_cmd(0, 0))
                    except Exception:
                        pass
                    time.sleep(0.02)
                with self._lock:
                    self.latest_linear  = 0
                    self.latest_angular = 0
                last_wd_sent_zero = True
            else:
                last_wd_sent_zero = False

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
                    f'[RX] 校验和错误: 计算={checksum_calc}, 接收={checksum_recv}')
                self.rx_buffer.pop(0)
                continue

            data_type = frame[2]
            if data_type == 0x01:
                self._parse_odom_data(frame)

            self.rx_buffer = self.rx_buffer[20:]

    def _parse_odom_data(self, frame):
        """解析并发布里程计"""
        if self.publish_tf:
            self.received_odom_data = True

        pos_x       = struct.unpack('<i', frame[3:7])[0]
        pos_y       = struct.unpack('<i', frame[7:11])[0]
        yaw         = struct.unpack('<h', frame[11:13])[0]
        linear_vel  = struct.unpack('<h', frame[13:15])[0]
        angular_vel = struct.unpack('<h', frame[15:17])[0]

        x     = pos_x       / 1000.0
        y     = pos_y       / 1000.0
        theta = yaw         / 1000.0
        vx    = linear_vel  / 1000.0
        vth   = angular_vel / 1000.0

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
            f'[RX] x={x:.3f}, y={y:.3f}, yaw={theta:.3f}, '
            f'vx={vx:.3f}, vth={vth:.3f}')

    # ── 清理 ────────────────────────────────────────────────────────────────

    def destroy_node(self):
        self.running = False
        # 直接写串口发停车帧（写线程可能已退出）
        for _ in range(5):
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
