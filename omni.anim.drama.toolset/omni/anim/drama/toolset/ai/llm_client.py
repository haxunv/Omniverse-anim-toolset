# -*- coding: utf-8 -*-
"""
LLM Client - Gemini API 封装
=============================

封装 Google Gemini API 调用，支持多模态输入（图像 + 文本）。

主要功能:
    - analyze_relight: 分析重打光图像差异
    - generate_light_operations: 生成灯光操作原语
"""

import os
import json
import base64
import asyncio
from typing import Dict, List, Optional, Any, Callable, Tuple
from concurrent.futures import ThreadPoolExecutor

from ..core.stage_utils import safe_log


# =============================================================================
# Gemini Client
# =============================================================================

class GeminiClient:
    """
    Google Gemini API 客户端封装。
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gemini-2.0-flash",
        base_url: Optional[str] = None
    ):
        """
        初始化 Gemini 客户端。

        Args:
            api_key: API 密钥，如果为 None 则从环境变量读取
            model: 模型名称
            base_url: 自定义 API 地址（用于代理）
        """
        self._api_key = api_key or os.environ.get("GEMINI_API_KEY", "")
        self._model = model
        self._base_url = base_url or "https://generativelanguage.googleapis.com/v1beta"
        self._executor = ThreadPoolExecutor(max_workers=2)
        
        # 检查是否有 google-genai 库
        self._use_sdk = False
        try:
            import google.generativeai as genai
            self._use_sdk = True
            if self._api_key:
                genai.configure(api_key=self._api_key)
        except ImportError:
            safe_log("[GeminiClient] google-generativeai not installed, using REST API")

    @property
    def is_configured(self) -> bool:
        """检查是否已配置 API Key。"""
        return bool(self._api_key)

    def set_api_key(self, api_key: str) -> None:
        """设置 API Key。"""
        self._api_key = api_key
        if self._use_sdk:
            try:
                import google.generativeai as genai
                genai.configure(api_key=api_key)
            except Exception:
                pass

    def set_model(self, model: str) -> None:
        """设置模型名称。"""
        self._model = model

    def set_base_url(self, base_url: str) -> None:
        """设置自定义 API 地址。"""
        self._base_url = base_url

    # =========================================================================
    # 核心分析方法
    # =========================================================================

    def analyze_relight(
        self,
        original_image_path: str,
        relit_image_path: str,
        scene_info: str,
        custom_prompt: Optional[str] = None,
        callback: Optional[Callable[[bool, str, Any], None]] = None
    ) -> Optional[Dict]:
        """
        分析原始图像和重打光图像的差异，生成灯光操作建议。

        Args:
            original_image_path: 原始渲染图路径
            relit_image_path: 重打光后的图像路径
            scene_info: 场景信息文本
            custom_prompt: 自定义提示词
            callback: 回调函数 callback(success, message, result)

        Returns:
            Dict: 分析结果，包含灯光操作原语
        """
        if not self.is_configured:
            error_msg = "API Key not configured"
            if callback:
                callback(False, error_msg, None)
            return None

        try:
            # 读取图像
            original_b64 = self._read_image_base64(original_image_path)
            relit_b64 = self._read_image_base64(relit_image_path)

            if not original_b64 or not relit_b64:
                error_msg = "Failed to read images"
                if callback:
                    callback(False, error_msg, None)
                return None

            # 构建 prompt
            from .prompt_templates import PromptTemplates
            if custom_prompt:
                # 用户提供了自定义提示词，与预制提示词组合
                prompt = PromptTemplates.get_relight_analysis_prompt_with_custom(scene_info, custom_prompt)
            else:
                # 使用纯预制提示词
                prompt = PromptTemplates.get_relight_analysis_prompt(scene_info)

            # 调用 API
            if self._use_sdk:
                result = self._call_sdk(
                    prompt=prompt,
                    images=[
                        {"data": original_b64, "mime_type": self._get_mime_type(original_image_path)},
                        {"data": relit_b64, "mime_type": self._get_mime_type(relit_image_path)},
                    ]
                )
            else:
                result = self._call_rest_api(
                    prompt=prompt,
                    images=[
                        {"data": original_b64, "mime_type": self._get_mime_type(original_image_path)},
                        {"data": relit_b64, "mime_type": self._get_mime_type(relit_image_path)},
                    ]
                )

            if result:
                # 解析结果
                from .primitive_parser import LightPrimitiveParser
                parsed = LightPrimitiveParser.parse_response(result)
                
                if callback:
                    callback(True, "Analysis completed", parsed)
                return parsed
            else:
                if callback:
                    callback(False, "No response from API", None)
                return None

        except Exception as e:
            error_msg = f"Error analyzing relight: {e}"
            safe_log(f"[GeminiClient] {error_msg}")
            if callback:
                callback(False, error_msg, None)
            return None

    def analyze_relight_async(
        self,
        original_image_path: str,
        relit_image_path: str,
        scene_info: str,
        custom_prompt: Optional[str] = None,
        callback: Optional[Callable[[bool, str, Any], None]] = None
    ) -> None:
        """
        异步分析重打光图像。

        Args:
            original_image_path: 原始渲染图路径
            relit_image_path: 重打光后的图像路径
            scene_info: 场景信息文本
            custom_prompt: 自定义提示词
            callback: 回调函数
        """
        def run():
            return self.analyze_relight(
                original_image_path,
                relit_image_path,
                scene_info,
                custom_prompt,
                callback
            )

        self._executor.submit(run)

    # =========================================================================
    # SDK 调用
    # =========================================================================

    def _call_sdk(
        self,
        prompt: str,
        images: List[Dict[str, str]]
    ) -> Optional[str]:
        """
        使用 Google GenAI SDK 调用 API。

        Args:
            prompt: 提示词
            images: 图像列表 [{"data": base64_str, "mime_type": "image/png"}, ...]

        Returns:
            str: API 响应文本
        """
        try:
            import google.generativeai as genai
            from PIL import Image
            import io

            model = genai.GenerativeModel(self._model)

            # 构建内容
            contents = []
            
            # 添加图像
            for img in images:
                image_data = base64.b64decode(img["data"])
                pil_image = Image.open(io.BytesIO(image_data))
                contents.append(pil_image)

            # 添加文本
            contents.append(prompt)

            # 生成
            response = model.generate_content(contents)
            
            if response and response.text:
                return response.text

        except Exception as e:
            safe_log(f"[GeminiClient] SDK call error: {e}")

        return None

    # =========================================================================
    # REST API 调用
    # =========================================================================

    def _call_rest_api(
        self,
        prompt: str,
        images: List[Dict[str, str]]
    ) -> Optional[str]:
        """
        Use REST API to call Gemini.

        Args:
            prompt: Prompt text
            images: Image list

        Returns:
            str: API response text
        """
        try:
            import urllib.request
            import urllib.error

            # Check if using custom base URL (third-party proxy)
            is_custom_endpoint = self._base_url and "generativelanguage.googleapis.com" not in self._base_url
            
            if is_custom_endpoint:
                # Third-party proxy: use header authentication
                url = f"{self._base_url}/models/{self._model}:generateContent"
                headers = {
                    "Content-Type": "application/json",
                    "x-api-key": self._api_key,
                    "Authorization": f"Bearer {self._api_key}",
                }
            else:
                # Official Google API: use URL parameter
                url = f"{self._base_url}/models/{self._model}:generateContent?key={self._api_key}"
                headers = {
                    "Content-Type": "application/json",
                }

            # Build request body
            parts = []
            
            # Add images
            for i, img in enumerate(images):
                parts.append({
                    "inline_data": {
                        "mime_type": img["mime_type"],
                        "data": img["data"]
                    }
                })
                # Add image description
                if i == 0:
                    parts.append({"text": "This is the original render:"})
                elif i == 1:
                    parts.append({"text": "This is the relit target image:"})

            # Add text prompt
            parts.append({"text": prompt})

            request_body = {
                "contents": [{
                    "parts": parts
                }],
                "generationConfig": {
                    "temperature": 0.4,
                    "topK": 32,
                    "topP": 1,
                    "maxOutputTokens": 4096,
                }
            }

            # Send request
            req = urllib.request.Request(
                url,
                data=json.dumps(request_body).encode("utf-8"),
                headers=headers,
                method="POST"
            )

            with urllib.request.urlopen(req, timeout=120) as response:
                result = json.loads(response.read().decode("utf-8"))
                
                # 提取文本
                if "candidates" in result and result["candidates"]:
                    candidate = result["candidates"][0]
                    if "content" in candidate and "parts" in candidate["content"]:
                        for part in candidate["content"]["parts"]:
                            if "text" in part:
                                return part["text"]

        except urllib.error.HTTPError as e:
            safe_log(f"[GeminiClient] HTTP Error: {e.code} - {e.reason}")
            try:
                error_body = e.read().decode("utf-8")
                safe_log(f"[GeminiClient] Error details: {error_body}")
            except Exception:
                pass
        except Exception as e:
            safe_log(f"[GeminiClient] REST API error: {e}")

        return None

    # =========================================================================
    # 工具方法
    # =========================================================================

    def _read_image_base64(self, image_path: str) -> Optional[str]:
        """读取图像并转换为 base64。"""
        if not os.path.exists(image_path):
            safe_log(f"[GeminiClient] Image not found: {image_path}")
            return None

        try:
            with open(image_path, "rb") as f:
                return base64.b64encode(f.read()).decode("utf-8")
        except Exception as e:
            safe_log(f"[GeminiClient] Error reading image: {e}")
            return None

    def _get_mime_type(self, file_path: str) -> str:
        """获取文件的 MIME 类型。"""
        ext = os.path.splitext(file_path)[1].lower()
        mime_types = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".webp": "image/webp",
        }
        return mime_types.get(ext, "image/png")

    # =========================================================================
    # 简单测试
    # =========================================================================

    def test_connection(self) -> Tuple[bool, str]:
        """
        Test API connection.

        Returns:
            Tuple[bool, str]: (success, message)
        """
        if not self.is_configured:
            return False, "API Key not configured"

        try:
            if self._use_sdk:
                import google.generativeai as genai
                model = genai.GenerativeModel(self._model)
                response = model.generate_content("Hello, respond with 'OK' only.")
                if response and response.text:
                    return True, f"Connection successful: {response.text[:50]}"
            else:
                # REST API test
                import urllib.request
                
                # Check if using custom base URL (third-party proxy)
                is_custom_endpoint = self._base_url and "generativelanguage.googleapis.com" not in self._base_url
                
                if is_custom_endpoint:
                    # Third-party proxy: use header authentication
                    url = f"{self._base_url}/models/{self._model}:generateContent"
                    headers = {
                        "Content-Type": "application/json",
                        "x-api-key": self._api_key,
                        "Authorization": f"Bearer {self._api_key}",
                    }
                else:
                    # Official Google API: use URL parameter
                    url = f"{self._base_url}/models/{self._model}:generateContent?key={self._api_key}"
                    headers = {"Content-Type": "application/json"}
                
                request_body = {
                    "contents": [{"parts": [{"text": "Hello, respond with 'OK' only."}]}]
                }
                
                req = urllib.request.Request(
                    url,
                    data=json.dumps(request_body).encode("utf-8"),
                    headers=headers,
                    method="POST"
                )
                
                with urllib.request.urlopen(req, timeout=30) as response:
                    result = json.loads(response.read().decode("utf-8"))
                    return True, "Connection successful"

        except Exception as e:
            return False, f"Connection failed: {e}"

        return False, "Unknown error"

    def dispose(self) -> None:
        """清理资源。"""
        if self._executor:
            self._executor.shutdown(wait=False)

