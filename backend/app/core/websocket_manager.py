# =============================================================================
# WebSocket 连接管理器
# 统一管理所有 WebSocket 连接，支持分组广播
# =============================================================================

import asyncio
import json
import logging
from typing import Dict, List, Optional, Set
from fastapi import WebSocket, WebSocketDisconnect
from app.core.config import WS_MAX_CONNECTIONS, WS_HEARTBEAT_INTERVAL

logger = logging.getLogger(__name__)


class ConnectionGroup:
    """WebSocket 连接分组，每个 topic 对应一个分组"""

    def __init__(self, name: str):
        self.name = name
        self.connections: Set[WebSocket] = set()

    async def add(self, ws: WebSocket):
        self.connections.add(ws)
        logger.debug(f"[WS] 客户端加入分组 '{self.name}'，当前连接数: {len(self.connections)}")

    async def remove(self, ws: WebSocket):
        self.connections.discard(ws)
        logger.debug(f"[WS] 客户端离开分组 '{self.name}'，当前连接数: {len(self.connections)}")

    async def broadcast(self, message: dict):
        """向分组内所有连接广播消息
        JSON 序列化在线程池中执行，避免大数据（如点云）阻塞 asyncio 事件循环
        """
        if not self.connections:
            return
        loop = asyncio.get_event_loop()
        # 点云等大数据的 JSON 序列化放到线程池，不阻塞事件循环
        data = await loop.run_in_executor(
            None, lambda: json.dumps(message, ensure_ascii=False)
        )
        dead: List[WebSocket] = []
        for ws in list(self.connections):
            try:
                await ws.send_text(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.connections.discard(ws)

    @property
    def count(self) -> int:
        return len(self.connections)


class WebSocketManager:
    """
    全局 WebSocket 管理器（单例）
    支持按 topic 分组订阅，客户端可订阅多个 topic
    """

    # 预定义 topic 列表
    TOPICS = {
        "system",             # 系统信息（CPU/内存/温度/网络）
        "robot_status",       # 机器人状态（电量/速度/模式）
        "lidar",              # 激光雷达数据
        "imu",                # IMU 姿态数据
        "slam_map",           # SLAM 地图数据
        "slam_pose",          # SLAM 位姿
        "video_rgb",          # RGB 原始视频帧（无标注）
        "video_annotated",    # AI 检测标注图像（带框）
        "video_depth",        # 深度视频帧
        "detection_results",  # YOLO 检测结果 JSON（目标框 + 距离）
        "navigation",         # 导航状态
        "log",                # 实时日志
        "heartbeat",          # 心跳
    }

    def __init__(self):
        # topic -> ConnectionGroup
        self._groups: Dict[str, ConnectionGroup] = {
            topic: ConnectionGroup(topic) for topic in self.TOPICS
        }
        # ws -> 已订阅的 topic 集合
        self._client_topics: Dict[WebSocket, Set[str]] = {}
        self._total_connections: int = 0
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket, topics: Optional[List[str]] = None):
        """接受新连接并订阅指定 topic"""
        async with self._lock:
            if self._total_connections >= WS_MAX_CONNECTIONS:
                await ws.close(code=1008, reason="连接数已达上限")
                return False
            await ws.accept()
            self._total_connections += 1
            self._client_topics[ws] = set()

        # 默认订阅所有 topic
        subscribe_list = topics if topics else list(self.TOPICS)
        for topic in subscribe_list:
            await self.subscribe(ws, topic)

        logger.info(f"[WS] 新连接，总连接数: {self._total_connections}，订阅: {subscribe_list}")
        return True

    async def disconnect(self, ws: WebSocket):
        """断开连接，清理所有订阅"""
        async with self._lock:
            topics = self._client_topics.pop(ws, set())
            self._total_connections = max(0, self._total_connections - 1)

        for topic in topics:
            if topic in self._groups:
                await self._groups[topic].remove(ws)

        logger.info(f"[WS] 连接断开，总连接数: {self._total_connections}")

    async def subscribe(self, ws: WebSocket, topic: str):
        """订阅指定 topic"""
        if topic not in self._groups:
            self._groups[topic] = ConnectionGroup(topic)
        await self._groups[topic].add(ws)
        if ws in self._client_topics:
            self._client_topics[ws].add(topic)

    async def unsubscribe(self, ws: WebSocket, topic: str):
        """取消订阅指定 topic"""
        if topic in self._groups:
            await self._groups[topic].remove(ws)
        if ws in self._client_topics:
            self._client_topics[ws].discard(topic)

    async def broadcast(self, topic: str, data: dict):
        """向指定 topic 的所有订阅者广播消息"""
        if topic not in self._groups:
            return
        message = {"topic": topic, "data": data}
        await self._groups[topic].broadcast(message)

    async def send_to(self, ws: WebSocket, topic: str, data: dict):
        """向单个连接发送消息"""
        try:
            message = {"topic": topic, "data": data}
            await ws.send_text(json.dumps(message, ensure_ascii=False))
        except Exception as e:
            logger.warning(f"[WS] 发送消息失败: {e}")

    async def handle_client_message(self, ws: WebSocket, raw: str):
        """处理客户端发来的消息（订阅/取消订阅/控制指令）"""
        try:
            msg = json.loads(raw)
            action = msg.get("action")
            topic = msg.get("topic")

            if action == "subscribe" and topic:
                await self.subscribe(ws, topic)
                await self.send_to(ws, "system", {"type": "ack", "action": "subscribe", "topic": topic})
            elif action == "unsubscribe" and topic:
                await self.unsubscribe(ws, topic)
                await self.send_to(ws, "system", {"type": "ack", "action": "unsubscribe", "topic": topic})
            elif action == "ping":
                await self.send_to(ws, "heartbeat", {"type": "pong", "ts": msg.get("ts")})
        except json.JSONDecodeError:
            logger.warning(f"[WS] 收到非法消息: {raw[:100]}")

    @property
    def stats(self) -> dict:
        """返回连接统计信息"""
        return {
            "total_connections": self._total_connections,
            "groups": {
                topic: group.count
                for topic, group in self._groups.items()
            }
        }


# 全局单例
ws_manager = WebSocketManager()
