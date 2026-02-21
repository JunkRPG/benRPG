
"""
Card Template Generator UI for JunkRPG

Visual Pygame UI for creating, editing, previewing, and generating batches
of cards from JSON templates. Matches the JunkRPG tool family style.

Usage:
    python CardTemplateGeneratorUI.py
"""

import pygame
import sys
import pygame_gui
from pygame_gui.elements import (
    UIButton, UITextEntryLine, UISelectionList, UILabel,
    UIDropDownMenu, UITextBox
)
from pygame import display, event
import os
import json
import tempfile

from card_template_generator import generate_cards, generate_card, _summarize_stats
from card_utils import validate_all_card_fields

# Initialize Pygame
pygame.init()

# Get display info for fullscreen
display_info = pygame.display.Info()
WINDOW_WIDTH = display_info.current_w
WINDOW_HEIGHT = display_info.current_h

# Colors
DARK_CHARCOAL = (35, 35, 40)

# Card types matching CardMaker
CARD_TYPES = [
    "Junk Card", "Document Card", "Enemy Card", "NPC Card",
    "Location Card", "Quest Card", "Instance Card", "Boss Card", "Transition Card"
]

NAMING_MODES = ["sequential", "prefix_list", "suffix_list", "name_list"]

FIELD_TYPES = ["fixed", "int", "float", "choice", "scaled"]

TEMPLATES_DIR = "card_templates"
os.makedirs(TEMPLATES_DIR, exist_ok=True)

# Initialize display and manager
screen = display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.FULLSCREEN)
display.set_caption("Card Template Generator")
manager = pygame_gui.UIManager((WINDOW_WIDTH, WINDOW_HEIGHT), "theme.json")


