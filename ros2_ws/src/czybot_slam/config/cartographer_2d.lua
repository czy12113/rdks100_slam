-- Copyright 2016 The Cartographer Authors
--
-- Licensed under the Apache License, Version 2.0 (the "License");
-- you may not use this file except in compliance with the License.
-- You may obtain a copy of the License at
--
--      http://www.apache.org/licenses/LICENSE-2.0
--
-- Unless required by applicable law or agreed to in writing, software
-- distributed under the License is distributed on an "AS IS" BASIS,
-- WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
-- See the License for the specific language governing permissions and
-- limitations under the License.

-- Cartographer 2D SLAM 配置  v2
-- 硬件：RDK S100 + Livox Mid-360S（点云经pointcloud_to_laserscan转为/scan）
--
-- 主要改动（相对 v1）：
--   1. 关闭里程计融合（use_odometry = false）
--      根因：STM32里程计缺少协方差矩阵（全零），Cartographer无法评估置信度，
--      转弯时里程计累积误差直接注入位姿估计，导致地图重影。
--      360S 360° 全向扫描匹配精度足够，无需里程计辅助也能建出好图。
--      后续若 STM32 固件提供带协方差的 /odom，再将 use_odometry 改回 true，
--      同时在 stm32_bridge.py 填充 pose_covariance 和 twist_covariance。
--
--   2. provide_odom_frame = true（Cartographer 自己维护 odom 帧）
--      关闭里程计后不再依赖 STM32 odom，Cartographer 内部提供连续里程帧，
--      避免 map→odom TF 断链。
--
--   3. published_frame 改为 "base_link"
--      无外部 odom 时，Cartographer 直接发布 map→base_link，TF树更简洁。
--
--   4. 运动滤波器角度阈值从 5° 收紧到 1.5°
--      原 5° 导致转弯过程中大量中间帧被丢弃，角度跳变产生重影。
--
--   5. 在线相关性扫描匹配角度搜索窗口从 20° 扩大到 30°
--      对应转弯场景，保证大角速度时仍能找到最优匹配。
--
--   6. Ceres 扫描匹配旋转权重从 40 提升到 100
--      增强旋转约束，减少转弯时的角度漂移。
--
--   7. 子图帧数从 120 减少到 80
--      更快完成子图，提高回环检测频率，改善转弯后的地图一致性。
--
--   8. 位姿图优化频率从每 90 节点一次改为每 50 节点一次
--      更频繁的全局优化可更快纠正转弯累积误差。
--
-- ⚠️ 雷达前倾安装说明（pitch=-40°）：
--   base_link→livox_frame 的静态TF已加入 pitch=-40° 旋转补偿
--   pointcloud_to_laserscan 在 base_link 坐标系下做切片，
--   min_height=-1.5m / max_height=1.2m 覆盖前倾后的点云高度范围
--   Cartographer 2D 接收的 /scan_dedup 已是正确补偿后的扫描数据

include "map_builder.lua"
include "trajectory_builder.lua"

options = {
  map_builder = MAP_BUILDER,
  trajectory_builder = TRAJECTORY_BUILDER,
  map_frame = "map",
  tracking_frame = "base_link",      -- 跟踪坐标系（底盘中心）
  published_frame = "base_link",     -- 直接发布 map→base_link（无外部odom时更稳定）
  odom_frame = "odom",
  provide_odom_frame = true,         -- Cartographer自己维护odom帧，保持TF树完整
  publish_frame_projected_to_2d = true,
  use_pose_extrapolator = true,
  use_odometry = false,              -- ⚠️ 关闭外部里程计：STM32里程计无协方差，
                                     --   融入后转弯会引入累积误差导致重影。
                                     --   360S 全向扫描匹配足以独立建图。
  use_nav_sat = false,
  use_landmarks = false,
  num_laser_scans = 1,               -- 单个2D激光扫描输入（来自点云转换）
  num_multi_echo_laser_scans = 0,
  num_subdivisions_per_laser_scan = 1,  -- 不细分扫描帧，避免时间戳问题
  num_point_clouds = 0,              -- 2D模式不直接使用点云
  lookup_transform_timeout_sec = 0.3,
  submap_publish_period_sec = 0.5,   -- 子图发布 2Hz，减少RViz2重绘
  pose_publish_period_sec = 50e-3,   -- 位姿发布 20Hz
  trajectory_publish_period_sec = 50e-3,
  rangefinder_sampling_ratio = 1.,
  odometry_sampling_ratio = 1.,
  fixed_frame_pose_sampling_ratio = 1.,
  imu_sampling_ratio = 1.,
  landmarks_sampling_ratio = 1.,
}

-- 2D SLAM
MAP_BUILDER.use_trajectory_builder_2d = true

