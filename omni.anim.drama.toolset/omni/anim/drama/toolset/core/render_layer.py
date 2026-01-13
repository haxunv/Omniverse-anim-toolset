# -*- coding: utf-8 -*-
"""
Render Layer Core Logic (Maya-Style)
=====================================

Provides Maya Render Setup style layer management using USD sublayer mechanism.

Key Concepts:
    - Each RenderLayer corresponds to a USD anonymous sublayer
    - Switching layers changes the Edit Target
    - Overrides are stored in the layer's sublayer, not affecting the base scene
    - Scene layer is read-only (like Maya's defaultRenderLayer)

Main Functions:
    - create_render_layer: Create a new render layer with USD sublayer
    - delete_render_layer: Delete render layer
    - switch_to_layer: Switch active layer (changes Edit Target)
    - set_layer_visible/solo/renderable: Layer state controls
    - get_all_render_layers: Query all layers
"""

from typing import List, Optional, Tuple, Dict, Any
from pxr import Usd, Sdf, UsdGeom

from .stage_utils import get_stage, safe_log


# =============================================================================
# Constants
# =============================================================================

RENDER_SETUP_PATH = "/RenderSetup"
LAYERS_PATH = f"{RENDER_SETUP_PATH}/Layers"
SCENE_LAYER_NAME = "defaultRenderLayer"

# Custom attributes (drama namespace)
ATTR_VISIBLE = "drama:visible"
ATTR_SOLO = "drama:solo"
ATTR_RENDERABLE = "drama:renderable"
ATTR_LAYER_ORDER = "drama:order"
ATTR_SUBLAYER_ID = "drama:sublayerId"
ATTR_IS_SCENE_LAYER = "drama:isSceneLayer"

# AOV override attribute (stored as JSON)
ATTR_AOV_OVERRIDES = "drama:aovOverrides"

# Omniverse supported AOVs
OMNIVERSE_AOVS = {
    "PtZDepth": {"name": "Z-Depth", "setting": "/rtx/post/aov/zDepth", "data_type": "float"},
    "PtWorldNormal": {"name": "World Normal", "setting": "/rtx/post/aov/worldNormal", "data_type": "normal3f"},
    "PtViewNormal": {"name": "View Normal", "setting": "/rtx/post/aov/viewNormal", "data_type": "normal3f"},
    "PtWorldPosition": {"name": "World Position", "setting": "/rtx/post/aov/worldPosition", "data_type": "point3f"},
    "PtDiffuseFilter": {"name": "Diffuse Filter", "setting": "/rtx/post/aov/diffuseFilter", "data_type": "color4f"},
    "PtDirectIllumination": {"name": "Direct Illumination", "setting": "/rtx/post/aov/directIllumination", "data_type": "color4f"},
    "PtGlobalIllumination": {"name": "Global Illumination", "setting": "/rtx/post/aov/globalIllumination", "data_type": "color4f"},
    "PtReflection": {"name": "Reflection", "setting": "/rtx/post/aov/reflection", "data_type": "color4f"},
    "PtRefraction": {"name": "Refraction", "setting": "/rtx/post/aov/refraction", "data_type": "color4f"},
    "PtBackground": {"name": "Background", "setting": "/rtx/post/aov/background", "data_type": "color4f"},
    "PtMotionVectors": {"name": "Motion Vectors", "setting": "/rtx/post/aov/motionVectors", "data_type": "float3"},
    "PtSubsurfaceScattering": {"name": "Subsurface", "setting": "/rtx/post/aov/subsurfaceScattering", "data_type": "color4f"},
    "PtSelfIllumination": {"name": "Self-Illumination", "setting": "/rtx/post/aov/selfIllumination", "data_type": "color4f"},
}

# Global: sublayer cache {layer_path: Sdf.Layer}
_sublayer_cache: Dict[str, Sdf.Layer] = {}

# Global: current active layer path
_active_layer_path: str = ""


# =============================================================================
# Initialization
# =============================================================================

