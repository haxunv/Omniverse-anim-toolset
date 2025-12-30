# -*- coding: utf-8 -*-
"""
Camera Shot Generator
=====================

将 AI 生成的镜头参数转换为 USD 相机动画。

功能:
    - 解析镜头参数 JSON
    - 生成相机运动轨迹
    - 创建 USD 相机动画关键帧
    - 支持多种路径类型（orbit, dolly, crane, follow, linear）
    - 支持修饰器（handheld, shake）
"""

import math
from typing import Dict, Any, List, Tuple, Optional
from dataclasses import dataclass, field

try:
    from pxr import Usd, UsdGeom, Gf, Sdf, UsdLux
    HAS_USD = True
except ImportError:
    HAS_USD = False

try:
    import omni.usd
    HAS_OMNI = True
except ImportError:
    HAS_OMNI = False


@dataclass
class CameraFrame:
    """单帧相机数据"""
    time: float
    position: Tuple[float, float, float]
    rotation: Tuple[float, float, float]  # euler angles (degrees)
    focal_length: float = 35.0


@dataclass 
class ShotParams:
    """镜头参数"""
    shot_name: str = "Shot"
    duration: float = 5.0
    fps: float = 24.0
    
    # 路径参数
    path_type: str = "orbit"
    path_radius: float = 4.0
    path_angle: float = 180.0
    path_height_start: float = 1.5
    path_height_end: float = 1.5
    path_distance: float = 3.0
    
    # 约束参数
    constraint_type: str = "look_at"
    target_position: Tuple[float, float, float] = (0, 0, 0)
    
    # 修饰器
    handheld_intensity: float = 0.0
    shake_intensity: float = 0.0
    
    # 镜头参数
    focal_length_start: float = 35.0
    focal_length_end: float = 35.0
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ShotParams":
        """从字典创建参数"""
        params = cls()
        
        params.shot_name = data.get("shot_name", "Shot")
        params.duration = data.get("duration", 5.0)
        
        # 解析路径
        path = data.get("path", {})
        params.path_type = path.get("type", "orbit")
        params.path_radius = path.get("radius", 4.0)
        params.path_angle = path.get("angle", 180.0)
        params.path_distance = path.get("distance", 3.0)
        
        height = path.get("height", {})
        if isinstance(height, dict):
            params.path_height_start = height.get("start", 1.5)
            params.path_height_end = height.get("end", 1.5)
        else:
            params.path_height_start = height
            params.path_height_end = height
        
        # 解析修饰器
        modifiers = data.get("modifiers", [])
        for mod in modifiers:
            mod_type = mod.get("type", "")
            intensity = mod.get("intensity", 0.3)
            if mod_type == "handheld":
                params.handheld_intensity = intensity
            elif mod_type == "shake":
                params.shake_intensity = intensity
        
        # 解析镜头参数
        lens = data.get("lens", {})
        focal = lens.get("focal_length", 35)
        if isinstance(focal, dict):
            params.focal_length_start = focal.get("start", 35)
            params.focal_length_end = focal.get("end", 35)
        else:
            params.focal_length_start = focal
            params.focal_length_end = focal
        
        return params


