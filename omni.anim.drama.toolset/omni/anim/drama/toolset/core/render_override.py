# -*- coding: utf-8 -*-
"""
Render Override Core Logic
==========================

Provides property override functionality for Collections.

Overrides are stored on the Collection prim and applied to all members.
When switching layers, each layer's Collection overrides take effect.

Supported Override Types:
    - visibility: Show/hide objects
    - light_intensity: Light intensity
    - light_color: Light color
    - material: Material binding
"""

from typing import List, Optional, Tuple, Dict, Any
from pxr import Usd, Sdf, UsdGeom, UsdShade, UsdLux, Gf

from .stage_utils import get_stage, safe_log


# =============================================================================
# Override Type Constants
# =============================================================================

OVERRIDE_VISIBILITY = "visibility"
OVERRIDE_LIGHT_INTENSITY = "light_intensity"
OVERRIDE_LIGHT_COLOR = "light_color"
OVERRIDE_MATERIAL = "material"

# Custom attribute names for storing overrides on Collection
ATTR_OVERRIDE_PREFIX = "drama:override:"
ATTR_OVERRIDE_VISIBILITY = f"{ATTR_OVERRIDE_PREFIX}visibility"
ATTR_OVERRIDE_VISIBILITY_VALUE = f"{ATTR_OVERRIDE_PREFIX}visibilityValue"
ATTR_OVERRIDE_LIGHT_INTENSITY = f"{ATTR_OVERRIDE_PREFIX}lightIntensity"
ATTR_OVERRIDE_LIGHT_INTENSITY_VALUE = f"{ATTR_OVERRIDE_PREFIX}lightIntensityValue"
ATTR_OVERRIDE_LIGHT_COLOR = f"{ATTR_OVERRIDE_PREFIX}lightColor"
ATTR_OVERRIDE_LIGHT_COLOR_VALUE = f"{ATTR_OVERRIDE_PREFIX}lightColorValue"
ATTR_OVERRIDE_MATERIAL = f"{ATTR_OVERRIDE_PREFIX}material"
ATTR_OVERRIDE_MATERIAL_PATH = f"{ATTR_OVERRIDE_PREFIX}materialPath"


# =============================================================================
# Direct Property Override (immediate effect)
# =============================================================================

def set_visibility_override(prim_path: str, visible: bool) -> Tuple[bool, str]:
    """
    Set visibility on a prim.
    
    Args:
        prim_path: Prim path
        visible: Whether visible
        
    Returns:
        Tuple[bool, str]: (success, message)
    """
    stage = get_stage()
    if not stage:
        return False, "No stage"
    
    prim = stage.GetPrimAtPath(prim_path)
    if not prim or not prim.IsValid():
        return False, f"Prim not found: {prim_path}"
    
    try:
        imageable = UsdGeom.Imageable(prim)
        if not imageable:
            return False, "Not imageable"
        
        if visible:
            imageable.MakeVisible()
        else:
            imageable.MakeInvisible()
        
        return True, f"Set {prim_path} {'visible' if visible else 'invisible'}"
        
    except Exception as e:
        return False, f"Error: {e}"


def set_light_property(light_path: str, property_name: str, value: Any) -> Tuple[bool, str]:
    """
    Set a light property.
    
    Args:
        light_path: Light prim path
        property_name: "intensity", "exposure", "color"
        value: Property value
    """
    stage = get_stage()
    if not stage:
        return False, "No stage"
    
    prim = stage.GetPrimAtPath(light_path)
    if not prim or not prim.IsValid():
        return False, "Light not found"
    
    if not prim.IsA(UsdLux.Light):
        return False, "Not a light"
    
    try:
        attr_name = f"inputs:{property_name}"
        attr = prim.GetAttribute(attr_name)
        
        if not attr:
            attr = prim.GetAttribute(property_name)
        
        if attr:
            attr.Set(value)
            return True, f"Set {property_name} = {value}"
        
        return False, f"Property not found: {property_name}"
        
    except Exception as e:
        return False, f"Error: {e}"


def set_material_binding(prim_path: str, material_path: str) -> Tuple[bool, str]:
    """
    Bind a material to a prim.
    
    Args:
        prim_path: Target prim path
        material_path: Material prim path
    """
    stage = get_stage()
    if not stage:
        return False, "No stage"
    
    prim = stage.GetPrimAtPath(prim_path)
    if not prim or not prim.IsValid():
        return False, "Prim not found"
    
    material_prim = stage.GetPrimAtPath(material_path)
    if not material_prim or not material_prim.IsValid():
        return False, "Material not found"
    
    try:
        material = UsdShade.Material(material_prim)
        if not material:
            return False, "Not a valid material"
        
        binding_api = UsdShade.MaterialBindingAPI.Apply(prim)
        binding_api.Bind(material)
        
        return True, f"Bound {material_path} to {prim_path}"
        
    except Exception as e:
        return False, f"Error: {e}"


