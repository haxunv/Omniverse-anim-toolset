# -*- coding: utf-8 -*-
"""
Render AOV Core Logic
=====================

Provides AOV (Arbitrary Output Variables) management for render layers.
Uses USD native RenderVar and RenderProduct for AOV configuration.

Main Features:
    - create_aov: Create AOV (creates UsdRender.Var)
    - delete_aov: Delete AOV
    - link_aov_to_layer: Link AOV to render layer
    - apply_aovs_to_render: Apply AOVs to render settings
"""

from typing import List, Optional, Tuple, Dict, Any
from pxr import Usd, Sdf, UsdRender

from .stage_utils import get_stage, safe_log
from .render_layer import RENDER_SETUP_PATH


# =============================================================================
# Constants
# =============================================================================

AOVS_PATH = f"{RENDER_SETUP_PATH}/AOVs"
RENDER_VARS_PATH = "/Render/Vars"
RENDER_PRODUCTS_PATH = "/Render/Products"
DEFAULT_RENDER_VIEW = "/Render/RenderView"

# Custom attributes
ATTR_AOV_NAME = "drama:aovName"
ATTR_AOV_ALIAS = "drama:aovAlias"
ATTR_AOV_DRIVER = "drama:aovDriver"
ATTR_AOV_FILTER = "drama:aovFilter"
ATTR_AOV_LAYER = "drama:linkedLayer"
ATTR_AOV_ENABLED = "drama:enabled"
ATTR_AOV_RENDER_VAR_PATH = "drama:renderVarPath"

# Common AOV types
COMMON_AOVS = [
    {"name": "beauty", "type": "color3f", "description": "Final rendered image"},
    {"name": "diffuse", "type": "color3f", "description": "Diffuse lighting"},
    {"name": "specular", "type": "color3f", "description": "Specular lighting"},
    {"name": "reflection", "type": "color3f", "description": "Reflections"},
    {"name": "depth", "type": "float", "description": "Z-depth"},
    {"name": "normal", "type": "normal3f", "description": "Surface normals"},
    {"name": "position", "type": "point3f", "description": "World position"},
    {"name": "motion_vector", "type": "float2", "description": "Motion vectors"},
    {"name": "object_id", "type": "int", "description": "Object ID"},
]

# Omniverse AOV names
OMNIVERSE_AOV_NAMES = [
    "LdrColor", "HdrColor", "Depth", "Normal", "MotionVector",
    "InstanceId", "SemanticId", "Albedo", "DirectDiffuse",
    "DirectSpecular", "IndirectDiffuse", "Reflections", "AmbientOcclusion",
]

# RenderVar data types
RENDER_VAR_DATA_TYPES = {
    "HdrColor": "color4f",
    "LdrColor": "color4f",
    "PtZDepth": "float",
    "PtWorldNormal": "normal3f",
    "PtWorldPosition": "point3f",
    "PtDiffuseFilter": "color4f",
    "PtDirectIllumination": "color4f",
    "PtGlobalIllumination": "color4f",
    "PtReflection": "color4f",
    "PtMotion": "float3",
}


# =============================================================================
# Structure Initialization
# =============================================================================

def ensure_aovs_structure() -> Tuple[bool, str]:
    """Ensure AOVs structure exists."""
    stage = get_stage()
    if not stage:
        return False, "No stage available"
    
    try:
        from .render_layer import ensure_render_setup_structure
        ensure_render_setup_structure()
        
        aovs_prim = stage.GetPrimAtPath(AOVS_PATH)
        if not aovs_prim or not aovs_prim.IsValid():
            stage.DefinePrim(AOVS_PATH, "Scope")
        
        return True, "AOVs structure ready"
    except Exception as e:
        return False, f"Error: {e}"


def ensure_render_structure() -> Tuple[bool, str]:
    """Ensure Omniverse render structure exists."""
    stage = get_stage()
    if not stage:
        return False, "No stage available"
    
    try:
        for path in ["/Render", RENDER_VARS_PATH, RENDER_PRODUCTS_PATH]:
            prim = stage.GetPrimAtPath(path)
            if not prim or not prim.IsValid():
                stage.DefinePrim(path, "Scope")
        
        return True, "Render structure ready"
    except Exception as e:
        return False, f"Error: {e}"