class CameraShotGenerator:
    """
    相机镜头生成器
    
    将镜头参数转换为相机动画关键帧。
    """
    
    def __init__(self, params: ShotParams):
        self.params = params
        self._noise_seed = 42
    
    def generate_frames(self) -> List[CameraFrame]:
        """
        生成所有关键帧
        
        Returns:
            相机帧列表
        """
        frames = []
        total_frames = int(self.params.duration * self.params.fps)
        
        for frame_idx in range(total_frames + 1):
            t = frame_idx / total_frames  # 0 到 1 的进度
            time = frame_idx / self.params.fps
            
            # 计算基础位置
            position = self._calculate_position(t)
            
            # 计算旋转（看向目标）
            rotation = self._calculate_rotation(position)
            
            # 应用修饰器
            position, rotation = self._apply_modifiers(position, rotation, time)
            
            # 计算焦距
            focal = self._lerp(
                self.params.focal_length_start,
                self.params.focal_length_end,
                t
            )
            
            frames.append(CameraFrame(
                time=time,
                position=position,
                rotation=rotation,
                focal_length=focal
            ))
        
        return frames
    
    def _calculate_position(self, t: float) -> Tuple[float, float, float]:
        """计算 t 时刻的相机位置"""
        path_type = self.params.path_type
        target = self.params.target_position
        
        # 高度插值
        height = self._lerp(
            self.params.path_height_start,
            self.params.path_height_end,
            self._ease_in_out(t)
        )
        
        if path_type == "orbit":
            # Orbit motion
            # Start from +Z direction (behind the object, looking at it)
            # In USD: +Y is up, camera looks along -Z by default
            start_angle = math.pi / 2  # Start at 90 degrees (on +Z axis)
            end_angle = start_angle + math.radians(self.params.path_angle)
            angle = self._lerp(start_angle, end_angle, self._ease_in_out(t))
            
            # X-Z plane orbit (Y is up)
            x = target[0] + self.params.path_radius * math.cos(angle)
            z = target[2] + self.params.path_radius * math.sin(angle)
            y = target[1] + height
            
            return (x, y, z)
        
        elif path_type == "dolly":
            # Dolly (push/pull) motion
            # Start far, move closer (or vice versa based on distance sign)
            start_distance = self.params.path_distance
            end_distance = max(1.0, start_distance * 0.3)  # End at 30% of start distance
            
            distance = self._lerp(start_distance, end_distance, self._ease_in_out(t))
            
            # Camera on +Z axis, looking at target
            x = target[0]
            z = target[2] + distance
            y = target[1] + height
            
            return (x, y, z)
        
        elif path_type == "crane":
            # Crane (vertical) motion - camera on +Z axis
            x = target[0]
            z = target[2] + self.params.path_radius  # Distance from target
            y = target[1] + height  # Height changes via height parameter
            
            return (x, y, z)
        
        elif path_type == "linear":
            # Linear (horizontal pan) motion
            start_x = target[0] - self.params.path_radius
            end_x = target[0] + self.params.path_radius
            
            x = self._lerp(start_x, end_x, self._ease_in_out(t))
            z = target[2] + self.params.path_distance  # Distance from target
            y = target[1] + height
            
            return (x, y, z)
        
        else:
            # Default: static camera on +Z axis
            return (
                target[0],
                target[1] + height,
                target[2] + self.params.path_radius
            )
    
    def _calculate_rotation(
        self, 
        position: Tuple[float, float, float]
    ) -> Tuple[float, float, float]:
        """计算相机旋转（看向目标）"""
        if self.params.constraint_type != "look_at":
            return (0, 0, 0)
        
        target = self.params.target_position
        
        # 计算方向向量
        dx = target[0] - position[0]
        dy = target[1] - position[1]
        dz = target[2] - position[2]
        
        # 计算水平角度 (yaw)
        yaw = math.degrees(math.atan2(dx, dz))
        
        # 计算垂直角度 (pitch)
        horizontal_dist = math.sqrt(dx * dx + dz * dz)
        pitch = math.degrees(math.atan2(-dy, horizontal_dist))
        
        # roll 保持为 0
        roll = 0
        
        return (pitch, yaw, roll)
    
    def _apply_modifiers(
        self,
        position: Tuple[float, float, float],
        rotation: Tuple[float, float, float],
        time: float
    ) -> Tuple[Tuple[float, float, float], Tuple[float, float, float]]:
        """应用修饰器（手持、震动等）"""
        px, py, pz = position
        rx, ry, rz = rotation
        
        # 手持效果（低频噪声）
        if self.params.handheld_intensity > 0:
            intensity = self.params.handheld_intensity
            freq = 0.5  # 低频
            
            px += self._perlin_noise(time * freq, 0) * intensity * 0.1
            py += self._perlin_noise(time * freq, 1) * intensity * 0.05
            pz += self._perlin_noise(time * freq, 2) * intensity * 0.1
            
            rx += self._perlin_noise(time * freq, 3) * intensity * 2
            ry += self._perlin_noise(time * freq, 4) * intensity * 2
        
        # 震动效果（高频噪声）
        if self.params.shake_intensity > 0:
            intensity = self.params.shake_intensity
            freq = 8.0  # 高频
            
            px += self._perlin_noise(time * freq, 10) * intensity * 0.2
            py += self._perlin_noise(time * freq, 11) * intensity * 0.2
            pz += self._perlin_noise(time * freq, 12) * intensity * 0.2
            
            rx += self._perlin_noise(time * freq, 13) * intensity * 5
            ry += self._perlin_noise(time * freq, 14) * intensity * 5
            rz += self._perlin_noise(time * freq, 15) * intensity * 3
        
        return (px, py, pz), (rx, ry, rz)
    
    def _lerp(self, a: float, b: float, t: float) -> float:
        """线性插值"""
        return a + (b - a) * t
    
    def _ease_in_out(self, t: float) -> float:
        """缓入缓出曲线"""
        if t < 0.5:
            return 2 * t * t
        else:
            return 1 - pow(-2 * t + 2, 2) / 2
    
    def _perlin_noise(self, x: float, seed: int) -> float:
        """简化的 Perlin 噪声"""
        import math
        x = x + seed * 100
        return math.sin(x * 1.0) * 0.5 + math.sin(x * 2.3) * 0.3 + math.sin(x * 4.1) * 0.2


