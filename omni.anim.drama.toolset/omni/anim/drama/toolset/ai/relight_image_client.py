# -*- coding: utf-8 -*-
"""
Relight Image Client - 图像重打光生成 API 封装
==============================================

封装图像重打光生成服务 API 调用，支持多种后端。

支持的服务:
    - Replicate (ic-light, flux-relight 等模型)
    - 可扩展支持其他服务

主要功能:
    - generate_relit_image: 根据描述生成重打光图像
"""

import os
import json
import base64
import time
import urllib.request
import urllib.error
from typing import Dict, Optional, Tuple, Callable
from enum import Enum

from ..core.stage_utils import safe_log


class RelightProvider(Enum):
    """支持的 Relight 服务提供商"""
    REPLICATE = "replicate"
    # 可扩展其他服务
    # COMFYUI = "comfyui"
    # STABILITY = "stability"


# 预设的 Replicate 模型
REPLICATE_MODELS = {
    "ic-light": "lllyasviel/ic-light:6d596855e8d93eb0ef2e923602c21c7df3ad58a3c60c47c4ee2c3c30d6ba8e1b",
    "flux-relight": "zsxkib/flux-pulid:a]b0a5e7be384faab45f4b27b5c",  # 占位，需要实际模型ID
}

# 默认模型
DEFAULT_REPLICATE_MODEL = "ic-light"


