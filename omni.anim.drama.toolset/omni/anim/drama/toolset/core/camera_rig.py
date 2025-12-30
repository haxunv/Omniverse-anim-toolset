# -*- coding: utf-8 -*-
"""
Camera Rig System - Hierarchical Camera Control
================================================

A professional, film-industry-standard camera rig system.
All complex camera movements are combinations of atomic operations on different "joints".

Hierarchy Structure:
    /CameraRig
        └── Root          (Layer 1: Anchor + Transport)
            └── Pivot     (Layer 2: Rotation around target)
                └── Boom   (Layer 2: Distance from target)
                    └── Head   (Layer 3: Camera orientation)
                        └── Camera  (Layer 4: Lens + Shake)

Author: AI Camera System
"""

import math
from dataclasses import dataclass, field
from typing import Optional, Tuple, List, Dict, Any
from enum import Enum

from pxr import Usd, UsdGeom, Gf, Sdf


# =============================================================================
# Data Classes for Atomic Operations
# =============================================================================

class EasingType(Enum):
    LINEAR = "linear"
    EASE_IN = "ease_in"
    EASE_OUT = "ease_out"
    EASE_IN_OUT = "ease_in_out"


class MovementType(Enum):
    LINEAR = "linear"
    BEZIER = "bezier"


@dataclass
class AnchorParams:
    """Layer 1: Set Anchor - Where the rig is placed"""
    target_prim: str = ""  # Prim path to attach to, empty = world origin
    initial_pos: Tuple[float, float, float] = (0, 0, 0)


@dataclass
class TransportParams:
    """Layer 1: Transport/Dolly - Root movement"""
    movement_type: MovementType = MovementType.LINEAR
    end_offset: Tuple[float, float, float] = (0, 0, 0)  # Relative movement
    duration: float = 0  # 0 = instant, >0 = animated
    easing: EasingType = EasingType.EASE_IN_OUT


@dataclass
class RotatePivotParams:
    """Layer 2: Rotate Pivot - Orbit around target"""
    axis: str = "Y"  # "Y" = horizontal orbit, "X" = vertical flip
    start_angle: float = 0
    end_angle: float = 0
    duration: float = 0
    easing: EasingType = EasingType.EASE_IN_OUT


@dataclass
class BoomParams:
    """Layer 2: Boom Length - Distance from center"""
    start_length: float = 5.0  # Initial distance
    end_length: float = 5.0    # Final distance (same = static)
    duration: float = 0
    easing: EasingType = EasingType.EASE_IN_OUT


@dataclass
class LookAtParams:
    """Layer 3: LookAt Target - What camera looks at"""
    target_prim: str = ""  # Prim to look at
    framing_offset: Tuple[float, float] = (0, 0)  # Screen-space offset for composition


@dataclass
class RollParams:
    """Layer 3: Roll - Dutch angle"""
    start_angle: float = 0
    end_angle: float = 0
    duration: float = 0
    easing: EasingType = EasingType.EASE_IN_OUT


@dataclass
class LensParams:
    """Layer 4: Lens Zoom"""
    start_focal_length: float = 35.0
    end_focal_length: float = 35.0
    duration: float = 0
    easing: EasingType = EasingType.EASE_IN_OUT


@dataclass
class ShakeParams:
    """Layer 4: Camera Shake"""
    intensity: float = 0  # 0 = no shake
    frequency: float = 1.0  # Low = handheld, High = earthquake
    seed: int = 0  # Random seed for reproducibility


@dataclass
class CameraRigParams:
    """Complete Camera Rig Parameters"""
    # Metadata
    name: str = "CameraShot"
    duration: float = 5.0
    fps: float = 24.0
    
    # Layer 1: Root
    anchor: AnchorParams = field(default_factory=AnchorParams)
    transport: TransportParams = field(default_factory=TransportParams)
    
    # Layer 2: Arm
    rotate_pivot: RotatePivotParams = field(default_factory=RotatePivotParams)
    boom: BoomParams = field(default_factory=BoomParams)
    
    # Layer 3: Head
    look_at: LookAtParams = field(default_factory=LookAtParams)
    roll: RollParams = field(default_factory=RollParams)
    
    # Layer 4: Lens & FX
    lens: LensParams = field(default_factory=LensParams)
    shake: ShakeParams = field(default_factory=ShakeParams)


# =============================================================================
# Camera Rig Builder
# =============================================================================