def get_material_binding(prim_path: str) -> Optional[str]:
    """Get current material binding."""
    stage = get_stage()
    if not stage:
        return None
    
    prim = stage.GetPrimAtPath(prim_path)
    if not prim or not prim.IsValid():
        return None
    
    try:
        binding_api = UsdShade.MaterialBindingAPI(prim)
        material, _ = binding_api.ComputeBoundMaterial()
        if material:
            return material.GetPath().pathString
    except Exception:
        pass
    
    return None


def batch_set_visibility(prim_paths: List[str], visible: bool) -> Tuple[int, int]:
    """
    Batch set visibility on multiple prims.
    
    Returns:
        Tuple[int, int]: (success_count, fail_count)
    """
    success = 0
    fail = 0
    
    for path in prim_paths:
        ok, _ = set_visibility_override(path, visible)
        if ok:
            success += 1
        else:
            fail += 1
    
    return success, fail


# =============================================================================
# Collection Override Storage
# =============================================================================

def set_collection_override(
    collection_path: str,
    override_type: str,
    value: Any
) -> Tuple[bool, str]:
    """
    Store an override on a Collection.
    
    The override is stored as custom attributes on the Collection prim.
    When the layer is activated, these overrides are applied to members.
    
    Args:
        collection_path: Collection path
        override_type: "visibility", "light_intensity", "light_color", "material"
        value: Override value
    """
    stage = get_stage()
    if not stage:
        return False, "No stage"
    
    prim = stage.GetPrimAtPath(collection_path)
    if not prim or not prim.IsValid():
        return False, "Collection not found"
    
    try:
        if override_type == OVERRIDE_VISIBILITY:
            _set_or_create_attr(prim, ATTR_OVERRIDE_VISIBILITY, Sdf.ValueTypeNames.Bool, True)
            _set_or_create_attr(prim, ATTR_OVERRIDE_VISIBILITY_VALUE, Sdf.ValueTypeNames.Bool, bool(value))
            
        elif override_type == OVERRIDE_LIGHT_INTENSITY:
            _set_or_create_attr(prim, ATTR_OVERRIDE_LIGHT_INTENSITY, Sdf.ValueTypeNames.Bool, True)
            _set_or_create_attr(prim, ATTR_OVERRIDE_LIGHT_INTENSITY_VALUE, Sdf.ValueTypeNames.Float, float(value))
            
        elif override_type == OVERRIDE_LIGHT_COLOR:
            _set_or_create_attr(prim, ATTR_OVERRIDE_LIGHT_COLOR, Sdf.ValueTypeNames.Bool, True)
            if isinstance(value, (list, tuple)) and len(value) >= 3:
                _set_or_create_attr(prim, ATTR_OVERRIDE_LIGHT_COLOR_VALUE, Sdf.ValueTypeNames.Float3, 
                                   Gf.Vec3f(value[0], value[1], value[2]))
            
        elif override_type == OVERRIDE_MATERIAL:
            _set_or_create_attr(prim, ATTR_OVERRIDE_MATERIAL, Sdf.ValueTypeNames.Bool, True)
            _set_or_create_attr(prim, ATTR_OVERRIDE_MATERIAL_PATH, Sdf.ValueTypeNames.String, str(value))
            
        else:
            return False, f"Unknown override type: {override_type}"
        
        safe_log(f"[Override] Set {override_type} override on collection")
        return True, f"Set {override_type} override"
        
    except Exception as e:
        return False, f"Error: {e}"


def _set_or_create_attr(prim: Usd.Prim, attr_name: str, type_name: Sdf.ValueTypeName, value: Any) -> None:
    """Helper to set or create attribute."""
    attr = prim.GetAttribute(attr_name)
    if not attr:
        attr = prim.CreateAttribute(attr_name, type_name)
    attr.Set(value)