class RelightImageClient:
    """
    图像重打光生成客户端。
    """

    def __init__(
        self,
        provider: RelightProvider = RelightProvider.REPLICATE,
        api_key: Optional[str] = None,
        model: Optional[str] = None
    ):
        """
        初始化客户端。

        Args:
            provider: 服务提供商
            api_key: API 密钥
            model: 模型名称/ID
        """
        self._provider = provider
        self._api_key = api_key or ""
        self._model = model or DEFAULT_REPLICATE_MODEL
        
    @property
    def is_configured(self) -> bool:
        """检查是否已配置。"""
        return bool(self._api_key)

    def set_api_key(self, api_key: str) -> None:
        """设置 API Key。"""
        self._api_key = api_key

    def set_model(self, model: str) -> None:
        """设置模型。"""
        self._model = model

    def set_provider(self, provider: RelightProvider) -> None:
        """设置服务提供商。"""
        self._provider = provider

    # =========================================================================
    # 主要方法
    # =========================================================================

    def generate_relit_image(
        self,
        source_image_path: str,
        lighting_description: str,
        output_path: Optional[str] = None,
        callback: Optional[Callable[[bool, str, Optional[str]], None]] = None
    ) -> Tuple[bool, str, Optional[str]]:
        """
        生成重打光图像。

        Args:
            source_image_path: 源图像路径
            lighting_description: 灯光效果描述
            output_path: 输出路径，如果为 None 则自动生成
            callback: 回调函数 callback(success, message, output_path)

        Returns:
            Tuple[bool, str, Optional[str]]: (成功, 消息, 输出路径)
        """
        if not self.is_configured:
            msg = "API Key not configured"
            if callback:
                callback(False, msg, None)
            return False, msg, None

        if not os.path.exists(source_image_path):
            msg = f"Source image not found: {source_image_path}"
            if callback:
                callback(False, msg, None)
            return False, msg, None

        # 生成输出路径
        if not output_path:
            base_dir = os.path.dirname(source_image_path)
            base_name = os.path.splitext(os.path.basename(source_image_path))[0]
            output_path = os.path.join(base_dir, f"{base_name}_relit.png")

        try:
            if self._provider == RelightProvider.REPLICATE:
                return self._generate_replicate(
                    source_image_path,
                    lighting_description,
                    output_path,
                    callback
                )
            else:
                msg = f"Unsupported provider: {self._provider}"
                if callback:
                    callback(False, msg, None)
                return False, msg, None

        except Exception as e:
            msg = f"Error generating relit image: {e}"
            safe_log(f"[RelightImageClient] {msg}")
            if callback:
                callback(False, msg, None)
            return False, msg, None

    # =========================================================================
    # Replicate API
    # =========================================================================

    def _generate_replicate(
        self,
        source_image_path: str,
        lighting_description: str,
        output_path: str,
        callback: Optional[Callable] = None
    ) -> Tuple[bool, str, Optional[str]]:
        """
        使用 Replicate API 生成重打光图像。
        """
        try:
            # 读取图像为 base64
            with open(source_image_path, "rb") as f:
                image_data = base64.b64encode(f.read()).decode("utf-8")
            
            # 获取 MIME 类型
            ext = os.path.splitext(source_image_path)[1].lower()
            mime_type = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}.get(ext, "image/png")
            image_uri = f"data:{mime_type};base64,{image_data}"

            # 获取模型 ID
            model_id = REPLICATE_MODELS.get(self._model, self._model)

            # 创建预测
            safe_log(f"[RelightImageClient] Creating prediction with model: {model_id}")
            
            # Replicate API - 创建预测
            url = "https://api.replicate.com/v1/predictions"
            headers = {
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            }
            
            # 构建请求体 (ic-light 模型的参数)
            request_body = {
                "version": model_id.split(":")[-1] if ":" in model_id else model_id,
                "input": {
                    "image": image_uri,
                    "prompt": lighting_description,
                    "light_source": "Left Light",  # 默认左侧光
                    "num_samples": 1,
                }
            }

            req = urllib.request.Request(
                url,
                data=json.dumps(request_body).encode("utf-8"),
                headers=headers,
                method="POST"
            )

            with urllib.request.urlopen(req, timeout=30) as response:
                result = json.loads(response.read().decode("utf-8"))
                prediction_id = result.get("id")
                
            if not prediction_id:
                return False, "Failed to create prediction", None

            safe_log(f"[RelightImageClient] Prediction created: {prediction_id}")

            # 轮询等待结果
            poll_url = f"https://api.replicate.com/v1/predictions/{prediction_id}"
            max_wait = 300  # 最多等待5分钟
            poll_interval = 2
            elapsed = 0

            while elapsed < max_wait:
                req = urllib.request.Request(poll_url, headers=headers)
                with urllib.request.urlopen(req, timeout=30) as response:
                    result = json.loads(response.read().decode("utf-8"))
                
                status = result.get("status")
                safe_log(f"[RelightImageClient] Status: {status}")

                if status == "succeeded":
                    # 获取输出图像
                    output = result.get("output")
                    if output:
                        # output 可能是列表或单个 URL
                        image_url = output[0] if isinstance(output, list) else output
                        
                        # 下载图像
                        self._download_image(image_url, output_path)
                        
                        msg = f"Relit image generated: {output_path}"
                        safe_log(f"[RelightImageClient] {msg}")
                        if callback:
                            callback(True, msg, output_path)
                        return True, msg, output_path
                    else:
                        return False, "No output from prediction", None

                elif status == "failed":
                    error = result.get("error", "Unknown error")
                    return False, f"Prediction failed: {error}", None

                elif status == "canceled":
                    return False, "Prediction was canceled", None

                time.sleep(poll_interval)
                elapsed += poll_interval

            return False, "Prediction timed out", None

        except urllib.error.HTTPError as e:
            error_body = ""
            try:
                error_body = e.read().decode("utf-8")
            except Exception:
                pass
            msg = f"HTTP Error {e.code}: {e.reason}. {error_body}"
            safe_log(f"[RelightImageClient] {msg}")
            return False, msg, None

        except Exception as e:
            msg = f"Error: {e}"
            safe_log(f"[RelightImageClient] {msg}")
            return False, msg, None

    def _download_image(self, url: str, output_path: str) -> bool:
        """下载图像到本地。"""
        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=60) as response:
                with open(output_path, "wb") as f:
                    f.write(response.read())
            return True
        except Exception as e:
            safe_log(f"[RelightImageClient] Download error: {e}")
            return False

    # =========================================================================
    # 测试连接
    # =========================================================================

    def test_connection(self) -> Tuple[bool, str]:
        """
        测试 API 连接。

        Returns:
            Tuple[bool, str]: (成功, 消息)
        """
        if not self.is_configured:
            return False, "API Key not configured"

        try:
            if self._provider == RelightProvider.REPLICATE:
                # 测试 Replicate API
                url = "https://api.replicate.com/v1/models"
                headers = {
                    "Authorization": f"Bearer {self._api_key}",
                }
                req = urllib.request.Request(url, headers=headers)
                
                with urllib.request.urlopen(req, timeout=10) as response:
                    if response.status == 200:
                        return True, "Replicate API connection successful"
                    
            return False, "Connection test failed"

        except urllib.error.HTTPError as e:
            if e.code == 401:
                return False, "Invalid API key"
            return False, f"HTTP Error: {e.code} {e.reason}"
        except Exception as e:
            return False, f"Connection error: {e}"

    def dispose(self) -> None:
        """清理资源。"""
        pass

