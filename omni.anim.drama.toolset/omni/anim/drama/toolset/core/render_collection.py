# -*- coding: utf-8 -*-
"""
Render Collection Core Logic
============================

Provides Maya Render Setup style Collection management.

Collections define groups of objects that can have overrides applied.
Each Collection can filter by type (shapes, lights, materials) and
supports pattern-based membership.

Key Features:
    - Filter types: shapes, lights, materials, all
    - Pattern-based auto-include (e.g. "*_GEO", "/World/Characters/*")
    - Nested sub-collections
    - Solo/Enable controls per collection
"""

from typing import List, Optional, Tuple, Dict, Any
import re
from pxr import Usd, Sdf, UsdGeom, UsdLux, UsdShade

from .stage_utils import get_stage, safe_log


# =============================================================================
# Constants
# =============================================================================

# Custom attributes
ATTR_COLLECTION_SOLO = "drama:solo"
ATTR_COLLECTION_ENABLED = "drama:enabled"
ATTR_COLLECTION_FILTER = "drama:filter"
ATTR_COLLECTION_ORDER = "drama:order"
ATTR_COLLECTION_EXPRESSION = "drama:includeExpression"

# Filter types
FILTER_SHAPES = "shapes"
FILTER_LIGHTS = "lights"
FILTER_MATERIALS = "materials"
FILTER_ALL = "all"

VALID_FILTERS = [FILTER_SHAPES, FILTER_LIGHTS, FILTER_MATERIALS, FILTER_ALL]


# =============================================================================
# Collection Creation and Deletion
# =============================================================================

def create_collection(
    parent_path: str,
    name: str,
    filter_type: str = FILTER_SHAPES
) -> Tuple[bool, str, Optional[str]]:
    """
    Create a Collection under a parent (Layer or another Collection).
    
    Args:
        parent_path: Parent path (Layer/Collections or Collection path)
        name: Collection name
        filter_type: Filter type for auto-filtering members
        
    Returns:
        Tuple[bool, str, Optional[str]]: (success, message, collection_path)
    """
    stage = get_stage()
    if not stage:
        return False, "No stage available", None
    
    parent_prim = stage.GetPrimAtPath(parent_path)
    if not parent_prim or not parent_prim.IsValid():
        return False, f"Parent not found: {parent_path}", None
    
    # Clean name
    clean_name = "".join(c if c.isalnum() or c == "_" else "_" for c in name)
    if not clean_name:
        clean_name = "collection"
    
    collection_path = f"{parent_path}/{clean_name}"
    
    if stage.GetPrimAtPath(collection_path):
        return False, f"Collection already exists: {clean_name}", None
    
    if filter_type not in VALID_FILTERS:
        filter_type = FILTER_ALL
    
    try:
        collection_prim = stage.DefinePrim(collection_path, "Scope")
        
        # Apply USD CollectionAPI
        collection_api = Usd.CollectionAPI.Apply(collection_prim, "members")
        collection_api.CreateIncludeRootAttr().Set(False)
        collection_api.CreateExpansionRuleAttr().Set("expandPrims")
        
        # Custom attributes
        collection_prim.CreateAttribute(ATTR_COLLECTION_SOLO, Sdf.ValueTypeNames.Bool).Set(False)
        collection_prim.CreateAttribute(ATTR_COLLECTION_ENABLED, Sdf.ValueTypeNames.Bool).Set(True)
        collection_prim.CreateAttribute(ATTR_COLLECTION_FILTER, Sdf.ValueTypeNames.String).Set(filter_type)
        collection_prim.CreateAttribute(ATTR_COLLECTION_ORDER, Sdf.ValueTypeNames.Int).Set(_get_next_order(parent_path))
        collection_prim.CreateAttribute(ATTR_COLLECTION_EXPRESSION, Sdf.ValueTypeNames.String).Set("")
        
        msg = f"Created collection: {clean_name}"
        safe_log(f"[Collection] {msg}")
        return True, msg, collection_path
        
    except Exception as e:
        return False, f"Error creating collection: {e}", None


def delete_collection(collection_path: str) -> Tuple[bool, str]:
    """Delete a Collection."""
    stage = get_stage()
    if not stage:
        return False, "No stage available"
    
    collection_prim = stage.GetPrimAtPath(collection_path)
    if not collection_prim or not collection_prim.IsValid():
        return False, f"Collection not found: {collection_path}"
    
    try:
        name = collection_prim.GetName()
        stage.RemovePrim(collection_path)
        return True, f"Deleted collection: {name}"
    except Exception as e:
        return False, f"Error: {e}"


