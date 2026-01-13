# -*- coding: utf-8 -*-
"""
Layer State Manager
===================

Implements Maya-style Layer state management:
- Cache object's original state
- Restore original state when switching layers
- Apply current layer's property overrides

This enables:
- Same mesh having different properties in different layers
- When rendering different layers, only that layer's overrides take effect
"""

from typing import Dict, List, Any, Optional, Tuple, Set
from pxr import Usd, Sdf, UsdGeom, UsdShade, UsdLux

from .stage_utils import get_stage, safe_log


# =============================================================================
# State cache data structure
# =============================================================================

class PrimState:
    """Store original state of a single Prim."""
    
    def __init__(self, prim_path: str):
        self.prim_path = prim_path
        self.visibility: Optional[str] = None  # "inherited", "invisible"
        self.material_binding: Optional[str] = None  # Material path
        self.light_intensity: Optional[float] = None
        self.light_color: Optional[Tuple[float, float, float]] = None
        self.light_exposure: Optional[float] = None
        self.custom_attrs: Dict[str, Any] = {}  # Other custom attributes


class LayerStateManager:
    """
    Layer state manager (singleton).
    
    Features:
    1. Cache all objects' original states
    2. Restore original states when switching layers
    3. Apply current layer's overrides
    """
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._initialized = True
        
        # Original state cache: prim_path -> PrimState
        self._original_states: Dict[str, PrimState] = {}
        
        # Currently active Layer
        self._active_layer_path: str = ""
        
        # Set of Prim paths with overrides applied
        self._overridden_prims: Set[str] = set()
        
        # Whether state management is enabled
        self._enabled: bool = True
    
    @property
    def enabled(self) -> bool:
        return self._enabled
    
    @enabled.setter
    def enabled(self, value: bool):
        self._enabled = value
        safe_log(f"[LayerState] State management {'enabled' if value else 'disabled'}")
    
    @property
    def active_layer_path(self) -> str:
        return self._active_layer_path
    
    def cache_prim_state(self, prim_path: str) -> bool:
        """
        Cache original state of a single Prim.
        
        Args:
            prim_path: Prim path
            
        Returns:
            bool: Whether successful
        """
        # Skip if already cached
        if prim_path in self._original_states:
            return True
        
        stage = get_stage()
        if not stage:
            return False
        
        prim = stage.GetPrimAtPath(prim_path)
        if not prim or not prim.IsValid():
            return False
        
        state = PrimState(prim_path)
        
        try:
            # Cache visibility
            if prim.IsA(UsdGeom.Imageable):
                imageable = UsdGeom.Imageable(prim)
                vis_attr = imageable.GetVisibilityAttr()
                if vis_attr and vis_attr.HasAuthoredValue():
                    state.visibility = vis_attr.Get()
                else:
                    state.visibility = "inherited"
            
            # Cache material binding
            if prim.IsA(UsdGeom.Gprim) or prim.IsA(UsdGeom.Subset):
                binding_api = UsdShade.MaterialBindingAPI(prim)
                material, _ = binding_api.ComputeBoundMaterial()
                if material:
                    state.material_binding = material.GetPath().pathString
            
            # Cache light properties
            if prim.IsA(UsdLux.Light):
                # Try to get intensity
                intensity_attr = prim.GetAttribute("inputs:intensity")
                if intensity_attr and intensity_attr.HasAuthoredValue():
                    state.light_intensity = intensity_attr.Get()
                
                # Try to get color
                color_attr = prim.GetAttribute("inputs:color")
                if color_attr and color_attr.HasAuthoredValue():
                    color = color_attr.Get()
                    if color:
                        state.light_color = (color[0], color[1], color[2])
                
                # Try to get exposure
                exposure_attr = prim.GetAttribute("inputs:exposure")
                if exposure_attr and exposure_attr.HasAuthoredValue():
                    state.light_exposure = exposure_attr.Get()
            
            self._original_states[prim_path] = state
            return True
            
        except Exception as e:
            safe_log(f"[LayerState] Error caching state for {prim_path}: {e}")
            return False
    
    def cache_collection_members(self, collection_path: str) -> int:
        """
        Cache original states of all members in a Collection.
        
        Args:
            collection_path: Collection path
            
        Returns:
            int: Number of members cached
        """
        from .render_collection import get_collection_members
        
        members = get_collection_members(collection_path)
        cached_count = 0
        
        for member_path in members:
            if self.cache_prim_state(member_path):
                cached_count += 1
        
        return cached_count
    
    def cache_layer_members(self, layer_path: str) -> int:
        """
        Cache original states of all Collection members in a Layer.
        
        Args:
            layer_path: Layer path
            
        Returns:
            int: Number of members cached
        """
        from .render_collection import get_collections_in_layer, get_collection_members
        
        collections = get_collections_in_layer(layer_path)
        cached_count = 0
        
        def process_collection(col_info):
            nonlocal cached_count
            members = get_collection_members(col_info["path"])
            for member_path in members:
                if self.cache_prim_state(member_path):
                    cached_count += 1
            
            # Recursively process child Collections
            for child in col_info.get("children", []):
                process_collection(child)
        
        for col in collections:
            process_collection(col)
        
        return cached_count
    
    def restore_prim_state(self, prim_path: str) -> bool:
        """
        Restore original state of a single Prim.
        
        Args:
            prim_path: Prim path
            
        Returns:
            bool: Whether successful
        """
        if prim_path not in self._original_states:
            return False
        
        stage = get_stage()
        if not stage:
            return False
        
        prim = stage.GetPrimAtPath(prim_path)
        if not prim or not prim.IsValid():
            return False
        
        state = self._original_states[prim_path]
        
        try:
            # Restore visibility
            if state.visibility is not None and prim.IsA(UsdGeom.Imageable):
                imageable = UsdGeom.Imageable(prim)
                imageable.GetVisibilityAttr().Set(state.visibility)
            
            # Restore material binding
            if state.material_binding is not None:
                material_prim = stage.GetPrimAtPath(state.material_binding)
                if material_prim and material_prim.IsValid():
                    material = UsdShade.Material(material_prim)
                    binding_api = UsdShade.MaterialBindingAPI(prim)
                    binding_api.Bind(material)
            
            # Restore light properties
            if prim.IsA(UsdLux.Light):
                if state.light_intensity is not None:
                    intensity_attr = prim.GetAttribute("inputs:intensity")
                    if intensity_attr:
                        intensity_attr.Set(state.light_intensity)
                
                if state.light_color is not None:
                    color_attr = prim.GetAttribute("inputs:color")
                    if color_attr:
                        from pxr import Gf
                        color_attr.Set(Gf.Vec3f(*state.light_color))
                
                if state.light_exposure is not None:
                    exposure_attr = prim.GetAttribute("inputs:exposure")
                    if exposure_attr:
                        exposure_attr.Set(state.light_exposure)
            
            return True
            
        except Exception as e:
            safe_log(f"[LayerState] Error restoring state for {prim_path}: {e}")
            return False
    
    def restore_all_original_states(self) -> int:
        """
        Restore original states of all cached Prims.
        
        Returns:
            int: Number of Prims restored
        """
        restored_count = 0
        
        for prim_path in self._overridden_prims.copy():
            if self.restore_prim_state(prim_path):
                restored_count += 1
        
        self._overridden_prims.clear()
        safe_log(f"[LayerState] Restored {restored_count} prims to original state")
        
        return restored_count
    
    def apply_layer_overrides(self, layer_path: str) -> Tuple[int, str]:
        """
        Apply all property overrides of a Layer.
        
        Workflow:
        1. Restore original states of all overridden Prims
        2. Apply new Layer's overrides
        
        Args:
            layer_path: Layer path
            
        Returns:
            Tuple[int, str]: (number of overrides applied, message)
        """
        if not self._enabled:
            return 0, "State management disabled"
        
        from .render_collection import get_collections_in_layer, get_collection_members
        from .render_override import (
            get_collection_overrides,
            apply_override_to_prim,
        )
        
        stage = get_stage()
        if not stage:
            return 0, "No stage available"
        
        # 1. Restore all overridden Prims
        self.restore_all_original_states()
        
        # 2. Cache new Layer's member states
        self.cache_layer_members(layer_path)
        
        # 3. Apply new Layer's overrides
        collections = get_collections_in_layer(layer_path)
        applied_count = 0
        
        def process_collection(col_info):
            nonlocal applied_count
            col_path = col_info["path"]
            
            # Get Collection's Override settings
            overrides = get_collection_overrides(col_path)
            
            if overrides:
                # Get Collection members
                members = get_collection_members(col_path)
                
                for member_path in members:
                    # Apply each Override
                    for override_type, override_value in overrides.items():
                        success = apply_override_to_prim(
                            member_path, override_type, override_value
                        )
                        if success:
                            self._overridden_prims.add(member_path)
                            applied_count += 1
            
            # Recursively process child Collections
            for child in col_info.get("children", []):
                process_collection(child)
        
        for col in collections:
            process_collection(col)
        
        self._active_layer_path = layer_path
        
        layer_name = layer_path.split("/")[-1]
        msg = f"Applied {applied_count} overrides for layer '{layer_name}'"
        safe_log(f"[LayerState] {msg}")
        
        return applied_count, msg
    
    def switch_to_layer(self, layer_path: str) -> Tuple[bool, str]:
        """
        Switch to specified Layer (Maya style).
        
        This is the main entry function that will:
        1. Restore all objects' original states
        2. Apply new Layer's overrides
        3. Update AOV configuration
        
        Args:
            layer_path: Target Layer path
            
        Returns:
            Tuple[bool, str]: (success, message)
        """
        if not self._enabled:
            return True, "State management disabled, switch skipped"
        
        if layer_path == self._active_layer_path:
            return True, "Already on this layer"
        
        try:
            # Apply Layer's overrides
            count, msg = self.apply_layer_overrides(layer_path)
            
            layer_name = layer_path.split("/")[-1]
            result_msg = f"Switched to layer '{layer_name}': {msg}"
            safe_log(f"[LayerState] {result_msg}")
            
            return True, result_msg
            
        except Exception as e:
            msg = f"Error switching layer: {e}"
            safe_log(f"[LayerState] {msg}")
            return False, msg
    
    def clear_cache(self) -> None:
        """Clear all cache."""
        self._original_states.clear()
        self._overridden_prims.clear()
        self._active_layer_path = ""
        safe_log("[LayerState] Cache cleared")
    
    def get_cached_prim_count(self) -> int:
        """Get number of cached Prims."""
        return len(self._original_states)
    
    def get_overridden_prim_count(self) -> int:
        """Get number of overridden Prims."""
        return len(self._overridden_prims)


