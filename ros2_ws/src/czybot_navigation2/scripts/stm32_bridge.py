#!/usr/bin/env python3
"""
STM32串口通信桥接节点
功能：
1. 订阅 /cmd_vel，转换为控制命令发送给STM32
2. 接收STM32的里程计数据，发布 /odom 和 TF
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
        
        # 初始化串口
        try:
            self.serial = serial.Serial(port, baudrate, timeout=0.1)
            self.get_logger().info(f'串口已打开: {port} @ {baudrate}')
        except Exception as e:
            self.get_logger().error(f'无法打开串口 {port}: {e}')
            raise
        
        # 命令节流缓存（防止低通滤波尾部微小变化持续触发串口写入）
        self.latest_linear = 0       # 最新线速度缓存 (mm/s)
        self.latest_angular = 0      # 最新角速度缓存 (mrad/s)
        self.sent_linear = 0         # 已发送线速度 (mm/s)
        self.sent_angular = 0        # 已发送角速度 (mrad/s)
        self.last_cmd_time = 0.0     # 最后收到 cmd_vel 的时间（秒）
        self.CMD_TIMEOUT = 0.3       # 超时阈值：0.3s 无新命令则自动停车

        # 订阅速度命令
        self.cmd_sub = self.create_subscription(
            Twist, 'cmd_vel', self.cmd_vel_callback, 10)
        
        # 发布里程计
        self.odom_pub = self.create_publisher(Odometry, 'odom', 10)
        
        # TF广播
        if self.publish_tf:
            self.tf_broadcaster = TransformBroadcaster(self)
            # 立即发布初始TF，避免激光数据等待
            self.publish_initial_tf()
            # 创建定时器持续发布TF，直到收到真实里程计数据
            self.initial_tf_timer = self.create_timer(0.05, self.publish_initial_tf_callback)
            self.received_odom_data = False
        
        # 接收缓冲区
        self.rx_buffer = bytearray()
        
        # 启动接收线程
        self.running = True
        self.rx_thread = threading.Thread(target=self.receive_thread, daemon=True)
        self.rx_thread.start()
        
        # 命令发送定时器：20Hz 节流，避免每帧 cmd_vel 都写串口
        self.cmd_timer = self.create_timer(0.05, self.send_cmd_if_changed)

        self.get_logger().info('STM32桥接节点已启动')
    
    def publish_initial_tf_callback(self):
        """定时器回调：持续发布初始TF，直到收到真实里程计数据"""
        if not self.received_odom_data:
            self.publish_initial_tf()
        else:
            # 收到真实数据后，停止定时器
            if hasattr(self, 'initial_tf_timer'):
                self.initial_tf_timer.cancel()
                self.get_logger().info('收到真实里程计数据，停止发布初始TF')
    
    def publish_initial_tf(self):
        """发布初始TF（位置为原点），避免激光数据等待TF"""
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
    
    def cmd_vel_callback(self, msg):
        """接收速度命令，缓存到 latest_*，由定时器节流发送"""
        import time
        # 转换单位：m/s -> mm/s, rad/s -> mrad/s
        linear_vel = int(msg.linear.x * 1000)  # m/s -> mm/s
        angular_vel = int(msg.angular.z * 1000)  # rad/s -> mrad/s

        # 限幅
        linear_vel = max(-1000, min(1000, linear_vel))
        angular_vel = max(-1570, min(1570, angular_vel))

        # 死区过滤：低于阈值的微小速度强制归零
        # 防止上位机低通滤波尾部的残余值持续驱动舵机抖动
        # 线速度死区：8 mm/s（对应 0.008 m/s）
        # 角速度死区：20 mrad/s（对应 ~0.02 rad/s），舵机对小角速度更敏感
        if abs(linear_vel) < 8:
            linear_vel = 0
        if abs(angular_vel) < 20:
            angular_vel = 0

        # 只更新缓存，不直接写串口（由 send_cmd_if_changed 定时节流发送）
        self.latest_linear = linear_vel
        self.latest_angular = angular_vel
        self.last_cmd_time = time.time()

    def send_cmd_if_changed(self):
        """定时器回调（20Hz）：节流发送，去重 + 超时自动停车"""
        import time
        now = time.time()

        # 超时保护：如果超过 CMD_TIMEOUT 没收到新命令，强制归零
        # 防止前端断连后舵机卡在最后位置
        if (self.last_cmd_time > 0 and
                now - self.last_cmd_time > self.CMD_TIMEOUT and
                (self.sent_linear != 0 or self.sent_angular != 0)):
            self.latest_linear = 0
            self.latest_angular = 0

        dl = abs(self.latest_linear - self.sent_linear)
        da = abs(self.latest_angular - self.sent_angular)

        # 满足以下任一条件才发送：
        # 1. 线速度变化 > 5 mm/s（避免微小波动触发）
        # 2. 角速度变化 > 10 mrad/s（舵机分辨率约 1°≈17mrad，10mrad 以下无意义）
        # 3. 目标为 (0,0) 且上次非零（确保停车指令必达）
        need_send = (
            dl > 5 or da > 10 or
            (self.latest_linear == 0 and self.latest_angular == 0 and
             (self.sent_linear != 0 or self.sent_angular != 0))
        )

        if need_send:
            cmd = self.build_control_cmd(self.latest_linear, self.latest_angular)
            try:
                self.serial.write(cmd)
                self.sent_linear = self.latest_linear
                self.sent_angular = self.latest_angular
                self.get_logger().debug(
                    f'发送命令: linear={self.latest_linear} mm/s, '
                    f'angular={self.latest_angular} mrad/s')
            except Exception as e:
                self.get_logger().error(f'发送命令失败: {e}')
    
    def build_control_cmd(self, linear_vel, angular_vel):
        """构造控制命令帧 (10字节)"""
        # 帧头: 0xAA 0x55
        # 命令类型: 0x01 (速度控制)
        # 线速度: int16 (mm/s)
        # 角速度: int16 (mrad/s)
        # 保留: 0x00
        # 校验和: uint8
        # 帧尾: 0x0D
        
        data = bytearray([0xAA, 0x55, 0x01])
        data.extend(struct.pack('<h', linear_vel))  # 小端int16
        data.extend(struct.pack('<h', angular_vel))
        data.append(0x00)  # 保留字节
        
        # 计算校验和 (从cmd_type到reserved)
        checksum = sum(data[2:7]) & 0xFF
        data.append(checksum)
        data.append(0x0D)  # 帧尾
        
        return bytes(data)
    
    def receive_thread(self):
        """接收线程，处理STM32发来的数据"""
        while self.running and rclpy.ok():
            try:
                # 用 timeout(0.1s) 兜底，避免 in_waiting 时序问题
                data = self.serial.read(self.serial.in_waiting or 1)
                if data:
                    self.rx_buffer.extend(data)
                    self.process_rx_buffer()
            except Exception as e:
                self.get_logger().error(f'接收数据错误: {e}')
    
    def process_rx_buffer(self):
        """处理接收缓冲区，解析里程计数据"""
        while len(self.rx_buffer) >= 20:  # 里程计帧长度20字节
            # 查找帧头 0xBB 0x66
            if self.rx_buffer[0] != 0xBB or self.rx_buffer[1] != 0x66:
                self.rx_buffer.pop(0)
                continue
            
            # 检查是否有完整帧
            if len(self.rx_buffer) < 20:
                break
            
            # 提取一帧
            frame = self.rx_buffer[:20]
            
            # 验证帧尾
            if frame[19] != 0x0D:
                self.rx_buffer.pop(0)
                continue
            
            # 验证校验和
            checksum_calc = sum(frame[2:18]) & 0xFF
            checksum_recv = frame[18]
            
            if checksum_calc != checksum_recv:
                self.get_logger().warn(
                    f'校验和错误: 计算={checksum_calc}, 接收={checksum_recv}')
                self.rx_buffer.pop(0)
                continue
            
            # 解析数据
            data_type = frame[2]
            if data_type == 0x01:  # 里程计数据
                self.parse_odom_data(frame)
            
            # 移除已处理的帧
            self.rx_buffer = self.rx_buffer[20:]
    
    def parse_odom_data(self, frame):
        """解析里程计数据并发布"""
        # 标记已收到真实里程计数据
        self.received_odom_data = True
        
        # 解析数据 (小端格式)
        pos_x = struct.unpack('<i', frame[3:7])[0]  # mm
        pos_y = struct.unpack('<i', frame[7:11])[0]  # mm
        yaw = struct.unpack('<h', frame[11:13])[0]  # mrad
        linear_vel = struct.unpack('<h', frame[13:15])[0]  # mm/s
        angular_vel = struct.unpack('<h', frame[15:17])[0]  # mrad/s
        
        # 转换单位
        x = pos_x / 1000.0  # mm -> m
        y = pos_y / 1000.0
        theta = yaw / 1000.0  # mrad -> rad
        vx = linear_vel / 1000.0  # mm/s -> m/s
        vth = angular_vel / 1000.0  # mrad/s -> rad/s
        
        # 当前时间
        current_time = self.get_clock().now()
        
        # 发布TF
        if self.publish_tf:
            t = TransformStamped()
            t.header.stamp = current_time.to_msg()
            t.header.frame_id = 'odom'
            t.child_frame_id = 'base_link'
            t.transform.translation.x = x
            t.transform.translation.y = y
            t.transform.translation.z = 0.0
            
            # 四元数
            cy = math.cos(theta / 2.0)
            sy = math.sin(theta / 2.0)
            t.transform.rotation.w = cy
            t.transform.rotation.x = 0.0
            t.transform.rotation.y = 0.0
            t.transform.rotation.z = sy
            
            self.tf_broadcaster.sendTransform(t)
        
        # 发布Odometry消息
        odom = Odometry()
        odom.header.stamp = current_time.to_msg()
        odom.header.frame_id = 'odom'
        odom.child_frame_id = 'base_link'
        
        # 位置
        odom.pose.pose.position.x = x
        odom.pose.pose.position.y = y
        odom.pose.pose.position.z = 0.0
        
        # 姿态（四元数）
        odom.pose.pose.orientation.w = cy
        odom.pose.pose.orientation.x = 0.0
        odom.pose.pose.orientation.y = 0.0
        odom.pose.pose.orientation.z = sy
        
        # 速度
        odom.twist.twist.linear.x = vx
        odom.twist.twist.linear.y = 0.0
        odom.twist.twist.angular.z = vth
        
        self.odom_pub.publish(odom)
        
        self.get_logger().debug(
            f'里程计: x={x:.3f}, y={y:.3f}, yaw={theta:.3f}, '
            f'vx={vx:.3f}, vth={vth:.3f}')
    
    def destroy_node(self):
        """清理资源"""
        self.running = False
        if hasattr(self, 'rx_thread'):
            self.rx_thread.join(timeout=1.0)
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
