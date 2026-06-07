# =============================================================================
# API 路由：SLAM 建图
# =============================================================================

import os
import glob
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from app.core.config import (
    SLAM_ALGORITHMS, SLAM_DEFAULT_ALGORITHM, SLAM_MAP_SAVE_PATH,
)
from app.services.mock_data import mock_generator
from app.services.ros2_bridge import ros2_bridge

router = APIRouter(prefix="/api/slam", tags=["slam"])


class SlamStartCmd(BaseModel):
    algorithm: str = Field(SLAM_DEFAULT_ALGORITHM, description="SLAM 算法名称")


class MapSaveCmd(BaseModel):
    name: str = Field(..., description="地图名称")


class MapLoadCmd(BaseModel):
    path: str = Field(..., description="地图文件路径")


@router.get("/algorithms", summary="获取支持的 SLAM 算法列表")
async def get_algorithms():
    return {"algorithms": SLAM_ALGORITHMS, "default": SLAM_DEFAULT_ALGORITHM}


@router.post("/start", summary="启动 SLAM")
async def start_slam(cmd: SlamStartCmd):
    if cmd.algorithm not in SLAM_ALGORITHMS:
        raise HTTPException(status_code=400, detail=f"不支持的算法: {cmd.algorithm}")
    mock_generator.start_slam(cmd.algorithm)
    return {"success": True, "algorithm": cmd.algorithm, "message": f"SLAM [{cmd.algorithm}] 已启动"}


@router.post("/stop", summary="停止 SLAM")
async def stop_slam():
    mock_generator.stop_slam()
    return {"success": True, "message": "SLAM 已停止"}


@router.get("/status", summary="获取 SLAM 状态")
async def get_slam_status():
    return mock_generator.get_slam_status()


@router.post("/map/save", summary="保存当前地图")
async def save_map(cmd: MapSaveCmd):
    result = await ros2_bridge.call_save_map(cmd.name)
    return result


@router.post("/map/load", summary="加载地图")
async def load_map(cmd: MapLoadCmd):
    result = await ros2_bridge.call_load_map(cmd.path)
    return result


@router.get("/map/list", summary="获取已保存地图列表")
async def list_maps():
    maps = []
    if os.path.exists(SLAM_MAP_SAVE_PATH):
        for f in glob.glob(os.path.join(SLAM_MAP_SAVE_PATH, "*.yaml")):
            stat = os.stat(f)
            maps.append({
                "name": os.path.splitext(os.path.basename(f))[0],
                "path": f,
                "size": stat.st_size,
                "modified": stat.st_mtime,
            })
    else:
        # 模拟地图列表
        maps = [
            {"name": "office_map", "path": f"{SLAM_MAP_SAVE_PATH}/office_map.yaml", "size": 12800, "modified": 1716000000},
            {"name": "lab_map", "path": f"{SLAM_MAP_SAVE_PATH}/lab_map.yaml", "size": 8192, "modified": 1716100000},
        ]
    return {"maps": maps}


@router.delete("/map/{map_name}", summary="删除地图")
async def delete_map(map_name: str):
    yaml_path = os.path.join(SLAM_MAP_SAVE_PATH, f"{map_name}.yaml")
    pgm_path = os.path.join(SLAM_MAP_SAVE_PATH, f"{map_name}.pgm")
    deleted = []
    for p in [yaml_path, pgm_path]:
        if os.path.exists(p):
            os.remove(p)
            deleted.append(p)
    return {"success": True, "deleted": deleted, "message": f"地图 '{map_name}' 已删除"}
