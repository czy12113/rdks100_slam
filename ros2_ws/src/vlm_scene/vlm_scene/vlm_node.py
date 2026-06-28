#!/usr/bin/env python3
"""
vlm_node.py — VLM 场景理解 ROS2 节点
====================================

订阅：
  /camera/camera/color/image_raw           sensor_msgs/Image   原始 RGB 关键帧
  /detection/results                       std_msgs/String     YOLO/DOSOD 检测 JSON

发布：
  /vlm/scene_description                   std_msgs/String     场景描述 JSON
  /vlm/status                              std_msgs/String     节点状态 JSON（启动 / provider / 错误）

ROS2 Service（可选，用于前端手动触发）：
  /vlm/ask                                 std_srvs/Trigger    立刻基于最新一帧做一次推理

整体管线：
  detection_results ──┐
                       ├─ KeyframeSelector.decide() ─ True ─→ provider.describe() ─→ publish
  rgb_image    ──cache┘

设计要点（与项目其它节点一致）：
  - 订阅使用 BEST_EFFORT + depth=1，旧帧 DDS 自动丢；
  - 推理在独立线程内做，避免阻塞 spin；
  - VLM 调用串行 + 节流，永远不会同时发起两个请求。
"""

from __future__ import annotations

import json
import logging
import os
import queue
import threading
import time
from typing import List, Optional, Tuple

import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
from sensor_msgs.msg import Image
from std_msgs.msg import String
try:
    from std_srvs.srv import Trigger
    _HAS_TRIGGER = True
except Exception:
    _HAS_TRIGGER = False

from .providers import create_provider, list_providers, VLMRequest
from .providers.base import Detection
from .utils import KeyframeSelector, ros_image_to_bgr, downsample_keep_aspect