# =============================================================================
# AOV Creation and Deletion
# =============================================================================

def create_aov(
    name: str,
    aov_type: str = "color3f",
    alias: str = "",
    driver: str = "exr",
    linked_layer: str = "",
    create_render_var: bool = True
) -> Tuple[bool, str, Optional[str]]:
    """
    Create AOV.
    
    Creates both:
    1. /RenderSetup/AOVs/{name} - Our management node
    2. /Render/Vars/{name} - UsdRender.Var (actual render variable)
    """
    stage = get_stage()
    if not stage:
        return False, "No stage available", None
    
    ensure_aovs_structure()
    
    clean_name = "".join(c if c.isalnum() or c == "_" else "_" for c in name)
    if not clean_name:
        clean_name = "aov"
    
    aov_path = f"{AOVS_PATH}/{clean_name}"
    
    if stage.GetPrimAtPath(aov_path):
        return False, f"AOV already exists: {clean_name}", None
    
    try:
        aov_prim = stage.DefinePrim(aov_path, "Scope")
        aov_prim.CreateAttribute(ATTR_AOV_NAME, Sdf.ValueTypeNames.String).Set(name)
        aov_prim.CreateAttribute(ATTR_AOV_ALIAS, Sdf.ValueTypeNames.String).Set(alias or name)
        aov_prim.CreateAttribute(ATTR_AOV_DRIVER, Sdf.ValueTypeNames.String).Set(driver)
        aov_prim.CreateAttribute(ATTR_AOV_FILTER, Sdf.ValueTypeNames.String).Set("")
        aov_prim.CreateAttribute(ATTR_AOV_ENABLED, Sdf.ValueTypeNames.Bool).Set(True)
        aov_prim.CreateAttribute("dataType", Sdf.ValueTypeNames.Token).Set(aov_type)
        
        if linked_layer:
            aov_prim.CreateAttribute(ATTR_AOV_LAYER, Sdf.ValueTypeNames.String).Set(linked_layer)
        
        render_var_path = ""
        if create_render_var:
            _, _, render_var_path = _create_render_var(clean_name, name, aov_type)
            if render_var_path:
                aov_prim.CreateAttribute(ATTR_AOV_RENDER_VAR_PATH, Sdf.ValueTypeNames.String).Set(render_var_path)
        
        return True, f"Created AOV: {clean_name}", aov_path
        
    except Exception as e:
        return False, f"Error: {e}", None


def _create_render_var(var_name: str, source_name: str, data_type: str) -> Tuple[bool, str, str]:
    """Create UsdRender.Var."""
    stage = get_stage()
    if not stage:
        return False, "No stage", ""
    
    ensure_render_structure()
    var_path = f"{RENDER_VARS_PATH}/{var_name}"
    
    if stage.GetPrimAtPath(var_path):
        return True, "Already exists", var_path
    
    try:
        try:
            render_var = UsdRender.Var.Define(stage, var_path)
            render_var.CreateSourceNameAttr().Set(source_name)
            render_var.CreateDataTypeAttr().Set(data_type)
        except Exception:
            var_prim = stage.DefinePrim(var_path, "RenderVar")
            var_prim.CreateAttribute("sourceName", Sdf.ValueTypeNames.String).Set(source_name)
            var_prim.CreateAttribute("dataType", Sdf.ValueTypeNames.Token).Set(data_type)
        
        return True, "Created", var_path
    except Exception as e:
        return False, f"Error: {e}", ""


def delete_aov(aov_path: str) -> Tuple[bool, str]:
    """Delete AOV and associated RenderVar."""
    stage = get_stage()
    if not stage:
        return False, "No stage"
    
    aov_prim = stage.GetPrimAtPath(aov_path)
    if not aov_prim or not aov_prim.IsValid():
        return False, "AOV not found"
    
    try:
        render_var_path = get_aov_attribute(aov_path, ATTR_AOV_RENDER_VAR_PATH, "")
        if render_var_path and stage.GetPrimAtPath(render_var_path):
            stage.RemovePrim(render_var_path)
        
        stage.RemovePrim(aov_path)
        return True, "Deleted AOV"
    except Exception as e:
        return False, f"Error: {e}"


