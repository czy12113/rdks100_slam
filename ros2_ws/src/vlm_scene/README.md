# vlm_scene — RDK S100 视觉语言场景理解

把 D435i 相机的关键帧 + DOSOD/YOLO 检测框送进 **通义千问 VL（Qwen-VL）** 等
视觉语言大模型，输出自然语言场景描述，供前端面板展示或语音播报。

> 示例输出：
> 「前方约 1.8 米处站着一名穿红色外套的成年男子，他正面向你；地面无明显障碍物，可继续前进。」

---

## 1. 架构

```
┌──────────────────────┐       ┌────────────────────────────┐
│  D435i (RGB+Depth)   │       │  d435i_detection           │
│  /camera/.../image_raw│      │  YOLO/DOSOD → /detection/  │
└──────────┬───────────┘       │             results (JSON) │
           │  /camera/.../    └──────────────┬─────────────┘
           │  color/image_raw                │ /detection/results
           ▼                                 ▼
       ┌─────────────────────────────────────────────────┐
       │  vlm_node  (本包，新增)                          │
       │  • KeyframeSelector（节流+变化触发）             │
       │  • crop ROI + downscale                          │
       │  • Provider 插件（qwen_vl / openai_vision / …）  │
       └────────────┬────────────────────────────────────┘
                    │
        ┌───────────┴──────────────────────────┐
        │                                      │
        ▼                                      ▼
   /vlm/scene_description (std_msgs/String)   /vlm/status
        │
        │  (FastAPI ROS2Bridge 订阅)
        ▼
   backend WebSocket → 前端 VlmView
```

设计要点：
- **不在 backend 里调 VLM API**：所有外网调用都在 ROS2 节点完成，API Key 仅暴露给一个进程；
- **关键帧触发**：默认 3 秒冷却 + 类别变化 + 距离变化 0.5 米才会请求一次 VLM，避免烧钱；
- **Provider 插件化**：换 provider 只改 `provider:=qwen_vl` 启动参数，业务代码不动；
- **离线降级**：未配置 API Key 时自动落回 `mock` provider（按检测框拼装中文模板）。

---

## 2. 文件结构

```
ros2_ws/src/vlm_scene/
├── package.xml
├── setup.py
├── setup.cfg
├── resource/vlm_scene
├── config/vlm_params.yaml          # 节点参数（topic 名、阈值、prompt 等）
├── launch/vlm.launch.py            # 启动文件（注入 venv PYTHONPATH）
└── vlm_scene/
    ├── vlm_node.py                 # 主 ROS2 节点（订阅+发布+service）
    ├── providers/                  # VLM 插件
    │   ├── base.py                 # BaseVLMProvider / VLMRequest / VLMResponse
    │   ├── factory.py              # name → 类的工厂
    │   ├── qwen_vl.py              # ★ 默认：通义千问 VL（DashScope）
    │   ├── openai_vision.py        # 任意 OpenAI 兼容 API
    │   ├── deepseek_text.py        # DeepSeek 纯文本（无视觉，仅依检测拼描述）
    │   ├── internvl_local.py       # 本地 InternVL2（BPU 占位）
    │   └── mock.py                 # 离线模板
    └── utils/
        ├── image_ops.py            # ROS Image → BGR / 裁剪 / 等比缩放
        └── keyframe.py             # 关键帧触发器
```

---

## 3. RDK S100 板端依赖安装

> ⚠️ 本节命令在 **RDK S100 板** 上执行（sunrise 用户），不是开发电脑。
> backend 已经在使用 `/home/sunrise/rdks100_slam/backend/venv/`，VLM 节点复用同一个 venv，避免依赖重复装。

### 3.1 系统包（一次性）

```bash
# 进入 sunrise 用户
sudo apt update
sudo apt install -y \
    python3-pip python3-venv \
    libgl1 libglib2.0-0 \
    ros-humble-cv-bridge \
    ros-humble-std-srvs

# realsense（如果还没装，detection 包已经装过则跳过）
sudo apt install -y ros-humble-realsense2-camera ros-humble-realsense2-description
```

### 3.2 Python 依赖（写入 backend venv）

```bash
cd /home/sunrise/rdks100_slam
source backend/venv/bin/activate

# 只装这两个，其它（numpy / cv2 / opencv-python）后端已经有了
pip install --upgrade pip
pip install \
    opencv-python-headless==4.8.* \
    numpy>=1.24

# 不需要 'requests' / 'openai' SDK，节点直接用标准库 urllib
```

> 板上 `cv2` 已经被 detection_node 装好；vlm_node 也只用 `cv2.imencode` 和 `cv2.resize`，
> 不会和 DOSOD/YOLO 冲突。

### 3.3 编译 ROS2 包

```bash
cd /home/sunrise/rdks100_slam/ros2_ws
colcon build --packages-select vlm_scene --symlink-install
source install/setup.bash
```

### 3.4 配置 API Key（**必做**）

通义千问 VL（DashScope）需要 API Key，去 <https://bailian.console.aliyun.com/> 申请。

**方式 A（推荐：直接改代码，最省事）**

打开 [`vlm_scene/providers/keys.py`](vlm_scene/providers/keys.py:1)，把 Key 粘贴进去即可：

```python
# vlm_scene/providers/keys.py
DASHSCOPE_API_KEY: str = "sk-xxxxxxxxxxxxxxxxxxxxxxxx"   # ← 你的 Key
VLM_QWEN_MODEL: str = "qwen-vl-plus"                     # 可选：qwen-vl-max
VLM_QWEN_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
```

> 改完不用重新 `colcon build`（`--symlink-install` 模式直接生效），重启 vlm_node 即可。

