# -*- coding: utf-8 -*-
"""
Render Setup Core Module
========================

Provides Maya-like Render Setup functionality for Omniverse.
Manages render layers, collections, and attribute overrides.

Features:
    - Render Layers: Manage multiple render configurations
    - Collections: Filter and group scene objects
    - Overrides: Apply attribute modifications per layer
"""

from typing import List, Dict, Optional, Any, Callable, Set
from dataclasses import dataclass, field
from enum import Enum
import fnmatch
import uuid
import json

try:
    import omni.usd
    from pxr import Usd, UsdGeom, Sdf
    HAS_USD = True
except ImportError:
    HAS_USD = False


# =============================================================================
# Enums
# =============================================================================

class FilterType(Enum):
    """Collection filter types."""
    TRANSFORMS = "Transforms"
    MESHES = "Meshes"
    LIGHTS = "Lights"
    CAMERAS = "Cameras"
    MATERIALS = "Materials"
    ALL = "All"


class OverrideType(Enum):
    """Override types."""
    ABSOLUTE = "Absolute"
    RELATIVE = "Relative"


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class Override:
    """
    Represents an attribute override.
    
    Attributes:
        id: Unique identifier
        name: Display name (usually the attribute name)
        attribute_path: Full attribute path (e.g., "primvars:visibility")
        override_type: Absolute or Relative
        value: The override value
        enabled: Whether this override is active
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = ""
    attribute_path: str = ""
    override_type: OverrideType = OverrideType.ABSOLUTE
    value: Any = None
    enabled: bool = True
    
    def to_dict(self) -> Dict:
        """Serialize to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "attribute_path": self.attribute_path,
            "override_type": self.override_type.value,
            "value": self.value,
            "enabled": self.enabled
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "Override":
        """Deserialize from dictionary."""
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            name=data.get("name", ""),
            attribute_path=data.get("attribute_path", ""),
            override_type=OverrideType(data.get("override_type", "Absolute")),
            value=data.get("value"),
            enabled=data.get("enabled", True)
        )


@dataclass
class Collection:
    """
    Represents a collection of scene objects.
    
    Attributes:
        id: Unique identifier
        name: Display name
        filter_type: Type of objects to include
        expression: Wildcard expression for auto-including objects
        include_paths: Manually included prim paths
        exclude_paths: Explicitly excluded prim paths
        enabled: Whether this collection is active
        overrides: List of attribute overrides
        sub_collections: Nested collections
        expanded: UI state for tree expansion
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = "collection"
    filter_type: FilterType = FilterType.TRANSFORMS
    expression: str = ""
    include_paths: List[str] = field(default_factory=list)
    exclude_paths: List[str] = field(default_factory=list)
    enabled: bool = True
    overrides: List[Override] = field(default_factory=list)
    sub_collections: List["Collection"] = field(default_factory=list)
    expanded: bool = True
    
    def get_matched_paths(self, all_paths: List[str]) -> Set[str]:
        """
        Get all paths that match this collection's criteria.
        
        Args:
            all_paths: List of all available prim paths
            
        Returns:
            Set of matched prim paths
        """
        matched = set()
        
        # Add manually included paths
        matched.update(self.include_paths)
        
        # Add expression-matched paths
        if self.expression:
            patterns = [p.strip() for p in self.expression.split(";") if p.strip()]
            for path in all_paths:
                prim_name = path.split("/")[-1] if "/" in path else path
                for pattern in patterns:
                    if fnmatch.fnmatch(prim_name, pattern) or fnmatch.fnmatch(path, pattern):
                        matched.add(path)
                        break
        
        # Remove excluded paths
        matched -= set(self.exclude_paths)
        
        return matched
    
    def add_override(self, override: Override) -> None:
        """Add an override to this collection."""
        self.overrides.append(override)
    
    def remove_override(self, override_id: str) -> bool:
        """Remove an override by ID."""
        for i, ovr in enumerate(self.overrides):
            if ovr.id == override_id:
                self.overrides.pop(i)
                return True
        return False
    
    def add_sub_collection(self, collection: "Collection") -> None:
        """Add a sub-collection."""
        self.sub_collections.append(collection)
    
    def remove_sub_collection(self, collection_id: str) -> bool:
        """Remove a sub-collection by ID."""
        for i, col in enumerate(self.sub_collections):
            if col.id == collection_id:
                self.sub_collections.pop(i)
                return True
        return False
    
    def to_dict(self) -> Dict:
        """Serialize to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "filter_type": self.filter_type.value,
            "expression": self.expression,
            "include_paths": self.include_paths,
            "exclude_paths": self.exclude_paths,
            "enabled": self.enabled,
            "overrides": [o.to_dict() for o in self.overrides],
            "sub_collections": [c.to_dict() for c in self.sub_collections],
            "expanded": self.expanded
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "Collection":
        """Deserialize from dictionary."""
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            name=data.get("name", "collection"),
            filter_type=FilterType(data.get("filter_type", "Transforms")),
            expression=data.get("expression", ""),
            include_paths=data.get("include_paths", []),
            exclude_paths=data.get("exclude_paths", []),
            enabled=data.get("enabled", True),
            overrides=[Override.from_dict(o) for o in data.get("overrides", [])],
            sub_collections=[cls.from_dict(c) for c in data.get("sub_collections", [])],
            expanded=data.get("expanded", True)
        )