def rename_aov(aov_path: str, new_name: str) -> Tuple[bool, str, Optional[str]]:
    """Rename AOV."""
    stage = get_stage()
    if not stage:
        return False, "No stage", None
    
    aov_prim = stage.GetPrimAtPath(aov_path)
    if not aov_prim or not aov_prim.IsValid():
        return False, "AOV not found", None
    
    clean_name = "".join(c if c.isalnum() or c == "_" else "_" for c in new_name)
    if not clean_name:
        return False, "Invalid name", None
    
    new_path = f"{AOVS_PATH}/{clean_name}"
    if stage.GetPrimAtPath(new_path):
        return False, "Name already exists", None
    
    try:
        old_alias = get_aov_attribute(aov_path, ATTR_AOV_ALIAS, "")
        old_driver = get_aov_attribute(aov_path, ATTR_AOV_DRIVER, "exr")
        old_layer = get_aov_attribute(aov_path, ATTR_AOV_LAYER, "")
        data_type = get_aov_attribute(aov_path, "dataType", "color3f")
        
        new_prim = stage.DefinePrim(new_path, "Scope")
        new_prim.CreateAttribute(ATTR_AOV_NAME, Sdf.ValueTypeNames.String).Set(new_name)
        new_prim.CreateAttribute(ATTR_AOV_ALIAS, Sdf.ValueTypeNames.String).Set(old_alias)
        new_prim.CreateAttribute(ATTR_AOV_DRIVER, Sdf.ValueTypeNames.String).Set(old_driver)
        new_prim.CreateAttribute(ATTR_AOV_LAYER, Sdf.ValueTypeNames.String).Set(old_layer)
        new_prim.CreateAttribute("dataType", Sdf.ValueTypeNames.Token).Set(data_type)
        
        stage.RemovePrim(aov_path)
        return True, f"Renamed to {clean_name}", new_path
    except Exception as e:
        return False, f"Error: {e}", None


# =============================================================================
# AOV Attributes
# =============================================================================

def get_aov_attribute(aov_path: str, attr_name: str, default: Any = None) -> Any:
    """Get AOV attribute value."""
    stage = get_stage()
    if not stage:
        return default
    
    prim = stage.GetPrimAtPath(aov_path)
    if not prim or not prim.IsValid():
        return default
    
    attr = prim.GetAttribute(attr_name)
    if attr and attr.HasAuthoredValue():
        return attr.Get()
    return default


def set_aov_attribute(aov_path: str, attr_name: str, value: Any) -> bool:
    """Set AOV attribute value."""
    stage = get_stage()
    if not stage:
        return False
    
    prim = stage.GetPrimAtPath(aov_path)
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


def set_aov_alias(aov_path: str, alias: str) -> Tuple[bool, str]:
    """Set AOV alias."""
    if set_aov_attribute(aov_path, ATTR_AOV_ALIAS, alias):
        return True, f"Set alias: {alias}"
    return False, "Failed"


def set_aov_driver(aov_path: str, driver: str) -> Tuple[bool, str]:
    """Set AOV driver."""
    if set_aov_attribute(aov_path, ATTR_AOV_DRIVER, driver):
        return True, f"Set driver: {driver}"
    return False, "Failed"


def set_aov_filter(aov_path: str, filter_type: str) -> Tuple[bool, str]:
    """Set AOV filter."""
    if set_aov_attribute(aov_path, ATTR_AOV_FILTER, filter_type):
        return True, f"Set filter: {filter_type}"
    return False, "Failed"


def set_aov_enabled(aov_path: str, enabled: bool) -> Tuple[bool, str]:
    """Enable or disable AOV."""
    if set_aov_attribute(aov_path, ATTR_AOV_ENABLED, enabled):
        return True, "AOV " + ("enabled" if enabled else "disabled")
    return False, "Failed"


