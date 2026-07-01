#!/usr/bin/env bash
# =============================================================================
# demo_recover.sh —— 创新点演示 · "网络恢复 → 云端 VLM 接管"
#
# 与 demo_offline.sh 对称：
#   1. 清空 iptables 中针对 dashscope.aliyuncs.com / api.deepseek.com 的 REJECT 规则；
#   2. 用 curl 主动请求千问 API，验证公网已恢复；
#   3. 通过 ros2 param set 把 provider 切回 qwen_vl（默认，可参数覆盖）；
#   4. 网页顶部 场景理解 徽标应变蓝色【云端·通义千问VL】，展现"云端增强"效果。
#
# 使用：
#   sudo bash scripts/demo_recover.sh                # 切回 qwen_vl
#   sudo bash scripts/demo_recover.sh openai_vision  # 切到 openai_vision
# =============================================================================

set -u
set -o pipefail

TARGET_HOST="${TARGET_HOST:-dashscope.aliyuncs.com}"
TARGET_HOST2="${TARGET_HOST2:-api.deepseek.com}"
TARGET_PROVIDER="${1:-qwen_vl}"
CURL_TIMEOUT="${CURL_TIMEOUT:-8}"
VLM_NODE_NAME="${VLM_NODE_NAME:-/vlm_scene_node}"

if [[ -t 1 ]]; then
  R=$'\033[31m'; G=$'\033[32m'; Y=$'\033[33m'; C=$'\033[36m'; N=$'\033[0m'; BOLD=$'\033[1m'
else
  R=; G=; Y=; C=; N=; BOLD=
fi

log() { echo -e "${C}[demo-recover]${N} $*"; }
ok()  { echo -e "${G}[ok]${N} $*"; }
warn(){ echo -e "${Y}[warn]${N} $*"; }
err() { echo -e "${R}[err]${N} $*"; }

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || { err "缺少命令 $1"; exit 1; }
}
need_cmd curl
need_cmd iptables

if [[ $EUID -ne 0 ]]; then
  warn "iptables 需要 root 权限，尝试 sudo 重启本脚本"
  exec sudo -E bash "$0" "$@"
fi

echo
echo -e "${BOLD}================================================================${N}"
echo -e "${BOLD}  创新点演示  ·  网络恢复 → 云端 VLM 接管${N}"
echo -e "${BOLD}================================================================${N}"
echo "  切回 provider：$TARGET_PROVIDER"
echo

# ---- 步骤 1：清空针对目标 host 的 REJECT 规则 ----
log "步骤 1/3 · 清空 iptables 中针对 ${TARGET_HOST} / ${TARGET_HOST2} 的 REJECT 规则"

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

# 精确删除本次可能加过的 REJECT 规则
for host in "$TARGET_HOST" "$TARGET_HOST2"; do
  ips=$(resolve_ips "$host" || true)
  while read -r ip; do
    [[ -z "$ip" ]] && continue
    # 循环删除同一条规则（可能被多次加过）
    while iptables -C OUTPUT -d "$ip" -j REJECT 2>/dev/null; do
      iptables -D OUTPUT -d "$ip" -j REJECT && ok "  删除 REJECT $host ($ip)"
    done
  done <<< "$ips"
done

# 兜底：也 flush 掉 OUTPUT 链里所有 REJECT 到 dashscope 段（防止 DNS 换了 IP 遗漏）
warn "  如果仍有残留，可以手动执行：sudo iptables -L OUTPUT --line-numbers | grep REJECT"
echo

# ---- 步骤 2：curl 验证 ----
log "步骤 2/3 · 用 curl 验证 ${TARGET_HOST} 是否可达"
set +e
curl -s -o /dev/null -m "$CURL_TIMEOUT" -w "  HTTP=%{http_code}  time_total=%{time_total}s\n" \
  "https://${TARGET_HOST}/compatible-mode/v1/models"
CURL_RC=$?
set -e
if [[ $CURL_RC -ne 0 ]]; then
  warn "curl 依然失败（可能物理网线仍拔着 / 防火墙有其他规则）"
else
  ok "curl 已能收到 HTTP 响应，公网可达"
fi
echo

# ---- 步骤 3：切换 provider 回云端 ----
log "步骤 3/3 · 通过 ROS2 参数服务把 VLM provider 切回 ${TARGET_PROVIDER}"

# 与 demo_offline.sh 完全一致的策略：在 sudo 已经降权到 sunrise 的子 shell 内部，
# 直接读取正在运行的 vlm_node 进程 /proc/<pid>/environ，逐个 export，
# 避免 sudo env_reset / sudoers env_keep 白名单等干扰。

if [[ -z "${SUDO_USER:-}" || "${SUDO_USER}" == "root" ]]; then
  err "无法确定原用户（SUDO_USER 未设置）。请通过 sudo（而非 su -）执行本脚本。"
  exit 1
fi

ROS_USER="${SUDO_USER}"
WS_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

