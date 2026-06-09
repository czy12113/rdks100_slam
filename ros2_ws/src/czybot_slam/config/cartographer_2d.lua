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

-- Cartographer 2D SLAM 配置
-- 硬件：RDK S100 + Livox Mid-360S（点云经pointcloud_to_laserscan转为/scan）
-- 特点：纯激光扫描匹配建图，不依赖里程计（STM32固件静止时不发odom帧）
-- 后续STM32固件改为固定频率发送里程计后，可将 use_odometry 改回 true

include "map_builder.lua"
include "trajectory_builder.lua"

options = {
  map_builder = MAP_BUILDER,
  trajectory_builder = TRAJECTORY_BUILDER,
  map_frame = "map",
  tracking_frame = "base_link",      -- 跟踪坐标系（底盘中心）
  published_frame = "odom",          -- STM32提供odom帧，Cartographer发布 map->odom
  odom_frame = "odom",
  provide_odom_frame = false,        -- odom由STM32提供，Cartographer不自己生成
  publish_frame_projected_to_2d = true,
  use_pose_extrapolator = true,
  use_odometry = true,               -- 启用里程计融合（STM32固定频率发布/odom）
  use_nav_sat = false,
  use_landmarks = false,
  num_laser_scans = 1,               -- 单个2D激光扫描输入（来自点云转换）
  num_multi_echo_laser_scans = 0,
  num_subdivisions_per_laser_scan = 1,
  num_point_clouds = 0,              -- 2D模式不直接使用点云
  lookup_transform_timeout_sec = 0.3,
  submap_publish_period_sec = 0.3,
  pose_publish_period_sec = 5e-3,    -- 200Hz位姿发布
  trajectory_publish_period_sec = 30e-3,
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

-- 在线相关性扫描匹配（实时性好）
TRAJECTORY_BUILDER_2D.use_online_correlative_scan_matching = true
TRAJECTORY_BUILDER_2D.real_time_correlative_scan_matcher.linear_search_window = 0.1
TRAJECTORY_BUILDER_2D.real_time_correlative_scan_matcher.angular_search_window = math.rad(20.)
TRAJECTORY_BUILDER_2D.real_time_correlative_scan_matcher.translation_delta_cost_weight = 10.
TRAJECTORY_BUILDER_2D.real_time_correlative_scan_matcher.rotation_delta_cost_weight = 1e-1

-- Ceres 精细扫描匹配
TRAJECTORY_BUILDER_2D.ceres_scan_matcher.occupied_space_weight = 1.
TRAJECTORY_BUILDER_2D.ceres_scan_matcher.translation_weight = 10.
TRAJECTORY_BUILDER_2D.ceres_scan_matcher.rotation_weight = 40.
TRAJECTORY_BUILDER_2D.ceres_scan_matcher.ceres_solver_options.use_nonmonotonic_steps = false
TRAJECTORY_BUILDER_2D.ceres_scan_matcher.ceres_solver_options.max_num_iterations = 20
TRAJECTORY_BUILDER_2D.ceres_scan_matcher.ceres_solver_options.num_threads = 2

-- 运动滤波器（小车移动场景：阈值稍大，减少CPU负载）
TRAJECTORY_BUILDER_2D.motion_filter.max_time_seconds = 0.5
TRAJECTORY_BUILDER_2D.motion_filter.max_distance_meters = 0.1   -- 10cm移动才处理
TRAJECTORY_BUILDER_2D.motion_filter.max_angle_radians = math.rad(5.)

-- 子图参数（360S点密度高，适当增加每子图帧数）
TRAJECTORY_BUILDER_2D.submaps.num_range_data = 120
TRAJECTORY_BUILDER_2D.submaps.grid_options_2d.grid_type = "PROBABILITY_GRID"
TRAJECTORY_BUILDER_2D.submaps.grid_options_2d.resolution = 0.05  -- 5cm分辨率
TRAJECTORY_BUILDER_2D.submaps.range_data_inserter.probability_grid_range_data_inserter.insert_free_space = true
TRAJECTORY_BUILDER_2D.submaps.range_data_inserter.probability_grid_range_data_inserter.hit_probability = 0.55
TRAJECTORY_BUILDER_2D.submaps.range_data_inserter.probability_grid_range_data_inserter.miss_probability = 0.49

-- ============================================================
-- 位姿图优化
-- ============================================================
POSE_GRAPH.optimize_every_n_nodes = 90
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