def get_aov_enabled(aov_path: str) -> bool:
    """Get AOV enabled state."""
    return get_aov_attribute(aov_path, ATTR_AOV_ENABLED, True)


# =============================================================================
# AOV-Layer Linking
# =============================================================================

def link_aov_to_layer(aov_path: str, layer_path: str) -> Tuple[bool, str]:
    """Link AOV to render layer."""
    if set_aov_attribute(aov_path, ATTR_AOV_LAYER, layer_path):
        return True, "Linked AOV to layer"
    return False, "Failed"


def unlink_aov_from_layer(aov_path: str) -> Tuple[bool, str]:
    """Unlink AOV from layer."""
    if set_aov_attribute(aov_path, ATTR_AOV_LAYER, ""):
        return True, "Unlinked AOV"
    return False, "Failed"


def get_aovs_for_layer(layer_path: str) -> List[Dict[str, Any]]:
    """Get all AOVs linked to a layer."""
    all_aovs = get_all_aovs()
    return [aov for aov in all_aovs if aov.get("linked_layer") == layer_path]


# =============================================================================
# AOV Queries
# =============================================================================

def get_all_aovs() -> List[Dict[str, Any]]:
    """Get all AOVs."""
    stage = get_stage()
    if not stage:
        return []
    
    aovs_prim = stage.GetPrimAtPath(AOVS_PATH)
    if not aovs_prim or not aovs_prim.IsValid():
        return []
    
    aovs = []
    for child in aovs_prim.GetChildren():
        aov_info = get_aov_info(child.GetPath().pathString)
        if aov_info:
            aovs.append(aov_info)
    return aovs


def get_aov_info(aov_path: str) -> Optional[Dict[str, Any]]:
    """Get AOV info."""
    stage = get_stage()
    if not stage:
        return None
    
    aov_prim = stage.GetPrimAtPath(aov_path)
    if not aov_prim or not aov_prim.IsValid():
        return None
    
    return {
        "path": aov_path,
        "name": aov_prim.GetName(),
        "display_name": get_aov_attribute(aov_path, ATTR_AOV_NAME, aov_prim.GetName()),
        "alias": get_aov_attribute(aov_path, ATTR_AOV_ALIAS, ""),
        "driver": get_aov_attribute(aov_path, ATTR_AOV_DRIVER, "exr"),
        "filter": get_aov_attribute(aov_path, ATTR_AOV_FILTER, ""),
        "data_type": get_aov_attribute(aov_path, "dataType", "color3f"),
        "linked_layer": get_aov_attribute(aov_path, ATTR_AOV_LAYER, ""),
        "enabled": get_aov_attribute(aov_path, ATTR_AOV_ENABLED, True),
        "render_var_path": get_aov_attribute(aov_path, ATTR_AOV_RENDER_VAR_PATH, ""),
    }


def get_available_aov_types() -> List[Dict[str, str]]:
    """Get available AOV types."""
    return COMMON_AOVS.copy()


# =============================================================================
# Batch Operations
# =============================================================================

def create_standard_aovs(layer_path: str = "") -> Tuple[int, str]:
    """Create standard AOV set."""
    standard = ["beauty", "diffuse", "specular", "reflection", "depth", "normal"]
    count = 0
    
    for name in standard:
        aov_info = next((a for a in COMMON_AOVS if a["name"] == name), None)
        aov_type = aov_info["type"] if aov_info else "color3f"
        success, _, _ = create_aov(name=name, aov_type=aov_type, linked_layer=layer_path)
        if success:
            count += 1
    
    return count, f"Created {count} standard AOVs"


# =============================================================================
# RenderProduct Management
# =============================================================================

