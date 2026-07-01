# 创新点演示手册 · 本地 VLM + Nav2 · 断网自主决策

> 项目：`rdks100_slam`  
> 关键词：本地轻量化 VLM、Nav2 动态避障、断网自主、云端 / 本地实时切换

本手册讲清楚三件事：**创新点到底新在哪里、系统结构是什么样、如何一步步复现演示。**

---

## 1. 创新点一句话

> **在完全断开公网的情况下，机器人依然能"看懂"前方场景、绕开动态行人、必要时紧急停车；一旦公网恢复，同一台机器人自动切回云端 VLM 获取更自然的语言描述，形成"本地兜底 + 云端增强"的双通道能力。**

对应演示会看到的四件事：

1. 网页刷新正常连上、小车画面 / 地图实时回传（Web 层不依赖公网）。
2. 前方放置动态行人：小车自动识别 → Nav2 重规划绕行 → 距离太近直接停车告警（全程走本地 VLM + Nav2）。
3. `curl` 千问 API 超时截图 / 日志作证：公网真的不通。
4. 清防火墙 → 网页 VLM 徽标从"绿·本地"变蓝"云端"，描述文本明显更自然，形成对比。

---

## 2. 系统结构

```
┌──────────────────── 感知层 ───────────────────┐
│  RealSense D435i  →  detection_node          │
│    ├── /camera/color/image_raw               │
│    └── /detection/results  (YOLO 类别 + 距离) │
└───────────────────────┬──────────────────────┘
                        │
        ┌───────────────┼────────────────┐
        │               │                │
        ▼               ▼                ▼
  vlm_scene_node   dynamic_person_    fire_smoke_node
  (通用场景理解)   obstacle_node      (火警)
   │  ├─ provider: qwen_vl / internvl_local / mock
   │  ├─ /vlm/scene_description   (JSON)
   │  ├─ /vlm/status              (心跳)
   │  └─ /vlm/safety_event        (clear / reroute / stop)
   │
   └─ /dynamic_person_points  (sensor_msgs/PointCloud2)  →  Nav2 obstacle_layer
                                                          （新增 observation_source）

  ┌────────────── 决策/规划层 (Nav2) ──────────────┐
  │  local_costmap.obstacle_layer:                 │
  │    observation_sources: scan dynamic_person    │
  │  global_costmap 同上                            │
  │  → Nav2 自动重规划绕开 dynamic_person 点云      │
  └────────────────────────┬────────────────────────┘
                           │  /cmd_vel + safety hooks
                           ▼
                        底盘 / STM32

  ┌────────────── 展示层 ──────────────┐
  │ backend  (FastAPI + WebSocket)     │
  │   ├─ ros2_bridge (订阅 topic)      │
  │   └─ data_pusher (推 WS 分组)      │
  │                                    │
  │ frontend  (Vue 3 + Element Plus)   │
  │   ├─ VideoView   ← 本地/云端徽标   │
  │   ├─ NavigationView ← 红点+计数    │
  │   └─ SafetyEventOverlay 全局横幅   │
  └────────────────────────────────────┘
```

关键约定：

* `vlm_scene_node` 是节点名（不是 `vlm_node`）。切 provider 走的是它的参数服务 `/vlm_scene_node/set_parameters`。
* `dynamic_person_obstacle_node` 只做"YOLO 人 + 深度 → PointCloud2 + 安全事件 JSON"，绕行 / 停车 全交给 Nav2 costmap，避免与 Nav2 冲突。
* 前端 `useSafetyEvent`、`useVlmProvider` 都是**模块级单例 composable**，任意页面注入都是同一份 state，刷新页面不会丢事件计数（除非整个前端刷新）。

---

## 3. 前置条件

| 项 | 建议值 | 备注 |
|-|-|-|
| ROS2 | Humble / Foxy | 需要 `rcl_interfaces`、`sensor_msgs`、`nav2_bringup` |
| Python | ≥3.8 | 后端 FastAPI + rclpy |
| Node | ≥18 | 前端 Vue3 + vite |
| 硬件 | RDK X5 / 有 GPU 或 NPU 的边端 | 本地 VLM 建议 4~8GB 权重（Qwen2-VL-2B / MiniCPM-V-2B / InternVL-1B）|
| 权重 | 已下载到本地 | `export VLM_LOCAL_MODEL_PATH=/models/Qwen2-VL-2B-Instruct` |
| API Key | 云端演示时需要 | 二选一：① `export DASHSCOPE_API_KEY=sk-xxx`；② 直接写入 [`keys.py:24`](ros2_ws/src/vlm_scene/vlm_scene/providers/keys.py:24) 的 `DASHSCOPE_API_KEY` 常量 |