@dataclass
class RenderLayer:
    """
    Represents a render layer.
    
    Attributes:
        id: Unique identifier
        name: Display name
        color: Layer color for visual distinction (ARGB hex)
        visible: Whether layer is visible in viewport
        renderable: Whether layer is included in batch renders
        enabled: Whether layer is active
        collections: List of collections in this layer
        expanded: UI state for tree expansion
        isolate_mode: If True, hide all objects not in any collection when layer is active
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = "Layer"
    color: int = 0xFF3A8EBA  # Default blue
    visible: bool = False
    renderable: bool = True
    enabled: bool = True
    collections: List[Collection] = field(default_factory=list)
    expanded: bool = True
    isolate_mode: bool = True  # Default to True for Maya-like behavior
    
    def add_collection(self, collection: Collection) -> None:
        """Add a collection to this layer."""
        self.collections.append(collection)
    
    def remove_collection(self, collection_id: str) -> bool:
        """Remove a collection by ID."""
        for i, col in enumerate(self.collections):
            if col.id == collection_id:
                self.collections.pop(i)
                return True
        return False
    
    def find_collection(self, collection_id: str) -> Optional[Collection]:
        """Find a collection by ID (including sub-collections)."""
        for col in self.collections:
            if col.id == collection_id:
                return col
            # Search in sub-collections recursively
            found = self._find_in_subcollections(col, collection_id)
            if found:
                return found
        return None
    
    def _find_in_subcollections(self, parent: Collection, collection_id: str) -> Optional[Collection]:
        """Recursively find collection in sub-collections."""
        for sub in parent.sub_collections:
            if sub.id == collection_id:
                return sub
            found = self._find_in_subcollections(sub, collection_id)
            if found:
                return found
        return None
    
    def to_dict(self) -> Dict:
        """Serialize to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "color": self.color,
            "visible": self.visible,
            "renderable": self.renderable,
            "enabled": self.enabled,
            "collections": [c.to_dict() for c in self.collections],
            "expanded": self.expanded,
            "isolate_mode": self.isolate_mode
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> "RenderLayer":
        """Deserialize from dictionary."""
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            name=data.get("name", "Layer"),
            color=data.get("color", 0xFF3A8EBA),
            visible=data.get("visible", False),
            renderable=data.get("renderable", True),
            enabled=data.get("enabled", True),
            collections=[Collection.from_dict(c) for c in data.get("collections", [])],
            expanded=data.get("expanded", True),
            isolate_mode=data.get("isolate_mode", True)
        )
    
    def get_all_collection_paths(self) -> Set[str]:
        """Get all paths from all collections in this layer."""
        all_paths = set()
        for col in self.collections:
            all_paths.update(self._get_collection_paths_recursive(col))
        return all_paths
    
    def _get_collection_paths_recursive(self, collection: Collection) -> Set[str]:
        """Recursively get paths from a collection and its sub-collections."""
        paths = set(collection.include_paths)
        for sub in collection.sub_collections:
            paths.update(self._get_collection_paths_recursive(sub))
        return paths


# =============================================================================
# Render Setup Manager
# =============================================================================

