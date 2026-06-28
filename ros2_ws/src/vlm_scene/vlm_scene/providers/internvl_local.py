"""
vlm_scene.providers.internvl_local
----------------------------------
在 RDK S100 板端跑量化后的 InternVL2-2B（或 MiniCPM-V/Phi-3-Vision 等）。

⚠️ 目前为占位实现，原因：
  - 不同模型的导出工具链差异较大（hbdk / 蒸馏 / int8）；
  - 直接给一份能 import 失败也不报错的 stub，未来转模型后只需把
    `_load_local()` 与 `_infer()` 两个方法填进去即可，不影响节点接口。

预期接入路径（推荐）：
  1) 用 ms-swift / lmdeploy 把 InternVL2-2B 转 ONNX → BPU
  2) 加载 hbm 模型，preprocess（NV12 / RGB）→ forward → 解析生成 token
  3) 把生成的字符串塞回 VLMResponse.description

API Key / 环境变量：
  VLM_INTERNVL_MODEL_PATH   .hbm / .onnx 模型路径（必填）
  VLM_INTERNVL_TOKENIZER    Tokenizer 目录（HuggingFace 格式）
"""

from __future__ import annotations

import logging
import os
import time
from typing import Optional

from .base import BaseVLMProvider, VLMRequest, VLMResponse

logger = logging.getLogger("vlm_scene.internvl_local")


class InternVLLocalProvider(BaseVLMProvider):
    name = "internvl_local"
    default_model = "internvl2-2b-int8"

    def __init__(
        self,
        model: Optional[str] = None,
        model_path: Optional[str] = None,
        tokenizer_path: Optional[str] = None,
        **kwargs,
    ):
        super().__init__(model=model, **kwargs)
        self.model_path = model_path or os.getenv("VLM_INTERNVL_MODEL_PATH", "").strip()
        self.tokenizer_path = tokenizer_path or os.getenv("VLM_INTERNVL_TOKENIZER", "").strip()
        self._engine = None
        self._loaded = False
        # 不在构造函数里直接加载，懒加载到首次 describe，避免节点启动失败

    def healthcheck(self) -> bool:
        if not self.model_path:
            logger.warning("[InternVL] 缺少 VLM_INTERNVL_MODEL_PATH，节点将返回占位描述")
            return False
        if not os.path.exists(self.model_path):
            logger.warning("[InternVL] 模型文件不存在: %s", self.model_path)
            return False
        return True

    def describe(self, req: VLMRequest) -> VLMResponse:
        t0 = time.time()
        if not self._loaded:
            try:
                self._load_local()
                self._loaded = True
            except Exception as e:
                logger.error("[InternVL] 模型加载失败: %s", e)
                return VLMResponse(
                    description=("[InternVL 本地模型未就绪] 请先按 README 转换"
                                  "并设置 VLM_INTERNVL_MODEL_PATH。"),
                    provider=self.name, model=self.model,
                    elapsed_ms=(time.time() - t0) * 1000.0,
                )

        try:
            text = self._infer(req)
        except Exception as e:
            logger.error("[InternVL] 推理失败: %s", e)
            text = f"[InternVL 推理失败] {e}"

        return VLMResponse(
            description=text or "[InternVL 输出为空]",
            provider=self.name, model=self.model,
            elapsed_ms=(time.time() - t0) * 1000.0,
        )

    # ------------------------------------------------------------------
    # TODO：板端模型转换好后替换以下两个方法
    # ------------------------------------------------------------------
    def _load_local(self):
        """加载 BPU/ONNX 引擎 + tokenizer。"""
        raise NotImplementedError(
            "InternVLLocalProvider 暂未实现板端推理。将 InternVL2-2B 转成 "
            "hbm/onnx 后，把加载与生成代码补到 _load_local / _infer 即可。"
        )

    def _infer(self, req: VLMRequest) -> str:
        raise NotImplementedError