**方式 B（生产环境用环境变量）**

```bash
# 写入 ~/.bashrc，重启 systemd 服务前 source
echo 'export DASHSCOPE_API_KEY="sk-xxxxxxxxxxxxxxxxxxxxxxxx"' >> ~/.bashrc
source ~/.bashrc

# 可选：覆盖模型 / Base URL
export VLM_QWEN_MODEL="qwen-vl-plus"
export VLM_QWEN_BASE_URL="https://dashscope.aliyuncs.com/compatible-mode/v1"
```

**读取优先级**：构造参数 > 环境变量 > `keys.py` 常量。三个 provider（qwen_vl / openai_vision / deepseek_text）都遵循同一套规则，所有 Key 都集中在 [`keys.py`](vlm_scene/providers/keys.py:1) 里。

可选模型：
| 模型 | 速度 | 价格 | 描述质量 |
|---|---|---|---|
| `qwen-vl-plus` | 中等 | 中等 | **推荐**，性价比最高 |
| `qwen-vl-max` | 慢 | 高 | 描述最精细 |
| `qwen-vl-max-latest` | 慢 | 高 | 最新版（更新频繁） |

---

## 4. 启动

### 4.1 单独启动 vlm_node（调试用）

```bash
cd /home/sunrise/rdks100_slam/ros2_ws
source install/setup.bash

# 用默认参数（provider=qwen_vl，订阅 /detection/results + /camera/camera/color/image_raw）
ros2 launch vlm_scene vlm.launch.py

# 切到 mock（不调外网，纯模板，给前端联调用）
ros2 launch vlm_scene vlm.launch.py provider:=mock

# 切到 OpenAI 兼容 API
export OPENAI_API_KEY="sk-..."
export VLM_OPENAI_BASE_URL="https://api.openai.com/v1"
export VLM_OPENAI_MODEL="gpt-4o-mini"
ros2 launch vlm_scene vlm.launch.py provider:=openai_vision

# 调慢节流（默认 3s 冷却，调成 5s）
ros2 launch vlm_scene vlm.launch.py cooldown_sec:=5.0 heartbeat_sec:=30.0
```

### 4.2 验证 topic

```bash
# 看节点是否在
ros2 node list | grep vlm

# 看场景描述（每条都是 JSON）
ros2 topic echo /vlm/scene_description --once

# 看状态心跳
ros2 topic echo /vlm/status --once

# 手动触发一次推理
ros2 service call /vlm/ask std_srvs/srv/Trigger {}
```

### 4.3 写入 systemd（开机自启）

参考 detection 节点的 systemd unit，新建 `/etc/systemd/system/vlm_scene.service`：

```ini
[Unit]
Description=VLM Scene Understanding (Qwen-VL)
After=network-online.target detection.service
Wants=network-online.target

[Service]
Type=simple
User=sunrise
Group=sunrise
Environment="DASHSCOPE_API_KEY=sk-xxxxxxxxxxxxxxxxxxxx"
Environment="VLM_QWEN_MODEL=qwen-vl-plus"
ExecStartPre=/bin/sleep 5
ExecStart=/bin/bash -lc 'source /opt/ros/humble/setup.bash && \
    source /home/sunrise/rdks100_slam/ros2_ws/install/setup.bash && \
    ros2 launch vlm_scene vlm.launch.py'
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now vlm_scene
sudo systemctl status vlm_scene
journalctl -u vlm_scene -f
```

---

## 5. Provider 切换速查

| name | 需要 Key | 说明 |
|---|---|---|
| `qwen_vl` | `DASHSCOPE_API_KEY` | **默认**，通义千问 VL（推荐） |
| `openai_vision` | `OPENAI_API_KEY` | OpenAI / 任意兼容服务（GPT-4o、Moonshot、智谱等） |
| `deepseek_text` | `DEEPSEEK_API_KEY` | DeepSeek 没视觉，仅依检测列表生成描述（兜底） |
| `internvl_local` | — | 本地 InternVL2 占位，需要后续接 BPU 模型 |
| `mock` | — | 完全离线，按检测拼模板，前端联调专用 |

切换只需改 launch 参数：

```bash
ros2 launch vlm_scene vlm.launch.py provider:=mock
```

---

## 6. 性能 & 成本提示

- 默认 `cooldown_sec=3.0` + 关键帧变化触发，**正常巡航 1 分钟约 5~10 次 VLM 调用**；
- `qwen-vl-plus` 单次约 ¥0.005，图像下采样到 768px 长边再 JPEG-80 编码，单帧约 30~70KB；
- 节流参数全在 [`vlm_params.yaml`](config/vlm_params.yaml:1)，可以按场景调；
- 节点崩了不会拉爆 backend：所有订阅都有 try/except，`provider` 失败会被吞掉并写到 `/vlm/status.last_error`。

---

## 7. 常见问题

- **`ImportError: No module named 'cv2'`** → 把 `backend/venv` 的 site-packages 注入到 PYTHONPATH，
  这一步 launch 文件已经做了，但如果你自己 `ros2 run` 启动，需要先 `source backend/venv/bin/activate`。
- **`401 Unauthorized`** → 检查 `DASHSCOPE_API_KEY` 是否在节点环境里（`systemctl show vlm_scene -p Environment`）。
- **每次 description 都一样** → 关键帧节流没有触发新帧，检查是否所有目标的距离都很接近且类别没变。
- **想强制每帧都推理（演示用）** → 把 `cooldown_sec` 调为 `0.5`，`heartbeat_sec` 调为 `1.0`，但成本会显著上升。