# ---------------------------------------------------------------------------
# FieldEditorRow
# ---------------------------------------------------------------------------
class FieldEditorRow:
    """Manages widgets for one field definition in the template editor."""

    ROW_HEIGHT = 40
    SPACING = 5

    def __init__(self, x, y, width, field_name="", field_type="fixed",
                 field_config=None, on_remove=None, row_index=0):
        self.x = x
        self.y = y
        self.width = width
        self.on_remove = on_remove
        self.row_index = row_index
        self.widgets = []
        self.param_widgets = {}

        # Field name entry
        name_w = 160
        self.name_entry = UITextEntryLine(
            relative_rect=pygame.Rect(x, y, name_w, 30),
            manager=manager
        )
        if field_name:
            self.name_entry.set_text(field_name)
        self.widgets.append(self.name_entry)

        # Type dropdown
        type_x = x + name_w + self.SPACING
        type_w = 100
        self.type_dropdown = UIDropDownMenu(
            options_list=FIELD_TYPES,
            starting_option=field_type,
            relative_rect=pygame.Rect(type_x, y, type_w, 30),
            manager=manager
        )
        self.widgets.append(self.type_dropdown)

        # Param area starts after type dropdown
        self.param_x = type_x + type_w + self.SPACING
        self.param_width = width - name_w - type_w - 40 - self.SPACING * 4

        # Remove button
        self.remove_button = UIButton(
            relative_rect=pygame.Rect(x + width - 35, y, 35, 30),
            text="X",
            manager=manager
        )
        self.widgets.append(self.remove_button)

        # Build param widgets for initial type
        self._build_params(field_type, field_config)

    def _build_params(self, field_type, config=None):
        """Create type-specific parameter widgets."""
        if config is None:
            config = {}

        # Clear old param widgets
        for w in self.param_widgets.values():
            w.kill()
        self.param_widgets = {}

        px = self.param_x
        pw = self.param_width

        if field_type == "fixed":
            entry = UITextEntryLine(
                relative_rect=pygame.Rect(px, self.y, pw, 30),
                manager=manager,
                placeholder_text="Value"
            )
            entry.set_text(str(config.get("value", "")))
            self.param_widgets["value"] = entry

        elif field_type == "int":
            third = (pw - self.SPACING * 2) // 3
            min_e = UITextEntryLine(
                relative_rect=pygame.Rect(px, self.y, third, 30),
                manager=manager,
                placeholder_text="Min"
            )
            min_e.set_text(str(config.get("min", "0")))
            self.param_widgets["min"] = min_e

            max_e = UITextEntryLine(
                relative_rect=pygame.Rect(px + third + self.SPACING, self.y, third, 30),
                manager=manager,
                placeholder_text="Max"
            )
            max_e.set_text(str(config.get("max", "100")))
            self.param_widgets["max"] = max_e

        elif field_type == "float":
            third = (pw - self.SPACING * 2) // 3
            min_e = UITextEntryLine(
                relative_rect=pygame.Rect(px, self.y, third, 30),
                manager=manager,
                placeholder_text="Min"
            )
            min_e.set_text(str(config.get("min", "0.0")))
            self.param_widgets["min"] = min_e

            max_e = UITextEntryLine(
                relative_rect=pygame.Rect(px + third + self.SPACING, self.y, third, 30),
                manager=manager,
                placeholder_text="Max"
            )
            max_e.set_text(str(config.get("max", "1.0")))
            self.param_widgets["max"] = max_e

            dec_e = UITextEntryLine(
                relative_rect=pygame.Rect(px + (third + self.SPACING) * 2, self.y, third, 30),
                manager=manager,
                placeholder_text="Decimals"
            )
            dec_e.set_text(str(config.get("decimals", "1")))
            self.param_widgets["decimals"] = dec_e

        elif field_type == "choice":
            entry = UITextEntryLine(
                relative_rect=pygame.Rect(px, self.y, pw, 30),
                manager=manager,
                placeholder_text="Options (comma-separated)"
            )
            opts = config.get("options", [])
            if isinstance(opts, list):
                entry.set_text(", ".join(str(o) for o in opts))
            else:
                entry.set_text(str(opts))
            self.param_widgets["options"] = entry

        elif field_type == "scaled":
            half = (pw - self.SPACING) // 2
            base_e = UITextEntryLine(
                relative_rect=pygame.Rect(px, self.y, half, 30),
                manager=manager,
                placeholder_text="Base Field"
            )
            base_e.set_text(str(config.get("base_field", "")))
            self.param_widgets["base_field"] = base_e

            mult_e = UITextEntryLine(
                relative_rect=pygame.Rect(px + half + self.SPACING, self.y, half, 30),
                manager=manager,
                placeholder_text="Multiplier"
            )
            mult_e.set_text(str(config.get("multiplier", "1.0")))
            self.param_widgets["multiplier"] = mult_e

    def rebuild_for_type(self, new_type):
        """Kill old param widgets and create new ones for the given type."""
        self._build_params(new_type)

    def get_current_type(self):
        """Get the currently selected field type from the dropdown."""
        sel = self.type_dropdown.selected_option
        if isinstance(sel, tuple):
            return sel[0]
        return sel

    def get_field_config(self):
        """Return (field_name, config_dict) from current widget values."""
        name = self.name_entry.get_text().strip()
        ftype = self.get_current_type()
        config = {"type": ftype}

        if ftype == "fixed":
            config["value"] = self.param_widgets.get("value", _DummyEntry()).get_text().strip()

        elif ftype == "int":
            try:
                config["min"] = int(self.param_widgets.get("min", _DummyEntry()).get_text().strip() or "0")
            except ValueError:
                config["min"] = 0
            try:
                config["max"] = int(self.param_widgets.get("max", _DummyEntry()).get_text().strip() or "100")
            except ValueError:
                config["max"] = 100

        elif ftype == "float":
            try:
                config["min"] = float(self.param_widgets.get("min", _DummyEntry()).get_text().strip() or "0")
            except ValueError:
                config["min"] = 0.0
            try:
                config["max"] = float(self.param_widgets.get("max", _DummyEntry()).get_text().strip() or "1.0")
            except ValueError:
                config["max"] = 1.0
            try:
                config["decimals"] = int(self.param_widgets.get("decimals", _DummyEntry()).get_text().strip() or "1")
            except ValueError:
                config["decimals"] = 1

        elif ftype == "choice":
            raw = self.param_widgets.get("options", _DummyEntry()).get_text().strip()
            config["options"] = [o.strip() for o in raw.split(",") if o.strip()]

        elif ftype == "scaled":
            config["base_field"] = self.param_widgets.get("base_field", _DummyEntry()).get_text().strip()
            try:
                config["multiplier"] = float(
                    self.param_widgets.get("multiplier", _DummyEntry()).get_text().strip() or "1.0"
                )
            except ValueError:
                config["multiplier"] = 1.0

        return name, config

    def destroy(self):
        """Kill all widgets belonging to this row."""
        for w in self.widgets:
            w.kill()
        for w in self.param_widgets.values():
            w.kill()
        self.widgets.clear()
        self.param_widgets.clear()


class _DummyEntry:
    """Fallback so .get_text() never crashes if a param widget is missing."""
    def get_text(self):
        return ""


