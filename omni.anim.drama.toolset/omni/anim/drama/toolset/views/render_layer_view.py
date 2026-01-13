# -*- coding: utf-8 -*-
"""
Render Layer View - Maya Render Setup Style
============================================

A Maya-inspired render layer management interface with AOV override support.

Key Features (matching Maya Render Setup):
    - Layer tree with AOV nodes as children
    - "Create Override" to add AOV to layer
    - AOV renaming per layer
    - Per-layer AOV enable/disable
"""

import omni.ui as ui

from .base_view import BaseView
from .styles import Styles, Sizes, Colors
from ..viewmodels.render_layer_vm import RenderLayerViewModel


# =============================================================================
# Maya-style Colors
# =============================================================================

class MayaColors:
    BG_DARK = 0xFF1E1E1E
    BG_PANEL = 0xFF2A2A2A
    BG_ITEM = 0xFF323232
    BG_SELECTED = 0xFF4A6FA5
    BG_LAYER = 0xFF3A3A4A
    BG_AOV = 0xFF2D3A2D
    BG_COLLECTION = 0xFF3A3A3A
    
    TEXT_PRIMARY = 0xFFD0D0D0
    TEXT_SECONDARY = 0xFF909090
    TEXT_DISABLED = 0xFF606060
    
    ICON_VISIBLE = 0xFF80C080
    ICON_SOLO = 0xFFFFC040
    ICON_RENDERABLE = 0xFF6090D0
    ICON_DISABLED = 0xFF505050
    ICON_AOV = 0xFF60A060
    
    ACCENT_GREEN = 0xFF4CAF50
    ACCENT_ORANGE = 0xFFFF9800
    ACCENT_RED = 0xFFF44336
    ACCENT_BLUE = 0xFF2196F3
    ACCENT_YELLOW = 0xFFFFEB3B