def get_collection_overrides(collection_path: str) -> Dict[str, Any]:
    """
    Get all overrides stored on a Collection.
    
    Returns:
        Dict[str, Any]: Override type to value mapping
    """
    stage = get_stage()
    if not stage:
        return {}
    
    prim = stage.GetPrimAtPath(collection_path)
    if not prim or not prim.IsValid():
        return {}
    
    overrides = {}
    
    try:
        # Visibility
        vis_enabled = prim.GetAttribute(ATTR_OVERRIDE_VISIBILITY)
        if vis_enabled and vis_enabled.HasAuthoredValue() and vis_enabled.Get():
            vis_value = prim.GetAttribute(ATTR_OVERRIDE_VISIBILITY_VALUE)
            if vis_value and vis_value.HasAuthoredValue():
                overrides[OVERRIDE_VISIBILITY] = vis_value.Get()
        
        # Light intensity
        int_enabled = prim.GetAttribute(ATTR_OVERRIDE_LIGHT_INTENSITY)
        if int_enabled and int_enabled.HasAuthoredValue() and int_enabled.Get():
            int_value = prim.GetAttribute(ATTR_OVERRIDE_LIGHT_INTENSITY_VALUE)
            if int_value and int_value.HasAuthoredValue():
                overrides[OVERRIDE_LIGHT_INTENSITY] = int_value.Get()
        
        # Light color
        color_enabled = prim.GetAttribute(ATTR_OVERRIDE_LIGHT_COLOR)
        if color_enabled and color_enabled.HasAuthoredValue() and color_enabled.Get():
            color_value = prim.GetAttribute(ATTR_OVERRIDE_LIGHT_COLOR_VALUE)
            if color_value and color_value.HasAuthoredValue():
                c = color_value.Get()
                overrides[OVERRIDE_LIGHT_COLOR] = (c[0], c[1], c[2]) if c else None
        
        # Material
        mat_enabled = prim.GetAttribute(ATTR_OVERRIDE_MATERIAL)
        if mat_enabled and mat_enabled.HasAuthoredValue() and mat_enabled.Get():
            mat_path = prim.GetAttribute(ATTR_OVERRIDE_MATERIAL_PATH)
            if mat_path and mat_path.HasAuthoredValue():
                overrides[OVERRIDE_MATERIAL] = mat_path.Get()
        
    except Exception as e:
        safe_log(f"[Override] Error reading overrides: {e}")
    
    return overrides


def clear_collection_overrides(collection_path: str) -> Tuple[bool, str]:
    """Clear all overrides on a Collection."""
    stage = get_stage()
    if not stage:
        return False, "No stage"
    
    prim = stage.GetPrimAtPath(collection_path)
    if not prim or not prim.IsValid():
        return False, "Collection not found"
    
    try:
        for attr_name in [ATTR_OVERRIDE_VISIBILITY, ATTR_OVERRIDE_LIGHT_INTENSITY,
                          ATTR_OVERRIDE_LIGHT_COLOR, ATTR_OVERRIDE_MATERIAL]:
            attr = prim.GetAttribute(attr_name)
            if attr:
                attr.Set(False)
        
        return True, "Cleared all overrides"
        
    except Exception as e:
        return False, f"Error: {e}"


# =============================================================================
# Apply Overrides to Members
# =============================================================================

def apply_override_to_prim(prim_path: str, override_type: str, value: Any) -> bool:
    """
    Apply a single override to a prim.
    
    Args:
        prim_path: Target prim path
        override_type: Override type
        value: Override value
        
    Returns:
        bool: Success
    """
    stage = get_stage()
    if not stage:
        return False
    
    prim = stage.GetPrimAtPath(prim_path)
    if not prim or not prim.IsValid():
        return False
    
    try:
        if override_type == OVERRIDE_VISIBILITY:
            if prim.IsA(UsdGeom.Imageable):
                imageable = UsdGeom.Imageable(prim)
                if value:
                    imageable.GetVisibilityAttr().Set(UsdGeom.Tokens.inherited)
                else:
                    imageable.GetVisibilityAttr().Set(UsdGeom.Tokens.invisible)
                return True
                
        elif override_type == OVERRIDE_LIGHT_INTENSITY:
            if prim.IsA(UsdLux.Light):
                intensity_attr = prim.GetAttribute("inputs:intensity")
                if intensity_attr:
                    intensity_attr.Set(float(value))
                    return True
                    
        elif override_type == OVERRIDE_LIGHT_COLOR:
            if prim.IsA(UsdLux.Light):
                color_attr = prim.GetAttribute("inputs:color")
                if color_attr:
                    color_attr.Set(Gf.Vec3f(value[0], value[1], value[2]))
                    return True
                    
        elif override_type == OVERRIDE_MATERIAL:
            material_prim = stage.GetPrimAtPath(value)
            if material_prim and material_prim.IsValid():
                material = UsdShade.Material(material_prim)
                binding_api = UsdShade.MaterialBindingAPI(prim)
                binding_api.Bind(material)
                return True
        
        return False
        
    except Exception as e:
        safe_log(f"[Override] Error applying to {prim_path}: {e}")
        return False