# ---------------------------------------------------------------------------
# MainMenuScreen
# ---------------------------------------------------------------------------
class MainMenuScreen:
    def __init__(self, app):
        self.app = app
        manager.clear_and_reset()

        self.title = UILabel(
            relative_rect=pygame.Rect(0, 60, WINDOW_WIDTH, 40),
            text="Card Template Generator",
            manager=manager,
            object_id="#title_label",
            anchors={'centerx': 'centerx'}
        )

        cx = (WINDOW_WIDTH - 200) // 2
        self.new_button = UIButton(
            relative_rect=pygame.Rect(cx, 200, 200, 40),
            text="New Template",
            manager=manager
        )
        self.load_button = UIButton(
            relative_rect=pygame.Rect(cx, 260, 200, 40),
            text="Load Template",
            manager=manager
        )
        self.quit_button = UIButton(
            relative_rect=pygame.Rect(cx, 320, 200, 40),
            text="Quit",
            manager=manager
        )

    def handle_event(self, ev):
        if ev.type == pygame_gui.UI_BUTTON_PRESSED:
            if ev.ui_element == self.new_button:
                self.app.show_editor()
            elif ev.ui_element == self.load_button:
                self.app.show_template_list()
            elif ev.ui_element == self.quit_button:
                pygame.quit()
                sys.exit()

    def draw(self):
        screen.fill(DARK_CHARCOAL)


# ---------------------------------------------------------------------------
# TemplateListScreen
# ---------------------------------------------------------------------------
class TemplateListScreen:
    def __init__(self, app):
        self.app = app
        manager.clear_and_reset()

        self.title = UILabel(
            relative_rect=pygame.Rect(0, 20, WINDOW_WIDTH, 40),
            text="Load Template",
            manager=manager,
            object_id="#title_label",
            anchors={'centerx': 'centerx'}
        )

        self.back_button = UIButton(
            relative_rect=pygame.Rect(20, 20, 100, 40),
            text="Back",
            manager=manager,
            object_id="#back_button"
        )

        # Gather template files
        self.template_files = []
        if os.path.isdir(TEMPLATES_DIR):
            for f in sorted(os.listdir(TEMPLATES_DIR)):
                if f.endswith(".json"):
                    self.template_files.append(f)

        # Selection list (left 40%)
        list_w = int(WINDOW_WIDTH * 0.4)
        list_h = WINDOW_HEIGHT - 160
        self.selection_list = UISelectionList(
            relative_rect=pygame.Rect(20, 80, list_w, list_h),
            item_list=self.template_files,
            manager=manager
        )

        # Summary text box (right 55%)
        summary_x = list_w + 40
        summary_w = WINDOW_WIDTH - summary_x - 20
        self.summary_box = UITextBox(
            html_text="<i>Select a template to see details.</i>",
            relative_rect=pygame.Rect(summary_x, 80, summary_w, list_h - 60),
            manager=manager,
            object_id="#log_textbox"
        )

        # Buttons
        btn_y = WINDOW_HEIGHT - 60
        self.load_button = UIButton(
            relative_rect=pygame.Rect(summary_x, btn_y, 140, 40),
            text="Load Selected",
            manager=manager
        )
        self.delete_button = UIButton(
            relative_rect=pygame.Rect(summary_x + 160, btn_y, 100, 40),
            text="Delete",
            manager=manager
        )

        self.selected_file = None

    def _load_summary(self, filename):
        """Load a template and return an HTML summary string."""
        path = os.path.join(TEMPLATES_DIR, filename)
        try:
            with open(path, 'r') as f:
                t = json.load(f)
        except Exception as e:
            return f"<b>Error:</b> {e}"

        lines = []
        lines.append(f"<b>Name:</b> {t.get('template_name', 'N/A')}")
        lines.append(f"<b>Type:</b> {t.get('card_type', 'N/A')}")
        sub = t.get('subclass') or t.get('blueprint_subclass') or 'None'
        lines.append(f"<b>Subclass:</b> {sub}")
        lines.append(f"<b>States:</b> {t.get('states', 1)}")
        lines.append(f"<b>Count:</b> {t.get('count', 10)}")
        lines.append(f"<b>Deck:</b> {t.get('deck', 'None')}")
        naming = t.get("naming", {})
        lines.append(f"<b>Naming mode:</b> {naming.get('mode', 'sequential')}")
        lines.append(f"<b>Base name:</b> {naming.get('base_name', '')}")
        fields = t.get("fields", {})
        lines.append(f"<b>Fields ({len(fields)}):</b> {', '.join(fields.keys()) if fields else 'None'}")
        s2 = t.get("state2_fields", {})
        if s2:
            lines.append(f"<b>State 2 Fields ({len(s2)}):</b> {', '.join(s2.keys())}")
        return "<br>".join(lines)

    def handle_event(self, ev):
        if ev.type == pygame_gui.UI_BUTTON_PRESSED:
            if ev.ui_element == self.back_button:
                self.app.show_main_menu()
            elif ev.ui_element == self.load_button and self.selected_file:
                path = os.path.join(TEMPLATES_DIR, self.selected_file)
                self.app.show_editor(template_path=path)
            elif ev.ui_element == self.delete_button and self.selected_file:
                path = os.path.join(TEMPLATES_DIR, self.selected_file)
                if os.path.exists(path):
                    os.remove(path)
                self.app.show_template_list()

        elif ev.type == pygame_gui.UI_SELECTION_LIST_NEW_SELECTION:
            if ev.ui_element == self.selection_list:
                self.selected_file = ev.text
                html = self._load_summary(self.selected_file)
                self.summary_box.set_text(html)

    def draw(self):
        screen.fill(DARK_CHARCOAL)