class CameraRigBuilder:
    """
    Builds and animates a hierarchical camera rig in USD.
    """
    
    def __init__(self, stage: Usd.Stage, params: CameraRigParams):
        self.stage = stage
        self.params = params
        self.total_frames = int(params.duration * params.fps)
        
        # Prim references (will be set during build)
        self.root_prim = None
        self.pivot_prim = None
        self.boom_prim = None
        self.head_prim = None
        self.camera_prim = None
        
        # Transform ops
        self.root_translate_op = None
        self.pivot_rotate_op = None
        self.boom_translate_op = None
        self.head_rotate_op = None
        self.camera_roll_op = None
        self.camera_shake_op = None
    
    def build(self) -> str:
        """Build the complete camera rig and return the camera path."""
        base_path = self._get_unique_path()
        
        # Build hierarchy
        self._build_root(base_path)
        self._build_pivot()
        self._build_boom()
        self._build_head()
        self._build_camera()
        
        # Apply animations
        self._animate_transport()
        self._animate_rotate_pivot()
        self._animate_boom()
        self._animate_look_at()
        self._animate_roll()
        self._animate_lens()
        self._animate_shake()
        
        return str(self.camera_prim.GetPath())
    
    def _get_unique_path(self) -> str:
        """Generate a unique path for the camera rig."""
        base = f"/World/CameraRig_{self.params.name}"
        path = base
        counter = 1
        while self.stage.GetPrimAtPath(path):
            path = f"{base}_{counter}"
            counter += 1
        return path
    
    # =========================================================================
    # Build Hierarchy
    # =========================================================================
    
    def _build_root(self, base_path: str):
        """Layer 1: Create root node (anchor point)."""
        self.root_prim = UsdGeom.Xform.Define(self.stage, base_path)
        xformable = UsdGeom.Xformable(self.root_prim.GetPrim())
        xformable.ClearXformOpOrder()
        
        # Set initial position
        self.root_translate_op = xformable.AddTranslateOp(
            opSuffix="anchor"
        )
        
        # Get anchor position
        anchor_pos = self._get_anchor_position()
        self.root_translate_op.Set(Gf.Vec3d(*anchor_pos))
    
    def _build_pivot(self):
        """Layer 2: Create pivot node (rotation control)."""
        pivot_path = f"{self.root_prim.GetPath()}/Pivot"
        self.pivot_prim = UsdGeom.Xform.Define(self.stage, pivot_path)
        xformable = UsdGeom.Xformable(self.pivot_prim.GetPrim())
        xformable.ClearXformOpOrder()
        
        # Add rotation ops for both axes
        axis = self.params.rotate_pivot.axis.upper()
        if axis == "Y":
            self.pivot_rotate_op = xformable.AddRotateYOp(opSuffix="orbit")
        elif axis == "X":
            self.pivot_rotate_op = xformable.AddRotateXOp(opSuffix="orbit")
        else:
            # Default to Y
            self.pivot_rotate_op = xformable.AddRotateYOp(opSuffix="orbit")
    
    def _build_boom(self):
        """Layer 2: Create boom node (distance control)."""
        boom_path = f"{self.pivot_prim.GetPath()}/Boom"
        self.boom_prim = UsdGeom.Xform.Define(self.stage, boom_path)
        xformable = UsdGeom.Xformable(self.boom_prim.GetPrim())
        xformable.ClearXformOpOrder()
        
        # Boom extends along -Z (camera looks along -Z, so boom pushes it back)
        self.boom_translate_op = xformable.AddTranslateOp(opSuffix="boom")
    
    def _build_head(self):
        """Layer 3: Create head node (look-at control)."""
        head_path = f"{self.boom_prim.GetPath()}/Head"
        self.head_prim = UsdGeom.Xform.Define(self.stage, head_path)
        xformable = UsdGeom.Xformable(self.head_prim.GetPrim())
        xformable.ClearXformOpOrder()
        
        # Head rotation for look-at adjustment
        self.head_rotate_op = xformable.AddRotateXYZOp(opSuffix="head")
    
    def _build_camera(self):
        """Layer 4: Create camera prim."""
        camera_path = f"{self.head_prim.GetPath()}/Camera"
        self.camera_prim = UsdGeom.Camera.Define(self.stage, camera_path)
        
        xformable = UsdGeom.Xformable(self.camera_prim.GetPrim())
        xformable.ClearXformOpOrder()
        
        # Roll rotation (Z axis)
        self.camera_roll_op = xformable.AddRotateZOp(opSuffix="roll")
        
        # Shake offset (separate translate op so it doesn't affect main animation)
        self.camera_shake_op = xformable.AddTranslateOp(opSuffix="shake")
        
        # Set initial lens params
        self.camera_prim.GetFocalLengthAttr().Set(self.params.lens.start_focal_length)
    
    # =========================================================================
    # Animation Methods
    # =========================================================================
    
    def _animate_transport(self):
        """Animate root node transport/dolly."""
        transport = self.params.transport
        if transport.end_offset == (0, 0, 0) or transport.duration <= 0:
            return
        
        anchor_pos = self._get_anchor_position()
        start_pos = Gf.Vec3d(*anchor_pos)
        end_pos = Gf.Vec3d(
            anchor_pos[0] + transport.end_offset[0],
            anchor_pos[1] + transport.end_offset[1],
            anchor_pos[2] + transport.end_offset[2]
        )
        
        transport_frames = int(transport.duration * self.params.fps)
        
        for frame in range(transport_frames + 1):
            t = frame / transport_frames
            t = self._apply_easing(t, transport.easing)
            
            pos = self._lerp_vec3(start_pos, end_pos, t)
            self.root_translate_op.Set(pos, Usd.TimeCode(frame))
    
    def _animate_rotate_pivot(self):
        """Animate pivot rotation (orbit)."""
        rotate = self.params.rotate_pivot
        
        start_angle = rotate.start_angle
        end_angle = rotate.end_angle
        
        for frame in range(self.total_frames + 1):
            t = frame / self.total_frames
            t = self._apply_easing(t, rotate.easing)
            
            angle = self._lerp(start_angle, end_angle, t)
            self.pivot_rotate_op.Set(angle, Usd.TimeCode(frame))
    
    def _animate_boom(self):
        """Animate boom length (distance from target)."""
        boom = self.params.boom
        
        for frame in range(self.total_frames + 1):
            t = frame / self.total_frames
            t = self._apply_easing(t, boom.easing)
            
            length = self._lerp(boom.start_length, boom.end_length, t)
            # Boom extends along +Z (away from target, camera looks at -Z)
            self.boom_translate_op.Set(Gf.Vec3d(0, 0, length), Usd.TimeCode(frame))
    
    def _animate_look_at(self):
        """Apply look-at rotation to head node."""
        look_at = self.params.look_at
        
        # For now, if we're using pivot rotation around target,
        # the camera naturally looks at target (since boom extends along Z).
        # LookAt adjustments would be for fine-tuning composition.
        
        # Apply framing offset as small rotation adjustments
        offset_x, offset_y = look_at.framing_offset
        
        # Convert screen offset to rotation (approximate)
        # Positive offset_x = look slightly right = negative Y rotation
        # Positive offset_y = look slightly up = negative X rotation
        adjust_yaw = -offset_x * 10  # Scale factor
        adjust_pitch = -offset_y * 10
        
        for frame in range(self.total_frames + 1):
            self.head_rotate_op.Set(
                Gf.Vec3f(adjust_pitch, adjust_yaw, 0),
                Usd.TimeCode(frame)
            )
    
    def _animate_roll(self):
        """Animate camera roll (Dutch angle)."""
        roll = self.params.roll
        
        for frame in range(self.total_frames + 1):
            t = frame / self.total_frames
            t = self._apply_easing(t, roll.easing)
            
            angle = self._lerp(roll.start_angle, roll.end_angle, t)
            self.camera_roll_op.Set(angle, Usd.TimeCode(frame))
    
    def _animate_lens(self):
        """Animate focal length (zoom)."""
        lens = self.params.lens
        focal_attr = self.camera_prim.GetFocalLengthAttr()
        
        for frame in range(self.total_frames + 1):
            t = frame / self.total_frames
            t = self._apply_easing(t, lens.easing)
            
            focal = self._lerp(lens.start_focal_length, lens.end_focal_length, t)
            focal_attr.Set(focal, Usd.TimeCode(frame))
    
    def _animate_shake(self):
        """Apply procedural camera shake."""
        shake = self.params.shake
        if shake.intensity <= 0:
            return
        
        import random
        random.seed(shake.seed)
        
        for frame in range(self.total_frames + 1):
            # Perlin-like noise using sine waves at different frequencies
            t = frame / self.params.fps
            
            # Multiple octaves of noise
            noise_x = self._procedural_noise(t, shake.frequency, shake.seed)
            noise_y = self._procedural_noise(t, shake.frequency * 1.3, shake.seed + 100)
            noise_z = self._procedural_noise(t, shake.frequency * 0.7, shake.seed + 200)
            
            offset = Gf.Vec3d(
                noise_x * shake.intensity,
                noise_y * shake.intensity,
                noise_z * shake.intensity * 0.5  # Less Z shake
            )
            
            self.camera_shake_op.Set(offset, Usd.TimeCode(frame))
    
    # =========================================================================
    # Helper Methods
    # =========================================================================
    
    def _get_anchor_position(self) -> Tuple[float, float, float]:
        """Get the anchor position (from target prim or initial_pos)."""
        anchor = self.params.anchor
        
        if anchor.target_prim:
            prim = self.stage.GetPrimAtPath(anchor.target_prim)
            if prim and prim.IsValid():
                xformable = UsdGeom.Xformable(prim)
                world_transform = xformable.ComputeLocalToWorldTransform(Usd.TimeCode.Default())
                translation = world_transform.ExtractTranslation()
                return (translation[0], translation[1], translation[2])
        
        return anchor.initial_pos
    
    def _lerp(self, a: float, b: float, t: float) -> float:
        """Linear interpolation."""
        return a + (b - a) * t
    
    def _lerp_vec3(self, a: Gf.Vec3d, b: Gf.Vec3d, t: float) -> Gf.Vec3d:
        """Linear interpolation for Vec3."""
        return Gf.Vec3d(
            self._lerp(a[0], b[0], t),
            self._lerp(a[1], b[1], t),
            self._lerp(a[2], b[2], t)
        )
    
    def _apply_easing(self, t: float, easing: EasingType) -> float:
        """Apply easing function."""
        if easing == EasingType.LINEAR:
            return t
        elif easing == EasingType.EASE_IN:
            return t * t
        elif easing == EasingType.EASE_OUT:
            return 1 - (1 - t) * (1 - t)
        elif easing == EasingType.EASE_IN_OUT:
            if t < 0.5:
                return 2 * t * t
            else:
                return 1 - pow(-2 * t + 2, 2) / 2
        return t
    
    def _procedural_noise(self, t: float, frequency: float, seed: int) -> float:
        """Generate procedural noise for shake effect."""
        # Simple multi-octave sine-based noise
        result = 0
        amplitude = 1.0
        freq = frequency
        
        for i in range(3):  # 3 octaves
            result += amplitude * math.sin(t * freq * 2 * math.pi + seed * 0.1)
            amplitude *= 0.5
            freq *= 2
        
        return result


