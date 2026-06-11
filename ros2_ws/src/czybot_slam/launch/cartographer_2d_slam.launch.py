#!/usr/bin/env python3
"""
Cartographer 2D SLAM 建图主启动文件
硬件：RDK S100 + Livox Mid-360S + STM32底盘

数据流：
  Mid-360S ──→ /livox/lidar (PointCloud2)
                     │
                     ▼
       pointcloud_to_laserscan
                     │
                     ▼
              /scan (LaserScan)
                     │
                     ▼
          cartographer_node (2D SLAM)
                     │
                     ▼
     /map + /tf(map→odom) + /submap_list

TF 树：
  map → odom (由Cartographer发布)
  odom → base_link (由STM32底盘stm32_bridge发布)
  base_link → livox_frame (静态TF，本文件发布)

启动时序：
  t=0s   STM32桥接 + 静态TF
  t=3s   Livox Mid-360S 驱动
  t=5s   pointcloud_to_laserscan
  t=7s   Cartographer 建图节点
  t=8s   Cartographer 地图发布节点
  t=9s   RViz2（此时/map和/scan都已就绪，打开即可见建图效果）

用法：
  ros2 launch czybot_slam cartographer_2d_slam.launch.py
  ros2 launch czybot_slam cartographer_2d_slam.launch.py use_rviz:=false
  ros2 launch czybot_slam cartographer_2d_slam.launch.py stm32_port:=/dev/ttyUSB1
"""

import os
from launch import LaunchDescription
from launch.actions import (
    DeclareLaunchArgument,
    TimerAction,
    LogInfo,
)
from launch.conditions import IfCondition
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from ament_index_python.packages import get_package_share_directory


