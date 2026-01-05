# -*- coding: utf-8 -*-
"""
Render Capture 渲染采集模块
===========================

提供视口渲染图像采集功能。

主要功能:
    - capture_viewport: 采集当前视口图像
    - capture_to_file: 采集并保存到文件
    - get_viewport_info: 获取视口信息
"""

import os
import base64
from typing import Optional, Tuple
from datetime import datetime

from .stage_utils import safe_log


# =============================================================================
# 视口采集
# =============================================================================

def capture_viewport(
    output_path: Optional[str] = None,
    width: int = 1920,
    height: int = 1080
) -> Tuple[bool, str, Optional[str]]:
    """
    采集当前视口的渲染图像。

    Args:
        output_path: 输出文件路径，如果为 None 则自动生成
        width: 输出宽度
        height: 输出高度

    Returns:
        Tuple[bool, str, Optional[str]]: (成功, 消息, 文件路径)
    """
    try:
        import omni.kit.viewport.utility as viewport_utils
        from omni.kit.viewport.utility import get_active_viewport
        
        # 获取活动视口
        viewport = get_active_viewport()
        if not viewport:
            return False, "No active viewport found", None

        # 生成输出路径
        if not output_path:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_path = os.path.join(
                os.path.expanduser("~"),
                "Pictures",
                f"omniverse_capture_{timestamp}.png"
            )

        # 确保目录存在
        output_dir = os.path.dirname(output_path)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir)

        # 使用 capture_viewport_to_file
        try:
            from omni.kit.viewport.utility import capture_viewport_to_file
            
            capture_viewport_to_file(
                viewport,
                output_path,
            )
            
            msg = f"Viewport captured to: {output_path}"
            safe_log(f"[RenderCapture] {msg}")
            return True, msg, output_path
            
        except ImportError:
            # 备用方法：使用 omni.kit.capture
            try:
                import omni.kit.capture.viewport
                
                capture_instance = omni.kit.capture.viewport.CaptureExtension.get_instance()
                if capture_instance:
                    capture_instance.capture_next_frame(output_path)
                    msg = f"Viewport captured to: {output_path}"
                    safe_log(f"[RenderCapture] {msg}")
                    return True, msg, output_path
                    
            except ImportError:
                pass

        return False, "Capture API not available", None

    except Exception as e:
        msg = f"Error capturing viewport: {e}"
        safe_log(f"[RenderCapture] {msg}")
        return False, msg, None


def capture_viewport_async(
    output_path: str,
    callback=None,
    width: int = 1920,
    height: int = 1080
) -> bool:
    """
    异步采集视口图像。

    Args:
        output_path: 输出文件路径
        callback: 完成回调函数 callback(success, path)
        width: 输出宽度
        height: 输出高度

    Returns:
        bool: 是否成功启动采集
    """
    try:
        import omni.kit.viewport.utility as viewport_utils
        from omni.kit.viewport.utility import get_active_viewport
        import asyncio

        viewport = get_active_viewport()
        if not viewport:
            if callback:
                callback(False, None)
            return False

        async def do_capture():
            try:
                from omni.kit.viewport.utility import capture_viewport_to_file
                
                # 确保目录存在
                output_dir = os.path.dirname(output_path)
                if output_dir and not os.path.exists(output_dir):
                    os.makedirs(output_dir)

                capture_viewport_to_file(viewport, output_path)
                
                if callback:
                    callback(True, output_path)
                    
            except Exception as e:
                safe_log(f"[RenderCapture] Async capture error: {e}")
                if callback:
                    callback(False, None)

        asyncio.ensure_future(do_capture())
        return True

    except Exception as e:
        safe_log(f"[RenderCapture] Error starting async capture: {e}")
        if callback:
            callback(False, None)
        return False


# =============================================================================
# 图像读取和编码
# =============================================================================

def read_image_as_base64(image_path: str) -> Optional[str]:
    """
    读取图像文件并转换为 base64 编码。

    Args:
        image_path: 图像文件路径

    Returns:
        Optional[str]: base64 编码字符串
    """
    if not os.path.exists(image_path):
        safe_log(f"[RenderCapture] Image not found: {image_path}")
        return None

    try:
        with open(image_path, "rb") as f:
            image_data = f.read()
        
        base64_str = base64.b64encode(image_data).decode("utf-8")
        return base64_str

    except Exception as e:
        safe_log(f"[RenderCapture] Error reading image: {e}")
        return None


def get_image_mime_type(image_path: str) -> str:
    """
    根据文件扩展名获取 MIME 类型。

    Args:
        image_path: 图像文件路径

    Returns:
        str: MIME 类型
    """
    ext = os.path.splitext(image_path)[1].lower()
    mime_types = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".webp": "image/webp",
        ".bmp": "image/bmp",
    }
    return mime_types.get(ext, "image/png")


# =============================================================================
# 视口信息
# =============================================================================

def get_viewport_info() -> dict:
    """
    获取当前视口的信息。

    Returns:
        dict: 视口信息
    """
    info = {
        "has_viewport": False,
        "resolution": None,
        "camera_path": None,
    }

    try:
        from omni.kit.viewport.utility import get_active_viewport
        
        viewport = get_active_viewport()
        if viewport:
            info["has_viewport"] = True
            
            # 获取分辨率
            try:
                resolution = viewport.resolution
                info["resolution"] = [resolution[0], resolution[1]]
            except Exception:
                pass

            # 获取相机路径
            try:
                camera_path = viewport.camera_path
                if camera_path:
                    info["camera_path"] = str(camera_path)
            except Exception:
                pass

    except ImportError:
        pass

    return info


def get_active_camera_path() -> Optional[str]:
    """
    获取当前活动视口的相机路径。

    Returns:
        Optional[str]: 相机路径
    """
    try:
        from omni.kit.viewport.utility import get_active_viewport
        
        viewport = get_active_viewport()
        if viewport:
            camera_path = viewport.camera_path
            if camera_path:
                return str(camera_path)
    except Exception:
        pass

    return None



