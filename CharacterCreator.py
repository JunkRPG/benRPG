import pygame
import sys
import tkinter as tk
from tkinter import filedialog
import pygame_gui
from pygame_gui.elements import UIButton, UITextEntryLine, UILabel, UIDropDownMenu, UISelectionList, UITextBox
import os
import json
import re
import datetime
from card_utils import load_card_index, load_card

# ========== CONSTANTS ==========

POINT_BUDGET = 30

STAT_CONFIG = {
    "hp":               {"label": "HP",        "min": 3,  "max": 18, "display_mult": 10},
    "movement":         {"label": "Movement",  "min": 2,  "max": 6,  "display_mult": 1},
    "projectile_range": {"label": "Proj Range","min": 2,  "max": 6,  "display_mult": 1},
    "melee_damage":     {"label": "Melee Dmg", "min": 1,  "max": 12, "display_mult": 1},
    "projectile_damage":{"label": "Proj Dmg",  "min": 1,  "max": 12, "display_mult": 1},
}

SPECIAL_ABILITIES = {
    "Piercing Shot": {
        "description": "Projectile attacks pierce through targets, hitting all units in a line.",
        "type": "passive",
        "summary": "Projectiles pierce all enemies in a line"
    },
    "Dual Strike": {
        "description": "Gain 2 attacks per turn instead of 1. Mix melee and projectile freely.",
        "type": "passive",
        "summary": "2 attacks per turn (any combination)"
    },
    "Spin Punch": {
        "description": "Active ability: Hit ALL adjacent hostile enemies with melee damage.",
        "type": "active",
        "summary": "AoE melee hitting all adjacent enemies"
    },
    "Heal": {
        "description": "Melee becomes Heal (20 HP) when no melee weapon equipped. Targets self or any adjacent unit.",
        "type": "passive",
        "summary": "Heal instead of melee (20 HP to any adjacent)"
    },
    "Master Builder": {
        "description": "Wood requirements in crafting/building auto-fulfilled when on forest terrain.",
        "type": "passive",
        "summary": "Wood auto-fulfilled on forest terrain"
    }
}

PRESET_CLASSES = {
    "Ranger": {
        "stats": {"hp": 5, "movement": 5, "projectile_range": 5, "melee_damage": 4, "projectile_damage": 8},
        "special": "Piercing Shot",
        "melee_name": "Fist",
        "proj_name": "Throw Rock",
        "kit": [
            {"card_id": "starter_ranger_bow", "state": 1},
            {"card_id": "starter_ranger_bowstring", "state": 1},
            {"card_id": "starter_ranger_curved_branch", "state": 1},
            {"card_id": "win_guide", "state": 1},
            {"card_id": "beta_junk_tool_scavengers_kit", "state": 2}
        ]
    },
    "Warrior": {
        "stats": {"hp": 10, "movement": 4, "projectile_range": 4, "melee_damage": 6, "projectile_damage": 6},
        "special": "Dual Strike",
        "melee_name": "Fist",
        "proj_name": "Throw Rock",
        "kit": [
            {"card_id": "starter_warrior_combat_bow", "state": 1},
            {"card_id": "starter_warrior_bowstring", "state": 1},
            {"card_id": "starter_warrior_metal_wraps", "state": 1},
            {"card_id": "starter_warrior_arrows", "state": 2},
            {"card_id": "win_guide", "state": 1},
            {"card_id": "beta_junk_tool_scavengers_kit", "state": 2}
        ]
    },
    "Tank": {
        "stats": {"hp": 15, "movement": 3, "projectile_range": 3, "melee_damage": 8, "projectile_damage": 4},
        "special": "Spin Punch",
        "melee_name": "Fist",
        "proj_name": "Throw Rock",
        "kit": [
            {"card_id": "starter_tank_sledgehammer_plans", "state": 1},
            {"card_id": "starter_tank_hammer_head", "state": 1},
            {"card_id": "starter_tank_branch", "state": 1},
            {"card_id": "win_guide", "state": 1},
            {"card_id": "beta_junk_tool_scavengers_kit", "state": 2}
        ]
    },
    "Healer": {
        "stats": {"hp": 5, "movement": 5, "projectile_range": 3, "melee_damage": 4, "projectile_damage": 4},
        "special": "Heal",
        "melee_name": "Fist",
        "proj_name": "Throw Rock",
        "kit": [
            {"card_id": "starter_healer_bow", "state": 1},
            {"card_id": "starter_healer_bowstring", "state": 1},
            {"card_id": "starter_healer_quiver_plans", "state": 1},
            {"card_id": "starter_healer_herb_bundle", "state": 1},
            {"card_id": "win_guide", "state": 1},
            {"card_id": "beta_junk_tool_scavengers_kit", "state": 2}
        ]
    },
    "Builder": {
        "stats": {"hp": 10, "movement": 4, "projectile_range": 4, "melee_damage": 6, "projectile_damage": 6},
        "special": "Master Builder",
        "melee_name": "Fist",
        "proj_name": "Throw Rock",
        "kit": [
            {"card_id": "starter_builder_hammer", "state": 1},
            {"card_id": "starter_builder_axe", "state": 1},
            {"card_id": "starter_builder_archer_tower_plans", "state": 1},
            {"card_id": "win_guide", "state": 1},
            {"card_id": "beta_junk_tool_scavengers_kit", "state": 2}
        ]
    }
}

