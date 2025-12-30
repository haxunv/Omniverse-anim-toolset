# -*- coding: utf-8 -*-
"""
Orbit Camera with Spherical Coordinates
========================================

Clear, controllable orbit camera system.
Run in Omniverse Script Editor.
"""

import math
from pxr import Usd, UsdGeom, Gf
import omni.usd


def create_orbit_camera(
    target=(0, 0, 0),       # Point to orbit around and look at
    distance=10.0,          # Horizontal distance from target
    
    # Azimuth (horizontal rotation)
    start_azimuth=0,        # Start angle (degrees, 0=+Z, 90=+X)
    end_azimuth=360,        # End angle
    
    # Height (vertical position) - independent of angle!
    start_height=0,         # Start height relative to target
    end_height=0,           # End height (change for crane motion)
    
    duration=6.0,
    fps=24.0,
    camera_name="OrbitCamera"
):
    """
    Create an orbit camera with simple, intuitive controls.
    
    Parameters:
    - azimuth: horizontal angle (0° = behind target on +Z, 90° = right side on +X)
    - height: vertical position relative to target (in scene units, not degrees!)
    - distance: horizontal distance from target
    
    Examples:
    - Horizontal orbit at eye level: start_height=0, end_height=0
    - High angle orbit: start_height=5, end_height=5
    - Crane up while orbiting: start_height=0, end_height=8
    - Crane down: start_height=10, end_height=2
    """
    stage = omni.usd.get_context().get_stage()
    if not stage:
        print("No stage!")
        return
    
    camera_path = f"/World/{camera_name}"
    
    if stage.GetPrimAtPath(camera_path):
        stage.RemovePrim(camera_path)
    
    camera = UsdGeom.Camera.Define(stage, camera_path)
    camera.GetFocalLengthAttr().Set(50.0)
    
    xformable = UsdGeom.Xformable(camera.GetPrim())
    xformable.ClearXformOpOrder()
    
    translate_op = xformable.AddTranslateOp()
    rotate_y_op = xformable.AddRotateYOp()   # Yaw (horizontal look direction)
    rotate_x_op = xformable.AddRotateXOp()   # Pitch (vertical look direction)
    
    total_frames = int(duration * fps)
    
    print(f"=== Creating Orbit Camera ===")
    print(f"Target: {target}")
    print(f"Distance: {distance}")
    print(f"Azimuth: {start_azimuth}° → {end_azimuth}°")
    print(f"Elevation: {start_elevation}° → {end_elevation}°")
    print(f"Duration: {duration}s ({total_frames} frames)")
    print()
    
    for frame_idx in range(total_frames + 1):
        t = frame_idx / total_frames
        time_code = Usd.TimeCode(frame_idx)
        
        # Interpolate angles
        azimuth = start_azimuth + (end_azimuth - start_azimuth) * t
        elevation = start_elevation + (end_elevation - start_elevation) * t
        
        az_rad = math.radians(azimuth)
        el_rad = math.radians(elevation)
        
        # Spherical to Cartesian (Y-up coordinate system)
        # At azimuth=0, elevation=0: camera is at (0, 0, distance) looking at origin
        x = target[0] + distance * math.cos(el_rad) * math.sin(az_rad)
        y = target[1] + distance * math.sin(el_rad)
        z = target[2] + distance * math.cos(el_rad) * math.cos(az_rad)
        
        translate_op.Set(Gf.Vec3d(x, y, z), time_code)
        
        # Camera rotation to look at target
        # Yaw: rotate around Y to face target horizontally
        yaw = 180 + azimuth  # Add 180 because camera looks along -Z
        rotate_y_op.Set(yaw, time_code)
        
        # Pitch: rotate around X to look up/down at target
        pitch = -elevation  # Negative because X rotation is inverted
        rotate_x_op.Set(pitch, time_code)
        
        if frame_idx % 24 == 0:
            print(f"Frame {frame_idx}: az={azimuth:.0f}° el={elevation:.0f}° pos=({x:.1f}, {y:.1f}, {z:.1f})")
    
    print(f"\n✓ Camera created: {camera_path}")
    print("Select this camera in viewport and press Play")
    return camera_path


# ============ TEST DIFFERENT ORBIT TYPES ============

print("=" * 50)
print("ORBIT CAMERA EXAMPLES")
print("=" * 50)

# Example 1: Horizontal orbit (水平环绕)
create_orbit_camera(
    target=(0, 0, 0),
    distance=10,
    start_azimuth=0,
    end_azimuth=360,
    start_elevation=0,    # Horizontal
    end_elevation=0,      # Stay horizontal
    camera_name="Orbit_Horizontal"
)

print("\n" + "-" * 50 + "\n")

# Example 2: High angle orbit (高角度环绕 - 俯视)
create_orbit_camera(
    target=(0, 0, 0),
    distance=10,
    start_azimuth=0,
    end_azimuth=360,
    start_elevation=30,   # 30 degrees above horizontal
    end_elevation=30,     # Stay at 30 degrees
    camera_name="Orbit_HighAngle"
)

print("\n" + "-" * 50 + "\n")

# Example 3: Crane up while orbiting (边转边升)
create_orbit_camera(
    target=(0, 0, 0),
    distance=10,
    start_azimuth=0,
    end_azimuth=180,      # Half orbit
    start_elevation=0,    # Start horizontal
    end_elevation=45,     # End at 45 degrees up
    camera_name="Orbit_CraneUp"
)

print("\n" + "=" * 50)
print("Created 3 cameras. Try each one!")
print("=" * 50)