def create_render_product(
    name: str,
    output_path: str = "",
    layer_path: str = ""
) -> Tuple[bool, str, Optional[str]]:
    """Create render product."""
    stage = get_stage()
    if not stage:
        return False, "No stage", None
    
    ensure_render_structure()
    
    clean_name = "".join(c if c.isalnum() or c == "_" else "_" for c in name)
    product_path = f"{RENDER_PRODUCTS_PATH}/{clean_name}"
    
    if stage.GetPrimAtPath(product_path):
        return False, "Already exists", None
    
    try:
        try:
            render_product = UsdRender.Product.Define(stage, product_path)
            render_product.CreateProductNameAttr().Set(output_path or f"{clean_name}.exr")
        except Exception:
            product_prim = stage.DefinePrim(product_path, "RenderProduct")
            product_prim.CreateAttribute("productName", Sdf.ValueTypeNames.String).Set(output_path or f"{clean_name}.exr")
        
        if layer_path:
            product_prim = stage.GetPrimAtPath(product_path)
            if product_prim:
                product_prim.CreateAttribute(ATTR_AOV_LAYER, Sdf.ValueTypeNames.String).Set(layer_path)
        
        return True, f"Created {clean_name}", product_path
    except Exception as e:
        return False, f"Error: {e}", None


def add_aov_to_product(product_path: str, aov_path: str) -> Tuple[bool, str]:
    """Add AOV to render product."""
    stage = get_stage()
    if not stage:
        return False, "No stage"
    
    product_prim = stage.GetPrimAtPath(product_path)
    if not product_prim or not product_prim.IsValid():
        return False, "Product not found"
    
    render_var_path = get_aov_attribute(aov_path, ATTR_AOV_RENDER_VAR_PATH, "")
    if not render_var_path:
        aov_name = aov_path.split("/")[-1]
        render_var_path = f"{RENDER_VARS_PATH}/{aov_name}"
    
    if not stage.GetPrimAtPath(render_var_path):
        return False, "RenderVar not found"
    
    try:
        ordered_vars = product_prim.GetRelationship("orderedVars")
        if not ordered_vars:
            ordered_vars = product_prim.CreateRelationship("orderedVars")
        ordered_vars.AddTarget(render_var_path)
        return True, "Added AOV to product"
    except Exception as e:
        return False, f"Error: {e}"


def apply_layer_aovs_to_render(layer_path: str) -> Tuple[bool, str]:
    """Apply layer's AOVs to render settings."""
    stage = get_stage()
    if not stage:
        return False, "No stage"
    
    layer_aovs = get_aovs_for_layer(layer_path)
    if not layer_aovs:
        return True, "No AOVs linked"
    
    layer_name = layer_path.split("/")[-1]
    product_path = f"{RENDER_PRODUCTS_PATH}/{layer_name}_output"
    
    if not stage.GetPrimAtPath(product_path):
        success, msg, _ = create_render_product(f"{layer_name}_output", f"{layer_name}.exr", layer_path)
        if not success:
            return False, msg
    
    count = 0
    for aov in layer_aovs:
        if aov.get("enabled", True):
            success, _ = add_aov_to_product(product_path, aov["path"])
            if success:
                count += 1
    
    return True, f"Applied {count} AOVs"


def get_render_products() -> List[Dict[str, Any]]:
    """Get all render products."""
    stage = get_stage()
    if not stage:
        return []
    
    products_prim = stage.GetPrimAtPath(RENDER_PRODUCTS_PATH)
    if not products_prim or not products_prim.IsValid():
        return []
    
    products = []
    for child in products_prim.GetChildren():
        product_path = child.GetPath().pathString
        name_attr = child.GetAttribute("productName")
        
        aov_paths = []
        vars_rel = child.GetRelationship("orderedVars")
        if vars_rel:
            aov_paths = [str(t) for t in vars_rel.GetTargets()]
        
        products.append({
            "path": product_path,
            "name": child.GetName(),
            "output_name": name_attr.Get() if name_attr else child.GetName(),
            "aov_count": len(aov_paths),
            "aov_paths": aov_paths,
            "linked_layer": get_aov_attribute(product_path, ATTR_AOV_LAYER, ""),
        })
    
    return products


def get_available_render_products() -> List[str]:
    """Get available render product paths."""
    stage = get_stage()
    if not stage:
        return []
    
    products = []
    products_prim = stage.GetPrimAtPath(RENDER_PRODUCTS_PATH)
    
    if products_prim and products_prim.IsValid():
        for child in products_prim.GetChildren():
            products.append(child.GetPath().pathString)
    
    return products