def ensure_render_setup_structure() -> Tuple[bool, str]:
    """
    Ensure RenderSetup hierarchy exists.
    
    Creates:
    - /RenderSetup
    - /RenderSetup/Layers
    - /RenderSetup/Layers/defaultRenderLayer (Scene layer, non-renderable by default)
    
    Returns:
        Tuple[bool, str]: (success, message)
    """
    stage = get_stage()
    if not stage:
        return False, "No stage available"
    
    try:
        # Create /RenderSetup
        render_setup_prim = stage.GetPrimAtPath(RENDER_SETUP_PATH)
        if not render_setup_prim or not render_setup_prim.IsValid():
            render_setup_prim = stage.DefinePrim(RENDER_SETUP_PATH, "Scope")
            safe_log(f"[RenderLayer] Created {RENDER_SETUP_PATH}")
        
        # Create /RenderSetup/Layers
        layers_prim = stage.GetPrimAtPath(LAYERS_PATH)
        if not layers_prim or not layers_prim.IsValid():
            layers_prim = stage.DefinePrim(LAYERS_PATH, "Scope")
            safe_log(f"[RenderLayer] Created {LAYERS_PATH}")
        
        # Create Scene layer (defaultRenderLayer) if not exists
        scene_layer_path = f"{LAYERS_PATH}/{SCENE_LAYER_NAME}"
        scene_prim = stage.GetPrimAtPath(scene_layer_path)
        if not scene_prim or not scene_prim.IsValid():
            scene_prim = stage.DefinePrim(scene_layer_path, "Scope")
            scene_prim.CreateAttribute(ATTR_VISIBLE, Sdf.ValueTypeNames.Bool).Set(True)
            scene_prim.CreateAttribute(ATTR_SOLO, Sdf.ValueTypeNames.Bool).Set(False)
            scene_prim.CreateAttribute(ATTR_RENDERABLE, Sdf.ValueTypeNames.Bool).Set(False)
            scene_prim.CreateAttribute(ATTR_LAYER_ORDER, Sdf.ValueTypeNames.Int).Set(-1)
            scene_prim.CreateAttribute(ATTR_IS_SCENE_LAYER, Sdf.ValueTypeNames.Bool).Set(True)
            safe_log(f"[RenderLayer] Created Scene layer: {SCENE_LAYER_NAME}")
        
        return True, "RenderSetup structure ready"
        
    except Exception as e:
        msg = f"Error creating RenderSetup structure: {e}"
        safe_log(f"[RenderLayer] {msg}")
        return False, msg


# =============================================================================
# Layer Creation and Deletion
# =============================================================================

def create_render_layer(name: str) -> Tuple[bool, str, Optional[str]]:
    """
    Create a new render layer with associated USD sublayer.
    
    Args:
        name: Layer name
        
    Returns:
        Tuple[bool, str, Optional[str]]: (success, message, layer_path)
    """
    stage = get_stage()
    if not stage:
        return False, "No stage available", None
    
    # Ensure structure exists
    success, msg = ensure_render_setup_structure()
    if not success:
        return False, msg, None
    
    # Clean name
    clean_name = "".join(c if c.isalnum() or c == "_" else "_" for c in name)
    if not clean_name:
        clean_name = "layer"
    
    # Prevent using reserved name
    if clean_name == SCENE_LAYER_NAME:
        clean_name = f"{clean_name}_1"
    
    layer_path = f"{LAYERS_PATH}/{clean_name}"
    
    # Check if exists
    existing_prim = stage.GetPrimAtPath(layer_path)
    if existing_prim and existing_prim.IsValid():
        return False, f"Layer already exists: {clean_name}", None
    
    try:
        # Create layer prim
        layer_prim = stage.DefinePrim(layer_path, "Scope")
        
        # Create anonymous sublayer for this layer
        sublayer = Sdf.Layer.CreateAnonymous(f"RenderLayer_{clean_name}")
        sublayer_id = sublayer.identifier
        
        # Cache sublayer
        _sublayer_cache[layer_path] = sublayer
        
        # Add custom attributes
        layer_prim.CreateAttribute(ATTR_VISIBLE, Sdf.ValueTypeNames.Bool).Set(True)
        layer_prim.CreateAttribute(ATTR_SOLO, Sdf.ValueTypeNames.Bool).Set(False)
        layer_prim.CreateAttribute(ATTR_RENDERABLE, Sdf.ValueTypeNames.Bool).Set(True)
        layer_prim.CreateAttribute(ATTR_SUBLAYER_ID, Sdf.ValueTypeNames.String).Set(sublayer_id)
        layer_prim.CreateAttribute(ATTR_IS_SCENE_LAYER, Sdf.ValueTypeNames.Bool).Set(False)
        
        # Set order
        order = _get_next_layer_order()
        layer_prim.CreateAttribute(ATTR_LAYER_ORDER, Sdf.ValueTypeNames.Int).Set(order)
        
        # Create Collections container
        collections_path = f"{layer_path}/Collections"
        stage.DefinePrim(collections_path, "Scope")
        
        # Create AOVs container
        aovs_path = f"{layer_path}/AOVs"
        stage.DefinePrim(aovs_path, "Scope")
        
        msg = f"Created render layer: {clean_name}"
        safe_log(f"[RenderLayer] {msg}")
        return True, msg, layer_path
        
    except Exception as e:
        msg = f"Error creating layer: {e}"
        safe_log(f"[RenderLayer] {msg}")
        return False, msg, None


def delete_render_layer(layer_path: str) -> Tuple[bool, str]:
    """
    Delete a render layer.
    
    Args:
        layer_path: Layer USD path
        
    Returns:
        Tuple[bool, str]: (success, message)
    """
    stage = get_stage()
    if not stage:
        return False, "No stage available"
    
    layer_prim = stage.GetPrimAtPath(layer_path)
    if not layer_prim or not layer_prim.IsValid():
        return False, f"Layer not found: {layer_path}"
    
    # Prevent deleting Scene layer
    is_scene = get_layer_attribute(layer_path, ATTR_IS_SCENE_LAYER, False)
    if is_scene:
        return False, "Cannot delete Scene layer"
    
    try:
        layer_name = layer_prim.GetName()
        
        # Remove from sublayer cache
        if layer_path in _sublayer_cache:
            del _sublayer_cache[layer_path]
        
        # Remove prim
        stage.RemovePrim(layer_path)
        
        msg = f"Deleted render layer: {layer_name}"
        safe_log(f"[RenderLayer] {msg}")
        return True, msg
        
    except Exception as e:
        msg = f"Error deleting layer: {e}"
        safe_log(f"[RenderLayer] {msg}")
        return False, msg