> **API Key 来源与优先级**
> 所有 provider 的 Key 都通过 [`keys.get(name)`](ros2_ws/src/vlm_scene/vlm_scene/providers/keys.py:69) 读取，顺序为 **构造参数 > 环境变量 > `keys.py` 常量**。
> 因此在本项目里，直接编辑 [`keys.py`](ros2_ws/src/vlm_scene/vlm_scene/providers/keys.py:1) 就等同于永久设置默认 Key，无需每次 `export`。
> `demo_recover.sh` 会自动同时探测 env 和 `keys.py`，任一存在即通过（否则打印 warn 而不阻断执行）。
> 请不要把包含真实 Key 的 `keys.py` 提交到公开仓库，建议加入 `.gitignore` 或在 CI 上用占位空字符串。

---

## 4. 一键跑通流程

```bash
# 1) 环境
cd rdks100_slam
source ros2_ws/install/setup.bash

# 2) 后端
cd backend
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000 --reload &

# 3) 前端（浏览器打开 http://<host>:5173）
cd ../frontend
npm install
npm run dev &

# 4) 感知 + 检测 + VLM
ros2 launch d435i_detection detection.launch.py &
ros2 launch vlm_scene vlm.launch.py provider:=qwen_vl &   # 默认云端
ros2 run czybot_navigation2 dynamic_person_obstacle_node &

# 5) Nav2（含 dynamic_person observation_source）
ros2 launch czybot_navigation2 navigation.launch.py &
```

打开网页，应该能看到：

* VideoView 顶部"场景理解"标签旁有一个圆点徽标：蓝色·**云端·通义千问VL**（或绿色·**本地轻量VLM**，取决于 provider 参数）。
* NavigationView 地图区域出现雷达式坐标系，机器人（青色圆点）居中，两圈虚线圆表示 0.8m/1.2m/2.5m 阈值。
* 顶部导航栏若触发"绕行"或"停车"，会有 SafetyEventOverlay 横幅或右下角 toast，与火警互不干扰。

---

## 5. 断网演示 · `demo_offline.sh`

```bash
sudo bash scripts/demo_offline.sh          # 默认切到 internvl_local
# 或者，只想演示"路子跑通"而不加载真 HF 模型：
sudo bash scripts/demo_offline.sh mock
```

脚本会按顺序做四件事：

1. 先 `curl -m 5 https://dashscope.aliyuncs.com/...` 作为**断网前基线**（通常 HTTP=200）。
2. `iptables -I OUTPUT -d <ip> -j REJECT` 阻断到千问 / DeepSeek 出口。
3. 再 `curl -v`，可看到 **`Failed to connect ... Connection refused / timed out`**。此步骤截图 / 拷贝日志即为"公网不通"的证据。
4. `ros2 param set /vlm_scene_node provider internvl_local`，节点内部会拉起本地 VLM provider。

网页现象（关键截图点）：

* 顶部徽标从"云端·通义千问VL"变为"**本地轻量VLM**"或"**本地规则兜底**"（后者说明 HF 模型未加载成功，走的是规则兜底）。
* VLM 平均延迟数字（`avgLatencyMs`）会立刻缩短或改变（本地推理与云端 latency 差异明显）。
* 在小车前方放一个人（或让人走进相机 2.5m 视野内），Navigation 页红点开始出现；进入 1.2m 触发 reroute → 0.8m 触发 stop，右下角/顶部 SafetyEventOverlay 会依次弹出。
* **网页刷新一次**：AUTO_SUBSCRIBED_TOPICS 内的 `safety_event` / `vlm_status` 都是重连即用，画面 / 事件都不会丢。

日志层面可以补一句：

```bash
ros2 topic hz /vlm/scene_description        # 观察本地 VLM 出词频率
ros2 topic echo /vlm/safety_event -n 5      # 看到 action=reroute/stop JSON
ros2 topic echo /dynamic_person_points --field header.frame_id  # 确认发布链路
```

---

## 6. 恢复演示 · `demo_recover.sh`

```bash
sudo bash scripts/demo_recover.sh                # 切回 qwen_vl（Key 从 keys.py 或 env 自动读取）
sudo bash scripts/demo_recover.sh openai_vision  # 也可切到 openai_vision
```

脚本要点：

1. 精确删除掉 `demo_offline.sh` 加过的 iptables REJECT 规则（同 IP 循环 `-D` 直到清干净）；DNS 换 IP 的极端情况会有 warn 提示，请手动 `iptables -L OUTPUT --line-numbers` 复查。
2. 再 `curl`，此时应显示 `HTTP=200` 并有 `time_total`。
3. 探测 Key：先看 `env`，再 `grep` 一下 [`keys.py`](ros2_ws/src/vlm_scene/vlm_scene/providers/keys.py:24)，两者都没有才 warn，避免"忘了 export 又忘了改 keys.py"直接 500。
4. `ros2 param set /vlm_scene_node provider qwen_vl` 切回云端。

现象对比（这就是"前后效果对比"的核心）：