-- ============================================================
-- 轨迹构建器 2D 参数
-- Livox Mid-360S 规格：
--   水平FOV 360°，垂直FOV -7°~52°
--   测量范围 0.1m ~ 40m（室内有效约30m）
--   点频约 200,000点/秒
-- ============================================================
TRAJECTORY_BUILDER_2D.use_imu_data = false       -- 不使用IMU（360S内置IMU但不接入此处）
TRAJECTORY_BUILDER_2D.min_range = 0.1            -- 最小测距（360S最近0.1m）
TRAJECTORY_BUILDER_2D.max_range = 25.0           -- 室内有效范围25m
TRAJECTORY_BUILDER_2D.missing_data_ray_length = 5.0

-- 在线相关性扫描匹配（实时性好，对大角度转弯适应性更强）
TRAJECTORY_BUILDER_2D.use_online_correlative_scan_matching = true
TRAJECTORY_BUILDER_2D.real_time_correlative_scan_matcher.linear_search_window = 0.15
TRAJECTORY_BUILDER_2D.real_time_correlative_scan_matcher.angular_search_window = math.rad(30.)  -- 扩大到30°，适应快速转弯
TRAJECTORY_BUILDER_2D.real_time_correlative_scan_matcher.translation_delta_cost_weight = 10.
TRAJECTORY_BUILDER_2D.real_time_correlative_scan_matcher.rotation_delta_cost_weight = 1e-1

-- Ceres 精细扫描匹配（增强旋转约束）
TRAJECTORY_BUILDER_2D.ceres_scan_matcher.occupied_space_weight = 1.
TRAJECTORY_BUILDER_2D.ceres_scan_matcher.translation_weight = 10.
TRAJECTORY_BUILDER_2D.ceres_scan_matcher.rotation_weight = 100.    -- 从40提升到100，减少转弯角度漂移
TRAJECTORY_BUILDER_2D.ceres_scan_matcher.ceres_solver_options.use_nonmonotonic_steps = false
TRAJECTORY_BUILDER_2D.ceres_scan_matcher.ceres_solver_options.max_num_iterations = 20
TRAJECTORY_BUILDER_2D.ceres_scan_matcher.ceres_solver_options.num_threads = 2

-- 运动滤波器（收紧角度阈值，防止转弯时帧跳变导致重影）
TRAJECTORY_BUILDER_2D.motion_filter.max_time_seconds = 0.5
TRAJECTORY_BUILDER_2D.motion_filter.max_distance_meters = 0.1   -- 10cm移动才处理
TRAJECTORY_BUILDER_2D.motion_filter.max_angle_radians = math.rad(1.5)  -- 从5°收紧到1.5°，捕获转弯细节

-- 子图参数（减少每子图帧数，提高回环检测频率）
TRAJECTORY_BUILDER_2D.submaps.num_range_data = 80              -- 从120减少到80
TRAJECTORY_BUILDER_2D.submaps.grid_options_2d.grid_type = "PROBABILITY_GRID"
TRAJECTORY_BUILDER_2D.submaps.grid_options_2d.resolution = 0.05  -- 5cm分辨率
TRAJECTORY_BUILDER_2D.submaps.range_data_inserter.probability_grid_range_data_inserter.insert_free_space = true
TRAJECTORY_BUILDER_2D.submaps.range_data_inserter.probability_grid_range_data_inserter.hit_probability = 0.55
TRAJECTORY_BUILDER_2D.submaps.range_data_inserter.probability_grid_range_data_inserter.miss_probability = 0.49

-- ============================================================
-- 位姿图优化（更频繁优化以快速纠正转弯误差）
-- ============================================================
POSE_GRAPH.optimize_every_n_nodes = 50             -- 从90减少到50，更频繁全局优化
POSE_GRAPH.constraint_builder.min_score = 0.55
POSE_GRAPH.constraint_builder.global_localization_min_score = 0.6
POSE_GRAPH.optimization_problem.huber_scale = 1e1
POSE_GRAPH.optimization_problem.acceleration_weight = 1e3
POSE_GRAPH.optimization_problem.rotation_weight = 3e5
POSE_GRAPH.constraint_builder.max_constraint_distance = 15.
POSE_GRAPH.constraint_builder.sampling_ratio = 0.3
POSE_GRAPH.constraint_builder.fast_correlative_scan_matcher.linear_search_window = 7.
POSE_GRAPH.constraint_builder.fast_correlative_scan_matcher.angular_search_window = math.rad(30.)
POSE_GRAPH.constraint_builder.fast_correlative_scan_matcher.branch_and_bound_depth = 7
POSE_GRAPH.constraint_builder.ceres_scan_matcher.occupied_space_weight = 20.
POSE_GRAPH.constraint_builder.ceres_scan_matcher.translation_weight = 10.
POSE_GRAPH.constraint_builder.ceres_scan_matcher.rotation_weight = 1.
POSE_GRAPH.constraint_builder.ceres_scan_matcher.ceres_solver_options.use_nonmonotonic_steps = true
POSE_GRAPH.constraint_builder.ceres_scan_matcher.ceres_solver_options.max_num_iterations = 10
POSE_GRAPH.constraint_builder.ceres_scan_matcher.ceres_solver_options.num_threads = 2

return options