# ---------------------------------------------------------------------------
# TemplateEditorScreen
# ---------------------------------------------------------------------------
class TemplateEditorScreen:
    LEFT_COL_W = 350
    ROW_START_Y = 80
    ROW_SPACING = 42

    def __init__(self, app, template_path=None, template_data=None):
        self.app = app
        self.template_path = template_path
        self.field_rows = []
        self.state2_field_rows = []
        self.scroll_offset = 0
        self.max_scroll = 0

        manager.clear_and_reset()

        # Use provided template_data, or load from file, or start blank
        self.template_data = template_data
        if self.template_data is None and template_path and os.path.exists(template_path):
            try:
                with open(template_path, 'r') as f:
                    self.template_data = json.load(f)
            except Exception:
                self.template_data = None

        self._build_ui()

    def _build_ui(self):
        t = self.template_data or {}

        # Title
        self.title = UILabel(
            relative_rect=pygame.Rect(0, 10, WINDOW_WIDTH, 40),
            text="Template Editor",
            manager=manager,
            object_id="#title_label",
            anchors={'centerx': 'centerx'}
        )

        self.back_button = UIButton(
            relative_rect=pygame.Rect(20, 12, 100, 35),
            text="Back",
            manager=manager,
            object_id="#back_button"
        )

        # ---- Left column: Metadata ----
        lx = 20
        ly = 50
        lw = self.LEFT_COL_W - 40

        def label_and_entry(label_text, y, default="", placeholder=""):
            UILabel(
                relative_rect=pygame.Rect(lx, y, lw, 20),
                text=label_text,
                manager=manager
            )
            entry = UITextEntryLine(
                relative_rect=pygame.Rect(lx, y + 20, lw, 28),
                manager=manager,
                placeholder_text=placeholder
            )
            if default:
                entry.set_text(str(default))
            return entry

        def label_and_dropdown(label_text, y, options, default):
            UILabel(
                relative_rect=pygame.Rect(lx, y, lw, 20),
                text=label_text,
                manager=manager
            )
            if default not in options:
                default = options[0]
            dd = UIDropDownMenu(
                options_list=options,
                starting_option=default,
                relative_rect=pygame.Rect(lx, y + 20, lw, 28),
                manager=manager
            )
            return dd

        self.name_entry = label_and_entry("Template Name", ly,
                                          t.get("template_name", ""), "My Template")
        ly += 52
        self.type_dropdown = label_and_dropdown("Card Type", ly, CARD_TYPES,
                                                t.get("card_type", CARD_TYPES[0]))
        ly += 52
        self.subclass_entry = label_and_entry("Subclass (optional)", ly,
                                              t.get("subclass") or t.get("blueprint_subclass") or "")
        ly += 52
        self.states_dropdown = label_and_dropdown("States", ly, ["1", "2"],
                                                  str(t.get("states", 1)))
        ly += 52
        self.count_entry = label_and_entry("Count", ly,
                                           str(t.get("count", 10)), "10")
        ly += 52
        self.deck_entry = label_and_entry("Deck", ly,
                                          t.get("deck", ""), "deck_name")

        # Separator
        ly += 56
        UILabel(
            relative_rect=pygame.Rect(lx, ly, lw, 20),
            text="--- Naming ---",
            manager=manager
        )
        ly += 24

        naming = t.get("naming", {})
        self.naming_mode_dropdown = label_and_dropdown(
            "Naming Mode", ly, NAMING_MODES, naming.get("mode", "sequential")
        )
        ly += 52
        self.base_name_entry = label_and_entry("Base Name", ly,
                                               naming.get("base_name", ""), "Card")
        ly += 52

        # The list entry — label depends on naming mode
        self.list_label = UILabel(
            relative_rect=pygame.Rect(lx, ly, lw, 20),
            text=self._list_label_text(naming.get("mode", "sequential")),
            manager=manager
        )
        self.list_entry = UITextEntryLine(
            relative_rect=pygame.Rect(lx, ly + 20, lw, 28),
            manager=manager,
            placeholder_text="comma-separated"
        )
        # Pre-fill from template
        mode = naming.get("mode", "sequential")
        list_data = naming.get("prefixes") or naming.get("suffixes") or naming.get("names") or []
        if isinstance(list_data, list):
            self.list_entry.set_text(", ".join(str(x) for x in list_data))

        # ---- Right column: Field definitions ----
        self.fields_x = self.LEFT_COL_W + 10
        self.fields_w = WINDOW_WIDTH - self.fields_x - 20
        self.fields_top = 50

        # Section label
        self.fields_label = UILabel(
            relative_rect=pygame.Rect(self.fields_x, self.fields_top, 300, 24),
            text="State 1 Fields",
            manager=manager
        )

        self.add_field_button = None
        self.state2_label = None
        self.add_state2_field_button = None

        # Build field rows from template
        self._rebuild_field_rows()

        # ---- Bottom toolbar ----
        btn_y = WINDOW_HEIGHT - 45
        self.save_button = UIButton(
            relative_rect=pygame.Rect(self.fields_x, btn_y, 150, 35),
            text="Save Template",
            manager=manager
        )
        self.preview_button = UIButton(
            relative_rect=pygame.Rect(self.fields_x + 170, btn_y, 180, 35),
            text="Preview / Generate",
            manager=manager
        )
        self.status_label = UILabel(
            relative_rect=pygame.Rect(self.fields_x + 370, btn_y, 400, 35),
            text="",
            manager=manager
        )

    def _list_label_text(self, mode):
        if mode == "prefix_list":
            return "Prefixes (comma-separated)"
        elif mode == "suffix_list":
            return "Suffixes (comma-separated)"
        elif mode == "name_list":
            return "Names (comma-separated)"
        return "List (N/A for sequential)"

    def _rebuild_field_rows(self):
        """Destroy and recreate all field rows from current data."""
        # Kill old rows
        for row in self.field_rows:
            row.destroy()
        self.field_rows = []
        for row in self.state2_field_rows:
            row.destroy()
        self.state2_field_rows = []

        if self.add_field_button:
            self.add_field_button.kill()
            self.add_field_button = None
        if self.state2_label:
            self.state2_label.kill()
            self.state2_label = None
        if self.add_state2_field_button:
            self.add_state2_field_button.kill()
            self.add_state2_field_button = None

        t = self.template_data or {}
        fields = t.get("fields", {})
        y = self.fields_top + 30 - self.scroll_offset

        # State 1 field rows
        for fname, fconf in fields.items():
            ftype = fconf.get("type", "fixed")
            row = FieldEditorRow(
                self.fields_x, y, self.fields_w,
                field_name=fname, field_type=ftype, field_config=fconf,
                on_remove=None, row_index=len(self.field_rows)
            )
            self.field_rows.append(row)
            y += self.ROW_SPACING

        # "Add Field" button
        self.add_field_button = UIButton(
            relative_rect=pygame.Rect(self.fields_x, y, 120, 30),
            text="+ Add Field",
            manager=manager
        )
        y += 40

        # State 2 section
        states = self._get_states()
        if states >= 2:
            self.state2_label = UILabel(
                relative_rect=pygame.Rect(self.fields_x, y, 300, 24),
                text="State 2 Fields",
                manager=manager
            )
            y += 28

            s2_fields = t.get("state2_fields", {})
            for fname, fconf in s2_fields.items():
                ftype = fconf.get("type", "fixed")
                row = FieldEditorRow(
                    self.fields_x, y, self.fields_w,
                    field_name=fname, field_type=ftype, field_config=fconf,
                    on_remove=None, row_index=len(self.state2_field_rows)
                )
                self.state2_field_rows.append(row)
                y += self.ROW_SPACING

            self.add_state2_field_button = UIButton(
                relative_rect=pygame.Rect(self.fields_x, y, 160, 30),
                text="+ Add State 2 Field",
                manager=manager
            )
            y += 40

        # Calculate max scroll
        total_content = y + self.scroll_offset
        visible = WINDOW_HEIGHT - self.fields_top - 60
        self.max_scroll = max(0, total_content - visible)

    def _get_states(self):
        sel = self.states_dropdown.selected_option
        if isinstance(sel, tuple):
            sel = sel[0]
        try:
            return int(sel)
        except (ValueError, TypeError):
            return 1

    def _collect_template_data(self):
        """Build template dict from current widget values."""
        card_type_sel = self.type_dropdown.selected_option
        if isinstance(card_type_sel, tuple):
            card_type_sel = card_type_sel[0]

        naming_mode_sel = self.naming_mode_dropdown.selected_option
        if isinstance(naming_mode_sel, tuple):
            naming_mode_sel = naming_mode_sel[0]

        states = self._get_states()

        # Naming config
        naming = {
            "mode": naming_mode_sel,
            "base_name": self.base_name_entry.get_text().strip()
        }
        raw_list = self.list_entry.get_text().strip()
        items = [x.strip() for x in raw_list.split(",") if x.strip()] if raw_list else []
        if naming_mode_sel == "prefix_list":
            naming["prefixes"] = items
        elif naming_mode_sel == "suffix_list":
            naming["suffixes"] = items
        elif naming_mode_sel == "name_list":
            naming["names"] = items

        # Fields
        fields = {}
        for row in self.field_rows:
            fname, fconf = row.get_field_config()
            if fname:
                fields[fname] = fconf

        state2_fields = {}
        for row in self.state2_field_rows:
            fname, fconf = row.get_field_config()
            if fname:
                state2_fields[fname] = fconf

        # Subclass handling
        subclass_text = self.subclass_entry.get_text().strip() or None

        template = {
            "template_name": self.name_entry.get_text().strip() or "Unnamed Template",
            "card_type": card_type_sel,
            "subclass": subclass_text,
            "blueprint_subclass": None,
            "states": states,
            "count": int(self.count_entry.get_text().strip() or "10"),
            "naming": naming,
            "fields": fields,
            "state2_fields": state2_fields,
            "deck": self.deck_entry.get_text().strip() or None
        }
        return template

    def _save_template(self):
        """Save current editor state to a JSON file in card_templates/."""
        template = self._collect_template_data()
        tname = template["template_name"]
        # Sanitize filename
        safe_name = "".join(c if c.isalnum() or c in " _-" else "_" for c in tname).strip()
        if not safe_name:
            safe_name = "unnamed_template"
        filename = safe_name.replace(" ", "_").lower() + ".json"
        path = os.path.join(TEMPLATES_DIR, filename)

        with open(path, 'w') as f:
            json.dump(template, f, indent=2)

        self.template_path = path
        self.status_label.set_text(f"Saved: {filename}")

    def _add_field_row(self, is_state2=False):
        """Snapshot current data, add an empty field, and rebuild."""
        self._snapshot_to_template_data()
        target_fields = "state2_fields" if is_state2 else "fields"
        if self.template_data is None:
            self.template_data = {}
        fields = self.template_data.get(target_fields, {})
        # Find a unique default name
        idx = len(fields) + 1
        while f"NewField{idx}" in fields:
            idx += 1
        fields[f"NewField{idx}"] = {"type": "fixed", "value": ""}
        self.template_data[target_fields] = fields
        self._rebuild_field_rows()

    def _remove_field_row(self, row, is_state2=False):
        """Snapshot, remove the field, rebuild."""
        self._snapshot_to_template_data()
        fname, _ = row.get_field_config()
        target_fields = "state2_fields" if is_state2 else "fields"
        fields = self.template_data.get(target_fields, {})
        if fname in fields:
            del fields[fname]
        self.template_data[target_fields] = fields
        self._rebuild_field_rows()

    def _snapshot_to_template_data(self):
        """Capture current widget values back into self.template_data."""
        self.template_data = self._collect_template_data()

    def handle_event(self, ev):
        if ev.type == pygame_gui.UI_BUTTON_PRESSED:
            if ev.ui_element == self.back_button:
                self.app.show_main_menu()
                return
            if ev.ui_element == self.save_button:
                self._save_template()
                return
            if ev.ui_element == self.preview_button:
                template = self._collect_template_data()
                self.app.show_preview(template, self.template_path)
                return
            if self.add_field_button and ev.ui_element == self.add_field_button:
                self._add_field_row(is_state2=False)
                return
            if self.add_state2_field_button and ev.ui_element == self.add_state2_field_button:
                self._add_field_row(is_state2=True)
                return

            # Check remove buttons on field rows
            for row in self.field_rows:
                if ev.ui_element == row.remove_button:
                    self._remove_field_row(row, is_state2=False)
                    return
            for row in self.state2_field_rows:
                if ev.ui_element == row.remove_button:
                    self._remove_field_row(row, is_state2=True)
                    return

        # Handle dropdown type changes — rebuild param widgets
        if ev.type == pygame_gui.UI_DROP_DOWN_MENU_CHANGED:
            for row in self.field_rows + self.state2_field_rows:
                if ev.ui_element == row.type_dropdown:
                    new_type = ev.text
                    row.rebuild_for_type(new_type)
                    return

            # States dropdown changed — rebuild field section
            if ev.ui_element == self.states_dropdown:
                self._snapshot_to_template_data()
                self._rebuild_field_rows()
                return

            # Naming mode changed — update list label
            if ev.ui_element == self.naming_mode_dropdown:
                sel = self.naming_mode_dropdown.selected_option
                if isinstance(sel, tuple):
                    sel = sel[0]
                self.list_label.set_text(self._list_label_text(sel))
                return

        # Scroll in the right column
        if ev.type == pygame.MOUSEWHEEL:
            mouse_x, _ = pygame.mouse.get_pos()
            if mouse_x > self.LEFT_COL_W:
                self._snapshot_to_template_data()
                self.scroll_offset = max(0, min(self.max_scroll,
                                                self.scroll_offset - ev.y * 30))
                self._rebuild_field_rows()

    def draw(self):
        screen.fill(DARK_CHARCOAL)
        # Draw a vertical separator line
        pygame.draw.line(screen, (58, 58, 92),
                         (self.LEFT_COL_W, 45),
                         (self.LEFT_COL_W, WINDOW_HEIGHT - 50), 1)
        # Draw a bottom toolbar line
        pygame.draw.line(screen, (58, 58, 92),
                         (0, WINDOW_HEIGHT - 50),
                         (WINDOW_WIDTH, WINDOW_HEIGHT - 50), 1)


