import pygame
import sys
import tkinter as tk
from tkinter import filedialog
import pygame_gui
from pygame_gui.elements import UIButton, UITextEntryLine, UILabel, UIDropDownMenu
from pygame import display, event
import os
import json
import uuid
import re
from deck_utils import resolve_deck_path, DECKS_DIR
from card_utils import validate_card_json_fields, JSON_FIELDS, get_json_field_help

# Constants
CARD_WIDTH = 400
CARD_HEIGHT = 600
DARK_CHARCOAL = (35, 35, 40)
CARD_BG = (26, 26, 62)
CARD_TEXT = (200, 200, 212)
SUPPORTED_IMAGE_FORMATS = ('.png', '.jpg', '.jpeg', '.bmp', '.gif')

# Initialize Pygame
pygame.init()

# Get display info for fullscreen
display_info = pygame.display.Info()
WINDOW_WIDTH = display_info.current_w
WINDOW_HEIGHT = display_info.current_h
CARD_SCALE = min((WINDOW_WIDTH - 40) / CARD_WIDTH, (WINDOW_HEIGHT - 200) / CARD_HEIGHT)

manager = pygame_gui.UIManager((WINDOW_WIDTH, WINDOW_HEIGHT), "theme.json")

screen = display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.FULLSCREEN)
display.set_caption("Card Management Application")

INDEX_FILE = "cards/card_index.json"
os.makedirs("cards", exist_ok=True)
if not os.path.exists(INDEX_FILE):
    with open(INDEX_FILE, 'w') as f:
        json.dump({}, f)

# Load range options from Range Maker
RANGE_INDEX_FILE = "ranges/range_index.json"
RANGE_OPTIONS = ["None"]  # Default option
if os.path.exists(RANGE_INDEX_FILE):
    try:
        with open(RANGE_INDEX_FILE, 'r') as f:
            range_index = json.load(f)
        RANGE_OPTIONS.extend([range_id for range_id in range_index.keys()])
    except Exception as e:
        print(f"Error loading range index: {e}")

# Define HP options globally for consistency
HP_OPTIONS = ["+0HP", "+5HP", "+10HP", "+15HP", "+20HP", "+25HP", "+30HP", "+35HP", "+40HP", "+50HP", "+75HP", "+100HP"]
PLACEHOLDER_OPTIONS = ["TBD"]

# Skill system options
SKILL_TYPES = ["Attack", "Buff_Heal", "Passive"]
SKILL_EFFECT_TYPES = ["Heal", "Heal_Adjacent", "Buff_Attack", "Buff_Defense", "Damage", "Damage_AOE"]
SKILL_TRIGGERS = ["Turn_Start", "Turn_End", "Always"]
SKILL_ATTACK_TYPES = ["Melee", "Projectile", "AOE"]
SKILL_TARGETS = ["Self", "Ally", "Enemy", "All_Allies", "All_Enemies"]

# Location system options
LOCATION_OUTCOME_TYPES = ["Junk Card", "NPC Card", "Enemy Card", "Document Card", "None"]
LOCATION_CHOICE_ACTIONS = ["draw_card", "heal", "trade", "shop", "sell", "exit"]
CURRENCY_TYPES = ["metal", "wood", "raw_materials", "refined_materials", "cards"]
ALLEGIANCE_TYPES = ["Hostile", "Neutral", "Allied"]

# Weapon/Ammunition system options
RANGE_TYPES = ["line_of_sight", "area_effect", "echo", "multi_echo", "perimeter", "mist_shadow"]
AMMO_TYPES = ["Arrow", "Bolt", "Stone", "Bullet", "Dart", "None"]
BOOL_OPTIONS = ["false", "true"]
RUNOUT_CHANCE_OPTIONS = ["0", "5", "10", "15", "20", "25", "30", "40", "50", "75", "100"]
TOOL_SLOT_OPTIONS = ["0", "1", "2", "3"]

# Tool/Accessory types
ACCESSORY_TYPES = ["Tool_Belt", "Pouch", "Belt", "Accessory"]

# Outcome editor constants
TRANSITION_OUTCOME_TYPES = [
    "none", "draw_instance", "spawn_enemy", "spawn_boss", "spawn_npc",
    "draw_junk", "draw_document", "weather", "flip_state",
    "modify_instance_chance", "spawn_horse", "spawn_wild_mount",
    "quest_npc_spawn", "trip_fall"
]

INSTANCE_OUTCOME_TYPES = [
    "none", "damage_player", "heal_player", "draw_card",
    "damage_enemy", "damage_ally", "spawn_enemy", "spawn_ally",
    "modify_stat", "teleport_player", "player_choice"
]

EDGE_OPTIONS = ["random", "north", "south", "east", "west"]
DRAW_CARD_TYPE_OPTIONS = ["Junk Card", "Document Card", "NPC Card", "Enemy Card"]

# param_name, widget_type, options_or_default, [default_selection]
# widget_type: "text" -> UITextEntryLine, "dropdown" -> UIDropDownMenu
OUTCOME_PARAM_DEFS = {
    # Transition outcome params
    "t_spawn_enemy": [("edge", "dropdown", EDGE_OPTIONS, "random"), ("deck", "text", ""), ("count", "text", "1")],
    "t_spawn_boss": [("edge", "dropdown", EDGE_OPTIONS, "random"), ("deck", "text", ""), ("count", "text", "1")],
    "t_spawn_npc": [("edge", "dropdown", EDGE_OPTIONS, "random"), ("deck", "text", ""), ("count", "text", "1"),
                     ("allegiance", "dropdown", ALLEGIANCE_TYPES, "Neutral")],
    "t_draw_junk": [("deck", "text", ""), ("count", "text", "1")],
    "t_draw_document": [("deck", "text", ""), ("count", "text", "1")],
    "t_spawn_horse": [("deck", "text", ""), ("count", "text", "1")],
    "t_spawn_wild_mount": [("deck", "text", ""), ("count", "text", "1")],
    "t_weather": [("effect", "text", ""), ("range_modifier", "text", "-2")],
    "t_modify_instance_chance": [("chance", "text", "0.15")],
    "t_quest_npc_spawn": [("npc_deck", "text", ""), ("quest_deck", "text", "")],
    "t_trip_fall": [("damage", "text", "3")],
    # Instance outcome params
    "i_damage_player": [("damage", "text", "0")],
    "i_heal_player": [("amount", "text", "0")],
    "i_draw_card": [("card_type", "dropdown", DRAW_CARD_TYPE_OPTIONS, "Junk Card")],
    "i_damage_enemy": [("damage", "text", "0"), ("target", "text", "random")],
    "i_damage_ally": [("damage", "text", "0"), ("target", "text", "random")],
    "i_spawn_enemy": [("deck", "text", ""), ("spawn_near", "text", "player"), ("count", "text", "1")],
    "i_spawn_ally": [("deck", "text", ""), ("spawn_near", "text", "player"), ("count", "text", "1")],
    "i_modify_stat": [("stat", "text", ""), ("amount", "text", "0")],
    "i_teleport_player": [("distance", "text", "1"), ("direction", "text", "random")],
    "i_player_choice": [("choices_json", "text", "[]")],
    # Shared no-param types
    "none": [], "draw_instance": [], "flip_state": [],
}


class OutcomeRow:
    """Manages pygame_gui widgets for a single outcome entry in the visual editor."""

    def __init__(self, index, field_name, mode, x, y, width, ui_elements_list,
                 type_options, initial_data=None):
        self.index = index
        self.field_name = field_name
        self.mode = mode  # "transition" or "instance"
        self.x = x
        self.y = y
        self.width = width
        self.ui_elements_list = ui_elements_list
        self.type_options = type_options
        self.widgets = []  # all widgets owned by this row
        self.param_widgets = []  # (param_name, widget) for param fields
        self.type_dropdown = None
        self.prob_entry = None
        self.text_entry = None
        self.remove_button = None
        self._build(initial_data or {"probability": 0.5, "type": "none", "text": "", "params": {}})

    def _build(self, data):
        prob = str(data.get("probability", 0.5))
        outcome_type = data.get("type", "none")
        text = data.get("text", "")
        params = data.get("params", {})

        uid = f"{self.field_name}_{self.index}"
        col_x = self.x
        row_y = self.y

        # Line 1: index label, probability, type dropdown, remove button
        idx_label = UILabel(
            relative_rect=pygame.Rect(col_x, row_y, 25, 30),
            text=f"{self.index + 1}.",
            manager=manager,
            object_id=f"#oe_idx_{uid}"
        )
        self._track(idx_label)

        prob_label = UILabel(
            relative_rect=pygame.Rect(col_x + 25, row_y, 35, 30),
            text="Prob:",
            manager=manager,
            object_id=f"#oe_plbl_{uid}"
        )
        self._track(prob_label)

        self.prob_entry = UITextEntryLine(
            relative_rect=pygame.Rect(col_x + 60, row_y, 60, 30),
            manager=manager,
            initial_text=prob,
            object_id=f"#oe_prob_{uid}"
        )
        self._track(self.prob_entry)

        type_label = UILabel(
            relative_rect=pygame.Rect(col_x + 125, row_y, 35, 30),
            text="Type:",
            manager=manager,
            object_id=f"#oe_tlbl_{uid}"
        )
        self._track(type_label)

        starting = outcome_type if outcome_type in self.type_options else self.type_options[0]
        self.type_dropdown = UIDropDownMenu(
            options_list=self.type_options,
            starting_option=starting,
            relative_rect=pygame.Rect(col_x + 160, row_y, 180, 30),
            manager=manager,
            object_id=f"#oe_type_{uid}"
        )
        self._track(self.type_dropdown)

        self.remove_button = UIButton(
            relative_rect=pygame.Rect(col_x + self.width - 60, row_y, 60, 30),
            text="X",
            manager=manager,
            object_id=f"#oe_rm_{uid}"
        )
        self._track(self.remove_button)

        # Line 2: description text
        row_y += 35
        text_label = UILabel(
            relative_rect=pygame.Rect(col_x, row_y, 35, 30),
            text="Text:",
            manager=manager,
            object_id=f"#oe_txtlbl_{uid}"
        )
        self._track(text_label)

        self.text_entry = UITextEntryLine(
            relative_rect=pygame.Rect(col_x + 35, row_y, self.width - 35, 30),
            manager=manager,
            initial_text=str(text),
            object_id=f"#oe_text_{uid}"
        )
        self._track(self.text_entry)

        # Line 3+: dynamic param fields
        row_y += 35
        param_defs = self._get_param_defs(outcome_type)
        px = col_x
        for pi, pdef in enumerate(param_defs):
            param_name = pdef[0]
            widget_type = pdef[1]
            # Special case: choices_json widget maps to "choices" key in data
            if param_name == "choices_json":
                param_val = params.get("choices", params.get("choices_json", ""))
            else:
                param_val = params.get(param_name, "")

            label_w = 110
            field_w = 90
            plbl = UILabel(
                relative_rect=pygame.Rect(px, row_y, label_w, 30),
                text=f"{param_name}:",
                manager=manager,
                object_id=f"#oe_plbl_{uid}_{pi}"
            )
            self._track(plbl)

            if widget_type == "dropdown":
                options = pdef[2]
                default = pdef[3] if len(pdef) > 3 else options[0]
                # If we have a stored value, use it
                if param_val and str(param_val) in options:
                    default = str(param_val)
                pw = UIDropDownMenu(
                    options_list=options,
                    starting_option=default,
                    relative_rect=pygame.Rect(px + label_w, row_y, field_w, 30),
                    manager=manager,
                    object_id=f"#oe_param_{uid}_{pi}"
                )
            else:
                # text entry
                default_text = pdef[2] if len(pdef) > 2 else ""
                if param_val != "":
                    default_text = str(param_val)
                # Special case: choices_json stores as list, convert back to JSON string
                if param_name == "choices_json" and isinstance(param_val, list):
                    default_text = json.dumps(param_val)
                elif param_name == "choices_json" and param_val == "":
                    default_text = "[]"
                pw = UITextEntryLine(
                    relative_rect=pygame.Rect(px + label_w, row_y, field_w, 30),
                    manager=manager,
                    initial_text=default_text,
                    object_id=f"#oe_param_{uid}_{pi}"
                )
            self._track(pw)
            self.param_widgets.append((param_name, pw))

            px += label_w + field_w + 5
            # Wrap to next line if needed
            if px + label_w + field_w + 5 > col_x + self.width:
                px = col_x
                row_y += 35

        # Store total height for this row
        self.height = (row_y - self.y) + 40  # 40px padding

    def _get_param_defs(self, outcome_type):
        """Get param definitions based on mode and outcome type."""
        prefix = "t_" if self.mode == "transition" else "i_"
        key = prefix + outcome_type
        if key in OUTCOME_PARAM_DEFS:
            return OUTCOME_PARAM_DEFS[key]
        # Try shared (no-param types)
        if outcome_type in OUTCOME_PARAM_DEFS:
            return OUTCOME_PARAM_DEFS[outcome_type]
        return []

    def _track(self, widget):
        """Track widget for cleanup and scroll."""
        self.widgets.append(widget)
        self.ui_elements_list.append(widget)

    def serialize(self):
        """Serialize this row to an outcome dict."""
        try:
            prob = float(self.prob_entry.get_text())
        except (ValueError, AttributeError):
            prob = 0.0

        outcome_type = self.type_dropdown.selected_option
        if isinstance(outcome_type, tuple):
            outcome_type = outcome_type[0]

        text = self.text_entry.get_text() if self.text_entry else ""

        params = {}
        for param_name, pw in self.param_widgets:
            if isinstance(pw, UIDropDownMenu):
                val = pw.selected_option
                if isinstance(val, tuple):
                    val = val[0]
            else:
                val = pw.get_text()

            # Convert numeric params
            if param_name in ("count", "damage", "amount", "distance"):
                try:
                    val = int(val)
                except (ValueError, TypeError):
                    try:
                        val = float(val)
                    except (ValueError, TypeError):
                        pass
            elif param_name in ("probability", "chance", "range_modifier", "risk"):
                try:
                    val = float(val)
                except (ValueError, TypeError):
                    pass
            elif param_name == "choices_json":
                # Store as parsed list under "choices" key
                try:
                    params["choices"] = json.loads(val)
                except (json.JSONDecodeError, TypeError):
                    params["choices"] = []
                continue

            params[param_name] = val

        return {"probability": prob, "type": outcome_type, "text": text, "params": params}

    def get_probability_text(self):
        return self.prob_entry.get_text() if self.prob_entry else "0"

    def kill(self):
        """Destroy all widgets owned by this row."""
        for w in self.widgets:
            if w in self.ui_elements_list:
                self.ui_elements_list.remove(w)
            w.kill()
        self.widgets.clear()
        self.param_widgets.clear()


class OutcomeEditorWidget:
    """Manages a list of OutcomeRows plus Add button and probability total label."""

    def __init__(self, field_name, mode, x, y, width, ui_elements_list):
        self.field_name = field_name
        self.mode = mode  # "transition" or "instance"
        self.x = x
        self.y = y
        self.width = width
        self.ui_elements_list = ui_elements_list
        self.rows = []
        self.add_button = None
        self.total_label = None
        self.header_label = None
        self.header_widgets = []  # header + add button + total label
        self.type_options = TRANSITION_OUTCOME_TYPES if mode == "transition" else INSTANCE_OUTCOME_TYPES

    def build_all(self, initial_outcomes=None):
        """Build all rows from data (or empty)."""
        self._destroy_all()
        outcomes = initial_outcomes or []

        # Header label
        header_text = self.field_name.replace("_", " ")
        self.header_label = UILabel(
            relative_rect=pygame.Rect(self.x, self.y, self.width, 25),
            text=f"--- {header_text} ---",
            manager=manager,
            object_id=f"#oe_header_{self.field_name}"
        )
        self.header_widgets.append(self.header_label)
        self.ui_elements_list.append(self.header_label)

        current_y = self.y + 30
        for i, outcome_data in enumerate(outcomes):
            row = OutcomeRow(
                index=i, field_name=self.field_name, mode=self.mode,
                x=self.x, y=current_y, width=self.width,
                ui_elements_list=self.ui_elements_list,
                type_options=self.type_options,
                initial_data=outcome_data
            )
            self.rows.append(row)
            current_y += row.height

        # Add Outcome button
        self.add_button = UIButton(
            relative_rect=pygame.Rect(self.x, current_y, 120, 30),
            text="+ Add Outcome",
            manager=manager,
            object_id=f"#oe_add_{self.field_name}"
        )
        self.header_widgets.append(self.add_button)
        self.ui_elements_list.append(self.add_button)

        # Total probability label
        self.total_label = UILabel(
            relative_rect=pygame.Rect(self.x + 130, current_y, self.width - 130, 30),
            text="Total: 0.0",
            manager=manager,
            object_id=f"#oe_total_{self.field_name}"
        )
        self.header_widgets.append(self.total_label)
        self.ui_elements_list.append(self.total_label)

        self._update_total_label()

    def handle_event(self, event):
        """Handle UI events. Returns True if event was consumed."""
        if event.type == pygame_gui.UI_BUTTON_PRESSED:
            # Add Outcome button
            if self.add_button and event.ui_element == self.add_button:
                self._rebuild_ui(add_new=True)
                return True
            # Remove buttons
            for row in self.rows:
                if row.remove_button and event.ui_element == row.remove_button:
                    self._rebuild_ui(remove_index=row.index)
                    return True

        elif event.type == pygame_gui.UI_DROP_DOWN_MENU_CHANGED:
            # Type dropdown changed -> rebuild to show new params
            for row in self.rows:
                if row.type_dropdown and event.ui_element == row.type_dropdown:
                    self._rebuild_ui()
                    return True

        return False

    def _rebuild_ui(self, add_new=False, remove_index=None):
        """Serialize all rows, destroy, recreate."""
        # Serialize current state
        current_data = []
        for row in self.rows:
            current_data.append(row.serialize())

        if remove_index is not None and 0 <= remove_index < len(current_data):
            current_data.pop(remove_index)

        if add_new:
            current_data.append({"probability": 0.5, "type": "none", "text": "", "params": {}})

        # Rebuild
        self.build_all(current_data)

    def _update_total_label(self):
        """Update the probability total display."""
        total = 0.0
        for row in self.rows:
            try:
                total += float(row.get_probability_text())
            except (ValueError, TypeError):
                pass
        warning = "(!) " if abs(total - 1.0) > 0.01 and len(self.rows) > 0 else ""
        if self.total_label:
            self.total_label.set_text(f"{warning}Total: {total:.2f}")

    def serialize_to_json_string(self):
        """Serialize all rows to a JSON string for card data storage."""
        outcomes = [row.serialize() for row in self.rows]
        return json.dumps(outcomes)

    def get_total_height(self):
        """Total vertical space used by this editor."""
        if not self.rows and not self.add_button:
            return 60
        # header + rows + add button row
        h = 30  # header
        for row in self.rows:
            h += row.height
        h += 40  # add button row
        return h

    def _destroy_all(self):
        """Cleanup all widgets."""
        for row in self.rows:
            row.kill()
        self.rows.clear()
        for w in self.header_widgets:
            if w in self.ui_elements_list:
                self.ui_elements_list.remove(w)
            w.kill()
        self.header_widgets.clear()
        self.add_button = None
        self.total_label = None
        self.header_label = None

    def destroy(self):
        self._destroy_all()


# --- Quest Card Visual Editor Constants ---

PLACEHOLDER_TYPES = ["NPC Card", "Enemy Card", "Location Card", "Junk Card", "Document Card"]
CONDITION_TYPES = ["unit_death", "player_death", "unit_reaches_location", "turn_limit", "enemy_defeated"]
CONDITION_PARAM_DEFS_QUEST = {
    "unit_death": [("unit", "text", "NPC1")],
    "player_death": [],
    "unit_reaches_location": [("unit", "text", "NPC1"), ("location", "text", "Location1")],
    "turn_limit": [("turns", "text", "20")],
    "enemy_defeated": [("enemy", "text", "Enemy1")],
}
CHAIN_MODES = ["none", "auto_activate", "offer"]

# --- Quest Card Visual Editor Widgets ---


class PlaceholderRow:
    """Manages widgets for a single placeholder definition in the Quest Card editor."""

    def __init__(self, index, field_name, x, y, width, ui_elements_list, initial_data=None):
        self.index = index
        self.field_name = field_name
        self.x = x
        self.y = y
        self.width = width
        self.ui_elements_list = ui_elements_list
        self.widgets = []
        self.id_entry = None
        self.type_dropdown = None
        self.spawn_dropdown = None
        self.near_entry = None
        self.dist_entry = None
        self.deck_entry = None
        self.remove_button = None
        self._build(initial_data or {"id": f"NPC{index + 1}", "type": "NPC Card", "spawn": True,
                                      "spawn_near": "player", "spawn_distance": 3, "deck_file": ""})

    def _build(self, data):
        uid = f"{self.field_name}_{self.index}"
        cx = self.x
        ry = self.y

        # Line 1: idx, ID entry, type dropdown, remove button
        idx_lbl = UILabel(relative_rect=pygame.Rect(cx, ry, 20, 30), text=f"{self.index + 1}.",
                          manager=manager, object_id=f"#ph_idx_{uid}")
        self._track(idx_lbl)

        id_lbl = UILabel(relative_rect=pygame.Rect(cx + 20, ry, 20, 30), text="ID:",
                         manager=manager, object_id=f"#ph_idl_{uid}")
        self._track(id_lbl)

        self.id_entry = UITextEntryLine(relative_rect=pygame.Rect(cx + 40, ry, 70, 30),
                                         manager=manager, initial_text=str(data.get("id", "")),
                                         object_id=f"#ph_id_{uid}")
        self._track(self.id_entry)

        starting_type = data.get("type", "NPC Card")
        if starting_type not in PLACEHOLDER_TYPES:
            starting_type = PLACEHOLDER_TYPES[0]
        self.type_dropdown = UIDropDownMenu(options_list=PLACEHOLDER_TYPES, starting_option=starting_type,
                                            relative_rect=pygame.Rect(cx + 115, ry, 120, 30),
                                            manager=manager, object_id=f"#ph_type_{uid}")
        self._track(self.type_dropdown)

        self.remove_button = UIButton(relative_rect=pygame.Rect(cx + self.width - 40, ry, 40, 30),
                                      text="X", manager=manager, object_id=f"#ph_rm_{uid}")
        self._track(self.remove_button)

        # Line 2: spawn dropdown, spawn_near, distance
        ry += 35
        sp_lbl = UILabel(relative_rect=pygame.Rect(cx, ry, 45, 30), text="Spawn:",
                         manager=manager, object_id=f"#ph_spl_{uid}")
        self._track(sp_lbl)

        spawn_val = "true" if data.get("spawn", False) else "false"
        self.spawn_dropdown = UIDropDownMenu(options_list=["true", "false"], starting_option=spawn_val,
                                             relative_rect=pygame.Rect(cx + 45, ry, 55, 30),
                                             manager=manager, object_id=f"#ph_sp_{uid}")
        self._track(self.spawn_dropdown)

        nr_lbl = UILabel(relative_rect=pygame.Rect(cx + 105, ry, 30, 30), text="Near:",
                         manager=manager, object_id=f"#ph_nrl_{uid}")
        self._track(nr_lbl)

        self.near_entry = UITextEntryLine(relative_rect=pygame.Rect(cx + 135, ry, 65, 30),
                                           manager=manager, initial_text=str(data.get("spawn_near", "player")),
                                           object_id=f"#ph_nr_{uid}")
        self._track(self.near_entry)

        dt_lbl = UILabel(relative_rect=pygame.Rect(cx + 205, ry, 30, 30), text="Dist:",
                         manager=manager, object_id=f"#ph_dtl_{uid}")
        self._track(dt_lbl)

        self.dist_entry = UITextEntryLine(relative_rect=pygame.Rect(cx + 235, ry, 35, 30),
                                           manager=manager, initial_text=str(data.get("spawn_distance", 3)),
                                           object_id=f"#ph_dt_{uid}")
        self._track(self.dist_entry)

        # Line 3: deck file
        ry += 35
        dk_lbl = UILabel(relative_rect=pygame.Rect(cx, ry, 35, 30), text="Deck:",
                         manager=manager, object_id=f"#ph_dkl_{uid}")
        self._track(dk_lbl)

        self.deck_entry = UITextEntryLine(relative_rect=pygame.Rect(cx + 35, ry, self.width - 35, 30),
                                           manager=manager, initial_text=str(data.get("deck_file", "")),
                                           object_id=f"#ph_dk_{uid}")
        self._track(self.deck_entry)

        self.height = (ry - self.y) + 40

    def _track(self, widget):
        self.widgets.append(widget)
        self.ui_elements_list.append(widget)

    def serialize(self):
        ph_type = self.type_dropdown.selected_option
        if isinstance(ph_type, tuple):
            ph_type = ph_type[0]
        spawn_val = self.spawn_dropdown.selected_option
        if isinstance(spawn_val, tuple):
            spawn_val = spawn_val[0]
        try:
            dist = int(self.dist_entry.get_text())
        except (ValueError, TypeError):
            dist = 3
        result = {
            "id": self.id_entry.get_text(),
            "type": ph_type,
            "spawn": spawn_val == "true",
            "spawn_near": self.near_entry.get_text(),
            "spawn_distance": dist,
        }
        deck = self.deck_entry.get_text().strip()
        if deck:
            result["deck_file"] = deck
        return result

    def kill(self):
        for w in self.widgets:
            if w in self.ui_elements_list:
                self.ui_elements_list.remove(w)
            w.kill()
        self.widgets.clear()