class RenderLayerView(BaseView):
    """
    Render Layer View - Maya Render Setup Style with AOV Override support.
    """
    
    def __init__(self, viewmodel: RenderLayerViewModel):
        super().__init__(viewmodel)
        self._vm: RenderLayerViewModel = viewmodel
        
        # UI containers
        self._tree_container = None
        self._properties_container = None
        self._aov_browser_container = None
        
        # Expanded states for tree nodes
        self._expanded_layers = set()
        self._expanded_aovs = set()
        
        # Selected AOV path (for property editor)
        self._selected_aov_path = None
        
        # Bind callback
        self._vm.add_data_changed_callback(self._refresh_all)
    
    def build(self) -> None:
        """Build the UI."""
        with ui.VStack(spacing=0, style={"background_color": MayaColors.BG_DARK}):
            # Toolbar
            self._build_toolbar()
            
            # Main content
            with ui.HStack(height=ui.Percent(100), spacing=2):
                # Left: Render Setup tree (Layers + AOVs + Collections)
                with ui.VStack(width=320, style={"background_color": MayaColors.BG_PANEL}):
                    self._build_render_setup_panel()
                
                # Right: Property Editor + AOV Browser
                with ui.VStack(style={"background_color": MayaColors.BG_PANEL}):
                    self._build_property_editor_panel()
            
            # Log
            self._create_log_section(height=60)
    
    # =========================================================================
    # Toolbar
    # =========================================================================
    
    def _build_toolbar(self) -> None:
        with ui.HStack(height=32, style={"background_color": 0xFF333333}):
            ui.Spacer(width=8)
            ui.Label("Render Setup", style={"font_size": 14, "color": MayaColors.TEXT_PRIMARY})
            ui.Spacer()
            
            # New Layer button
            ui.Button("+ New Layer", width=90, height=24, clicked_fn=self._on_new_layer,
                      style={"background_color": MayaColors.ACCENT_GREEN})
            ui.Spacer(width=8)
            ui.Button("Refresh", width=60, height=24, clicked_fn=self._vm.refresh)
            ui.Spacer(width=8)
    
    # =========================================================================
    # Left Panel: Render Setup Tree (Like Maya's Render Setup window)
    # =========================================================================
    
    def _build_render_setup_panel(self) -> None:
        """Build the main Render Setup tree panel."""
        with ui.VStack(spacing=0):
            # Header
            with ui.HStack(height=26, style={"background_color": 0xFF383838}):
                ui.Spacer(width=8)
                ui.Label("Render Setup", style={"color": MayaColors.TEXT_PRIMARY, "font_size": 11})
                ui.Spacer()
            
            # Scene/Render Settings/AOVs/Lights (like Maya)
            with ui.VStack(height=80, style={"background_color": MayaColors.BG_DARK}):
                self._build_scene_header_items()
            
            ui.Separator(height=1, style={"color": 0xFF404040})
            
            # Main tree (Layers > AOVs > Collections)
            with ui.ScrollingFrame(style={"background_color": MayaColors.BG_DARK, "border_width": 0}):
                self._tree_container = ui.VStack(spacing=0)
                with self._tree_container:
                    self._build_tree()
    
    def _build_scene_header_items(self) -> None:
        """Build Scene/Render Settings/AOVs/Lights header items (like Maya)."""
        items = [
            ("Scene", "◆"),
            ("Render Settings", "⚙"),
            ("AOVs", "◈"),
            ("Lights", "☀"),
        ]
        
        for name, icon in items:
            with ui.HStack(height=20):
                ui.Spacer(width=8)
                ui.Label(icon, width=16, style={"color": MayaColors.TEXT_SECONDARY})
                ui.Label(name, style={"color": MayaColors.TEXT_SECONDARY, "font_size": 11})
    
    def _build_tree(self) -> None:
        """Build the layer tree with AOVs and Collections as children."""
        layers = self._vm.get_layers()
        
        if not layers:
            with ui.HStack(height=40):
                ui.Spacer()
                ui.Label("No render layers", style={"color": MayaColors.TEXT_DISABLED})
                ui.Spacer()
            with ui.HStack(height=20):
                ui.Spacer()
                ui.Label("Click '+ New Layer' to create", style={"color": MayaColors.TEXT_DISABLED, "font_size": 10})
                ui.Spacer()
            return
        
        for layer in layers:
            self._build_layer_node(layer)
    
    def _build_layer_node(self, layer: dict) -> None:
        """Build a layer node with its children (AOVs, Collections)."""
        path = layer["path"]
        name = layer["name"]
        is_selected = path == self._vm.selected_layer_path
        is_expanded = path in self._expanded_layers
        
        # Layer row
        bg = MayaColors.BG_SELECTED if is_selected else MayaColors.BG_LAYER
        
        with ui.HStack(height=26, style={"background_color": bg}):
            # Expand/collapse arrow
            arrow = "▼" if is_expanded else "▶"
            ui.Button(
                arrow, width=20, height=24,
                clicked_fn=lambda p=path: self._toggle_layer_expand(p),
                style={"background_color": 0x00000000, "color": MayaColors.TEXT_SECONDARY}
            )
            
            # Layer icon
            ui.Label("◆", width=16, style={"color": MayaColors.ACCENT_ORANGE})
            
            # Layer label (clickable)
            ui.Button(
                f"Layer: {name}",
                height=24,
                clicked_fn=lambda p=path: self._on_layer_clicked(p),
                style={"background_color": 0x00000000, "color": MayaColors.TEXT_PRIMARY, "font_size": 11}
            )
            
            ui.Spacer()
            
            # V/S/R toggles
            vis_color = MayaColors.ICON_VISIBLE if layer["visible"] else MayaColors.ICON_DISABLED
            ui.Button("V", width=20, height=22,
                      clicked_fn=lambda p=path: self._vm.toggle_layer_visible(p),
                      style={"background_color": 0x00000000, "color": vis_color})
            
            solo_color = MayaColors.ICON_SOLO if layer["solo"] else MayaColors.ICON_DISABLED
            ui.Button("S", width=20, height=22,
                      clicked_fn=lambda p=path: self._vm.toggle_layer_solo(p),
                      style={"background_color": 0x00000000, "color": solo_color})
            
            render_color = MayaColors.ICON_RENDERABLE if layer["renderable"] else MayaColors.ICON_DISABLED
            ui.Button("R", width=20, height=22,
                      clicked_fn=lambda p=path: self._vm.toggle_layer_renderable(p),
                      style={"background_color": 0x00000000, "color": render_color})
            
            # Delete
            ui.Button("×", width=20, height=22,
                      clicked_fn=lambda p=path: self._on_delete_layer(p),
                      style={"background_color": 0x00000000, "color": MayaColors.ACCENT_RED})
            
            ui.Spacer(width=4)
        
        # Children (if expanded)
        if is_expanded:
            # AOVs section
            layer_aovs = self._vm.get_layer_aov_list(path)
            if layer_aovs:
                self._build_aovs_section(path, layer_aovs)
            
            # Collections section
            collections = self._vm.get_collections_for_selected_layer() if is_selected else []
            if collections:
                for col in collections:
                    self._build_collection_node(col, indent=1)
    
    def _build_aovs_section(self, layer_path: str, aovs: list) -> None:
        """Build the AOVs section under a layer (like Maya's AOVs node)."""
        is_aov_expanded = f"{layer_path}/AOVs" in self._expanded_aovs
        
        # AOVs header row
        with ui.HStack(height=22, style={"background_color": MayaColors.BG_AOV}):
            ui.Spacer(width=20)
            
            arrow = "▼" if is_aov_expanded else "▶"
            ui.Button(
                arrow, width=18, height=20,
                clicked_fn=lambda p=f"{layer_path}/AOVs": self._toggle_aov_expand(p),
                style={"background_color": 0x00000000, "color": MayaColors.TEXT_SECONDARY}
            )
            
            ui.Label("◈", width=14, style={"color": MayaColors.ICON_AOV})
            ui.Label("AOVs", style={"color": MayaColors.ICON_AOV, "font_size": 11})
            
            ui.Spacer()
            
            ui.Label(f"({len(aovs)})", width=30, style={"color": MayaColors.TEXT_SECONDARY, "font_size": 10})
        
        # Individual AOV items
        if is_aov_expanded:
            for aov in aovs:
                self._build_aov_item(aov)
    
    def _build_aov_item(self, aov: dict) -> None:
        """Build a single AOV item under a layer (like Maya's AOV override)."""
        aov_path = aov["path"]
        display_name = aov.get("name_override") or aov.get("display_name", "")
        enabled = aov.get("enabled", True)
        is_selected = self._selected_aov_path == aov_path
        
        bg = MayaColors.BG_SELECTED if is_selected else 0xFF2A3A2A
        name_color = MayaColors.ICON_AOV if enabled else MayaColors.ICON_DISABLED
        
        with ui.HStack(height=22, style={"background_color": bg}):
            ui.Spacer(width=44)
            
            # Checkbox for enabled
            checkbox = ui.CheckBox(width=18, height=18)
            checkbox.model.set_value(enabled)
            checkbox.model.add_value_changed_fn(
                lambda m, p=aov_path: self._on_toggle_aov(p)
            )
            
            # AOV name (clickable to select for property editor)
            ui.Button(
                display_name,
                height=20,
                clicked_fn=lambda p=aov_path: self._on_aov_clicked(p),
                style={"background_color": 0x00000000, "color": name_color, "font_size": 10}
            )
            
            ui.Spacer()
            
            # If renamed, show indicator
            if aov.get("name_override") and aov.get("name_override") != aov.get("display_name"):
                ui.Label("(renamed)", width=50, style={"color": MayaColors.ACCENT_YELLOW, "font_size": 9})
            
            # Delete AOV from layer
            ui.Button(
                "×", width=18, height=18,
                clicked_fn=lambda t=aov["source_type"]: self._on_remove_aov(t),
                style={"background_color": 0x00000000, "color": MayaColors.ACCENT_RED}
            )
            
            ui.Spacer(width=8)
    
    def _build_collection_node(self, col: dict, indent: int = 0) -> None:
        """Build a collection node."""
        path = col["path"]
        name = col["name"]
        is_selected = path == self._vm.selected_collection_path
        
        bg = MayaColors.BG_SELECTED if is_selected else MayaColors.BG_COLLECTION
        
        with ui.HStack(height=22, style={"background_color": bg}):
            ui.Spacer(width=20 + indent * 16)
            
            # Collection icon
            enabled = col.get("enabled", True)
            en_color = MayaColors.ACCENT_GREEN if enabled else MayaColors.ICON_DISABLED
            ui.Button(
                "●" if enabled else "○", width=18, height=20,
                clicked_fn=lambda p=path: self._vm.toggle_collection_enabled(p),
                style={"background_color": 0x00000000, "color": en_color}
            )
            
            # Collection name
            ui.Button(
                f"Collection: {name}",
                height=20,
                clicked_fn=lambda p=path: self._on_collection_clicked(p),
                style={"background_color": 0x00000000, "color": MayaColors.TEXT_PRIMARY, "font_size": 10}
            )
            
            ui.Spacer()
            
            # Member count
            ui.Label(f"({col.get('member_count', 0)})", width=30, 
                     style={"color": MayaColors.TEXT_SECONDARY, "font_size": 9})
            
            # Solo
            solo_color = MayaColors.ICON_SOLO if col.get("solo") else MayaColors.ICON_DISABLED
            ui.Button("S", width=18, height=18,
                      clicked_fn=lambda p=path: self._vm.toggle_collection_solo(p),
                      style={"background_color": 0x00000000, "color": solo_color, "font_size": 9})
            
            # Delete
            ui.Button("×", width=18, height=18,
                      clicked_fn=lambda p=path: self._on_delete_collection(p),
                      style={"background_color": 0x00000000, "color": MayaColors.ACCENT_RED})
            
            ui.Spacer(width=4)
    
    # =========================================================================
    # Right Panel: Property Editor + AOV Browser
    # =========================================================================
    
    def _build_property_editor_panel(self) -> None:
        """Build the property editor panel (like Maya's Property Editor - Render Setup)."""
        with ui.VStack(spacing=0):
            # Header
            with ui.HStack(height=26, style={"background_color": 0xFF383838}):
                ui.Spacer(width=8)
                ui.Label("Property Editor - Render Setup", style={"color": MayaColors.TEXT_PRIMARY, "font_size": 11})
                ui.Spacer()
            
            # Property content
            with ui.ScrollingFrame(height=200, style={"background_color": MayaColors.BG_DARK}):
                self._properties_container = ui.VStack(spacing=2)
                with self._properties_container:
                    self._build_properties_content()
            
            ui.Separator(height=1, style={"color": 0xFF404040})
            
            # AOV Browser (like Maya's Render Settings > AOVs)
            with ui.CollapsableFrame("AOV Browser - Create Override", height=220, collapsed=False,
                                      style={"background_color": 0xFF333333}):
                with ui.VStack(spacing=2):
                    self._build_aov_browser()
            
            ui.Separator(height=1, style={"color": 0xFF404040})
            
            # Collection controls
            with ui.CollapsableFrame("Collection Controls", height=150, collapsed=False,
                                      style={"background_color": 0xFF333333}):
                with ui.VStack(spacing=4):
                    self._build_collection_controls()
    
    def _build_properties_content(self) -> None:
        """Build the properties content based on what's selected."""
        # Check if AOV is selected
        if self._selected_aov_path:
            self._build_aov_properties()
            return
        
        # Check if collection is selected
        col_info = self._vm.get_selected_collection_info()
        if col_info:
            self._build_collection_properties(col_info)
            return
        
        # Check if layer is selected
        layer_info = self._vm.get_selected_layer_info()
        if layer_info:
            self._build_layer_properties(layer_info)
            return
        
        # Nothing selected
        with ui.VStack():
            ui.Spacer(height=30)
            with ui.HStack():
                ui.Spacer()
                ui.Label("Select an item to view properties", style={"color": MayaColors.TEXT_DISABLED})
                ui.Spacer()
    
    def _build_aov_properties(self) -> None:
        """Build AOV properties editor (like Maya's Absolute Override editor)."""
        from ..core.render_layer import get_layer_aov_node_info
        
        aov_info = get_layer_aov_node_info(self._selected_aov_path)
        if not aov_info:
            ui.Label("AOV not found", style={"color": MayaColors.ACCENT_RED})
            return
        
        with ui.VStack(spacing=4):
            ui.Spacer(height=8)
            
            # Header - "Absolute Override"
            with ui.HStack(height=24):
                ui.Spacer(width=8)
                ui.Label("Absolute Override:", width=100, style={"color": MayaColors.TEXT_SECONDARY})
                ui.Label(aov_info.get("source_type", ""), style={"color": MayaColors.ICON_AOV})
            
            ui.Separator(height=1, style={"color": 0xFF404040})
            
            # Path
            with ui.HStack(height=20):
                ui.Spacer(width=8)
                ui.Label("Path", width=60, style={"color": MayaColors.TEXT_SECONDARY, "font_size": 10})
                ui.Label(self._selected_aov_path, style={"color": MayaColors.TEXT_PRIMARY, "font_size": 10}, elided_text=True)
            
            ui.Separator(height=1, style={"color": 0xFF404040})
            
            # Name Override (重命名 - 关键功能!)
            with ui.HStack(height=26):
                ui.Spacer(width=8)
                ui.Label("Name", width=60, style={"color": MayaColors.TEXT_SECONDARY})
                self._aov_name_field = ui.StringField(height=22)
                self._aov_name_field.model.set_value(aov_info.get("name_override", "") or aov_info.get("display_name", ""))
                ui.Button("Rename", width=60, height=22, clicked_fn=self._on_rename_aov,
                          style={"background_color": MayaColors.ACCENT_BLUE})
            
            # Enabled
            with ui.HStack(height=24):
                ui.Spacer(width=8)
                ui.Label("Enabled", width=60, style={"color": MayaColors.TEXT_SECONDARY})
                enabled_cb = ui.CheckBox(height=20)
                enabled_cb.model.set_value(aov_info.get("enabled", True))
                enabled_cb.model.add_value_changed_fn(
                    lambda m: self._on_aov_enabled_changed(m.get_value_as_bool())
                )
            
            # Data Type (read-only)
            with ui.HStack(height=20):
                ui.Spacer(width=8)
                ui.Label("Data Type", width=60, style={"color": MayaColors.TEXT_SECONDARY, "font_size": 10})
                ui.Label(aov_info.get("data_type", ""), style={"color": MayaColors.TEXT_PRIMARY, "font_size": 10})
            
            # Driver
            with ui.HStack(height=24):
                ui.Spacer(width=8)
                ui.Label("Driver", width=60, style={"color": MayaColors.TEXT_SECONDARY})
                self._driver_combo = ui.ComboBox(0, "exr", "png", "tiff", "jpg", width=80, height=20)
                driver_map = {"exr": 0, "png": 1, "tiff": 2, "jpg": 3}
                self._driver_combo.model.get_item_value_model().set_value(
                    driver_map.get(aov_info.get("driver", "exr"), 0)
                )
            
            # Filter
            with ui.HStack(height=24):
                ui.Spacer(width=8)
                ui.Label("Filter", width=60, style={"color": MayaColors.TEXT_SECONDARY})
                self._filter_combo = ui.ComboBox(0, "gaussian", "box", "triangle", "closest", width=80, height=20)
    
    def _build_layer_properties(self, info: dict) -> None:
        """Build layer properties."""
        with ui.VStack(spacing=4):
            ui.Spacer(height=8)
            with ui.HStack(height=24):
                ui.Spacer(width=8)
                ui.Label("Layer:", width=50, style={"color": MayaColors.TEXT_SECONDARY})
                ui.Label(info["name"], style={"color": MayaColors.ACCENT_ORANGE, "font_size": 13})
            
            ui.Separator(height=1, style={"color": 0xFF404040})
            
            self._prop_row("Path", info["path"])
            self._prop_row("Visible", "Yes" if info["visible"] else "No")
            self._prop_row("Solo", "Yes" if info["solo"] else "No")
            self._prop_row("Renderable", "Yes" if info["renderable"] else "No")
    
    def _build_collection_properties(self, info: dict) -> None:
        """Build collection properties."""
        with ui.VStack(spacing=4):
            ui.Spacer(height=8)
            with ui.HStack(height=24):
                ui.Spacer(width=8)
                ui.Label("Collection:", width=70, style={"color": MayaColors.TEXT_SECONDARY})
                ui.Label(info["name"], style={"color": MayaColors.ACCENT_GREEN, "font_size": 13})
            
            ui.Separator(height=1, style={"color": 0xFF404040})
            
            self._prop_row("Path", info["path"])
            self._prop_row("Filter", info.get("filter", "all"))
            self._prop_row("Members", str(info.get("member_count", 0)))
    
    def _prop_row(self, label: str, value: str) -> None:
        with ui.HStack(height=18):
            ui.Spacer(width=8)
            ui.Label(label, width=70, style={"color": MayaColors.TEXT_SECONDARY, "font_size": 10})
            ui.Label(value, style={"color": MayaColors.TEXT_PRIMARY, "font_size": 10}, elided_text=True)
    
    def _build_aov_browser(self) -> None:
        """Build the AOV browser (like Maya's Render Settings > AOVs panel)."""
        with ui.VStack(spacing=2):
            ui.Spacer(height=4)
            
            # Instructions
            with ui.HStack(height=20):
                ui.Spacer(width=8)
                ui.Label("Select AOV, then click 'Create Override' to add to current layer",
                         style={"color": MayaColors.TEXT_SECONDARY, "font_size": 10})
            
            ui.Separator(height=1, style={"color": 0xFF404040})
            
            # AOV list
            with ui.ScrollingFrame(height=120, style={"background_color": MayaColors.BG_DARK}):
                self._aov_browser_container = ui.VStack(spacing=1)
                with self._aov_browser_container:
                    self._build_aov_list()
            
            # Create Override button (the key Maya feature!)
            with ui.HStack(height=28):
                ui.Spacer(width=8)
                ui.Button(
                    "Create Absolute Override for Current Layer",
                    height=26,
                    clicked_fn=self._on_create_aov_override,
                    style={"background_color": MayaColors.ACCENT_GREEN},
                    tooltip="Add selected AOV to current layer (like Maya's right-click menu)"
                )
                ui.Spacer(width=8)
            
            # Quick add standard AOVs
            with ui.HStack(height=24):
                ui.Spacer(width=8)
                ui.Button(
                    "Add Standard AOVs (Depth, Normal, Diffuse)",
                    height=22,
                    clicked_fn=self._on_add_standard_aovs,
                    tooltip="Add common AOVs to current layer"
                )
                ui.Spacer(width=8)
    
    def _build_aov_list(self) -> None:
        """Build the list of available AOVs."""
        aov_types = self._vm.get_available_aov_types_for_browser()
        
        if not aov_types:
            ui.Label("No AOV types available", style={"color": MayaColors.TEXT_DISABLED})
            return
        
        for aov in aov_types:
            aov_id = aov["id"]
            aov_name = aov["name"]
            is_added = aov.get("added", False)
            is_selected = getattr(self, '_selected_aov_type', None) == aov_id
            
            bg = MayaColors.BG_SELECTED if is_selected else (0xFF2A4A3A if is_added else MayaColors.BG_ITEM)
            
            with ui.HStack(height=20, style={"background_color": bg}):
                ui.Spacer(width=8)
                
                # Checkbox showing if added
                ui.Label("✓" if is_added else "○", width=16, 
                         style={"color": MayaColors.ACCENT_GREEN if is_added else MayaColors.TEXT_DISABLED})
                
                # AOV name (clickable)
                ui.Button(
                    aov_name,
                    height=18,
                    clicked_fn=lambda aid=aov_id: self._on_select_aov_type(aid),
                    style={"background_color": 0x00000000, "color": MayaColors.TEXT_PRIMARY, "font_size": 10}
                )
                
                ui.Spacer()
                
                if is_added:
                    ui.Label("[in layer]", width=55, style={"color": MayaColors.ACCENT_GREEN, "font_size": 9})
    
    def _build_collection_controls(self) -> None:
        """Build collection controls."""
        with ui.VStack(spacing=4):
            ui.Spacer(height=4)
            
            # New collection input
            with ui.HStack(height=24):
                ui.Spacer(width=8)
                ui.Label("Name:", width=40, style={"color": MayaColors.TEXT_SECONDARY})
                self._collection_name_field = ui.StringField(height=22)
                self._collection_name_field.model.set_value("Collection1")
                ui.Button("+", width=24, height=22, clicked_fn=self._on_new_collection,
                          style={"background_color": MayaColors.ACCENT_GREEN})
                ui.Spacer(width=8)
            
            # Add/Remove members
            with ui.HStack(height=24):
                ui.Spacer(width=8)
                ui.Button("+ Add Selection", height=22, clicked_fn=self._vm.add_selection_to_collection,
                          style={"background_color": MayaColors.ACCENT_GREEN})
                ui.Button("- Remove", height=22, clicked_fn=self._vm.remove_selection_from_collection)
                ui.Button("Clear", width=50, height=22, clicked_fn=self._vm.clear_collection_members,
                          style={"background_color": MayaColors.ACCENT_RED})
                ui.Spacer(width=8)
            
            # Override controls
            ui.Separator(height=1, style={"color": 0xFF404040})
            ui.Label("  Visibility Override:", style={"color": MayaColors.TEXT_SECONDARY, "font_size": 10})
            
            with ui.HStack(height=22):
                ui.Spacer(width=8)
                ui.Button("Show", width=60, height=20,
                          clicked_fn=lambda: self._vm.set_collection_property_override("visibility", True),
                          style={"background_color": MayaColors.ACCENT_GREEN})
                ui.Button("Hide", width=60, height=20,
                          clicked_fn=lambda: self._vm.set_collection_property_override("visibility", False),
                          style={"background_color": MayaColors.ACCENT_ORANGE})
                ui.Spacer()
    
    # =========================================================================
    # Event Handlers
    # =========================================================================
    
    def _on_new_layer(self) -> None:
        """Create a new layer."""
        # Generate unique name
        layers = self._vm.get_layers()
        idx = len(layers) + 1
        name = f"RenderLayer{idx}"
        self._vm.create_layer(name)
    
    def _on_layer_clicked(self, path: str) -> None:
        self._selected_aov_path = None  # Clear AOV selection
        self._vm.selected_layer_path = path
        # Auto expand when selected
        self._expanded_layers.add(path)
        self._expanded_aovs.add(f"{path}/AOVs")
    
    def _on_delete_layer(self, path: str) -> None:
        self._vm.selected_layer_path = path
        self._vm.delete_selected_layer()
    
    def _toggle_layer_expand(self, path: str) -> None:
        if path in self._expanded_layers:
            self._expanded_layers.remove(path)
        else:
            self._expanded_layers.add(path)
        self._refresh_all()
    
    def _toggle_aov_expand(self, path: str) -> None:
        if path in self._expanded_aovs:
            self._expanded_aovs.remove(path)
        else:
            self._expanded_aovs.add(path)
        self._refresh_all()
    
    def _on_aov_clicked(self, aov_path: str) -> None:
        """Select an AOV for property editing."""
        self._selected_aov_path = aov_path
        self._refresh_all()
    
    def _on_toggle_aov(self, aov_path: str) -> None:
        """Toggle AOV enabled state."""
        self._vm.toggle_layer_aov_node_enabled(aov_path)
    
    def _on_remove_aov(self, aov_type_id: str) -> None:
        """Remove AOV from current layer."""
        self._vm.remove_aov_from_selected_layer(aov_type_id)
        self._selected_aov_path = None
    
    def _on_select_aov_type(self, aov_id: str) -> None:
        """Select an AOV type in the browser."""
        self._selected_aov_type = aov_id
        self._refresh_aov_browser()
    
    def _on_create_aov_override(self) -> None:
        """Create AOV override for current layer (the Maya feature!)."""
        aov_type_id = getattr(self, '_selected_aov_type', None)
        if not aov_type_id:
            self._vm.log("[!] Please select an AOV type first")
            return
        
        if not self._vm.selected_layer_path:
            self._vm.log("[!] Please select a layer first")
            return
        
        # Create the AOV override
        self._vm.add_aov_to_selected_layer(aov_type_id)
        
        # Auto expand to show it
        layer_path = self._vm.selected_layer_path
        self._expanded_layers.add(layer_path)
        self._expanded_aovs.add(f"{layer_path}/AOVs")
    
    def _on_add_standard_aovs(self) -> None:
        """Add standard AOVs to current layer."""
        self._vm.create_standard_layer_aovs()
        
        # Auto expand
        if self._vm.selected_layer_path:
            layer_path = self._vm.selected_layer_path
            self._expanded_layers.add(layer_path)
            self._expanded_aovs.add(f"{layer_path}/AOVs")
    
    def _on_rename_aov(self) -> None:
        """Rename the selected AOV."""
        if not self._selected_aov_path:
            return
        new_name = self._aov_name_field.model.get_value_as_string()
        if new_name:
            self._vm.rename_layer_aov(self._selected_aov_path, new_name)
    
    def _on_aov_enabled_changed(self, enabled: bool) -> None:
        """AOV enabled state changed."""
        if not self._selected_aov_path:
            return
        from ..core.render_layer import set_layer_aov_property
        set_layer_aov_property(self._selected_aov_path, "enabled", enabled)
        self._vm._notify_data_changed()
    
    def _on_collection_clicked(self, path: str) -> None:
        self._selected_aov_path = None
        self._vm.selected_collection_path = path
    
    def _on_new_collection(self) -> None:
        name = self._collection_name_field.model.get_value_as_string()
        if name:
            self._vm.create_collection_in_layer(name)
    
    def _on_delete_collection(self, path: str) -> None:
        self._vm.selected_collection_path = path
        self._vm.delete_selected_collection()
    
    # =========================================================================
    # Refresh
    # =========================================================================
    
    def _refresh_all(self) -> None:
        if self._tree_container:
            self._tree_container.clear()
            with self._tree_container:
                self._build_tree()
        
        if self._properties_container:
            self._properties_container.clear()
            with self._properties_container:
                self._build_properties_content()
        
        self._refresh_aov_browser()
    
    def _refresh_aov_browser(self) -> None:
        if self._aov_browser_container:
            self._aov_browser_container.clear()
            with self._aov_browser_container:
                self._build_aov_list()
    
    # =========================================================================
    # Lifecycle
    # =========================================================================
    
    def dispose(self) -> None:
        self._vm.remove_data_changed_callback(self._refresh_all)
        self._tree_container = None
        self._properties_container = None
        self._aov_browser_container = None
        super().dispose()
