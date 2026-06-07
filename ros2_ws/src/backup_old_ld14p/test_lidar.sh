#!/bin/bash
# LD14P 雷达测试脚本

echo "========================================="
echo "LD14P 雷达测试"
echo "========================================="
echo ""

# 检查 ROS2 环境
if [ -z "$ROS_DISTRO" ]; then
    echo "正在加载 ROS2 环境..."
    if [ -f "/opt/ros/humble/setup.bash" ]; then
        source /opt/ros/humble/setup.bash
    else
        echo "❌ 找不到 ROS2 环境"
        exit 1
    fi
fi

# 加载工作空间
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
WS_DIR="$( cd "$SCRIPT_DIR/../../.." && pwd )"

if [ -f "$WS_DIR/install/setup.bash" ]; then
    source "$WS_DIR/install/setup.bash"
fi

# 检查设备
echo "1. 检查串口设备..."
echo ""
if ls /dev/ttyCH343USB* 1> /dev/null 2>&1; then
    echo "✓ 找到 CH343 设备:"
    ls -l /dev/ttyCH343USB*
    DEVICE=$(ls /dev/ttyCH343USB* | head -n 1)
elif ls /dev/ttyUSB* 1> /dev/null 2>&1; then
    echo "✓ 找到 USB 设备:"
    ls -l /dev/ttyUSB*
    DEVICE=$(ls /dev/ttyUSB* | head -n 1)
else
    echo "❌ 未找到设备"
    exit 1
fi

echo ""
echo "将使用设备: $DEVICE"
echo ""

# 检查权限
if [ ! -r "$DEVICE" ] || [ ! -w "$DEVICE" ]; then
    echo "⚠️  权限不足，尝试修复..."
    sudo chmod 666 "$DEVICE"
fi

echo "2. 启动雷达驱动..."
echo ""
echo "按 Ctrl+C 停止测试"
echo ""

# 启动雷达
ros2 launch ldlidar ld14p.launch.py port_name:=$DEVICE &
LIDAR_PID=$!

# 等待雷达启动
sleep 3

echo ""
echo "3. 检查雷达话题..."
echo ""

# 检查话题
if ros2 topic list | grep -q "/scan"; then
    echo "✓ 找到 /scan 话题"
    echo ""
    echo "4. 雷达数据频率:"
    timeout 5 ros2 topic hz /scan
    echo ""
    echo "5. 雷达数据示例:"
    ros2 topic echo /scan --once
    echo ""
    echo "========================================="
    echo "✓ 雷达测试成功！"
    echo "========================================="
else
    echo "❌ 未找到 /scan 话题"
    echo ""
    echo "可用话题:"
    ros2 topic list
fi

# 清理
kill $LIDAR_PID 2>/dev/null
