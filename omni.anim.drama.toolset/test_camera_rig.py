# -*- coding: utf-8 -*-
"""
Test Camera Rig System
======================

Run this in Omniverse Script Editor to test the hierarchical camera rig.

The camera rig has 4 layers:
- Layer 1 (Root): anchor + transport
- Layer 2 (Arm): rotate_pivot + boom
- Layer 3 (Head): look_at + roll
- Layer 4 (Lens): lens + shake
"""

import sys
import os

# Add the module path for running from Script Editor
module_path = r"D:\ov\kit-app-template\Omniverse-anim-toolset\omni.anim.drama.toolset"
if module_path not in sys.path:
    sys.path.insert(0, module_path)

from omni.anim.drama.toolset.core.camera_rig import (
    create_camera_rig,
    create_camera_from_dict,
    create_orbit_shot,
    create_dolly_zoom_shot,
    create_crane_shot,
    CameraRigParams,
    AnchorParams,
    RotatePivotParams,
    BoomParams,
    LensParams,
    ShakeParams,
    RollParams
)


def test_orbit():
    """Test basic orbit shot."""
    print("\n=== Test 1: Basic Orbit ===")
    
    camera_path = create_orbit_shot(
        target_pos=(0, 0, 0),
        distance=15.0,  # Further back to see the sphere
        start_angle=0,
        end_angle=360,
        height=2.0,     # Slightly above the sphere
        duration=6.0
    )
    
    print(f"Created: {camera_path}")
    print("Expected: Horizontal 360° orbit around origin")


def test_dolly_zoom():
    """Test Hitchcock dolly zoom."""
    print("\n=== Test 2: Dolly Zoom (Vertigo Effect) ===")
    
    camera_path = create_dolly_zoom_shot(
        target_pos=(0, 0, 0),
        start_distance=25.0,  # Start far
        end_distance=10.0,    # End closer but still visible
        start_focal=24.0,
        end_focal=85.0,
        duration=4.0
    )
    
    print(f"Created: {camera_path}")
    print("Expected: Push in while zooming out (vertigo effect)")


def test_crane():
    """Test crane shot."""
    print("\n=== Test 3: Crane Up + Orbit ===")
    
    camera_path = create_crane_shot(
        target_pos=(0, 0, 0),
        distance=15.0,      # Distance from sphere
        start_height=1.0,   # Start near ground level
        end_height=12.0,    # Rise up high
        orbit_angle=180,
        duration=5.0
    )
    
    print(f"Created: {camera_path}")
    print("Expected: Rise up while orbiting 180 degrees")


def test_from_dict():
    """Test creating camera from JSON-like dict (AI input)."""
    print("\n=== Test 4: From Dictionary (AI Input) ===")
    
    # This is what the AI would generate
    ai_params = {
        "name": "EpicReveal",
        "duration": 8.0,
        "anchor": {
            "initial_pos": [0, 0, 0]
        },
        "rotate_pivot": {
            "axis": "Y",
            "start_angle": 0,
            "end_angle": 270
        },
        "boom": {
            "start_length": 25.0,   # Start far
            "end_length": 12.0      # End closer but visible
        },
        "lens": {
            "start_focal_length": 24,
            "end_focal_length": 50
        },
        "roll": {
            "start_angle": -10,
            "end_angle": 0
        },
        "shake": {
            "intensity": 0.05,
            "frequency": 0.5
        }
    }
    
    camera_path = create_camera_from_dict(ai_params)
    
    print(f"Created: {camera_path}")
    print("Expected: Complex shot with orbit + dolly + zoom + roll + shake")


def test_with_shake():
    """Test handheld shake effect."""
    print("\n=== Test 5: Handheld with Shake ===")
    
    params = CameraRigParams(
        name="Handheld",
        duration=5.0,
        boom=BoomParams(start_length=15.0, end_length=15.0),  # Far enough to see sphere
        shake=ShakeParams(
            intensity=0.15,  # Subtle shake
            frequency=0.8,   # Low frequency = handheld feel
            seed=42
        )
    )
    
    camera_path = create_camera_rig(params)
    
    print(f"Created: {camera_path}")
    print("Expected: Static position with handheld shake")


def run_all_tests():
    """Run all camera rig tests."""
    print("=" * 50)
    print("CAMERA RIG SYSTEM TESTS")
    print("=" * 50)
    
    test_orbit()
    test_dolly_zoom()
    test_crane()
    test_from_dict()
    test_with_shake()
    
    print("\n" + "=" * 50)
    print("All tests complete!")
    print("Select each camera in viewport to test.")
    print("=" * 50)


# Run tests
run_all_tests()