def rename_render_layer(layer_path: str, new_name: str) -> Tuple[bool, str, Optional[str]]:
    """
    Rename a render layer.
    
    Args:
        layer_path: Current layer path
        new_name: New name
        
    Returns:
        Tuple[bool, str, Optional[str]]: (success, message, new_path)
    """
    stage = get_stage()
    if not stage:
        return False, "No stage available", None
    
    layer_prim = stage.GetPrimAtPath(layer_path)
    if not layer_prim or not layer_prim.IsValid():
        return False, f"Layer not found: {layer_path}", None
    
    # Cannot rename Scene layer
    is_scene = get_layer_attribute(layer_path, ATTR_IS_SCENE_LAYER, False)
    if is_scene:
        return False, "Cannot rename Scene layer", None
    
    # Clean name
    clean_name = "".join(c if c.isalnum() or c == "_" else "_" for c in new_name)
    if not clean_name:
        return False, "Invalid name", None
    
    new_path = f"{LAYERS_PATH}/{clean_name}"
    
    if stage.GetPrimAtPath(new_path):
        return False, f"Layer already exists: {clean_name}", None
    
    try:
        # Get old properties
        visible = get_layer_attribute(layer_path, ATTR_VISIBLE, True)
        solo = get_layer_attribute(layer_path, ATTR_SOLO, False)
        renderable = get_layer_attribute(layer_path, ATTR_RENDERABLE, True)
        order = get_layer_attribute(layer_path, ATTR_LAYER_ORDER, 0)
        sublayer_id = get_layer_attribute(layer_path, ATTR_SUBLAYER_ID, "")
        
        # Transfer sublayer cache
        sublayer = _sublayer_cache.get(layer_path)
        
        # Create new layer
        new_prim = stage.DefinePrim(new_path, "Scope")
        new_prim.CreateAttribute(ATTR_VISIBLE, Sdf.ValueTypeNames.Bool).Set(visible)
        new_prim.CreateAttribute(ATTR_SOLO, Sdf.ValueTypeNames.Bool).Set(solo)
        new_prim.CreateAttribute(ATTR_RENDERABLE, Sdf.ValueTypeNames.Bool).Set(renderable)
        new_prim.CreateAttribute(ATTR_LAYER_ORDER, Sdf.ValueTypeNames.Int).Set(order)
        new_prim.CreateAttribute(ATTR_SUBLAYER_ID, Sdf.ValueTypeNames.String).Set(sublayer_id)
        new_prim.CreateAttribute(ATTR_IS_SCENE_LAYER, Sdf.ValueTypeNames.Bool).Set(False)
        
        # Copy children (Collections, AOVs)
        for child in layer_prim.GetChildren():
            _copy_prim_recursive(child, new_path)
        
        # Update cache
        if sublayer:
            del _sublayer_cache[layer_path]
            _sublayer_cache[new_path] = sublayer
        
        # Delete old layer
        stage.RemovePrim(layer_path)
        
        msg = f"Renamed layer to: {clean_name}"
        safe_log(f"[RenderLayer] {msg}")
        return True, msg, new_path
        
    except Exception as e:
        msg = f"Error renaming layer: {e}"
        safe_log(f"[RenderLayer] {msg}")
        return False, msg, None


def _copy_prim_recursive(prim: Usd.Prim, new_parent_path: str) -> None:
    """Recursively copy a prim to new parent."""
    stage = prim.GetStage()
    new_path = f"{new_parent_path}/{prim.GetName()}"
    
    new_prim = stage.DefinePrim(new_path, prim.GetTypeName())
    
    # Copy attributes
    for attr in prim.GetAttributes():
        if attr.HasAuthoredValue():
            new_attr = new_prim.CreateAttribute(attr.GetName(), attr.GetTypeName())
            new_attr.Set(attr.Get())
    
    # Copy relationships
    for rel in prim.GetRelationships():
        if rel.HasAuthoredTargets():
            new_rel = new_prim.CreateRelationship(rel.GetName())
            for target in rel.GetTargets():
                new_rel.AddTarget(target)
    
    # Recurse children
    for child in prim.GetChildren():
        _copy_prim_recursive(child, new_path)


# =============================================================================
# Layer Attribute Operations
# =============================================================================

def get_layer_attribute(layer_path: str, attr_name: str, default: Any = None) -> Any:
    """Get layer attribute value."""
    stage = get_stage()
    if not stage:
        return default
    
    prim = stage.GetPrimAtPath(layer_path)
    if not prim or not prim.IsValid():
        return default
    
    attr = prim.GetAttribute(attr_name)
    if attr and attr.HasAuthoredValue():
        return attr.Get()
    
    return default


