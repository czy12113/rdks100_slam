#!/usr/bin/env python3
"""
实物机器人 SLAM 建图启动文件
硬件配置：RDK S100 + Livox Mid-360S 激光雷达
功能：启动雷达驱动和 SLAM 建图节点
使用方法：ros2 launch czybot_navigation2 slam_ld14p.launch.py
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    # 声明参数
    use_sim_time = LaunchConfiguration('use_sim_time')
    slam_params_file = LaunchConfiguration('slam_params_file')
    
    # 参数声明
    declare_use_sim_time = DeclareLaunchArgument(
        'use_sim_time',
        default_value='false',
        description='Use simulation time'
    )
    
    declare_slam_params_file = DeclareLaunchArgument(
        'slam_params_file',
        default_value=PathJoinSubstitution([
            FindPackageShare('czybot_navigation2'),
            'config',
            'slam_toolbox_params.yaml'
        ]),
        description='Full path to the SLAM parameters file'
    )
    
    # LD14P 雷达驱动节点
    # 使用你的 ldlidar_ros2 驱动包
    port_name_arg = DeclareLaunchArgument(
        'port_name',
        default_value='/dev/ttyCH343USB0',  # RDK S100 上 CH343 转串口的默认设备名
        description='LD14P serial port device path'
    )
    
    ld14p_node = Node(
        package='ldlidar',  # 你的驱动包名称
        executable='ldlidar',  # 可执行文件名
        name='ldlidar_publisher_ld14p',
        output='screen',
        parameters=[{
            'product_name': 'LDLiDAR_LD14P',
            'topic_name': 'scan',
            'port_name': LaunchConfiguration('port_name'),
            'frame_id': 'base_laser',  # 驱动包使用的 frame_id
            'laser_scan_dir': True,  # 逆时针扫描
            'enable_angle_crop_func': False,  # 不裁剪角度
            'angle_crop_min': 135.0,
            'angle_crop_max': 225.0,
            'truncated_mode_': 0,
        }]
    )
    
    # SLAM Toolbox 异步建图节点
    slam_toolbox_node = Node(
        package='slam_toolbox',
        executable='async_slam_toolbox_node',
        name='slam_toolbox',
        output='screen',
        parameters=[
            slam_params_file,
            {'use_sim_time': use_sim_time}
        ]
    )
    
    # 静态 TF：base_link -> base_laser
    # 雷达驱动使用 base_laser 作为 frame_id
    # 根据你的雷达安装位置调整 xyz 参数
    static_tf_laser = Node(
        package='tf2_ros',
        executable='static_transform_publisher',
        name='base_to_laser_tf',
        arguments=[
            '0.0', '0.0', '0.1',  # x, y, z (雷达相对于底盘中心的位置，单位：米)
            '0', '0', '0',  # roll, pitch, yaw
            'base_link',
            'base_laser'  # 与驱动包的 frame_id 保持一致
        ],
        parameters=[{'use_sim_time': use_sim_time}]
    )
    
    # 静态 TF：base_footprint -> base_link
    static_tf_base = Node(
        package='tf2_ros',
        executable='static_transform_publisher',
        name='base_footprint_to_base_link',
        arguments=[
            '0', '0', '0',
            '0', '0', '0',
            'base_footprint',
            'base_link'
        ],
        parameters=[{'use_sim_time': use_sim_time}]
    )
    
    # RViz2 可视化
    rviz_config = PathJoinSubstitution([
        FindPackageShare('czybot_navigation2'),
        'config',
        'slam_rviz.rviz'
    ])
    
    rviz_node = Node(
        package='rviz2',
        executable='rviz2',
        name='rviz2',
        arguments=['-d', rviz_config],
        parameters=[{'use_sim_time': use_sim_time}],
        output='screen'
    )
    
    return LaunchDescription([
        declare_use_sim_time,
        declare_slam_params_file,
        port_name_arg,
        ld14p_node,
        static_tf_laser,
        static_tf_base,
        slam_toolbox_node,
        rviz_node,
    ])