class PlaceholderEditorWidget:
    """Manages a list of PlaceholderRows for the Quest Card Placeholders field."""

    def __init__(self, field_name, x, y, width, ui_elements_list):
        self.field_name = field_name
        self.x = x
        self.y = y
        self.width = width
        self.ui_elements_list = ui_elements_list
        self.rows = []
        self.add_button = None
        self.header_label = None
        self.header_widgets = []

    def build_all(self, initial_data=None):
        self._destroy_all()
        items = initial_data or []

        self.header_label = UILabel(relative_rect=pygame.Rect(self.x, self.y, self.width, 25),
                                    text="--- Placeholders ---",
                                    manager=manager, object_id=f"#ph_header_{self.field_name}")
        self.header_widgets.append(self.header_label)
        self.ui_elements_list.append(self.header_label)

        current_y = self.y + 30
        for i, item_data in enumerate(items):
            row = PlaceholderRow(i, self.field_name, self.x, current_y, self.width,
                                 self.ui_elements_list, item_data)
            self.rows.append(row)
            current_y += row.height

        self.add_button = UIButton(relative_rect=pygame.Rect(self.x, current_y, 140, 30),
                                   text="+ Add Placeholder",
                                   manager=manager, object_id=f"#ph_add_{self.field_name}")
        self.header_widgets.append(self.add_button)
        self.ui_elements_list.append(self.add_button)

    def handle_event(self, event):
        if event.type == pygame_gui.UI_BUTTON_PRESSED:
            if self.add_button and event.ui_element == self.add_button:
                self._rebuild_ui(add_new=True)
                return True
            for row in self.rows:
                if row.remove_button and event.ui_element == row.remove_button:
                    self._rebuild_ui(remove_index=row.index)
                    return True
        return False

    def _rebuild_ui(self, add_new=False, remove_index=None):
        current_data = [row.serialize() for row in self.rows]
        if remove_index is not None and 0 <= remove_index < len(current_data):
            current_data.pop(remove_index)
        if add_new:
            next_idx = len(current_data) + 1
            current_data.append({"id": f"NPC{next_idx}", "type": "NPC Card", "spawn": True,
                                 "spawn_near": "player", "spawn_distance": 3, "deck_file": ""})
        self.build_all(current_data)

    def serialize_to_json_string(self):
        return json.dumps([row.serialize() for row in self.rows])

    def get_total_height(self):
        if not self.rows and not self.add_button:
            return 60
        h = 30
        for row in self.rows:
            h += row.height
        h += 40
        return h

    def _destroy_all(self):
        for row in self.rows:
            row.kill()
        self.rows.clear()
        for w in self.header_widgets:
            if w in self.ui_elements_list:
                self.ui_elements_list.remove(w)
            w.kill()
        self.header_widgets.clear()
        self.add_button = None
        self.header_label = None

    def destroy(self):
        self._destroy_all()


class ConditionRow:
    """Manages widgets for a single condition in the Quest Card editor."""

    def __init__(self, index, field_name, x, y, width, ui_elements_list, initial_data=None):
        self.index = index
        self.field_name = field_name
        self.x = x
        self.y = y
        self.width = width
        self.ui_elements_list = ui_elements_list
        self.widgets = []
        self.param_widgets = []
        self.type_dropdown = None
        self.remove_button = None
        self._build(initial_data or {"type": "unit_death", "params": {}})

    def _build(self, data):
        cond_type = data.get("type", "unit_death")
        params = data.get("params", {})
        uid = f"{self.field_name}_{self.index}"
        cx = self.x
        ry = self.y

        # Line 1: idx, type dropdown, remove button
        idx_lbl = UILabel(relative_rect=pygame.Rect(cx, ry, 20, 30), text=f"{self.index + 1}.",
                          manager=manager, object_id=f"#cd_idx_{uid}")
        self._track(idx_lbl)

        starting = cond_type if cond_type in CONDITION_TYPES else CONDITION_TYPES[0]
        self.type_dropdown = UIDropDownMenu(options_list=CONDITION_TYPES, starting_option=starting,
                                            relative_rect=pygame.Rect(cx + 20, ry, 195, 30),
                                            manager=manager, object_id=f"#cd_type_{uid}")
        self._track(self.type_dropdown)

        self.remove_button = UIButton(relative_rect=pygame.Rect(cx + self.width - 40, ry, 40, 30),
                                      text="X", manager=manager, object_id=f"#cd_rm_{uid}")
        self._track(self.remove_button)

        # Line 2: type-specific params
        ry += 35
        param_defs = CONDITION_PARAM_DEFS_QUEST.get(cond_type, [])
        px = cx
        for pi, pdef in enumerate(param_defs):
            param_name = pdef[0]
            default_val = pdef[2] if len(pdef) > 2 else ""
            param_val = str(params.get(param_name, default_val))

            label_w = 55
            field_w = 80
            plbl = UILabel(relative_rect=pygame.Rect(px, ry, label_w, 30), text=f"{param_name}:",
                           manager=manager, object_id=f"#cd_plbl_{uid}_{pi}")
            self._track(plbl)

            pw = UITextEntryLine(relative_rect=pygame.Rect(px + label_w, ry, field_w, 30),
                                 manager=manager, initial_text=param_val,
                                 object_id=f"#cd_param_{uid}_{pi}")
            self._track(pw)
            self.param_widgets.append((param_name, pw))

            px += label_w + field_w + 5
            if px + label_w + field_w > cx + self.width:
                px = cx
                ry += 35

        self.height = (ry - self.y) + 40

    def _track(self, widget):
        self.widgets.append(widget)
        self.ui_elements_list.append(widget)

    def serialize(self):
        cond_type = self.type_dropdown.selected_option
        if isinstance(cond_type, tuple):
            cond_type = cond_type[0]
        params = {}
        for param_name, pw in self.param_widgets:
            val = pw.get_text()
            if param_name == "turns":
                try:
                    val = int(val)
                except (ValueError, TypeError):
                    val = 20
            params[param_name] = val
        return {"type": cond_type, "params": params}

    def kill(self):
        for w in self.widgets:
            if w in self.ui_elements_list:
                self.ui_elements_list.remove(w)
            w.kill()
        self.widgets.clear()
        self.param_widgets.clear()


class ConditionEditorWidget:
    """Manages a list of ConditionRows for Success/Failure Conditions."""

    def __init__(self, field_name, x, y, width, ui_elements_list):
        self.field_name = field_name
        self.x = x
        self.y = y
        self.width = width
        self.ui_elements_list = ui_elements_list
        self.rows = []
        self.add_button = None
        self.header_label = None
        self.header_widgets = []

    def build_all(self, initial_data=None):
        self._destroy_all()
        items = initial_data or []

        header_text = self.field_name.replace("_", " ")
        self.header_label = UILabel(relative_rect=pygame.Rect(self.x, self.y, self.width, 25),
                                    text=f"--- {header_text} ---",
                                    manager=manager, object_id=f"#cd_header_{self.field_name}")
        self.header_widgets.append(self.header_label)
        self.ui_elements_list.append(self.header_label)

        current_y = self.y + 30
        for i, item_data in enumerate(items):
            row = ConditionRow(i, self.field_name, self.x, current_y, self.width,
                               self.ui_elements_list, item_data)
            self.rows.append(row)
            current_y += row.height

        self.add_button = UIButton(relative_rect=pygame.Rect(self.x, current_y, 130, 30),
                                   text="+ Add Condition",
                                   manager=manager, object_id=f"#cd_add_{self.field_name}")
        self.header_widgets.append(self.add_button)
        self.ui_elements_list.append(self.add_button)

    def handle_event(self, event):
        if event.type == pygame_gui.UI_BUTTON_PRESSED:
            if self.add_button and event.ui_element == self.add_button:
                self._rebuild_ui(add_new=True)
                return True
            for row in self.rows:
                if row.remove_button and event.ui_element == row.remove_button:
                    self._rebuild_ui(remove_index=row.index)
                    return True
        elif event.type == pygame_gui.UI_DROP_DOWN_MENU_CHANGED:
            for row in self.rows:
                if row.type_dropdown and event.ui_element == row.type_dropdown:
                    self._rebuild_ui()
                    return True
        return False

    def _rebuild_ui(self, add_new=False, remove_index=None):
        current_data = [row.serialize() for row in self.rows]
        if remove_index is not None and 0 <= remove_index < len(current_data):
            current_data.pop(remove_index)
        if add_new:
            current_data.append({"type": "unit_death", "params": {}})
        self.build_all(current_data)

    def serialize_to_json_string(self):
        return json.dumps([row.serialize() for row in self.rows])

    def get_total_height(self):
        if not self.rows and not self.add_button:
            return 60
        h = 30
        for row in self.rows:
            h += row.height
        h += 40
        return h

    def _destroy_all(self):
        for row in self.rows:
            row.kill()
        self.rows.clear()
        for w in self.header_widgets:
            if w in self.ui_elements_list:
                self.ui_elements_list.remove(w)
            w.kill()
        self.header_widgets.clear()
        self.add_button = None
        self.header_label = None

    def destroy(self):
        self._destroy_all()


class RewardsEditorWidget:
    """Simple editor for the Quest Card Rewards JSON object {experience, cards}."""

    def __init__(self, field_name, x, y, width, ui_elements_list):
        self.field_name = field_name
        self.x = x
        self.y = y
        self.width = width
        self.ui_elements_list = ui_elements_list
        self.widgets = []
        self.exp_entry = None
        self.cards_entry = None

    def build_all(self, initial_data=None):
        self._destroy_all()
        data = initial_data or {}
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except (json.JSONDecodeError, TypeError):
                data = {}
        if isinstance(data, list):
            data = {}

        cx = self.x
        ry = self.y

        header = UILabel(relative_rect=pygame.Rect(cx, ry, self.width, 25),
                         text="--- Rewards ---",
                         manager=manager, object_id=f"#rw_header_{self.field_name}")
        self._track(header)

        ry += 30
        exp_lbl = UILabel(relative_rect=pygame.Rect(cx, ry, 80, 30), text="Experience:",
                          manager=manager, object_id=f"#rw_expl_{self.field_name}")
        self._track(exp_lbl)

        self.exp_entry = UITextEntryLine(relative_rect=pygame.Rect(cx + 80, ry, self.width - 80, 30),
                                         manager=manager,
                                         initial_text=str(data.get("experience", "0")),
                                         object_id=f"#rw_exp_{self.field_name}")
        self._track(self.exp_entry)

        ry += 35
        cards_lbl = UILabel(relative_rect=pygame.Rect(cx, ry, 70, 30), text="Cards:",
                            manager=manager, object_id=f"#rw_cdsl_{self.field_name}")
        self._track(cards_lbl)

        cards_val = data.get("cards", [])
        if isinstance(cards_val, list):
            cards_val = ", ".join(str(c) for c in cards_val)
        self.cards_entry = UITextEntryLine(relative_rect=pygame.Rect(cx + 70, ry, self.width - 70, 30),
                                           manager=manager,
                                           initial_text=str(cards_val),
                                           object_id=f"#rw_cds_{self.field_name}")
        self._track(self.cards_entry)

    def handle_event(self, event):
        return False

    def serialize_to_json_string(self):
        result = {}
        try:
            exp = int(self.exp_entry.get_text())
            if exp > 0:
                result["experience"] = exp
        except (ValueError, TypeError):
            pass
        cards_text = self.cards_entry.get_text().strip()
        if cards_text:
            result["cards"] = [c.strip() for c in cards_text.split(",") if c.strip()]
        return json.dumps(result)

    def get_total_height(self):
        return 100

    def _track(self, widget):
        self.widgets.append(widget)
        self.ui_elements_list.append(widget)

    def _destroy_all(self):
        for w in self.widgets:
            if w in self.ui_elements_list:
                self.ui_elements_list.remove(w)
            w.kill()
        self.widgets.clear()
        self.exp_entry = None
        self.cards_entry = None

    def destroy(self):
        self._destroy_all()


class ChainConfigEditorWidget:
    """Editor for the Quest Card Chain_Config JSON object {on_success, on_failure}."""

    def __init__(self, field_name, x, y, width, ui_elements_list):
        self.field_name = field_name
        self.x = x
        self.y = y
        self.width = width
        self.ui_elements_list = ui_elements_list
        self.widgets = []
        self.s_mode_dropdown = None
        self.s_quest_id_entry = None
        self.s_quest_deck_entry = None
        self.s_inherit_entry = None
        self.s_message_entry = None
        self.f_mode_dropdown = None
        self.f_quest_id_entry = None
        self.f_quest_deck_entry = None
        self.f_inherit_entry = None
        self.f_message_entry = None

    def build_all(self, initial_data=None):
        self._destroy_all()
        data = initial_data or {}
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except (json.JSONDecodeError, TypeError):
                data = {}
        if isinstance(data, list):
            data = {}

        cx = self.x
        ry = self.y
        w = self.width

        header = UILabel(relative_rect=pygame.Rect(cx, ry, w, 25),
                         text="--- Chain Config ---",
                         manager=manager, object_id=f"#cc_header_{self.field_name}")
        self._track(header)

        # On Success section
        ry += 30
        s_data = data.get("on_success", {}) or {}
        self._build_branch(cx, ry, w, "Success", s_data, is_success=True)

        # On Failure section
        ry += 165
        f_data = data.get("on_failure", {}) or {}
        self._build_branch(cx, ry, w, "Failure", f_data, is_success=False)

    def _build_branch(self, cx, ry, w, label, data, is_success):
        prefix = "s" if is_success else "f"
        uid = f"{self.field_name}_{prefix}"

        sec_lbl = UILabel(relative_rect=pygame.Rect(cx, ry, w, 25),
                          text=f"On {label}:",
                          manager=manager, object_id=f"#cc_{prefix}lbl_{uid}")
        self._track(sec_lbl)

        ry += 28
        mode_lbl = UILabel(relative_rect=pygame.Rect(cx, ry, 45, 30), text="Mode:",
                           manager=manager, object_id=f"#cc_{prefix}ml_{uid}")
        self._track(mode_lbl)

        mode_val = data.get("mode", "none")
        if mode_val not in CHAIN_MODES:
            mode_val = "none"
        mode_dd = UIDropDownMenu(options_list=CHAIN_MODES, starting_option=mode_val,
                                  relative_rect=pygame.Rect(cx + 45, ry, 120, 30),
                                  manager=manager, object_id=f"#cc_{prefix}mode_{uid}")
        self._track(mode_dd)

        qid_lbl = UILabel(relative_rect=pygame.Rect(cx + 170, ry, 65, 30), text="Quest ID:",
                          manager=manager, object_id=f"#cc_{prefix}ql_{uid}")
        self._track(qid_lbl)

        qid_entry = UITextEntryLine(relative_rect=pygame.Rect(cx + 235, ry, w - 235, 30),
                                     manager=manager, initial_text=str(data.get("quest_card_id", "")),
                                     object_id=f"#cc_{prefix}qid_{uid}")
        self._track(qid_entry)

        ry += 33
        dk_lbl = UILabel(relative_rect=pygame.Rect(cx, ry, 82, 30), text="Quest Deck:",
                         manager=manager, object_id=f"#cc_{prefix}dkl_{uid}")
        self._track(dk_lbl)

        dk_entry = UITextEntryLine(relative_rect=pygame.Rect(cx + 82, ry, w - 82, 30),
                                    manager=manager, initial_text=str(data.get("quest_deck", "")),
                                    object_id=f"#cc_{prefix}dk_{uid}")
        self._track(dk_entry)

        ry += 33
        inh_lbl = UILabel(relative_rect=pygame.Rect(cx, ry, 50, 30), text="Inherit:",
                          manager=manager, object_id=f"#cc_{prefix}inl_{uid}")
        self._track(inh_lbl)

        inherit_val = data.get("inherit_placeholders", [])
        if isinstance(inherit_val, list):
            inherit_val = ", ".join(str(v) for v in inherit_val)
        inh_entry = UITextEntryLine(relative_rect=pygame.Rect(cx + 50, ry, w - 50, 30),
                                     manager=manager, initial_text=str(inherit_val),
                                     object_id=f"#cc_{prefix}inh_{uid}")
        self._track(inh_entry)

        ry += 33
        msg_lbl = UILabel(relative_rect=pygame.Rect(cx, ry, 35, 30), text="Msg:",
                          manager=manager, object_id=f"#cc_{prefix}mgl_{uid}")
        self._track(msg_lbl)

        msg_entry = UITextEntryLine(relative_rect=pygame.Rect(cx + 35, ry, w - 35, 30),
                                    manager=manager, initial_text=str(data.get("message", "")),
                                    object_id=f"#cc_{prefix}msg_{uid}")
        self._track(msg_entry)

        if is_success:
            self.s_mode_dropdown = mode_dd
            self.s_quest_id_entry = qid_entry
            self.s_quest_deck_entry = dk_entry
            self.s_inherit_entry = inh_entry
            self.s_message_entry = msg_entry
        else:
            self.f_mode_dropdown = mode_dd
            self.f_quest_id_entry = qid_entry
            self.f_quest_deck_entry = dk_entry
            self.f_inherit_entry = inh_entry
            self.f_message_entry = msg_entry

    def handle_event(self, event):
        return False

    def _serialize_branch(self, mode_dd, qid_entry, dk_entry, inh_entry, msg_entry):
        if mode_dd is None:
            return None
        mode = mode_dd.selected_option
        if isinstance(mode, tuple):
            mode = mode[0]
        if mode == "none":
            return None
        result = {"mode": mode}
        qid = qid_entry.get_text().strip()
        if qid:
            result["quest_card_id"] = qid
        dk = dk_entry.get_text().strip()
        if dk:
            result["quest_deck"] = dk
        inh = inh_entry.get_text().strip()
        if inh:
            result["inherit_placeholders"] = [s.strip() for s in inh.split(",") if s.strip()]
        msg = msg_entry.get_text().strip()
        if msg:
            result["message"] = msg
        return result

    def serialize_to_json_string(self):
        result = {}
        s_branch = self._serialize_branch(self.s_mode_dropdown, self.s_quest_id_entry,
                                           self.s_quest_deck_entry, self.s_inherit_entry,
                                           self.s_message_entry)
        if s_branch:
            result["on_success"] = s_branch
        f_branch = self._serialize_branch(self.f_mode_dropdown, self.f_quest_id_entry,
                                           self.f_quest_deck_entry, self.f_inherit_entry,
                                           self.f_message_entry)
        if f_branch:
            result["on_failure"] = f_branch
        return json.dumps(result)

    def get_total_height(self):
        return 360

    def _track(self, widget):
        self.widgets.append(widget)
        self.ui_elements_list.append(widget)

    def _destroy_all(self):
        for w in self.widgets:
            if w in self.ui_elements_list:
                self.ui_elements_list.remove(w)
            w.kill()
        self.widgets.clear()
        self.s_mode_dropdown = None
        self.s_quest_id_entry = None
        self.s_quest_deck_entry = None
        self.s_inherit_entry = None
        self.s_message_entry = None
        self.f_mode_dropdown = None
        self.f_quest_id_entry = None
        self.f_quest_deck_entry = None
        self.f_inherit_entry = None
        self.f_message_entry = None

    def destroy(self):
        self._destroy_all()


# --- Location Card Visual Editor Widgets ---

LOCATION_OUTCOME_CARD_TYPES = ["Junk Card", "NPC Card", "Enemy Card", "Document Card", "None"]
LOCATION_CHOICE_ACTION_TYPES = ["draw_card", "heal", "trade", "shop", "sell", "exit"]


class LocationOutcomeRow:
    """Manages widgets for a single Location Card outcome entry."""

    def __init__(self, index, field_name, x, y, width, ui_elements_list, initial_data=None):
        self.index = index
        self.field_name = field_name
        self.x = x
        self.y = y
        self.width = width
        self.ui_elements_list = ui_elements_list
        self.widgets = []
        self.prob_entry = None
        self.type_dropdown = None
        self.deck_entry = None
        self.remove_button = None
        self._build(initial_data or {"probability": 0.5, "card_type": "Junk Card", "deck_file": ""})

    def _build(self, data):
        uid = f"{self.field_name}_{self.index}"
        cx = self.x
        ry = self.y

        # Line 1: idx, probability, card_type dropdown, remove button
        idx_lbl = UILabel(relative_rect=pygame.Rect(cx, ry, 20, 30), text=f"{self.index + 1}.",
                          manager=manager, object_id=f"#lo_idx_{uid}")
        self._track(idx_lbl)

        prob_lbl = UILabel(relative_rect=pygame.Rect(cx + 20, ry, 30, 30), text="Prob:",
                           manager=manager, object_id=f"#lo_plbl_{uid}")
        self._track(prob_lbl)

        self.prob_entry = UITextEntryLine(relative_rect=pygame.Rect(cx + 50, ry, 45, 30),
                                          manager=manager, initial_text=str(data.get("probability", 0.5)),
                                          object_id=f"#lo_prob_{uid}")
        self._track(self.prob_entry)

        ct_lbl = UILabel(relative_rect=pygame.Rect(cx + 100, ry, 30, 30), text="Type:",
                         manager=manager, object_id=f"#lo_ctl_{uid}")
        self._track(ct_lbl)

        card_type = data.get("card_type", "Junk Card")
        if card_type not in LOCATION_OUTCOME_CARD_TYPES:
            card_type = LOCATION_OUTCOME_CARD_TYPES[0]
        self.type_dropdown = UIDropDownMenu(options_list=LOCATION_OUTCOME_CARD_TYPES, starting_option=card_type,
                                            relative_rect=pygame.Rect(cx + 130, ry, 110, 30),
                                            manager=manager, object_id=f"#lo_type_{uid}")
        self._track(self.type_dropdown)

        self.remove_button = UIButton(relative_rect=pygame.Rect(cx + self.width - 40, ry, 40, 30),
                                      text="X", manager=manager, object_id=f"#lo_rm_{uid}")
        self._track(self.remove_button)

        # Line 2: deck file
        ry += 35
        dk_lbl = UILabel(relative_rect=pygame.Rect(cx, ry, 35, 30), text="Deck:",
                         manager=manager, object_id=f"#lo_dkl_{uid}")
        self._track(dk_lbl)

        self.deck_entry = UITextEntryLine(relative_rect=pygame.Rect(cx + 35, ry, self.width - 35, 30),
                                           manager=manager, initial_text=str(data.get("deck_file", "")),
                                           object_id=f"#lo_dk_{uid}")
        self._track(self.deck_entry)

        self.height = (ry - self.y) + 40

    def _track(self, widget):
        self.widgets.append(widget)
        self.ui_elements_list.append(widget)

    def serialize(self):
        card_type = self.type_dropdown.selected_option
        if isinstance(card_type, tuple):
            card_type = card_type[0]
        try:
            prob = float(self.prob_entry.get_text())
        except (ValueError, TypeError):
            prob = 0.0
        result = {"probability": prob, "card_type": card_type}
        deck = self.deck_entry.get_text().strip()
        if deck:
            result["deck_file"] = deck
        return result

    def get_probability_text(self):
        return self.prob_entry.get_text() if self.prob_entry else "0"

    def kill(self):
        for w in self.widgets:
            if w in self.ui_elements_list:
                self.ui_elements_list.remove(w)
            w.kill()
        self.widgets.clear()


class LocationOutcomeEditorWidget:
    """Manages a list of LocationOutcomeRows for Location Card Outcomes."""

    def __init__(self, field_name, x, y, width, ui_elements_list):
        self.field_name = field_name
        self.x = x
        self.y = y
        self.width = width
        self.ui_elements_list = ui_elements_list
        self.rows = []
        self.add_button = None
        self.total_label = None
        self.header_label = None
        self.header_widgets = []

    def build_all(self, initial_data=None):
        self._destroy_all()
        items = initial_data or []

        header_text = self.field_name.replace("_", " ")
        self.header_label = UILabel(relative_rect=pygame.Rect(self.x, self.y, self.width, 25),
                                    text=f"--- {header_text} ---",
                                    manager=manager, object_id=f"#lo_header_{self.field_name}")
        self.header_widgets.append(self.header_label)
        self.ui_elements_list.append(self.header_label)

        current_y = self.y + 30
        for i, item_data in enumerate(items):
            row = LocationOutcomeRow(i, self.field_name, self.x, current_y, self.width,
                                      self.ui_elements_list, item_data)
            self.rows.append(row)
            current_y += row.height

        self.add_button = UIButton(relative_rect=pygame.Rect(self.x, current_y, 120, 30),
                                   text="+ Add Outcome",
                                   manager=manager, object_id=f"#lo_add_{self.field_name}")
        self.header_widgets.append(self.add_button)
        self.ui_elements_list.append(self.add_button)

        self.total_label = UILabel(relative_rect=pygame.Rect(self.x + 130, current_y, self.width - 130, 30),
                                   text="Total: 0.0",
                                   manager=manager, object_id=f"#lo_total_{self.field_name}")
        self.header_widgets.append(self.total_label)
        self.ui_elements_list.append(self.total_label)

        self._update_total_label()

    def handle_event(self, event):
        if event.type == pygame_gui.UI_BUTTON_PRESSED:
            if self.add_button and event.ui_element == self.add_button:
                self._rebuild_ui(add_new=True)
                return True
            for row in self.rows:
                if row.remove_button and event.ui_element == row.remove_button:
                    self._rebuild_ui(remove_index=row.index)
                    return True
        return False

    def _rebuild_ui(self, add_new=False, remove_index=None):
        current_data = [row.serialize() for row in self.rows]
        if remove_index is not None and 0 <= remove_index < len(current_data):
            current_data.pop(remove_index)
        if add_new:
            current_data.append({"probability": 0.5, "card_type": "Junk Card", "deck_file": ""})
        self.build_all(current_data)

    def _update_total_label(self):
        total = 0.0
        for row in self.rows:
            try:
                total += float(row.get_probability_text())
            except (ValueError, TypeError):
                pass
        warning = "(!) " if abs(total - 1.0) > 0.01 and len(self.rows) > 0 else ""
        if self.total_label:
            self.total_label.set_text(f"{warning}Total: {total:.2f}")

    def serialize_to_json_string(self):
        return json.dumps([row.serialize() for row in self.rows])

    def get_total_height(self):
        if not self.rows and not self.add_button:
            return 60
        h = 30
        for row in self.rows:
            h += row.height
        h += 40
        return h

    def _destroy_all(self):
        for row in self.rows:
            row.kill()
        self.rows.clear()
        for w in self.header_widgets:
            if w in self.ui_elements_list:
                self.ui_elements_list.remove(w)
            w.kill()
        self.header_widgets.clear()
        self.add_button = None
        self.total_label = None
        self.header_label = None

    def destroy(self):
        self._destroy_all()