def apply_collection_overrides(collection_path: str) -> Tuple[int, str]:
    """
    Apply all overrides on a Collection to its members.
    
    Args:
        collection_path: Collection path
        
    Returns:
        Tuple[int, str]: (count_applied, message)
    """
    from .render_collection import get_collection_members
    
    overrides = get_collection_overrides(collection_path)
    if not overrides:
        return 0, "No overrides to apply"
    
    members = get_collection_members(collection_path)
    if not members:
        return 0, "No members in collection"
    
    applied = 0
    
    for member_path in members:
        for override_type, override_value in overrides.items():
            if apply_override_to_prim(member_path, override_type, override_value):
                applied += 1
    
    return applied, f"Applied {applied} overrides"


def apply_override_to_collection(
    collection_path: str,
    override_type: str,
    property_name: str,
    value: Any
) -> Tuple[int, int, str]:
    """
    Apply property override to all Collection members immediately.
    
    This is for direct manipulation, not stored overrides.
    
    Args:
        collection_path: Collection path
        override_type: Override type
        property_name: Property name (for light properties)
        value: Value to set
        
    Returns:
        Tuple[int, int, str]: (success_count, fail_count, message)
    """
    from .render_collection import get_collection_members
    
    members = get_collection_members(collection_path)
    if not members:
        return 0, 0, "No members"
    
    success = 0
    fail = 0
    
    for member_path in members:
        ok = False
        
        if override_type == OVERRIDE_VISIBILITY:
            result, _ = set_visibility_override(member_path, value)
            ok = result
            
        elif override_type == "light":
            result, _ = set_light_property(member_path, property_name, value)
            ok = result
            
        elif override_type == OVERRIDE_MATERIAL:
            result, _ = set_material_binding(member_path, value)
            ok = result
            
        else:
            ok = apply_override_to_prim(member_path, override_type, value)
        
        if ok:
            success += 1
        else:
            fail += 1
    
    return success, fail, f"Applied to {success}/{len(members)} members"


# =============================================================================
# Light Property Helpers
# =============================================================================

LIGHT_PROPERTIES = ["intensity", "exposure", "color", "enableColorTemperature", 
                    "colorTemperature", "diffuse", "specular"]


def get_light_properties(light_path: str) -> Dict[str, Any]:
    """Get all properties of a light."""
    stage = get_stage()
    if not stage:
        return {}
    
    prim = stage.GetPrimAtPath(light_path)
    if not prim or not prim.IsValid():
        return {}
    
    result = {}
    
    for prop_name in LIGHT_PROPERTIES:
        attr = prim.GetAttribute(f"inputs:{prop_name}")
        if not attr:
            attr = prim.GetAttribute(prop_name)
        
        if attr and attr.HasAuthoredValue():
            result[prop_name] = attr.Get()
    
    return result


def clear_material_binding(prim_path: str) -> Tuple[bool, str]:
    """Clear material binding from a prim."""
    stage = get_stage()
    if not stage:
        return False, "No stage"
    
    prim = stage.GetPrimAtPath(prim_path)
    if not prim or not prim.IsValid():
        return False, "Prim not found"
    
    try:
        binding_api = UsdShade.MaterialBindingAPI(prim)
        binding_api.UnbindAllBindings()
        return True, "Cleared material binding"
    except Exception as e:
        return False, f"Error: {e}"


# =============================================================================
# Property Introspection
# =============================================================================

def get_overridable_properties(prim_path: str) -> List[Dict[str, Any]]:
    """
    Get list of properties that can be overridden on a prim.
    """
    stage = get_stage()
    if not stage:
        return []
    
    prim = stage.GetPrimAtPath(prim_path)
    if not prim or not prim.IsValid():
        return []
    
    result = []
    
    for attr in prim.GetAttributes():
        attr_name = attr.GetName()
        
        # Skip internal attributes
        if attr_name.startswith("xformOp") and ":" not in attr_name:
            continue
        
        result.append({
            "name": attr_name,
            "type": str(attr.GetTypeName()),
            "has_value": attr.HasAuthoredValue(),
            "value": attr.Get() if attr.HasAuthoredValue() else None,
        })
    
    return result


def get_visibility(prim_path: str) -> Optional[str]:
    """Get prim visibility state."""
    stage = get_stage()
    if not stage:
        return None
    
    prim = stage.GetPrimAtPath(prim_path)
    if not prim or not prim.IsValid():
        return None
    
    try:
        imageable = UsdGeom.Imageable(prim)
        if not imageable:
            return None
        
        vis_attr = imageable.GetVisibilityAttr()
        if vis_attr and vis_attr.HasAuthoredValue():
            return vis_attr.Get()
        
        computed = imageable.ComputeVisibility()
        return "visible" if computed == UsdGeom.Tokens.inherited else "invisible"
        
    except Exception:
        return None
