# STM32 诊断结果分析

## 诊断输出解读

```
[3/5] 向 /dev/ttyUSB0 发送速度命令并监听响应...
  ✓ 收到STM32响应:
    00000000: 0000 0000 0000 0000 0000 0000 0000 0000  ................
```

**关键发现：** STM32 持续发送 `0x00` 字节流，这是**典型的串口接线错误**或**设备插反**的症状。

---

## 根本原因

### 可能性1：USB转TTL插反了（最可能）⚠️

**症状：**
- 发送命令后收到全 `00` 字节
- 持续收到 `00` 字节流

**原因：**
- `/dev/ttyUSB0` 实际连接的是 **TJC串口屏**
- `/dev/ttyUSB1` 实际连接的是 **STM32**

**证据：**
```
/dev/ttyUSB0: idVendor=1a86, idProduct=7523 (CH340芯片)
/dev/ttyUSB1: idVendor=10c4, idProduct=ea60 (CP2102芯片)
```

TJC串口屏在空闲时会持续发送 `0x00`，这正是你看到的现象。

---

## 解决方案

### 方案A：交换物理连接（推荐）

1. **拔掉两根USB转TTL线**
2. **交换连接：**
   - 原来插在 ttyUSB0 的线 → 插到另一个USB口（变成 ttyUSB1）
   - 原来插在 ttyUSB1 的线 → 插到另一个USB口（变成 ttyUSB0）
3. **重新测试：**
   ```bash
   bash diagnose_stm32.sh
   ```

### 方案B：修改ROS配置文件（如果不想换线）

如果确认：
- ttyUSB0 = TJC串口屏
- ttyUSB1 = STM32

则修改配置：

**修改 [`tjc_hmi_params.yaml`](config/tjc_hmi_params.yaml)：**
```yaml
tjc_hmi_bridge:
  ros__parameters:
    port: '/dev/ttyUSB0'  # 改为 ttyUSB0
    baudrate: 115200
```

**修改 STM32 启动参数（在 launch 文件中）：**
```python
# 在 robot_with_hmi.launch.py 或相关文件中
stm32_node = Node(
    package='czybot_navigation2',
    executable='stm32_bridge.py',
    parameters=[{
        'port': '/dev/ttyUSB1',  # 改为 ttyUSB1
        'baudrate': 115200
    }]
)
```

---

## 验证步骤

### 1. 先确认哪个是STM32

```bash
# 测试 ttyUSB1 是否是STM32
stty -F /dev/ttyUSB1 115200 raw
printf '\xAA\x55\x01\xC8\x00\x00\x00\xC9\x0D' > /dev/ttyUSB1
timeout 2 cat /dev/ttyUSB1 | xxd
```

**期望结果：**
- 如果是STM32：收到 `BB 66 01 ...` 开头的里程计数据
- 如果是TJC：收到全 `00` 或 `FF FF FF`

### 2. 测试另一个端口

```bash
# 测试 ttyUSB0
stty -F /dev/ttyUSB0 115200 raw
printf '\xAA\x55\x01\xC8\x00\x00\x00\xC9\x0D' > /dev/ttyUSB0
timeout 2 cat /dev/ttyUSB0 | xxd
```

### 3. 确认后重新配置

根据测试结果，使用方案A或方案B。

---

## 其他可能原因（如果交换后仍无效）

### 原因2：STM32固件未运行
- 检查STM32电源指示灯
- 重新烧录固件
- 检查固件串口初始化代码

### 原因3：波特率不匹配
- STM32固件波特率不是115200
- 尝试其他波特率：9600, 57600, 230400

### 原因4：协议格式不匹配
- STM32固件期望的帧格式与 [`stm32_bridge.py:111`](../scripts/stm32_bridge.py:111) 不一致
- 需要查看STM32固件源码确认协议

---

## 快速测试脚本

```bash
#!/bin/bash
# 快速确认哪个是STM32

echo "测试 ttyUSB0..."
stty -F /dev/ttyUSB0 115200 raw 2>/dev/null
printf '\xAA\x55\x01\xC8\x00\x00\x00\xC9\x0D' > /dev/ttyUSB0
DATA0=$(timeout 1 cat /dev/ttyUSB0 | xxd | head -3)

echo "测试 ttyUSB1..."
stty -F /dev/ttyUSB1 115200 raw 2>/dev/null
printf '\xAA\x55\x01\xC8\x00\x00\x00\xC9\x0D' > /dev/ttyUSB1
DATA1=$(timeout 1 cat /dev/ttyUSB1 | xxd | head -3)

echo "=== ttyUSB0 响应 ==="
echo "$DATA0"
echo ""
echo "=== ttyUSB1 响应 ==="
echo "$DATA1"
echo ""

if echo "$DATA0" | grep -q "bb66"; then
    echo "✓ ttyUSB0 是 STM32"
elif echo "$DATA1" | grep -q "bb66"; then
    echo "✓ ttyUSB1 是 STM32"
else
    echo "✗ 两个端口都不像STM32，检查固件和接线"
fi
```

保存为 `identify_stm32.sh` 并运行。