# =============================================================================
# RenderView Operations
# =============================================================================

def add_aov_to_render_view(aov_name: str, render_view_path: str = None) -> Tuple[bool, str]:
    """Add AOV to RenderView."""
    stage = get_stage()
    if not stage:
        return False, "No stage"
    
    if render_view_path is None:
        render_view_path = DEFAULT_RENDER_VIEW
    
    try:
        vars_prim = stage.GetPrimAtPath(RENDER_VARS_PATH)
        if not vars_prim or not vars_prim.IsValid():
            stage.DefinePrim(RENDER_VARS_PATH, "Scope")
        
        var_path = f"{RENDER_VARS_PATH}/{aov_name}"
        if not stage.GetPrimAtPath(var_path):
            data_type = RENDER_VAR_DATA_TYPES.get(aov_name, "color4f")
            try:
                render_var = UsdRender.Var.Define(stage, var_path)
                render_var.CreateDataTypeAttr().Set(data_type)
                render_var.CreateSourceNameAttr().Set(aov_name)
            except Exception:
                var_prim = stage.DefinePrim(var_path, "RenderVar")
                var_prim.CreateAttribute("dataType", Sdf.ValueTypeNames.Token).Set(data_type)
                var_prim.CreateAttribute("sourceName", Sdf.ValueTypeNames.String).Set(aov_name)
        
        render_view_prim = stage.GetPrimAtPath(render_view_path)
        if not render_view_prim or not render_view_prim.IsValid():
            return False, f"RenderView not found: {render_view_path}"
        
        ordered_vars_rel = render_view_prim.GetRelationship("orderedVars")
        if not ordered_vars_rel:
            ordered_vars_rel = render_view_prim.CreateRelationship("orderedVars")
        
        existing = ordered_vars_rel.GetTargets()
        if Sdf.Path(var_path) not in existing:
            ordered_vars_rel.AddTarget(var_path)
            return True, f"Added {aov_name} to RenderView"
        return True, f"{aov_name} already in RenderView"
        
    except Exception as e:
        return False, f"Error: {e}"


def remove_aov_from_render_view(aov_name: str, render_view_path: str = None) -> Tuple[bool, str]:
    """Remove AOV from RenderView."""
    stage = get_stage()
    if not stage:
        return False, "No stage"
    
    if render_view_path is None:
        render_view_path = DEFAULT_RENDER_VIEW
    
    try:
        render_view_prim = stage.GetPrimAtPath(render_view_path)
        if not render_view_prim or not render_view_prim.IsValid():
            return False, "RenderView not found"
        
        var_path = f"{RENDER_VARS_PATH}/{aov_name}"
        ordered_vars_rel = render_view_prim.GetRelationship("orderedVars")
        if ordered_vars_rel:
            ordered_vars_rel.RemoveTarget(var_path)
            return True, f"Removed {aov_name}"
        return True, "No orderedVars"
    except Exception as e:
        return False, f"Error: {e}"


def get_render_view_aovs(render_view_path: str = None) -> List[str]:
    """Get AOVs in RenderView."""
    stage = get_stage()
    if not stage:
        return []
    
    if render_view_path is None:
        render_view_path = DEFAULT_RENDER_VIEW
    
    try:
        render_view_prim = stage.GetPrimAtPath(render_view_path)
        if not render_view_prim or not render_view_prim.IsValid():
            return []
        
        ordered_vars_rel = render_view_prim.GetRelationship("orderedVars")
        if not ordered_vars_rel:
            return []
        
        return [str(t).split("/")[-1] for t in ordered_vars_rel.GetTargets()]
    except Exception:
        return []