def rename_collection(collection_path: str, new_name: str) -> Tuple[bool, str, Optional[str]]:
    """Rename a Collection."""
    stage = get_stage()
    if not stage:
        return False, "No stage available", None
    
    collection_prim = stage.GetPrimAtPath(collection_path)
    if not collection_prim or not collection_prim.IsValid():
        return False, "Collection not found", None
    
    clean_name = "".join(c if c.isalnum() or c == "_" else "_" for c in new_name)
    if not clean_name:
        return False, "Invalid name", None
    
    parent_path = str(collection_prim.GetParent().GetPath())
    new_path = f"{parent_path}/{clean_name}"
    
    if stage.GetPrimAtPath(new_path):
        return False, f"Collection already exists: {clean_name}", None
    
    try:
        # Get current data
        members = get_collection_members(collection_path)
        solo = get_collection_attribute(collection_path, ATTR_COLLECTION_SOLO, False)
        enabled = get_collection_attribute(collection_path, ATTR_COLLECTION_ENABLED, True)
        filter_type = get_collection_attribute(collection_path, ATTR_COLLECTION_FILTER, FILTER_SHAPES)
        order = get_collection_attribute(collection_path, ATTR_COLLECTION_ORDER, 0)
        expression = get_collection_attribute(collection_path, ATTR_COLLECTION_EXPRESSION, "")
        
        # Create new
        new_prim = stage.DefinePrim(new_path, "Scope")
        collection_api = Usd.CollectionAPI.Apply(new_prim, "members")
        collection_api.CreateIncludeRootAttr().Set(False)
        collection_api.CreateExpansionRuleAttr().Set("expandPrims")
        
        # Add members
        if members:
            includes_rel = collection_api.GetIncludesRel()
            for m in members:
                includes_rel.AddTarget(m)
        
        # Set attributes
        new_prim.CreateAttribute(ATTR_COLLECTION_SOLO, Sdf.ValueTypeNames.Bool).Set(solo)
        new_prim.CreateAttribute(ATTR_COLLECTION_ENABLED, Sdf.ValueTypeNames.Bool).Set(enabled)
        new_prim.CreateAttribute(ATTR_COLLECTION_FILTER, Sdf.ValueTypeNames.String).Set(filter_type)
        new_prim.CreateAttribute(ATTR_COLLECTION_ORDER, Sdf.ValueTypeNames.Int).Set(order)
        new_prim.CreateAttribute(ATTR_COLLECTION_EXPRESSION, Sdf.ValueTypeNames.String).Set(expression)
        
        # Copy children
        for child in collection_prim.GetChildren():
            _copy_prim_recursive(child, new_path)
        
        # Delete old
        stage.RemovePrim(collection_path)
        
        return True, f"Renamed to: {clean_name}", new_path
        
    except Exception as e:
        return False, f"Error: {e}", None


def _copy_prim_recursive(prim: Usd.Prim, new_parent: str) -> None:
    """Recursively copy prim."""
    stage = prim.GetStage()
    new_path = f"{new_parent}/{prim.GetName()}"
    new_prim = stage.DefinePrim(new_path, "Scope")
    
    # Copy CollectionAPI
    old_col = Usd.CollectionAPI.Get(prim, "members")
    if old_col:
        new_col = Usd.CollectionAPI.Apply(new_prim, "members")
        old_includes = old_col.GetIncludesRel()
        if old_includes:
            new_includes = new_col.GetIncludesRel()
            for target in old_includes.GetTargets():
                new_includes.AddTarget(target)
    
    # Copy custom attributes
    for attr in prim.GetAttributes():
        if attr.HasAuthoredValue() and attr.GetName().startswith("drama:"):
            new_attr = new_prim.CreateAttribute(attr.GetName(), attr.GetTypeName())
            new_attr.Set(attr.Get())
    
    for child in prim.GetChildren():
        _copy_prim_recursive(child, new_path)


# =============================================================================
# Member Management
# =============================================================================