class VLMSceneNode(Node):

    def __init__(self):
        super().__init__("vlm_scene_node")

        # ------------------------------------------------------------------
        # ROS 参数（全部带默认值，可由 config / launch / CLI 覆盖）
        # ------------------------------------------------------------------
        # provider 选择 + 模型名
        self.declare_parameter("provider", "qwen_vl")
        self.declare_parameter("model", "")
        # 订阅 topic
        self.declare_parameter("sub_topic_rgb",       "/camera/camera/color/image_raw")
        self.declare_parameter("sub_topic_detection", "/detection/results")
        # 发布 topic
        self.declare_parameter("pub_topic_description", "/vlm/scene_description")
        self.declare_parameter("pub_topic_status",      "/vlm/status")
        # 节流 / 触发
        self.declare_parameter("cooldown_sec",          3.0)
        self.declare_parameter("heartbeat_sec",        20.0)
        self.declare_parameter("distance_threshold_m",  0.5)
        self.declare_parameter("near_distance_m",       1.0)
        # 输入预处理
        self.declare_parameter("max_image_side",       768)
        self.declare_parameter("min_detections",         1)  # 0 表示无检测也调用 VLM
        self.declare_parameter("max_detections",        10)
        # Prompt
        self.declare_parameter("system_prompt",        "")
        # 网络
        self.declare_parameter("timeout_sec",          20.0)

        self.provider_name      = self.get_parameter("provider").value
        self.model_name         = self.get_parameter("model").value
        self._sub_rgb_topic     = self.get_parameter("sub_topic_rgb").value
        self._sub_det_topic     = self.get_parameter("sub_topic_detection").value
        self._pub_desc_topic    = self.get_parameter("pub_topic_description").value
        self._pub_status_topic  = self.get_parameter("pub_topic_status").value
        self._cooldown          = float(self.get_parameter("cooldown_sec").value)
        self._heartbeat         = float(self.get_parameter("heartbeat_sec").value)
        self._dist_th           = float(self.get_parameter("distance_threshold_m").value)
        self._near_th           = float(self.get_parameter("near_distance_m").value)
        self._max_side          = int(self.get_parameter("max_image_side").value)
        self._min_dets          = int(self.get_parameter("min_detections").value)
        self._max_dets          = int(self.get_parameter("max_detections").value)
        self._system_prompt     = self.get_parameter("system_prompt").value or None
        self._timeout           = float(self.get_parameter("timeout_sec").value)

        # ------------------------------------------------------------------
        # 实例化 Provider
        # ------------------------------------------------------------------
        provider_kwargs = dict(
            model=self.model_name or None,
            timeout=self._timeout,
            max_image_side=self._max_side,
        )
        self._provider = create_provider(self.provider_name, **provider_kwargs)
        self._provider_ready = self._provider.healthcheck()
        self.get_logger().info(
            f"[VLM] provider={self._provider.name} model={self._provider.model} "
            f"ready={self._provider_ready}（可用: {list_providers()}）"
        )

        # ------------------------------------------------------------------
        # 触发器
        # ------------------------------------------------------------------
        self._selector = KeyframeSelector(
            cooldown_sec=self._cooldown,
            heartbeat_sec=self._heartbeat,
            distance_threshold_m=self._dist_th,
            near_distance_m=self._near_th,
        )

        # ------------------------------------------------------------------
        # 双缓冲：最新 RGB 帧 + 最新检测；推理线程消费
        # ------------------------------------------------------------------
        self._lock = threading.Lock()
        self._latest_bgr: Optional[np.ndarray] = None
        self._latest_bgr_ts: float = 0.0
        self._latest_dets: List[Detection] = []
        self._latest_det_ts: float = 0.0
        self._latest_frame_id: int = 0

        # 强制触发标志（service 调用时置位，附带用户自定义 prompt）
        self._force_lock = threading.Lock()
        self._force_pending: Optional[str] = None  # None = 不强制；str = 用户 prompt

        # ------------------------------------------------------------------
        # ROS 通信
        # ------------------------------------------------------------------
        qos_sensor = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            history=HistoryPolicy.KEEP_LAST, depth=1,
        )
        qos_reliable = QoSProfile(
            reliability=ReliabilityPolicy.RELIABLE,
            history=HistoryPolicy.KEEP_LAST, depth=10,
        )

        self.create_subscription(Image,  self._sub_rgb_topic,
                                 self._cb_rgb, qos_sensor)
        self.create_subscription(String, self._sub_det_topic,
                                 self._cb_det, qos_reliable)

        self._pub_desc   = self.create_publisher(String, self._pub_desc_topic, 10)
        self._pub_status = self.create_publisher(String, self._pub_status_topic, 10)

        # 可选 Service：std_srvs/Trigger（无入参，调用后触发一次推理）
        if _HAS_TRIGGER:
            self.create_service(Trigger, "/vlm/ask", self._srv_ask)
            self.get_logger().info("[VLM] /vlm/ask service 已就绪")

        # ------------------------------------------------------------------
        # 推理线程
        # ------------------------------------------------------------------
        self._stop_evt = threading.Event()
        self._thread = threading.Thread(
            target=self._infer_loop, daemon=True, name="vlm_infer",
        )
        self._thread.start()

        # 启动状态广播
        self._publish_status({
            "type": "startup",
            "provider": self._provider.name,
            "model": self._provider.model,
            "ready": self._provider_ready,
            "providers_available": list_providers(),
            "sub": {"rgb": self._sub_rgb_topic, "detection": self._sub_det_topic},
            "pub": {"description": self._pub_desc_topic, "status": self._pub_status_topic},
        })

    # ----------------------------------------------------------------------
    # 订阅回调（在 ROS spin 线程中执行，必须很快返回）
    # ----------------------------------------------------------------------
    def _cb_rgb(self, msg: Image):
        bgr = ros_image_to_bgr(msg)
        if bgr is None:
            return
        ts = msg.header.stamp.sec + msg.header.stamp.nanosec * 1e-9
        with self._lock:
            self._latest_bgr = bgr
            self._latest_bgr_ts = ts

    def _cb_det(self, msg: String):
        try:
            data = json.loads(msg.data)
        except Exception as e:
            self.get_logger().warn(f"[VLM] 解析 detection_results 失败: {e}")
            return
        dets = self._parse_detections(data)
        with self._lock:
            self._latest_dets = dets
            self._latest_det_ts = float(data.get("timestamp", 0.0) or 0.0)
            self._latest_frame_id = int(data.get("frame_id", 0) or 0)

    @staticmethod
    def _parse_detections(payload: dict) -> List[Detection]:
        out: List[Detection] = []
        for d in payload.get("detections", []) or []:
            bbox = d.get("bbox") or {}
            try:
                out.append(Detection(
                    class_id=int(d.get("class_id", -1)),
                    class_name=str(d.get("class_name", "unknown")),
                    confidence=float(d.get("confidence", 0.0)),
                    x1=float(bbox.get("x1", 0.0)),
                    y1=float(bbox.get("y1", 0.0)),
                    x2=float(bbox.get("x2", 0.0)),
                    y2=float(bbox.get("y2", 0.0)),
                    distance_m=float(d.get("distance_m", 0.0) or 0.0),
                ))
            except (TypeError, ValueError):
                continue
        # 高置信度优先
        out.sort(key=lambda x: x.confidence, reverse=True)
        return out

    # ----------------------------------------------------------------------
    # 推理主循环
    # ----------------------------------------------------------------------
    def _infer_loop(self):
        while not self._stop_evt.is_set() and rclpy.ok():
            try:
                self._tick_once()
            except Exception as e:
                self.get_logger().error(f"[VLM] 推理循环异常: {e}")
            # 50ms 节流 + 触发器内部 cooldown 双保险
            self._stop_evt.wait(0.05)

    def _tick_once(self):
        # 1. 取出最新一帧 + 检测
        with self._lock:
            bgr = self._latest_bgr.copy() if self._latest_bgr is not None else None
            dets = list(self._latest_dets)
            frame_id = self._latest_frame_id
            ts = self._latest_bgr_ts
        if bgr is None:
            return  # 还没收到图

        # 2. 检查是否被外部强制触发（service 或 REST）
        with self._force_lock:
            forced_prompt = self._force_pending
            forced = forced_prompt is not None
            self._force_pending = None

        # 3. 判定是否触发
        # 过滤掉低置信度 / 超量
        dets = dets[: self._max_dets]
        if not forced:
            if self._min_dets > 0 and len(dets) < self._min_dets:
                return
        decision = self._selector.decide(dets, force=forced)
        if not decision.fire:
            return

        # 4. 预处理 + 发起 VLM 推理
        small_bgr = downsample_keep_aspect(bgr, self._max_side)
        req = VLMRequest(
            frame_bgr=small_bgr,
            detections=dets,
            user_prompt=forced_prompt,
            system_prompt=self._system_prompt,
            crop_roi=False,
            frame_id=frame_id,
            timestamp=ts,
        )

        self.get_logger().info(
            f"[VLM] 触发推理 reason={decision.reason} dets={len(dets)} "
            f"frame={frame_id} provider={self._provider.name}"
        )

        t0 = time.time()
        try:
            resp = self._provider.describe(req)
        except Exception as e:
            self.get_logger().error(f"[VLM] provider 异常: {e}")
            self._publish_status({"type": "error", "error": str(e)})
            return
        elapsed = (time.time() - t0) * 1000.0

        # 5. 发布场景描述
        out_payload = {
            "timestamp":   time.time(),
            "frame_id":    frame_id,
            "trigger":     decision.reason,
            "provider":    resp.provider or self._provider.name,
            "model":       resp.model or self._provider.model,
            "description": resp.description,
            "per_object":  resp.per_object,
            "elapsed_ms":  round(resp.elapsed_ms or elapsed, 1),
            "tokens_in":   resp.tokens_in,
            "tokens_out":  resp.tokens_out,
            "detections": [
                {
                    "class_id":   d.class_id,
                    "class_name": d.class_name,
                    "confidence": round(d.confidence, 3),
                    "bbox": {"x1": d.x1, "y1": d.y1, "x2": d.x2, "y2": d.y2},
                    "distance_m": d.distance_m,
                }
                for d in dets
            ],
        }
        out_msg = String()
        out_msg.data = json.dumps(out_payload, ensure_ascii=False)
        self._pub_desc.publish(out_msg)
        self._publish_status({
            "type": "infer_ok",
            "elapsed_ms": round(elapsed, 1),
            "provider": self._provider.name,
            "trigger": decision.reason,
        })

    # ----------------------------------------------------------------------
    # 工具
    # ----------------------------------------------------------------------
    def _publish_status(self, payload: dict):
        try:
            payload.setdefault("timestamp", time.time())
            msg = String()
            msg.data = json.dumps(payload, ensure_ascii=False)
            self._pub_status.publish(msg)
        except Exception:
            pass

    def request_force(self, user_prompt: Optional[str] = None):
        """外部调用入口（service / 后端 import 时使用）。"""
        with self._force_lock:
            self._force_pending = user_prompt or ""
        # 顺便重置触发器，避免被 cooldown 卡住
        self._selector.force_reset()

    # ----------------------------------------------------------------------
    # ROS Service
    # ----------------------------------------------------------------------
    def _srv_ask(self, request, response):
        """std_srvs/Trigger：不带参数的手动触发"""
        self.request_force(None)
        response.success = True
        response.message = "VLM 推理请求已排队"
        return response

    # ----------------------------------------------------------------------
    def destroy_node(self):
        self._stop_evt.set()
        try:
            self._thread.join(timeout=1.0)
        except Exception:
            pass
        try:
            self._provider.close()
        except Exception:
            pass
        return super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = VLMSceneNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        try:
            rclpy.shutdown()
        except Exception:
            pass


if __name__ == "__main__":
    main()
