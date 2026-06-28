"""
vlm_scene.providers.keys
------------------------
所有 VLM Provider 的默认 API Key / 模型 / Base URL 在此集中预设。

⚙️ 使用方法（二选一，按优先级）：
  1. 直接在本文件粘贴你的 API Key（推荐：本机部署）
  2. 通过环境变量覆盖（推荐：生产环境 / systemd）

读取优先级：
  构造参数 > 环境变量 > 本文件常量

🔒 安全提示：
  - 本文件包含明文 Key，不要 git push 到公开仓库
  - 建议把本文件加入 .gitignore，或保持 Key 为空，运行时由环境变量提供
"""

# =============================================================================
# 1. 通义千问 VL（DashScope）—— 默认推荐 provider
#
# 申请：https://bailian.console.aliyun.com/ → API-KEY 管理
# 价格：qwen-vl-plus ≈ ¥0.005/次，qwen-vl-max ≈ ¥0.02/次
# =============================================================================
DASHSCOPE_API_KEY: str = "sk-ws-H.RYYMHLX.pB1E.MEUCIQC4iBKVan293O43HL7rCqdkV8qL3eN8rovTxTbHj7hIxgIgLixmfkSOpDP0LJOTvdC-ZeM65hjCbhA-O74RFkIciSQ"   # ← 粘贴你的阿里云百炼 sk-xxxxxxxx
VLM_QWEN_MODEL: str = "qwen-vl-plus"
VLM_QWEN_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"


# =============================================================================
# 2. OpenAI 兼容 API（OpenAI / 智谱 GLM-4V / Moonshot / 自建 vLLM 等）
#
# OpenAI 官方：       base=https://api.openai.com/v1                model=gpt-4o-mini
# 智谱 GLM-4V：       base=https://open.bigmodel.cn/api/paas/v4      model=glm-4v
# Moonshot Kimi-VL：  base=https://api.moonshot.cn/v1                model=moonshot-v1-8k-vision-preview
# 自建 vLLM/LMDeploy：base=http://your-server:8000/v1                model=<your-model>
# =============================================================================
OPENAI_API_KEY: str = ""      # ← 通用 OpenAI 兼容服务的 API Key
VLM_OPENAI_MODEL: str = "gpt-4o-mini"
VLM_OPENAI_BASE_URL: str = "https://api.openai.com/v1"


# =============================================================================
# 3. DeepSeek（纯文本，无视觉 API）
#
# ⚠️ DeepSeek 目前没视觉模型，只能依检测列表"脑补"画面
# 仅作兜底；想要真视觉请用 qwen_vl 或 openai_vision
# 申请：https://platform.deepseek.com/
# =============================================================================
DEEPSEEK_API_KEY: str = ""    # ← 粘贴你的 DeepSeek sk-xxxxxxxx
VLM_DEEPSEEK_MODEL: str = "deepseek-chat"
VLM_DEEPSEEK_BASE_URL: str = "https://api.deepseek.com/v1"


# =============================================================================
# 4. 本地 InternVL2（RDK S100 BPU 上跑，占位中）
#
# 暂未实现，需要把 InternVL2-2B 转成 BPU hbm 模型，后续接 hbDNN runtime
# =============================================================================
INTERNVL_MODEL_PATH: str = "/home/sunrise/models/internvl2_2b.hbm"


# =============================================================================
# 通用：通过环境变量覆盖本文件（运行时调用）
# 优先级：env > 本文件常量
# =============================================================================
import os as _os


def get(name: str, fallback: str = "") -> str:
    """
    读取一个配置值。先看环境变量，再用本文件同名常量，最后用 fallback。

    用法：
        from vlm_scene.providers import keys
        api_key = keys.get("DASHSCOPE_API_KEY")
        model   = keys.get("VLM_QWEN_MODEL", "qwen-vl-plus")
    """
    env_val = _os.getenv(name, "").strip()
    if env_val:
        return env_val
    const_val = globals().get(name, "")
    if isinstance(const_val, str) and const_val:
        return const_val
    return fallback
