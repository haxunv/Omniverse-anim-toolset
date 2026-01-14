# -*- coding: utf-8 -*-
"""
Render Setup View
=================

Provides the UI for Maya-like Render Setup functionality.

Layout:
    - Top: Toolbar with create layer button
    - Left: Hierarchical tree (Layers > Collections > Overrides)
    - Right: Property Editor for selected item
"""

from typing import Optional, List, Dict, Any
import omni.ui as ui

from .base_view import BaseView
from .styles import Styles, Sizes, Colors
from ..viewmodels.render_setup_vm import RenderSetupViewModel
from ..core.render_setup import (
    RenderLayer, Collection, Override,
    FilterType, OverrideType
)


# =============================================================================
# Style Constants
# =============================================================================

class RenderSetupColors:
    """Colors specific to Render Setup UI."""
    LAYER_BG = 0xFF2D2D2D
    LAYER_BG_SELECTED = 0xFF3D5A70
    COLLECTION_BG = 0xFF262626
    COLLECTION_BG_SELECTED = 0xFF3A5A3A
    OVERRIDE_BG = 0xFF1F1F1F
    OVERRIDE_BG_SELECTED = 0xFF5A5A3A
    SCENE_BG = 0xFF252525
    TOOLBAR_BG = 0xFF1A1A1A
    PROPERTY_BG = 0xFF2A2A2A
    SPLITTER = 0xFF404040


class RenderSetupSizes:
    """Sizes specific to Render Setup UI."""
    TREE_INDENT = 20
    ITEM_HEIGHT = 26
    ICON_SIZE = 18
    COLOR_BAR_WIDTH = 4
    TOOLBAR_HEIGHT = 32
    PROPERTY_WIDTH = 320


# =============================================================================
# Render Setup View
# =============================================================================