| 维度 | 断网 / 本地 | 联网 / 云端 |
|-|-|-|
| VLM 徽标 | 绿色 · 本地轻量VLM / 本地规则兜底 | 蓝色 · 云端·通义千问VL |
| 描述文本 | 短、动作导向、少语气词 | 长、场景化、带情境建议 |
| 延迟 avg_ms | 视本地模型而定，通常几百 ms（NPU）到 3s（CPU） | 云端 1~4s，含网络 RTT |
| 安全动作 | 依然能 reroute / stop（**关键** ！本地兜底就是干这个用的） | 同上 |
| curl 千问 | 失败 | 成功 |

---

## 7. FAQ / 故障排查

**Q1: 网页刷新后 SafetyEventOverlay 横幅不出现？**  
A: 检查后端日志是否在打印 `push_safety_event`；然后浏览器 devtools → Network → WS 帧里是否有 `topic:"safety_event"`。若没有，通常是 `dynamic_person_obstacle_node` 未启动或 `/vlm/safety_event` 未发布。

**Q2: 本地 VLM 加载失败，一直显示"本地规则兜底"？**  
A: 看 `vlm_scene_node` 启动日志，通常是：`VLM_LOCAL_MODEL_PATH` 未设置或路径下没有 config.json / transformers 版本过低。规则兜底会继续给出简短描述，不影响避障功能。

**Q3: iptables 规则清不掉？**  
A: 手动执行 `sudo iptables -L OUTPUT --line-numbers | grep REJECT`，用 `sudo iptables -D OUTPUT <行号>` 精确删除；或者 `sudo iptables -F OUTPUT`（会清空整个 OUTPUT 链，请评估风险）。

**Q4: 断网后云端 provider（如 openai_vision）依然被调用怎么办？**  
A: 说明 provider 参数没成功切换。`ros2 param get /vlm_scene_node provider` 应返回 `internvl_local` / `mock`。若返回旧值，检查节点名 `vlm_scene_node` 是否被 remap 过。

**Q5: dynamic_person 红点不出现？**  
A:
- 查看 `nav2_params.yaml` 里 `observation_sources` 是否包含 `dynamic_person`。
- 查看 `dynamic_person_obstacle_node` 日志，是否有 "person detected, publishing X points"。
- 前端 NavigationView 只画 3m 内的点，若行人在更远处不会显示；缩短距离再试。

---

## 8. 关键改动索引

| 位置 | 作用 |
|-|-|
| `ros2_ws/src/vlm_scene/vlm_scene/providers/internvl_local.py` | 本地 HF 推理 + 规则兜底 |
| `ros2_ws/src/vlm_scene/config/vlm_params.yaml` | 本地模型路径 / 类型 / dtype 等参数 |
| `ros2_ws/src/vlm_scene/launch/vlm.launch.py` | 本地 VLM 启动参数与 env 传参 |
| `ros2_ws/src/vlm_scene/vlm_scene/vlm_node.py` | 声明 `local_*`、`next_user_prompt` 参数 |
| `ros2_ws/src/czybot_navigation2/scripts/dynamic_person_obstacle_node.py` | 检测行人 → PointCloud2 + safety_event |
| `ros2_ws/src/czybot_navigation2/config/nav2_params.yaml` | `observation_sources: scan dynamic_person` |
| `backend/app/services/ros2_bridge.py` | 订阅 safety_event / dynamic_person_points + 修正节点名 |
| `backend/app/services/data_pusher.py` | 2Hz safety_event / 5Hz dynamic_person_points 推送 |
| `frontend/src/composables/useSafetyEvent.ts` | 模块级单例，全局共享安全事件 |
| `frontend/src/composables/useVlmProvider.ts` | 模块级单例，追踪本地/云端 provider |
| `frontend/src/components/SafetyEventOverlay.vue` | 全局横幅 + toast + 详情弹窗 |
| `frontend/src/views/navigation/NavigationView.vue` | 动态障碍红点 + 计数 + 状态面板 |
| `scripts/demo_offline.sh` / `scripts/demo_recover.sh` | 一键断网 / 恢复演示 |

---

## 9. 一分钟演示脚本（口播稿参考）

> "打开网页，能看到相机画面和 SLAM 地图，右上角显示当前使用云端通义千问 VL。"  
> "现在演示断网场景。我执行 `demo_offline.sh`，它会 iptables 阻断到千问 API 的出口，然后 curl 显示 timeout。"  
> "网页顶部徽标从蓝色云端变成绿色本地。我在小车前方放一个人，注意 Navigation 页面出现红点、上方 SafetyEventOverlay 弹出'紧急停车'横幅——整个决策没有走一次云端。"  
> "接下来恢复。执行 `demo_recover.sh`，iptables 规则清掉，curl 恢复 200，网页徽标变回蓝色，同一场景的描述文本明显更自然，这就是'本地兜底 + 云端增强'的双通道。"
