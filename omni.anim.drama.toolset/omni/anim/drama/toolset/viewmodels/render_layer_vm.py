# -*- coding: utf-8 -*-
"""
Render Layer ViewModel
======================

Manages UI state and business logic for Render Layer functionality.

Features:
    - Layer create/delete/rename
    - Collection management
    - Visibility/Solo/Renderable control
    - Member management
"""

from typing import Optional, Tuple, List, Dict, Any, Callable

from .base_viewmodel import BaseViewModel
from ..core.stage_utils import get_stage, get_selection_paths
from ..core.render_layer import (
    create_render_layer,
    delete_render_layer,
    rename_render_layer,
    get_all_render_layers,
    get_render_layer_info,
    set_layer_visible,
    set_layer_solo,
    set_layer_renderable,
    clear_all_solo,
    move_layer_up,
    move_layer_down,
    move_layer_to_top,
    move_layer_to_bottom,
    LAYERS_PATH,
    # AOV override functionality
    get_layer_aov_overrides,
    set_layer_aov_overrides,
    set_layer_aov_enabled,
    get_layer_aov_enabled,
    apply_layer_aov_settings,
    get_available_aovs,
    create_aov_override_for_layer,
    clear_layer_aov_overrides,
    OMNIVERSE_AOVS,
    # Maya style AOV sub-node management
    create_layer_aov,
    delete_layer_aov,
    get_layer_aov_nodes,
    get_layer_aov_node_info,
    set_layer_aov_property,
    rename_layer_aov,
    toggle_layer_aov_enabled,
    create_standard_aovs_for_layer as create_standard_aovs_core,
    apply_layer_aovs_to_renderer,
)
from ..core.render_collection import (
    create_collection,
    delete_collection,
    rename_collection,
    add_members,
    remove_members,
    clear_members,
    get_collection_members,
    get_collection_info,
    get_collections_in_layer,
    get_members_info,
    set_collection_solo,
    set_collection_enabled,
    set_collection_filter,
    set_include_expression,
    get_include_expression,
    refresh_expression_members,
    get_expression_preview,
)
from ..core.render_override import (
    set_visibility_override,
    batch_set_visibility,
    set_light_property,
    get_light_properties,
    set_material_binding,
    get_material_binding,
    clear_material_binding,
    apply_override_to_collection,
    get_overridable_properties,
    OVERRIDE_VISIBILITY,
    OVERRIDE_LIGHT_INTENSITY,
    OVERRIDE_MATERIAL,
    # Maya style Override storage
    set_collection_override,
    get_collection_overrides,
    clear_collection_overrides,
)
from ..core.layer_state import (
    get_layer_state_manager,
    switch_to_layer,
    restore_original_states,
    enable_layer_state_management,
    is_layer_state_management_enabled,
    get_layer_state_info,
)
from ..core.render_aov import (
    create_aov,
    delete_aov,
    rename_aov,
    get_all_aovs,
    get_aov_info,
    link_aov_to_layer,
    unlink_aov_from_layer,
    get_aovs_for_layer,
    set_aov_alias,
    set_aov_driver,
    set_aov_filter,
    get_available_aov_types,
    create_standard_aovs,
    create_render_product,
    add_aov_to_product,
    apply_layer_aovs_to_render,
    get_render_products,
    set_aov_enabled,
    configure_render_product_for_aovs,
    get_omniverse_aov_settings,
    get_available_render_products,
    capture_multiple_aovs,
    get_omniverse_available_aovs,
    OMNIVERSE_AOV_NAMES,
    # New: Movie Capture AOV control
    enable_movie_capture_aovs,
    get_movie_capture_aov_status,
    # New: Correct RenderView operations
    add_aov_to_render_view,
    remove_aov_from_render_view,
    get_render_view_aovs,
    setup_layer_aovs_for_movie_capture,
    get_all_available_render_vars,
)
from ..core.aov_merge import (
    scan_aov_files,
    get_scan_summary,
    merge_aovs_external,
    auto_merge_aovs,
    check_openexr_available,
    ensure_openexr_available,
)


