#!/usr/bin/env bash
# =============================================================================
# demo_offline.sh —— 创新点演示 · "云端断网 → 本地接管"
#
# 场景：
#   1. 使用 iptables 阻断到 dashscope.aliyuncs.com 的出口流量，模拟公网不通；
#   2. 用 curl -m 5 主动请求千问 API，可看到 "Connection timed out"，证明网确实断了；
#   3. 通过 ros2 service call /vlm_scene_node/set_parameters 把 provider 切成
#      internvl_local，接下来的场景理解/避障判定完全走本地推理；
#   4. 在网页上继续查看小车画面、地图、场景描述，观察"本地"徽标常亮。
#
# 使用：
#   sudo bash scripts/demo_offline.sh          # 默认切成 internvl_local
#   sudo bash scripts/demo_offline.sh mock     # 切成 mock provider（无本地权重时兜底）
#
# 需要：
#   - iptables 权限（脚本内部会 sudo 提权，若已 root 直接执行即可）
#   - 环境已 source ros2_ws/install/setup.bash（含 rclpy / rcl_interfaces）
#   - 若使用真实 HF 权重，先 export VLM_LOCAL_MODEL_PATH=/path/to/model
# =============================================================================

set -u
set -o pipefail

# ---- 可配置项 ----
TARGET_HOST="${TARGET_HOST:-dashscope.aliyuncs.com}"
TARGET_HOST2="${TARGET_HOST2:-api.deepseek.com}"
TARGET_PROVIDER="${1:-internvl_local}"
CURL_TIMEOUT="${CURL_TIMEOUT:-5}"
VLM_NODE_NAME="${VLM_NODE_NAME:-/vlm_scene_node}"

# ---- 颜色 ----
if [[ -t 1 ]]; then
  R=$'\033[31m'; G=$'\033[32m'; Y=$'\033[33m'; B=$'\033[34m'; C=$'\033[36m'; N=$'\033[0m'; BOLD=$'\033[1m'
else
  R=; G=; Y=; B=; C=; N=; BOLD=
fi

log() { echo -e "${C}[demo-offline]${N} $*"; }
ok()  { echo -e "${G}[ok]${N} $*"; }
warn(){ echo -e "${Y}[warn]${N} $*"; }
err() { echo -e "${R}[err]${N} $*"; }

need_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    err "缺少命令 $1，请先安装"
    exit 1
  fi
}

need_cmd curl
need_cmd iptables

# ---- 提权检查 ----
if [[ $EUID -ne 0 ]]; then
  warn "iptables 需要 root 权限，将尝试 sudo 重启本脚本"
  exec sudo -E bash "$0" "$@"
fi

echo
echo -e "${BOLD}================================================================${N}"
echo -e "${BOLD}  创新点演示  ·  云端断网 → 本地 VLM 接管${N}"
echo -e "${BOLD}================================================================${N}"
echo "  目标云端：$TARGET_HOST"
echo "  切换到 provider：$TARGET_PROVIDER"
echo

# ---- 步骤 1：curl 验证（断网前）----
log "步骤 1/4 · 断网前先 curl 一次，作为基线"
curl -s -o /dev/null -m "$CURL_TIMEOUT" -w "  HTTP=%{http_code}  time_total=%{time_total}s\n" \
  "https://${TARGET_HOST}/compatible-mode/v1/models" || true
echo

# ---- 步骤 2：iptables 阻断 ----
log "步骤 2/4 · 用 iptables 阻断到 ${TARGET_HOST} 与 ${TARGET_HOST2} 的出口流量"

# 解析 IP（用 getent 兼容 nss；失败则回退到 host / dig）
resolve_ips() {
  local host="$1"
  if command -v getent >/dev/null 2>&1; then
    getent ahostsv4 "$host" 2>/dev/null | awk '{print $1}' | sort -u
  elif command -v dig >/dev/null 2>&1; then
    dig +short "$host" A
  elif command -v host >/dev/null 2>&1; then
    host "$host" | awk '/has address/ {print $NF}'
  fi
}

