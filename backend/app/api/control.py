# =============================================================================
# API 路由：机器人控制
# =============================================================================

import time
import asyncio
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from app.core.config import (
    ROBOT_MAX_LINEAR_VEL, ROBOT_MAX_ANGULAR_VEL,
    ROBOT_DEFAULT_LINEAR_VEL, ROBOT_DEFAULT_ANGULAR_VEL,
    ROS2_ENABLED,
)
from app.services.mock_data import mock_generator
from app.services.ros2_bridge import ros2_bridge

router = APIRouter(prefix="/api/control", tags=["control"])

# -----------------------------------------------------------------------------
# 控制状态（仅用于 mock 数据显示，不再做任何速度滤波/限幅）
# 说明：前端已有低通滤波 + 死区处理，stm32_bridge 也有节流 + 超时保护，
#       后端不应再叠加任何滤波，否则双重延迟导致响应卡顿、松键不停车。
# -----------------------------------------------------------------------------
_current_vx: float = 0.0
_current_wz: float = 0.0


class VelocityCmd(BaseModel):
    linear_x: float = Field(0.0, ge=-ROBOT_MAX_LINEAR_VEL, le=ROBOT_MAX_LINEAR_VEL, description="线速度 m/s")
    linear_y: float = Field(0.0, ge=-ROBOT_MAX_LINEAR_VEL, le=ROBOT_MAX_LINEAR_VEL, description="横向速度 m/s")
    angular_z: float = Field(0.0, ge=-ROBOT_MAX_ANGULAR_VEL, le=ROBOT_MAX_ANGULAR_VEL, description="角速度 rad/s")


class ModeCmd(BaseModel):
    mode: str = Field(..., description="运行模式: manual / auto / navigation")


@router.post("/velocity", summary="发送速度控制指令")
async def set_velocity(cmd: VelocityCmd):
    global _current_vx, _current_wz

    # 直接透传，不做任何斜坡/低通滤波
    # 前端负责平滑，stm32_bridge 负责节流和超时停车
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


@router.post("/stop", summary="急停")
async def emergency_stop():
    global _current_vx, _current_wz
    _current_vx = 0.0
    _current_wz = 0.0

    mock_generator.emergency_stop()

    # 急停：连续发送 3 次零速，确保 STM32 收到
    if ros2_bridge.is_enabled:
        for _ in range(3):
            ros2_bridge.publish_cmd_vel(0.0, 0.0, 0.0)

    return {"success": True, "message": "急停指令已执行"}


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
