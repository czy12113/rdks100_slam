#!/bin/bash
# 部署脚本：tar 打包 + scp 传输到 RDK S100 设备
# 用法: bash deploy.sh

REMOTE_USER="sunrise"
REMOTE_HOST="10.21.1.145"
REMOTE_PASS="sunrise"
REMOTE_DIR="/home/sunrise/rdks100_slam"
LOCAL_DIR="/home/kkk/rdks100_slam"
TAR_FILE="/tmp/rdks100_slam_deploy.tar.gz"

echo "=== 开始部署到 ${REMOTE_USER}@${REMOTE_HOST} ==="

# 1. 打包（排除 venv 和 node_modules）
echo "[1/3] 正在打包文件..."
tar czf "${TAR_FILE}" \
    --exclude='rdks100_slam/backend/venv' \
    --exclude='rdks100_slam/frontend/node_modules' \
    --exclude='rdks100_slam/.git' \
    --exclude='rdks100_slam/ros2_ws/build' \
    --exclude='rdks100_slam/ros2_ws/install' \
    --exclude='rdks100_slam/ros2_ws/log' \
    --exclude='rdks100_slam/LivoxViewer_2.5.5_Ubuntu' \
    -C /home/kkk rdks100_slam

if [ $? -ne 0 ]; then
    echo "[ERROR] 打包失败！"
    exit 1
fi
echo "[1/3] 打包完成: ${TAR_FILE} ✓"

# 2. scp 上传压缩包
echo "[2/3] 正在上传文件..."
scp -o StrictHostKeyChecking=no "${TAR_FILE}" "${REMOTE_USER}@${REMOTE_HOST}:/tmp/"

if [ $? -ne 0 ]; then
    echo "[ERROR] 上传失败！"
    exit 1
fi
echo "[2/3] 上传完成 ✓"

# 3. 远程解压并设置权限
echo "[3/3] 远程解压并设置权限..."
ssh -o StrictHostKeyChecking=no "${REMOTE_USER}@${REMOTE_HOST}" \
    "mkdir -p ${REMOTE_DIR} && \
     tar xzf /tmp/rdks100_slam_deploy.tar.gz -C /home/sunrise && \
     chmod +x ${REMOTE_DIR}/start.sh && \
     chmod +x ${REMOTE_DIR}/build_ros2_ws.sh && \
     rm /tmp/rdks100_slam_deploy.tar.gz && \
     echo '解压完成'"

if [ $? -ne 0 ]; then
    echo "[ERROR] 远程解压失败！"
    exit 1
fi
echo "[3/3] 远程解压完成 ✓"

# 清理本地临时文件
rm -f "${TAR_FILE}"

echo ""
echo "=== 部署完成 ==="
echo "登录设备启动服务："
echo "  ssh ${REMOTE_USER}@${REMOTE_HOST}"
echo "  cd ${REMOTE_DIR} && ./start.sh prod"
echo ""
echo "浏览器访问: http://${REMOTE_HOST}:8000"