# =============================================================================
# Global function interface
# =============================================================================

def get_layer_state_manager() -> LayerStateManager:
    """Get LayerStateManager singleton."""
    return LayerStateManager()


def switch_to_layer(layer_path: str) -> Tuple[bool, str]:
    """
    Switch to specified Layer (Maya style).
    
    This will:
    1. Restore all objects' original states
    2. Only apply target Layer's overrides
    
    Args:
        layer_path: Target Layer path
        
    Returns:
        Tuple[bool, str]: (success, message)
    """
    manager = get_layer_state_manager()
    return manager.switch_to_layer(layer_path)


def restore_original_states() -> Tuple[int, str]:
    """
    Restore all objects' original states.
    
    Returns:
        Tuple[int, str]: (restore count, message)
    """
    manager = get_layer_state_manager()
    count = manager.restore_all_original_states()
    return count, f"Restored {count} prims"


def enable_layer_state_management(enabled: bool = True) -> None:
    """Enable or disable Layer state management."""
    manager = get_layer_state_manager()
    manager.enabled = enabled


def is_layer_state_management_enabled() -> bool:
    """Check if Layer state management is enabled."""
    manager = get_layer_state_manager()
    return manager.enabled


def get_layer_state_info() -> Dict[str, Any]:
    """Get current Layer state info."""
    manager = get_layer_state_manager()
    return {
        "enabled": manager.enabled,
        "active_layer": manager.active_layer_path,
        "cached_prims": manager.get_cached_prim_count(),
        "overridden_prims": manager.get_overridden_prim_count(),
    }

