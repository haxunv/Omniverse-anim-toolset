# -*- coding: utf-8 -*-
"""
AI Camera ViewModel
===================

Manages AI camera shot generation state and business logic.
Uses the hierarchical Camera Rig system.
"""

from typing import Optional, Tuple, Dict, Any, List
import json

from .base_viewmodel import BaseViewModel

# Import camera rig system
from ..core.camera_rig import (
    create_camera_from_dict,
    CameraRigParams,
)

# Import helpers from camera_shot (for selection and bounding box)
from ..core.camera_shot import (
    get_selected_prim_path,
    get_prim_bounding_box,
)

# Try to import AI client
try:
    from ..ai.llm_client import OllamaClient, AutoClient
    HAS_AI = True
except ImportError:
    HAS_AI = False


class AICameraViewModel(BaseViewModel):
    """
    AI 镜头生成的 ViewModel
    
    功能:
        - 接收用户的自然语言描述
        - 调用 AI 生成镜头参数
        - 创建带动画的相机
    """
    
    def __init__(self):
        super().__init__()
        
        # 状态
        self._prompt: str = ""
        self._target_path: str = ""
        self._target_size: float = 1.0  # Detected object size
        self._target_center: Tuple[float, float, float] = (0, 0, 0)
        self._generated_params: Optional[Dict] = None
        self._last_camera_path: str = ""
        self._is_generating: bool = False
        
        # AI 客户端
        self._ai_client = None
        self._ai_backend = "none"
        self._model_name = "qwen3:8b"
        
        # 参数
        self._fps: float = 24.0
        
        # 初始化 AI
        self._init_ai_client()
        
        # 回调
        self._data_changed_callbacks = []
    
    def _init_ai_client(self):
        """初始化 AI 客户端"""
        if not HAS_AI:
            self._ai_backend = "not_installed"
            return
        
        try:
            # 尝试使用 Ollama
            client = OllamaClient(model=self._model_name)
            if client.is_available():
                self._ai_client = client
                self._ai_backend = f"Ollama ({self._model_name})"
                self.log(f"✓ AI Backend: {self._ai_backend}")
                return
        except Exception as e:
            self.log(f"Ollama init failed: {e}")
        
        self._ai_backend = "not_available"
        self.log("⚠ No AI backend available")
    
    # =========================================================================
    # 属性
    # =========================================================================
    
    @property
    def prompt(self) -> str:
        return self._prompt
    
    @prompt.setter
    def prompt(self, value: str):
        self._prompt = value
        self._notify_data_changed()
    
    @property
    def target_path(self) -> str:
        return self._target_path
    
    @target_path.setter
    def target_path(self, value: str):
        self._target_path = value
        self._notify_data_changed()
    
    @property
    def generated_params(self) -> Optional[Dict]:
        return self._generated_params
    
    @property
    def last_camera_path(self) -> str:
        return self._last_camera_path
    
    @property
    def is_generating(self) -> bool:
        return self._is_generating
    
    @property
    def ai_backend(self) -> str:
        return self._ai_backend
    
    @property
    def is_ai_available(self) -> bool:
        return self._ai_client is not None
    
    @property
    def fps(self) -> float:
        return self._fps
    
    @fps.setter
    def fps(self, value: float):
        self._fps = max(1.0, min(120.0, value))
        self._notify_data_changed()
    
    @property
    def model_name(self) -> str:
        return self._model_name
    
    @model_name.setter
    def model_name(self, value: str):
        self._model_name = value
        self._init_ai_client()
        self._notify_data_changed()
    
    # =========================================================================
    # 命令
    # =========================================================================
    
    def set_target_from_selection(self) -> bool:
        """Set target from selection and detect its size"""
        path = get_selected_prim_path()
        if path:
            self._target_path = path
            
            # Get object size
            try:
                self._target_size, self._target_center = get_prim_bounding_box(path)
                self.log(f"Target = {path}")
                self.log(f"  Detected size: {self._target_size:.2f} units")
                self.log(f"  Center: ({self._target_center[0]:.1f}, {self._target_center[1]:.1f}, {self._target_center[2]:.1f})")
                
                # Warn if size seems wrong
                if self._target_size > 50:
                    self.log(f"  WARNING: Size {self._target_size:.1f} seems large!")
                    self.log(f"  You may want to select a more specific object.")
                elif self._target_size < 0.1:
                    self.log(f"  WARNING: Size {self._target_size:.2f} seems small!")
                    
            except Exception as e:
                self._target_size = 1.0
                self._target_center = (0, 0, 0)
                self.log(f"Could not detect size: {e}")
            
            self._notify_data_changed()
            return True
        else:
            self.log("Please select a target object first")
            return False
    
    @property
    def target_size(self) -> float:
        """Get detected target size"""
        return self._target_size
    
    @property
    def target_center(self) -> Tuple[float, float, float]:
        """Get detected target center"""
        return self._target_center
    
    def generate_shot_params(self) -> Tuple[bool, str]:
        """
        Generate shot parameters using AI
        
        Returns:
            (success, message)
        """
        if not self._prompt.strip():
            msg = "Please enter a shot description"
            self.log(msg)
            return False, msg
        
        if not self._ai_client:
            msg = "AI not available. Please ensure Ollama is running."
            self.log(msg)
            return False, msg
        
        self._is_generating = True
        self._notify_data_changed()
        
        try:
            # Build enhanced prompt with object size info
            enhanced_prompt = self._prompt
            
            # If we have a target, include its size in prompt
            if self._target_path and self._target_size > 0:
                obj_size = self._target_size
                obj_center = self._target_center
                
                # Calculate recommended values based on object size
                recommended_boom = max(5.0, obj_size * 5.0)
                
                # Movement references (proportional to object size)
                crane_subtle = obj_size * 0.1
                crane_slight = obj_size * 0.3
                crane_moderate = obj_size * 0.5  # Default
                crane_dramatic = obj_size * 1.0
                
                truck_small = obj_size * 0.3
                truck_medium = obj_size * 0.5
                truck_large = obj_size * 0.8
                
                self.log(f"Object size: {obj_size:.2f} units")
                self.log(f"Recommended boom: {recommended_boom:.1f} units")
                self.log(f"Crane moderate: {crane_moderate:.1f} units")
                
                # Add comprehensive size info to prompt
                enhanced_prompt = (
                    f"{self._prompt}\n\n"
                    f"[SCENE INFO - USE THESE VALUES:\n"
                    f"Object size: {obj_size:.1f} units\n"
                    f"Object center: ({obj_center[0]:.1f}, {obj_center[1]:.1f}, {obj_center[2]:.1f})\n"
                    f"\n"
                    f"REQUIRED boom.start_length: {recommended_boom:.1f} units\n"
                    f"REQUIRED boom.end_length: {recommended_boom:.1f} units (minimum)\n"
                    f"\n"
                    f"CRANE UP REFERENCE (transport.end_offset Y value):\n"
                    f"- subtle: {crane_subtle:.1f} units\n"
                    f"- slight: {crane_slight:.1f} units\n"
                    f"- moderate (DEFAULT): {crane_moderate:.1f} units\n"
                    f"- dramatic: {crane_dramatic:.1f} units\n"
                    f"\n"
                    f"TRUCK LEFT/RIGHT REFERENCE (transport.end_offset X value):\n"
                    f"- small: {truck_small:.1f} units\n"
                    f"- medium: {truck_medium:.1f} units\n"
                    f"- large: {truck_large:.1f} units\n"
                    f"\n"
                    f"If crane/transport is mentioned without intensity, use MODERATE values!\n"
                    f"Use focal_length 35mm for product shots.]"
                )
            
            self.log(f"Generating shot params...")
            self.log(f"Prompt: {self._prompt}")
            
            # Call AI with enhanced prompt
            result = self._ai_client.generate_shot_params(enhanced_prompt)
            
            if "error" in result:
                msg = f"❌ AI Error: {result.get('error')}"
                self.log(msg)
                self._is_generating = False
                self._notify_data_changed()
                return False, msg
            
            self._generated_params = result
            self.log("✓ Shot params generated:")
            self.log(json.dumps(result, indent=2, ensure_ascii=False)[:500])
            
            self._is_generating = False
            self._notify_data_changed()
            return True, "Shot params generated successfully"
            
        except Exception as e:
            msg = f"❌ Error: {str(e)}"
            self.log(msg)
            self._is_generating = False
            self._notify_data_changed()
            return False, msg
    
    def create_camera(self) -> Tuple[bool, str]:
        """
        Create camera with animation using the Camera Rig system.
        
        Returns:
            (success, message)
        """
        if not self._generated_params:
            msg = "Please generate shot params first"
            self.log(msg)
            return False, msg
        
        try:
            # Prepare params - inject target and fps
            params = dict(self._generated_params)
            params["fps"] = self._fps
            
            # If we have a target, set it in anchor
            if self._target_path:
                if "anchor" not in params:
                    params["anchor"] = {}
                params["anchor"]["target_prim"] = self._target_path
            
            # SAFETY CHECK: Ensure boom is large enough for good framing
            if self._target_size > 0 and "boom" in params:
                min_boom = self._target_size * 5.0  # 5x for good product shot framing
                current_boom_start = params["boom"].get("start_length", 5.0)
                current_boom_end = params["boom"].get("end_length", 5.0)
                
                if current_boom_start < min_boom:
                    self.log(f"WARNING: LLM set boom={current_boom_start}, but object is {self._target_size} units!")
                    self.log(f"         Auto-correcting boom to {min_boom:.1f} (5x object size)")
                    params["boom"]["start_length"] = min_boom
                
                if current_boom_end < min_boom * 0.4:  # Allow some dolly-in but not too close
                    params["boom"]["end_length"] = max(current_boom_end, min_boom * 0.5)
                    self.log(f"         Also adjusting end_length to {params['boom']['end_length']:.1f}")
            
            # SAFETY CHECK: Ensure transport values are proportional to object size
            if self._target_size > 0 and "transport" in params:
                transport = params["transport"]
                end_offset = transport.get("end_offset", [0, 0, 0])
                duration = transport.get("duration", 0)
                
                # If there's transport movement but values are too small, scale them up
                if duration > 0 and any(abs(v) > 0 for v in end_offset):
                    min_noticeable = self._target_size * 0.3  # At least 30% for visible movement
                    
                    # Check Y (crane up/down)
                    if abs(end_offset[1]) > 0 and abs(end_offset[1]) < min_noticeable:
                        moderate_y = self._target_size * 0.5
                        self.log(f"WARNING: Crane Y={end_offset[1]:.1f} too small for {self._target_size:.0f} unit object")
                        self.log(f"         Auto-correcting to moderate: {moderate_y:.1f}")
                        end_offset[1] = moderate_y if end_offset[1] > 0 else -moderate_y
                    
                    # Check X (truck left/right)
                    if abs(end_offset[0]) > 0 and abs(end_offset[0]) < min_noticeable:
                        moderate_x = self._target_size * 0.5
                        self.log(f"WARNING: Truck X={end_offset[0]:.1f} too small")
                        self.log(f"         Auto-correcting to: {moderate_x:.1f}")
                        end_offset[0] = moderate_x if end_offset[0] > 0 else -moderate_x
                    
                    params["transport"]["end_offset"] = end_offset
            
            self.log(f"Creating camera rig...")
            self.log(f"   Duration: {params.get('duration', 5.0)}s")
            if "boom" in params:
                self.log(f"   Boom: {params['boom'].get('start_length', 5.0):.1f} → {params['boom'].get('end_length', 5.0):.1f}")
            
            # Create camera using new rig system
            camera_path = create_camera_from_dict(params)
            
            self._last_camera_path = camera_path
            self.log(f"Camera created: {camera_path}")
            self._notify_data_changed()
            return True, f"Camera created: {camera_path}"
                
        except Exception as e:
            msg = f"Error: {str(e)}"
            self.log(msg)
            import traceback
            self.log(traceback.format_exc())
            return False, msg
    
    def generate_and_create(self) -> Tuple[bool, str]:
        """
        一键生成：生成参数并创建相机
        
        Returns:
            (成功标志, 消息)
        """
        # 先生成参数
        success, message = self.generate_shot_params()
        if not success:
            return False, message
        
        # 再创建相机
        return self.create_camera()
    
    def clear(self):
        """清空所有状态"""
        self._prompt = ""
        self._target_path = ""
        self._generated_params = None
        self._last_camera_path = ""
        self._notify_data_changed()
        self.log("Cleared all")
    
    def activate_camera(self) -> Tuple[bool, str]:
        """
        激活生成的相机为当前视角
        
        Returns:
            (成功标志, 消息)
        """
        if not self._last_camera_path:
            msg = "⚠ No camera created yet"
            self.log(msg)
            return False, msg
        
        try:
            import omni.kit.viewport.utility as viewport_util
            
            # 获取活动 viewport
            viewport = viewport_util.get_active_viewport()
            if viewport:
                # 设置相机
                viewport.set_active_camera(self._last_camera_path)
                self.log(f"✓ Activated camera: {self._last_camera_path}")
                return True, f"Camera activated: {self._last_camera_path}"
            else:
                msg = "⚠ No active viewport found"
                self.log(msg)
                return False, msg
                
        except ImportError:
            # 备用方法
            try:
                import omni.usd
                stage = omni.usd.get_context().get_stage()
                if stage:
                    from pxr import UsdGeom
                    # 设置为渲染相机
                    render_settings = stage.GetPrimAtPath("/Render/RenderSettings")
                    # 这个方法可能不适用于所有版本
                    self.log("⚠ Please manually set camera in viewport dropdown")
                    return False, "Please manually set camera in viewport"
            except Exception as e:
                msg = f"⚠ Could not activate camera: {e}"
                self.log(msg)
                return False, msg
        except Exception as e:
            msg = f"❌ Error: {e}"
            self.log(msg)
            return False, msg
    
    def play_animation(self) -> Tuple[bool, str]:
        """
        播放时间轴动画
        
        Returns:
            (成功标志, 消息)
        """
        try:
            import omni.timeline
            
            timeline = omni.timeline.get_timeline_interface()
            
            # 设置时间范围
            if self._generated_params:
                duration = self._generated_params.get("duration", 5.0)
                fps = self._fps
                end_frame = duration * fps
                timeline.set_start_time(0)
                timeline.set_end_time(end_frame / fps)
            
            # 回到开始
            timeline.set_current_time(0)
            
            # 播放
            timeline.play()
            
            self.log("▶ Playing animation...")
            return True, "Playing"
            
        except Exception as e:
            msg = f"⚠ Could not play: {e}"
            self.log(msg)
            return False, msg
    
    def stop_animation(self) -> Tuple[bool, str]:
        """停止播放"""
        try:
            import omni.timeline
            timeline = omni.timeline.get_timeline_interface()
            timeline.stop()
            timeline.set_current_time(0)
            self.log("⏹ Stopped")
            return True, "Stopped"
        except Exception as e:
            return False, str(e)
    
    def pause_animation(self) -> Tuple[bool, str]:
        """暂停播放"""
        try:
            import omni.timeline
            timeline = omni.timeline.get_timeline_interface()
            timeline.pause()
            self.log("⏸ Paused")
            return True, "Paused"
        except Exception as e:
            return False, str(e)
    
    # =========================================================================
    # 预设
    # =========================================================================
    
    def apply_preset(self, preset_name: str) -> bool:
        """
        Apply a preset
        
        Args:
            preset_name: Preset name
            
        Returns:
            Success flag
        """
        presets = {
            # Orbit shots
            "orbit_epic": "epic orbit shot around the character, rising from low angle, 6 seconds",
            "orbit_smooth": "smooth orbit shot, 180 degree rotation, 5 seconds",
            "orbit_low": "low angle orbit shot, looking up at the subject",
            "orbit_fast": "fast orbit shot, 360 degree rotation, dynamic feel",
            # Dolly shots
            "dolly_tense": "tense dolly in shot, pushing towards the subject, 3 seconds",
            "dolly_slow": "slow dolly in, building tension",
            "dolly_out": "dolly out shot, revealing the environment",
            # Crane shots
            "crane_reveal": "crane up revealing the landscape, ground to bird's eye view, 5 seconds",
            "crane_down": "crane down shot, descending from high angle",
            # Other
            "follow_chase": "chase follow shot, tracking the target with handheld feel, 4 seconds",
            "handheld": "handheld tracking shot with subtle breathing movement",
        }
        
        if preset_name in presets:
            self._prompt = presets[preset_name]
            self._notify_data_changed()
            self.log(f"Applied preset: {preset_name}")
            return True
        
        return False
    
    def get_preset_names(self) -> list:
        """Get all preset names"""
        return [
            # Row 1: Orbit
            ("orbit_epic", "Epic Orbit"),
            ("orbit_smooth", "Smooth Orbit"),
            ("orbit_low", "Low Angle Orbit"),
            ("orbit_fast", "Fast Orbit"),
            # Row 2: Dolly
            ("dolly_tense", "Tense Dolly In"),
            ("dolly_slow", "Slow Dolly"),
            ("dolly_out", "Dolly Out"),
            # Row 3: Crane & Other
            ("crane_reveal", "Crane Reveal"),
            ("crane_down", "Crane Down"),
            ("follow_chase", "Chase Follow"),
            ("handheld", "Handheld"),
        ]
    
    # =========================================================================
    # 回调管理
    # =========================================================================
    
    def add_data_changed_callback(self, callback):
        if callback not in self._data_changed_callbacks:
            self._data_changed_callbacks.append(callback)
    
    def remove_data_changed_callback(self, callback):
        if callback in self._data_changed_callbacks:
            self._data_changed_callbacks.remove(callback)
    
    def _notify_data_changed(self):
        for callback in self._data_changed_callbacks:
            try:
                callback()
            except Exception:
                pass