class RenderLayerViewModel(BaseViewModel):
    """
    Render Layer ViewModel.
    
    Manages render layer and Collection state,
    and provides create, delete, edit commands.
    """
    
    def __init__(self):
        """Initialize RenderLayerViewModel."""
        super().__init__()
        
        # Currently selected layer and Collection
        self._selected_layer_path: str = ""
        self._selected_collection_path: str = ""
        
        # Data change callbacks
        self._data_changed_callbacks: List[Callable[[], None]] = []
        
        # Layer data cache
        self._layers_cache: List[Dict[str, Any]] = []
        
        # Auto sync AOV to RenderView (Maya style)
        self._auto_sync_aovs: bool = True
        
        # Maya style Layer switch (restore original state and apply Override on switch)
        self._maya_style_layer_switch: bool = True
        
    # =========================================================================
    # Properties
    # =========================================================================
    
    @property
    def selected_layer_path(self) -> str:
        """Get currently selected layer path."""
        return self._selected_layer_path
    
    @selected_layer_path.setter
    def selected_layer_path(self, value: str) -> None:
        """Set currently selected layer path."""
        old_path = self._selected_layer_path
        self._selected_layer_path = value
        self._selected_collection_path = ""  # Clear Collection selection when switching layers
        
        if value and value != old_path:
            # Maya style: Apply Layer Override when switching
            if self._maya_style_layer_switch:
                self._apply_maya_style_layer_switch(value)
            
            # If auto sync enabled, auto update RenderView AOV when switching Layer
            if self._auto_sync_aovs:
                self._sync_layer_aovs_to_render_view(value)
        
        self._notify_data_changed()
    
    @property
    def selected_collection_path(self) -> str:
        """Get currently selected Collection path."""
        return self._selected_collection_path
    
    @selected_collection_path.setter
    def selected_collection_path(self, value: str) -> None:
        """Set currently selected Collection path."""
        self._selected_collection_path = value
        self._notify_data_changed()
    
    @property
    def has_selection(self) -> bool:
        """Whether a layer or Collection is selected."""
        return bool(self._selected_layer_path or self._selected_collection_path)
    
    @property
    def auto_sync_aovs(self) -> bool:
        """Whether to auto sync Layer AOV to RenderView."""
        return self._auto_sync_aovs
    
    @auto_sync_aovs.setter
    def auto_sync_aovs(self, value: bool) -> None:
        """Set whether to auto sync AOV."""
        self._auto_sync_aovs = value
        if value:
            self.log("[OK] Auto sync AOV enabled - RenderView will update on Layer switch")
        else:
            self.log("[i] Auto sync AOV disabled")
    
    def _sync_layer_aovs_to_render_view(self, layer_path: str) -> None:
        """
        Internal method: Sync Layer AOV to RenderView.
        
        Called automatically when switching Layer (if auto sync enabled).
        """
        try:
            # Clear old AOV in RenderView, then add new Layer's AOV
            success, msg = setup_layer_aovs_for_movie_capture(layer_path)
            
            if success:
                layer_name = layer_path.split("/")[-1]
                self.log(f"[~] Synced Layer '{layer_name}' AOVs to RenderView")
            # Don't print error on failure (Layer may have no AOV)
        except Exception as e:
            # Silent failure, don't affect user experience
            pass
    
    def _apply_maya_style_layer_switch(self, layer_path: str) -> None:
        """
        Internal method: Maya style Layer switch.
        
        1. Restore all objects to original state
        2. Apply target Layer's Override
        """
        try:
            success, msg = switch_to_layer(layer_path)
            
            if success:
                layer_name = layer_path.split("/")[-1]
                self.log(f"[>] Switched to Layer '{layer_name}' - Override applied")
        except Exception as e:
            # Silent failure
            pass
    
    @property
    def maya_style_layer_switch(self) -> bool:
        """Whether Maya style Layer switch is enabled."""
        return self._maya_style_layer_switch
    
    @maya_style_layer_switch.setter
    def maya_style_layer_switch(self, value: bool) -> None:
        """Set whether Maya style Layer switch is enabled."""
        self._maya_style_layer_switch = value
        enable_layer_state_management(value)
        
        if value:
            self.log("[OK] Maya style Layer switch enabled")
            self.log("   Auto restore original state and apply Override on Layer switch")
        else:
            self.log("[i] Maya style Layer switch disabled")
    
    def restore_all_to_original(self) -> Tuple[int, str]:
        """
        Restore all objects to original state.
        
        Returns:
            Tuple[int, str]: (restore count, message)
        """
        count, msg = restore_original_states()
        self.log(f"[~] {msg}")
        self._notify_data_changed()
        return count, msg
    
    def get_layer_state_status(self) -> Dict[str, Any]:
        """Get Layer state management status info."""
        return get_layer_state_info()
    
    def set_collection_property_override(
        self,
        override_type: str,
        value: Any
    ) -> Tuple[bool, str]:
        """
        Set property override for currently selected Collection.
        
        This override is stored on Collection and auto-applied on Layer switch.
        
        Args:
            override_type: Override type ("visibility", "material", "light_intensity", "light_color")
            value: Override value
        """
        if not self._selected_collection_path:
            self.log("[!] Please select a Collection first")
            return False, "No collection selected"
        
        success, msg = set_collection_override(
            self._selected_collection_path,
            override_type,
            value
        )
        
        if success:
            self.log(f"[OK] Set {override_type} override successfully")
            self._notify_data_changed()
        else:
            self.log(f"[X] {msg}")
        
        return success, msg
    
    def get_collection_property_overrides(self) -> Dict[str, Any]:
        """Get all property overrides for currently selected Collection."""
        if not self._selected_collection_path:
            return {}
        return get_collection_overrides(self._selected_collection_path)
    
    def clear_collection_property_overrides(self) -> Tuple[bool, str]:
        """Clear all property overrides for currently selected Collection."""
        if not self._selected_collection_path:
            return False, "No collection selected"
        
        success, msg = clear_collection_overrides(self._selected_collection_path)
        
        if success:
            self.log("[OK] Cleared all Collection overrides")
            self._notify_data_changed()
        
        return success, msg
    
    # =========================================================================
    # Data Change Notification
    # =========================================================================
    
    def add_data_changed_callback(self, callback: Callable[[], None]) -> None:
        """Add data change listener."""
        if callback not in self._data_changed_callbacks:
            self._data_changed_callbacks.append(callback)
    
    def remove_data_changed_callback(self, callback: Callable[[], None]) -> None:
        """Remove data change listener."""
        if callback in self._data_changed_callbacks:
            self._data_changed_callbacks.remove(callback)
    
    def _notify_data_changed(self) -> None:
        """Notify data has changed."""
        for callback in self._data_changed_callbacks:
            try:
                callback()
            except Exception as e:
                print(f"[RenderLayerVM] Data changed callback error: {e}")
    
    # =========================================================================
    # Layer Operations
    # =========================================================================
    
    def create_layer(self, name: str) -> Tuple[bool, str]:
        """
        Create new render layer.
        
        Args:
            name: Layer name
            
        Returns:
            Tuple[bool, str]: (success, message)
        """
        if not name:
            self.log("[!] Please enter a layer name")
            return False, "Name required"
        
        success, msg, path = create_render_layer(name)
        
        if success:
            self.log(f"[OK] {msg}")
            self._selected_layer_path = path
            self._notify_data_changed()
        else:
            self.log(f"[X] {msg}")
        
        return success, msg
    
    def delete_selected_layer(self) -> Tuple[bool, str]:
        """
        Delete currently selected layer.
        
        Returns:
            Tuple[bool, str]: (success, message)
        """
        if not self._selected_layer_path:
            self.log("[!] Please select a layer first")
            return False, "No layer selected"
        
        success, msg = delete_render_layer(self._selected_layer_path)
        
        if success:
            self.log(f"[OK] {msg}")
            self._selected_layer_path = ""
            self._selected_collection_path = ""
            self._notify_data_changed()
        else:
            self.log(f"[X] {msg}")
        
        return success, msg
    
    def rename_selected_layer(self, new_name: str) -> Tuple[bool, str]:
        """
        Rename currently selected layer.
        
        Args:
            new_name: New name
            
        Returns:
            Tuple[bool, str]: (success, message)
        """
        if not self._selected_layer_path:
            self.log("[!] Please select a layer first")
            return False, "No layer selected"
        
        if not new_name:
            self.log("[!] Please enter a new name")
            return False, "Name required"
        
        success, msg, new_path = rename_render_layer(self._selected_layer_path, new_name)
        
        if success:
            self.log(f"[OK] {msg}")
            self._selected_layer_path = new_path
            self._notify_data_changed()
        else:
            self.log(f"[X] {msg}")
        
        return success, msg
    
    def toggle_layer_visible(self, layer_path: str) -> Tuple[bool, str]:
        """
        Toggle layer visibility.
        
        Args:
            layer_path: Layer path
            
        Returns:
            Tuple[bool, str]: (success, message)
        """
        # Get current state
        layer_info = get_render_layer_info(layer_path)
        if not layer_info:
            return False, "Layer not found"
        
        new_visible = not layer_info["visible"]
        success, msg = set_layer_visible(layer_path, new_visible)
        
        if success:
            self._notify_data_changed()
        
        return success, msg
    
    def toggle_layer_solo(self, layer_path: str) -> Tuple[bool, str]:
        """
        Toggle layer Solo state.
        
        Args:
            layer_path: Layer path
            
        Returns:
            Tuple[bool, str]: (success, message)
        """
        layer_info = get_render_layer_info(layer_path)
        if not layer_info:
            return False, "Layer not found"
        
        new_solo = not layer_info["solo"]
        success, msg = set_layer_solo(layer_path, new_solo)
        
        if success:
            self.log(f"[OK] {msg}")
            self._notify_data_changed()
        
        return success, msg
    
    def toggle_layer_renderable(self, layer_path: str) -> Tuple[bool, str]:
        """
        Toggle layer renderable state.
        
        Args:
            layer_path: Layer path
            
        Returns:
            Tuple[bool, str]: (success, message)
        """
        layer_info = get_render_layer_info(layer_path)
        if not layer_info:
            return False, "Layer not found"
        
        new_renderable = not layer_info["renderable"]
        success, msg = set_layer_renderable(layer_path, new_renderable)
        
        if success:
            self._notify_data_changed()
        
        return success, msg
    
    def clear_all_layer_solo(self) -> Tuple[bool, str]:
        """
        Clear all layers' Solo state.
        
        Returns:
            Tuple[bool, str]: (success, message)
        """
        success, msg = clear_all_solo()
        
        if success:
            self.log(f"[OK] {msg}")
            self._notify_data_changed()
        
        return success, msg
    
    # =========================================================================
    # Collection Operations
    # =========================================================================
    
    def create_collection_in_layer(
        self,
        name: str,
        filter_type: str = "shapes"
    ) -> Tuple[bool, str]:
        """
        Create Collection under currently selected layer.
        
        Args:
            name: Collection name
            filter_type: Filter type
            
        Returns:
            Tuple[bool, str]: (success, message)
        """
        if not self._selected_layer_path:
            self.log("[!] Please select a layer first")
            return False, "No layer selected"
        
        if not name:
            self.log("[!] Please enter a collection name")
            return False, "Name required"
        
        success, msg, path = create_collection(
            self._selected_layer_path, name, filter_type
        )
        
        if success:
            self.log(f"[OK] {msg}")
            self._selected_collection_path = path
            self._notify_data_changed()
        else:
            self.log(f"[X] {msg}")
        
        return success, msg
    
    def create_sub_collection(
        self,
        name: str,
        filter_type: str = "shapes"
    ) -> Tuple[bool, str]:
        """
        Create sub-Collection under currently selected Collection.
        
        Args:
            name: Collection name
            filter_type: Filter type
            
        Returns:
            Tuple[bool, str]: (success, message)
        """
        if not self._selected_collection_path:
            self.log("[!] Please select a collection first")
            return False, "No collection selected"
        
        if not name:
            self.log("[!] Please enter a collection name")
            return False, "Name required"
        
        success, msg, path = create_collection(
            self._selected_collection_path, name, filter_type
        )
        
        if success:
            self.log(f"[OK] {msg}")
            self._selected_collection_path = path
            self._notify_data_changed()
        else:
            self.log(f"[X] {msg}")
        
        return success, msg
    
    def delete_selected_collection(self) -> Tuple[bool, str]:
        """
        Delete currently selected Collection.
        
        Returns:
            Tuple[bool, str]: (success, message)
        """
        if not self._selected_collection_path:
            self.log("[!] Please select a collection first")
            return False, "No collection selected"
        
        success, msg = delete_collection(self._selected_collection_path)
        
        if success:
            self.log(f"[OK] {msg}")
            self._selected_collection_path = ""
            self._notify_data_changed()
        else:
            self.log(f"[X] {msg}")
        
        return success, msg
    
    def rename_selected_collection(self, new_name: str) -> Tuple[bool, str]:
        """
        Rename currently selected Collection.
        
        Args:
            new_name: New name
            
        Returns:
            Tuple[bool, str]: (success, message)
        """
        if not self._selected_collection_path:
            self.log("[!] Please select a collection first")
            return False, "No collection selected"
        
        if not new_name:
            self.log("[!] Please enter a new name")
            return False, "Name required"
        
        success, msg, new_path = rename_collection(
            self._selected_collection_path, new_name
        )
        
        if success:
            self.log(f"[OK] {msg}")
            self._selected_collection_path = new_path
            self._notify_data_changed()
        else:
            self.log(f"[X] {msg}")
        
        return success, msg
    
    def toggle_collection_solo(self, collection_path: str) -> Tuple[bool, str]:
        """
        Toggle Collection Solo state.
        
        Args:
            collection_path: Collection path
            
        Returns:
            Tuple[bool, str]: (success, message)
        """
        col_info = get_collection_info(collection_path)
        if not col_info:
            return False, "Collection not found"
        
        new_solo = not col_info["solo"]
        success, msg = set_collection_solo(collection_path, new_solo)
        
        if success:
            self.log(f"[OK] {msg}")
            self._notify_data_changed()
        
        return success, msg
    
    def toggle_collection_enabled(self, collection_path: str) -> Tuple[bool, str]:
        """
        Toggle Collection enabled state.
        
        Args:
            collection_path: Collection path
            
        Returns:
            Tuple[bool, str]: (success, message)
        """
        col_info = get_collection_info(collection_path)
        if not col_info:
            return False, "Collection not found"
        
        new_enabled = not col_info["enabled"]
        success, msg = set_collection_enabled(collection_path, new_enabled)
        
        if success:
            self._notify_data_changed()
        
        return success, msg
    
    def set_collection_filter_type(
        self,
        collection_path: str,
        filter_type: str
    ) -> Tuple[bool, str]:
        """
        Set Collection filter type.
        
        Args:
            collection_path: Collection path
            filter_type: Filter type
            
        Returns:
            Tuple[bool, str]: (success, message)
        """
        success, msg = set_collection_filter(collection_path, filter_type)
        
        if success:
            self.log(f"[OK] {msg}")
            self._notify_data_changed()
        else:
            self.log(f"[X] {msg}")
        
        return success, msg
    
    # =========================================================================
    # Member Management
    # =========================================================================
    
    def add_selection_to_collection(self) -> Tuple[bool, str]:
        """
        Add current scene selection to selected Collection.
        
        Returns:
            Tuple[bool, str]: (success, message)
        """
        if not self._selected_collection_path:
            self.log("[!] Please select a collection first")
            return False, "No collection selected"
        
        selection = get_selection_paths()
        if not selection:
            self.log("[!] Please select objects in the viewport first")
            return False, "No objects selected"
        
        success, msg, count = add_members(self._selected_collection_path, selection)
        
        if success and count > 0:
            self.log(f"[OK] Added {count} member(s)")
            self._notify_data_changed()
        elif success:
            self.log("[i] No new members added (already in collection or filtered)")
        else:
            self.log(f"[X] {msg}")
        
        return success, msg
    
    def remove_selection_from_collection(self) -> Tuple[bool, str]:
        """
        Remove current scene selection from selected Collection.
        
        Returns:
            Tuple[bool, str]: (success, message)
        """
        if not self._selected_collection_path:
            self.log("[!] Please select a collection first")
            return False, "No collection selected"
        
        selection = get_selection_paths()
        if not selection:
            self.log("[!] Please select objects in the viewport first")
            return False, "No objects selected"
        
        success, msg, count = remove_members(self._selected_collection_path, selection)
        
        if success:
            self.log(f"[OK] Removed {count} member(s)")
            self._notify_data_changed()
        else:
            self.log(f"[X] {msg}")
        
        return success, msg
    
    def clear_collection_members(self) -> Tuple[bool, str]:
        """
        Clear all members from selected Collection.
        
        Returns:
            Tuple[bool, str]: (success, message)
        """
        if not self._selected_collection_path:
            self.log("[!] Please select a collection first")
            return False, "No collection selected"
        
        success, msg = clear_members(self._selected_collection_path)
        
        if success:
            self.log(f"[OK] {msg}")
            self._notify_data_changed()
        else:
            self.log(f"[X] {msg}")
        
        return success, msg
    
    def remove_member_by_path(self, member_path: str) -> Tuple[bool, str]:
        """
        Remove single member by path.
        
        Args:
            member_path: Member path
            
        Returns:
            Tuple[bool, str]: (success, message)
        """
        if not self._selected_collection_path:
            return False, "No collection selected"
        
        success, msg, _ = remove_members(
            self._selected_collection_path, [member_path]
        )
        
        if success:
            self._notify_data_changed()
        
        return success, msg
    
    # =========================================================================
    # Data Retrieval
    # =========================================================================
    
    def get_layers(self) -> List[Dict[str, Any]]:
        """
        Get all render layer data.
        
        Returns:
            List[Dict]: Layer info list
        """
        return get_all_render_layers()
    
    def get_selected_layer_info(self) -> Optional[Dict[str, Any]]:
        """
        Get detailed info of currently selected layer.
        
        Returns:
            Dict or None: Layer info
        """
        if not self._selected_layer_path:
            return None
        return get_render_layer_info(self._selected_layer_path)
    
    def get_selected_collection_info(self) -> Optional[Dict[str, Any]]:
        """
        Get detailed info of currently selected Collection.
        
        Returns:
            Dict or None: Collection info
        """
        if not self._selected_collection_path:
            return None
        return get_collection_info(self._selected_collection_path)
    
    def get_selected_collection_members(self) -> List[Dict[str, Any]]:
        """
        Get member info of currently selected Collection.
        
        Returns:
            List[Dict]: Member info list
        """
        if not self._selected_collection_path:
            return []
        return get_members_info(self._selected_collection_path)
    
    def get_collections_for_selected_layer(self) -> List[Dict[str, Any]]:
        """
        Get all Collections for currently selected layer.
        
        Returns:
            List[Dict]: Collection info list
        """
        if not self._selected_layer_path:
            return []
        return get_collections_in_layer(self._selected_layer_path)
    
    # =========================================================================
    # Layer Sorting
    # =========================================================================
    
    def move_selected_layer_up(self) -> Tuple[bool, str]:
        """Move selected layer up."""
        if not self._selected_layer_path:
            return False, "No layer selected"
        
        success, msg = move_layer_up(self._selected_layer_path)
        if success:
            self._notify_data_changed()
        return success, msg
    
    def move_selected_layer_down(self) -> Tuple[bool, str]:
        """Move selected layer down."""
        if not self._selected_layer_path:
            return False, "No layer selected"
        
        success, msg = move_layer_down(self._selected_layer_path)
        if success:
            self._notify_data_changed()
        return success, msg
    
    def move_selected_layer_to_top(self) -> Tuple[bool, str]:
        """Move selected layer to top."""
        if not self._selected_layer_path:
            return False, "No layer selected"
        
        success, msg = move_layer_to_top(self._selected_layer_path)
        if success:
            self._notify_data_changed()
        return success, msg
    
    def move_selected_layer_to_bottom(self) -> Tuple[bool, str]:
        """Move selected layer to bottom."""
        if not self._selected_layer_path:
            return False, "No layer selected"
        
        success, msg = move_layer_to_bottom(self._selected_layer_path)
        if success:
            self._notify_data_changed()
        return success, msg
    
    # =========================================================================
    # Include Expression
    # =========================================================================
    
    def set_collection_expression(self, expression: str) -> Tuple[bool, str]:
        """
        Set include expression for current Collection.
        
        Args:
            expression: Expression (e.g. "*_GEO", "/World/Characters/*")
        """
        if not self._selected_collection_path:
            return False, "No collection selected"
        
        success, msg = set_include_expression(self._selected_collection_path, expression)
        if success:
            self.log(f"Expression set: {expression}")
            self._notify_data_changed()
        return success, msg
    
    def get_collection_expression(self) -> str:
        """Get include expression for current Collection."""
        if not self._selected_collection_path:
            return ""
        return get_include_expression(self._selected_collection_path)
    
    def refresh_collection_expression(self) -> Tuple[bool, str]:
        """Refresh Collection members based on expression."""
        if not self._selected_collection_path:
            return False, "No collection selected"
        
        success, msg, count = refresh_expression_members(self._selected_collection_path)
        if success:
            self._notify_data_changed()
        return success, msg
    
    def preview_expression(self, expression: str) -> List[Dict[str, str]]:
        """Preview which Prims the expression will match."""
        return get_expression_preview(expression)
    
    # =========================================================================
    # Property Override
    # =========================================================================
    
    def apply_visibility_override(self, visible: bool) -> Tuple[bool, str]:
        """
        Apply visibility override to selected Collection members.
        
        Args:
            visible: Whether visible
        """
        if not self._selected_collection_path:
            return False, "No collection selected"
        
        success_count, fail_count, msg = apply_override_to_collection(
            self._selected_collection_path,
            OVERRIDE_VISIBILITY,
            "",
            visible
        )
        
        self.log(f"Visibility override: {msg}")
        self._notify_data_changed()
        return success_count > 0, msg
    
    def apply_light_override(
        self,
        property_name: str,
        value: Any
    ) -> Tuple[bool, str]:
        """
        Apply property override to light members in selected Collection.
        
        Args:
            property_name: Property name (e.g. "intensity", "color")
            value: Property value
        """
        if not self._selected_collection_path:
            return False, "No collection selected"
        
        success_count, fail_count, msg = apply_override_to_collection(
            self._selected_collection_path,
            "light",
            property_name,
            value
        )
        
        self.log(f"Light override: {msg}")
        self._notify_data_changed()
        return success_count > 0, msg
    
    def apply_material_override(self, material_path: str) -> Tuple[bool, str]:
        """
        Apply material override to selected Collection members.
        
        Args:
            material_path: Material path
        """
        if not self._selected_collection_path:
            return False, "No collection selected"
        
        success_count, fail_count, msg = apply_override_to_collection(
            self._selected_collection_path,
            OVERRIDE_MATERIAL,
            "",
            material_path
        )
        
        self.log(f"Material override: {msg}")
        self._notify_data_changed()
        return success_count > 0, msg
    
    def get_member_properties(self, member_path: str) -> List[Dict[str, Any]]:
        """Get list of overridable properties for member."""
        return get_overridable_properties(member_path)
    
    # =========================================================================
    # AOV Management
    # =========================================================================
    
    def create_aov(
        self,
        name: str,
        aov_type: str = "color3f",
        link_to_layer: bool = True
    ) -> Tuple[bool, str]:
        """
        Create AOV.
        
        Args:
            name: AOV name
            aov_type: Data type
            link_to_layer: Whether to link to currently selected layer
        """
        linked_layer = self._selected_layer_path if link_to_layer else ""
        
        success, msg, path = create_aov(
            name=name,
            aov_type=aov_type,
            linked_layer=linked_layer
        )
        
        if success:
            self.log(f"Created AOV: {name}")
            self._notify_data_changed()
        else:
            self.log(f"Failed to create AOV: {msg}")
        
        return success, msg
    
    def delete_aov(self, aov_path: str) -> Tuple[bool, str]:
        """Delete AOV."""
        success, msg = delete_aov(aov_path)
        if success:
            self._notify_data_changed()
        return success, msg
    
    def rename_aov(self, aov_path: str, new_name: str) -> Tuple[bool, str]:
        """Rename AOV."""
        success, msg, new_path = rename_aov(aov_path, new_name)
        if success:
            self._notify_data_changed()
        return success, msg
    
    def get_all_aovs(self) -> List[Dict[str, Any]]:
        """Get all AOVs."""
        return get_all_aovs()
    
    def get_layer_aovs(self) -> List[Dict[str, Any]]:
        """Get AOVs linked to currently selected layer."""
        if not self._selected_layer_path:
            return []
        return get_aovs_for_layer(self._selected_layer_path)
    
    def link_aov_to_selected_layer(self, aov_path: str) -> Tuple[bool, str]:
        """Link AOV to currently selected layer."""
        if not self._selected_layer_path:
            return False, "No layer selected"
        
        success, msg = link_aov_to_layer(aov_path, self._selected_layer_path)
        if success:
            self._notify_data_changed()
        return success, msg
    
    def unlink_aov(self, aov_path: str) -> Tuple[bool, str]:
        """Unlink AOV from layer."""
        success, msg = unlink_aov_from_layer(aov_path)
        if success:
            self._notify_data_changed()
        return success, msg
    
    def set_aov_properties(
        self,
        aov_path: str,
        alias: str = None,
        driver: str = None,
        filter_type: str = None
    ) -> Tuple[bool, str]:
        """Set AOV properties."""
        results = []
        
        if alias is not None:
            success, msg = set_aov_alias(aov_path, alias)
            results.append(success)
        
        if driver is not None:
            success, msg = set_aov_driver(aov_path, driver)
            results.append(success)
        
        if filter_type is not None:
            success, msg = set_aov_filter(aov_path, filter_type)
            results.append(success)
        
        if results:
            self._notify_data_changed()
        
        return all(results) if results else True, "Properties updated"
    
    def get_available_aov_types(self) -> List[Dict[str, str]]:
        """Get available AOV type list."""
        return get_available_aov_types()
    
    def create_standard_aovs_for_layer(self) -> Tuple[bool, str]:
        """Create standard AOV set for currently selected layer."""
        layer_path = self._selected_layer_path or ""
        count, msg = create_standard_aovs(layer_path)
        
        if count > 0:
            self.log(f"Created {count} standard AOVs")
            self._notify_data_changed()
        
        return count > 0, msg
    
    def apply_aovs_to_render(self) -> Tuple[bool, str]:
        """
        Apply current layer's AOVs to render settings.
        
        Creates RenderProduct and links all AOVs,
        enabling AOV channel output during rendering.
        """
        if not self._selected_layer_path:
            self.log("Please select a layer first")
            return False, "No layer selected"
        
        success, msg = apply_layer_aovs_to_render(self._selected_layer_path)
        
        if success:
            self.log(f"[OK] {msg}")
            self._notify_data_changed()
        else:
            self.log(f"[X] {msg}")
        
        return success, msg
    
    def create_render_product_for_layer(
        self,
        output_path: str = ""
    ) -> Tuple[bool, str]:
        """
        Create render product (output configuration) for selected layer.
        
        Args:
            output_path: Output file path
        """
        if not self._selected_layer_path:
            self.log("Please select a layer first")
            return False, "No layer selected"
        
        layer_name = self._selected_layer_path.split("/")[-1]
        
        success, msg, product_path = create_render_product(
            name=f"{layer_name}_output",
            output_path=output_path or f"{layer_name}.exr",
            layer_path=self._selected_layer_path
        )
        
        if success:
            self.log(f"[OK] Created render product: {product_path}")
            self._notify_data_changed()
        else:
            self.log(f"[X] {msg}")
        
        return success, msg
    
    def add_aov_to_layer_product(self, aov_path: str) -> Tuple[bool, str]:
        """
        Add AOV to current layer's render product.
        
        Args:
            aov_path: AOV path
        """
        if not self._selected_layer_path:
            return False, "No layer selected"
        
        layer_name = self._selected_layer_path.split("/")[-1]
        product_path = f"/Render/Products/{layer_name}_output"
        
        # Ensure product exists
        from ..core.render_aov import RENDER_PRODUCTS_PATH
        from ..core.stage_utils import get_stage
        
        stage = get_stage()
        if stage and not stage.GetPrimAtPath(product_path):
            self.create_render_product_for_layer()
        
        success, msg = add_aov_to_product(product_path, aov_path)
        
        if success:
            self._notify_data_changed()
        
        return success, msg
    
    def get_render_products(self) -> List[Dict[str, Any]]:
        """Get all render products."""
        return get_render_products()
    
    def toggle_aov_enabled(self, aov_path: str) -> Tuple[bool, str]:
        """Toggle AOV enabled state."""
        from ..core.render_aov import get_aov_enabled
        
        current_enabled = get_aov_enabled(aov_path)
        success, msg = set_aov_enabled(aov_path, not current_enabled)
        
        if success:
            self._notify_data_changed()
        
        return success, msg
    
    def configure_native_aovs(self) -> Tuple[bool, str]:
        """
        Configure Omniverse native AOV output.
        
        Creates correct RenderSettings, RenderProduct and RenderVar structure,
        enabling Movie Capture to output multi-channel EXR.
        """
        # Get AOV names to configure
        our_aovs = self.get_all_aovs()
        aov_names = [aov["name"] for aov in our_aovs if aov.get("enabled", True)]
        
        if not aov_names:
            aov_names = ["diffuse", "specular", "normal", "depth", "beauty"]
        
        success, msg = configure_render_product_for_aovs(
            product_name="drama_aov_output",
            aov_names=aov_names
        )
        
        if success:
            self.log(f"[OK] {msg}")
            self.log("[>] In Movie Capture, select '/Render/Products/drama_aov_output' from the Render Product dropdown")
            self._notify_data_changed()
        else:
            self.log(f"[X] {msg}")
        
        return success, msg
    
    def setup_movie_capture_aovs(
        self,
        output_dir: str = ""
    ) -> Tuple[bool, str]:
        """
        One-click setup Movie Capture for multiple AOV output.
        
        This function enables Movie Capture to output multiple AOV files!
        
        Args:
            output_dir: Output directory
        """
        import os
        
        # Get current layer's AOV configuration
        aov_list = []
        
        if self._selected_layer_path:
            # Get enabled AOVs from layer's AOV sub-nodes
            layer_aovs = self.get_layer_aov_list()
            for aov in layer_aovs:
                if aov.get("enabled", True):
                    # Convert to Movie Capture supported AOV names
                    source_type = aov.get("source_type", "")
                    aov_name_map = {
                        "z_depth": "Depth",
                        "32bit_depth": "Depth",
                        "world_normal": "Normal",
                        "diffuse_filter": "Albedo",
                        "direct_illumination": "DirectDiffuse",
                        "global_illumination": "IndirectDiffuse",
                        "reflection": "Reflections",
                        "motion_vectors": "MotionVector",
                        "background": "HdrColor",
                        "pre_denoised": "HdrColor",
                    }
                    mc_name = aov_name_map.get(source_type, "HdrColor")
                    if mc_name not in aov_list:
                        aov_list.append(mc_name)
        
        # Use defaults if not configured
        if not aov_list:
            aov_list = ["HdrColor", "Depth", "Normal", "Albedo"]
        
        # Set default output directory
        if not output_dir:
            output_dir = os.path.expanduser("~/Documents/OmniverseAOV")
            os.makedirs(output_dir, exist_ok=True)
        
        # Call core function
        success, msg = enable_movie_capture_aovs(
            aov_list=aov_list,
            output_dir=output_dir,
            file_prefix="render"
        )
        
        if success:
            self.log(f"[OK] {msg}")
            self.log(f"[>] Output folder: {output_dir}")
            self.log("[>] Now open Movie Capture (Window > Rendering > Movie Capture)")
            self.log("[>] Click Capture button to start rendering")
        else:
            self.log(f"[X] {msg}")
        
        return success, msg
    
    def get_movie_capture_status(self) -> Dict[str, Any]:
        """Get Movie Capture AOV configuration status."""
        return get_movie_capture_aov_status()
    
    def push_layer_aovs_to_render_view(self) -> Tuple[bool, str]:
        """
        Push current Layer's AOVs to RenderView (the correct way!).
        
        This enables Movie Capture to output these AOVs.
        
        How it works:
        1. Read AOVs configured in the Layer
        2. Create corresponding RenderVars under /Render/Vars/
        3. Add RenderVars to /Render/RenderView's orderedVars
        4. After checking "Use render product to capture" in Movie Capture, these AOVs will be output
        """
        if not self._selected_layer_path:
            self.log("[!] Please select a Layer first")
            return False, "No layer selected"
        
        success, msg = setup_layer_aovs_for_movie_capture(self._selected_layer_path)
        
        if success:
            self.log(f"[OK] {msg}")
            self.log("")
            self.log("[>] Next steps:")
            self.log("1. Open Movie Capture (Window > Rendering > Movie Capture)")
            self.log("2. Check 'Use render product to capture'")
            self.log("3. Make sure Render Product is '/Render/RenderView'")
            self.log("4. Click Capture to start rendering")
            self.log("5. The output EXR file will contain all configured AOV channels")
        else:
            self.log(f"[X] {msg}")
        
        return success, msg
    
    def get_current_render_view_aovs(self) -> List[str]:
        """Get list of AOVs configured in current RenderView."""
        return get_render_view_aovs()
    
    def add_single_aov_to_render_view(self, aov_name: str) -> Tuple[bool, str]:
        """
        Manually add single AOV to RenderView.
        
        Args:
            aov_name: AOV name (e.g. "PtZDepth", "PtWorldNormal")
        """
        success, msg = add_aov_to_render_view(aov_name)
        
        if success:
            self.log(f"[OK] {msg}")
            self._notify_data_changed()
        else:
            self.log(f"[X] {msg}")
        
        return success, msg
    
    def get_available_render_var_list(self) -> List[Dict[str, str]]:
        """Get all available RenderVar types."""
        return get_all_available_render_vars()
    
    def get_native_aov_settings(self) -> Dict[str, Any]:
        """Get Omniverse native AOV settings info."""
        return get_omniverse_aov_settings()
    
    def get_available_render_products_list(self) -> List[str]:
        """Get all available RenderProduct paths."""
        return get_available_render_products()
    
    def capture_aovs_to_folder(
        self,
        output_dir: str = "",
        aov_names: List[str] = None
    ) -> Tuple[bool, str]:
        """
        Capture multiple AOVs to specified folder.
        
        This is Omniverse's native AOV output method!
        
        Args:
            output_dir: Output directory, defaults to user documents folder
            aov_names: List of AOV names to capture
        """
        import os
        
        if not output_dir:
            # Default output to user documents directory
            output_dir = os.path.expanduser("~/Documents/OmniverseAOV")
        
        if aov_names is None:
            # Default capture these common AOVs
            aov_names = ["LdrColor", "Depth", "Normal", "Albedo"]
        
        self.log(f"Capturing AOVs to: {output_dir}")
        self.log(f"AOVs: {', '.join(aov_names)}")
        
        count, msg = capture_multiple_aovs(
            output_dir=output_dir,
            aov_names=aov_names,
            file_prefix="render"
        )
        
        if count > 0:
            self.log(f"[~] Capturing {count} AOVs in background...")
            self.log(f"[>] Output folder: {output_dir}")
            self.log(f"[...] Each AOV is captured sequentially. Check the log for completion.")
        else:
            self.log(f"[X] Failed to capture AOVs: {msg}")
        
        return count > 0, msg
    
    def get_omniverse_aov_list(self) -> List[str]:
        """Get list of AOV names supported by Omniverse."""
        return get_omniverse_available_aovs()
    
    # =========================================================================
    # AOV merge (merge multiple single AOV EXRs into one multi-layer EXR)
    # =========================================================================
    
    def scan_aov_folder(self, folder_path: str) -> Tuple[int, List[str], str]:
        """
        Scan AOV files in directory.
        
        Args:
            folder_path: Directory to scan
            
        Returns:
            Tuple[frame_count, aov_list, message]
        """
        frame_count, aov_list, msg = get_scan_summary(folder_path)
        self.log(f"Scan: {msg}")
        return frame_count, aov_list, msg
    
    def merge_aov_files(
        self,
        src_dir: str,
        output_dir: str = "",
        shot_name: str = "render",
        keep_singles: bool = True
    ) -> Tuple[bool, str]:
        """
        Merge AOV EXR files in directory into multi-layer EXR.
        
        Args:
            src_dir: Source directory (containing individual AOV EXR files)
            output_dir: Output directory (defaults to src_dir/merged)
            shot_name: Shot name (for output file naming, e.g. "E001_C020")
            keep_singles: Whether to keep original individual AOV files
            
        Returns:
            Tuple[bool, str]: (success, message)
        """
        import os
        
        if not output_dir:
            output_dir = os.path.join(src_dir, "merged")
        
        self.log(f"[~] Starting AOV merge...")
        self.log(f"   Source: {src_dir}")
        self.log(f"   Output: {output_dir}")
        self.log(f"   Shot: {shot_name}")
        
        def progress_callback(msg: str):
            self.log(f"   {msg}")
        
        success, msg = merge_aovs_external(
            src_dir=src_dir,
            output_dir=output_dir,
            shot_name=shot_name,
            keep_singles=keep_singles,
            progress_callback=progress_callback
        )
        
        if success:
            self.log(f"[OK] {msg}")
        else:
            self.log(f"[X] {msg}")
        
        return success, msg
    
    def auto_merge_captured_aovs(
        self,
        shot_name: str = "render"
    ) -> Tuple[bool, str]:
        """
        Auto merge recently captured AOV files.
        
        Uses default OmniverseAOV directory.
        
        Args:
            shot_name: Shot name
            
        Returns:
            Tuple[bool, str]: (success, message)
        """
        import os
        
        # Default AOV output directory
        src_dir = os.path.expanduser("~/Documents/OmniverseAOV")
        
        if not os.path.isdir(src_dir):
            msg = f"AOV folder not found: {src_dir}"
            self.log(f"[X] {msg}")
            return False, msg
        
        success, msg, output_dir = auto_merge_aovs(
            src_dir=src_dir,
            shot_name=shot_name
        )
        
        if success:
            self.log(f"[OK] Merged AOVs to: {output_dir}")
        else:
            self.log(f"[X] {msg}")
        
        return success, msg
    
    def check_openexr_status(self) -> Tuple[bool, str]:
        """
        Check if OpenEXR library is available.
        
        Returns:
            Tuple[bool, str]: (is_available, message)
        """
        ok, msg = check_openexr_available()
        self.log(f"OpenEXR status: {msg}")
        return ok, msg
    
    def install_openexr(self) -> Tuple[bool, str]:
        """
        Install OpenEXR and Imath libraries.
        
        Returns:
            Tuple[bool, str]: (success, message)
        """
        self.log("[~] Installing OpenEXR/Imath...")
        ok, msg = ensure_openexr_available()
        
        if ok:
            self.log(f"[OK] {msg}")
        else:
            self.log(f"[X] {msg}")
        
        return ok, msg
    
    # =========================================================================
    # AOV override functionality (per-Layer independent AOV configuration)
    # =========================================================================
    
    def get_available_aov_list(self) -> List[Dict[str, Any]]:
        """
        Get all available AOV list.
        
        Returns:
            List[Dict]: AOV info list
        """
        return get_available_aovs()
    
    def get_selected_layer_aov_overrides(self) -> Dict[str, bool]:
        """
        Get AOV override settings for selected layer.
        
        Returns:
            Dict[str, bool]: AOV name to enabled state mapping
        """
        if not self._selected_layer_path:
            return {}
        return get_layer_aov_overrides(self._selected_layer_path)
    
    def set_layer_aov(
        self,
        aov_name: str,
        enabled: bool
    ) -> Tuple[bool, str]:
        """
        Set single AOV enabled state for selected layer.
        
        Args:
            aov_name: AOV name
            enabled: Whether to enable
        """
        if not self._selected_layer_path:
            return False, "No layer selected"
        
        success, msg = set_layer_aov_enabled(
            self._selected_layer_path,
            aov_name,
            enabled
        )
        
        if success:
            state = "enabled" if enabled else "disabled"
            self.log(f"AOV '{aov_name}' {state} for current layer")
            self._notify_data_changed()
        
        return success, msg
    
    def create_aov_override_for_selected_layer(
        self,
        aov_names: List[str] = None
    ) -> Tuple[bool, str]:
        """
        Create AOV override for selected layer.
        
        Similar to Maya's "Create Absolute Override for Active Layer".
        
        Args:
            aov_names: List of AOV names to enable
        """
        if not self._selected_layer_path:
            self.log("[!] Please select a layer first")
            return False, "No layer selected"
        
        success, msg = create_aov_override_for_layer(
            self._selected_layer_path,
            aov_names
        )
        
        if success:
            self.log(f"[OK] {msg}")
            self._notify_data_changed()
        else:
            self.log(f"[X] {msg}")
        
        return success, msg
    
    def clear_selected_layer_aov_overrides(self) -> Tuple[bool, str]:
        """
        Clear all AOV overrides for selected layer.
        """
        if not self._selected_layer_path:
            return False, "No layer selected"
        
        success, msg = clear_layer_aov_overrides(self._selected_layer_path)
        
        if success:
            self.log("Cleared AOV overrides for current layer")
            self._notify_data_changed()
        
        return success, msg
    
    def apply_selected_layer_aov_settings(self) -> Tuple[bool, str]:
        """
        Apply selected layer's AOV settings to renderer.
        
        Call this function when preparing to render this layer.
        """
        if not self._selected_layer_path:
            return False, "No layer selected"
        
        success, msg = apply_layer_aov_settings(self._selected_layer_path)
        
        if success:
            self.log(f"[OK] {msg}")
        else:
            self.log(f"[X] {msg}")
        
        return success, msg
    
    def get_aov_info_for_layer(self, layer_path: str = None) -> List[Dict[str, Any]]:
        """
        Get layer's AOV configuration info (for UI display).
        
        Args:
            layer_path: Layer path, if None uses current selected layer
            
        Returns:
            List[Dict]: Each AOV's info and enabled state
        """
        if layer_path is None:
            layer_path = self._selected_layer_path
        
        if not layer_path:
            return []
        
        # Get all available AOVs
        available_aovs = get_available_aovs()
        
        # Get layer's override settings
        overrides = get_layer_aov_overrides(layer_path)
        
        # Merge info
        result = []
        for aov in available_aovs:
            aov_id = aov["id"]
            result.append({
                "id": aov_id,
                "name": aov["name"],
                "render_var": aov["render_var"],
                "enabled": overrides.get(aov_id, None),  # None means no override set
                "has_override": aov_id in overrides,
            })
        
        return result
    
    # =========================================================================
    # Maya style AOV sub-node management
    # =========================================================================
    
    def add_aov_to_selected_layer(
        self,
        aov_type_id: str,
        name_override: str = "",
        driver: str = "exr",
        filter_type: str = "gaussian"
    ) -> Tuple[bool, str]:
        """
        Add AOV sub-node to selected layer (Maya style).
        
        Similar to Maya's "Create Absolute Override for Active Layer".
        
        Args:
            aov_type_id: AOV type ID (e.g. "z_depth", "world_normal")
            name_override: Custom name (for renaming)
            driver: Output driver type
            filter_type: Filter type
        """
        if not self._selected_layer_path:
            self.log("[!] Please select a layer first")
            return False, "No layer selected"
        
        success, msg, aov_path = create_layer_aov(
            layer_path=self._selected_layer_path,
            aov_type_id=aov_type_id,
            name_override=name_override,
            driver=driver,
            filter_type=filter_type,
            enabled=True
        )
        
        if success:
            layer_name = self._selected_layer_path.split("/")[-1]
            self.log(f"[OK] Added AOV '{aov_type_id}' to layer '{layer_name}'")
            self._notify_data_changed()
        else:
            self.log(f"[X] {msg}")
        
        return success, msg
    
    def remove_aov_from_selected_layer(self, aov_type_id: str) -> Tuple[bool, str]:
        """
        Remove AOV sub-node from selected layer.
        
        Args:
            aov_type_id: AOV type ID
        """
        if not self._selected_layer_path:
            return False, "No layer selected"
        
        success, msg = delete_layer_aov(self._selected_layer_path, aov_type_id)
        
        if success:
            self.log(f"[OK] Removed AOV '{aov_type_id}' from layer")
            self._notify_data_changed()
        else:
            self.log(f"[X] {msg}")
        
        return success, msg
    
    def get_layer_aov_list(self, layer_path: str = None) -> List[Dict[str, Any]]:
        """
        Get layer's AOV sub-node list (Maya style).
        
        Args:
            layer_path: Layer path, defaults to current selected layer
            
        Returns:
            List[Dict]: AOV sub-node info list
        """
        if layer_path is None:
            layer_path = self._selected_layer_path
        
        if not layer_path:
            return []
        
        return get_layer_aov_nodes(layer_path)
    
    def rename_layer_aov(
        self,
        aov_node_path: str,
        new_name: str
    ) -> Tuple[bool, str]:
        """
        Rename layer's AOV sub-node.
        
        Args:
            aov_node_path: AOV node path
            new_name: New name
        """
        success, msg = rename_layer_aov(aov_node_path, new_name)
        
        if success:
            self.log(f"[OK] Renamed AOV to '{new_name}'")
            self._notify_data_changed()
        else:
            self.log(f"[X] {msg}")
        
        return success, msg
    
    def set_layer_aov_driver(
        self,
        aov_node_path: str,
        driver: str
    ) -> Tuple[bool, str]:
        """
        Set AOV output driver.
        
        Args:
            aov_node_path: AOV node path
            driver: Driver type ("exr", "png", "tiff")
        """
        success, msg = set_layer_aov_property(aov_node_path, "driver", driver)
        
        if success:
            self._notify_data_changed()
        
        return success, msg
    
    def set_layer_aov_filter(
        self,
        aov_node_path: str,
        filter_type: str
    ) -> Tuple[bool, str]:
        """
        Set AOV filter type.
        
        Args:
            aov_node_path: AOV node path
            filter_type: Filter type ("gaussian", "box", "triangle")
        """
        success, msg = set_layer_aov_property(aov_node_path, "filter", filter_type)
        
        if success:
            self._notify_data_changed()
        
        return success, msg
    
    def toggle_layer_aov_node_enabled(self, aov_node_path: str) -> Tuple[bool, str]:
        """
        Toggle AOV sub-node enabled state.
        
        Args:
            aov_node_path: AOV node path
        """
        success, msg = toggle_layer_aov_enabled(aov_node_path)
        
        if success:
            self._notify_data_changed()
        
        return success, msg
    
    def create_standard_layer_aovs(self) -> Tuple[int, str]:
        """
        Create a set of standard AOV sub-nodes for selected layer.
        
        Similar to Maya's batch add common AOVs.
        """
        if not self._selected_layer_path:
            self.log("[!] Please select a layer first")
            return 0, "No layer selected"
        
        count, msg = create_standard_aovs_core(self._selected_layer_path)
        
        if count > 0:
            self.log(f"[OK] Created {count} standard AOVs for layer")
            self._notify_data_changed()
        else:
            self.log(f"[i] {msg}")
        
        return count, msg
    
    def apply_layer_aovs_to_render(self) -> Tuple[bool, str]:
        """
        Apply selected layer's AOV sub-node settings to renderer.
        
        Pushes layer's AOV configuration to Omniverse render settings.
        """
        if not self._selected_layer_path:
            self.log("[!] Please select a layer first")
            return False, "No layer selected"
        
        success, msg = apply_layer_aovs_to_renderer(self._selected_layer_path)
        
        if success:
            self.log(f"[OK] {msg}")
            self.log("[>] You can now use Movie Capture to render, AOV settings applied")
        else:
            self.log(f"[X] {msg}")
        
        return success, msg
    
    def get_available_aov_types_for_browser(self) -> List[Dict[str, Any]]:
        """
        Get available AOV types list for AOV browser.
        
        Shows all Omniverse supported AOVs and their status.
        
        Returns:
            List[Dict]: AOV type list, including whether added to current layer
        """
        if not self._selected_layer_path:
            # Return all available AOVs but marked as not added
            return [
                {
                    "id": aov_id,
                    "name": aov_info["name"],
                    "description": aov_info.get("description", ""),
                    "added": False,
                }
                for aov_id, aov_info in OMNIVERSE_AOVS.items()
            ]
        
        # Get AOVs added to layer
        layer_aovs = get_layer_aov_nodes(self._selected_layer_path)
        added_aov_ids = {aov["source_type"] for aov in layer_aovs}
        
        result = []
        for aov_id, aov_info in OMNIVERSE_AOVS.items():
            result.append({
                "id": aov_id,
                "name": aov_info["name"],
                "description": aov_info.get("description", ""),
                "added": aov_id in added_aov_ids,
            })
        
        return result
    
    # =========================================================================
    # Refresh
    # =========================================================================
    
    def refresh(self) -> None:
        """Refresh data."""
        self._layers_cache = get_all_render_layers()
        self._notify_data_changed()
        self.log("Data refreshed")
    
    # =========================================================================
    # Lifecycle
    # =========================================================================
    
    def dispose(self) -> None:
        """Clean up resources."""
        self._data_changed_callbacks.clear()
        self._selected_layer_path = ""
        self._selected_collection_path = ""
        self._layers_cache.clear()
        super().dispose()