SUGGESTED_KITS = {
    "Ranger Kit": [
        "starter_ranger_bow", "starter_ranger_bowstring", "starter_ranger_curved_branch",
        "win_guide", "beta_junk_tool_scavengers_kit"
    ],
    "Warrior Kit": [
        "starter_warrior_combat_bow", "starter_warrior_bowstring", "starter_warrior_metal_wraps",
        "starter_warrior_arrows", "win_guide", "beta_junk_tool_scavengers_kit"
    ],
    "Tank Kit": [
        "starter_tank_sledgehammer_plans", "starter_tank_hammer_head", "starter_tank_branch",
        "win_guide", "beta_junk_tool_scavengers_kit"
    ],
    "Healer Kit": [
        "starter_healer_bow", "starter_healer_bowstring", "starter_healer_quiver_plans",
        "starter_healer_herb_bundle", "win_guide", "beta_junk_tool_scavengers_kit"
    ],
    "Builder Kit": [
        "starter_builder_hammer", "starter_builder_axe", "starter_builder_archer_tower_plans",
        "win_guide", "beta_junk_tool_scavengers_kit"
    ],
    "Empty": []
}

MAX_KIT_CARDS = 6

DARK_CHARCOAL = (35, 35, 40)
PANEL_BG = (26, 26, 46)
PANEL_BORDER = (58, 58, 92)
GOLD = (255, 215, 0)
LIGHT_GOLD = (238, 221, 130)
WHITE = (255, 255, 255)
LIGHT_GRAY = (200, 200, 212)
DIM_GRAY = (120, 120, 140)
RED = (255, 80, 80)
GREEN = (100, 220, 100)
YELLOW_WARN = (255, 220, 50)


# ========== APP ==========