class LocationChoiceRow:
    """Manages widgets for a single Location Card choice entry."""

    def __init__(self, index, field_name, x, y, width, ui_elements_list, initial_data=None):
        self.index = index
        self.field_name = field_name
        self.x = x
        self.y = y
        self.width = width
        self.ui_elements_list = ui_elements_list
        self.widgets = []
        self.name_entry = None
        self.action_dropdown = None
        self.costs_action_dropdown = None
        self.deck_entry = None
        self.remove_button = None
        self._build(initial_data or {"name": "Search", "action": "draw_card",
                                      "costs_action": True, "params": {}})

    def _build(self, data):
        uid = f"{self.field_name}_{self.index}"
        cx = self.x
        ry = self.y

        # Line 1: idx, name entry, action dropdown, remove button
        idx_lbl = UILabel(relative_rect=pygame.Rect(cx, ry, 20, 30), text=f"{self.index + 1}.",
                          manager=manager, object_id=f"#lc_idx_{uid}")
        self._track(idx_lbl)

        nm_lbl = UILabel(relative_rect=pygame.Rect(cx + 20, ry, 35, 30), text="Name:",
                         manager=manager, object_id=f"#lc_nml_{uid}")
        self._track(nm_lbl)

        self.name_entry = UITextEntryLine(relative_rect=pygame.Rect(cx + 55, ry, 80, 30),
                                           manager=manager, initial_text=str(data.get("name", "Search")),
                                           object_id=f"#lc_nm_{uid}")
        self._track(self.name_entry)

        action = data.get("action", "draw_card")
        if action not in LOCATION_CHOICE_ACTION_TYPES:
            action = LOCATION_CHOICE_ACTION_TYPES[0]
        self.action_dropdown = UIDropDownMenu(options_list=LOCATION_CHOICE_ACTION_TYPES, starting_option=action,
                                               relative_rect=pygame.Rect(cx + 140, ry, 100, 30),
                                               manager=manager, object_id=f"#lc_act_{uid}")
        self._track(self.action_dropdown)

        self.remove_button = UIButton(relative_rect=pygame.Rect(cx + self.width - 40, ry, 40, 30),
                                      text="X", manager=manager, object_id=f"#lc_rm_{uid}")
        self._track(self.remove_button)

        # Line 2: costs_action, deck param
        ry += 35
        ca_lbl = UILabel(relative_rect=pygame.Rect(cx, ry, 75, 30), text="Costs Action:",
                         manager=manager, object_id=f"#lc_cal_{uid}")
        self._track(ca_lbl)

        costs_val = "true" if data.get("costs_action", True) else "false"
        self.costs_action_dropdown = UIDropDownMenu(options_list=["true", "false"], starting_option=costs_val,
                                                     relative_rect=pygame.Rect(cx + 75, ry, 55, 30),
                                                     manager=manager, object_id=f"#lc_ca_{uid}")
        self._track(self.costs_action_dropdown)

        dk_lbl = UILabel(relative_rect=pygame.Rect(cx + 135, ry, 35, 30), text="Deck:",
                         manager=manager, object_id=f"#lc_dkl_{uid}")
        self._track(dk_lbl)

        params = data.get("params", {})
        deck_val = params.get("deck", "")
        self.deck_entry = UITextEntryLine(relative_rect=pygame.Rect(cx + 170, ry, self.width - 170, 30),
                                           manager=manager, initial_text=str(deck_val),
                                           object_id=f"#lc_dk_{uid}")
        self._track(self.deck_entry)

        self.height = (ry - self.y) + 40

    def _track(self, widget):
        self.widgets.append(widget)
        self.ui_elements_list.append(widget)

    def serialize(self):
        action = self.action_dropdown.selected_option
        if isinstance(action, tuple):
            action = action[0]
        costs_val = self.costs_action_dropdown.selected_option
        if isinstance(costs_val, tuple):
            costs_val = costs_val[0]
        result = {
            "name": self.name_entry.get_text(),
            "action": action,
            "costs_action": costs_val == "true",
        }
        deck = self.deck_entry.get_text().strip()
        if deck:
            result["params"] = {"deck": deck}
        else:
            result["params"] = {}
        return result

    def kill(self):
        for w in self.widgets:
            if w in self.ui_elements_list:
                self.ui_elements_list.remove(w)
            w.kill()
        self.widgets.clear()


class LocationChoiceEditorWidget:
    """Manages a list of LocationChoiceRows for Location Card Choices."""

    def __init__(self, field_name, x, y, width, ui_elements_list):
        self.field_name = field_name
        self.x = x
        self.y = y
        self.width = width
        self.ui_elements_list = ui_elements_list
        self.rows = []
        self.add_button = None
        self.header_label = None
        self.header_widgets = []

    def build_all(self, initial_data=None):
        self._destroy_all()
        items = initial_data or []

        header_text = self.field_name.replace("_", " ")
        self.header_label = UILabel(relative_rect=pygame.Rect(self.x, self.y, self.width, 25),
                                    text=f"--- {header_text} ---",
                                    manager=manager, object_id=f"#lc_header_{self.field_name}")
        self.header_widgets.append(self.header_label)
        self.ui_elements_list.append(self.header_label)

        current_y = self.y + 30
        for i, item_data in enumerate(items):
            row = LocationChoiceRow(i, self.field_name, self.x, current_y, self.width,
                                     self.ui_elements_list, item_data)
            self.rows.append(row)
            current_y += row.height

        self.add_button = UIButton(relative_rect=pygame.Rect(self.x, current_y, 120, 30),
                                   text="+ Add Choice",
                                   manager=manager, object_id=f"#lc_add_{self.field_name}")
        self.header_widgets.append(self.add_button)
        self.ui_elements_list.append(self.add_button)

    def handle_event(self, event):
        if event.type == pygame_gui.UI_BUTTON_PRESSED:
            if self.add_button and event.ui_element == self.add_button:
                self._rebuild_ui(add_new=True)
                return True
            for row in self.rows:
                if row.remove_button and event.ui_element == row.remove_button:
                    self._rebuild_ui(remove_index=row.index)
                    return True
        return False

    def _rebuild_ui(self, add_new=False, remove_index=None):
        current_data = [row.serialize() for row in self.rows]
        if remove_index is not None and 0 <= remove_index < len(current_data):
            current_data.pop(remove_index)
        if add_new:
            current_data.append({"name": "Search", "action": "draw_card",
                                 "costs_action": True, "params": {}})
        self.build_all(current_data)

    def serialize_to_json_string(self):
        return json.dumps([row.serialize() for row in self.rows])

    def get_total_height(self):
        if not self.rows and not self.add_button:
            return 60
        h = 30
        for row in self.rows:
            h += row.height
        h += 40
        return h

    def _destroy_all(self):
        for row in self.rows:
            row.kill()
        self.rows.clear()
        for w in self.header_widgets:
            if w in self.ui_elements_list:
                self.ui_elements_list.remove(w)
            w.kill()
        self.header_widgets.clear()
        self.add_button = None
        self.header_label = None

    def destroy(self):
        self._destroy_all()


