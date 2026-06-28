"""
vlm.launch.py
-------------
启动 vlm_scene 节点。可与已经在跑的 d435i_detection / d435i_bringup
独立启动，也可以从主 bringup launch 里 IncludeLaunchDescription 进来。

用法示例：
  # 1) 默认（qwen_vl，需要先 export DASHSCOPE_API_KEY=sk-...）
  ros2 launch vlm_scene vlm.launch.py

  # 2) 离线模板验证
  ros2 launch vlm_scene vlm.launch.py provider:=mock

  # 3) 切到 DeepSeek（仅文本）
  ros2 launch vlm_scene vlm.launch.py provider:=deepseek_text

  # 4) 调用智谱 GLM-4V（通过 openai_vision 兼容通道）
  # 先 export OPENAI_API_KEY=... VLM_OPENAI_BASE_URL=...
  ros2 launch vlm_scene vlm.launch.py provider:=openai_vision

API Key 通过环境变量传入（launch 会自动透传）：
  DASHSCOPE_API_KEY      qwen_vl
  OPENAI_API_KEY         openai_vision
  VLM_OPENAI_BASE_URL    openai_vision endpoint
  VLM_OPENAI_MODEL       openai_vision 模型名
  DEEPSEEK_API_KEY       deepseek_text
  VLM_INTERNVL_MODEL_PATH internvl_local
"""

import os
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, LogInfo
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    provider_arg = DeclareLaunchArgument(
        "provider", default_value="qwen_vl",
        description="VLM provider: qwen_vl / openai_vision / deepseek_text / internvl_local / mock",
    )
    model_arg = DeclareLaunchArgument(
        "model", default_value="",
        description="模型名，留空使用 provider 默认",
    )
    cooldown_arg = DeclareLaunchArgument(
        "cooldown_sec", default_value="3.0",
        description="相邻两次 VLM 推理最小间隔（秒）",
    )
    heartbeat_arg = DeclareLaunchArgument(
        "heartbeat_sec", default_value="20.0",
        description="无变化时多久强制刷新（秒）",
    )

    params_file = PathJoinSubstitution([
        FindPackageShare("vlm_scene"),
        "config",
        "vlm_params.yaml",
    ])

    # 注入 venv site-packages（与 d435i_detection 保持一致），
    # 让节点里 import opencv-python / numpy 不被系统 Python 路径拦截
    _venv_sp = "/home/sunrise/rdks100_slam/backend/venv/lib/python3.10/site-packages"
    _sys_pp = os.environ.get("PYTHONPATH", "")
    _merged_pp = _venv_sp + (":" + _sys_pp if _sys_pp else "")

    vlm_node = Node(
        package="vlm_scene",
        executable="vlm_node",
        name="vlm_scene_node",
        parameters=[
            params_file,
            {
                "provider":      LaunchConfiguration("provider"),
                "model":         LaunchConfiguration("model"),
                "cooldown_sec":  LaunchConfiguration("cooldown_sec"),
                "heartbeat_sec": LaunchConfiguration("heartbeat_sec"),
            },
        ],
        output="screen",
        emulate_tty=True,
        additional_env={"PYTHONPATH": _merged_pp},
    )

    return LaunchDescription([
        provider_arg,
        model_arg,
        cooldown_arg,
        heartbeat_arg,
        LogInfo(msg="[vlm_scene] 启动 VLM 场景理解节点..."),
        vlm_node,
    ])
