#!/usr/bin/env python3
"""
/scan 时间戳去重节点
问题：pointcloud_to_laserscan 连续多帧 LaserScan 时间戳相同，
     Cartographer 要求时间严格递增，相同时间戳的帧全被丢弃。
方案：只转发时间戳严格大于上一帧的消息，丢弃重复时间戳帧。
"""
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import LaserScan
from rclpy.qos import QoSProfile, ReliabilityPolicy
from builtin_interfaces.msg import Time


def ts_to_ns(t: Time) -> int:
    return t.sec * 1_000_000_000 + t.nanosec


class ScanDedup(Node):
    def __init__(self):
        super().__init__('scan_dedup')
        self._last_ts_ns = 0
        self._dropped = 0
        self._passed = 0

        self._pub = self.create_publisher(LaserScan, '/scan_dedup', 10)

        # 使用 BEST_EFFORT QoS 匹配 pointcloud_to_laserscan 的发布端
        qos = QoSProfile(depth=10, reliability=ReliabilityPolicy.BEST_EFFORT)
        self._sub = self.create_subscription(
            LaserScan, '/scan', self._cb, qos)

        self.create_timer(10.0, self._report)

    def _cb(self, msg: LaserScan):
        ts = ts_to_ns(msg.header.stamp)
        if ts > self._last_ts_ns:
            self._last_ts_ns = ts
            self._passed += 1
            self._pub.publish(msg)
        else:
            self._dropped += 1

    def _report(self):
        self.get_logger().info(
            f'scan_dedup: passed={self._passed} dropped={self._dropped}')


def main():
    rclpy.init()
    node = ScanDedup()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