def apply_animation_to_camera(
    camera_path: str,
    frames: List[CameraFrame],
    fps: float = 24.0
) -> Tuple[bool, str]:
    """
    将动画应用到 USD 相机
    
    Args:
        camera_path: 相机 prim 路径
        frames: 相机帧列表
        fps: 帧率
        
    Returns:
        (成功标志, 消息)
    """
    if not HAS_USD or not HAS_OMNI:
        return False, "USD/Omniverse not available"
    
    try:
        stage = omni.usd.get_context().get_stage()
        if not stage:
            return False, "No stage available"
        
        camera_prim = stage.GetPrimAtPath(camera_path)
        if not camera_prim or not camera_prim.IsValid():
            return False, f"Camera not found: {camera_path}"
        
        # 获取 Xformable
        xformable = UsdGeom.Xformable(camera_prim)
        if not xformable:
            return False, "Camera is not Xformable"
        
        # 清除现有的 xform ops
        xformable.ClearXformOpOrder()
        
        # 创建变换操作
        translate_op = xformable.AddTranslateOp()
        rotate_op = xformable.AddRotateXYZOp()
        
        # 获取相机属性
        camera = UsdGeom.Camera(camera_prim)
        focal_attr = camera.GetFocalLengthAttr()
        
        # 应用关键帧
        for frame in frames:
            time_code = Usd.TimeCode(frame.time * fps)
            
            # 设置位置
            translate_op.Set(
                Gf.Vec3d(frame.position[0], frame.position[1], frame.position[2]),
                time_code
            )
            
            # 设置旋转
            rotate_op.Set(
                Gf.Vec3f(frame.rotation[0], frame.rotation[1], frame.rotation[2]),
                time_code
            )
            
            # 设置焦距
            if focal_attr:
                focal_attr.Set(frame.focal_length, time_code)
        
        return True, f"Applied {len(frames)} keyframes to {camera_path}"
        
    except Exception as e:
        return False, f"Error: {str(e)}"


def create_camera_with_animation(
    params: ShotParams,
    target_path: Optional[str] = None,
    camera_name: str = "AICamera"
) -> Tuple[bool, str, str]:
    """
    创建带动画的相机
    
    Args:
        params: 镜头参数
        target_path: 目标物体路径（用于确定看向位置）
        camera_name: 相机名称
        
    Returns:
        (成功标志, 消息, 相机路径)
    """
    if not HAS_USD or not HAS_OMNI:
        return False, "USD/Omniverse not available", ""
    
    try:
        stage = omni.usd.get_context().get_stage()
        if not stage:
            return False, "No stage available", ""
        
        # 获取目标位置
        target_pos = (0, 0, 0)
        if target_path:
            target_prim = stage.GetPrimAtPath(target_path)
            if target_prim and target_prim.IsValid():
                xformable = UsdGeom.Xformable(target_prim)
                if xformable:
                    world_transform = xformable.ComputeLocalToWorldTransform(
                        Usd.TimeCode.Default()
                    )
                    translation = world_transform.ExtractTranslation()
                    target_pos = (translation[0], translation[1], translation[2])
        
        # 更新参数中的目标位置
        params.target_position = target_pos
        
        # 创建相机
        camera_path = f"/World/{camera_name}"
        
        # 确保路径唯一
        counter = 1
        while stage.GetPrimAtPath(camera_path):
            camera_path = f"/World/{camera_name}_{counter}"
            counter += 1
        
        camera = UsdGeom.Camera.Define(stage, camera_path)
        if not camera:
            return False, "Failed to create camera", ""
        
        # 设置相机属性
        camera.GetFocalLengthAttr().Set(params.focal_length_start)
        camera.GetFocusDistanceAttr().Set(params.path_radius)
        
        # 生成动画
        generator = CameraShotGenerator(params)
        frames = generator.generate_frames()
        
        # 应用动画
        success, message = apply_animation_to_camera(
            camera_path, 
            frames, 
            params.fps
        )
        
        if success:
            return True, f"Created camera with {len(frames)} keyframes", camera_path
        else:
            return False, message, camera_path
            
    except Exception as e:
        return False, f"Error: {str(e)}", ""