def set_layer_attribute(layer_path: str, attr_name: str, value: Any) -> bool:
    """Set layer attribute value."""
    stage = get_stage()
    if not stage:
        return False
    
    prim = stage.GetPrimAtPath(layer_path)
    if not prim or not prim.IsValid():
        return False
    
    try:
        attr = prim.GetAttribute(attr_name)
        if attr:
            attr.Set(value)
            return True
    except Exception:
        pass
    
    return False


def set_layer_visible(layer_path: str, visible: bool) -> Tuple[bool, str]:
    """
    Set layer visibility.
    
    When visible=True, the layer's overrides are applied to the viewport.
    """
    success = set_layer_attribute(layer_path, ATTR_VISIBLE, visible)
    if success:
        _update_layer_visibility_effect(layer_path, visible)
        state = "visible" if visible else "hidden"
        return True, f"Layer {state}"
    return False, "Failed to set visibility"


def set_layer_solo(layer_path: str, solo: bool) -> Tuple[bool, str]:
    """
    Set layer Solo mode.
    
    When Solo is ON:
    - Only this layer's Collection members are visible
    - All other objects are hidden
    """
    success = set_layer_attribute(layer_path, ATTR_SOLO, solo)
    if not success:
        return False, "Failed to set solo"
    
    if solo:
        # Turn off solo on other layers
        all_layers = get_all_render_layers()
        for layer in all_layers:
            if layer["path"] != layer_path and layer["solo"]:
                set_layer_attribute(layer["path"], ATTR_SOLO, False)
        
        # Apply solo effect
        _apply_solo_effect(layer_path)
        return True, "Solo ON"
    else:
        # Restore visibility
        _clear_solo_effect()
        return True, "Solo OFF"


def set_layer_renderable(layer_path: str, renderable: bool) -> Tuple[bool, str]:
    """Set whether layer is renderable."""
    success = set_layer_attribute(layer_path, ATTR_RENDERABLE, renderable)
    if success:
        state = "renderable" if renderable else "not renderable"
        return True, f"Layer {state}"
    return False, "Failed to set renderable"


# =============================================================================
# Layer Switching (Edit Target)
# =============================================================================

def switch_to_layer(layer_path: str) -> Tuple[bool, str]:
    """
    Switch to a render layer (Maya style).
    
    This changes the USD Edit Target to this layer's sublayer,
    so any subsequent edits go into this layer, not the base scene.
    
    Args:
        layer_path: Layer path to switch to
        
    Returns:
        Tuple[bool, str]: (success, message)
    """
    global _active_layer_path
    
    stage = get_stage()
    if not stage:
        return False, "No stage available"
    
    layer_prim = stage.GetPrimAtPath(layer_path)
    if not layer_prim or not layer_prim.IsValid():
        return False, f"Layer not found: {layer_path}"
    
    try:
        is_scene = get_layer_attribute(layer_path, ATTR_IS_SCENE_LAYER, False)
        
        if is_scene:
            # Switch to root layer (Scene layer)
            root_layer = stage.GetRootLayer()
            stage.SetEditTarget(Usd.EditTarget(root_layer))
            _active_layer_path = layer_path
            safe_log("[RenderLayer] Switched to Scene layer (root)")
            return True, "Switched to Scene layer"
        
        # Get or create sublayer
        sublayer = _get_or_create_sublayer(layer_path)
        if not sublayer:
            return False, "Failed to get layer sublayer"
        
        # Set edit target to this sublayer
        root_layer = stage.GetRootLayer()
        
        # Make sure sublayer is in the stage's layer stack
        if sublayer.identifier not in root_layer.subLayerPaths:
            root_layer.subLayerPaths.append(sublayer.identifier)
        
        # Set edit target
        stage.SetEditTarget(Usd.EditTarget(sublayer))
        
        _active_layer_path = layer_path
        
        layer_name = layer_prim.GetName()
        msg = f"Switched to layer: {layer_name}"
        safe_log(f"[RenderLayer] {msg}")
        return True, msg
        
    except Exception as e:
        msg = f"Error switching layer: {e}"
        safe_log(f"[RenderLayer] {msg}")
        return False, msg


def get_active_layer_path() -> str:
    """Get currently active layer path."""
    return _active_layer_path


def _get_or_create_sublayer(layer_path: str) -> Optional[Sdf.Layer]:
    """Get or create sublayer for a layer."""
    # Check cache first
    if layer_path in _sublayer_cache:
        return _sublayer_cache[layer_path]
    
    # Try to find from attribute
    sublayer_id = get_layer_attribute(layer_path, ATTR_SUBLAYER_ID, "")
    
    if sublayer_id:
        try:
            sublayer = Sdf.Layer.Find(sublayer_id)
            if sublayer:
                _sublayer_cache[layer_path] = sublayer
                return sublayer
        except Exception:
            pass
    
    # Create new anonymous layer
    layer_name = layer_path.split("/")[-1]
    sublayer = Sdf.Layer.CreateAnonymous(f"RenderLayer_{layer_name}")
    
    # Store ID
    set_layer_attribute(layer_path, ATTR_SUBLAYER_ID, sublayer.identifier)
    
    _sublayer_cache[layer_path] = sublayer
    return sublayer


# =============================================================================
# Solo/Visibility Effects
# =============================================================================

_solo_hidden_prims: set = set()