for host in "$TARGET_HOST" "$TARGET_HOST2"; do
  ips=$(resolve_ips "$host" || true)
  if [[ -z "${ips// }" ]]; then
    warn "  $host 解析不到 IP（可能 DNS 也不通了？），改为按域名直接 REJECT DNS-only 记录"
    continue
  fi
  while read -r ip; do
    [[ -z "$ip" ]] && continue
    if ! iptables -C OUTPUT -d "$ip" -j REJECT 2>/dev/null; then
      iptables -I OUTPUT -d "$ip" -j REJECT
      ok "  已 REJECT $host ($ip)"
    else
      warn "  规则已存在 $host ($ip)"
    fi
  done <<< "$ips"
done
echo

# ---- 步骤 3：curl 再测一次，应超时/拒绝 ----
log "步骤 3/4 · 再次 curl，应出现 timeout 或 connection refused"
set +e
curl -v -m "$CURL_TIMEOUT" "https://${TARGET_HOST}/compatible-mode/v1/models" 2>&1 \
  | tail -20
CURL_RC=$?
set -e
if [[ $CURL_RC -ne 0 ]]; then
  ok "curl 已按预期失败（exit=$CURL_RC），证明公网确实不通"
else
  warn "curl 竟然成功了？可能 iptables 规则未生效，请检查"
fi
echo

# ---- 步骤 4：切换 provider 到本地 ----
log "步骤 4/4 · 通过 ROS2 参数服务把 VLM provider 切到 ${TARGET_PROVIDER}"

# ⚠️ ROS 2 DDS 发现受 ROS_DOMAIN_ID / RMW_IMPLEMENTATION 等 env 决定。
# sudo 默认会 env_reset，即便 `sudo VAR=val cmd` 也可能被 sudoers 过滤。
# 唯一 100% 可靠方案：在 sudo 已经降权到 sunrise 的子 shell **内部**，
# 直接读取正在运行的 vlm_node 进程的 /proc/<pid>/environ，逐个 export。

if [[ -z "${SUDO_USER:-}" || "${SUDO_USER}" == "root" ]]; then
  err "无法确定原用户（SUDO_USER 未设置）。请通过 sudo（而非 su -）执行本脚本。"
  err "  例如： sudo bash scripts/demo_offline.sh"
  exit 1
fi

ROS_USER="${SUDO_USER}"
WS_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

SYS_ROS=""
for cand in /opt/ros/*/setup.bash; do
  [[ -f "$cand" ]] && SYS_ROS="$cand" && break
done
WS_SETUP="$WS_ROOT/ros2_ws/install/setup.bash"

# ---- 4.1 定位正在跑的 vlm_node 进程 ----
# 优先匹配真实的 python 子进程（含 "vlm_node" 关键字）；退而求其次匹配 launch 主进程
VLM_PID="$(pgrep -u "$ROS_USER" -f 'vlm_node' 2>/dev/null | head -1)"
if [[ -z "$VLM_PID" ]]; then
  VLM_PID="$(pgrep -u "$ROS_USER" -f 'vlm_scene' 2>/dev/null | head -1)"
fi
if [[ -z "$VLM_PID" ]]; then
  err "  未在 $ROS_USER 用户下找到 vlm_node/vlm_scene 进程"
  err "  请确认 vlm.launch.py 那个终端还在跑"
  exit 1
fi
log "  发现 vlm 进程 PID=$VLM_PID  ($(tr '\0' ' ' </proc/$VLM_PID/cmdline 2>/dev/null | cut -c1-120))"

if [[ ! -r "/proc/$VLM_PID/environ" ]]; then
  err "  无法读取 /proc/$VLM_PID/environ（应该 root 可读，请检查权限）"
  exit 1
fi

# 预览节点关键 env（仅用来打日志，实际 export 在子 shell 内做）
_preview_env() {
  local key="$1"
  tr '\0' '\n' < "/proc/$VLM_PID/environ" 2>/dev/null \
    | awk -F= -v k="$key" '$1==k {sub(/^[^=]+=/,""); print; exit}'
}
PREVIEW_DOMAIN="$(_preview_env ROS_DOMAIN_ID)"
PREVIEW_RMW="$(_preview_env RMW_IMPLEMENTATION)"
PREVIEW_LOCALHOST="$(_preview_env ROS_LOCALHOST_ONLY)"
log "  节点关键 env："
log "    ROS_DOMAIN_ID     = ${PREVIEW_DOMAIN:-<unset, 默认 0>}"
log "    RMW_IMPLEMENTATION= ${PREVIEW_RMW:-<unset, 默认 fastrtps>}"
log "    ROS_LOCALHOST_ONLY= ${PREVIEW_LOCALHOST:-<unset>}"

# ---- 4.2 组装 "先降权到原用户，再在子 shell 内部 export env + source ROS" ----
_run_as_user() {
  local cmd="$*"
  # 用 heredoc 把整段 bash 传给 sudo，避免多层引号地狱
  sudo -u "$ROS_USER" -H bash <<HEREDOC
set +u
# 1) 从 vlm_node 进程读 env（NUL 分隔），只保留 ROS_*/RMW_*/FASTRTPS_*/CYCLONEDDS_*
while IFS= read -r -d '' kv; do
  case "\$kv" in
    ROS_*=*|RMW_*=*|FASTRTPS_*=*|CYCLONEDDS_*=*)
      export "\$kv"
      ;;
  esac
