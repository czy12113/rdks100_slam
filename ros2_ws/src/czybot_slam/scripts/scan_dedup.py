#!/usr/bin/env python3
"""
/scan 时间戳去重 + 时间戳修复节点  v2
===========================================
问题根因：
  1. pointcloud_to_laserscan 将点云帧的 header.stamp 原样复制给 LaserScan，
     Livox 驱动在同一扫描周期（100ms）内可能输出多帧时间戳完全相同的点云。
  2. Cartographer sensor_bridge 的 LaserScan 细分逻辑（subdivisions）要求
     每个子扫描时间戳严格单调递增，相同时间戳即触发：
       "Ignored subdivision ... because previous subdivision time X is not
        before current subdivision time X"
  3. 原 v1 的 scan_dedup 只丢弃重复帧，但在帧率高于 10Hz 时（Livox 实际
     输出可能更快），多余帧仍被丢弃，无法解决根本问题。

v2 修复方案（两层保障）：
  Layer 1 — 时间戳强制单调递增：
    若当前帧 stamp ≤ 上一帧 stamp，则将当前帧 stamp 设为
    (上一帧 stamp + 1ms)，而不是直接丢弃。
    这样 Cartographer 始终收到严格递增的时间戳，不再产生警告。

  Layer 2 — 限速保护（可选）：
    若两帧间隔小于 MIN_INTERVAL_NS（默认 80ms = 12.5Hz 上限），
    则丢弃该帧，防止以过高频率向 Cartographer 灌数据拖慢建图。

  统计日志：每 10 秒打印通过/丢弃/时间戳修复的帧数。
"""
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import LaserScan
from rclpy.qos import QoSProfile, ReliabilityPolicy
from builtin_interfaces.msg import Time


def ts_to_ns(t: Time) -> int:
    return t.sec * 1_000_000_000 + t.nanosec


def ns_to_ts(ns: int) -> Time:
    t = Time()
    t.sec = int(ns // 1_000_000_000)
    t.nanosec = int(ns % 1_000_000_000)
    return t


class ScanDedup(Node):
    def __init__(self):
        super().__init__('scan_dedup')

        # 最小帧间隔：80ms（12.5 Hz），防止向 Cartographer 灌入过高频率数据
        # Livox 驱动配置为 10Hz，正常帧间隔约 100ms；
        # 80ms 下限可允许轻微抖动，同时过滤掉同一周期内的多余帧
        self.MIN_INTERVAL_NS = 80_000_000   # 80 ms

        self._last_out_ts_ns = 0   # 上次发布帧的时间戳（纳秒）
        self._dropped = 0
        self._passed = 0
        self._fixed = 0           # 时间戳被修正的帧数

        self._pub = self.create_publisher(LaserScan, '/scan_dedup', 10)

        # BEST_EFFORT QoS 匹配 pointcloud_to_laserscan 发布端
        qos = QoSProfile(depth=10, reliability=ReliabilityPolicy.BEST_EFFORT)
        self._sub = self.create_subscription(
            LaserScan, '/scan', self._cb, qos)

        self.create_timer(10.0, self._report)
        self.get_logger().info(
            'scan_dedup v2 启动：时间戳强制单调递增 + 80ms 最小帧间隔')

    def _cb(self, msg: LaserScan):
        ts = ts_to_ns(msg.header.stamp)

        # ── Layer 2：限速保护 ─────────────────────────────────────────────
        # 若距上次发布不足 MIN_INTERVAL_NS，直接丢弃（避免高频刷爆 Cartographer）
        if self._last_out_ts_ns > 0:
            gap = ts - self._last_out_ts_ns
            # 允许时间戳相同或略小（由 Layer 1 修复），只丢弃明显过快的帧
            # 条件：实际时间差 < 80ms 且 原始时间戳确实比上一帧新（排除同帧重发）
            if gap < self.MIN_INTERVAL_NS and gap > 0:
                self._dropped += 1
                return

        # ── Layer 1：时间戳强制单调递增 ──────────────────────────────────
        # 若 stamp ≤ 上次发布的 stamp，强制设为 (上次 stamp + 1ms)
        if ts <= self._last_out_ts_ns:
            ts = self._last_out_ts_ns + 1_000_000  # +1ms
            msg.header.stamp = ns_to_ts(ts)
            self._fixed += 1

        self._last_out_ts_ns = ts
        self._passed += 1
        self._pub.publish(msg)

    def _report(self):
        self.get_logger().info(
            f'scan_dedup: passed={self._passed} '
            f'dropped={self._dropped} '
            f'fixed={self._fixed}')


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