def _apply_solo_effect(layer_path: str) -> None:
    """Apply Solo effect - hide everything except layer's collection members."""
    global _solo_hidden_prims
    
    stage = get_stage()
    if not stage:
        return
    
    from .render_collection import get_collections_in_layer, get_collection_members
    
    # Get all members in this layer's collections
    visible_paths = set()
    collections = get_collections_in_layer(layer_path)
    
    def collect_members(col_info):
        members = get_collection_members(col_info["path"])
        visible_paths.update(members)
        for child in col_info.get("children", []):
            collect_members(child)
    
    for col in collections:
        collect_members(col)
    
    # Also include ancestors of visible prims
    ancestor_paths = set()
    for path in visible_paths:
        parts = path.split("/")
        for i in range(1, len(parts)):
            ancestor_paths.add("/".join(parts[:i+1]))
    
    visible_paths.update(ancestor_paths)
    
    # Hide all other imageables
    _solo_hidden_prims.clear()
    
    for prim in stage.Traverse():
        prim_path = prim.GetPath().pathString
        
        # Skip RenderSetup
        if prim_path.startswith(RENDER_SETUP_PATH):
            continue
        
        # Skip if in visible set
        if prim_path in visible_paths:
            continue
        
        # Hide if imageable
        if prim.IsA(UsdGeom.Imageable):
            imageable = UsdGeom.Imageable(prim)
            vis_attr = imageable.GetVisibilityAttr()
            if vis_attr:
                current_vis = vis_attr.Get()
                if current_vis != UsdGeom.Tokens.invisible:
                    try:
                        imageable.MakeInvisible()
                        _solo_hidden_prims.add(prim_path)
                    except Exception:
                        pass


def _clear_solo_effect() -> None:
    """Clear Solo effect - restore hidden prims."""
    global _solo_hidden_prims
    
    stage = get_stage()
    if not stage:
        return
    
    for prim_path in _solo_hidden_prims:
        prim = stage.GetPrimAtPath(prim_path)
        if prim and prim.IsValid():
            try:
                imageable = UsdGeom.Imageable(prim)
                if imageable:
                    imageable.MakeVisible()
            except Exception:
                pass
    
    _solo_hidden_prims.clear()


def _update_layer_visibility_effect(layer_path: str, visible: bool) -> None:
    """Update visibility based on layer visible state."""
    # This can be expanded to apply/remove layer overrides
    pass


# =============================================================================
# Layer Queries
# =============================================================================

def get_all_render_layers() -> List[Dict[str, Any]]:
    """
    Get all render layers.
    
    Returns:
        List[Dict]: Layer info list, sorted by order
    """
    stage = get_stage()
    if not stage:
        return []
    
    layers_prim = stage.GetPrimAtPath(LAYERS_PATH)
    if not layers_prim or not layers_prim.IsValid():
        return []
    
    layers = []
    for child in layers_prim.GetChildren():
        layer_path = child.GetPath().pathString
        
        # Skip non-layer children (Collections, AOVs containers)
        if not child.HasAttribute(ATTR_VISIBLE):
            continue
        
        # Count collections
        collections_path = f"{layer_path}/Collections"
        collections_prim = stage.GetPrimAtPath(collections_path)
        collection_count = len(list(collections_prim.GetChildren())) if collections_prim else 0
        
        # Count AOVs
        aovs_path = f"{layer_path}/AOVs"
        aovs_prim = stage.GetPrimAtPath(aovs_path)
        aov_count = len(list(aovs_prim.GetChildren())) if aovs_prim else 0
        
        is_scene = get_layer_attribute(layer_path, ATTR_IS_SCENE_LAYER, False)
        
        layer_info = {
            "path": layer_path,
            "name": child.GetName(),
            "visible": get_layer_attribute(layer_path, ATTR_VISIBLE, True),
            "solo": get_layer_attribute(layer_path, ATTR_SOLO, False),
            "renderable": get_layer_attribute(layer_path, ATTR_RENDERABLE, True),
            "order": get_layer_attribute(layer_path, ATTR_LAYER_ORDER, 0),
            "collection_count": collection_count,
            "aov_count": aov_count,
            "is_scene_layer": is_scene,
            "is_active": layer_path == _active_layer_path,
        }
        layers.append(layer_info)
    
    layers.sort(key=lambda x: x["order"])
    return layers


def get_render_layer_info(layer_path: str) -> Optional[Dict[str, Any]]:
    """Get detailed info for a single layer."""
    stage = get_stage()
    if not stage:
        return None
    
    layer_prim = stage.GetPrimAtPath(layer_path)
    if not layer_prim or not layer_prim.IsValid():
        return None
    
    from .render_collection import get_collection_info
    
    # Get collections
    collections = []
    collections_path = f"{layer_path}/Collections"
    collections_prim = stage.GetPrimAtPath(collections_path)
    if collections_prim:
        for child in collections_prim.GetChildren():
            col_info = get_collection_info(child.GetPath().pathString)
            if col_info:
                collections.append(col_info)
    
    return {
        "path": layer_path,
        "name": layer_prim.GetName(),
        "visible": get_layer_attribute(layer_path, ATTR_VISIBLE, True),
        "solo": get_layer_attribute(layer_path, ATTR_SOLO, False),
        "renderable": get_layer_attribute(layer_path, ATTR_RENDERABLE, True),
        "order": get_layer_attribute(layer_path, ATTR_LAYER_ORDER, 0),
        "collections": collections,
        "is_scene_layer": get_layer_attribute(layer_path, ATTR_IS_SCENE_LAYER, False),
        "is_active": layer_path == _active_layer_path,
    }


