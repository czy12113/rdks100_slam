cmake_minimum_required(VERSION 3.8)
project(czybot_navigation2)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

# find dependencies
find_package(ament_cmake REQUIRED)
# uncomment the following section in order to fill in
# further dependencies manually.
# find_package(<dependency> REQUIRED)

if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  # the following line skips the linter which checks for copyrights
  # comment the line when a copyright and license is added to all source files
  set(ament_cmake_copyright_FOUND TRUE)
  # the following line skips cpplint (only works in a git repo)
  # comment the line when this package is in a git repo and when
  # a copyright and license is added to all source files
  set(ament_cmake_cpplint_FOUND TRUE)
  ament_lint_auto_find_test_dependencies()
endif()

install(DIRECTORY launch maps config scripts behavior_trees
  DESTINATION share/${PROJECT_NAME}
  USE_SOURCE_PERMISSIONS
)

# === 核心节点 ===
install(PROGRAMS scripts/stm32_bridge.py DESTINATION lib/${PROJECT_NAME} RENAME stm32_bridge)
install(PROGRAMS scripts/tjc_hmi_bridge.py DESTINATION lib/${PROJECT_NAME} RENAME tjc_hmi_bridge)
install(PROGRAMS scripts/ackermann_teleop_key.py DESTINATION lib/${PROJECT_NAME} RENAME ackermann_teleop_key)
install(PROGRAMS scripts/ackermann_teleop_key_optimized.py DESTINATION lib/${PROJECT_NAME} RENAME ackermann_teleop_key_optimized)
# === 辅助工具 ===
install(PROGRAMS scripts/fake_odom.py DESTINATION lib/${PROJECT_NAME} RENAME fake_odom)
install(PROGRAMS scripts/tjc_demo_publisher.py DESTINATION lib/${PROJECT_NAME} RENAME tjc_demo_publisher)
install(PROGRAMS scripts/monitor_stm32.py DESTINATION lib/${PROJECT_NAME} RENAME monitor_stm32)
install(PROGRAMS scripts/long_monitor.py DESTINATION lib/${PROJECT_NAME} RENAME long_monitor)
install(PROGRAMS scripts/diagnose_stm32.sh DESTINATION lib/${PROJECT_NAME} RENAME diagnose_stm32)
install(PROGRAMS scripts/verify_chassis.sh DESTINATION lib/${PROJECT_NAME} RENAME verify_chassis)
# === 导航命令行 ===
install(PROGRAMS scripts/send_goal.py DESTINATION lib/${PROJECT_NAME} RENAME send_goal)

ament_package()