def setup_layer_aovs_for_movie_capture(layer_path: str, render_view_path: str = None) -> Tuple[bool, str]:
    """Setup layer AOVs for Movie Capture."""
    from .render_layer import get_layer_aov_nodes, OMNIVERSE_AOVS
    
    stage = get_stage()
    if not stage:
        return False, "No stage"
    
    if render_view_path is None:
        render_view_path = DEFAULT_RENDER_VIEW
    
    render_view_prim = stage.GetPrimAtPath(render_view_path)
    if not render_view_prim or not render_view_prim.IsValid():
        return False, f"RenderView not found: {render_view_path}"
    
    layer_aovs = get_layer_aov_nodes(layer_path)
    if not layer_aovs:
        return False, "No AOVs in layer"
    
    count = 0
    for aov in layer_aovs:
        if not aov.get("enabled", True):
            continue
        
        source_type = aov.get("source_type", "")
        aov_info = OMNIVERSE_AOVS.get(source_type, {})
        render_var_name = aov_info.get("render_var", "")
        
        if render_var_name:
            success, _ = add_aov_to_render_view(render_var_name, render_view_path)
            if success:
                count += 1
    
    if count > 0:
        return True, f"Added {count} AOVs to RenderView"
    return False, "No AOVs added"


def get_all_available_render_vars() -> List[Dict[str, str]]:
    """Get all available RenderVar types."""
    return [{"name": n, "data_type": t} for n, t in RENDER_VAR_DATA_TYPES.items()]


def get_omniverse_available_aovs() -> List[str]:
    """Get Omniverse supported AOV names."""
    return OMNIVERSE_AOV_NAMES.copy()


def get_omniverse_aov_settings() -> Dict[str, Any]:
    """Get Omniverse AOV settings."""
    return {"available_aovs": OMNIVERSE_AOV_NAMES}


def configure_render_product_for_aovs(product_name: str = "aov_output", aov_names: List[str] = None) -> Tuple[bool, str]:
    """Configure render product for AOVs."""
    if aov_names is None:
        aov_names = ["diffuse", "specular", "normal", "depth"]
    
    stage = get_stage()
    if not stage:
        return False, "No stage"
    
    try:
        ensure_render_structure()
        
        product_path = f"{RENDER_PRODUCTS_PATH}/{product_name}"
        if not stage.GetPrimAtPath(product_path):
            try:
                render_product = UsdRender.Product.Define(stage, product_path)
                render_product.CreateProductNameAttr().Set(f"{product_name}.exr")
            except Exception:
                product_prim = stage.DefinePrim(product_path, "RenderProduct")
                product_prim.CreateAttribute("productName", Sdf.ValueTypeNames.String).Set(f"{product_name}.exr")
        
        var_paths = []
        for aov_name in aov_names:
            var_path = f"{RENDER_VARS_PATH}/{aov_name}"
            if not stage.GetPrimAtPath(var_path):
                aov_info = next((a for a in COMMON_AOVS if a["name"] == aov_name), None)
                data_type = aov_info["type"] if aov_info else "color3f"
                
                try:
                    render_var = UsdRender.Var.Define(stage, var_path)
                    render_var.CreateSourceNameAttr().Set(aov_name)
                    render_var.CreateDataTypeAttr().Set(data_type)
                except Exception:
                    var_prim = stage.DefinePrim(var_path, "RenderVar")
                    var_prim.CreateAttribute("sourceName", Sdf.ValueTypeNames.String).Set(aov_name)
                    var_prim.CreateAttribute("dataType", Sdf.ValueTypeNames.Token).Set(data_type)
            
            var_paths.append(var_path)
        
        product_prim = stage.GetPrimAtPath(product_path)
        if product_prim:
            ordered_vars = product_prim.GetRelationship("orderedVars")
            if not ordered_vars:
                ordered_vars = product_prim.CreateRelationship("orderedVars")
            for var_path in var_paths:
                ordered_vars.AddTarget(var_path)
        
        return True, f"Configured {len(aov_names)} AOVs"
    except Exception as e:
        return False, f"Error: {e}"


# Stub functions for compatibility
def enable_movie_capture_aovs(aov_list=None, output_dir="", file_prefix="render"):
    return True, "Use Movie Capture UI directly"


def get_movie_capture_aov_status():
    return {"info": "Use Movie Capture UI"}


def capture_multiple_aovs(output_dir, aov_names=None, file_prefix="capture"):
    return 0, "Use Movie Capture UI"