def get_selected_prim_path() -> Optional[str]:
    """Get currently selected prim path"""
    if not HAS_OMNI:
        return None
    
    try:
        context = omni.usd.get_context()
        selection = context.get_selection()
        paths = selection.get_selected_prim_paths()
        return paths[0] if paths else None
    except Exception:
        return None


def get_prim_bounding_box(prim_path: str) -> Tuple[float, Tuple[float, float, float]]:
    """
    Get the bounding box size and center of a prim.
    
    Args:
        prim_path: Path to the prim
        
    Returns:
        (max_dimension, center_position)
        max_dimension: The largest dimension of the bounding box
        center_position: The center of the bounding box (x, y, z)
    """
    if not HAS_USD or not HAS_OMNI:
        return 1.0, (0, 0, 0)
    
    try:
        stage = omni.usd.get_context().get_stage()
        if not stage:
            return 1.0, (0, 0, 0)
        
        prim = stage.GetPrimAtPath(prim_path)
        if not prim or not prim.IsValid():
            return 1.0, (0, 0, 0)
        
        # Get bounding box
        boundable = UsdGeom.Boundable(prim)
        if boundable:
            # Try to get the extent
            extent_attr = boundable.GetExtentAttr()
            if extent_attr and extent_attr.HasValue():
                extent = extent_attr.Get()
                if extent and len(extent) >= 2:
                    min_pt = extent[0]
                    max_pt = extent[1]
                    
                    size_x = abs(max_pt[0] - min_pt[0])
                    size_y = abs(max_pt[1] - min_pt[1])
                    size_z = abs(max_pt[2] - min_pt[2])
                    
                    max_dim = max(size_x, size_y, size_z)
                    
                    # Get world transform for center
                    xformable = UsdGeom.Xformable(prim)
                    if xformable:
                        world_transform = xformable.ComputeLocalToWorldTransform(
                            Usd.TimeCode.Default()
                        )
                        translation = world_transform.ExtractTranslation()
                        center = (
                            translation[0] + (min_pt[0] + max_pt[0]) / 2,
                            translation[1] + (min_pt[1] + max_pt[1]) / 2,
                            translation[2] + (min_pt[2] + max_pt[2]) / 2
                        )
                        return max_dim, center
        
        # Fallback: try to compute bounds
        imageable = UsdGeom.Imageable(prim)
        if imageable:
            bounds = imageable.ComputeWorldBound(
                Usd.TimeCode.Default(),
                purpose1=UsdGeom.Tokens.default_
            )
            if bounds:
                bbox = bounds.GetBox()
                min_pt = bbox.GetMin()
                max_pt = bbox.GetMax()
                
                size_x = abs(max_pt[0] - min_pt[0])
                size_y = abs(max_pt[1] - min_pt[1])
                size_z = abs(max_pt[2] - min_pt[2])
                
                max_dim = max(size_x, size_y, size_z)
                center = (
                    (min_pt[0] + max_pt[0]) / 2,
                    (min_pt[1] + max_pt[1]) / 2,
                    (min_pt[2] + max_pt[2]) / 2
                )
                
                return max_dim, center
        
        return 1.0, (0, 0, 0)
        
    except Exception as e:
        print(f"Error getting bounding box: {e}")
        return 1.0, (0, 0, 0)


def calculate_safe_camera_distance(prim_path: str, multiplier: float = 3.0) -> float:
    """
    Calculate a safe camera distance based on object size.
    
    Args:
        prim_path: Path to the target prim
        multiplier: Multiplier for the object size (default 3.0 = 3x the object size)
        
    Returns:
        Safe distance for the camera
    """
    max_dim, _ = get_prim_bounding_box(prim_path)
    
    # Minimum distance of 2 units, or 3x the object size
    safe_distance = max(2.0, max_dim * multiplier)
    
    return safe_distance