# ---------------------------------------------------------------------------
# PreviewGenerateScreen
# ---------------------------------------------------------------------------
class PreviewGenerateScreen:
    LEFT_PANEL_W = 300

    def __init__(self, app, template_data, editor_template_path=None):
        self.app = app
        self.template_data = template_data
        self.editor_template_path = editor_template_path

        manager.clear_and_reset()

        self.title = UILabel(
            relative_rect=pygame.Rect(0, 10, WINDOW_WIDTH, 40),
            text="Preview / Generate",
            manager=manager,
            object_id="#title_label",
            anchors={'centerx': 'centerx'}
        )

        self.back_button = UIButton(
            relative_rect=pygame.Rect(20, 12, 140, 35),
            text="Back to Editor",
            manager=manager,
            object_id="#back_button"
        )

        # Left panel controls
        lx = 20
        ly = 60
        lw = self.LEFT_PANEL_W - 40

        UILabel(relative_rect=pygame.Rect(lx, ly, lw, 20),
                text="Count", manager=manager)
        self.count_entry = UITextEntryLine(
            relative_rect=pygame.Rect(lx, ly + 20, lw, 28), manager=manager)
        self.count_entry.set_text(str(template_data.get("count", 10)))
        ly += 52

        UILabel(relative_rect=pygame.Rect(lx, ly, lw, 20),
                text="Seed (optional)", manager=manager)
        self.seed_entry = UITextEntryLine(
            relative_rect=pygame.Rect(lx, ly + 20, lw, 28), manager=manager,
            placeholder_text="Random")
        ly += 52

        UILabel(relative_rect=pygame.Rect(lx, ly, lw, 20),
                text="Deck", manager=manager)
        self.deck_entry = UITextEntryLine(
            relative_rect=pygame.Rect(lx, ly + 20, lw, 28), manager=manager)
        self.deck_entry.set_text(template_data.get("deck", "") or "")
        ly += 60

        self.use_name_id = False
        self.name_id_button = UIButton(
            relative_rect=pygame.Rect(lx, ly, lw, 32),
            text="Use Name as ID: OFF",
            manager=manager
        )
        ly += 44

        self.dry_run_button = UIButton(
            relative_rect=pygame.Rect(lx, ly, lw, 36),
            text="Dry Run",
            manager=manager
        )
        ly += 46

        self.generate_button = UIButton(
            relative_rect=pygame.Rect(lx, ly, lw, 36),
            text="Generate Cards",
            manager=manager
        )
        ly += 46

        self.status_label = UILabel(
            relative_rect=pygame.Rect(lx, ly, lw, 60),
            text="",
            manager=manager
        )

        # Right panel: log text box
        log_x = self.LEFT_PANEL_W + 10
        log_w = WINDOW_WIDTH - log_x - 20
        self.log_box = UITextBox(
            html_text="<i>Run a dry run or generate to see results here.</i>",
            relative_rect=pygame.Rect(log_x, 50, log_w, WINDOW_HEIGHT - 70),
            manager=manager,
            object_id="#log_textbox"
        )

    def _get_count(self):
        try:
            return int(self.count_entry.get_text().strip() or "10")
        except ValueError:
            return 10

    def _get_seed(self):
        txt = self.seed_entry.get_text().strip()
        if txt:
            try:
                return int(txt)
            except ValueError:
                return None
        return None

    def _do_dry_run(self):
        """Preview cards without saving."""
        import random as _random
        count = self._get_count()
        seed = self._get_seed()
        rng = _random.Random(seed)

        lines = []
        lines.append(f"<b>Dry Run Preview — {count} cards</b><br>")
        lines.append(f"Template: {self.template_data.get('template_name', 'N/A')}<br>")
        lines.append(f"Type: {self.template_data.get('card_type', 'N/A')}<br><br>")

        valid_count = 0
        invalid_count = 0
        used_names = set()

        for i in range(count):
            card_data, name = generate_card(self.template_data, i, rng)

            # Ensure unique names
            original_name = name
            suffix = 1
            while name in used_names:
                suffix += 1
                name = f"{original_name} {suffix}"
                card_data["data"]["Name"] = name
            used_names.add(name)

            stats = _summarize_stats(card_data)
            is_valid, errors = validate_all_card_fields(card_data)

            if is_valid:
                valid_count += 1
                lines.append(f"  <b>{name}</b>: {stats}<br>")
            else:
                invalid_count += 1
                err_str = "; ".join(errors)
                lines.append(f"  <b>{name}</b> [INVALID: {err_str}]: {stats}<br>")

        lines.append(f"<br><b>Summary:</b> {valid_count} valid, {invalid_count} invalid")
        self.log_box.set_text("".join(lines))
        self.status_label.set_text(f"Dry run: {valid_count} valid, {invalid_count} invalid")

    def _do_generate(self):
        """Actually generate cards by saving template to a temp file and calling generate_cards()."""
        count = self._get_count()
        seed = self._get_seed()
        deck = self.deck_entry.get_text().strip() or None

        # Write template to a temp file
        tmp_fd, tmp_path = tempfile.mkstemp(suffix=".json", prefix="ctg_tmp_")
        try:
            with os.fdopen(tmp_fd, 'w') as f:
                json.dump(self.template_data, f, indent=2)

            generated, skipped, errors = generate_cards(
                tmp_path,
                count=count,
                deck_name=deck,
                seed=seed,
                use_name_as_id=self.use_name_id,
                dry_run=False
            )
        finally:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)

        lines = []
        lines.append(f"<b>Generation Complete</b><br><br>")
        lines.append(f"<b>Generated:</b> {generated}<br>")
        lines.append(f"<b>Skipped:</b> {skipped}<br>")
        if errors:
            lines.append(f"<br><b>Errors ({len(errors)}):</b><br>")
            for err in errors:
                lines.append(f"  {err}<br>")
        else:
            lines.append("<br>No errors.")
        if deck:
            lines.append(f"<br>Deck: {deck}")

        self.log_box.set_text("".join(lines))
        self.status_label.set_text(f"Done: {generated} generated, {skipped} skipped")

    def handle_event(self, ev):
        if ev.type == pygame_gui.UI_BUTTON_PRESSED:
            if ev.ui_element == self.back_button:
                self.app.show_editor(template_path=self.editor_template_path,
                                     template_data=self.template_data)
                return
            if ev.ui_element == self.name_id_button:
                self.use_name_id = not self.use_name_id
                label = "ON" if self.use_name_id else "OFF"
                self.name_id_button.set_text(f"Use Name as ID: {label}")
                return
            if ev.ui_element == self.dry_run_button:
                self._do_dry_run()
                return
            if ev.ui_element == self.generate_button:
                self._do_generate()
                return

    def draw(self):
        screen.fill(DARK_CHARCOAL)
        # Separator line
        pygame.draw.line(screen, (58, 58, 92),
                         (self.LEFT_PANEL_W, 45),
                         (self.LEFT_PANEL_W, WINDOW_HEIGHT - 10), 1)