# =============================================================================
# High-Level API
# =============================================================================

def create_camera_rig(params: CameraRigParams) -> str:
    """
    Create a camera rig with the given parameters.
    
    Returns the camera prim path.
    """
    import omni.usd
    
    stage = omni.usd.get_context().get_stage()
    if not stage:
        raise RuntimeError("No USD stage available")
    
    builder = CameraRigBuilder(stage, params)
    return builder.build()


def create_camera_from_dict(params_dict: Dict[str, Any]) -> str:
    """
    Create a camera rig from a dictionary (for AI/JSON input).
    
    Example input:
    {
        "name": "HeroShot",
        "duration": 6.0,
        "anchor": {
            "target_prim": "/World/Character"
        },
        "rotate_pivot": {
            "axis": "Y",
            "start_angle": 0,
            "end_angle": 360
        },
        "boom": {
            "start_length": 5.0,
            "end_length": 5.0
        },
        "lens": {
            "start_focal_length": 35,
            "end_focal_length": 85
        }
    }
    """
    params = CameraRigParams()
    
    # Metadata
    params.name = params_dict.get("name", "CameraShot")
    params.duration = params_dict.get("duration", 5.0)
    params.fps = params_dict.get("fps", 24.0)
    
    # Layer 1: Anchor
    if "anchor" in params_dict:
        a = params_dict["anchor"]
        params.anchor.target_prim = a.get("target_prim", "")
        params.anchor.initial_pos = tuple(a.get("initial_pos", [0, 0, 0]))
    
    # Layer 1: Transport
    if "transport" in params_dict:
        t = params_dict["transport"]
        params.transport.movement_type = MovementType(t.get("movement_type", "linear"))
        params.transport.end_offset = tuple(t.get("end_offset", [0, 0, 0]))
        params.transport.duration = t.get("duration", 0)
        params.transport.easing = EasingType(t.get("easing", "ease_in_out"))
    
    # Layer 2: Rotate Pivot
    if "rotate_pivot" in params_dict:
        r = params_dict["rotate_pivot"]
        params.rotate_pivot.axis = r.get("axis", "Y")
        params.rotate_pivot.start_angle = r.get("start_angle", 0)
        params.rotate_pivot.end_angle = r.get("end_angle", 0)
        params.rotate_pivot.easing = EasingType(r.get("easing", "ease_in_out"))
    
    # Layer 2: Boom
    if "boom" in params_dict:
        b = params_dict["boom"]
        params.boom.start_length = b.get("start_length", 5.0)
        params.boom.end_length = b.get("end_length", 5.0)
        params.boom.easing = EasingType(b.get("easing", "ease_in_out"))
    
    # Layer 3: LookAt
    if "look_at" in params_dict:
        l = params_dict["look_at"]
        params.look_at.target_prim = l.get("target_prim", "")
        params.look_at.framing_offset = tuple(l.get("framing_offset", [0, 0]))
    
    # Layer 3: Roll
    if "roll" in params_dict:
        r = params_dict["roll"]
        params.roll.start_angle = r.get("start_angle", 0)
        params.roll.end_angle = r.get("end_angle", 0)
        params.roll.easing = EasingType(r.get("easing", "ease_in_out"))
    
    # Layer 4: Lens
    if "lens" in params_dict:
        l = params_dict["lens"]
        params.lens.start_focal_length = l.get("start_focal_length", 35.0)
        params.lens.end_focal_length = l.get("end_focal_length", 35.0)
        params.lens.easing = EasingType(l.get("easing", "ease_in_out"))
    
    # Layer 4: Shake
    if "shake" in params_dict:
        s = params_dict["shake"]
        params.shake.intensity = s.get("intensity", 0)
        params.shake.frequency = s.get("frequency", 1.0)
        params.shake.seed = s.get("seed", 0)
    
    return create_camera_rig(params)