def _get_next_layer_order() -> int:
    """Get next layer order number."""
    layers = get_all_render_layers()
    if not layers:
        return 0
    return max(l["order"] for l in layers) + 1


# =============================================================================
# Layer Ordering
# =============================================================================

def move_layer_up(layer_path: str) -> Tuple[bool, str]:
    """Move layer up in order."""
    layers = get_all_render_layers()
    
    current_idx = -1
    for i, layer in enumerate(layers):
        if layer["path"] == layer_path:
            current_idx = i
            break
    
    if current_idx == -1:
        return False, "Layer not found"
    
    if current_idx == 0:
        return False, "Layer is already at the top"
    
    # Swap orders
    current_order = layers[current_idx]["order"]
    prev_order = layers[current_idx - 1]["order"]
    
    set_layer_attribute(layer_path, ATTR_LAYER_ORDER, prev_order)
    set_layer_attribute(layers[current_idx - 1]["path"], ATTR_LAYER_ORDER, current_order)
    
    return True, "Layer moved up"


def move_layer_down(layer_path: str) -> Tuple[bool, str]:
    """Move layer down in order."""
    layers = get_all_render_layers()
    
    current_idx = -1
    for i, layer in enumerate(layers):
        if layer["path"] == layer_path:
            current_idx = i
            break
    
    if current_idx == -1:
        return False, "Layer not found"
    
    if current_idx >= len(layers) - 1:
        return False, "Layer is already at the bottom"
    
    # Swap orders
    current_order = layers[current_idx]["order"]
    next_order = layers[current_idx + 1]["order"]
    
    set_layer_attribute(layer_path, ATTR_LAYER_ORDER, next_order)
    set_layer_attribute(layers[current_idx + 1]["path"], ATTR_LAYER_ORDER, current_order)
    
    return True, "Layer moved down"


def move_layer_to_top(layer_path: str) -> Tuple[bool, str]:
    """Move layer to top."""
    layers = get_all_render_layers()
    if not layers:
        return False, "No layers"
    
    min_order = min(l["order"] for l in layers)
    set_layer_attribute(layer_path, ATTR_LAYER_ORDER, min_order - 1)
    
    return True, "Layer moved to top"


def move_layer_to_bottom(layer_path: str) -> Tuple[bool, str]:
    """Move layer to bottom."""
    layers = get_all_render_layers()
    if not layers:
        return False, "No layers"
    
    max_order = max(l["order"] for l in layers)
    set_layer_attribute(layer_path, ATTR_LAYER_ORDER, max_order + 1)
    
    return True, "Layer moved to bottom"


# =============================================================================
# AOV Sub-node Management (Maya Style)
# =============================================================================

ATTR_AOV_SOURCE_TYPE = "drama:aovSourceType"
ATTR_AOV_NAME_OVERRIDE = "drama:aovNameOverride"
ATTR_AOV_DRIVER = "drama:aovDriver"
ATTR_AOV_FILTER = "drama:aovFilter"
ATTR_AOV_ENABLED = "drama:aovEnabled"


def create_layer_aov(
    layer_path: str,
    aov_type_id: str,
    name_override: str = "",
    driver: str = "exr",
    filter_type: str = "gaussian",
    enabled: bool = True
) -> Tuple[bool, str, Optional[str]]:
    """
    Create AOV sub-node under a layer.
    
    Similar to Maya's "Create Absolute Override for Active Layer".
    
    Args:
        layer_path: Layer path
        aov_type_id: AOV type ID (e.g. "PtZDepth", "PtWorldNormal")
        name_override: Custom output name
        driver: Output driver ("exr", "png", etc.)
        filter_type: Filter type
        enabled: Whether enabled
        
    Returns:
        Tuple[bool, str, Optional[str]]: (success, message, aov_path)
    """
    stage = get_stage()
    if not stage:
        return False, "No stage available", None
    
    if aov_type_id not in OMNIVERSE_AOVS:
        return False, f"Unknown AOV type: {aov_type_id}", None
    
    aov_info = OMNIVERSE_AOVS[aov_type_id]
    aovs_container = f"{layer_path}/AOVs"
    
    # Ensure AOVs container exists
    aovs_prim = stage.GetPrimAtPath(aovs_container)
    if not aovs_prim or not aovs_prim.IsValid():
        aovs_prim = stage.DefinePrim(aovs_container, "Scope")
    
    aov_path = f"{aovs_container}/{aov_type_id}"
    
    # Check if exists
    if stage.GetPrimAtPath(aov_path):
        return False, f"AOV already exists in this layer: {aov_type_id}", None
    
    try:
        aov_prim = stage.DefinePrim(aov_path, "Scope")
        
        aov_prim.CreateAttribute(ATTR_AOV_SOURCE_TYPE, Sdf.ValueTypeNames.String).Set(aov_type_id)
        aov_prim.CreateAttribute(ATTR_AOV_NAME_OVERRIDE, Sdf.ValueTypeNames.String).Set(name_override or aov_info["name"])
        aov_prim.CreateAttribute(ATTR_AOV_DRIVER, Sdf.ValueTypeNames.String).Set(driver)
        aov_prim.CreateAttribute(ATTR_AOV_FILTER, Sdf.ValueTypeNames.String).Set(filter_type)
        aov_prim.CreateAttribute(ATTR_AOV_ENABLED, Sdf.ValueTypeNames.Bool).Set(enabled)
        
        msg = f"Created AOV '{aov_info['name']}' in layer"
        safe_log(f"[RenderLayer] {msg}")
        return True, msg, aov_path
        
    except Exception as e:
        return False, f"Error creating AOV: {e}", None


