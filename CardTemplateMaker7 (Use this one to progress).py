"""
CardTemplateMaker7 — Visual card layout template designer.

Design card layout templates with positioned text/image fields, preview cards
with real data rendered via Pillow, and export as PNG/JPEG.
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, colorchooser
import json
import os
import uuid
from PIL import Image, ImageTk

import layout_renderer


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CARD_TYPES = [
    "Enemy Card", "NPC Card", "Boss Card", "Junk Card",
    "Document Card", "Location Card", "Quest Card",
    "Instance Card", "Transition Card",
]

FONT_STYLES = ["normal", "bold", "italic", "bold_italic"]
ALIGNMENTS = ["left", "center", "right"]
TARGET_STATES = ["full", "state1", "state2"]

# Common field keys per card type (for the dropdown helper)
COMMON_FIELDS = {
    "Enemy Card": [
        "Name", "Health", "Movement", "Melee Damage",
        "Projectile Damage", "Projectile Range",
        "Enemy Image File Path", "Background Image File Path",
    ],
    "NPC Card": [
        "Name", "Health", "Movement", "Melee Damage",
        "Projectile Damage", "Projectile Range",
        "Allegiance (Hostile, Neutral, Allied)", "Special Skill",
        "NPC Image File Path", "Background Image File Path",
    ],
    "Boss Card": [
        "Name", "Health", "Movement", "Melee Damage",
        "Projectile Damage", "Projectile Range",
        "Boss Image File Path", "Background Image File Path",
    ],
    "Junk Card": [
        "Name", "Description", "Raw Material Value",
        "Refined Material Value", "Metal Value", "Wood Value",
        "Junk Image File Path", "Background Image File Path",
    ],
    "Document Card": [
        "Name", "Description",
        "Document Image File Path", "Background Image File Path",
    ],
    "Location Card": [
        "Name", "Description",
        "Location Image File Path", "Background Image File Path",
    ],
    "Quest Card": [
        "Name", "Description", "Template_Text",
        "Quest Image File Path", "Background Image File Path",
    ],
    "Instance Card": [
        "Name", "Description",
        "Image_File_Path", "Background Image File Path",
    ],
    "Transition Card": [
        "Name", "Description",
        "Background Image File Path",
    ],
}

SYSTEM_FONTS = [
    "Arial", "Times New Roman", "Courier New", "Verdana",
    "Georgia", "Trebuchet MS", "Impact", "Comic Sans MS",
    "Tahoma", "Palatino Linotype", "Lucida Console",
    "Segoe UI", "Calibri", "Cambria", "Consolas",
]


# ═══════════════════════════════════════════════════════════════════════════
# Main Application
# ═══════════════════════════════════════════════════════════════════════════

class CardTemplateMaker:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Card Template Maker")
        self.root.state("zoomed")
        self.root.minsize(1024, 700)

        self.current_screen = None
        self._tk_images = []  # prevent GC of PhotoImages

        self.show_screen(MainMenuScreen)

    # -- Screen navigation --------------------------------------------------

    def show_screen(self, screen_class, **kwargs):
        if self.current_screen is not None:
            self.current_screen.destroy()
        self._tk_images.clear()
        self.current_screen = screen_class(self, self.root, **kwargs)

    def keep_image(self, tk_img):
        """Keep a reference to a PhotoImage to prevent garbage collection."""
        self._tk_images.append(tk_img)

    def run(self):
        os.makedirs("layouts", exist_ok=True)
        self.root.mainloop()


# ═══════════════════════════════════════════════════════════════════════════
# Base Screen
# ═══════════════════════════════════════════════════════════════════════════

class BaseScreen:
    def __init__(self, app, root):
        self.app = app
        self.root = root
        self.frame = tk.Frame(root)
        self.frame.pack(fill=tk.BOTH, expand=True)

    def destroy(self):
        self.frame.destroy()


# ═══════════════════════════════════════════════════════════════════════════
# Main Menu Screen
# ═══════════════════════════════════════════════════════════════════════════

class MainMenuScreen(BaseScreen):
    def __init__(self, app, root):
        super().__init__(app, root)

        # Center everything
        container = tk.Frame(self.frame)
        container.place(relx=0.5, rely=0.5, anchor="center")

        tk.Label(container, text="Card Template Maker",
                 font=("Arial", 32, "bold")).pack(pady=(0, 40))

        btn_style = {"width": 25, "height": 2, "font": ("Arial", 14)}

        tk.Button(container, text="Design Layout",
                  command=self._design_layout, **btn_style).pack(pady=8)
        tk.Button(container, text="Preview Card",
                  command=self._preview_card, **btn_style).pack(pady=8)
        tk.Button(container, text="Manage Layouts",
                  command=self._manage_layouts, **btn_style).pack(pady=8)
        tk.Button(container, text="Quit",
                  command=self.root.quit, **btn_style).pack(pady=8)

    def _design_layout(self):
        self.app.show_screen(LayoutDesignerScreen)

    def _preview_card(self):
        self.app.show_screen(CardPreviewScreen)

    def _manage_layouts(self):
        self.app.show_screen(TemplateListScreen)


# ═══════════════════════════════════════════════════════════════════════════
# Layout Designer Screen
# ═══════════════════════════════════════════════════════════════════════════

class LayoutDesignerScreen(BaseScreen):
    def __init__(self, app, root, load_template=None):
        super().__init__(app, root)

        # Template data
        self.elements = []  # list of element dicts
        self.selected_idx = None
        self._drag_data = None

        # --- Three-column layout ---
        self.frame.columnconfigure(1, weight=1)
        self.frame.rowconfigure(0, weight=1)

        # Left panel (scrollable)
        left_outer = tk.Frame(self.frame, width=220)
        left_outer.grid(row=0, column=0, sticky="ns")
        left_outer.grid_propagate(False)

        left_canvas = tk.Canvas(left_outer, width=220)
        left_scroll = ttk.Scrollbar(left_outer, orient="vertical", command=left_canvas.yview)
        self.left_panel = tk.Frame(left_canvas)
        self.left_panel.bind("<Configure>",
                             lambda e: left_canvas.configure(scrollregion=left_canvas.bbox("all")))
        left_canvas.create_window((0, 0), window=self.left_panel, anchor="nw")
        left_canvas.configure(yscrollcommand=left_scroll.set)
        left_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        left_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # Center (canvas)
        center = tk.Frame(self.frame)
        center.grid(row=0, column=1, sticky="nsew")
        center.rowconfigure(0, weight=1)
        center.columnconfigure(0, weight=1)
        self.canvas = tk.Canvas(center, bg="#555555")
        self.canvas.grid(row=0, column=0, sticky="nsew")

        # Right panel (scrollable)
        right_outer = tk.Frame(self.frame, width=260)
        right_outer.grid(row=0, column=2, sticky="ns")
        right_outer.grid_propagate(False)

        right_canvas = tk.Canvas(right_outer, width=260)
        right_scroll = ttk.Scrollbar(right_outer, orient="vertical", command=right_canvas.yview)
        self.right_panel = tk.Frame(right_canvas)
        self.right_panel.bind("<Configure>",
                              lambda e: right_canvas.configure(scrollregion=right_canvas.bbox("all")))
        right_canvas.create_window((0, 0), window=self.right_panel, anchor="nw")
        right_canvas.configure(yscrollcommand=right_scroll.set)
        right_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        right_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # Status bar
        self.status_var = tk.StringVar(value="Ready")
        status_bar = tk.Label(self.frame, textvariable=self.status_var,
                              anchor="w", relief="sunken", bd=1)
        status_bar.grid(row=1, column=0, columnspan=3, sticky="ew")

        # Build left panel controls
        self._build_left_panel()

        # Canvas events
        self.canvas.bind("<Button-1>", self._on_canvas_click)
        self.canvas.bind("<B1-Motion>", self._on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_canvas_release)
        self.canvas.bind("<Configure>", lambda e: self._redraw_canvas())

        # Load template if provided
        if load_template:
            self._populate_from_template(load_template)

    # -- Left panel ---------------------------------------------------------

    def _build_left_panel(self):
        p = self.left_panel
        pad = {"padx": 6, "pady": 2, "sticky": "ew"}

        tk.Label(p, text="Template Metadata", font=("Arial", 11, "bold")).grid(
            row=0, column=0, columnspan=2, **{k: v for k, v in pad.items() if k != "sticky"}, sticky="w")

        # Template name
        tk.Label(p, text="Name:").grid(row=1, column=0, **pad)
        self.name_var = tk.StringVar(value="New Template")
        tk.Entry(p, textvariable=self.name_var, width=20).grid(row=1, column=1, **pad)

        # Target type
        tk.Label(p, text="Target Type:").grid(row=2, column=0, **pad)
        self.type_var = tk.StringVar(value=CARD_TYPES[0])
        ttk.OptionMenu(p, self.type_var, CARD_TYPES[0], *CARD_TYPES).grid(row=2, column=1, **pad)

        # Target subclass
        tk.Label(p, text="Subclass:").grid(row=3, column=0, **pad)
        self.subclass_var = tk.StringVar()
        tk.Entry(p, textvariable=self.subclass_var, width=20).grid(row=3, column=1, **pad)

        # Target state
        tk.Label(p, text="State:").grid(row=4, column=0, **pad)
        self.state_var = tk.StringVar(value="full")
        state_menu = ttk.OptionMenu(p, self.state_var, "full", *TARGET_STATES,
                                    command=self._on_state_change)
        state_menu.grid(row=4, column=1, **pad)

        # Dimensions
        tk.Label(p, text="Width:").grid(row=5, column=0, **pad)
        self.width_var = tk.IntVar(value=750)
        tk.Spinbox(p, from_=100, to=3000, textvariable=self.width_var,
                   width=8).grid(row=5, column=1, **pad)

        tk.Label(p, text="Height:").grid(row=6, column=0, **pad)
        self.height_var = tk.IntVar(value=1050)
        tk.Spinbox(p, from_=100, to=4200, textvariable=self.height_var,
                   width=8).grid(row=6, column=1, **pad)

        # Colors
        tk.Label(p, text="Background:").grid(row=7, column=0, **pad)
        self.bg_color_var = tk.StringVar(value="#1a1a2e")
        self.bg_color_btn = tk.Button(p, textvariable=self.bg_color_var, width=12,
                                      command=lambda: self._pick_color(self.bg_color_var, self.bg_color_btn))
        self.bg_color_btn.grid(row=7, column=1, **pad)
        self._update_color_btn(self.bg_color_btn, self.bg_color_var.get())

        tk.Label(p, text="Border:").grid(row=8, column=0, **pad)
        self.border_color_var = tk.StringVar(value="#3a3a5c")
        self.border_color_btn = tk.Button(p, textvariable=self.border_color_var, width=12,
                                          command=lambda: self._pick_color(self.border_color_var, self.border_color_btn))
        self.border_color_btn.grid(row=8, column=1, **pad)
        self._update_color_btn(self.border_color_btn, self.border_color_var.get())

        tk.Label(p, text="Border Width:").grid(row=9, column=0, **pad)
        self.border_width_var = tk.IntVar(value=2)
        tk.Spinbox(p, from_=0, to=20, textvariable=self.border_width_var,
                   width=8).grid(row=9, column=1, **pad)

        # Separator
        ttk.Separator(p, orient="horizontal").grid(
            row=10, column=0, columnspan=2, sticky="ew", pady=8)

        # Add element buttons
        tk.Label(p, text="Add Elements", font=("Arial", 11, "bold")).grid(
            row=11, column=0, columnspan=2, sticky="w", padx=6)

        tk.Button(p, text="Add Text Field", command=self._add_text_element).grid(
            row=12, column=0, columnspan=2, **pad)
        tk.Button(p, text="Add Image Field", command=self._add_image_element).grid(
            row=13, column=0, columnspan=2, **pad)
        tk.Button(p, text="Add Static Label", command=self._add_static_text_element).grid(
            row=14, column=0, columnspan=2, **pad)

        # Separator
        ttk.Separator(p, orient="horizontal").grid(
            row=15, column=0, columnspan=2, sticky="ew", pady=8)

        # Elements list
        tk.Label(p, text="Elements", font=("Arial", 11, "bold")).grid(
            row=16, column=0, columnspan=2, sticky="w", padx=6)

        self.elements_listbox = tk.Listbox(p, height=10, width=28)
        self.elements_listbox.grid(row=17, column=0, columnspan=2, padx=6, pady=2, sticky="ew")
        self.elements_listbox.bind("<<ListboxSelect>>", self._on_listbox_select)

        tk.Button(p, text="Delete Selected", command=self._delete_selected).grid(
            row=18, column=0, columnspan=2, **pad)

        tk.Button(p, text="Move Up", command=self._move_element_up).grid(
            row=19, column=0, **pad)
        tk.Button(p, text="Move Down", command=self._move_element_down).grid(
            row=19, column=1, **pad)

        # Separator
        ttk.Separator(p, orient="horizontal").grid(
            row=20, column=0, columnspan=2, sticky="ew", pady=8)

        # File operations
        tk.Button(p, text="Save Template", command=self._save_template).grid(
            row=21, column=0, columnspan=2, **pad)
        tk.Button(p, text="Load Template", command=self._load_template).grid(
            row=22, column=0, columnspan=2, **pad)

        ttk.Separator(p, orient="horizontal").grid(
            row=23, column=0, columnspan=2, sticky="ew", pady=8)

        tk.Button(p, text="Back to Menu", command=self._back).grid(
            row=24, column=0, columnspan=2, **pad)

    # -- State change handler -----------------------------------------------

    def _on_state_change(self, *_args):
        state = self.state_var.get()
        if state in ("state1", "state2"):
            self.height_var.set(525)
        else:
            self.height_var.set(1050)
        self._redraw_canvas()

    # -- Color helpers ------------------------------------------------------

    def _pick_color(self, var, btn):
        color = colorchooser.askcolor(initialcolor=var.get())
        if color[1]:
            var.set(color[1])
            self._update_color_btn(btn, color[1])
            self._redraw_canvas()

    @staticmethod
    def _update_color_btn(btn, hex_color):
        try:
            # Compute contrasting text color
            r, g, b = int(hex_color[1:3], 16), int(hex_color[3:5], 16), int(hex_color[5:7], 16)
            fg = "#000000" if (r * 0.299 + g * 0.587 + b * 0.114) > 128 else "#ffffff"
            btn.configure(bg=hex_color, fg=fg)
        except (ValueError, tk.TclError):
            pass

    # -- Element creation ---------------------------------------------------

    def _add_text_element(self):
        card_w = self.width_var.get()
        elem = {
            "id": f"text_{uuid.uuid4().hex[:8]}",
            "type": "text",
            "field_key": "Name",
            "label_prefix": "",
            "x": card_w // 2,
            "y": 60,
            "font_family": "Arial",
            "font_size": 20,
            "font_style": "normal",
            "font_color": "#ffffff",
            "alignment": "center",
            "max_width": card_w - 50,
        }
        self.elements.append(elem)
        self._refresh_elements_list()
        self.selected_idx = len(self.elements) - 1
        self.elements_listbox.selection_clear(0, tk.END)
        self.elements_listbox.selection_set(self.selected_idx)
        self._show_properties()
        self._redraw_canvas()

    def _add_image_element(self):
        elem = {
            "id": f"img_{uuid.uuid4().hex[:8]}",
            "type": "image",
            "field_key": "Image File Path",
            "x": 175,
            "y": 150,
            "width": 400,
            "height": 400,
        }
        self.elements.append(elem)
        self._refresh_elements_list()
        self.selected_idx = len(self.elements) - 1
        self.elements_listbox.selection_clear(0, tk.END)
        self.elements_listbox.selection_set(self.selected_idx)
        self._show_properties()
        self._redraw_canvas()

    def _add_static_text_element(self):
        card_w = self.width_var.get()
        elem = {
            "id": f"label_{uuid.uuid4().hex[:8]}",
            "type": "static_text",
            "text": "Label",
            "x": card_w // 2,
            "y": 30,
            "font_family": "Arial",
            "font_size": 16,
            "font_style": "normal",
            "font_color": "#cccccc",
            "alignment": "center",
            "max_width": card_w - 50,
        }
        self.elements.append(elem)
        self._refresh_elements_list()
        self.selected_idx = len(self.elements) - 1
        self.elements_listbox.selection_clear(0, tk.END)
        self.elements_listbox.selection_set(self.selected_idx)
        self._show_properties()
        self._redraw_canvas()

    def _delete_selected(self):
        if self.selected_idx is not None and 0 <= self.selected_idx < len(self.elements):
            del self.elements[self.selected_idx]
            self.selected_idx = None
            self._refresh_elements_list()
            self._clear_properties()
            self._redraw_canvas()

    def _move_element_up(self):
        if self.selected_idx is not None and self.selected_idx > 0:
            i = self.selected_idx
            self.elements[i - 1], self.elements[i] = self.elements[i], self.elements[i - 1]
            self.selected_idx = i - 1
            self._refresh_elements_list()
            self.elements_listbox.selection_set(self.selected_idx)
            self._redraw_canvas()

    def _move_element_down(self):
        if self.selected_idx is not None and self.selected_idx < len(self.elements) - 1:
            i = self.selected_idx
            self.elements[i + 1], self.elements[i] = self.elements[i], self.elements[i + 1]
            self.selected_idx = i + 1
            self._refresh_elements_list()
            self.elements_listbox.selection_set(self.selected_idx)
            self._redraw_canvas()

    # -- Elements list ------------------------------------------------------

    def _refresh_elements_list(self):
        self.elements_listbox.delete(0, tk.END)
        for elem in self.elements:
            etype = elem["type"]
            if etype == "text":
                label = f"[Text] {elem.get('field_key', '?')}"
            elif etype == "image":
                label = f"[Image] {elem.get('field_key', '?')}"
            elif etype == "static_text":
                label = f"[Label] {elem.get('text', '?')[:20]}"
            else:
                label = f"[{etype}]"
            self.elements_listbox.insert(tk.END, label)

    def _on_listbox_select(self, _event):
        sel = self.elements_listbox.curselection()
        if sel:
            self.selected_idx = sel[0]
            self._show_properties()
            self._redraw_canvas()

    # -- Properties panel ---------------------------------------------------

    def _clear_properties(self):
        for w in self.right_panel.winfo_children():
            w.destroy()

    def _show_properties(self):
        self._clear_properties()
        if self.selected_idx is None or self.selected_idx >= len(self.elements):
            return

        elem = self.elements[self.selected_idx]
        p = self.right_panel
        pad = {"padx": 6, "pady": 2, "sticky": "ew"}

        tk.Label(p, text="Element Properties", font=("Arial", 11, "bold")).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=6, pady=4)

        tk.Label(p, text=f"Type: {elem['type']}").grid(row=1, column=0, columnspan=2, **pad)

        row = 2
        self._prop_vars = {}

        # Position
        tk.Label(p, text="X:").grid(row=row, column=0, **pad)
        xvar = tk.IntVar(value=elem.get("x", 0))
        tk.Spinbox(p, from_=0, to=5000, textvariable=xvar, width=8).grid(row=row, column=1, **pad)
        self._prop_vars["x"] = xvar
        row += 1

        tk.Label(p, text="Y:").grid(row=row, column=0, **pad)
        yvar = tk.IntVar(value=elem.get("y", 0))
        tk.Spinbox(p, from_=0, to=5000, textvariable=yvar, width=8).grid(row=row, column=1, **pad)
        self._prop_vars["y"] = yvar
        row += 1

        if elem["type"] in ("text", "static_text"):
            # Field key (for text only)
            if elem["type"] == "text":
                tk.Label(p, text="Field Key:").grid(row=row, column=0, **pad)
                fk_var = tk.StringVar(value=elem.get("field_key", ""))
                fk_entry = tk.Entry(p, textvariable=fk_var, width=20)
                fk_entry.grid(row=row, column=1, **pad)
                self._prop_vars["field_key"] = fk_var
                row += 1

                # Common fields dropdown
                tk.Label(p, text="Common:").grid(row=row, column=0, **pad)
                current_type = self.type_var.get()
                fields = COMMON_FIELDS.get(current_type, ["Name"])
                fields_var = tk.StringVar()
                fields_menu = ttk.OptionMenu(
                    p, fields_var, "", *fields,
                    command=lambda v: fk_var.set(v))
                fields_menu.grid(row=row, column=1, **pad)
                row += 1

            # Label prefix
            tk.Label(p, text="Label Prefix:").grid(row=row, column=0, **pad)
            lp_var = tk.StringVar(value=elem.get("label_prefix", ""))
            tk.Entry(p, textvariable=lp_var, width=20).grid(row=row, column=1, **pad)
            self._prop_vars["label_prefix"] = lp_var
            row += 1

            # Static text content
            if elem["type"] == "static_text":
                tk.Label(p, text="Text:").grid(row=row, column=0, **pad)
                txt_var = tk.StringVar(value=elem.get("text", ""))
                tk.Entry(p, textvariable=txt_var, width=20).grid(row=row, column=1, **pad)
                self._prop_vars["text"] = txt_var
                row += 1

            # Font family
            tk.Label(p, text="Font:").grid(row=row, column=0, **pad)
            ff_var = tk.StringVar(value=elem.get("font_family", "Arial"))
            ttk.OptionMenu(p, ff_var, elem.get("font_family", "Arial"),
                           *SYSTEM_FONTS).grid(row=row, column=1, **pad)
            self._prop_vars["font_family"] = ff_var
            row += 1

            # Font size
            tk.Label(p, text="Size:").grid(row=row, column=0, **pad)
            fs_var = tk.IntVar(value=elem.get("font_size", 16))
            tk.Spinbox(p, from_=8, to=72, textvariable=fs_var,
                       width=8).grid(row=row, column=1, **pad)
            self._prop_vars["font_size"] = fs_var
            row += 1

            # Font style
            tk.Label(p, text="Style:").grid(row=row, column=0, **pad)
            fst_var = tk.StringVar(value=elem.get("font_style", "normal"))
            ttk.OptionMenu(p, fst_var, elem.get("font_style", "normal"),
                           *FONT_STYLES).grid(row=row, column=1, **pad)
            self._prop_vars["font_style"] = fst_var
            row += 1

            # Font color
            tk.Label(p, text="Color:").grid(row=row, column=0, **pad)
            fc_var = tk.StringVar(value=elem.get("font_color", "#ffffff"))
            fc_btn = tk.Button(p, textvariable=fc_var, width=12,
                               command=lambda: self._pick_prop_color(fc_var, fc_btn))
            fc_btn.grid(row=row, column=1, **pad)
            self._update_color_btn(fc_btn, fc_var.get())
            self._prop_vars["font_color"] = fc_var
            row += 1

            # Alignment
            tk.Label(p, text="Align:").grid(row=row, column=0, **pad)
            al_var = tk.StringVar(value=elem.get("alignment", "left"))
            ttk.OptionMenu(p, al_var, elem.get("alignment", "left"),
                           *ALIGNMENTS).grid(row=row, column=1, **pad)
            self._prop_vars["alignment"] = al_var
            row += 1

            # Max width
            tk.Label(p, text="Max Width:").grid(row=row, column=0, **pad)
            mw_var = tk.IntVar(value=elem.get("max_width", 700))
            tk.Spinbox(p, from_=50, to=3000, textvariable=mw_var,
                       width=8).grid(row=row, column=1, **pad)
            self._prop_vars["max_width"] = mw_var
            row += 1

        elif elem["type"] == "image":
            # Field key
            tk.Label(p, text="Field Key:").grid(row=row, column=0, **pad)
            fk_var = tk.StringVar(value=elem.get("field_key", ""))
            tk.Entry(p, textvariable=fk_var, width=20).grid(row=row, column=1, **pad)
            self._prop_vars["field_key"] = fk_var
            row += 1

            # Width / Height
            tk.Label(p, text="Width:").grid(row=row, column=0, **pad)
            iw_var = tk.IntVar(value=elem.get("width", 400))
            tk.Spinbox(p, from_=10, to=3000, textvariable=iw_var,
                       width=8).grid(row=row, column=1, **pad)
            self._prop_vars["width"] = iw_var
            row += 1

            tk.Label(p, text="Height:").grid(row=row, column=0, **pad)
            ih_var = tk.IntVar(value=elem.get("height", 400))
            tk.Spinbox(p, from_=10, to=4200, textvariable=ih_var,
                       width=8).grid(row=row, column=1, **pad)
            self._prop_vars["height"] = ih_var
            row += 1

        # Apply button
        ttk.Separator(p, orient="horizontal").grid(
            row=row, column=0, columnspan=2, sticky="ew", pady=6)
        row += 1

        tk.Button(p, text="Apply Changes", font=("Arial", 10, "bold"),
                  command=self._apply_properties).grid(
            row=row, column=0, columnspan=2, **pad)

    def _pick_prop_color(self, var, btn):
        color = colorchooser.askcolor(initialcolor=var.get())
        if color[1]:
            var.set(color[1])
            self._update_color_btn(btn, color[1])

    def _apply_properties(self):
        if self.selected_idx is None or self.selected_idx >= len(self.elements):
            return
        elem = self.elements[self.selected_idx]
        for key, var in self._prop_vars.items():
            val = var.get()
            elem[key] = val
        self._refresh_elements_list()
        if self.selected_idx is not None:
            self.elements_listbox.selection_set(self.selected_idx)
        self._redraw_canvas()
        self.status_var.set("Properties applied")

    # -- Canvas drawing -----------------------------------------------------

    def _get_scale(self):
        """Return scale factor to fit the card into the canvas area."""
        cw = self.canvas.winfo_width() or 800
        ch = self.canvas.winfo_height() or 600
        card_w = self.width_var.get()
        card_h = self.height_var.get()
        margin = 40
        sx = (cw - margin * 2) / card_w
        sy = (ch - margin * 2) / card_h
        return min(sx, sy, 1.0)  # don't upscale

    def _redraw_canvas(self):
        self.canvas.delete("all")
        scale = self._get_scale()
        card_w = self.width_var.get()
        card_h = self.height_var.get()

        # Centered offset
        cw = self.canvas.winfo_width() or 800
        ch = self.canvas.winfo_height() or 600
        ox = (cw - card_w * scale) / 2
        oy = (ch - card_h * scale) / 2
        self._canvas_offset = (ox, oy)
        self._canvas_scale = scale

        # Card background
        self.canvas.create_rectangle(
            ox, oy, ox + card_w * scale, oy + card_h * scale,
            fill=self.bg_color_var.get(), outline=self.border_color_var.get(),
            width=self.border_width_var.get())

        # Draw elements
        for i, elem in enumerate(self.elements):
            is_selected = (i == self.selected_idx)
            self._draw_element(elem, ox, oy, scale, is_selected)

    def _draw_element(self, elem, ox, oy, scale, is_selected):
        x = ox + elem.get("x", 0) * scale
        y = oy + elem.get("y", 0) * scale
        etype = elem["type"]

        if etype in ("text", "static_text"):
            if etype == "text":
                display = f"[{elem.get('field_key', '?')}]"
                if elem.get("label_prefix"):
                    display = elem["label_prefix"] + display
            else:
                display = elem.get("text", "Label")

            font_size = max(8, int(elem.get("font_size", 16) * scale))
            font_style = elem.get("font_style", "normal")
            tk_style = ""
            if "bold" in font_style:
                tk_style += "bold "
            if "italic" in font_style:
                tk_style += "italic"
            tk_font = (elem.get("font_family", "Arial"), font_size, tk_style.strip() or "normal")

            alignment = elem.get("alignment", "left")
            anchor = "w" if alignment == "left" else ("e" if alignment == "right" else "n")

            tag = f"elem_{id(elem)}"
            self.canvas.create_text(
                x, y, text=display, font=tk_font,
                fill=elem.get("font_color", "#ffffff"),
                anchor=anchor, tags=(tag,))

            if is_selected:
                bbox = self.canvas.bbox(tag)
                if bbox:
                    self.canvas.create_rectangle(
                        bbox[0] - 2, bbox[1] - 2, bbox[2] + 2, bbox[3] + 2,
                        outline="#00ff00", dash=(4, 2), width=2)

        elif etype == "image":
            w = elem.get("width", 400) * scale
            h = elem.get("height", 400) * scale
            outline_color = "#00ff00" if is_selected else "#888888"
            dash = (4, 2) if is_selected else ()
            self.canvas.create_rectangle(
                x, y, x + w, y + h,
                outline=outline_color, dash=dash, width=2)
            self.canvas.create_text(
                x + w / 2, y + h / 2,
                text=f"[IMG: {elem.get('field_key', '?')}]",
                fill="#aaaaaa", font=("Arial", max(8, int(12 * scale))))

    # -- Canvas interaction -------------------------------------------------

    def _canvas_to_card(self, cx, cy):
        """Convert canvas coordinates to card coordinates."""
        ox, oy = self._canvas_offset
        scale = self._canvas_scale
        return (cx - ox) / scale, (cy - oy) / scale

    def _find_element_at(self, cx, cy):
        """Find the topmost element at canvas position (cx, cy)."""
        card_x, card_y = self._canvas_to_card(cx, cy)
        scale = self._canvas_scale

        # Search in reverse order (topmost = last drawn)
        for i in range(len(self.elements) - 1, -1, -1):
            elem = self.elements[i]
            ex = elem.get("x", 0)
            ey = elem.get("y", 0)

            if elem["type"] in ("text", "static_text"):
                # Approximate hit area for text
                fs = elem.get("font_size", 16)
                mw = elem.get("max_width", 200)
                alignment = elem.get("alignment", "left")
                if alignment == "center":
                    hit_x1 = ex - mw / 2
                    hit_x2 = ex + mw / 2
                elif alignment == "right":
                    hit_x1 = ex - mw
                    hit_x2 = ex
                else:
                    hit_x1 = ex
                    hit_x2 = ex + mw
                hit_y1 = ey - fs / 2
                hit_y2 = ey + fs * 1.5

                if hit_x1 <= card_x <= hit_x2 and hit_y1 <= card_y <= hit_y2:
                    return i

            elif elem["type"] == "image":
                w = elem.get("width", 400)
                h = elem.get("height", 400)
                if ex <= card_x <= ex + w and ey <= card_y <= ey + h:
                    return i

        return None

    def _on_canvas_click(self, event):
        idx = self._find_element_at(event.x, event.y)
        if idx is not None:
            self.selected_idx = idx
            self.elements_listbox.selection_clear(0, tk.END)
            self.elements_listbox.selection_set(idx)
            card_x, card_y = self._canvas_to_card(event.x, event.y)
            elem = self.elements[idx]
            self._drag_data = {
                "offset_x": card_x - elem.get("x", 0),
                "offset_y": card_y - elem.get("y", 0),
            }
            self._show_properties()
        else:
            self.selected_idx = None
            self.elements_listbox.selection_clear(0, tk.END)
            self._drag_data = None
            self._clear_properties()
        self._redraw_canvas()

    def _on_canvas_drag(self, event):
        if self._drag_data is None or self.selected_idx is None:
            return
        card_x, card_y = self._canvas_to_card(event.x, event.y)
        elem = self.elements[self.selected_idx]
        elem["x"] = max(0, int(card_x - self._drag_data["offset_x"]))
        elem["y"] = max(0, int(card_y - self._drag_data["offset_y"]))
        self._redraw_canvas()
        # Update position spinboxes if properties shown
        if hasattr(self, "_prop_vars"):
            if "x" in self._prop_vars:
                self._prop_vars["x"].set(elem["x"])
            if "y" in self._prop_vars:
                self._prop_vars["y"].set(elem["y"])

    def _on_canvas_release(self, event):
        self._drag_data = None

    # -- Save / Load --------------------------------------------------------

    def _build_template_dict(self):
        subclass = self.subclass_var.get().strip() or None
        return {
            "template_name": self.name_var.get().strip(),
            "target_type": self.type_var.get(),
            "target_subclass": subclass,
            "target_state": self.state_var.get(),
            "card_width": self.width_var.get(),
            "card_height": self.height_var.get(),
            "background_color": self.bg_color_var.get(),
            "border_color": self.border_color_var.get(),
            "border_width": self.border_width_var.get(),
            "elements": self.elements,
        }

    def _save_template(self):
        name = self.name_var.get().strip()
        if not name:
            messagebox.showerror("Error", "Template name is required.")
            return

        template = self._build_template_dict()
        filename = name.replace(" ", "_").lower() + ".json"
        filepath = os.path.join("layouts", filename)

        if os.path.exists(filepath):
            if not messagebox.askyesno("Overwrite?",
                                       f"'{filename}' already exists. Overwrite?"):
                return

        try:
            os.makedirs("layouts", exist_ok=True)
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(template, f, indent=2)
            self.status_var.set(f"Saved: {filepath}")
            messagebox.showinfo("Saved", f"Template saved to {filepath}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save: {e}")

    def _load_template(self):
        filepath = filedialog.askopenfilename(
            initialdir="layouts",
            filetypes=[("JSON files", "*.json")],
            title="Load Template",
        )
        if not filepath:
            return
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                template = json.load(f)
            self._populate_from_template(template)
            self.status_var.set(f"Loaded: {filepath}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load: {e}")

    def _populate_from_template(self, template):
        self.name_var.set(template.get("template_name", "Untitled"))
        self.type_var.set(template.get("target_type", CARD_TYPES[0]))
        self.subclass_var.set(template.get("target_subclass", "") or "")
        self.state_var.set(template.get("target_state", "full"))
        self.width_var.set(template.get("card_width", 750))
        self.height_var.set(template.get("card_height", 1050))
        self.bg_color_var.set(template.get("background_color", "#1a1a2e"))
        self.border_color_var.set(template.get("border_color", "#3a3a5c"))
        self.border_width_var.set(template.get("border_width", 2))
        self._update_color_btn(self.bg_color_btn, self.bg_color_var.get())
        self._update_color_btn(self.border_color_btn, self.border_color_var.get())
        self.elements = list(template.get("elements", []))
        self.selected_idx = None
        self._refresh_elements_list()
        self._clear_properties()
        self._redraw_canvas()

    # -- Navigation ---------------------------------------------------------

    def _back(self):
        self.app.show_screen(MainMenuScreen)


# ═══════════════════════════════════════════════════════════════════════════
# Card Preview Screen
# ═══════════════════════════════════════════════════════════════════════════

class CardPreviewScreen(BaseScreen):
    def __init__(self, app, root):
        super().__init__(app, root)

        self.card_data = None
        self.rendered_image = None  # PIL Image
        self.matched_template = None
        self.all_templates = layout_renderer.load_all_templates("layouts")

        # Two-column layout
        self.frame.columnconfigure(1, weight=1)
        self.frame.rowconfigure(0, weight=1)

        # Left panel
        left = tk.Frame(self.frame, width=280)
        left.grid(row=0, column=0, sticky="ns", padx=5, pady=5)
        left.grid_propagate(False)
        self.left = left

        # Center (preview)
        center = tk.Frame(self.frame)
        center.grid(row=0, column=1, sticky="nsew", padx=5, pady=5)
        center.rowconfigure(0, weight=1)
        center.columnconfigure(0, weight=1)
        self.preview_canvas = tk.Canvas(center, bg="#444444")
        self.preview_canvas.grid(row=0, column=0, sticky="nsew")
        self.preview_canvas.bind("<Configure>", lambda e: self._show_preview())

        # Build left panel
        self._build_left_panel()

    def _build_left_panel(self):
        p = self.left

        tk.Label(p, text="Card Preview", font=("Arial", 14, "bold")).pack(pady=(10, 15))

        tk.Button(p, text="Import Card", command=self._import_card,
                  width=22, height=2).pack(pady=5)

        ttk.Separator(p, orient="horizontal").pack(fill="x", pady=10)

        # Card info
        self.info_var = tk.StringVar(value="No card loaded")
        tk.Label(p, textvariable=self.info_var, justify="left",
                 wraplength=250, anchor="w").pack(padx=5, fill="x")

        ttk.Separator(p, orient="horizontal").pack(fill="x", pady=10)

        # Template match
        tk.Label(p, text="Template Match:", font=("Arial", 10, "bold")).pack(padx=5, anchor="w")
        self.match_var = tk.StringVar(value="(none)")
        tk.Label(p, textvariable=self.match_var, justify="left",
                 wraplength=250, anchor="w", fg="#0066cc").pack(padx=5, fill="x")

        ttk.Separator(p, orient="horizontal").pack(fill="x", pady=10)

        # Override template dropdown
        tk.Label(p, text="Override Template:", font=("Arial", 10, "bold")).pack(padx=5, anchor="w")
        self.override_var = tk.StringVar(value="(auto)")
        self.override_menu = ttk.OptionMenu(p, self.override_var, "(auto)")
        self.override_menu.pack(padx=5, fill="x", pady=2)

        tk.Button(p, text="Re-render with Override", command=self._render_override,
                  width=22).pack(pady=5)

        ttk.Separator(p, orient="horizontal").pack(fill="x", pady=10)

        # Export
        tk.Button(p, text="Export PNG", command=lambda: self._export("png"),
                  width=22).pack(pady=3)
        tk.Button(p, text="Export JPEG", command=lambda: self._export("jpeg"),
                  width=22).pack(pady=3)

        ttk.Separator(p, orient="horizontal").pack(fill="x", pady=10)

        tk.Button(p, text="Refresh Templates", command=self._refresh_templates,
                  width=22).pack(pady=3)

        tk.Button(p, text="Back to Menu", command=self._back,
                  width=22, height=2).pack(pady=10)

    def _refresh_templates(self):
        self.all_templates = layout_renderer.load_all_templates("layouts")
        self._update_override_menu()
        if self.card_data:
            self._render_card()

    def _update_override_menu(self):
        menu = self.override_menu["menu"]
        menu.delete(0, "end")
        menu.add_command(label="(auto)", command=lambda: self.override_var.set("(auto)"))
        for t in self.all_templates:
            name = t.get("template_name", "Untitled")
            state = t.get("target_state", "?")
            label = f"{name} [{state}]"
            menu.add_command(label=label, command=lambda v=label: self.override_var.set(v))

    def _import_card(self):
        cards_dir = os.path.join(os.getcwd(), "cards")
        filepath = filedialog.askopenfilename(
            initialdir=cards_dir,
            filetypes=[("JSON files", "*.json")],
            title="Select Card JSON",
        )
        if not filepath:
            return

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                self.card_data = json.load(f)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load card: {e}")
            return

        # Show card info
        ct = self.card_data.get("card_type", "?")
        sc = self.card_data.get("subclass", "") or "(none)"
        st = self.card_data.get("states", 1)
        name = self.card_data.get("data", {}).get("Name", "?")
        self.info_var.set(f"Name: {name}\nType: {ct}\nSubclass: {sc}\nStates: {st}")

        self._update_override_menu()
        self._render_card()

    def _render_card(self):
        if not self.card_data:
            return

        self.all_templates = layout_renderer.load_all_templates("layouts")
        match = layout_renderer.find_matching_template(self.card_data, self.all_templates)
        self.matched_template = match

        if match is None:
            self.match_var.set("No matching template found")
            self.rendered_image = None
            self._show_preview()
            return

        if isinstance(match, tuple):
            s1, s2 = match
            names = []
            if s1:
                names.append(s1.get("template_name", "?"))
            if s2:
                names.append(s2.get("template_name", "?"))
            self.match_var.set("Matched: " + " + ".join(names))
        else:
            self.match_var.set(f"Matched: {match.get('template_name', '?')}")

        self.rendered_image = layout_renderer.render_card(self.card_data, match)
        self._show_preview()

    def _render_override(self):
        if not self.card_data:
            messagebox.showinfo("Info", "Import a card first.")
            return

        override = self.override_var.get()
        if override == "(auto)":
            self._render_card()
            return

        # Find the template by name
        for t in self.all_templates:
            name = t.get("template_name", "Untitled")
            state = t.get("target_state", "?")
            label = f"{name} [{state}]"
            if label == override:
                self.matched_template = t
                self.match_var.set(f"Override: {name}")
                self.rendered_image = layout_renderer.render_card(self.card_data, t)
                self._show_preview()
                return

        messagebox.showwarning("Warning", "Selected template not found.")

    def _show_preview(self):
        self.preview_canvas.delete("all")
        if self.rendered_image is None:
            self.preview_canvas.create_text(
                self.preview_canvas.winfo_width() // 2,
                self.preview_canvas.winfo_height() // 2,
                text="No preview available\n\nImport a card and ensure\na matching template exists",
                fill="#999999", font=("Arial", 16), justify="center")
            return

        # Scale to fit canvas
        cw = self.preview_canvas.winfo_width() or 600
        ch = self.preview_canvas.winfo_height() or 800
        iw, ih = self.rendered_image.size
        margin = 20
        sx = (cw - margin * 2) / iw
        sy = (ch - margin * 2) / ih
        scale = min(sx, sy, 1.0)

        display_w = int(iw * scale)
        display_h = int(ih * scale)
        display_img = self.rendered_image.resize((display_w, display_h), Image.Resampling.LANCZOS)

        tk_img = ImageTk.PhotoImage(display_img)
        self.app.keep_image(tk_img)

        x = cw // 2
        y = ch // 2
        self.preview_canvas.create_image(x, y, image=tk_img, anchor="center")

    def _export(self, fmt):
        if self.rendered_image is None:
            messagebox.showinfo("Info", "No rendered card to export.")
            return

        if fmt == "png":
            filepath = filedialog.asksaveasfilename(
                defaultextension=".png",
                filetypes=[("PNG files", "*.png")],
                title="Export as PNG",
            )
        else:
            filepath = filedialog.asksaveasfilename(
                defaultextension=".jpg",
                filetypes=[("JPEG files", "*.jpg *.jpeg")],
                title="Export as JPEG",
            )

        if not filepath:
            return

        try:
            if fmt == "jpeg":
                # JPEG doesn't support RGBA
                rgb_img = self.rendered_image.convert("RGB")
                rgb_img.save(filepath, "JPEG", quality=95)
            else:
                self.rendered_image.save(filepath, "PNG")
            messagebox.showinfo("Exported", f"Card exported to:\n{filepath}")
        except Exception as e:
            messagebox.showerror("Error", f"Export failed: {e}")

    def _back(self):
        self.app.show_screen(MainMenuScreen)


# ═══════════════════════════════════════════════════════════════════════════
# Template List Screen
# ═══════════════════════════════════════════════════════════════════════════

class TemplateListScreen(BaseScreen):
    def __init__(self, app, root):
        super().__init__(app, root)

        tk.Label(self.frame, text="Manage Layouts",
                 font=("Arial", 18, "bold")).pack(pady=(15, 10))

        # Treeview for template list
        columns = ("name", "type", "subclass", "state", "dimensions")
        self.tree = ttk.Treeview(self.frame, columns=columns, show="headings",
                                 height=20)
        self.tree.heading("name", text="Template Name")
        self.tree.heading("type", text="Target Type")
        self.tree.heading("subclass", text="Subclass")
        self.tree.heading("state", text="State")
        self.tree.heading("dimensions", text="Dimensions")

        self.tree.column("name", width=250)
        self.tree.column("type", width=150)
        self.tree.column("subclass", width=120)
        self.tree.column("state", width=80)
        self.tree.column("dimensions", width=120)

        scrollbar = ttk.Scrollbar(self.frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)

        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(15, 0), pady=5)
        scrollbar.pack(side=tk.LEFT, fill=tk.Y, pady=5)

        # Right buttons
        btn_frame = tk.Frame(self.frame)
        btn_frame.pack(side=tk.RIGHT, padx=15, pady=5, anchor="n")

        tk.Button(btn_frame, text="Edit", width=18, command=self._edit).pack(pady=5)
        tk.Button(btn_frame, text="Delete", width=18, command=self._delete).pack(pady=5)
        tk.Button(btn_frame, text="Refresh", width=18, command=self._refresh).pack(pady=5)

        ttk.Separator(btn_frame, orient="horizontal").pack(fill="x", pady=15)

        tk.Button(btn_frame, text="Back to Menu", width=18,
                  command=self._back).pack(pady=5)

        self.templates = []
        self._refresh()

    def _refresh(self):
        self.tree.delete(*self.tree.get_children())
        self.templates = layout_renderer.load_all_templates("layouts")
        for t in self.templates:
            name = t.get("template_name", "Untitled")
            ttype = t.get("target_type", "?")
            sub = t.get("target_subclass") or ""
            state = t.get("target_state", "full")
            dims = f"{t.get('card_width', '?')} x {t.get('card_height', '?')}"
            self.tree.insert("", "end", values=(name, ttype, sub, state, dims))

    def _get_selected_template(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showinfo("Info", "Select a template first.")
            return None
        idx = self.tree.index(sel[0])
        if 0 <= idx < len(self.templates):
            return self.templates[idx]
        return None

    def _edit(self):
        tmpl = self._get_selected_template()
        if tmpl:
            self.app.show_screen(LayoutDesignerScreen, load_template=tmpl)

    def _delete(self):
        tmpl = self._get_selected_template()
        if not tmpl:
            return
        name = tmpl.get("template_name", "Untitled")
        if not messagebox.askyesno("Confirm Delete",
                                    f"Delete template '{name}'?"):
            return
        fpath = tmpl.get("_file_path")
        if fpath and os.path.isfile(fpath):
            try:
                os.remove(fpath)
                self._refresh()
            except Exception as e:
                messagebox.showerror("Error", f"Failed to delete: {e}")
        else:
            messagebox.showerror("Error", "Template file not found.")

    def _back(self):
        self.app.show_screen(MainMenuScreen)


# ═══════════════════════════════════════════════════════════════════════════
# Entry point
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    app = CardTemplateMaker()
    app.run()