def add_members(collection_path: str, member_paths: List[str]) -> Tuple[bool, str, int]:
    """
    Add members to a Collection.
    
    Members are filtered based on the Collection's filter type.
    
    Args:
        collection_path: Collection path
        member_paths: List of prim paths to add
        
    Returns:
        Tuple[bool, str, int]: (success, message, count_added)
    """
    stage = get_stage()
    if not stage:
        return False, "No stage available", 0
    
    collection_prim = stage.GetPrimAtPath(collection_path)
    if not collection_prim or not collection_prim.IsValid():
        return False, "Collection not found", 0
    
    try:
        collection_api = Usd.CollectionAPI.Get(collection_prim, "members")
        if not collection_api:
            collection_api = Usd.CollectionAPI.Apply(collection_prim, "members")
            collection_api.CreateIncludeRootAttr().Set(False)
        
        includes_rel = collection_api.GetIncludesRel()
        if not includes_rel:
            includes_rel = collection_api.CreateIncludesRel()
        
        existing = set(str(t) for t in includes_rel.GetTargets())
        filter_type = get_collection_attribute(collection_path, ATTR_COLLECTION_FILTER, FILTER_ALL)
        
        added = 0
        for path in member_paths:
            if path in existing:
                continue
            
            member_prim = stage.GetPrimAtPath(path)
            if not member_prim or not member_prim.IsValid():
                continue
            
            if not _matches_filter(member_prim, filter_type):
                continue
            
            includes_rel.AddTarget(path)
            added += 1
        
        if added > 0:
            return True, f"Added {added} member(s)", added
        return True, "No new members added", 0
        
    except Exception as e:
        return False, f"Error: {e}", 0


def remove_members(collection_path: str, member_paths: List[str]) -> Tuple[bool, str, int]:
    """Remove members from a Collection."""
    stage = get_stage()
    if not stage:
        return False, "No stage available", 0
    
    collection_prim = stage.GetPrimAtPath(collection_path)
    if not collection_prim or not collection_prim.IsValid():
        return False, "Collection not found", 0
    
    try:
        collection_api = Usd.CollectionAPI.Get(collection_prim, "members")
        if not collection_api:
            return False, "No members", 0
        
        includes_rel = collection_api.GetIncludesRel()
        if not includes_rel:
            return False, "No members", 0
        
        removed = 0
        for path in member_paths:
            includes_rel.RemoveTarget(path)
            removed += 1
        
        return True, f"Removed {removed} member(s)", removed
        
    except Exception as e:
        return False, f"Error: {e}", 0


def clear_members(collection_path: str) -> Tuple[bool, str]:
    """Clear all members from a Collection."""
    stage = get_stage()
    if not stage:
        return False, "No stage available"
    
    collection_prim = stage.GetPrimAtPath(collection_path)
    if not collection_prim or not collection_prim.IsValid():
        return False, "Collection not found"
    
    try:
        collection_api = Usd.CollectionAPI.Get(collection_prim, "members")
        if collection_api:
            includes_rel = collection_api.GetIncludesRel()
            if includes_rel:
                includes_rel.ClearTargets(True)
        return True, "Cleared all members"
    except Exception as e:
        return False, f"Error: {e}"


def get_collection_members(collection_path: str) -> List[str]:
    """Get all member paths in a Collection."""
    stage = get_stage()
    if not stage:
        return []
    
    collection_prim = stage.GetPrimAtPath(collection_path)
    if not collection_prim or not collection_prim.IsValid():
        return []
    
    try:
        collection_api = Usd.CollectionAPI.Get(collection_prim, "members")
        if not collection_api:
            return []
        
        includes_rel = collection_api.GetIncludesRel()
        if not includes_rel:
            return []
        
        return [str(t) for t in includes_rel.GetTargets()]
    except Exception:
        return []


def get_members_info(collection_path: str) -> List[Dict[str, Any]]:
    """Get detailed info for all members."""
    stage = get_stage()
    if not stage:
        return []
    
    members = get_collection_members(collection_path)
    result = []
    
    for path in members:
        prim = stage.GetPrimAtPath(path)
        if prim and prim.IsValid():
            result.append({
                "path": path,
                "name": prim.GetName(),
                "type": prim.GetTypeName(),
                "valid": True,
            })
        else:
            result.append({
                "path": path,
                "name": path.split("/")[-1],
                "type": "Unknown",
                "valid": False,
            })
    
    return result


# =============================================================================
# Collection Attributes
# =============================================================================

def get_collection_attribute(collection_path: str, attr_name: str, default: Any = None) -> Any:
    """Get collection attribute value."""
    stage = get_stage()
    if not stage:
        return default
    
    prim = stage.GetPrimAtPath(collection_path)
    if not prim or not prim.IsValid():
        return default
    
    attr = prim.GetAttribute(attr_name)
    if attr and attr.HasAuthoredValue():
        return attr.Get()
    return default