def delete_layer_aov(layer_path: str, aov_type_id: str) -> Tuple[bool, str]:
    """Delete AOV from layer."""
    stage = get_stage()
    if not stage:
        return False, "No stage available"
    
    aov_path = f"{layer_path}/AOVs/{aov_type_id}"
    
    aov_prim = stage.GetPrimAtPath(aov_path)
    if not aov_prim or not aov_prim.IsValid():
        return False, f"AOV not found: {aov_type_id}"
    
    try:
        stage.RemovePrim(aov_path)
        return True, f"Deleted AOV '{aov_type_id}'"
    except Exception as e:
        return False, f"Error: {e}"


def get_layer_aov_nodes(layer_path: str) -> List[Dict[str, Any]]:
    """Get all AOV nodes in a layer."""
    stage = get_stage()
    if not stage:
        return []
    
    aovs_path = f"{layer_path}/AOVs"
    aovs_prim = stage.GetPrimAtPath(aovs_path)
    
    if not aovs_prim or not aovs_prim.IsValid():
        return []
    
    result = []
    for child in aovs_prim.GetChildren():
        aov_path = child.GetPath().pathString
        info = get_layer_aov_node_info(aov_path)
        if info:
            result.append(info)
    
    return result


def get_layer_aov_node_info(aov_node_path: str) -> Optional[Dict[str, Any]]:
    """Get AOV node info."""
    stage = get_stage()
    if not stage:
        return None
    
    aov_prim = stage.GetPrimAtPath(aov_node_path)
    if not aov_prim or not aov_prim.IsValid():
        return None
    
    def get_attr(name, default):
        attr = aov_prim.GetAttribute(name)
        return attr.Get() if attr and attr.HasAuthoredValue() else default
    
    source_type = get_attr(ATTR_AOV_SOURCE_TYPE, "")
    aov_base = OMNIVERSE_AOVS.get(source_type, {})
    
    return {
        "path": aov_node_path,
        "node_name": aov_prim.GetName(),
        "source_type": source_type,
        "display_name": aov_base.get("name", source_type),
        "name_override": get_attr(ATTR_AOV_NAME_OVERRIDE, ""),
        "driver": get_attr(ATTR_AOV_DRIVER, "exr"),
        "filter": get_attr(ATTR_AOV_FILTER, "gaussian"),
        "enabled": get_attr(ATTR_AOV_ENABLED, True),
        "setting": aov_base.get("setting", ""),
        "data_type": aov_base.get("data_type", "color4f"),
    }


def set_layer_aov_property(aov_node_path: str, property_name: str, value: Any) -> Tuple[bool, str]:
    """Set AOV node property."""
    stage = get_stage()
    if not stage:
        return False, "No stage available"
    
    aov_prim = stage.GetPrimAtPath(aov_node_path)
    if not aov_prim or not aov_prim.IsValid():
        return False, "AOV not found"
    
    attr_map = {
        "name_override": ATTR_AOV_NAME_OVERRIDE,
        "driver": ATTR_AOV_DRIVER,
        "filter": ATTR_AOV_FILTER,
        "enabled": ATTR_AOV_ENABLED,
    }
    
    attr_name = attr_map.get(property_name)
    if not attr_name:
        return False, f"Unknown property: {property_name}"
    
    try:
        attr = aov_prim.GetAttribute(attr_name)
        if attr:
            attr.Set(value)
            return True, f"Set {property_name} = {value}"
    except Exception as e:
        return False, f"Error: {e}"
    
    return False, "Attribute not found"


def rename_layer_aov(aov_node_path: str, new_name: str) -> Tuple[bool, str]:
    """Rename AOV (set name_override)."""
    return set_layer_aov_property(aov_node_path, "name_override", new_name)


def toggle_layer_aov_enabled(aov_node_path: str) -> Tuple[bool, str]:
    """Toggle AOV enabled state."""
    info = get_layer_aov_node_info(aov_node_path)
    if not info:
        return False, "AOV not found"
    
    return set_layer_aov_property(aov_node_path, "enabled", not info["enabled"])