done < "/proc/$VLM_PID/environ"
# 2) 加载系统 ROS 与工作区
[[ -f '$SYS_ROS' ]] && source '$SYS_ROS'
[[ -f '$WS_SETUP' ]] && source '$WS_SETUP'
set -u
# 3) 执行调用者传入的命令
$cmd
HEREDOC
}

# ---- 4.3 自检：先 dump 子 shell 里真实的 ROS env（便于故障时定位） ----
log "  子 shell 自检："
_run_as_user 'env | grep -E "^(ROS_|RMW_|FASTRTPS_|CYCLONEDDS_)" | sort | sed "s/^/    /"' || true

# ---- 4.3.5 强制重启 ros2 daemon ----
# 关键：daemon 缓存脏了会导致 ros2 node list 返回空。手动 stop → start 强制重建。
# 之前诊断显示：sunrise 用户在 launch 之后 ros2 node list 就是空的，
# 只有 ros2 daemon stop && start 后才能看到节点。这是 ROS 2 Humble 已知的 daemon 陈旧问题。
log "  强制重启 ros2 daemon 以刷新发现缓存 ..."
_run_as_user 'ros2 daemon stop >/dev/null 2>&1; ros2 daemon start >/dev/null 2>&1; sleep 1'

# ---- 4.4 发现节点 ----
log "  探测 ROS 图里的 VLM 节点 ..."
NODES="$(_run_as_user 'ros2 node list 2>/dev/null | grep -Ei "vlm" || true')"
if [[ -z "$NODES" ]]; then
  err "  子 shell 里 env 已对齐，但仍看不到 vlm* 节点"
  err "  下一步定位（在 root shell 里执行）："
  err "    sudo -u $ROS_USER -H bash -c \"while IFS= read -r -d '' kv; do case \\\"\\\$kv\\\" in ROS_*|RMW_*) export \\\"\\\$kv\\\";; esac; done < /proc/$VLM_PID/environ; source '$SYS_ROS'; source '$WS_SETUP'; ros2 node list\""
  err "  以及在你启动 launch 的 sunrise 终端里直接 ros2 node list，看是否也看不到"
  exit 1
fi
log "  发现节点："
echo "$NODES" | sed 's/^/    /'

REAL_NODE="$(echo "$NODES" | grep -x "$VLM_NODE_NAME" | head -1)"
[[ -z "$REAL_NODE" ]] && REAL_NODE="$(echo "$NODES" | grep -E 'vlm_scene' | head -1)"
[[ -z "$REAL_NODE" ]] && REAL_NODE="$(echo "$NODES" | head -1)"
log "  选中节点： $REAL_NODE"

# ---- 4.5 切 provider ----
set +e
_run_as_user "ros2 param set '$REAL_NODE' provider '$TARGET_PROVIDER'"
RC=$?
set -e

if [[ $RC -ne 0 ]]; then
  err "切换失败。节点 $REAL_NODE 未声明 'provider' 参数，或参数服务未起。"
  err "  排查： _run_as_user 'ros2 param list $REAL_NODE'"
  exit 1
fi
ok "provider 已切换。请打开网页：应看到"
ok "  · 顶部 场景理解 卡片 · 徽标：绿色 · 【本地轻量VLM】或【本地规则兜底】"
ok "  · 网页刷新/切换页面依然能正常收到画面、地图（走的是本地 backend，公网不通不影响）"
ok "  · 放置一个人挡在小车前方，Navigation 页应看到红点闪烁 + 顶部 🛑 停车横幅"

echo
log "如需恢复公网，执行：  sudo bash scripts/demo_recover.sh"
echo