class CharacterCreator:
    def __init__(self):
        pygame.init()
        display_info = pygame.display.Info()
        self.W = display_info.current_w
        self.H = display_info.current_h
        self.screen = pygame.display.set_mode((self.W, self.H), pygame.FULLSCREEN)
        pygame.display.set_caption("Character Creator")
        self.manager = pygame_gui.UIManager((self.W, self.H), "theme.json")
        self.clock = pygame.time.Clock()

        os.makedirs("characters", exist_ok=True)

        # State
        self.stats = {}
        self.selected_special = "Piercing Shot"
        self.selected_kit = []  # list of {"card_id": ..., "state": ...}
        self.available_card_pool = []  # list of card_id strings
        self.card_names = {}  # card_id -> display name
        self.card_data_cache = {}  # card_id -> full card dict
        self.over_budget_warning = ""

        self._init_stats()
        self._load_card_pool()
        self._build_ui()

    # ---------- State helpers ----------

    def _init_stats(self):
        for key, cfg in STAT_CONFIG.items():
            self.stats[key] = cfg["min"]

    def _points_spent(self):
        return sum(self.stats[k] for k in STAT_CONFIG)

    def _points_remaining(self):
        return POINT_BUDGET - self._points_spent()

    def _display_value(self, key):
        return self.stats[key] * STAT_CONFIG[key]["display_mult"]

    def _load_card_pool(self):
        index = load_card_index(silent=True)
        pool = []
        universal = ["win_guide", "beta_junk_tool_scavengers_kit"]
        for card_id in index:
            if card_id.startswith("starter_") or card_id in universal:
                pool.append(card_id)
        # Also ensure universals are included even if missing from index
        for uid in universal:
            if uid not in pool:
                pool.append(uid)
        self.available_card_pool = sorted(pool)

        # Load display names and cache card data
        for card_id in self.available_card_pool:
            card = load_card(card_id, silent=True)
            if card:
                name = card.get("data", {}).get("Name", card_id)
                self.card_names[card_id] = f"{name} ({card_id})"
                self.card_data_cache[card_id] = card
            else:
                self.card_names[card_id] = card_id

    # ---------- UI construction ----------

    def _build_ui(self):
        W, H = self.W, self.H

        # Layout columns
        left_x = int(W * 0.02)
        left_w = int(W * 0.27)
        center_x = left_x + left_w + int(W * 0.015)
        center_w = int(W * 0.36)
        right_x = center_x + center_w + int(W * 0.015)
        right_w = W - right_x - int(W * 0.02)

        top_bar_h = int(H * 0.06)
        content_y = top_bar_h + int(H * 0.02)

        # ===== TOP BAR =====
        self.back_btn = UIButton(
            relative_rect=pygame.Rect(int(W * 0.01), int(H * 0.01), 100, 36),
            text="Back (ESC)", manager=self.manager)

        self.save_btn = UIButton(
            relative_rect=pygame.Rect(W - 220, int(H * 0.01), 100, 36),
            text="Save", manager=self.manager)

        self.load_btn = UIButton(
            relative_rect=pygame.Rect(W - 110, int(H * 0.01), 100, 36),
            text="Load", manager=self.manager)

        # ===== LEFT PANEL: Name + Stats =====
        y = content_y
        self.name_label = UILabel(
            relative_rect=pygame.Rect(left_x, y, left_w, 24),
            text="Character Name:", manager=self.manager)
        y += 28
        self.name_entry = UITextEntryLine(
            relative_rect=pygame.Rect(left_x, y, left_w, 36),
            manager=self.manager, placeholder_text="Enter name...")
        y += 50

        self.budget_label = UILabel(
            relative_rect=pygame.Rect(left_x, y, left_w, 28),
            text=f"Point Budget: {POINT_BUDGET}    Remaining: {self._points_remaining()}",
            manager=self.manager)
        y += 36

        # Stat rows: [-] value [+]
        self.stat_minus_btns = {}
        self.stat_plus_btns = {}
        self.stat_value_labels = {}
        self.stat_pts_labels = {}

        btn_size = 36
        label_w = 100
        val_w = 80

        for key, cfg in STAT_CONFIG.items():
            # Label
            UILabel(relative_rect=pygame.Rect(left_x, y + 4, label_w, 28),
                    text=cfg["label"] + ":", manager=self.manager)

            bx = left_x + label_w + 8
            self.stat_minus_btns[key] = UIButton(
                relative_rect=pygame.Rect(bx, y, btn_size, btn_size),
                text="-", manager=self.manager)

            self.stat_value_labels[key] = UILabel(
                relative_rect=pygame.Rect(bx + btn_size + 4, y + 4, val_w, 28),
                text=str(self._display_value(key)),
                manager=self.manager)

            self.stat_plus_btns[key] = UIButton(
                relative_rect=pygame.Rect(bx + btn_size + val_w + 8, y, btn_size, btn_size),
                text="+", manager=self.manager)

            # Points allocated label
            self.stat_pts_labels[key] = UILabel(
                relative_rect=pygame.Rect(bx + btn_size * 2 + val_w + 16, y + 4, 60, 28),
                text=f"({self.stats[key]} pts)", manager=self.manager)

            y += btn_size + 10

        y += 10
        self.reset_btn = UIButton(
            relative_rect=pygame.Rect(left_x, y, 140, 36),
            text="Reset Stats", manager=self.manager)

        self.warning_label = UILabel(
            relative_rect=pygame.Rect(left_x, y + 44, left_w, 28),
            text="", manager=self.manager)

        # Card info box
        info_y = y + 80
        UILabel(relative_rect=pygame.Rect(left_x, info_y, left_w, 24),
                text="CARD INFO", manager=self.manager)
        info_y += 26
        info_h = H - info_y - int(H * 0.02)
        self.card_info_box = UITextBox(
            html_text="<i>Select a card from the kit lists to see details.</i>",
            relative_rect=pygame.Rect(left_x, info_y, left_w, info_h),
            manager=self.manager)

        # ===== CENTER PANEL: Special + Attacks + Kit =====
        y = content_y

        UILabel(relative_rect=pygame.Rect(center_x, y, center_w, 24),
                text="SPECIAL ABILITY", manager=self.manager)
        y += 28

        self.special_btns = {}
        for ability_name in SPECIAL_ABILITIES:
            btn = UIButton(
                relative_rect=pygame.Rect(center_x, y, center_w, 32),
                text=ability_name, manager=self.manager)
            self.special_btns[ability_name] = btn
            y += 36

        self.special_desc_box = UITextBox(
            html_text=self._ability_desc_html(self.selected_special),
            relative_rect=pygame.Rect(center_x, y, center_w, 70),
            manager=self.manager)
        y += 80

        # Attack names
        UILabel(relative_rect=pygame.Rect(center_x, y, center_w, 24),
                text="ATTACK NAMES", manager=self.manager)
        y += 28

        half_w = (center_w - 10) // 2

        UILabel(relative_rect=pygame.Rect(center_x, y, half_w, 22),
                text="Projectile Attack:", manager=self.manager)
        UILabel(relative_rect=pygame.Rect(center_x + half_w + 10, y, half_w, 22),
                text="Melee Attack:", manager=self.manager)
        y += 24
        self.proj_name_entry = UITextEntryLine(
            relative_rect=pygame.Rect(center_x, y, half_w, 32),
            manager=self.manager, placeholder_text="Throw Rock")
        self.melee_name_entry = UITextEntryLine(
            relative_rect=pygame.Rect(center_x + half_w + 10, y, half_w, 32),
            manager=self.manager, placeholder_text="Fist")
        y += 44

        # Starting kit
        UILabel(relative_rect=pygame.Rect(center_x, y, center_w, 24),
                text="STARTING KIT", manager=self.manager)
        y += 28

        # Suggested kits dropdown
        UILabel(relative_rect=pygame.Rect(center_x, y, 80, 24),
                text="Suggest:", manager=self.manager)
        kit_options = list(SUGGESTED_KITS.keys())
        self.kit_dropdown = UIDropDownMenu(
            options_list=kit_options,
            starting_option=kit_options[0],
            relative_rect=pygame.Rect(center_x + 85, y, 180, 30),
            manager=self.manager)
        self.kit_apply_btn = UIButton(
            relative_rect=pygame.Rect(center_x + 270, y, 80, 30),
            text="Apply", manager=self.manager)
        y += 38

        list_h = int(H * 0.28)
        list_w = (center_w - 90) // 2

        UILabel(relative_rect=pygame.Rect(center_x, y, list_w, 22),
                text="Available Cards:", manager=self.manager)
        self.selected_count_label_rect = pygame.Rect(center_x + list_w + 90, y, list_w, 22)
        y += 24

        avail_names = [self.card_names.get(cid, cid) for cid in self.available_card_pool]
        self.avail_list = UISelectionList(
            relative_rect=pygame.Rect(center_x, y, list_w, list_h),
            item_list=avail_names,
            manager=self.manager)

        btn_x = center_x + list_w + 10
        btn_mid_y = y + list_h // 2 - 40
        self.add_btn = UIButton(
            relative_rect=pygame.Rect(btn_x, btn_mid_y, 70, 34),
            text="Add >>", manager=self.manager)
        self.remove_btn = UIButton(
            relative_rect=pygame.Rect(btn_x, btn_mid_y + 42, 70, 34),
            text="<< Remove", manager=self.manager)

        self.selected_list = UISelectionList(
            relative_rect=pygame.Rect(center_x + list_w + 90, y, list_w, list_h),
            item_list=[],
            manager=self.manager)

        # ===== RIGHT PANEL: Summary + Presets =====
        y = content_y

        UILabel(relative_rect=pygame.Rect(right_x, y, right_w, 24),
                text="CHARACTER SUMMARY", manager=self.manager)
        y += 28

        # Reserve area for custom-drawn summary
        self.summary_rect = pygame.Rect(right_x, y, right_w, int(H * 0.42))
        y = self.summary_rect.bottom + 16

        UILabel(relative_rect=pygame.Rect(right_x, y, right_w, 24),
                text="PRESETS", manager=self.manager)
        y += 28

        self.preset_btns = {}
        for preset_name in PRESET_CLASSES:
            btn = UIButton(
                relative_rect=pygame.Rect(right_x, y, right_w, 36),
                text=f"Load {preset_name}", manager=self.manager)
            self.preset_btns[preset_name] = btn
            y += 42

        # Update initial button states
        self._update_special_btn_visuals()
        self._update_stat_buttons()

    # ---------- UI helpers ----------

    def _ability_desc_html(self, name):
        ab = SPECIAL_ABILITIES.get(name, {})
        typ = ab.get("type", "?").capitalize()
        desc = ab.get("description", "")
        return f"<b>[{typ}]</b> {desc}"

    def _update_special_btn_visuals(self):
        for name, btn in self.special_btns.items():
            if name == self.selected_special:
                btn.set_text(f"> {name} <")
            else:
                btn.set_text(name)

    def _update_stat_buttons(self):
        remaining = self._points_remaining()
        for key, cfg in STAT_CONFIG.items():
            val = self.stats[key]
            self.stat_minus_btns[key].enable() if val > cfg["min"] else self.stat_minus_btns[key].disable()
            if val < cfg["max"] and remaining > 0:
                self.stat_plus_btns[key].enable()
            else:
                self.stat_plus_btns[key].disable()
            self.stat_value_labels[key].set_text(str(self._display_value(key)))
            self.stat_pts_labels[key].set_text(f"({self.stats[key]} pts)")

        self.budget_label.set_text(
            f"Point Budget: {POINT_BUDGET}    Remaining: {remaining}")

        # Over-budget warning
        if remaining < 0:
            self.over_budget_warning = f"Over budget by {-remaining} - adjust stats before saving."
            self.warning_label.set_text(self.over_budget_warning)
            self.save_btn.disable()
        else:
            self.over_budget_warning = ""
            self.warning_label.set_text("")
            self.save_btn.enable()

    def _update_selected_list_ui(self):
        names = []
        for item in self.selected_kit:
            cid = item["card_id"]
            names.append(self.card_names.get(cid, cid))
        self.selected_list.set_item_list(names)
        # Rebuild the selected count label through the manager
        # We'll just draw it manually in the render

    def _get_available_minus_selected(self):
        selected_ids = {item["card_id"] for item in self.selected_kit}
        return [cid for cid in self.available_card_pool if cid not in selected_ids]

    def _update_available_list_ui(self):
        available_ids = self._get_available_minus_selected()
        names = [self.card_names.get(cid, cid) for cid in available_ids]
        self.avail_list.set_item_list(names)

    def _build_card_info_html(self, card_id):
        card = self.card_data_cache.get(card_id)
        if not card:
            return f"<i>No data for {card_id}</i>"

        data = card.get("data", {})
        card_type = card.get("card_type", "Unknown")
        subclass = card.get("subclass", "")
        states = card.get("states", 1)

        lines = []
        # Header
        name1 = data.get("Name", card_id)
        lines.append(f"<b>{name1}</b>")
        type_line = card_type
        if subclass:
            type_line += f" ({subclass})"
        lines.append(f"<i>{type_line}</i>")

        # Description
        desc = data.get("Description", "")
        if desc:
            lines.append(f"<br>{desc}")

        # Material values
        mat_fields = [
            ("Raw Material Value", "Raw"),
            ("Refined Material Value", "Refined"),
            ("Metal Value", "Metal"),
            ("Wood Value", "Wood"),
        ]
        mat_parts = []
        for field, label in mat_fields:
            val = data.get(field, "")
            if val and val != "0":
                mat_parts.append(f"{label}: {val}")
        if mat_parts:
            lines.append(f"<br><b>Materials:</b> {', '.join(mat_parts)}")

        # Crafting requirements
        req_fields = [
            ("Requirements: Raw Materials", "Raw"),
            ("Requirements: Refined Materials", "Refined"),
            ("Requirements: Wood", "Wood"),
            ("Requirements: Metal", "Metal"),
        ]
        req_parts = []
        for field, label in req_fields:
            val = data.get(field, "")
            if val and val != "0" and val.strip():
                req_parts.append(f"{label}: {val}")
        specific = data.get("Requirements: Specific Cards", "")
        if specific and specific.strip():
            req_parts.append(f"Cards: {specific}")
        if req_parts:
            lines.append(f"<b>Craft Cost:</b> {', '.join(req_parts)}")

        # State 2 info
        if states >= 2:
            name2 = data.get("2nd_state_Name", "")
            lines.append(f"<br><b>--- Crafted: {name2 or 'State 2'} ---</b>")

            s2_type = data.get("2nd_state_Type", "")
            s2_subtype = data.get("2nd_state_Subtype", "")
            if s2_type:
                type_str = s2_type
                if s2_subtype:
                    type_str += f" / {s2_subtype}"
                lines.append(f"Type: {type_str}")

            # Weapon stats
            melee = data.get("2nd_state_Melee Damage", "")
            proj = data.get("2nd_state_Projectile Damage", "")
            if melee or proj:
                parts = []
                if melee and melee != "0":
                    parts.append(f"Melee: {melee}")
                if proj and proj != "0":
                    parts.append(f"Proj: {proj}")
                if parts:
                    lines.append(f"Damage: {', '.join(parts)}")

            # Range
            rng_type = data.get("2nd_state_Range_Type", "")
            rng_dist = data.get("2nd_state_Range_Distance", "")
            if rng_type:
                rng_str = f"Range: {rng_type}"
                if rng_dist:
                    rng_str += f" ({rng_dist} hexes)"
                lines.append(rng_str)

            # Ammo
            req_ammo = data.get("2nd_state_Requires_Ammo", "")
            if req_ammo and req_ammo.lower() == "true":
                compat = data.get("2nd_state_Compatible_Ammo", "Any")
                lines.append(f"Requires Ammo: {compat}")

            # Tool info
            tool_action = data.get("2nd_state_Tool_Action", "")
            if tool_action:
                lines.append(f"Action: {tool_action}")

            # Use/description for state 2
            s2_use = data.get("2nd_state_Use", "")
            s2_desc = data.get("2nd_state_Description", "")
            if s2_use:
                lines.append(f"<i>{s2_use}</i>")
            elif s2_desc:
                lines.append(f"<i>{s2_desc}</i>")

            # Guide info
            guide_chance = data.get("2nd_state_Guide_Draw_Chance", "") or data.get("Guide_Draw_Chance", "")
            if guide_chance:
                lines.append(f"Draw Chance: {guide_chance}%")

        return "<br>".join(lines)

    def _update_card_info(self, card_id):
        if card_id:
            html = self._build_card_info_html(card_id)
        else:
            html = "<i>Select a card from the kit lists to see details.</i>"
        self.card_info_box.set_text(html)

    def _get_card_id_from_display_name(self, display_name):
        for cid, dname in self.card_names.items():
            if dname == display_name:
                return cid
        # Fallback: display_name is the card_id itself
        if display_name in self.available_card_pool:
            return display_name
        return None

    # ---------- Actions ----------

    def _increment_stat(self, key):
        cfg = STAT_CONFIG[key]
        if self.stats[key] < cfg["max"] and self._points_remaining() > 0:
            self.stats[key] += 1
            self._update_stat_buttons()

    def _decrement_stat(self, key):
        cfg = STAT_CONFIG[key]
        if self.stats[key] > cfg["min"]:
            self.stats[key] -= 1
            self._update_stat_buttons()

    def _select_special(self, name):
        self.selected_special = name
        self._update_special_btn_visuals()
        self.special_desc_box.set_text(self._ability_desc_html(name))

    def _add_to_kit(self):
        if len(self.selected_kit) >= MAX_KIT_CARDS:
            return
        sel = self.avail_list.get_single_selection()
        if sel is None:
            return
        cid = self._get_card_id_from_display_name(sel)
        if cid is None:
            return
        # Check not already selected
        if any(item["card_id"] == cid for item in self.selected_kit):
            return
        # Determine state - check if preset kits have specific states
        state = 1
        # Check card data for default state
        card = load_card(cid, silent=True)
        if card and card.get("states", 1) >= 2:
            # For scavenger's kit, state 2 is the crafted version
            if "scavenger" in cid.lower():
                state = 2
        self.selected_kit.append({"card_id": cid, "state": state})
        self._update_selected_list_ui()
        self._update_available_list_ui()

    def _remove_from_kit(self):
        sel = self.selected_list.get_single_selection()
        if sel is None:
            return
        cid = self._get_card_id_from_display_name(sel)
        if cid is None:
            return
        self.selected_kit = [item for item in self.selected_kit if item["card_id"] != cid]
        self._update_selected_list_ui()
        self._update_available_list_ui()

    def _apply_suggested_kit(self):
        kit_name = self.kit_dropdown.selected_option
        if isinstance(kit_name, tuple):
            kit_name = kit_name[0]
        card_ids = SUGGESTED_KITS.get(kit_name, [])
        self.selected_kit = []
        for cid in card_ids:
            if len(self.selected_kit) >= MAX_KIT_CARDS:
                break
            # Check card exists
            if cid in self.available_card_pool or load_card(cid, silent=True) is not None:
                state = 1
                if "scavenger" in cid.lower():
                    state = 2
                # For warrior arrows preset
                if cid == "starter_warrior_arrows":
                    state = 2
                self.selected_kit.append({"card_id": cid, "state": state})
        self._update_selected_list_ui()
        self._update_available_list_ui()

    def _load_preset(self, preset_name):
        preset = PRESET_CLASSES[preset_name]
        # Set stats
        for key, val in preset["stats"].items():
            self.stats[key] = val
        self._update_stat_buttons()

        # Set special
        self._select_special(preset["special"])

        # Set attack names
        self.proj_name_entry.set_text(preset["proj_name"])
        self.melee_name_entry.set_text(preset["melee_name"])

        # Set name
        self.name_entry.set_text(preset_name)

        # Set kit
        self.selected_kit = []
        for item in preset["kit"]:
            cid = item["card_id"]
            if cid in self.available_card_pool or load_card(cid, silent=True) is not None:
                self.selected_kit.append({"card_id": cid, "state": item.get("state", 1)})
        # Cap at MAX_KIT_CARDS
        self.selected_kit = self.selected_kit[:MAX_KIT_CARDS]
        self._update_selected_list_ui()
        self._update_available_list_ui()

    def _reset_stats(self):
        self._init_stats()
        self._update_stat_buttons()

    # ---------- Save / Load ----------

    def _sanitize_filename(self, name):
        safe = re.sub(r'[^a-zA-Z0-9_\- ]', '', name).strip()
        safe = re.sub(r'\s+', '_', safe)
        return safe if safe else "unnamed"

    def _build_save_data(self):
        name = self.name_entry.get_text().strip()
        proj_name = self.proj_name_entry.get_text().strip() or "Throw Rock"
        melee_name = self.melee_name_entry.get_text().strip() or "Fist"

        return {
            "version": 1,
            "name": name,
            "created": datetime.datetime.now().isoformat(timespec='seconds'),
            "stats": {
                "hp": self._display_value("hp"),
                "max_hp": self._display_value("hp"),
                "movement": self._display_value("movement"),
                "projectile_range": self._display_value("projectile_range"),
                "melee_damage": self._display_value("melee_damage"),
                "projectile_damage": self._display_value("projectile_damage"),
            },
            "point_buy": {
                "budget": POINT_BUDGET,
                "spent": self._points_spent(),
                "allocation": dict(self.stats),
            },
            "attacks": {
                "projectile": {"name": proj_name, "damage": self._display_value("projectile_damage")},
                "melee": {"name": melee_name, "damage": self._display_value("melee_damage")},
            },
            "special_ability": self.selected_special,
            "starting_kit": list(self.selected_kit),
            "class_name": "Custom"
        }

    def _save_character(self):
        name = self.name_entry.get_text().strip()
        if not name:
            self.warning_label.set_text("Enter a character name before saving.")
            return
        if self._points_remaining() < 0:
            self.warning_label.set_text("Over budget! Adjust stats before saving.")
            return

        data = self._build_save_data()
        filename = self._sanitize_filename(name) + ".json"
        filepath = os.path.join("characters", filename)

        try:
            with open(filepath, 'w') as f:
                json.dump(data, f, indent=2)
            self.warning_label.set_text(f"Saved: {filepath}")
        except Exception as e:
            self.warning_label.set_text(f"Save error: {e}")

    def _load_character(self):
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        filepath = filedialog.askopenfilename(
            title="Load Character",
            initialdir="characters",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")])
        root.destroy()

        if not filepath:
            return

        try:
            with open(filepath, 'r') as f:
                data = json.load(f)
        except Exception as e:
            self.warning_label.set_text(f"Load error: {e}")
            return

        # Restore name
        self.name_entry.set_text(data.get("name", ""))

        # Restore stats from point_buy allocation
        alloc = data.get("point_buy", {}).get("allocation", {})
        for key in STAT_CONFIG:
            if key in alloc:
                self.stats[key] = alloc[key]
        self._update_stat_buttons()

        # Restore special
        special = data.get("special_ability", "")
        if special in SPECIAL_ABILITIES:
            self._select_special(special)

        # Restore attack names
        attacks = data.get("attacks", {})
        proj = attacks.get("projectile", {}).get("name", "")
        melee = attacks.get("melee", {}).get("name", "")
        if proj:
            self.proj_name_entry.set_text(proj)
        if melee:
            self.melee_name_entry.set_text(melee)

        # Restore kit
        self.selected_kit = []
        for item in data.get("starting_kit", []):
            cid = item.get("card_id", "")
            state = item.get("state", 1)
            if cid:
                self.selected_kit.append({"card_id": cid, "state": state})
        self._update_selected_list_ui()
        self._update_available_list_ui()

        self.warning_label.set_text(f"Loaded: {os.path.basename(filepath)}")

    # ---------- Custom rendering ----------

    def _draw_summary(self):
        rect = self.summary_rect
        # Panel background
        pygame.draw.rect(self.screen, PANEL_BG, rect, border_radius=6)
        pygame.draw.rect(self.screen, PANEL_BORDER, rect, 1, border_radius=6)

        x = rect.x + 16
        y = rect.y + 12
        line_h = 28

        font_title = pygame.font.SysFont("freesansbold", 22, bold=True)
        font = pygame.font.SysFont("freesansbold", 18)
        font_small = pygame.font.SysFont("freesansbold", 15)

        name = self.name_entry.get_text().strip() or "Unnamed"
        self.screen.blit(font_title.render(name, True, GOLD), (x, y))
        y += line_h + 4

        # Stats
        hp = self._display_value("hp")
        lines = [
            f"HP: {hp} / {hp}",
            f"Movement: {self._display_value('movement')}",
            f"Proj Range: {self._display_value('projectile_range')}",
        ]

        melee_name = self.melee_name_entry.get_text().strip() or "Punch"
        proj_name = self.proj_name_entry.get_text().strip() or "Throw"
        lines.append(f"Melee: {melee_name} ({self._display_value('melee_damage')} dmg)")
        lines.append(f"Projectile: {proj_name} ({self._display_value('projectile_damage')} dmg)")

        for line in lines:
            self.screen.blit(font.render(line, True, LIGHT_GRAY), (x, y))
            y += line_h

        y += 6
        # Special
        ab = SPECIAL_ABILITIES.get(self.selected_special, {})
        self.screen.blit(font.render(f"Special: {self.selected_special}", True, LIGHT_GOLD), (x, y))
        y += line_h - 4
        summary = ab.get("summary", "")
        self.screen.blit(font_small.render(summary, True, DIM_GRAY), (x + 8, y))
        y += line_h

        # Kit
        kit_count = len(self.selected_kit)
        color = GREEN if kit_count > 0 else RED
        self.screen.blit(font.render(f"Starting Kit: {kit_count}/{MAX_KIT_CARDS}", True, color), (x, y))
        y += line_h - 6
        for item in self.selected_kit:
            cid = item["card_id"]
            dname = self.card_names.get(cid, cid)
            # Truncate long names
            if len(dname) > 35:
                dname = dname[:32] + "..."
            self.screen.blit(font_small.render(f"  - {dname}", True, DIM_GRAY), (x, y))
            y += 20

        # Points
        remaining = self._points_remaining()
        pts_color = GREEN if remaining >= 0 else RED
        y = rect.bottom - 32
        self.screen.blit(font.render(
            f"Points: {self._points_spent()}/{POINT_BUDGET} spent  ({remaining} remaining)",
            True, pts_color), (x, y))

    def _draw_title(self):
        font = pygame.font.SysFont("freesansbold", 30, bold=True)
        title = font.render("CHARACTER CREATOR", True, GOLD)
        self.screen.blit(title, (self.W // 2 - title.get_width() // 2, int(self.H * 0.012)))

    def _draw_selected_count(self):
        font = pygame.font.SysFont("freesansbold", 16)
        r = self.selected_count_label_rect
        text = f"Selected ({len(self.selected_kit)}/{MAX_KIT_CARDS}):"
        self.screen.blit(font.render(text, True, LIGHT_GOLD), (r.x, r.y + 2))

    # ---------- Main loop ----------

    def run(self):
        running = True
        while running:
            dt = self.clock.tick(60) / 1000.0

            for ev in pygame.event.get():
                if ev.type == pygame.QUIT:
                    running = False

                if ev.type == pygame.KEYDOWN:
                    if ev.key == pygame.K_ESCAPE:
                        running = False

                if ev.type == pygame_gui.UI_BUTTON_PRESSED:
                    ui_el = ev.ui_element

                    if ui_el == self.back_btn:
                        running = False

                    elif ui_el == self.save_btn:
                        self._save_character()

                    elif ui_el == self.load_btn:
                        self._load_character()

                    elif ui_el == self.reset_btn:
                        self._reset_stats()

                    elif ui_el == self.add_btn:
                        self._add_to_kit()

                    elif ui_el == self.remove_btn:
                        self._remove_from_kit()

                    elif ui_el == self.kit_apply_btn:
                        self._apply_suggested_kit()

                    else:
                        # Check stat buttons
                        for key in STAT_CONFIG:
                            if ui_el == self.stat_plus_btns[key]:
                                self._increment_stat(key)
                                break
                            if ui_el == self.stat_minus_btns[key]:
                                self._decrement_stat(key)
                                break

                        # Check special buttons
                        for name, btn in self.special_btns.items():
                            if ui_el == btn:
                                self._select_special(name)
                                break

                        # Check preset buttons
                        for preset_name, btn in self.preset_btns.items():
                            if ui_el == btn:
                                self._load_preset(preset_name)
                                break

                if ev.type == pygame_gui.UI_SELECTION_LIST_NEW_SELECTION:
                    if ev.ui_element in (self.avail_list, self.selected_list):
                        sel_text = ev.text
                        cid = self._get_card_id_from_display_name(sel_text)
                        self._update_card_info(cid)

                self.manager.process_events(ev)

            self.manager.update(dt)

            # Draw
            self.screen.fill(DARK_CHARCOAL)
            self.manager.draw_ui(self.screen)
            self._draw_title()
            self._draw_summary()
            self._draw_selected_count()

            pygame.display.flip()

        pygame.quit()
        sys.exit()


if __name__ == "__main__":
    app = CharacterCreator()
    app.run()