class RenderSetupView(BaseView):
    """
    Render Setup View implementing Maya-like render layer management.
    
    Features:
        - Layer management with visibility and renderability toggles
        - Collection management with filters and expressions
        - Override management for attribute modifications
        - Drag & drop support for adding objects
        - Property editor for selected items
    """
    
    def __init__(self, viewmodel: RenderSetupViewModel):
        """Initialize the view."""
        super().__init__(viewmodel)
        self._vm: RenderSetupViewModel = viewmodel
        
        # UI component references
        self._tree_container: Optional[ui.VStack] = None
        self._property_container: Optional[ui.VStack] = None
        self._scene_frame: Optional[ui.Frame] = None
        
        # Drag & drop state
        self._drop_target_collection_id: Optional[str] = None
        
        # Subscribe to data changes
        self._vm.add_data_changed_callback(self._refresh_ui)
    
    def build(self) -> None:
        """Build the UI."""
        with ui.VStack(spacing=0):
            # Toolbar
            self._build_toolbar()
            
            # Main content area with splitter
            with ui.HStack(spacing=0):
                # Left panel: Tree view
                with ui.VStack(width=ui.Fraction(1), spacing=0):
                    self._build_scene_section()
                    ui.Separator(height=1, style={"background_color": RenderSetupColors.SPLITTER})
                    self._build_tree_section()
                
                # Splitter
                ui.Spacer(width=2, style={"background_color": RenderSetupColors.SPLITTER})
                
                # Right panel: Property Editor
                with ui.VStack(width=RenderSetupSizes.PROPERTY_WIDTH, spacing=0):
                    self._build_property_section()
    
    # =========================================================================
    # Toolbar
    # =========================================================================
    
    def _build_toolbar(self) -> None:
        """Build the toolbar with create layer button."""
        with ui.HStack(height=RenderSetupSizes.TOOLBAR_HEIGHT, 
                      style={"background_color": RenderSetupColors.TOOLBAR_BG}):
            ui.Spacer(width=8)
            
            # Create Layer button
            ui.Button(
                "+",
                width=28,
                height=24,
                tooltip="Create Render Layer",
                clicked_fn=self._on_create_layer_clicked,
                style={
                    "background_color": 0xFF3A8EBA,
                    "border_radius": 3,
                    "font_size": 16
                }
            )
            
            ui.Spacer(width=8)
            
            # Title
            ui.Label(
                "Render Setup",
                style={"font_size": 14, "color": Colors.TEXT_PRIMARY}
            )
            
            ui.Spacer()
            
            # Refresh button
            ui.Button(
                "R",
                width=24,
                height=24,
                tooltip="Refresh",
                clicked_fn=self._on_refresh_clicked,
                style={"border_radius": 3}
            )
            
            ui.Spacer(width=8)
    
    # =========================================================================
    # Scene Section (Master Layer)
    # =========================================================================
    
    def _build_scene_section(self) -> None:
        """Build the Scene section showing the master layer."""
        self._scene_frame = ui.Frame(height=50)
        with self._scene_frame:
            with ui.VStack(style={"background_color": RenderSetupColors.SCENE_BG}):
                ui.Spacer(height=4)
                with ui.HStack(height=RenderSetupSizes.ITEM_HEIGHT):
                    ui.Spacer(width=8)
                    
                    # Scene icon
                    ui.Label(
                        "S",
                        width=RenderSetupSizes.ICON_SIZE,
                        style={"font_size": 12, "color": 0xFF90CAF9}
                    )
                    
                    ui.Spacer(width=4)
                    
                    # Scene label
                    ui.Label(
                        "Scene",
                        style={"font_size": 13, "color": Colors.TEXT_PRIMARY}
                    )
                    
                    ui.Spacer()
                    
                ui.Spacer(height=4)
    
    # =========================================================================
    # Tree Section
    # =========================================================================
    
    def _build_tree_section(self) -> None:
        """Build the tree section for layers/collections/overrides."""
        with ui.ScrollingFrame(
            horizontal_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_AS_NEEDED,
            vertical_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_AS_NEEDED
        ):
            self._tree_container = ui.VStack(spacing=1)
            with self._tree_container:
                self._build_tree_content()
    
    def _build_tree_content(self) -> None:
        """Build the actual tree content."""
        layers = self._vm.layers
        
        if not layers:
            with ui.HStack(height=40):
                ui.Spacer(width=20)
                ui.Label(
                    "No render layers. Click '+' to create one.",
                    style={"color": Colors.TEXT_SECONDARY}
                )
        else:
            for layer in layers:
                self._build_layer_item(layer)
    
    def _build_layer_item(self, layer: RenderLayer) -> None:
        """Build a layer item in the tree."""
        selected_id, selected_type = self._vm.selected_item
        is_selected = selected_type == "layer" and selected_id == layer.id
        
        bg_color = RenderSetupColors.LAYER_BG_SELECTED if is_selected else RenderSetupColors.LAYER_BG
        
        with ui.VStack(spacing=0):
            # Layer row
            with ui.ZStack(height=RenderSetupSizes.ITEM_HEIGHT):
                # Background
                ui.Rectangle(style={"background_color": bg_color, "border_radius": 2})
                
                with ui.HStack():
                    # Color bar
                    ui.Rectangle(
                        width=RenderSetupSizes.COLOR_BAR_WIDTH,
                        style={"background_color": layer.color, "border_radius": 2}
                    )
                    
                    ui.Spacer(width=4)
                    
                    # Expand/collapse button
                    expand_icon = "V" if layer.expanded else ">"
                    ui.Button(
                        expand_icon,
                        width=16,
                        height=16,
                        clicked_fn=lambda lid=layer.id: self._on_layer_expand_clicked(lid),
                        style={"background_color": 0x00000000, "font_size": 10}
                    )
                    
                    ui.Spacer(width=2)
                    
                    # Layer icon
                    ui.Label(
                        "L",
                        width=RenderSetupSizes.ICON_SIZE,
                        style={"font_size": 11, "color": layer.color}
                    )
                    
                    # Layer name (clickable)
                    name_btn = ui.Button(
                        layer.name,
                        clicked_fn=lambda lid=layer.id: self._on_layer_selected(lid),
                        style={
                            "background_color": 0x00000000,
                            "color": Colors.TEXT_PRIMARY,
                            "font_size": 12
                        }
                    )
                    
                    ui.Spacer()
                    
                    # Visibility toggle (eye icon)
                    vis_color = 0xFFFFFFFF if layer.visible else 0xFF606060
                    ui.Button(
                        "O",  # Eye icon placeholder
                        width=22,
                        height=22,
                        tooltip="Toggle Visibility (Set as Active Layer)",
                        clicked_fn=lambda lid=layer.id, vis=layer.visible: self._on_layer_visibility_clicked(lid, vis),
                        style={"background_color": 0x00000000, "color": vis_color, "font_size": 12}
                    )
                    
                    # Renderable toggle (clapperboard icon)
                    rend_color = 0xFF3A8EBA if layer.renderable else 0xFF606060
                    ui.Button(
                        "R",  # Clapperboard icon placeholder
                        width=22,
                        height=22,
                        tooltip="Toggle Renderable",
                        clicked_fn=lambda lid=layer.id, rend=layer.renderable: self._on_layer_renderable_clicked(lid, rend),
                        style={"background_color": 0x00000000, "color": rend_color, "font_size": 12}
                    )
                    
                    ui.Spacer(width=4)
            
            # Collections (if expanded)
            if layer.expanded:
                for collection in layer.collections:
                    self._build_collection_item(collection, layer.id, indent=1)
    
    def _build_collection_item(self, collection: Collection, layer_id: str, indent: int = 1) -> None:
        """Build a collection item in the tree."""
        selected_id, selected_type = self._vm.selected_item
        is_selected = selected_type == "collection" and selected_id == collection.id
        
        bg_color = RenderSetupColors.COLLECTION_BG_SELECTED if is_selected else RenderSetupColors.COLLECTION_BG
        indent_width = indent * RenderSetupSizes.TREE_INDENT
        
        with ui.VStack(spacing=0):
            # Collection row
            with ui.ZStack(height=RenderSetupSizes.ITEM_HEIGHT):
                # Background
                ui.Rectangle(style={"background_color": bg_color, "border_radius": 2})
                
                with ui.HStack():
                    # Indent
                    ui.Spacer(width=indent_width)
                    
                    # Expand/collapse button
                    has_children = len(collection.overrides) > 0 or len(collection.sub_collections) > 0
                    if has_children:
                        expand_icon = "V" if collection.expanded else ">"
                        ui.Button(
                            expand_icon,
                            width=16,
                            height=16,
                            clicked_fn=lambda cid=collection.id: self._on_collection_expand_clicked(cid),
                            style={"background_color": 0x00000000, "font_size": 10}
                        )
                    else:
                        ui.Spacer(width=16)
                    
                    ui.Spacer(width=2)
                    
                    # Collection icon (diamond)
                    ui.Label(
                        "*",
                        width=RenderSetupSizes.ICON_SIZE,
                        style={"font_size": 14, "color": 0xFF90EE90}
                    )
                    
                    # Collection name (clickable)
                    ui.Button(
                        collection.name,
                        clicked_fn=lambda cid=collection.id: self._on_collection_selected(cid),
                        style={
                            "background_color": 0x00000000,
                            "color": Colors.TEXT_PRIMARY,
                            "font_size": 12
                        }
                    )
                    
                    ui.Spacer()
                    
                    # Select collection members button (diamond icon)
                    ui.Button(
                        "*",
                        width=22,
                        height=22,
                        tooltip="Select Collection Members",
                        clicked_fn=lambda cid=collection.id: self._on_select_collection_members(cid),
                        style={"background_color": 0x00000000, "color": 0xFF90EE90, "font_size": 12}
                    )
                    
                    # Enable/disable toggle
                    enable_color = 0xFFFFFFFF if collection.enabled else 0xFF606060
                    enable_icon = "E" if collection.enabled else "D"
                    ui.Button(
                        enable_icon,
                        width=22,
                        height=22,
                        tooltip="Enable/Disable Collection",
                        clicked_fn=lambda cid=collection.id, en=collection.enabled: self._on_collection_enable_clicked(cid, en),
                        style={"background_color": 0x00000000, "color": enable_color, "font_size": 10}
                    )
                    
                    ui.Spacer(width=4)
            
            # Overrides and sub-collections (if expanded)
            if collection.expanded:
                for override in collection.overrides:
                    self._build_override_item(override, collection.id, indent + 1)
                for sub_col in collection.sub_collections:
                    self._build_collection_item(sub_col, layer_id, indent + 1)
    
    def _build_override_item(self, override: Override, collection_id: str, indent: int = 2) -> None:
        """Build an override item in the tree."""
        selected_id, selected_type = self._vm.selected_item
        is_selected = selected_type == "override" and selected_id == override.id
        
        bg_color = RenderSetupColors.OVERRIDE_BG_SELECTED if is_selected else RenderSetupColors.OVERRIDE_BG
        indent_width = indent * RenderSetupSizes.TREE_INDENT
        
        with ui.ZStack(height=RenderSetupSizes.ITEM_HEIGHT):
            # Background
            ui.Rectangle(style={"background_color": bg_color, "border_radius": 2})
            
            with ui.HStack():
                # Indent
                ui.Spacer(width=indent_width)
                
                ui.Spacer(width=18)  # No expand button for overrides
                
                # Override type icon
                type_icon = "A" if override.override_type == OverrideType.ABSOLUTE else "R"
                type_color = 0xFFFFAA00 if override.override_type == OverrideType.ABSOLUTE else 0xFF00AAFF
                ui.Label(
                    type_icon,
                    width=RenderSetupSizes.ICON_SIZE,
                    style={"font_size": 10, "color": type_color}
                )
                
                # Override name
                ui.Button(
                    f"{override.name}: {override.value}",
                    clicked_fn=lambda oid=override.id: self._on_override_selected(oid),
                    style={
                        "background_color": 0x00000000,
                        "color": Colors.TEXT_PRIMARY if override.enabled else Colors.TEXT_DISABLED,
                        "font_size": 11
                    }
                )
                
                ui.Spacer()
                
                # Enable/disable toggle
                enable_color = 0xFFFFFFFF if override.enabled else 0xFF606060
                ui.Button(
                    "T" if override.enabled else "F",
                    width=22,
                    height=22,
                    tooltip="Enable/Disable Override",
                    clicked_fn=lambda oid=override.id, en=override.enabled: self._on_override_enable_clicked(oid, en),
                    style={"background_color": 0x00000000, "color": enable_color, "font_size": 10}
                )
                
                ui.Spacer(width=4)
    
    # =========================================================================
    # Property Editor Section
    # =========================================================================
    
    def _build_property_section(self) -> None:
        """Build the property editor section."""
        with ui.VStack(style={"background_color": RenderSetupColors.PROPERTY_BG}):
            # Header
            with ui.HStack(height=30):
                ui.Spacer(width=8)
                ui.Label(
                    "Property Editor - Render Setup",
                    style={"font_size": 12, "color": Colors.TEXT_PRIMARY}
                )
            
            ui.Separator(height=1, style={"background_color": RenderSetupColors.SPLITTER})
            
            # Content
            with ui.ScrollingFrame(
                horizontal_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_AS_NEEDED,
                vertical_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_AS_NEEDED
            ):
                self._property_container = ui.VStack(spacing=Sizes.SPACING_SMALL)
                with self._property_container:
                    self._build_property_content()
    
    def _build_property_content(self) -> None:
        """Build the property editor content based on selection."""
        selected_id, selected_type = self._vm.selected_item
        
        if not selected_id:
            ui.Spacer(height=20)
            ui.Label(
                "Select a layer or collection to edit properties",
                style={"color": Colors.TEXT_SECONDARY},
                alignment=ui.Alignment.CENTER
            )
            return
        
        if selected_type == "layer":
            self._build_layer_properties()
        elif selected_type == "collection":
            self._build_collection_properties()
        elif selected_type == "override":
            self._build_override_properties()
    
    def _build_layer_properties(self) -> None:
        """Build property editor for a layer."""
        layer = self._vm.selected_layer
        if not layer:
            return
        
        with ui.VStack(spacing=Sizes.SPACING_SMALL):
            ui.Spacer(height=8)
            
            # Layer header
            with ui.CollapsableFrame("Layer", collapsed=False):
                with ui.VStack(spacing=Sizes.SPACING_SMALL):
                    ui.Spacer(height=4)
                    
                    # Name
                    with ui.HStack(height=24):
                        ui.Label("Name:", width=100)
                        name_field = ui.StringField()
                        name_field.model.set_value(layer.name)
                        name_field.model.add_end_edit_fn(
                            lambda m, lid=layer.id: self._on_layer_name_changed(lid, m.get_value_as_string())
                        )
                    
                    # Color selection
                    with ui.HStack(height=24):
                        ui.Label("Color:", width=100)
                        colors = self._vm.get_layer_colors()
                        for color in colors:
                            is_current = color == layer.color
                            style = {
                                "background_color": color,
                                "border_width": 2 if is_current else 0,
                                "border_color": 0xFFFFFFFF
                            }
                            ui.Button(
                                "",
                                width=20,
                                height=20,
                                clicked_fn=lambda c=color, lid=layer.id: self._on_layer_color_changed(lid, c),
                                style=style
                            )
                        ui.Spacer()
                    
                    # Isolate Mode toggle
                    with ui.HStack(height=24):
                        ui.Label("Isolate Mode:", width=100)
                        isolate_checkbox = ui.CheckBox(width=20)
                        isolate_checkbox.model.set_value(layer.isolate_mode)
                        isolate_checkbox.model.add_value_changed_fn(
                            lambda m, lid=layer.id: self._on_layer_isolate_changed(lid, m.get_value_as_bool())
                        )
                        ui.Label(
                            "Only show collection members",
                            style={"color": Colors.TEXT_SECONDARY, "font_size": 11}
                        )
                    
                    ui.Spacer(height=4)
            
            # Add Collection button
            ui.Spacer(height=8)
            ui.Button(
                "Create Collection",
                height=Sizes.BUTTON_HEIGHT,
                clicked_fn=lambda lid=layer.id: self._on_create_collection_clicked(lid),
                style={"background_color": 0xFF3A8EBA}
            )
            
            # Delete Layer button
            ui.Spacer(height=4)
            ui.Button(
                "Delete Layer",
                height=Sizes.BUTTON_HEIGHT,
                clicked_fn=lambda lid=layer.id: self._on_delete_layer_clicked(lid),
                style={"background_color": 0xFF8E3A3A}
            )
    
    def _build_collection_properties(self) -> None:
        """Build property editor for a collection."""
        collection = self._vm.selected_collection
        if not collection:
            return
        
        with ui.VStack(spacing=Sizes.SPACING_SMALL):
            ui.Spacer(height=8)
            
            # Collection header
            with ui.CollapsableFrame("Collection", collapsed=False):
                with ui.VStack(spacing=Sizes.SPACING_SMALL):
                    ui.Spacer(height=4)
                    
                    # Name
                    with ui.HStack(height=24):
                        ui.Label("Name:", width=100)
                        name_field = ui.StringField()
                        name_field.model.set_value(collection.name)
                        name_field.model.add_end_edit_fn(
                            lambda m, cid=collection.id: self._on_collection_name_changed(cid, m.get_value_as_string())
                        )
                    
                    ui.Spacer(height=4)
            
            # Collection Filters
            with ui.CollapsableFrame("Collection Filters", collapsed=False):
                with ui.VStack(spacing=Sizes.SPACING_SMALL):
                    ui.Spacer(height=4)
                    
                    # Filter type dropdown
                    with ui.HStack(height=24):
                        ui.Label("Filter:", width=100)
                        filter_combo = ui.ComboBox(0)
                        filter_types = self._vm.get_filter_types()
                        for i, ft in enumerate(filter_types):
                            filter_combo.model.append_child_item(None, ui.SimpleStringModel(ft))
                            if ft == collection.filter_type.value:
                                filter_combo.model.get_item_value_model().set_value(i)
                        filter_combo.model.add_item_changed_fn(
                            lambda m, item, cid=collection.id, types=filter_types: 
                            self._on_collection_filter_changed(cid, types[m.get_item_value_model().get_value_as_int()])
                        )
                    
                    ui.Spacer(height=4)
            
            # Add to Collection
            with ui.CollapsableFrame("Add to Collection", collapsed=False):
                with ui.VStack(spacing=Sizes.SPACING_SMALL):
                    ui.Spacer(height=4)
                    
                    # Expression
                    ui.Label("Include:", style={"color": Colors.TEXT_SECONDARY})
                    with ui.HStack(height=24):
                        ui.Label("Expression:", width=80)
                        expr_field = ui.StringField()
                        expr_field.model.set_value(collection.expression)
                        expr_field.model.add_end_edit_fn(
                            lambda m, cid=collection.id: self._on_collection_expression_changed(cid, m.get_value_as_string())
                        )
                    
                    ui.Label(
                        "Use wildcards: *Character* ; *_geo",
                        style={"color": Colors.TEXT_SECONDARY, "font_size": 10}
                    )
                    
                    ui.Spacer(height=4)
                    
                    # Manual add/remove buttons
                    with ui.HStack(height=Sizes.BUTTON_HEIGHT):
                        ui.Button(
                            "Add",
                            clicked_fn=lambda cid=collection.id: self._on_add_to_collection_clicked(cid),
                            tooltip="Add selected objects to collection"
                        )
                        ui.Button(
                            "Remove",
                            clicked_fn=lambda cid=collection.id: self._on_remove_from_collection_clicked(cid),
                            tooltip="Remove selected objects from collection"
                        )
                        ui.Button(
                            "Select",
                            clicked_fn=lambda cid=collection.id: self._on_select_collection_members(cid),
                            tooltip="Select all collection members"
                        )
                    
                    ui.Spacer(height=4)
                    
                    # Member list
                    ui.Label("Members:", style={"color": Colors.TEXT_SECONDARY})
                    members = self._vm.get_collection_members(collection.id)
                    
                    with ui.ScrollingFrame(
                        height=100,
                        horizontal_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_AS_NEEDED,
                        vertical_scrollbar_policy=ui.ScrollBarPolicy.SCROLLBAR_AS_NEEDED,
                        style={"background_color": 0xFF1E1E1E, "border_radius": 4}
                    ):
                        with ui.VStack(spacing=1):
                            if not members:
                                ui.Label(
                                    "  No members",
                                    style={"color": Colors.TEXT_SECONDARY}
                                )
                            else:
                                for member in members[:50]:  # Limit display
                                    with ui.HStack(height=18):
                                        ui.Label(
                                            f"  {member['name']}",
                                            elided_text=True,
                                            tooltip=member['path'],
                                            style={"color": Colors.TEXT_PRIMARY, "font_size": 11}
                                        )
                                if len(members) > 50:
                                    ui.Label(
                                        f"  ... and {len(members) - 50} more",
                                        style={"color": Colors.TEXT_SECONDARY}
                                    )
                    
                    with ui.HStack(height=20):
                        ui.Label(f"View All ({len(members)})", style={"color": Colors.TEXT_SECONDARY})
                        ui.Spacer()
                        ui.Button(
                            "Select All",
                            width=70,
                            height=20,
                            clicked_fn=lambda cid=collection.id: self._on_select_collection_members(cid)
                        )
                    
                    ui.Spacer(height=4)
            
            # Add Override
            with ui.CollapsableFrame("Add Override", collapsed=False):
                with ui.VStack(spacing=Sizes.SPACING_SMALL):
                    ui.Spacer(height=4)
                    
                    # Override type
                    with ui.HStack(height=24):
                        ui.Label("Type:", width=80)
                        self._override_type_combo = ui.ComboBox(0)
                        override_types = self._vm.get_override_types()
                        for ot in override_types:
                            self._override_type_combo.model.append_child_item(None, ui.SimpleStringModel(ot))
                    
                    ui.Spacer(height=4)
                    
                    # Common attributes - Visibility
                    ui.Label("Visibility:", style={"color": Colors.TEXT_SECONDARY, "font_size": 11})
                    with ui.HStack(height=22, spacing=4):
                        for attr in self._vm.get_visibility_attributes():
                            ui.Button(
                                f"+ {attr['name']}",
                                height=20,
                                clicked_fn=lambda cid=collection.id, a=attr: self._on_add_common_override(cid, a),
                                tooltip=attr['description'],
                                style={"font_size": 10}
                            )
                    
                    # Common attributes - Rendering
                    ui.Label("Rendering:", style={"color": Colors.TEXT_SECONDARY, "font_size": 11})
                    with ui.VStack(spacing=2):
                        for attr in self._vm.get_rendering_attributes():
                            ui.Button(
                                f"+ {attr['name']}",
                                height=20,
                                clicked_fn=lambda cid=collection.id, a=attr: self._on_add_common_override(cid, a),
                                tooltip=attr['description'],
                                style={"font_size": 10}
                            )
                    
                    # Common attributes - Transform
                    ui.Label("Transform:", style={"color": Colors.TEXT_SECONDARY, "font_size": 11})
                    with ui.HStack(height=22, spacing=4):
                        for attr in self._vm.get_transform_attributes():
                            ui.Button(
                                f"+ {attr['name']}",
                                height=20,
                                clicked_fn=lambda cid=collection.id, a=attr: self._on_add_common_override(cid, a),
                                tooltip=attr['description'],
                                style={"font_size": 10}
                            )
                    
                    ui.Spacer(height=8)
                    
                    # Custom attribute input
                    ui.Label("Custom Attribute:", style={"color": Colors.TEXT_SECONDARY, "font_size": 11})
                    with ui.HStack(height=24, spacing=4):
                        self._custom_attr_field = ui.StringField()
                        self._custom_attr_field.model.set_value("")
                        ui.Button(
                            "Add",
                            width=50,
                            height=22,
                            clicked_fn=lambda cid=collection.id: self._on_add_custom_override(cid),
                            tooltip="Add custom attribute override"
                        )
                    ui.Label(
                        "Enter attribute path (e.g., visibility, xformOp:translate)",
                        style={"color": Colors.TEXT_SECONDARY, "font_size": 9}
                    )
                    
                    ui.Spacer(height=4)
                    
                    # Get attributes from selection
                    ui.Button(
                        "Get Attributes from Selection...",
                        height=Sizes.BUTTON_HEIGHT,
                        clicked_fn=lambda cid=collection.id: self._on_show_prim_attributes(cid),
                        tooltip="Show attributes of selected prim"
                    )
                    
                    ui.Spacer(height=4)
            
            # Actions
            ui.Spacer(height=8)
            
            # Find parent layer for operations
            layer_id = self._find_layer_for_collection(collection.id)
            
            if layer_id:
                ui.Button(
                    "Create Sub-Collection",
                    height=Sizes.BUTTON_HEIGHT,
                    clicked_fn=lambda lid=layer_id, cid=collection.id: self._on_create_sub_collection_clicked(lid, cid)
                )
                
                ui.Spacer(height=4)
                
                ui.Button(
                    "Delete Collection",
                    height=Sizes.BUTTON_HEIGHT,
                    clicked_fn=lambda lid=layer_id, cid=collection.id: self._on_delete_collection_clicked(lid, cid),
                    style={"background_color": 0xFF8E3A3A}
                )
    
    def _build_override_properties(self) -> None:
        """Build property editor for an override."""
        # Find the override
        selected_id, _ = self._vm.selected_item
        override = self._find_override_by_id(selected_id)
        
        if not override:
            return
        
        collection_id = self._find_collection_for_override(selected_id)
        
        with ui.VStack(spacing=Sizes.SPACING_SMALL):
            ui.Spacer(height=8)
            
            with ui.CollapsableFrame("Override", collapsed=False):
                with ui.VStack(spacing=Sizes.SPACING_SMALL):
                    ui.Spacer(height=4)
                    
                    # Name (read-only)
                    with ui.HStack(height=24):
                        ui.Label("Attribute:", width=80)
                        ui.Label(override.name, style={"color": Colors.TEXT_PRIMARY})
                    
                    # Type
                    with ui.HStack(height=24):
                        ui.Label("Type:", width=80)
                        ui.Label(
                            override.override_type.value,
                            style={"color": 0xFFFFAA00 if override.override_type == OverrideType.ABSOLUTE else 0xFF00AAFF}
                        )
                    
                    # Value
                    with ui.HStack(height=24):
                        ui.Label("Value:", width=80)
                        if isinstance(override.value, bool):
                            checkbox = ui.CheckBox(width=20)
                            checkbox.model.set_value(override.value)
                            checkbox.model.add_value_changed_fn(
                                lambda m, oid=override.id: self._on_override_value_changed(oid, m.get_value_as_bool())
                            )
                        elif isinstance(override.value, (int, float)):
                            value_field = ui.FloatField()
                            value_field.model.set_value(float(override.value))
                            value_field.model.add_value_changed_fn(
                                lambda m, oid=override.id: self._on_override_value_changed(oid, m.get_value_as_float())
                            )
                        else:
                            value_field = ui.StringField()
                            value_field.model.set_value(str(override.value))
                            value_field.model.add_end_edit_fn(
                                lambda m, oid=override.id: self._on_override_value_changed(oid, m.get_value_as_string())
                            )
                    
                    # Enabled
                    with ui.HStack(height=24):
                        ui.Label("Enabled:", width=80)
                        enabled_checkbox = ui.CheckBox(width=20)
                        enabled_checkbox.model.set_value(override.enabled)
                        enabled_checkbox.model.add_value_changed_fn(
                            lambda m, oid=override.id: self._vm.set_override_enabled(oid, m.get_value_as_bool())
                        )
                    
                    ui.Spacer(height=4)
            
            # Delete button
            if collection_id:
                ui.Spacer(height=8)
                ui.Button(
                    "Delete Override",
                    height=Sizes.BUTTON_HEIGHT,
                    clicked_fn=lambda cid=collection_id, oid=override.id: self._on_delete_override_clicked(cid, oid),
                    style={"background_color": 0xFF8E3A3A}
                )
    
    # =========================================================================
    # Event Handlers - Toolbar
    # =========================================================================
    
    def _on_create_layer_clicked(self) -> None:
        """Handle create layer button click."""
        self._vm.create_layer()
    
    def _on_refresh_clicked(self) -> None:
        """Handle refresh button click."""
        self._refresh_ui()
    
    # =========================================================================
    # Event Handlers - Layer
    # =========================================================================
    
    def _on_layer_selected(self, layer_id: str) -> None:
        """Handle layer selection."""
        self._vm.select_item(layer_id, "layer")
    
    def _on_layer_expand_clicked(self, layer_id: str) -> None:
        """Handle layer expand/collapse."""
        self._vm.toggle_layer_expanded(layer_id)
    
    def _on_layer_visibility_clicked(self, layer_id: str, current_visible: bool) -> None:
        """Handle layer visibility toggle."""
        self._vm.set_layer_visible(layer_id, not current_visible)
    
    def _on_layer_renderable_clicked(self, layer_id: str, current_renderable: bool) -> None:
        """Handle layer renderable toggle."""
        self._vm.set_layer_renderable(layer_id, not current_renderable)
    
    def _on_layer_name_changed(self, layer_id: str, new_name: str) -> None:
        """Handle layer name change."""
        if new_name.strip():
            self._vm.rename_layer(layer_id, new_name.strip())
    
    def _on_layer_color_changed(self, layer_id: str, color: int) -> None:
        """Handle layer color change."""
        self._vm.set_layer_color(layer_id, color)
    
    def _on_layer_isolate_changed(self, layer_id: str, isolate: bool) -> None:
        """Handle layer isolate mode change."""
        self._vm.set_layer_isolate_mode(layer_id, isolate)
    
    def _on_delete_layer_clicked(self, layer_id: str) -> None:
        """Handle delete layer button click."""
        self._vm.delete_layer(layer_id)
        self._vm.clear_selection()
    
    def _on_create_collection_clicked(self, layer_id: str) -> None:
        """Handle create collection button click."""
        self._vm.create_collection(layer_id)
    
    # =========================================================================
    # Event Handlers - Collection
    # =========================================================================
    
    def _on_collection_selected(self, collection_id: str) -> None:
        """Handle collection selection."""
        self._vm.select_item(collection_id, "collection")
    
    def _on_collection_expand_clicked(self, collection_id: str) -> None:
        """Handle collection expand/collapse."""
        self._vm.toggle_collection_expanded(collection_id)
    
    def _on_collection_enable_clicked(self, collection_id: str, current_enabled: bool) -> None:
        """Handle collection enable toggle."""
        self._vm.set_collection_enabled(collection_id, not current_enabled)
    
    def _on_select_collection_members(self, collection_id: str) -> None:
        """Handle select collection members button."""
        self._vm.select_collection_members(collection_id)
    
    def _on_collection_name_changed(self, collection_id: str, new_name: str) -> None:
        """Handle collection name change."""
        if new_name.strip():
            self._vm.rename_collection(collection_id, new_name.strip())
    
    def _on_collection_filter_changed(self, collection_id: str, filter_value: str) -> None:
        """Handle collection filter change."""
        filter_type = FilterType(filter_value)
        self._vm.set_collection_filter(collection_id, filter_type)
    
    def _on_collection_expression_changed(self, collection_id: str, expression: str) -> None:
        """Handle collection expression change."""
        self._vm.set_collection_expression(collection_id, expression)
    
    def _on_add_to_collection_clicked(self, collection_id: str) -> None:
        """Handle add to collection button."""
        self._vm.add_selected_to_collection(collection_id)
    
    def _on_remove_from_collection_clicked(self, collection_id: str) -> None:
        """Handle remove from collection button."""
        # Get selected prims and remove them
        from ..core.render_setup import get_render_setup_manager
        manager = get_render_setup_manager()
        selected = manager.get_selected_prims()
        for path in selected:
            self._vm.remove_path_from_collection(collection_id, path)
    
    def _on_delete_collection_clicked(self, layer_id: str, collection_id: str) -> None:
        """Handle delete collection button."""
        self._vm.delete_collection(layer_id, collection_id)
        self._vm.clear_selection()
    
    def _on_create_sub_collection_clicked(self, layer_id: str, parent_collection_id: str) -> None:
        """Handle create sub-collection button."""
        self._vm.create_collection(layer_id, parent_collection_id=parent_collection_id)
    
    # =========================================================================
    # Event Handlers - Override
    # =========================================================================
    
    def _on_override_selected(self, override_id: str) -> None:
        """Handle override selection."""
        self._vm.select_item(override_id, "override")
    
    def _on_override_enable_clicked(self, override_id: str, current_enabled: bool) -> None:
        """Handle override enable toggle."""
        self._vm.set_override_enabled(override_id, not current_enabled)
    
    def _on_override_value_changed(self, override_id: str, value: Any) -> None:
        """Handle override value change."""
        self._vm.set_override_value(override_id, value)
    
    def _on_delete_override_clicked(self, collection_id: str, override_id: str) -> None:
        """Handle delete override button."""
        self._vm.delete_override(collection_id, override_id)
        self._vm.clear_selection()
    
    def _on_add_common_override(self, collection_id: str, attr_info: Dict[str, Any]) -> None:
        """Handle adding a common override."""
        override_type_idx = 0
        if hasattr(self, '_override_type_combo'):
            override_type_idx = self._override_type_combo.model.get_item_value_model().get_value_as_int()
        
        override_types = self._vm.get_override_types()
        override_type = OverrideType(override_types[override_type_idx])
        
        self._vm.create_override(
            collection_id,
            attr_info['path'],
            attr_info['default_value'],
            override_type,
            attr_info['name']
        )
    
    def _on_add_custom_override(self, collection_id: str) -> None:
        """Handle adding a custom attribute override."""
        if not hasattr(self, '_custom_attr_field'):
            return
        
        attr_path = self._custom_attr_field.model.get_value_as_string().strip()
        if not attr_path:
            return
        
        override_type_idx = 0
        if hasattr(self, '_override_type_combo'):
            override_type_idx = self._override_type_combo.model.get_item_value_model().get_value_as_int()
        
        override_types = self._vm.get_override_types()
        override_type = OverrideType(override_types[override_type_idx])
        
        # Determine default value based on common attribute names
        default_value: Any = True
        attr_lower = attr_path.lower()
        if 'translate' in attr_lower or 'scale' in attr_lower or 'rotate' in attr_lower:
            default_value = [0.0, 0.0, 0.0]
        elif 'color' in attr_lower:
            default_value = [1.0, 1.0, 1.0]
        elif 'intensity' in attr_lower or 'exposure' in attr_lower:
            default_value = 1.0
        
        # Use the last part of the path as the name
        attr_name = attr_path.split(":")[-1] if ":" in attr_path else attr_path
        
        self._vm.create_override(
            collection_id,
            attr_path,
            default_value,
            override_type,
            attr_name
        )
        
        # Clear the input field
        self._custom_attr_field.model.set_value("")
    
    def _on_show_prim_attributes(self, collection_id: str) -> None:
        """Show attributes of the selected prim in a popup."""
        attrs = self._vm.get_selected_prim_attributes()
        if not attrs:
            print("[RenderSetup] No prim selected or no attributes found")
            return
        
        # Create a popup window showing attributes
        self._show_attributes_popup(collection_id, attrs)
    
    def _show_attributes_popup(self, collection_id: str, attrs: List[Dict[str, Any]]) -> None:
        """Show a popup window with prim attributes."""
        # Create a simple popup window
        popup_window = ui.Window(
            "Select Attribute to Override",
            width=400,
            height=500,
            flags=ui.WINDOW_FLAGS_NO_COLLAPSE
        )
        
        with popup_window.frame:
            with ui.VStack(spacing=4):
                ui.Label(
                    f"Found {len(attrs)} attributes",
                    style={"font_size": 12, "color": Colors.TEXT_SECONDARY}
                )
                ui.Label(
                    "Click an attribute to add as override:",
                    style={"font_size": 11, "color": Colors.TEXT_SECONDARY}
                )
                
                ui.Separator(height=4)
                
                with ui.ScrollingFrame(height=400):
                    with ui.VStack(spacing=2):
                        for attr in attrs[:100]:  # Limit to 100 attributes
                            attr_name = attr.get('name', 'unknown')
                            attr_value = attr.get('value', None)
                            attr_type = attr.get('type', 'unknown')
                            
                            # Format value for display
                            value_str = str(attr_value)[:30] if attr_value is not None else "None"
                            
                            with ui.HStack(height=22):
                                ui.Button(
                                    f"+ {attr_name}",
                                    width=150,
                                    height=20,
                                    clicked_fn=lambda a=attr, cid=collection_id, w=popup_window: self._add_attr_and_close(cid, a, w),
                                    style={"font_size": 10}
                                )
                                ui.Label(
                                    f"= {value_str}",
                                    style={"font_size": 10, "color": Colors.TEXT_SECONDARY}
                                )
                                ui.Label(
                                    f"({attr_type})",
                                    width=80,
                                    style={"font_size": 9, "color": 0xFF808080}
                                )
                
                ui.Separator(height=4)
                
                ui.Button(
                    "Close",
                    height=26,
                    clicked_fn=lambda w=popup_window: w.destroy()
                )
    
    def _add_attr_and_close(self, collection_id: str, attr: Dict[str, Any], window: ui.Window) -> None:
        """Add an attribute as override and close the popup."""
        attr_name = attr.get('name', 'unknown')
        attr_value = attr.get('value', True)
        
        override_type_idx = 0
        if hasattr(self, '_override_type_combo'):
            override_type_idx = self._override_type_combo.model.get_item_value_model().get_value_as_int()
        
        override_types = self._vm.get_override_types()
        override_type = OverrideType(override_types[override_type_idx])
        
        self._vm.create_override(
            collection_id,
            attr_name,
            attr_value if attr_value is not None else True,
            override_type,
            attr_name
        )
        
        window.destroy()
    
    # =========================================================================
    # Utility Methods
    # =========================================================================
    
    def _find_layer_for_collection(self, collection_id: str) -> Optional[str]:
        """Find the layer ID that contains a collection."""
        for layer in self._vm.layers:
            if layer.find_collection(collection_id):
                return layer.id
        return None
    
    def _find_override_by_id(self, override_id: str) -> Optional[Override]:
        """Find an override by ID."""
        for layer in self._vm.layers:
            for col in layer.collections:
                override = self._search_override_in_collection(col, override_id)
                if override:
                    return override
        return None
    
    def _search_override_in_collection(self, collection: Collection, override_id: str) -> Optional[Override]:
        """Recursively search for an override in a collection."""
        for ovr in collection.overrides:
            if ovr.id == override_id:
                return ovr
        for sub in collection.sub_collections:
            found = self._search_override_in_collection(sub, override_id)
            if found:
                return found
        return None
    
    def _find_collection_for_override(self, override_id: str) -> Optional[str]:
        """Find the collection ID that contains an override."""
        for layer in self._vm.layers:
            for col in layer.collections:
                cid = self._search_collection_for_override(col, override_id)
                if cid:
                    return cid
        return None
    
    def _search_collection_for_override(self, collection: Collection, override_id: str) -> Optional[str]:
        """Recursively search for the collection containing an override."""
        for ovr in collection.overrides:
            if ovr.id == override_id:
                return collection.id
        for sub in collection.sub_collections:
            cid = self._search_collection_for_override(sub, override_id)
            if cid:
                return cid
        return None
    
    # =========================================================================
    # UI Refresh
    # =========================================================================
    
    def _refresh_ui(self) -> None:
        """Refresh the entire UI."""
        # Rebuild tree
        if self._tree_container:
            self._tree_container.clear()
            with self._tree_container:
                self._build_tree_content()
        
        # Rebuild property panel
        if self._property_container:
            self._property_container.clear()
            with self._property_container:
                self._build_property_content()
    
    # =========================================================================
    # Lifecycle
    # =========================================================================
    
    def dispose(self) -> None:
        """Clean up resources."""
        self._vm.remove_data_changed_callback(self._refresh_ui)
        self._tree_container = None
        self._property_container = None
        self._scene_frame = None
        super().dispose()
