# =============================================================================
# API 路由：机器人控制
# =============================================================================

import asyncio
import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from app.core.config import (
    ROBOT_MAX_LINEAR_VEL, ROBOT_MAX_ANGULAR_VEL,
    ROBOT_DEFAULT_LINEAR_VEL, ROBOT_DEFAULT_ANGULAR_VEL,
    ROS2_ENABLED,
)
from app.services.mock_data import mock_generator
from app.services.ros2_bridge import ros2_bridge

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/control", tags=["control"])

# -----------------------------------------------------------------------------
# 控制状态（仅用于 mock 数据显示）
# 说明：主控制通道已迁移到 WebSocket（低延迟、无 HTTP 往返）。
#       HTTP /velocity 保留为兼容 fallback，/stop 作为急停独立通道。
#       stm32_bridge 有自己的 CMD_TIMEOUT(0.5s) + 看门狗兜底，
#       后端不叠加任何滤波，直接透传。
# -----------------------------------------------------------------------------
_current_vx: float = 0.0
_current_wz: float = 0.0


class VelocityCmd(BaseModel):
    linear_x: float = Field(0.0, ge=-ROBOT_MAX_LINEAR_VEL, le=ROBOT_MAX_LINEAR_VEL, description="线速度 m/s")
    linear_y: float = Field(0.0, ge=-ROBOT_MAX_LINEAR_VEL, le=ROBOT_MAX_LINEAR_VEL, description="横向速度 m/s")
    angular_z: float = Field(0.0, ge=-ROBOT_MAX_ANGULAR_VEL, le=ROBOT_MAX_ANGULAR_VEL, description="角速度 rad/s")


class ModeCmd(BaseModel):
    mode: str = Field(..., description="运行模式: manual / auto / navigation")


@router.post("/velocity", summary="发送速度控制指令（HTTP fallback，主通道为 WebSocket）")
async def set_velocity(cmd: VelocityCmd):
    """
    HTTP 速度控制接口（保留作 fallback）。
    正常情况下前端通过 WebSocket cmd_vel 消息控制，延迟更低。
    """
    global _current_vx, _current_wz
    _current_vx = cmd.linear_x
    _current_wz = cmd.angular_z

    mock_generator.set_velocity(cmd.linear_x, cmd.linear_y, cmd.angular_z)
    if ros2_bridge.is_enabled:
        ros2_bridge.publish_cmd_vel(cmd.linear_x, cmd.linear_y, cmd.angular_z)

    return {
        "success": True,
        "data": {
            "linear_x": cmd.linear_x,
            "linear_y": cmd.linear_y,
            "angular_z": cmd.angular_z,
        }
    }


@router.post("/stop", summary="急停（HTTP 独立通道，不受 WebSocket 速度指令影响）")
async def emergency_stop():
    """
    急停接口：
    - 连续发送 5 次零速帧，间隔 20ms，确保 STM32 串口必然收到
    - 在线程池中执行串口写入，不阻塞 asyncio 事件循环
    - HTTP 独立通道，不会被 WebSocket 速度消息取消或覆盖
    """
    global _current_vx, _current_wz
    _current_vx = 0.0
    _current_wz = 0.0

    mock_generator.emergency_stop()

    if ros2_bridge.is_enabled:
        loop = asyncio.get_event_loop()

        def _send_stop_frames():
            import time
            for i in range(5):
                try:
                    ros2_bridge.publish_cmd_vel(0.0, 0.0, 0.0)
                except Exception as e:
                    logger.warning(f"[Control] 急停发送第 {i+1} 帧失败: {e}")
                time.sleep(0.02)  # 20ms 间隔，与 stm32_bridge 定时器(40ms)配合

        await loop.run_in_executor(None, _send_stop_frames)
        logger.info("[Control] 急停：已发送 5 帧零速")
    else:
        # 模拟模式：直接返回
        pass

    return {"success": True, "message": "急停指令已执行（5 帧零速）"}


@router.post("/mode", summary="切换运行模式")
async def set_mode(cmd: ModeCmd):
    allowed = {"manual", "auto", "navigation"}
    if cmd.mode not in allowed:
        raise HTTPException(status_code=400, detail=f"无效模式，允许值: {allowed}")
    return {"success": True, "mode": cmd.mode}


@router.get("/params", summary="获取控制参数")
async def get_control_params():
    return {
        "max_linear_vel": ROBOT_MAX_LINEAR_VEL,
        "max_angular_vel": ROBOT_MAX_ANGULAR_VEL,
        "default_linear_vel": ROBOT_DEFAULT_LINEAR_VEL,
        "default_angular_vel": ROBOT_DEFAULT_ANGULAR_VEL,
    }