def set_collection_attribute(collection_path: str, attr_name: str, value: Any) -> bool:
    """Set collection attribute value."""
    stage = get_stage()
    if not stage:
        return False
    
    prim = stage.GetPrimAtPath(collection_path)
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


def set_collection_solo(collection_path: str, solo: bool) -> Tuple[bool, str]:
    """
    Set Collection Solo mode.
    
    When Solo is ON, only this collection's members are visible in the layer.
    """
    stage = get_stage()
    if not stage:
        return False, "No stage"
    
    collection_prim = stage.GetPrimAtPath(collection_path)
    if not collection_prim:
        return False, "Collection not found"
    
    parent_path = str(collection_prim.GetParent().GetPath())
    
    success = set_collection_attribute(collection_path, ATTR_COLLECTION_SOLO, solo)
    if not success:
        return False, "Failed to set solo"
    
    if solo:
        # Disable siblings
        parent_prim = stage.GetPrimAtPath(parent_path)
        if parent_prim:
            for sibling in parent_prim.GetChildren():
                sib_path = sibling.GetPath().pathString
                if sib_path != collection_path:
                    set_collection_attribute(sib_path, ATTR_COLLECTION_ENABLED, False)
            set_collection_attribute(collection_path, ATTR_COLLECTION_ENABLED, True)
    else:
        # Re-enable siblings
        parent_prim = stage.GetPrimAtPath(parent_path)
        if parent_prim:
            for sibling in parent_prim.GetChildren():
                set_collection_attribute(sibling.GetPath().pathString, ATTR_COLLECTION_ENABLED, True)
    
    return True, f"Solo {'ON' if solo else 'OFF'}"


def set_collection_enabled(collection_path: str, enabled: bool) -> Tuple[bool, str]:
    """Set Collection enabled state."""
    success = set_collection_attribute(collection_path, ATTR_COLLECTION_ENABLED, enabled)
    if success:
        return True, f"Collection {'enabled' if enabled else 'disabled'}"
    return False, "Failed"


def set_collection_filter(collection_path: str, filter_type: str) -> Tuple[bool, str]:
    """Set Collection filter type."""
    if filter_type not in VALID_FILTERS:
        return False, f"Invalid filter. Valid: {VALID_FILTERS}"
    
    success = set_collection_attribute(collection_path, ATTR_COLLECTION_FILTER, filter_type)
    if success:
        return True, f"Filter set to: {filter_type}"
    return False, "Failed"


# =============================================================================
# Collection Query
# =============================================================================

def get_collection_info(collection_path: str) -> Optional[Dict[str, Any]]:
    """Get Collection info."""
    stage = get_stage()
    if not stage:
        return None
    
    collection_prim = stage.GetPrimAtPath(collection_path)
    if not collection_prim or not collection_prim.IsValid():
        return None
    
    members = get_collection_members(collection_path)
    
    # Get children (sub-collections)
    children = []
    for child in collection_prim.GetChildren():
        child_info = get_collection_info(child.GetPath().pathString)
        if child_info:
            children.append(child_info)
    
    return {
        "path": collection_path,
        "name": collection_prim.GetName(),
        "solo": get_collection_attribute(collection_path, ATTR_COLLECTION_SOLO, False),
        "enabled": get_collection_attribute(collection_path, ATTR_COLLECTION_ENABLED, True),
        "filter": get_collection_attribute(collection_path, ATTR_COLLECTION_FILTER, FILTER_SHAPES),
        "order": get_collection_attribute(collection_path, ATTR_COLLECTION_ORDER, 0),
        "expression": get_collection_attribute(collection_path, ATTR_COLLECTION_EXPRESSION, ""),
        "member_count": len(members),
        "members": members,
        "children": children,
    }


def get_collections_in_layer(layer_path: str) -> List[Dict[str, Any]]:
    """Get all Collections in a Layer."""
    stage = get_stage()
    if not stage:
        return []
    
    # Collections are under layer_path/Collections
    collections_container = f"{layer_path}/Collections"
    container_prim = stage.GetPrimAtPath(collections_container)
    
    if not container_prim or not container_prim.IsValid():
        return []
    
    collections = []
    for child in container_prim.GetChildren():
        col_info = get_collection_info(child.GetPath().pathString)
        if col_info:
            collections.append(col_info)
    
    collections.sort(key=lambda x: x.get("order", 0))
    return collections


# =============================================================================
# Filter Helpers
# =============================================================================