# ---------------------------------------------------------------------------
# TemplateGeneratorApp (main manager)
# ---------------------------------------------------------------------------
class TemplateGeneratorApp:
    def __init__(self):
        self.current_screen = None
        self.show_main_menu()

    def show_main_menu(self):
        self.current_screen = MainMenuScreen(self)

    def show_template_list(self):
        self.current_screen = TemplateListScreen(self)

    def show_editor(self, template_path=None, template_data=None):
        """Open the editor. If template_data is provided (returning from preview),
        use it directly. Otherwise load from path."""
        self.current_screen = TemplateEditorScreen(
            self, template_path=template_path, template_data=template_data
        )

    def show_preview(self, template_data, editor_template_path=None):
        self.current_screen = PreviewGenerateScreen(
            self, template_data, editor_template_path
        )

    def handle_event(self, ev):
        if self.current_screen:
            self.current_screen.handle_event(ev)

    def draw(self):
        if self.current_screen:
            self.current_screen.draw()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    app = TemplateGeneratorApp()
    clock = pygame.time.Clock()

    while True:
        time_delta = clock.tick(60) / 1000.0
        for e in event.get():
            if e.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if e.type == pygame.KEYDOWN and e.key == pygame.K_ESCAPE:
                pygame.quit()
                sys.exit()
            app.handle_event(e)
            manager.process_events(e)

        manager.update(time_delta)
        app.draw()
        manager.draw_ui(screen)
        display.flip()


if __name__ == "__main__":
    main()
