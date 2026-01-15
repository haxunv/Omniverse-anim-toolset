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
    GPTSAPI = "gptsapi"


# 预设的 Replicate 模型
REPLICATE_MODELS = {
    "ic-light": "lllyasviel/ic-light:6d596855e8d93eb0ef2e923602c21c7df3ad58a3c60c47c4ee2c3c30d6ba8e1b",
    "flux-relight": "zsxkib/flux-pulid:a]b0a5e7be384faab45f4b27b5c",  # 占位，需要实际模型ID
}

# 预设的 GPTSapi 模型
GPTSAPI_MODELS = {
    "gemini-3-pro-image-preview": "gemini-3-pro-image-preview",
    "gemini-2.0-flash-exp-image-generation": "gemini-2.0-flash-exp-image-generation",
}

# 默认模型
DEFAULT_REPLICATE_MODEL = "ic-light"
DEFAULT_GPTSAPI_MODEL = "gemini-3-pro-image-preview"


class RelightImageClient:
    """
    图像重打光生成客户端。
    """

    # 默认 API URL
    DEFAULT_REPLICATE_URL = "https://api.replicate.com/v1"
    DEFAULT_GPTSAPI_URL = "https://api.gptsapi.net"

    def __init__(
        self,
        provider: RelightProvider = RelightProvider.REPLICATE,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None
    ):
        """
        初始化客户端。

        Args:
            provider: 服务提供商
            api_key: API 密钥
            model: 模型名称/ID
            base_url: 自定义 API URL（用于代理）
        """
        self._provider = provider
        self._api_key = api_key or ""
        
        # 根据 provider 设置默认值
        if provider == RelightProvider.GPTSAPI:
            self._model = model or DEFAULT_GPTSAPI_MODEL
            self._base_url = base_url or self.DEFAULT_GPTSAPI_URL
        else:
            self._model = model or DEFAULT_REPLICATE_MODEL
            self._base_url = base_url or self.DEFAULT_REPLICATE_URL
        
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

    def set_base_url(self, base_url: str) -> None:
        """设置自定义 API URL。"""
        self._base_url = base_url if base_url else self.DEFAULT_REPLICATE_URL

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
            elif self._provider == RelightProvider.GPTSAPI:
                return self._generate_gptsapi(
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
            url = f"{self._base_url}/predictions"
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
            poll_url = f"{self._base_url}/predictions/{prediction_id}"
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
                        result_image_url = output[0] if isinstance(output, list) else output
                        
                        # 下载图像
                        download_success, download_msg = self._download_image(result_image_url, output_path)
                        
                        if not download_success:
                            # 尝试带认证下载
                            download_success, download_msg = self._download_image(
                                result_image_url, output_path, self._api_key
                            )
                        
                        if download_success:
                            msg = f"Relit image generated: {output_path}"
                            safe_log(f"[RelightImageClient] {msg}")
                            if callback:
                                callback(True, msg, output_path)
                            return True, msg, output_path
                        else:
                            return False, f"Failed to download: {download_msg}", None
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

    # =========================================================================
    # GPTSapi API (gemini-3-pro-image-preview)
    # =========================================================================

    def _upload_image_to_host(self, image_path: str) -> Tuple[bool, str]:
        """
        上传图像到免费图床获取 URL。
        尝试多个图床服务以提高成功率。
        
        Returns:
            Tuple[bool, str]: (成功, URL 或错误消息)
        """
        # 获取文件名和 MIME 类型
        filename = os.path.basename(image_path)
        ext = os.path.splitext(image_path)[1].lower()
        mime_type = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}.get(ext, "image/png")
        
        # 读取原始二进制数据
        with open(image_path, "rb") as f:
            file_data = f.read()
        
        # 尝试多个图床服务
        upload_methods = [
            self._upload_to_catbox,
            self._upload_to_litterbox,
        ]
        
        last_error = ""
        for upload_method in upload_methods:
            try:
                success, result = upload_method(file_data, filename, mime_type)
                if success:
                    return True, result
                last_error = result
            except Exception as e:
                last_error = str(e)
                continue
        
        return False, f"All upload methods failed. Last error: {last_error}"

    def _upload_to_catbox(self, file_data: bytes, filename: str, mime_type: str) -> Tuple[bool, str]:
        """上传到 catbox.moe（永久存储）"""
        try:
            url = "https://catbox.moe/user/api.php"
            boundary = "----PythonFormBoundary7MA4YWxkTrZu0gW"
            
            # 构建 multipart body
            body = (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="reqtype"\r\n\r\n'
                f"fileupload\r\n"
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="fileToUpload"; filename="{filename}"\r\n'
                f"Content-Type: {mime_type}\r\n\r\n"
            ).encode("utf-8") + file_data + f"\r\n--{boundary}--\r\n".encode("utf-8")
            
            headers = {
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) OmniversePlugin/1.0",
            }
            
            req = urllib.request.Request(url, data=body, headers=headers, method="POST")
            
            with urllib.request.urlopen(req, timeout=60) as response:
                result_url = response.read().decode("utf-8").strip()
                if result_url.startswith("https://"):
                    safe_log(f"[RelightImageClient] Image uploaded to catbox: {result_url}")
                    return True, result_url
                else:
                    return False, f"Catbox upload failed: {result_url}"
                    
        except Exception as e:
            safe_log(f"[RelightImageClient] Catbox upload error: {e}")
            return False, f"Catbox error: {e}"

    def _upload_to_litterbox(self, file_data: bytes, filename: str, mime_type: str) -> Tuple[bool, str]:
        """上传到 litterbox.catbox.moe（临时存储，1小时后过期）"""
        try:
            url = "https://litterbox.catbox.moe/resources/internals/api.php"
            boundary = "----PythonFormBoundary7MA4YWxkTrZu0gW"
            
            # 构建 multipart body
            body = (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="reqtype"\r\n\r\n'
                f"fileupload\r\n"
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="time"\r\n\r\n'
                f"1h\r\n"
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="fileToUpload"; filename="{filename}"\r\n'
                f"Content-Type: {mime_type}\r\n\r\n"
            ).encode("utf-8") + file_data + f"\r\n--{boundary}--\r\n".encode("utf-8")
            
            headers = {
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) OmniversePlugin/1.0",
            }
            
            req = urllib.request.Request(url, data=body, headers=headers, method="POST")
            
            with urllib.request.urlopen(req, timeout=60) as response:
                result_url = response.read().decode("utf-8").strip()
                if result_url.startswith("https://"):
                    safe_log(f"[RelightImageClient] Image uploaded to litterbox: {result_url}")
                    return True, result_url
                else:
                    return False, f"Litterbox upload failed: {result_url}"
                    
        except Exception as e:
            safe_log(f"[RelightImageClient] Litterbox upload error: {e}")
            return False, f"Litterbox error: {e}"

    def _generate_gptsapi(
        self,
        source_image_path: str,
        lighting_description: str,
        output_path: str,
        callback: Optional[Callable] = None
    ) -> Tuple[bool, str, Optional[str]]:
        """
        使用 GPTSapi (Gemini) 生成重打光图像。
        
        API 文档:
        - 图生图: POST https://api.gptsapi.net/api/v3/google/{model}/image-edit
        - 查询结果: GET https://api.gptsapi.net/api/v3/predictions/{result_id}/result
        """
        try:
            # GPTSapi 需要图像 URL，不支持 base64 data URI
            # 先上传图像到图床获取 URL
            safe_log(f"[RelightImageClient] Uploading image to get URL...")
            upload_success, image_url = self._upload_image_to_host(source_image_path)
            
            if not upload_success:
                return False, f"Failed to upload image: {image_url}", None
            
            safe_log(f"[RelightImageClient] Image URL: {image_url}")

            # 获取模型名
            model_name = GPTSAPI_MODELS.get(self._model, self._model)

            safe_log(f"[RelightImageClient] Creating GPTSapi prediction with model: {model_name}")
            
            # 确保 base_url 是根域名
            base = self._base_url.rstrip("/")
            # 移除可能存在的 /api 后缀
            if base.endswith("/api"):
                base = base[:-4]
            
            # GPTSapi - 创建预测 (image-edit 接口)
            # 文档: POST https://api.gptsapi.net/api/v3/google/gemini-3-pro-image-preview/image-edit
            url = f"{base}/api/v3/google/{model_name}/image-edit"
            headers = {
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            }
            
            safe_log(f"[RelightImageClient] Request URL: {url}")
            
            # 构建请求体
            # 使用专门的 relight prompt 模板
            relight_prompt = f"Relight this image with the following lighting effect: {lighting_description}. Keep the subject and composition exactly the same, only change the lighting."
            
            # 使用上传后的图像 URL（不是 data URI）
            request_body = {
                "prompt": relight_prompt,
                "images": [image_url],  # 使用 HTTP URL
                "output_format": "png"
            }

            req = urllib.request.Request(
                url,
                data=json.dumps(request_body).encode("utf-8"),
                headers=headers,
                method="POST"
            )

            with urllib.request.urlopen(req, timeout=60) as response:
                result = json.loads(response.read().decode("utf-8"))
            
            # 检查响应
            if result.get("code") != 200 and result.get("message") != "success":
                error_msg = result.get("message", "Unknown error")
                return False, f"GPTSapi error: {error_msg}", None

            # 获取 result_id
            data = result.get("data", {})
            result_id = data.get("id")
            
            if not result_id:
                return False, "Failed to get result_id from GPTSapi", None

            safe_log(f"[RelightImageClient] GPTSapi prediction created: {result_id}")

            # 轮询等待结果
            # 文档: GET https://api.gptsapi.net/api/v3/predictions/{result_id}/result
            poll_url = f"{base}/api/v3/predictions/{result_id}/result"
            max_wait = 300  # 最多等待5分钟
            poll_interval = 3
            elapsed = 0

            while elapsed < max_wait:
                time.sleep(poll_interval)
                elapsed += poll_interval
                
                req = urllib.request.Request(poll_url, headers=headers)
                try:
                    with urllib.request.urlopen(req, timeout=30) as response:
                        result = json.loads(response.read().decode("utf-8"))
                except urllib.error.HTTPError as e:
                    if e.code == 404:
                        # 还在处理中
                        safe_log(f"[RelightImageClient] GPTSapi status: processing... ({elapsed}s)")
                        continue
                    raise
                
                data = result.get("data", {})
                status = data.get("status", "")
                safe_log(f"[RelightImageClient] GPTSapi status: {status}")

                if status == "succeeded" or status == "completed":
                    # 获取输出图像
                    outputs = data.get("outputs", [])
                    if outputs:
                        result_image_url = outputs[0]
                        safe_log(f"[RelightImageClient] Result image URL: {result_image_url}")
                        
                        # 尝试下载图像（先不带认证，再带认证）
                        download_success, download_msg = self._download_image(result_image_url, output_path)
                        
                        if not download_success:
                            # 尝试带认证下载
                            safe_log(f"[RelightImageClient] Retrying with auth token...")
                            download_success, download_msg = self._download_image(
                                result_image_url, output_path, self._api_key
                            )
                        
                        if download_success:
                            msg = f"Relit image generated: {output_path}"
                            safe_log(f"[RelightImageClient] {msg}")
                            if callback:
                                callback(True, msg, output_path)
                            return True, msg, output_path
                        else:
                            msg = f"Failed to download result image: {download_msg}"
                            safe_log(f"[RelightImageClient] {msg}")
                            if callback:
                                callback(False, msg, None)
                            return False, msg, None
                    else:
                        return False, "No output from GPTSapi prediction", None

                elif status == "failed":
                    error = data.get("error", "Unknown error")
                    return False, f"GPTSapi prediction failed: {error}", None

            return False, "GPTSapi prediction timed out", None

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

    def _download_image(self, url: str, output_path: str, auth_token: str = None) -> Tuple[bool, str]:
        """
        下载图像到本地。
        
        Returns:
            Tuple[bool, str]: (成功, 错误消息或成功消息)
        """
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) OmniversePlugin/1.0",
            }
            
            # 如果提供了认证 token，添加到 headers
            if auth_token:
                headers["Authorization"] = f"Bearer {auth_token}"
                headers["x-api-key"] = auth_token
            
            safe_log(f"[RelightImageClient] Downloading from: {url}")
            
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=60) as response:
                with open(output_path, "wb") as f:
                    f.write(response.read())
            
            safe_log(f"[RelightImageClient] Downloaded to: {output_path}")
            return True, "Download successful"
            
        except urllib.error.HTTPError as e:
            error_msg = f"HTTP Error {e.code}: {e.reason}"
            safe_log(f"[RelightImageClient] Download error: {error_msg}")
            return False, error_msg
            
        except Exception as e:
            error_msg = str(e)
            safe_log(f"[RelightImageClient] Download error: {error_msg}")
            return False, error_msg

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
                url = f"{self._base_url}/models"
                headers = {
                    "Authorization": f"Bearer {self._api_key}",
                }
                req = urllib.request.Request(url, headers=headers)
                
                with urllib.request.urlopen(req, timeout=10) as response:
                    if response.status == 200:
                        return True, "Replicate API connection successful"

            elif self._provider == RelightProvider.GPTSAPI:
                # 测试 GPTSapi - 根据官方文档使用 /v1/models 端点
                # 文档: curl https://api.gptsapi.net/v1/models -H "Authorization: Bearer $API_KEY"
                
                # 确保 base_url 是根域名
                base = self._base_url.rstrip("/")
                # 移除可能存在的 /api 后缀
                if base.endswith("/api"):
                    base = base[:-4]
                
                test_url = f"{base}/v1/models"
                
                headers = {
                    "Authorization": f"Bearer {self._api_key}",
                    "x-api-key": self._api_key,
                }
                
                safe_log(f"[RelightImageClient] Testing GPTSapi: {test_url}")
                
                req = urllib.request.Request(test_url, headers=headers)
                with urllib.request.urlopen(req, timeout=10) as response:
                    if response.status == 200:
                        return True, "GPTSapi connection successful"
                    
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