# =============================================================================
# Preset Shots
# =============================================================================

def create_orbit_shot(
    target_prim: str = "",
    target_pos: Tuple[float, float, float] = (0, 0, 0),
    distance: float = 5.0,
    start_angle: float = 0,
    end_angle: float = 360,
    height: float = 0,
    duration: float = 6.0,
    focal_length: float = 50.0
) -> str:
    """Quick helper for common orbit shot."""
    params = CameraRigParams(
        name="OrbitShot",
        duration=duration,
        anchor=AnchorParams(
            target_prim=target_prim,
            initial_pos=target_pos if not target_prim else (0, 0, 0)
        ),
        rotate_pivot=RotatePivotParams(
            axis="Y",
            start_angle=start_angle,
            end_angle=end_angle
        ),
        boom=BoomParams(
            start_length=distance,
            end_length=distance
        ),
        lens=LensParams(
            start_focal_length=focal_length,
            end_focal_length=focal_length
        )
    )
    
    # Add height by adjusting initial position
    if height != 0 and not target_prim:
        params.anchor.initial_pos = (target_pos[0], target_pos[1] + height, target_pos[2])
    
    return create_camera_rig(params)


def create_dolly_zoom_shot(
    target_prim: str = "",
    target_pos: Tuple[float, float, float] = (0, 0, 0),
    start_distance: float = 10.0,
    end_distance: float = 3.0,
    start_focal: float = 24.0,
    end_focal: float = 85.0,
    duration: float = 4.0
) -> str:
    """Hitchcock vertigo/dolly zoom effect."""
    params = CameraRigParams(
        name="DollyZoom",
        duration=duration,
        anchor=AnchorParams(
            target_prim=target_prim,
            initial_pos=target_pos if not target_prim else (0, 0, 0)
        ),
        boom=BoomParams(
            start_length=start_distance,
            end_length=end_distance,
            easing=EasingType.EASE_IN_OUT
        ),
        lens=LensParams(
            start_focal_length=start_focal,
            end_focal_length=end_focal,
            easing=EasingType.EASE_IN_OUT
        )
    )
    return create_camera_rig(params)


def create_crane_shot(
    target_prim: str = "",
    target_pos: Tuple[float, float, float] = (0, 0, 0),
    distance: float = 5.0,
    start_height: float = 0,
    end_height: float = 10.0,
    orbit_angle: float = 90,
    duration: float = 5.0
) -> str:
    """Crane up while orbiting."""
    # For crane, we use transport to move up while rotating
    params = CameraRigParams(
        name="CraneShot",
        duration=duration,
        anchor=AnchorParams(
            target_prim=target_prim,
            initial_pos=(target_pos[0], target_pos[1] + start_height, target_pos[2])
        ),
        transport=TransportParams(
            end_offset=(0, end_height - start_height, 0),
            duration=duration,
            easing=EasingType.EASE_IN_OUT
        ),
        rotate_pivot=RotatePivotParams(
            axis="Y",
            start_angle=0,
            end_angle=orbit_angle
        ),
        boom=BoomParams(
            start_length=distance,
            end_length=distance
        )
    )
    return create_camera_rig(params)