SYS_ROS=""
for cand in /opt/ros/*/setup.bash; do
  [[ -f "$cand" ]] && SYS_ROS="$cand" && break
done
WS_SETUP="$WS_ROOT/ros2_ws/install/setup.bash"

VLM_PID="$(pgrep -u "$ROS_USER" -f 'vlm_node' 2>/dev/null | head -1)"
if [[ -z "$VLM_PID" ]]; then
  VLM_PID="$(pgrep -u "$ROS_USER" -f 'vlm_scene' 2>/dev/null | head -1)"
fi
if [[ -z "$VLM_PID" ]]; then
  err "  未找到 vlm_node/vlm_scene 进程，请先启动： ros2 launch vlm_scene vlm.launch.py"
  exit 1
fi
log "  发现 vlm 进程 PID=$VLM_PID  ($(tr '\0' ' ' </proc/$VLM_PID/cmdline 2>/dev/null | cut -c1-120))"

if [[ ! -r "/proc/$VLM_PID/environ" ]]; then
  err "  无法读取 /proc/$VLM_PID/environ（root 应可读，请检查权限）"
  exit 1
fi

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

_run_as_user() {
  local cmd="$*"
  sudo -u "$ROS_USER" -H bash <<HEREDOC
set +u
while IFS= read -r -d '' kv; do
  case "\$kv" in
    ROS_*=*|RMW_*=*|FASTRTPS_*=*|CYCLONEDDS_*=*)
      export "\$kv"
      ;;
  esac
done < "/proc/$VLM_PID/environ"
[[ -f '$SYS_ROS' ]] && source '$SYS_ROS'
[[ -f '$WS_SETUP' ]] && source '$WS_SETUP'
set -u
$cmd
HEREDOC
}

log "  子 shell 自检："
_run_as_user 'env | grep -E "^(ROS_|RMW_|FASTRTPS_|CYCLONEDDS_)" | sort | sed "s/^/    /"' || true

# 强制重启 daemon 刷新发现缓存（与 demo_offline.sh 一致）
log "  强制重启 ros2 daemon 以刷新发现缓存 ..."
_run_as_user 'ros2 daemon stop >/dev/null 2>&1; ros2 daemon start >/dev/null 2>&1; sleep 1'

log "  探测 ROS 图里的 VLM 节点 ..."
NODES="$(_run_as_user 'ros2 node list 2>/dev/null | grep -Ei "vlm" || true')"
if [[ -z "$NODES" ]]; then
  err "  子 shell env 已对齐，仍然看不到 vlm* 节点"
  err "  请在原 launch 终端里 ros2 node list 确认节点还活着"
  exit 1
fi
log "  发现节点："
echo "$NODES" | sed 's/^/    /'

REAL_NODE="$(echo "$NODES" | grep -x "$VLM_NODE_NAME" | head -1)"
[[ -z "$REAL_NODE" ]] && REAL_NODE="$(echo "$NODES" | grep -E 'vlm_scene' | head -1)"
[[ -z "$REAL_NODE" ]] && REAL_NODE="$(echo "$NODES" | head -1)"
log "  选中节点： $REAL_NODE"

# ---- Key 探测：env > keys.py 常量 ----
# keys.py 已在 vlm_scene/providers/keys.py:24 预置了 DASHSCOPE_API_KEY，
# 这里再兜底判断一次，避免"忘记 export env 又忘了改 keys.py"直接 500。
KEYS_PY_DEFAULT="${KEYS_PY:-$(dirname "$0")/../ros2_ws/src/vlm_scene/vlm_scene/providers/keys.py}"
key_in_file() {
  local var="$1"
  local file="$2"
  [[ -f "$file" ]] || return 1
  # 匹配形如：VAR: str = "sk-xxxxx"  且非空
  grep -Eq "^${var}[[:space:]]*:[[:space:]]*str[[:space:]]*=[[:space:]]*\"[^\"]+\"" "$file"
}

if [[ "$TARGET_PROVIDER" == "qwen_vl" ]]; then
  if [[ -n "${DASHSCOPE_API_KEY:-}" ]]; then
    ok "env DASHSCOPE_API_KEY 已设置，将优先使用环境变量"
  elif key_in_file "DASHSCOPE_API_KEY" "$KEYS_PY_DEFAULT"; then
    ok "已在 keys.py 中检测到 DASHSCOPE_API_KEY（第 24 行）"
  else
    warn "DASHSCOPE_API_KEY 既未 export，也未写入 keys.py，qwen_vl 会调用失败。"
    warn "  处理办法二选一："
    warn "    A. export DASHSCOPE_API_KEY=sk-xxx"
    warn "    B. 直接编辑 ros2_ws/src/vlm_scene/vlm_scene/providers/keys.py 第 24 行"
  fi
elif [[ "$TARGET_PROVIDER" == "openai_vision" ]]; then
  if [[ -z "${OPENAI_API_KEY:-}" ]] && ! key_in_file "OPENAI_API_KEY" "$KEYS_PY_DEFAULT"; then
    warn "OPENAI_API_KEY 既未 export，也未写入 keys.py，openai_vision 会调用失败。"
    warn "  处理办法二选一："
    warn "    A. export OPENAI_API_KEY=sk-xxx"
    warn "    B. 编辑 keys.py 第 37 行 OPENAI_API_KEY"
  fi
fi

set +e
_run_as_user "ros2 param set '$REAL_NODE' provider '$TARGET_PROVIDER'"
RC=$?
set -e

if [[ $RC -ne 0 ]]; then
  err "切换失败。节点 $REAL_NODE 未声明 'provider' 参数或参数服务未起。"
  exit 1
fi

ok "provider 已切回。请在网页确认："
ok "  · 场景理解 徽标：蓝色 · 【云端·通义千问VL】"
ok "  · 新一轮场景描述文本更加自然（带情境理解、动作建议），与本地模式形成对比"
ok "  · 若之前触发过安全事件，counter 数值不会清零，可直观对比"

echo
log "如果要重新进入离线模式，执行： sudo bash scripts/demo_offline.sh"
echo