# CardPreview class (unchanged)
class CardPreview:
    def __init__(self, card_data, card_id, back_action, edit_action=None):
        self.card_data = card_data
        self.card_id = card_id
        self.back_action = back_action
        self.edit_action = edit_action
        
        manager.clear_and_reset()
        
        card_scaled_width = int(CARD_WIDTH * CARD_SCALE)
        card_scaled_height = int(CARD_HEIGHT * CARD_SCALE)
        self.card_rect = pygame.Rect((WINDOW_WIDTH - card_scaled_width) // 2,
                                   (WINDOW_HEIGHT - card_scaled_height) // 2,
                                   card_scaled_width, card_scaled_height)
        
        self.title = UILabel(
            relative_rect=pygame.Rect(0, 20, WINDOW_WIDTH, 40),
            text="Card Preview",
            manager=manager,
            object_id="#title_label",
            anchors={'centerx': 'centerx'}
        )
        
        button_y = self.card_rect.bottom + 20
        button_width = 150
        button_spacing = 20
        
        if self.edit_action:
            total_button_width = button_width * 2 + button_spacing
            button_x_start = (WINDOW_WIDTH - total_button_width) // 2
            self.back_button = UIButton(
                relative_rect=pygame.Rect(button_x_start, button_y, button_width, 40),
                text="Back to Menu",
                manager=manager,
                object_id="#back_to_menu"
            )
            self.edit_button = UIButton(
                relative_rect=pygame.Rect(button_x_start + button_width + button_spacing, 
                                        button_y, button_width, 40),
                text="Continue Editing",
                manager=manager,
                object_id="#continue_editing"
            )
        else:
            total_button_width = button_width
            button_x_start = (WINDOW_WIDTH - total_button_width) // 2
            self.back_button = UIButton(
                relative_rect=pygame.Rect(button_x_start, button_y, button_width, 40),
                text="Back",
                manager=manager,
                object_id="#back_to_menu"
            )
            self.edit_button = None

    def handle_event(self, event):
        if event.type == pygame_gui.UI_BUTTON_PRESSED:
            if event.ui_element == self.back_button:
                self.back_action()
            elif self.edit_button and event.ui_element == self.edit_button:
                self.edit_action()

    def draw(self):
        screen.fill(DARK_CHARCOAL)
        
        card_surface = pygame.Surface((CARD_WIDTH, CARD_HEIGHT))
        card_surface.fill(CARD_BG)  # Card background
        
        bg_path = self.card_data["data"].get("Background Image", 
                                           self.card_data["data"].get("Background Image File Path", ""))
        if bg_path and os.path.exists(bg_path):
            try:
                bg_image = pygame.image.load(bg_path).convert_alpha()
                bg_image = pygame.transform.scale(bg_image, (CARD_WIDTH, CARD_HEIGHT))
                card_surface.blit(bg_image, (0, 0))
            except pygame.error:
                pass

        image_key = {
            "Junk Card": "Junk Image" if "Junk Image" in self.card_data["data"] else "Junk Image File Path",
            "Enemy Card": "Enemy Image File Path",
            "Boss Card": "Boss Image File Path",
            "NPC Card": "NPC Image File Path",
            "Location Card": "Location Image File Path",
            "Document Card": "Background Image",
            "Transition Card": "Background Image"
        }.get(self.card_data["card_type"], "Background Image")
        image_path = self.card_data["data"].get(image_key, "")
        if image_path and os.path.exists(image_path):
            try:
                image = pygame.image.load(image_path).convert_alpha()
                image_scaled = pygame.transform.scale(image, (CARD_WIDTH//2, CARD_HEIGHT//2))
                image_rect = image_scaled.get_rect(center=(CARD_WIDTH//2, CARD_HEIGHT//2))
                card_surface.blit(image_scaled, image_rect)
            except pygame.error:
                pass

        font = pygame.font.Font(None, int(72 * CARD_SCALE))
        y_pos = int(20 * CARD_SCALE)
        name = self.card_data["data"].get("Name", 
                                        self.card_data["data"].get("Default Name", "Unnamed"))
        name_surface = font.render(name, True, CARD_TEXT)
        name_rect = name_surface.get_rect(center=(CARD_WIDTH//2, y_pos))
        card_surface.blit(name_surface, name_rect)
        y_pos += int(120 * CARD_SCALE)

        for key, value in self.card_data["data"].items():
            if key not in ["Name", "Default Name", "Background Image", "Background Image File Path", 
                           "Junk Image", "Junk Image File Path", "Enemy Image File Path", 
                           "Boss Image File Path", "NPC Image File Path", 
                           "Location Image File Path",
                           "2nd_state_Weapon Image", "2nd_state_Tool Image", "2nd_state_Item Image",
                           "Book Image", "Pamphlet Image"]:
                if key in ["Upgraded Type (Weapon, Tool, Consumable, Armor)", "Upgraded Name"]:
                    value = value or "N/A"
                text = f"{key}: {value}"
                text_surface = font.render(text, True, CARD_TEXT)
                text_rect = text_surface.get_rect(center=(CARD_WIDTH//2, y_pos))
                if text_rect.width > CARD_WIDTH - 20:
                    while text_rect.width > CARD_WIDTH - 20 and len(text) > 0:
                        text = text[:-1]
                        text_surface = font.render(text + "...", True, CARD_TEXT)
                        text_rect = text_surface.get_rect(center=(CARD_WIDTH//2, y_pos))
                card_surface.blit(text_surface, text_rect)
                y_pos += int(90 * CARD_SCALE)

        scaled_card = pygame.transform.scale(card_surface, 
                                           (self.card_rect.width, self.card_rect.height))
        screen.blit(scaled_card, self.card_rect)

class CardEditor:
    def __init__(self, card_type, back_action):
        self.card_type = card_type
        self.back_action = back_action
        self.scroll_offset = 0
        self.max_scroll = 0
        self._original_positions = {}
        self._fixed_elements = set()
        self.selected_card = None
        self.ui_elements = []
        self.card_buttons = []
        self.input_boxes = []
        self.file_inputs = []
        self.dropdown_inputs = []
        self.submit_button = None
        self.delete_button = None
        self.outcome_editors = []
        self.load_cards()

    def _apply_scroll(self):
        for element in self.ui_elements:
            eid = id(element)
            if eid in self._fixed_elements:
                continue
            if eid not in self._original_positions:
                self._original_positions[eid] = (element.relative_rect.x, element.relative_rect.y)
            ox, oy = self._original_positions[eid]
            element.set_position((ox, oy - self.scroll_offset))

    def load_cards(self):
        self.outcome_editors = []
        manager.clear_and_reset()
        self.ui_elements = []
        self.card_buttons = []
        self.submit_button = None
        self.delete_button = None
        self.scroll_offset = 0
        self._original_positions = {}
        self._fixed_elements = set()

        self.title = UILabel(
            relative_rect=pygame.Rect(0, 20, WINDOW_WIDTH, 40),
            text=f"Edit {self.card_type}",
            manager=manager,
            object_id="#title_label",
            anchors={'centerx': 'centerx'}
        )
        self.ui_elements.append(self.title)
        
        self.back_button = UIButton(
            relative_rect=pygame.Rect(20, 20, 100, 40),
            text="Back",
            manager=manager,
            object_id="#back_button"
        )
        self.ui_elements.append(self.back_button)
        self._fixed_elements.add(id(self.title))
        self._fixed_elements.add(id(self.back_button))

        with open(INDEX_FILE, 'r') as f:
            index = json.load(f)

        self.cards = []
        for card_id, info in index.items():
            if info['type'] == self.card_type:
                self.cards.append((card_id, info))
        self.cards.sort(key=lambda x: x[1]['name'].lower())

        y_start = 80
        for i, (card_id, info) in enumerate(self.cards):
            y_pos = y_start + i * 60
            button = UIButton(
                relative_rect=pygame.Rect((WINDOW_WIDTH - 200) // 2, y_pos, 200, 40),
                text=info['name'],
                manager=manager,
                object_id=f"#card_{card_id}"
            )
            self.card_buttons.append((button, card_id))
            self.ui_elements.append(button)

        total_list_height = len(self.cards) * 60 + 100
        self.max_scroll = max(0, total_list_height - WINDOW_HEIGHT)

    def get_field_type(self, field, card_data):
        if field == "2nd_state_Type" and (card_data.get("subclass") in ["Junk_to_Weapon"] or 
                                          card_data.get("blueprint_subclass") in ["Blueprint_to_Weapon"]):
            return "dropdown"
        elif field == "2nd_state_Use_HP" and card_data.get("subclass") == "Junk_to_Consumable_Item":
            return "dropdown"
        elif field == "2nd_state_Use_Placeholder" and card_data.get("subclass") == "Junk_to_Consumable_Item":
            return "dropdown"
        elif field in ["range_id", "2nd_state_range_id", "2nd_State_range_id"]:
            return "dropdown"
        elif "image" in field.lower() or "file" in field.lower():
            return "file"
        elif field == "Requirements: Specific Cards":
            return "card_selection"
        else:
            return "text"

    def load_card_for_edit(self, card_id):
        self.selected_card = card_id
        self.scroll_offset = 0
        self._original_positions = {}
        self._fixed_elements = set()
        for oe in getattr(self, 'outcome_editors', []):
            oe.destroy()
        self.outcome_editors = []
        manager.clear_and_reset()
        self.ui_elements = []
        self.input_boxes = []
        self.file_inputs = []
        self.dropdown_inputs = []

        self.title = UILabel(
            relative_rect=pygame.Rect(0, 20, WINDOW_WIDTH, 40),
            text=f"Edit {self.card_type}",
            manager=manager,
            object_id="#title_label",
            anchors={'centerx': 'centerx'}
        )
        self.ui_elements.append(self.title)

        self.back_button = UIButton(
            relative_rect=pygame.Rect(20, 20, 100, 40),
            text="Back",
            manager=manager,
            object_id="#back_button"
        )
        self.ui_elements.append(self.back_button)

        self.submit_button = UIButton(
            relative_rect=pygame.Rect((WINDOW_WIDTH - 200) // 2, WINDOW_HEIGHT - 60, 200, 40),
            text="Submit",
            manager=manager,
            object_id="#submit_button"
        )
        self.ui_elements.append(self.submit_button)

        self.delete_button = UIButton(
            relative_rect=pygame.Rect((WINDOW_WIDTH - 200) // 2 - 220, WINDOW_HEIGHT - 60, 200, 40),
            text="Delete",
            manager=manager,
            object_id="#delete_button"
        )
        self.ui_elements.append(self.delete_button)
        self._fixed_elements.add(id(self.title))
        self._fixed_elements.add(id(self.back_button))
        self._fixed_elements.add(id(self.submit_button))
        self._fixed_elements.add(id(self.delete_button))

        card_file = os.path.join("cards", f"{card_id}.json")
        with open(card_file, 'r') as f:
            card_data = json.load(f)
        
        y_start = 80
        if card_data["card_type"] == "Junk Card" and card_data.get("states") == 2:
            left_field_names = [
                "Name", "Description", "Raw Material Value", "Refined Material Value",
                "Metal Value", "Wood Value", "Background Image", "Junk Image"
            ]
            middle_field_names = [
                "Requirements: Raw Materials", "Requirements: Refined Materials",
                "Requirements: Wood", "Requirements: Metal", "Requirements: Specific Cards"
            ]
            left_fields = [(k, v) for k, v in card_data["data"].items() if k in left_field_names]
            middle_fields = [(k, v) for k, v in card_data["data"].items() if k in middle_field_names]
            right_fields = [(k, v) for k, v in card_data["data"].items() 
                           if k not in left_field_names and k not in middle_field_names]

            column_width = 300
            spacing = 50
            total_width = 3 * column_width + 2 * spacing
            left_margin = (WINDOW_WIDTH - total_width) // 2
            column1_x = left_margin
            column2_x = column1_x + column_width + spacing
            column3_x = column2_x + column_width + spacing

            for i, (field, value) in enumerate(left_fields):
                y_pos = y_start + i * 80
                label = UILabel(
                    relative_rect=pygame.Rect(column1_x, y_pos - 30, column_width, 30),
                    text=field,
                    manager=manager,
                    object_id=f"#label_{field.replace(' ', '_')}"
                )
                self.ui_elements.append(label)
                field_type = self.get_field_type(field, card_data)
                if field_type == "text":
                    entry = UITextEntryLine(
                        relative_rect=pygame.Rect(column1_x, y_pos, column_width, 40),
                        manager=manager,
                        initial_text=str(value),
                        object_id=f"#entry_{field.replace(' ', '_')}"
                    )
                    self.input_boxes.append((entry, field))
                    self.ui_elements.append(entry)
                elif field_type == "file":
                    entry = UITextEntryLine(
                        relative_rect=pygame.Rect(column1_x, y_pos, column_width - 80, 40),
                        manager=manager,
                        initial_text=str(value),
                        object_id=f"#entry_{field.replace(' ', '_')}"
                    )
                    browse = UIButton(
                        relative_rect=pygame.Rect(column1_x + column_width - 80, y_pos, 80, 40),
                        text="Browse",
                        manager=manager,
                        object_id=f"#browse_{field.replace(' ', '_')}"
                    )
                    self.file_inputs.append((entry, browse, field))
                    self.ui_elements.append(entry)
                    self.ui_elements.append(browse)

            for i, (field, value) in enumerate(middle_fields):
                y_pos = y_start + i * 80
                label = UILabel(
                    relative_rect=pygame.Rect(column2_x, y_pos - 30, column_width, 30),
                    text=field,
                    manager=manager,
                    object_id=f"#label_{field.replace(' ', '_')}"
                )
                self.ui_elements.append(label)
                field_type = self.get_field_type(field, card_data)
                if field_type == "text":
                    entry = UITextEntryLine(
                        relative_rect=pygame.Rect(column2_x, y_pos, column_width, 40),
                        manager=manager,
                        initial_text=str(value),
                        object_id=f"#entry_{field.replace(' ', '_')}"
                    )
                    self.input_boxes.append((entry, field))
                    self.ui_elements.append(entry)
                elif field_type == "card_selection":
                    entry = UITextEntryLine(
                        relative_rect=pygame.Rect(column2_x, y_pos, column_width - 80, 40),
                        manager=manager,
                        initial_text=str(value),
                        object_id=f"#entry_{field.replace(' ', '_')}"
                    )
                    browse = UIButton(
                        relative_rect=pygame.Rect(column2_x + column_width - 80, y_pos, 80, 40),
                        text="Browse",
                        manager=manager,
                        object_id=f"#browse_{field.replace(' ', '_')}"
                    )
                    self.input_boxes.append((entry, field))
                    self.ui_elements.append(entry)
                    self.ui_elements.append(browse)

            for i, (field, value) in enumerate(right_fields):
                y_pos = y_start + i * 80
                label = UILabel(
                    relative_rect=pygame.Rect(column3_x, y_pos - 30, column_width, 30),
                    text=field,
                    manager=manager,
                    object_id=f"#label_{field.replace(' ', '_')}"
                )
                self.ui_elements.append(label)
                field_type = self.get_field_type(field, card_data)
                if field_type == "text":
                    entry = UITextEntryLine(
                        relative_rect=pygame.Rect(column3_x, y_pos, column_width, 40),
                        manager=manager,
                        initial_text=str(value),
                        object_id=f"#entry_{field.replace(' ', '_')}"
                    )
                    self.input_boxes.append((entry, field))
                    self.ui_elements.append(entry)
                elif field_type == "file":
                    entry = UITextEntryLine(
                        relative_rect=pygame.Rect(column3_x, y_pos, column_width - 80, 40),
                        manager=manager,
                        initial_text=str(value),
                        object_id=f"#entry_{field.replace(' ', '_')}"
                    )
                    browse = UIButton(
                        relative_rect=pygame.Rect(column3_x + column_width - 80, y_pos, 80, 40),
                        text="Browse",
                        manager=manager,
                        object_id=f"#browse_{field.replace(' ', '_')}"
                    )
                    self.file_inputs.append((entry, browse, field))
                    self.ui_elements.append(entry)
                    self.ui_elements.append(browse)
                elif field_type == "dropdown":
                    if field == "2nd_state_Type":
                        options = ["Melee", "Projectile"]
                        default = value if value in options else options[0]
                    elif field == "2nd_state_Use_HP":
                        options = HP_OPTIONS
                        default = value if isinstance(value, str) and value in options else (value[0] if isinstance(value, list) and value and value[0] in options else options[0])
                    elif field == "2nd_state_Use_Placeholder":
                        options = PLACEHOLDER_OPTIONS
                        default = value if isinstance(value, str) and value in options else (value[0] if isinstance(value, list) and value and value[0] in options else options[0])
                    elif field in ["range_id", "2nd_state_range_id", "2nd_State_range_id"]:
                        options = RANGE_OPTIONS
                        default = value if value in options else "None"
                    else:
                        continue
                    dropdown = UIDropDownMenu(
                        options_list=options,
                        starting_option=default,
                        relative_rect=pygame.Rect(right_column_x, y_pos, column_width, 40),
                        manager=manager,
                        object_id=f"#dropdown_{field.replace(' ', '_')}"
                    )
                    self.dropdown_inputs.append((dropdown, field))
                    self.ui_elements.append(dropdown)

            max_fields = max(len(left_fields), len(middle_fields), len(right_fields))
            total_form_height = max_fields * 80 + 140
            self.max_scroll = max(0, total_form_height - WINDOW_HEIGHT)
        elif card_data["card_type"] == "Transition Card":
            # Transition Card editor with visual outcome editors
            # Separate outcome fields from standard fields
            outcomes_json = card_data["data"].pop("Outcomes", "[]")
            outcomes_2_json = card_data["data"].pop("2nd_state_Outcomes", "[]")

            state_1_fields = {k: v for k, v in card_data["data"].items() if not k.lower().startswith("2nd_")}
            state_2_fields = {k: v for k, v in card_data["data"].items() if k.lower().startswith("2nd_")}

            column_width = 400
            left_column_x = (WINDOW_WIDTH - 2 * column_width - 50) // 2
            right_column_x = left_column_x + column_width + 50

            for i, (field, value) in enumerate(state_1_fields.items()):
                y_pos = y_start + i * 80
                label = UILabel(
                    relative_rect=pygame.Rect(left_column_x, y_pos - 30, column_width, 30),
                    text=field,
                    manager=manager,
                    object_id=f"#label_{field.replace(' ', '_')}"
                )
                self.ui_elements.append(label)
                field_type = "file" if any(img in field.lower() for img in ["image", "file"]) else "text"
                if field_type == "text":
                    entry = UITextEntryLine(
                        relative_rect=pygame.Rect(left_column_x, y_pos, column_width, 40),
                        manager=manager,
                        initial_text=str(value),
                        object_id=f"#entry_{field.replace(' ', '_')}"
                    )
                    self.input_boxes.append((entry, field))
                    self.ui_elements.append(entry)
                else:
                    entry = UITextEntryLine(
                        relative_rect=pygame.Rect(left_column_x, y_pos, column_width - 80, 40),
                        manager=manager,
                        initial_text=str(value),
                        object_id=f"#entry_{field.replace(' ', '_')}"
                    )
                    browse = UIButton(
                        relative_rect=pygame.Rect(left_column_x + column_width - 80, y_pos, 80, 40),
                        text="Browse",
                        manager=manager,
                        object_id=f"#browse_{field.replace(' ', '_')}"
                    )
                    self.file_inputs.append((entry, browse, field))
                    self.ui_elements.append(entry)
                    self.ui_elements.append(browse)

            for i, (field, value) in enumerate(state_2_fields.items()):
                y_pos = y_start + i * 80
                label = UILabel(
                    relative_rect=pygame.Rect(right_column_x, y_pos - 30, column_width, 30),
                    text=field,
                    manager=manager,
                    object_id=f"#label_{field.replace(' ', '_')}"
                )
                self.ui_elements.append(label)
                field_type = "file" if any(img in field.lower() for img in ["image", "file"]) else "text"
                if field_type == "text":
                    entry = UITextEntryLine(
                        relative_rect=pygame.Rect(right_column_x, y_pos, column_width, 40),
                        manager=manager,
                        initial_text=str(value),
                        object_id=f"#entry_{field.replace(' ', '_')}"
                    )
                    self.input_boxes.append((entry, field))
                    self.ui_elements.append(entry)
                else:
                    entry = UITextEntryLine(
                        relative_rect=pygame.Rect(right_column_x, y_pos, column_width - 80, 40),
                        manager=manager,
                        initial_text=str(value),
                        object_id=f"#entry_{field.replace(' ', '_')}"
                    )
                    browse = UIButton(
                        relative_rect=pygame.Rect(right_column_x + column_width - 80, y_pos, 80, 40),
                        text="Browse",
                        manager=manager,
                        object_id=f"#browse_{field.replace(' ', '_')}"
                    )
                    self.file_inputs.append((entry, browse, field))
                    self.ui_elements.append(entry)
                    self.ui_elements.append(browse)

            # Visual outcome editors below the standard fields
            outcome_y = y_start + max(len(state_1_fields), len(state_2_fields)) * 80 + 20

            # Parse existing outcomes
            try:
                outcomes_list = json.loads(outcomes_json) if isinstance(outcomes_json, str) else (outcomes_json or [])
            except (json.JSONDecodeError, TypeError):
                outcomes_list = []
            try:
                outcomes_2_list = json.loads(outcomes_2_json) if isinstance(outcomes_2_json, str) else (outcomes_2_json or [])
            except (json.JSONDecodeError, TypeError):
                outcomes_2_list = []

            oe_left = OutcomeEditorWidget("Outcomes", "transition", left_column_x, outcome_y, column_width, self.ui_elements)
            oe_left.build_all(outcomes_list)
            self.outcome_editors.append(oe_left)

            oe_right = OutcomeEditorWidget("2nd_state_Outcomes", "transition", right_column_x, outcome_y, column_width, self.ui_elements)
            oe_right.build_all(outcomes_2_list)
            self.outcome_editors.append(oe_right)

            total_form_height = outcome_y + max(oe_left.get_total_height(), oe_right.get_total_height()) + 60
            self.max_scroll = max(0, total_form_height - WINDOW_HEIGHT)
        elif card_data["card_type"] == "Instance Card":
            # Instance Card editor with visual outcome editor
            outcomes_json = card_data["data"].pop("Outcomes", "[]")

            fields = card_data["data"]
            column_width = 400
            column_x = (WINDOW_WIDTH - column_width) // 2

            for i, (field, value) in enumerate(fields.items()):
                y_pos = y_start + i * 80
                label = UILabel(
                    relative_rect=pygame.Rect(column_x, y_pos - 30, column_width, 30),
                    text=field,
                    manager=manager,
                    object_id=f"#label_{field.replace(' ', '_')}"
                )
                self.ui_elements.append(label)
                field_type = self.get_field_type(field, card_data)
                if field_type == "dropdown":
                    if field == "Subclass":
                        options = ["Environmental", "Combat", "Social", "Discovery", "Danger"]
                        default = value if value in options else options[0]
                    else:
                        options = RANGE_OPTIONS if "range" in field.lower() else [str(value)]
                        default = str(value)
                    dropdown = UIDropDownMenu(
                        options_list=options,
                        starting_option=default,
                        relative_rect=pygame.Rect(column_x, y_pos, column_width, 40),
                        manager=manager,
                        object_id=f"#dropdown_{field.replace(' ', '_')}"
                    )
                    self.dropdown_inputs.append((dropdown, field))
                    self.ui_elements.append(dropdown)
                elif field_type == "file":
                    entry = UITextEntryLine(
                        relative_rect=pygame.Rect(column_x, y_pos, column_width - 80, 40),
                        manager=manager,
                        initial_text=str(value),
                        object_id=f"#entry_{field.replace(' ', '_')}"
                    )
                    browse = UIButton(
                        relative_rect=pygame.Rect(column_x + column_width - 80, y_pos, 80, 40),
                        text="Browse",
                        manager=manager,
                        object_id=f"#browse_{field.replace(' ', '_')}"
                    )
                    self.file_inputs.append((entry, browse, field))
                    self.ui_elements.append(entry)
                    self.ui_elements.append(browse)
                else:
                    entry = UITextEntryLine(
                        relative_rect=pygame.Rect(column_x, y_pos, column_width, 40),
                        manager=manager,
                        initial_text=str(value),
                        object_id=f"#entry_{field.replace(' ', '_')}"
                    )
                    self.input_boxes.append((entry, field))
                    self.ui_elements.append(entry)

            # Visual outcome editor below standard fields
            outcome_y = y_start + len(fields) * 80 + 20

            try:
                outcomes_list = json.loads(outcomes_json) if isinstance(outcomes_json, str) else (outcomes_json or [])
            except (json.JSONDecodeError, TypeError):
                outcomes_list = []

            oe = OutcomeEditorWidget("Outcomes", "instance", column_x, outcome_y, column_width, self.ui_elements)
            oe.build_all(outcomes_list)
            self.outcome_editors.append(oe)

            total_form_height = outcome_y + oe.get_total_height() + 60
            self.max_scroll = max(0, total_form_height - WINDOW_HEIGHT)
        elif card_data["card_type"] == "Quest Card":
            # Quest Card editor with visual editors for JSON fields
            placeholders_json = card_data["data"].pop("Placeholders", "[]")
            success_json = card_data["data"].pop("Success_Conditions", "[]")
            failure_json = card_data["data"].pop("Failure_Conditions", "[]")
            rewards_json = card_data["data"].pop("Rewards", "{}")
            chain_json = card_data["data"].pop("Chain_Config", "{}")

            state1_fields = {k: v for k, v in card_data["data"].items() if not k.startswith("2nd_state_")}
            state2_fields = {k: v for k, v in card_data["data"].items() if k.startswith("2nd_state_")}

            column_width = 300
            spacing = 30
            total_width = 3 * column_width + 2 * spacing
            left_margin = (WINDOW_WIDTH - total_width) // 2
            column1_x = left_margin
            column2_x = column1_x + column_width + spacing
            column3_x = column2_x + column_width + spacing

            for i, (field, value) in enumerate(state1_fields.items()):
                y_pos = y_start + i * 80
                label = UILabel(relative_rect=pygame.Rect(column1_x, y_pos - 30, column_width, 30),
                                text=field, manager=manager, object_id=f"#label_{field.replace(' ', '_')}")
                self.ui_elements.append(label)
                field_type = "file" if any(img in field.lower() for img in ["image", "file"]) else "text"
                if field_type == "file":
                    entry = UITextEntryLine(relative_rect=pygame.Rect(column1_x, y_pos, column_width - 80, 40),
                                            manager=manager, initial_text=str(value),
                                            object_id=f"#entry_{field.replace(' ', '_')}")
                    browse = UIButton(relative_rect=pygame.Rect(column1_x + column_width - 80, y_pos, 80, 40),
                                      text="Browse", manager=manager,
                                      object_id=f"#browse_{field.replace(' ', '_')}")
                    self.file_inputs.append((entry, browse, field))
                    self.ui_elements.append(entry)
                    self.ui_elements.append(browse)
                else:
                    entry = UITextEntryLine(relative_rect=pygame.Rect(column1_x, y_pos, column_width, 40),
                                            manager=manager, initial_text=str(value),
                                            object_id=f"#entry_{field.replace(' ', '_')}")
                    self.input_boxes.append((entry, field))
                    self.ui_elements.append(entry)

            for i, (field, value) in enumerate(state2_fields.items()):
                y_pos = y_start + i * 80
                label = UILabel(relative_rect=pygame.Rect(column3_x, y_pos - 30, column_width, 30),
                                text=field, manager=manager, object_id=f"#label_{field.replace(' ', '_')}")
                self.ui_elements.append(label)
                field_type = "file" if any(img in field.lower() for img in ["image", "file"]) else "text"
                if field_type == "file":
                    entry = UITextEntryLine(relative_rect=pygame.Rect(column3_x, y_pos, column_width - 80, 40),
                                            manager=manager, initial_text=str(value),
                                            object_id=f"#entry_{field.replace(' ', '_')}")
                    browse = UIButton(relative_rect=pygame.Rect(column3_x + column_width - 80, y_pos, 80, 40),
                                      text="Browse", manager=manager,
                                      object_id=f"#browse_{field.replace(' ', '_')}")
                    self.file_inputs.append((entry, browse, field))
                    self.ui_elements.append(entry)
                    self.ui_elements.append(browse)
                else:
                    entry = UITextEntryLine(relative_rect=pygame.Rect(column3_x, y_pos, column_width, 40),
                                            manager=manager, initial_text=str(value),
                                            object_id=f"#entry_{field.replace(' ', '_')}")
                    self.input_boxes.append((entry, field))
                    self.ui_elements.append(entry)

            # Parse JSON data for visual editors
            editor_start_y = y_start + max(len(state1_fields), len(state2_fields)) * 80 + 20

            try:
                placeholders_list = json.loads(placeholders_json) if isinstance(placeholders_json, str) else (placeholders_json or [])
            except (json.JSONDecodeError, TypeError):
                placeholders_list = []
            try:
                success_list = json.loads(success_json) if isinstance(success_json, str) else (success_json or [])
            except (json.JSONDecodeError, TypeError):
                success_list = []
            try:
                failure_list = json.loads(failure_json) if isinstance(failure_json, str) else (failure_json or [])
            except (json.JSONDecodeError, TypeError):
                failure_list = []
            try:
                rewards_obj = json.loads(rewards_json) if isinstance(rewards_json, str) else (rewards_json or {})
            except (json.JSONDecodeError, TypeError):
                rewards_obj = {}
            try:
                chain_obj = json.loads(chain_json) if isinstance(chain_json, str) else (chain_json or {})
            except (json.JSONDecodeError, TypeError):
                chain_obj = {}

            # Placeholders editor (left column)
            pe = PlaceholderEditorWidget("Placeholders", column1_x, editor_start_y,
                                         column_width, self.ui_elements)
            pe.build_all(placeholders_list)
            self.outcome_editors.append(pe)

            # Success Conditions editor (middle column)
            sc = ConditionEditorWidget("Success_Conditions", column2_x, editor_start_y,
                                        column_width, self.ui_elements)
            sc.build_all(success_list)
            self.outcome_editors.append(sc)

            # Failure Conditions editor (middle column, below success)
            fc_y = editor_start_y + sc.get_total_height() + 10
            fc = ConditionEditorWidget("Failure_Conditions", column2_x, fc_y,
                                        column_width, self.ui_elements)
            fc.build_all(failure_list)
            self.outcome_editors.append(fc)

            # Rewards editor (right column)
            rw = RewardsEditorWidget("Rewards", column3_x, editor_start_y,
                                      column_width, self.ui_elements)
            rw.build_all(rewards_obj)
            self.outcome_editors.append(rw)

            # Chain Config editor (right column, below rewards)
            cc_y = editor_start_y + rw.get_total_height() + 10
            cc = ChainConfigEditorWidget("Chain_Config", column3_x, cc_y,
                                          column_width, self.ui_elements)
            cc.build_all(chain_obj)
            self.outcome_editors.append(cc)

            total_form_height = max(
                editor_start_y + pe.get_total_height(),
                fc_y + fc.get_total_height(),
                cc_y + cc.get_total_height()
            ) + 60
            self.max_scroll = max(0, total_form_height - WINDOW_HEIGHT)
        elif card_data["card_type"] in ["Location Card", "Location/Location"]:
            # Location Card editor with visual editors for Outcomes/Choices
            outcomes_json = card_data["data"].pop("Outcomes", "[]")
            choices_json = card_data["data"].pop("Choices", "[]")
            outcomes_2_json = card_data["data"].pop("2nd_state_Outcomes", "[]")
            choices_2_json = card_data["data"].pop("2nd_state_Choices", "[]")

            state1_fields = {k: v for k, v in card_data["data"].items() if not k.startswith("2nd_state_")}
            state2_fields = {k: v for k, v in card_data["data"].items() if k.startswith("2nd_state_")}

            column_width = 300
            if state2_fields:
                left_column_x = (WINDOW_WIDTH - 2 * column_width - 100) // 2
                right_column_x = left_column_x + column_width + 100
            else:
                left_column_x = (WINDOW_WIDTH - column_width) // 2
                right_column_x = None

            for i, (field, value) in enumerate(state1_fields.items()):
                y_pos = y_start + i * 80
                label = UILabel(relative_rect=pygame.Rect(left_column_x, y_pos - 30, column_width, 30),
                                text=field, manager=manager, object_id=f"#label_{field.replace(' ', '_')}")
                self.ui_elements.append(label)
                field_type = self.get_field_type(field, card_data)
                if field_type == "dropdown":
                    options = ALLEGIANCE_TYPES if "allegiance" in field.lower() else ["false", "true"]
                    if "currency" in field.lower():
                        options = CURRENCY_TYPES
                    elif "range_type" in field.lower():
                        options = RANGE_TYPES
                    default = str(value) if str(value) in options else options[0]
                    dropdown = UIDropDownMenu(options_list=options, starting_option=default,
                                              relative_rect=pygame.Rect(left_column_x, y_pos, column_width, 40),
                                              manager=manager, object_id=f"#dropdown_{field.replace(' ', '_')}")
                    self.dropdown_inputs.append((dropdown, field))
                    self.ui_elements.append(dropdown)
                elif field_type == "file":
                    entry = UITextEntryLine(relative_rect=pygame.Rect(left_column_x, y_pos, column_width - 80, 40),
                                            manager=manager, initial_text=str(value),
                                            object_id=f"#entry_{field.replace(' ', '_')}")
                    browse = UIButton(relative_rect=pygame.Rect(left_column_x + column_width - 80, y_pos, 80, 40),
                                      text="Browse", manager=manager,
                                      object_id=f"#browse_{field.replace(' ', '_')}")
                    self.file_inputs.append((entry, browse, field))
                    self.ui_elements.append(entry)
                    self.ui_elements.append(browse)
                else:
                    entry = UITextEntryLine(relative_rect=pygame.Rect(left_column_x, y_pos, column_width, 40),
                                            manager=manager, initial_text=str(value),
                                            object_id=f"#entry_{field.replace(' ', '_')}")
                    self.input_boxes.append((entry, field))
                    self.ui_elements.append(entry)

            if right_column_x and state2_fields:
                for i, (field, value) in enumerate(state2_fields.items()):
                    y_pos = y_start + i * 80
                    label = UILabel(relative_rect=pygame.Rect(right_column_x, y_pos - 30, column_width, 30),
                                    text=field, manager=manager, object_id=f"#label_{field.replace(' ', '_')}")
                    self.ui_elements.append(label)
                    field_type = self.get_field_type(field, card_data)
                    if field_type == "dropdown":
                        options = ["false", "true"]
                        if "currency" in field.lower():
                            options = CURRENCY_TYPES
                        elif "range_type" in field.lower():
                            options = RANGE_TYPES
                        default = str(value) if str(value) in options else options[0]
                        dropdown = UIDropDownMenu(options_list=options, starting_option=default,
                                                  relative_rect=pygame.Rect(right_column_x, y_pos, column_width, 40),
                                                  manager=manager, object_id=f"#dropdown_{field.replace(' ', '_')}")
                        self.dropdown_inputs.append((dropdown, field))
                        self.ui_elements.append(dropdown)
                    elif field_type == "file":
                        entry = UITextEntryLine(relative_rect=pygame.Rect(right_column_x, y_pos, column_width - 80, 40),
                                                manager=manager, initial_text=str(value),
                                                object_id=f"#entry_{field.replace(' ', '_')}")
                        browse = UIButton(relative_rect=pygame.Rect(right_column_x + column_width - 80, y_pos, 80, 40),
                                          text="Browse", manager=manager,
                                          object_id=f"#browse_{field.replace(' ', '_')}")
                        self.file_inputs.append((entry, browse, field))
                        self.ui_elements.append(entry)
                        self.ui_elements.append(browse)
                    else:
                        entry = UITextEntryLine(relative_rect=pygame.Rect(right_column_x, y_pos, column_width, 40),
                                                manager=manager, initial_text=str(value),
                                                object_id=f"#entry_{field.replace(' ', '_')}")
                        self.input_boxes.append((entry, field))
                        self.ui_elements.append(entry)

            # Visual editors for Outcomes/Choices below standard fields
            editor_y = y_start + max(len(state1_fields), len(state2_fields) if state2_fields else 0) * 80 + 20

            try:
                outcomes_list = json.loads(outcomes_json) if isinstance(outcomes_json, str) else (outcomes_json or [])
            except (json.JSONDecodeError, TypeError):
                outcomes_list = []
            try:
                choices_list = json.loads(choices_json) if isinstance(choices_json, str) else (choices_json or [])
            except (json.JSONDecodeError, TypeError):
                choices_list = []

            oe = LocationOutcomeEditorWidget("Outcomes", left_column_x, editor_y, column_width, self.ui_elements)
            oe.build_all(outcomes_list)
            self.outcome_editors.append(oe)

            ce_y = editor_y + oe.get_total_height() + 10
            ce = LocationChoiceEditorWidget("Choices", left_column_x, ce_y, column_width, self.ui_elements)
            ce.build_all(choices_list)
            self.outcome_editors.append(ce)

            max_height = ce_y + ce.get_total_height()

            if right_column_x and state2_fields:
                try:
                    outcomes_2_list = json.loads(outcomes_2_json) if isinstance(outcomes_2_json, str) else (outcomes_2_json or [])
                except (json.JSONDecodeError, TypeError):
                    outcomes_2_list = []
                try:
                    choices_2_list = json.loads(choices_2_json) if isinstance(choices_2_json, str) else (choices_2_json or [])
                except (json.JSONDecodeError, TypeError):
                    choices_2_list = []

                oe2 = LocationOutcomeEditorWidget("2nd_state_Outcomes", right_column_x, editor_y, column_width, self.ui_elements)
                oe2.build_all(outcomes_2_list)
                self.outcome_editors.append(oe2)

                ce2_y = editor_y + oe2.get_total_height() + 10
                ce2 = LocationChoiceEditorWidget("2nd_state_Choices", right_column_x, ce2_y, column_width, self.ui_elements)
                ce2.build_all(choices_2_list)
                self.outcome_editors.append(ce2)

                max_height = max(max_height, ce2_y + ce2.get_total_height())

            total_form_height = max_height + 60
            self.max_scroll = max(0, total_form_height - WINDOW_HEIGHT)
        elif card_data.get("states") == 2:
            state_1_fields = {k: v for k, v in card_data["data"].items() if not k.lower().startswith("2nd_")}
            state_2_fields = {k: v for k, v in card_data["data"].items() if k.lower().startswith("2nd_")}
            
            column_width = 300
            left_column_x = (WINDOW_WIDTH - 2 * column_width - 100) // 2
            right_column_x = left_column_x + column_width + 100
            
            for i, (field, value) in enumerate(state_1_fields.items()):
                y_pos = y_start + i * 80
                label = UILabel(
                    relative_rect=pygame.Rect(left_column_x, y_pos - 30, column_width, 30),
                    text=field,
                    manager=manager,
                    object_id=f"#label_{field.replace(' ', '_')}"
                )
                self.ui_elements.append(label)
                field_type = "file" if any(img in field.lower() for img in ["image", "file"]) else "text"
                if field_type == "text":
                    entry = UITextEntryLine(
                        relative_rect=pygame.Rect(left_column_x, y_pos, column_width, 40),
                        manager=manager,
                        initial_text=str(value),
                        object_id=f"#entry_{field.replace(' ', '_')}"
                    )
                    self.input_boxes.append((entry, field))
                    self.ui_elements.append(entry)
                else:
                    entry = UITextEntryLine(
                        relative_rect=pygame.Rect(left_column_x, y_pos, column_width - 80, 40),
                        manager=manager,
                        initial_text=str(value),
                        object_id=f"#entry_{field.replace(' ', '_')}"
                    )
                    browse = UIButton(
                        relative_rect=pygame.Rect(left_column_x + column_width - 80, y_pos, 80, 40),
                        text="Browse",
                        manager=manager,
                        object_id=f"#browse_{field.replace(' ', '_')}"
                    )
                    self.file_inputs.append((entry, browse, field))
                    self.ui_elements.append(entry)
                    self.ui_elements.append(browse)
            
            for i, (field, value) in enumerate(state_2_fields.items()):
                y_pos = y_start + i * 80
                label = UILabel(
                    relative_rect=pygame.Rect(right_column_x, y_pos - 30, column_width, 30),
                    text=field,
                    manager=manager,
                    object_id=f"#label_{field.replace(' ', '_')}"
                )
                self.ui_elements.append(label)
                field_type = self.get_field_type(field, card_data)
                if field_type == "dropdown":
                    if field == "2nd_state_Type":
                        options = ["Melee", "Projectile"]
                        default = value if value in options else options[0]
                    elif field == "2nd_state_Use_HP":
                        options = HP_OPTIONS
                        default = value if isinstance(value, str) and value in options else (value[0] if isinstance(value, list) and value and value[0] in options else options[0])
                    elif field == "2nd_state_Use_Placeholder":
                        options = PLACEHOLDER_OPTIONS
                        default = value if isinstance(value, str) and value in options else (value[0] if isinstance(value, list) and value and value[0] in options else options[0])
                    else:
                        continue
                    dropdown = UIDropDownMenu(
                        options_list=options,
                        starting_option=default,
                        relative_rect=pygame.Rect(right_column_x, y_pos, column_width, 40),
                        manager=manager,
                        object_id=f"#dropdown_{field.replace(' ', '_')}"
                    )
                    self.dropdown_inputs.append((dropdown, field))
                    self.ui_elements.append(dropdown)
                elif field_type == "file":
                    entry = UITextEntryLine(
                        relative_rect=pygame.Rect(right_column_x, y_pos, column_width - 80, 40),
                        manager=manager,
                        initial_text=str(value),
                        object_id=f"#entry_{field.replace(' ', '_')}"
                    )
                    browse = UIButton(
                        relative_rect=pygame.Rect(right_column_x + column_width - 80, y_pos, 80, 40),
                        text="Browse",
                        manager=manager,
                        object_id=f"#browse_{field.replace(' ', '_')}"
                    )
                    self.file_inputs.append((entry, browse, field))
                    self.ui_elements.append(entry)
                    self.ui_elements.append(browse)
                else:
                    entry = UITextEntryLine(
                        relative_rect=pygame.Rect(right_column_x, y_pos, column_width, 40),
                        manager=manager,
                        initial_text=str(value),
                        object_id=f"#entry_{field.replace(' ', '_')}"
                    )
                    self.input_boxes.append((entry, field))
                    self.ui_elements.append(entry)
            
            total_form_height = max(len(state_1_fields), len(state_2_fields)) * 80 + 140
            self.max_scroll = max(0, total_form_height - WINDOW_HEIGHT)
        else:
            fields = card_data["data"]
            for i, (field, value) in enumerate(fields.items()):
                y_pos = y_start + i * 80
                label = UILabel(
                    relative_rect=pygame.Rect((WINDOW_WIDTH - 300) // 2, y_pos - 30, 300, 30),
                    text=field,
                    manager=manager,
                    object_id=f"#label_{field.replace(' ', '_')}"
                )
                self.ui_elements.append(label)
                field_type = self.get_field_type(field, card_data)
                if field_type == "text":
                    entry = UITextEntryLine(
                        relative_rect=pygame.Rect((WINDOW_WIDTH - 300) // 2, y_pos, 300, 40),
                        manager=manager,
                        initial_text=str(value),
                        object_id=f"#entry_{field.replace(' ', '_')}"
                    )
                    self.input_boxes.append((entry, field))
                    self.ui_elements.append(entry)
                elif field_type == "file":
                    entry = UITextEntryLine(
                        relative_rect=pygame.Rect((WINDOW_WIDTH - 300) // 2, y_pos, 220, 40),
                        manager=manager,
                        initial_text=str(value),
                        object_id=f"#entry_{field.replace(' ', '_')}"
                    )
                    browse = UIButton(
                        relative_rect=pygame.Rect((WINDOW_WIDTH + 240) // 2, y_pos, 80, 40),
                        text="Browse",
                        manager=manager,
                        object_id=f"#browse_{field.replace(' ', '_')}"
                    )
                    self.file_inputs.append((entry, browse, field))
                    self.ui_elements.append(entry)
                    self.ui_elements.append(browse)
                elif field_type == "dropdown":
                    options = RANGE_OPTIONS if field == "range_id" else []
                    default = value if value in options else "None"
                    dropdown = UIDropDownMenu(
                        options_list=options,
                        starting_option=default,
                        relative_rect=pygame.Rect((WINDOW_WIDTH - 300) // 2, y_pos, 300, 40),
                        manager=manager,
                        object_id=f"#dropdown_{field.replace(' ', '_')}"
                    )
                    self.dropdown_inputs.append((dropdown, field))
                    self.ui_elements.append(dropdown)
            
            total_form_height = len(fields) * 80 + 140
            self.max_scroll = max(0, total_form_height - WINDOW_HEIGHT)

    def submit_changes(self):
        if not self.selected_card:
            return

        card_file = os.path.join("cards", f"{self.selected_card}.json")
        with open(card_file, 'r') as f:
            card_data = json.load(f)

        new_data = {entry[1]: entry[0].get_text() for entry in self.input_boxes}
        new_data.update({entry[2]: entry[0].get_text() for entry in self.file_inputs})
        new_data.update({dropdown[1]: dropdown[0].selected_option[0] if isinstance(dropdown[0].selected_option, tuple) else dropdown[0].selected_option for dropdown in self.dropdown_inputs})

        # Add outcome editor data
        for oe in getattr(self, 'outcome_editors', []):
            new_data[oe.field_name] = oe.serialize_to_json_string()

        card_data["data"] = new_data

        # Validate JSON fields before saving
        is_valid, errors = validate_card_json_fields(card_data)
        if not is_valid:
            error_msg = "JSON Validation Errors:\n" + "\n".join(errors)
            print(error_msg)
            self.show_validation_error(errors)
            return

        with open(card_file, 'w') as f:
            json.dump(card_data, f, indent=2)

        with open(INDEX_FILE, 'r') as f:
            index = json.load(f)

        index[self.selected_card]["name"] = card_data["data"].get("Name",
                                                               card_data["data"].get("Default Name", "Unnamed"))

        with open(INDEX_FILE, 'w') as f:
            json.dump(index, f, indent=2)

        print(f"Card updated: {self.selected_card}")
        self.preview_card(card_data)

    def show_validation_error(self, errors):
        """Show validation errors in a popup window."""
        # Clear any existing error window
        if hasattr(self, 'error_window') and self.error_window:
            self.error_window.kill()

        error_text = "Cannot save card - JSON validation failed:\n\n"
        for error in errors:
            error_text += f"• {error}\n"
        error_text += "\nPlease fix the errors and try again."

        # Create error window
        window_width = 500
        window_height = 200 + len(errors) * 30
        window_x = (WINDOW_WIDTH - window_width) // 2
        window_y = (WINDOW_HEIGHT - window_height) // 2

        self.error_window = pygame_gui.elements.UIWindow(
            rect=pygame.Rect(window_x, window_y, window_width, window_height),
            manager=manager,
            window_display_title="Validation Error"
        )

        pygame_gui.elements.UITextBox(
            relative_rect=pygame.Rect(10, 10, window_width - 40, window_height - 80),
            html_text=error_text.replace('\n', '<br>'),
            manager=manager,
            container=self.error_window
        )

        pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect((window_width - 120) // 2, window_height - 70, 100, 40),
            text="OK",
            manager=manager,
            container=self.error_window
        )

    def delete_card(self):
        if not self.selected_card:
            return
        
        card_file = os.path.join("cards", f"{self.selected_card}.json")
        if os.path.exists(card_file):
            os.remove(card_file)
        
        with open(INDEX_FILE, 'r') as f:
            index = json.load(f)
        
        if self.selected_card in index:
            del index[self.selected_card]
        
        with open(INDEX_FILE, 'w') as f:
            json.dump(index, f, indent=2)
        
        print(f"Card deleted: {self.selected_card}")
        self.back_to_list()

    def preview_card(self, card_data):
        CardManager.instance.preview_screen = CardPreview(
            card_data,
            self.selected_card,
            CardManager.instance.back_to_main,
            lambda: self.load_card_for_edit(self.selected_card)
        )
        CardManager.instance.current_screen = "preview"
        self.selected_card = None
        self.back_action()

    def back_to_list(self):
        if self.selected_card:
            self.selected_card = None
            self.load_cards()
        else:
            self.back_action()

    def handle_event(self, event):
        # Forward events to outcome editors first
        for oe in getattr(self, 'outcome_editors', []):
            if oe.handle_event(event):
                # Prune dead element IDs and re-register new elements
                live_ids = {id(el) for el in self.ui_elements}
                self._original_positions = {k: v for k, v in self._original_positions.items() if k in live_ids}
                self._apply_scroll()
                # Recalculate max_scroll after rebuild
                max_h = 0
                for oe2 in self.outcome_editors:
                    h = oe2.y + oe2.get_total_height()
                    if h > max_h:
                        max_h = h
                if max_h > 0:
                    self.max_scroll = max(0, max_h + 60 - WINDOW_HEIGHT)
                return

        if event.type == pygame_gui.UI_BUTTON_PRESSED:
            if event.ui_element == self.back_button:
                self.back_to_list()
            elif self.submit_button and event.ui_element == self.submit_button and self.selected_card:
                self.submit_changes()
            elif self.delete_button and event.ui_element == self.delete_button and self.selected_card:
                self.delete_card()
            else:
                for button, card_id in self.card_buttons:
                    if event.ui_element == button:
                        self.load_card_for_edit(card_id)
                        break
                for entry, browse, field in self.file_inputs:
                    if event.ui_element == browse:
                        root = tk.Tk()
                        root.withdraw()
                        file_path = filedialog.askopenfilename(
                            filetypes=[("Image files", "*.png *.jpg *.jpeg *.bmp *.gif")]
                        )
                        root.destroy()
                        if file_path and file_path.lower().endswith(SUPPORTED_IMAGE_FORMATS):
                            entry.set_text(file_path)
                            try:
                                pygame.image.load(file_path)
                            except pygame.error:
                                print(f"Error: Cannot load image file: {file_path}")
                                entry.set_text("")
        elif event.type == pygame.MOUSEWHEEL and self.selected_card:
            self.scroll_offset -= event.y * 20
            self.scroll_offset = max(0, min(self.scroll_offset, self.max_scroll))
            self._apply_scroll()

    def draw(self):
        screen.fill(DARK_CHARCOAL)

class CardViewer:
    def __init__(self, card_type, back_action):
        self.card_type = card_type
        self.back_action = back_action
        self.scroll_offset = 0
        self.max_scroll = 0
        self._original_positions = {}
        self._fixed_elements = set()
        self.selected_card = None
        self.preview = None
        self.ui_elements = []
        self.card_buttons = []
        self.load_cards()

    def _apply_scroll(self):
        for element in self.ui_elements:
            eid = id(element)
            if eid in self._fixed_elements:
                continue
            if eid not in self._original_positions:
                self._original_positions[eid] = (element.relative_rect.x, element.relative_rect.y)
            ox, oy = self._original_positions[eid]
            element.set_position((ox, oy - self.scroll_offset))

    def load_cards(self):
        manager.clear_and_reset()
        self.ui_elements = []
        self.card_buttons = []
        self.preview = None
        self.scroll_offset = 0
        self._original_positions = {}
        self._fixed_elements = set()

        self.title = UILabel(
            relative_rect=pygame.Rect(0, 20, WINDOW_WIDTH, 40),
            text=f"{self.card_type}s",
            manager=manager,
            object_id="#title_label",
            anchors={'centerx': 'centerx'}
        )
        self.ui_elements.append(self.title)

        self.back_button = UIButton(
            relative_rect=pygame.Rect(20, 20, 100, 40),
            text="Back",
            manager=manager,
            object_id="#back_button"
        )
        self.ui_elements.append(self.back_button)
        self._fixed_elements.add(id(self.title))
        self._fixed_elements.add(id(self.back_button))

        with open(INDEX_FILE, 'r') as f:
            index = json.load(f)

        self.cards = []
        for card_id, info in index.items():
            if info['type'] == self.card_type:
                self.cards.append((card_id, info))
        self.cards.sort(key=lambda x: x[1]['name'].lower())

        y_start = 80
        for i, (card_id, info) in enumerate(self.cards):
            y_pos = y_start + i * 60
            button = UIButton(
                relative_rect=pygame.Rect((WINDOW_WIDTH - 200) // 2, y_pos, 200, 40),
                text=info['name'],
                manager=manager,
                object_id=f"#card_{card_id}"
            )
            self.card_buttons.append((button, card_id))
            self.ui_elements.append(button)

        total_list_height = len(self.cards) * 60 + 100
        self.max_scroll = max(0, total_list_height - WINDOW_HEIGHT)

    def show_card_details(self, card_id):
        self.selected_card = card_id
        card_file = os.path.join("cards", f"{card_id}.json")
        with open(card_file, 'r') as f:
            card_data = json.load(f)

        self.preview = CardPreview(
            card_data,
            card_id,
            self.back_to_list
        )

    def back_to_list(self):
        if self.selected_card:
            self.selected_card = None
            self.preview = None
            self.load_cards()
        else:
            self.back_action()

    def handle_event(self, event):
        if self.preview:
            self.preview.handle_event(event)
        elif event.type == pygame_gui.UI_BUTTON_PRESSED:
            if event.ui_element == self.back_button:
                self.back_to_list()
            else:
                for button, card_id in self.card_buttons:
                    if event.ui_element == button:
                        self.show_card_details(card_id)
                        break
        elif event.type == pygame.MOUSEWHEEL and not self.selected_card:
            self.scroll_offset -= event.y * 20
            self.scroll_offset = max(0, min(self.scroll_offset, self.max_scroll))
            self._apply_scroll()

    def draw(self):
        screen.fill(DARK_CHARCOAL)
        if self.preview:
            self.preview.draw()

class CardCreationScreen:
    def __init__(self, card_type, back_action):
        self.card_type = card_type
        self.back_action = back_action
        if card_type == "Document Card":
            self.current_screen = "subclass_selection"
        else:
            self.current_screen = "state_selection"
        self.selected_subclass = None
        self.selected_blueprint_subclass = None
        self.selected_skill_subclass = None
        self.state = None
        self.scroll_offset = 0
        self.max_scroll = 0
        self._original_positions = {}
        self._fixed_elements = set()
        self.ui_elements = []
        self.input_boxes = []
        self.file_inputs = []
        self.dropdown_inputs = []
        self.outcome_editors = []
        self.initialize_screen()

    def _apply_scroll(self):
        for element in self.ui_elements:
            eid = id(element)
            if eid in self._fixed_elements:
                continue
            if eid not in self._original_positions:
                self._original_positions[eid] = (element.relative_rect.x, element.relative_rect.y)
            ox, oy = self._original_positions[eid]
            element.set_position((ox, oy - self.scroll_offset))

    def initialize_screen(self):
        for oe in getattr(self, 'outcome_editors', []):
            oe.destroy()
        self.outcome_editors = []
        manager.clear_and_reset()
        self.ui_elements = []
        self.input_boxes = []
        self.file_inputs = []
        self.dropdown_inputs = []
        self.scroll_offset = 0
        self._original_positions = {}
        self._fixed_elements = set()

        if self.card_type == "Document Card":
            if self.current_screen == "subclass_selection":
                self.initialize_document_subclass_selection()
            elif self.current_screen == "blueprint_subclass_selection":
                self.initialize_blueprint_subclass_selection()
            elif self.current_screen == "skill_subclass_selection":
                self.initialize_skill_subclass_selection()
            elif self.current_screen == "input_form":
                self.initialize_input_form()
        elif self.card_type == "Junk Card":
            if self.current_screen == "state_selection":
                self.initialize_state_selection()
            elif self.current_screen == "subclass_selection":
                self.initialize_junk_subclass_selection()
            elif self.current_screen == "input_form":
                self.initialize_input_form()
        elif self.card_type == "Quest Card":
            # Quest cards are always 2-state, skip state selection
            if self.current_screen == "state_selection":
                self.state = 2
                self.current_screen = "input_form"
            if self.current_screen == "input_form":
                self.initialize_input_form()
        else:
            if self.current_screen == "state_selection":
                self.initialize_state_selection()
            elif self.current_screen == "input_form":
                self.initialize_input_form()

    def initialize_document_subclass_selection(self):
        self.title = UILabel(
            relative_rect=pygame.Rect(0, 20, WINDOW_WIDTH, 40),
            text="What is the subclass of Document?",
            manager=manager,
            object_id="#title_label",
            anchors={'centerx': 'centerx'}
        )
        self.ui_elements.append(self.title)

        subclasses = ["Blueprint", "Skill_Tome", "Location_Plan", "Guide", "Searchable", "Journal", "Map", "Note", "Book", "Pamphlet"]
        for i, subclass in enumerate(subclasses):
            y_pos = 100 + i * 60
            button = UIButton(
                relative_rect=pygame.Rect((WINDOW_WIDTH - 200) // 2, y_pos, 200, 40),
                text=subclass,
                manager=manager,
                object_id=f"#subclass_{subclass}"
            )
            self.ui_elements.append(button)

        self.back_button = UIButton(
            relative_rect=pygame.Rect(20, 20, 100, 40),
            text="Back",
            manager=manager,
            object_id="#back_button"
        )
        self.ui_elements.append(self.back_button)
        self._fixed_elements.add(id(self.title))
        self._fixed_elements.add(id(self.back_button))

    def initialize_blueprint_subclass_selection(self):
        self.title = UILabel(
            relative_rect=pygame.Rect(0, 20, WINDOW_WIDTH, 40),
            text="Sub-classification of Blueprint?",
            manager=manager,
            object_id="#title_label",
            anchors={'centerx': 'centerx'}
        )
        self.ui_elements.append(self.title)

        blueprint_subclasses = ["Blueprint_to_Weapon", "Blueprint_to_Tool", "Blueprint_to_Consumable_Item"]
        for i, subclass in enumerate(blueprint_subclasses):
            y_pos = 100 + i * 60
            button = UIButton(
                relative_rect=pygame.Rect((WINDOW_WIDTH - 200) // 2, y_pos, 200, 40),
                text=subclass.replace("_", " "),
                manager=manager,
                object_id=f"#blueprint_subclass_{subclass}"
            )
            self.ui_elements.append(button)

        self.back_button = UIButton(
            relative_rect=pygame.Rect(20, 20, 100, 40),
            text="Back",
            manager=manager,
            object_id="#back_button"
        )
        self.ui_elements.append(self.back_button)
        self._fixed_elements.add(id(self.title))
        self._fixed_elements.add(id(self.back_button))

    def initialize_skill_subclass_selection(self):
        self.title = UILabel(
            relative_rect=pygame.Rect(0, 20, WINDOW_WIDTH, 40),
            text="What type of Skill?",
            manager=manager,
            object_id="#title_label",
            anchors={'centerx': 'centerx'}
        )
        self.ui_elements.append(self.title)

        skill_subclasses = ["Skill_Attack", "Skill_Buff_Heal", "Skill_Passive"]
        for i, subclass in enumerate(skill_subclasses):
            y_pos = 100 + i * 60
            button = UIButton(
                relative_rect=pygame.Rect((WINDOW_WIDTH - 200) // 2, y_pos, 200, 40),
                text=subclass.replace("_", " "),
                manager=manager,
                object_id=f"#skill_subclass_{subclass}"
            )
            self.ui_elements.append(button)

        self.back_button = UIButton(
            relative_rect=pygame.Rect(20, 20, 100, 40),
            text="Back",
            manager=manager,
            object_id="#back_button"
        )
        self.ui_elements.append(self.back_button)
        self._fixed_elements.add(id(self.title))
        self._fixed_elements.add(id(self.back_button))

    def initialize_junk_subclass_selection(self):
        self.title = UILabel(
            relative_rect=pygame.Rect(0, 20, WINDOW_WIDTH, 40),
            text="What is the subclass of Junk?",
            manager=manager,
            object_id="#title_label",
            anchors={'centerx': 'centerx'}
        )
        self.ui_elements.append(self.title)

        subclasses = ["Junk_to_Weapon", "Junk_to_Tool", "Junk_to_Consumable_Item"]
        for i, subclass in enumerate(subclasses):
            y_pos = 100 + i * 60
            button = UIButton(
                relative_rect=pygame.Rect((WINDOW_WIDTH - 200) // 2, y_pos, 200, 40),
                text=subclass.replace("_", " "),
                manager=manager,
                object_id=f"#junk_subclass_{subclass}"
            )
            self.ui_elements.append(button)

        self.back_button = UIButton(
            relative_rect=pygame.Rect(20, 20, 100, 40),
            text="Back",
            manager=manager,
            object_id="#back_button"
        )
        self.ui_elements.append(self.back_button)
        self._fixed_elements.add(id(self.title))
        self._fixed_elements.add(id(self.back_button))

    def initialize_state_selection(self):
        self.title = UILabel(
            relative_rect=pygame.Rect(0, 20, WINDOW_WIDTH, 40),
            text=f"How many states will the {self.card_type} have?",
            manager=manager,
            object_id="#title_label",
            anchors={'centerx': 'centerx'}
        )
        self.ui_elements.append(self.title)
        
        self.back_button = UIButton(
            relative_rect=pygame.Rect(20, 20, 100, 40),
            text="Back",
            manager=manager,
            object_id="#back_button"
        )
        self.ui_elements.append(self.back_button)
        self._fixed_elements.add(id(self.title))
        self._fixed_elements.add(id(self.back_button))

        self.state_1_button = UIButton(
            relative_rect=pygame.Rect((WINDOW_WIDTH - 220) // 2 - 110, 200, 100, 40),
            text="1",
            manager=manager,
            object_id="#state_1"
        )
        self.state_2_button = UIButton(
            relative_rect=pygame.Rect((WINDOW_WIDTH + 220) // 2 - 110, 200, 100, 40),
            text="2",
            manager=manager,
            object_id="#state_2"
        )
        self.ui_elements.append(self.state_1_button)
        self.ui_elements.append(self.state_2_button)

    def initialize_input_form(self):
        manager.clear_and_reset()
        self.ui_elements = []
        self.input_boxes = []
        self.file_inputs = []
        self.dropdown_inputs = []

        title_text = f"Create {self.card_type}"
        if self.card_type == "Document Card":
            title_text += f" - {self.selected_subclass}"
            if self.selected_subclass == "Blueprint":
                title_text += f" {self.selected_blueprint_subclass.replace('_', ' ')}"
        elif self.card_type == "Junk Card" and self.state == 2:
            title_text += f" - {self.selected_subclass.replace('_', ' ')}"

        self.title = UILabel(
            relative_rect=pygame.Rect(0, 20, WINDOW_WIDTH, 40),
            text=title_text,
            manager=manager,
            object_id="#title_label",
            anchors={'centerx': 'centerx'}
        )
        self.ui_elements.append(self.title)

        self.back_button = UIButton(
            relative_rect=pygame.Rect(20, 20, 100, 40),
            text="Back",
            manager=manager,
            object_id="#back_button"
        )
        self.ui_elements.append(self.back_button)

        self.submit_button = UIButton(
            relative_rect=pygame.Rect((WINDOW_WIDTH - 200) // 2, WINDOW_HEIGHT - 60, 200, 40),
            text="Submit",
            manager=manager,
            object_id="#submit_button"
        )
        self.ui_elements.append(self.submit_button)
        self._fixed_elements.add(id(self.title))
        self._fixed_elements.add(id(self.back_button))
        self._fixed_elements.add(id(self.submit_button))

        y_start = 80

        def create_field_ui(column_x, y_pos, field_info, column_width=300):
            if len(field_info) == 2:
                field, field_type = field_info
                default = ""
            elif len(field_info) == 3:
                field, field_type, default = field_info
            elif len(field_info) == 4:
                field, field_type, options, default = field_info
            else:
                return

            label = UILabel(
                relative_rect=pygame.Rect(column_x, y_pos - 30, column_width, 30),
                text=field,
                manager=manager,
                object_id=f"#label_{field.replace(' ', '_')}"
            )
            self.ui_elements.append(label)

            if field_type == "text":
                entry = UITextEntryLine(
                    relative_rect=pygame.Rect(column_x, y_pos, column_width, 40),
                    manager=manager,
                    initial_text=default,
                    object_id=f"#entry_{field.replace(' ', '_')}"
                )
                self.input_boxes.append((entry, field))
                self.ui_elements.append(entry)
            elif field_type == "file":
                entry = UITextEntryLine(
                    relative_rect=pygame.Rect(column_x, y_pos, column_width - 80, 40),
                    manager=manager,
                    initial_text=default,
                    object_id=f"#entry_{field.replace(' ', '_')}"
                )
                browse = UIButton(
                    relative_rect=pygame.Rect(column_x + column_width - 80, y_pos, 80, 40),
                    text="Browse",
                    manager=manager,
                    object_id=f"#browse_{field.replace(' ', '_')}"
                )
                self.file_inputs.append((entry, browse, field))
                self.ui_elements.append(entry)
                self.ui_elements.append(browse)
            elif field_type == "dropdown":
                dropdown = UIDropDownMenu(
                    options_list=options,
                    starting_option=default,
                    relative_rect=pygame.Rect(column_x, y_pos, column_width, 40),
                    manager=manager,
                    object_id=f"#dropdown_{field.replace(' ', '_')}"
                )
                self.dropdown_inputs.append((dropdown, field))
                self.ui_elements.append(dropdown)
            elif field_type == "card_selection":
                entry = UITextEntryLine(
                    relative_rect=pygame.Rect(column_x, y_pos, column_width - 80, 40),
                    manager=manager,
                    initial_text=default,
                    object_id=f"#entry_{field.replace(' ', '_')}",
                    placeholder_text="Select cards (TBD)"
                )
                browse = UIButton(
                    relative_rect=pygame.Rect(column_x + column_width - 80, y_pos, 80, 40),
                    text="Browse",
                    manager=manager,
                    object_id=f"#browse_{field.replace(' ', '_')}"
                )
                self.input_boxes.append((entry, field))
                self.ui_elements.append(entry)
                self.ui_elements.append(browse)

        if self.state == 2:
            if self.card_type == "Junk Card":
                left_fields = [
                    ("Name", "text"),
                    ("Description", "text"),
                    ("Raw Material Value", "text"),
                    ("Refined Material Value", "text"),
                    ("Metal Value", "text"),
                    ("Wood Value", "text"),
                    ("Background Image", "file"),
                    ("Junk Image", "file"),
                ]
                middle_fields = [
                    ("Requirements: Raw Materials", "text"),
                    ("Requirements: Refined Materials", "text"),
                    ("Requirements: Wood", "text"),
                    ("Requirements: Metal", "text"),
                    ("Requirements: Specific Cards", "card_selection"),
                ]
                if self.selected_subclass == "Junk_to_Weapon":
                    right_fields = [
                        ("2nd_state_Name", "text"),
                        ("2nd_state_Type", "dropdown", ["Melee", "Projectile"], "Melee"),
                        ("2nd_state_Melee Damage", "text"),
                        ("2nd_state_Projectile Damage", "text"),
                        # Range properties for projectile weapons
                        ("2nd_state_Range_Type", "dropdown", RANGE_TYPES, "line_of_sight"),
                        ("2nd_state_Range_Distance", "text"),
                        ("2nd_state_Include_Position", "dropdown", BOOL_OPTIONS, "false"),
                        ("2nd_state_Exclude_Adjacent", "dropdown", BOOL_OPTIONS, "false"),
                        ("2nd_state_Requires_Ammo", "dropdown", BOOL_OPTIONS, "false"),
                        ("2nd_state_Compatible_Ammo", "text"),  # e.g., "Arrow,Bolt"
                        ("2nd_state_range_id", "dropdown", RANGE_OPTIONS, "None"),  # Legacy range_id
                        ("2nd_state_Weapon Image", "file"),
                    ]
                elif self.selected_subclass == "Junk_to_Tool":
                    right_fields = [
                        ("2nd_state_Name", "text"),
                        ("2nd_state_Type", "dropdown", ["Tool", "Tool_Belt", "Accessory", "Shield", "Armor"], "Tool"),
                        ("2nd_state_Use", "text"),
                        ("2nd_state_Subtype", "text"),  # e.g., "Building", "Repair"
                        ("2nd_state_Tool_Action", "text"),  # e.g., "Build", "Dig", "Prune"
                        # Range properties for tools with effects (healing at range, etc.)
                        ("2nd_state_Effect_Range_Type", "dropdown", RANGE_TYPES, "line_of_sight"),
                        ("2nd_state_Effect_Range_Distance", "text"),
                        ("2nd_state_Effect_Include_Position", "dropdown", BOOL_OPTIONS, "true"),
                        ("2nd_state_Effect_Exclude_Adjacent", "dropdown", BOOL_OPTIONS, "false"),
                        # Tool belt/accessory fields
                        ("2nd_state_Extra_Tool_Slots", "dropdown", TOOL_SLOT_OPTIONS, "0"),
                        ("2nd_state_Defense_Value", "text"),
                        ("2nd_state_Armor_Value", "text"),
                        ("2nd_state_Tool Image", "file"),
                    ]
                elif self.selected_subclass == "Junk_to_Consumable_Item":
                    right_fields = [
                        ("2nd_state_Name", "text"),
                        ("2nd_state_Type", "dropdown", ["Consumable", "Ammunition"], "Consumable"),
                        ("2nd_state_Use_HP", "dropdown", HP_OPTIONS, "+15HP"),
                        ("2nd_state_Revert_Chance", "text"),
                        ("2nd_state_Use_Placeholder", "dropdown", PLACEHOLDER_OPTIONS, "TBD"),
                        ("2nd_state_Revival", "text"),
                        # Range properties for ranged consumables (healing potions thrown at allies, etc.)
                        ("2nd_state_Effect_Range_Type", "dropdown", RANGE_TYPES, "line_of_sight"),
                        ("2nd_state_Effect_Range_Distance", "text"),
                        ("2nd_state_Effect_Include_Position", "dropdown", BOOL_OPTIONS, "true"),
                        ("2nd_state_Effect_Exclude_Adjacent", "dropdown", BOOL_OPTIONS, "false"),
                        # Ammunition-specific fields (used when Type is Ammunition)
                        ("2nd_state_Ammo_Type", "dropdown", AMMO_TYPES, "None"),
                        ("2nd_state_Ammo_Damage", "text"),
                        ("2nd_state_Runout_Chance", "dropdown", RUNOUT_CHANCE_OPTIONS, "15"),
                        ("2nd_state_Compatible_Weapons", "text"),  # e.g., "Hunting Bow,Longbow"
                        ("2nd_state_Item Image", "file"),
                    ]
                else:
                    right_fields = []

                column_width = 300
                spacing = 50
                total_width = 3 * column_width + 2 * spacing
                left_margin = (WINDOW_WIDTH - total_width) // 2
                column1_x = left_margin
                column2_x = column1_x + column_width + spacing
                column3_x = column2_x + column_width + spacing

                for i, field_info in enumerate(left_fields):
                    y_pos = y_start + i * 80
                    create_field_ui(column1_x, y_pos, field_info, column_width)

                for i, field_info in enumerate(middle_fields):
                    y_pos = y_start + i * 80
                    create_field_ui(column2_x, y_pos, field_info, column_width)

                for i, field_info in enumerate(right_fields):
                    y_pos = y_start + i * 80
                    create_field_ui(column3_x, y_pos, field_info, column_width)

                max_fields = max(len(left_fields), len(middle_fields), len(right_fields))
                total_form_height = max_fields * 80 + 140
                self.max_scroll = max(0, total_form_height - WINDOW_HEIGHT)
            elif self.card_type == "Document Card" and self.selected_subclass == "Blueprint":
                if self.selected_blueprint_subclass == "Blueprint_to_Weapon":
                    fields_state_1 = [
                        ("Name", "text"),
                        ("Requirements: Raw Materials", "text"),
                        ("Requirements: Refined Materials", "text"),
                        ("Requirements: Wood", "text"),
                        ("Requirements: Metal", "text"),
                        ("Requirements: Specific Cards", "card_selection"),
                        ("Background Image", "file"),
                    ]
                    fields_state_2 = [
                        ("2nd_state_Name", "text"),
                        ("2nd_state_Type", "dropdown", ["Melee", "Projectile"], "Melee"),
                        ("2nd_state_Melee Damage", "text"),
                        ("2nd_state_Projectile Damage", "text"),
                        # Range properties for projectile weapons
                        ("2nd_state_Range_Type", "dropdown", RANGE_TYPES, "line_of_sight"),
                        ("2nd_state_Range_Distance", "text"),
                        ("2nd_state_Include_Position", "dropdown", BOOL_OPTIONS, "false"),
                        ("2nd_state_Exclude_Adjacent", "dropdown", BOOL_OPTIONS, "false"),
                        ("2nd_state_Requires_Ammo", "dropdown", BOOL_OPTIONS, "false"),
                        ("2nd_state_Compatible_Ammo", "text"),  # e.g., "Arrow,Bolt"
                        ("2nd_state_range_id", "dropdown", RANGE_OPTIONS, "None"),  # Legacy range_id
                        ("2nd_state_Weapon Image", "file"),
                    ]
                elif self.selected_blueprint_subclass == "Blueprint_to_Tool":
                    fields_state_1 = [
                        ("Name", "text"),
                        ("Requirements: Raw Materials", "text"),
                        ("Requirements: Refined Materials", "text"),
                        ("Requirements: Wood", "text"),
                        ("Requirements: Metal", "text"),
                        ("Requirements: Specific Cards", "card_selection"),
                        ("Background Image", "file"),
                    ]
                    fields_state_2 = [
                        ("2nd_state_Name", "text"),
                        ("2nd_state_Type", "dropdown", ["Tool", "Tool_Belt", "Accessory", "Shield", "Armor"], "Tool"),
                        ("2nd_state_Use", "text"),
                        ("2nd_state_Subtype", "text"),  # e.g., "Building", "Repair"
                        ("2nd_state_Tool_Action", "text"),  # e.g., "Build", "Dig", "Prune"
                        # Tool belt/accessory fields
                        ("2nd_state_Extra_Tool_Slots", "dropdown", TOOL_SLOT_OPTIONS, "0"),
                        ("2nd_state_Defense_Value", "text"),
                        ("2nd_state_Armor_Value", "text"),
                        ("2nd_state_Tool Image", "file"),
                    ]
                elif self.selected_blueprint_subclass == "Blueprint_to_Consumable_Item":
                    fields_state_1 = [
                        ("Name", "text"),
                        ("Requirements: Raw Materials", "text"),
                        ("Requirements: Refined Materials", "text"),
                        ("Requirements: Wood", "text"),
                        ("Requirements: Metal", "text"),
                        ("Requirements: Specific Cards", "card_selection"),
                        ("Background Image", "file"),
                    ]
                    fields_state_2 = [
                        ("2nd_state_Name", "text"),
                        ("2nd_state_Type", "dropdown", ["Consumable", "Ammunition"], "Consumable"),
                        ("2nd_state_Use_HP", "dropdown", HP_OPTIONS, "+15HP"),
                        ("2nd_state_Revert_Chance", "text"),
                        ("2nd_state_Use_Placeholder", "dropdown", PLACEHOLDER_OPTIONS, "TBD"),
                        ("2nd_state_Revival", "text"),
                        # Ammunition-specific fields (used when Type is Ammunition)
                        ("2nd_state_Ammo_Type", "dropdown", AMMO_TYPES, "None"),
                        ("2nd_state_Ammo_Damage", "text"),
                        ("2nd_state_Runout_Chance", "dropdown", RUNOUT_CHANCE_OPTIONS, "15"),
                        ("2nd_state_Compatible_Weapons", "text"),  # e.g., "Hunting Bow,Longbow"
                        ("2nd_state_Item Image", "file"),
                    ]
                column_width = 300
                left_column_x = (WINDOW_WIDTH - 2 * column_width - 100) // 2
                right_column_x = left_column_x + column_width + 100

                for i, field_info in enumerate(fields_state_1):
                    y_pos = y_start + i * 80
                    create_field_ui(left_column_x, y_pos, field_info, column_width)

                for i, field_info in enumerate(fields_state_2):
                    y_pos = y_start + i * 80
                    create_field_ui(right_column_x, y_pos, field_info, column_width)

                total_form_height = max(len(fields_state_1), len(fields_state_2)) * 80 + 140
                self.max_scroll = max(0, total_form_height - WINDOW_HEIGHT)
            elif self.card_type == "Document Card" and self.selected_subclass == "Skill_Tome":
                # Base fields for all skill tomes (State 1 - Document side)
                fields_state_1 = [
                    ("Name", "text"),
                    ("Description", "text"),
                    ("Acquisition_Condition", "text"),
                    ("Background Image", "file"),
                ]
                # State 2 fields depend on skill type
                if self.selected_skill_subclass == "Skill_Attack":
                    fields_state_2 = [
                        ("2nd_state_Name", "text"),
                        ("2nd_state_Skill_Type", "text", "Attack"),
                        ("2nd_state_Damage", "text"),
                        ("2nd_state_Attack_Range", "text"),
                        ("2nd_state_Attack_Type", "dropdown", SKILL_ATTACK_TYPES, "Melee"),
                        ("2nd_state_Cooldown", "text"),
                        ("2nd_state_range_id", "dropdown", RANGE_OPTIONS, "None"),
                        ("2nd_state_Skill Image", "file"),
                    ]
                elif self.selected_skill_subclass == "Skill_Buff_Heal":
                    fields_state_2 = [
                        ("2nd_state_Name", "text"),
                        ("2nd_state_Skill_Type", "text", "Buff_Heal"),
                        ("2nd_state_Effect_Type", "dropdown", SKILL_EFFECT_TYPES, "Heal"),
                        ("2nd_state_Effect_Value", "text"),
                        ("2nd_state_Duration", "text"),
                        ("2nd_state_Target", "dropdown", SKILL_TARGETS, "Self"),
                        ("2nd_state_Cooldown", "text"),
                        ("2nd_state_Skill Image", "file"),
                    ]
                elif self.selected_skill_subclass == "Skill_Passive":
                    fields_state_2 = [
                        ("2nd_state_Name", "text"),
                        ("2nd_state_Skill_Type", "text", "Passive"),
                        ("2nd_state_Effect_Type", "dropdown", SKILL_EFFECT_TYPES, "Heal_Adjacent"),
                        ("2nd_state_Effect_Value", "text"),
                        ("2nd_state_Range", "text"),
                        ("2nd_state_Trigger", "dropdown", SKILL_TRIGGERS, "Turn_End"),
                        ("2nd_state_Skill Image", "file"),
                    ]
                else:
                    fields_state_2 = []

                column_width = 300
                left_column_x = (WINDOW_WIDTH - 2 * column_width - 100) // 2
                right_column_x = left_column_x + column_width + 100

                for i, field_info in enumerate(fields_state_1):
                    y_pos = y_start + i * 80
                    create_field_ui(left_column_x, y_pos, field_info, column_width)

                for i, field_info in enumerate(fields_state_2):
                    y_pos = y_start + i * 80
                    create_field_ui(right_column_x, y_pos, field_info, column_width)

                total_form_height = max(len(fields_state_1), len(fields_state_2)) * 80 + 140
                self.max_scroll = max(0, total_form_height - WINDOW_HEIGHT)
            elif self.card_type == "Document Card" and self.selected_subclass == "Location_Plan":
                # Document/Location compound type: State 1 is Document (plan), State 2 is Location
                SPAWN_LOCATION_OPTIONS_LP = ["false", "true"]
                RANGE_TYPE_OPTIONS_LP = ["area_effect", "line_of_sight", "melee", "perimeter", "echo", "multi_echo", "mist_shadow"]
                fields_state_1 = [
                    ("Name", "text"),
                    ("Description", "text"),
                    ("Requirements_NPC_Type", "dropdown", ALLEGIANCE_TYPES, "Allied"),
                    ("Requirements_Gems", "text"),
                    ("Requirements_Materials", "text"),  # JSON: {"Metal":10,"Wood":5}
                    ("Background Image", "file"),
                ]
                # State 2 is the actual location
                fields_state_2 = [
                    ("2nd_state_Name", "text"),
                    ("2nd_state_Description", "text"),
                    ("2nd_state_Outcomes", "text"),
                    ("2nd_state_Choices", "text"),
                    ("2nd_state_Shop_Deck", "text"),
                    ("2nd_state_Shop_Size", "text"),
                    ("2nd_state_Shop_Currency", "dropdown", CURRENCY_TYPES, "metal"),
                    ("2nd_state_Shop_Cycle_Turns", "text"),
                    # Defense Attack 1 fields (state 2)
                    ("2nd_state_Defense_Enabled", "dropdown", SPAWN_LOCATION_OPTIONS_LP, "false"),
                    ("2nd_state_Defense_Requires_NPC", "dropdown", SPAWN_LOCATION_OPTIONS_LP, "false"),
                    ("2nd_state_Defense_Damage", "text"),
                    ("2nd_state_Defense_Range_Type", "dropdown", RANGE_TYPE_OPTIONS_LP, "area_effect"),
                    ("2nd_state_Defense_Range_Distance", "text"),
                    ("2nd_state_Defense_Include_Position", "dropdown", SPAWN_LOCATION_OPTIONS_LP, "false"),
                    ("2nd_state_Defense_Exclude_Adjacent", "dropdown", SPAWN_LOCATION_OPTIONS_LP, "false"),
                    ("2nd_state_Defense_Passthrough_Chance", "text"),
                    ("2nd_state_Defense_Color_R", "text"),
                    ("2nd_state_Defense_Color_G", "text"),
                    ("2nd_state_Defense_Color_B", "text"),
                    # Defense Attack 2 fields (state 2, secondary)
                    ("2nd_state_Defense2_Enabled", "dropdown", SPAWN_LOCATION_OPTIONS_LP, "false"),
                    ("2nd_state_Defense2_Requires_NPC", "dropdown", SPAWN_LOCATION_OPTIONS_LP, "false"),
                    ("2nd_state_Defense2_Damage", "text"),
                    ("2nd_state_Defense2_Range_Type", "dropdown", RANGE_TYPE_OPTIONS_LP, "area_effect"),
                    ("2nd_state_Defense2_Range_Distance", "text"),
                    ("2nd_state_Defense2_Include_Position", "dropdown", SPAWN_LOCATION_OPTIONS_LP, "false"),
                    ("2nd_state_Defense2_Exclude_Adjacent", "dropdown", SPAWN_LOCATION_OPTIONS_LP, "false"),
                    ("2nd_state_Defense2_Passthrough_Chance", "text"),
                    ("2nd_state_Defense2_Color_R", "text"),
                    ("2nd_state_Defense2_Color_G", "text"),
                    ("2nd_state_Defense2_Color_B", "text"),
                    ("2nd_state_Location Image File Path", "file"),
                ]

                column_width = 300
                left_column_x = (WINDOW_WIDTH - 2 * column_width - 100) // 2
                right_column_x = left_column_x + column_width + 100

                for i, field_info in enumerate(fields_state_1):
                    y_pos = y_start + i * 80
                    create_field_ui(left_column_x, y_pos, field_info, column_width)

                for i, field_info in enumerate(fields_state_2):
                    y_pos = y_start + i * 80
                    create_field_ui(right_column_x, y_pos, field_info, column_width)

                total_form_height = max(len(fields_state_1), len(fields_state_2)) * 80 + 140
                self.max_scroll = max(0, total_form_height - WINDOW_HEIGHT)
            elif self.card_type == "Document Card" and self.selected_subclass == "Searchable":
                # Searchable documents: State 1 describes where to search, State 2 is the found item
                fields_state_1 = [
                    ("Name", "text"),
                    ("Description", "text"),
                    ("Search_Terrain", "text"),  # Comma-separated: "forest,swamp" or empty for location-based
                    ("Search_Location", "text"),  # Location name to search at (optional)
                    ("Search_Success_Chance", "text"),  # Percentage 0-100
                    ("Required_Tool_Action", "text"),  # e.g., "Dig", "Prune" - if set, requires tool action instead of Search button
                    ("Track_Hex_Attempts", "dropdown", BOOL_OPTIONS, "false"),  # Track which hexes have been attempted
                    ("Background Image", "file"),
                ]
                # State 2 is the found item (consumable, weapon, or material)
                fields_state_2 = [
                    ("2nd_state_Name", "text"),
                    ("2nd_state_Type", "dropdown", ["Consumable", "Melee", "Projectile", "Material"], "Consumable"),
                    ("2nd_state_Use_HP", "dropdown", HP_OPTIONS, "+15HP"),
                    ("2nd_state_Revert_Chance", "text"),
                    ("2nd_state_Melee Damage", "text"),
                    ("2nd_state_Projectile Damage", "text"),
                    ("2nd_state_Projectile Range", "text"),
                    ("2nd_state_Raw Material Value", "text"),
                    ("2nd_state_Metal Value", "text"),
                    ("2nd_state_Wood Value", "text"),
                    ("2nd_state_Item Image", "file"),
                ]

                column_width = 300
                left_column_x = (WINDOW_WIDTH - 2 * column_width - 100) // 2
                right_column_x = left_column_x + column_width + 100

                for i, field_info in enumerate(fields_state_1):
                    y_pos = y_start + i * 80
                    create_field_ui(left_column_x, y_pos, field_info, column_width)

                for i, field_info in enumerate(fields_state_2):
                    y_pos = y_start + i * 80
                    create_field_ui(right_column_x, y_pos, field_info, column_width)

                total_form_height = max(len(fields_state_1), len(fields_state_2)) * 80 + 140
                self.max_scroll = max(0, total_form_height - WINDOW_HEIGHT)
            elif self.card_type == "Document Card" and self.selected_subclass == "Guide":
                # Guide documents: equippable in tool slot, reading draws from a deck
                fields_state_1 = [
                    ("Name", "text"),
                    ("Description", "text"),
                    ("Tool_Action", "text"),  # e.g., "Read"
                    ("Guide_Deck", "text"),
                    ("Guide_Draw_Chance", "text"),
                    ("Document Image File Path", "file"),
                    ("Background Image File Path", "file"),
                ]
                fields_state_2 = [
                    ("2nd_state_Name", "text"),
                    ("2nd_state_Description", "text"),
                    ("2nd_state_Tool_Action", "text"),
                    ("2nd_state_Guide_Deck", "text"),
                    ("2nd_state_Guide_Draw_Chance", "text"),
                    ("2nd_state_Document Image File Path", "file"),
                    ("2nd_state_Background Image File Path", "file"),
                ]

                column_width = 300
                left_column_x = (WINDOW_WIDTH - 2 * column_width - 100) // 2
                right_column_x = left_column_x + column_width + 100

                for i, field_info in enumerate(fields_state_1):
                    y_pos = y_start + i * 80
                    create_field_ui(left_column_x, y_pos, field_info, column_width)

                for i, field_info in enumerate(fields_state_2):
                    y_pos = y_start + i * 80
                    create_field_ui(right_column_x, y_pos, field_info, column_width)

                total_form_height = max(len(fields_state_1), len(fields_state_2)) * 80 + 140
                self.max_scroll = max(0, total_form_height - WINDOW_HEIGHT)
            elif self.card_type == "Enemy Card":
                fields_state_1 = [
                    ("Name", "text"),
                    ("Health", "text"),
                    ("Movement", "text"),
                    ("Melee Damage", "text"),
                    ("Projectile Damage", "text"),
                    ("Projectile Range", "text"),
                    ("range_id", "dropdown", RANGE_OPTIONS, "None"),  # Added range_id
                    ("Special Skill", "text"),
                    ("Heal_Amount", "text"),
                    ("Heal_Range", "text"),
                    ("Default_Behavior_Tree", "text"),
                    ("Hostile_Behavior_Tree", "text"),
                    ("Neutral_Behavior_Tree", "text"),
                    ("Allied_Behavior_Tree", "text"),
                    ("Allegiance_Priority", "text"),
                    ("Stubborn", "text"),
                    ("Spawn_Deck", "text"),
                    ("Repair_Value", "text"),
                    ("Aggro_Range", "text"),
                    ("Attack_Proximity_Range", "text"),
                    ("Background Image File Path", "file"),
                    ("Enemy Image File Path", "file")
                ]
                fields_state_2 = [
                    ("2nd_State_Name", "text"),
                    ("2nd_State_Health", "text"),
                    ("2nd_State_Movement", "text"),
                    ("2nd_State_Melee Damage", "text"),
                    ("2nd_State_Projectile Damage", "text"),
                    ("2nd_State_Projectile Range", "text"),
                    ("2nd_State_range_id", "dropdown", RANGE_OPTIONS, "None"),  # Added range_id for 2nd state
                    ("2nd_State_Special Skill", "text"),
                    ("2nd_State_Heal_Amount", "text"),
                    ("2nd_State_Heal_Range", "text"),
                    ("2nd_State_Default_Behavior_Tree", "text"),
                    ("2nd_State_Hostile_Behavior_Tree", "text"),
                    ("2nd_State_Neutral_Behavior_Tree", "text"),
                    ("2nd_State_Allied_Behavior_Tree", "text"),
                    ("2nd_State_Allegiance_Priority", "text"),
                    ("2nd_State_Stubborn", "text"),
                    ("2nd_State_Spawn_Deck", "text"),
                    ("2nd_State_Repair_Value", "text"),
                    ("2nd_State_Aggro_Range", "text"),
                    ("2nd_State_Enemy Image File Path", "file")
                ]
                column_width = 300
                left_column_x = (WINDOW_WIDTH - 2 * column_width - 100) // 2
                right_column_x = left_column_x + column_width + 100

                for i, field_info in enumerate(fields_state_1):
                    y_pos = y_start + i * 80
                    create_field_ui(left_column_x, y_pos, field_info, column_width)

                for i, field_info in enumerate(fields_state_2):
                    y_pos = y_start + i * 80
                    create_field_ui(right_column_x, y_pos, field_info, column_width)

                total_form_height = max(len(fields_state_1), len(fields_state_2)) * 80 + 140
                self.max_scroll = max(0, total_form_height - WINDOW_HEIGHT)
            elif self.card_type == "Boss Card":
                fields_state_1 = [
                    ("Name", "text"),
                    ("Health", "text"),
                    ("Movement", "text"),
                    ("Melee Damage", "text"),
                    ("Projectile Damage", "text"),
                    ("Projectile Range", "text"),
                    ("range_id", "dropdown", RANGE_OPTIONS, "None"),  # Added range_id
                    ("Special Skill", "text"),
                    ("Heal_Amount", "text"),
                    ("Heal_Range", "text"),
                    ("Default_Behavior_Tree", "text"),
                    ("Hostile_Behavior_Tree", "text"),
                    ("Neutral_Behavior_Tree", "text"),
                    ("Allied_Behavior_Tree", "text"),
                    ("Allegiance_Priority", "text"),
                    ("Stubborn", "text"),
                    ("Spawn_Deck", "text"),
                    ("Repair_Value", "text"),
                    ("Aggro_Range", "text"),
                    ("Attack_Proximity_Range", "text"),
                    ("Background Image File Path", "file"),
                    ("Boss Image File Path", "file")
                ]
                fields_state_2 = [
                    ("2nd_State_Name", "text"),
                    ("2nd_State_Health", "text"),
                    ("2nd_State_Movement", "text"),
                    ("2nd_State_Melee Damage", "text"),
                    ("2nd_State_Projectile Damage", "text"),
                    ("2nd_State_Projectile Range", "text"),
                    ("2nd_State_range_id", "dropdown", RANGE_OPTIONS, "None"),  # Added range_id for 2nd state
                    ("2nd_State_Special Skill", "text"),
                    ("2nd_State_Heal_Amount", "text"),
                    ("2nd_State_Heal_Range", "text"),
                    ("2nd_State_Default_Behavior_Tree", "text"),
                    ("2nd_State_Hostile_Behavior_Tree", "text"),
                    ("2nd_State_Neutral_Behavior_Tree", "text"),
                    ("2nd_State_Allied_Behavior_Tree", "text"),
                    ("2nd_State_Allegiance_Priority", "text"),
                    ("2nd_State_Stubborn", "text"),
                    ("2nd_State_Spawn_Deck", "text"),
                    ("2nd_State_Repair_Value", "text"),
                    ("2nd_State_Aggro_Range", "text"),
                    ("2nd_State_Boss Image File Path", "file")
                ]
                column_width = 300
                left_column_x = (WINDOW_WIDTH - 2 * column_width - 100) // 2
                right_column_x = left_column_x + column_width + 100

                for i, field_info in enumerate(fields_state_1):
                    y_pos = y_start + i * 80
                    create_field_ui(left_column_x, y_pos, field_info, column_width)

                for i, field_info in enumerate(fields_state_2):
                    y_pos = y_start + i * 80
                    create_field_ui(right_column_x, y_pos, field_info, column_width)

                total_form_height = max(len(fields_state_1), len(fields_state_2)) * 80 + 140
                self.max_scroll = max(0, total_form_height - WINDOW_HEIGHT)
            elif self.card_type == "NPC Card":
                fields_state_1 = [
                    ("Name", "text"),
                    ("Health", "text"),
                    ("Movement", "text"),
                    ("Melee Damage", "text"),
                    ("Projectile Damage", "text"),
                    ("Projectile Range", "text"),
                    ("range_id", "dropdown", RANGE_OPTIONS, "None"),  # Added range_id
                    ("Allegiance (Hostile, Neutral, Allied)", "text"),
                    ("Special Skill", "text"),
                    ("Heal_Amount", "text"),
                    ("Heal_Range", "text"),
                    ("Default_Behavior_Tree", "text"),
                    ("Hostile_Behavior_Tree", "text"),
                    ("Neutral_Behavior_Tree", "text"),
                    ("Allied_Behavior_Tree", "text"),
                    ("Allegiance_Priority", "text"),
                    ("Stubborn", "text"),
                    ("Dialogue_Text", "text"),
                    ("Dialogue_Gift_Cards", "text"),
                    ("Attack_Proximity_Range", "text"),
                    ("Avoid_Location_Hexes", "text"),
                    ("Mount_Movement", "text"),
                    ("Mount_Melee_Damage", "text"),
                    ("Mount_Projectile_Range", "text"),
                    ("Background Image File Path", "file"),
                    ("NPC Image File Path", "file")
                ]
                fields_state_2 = [
                    ("2nd_State_Name", "text"),
                    ("2nd_State_Health", "text"),
                    ("2nd_State_Movement", "text"),
                    ("2nd_State_Melee Damage", "text"),
                    ("2nd_State_Projectile Damage", "text"),
                    ("2nd_State_Projectile Range", "text"),
                    ("2nd_State_range_id", "dropdown", RANGE_OPTIONS, "None"),  # Added range_id for 2nd state
                    ("2nd_State_Allegiance (Hostile, Neutral, Allied)", "text"),
                    ("2nd_State_Special Skill", "text"),
                    ("2nd_State_Heal_Amount", "text"),
                    ("2nd_State_Heal_Range", "text"),
                    ("2nd_State_Default_Behavior_Tree", "text"),
                    ("2nd_State_Hostile_Behavior_Tree", "text"),
                    ("2nd_State_Neutral_Behavior_Tree", "text"),
                    ("2nd_State_Allied_Behavior_Tree", "text"),
                    ("2nd_State_Allegiance_Priority", "text"),
                    ("2nd_State_Mount_Movement", "text"),
                    ("2nd_State_Mount_Melee_Damage", "text"),
                    ("2nd_State_Mount_Projectile_Range", "text"),
                    ("2nd_State_Stubborn", "text"),
                    ("2nd_State_NPC Image File Path", "file")
                ]
                column_width = 300
                left_column_x = (WINDOW_WIDTH - 2 * column_width - 100) // 2
                right_column_x = left_column_x + column_width + 100

                for i, field_info in enumerate(fields_state_1):
                    y_pos = y_start + i * 80
                    create_field_ui(left_column_x, y_pos, field_info, column_width)

                for i, field_info in enumerate(fields_state_2):
                    y_pos = y_start + i * 80
                    create_field_ui(right_column_x, y_pos, field_info, column_width)

                total_form_height = max(len(fields_state_1), len(fields_state_2)) * 80 + 140
                self.max_scroll = max(0, total_form_height - WINDOW_HEIGHT)
            elif self.card_type == "Transition Card":
                # Transition Cards - represent world events that happen each turn cycle
                # Standard fields (no Outcomes - those use visual editor)
                fields_state_1 = [
                    ("Name", "text"),
                    ("Description", "text"),
                    ("Background Image", "file"),
                ]
                fields_state_2 = [
                    ("2nd_state_Name", "text"),
                    ("2nd_state_Description", "text"),
                    ("2nd_state_Background Image", "file"),
                ]
                column_width = 400
                left_column_x = (WINDOW_WIDTH - 2 * column_width - 50) // 2
                right_column_x = left_column_x + column_width + 50

                for i, field_info in enumerate(fields_state_1):
                    y_pos = y_start + i * 80
                    create_field_ui(left_column_x, y_pos, field_info, column_width)

                for i, field_info in enumerate(fields_state_2):
                    y_pos = y_start + i * 80
                    create_field_ui(right_column_x, y_pos, field_info, column_width)

                # Visual outcome editors below the standard fields
                outcome_y = y_start + max(len(fields_state_1), len(fields_state_2)) * 80 + 20
                oe_left = OutcomeEditorWidget("Outcomes", "transition", left_column_x, outcome_y, column_width, self.ui_elements)
                oe_left.build_all()
                self.outcome_editors.append(oe_left)

                oe_right = OutcomeEditorWidget("2nd_state_Outcomes", "transition", right_column_x, outcome_y, column_width, self.ui_elements)
                oe_right.build_all()
                self.outcome_editors.append(oe_right)

                total_form_height = outcome_y + max(oe_left.get_total_height(), oe_right.get_total_height()) + 60
                self.max_scroll = max(0, total_form_height - WINDOW_HEIGHT)
            elif self.card_type == "Quest Card":
                # Quest cards are always 2-state (Active/Complete)
                # Left column: State 1 text fields
                left_fields = [
                    ("Name", "text"),
                    ("Description", "text"),
                    ("Template_Text", "text"),
                    ("Quest Image File Path", "file"),
                ]
                # Right column: State 2 fields (completed quest)
                right_fields = [
                    ("2nd_state_Name", "text"),
                    ("2nd_state_Template_Text", "text"),
                    ("2nd_state_Quest Image File Path", "file"),
                ]

                column_width = 300
                spacing = 30
                total_width = 3 * column_width + 2 * spacing
                left_margin = (WINDOW_WIDTH - total_width) // 2
                column1_x = left_margin
                column2_x = column1_x + column_width + spacing
                column3_x = column2_x + column_width + spacing

                for i, field_info in enumerate(left_fields):
                    y_pos = y_start + i * 80
                    create_field_ui(column1_x, y_pos, field_info, column_width)

                for i, field_info in enumerate(right_fields):
                    y_pos = y_start + i * 80
                    create_field_ui(column3_x, y_pos, field_info, column_width)

                # Visual editors below standard fields
                editor_start_y = y_start + max(len(left_fields), len(right_fields)) * 80 + 20

                # Placeholders editor (left column)
                pe = PlaceholderEditorWidget("Placeholders", column1_x, editor_start_y,
                                             column_width, self.ui_elements)
                pe.build_all()
                self.outcome_editors.append(pe)

                # Success Conditions editor (middle column)
                sc = ConditionEditorWidget("Success_Conditions", column2_x, editor_start_y,
                                            column_width, self.ui_elements)
                sc.build_all()
                self.outcome_editors.append(sc)

                # Failure Conditions editor (middle column, below success)
                fc_y = editor_start_y + sc.get_total_height() + 10
                fc = ConditionEditorWidget("Failure_Conditions", column2_x, fc_y,
                                            column_width, self.ui_elements)
                fc.build_all()
                self.outcome_editors.append(fc)

                # Rewards editor (right column)
                rw = RewardsEditorWidget("Rewards", column3_x, editor_start_y,
                                          column_width, self.ui_elements)
                rw.build_all()
                self.outcome_editors.append(rw)

                # Chain Config editor (right column, below rewards)
                cc_y = editor_start_y + rw.get_total_height() + 10
                cc = ChainConfigEditorWidget("Chain_Config", column3_x, cc_y,
                                              column_width, self.ui_elements)
                cc.build_all()
                self.outcome_editors.append(cc)

                total_form_height = max(
                    editor_start_y + pe.get_total_height(),
                    fc_y + fc.get_total_height(),
                    cc_y + cc.get_total_height()
                ) + 60
                self.max_scroll = max(0, total_form_height - WINDOW_HEIGHT)
            else:
                fields_state_1 = []
                fields_state_2 = []
                column_width = 300
                left_column_x = (WINDOW_WIDTH - 2 * column_width - 100) // 2
                right_column_x = left_column_x + column_width + 100

                for i, field_info in enumerate(fields_state_1):
                    y_pos = y_start + i * 80
                    create_field_ui(left_column_x, y_pos, field_info, column_width)

                for i, field_info in enumerate(fields_state_2):
                    y_pos = y_start + i * 80
                    create_field_ui(right_column_x, y_pos, field_info, column_width)

                total_form_height = max(len(fields_state_1), len(fields_state_2)) * 80 + 140
                self.max_scroll = max(0, total_form_height - WINDOW_HEIGHT)
        else:
            if self.card_type == "Document Card":
                if self.selected_subclass == "Journal":
                    fields = [
                        ("Name", "text"),
                        ("Description", "text"),
                        ("Background Image", "file"),
                    ]
                elif self.selected_subclass == "Map":
                    fields = [("Name", "text"), ("Description", "text"), ("Background Image", "file")]
                elif self.selected_subclass == "Note":
                    fields = [
                        ("Name", "text"),
                        ("Contents", "text"),
                        ("Background Image", "file"),
                    ]
                elif self.selected_subclass == "Book":
                    fields = [
                        ("Name", "text"),
                        ("Description", "text"),
                        ("Background Image", "file"),
                        ("Book Image", "file"),
                    ]
                elif self.selected_subclass == "Pamphlet":
                    fields = [
                        ("Name", "text"),
                        ("Lesson", "text"),
                        ("Background Image", "file"),
                        ("Pamphlet Image", "file"),
                    ]
                else:
                    fields = []
                column_width = 300
                column_x = (WINDOW_WIDTH - column_width) // 2
                for i, field_info in enumerate(fields):
                    y_pos = y_start + i * 80
                    create_field_ui(column_x, y_pos, field_info, column_width)
                total_form_height = len(fields) * 80 + 140
                self.max_scroll = max(0, total_form_height - WINDOW_HEIGHT)
            elif self.card_type == "Junk Card":
                fields = [
                    ("Name", "text"),
                    ("Description", "text"),
                    ("Raw Material Value", "text"),
                    ("Refined Material Value", "text"),
                    ("Metal Value", "text"),
                    ("Wood Value", "text"),
                    ("Background Image", "file"),
                    ("Junk Image", "file"),
                ]
                column_width = 300
                column_x = (WINDOW_WIDTH - column_width) // 2
                for i, field_info in enumerate(fields):
                    y_pos = y_start + i * 80
                    create_field_ui(column_x, y_pos, field_info, column_width)
                total_form_height = len(fields) * 80 + 140
                self.max_scroll = max(0, total_form_height - WINDOW_HEIGHT)
            elif self.card_type == "Enemy Card":
                fields = [
                    ("Name", "text"),
                    ("Health", "text"),
                    ("Movement", "text"),
                    ("Melee Damage", "text"),
                    ("Projectile Damage", "text"),
                    ("range_id", "dropdown", RANGE_OPTIONS, "None"),  # Added range_id
                    ("Projectile Range", "text"),
                    ("Special Skill", "text"),
                    ("Heal_Amount", "text"),
                    ("Heal_Range", "text"),
                    ("Default_Behavior_Tree", "text"),
                    ("Hostile_Behavior_Tree", "text"),
                    ("Neutral_Behavior_Tree", "text"),
                    ("Allied_Behavior_Tree", "text"),
                    ("Stubborn", "text"),
                    ("Background Image File Path", "file"),
                    ("Enemy Image File Path", "file")
                ]
                column_width = 300
                column_x = (WINDOW_WIDTH - column_width) // 2
                for i, field_info in enumerate(fields):
                    y_pos = y_start + i * 80
                    create_field_ui(column_x, y_pos, field_info, column_width)
                total_form_height = len(fields) * 80 + 140
                self.max_scroll = max(0, total_form_height - WINDOW_HEIGHT)
            elif self.card_type == "Boss Card":
                fields = [
                    ("Name", "text"),
                    ("Health", "text"),
                    ("Movement", "text"),
                    ("Melee Damage", "text"),
                    ("Projectile Damage", "text"),
                    ("Projectile Range", "text"),
                    ("range_id", "dropdown", RANGE_OPTIONS, "None"),  # Added range_id
                    ("Special Skill", "text"),
                    ("Heal_Amount", "text"),
                    ("Heal_Range", "text"),
                    ("Default_Behavior_Tree", "text"),
                    ("Hostile_Behavior_Tree", "text"),
                    ("Neutral_Behavior_Tree", "text"),
                    ("Allied_Behavior_Tree", "text"),
                    ("Stubborn", "text"),
                    ("Background Image File Path", "file"),
                    ("Boss Image File Path", "file")
                ]
                column_width = 300
                column_x = (WINDOW_WIDTH - column_width) // 2
                for i, field_info in enumerate(fields):
                    y_pos = y_start + i * 80
                    create_field_ui(column_x, y_pos, field_info, column_width)
                total_form_height = len(fields) * 80 + 140
                self.max_scroll = max(0, total_form_height - WINDOW_HEIGHT)
            elif self.card_type == "NPC Card":
                fields = [
                    ("Name", "text"),
                    ("Health", "text"),
                    ("Movement", "text"),
                    ("Melee Damage", "text"),
                    ("Projectile Damage", "text"),
                    ("Projectile Range", "text"),
                    ("range_id", "dropdown", RANGE_OPTIONS, "None"),  # Added range_id
                    ("Allegiance (Hostile, Neutral, Allied)", "text"),
                    ("Special Skill", "text"),
                    ("Heal_Amount", "text"),
                    ("Heal_Range", "text"),
                    ("Default_Behavior_Tree", "text"),
                    ("Hostile_Behavior_Tree", "text"),
                    ("Neutral_Behavior_Tree", "text"),
                    ("Allied_Behavior_Tree", "text"),
                    ("Stubborn", "text"),
                    ("Background Image File Path", "file"),
                    ("NPC Image File Path", "file")
                ]
                column_width = 300
                column_x = (WINDOW_WIDTH - column_width) // 2
                for i, field_info in enumerate(fields):
                    y_pos = y_start + i * 80
                    create_field_ui(column_x, y_pos, field_info, column_width)
                total_form_height = len(fields) * 80 + 140
                self.max_scroll = max(0, total_form_height - WINDOW_HEIGHT)
            elif self.card_type == "Location Card":
                # Location cards now support 1 or 2 states (Location/Location)
                # Spawn location options
                SPAWN_LOCATION_OPTIONS = ["false", "true"]
                RANGE_TYPE_OPTIONS = ["area_effect", "line_of_sight", "melee", "perimeter", "echo", "multi_echo", "mist_shadow"]
                # State 1 fields (left column)
                left_fields = [
                    ("Name", "text"),
                    ("Description", "text"),
                    # Outcomes and Choices use visual editors below
                    ("Shop_Deck", "text"),
                    ("Shop_Size", "text"),
                    ("Shop_Currency", "dropdown", CURRENCY_TYPES, "metal"),
                    ("Shop_Cycle_Turns", "text"),
                    ("Is_Spawn_Location", "dropdown", SPAWN_LOCATION_OPTIONS, "false"),  # Enemy spawn location
                    ("Health", "text"),  # Health for enemy spawn locations
                    ("Spawn_Enemy_Deck", "text"),  # Deck file for spawning enemies
                    ("Is_NPC_Spawn_Location", "dropdown", SPAWN_LOCATION_OPTIONS, "false"),  # NPC spawn location (church)
                    ("NPC_Health", "text"),  # Health for NPC spawn locations (can be destroyed by enemies)
                    ("NPC_Spawn_Deck", "text"),  # Deck file for spawning NPCs
                    # Defense Attack 1 fields
                    ("Defense_Enabled", "dropdown", SPAWN_LOCATION_OPTIONS, "false"),
                    ("Defense_Requires_NPC", "dropdown", SPAWN_LOCATION_OPTIONS, "false"),
                    ("Defense_Damage", "text"),
                    ("Defense_Range_Type", "dropdown", RANGE_TYPE_OPTIONS, "area_effect"),
                    ("Defense_Range_Distance", "text"),
                    ("Defense_Include_Position", "dropdown", SPAWN_LOCATION_OPTIONS, "false"),
                    ("Defense_Exclude_Adjacent", "dropdown", SPAWN_LOCATION_OPTIONS, "false"),
                    ("Defense_Passthrough_Chance", "text"),
                    ("Defense_Color_R", "text"),
                    ("Defense_Color_G", "text"),
                    ("Defense_Color_B", "text"),
                    # Defense Attack 2 fields (secondary)
                    ("Defense2_Enabled", "dropdown", SPAWN_LOCATION_OPTIONS, "false"),
                    ("Defense2_Requires_NPC", "dropdown", SPAWN_LOCATION_OPTIONS, "false"),
                    ("Defense2_Damage", "text"),
                    ("Defense2_Range_Type", "dropdown", RANGE_TYPE_OPTIONS, "area_effect"),
                    ("Defense2_Range_Distance", "text"),
                    ("Defense2_Include_Position", "dropdown", SPAWN_LOCATION_OPTIONS, "false"),
                    ("Defense2_Exclude_Adjacent", "dropdown", SPAWN_LOCATION_OPTIONS, "false"),
                    ("Defense2_Passthrough_Chance", "text"),
                    ("Defense2_Color_R", "text"),
                    ("Defense2_Color_G", "text"),
                    ("Defense2_Color_B", "text"),
                    ("Background Image File Path", "file"),
                    ("Location Image File Path", "file")
                ]

                if self.state == 2:
                    # 2-state Location/Location card
                    # Middle column: upgrade requirements
                    middle_fields = [
                        ("Upgrade_NPC_Type", "dropdown", ALLEGIANCE_TYPES, "Allied"),
                        ("Upgrade_Material_Cost", "text"),  # JSON: {"Raw Materials":10}
                    ]
                    # Right column: state 2 fields
                    right_fields = [
                        ("2nd_state_Name", "text"),
                        ("2nd_state_Description", "text"),
                        # 2nd_state Outcomes and Choices use visual editors below
                        ("2nd_state_Shop_Deck", "text"),
                        ("2nd_state_Shop_Size", "text"),
                        ("2nd_state_Shop_Currency", "dropdown", CURRENCY_TYPES, "metal"),
                        ("2nd_state_Shop_Cycle_Turns", "text"),
                        ("2nd_state_Is_Spawn_Location", "dropdown", SPAWN_LOCATION_OPTIONS, "false"),  # Usually false for ruins
                        ("2nd_state_Health", "text"),  # Usually 0 for ruins
                        ("2nd_state_Spawn_Enemy_Deck", "text"),  # Usually empty for ruins
                        ("2nd_state_Is_NPC_Spawn_Location", "dropdown", SPAWN_LOCATION_OPTIONS, "false"),  # Usually false for ruins
                        ("2nd_state_NPC_Health", "text"),  # Usually 0 for ruins
                        ("2nd_state_NPC_Spawn_Deck", "text"),  # Usually empty for ruins
                        # Defense Attack 1 fields (state 2)
                        ("2nd_state_Defense_Enabled", "dropdown", SPAWN_LOCATION_OPTIONS, "false"),
                        ("2nd_state_Defense_Requires_NPC", "dropdown", SPAWN_LOCATION_OPTIONS, "false"),
                        ("2nd_state_Defense_Damage", "text"),
                        ("2nd_state_Defense_Range_Type", "dropdown", RANGE_TYPE_OPTIONS, "area_effect"),
                        ("2nd_state_Defense_Range_Distance", "text"),
                        ("2nd_state_Defense_Include_Position", "dropdown", SPAWN_LOCATION_OPTIONS, "false"),
                        ("2nd_state_Defense_Exclude_Adjacent", "dropdown", SPAWN_LOCATION_OPTIONS, "false"),
                        ("2nd_state_Defense_Passthrough_Chance", "text"),
                        ("2nd_state_Defense_Color_R", "text"),
                        ("2nd_state_Defense_Color_G", "text"),
                        ("2nd_state_Defense_Color_B", "text"),
                        # Defense Attack 2 fields (state 2, secondary)
                        ("2nd_state_Defense2_Enabled", "dropdown", SPAWN_LOCATION_OPTIONS, "false"),
                        ("2nd_state_Defense2_Requires_NPC", "dropdown", SPAWN_LOCATION_OPTIONS, "false"),
                        ("2nd_state_Defense2_Damage", "text"),
                        ("2nd_state_Defense2_Range_Type", "dropdown", RANGE_TYPE_OPTIONS, "area_effect"),
                        ("2nd_state_Defense2_Range_Distance", "text"),
                        ("2nd_state_Defense2_Include_Position", "dropdown", SPAWN_LOCATION_OPTIONS, "false"),
                        ("2nd_state_Defense2_Exclude_Adjacent", "dropdown", SPAWN_LOCATION_OPTIONS, "false"),
                        ("2nd_state_Defense2_Passthrough_Chance", "text"),
                        ("2nd_state_Defense2_Color_R", "text"),
                        ("2nd_state_Defense2_Color_G", "text"),
                        ("2nd_state_Defense2_Color_B", "text"),
                        ("2nd_state_Location Image File Path", "file")
                    ]

                    column_width = 280
                    spacing = 30
                    total_width = 3 * column_width + 2 * spacing
                    left_margin = (WINDOW_WIDTH - total_width) // 2
                    column1_x = left_margin
                    column2_x = column1_x + column_width + spacing
                    column3_x = column2_x + column_width + spacing

                    for i, field_info in enumerate(left_fields):
                        y_pos = y_start + i * 70
                        create_field_ui(column1_x, y_pos, field_info, column_width)

                    for i, field_info in enumerate(middle_fields):
                        y_pos = y_start + i * 70
                        create_field_ui(column2_x, y_pos, field_info, column_width)

                    for i, field_info in enumerate(right_fields):
                        y_pos = y_start + i * 70
                        create_field_ui(column3_x, y_pos, field_info, column_width)

                    # Visual editors for Outcomes/Choices below standard fields
                    editor_y = y_start + max(len(left_fields), len(right_fields)) * 70 + 20

                    oe_left = LocationOutcomeEditorWidget("Outcomes", column1_x, editor_y,
                                                           column_width, self.ui_elements)
                    oe_left.build_all()
                    self.outcome_editors.append(oe_left)

                    ce_left_y = editor_y + oe_left.get_total_height() + 10
                    ce_left = LocationChoiceEditorWidget("Choices", column1_x, ce_left_y,
                                                          column_width, self.ui_elements)
                    ce_left.build_all()
                    self.outcome_editors.append(ce_left)

                    oe_right = LocationOutcomeEditorWidget("2nd_state_Outcomes", column3_x, editor_y,
                                                            column_width, self.ui_elements)
                    oe_right.build_all()
                    self.outcome_editors.append(oe_right)

                    ce_right_y = editor_y + oe_right.get_total_height() + 10
                    ce_right = LocationChoiceEditorWidget("2nd_state_Choices", column3_x, ce_right_y,
                                                           column_width, self.ui_elements)
                    ce_right.build_all()
                    self.outcome_editors.append(ce_right)

                    total_form_height = max(
                        ce_left_y + ce_left.get_total_height(),
                        ce_right_y + ce_right.get_total_height()
                    ) + 60
                else:
                    # Single-state Location card
                    column_width = 300
                    column_x = (WINDOW_WIDTH - column_width) // 2
                    for i, field_info in enumerate(left_fields):
                        y_pos = y_start + i * 80
                        create_field_ui(column_x, y_pos, field_info, column_width)

                    # Visual editors for Outcomes/Choices below standard fields
                    editor_y = y_start + len(left_fields) * 80 + 20

                    oe = LocationOutcomeEditorWidget("Outcomes", column_x, editor_y,
                                                      column_width, self.ui_elements)
                    oe.build_all()
                    self.outcome_editors.append(oe)

                    ce_y = editor_y + oe.get_total_height() + 10
                    ce = LocationChoiceEditorWidget("Choices", column_x, ce_y,
                                                     column_width, self.ui_elements)
                    ce.build_all()
                    self.outcome_editors.append(ce)

                    total_form_height = ce_y + ce.get_total_height() + 60

                self.max_scroll = max(0, total_form_height - WINDOW_HEIGHT)
            elif self.card_type == "Transition Card":
                # Transition Cards - world events that happen each turn cycle
                # Standard fields (no Outcomes - those use visual editor)
                left_fields = [
                    ("Name", "text"),
                    ("Description", "text"),
                    ("Background Image", "file"),
                ]
                right_fields = [
                    ("2nd_state_Name", "text"),
                    ("2nd_state_Description", "text"),
                    ("2nd_state_Background Image", "file"),
                ]
                column_width = 400
                spacing = 50
                left_column_x = (WINDOW_WIDTH - 2 * column_width - spacing) // 2
                right_column_x = left_column_x + column_width + spacing

                for i, field_info in enumerate(left_fields):
                    y_pos = y_start + i * 80
                    create_field_ui(left_column_x, y_pos, field_info, column_width)

                for i, field_info in enumerate(right_fields):
                    y_pos = y_start + i * 80
                    create_field_ui(right_column_x, y_pos, field_info, column_width)

                # Visual outcome editors below the standard fields
                outcome_y = y_start + max(len(left_fields), len(right_fields)) * 80 + 20
                oe_left = OutcomeEditorWidget("Outcomes", "transition", left_column_x, outcome_y, column_width, self.ui_elements)
                oe_left.build_all()
                self.outcome_editors.append(oe_left)

                oe_right = OutcomeEditorWidget("2nd_state_Outcomes", "transition", right_column_x, outcome_y, column_width, self.ui_elements)
                oe_right.build_all()
                self.outcome_editors.append(oe_right)

                total_form_height = outcome_y + max(oe_left.get_total_height(), oe_right.get_total_height()) + 60
                self.max_scroll = max(0, total_form_height - WINDOW_HEIGHT)
            elif self.card_type == "Instance Card":
                # Instance Card - single state, defines random event outcomes
                # Standard fields (no Outcomes - those use visual editor)
                subclass_options = ["Environmental", "Combat", "Social", "Discovery", "Danger"]
                fields = [
                    ("Name", "text"),
                    ("Description", "text"),
                    ("Subclass", "dropdown", subclass_options, "Environmental"),
                    ("Image_File_Path", "file"),
                ]
                column_width = 400
                column_x = (WINDOW_WIDTH - column_width) // 2
                for i, field_info in enumerate(fields):
                    y_pos = y_start + i * 80
                    create_field_ui(column_x, y_pos, field_info, column_width)

                # Visual outcome editor below standard fields
                outcome_y = y_start + len(fields) * 80 + 20
                oe = OutcomeEditorWidget("Outcomes", "instance", column_x, outcome_y, column_width, self.ui_elements)
                oe.build_all()
                self.outcome_editors.append(oe)

                total_form_height = outcome_y + oe.get_total_height() + 60
                self.max_scroll = max(0, total_form_height - WINDOW_HEIGHT)
            else:
                fields = []
                column_width = 300
                column_x = (WINDOW_WIDTH - column_width) // 2
                for i, field_info in enumerate(fields):
                    y_pos = y_start + i * 80
                    create_field_ui(column_x, y_pos, field_info, column_width)
                total_form_height = len(fields) * 80 + 140
                self.max_scroll = max(0, total_form_height - WINDOW_HEIGHT)
                
    def handle_event(self, event):
        # Forward events to outcome editors first
        for oe in self.outcome_editors:
            if oe.handle_event(event):
                # Prune dead element IDs and re-register new elements
                live_ids = {id(el) for el in self.ui_elements}
                self._original_positions = {k: v for k, v in self._original_positions.items() if k in live_ids}
                self._apply_scroll()
                # Recalculate max_scroll after rebuild
                max_h = 0
                for oe2 in self.outcome_editors:
                    h = oe2.y + oe2.get_total_height()
                    if h > max_h:
                        max_h = h
                if max_h > 0:
                    self.max_scroll = max(0, max_h + 60 - WINDOW_HEIGHT)
                return

        if event.type == pygame_gui.UI_BUTTON_PRESSED:
            if event.ui_element == self.back_button:
                if self.current_screen == "subclass_selection" or self.current_screen == "state_selection":
                    self.back_action()
                elif self.current_screen == "blueprint_subclass_selection":
                    self.current_screen = "subclass_selection"
                    self.selected_subclass = None
                    self.state = None
                    self.initialize_screen()
                elif self.current_screen == "skill_subclass_selection":
                    self.current_screen = "subclass_selection"
                    self.selected_subclass = None
                    self.state = None
                    self.initialize_screen()
                elif self.current_screen == "input_form":
                    if self.card_type == "Document Card" and self.selected_subclass == "Blueprint":
                        self.current_screen = "blueprint_subclass_selection"
                    elif self.card_type == "Document Card" and self.selected_subclass == "Skill_Tome":
                        self.current_screen = "skill_subclass_selection"
                    elif self.card_type == "Document Card" and self.selected_subclass == "Location_Plan":
                        self.current_screen = "subclass_selection"
                    elif self.card_type == "Location Card":
                        self.current_screen = "state_selection"
                    elif self.card_type == "Quest Card":
                        # Quest Card goes back to card type selection (main menu)
                        self.back_action()
                        return
                    else:
                        self.current_screen = "subclass_selection" if self.card_type == "Document Card" else "state_selection"
                    self.state = None
                    self.initialize_screen()
                elif self.current_screen == "subclass_selection" and self.card_type == "Junk Card":
                    self.current_screen = "state_selection"
                    self.selected_subclass = None
                    self.initialize_screen()

            elif self.current_screen == "subclass_selection" and self.card_type == "Document Card":
                for subclass in ["Blueprint", "Skill_Tome", "Location_Plan", "Guide", "Searchable", "Journal", "Map", "Note", "Book", "Pamphlet"]:
                    if event.ui_element.object_ids and event.ui_element.object_ids[0] == f"#subclass_{subclass}":
                        self.selected_subclass = subclass
                        self.state = 2 if subclass in ["Blueprint", "Skill_Tome", "Location_Plan", "Guide", "Searchable"] else 1
                        if subclass == "Blueprint":
                            self.current_screen = "blueprint_subclass_selection"
                        elif subclass == "Skill_Tome":
                            self.current_screen = "skill_subclass_selection"
                        elif subclass == "Location_Plan":
                            self.current_screen = "input_form"  # Goes directly to form for Document/Location
                        else:
                            self.current_screen = "input_form"
                        self.initialize_screen()
                        break

            elif self.current_screen == "blueprint_subclass_selection":
                for subclass in ["Blueprint_to_Weapon", "Blueprint_to_Tool", "Blueprint_to_Consumable_Item"]:
                    if event.ui_element.object_ids and event.ui_element.object_ids[0] == f"#blueprint_subclass_{subclass}":
                        self.selected_blueprint_subclass = subclass
                        self.current_screen = "input_form"
                        self.initialize_screen()
                        break

            elif self.current_screen == "skill_subclass_selection":
                for subclass in ["Skill_Attack", "Skill_Buff_Heal", "Skill_Passive"]:
                    if event.ui_element.object_ids and event.ui_element.object_ids[0] == f"#skill_subclass_{subclass}":
                        self.selected_skill_subclass = subclass
                        self.current_screen = "input_form"
                        self.initialize_screen()
                        break

            elif self.current_screen == "state_selection":
                if event.ui_element == self.state_1_button:
                    self.state = 1
                    self.current_screen = "input_form"
                    self.initialize_screen()
                elif event.ui_element == self.state_2_button:
                    self.state = 2
                    self.current_screen = "subclass_selection" if self.card_type == "Junk Card" else "input_form"
                    self.initialize_screen()

            elif self.current_screen == "subclass_selection" and self.card_type == "Junk Card":
                for subclass in ["Junk_to_Weapon", "Junk_to_Tool", "Junk_to_Consumable_Item"]:
                    if event.ui_element.object_ids and event.ui_element.object_ids[0] == f"#junk_subclass_{subclass}":
                        self.selected_subclass = subclass
                        self.current_screen = "input_form"
                        self.initialize_screen()
                        break

            elif event.ui_element == self.submit_button and self.current_screen == "input_form":
                self.submit_card()

            else:
                for entry, browse, field in self.file_inputs:
                    if event.ui_element == browse:
                        root = tk.Tk()
                        root.withdraw()
                        file_path = filedialog.askopenfilename(
                            filetypes=[("Image files", "*.png *.jpg *.jpeg *.bmp *.gif")]
                        )
                        root.destroy()
                        if file_path and file_path.lower().endswith(SUPPORTED_IMAGE_FORMATS):
                            entry.set_text(file_path)
                            try:
                                pygame.image.load(file_path)
                            except pygame.error:
                                print(f"Error: Cannot load image file: {file_path}")
                                entry.set_text("")

        elif event.type == pygame.MOUSEWHEEL and self.current_screen == "input_form":
            self.scroll_offset -= event.y * 20
            self.scroll_offset = max(0, min(self.scroll_offset, self.max_scroll))
            self._apply_scroll()

    def submit_card(self):
        # Determine card_type - use compound format for two-state cards
        card_type_value = self.card_type
        if self.state == 2 and self.selected_subclass == "Skill_Tome":
            card_type_value = "Document/Skill"
        elif self.state == 2 and self.selected_subclass == "Location_Plan":
            card_type_value = "Document/Location"
        elif self.card_type == "Location Card" and self.state == 2:
            card_type_value = "Location/Location"

        card_data = {
            "card_type": card_type_value,
            "subclass": self.selected_subclass if self.card_type in ["Document Card", "Junk Card"] else None,
            "blueprint_subclass": self.selected_blueprint_subclass if self.selected_subclass == "Blueprint" else None,
            "skill_subclass": self.selected_skill_subclass if self.selected_subclass == "Skill_Tome" else None,
            "states": self.state,
            "data": {entry[1]: entry[0].get_text() for entry in self.input_boxes}
        }
        card_data["data"].update({entry[2]: entry[0].get_text() for entry in self.file_inputs})
        card_data["data"].update({dropdown[1]: dropdown[0].selected_option[0] if isinstance(dropdown[0].selected_option, tuple) else dropdown[0].selected_option for dropdown in self.dropdown_inputs})

        # Add outcome editor data
        for oe in self.outcome_editors:
            card_data["data"][oe.field_name] = oe.serialize_to_json_string()

        # Validate JSON fields before saving
        is_valid, errors = validate_card_json_fields(card_data)
        if not is_valid:
            error_msg = "JSON Validation Errors:\n" + "\n".join(errors)
            print(error_msg)
            self.show_validation_error(errors)
            return

        # Debug print to verify dropdown values
        print("Submitting card data:")
        for key, value in card_data["data"].items():
            print(f"{key}: {value} (type: {type(value)})")

        card_id = str(uuid.uuid4())
        card_file = os.path.join("cards", f"{card_id}.json")
        with open(card_file, 'w') as f:
            json.dump(card_data, f, indent=2)

        with open(INDEX_FILE, 'r') as f:
            index = json.load(f)

        index[card_id] = {
            "type": self.card_type,
            "subclass": card_data["subclass"],
            "blueprint_subclass": card_data["blueprint_subclass"],
            "skill_subclass": card_data.get("skill_subclass"),
            "states": self.state,
            "name": card_data["data"].get("Name",
                                        card_data["data"].get("Default Name", "Unnamed"))
        }

        with open(INDEX_FILE, 'w') as f:
            json.dump(index, f, indent=2)

        print(f"Card saved with ID: {card_id}")
        self.preview_card(card_data, card_id)

    def show_validation_error(self, errors):
        """Show validation errors in a popup window."""
        # Clear any existing error window
        if hasattr(self, 'error_window') and self.error_window:
            self.error_window.kill()

        error_text = "Cannot save card - JSON validation failed:\n\n"
        for error in errors:
            error_text += f"• {error}\n"
        error_text += "\nPlease fix the errors and try again."

        # Create error window
        window_width = 500
        window_height = 200 + len(errors) * 30
        window_x = (WINDOW_WIDTH - window_width) // 2
        window_y = (WINDOW_HEIGHT - window_height) // 2

        self.error_window = pygame_gui.elements.UIWindow(
            rect=pygame.Rect(window_x, window_y, window_width, window_height),
            manager=manager,
            window_display_title="Validation Error"
        )

        pygame_gui.elements.UITextBox(
            relative_rect=pygame.Rect(10, 10, window_width - 40, window_height - 80),
            html_text=error_text.replace('\n', '<br>'),
            manager=manager,
            container=self.error_window
        )

        pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect((window_width - 120) // 2, window_height - 70, 100, 40),
            text="OK",
            manager=manager,
            container=self.error_window
        )

    def preview_card(self, card_data, card_id):
        CardManager.instance.preview_screen = CardPreview(
            card_data,
            card_id,
            CardManager.instance.back_to_main,
            lambda: CardManager.instance.edit_card(self.card_type)
        )
        CardManager.instance.current_screen = "preview"

    def draw(self):
        screen.fill(DARK_CHARCOAL)

class DeckMaker:
    def __init__(self, back_action):
        self.back_action = back_action
        self.selected_cards = []
        self.ui_elements = []
        self.deck_name_entry = None
        self.back_image_entry = None
        self.back_image_browse = None
        self.available_cards_list = None
        self.selected_cards_list = None
        self.remove_button = None
        self.load_cards()
        os.makedirs("decks", exist_ok=True)

    def load_cards(self):
        manager.clear_and_reset()
        self.ui_elements = []
        self.selected_cards = []

        self.title = UILabel(
            relative_rect=pygame.Rect(0, 20, WINDOW_WIDTH, 40),
            text="Deck Maker",
            manager=manager,
            object_id="#title_label",
            anchors={'centerx': 'centerx'}
        )
        self.ui_elements.append(self.title)

        self.back_button = UIButton(
            relative_rect=pygame.Rect(20, 20, 100, 40),
            text="Back",
            manager=manager,
            object_id="#back_button"
        )
        self.ui_elements.append(self.back_button)

        column_width = WINDOW_WIDTH // 3
        y_start = 80
        list_height = WINDOW_HEIGHT - y_start - 150

        with open(INDEX_FILE, 'r') as f:
            index = json.load(f)

        self.cards = [(card_id, info) for card_id, info in index.items()]
        self.cards.sort(key=lambda x: x[1]['name'].lower())
        available_cards_dict = {info['name']: card_id for card_id, info in self.cards}

        self.available_cards_list = pygame_gui.elements.UISelectionList(
            relative_rect=pygame.Rect(20, y_start, column_width - 40, list_height),
            item_list=list(available_cards_dict.keys()),
            manager=manager,
            allow_multi_select=True,
            object_id="#available_cards_list"
        )
        self.ui_elements.append(self.available_cards_list)
        self.available_cards_dict = available_cards_dict

        deck_info_x = column_width
        self.deck_name_label = UILabel(
            relative_rect=pygame.Rect(deck_info_x + 20, y_start, column_width - 40, 30),
            text="Deck Name:",
            manager=manager
        )
        self.deck_name_entry = UITextEntryLine(
            relative_rect=pygame.Rect(deck_info_x + 20, y_start + 30, column_width - 40, 40),
            manager=manager
        )
        self.back_image_label = UILabel(
            relative_rect=pygame.Rect(deck_info_x + 20, y_start + 90, column_width - 40, 30),
            text="Back Image (Optional):",
            manager=manager
        )
        self.back_image_entry = UITextEntryLine(
            relative_rect=pygame.Rect(deck_info_x + 20, y_start + 120, column_width - 120, 40),
            manager=manager
        )
        self.back_image_browse = UIButton(
            relative_rect=pygame.Rect(deck_info_x + column_width - 100, y_start + 120, 80, 40),
            text="Browse",
            manager=manager,
            object_id="#browse_back_image"
        )
        self.ui_elements.extend([
            self.deck_name_label, self.deck_name_entry,
            self.back_image_label, self.back_image_entry,
            self.back_image_browse
        ])

        selected_cards_x = 2 * column_width
        self.selected_cards_label = UILabel(
            relative_rect=pygame.Rect(selected_cards_x + 20, y_start, column_width - 40, 30),
            text="Selected Cards:",
            manager=manager
        )
        self.ui_elements.append(self.selected_cards_label)

        self.selected_cards_list = pygame_gui.elements.UISelectionList(
            relative_rect=pygame.Rect(selected_cards_x + 20, y_start + 30, column_width - 40, list_height - 30),
            item_list=[],
            manager=manager,
            allow_multi_select=True,
            object_id="#selected_cards_list"
        )
        self.ui_elements.append(self.selected_cards_list)

        button_y = WINDOW_HEIGHT - 60
        button_width = (column_width - 70) // 4
        self.create_deck_button = UIButton(
            relative_rect=pygame.Rect(selected_cards_x + 20, button_y, button_width, 40),
            text="Create Deck",
            manager=manager,
            object_id="#create_deck"
        )
        self.cancel_button = UIButton(
            relative_rect=pygame.Rect(selected_cards_x + 20 + button_width + 10, 
                                   button_y, button_width, 40),
            text="Cancel",
            manager=manager,
            object_id="#cancel_deck"
        )
        self.remove_button = UIButton(
            relative_rect=pygame.Rect(selected_cards_x + 20 + 2 * (button_width + 10), 
                                   button_y, button_width, 40),
            text="Remove",
            manager=manager,
            object_id="#remove_selected"
        )
        self.main_menu_button = UIButton(
            relative_rect=pygame.Rect(selected_cards_x + 20 + 3 * (button_width + 10), 
                                   button_y, button_width, 40),
            text="Main Menu",
            manager=manager,
            object_id="#main_menu"
        )
        self.ui_elements.extend([
            self.create_deck_button, self.cancel_button,
            self.remove_button, self.main_menu_button
        ])

    def update_selected_cards(self):
        selected_names = self.available_cards_list.get_multi_selection()
        self.selected_cards = [self.available_cards_dict[name] for name in selected_names 
                             if name in self.available_cards_dict]
        
        selected_names_list = [info['name'] for card_id, info in self.cards 
                             if card_id in self.selected_cards]
        self.selected_cards_list.set_item_list(selected_names_list)

    def remove_selected_cards(self):
        selected_names_to_remove = self.selected_cards_list.get_multi_selection()
        if not selected_names_to_remove:
            return
        
        self.selected_cards = [card_id for card_id in self.selected_cards 
                             if next(info['name'] for cid, info in self.cards if cid == card_id) 
                             not in selected_names_to_remove]
        
        selected_names_list = [info['name'] for card_id, info in self.cards 
                             if card_id in self.selected_cards]
        self.selected_cards_list.set_item_list(selected_names_list)
        
        current_selections = self.available_cards_list.get_multi_selection()
        all_cards = [info['name'] for _, info in self.cards]
        self.available_cards_list.set_item_list(all_cards)

    def create_deck(self):
        deck_name = self.deck_name_entry.get_text().strip()
        back_image = self.back_image_entry.get_text().strip()

        if not deck_name:
            print("Error: Deck name is required")
            return
        if not self.selected_cards:
            print("Error: At least one card must be selected")
            return

        safe_filename = re.sub(r'[^\w\s-]', '', deck_name).strip().replace(' ', '_')
        if not safe_filename:
            safe_filename = "unnamed_deck"

        deck_data = {
            "deck_name": deck_name,
            "back_image": back_image if back_image else None,
            "cards": self.selected_cards
        }

        deck_id = str(uuid.uuid4())
        deck_file = os.path.join(DECKS_DIR, f"{safe_filename}_{deck_id}.json")
        
        try:
            with open(deck_file, 'w') as f:
                json.dump(deck_data, f, indent=2)
            print(f"Deck saved: {deck_file}")
            self.load_cards()
        except Exception as e:
            print(f"Error saving deck: {e}")

    def handle_event(self, event):
        if event.type == pygame_gui.UI_BUTTON_PRESSED:
            if event.ui_element == self.back_button:
                self.back_action()
            elif event.ui_element == self.create_deck_button:
                self.create_deck()
            elif event.ui_element == self.cancel_button:
                self.load_cards()
            elif event.ui_element == self.main_menu_button:
                CardManager.instance.back_to_main()
            elif event.ui_element == self.back_image_browse:
                root = tk.Tk()
                root.withdraw()
                file_path = filedialog.askopenfilename(
                    filetypes=[("Image files", "*.png *.jpg *.jpeg *.bmp *.gif")]
                )
                root.destroy()
                if file_path:
                    self.back_image_entry.set_text(file_path)
            elif event.ui_element == self.remove_button:
                self.remove_selected_cards()
        elif event.type == pygame_gui.UI_SELECTION_LIST_NEW_SELECTION:
            if event.ui_element == self.available_cards_list:
                self.update_selected_cards()

    def draw(self):
        screen.fill(DARK_CHARCOAL)

class CardManager:
    instance = None

    def __init__(self):
        CardManager.instance = self
        self.current_screen = "main"
        self.creation_screen = None
        self.viewer_screen = None
        self.editor_screen = None
        self.preview_screen = None
        self.deck_maker_screen = None
        self.ui_elements = []
        self.initialize_buttons()

    def initialize_buttons(self):
        manager.clear_and_reset()
        self.ui_elements = []
        
        self.title = UILabel(
            relative_rect=pygame.Rect(0, 20, WINDOW_WIDTH, 40),
            text="Card Management System",
            manager=manager,
            object_id="#title_label",
            anchors={'centerx': 'centerx'}
        )
        self.ui_elements.append(self.title)
        
        self.create_button = UIButton(
            relative_rect=pygame.Rect((WINDOW_WIDTH - 200) // 2, 200, 200, 40),
            text="Create Card",
            manager=manager,
            object_id="#create_card"
        )
        self.edit_button = UIButton(
            relative_rect=pygame.Rect((WINDOW_WIDTH - 200) // 2, 260, 200, 40),
            text="Edit Card",
            manager=manager,
            object_id="#edit_card"
        )
        self.view_button = UIButton(
            relative_rect=pygame.Rect((WINDOW_WIDTH - 200) // 2, 320, 200, 40),
            text="View Cards",
            manager=manager,
            object_id="#view_cards"
        )
        self.deck_maker_button = UIButton(
            relative_rect=pygame.Rect((WINDOW_WIDTH - 200) // 2, 380, 200, 40),
            text="Deck Maker",
            manager=manager,
            object_id="#deck_maker"
        )
        self.quit_button = UIButton(
            relative_rect=pygame.Rect((WINDOW_WIDTH - 200) // 2, 440, 200, 40),
            text="Quit",
            manager=manager,
            object_id="#quit_button"
        )
        self.update_index_button = UIButton(
            relative_rect=pygame.Rect((WINDOW_WIDTH - 200) // 2, 500, 200, 40),
            text="Update Card Index",
            manager=manager,
            object_id="#update_index"
        )
        self.ui_elements.extend([
            self.create_button, self.edit_button, self.view_button,
            self.deck_maker_button, self.quit_button, self.update_index_button
        ])

        self.card_types = [
            "Junk Card", "Document Card", "Enemy Card", "NPC Card",
            "Location Card", "Quest Card", "Instance Card", "Boss Card", "Transition Card"
        ]
        self.create_buttons = []
        self.edit_buttons = []
        self.view_buttons = []

    def show_create_menu(self):
        manager.clear_and_reset()
        self.ui_elements = []
        self.current_screen = "create"
        
        self.title = UILabel(
            relative_rect=pygame.Rect(0, 20, WINDOW_WIDTH, 40),
            text="Create Card",
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
        self.ui_elements.extend([self.title, self.back_button])
        
        y_start = 80
        for i, card_type in enumerate(self.card_types):
            y_pos = y_start + i * 60
            button = UIButton(
                relative_rect=pygame.Rect((WINDOW_WIDTH - 200) // 2, y_pos, 200, 40),
                text=f"Create {card_type}",
                manager=manager,
                object_id=f"#create_{card_type.replace(' ', '_')}"
            )
            self.create_buttons.append((button, card_type))
            self.ui_elements.append(button)

    def show_edit_menu(self):
        manager.clear_and_reset()
        self.ui_elements = []
        self.current_screen = "edit"
        
        self.title = UILabel(
            relative_rect=pygame.Rect(0, 20, WINDOW_WIDTH, 40),
            text="Edit Card",
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
        self.ui_elements.extend([self.title, self.back_button])
        
        y_start = 80
        for i, card_type in enumerate(self.card_types):
            y_pos = y_start + i * 60
            button = UIButton(
                relative_rect=pygame.Rect((WINDOW_WIDTH - 200) // 2, y_pos, 200, 40),
                text=f"Edit {card_type}",
                manager=manager,
                object_id=f"#edit_{card_type.replace(' ', '_')}"
            )
            self.edit_buttons.append((button, card_type))
            self.ui_elements.append(button)

    def show_view_menu(self):
        manager.clear_and_reset()
        self.ui_elements = []
        self.current_screen = "view"
        
        self.title = UILabel(
            relative_rect=pygame.Rect(0, 20, WINDOW_WIDTH, 40),
            text="View Cards",
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
        self.ui_elements.extend([self.title, self.back_button])
        
        y_start = 80
        for i, card_type in enumerate(self.card_types):
            y_pos = y_start + i * 60
            button = UIButton(
                relative_rect=pygame.Rect((WINDOW_WIDTH - 200) // 2, y_pos, 200, 40),
                text=f"View {card_type}s",
                manager=manager,
                object_id=f"#view_{card_type.replace(' ', '_')}"
            )
            self.view_buttons.append((button, card_type))
            self.ui_elements.append(button)

    def show_deck_maker(self):
        self.current_screen = "deck_maker"
        self.deck_maker_screen = DeckMaker(self.back_to_main)
        self.creation_screen = None
        self.viewer_screen = None
        self.editor_screen = None
        self.preview_screen = None

    def back_to_main(self):
        self.current_screen = "main"
        self.creation_screen = None
        self.viewer_screen = None
        self.editor_screen = None
        self.preview_screen = None
        self.deck_maker_screen = None
        self.initialize_buttons()

    def create_card(self, card_type):
        self.current_screen = "creation"
        self.creation_screen = CardCreationScreen(card_type, self.show_create_menu)
        self.viewer_screen = None
        self.editor_screen = None
        self.preview_screen = None
        self.deck_maker_screen = None

    def edit_card(self, card_type):
        self.current_screen = "editor"
        self.editor_screen = CardEditor(card_type, self.show_edit_menu)
        self.creation_screen = None
        self.viewer_screen = None
        self.preview_screen = None
        self.deck_maker_screen = None

    def view_cards(self, card_type):
        self.current_screen = "viewer"
        self.viewer_screen = CardViewer(card_type, self.show_view_menu)
        self.creation_screen = None
        self.editor_screen = None
        self.preview_screen = None
        self.deck_maker_screen = None

    def update_card_index(self):
        index = {}
        for filename in os.listdir("cards"):
            if filename.endswith(".json") and filename != "card_index.json":
                card_id = os.path.splitext(filename)[0]
                try:
                    with open(os.path.join("cards", filename), 'r') as f:
                        card_data = json.load(f)
                    if "card_type" in card_data and "data" in card_data:
                        name = card_data["data"].get("Name", card_data["data"].get("Default Name", "Unnamed"))
                        index[card_id] = {
                            "type": card_data["card_type"],
                            "subclass": card_data.get("subclass"),
                            "blueprint_subclass": card_data.get("blueprint_subclass"),
                            "states": card_data.get("states"),
                            "name": name
                        }
                    else:
                        print(f"Skipping {filename}: missing 'card_type' or 'data'")
                except json.JSONDecodeError:
                    print(f"Error decoding JSON in {filename}")
                except Exception as e:
                    print(f"Error processing {filename}: {e}")
        with open(INDEX_FILE, 'w') as f:
            json.dump(index, f, indent=2)
        print("Card index updated.")

    def handle_event(self, event):
        if self.current_screen == "creation" and self.creation_screen:
            self.creation_screen.handle_event(event)
            return
        if self.current_screen == "viewer" and self.viewer_screen:
            self.viewer_screen.handle_event(event)
            return
        if self.current_screen == "editor" and self.editor_screen:
            self.editor_screen.handle_event(event)
            return
        if self.current_screen == "preview" and self.preview_screen:
            self.preview_screen.handle_event(event)
            return
        if self.current_screen == "deck_maker" and self.deck_maker_screen:
            self.deck_maker_screen.handle_event(event)
            return

        if event.type == pygame_gui.UI_BUTTON_PRESSED:
            if event.ui_element == self.create_button:
                self.show_create_menu()
            elif event.ui_element == self.edit_button:
                self.show_edit_menu()
            elif event.ui_element == self.view_button:
                self.show_view_menu()
            elif event.ui_element == self.deck_maker_button:
                self.show_deck_maker()
            elif event.ui_element == self.quit_button:
                pygame.quit()
                sys.exit()
            elif event.ui_element == self.update_index_button:
                self.update_card_index()
            elif self.current_screen in ["create", "edit", "view"] and event.ui_element == self.back_button:
                self.back_to_main()
            else:
                for button, card_type in self.create_buttons:
                    if event.ui_element == button:
                        self.create_card(card_type)
                        break
                for button, card_type in self.edit_buttons:
                    if event.ui_element == button:
                        self.edit_card(card_type)
                        break
                for button, card_type in self.view_buttons:
                    if event.ui_element == button:
                        self.view_cards(card_type)
                        break

    def draw(self):
        screen.fill(DARK_CHARCOAL)
        if self.current_screen == "creation" and self.creation_screen:
            self.creation_screen.draw()
        elif self.current_screen == "viewer" and self.viewer_screen:
            self.viewer_screen.draw()
        elif self.current_screen == "editor" and self.editor_screen:
            self.editor_screen.draw()
        elif self.current_screen == "preview" and self.preview_screen:
            self.preview_screen.draw()
        elif self.current_screen == "deck_maker" and self.deck_maker_screen:
            self.deck_maker_screen.draw()

def main():
    pygame.display.set_mode((1, 1))
    root = tk.Tk()
    root.withdraw()
    pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.FULLSCREEN)
    
    card_manager = CardManager()
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
            card_manager.handle_event(e)
            manager.process_events(e)

        manager.update(time_delta)
        card_manager.draw()
        manager.draw_ui(screen)
        display.flip()

if __name__ == "__main__":
    main()
