#!/usr/bin/env python3
"""
阿克曼底盘 SLAM 建图启动文件
硬件配置：RDK S100 + STM32 + Livox Mid-360S激光雷达
底盘类型：阿克曼转向（前轮转向，后轮驱动）
使用方法：ros2 launch czybot_navigation2 ackermann_slam.launch.py
"""

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, LogInfo
from launch.substitutions import LaunchConfiguration, PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def generate_launch_description():
    # 参数声明
    use_sim_time = LaunchConfiguration('use_sim_time')
    slam_params_file = LaunchConfiguration('slam_params_file')
    lidar_port = LaunchConfiguration('lidar_port')
    stm32_port = LaunchConfiguration('stm32_port')
    stm32_baudrate = LaunchConfiguration('stm32_baudrate')
    
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
            'ackermann_slam_params.yaml'
        ]),
        description='Full path to the SLAM parameters file'
    )
    
    declare_lidar_port = DeclareLaunchArgument(
        'lidar_port',
        default_value='/dev/ttyCH343USB0',
        description='LD14P laser serial port'
    )
    
    declare_stm32_port = DeclareLaunchArgument(
        'stm32_port',
        default_value='/dev/ttyUSB0',
        description='STM32 serial port'
    )
    
    declare_stm32_baudrate = DeclareLaunchArgument(
        'stm32_baudrate',
        default_value='9600',
        description='STM32 serial baudrate'
    )
    
    # 1. LD14P 激光雷达驱动节点
    ld14p_node = Node(
        package='ldlidar',
        executable='ldlidar',
        name='ldlidar_publisher',
        output='screen',
        parameters=[{
            'product_name': 'LDLiDAR_LD14P',
            'topic_name': 'scan',
            'port_name': lidar_port,
            'frame_id': 'base_laser',
            'laser_scan_dir': True,  # 逆时针扫描
            'enable_angle_crop_func': False,  # 不裁剪角度
        }],
        respawn=True,
        respawn_delay=2.0
    )
    
    # 2. STM32串口通信桥接节点（发布里程计和TF）
    stm32_bridge_node = Node(
        package='czybot_navigation2',
        executable='stm32_bridge',
        name='stm32_bridge',
        output='screen',
        parameters=[{
            'port': stm32_port,
            'baudrate': stm32_baudrate,
            'publish_tf': True,  # 发布 odom->base_link TF
        }],
        respawn=True,
        respawn_delay=2.0
    )
    
    # 3. SLAM Toolbox 异步建图节点（针对阿克曼底盘优化）
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
    
    # 4. 静态TF：base_link -> base_laser
    # 根据实际雷达安装位置调整xyz参数
    # 假设雷达安装在底盘中心上方10cm处
    static_tf_laser = Node(
        package='tf2_ros',
        executable='static_transform_publisher',
        name='base_to_laser_tf',
        arguments=[
            '0.0', '0.0', '0.1',  # x, y, z (米)
            '0', '0', '0',  # roll, pitch, yaw
            'base_link',
            'base_laser'
        ],
        parameters=[{'use_sim_time': use_sim_time}]
    )
    
    # 5. RViz2 可视化
    rviz_config = PathJoinSubstitution([
        FindPackageShare('czybot_navigation2'),
        'config',
        'ackermann_slam.rviz'
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
        declare_lidar_port,
        declare_stm32_port,
        declare_stm32_baudrate,
        LogInfo(msg='========================================'),
        LogInfo(msg='阿克曼底盘 SLAM 建图系统启动'),
        LogInfo(msg='激光雷达端口: /dev/ttyCH343USB0'),
        LogInfo(msg='STM32端口: /dev/ttyUSB0 (9600)'),
        LogInfo(msg='========================================'),
        ld14p_node,
        stm32_bridge_node,
        static_tf_laser,
        slam_toolbox_node,
        rviz_node,
    ])