def _matches_filter(prim: Usd.Prim, filter_type: str) -> bool:
    """Check if prim matches filter type."""
    if filter_type == FILTER_ALL:
        return True
    
    if filter_type == FILTER_SHAPES:
        # Meshes, curves, points, etc. but not lights
        return prim.IsA(UsdGeom.Gprim) and not prim.IsA(UsdLux.Light)
    
    elif filter_type == FILTER_LIGHTS:
        return prim.IsA(UsdLux.Light)
    
    elif filter_type == FILTER_MATERIALS:
        type_name = prim.GetTypeName()
        return type_name in ["Material", "Shader", "NodeGraph"]
    
    return True


def _get_next_order(parent_path: str) -> int:
    """Get next order number for collections under parent."""
    stage = get_stage()
    if not stage:
        return 0
    
    parent_prim = stage.GetPrimAtPath(parent_path)
    if not parent_prim:
        return 0
    
    max_order = -1
    for child in parent_prim.GetChildren():
        order = get_collection_attribute(child.GetPath().pathString, ATTR_COLLECTION_ORDER, 0)
        if order > max_order:
            max_order = order
    
    return max_order + 1


# =============================================================================
# Include Expression
# =============================================================================

def set_include_expression(collection_path: str, expression: str) -> Tuple[bool, str]:
    """
    Set include expression for auto-matching members.
    
    Syntax:
        - "*" : match all
        - "Mesh*" : names starting with "Mesh"
        - "*_GEO" : names ending with "_GEO"
        - "/World/Props/*" : all under /World/Props
    """
    stage = get_stage()
    if not stage:
        return False, "No stage"
    
    prim = stage.GetPrimAtPath(collection_path)
    if not prim or not prim.IsValid():
        return False, "Collection not found"
    
    try:
        expr_attr = prim.GetAttribute(ATTR_COLLECTION_EXPRESSION)
        if not expr_attr:
            expr_attr = prim.CreateAttribute(ATTR_COLLECTION_EXPRESSION, Sdf.ValueTypeNames.String)
        expr_attr.Set(expression)
        
        # Apply expression
        if expression:
            matched = evaluate_expression(expression)
            if matched:
                success, msg, count = add_members(collection_path, matched)
                return True, f"Expression set. Added {count} matches."
        
        return True, f"Expression set: {expression}"
        
    except Exception as e:
        return False, f"Error: {e}"


def get_include_expression(collection_path: str) -> str:
    """Get Collection's include expression."""
    return get_collection_attribute(collection_path, ATTR_COLLECTION_EXPRESSION, "")


def evaluate_expression(expression: str) -> List[str]:
    """
    Evaluate expression and return matching prim paths.
    """
    stage = get_stage()
    if not stage:
        return []
    
    matched = []
    
    # Convert wildcard to regex
    if expression.startswith("/"):
        # Path pattern
        pattern = expression.replace("*", ".*").replace("?", ".")
        regex = re.compile(f"^{pattern}$")
        
        for prim in stage.Traverse():
            if regex.match(prim.GetPath().pathString):
                matched.append(prim.GetPath().pathString)
    else:
        # Name pattern
        pattern = expression.replace("*", ".*").replace("?", ".")
        regex = re.compile(f"^{pattern}$")
        
        for prim in stage.Traverse():
            if regex.match(prim.GetName()):
                matched.append(prim.GetPath().pathString)
    
    return matched


def refresh_expression_members(collection_path: str) -> Tuple[bool, str, int]:
    """Refresh Collection members based on expression."""
    expression = get_include_expression(collection_path)
    if not expression:
        return False, "No expression set", 0
    
    matched = evaluate_expression(expression)
    if not matched:
        return True, "No matches", 0
    
    existing = set(get_collection_members(collection_path))
    new_members = [p for p in matched if p not in existing]
    
    if new_members:
        success, msg, count = add_members(collection_path, new_members)
        return success, f"Added {count} new members", count
    
    return True, "No new members", 0


def get_expression_preview(expression: str) -> List[Dict[str, str]]:
    """Preview which prims an expression would match."""
    stage = get_stage()
    if not stage:
        return []
    
    matched = evaluate_expression(expression)
    result = []
    
    for path in matched[:100]:  # Limit preview
        prim = stage.GetPrimAtPath(path)
        if prim and prim.IsValid():
            result.append({
                "path": path,
                "name": prim.GetName(),
                "type": prim.GetTypeName(),
            })
    
    return result