def generate_launch_description():

    # ─── 包路径 ────────────────────────────────────────────────
    czybot_slam_dir = get_package_share_directory('czybot_slam')
    livox_driver_dir = get_package_share_directory('livox_ros_driver2')

    # ─── Launch 参数声明 ───────────────────────────────────────
    declare_use_sim_time = DeclareLaunchArgument(
        'use_sim_time',
        default_value='false',
        description='是否使用仿真时钟'
    )

    declare_use_rviz = DeclareLaunchArgument(
        'use_rviz',
        default_value='true',
        description='是否启动RViz2可视化（默认开启，打开即可见建图效果）'
    )

    declare_stm32_port = DeclareLaunchArgument(
        'stm32_port',
        default_value='/dev/ttyUSB0',
        description='STM32底盘串口（若不存在自动探测ttyUSB0/1/2）'
    )

    declare_stm32_baudrate = DeclareLaunchArgument(
        'stm32_baudrate',
        default_value='115200',
        description='STM32底盘串口波特率'
    )

    declare_resolution = DeclareLaunchArgument(
        'resolution',
        default_value='0.05',
        description='占据栅格地图分辨率(m)'
    )

    declare_publish_period = DeclareLaunchArgument(
        'publish_period_sec',
        default_value='1.0',
        description='地图发布周期(秒)'
    )

    # ─── LaunchConfiguration 引用 ─────────────────────────────
    use_sim_time      = LaunchConfiguration('use_sim_time')
    use_rviz          = LaunchConfiguration('use_rviz')
    stm32_port        = LaunchConfiguration('stm32_port')
    stm32_baudrate    = LaunchConfiguration('stm32_baudrate')
    resolution        = LaunchConfiguration('resolution')
    publish_period_sec = LaunchConfiguration('publish_period_sec')

    # ─── 节点定义 ──────────────────────────────────────────────

    # 1. STM32 底盘桥接（立即启动）
    # 发布：/odom、TF(odom→base_link)；订阅：/cmd_vel
    stm32_bridge_node = Node(
        package='czybot_navigation2',
        executable='stm32_bridge',
        name='stm32_bridge',
        output='screen',
        parameters=[{
            'port': stm32_port,
            'baudrate': stm32_baudrate,
            'publish_tf': True,
        }]
    )

    # 2. 静态TF：base_link → livox_frame（立即发布）
    # 360S安装在车体中心正上方，高度约15cm
    # ⚠️ 雷达实际安装前倾约40°（绕Y轴旋转 pitch=-40°）
    # 四元数计算：pitch=-40° → qx=0, qy=sin(-20°)=-0.342, qz=0, qw=cos(-20°)=0.940
    # 若前倾角度有变化，请用以下公式重新计算：
    #   qy = sin(pitch/2), qw = cos(pitch/2)，pitch 单位为弧度，前倾为负值
    static_tf_base_to_livox = Node(
        package='tf2_ros',
        executable='static_transform_publisher',
        name='static_tf_base_to_livox',
        arguments=[
            '0.0', '0.0', '0.15',              # x y z：360S相对base_link的安装位置（米）
            '0.0', '-0.342', '0.0', '0.940',   # qx qy qz qw：前倾40°（pitch=-40°）
            'base_link',
            'livox_frame'
        ],
        output='screen'
    )

    # 3. Livox Mid-360S 驱动（t=3s）
    livox_config_path = os.path.join(livox_driver_dir, 'config', 'MID360s_config.json')

    livox_driver_node = Node(
        package='livox_ros_driver2',
        executable='livox_ros_driver2_node',
        name='livox_lidar_publisher',
        output='screen',
        parameters=[{
            'xfer_format': 0,         # 0=PointXYZRTL，与pointcloud_to_laserscan兼容
            'multi_topic': 0,         # 0=所有雷达共享同一话题
            'data_src': 0,            # 0=实体雷达
            'publish_freq': 10.0,     # 10Hz，Cartographer推荐频率
            'output_data_type': 0,
            'frame_id': 'livox_frame',
            'use_sim_time': use_sim_time,
            'user_config_path': livox_config_path,
        }]
    )

    # 4. PointCloud2 → LaserScan 转换（t=5s）
    # 将360S的3D点云水平切片，生成/scan供Cartographer 2D使用
    pointcloud_to_laserscan_node = Node(
        package='pointcloud_to_laserscan',
        executable='pointcloud_to_laserscan_node',
        name='pointcloud_to_laserscan',
        output='screen',
        parameters=[
            os.path.join(czybot_slam_dir, 'config', 'pointcloud_to_laserscan.yaml'),
            {'use_sim_time': use_sim_time}
        ],
        remappings=[
            ('cloud_in', '/livox/lidar'),
            ('scan',     '/scan'),
        ]
    )

    # 4.5. Scan 时间戳去重节点（t=5.5s）
    # 丢弃时间戳重复的 LaserScan 帧，发布到 /scan_dedup
    # 使用 BEST_EFFORT QoS 匹配 pointcloud_to_laserscan 发布端
    scan_dedup_node = Node(
        package='czybot_slam',
        executable='scan_dedup.py',
        name='scan_dedup',
        output='screen',
    )

    # 5. Cartographer 2D 建图节点（t=7s）
    cartographer_config_dir = os.path.join(czybot_slam_dir, 'config')

    cartographer_node = Node(
        package='cartographer_ros',
        executable='cartographer_node',
        name='cartographer_node',
        output='screen',
        parameters=[{'use_sim_time': use_sim_time}],
        arguments=[
            '-configuration_directory', cartographer_config_dir,
            '-configuration_basename', 'cartographer_2d.lua',
        ],
        remappings=[
            ('scan', '/scan_dedup'),
            ('odom', '/odom'),
        ]
    )

    # 6. Cartographer 占据栅格地图发布节点（t=8s）
    occupancy_grid_node = Node(
        package='cartographer_ros',
        executable='cartographer_occupancy_grid_node',
        name='cartographer_occupancy_grid_node',
        output='screen',
        parameters=[
            {'use_sim_time': use_sim_time},
            {'resolution': resolution},
        ],
        arguments=[
            '-resolution', resolution,
            '-publish_period_sec', publish_period_sec,
        ]
    )

    # 7. RViz2 可视化（t=9s，等待/map和/scan话题就绪后再启动）
    # 使用预配置的slam_2d.rviz：包含Map、LaserScan、SubmapList、PointCloud2、Odometry、TF
    # 打开即可看到建图效果，无需手动添加显示项
    rviz_config = os.path.join(czybot_slam_dir, 'rviz', 'slam_2d.rviz')

    rviz_node = Node(
        package='rviz2',
        executable='rviz2',
        name='rviz2',
        output='screen',
        arguments=['-d', rviz_config],
        parameters=[{'use_sim_time': use_sim_time}],
        condition=IfCondition(use_rviz)
    )

    # ─── 组装 LaunchDescription（按时序延迟启动）────────────────
    return LaunchDescription([
        # 参数声明
        declare_use_sim_time,
        declare_use_rviz,
        declare_stm32_port,
        declare_stm32_baudrate,
        declare_resolution,
        declare_publish_period,

        # 启动提示
        LogInfo(msg='[czybot_slam] 启动 Cartographer 2D SLAM...'),
        LogInfo(msg='[czybot_slam] 硬件: RDK S100 + Livox Mid-360S + STM32底盘'),
        LogInfo(msg='[czybot_slam] RViz2 将在9秒后自动打开（/map和/scan就绪后）'),
        LogInfo(msg='[czybot_slam] 建图完成后执行: bash ~/rdks100_slam/ros2_ws/src/czybot_slam/scripts/save_map.sh'),

        # t=0s：STM32桥接 + 静态TF
        stm32_bridge_node,
        static_tf_base_to_livox,

        # t=3s：Livox驱动
        TimerAction(period=3.0, actions=[livox_driver_node]),

        # t=5s：点云转激光扫描
        TimerAction(period=5.0, actions=[pointcloud_to_laserscan_node]),

        # t=5.5s：扫描时间戳去重
        TimerAction(period=5.5, actions=[scan_dedup_node]),

        # t=7s：Cartographer建图
        TimerAction(period=7.0, actions=[cartographer_node]),

        # t=8s：地图栅格发布
        TimerAction(period=8.0, actions=[occupancy_grid_node]),

        # t=9s：RViz2（此时/map、/scan、/submap_list均已就绪）
        TimerAction(period=9.0, actions=[rviz_node]),
    ])
