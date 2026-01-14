# -*- coding: utf-8 -*-
"""
Render Setup ViewModel
======================

ViewModel for the Render Setup feature.
Manages the interaction between the UI and the RenderSetupManager.
"""

from typing import List, Dict, Optional, Any, Callable
from .base_viewmodel import BaseViewModel
from ..core.render_setup import (
    RenderSetupManager,
    get_render_setup_manager,
    RenderLayer,
    Collection,
    Override,
    FilterType,
    OverrideType
)


class RenderSetupViewModel(BaseViewModel):
    """
    ViewModel for Render Setup functionality.
    
    Bridges the UI with the RenderSetupManager, providing:
        - Layer operations
        - Collection operations
        - Override operations
        - Selection management
        - Data change notifications
    """
    
    def __init__(self):
        """Initialize the ViewModel."""
        super().__init__()
        
        self._manager: RenderSetupManager = get_render_setup_manager()
        self._data_changed_callbacks: List[Callable[[], None]] = []
        
        # Subscribe to manager changes
        self._manager.add_change_callback(self._on_manager_change)
    
    # =========================================================================
    # Data Change Notifications
    # =========================================================================
    
    def add_data_changed_callback(self, callback: Callable[[], None]) -> None:
        """Add a callback for data changes."""
        if callback not in self._data_changed_callbacks:
            self._data_changed_callbacks.append(callback)
    
    def remove_data_changed_callback(self, callback: Callable[[], None]) -> None:
        """Remove a data change callback."""
        if callback in self._data_changed_callbacks:
            self._data_changed_callbacks.remove(callback)
    
    def _on_manager_change(self) -> None:
        """Handle manager data change."""
        for callback in self._data_changed_callbacks:
            try:
                callback()
            except Exception as e:
                self.log(f"Data change callback error: {e}")
    
    def _notify_data_changed(self) -> None:
        """Manually trigger data changed notification."""
        self._on_manager_change()
    
    # =========================================================================
    # Layer Operations
    # =========================================================================
    
    @property
    def layers(self) -> List[RenderLayer]:
        """Get all render layers."""
        return self._manager.layers
    
    @property
    def active_layer(self) -> Optional[RenderLayer]:
        """Get the active layer."""
        return self._manager.active_layer
    
    def create_layer(self, name: Optional[str] = None) -> Optional[RenderLayer]:
        """
        Create a new render layer.
        
        Args:
            name: Optional layer name
            
        Returns:
            The created layer
        """
        layer = self._manager.create_layer(name)
        self.log(f"Created layer: {layer.name}")
        return layer
    
    def delete_layer(self, layer_id: str) -> bool:
        """
        Delete a layer.
        
        Args:
            layer_id: ID of the layer to delete
            
        Returns:
            True if successful
        """
        layer = self._manager.find_layer(layer_id)
        if layer:
            name = layer.name
            if self._manager.delete_layer(layer_id):
                self.log(f"Deleted layer: {name}")
                return True
        return False
    
    def set_layer_visible(self, layer_id: str, visible: bool) -> None:
        """
        Set layer visibility (make it the active layer or deactivate).
        
        Args:
            layer_id: ID of the layer
            visible: Whether to make visible
        """
        if visible:
            self._manager.set_active_layer(layer_id)
            self.log(f"Activated layer")
        else:
            current = self._manager.active_layer
            if current and current.id == layer_id:
                self._manager.set_active_layer(None)
                self.log(f"Deactivated layer")
    
    def set_layer_renderable(self, layer_id: str, renderable: bool) -> None:
        """Set whether a layer is renderable."""
        self._manager.set_layer_renderable(layer_id, renderable)
    
    def rename_layer(self, layer_id: str, new_name: str) -> None:
        """Rename a layer."""
        self._manager.rename_layer(layer_id, new_name)
        self.log(f"Renamed layer to: {new_name}")
    
    def set_layer_color(self, layer_id: str, color: int) -> None:
        """Set layer color."""
        self._manager.set_layer_color(layer_id, color)
    
    def set_layer_isolate_mode(self, layer_id: str, isolate: bool) -> None:
        """Set layer isolate mode."""
        self._manager.set_layer_isolate_mode(layer_id, isolate)
        self.log(f"Isolate mode: {'On' if isolate else 'Off'}")
    
    def toggle_layer_expanded(self, layer_id: str) -> None:
        """Toggle layer expansion state."""
        layer = self._manager.find_layer(layer_id)
        if layer:
            layer.expanded = not layer.expanded
            self._notify_data_changed()
    
    # =========================================================================
    # Collection Operations
    # =========================================================================
    
    def create_collection(self, layer_id: str, name: Optional[str] = None,
                         parent_collection_id: Optional[str] = None) -> Optional[Collection]:
        """
        Create a new collection.
        
        Args:
            layer_id: ID of the parent layer
            name: Optional collection name
            parent_collection_id: Optional parent collection ID for nesting
            
        Returns:
            The created collection
        """
        collection = self._manager.create_collection(layer_id, name, parent_collection_id)
        if collection:
            self.log(f"Created collection: {collection.name}")
        return collection
    
    def delete_collection(self, layer_id: str, collection_id: str) -> bool:
        """Delete a collection."""
        if self._manager.delete_collection(layer_id, collection_id):
            self.log("Deleted collection")
            return True
        return False
    
    def rename_collection(self, collection_id: str, new_name: str) -> None:
        """Rename a collection."""
        self._manager.update_collection(collection_id, name=new_name)
        self.log(f"Renamed collection to: {new_name}")
    
    def set_collection_enabled(self, collection_id: str, enabled: bool) -> None:
        """Enable or disable a collection."""
        self._manager.update_collection(collection_id, enabled=enabled)
    
    def set_collection_filter(self, collection_id: str, filter_type: FilterType) -> None:
        """Set collection filter type."""
        self._manager.update_collection(collection_id, filter_type=filter_type)
    
    def set_collection_expression(self, collection_id: str, expression: str) -> None:
        """Set collection expression."""
        self._manager.update_collection(collection_id, expression=expression)
    
    def toggle_collection_expanded(self, collection_id: str) -> None:
        """Toggle collection expansion state."""
        collection = self._manager._find_collection_in_all_layers(collection_id)
        if collection:
            collection.expanded = not collection.expanded
            self._notify_data_changed()
    
    def add_selected_to_collection(self, collection_id: str) -> int:
        """
        Add currently selected prims to a collection.
        
        Returns:
            Number of items added
        """
        paths = self._manager.get_selected_prims()
        if paths:
            self._manager.add_paths_to_collection(collection_id, paths)
            self.log(f"Added {len(paths)} item(s) to collection")
            return len(paths)
        else:
            self.log("No items selected")
            return 0
    
    def remove_path_from_collection(self, collection_id: str, path: str) -> bool:
        """Remove a path from a collection."""
        return self._manager.remove_path_from_collection(collection_id, path)
    
    def get_collection_members(self, collection_id: str) -> List[Dict[str, str]]:
        """
        Get all members of a collection.
        
        Returns:
            List of dicts with 'path' and 'name' keys
        """
        collection = self._manager._find_collection_in_all_layers(collection_id)
        if not collection:
            return []
        
        # Get all matching prims
        all_prims = self._manager.get_scene_prims(collection.filter_type)
        all_paths = [p["path"] for p in all_prims]
        matched_paths = collection.get_matched_paths(all_paths)
        
        # Build result with names
        result = []
        path_to_name = {p["path"]: p["name"] for p in all_prims}
        for path in matched_paths:
            result.append({
                "path": path,
                "name": path_to_name.get(path, path.split("/")[-1])
            })
        
        return result
    
    def select_collection_members(self, collection_id: str) -> None:
        """Select all members of a collection in the viewport."""
        members = self.get_collection_members(collection_id)
        paths = [m["path"] for m in members]
        if paths:
            self._manager.select_prims_in_viewport(paths)
            self.log(f"Selected {len(paths)} item(s)")
        else:
            self.log("No items in collection")
    
    # =========================================================================
    # Override Operations
    # =========================================================================
    
    def create_override(self, collection_id: str, attribute_path: str,
                       value: Any, override_type: OverrideType = OverrideType.ABSOLUTE,
                       name: Optional[str] = None) -> Optional[Override]:
        """
        Create a new override.
        
        Args:
            collection_id: ID of the parent collection
            attribute_path: The attribute to override
            value: The override value
            override_type: Absolute or Relative
            name: Optional display name
            
        Returns:
            The created override
        """
        override = self._manager.create_override(
            collection_id, attribute_path, value, override_type, name
        )
        if override:
            self.log(f"Created override: {override.name}")
        return override
    
    def delete_override(self, collection_id: str, override_id: str) -> bool:
        """Delete an override."""
        if self._manager.delete_override(collection_id, override_id):
            self.log("Deleted override")
            return True
        return False
    
    def set_override_enabled(self, override_id: str, enabled: bool) -> None:
        """Enable or disable an override."""
        self._manager.update_override(override_id, enabled=enabled)
    
    def set_override_value(self, override_id: str, value: Any) -> None:
        """Update override value."""
        self._manager.update_override(override_id, value=value)
    
    # =========================================================================
    # Selection
    # =========================================================================
    
    def select_item(self, item_id: str, item_type: str) -> None:
        """
        Select an item in the tree.
        
        Args:
            item_id: ID of the item
            item_type: "layer", "collection", or "override"
        """
        self._manager.select_item(item_id, item_type)
    
    def clear_selection(self) -> None:
        """Clear the current selection."""
        self._manager.clear_selection()
    
    @property
    def selected_item(self) -> tuple:
        """Get the selected item (id, type)."""
        return self._manager.selected_item
    
    @property
    def selected_collection(self) -> Optional[Collection]:
        """Get the selected collection."""
        return self._manager.get_selected_collection()
    
    @property
    def selected_layer(self) -> Optional[RenderLayer]:
        """Get the selected layer."""
        return self._manager.get_selected_layer()
    
    # =========================================================================
    # Scene Query
    # =========================================================================
    
    def get_filter_types(self) -> List[str]:
        """Get available filter types."""
        return [ft.value for ft in FilterType]
    
    def get_override_types(self) -> List[str]:
        """Get available override types."""
        return [ot.value for ot in OverrideType]
    
    def get_common_attributes(self) -> List[Dict[str, Any]]:
        """
        Get commonly overridden attributes.
        
        Returns:
            List of attribute info dicts
        """
        return self.get_visibility_attributes() + self.get_rendering_attributes()
    
    def get_visibility_attributes(self) -> List[Dict[str, Any]]:
        """Get visibility-related attributes."""
        return [
            {
                "name": "Visible",
                "path": "visibility",
                "description": "Object visibility (inherited/invisible)",
                "default_value": True,
                "type": "bool"
            },
            {
                "name": "Hidden",
                "path": "visibility",
                "description": "Hide object (set to invisible)",
                "default_value": False,
                "type": "bool"
            },
        ]
    
    def get_rendering_attributes(self) -> List[Dict[str, Any]]:
        """Get rendering-related attributes."""
        return [
            {
                "name": "doubleSided",
                "path": "doubleSided",
                "description": "Double sided rendering",
                "default_value": True,
                "type": "bool"
            },
            {
                "name": "castsShadows",
                "path": "primvars:castsShadows",
                "description": "Object casts shadows",
                "default_value": True,
                "type": "bool"
            },
            {
                "name": "subdivisionScheme",
                "path": "subdivisionScheme",
                "description": "Subdivision scheme (none/catmullClark/loop/bilinear)",
                "default_value": "none",
                "type": "string"
            },
        ]
    
    def get_transform_attributes(self) -> List[Dict[str, Any]]:
        """Get transform-related attributes."""
        return [
            {
                "name": "Scale",
                "path": "xformOp:scale",
                "description": "Object scale",
                "default_value": [1.0, 1.0, 1.0],
                "type": "float3"
            },
            {
                "name": "Translate",
                "path": "xformOp:translate",
                "description": "Object translation",
                "default_value": [0.0, 0.0, 0.0],
                "type": "float3"
            },
        ]
    
    def get_selected_prim_attributes(self) -> List[Dict[str, Any]]:
        """Get attributes from the first selected prim."""
        paths = self._manager.get_selected_prims()
        if not paths:
            return []
        return self._manager.get_prim_attributes(paths[0])
    
    def get_prim_attributes(self, prim_path: str) -> List[Dict[str, Any]]:
        """Get attributes for a specific prim."""
        return self._manager.get_prim_attributes(prim_path)
    
    # =========================================================================
    # Import/Export
    # =========================================================================
    
    def export_setup(self, filepath: str) -> bool:
        """Export render setup to a file."""
        if self._manager.export_to_json(filepath):
            self.log(f"Exported to: {filepath}")
            return True
        self.log("Export failed")
        return False
    
    def import_setup(self, filepath: str) -> bool:
        """Import render setup from a file."""
        if self._manager.import_from_json(filepath):
            self.log(f"Imported from: {filepath}")
            return True
        self.log("Import failed")
        return False
    
    # =========================================================================
    # Utility
    # =========================================================================
    
    def clear_all(self) -> None:
        """Clear all layers and reset."""
        self._manager.clear_all()
        self.log("Cleared all layers")
    
    def get_layer_colors(self) -> List[int]:
        """Get available layer colors."""
        return RenderSetupManager.LAYER_COLORS
    
    # =========================================================================
    # Lifecycle
    # =========================================================================
    
    def dispose(self) -> None:
        """Clean up resources."""
        self._manager.remove_change_callback(self._on_manager_change)
        self._data_changed_callbacks.clear()
        super().dispose()