class RenderSetupManager:
    """
    Manages the render setup state and operations.
    
    This class handles:
        - Layer management (create, delete, reorder)
        - Collection management
        - Override application
        - Scene querying for available prims
        - Import/Export of render setups
    """
    
    # Available layer colors
    LAYER_COLORS = [
        0xFF3A8EBA,  # Blue
        0xFF8E3ABA,  # Purple
        0xFFBA3A8E,  # Pink
        0xFFBA8E3A,  # Orange
        0xFF3ABA8E,  # Teal
        0xFF8EBA3A,  # Lime
        0xFFBA3A3A,  # Red
        0xFF3A3ABA,  # Indigo
    ]
    
    def __init__(self):
        """Initialize the render setup manager."""
        self._layers: List[RenderLayer] = []
        self._active_layer_id: Optional[str] = None
        self._selected_item_id: Optional[str] = None
        self._selected_item_type: Optional[str] = None  # "layer", "collection", "override"
        self._change_callbacks: List[Callable[[], None]] = []
        self._color_index = 0
        
        # Store original attribute values for restoration
        self._original_values: Dict[str, Dict[str, Any]] = {}
    
    # =========================================================================
    # Callback Management
    # =========================================================================
    
    def add_change_callback(self, callback: Callable[[], None]) -> None:
        """Add a callback for when data changes."""
        if callback not in self._change_callbacks:
            self._change_callbacks.append(callback)
    
    def remove_change_callback(self, callback: Callable[[], None]) -> None:
        """Remove a change callback."""
        if callback in self._change_callbacks:
            self._change_callbacks.remove(callback)
    
    def _notify_change(self) -> None:
        """Notify all listeners of a change."""
        for callback in self._change_callbacks:
            try:
                callback()
            except Exception as e:
                print(f"[RenderSetupManager] Callback error: {e}")
    
    # =========================================================================
    # Layer Management
    # =========================================================================
    
    @property
    def layers(self) -> List[RenderLayer]:
        """Get all layers."""
        return self._layers
    
    @property
    def active_layer(self) -> Optional[RenderLayer]:
        """Get the currently active (visible) layer."""
        if self._active_layer_id:
            return self.find_layer(self._active_layer_id)
        return None
    
    def create_layer(self, name: Optional[str] = None) -> RenderLayer:
        """
        Create a new render layer.
        
        Args:
            name: Optional layer name
            
        Returns:
            The newly created layer
        """
        layer_num = len(self._layers) + 1
        layer_name = name or f"Layer{layer_num}"
        
        # Get next color
        color = self.LAYER_COLORS[self._color_index % len(self.LAYER_COLORS)]
        self._color_index += 1
        
        layer = RenderLayer(name=layer_name, color=color)
        self._layers.append(layer)
        self._notify_change()
        return layer
    
    def delete_layer(self, layer_id: str) -> bool:
        """
        Delete a layer.
        
        Args:
            layer_id: ID of layer to delete
            
        Returns:
            True if deleted successfully
        """
        for i, layer in enumerate(self._layers):
            if layer.id == layer_id:
                # If this was the active layer, deactivate it first
                if self._active_layer_id == layer_id:
                    self.set_active_layer(None)
                self._layers.pop(i)
                self._notify_change()
                return True
        return False
    
    def find_layer(self, layer_id: str) -> Optional[RenderLayer]:
        """Find a layer by ID."""
        for layer in self._layers:
            if layer.id == layer_id:
                return layer
        return None
    
    def set_active_layer(self, layer_id: Optional[str]) -> None:
        """
        Set the active (visible) layer.
        
        Args:
            layer_id: ID of layer to activate, or None to deactivate all
        """
        # Deactivate previous layer
        if self._active_layer_id:
            prev_layer = self.find_layer(self._active_layer_id)
            if prev_layer:
                prev_layer.visible = False
                self._restore_overrides(prev_layer)
        
        # Activate new layer
        self._active_layer_id = layer_id
        if layer_id:
            new_layer = self.find_layer(layer_id)
            if new_layer:
                new_layer.visible = True
                self._apply_overrides(new_layer)
        
        self._notify_change()
    
    def set_layer_renderable(self, layer_id: str, renderable: bool) -> None:
        """Set whether a layer is renderable."""
        layer = self.find_layer(layer_id)
        if layer:
            layer.renderable = renderable
            self._notify_change()
    
    def set_layer_color(self, layer_id: str, color: int) -> None:
        """Set layer color."""
        layer = self.find_layer(layer_id)
        if layer:
            layer.color = color
            self._notify_change()
    
    def rename_layer(self, layer_id: str, new_name: str) -> None:
        """Rename a layer."""
        layer = self.find_layer(layer_id)
        if layer:
            layer.name = new_name
            self._notify_change()
    
    def set_layer_isolate_mode(self, layer_id: str, isolate: bool) -> None:
        """
        Set layer isolate mode.
        
        When isolate mode is on, only objects in collections are visible.
        """
        layer = self.find_layer(layer_id)
        if layer:
            layer.isolate_mode = isolate
            # Re-apply if this is the active layer
            if self._active_layer_id == layer_id:
                self._restore_overrides(layer)
                self._apply_overrides(layer)
            self._notify_change()
    
    # =========================================================================
    # Collection Management
    # =========================================================================
    
    def create_collection(self, layer_id: str, name: Optional[str] = None, 
                         parent_collection_id: Optional[str] = None) -> Optional[Collection]:
        """
        Create a new collection in a layer.
        
        Args:
            layer_id: ID of the parent layer
            name: Optional collection name
            parent_collection_id: Optional parent collection for nesting
            
        Returns:
            The newly created collection, or None if layer not found
        """
        layer = self.find_layer(layer_id)
        if not layer:
            return None
        
        col_num = len(layer.collections) + 1
        col_name = name or f"collection{col_num}"
        collection = Collection(name=col_name)
        
        if parent_collection_id:
            parent = layer.find_collection(parent_collection_id)
            if parent:
                parent.add_sub_collection(collection)
            else:
                layer.add_collection(collection)
        else:
            layer.add_collection(collection)
        
        self._notify_change()
        return collection
    
    def delete_collection(self, layer_id: str, collection_id: str) -> bool:
        """Delete a collection from a layer."""
        layer = self.find_layer(layer_id)
        if not layer:
            return False
        
        # Try to remove from top-level collections
        if layer.remove_collection(collection_id):
            self._notify_change()
            return True
        
        # Try to remove from sub-collections
        for col in layer.collections:
            if self._remove_from_subcollections(col, collection_id):
                self._notify_change()
                return True
        
        return False
    
    def _remove_from_subcollections(self, parent: Collection, collection_id: str) -> bool:
        """Recursively remove collection from sub-collections."""
        if parent.remove_sub_collection(collection_id):
            return True
        for sub in parent.sub_collections:
            if self._remove_from_subcollections(sub, collection_id):
                return True
        return False
    
    def update_collection(self, collection_id: str, **kwargs) -> bool:
        """
        Update collection properties.
        
        Args:
            collection_id: ID of the collection
            **kwargs: Properties to update (name, filter_type, expression, enabled, etc.)
            
        Returns:
            True if updated successfully
        """
        collection = self._find_collection_in_all_layers(collection_id)
        if not collection:
            return False
        
        for key, value in kwargs.items():
            if hasattr(collection, key):
                setattr(collection, key, value)
        
        self._notify_change()
        return True
    
    def add_paths_to_collection(self, collection_id: str, paths: List[str]) -> bool:
        """Add prim paths to a collection."""
        collection = self._find_collection_in_all_layers(collection_id)
        if not collection:
            return False
        
        for path in paths:
            if path not in collection.include_paths:
                collection.include_paths.append(path)
        
        self._notify_change()
        return True
    
    def remove_path_from_collection(self, collection_id: str, path: str) -> bool:
        """Remove a prim path from a collection."""
        collection = self._find_collection_in_all_layers(collection_id)
        if not collection:
            return False
        
        if path in collection.include_paths:
            collection.include_paths.remove(path)
            self._notify_change()
            return True
        return False
    
    def _find_collection_in_all_layers(self, collection_id: str) -> Optional[Collection]:
        """Find a collection across all layers."""
        for layer in self._layers:
            col = layer.find_collection(collection_id)
            if col:
                return col
        return None
    
    # =========================================================================
    # Override Management
    # =========================================================================
    
    def create_override(self, collection_id: str, attribute_path: str, 
                       value: Any, override_type: OverrideType = OverrideType.ABSOLUTE,
                       name: Optional[str] = None) -> Optional[Override]:
        """
        Create a new override in a collection.
        
        Args:
            collection_id: ID of the parent collection
            attribute_path: The attribute to override
            value: The override value
            override_type: Absolute or Relative
            name: Optional display name
            
        Returns:
            The newly created override, or None if collection not found
        """
        collection = self._find_collection_in_all_layers(collection_id)
        if not collection:
            return None
        
        override_name = name or attribute_path.split(":")[-1] if ":" in attribute_path else attribute_path
        override = Override(
            name=override_name,
            attribute_path=attribute_path,
            override_type=override_type,
            value=value
        )
        collection.add_override(override)
        
        # Apply immediately if in active layer
        if self._is_collection_in_active_layer(collection_id):
            self._apply_single_override(collection, override)
        
        self._notify_change()
        return override
    
    def delete_override(self, collection_id: str, override_id: str) -> bool:
        """Delete an override from a collection."""
        collection = self._find_collection_in_all_layers(collection_id)
        if not collection:
            return False
        
        # Find and restore before deleting
        for ovr in collection.overrides:
            if ovr.id == override_id:
                if self._is_collection_in_active_layer(collection_id):
                    self._restore_single_override(collection, ovr)
                break
        
        if collection.remove_override(override_id):
            self._notify_change()
            return True
        return False
    
    def update_override(self, override_id: str, **kwargs) -> bool:
        """Update override properties."""
        for layer in self._layers:
            for col in layer.collections:
                override = self._find_override_in_collection(col, override_id)
                if override:
                    for key, value in kwargs.items():
                        if hasattr(override, key):
                            setattr(override, key, value)
                    self._notify_change()
                    return True
        return False
    
    def _find_override_in_collection(self, collection: Collection, override_id: str) -> Optional[Override]:
        """Find an override in a collection tree."""
        for ovr in collection.overrides:
            if ovr.id == override_id:
                return ovr
        for sub in collection.sub_collections:
            found = self._find_override_in_collection(sub, override_id)
            if found:
                return found
        return None
    
    def _is_collection_in_active_layer(self, collection_id: str) -> bool:
        """Check if a collection belongs to the active layer."""
        if not self._active_layer_id:
            return False
        layer = self.find_layer(self._active_layer_id)
        if layer:
            return layer.find_collection(collection_id) is not None
        return False
    
    # =========================================================================
    # Selection Management
    # =========================================================================
    
    def select_item(self, item_id: str, item_type: str) -> None:
        """
        Select an item in the tree.
        
        Args:
            item_id: ID of the item
            item_type: "layer", "collection", or "override"
        """
        self._selected_item_id = item_id
        self._selected_item_type = item_type
        self._notify_change()
    
    def clear_selection(self) -> None:
        """Clear the current selection."""
        self._selected_item_id = None
        self._selected_item_type = None
        self._notify_change()
    
    @property
    def selected_item(self) -> tuple:
        """Get the currently selected item (id, type)."""
        return (self._selected_item_id, self._selected_item_type)
    
    def get_selected_collection(self) -> Optional[Collection]:
        """Get the currently selected collection."""
        if self._selected_item_type == "collection" and self._selected_item_id:
            return self._find_collection_in_all_layers(self._selected_item_id)
        return None
    
    def get_selected_layer(self) -> Optional[RenderLayer]:
        """Get the currently selected layer."""
        if self._selected_item_type == "layer" and self._selected_item_id:
            return self.find_layer(self._selected_item_id)
        return None
    
    # =========================================================================
    # Scene Query
    # =========================================================================
    
    def get_scene_prims(self, filter_type: FilterType = FilterType.ALL) -> List[Dict[str, str]]:
        """
        Get available prims from the scene.
        
        Args:
            filter_type: Type of prims to return
            
        Returns:
            List of dicts with 'path' and 'name' keys
        """
        if not HAS_USD:
            return []
        
        try:
            ctx = omni.usd.get_context()
            stage = ctx.get_stage()
            if not stage:
                return []
            
            prims = []
            for prim in stage.Traverse():
                if self._matches_filter(prim, filter_type):
                    prims.append({
                        "path": str(prim.GetPath()),
                        "name": prim.GetName()
                    })
            return prims
        except Exception as e:
            print(f"[RenderSetupManager] Error getting scene prims: {e}")
            return []
    
    def _matches_filter(self, prim: "Usd.Prim", filter_type: FilterType) -> bool:
        """Check if a prim matches the filter type."""
        if filter_type == FilterType.ALL:
            return True
        elif filter_type == FilterType.TRANSFORMS:
            return prim.IsA(UsdGeom.Xformable)
        elif filter_type == FilterType.MESHES:
            return prim.IsA(UsdGeom.Mesh)
        elif filter_type == FilterType.LIGHTS:
            return prim.HasAPI(UsdGeom.LightAPI) if hasattr(UsdGeom, 'LightAPI') else False
        elif filter_type == FilterType.CAMERAS:
            return prim.IsA(UsdGeom.Camera)
        elif filter_type == FilterType.MATERIALS:
            return prim.IsA(Usd.Typed) and "Material" in prim.GetTypeName()
        return False
    
    def get_selected_prims(self) -> List[str]:
        """Get currently selected prim paths from the viewport."""
        if not HAS_USD:
            return []
        
        try:
            ctx = omni.usd.get_context()
            selection = ctx.get_selection()
            paths = selection.get_selected_prim_paths()
            return list(paths) if paths else []
        except Exception as e:
            print(f"[RenderSetupManager] Error getting selection: {e}")
            return []
    
    def select_prims_in_viewport(self, paths: List[str]) -> None:
        """Select prims in the viewport."""
        if not HAS_USD:
            return
        
        try:
            ctx = omni.usd.get_context()
            selection = ctx.get_selection()
            selection.set_selected_prim_paths(paths, True)
        except Exception as e:
            print(f"[RenderSetupManager] Error setting selection: {e}")
    
    # =========================================================================
    # Override Application
    # =========================================================================
    
    def _apply_overrides(self, layer: RenderLayer) -> None:
        """Apply all overrides for a layer."""
        if not HAS_USD or not layer.enabled:
            return
        
        # If isolate mode is on, hide all objects not in any collection
        if layer.isolate_mode:
            self._apply_isolate_mode(layer)
        
        # Apply collection overrides
        for collection in layer.collections:
            self._apply_collection_overrides(collection)
    
    def _apply_isolate_mode(self, layer: RenderLayer) -> None:
        """Hide all objects not in any collection of this layer."""
        if not HAS_USD:
            return
        
        try:
            ctx = omni.usd.get_context()
            stage = ctx.get_stage()
            if not stage:
                return
            
            # Get all paths from all collections in this layer
            collection_paths = set()
            for collection in layer.collections:
                if collection.enabled:
                    all_prims = self.get_scene_prims(collection.filter_type)
                    all_paths = [p["path"] for p in all_prims]
                    matched = collection.get_matched_paths(all_paths)
                    collection_paths.update(matched)
                    print(f"[RenderSetup] Collection '{collection.name}' matched paths: {matched}")
            
            # If no paths in collections, hide everything except root
            if not collection_paths:
                print(f"[RenderSetup] No paths in collections, hiding all prims")
            
            # Add parent paths to keep hierarchy visible
            paths_with_parents = set(collection_paths)
            for path in collection_paths:
                parts = path.split("/")
                for i in range(1, len(parts)):
                    parent_path = "/".join(parts[:i+1])
                    if parent_path:
                        paths_with_parents.add(parent_path)
            
            print(f"[RenderSetup] Paths to show (including parents): {paths_with_parents}")
            
            # Get all imageable prims and hide those not in collections
            hidden_count = 0
            shown_count = 0
            
            for prim in stage.Traverse():
                prim_path = str(prim.GetPath())
                
                # Skip root and system prims
                if prim_path == "/" or prim_path.startswith("/OmniverseKit"):
                    continue
                
                # Check if prim is imageable
                if not prim.IsA(UsdGeom.Imageable):
                    continue
                
                imageable = UsdGeom.Imageable(prim)
                if not imageable:
                    continue
                
                # Store original visibility
                if prim_path not in self._original_values:
                    self._original_values[prim_path] = {}
                
                if "visibility" not in self._original_values[prim_path]:
                    orig_vis = imageable.GetVisibilityAttr().Get()
                    self._original_values[prim_path]["visibility"] = orig_vis
                
                # Check if this prim should be visible
                is_in_collection = prim_path in paths_with_parents
                
                # Also check if any children are in collection (don't hide parents of collection members)
                if not is_in_collection:
                    for col_path in paths_with_parents:
                        if col_path.startswith(prim_path + "/"):
                            is_in_collection = True
                            break
                
                # Set visibility
                if not is_in_collection:
                    imageable.GetVisibilityAttr().Set(UsdGeom.Tokens.invisible)
                    hidden_count += 1
                else:
                    # Make sure collection members are visible
                    imageable.GetVisibilityAttr().Set(UsdGeom.Tokens.inherited)
                    shown_count += 1
            
            print(f"[RenderSetup] Isolate mode applied: {shown_count} shown, {hidden_count} hidden")
                    
        except Exception as e:
            print(f"[RenderSetupManager] Error applying isolate mode: {e}")
            import traceback
            traceback.print_exc()
    
    def _apply_collection_overrides(self, collection: Collection) -> None:
        """Apply overrides for a collection and its sub-collections."""
        if not collection.enabled:
            return
        
        # Get all matching paths
        all_prims = self.get_scene_prims(collection.filter_type)
        all_paths = [p["path"] for p in all_prims]
        matched_paths = collection.get_matched_paths(all_paths)
        
        # Apply overrides to matched prims
        for override in collection.overrides:
            if override.enabled:
                self._apply_override_to_prims(override, matched_paths)
        
        # Process sub-collections
        for sub in collection.sub_collections:
            self._apply_collection_overrides(sub)
    
    def _apply_override_to_prims(self, override: Override, prim_paths: Set[str]) -> None:
        """Apply an override to a set of prims."""
        if not HAS_USD:
            return
        
        try:
            ctx = omni.usd.get_context()
            stage = ctx.get_stage()
            if not stage:
                return
            
            for path in prim_paths:
                prim = stage.GetPrimAtPath(path)
                if not prim:
                    continue
                
                # Store original value
                if path not in self._original_values:
                    self._original_values[path] = {}
                
                # Handle common visibility attribute
                if override.attribute_path in ["visibility", "primvars:visibility"]:
                    imageable = UsdGeom.Imageable(prim)
                    if imageable:
                        # Store original
                        orig_vis = imageable.GetVisibilityAttr().Get()
                        self._original_values[path][override.attribute_path] = orig_vis
                        
                        # Apply override
                        if override.override_type == OverrideType.ABSOLUTE:
                            new_value = UsdGeom.Tokens.invisible if not override.value else UsdGeom.Tokens.inherited
                            imageable.GetVisibilityAttr().Set(new_value)
                else:
                    # Generic attribute handling
                    attr = prim.GetAttribute(override.attribute_path)
                    if attr:
                        self._original_values[path][override.attribute_path] = attr.Get()
                        if override.override_type == OverrideType.ABSOLUTE:
                            attr.Set(override.value)
                        elif override.override_type == OverrideType.RELATIVE:
                            original = attr.Get()
                            if isinstance(original, (int, float)):
                                attr.Set(original + override.value)
        except Exception as e:
            print(f"[RenderSetupManager] Error applying override: {e}")
    
    def _apply_single_override(self, collection: Collection, override: Override) -> None:
        """Apply a single override."""
        if not override.enabled or not collection.enabled:
            return
        
        all_prims = self.get_scene_prims(collection.filter_type)
        all_paths = [p["path"] for p in all_prims]
        matched_paths = collection.get_matched_paths(all_paths)
        self._apply_override_to_prims(override, matched_paths)
    
    def _restore_overrides(self, layer: RenderLayer) -> None:
        """Restore all overrides for a layer."""
        if not HAS_USD:
            return
        
        try:
            ctx = omni.usd.get_context()
            stage = ctx.get_stage()
            if not stage:
                return
            
            for path, attrs in self._original_values.items():
                prim = stage.GetPrimAtPath(path)
                if not prim:
                    continue
                
                for attr_path, value in attrs.items():
                    if attr_path in ["visibility", "primvars:visibility"]:
                        imageable = UsdGeom.Imageable(prim)
                        if imageable and value is not None:
                            imageable.GetVisibilityAttr().Set(value)
                    else:
                        attr = prim.GetAttribute(attr_path)
                        if attr and value is not None:
                            attr.Set(value)
            
            # Clear stored values
            self._original_values.clear()
        except Exception as e:
            print(f"[RenderSetupManager] Error restoring overrides: {e}")
    
    def _restore_single_override(self, collection: Collection, override: Override) -> None:
        """Restore a single override."""
        if not HAS_USD:
            return
        
        all_prims = self.get_scene_prims(collection.filter_type)
        all_paths = [p["path"] for p in all_prims]
        matched_paths = collection.get_matched_paths(all_paths)
        
        try:
            ctx = omni.usd.get_context()
            stage = ctx.get_stage()
            if not stage:
                return
            
            for path in matched_paths:
                if path in self._original_values and override.attribute_path in self._original_values[path]:
                    value = self._original_values[path][override.attribute_path]
                    prim = stage.GetPrimAtPath(path)
                    if prim:
                        if override.attribute_path in ["visibility", "primvars:visibility"]:
                            imageable = UsdGeom.Imageable(prim)
                            if imageable and value is not None:
                                imageable.GetVisibilityAttr().Set(value)
                        else:
                            attr = prim.GetAttribute(override.attribute_path)
                            if attr and value is not None:
                                attr.Set(value)
        except Exception as e:
            print(f"[RenderSetupManager] Error restoring single override: {e}")
    
    # =========================================================================
    # Import/Export
    # =========================================================================
    
    def export_to_dict(self) -> Dict:
        """Export the entire render setup to a dictionary."""
        return {
            "version": "1.0",
            "layers": [layer.to_dict() for layer in self._layers],
            "active_layer_id": self._active_layer_id
        }
    
    def export_to_json(self, filepath: str) -> bool:
        """Export the render setup to a JSON file."""
        try:
            with open(filepath, 'w') as f:
                json.dump(self.export_to_dict(), f, indent=2)
            return True
        except Exception as e:
            print(f"[RenderSetupManager] Export error: {e}")
            return False
    
    def import_from_dict(self, data: Dict) -> bool:
        """Import render setup from a dictionary."""
        try:
            # Deactivate current layer first
            if self._active_layer_id:
                self.set_active_layer(None)
            
            # Clear existing layers
            self._layers.clear()
            
            # Import layers
            for layer_data in data.get("layers", []):
                self._layers.append(RenderLayer.from_dict(layer_data))
            
            # Restore active layer
            active_id = data.get("active_layer_id")
            if active_id and self.find_layer(active_id):
                self.set_active_layer(active_id)
            
            self._notify_change()
            return True
        except Exception as e:
            print(f"[RenderSetupManager] Import error: {e}")
            return False
    
    def import_from_json(self, filepath: str) -> bool:
        """Import render setup from a JSON file."""
        try:
            with open(filepath, 'r') as f:
                data = json.load(f)
            return self.import_from_dict(data)
        except Exception as e:
            print(f"[RenderSetupManager] Import error: {e}")
            return False
    
    # =========================================================================
    # Utility
    # =========================================================================
    
    def clear_all(self) -> None:
        """Clear all layers and reset state."""
        if self._active_layer_id:
            self.set_active_layer(None)
        self._layers.clear()
        self._color_index = 0
        self._selected_item_id = None
        self._selected_item_type = None
        self._original_values.clear()
        self._notify_change()
    
    def get_prim_attributes(self, prim_path: str) -> List[Dict[str, Any]]:
        """
        Get available attributes for a prim.
        
        Returns list of dicts with 'name', 'path', 'value', 'type' keys.
        """
        if not HAS_USD:
            return []
        
        try:
            ctx = omni.usd.get_context()
            stage = ctx.get_stage()
            if not stage:
                return []
            
            prim = stage.GetPrimAtPath(prim_path)
            if not prim:
                return []
            
            attributes = []
            for attr in prim.GetAttributes():
                attr_info = {
                    "name": attr.GetName(),
                    "path": str(attr.GetPath()),
                    "value": attr.Get(),
                    "type": str(attr.GetTypeName())
                }
                attributes.append(attr_info)
            
            return attributes
        except Exception as e:
            print(f"[RenderSetupManager] Error getting attributes: {e}")
            return []


# =============================================================================
# Singleton Instance
# =============================================================================

_render_setup_manager: Optional[RenderSetupManager] = None


def get_render_setup_manager() -> RenderSetupManager:
    """Get the singleton RenderSetupManager instance."""
    global _render_setup_manager
    if _render_setup_manager is None:
        _render_setup_manager = RenderSetupManager()
    return _render_setup_manager


def reset_render_setup_manager() -> None:
    """Reset the singleton instance."""
    global _render_setup_manager
    if _render_setup_manager:
        _render_setup_manager.clear_all()
    _render_setup_manager = None