def create_standard_aovs_for_layer(layer_path: str) -> Tuple[int, str]:
    """Create standard AOV set for a layer."""
    standard_aovs = ["PtZDepth", "PtWorldNormal", "PtDiffuseFilter", "PtDirectIllumination", "PtReflection"]
    
    created = 0
    for aov_id in standard_aovs:
        success, _, _ = create_layer_aov(layer_path, aov_id)
        if success:
            created += 1
    
    return created, f"Created {created} standard AOVs"


def apply_layer_aovs_to_renderer(layer_path: str) -> Tuple[bool, str]:
    """Apply layer's AOV settings to Omniverse renderer."""
    try:
        import carb.settings
        settings = carb.settings.get_settings()
    except ImportError:
        return False, "carb.settings not available"
    
    aov_nodes = get_layer_aov_nodes(layer_path)
    if not aov_nodes:
        return True, "No AOVs in this layer"
    
    applied = 0
    for aov in aov_nodes:
        if aov["enabled"] and aov["setting"]:
            try:
                settings.set(aov["setting"], True)
                applied += 1
            except Exception:
                pass
    
    return True, f"Applied {applied} AOV settings"


def get_available_aovs() -> List[Dict[str, Any]]:
    """Get list of all available AOV types."""
    return [
        {"id": aov_id, "name": info["name"], "render_var": aov_id}
        for aov_id, info in OMNIVERSE_AOVS.items()
    ]


# =============================================================================
# Renderable Layers Query (for batch rendering)
# =============================================================================

def get_renderable_layers() -> List[Dict[str, Any]]:
    """Get all layers marked as renderable."""
    all_layers = get_all_render_layers()
    return [l for l in all_layers if l["renderable"]]


def clear_all_solo() -> Tuple[bool, str]:
    """Clear all layers' solo state."""
    all_layers = get_all_render_layers()
    
    for layer in all_layers:
        if layer["solo"]:
            set_layer_attribute(layer["path"], ATTR_SOLO, False)
    
    _clear_solo_effect()
    return True, "Cleared all solo"


# =============================================================================
# AOV Override Functions (for ViewModel compatibility)
# =============================================================================

def get_layer_aov_overrides(layer_path: str) -> Dict[str, bool]:
    """
    Get AOV override settings for a layer.
    
    Returns:
        Dict[str, bool]: AOV name to enabled state mapping
    """
    aov_nodes = get_layer_aov_nodes(layer_path)
    return {
        aov["source_type"]: aov.get("enabled", True)
        for aov in aov_nodes
    }


def set_layer_aov_overrides(layer_path: str, overrides: Dict[str, bool]) -> Tuple[bool, str]:
    """
    Set AOV override settings for a layer.
    
    Args:
        layer_path: Layer path
        overrides: Dict of AOV name to enabled state
    """
    for aov_id, enabled in overrides.items():
        aov_path = f"{layer_path}/AOVs/{aov_id}"
        set_layer_aov_property(aov_path, "enabled", enabled)
    
    return True, f"Set {len(overrides)} AOV overrides"


def set_layer_aov_enabled(layer_path: str, aov_name: str, enabled: bool) -> Tuple[bool, str]:
    """
    Set single AOV enabled state for a layer.
    
    Args:
        layer_path: Layer path
        aov_name: AOV name
        enabled: Whether to enable
    """
    aov_path = f"{layer_path}/AOVs/{aov_name}"
    return set_layer_aov_property(aov_path, "enabled", enabled)


def get_layer_aov_enabled(layer_path: str, aov_name: str) -> bool:
    """Get whether an AOV is enabled for a layer."""
    aov_path = f"{layer_path}/AOVs/{aov_name}"
    stage = get_stage()
    if not stage:
        return False
    
    prim = stage.GetPrimAtPath(aov_path)
    if not prim or not prim.IsValid():
        return False
    
    attr = prim.GetAttribute(ATTR_AOV_ENABLED)
    if attr and attr.HasAuthoredValue():
        return attr.Get()
    return True


def apply_layer_aov_settings(layer_path: str) -> Tuple[bool, str]:
    """
    Apply layer's AOV settings to renderer.
    Alias for apply_layer_aovs_to_renderer.
    """
    return apply_layer_aovs_to_renderer(layer_path)


def create_aov_override_for_layer(layer_path: str, aov_names: List[str] = None) -> Tuple[bool, str]:
    """
    Create AOV override for a layer.
    
    Args:
        layer_path: Layer path
        aov_names: List of AOV names to enable (None = standard set)
    """
    if aov_names is None:
        aov_names = ["z_depth", "world_normal", "diffuse_filter"]
    
    count = 0
    for aov_name in aov_names:
        success, _, _ = create_layer_aov(layer_path, aov_name)
        if success:
            count += 1
    
    return count > 0, f"Created {count} AOV overrides"


def clear_layer_aov_overrides(layer_path: str) -> Tuple[bool, str]:
    """Clear all AOV overrides for a layer."""
    stage = get_stage()
    if not stage:
        return False, "No stage"
    
    aovs_path = f"{layer_path}/AOVs"
    aovs_prim = stage.GetPrimAtPath(aovs_path)
    
    if aovs_prim and aovs_prim.IsValid():
        for child in aovs_prim.GetChildren():
            stage.RemovePrim(child.GetPath())
    
    return True, "Cleared AOV overrides"
