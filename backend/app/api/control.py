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
# 加速度限幅（仅对线速度做斜坡滤波，防止启停冲击）
# 角速度不做限幅：前端已有低通滤波+死区，后端再限幅会拉长衰减尾巴导致舵机抖动
# -----------------------------------------------------------------------------
_MAX_LINEAR_ACCEL: float = 2.0    # 线速度最大加速度 (m/s²)
_MAX_ANGULAR_ACCEL: float = 4.0   # 角速度最大加速度 (rad/s²)，兜底防止后端透传突变
_MIN_SEND_INTERVAL: float = 0.02  # 最小发送间隔（秒）

# 当前实际发送的速度（用于加速度限幅计算）
_current_vx: float = 0.0
_current_wz: float = 0.0          # 当前实际发送的角速度
_last_send_time: float = 0.0


def _ramp(current: float, target: float, max_delta: float) -> float:
    """单步加速度限幅：将 current 向 target 靠近，步长不超过 max_delta"""
    delta = target - current
    if abs(delta) <= max_delta:
        return target
    return current + max_delta * (1.0 if delta > 0 else -1.0)


class VelocityCmd(BaseModel):
    linear_x: float = Field(0.0, ge=-ROBOT_MAX_LINEAR_VEL, le=ROBOT_MAX_LINEAR_VEL, description="线速度 m/s")
    linear_y: float = Field(0.0, ge=-ROBOT_MAX_LINEAR_VEL, le=ROBOT_MAX_LINEAR_VEL, description="横向速度 m/s")
    angular_z: float = Field(0.0, ge=-ROBOT_MAX_ANGULAR_VEL, le=ROBOT_MAX_ANGULAR_VEL, description="角速度 rad/s")


class ModeCmd(BaseModel):
    mode: str = Field(..., description="运行模式: manual / auto / navigation")


@router.post("/velocity", summary="发送速度控制指令")
async def set_velocity(cmd: VelocityCmd):
    global _current_vx, _current_wz, _last_send_time

    now = time.monotonic()
    dt = now - _last_send_time if _last_send_time > 0 else _MIN_SEND_INTERVAL
    # 限制 dt 范围，防止长时间未调用后第一次步进过大
    dt = max(_MIN_SEND_INTERVAL, min(dt, 0.5))
    _last_send_time = now

    # 线速度做斜坡限幅（防止启停冲击）
    max_dvx = _MAX_LINEAR_ACCEL * dt
    ramped_vx = _ramp(_current_vx, cmd.linear_x, max_dvx)
    _current_vx = ramped_vx

    # 角速度做斜坡限幅（后端兜底，防止前端异常突变直接冲击舵机）
    max_dwz = _MAX_ANGULAR_ACCEL * dt
    ramped_wz = _ramp(_current_wz, cmd.angular_z, max_dwz)
    _current_wz = ramped_wz
    wz = ramped_wz

    mock_generator.set_velocity(ramped_vx, cmd.linear_y, wz)
    if ros2_bridge.is_enabled:
        ros2_bridge.publish_cmd_vel(ramped_vx, cmd.linear_y, wz)

    return {
        "success": True,
        "data": {
            "linear_x": ramped_vx,
            "linear_y": cmd.linear_y,
            "angular_z": wz,
        }
    }


@router.post("/stop", summary="急停")
async def emergency_stop():
    global _current_vx, _current_wz
    # 急停直接清零，不经过加速度限幅
    _current_vx = 0.0
    _current_wz = 0.0
    mock_generator.emergency_stop()
    if ros2_bridge.is_enabled:
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
        "max_linear_accel": _MAX_LINEAR_ACCEL,
    }
